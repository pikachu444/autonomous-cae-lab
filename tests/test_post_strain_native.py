"""Actual VTK operations with existing import adapter; no native session."""
import numpy as np
import pytest
from vtk.util.numpy_support import vtk_to_numpy
from test_post_comparison_native import native, add, run, tetra
from test_post_analysis import analysis, grid
from test_post_strain_measures import side


def settings(association='POINTS'):
    value=side('material_hencky',association=association)
    value.update(_strain_target='green_lagrange',_strain_units='1');return value


def test_nonlinear_measure_conversion_precedes_cell_projection_and_time(native):
    source=grid(np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1],[0,0,-1.]]),[(0,1,2,3),(0,2,1,4)],np.zeros(5))
    first=np.zeros(9);second=np.diag([np.log(2.),0,0]).reshape(-1)
    add(source.GetCellData(),'strain',[first,second])
    projected=run(native,'prepare',[source],settings('CELLS'))
    np.testing.assert_allclose(vtk_to_numpy(projected.GetPointData().GetArray(native.RAW))[:3,0],.75,atol=1e-15,rtol=0)
    source=tetra();add(source.GetPointData(),'strain',np.tile(first,(4,1)))
    left=run(native,'prepare',[source],settings())
    add(source.GetPointData(),'strain',np.tile(second,(4,1)))
    right=run(native,'prepare',[source],settings())
    temporal=run(native,'temporal',[left,right],{'weight':.5})
    np.testing.assert_allclose(vtk_to_numpy(temporal.GetPointData().GetArray(native.RAW))[:,0],.75,atol=1e-15,rtol=0)
    np.testing.assert_allclose(vtk_to_numpy(temporal.GetPointData().GetArray(native.ORIGINAL))[:,0],np.log(2)/2,atol=1e-15,rtol=0)
    assert not np.isclose(.75,.5)  # transforming averaged H would incorrectly give .5


def test_f_quality_missing_row_and_original_tuples_are_preserved(native):
    source=tetra();s=side('euler_almansi');s.update(_strain_target='green_lagrange',_strain_units='1')
    add(source.GetPointData(),'strain',np.zeros((4,9)));add(source.GetPointData(),'F',np.tile(np.eye(3).reshape(-1),(4,1)))
    add(source.GetPointData(),'F_quality',[1,0,1,1]);s['deformation_gradient']['validity_masks']=['F_quality']
    output=run(native,'prepare',[source],s)
    assert np.isnan(vtk_to_numpy(output.GetPointData().GetArray(native.RAW))[1]).all()
    np.testing.assert_equal(vtk_to_numpy(output.GetPointData().GetArray(native.ORIGINAL)),np.zeros((4,9)))
    source.GetPointData().RemoveArray('F_quality')
    with pytest.raises(ValueError,match='유효성'):run(native,'prepare',[source],s)


def test_strain_selected_array_spatial_mask_is_not_dropped(native):
    source=tetra();s=settings();s['spatial_mask']='source_spatial'
    add(source.GetPointData(),'strain',np.zeros((4,9)));add(source.GetPointData(),'source_spatial',[1,1,0,1])
    output=run(native,'prepare',[source],s)
    assert np.isnan(vtk_to_numpy(output.GetPointData().GetArray(native.RAW))[2]).all()
    np.testing.assert_equal(vtk_to_numpy(output.GetPointData().GetArray(native.ORIGINAL)),np.zeros((4,9)))
