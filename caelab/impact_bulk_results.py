"""B's typed selections, source rows, deletion brackets and sampled integration.

Native stored quantities, converter transformations, and derived quadratures
are distinct. Unknown fields remain empty/masked, never fabricated zeros.
"""
from copy import deepcopy
import math
from .adapters.impact_results import continuity
from .impact_bulk_history import bind, series, pair_provenance, impulse_secants
from .impact_model import NAME
from .impact_interface import face_sample, audit_controls

BULK = {
 'damage_sum':('벌크 손상 합','DAMA','1','native_sum_of_damages_not_unique_INIEVO_state'),
 'active':('벌크 활성/삭제','OFF','1','native_element_activation'),
 'plastic_strain':('누적 소성변형률','PLAS','1','native_plastic_strain'),
 'internal_energy_density':('벌크 내부에너지 밀도','IE','N/mm^2','native_internal_energy_per_volume'),
 'volume':('현재 요소 체적','VOL','mm^3','native_element_volume'),
 'strain_rate':('요소 기록 변형률속도','PLSR','1/s','native_PLSR_not_automatically_failure_EPSD'),
 'stress_xx':('벌크 X 응력','SX','MPa','native_global_Cauchy_stress'),
 'stress_yy':('벌크 Y 응력','SY','MPa','native_global_Cauchy_stress'),
 'stress_zz':('벌크 Z 응력','SZ','MPa','native_global_Cauchy_stress'),
 'stress_xy':('벌크 XY 응력','SXY','MPa','native_global_Cauchy_stress'),
 'stress_yz':('벌크 YZ 응력','SYZ','MPa','native_global_Cauchy_stress'),
 'stress_xz':('벌크 XZ 응력','SXZ','MPa','native_global_Cauchy_stress'),
}
PAIR = ('force','native_impulse','sampled_impulse')
INTERFACE = ('face_separation','face_opening_change','face_slip_change','cohesive_active')


def validate(model,settings):
    rows=settings.get('b_responses',[])
    if not isinstance(rows,list) or len(rows)+len(settings.get('responses',[]))>64:
        raise ValueError('전체 선택 응답은 64개 이하입니다')
    seen={v['name'] for v in settings.get('responses',[])}
    bulk_materials={v['material'] for v in settings.get('bulk_damage',[])}
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'name','scope','identity','quantity','component'}:
            raise ValueError('B 응답은 이름·벌크/계면/접촉쌍·정확한 위치·물리량·성분을 선택하세요')
        name=row['name']; q=row['quantity'];ident=row['identity'];component=row['component']
        if not isinstance(name,str) or not NAME.fullmatch(name) or name in seen or name.startswith('global_'):
            raise ValueError('원 응답과 중복되지 않는 영문 응답 이름이 필요합니다')
        seen.add(name)
        if type(ident) is not int:
            raise ValueError('원 요소 번호 또는 접촉쌍 순서를 선택하세요')
        if row['scope']=='bulk':
            if q not in BULK or component!='scalar' or model['assignment'].get(ident) not in bulk_materials:
                raise ValueError('벌크 응답은 INIEVO를 배정한 정확한 요소에서 선택하세요')
        elif row['scope']=='pair':
            if not 0<=ident<len(settings.get('contacts',[])) or q not in PAIR or component not in ('FNX','FNY','FNZ','FTX','FTY','FTZ'):
                raise ValueError('접촉쌍의 signed 법선/접선 전역 성분을 선택하세요')
        elif row['scope']=='interface':
            if model['elements'].get(ident,{}).get('type')!='COH3D8' or q not in INTERFACE:
                raise ValueError('원 응집 요소와 대응하는 면 응답을 선택하세요')
            allowed=('tangent1','tangent2') if q=='face_slip_change' else ('scalar',) if q=='cohesive_active' else ('normal',)
            if component not in allowed:
                raise ValueError('계면 응답의 초기 기준계 성분을 확인하세요')
        else:
            raise ValueError('벌크·계면·접촉쌍을 구분하세요')


def sampled_integral(times,values,*,gap_before=None):
    """Trapezoid of actual force samples; zero is only an explicit reference."""
    if len(times)!=len(values) or any(not math.isfinite(t) for t in times) or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError('실제 표본 시각/값 길이와 증가 순서를 확인하세요')
    gap_before=list(gap_before or [False]*len(times))
    if len(gap_before)!=len(times):
        raise ValueError('표본 구간 마스크 길이가 다릅니다')
    result=[]; total=0.; broken=False
    for i,value in enumerate(values):
        if value is None or type(value) not in (int,float) or not math.isfinite(value) or gap_before[i]:
            broken=True
        if broken:
            result.append(None)
        else:
            if i:
                total+=.5*(values[i-1]+value)*(times[i]-times[i-1])
            result.append(total)
    return result


def response(times,values,*,unit,label,measure,selection,source_rows=None,reasons=None,gap_before=None,metadata=None):
    if len(times)!=len(values):
        raise ValueError('Selected time and sample lengths differ')
    source_rows=list(range(len(times))) if source_rows is None else source_rows
    gap_before=list(gap_before or [False]*len(times))
    rows=[{'source_row':r,'tokens':[str(t),str(v)],'values':[t,v]} for r,t,v in zip(source_rows,times,values)]
    continuity_data=continuity(rows,1)
    # Split retained values when an excluded independent frame interrupts ordinals.
    selected_index={r:i for i,r in enumerate(continuity_data['source_rows'])}; blocks=[];block=[]
    for r,v,gap in zip(source_rows,values,gap_before):
        if gap or v is None:
            if block:blocks.append(block);block=[]
        if v is not None:block.append(r)
    if block:blocks.append(block)
    continuity_data['segments']=[{'source_rows':b,'rows':[selected_index[b[0]],selected_index[b[-1]]+1]} for b in blocks]
    continuity_data['has_calculation_gaps'] |= any(gap_before)
    result={'kind':'series','unit':unit,'value':[v for v in values if v is not None],
        'axes':[{'name':'time','unit':'s','values':[t for t,v in zip(times,values) if v is not None]}],
        'component':selection['component'],'location':{'kind':selection['scope'],'id':selection['identity']},
        'reduction':'none','frame':'MODEL_GLOBAL','measure':measure,**continuity_data,
        'metadata':{'label':label,'selection':deepcopy(selection),'status':'AVAILABLE' if any(v is not None for v in values) else 'UNKNOWN',
                    **(metadata or {})}}
    if reasons is not None:
        result['raw_samples']['quality_reasons']=list(reasons)
    result['raw_samples']['gap_before']=gap_before
    return result


def deletion_events(times,states,*,source_rows=None,gap_before=None):
    """OFF=0 observation is not solver failure. Missing elements are not deleted."""
    events=[]; last_active=None; uncertain=False
    for i,(t,state) in enumerate(zip(times,states)):
        if (gap_before or [False]*len(times))[i]:
            uncertain=True
        if state is None:
            uncertain=True
        elif state==1:
            if events:
                events.append({'kind':'UNEXPECTED_REACTIVATION','time_s':t,'source_row':(source_rows or list(range(len(times))))[i]})
            last_active=t
        elif state==0 and not any(e['kind']=='FIRST_OBSERVED_DELETION' for e in events):
            events.append({'kind':'FIRST_OBSERVED_DELETION','last_observed_active_s':last_active,
                'first_observed_inactive_s':t,'exact_native_deletion_time_s':None,
                'unobserved_or_missing_interval':uncertain or last_active is None,
                'source_row':(source_rows or list(range(len(times))))[i],
                'solver_failure':False})
    return events


def read_selected(history,frames,model,settings,definition,*,excluded_frames=(),runtime_identity=None,unit_evidence=None):
    validate(model,settings); responses={};records={}; events={};bound=[]
    if history is not None:
        bound=bind(history,definition['outputs'])
    for selected in settings.get('b_responses',[]):
        scope,q,identity=selected['scope'],selected['quantity'],selected['identity']
        meta={'origin':'NATIVE','qualification':'UNKNOWN','decision':'NOT_RELEASED'}
        if scope in ('bulk','pair'):
            times=[r['time_s'] for r in history['samples']] if history else []
            source_rows=[r['source_row'] for r in history['samples']] if history else []
            values=[None]*len(times); reasons=['선택한 native TH 채널이 없습니다']*len(times)
            group=next((g for g in bound if g['kind']==scope and (identity in g['members'] if scope=='bulk' else g['contact_index']==identity)),None)
            if scope=='bulk':
                label,token,unit,measure=BULK[q]
                if group:
                    values=series(history,group,identity,token)
                    states=series(history,group,identity,'OFF')
                    states=[v if v in (0.,1.) else None for v in states]
                    events[str(identity)]=deletion_events(times,states,source_rows=source_rows)
                    reasons=[]
                    for i,(value,state) in enumerate(zip(values,states)):
                        if q=='active':
                            values[i]=state
                        elif state!=1:
                            values[i]=None
                        reasons.append('' if values[i] is not None else '비유한/미기록 채널 또는 비활성 요소')
                meta.update(native_token=token,damage_definition='DAMA remains native sum-of-damages',
                            element=deepcopy(definition['bulk']['elements'].get(str(identity))))
            else:
                label={'force':'접촉쌍 힘','native_impulse':'접촉쌍 원 충격량','sampled_impulse':'접촉쌍 힘 표본 적분'}[q]
                unit='N' if q=='force' else 'N s';measure=q
                raw=series(history,group,group['members'][0],selected['component']) if group else []
                provenance=pair_provenance(history,group,runtime_identity,unit_evidence) if group else None
                meta.update(native_stored_values=raw,pair=deepcopy(group))
                if provenance is None:
                    reasons=['고정 producer·단위·원 채널 번호 대응을 확인할 수 없어 접촉 물리량은 UNKNOWN입니다']*len(times)
                    meta.update(status='UNKNOWN',native_store_semantics='UNVERIFIED')
                else:
                    meta.update(provenance,native_store_semantics=provenance['native_store_semantics'])
                    if q=='native_impulse':
                        values=list(raw);label='접촉쌍 누적 충격량';measure='native_cumulative_contact_impulse'
                    else:
                        values,support=impulse_secants(times,raw,source_rows=source_rows)
                        meta.update(origin='DERIVED',force_support=support,instantaneous_force=False)
                        label='접촉쌍 구간 평균 힘';measure='derived_mean_force_from_native_impulse_secants'
                        if q=='sampled_impulse':
                            values=sampled_integral(times,values)
                            label='접촉쌍 평균 힘 표본 적분';measure='derived_trapezoid_of_sampled_mean_force'
                            meta.update(integration_reference='zero at first retained sample; not a native observation',
                                exact_solver_impulse=False,derived_integration='trapezoid using actual retained TT samples')
                    reasons=['' if value is not None else '구간 표본 부족·누락 또는 비유한 원 충격량으로 계산할 수 없습니다' for value in values]
            meta.update(native_group=deepcopy(group),source_pin=deepcopy(history['source_pin']) if history else None,
                byte_ranges=[r['byte_range'] for r in history['samples']] if history else [],
                excluded_tail=deepcopy(history['excluded']) if history else [],
                failed_source=bool(history and history['failed_source']))
            gap_before=[False]*len(times)
        else:
            times=[raw['time'] for _,raw in frames]
            source_rows=[raw.get('source_ordinal',i) for i,(_,raw) in enumerate(frames)]
            gap_before=[False]+[b!=a+1 for a,b in zip(source_rows,source_rows[1:])] if times else []
            values=[];reasons=[]
            label='응집 활성/삭제' if q=='cohesive_active' else '원 대응 벌크면 '+q
            unit='1' if q=='cohesive_active' else 'mm';measure='native_element_activation' if q=='cohesive_active' else 'derived_original_paired_bulk_face_separation_initial_basis'
            for _,raw in frames:
                if q=='cohesive_active':
                    match=[a for e,a in zip(raw['CELLS']['ELEMENT_ID']['values'],raw['CELLS']['EROSION_STATUS']['values']) if int(e)==identity]
                    value=match[0] if len(match)==1 else None;reason='' if value is not None else '활성 상태가 미기록입니다'
                else:
                    value,reason=face_sample(raw,model,definition['cohesive'],identity,selected['component'],change=q!='face_separation')
                values.append(value);reasons.append(reason)
            if q=='cohesive_active':
                events['interface_'+str(identity)]=deletion_events(times,values,source_rows=source_rows,gap_before=gap_before)
            meta.update(origin='NATIVE' if q=='cohesive_active' else 'DERIVED',
                excluded_frames=deepcopy(list(excluded_frames)),comparison='Not a closest/native contact gap; does not prove contact force',
                geometry=deepcopy(definition['cohesive']['geometry'].get(str(identity))))
        r=response(times,values,unit=unit,label=label,measure=measure,selection=selected,source_rows=source_rows,
                   reasons=reasons,gap_before=gap_before,metadata=meta)
        if history is not None and scope!='interface' and history['excluded']:
            r['has_calculation_gaps']=True
        responses[selected['name']]=r
        records[selected['name']]={'selection':deepcopy(selected),'times_s':times,'values':values,'source_rows':source_rows,
                                   'quality_reasons':reasons,'gap_before':gap_before}
    return responses,{'selections':records,'events':events,'interface_controls':audit_controls(frames,definition['interface']),
                      'bulk_damage_dissipation':'UNKNOWN_NOT_SYNTHESIZED','native_initiation_evolution_states':'NOT_MAPPED_TO_A_VERIFIED_OUTPUT_CHANNEL'}
