"""Actual VTK stages under the existing ParaView import adapter, not a GUI run."""
from copy import deepcopy
from pathlib import Path
import importlib.util,sys
import numpy as np
import pytest
vtk=pytest.importorskip('vtk')
from vtk.util.numpy_support import vtk_to_numpy
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'tests/test_post_analysis.py').is_file())
sys.path.insert(0,str(ROOT/'tests'))
from test_post_analysis import analysis,grid
from test_post_comparison_native import native,add,run,tetra
from test_post_stress_measures import c,side,recipe


@pytest.fixture
def stages(native):
    path=Path(__file__).resolve().parents[1]/'apps/desktop_post/comparison_native.py'
    spec=importlib.util.spec_from_file_location('apps.desktop_post.comparison_stress_stages',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.physical=c
    return module


def prep_side(association='POINTS'):
    s=side('pk1',association);s.update(_stress_target='cauchy',_stress_units='MPa')
    return s


def test_original_cell_stresses_convert_before_native_incident_cell_projection(stages):
    source=grid(np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1],[0,0,-1.]]),[(0,1,2,3),(0,2,1,4)],np.zeros(5))
    P=np.diag([0.,1,0]).reshape(-1)
    add(source.GetCellData(),'stress',[P,P]);add(source.GetCellData(),'F',[np.eye(3).reshape(-1),np.diag([3.,1,1]).reshape(-1)])
    before=vtk_to_numpy(source.GetCellData().GetArray('stress')).copy()
    prepared=run(stages,'prepare',[source],prep_side('CELLS'))
    actual=vtk_to_numpy(prepared.GetPointData().GetArray(stages.RAW))
    np.testing.assert_allclose(actual[:3,4],2/3,rtol=0,atol=1e-14)
    assert not np.isclose(actual[0,4],.5)
    np.testing.assert_equal(vtk_to_numpy(prepared.GetPointData().GetArray(stages.ORIGINAL))[:,4],1.)
    np.testing.assert_equal(vtk_to_numpy(source.GetCellData().GetArray('stress')),before)


def test_native_endpoint_conversion_precedes_time_interpolation_and_preserves_raw(stages):
    source=tetra();P=np.diag([0.,1,0]).reshape(-1)
    add(source.GetPointData(),'stress',np.tile(P,(4,1)));add(source.GetPointData(),'F',np.tile(np.eye(3).reshape(-1),(4,1)))
    settings=prep_side();left=run(stages,'prepare',[source],settings)
    add(source.GetPointData(),'F',np.tile(np.diag([3.,1,1]).reshape(-1),(4,1)))
    right=run(stages,'prepare',[source],settings)
    blended=run(stages,'temporal',[left,right],{'weight':.5})
    np.testing.assert_allclose(vtk_to_numpy(blended.GetPointData().GetArray(stages.RAW))[:,4],2/3,rtol=0,atol=1e-14)
    r=recipe();r['selection']='yy';r['b']=side('pk1')
    transformed=run(stages,'transform',[blended],{'side':settings,'recipe':r,'response_rotation':c.IDENTITY,'geometry_rotation':c.IDENTITY,'translation':[0,0,0]})
    np.testing.assert_allclose(vtk_to_numpy(transformed.GetPointData().GetArray(stages.VALUE))[:,4],2/3,rtol=0,atol=1e-14)
    np.testing.assert_equal(vtk_to_numpy(transformed.GetPointData().GetArray(stages.ORIGINAL))[:,4],1.)


def test_f_mask_keeps_original_values_and_missing_f_has_recoverable_error(stages):
    source=tetra();P=np.eye(3).reshape(-1)
    add(source.GetPointData(),'stress',np.tile(P,(4,1)));add(source.GetPointData(),'F',np.tile(P,(4,1)))
    add(source.GetPointData(),'F_quality',[1,0,1,1])
    s=prep_side();s['deformation_gradient']['validity_masks']=['F_quality']
    output=run(stages,'prepare',[source],s)
    assert np.isnan(vtk_to_numpy(output.GetPointData().GetArray(stages.RAW))[1]).all()
    np.testing.assert_equal(vtk_to_numpy(output.GetPointData().GetArray(stages.ORIGINAL))[1],P)
    source.GetPointData().RemoveArray('F')
    with pytest.raises(ValueError,match='F'):run(stages,'prepare',[source],s)
    np.testing.assert_equal(vtk_to_numpy(source.GetPointData().GetArray('stress')),np.tile(P,(4,1)))
    add(source.GetPointData(),'F',np.tile(P,(4,1)))
    repaired=run(stages,'prepare',[source],s)
    assert np.isfinite(vtk_to_numpy(repaired.GetPointData().GetArray(stages.RAW))[[0,2,3]]).all()


def test_original_and_common_stress_are_separate_native_arrays(stages):
    source=tetra();F=np.diag([2.,1,1]);P=np.diag([6.,5,7]);sigma=np.diag([6.,2.5,3.5])
    add(source.GetPointData(),'stress',np.tile(P.reshape(-1),(4,1)));add(source.GetPointData(),'F',np.tile(F.reshape(-1),(4,1)))
    bside=prep_side();r=recipe();r['selection']='yy'
    bpre=run(stages,'prepare',[source],bside)
    b=run(stages,'transform',[bpre],{'side':bside,'recipe':r,'response_rotation':c.IDENTITY,'geometry_rotation':c.IDENTITY,'translation':[0,0,0]})
    add(source.GetPointData(),'a_stress',np.tile(sigma.reshape(-1),(4,1)))
    aside=side('cauchy');aside.update(array='a_stress',_stress_target='cauchy',_stress_units='MPa');r['a']=aside
    apre=run(stages,'prepare',[source],aside)
    a=run(stages,'transform',[apre],{'side':aside,'recipe':r,'response_rotation':c.IDENTITY,'geometry_rotation':c.IDENTITY,'translation':[0,0,0]})
    result=run(stages,'difference',[a,b,source],dict(r,observable_version=1))
    attrs=result.GetPointData()
    np.testing.assert_equal(vtk_to_numpy(attrs.GetArray('B_source_sampled')),5.)
    np.testing.assert_equal(vtk_to_numpy(attrs.GetArray('B_at_A')),2.5)
    np.testing.assert_equal(vtk_to_numpy(attrs.GetArray('B_minus_A')),0.)
