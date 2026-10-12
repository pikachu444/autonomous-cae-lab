"""Bounded Qt acceptance checks for the isolated desktop UX prototype.

Run with an EXISTING Windows PySide6 interpreter; this script installs nothing:
    py -3.13 qt_acceptance.py --source <pro-ux-directory> --offscreen \
        --output <scratch-output-directory>

Checks Qt widgets and public synthetic state only. Passing offscreen checks does
not qualify a native FreeCAD/ParaView host, a solver, a provider, or Windows OS
integration. No product files are modified. Screenshots/JSON go to --output;
review document writes go to a separate temporary workspace under that directory.
The authoring dialogs are driven by QTimer/QTest with a 4-second rejection timer.
Missing PySide6 is reported as NOT_RUN, exit code 2. Failed assertions exit 1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True,
                        help='Directory containing qt_prototype.py and fixtures')
    parser.add_argument('--offscreen', action='store_true',
                        help='Set QT_QPA_PLATFORM=offscreen before importing Qt')
    parser.add_argument('--output', type=Path,
                        help='Scratch results/screenshot directory; default: new temp directory')
    return parser.parse_args()


def main():
    args = arguments()
    output = args.output or Path(tempfile.mkdtemp(prefix='caelab-qt-acceptance-'))
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.offscreen:
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    report = {'scope': 'QT_WIDGETS_SYNTHETIC_STATE_ONLY',
              'native_solver_provider': 'NOT_RUN', 'source': str(args.source.resolve()),
              'requested_platform': os.environ.get('QT_QPA_PLATFORM', 'default'),
              'output': str(output), 'checks': []}

    def finish(code):
        (output / 'qt-acceptance-results.json').write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return code

    try:
        import PySide6
        from PySide6.QtCore import Qt, QTimer, QRectF
        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox,
                                      QFormLayout, QLineEdit, QComboBox,
                                      QGraphicsScene)
    except ImportError as error:
        report.update(status='NOT_RUN', reason=str(error))
        return finish(2)

    source = args.source.resolve()
    sys.path.insert(0, str(source))
    try:
        import prototype_state as state
        import qt_prototype as prototype
        from qt_widgets import GraphNode
    except Exception:
        report.update(status='FAIL', reason='Prototype import failed',
                      traceback=traceback.format_exc())
        return finish(1)

    report['versions'] = {'python': sys.version, 'PySide6': PySide6.__version__}
    report['source_hashes'] = {
        name: hashlib.sha256((source / name).read_bytes()).hexdigest()
        for name in ('prototype_state.py', 'qt_prototype.py', 'qt_widgets.py')}
    app = QApplication.instance() or QApplication(['qt-acceptance'])
    app.setQuitOnLastWindowClosed(False)
    app.setStyle('Fusion')
    app.setStyleSheet(prototype.STYLE)
    report['actual_qt_platform'] = app.platformName()
    workspace = Path(tempfile.mkdtemp(prefix='review-workspace-', dir=output))
    report['temporary_workspace'] = str(workspace)
    hubs = []
    callback_errors = []

    # PySide signal/virtual-method exceptions otherwise may only print to stderr.
    old_hook = sys.excepthook

    def callback_hook(kind, error, tb):
        callback_errors.append(''.join(traceback.format_exception(kind, error, tb)))

    sys.excepthook = callback_hook

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

    def must_block(function):
        try:
            function()
        except state.ReviewError as error:
            return str(error)
        raise AssertionError('Expected ReviewError; operation was allowed')

    def typed_cell(table, row, column, text, *, f2=False, expected_initial=None):
        """Use the actual Qt delegate editor and commit its typed value."""
        item = table.item(row, column)
        assert item is not None, (row, column)
        table.setCurrentCell(row, column)
        table.setFocus()
        if f2:
            QTest.keyClick(table, Qt.Key.Key_F2)
        else:
            table.editItem(item)
        pump()
        editor = QApplication.focusWidget()
        assert isinstance(editor, QLineEdit), 'Expected active table QLineEdit delegate'
        if expected_initial is not None:
            assert float(editor.text()) == expected_initial, (
                'Editor changed the exact initial value', editor.text(), expected_initial)
        QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(editor, text)
        QTest.keyClick(editor, Qt.Key.Key_Return)
        pump()

    def form_field(dialog, label):
        form = dialog.layout()
        assert isinstance(form, QFormLayout), 'Expected QFormLayout authoring dialog'
        for row in range(form.rowCount()):
            entry = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            if entry and entry.widget() and entry.widget().text().rstrip(':') == label:
                return form.itemAt(row, QFormLayout.ItemRole.FieldRole).widget()
        raise AssertionError('Missing form field: ' + label)

    def type_line(dialog, label, value):
        editor = form_field(dialog, label)
        assert isinstance(editor, QLineEdit), label
        editor.setFocus()
        QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(editor, value)

    def drive_dialog(action, title, fill):
        """Fill/accept one known modal; reject on errors or timeout, never hang."""
        seen = {'dialog': False, 'done': False, 'error': None}

        def visit():
            dialog = app.activeModalWidget()
            if not isinstance(dialog, QDialog) or dialog.windowTitle() != title:
                seen['error'] = 'Expected active dialog: ' + title
                if isinstance(dialog, QDialog):
                    dialog.reject()
                return
            seen['dialog'] = True
            try:
                fill(dialog)
                buttons = dialog.findChild(QDialogButtonBox)
                ok = buttons.button(QDialogButtonBox.StandardButton.Ok) if buttons else None
                assert ok is not None, 'Missing OK button'
                seen['done'] = True
                QTest.mouseClick(ok, Qt.MouseButton.LeftButton)
            except Exception:
                seen['error'] = traceback.format_exc()
                dialog.reject()

        watchdog = QTimer()
        watchdog.setSingleShot(True)

        def timeout():
            seen['error'] = 'Modal dialog timed out: ' + title
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
        assert seen['dialog'] and seen['done'] and seen['error'] is None, seen
        pump()

    def simulation_gate():
        s, _, w = window('simulation', 'simulation-gate')
        dt = w.numeric_fields.index('time_step')
        typed_cell(w.table, dt, 1, '-1e-6')
        assert s.doc('simulation')['draft']['time_step'] == -1e-6
        s.save_document('simulation')  # Invalid drafts remain saveable.
        error = must_block(lambda: s.freeze('simulation'))
        typed_cell(w.table, dt, 1, '1e-6')
        typed_cell(w.table, w.numeric_fields.index('force'), 1, '-250')
        if 'initial_velocity' in w.numeric_fields:
            typed_cell(w.table, w.numeric_fields.index('initial_velocity'), 1, '0')
            typed_cell(w.table, w.numeric_fields.index('angular_velocity'), 1, '0')
        else:
            w.pages.setCurrentIndex(w.nodes.index('Initial conditions'))
            pump()
            typed_cell(w.initial, 0, 1, '0')
            typed_cell(w.initial, 1, 1, '0')
        assert not s.diagnostics('simulation'), s.diagnostics('simulation')
        s.save_document('simulation')
        frozen = s.freeze('simulation')
        assert frozen['payload']['force'] == -250
        assert frozen['payload']['time_step'] == 1e-6
        assert frozen['payload']['initial_velocity'] == 0
        assert frozen['payload']['angular_velocity'] == 0
        return {'negative_dt_block': error, 'repaired_input': frozen['source']}

    def cad_gate():
        s, _, w = window('cad', 'cad-gate')
        typed_cell(w.props, 0, 1, '15')
        assert s.doc('cad')['draft']['thickness'] == 15
        assert s.doc('cad')['draft']['mesh']['stale'] is True
        s.save_document('cad')
        must_block(lambda: s.freeze('cad'))
        w.rebuild_mesh()
        s.save_document('cad')
        s.freeze('cad')
        for side in ('set_a', 'set_b'):
            payload = state.clone(s.doc('cad')['draft'])
            original = state.clone(payload['contact'][side])
            payload['contact'][side] = []
            s.change('cad', payload, 'Acceptance empty contact ' + side)
            s.save_document('cad')
            must_block(lambda: s.freeze('cad'))
            payload['contact'][side] = original
            s.change('cad', payload, 'Acceptance restore contact ' + side)
            s.save_document('cad')
        return {'stale_geometry_blocked': True, 'empty_set_a_b_blocked': True}

    def numerical_gate_undo():
        s, _, w = window('numerical', 'numerical-gate')
        w.top_tabs.setCurrentIndex(1)
        pump()
        typed_cell(w.responses, 0, 1, 'banana')
        assert s.doc('numerical')['draft']['responses'][0]['role'] == 'banana'
        s.save_document('numerical')
        error = must_block(lambda: s.freeze('numerical'))
        typed_cell(w.responses, 0, 1, 'Minimize')
        w.top_tabs.setCurrentIndex(0)
        pump()
        assert float(w.variables.item(0, 2).text()) == 14
        typed_cell(w.variables, 0, 2, '15')
        assert s.doc('numerical')['draft']['variables'][0]['start'] == 15
        w.undo(False)
        pump()
        assert s.doc('numerical')['draft']['variables'][0]['start'] == 14
        assert float(w.variables.item(0, 2).text()) == 14
        assert w.responses.item(0, 1).text() == 'Minimize'
        return {'invalid_role_block': error, 'visible_start_sequence': [14, 15, 14]}

    def scientific_f2_preservation():
        """Exercise actual F2 editors: never accept a two-decimal float delegate."""
        evidence = []
        for tool, field, entries in (
                ('simulation', 'time_step', [('0.001', .001), ('1e-6', 1e-6)]),
                ('thermoelastic', 'alpha', [('1.2e-5', 1.2e-5)])):
            s, _, w = window(tool, 'scientific-' + tool)
            row = w.numeric_fields.index(field)
            for text, expected in entries:
                initial = s.doc(tool)['draft'][field]
                typed_cell(w.table, row, 1, text, f2=True, expected_initial=initial)
                assert s.doc(tool)['draft'][field] == expected
                assert float(w.table.item(row, 1).text()) == expected
                receipt = s.save_document(tool)
                assert s.doc(tool)['saved'][field] == expected
                disk = json.loads(Path(receipt['path']).read_text(encoding='utf-8'))
                assert disk['document']['saved'][field] == expected
                reopened = state.ReviewSession(workspace / ('scientific-reopen-' + tool))
                reopened.open_document(receipt['path'])
                assert reopened.doc(tool)['saved'][field] == expected
                assert reopened.doc(tool)['draft'][field] == expected
                cold_hub = prototype.DesktopHub(reopened)
                hubs.append(cold_hub)
                cold_window = cold_hub.open(tool)
                pump()
                assert float(cold_window.table.item(row, 1).text()) == expected
                typed_cell(cold_window.table, row, 1, text, f2=True,
                           expected_initial=expected)
                assert reopened.doc(tool)['draft'][field] == expected
                evidence.append({'tool': tool, 'field': field, 'typed': text,
                                 'exact_value': expected, 'saved_revision': receipt['revision'],
                                 'reopened_visible_text': cold_window.table.item(row, 1).text()})
                cold_window.hide()
                w.show()
                w.activateWindow()
                pump()
        return {'exact_f2_save_reopen': evidence}

    def numerical_evaluator_row_height():
        _, _, w = window('numerical', 'evaluator-height')
        row = w.evaluator.parentWidget()
        height = row.height()
        assert row.isVisible() and w.evaluator.isVisible()
        assert 0 < height <= 38, ('Evaluator row height exceeds compact design', height)
        assert w.evaluator.height() <= height
        assert w.variables.viewport().height() > height, 'Evaluator row displaced the research table'
        return {'evaluator_row_height_px': height,
                'combo_height_px': w.evaluator.height(),
                'variables_viewport_height_px': w.variables.viewport().height()}

    def new_plan_authoring():
        s = state.ReviewSession(workspace / 'new-plan')
        payload = state.clone(s.doc('numerical')['saved'])
        payload.update(method='DOE', evaluator='Unassigned', variables=[], responses=[])
        key = 'plan:acceptance'
        s.documents[key] = state.make_document(key, 'Typed research plan', 'Numerical',
                                               'N-ACCEPTANCE', 0, payload)
        hub = prototype.DesktopHub(s)
        hubs.append(hub)
        w = hub.open(key)
        pump()
        must_block(lambda: s.freeze(key))
        w.evaluator.setCurrentText('Structural Simulation')
        pump()

        def variable(dialog):
            form_field(dialog, 'Owner').setCurrentText('cad')
            form_field(dialog, 'Field').setCurrentText('thickness')
            type_line(dialog, 'Start', '14')
            type_line(dialog, 'Search lower', '12')
            type_line(dialog, 'Search upper', '16')

        drive_dialog(w.add_variable, 'Bind variable', variable)

        def response(dialog):
            form_field(dialog, 'Quantity').setCurrentText('Displacement')
            form_field(dialog, 'Role').setCurrentText('Upper bound')
            type_line(dialog, 'Limit / target', '0.35')
            type_line(dialog, 'Location', 'Gauge endpoints')
            type_line(dialog, 'Time [s]', '0.04')

        drive_dialog(w.add_response, 'Define response', response)
        assert len(s.doc(key)['draft']['variables']) == 1
        assert len(s.doc(key)['draft']['responses']) == 1
        assert w.variables.rowCount() == 1 and w.responses.rowCount() == 1
        assert w.responses.item(0, 1).text() == 'Upper bound'
        assert not s.diagnostics(key), s.diagnostics(key)
        s.save_document(key)
        frozen = s.freeze(key)
        assert frozen['payload']['variables'][0]['field'] == 'thickness'
        assert frozen['payload']['responses'][0]['limit'] == .35
        assert frozen['source']['id'] == 'N-ACCEPTANCE'
        assert w.cases.rowCount() == 0, 'New DOE plan must not show MOO candidates'
        return {'typed_variable_response': True, 'frozen_source': frozen['source']}

    def post_atomic_and_frame():
        s, _, w = window('post', 'post-frame')
        before = state.clone(s.doc('post')['draft'])
        depth = len(s.doc('post')['undo'])
        w.array.setCurrentText('Contact pressure')
        pump()
        selected = s.doc('post')['draft']
        assert (selected['array'], selected['unit'], selected['association']) == (
            'Contact pressure', 'MPa', 'CELLS')
        assert len(s.doc('post')['undo']) == depth + 1
        w.undo(False)
        pump()
        assert s.doc('post')['draft'] == before, 'One Undo must restore exact view draft'
        assert (w.array.currentText(), w.association.currentText()) == (
            before['array'], before['association'])
        zero = w.time.findData(0)
        assert zero >= 0
        w.time.setCurrentIndex(zero)
        pump()
        frame = s.post_frame('post')
        assert frame['available'] and frame['time'] == 0 and frame['value'] == 0
        assert w.viewer.field_available and w.viewer.field_max == 0
        assert 't = 0' in w.viewer.field
        assert w.curve.cursor_x == 0 and '0' in w.curve.caption
        assert w.curve.series[0]['y'][0] == 0
        assert all(float(w.measure.item(row, 1).text()) == 0
                   for row in range(w.measure.rowCount()))
        w.grab().save(str(output / 'post-time-zero.png'))
        # .03 is absent in this retained result; rendering must not interpolate.
        s.edit('post', 'time', .03)
        w.render_frame()
        pump()
        assert not s.post_frame('post')['available']
        assert not w.viewer.field_available and 'unavailable' in w.viewer.annotation.lower()
        assert w.curve.series == [] and 'Unavailable' in w.curve.caption
        assert all(w.measure.item(row, 1).text() == 'Unavailable'
                   for row in range(w.measure.rowCount()))
        return {'atomic_field_undo': True, 'time_zero_synchronized': True,
                'unretained_time': .03, 'interpolation': False}

    def material_tab_backtab():
        s, _, w = window('material', 'material-focus')
        assert not s.diagnostics('material')
        w.show()
        w.activateWindow()
        w.curve.setFocus(Qt.FocusReason.OtherFocusReason)
        pump()
        assert QApplication.focusWidget() is w.curve, 'CurveView did not receive focus'
        QTest.keyClick(w.curve, Qt.Key.Key_Tab)
        pump()
        next_widget = QApplication.focusWidget()
        assert next_widget is not None and next_widget is not w.curve, 'Tab was swallowed'
        next_type = type(next_widget).__name__
        # Test backwards delegation from the same custom QWidget. A neighboring
        # table's own cell-level Tab navigation is a separate standard Qt behavior.
        w.curve.setFocus(Qt.FocusReason.OtherFocusReason)
        pump()
        QTest.keyClick(w.curve, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
        pump()
        previous_widget = QApplication.focusWidget()
        assert previous_widget is not None and previous_widget is not w.curve, 'Backtab was swallowed'
        assert not s.doc('material')['dirty'], 'Focus traversal altered valid Material'
        return {'Tab_next_widget': next_type,
                'Backtab_previous_widget': type(previous_widget).__name__}

    def graph_label_pixels():
        scene = QGraphicsScene()
        node = GraphNode('acceptance', 'CAD / FE test label', 0, 0, lambda: None)
        scene.addItem(node)

        def render():
            image = QImage(190, 78, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.white)
            painter = QPainter(image)
            scene.render(painter, QRectF(0, 0, 190, 78), QRectF(-10, -10, 190, 78))
            painter.end()
            return image

        labeled = render()
        node.label = ''
        blank = render()
        changed = sum(labeled.pixel(x, y) != blank.pixel(x, y)
                      for y in range(15, 63) for x in range(20, 170))
        assert changed > 20, 'No sufficient painted label pixel difference: ' + str(changed)
        labeled.save(str(output / 'graph-labeled.png'))
        blank.save(str(output / 'graph-empty-label.png'))
        return {'interior_pixel_difference': changed,
                'claim': 'GraphNode painted text only; no OS/native integration claim'}

    checks = [
        ('simulation_dt_repair_signed_force_zero', simulation_gate),
        ('cad_geometry_stale_and_empty_contact_sets', cad_gate),
        ('numerical_unknown_role_and_visible_undo', numerical_gate_undo),
        ('scientific_f2_exact_values_save_reopen', scientific_f2_preservation),
        ('numerical_evaluator_compact_row_height', numerical_evaluator_row_height),
        ('new_plan_typed_variable_response_authoring', new_plan_authoring),
        ('post_atomic_field_undo_zero_and_unavailable_frame', post_atomic_and_frame),
        ('material_qtest_tab_backtab', material_tab_backtab),
        ('graph_node_painted_label_pixels', graph_label_pixels),
    ]
    try:
        for name, check in checks:
            start_errors = len(callback_errors)
            try:
                detail = check()
                pump()
                assert len(callback_errors) == start_errors, callback_errors[start_errors:]
                report['checks'].append({'check': name, 'status': 'PASS', 'detail': detail})
            except Exception:
                report['checks'].append({'check': name, 'status': 'FAIL',
                                         'traceback': traceback.format_exc(),
                                         'qt_callback_errors': callback_errors[start_errors:]})
            finally:
                for hub in hubs:
                    for key, widget in hub.windows.items():
                        if widget.isVisible():
                            safe_key = ''.join(c if c.isalnum() else '_' for c in key)
                            widget.grab().save(str(output / (name + '-' + safe_key + '.png')))
                            widget.hide()  # Avoid invoking unsaved-close dialogs in cleanup.
                pump()
    finally:
        sys.excepthook = old_hook
    report['status'] = 'PASS' if all(c['status'] == 'PASS' for c in report['checks']) else 'FAIL'
    report['qt_callback_errors'] = callback_errors
    return finish(0 if report['status'] == 'PASS' else 1)


if __name__ == '__main__':
    raise SystemExit(main())
