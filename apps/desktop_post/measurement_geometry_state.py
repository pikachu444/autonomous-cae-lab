"""Actual X+u measurement geometry; display Warp scale is never an input."""
from copy import deepcopy
import math
import numpy as np


def face_normal(coordinates):
    """Oriented area vector from the same native face connectivity/quadrature."""
    points=np.asarray(coordinates,dtype=float)
    if points.shape not in ((3,3),(4,3),(6,3),(8,3)) or not np.isfinite(points).all():
        raise ValueError('A finite native TRI3/QUAD4/TRI6/QUAD8 face is required')
    points=points-points[0]
    if len(points) in (6,8):
        from caelab.quadratic_surface import derivatives,regularity
        try:from .surface_quadrature import rule
        except ImportError:from surface_quadrature import rule
        regularity(points);vectors=[]
        for r,s,w in rule(len(points),True):
            tangent=derivatives(len(points),r,s)@points
            vectors.append(w*np.cross(tangent[0],tangent[1]))
        vector=np.sum(vectors,axis=0)
    else:
        # VTK's own triangulation retains its diagonal and original orientation.
        from vtkmodules.vtkCommonDataModel import vtkTriangle,vtkQuad
        from vtkmodules.vtkCommonCore import vtkIdList,vtkPoints
        cell=vtkTriangle() if len(points)==3 else vtkQuad()
        for i,point in enumerate(points):cell.GetPoints().SetPoint(i,point);cell.GetPointIds().SetId(i,i)
        ids=vtkIdList();triangles=vtkPoints()
        if not cell.Triangulate(0,ids,triangles):raise ValueError('Native surface triangulation failed')
        vectors=[]
        for i in range(0,triangles.GetNumberOfPoints(),3):
            a,b,c=[np.asarray(triangles.GetPoint(i+j)) for j in range(3)]
            cross=np.cross(b-a,c-a)
            if not np.isfinite(cross).all() or np.linalg.norm(cross)==0:
                raise ValueError('Current surface has a degenerate native triangle')
            vectors.append(cross/2)
        vector=np.sum(vectors,axis=0)
        if any(np.dot(v,vector)<=0 for v in vectors):
            raise ValueError('Current surface is folded or has inconsistent native orientation')
    magnitude=float(np.linalg.norm(vector))
    if not math.isfinite(magnitude) or magnitude<=0:
        raise ValueError('The oriented surface area vector is degenerate')
    return {'normal':(vector/magnitude).tolist(),'oriented_area_vector':vector.tolist(),
            'normal_semantics':'area_weighted_oriented_native_face_normal'}


def reference_plus_displacement(data,faces,definition,*,coordinate_units,coordinate_frame):
    """Copy selected-point geometry using actual same-frame global displacement."""
    from caelab.experiment_calibration import factor
    from vtkmodules.vtkCommonCore import vtkPoints
    from vtkmodules.util.numpy_support import vtk_to_numpy,numpy_to_vtk
    required={'mode','array','association','units','frame','basis'}
    if (not isinstance(definition,dict) or not required<=set(definition) or
            not set(definition)<=required|{'validity_masks','validity_policy'} or
            definition.get('mode')!='reference_plus_displacement' or definition.get('association')!='POINTS' or
            definition.get('basis')!='fixed_cartesian' or definition.get('frame')!=coordinate_frame or
            not isinstance(coordinate_frame,str) or coordinate_frame.lower() in ('unknown','undeclared','local','scalar')):
        raise ValueError('Declare same-frame POINTS displacement in the fixed coordinate basis')
    scale=factor(definition['units'],coordinate_units)
    from caelab.experiment_calibration import UNITS
    if UNITS.get(coordinate_units,(None,))[0]!='length':raise ValueError('Actual geometry requires length units')
    array=data.GetPointData().GetArray(definition['array'])
    if array is None or array.GetNumberOfComponents()!=3 or array.GetNumberOfTuples()!=data.GetNumberOfPoints():
        raise ValueError('The actual native displacement field is missing or has a different POINTS layout')
    if any([list(data.GetPoint(i)) for i in face['point_indices']]!=face['coordinates'] for face in faces):
        raise ValueError('Reference coordinates changed; actual displacement cannot be added to displayed/current geometry')
    indices=sorted({i for face in faces for i in face['point_indices']})
    points=vtkPoints();points.SetData(numpy_to_vtk(np.asarray(vtk_to_numpy(data.GetPoints().GetData()),dtype=np.float64).copy(),deep=True))
    for i in indices:
        original=np.asarray(data.GetPoint(i));u=np.asarray(array.GetTuple(i))
        if not np.isfinite(original).all() or not np.isfinite(u).all():
            return {'valid':False,'reason':'nonfinite_actual_displacement','data':None,'faces':None}
        points.SetPoint(i,original+scale*u)
    current=data.NewInstance();current.ShallowCopy(data);current.SetPoints(points)
    transformed=[];normals=[]
    for face in faces:
        row=deepcopy(face);row['coordinates']=[list(current.GetPoint(i)) for i in face['point_indices']]
        transformed.append(row)
        normals.append({'cell_index':face['cell_index'],'face_index':face['face_index'],
            'reference':face_normal(face['coordinates']),'current':face_normal(row['coordinates'])})
    return {'valid':True,'reason':'valid','data':current,'faces':transformed,'normals':normals,
            'definition':deepcopy(definition),'displacement_to_coordinate_factor':scale,
            'geometry':'current','source_coordinates':'reference_plus_actual_displacement',
            'display_scale_used':False}
