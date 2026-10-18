"""Actual Qt/HTTP inspection of existing DP states, with zero new jobs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import threading
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from apps.research.appearance import apply_appearance
from apps.research.constitutive_inspection_window import ConstitutiveInspectionWindow
from apps.lab.service import LabService
from apps.lab.server import LabHTTPServer
from caelab.workbench_client import Client
from caelab.storage import canonical_hash
from caelab.law_native_fe import dp_observables


def wait(app,predicate):
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise TimeoutError('Retained constitutive Qt/HTTP reply')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    receipt=json.loads((args.source/'result.json').read_text(encoding='utf-8'))
    source=next(c for c in receipt['cases'] if c['name']=='dp_free')
    paths=('caelab/law_native_fe.py','caelab/law_native_inspection.py',
        'apps/research/constitutive_inspection_window.py','tests/check_case_a_inspection_windows.py')
    pins={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
    store=args.output/'store';shutil.copytree(args.source/'store',store)
    service=LabService(store);server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client(f'http://127.0.0.1:{server.server_port}');app=QApplication([]);apply_appearance(app)
    window=None
    try:
        jobs=client.request('/api/workbench')['jobs']
        doc=client.document_open(kind='material',document_id=source['document_id'])
        result=client.document_result(doc['id'],source['job_id'])
        assert canonical_hash(result)==source['result_hash']
        window=ConstitutiveInspectionWindow(client,doc['id'],source['job_id']);window.show()
        wait(app,lambda:window._data is not None)
        window.increment.setCurrentIndex(window.increment.findData(2))
        wait(app,lambda:window._data is not None and window._data['increment']==2)
        row=next(r for r in result['diagnostics']['constitutive_increments'] if r['increment']==2)
        run=next(r for r in doc['runs'] if r['job_id']==source['job_id'])
        expected=dp_observables(row['stress'],row['committed_state'],run['draft']['settings']['parameters'])
        actual={q['components'][0]:q['values'][0] for q in window._data['quantities'] if len(q['components'])==1}
        assert actual==dict(p=expected['pressure'],q=expected['equivalent_stress'],f=expected['yield_function'],
            **{'tr(εᵖ)':expected['plastic_volume_strain'],'κ':expected['kappa']})
        index=next(i for i in range(window.stress.rowCount()) if window.stress.item(i,1).text()=='p')
        window.stress.setCurrentCell(index,2);window.stress.scrollToBottom()
        for width,height in ((1320,820),(900,720)):
            window.resize(width,height);wait(app,lambda:window.width()==width)
            app.processEvents();window.stress.scrollToBottom();app.processEvents()
            assert window.grab().save(str(args.output/f'inspection-{width}.png'))
            assert window.stress.currentRow()==index
        assert client.document_read(doc['id'])==doc
        assert canonical_hash(client.document_result(doc['id'],source['job_id']))==source['result_hash']
        assert client.request('/api/workbench')['jobs']==jobs
        assert pins=={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
        report=dict(status='PASS',source_files=pins,source=source,selected_increment=2,
            observed=actual,original_document_unchanged=True,original_result_unchanged=True,
            jobs_before=len(jobs),jobs_after=len(jobs),new_jobs=0,
            input_claim='Actual Qt selection/capture; no physical OS mouse/keyboard claim')
        (args.output/'inspection.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
    finally:
        if window is not None:window.close();app.processEvents()
        server.shutdown();server.server_close();service.shutdown();thread.join(5)


if __name__=='__main__':main()
