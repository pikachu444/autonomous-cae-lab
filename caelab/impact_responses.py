"""Explicit, exact FE locations; selected native samples and separately derived values."""
import math
from copy import deepcopy

QUANTITIES={
 'displacement':('변위','POINTS','Displacement','mm',('X','Y','Z'),'displacement'),
 'velocity':('속도','POINTS','Velocity','mm/s',('X','Y','Z'),'velocity'),
 'acceleration':('가속도','POINTS','Acceleration','mm/s^2',('X','Y','Z'),'acceleration'),
 'contact_force':('절점 접촉력','POINTS','Contact_Forces','N',('X','Y','Z'),'all_contact_nodal_force'),
 'contact_impulse':('접촉력 표본 적분','POINTS','Contact_Forces','N s',('X','Y','Z'),'sampled_contact_impulse'),
 'stress':('응력','CELLS','3DELEM_Stress','MPa',('xx','xy','xz','yx','yy','yz','zx','zy','zz'),'Cauchy_stress'),
 'cohesive_damage':('응집 손상','CELLS','3DELEM_Damage','1',('scalar',),'LAW117_mean_damage'),
 'cohesive_opening':('응집 면 분리 변화','CELLS',None,'mm',('normal',),'derived_initial_basis_separation_change'),
 'cohesive_slip':('응집 면 접선 변화','CELLS',None,'mm',('tangent1','tangent2'),'derived_initial_basis_separation_change'),
}


def validate(model,rows):
    from .impact_model import NAME
    if not isinstance(rows,list) or len(rows)>64:raise ValueError('선택 응답은 최대 64개입니다')
    seen=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'name','quantity','identity','component'}:
            raise ValueError('응답 이름·물리량·원 절점/요소·성분을 선택하세요')
        if not isinstance(row['name'],str) or not NAME.fullmatch(row['name']) or row['name'] in seen or row['name'].startswith('global_'):
            raise ValueError('응답의 영문 이름은 중복 없이 입력하세요')
        seen.add(row['name'])
        declaration=QUANTITIES.get(row['quantity'])
        if not declaration or row['component'] not in declaration[4]:raise ValueError('지원 물리량의 정확한 성분을 선택하세요')
        ids=model['nodes'] if declaration[1]=='POINTS' else model['elements']
        if type(row['identity']) is not int or row['identity'] not in ids:raise ValueError('원 메시의 절점/요소 번호를 선택하세요')
        if row['quantity'].startswith('cohesive_') and model['elements'][row['identity']]['type']!='COH3D8':
            raise ValueError('응집 응답은 LAW117을 배정한 COH3D8 요소에서 선택하세요')


def _sample(raw,row,model,damage):
    q=row['quantity'];_,association,array,_,components,_=QUANTITIES[q]
    ident=row['identity'];index=components.index(row['component'])
    cells=raw['CELLS'];eid=[int(v) for v in cells['ELEMENT_ID']['values']]
    active=cells['EROSION_STATUS']['values']
    if q.startswith('cohesive_') and str(ident) not in damage.get('elements',{}):
        return None,'선택 요소에 보존된 LAW117 적용이 없습니다'
    if q in ('cohesive_opening','cohesive_slip'):
        from .impact_damage import sub,dot,length,cross
        positions={int(n):p for n,p in zip(raw['POINTS']['NODE_ID']['values'],raw['points'])}
        geo=damage['geometry'][str(ident)]
        matching=[i for i,e in enumerate(eid) if e==ident]
        if not matching or any(active[i]!=1 for i in matching):return None,'응집 요소가 누락되거나 소실됐습니다'
        if any(n not in positions for n in geo['lower_nodes']+geo['upper_nodes']):return None,'대응 절점의 현재 좌표가 누락됐습니다'
        normal=geo['normal'];lower=geo['lower_nodes'];upper=geo['upper_nodes']
        tangent=sub(model['nodes'][lower[1]],model['nodes'][lower[0]])
        tangent=[x/length(tangent) for x in tangent]
        direction=normal if q=='cohesive_opening' else tangent if index==0 else cross(normal,tangent)
        values=[dot(sub(sub(positions[b],positions[a]),sub(model['nodes'][b],model['nodes'][a])),direction)
                for a,b in zip(lower,upper)]
        return sum(values)/4,''
    identities=raw[association].get('NODE_ID' if association=='POINTS' else 'ELEMENT_ID',{}).get('values',[])
    matches=[i for i,v in enumerate(identities) if int(v)==ident]
    if not matches:return None,'선택한 원 절점/요소가 이 프레임에 없습니다'
    if association=='POINTS':
        used={n for i,conn in enumerate(raw['cells']) if active[i]==1 for n in conn}
        if any(i not in used for i in matches):return None,'선택 절점에 활성 요소가 없습니다'
    elif any(active[i]!=1 for i in matches):return None,'선택 요소가 소실됐습니다'
    item=raw[association].get(array)
    if item is None:
        return None,'선택한 native 배열/성분이 기록되지 않았습니다'
    if item['components']!=len(components):return None,'native 성분 수가 선언과 다릅니다'
    tuples=[item['values'][i*item['components']:(i+1)*item['components']] for i in matches]
    if any(len(v)!=len(components) or not all(math.isfinite(x) for x in v) for v in tuples):
        return None,'native 응답이 비유한 값이거나 잘렸습니다'
    # Quadratic visualization may repeat an FE ID. Do not average different
    # integration/display values into an invented elemental result.
    if any(v!=tuples[0] for v in tuples[1:]):return None,'동일 원 요소의 표시 셀 값이 서로 달라 단일 값으로 축약하지 않습니다'
    return tuples[0][index],''


def read_selected(frames,model,rows,damage):
    from .evaluation import file_hash
    from .adapters.impact_results import continuity
    validate(model,rows);responses={};records={}
    times=[raw['time'] for _,raw in frames]
    if not times or any(b<=a for a,b in zip(times,times[1:])):raise ValueError('원 프레임 시간 순서를 확인하세요')
    sources=[{'file':path.name,'sha256':file_hash(path),'time_s':raw['time']} for path,raw in frames]
    for row in rows:
        quantity=row['quantity'];label,association,_,unit,_,measure=QUANTITIES[quantity]
        samples=[_sample(raw,row,model,damage) for _,raw in frames]
        native_values=[v for v,_ in samples];values=list(native_values);reasons=[r for _,r in samples]
        derived=quantity in ('contact_impulse','cohesive_opening','cohesive_slip')
        if quantity=='contact_impulse':
            # An integral is unavailable after any missing interval. Never
            # bridge a gap or restart it at an unmarked zero.
            integral=0.;broken=False
            for i,value in enumerate(native_values):
                if value is None:broken=True
                if broken:values[i]=None;reasons[i]=reasons[i] or '앞선 힘 표본 누락으로 적분을 이어갈 수 없습니다'
                elif i==0:values[i]=0.
                else:
                    integral+=(native_values[i-1]+value)*.5*(times[i]-times[i-1]);values[i]=integral
        raw_rows=[{'source_row':i,'tokens':[str(t),str(v)],'values':[t,v]} for i,(t,v) in enumerate(zip(times,values))]
        response={'kind':'series','unit':unit,'value':[v for v in values if v is not None],
            'axes':[{'name':'time','unit':'s','values':[t for t,v in zip(times,values) if v is not None]}],
            'component':row['component'],'measure':measure,
            'frame':'INITIAL_INTERFACE_FIXED_BASIS' if quantity in ('cohesive_opening','cohesive_slip') else 'MODEL_GLOBAL',
            'location':{'kind':'node' if association=='POINTS' else 'element','id':row['identity']},
            'reduction':'none',**continuity(raw_rows,1),
            'metadata':{'label':label+' '+str(row['identity'])+' '+row['component'],'selection':deepcopy(row),
                'origin':'DERIVED' if derived else 'NATIVE','frames':sources,
                'status':'AVAILABLE' if any(v is not None for v in values) else 'UNKNOWN',
                'limitations':(['All-contact nodal resultant; no pair identity'] if quantity.startswith('contact_') else [])}}
        response['raw_samples']['quality_reasons']=reasons
        response['raw_samples']['native_values']=native_values
        if quantity=='contact_impulse':
            response['metadata'].update(integration='trapezoid of animation samples',origin_time_s=times[0],
                origin_zero='integral reference, not native impulse',sampling='No solver-step peak/impulse claim')
        if quantity in ('cohesive_opening','cohesive_slip'):
            response['metadata'].update(geometry=deepcopy(damage['geometry'][str(row['identity'])]),
                reference='effective initial coordinates after declared translations',
                comparison='mean paired-corner separation change; not native integration-point opening or closest contact gap')
        responses[row['name']]=response
        records[row['name']]={'selection':deepcopy(row),'times_s':times,'values':values,'reasons':reasons,'native_values':native_values}
    return responses,records
