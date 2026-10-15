"""Real VTK endpoint data; no solver or native proxy execution in these units."""
from copy import deepcopy
import importlib
import sys
from types import SimpleNamespace

import numpy as np
import pytest
vtk = pytest.importorskip('vtk')
from vtk.util.numpy_support import numpy_to_vtk
from test_post_analysis import analysis, grid


@pytest.fixture
def gauge(analysis):
    sys.modules.pop('apps.desktop_post.measurements', None)
    module = importlib.import_module('apps.desktop_post.measurements')
    yield module
    sys.modules.pop('apps.desktop_post.measurements', None)


def recipe():
    return {'measurement': 'gauge', 'array': 'response', 'association': 'POINTS',
        'point_indices': [0, 1], 'point1': [0, 0, 0], 'point2': [1, 0, 0],
        'direction': [1, 0, 0], 'units': 'mm', 'measure': 'displacement',
        'frame': 'lab', 'coordinate_units': 'm', 'coordinate_frame': 'lab',
        'basis': 'fixed_cartesian', 'coordinate_configuration': 'reference'}


def field(first=(2, 3, 4), second=(2, 3, 4)):
    return grid([(0,0,0), (1,0,0), (0,1,0), (0,0,1)], [(0,1,2,3)], [first, second, first, first])


def test_translation_zero_and_signed_relative_displacement(gauge):
    original = recipe(); frozen = deepcopy(original)
    result = gauge._gauge_definition(field(), original)
    assert result['value'] == 0 and result['units'] == 'mm' and result['coordinate_units'] == 'm'
    assert result['original_ids'] == {'NativeNodeId': [0, 1]}
    assert result['point1'] == [0, 0, 0] and original == frozen
    original['direction'] = [-1, 0, 0]
    assert gauge._gauge_definition(field(second=(2.5, 3, 4)), original)['value'] == -.5


def test_large_rotation_is_projected_difference_not_length_change_or_strain(gauge):
    result = gauge._gauge_definition(field((0, 0, 0), (-1, 1, 0)), recipe())
    assert result['value'] == -1
    assert np.linalg.norm(np.array(result['point2']) + result['endpoint_displacements'][1]) == 1


def test_coincident_distinct_original_points_need_no_invented_gauge_length(gauge):
    data = field(second=(4, 3, 4)); data.GetPoints().SetPoint(1, 0, 0, 0)
    draft = recipe(); draft['point2'] = [0, 0, 0]
    assert gauge._gauge_definition(data, draft)['value'] == 2


@pytest.mark.parametrize('changed', [
    {'point_indices': [0]}, {'point_indices': [0, 0]}, {'direction': [2, 0, 0]},
    {'point2': [1.1, 0, 0]}, {'measure': 'strain'}, {'frame': 'other'},
    {'frame': 'UNKNOWN', 'coordinate_frame': 'UNKNOWN'}, {'units': 'MPa'},
    {'basis': 'local'}, {'coordinate_configuration': 'deformed'},
])
def test_unknown_or_changed_definition_is_rejected(gauge, changed):
    with pytest.raises(ValueError):
        gauge._gauge_definition(field(), {**recipe(), **changed})


@pytest.mark.parametrize('fault', ['invalid_first', 'hidden_second', 'nonfinite', 'not_vector'])
def test_finite_but_invalid_or_inactive_endpoint_never_becomes_success(gauge, fault):
    data = field()
    if fault in ('invalid_first', 'hidden_second'):
        values = [0, 1, 1, 1] if fault == 'invalid_first' else [0, 2, 0, 0]
        array = numpy_to_vtk(np.array(values, dtype=np.uint8), deep=True)
        array.SetName('vtkValidPointMask' if fault == 'invalid_first' else 'vtkGhostType')
        data.GetPointData().AddArray(array)
    elif fault == 'nonfinite': data.GetPointData().GetArray('response').SetComponent(0, 0, float('nan'))
    else:
        data.GetPointData().RemoveArray('response')
        array = numpy_to_vtk(np.ones(4), deep=True); array.SetName('response'); data.GetPointData().AddArray(array)
    with pytest.raises(ValueError):
        gauge._gauge_definition(data, recipe())


@pytest.mark.parametrize('fault', ['short_mask', 'nonfinite_mask', 'short_ids', 'nonfinite_ids', 'duplicate_ids', 'changed_capture'])
def test_gauge_mask_and_original_identity_shape_is_not_guessed(gauge, fault):
    data = field(); draft = recipe()
    if fault in ('short_mask', 'nonfinite_mask'):
        values = [1, 1] if fault == 'short_mask' else [float('nan'), 1, 1, 1]
        array = numpy_to_vtk(np.asarray(values), deep=True); array.SetName('vtkValidPointMask')
        data.GetPointData().AddArray(array)
    elif fault == 'changed_capture': draft['original_point_ids'] = {'NativeNodeId': [9, 10]}
    else:
        values = {'short_ids': [0, 1], 'nonfinite_ids': [0, 1, 2, float('nan')], 'duplicate_ids': [0, 1, 1, 3]}[fault]
        data.GetPointData().RemoveArray('NativeNodeId')
        array = numpy_to_vtk(np.asarray(values), deep=True); array.SetName('NativeNodeId')
        data.GetPointData().AddArray(array)
    with pytest.raises(ValueError): gauge._gauge_definition(data, draft)


def test_native_two_point_capture_records_coordinates_and_explicit_index_order(gauge, monkeypatch):
    source = SimpleNamespace(data=field(), UpdatePipeline=lambda: None)
    monkeypatch.setattr(gauge, 'capture_point_selection', lambda source: [1, 0])
    captured = gauge.capture_gauge_points(source)
    assert captured == {'point_indices': [0, 1], 'point1': [0, 0, 0], 'point2': [1, 0, 0],
        'original_point_ids': {'NativeNodeId': [0, 1]}}
    assert gauge._gauge_definition(source.data, {**recipe(), **captured})['value'] == 0
