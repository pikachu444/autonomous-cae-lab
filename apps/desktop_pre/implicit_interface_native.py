"""Author user joint definitions on the existing native FEM owner and CAS store."""
from copy import deepcopy
import json

from caelab.storage import canonical_hash
from caelab.implicit_interface import BACKEND,build_joints,parameters
from caelab.adapters.contact_aster_model import surface_union

NAMESPACE = 'implicit_interfaces'
OPERATIONS = tuple('pre.interface.'+name for name in ('read','region','save_draft','apply','discard'))
READ_ONLY = OPERATIONS[:2]


def _canonical(value):
    return json.loads(json.dumps(value,ensure_ascii=False,allow_nan=False))


def _records(fem):
    value = fem._metadata().get(NAMESPACE,{})
    if not isinstance(value,dict):
        raise ValueError('저장한 계면 정의의 형식을 확인하세요.')
    return value


def record(fem,analysis_id):
    value = deepcopy(_records(fem).get(analysis_id))
    if value is not None and not isinstance(value,dict):
        raise ValueError('저장한 계면 초안의 형식을 확인하세요.')
    return value


def _binding_hash(value):
    # The existing binding validates the original BRep and complete mesh. Its
    # optional reload-equivalence receipt is diagnostic, not a new identity.
    return canonical_hash({k:v for k,v in value.items() if k != 'source_equivalence'})


def region(fem,analysis,region_id):
    saved,body,names = fem._region(region_id)
    if not names or any(not n.startswith('Face') for n in names):
        raise ValueError('계면으로 사용할 원 고체의 면 영역을 선택하세요.')
    meshes = [obj for obj in analysis.Group if hasattr(obj,'FemMesh')
              and getattr(obj,'Shape',None) is body and not getattr(obj,'Suppressed',False)]
    if len(meshes) != 1:
        raise ValueError('선택한 고체의 활성 메시 하나가 필요합니다.')
    mesh = meshes[0]
    binding = fem.owner.mesh_bindings.validate(mesh)
    from femmesh import meshtools
    nodes = sorted(map(int,meshtools.get_femnodes_by_references(mesh.FemMesh,[(body,tuple(names))])))
    if not nodes:
        raise ValueError('선택한 원 면에 연결된 메시 절점이 없습니다.')
    return _canonical(dict(region_id=region_id,label=saved['label'],body_id=body.Name,
        body_label=body.Label,mesh_id=mesh.Name,target=saved['target'],
        mesh_binding_sha256=_binding_hash(binding),native_node_ids=nodes))


def _resolve(fem,analysis,side,bodies,mappings):
    required = ('region_id','body_id','mesh_id','target','mesh_binding_sha256','native_node_ids')
    if not isinstance(side,dict) or not set(required) <= set(side) or set(side)-set(required)-{'label','body_label'}:
        raise ValueError('원 면 영역을 다시 선택해 현재 형상·메시 대응을 확인하세요.')
    current = region(fem,analysis,side['region_id'])
    if any(side[key] != current[key] for key in required):
        raise ValueError('선택한 면 영역이나 원 메시가 바뀌었습니다. 원 영역을 다시 선택하고 명시 적용하세요.')
    body = bodies.get(current['body_id'])
    if body is None or body['mesh'].Name != current['mesh_id']:
        raise ValueError('선택한 면 영역이 현재 두 고체의 메시와 다릅니다.')
    from femmesh import meshtools
    faces = []
    for face in current['target']['subelements']:
        _,entries,is_sub = meshtools.get_ccx_elements(body['getter'],(body['object'],face['name']))
        if not is_sub:
            raise ValueError('선택한 원 면을 HEXA8 요소의 면으로 확인하지 못했습니다.')
        faces.append(dict(face=face['name'],element_faces=[(int(e),int(f)) for e,f in entries]))
    resolved = surface_union(current['body_id'],faces,mappings)
    resolved['source_region'] = {key:current[key] for key in required}
    return resolved


def _definitions(fem,analysis,draft,bodies,model):
    if not isinstance(draft,dict) or set(draft) != {'interfaces'} or not isinstance(draft['interfaces'],list):
        raise ValueError('계면 목록과 선택한 원 영역·명시한 절점 대응·재료 계수를 확인하세요.')
    mappings = {body:{kind:{int(k):v for k,v in tables[kind].items()} for kind in ('nodes','elements')}
                for body,tables in model['body_maps'].items()}
    definitions = []
    for raw in draft['interfaces']:
        if not isinstance(raw,dict) or set(raw) != {'object_id','label','a','b','node_pairs','material'}:
            raise ValueError('각 계면의 이름, 두 원 영역, 명시한 절점 대응과 계수가 필요합니다.')
        definition = {key:deepcopy(raw[key]) for key in ('object_id','label','node_pairs')}
        definition['material'] = parameters(raw['material'])
        for side in ('a','b'):
            definition[side] = _resolve(fem,analysis,raw[side],bodies,mappings)
        definitions.append(definition)
    if definitions:
        build_joints(model,definitions)
    return _canonical(definitions)


def _identity(rows,definitions):
    return _canonical(dict(bodies=[dict(body_id=r['body_id'],mesh_id=r['mesh_id'],
        mesh_binding_sha256=_binding_hash(r['binding'])) for r in sorted(rows,key=lambda r:r['body_id'])],
        regions=[definition[side]['source_region'] for definition in definitions for side in ('a','b')]))


def base(fem,analysis):
    from .fem_edit import _native_type
    solvers = [obj for obj in analysis.Group if _native_type(obj) == 'Fem::SolverCcxTools'
               and not getattr(obj,'Suppressed',False)]
    if len(solvers) != 1:
        raise ValueError('현재 해석의 기존 3D 솔버 설정 하나를 선택하세요.')
    from .freeze_contact import collect
    return collect(analysis,solvers[0],fem,capture_only=True,_implicit_interface=True)


def read(fem,analysis):
    saved = record(fem,analysis.Name)
    errors = []
    if saved:
        try:
            draft = saved['draft']
            if not isinstance(draft,dict) or set(draft) != {'interfaces'} or not isinstance(draft['interfaces'],list):
                raise ValueError('계면 목록의 형식을 확인하세요. 원문 초안은 보관돼 있습니다.')
            for definition in draft['interfaces']:
                parameters(definition['material'])
        except (KeyError,TypeError,ValueError) as error:
            errors.append(str(error))
    bodies = {obj.Shape.Name for obj in analysis.Group if hasattr(obj,'FemMesh') and getattr(obj,'Shape',None) is not None}
    return dict(record=saved,errors=errors,default_draft={'interfaces':[]},
        meshes=[dict(id=obj.Name,label=obj.Label,body_id=obj.Shape.Name) for obj in analysis.Group
                if hasattr(obj,'FemMesh') and getattr(obj,'Shape',None) is not None],
        regions=[dict(id=r['id'],label=r['label'],body_id=r['target']['object_id'])
                 for r in fem._metadata().get('regions',[]) if r.get('target',{}).get('subelements') and r['target']['object_id'] in bodies
                 and all(s['name'].startswith('Face') for s in r['target']['subelements'])],
        execution='NOT_PERFORMED',source_check='REQUIRED_BEFORE_EXECUTION')


def dispatch(fem,operation,args,target):
    fem.owner.assert_thread()
    analysis = fem._object(target)
    from .fem_edit import _native_type
    if _native_type(analysis) != 'Fem::FemAnalysis':
        raise ValueError('계면을 편집할 현재 해석을 선택하세요.')
    if operation not in OPERATIONS or not isinstance(args,dict):
        raise ValueError('지원하는 계면 편집 작업을 선택하세요.')
    if operation == 'pre.interface.read':
        if args:
            raise ValueError('계면 읽기는 현재 해석만 받습니다.')
        return read(fem,analysis)
    if operation == 'pre.interface.region':
        if set(args) != {'region_id'}:
            raise ValueError('현재 고체에서 선택한 원 면 영역을 지정하세요.')
        return region(fem,analysis,args['region_id'])
    fem._assert_idle()
    original = deepcopy(fem._metadata())
    old = record(fem,analysis.Name)
    expected = {'expected_revision','draft'} if operation == 'pre.interface.save_draft' else {'expected_revision'}
    if set(args) != expected:
        raise ValueError('현재 저장 상태와 해당 계면 초안을 확인하세요.')
    if args['expected_revision'] != (old or {}).get('revision'):
        raise ValueError('다른 곳에서 계면 정의를 바꿨습니다. 현재 편집을 보존하고 다시 읽으세요.')
    new = deepcopy(old) if old else dict(draft={'interfaces':[]},applied=None)
    if operation == 'pre.interface.save_draft':
        if not isinstance(args['draft'],dict) or len(json.dumps(args,ensure_ascii=False,allow_nan=False).encode()) > 4*1024**2:
            raise ValueError('계면 초안의 형식과 저장 크기를 확인하세요.')
        new['draft'] = _canonical(args['draft'])
    elif operation == 'pre.interface.discard':
        if not old:
            return read(fem,analysis)
        if old.get('applied'):
            new['draft'] = deepcopy(old['applied']['native_draft'])
        else:
            new = None
    else:
        if not old:
            raise ValueError('계면 초안을 먼저 보관하세요.')
        if new['draft'] == {'interfaces':[]}:
            new = None  # Explicit Apply of an empty list removes this definition.
        else:
            model,identity = base(fem,analysis)
            definition = _canonical(model['interfaces'])
            new['applied'] = dict(native_draft=deepcopy(new['draft']),definition=definition,
                                  source_identity=_identity(identity,definition))
    if new is not None:
        new['revision'] = canonical_hash({k:v for k,v in new.items() if k != 'revision'})
    def change():
        if fem._metadata() != original:
            raise ValueError('계면 정의를 저장하기 전에 원 모델이 바뀌었습니다. 현재 초안은 유지됩니다.')
        value = deepcopy(original)
        records = value.setdefault(NAMESPACE,{})
        if new is None:
            records.pop(analysis.Name,None)
        else:
            records[analysis.Name] = new
        fem.owner.write_metadata(value)
    labels = {'pre.interface.save_draft':'초안 보관','pre.interface.apply':'조건 적용','pre.interface.discard':'수정 취소'}
    fem._transaction('계면 '+labels[operation],change)
    return read(fem,analysis)


def freeze(fem,analysis,bodies,model,*,capture_only=False):
    saved = record(fem,analysis.Name)
    if saved is None:
        return
    if model.get('backend') != BACKEND:
        raise ValueError('작성한 접합 계면을 다른 솔버 입력에서 생략하지 않습니다. 지원되는 계면 해석을 선택하거나 계면 목록을 명시 해제하세요.')
    from .initial_field_native import record as initial_record,native_temperatures
    if initial_record(fem,analysis.Name) or native_temperatures(analysis):
        raise ValueError('현재 접합 계면 연결은 초기 온도·응력·상태를 생략해 실행하지 않습니다.')
    if not capture_only and (not saved.get('applied') or saved['draft'] != saved['applied']['native_draft']):
        raise ValueError('계면에 미적용 초안이 있습니다. 조건 적용 또는 수정 취소 후 진행하세요.')
    definition = _definitions(fem,analysis,saved['draft'],bodies,model)
    rows = [dict(body_id=body,mesh_id=row['mesh'].Name,binding=row['binding']) for body,row in bodies.items()]
    source_identity = _identity(rows,definition)
    if not capture_only and (definition != saved['applied']['definition']
            or source_identity != saved['applied']['source_identity']):
        raise ValueError('계면의 원 영역·형상·메시 또는 대응이 바뀌었습니다. 원 선택을 확인하고 명시 재적용하세요.')
    model['interfaces'] = definition
