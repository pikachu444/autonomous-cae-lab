"""Existing converter plus synthetic callback/PRINT contract doubles; no native solve."""
import json
import math
from copy import deepcopy
from pathlib import Path
import pytest
from reclosure_fixtures import settings
from caelab.impact_model import model_from_settings,validate_settings
from caelab.impact_reclosure_policy import POLICY,TRACE,PHASE_ENV,SEGMENT_ENV,callback_source,validate,verify,audit_trace
from caelab.impact_bulk_deck import cards


@pytest.fixture
def compiled(tmp_path):
    from impact_b_fixtures import compile_fixture
    return compile_fixture(tmp_path/'input',settings())


def receipt():
    return {'sensor_id':19,'function_name':'caelab_reclosure_19','cohort':{'cohesive':2,'lower_bulk':1,'upper_bulk':3},
            'trace_relative':TRACE}


@pytest.fixture(autouse=True)
def windows_module_query(tmp_path, monkeypatch):
    import ctypes
    from types import SimpleNamespace
    dll = tmp_path / 'synthetic-python.dll'
    dll.write_bytes(b'WINDOWS_MODULE_QUERY_DOUBLE_NOT_A_RUNTIME')
    def query(handle, buffer, capacity):
        assert handle == ctypes.pythonapi._handle and len(str(dll)) < capacity
        buffer.value = str(dll)
        return len(buffer.value)
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **kw:
                        SimpleNamespace(GetModuleFileNameW=query), raising=False)


def callback(tmp_path,monkeypatch,*,phase='ENGINE',segment='0001'):
    monkeypatch.chdir(tmp_path);monkeypatch.setenv(PHASE_ENV,phase);monkeypatch.setenv(SEGMENT_ENV,segment)
    values={2:1.,1:1.,3:1.};namespace={'OFF':lambda eid:values[eid],'TIME':0.,'DT':1e-7,'sensors':{19:{'status':0}}}
    source=callback_source(receipt());exec(compile(source,'generated-test-callback','exec'),namespace)
    state={};fn=namespace['caelab_reclosure_19']
    def call(coh=1.,lower=1.,upper=1.):
        values.update({2:coh,1:lower,3:upper});namespace['TIME']+=namespace['DT']
        return fn(state)
    return call,namespace,state


def test_pinned_cards_only_idel_sensor_and_approved_source_changed(compiled):
    s,model,initial,physics,text,definition=compiled
    policies=definition['interface']['reclosure_policies'];assert len(policies)==1
    policy=policies[0];assert policy['cohort']=={'cohesive':2,'lower_bulk':1,'upper_bulk':3}
    assert policy['cycle_binding']=='PINNED_SENSOR_INIT_THEN_PRINT1'
    assert policy['terminal_cycle_relation']=='PRINT_LAST_TOTAL_MINUS_ONE'
    verify(text,model,s,policies)
    block=cards(text)['/INTER/TYPE24/'+str(policy['native_contact_id'])]
    assert int(block[1][70:80])==1 and int(block[6][50:60])==policy['sensor_id']
    assert float(block[4][40:60].strip() or '0')==0. and float(block[4][60:80].strip() or '0')==0.
    assert len(next(v for k,v in cards(text).items() if k.startswith('/MAT/LAW117/')))==5
    assert policy['callback_source'].startswith('def '+policy['function_name']+'(state):')
    assert policy['callback_source'].endswith('\n\n')
    assert max(map(len,policy['callback_source'].splitlines()))<=100
    changed=text.replace('FADING_CONTACT_OFF','FADING_CONTACT_ON')
    with pytest.raises(ValueError):verify(changed,model,s,policies)
    no_blank=text.replace('    return gate\n\n','    return gate\n',1)
    with pytest.raises(ValueError,match='빈 줄'):verify(no_blank,model,s,policies)
    extra=text.replace('/END','/SENSOR/PYTHON/9999\ndef unapproved(state):\n    return 1.0\n\n/END')
    with pytest.raises(ValueError,match='승인되지'):verify(extra,model,s,policies)
    forged=deepcopy(policies);forged[0]['callback_source']+='print("unapproved")\n'
    with pytest.raises(ValueError):verify(text,model,s,forged)


def test_fresh_gate_waits_two_callbacks_and_fade_never_enables(tmp_path,monkeypatch):
    call,namespace,state=callback(tmp_path,monkeypatch)
    assert call()==call()==call()==0.
    assert call(.8)==call(.64)==call(.1)==0.
    assert call(0.)==1.
    rows=[json.loads(line) for line in Path(TRACE).read_text().splitlines()]
    assert [r['ordinal'] for r in rows]==list(range(1,8))
    assert [r['armed'] for r in rows[:3]]==[False,False,True]
    assert rows[3]['reason']=='FADING_CONTACT_OFF'
    assert rows[-1]['off']==[0.,1.,1.] and rows[-1]['gate']==1.
    assert rows[0]['python']['implementation']=='cpython'
    runtime=rows[0]['python']
    assert Path(runtime['dll_path']).is_file() and len(runtime['dll_sha256'])==64
    assert runtime['pointer_bits']==64
    if runtime['math_file'] is None:
        assert runtime['math_origin']=='built-in' and runtime['math_sha256'] is None
    else:assert len(runtime['math_sha256'])==64


def test_runtime_query_failure_is_preserved_and_never_arms(tmp_path,monkeypatch):
    import ctypes
    def failed(*args,**kwargs):raise OSError('declared DLL query failure')
    monkeypatch.setattr(ctypes,'WinDLL',failed)
    call,_,_=callback(tmp_path,monkeypatch)
    call();call();call();assert call(0.)==0.
    rows=[json.loads(line) for line in Path(TRACE).read_text().splitlines()]
    assert all(not row['armed'] and row['gate']==0. for row in rows)
    assert rows[0]['runtime_error']=='OSError:declared DLL query failure'
    assert rows[-1]['reason']=='RUNTIME_QUERY_FAILED_CONTACT_OFF'


def test_math_without_file_requires_exact_builtin_origin(tmp_path,monkeypatch):
    monkeypatch.delattr(math,'__file__',raising=False)
    monkeypatch.setattr(math.__spec__,'origin','unverified')
    call,_,_=callback(tmp_path,monkeypatch)
    call();call();call();assert call(0.)==0.
    row=json.loads(Path(TRACE).read_text().splitlines()[0])
    assert row['python']['math_origin']=='unverified'
    assert 'no verified file or built-in origin' in row['runtime_error']


def test_positive_print_table_uses_exact_ecrit_fields_and_keeps_tokens(tmp_path,monkeypatch):
    call,_,_=callback(tmp_path,monkeypatch);call();call();call();call()
    log=tmp_path/'engine.out'
    lines=['   CYCLE    TIME      TIME-STEP  ELEMENT          ERROR  I-ENERGY']
    for cycle in range(3):
        lines.append(f'{cycle:8d} {cycle*1.e-7:11.4g} {1.e-7:11.4g} NODE  {9:10d}   0.0%')
    log.write_text('\n'.join(lines)+'\nNORMAL TERMINATION\nTOTAL NUMBER OF CYCLES : 3\n')
    audit=audit_trace(Path(TRACE),log,receipt())
    assert audit['engine_print_count']==3 and audit['engine_callback_count']==4
    assert [r['print_cycle'] for r in audit['cycle_mapping']]==[0,1,2]
    assert audit['print_rows'][1]['time_token']=='1e-07'
    assert audit['print_rows'][1]['raw_line']==lines[2]
    assert audit['every_increment']=='EVERY_INCREMENT_UNKNOWN'
    assert audit['unmatched_tail_callbacks']==[]


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),-1.e30,None,.5])
def test_bad_bulk_values_fail_closed_and_keep_original_unknown(tmp_path,monkeypatch,bad):
    call,_,_=callback(tmp_path,monkeypatch);call();call();call()
    assert call(0.,bad,1.)==0.
    raw=json.loads(Path(TRACE).read_text().splitlines()[-1])
    assert raw['reason']=='INVALID_NATIVE_VALUE_CONTACT_OFF'
    if bad is None:assert raw['off'][1] is None
    elif math.isfinite(bad):assert raw['off'][1]==bad
    else:assert raw['off'][1]==repr(bad)


def test_deleted_bulk_and_reappeared_cohesive_never_reenable(tmp_path,monkeypatch):
    call,_,_=callback(tmp_path,monkeypatch);call();call();call()
    assert call(0.)==1.
    assert call(0.,1.,0.)==0.
    assert call(0.,1.,1.)==0.
    assert call(.8)==0.
    assert call(0.)==0.


@pytest.mark.parametrize('phase,segment',[('STARTER','0001'),('UNKNOWN','0001'),('ENGINE','0002'),('ENGINE','UNKNOWN')])
def test_noninitial_engine_or_unknown_stage_cannot_fresh_arm(tmp_path,monkeypatch,phase,segment):
    call,_,_=callback(tmp_path,monkeypatch,phase=phase,segment=segment)
    call();call();call();assert call(0.)==0.


@pytest.mark.parametrize('change',['clock','friction','duplicate_pair','bad_bulk','multi_cohesive'])
def test_new_policy_is_not_a_clock_gate_or_arbitrary_contact(change):
    value=settings();model=model_from_settings(value)
    if change=='clock':value['interface_controls'][0]['contact_start_s']=.0001
    elif change=='friction':value['contacts'][0]['friction']=.1
    elif change=='duplicate_pair':value['contacts'].append(deepcopy(value['contacts'][0]))
    elif change=='bad_bulk':model['elements'][3]['nodes']=[1,2,3,4,5,6,7,8]
    else:model['assignment'][3]='BOND'
    with pytest.raises(ValueError):validate(model,value)


def test_p1_uses_existing_history_and_original_law_without_parameter_tuning(tmp_path):
    from impact_b_fixtures import compile_fixture
    value=settings('P1');validate_settings(value)
    _,model,_,_,text,definition=compile_fixture(tmp_path/'p1',value)
    assert definition['interface_history']['histories'][0]['displacement_mm']==[0,.03,.03,-.025,-.025,.01,.01,.01]
    assert value['cohesive'][0]['normal_strength_mpa']==2.
    assert definition['interface']['reclosure_policies'][0]['native_idel']==1
    assert '/IMPDISP/' in text



def test_trace_auditor_preserves_unknown_prefix_and_definite_overlap(tmp_path,monkeypatch):
    call,_,_=callback(tmp_path,monkeypatch);call();call();call();call(.8);call(0.)
    path=Path(TRACE);rows=[json.loads(v) for v in path.read_text().splitlines()]
    log=tmp_path/'engine.stdout.log'
    log.write_text(''.join(f"NC= {i} T= {row['time_s']:.4E} DT= {row['dt_s']:.4E}\n" for i,row in enumerate(rows[1:]))+
        'NORMAL TERMINATION\nTOTAL NUMBER OF CYCLES : 4\n',encoding='ascii')
    report=audit_trace(path,log,receipt())
    assert report['every_increment']=='EVERY_INCREMENT_UNKNOWN'
    assert report['actual_initial_live_row']==2 and report['fading_contact_off_rows']==[3]
    assert report['gate_on_rows']==[4] and report['violations']==[]
    assert report['engine_callback_count']==5 and len(report['trace_rows'])==5
    # Synthetic alignment contract only, not a claim about native PRINT source.
    bound={**receipt(),'cycle_binding':'PINNED_SENSOR_INIT_THEN_PRINT1','terminal_cycle_relation':'PRINT_LAST_TOTAL_MINUS_ONE'}
    assert audit_trace(path,log,bound)['every_increment']=='COMPLETE_PINNED_TRACE_COVERAGE'
    rows[3]['gate']=1.
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
    report=audit_trace(path,log,bound)
    assert report['every_increment']=='VIOLATED'
    assert report['violations']==[{'row':3,'reason':'LIVE_FADING_OR_MISSING_BULK_CONTACT_OVERLAP'}]
    assert report['trace_rows'][3]['off'][0]==.8
    # Broken tail/cycle prefix cannot disappear behind a previous valid row.
    rows[3]['gate']=0.;path.write_text(''.join(json.dumps(row)+'\n' for row in rows[:-1])+'{"cut":',encoding='utf-8')
    report=audit_trace(path,log,bound)
    assert report['every_increment']=='EVERY_INCREMENT_UNKNOWN'
    assert report['engine_callback_count']==4 and any('truncated' in r for r in report['unknown_reasons'])


def test_shared_persistent_dict_keeps_sensor_namespaces_separate(tmp_path,monkeypatch):
    call,namespace,state=callback(tmp_path,monkeypatch)
    other={**receipt(),'sensor_id':20,'function_name':'caelab_reclosure_20'}
    namespace['sensors'][20]={'status':0}
    exec(compile(callback_source(other),'other-generated-callback','exec'),namespace)
    call();call();call()
    assert namespace['caelab_reclosure_20'](state)==0.
    assert state['caelab_reclosure_19']['ordinal']==3
    assert state['caelab_reclosure_20']['ordinal']==1 and not state['caelab_reclosure_20'].get('armed',False)
