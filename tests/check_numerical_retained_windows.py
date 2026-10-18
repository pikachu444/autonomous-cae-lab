"""Cold HTTP/Qt reading of an existing Numerical result; no run command."""
import json
import hashlib
from pathlib import Path
import sys
import threading

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_numerical_evaluation_workflow import wait


def main(store,folder,document_id,job_id):
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from apps.research.request_plan_window import RequestPlanWindow
    from caelab.storage import canonical_hash
    from caelab.workbench_client import Client

    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=False)
    app=QApplication.instance() or QApplication([])
    server=LabHTTPServer(LabService(Path(store).resolve()),0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client('http://127.0.0.1:'+str(server.server_port))
    before=client.document_read(document_id)
    result=client.document_result(document_id,job_id);result_hash=canonical_hash(result)
    submissions=[]
    def forbid_submit(*args,**kwargs):
        submissions.append('submit');raise AssertionError('Retained reading must not submit calculations')
    server.workbench.submit=forbid_submit
    jobs_before={r['job_id'] for r in before['runs']}
    window=RequestPlanWindow(client,document_id=document_id,poll_interval=0)
    children=[]
    def settled(predicate=lambda:True):
        wait(app,lambda:not window._busy and not window._callbacks and predicate(),lambda:window.message.text())
    try:
        window.show();settled(lambda:window.document is not None)
        row=next(i for i,r in enumerate(window.document['runs']) if r['job_id']==job_id)
        window.runs.selectRow(row);window.retry_result();settled(lambda:job_id in window._result_cache)
        assert canonical_hash(window._result_cache[job_id])==result_hash
        assert window.gradient_evidence.checks.rowCount()==8
        assert window.gradient_evidence.gradients.rowCount()>0
        window.tabs.setCurrentWidget(window.gradient_evidence)
        window.gradient_evidence.tabs.setCurrentIndex(2)
        ticks={}
        for width,height in ((1440,900),(1100,780)):
            window.resize(width,height);app.processEvents()
            window.gradient_evidence.canvas.draw()
            ticks[str(width)]={name:[label.get_text() for label in axis.get_majorticklabels()+axis.get_minorticklabels()
                if label.get_text()] for name,axis in (('x',window.gradient_evidence.axes.xaxis),('y',window.gradient_evidence.axes.yaxis))}
            assert all(text.isascii() and '$' not in text for labels in ticks[str(width)].values() for text in labels)
            assert window.grab().save(str(folder/f'adjoint-taylor-{width}.png'))
        window.gradient_evidence.tabs.setCurrentIndex(3)
        app.processEvents();assert window.grab().save(str(folder/'adjoint-residuals.png'))
        window.candidates.selectRow(0);window.open_candidate_results()
        child=window._candidate_result_windows[-1];children.append(child)
        wait(app,lambda:not child._busy and child._composite is not None,lambda:child.message.text())
        actual=child._composite
        assert actual['execution_status']=='SUCCEEDED'
        child.gradient_evidence.parentWidget().setCurrentWidget(child.gradient_evidence)
        app.processEvents();assert child.grab().save(str(folder/'candidate-exact-inputs.png'))
        after=client.document_read(document_id)
        assert canonical_hash(after['draft'])==canonical_hash(before['draft'])
        assert {r['job_id'] for r in after['runs']}==jobs_before
        assert canonical_hash(client.document_result(document_id,job_id))==result_hash
        assert not submissions
        record={'document_id':document_id,'job_id':job_id,'result_sha256':result_hash,
            'draft_sha256':canonical_hash(before['draft']),'new_jobs':0,'qt_platform':app.platformName(),
            'gradient_verification':result.get('gradient_verification'),
            'candidate_count':len(result.get('candidates',[])),
            'calculation_submissions':len(submissions),'taylor_tick_labels':ticks,
            'source_hashes':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (
                'apps/research/numerical_window.py','apps/research/request_plan_window.py',
                'apps/research/s2_gradient_widgets.py','apps/research/numerical_methods.py')}}
        (folder/'cold.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in record.items() if k!='gradient_verification'},ensure_ascii=False),flush=True)
    finally:
        for child in children:child.close()
        window._allow_close=True;window.close();app.processEvents()
        assert QThreadPool.globalInstance().waitForDone(5000)
        server.shutdown()
        try:assert server.workbench.shutdown(timeout=10)['joined']
        finally:server.server_close();thread.join(5)


if __name__=='__main__':main(*sys.argv[1:])
