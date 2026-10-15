"""Managed readback on the real JobManager with synthetic owned-native process only."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import time
import shutil
import pytest
from test_dynamic_support import dynamic_model,outputs,snapshot,synthetic_rout
from test_dynamic_results import run_double
from test_dynamic_retained_r1 import fingerprints
from caelab.workbench import Workbench
from caelab.dynamic_recovery import reprocess
from caelab.dynamic_recovery_job import request,open_result,OPERATION
from caelab.dynamic_result_store import read_attempt,file_pin
from caelab.adapters import contact_fem
from caelab.execution_control import ExecutionCancelled


def wait(wb,job):
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        status=wb.manager.status(job['id'])
        if status['state'] in {'SUCCEEDED','FAILED','CANCELLED','INTERRUPTED'}:return status
        time.sleep(.02)
    raise AssertionError('Dedicated small readback job did not reach terminal state')


def managed(monkeypatch,tmp_path,failed=False):
    model=dynamic_model(mixed=True);source=tmp_path/'source';source.mkdir();snapshot(model,source/'input')
    exe=tmp_path/'ccx-double';exe.write_bytes(b'EXPLICIT_OWNED_PROCESS_DOUBLE_NO_NATIVE_SOLVE')
    monkeypatch.setattr(contact_fem.shutil,'which',lambda _:str(exe));calls=[]
    def native(args,cwd,label):
        calls.append(str(cwd));frd,dat,sta=outputs(model)
        for ext,body in [('frd',frd),('dat',dat),('sta',sta)]: (cwd/('contact.'+ext)).write_text(body)
        (cwd/'contact.rout').write_bytes(synthetic_rout(model))
        return SimpleNamespace(returncode=1 if failed else 0)
    monkeypatch.setattr(contact_fem,'run_owned_command',native)
    wb=Workbench(tmp_path/'workspace',configuration={'input_roots':{'inputs':str(source)},'cpu_budget':64})
    try:
        receipt=wb.register_local_input('inputs','input/snapshot.json')
        job=wb.submit('run',{'backend':'structure.calculix.contact','settings':{'data_id':receipt['id']}})
        status=wait(wb,job)
        assert status['state']==('FAILED' if failed else 'SUCCEEDED'),status
        return wb,job,calls
    except BaseException:
        wb.manager.shutdown();raise


@pytest.mark.parametrize('failed',[False,True])
def test_actual_manager_explicit_readback_job_idempotence_and_cold_owner(monkeypatch,tmp_path,failed):
    wb,job,calls=managed(monkeypatch,tmp_path,failed=failed)
    try:
        source=wb.root/'native'/job['id'];before=fingerprints(source);original=wb.manager.status(job['id'])
        count=len(wb.manager.list());args=request(wb,job['id']);assert len(wb.manager.list())==count
        monkeypatch.setattr(contact_fem,'run_owned_command',lambda *a,**k:pytest.fail('REPROCESS_INVOKED_CCX'))
        new=wb.submit(OPERATION,args,request_id='R2exactReadback')
        status=wait(wb,new);assert status['state']=='SUCCEEDED',status
        assert wb.submit(OPERATION,args,request_id='R2exactReadback')['id']==new['id']
        result=wb.manager.result(new['id']);assert result['solver_execution']=='NOT_PERFORMED'
        assert result['source_execution_status']==('FAILED' if failed else 'SUCCEEDED')
        selected=open_result(wb,new['id']);selected_frame=selected['frames'][4]
        assert selected['job_id']==job['id'] and selected['derivation']['readback_job']['id']==new['id']
        assert selected['qualification']=='UNKNOWN'
        assert wb.manager.status(job['id'])==original and fingerprints(source)==before
        assert len(calls)==1 and len(wb.manager.list())==count+1
        with pytest.raises(ValueError):wb.submit(OPERATION,{**args,'source_job_id':new['id']})
        with pytest.raises(ValueError):wb.submit(OPERATION,{**args,'source_record':{**args['source_record'],'sha256':'1'*64}})
        workspace=wb.workspace
    finally:wb.manager.shutdown()
    moved=tmp_path/'경로 이동';shutil.move(workspace,moved)
    reopened=Workbench(moved)
    try:
        assert open_result(reopened,new['id'])['frames'][4]==selected_frame
        assert reopened.manager.status(job['id'])==original
    finally:reopened.manager.shutdown()


@pytest.mark.parametrize('status',['FAILED','CANCELLED','UNKNOWN'])
def test_reprocessing_never_promotes_original_failure_and_keeps_raw(monkeypatch,tmp_path,status):
    _,source=run_double(monkeypatch,tmp_path,dynamic_model(),failed=True,rout=True)
    p=source/'contact_execution.json';r=json.loads(p.read_text());r['execution_status']=status;p.write_text(json.dumps(r))
    before=fingerprints(source)
    monkeypatch.setattr(contact_fem,'run_owned_command',lambda *a,**k:pytest.fail('ccx'))
    output=tmp_path/'readback';receipt=reprocess(source,output,expected_record=file_pin(source,p))
    assert receipt['readback_status']=='SUCCEEDED',receipt
    assert receipt['execution_status']==status and read_attempt(output)['execution_status']==status
    assert receipt['responses']=={} and fingerprints(source)==before
    assert receipt['derivation']['original_execution_status']==status


@pytest.mark.parametrize('phase',['result','post','copy'])
def test_cancel_partial_write_retains_native_record_and_no_success(monkeypatch,tmp_path,phase):
    from caelab.adapters import dynamic_fem
    from caelab import dynamic_post
    from caelab import dynamic_recovery
    _,source=run_double(monkeypatch,tmp_path,dynamic_model(),rout=True);before=fingerprints(source)
    def cancel(*a,**k):raise ExecutionCancelled('R2_CANCEL_AT_'+phase)
    if phase=='result':monkeypatch.setattr(dynamic_fem,'write_result',cancel)
    elif phase=='post':monkeypatch.setattr(dynamic_post,'write',cancel)
    else:monkeypatch.setattr(dynamic_recovery.shutil,'copyfileobj',cancel)
    receipt=reprocess(source,tmp_path/'cancelled')
    assert receipt['execution_status']=='SUCCEEDED' # original native job, NOT readback
    assert receipt['readback_status']=='CANCELLED' and not receipt.get('dynamic_result')
    assert receipt['responses']=={} and fingerprints(source)==before
    saved=json.loads((tmp_path/'cancelled/contact_execution.json').read_text())
    assert saved['readback_status']=='CANCELLED' and saved['solver_execution']=='NOT_PERFORMED'


def test_changed_raw_wrong_record_and_active_native_rejected_before_output(monkeypatch,tmp_path):
    _,source=run_double(monkeypatch,tmp_path,dynamic_model(),rout=True)
    p=source/'contact_execution.json';ref=file_pin(source,p)
    with pytest.raises(ValueError):reprocess(source,tmp_path/'wrong',expected_record={**ref,'relative':'solver/contact.rout'})
    r=json.loads(p.read_text());r['native_execution']['status']='RUNNING';p.write_text(json.dumps(r))
    with pytest.raises(ValueError,match='termination'):reprocess(source,tmp_path/'active')
    assert not (tmp_path/'active').exists()
    r['native_execution']['status']='COMPLETED';p.write_text(json.dumps(r))
    with (source/'solver/contact.rout').open('ab') as stream:stream.write(b'x')
    with pytest.raises(ValueError,match='changed'):reprocess(source,tmp_path/'corrupt')
    assert not (tmp_path/'corrupt').exists()


def test_live_cancellation_after_native_terminal_saves_cancelled_record(monkeypatch,tmp_path):
    from caelab.execution_control import CancellationToken,cancellation_scope
    from caelab import dynamic_native_stream as stream
    from caelab.dynamic_execution import read_terminal
    token=CancellationToken();original=stream.NativeFrames.append
    def cancel(self,frame):
        original(self,frame)
        token.request()
    monkeypatch.setattr(stream.NativeFrames,'append',cancel)
    with cancellation_scope(token):
        receipt,output=run_double(monkeypatch,tmp_path,dynamic_model(),rout=True)
    assert receipt['execution_status']=='CANCELLED' and receipt['responses']=={}
    assert not receipt.get('dynamic_result')
    terminal=read_terminal(output,full=True)
    assert terminal['status']=='COMPLETED' # owned synthetic command returned before cancellation
    assert terminal['execution_status']=='CANCELLED'
    assert (output/'solver/contact.rout').is_file()
    assert json.loads((output/'contact_execution.json').read_text())['execution_status']=='CANCELLED'


def test_zero_length_raw_dat_stays_missing_energy_not_zero(monkeypatch,tmp_path):
    from caelab.dynamic_execution import read_terminal
    from caelab import dynamic_locations as loc
    m=dynamic_model();snap=snapshot(m,tmp_path/'input');exe=tmp_path/'ccx';exe.write_bytes(b'DOUBLE')
    monkeypatch.setattr(contact_fem.shutil,'which',lambda _:str(exe))
    def process(args,cwd,label):
        frd,_,sta=outputs(m)
        (cwd/'contact.frd').write_text(frd);(cwd/'contact.sta').write_text(sta);(cwd/'contact.dat').write_bytes(b'')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(contact_fem,'run_owned_command',process)
    out=tmp_path/'run';r=contact_fem.ContactFemCalculixAdapter().run({'snapshot_path':str(snap)},output=out)
    assert r['execution_status']=='SUCCEEDED',r
    data=read_attempt(out)
    assert all(frame['energy']['ELKE']['total'] is None for frame in data['frames'])
    assert 'ELKE.structural_sum' not in r['responses']
    a=r['dynamic_post_artifacts']['dynamic'];assert loc.audit(out/a['relative'],a['native_metadata'])['scope']=='ALL_REFERENCED_BYTES'
    assert read_terminal(out,full=True)['source_pins']['solver/contact.dat']['bytes']==0
