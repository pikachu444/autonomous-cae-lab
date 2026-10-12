"""Two isolated synthetic Qt regressions for UX-FIX-06, no native execution.

Run existing PySide6 interpreter with --source frozen prototype and --output
scratch directory. Only test artifacts/review files are written to scratch.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(args.source.resolve()))
import PySide6
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QDialog, QDialogButtonBox, QFormLayout
import prototype_state as state
import qt_prototype as prototype

args.output.mkdir(parents=True, exist_ok=True)
workspace = Path(tempfile.mkdtemp(prefix='ux06-workspace-', dir=args.output))
app = QApplication(['ux06-acceptance'])
app.setQuitOnLastWindowClosed(False)
prototype.configure_application_fonts(app)
app.setStyle('Fusion')
app.setStyleSheet(prototype.STYLE)
errors, hubs, results = [], [], []
sys.excepthook = lambda t, e, tb: errors.append(''.join(traceback.format_exception(t, e, tb)))


def pump():
    app.processEvents()
    QTest.qWait(10)
    app.processEvents()


def window(tool, name):
    s = state.ReviewSession(workspace / name)
    hub = prototype.DesktopHub(s)
    hubs.append(hub)
    w = hub.open(tool)
    pump()
    return s, hub, w


def cell(table, row, column, value):
    table.setCurrentCell(row, column)
    table.setFocus()
    QTest.keyClick(table, Qt.Key.Key_F2)
    pump()
    editor = QApplication.focusWidget()
    assert isinstance(editor, QLineEdit), 'F2 did not open text delegate'
    QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(editor, str(value))
    QTest.keyClick(editor, Qt.Key.Key_Return)
    pump()


def form_field(dialog, label):
    form = dialog.layout()
    assert isinstance(form, QFormLayout)
    for row in range(form.rowCount()):
        item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
        if item and item.widget() and item.widget().text().rstrip(':') == label:
            return form.itemAt(row, QFormLayout.ItemRole.FieldRole).widget()
    raise AssertionError('Missing form field ' + label)


def step_modal(action, fill):
    outcome = {'visited': False, 'error': None}
    watchdog = QTimer()
    watchdog.setSingleShot(True)

    def visit():
        dialog = app.activeModalWidget()
        try:
            assert isinstance(dialog, QDialog) and dialog.windowTitle() == 'Analysis step'
            fill(dialog)
            outcome['visited'] = True
            buttons = dialog.findChild(QDialogButtonBox)
            QTest.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton)
        except Exception:
            outcome['error'] = traceback.format_exc()
            if isinstance(dialog, QDialog):
                dialog.reject()

    def timeout():
        outcome['error'] = 'Analysis step dialog timeout'
        dialog = app.activeModalWidget()
        if isinstance(dialog, QDialog):
            dialog.reject()

    watchdog.timeout.connect(timeout)
    watchdog.start(4000)
    QTimer.singleShot(0, visit)
    try:
        action()
    finally:
        watchdog.stop()
    assert outcome['visited'] and outcome['error'] is None, outcome
    pump()


def cold_process(path, expected_path, code, destination):
    script = """import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from prototype_state import ReviewSession
s=ReviewSession(sys.argv[4]);key=s.open_document(sys.argv[2]);expected=json.loads(Path(sys.argv[3]).read_text())
""" + code
    run = subprocess.run([sys.executable, '-c', script, str(args.source.resolve()), str(path),
                          str(expected_path), str(destination)], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, run.stderr
    return run.stdout.strip()


def second_step_name_only_preserves_fields():
    s, _, w = window('simulation', 'hold-step')

    def new_hold(dialog):
        form_field(dialog, 'Name').setText('Hold')
        form_field(dialog, 'Duration [s]').setText('2')

    step_modal(w.step_dialog, new_hold)
    w.tree.setCurrentItem(w.tree.topLevelItem(0).child(w.nodes.index('Steps')))
    w.activateWindow()
    w.steps.selectRow(1)
    pump()
    cell(w.table, w.numeric_fields.index('time_step'), 1, '2e-5')
    cell(w.table, w.numeric_fields.index('force'), 1, '-125')
    original_load = state.clone(w.data['steps'][0])
    original_hold = state.clone(w.data['steps'][1])
    assert original_hold['time_step'] == 2e-5 and original_hold['force'] == -125

    def rename_only(dialog):
        form_field(dialog, 'Name').setText('Hold renamed')

    step_modal(lambda: w.step_dialog(True), rename_only)
    expected_hold = dict(original_hold, name='Hold renamed')
    assert w.data['steps'][1] == expected_hold, (original_hold, w.data['steps'][1])
    w.steps.selectRow(0)
    pump()
    assert w.data['steps'][0] == original_load
    w.steps.selectRow(1)
    pump()
    assert float(w.table.item(w.numeric_fields.index('time_step'), 1).text()) == 2e-5
    assert float(w.table.item(w.numeric_fields.index('force'), 1).text()) == -125
    path = workspace / 'Hold-step-ordinary.json'
    s.save_document('simulation', path)
    assert w.save()
    expected_path = workspace / 'hold-expected.json'
    expected_path.write_text(json.dumps({'load': original_load, 'hold': expected_hold}), encoding='utf-8')
    cold_process(path, expected_path,
                 "assert s.doc(key)['saved']['steps'][0]==expected['load']\nassert s.doc(key)['saved']['steps'][1]==expected['hold']\nprint('name-only step exact cold payload PASS')\n",
                 workspace / 'hold-cold-process')
    cold = state.ReviewSession(workspace / 'hold-cold-qt')
    cold.open_document(path)
    hub = prototype.DesktopHub(cold)
    hubs.append(hub)
    reopened = hub.open('simulation')
    reopened.steps.selectRow(1)
    pump()
    assert float(reopened.table.item(reopened.numeric_fields.index('time_step'), 1).text()) == 2e-5
    assert float(reopened.table.item(reopened.numeric_fields.index('force'), 1).text()) == -125
    return {'second_step': expected_hold, 'load_unchanged': original_load,
            'ordinary_save_fresh_process_and_cold_qt': True}


def check_turn_location(s, hub, expert, turn_id, rid, locator, case):
    row = next(i for i, turn in enumerate(expert.data['turns']) if turn['id'] == turn_id)
    expert.turns.setCurrentRow(row)
    pump()
    refs = [(e['id'], e['locator']) for e in expert.visible_evidence]
    assert refs == [(rid, locator)], refs
    assert expert.evidence.rowCount() == 1
    assert expert.evidence.item(0, 1).text() == locator
    expert.evidence.selectRow(0)
    expert.open_evidence()
    pump()
    dialog = hub.result_dialogs[rid]
    assert dialog.result_id == rid
    table = dialog.result_tables[dialog.result_tabs.currentIndex()]
    assert table.currentRow() >= 0
    assert table.item(table.currentRow(), 0).text() == case, (
        locator, table.currentRow(), table.item(table.currentRow(), 0).text())
    assert s.selected['result_evidence'] == {'id': rid, 'locator': locator}
    return refs


def same_result_distinct_row_replies():
    s, hub, expert = window('expert', 'row-evidence')
    payload = state.clone(s.doc('numerical')['saved'])
    payload.update(method='DOE', budget=4, parent_key='expert', evaluator='Structural Simulation')
    key = 'plan:ux06'
    s.documents[key] = state.make_document(key, 'Row-specific discussion test', 'Numerical', 'N-UX06', 0, payload)
    plan = hub.open(key)
    plan.example_matrix()
    s.save_document(key)
    frozen = s.freeze(key)
    job = s.create_attempt(frozen['id'])
    s.job_event(job['id'], 'result')
    rid = job['result']
    assert s.results[rid]['kind'] == 'numerical'
    dialog = hub.open_result(rid)
    pump()
    locators = []
    turns = []
    for case in ('d1', 'd2'):
        table = dialog.result_tables[0]
        row = next(i for i in range(table.rowCount()) if table.item(i, 0).text() == case)
        dialog.result_tabs.setCurrentIndex(0)
        table.selectRow(row)
        pump()
        locator = s.selected['result_evidence']['locator']
        assert case in locator
        locators.append(locator)
        expert = hub.discuss_result(rid, locator)
        expert.composer.setPlainText('Local user reply about selected ' + case)
        expert.save_reply()
        pump()
        turns.append(expert.data['turns'][-1]['id'])
    expected_pairs = []
    for case, locator, turn_id in zip(('d1', 'd2'), locators, turns):
        expected_pairs.append(check_turn_location(s, hub, expert, turn_id, rid, locator, case))
    path = workspace / 'Expert-row-evidence.json'
    s.save_document('expert', path)
    assert expert.save()
    expected_path = workspace / 'expert-row-expected.json'
    expected_path.write_text(json.dumps({'view': s.doc('expert')['saved'], 'result': s.results[rid]}), encoding='utf-8')
    cold_process(path, expected_path,
                 "assert s.doc(key)['saved']==expected['view']\nrid=expected['result']['id'];assert s.results[rid]==expected['result']\nprint('ordinary Expert exact row evidence cold payload PASS')\n",
                 workspace / 'row-cold-process')
    cold = state.ReviewSession(workspace / 'row-cold-qt')
    cold.open_document(path)
    cold_hub = prototype.DesktopHub(cold)
    hubs.append(cold_hub)
    cold_expert = cold_hub.open('expert')
    pump()
    for case, locator, turn_id in zip(('d1', 'd2'), locators, turns):
        check_turn_location(cold, cold_hub, cold_expert, turn_id, rid, locator, case)
    return {'same_result_id': rid, 'distinct_reply_turns': turns, 'locators': locators,
            'selected_turn_visible_refs': expected_pairs,
            'ordinary_save_fresh_process_and_cold_qt': True}


for name, check in [('hold_step_name_only_preserves_fields', second_step_name_only_preserves_fields),
                    ('same_doe_result_distinct_row_replies', same_result_distinct_row_replies)]:
    start = len(errors)
    try:
        detail = check()
        pump()
        assert len(errors) == start, errors[start:]
        results.append({'check': name, 'status': 'PASS', 'detail': detail})
    except Exception:
        results.append({'check': name, 'status': 'FAIL', 'traceback': traceback.format_exc(),
                        'qt_callback_errors': errors[start:]})
    finally:
        for hub in hubs:
            widgets = list(hub.windows.values()) + list(hub.result_dialogs.values())
            for index, widget in enumerate(widgets):
                if widget.isVisible():
                    widget.grab().save(str(args.output / (name + '-' + str(index) + '.png')))
                    widget.hide()
        pump()
report = {'scope': 'TWO_UX06_SYNTHETIC_QT_PATHS', 'platform': app.platformName(),
          'versions': {'PySide6': PySide6.__version__, 'python': sys.version},
          'native_solver_provider_windows': 'NOT_RUN', 'source': str(args.source.resolve()),
          'source_hashes': {n: hashlib.sha256((args.source / n).read_bytes()).hexdigest()
                            for n in ('prototype_state.py', 'qt_prototype.py', 'qt_widgets.py')},
          'checks': results, 'qt_callback_errors': errors,
          'status': 'PASS' if all(r['status']=='PASS' for r in results) and not errors else 'FAIL'}
(args.output / 'ux06-results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
raise SystemExit(0 if report['status']=='PASS' else 1)
