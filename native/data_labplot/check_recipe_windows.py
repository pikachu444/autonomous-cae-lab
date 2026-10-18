"""Actual B4.1 HTTP/Qt recipe, canonical samples, Plan admission and cold read.
Run under scripts/native_check.py to own this process and every child window.
"""
import argparse
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))
os.environ.pop('QT_QPA_PLATFORM', None)
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from apps.research.appearance import apply_appearance
from apps.research.data_window import DataWindow
from apps.research.data_processing_dialog import DataProcessingRecipeDialog
from apps.research.data_processing_inspector import DataProcessingInspectorDialog, ProcessingSampleTraceDialog
from apps.research.data_sample_policy_dialog import SamplePolicyDialog
from apps.research.experiment_dialogs import CalibrationDialog
from apps.research.material_test_dialog import ExperimentDialog
from apps.research.numerical_window import NumericalWindow
from caelab.experiment_calibration import default_calibration
from caelab.material_document import default_draft as material_draft
from caelab.numerical_document import from_material_document
from caelab.storage import canonical_hash
from caelab.workbench_client import Client


class RecordingClient(Client):
    def __init__(self, url):
        super().__init__(url); self.reads = Counter()
    def request(self, path, body=None, **kwargs):
        self.reads[path.split('?')[0]] += 1
        return super().request(path, body, **kwargs)


def wait(app, ready, description='Qt/owner read'):
    end = time.monotonic() + 90
    stable_since = None
    while True:
        app.processEvents()
        if ready():
            if stable_since is None: stable_since = time.monotonic()
            elif time.monotonic() - stable_since >= .05: return
        else: stable_since = None
        if time.monotonic() > end: raise TimeoutError(description)
        time.sleep(.01)


def settled(window):
    return not any(getattr(window, key, False) for key in ('_busy', '_callbacks', '_accepting', '_callback_calls', '_result_pending'))


@contextmanager
def modal(cls, operation):
    original, errors, opened = cls.exec, [], []
    def execute(dialog):
        opened.append(dialog)
        def act():
            try: operation(dialog)
            except Exception as error:
                errors.append(error); dialog.reject()
        QTimer.singleShot(80, act)
        def expired():
            if dialog.isVisible():
                errors.append(TimeoutError(cls.__name__ + ' acceptance did not close'))
                dialog.reject()
        QTimer.singleShot(20000, expired)
        return original(dialog)
    cls.exec = execute
    try:
        yield
        if errors: raise errors[0]
        assert len(opened) == 1, f'{cls.__name__} was not actually opened exactly once'
    finally: cls.exec = original


def picture(app, widget, path, narrow=False):
    if narrow: widget.resize(760, 680)
    app.processEvents(); widget.grab().save(str(path))


def recipe(high, gap, step):
    operations = [
        dict(id='Ostrain', operation='engineering_strain', input='extension', output='E', settings=dict(L0=50., length_unit='mm', measurement='extensometer_gauge_extension')),
        dict(id='Ostress', operation='nominal_stress', input='force', output='P11', settings=dict(A0=10., area_unit='mm2')),
        dict(id='Obefore', operation='savgol', input='P11', output='P_before', settings=dict(window_length=3, polyorder=1, uniform_rtol=1e-7, uniform_atol=0.))]
    for source, output in [('P11', 'P_grid'), ('E', 'E_grid')]:
        operations.append(dict(id='O' + output, operation='resample', input=source, output=output,
            settings=dict(method='linear', max_gap=gap, range=[0., high], step=step)))
    for source, output in [('P_grid', 'P_filtered'), ('E_grid', 'E_filtered')]:
        operations.append(dict(id='O' + output, operation='savgol', input=source, output=output,
            settings=dict(window_length=3, polyorder=1, uniform_rtol=1e-7, uniform_atol=0.)))
    return dict(version=1, operations=operations)


def command(client, document, operation, arguments=None):
    return client.document_command(document['id'], operation, arguments or {}, session_id=document['session_id'], expected_generation=document['generation'])['document']


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    for source in (Path(__file__), REPOSITORY / 'apps/research/data_processing_inspector.py'):
        (output / ('checked-' + source.name)).write_bytes(source.read_bytes())
    app = QApplication.instance() or QApplication([]); apply_appearance(app)
    service = LabService(output / 'store'); server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True); thread.start()
    client = RecordingClient(f'http://127.0.0.1:{server.server_port}'); windows = []; receipts = []
    try:
        certificate = client.upload('synthetic-calibration.txt', b'Synthetic acceptance fixture: force_N = 10 * voltage_mV. Not an instrument qualification.')
        calibration = {**default_calibration('N'), 'a': 10., 'source': {'data_id': certificate['id'], 'sha256': certificate['sha256'], 'name': certificate['name']}, 'displacement_role': 'not_displacement'}
        for label, times, delimiter, selection in (
            ('인장A.csv', [0., 1., 2., 3., 4.], ',', {'exclude_rows': []}),
            ('반복인장B.txt', [0., .5, 1., 1.5, 4., 4.5, 5., 5.5], None, {'exclude_rows': [3], 'quality_rows': [6]})):
            folder = output / ('csv' if delimiter else 'ascii'); folder.mkdir()
            sep = ',' if delimiter else ' '
            raw = ('time' + sep + 'extension' + sep + 'voltage\n' + ''.join(f'{t}{sep}{t * .1}{sep}' + ('nan' if not delimiter and index == 2 else str(t)) + '\n' for index, t in enumerate(times))).encode()
            (folder / 'input.txt').write_bytes(raw)
            upload = client.upload(label, raw)
            columns = {name: dict(column=index, unit=unit, component='xx', location='material_point', measure=measure, frame='material_cartesian', row_selection=deepcopy(selection), axis=dict(column=0, name='time', unit='s')) for name, index, unit, measure in [('force', 2, 'kN', 'force'), ('extension', 1, 'mm', 'displacement')]}
            document = client.document_open(kind='data', title=label, draft=dict(data_id=upload['id'], mapping=dict(delimiter=delimiter, skip_header=1, columns=columns)))
            window = DataWindow(client, auto_open=False, poll_interval=0); windows.append(window); window.show(); window.open_document(document_id=document['id'])
            wait(app, lambda: settled(window) and bool(window._preview), 'raw source preview')
            window.channel_selector.setCurrentText('force'); app.processEvents()
            before_reads = client.reads.copy()
            for unit in ('N', 'kN', 'N'):
                window.mapping.item(1, 3).setText(unit); app.processEvents()
            assert client.reads == before_reads, 'editing channel units reloaded the source'
            def calibrate(dialog):
                dialog.recipe = deepcopy(calibration)
                for key, field in dialog.fields.items():
                    if key in calibration and not isinstance(calibration[key], (dict, list)) and calibration[key] is not None: field.setText(str(calibration[key]))
                dialog.source.setText(calibration['source']['name']); dialog.role.setCurrentIndex(dialog.role.findData('not_displacement'))
                dialog.refresh_preview(); wait(app, lambda: not dialog._workers, 'calibration preview')
                picture(app, dialog, folder / 'calibration.png'); dialog.accept()
            with modal(CalibrationDialog, calibrate): window.edit_calibration(); wait(app, lambda: 'calibration' in window.edited_draft()['mapping']['columns']['force'])
            window.apply_inputs(); wait(app, lambda: settled(window) and not window.local_dirty)
            document = client.document_read(document['id']); assert document['draft']['mapping']['columns']['force']['unit'] == 'N'
            document = command(client, document, 'data.import'); job = document['runs'][-1]['job_id']
            wait(app, lambda: client.status(job)['state'] in ('SUCCEEDED', 'FAILED'), 'raw import')
            assert client.status(job)['state'] == 'SUCCEEDED'
            window._show_document(client.document_read(document['id'])); window.refresh_result(); wait(app, lambda: settled(window) and window.result_channel.count() == 2)
            prepared_recipe = recipe(times[-1], 1.1 if delimiter else .75, .5 if delimiter else .25)
            if not delimiter:
                for source, name in [('P11', 'P_segment'), ('E', 'E_segment')]:
                    prepared_recipe['operations'].append(dict(id='O' + name, operation='resample', input=source, output=name,
                        settings=dict(method='linear', max_gap=.75, range=[5., 5.5], step=.25)))
            def edit(dialog):
                dialog.recipe = deepcopy(prepared_recipe); dialog._show()
                dialog.table.selectRow(1); dialog.move(-1); dialog.move(1)
                assert dialog.recipe == prepared_recipe
                picture(app, dialog, folder / 'recipe.png'); dialog.accept()
            with modal(DataProcessingRecipeDialog, edit): window.processing_recipe_action.trigger()
            assert window.local_dirty
            window.apply_inputs(); wait(app, lambda: settled(window) and not window.local_dirty)
            before = client.document_read(document['id'])
            def cancel_preview(dialog):
                assert isinstance(dialog, DataProcessingInspectorDialog)
                dialog.channel.setCurrentText('P_filtered'); dialog.table.setCurrentCell(1, 0)
                picture(app, dialog, folder / 'preview.png'); picture(app, dialog, folder / 'preview-narrow.png', True)
                dialog.reject()
            with modal(DataProcessingInspectorDialog, cancel_preview): window.preview_processing(); wait(app, lambda: settled(window))
            assert client.document_read(document['id']) == before
            with modal(DataProcessingInspectorDialog, lambda dialog: dialog.accept()): window.preview_processing(); wait(app, lambda: settled(window) and len(window.document.get('processing_revisions', [])) == 1)
            window.save_document(); wait(app, lambda: settled(window) and not window.document['dirty'])
            document = client.document_read(document['id']); record = document['processing_revisions'][0]
            retained = client.data_material('data.processing.result', dict(document_id=document['id'], processing_revision=record['id']))
            channel = retained['channels']['P_grid']
            if not delimiter:
                assert retained['diagnostics']['processing_status'] == 'PARTIAL'
                assert next(s for s in retained['stages'] if s['id'] == 'Obefore')['state'] == 'BLOCKED'
                for point, valid in zip(channel['axis']['values'], channel['operation_valid']):
                    if .5 < point < 1.5 or 1.5 < point < 4. or 4. < point < 5.: assert not valid, point
                assert len(retained['responses']['P_grid']['segments']) > 1
            inspector = DataProcessingInspectorDialog(retained, window, retained=True, allow_plan=True); windows.append(inspector)
            inspector.show(); inspector.channel.setCurrentText('P_grid'); inspector.table.setCurrentCell(1, 0); app.processEvents()
            terms = inspector._trace['terms']; assert terms and all(term['raw_value'] is not None for term in terms)
            trace = ProcessingSampleTraceDialog(channel, inspector.selected_sample_index(), inspector._trace, inspector._segments[inspector.selected_sample_index()], inspector); windows.append(trace)
            trace.show(); picture(app, trace, folder / 'trace.png'); trace.close(); inspector.close()
            receipts.append(dict(document_id=document['id'], job_id=job, processing_revision=record['id'], result_sha256=canonical_hash(retained), result=retained, raw_sha256=hashlib.sha256(raw).hexdigest(), source_sha256=upload['sha256'], recipe=prepared_recipe))
        declared = material_draft(); declared['settings'].update(model='neo_hooke', parameters={'mu': 1., 'lmbda': 2.})
        material = client.document_open(kind='material', title='합성 유한변형 인수 재료', draft=declared); material = command(client, material, 'document.save')
        plan = client.document_open(kind='numerical', title='두 시험 표본 계획', draft=from_material_document(material))
        numerical = NumericalWindow(client, document_id=plan['id'], poll_interval=0); windows.append(numerical); numerical.show()
        wait(app, numerical.can_stage_processed_trial, 'Plan read')
        for index, receipt in enumerate(receipts):
            result = receipt['result']; record = result['diagnostics']['processing_record']
            response, driver = ('P_segment', 'E_segment') if index else ('P_filtered', 'E_filtered')
            source = {**record['source'], 'processing_revision': record['id'], 'response': response}
            def review(dialog):
                dialog.observed.setCurrentIndex(dialog.observed.findData(response)); dialog.protocol.setCurrentIndex(dialog.protocol.findData('measured'))
                dialog.driver.setCurrentIndex(dialog.driver.findData(driver)); dialog.lateral_22.setText('1'); dialog.lateral_33.setText('1')
                dialog.role.setCurrentIndex(dialog.role.findData('fit' if index == 0 else 'holdout'))
                picture(app, dialog, output / f'trial-{index}.png'); dialog._accept()
            with modal(ExperimentDialog, review): assert numerical.stage_processed_trial(source, result)
            numerical.apply_inputs(); wait(app, lambda: settled(numerical) and not numerical.local_dirty)
            numerical.experiments.selectRow(index); wait(app, numerical.can_stage_processed_trial, 'trial source read')
            def policy(dialog):
                assert isinstance(dialog, SamplePolicyDialog)
                dialog.role.setCurrentIndex(dialog.role.findData('fit' if index == 0 else 'holdout'))
                dialog.table.selectRow(1); dialog.weight.setText('2.5'); dialog._batch()
                if index == 0: dialog.table.selectRow(0); dialog._batch(included=False)
                picture(app, dialog, output / f'policy-{index}.png'); dialog._accept()
            with modal(SamplePolicyDialog, policy):
                assert numerical.edit_sample_policy()
                wait(app, lambda: settled(numerical) and numerical._adoption_receipt is None and 'selection' in numerical.document['draft']['experiments'][index])
        numerical.save_document(); wait(app, lambda: settled(numerical) and not numerical.document['dirty'])
        plan = client.document_read(plan['id']); owner = server.workbench._document_owner(plan['id'])
        prepared = owner.job_arguments(plan['draft'])
        assert prepared['frozen_inclusion']['independence']['status'] == 'DISJOINT'
        assert {e['role'] for e in prepared['experiments']} == {'fit', 'holdout'}
        assert all(e['observations']['sample_domain'] == 'derived-grid-v2' for e in prepared['experiments'])
        assert not plan['runs']
        summary = dict(status='PASS', store=str((output / 'store').resolve()), data=[{k: v for k, v in r.items() if k != 'result'} for r in receipts], plan_document_id=plan['id'], frozen_inclusion=prepared['frozen_inclusion'], imports=2, fit_solver_provider_runs=0)
        (output / 'result.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps({k:v for k,v in summary.items() if k not in ('data','frozen_inclusion')}))
    finally:
        for window in reversed(windows):
            if hasattr(window, '_allow_close'): window._allow_close = True
            window.close()
        app.processEvents(); server.shutdown(); server.server_close(); service.shutdown(); thread.join(5)



def resume(output, prior):
    """Continue the saved two-file result; never repeat its imports or old recipe."""
    output.mkdir(parents=True, exist_ok=False)
    for source in (Path(__file__), REPOSITORY / 'apps/research/data_processing_inspector.py'):
        (output / ('checked-' + source.name)).write_bytes(source.read_bytes())
    app = QApplication.instance() or QApplication([]); apply_appearance(app)
    store = prior / 'store'; service = LabService(store); server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True); thread.start()
    client = RecordingClient(f'http://127.0.0.1:{server.server_port}'); windows = []
    try:
        documents = client.documents()['documents']
        saved_data = [client.document_read(d['id']) for d in documents if d['kind'] == 'data']
        assert len(saved_data) == 2
        csv = next(d for d in saved_data if d['title'].endswith('.csv'))
        ascii_doc = next(d for d in saved_data if d['title'].endswith('.txt'))
        initial_jobs = client.request('/api/workbench')['jobs']; assert len(initial_jobs) == 2
        # The existing guard rejects the discontinuous prescribed driver; choose
        # a declared continuous interval through the original recipe controls.
        before_record = ascii_doc['processing_revisions'][0]
        old_result = client.data_material('data.processing.result', dict(document_id=ascii_doc['id'], processing_revision=before_record['id']))
        from caelab.material_test import measured_protocol
        rejected_gap = False
        try:
            measured_protocol(material_draft()['settings'], {**old_result, 'execution_status': 'SUCCEEDED'}, dict(channel='E_filtered', kind='engineering_strain', lateral_22=1., lateral_33=1.))
        except ValueError as error:
            rejected_gap = '제외 구간' in str(error)
        assert rejected_gap
        window = DataWindow(client, auto_open=False, poll_interval=0); windows.append(window); window.show(); window.open_document(document_id=ascii_doc['id'])
        wait(app, lambda: settled(window) and window.result_channel.count() == 2, 'saved ASCII channel read')
        chosen_recipe = deepcopy(ascii_doc['draft']['processing']['recipe'])
        for source, name in [('P11', 'P_segment'), ('E', 'E_segment')]:
            if not any(operation['output'] == name for operation in chosen_recipe['operations']):
                chosen_recipe['operations'].append(dict(id='O' + name, operation='resample', input=source, output=name,
                    settings=dict(method='linear', max_gap=.75, range=[5., 5.5], step=.25)))
        def edit(dialog):
            dialog.recipe = deepcopy(chosen_recipe); dialog._show(); picture(app, dialog, output / 'continuous-recipe.png'); dialog.accept()
        with modal(DataProcessingRecipeDialog, edit): window.processing_recipe_action.trigger()
        if window.local_dirty:
            window.apply_inputs(); wait(app, lambda: settled(window) and not window.local_dirty)
        def retain(dialog):
            dialog.channel.setCurrentText('P_segment'); dialog.table.setCurrentCell(1, 0)
            picture(app, dialog, output / 'continuous-preview.png'); picture(app, dialog, output / 'continuous-preview-narrow.png', True); dialog.accept()
        if len(ascii_doc['processing_revisions']) == 1:
            with modal(DataProcessingInspectorDialog, retain): window.preview_processing(); wait(app, lambda: settled(window) and len(window.document.get('processing_revisions', [])) == 2)
        window.save_document(); wait(app, lambda: settled(window) and not window.document['dirty'])
        ascii_doc = client.document_read(ascii_doc['id'])
        assert ascii_doc['processing_revisions'][0]['id'] == before_record['id']
        receipts = []
        for data in (csv, ascii_doc):
            record = data['processing_revisions'][-1]
            result = client.data_material('data.processing.result', dict(document_id=data['id'], processing_revision=record['id']))
            receipts.append(dict(document_id=data['id'], processing_revision=record['id'], result_sha256=canonical_hash(result), result=result))
        assert client.request('/api/workbench')['jobs'] == initial_jobs
        compatible = [d for d in documents if d['kind'] == 'numerical' and d['title'] == '두 시험 유한변형 계획']
        if compatible:
            plan = client.document_read(compatible[0]['id'])
        else:
            # Declared synthetic law chosen for the first-Piola observation.
            # Keep the earlier incompatible saved Plan as a refusal receipt.
            declared = material_draft()
            declared['settings'].update(model='neo_hooke', parameters={'mu': 1., 'lmbda': 2.})
            material = client.document_open(kind='material', title='합성 유한변형 인수 재료', draft=declared)
            material = command(client, material, 'document.save')
            plan = client.document_open(kind='numerical', title='두 시험 유한변형 계획', draft=from_material_document(material))
        numerical = NumericalWindow(client, document_id=plan['id'], poll_interval=0); windows.append(numerical); numerical.show()
        wait(app, numerical.can_stage_processed_trial, 'saved Plan read')
        assert len(numerical.edited_draft()['experiments']) in (0, 1, 2)
        for index, receipt in enumerate(receipts):
            result = receipt['result']; record = result['diagnostics']['processing_record']
            if index >= len(numerical.edited_draft()['experiments']):
                response, driver = ('P_segment', 'E_segment') if index else ('P_filtered', 'E_filtered')
                source = {**record['source'], 'processing_revision': record['id'], 'response': response}
                def trial(dialog):
                    dialog.observed.setCurrentIndex(dialog.observed.findData(response)); dialog.protocol.setCurrentIndex(dialog.protocol.findData('measured'))
                    dialog.driver.setCurrentIndex(dialog.driver.findData(driver)); dialog.lateral_22.setText('1'); dialog.lateral_33.setText('1')
                    dialog.role.setCurrentIndex(dialog.role.findData('holdout' if index else 'fit')); picture(app, dialog, output / f'trial-{index}.png'); dialog._accept()
                    QTimer.singleShot(10000, lambda: dialog.reject() if dialog.isVisible() and dialog.value is None else None)
                with modal(ExperimentDialog, trial): assert numerical.stage_processed_trial(source, result)
                numerical.apply_inputs(); wait(app, lambda: settled(numerical) and not numerical.local_dirty)
            numerical.experiments.selectRow(index); wait(app, numerical.can_stage_processed_trial, 'selected trial source read')
            def policy(dialog):
                dialog.role.setCurrentIndex(dialog.role.findData('fit' if index == 0 else 'holdout'))
                dialog.table.selectRow(1); dialog.weight.setText('2.5'); dialog._batch()
                if index == 0: dialog.table.selectRow(0); dialog._batch(included=False)
                picture(app, dialog, output / f'policy-{index}.png'); picture(app, dialog, output / f'policy-{index}-narrow.png', True); dialog._accept()
            with modal(SamplePolicyDialog, policy):
                assert numerical.edit_sample_policy()
                wait(app, lambda: settled(numerical) and numerical._adoption_receipt is None and 'selection' in numerical.document['draft']['experiments'][index], 'sample policy adoption')
        numerical.save_document(); wait(app, lambda: settled(numerical) and not numerical.document['dirty'])
        plan = client.document_read(plan['id']); prepared = server.workbench._document_owner(plan['id']).job_arguments(plan['draft'])
        assert prepared['frozen_inclusion']['independence']['status'] == 'DISJOINT'
        assert {e['role'] for e in prepared['experiments']} == {'fit', 'holdout'}
        assert not plan['runs']
        # Actual owner/CAS adoption of a conflicting policy remains editable;
        # the exact original preparation/compiler must block its inclusion.
        bad = client.document_open(kind='numerical', title='같은 원행 중복 반례', draft=deepcopy(plan['draft']))
        trial = bad['draft']['experiments'][0]; source = trial['source']
        proposal = client.data_material('data.sample_policy.preview', dict(document_id=source['document_id'], processing_revision=source['processing_revision'], response=source['response']))
        entries = deepcopy(proposal['entries']); sid = list(entries)[1]; entries[sid]['role'] = 'holdout'
        accepted = client.data_material('data.sample_policy.adopt', dict(document_id=bad['id'], experiment_id=trial['id'], proposal=proposal, entries=entries, session_id=bad['session_id'], expected_generation=bad['generation'], command_id='Cshared-row-counterexample'))
        bad = accepted['document']; blocked = False
        try: server.workbench._document_owner(bad['id']).job_arguments(bad['draft'])
        except ValueError as error: blocked = 'RAW_CONTRIBUTOR_OVERLAP' in str(error)
        assert blocked and not bad['runs']; bad = command(client, bad, 'document.save')
        assert client.document_read(plan['id']) == plan and client.request('/api/workbench')['jobs'] == initial_jobs
        summary = dict(status='PASS', store=str(store.resolve()), data=[{k:v for k,v in r.items() if k != 'result'} for r in receipts],
            plan_document_id=plan['id'], frozen_inclusion=prepared['frozen_inclusion'], blocked_plan_document_id=bad['id'],
            raw_overlap_blocked=True, discontinuous_driver_blocked=True, new_imports=0, fit_solver_provider_runs=0)
        (output / 'result.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps({k:v for k,v in summary.items() if k not in ('data','frozen_inclusion')}))
    finally:
        for window in reversed(windows):
            if hasattr(window, '_allow_close'): window._allow_close = True
            window.close()
        app.processEvents(); server.shutdown(); server.server_close(); service.shutdown(); thread.join(5)

def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True); parser.add_argument('--resume', type=Path)
    args = parser.parse_args()
    if args.resume: resume(args.output.resolve(), args.resume.resolve(strict=True))
    else: run(args.output.resolve())


if __name__ == '__main__': main()
