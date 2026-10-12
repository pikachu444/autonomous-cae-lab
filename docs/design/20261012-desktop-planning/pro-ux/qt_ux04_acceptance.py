"""Four bounded UX-FIX-04 paths using synthetic Qt offscreen only."""
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
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QDialog, QDialogButtonBox, QFormLayout, QComboBox
import prototype_state as state
import qt_prototype as prototype
from qt_widgets import EngineeringView

args.output.mkdir(parents=True, exist_ok=True)
workspace = Path(tempfile.mkdtemp(prefix='ux04-workspace-', dir=args.output))
app = QApplication(['ux04-acceptance'])
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


def modal(action, title, inspect):
    result = {'visited': False, 'error': None}
    timer = QTimer()
    timer.setSingleShot(True)

    def visit():
        dialog = app.activeModalWidget()
        try:
            assert isinstance(dialog, QDialog) and dialog.windowTitle() == title
            inspect(dialog)
            result['visited'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        finally:
            if isinstance(dialog, QDialog) and dialog.isVisible():
                dialog.reject()

    def timeout():
        result['error'] = 'Modal timeout: ' + title
        dialog = app.activeModalWidget()
        if isinstance(dialog, QDialog):
            dialog.reject()

    timer.timeout.connect(timeout)
    timer.start(4000)
    QTimer.singleShot(0, visit)
    try:
        action()
    finally:
        timer.stop()
    assert result['visited'] and result['error'] is None, result
    pump()


def form_field(dialog, label):
    form = dialog.layout()
    assert isinstance(form, QFormLayout)
    for row in range(form.rowCount()):
        item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
        if item and item.widget() and item.widget().text().rstrip(':') == label:
            return form.itemAt(row, QFormLayout.ItemRole.FieldRole).widget()
    raise AssertionError('Missing form field ' + label)


def cad_sketch_roundtrip():
    s, _, w = window('cad', 'cad-sketch')
    w.mode.setCurrentText('Sketch')
    w.draw_line()
    pump()
    count = len(s.doc('cad')['draft']['sketch'].get('lines', []))
    QTest.mousePress(w.viewer, Qt.MouseButton.LeftButton, pos=QPoint(100, 100))
    QTest.mouseMove(w.viewer, QPoint(180, 180))
    QTest.mouseRelease(w.viewer, Qt.MouseButton.LeftButton, pos=QPoint(180, 180))
    pump()
    assert len(s.doc('cad')['draft']['sketch']['lines']) == count + 1
    cell(w.constraints, 0, 1, '90')
    w.constrain_sketch()
    assert s.doc('cad')['draft']['width'] == 90
    assert s.doc('cad')['draft']['sketch']['fully_constrained']
    lines = state.clone(s.doc('cad')['draft']['sketch']['lines'])
    receipt = s.save_document('cad')
    cold = state.ReviewSession(workspace / 'cad-sketch-cold')
    cold.open_document(receipt['path'])
    cold_hub = prototype.DesktopHub(cold)
    hubs.append(cold_hub)
    reopened = cold_hub.open('cad')
    reopened.mode.setCurrentText('Sketch')
    pump()
    assert cold.doc('cad')['saved']['sketch']['lines'] == lines
    assert cold.doc('cad')['saved']['sketch']['fully_constrained']
    assert float(reopened.constraints.item(0, 1).text()) == 90
    assert reopened.sketch_lines.rowCount() == len(lines)
    assert reopened.viewer.model_width == 90 and reopened.viewer.sketch_segments == lines
    return {'mouse_drawn_lines': lines, 'saved_reopened_width': 90, 'table_view_consistent': True}


def saved_geometry_and_selected_step():
    s, hub, cad = window('cad', 'geometry-step')
    cad.angle.setValue(45)
    cad.use_pose()
    cad.instances.setValue(4)
    cad.hole.setChecked(True)
    cad.mesh_size.setValue(1)
    cad.rebuild_mesh()
    s.save_document('cad')
    cad.to_simulation()
    sim = hub.open('simulation')
    pump()
    assert sim.viewer.joint_angle == 45
    assert sim.viewer.instances == 4 and sim.viewer.through_hole
    assert sim.viewer.mesh_size == 1
    assert sim.data['model_ref'] == {'id': 'CAD-01', 'revision': s.doc('cad')['revision']}

    def hold_dialog(dialog):
        name = form_field(dialog, 'Name')
        duration = form_field(dialog, 'Duration [s]')
        name.setText('Hold')
        duration.setText('2')
        buttons = dialog.findChild(QDialogButtonBox)
        QTest.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton)

    modal(sim.step_dialog, 'Analysis step', hold_dialog)
    sim.tree.setCurrentItem(sim.tree.topLevelItem(0).child(sim.nodes.index('Steps')))
    sim.activateWindow()
    sim.steps.selectRow(1)
    pump()
    row = sim.numeric_fields.index('duration')
    assert float(sim.table.item(row, 1).text()) == 2
    original_load = state.clone(sim.data['steps'][0])
    cell(sim.table, row, 1, '3')
    assert sim.data['steps'][1]['duration'] == 3
    assert sim.data['steps'][0] == original_load
    assert sim.data['duration'] == original_load['duration']
    assert float(sim.steps.item(1, 1).text()) == 3
    thermal = hub.open('thermal')
    pump()
    root = thermal.tree.topLevelItem(0)
    hidden = {root.child(i).text(0): root.child(i).isHidden() for i in range(root.childCount())}
    for label in ('Contact', 'Initial conditions', 'Failure'):
        assert hidden[label], hidden
    assert not thermal.geometry_action.isEnabled()
    assert not thermal.steps.isVisible() and not thermal.step_controls.isVisible()
    return {'saved_geometry': {'pose': 45, 'instances': 4, 'hole': True, 'mesh': 1},
            'hold_selected_duration': 2, 'hold_edited_duration': 3,
            'load_unchanged': original_load, 'thermal_hidden_nodes': hidden}


def post_compare_exact_geometry():
    s, _, w = window('post', 'post-compare')
    s.edit('cad', 'thickness', 99)
    w.refresh()
    assert w.viewer.thickness == 13.7, w.viewer.thickness
    evidence = {}

    def inspect(dialog):
        picker = dialog.findChild(QComboBox)
        index = picker.findData('fixture-result-p04')
        assert index >= 0
        picker.setCurrentIndex(index)
        pump()
        views = dialog.findChildren(EngineeringView)
        assert len(views) == 2
        views.sort(key=lambda view: view.mapTo(dialog, QPoint(0, 0)).x())
        actual = [v.thickness for v in views]
        assert actual == [13.7, 14.6], actual
        evidence['thicknesses'] = actual
        dialog.grab().save(str(args.output / 'post-p19-p04-compare.png'))
        dialog.reject()

    modal(w.compare, 'Compare results', inspect)
    assert s.doc('cad')['draft']['thickness'] == 99
    return {'current_cad_draft_thickness': 99, 'result_view_thicknesses': evidence['thicknesses']}


def expert_plan_result_reply_cold():
    s, hub, _ = window('expert', 'expert-research')
    payload = state.clone(s.doc('numerical')['saved'])
    payload.update(method='DOE', budget=4, parent_key='expert', evaluator='Structural Simulation')
    key = 'plan:expert-acceptance'
    s.documents[key] = state.make_document(key, 'Discussion experiment', 'Numerical',
                                         'N-UX04-EXPERT', 0, payload)
    plan = hub.open(key)
    plan.example_matrix()
    s.save_document(key)
    frozen = s.freeze(key)
    job = s.create_attempt(frozen['id'])
    s.job_event(job['id'], 'result')
    rid = job['result']
    assert s.results[rid]['kind'] == 'numerical'
    assert s.results[rid]['computed_from_input'] is False
    result_dialog = hub.open_result(rid)
    pump()
    assert result_dialog.result_id == rid and result_dialog.result_tables
    locator = 'DOE / Design matrix / d1'
    expert = hub.discuss_result(rid, locator)
    assert expert.key == 'expert'
    expert.composer.setPlainText('Review the selected synthetic DOE row before a real evaluation.')
    expert.save_reply()
    pump()
    turn = s.doc('expert')['draft']['turns'][-1]
    assert turn['actual'] and turn['evidence'] == [rid]
    path = workspace / 'Expert-ordinary-save.json'
    s.save_document('expert', path)
    expert.question.setText('Compare the selected DOE row')
    expert.question_changed()
    assert expert.save()
    expected = {'result': s.results[rid], 'view': s.doc('expert')['saved']}
    expected_file = workspace / 'expert-expected.json'
    expected_file.write_text(json.dumps(expected), encoding='utf-8')
    code = """import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from prototype_state import ReviewSession
s=ReviewSession(sys.argv[4]);key=s.open_document(sys.argv[2]);expected=json.loads(Path(sys.argv[3]).read_text())
assert s.doc(key)['saved']==expected['view']
rid=expected['result']['id'];assert s.results[rid]==expected['result'];assert s.results[rid]['kind']=='numerical'
assert s.doc(key)['saved']['turns'][-1]['evidence']==[rid]
print('ordinary Expert cold process exact numerical evidence PASS')
"""
    process = subprocess.run([sys.executable, '-c', code, str(args.source.resolve()), str(path),
                              str(expected_file), str(workspace / 'expert-cold-process')],
                             capture_output=True, text=True, timeout=15)
    assert process.returncode == 0, process.stderr
    study_payload = state.clone(s.doc('study')['draft'])
    study_payload['evidence'].append({'ref': rid, 'locator': locator, 'hypothesis': 'H1',
                                     'relation': 'Neutral', 'synthetic': True})
    s.change('study', study_payload, 'Acceptance relate exact numerical evidence')
    study = hub.open('study')
    study.judgment.setCurrentText('Insufficient evidence')
    study.reason.setPlainText('The selected table is an authored example; it does not establish a physical conclusion.')
    study.apply_judgment()
    s.save_document('study')
    session_path = workspace / 'Expert-Study-review-session.json'
    s.save_session(session_path)
    reopened = state.ReviewSession.open_session(session_path)
    assert reopened.doc('study')['saved']['judgment'] == 'Insufficient evidence'
    assert reopened.doc('study')['saved']['reason'] == study.reason.toPlainText()
    assert any(e['ref'] == rid for e in reopened.doc('study')['saved']['evidence'])
    assert reopened.results[rid] == s.results[rid]
    return {'result_id': rid, 'kind': 'numerical', 'computed_from_input': False,
            'ordinary_expert_cold_evidence': True, 'session_study_judgment': 'Insufficient evidence'}


checks = [('cad_draw_width_constrain_save_reopen', cad_sketch_roundtrip),
          ('saved_geometry_selected_step_thermal_pages', saved_geometry_and_selected_step),
          ('post_comparison_exact_result_geometry', post_compare_exact_geometry),
          ('expert_plan_result_reply_save_cold_study_judgment', expert_plan_result_reply_cold)]
for name, check in checks:
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
            widgets = list(hub.windows.values()) + list(getattr(hub, 'result_dialogs', {}).values())
            for index, widget in enumerate(widgets):
                if widget.isVisible():
                    widget.grab().save(str(args.output / (name + '-' + str(index) + '.png')))
                    widget.hide()
        pump()
report = {'scope': 'FOUR_UX04_SYNTHETIC_QT_PATHS', 'platform': app.platformName(),
          'versions': {'PySide6': PySide6.__version__, 'python': sys.version},
          'native_solver_provider_windows': 'NOT_RUN', 'source': str(args.source.resolve()),
          'source_hashes': {n: hashlib.sha256((args.source / n).read_bytes()).hexdigest()
                            for n in ('prototype_state.py', 'qt_prototype.py', 'qt_widgets.py')},
          'checks': results, 'qt_callback_errors': errors,
          'status': 'PASS' if all(r['status']=='PASS' for r in results) and not errors else 'FAIL'}
(args.output / 'ux04-results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
raise SystemExit(0 if report['status']=='PASS' else 1)
