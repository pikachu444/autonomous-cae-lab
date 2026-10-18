"""Bounded read of the exact retained finite-measure case; no new calculation."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import threading
import time
import shutil
import hashlib

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from apps.lab.service import LabService
from apps.lab.server import LabHTTPServer
from caelab.workbench_client import Client
from caelab.storage import canonical_hash
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from apps.research.appearance import apply_appearance
from apps.research.finite_measure_dialog import FiniteAuditDialog, FinitePredictionDialog
from apps.research.material_test_dialog import ExperimentDialog
from apps.research.numerical_window import NumericalWindow


def wait(app,ready):
    end=time.monotonic()+60
    while True:
        app.processEvents()
        if ready():return
        if time.monotonic()>end:raise TimeoutError('retained Qt read')
        time.sleep(.01)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--adoption-boundary',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    checkpoint=json.loads((args.case/'checkpoint.json').read_text(encoding='utf-8'))
    store=args.case/'store'
    if args.adoption_boundary:
        store=args.output/'store';shutil.copytree(args.case/'store',store)
    (args.output/'checkpoint.json').write_bytes((args.case/'checkpoint.json').read_bytes())
    source_hashes={}
    for source in (Path(__file__),ROOT/'apps/research/finite_measure_dialog.py',ROOT/'apps/research/material_test_dialog.py',ROOT/'apps/research/numerical_window.py'):
        raw=source.read_bytes();source_hashes[str(source.relative_to(ROOT))]=hashlib.sha256(raw).hexdigest()
        (args.output/('checked-'+source.name)).write_bytes(raw)
    app=QApplication([]);apply_appearance(app);windows=[]
    service=LabService(store);server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client(f'http://127.0.0.1:{server.server_port}')
    try:
        jobs=client.request('/api/workbench')['jobs'];plan=client.document_read(checkpoint['plan_id']);material=client.document_read(checkpoint['material_id'])
        fit=client.document_result(plan['id'],checkpoint['fit_job']);assert canonical_hash(fit)==checkpoint['fit_hash']
        detail=client.numerical_candidate_detail(plan['id'],checkpoint['fit_job'],'C000010')
        (args.output/'candidate-detail.json').write_text(json.dumps(detail,ensure_ascii=False,indent=2),encoding='utf-8')
        prediction=FinitePredictionDialog(detail['trials'][0]['raw_evaluation']);windows.append(prediction);prediction.show()
        app.processEvents();prediction.grab().save(str(args.output/'candidate-actual-state.png'))
        prediction.resize(800,680);app.processEvents();prediction.grab().save(str(args.output/'candidate-actual-state-narrow.png'))
        assert prediction.table.rowCount()==6
        frozen_trials=[]
        for trial in detail['trials']:
            curve=trial['curve'];assert curve['prediction_metadata']['measure']=='finite_Cauchy'
            frozen_trials.append(dict(role=trial['role'],mask=curve['mask'],sample_weights=curve['sample_weights'],
                weight=curve['weight'],scale=curve['scale'],frozen_inclusion=curve['frozen_fit_inclusion']))
        cases=[]
        for index,item in enumerate(checkpoint['data']):
            result=client.data_material('data.processing.result',dict(document_id=item['document_id'],processing_revision=item['processing_revision'],selection=['finite_sigma','finite_lambda']))
            (args.output/f'processing-{index}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            immutable=deepcopy(result);immutable['diagnostics']['processing_record'].pop('retained_revision',None)
            assert canonical_hash(immutable)==item['immutable_hash'], (canonical_hash(immutable),item['immutable_hash'])
            trial=plan['draft']['experiments'][index]
            audit=FiniteAuditDialog(result);windows.append(audit);audit.show()
            audit.channels.setCurrentIndex(audit.channels.findData('finite_sigma'));audit.table.setCurrentCell(1,0)
            app.processEvents();audit.grab().save(str(args.output/f'audit-{index}.png'))
            audit.resize(800,680);app.processEvents();audit.grab().save(str(args.output/f'audit-{index}-narrow.png'))
            dialog=ExperimentDialog(plan['draft']['material']['draft']['settings'],result,experiment=trial);windows.append(dialog);dialog.show()
            app.processEvents();dialog.grab().save(str(args.output/f'trial-{index}.png'))
            dialog.resize(800,680);app.processEvents();dialog.grab().save(str(args.output/f'trial-{index}-narrow.png'))
            dialog.reject();assert dialog.value is None
            cases.append(dict(source=item, role=trial['role'],weight=trial['weight'],scale=trial['scale'],observation_measure=result['responses']['finite_sigma']['measure'],driver=result['responses']['finite_lambda']['value']))
        boundary=None
        if args.adoption_boundary:
            window=NumericalWindow(client,document_id=plan['id'],poll_interval=0);windows.append(window);window.show()
            wait(app,lambda:window.document is not None and not window._busy and not window._callbacks)
            window._populate_runs(checkpoint['fit_job']);window.refresh_result()
            wait(app,lambda:checkpoint['fit_job'] in window._result_cache and not window._busy and not window._callbacks)
            for row in range(window.candidates.rowCount()):
                item=window.candidates.item(row,0)
                if (item.data(Qt.ItemDataRole.UserRole) or item.text())=='C000010':window.candidates.selectRow(row);break
            reference=checkpoint['evidence'][0];assert reference['candidate_id']=='C000010'
            window._accept_fit_evidence(reference)
            original=QMessageBox.question;confirmations=[]
            def question(parent,title,text,*more):
                confirmations.append(text)
                def cancel():
                    dialog=app.activeModalWidget();dialog.grab().save(str(args.output/'adoption-cancel.png'))
                    dialog.button(QMessageBox.StandardButton.Cancel).click()
                QTimer.singleShot(100,cancel)
                return original(parent,title,text,*more)
            QMessageBox.question=question
            try:
                window.adopt_candidate();wait(app,lambda:len(confirmations)==1 and not window._busy and not window._callbacks)
            finally:QMessageBox.question=original
            assert client.document_read(material['id'])==material
            QMessageBox.question=lambda *args:QMessageBox.StandardButton.Yes
            try:
                window.adopt_candidate();wait(app,lambda:not window._busy and not window._callbacks and '거절' in window.message.text())
            finally:QMessageBox.question=original
            boundary=dict(message=window.message.text(),refusal=window.message.toolTip(),confirmations=confirmations,
                pending_receipt=window._adoption_receipt,retry_enabled=window.retry_adoption_button.isEnabled())
            assert 'Material changed after this Plan was bound' in boundary['refusal']
            assert window._adoption_receipt is None
            window.resize(920,760);app.processEvents()
            window.grab().save(str(args.output/'adoption-blocked.png'))
            assert client.document_read(material['id'])==material
        assert client.document_read(plan['id'])==plan and client.document_read(material['id'])==material
        assert client.request('/api/workbench')['jobs']==jobs
        record=dict(status='PASS',case=str(args.case.resolve()),store=str(store.resolve()),source_hashes=source_hashes,
            plan_id=plan['id'],fit_hash=checkpoint['fit_hash'],cases=cases,jobs_before=len(jobs),jobs_after=len(jobs),new_runs=0,
            dialog_cancel_preserves=True,adoption_boundary=boundary,material_hash=canonical_hash(material['draft']))
        record['retained_trial_inclusion']=frozen_trials
        (args.output/'result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(record,ensure_ascii=False))
    finally:
        for window in reversed(windows):
            if hasattr(window,'_allow_close'):window._allow_close=True
            window.close()
        app.processEvents();server.shutdown();server.server_close();service.shutdown();thread.join(5)


if __name__=='__main__':main()
