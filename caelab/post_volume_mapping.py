"""Native VTK volume shape interpolation with retained source-cell lineage.

No IP recovery, nearest-cell fallback, extrapolation or conservative transfer.
VTK owns TET4/TET10/HEX8/HEX20 shapes and native point ordering. Whole-domain
regularity follows quadratic_surface.regularity's Bernstein contraction test.
"""
from copy import deepcopy
from itertools import product
import hashlib
import math
import numpy as np
from .storage import canonical_hash

FAMILIES={'TET4':('vtkTetra',4),'TET10':('vtkQuadraticTetra',10),
          'HEX8':('vtkHexahedron',8),'HEX20':('vtkQuadraticHexahedron',20)}
_BERNSTEIN_INVERSE=np.array([[1.,0.,0.],[-.5,2.,-.5],[0.,0.,1.]])


def _need(ok,message):
    if not ok:raise ValueError(message)


def _points(ids,coordinates,label):
    points=np.asarray(coordinates,dtype=float)
    _need(isinstance(ids,list) and ids and all(type(n) is int and n>=0 for n in ids) and
          len(set(ids))==len(ids) and points.shape==(len(ids),3) and np.isfinite(points).all(),
          label+' requires unique native IDs and finite XYZ rows')
    return points


def _shape(cell,natural):
    weights=[0.]*cell.GetNumberOfPoints();cell.InterpolateFunctions(natural,weights)
    return np.asarray(weights)


def _derivatives(cell,natural):
    values=[0.]*(3*cell.GetNumberOfPoints());cell.InterpolateDerivs(natural,values)
    return np.asarray(values).reshape(3,-1)


def _certificate(cell,points,family):
    shifted=points-points[0];scale=float(np.ptp(shifted,axis=0).max())
    _need(scale>0,'Degenerate native volume cell')
    shifted=shifted/scale
    center=np.full(3,.25 if family.startswith('TET') else .5)
    affine=_derivatives(cell,center)@shifted
    determinant=float(np.linalg.det(affine))
    _need(math.isfinite(determinant) and determinant>0,'Inverted or degenerate native volume ordering')
    try:inverse=np.linalg.inv(affine);condition=float(np.linalg.cond(affine))
    except np.linalg.LinAlgError:raise ValueError('Singular native volume Jacobian') from None
    def residual(natural):return _derivatives(cell,natural)@shifted@inverse-np.eye(3)
    if family.startswith('TET'):
        coefficients=np.asarray([residual(p) for p in ((0,0,0),(1,0,0),(0,1,0),(0,0,1))])
    elif family=='HEX8':coefficients=np.asarray([residual(p) for p in product((0.,1.),repeat=3)])
    else:
        values=np.asarray([residual(p) for p in product((0.,.5,1.),repeat=3)]).reshape(3,3,3,3,3)
        basis=_BERNSTEIN_INVERSE
        coefficients=np.einsum('ai,bj,ck,ijkxy->abcxy',basis,basis,basis,values).reshape(-1,3,3)
    _need(np.isfinite(coefficients).all() and math.isfinite(condition),'Native volume regularity is nonfinite')
    bound=max(float(np.linalg.norm(matrix,2)) for matrix in coefficients)
    geometry_scale=float(np.linalg.norm(inverse,2))*max(float(np.linalg.norm(p)) for p in shifted)
    margin=128*np.finfo(float).eps*(condition+geometry_scale)*max(1.,bound)
    _need(math.isfinite(margin) and bound+margin<1.,
          'Whole-cell regularity is unverified: check folds, midside ordering or deformation outside the contraction certificate')
    return {'method':'native_shape_affine_contraction_bernstein','derivative_bound':bound,
            'roundoff_margin':margin,'status':'CERTIFIED_VOLUME_MAP','engineering_qualification':'UNKNOWN'}


def _bounds(cell,points,family):
    """Conservative Bernstein coefficient hull, including quadratic bulges."""
    origin=points[0];scale=float(np.ptp(points,axis=0).max());x=(points-origin)/scale
    if family in ('TET4','HEX8'):coefficients=x
    elif family=='TET10':
        edges=((0,1),(1,2),(2,0),(0,3),(1,3),(2,3))
        coefficients=np.asarray([*x[:4],*[2*x[4+i]-.5*(x[a]+x[b]) for i,(a,b) in enumerate(edges)]])
    else:
        values=np.asarray([_shape(cell,p)@x for p in product((0.,.5,1.),repeat=3)]).reshape(3,3,3,3)
        basis=_BERNSTEIN_INVERSE
        coefficients=np.einsum('ai,bj,ck,ijkx->abcx',basis,basis,basis,values).reshape(-1,3)
    _need(np.isfinite(coefficients).all(),'Native volume geometry bounds are nonfinite')
    margin=256*np.finfo(float).eps*max(1.,float(np.max(np.abs(coefficients))))
    return origin,scale,np.min(coefficients,axis=0)-margin,np.max(coefficients,axis=0)+margin


def _inverse(cell,points,query,family,distance_tolerance,natural_tolerance,max_iterations):
    scale=float(np.ptp(points,axis=0).max());x=(points-points[0])/scale;q=(query-points[0])/scale
    natural=np.full(3,.25 if family.startswith('TET') else .5)
    converged=False
    for iteration in range(max_iterations):
        weights=_shape(cell,natural);residual=weights@x-q;error=float(np.linalg.norm(residual))
        if error<=distance_tolerance/scale:converged=True;break
        try:delta=np.linalg.solve((_derivatives(cell,natural)@x).T,residual)
        except np.linalg.LinAlgError:break
        if not np.isfinite(delta).all():break
        for fraction in (1.,.5,.25,.125,.0625,.03125,.015625):
            candidate=natural-fraction*delta
            if np.isfinite(candidate).all() and np.linalg.norm(_shape(cell,candidate)@x-q)<error:
                natural=candidate;break
        else:break
    weights=_shape(cell,natural);distance=float(np.linalg.norm(weights@x-q)*scale)
    converged=converged or distance<=distance_tolerance
    sides=[*natural,1-float(natural.sum())] if family.startswith('TET') else [*natural,*(1-natural)]
    inside=min(sides)>=-natural_tolerance
    if not converged or not inside:return None,'failed_inversion' if not converged else 'outside_coverage'
    _need(abs(float(weights.sum())-1)<=1e-10,'Native volume shape partition of unity failed')
    return {'weights':weights.tolist(),'natural_coordinates':natural.tolist(),'distance':distance,
            'iterations':iteration+1,'on_boundary':bool(min(sides)<=natural_tolerance)},None


def _metadata(source,target):
    required={'coordinate_units','coordinate_frame','geometry','clock','units','frame','measure','quantity','components'}
    _need(isinstance(source,dict) and isinstance(target,dict) and required<=set(source) and required<=set(target),
          'Declare reference geometry, matching clocks, quantity, units and frames')
    _need(all(source[k]==target[k] for k in required),'Volume sampling requires matching physical metadata; convert explicitly first')
    _need(source['geometry']=='reference','Volume sampling currently requires actual reference geometry')
    labels=source['components']
    _need(isinstance(labels,list) and labels and all(isinstance(label,str) and label.strip() for label in labels) and
          len(set(labels))==len(labels),'Declare unique ordered physical component labels')
    from .experiment_calibration import UNITS
    _need(UNITS.get(source['coordinate_units'],(None,))[0]=='length','Declare the shared coordinate length unit')
    _need(all(isinstance(source[k],str) and source[k].strip() and source[k].lower() not in
          ('unknown','undeclared','local','identifier','id','node_id','element_id')
          for k in ('coordinate_frame','units','frame','measure','quantity')),
          'Identifiers and undeclared/local response bases cannot be interpolated')
    _need(source['coordinate_frame']!='scalar','Coordinates require a fixed spatial frame')
    clock=source['clock']
    _need(clock is None or isinstance(clock,dict) and set(clock)=={'value','unit','semantics'} and
          type(clock['value']) in (int,float) and math.isfinite(clock['value']) and
          all(isinstance(clock[k],str) and clock[k].strip() for k in ('unit','semantics')),
          'Choose the same explicit native clock; static data uses None')
    if clock is not None and clock['semantics']=='STATIC_LOAD_PARAMETER':
        _need(clock['unit']=='1','Static load parameter is dimensionless, never physical time')
    if clock is not None and clock['semantics']=='PHYSICAL_TIME':
        _need(UNITS.get(clock['unit'],(None,))[0]=='time','Physical time requires declared time units')


def sample_volume(mesh,query,field,*,source_metadata,target_metadata,
                  distance_tolerance,natural_tolerance,max_iterations=50):
    """Sample explicit POINTS fields or CELLS owner constants on another mesh.

    mesh: node_ids/coordinates/cells; each cell has cell_id/type/node_ids in VTK
    ordering. query: node_ids/coordinates. field: association/values in the
    corresponding original node/cell row order. Native IP values are rejected.
    """
    _metadata(source_metadata,target_metadata)
    _need(isinstance(mesh,dict) and set(mesh)=={'node_ids','coordinates','cells'} and
          isinstance(query,dict) and set(query)=={'node_ids','coordinates'},'Select exact source mesh and query point rows')
    xyz=_points(mesh['node_ids'],mesh['coordinates'],'Source mesh')
    queries=_points(query['node_ids'],query['coordinates'],'Query mesh')
    _need(isinstance(field,dict) and set(field)=={'association','values'} and field['association'] in ('POINTS','CELLS'),
          'Only original POINTS fields or explicit CELLS constants are supported; native IP recovery is not performed')
    _need(source_metadata.get('association',field['association'])==field['association'],
          'The original source association differs; implicit field recovery is not performed')
    _need(type(distance_tolerance) in (int,float) and math.isfinite(distance_tolerance) and distance_tolerance>0 and
          type(natural_tolerance) in (int,float) and math.isfinite(natural_tolerance) and natural_tolerance>=0 and
          type(max_iterations) is int and 1<=max_iterations<=100,'Declare finite positive geometric tolerance and an iteration budget of 1–100')
    cells=mesh['cells'];_need(isinstance(cells,list) and cells and len(cells)*len(queries)<=4_000_000,
                           'Use a nonempty source mesh within the 4-million cell-query capacity')
    values=np.asarray(field['values'],dtype=float)
    scalar=values.ndim==1
    if scalar:values=values[:,None]
    count=len(xyz) if field['association']=='POINTS' else len(cells)
    _need(values.ndim==2 and values.shape[0]==count and 1<=values.shape[1]<=9,'Native field rows/components differ from their declared association')
    _need(len(source_metadata['components'])==values.shape[1],
          'Ordered component labels differ from the actual native field width')
    if values.shape[1]>1:_need(source_metadata['frame']==source_metadata['coordinate_frame'],
                             'Vector/tensor components require the same fixed coordinate basis')
    from vtkmodules import vtkCommonDataModel as vtk
    from vtkmodules.vtkCommonCore import vtkVersion
    lookup={n:i for i,n in enumerate(mesh['node_ids'])};prepared=[];ids=set();connectivity=set()
    for index,row in enumerate(cells):
        _need(isinstance(row,dict) and set(row)=={'cell_id','type','node_ids'} and row['type'] in FAMILIES,
              'Use explicitly ordered TET4/TET10/HEX8/HEX20 source cells')
        klass,width=FAMILIES[row['type']];nodes=row['node_ids'];identifier=row['cell_id']
        _need(type(identifier) is int and identifier>=0 and identifier not in ids and isinstance(nodes,list) and
              len(nodes)==width and len(set(nodes))==width and all(type(n) is int and n in lookup for n in nodes),
              'Source cells require unique native cell IDs and complete native node ordering')
        key=row['type'],tuple(sorted(nodes));_need(key not in connectivity,'Duplicate native source volume cells are ambiguous')
        ids.add(identifier);connectivity.add(key);cell=getattr(vtk,klass)()
        positions=[lookup[n] for n in nodes];points=xyz[positions]
        certificate=_certificate(cell,points,row['type'])
        prepared.append((row,cell,points,positions,certificate,index,_bounds(cell,points,row['type'])))
    rows=[];result=[]
    for identifier,point in zip(query['node_ids'],queries):
        candidates=[];failures=[];unverified=[]
        for row,cell,points,positions,certificate,index,bounds in prepared:
            origin,scale,lower,upper=bounds;normalized=(point-origin)/scale
            if np.any(normalized<lower-distance_tolerance/scale) or np.any(normalized>upper+distance_tolerance/scale):
                failures.append('outside_coverage');continue
            inverse,reason=_inverse(cell,points,point,row['type'],distance_tolerance,natural_tolerance,max_iterations)
            if inverse is None:
                failures.append(reason)
                # An outside Newton root proves exclusion only for the affine
                # TET4 map. Curved-map regularity covers the reference domain.
                if reason=='failed_inversion' or row['type']!='TET4':unverified.append(row['cell_id'])
                continue
            weights=np.asarray(inverse['weights']);global_weights=dict(zip(row['node_ids'],weights))
            native=values[positions] if field['association']=='POINTS' else values[index:index+1]
            sampled=weights@native if field['association']=='POINTS' else native[0]
            candidates.append((row,inverse,global_weights,sampled,certificate))
        record={'query_node_id':identifier,'coordinates':point.tolist(),'valid':False}
        if unverified:
            record.update(reason='source_cell_inversion_unverified',unverified_cell_ids=unverified,
                          candidate_cell_ids=[candidate[0]['cell_id'] for candidate in candidates])
            rows.append(record);result.append(None);continue
        if not candidates:
            record['reason']='failed_inversion' if 'failed_inversion' in failures else 'outside_coverage'
            rows.append(record);result.append(None);continue
        first=candidates[0]
        if len(candidates)>1:
            keys=set().union(*(set(candidate[2]) for candidate in candidates))
            same=(field['association']=='POINTS' and all(candidate[1]['on_boundary'] for candidate in candidates) and
                all(max(abs(first[2].get(k,0)-candidate[2].get(k,0)) for k in keys)<=1e-10 for candidate in candidates[1:]))
            if not same:
                record.update(reason='ambiguous_source_cells',candidate_cell_ids=[candidate[0]['cell_id'] for candidate in candidates])
                rows.append(record);result.append(None);continue
        row,inverse,_,sampled,certificate=first
        record.update(source_cell_id=row['cell_id'],source_cell_type=row['type'],
            source_cell_ids=[candidate[0]['cell_id'] for candidate in candidates],source_node_ids=deepcopy(row['node_ids']),
            **inverse,geometry_certificate=certificate)
        if not np.isfinite(sampled).all():record['reason']='nonfinite_source_field';result.append(None)
        else:
            record.update(valid=True,reason='inside')
            result.append(float(sampled[0]) if scalar else sampled.tolist())
        rows.append(record)
    return {'values':result,'mask':[row['valid'] for row in rows],'rows':rows,
            'source_mesh_sha256':canonical_hash(mesh),'source_field_sha256':canonical_hash({
                'association':field['association'],'shape':list(values.shape),'encoding':'little_endian_float64',
                'values_sha256':hashlib.sha256(np.asarray(values,dtype='<f8').tobytes()).hexdigest()}),
            'source_metadata':deepcopy(source_metadata),'target_metadata':deepcopy(target_metadata),
            'native_shape_runtime':{'library':'VTK','version':vtkVersion.GetVTKVersion()},
            'interpolation':'native_volume_shape','conservative_transfer':False,
            'coverage':sum(row['valid'] for row in rows)/len(rows)}
