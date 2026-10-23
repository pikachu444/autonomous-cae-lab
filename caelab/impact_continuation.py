"""One saved L03 prefix -> one separately owned Engine2 child, no restart framework.

The common Simulation owner supplies verified saved-revision context. Native TT
is distinct from RUN target, PRINT display and the last Python callback time.
"""
from copy import deepcopy
import json
import math
from pathlib import Path
import re

from .storage import canonical_hash
from .dynamic_result_store import file_pin,verify_pin
from .impact_native_io import read_bytes
from .impact_reclosure_policy import PIN,POLICY,TRACE,verify as verify_policy

PREFIX_TIME=.00225
END_TIME=.004
DELETED_BULK=3
KIND='IMPACT_L03_PREFIX'


def prefix_plan(settings):
    """Keep the full native history; only the dedicated Engine1 stop is shorter."""
    from .impact_model import validate_settings,model_from_settings
    from .impact_reclosure_policy import validate
    value=validate_settings(settings);model=model_from_settings(value)
    policies=validate(model,value)
    if len(policies)!=1 or policies[0]['cohort']!={'cohesive':2,'lower_bulk':1,'upper_bulk':3}:
        raise ValueError('첫 이어 실행은 원 응집2·벌크1/3의 정확한 계면만 지원합니다')
    if value['time']['end_s']!=END_TIME or value['time']['scale']!=.9 or value['motions']:
        raise ValueError('원 .004 s 전체 이력·시간 scale·초기 운동을 보존하세요')
    rows=value.get('interface_histories',[])
    if len(rows)!=1 or rows[0]['component']!='Z' or rows[0]['time_s']!=[0,.0005,.00075,.00175,.00225,.00325,.0035,.004] or rows[0]['displacement_mm']!=[0,.030,.030,-.025,-.025,.010,.010,.010]:
        raise ValueError('사전 지정한 개방·압축 hold·재개방 이력을 변경하지 않습니다')
    return {'kind':KIND,'source_pin':PIN,'target_time_s':PREFIX_TIME,
        'full_input_end_s':END_TIME,'settings_sha256':canonical_hash(value),
        'history_sha256':canonical_hash(rows),'clock_status':'NATIVE_CHECKPOINT_TT_UNVERIFIED',
        'engine_stop_only':True,'engineering_qualification':'UNKNOWN'}


def _json(root,pin):
    return json.loads(read_bytes(verify_pin(root,pin),expected=pin,maximum=64*1024*1024))


def _run_stop(text,segment):
    match=re.search(r'(?m)^/RUN/impact/'+str(segment)+r'[ \t]*\r?\n([^\r\n]+)',text)
    if match is None:raise ValueError('원 segment의 정확한 RUN 카드가 없습니다')
    stop=float(match.group(1).strip())
    if not math.isfinite(stop):raise ValueError('RUN 시각이 비유한 값입니다')
    return stop


def prefix_observation(source_root,record,checkpoint_clock=None):
    """Evidence-only admission, never infer actual RST TT from another clock.

    checkpoint_clock must originate in the bounded pinned native restart reader;
    the common owner never accepts it from command JSON or a user-edited draft.
    A missing decoder observation is retained as UNKNOWN and cannot launch child.
    """
    root=Path(source_root);retained=record['retained_native'];native=retained['native_artifacts']
    engine_pin=native.get('native/impact_0001.rad')
    if engine_pin is None:raise ValueError('보존한 Engine1 입력이 없습니다')
    engine=read_bytes(verify_pin(root,engine_pin),expected=engine_pin,maximum=1024*1024).decode('ascii')
    target=_run_stop(engine,1)
    checkpoints={name:deepcopy(pin) for name,pin in native.items()
        if re.fullmatch(r'native/impact_0001_\d{4}\.rst',name)}
    for pin in checkpoints.values():verify_pin(root,pin)
    observed={'kind':KIND,'source_pin':PIN,'requested_time_s':PREFIX_TIME,'run_target_s':target,
        'checkpoint_files':checkpoints,'checkpoint_clock':deepcopy(checkpoint_clock),
        'admissible':False,'status':'UNKNOWN_CHECKPOINT_CLOCK','engineering_qualification':'UNKNOWN'}
    if target!=PREFIX_TIME:
        observed['status']='INELIGIBLE_RUN_TARGET';return observed
    if set(checkpoints)!={'native/impact_0001_0001.rst'}:
        observed['status']='INELIGIBLE_CHECKPOINT_FILE_SET';return observed
    if not isinstance(checkpoint_clock,dict):return observed
    pin=checkpoints['native/impact_0001_0001.rst']
    if (checkpoint_clock.get('source_pin')!=PIN or checkpoint_clock.get('origin')!='NATIVE_RESTART_TT'
            or checkpoint_clock.get('artifact')!=pin):
        observed['status']='INELIGIBLE_CLOCK_SOURCE';return observed
    time=checkpoint_clock.get('time_s')
    if type(time) not in (int,float) or not math.isfinite(time) or time!=PREFIX_TIME:
        observed['status']='INELIGIBLE_ACTUAL_CHECKPOINT_TIME';return observed
    observed.update(admissible=True,status='EXACT_CHECKPOINT_TIME_VERIFIED')
    return observed


def engine2_cards():
    """No Starter, no function/material rewrite, no RUN1 whitelist expansion."""
    return '/RUN/impact/2\n0.004\n/PRINT/1\n/DEL/BRICK\n'+f'{DELETED_BULK:10d}\n'+'/STOP\n0 0 0 1 1\n'


def prepare(parent_selection,*,context):
    """Freeze a same-owner saved parent; all native pins are verified directly."""
    if not isinstance(parent_selection,dict) or set(parent_selection)!={'document_id','source_job_id','saved_revision'}:
        raise ValueError('같은 Simulation의 정확한 저장 revision과 원 실행을 선택하세요')
    owner=context['owner_binding'];root=Path(context['source_root']);record=context['record']
    settings=context['settings'];plan=prefix_plan(settings)
    if any(parent_selection[key]!=owner.get({'source_job_id':'job_id'}.get(key,key)) for key in parent_selection):
        raise ValueError('선택 부모와 같은 Simulation의 저장 신원이 다릅니다')
    if owner.get('job_state')!='SUCCEEDED' or owner.get('cleanup_confirmed') is not True or owner.get('cancelled') is True:
        raise ValueError('성공한 부모 실행과 owned 프로세스 정리를 확인하세요')
    if canonical_hash({'backend':'explicit.opencourant.model','settings':settings})!=owner['input_sha256']:
        raise ValueError('저장 부모의 정확한 실행 입력과 다릅니다')
    if record.get('execution_status')!='SUCCEEDED' or record['diagnostics'].get('cleanup_unconfirmed'):
        raise ValueError('부모 native 종료·정리 상태가 적격하지 않습니다')
    retained=record['retained_native'];fixed=retained['input_artifacts'];native=retained['native_artifacts']
    for pin in [*fixed.values(),*native.values()]:verify_pin(root,pin)
    if _json(root,fixed['input.json'])!=settings:raise ValueError('원 input bytes와 부모 입력이 다릅니다')
    prefix=owner.get('prefix_record')
    if not isinstance(prefix,dict) or prefix!=record['diagnostics'].get('continuation_prefix'):
        raise ValueError('전용 prefix 실행의 보존 checkpoint 신원이 없습니다')
    observed=prefix_observation(root,record,prefix.get('checkpoint_clock'))
    if not observed['admissible']:raise ValueError('실제 .00225 s checkpoint가 확인되지 않았습니다: '+observed['status'])
    definition=_json(root,fixed['b_definition.json'])
    policies=definition['interface'].get('reclosure_policies',[])
    starter=read_bytes(verify_pin(root,native['native/impact_0000.rad']),expected=native['native/impact_0000.rad'],maximum=16*1024*1024).decode('ascii')
    verify_policy(starter,context['model'],settings,policies)
    if len(policies)!=1:raise ValueError('정확한 삭제 연동 센서 하나가 필요합니다')
    policy=policies[0];audit=_json(root,fixed['reclosure_audit.json'])['policies'][0]
    rows=audit['trace_rows']
    if (audit['every_increment']!='COMPLETE_PINNED_TRACE_COVERAGE' or audit['violations']
            or not rows or not any(row['armed'] and row['off']==[1.,1.,1.] for row in rows)):
        raise ValueError('부모의 전수 trace와 실제 arm 이력이 확인되지 않았습니다')
    last=rows[-1]
    if last['off']!=[0.,1.,1.] or last['armed'] is not True or last['gate']!=1 or last.get('runtime_error'):
        raise ValueError('부모의 완전 삭제·양쪽 벌크 생존 상태가 확인되지 않았습니다')
    source_pins={'input_artifacts':deepcopy(fixed),'native_artifacts':deepcopy(native),
        'execution_record':file_pin(root,root/'impact_execution.json')}
    parent={**deepcopy(parent_selection),'input_sha256':owner['input_sha256'],
        'result_sha256':owner['result_sha256'],'runtime':deepcopy(record['diagnostics']['runtime']),
        'source_pins':source_pins,'checkpoint':observed,'policy':deepcopy(policy),'state':deepcopy(last)}
    parent['source_fingerprint']=canonical_hash(parent)
    cards=engine2_cards()
    arguments={'parent':parent,'prefix_plan':plan,'engine2_cards':cards,
        'engine2_cards_sha256':__import__('hashlib').sha256(cards.encode('ascii')).hexdigest(),
        'deleted_bulk':DELETED_BULK,'target_time_s':END_TIME}
    return {'arguments':arguments,'admission':{'status':'ADMITTED_EXACT_SAVED_PREFIX',
        'parent_fingerprint':parent['source_fingerprint'],'engineering_qualification':'UNKNOWN'}}
