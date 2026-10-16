"""FEM owner transactions over exact existing mesh faces; no mesh/solver owner."""
from copy import deepcopy
import json,re
from caelab.pretension import OPERATIONS,normalize,face_catalog,validate_cut


def _data(fem):
    data=fem._metadata()
    for key in ('pretension_sections','pretension_history','pretension_receipts'):
        data.setdefault(key,[])
        if not isinstance(data[key],list):raise ValueError('저장된 체결 조건 형식을 확인하세요.')
    data.setdefault('pretension_editors',{})
    if not isinstance(data['pretension_editors'],dict):raise ValueError('저장된 체결 편집 초안을 확인하세요.')
    return data


def _analysis(fem,target):
    from .fem_edit import _native_type
    obj=fem._object(target)
    if _native_type(obj)!='Fem::FemAnalysis':raise ValueError('체결 조건을 편집할 해석을 선택하세요.')
    return obj


def _mesh(fem,analysis,identifier):
    from .freeze_analysis import CCX_FROM_NATIVE_TET10
    obj=fem.owner._object(identifier)
    if obj not in analysis.Group or not hasattr(obj,'FemMesh') or getattr(obj,'Suppressed',False):
        raise ValueError('현재 해석에 속한 활성 고체 메시를 선택하세요.')
    binding=fem.owner.mesh_bindings.validate(obj)
    # A validated cold geometry proof is evidence, not a changed source/mesh stamp.
    binding={k:v for k,v in binding.items() if k!='source_equivalence'}
    source=getattr(obj,'Shape',None)
    if source is None or len(source.Shape.Solids)!=1:raise ValueError('하나의 원 고체에 귀속된 메시를 선택하세요.')
    nodes=[{'node_id':int(n),'position_mm':[float(p.x),float(p.y),float(p.z)]} for n,p in obj.FemMesh.Nodes.items()]
    elements=[]
    for e in obj.FemMesh.Volumes:
        ids=list(map(int,obj.FemMesh.getElementNodes(e)))
        if len(ids)!=10:raise ValueError('실제 C3D10 고체 메시를 선택하세요.')
        elements.append({'element_id':int(e),'type':'C3D10','body_id':source.Name,
                         'node_ids':[ids[i] for i in CCX_FROM_NATIVE_TET10]})
    if not elements:raise ValueError('선택한 메시의 고체 요소가 없습니다.')
    return obj,binding,{'nodes':nodes,'elements':elements,'contacts':[]},source.Name


def errors(fem,analysis,row):
    try:
        obj,binding,model,body=_mesh(fem,analysis,row['draft']['mesh_id'])
        if binding!=row['mesh_binding'] or body!=row['body_id']:
            raise ValueError('체결 절단면의 원 메시가 변경됐습니다. 실제 요소면을 다시 선택하세요.')
        validate_cut(model,{**row,'body_id':body})
        return []
    except (ValueError,TypeError,KeyError,AttributeError) as error:return [str(error)]


def read(fem,analysis):
    rows=[deepcopy(r) for r in _data(fem)['pretension_sections'] if r['analysis_id']==analysis.Name]
    for row in rows:row['errors']=errors(fem,analysis,row)
    meshes=[{'id':o.Name,'label':o.Label} for o in analysis.Group if hasattr(o,'FemMesh') and not getattr(o,'Suppressed',False)]
    return {'sections':rows,'meshes':meshes,'analysis_id':analysis.Name,'solver_execution':'NOT_PERFORMED',
            'editor':deepcopy(_data(fem)['pretension_editors'].get(analysis.Name))}


def dispatch(fem,operation,args,target):
    fem.owner.assert_thread();analysis=_analysis(fem,target)
    if operation=='pre.fem.pretension_save_editor':return save_editor(fem,analysis,args)
    if operation=='pre.fem.pretension_read':
        if args:raise ValueError('체결 조건 읽기는 현재 해석만 받습니다.')
        return read(fem,analysis)
    if operation=='pre.fem.pretension_faces':
        if set(args)!={'mesh_id','start','count'} or type(args['start']) is not int or args['start']<0 or type(args['count']) is not int or not 1<=args['count']<=200:
            raise ValueError('실제 메시와 최대 200면의 조회 구간을 선택하세요.')
        obj,binding,model,body=_mesh(fem,analysis,args['mesh_id'])
        rows=[]
        for item in face_catalog(model,body):
            rows.append(item)
            other=deepcopy(item);other['element_face'],other['opposite_face']=item['opposite_face'],item['element_face']
            other['normal']=[-v for v in item['normal']];rows.append(other)
        rows.sort(key=lambda r:r['element_face']);start=args['start']
        return {'faces':rows[start:start+args['count']],'total':len(rows),'start':start,'mesh_binding':binding,'body_id':body}
    if operation=='pre.fem.pretension_highlight':
        if set(args)!={'id'}:raise ValueError('강조할 체결 조건을 선택하세요.')
        row=next((r for r in _data(fem)['pretension_sections'] if r['id']==args['id'] and r['analysis_id']==analysis.Name),None)
        if row is None:raise ValueError('체결 조건을 다시 선택하세요.')
        problems=errors(fem,analysis,row)
        if problems:raise ValueError('; '.join(problems))
        mesh,binding,model,body=_mesh(fem,analysis,row['draft']['mesh_id'])
        cut=validate_cut(model,row);mesh.ViewObject.HighlightedNodes=cut['node_ids']
        return {'selected_mesh_nodes':len(cut['node_ids']),'applied':False}
    fem._assert_idle()
    expected={'id','expected_revision','request_id'}|({'draft','mesh_binding'} if operation=='pre.fem.pretension_set' else set())
    if 'expected_editor_sha256' in args:expected.add('expected_editor_sha256')
    if operation not in ('pre.fem.pretension_set','pre.fem.pretension_remove') or set(args)!=expected:
        raise ValueError('현재 체결 초안과 이전 버전으로 적용하거나 삭제하세요.')
    identifier,request=args['id'],args['request_id']
    if not isinstance(identifier,str) or not re.fullmatch(r'P[A-Za-z0-9_]{1,47}',identifier):raise ValueError('체결 조건의 식별자가 올바르지 않습니다.')
    if not isinstance(request,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}',request):raise ValueError('같은 요청의 재확인 정보가 필요합니다.')
    if len(json.dumps(args,allow_nan=False))>4*1024*1024:raise ValueError('체결 초안 크기를 줄이세요.')
    from .fem_edit import _hash
    data=_data(fem);digest=_hash({'operation':operation,'analysis_id':analysis.Name,'arguments':args})
    old=next((r for r in data['pretension_sections'] if r['id']==identifier and r['analysis_id']==analysis.Name),None)
    revision=(old or {}).get('revision')
    receipts=[r for r in data['pretension_receipts'] if r['request_id']==request]
    if receipts:
        if len(receipts)!=1 or receipts[0]['command_sha256']!=digest or receipts[0]['result_revision']!=revision:
            raise ValueError('이 요청 뒤 체결 조건이 바뀌었습니다. 현재 초안은 유지됩니다.')
        return {'id':identifier,'revision':revision,'replayed':True,'state':read(fem,analysis)}
    if 'expected_editor_sha256' in args:
        from caelab.storage import canonical_hash
        editor=data['pretension_editors'].get(analysis.Name)
        if args['expected_editor_sha256']!=(canonical_hash(editor) if editor is not None else None):
            raise ValueError('체결 편집 초안이 다른 곳에서 바뀌었습니다. 현재 입력을 유지합니다.')
    if args['expected_revision']!=revision:raise ValueError('체결 조건이 다른 곳에서 변경됐습니다. 초안을 보존하고 다시 읽으세요.')
    record=None
    if operation=='pre.fem.pretension_set':
        draft=deepcopy(args['draft'])
        # Incomplete numeric text remains editable/saveable; freeze calls normalize.
        if not isinstance(draft,dict) or set(draft)!={'label','mesh_id','element_faces','axis','control'}:
            raise ValueError('체결 초안의 항목을 확인하세요.')
        obj,binding,model,body=_mesh(fem,analysis,draft['mesh_id'])
        if args['mesh_binding']!=binding:raise ValueError('절단면을 고른 뒤 메시가 변경됐습니다. 실제 요소면을 다시 선택하세요.')
        record={'id':identifier,'analysis_id':analysis.Name,'draft':draft,'mesh_binding':binding,'body_id':body}
        record['revision']=_hash(record)
    elif old is None:raise ValueError('삭제할 체결 조건이 없습니다.')
    new_revision=(record or {}).get('revision')
    def change():
        current=_data(fem)
        if current!=data:raise ValueError('적용 전 문서가 바뀌었습니다. 현재 초안을 유지합니다.')
        if old:current['pretension_history'].append(deepcopy(old))
        current['pretension_sections']=[r for r in current['pretension_sections'] if r['id']!=identifier]
        if record:current['pretension_sections'].append(record)
        stored=current['pretension_editors'].get(analysis.Name)
        if stored and stored['id']==identifier and ('expected_editor_sha256' in args or
                (record is not None and stored['draft']==record['draft'] and stored['mesh_binding']==record['mesh_binding'])):
            current['pretension_editors'].pop(analysis.Name,None)
        current['pretension_receipts'].append({'request_id':request,'command_sha256':digest,'id':identifier,'result_revision':new_revision})
        fem.owner.write_metadata(current)
    fem._transaction('체결 조건 적용' if record else '체결 조건 삭제',change)
    return {'id':identifier,'revision':new_revision,'replayed':False,'state':read(fem,analysis)}


def freeze(fem,analysis,bodies,model):
    if analysis.Name in _data(fem)['pretension_editors']:
        raise ValueError('저장된 체결 초안이 미적용 상태입니다. 볼트 체결에서 적용하거나 수정 취소하세요.')
    frozen=[]
    for record in _data(fem)['pretension_sections']:
        if record['analysis_id']!=analysis.Name:continue
        problems=errors(fem,analysis,record)
        if problems:raise ValueError('; '.join(problems))
        body=record['body_id'];native=bodies.get(body)
        if native is None or native['mesh'].Name!=record['draft']['mesh_id'] or {k:v for k,v in native['binding'].items() if k!='source_equivalence'}!=record['mesh_binding']:
            raise ValueError('체결 절단면과 동결할 원 메시가 다릅니다.')
        row=deepcopy(record);mapping=model['body_maps'][body]['elements']
        row['native_element_faces']=deepcopy(row['draft']['element_faces'])
        row['draft']['element_faces']=[[mapping.get(e,mapping.get(str(e))),f] for e,f in row['native_element_faces']]
        frozen.append(row)
    if frozen:
        from caelab.pretension import sections
        model['pretension_sections']=frozen;sections(model)


def save_editor(fem,analysis,args):
    """Save raw UI text without applying it to the physical condition."""
    from caelab.storage import canonical_hash
    fem._assert_idle()
    if set(args)!={'editor','expected_editor_sha256'}:
        raise ValueError('현재 체결 편집 초안과 이전 저장 상태를 지정하세요.')
    data=_data(fem);old=data['pretension_editors'].get(analysis.Name);editor=deepcopy(args['editor'])
    if old==editor:return {'editor':editor,'state':read(fem,analysis),'replayed':True}
    if args['expected_editor_sha256']!=(canonical_hash(old) if old is not None else None):
        raise ValueError('체결 편집 초안이 다른 곳에서 바뀌었습니다. 현재 입력은 유지합니다.')
    if editor is not None:
        if (not isinstance(editor,dict) or set(editor)!={'id','draft','mesh_binding','expected_revision'} or
                not isinstance(editor['id'],str) or not re.fullmatch(r'P[A-Za-z0-9_]{1,47}',editor['id']) or
                not isinstance(editor['draft'],dict) or set(editor['draft'])!={'label','mesh_id','element_faces','axis','control'} or
                len(json.dumps(editor,ensure_ascii=False,allow_nan=False).encode('utf-8'))>4*1024**2):
            raise ValueError('체결 편집 초안의 항목과 크기를 확인하세요.')
        applied=next((r for r in data['pretension_sections'] if r['id']==editor['id'] and r['analysis_id']==analysis.Name),None)
        if editor['expected_revision']!=(applied or {}).get('revision'):
            raise ValueError('적용된 체결 조건이 바뀌었습니다. 현재 초안을 유지하고 대상을 다시 확인하세요.')
    def change():
        if _data(fem)!=data:raise ValueError('저장 중 문서가 바뀌었습니다. 현재 체결 편집을 유지합니다.')
        if editor is None:data['pretension_editors'].pop(analysis.Name,None)
        else:data['pretension_editors'][analysis.Name]=editor
        fem.owner.write_metadata(data)
    fem._transaction('체결 편집 초안 저장' if editor is not None else '체결 편집 초안 취소',change)
    return {'editor':editor,'state':read(fem,analysis),'replayed':False}
