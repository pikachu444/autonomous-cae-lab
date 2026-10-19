"""TR-F ports over existing frozen single-solid CCX ownership and readers."""
from copy import deepcopy
from pathlib import Path
import json
import shutil
import uuid
import numpy as np

from ..conservative_load_transfer import reaction_field, EQUILIBRIUM_TOLERANCE, resultants
from ..contact_deck import validate_model, render, FACES
from ..contact_status import read_status, require_converged
from ..storage import check_id, save_json, canonical_hash
from ..contact_steps import compile_program, default_program, profile, validate_contributions, _at
from .contact_fem import validate_snapshot, ContactFemCalculixAdapter
from .frozen_fem import _read, _relative, _sha, read_frd, _gates

SOURCE = 'structure.calculix.support_reaction'
RECEIVER = 'structure.calculix.conservative_load'


def _need(ok, message):
    if not ok: raise ValueError(message)


def _profile(path):
    manifest, model, pins, _ = validate_snapshot(path)
    nodes, elements, bodies = validate_model(model)
    validate_contributions(model)
    _need(model.get('analysis_scope') == 'single_solid_static' and not model['contacts'] and
          model['step']['geometry'] == 'linear' and len(bodies) == 1 and
          not any(model.get(key) for key in ('restart','dynamic','initial_fields','periodic_constraints','pretension_sections')),
          'TR-F requires a single linear static C3D10 body without coupling')
    _need(all(not m.get('plasticity') and m.get('law') == 'isotropic_linear_elastic'
              for m in model['materials']), 'TR-F requires isotropic linear elasticity')
    # Inspect the actual native keywords, in addition to the exact existing
    # frozen model->deck equality. No TRANSFORM/MPC/TIE/DLOAD/body force cards.
    allowed={'*HEADING','*NODE','*ELEMENT','*MATERIAL','*ELASTIC','*SOLID SECTION',
             '*STEP','*STATIC','*BOUNDARY','*CLOAD','*NODE FILE','*EL FILE','*END STEP','*CONTROLS','*AMPLITUDE'}
    text=_read(Path(path).parent/'contact.inp').decode('ascii')
    cards=[line.split(',')[0].strip().upper() for line in text.splitlines()
           if line.strip().startswith('*') and not line.strip().startswith('**')]
    _need(set(cards)<=allowed and cards.count('*STEP')==1 and cards.count('*STATIC')==1,
          'The executed deck contains an unsupported load, constraint or procedure')
    _static_stage(model)
    _gates(nodes,elements,{(r['node_id'],r['component']) for r in model['boundary_dofs']})
    return manifest,model,pins,nodes,elements


def _static_stage(model):
    program=model.get('analysis_steps') or default_program(model['step'],model['conditions'])
    rows=compile_program(program,model['conditions'])
    _need(len(rows)==1 and rows[0]['procedure']=='static',
          'TR-F currently supports one authored STATIC stage')
    return rows[0]


def boundary(model, selected_faces):
    nodes,elements,_=validate_model(model)
    _need(isinstance(selected_faces,list) and selected_faces and
          len({tuple(f) for f in selected_faces})==len(selected_faces),'Select distinct receiver TRI6 faces')
    owners={}
    for e,row in elements.items():
        for face,slots in FACES.items(): owners.setdefault(tuple(sorted(row[s] for s in slots[:3])),[]).append((e,face))
    faces=[]
    for pair in selected_faces:
        _need(isinstance(pair,list) and len(pair)==2 and all(type(v)is int for v in pair),
              'Select native element and face pairs')
        e,face=pair
        _need(e in elements and face in FACES,'Receiver boundary has a foreign element or face')
        ids=[elements[e][s] for s in FACES[face]]
        _need(len(owners[tuple(sorted(ids[:3]))])==1,'Select an external receiver boundary, not an internal face')
        faces.append(ids)
    ids=sorted({n for row in faces for n in row})
    return {'node_ids':ids,'coordinates':[nodes[n] for n in ids],'faces':faces}


def bind_receiver_model(original, field, target_faces):
    """Add an explicit force contribution, retaining the authored native task.

    The imported force ramps from zero across the receiver's single STATIC
    stage. Existing force curves, supports and stage settings retain their
    exact definitions. No source clock is interpreted as receiver time.
    """
    validate_model(original);_static_stage(original)
    _need(original.get('analysis_scope')=='single_solid_static' and not original['contacts'] and
          original['step']['geometry']=='linear' and
          not any(original.get(k) for k in ('restart','dynamic','initial_fields','periodic_constraints','pretension_sections')) and
          all(m.get('law')=='isotropic_linear_elastic' and not m.get('plasticity') for m in original['materials']),
          'TR-F requires a single linear elastic STATIC solid without coupled state')
    selected=boundary(original,target_faces)
    _need(isinstance(field,dict) and field.get('mapping')=='tri6_conservative_load' and
          field.get('measure')=='applied_nodal_force' and field.get('unit')=='N' and
          field.get('association')=='POINTS' and field.get('component')=='VECTOR' and
          field.get('frame')=='global_cartesian' and field.get('coordinate_units')=='mm' and
          field.get('node_ids')==selected['node_ids'] and field.get('coordinates')==selected['coordinates'],
          'Mapped load differs from the selected receiver boundary or units')
    _need(isinstance(field.get('receipt_sha256'),str) and len(field['receipt_sha256'])==64,
          'The mapped load has no numerical receipt identity')
    values=np.asarray(field['value'],dtype=float)
    _need(values.shape==(len(selected['node_ids']),3) and np.isfinite(values).all(),
          'Mapped nodal loads are incomplete')
    _need(np.any(values!=0),'The transferred receiver load is zero')
    model=deepcopy(original)
    if 'analysis_steps' not in model:
        model['analysis_steps']=default_program(model['step'],model['conditions'])
    ids={c['object_id'].upper() for c in model['conditions']}
    identifier='ImportedNodalForce';suffix=1
    while identifier.upper() in ids:
        identifier='ImportedNodalForce_'+str(suffix);suffix+=1
    body={r['body_id'] for r in model['nodes'] if r['node_id'] in selected['node_ids']}
    _need(len(body)==1,'Select a boundary on one receiving solid')
    weights=[{'node_id':n,'component':d+1,'weight':float(f)}
             for n,row in zip(selected['node_ids'],values) for d,f in enumerate(row) if f!=0]
    model['conditions'].append({'object_id':identifier,'label':'가져온 절점 하중',
        'type':'Fem::ConstraintForce','body_id':body.pop(),'total_force_N':1.,'force_weights':weights})
    loads={(r['node_id'],r['component']):deepcopy(r) for r in model['loads']}
    for row in weights:
        key=row['node_id'],row['component']
        if key not in loads:loads[key]={'node_id':key[0],'component':key[1],'force_N':0.}
        loads[key]['force_N']+=row['weight']
    model['loads']=list(loads.values())
    stage=model['analysis_steps']['steps'][0]
    stage['curves'].append({'condition_id':identifier,'component':0,'unit':'N',
                            'points':[[0,0],[stage['duration'],1.]]})
    model['load_transfer_profile']='TR-F'
    model['conservative_load_binding']={'source':deepcopy(field['source']),
        'receipt_sha256':field['receipt_sha256'],'captured_model_sha256':canonical_hash(original),
        'original_loads':deepcopy(original['loads']),'original_conditions':deepcopy(original['conditions']),
        'original_analysis_steps':deepcopy(original.get('analysis_steps')),
        'binding_policy':'additive_force_contribution_zero_to_mapped_over_single_static_stage',
        'imported_condition_id':identifier,'editable_model_conditions':'original_unchanged'}
    validate_contributions(model);validate_model(model);render(model)
    return model


def receiver_equilibrium(model, reactions, *, static):
    """All effective authored loads and all active SPC reactions at one state."""
    nodes,_,_=validate_model(model);stage=_static_stage(model)
    local=static['load_parameter']-stage['start']
    _need(static['step']==stage['index'] and 0<=local<=stage['duration'],
          'Receiver equilibrium frame lies outside its STATIC stage')
    ids=sorted(nodes);X=np.asarray([nodes[n] for n in ids]);F=np.zeros((len(ids),3));R=F.copy()
    lookup={n:i for i,n in enumerate(ids)}
    for (n,d),points in stage['loads'].items():F[lookup[n],d-1]=_at(points,local)
    for n,d in stage['boundary']:
        _need(n in reactions and len(reactions[n])==3,'Missing active receiver SPC reaction')
        R[lookup[n],d-1]=reactions[n][d-1]
    _need(np.isfinite(R).all(),'Receiver SPC reaction is nonfinite')
    ff,fm=resultants(X,F,np.zeros(3));rf,rm=resultants(X,R,np.zeros(3))
    scale=max(1.,float(np.sum(np.linalg.norm(F,axis=1))));length=max(1.,float(np.ptp(X,axis=0).max()))
    return {'force_error':float(np.max(np.abs(rf+ff))/scale),
        'moment_error':float(np.max(np.abs(rm+fm))/(scale*length)),'limit':EQUILIBRIUM_TOLERANCE,
        'applied_force_N':ff.tolist(),'support_force_N':rf.tolist(),'applied_moment_origin_Nmm':fm.tolist(),
        'support_moment_origin_Nmm':rm.tolist(),'moment_origin_mm':[0.,0.,0.],
        'scope':'all_effective_receiver_loads_and_active_SPCs','static':deepcopy(static)}


def _exterior_nodes(elements):
    owners={}
    for row in elements.values():
        for slots in FACES.values():
            ids=tuple(row[s] for s in slots)
            owners.setdefault(tuple(sorted(ids[:3])),[]).append(ids)
    return {n for faces in owners.values() if len(faces)==1 for n in faces[0]}


def read_source(attempt, selected_nodes, *, static=None, with_catalog=False):
    """Read original FORC through the existing strict FRD/STA admission."""
    root=Path(attempt).resolve(strict=True)
    raw=_read(root/'contact_execution.json',8*1024**2);result=json.loads(raw)
    _need(result.get('execution_status')=='SUCCEEDED' and result.get('native_version')=='2.22',
          'Select a successful retained CalculiX 2.22 source calculation')
    manifest,model,pins,nodes,elements=_profile(root/'frozen_input/snapshot.json')
    inventory={r['relative']:r for r in result['artifacts']}
    _need(len(inventory)==len(result['artifacts']),'Duplicate retained native artifact identity')
    required=['solver/contact.inp','solver/contact.frd','solver/contact.sta','solver/ccx_contact.execution.json']
    for name in required:
        pin=inventory.get(name)
        _need(pin and len(_read(root/name))==pin['bytes'] and _sha(root/name)==pin['sha256'],
              'Original solver source is absent or changed: '+name)
    _need(_read(root/'solver/contact.inp')==_read(root/'frozen_input/contact.inp'),
          'Executed deck differs from its retained frozen input')
    execution=json.loads(_read(root/'solver/ccx_contact.execution.json',1024**2))
    _need(execution.get('status')=='COMPLETED' and execution.get('return_code')==0,
          'The retained native solver process did not complete successfully')
    _need(isinstance(selected_nodes,list) and selected_nodes and
          len(set(selected_nodes))==len(selected_nodes) and
          all(type(n)is int and n in nodes for n in selected_nodes),'Select exact native support nodes')
    _need(set(selected_nodes)<=_exterior_nodes(elements),'Select source support nodes on the actual exterior boundary')
    # _profile has no DLOAD/body cards anywhere, hence in particular none on
    # every incident element of the selected SPC nodes.
    materials={'names':['M1'],'elements':{e:'M1' for e in elements}}
    observed=read_frd(root/'solver/contact.frd',nodes,elements,
                      contact_materials=materials,contact_profile=profile(model),require_contact=False)
    _need(observed['native_version']=='2.22','The original FRD is not CalculiX 2.22')
    require_converged(observed['frames'],read_status(root/'solver/contact.sta',model))
    frames=observed['frames']
    matches=[frame for frame in frames if frame['static']==static] if static is not None else [frames[-1]]
    _need(len(matches)==1,'Select one exact retained static frame')
    final=matches[0]
    _need('FORC' in final['fields'],'The selected retained frame has no native FORC field')
    deck=_read(root/'solver/contact.inp').decode('ascii')
    card=None;cload_nodes=set();global_rf=False;node_global=False
    for line in deck.splitlines():
        text=line.strip().upper()
        if not text or text.startswith('**'):continue
        if text.startswith('*'):
            card=text.split(',')[0]
            node_global=card=='*NODE FILE' and 'GLOBAL=YES' in text.replace(' ','')
        elif card=='*CLOAD':cload_nodes.add(int(text.split(',')[0]))
        elif card=='*NODE FILE' and 'RF' in [v.strip() for v in text.split(',')]:
            _need(node_global,'Source RF requires explicit *NODE FILE,GLOBAL=YES')
            global_rf=True
    _need(global_rf,'Source RF requires explicit *NODE FILE,GLOBAL=YES')
    _need(not cload_nodes.intersection(selected_nodes),
          'A selected support node also carries CLOAD; RF is not an isolated support reaction')
    stage=_static_stage(model);local=final['static']['load_parameter']-stage['start']
    fixed=stage['boundary'];loads=stage['loads']
    _need(all((n,d) in fixed and _at(fixed[n,d],local)==0 for n in selected_nodes for d in (1,2,3)),
          'Every selected source node must have active zero XYZ SPCs at the selected frame')
    _need(not any(n in selected_nodes for n,d in loads),
          'A selected support node also carries CLOAD; RF is not an isolated support reaction')
    _need(all(n in final['fields']['FORC'] for n in selected_nodes),'Native FORC has missing selected support rows')
    _need(_read(root/'contact_execution.json',8*1024**2)==raw,'Source result changed while reading')
    for name in required:
        _need(_sha(root/name)==inventory[name]['sha256'],'Original solver source changed while reading: '+name)
    for name,pin in pins.items():
        _need(_sha(root/'frozen_input'/name)==pin['sha256'],'Original frozen source changed while reading: '+name)
    source={'result_sha256':canonical_hash(result),'snapshot_sha256':pins['snapshot.json']['sha256'],
            'frd_sha256':_sha(root/'solver/contact.frd'),'deck_sha256':_sha(root/'solver/contact.inp'),
            'selected_node_ids':list(selected_nodes),'producer_profile':'CCX2.22_C3D10_linear_SPC_only',
            'raw_field':'FORC','raw_sign':'support_on_source','DLOAD_scope':'none_in_admitted_deck',
            'selected_static':deepcopy(final['static'])}
    field=reaction_field(selected_nodes,[nodes[n] for n in selected_nodes],
                          [final['fields']['FORC'][n] for n in selected_nodes],source=source,static=final['static'])
    if with_catalog:
        return field,[deepcopy(frame['static']) for frame in frames if 'FORC' in frame['fields']]
    return field


def prepare_source(attempt, output):
    """Explicit import preparation; no solver, new owner or automatic repair."""
    source=Path(attempt).resolve(strict=True);target=Path(output).absolute()
    _need(not target.exists() and not target.is_relative_to(source),'Choose a new source import folder')
    result=json.loads(_read(source/'contact_execution.json',8*1024**2))
    _profile(source/'frozen_input/snapshot.json')
    target.mkdir(parents=True)
    members=['contact_execution.json','solver/contact.inp','solver/contact.frd','solver/contact.sta','solver/ccx_contact.execution.json']
    members += ['frozen_input/'+n for n in _profile(source/'frozen_input/snapshot.json')[2]]
    pins=[]
    for name in sorted(set(members)):
        data=_read(source/name);p=target/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        _need(_sha(source/name)==_sha(p),'Source changed while preparing retained import')
        pins.append({'relative':name,'bytes':len(data),'sha256':_sha(p)})
    save_json(target/'support-source.json',{'kind':'conservative-support-source','schema_version':'1',
        'files':pins,'original_result_sha256':canonical_hash(result)})
    return target/'support-source.json'


def validate_source(path):
    path=Path(path);_need(path.is_absolute() and path.name=='support-source.json','Select a registered support source')
    doc=json.loads(_read(path,8*1024**2));_need(doc.get('kind')=='conservative-support-source' and doc.get('schema_version')=='1',
                                            'Unsupported retained support input')
    seen=set()
    for pin in doc['files']:
        name=_relative(pin['relative']);_need(name not in seen,'Duplicate retained source file');seen.add(name)
        _need(len(_read(path.parent/name))==pin['bytes'] and _sha(path.parent/name)==pin['sha256'],
              'Retained support source changed: '+name)
    _need({'contact_execution.json','solver/contact.inp','solver/contact.frd','solver/contact.sta',
           'frozen_input/snapshot.json'} <= seen,'Missing required original support files')
    _need(canonical_hash(json.loads(_read(path.parent/'contact_execution.json')))==doc['original_result_sha256'],
          'The imported original result changed')
    _,_,pins,*_=_profile(path.parent/'frozen_input/snapshot.json')
    expected={'contact_execution.json','solver/contact.inp','solver/contact.frd','solver/contact.sta','solver/ccx_contact.execution.json'} | {
        'frozen_input/'+name for name in pins}
    _need(seen==expected,'Retained source contains missing or unrelated files')
    return doc


def selection_catalog(path, *, static=None):
    """Pure current-input catalog after the existing registered-file verification.

    Returned in native_input, never duplicated in the receipt's 64 KiB metadata.
    Existing bounded snapshot/FRD readers own input limits and no native runs.
    """
    path=Path(path)
    if path.name=='support-source.json':
        validate_source(path);manifest,model,pins,nodes,elements=_profile(path.parent/'frozen_input/snapshot.json')
        stage=_static_stage(model);fixed=stage['boundary'];loaded={n for n,d in stage['loads']}
        local=stage['duration'] if static is None else static['load_parameter']-stage['start']
        ids=sorted(n for n in _exterior_nodes(elements) if n not in loaded and
                   all((n,d) in fixed and _at(fixed[n,d],local)==0 for d in (1,2,3)))
        field,frames=read_source(path.parent,ids,static=static,with_catalog=True)
        return {'status':'AVAILABLE','role':'source','title':'보존한 지지 반력',
            'force_unit':'N','coordinate_unit':'mm','frame':'global_cartesian',
            'nodes':[{'node_id':n,'coordinates_mm':list(nodes[n]),'R_source_N':f}
                     for n,f in zip(ids,field['value'])],
            'source':field['source'],'static':field['static'],'frames':frames,
            'axis':{'name':'load_parameter','unit':'1','semantics':'STATIC_LOAD_PARAMETER'}}
    # A general contact input remains usable when TR-F is not its profile.
    validate_snapshot(path)
    try:manifest,model,pins,nodes,elements=_profile(path)
    except ValueError as error:return {'status':'UNSUPPORTED','reason':str(error),'role':'receiver'}
    owners={}
    for e,row in elements.items():
        for f,slots in FACES.items():owners.setdefault(tuple(sorted(row[s] for s in slots[:3])),[]).append((e,f))
    faces=[];used=set()
    for pairs in owners.values():
        if len(pairs)!=1:continue
        e,f=pairs[0];ids=[elements[e][s] for s in FACES[f]];used.update(ids)
        faces.append({'element_id':e,'face':f,'node_ids':ids,
                      'centroid_mm':np.mean(np.asarray([nodes[n] for n in ids[:3]]),axis=0).tolist()})
    return {'status':'AVAILABLE','role':'receiver','title':'수신 고체 경계',
        'coordinate_unit':'mm','frame':'global_cartesian',
        'nodes':[{'node_id':n,'coordinates_mm':list(nodes[n])} for n in sorted(used)],'faces':faces,
        'fixed_dofs':deepcopy(model['boundary_dofs']),'snapshot_sha256':pins['snapshot.json']['sha256']}


def registration_members(path,approved_root):
    from ..native_inputs import _within_root
    doc=validate_source(path)
    paths=[Path(path)]+[_within_root(Path(path).parent/p['relative'],Path(approved_root)) for p in doc['files']]
    return paths,_sha(path)


class SupportReactionAdapter:
    backend=SOURCE;version='1'
    def default_settings(self):return {'data_id':'','support_node_ids':[]}
    def validate_settings(self,settings):
        _need(isinstance(settings,dict) and set(settings) in ({'data_id','support_node_ids'},
              {'data_id','support_node_ids','static'}),'Select a retained source and SPC nodes')
        check_id(settings['data_id'])
        ids=settings['support_node_ids'];_need(isinstance(ids,list) and ids and len(set(ids))==len(ids) and
                                            all(type(n)is int and n>0 for n in ids),'Select source support nodes')
        if 'static' in settings:
            from ..conservative_load_transfer import validate_static
            validate_static(settings['static'])
        return deepcopy(settings)
    def describe_ports(self,settings):
        self.validate_settings(settings)
        return {'inputs':{},'outputs':{'support_reaction':{'kind':'field','unit':'N','quantity':'support_reaction',
            'association':'POINTS','component':'VECTOR','location':'node','measure':'support_reaction_on_source',
            'frame':'global_cartesian','coordinate_units':'mm','coordinate_frame':'global_cartesian'}}}
    def run(self,settings,*,output,runtime=None):
        _need(not runtime and set(settings) in ({'data_id','support_node_ids','snapshot_path'},
              {'data_id','support_node_ids','snapshot_path','static'}),'Use a registered retained source')
        self.validate_settings({k:v for k,v in settings.items() if k!='snapshot_path'})
        path=Path(settings['snapshot_path']);validate_source(path)
        output=Path(output);output.mkdir(parents=True,exist_ok=True)
        _need(not any(output.iterdir()),'Use a new empty source attempt')
        retained=output/'source';retained.mkdir()
        doc=validate_source(path)
        for name in ['support-source.json']+[p['relative'] for p in doc['files']]:
            target=retained/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(_read(path.parent/name))
        validate_source(retained/'support-source.json')
        field=read_source(retained,settings['support_node_ids'],static=settings.get('static'))
        save_json(output/'support_reaction.json',field)
        result={'execution_status':'SUCCEEDED','responses':{'support_reaction':field},
            'solver_executed':False,'qualification':'UNKNOWN','engineering_valid':False,
            'source_input_sha256':_sha(path),'artifacts':[]}
        result['artifacts']=[{'relative':p.relative_to(output).as_posix(),'bytes':p.stat().st_size,'sha256':_sha(p)}
                             for p in sorted(output.rglob('*')) if p.is_file()]
        save_json(output/'support_execution.json',result);return result


class ConservativeLoadAdapter:
    backend=RECEIVER;version='1'
    def default_settings(self):return {'data_id':'','target_faces':[]}
    def validate_settings(self,settings):
        _need(isinstance(settings,dict) and set(settings) in ({'data_id','target_faces'}, {'data_id','target_faces','nodal_load'}),
              'Select the receiver frozen input and TRI6 boundary')
        check_id(settings['data_id'])
        _need(isinstance(settings['target_faces'],list) and settings['target_faces'],'Select target boundary faces')
        return deepcopy(settings)
    def describe_ports(self,settings):
        self.validate_settings(settings)
        return {'inputs':{'nodal_load':{'kind':'field','unit':'N','quantity':'applied_nodal_force',
            'association':'POINTS','component':'VECTOR','location':'node','measure':'applied_nodal_force',
            'frame':'global_cartesian','coordinate_units':'mm','coordinate_frame':'global_cartesian',
            'required':True,'mappings':['tri6_conservative_load']}},'outputs':{}}
    def bind_port(self,settings,name,value):
        self.validate_settings(settings);_need(name=='nodal_load','Unknown conservative load port')
        result=deepcopy(settings);result[name]=deepcopy(value);return result
    def target_boundary(self,settings):
        _,model,*_=_profile(settings['snapshot_path'])
        return boundary(model,settings['target_faces'])
    def run(self,settings,*,output,runtime=None):
        _need(not runtime and set(settings)=={'data_id','snapshot_path','target_faces','nodal_load'},
              'Connect an admitted conservative load before receiver execution')
        original=Path(settings['snapshot_path']);manifest,model,pins,nodes,elements=_profile(original)
        field=settings['nodal_load']
        model=bind_receiver_model(model,field,settings['target_faces'])
        model['conservative_load_binding']['original_snapshot_sha256']=pins['snapshot.json']['sha256']
        output=Path(output);output.mkdir(parents=True,exist_ok=True)
        _need(not any(output.iterdir()),'Use a new empty receiver attempt')
        retained=output/'original_input';retained.mkdir()
        for name,pin in pins.items():
            data=_read(original.parent/name);_need(len(data)==pin['bytes'] and _sha(original.parent/name)==pin['sha256'],'Receiver input changed')
            target=retained/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        derived=output/'load_input';shutil.copytree(retained,derived)
        # The editable native model is retained unchanged. This new port-bound
        # deck has explicit lineage and is not claimed as an edited FreeCAD model.
        save_json(derived/'mesh.json',model);(derived/'contact.inp').write_text(render(model),encoding='ascii',newline='\n')
        manifest['id']='F'+uuid.uuid4().hex
        manifest['derived_load']=deepcopy(model['conservative_load_binding'])
        for pin in manifest['files']:
            p=derived/pin['relative'];pin.update(bytes=p.stat().st_size,sha256=_sha(p))
        save_json(derived/'snapshot.json',manifest);_profile(derived/'snapshot.json')
        result=ContactFemCalculixAdapter().run({'snapshot_path':str((derived/'snapshot.json').absolute())},output=output/'calculation')
        if result['execution_status']=='SUCCEEDED':
            observed=read_frd(output/'calculation/solver/contact.frd',nodes,elements,
                contact_materials={'names':['M1'],'elements':{e:'M1' for e in elements}},
                contact_profile=profile(model),require_contact=False)
            require_converged(observed['frames'],read_status(output/'calculation/solver/contact.sta',model))
            final=observed['frames'][-1]
            _need('FORC' in final['fields'],'Receiver equilibrium requires native FORC output')
            balance=receiver_equilibrium(model,final['fields']['FORC'],static=final['static'])
            result['receiver_equilibrium']=balance
            force_error,moment_error=balance['force_error'],balance['moment_error']
            if max(force_error,moment_error)>EQUILIBRIUM_TOLERANCE:
                result.update(execution_status='FAILED',diagnostics={'reason':'Receiver force/moment equilibrium failed'})
        # Prefix the existing artifact paths; keep all original raw files.
        for key in ('post_artifact',):
            if key in result:result[key]['relative']='calculation/'+result[key]['relative']
        result.update(backend=RECEIVER,load_binding=deepcopy(model['conservative_load_binding']))
        result['artifacts']=[{'relative':p.relative_to(output).as_posix(),'bytes':p.stat().st_size,'sha256':_sha(p)}
            for p in sorted(output.rglob('*')) if p.is_file()]
        save_json(output/'load_execution.json',result);return result
