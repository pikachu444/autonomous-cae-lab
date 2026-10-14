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
    r['a']['layout']['scalar_semantics'] = 'component'
    r['b']['layout']['scalar_semantics'] = 'component'
    rows = native.declarations(r)['arrays']
    assert all(row['layout']['scalar_semantics'] == 'component' for row in rows)
    assert [row['validity_masks'] for row in rows] == [['A_finite'],['B_finite'],['comparison_valid']]
