"""Manufactured VTK fields and exact definitions; no solver or fake native pass."""
from copy import deepcopy
import importlib
import sys
from types import SimpleNamespace
import numpy as np
import pytest
vtk=pytest.importorskip('vtk')
from vtk.util.numpy_support import numpy_to_vtk
from test_post_analysis import analysis,grid


@pytest.fixture
def histories(analysis):
    for name in ('apps.desktop_post.measurements','apps.desktop_post.measurement_histories'):sys.modules.pop(name,None)
    module=importlib.import_module('apps.desktop_post.measurement_histories')
    module.external.times=lambda source:list(source.TimestepValues)
    yield module
    for name in ('apps.desktop_post.measurements','apps.desktop_post.measurement_histories'):sys.modules.pop(name,None)


def surface(quad=False):
    result=vtk.vtkUnstructuredGrid();points=vtk.vtkPoints()
    coordinates=[(0,0,0),(1,0,0),(1,1,0),(0,1,0)] if quad else [(0,0,0),(1,0,0),(0,1,0),(2,0,0),(4,0,0),(2,2,0)]
    for point in coordinates:points.InsertNextPoint(*point)
    result.SetPoints(points)
    for ids in ([(0,1,2,3)] if quad else [(0,1,2),(3,4,5)]):
        native=vtk.vtkIdList()
        for value in ids:native.InsertNextId(value)
        result.InsertNextCell(9 if quad else 5,native)
    for attrs,name,values in ((result.GetPointData(),'NativeNodeId',np.arange(len(coordinates))),
        (result.GetPointData(),'q',np.asarray([0.,0.,1.,0.] if quad else [2.,2.,2.,8.,8.,8.])),
        (result.GetCellData(),'cell_q',np.asarray([3.] if quad else [2.,8.]))):
        array=numpy_to_vtk(values,deep=True);array.SetName(name);attrs.AddArray(array)
    return result


def recipe(module,data,association='POINTS'):
    return {'measurement':'surface_time','association':association,'array':'q' if association=='POINTS' else 'cell_q',
        'surface_faces':module.surface_catalog(data),'geometry':'fixed_reference','component':None,'direction':None,
        'units':'MPa','quantity':'stress','measure':'Cauchy','frame':'lab','coordinate_frame':'lab','coordinate_units':'mm',
        'time_range':[0.,.7],'reference_time':0.,'time_units':'s','time_origin':'PHYSICAL_TIME'}


@pytest.mark.parametrize('association',['POINTS','CELLS'])
def test_unequal_face_area_average_is_not_arithmetic_average(histories,association):
    data=surface();draft=recipe(histories,data,association);before=deepcopy(draft)
    result=histories.surface_average(data,draft)
    assert result['area']==2.5 and result['value']==pytest.approx(6.8)
    assert result['value']!=5 and draft==before


def test_quad_native_triangulation_is_not_bilinear_nodal_average(histories):
    data=surface(quad=True);result=histories.surface_average(data,recipe(histories,data))
    assert result['area']==1 and result['value']==pytest.approx(1/3)
    assert result['value']!=pytest.approx(.25)


def test_volume_catalog_retains_exact_boundary_face_and_rejects_interior(histories):
    data=grid([(0,0,0),(1,0,0),(0,1,0),(0,0,1),(0,0,-1)],[(0,1,2,3),(0,2,1,4)],[1.,1.,1.,1.,1.])
    faces=histories.surface_catalog(data)
    assert len(faces)==6 and all(sorted(f['point_indices'])!=[0,1,2] for f in faces)
    draft=recipe(histories,data);draft['array']='response';draft['surface_faces']=[faces[0]]
    assert histories.surface_average(data,draft)['value']==1
    draft['surface_faces']=[{**faces[0],'point_indices':[0,1,2],'coordinates':[[0,0,0],[1,0,0],[0,1,0]]}]
    with pytest.raises(ValueError,match='다시 선택'):histories.surface_average(data,draft)


@pytest.mark.parametrize('association,mask,values',[('POINTS','vtkValidPointMask',[1,1,1,1,0,1]),
    ('POINTS','vtkGhostType',[0,0,0,0,2,0]),('CELLS','vtkGhostType',[0,1]),('CELLS','vtkGhostType',[0,32])])
def test_invalid_selected_sample_never_shrinks_averaging_domain(histories,association,mask,values):
    data=surface();draft=recipe(histories,data,association)
    a=numpy_to_vtk(np.asarray(values,dtype=np.uint8),deep=True);a.SetName(mask)
    (data.GetPointData() if association=='POINTS' else data.GetCellData()).AddArray(a)
    # Use the captured face definition: changing a validity flag cannot change its domain.
    result=histories.surface_average(data,draft,draft['surface_faces'])
    assert not result['valid'] and result['value'] is None and result['area'] is None


def test_reference_geometry_change_duplicate_face_and_unknown_current_are_rejected(histories):
    data=surface();draft=recipe(histories,data)
    with pytest.raises(ValueError):histories.surface_average(data,{**draft,'surface_faces':[draft['surface_faces'][0]]*2})
    with pytest.raises(ValueError,match='현재 면적'):histories.surface_average(data,{**draft,'geometry':'current'})
    data.GetPoints().SetPoint(1,1.1,0,0)
    with pytest.raises(ValueError,match='다시 선택'):histories.surface_average(data,draft,draft['surface_faces'])


def test_exact_irregular_clock_no_static_history_or_implicit_reference(histories):
    data=surface();draft=recipe(histories,data);source=SimpleNamespace(TimestepValues=[0.,.2,.7])
    assert histories._clock(source,draft)==([0.,.2,.7],0.)
    assert histories._clock(source,{**draft,'time_range':[.2,.7],'reference_time':0.})==([.2,.7],0.)
    for bad in ({'time_range':[0.,.5]},{'reference_time':None},{'time_units':'UNKNOWN'}):
        with pytest.raises(ValueError):histories._clock(source,{**draft,**bad})
    with pytest.raises(ValueError,match='정적'):histories._clock(SimpleNamespace(TimestepValues=[]),draft)


def test_gauge_invalid_time_sample_is_masked_but_reference_and_identity_changes_reject(histories):
    from test_post_gauge import field,recipe as gauge_recipe
    m=histories._measurement_module();draft=gauge_recipe();data=field(second=(3,3,4))
    assert m._gauge_definition(data,draft)['value']==1
    data.GetPointData().GetArray('response').SetComponent(1,0,float('nan'))
    result=m._gauge_definition(data,draft,allow_invalid=True)
    assert result['value'] is None and not result['valid']
    with pytest.raises(ValueError):m._gauge_definition(data,draft)
    with pytest.raises(ValueError,match='REFERENCE_REPAIR'):m._gauge_definition(data,{**draft,'point2':[2,0,0]},allow_invalid=True)


def test_single_static_average_has_no_fabricated_time(histories,monkeypatch):
    data=surface();draft={**recipe(histories,data),'measurement':'surface_average','time':None,'time_units':None,'time_origin':None}
    source=SimpleNamespace(TimestepValues=[],data=data)
    monkeypatch.setattr(histories.analysis,'_freeze',lambda source,time,namespace,proxies:source)
    monkeypatch.setattr(histories.analysis,'_fetch',lambda source:source.data)
    monkeypatch.setattr(histories,'_table',lambda values,namespace:SimpleNamespace(values=values))
    result=histories.build(source,draft,'static')
    assert result['source'].values=={'SampleIndex':[0],'SurfaceAreaAverage':[6.8],'vtkValidMask':[1],'SurfaceArea':[2.5]}
    assert result['summary']['time'] is None and result['summary']['time_values']==[]
    assert result['summary']['axis_unit']=='1' and result['summary']['area_unit']=='mm^2'


def test_gauge_history_preserves_nonzero_reference_and_invalid_clock_row(histories,monkeypatch):
    from test_post_gauge import field,recipe as gauge_recipe
    frames={0.:field(second=(4,3,4)),.07:field(second=(float('nan'),3,4)),.2:field(second=(6,3,4))}
    draft={**gauge_recipe(),'measurement':'gauge_time','time_range':[0.,.2],'reference_time':0.,'quantity':'length','time_units':'s','time_origin':'PHYSICAL_TIME'}
    source=SimpleNamespace(TimestepValues=[0.,.07,.2])
    monkeypatch.setattr(histories.analysis,'_freeze',lambda source,time,namespace,proxies:SimpleNamespace(data=frames[time]))
    monkeypatch.setattr(histories.analysis,'_fetch',lambda source:source.data)
    monkeypatch.setattr(histories,'_table',lambda values,namespace:SimpleNamespace(values=values))
    result=histories.build(source,draft,'relative')
    assert result['source'].values=={'Time':[0.,.07,.2],'GaugeRelativeDisplacement':[2.,None,4.],'vtkValidMask':[1,0,1]}
    assert result['summary']['baseline_subtraction'] is False
    assert result['summary']['samples'][1]['reason']=='nonfinite_endpoint'


def test_selected_declared_mask_is_not_replaced_by_unrelated_joint_mask(histories):
    data=surface();draft=recipe(histories,data)
    for name,values in [('vtkValidPointMask',[0]*6),('selected_q_valid',[1]*6)]:
        a=numpy_to_vtk(np.asarray(values,dtype=np.uint8),deep=True);a.SetName(name);data.GetPointData().AddArray(a)
    draft.update(validity_policy='declared_array',validity_masks=['selected_q_valid'])
    assert histories.surface_average(data,draft,draft['surface_faces'])['value']==6.8
    data.GetPointData().GetArray('selected_q_valid').SetValue(4,0)
    assert histories.surface_average(data,draft,draft['surface_faces'])['value'] is None


def test_scalar_frame_is_independent_but_vector_components_require_declared_fixed_basis(histories):
    data=surface();draft=recipe(histories,data);draft['frame']='scalar'
    assert histories.surface_average(data,draft)['value']==6.8
    a=numpy_to_vtk(np.tile([2.,3.,4.],(6,1)),deep=True);a.SetName('vector');data.GetPointData().AddArray(a)
    draft.update(array='vector',component='projection',direction=[1.,0.,0.],frame='lab')
    with pytest.raises(ValueError,match='fixed_cartesian'):histories.surface_average(data,draft)
    draft['basis']='fixed_cartesian'
    assert histories.surface_average(data,draft)['value']==2.
    with pytest.raises(ValueError):histories.surface_average(data,{**draft,'frame':'local'})


def test_gauge_reference_identifies_geometry_without_requiring_valid_reference_displacement(histories,monkeypatch):
    from test_post_gauge import field,recipe as gauge_recipe
    frames={0.:field(second=(float('nan'),3,4)),.07:field(second=(4,3,4)),.2:field(second=(6,3,4))}
    draft={**gauge_recipe(),'measurement':'gauge_time','time_range':[.07,.2],'reference_time':0.,
        'quantity':'length','time_units':'s','time_origin':'PHYSICAL_TIME'}
    source=SimpleNamespace(TimestepValues=[0.,.07,.2])
    monkeypatch.setattr(histories.analysis,'_freeze',lambda source,time,namespace,proxies:SimpleNamespace(data=frames[time]))
    monkeypatch.setattr(histories.analysis,'_fetch',lambda source:source.data)
    monkeypatch.setattr(histories,'_table',lambda values,namespace:SimpleNamespace(values=values))
    result=histories.build(source,draft,'reference outside interval')
    assert result['source'].values['Time']==[.07,.2]
    assert result['source'].values['GaugeRelativeDisplacement']==[2.,4.]
    assert result['source'].values['vtkValidMask']==[1,1]
    included=histories.build(source,{**draft,'time_range':[0.,.2]},'reference included')
    assert included['source'].values['GaugeRelativeDisplacement']==[None,2.,4.]
    assert included['source'].values['vtkValidMask']==[0,1,1]
    assert included['summary']['baseline_subtraction'] is False
    # Geometry/ID authority is still checked even when U at reference is invalid.
    with pytest.raises(ValueError,match='REFERENCE_REPAIR'):
        histories.build(source,{**draft,'point2':[2.,0.,0.]},'wrong reference geometry')
