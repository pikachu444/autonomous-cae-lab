"""TR-F: global SPC reaction -> opposite load -> planar quadratic H transpose.

The input values are nodal forces, never tractions. No area weights, nearest
node fallback, projection outside the selected surface, or resultant splitting.
"""
from copy import deepcopy
import math
import numpy as np

from .quadratic_surface import tri6_shape, tri6_derivatives
from .storage import canonical_hash

MAPPING = 'tri6_conservative_load'
TOLERANCE = 1e-10
EQUILIBRIUM_TOLERANCE = 1e-6
FIELD_KEYS = {'kind', 'unit', 'value', 'component', 'location', 'reduction', 'association', 'measure',
              'frame', 'coordinate_units', 'coordinates', 'node_ids', 'static',
              'source', 'capture_sha256'}


class TransferError(ValueError):
    def __init__(self, message, receipt):
        super().__init__(message)
        self.receipt = receipt


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _xyz(values, count=None):
    a = np.asarray(values, dtype=float)
    _need(a.ndim == 2 and a.shape[1] == 3 and len(a) > 0 and
          (count is None or len(a) == count) and np.isfinite(a).all(),
          'Finite XYZ vectors with matching rows are required')
    return a


def _ids(ids):
    _need(isinstance(ids, list) and ids and len(set(ids)) == len(ids) and
          all(type(n) is int and n > 0 for n in ids), 'Unique native node IDs are required')
    return ids


def _plane(x):
    origin = x[0]
    length = float(np.ptp(x, axis=0).max())
    _need(length > 0, 'The selected boundary has zero extent')
    _, singular, axes = np.linalg.svd((x-origin)/length, full_matrices=False)
    _need(len(singular) == 3 and singular[1] > 1e-10 and singular[2] <= TOLERANCE,
          'Select one planar nondegenerate TRI6 boundary')
    return origin, axes[:2], axes[2], length


def _inverse(point, coordinates, origin, axes, length):
    """Newton on the actual six-node geometry, including in-plane curved edges."""
    x = (coordinates-origin) @ axes.T / length
    p = (point-origin) @ axes.T / length
    linear = np.column_stack((x[1]-x[0], x[2]-x[0]))
    _need(abs(np.linalg.det(linear)) > 1e-12, 'Degenerate TRI6 corner triangle')
    uv = np.linalg.solve(linear, p-x[0])
    for _ in range(30):
        residual = tri6_shape(*uv) @ x-p
        jacobian = tri6_derivatives(*uv) @ x
        _need(abs(np.linalg.det(jacobian)) > 1e-12, 'Singular TRI6 inverse mapping')
        delta = np.linalg.solve(jacobian.T, residual)
        uv -= delta
        if float(np.linalg.norm(residual, ord=np.inf)) <= TOLERANCE/10:
            break
    else:
        raise ValueError('TRI6 inverse mapping did not converge')
    if min(uv[0], uv[1], 1-uv.sum()) < -TOLERANCE:
        return None
    row = tri6_shape(*uv)
    if np.max(np.abs(row @ coordinates-point))/length > TOLERANCE:
        return None
    return row


def validate_target(target):
    """Bounded declared geometry only; no interpolation/solver/native lookup."""
    _need(isinstance(target, dict) and set(target) == {'node_ids', 'coordinates', 'faces'},
          'Select target native node IDs, coordinates and ordered TRI6 faces')
    ids = _ids(target['node_ids'])
    x = _xyz(target['coordinates'], len(ids))
    faces=target['faces'];_need(isinstance(faces,list) and faces,'Select at least one TRI6 boundary face')
    used,seen=set(),set()
    for face in faces:
        _need(isinstance(face,list) and len(face)==6 and len(set(face))==6 and all(n in ids for n in face),
              'TRI6 face ordering or native membership is invalid')
        key=tuple(sorted(face[:3]));_need(key not in seen,'Duplicate boundary face');seen.add(key);used.update(face)
    _need(used==set(ids),'Target selection includes nodes outside its faces')
    return ids,x


def interpolation(source_coordinates, target):
    """H rows reproduce each source point from the explicit target TRI6 mesh."""
    ids,x=validate_target(target)
    y = _xyz(source_coordinates)
    _need(len(x)*len(y)<=4_000_000,'The selected interface exceeds the bounded 4-million-coefficient H capacity')
    origin, axes, normal, length = _plane(x)
    _need(np.max(np.abs((y-origin) @ normal))/length <= TOLERANCE,
          'Source nodes and receiver boundary must lie in the same global plane')
    faces = target['faces']
    _need(isinstance(faces, list) and faces, 'Select at least one TRI6 boundary face')
    lookup = {n: i for i, n in enumerate(ids)}
    indexed = []
    for face in faces:
        indices = [lookup[n] for n in face]
        c = x[indices]
        # Screen the entire quadratic Jacobian, not only corner area. For TRI6
        # the in-plane determinant is quadratic; its stationary/edge extrema
        # are included below, so a folded face cannot pass sparse sampling.
        xy = (c-origin) @ axes.T / length
        def det(r, s):
            return float(np.linalg.det(tri6_derivatives(r, s) @ xy))
        sample = [(0, 0), (1, 0), (0, 1), (.5, 0), (.5, .5), (0, .5)]
        matrix = np.asarray([[1,r,s,r*r,r*s,s*s] for r,s in sample])
        a,b,d,e,f,g = np.linalg.solve(matrix, [det(*v) for v in sample])
        candidates = sample[:3]
        for start, vector in [((0,0),(1,0)), ((0,0),(0,1)), ((1,0),(-1,1))]:
            r,s = start; u,v = vector
            qa=e*u*u+f*u*v+g*v*v
            qb=b*u+d*v+2*e*r*u+f*(r*v+s*u)+2*g*s*v
            if abs(qa)>1e-15:
                t=-qb/(2*qa)
                if 0<t<1: candidates.append((r+t*u,s+t*v))
        hessian=np.asarray([[2*e,f],[f,2*g]])
        if abs(np.linalg.det(hessian))>1e-15:
            stationary=np.linalg.solve(hessian,[-b,-d])
            if min(*stationary,1-stationary.sum())>=0:
                candidates.append(tuple(stationary))
        determinants=np.asarray([det(*v) for v in candidates])
        _need(np.min(determinants)>1e-12 or np.max(determinants)<-1e-12,
              'Folded or degenerate quadratic boundary face')
        indexed.append(indices)
    H = np.zeros((len(y), len(x)))
    for i, point in enumerate(y):
        rows=[]
        for indices in indexed:
            row=_inverse(point,x[indices],origin,axes,length)
            if row is not None:
                candidate=np.zeros(len(x));candidate[indices]=row;rows.append(candidate)
        _need(rows, 'A selected source node lies outside the target boundary')
        _need(all(np.max(np.abs(row-rows[0])) <= TOLERANCE for row in rows[1:]),
              'Overlapping target faces give ambiguous quadratic interpolation')
        H[i]=rows[0]
    unity=float(np.max(np.abs(H.sum(axis=1)-1)))
    affine=float(np.max(np.abs(H @ x-y))/length)
    _need(unity <= TOLERANCE and affine <= TOLERANCE,
          'Quadratic H failed partition of unity or affine coordinate reproduction')
    return H, {'partition_unity_error':unity,'affine_reproduction_error':affine,
               'limit':TOLERANCE,'coordinate_scale_mm':length}


def reaction_field(node_ids, coordinates, reactions, *, source, static):
    _ids(node_ids); _xyz(coordinates,len(node_ids));_xyz(reactions,len(node_ids))
    value={'kind':'field','unit':'N','value':deepcopy(reactions),'component':'VECTOR','location':'node','reduction':'none',
        'association':'POINTS','measure':'support_reaction_on_source',
        'frame':'global_cartesian','coordinate_units':'mm','coordinates':deepcopy(coordinates),
        'node_ids':list(node_ids),'source':deepcopy(source),'static':deepcopy(static)}
    value['capture_sha256']=canonical_hash(value)
    return value


def validate_static(state):
    _need(isinstance(state,dict) and set(state)=={'step','increment','load_parameter'} and
          all(type(state[k]) is int and state[k]>0 for k in ('step','increment')) and
          type(state['load_parameter']) in (int,float) and math.isfinite(state['load_parameter']) and
          state['load_parameter']>0, 'Select an explicitly retained converged static state')
    return deepcopy(state)


def validate_field(field):
    _need(isinstance(field,dict) and set(field)==FIELD_KEYS,'Select an admitted support reaction field')
    for key,value in {'kind':'field','unit':'N','component':'VECTOR','association':'POINTS',
        'measure':'support_reaction_on_source','frame':'global_cartesian','coordinate_units':'mm'}.items():
        _need(field[key]==value,'Unsupported support reaction '+key)
    _ids(field['node_ids']);_xyz(field['coordinates'],len(field['node_ids']));_xyz(field['value'],len(field['node_ids']))
    _need(field['capture_sha256']==canonical_hash({k:v for k,v in field.items() if k!='capture_sha256'}),
          'Support reaction field changed after retention')
    validate_static(field['static'])
    return field


def resultants(x, f, origin):
    return np.sum(f,axis=0),np.sum(np.cross(x-origin,f),axis=0)


def map_load(field, target, *, moment_origin_mm):
    receipt={'mapping':MAPPING,'status':'FAILED','conservative':True,
        'source_measure':'support_reaction_on_source','sign':'f_source = -R_source',
        'force_unit':'N','coordinate_unit':'mm','moment_unit':'N mm',
        'moment_origin_mm':deepcopy(moment_origin_mm),'source':deepcopy(field.get('source')),
        'source_field_sha256':canonical_hash(field),'target':deepcopy(target)}
    try:
        validate_field(field)
        origin=np.asarray(moment_origin_mm,dtype=float)
        _need(origin.shape==(3,) and np.isfinite(origin).all(),'Choose a finite global moment origin in mm')
        H,checks=interpolation(field['coordinates'],target)
        x=_xyz(field['coordinates']);y=_xyz(target['coordinates'])
        raw=_xyz(field['value']);force=-raw;mapped=H.T @ force
        sf,sm=resultants(x,force,origin);tf,tm=resultants(y,mapped,origin)
        scale=max(1.,float(np.sum(np.linalg.norm(force,axis=1))))
        length=checks['coordinate_scale_mm']
        force_error=float(np.max(np.abs(tf-sf))/scale)
        moment_error=float(np.max(np.abs(tm-sm))/(scale*max(1.,length)))
        # The matrix identity is the all-displacements virtual-work proof.
        # A deterministic non-rigid witness is recorded as an additional check.
        u=np.column_stack([np.sin(np.arange(len(y))+j+.25) for j in range(3)])
        source_work=float(np.sum(force*(H @ u)));target_work=float(np.sum(mapped*u))
        work_error=abs(source_work-target_work)/max(1.,abs(source_work),abs(target_work))
        _need(max(force_error,moment_error,work_error)<=TOLERANCE,
              'Force, moment or virtual work conservation failed')
        receipt.update(status='VALIDATED',H=H.tolist(),R_source_N=raw.tolist(),
            f_source_N=force.tolist(),f_target_N=mapped.tolist(),checks={**checks,
            'force_error':force_error,'moment_error':moment_error,'virtual_work_error':work_error},
            source_resultant_N=sf.tolist(),target_resultant_N=tf.tolist(),
            source_moment_Nmm=sm.tolist(),target_moment_Nmm=tm.tolist(),
            virtual_work={'source_Nmm':source_work,'target_Nmm':target_work,
                          'target_displacement_mm':u.tolist(),'identity':'u_source = H u_target'})
        mapped_field={'kind':'field','unit':'N','component':'VECTOR','association':'POINTS',
            'measure':'applied_nodal_force','frame':'global_cartesian','coordinate_units':'mm',
            'node_ids':deepcopy(target['node_ids']),'coordinates':deepcopy(target['coordinates']),
            'value':mapped.tolist(),'source':deepcopy(field['source']),
            'mapping':MAPPING,'receipt_sha256':canonical_hash(receipt)}
        return mapped_field,receipt
    except (ValueError,TypeError,KeyError,IndexError,np.linalg.LinAlgError) as error:
        receipt['error']=str(error)
        raise TransferError(str(error),receipt) from error
