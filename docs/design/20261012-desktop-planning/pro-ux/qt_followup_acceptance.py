"""Focused, synthetic Qt regressions: method bindings/budget/train, Undo, Post.

Use the existing isolated PySide6 interpreter, --source pointing to a frozen
prototype snapshot, and --output pointing to scratch. Does not execute providers,
solvers, native hosts, or Windows integration. No source/product edits.
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
from PySide6.QtCore import Qt, QTimer
import PySide6
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QDialog, QDialogButtonBox, QFormLayout
import prototype_state as state
import qt_prototype as prototype

args.output.mkdir(parents=True, exist_ok=True)
workspace = Path(tempfile.mkdtemp(prefix='followup-workspace-', dir=args.output))
app = QApplication.instance() or QApplication(['focused-followup'])
app.setQuitOnLastWindowClosed(False)
app.setStyle('Fusion')
app.setStyleSheet(prototype.STYLE)
errors, hubs, results = [], [], []
sys.excepthook = lambda t, e, tb: errors.append(''.join(traceback.format_exception(t, e, tb)))


def pump():
    app.processEvents()
    QTest.qWait(10)
    app.processEvents()


def window(tool, name):
    session = state.ReviewSession(workspace / name)
    hub = prototype.DesktopHub(session)
    hubs.append(hub)
    widget = hub.open(tool)
    pump()
    return session, hub, widget


def blocked(function):
    try:
        function()
    except state.ReviewError as error:
        return str(error)
    raise AssertionError('Expected recoverable admission error; freeze was allowed')


def cell(table, row, column, text):
    table.setCurrentCell(row, column)
    table.setFocus()
    QTest.keyClick(table, Qt.Key.Key_F2)
    pump()
    editor = QApplication.focusWidget()
    assert isinstance(editor, QLineEdit), 'Expected text delegate on F2'
    QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(editor, str(text))
    QTest.keyClick(editor, Qt.Key.Key_Return)
    pump()


def field(dialog, name):
    form = dialog.layout()
    assert isinstance(form, QFormLayout)
    for row in range(form.rowCount()):
        label = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
        if label and label.widget() and label.widget().text().rstrip(':') == name:
            return form.itemAt(row, QFormLayout.ItemRole.FieldRole).widget()
    raise AssertionError('Missing field ' + name)


def add_width(widget):
    result = {'accepted': False, 'error': None}
    watchdog = QTimer()
    watchdog.setSingleShot(True)

    def timeout():
        result['error'] = 'Add variable modal timeout'
        dialog = app.activeModalWidget()
        if isinstance(dialog, QDialog):
            dialog.reject()

    def fill():
        dialog = app.activeModalWidget()
        try:
            assert isinstance(dialog, QDialog) and dialog.windowTitle() == 'Bind variable'
            field(dialog, 'Owner').setCurrentText('cad')
            field(dialog, 'Field').setCurrentText('width')
            for name, value in [('Start', '72'), ('Search lower', '50'), ('Search upper', '90')]:
                editor = field(dialog, name)
                editor.setFocus()
                QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
                QTest.keyClicks(editor, value)
            buttons = dialog.findChild(QDialogButtonBox)
            result['accepted'] = True
            QTest.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton)
        except Exception:
            result['error'] = traceback.format_exc()
            if isinstance(dialog, QDialog):
                dialog.reject()

    watchdog.timeout.connect(timeout)
    watchdog.start(4000)
    QTimer.singleShot(0, fill)
    try:
        widget.add_variable()
    finally:
        watchdog.stop()
    assert result['accepted'] and result['error'] is None, result
    pump()


def matrix_binding_remap():
    s, _, w = window('numerical', 'bindings')
    w.method.setCurrentText('DOE')
    w.example_matrix()
    pump()
    original = [[w.method_detail.item(r, c).text() for c in range(w.method_detail.columnCount())]
                for r in range(w.method_detail.rowCount())]
    assert len(original) == 4 and len(original[0]) == 4
    w.top_tabs.setCurrentIndex(0)
    w.variables.selectRow(0)  # Remove CAD thickness; Material mu must retain its cells.
    w.remove_definition('variables')
    pump()
    remapped = [[w.method_detail.item(r, c).text() for c in range(w.method_detail.columnCount())]
                for r in range(w.method_detail.rowCount())]
    assert all(new == [old[0], old[2], old[-1]] for old, new in zip(original, remapped)), remapped
    add_width(w)  # A new CAD width column must be empty, never reuse old thickness.
    expanded = [[w.method_detail.item(r, c).text() for c in range(w.method_detail.columnCount())]
                for r in range(w.method_detail.rowCount())]
    assert all(new == [old[0], old[2], '', old[-1]] for old, new in zip(original, expanded)), expanded
    s.save_document('numerical')
    error = blocked(lambda: s.freeze('numerical'))
    return {'case_and_use_preserved': True, 'material_values_preserved': True,
            'new_width_cells_empty': True, 'admission_error': error}


def moo_response_binding():
    s, _, w = window('numerical', 'moo-binding')
    w.top_tabs.setCurrentIndex(3)
    w.sheet_tabs.setCurrentIndex(0)
    pump()
    row = next(i for i in range(w.method_detail.rowCount())
               if w.method_detail.item(i, 0).text() == 'Displacement')
    cell(w.method_detail, row, 1, '.25')
    cell(w.method_detail, row, 2, 'Upper bound')
    response = next(r for r in s.doc('numerical')['draft']['responses'] if r['name'] == 'Displacement')
    assert float(response['limit']) == .25 and response['role'] == 'Upper bound', response
    w.refresh()
    assert float(w.responses.item(row, 2).text()) == .25
    s.save_document('numerical')
    frozen = s.freeze('numerical')
    exact = next(r for r in frozen['payload']['responses'] if r['name'] == 'Displacement')
    assert float(exact['limit']) == .25 and exact['role'] == 'Upper bound'
    return {'canonical_and_frozen_displacement_limit': exact['limit']}


def method_budget_admission():
    s, _, w = window('numerical', 'budget')
    w.method.setCurrentText('DOE')
    w.top_tabs.setCurrentIndex(2)
    pump()
    cell(w.method_table, 0, 1, '1')
    s.save_document('numerical')
    default_error = blocked(lambda: s.freeze('numerical'))
    w.example_matrix()
    assert s.doc('numerical')['draft']['method_settings']['DOE']['Design points'] == 4
    w.top_tabs.setCurrentIndex(2)
    pump()
    cell(w.method_table, 0, 1, '4')
    s.save_document('numerical')
    valid = s.freeze('numerical')
    assert valid['payload']['budget'] == 4
    cell(w.method_table, 0, 1, '3')
    s.save_document('numerical')
    override_error = blocked(lambda: s.freeze('numerical'))
    return {'default_settings_budget_error': default_error,
            'example_matrix_budget_four_valid': True, 'budget_three_error': override_error}


def inverse_training_binding():
    s, _, w = window('numerical', 'train')
    s.mask(['A82'])
    s.save_document('data')
    s.refresh_data_source('numerical')
    w.method.setCurrentText('Inverse')
    w.top_tabs.setCurrentIndex(3)
    w.sheet_tabs.setCurrentIndex(0)
    pump()
    row = next(i for i in range(w.method_detail.rowCount())
               if w.method_detail.item(i, 0).text() == 'Tension A')
    cell(w.method_detail, row, 1, 'Holdout')
    s.save_document('numerical')
    no_train_error = blocked(lambda: s.freeze('numerical'))
    cell(w.method_detail, row, 1, 'Train')
    cell(w.method_detail, row, 2, '-1')
    s.save_document('numerical')
    negative_weight_error = blocked(lambda: s.freeze('numerical'))
    cell(w.method_detail, row, 2, '1')
    cell(w.method_detail, row, 3, '1')
    s.save_document('numerical')
    frozen = s.freeze('numerical')
    assert frozen['included_count'] == 300 and 'A82' not in frozen['included_ids']
    return {'all_holdout_error': no_train_error, 'negative_train_weight_error': negative_weight_error,
            'masked_train_included_count': frozen['included_count']}


def invalid_buffer_undo_redo():
    s, _, w = window('material', 'buffer-history')
    original = s.doc('material')['draft']['mu']
    cell(w.coeff, 0, 1, 'banana')
    assert s.doc('material')['buffers'].get('mu') == 'banana'
    assert s.doc('material')['dirty']
    w.undo(False)
    pump()
    assert s.doc('material')['buffers'] == {}
    assert s.doc('material')['draft']['mu'] == original
    assert float(w.coeff.item(0, 1).text()) == original
    assert not s.doc('material')['dirty']
    w.undo(True)
    pump()
    assert s.doc('material')['buffers'].get('mu') == 'banana'
    assert w.coeff.item(0, 1).text() == 'banana' and s.doc('material')['dirty']
    session_path = workspace / 'buffer-history-session.json'
    s.save_session(session_path)
    reopened = state.ReviewSession.open_session(session_path)
    assert reopened.doc('material')['buffers'].get('mu') == 'banana'
    assert reopened.history_step('material')
    assert reopened.doc('material')['buffers'] == {}
    return {'invalid_text_undo_redo_visible': True, 'session_reopen_undo': True}


def post_ordinary_save_cold_result():
    s, hub, _ = window('runner', 'post-result-save')
    frozen = s.freeze('simulation')
    job = s.create_attempt(frozen['id'])
    s.job_event(job['id'], 'result')
    result_id = job['result']
    assert result_id not in state.ReviewSession(workspace / 'unrelated').results
    w = hub.open_result(result_id)
    pump()
    w.array.setCurrentText('Contact pressure')
    w.time.setCurrentIndex(w.time.findData(0))
    pump()
    path = workspace / 'Ordinary-result-view.json'
    s.save_document(w.key, path)  # Establish the ordinary Save destination.
    w.filter.setCurrentText('Clip')
    w.apply_filter()
    assert w.save(), 'Ordinary GUI Save failed'
    expected_result = state.clone(s.results[result_id])
    expected_view = state.clone(s.doc(w.key)['saved'])
    script = """import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from prototype_state import ReviewSession
expected=json.loads(Path(sys.argv[3]).read_text())
s=ReviewSession(sys.argv[4]);key=s.open_document(sys.argv[2])
assert s.doc(key)['saved']==expected['view']
rid=s.doc(key)['saved']['result']
assert s.results[rid]==expected['result']
assert s.frozen[expected['result']['input']]==expected['frozen']
attempt=next(j for j in s.jobs if j['attempt']==expected['result']['attempt'])
assert attempt['input']==expected['result']['input'] and attempt['source']==expected['result']['source']
frame=s.post_frame(key)
assert frame['available'] and frame['time']==0 and frame['value']==0
assert frame['unit']=='MPa' and frame['association']=='CELLS'
print(json.dumps({'key':key,'result':rid,'frame':frame}))
"""
    expected_path = workspace / 'post-expected.json'
    expected_path.write_text(json.dumps({'result': expected_result, 'view': expected_view,
                                         'frozen': s.frozen[frozen['id']]}), encoding='utf-8')
    process = subprocess.run([sys.executable, '-c', script, str(args.source.resolve()), str(path),
                              str(expected_path), str(workspace / 'fresh-post-process')],
                             capture_output=True, text=True, timeout=15)
    assert process.returncode == 0, process.stderr
    return {'ordinary_file_fresh_process_result': result_id,
            'exact_source': expected_result['source'], 'cold_process_stdout': process.stdout.strip()}


checks = [('matrix_binding_remap', matrix_binding_remap), ('moo_canonical_response_binding', moo_response_binding),
          ('method_count_budget_admission', method_budget_admission), ('inverse_train_observation_binding', inverse_training_binding),
          ('invalid_buffer_history_undo_redo', invalid_buffer_undo_redo), ('post_ordinary_save_cold_result', post_ordinary_save_cold_result)]
for name, check in checks:
    start = len(errors)
    try:
        detail = check()
        pump()
        assert len(errors) == start, errors[start:]
        results.append({'check': name, 'status': 'PASS', 'detail': detail})
    except Exception:
        results.append({'check': name, 'status': 'FAIL', 'traceback': traceback.format_exc(), 'qt_callback_errors': errors[start:]})
    finally:
        for hub in hubs:
            for key, widget in hub.windows.items():
                if widget.isVisible():
                    safe = ''.join(c if c.isalnum() else '_' for c in key)
                    widget.grab().save(str(args.output / (name + '-' + safe + '.png')))
                    widget.hide()
        pump()
report = {'scope': 'FOCUSED_QT_SYNTHETIC_STATE_ONLY', 'platform': app.platformName(),
          'versions': {'PySide6': PySide6.__version__, 'python': sys.version},
          'native_solver_provider_windows': 'NOT_RUN', 'source': str(args.source.resolve()),
          'source_hashes': {n: hashlib.sha256((args.source / n).read_bytes()).hexdigest()
                            for n in ('prototype_state.py', 'qt_prototype.py', 'qt_widgets.py')},
          'checks': results, 'qt_callback_errors': errors,
          'status': 'PASS' if all(r['status']=='PASS' for r in results) and not errors else 'FAIL'}
(args.output / 'followup-results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
raise SystemExit(0 if report['status']=='PASS' else 1)
