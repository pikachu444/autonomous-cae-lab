"""Existing native Owner metadata/transactions, exact mesh binding and IC objects."""
from copy import deepcopy
import json
from caelab.storage import canonical_hash
from caelab.initial_field_conditions import default_draft,normalize,OPERATIONS,READ_ONLY


def data(fem):
    value=fem._metadata();value.setdefault('initial_fields',{})
    if not isinstance(value['initial_fields'],dict):raise ValueError('저장된 초기장 조건을 확인하세요.')
    return value


def record(fem,aid):return deepcopy(data(fem)['initial_fields'].get(aid))


def native_temperatures(analysis):
    from .fem_edit import _native_type
    return [o for o in analysis.Group if _native_type(o)=='Fem::ConstraintInitialTemperature' and not getattr(o,'Suppressed',False)]


def allowed_members(fem,analysis,*,capture_only=False):
    objects=native_temperatures(analysis);r=record(fem,analysis.Name)
    if capture_only:return objects
    if not objects:
        if r and r.get('applied',{}).get('definition',{}).get('kind')=='temperature':
            raise ValueError('적용한 원 온도 조건이 삭제되거나 비활성화됐습니다. 다시 확인하고 명시 적용하세요.')
        return []
    if not r or not r.get('applied') or len(objects)!=1 or objects[0].Name!=r['applied'].get('temperature_object'):
        raise ValueError('기존 초기 온도 조건을 온도·초기 상태에서 읽고 명시 적용하세요. 조건을 생략하지 않습니다.')
    t=r['applied']['definition'].get('temperature')
    if t is None:raise ValueError('기존 온도 조건과 선택한 초기 상태의 종류가 다릅니다.')
    obj=objects[0]
    expected=[(t['object_id'],tuple(s['name'] for s in t['subelements'])) for t in r['applied']['region']['targets']]
    actual=[(o.Name,tuple(n)) for o,n in obj.References]
    if actual!=expected:raise ValueError('원 온도 조건의 선택 영역이 바뀌었습니다. 영역을 다시 확인하고 적용하세요.')
    if (float(obj.initialTemperature.getValueAs('K').Value)!=t['reference_K'] or
        not obj.EnableFinalTemperature or float(obj.FinalTemperature.getValueAs('K').Value)!=t['samples_K'][-1][1] or obj.EnableAmplitude):
        raise ValueError('원 FreeCAD 온도 조건이 적용된 초기장과 다릅니다. 다시 읽고 명시 적용하세요.')
    return objects


def base(fem,analysis,solver=None):
    from .fem_edit import _native_type
    solvers=[o for o in analysis.Group if _native_type(o)=='Fem::SolverCcxTools' and not getattr(o,'Suppressed',False)]
    if solver is None:
        if len(solvers)!=1:raise ValueError('현재 해석의 기존 CalculiX 3D 솔버 하나를 선택하세요.')
        solver=solvers[0]
    from .freeze_contact import collect
    return collect(analysis,solver,fem,capture_only=True,for_initial_fields=True)


def region(fem,analysis,mesh_id,*,selected=False):
    mesh=fem.owner._object(mesh_id)
    if mesh not in analysis.Group or not hasattr(mesh,'FemMesh'):raise ValueError('현재 해석의 고체 메시를 선택하세요.')
    proof=fem.owner.mesh_bindings.validate(mesh);proof={k:v for k,v in proof.items() if k!='source_equivalence'}
    nodes=sorted(map(int,mesh.FemMesh.Nodes));elements=sorted(map(int,mesh.FemMesh.Volumes))
    target=[]
    if selected:
        from femmesh import meshtools
        from .fem_edit import _target
        selections=fem.owner.Gui.Selection.getSelectionEx(fem.owner.doc.Name)
        if not selections or any(s.Object is not mesh.Shape for s in selections):raise ValueError('현재 메시의 원 고체에서 실제 면·절점을 선택하세요.')
        refs=[]
        for selection in selections:
            names=list(selection.SubElementNames)
            if not names or any(not n.startswith(('Face','Vertex','Solid')) for n in names):raise ValueError('원 고체의 면·절점 또는 전체 고체를 선택하세요.')
            refs.append((selection.Object,tuple(names)));target.append(_target(selection.Object,names))
        nodes=sorted(map(int,meshtools.get_femnodes_by_references(mesh.FemMesh,refs)))
        if not nodes:raise ValueError('선택한 영역에 원 메시 절점이 없습니다.')
    return {'mesh_id':mesh_id,'body_id':mesh.Shape.Name,'node_ids':nodes,'element_ids':elements,
        'mesh_binding':proof,'targets':target,'selection':'native_subshape' if selected else 'explicit_whole_body'}


def normalized(fem,analysis,draft,selection):
    if not selection or selection['mesh_id']!=draft['mesh_id']:raise ValueError('실제 메시 영역을 선택하세요.')
    current=region(fem,analysis,selection['mesh_id'])
    if current['mesh_binding']!=selection['mesh_binding'] or not set(selection['node_ids'])<=set(current['node_ids']):
        raise ValueError('선택 뒤 원 형상·메시가 바뀌었습니다. 영역을 다시 선택하세요.')
    if selection.get('targets'):
        from .fem_edit import _target
        for target in selection['targets']:
            now=_target(fem.owner._object(target['object_id']),[s['name'] for s in target['subelements']])
            if not fem._same_condition_target(target,now):raise ValueError('초기장 원 선택이 바뀌었습니다. 실제 영역을 다시 선택하세요.')
    model,proof=base(fem,analysis);body=selection['body_id'];maps=model['body_maps'][body]
    converted=deepcopy(draft)
    def mapped(values,key):return [maps[key].get(i,maps[key].get(str(i))) for i in values]
    converted['node_ids']=mapped(selection['node_ids'],'nodes');converted['element_ids']=mapped(selection['element_ids'],'elements')
    if converted['stress']['ip_rows'] is not None:
        for row in converted['stress']['ip_rows']:row['element_id']=maps['elements'].get(row['element_id'],maps['elements'].get(str(row['element_id'])))
    definition=normalize(model,converted)
    from caelab.adapters.initial_field_deck import program
    program(model,definition)
    return model,converted,definition,proof


def read(fem,analysis):
    r=record(fem,analysis.Name);errors=[]
    if r:
        try:normalized(fem,analysis,r['draft'],r.get('region'))
        except (ValueError,KeyError,TypeError,AttributeError) as e:errors.append(str(e))
    temps=[]
    for obj in native_temperatures(analysis):
        temps.append({'id':obj.Name,'label':obj.Label,'reference_K':float(obj.initialTemperature.getValueAs('K').Value),
            'final_K':float(obj.FinalTemperature.getValueAs('K').Value) if obj.EnableFinalTemperature else None,
            'amplitude':bool(obj.EnableAmplitude),'references':[{'object':o.Name,'subelements':list(n)} for o,n in obj.References]})
    defaults=None;steps=[]
    try:
        model,_=base(fem,analysis)
        from caelab.initial_field_conditions import static_program
        defaults=default_draft(model)
        steps=static_program(model)[0]['steps']
    except (ValueError,KeyError,TypeError,AttributeError) as e:
        if str(e) not in errors:errors.append(str(e))
    return {'record':r,'errors':errors,'meshes':[{'id':o.Name,'label':o.Label} for o in analysis.Group if hasattr(o,'FemMesh')],
        'native_temperatures':temps,'default_draft':defaults,'static_steps':deepcopy(steps),'execution':'NOT_PERFORMED'}


def dispatch(fem,operation,args,target):
    fem.owner.assert_thread();analysis=fem._object(target)
    from .fem_edit import _native_type
    if _native_type(analysis)!='Fem::FemAnalysis':raise ValueError('초기장을 편집할 원 해석을 선택하세요.')
    if operation=='pre.initial.read':
        if args:raise ValueError('읽기는 현재 해석만 받습니다.')
        return read(fem,analysis)
    if operation=='pre.initial.region':
        if set(args)!={'mesh_id','selected'} or type(args['selected'])is not bool:raise ValueError('현재 메시와 실제 선택 영역을 지정하세요.')
        return region(fem,analysis,args['mesh_id'],selected=args['selected'])
    fem._assert_idle();value=data(fem);old=value['initial_fields'].get(analysis.Name)
    if operation not in OPERATIONS or set(args)!=({'draft','region','expected_revision'} if operation=='pre.initial.save_draft' else {'expected_revision'}):
        raise ValueError('초기장 초안과 현재 저장 상태로 적용하거나 취소하세요.')
    if args['expected_revision']!=(old or {}).get('revision'):raise ValueError('다른 곳에서 초기장을 바꿨습니다. 현재 편집을 보존하고 다시 읽으세요.')
    new=deepcopy(old) if old else {'draft':default_draft(),'region':None,'applied':None}
    if operation=='pre.initial.save_draft':
        json.dumps(args,allow_nan=False)
        if len(json.dumps(args,ensure_ascii=False).encode())>4*1024**2 or not isinstance(args['draft'],dict):raise ValueError('초기장 편집 크기와 형식을 확인하세요.')
        new.update(draft=deepcopy(args['draft']),region=deepcopy(args['region']))
    elif operation=='pre.initial.discard':
        if not old:return read(fem,analysis)
        if old.get('applied'):new.update(draft=deepcopy(old['applied']['native_draft']),region=deepcopy(old['applied']['region']))
        else:new=None
    elif operation=='pre.initial.apply':
        if not old:raise ValueError('초안을 먼저 보관하세요.')
        model,converted,definition,proof=normalized(fem,analysis,new['draft'],new['region'])
        new['applied']={'native_draft':deepcopy(new['draft']),'region':deepcopy(new['region']),
            'draft':converted,'definition':definition,'source_identity':proof,'temperature_object':None}
    def change():
        if data(fem)!=value:raise ValueError('저장 중 원 문서가 바뀌었습니다. 현재 초안을 유지합니다.')
        if operation=='pre.initial.apply':
            existing=native_temperatures(analysis)
            if len(existing)>1:raise ValueError('중복된 초기 온도 조건을 원 트리에서 정리하세요.')
            if definition['kind']=='temperature':
                from ObjectsFem import makeConstraintInitialTemperature
                obj=existing[0] if existing else makeConstraintInitialTemperature(analysis.Document,'InitialFieldTemperature')
                if obj not in analysis.Group:analysis.addObject(obj)
                t=definition['temperature'];obj.initialTemperature=str(t['reference_K'])+' K'
                obj.EnableFinalTemperature=True;obj.FinalTemperature=str(t['samples_K'][-1][1])+' K';obj.EnableAmplitude=False
                source=fem.owner._object(new['region']['body_id'])
                obj.References=[(source,tuple(s['name'] for s in trow['subelements'])) for trow in new['region']['targets']] if new['region']['targets'] else []
                new['applied']['temperature_object']=obj.Name
            elif existing:
                if not old or not old.get('applied') or old['applied'].get('temperature_object')!=existing[0].Name:
                    raise ValueError('원 온도 조건을 명시 해제한 뒤 다른 초기 상태를 적용하세요.')
                analysis.removeObject(existing[0])
        if new is None:value['initial_fields'].pop(analysis.Name,None)
        else:
            new['revision']=canonical_hash({k:v for k,v in new.items() if k!='revision'})
            value['initial_fields'][analysis.Name]=new
        fem.owner.write_metadata(value)
    fem._transaction('초기장 '+{'pre.initial.save_draft':'초안 보관','pre.initial.apply':'조건 적용','pre.initial.discard':'수정 취소'}[operation],change)
    return read(fem,analysis)


def freeze(fem,analysis,bodies,model,*,capture_only=False):
    if capture_only:return
    r=record(fem,analysis.Name)
    if r is None:return
    if not r.get('applied') or r['draft']!=r['applied']['native_draft'] or r.get('region')!=r['applied']['region']:
        raise ValueError('초기장에 미적용 초안이 있습니다. 조건 적용 또는 수정 취소 후 진행하세요.')
    # Validate the captured model without recursively collecting it again.
    mesh=fem.owner._object(r['region']['mesh_id']);binding=fem.owner.mesh_bindings.validate(mesh)
    binding={k:v for k,v in binding.items() if k!='source_equivalence'}
    if binding!=r['region']['mesh_binding']:raise ValueError('초기장의 원 메시가 바뀌었습니다.')
    draft=deepcopy(r['applied']['draft']);definition=normalize(model,draft)
    if definition!=r['applied']['definition']:raise ValueError('초기장과 현재 원 재료·구속·기저가 다릅니다. 명시 재적용하세요.')
    model['initial_fields']={'draft':draft,'definition':definition}
    from caelab.adapters.initial_field_deck import program
    model['analysis_steps']=program(model,definition)
