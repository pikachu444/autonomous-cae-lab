"""Existing failed-candidate and immutable Report assets; never evaluate models."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import threading
import time
from types import SimpleNamespace
import uuid
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
SOURCE_NAMES=('apps/research/numerical_candidate_detail_window.py','caelab/numerical_candidate_detail.py',
              'caelab/numerical_candidate_evidence.py','tests/check_candidate_results_assets_windows.py')
SOURCE_BYTES={name:(ROOT/name).read_bytes() for name in SOURCE_NAMES}
from PySide6.QtWidgets import QApplication
from apps.research.appearance import apply_appearance
from apps.research.numerical_candidate_detail_window import NumericalCandidateDetailWindow
from caelab.storage import canonical_hash
from caelab.workbench_client import Client, WorkbenchHTTPError
from caelab.numerical_candidate_detail import client_read_candidate_detail
from caelab.numerical_candidate_evidence import resolve_candidate_evidence


def wait(app,ready):
    end=time.monotonic()+90
    while True:
        app.processEvents()
        if ready():return
        if time.monotonic()>end:raise TimeoutError('candidate asset Qt reply')
        time.sleep(.01)


def cmd(client,d,operation,arguments=None):
    return client.document_command(d['id'],operation,arguments or {},session_id=d['session_id'],
        expected_generation=d['generation'],command_id='C'+uuid.uuid4().hex)


def failed_source(app,source,out,*,prior=None):
    from _numerical_candidate_detail_support import DetailHost
    def forbidden(*args):raise AssertionError('Retained reads must not evaluate')
    store=Path(prior['store']) if prior else out/'store'
    if not prior:shutil.copytree(source,store)
    windows=[]
    with DetailHost(store,evaluator=forbidden) as host:
        try:
            jobs=host.manager.list()
            identifier=prior['document_id'] if prior else next((store/'documents').glob('N*')).name
            document=host.owner.open(document_id=identifier)
            job=prior['job_id'] if prior else document['runs'][0]['job_id']
            result=host.owner.result(identifier,job);original_hash=canonical_hash(result)
            candidate=prior['candidate_id'] if prior else next(c['candidate_id'] for c in result['candidates'] if c['execution_status']=='FAILED')
            client=SimpleNamespace(document_read=host.owner.read,document_result=host.owner.result,
                document_command=host.owner.command,status=host.manager.status,cancel=host.manager.cancel)
            client.numerical_candidate_detail=lambda doc,job,cid,**kw:client_read_candidate_detail(client,doc,job,cid,**kw)
            window=NumericalCandidateDetailWindow(client,document_id=identifier,session_id=host.owner.session_id,
                job_id=job,candidate_id=candidate,poll_interval=60000)
            windows.append(window);window.show()
            wait(app,lambda:window.view is not None and window._read_worker is None)
            assert window.view['candidate']['execution_status']=='FAILED'
            assert all(row['prediction'] is None for row in window.model.rows)
            window.evidence_purpose.setCurrentIndex(window.evidence_purpose.findData('failure_diagnostic'))
            if prior:reference=prior['reference']
            else:
                assert window.evidence_button.isEnabled();window.preserve_evidence()
                wait(app,lambda:not window._writing and window._evidence_reference is not None and window._read_worker is None)
                reference=deepcopy(window._evidence_reference)
            resolved=resolve_candidate_evidence(host.owner,reference,consumer='failure_report')
            assert not resolved['readiness']['success_judgment_permitted']
            assert resolved['readiness']['failure_diagnostic_permitted']
            for width,height in ((1320,820),(900,720)):
                window.resize(width,height);app.processEvents();window.grab().save(str(out/f'failed-{width}.png'))
            assert canonical_hash(host.owner.result(identifier,job))==original_hash
            assert host.manager.list()==jobs and host.dispatched==[]
            return dict(status='PASS',source=str(source),store=str(store.resolve()),document_id=identifier,job_id=job,
                candidate_id=candidate,result_hash=original_hash,reference=reference,snapshot_hash=canonical_hash(resolved),
                jobs_before=len(jobs),jobs_after=len(jobs),new_jobs=0,evaluator_calls=0,
                claim='Previously generated algebra candidate fixture; not material physics execution')
        finally:
            for window in windows:window.close()
            app.processEvents()


def report_asset(app,case,out,*,prior=None):
    from apps.lab.service import LabService
    from apps.lab.server import LabHTTPServer
    from apps.research.report_window import ReportWindow
    checkpoint=json.loads((case/'checkpoint.json').read_text(encoding='utf-8'))
    store=Path(prior['store']) if prior else out/'store'
    if not prior:shutil.copytree(case/'store',store)
    service=LabService(store);server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client(f'http://127.0.0.1:{server.server_port}');windows=[]
    try:
        jobs=client.request('/api/workbench')['jobs']
        plan=client.document_open(kind='numerical',document_id=checkpoint['plan_id'])
        original_fit=client.document_result(plan['id'],checkpoint['fit_job']);assert canonical_hash(original_fit)==checkpoint['fit_hash']
        if prior:
            report=ReportWindow(client,document_id=prior['report_id']);windows.append(report);report.show()
            wait(app,lambda:report.document is not None and bool(report.assets) and not report._busy and not report._workers)
            assert canonical_hash(report.document['draft'])==prior['report_draft_hash']
            reference=prior['reference']
        else:
            detail=NumericalCandidateDetailWindow(client,document_id=plan['id'],session_id=plan['session_id'],
                job_id=checkpoint['fit_job'],candidate_id='C000010',poll_interval=60000)
            windows.append(detail);detail.show();wait(app,lambda:detail.view is not None and detail._read_worker is None)
            detail.open_evidence_report()
            wait(app,lambda:bool(detail._report_windows) and detail._evidence_reference is not None)
            reference=deepcopy(detail._evidence_reference);report=detail._report_windows[0];windows.append(report)
            wait(app,lambda:report.document is not None and bool(report.assets) and not report._busy and not report._workers)
            report.save_document();wait(app,lambda:not report._busy and not report._workers and report.document.get('saved_revision') is not None)
        bindings=[s['asset'] for s in report.document['draft']['sections'] if s.get('asset')]
        content=client.report_content(report.document['id'],bindings)
        assert len(content['assets'])==1
        asset=content['assets'][0]
        assert asset['source_status']=='AVAILABLE'
        assert asset['content']['candidate_evidence']['reference']==reference
        assert asset['content']['report_intent']=='success_report'
        if prior:assert canonical_hash(asset['content'])==prior['asset_content_hash']
        report.resize(1000,740);app.processEvents();report.grab().save(str(out/'retained-candidate-report.png'))
        assert canonical_hash(client.document_result(plan['id'],checkpoint['fit_job']))==checkpoint['fit_hash']
        assert client.request('/api/workbench')['jobs']==jobs
        return dict(status='PASS',store=str(store.resolve()),report_id=report.document['id'],
            report_draft_hash=canonical_hash(report.document['draft']),reference=reference,
            asset_content_hash=canonical_hash(asset['content']),bindings=bindings,
            jobs_before=len(jobs),jobs_after=len(jobs),new_jobs=0,cold=bool(prior))
    finally:
        for window in reversed(windows):
            if hasattr(window,'_allow_close'):window._allow_close=True
            window.close()
        app.processEvents();server.shutdown();server.server_close();service.shutdown();thread.join(5)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',type=Path,required=True)
    parser.add_argument('--failed-source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prior',type=Path)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    for name,content in SOURCE_BYTES.items():(args.output/('checked-'+Path(name).name)).write_bytes(content)
    app=QApplication([]);apply_appearance(app)
    prior=json.loads((args.prior/'assets.json').read_text(encoding='utf-8')) if args.prior else None
    failed_out=args.output/'failed';failed_out.mkdir()
    report_out=args.output/'report';report_out.mkdir()
    failed=failed_source(app,args.failed_source,failed_out,prior=prior['failed'] if prior else None)
    report=report_asset(app,args.case,report_out,prior=prior['report'] if prior else None)
    result=dict(status='PASS',failed=failed,report=report,
        source_hashes={name:hashlib.sha256(content).hexdigest() for name,content in SOURCE_BYTES.items()},
        source_end_hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCE_NAMES})
    assert result['source_hashes']['apps/research/numerical_candidate_detail_window.py']==result['source_end_hashes']['apps/research/numerical_candidate_detail_window.py']
    (args.output/'assets.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
