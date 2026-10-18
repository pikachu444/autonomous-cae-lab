"""Pure reference-boundary U -> prescribed-U preparation, never a deck writer."""
from copy import deepcopy
import math
import numpy as np

from .execution_control import check_cancelled
from .post_comparison import transform_points, transform_values
from .post_spatial_mapping import selected_boundary, invert_tri6
from .storage import canonical_hash


class TransferError(ValueError):
    def __init__(self,message,receipt=None):
        super().__init__(message)
        self.receipt=deepcopy(receipt or {})
        self.receipt.update(status='FAILED',error=message,boundary_dofs=[])


def _mesh(value):
    ids=value.get('node_ids');points=np.asarray(value.get('coordinates'),dtype=float)
    if (not isinstance(ids,list) or not ids or any(type(n) is not int or n<=0 for n in ids)
            or len(set(ids))!=len(ids) or points.shape!=(len(ids),3) or not np.isfinite(points).all()
            or not isinstance(value.get('coordinate_frame'),str) or not value['coordinate_frame'].strip()
            or not isinstance(value.get('units'),dict)):
        raise ValueError('Use complete native node IDs, finite reference XYZ, length units and an explicit frame.')
    if value.get('geometry','fixed_reference')!='fixed_reference':
        raise ValueError('Prescribed-U transfer requires undeformed reference geometry.')
    return ids,points


def _consistent_boundary_hit(hits, tolerance):
    """A shared topological edge/vertex may have several identical traces.

    Agreement of values alone does not admit overlapping, unrelated surfaces.
    Original signed quadratic weights are retained without clipping/rescaling.
    """
    if len(hits)==1:return hits[0],{'kind':'single_face'}
    shared=set.intersection(*(set(row['node_ids']) for row in hits))
    if not shared:raise ValueError('AMBIGUOUS_SOURCE_FACES: unrelated exterior faces contain the same target point.')
    if len(shared)==1:
        if not all(shared<=set(row['node_ids'][:3]) for row in hits):
            raise ValueError('AMBIGUOUS_SOURCE_FACES: a shared midside ID alone is not a conforming corner vertex.')
        kind='corner_vertex'
    elif len(shared)==3:
        def edge_keys(row):
            a,b,c,ab,bc,ca=row['node_ids']
            return {(tuple(sorted(pair)),middle) for pair,middle in (((a,b),ab),((b,c),bc),((c,a),ca))
                    if shared=={*pair,middle}}
        common_edges=set.intersection(*(edge_keys(row) for row in hits))
        if len(common_edges)!=1:
            raise ValueError('AMBIGUOUS_SOURCE_FACES: the shared IDs are not one actual quadratic edge.')
        kind='quadratic_edge'
    else:
        raise ValueError('AMBIGUOUS_SOURCE_FACES: shared source support is not a conforming edge or corner vertex.')
    maps=[dict(zip(row['node_ids'],row['weights'])) for row in hits]
    if any(abs(weight)>tolerance for weights in maps for node,weight in weights.items() if node not in shared):
        raise ValueError('AMBIGUOUS_SOURCE_FACES: multiple face interiors overlap beyond a common edge/vertex.')
    if any(abs(weights.get(node,0.)-maps[0].get(node,0.))>tolerance for weights in maps[1:] for node in shared):
        raise ValueError('AMBIGUOUS_SOURCE_FACES: common boundary interpolation weights disagree.')
    return min(hits,key=lambda row:(row['element_id'],row['face'])),{
        'kind':kind,'node_ids':sorted(shared),'weight_tolerance':tolerance,
        'verification':'topology_confirmed_support_and_numerically_equivalent_signed_weights'}


def prepare_transfer(field, receiver, definition):
    """Return preview+exact boundary_dofs, or TransferError with retained masks.

    ``boundary_faces`` is an actual target exterior element/side selection.
    Every node on every selected TRI6 face is essential, including midsides.
    The existing receiver writer retains BC/amplitude/conflict responsibility.
    """
    receipt={'status':'PREPARING','source':deepcopy(field.get('source')),'definition':deepcopy(definition),
             'units':deepcopy(receiver.get('units')),'source_frame':field.get('coordinate_frame'),
             'receiver_frame':receiver.get('coordinate_frame'),'rows':[],'mask':[],
             'boundary_dofs':[],'conservative_transfer':False,'qualification':'UNKNOWN','engineering_valid':False}
    try:
        required={'source_faces','rotation','translation','distance_tolerance','natural_tolerance',
                  'weight_tolerance','max_iterations','source_static'}
        if not isinstance(definition,dict) or set(definition)!=required:
            raise ValueError('Explicit source faces, frame/unit transform, inverse tolerances/budget and source static frame are required.')
        if definition['source_static']!=field.get('static') or field.get('axis')!={'name':'load_parameter','semantics':'STATIC_LOAD_PARAMETER','unit':'1'}:
            raise ValueError('Select the exact native static load parameter; physical time interpolation is unsupported.')
        weight_tolerance=definition['weight_tolerance']
        if type(weight_tolerance) not in (int,float) or not math.isfinite(weight_tolerance) or weight_tolerance<0:
            raise ValueError('Use an explicit finite nonnegative shared-boundary weight tolerance.')
        source_ids,source_points=_mesh(field);target_ids,target_points=_mesh(receiver)
        values=np.asarray(field.get('values'),dtype=float);valid=field.get('valid_mask')
        if (values.shape!=(len(source_ids),3) or not np.isfinite(values).all()
                or not isinstance(valid,list) or len(valid)!=len(source_ids) or any(type(v) is not bool for v in valid)):
            raise ValueError('All three source U components and an explicit original boolean validity mask are required.')
        source_faces=selected_boundary(source_ids,source_points,field['elements'],definition['source_faces'])
        target_faces=selected_boundary(target_ids,target_points,receiver['elements'],receiver.get('boundary_faces'))
        from .quadratic_surface import regularity
        target_index={n:i for i,n in enumerate(target_ids)}
        for face in target_faces:
            points=target_points[[target_index[n] for n in face['node_ids']]]
            regularity(points-points[0])
        components=receiver.get('components')
        if not isinstance(components,list) or not components or len(set(components))!=len(components) or any(type(v) is not int or v not in (1,2,3) for v in components):
            raise ValueError('Explicit distinct receiver displacement DOFs1,2,3 are required.')
        required_nodes=sorted({n for face in target_faces for n in face['node_ids']})
        if receiver.get('boundary_node_ids',required_nodes)!=required_nodes:
            raise ValueError('The essential selected TRI6 boundary node set is incomplete, including its midside nodes.')
        xyz=transform_points(source_points,field['units']['position'],receiver['units']['position'],definition['rotation'],definition['translation'])
        u=transform_values(values,{'layout':{'kind':'vector','components':['x','y','z']},
            'units':field['units']['displacement'],'quantity':'displacement'},
            {'units':receiver['units']['displacement']},definition['rotation'])
        if receiver['units']['displacement']!='mm':
            raise ValueError('The current native prescribed displacement receiver requires explicit mm output.')
        source_index={n:i for i,n in enumerate(source_ids)};target_index={n:i for i,n in enumerate(target_ids)}
        receipt.update(target_node_ids=required_nodes,boundaries=deepcopy(target_faces),components=deepcopy(components),
                       receiver_sha256=canonical_hash(receiver),static=deepcopy(field['static']))
        invalid=[];dofs=[]
        for node in required_nodes:
            check_cancelled();point=target_points[target_index[node]];hits=[];missing_support=False
            for face in source_faces:
                check_cancelled();indices=[source_index[n] for n in face['node_ids']]
                inverse=invert_tri6(xyz[indices],point,distance_tolerance=definition['distance_tolerance'],
                    natural_tolerance=definition['natural_tolerance'],max_iterations=definition['max_iterations'])
                if inverse is None:continue
                hit={**deepcopy(face),**inverse}
                if not all(valid[i] for i in indices):missing_support=True
                hits.append(hit)
            row={'node_id':node,'position':point.tolist(),'source_matches':hits,'valid':False}
            try:
                if not hits:raise ValueError('NO_SOURCE_BOUNDARY_SUPPORT: target is outside the explicitly selected reference surface.')
                if missing_support:raise ValueError('MISSING_SOURCE_COMPONENT_SUPPORT: a containing source face has invalid original nodal data.')
                chosen,shared_support=_consistent_boundary_hit(hits,weight_tolerance)
                mapped=np.asarray(chosen['weights'])@u[[source_index[n] for n in chosen['node_ids']]]
                if not np.isfinite(mapped).all():raise ValueError('NONFINITE_TRANSFER: no prescribed displacement was prepared.')
                row.update(valid=True,displacement_mm=mapped.tolist(),selected_source_face=[chosen['element_id'],chosen['face']],
                           shared_support=shared_support)
                dofs.extend({'node_id':node,'component':component,'value_mm':float(mapped[component-1])} for component in components)
            except ValueError as error:
                row['error']=str(error);invalid.append(node)
            receipt['rows'].append(row);receipt['mask'].append(row['valid'])
        receipt['invalid_required_node_ids']=invalid
        if invalid:raise TransferError('Essential receiver nodes lack unambiguous valid source boundary support: '+str(invalid),receipt)
        receipt.update(status='READY',boundary_dofs=dofs)
        return receipt
    except TransferError:raise
    except (ValueError,KeyError,TypeError,np.linalg.LinAlgError) as error:
        raise TransferError(str(error),receipt) from error
