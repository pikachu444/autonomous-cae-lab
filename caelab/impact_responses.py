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
                'source_entity':deepcopy(model.get('lineage',{}).get(
                    'nodes' if association=='POINTS' else 'elements',{}).get(str(row['identity']))),
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


def _history_source(snapshot):
    """The common owner supplies the exact retained result; no file/runtime read."""
    import re
    from .storage import check_id
    source=snapshot.get('source')
    if not isinstance(source,dict) or not {'document_id','job_id','input_revision','input_sha256','result_sha256'}<=source.keys():
        raise ValueError('보존된 문서·실행·입력·결과를 먼저 선택하세요')
    for key in ('document_id','job_id','input_revision'):check_id(source[key])
    for key in ('input_sha256','result_sha256'):
        if not isinstance(source[key],str) or not re.fullmatch('[0-9a-f]{64}',source[key]):
            raise ValueError('원 결과와 입력의 정확한 저장 신원이 필요합니다')
    return deepcopy(source)


def _history_semantics(response):
    meta=response.get('metadata',{});measure=response.get('measure') or '';variable=meta.get('native_variable')
    if measure=='native_cumulative_contact_impulse':meaning='NATIVE_CUMULATIVE_SIGNED_PAIR_IMPULSE'
    elif measure=='derived_mean_force_from_native_impulse_secants':meaning='DERIVED_INTERVAL_AVERAGE_PAIR_FORCE'
    elif 'trapezoid' in measure:meaning='DERIVED_SAMPLE_TRAPEZOID_NOT_NATIVE_IMPULSE'
    elif measure=='native_internal_energy_per_volume':meaning='ELEMENT_INTERNAL_ENERGY_DENSITY_NOT_TOTAL_ENERGY'
    elif variable==1:meaning='WHOLE_MODEL_INTERNAL_ENERGY_NOT_ELEMENT_DENSITY'
    elif variable==6:meaning='NATIVE_CURRENT_TOTAL_MASS_NOT_INPUT_ORIGINAL_MASS'
    elif variable==17:meaning='NATIVE_ADDED_MASS_NOT_ORIGINAL_MASS'
    elif variable==18:meaning='NATIVE_ADDED_MASS_PERCENTAGE'
    elif variable in (2,8,9,10,11,12,13,14,15,16,21,22):meaning='INDIVIDUAL_GLOBAL_ENERGY_OR_WORK_NOT_BALANCE_VERDICT'
    elif measure=='derived_original_paired_bulk_face_separation_initial_basis':meaning='DERIVED_PAIRED_SEPARATION_NOT_NATIVE_PENE'
    else:meaning=measure or 'RECORDED_CHANNEL_MEANING_NOT_EXTENDED'
    csv=meta.get('source_artifact','').lower().endswith('.csv')
    native_unit=meta.get('native_unit')
    if csv:
        native_unit=('N mm' if variable in (1,2,8,9,10,11,12,13,14,15,16,21,22) else
            'Mg' if variable in (6,17,19,20) else 'Mg mm/s' if variable in (3,4,5) else response.get('unit'))
    scale=meta.get('value_scale_from_Mg_mm_s',1.)
    conversion='DISPLAY_UNIT_SCALE' if csv else 'RETAINED_VALUE'
    if measure=='derived_mean_force_from_native_impulse_secants':
        conversion='DERIVED_SECANT';scale=None
    elif 'trapezoid' in measure or measure=='sampled_contact_impulse':
        conversion='DERIVED_SAMPLE_TRAPEZOID';scale=None
    return {'physical_meaning':meaning,'origin':meta.get('origin','NATIVE_CONVERTER_OUTPUT' if csv else 'UNKNOWN'),
        'native_unit':native_unit,'display_unit':response.get('unit'),
        'conversion_kind':conversion,'display_scale_from_native':scale,
        'conversion_note':('(J_b - J_a) / (t_b - t_a); support-specific signed mean force, not unit scaling'
            if conversion=='DERIVED_SECANT' else 'trapezoid of retained force samples, not conversion of native cumulative impulse'
            if conversion=='DERIVED_SAMPLE_TRAPEZOID' else None),
        'clock':'RETAINED_CONVERTER_CSV_TIME' if csv else meta.get('clock','RETAINED_ANIMATION_SAMPLE_TIME'),
        'source_row_kind':'CSV_PHYSICAL_LINE' if csv else 'RAW_TH_RECORD_INDEX' if meta.get('source_pin') else 'ANIMATION_FRAME_INDEX',
        'sign':meta.get('sign','retained signed values; no absolute value'),
        'normal_orientation':meta.get('normal_orientation'),'tangent_orientation':meta.get('tangent_orientation'),
        'instantaneous_force':False if 'force_support' in meta else None,
        'producer_source_commit':meta.get('producer_source_commit'),
        'converter_source_commit':'NOT_PROVEN_BY_RELEASE' if csv else 'NOT_APPLICABLE_RAW_TH_READER' if meta.get('source_pin') else None,
        'qualification':'UNKNOWN','decision':'NOT_RELEASED'}


def _history_execution(result):
    # A retained re-read is an operation on existing output, not another solve.
    return {key:deepcopy(result.get(key)) for key in
        ('operation','execution_status','source_execution_status','solver_execution')}


def history_catalog(snapshot):
    """Only already retained channels; no inferred pair, density or mass curve."""
    _history_source(snapshot);result=snapshot.get('result',{});channels=[]
    for name,response in result.get('responses',{}).items():
        if response.get('kind')!='series' or not response.get('axes'):continue
        meta=response.get('metadata',{});selection=meta.get('selection',{})
        if not (selection.get('scope') in ('pair','interface','bulk') or meta.get('native_variable') is not None
                or selection.get('quantity') in QUANTITIES):continue
        channels.append({'response':name,'label':meta.get('label',name),'unit':response.get('unit','단위 미확인'),
            'measure':response.get('measure'),'location':deepcopy(response.get('location')),
            'component':response.get('component'),'selection':deepcopy(selection),
            'pair':deepcopy(meta.get('pair')),'status':meta.get('status','RECORDED'),
            'semantics':_history_semantics(response)})
    initial=deepcopy(snapshot.get('initial_mass_properties'))
    return {'source':deepcopy(snapshot['source']),'channels':channels,'initial_mass_properties':initial,
        'initial_mass_meaning':'INPUT_DERIVED_INITIAL_VOLUME_INTEGRAL_NOT_NATIVE_MASS; unsupported element families remain UNKNOWN',
        **_history_execution(result),'qualification':'UNKNOWN'}


def select_history(snapshot,request):
    """Exact sample endpoints/masks/support, no interpolation or executable use.

    The returned response is a selection capsule for the existing owner, not a
    replacement of its original result. Interval integration is an explicit new
    derived quantity, with a selected-start zero reference and preserved gaps.
    """
    from .storage import canonical_hash
    source=_history_source(snapshot)
    if not isinstance(request,dict) or set(request)!={'response','start_s','end_s','side','transform'}:
        raise ValueError('원 응답·실제 시작/끝 시각·부호 기준·표본 적분 여부를 선택하세요')
    if request['side']!='native':raise ValueError('기록되지 않은 물체별 반력이나 반대 면 부호를 추정하지 않습니다')
    if request['transform'] not in ('identity','sample_trapezoid'):raise ValueError('명시한 원값 또는 표본 적분을 선택하세요')
    begin,end=request['start_s'],request['end_s']
    finite=lambda x:type(x) in (int,float) and math.isfinite(x)
    if not finite(begin) or not finite(end) or begin>end:raise ValueError('유한하고 순서가 맞는 실제 표본 시각을 선택하세요')
    response=snapshot['result'].get('responses',{}).get(request['response'])
    if not isinstance(response,dict) or response.get('kind')!='series':raise ValueError('보존된 이력 응답을 선택하세요')
    raw=response.get('raw_samples',{});times=raw.get('transformed_axis',[]);values=raw.get('transformed_values',[])
    rows=raw.get('source_rows',[]);n=len(times)
    if not n or len(values)!=n or len(rows)!=n or any(not finite(t) for t in times) or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError('원 표본 시각이 누락·중복·비단조이거나 원행이 일치하지 않습니다')
    if any(type(row) is not int or row<0 for row in rows) or len(set(rows))!=n or any(b<=a for a,b in zip(rows,rows[1:])):
        raise ValueError('원행 식별자가 중복·비단조이거나 유효한 원행이 아닙니다')
    if begin not in times or end not in times:raise ValueError('시작과 끝은 실제 표본 시각이어야 합니다. 보간하거나 가장 가까운 값으로 바꾸지 않습니다')
    start,stop=times.index(begin),times.index(end)+1
    quality=raw.get('quality_valid',[finite(v) for v in values]);calculation=raw.get('calculation_valid',quality)
    gaps=raw.get('gap_before',[False]*n);reasons=raw.get('quality_reasons',['']*n)
    if any(len(v)!=n for v in (quality,calculation,gaps,reasons)):raise ValueError('원 표본 마스크의 길이가 다릅니다')
    if any(type(v) is not bool for mask in (quality,calculation,gaps) for v in mask):raise ValueError('원 표본 마스크는 명시한 참/거짓이어야 합니다')
    selected_values=deepcopy(values[start:stop]);selected_times=deepcopy(times[start:stop]);selected_rows=deepcopy(rows[start:stop])
    selected_gaps=[bool(gaps[i]) or i>start and rows[i]!=rows[i-1]+1 for i in range(start,stop)]
    meta=deepcopy(response.get('metadata',{}));support=meta.get('force_support')
    if support is not None and len(support)!=n:raise ValueError('원 힘의 평균 계산 구간이 표본과 다릅니다')
    native_values=meta.get('native_stored_values') or raw.get('native_values') or [None]*n
    if not isinstance(native_values,list) or len(native_values)!=n:raise ValueError('원 저장 채널의 행 수가 선택 응답과 다릅니다')
    if request['transform']=='sample_trapezoid':
        if response.get('measure')!='derived_mean_force_from_native_impulse_secants' or response.get('unit')!='N':
            raise ValueError('표본 적분은 명시된 접촉쌍 구간 평균 힘 [N]에서만 계산합니다')
        if stop-start<2:raise ValueError('표본 적분에는 서로 다른 실제 시각의 힘 표본 둘 이상이 필요합니다')
        from .impact_bulk_results import sampled_integral
        masked=[v if quality[i] and calculation[i] and finite(v) else None for i,v in enumerate(values)]
        selected_values=sampled_integral(selected_times,masked[start:stop],gap_before=selected_gaps)
        meta.update(origin='DERIVED',integration_reference='zero at selected first sample; not a native impulse observation',
            derived_integration='trapezoid of selected retained interval-average force samples',exact_solver_impulse=False)
    packet_response=deepcopy(response);packet_response['raw_samples']={
        key:deepcopy(value[start:stop]) if isinstance(value,list) and len(value)==n else deepcopy(value) for key,value in raw.items()}
    packet_response['raw_samples'].update(transformed_axis=selected_times,transformed_values=selected_values,
        source_rows=selected_rows,gap_before=selected_gaps,quality_valid=deepcopy(quality[start:stop]),
        calculation_valid=deepcopy(calculation[start:stop]),quality_reasons=deepcopy(reasons[start:stop]))
    if request['transform']=='sample_trapezoid':
        packet_response.update(unit='N s',measure='derived_trapezoid_of_selected_mean_force_samples')
        packet_response['raw_samples']['quality_valid']=[finite(v) for v in selected_values]
        packet_response['raw_samples']['calculation_valid']=[finite(v) for v in selected_values]
        packet_response['raw_samples']['quality_reasons']=[reasons[start+i] if finite(v) else
            reasons[start+i] or '힘 표본·연속 구간이 누락되어 이 적분을 계속할 수 없습니다' for i,v in enumerate(selected_values)]
    usable=[i for i,v in enumerate(selected_values) if finite(v) and quality[start+i] and calculation[start+i]]
    packet_response['value']=[selected_values[i] for i in usable]
    packet_response['axes'][0]['values']=[selected_times[i] for i in usable]
    packet_response['source_rows']=[selected_rows[i] for i in usable]
    packet_response['has_calculation_gaps']=len(usable)!=len(selected_values) or any(selected_gaps)
    # Reuse the existing mask/segment construction; include row gaps explicitly.
    segments=[];block=[]
    for i in usable:
        if block and (i!=block[-1]+1 or selected_gaps[i]):segments.append(block);block=[]
        block.append(i)
    if block:segments.append(block)
    lookup={index:position for position,index in enumerate(usable)}
    packet_response['segments']=[{'source_rows':[selected_rows[i] for i in block],
        'rows':[lookup[block[0]],lookup[block[-1]]+1]} for block in segments]
    table=[]
    raw_tokens=raw.get('raw_values',[None]*n)
    if not isinstance(raw_tokens,list) or len(raw_tokens)!=n:raise ValueError('원 저장 token의 행 수가 선택 응답과 다릅니다')
    for i in range(start,stop):
        interval=deepcopy(support[i]) if support is not None else None
        table.append({'source_row':rows[i],'time_s':times[i],'value':values[i],'selected_value':selected_values[i-start],
            'native_stored_value':native_values[i],'raw_token':raw_tokens[i],
            'quality_valid':quality[i],'calculation_valid':calculation[i],'reason':reasons[i],
            'selected_reason':packet_response['raw_samples']['quality_reasons'][i-start],
            'gap_before':selected_gaps[i-start],'force_support':interval,
            'support_crosses_selection':bool(interval and (interval['time_interval_s'][0]<begin or interval['time_interval_s'][1]>end))})
    for key in ('force_support','native_stored_values','byte_ranges','frames','source_rows'):
        if isinstance(meta.get(key),list) and len(meta[key])==n:meta[key]=deepcopy(meta[key][start:stop])
    meta['status']='AVAILABLE' if usable else 'UNKNOWN';meta['selection_request']=deepcopy(request)
    packet_response['metadata']=meta
    selection={'request':deepcopy(request),'source_rows':selected_rows,'time_s':selected_times,
        'quality_valid':deepcopy(packet_response['raw_samples']['quality_valid']),
        'calculation_valid':deepcopy(packet_response['raw_samples']['calculation_valid']),
        'source_quality_valid':deepcopy(quality[start:stop]),'source_calculation_valid':deepcopy(calculation[start:stop]),
        'gap_before':selected_gaps,'original_response_sha256':canonical_hash(response),
        'selected_response_sha256':canonical_hash(packet_response),'semantics':_history_semantics(packet_response)}
    return {'source':{**source,'response':request['response']},'selection':selection,
        'selection_sha256':canonical_hash({'source':source,'selection':selection}),
        'response':packet_response,'rows':table,'qualification':'UNKNOWN',**_history_execution(snapshot['result'])}
