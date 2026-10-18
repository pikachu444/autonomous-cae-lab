"""Bounded mixed-control UI checks; retained reads never submit calculations."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import threading
import time
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.lab.service import LabService
from apps.lab.server import LabHTTPServer
from caelab.storage import canonical_hash
from caelab.workbench_client import Client
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from apps.research.appearance import apply_appearance


def first_contact(case, output):
    from apps.research.material_control_dialog import MaterialControlDialog
    checkpoint = json.loads((case / 'checkpoint.json').read_text(encoding='utf-8'))
    app = QApplication.instance() or QApplication([])
    apply_appearance(app)
    service = LabService(case / 'store')
    server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    client = Client(f'http://127.0.0.1:{server.server_port}')
    windows = []
    try:
        jobs = client.request('/api/workbench')['jobs']
        plan = client.document_read(checkpoint['plan_id'])
        material = client.document_read(checkpoint['material_id'])
        fit = client.document_result(plan['id'], checkpoint['fit_job'])
        assert canonical_hash(fit) == checkpoint['fit_hash']
        detail = client.numerical_candidate_detail(plan['id'], checkpoint['fit_job'], 'C000010')
        capabilities = {model: client.data_material('material.control.capabilities', {'model': model})
                        for model in ('neo_hooke', 'drucker_prager_linear', 'single_branch_maxwell')}
        settings = plan['draft']['material']['draft']['settings']
        original = deepcopy(settings)
        dialog = MaterialControlDialog(client, settings)
        windows.append(dialog)
        dialog.show()
        app.processEvents()
        dialog.grab().save(str(output / 'existing-control.png'))
        dialog.reject()
        assert dialog.result_settings is None and settings == original
        assert client.document_read(plan['id']) == plan
        assert client.document_read(material['id']) == material
        assert client.request('/api/workbench')['jobs'] == jobs
        result = dict(status='PASS', source=str(case.resolve()), plan_id=plan['id'],
                      material_id=material['id'], fit_job=checkpoint['fit_job'],
                      fit_hash=checkpoint['fit_hash'], capabilities=capabilities,
                      trial_evaluations=[t['raw_evaluation']['execution_status'] for t in detail['trials']],
                      jobs_before=len(jobs), jobs_after=len(jobs), new_runs=0, cancel_preserves=True)
        (output / 'first-contact.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
    finally:
        for window in reversed(windows):
            window.close()
        app.processEvents()
        server.shutdown(); server.server_close(); service.shutdown(); thread.join(5)


def editor_check(inputs, output):
    from apps.research.material_control_gui import MixedControlDialog
    app = QApplication.instance() or QApplication([]); apply_appearance(app)
    records = []
    for case in inputs['cases'][:4]:
        dialog = MixedControlDialog(None, case['settings'])
        try:
            original = deepcopy(case['settings'])
            dialog.show(); app.processEvents()
            for width, height in ((1160, 720), (780, 620)):
                dialog.resize(width, height); dialog.table.setCurrentCell(1, 1); dialog.table.setFocus()
                app.processEvents(); dialog.grab().save(str(output / f"{case['name']}-{width}.png"))
            assert dialog.draft_settings() == original
            if case['name'] == 'neo_free':
                dialog.table.item(1, 1).setText('1e'); assert not dialog.validate_draft()
                app.processEvents(); dialog.grab().save(str(output / 'incomplete-draft.png'))
                dialog.table.item(1, 1).setText(str(original['deformation_gradient'][1][0][0]))
                assert dialog.validate_draft()
            dialog.reject(); assert dialog.result_settings is None and case['settings'] == original
            records.append(dict(case=case['name'], cancel_preserves=True, no_change_exact=True))
        finally: dialog.close(); app.processEvents()
    (output / 'editor.json').write_text(json.dumps(dict(status='PASS', checks=records, new_runs=0), indent=2), encoding='utf-8')


def command(client, document, operation, arguments=None):
    import uuid
    return client.document_command(document['id'], operation, arguments or {},
        session_id=document['session_id'], expected_generation=document['generation'], command_id='C' + uuid.uuid4().hex)


def calculated_check(inputs, output, *, store=None, expected=None):
    """Six predeclared existing Point jobs, or read-only cold verification."""
    from apps.research.material_control_gui import MixedControlResultDialog
    from caelab.numerical_document import from_material_document
    app = QApplication.instance() or QApplication([]); apply_appearance(app)
    store = store or output / 'store'
    service = LabService(store); server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True); thread.start()
    client = Client(f'http://127.0.0.1:{server.server_port}'); windows = []
    try:
        jobs_before = len(client.request('/api/workbench')['jobs']); records = []; results = {}
        if expected is None:
            assert jobs_before == 0 and inputs['maximum_jobs'] == 6 and len(inputs['cases']) == 6
            for case in inputs['cases']:
                document = client.document_open(kind='material', title='합성 혼합 제어 ' + case['name'],
                    draft={'backend': 'material.law_native', 'settings': case['settings']})
                response = command(client, document, 'material.evaluate')
                job = response['job']; document = response['document']
                end = time.monotonic() + 60
                while job['state'] not in {'SUCCEEDED', 'FAILED', 'REJECTED', 'CANCELLED', 'INTERRUPTED'}:
                    app.processEvents()
                    if time.monotonic() > end: raise TimeoutError(case['name'])
                    time.sleep(.02); job = client.status(job['id'])
                result = client.document_result(document['id'], job['id'])
                assert result['execution_status'] == case['expected_status'], (case['name'], result)
                document = client.document_read(document['id'])
                saved = command(client, document, 'document.save')['document']
                assert saved['draft']['settings'] == case['settings']
                records.append(dict(name=case['name'], document_id=saved['id'], job_id=job['id'],
                    result_hash=canonical_hash(result), settings_hash=canonical_hash(case['settings']),
                    initial_state_hash=canonical_hash(case['settings']['initial_state']), saved_revision=saved['saved_revision'],
                    expected_status=case['expected_status']))
                results[case['name']] = result
            material = client.document_read(records[0]['document_id'])
            plan = client.document_open(kind='numerical', title='합성 혼합 제어 계획', draft=from_material_document(material))
            plan = command(client, plan, 'document.save')['document']
            assert plan['draft']['material']['draft']['settings'] == inputs['cases'][0]['settings']
            plan_receipt = dict(document_id=plan['id'], draft_hash=canonical_hash(plan['draft']), saved_revision=plan['saved_revision'])
        else:
            records = expected['cases']; plan_receipt = expected['plan']
            for item in records:
                document = client.document_open(kind='material', document_id=item['document_id'])
                result = client.document_result(document['id'], item['job_id'])
                assert canonical_hash(result) == item['result_hash']
                assert canonical_hash(document['draft']['settings']) == item['settings_hash']
                results[item['name']] = result
            plan = client.document_open(kind='numerical', document_id=plan_receipt['document_id'])
            assert canonical_hash(plan['draft']) == plan_receipt['draft_hash']
        for item, case in zip(records, inputs['cases']):
            result = results[item['name']]
            dialog = MixedControlResultDialog(result, case['settings']); windows.append(dialog)
            dialog.show(); dialog.increment.setCurrentIndex(min(1, dialog.increment.count()-1)); app.processEvents()
            for width, height in ((1120, 760), (780, 620)):
                dialog.resize(width, height); app.processEvents()
                dialog.grab().save(str(output / f"result-{item['name']}-{width}.png"))
            dialog.tabs.setCurrentWidget(dialog.states); app.processEvents()
            dialog.grab().save(str(output / f"states-{item['name']}.png")); dialog.close()
        assert records[4]['initial_state_hash'] == records[5]['initial_state_hash']
        failed = results['dp_local_failure_preserved']['diagnostics']
        assert failed['failed_increment']['increment'] == 1
        assert len(failed['constitutive_increments']) == 1
        assert canonical_hash(failed['last_accepted_state']) == records[4]['initial_state_hash']
        for name in ('neo_free', 'dp_free', 'maxwell_free_physical_time'):
            for row in results[name]['diagnostics']['constitutive_increments'][1:]:
                assert row['boundary']['residual'] <= row['boundary']['tolerance']
        free = results['neo_free']['diagnostics']['constitutive_increments'][-1]
        fixed = results['neo_constrained']['diagnostics']['constitutive_increments'][-1]
        assert free['F'][1][1] != 1. and fixed['F'][1][1] == 1.
        assert free['stress_tensor'][0][0] != fixed['stress_tensor'][0][0]
        jobs_after = len(client.request('/api/workbench')['jobs'])
        assert jobs_after - jobs_before == (6 if expected is None else 0)
        record = dict(status='PASS', cases=records, plan=plan_receipt, store=str(store.resolve()),
            declared_inputs_hash=canonical_hash(inputs), new_jobs=jobs_after-jobs_before,
            jobs_before=jobs_before, jobs_after=jobs_after, initial_retry_identical=True,
            failed_prefix_preserved=True, no_automatic_plan_execution=True)
        (output / 'result.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
        print(json.dumps(record))
    finally:
        for window in reversed(windows): window.close()
        app.processEvents(); server.shutdown(); server.server_close(); service.shutdown(); thread.join(5)


def wait(app, ready):
    end = time.monotonic() + 40
    while True:
        app.processEvents()
        if ready(): return
        if time.monotonic() > end: raise TimeoutError('mixed-control Qt reply')
        time.sleep(.01)


def host_check(inputs, prior, output):
    from apps.research.material_control_gui import MixedControlDialog, MixedControlResultDialog
    from apps.research.law_native_material_window import LawNativeMaterialWindow
    from caelab.evaluation import prepare
    from caelab.numerical_document import from_material_document, diagnostics
    record = json.loads((prior / 'result.json').read_text(encoding='utf-8'))
    shutil.copytree(record['store'], output / 'store')
    app = QApplication.instance() or QApplication([]); apply_appearance(app)
    service = LabService(output / 'store'); server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True); thread.start()
    client = Client(f'http://127.0.0.1:{server.server_port}')
    window = None
    try:
        jobs = client.request('/api/workbench')['jobs']
        original = client.document_open(kind='material', document_id=record['cases'][0]['document_id'])
        other = client.document_open(kind='material', document_id=record['cases'][1]['document_id'])
        window = LawNativeMaterialWindow(client, auto_open=False, poll_interval=0)
        window.show(); window.open_document(document_id=original['id'])
        wait(app, lambda: window.document is not None and not window._busy and not window._workers)
        def edit(cancel=False, stale=False):
            dialog = app.activeModalWidget(); assert isinstance(dialog, MixedControlDialog)
            dialog.resize(780, 620); dialog.table.setCurrentCell(1, 12)
            dialog.table.item(1, 12).setText('.1')
            if cancel:
                app.processEvents(); dialog.grab().save(str(output / 'host-cancel.png')); dialog.reject()
            else:
                if stale: window._opened(other)
                dialog._compile()
        QTimer.singleShot(50, lambda: edit(cancel=True)); window.configure_control()
        assert not window.local_dirty and client.document_read(original['id']) == original
        wait(app, lambda: not window._busy and not window._workers)
        QTimer.singleShot(50, edit); window.configure_control()
        assert window.local_dirty and window.edited_draft()['settings']['boundary_control']['stress_components']['zz'][1] == .1
        assert client.document_read(original['id']) == original
        window.apply_inputs(); wait(app, lambda: not window._busy and not window._workers)
        assert client.document_read(original['id'])['draft'] == window.edited_draft()
        window.undo_action.trigger(); wait(app, lambda: not window._busy and not window._workers)
        assert window.document['draft'] == original['draft']
        window.redo_action.trigger(); wait(app, lambda: not window._busy and not window._workers)
        assert window.document['draft']['settings']['boundary_control']['stress_components']['zz'][1] == .1
        window.undo_action.trigger(); wait(app, lambda: not window._busy and not window._workers)
        window.save_document(); wait(app, lambda: not window._busy and not window._workers)
        assert window.document['draft'] == original['draft']
        before = deepcopy(window.document)
        QTimer.singleShot(50, lambda: edit(stale=True)); window.configure_control()
        assert window.document['id'] == other['id'] and not window.local_dirty
        assert client.document_read(before['id']) == before and client.document_read(other['id']) == other
        window.open_document(document_id=before['id']); wait(app, lambda: not window._busy and not window._workers)
        window._selected_job = record['cases'][0]['job_id']
        # A retained result must use its submitted settings even with a different local buffer.
        edited = deepcopy(window.edited_draft()); edited['settings']['parameters']['mu'] = '1e'
        window._show_document(window.document, preserve_draft=edited); window.local_dirty = True
        window.open_control_result()
        wait(app, lambda: any(isinstance(w, MixedControlResultDialog) for w in window._law_windows) and not window._busy)
        result_dialog = next(w for w in window._law_windows if isinstance(w, MixedControlResultDialog))
        assert result_dialog.settings == original['draft']['settings'] and window.edited_draft() == edited
        result_dialog.increment.setCurrentIndex(1); result_dialog.resize(780, 620); app.processEvents()
        result_dialog.grab().save(str(output / 'host-retained-result.png')); result_dialog.close()
        window._show_document(window.document); window.local_dirty = False
        # Existing compiler + prepared adapter bind all mixed settings without evaluation.
        draft = from_material_document(window.document); draft.update(mode='doe', count=1, budget=1)
        assert diagnostics(draft) == []
        plan = client.document_open(kind='numerical', title='혼합 제어 실행 전 계획', draft=draft)
        plan = command(client, plan, 'document.save')['document']
        arguments = server.workbench.numerical_documents.job_arguments(plan['draft'])
        assert arguments['settings'] == original['draft']['settings']
        with prepare(arguments['backend'], arguments['settings']) as prepared:
            assert prepared.settings == arguments['settings']
        assert client.request('/api/workbench')['jobs'] == jobs
        receipt = dict(status='PASS', plan_id=plan['id'], plan_hash=canonical_hash(plan['draft']),
            prepared_settings_hash=canonical_hash(arguments['settings']), prepare_evaluations=0,
            cancel_preserves=True, stale_editor_preserves=True, undo_redo=True,
            retained_result_uses_submitted_settings=True, jobs_before=len(jobs), jobs_after=len(jobs), new_jobs=0,
            store=str((output / 'store').resolve()), material_id=original['id'], material_hash=canonical_hash(original['draft']))
        (output / 'host.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8'); print(json.dumps(receipt))
    finally:
        if window is not None:
            for child in window._law_windows: child.close()
            window._allow_close = True; window.close()
        app.processEvents(); server.shutdown(); server.server_close(); service.shutdown(); thread.join(5)


def validation_check(inputs, prior, output, *, cold=False):
    from apps.research.material_control_gui import MixedControlDialog
    from caelab.evaluation import prepare
    from caelab.numerical_document import from_material_document, diagnostics
    from caelab.workbench_client import WorkbenchHTTPError
    receipt = json.loads((prior / ('validation.json' if cold else 'result.json')).read_text(encoding='utf-8'))
    store = Path(receipt['store']) if cold else output / 'store'
    if not cold: shutil.copytree(receipt['store'], store)
    app = QApplication.instance() or QApplication([]); apply_appearance(app)
    service = LabService(store); server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True); thread.start()
    client = Client(f'http://127.0.0.1:{server.server_port}'); dialog = None
    try:
        jobs = client.request('/api/workbench')['jobs']; plans = []
        if cold:
            invalid = receipt['invalid_draft']
            for item in receipt['plans']:
                plan = client.document_open(kind='numerical', document_id=item['document_id'])
                assert canonical_hash(plan['draft']) == item['draft_hash']
                args = server.workbench.numerical_documents.job_arguments(plan['draft'])
                with prepare(args['backend'], args['settings']) as prepared:
                    assert canonical_hash(prepared.settings) == item['prepared_settings_hash']
                plans.append(item)
        else:
            material = client.document_open(kind='material', document_id=receipt['cases'][0]['document_id'])
            original = deepcopy(material['draft'])
            invalid_settings = deepcopy(original['settings'])
            invalid_settings['boundary_control']['stress_components']['yy'][1] = '1e'
            dialog = MixedControlDialog(client, invalid_settings); dialog.show(); dialog.resize(780, 680)
            assert not dialog.validate_draft(); app.processEvents(); dialog.grab().save(str(output / 'invalid-target.png'))
            dialog._compile(); assert dialog.result_settings == invalid_settings
            material = command(client, material, 'material.update', {'draft': {'backend': original['backend'], 'settings': dialog.result_settings}})['document']
            material = command(client, material, 'document.save')['document']
            assert material['draft']['settings'] == invalid_settings and material['diagnostics']
            try:
                command(client, material, 'material.evaluate')
                raise AssertionError('Invalid target was admitted')
            except WorkbenchHTTPError as error:
                assert error.code == 400
                refusal = str(error.service_message)
            invalid = dict(saved_revision=material['saved_revision'], input_hash=canonical_hash(material['draft']),
                           raw_target='1e', refusal=refusal, execution_jobs=0)
            assert client.document_read(material['id'])['draft'] == material['draft']
            material = command(client, material, 'material.update', {'draft': original})['document']
            material = command(client, material, 'document.save')['document']
            assert material['draft'] == original
            for index in (0, 2, 3):
                source = client.document_read(receipt['cases'][index]['document_id'])
                draft = from_material_document(source); draft.update(mode='doe', count=1, budget=1)
                draft['material'].update(saved_revision=source['saved_revision'], input_sha256=canonical_hash(source['draft']))
                assert diagnostics(draft) == []
                plan = client.document_open(kind='numerical', title='실행 전 혼합 제어 ' + receipt['cases'][index]['name'], draft=draft)
                plan = command(client, plan, 'document.save')['document']
                args = server.workbench.numerical_documents.job_arguments(plan['draft'])
                assert args['settings'] == inputs['cases'][index]['settings']
                with prepare(args['backend'], args['settings']) as prepared:
                    assert prepared.settings == args['settings']
                plans.append(dict(document_id=plan['id'], draft_hash=canonical_hash(plan['draft']),
                                  prepared_settings_hash=canonical_hash(args['settings']), model=args['settings']['model']))
        assert client.request('/api/workbench')['jobs'] == jobs
        result = dict(status='PASS', plans=plans, invalid_draft=invalid, store=str(store.resolve()),
                      jobs_before=len(jobs), jobs_after=len(jobs), new_jobs=0, evaluator_calls=0, cold=cold)
        (output / 'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8'); print(json.dumps(result, ensure_ascii=False))
    finally:
        if dialog is not None: dialog.close()
        app.processEvents(); server.shutdown(); server.server_close(); service.shutdown(); thread.join(5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phase', choices=['first-contact', 'editor', 'run', 'cold', 'host', 'validate', 'cold-validate'], default='first-contact')
    parser.add_argument('--inputs', type=Path)
    parser.add_argument('--prior', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    for source in (Path(__file__), ROOT / 'apps/research/material_control_gui.py', ROOT / 'apps/research/material_test_dialog.py', ROOT / 'apps/research/law_native_material_window.py', ROOT / 'apps/research/material_window.py'):
        (args.output / ('checked-' + source.name)).write_bytes(source.read_bytes())
    if args.phase == 'first-contact': first_contact(args.case, args.output)
    else:
        inputs = json.loads(args.inputs.read_text(encoding='utf-8'))
        if args.phase == 'editor': editor_check(inputs, args.output)
        elif args.phase == 'run': calculated_check(inputs, args.output)
        elif args.phase == 'host': host_check(inputs, args.prior, args.output)
        elif args.phase in ('validate', 'cold-validate'): validation_check(inputs, args.prior, args.output, cold=args.phase == 'cold-validate')
        else:
            prior = json.loads((args.prior / 'result.json').read_text(encoding='utf-8'))
            calculated_check(inputs, args.output, store=Path(prior['store']), expected=prior)


if __name__ == '__main__':
    main()
