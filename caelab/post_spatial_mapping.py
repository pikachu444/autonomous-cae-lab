"""Bounded C3D10 topology and TRI6 reference-boundary inverse mapping.

Only explicitly selected exterior faces are admitted. This is not a volume
submodel mapper, nearest-neighbour projection or a conservative transfer.
"""
from collections import defaultdict
import math
import numpy as np

from .contact_deck import FACES
from .quadratic_surface import tri6_shape, tri6_derivatives


def tetra10_boundary(node_ids, coordinates, elements):
    """Keep native IDs and the existing CCX face order, including midsides."""
    ids=list(node_ids);points=np.asarray(coordinates,dtype=float)
    if (not ids or any(type(n) is not int or n<=0 for n in ids) or len(set(ids))!=len(ids)
            or points.shape!=(len(ids),3) or not np.isfinite(points).all()):
        raise ValueError('C3D10 reference nodes require distinct positive IDs and finite XYZ.')
    positions=dict(zip(ids,points));owners=defaultdict(list);seen=set();cell_ids=set()
    for element in elements:
        nodes=element.get('node_ids');identifier=element.get('element_id')
        if (element.get('type')!='C3D10' or type(identifier) is not int or identifier<=0 or identifier in cell_ids
                or not isinstance(nodes,list) or len(nodes)!=10 or len(set(nodes))!=10
                or any(type(n) is not int or n not in positions for n in nodes)):
            raise ValueError('Use distinct ordered C3D10 cells with complete native node identities.')
        key=tuple(sorted(nodes))
        if key in seen:raise ValueError('Duplicate C3D10 owner cells are ambiguous.')
        seen.add(key);cell_ids.add(identifier)
        corners=np.asarray([positions[n] for n in nodes[:4]])
        determinant=float(np.linalg.det((corners[1:]-corners[0]).T))
        if not math.isfinite(determinant) or determinant<=0:
            raise ValueError('Inverted or degenerate ordered C3D10 corner geometry.')
        for side,slots in FACES.items():
            face=[nodes[i] for i in slots]
            owners[tuple(sorted(face[:3]))].append({'element_id':identifier,'face':side,'node_ids':face})
    if not seen:raise ValueError('A reference C3D10 owner mesh is required.')
    exterior=[]
    for faces in owners.values():
        if len(faces)>2:raise ValueError('Nonmanifold C3D10 reference face owners.')
        if len(faces)==1:exterior.append(faces[0]);continue
        def edges(face):
            a,b,c,ab,bc,ca=face['node_ids']
            return {tuple(sorted(pair)):middle for pair,middle in [((a,b),ab),((b,c),bc),((c,a),ca)]}
        if edges(faces[0])!=edges(faces[1]):
            raise ValueError('Adjacent C3D10 faces have inconsistent midside connectivity.')
    return sorted(exterior,key=lambda face:(face['element_id'],face['face']))


def invert_tri6(coordinates, point, *, distance_tolerance, natural_tolerance, max_iterations):
    """Invert a certified native quadratic face; never project off-surface data."""
    from .quadratic_surface import regularity
    coordinates=np.asarray(coordinates,dtype=float);point=np.asarray(point,dtype=float)
    if coordinates.shape!=(6,3) or point.shape!=(3,) or not np.isfinite(coordinates).all() or not np.isfinite(point).all():
        raise ValueError('TRI6 inverse requires six actual reference nodes and finite XYZ.')
    for name,value in [('distance_tolerance',distance_tolerance),('natural_tolerance',natural_tolerance)]:
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:
            raise ValueError(name+' must be an explicit finite nonnegative number.')
    if distance_tolerance==0 or type(max_iterations) is not int or not 1<=max_iterations<=100:
        raise ValueError('Use a positive geometric tolerance and an iteration budget from1 to100.')
    shifted=coordinates-coordinates[0];query=point-coordinates[0]
    certificate=regularity(shifted)
    natural=np.linalg.lstsq(np.column_stack((shifted[1],shifted[2])),query,rcond=None)[0]
    for iteration in range(max_iterations):
        weights=tri6_shape(*natural);residual=weights@shifted-query
        if np.linalg.norm(residual)<=distance_tolerance:
            break
        tangent=tri6_derivatives(*natural)@shifted
        delta,_,rank,_=np.linalg.lstsq(tangent.T,residual,rcond=None)
        if rank!=2 or not np.isfinite(delta).all():break
        updated=natural-delta
        if np.array_equal(updated,natural):break
        natural=updated
        if not np.isfinite(natural).all():break
    if not np.isfinite(natural).all():return None
    weights=tri6_shape(*natural);residual=float(np.linalg.norm(weights@shifted-query))
    inside=(natural[0]>=-natural_tolerance and natural[1]>=-natural_tolerance
            and natural.sum()<=1+natural_tolerance)
    if not inside or not math.isfinite(residual) or residual>distance_tolerance:return None
    return {'natural_coordinates':natural.tolist(),'weights':weights.tolist(),
            'distance':residual,'iterations':iteration+1,'geometry_certificate':certificate}


def selected_boundary(node_ids, coordinates, elements, selection):
    catalog=tetra10_boundary(node_ids,coordinates,elements)
    known={(face['element_id'],face['face']):face for face in catalog}
    if (not isinstance(selection,list) or not selection or any(not isinstance(row,list) or len(row)!=2
            or any(type(v) is not int for v in row) for row in selection)
            or len({tuple(row) for row in selection})!=len(selection)):
        raise ValueError('Select distinct actual source exterior element/face pairs.')
    if any(tuple(row) not in known for row in selection):
        raise ValueError('A selected face is not an exterior face of its declared C3D10 owner.')
    return [known[tuple(row)] for row in selection]
