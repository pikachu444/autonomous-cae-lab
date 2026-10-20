"""Actual displacement geometry checks independent of display Warp settings."""
from copy import deepcopy
import numpy as np
import pytest
vtk=pytest.importorskip('vtk')
from vtk.util.numpy_support import numpy_to_vtk
from test_post_measurement_histories import histories,surface,recipe
from test_post_analysis import analysis
from apps.desktop_post.measurement_geometry_state import reference_plus_displacement,face_normal


def definition():
    return {'mode':'reference_plus_displacement','array':'U','association':'POINTS',
            'units':'mm','frame':'lab','basis':'fixed_cartesian'}


def displace(data,transform):
    x=np.asarray([data.GetPoint(i) for i in range(data.GetNumberOfPoints())])
    a=numpy_to_vtk(transform(x)-x,deep=True);a.SetName('U');data.GetPointData().AddArray(a)


def test_actual_biaxial_stretch_area_and_reference_source_are_preserved(histories):
    data=surface(quad=True);faces=histories.surface_catalog(data);before=deepcopy(faces)
    displace(data,lambda x:x*np.array([2.,3.,1.]))
    current=reference_plus_displacement(data,faces,definition(),coordinate_units='mm',coordinate_frame='lab')
    assert current['valid'] and current['display_scale_used'] is False and faces==before
    assert data.GetPoint(2)==(1.,1.,0.) and current['data'].GetPoint(2)==(2.,3.,0.)
    result=histories.surface_average(current['data'],recipe(histories,current['data']),current['faces'])
    assert result['area']==pytest.approx(6.)
    assert current['normals'][0]['current']['normal']==[0.,0.,1.]


def test_rigid_rotation_can_reverse_global_normal_without_false_fold(histories):
    data=surface(quad=True);faces=histories.surface_catalog(data)
    displace(data,lambda x:x*np.array([1.,-1.,-1.]))
    current=reference_plus_displacement(data,faces,definition(),coordinate_units='mm',coordinate_frame='lab')
    assert current['normals'][0]['current']['normal']==[0.,0.,-1.]
    assert np.linalg.norm(current['normals'][0]['current']['oriented_area_vector'])==pytest.approx(1.)


def test_units_missing_u_nonfinite_and_folded_face(histories):
    data=surface(quad=True);faces=histories.surface_catalog(data)
    with pytest.raises(ValueError,match='missing'):reference_plus_displacement(data,faces,definition(),coordinate_units='mm',coordinate_frame='lab')
    displace(data,lambda x:x+np.array([.001,0.,0.]))
    current=reference_plus_displacement(data,faces,{**definition(),'units':'m'},coordinate_units='mm',coordinate_frame='lab')
    assert current['data'].GetPoint(0)==pytest.approx((1.,0.,0.))
    data.GetPointData().GetArray('U').SetComponent(0,1,float('nan'))
    assert not reference_plus_displacement(data,faces,definition(),coordinate_units='mm',coordinate_frame='lab')['valid']
    with pytest.raises(ValueError):face_normal([[0,0,0],[1,0,0],[0,1,0],[1,1,0]])


def test_current_recipe_uses_displacement_mask_and_keeps_reference_quadrature_distinct(histories):
    data=surface(quad=True);faces=histories.surface_catalog(data)
    displace(data,lambda x:x*np.array([2.,3.,1.]))
    draft={**recipe(histories,data),'geometry':'current','geometry_state':definition(),'surface_faces':faces}
    sample=histories.surface_average(data,draft)
    assert sample['reference_geometry_area']==pytest.approx(1.) and sample['current_geometry_area']==pytest.approx(6.)
    mask=numpy_to_vtk(np.array([1,1,0,1],dtype=np.uint8),deep=True);mask.SetName('U_valid');data.GetPointData().AddArray(mask)
    draft['geometry_state']={**definition(),'validity_masks':['U_valid'],'validity_policy':'declared_array'}
    sample=histories.surface_average(data,draft)
    assert not sample['valid'] and sample['reason']=='actual_displacement_U_valid' and sample['value'] is None


def test_current_geometry_rejects_missing_native_ids_and_changed_reference_coordinates(histories):
    data=surface(quad=True);faces=histories.surface_catalog(data);displace(data,lambda x:x)
    draft={**recipe(histories,data),'geometry':'current','geometry_state':definition(),'surface_faces':faces}
    data.GetPoints().SetPoint(1,1.1,0,0)
    with pytest.raises(ValueError,match='다시 선택|Reference coordinates changed'):
        histories.surface_average(data,draft,faces)
    data=surface(quad=True);faces=histories.surface_catalog(data);displace(data,lambda x:x)
    data.GetPointData().RemoveArray('NativeNodeId');draft['surface_faces']=faces
    with pytest.raises(ValueError,match='complete original native point IDs'):histories.surface_average(data,draft,faces)


@pytest.mark.parametrize('kind',[6,8])
def test_current_quadratic_face_preserves_all_midside_displacements_and_rule_semantics(histories,kind):
    from test_quadratic_surface_native import grid,recipe as quadratic_recipe
    data=grid(kind,height=.2);draft=quadratic_recipe(histories,data)
    before=histories.surface_average(data,draft)
    displace(data,lambda x:2*x)
    current=histories.surface_average(data,{**draft,'geometry':'current','geometry_state':definition()})
    assert current['area']==pytest.approx(4*before['area'],rel=1e-12)
    assert current['reference_geometry_area']==before['area']
    assert current['area_difference']==pytest.approx(4*before['area_difference'],abs=1e-13)
    assert current['quadrature']['error_bound']=='NOT_ESTABLISHED'
    assert current['quadrature']['convergence']=='UNKNOWN'
    data.GetPointData().GetArray('U').SetComponent(kind-1,0,float('nan'))
    assert not histories.surface_average(data,{**draft,'geometry':'current','geometry_state':definition()})['valid']


@pytest.mark.parametrize('valid',[True,False])
def test_single_current_native_table_projects_its_saved_actual_geometry(histories,monkeypatch,valid):
    from types import SimpleNamespace
    from test_post_measurement_blocks import native_measurement_bundle
    from test_post_measurement_history_observation import selection
    from caelab.post_observation import project_samples
    _,_,measurement=native_measurement_bundle(histories,monkeypatch,current=True)
    data=surface(quad=True);displace(data,lambda x:x*np.array([2.,3.,1.]))
    if not valid:data.GetPointData().GetArray('U').SetComponent(0,0,float('nan'))
    draft={**recipe(histories,data),'measurement':'surface_average','time':None,
        'time_units':None,'time_origin':None,'geometry':'current','geometry_state':definition()}
    source=SimpleNamespace(data=data,TimestepValues=[],UpdatePipeline=lambda:None)
    bundle=histories.build(source,draft,'single actual current geometry')
    rows=measurement.sample_data(bundle['source'])['rows']
    assert rows[0]['values']['ReferenceSurfaceArea']==pytest.approx(1.)
    snapshot={'complete':True,'origin':{},'recipe':draft,'summary':bundle['summary'],'rows':rows}
    if not valid:
        assert rows[0]['values']['CurrentSurfaceArea'] is None and rows[0]['values']['vtkValidMask']==0
        assert bundle['summary']['display_scale_used'] is None
        with pytest.raises(ValueError):project_samples(snapshot,selection(snapshot))
        return
    assert rows[0]['values']['CurrentSurfaceArea']==pytest.approx(6.)
    projected=project_samples(snapshot,selection(snapshot))
    assert projected['rows'][0]['value']==pytest.approx(1/3)
    assert projected['origin']['summary']['samples'][0]['geometry_state']==definition()
