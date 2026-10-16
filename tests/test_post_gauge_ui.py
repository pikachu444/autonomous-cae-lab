"""Existing Qt measurement form and polling; native selection transport is a double."""
from copy import deepcopy
import time

import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QPushButton
from test_research_post_ui import app, window


def draft():
    return {'measurement': 'gauge', 'source_ref': 'Sfirst', 'array': 'U', 'association': 'POINTS',
        'point_indices': [], 'point1': [], 'point2': [], 'direction': [1,0,0], 'basis': 'fixed_cartesian',
        'coordinate_configuration': 'reference', 'time': None, 'time_units': None, 'time_origin': None,
        'units': 'mm', 'measure': 'displacement', 'frame': 'lab', 'coordinate_units': 'm', 'coordinate_frame': 'lab'}


def prepare(window, monkeypatch):
    window._kind = 'measurement'; window._draft = draft(); window._object_ref = None
    window._populate_editor()
    original = window.client._execute
    def captured(command):
        result = original(command)
        if command['operation'] == 'post.measurement_capture':
            assert command['arguments']['measurement'] == 'gauge'
            result['draft'].update(measurement='gauge', point_indices=[0,1], point1=[0,0,0], point2=[1,0,0],
                original_point_ids={'NativeNodeId':[100,101]}, time=.5)
            obj = next(row for row in window.client.document['state']['analysis']['objects'] if row['id'] == result['id'])
            obj.update(deepcopy(result))
        return result
    monkeypatch.setattr(window.client, '_execute', captured)


def settle(app, window):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        app.processEvents()
        if window._pending is None and not window._busy: return
        time.sleep(.005)
    raise AssertionError('Existing Post Qt command did not settle')


def test_two_point_selection_populates_reference_geometry_and_swap_without_execution(app, window, monkeypatch):
    prepare(window, monkeypatch)
    assert window.fields[('measure',)][0].currentText() == '변위'
    assert window.edited_draft()['measure'] == 'displacement'
    assert window.capture_button.isEnabled()
    assert window.capture_selection()
    settle(app, window)
    selected = window.edited_draft()
    assert selected['measurement'] == 'gauge' and selected['point_indices'] == [0,1]
    assert selected['point1'] == [0,0,0] and selected['point2'] == [1,0,0] and selected['time'] == .5
    assert window.swap_gauge_points()
    swapped = window.edited_draft()
    assert swapped['point_indices'] == [1,0] and swapped['point1'] == [1,0,0] and swapped['point2'] == [0,0,0]
    assert swapped['original_point_ids'] == {'NativeNodeId':[101,100]} and swapped['direction'] == [1,0,0]
    assert [call[1] for call in window.client.calls] == ['post.measurement_capture']
    assert window.local_dirty


def test_unsupported_saved_quantity_stays_editable_until_explicit_displacement_choice(app, window):
    window._kind = 'measurement'; window._draft = {**draft(), 'measure': 'stress'}
    window._populate_editor()
    field = window.fields[('measure',)][0]
    assert field.currentText() == '지원하지 않는 물리량' and window.edited_draft()['measure'] == 'stress'
    field.setCurrentIndex(field.findData('displacement'))
    assert field.currentText() == '변위' and window.edited_draft()['measure'] == 'displacement'


def test_pending_capture_preserves_new_local_direction_and_disables_swap(app, window, monkeypatch):
    prepare(window, monkeypatch); window.client.release = False
    assert window.capture_selection()
    before = deepcopy(window.edited_draft())
    assert not window.findChild(QPushButton, 'swapGaugePoints').isEnabled()
    assert window.swap_gauge_points() is False and window.edited_draft() == before
    window.fields[('direction',)][0].setText('0, 1, 0'); window._edited()
    window.client.release = True; settle(app, window)
    assert window.edited_draft()['direction'] == [0,1,0] and window.local_dirty
    assert not any(call[1] in ('post.apply', 'post.mapping_validate') for call in window.client.calls)


def test_gauge_review_keeps_scalar_direction_reference_and_actual_clock_visible(app):
    from apps.research.post_measurement_dialog import MeasurementDialog
    from test_post_gauge_handoff import snapshot
    measured = snapshot()
    measured['origin']['object_ref'] = 'Agauge'
    measured['summary'].update(time=.5, time_units='s', time_origin='analysis_start')
    dialog = MeasurementDialog(measured)
    try:
        text = dialog.summary.text()
        assert '3 → 7' in text and '[1, 0, 0]' in text and '0.5 [s]' in text and 'analysis_start' in text
        assert dialog.summary.wordWrap()
        assert dialog.value_column.count() == 2  # Placeholder and derived scalar; original U stays auxiliary.
        assert dialog.fields['component_label'].isReadOnly() and dialog.fields['location'].isReadOnly()
        dialog.value_column.setCurrentIndex(1)
        dialog.axis_column.setCurrentIndex(dialog.axis_column.findData({'kind':'coordinate','component':0}))
        assert dialog.selection['measure'] == 'projected_relative_displacement'
        assert dialog.projected['rows'][0]['value'] == .5
        app.processEvents()  # Drain the existing Matplotlib idle draw before closing its widget.
    finally:
        dialog.close()


def test_desktop_commands_keep_native_selection_activation_and_unconfirmed_foreground_distinct(app, window, monkeypatch):
    prepare(window, monkeypatch)
    window.document['capabilities'] = ['document.activate']
    window.client.document['capabilities'] = ['document.activate']
    original = window.client._execute
    def activate(command):
        payload = original(command)
        return {'status': 'NOT_PERFORMED', 'foreground_confirmed': False} if command['operation'] == 'document.activate' else payload
    monkeypatch.setattr(window.client, '_execute', activate)
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    window.show(); window.activateWindow(); app.processEvents()
    QTest.keyClick(window, Qt.Key.Key_F4)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        app.processEvents(); time.sleep(.005)
        if len(window.client.calls) == 2 and window._pending is None and not window._busy: break
    assert [call[1] for call in window.client.calls] == ['post.source_select', 'document.activate']
    assert window.client.calls[0][2]['source_ref'] == 'Sfirst'
    assert 'Windows' in window.message.text() and '작업 표시줄' in window.message.text()
    assert not any('capture' in call[1] for call in window.client.calls)
    assert window.native_action.shortcut().toString() == 'F4'
    assert not window.native_action.icon().isNull()
    assert [a.text() for a in window.menuBar().actions()] == ['파일(&F)', '편집(&E)', '분석(&A)', '결과(&R)', '보기(&V)']


def test_settings_keep_undecided_conditions_visible_and_no_implicit_direction(app, window):
    assert window.new_gauge()
    recipe = window.edited_draft()
    assert recipe['direction'] == [] and not recipe.get('units') and not recipe.get('basis')
    assert '미결정' in window.gauge_conditions.text() and '응답 단위' in window.gauge_conditions.text()
    assert '두 개 선택 필요' in window.gauge_points.text()
    assert not window.findChild(QPushButton, 'swapGaugePoints').isHidden()
    before = deepcopy(recipe)
    window.findChild(__import__('PySide6.QtWidgets', fromlist=['QToolButton']).QToolButton, 'gaugeConditionsToggle').click()
    assert window.edited_draft() == before
    assert window.new_gauge() is False  # Existing unsaved draft is still protected.


def test_preview_action_reads_only_matching_preview_and_stale_plot_keeps_its_basis(app, window, monkeypatch):
    prepare(window, monkeypatch)
    assert window.preview_result() is not False
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        app.processEvents(); time.sleep(.005)
        if window._sample_basis is not None and window._pending is None and not window._busy: break
    assert [call[1] for call in window.client.calls] == ['post.measurement_edit', 'post.mapping_validate', 'post.sample']
    assert window.client.calls[-1][2]['preview'] is True
    window.apply_action.trigger()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        app.processEvents(); time.sleep(.005)
        if window._sample_basis and window._sample_basis['preview'] is False and window._pending is None and not window._busy: break
    assert [call[1] for call in window.client.calls][-2:] == ['post.apply', 'post.sample']
    assert window.client.calls[-1][2]['preview'] is False
    basis = deepcopy(window._sample_basis)
    window.fields[('direction',)][0].setText('0, 1, 0'); window._edited()
    assert window._sample_basis == basis and '이전 조회' in window.sample_context.text()
    assert not window.apply_action.isEnabled()


def test_real_scalar_plot_does_not_show_auxiliary_vectors_or_invalid_zero(app):
    from apps.research.post_result_plot import ResultPlot
    plot = ResultPlot()
    try:
        plot.set_samples({'rows': [
            {'values': {'GaugeRelativeDisplacement': .5, 'U': [2,3,4]}, 'validity': {'GaugeRelativeDisplacement':'valid'}},
            {'values': {'GaugeRelativeDisplacement': 0, 'U': [2,3,4]}, 'validity': {'GaugeRelativeDisplacement':'invalid'}}]}, draft())
        assert plot.column.count() == 1 and plot.column.currentText() == '두 점 상대변위'
        ys = plot.figure.axes[0].lines[0].get_ydata()
        assert ys[0] == .5 and __import__('math').isnan(ys[1])
        assert '무효 1행' in plot.figure.axes[0].get_title()
    finally:
        plot.close()


def test_gauge_history_capture_preserves_explicit_range_and_exact_reference(app, window, monkeypatch):
    window._kind = 'measurement'
    window._draft = {**draft(), 'measurement':'gauge_time', 'time_range':[.5,1], 'reference_time':.5}
    window._draft.pop('time')
    window._object_ref = None; window._populate_editor()
    original = window.client._execute
    def captured(command):
        payload = original(command)
        if command['operation'] == 'post.measurement_capture':
            assert command['arguments'] == {'source_ref':'Sfirst','array':'U','measurement':'gauge_time','reference_time':.5}
            payload['draft'].update(measurement='gauge_time', point_indices=[0,1], point1=[0,0,0],point2=[1,0,0],
                time_range=[0,1], reference_time=.5)
            window.client.document['state']['analysis']['objects'][-1].update(deepcopy(payload))
        return payload
    monkeypatch.setattr(window.client, '_execute', captured)
    assert window.capture_selection()
    settle(app, window)
    assert window.edited_draft()['time_range'] == [.5,1] and window.edited_draft()['reference_time'] == .5
    assert 'time' not in window.edited_draft() and window.swap_gauge_points()


@pytest.mark.parametrize('kind', ['surface_average', 'surface_time'])
def test_surface_face_pages_keep_explicit_selection_cancel_and_no_apply(app, window, monkeypatch, kind):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog, QTreeWidget, QDialogButtonBox
    assert window.new_measurement_type(kind)
    source_field = window.fields[('source_ref',)][0]
    source_field.setCurrentIndex(source_field.findData('Sfirst'))
    window.fields[('array',)][0].setCurrentText('U')
    before = deepcopy(window.edited_draft())
    faces = [{'cell_index':i, 'face_index':0, 'point_indices':[i,i+1,i+2],
              'coordinates':[[0,0,0],[1,0,0],[0,1,0]], 'original_point_ids':{}} for i in (0,200)]
    original = window.client._execute
    def captured(command):
        if command['operation'] != 'post.measurement_capture': return original(command)
        args = command['arguments']; offset = args['offset']
        assert args['measurement'] == kind and args['limit'] == 200
        window.client.document['generation'] += 1
        return {'reference_time':None if kind == 'surface_average' else .5, 'geometry':'fixed_reference',
            'faces':[faces[0 if offset == 0 else 1]], 'total':201, 'offset':offset, 'limit':200, 'has_more':offset == 0}
    monkeypatch.setattr(window.client, '_execute', captured)
    assert window.capture_surface_faces(); settle(app, window)
    dialog = next(d for d in window.findChildren(QDialog) if d.isVisible())
    dialog.reject(); app.processEvents()
    assert window.edited_draft() == before
    assert window.capture_surface_faces(); settle(app, window)
    dialog = next(d for d in window.findChildren(QDialog) if d.isVisible())
    tree = dialog.findChild(QTreeWidget)
    tree.topLevelItem(0).setCheckState(0, Qt.CheckState.Checked)
    next(button for button in dialog.findChildren(QPushButton) if button.text() == '다음 면').click()
    settle(app, window)
    tree.topLevelItem(0).setCheckState(0, Qt.CheckState.Checked)
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
    app.processEvents()
    assert window.edited_draft()['surface_faces'] == faces
    assert window.edited_draft()['geometry'] == 'fixed_reference'
    assert window.local_dirty and window._object_ref is None
    assert [call[1] for call in window.client.calls] == ['post.measurement_capture'] * 3


def test_native_table_plot_selection_uses_exact_row_revision_and_rejects_old_revision(app, window, monkeypatch):
    recipe = {**draft(), 'measurement':'surface_time', 'time_range':[0,1], 'reference_time':0}
    obj = {'id':'Asurface','kind':'measurement','title':'면 평균 이력','draft':recipe,
           'history':[{'id':'H1','recipe':recipe,'summary':{}}],'position':0,'preview':None}
    window.client.document['state']['analysis']['objects'] = [obj]
    window._object_ref = 'Asurface'; window._tree_selection = ('object','Asurface')
    window._show_document(window.client.document_read('Dpost'))
    window._show_samples({'object_ref':'Asurface','revision':'H1','preview':False,
        'summary':{'measurement':'surface_time','units':'mm','time_units':'s'},
        'rows':[{'block':[],'row':i,'values':{'Time':i,'SurfaceAreaAverage':8+i,'vtkValidMask':1}} for i in (0,1)]})
    original = window.client._execute
    def sampled(command):
        payload = original(command)
        if command['operation'] == 'post.sample':
            return {'object_ref':'Asurface','revision':'H1','rows':[window._samples['rows'][1]]}
        return payload
    monkeypatch.setattr(window.client, '_execute', sampled)
    window.result_plot.rowSelected.emit(1); settle(app, window)
    args = window.client.calls[-1][2]
    assert args == {'object_ref':'Asurface','preview':False,'row_index':1,'expected_revision':'H1'}
    assert len(window._samples['rows']) == 2 and window._sample_basis['revision'] == 'H1'
    window.document['state']['analysis']['objects'][0]['history'][0]['id'] = 'Hchanged'
    count = len(window.client.calls)
    assert window.select_curve_row(0, window._sample_basis) is False
    assert len(window.client.calls) == count


def test_related_modes_preserve_exact_selection_and_vector_mean_requires_explicit_basis(app, window):
    window._kind = 'measurement'
    window._draft = {**draft(), 'original_point_ids':{'NativeNodeId':[100,101]}}
    window._populate_editor()
    window._measurement_changed('gauge_time')
    assert window.edited_draft()['original_point_ids'] == {'NativeNodeId':[100,101]}
    face = {'cell_index':3,'face_index':1,'point_indices':[4,7,8],
            'coordinates':[[0,0,0],[1,0,0],[0,1,0]],'original_point_ids':{}}
    window._draft = {**draft(), 'measurement':'surface_time', 'surface_faces':[face],
        'component':0,'basis':None,'geometry':'fixed_reference','time_range':[0,1],'reference_time':0}
    window._populate_editor()
    assert '방향의 기준' in window.surface_conditions.text()
    window._measurement_changed('surface_average')
    assert window.edited_draft()['surface_faces'] == [face] and window.edited_draft()['basis'] is None
    assert 'time_range' not in window.edited_draft()
    assert not window.client.calls


def test_source_context_command_targets_clicked_source_and_retains_dirty_editor(app, window):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QMenu
    window._kind = 'measurement'; window._draft = draft(); window._populate_editor()
    window.local_dirty = True
    retained = deepcopy(window.edited_draft())
    item = window.tree.topLevelItem(0).child(1)
    window.show(); app.processEvents()
    errors = []
    def choose():
        menu = app.activePopupWidget()
        try:
            assert isinstance(menu, QMenu)
            assert menu.actions()[0] is window.native_action
            assert not window.new_gauge_action.isEnabled()
            menu.actions()[0].trigger()
        except BaseException as error:
            errors.append(error)
        finally:
            if menu is not None: menu.close()
    QTimer.singleShot(0, choose)
    window._tree_menu(window.tree.visualItemRect(item).center())
    if errors: raise errors[0]
    settle(app, window)
    assert window.client.calls[-1][2]['source_ref'] == 'Ssecond'
    assert window.edited_draft() == retained and window.local_dirty
    assert window.return_editor.isVisible()


def _surface_ui_field(window, kind, array, names=None):
    for document in (window.document, window.client.document):
        for source in document['state']['analysis']['sources']:
            source['metadata']['arrays'] = [{'name':'tensor','association':'POINTS','components':6,
                **({'component_names':names} if names else {})}, {'name':'U','association':'POINTS','components':3}]
    assert window.new_measurement_type(kind)
    source = window.fields[('source_ref',)][0]
    source.setCurrentIndex(source.findData('Sfirst'))
    window.fields[('array',)][0].setCurrentText(array)
    window._source_field_changed(('array',))


@pytest.mark.parametrize('kind', ['surface_average','surface_time'])
def test_new_scalar_surface_recipe_has_no_hidden_direction(window, kind):
    _surface_ui_field(window, kind, 'tensor')
    assert window.edited_draft().get('component') is None
    assert window.edited_draft()['direction'] is None
    assert not window.client.calls


def test_surface_component_change_clears_inapplicable_projection_direction(window):
    _surface_ui_field(window, 'surface_average', 'U')
    combo = window.fields[('component',)][0]
    combo.setCurrentIndex(combo.findData('projection'))
    window.fields[('direction',)][0].setText('1, 0, 0'); window._edited()
    assert window.edited_draft()['direction'] == [1,0,0]
    combo = window.fields[('component',)][0]
    combo.setCurrentIndex(combo.findData(1))
    assert window.edited_draft()['component'] == 1 and window.edited_draft()['direction'] is None
    combo = window.fields[('component',)][0]
    combo.setCurrentIndex(combo.findData(None))
    assert window.edited_draft()['component'] is None and window.edited_draft()['direction'] is None


def test_surface_tensor_components_keep_original_names_and_all_native_indices(window):
    names = ['n0','n1','n2','native shear C','native shear A','native shear B']
    _surface_ui_field(window, 'surface_time', 'tensor', names)
    combo = window.fields[('component',)][0]
    assert [combo.itemData(i) for i in range(combo.count())] == [None,0,1,2,3,4,5]
    assert [combo.itemText(i) for i in range(1,7)] == names
    combo.setCurrentIndex(combo.findData(5))
    assert window.edited_draft()['component'] == 5 and window.edited_draft()['direction'] is None


def test_nonsurface_component_change_does_not_add_surface_direction(window):
    from apps.research.post_window import defaults
    window._kind = 'filter'; window._draft = defaults('filter'); window._populate_editor()
    field = window._form_field(None, 'component', 1, ('component',))
    serial = window._edit_serial
    field.setCurrentIndex(field.findData(None))
    assert window._edit_serial > serial and window.local_dirty
    assert 'direction' not in window.edited_draft() and field.currentIndex() == 0


def test_surface_association_commit_uses_the_same_name_exact_location_descriptor(window):
    _surface_ui_field(window, 'surface_average', 'U')
    window.document['state']['analysis']['sources'][0]['metadata']['arrays'].append(
        {'name':'U','association':'CELLS','components':6})
    assert window.fields[('component',)][0].findData('projection') >= 0
    association = window.fields[('association',)][0]
    association.setCurrentText('CELLS'); association.activated.emit(association.currentIndex())
    combo = window.fields[('component',)][0]
    assert [combo.itemData(i) for i in range(combo.count())] == [None,0,1,2,3,4,5]


@pytest.mark.parametrize('kind', ['surface_average', 'surface_time', 'gauge_time'])
def test_deleted_comparison_editor_is_not_used_for_measurement_samples(app, window, kind):
    from PySide6.QtCore import QCoreApplication, QEvent
    from shiboken6 import isValid
    previous = window.comparison_editor
    assert isValid(previous) and previous.checks_button is not None
    assert window.new_measurement_type(kind)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    assert not isValid(previous)
    assert window.comparison_editor is None
    key = 'SurfaceAreaAverage' if kind.startswith('surface') else 'GaugeRelativeDisplacement'
    window._show_samples({'revision': 'Vretained', 'summary': {'measurement': kind, 'units': 'mm'},
        'rows': [{'block': [], 'row': 0, 'values': {key: 2., 'vtkValidMask': 1}},
                 {'block': [], 'row': 1, 'values': {key: None, 'vtkValidMask': 0}}]})
    assert window.samples.rowCount() == 2
    assert window._sample_basis['draft']['measurement'] == kind
    assert window._samples['rows'][1]['values']['vtkValidMask'] == 0
    assert window.result_plot is not None and not window.client.calls


@pytest.mark.parametrize('version', [2, 3])
def test_current_comparison_editor_keeps_its_recipe_and_result_controls(app, window, version):
    from apps.research.post_comparison_editor import default_recipe as field_recipe
    from apps.research.post_curve_editor import default_recipe as curve_recipe
    recipe = field_recipe() if version == 2 else curve_recipe()
    window._kind = 'comparison'; window._draft = deepcopy(recipe)
    window._populate_editor()
    app.processEvents()
    assert window.edited_draft() == recipe
    if version == 2:
        summary = {'field_transfer': True, 'recipe': deepcopy(recipe)}
        window._show_samples({'summary': summary, 'rows': []})
        assert window.comparison_editor.result_summary == summary
        assert window.comparison_editor.checks_button.isEnabled()
    else:
        window._show_samples({'semantics': 'retained_curve_comparison', 'summary': {}, 'rows': []})
        assert window.edited_draft() == recipe
