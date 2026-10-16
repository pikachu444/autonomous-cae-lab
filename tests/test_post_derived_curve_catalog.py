"""Saved derived history admission with actual VTK tables and proxy transport."""
from copy import deepcopy

import pytest
vtk = pytest.importorskip('vtk')

from caelab.post_comparison import UNKNOWN_OBSERVABLE, observable_value
from caelab.post_observation import file_pin
from test_post_curve_origin_native import native
from test_post_r3_repairs import post_modules


def derived_history(native, kind):
    n = native
    obj = n.measurement('Aderived', [0., .07, .2], [2., 5., 7.])
    record = obj['history'][0]
    array = 'SurfaceAreaAverage' if kind == 'surface_time' else 'GaugeRelativeDisplacement'
    recipe = record['recipe']
    recipe.update(measurement=kind, component=2, surface_faces=[{'point_indices': list(range(6))}])
    summary = record['summary']
    summary.update(measurement=kind, input_array='F', array=array, units='MPa', quantity='stress',
        measure='cauchy' if kind == 'surface_time' else 'projected_relative_displacement',
        geometry='fixed_reference', time_values=[0., .07, .2],
        reduction='native_parametric_quadratic_area_weighted_mean',
        field_interpolation='native_quadratic_shape',
        quadrature={'version': 1, 'error_bound': 'NOT_ESTABLISHED', 'convergence': 'UNKNOWN'},
        selected_declaration={'layout': {'kind': 'vector', 'components': ['z', 'x', 'y']},
            'observable': observable_value('vector', 'z')})
    obj['draft'] = deepcopy(recipe)
    table = n.bundles[record['id']]['source'].data
    table.RemoveColumnByName('F')
    for name, values in ((array, [2., 5., 7.]), ('vtkValidMask', [1., 0., 1.]),
                         ('SurfaceIntegral', [4., 10., 14.]), ('load_parameter', [1., 2., 3.])):
        column = vtk.vtkDoubleArray(); column.SetName(name)
        for value in values: column.InsertNextValue(value)
        table.AddColumn(column)
    writer = vtk.vtkXMLTableWriter()
    writer.SetFileName(record['result_file']); writer.SetInputData(table)
    assert writer.Write() == 1
    pin = file_pin(record['result_file'])
    record.update(result_files=[pin], result_sha256=pin['sha256'])
    n.save()
    return obj, record, table


@pytest.mark.parametrize('kind', ['surface_time', 'gauge_time'])
def test_saved_derived_history_catalog_preserves_scalar_meaning_time_and_mask(native, kind):
    n = native
    obj, record, _ = derived_history(n, kind)
    before = deepcopy(obj)
    catalog = n.curves.catalog(n.ws)
    assert not catalog['issues']
    options = [row for row in catalog['curves'] if row['source_ref'] == obj['id']]
    assert len(options) == 1
    option = options[0]
    assert option['column'] == record['summary']['array'] and option['axis_column'] == 'Time'
    assert option['declaration']['layout'] == {'kind': 'scalar', 'components': ['scalar']}
    assert option['declaration']['measure'] == record['summary']['measure']
    assert option['declaration']['observable'] == (observable_value('vector', 'y')
        if kind == 'surface_time' else UNKNOWN_OBSERVABLE)
    assert option['declaration']['reduction'] == ('avg' if kind == 'surface_time' else 'none')
    curve = n.curves.selected(n.ws, option)
    assert [row['x'] for row in curve['rows']] == [0., .07, .2]
    assert [row['raw_y'] for row in curve['rows']] == [2., 5., 7.]
    assert [row['quality'] for row in curve['rows']] == [True, False, True]
    assert curve['rows'][1]['quality_reason'] == 'native_mask'
    assert curve['origin']['recipe'] == record['recipe'] and obj == before


@pytest.mark.parametrize('fault', ['clock', 'mask', 'error_bound'])
def test_derived_curve_rejects_changed_clock_missing_mask_and_false_accuracy(native, fault):
    n = native
    obj, record, table = derived_history(n, 'surface_time')
    if fault == 'clock': record['summary']['time_values'] = [0., .1, .2]
    elif fault == 'mask': table.RemoveColumnByName('vtkValidMask')
    else: record['summary']['quadrature']['error_bound'] = 'CERTIFIED'
    n.save()
    with pytest.raises(ValueError): n.curves.options(n.ws, obj['id'])


@pytest.mark.parametrize('kind', ['surface_average', 'point', 'path'])
def test_nonhistory_measurements_remain_outside_curve_catalog(native, kind):
    n = native
    obj, record, _ = derived_history(n, kind)
    assert obj['id'] not in [row['source_ref'] for row in n.curves.catalog(n.ws)['curves']]
    with pytest.raises(ValueError): n.curves.options(n.ws, obj['id'])
