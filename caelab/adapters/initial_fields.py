"""Two typed initial-state consumers over the existing CCX/Aster executors."""
from copy import deepcopy
from pathlib import Path
import json,shutil,math
from .contact_fem import ContactFemCalculixAdapter,validate_snapshot
from . import codeaster_frozen as aster
from . import codeaster_frozen_worker as old_worker
from . import initial_field_aster_worker as state_worker
from ..initial_field_conditions import BACKENDS,effective
from ..storage import check_id,save_json


class InitialFieldsCalculixAdapter(ContactFemCalculixAdapter):
    backend,version=BACKENDS['calculix'],'1'
    input_source_files=[__file__,Path(__file__).with_name('initial_field_deck.py'),
        Path(__file__).with_name('initial_field_results.py'),Path(__file__).parents[1]/'initial_field_conditions.py']
    @staticmethod
    def default_settings():return {'data_id':''}
    @staticmethod
    def validate_settings(settings):
        if not isinstance(settings,dict) or set(settings)!={'data_id'}:raise ValueError('등록한 초기장 입력을 선택하세요.')
        check_id(settings['data_id']);return deepcopy(settings)
    def describe_model(self,settings):return {'backend':self.backend,'model':{'settings':self.validate_settings(settings)}}
    def describe_ports(self,settings):
        self.validate_settings(settings)
        return {'inputs':{},'outputs':{},'clock':'static_load_parameter','coordinate_frame':'FREECAD_DOCUMENT_GLOBAL','qualification':'UNKNOWN'}
    def run(self,settings,*,output,runtime=None):
        if not isinstance(settings,dict) or set(settings)!={'data_id','snapshot_path'}:raise ValueError('등록 초기장 입력은 실행 내부에서 한 번 해소하세요.')
        self.validate_settings({'data_id':settings['data_id']})
        _,model,_,_=validate_snapshot(settings['snapshot_path']);definition=effective(model)
        if definition is None or definition['solver']!='calculix':raise ValueError('현재 입력은 CalculiX 초기장 해석이 아닙니다.')
        return super().run(settings,output=output,runtime=runtime)


def prepare_aster(source,output):
    manifest,model,pins,gates=validate_snapshot(source);definition=effective(model)
    if definition is None or definition['kind']!='compatible' or definition['solver']!='codeaster':raise ValueError('실제 호환 초기 변위·응력 입력을 선택하세요.')
    retained=output/'frozen_input';retained.mkdir()
    for relative,pin in pins.items():
        target=retained/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source.parent/relative,target)
    aster._source_check(source,retained,pins);validate_snapshot(retained/'snapshot.json')
    solver=output/'solver';solver.mkdir()
    mesh={'nodes':deepcopy(model['nodes']),'elements':deepcopy(model['elements']),
        'fixed_dofs':deepcopy(model['boundary_dofs']),'loads':deepcopy(model['loads']),
        'initial_field_definition':deepcopy(definition)}
    text,labels,elements=old_worker.mesh_text(mesh);(solver/'mesh.mail').write_text(text,encoding='ascii',newline='\n');save_json(solver/'mesh.json',mesh)
    workers=[Path(state_worker.__file__),Path(old_worker.__file__),aster.HELPER,aster.GEOMETRY]
    for path in workers:(output/path.name).write_bytes(path.read_bytes())
    sources={p.name:aster._sha(p) for p in workers}
    save_json(solver/'input.json',{'material':model['materials'][0],'node_labels':labels,'element_labels':elements,
        'initial_field_definition':definition,'mail_sha256':aster._sha(solver/'mesh.mail'),
        'mesh_record_sha256':aster._sha(solver/'mesh.json'),'worker_sources':sources})
    (solver/'model.comm').write_text("import sys\nsys.path.insert(0,'/work')\nfrom initial_field_aster_worker import solve\nsolve('/work/solver/input.json')\n",encoding='ascii')
    budgets=aster.process_budgets()
    (solver/'model.export').write_text(f"P actions make_etude\nP memory_limit {budgets['solver_memory_mb']}\nP time_limit {budgets['solver_time_seconds']}\nP mpi_nbcpu 1\nP ncpus 1\nF comm /work/solver/model.comm D 1\nF mail /work/solver/mesh.mail D 20\nF rmed /work/solver/results.med R 80\nF mess /work/solver/aster.mess R 6\nF resu /work/solver/aster.resu R 8\n",encoding='ascii')
    return manifest,mesh,pins,gates,sources,budgets


def validate_provided_aster(raw,mesh):
    """Check the real CHAM_GD tables independently of accepted result orders."""
    from .codeaster_worker import _table,_table_identifier,_finite,VECTOR_COMPONENTS,STRESS_COMPONENTS
    initial=mesh['initial_field_definition']['compatible'];guard=raw['native_mesh_checks']
    nodes=guard['node_ids_in_native_order'];elements=guard['element_ids_in_native_order']
    expected={r['node_id']:r['value'] for r in initial['displacements_mm']}
    table,count=_table(raw['native_initial_tables'].get('DEPL'),('NOEUD',*VECTOR_COMPONENTS),'provided DEPL')
    seen=set()
    for row in range(count):
        i=_table_identifier(table['NOEUD'][row],'NOEUD')-1
        if i not in range(len(nodes)) or nodes[i] in seen:raise ValueError('제공 초기 변위의 원 절점이 중복되거나 다릅니다.')
        n=nodes[i];seen.add(n)
        if any(not math.isclose(_finite(table[k][row],'provided DEPL'),v,rel_tol=1e-12,abs_tol=1e-12) for k,v in zip(VECTOR_COMPONENTS,expected[n])):
            raise ValueError('실제로 생성한 초기 변위가 명시 입력과 다릅니다.')
    if seen!=set(expected):raise ValueError('제공 초기 변위의 실제 원 절점이 빠졌습니다.')
    table,count=_table(raw['native_initial_tables'].get('SIGM'),('MAILLE','POINT','SOUS_POINT',*STRESS_COMPONENTS),'provided SIGM')
    seen=set()
    for row in range(count):
        i=_table_identifier(table['MAILLE'][row],'MAILLE')-1;p=table['POINT'][row];s=table['SOUS_POINT'][row]
        if i not in range(len(elements)) or type(p)is not int or p not in range(1,6) or s!=1 or (i,p) in seen:
            raise ValueError('제공 초기 응력의 원 요소·적분점이 중복되거나 다릅니다.')
        seen.add((i,p))
        if any(not math.isclose(_finite(table[k][row],'provided SIGM'),v,rel_tol=1e-12,abs_tol=1e-12) for k,v in zip(STRESS_COMPONENTS,initial['stress_MPa'])):
            raise ValueError('실제로 생성한 초기 응력이 명시 입력과 다릅니다.')
    if seen!={(i,p) for i in range(len(elements)) for p in range(1,6)}:raise ValueError('제공 초기 응력의 실제 원 적분점이 빠졌습니다.')


def parse_aster(raw,mesh):
    if not isinstance(raw.get('states'),list) or not raw['states']:raise ValueError('원 Aster 초기장 상태 출력이 없습니다.')
    if raw['provided_initial']!=mesh['initial_field_definition']['compatible']:raise ValueError('원 초기 상태와 native 생성 입력이 다릅니다.')
    states=[old_worker.parse_result(row,mesh,allow_initial_order=True) for row in raw['states']]
    validate_provided_aster(raw,mesh)
    times=[r['static']['load_parameter'] for r in states]
    if any(b<=a for a,b in zip(times,times[1:])):raise ValueError('원 Aster 상태 시각이 중복되거나 역순입니다.')
    final=deepcopy(states[-1]);final['initial_fields_states']=states;final['provided_initial']=deepcopy(raw['provided_initial'])
    final['initial_snapshot_status']=raw['native_initial_snapshot_status'];final['native_initial_tables']=raw['native_initial_tables']
    return final


def write_aster_post(output,manifest,mesh,pins,observed):
    save_json(output/'initial_fields.json',{'provided_initial':observed['provided_initial'],
        'provided_initial_status':observed['initial_snapshot_status'],'native_initial_tables':observed['native_initial_tables'],'native_states':observed['initial_fields_states'],
        'static_axis':'load parameter, not seconds','engineering_release':'UNKNOWN'})
    return aster.write_post(output,manifest,mesh,pins,observed)


class InitialFieldsCodeAsterAdapter(aster.FrozenFemCodeAsterAdapter):
    backend,version=BACKENDS['codeaster'],'1'
    prepare_input=staticmethod(prepare_aster);parse_result=staticmethod(parse_aster);write_post=staticmethod(write_aster_post)
    default_settings=staticmethod(InitialFieldsCalculixAdapter.default_settings)
    validate_settings=staticmethod(InitialFieldsCalculixAdapter.validate_settings)
    describe_model=InitialFieldsCalculixAdapter.describe_model;describe_ports=InitialFieldsCalculixAdapter.describe_ports
    input_source_files=[__file__,Path(state_worker.__file__),Path(old_worker.__file__)]
    limitations=['Configured existing Code_Aster17.4 runtime required; no installation or WSL setup',
        'Single elastic TETRA10 compatible affine total strain/displacement/stress only; no plastic/eigenstrain reconstruction',
        'Actual first equilibrium is distinct from supplied initial state; engineering release UNKNOWN']
    def run(self,settings,*,output,runtime=None):
        if not isinstance(settings,dict) or set(settings)!={'data_id','snapshot_path'}:raise ValueError('등록 초기장 입력은 실행 내부에서 해소하세요.')
        self.validate_settings({'data_id':settings['data_id']})
        result=super().run(settings,output=output,runtime=runtime)
        if result['execution_status']=='SUCCEEDED':
            record=json.loads((Path(output)/'initial_fields.json').read_text(encoding='utf-8'))
            states=record['native_states'];definition=json.loads((Path(output)/'solver/input.json').read_text(encoding='utf-8'))['initial_field_definition']
            times=[s['static']['load_parameter'] for s in states]
            if any(t not in times for t in [s['parameter'] for s in definition['states']]):
                result.update(execution_status='FAILED',diagnostics={'reason':'요청한 첫 평형·후속 상태의 실제 출력이 빠졌습니다.'})
            else:
                result['initial_field_outputs']={'raw_rows':'initial_fields.json','status':'actual_native_orders',
                    'provided_initial_is_equilibrated':False}
                result['responses']={}
                for prefix,request in zip(('first_equilibrium','subsequent'),definition['states']):
                    state=next(s for s in states if s['static']['load_parameter']==request['parameter']);ids=sorted(map(int,state['displacements']))
                    for key,field,unit in (('displacement','displacements','mm'),('reaction','reactions','N')):
                        result['responses'][prefix+'_'+key]={'kind':'field','unit':unit,'value':[state[field][str(n)] for n in ids],
                            'component':'VECTOR','location':'native_TETRA10_nodes','reduction':'none','metadata':{'node_ids':ids,
                                'frame':'FREECAD_DOCUMENT_GLOBAL','static':state['static'],'raw_rows':'initial_fields.json'}}
                    points=state['stress_points']
                    for axis,name in enumerate(('XX','YY','ZZ','XY','XZ','YZ')):
                        result['responses'][prefix+'_IP_stress_'+name]={'kind':'field','unit':'MPa','value':[p['stress_MPa'][axis] for p in points],
                            'component':name,'location':'native_TETRA10_FPG5','reduction':'none','metadata':{'element_ids':[p['element_id'] for p in points],
                                'point_ids':[p['point'] for p in points],'frame':'FREECAD_DOCUMENT_GLOBAL','static':state['static'],
                                'measure':'small_strain_Cauchy_stress','raw_rows':'initial_fields.json'}}
            save_json(Path(output)/'frozen_execution.json',result)
        return result
