"""Public tiny TR-U fixture geometry; no source solve or deck generation.

The existing saved single straight C3D10 tetra is subdivided into eight straight
C3D10 cells over the same reference domain. Native execution is separately
declared and uses the existing FreeCAD freeze/contact writer/JobManager.
"""
from copy import deepcopy
import numpy as np
from caelab.post_spatial_mapping import tetra10_boundary
from caelab.adapters.frozen_fem import CCX_FROM_NATIVE_TET10

EDGES=((0,1),(1,2),(2,0),(0,3),(1,3),(2,3))


def subdivided_receiver(source):
    if len(source['elements'])!=1:raise ValueError('This public fixture uses one original straight tetra.')
    original=dict(zip(source['node_ids'],source['coordinates']))
    cell=source['elements'][0]['node_ids'];points=[np.asarray(original[n],dtype=float) for n in cell]
    if any(not np.array_equal(points[4+i],(points[a]+points[b])/2) for i,(a,b) in enumerate(EDGES)):
        raise ValueError('The bounded receiving fixture requires the original straight C3D10 geometry.')
    # Four corner tetrahedra and the central octahedron split about edge01--23.
    children=[(0,4,6,7),(4,1,5,8),(6,5,2,9),(7,8,9,3),
              (4,6,7,9),(4,6,5,9),(4,5,8,9),(4,7,8,9)]
    coordinates=[point.tolist() for point in points];index={tuple(x):i+1 for i,x in enumerate(coordinates)}
    def node(point):
        key=tuple(point)
        if key not in index:index[key]=len(coordinates)+1;coordinates.append(list(point))
        return index[key]
    elements=[]
    for identifier,child in enumerate(children,1):
        corners=[points[i] for i in child]
        if np.linalg.det((np.asarray(corners[1:])-corners[0]).T)<0:corners[1],corners[2]=corners[2],corners[1]
        xyz=corners+[(corners[a]+corners[b])/2 for a,b in EDGES]
        ids=[node(point) for point in xyz];native=[None]*10
        for deck_slot,native_slot in enumerate(CCX_FROM_NATIVE_TET10):native[native_slot]=ids[deck_slot]
        elements.append({'element_id':identifier,'native_element_id':identifier,'type':'C3D10',
            'body_id':'Solid','node_ids':ids,'native_node_ids':native})
    ids=list(range(1,len(coordinates)+1));faces=tetra10_boundary(ids,coordinates,elements)
    boundary=sorted({n for face in faces for n in face['node_ids']})
    return {'node_ids':ids,'coordinates':coordinates,'elements':elements,
        'boundary_faces':[[face['element_id'],face['face']] for face in faces],
        'boundary_node_ids':boundary,'components':[1,2,3],
        'units':deepcopy(source['units']),'coordinate_frame':source['coordinate_frame'],'geometry':'fixed_reference'}


def transfer_definition(source):
    faces=tetra10_boundary(source['node_ids'],source['coordinates'],source['elements'])
    return {'source_faces':[[face['element_id'],face['face']] for face in faces],
        'rotation':np.eye(3).tolist(),'translation':[0.,0.,0.],
        'distance_tolerance':1e-10,'natural_tolerance':1e-12,'weight_tolerance':1e-11,
        'max_iterations':30,'source_static':deepcopy(source['static'])}
