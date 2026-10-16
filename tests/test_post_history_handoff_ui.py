"""Qt handoff checks with manufactured saved rows; no native transport or solver."""
import os
from copy import deepcopy

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from apps.research.post_measurement_dialog import MeasurementDialog


@pytest.fixture(scope='module')
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance
    instance.processEvents()


def snapshot(kind, *, invalid_middle=False):
    gauge = kind == 'gauge_time'
    static = kind == 'surface_average'
    output = 'GaugeRelativeDisplacement' if gauge else 'SurfaceAreaAverage'
    clock = [0.] if static else [0., .07, .2]
    recipe = {'measurement': kind, 'array': 'U' if gauge else 'Stress',
              'association': 'POINTS', 'coordinate_units': 'mm',
              'point_indices': [0, 1], 'point1': [0., 0., 0.], 'point2': [1., 0., 0.],
              'direction': [1., 0., 0.], 'surface_faces': [{'cell_index': 0}]}
    summary = {'measurement': kind, 'input_array': recipe['array'], 'array': output,
               'measure': 'projected_relative_displacement' if gauge else 'cauchy_stress',
               'frame': 'lab', 'units': 'mm' if gauge else 'MPa', 'coordinate_units': 'mm',
               'component_label': 'projection X' if gauge else 'scalar',
               'location': '{"exact_original_reference": true}', 'time': None,
               'time_values': [] if static else clock, 'time_units': 's', 'axis_values': [0.] if static else clock,
               'geometry': 'fixed_reference', 'reduction': 'native_surface_triangulation_area_weighted_mean'}
    rows = []
    for i, time in enumerate(clock):
        valid = not (invalid_middle and i == 1)
        rows.append({'block': [], 'row': i, 'values': {
            'SampleIndex' if static else 'Time': 0. if static else time,
            output: float(i + 1) if valid else None, 'vtkValidMask': int(valid),
            **({} if gauge else {'SurfaceArea': 4.})}})
    return {'recipe': recipe, 'summary': summary, 'rows': rows,
            'origin': {'object_ref': 'saved-measurement'}}


@pytest.mark.parametrize('kind', ['gauge_time', 'surface_time', 'surface_average'])
def test_generated_measurement_has_exact_axis_and_readonly_definition(app, kind):
    saved = snapshot(kind)
    original = deepcopy(saved)
    dialog = MeasurementDialog(saved)
    try:
        assert dialog.selection is not None, dialog.notice.text()
        assert dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
        assert dialog.value_column.count() == 2  # Placeholder and the measured scalar only.
        assert dialog.axis_column.count() == 2
        assert 'SurfaceArea' not in dialog.value_column.currentText()
        assert dialog.fields['location'].isReadOnly()
        assert 'exact_original_reference' not in dialog.summary.text()
        if kind == 'surface_average':
            assert dialog.selection['axis'] == {'kind': 'array', 'name': 'SampleIndex', 'component': None}
            assert dialog.selection['axis_unit'] == '1'
            assert 'Time' not in saved['rows'][0]['values']
            assert dialog.axes.get_xlabel() == '표본 번호 [1]'
        else:
            assert dialog.selection['axis'] == {'kind': 'array', 'name': 'Time', 'component': None}
            assert dialog.selection['axis_unit'] == 's'
            assert [row['axis'] for row in dialog.projected['rows']] == [0., .07, .2]
            assert dialog.axes.get_xlabel() == '시간 [s]'
        assert saved == original
    finally:
        dialog.close()
        app.processEvents()


def test_invalid_native_frame_stays_visible_and_needs_explicit_exclusion(app):
    dialog = MeasurementDialog(snapshot('gauge_time', invalid_middle=True))
    try:
        button = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
        assert not button.isEnabled()
        assert len(dialog.projected['rows']) == 3
        assert not dialog.projected['rows'][1]['valid']
        dialog.exclude_invalid.setChecked(True)
        assert button.isEnabled()
        assert dialog.projected['invalid_rows'] == [2]
        assert len(dialog.projected['rows']) == 3
        assert not dialog.projected['rows'][1]['valid']
    finally:
        dialog.close()
        app.processEvents()
