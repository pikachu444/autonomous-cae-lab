"""Prefix/parent counterexamples, no native execution or invented restart payload."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from caelab.dynamic_result_store import file_pin
from caelab.evaluation import file_hash
from caelab.impact_continuation import PREFIX_TIME,prefix_plan,prefix_observation,prepare
from reclosure_fixtures import settings


def retained_fixture(tmp_path,stop='.00225'):
    native=tmp_path/'native';native.mkdir()
    engine=native/'impact_0001.rad';engine.write_text('/RUN/impact/1\n'+stop+'\n/PRINT/1\n')
    # This is deliberately NOT a native restart. No test invents a decoder TT.
    restart=native/'impact_0001_0001.rst';restart.write_bytes(b'SYNTHETIC_NOT_NATIVE_RESTART')
    return {'retained_native':{'native_artifacts':{p.relative_to(tmp_path).as_posix():file_pin(tmp_path,p)
        for p in (engine,restart)}}}


def test_prefix_plan_keeps_full_history_and_original_settings():
    original=settings('P1');before=deepcopy(original)
    plan=prefix_plan(original)
    assert plan['target_time_s']==PREFIX_TIME and plan['full_input_end_s']==.004
    assert plan['engine_stop_only'] and plan['clock_status']=='NATIVE_CHECKPOINT_TT_UNVERIFIED'
    assert original==before and original['interface_histories'][0]['time_s'][-1]==.004


def test_current_run_target_cannot_be_relabelled_as_prefix(tmp_path):
    record=retained_fixture(tmp_path,'.004')
    observed=prefix_observation(tmp_path,record)
    assert not observed['admissible'] and observed['status']=='INELIGIBLE_RUN_TARGET'
    assert observed['run_target_s']==.004 and observed['requested_time_s']==PREFIX_TIME


def test_requested_stop_and_last_print_are_not_actual_restart_clock(tmp_path):
    record=retained_fixture(tmp_path)
    (tmp_path/'native/impact_0001.out').write_text('CYCLE TIME .00225\nNORMAL TERMINATION')
    observed=prefix_observation(tmp_path,record)
    assert not observed['admissible'] and observed['status']=='UNKNOWN_CHECKPOINT_CLOCK'
    observed=prefix_observation(tmp_path,record,{'origin':'LAST_PRINT_TIME','time_s':PREFIX_TIME})
    assert not observed['admissible'] and observed['status']=='INELIGIBLE_CLOCK_SOURCE'


def test_unpinned_or_changed_restart_cannot_supply_clock(tmp_path):
    record=retained_fixture(tmp_path)
    (tmp_path/'native/impact_0001_0001.rst').write_bytes(b'SAME LENGTH DIFFERENT_CONTENT')
    with pytest.raises(ValueError):prefix_observation(tmp_path,record)


def test_missing_or_extra_restart_rank_is_ineligible(tmp_path):
    record=retained_fixture(tmp_path)
    del record['retained_native']['native_artifacts']['native/impact_0001_0001.rst']
    assert prefix_observation(tmp_path,record)['status']=='INELIGIBLE_CHECKPOINT_FILE_SET'


def test_parent_owner_revision_mismatch_blocks_before_execution(tmp_path):
    selection={'document_id':'Vone','source_job_id':'Jone','saved_revision':'Rone'}
    context={'source_root':tmp_path,'record':{},'settings':settings('P1'),
        'owner_binding':{'document_id':'Vone','job_id':'Jone','saved_revision':'Rother'}}
    with pytest.raises(ValueError,match='저장 신원'):prepare(selection,context=context)


def test_existing_actual_p1_end_checkpoint_is_not_exact_prefix():
    source=Path(__file__).resolve().parents[1]/'runs/interface-reclosure-20261018/p1-native-01/store/workbench/results/J7a50086011154ae885666628f4ab9903/calculation'
    if not source.is_dir():pytest.skip('Local preserved P1 only; no solver creates the evidence')
    before=file_hash(source/'impact_execution.json')
    record=json.loads((source/'impact_execution.json').read_text(encoding='utf-8'))
    observed=prefix_observation(source,record)
    assert observed['status']=='INELIGIBLE_RUN_TARGET' and not observed['admissible']
    assert observed['run_target_s']==.004 and observed['checkpoint_clock'] is None
    assert set(observed['checkpoint_files'])=={'native/impact_0001_0001.rst'}
    assert file_hash(source/'impact_execution.json')==before
