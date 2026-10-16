"""Finite observation chains over retained sources; existing covariance engine.

Fixed reference projection, coaxial scalar measures and ONE common time shift
per operand. No uncertain grid, orientation, solver, store or Monte Carlo engine.
"""
from copy import deepcopy
import math
import numpy as np

from .experiment_calibration import factor
from .experiment_uncertainty import (MAX_VARIABLES, MAX_SAMPLES, METADATA,
    calibration_problem, processing_problem, plain, _number, _mask)
from .storage import canonical_hash

KINDS = ('value', 'projection', 'engineering_strain', 'stretch', 'log_strain',
         'nominal_stress', 'cauchy_stress')
ORDERS = ('transform_then_align', 'align_then_transform')
LABELS = {'value':'교정/처리 값', 'projection':'투영 게이지 신장',
    'engineering_strain':'공학 변형률', 'stretch':'동축 신장비',
    'log_strain':'동축 로그 변형률', 'nominal_stress':'공칭 응력', 'cauchy_stress':'동축 Cauchy 응력'}


def _closed(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value)-set(required)-set(optional):
        raise ValueError('관측 변환의 입력 항목이 다릅니다: '+', '.join(required))


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _sum(*terms):
    out = {}
    for scale, gradient in terms:
        for key, value in gradient.items():
            out[key] = out.get(key, 0.) + scale*value
    return {key:value for key,value in out.items() if value != 0.}


def _source_channel(reader, source):
    """Existing exact readers and affine/processing sensitivities, no replay."""
    if source['kind'] == 'result_response':
        ref = source['reference']
        actual = reader.document_result_reference(ref['document_id'], ref['job_id'])
        if actual != ref:
            raise ValueError('관측 변환의 보존 입력/결과 개정이 달라졌습니다.')
        result = reader.document_result(ref['document_id'], ref['job_id'], selection=[source['response']])
        if result.get('execution_status') != 'SUCCEEDED':
            raise ValueError('실패한 원 응답을 성공한 관측값으로 전파하지 않습니다.')
        response = plain(result['responses'][source['response']])
        if response['kind'] not in ('scalar','series'):
            raise ValueError('관측 변환에는 실제 scalar 성분 또는 시간 곡선을 선택하세요.')
        if response.get('calibration') or response.get('mapping',{}).get('calibration'):
            problem = calibration_problem(response)
            raw = response['raw_samples']
            axis = raw.get('transformed_axis', raw.get('axis'))
            if response['kind']=='series' and axis is None:
                raise ValueError('교정 원 표본의 실제 시각이 보존되지 않았습니다.')
            axis_unit = (response.get('axes') or [{}])[0].get('unit')
        else:
            vals = response['value'] if isinstance(response['value'],list) else [response['value']]
            if not 0 < len(vals) <= min(MAX_SAMPLES, MAX_VARIABLES):
                raise ValueError('관측 변환의 원 표본 한도를 넘습니다. 원자료는 유지하며 더 짧은 보존 구간을 선택하세요.')
            valid = response.get('valid_mask', [True]*len(vals))
            if len(valid)!=len(vals):raise ValueError('원값과 품질 mask 길이가 다릅니다.')
            rows = response.get('source_rows', list(range(len(vals))))
            if len(rows)!=len(vals):raise ValueError('원값과 원행 길이가 다릅니다.')
            problem = {'variables':[{'id':'sample:'+str(i),'unit':response['unit'], 'value':v,
                **({'source_row':rows[i]} if 'source_rows' in response else {'sample_index':i})} for i,v in enumerate(vals)],
                'sensitivities':np.eye(len(vals)).tolist(), 'values':vals,
                'included':[bool(ok and _finite(v)) for ok,v in zip(valid,vals)],
                'unit':response['unit'],'original':response,'sample_ids':[str(v) for v in rows]}
            axes = response.get('axes',[])
            if response['kind']=='series' and (len(axes)!=1 or axes[0]['name'] not in ('time','시간')):
                raise ValueError('관측 변환에는 명시한 한 시간축이 필요합니다.')
            axis = axes[0]['values'] if axes else None
            axis_unit = axes[0]['unit'] if axes else None
    elif source['kind']=='processing_channel':
        if hasattr(reader,'data_documents'):
            from .data_processing_document import result as read_processing
            retained=read_processing(reader.data_documents,source['document_id'],source['revision'])
            response=plain(retained['channels'][source['channel']])
            if canonical_hash(response)!=source['channel_sha256']:raise ValueError('보존 처리 채널의 값/원기여가 달라졌습니다.')
            problem=processing_problem(response)
        else:
            from .experiment_analysis_actions import read_analysis_source
            view = read_analysis_source(reader, source=source)
            problem = view['problem'];response = problem['original']
        axis = response['axis']['values'];axis_unit = response['axis']['unit']
        if response['axis']['name'] not in ('time','시간'):raise ValueError('처리 채널의 고정 시간축을 선택하세요.')
    else:
        raise ValueError('실제 보존 결과 응답 또는 처리 채널을 선택하세요.')
    if axis is not None:
        axis = [_number(x,'원 시각')*factor(axis_unit,'s') for x in axis]
        if len(axis)!=len(problem['values']) or any(b<=a for a,b in zip(axis,axis[1:])):
            raise ValueError('원 시각은 값과 같은 길이의 엄격한 증가 축이어야 합니다.')
    return {'problem':problem,'axis_s':axis,'source':deepcopy(source),'response':response}


def template(reader, base):
    """Editable definition with no guessed dimensions, axes or physical values."""
    if base['kind']=='retained_comparison':
        payload=reader.research_reference(base['reference'])
        if payload.get('status')!='AVAILABLE' or payload.get('kind')!='comparison':raise ValueError('저장 비교를 선택하세요.')
        record=payload['comparison'];operands={}
        for side,key in (('A','source'),('B','prediction_source')):
            b=record['binding'][key];ref=reader.document_result_reference(b['document_id'],b['job_id'])
            operands[side]={'channels':{'value':{'kind':'result_response','reference':ref,'response':b['response']}},
                'quantity':'value','parameters':{},'order':'transform_then_align','max_gap_s':None}
    elif base['kind'] in ('result_response','processing_channel'):
        operands={'A':{'channels':{'value':deepcopy(base)},'quantity':'value','parameters':{},
            'order':'transform_then_align','max_gap_s':None}}
    else:raise ValueError('원 응답/처리 채널/저장 비교에서 관측 변환을 만드세요.')
    return {'kind':'observation_chain','base':deepcopy(base),'operands':operands}


class _Inputs:
    def __init__(self):self.rows={};self.order=[]
    def add(self, identity, unit, value, label, **proof):
        if not isinstance(identity,str) or not identity.strip():raise ValueError(label+': 공유 원본 identity를 명시하세요.')
        row={'id':identity,'unit':unit,'value':value,'label':label,**proof}
        if identity in self.rows:
            old=self.rows[identity]
            # Identity is metrological identity, not equal numbers/recipe text.
            if old['unit']!=unit or old['value']!=value or old.get('identity_source')!=proof.get('identity_source'):
                raise ValueError(label+': 같은 source identity의 값·원단위·근거가 충돌합니다.')
        else:
            if len(self.rows)>=MAX_VARIABLES:raise ValueError('공동 불확실 입력 한도를 넘습니다. 더 짧은 구간을 선택하세요.')
            self.rows[identity]=row;self.order.append(identity)
        return identity
    def quantity(self,record,name,target,*,positive=False):
        _closed(record,('value','unit','identity','source'),('interpretation',))
        value=_number(record['value'],name)
        if positive and value<=0:raise ValueError(name+'는 실제 제공된 양수여야 합니다.')
        if not isinstance(record['source'],str) or not record['source'].strip():raise ValueError(name+'의 원본/명시 가정을 입력하세요.')
        key=self.add(record['identity'],record['unit'],value,name,identity_source=record['source'],parameter=name)
        scale = ({'mm^2':1.,'m^2':1e6}.get(record['unit']) if target=='mm^2' else factor(record['unit'],target))
        if scale is None:raise ValueError('면적은 mm^2 또는 m^2로 명시하세요.')
        return value*scale,{key:scale}


def _register_channel(inputs, channel, aliases, side, name):
    p=channel['problem'];keys=[]
    for row in p['variables']:
        raw=row.get('raw_ref')
        # Existing DAG raw_ref already names the exact sample; simple response
        # variables need the exact owner/run/channel namespace as well.
        natural=('raw:'+canonical_hash(raw) if raw else 'source:'+canonical_hash([channel['source'],row['id']]))
        identity=aliases.get(row['id'],natural)
        source_proof=({'declared_shared_source':identity,'calibration_source':row.get('calibration_source')} if row['id'] in aliases else
                      raw if raw else {'source':channel['source'],'variable':row['id']})
        sample_label=('원행 '+str(row['source_row']) if 'source_row' in row else '표본 '+str(row['sample_index']+1) if 'sample_index' in row else '보존 입력')
        label=side+' '+({'force':'힘 F','value':'교정/처리 값'}.get(name,name))+' / '+({'a':'기울기 a','x0':'입력 영점 x0','b':'출력 오프셋 b'}.get(row['id'],sample_label))
        key=inputs.add(identity,row['unit'],row.get('value'),label,identity_source=source_proof,
            source=deepcopy(channel['source']),coefficient=row.get('coefficient',row['id']),
            **({'source_row':row['source_row']} if 'source_row' in row else {}))
        keys.append(key)
    if set(aliases)-{v['id'] for v in p['variables']}:raise ValueError('공유 source 선언이 실제 원값/계수에 속하지 않습니다.')
    return [{'value':v if _finite(v) else None,'gradient':_sum(*[(float(a),{key:1.}) for key,a in zip(keys,g)]),
             'valid':ok and _finite(v),'reason':None}
            for v,g,ok in zip(p['values'],p['sensitivities'],p['included'])]


def _interpolate(rows, axis, query, gap, shifted, segments):
    if axis is None:
        if len(rows)!=1 or shifted:raise ValueError('스칼라 응답에는 시간 offset을 지정하지 마세요.')
        return deepcopy(rows[0]),0.
    j=int(np.searchsorted(axis,query));exact=j<len(axis) and axis[j]==query
    if exact:
        row=deepcopy(rows[j]);slope=0.
        if shifted:row['reason']='시간 offset 평가점이 원 시각 knot에 있어 미분이 유일하지 않습니다.'
        return row,slope
    if j==0 or j==len(axis):
        return {'value':None,'gradient':{},'valid':True,'reason':'시간 offset 평가점이 원 시각 범위 밖입니다.'},0.
    lo,hi=j-1,j
    valid=rows[lo]['valid'] and rows[hi]['valid']
    same_segment=(not segments or any(s['rows'][0]<=lo and hi<s['rows'][1] for s in segments))
    if not valid or not same_segment or axis[hi]-axis[lo]>gap:
        return {'value':None,'gradient':{},'valid':True,'reason':'시간 정렬 구간에 품질 제외 또는 segment gap이 있습니다.'},0.
    w=(query-axis[lo])/(axis[hi]-axis[lo]);a,b=rows[lo],rows[hi]
    reason=a['reason'] or b['reason'];slope=(b['value']-a['value'])/(axis[hi]-axis[lo]) if a['value'] is not None and b['value'] is not None else 0.
    value=(1-w)*a['value']+w*b['value'] if a['value'] is not None and b['value'] is not None else None
    return {'value':value,'gradient':_sum((1-w,a['gradient']),(w,b['gradient'])),
            'valid':True,'reason':reason},slope


def transform(channels, definition, parameters):
    """Explicit analytic value derivatives of the selected physical profile."""
    q=definition['quantity'];reason=next((v['reason'] for v in channels.values() if v['reason']),None)
    valid=all(v['valid'] for v in channels.values())
    if any(v['value'] is None for v in channels.values()):return {'value':None,'gradient':{},'valid':valid,'reason':reason or '원값 없음'}
    if q=='value':return deepcopy(channels['value'])
    g=0.;dg={}
    if q in ('projection','engineering_strain','stretch','log_strain','cauchy_stress'):
        n=definition['direction']
        for i,axis in enumerate('xyz'):
            a,b=channels['uA'+axis],channels['uB'+axis]
            g+=n[i]*(b['value']-a['value']);dg=_sum((1,dg),(-n[i],a['gradient']),(n[i],b['gradient']))
    if q=='projection':value,gradient=g,dg
    elif q in ('engineering_strain','stretch','log_strain','cauchy_stress'):
        L,dL=parameters['L0'];stretch=1+g/L
        de=_sum((1/L,dg),(-g/L**2,dL))
        if stretch<=0:
            return {'value':None,'gradient':{},'valid':valid,'reason':'lambda는 양수여야 합니다. 원 성분과 mask는 보존합니다.'}
        if q=='engineering_strain':value,gradient=g/L,de
        elif q=='stretch':value,gradient=stretch,de
        elif stretch<=0:
            return {'value':None,'gradient':{},'valid':valid,'reason':'lambda가 양수가 아니어서 로그/동축 Cauchy 변환을 계산할 수 없습니다.'}
        elif q=='log_strain':value,gradient=math.log(stretch),_sum((1/stretch,de))
    if q in ('nominal_stress','cauchy_stress'):
        F=channels['force']['value'];dF=channels['force']['gradient'];A,dA=parameters['A0']
        nominal=F/A;dP=_sum((1/A,dF),(-nominal/A,dA))
        if q=='nominal_stress':value,gradient=nominal,dP
        else:
            J,dJ=parameters['J'];value=nominal*stretch/J
            gradient=_sum((stretch/J,dP),(nominal/J,de),(-value/J,dJ))
    if not math.isfinite(value) or any(not math.isfinite(x) for x in gradient.values()):
        return {'value':None,'gradient':{},'valid':valid,'reason':'관측 변환의 값/민감도가 유한하지 않습니다.'}
    return {'value':value,'gradient':gradient,'valid':valid,'reason':reason}


def _operand(reader, inputs, definition, target, side):
    _closed(definition,('channels','quantity','parameters','order','max_gap_s'),
        ('direction','basis','reference_points_mm','protocol','time_offset','shared_identities'))
    q=definition['quantity']
    if q not in KINDS or definition['order'] not in ORDERS:raise ValueError('지원하는 관측량과 저장할 연산 순서를 선택하세요.')
    needed=({'value'} if q=='value' else {'force'} if q=='nominal_stress' else
            {'u'+p+a for p in 'AB' for a in 'xyz'}|({'force'} if q=='cauchy_stress' else set()))
    if set(definition['channels'])!=needed:raise ValueError(LABELS[q]+'에 필요한 실제 원 성분을 모두 선택하세요.')
    if q not in ('value','nominal_stress'):
        n=definition.get('direction');points=definition.get('reference_points_mm')
        if not isinstance(n,list) or len(n)!=3 or any(not _finite(x) for x in n) or abs(sum(x*x for x in n)-1)>1e-10:
            raise ValueError('고정 방향 n은 실제 제공된 단위 벡터여야 합니다.')
        if not isinstance(definition.get('basis'),str) or not definition['basis'].strip():raise ValueError('고정 방향과 변위 성분의 공통 기저를 명시하세요.')
        if not isinstance(points,list) or len(points)!=2 or any(not isinstance(p,list) or len(p)!=3 or any(not _finite(x) for x in p) for p in points):
            raise ValueError('두 기준점의 고정 원좌표 [mm]를 명시하세요.')
        if points[0]==points[1]:raise ValueError('두 기준점의 원좌표가 같습니다.')
    if q=='cauchy_stress' and definition.get('protocol')!='uniaxial_coaxial_declared':
        raise ValueError('scalar Cauchy 변환은 힘·게이지·면적축이 같은 단축/동축 protocol을 명시하세요.')
    names=({'L0'} if q in ('engineering_strain','stretch','log_strain') else
           {'A0'} if q=='nominal_stress' else {'L0','A0','J'} if q=='cauchy_stress' else set())
    if set(definition['parameters'])!=names:raise ValueError('선택한 관측량의 실제 L0/A0/J 입력을 확인하세요.')
    params={name:inputs.quantity(definition['parameters'][name],name,{'L0':'mm','A0':'mm^2','J':'1'}[name],positive=True) for name in sorted(names)}
    if 'J' in params:
        record=definition['parameters']['J']
        if record.get('interpretation') not in ('measured','assumed_incompressible'):
            raise ValueError('J는 실측 또는 명시한 비압축 가정인지 지정하세요. J=1을 자동 가정하지 않습니다.')
        if record['interpretation']=='assumed_incompressible' and params['J'][0]!=1:
            raise ValueError('비압축 가정의 J는 사용자가 명시한 1이어야 합니다.')
    offset,dshift=(0.,{})
    shifted='time_offset' in definition
    if shifted:offset,dshift=inputs.quantity(definition['time_offset'],side+' 공통 시간 offset','s')
    loaded={};data={};axes={};segments={}
    shared=definition.get('shared_identities',{})
    if set(shared)-needed:raise ValueError('공유 source 선언의 채널이 다릅니다.')
    for name in sorted(needed):
        channel=_source_channel(reader,definition['channels'][name]);loaded[name]=channel
        frame=channel['response'].get('frame',channel['response'].get('metadata',{}).get('frame'))
        if q not in ('value','nominal_stress') and frame not in (None,'UNKNOWN','UNSPECIFIED',definition['basis']):
            raise ValueError(name+'의 원 기저와 선언한 고정 방향 기저가 다릅니다.')
        data[name]=_register_channel(inputs,channel,shared.get(name,{}),side,name)
        target_unit=('N' if name=='force' else 'mm' if name.startswith('u') else channel['problem']['unit'])
        scale=factor(channel['problem']['unit'],target_unit)
        for row in data[name]:
            if row['value'] is not None and _finite(row['value']):row['value']*=scale
            row['gradient']=_sum((scale,row['gradient']))
        axes[name]=channel['axis_s'];segments[name]=channel['response'].get('segments',[])
    time_dependent=any(axis is not None for axis in axes.values())
    gap=_number(definition['max_gap_s'],'허용 정렬 간격 [s]') if time_dependent else math.inf
    if gap<=0:raise ValueError('허용 정렬 간격은 실제 양수로 명시하세요.')
    if definition['order']=='transform_then_align':
        axis=next(iter(axes.values()))
        if any(v!=axis for v in axes.values()):raise ValueError('변환 후 정렬에는 같은 원 시각을 쓰는 성분이 필요합니다. 정렬 후 변환을 선택하세요.')
        count=len(next(iter(data.values())))
        if any(len(rows)!=count for rows in data.values()):raise ValueError('원 성분 표본 수가 다릅니다.')
        physical=[transform({name:rows[i] for name,rows in data.items()},definition,params) for i in range(count)]
        out=[]
        for t in target:
            row,slope=_interpolate(physical,axis,t+offset,gap,shifted,next(iter(segments.values())))
            # A transformed sample is valid only if ALL source segments permit it.
            if axis is not None:
                for name in data:
                    checked,_=_interpolate(data[name],axis,t+offset,gap,shifted,segments[name])
                    if checked['reason'] and 'knot' not in checked['reason']:row['reason']=checked['reason'];row['value']=None
            row['gradient']=_sum((1,row['gradient']),(slope,dshift));out.append(row)
    else:
        out=[]
        for t in target:
            current={}
            for name,rows in data.items():
                row,slope=_interpolate(rows,axes[name],t+offset,gap,shifted,segments[name])
                row['gradient']=_sum((1,row['gradient']),(slope,dshift));current[name]=row
            out.append(transform(current,definition,params))
    unit=(next(iter(loaded.values()))['problem']['unit'] if q=='value' else 'mm' if q=='projection' else 'MPa' if q in ('nominal_stress','cauchy_stress') else '1')
    return out,unit,plain({name:{'source':c['source'],'original':c['response'],'source_problem':c['problem']} for name,c in loaded.items()})


def read_problem(reader, source, *, plan_mask=None):
    _closed(source,('kind','base','operands'))
    if source['kind']!='observation_chain':raise ValueError('관측 변환 입력을 선택하세요.')
    base=source['base'];difference=base['kind']=='retained_comparison'
    if difference:
        from .experiment_comparison_uncertainty import read_problem as read_comparison
        original=read_comparison(reader,base['reference'],plan_mask=plan_mask)
        target=original['original']['axis'];included=original['included'];refs=original['operand_references']
        expected={'A','B'}
    else:
        c=_source_channel(reader,base);p=c['problem'];count=len(p['values'])
        target={'name':'time' if c['axis_s'] is not None else '표본 순서','unit':'s' if c['axis_s'] is not None else '1',
                'values':c['axis_s'] if c['axis_s'] is not None else [0.]*count}
        included=[a and b for a,b in zip(p['included'],_mask(plan_mask,count,'Plan mask'))]
        original=plain(p);refs={'A':base.get('reference')};expected={'A'}
    if set(source['operands'])!=expected:raise ValueError('원자료 또는 원 비교의 A/B 피연산자와 변환이 다릅니다.')
    if len(target['values'])>MAX_SAMPLES:raise ValueError('관측 변환 표본 한도를 넘습니다.')
    times=[_number(t,'고정 target 시각')*(factor(target['unit'],'s') if target['unit']!='1' else 1.) for t in target['values']]
    inputs=_Inputs();outputs={};proofs={};unit=None
    for side in sorted(expected):
        rows,u,proof=_operand(reader,inputs,source['operands'][side],times,side)
        if unit is not None and unit!=u:raise ValueError('B−A는 같은 관측량과 변환 후 단위를 선택하세요.')
        if difference and source['operands'][side]['quantity']!=source['operands']['A']['quantity']:
            raise ValueError('B−A의 두 관측 변환 물리량이 다릅니다.')
        if difference and source['operands'][side]['quantity'] not in ('value','nominal_stress') and any(source['operands'][side].get(k)!=source['operands']['A'].get(k) for k in ('basis','direction')):
            raise ValueError('B−A의 고정 방향과 공통 기저가 다릅니다.')
        outputs[side]=rows;proofs[side]=proof;unit=u
    values=[];gradients=[];reasons=[]
    for i,ok in enumerate(included):
        a=outputs['A'][i];b=outputs.get('B',[None]*len(included))[i]
        reason=a['reason'] or (b['reason'] if b else None)
        if not a['valid'] or b and not b['valid']:reason=reason or '원 관측 성분의 품질/계산 mask에서 제외되었습니다.'
        value=(b['value']-a['value'] if b else a['value']) if a['value'] is not None and (not b or b['value'] is not None) else None
        g=_sum((-1 if b else 1,a['gradient']), *(([(1,b['gradient'])]) if b else []))
        values.append(value);reasons.append(reason)
        gradients.append([None if reason else g.get(key,0.) for key in inputs.order])
    return {'kind':'observation_chain','comparison_difference':difference,
        'variables':[inputs.rows[key] for key in inputs.order], 'sensitivities':gradients,
        'included':included,'sample_ids':['observation:'+str(i) for i in range(len(values))],
        'values':values,'unit':unit,'metadata':{**{k:'UNKNOWN' for k in METADATA},
            'measure':LABELS[source['operands']['A']['quantity']], 'frame':source['operands']['A'].get('basis','retained'),
            'direction':source['operands']['A'].get('direction','UNKNOWN')},
        'original':{'axis':deepcopy(target),'base_problem':original,'operand_sources':proofs},
        'operand_values':{side:[r['value'] for r in rows] for side,rows in outputs.items()},
        'operand_references':refs,'row_reasons':reasons,'source':deepcopy(source),
        'coefficient_basis':'analytic chain; declared physical transform/order; exact interior piecewise-linear slopes',
        'calibration_reapplied':False,'supplied_output_uncertainty':[],
        'limitations':['fixed unit direction, reference coordinates and source/target sample grids',
            'projection is not actual distance stretch under general rotation/shear',
            'scalar Cauchy only for declared uniaxial coaxial protocol',
            'local first-order propagation; no distribution, normality or confidence interval']}


def propagate(problem, specification):
    from .experiment_uncertainty import propagate as existing
    spec=deepcopy(specification);coverage=spec.pop('output_coverage_factor',None)
    p=deepcopy(problem);p['kind']='linearized_observation_chain'
    result=existing(p,spec);a=result['experiment_analysis'];a['source_problem']=deepcopy(problem)
    a['scope']='first_order_declared_observation_chain_conditional_on_fixed_direction_and_grids'
    a['limitations']=deepcopy(problem['limitations']);a['unsupported_judgments']=['uncertain orientation/full 3D F tensor','individual stochastic sample timestamps']
    if coverage is not None and _number(coverage,'출력 포함인자 k')<=0:raise ValueError('출력 포함인자 k는 양수여야 합니다.')
    for i,row in enumerate(a.get('rows',[])):
        if problem['included'][i] and problem['row_reasons'][i]:row.update(status='UNKNOWN',reason=problem['row_reasons'][i])
        row['expanded_uncertainty']=row['standard_uncertainty']*coverage if coverage is not None and row['standard_uncertainty'] is not None else None
        row['coverage_factor']=coverage
    a['output_coverage_factor']=coverage;a['expanded_interpretation']='supplied k times local standard uncertainty; no confidence probability inferred'
    return result
