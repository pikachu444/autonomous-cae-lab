"""Real Qt widgets when available. Offscreen is not Windows/FreeCAD acceptance."""
from copy import deepcopy
import os
from pathlib import Path

import pytest

from test_pre_motion import setup, qt_panel
from test_pre_motion_general_relation_owner import independent_definition, raw_editor
from test_pre_motion_general_relations import inputs, follower
from apps.desktop_pre.motion_relation import relation_values
from apps.desktop_pre.motion_relation_editor import RelationEditor


@pytest.fixture
def editor():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    pytest.importorskip('PySide6')
    from PySide6 import QtCore, QtWidgets, QtTest
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    drives, joints = inputs()
    value = follower(drives, joints, expression='amplitude*sin(A)+B',
        constants=[{'name': 'amplitude', 'value': 30., 'unit': 'deg'}])['relation']
    context = {'drives': drives, 'joints': joints, 'choices': [], 'time_label': '0'}
    def update_choices():
        context['choices'] = [{'label': '조립 / '+d['joint_id']+' / '+('회전' if d['type']=='Angular' else '이동'),
            'binding': {'joint_id': d['joint_id'], 'type': d['type'], 'path': deepcopy(joints[d['joint_id']]['path']),
                'unit': d['unit']}, 'issue': '', 'value': '0'} for d in drives]
    update_choices()
    scope = ['document', 'owner', 'assembly', 'drive', 0]
    changes = []
    widget = RelationEditor(QtCore, QtWidgets, changed=lambda v: changes.append(deepcopy(v)),
        context=lambda: context, scope=lambda: tuple(scope))
    widget.load(value); widget.widget.resize(960, 700); widget.widget.show(); app.processEvents()
    yield app, QtCore, QtTest, widget, context, scope, changes, update_choices
    widget.cancel_picker(); widget.widget.close(); widget.widget.deleteLater(); app.processEvents()


def type_text(qt, field, text):
    app, C, T = qt[:3]
    field.setFocus(); field.selectAll(); T.QTest.keyClicks(field, text); app.processEvents()


@pytest.mark.parametrize('width', [480, 960])
def test_real_widget_expression_constants_keyboard_and_narrow_layout(editor, width):
    app, C, T, w, context, scope, changes, _ = editor
    w.widget.resize(width, 700); app.processEvents()
    type_text(editor, w.expression, 'amplitude*sin(')
    field = w.constants.cellWidget(0, 1)
    type_text(editor, field, '1e')
    assert field.hasFocus()  # no forced focus-out required to retain pending text
    assert w.value()['constants'][0]['value'] == '1e'
    assert w.value()['expression'] == 'amplitude*sin('
    assert changes[-1] == w.value()
    before = w.value(); cursor = field.cursorPosition()
    w.refresh_context(); app.processEvents()
    assert w.value() == before and field.hasFocus() and field.cursorPosition() == cursor
    assert w.expression.width() > 100 and w.widget.width() <= width
    # Optional captures exist only if this REAL Qt test actually ran.
    folder = os.environ.get('CAELAB_M1_QT_CAPTURE_DIR')
    if folder:
        Path(folder).mkdir(parents=True, exist_ok=True)
        assert w.widget.grab().save(str(Path(folder)/f'relation-{width}.png'))


def test_alias_unit_edit_reorder_and_selection_are_raw(editor):
    app, C, T, w, context, scope, changes, _ = editor
    type_text(editor, w.sources.cellWidget(0, 0), 'sourceA')
    unit = w.constants.cellWidget(0, 2)
    unit.setCurrentText('mm/deg')
    assert w.value()['sources'][0]['alias'] == 'sourceA'
    assert w.value()['constants'][0]['unit'] == 'mm/deg'
    w.sources.setCurrentCell(0, 0); w.move('sources', 1)
    assert w.value()['sources'][1]['alias'] == 'sourceA' and w.view()['source_row'] == 1
    w.add_constant(); type_text(editor, w.constants.cellWidget(1, 1), '1e')
    w.move('constants', -1)
    assert w.value()['constants'][0]['value'] == '1e' and w.view()['constant_row'] == 0
    w.remove('constants'); assert len(w.value()['constants']) == 1


def test_reselect_escape_is_exact_cancel_no_implicit_binding(editor):
    app, C, T, w, context, scope, changes, _ = editor
    w.sources.setCurrentCell(0, 0)
    before = w.value(); view = w.view(); count = len(changes)
    w.choose_source(); app.processEvents()
    dialog = w._dialog; combo, ack, ok, notice = dialog.relation_controls
    combo.setCurrentIndex(2)
    T.QTest.keyClick(dialog, C.Qt.Key_Escape); app.processEvents()
    assert w.value() == before and w.view() == view and len(changes) == count
    assert w._dialog is None


def test_reselect_commits_only_binding_keeps_alias_expression_constants(editor):
    app, C, T, w, context, scope, changes, _ = editor
    w.sources.setCurrentCell(0, 0); before = w.value()
    w.choose_source(); app.processEvents()
    combo, ack, ok, notice = w._dialog.relation_controls
    combo.setCurrentIndex(2); T.QTest.mouseClick(ok, C.Qt.LeftButton); app.processEvents()
    now = w.value()
    assert now['sources'][0]['joint_id'] == 'B'
    assert now['sources'][0]['alias'] == 'A'
    assert now['expression'] == before['expression'] and now['constants'] == before['constants']


def test_unit_reconfirmation_needs_explicit_ack_and_never_changes_gain(editor):
    app, C, T, w, context, scope, changes, update = editor
    w.sources.setCurrentCell(0, 0)
    before = w.value(); context['drives'][0]['unit'] = 'rad'; update(); w.refresh_context()
    assert '단위' in w.source_notice.text()
    w.confirm_unit(); app.processEvents()
    dialog = w._dialog; combo, ack, ok, notice = dialog.relation_controls
    assert not ok.isEnabled() and ack.isVisible()
    T.QTest.keyClick(dialog, C.Qt.Key_Escape); app.processEvents()
    assert w.value() == before
    w.confirm_unit(); app.processEvents()
    combo, ack, ok, notice = w._dialog.relation_controls
    ack.setChecked(True); assert ok.isEnabled()
    T.QTest.mouseClick(ok, C.Qt.LeftButton); app.processEvents()
    assert w.value()['sources'][0]['unit'] == 'rad'
    assert w.value()['constants'] == before['constants']


@pytest.mark.parametrize('changed', ['owner', 'assembly', 'edit', 'raw', 'path'])
def test_late_picker_cannot_replace_new_owner_selection_input_or_path(editor, changed):
    app, C, T, w, context, scope, changes, _ = editor
    w.sources.setCurrentCell(0, 0); w.choose_source(); app.processEvents()
    combo, ack, ok, notice = w._dialog.relation_controls
    combo.setCurrentIndex(2)
    if changed == 'owner': scope[1] = 'new owner'
    elif changed == 'assembly': scope[2] = 'other assembly'
    elif changed == 'edit': scope[-1] += 1
    elif changed == 'raw': w._value['expression'] += '+other'
    else: context['joints']['B']['path'] = ['Rig', 'Other', 'B']
    before = w.value(); count = len(changes)
    T.QTest.mouseClick(ok, C.Qt.LeftButton); app.processEvents()
    assert w.value() == before and len(changes) == count
    assert not ok.isEnabled() and notice.text()


def test_missing_binding_read_refresh_and_hide_show_never_repairs_itself(editor):
    app, C, T, w, context, scope, changes, _ = editor
    before = w.value(); del context['joints']['A']
    w.sources.setCurrentCell(0, 0); w.refresh_context()
    assert '참조 없음' in w.source_notice.text()
    w.widget.hide(); app.processEvents(); w.widget.show(); app.processEvents(); w.refresh_context()
    assert w.value() == before and not changes


def panel_relation(fixture):
    app, widget, panel, queued, descriptor, setup = fixture
    owner, motion, target, d = independent_definition(setup)
    motion.dispatch('pre.motion.configure', {'definition': d}, target)
    panel._inspect_value(motion.dispatch('pre.motion.inspect', {}, target))
    panel._restore_editor(raw_editor(d)); panel.drives.setCurrentCell(2, 0); panel._drive_selected()
    return owner, motion, target, d, panel.general_relation.editor


def test_panel_pending_text_snapshot_restore_and_invalid_apply(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, d, w = panel_relation(qt_panel)
    from PySide6 import QtCore, QtTest
    type_text((app, QtCore, QtTest), w.constants.cellWidget(0, 1), '1e')
    snapshot = panel.editor_snapshot(); raw = snapshot['editor']['definition_draft']['drives'][2]['relation']
    assert raw['constants'][0]['value'] == '1e' and panel._edited
    motion.dispatch('pre.motion.save_editor', {'editor': snapshot['editor']}, target)
    before = len(queued); panel._configure(); assert len(queued) == before
    panel._restore_editor(snapshot['editor'])
    assert panel.general_relation.editor.value() == raw
    assert panel.general_relation.editor.view() == snapshot['editor']['relation_view']


def test_panel_selected_relation_hides_single_source_controls_and_keeps_the_relation(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, d, w = panel_relation(qt_panel)
    before = w.value()
    assert panel.drive_ratio.isHidden() and panel.drive_offset.isHidden() and panel.drive_source.isHidden()
    panel.drives.setCurrentCell(0, 0)
    assert not panel.drive_ratio.isHidden() and not panel.drive_source.isHidden()
    panel.drives.setCurrentCell(2, 0)
    assert panel.drive_ratio.isHidden() and w.value() == before
    assert not queued


def test_candidate_direct_callback_blocks_unsaved_relation_and_allows_explicit_repair(qt_panel):
    from types import SimpleNamespace as NS
    from apps.desktop_pre.assembly_pose_panel import attach_motion
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, d, w = panel_relation(qt_panel)
    submitted = []
    candidate_owner = NS(closed=False, pose_candidates=NS(busy=False,
        descriptor=lambda: {'busy': False, 'history': [], 'current': None}))
    connection = NS(QtWidgets=panel.Q, QtCore=panel.QtCore,
        submit_native=lambda *args, **kwargs: submitted.append((args, kwargs)))
    panel._frame_args = lambda: {'calculation_id': 'Kretained', 'frame': 2}
    actions = attach_motion(connection, candidate_owner, panel)
    try:
        from PySide6 import QtCore, QtTest
        type_text((app, QtCore, QtTest), w.constants.cellWidget(0, 1), '1e')
        panel._selected_calculation = lambda: {'accepted': True, 'persisted': True}
        actions.refresh()
        assert not actions.create.isEnabled()
        actions.start()
        assert not submitted and '편집을 적용하거나 취소' in actions.status.text()
        type_text((app, QtCore, QtTest), w.constants.cellWidget(0, 1), '30')
        panel._configure()
        op, args, selected, done = queued[-1]
        done({'status': 'COMPLETED', 'result': motion.dispatch(op, args, selected)})
        assert not panel._edited
        panel._joint_edited = True
        actions.refresh()
        assert not actions.create.isEnabled()
        actions.start()
        assert not submitted
        panel._joint_edited = False
        actions.refresh()
        assert actions.create.isEnabled()
        actions.start()
        assert submitted[0][0][:3] == ('pre.assembly_candidate.create',
            {'calculation_id': 'Kretained', 'frame': 2}, target)
    finally:
        actions.timer.stop(); actions.close(); actions.deleteLater(); app.processEvents()


def test_panel_late_apply_receipt_and_old_owner_save_do_not_replace_input(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, d, w = panel_relation(qt_panel)
    from PySide6 import QtCore, QtTest
    panel._configure(); op, args, selected, done = queued[-1]
    reply = motion.dispatch(op, args, selected)
    old = panel.editor_snapshot()
    type_text((app, QtCore, QtTest), w.expression, 'amplitude*sin(')
    before = panel.editor_snapshot()
    done({'status': 'COMPLETED', 'result': reply})
    assert panel.editor_snapshot()['editor']['definition_draft'] == before['editor']['definition_draft']
    panel._session = 'fresh-owner'; panel.accept_saved_editor(old)
    assert w.value()['expression'] == 'amplitude*sin(' and panel._edited
    count = len(queued); panel._send('pre.motion.calculate', {}); assert len(queued) == count
