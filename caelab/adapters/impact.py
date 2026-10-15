"""User FE explicit execution through the existing evaluation/owned-process boundary."""
from copy import deepcopy
import math
from pathlib import Path
import re
import shutil
import sys

from .. import impact_model as domain
from ..evaluation import file_hash
from ..execution_control import run_owned_command,check_cancelled,ExecutionCancelled,ExecutionCleanupFailed
from ..storage import save_json,canonical_hash
from .opencourant_runtime import runtime as selected_runtime
from .impact_results import history,read_vtk,write_post,validate_frame_identity
from .impact_admission import global_gravity,validate_physics,normalize_contact_friction,normalize_surfaces
from .impact_timing import engine_termination,history_inventory,sample_coverage,energy_observations


def converted_mesh(path, expected, input_nodes):
    """Postflight native IDs and ordered connectivity; do not trust converter exit alone."""
    blocks={}; current=None
    for line in Path(path).read_text(encoding='ascii').splitlines():
        if not line.strip() or line.lstrip().startswith('#'): continue
        if line.startswith('/'):
            current=line.strip(); blocks.setdefault(current,[])
        elif current: blocks[current].append(line)
    nodes={}; elements={}
    for key,rows in blocks.items():
        if key=='/NODE':
            for line in rows:
                ident=int(line[:10]); values=[float(line[10+i*20:30+i*20]) for i in range(3)]
                if ident in nodes: raise ValueError('Converted duplicate node')
                nodes[ident]=values
        elif key.startswith(('/TETRA4/','/TETRA10/','/BRICK/')):
            tokens=[int(line[i:i+10]) for line in rows for i in range(0,len(line),10) if line[i:i+10].strip()]
            width=10 if key.startswith('/TETRA10/') else 4 if key.startswith('/TETRA4/') else 8
            if len(tokens)%(width+1): raise ValueError('Incomplete converted element')
            for i in range(0,len(tokens),width+1):
                ident=tokens[i]
                if ident in elements: raise ValueError('Converted duplicate element')
                elements[ident]=tokens[i+1:i+width+1]
    if set(nodes)!=set(input_nodes) or set(elements)!=set(expected['elements']):
        raise ValueError('Converter changed native mesh identity/coverage')
    for n,position in nodes.items():
        # Converter writes decimal coordinates. Record its precision rather than
        # changing the retained native source. The comparison is input admission.
        if any(not math.isclose(a,b,rel_tol=2e-9,abs_tol=1e-10) for a,b in zip(position,input_nodes[n])):
            raise ValueError('Converter changed a native coordinate')
    for eid,row in expected['elements'].items():
        order=(0,2,1,3,6,5,4,7,9,8) if row['type']=='C3D10' else (0,2,1,3) if row['type']=='C3D4' else tuple(range(8))
        if elements[eid]!=[row['nodes'][i] for i in order]:
            raise ValueError('Converter changed ordered element connectivity')
    return {'node_count':len(nodes),'element_count':len(elements),'input_sha256':file_hash(path)}


def starter_admission(path, model):
    text=Path(path).read_text(encoding='ascii',errors='strict')
    if 'NORMAL TERMINATION' not in text or 'NO SYNTAX ERROR DETECTED' not in text:
        raise ValueError('Starter did not record syntax-checked normal termination')
    for name in ('ERROR','WARNING'):
        values=re.findall(r'^\s*(\d+) '+name+r'\(S\)\s*$',text,re.MULTILINE)
        if not values or any(int(v) for v in values):
            raise ValueError('Starter '+name.lower()+' record requires review; Engine was not started')
    count=re.search(r'^\s*NUMNOD:[^\n]*?\s(\d+)\s*$',text,re.MULTILINE)
    if not count or int(count[1])!=len(model['nodes']):
        raise ValueError('Starter node count differs from the admitted user mesh')
    for label in ('WORK UNIT SYSTEM','INPUT UNIT SYSTEM'):
        match=re.search(label+r'[^\n]*\(\s*Mg\s*,\s*mm\s*,\s*s\s*\)\s+([0-9.E+-]+)\s+([0-9.E+-]+)\s+([0-9.E+-]+)',text)
        if not match or not all(math.isclose(float(v),e,rel_tol=1e-9) for v,e in zip(match.groups(),(1000.,.001,1.))):
            raise ValueError('Starter units differ from Mg/mm/s; original log retained')
    # Automatic property defaults can be incompatible even with zero warnings.
    # Inspect the actual Starter review, never infer resolved flags from input.
    review=[];lines=text.splitlines();part_type=None
    for index,line in enumerate(lines[:-1]):
        if 'Part id,name:' in line:
            kind=re.search(r'Elm type:\s*(\S+)',line)
            part_type=kind[1] if kind else None
        columns=line.split()
        if 'Isolid' not in columns or 'Ismstr' not in columns or 'Itetra4' not in columns:continue
        tokens=lines[index+1].split()
        if len(tokens)!=len(columns) or any(not re.fullmatch(r'[+-]?\d+',v) for v in tokens):
            raise ValueError('Starter formulation review is incomplete; Engine was not started')
        actual=dict(zip(columns,map(int,tokens)));review.append(actual)
        tetra_part=(part_type=='TETRA4' or part_type is None and
                    all(e['type']=='C3D4' for e in model['elements'].values()))
        if tetra_part and actual['Itetra4']==3 and actual['Ismstr'] in (10,12):
            raise ValueError('Starter resolved Itetra4=3 with incompatible Ismstr=10/12; review the original solid property and material. For supported elastic C3D4, explicitly select Itetra4=1000. Engine was not started')
    return {'name':'native_starter','status':'PASS','units':'Mg/mm/s','warnings':0,'errors':0,
            'actual_formulation_review':review}


class ImpactAdapter:
    backend,version=domain.BACKEND,'2'
    input_source_files=[__file__,domain.__file__,Path(__file__).with_name('impact_admission.py'),
                        Path(__file__).with_name('impact_timing.py'),
                        Path(domain.__file__).with_name('impact_source.py'),
                        Path(domain.__file__).with_name('impact_sets.py'),
                        *[Path(domain.__file__).with_name(name) for name in (
                            'impact_assembly.py','impact_input_edits.py','impact_rad_source.py',
                            'impact_native.py','impact_initial_state.py','impact_retained.py','impact_native_io.py',
                            'impact_reference_bindings.py')]]
    default_settings=staticmethod(domain.default_settings)
    validate_settings=staticmethod(domain.validate_settings)
    input_runtime_identity=staticmethod(lambda:{'runtime':'explicit_selected_opencourant','qualification':'UNKNOWN'})

    def describe_model(self,settings):
        return {'backend':self.backend,'model':{'settings':domain.validate_settings(settings)}}

    def describe_ports(self,settings):
        domain.validate_settings(settings)
        return {'inputs':{},'outputs':{},'coordinate_frame':'MODEL_GLOBAL','clock':'physical_seconds',
                'qualification':'UNKNOWN'}

    def describe_inputs(self,settings):
        s=domain.validate_settings(settings); rows=[]
        if s['source']['format']=='RAD':
            raise ValueError('native 원문 field 편집을 사용하세요. 원문과 분리된 수치 연구 입력 binding은 첫 지원 밖입니다')
        for i,m in enumerate(s['motions']):
            for key,label,unit in (('velocity_mm_s','초기 속도','mm/s'),('omega_rad_s','초기 각속도','rad/s')):
                if key=='velocity_mm_s' and m['mode']!='velocity': continue
                for j,axis in enumerate('XYZ'):
                    path=['motions',i,key,j]
                    rows.append({'id':f'motion_{i}_{key}_{j}','label':m['node_set']+' '+label+' '+axis,
                        'unit':unit,'value':m[key][j],'lower':-1e9,'upper':1e9,
                        'settings_path':path,'declaration_paths':[['model','settings',*path]]})
            if m['mode']!='velocity':
                path=['motions',i,'height_mm']
                rows.append({'id':f'motion_{i}_height','label':m['node_set']+' 높이','unit':'mm',
                    'value':m['height_mm'],'lower':1e-12,'upper':1e9,'settings_path':path,
                    'declaration_paths':[['model','settings',*path]]})
        for i,law in enumerate(s.get('cohesive',[])):
            for key,label,unit in (('normal_strength_mpa','법선 강도','MPa'),('shear_strength_mpa','전단 강도','MPa'),
                                  ('mode_I_n_mm','모드 I 파괴 에너지','N/mm'),('mode_II_n_mm','모드 II 파괴 에너지','N/mm')):
                path=['cohesive',i,key]
                rows.append({'id':f'cohesive_{i}_{key}','label':law['material']+' '+label,'unit':unit,
                    'value':law[key],'lower':1e-12,'upper':1e12,'settings_path':path,
                    'declaration_paths':[['model','settings',*path]]})
        if not 1<=len(rows)<=32: raise ValueError('수치 연구에는 1~32개의 명시 초기 운동 성분이 필요합니다')
        return rows

    def bind_inputs(self,settings,values):
        from ..model_parameters import expected_settings
        return domain.validate_settings(expected_settings(settings,self.describe_inputs(settings),values))

    def run(self,settings,*,output,runtime=None):
        if runtime and set(runtime)-{'threads','memory_mb'}:
            raise ValueError('Operator runtime cannot be changed by the model')
        s=domain.validate_settings(settings);model=domain.model_from_settings(s)
        out=Path(output);native=out/'native'
        save_json(out/'input.json',s)
        from ..impact_source import retain
        from ..impact_initial_state import describe as initial_integrals
        from ..impact_retained import artifact_receipt,reference,catalog
        retain(s['source'],out/'source_bundle')
        save_json(out/'generated_sets.json',s.get('generated_sets',[]))
        save_json(out/'source_lineage.json',model.get('lineage',{}))
        direct=s['source']['format']=='RAD';name='impact';frames=[]
        phase='input_admission';result={'execution_status':'FAILED','responses':{},'checks':[],
            'diagnostics':{'decision':'NOT_RELEASED','qualification':'UNKNOWN',
                           'native_execution_status':'NOT_STARTED',
                           'input_route':'NATIVE_DIRECT' if direct else 'INP_COMPILED'},'post_artifacts':[]}
        names=None;identity=None;env=None
        def command(argv,label):
            check_cancelled()
            process=run_owned_command([str(x) for x in argv],native,label,env=env,owned_tree=True)
            if process.returncode:raise RuntimeError(label+' failed; native log and partial files retained')
            return process
        try:
            if direct:
                from ..impact_native import parse_source,export_direct
                parsed=parse_source(s['source']);name=parsed['name']
                direct_receipt=export_direct(s,native)
                initial=parsed['initial'];physics=parsed['physics']
                save_json(out/'native_direct_export.json',direct_receipt)
                frozen={key:item['sha256'] for key,item in direct_receipt['files'].items()}
                save_json(out/'physical_admission.json',{'physics':physics,
                    'route':'NATIVE_DIRECT','original_native_bytes_preserved':True})
                damage_receipt={'elements':{},'geometry':{},'status':'NOT_REQUESTED_NATIVE_ELASTIC'}
                result['checks'].append({'name':'native_direct_mesh_and_physics','status':'PASS',
                                        'converter_execution':'NOT_PERFORMED',**physics})
            else:
                native.mkdir()
                (out/'original.inp').write_text(s['source']['text'],encoding='ascii',newline='\n')
                effective,initial=domain.render(s)
                (native/'impact.inp').write_text(effective,encoding='ascii',newline='\n')
            save_json(out/'initial_conditions.json',initial)
            save_json(out/'initial_mass_properties.json',initial_integrals(model,initial,s))
            actual_model={**model,'nodes':initial['nodes']}
            phase='runtime'
            names,env,identity=selected_runtime()
            result['diagnostics']['runtime']=identity
            if not direct:
                phase='conversion'
                command([sys.executable,Path(__file__).with_name('inp2rad_worker.py'),native/'impact.inp'],'convert')
                for tail in ('0000','0001'):
                    shutil.copyfile(native/f'impact_{tail}.rad',out/f'converted_{tail}.rad')
                result['checks'].append({'name':'converted_mesh','status':'PASS',
                    **converted_mesh(native/'impact_0000.rad',model,initial['nodes'])})
                starter=native/'impact_0000.rad'
                effective_gravity,gravity_receipt=global_gravity(starter.read_text(encoding='ascii'),s['gravity_mm_s2'])
                effective_gravity=normalize_contact_friction(effective_gravity,s)
                effective_gravity,surface_receipt=normalize_surfaces(effective_gravity,model)
                starter.write_text(effective_gravity,encoding='ascii',newline='\n')
                physics=validate_physics(effective_gravity,model,initial,s)
                from ..impact_damage import apply_laws,verify_laws
                effective_gravity,damage_receipt=apply_laws(effective_gravity,actual_model,s.get('cohesive',[]))
                verify_laws(effective_gravity,actual_model,s.get('cohesive',[]),damage_receipt)
                starter.write_text(effective_gravity,encoding='ascii',newline='\n')
                save_json(out/'physical_admission.json',{'physics':physics,'gravity':gravity_receipt,
                                                       'surface_serialization':surface_receipt})
                (native/'impact_0001.rad').write_text(domain.engine_deck(s),encoding='ascii',newline='\n')
                frozen={p.name:file_hash(p) for p in native.glob('*.rad')}
            save_json(out/'damage_definition.json',damage_receipt)
            result['checks'].append({'name':'effective_physics','status':'PASS'})
            save_json(out/'effective_deck_pins.json',frozen)
            phase='starter'
            command([names['starter'],'-i',name+'_0000.rad','-np','1','-nt','2'],'starter')
            result['checks'].append(starter_admission(native/(name+'_0000.out'),model))
            if any(file_hash(native/key)!=value for key,value in frozen.items()):
                raise ValueError('Effective deck/include bytes changed during Starter')
            phase='engine';result['diagnostics']['native_execution_status']='STARTED'
            process=command([names['engine'],'-i',name+'_0001.rad','-nt','2'],'engine')
            termination=engine_termination(native/(name+'_0001.out'),process.stdout,s['time']['end_s'])
            result['diagnostics']['native_termination']=termination
            if termination['status']!='NORMAL':
                raise ValueError('Engine termination is '+termination['status']+'; native stop evidence retained')
            if any(file_hash(native/key)!=value for key,value in frozen.items()):
                raise ValueError('Effective deck/include bytes changed during execution')
            if selected_runtime()[2]!=identity:raise ValueError('Selected runtime changed during execution')
            result['diagnostics']['native_execution_status']='SUCCEEDED'
            result['execution_status']='SUCCEEDED'
        except ExecutionCleanupFailed:
            result['diagnostics'].update(last_phase=phase,cleanup_unconfirmed=True,
                source_sha256=canonical_hash(s['source']))
            save_json(out/'impact_execution.json',result)
            raise
        except ExecutionCancelled as error:
            result['execution_status']='CANCELLED';result['diagnostics']['reason']=str(error)
            if result['diagnostics']['native_execution_status']=='STARTED':
                result['diagnostics']['native_execution_status']='CANCELLED'
        except (ValueError,KeyError,TypeError,OSError,RuntimeError,ArithmeticError) as error:
            result['diagnostics']['reason']=str(error)
            if result['diagnostics']['native_execution_status']=='STARTED':
                result['diagnostics']['native_execution_status']='FAILED'
        # A cancelled owner cannot start postprocessors. Later explicit read jobs
        # retain the original solver failure/cancellation separately.
        if result['execution_status']=='SUCCEEDED':
            try:
                phase='readback'
                read_outputs(out,s,actual_model,physics,damage_receipt,result,frames,
                             name=name,command=command,names=names,convert=True)
            except ExecutionCleanupFailed:
                result['diagnostics'].update(last_phase=phase,cleanup_unconfirmed=True,
                    source_sha256=canonical_hash(s['source']))
                save_json(out/'impact_execution.json',result)
                raise
            except ExecutionCancelled as error:
                result['execution_status']='CANCELLED';result['diagnostics']['readback_error']=str(error)
            except (ValueError,KeyError,TypeError,OSError,RuntimeError) as error:
                result['execution_status']='FAILED';result['diagnostics']['readback_error']=str(error)
        result['diagnostics'].update(last_phase=phase,source_sha256=canonical_hash(s['source']),
            physical_failure='UNKNOWN',partial_output=result['execution_status']!='SUCCEEDED',
            contact_scope='TYPE24 corner-faceted surfaces, no static penalty-law equivalence',
            limitations=['No inferred failure/life from solver termination','Unknown native arrays retained without invented units',
                         'Selected nodal force is all-contact, not pair-specific; impulse is animation-sample quadrature',
                         'First hierarchy/native route: elastic C3D4; unsupported influence cards block execution',
                         'Input-derived COM/inertia are not solver RBODY measurements; general rigid native cards remain blocked'])
        result['retained_native']=artifact_receipt(out,frames)
        save_json(out/'impact_execution.json',result)
        # The evaluator already knows how to retain native channels and source
        # references. The receipt cannot recursively contain its own digest.
        result['diagnostics']['native_outcome']=reference(out)
        if frames:
            result['native_channels']=catalog(self.backend,result['diagnostics']['native_outcome'],out)
            result['native_result']={'backend':self.backend,'directory':'.'}
        return result


def read_outputs(out,s,model,physics,damage,result,frame_records,*,name,command=None,names=None,convert=False):
    """Actual TH/ANIM reader shared with an explicit, solver-free re-read job."""
    from ..impact_retained import FrameView,frame_record
    out=Path(out);native=out/'native'
    th=native/(name+'T01')
    if not th.is_file() or not th.with_name(th.name+'_TITLES').is_file():
        raise ValueError('Native history or matching titles missing')
    if convert:command([names['th_to_csv'],th.name,'history'],'history_convert')
    responses,table=history(native/'history.csv')
    save_json(out/'history.json',table);result['responses']=responses
    integrity=history_inventory(th,table)
    coverage=sample_coverage([r['values'][0] for r in table['rows']],s['time']['end_s'],s['time']['history_interval_s'])
    coverage['native_records']=integrity
    coverage['converted_source']={'artifact':'history.csv','sha256':file_hash(native/'history.csv')}
    result['diagnostics']['history_coverage']=coverage
    result['diagnostics']['energy_observations']=energy_observations(table,native/'history.csv')
    for response in responses.values():response['metadata']['sample_coverage']=deepcopy(coverage)
    if convert:
        paths=sorted(native.glob(name+'A[0-9]*'),key=lambda p:int(p.name[len(name)+1:]))
    else:paths=sorted(native.glob('frame[0-9][0-9][0-9][0-9].vtk'))
    for index,path in enumerate(paths):
        check_cancelled()
        if index>=1024:raise ValueError('Native frame count exceeds limit')
        if convert:
            process=command([names['anim_to_vtk'],path.name],f'animation_{index:04d}')
            payload=process.stdout
            if isinstance(payload,str):payload=payload.encode('ascii')
            target=native/f'frame{index:04d}.vtk';target.write_bytes(payload)
        else:target=path
        raw=read_vtk(target);raw['coverage']=validate_frame_identity(raw,model,physics)
        if frame_records and raw['time']<=frame_records[-1]['time_s']:
            raise ValueError('Duplicate/non-monotonic native animation time')
        frame_records.append(frame_record(out,target,raw))
    if not frame_records:raise ValueError('No native animation frame was retained')
    frames=FrameView(out,frame_records,model,physics)
    frame_coverage=sample_coverage([r['time_s'] for r in frame_records],s['time']['end_s'],s['time']['field_interval_s'])
    result['diagnostics']['animation_coverage']=frame_coverage
    from ..impact_responses import read_selected
    chosen,selection_record=read_selected(frames,model,s.get('responses',[]),damage)
    for response in chosen.values():response.setdefault('metadata',{})['sample_coverage']=deepcopy(frame_coverage)
    result['responses'].update(chosen)
    save_json(out/'selected_responses.json',selection_record)
    metadata=write_post(out/'post',frames,damage=damage)
    pvd=out/'post/impact.pvd'
    result['post_artifacts']=[{'relative':'post/impact.pvd','sha256':file_hash(pvd),
        'native_metadata':metadata,'response':'impact_fields',
        'dependencies':{p.name:file_hash(p) for p in sorted(pvd.parent.glob('*.vtu'))}}]
    result['diagnostics']['frame_count']=len(frames)
