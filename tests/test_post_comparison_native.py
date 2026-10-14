"""Actual VTK stages under a narrow import adapter, not a ParaView session."""
import importlib
import sys
import numpy as np
import pytest
vtk = pytest.importorskip('vtk')
from vtk.util import numpy_support
from test_post_analysis import analysis, grid
from test_post_comparison_physics import recipe


@pytest.fixture
def native(analysis, monkeypatch):
    module, adapter = analysis
    monkeypatch.setattr(sys.modules['paraview'], 'vtk', vtk, raising=False)
    monkeypatch.setitem(sys.modules, 'paraview.vtk.util.numpy_support', numpy_support)
    monkeypatch.delitem(sys.modules, 'apps.desktop_post.comparison_native', raising=False)
    result = importlib.import_module('apps.desktop_post.comparison_native')
    yield result
    sys.modules.pop('apps.desktop_post.comparison_native', None)


def add(attrs, name, values):
    arr = numpy_support.numpy_to_vtk(np.asarray(values), deep=True); arr.SetName(name); attrs.AddArray(arr)


def run(native, stage, inputs, settings):
    output = vtk.vtkUnstructuredGrid()
    native.execute(inputs, output, stage, settings)
    return output


def tetra():
    return grid(np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1.]]), [(0,1,2,3)], np.array([2.,2.,2.,2.]), ids=[10,11,12,13])


def test_quality_mask_preserves_raw_but_blocks_difference(native):
    original=tetra(); add(original.GetPointData(),'vtkValidPointMask',[1,0,1,1])
    r=recipe()
    for side in ('a','b'): r[side]['array']='response'
    prepared=run(native,'prepare',[original],r['a'])
    assert numpy_support.vtk_to_numpy(prepared.GetPointData().GetArray(native.ORIGINAL)).tolist()==[2,2,2,2]
    assert np.isnan(numpy_support.vtk_to_numpy(prepared.GetPointData().GetArray(native.RAW))[1])
    transformed=run(native,'transform',[prepared],{'side':r['a'],'recipe':r,
        'response_rotation':r['alignment']['response_rotation'],'geometry_rotation':r['alignment']['geometry_rotation'],'translation':[0,0,0]})
    output=run(native,'difference',[transformed,transformed,original],r)
    assert numpy_support.vtk_to_numpy(output.GetPointData().GetArray('comparison_valid')).tolist()==[1,0,1,1]
    assert numpy_support.vtk_to_numpy(output.GetPointData().GetArray('A_source_value')).tolist()==[2,2,2,2]
    assert numpy_support.vtk_to_numpy(original.GetPointData().GetArray('response')).tolist()==[2,2,2,2]
    assert numpy_support.vtk_to_numpy(output.GetPointData().GetArray('NativeNodeId')).tolist()==[10,11,12,13]


def test_cell_projection_and_invalid_cell_are_native_and_explicit(native):
    source=tetra(); add(source.GetCellData(),'cell_pressure',[6.]); add(source.GetCellData(),'quality',[0])
    side=recipe()['a']; side.update(array='cell_pressure',association='CELLS',
        projection='cell_to_point_equal_incident',validity_masks=['quality'])
    output=run(native,'prepare',[source],side)
    assert np.isnan(numpy_support.vtk_to_numpy(output.GetPointData().GetArray(native.RAW))).all()
    np.testing.assert_equal(numpy_support.vtk_to_numpy(output.GetPointData().GetArray(native.ORIGINAL)),[6.,6.,6.,6.])


def test_temporal_float_interpolation_and_topology_guard(native):
    source=tetra(); side=recipe()['a']; side['array']='response'
    left=run(native,'prepare',[source],side)
    add(source.GetPointData(),'response',[4,4,4,4])
    right=run(native,'prepare',[source],side)
    result=run(native,'temporal',[left,right],{'weight':.25})
    np.testing.assert_equal(numpy_support.vtk_to_numpy(result.GetPointData().GetArray(native.RAW)),[2.5]*4)
    right.GetPoints().SetPoint(1,2,0,0)
    with pytest.raises(ValueError,match='대응'): run(native,'temporal',[left,right],{'weight':.25})



def test_quality_is_applied_before_path_drops_upstream_arrays(native):
    original = tetra()
    add(original.GetPointData(), 'comparison_valid', [1,0,1,1])
    result = run(native, 'quality_only', [original], {'array':'response', 'masks':['comparison_valid']})
    assert np.isnan(numpy_support.vtk_to_numpy(result.GetPointData().GetArray('response'))[1])
    assert numpy_support.vtk_to_numpy(original.GetPointData().GetArray('response'))[1] == 2.
    assert numpy_support.vtk_to_numpy(result.GetPointData().GetArray('NativeNodeId')).tolist() == [10,11,12,13]


def test_malformed_cell_tuple_count_never_becomes_a_projected_value(native):
    source = tetra()
    add(source.GetCellData(), 'bad_cells', [1.,2.])
    side = recipe()['a']
    side.update(array='bad_cells', association='CELLS', projection='cell_to_point_equal_incident')
    with pytest.raises(ValueError, match='개수'):
        run(native, 'prepare', [source], side)


def test_derived_declaration_does_not_turn_scalar_component_into_invariant(native):
    r = recipe()
    for side in ('a', 'b'):
        r[side]['layout']['scalar_semantics'] = 'component'
        r[side]['observable'] = native.physical.observable_value('vector','x')
    rows = native.declarations(r)['arrays']
    assert all(row['layout']['scalar_semantics'] == 'component' for row in rows)
    assert [row['validity_masks'] for row in rows] == [['A_finite'],['B_finite'],['comparison_valid']]


@pytest.mark.parametrize('av,bv,inside,role,expected,reason', [
    (2.,np.nan,True,'A_original',2.,'valid'),
    (np.nan,3.,True,'B_at_A',3.,'valid'),
    (2.,3.,False,'A_original',2.,'valid'),
    (2.,3.,False,'B_at_A',None,'outside_domain'),
    (2.,np.nan,True,'B_minus_A',None,'nonfinite'),
])
def test_selected_array_masks_preserve_independent_original_values(native, av, bv, inside, role, expected, reason):
    from apps.desktop_post import analysis as owner_analysis
    r = recipe()
    a = tetra(); b = tetra()
    for data, value in ((a,av),(b,bv)):
        add(data.GetPointData(),native.VALUE,[value]*4)
        add(data.GetPointData(),native.ORIGINAL,[value]*4)
    add(b.GetPointData(),'vtkValidPointMask',[int(inside)]*4)
    output = run(native,'difference',[a,b,a],dict(r,observable_version=1))
    declarations = native.declarations(r)
    # Narrow native source adapter: the arrays above are actual vtk arrays.
    before_fetch = owner_analysis._fetch
    owner_analysis._fetch = lambda source: source
    try:
        row = owner_analysis.sample_data(output,limit=1,declarations=declarations)['rows'][0]
    finally:
        owner_analysis._fetch = before_fetch
    assert row['values'][role] == expected
    assert row['validity'][role] == reason
    assert row['values']['A_finite'] == int(np.isfinite(av))
    assert row['values']['spatial_valid'] == int(inside)
    assert row['values']['comparison_valid'] == 0
    selected = next(item for item in declarations['arrays'] if item['name']==role)
    side = dict(r['a'], **{k:v for k,v in selected.items() if k!='name'},array=role)
    prepared = run(native,'prepare',[output],side)
    value = numpy_support.vtk_to_numpy(prepared.GetPointData().GetArray(native.RAW))[0]
    assert (np.isnan(value) if expected is None else value == expected)
    measured = run(native,'quality_only',[output],{'array':role,
        'masks':selected['validity_masks'],'validity_policy':'declared_array'})
    assert numpy_support.vtk_to_numpy(measured.GetPointData().GetArray('vtkValidPointMask'))[0] == int(expected is not None)
    # The original joint mask is never changed.
    assert numpy_support.vtk_to_numpy(output.GetPointData().GetArray('vtkValidPointMask'))[0] == 0
    legacy = run(native,'quality_only',[output],{'array':role,'masks':selected['validity_masks']})
    assert numpy_support.vtk_to_numpy(legacy.GetPointData().GetArray('vtkValidPointMask'))[0] == 0


def test_policyless_saved_sample_keeps_legacy_row_shape_and_selection_hash_inputs(native):
    from apps.desktop_post import analysis as owner_analysis
    data=tetra()
    add(data.GetPointData(),'vtkValidPointMask',[0]*4)
    add(data.GetPointData(),'A_finite',[1]*4)
    add(data.GetPointData(),'B_finite',[0]*4)
    add(data.GetPointData(),'spatial_valid',[1]*4)
    before_fetch=owner_analysis._fetch
    owner_analysis._fetch=lambda source:source
    try:
        row=owner_analysis.sample_data(data,limit=1)['rows'][0]
    finally:
        owner_analysis._fetch=before_fetch
    assert row['values']['response'] is None
    assert row['values']['A_finite'] is None
    assert row['values']['B_finite'] is None
    assert row['values']['spatial_valid'] is None
    assert row['values']['vtkValidPointMask']==0
    assert 'raw_values' not in row


def test_legacy_saved_difference_keeps_values_but_new_unidentified_comparison_is_blocked(native):
    r=recipe()
    for side in ('a','b'):
        r[side]['layout']['scalar_semantics']='component'
    a=tetra();b=tetra()
    for data,value in ((a,2.),(b,4.)):
        add(data.GetPointData(),native.VALUE,[value]*4)
        add(data.GetPointData(),native.ORIGINAL,[value]*4)
    output=run(native,'difference',[a,b,a],r)
    np.testing.assert_equal(numpy_support.vtk_to_numpy(output.GetPointData().GetArray('B_minus_A')),[2.]*4)
    with pytest.raises(ValueError,match='미확인'):
        run(native,'difference',[a,b,a],dict(r,observable_version=1))
