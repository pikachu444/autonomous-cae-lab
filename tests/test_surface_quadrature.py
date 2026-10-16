import numpy as np
import pytest
pytest.importorskip('vtkmodules.vtkCommonDataModel')
from vtkmodules.vtkCommonDataModel import vtkQuadraticTriangle,vtkQuadraticQuad
from caelab.quadratic_surface import shape,derivatives
from apps.desktop_post.surface_quadrature import integrate


def coordinates(kind,height=0.):
    cell=vtkQuadraticTriangle() if kind==6 else vtkQuadraticQuad()
    points=np.array(cell.GetParametricCoords()).reshape(-1,3)
    points[3 if kind==6 else 4:,2]=height
    return points


@pytest.mark.parametrize('kind',[6,8])
def test_shape_order_derivatives_and_vtk_agree(kind):
    cell=vtkQuadraticTriangle() if kind==6 else vtkQuadraticQuad()
    points=coordinates(kind)
    for i,(r,s,_) in enumerate(points):np.testing.assert_allclose(shape(kind,r,s),np.eye(kind)[i],atol=1e-15,rtol=0)
    for r,s in ((.2,.3),(.1,.7)):
        weights=[0.]*kind;deriv=[0.]*(2*kind)
        cell.InterpolateFunctions([r,s,0],weights);cell.InterpolateDerivs([r,s,0],deriv)
        np.testing.assert_allclose(shape(kind,r,s),weights,atol=1e-15,rtol=0)
        np.testing.assert_allclose(derivatives(kind,r,s),np.array(deriv).reshape(2,kind),atol=1e-15,rtol=0)
        np.testing.assert_allclose(derivatives(kind,r,s).sum(axis=1),0.,atol=1e-15,rtol=0)


@pytest.mark.parametrize('kind',[6,8])
def test_flat_constant_and_linear_shape_area_mean(kind):
    points=coordinates(kind);field=3+points[:,0]+2*points[:,1]
    value=integrate(points,field);expected_area=.5 if kind==6 else 1.
    assert value['area']==pytest.approx(expected_area,abs=2e-14)
    assert value['value']==pytest.approx(4. if kind==6 else 4.5,abs=2e-14)
    constant=integrate(points,7.)
    assert constant['value']==pytest.approx(7.,abs=2e-14)
    assert constant['integral']==pytest.approx(7*expected_area,abs=2e-14)


def test_curved_patch_independent_analytic_metric_not_corner_area():
    from scipy.integrate import dblquad
    h=.2;points=coordinates(6,h)
    value=integrate(points,np.full(6,2.))
    metric=lambda s,r:np.sqrt(1+(4*h*(1-2*r-s))**2+(4*h*(1-r-2*s))**2)
    actual,error=dblquad(metric,0,1,lambda r:0,lambda r:1-r,epsabs=1e-12,epsrel=1e-12)
    assert value['area']>.5 and value['area_difference']>0
    assert abs(value['reference_area']-actual)<abs(value['area']-actual)
    assert abs(value['reference_area']-actual)<2e-5
    assert value['value']==pytest.approx(2.,abs=1e-14)
    assert value['geometry_checks']['status']=='CERTIFIED_GRAPH_PATCH'


@pytest.mark.parametrize('damage',['missing','nonfinite','duplicate','midside_order','field'])
def test_bad_face_is_not_linearized_or_zero_filled(damage):
    points=coordinates(6);field=np.ones(6)
    if damage=='missing':points=points[:3]
    elif damage=='nonfinite':points[3,2]=np.nan
    elif damage=='duplicate':points[1]=points[0]
    elif damage=='midside_order':points[[3,4]]=points[[4,3]]
    elif damage=='field':field[3]=np.nan
    with pytest.raises(ValueError):integrate(points,field)


def test_3d_rigid_rotation_and_origin_do_not_change_area():
    points=coordinates(8,.3);field=2+points[:,0]
    a=integrate(points,field)
    rotation=np.array([[0.,0.,1.],[1,0,0],[0,1,0]])
    b=integrate(points@rotation.T+[100.,200.,300.],field)
    assert b['area']==pytest.approx(a['area'],abs=1e-12)
    assert b['value']==pytest.approx(a['value'],abs=1e-12)


@pytest.mark.parametrize('kind',[6,8])
def test_nodal_quadratic_field_uses_full_shape(kind):
    points=coordinates(kind);value=integrate(points,points[:,0]**2)
    assert value['value']==pytest.approx(1/6 if kind==6 else 1/3,abs=2e-14)


def test_uncertified_graph_is_rejected_without_rule_or_tolerance_retry():
    points=coordinates(8);points[4,0]=3.
    with pytest.raises(ValueError,match='전 영역'):integrate(points,np.ones(8))
