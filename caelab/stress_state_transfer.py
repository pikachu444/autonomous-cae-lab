"""Exact retained CCX IP stress to a same-mesh elastic initial state.

This port never recovers IP stresses from nodal S and never resumes material
history. The existing initial-field consumer owns the native initial-state card.
"""
from copy import deepcopy
import json
import math
from pathlib import Path
import re

from .storage import canonical_hash
from .structural_field_ports import (
    _mesh, _pinned, _static, read_saved_displacement, verify_displacement_source,
)
from .initial_field_conditions import default_draft, normalize, rotation


def _identity(model):
    ids,xyz,elements=_mesh(model)
    return {
        'nodes':sorted((i,list(p)) for i,p in zip(ids,xyz)),
        'elements':sorted((e['element_id'],e['native_element_id'],
                           list(e['node_ids']),list(e['native_node_ids'])) for e in elements),
        'native_node_ids':sorted((n['node_id'],n['native_node_id']) for n in model['nodes']),
        'native_to_deck_slots':list(model['native_to_deck_slots']),
    }


def _elastic(model):
    if (model.get('analysis_scope')!='single_solid_static' or model.get('contacts')
            or model.get('restart') or model.get('dynamic') or model.get('initial_conditions')
            or model.get('pretension_sections') or model.get('periodic_constraints')
            or model.get('step',{}).get('geometry')!='linear'
            or len(model.get('materials',[]))!=1
            or any(m.get('law')!='isotropic_linear_elastic' or m.get('plasticity')
                   for m in model.get('materials',[]))):
        raise ValueError('초기 응력 전달은 접촉·소성·재시작 없는 단일 C3D10 고체의 선형 탄성 정적 해석만 지원합니다.')


def _field(displacement,proof,stress_pin,dat_pin,frame_pins):
    verified=verify_displacement_source(displacement,proof)
    mesh_path=Path(proof['files']['mesh']['path'])
    expected=mesh_path.parents[1]/'initial_fields.json'
    if Path(stress_pin['path'])!=expected:
        raise ValueError('선택한 원 계산의 보존 적분점 응력 파일이 필요합니다.')
    model=json.loads(_pinned(mesh_path,proof['files']['mesh']['sha256']))
    _elastic(model)
    payload=json.loads(_pinned(expected,stress_pin['sha256']))
    if payload.get('raw_source')!='solver/contact.dat' or not isinstance(payload.get('rows'),list):
        raise ValueError('원 CalculiX DAT 적분점 응력이 필요합니다. 절점 응력으로 대체할 수 없습니다.')
    location=_static(verified['field']['static'])
    selected=[r for r in payload['rows'] if r.get('static')==location]
    dat_path=mesh_path.parents[1]/'solver/contact.dat'
    if Path(dat_pin['path'])!=dat_path:raise ValueError('같은 원 계산의 DAT 적분점 출력을 보존해야 합니다.')
    _pinned(dat_path,dat_pin['sha256'])
    frames=[];seen_paths=set()
    for pin in frame_pins:
        path=Path(pin['path'])
        if (path.parent!=mesh_path.parents[1]/'post' or re.fullmatch(r'frame[0-9]{4,8}\.json',path.name) is None
                or str(path) in seen_paths):raise ValueError('같은 원 계산의 고유한 정적 프레임 정보가 필요합니다.')
        seen_paths.add(str(path));frame=json.loads(_pinned(path,pin['sha256']))
        if frame.get('step_location',{}).get('axis')!={'name':'load_parameter','semantics':'STATIC_LOAD_PARAMETER','unit':'1'}:
            raise ValueError('초기 응력에는 정적 하중 매개변수를 보존한 원 프레임이 필요합니다.')
        frames.append({'static':_static(frame.get('static'))})
    if len({tuple(r['static'].values()) for r in frames})!=len(frames):raise ValueError('원 정적 프레임이 중복됐습니다.')
    from .adapters.initial_field_results import read
    raw_rows=read(dat_path,model,frames,require_definition=False)
    raw_selected=[r for r in raw_rows if r['static']==location]
    if sorted(selected,key=lambda r:(r.get('element_id',0),r.get('point',0)))!=raw_selected:
        raise ValueError('보존된 적분점 응력과 원 DAT의 응력·좌표·순서·출력 정밀도가 다릅니다.')
    _pinned(dat_path,dat_pin['sha256'])
    wanted={(e['element_id'],p) for e in model['elements'] for p in range(1,5)}
    seen=set();rows=[]
    for row in selected:
        key=row.get('element_id'),row.get('point')
        if (any(type(v)is not int for v in key) or key not in wanted or key in seen
                or row.get('basis')!='native_CCX_2.22_C3D10_IP4'
                or row.get('frame')!='FREECAD_DOCUMENT_GLOBAL'
                or row.get('component_names')!=['XX','YY','ZZ','XY','XZ','YZ']):
            raise ValueError('원 요소·적분점 순서 또는 응력 좌표계·성분이 다릅니다.')
        values=row.get('stress_MPa')
        if (not isinstance(values,list) or len(values)!=6
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in values)):
            raise ValueError('원 적분점 응력의 유한한 여섯 성분이 필요합니다.')
        tokens=row.get('raw_stress_tokens')
        if not isinstance(tokens,list) or len(tokens)!=6 or not all(isinstance(v,str) for v in tokens):
            raise ValueError('원 DAT의 출력 정밀도와 응력 성분 토큰을 보존해야 합니다.')
        from .adapters.fixture_field import _number
        if [_number(t) for t in tokens]!=values:
            raise ValueError('원 DAT 출력 토큰과 응력 값이 다릅니다.')
        seen.add(key);rows.append(deepcopy(row))
    if seen!=wanted:
        raise ValueError('선택한 원 상태의 모든 C3D10 네 적분점 응력이 필요합니다.')
    return {'reference':deepcopy(verified['reference']),'label':verified['label'],
        'mesh_identity':_identity(model),'static':location,'rows':sorted(rows,key=lambda r:(r['element_id'],r['point'])),
        'stress_unit':'MPa','coordinate_frame':'FREECAD_DOCUMENT_GLOBAL',
        'stress_measure':'Cauchy_at_reference_linear_small_strain',
        'native_basis':'CCX_2.22_C3D10_IP4','engineering_release':'UNKNOWN'}


def read_saved_stress(workbench,reference,*,with_proof=False):
    """Reuse the retained run/frame resolver and pin its raw IP artifact."""
    from .evaluation import read_result
    displacement,source_proof=read_saved_displacement(workbench,reference,with_proof=True)
    mesh=Path(source_proof['files']['mesh']['path'])
    result=read_result(mesh.parents[2],verify='none',selection=[])
    files=[r for r in result.get('artifacts',[]) if r.get('path')=='calculation/initial_fields.json']
    if len(files)!=1:raise ValueError('선택한 계산에 원 적분점 응력이 보존돼 있지 않습니다. 절점 응력은 초기 상태로 사용할 수 없습니다.')
    pin={'path':str(mesh.parents[1]/'initial_fields.json'),'sha256':files[0]['sha256']}
    dat=[r for r in result.get('artifacts',[]) if r.get('path')=='calculation/solver/contact.dat']
    if len(dat)!=1:raise ValueError('같은 계산의 원 DAT 적분점 응력·좌표 파일을 보존해야 합니다.')
    dat_pin={'path':str(mesh.parents[1]/'solver/contact.dat'),'sha256':dat[0]['sha256']}
    frame_pins=[{'path':str(mesh.parents[2]/r['path']),'sha256':r['sha256']} for r in result.get('artifacts',[])
                if re.fullmatch(r'calculation/post/frame[0-9]{4,8}\.json',r.get('path',''))]
    field=_field(displacement,source_proof,pin,dat_pin,frame_pins)
    if not with_proof:return field
    return field,{'displacement':displacement,'source_proof':source_proof,
                  'stress_file':pin,'native_dat':dat_pin,'frames':frame_pins,'field_sha256':canonical_hash(field)}


def verify_stress_source(field,proof):
    if not isinstance(proof,dict) or set(proof)!={'displacement','source_proof','stress_file','native_dat','frames','field_sha256'}:
        raise ValueError('보존된 원 적분점 응력의 검증 정보가 필요합니다.')
    actual=_field(proof['displacement'],proof['source_proof'],proof['stress_file'],proof['native_dat'],proof['frames'])
    if actual!=field or canonical_hash(actual)!=proof['field_sha256']:
        raise ValueError('선택 뒤 원 적분점 응력이 바뀌었습니다.')
    return actual


def draft_for_receiver(model,field,proof,*,mesh_id,tensor_rotation):
    """Build a normal initial-field draft; do not modify the receiver or run it."""
    source=verify_stress_source(field,proof)
    _elastic(model)
    if _identity(model)!=source['mesh_identity']:
        raise ValueError('원 절점·요소·연결 순서·기준 좌표가 정확히 같은 메시가 필요합니다. 다른 메시 사상은 지원하지 않습니다.')
    rotation(tensor_rotation)
    draft=default_draft(model)
    draft.update(kind='stress',solver='calculix',label='가져온 초기 응력',mesh_id=mesh_id,
                 node_ids=[n['node_id'] for n in model['nodes']],
                 element_ids=[e['element_id'] for e in model['elements']],frame=deepcopy(tensor_rotation))
    draft['stress']={'unit':'MPa','values':[None]*6,
        'ip_rows':[{'element_id':r['element_id'],'point':r['point'],'values':deepcopy(r['stress_MPa'])} for r in source['rows']]}
    definition=normalize(model,draft)
    # The normal native editor consumes original native IDs and maps them once
    # at capture. Keep its raw input separate from the normalized deck draft.
    native_draft=deepcopy(draft)
    native_nodes={n['node_id']:n['native_node_id'] for n in model['nodes']}
    native_elements={e['element_id']:e['native_element_id'] for e in model['elements']}
    native_draft['node_ids']=[native_nodes[n] for n in draft['node_ids']]
    native_draft['element_ids']=[native_elements[e] for e in draft['element_ids']]
    for row in native_draft['stress']['ip_rows']:row['element_id']=native_elements[row['element_id']]
    provenance={'source_reference':deepcopy(source['reference']),'source_static':deepcopy(source['static']),
        'source_field_sha256':canonical_hash(source),'source_stress_file_sha256':proof['stress_file']['sha256'],
        'source_mesh_sha256':proof['source_proof']['files']['mesh']['sha256'],
        'source_native_dat_sha256':proof['native_dat']['sha256'],
        'receiver_mesh_identity_sha256':canonical_hash(_identity(model)),
        'tensor_rotation':deepcopy(tensor_rotation),'transformation':'R sigma R^T; physical tensor shear; once',
        'rotation_semantics':'user-rotated initial tensor in the unchanged common global reference mesh; not a mesh-coordinate re-expression',
        'input_measure':definition['initial_stress_measure'],
        'first_equilibrium':'native re-equilibration; no assumed stress preservation',
        'material_history':'none; not plastic, damage or finite-strain restart','engineering_release':'UNKNOWN'}
    return {'native_draft':native_draft,'draft':draft,'definition':definition,'provenance':provenance}
