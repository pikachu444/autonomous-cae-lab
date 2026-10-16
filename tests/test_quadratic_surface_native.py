import numpy as np
import pytest
vtk = pytest.importorskip('vtk')
from vtk.util.numpy_support import numpy_to_vtk
from test_post_measurement_histories import histories
from test_post_analysis import analysis
from test_surface_quadrature import coordinates


def grid(kind=6,height=.2,volume=False):
    data=vtk.vtkUnstructuredGrid();points=vtk.vtkPoints();points.SetDataTypeToDouble()
    cell=vtk.vtkQuadraticTetra() if volume else vtk.vtkQuadraticTriangle() if kind==6 else vtk.vtkQuadraticQuad()
    coords=np.array(cell.GetParametricCoords()).reshape(-1,3) if volume else coordinates(kind,height)
    for i,point in enumerate(coords):points.InsertNextPoint(point);cell.GetPointIds().SetId(i,i)
    data.SetPoints(points);data.InsertNextCell(cell.GetCellType(),cell.GetPointIds())
    for attrs,name,values in [(data.GetPointData(),'q',np.full(len(coords),2.)),
          (data.GetPointData(),'NativeNodeId',np.arange(len(coords))+100),
          (data.GetCellData(),'cell_q',np.array([5.]))]:
        array=numpy_to_vtk(values,deep=True);array.SetName(name);attrs.AddArray(array)
    return data


def recipe(histories,data,association='POINTS'):
    return {'measurement':'surface_average','surface_faces':histories.surface_catalog(data),'geometry':'fixed_reference',
        'association':association,'array':'q' if association=='POINTS' else 'cell_q','component':None,'direction':None,
        'coordinate_units':'mm','units':'MPa','frame':'scalar','coordinate_frame':'lab'}


@pytest.mark.parametrize('kind',[6,8])
def test_real_high_order_boundary_selection_integral_midpoints_and_masks(histories,kind):
    data=grid(kind);draft=recipe(histories,data);faces=draft['surface_faces']
    assert len(faces)==1 and len(faces[0]['point_indices'])==kind
    assert faces[0]['original_point_ids']['NativeNodeId']==list(range(100,100+kind))
    value=histories.surface_average(data,draft)
    assert value['value']==pytest.approx(2.) and value['area']>(.5 if kind==6 else 1.)
    mask=numpy_to_vtk(np.array([1]*(kind-1)+[0],dtype=np.uint8),deep=True);mask.SetName('vtkValidPointMask');data.GetPointData().AddArray(mask)
    assert not histories.surface_average(data,draft)['valid']


def test_tetra10_boundary_and_constant_original_owner_field(histories):
    data=grid(volume=True);draft=recipe(histories,data,'CELLS')
    assert len(draft['surface_faces'])==4 and all(len(f['point_indices'])==6 for f in draft['surface_faces'])
    value=histories.surface_average(data,draft)
    assert value['value']==pytest.approx(5.)
    assert value['area']==pytest.approx(1.5+np.sqrt(3)/2,abs=1e-13)


def test_shared_quadratic_face_and_mismatching_midnode_are_not_exposed(histories):
    data=vtk.vtkUnstructuredGrid();points=vtk.vtkPoints();points.SetDataTypeToDouble();seen={}
    natural=np.array(vtk.vtkQuadraticTetra().GetParametricCoords()).reshape(-1,3)
    for corners in (np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1.]]),np.array([[0,0,0],[0,1,0],[1,0,0],[0,0,-1.]])):
        cell=vtk.vtkQuadraticTetra()
        for i,(r,s,t) in enumerate(natural):
            xyz=tuple((1-r-s-t)*corners[0]+r*corners[1]+s*corners[2]+t*corners[3])
            if xyz not in seen:seen[xyz]=points.InsertNextPoint(xyz)
            cell.GetPointIds().SetId(i,seen[xyz])
        data.SetPoints(points);data.InsertNextCell(24,cell.GetPointIds())
    faces=histories.surface_catalog(data)
    assert len(faces)==6
    assert all(set(f['point_indices'][:3])!={0,1,2} for f in faces)
    original=data.GetCell(1);ids=vtk.vtkIdList();ids.DeepCopy(original.GetPointIds())
    swapped=vtk.vtkIdList();swapped.DeepCopy(ids);swapped.SetId(4,ids.GetId(5));swapped.SetId(5,ids.GetId(4))
    data.ReplaceCell(1,swapped.GetNumberOfIds(),[swapped.GetId(i) for i in range(swapped.GetNumberOfIds())])
    with pytest.raises(ValueError,match='비정합'):histories.surface_catalog(data)
    ids.SetId(4,points.InsertNextPoint(.1,.5,0));data.ReplaceCell(1,ids.GetNumberOfIds(),[ids.GetId(i) for i in range(ids.GetNumberOfIds())])
    with pytest.raises(ValueError,match='비정합'):histories.surface_catalog(data)
