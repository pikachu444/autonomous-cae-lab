"""Narrow existing-owner failure/cancellation gates, not a new execution stack."""
from copy import deepcopy
import threading
import time
import pytest
from caelab.workbench import Workbench
from caelab.fatigue_example import csv_bytes,data_draft,settings
from caelab.fatigue_tensor import read_bundle
from caelab.storage import canonical_hash
from caelab.jobs import TERMINAL
from test_fatigue_workflow import wait


def command(wb,doc,op,args=None):
    return wb.document_command(doc['id'],op,args or {},session_id=doc['session_id'],expected_generation=doc['generation'])


def imported(wb):
    upload=wb.upload('synthetic-tensor.csv',csv_bytes())
    data=wb.document_open(kind='data',draft=data_draft(upload['id']))
    job=command(wb,data,'data.import')['job'];wait(wb,job)
    data=command(wb,wb.document_read(data['id']),'document.save')['document']
    return data,job,wb.document_result_reference(data['id'],job['id'])


def test_exact_saved_source_no_private_payload_and_save_failure_preserves_pointer(tmp_path,monkeypatch):
    wb=Workbench(tmp_path)
    try:
        data,import_job,ref=imported(wb);s=settings(ref)
        source_hash=canonical_hash(wb.document_result(data['id'],import_job['id']))
        bundle=read_bundle(wb,s['source'],method=s['method'],mean_stress=s['mean_stress'])
        assert len(bundle['responses'])==12
        stale=deepcopy(s['source']);stale['result']['result_sha256']='f'*64
        with pytest.raises(ValueError):read_bundle(wb,stale,method=s['method'],mean_stress=s['mean_stress'])
        from caelab.fatigue import validate_settings
        injected=deepcopy(s);injected['resolved_response']=bundle
        with pytest.raises(ValueError):validate_settings(injected)
        doc=wb.document_open(kind='simulation',draft={'backend':'damage.rainflow','settings':s})
        job=command(wb,doc,'simulation.evaluate')['job'];wait(wb,job)
        doc=command(wb,wb.document_read(doc['id']),'document.save')['document']
        result_hash=canonical_hash(wb.document_result(doc['id'],job['id']))
        pointer=wb.simulation_documents._folder(doc['id'])/'document.json';previous=pointer.read_bytes()
        draft=deepcopy(doc['draft']);draft['settings']['calibration']['conditions']='Explicit edited conditions retained after failed save'
        doc=command(wb,doc,'simulation.update',{'draft':draft})['document']
        from caelab import material_document
        real_save=material_document.save_json
        def fail_pointer(path,value):
            if path==pointer:raise OSError('INJECTED publication failure; not a real disk failure')
            return real_save(path,value)
        with monkeypatch.context() as m:
            m.setattr(material_document,'save_json',fail_pointer)
            with pytest.raises(OSError,match='INJECTED'):command(wb,doc,'document.save')
        assert pointer.read_bytes()==previous
        current=wb.document_read(doc['id'])
        assert current['draft']==draft and current['generation']==doc['generation']
        assert canonical_hash(wb.document_result(doc['id'],job['id']))==result_hash
        current=command(wb,current,'document.save')['document']
        assert pointer.read_bytes()!=previous and current['draft']==draft
        assert canonical_hash(wb.document_result(data['id'],import_job['id']))==source_hash
        assert len(wb.manager.list())==2
    finally:assert wb.shutdown()['joined']


def test_actual_job_cancellation_retains_two_planes_and_cold_reads_without_compute(tmp_path,monkeypatch):
    wb=Workbench(tmp_path);fresh=None;ready=threading.Event();release=threading.Event()
    try:
        data,import_job,ref=imported(wb);source_hash=canonical_hash(wb.document_result(data['id'],import_job['id']))
        from caelab import fatigue_strain
        real= fatigue_strain._plane;calls=[0]
        def blocked(*args):
            value=real(*args);calls[0]+=1
            if calls[0]==2:
                ready.set()
                if not release.wait(10):raise AssertionError('Owned cancellation coordination timeout')
            return value
        monkeypatch.setattr(fatigue_strain,'_plane',blocked)
        doc=wb.document_open(kind='simulation',draft={'backend':'damage.rainflow','settings':settings(ref)})
        job=command(wb,doc,'simulation.evaluate')['job']
        assert ready.wait(10)
        wb.manager.cancel(job['id']);release.set()
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            state=wb.manager.status(job['id'])
            if state['state'] in TERMINAL:break
            time.sleep(.005)
        assert state['state']=='CANCELLED',state
        result=wb.document_result(doc['id'],job['id'])
        assert result['execution_status']=='CANCELLED' and len(result['planes'])==2
        assert result['critical_plane_ids']==[] and 'miner_damage' not in result['responses']
        assert any(a['path'].endswith('cycle_assessment.json') for a in result['artifacts'])
        result_hash=canonical_hash(result)
        doc=command(wb,wb.document_read(doc['id']),'document.save')['document']
        assert doc['runs'][-1]['retained_state']=='CANCELLED'
        assert canonical_hash(wb.document_result(data['id'],import_job['id']))==source_hash
        assert wb.shutdown()['joined'];fresh=Workbench(tmp_path)
        count=len(fresh.manager.list());cold=fresh.document_open(kind='simulation',document_id=doc['id'])
        assert canonical_hash(fresh.document_result(cold['id'],job['id']))==result_hash
        assert len(fresh.manager.list())==count
    finally:
        release.set()
        if fresh:assert fresh.shutdown()['joined']
        else:assert wb.shutdown()['joined']
