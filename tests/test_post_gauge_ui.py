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
    finally:
        dialog.close()
