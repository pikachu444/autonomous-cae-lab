"""Finite signed stress histories, explicit S-N calibration and retained cycle rows."""
from copy import deepcopy
import importlib.util
import math
from pathlib import Path
from .storage import canonical_hash
from .execution_control import check_cancelled

BACKEND='damage.rainflow'
REF_KEYS={'document_id','job_id','input_revision','input_sha256','result_sha256'}


def default_settings():
    return {'source':None,'sn_curve':[],
        'calibration':{'reference':'','mean_min_mpa':None,'mean_max_mpa':None,
            'temperature_min_k':None,'temperature_max_k':None,'conditions':''},
        'temperature_k':None,'repeat_block':False}


def finite(value,label,positive=False):
    if type(value) not in (int,float) or not math.isfinite(value) or positive and value<=0:
        raise ValueError(label+'에 유한한 '+('양수' if positive else '수')+'를 입력하세요')
    return float(value)


def validate_settings(settings):
    if not isinstance(settings,dict) or set(settings)!=set(default_settings()):
        raise ValueError('반복하중 입력에는 보존 응력 선택과 S–N 시험 자료가 필요합니다')
    source=settings['source']
    if (not isinstance(source,dict) or set(source)!={'result','response','title'} or
        not isinstance(source['result'],dict) or set(source['result'])!=REF_KEYS or
        not isinstance(source['response'],str) or not source['response']):
        raise ValueError('저장된 실제 응력 이력을 선택하세요')
    from .research_operations import validate_result_reference
    validate_result_reference(source['result'])
    curve=settings['sn_curve']
    if not isinstance(curve,list) or not 2<=len(curve)<=10000: raise ValueError('S–N 시험점을 두 개 이상 입력하세요')
    last=None
    for row in curve:
        if not isinstance(row,dict) or set(row)!={'amplitude_mpa','cycles'}:raise ValueError('S–N 진폭 [MPa]과 사이클 수를 입력하세요')
        a=finite(row['amplitude_mpa'],'응력 진폭',True);n=finite(row['cycles'],'사이클 수',True)
        if last and (a<=last[0] or n>=last[1]):raise ValueError('진폭은 증가, 수명 사이클 수는 감소하는 순서로 입력하세요')
        last=(a,n)
    c=settings['calibration']
    if not isinstance(c,dict) or set(c)!=set(default_settings()['calibration']):raise ValueError('시험 조건을 확인하세요')
    if any(not isinstance(c[k],str) or not c[k].strip() for k in ('reference','conditions')):
        raise ValueError('S–N 자료 출처와 적용 시험 조건을 적으세요')
    for prefix,positive in (('mean',False),('temperature',True)):
        suffix='mpa' if prefix=='mean' else 'k'
        lo=finite(c[prefix+'_min_'+suffix],prefix+' 최소',positive)
        hi=finite(c[prefix+'_max_'+suffix],prefix+' 최대',positive)
        if lo>hi:raise ValueError('시험 조건의 최소·최대를 확인하세요')
    finite(settings['temperature_k'],'이력의 평가 온도 [K]',True)
    if type(settings['repeat_block']) is not bool:raise ValueError('반복 블록 가정을 명시하세요')
    return deepcopy(settings)


def stress_history(response):
    if not isinstance(response,dict) or response.get('kind')!='series':
        raise ValueError('공간 최대값이 아닌 한 위치의 부호 있는 응력 이력을 선택하세요')
    if response.get('unit') not in ('Pa','MPa') or response.get('component') not in ('xx','yy','zz','11','22','33'):
        raise ValueError('Pa/MPa의 명시 수직 응력 성분이 필요합니다. 등가응력/절댓값/전단은 이 경로의 수명으로 환산하지 않습니다')
    if response.get('reduction','none') not in ('none','NONE',None):
        raise ValueError('축약하지 않은 원 응력 이력을 선택하세요')
    if response.get('measure') not in ('Cauchy_stress','cauchy_stress','infinitesimal_Cauchy','engineering_stress','nominal_stress'):
        raise ValueError('원 Data/모델에서 응력 측도를 명시하고 저장하세요')
    if not response.get('frame') or str(response['frame']).upper().startswith('UNKNOWN') or not response.get('location'):
        raise ValueError('원 응력의 고정 기준계와 위치를 명시하세요')
    values=response.get('value');axes=response.get('axes',[])
    if not isinstance(values,list) or not 3<=len(values)<=1000000 or len(axes)!=1:
        raise ValueError('하나의 실제 시간축과 3점 이상의 응력이 필요합니다')
    times=axes[0].get('values')
    if axes[0].get('name')!='time' or axes[0].get('unit')!='s' or not isinstance(times,list) or len(times)!=len(values):
        raise ValueError('물리 시간 [s] 원 이력만 사용합니다. 하중계수/인덱스를 시간으로 바꾸지 않습니다')
    values=[finite(v,'원 응력') for v in values];times=[finite(v,'원 시간') for v in times]
    if any(b<=a for a,b in zip(times,times[1:])):raise ValueError('원 시간은 엄격히 증가해야 합니다')
    if response.get('has_calculation_gaps') or len(response.get('segments',[]))>1:
        raise ValueError('누락·제외 구간을 이어 붙여 사이클을 만들 수 없습니다. 원 Data의 구간을 수리하세요')
    raw=response.get('raw_samples',{})
    for key in ('quality_valid','calculation_valid'):
        if key in raw and any(v is not True for v in raw[key]):raise ValueError('원 이력에 무효/제외 행이 있습니다')
    if response.get('mask') is not None and any(v is not True for v in response['mask']):
        raise ValueError('제외 행이 있는 원 이력은 그대로 계산하지 않습니다')
    factor=1e-6 if response['unit']=='Pa' else 1.
    return times,[v*factor for v in values],factor


def resolved_adapter(workbench,settings):
    """No private payload in public drafts: obtain trusted detached bytes here."""
    validate_settings(settings)
    from .research_operations import _resolve
    ref=settings['source']['result']
    retained=_resolve(ref,workbench.document_read,workbench.document_result)
    if retained.get('execution_status')!='SUCCEEDED' or retained.get('prediction_status') or 'candidates' in retained:
        raise ValueError('성공한 실제 이력만 선택하세요. 예측/후보 집계는 응력 이력이 아닙니다')
    read=workbench.document_result(ref['document_id'],ref['job_id'],selection=[settings['source']['response']])
    response=deepcopy(read['responses'][settings['source']['response']])
    stress_history(response)
    _resolve(ref,workbench.document_read,workbench.document_result)
    return FatigueAdapter(response,deepcopy(settings['source']))


def _counter():
    path=Path(__file__).resolve().parents[1]/'third_party/rainflow/rainflow.py'
    spec=importlib.util.spec_from_file_location('caelab_pinned_rainflow',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.extract_cycles


def analyze(settings,response):
    s=validate_settings(settings);times,stress,factor=stress_history(response)
    table=s['sn_curve'];c=s['calibration'];cycles=[];partial=0.;unknown=0
    def life(amplitude):
        if not table[0]['amplitude_mpa']<=amplitude<=table[-1]['amplitude_mpa']:return None
        for low,high in zip(table,table[1:]):
            if low['amplitude_mpa']<=amplitude<=high['amplitude_mpa']:
                fraction=math.log(amplitude/low['amplitude_mpa'])/math.log(high['amplitude_mpa']/low['amplitude_mpa'])
                return math.exp(math.log(low['cycles'])+fraction*math.log(high['cycles']/low['cycles']))
    for index,(span,mean,count,start,end) in enumerate(_counter()(stress)):
        check_cancelled()
        amplitude=span/2;reason=''
        n=life(amplitude)
        if n is None:reason='응력 진폭이 S–N 시험 범위를 벗어납니다'
        if not c['mean_min_mpa']<=mean<=c['mean_max_mpa']:reason='평균 응력이 시험 조건을 벗어납니다'
        if not c['temperature_min_k']<=s['temperature_k']<=c['temperature_max_k']:reason='평가 온도가 시험 조건을 벗어납니다'
        increment=None if reason else count/n
        if increment is None:unknown+=1
        else:partial+=increment
        cycles.append({'cycle':index+1,'range_mpa':span,'amplitude_mpa':amplitude,'mean_mpa':mean,'count':count,
            'start_row':start,'end_row':end,'start_s':times[start],'end_s':times[end],
            'calibrated_cycles':n if not reason else None,'damage':increment,
            'admitted_partial_damage':partial,'status':'UNKNOWN' if reason else 'CALCULATED','reason':reason})
    total=partial if cycles and unknown==0 else None
    blocks=None;life_reason='유한 이력의 누적값이며 반복 블록을 가정하지 않았습니다'
    if s['repeat_block']:
        if stress[0]!=stress[-1] or stress[0] not in (min(stress),max(stress)):
            life_reason='반복 블록은 같은 전역 극값에서 시작·종료하는 닫힌 원 이력이 필요합니다'
        elif total is None or total<=0:life_reason='모든 사이클이 시험 범위에 있고 양의 누적값이어야 합니다'
        else:
            # At a global-extremum boundary, residual half cycles must pair
            # exactly. Do not treat merely equal endpoints as periodic counting.
            counts={}
            for row in cycles:
                key=(row['range_mpa'],row['mean_mpa']);counts[key]=counts.get(key,0)+row['count']
            if any(v!=int(v) for v in counts.values()):life_reason='잔여 반사이클이 반복 경계에서 짝을 이루지 않습니다'
            else:blocks=1/total;life_reason='명시 반복 블록 가정의 선형 Miner 한계 D=1'
    responses={
        'stress_history':{**deepcopy(response),'metadata':{**response.get('metadata',{}),'source':deepcopy(s['source'])}},
        'admitted_partial_damage':{'kind':'scalar','unit':'1','value':partial,'metadata':{'label':'시험 범위 내 부분 누적값','excluded_unknown_cycles':unknown}}}
    if total is not None:responses['miner_damage']={'kind':'scalar','unit':'1','value':total,'metadata':{'label':'유한 이력 Miner 누적값'}}
    if blocks is not None:responses['repeating_blocks_to_D1']={'kind':'scalar','unit':'blocks','value':blocks,'metadata':{'label':'가정한 반복 블록 수 (D=1)'}}
    if cycles:
        responses['admitted_damage_history']={'kind':'series','unit':'1','value':[r['admitted_partial_damage'] for r in cycles],
            'axes':[{'name':'cycle_count_record','unit':'1','values':list(range(1,len(cycles)+1))}],
            'metadata':{'label':'시험 범위 내 부분 누적값','not_physical_time':True}}
    return {'execution_status':'SUCCEEDED','responses':responses,'checks':[],'cycles':cycles,
        'diagnostics':{'assessment':'CALCULATED' if total is not None else 'UNKNOWN',
            'life_status':'ASSUMPTION_DEPENDENT' if blocks is not None else 'UNKNOWN','life_reason':life_reason,
            'unknown_cycle_count':unknown,'mean_stress_correction':'NONE','sn_interpolation':'log amplitude/log cycles, no extrapolation',
            'stress_to_mpa':factor,'source':deepcopy(s['source']),'source_response_sha256':canonical_hash(response),
            'assumed_temperature_k':s['temperature_k'],'calibration':deepcopy(c),'decision':'NOT_RELEASED',
            'limitations':['Signed uniaxial S-N only','No sequence interaction or coupled cyclic plasticity/cohesive fatigue']}}


class FatigueAdapter:
    backend,version=BACKEND,'1'
    default_settings=staticmethod(default_settings)
    validate_settings=staticmethod(validate_settings)
    def __init__(self,response=None,source=None):
        self.response=deepcopy(response);self.source=deepcopy(source)
    def describe_ports(self,settings):
        validate_settings(settings)
        return {'inputs':{},'outputs':{},'qualification':'UNKNOWN'}
    def run(self,settings,*,output,runtime=None):
        if runtime:raise ValueError('반복하중 읽기는 별도 solver runtime을 사용하지 않습니다')
        validate_settings(settings)
        if self.response is None or self.source!=settings['source']:
            raise ValueError('공유 서비스에서 정확한 보존 이력을 다시 선택하세요')
        from .storage import save_json
        save_json(Path(output)/'source_response.json',self.response)
        result=analyze(settings,self.response)
        save_json(Path(output)/'cycle_assessment.json',result)
        return result
