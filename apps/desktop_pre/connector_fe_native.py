"""Native C3D4 capture additions; existing Impact capture owns material/BCs."""
from copy import deepcopy
from caelab.connector_model import ConnectorInputError,number
from caelab.storage import canonical_hash


def _binding_state(owner,mesh):
    value=deepcopy(owner.mesh_bindings.validate(mesh))
    value.pop('source_equivalence',None)  # Current validation report, not source state.
    return value


def source_stamp(owner,analysis_id):
    from .freeze_analysis import _plain
    analysis=owner.doc.getObject(analysis_id)
    if analysis is None:raise ConnectorInputError('fe','원 해석이 삭제됐습니다.')
    # Supported material/condition properties only; no proxy/object serialization
    # and no volatile UI/mesh cache properties become physical authority.
    rows=[]
    for obj in analysis.Group:
        row={'object_id':obj.Name,'type':obj.TypeId,'suppressed':bool(getattr(obj,'Suppressed',False))}
        for key in ('Material','References','Category','Force','DirectionVector','Reversed','AnalysisType','ModelSpace','GeometricalNonlinearity','MaterialNonlinearity'):
            if hasattr(obj,key):row[key]=_plain(getattr(obj,key))
        if hasattr(obj,'FemMesh'):row['mesh_binding']=_binding_state(owner,obj)
        rows.append(row)
    return canonical_hash(rows)


def assemble(bodies,*,minimum_bodies=1):
    """FreeCAD 1.1.4 FemMesh.writeABAQUS tetra4 order (1,0,2,3).

    Keep separate bodies and their actual native labels. Only the current E5
    private capture branch calls this; legacy C3D10 contact assembly is unchanged.
    """
    if minimum_bodies!=1 or not bodies: raise ValueError('실제 C3D4 물체 메시를 선택하세요.')
    nodes=[];elements=[];maps={}
    for b in bodies:
        if b['body_id'] in maps: raise ValueError('물체 메시 소유권이 중복됐습니다.')
        nm={};em={}
        for row in b['nodes']:
            n=row['node_id']
            if type(n) is not int or n<=0 or n in nm: raise ValueError('원 메시 절점 번호가 잘못됐습니다.')
            nm[n]=len(nodes)+1
            nodes.append({'node_id':nm[n],'body_id':b['body_id'],'native_node_id':n,'position_mm':row['position_mm']})
        used=set()
        for row in b['elements']:
            conn=row['native_node_ids'];eid=row['element_id']
            if len(conn)!=4 or len(set(conn))!=4 or any(n not in nm for n in conn) or eid in em:
                raise ValueError('이 FE 연결은 전체 선형 C3D4 메시를 사용합니다. 2차·혼합 요소를 바꾸지 않습니다.')
            em[eid]=len(elements)+1;used.update(conn)
            elements.append({'element_id':em[eid],'body_id':b['body_id'],'native_element_id':eid,
                'native_node_ids':list(conn),'node_ids':[nm[conn[j]] for j in (1,0,2,3)]})
        if not em or used!=set(nm):raise ValueError('메시에 누락·미사용 절점 또는 요소가 있습니다.')
        maps[b['body_id']]={'nodes':nm,'elements':em}
    return {'nodes':nodes,'elements':elements,'body_maps':maps,'native_to_deck_slots':[1,0,2,3],'interface_policy':'independent_body_dofs'}


def validate_native_mesh(mesh):
    """Use existing native tetra Jacobians/floors, with this C3D4 profile."""
    from .fem_edit import _element_quality
    native=mesh.FemMesh;nodes=native.Nodes
    if not native.Volumes:raise ConnectorInputError('fe','선형 C3D4 체적 메시를 선택하세요.')
    for ident in native.Volumes:
        row=_element_quality(native,int(ident),node_table=nodes)
        errors=[e for e in row['errors'] if not (row['node_count']==4 and e=='UNSUPPORTED_RUN_ELEMENT_TYPE')]
        if row['node_count']!=4 or errors:
            raise ConnectorInputError('fe',mesh.Label+': 선형 C3D4 연결·좌표와 기존 Jacobian 품질 기준을 확인하세요.')


def capture(owner,analysis_id,solver_id,draft):
    from .impact_capture import capture as impact_capture
    # Existing function still owns actual material, density, supports, contacts,
    # native mesh binding, saved archive and generation checks.
    value=impact_capture(owner,analysis_id,solver_id,_connector_linear=True)
    settings=value['draft']['settings'];model=__import__('caelab.impact_model',fromlist=['model_from_settings']).model_from_settings(settings)
    provenance=settings['source']['provenance'];bodymap=provenance['body_map'];attachments=[];binding=[]
    analysis=owner.doc.getObject(analysis_id)
    meshes=[o for o in analysis.Group if hasattr(o,'FemMesh') and not getattr(o,'Suppressed',False)]
    for i,end in enumerate(draft['endpoints']):
        s=end['selection']
        if not isinstance(s,dict): raise ConnectorInputError(f'endpoints.{i}.selection','먼저 실제 부착 영역과 기준점을 선택하세요.')
        ids=set();body_id=None;mesh_id=None
        for ref in s['native_refs']:
            obj=owner.doc.getObject(ref['object_id'])
            if obj is None:raise ConnectorInputError('fe','원 부착 대상을 다시 선택하세요.')
            # Last RP-only vertex may be independent CAD datum. Only a matching
            # source mesh contributes FE patch nodes; RP remains a separate node.
            selected=[m for m in meshes if getattr(m,'Shape',None) is obj or m is obj]
            if not selected:
                if all(n.startswith('Vertex') for n in ref['subelements']):continue
                raise ConnectorInputError('fe','선택 영역은 이 해석의 실제 메시 물체여야 합니다.')
            if len(selected)!=1:raise ConnectorInputError('fe','물체의 메시를 하나로 명확히 지정하세요.')
            mesh=selected[0];body=mesh.Shape.Name
            if body_id is not None and body_id!=body:raise ConnectorInputError('fe','한 부착 영역은 한 FE 물체에 속해야 합니다.')
            body_id,mesh_id=body,mesh.Name
            from femmesh import meshtools
            if mesh is obj:
                native=[int(n[4:]) for n in ref['subelements'] if n.startswith('Node') and n[4:].isdigit()]
                if len(native)!=len(ref['subelements']):raise ConnectorInputError('fe','실제 메시 Node 번호를 선택하세요.')
            else:
                if any(not n.startswith(('Face','Edge','Vertex')) for n in ref['subelements']):
                    raise ConnectorInputError('fe','C3D4 전체 물체가 아닌 부착 면 또는 절점 영역을 선택하세요.')
                native=meshtools.get_femnodes_by_references(mesh.FemMesh,[(obj,tuple(ref['subelements']))])
            mapping=bodymap[body]['nodes']
            for n in native:
                if n not in mapping and str(n) not in mapping:raise ConnectorInputError('fe','원 메시 절점 대응이 없습니다.')
                ids.add(mapping[n] if n in mapping else mapping[str(n)])
            binding.append({'mesh_id':mesh.Name,'body_id':body,'binding':_binding_state(owner,mesh),
                            'analysis_stamp':source_stamp(owner,analysis_id)})
        attachments.append({'native_node_ids':sorted(ids),'selection_sha256':canonical_hash(s),
                            'body_id':body_id,'mesh_id':mesh_id})
    # These fields are current user time settings, not an implicit solver run.
    end=number(draft['time']['end_s'],'time.end_s')
    settings['time'].update(end_s=end,history_interval_s=number(draft['time']['history_interval_s'],'time.history_interval_s'),
                            field_interval_s=end,scale=number(draft['time']['scale'],'time.scale'))
    fe={'analysis_id':analysis_id,'solver_id':solver_id,'settings':settings,'attachments':attachments,'source_binding':binding,
        'initial_motion_source':'existing_fe'}
    from caelab.connector_fe import validate_fe
    validate_fe(fe,{**draft,'fe':fe})
    return fe


def revalidate(owner,draft):
    if draft['fe'] is None:return
    fe=draft['fe']
    # Read-only current mesh stamp comparison; no material edit or regenerated
    # capture/save during apply/freeze. Material/source pin is part of records.
    for row in fe['source_binding']:
        mesh=owner.doc.getObject(row['mesh_id'])
        if mesh is None or _binding_state(owner,mesh)!={k:v for k,v in row['binding'].items() if k!='source_equivalence'} or source_stamp(owner,fe['analysis_id'])!=row['analysis_stamp']:
            raise ConnectorInputError('fe','원 FE 메시 또는 형상이 바뀌었습니다. FE 입력을 다시 가져오세요.')
