"""Actual Windows-capable PDE owner/HTTP/Qt workflow; no provider or CAD.

Run this module directly to retain normal/narrow native Qt captures and a receipt.
The two explicit jobs use the existing SciPy and scikit-fem adapters unchanged.
"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest


def wait(app, predicate, message, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            app.processEvents()
            return
        # Yield the GIL to the real HTTP owner as well as processing Qt events.
        time.sleep(.01)
    raise AssertionError(message())


def cold_read(store, receipt):
    from PySide6.QtWidgets import QApplication
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from apps.research.pde_window import PDEWindow
    from caelab.workbench_client import Client
    from caelab.storage import canonical_hash
    app = QApplication.instance() or QApplication([])
    server = LabHTTPServer(LabService(store), 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    client = Client('http://127.0.0.1:' + str(server.server_port))
    window = PDEWindow(client, auto_open=False, poll_interval=0); window.show()
    try:
        jobs_before = len(server.workbench.manager.list())
        for record in receipt['models']:
            window.open_document(document_id=record['document_id'])
            wait(app, lambda: not window._busy and window.document and
                 window.document['id']==record['document_id'] and bool(window._result),
                 lambda: window.message.text())
            doc = window.document
            assert canonical_hash(doc['draft']) == record['draft_sha256']
            assert doc['saved_revision'] == record['saved_revision']
            assert window._selected_job == record['job_id']
            result = window._result
            assert canonical_hash(result) == record['result_sha256']
            assert window.grab().save(str(Path(store).parent / ('cold-'+record['backend'].split('.')[-1]+'.png')))
        assert len(server.workbench.manager.list()) == jobs_before
        return {'process_id': __import__('os').getpid(), 'same_saved_inputs_and_results': True,
                'new_jobs': 0, 'http_qt': True, 'qt_platform': app.platformName()}
    finally:
        window._allow_close=True; window.close(); app.processEvents()
        server.shutdown(); server.server_close(); thread.join(3)
        assert server.workbench.shutdown()['joined']


def run_workflow(folder, *, resume=False):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtTest import QTest
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from apps.research.pde_window import PDEWindow
    from caelab.workbench_client import Client
    from caelab.pde_document import default_draft
    from caelab.dimensioned_models import ODE, SCIKIT_WEAK
    from caelab.storage import canonical_hash
    import numpy as np

    folder = Path(folder).resolve(); folder.mkdir(parents=True, exist_ok=True)
    assert resume or not (folder / 'store').exists(), 'A fresh store is required'
    app = QApplication.instance() or QApplication([])
    server = LabHTTPServer(LabService(folder / 'store'), 0)
    thread = threading.Thread(target=server.serve_forever,
                              kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    client = Client('http://127.0.0.1:' + str(server.server_port))
    window = PDEWindow(client, auto_open=False, poll_interval=0)
    window.show()
    receipt = {'models': [], 'platform': __import__('os').name,
               'qt_platform': app.platformName(), 'provider_calls': 0, 'cad_calls': 0}

    def settled(predicate=lambda: True):
        wait(app, lambda: not window._busy and predicate(), lambda: window.message.text())

    def edit(path, value):
        # Use the existing tree and actual typed editor, including selection/focus.
        parent = max((p for p in window._nodes if path[:len(p)] == p), key=len)
        window.tree.setCurrentItem(window._nodes[parent]); app.processEvents()
        widget = window.fields[path][0]
        widget.setFocus(); widget.selectAll(); QTest.keyClicks(widget, value)
        assert widget.hasFocus()

    def capture(name):
        app.processEvents(); time.sleep(.1); app.processEvents()
        assert window.grab().save(str(folder / (name + '.png')))

    try:
        for backend in (ODE, SCIKIT_WEAK):
            if resume:
                candidates = client.documents()['documents']
                identifier = next(d['id'] for d in candidates if d['kind']=='pde' and
                                  client.document_read(d['id'])['draft']['backend']==backend)
                window.open_document(document_id=identifier)
            else:
                window.open_document(draft=default_draft(backend))
            settled(lambda: bool(window.document) and window.document['draft']['backend']==backend)
            assert window.document['draft']['backend'] == backend
            if not resume and backend == ODE:
                # A real invalid AST and a dimension mismatch stay editable/saveable.
                path = ('settings', 'states', 0, 'rhs')
                valid = '-rate*(temperature-ambient)'
                for invalid in ('sin(', 'temperature'):
                    edit(path, invalid); window.validate_inputs(); settled()
                    assert window.issue_summary.text()
                    window.save_document(); settled(lambda: not window.document['dirty'])
                    assert window.document['diagnostics'] and not window.evaluate_button.isEnabled()
                    assert len(server.workbench.manager.list()) == 0
                capture('ode-invalid-draft')
                edit(path, valid)
                edit(('settings', 'states', 0, 'initial'), '305')
                edit(('settings', 'states', 0, 'unit'), 'K')
                edit(('settings', 'parameters', 0, 'value'), '0.75')
                edit(('settings', 'parameters', 2, 'value'), '305')
            elif not resume:
                edit(('settings', 'parameters', 0, 'value'), '200')
                edit(('settings', 'parameters', 1, 'value'), '1000')
                edit(('settings', 'parameters', 0, 'unit'), 'W/(m*K)')
                edit(('settings', 'boundaries', 0, 'expression'), 'left_value')
                edit(('settings', 'forms', 'linear'), 'q*v')
                edit(('settings', 'mesh', 'levels', 0), '2')
                edit(('settings', 'mesh', 'levels', 1), '4')
                edit(('settings', 'reference'),
                     'left_value+(right_value-left_value)*x/length+q*x*(length-x)/(2*k)')
            before_jobs = len(server.workbench.manager.list())
            if not resume:
                window.validate_inputs(); settled()
                assert window.issue_summary.isHidden(), window.issue_summary.text()
                assert len(server.workbench.manager.list()) == before_jobs
                window.apply_inputs(); settled()
                assert window.evaluate_button.isEnabled(), window.message.text()
                # Check/apply/save have not submitted the numerical job.
                assert len(server.workbench.manager.list()) == before_jobs
                window.evaluate_button.click(); settled(lambda: bool(window._selected_job))
            job = window._selected_job
            if not resume:
                wait(app, lambda: client.status(job)['state'] in {'SUCCEEDED','FAILED','REJECTED','CANCELLED'},
                     lambda: str(client.status(job)))
            window.refresh_document(); settled()
            window.refresh_result(); settled(lambda: bool(window._result))
            result = deepcopy(window._result)
            assert result['execution_status'] == 'SUCCEEDED', result
            if backend == ODE:
                series = result['responses']['temperature']
                clock = np.asarray(series['axes'][0]['values'])
                expected = 290 + 15 * np.exp(-.75 * clock)
                assert np.max(np.abs(np.asarray(series['value']) - expected)) < 1e-4
                assert result['diagnostics']['residual'] == 'NOT_REPORTED_BY_SOLVER'
                assert '솔버가 보고하지 않음' in window.result_label.text()
                observed = {'max_abs_reference_error_K': float(np.max(np.abs(np.asarray(series['value'])-expected))),
                            'residual': result['diagnostics']['residual'],
                            'accepted_steps': result['diagnostics']['accepted_steps']}
            else:
                rows = result['diagnostics']['mesh_studies']
                assert len(rows) == 2
                assert all(r['free_dofs'] > 0 and r['relative_residual'] <= 1e-9 for r in rows)
                assert rows[1]['l2_error'] < rows[0]['l2_error']
                assert rows[1]['h1_seminorm_error'] < rows[0]['h1_seminorm_error']
                window.open_mesh_study(); app.processEvents()
                study = window._mesh_study_windows[-1]
                assert study.rows == rows and rows[0]['norm_definition'] in study.detail.text()
                assert study.grab().save(str(folder / 'p1-original-norms.png'))
                study.close()
                observed = {'mesh_studies': rows,
                            'physical_qualification': result['diagnostics'].get('physical_qualification')}
                field_index = next(i for i in reversed(range(window.result_selector.count()))
                                   if window.result_selector.itemData(i)[0] == 'field')
                window.result_selector.setCurrentIndex(field_index)
                app.processEvents()
                assert window.field_node.count() == rows[-1]['dofs']
            window.resize(1440, 900); capture(('ode' if backend == ODE else 'p1') + '-normal')
            window.resize(1100, 780); capture(('ode' if backend == ODE else 'p1') + '-narrow')
            retained_hash = canonical_hash(result)
            if not resume or window.document['dirty']:
                window.save_document(); settled(lambda: not window.document['dirty'])
            # Navigation/reload reads the exact retained job. It must never evaluate.
            window.refresh_result(); settled()
            assert canonical_hash(window._result) == retained_hash
            assert len(server.workbench.manager.list()) == before_jobs + (0 if resume else 1)
            doc = window.document
            record = {'backend': backend, 'document_id': doc['id'], 'job_id': job,
                      'input_revision': doc['input_revision'], 'saved_revision': doc['saved_revision'],
                      'draft_sha256': canonical_hash(doc['draft']), 'result_sha256': retained_hash,
                      'observed': observed}
            receipt['models'].append(record)
            (folder / 'workflow.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(record, ensure_ascii=False), flush=True)
        # Existing abandon Cancel preserves current accepted input/result and unsaved editor.
        accepted_draft = deepcopy(window.document['draft']); selected = window._selected_job
        edit(('settings','forms','linear'), '2*q*v')
        edited = deepcopy(window.edited_draft())
        original_question = QMessageBox.question
        QMessageBox.question = lambda *a, **k: QMessageBox.StandardButton.Cancel
        try:
            called = []
            assert window._abandon(lambda: called.append(True)) is False
            assert not called and window.edited_draft() == edited
            assert window.document['draft'] == accepted_draft and window._selected_job == selected
        finally:
            QMessageBox.question = original_question
        receipt['abandon_cancel_preserved'] = True
        # Preserve the saved accepted state; the deliberate unsaved editor is discarded on close.
    finally:
        window._allow_close = True; window.close(); app.processEvents()
        server.shutdown(); server.server_close(); thread.join(3)
        assert server.workbench.shutdown()['joined']
    (folder / 'workflow.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    cold = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--cold', str(folder)],
                          cwd=str(Path(__file__).resolve().parents[1]), capture_output=True,
                          text=True, encoding='utf-8', timeout=30)
    (folder / 'cold-stdout.log').write_text(cold.stdout, encoding='utf-8')
    (folder / 'cold-stderr.log').write_text(cold.stderr, encoding='utf-8')
    assert cold.returncode == 0, cold.stderr
    receipt['cold_reopen'] = json.loads(cold.stdout)
    (folder / 'workflow.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    return receipt


def test_actual_http_qt_ode_p1_save_and_cold_reopen(tmp_path):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    pytest.importorskip('PySide6'); pytest.importorskip('skfem')
    receipt = run_workflow(tmp_path / 'pde-workflow')
    assert receipt['cold_reopen']['same_saved_inputs_and_results']


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    if sys.argv[1] == '--cold':
        folder = Path(sys.argv[2])
        print(json.dumps(cold_read(folder / 'store', json.loads((folder / 'workflow.json').read_text(encoding='utf-8')))))
    else:
        run_workflow(sys.argv[1], resume='--resume' in sys.argv[2:])
