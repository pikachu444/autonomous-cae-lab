from pathlib import Path
from copy import deepcopy
import json
import shutil
import time
import uuid
import pytest
from caelab.impact_model import BACKEND
from caelab.workbench import Workbench
from caelab.storage import canonical_hash,save_json
from caelab.evaluation import run,read_result
from caelab.impact_retained import select_frame,inventory,context,reference,artifact_receipt,frame_record
from test_native import definition
from support import install_boundary_double,vtk,TIMES


def change(wb,doc,op,args=None,command_id=None):
    return wb.document_command(doc['id'],op,args or {},session_id=doc['session_id'],
        expected_generation=doc['generation'],command_id=command_id or 'C'+uuid.uuid4().hex)


def wait(wb,job):
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        result=wb.manager.status(job['id'])
        if result['state'] in {'SUCCEEDED','FAILED','CANCELLED','PARTIAL_FAILURE','INTERRUPTED'}:return result
        time.sleep(.01)
    raise AssertionError('Dedicated small unit job did not terminate')


def test_managed_native_direct_source_apply_save_selected_new_owner_no_solver(tmp_path,monkeypatch):
    calls=install_boundary_double(monkeypatch);workspace=tmp_path/'workspace';wb=Workbench(workspace,configuration={'workers':1})
    try:
        s=definition();doc=wb.document_open(kind='simulation',title='UNIT 원문→실행→선택 보관',draft={'backend':BACKEND,'settings':s})
        doc=change(wb,doc,'document.save')['document']
        reply=change(wb,doc,'simulation.evaluate');doc=reply['document'];job=wait(wb,reply['job'])
        assert job['state']=='SUCCEEDED',job
        selected=wb.document_result(doc['id'],job['id'],selection={'responses':['impact.displacement.Z@2']})
        response=selected['responses']['impact.displacement.Z@2']
        assert response['value']==pytest.approx([0.,-.05,-.1])
        assert response['unit']=='mm' and response['frame']=='MODEL_GLOBAL'
        assert selected['post_input']['format']=='pvd'
        doc=change(wb,doc,'document.save')['document'];old_calls=list(calls)
        assert calls==['starter','engine','history_convert','animation_0000','animation_0001','animation_0002']
        docid=doc['id'];jobid=job['id'];saved_count=len(wb.manager.list())
    finally:assert wb.shutdown()['joined']
    def forbidden(*a,**kw):raise AssertionError('A cold selected read cannot execute a solver or probe runtime')
    monkeypatch.setattr('caelab.adapters.impact.selected_runtime',forbidden)
    monkeypatch.setattr('caelab.adapters.impact.run_owned_command',forbidden)
    fresh=Workbench(workspace,configuration={'workers':1})
    try:
        reopened=fresh.document_open(kind='simulation',document_id=docid)
        assert reopened['draft']['settings']==s and len(fresh.manager.list())==saved_count
        selected=fresh.document_result(docid,jobid,selection={'responses':['impact.velocity.Z@4']})
        assert selected['responses']['impact.velocity.Z@4']['value']==[-100.]*3
        assert selected['responses']['impact.velocity.Z@4']['metadata']['solver_execution']=='NOT_PERFORMED'
        assert calls==old_calls and len(fresh.manager.list())==saved_count
        # Actual old live result folder can disappear: saved Simulation owns a copy.
        shutil.rmtree(fresh.root/'results'/jobid)
        again=fresh.document_result(docid,jobid,selection={'responses':['impact.displacement.Z@1']})
        assert again['responses']['impact.displacement.Z@1']['value']==pytest.approx([0.,-.05,-.1])
    finally:assert fresh.shutdown()['joined']


def test_selected_payload_not_other_frames_and_metadata_cannot_verify(tmp_path,monkeypatch):
    install_boundary_double(monkeypatch)
    output=tmp_path/'attempt';result=run(BACKEND,definition(),output=output)
    outcome=result['diagnostics']['native_outcome']
    assert inventory(outcome,output)['verification']=='METADATA_ONLY_PAYLOAD_NOT_VERIFIED'
    frame=select_frame(outcome,output,index=1,quantity='velocity',component='Z',identity=2)
    assert frame['value']==-100. and frame['time_s']==.0005 and frame['source_entity']['native_id']==2
    other=output/'native/frame0002.vtk';raw=other.read_bytes();other.write_bytes(raw.replace(b'-100',b'-200'))
    # Selected file only succeeds; full verification must reject other-file damage.
    assert select_frame(outcome,output,index=1,quantity='velocity',component='Z',identity=2)['value']==-100.
    with pytest.raises(ValueError,match='hash|size'):
        select_frame(outcome,output,index=1,quantity='velocity',component='Z',identity=2,verification='all')
    with pytest.raises(ValueError,match='metadata_only'):
        select_frame(outcome,output,index=1,quantity='velocity',component='Z',identity=2,metadata_only=True)
    target=output/'native/frame0001.vtk';raw=target.read_bytes();target.write_bytes(raw.replace(b'-100',b'-300'))
    with pytest.raises(ValueError,match='hash|size'):
        select_frame(outcome,output,index=1,quantity='velocity',component='Z',identity=2)


def test_unknown_arrays_and_exact_missing_or_inactive_values(tmp_path,monkeypatch):
    install_boundary_double(monkeypatch);output=tmp_path/'attempt';result=run(BACKEND,definition(),output=output)
    assert all('Unknown' not in name for name in result['native_channels'])
    assert b'Unknown_Force' in (output/'native/frame0001.vtk').read_bytes()
    assert b'Unknown_Force' not in (output/'post/frame0001.vtu').read_bytes()
    outcome=result['diagnostics']['native_outcome']
    with pytest.raises(ValueError):select_frame(outcome,output,index=1,quantity='velocity',component='Z',identity=99)
    # An explicit synthetic second attempt with inactive element; never alter the
    # old receipt to bless tampering. Build its own receipt and retain old failure.
    new=tmp_path/'eroded';shutil.copytree(output,new)
    path=new/'native/frame0001.vtk';path.write_text(vtk(.0005,active=0))
    record=json.loads((new/'impact_execution.json').read_text(encoding='utf-8'))
    from caelab.adapters.impact_results import read_vtk
    record['retained_native']['frames'][1]=frame_record(new,path,read_vtk(path))
    record['execution_status']='FAILED';save_json(new/'impact_execution.json',record)
    value=select_frame(reference(new),new,index=1,quantity='velocity',component='Z',identity=2)
    assert value['value'] is None and value['status']=='UNKNOWN' and value['original_execution_status']=='FAILED'


def test_invalid_native_draft_save_then_apply_cold_without_runtime(tmp_path,monkeypatch):
    from caelab.impact_input_workflow import inspect,apply_text,admitted_guard_paths
    from caelab.impact_input_edits import original_files
    workspace=tmp_path/'workspace';wb=Workbench(workspace,configuration={'workers':1})
    try:
        s=definition();source=s['source'];file='impact_0000.rad';raw=original_files(source)[file];start=raw.index(b'/END')
        edit=apply_text(s,file=file,start=start,end=start,replacement='/UNSUPPORTED/LAW/99\r\n',reason='UNIT draft',expected_definition_sha256=canonical_hash(s))
        blocked=edit['settings'];assert edit['inspection']['readiness']=='BLOCKED'
        doc=wb.document_open(kind='simulation',draft={'backend':BACKEND,'settings':blocked})
        doc=change(wb,doc,'document.save')['document'];identifier=doc['id']
        with pytest.raises(ValueError):change(wb,doc,'simulation.evaluate')
        assert len(wb.manager.list())==0
        # Captured member paths alone are admitted. An unrelated execution path is not.
        assert wb._settings(BACKEND,s)==s
        forged=deepcopy(s);forged['source']['provenance']['path']='C:/arbitrary.exe'
        with pytest.raises(ValueError,match='path'):wb._settings(BACKEND,forged)
    finally:assert wb.shutdown()['joined']
    fresh=Workbench(workspace,configuration={'workers':1})
    try:
        doc=fresh.document_open(kind='simulation',document_id=identifier)
        assert doc['draft']['settings']==blocked and doc['diagnostics']
        doc=change(fresh,doc,'simulation.update',{'draft':{'backend':BACKEND,'settings':s}})['document']
        assert not doc['diagnostics'];assert len(fresh.manager.list())==0
        doc=change(fresh,doc,'document.undo')['document'];assert doc['draft']['settings']==blocked
        doc=change(fresh,doc,'document.redo')['document'];assert doc['draft']['settings']==s
    finally:assert fresh.shutdown()['joined']


def test_same_owner_explicit_readback_job_original_failure_is_not_rewritten(tmp_path,monkeypatch):
    calls=install_boundary_double(monkeypatch);wb=Workbench(tmp_path/'workspace',configuration={'workers':1})
    try:
        s=definition();doc=wb.document_open(kind='simulation',draft={'backend':BACKEND,'settings':s})
        reply=change(wb,doc,'simulation.evaluate');doc=reply['document'];job=wait(wb,reply['job'])
        assert job['state']=='SUCCEEDED',job
        first=wb.document_result(doc['id'],job['id'],selection={'metadata_only':True})
        before=canonical_hash(first);calls_before=list(calls)
        # Make a new reader job of retained, already converted VTK/CSV. Runtime
        # lookup and all subprocess calls are forbidden for this path.
        def forbidden(*a,**kw):raise AssertionError('solver/converter call in convert_raw=False readback')
        monkeypatch.setattr('caelab.adapters.impact.selected_runtime',forbidden)
        monkeypatch.setattr('caelab.adapters.impact.run_owned_command',forbidden)
        monkeypatch.setattr('caelab.impact_recovery.run_owned_command',forbidden)
        command_id='C'+uuid.uuid4().hex
        reply=change(wb,doc,'simulation.reprocess',{'source_job_id':job['id'],'convert_raw':False},command_id)
        repeated=change(wb,doc,'simulation.reprocess',{'source_job_id':job['id'],'convert_raw':False},command_id)
        assert repeated['job']['id']==reply['job']['id']
        doc=reply['document'];readjob=wait(wb,reply['job']);assert readjob['state']=='SUCCEEDED',readjob
        readresult=wb.document_result(doc['id'],readjob['id'],selection={'responses':['impact.displacement.Z@2']})
        assert readresult['solver_execution']=='NOT_PERFORMED' and readresult['operation_kind']=='READBACK_ONLY'
        assert readresult['source_job_id']==job['id'] and calls==calls_before
        assert readresult['responses']['impact.displacement.Z@2']['value']==pytest.approx([0.,-.05,-.1])
        assert canonical_hash(wb.document_result(doc['id'],job['id'],selection={'metadata_only':True}))==before
        doc=change(wb,doc,'document.save')['document'];docid=doc['id'];rid=readjob['id']
    finally:assert wb.shutdown()['joined']
    fresh=Workbench(tmp_path/'workspace',configuration={'workers':1})
    try:
        fresh.document_open(kind='simulation',document_id=docid)
        readresult=fresh.document_result(docid,rid,selection={'responses':['impact.velocity.Z@1']})
        assert readresult['responses']['impact.velocity.Z@1']['value']==[-100.]*3
        assert readresult['solver_execution']=='NOT_PERFORMED' and len(fresh.manager.list())==2
    finally:assert fresh.shutdown()['joined']


def test_original_failed_postflight_can_have_new_successful_readback_without_rewriting(tmp_path,monkeypatch):
    from caelab.adapters import impact
    calls=install_boundary_double(monkeypatch)
    original_writer=impact.write_post
    def fail_once(*a,**kw):raise ValueError('UNIT injected Post failure after actual reader retained frame pins')
    monkeypatch.setattr(impact,'write_post',fail_once)
    wb=Workbench(tmp_path/'workspace',configuration={'workers':1})
    try:
        s=definition();doc=wb.document_open(kind='simulation',draft={'backend':BACKEND,'settings':s})
        reply=change(wb,doc,'simulation.evaluate');doc=reply['document'];job=wait(wb,reply['job'])
        assert job['state']=='FAILED'
        first=wb.document_result(doc['id'],job['id'],selection={'metadata_only':True});before=canonical_hash(first)
        assert first['execution_status']=='FAILED' and first['diagnostics']['native_execution_status']=='SUCCEEDED'
        # Reading partial frames does not relabel the old execution.
        part=wb.document_result(doc['id'],job['id'],selection={'responses':['impact.velocity.Z@1']})
        assert part['execution_status']=='FAILED' and part['responses']['impact.velocity.Z@1']['value']==[-100.]*3
        monkeypatch.setattr(impact,'write_post',original_writer)
        def forbidden(*a,**kw):raise AssertionError('No process in reader-only recovery')
        monkeypatch.setattr(impact,'selected_runtime',forbidden);monkeypatch.setattr(impact,'run_owned_command',forbidden)
        monkeypatch.setattr('caelab.impact_recovery.run_owned_command',forbidden)
        count=len(calls)
        reply=change(wb,doc,'simulation.reprocess',{'source_job_id':job['id'],'convert_raw':False})
        doc=reply['document'];new=wait(wb,reply['job']);assert new['state']=='SUCCEEDED',new
        result=wb.document_result(doc['id'],new['id'],selection={'responses':['impact.displacement.Z@2']})
        assert result['source_execution_status']=='FAILED' and result['execution_status']=='SUCCEEDED'
        assert result['solver_execution']=='NOT_PERFORMED' and len(calls)==count
        assert canonical_hash(wb.document_result(doc['id'],job['id'],selection={'metadata_only':True}))==before
        # Full original bundle (not merely its manifest) accompanies the new read job.
        target=wb.root/'results'/new['id']/'calculation'
        original=wb.root/'results'/job['id']/'calculation'
        old_files=list((original/'source_bundle').rglob('*'))
        assert any(p.is_file() and p.name.endswith('.rad') for p in old_files)
        for p in old_files:
            if p.is_file():assert (target/p.relative_to(original)).read_bytes()==p.read_bytes()
        change(wb,doc,'document.save')
    finally:assert wb.shutdown()['joined']


@pytest.mark.parametrize('source_state,lost_response',[
    ('SUCCEEDED',False),('FAILED',True),('CANCELLED',True)])
def test_reprocess_after_edit_binds_old_input_identity_and_lost_response(tmp_path,monkeypatch,source_state,lost_response):
    """D1 authority/edits stay current; the separate read job is about D0."""
    from caelab.adapters import impact
    from caelab.execution_control import ExecutionCancelled
    from caelab.impact_input_workflow import inspect,apply_native_field
    calls=install_boundary_double(monkeypatch);writer=impact.write_post
    if source_state!='SUCCEEDED':
        def source_failure(*a,**kw):
            if source_state=='CANCELLED':raise ExecutionCancelled('UNIT cancelled after retained frames')
            raise ValueError('UNIT failed after retained frames')
        monkeypatch.setattr(impact,'write_post',source_failure)
    wb=Workbench(tmp_path/'workspace',configuration={'workers':1})
    try:
        doc=wb.document_open(kind='simulation',draft={'backend':BACKEND,'settings':definition()})
        reply=change(wb,doc,'simulation.evaluate');doc=reply['document'];source=wait(wb,reply['job'])
        assert source['state']==source_state
        doc=change(wb,doc,'document.save')['document']
        original=deepcopy(next(r for r in doc['runs'] if r['job_id']==source['id']))
        original_result=canonical_hash(wb.document_result(doc['id'],source['id'],selection={'metadata_only':True}))
        monkeypatch.setattr(impact,'write_post',writer)
        settings=doc['draft']['settings'];field=next(f for f in inspect(settings)['fields'] if f['field']=='end_s')
        amended=apply_native_field(settings,field['id'],.002,reason='UNIT D1 input edit',
            expected_definition_sha256=canonical_hash(settings))['settings']
        doc=change(wb,doc,'simulation.update',{'draft':{'backend':BACKEND,'settings':amended}})['document']
        d1=deepcopy(doc);assert d1['input_revision']!=original['input_revision']
        count=len(calls)
        def forbidden(*a,**kw):raise AssertionError('Re-read started a process')
        monkeypatch.setattr(impact,'selected_runtime',forbidden)
        monkeypatch.setattr(impact,'run_owned_command',forbidden)
        monkeypatch.setattr('caelab.impact_recovery.run_owned_command',forbidden)
        owner=wb.simulation_documents;persist=owner._persist_draft
        cid='C'+uuid.uuid4().hex
        if lost_response:
            armed=[True];prepared_inputs=[]
            def lose_once(value):
                if armed[0] and any(r.get('operation')=='impact.reprocess' for r in value['runs']):
                    armed[0]=False
                    receipt=owner._folder(doc['id'])/'commands'/(cid+'.json')
                    pending=json.loads(receipt.read_text(encoding='utf-8'))
                    prepared_inputs.append(deepcopy(pending))
                    if source_state=='FAILED':
                        # Pending pre-context-hook A receipts recover the same D0
                        # identity from their original run, never today's D1.
                        pending.pop('submitted_input_context')
                        save_json(receipt,pending)
                    raise OSError('UNIT response lost after read job submission')
                return persist(value)
            monkeypatch.setattr(owner,'_persist_draft',lose_once)
            with pytest.raises(OSError,match='response lost'):
                change(wb,doc,'simulation.reprocess',{'source_job_id':source['id'],'convert_raw':False},cid)
            monkeypatch.setattr(owner,'_persist_draft',persist)
            doc=wb.document_read(doc['id'])
            run=next(r for r in doc['runs'] if r['operation']=='impact.reprocess')
            readjob=wait(wb,wb.manager.status(run['job_id']))
            repeated=change(wb,d1,'simulation.reprocess',{'source_job_id':source['id'],'convert_raw':False},cid)
            assert repeated['job']['id']==readjob['id']
            assert run['recovered_after_response_loss'] is True
            assert prepared_inputs[0]['input_revision']==d1['input_revision']
            assert prepared_inputs[0]['submitted_input_context']=={
                'input_revision':original['input_revision'],'input_generation':original['input_generation']}
        else:
            reply=change(wb,doc,'simulation.reprocess',{'source_job_id':source['id'],'convert_raw':False},cid)
            doc=reply['document'];readjob=wait(wb,reply['job'])
        assert readjob['state']=='SUCCEEDED',readjob
        doc=wb.document_read(doc['id']);run=next(r for r in doc['runs'] if r['job_id']==readjob['id'])
        for key in ('input_generation','input_revision','input_sha256','draft'):
            assert run[key]==original[key]
        for key in ('draft','generation','input_revision'):
            assert doc[key]==d1[key]
        assert len(calls)==count and len(wb.manager.list())==2
        result=wb.document_result(doc['id'],readjob['id'],selection={'responses':['impact.velocity.Z@1']})
        assert result['source_execution_status']==source_state and result['solver_execution']=='NOT_PERFORMED'
        assert wb.manager.status(source['id'])['state']==source_state
        assert canonical_hash(wb.document_result(doc['id'],source['id'],selection={'metadata_only':True}))==original_result
        doc=change(wb,doc,'document.save')['document'];identifier=doc['id'];jid=readjob['id']
        reference=wb.document_result_reference(identifier,jid)
        assert reference['input_revision']==original['input_revision'] and reference['input_sha256']==original['input_sha256']
    finally:assert wb.shutdown()['joined']
    cold=Workbench(tmp_path/'workspace',configuration={'workers':1})
    try:
        reopened=cold.document_open(kind='simulation',document_id=identifier)
        assert reopened['draft']==d1['draft'] and reopened['input_revision']==d1['input_revision']
        assert cold.document_result_reference(identifier,jid)==reference
        assert len(cold.manager.list())==2
    finally:assert cold.shutdown()['joined']
