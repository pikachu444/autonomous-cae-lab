"""Read exact retained candidates; no fit or detail evaluation is submitted."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import threading
import time
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
SOURCE_NAMES = ('apps/research/numerical_candidate_detail_window.py',
    'caelab/numerical_candidate_detail.py', 'caelab/numerical_candidate_evidence.py',
    'tests/check_candidate_results_workflow_windows.py')
SOURCE_BYTES = {name: (ROOT / name).read_bytes() for name in SOURCE_NAMES}
from apps.lab.service import LabService
from apps.lab.server import LabHTTPServer
from caelab.workbench_client import Client
from caelab.storage import canonical_hash
from PySide6.QtWidgets import QApplication
from apps.research.appearance import apply_appearance
from apps.research.numerical_candidate_detail_window import NumericalCandidateDetailWindow


def wait(app, ready):
    end = time.monotonic() + 60
    while True:
        app.processEvents()
        if ready(): return
        if time.monotonic() > end: raise TimeoutError('candidate retained read')
        time.sleep(.01)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--catalog', action='store_true')
    parser.add_argument('--actions', action='store_true')
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    checkpoint = json.loads((args.case / 'checkpoint.json').read_text(encoding='utf-8'))
    for name, content in SOURCE_BYTES.items():
        (args.output / ('checked-' + Path(name).name)).write_bytes(content)
    store = args.output / 'store'; shutil.copytree(args.case / 'store', store)
    app = QApplication([]); apply_appearance(app); windows = []
    service = LabService(store); server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True); thread.start()
    client = Client(f'http://127.0.0.1:{server.server_port}')
    try:
        jobs = client.request('/api/workbench')['jobs']
        plan = client.document_open(kind='numerical', document_id=checkpoint['plan_id'])
        material = client.document_open(kind='material', document_id=checkpoint['material_id'])
        fit = client.document_result(plan['id'], checkpoint['fit_job'])
        assert canonical_hash(fit) == checkpoint['fit_hash']
        view = client.numerical_candidate_detail(plan['id'], checkpoint['fit_job'], 'C000010')
        window = NumericalCandidateDetailWindow(client, document_id=plan['id'], session_id=plan['session_id'],
            job_id=checkpoint['fit_job'], candidate_id='C000010', source=view['source'], poll_interval=60000)
        windows.append(window); window.show()
        wait(app, lambda: window._read_worker is None and window.view is not None)
        for width, height in ((1320, 820), (900, 720)):
            window.resize(width, height); app.processEvents(); window.grab().save(str(args.output / f'detail-{width}.png'))
        assert window.candidate_id == 'C000010' and len(window.view['trials']) == 2
        actions = None
        if args.actions:
            import uuid
            from caelab.numerical_candidate_evidence import CAPTURE
            rows = deepcopy(window.model.rows)
            bad_source = deepcopy(view['source']); bad_source['result_sha256'] = '0' * 64
            arguments = dict(source=bad_source,candidate_id='C000010',attempt_job_id=None,purpose='success_judgment')
            window._write(lambda: window._owner_command(CAPTURE, arguments, 'C'+uuid.uuid4().hex),
                lambda value: (_ for _ in ()).throw(AssertionError('Changed source must be refused')))
            wait(app, lambda: not window._writing)
            assert '요청이 거절' in window.status.text() and 'HTTP 400' in window.status.toolTip()
            assert window.model.rows == rows and window.view is None
            refusal = dict(message=window.status.text(),diagnostic=window.status.toolTip())
            for width, height in ((1320, 820), (900, 720)):
                window.resize(width, height); app.processEvents(); window.grab().save(str(args.output / f'refusal-{width}.png'))
            window.refresh(); wait(app, lambda: window.view is not None and window._read_worker is None)
            assert window.model.rows == rows
            window.candidates.setCurrentIndex(window.candidates.findData('C000000'))
            wait(app, lambda: window.view is not None and window._read_worker is None)
            assert window.view['detail_eval_blocked'] == 'SELECT_LATEST_ATTEMPT'
            assert not window.detail_button.isEnabled() and window.latest_button.isEnabled()
            assert '최신 상세 선택' in window.evidence_state.text()
            window.resize(900,720);app.processEvents();window.grab().save(str(args.output / 'existing-attempt-guidance.png'))
            actions = dict(confirmed_refusal=refusal,old_rows_preserved=True,recovery_read=True,
                original_fit_retained=window.view['trials'][0]['retention'],
                original_holdout_retained=window.view['trials'][1]['retention'],
                existing_attempt_guidance=window.evidence_state.text())
            (args.output / 'actions.json').write_text(json.dumps(actions,ensure_ascii=False,indent=2),encoding='utf-8')
        catalog = None
        if args.catalog:
            from caelab.numerical_candidate_evidence import READ, COMPARE, ADOPTION_PREVIEW
            selected = []
            def capture(name):
                app.processEvents(); window.grab().save(str(args.output / (name + '.png')))
                selected.append(dict(name=name, candidate=window.candidate_id, attempt=window.attempt_job_id,
                    source=window.view['source'], candidate_status=window.view['candidate']['execution_status'],
                    missing=window.view['missing_experiments'], can_detail_eval=window.view['can_detail_eval'],
                    blocked=window.view.get('detail_eval_blocked'), latest=window.view.get('latest_attempt_job_id'),
                    trials=[{k: t.get(k) for k in ('experiment_id','role','retention','execution_status','evaluation_status')} for t in window.view['trials']]))
            window.resize(900, 720)
            window.trials.setCurrentItem(window.trials.topLevelItem(1)); capture('retained-holdout')
            window.candidates.setCurrentIndex(window.candidates.findData('C000000'))
            wait(app, lambda: window.view is not None and window._read_worker is None)
            capture('original-unretained')
            assert any(t['retention'] != 'RETAINED' for t in window.view['trials'])
            window.select_latest(); wait(app, lambda: window.view is not None and window._read_worker is None)
            capture('existing-detail-attempt')
            assert all(t['retention'] == 'RETAINED' for t in window.view['trials'])
            refs = checkpoint['evidence']
            reads = [client.numerical_evidence_command(plan['id'], READ, {'reference': reference, 'consumer': 'read'}) for reference in refs]
            preview = client.numerical_evidence_command(plan['id'], ADOPTION_PREVIEW, {'reference': refs[0]})
            comparison = client.numerical_evidence_command(plan['id'], COMPARE, {'left': refs[0], 'right': refs[1], 'experiment_id': view['trials'][0]['experiment_id']})
            catalog = dict(selections=selected, evidence_references=refs,
                evidence_read_hashes=[canonical_hash(item) for item in reads], preview=preview,
                comparison=comparison, original_candidate_states={c['candidate_id']: c['execution_status'] for c in view['candidates']})
            (args.output / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding='utf-8')
        assert client.document_read(plan['id']) == plan and client.document_read(material['id']) == material
        assert client.request('/api/workbench')['jobs'] == jobs
        result = dict(status='PASS', source=str(args.case.resolve()), plan_id=plan['id'], material_id=material['id'],
            fit_job=checkpoint['fit_job'], fit_hash=checkpoint['fit_hash'], source_identity=view['source'],
            candidate=view['candidate'], trials=[{k: t.get(k) for k in ('experiment_id','role','retention','execution_status','evaluation_status')} for t in view['trials']],
            jobs_before=len(jobs), jobs_after=len(jobs), new_jobs=0,
            source_hashes={name: hashlib.sha256(content).hexdigest() for name,content in SOURCE_BYTES.items()},
            source_end_hashes={name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCE_NAMES})
        assert result['source_hashes']['apps/research/numerical_candidate_detail_window.py'] == result['source_end_hashes']['apps/research/numerical_candidate_detail_window.py']
        (args.output / 'first-contact.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        (args.output / 'view.json').write_text(json.dumps(view, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
    finally:
        for window in reversed(windows): window.close()
        app.processEvents(); server.shutdown(); server.server_close(); service.shutdown(); thread.join(5)


if __name__ == '__main__': main()
