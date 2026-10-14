"""FreeCAD-only capture and immutable native writer cross-checks for B32R.

Imports of FreeCAD/Fem are deliberately inside native functions. Headless reads
and JobManager execution do not instantiate another CAD document.
"""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
from types import SimpleNamespace
import uuid

from caelab.beam_model import (SCHEMA, BeamInputError, frame, native_axis_formula,
    validate_draft, validate_model, mesh_data, effective_conditions, number, sub, dot, unit)
from caelab.beam_deck import render, section_card, parse_native_mesh
from caelab.storage import canonical_hash, save_json
from .beam_mesh_binding import require_same_binding
from .mesh_binding import global_placement
from .freeze_analysis import _hash, _serialized_coordinate_close


def native_type(obj):
    from femtools.femutils import type_of_obj
    return type_of_obj(obj)


def get_object(owner, name, path):
    obj=owner.doc.getObject(name) if isinstance(name,str) and name else None
    if obj is None:
        raise BeamInputError(path,'대상이 삭제됐거나 선택되지 않았습니다. 다시 지정하세요.')
    return obj


def _shape(owner, reference, kind, path):
    if not isinstance(reference,dict) or set(reference)!={'object','subelement'}:
        raise BeamInputError(path,'모델에서 모서리 또는 끝점을 선택하세요.')
    obj=get_object(owner,reference['object'],path)
    name=reference['subelement']
    if not isinstance(name,str) or not re.fullmatch(kind+r'[1-9]\d*',name):
        raise BeamInputError(path,'모델의 '+('모서리' if kind=='Edge' else '꼭짓점')+'를 다시 선택하세요.')
    if obj.TypeId in ('App::Link','App::LinkElement') or not hasattr(obj,'Shape'):
        raise BeamInputError(path,'첫 빔 경로는 같은 문서의 직접 형상만 지원합니다. 링크를 원형상으로 바꾸지 않습니다.')
    # Nested parts need a separate placement/occurrence contract; no guesswork.
    gp=global_placement(obj)
    p=obj.Placement
    lp=[float(p.Base.x),float(p.Base.y),float(p.Base.z),*[float(x) for x in p.Rotation.Q]]
    if gp!=lp:
        raise BeamInputError(path,'상위 부품의 별도 배치가 있는 형상은 아직 지원하지 않습니다.')
    if obj.Shape.isNull() or not obj.Shape.isValid():
        raise BeamInputError(path,'형상이 유효하지 않습니다. 원 피처를 수정하세요.')
    try:
        shape=obj.Shape.getElement(name)
    except Exception as exc:
        raise BeamInputError(path,'모서리 또는 꼭짓점이 삭제됐습니다. 다시 지정하세요.') from exc
    if shape.ShapeType!=kind:
        raise BeamInputError(path,'선택한 하위 형상 종류가 다릅니다.')
    return obj,shape,{'object':obj.Name,'subelement':name,'type':obj.TypeId,
        'brep_sha256':hashlib.sha256(obj.Shape.exportBrepToString().encode('utf-8')).hexdigest(),
        'global_placement':gp}


def geometry(owner, draft):
    """Read the real mesh, with native labels. No solid fallback or generated mesh."""
    analysis=get_object(owner,draft['analysis_id'],'analysis_id')
    mesh=get_object(owner,draft['mesh_id'],'mesh_id')
    if native_type(analysis)!='Fem::FemAnalysis' or mesh not in analysis.Group or not hasattr(mesh,'FemMesh'):
        raise BeamInputError('mesh_id','선택한 해석에 포함된 실제 선 메시를 선택하세요.')
    if hasattr(mesh,'getGlobalPlacement'):
        pose=global_placement(mesh)
        if any(abs(v)>1e-12 for v in pose[:6]) or abs(abs(pose[6])-1)>1e-12:
            raise BeamInputError('mesh_id','별도 배치가 있는 메시는 지원하지 않습니다. 표시 형상과 원 메시 좌표를 확인하세요.')
    native=mesh.FemMesh
    if native.Volumes or native.Faces or not native.Edges:
        raise BeamInputError('mesh_id','솔리드·셸이 섞이지 않은 3절점 선 메시가 필요합니다.')
    source,edge,source_pin=_shape(owner,draft['edge'],'Edge','edge')
    if hasattr(mesh,'Shape') and mesh.Shape is not source:
        raise BeamInputError('edge','선택한 메시와 모서리의 원형상이 다릅니다.')
    if str(getattr(edge,'Orientation','Forward'))!='Forward':
        raise BeamInputError('edge','역방향 위상 모서리는 아직 지원하지 않습니다. 진행 방향을 명시한 직선을 사용하세요.')
    import math
    # Parametric endpoints, not Vertex index arithmetic or inferred node labels.
    a=edge.valueAt(edge.FirstParameter);b=edge.valueAt(edge.LastParameter)
    xyz=lambda p:[float(p.x),float(p.y),float(p.z)]
    start,end=xyz(a),xyz(b);length=math.dist(start,end)
    if length<=0 or not math.isclose(float(edge.Length),length,rel_tol=1e-10,abs_tol=1e-8):
        raise BeamInputError('edge','첫 빔 경로는 직선 모서리만 지원합니다.')
    from femmesh import meshtools
    tangent=unit(sub(end,start),'edge')
    native_axis=meshtools.get_beam_main_axis_m(owner.App.Vector(*tangent),number(draft['section']['rotation_deg']))
    local1=xyz(native_axis)
    expected=native_axis_formula(tangent,draft['section']['rotation_deg'])
    if any(abs(x-y)>1e-11 for x,y in zip(local1,expected)):
        raise BeamInputError('section.rotation_deg','설치된 FreeCAD 단면 방향 계산이 이 경로의 확인된 규약과 다릅니다.')
    axes=frame(tangent,local1)
    nodes=[{'id':int(n),'xyz_mm':xyz(p)} for n,p in sorted(native.Nodes.items())]
    elements=[]
    for e in sorted(native.Edges):
        conn=list(native.getElementNodes(e))
        if len(conn)!=3:
            raise BeamInputError('mesh_id','2차 Seg3만 지원합니다. 3절점 선 메시를 선택하세요.')
        elements.append({'id':int(e),'native_nodes':conn,'ccx_nodes':[conn[0],conn[2],conn[1]]})
    model={'schema':SCHEMA,'element':'B32R','section_type':'RECT',
           'units':{'length':'mm','force':'N','moment':'Nmm','elasticity':'MPa','rotation':'rad'},
           'nodes':nodes,'elements':elements,'axes':axes,'edge_start_mm':start,'edge_end_mm':end,
           'length_mm':length,'draft':deepcopy(draft)}
    nn,ee,ss,endpoint_ids=mesh_data(model)
    refs=[];actual=[]
    for i,row in enumerate(draft['ends']):
        obj,vertex,pin=_shape(owner,row['reference'],'Vertex',f'ends.{i}.reference')
        if obj is not source:
            raise BeamInputError(f'ends.{i}.reference','같은 빔 원형상의 끝점을 선택하세요.')
        selected=list(native.getNodesByVertex(vertex))
        if len(selected)!=1 or selected[0] not in endpoint_ids:
            raise BeamInputError(f'ends.{i}.reference','선택 꼭짓점에 유일한 빔 끝 절점이 없습니다. 메시와 참조를 확인하세요.')
        actual.append(int(selected[0]));refs.append(pin)
    model['end_node_ids']=actual
    model['loads'],model['boundaries'],model['end_conditions']=effective_conditions(draft,axes,actual)
    binding={'edge':source_pin,'ends':refs,'mesh_id':mesh.Name,
             'mesh_sha256':canonical_hash({'nodes':nodes,'elements':elements})}
    return model,binding


def _quantity(obj,name,unit_name):
    return float(getattr(obj,name).getValueAs(unit_name).Value)


def native_values(owner, record):
    """Read properties edited in FreeCAD; import is explicit, never overwritten silently."""
    d=deepcopy(record['draft']);s=d['section'];m=d['material']
    sec=get_object(owner,s['object_id'],'section.object_id')
    rot=get_object(owner,s['rotation_id'],'section.rotation_id')
    mat=get_object(owner,m['object_id'],'material.object_id')
    s.update(width_mm=str(_quantity(sec,'RectWidth','mm')),height_mm=str(_quantity(sec,'RectHeight','mm')),
             rotation_deg=str(_quantity(rot,'Rotation','deg')))
    m.update(young_MPa=str(float(owner.App.Units.Quantity(mat.Material['YoungsModulus']).getValueAs('MPa').Value)),
             poisson=str(number(mat.Material['PoissonRatio'])))
    for i,name in enumerate(record.get('end_object_ids',[])):
        obj=get_object(owner,name,f'ends.{i}.reference');row=d['ends'][i]
        refs=list(obj.References)
        if len(refs)!=1:
            raise BeamInputError(f'ends.{i}.reference','단일 끝점 참조가 필요합니다.')
        target,names=refs[0]; names=[names] if isinstance(names,str) else list(names)
        if target is None or len(names)!=1:
            raise BeamInputError(f'ends.{i}.reference','끝점 참조를 다시 지정하세요.')
        row['reference']={'object':target.Name,'subelement':names[0]}
        row['system']=str(obj.CoordinateSystem)
        row['force_N']=[str(_quantity(obj,'Force'+axis,'N')) for axis in 'XYZ']
        row['moment_Nmm']=[str(_quantity(obj,'Moment'+axis,'N*mm')) for axis in 'XYZ']
        for key,prefix,free,units in (('translation_mm','Displacement','TranslationFree','mm'),
                                     ('rotation_deg','Rotation','RotationFree','deg')):
            row[key]=['' if getattr(obj,free+axis) else str(_quantity(obj,prefix+axis,units)) for axis in 'XYZ']
    return d


def property_stamp(owner, record, *, values_only=False):
    """Track native values even when an end reference has become dangling.

    Explicit rebind may repair references, but cannot overwrite a concurrently
    edited material, force or section. Deleted condition objects remain a gate.
    """
    d=record['draft'];s=d['section']
    mat=get_object(owner,d['material']['object_id'],'material.object_id')
    sec=get_object(owner,s['object_id'],'section.object_id');rot=get_object(owner,s['rotation_id'],'section.rotation_id')
    def refs(obj):
        return [(o.Name if o is not None else None,list(ns) if not isinstance(ns,str) else [ns]) for o,ns in obj.References]
    value={'section_id':sec.Name,'rotation_id':rot.Name,'material_id':mat.Name,
        'section_type':str(sec.SectionType),'width_mm':_quantity(sec,'RectWidth','mm'),
        'height_mm':_quantity(sec,'RectHeight','mm'),'rotation_deg':_quantity(rot,'Rotation','deg'),
        'material':dict(mat.Material),'ends':[]}
    if not values_only:value.update(section_refs=refs(sec),rotation_refs=refs(rot),material_refs=refs(mat))
    for name in record.get('end_object_ids',[]):
        obj=get_object(owner,name,'ends');row={'id':name,'system':str(obj.CoordinateSystem)}
        for prefix,units in [('Force','N'),('Moment','N*mm'),('Displacement','mm'),('Rotation','deg')]:
            row[prefix]=[_quantity(obj,prefix+axis,units) for axis in 'XYZ']
        for prefix in ('TranslationFree','RotationFree'):
            row[prefix]=[bool(getattr(obj,prefix+axis)) for axis in 'XYZ']
        if not values_only:row['references']=refs(obj)
        value['ends'].append(row)
    return canonical_hash(value)



def analysis_members(owner, record):
    """Resolve the *current* Analysis membership, independently of property stamps.

    A document object can survive removal from Analysis.Group unchanged. A saved
    property hash is therefore not evidence that a condition is still applied.
    This check is read-only: no automatic re-add, deletion or draft repair.
    """
    draft = record['draft']
    analysis = get_object(owner, draft['analysis_id'], 'analysis_id')
    if native_type(analysis) != 'Fem::FemAnalysis':
        raise BeamInputError('analysis_id', '선택한 객체가 FEM 해석이 아닙니다. 해석을 다시 지정하세요.')
    ends = record.get('end_object_ids')
    if (not isinstance(ends, list) or len(ends) != 2 or
            any(not isinstance(name, str) or not name for name in ends) or len(set(ends)) != 2):
        raise BeamInputError('ends', '서로 다른 빔 끝 조건 두 개를 다시 지정하세요. 저장된 초안은 유지됩니다.')
    required = [
        ('mesh_id', draft['mesh_id'], {'Fem::FemMeshObject', 'Fem::FemMeshGmsh', 'Fem::FemMeshNetgen'}),
        ('section.object_id', draft['section']['object_id'], {'Fem::ElementGeometry1D'}),
        ('section.rotation_id', draft['section']['rotation_id'], {'Fem::ElementRotation1D'}),
        ('material.object_id', draft['material']['object_id'], {'Fem::MaterialCommon'}),
        *[(f'ends.{i}', name, {'CAELab::BeamEnd'}) for i, name in enumerate(ends)],
    ]
    names = [name for _, name, _ in required]
    if len(set(names)) != len(names):
        raise BeamInputError('analysis_id', '단면·재료·방향·메시·끝 조건 참조가 중복됐습니다. 다시 지정하세요.')
    members = list(analysis.Group)
    if len({obj.Name for obj in members}) != len(members):
        raise BeamInputError('analysis_id', '해석 소속 객체가 중복됐습니다. 해석 트리를 확인하세요.')
    for path, name, kinds in required:
        obj = get_object(owner, name, path)
        if obj not in members or native_type(obj) not in kinds:
            raise BeamInputError(path, '현재 해석에서 빠졌거나 종류가 다른 객체입니다: '
                                 + str(getattr(obj, 'Label', name))
                                 + '. 해석 트리에서 명시적으로 다시 지정한 뒤 적용하세요. 초안과 이전 결과는 유지됩니다.')
        if path.startswith('ends.') and getattr(obj, 'TypeId', None) != 'App::FeaturePython':
            raise BeamInputError(path, '빔 끝 조건의 native 객체 종류가 다릅니다. 다시 지정하세요.')
    solvers = []
    for obj in members:
        if getattr(obj, 'Suppressed', False) or set(getattr(obj, 'State', [])) & {'Invalid', 'Error', 'Recompute', 'Touched'}:
            raise BeamInputError('analysis_id', '비활성 또는 재계산이 필요한 해석 객체입니다: ' + obj.Label)
        kind = native_type(obj)
        if kind in ('Fem::SolverCcxTools', 'Fem::SolverCalculix'):
            solvers.append(obj)
        elif obj.Name not in names:
            raise BeamInputError('analysis_id', '빔 전용 경로가 해석 객체를 생략할 수 없습니다: ' + obj.Label)
    if len(solvers) != 1:
        raise BeamInputError('analysis_id', 'CalculiX 설정을 하나 선택하세요.')
    return analysis, solvers[0]


def collect(owner, record):
    if [str(v) for v in owner.App.Version()[:3]] != ['1','1','4']:
        raise BeamInputError('native', '이 빔 경로는 FreeCAD 1.1.4를 기준으로 합니다. 설치 버전을 확인하세요.')
    if record.get('applied_draft_hash')!=canonical_hash(record['draft']):
        raise BeamInputError('draft','수정한 초안을 먼저 적용하세요.')
    analysis, solver = analysis_members(owner, record)
    if property_stamp(owner,record)!=record.get('native_property_stamp'):
        raise BeamInputError('native','FreeCAD 속성이 변경됐습니다. 속성 불러오기 후 확인·적용하세요.')
    model,binding=geometry(owner,record['draft'])
    require_same_binding(record,model,binding)
    required={'AnalysisType':'static','GeometricalNonlinearity':'linear','MaterialNonlinearity':'linear',
              'ModelSpace':'3D','ExcludeBendingStiffness':False,'BeamReducedIntegration':True}
    for name,value in required.items():
        if not hasattr(solver,name) or getattr(solver,name)!=value:
            raise BeamInputError('solver.'+name,'첫 빔 경로는 B32R 선형 정적 해석입니다. native solver 설정을 확인하세요.')
    section=get_object(owner,record['draft']['section']['object_id'],'section.object_id')
    if str(section.SectionType)!='Rectangular':
        raise BeamInputError('section','첫 빔 경로는 Rectangular / RECT 단면만 지원합니다.')
    material=get_object(owner,record['draft']['material']['object_id'],'material.object_id')
    if native_type(material)!='Fem::MaterialCommon' or material.Category!='Solid':
        raise BeamInputError('material','등방 선형 탄성 Solid 재료가 필요합니다.')
    validate_model(model)
    model['source']={'document_id':owner.document_id,'native_document':owner.doc.Name,
                     'analysis_id':analysis.Name,'mesh_id':record['draft']['mesh_id'],
                     'solver_id':solver.Name,'binding':binding,'end_object_ids':record['end_object_ids']}
    return model,solver


def verify_writers(owner,model,solver,folder):
    """Actually call installed native writers, then verify identity and section axes."""
    mesh=get_object(owner,model['draft']['mesh_id'],'mesh_id').FemMesh
    probe=folder/'native-mesh.inp'
    try:
        mesh.writeABAQUS(str(probe),1,False,volVariant='standard',faceVariant='shell',edgeVariant='beam reduced')
        nn,ee=parse_native_mesh(probe.read_text(encoding='utf-8-sig'))
        nodes,elements,_=validate_model(model)
        if set(nn)!=set(nodes) or ee!=elements or any(not _serialized_coordinate_close(x,y)
                for n in nodes for x,y in zip(nodes[n],nn[n])):
            raise BeamInputError('mesh_id','native writer 출력이 저장된 절점·요소·순서와 다릅니다.')
        from femsolver.calculix.write_femelement_geometry import write_femelement_geometry
        sec=get_object(owner,model['draft']['section']['object_id'],'section.object_id')
        ctx=SimpleNamespace(solver_obj=solver,mat_geo_sets=[{'ccx_elset':list(elements),'ccx_elset_name':'BEAM',
            'mat_obj_name':'BEAMMAT','beamsection_obj':sec,'beam_axis_m':model['axes']['local1']}])
        stream=io.StringIO();write_femelement_geometry(stream,ctx)
        effective='\n'.join(s for s in stream.getvalue().splitlines() if s.strip() and not s.startswith('**'))+'\n'
        if effective!=section_card(model):
            raise BeamInputError('section','설치된 native BEAM SECTION 출력이 일치하지 않습니다.')
        return {'mesh_writer':'FemMesh.writeABAQUS(edgeVariant=beam reduced)',
                'mesh_writer_sha256':_hash(probe),'section_writer':'femsolver.calculix.write_femelement_geometry',
                'section_card':effective,'moment_route':'CLOAD DOF4..6; no rigid body; no force couples',
                'rotation_route':'BOUNDARY DOF4..6; deg converted to rad', 'output':'OUTPUT=2D / SECTION FORCES'}
    finally:
        # This diagnostic is not an untracked second executable input.
        if probe.exists():probe.unlink()


def freeze(owner,record):
    model,solver=collect(owner,record)
    saved=owner.project.save()
    generation=owner.generation
    root=owner.export_root/owner.document_id/('F'+uuid.uuid4().hex)
    root.mkdir(parents=True,exist_ok=False)
    writers=verify_writers(owner,model,solver,root)
    name=owner.doc.FileName
    from .projects import save_native_copy
    save_native_copy(owner.doc, root/'editable.FCStd', App=owner.App)
    if owner.doc.FileName!=name or not (root/'editable.FCStd').is_file():
        raise ValueError('Native independent saveCopy failed')
    save_json(root/'mesh.json',model)
    (root/'beam.inp').write_text(render(model),encoding='ascii',newline='\n')
    shutil.copyfile(saved['retained_project'],root/'editable.caepre')
    after,_=collect(owner,record)
    if after!=model or owner.generation!=generation:
        raise BeamInputError('draft','입력 준비 중 모델이 변경됐습니다. 새 입력을 준비하세요. 이전 파일은 보존됩니다.')
    manifest={'kind':'freecad-beam-frozen','schema_version':'1','id':root.name,'input_file':'beam.inp',
        'editable_project':'editable.caepre','native_version':[str(v) for v in owner.App.Version()],
        'document_id':owner.document_id,'analysis_id':model['draft']['analysis_id'],
        'writers':writers,'qualification':'UNKNOWN',
        'files':[{'relative':p.name,'bytes':p.stat().st_size,'sha256':_hash(p)} for p in sorted(root.iterdir()) if p.is_file()]}
    save_json(root/'snapshot.json',manifest)
    return {'snapshot_relative':(root/'snapshot.json').relative_to(owner.export_root).as_posix(),
            'label':owner.doc.Label+' — 빔', 'backend':'structure.calculix.beam'}
