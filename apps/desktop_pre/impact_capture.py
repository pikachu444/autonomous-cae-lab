"""Main-thread capture of the user's admitted native FE bodies, without solving."""
import threading
from copy import deepcopy
from caelab.impact_model import BACKEND,default_settings,parse_inp
from caelab.contact import separate_meshes,surface_union,number
from .freeze_contact import _refs
from .fem_edit import _native_type,_target


def capture(owner,analysis_id,solver_id):
    import FreeCAD as App
    from femtools import membertools
    from femmesh import meshtools
    from femmesh.meshsetsgetter import MeshSetsGetter
    if threading.current_thread() is not threading.main_thread():
        raise ValueError('Native FE capture requires its GUI owner thread')
    owner.fem._assert_idle()
    analysis,solver=owner._object(analysis_id),owner._object(solver_id)
    if _native_type(analysis)!='Fem::FemAnalysis' or solver not in analysis.Group:
        raise ValueError('이 문서의 Analysis와 메시 참조용 solver를 선택하세요')
    if _native_type(solver)!='Fem::SolverCcxTools':
        raise ValueError('현재 native 면 매핑은 CalculiX 도구가 소유한 메시를 사용합니다')
    doc=owner.doc
    if doc.isTouched() or any(set(o.State)&{'Touched','Invalid','Error','Recompute'} for o in doc.Objects):
        raise ValueError('형상과 메시를 재계산하고 오류를 해결하세요')
    saved=owner.project.save(); generation=owner.generation
    active=[o for o in analysis.Group if not getattr(o,'Suppressed',False)]
    members=membertools.AnalysisMember(analysis)
    meshes=[o for o in active if hasattr(o,'FemMesh')]
    records=[r for r in owner.fem.contact._data()['contacts'] if r['analysis_id']==analysis.Name
             and not getattr(owner._object(r['object_id']),'Suppressed',False)]
    allowed=[solver,*meshes,*[r['Object'] for r in members.mats_linear],
             *[r['Object'] for r in members.cons_fixed],*[owner._object(r['object_id']) for r in records]]
    unsupported=[o.Label for o in active if o not in allowed]
    if unsupported: raise ValueError('동적 조건으로 자동 변환하지 않는 항목: '+', '.join(unsupported)+'. 별도 Analysis에서 명시적으로 정리하세요')
    bodies={}; rows=[]
    for mesh in meshes:
        source=getattr(mesh,'Shape',None)
        if source is None or source.Document is not doc or source.Name in bodies or len(source.Shape.Solids)!=1 or not source.Shape.copy(True,False).isValid():
            raise ValueError('물체별로 유효한 한 솔리드와 독립 메시가 필요합니다')
        binding=owner.mesh_bindings.validate(mesh)
        quality=owner.fem.quality(mesh,offset=0,limit=1)
        if quality['bad_element_count'] or not mesh.FemMesh.Volumes: raise ValueError(mesh.Label+': 메시 품질을 수정하세요')
        getter=MeshSetsGetter(analysis,solver,mesh,membertools.AnalysisMember(analysis))
        _,ids,is_sub=meshtools.get_ccx_elements(getter,(source,'Solid1'))
        if is_sub or set(map(int,ids))!=set(map(int,mesh.FemMesh.Volumes)): raise ValueError('실제 물체와 메시 소유권이 다릅니다')
        native_nodes=mesh.FemMesh.Nodes
        rows.append({'body_id':source.Name,
            'nodes':[{'node_id':int(n),'position_mm':[number(p.x),number(p.y),number(p.z)]} for n,p in sorted(native_nodes.items())],
            'elements':[{'element_id':int(e),'type':'C3D10','native_node_ids':list(map(int,mesh.FemMesh.getElementNodes(e)))}
                        for e in sorted(mesh.FemMesh.Volumes)]})
        bodies[source.Name]={'object':source,'getter':getter,'mesh':mesh,'binding':binding,'target':_target(source,['Solid1'])}
    assembled=separate_meshes(rows,minimum_bodies=1)
    lines=['*HEADING','Native FE explicit capture','*NODE']
    lines += [str(r['node_id'])+','+','.join(format(x,'.17g') for x in r['position_mm']) for r in assembled['nodes']]
    names={body:'BODY'+str(i) for i,body in enumerate(bodies,1)}
    for body,name in names.items():
        lines.append('*ELEMENT,TYPE=C3D10,ELSET='+name)
        lines += [str(r['element_id'])+','+','.join(map(str,r['node_ids'])) for r in assembled['elements'] if r['body_id']==body]
        lines.append('*NSET,NSET='+name)
        node_ids=list(assembled['body_maps'][body]['nodes'].values())
        lines += [','.join(map(str,node_ids[i:i+16])) for i in range(0,len(node_ids),16)]
    assigned={}
    for i,row in enumerate(members.mats_linear,1):
        material=row['Object']; refs=_refs(material,bodies,material=True)
        owners=[o.Name for o,_ in refs] if refs else list(bodies) if len(members.mats_linear)==1 else []
        if _native_type(material)!='Fem::MaterialCommon' or material.Category!='Solid' or not owners:
            raise ValueError('등방 재료를 각 물체에 명시적으로 배정하세요')
        E=number(App.Units.Quantity(material.Material['YoungsModulus']).getValueAs('MPa').Value)
        nu=number(material.Material['PoissonRatio'])
        if not material.Material.get('Density'): raise ValueError(material.Label+': 밀도와 단위를 native 재료에 입력하세요')
        rho=number(App.Units.Quantity(material.Material['Density']).getValueAs('kg/m^3').Value)*1e-12
        lines += [f'*MATERIAL,NAME=MAT{i}','*DENSITY',format(rho,'.17g'),'*ELASTIC',f'{E:.17g},{nu:.17g}']
        for body in owners:
            if body in assigned: raise ValueError('물체에 재료가 중복 배정되었습니다')
            assigned[body]=i
            lines.append(f'*SOLID SECTION,ELSET={names[body]},MATERIAL=MAT{i}')
    if set(assigned)!=set(bodies): raise ValueError('재료 없는 물체가 있습니다')
    for i,row in enumerate(members.cons_fixed,1):
        obj=row['Object']; refs=_refs(obj,bodies)
        errors=owner.fem._condition_errors(obj,owner.fem._metadata())
        if errors: raise ValueError(obj.Label+': '+'; '.join(errors))
        body=refs[0][0].Name; getter=bodies[body]['getter']
        local_nodes=meshtools.get_femnodes_by_references(bodies[body]['mesh'].FemMesh,obj.References)
        ids=sorted(assembled['body_maps'][body]['nodes'][int(n)] for n in local_nodes)
        if not ids: raise ValueError('고정 면에 대응하는 절점이 없습니다')
        lines.append(f'*NSET,NSET=FIXED{i}')
        lines += [','.join(map(str,ids[j:j+16])) for j in range(0,len(ids),16)]
        lines += ['*BOUNDARY',f'FIXED{i},1,3,0']
    contact_sources=[]; contacts=[]
    for i,record in enumerate(records,1):
        errors=owner.fem.contact.errors(record)
        if errors: raise ValueError(record['draft']['label']+': '+'; '.join(r['message'] for r in errors))
        source_row={'draft':deepcopy(record['draft']),'surfaces':{}}
        for side in ('a','b'):
            target=record[side]['target']; body=target['object_id']
            if body not in bodies: raise ValueError('접촉 면 물체의 메시가 없습니다')
            face_rows=[]
            for face in target['subelements']:
                _,entries,is_sub=meshtools.get_ccx_elements(bodies[body]['getter'],(bodies[body]['object'],face['name']))
                if not is_sub: raise ValueError('접촉 면의 원 요소 면을 찾지 못했습니다')
                face_rows.append({'face':face['name'],'element_faces':[(int(e),int(s)) for e,s in entries]})
            mapped=surface_union(body,face_rows,assembled['body_maps'])
            name=f'CONTACT{i}{side.upper()}'
            lines.append('*SURFACE,TYPE=ELEMENT,NAME='+name)
            lines += [f'{e},S{s}' for e,s in mapped['element_faces']]
            source_row['surfaces'][side]={'name':name,'mapping':mapped,'target':deepcopy(target)}
        contacts.append({'a':f'CONTACT{i}A','b':f'CONTACT{i}B','law':'UNSELECTED','friction':0.})
        contact_sources.append(source_row)
    settings=default_settings()
    settings['source']={'title':doc.Label,'format':'INP','units':'Mg/mm/s','text':'\n'.join(lines)+'\n',
        'provenance':{'kind':'native_FE_capture','document_id':owner.document_id,'analysis_id':analysis.Name,
            'saved_project_identity':{k:v for k,v in saved.items() if k in ('id','revision_id','sha256')},'body_map':assembled['body_maps'],'body_labels':{names[k]:v['object'].Label for k,v in bodies.items()},
            'contact_sources':contact_sources,'generation':generation}}
    settings['contacts']=contacts
    parse_inp(settings['source']['text'])
    owner.refresh()
    if owner.generation!=generation: raise ValueError('입력 보존 중 native 형상이 바뀌었습니다. 원본을 확인하세요')
    return {'draft':{'backend':BACKEND,'settings':settings},'title':doc.Label+' 충격 해석','calculation':'NOT_STARTED'}
