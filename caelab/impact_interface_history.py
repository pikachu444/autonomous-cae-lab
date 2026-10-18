"""Explicit imposed displacement histories over the existing cohesive model.

No material integration or cyclic fatigue model. Existing motion, geometry,
native card helpers and retained frame readers remain the physical owners.
"""
from copy import deepcopy
import math
from .impact_bulk import number
from .impact_damage import geometry
from .impact_bulk_deck import cards,integer,real,append_before_end,_allocator
from .storage import canonical_hash

KEYS={'name','material','node_set','component','time_s','displacement_mm','frame'}


def validate(model,settings):
    rows=settings.get('interface_histories',[])
    if not isinstance(rows,list) or len(rows)>64:raise ValueError('명시 계면 하중 이력은 최대 64개입니다')
    if not rows:return []
    if settings['source'].get('format')!='INP':
        raise ValueError('계면 하중 이력 추가는 INP 변환 경로에서 명시합니다. 원 RAD 카드를 덮지 않습니다')
    for row in rows:
        if not isinstance(row,dict) or set(row)!=KEYS:raise ValueError('계면 이력의 이름·재료·절점 집합·축·시간·변위·기준계를 명시하세요')
        if not all(isinstance(row[key],str) for key in ('name','material','node_set','component','frame')):
            raise ValueError('원 재료·절점 집합·축·기준계 이름을 확인하세요')
    from .impact_model import NAME
    from .impact_initial_state import motion_state
    from .impact_interface import validate as validate_interface,default_control
    materials={row.get('material') for row in rows if isinstance(row,dict)}
    controls={row['material']:row for row in settings.get('interface_controls',[])}
    selected_controls=[controls.get(material,default_control(material)) for material in materials]
    if any(row['reclosure']!='COHESIVE_ONLY' for row in selected_controls):
        raise ValueError('부분 손상 반복 이력은 별도 TYPE24 없이 응집 압축만 명시합니다')
    validate_interface(model,{**settings,'interface_controls':selected_controls})
    fixed=set();velocity_dofs=set()
    for block in model['blocks']:
        if block['card']!='BOUNDARY':continue
        for _,line in block['rows']:
            values=[v.strip().upper() for v in line.split(',')]
            nodes={int(values[0])} if values[0].isdigit() else model['nsets'][values[0]]
            lo=int(values[1]);hi=int(values[2]) if len(values)>2 and values[2] else lo
            fixed.update((n,d) for n in nodes for d in range(lo,hi+1))
    for motion in settings.get('motions',[]):
        _,speeds,_=motion_state(model,motion,settings['gravity_mm_s2'])
        velocity_dofs.update((n,axis+1) for n,speed in speeds.items() for axis,v in enumerate(speed) if v!=0)
    names=set();dofs=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!=KEYS:raise ValueError('계면 이력의 이름·재료·절점 집합·축·시간·변위·기준계를 명시하세요')
        name=row['name']
        if not isinstance(name,str) or not NAME.fullmatch(name) or name in names:raise ValueError('중복 없는 영문 이력 이름을 입력하세요')
        names.add(name)
        if row['component'] not in ('X','Y','Z') or row['frame']!='MODEL_GLOBAL':raise ValueError('계면 이력은 명시 전역 X/Y/Z 병진 변위입니다')
        nodes=model['nsets'].get(row['node_set'])
        if not nodes:raise ValueError('실제 원 절점 집합을 선택하세요')
        elements=[e for e,m in model['assignment'].items() if m==row['material']]
        if not elements or any(model['elements'][e]['type']!='COH3D8' for e in elements):raise ValueError('원 LAW117 계면 재료를 선택하세요')
        upper=set();lower=set()
        for eid in elements:
            paired=geometry(model,eid);upper.update(paired['upper_nodes']);lower.update(paired['lower_nodes'])
        if not upper<=nodes or lower&nodes:raise ValueError('계면 위 대응면 전체를 포함하고 아래 대응면과 분리된 원 절점 집합을 선택하세요')
        times,values=row['time_s'],row['displacement_mm']
        if not isinstance(times,list) or not isinstance(values,list) or not 2<=len(times)<=256 or len(times)!=len(values):raise ValueError('이력의 같은 길이 시간·변위 표 2~256행이 필요합니다')
        for value in times:number(value,'이력 시간 [s]')
        for value in values:number(value,'부과 변위 [mm]')
        if times[0]!=0 or values[0]!=0 or times[-1]!=settings['time']['end_s'] or any(b<=a for a,b in zip(times,times[1:])):
            raise ValueError('이력은 시간0·변위0에서 시작하고 종료 시각까지 엄격히 증가하는 시간을 지정하세요')
        axis='XYZ'.index(row['component']);selected={(n,axis+1) for n in nodes}
        if selected&fixed:raise ValueError('부과 변위와 고정 자유도가 중복됩니다')
        if selected&dofs:raise ValueError('계면 이력의 같은 원 절점·축을 중복 지정할 수 없습니다')
        if selected&velocity_dofs:raise ValueError('같은 자유도의 부과 변위와 초기 속도가 충돌합니다')
        dofs.update(selected)
    return deepcopy(rows)


def apply(text,model,settings):
    rows=validate(model,settings);before=cards(text)
    if rows and any(key.startswith(('/IMPDISP/','/IMPVEL/')) for key in before):
        raise ValueError('기존 부과 운동 카드를 덮거나 이중 적용하지 않습니다')
    allocate=_allocator(before);groups={};addition='';entries=[]
    for row in rows:
        target=row['node_set'];nodes=sorted(model['nsets'][target])
        if target not in groups:
            gid=allocate();groups[target]=gid
            addition+=f'/GRNOD/NODE/{gid}\nHISTORY_{target}\n'
            for start in range(0,len(nodes),10):addition+=''.join(integer(n) for n in nodes[start:start+10])+'\n'
        gid=groups[target];fid=allocate();lid=allocate()
        addition+=f'/FUNCT/{fid}\nHISTORY_{row["name"]}\n'
        addition+=''.join(real(t)+real(u)+'\n' for t,u in zip(row['time_s'],row['displacement_mm']))
        addition+=f'/IMPDISP/{lid}\nHISTORY_{row["name"]}\n'
        addition+=integer(fid)+f'{row["component"]:>10}'+' '*10+integer(0)+integer(gid)+' '*10+integer(0)+'\n'
        addition+=real(1)+real(1)+real(0)+real(settings['time']['end_s'])+'\n'
        entries.append({**deepcopy(row),'nodes':nodes,'native_group_id':gid,'native_function_id':fid,'native_imposed_id':lid})
    effective=append_before_end(text,addition) if rows else text
    from .impact_b import model_identity
    receipt={'model_identity':model_identity(model),'definition_sha256':canonical_hash(rows),'histories':entries,
        'cards':{key:value for key,value in cards(effective).items() if key not in before},
        'kind':'IMPOSED_GLOBAL_DISPLACEMENT','units':{'time':'s','displacement':'mm'},
        'solver_execution':'NOT_PERFORMED','material_integration':'EXISTING_NATIVE_LAW117'}
    verify(effective,model,settings,receipt)
    return effective,receipt


def verify(text,model,settings,receipt):
    from .impact_b import model_identity
    rows=validate(model,settings)
    if model_identity(model)!=receipt['model_identity'] or canonical_hash(rows)!=receipt['definition_sha256']:
        raise ValueError('부과 이력의 원 모델·선택·정의가 변경되었습니다')
    actual=cards(text)
    for key,expected in receipt['cards'].items():
        if actual.get(key)!=expected:raise ValueError('원 부과 이력 카드가 변경되었습니다: '+key)
    if rows and {key for key in actual if key.startswith(('/IMPDISP/','/IMPVEL/'))}!={key for key in receipt['cards'] if key.startswith('/IMPDISP/')}:
        raise ValueError('미확인 부과 운동 카드가 기존 이력과 중복됩니다')



def observe(frames,model,settings,cohesive_receipt,history_receipt):
    """Preserve actual samples; mean DAMA/face change is not a GP constitutive test.

    The fixed TYPE43 producer maps LAW117's four-GP mean traction tensor to
    3DELEM_Stress in global coordinates. Projections below are derived MPa.
    No interpolation, synthetic damage, fatigue law or unobserved-step verdict.
    """
    from .impact_responses import _sample
    from .impact_interface import face_sample
    from .impact_damage import sub,dot,cross,length
    from .evaluation import file_hash
    from .impact_b import model_identity
    rows=validate(model,settings)
    if (history_receipt['model_identity']!=model_identity(model) or
            history_receipt['definition_sha256']!=canonical_hash(rows)):
        raise ValueError('관측 이력의 원 모델·정의가 변경되었습니다')
    times=[raw['time'] for _,raw in frames]
    if any(not math.isfinite(t) for t in times) or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError('원 프레임의 유한·증가 시각을 보존해야 합니다')
    materials={row['material'] for row in rows};elements=[]
    for eid,material in sorted(model['assignment'].items()):
        if material not in materials:continue
        geo=cohesive_receipt.get('geometry',{}).get(str(eid))
        if geo is None:raise ValueError('원 LAW117 대응면 기하가 없습니다')
        normal=geo['normal'];lower=geo['lower_nodes'];upper=geo['upper_nodes']
        tangent=sub(model['nodes'][lower[1]],model['nodes'][lower[0]])
        tangent=[v/length(tangent) for v in tangent];basis=[tangent,cross(normal,tangent),normal]
        samples=[]
        for path,raw in frames:
            reasons=[]
            def selected(quantity,component):
                value,reason=_sample(raw,{'quantity':quantity,'component':component,'identity':eid},model,cohesive_receipt)
                if reason and reason not in reasons:reasons.append(reason)
                return value
            damage=selected('cohesive_damage','scalar')
            tensor=[selected('stress',c) for c in ('xx','xy','xz','yx','yy','yz','zx','zy','zz')]
            cell_ids=raw['CELLS']['ELEMENT_ID']['values'];active_values=raw['CELLS']['EROSION_STATUS']['values']
            active=[a for e,a in zip(cell_ids,active_values) if int(e)==eid]
            neighbors=sorted({e for face in (set(lower),set(upper)) for e,c in model['elements'].items()
                              if c['type']!='COH3D8' and face<=set(c['nodes'])})
            bulk_activity={str(e):[a for i,a in zip(cell_ids,active_values) if int(i)==e] for e in neighbors}
            # Keep raw activity, including absence/deletion. Do not mask it to zero.
            active_state=active[0] if active and all(a==active[0] for a in active) else None
            if active_state!=1:reasons.append('선택 계면 요소의 활성 상태가 확인되지 않았습니다')
            changes={};separations={}
            for component in ('normal','tangent1','tangent2'):
                changes[component],reason=face_sample(raw,model,cohesive_receipt,eid,component,True)
                separations[component],_=face_sample(raw,model,cohesive_receipt,eid,component,False)
                if reason and reason not in reasons:reasons.append(reason)
            positions={int(n):p for n,p in zip(raw['POINTS']['NODE_ID']['values'],raw['points'])}
            corner_change=None;current_basis=None
            if all(n in positions for n in lower+upper):
                corner_change=[sub(sub(positions[b],positions[a]),sub(model['nodes'][b],model['nodes'][a])) for a,b in zip(lower,upper)]
                mid=[[.5*(a+b) for a,b in zip(positions[lo],positions[hi])] for lo,hi in zip(lower,upper)]
                u=sub(mid[1],mid[0]);n=cross(u,sub(mid[3],mid[0]))
                if length(u)>0 and length(n)>0:
                    u=[v/length(u) for v in u];n=[v/length(n) for v in n]
                    current_basis=[u,cross(n,u),n]
            if corner_change is not None and not all(math.isfinite(v) for row in corner_change for v in row):
                corner_change=None;current_basis=None;reasons.append('대응면 변위가 비유한 값입니다')
            def projections(axes):
                if axes is None or any(v is None for v in tensor) or active_state!=1:return None
                n=axes[2];traction=[sum(tensor[i*3+j]*n[j] for j in range(3)) for i in range(3)]
                return {'normal':dot(n,traction),'tangent1':dot(axes[0],traction),'tangent2':dot(axes[1],traction)}
            en,et,_,_=model['materials'][material]['ELASTIC'][0]
            projected=projections(basis);comparison={}
            if projected is not None and damage is not None:
                for component,stiffness in (('normal',en),('tangent1',et),('tangent2',et)):
                    delta=changes[component]
                    if delta is None:continue
                    factor=1. if component=='normal' and delta<0 else 1.-damage
                    expected=factor*stiffness*delta
                    comparison[component]={'mean_surrogate_mpa':expected,'native_projection_minus_surrogate_mpa':projected[component]-expected,
                        'secant_mpa_per_mm':projected[component]/delta if delta!=0 else None}
            samples.append({'time_s':raw['time'],'file':path.name,'sha256':file_hash(path),
                'active':active_state,'native_active_values':active,'adjacent_bulk_activity':bulk_activity,'native_mean_damage':damage,
                'paired_change_mm':changes,'paired_separation_mm':separations,'corner_change_global_mm':corner_change,
                'corner_derived_current_midsurface_basis':current_basis,'native_global_mean_traction_tensor_mpa':tensor,
                'derived_initial_basis_traction_mpa':projected,'derived_current_basis_traction_mpa':projections(current_basis),
                'mean_comparison':comparison,'reasons':reasons})
        valid=[s for s in samples if s['active']==1 and s['native_mean_damage'] is not None
               and len(s['adjacent_bulk_activity'])==2 and all(v==[1] for v in s['adjacent_bulk_activity'].values())]
        damage_steps=[{'before_time_s':a['time_s'],'after_time_s':b['time_s'],
                       'before':a['native_mean_damage'],'after':b['native_mean_damage']}
                      for a,b in zip(valid,valid[1:]) if b['native_mean_damage']<a['native_mean_damage']]
        partial=[s['time_s'] for s in valid if 0<s['native_mean_damage']<1]
        compression=[{'time_s':s['time_s'],'opening_change_mm':s['paired_change_mm']['normal'],
                      'traction_mpa':s['derived_initial_basis_traction_mpa']['normal']}
                     for s in valid if s['paired_change_mm']['normal'] is not None and s['paired_change_mm']['normal']<0
                     and s['derived_initial_basis_traction_mpa'] is not None]
        elements.append({'element_id':eid,'material':material,'initial_basis':basis,'samples':samples,
            'strict_partial_times_s':partial,'damage_decrease_steps':damage_steps,'compression_samples':compression,
            'partial_state':'OBSERVED' if partial else 'NOT_OBSERVED',
            'sampled_damage_nondecrease':'VIOLATED' if damage_steps else 'OBSERVED' if len(valid)>1 and len(valid)==len(samples) else 'UNKNOWN',
            'sampled_initial_basis_compressive_sign':'SIGN_MISMATCH' if any(s['traction_mpa']>0 for s in compression) else
                                       'OBSERVED' if compression and all(s['traction_mpa']<0 for s in compression) else 'UNKNOWN'})
    return {'definition_sha256':history_receipt['definition_sha256'],'model_identity':model_identity(model),
        'declared_histories':deepcopy(history_receipt['histories']),'elements':elements,'qualification':'UNKNOWN','continuous_history':'UNKNOWN_BETWEEN_SAMPLES',
        'basis':'initial paired-face basis and corner-derived current midsurface basis; not solver SCOOR431 basis',
        'comparison':'four-GP mean traction versus paired-corner mean change and mean DAMA; not GP constitutive equality',
        'constitutive_numerical_criterion':'UNKNOWN','stiffness':'secant only, not tangent stiffness','fatigue':'NOT_IMPLEMENTED','native_damage_dissipation':'UNKNOWN_NOT_SYNTHESIZED'}
