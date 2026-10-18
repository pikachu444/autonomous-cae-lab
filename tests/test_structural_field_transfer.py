"""Detached TR-U mathematics/identity tests; no source or receiver solver runs."""
from copy import deepcopy
import numpy as np
import pytest

from caelab.post_spatial_mapping import tetra10_boundary,invert_tri6,selected_boundary
from caelab.structural_field_transfer import prepare_transfer,TransferError,_consistent_boundary_hit
from caelab.quadratic_surface import tri6_shape
from examples.structural_u_transfer import subdivided_receiver,transfer_definition,EDGES


def source(matrix=None,translation=None):
    corners=np.array([[0.,0.,0.],[10.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
    points=np.vstack((corners,[(corners[a]+corners[b])/2 for a,b in EDGES]))
    matrix=np.asarray(matrix if matrix is not None else np.eye(3)*.0005)
    translation=np.asarray(translation if translation is not None else [0.,0.,0.])
    return {'node_ids':list(range(1,11)),'coordinates':points.tolist(),
        'elements':[{'element_id':1,'type':'C3D10','node_ids':list(range(1,11))}],
        'values':(points@matrix.T+translation).tolist(),'valid_mask':[True]*10,
        'units':{'position':'mm','displacement':'mm'},'coordinate_frame':'source_global','geometry':'fixed_reference',
        'static':{'step':1,'increment':1,'load_parameter':1.},
        'axis':{'name':'load_parameter','semantics':'STATIC_LOAD_PARAMETER','unit':'1'},
        'source':{'kind':'MANUFACTURED_TEST_ONLY'}}


@pytest.mark.parametrize('matrix,translation',[
    (np.zeros((3,3)),[.1,-.2,.3]),
    ([[0.,-.002,.001],[.002,0.,-.003],[-.001,.003,0.]],[0.,0.,0.]),
    ([[.001,.002,-.001],[.003,-.001,.0005],[.0002,.0008,.002]],[.02,-.01,.03])])
def test_different_mesh_translation_infinitesimal_rotation_and_affine(matrix,translation):
    field=source(matrix,translation);receiver=subdivided_receiver(field);original=deepcopy((field,receiver))
    result=prepare_transfer(field,receiver,transfer_definition(field))
    assert result['status']=='READY' and len(result['boundary_dofs'])==102 and all(result['mask'])
    assert len(receiver['node_ids'])==35 and len(receiver['boundary_node_ids'])==34
    assert set(receiver['node_ids'])-set(receiver['boundary_node_ids'])=={35}
    coordinates=dict(zip(receiver['node_ids'],receiver['coordinates']))
    for row in result['rows']:
        expected=np.asarray(matrix)@coordinates[row['node_id']]+translation
        np.testing.assert_allclose(row['displacement_mm'],expected,rtol=1e-12,atol=1e-12)
    assert {row['shared_support']['kind'] for row in result['rows']}=={'single_face','quadratic_edge','corner_vertex'}
    assert any(weight<0 for row in result['rows'] for match in row['source_matches'] for weight in match['weights'])
    assert (field,receiver)==original and result['conservative_transfer'] is False


def test_length_and_proper_frame_rotation_once_without_translating_u():
    field=source(np.zeros((3,3)),[1.,2.,3.]);receiver=subdivided_receiver(field)
    r=np.array([[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]])
    receiver['coordinates']=(np.asarray(receiver['coordinates'])@r.T+[3.,-2.,1.]).tolist()
    receiver['coordinate_frame']='target_global';receiver['components']=[1,3]
    definition=transfer_definition(field);definition.update(rotation=r.tolist(),translation=[3.,-2.,1.])
    field['coordinates']=(np.asarray(field['coordinates'])*.001).tolist()
    field['values']=(np.asarray(field['values'])*.001).tolist();field['units']={'position':'m','displacement':'m'}
    result=prepare_transfer(field,receiver,definition)
    for row in result['rows']:np.testing.assert_allclose(row['displacement_mm'],[-2.,1.,3.],atol=1e-12,rtol=0)
    assert len(result['boundary_dofs'])==68 and {row['component'] for row in result['boundary_dofs']}=={1,3}


def test_curved_tri6_inverse_and_quadratic_trace_keep_signed_weights():
    points=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[.5,0.,.08],[.5,.5,.06],[0.,.5,.04]])
    uv=np.array([.22,.31]);point=tri6_shape(*uv)@points
    inverse=invert_tri6(points,point,distance_tolerance=1e-12,natural_tolerance=1e-12,max_iterations=30)
    np.testing.assert_allclose(inverse['natural_coordinates'],uv,atol=1e-12,rtol=0)
    natural=np.array([[0.,0.],[1.,0.],[0.,1.],[.5,0.],[.5,.5],[0.,.5]])
    values=natural[:,0]**2+2*natural[:,0]*natural[:,1]+3*natural[:,1]**2
    assert np.dot(inverse['weights'],values)==pytest.approx(uv[0]**2+2*uv[0]*uv[1]+3*uv[1]**2,abs=1e-12)
    assert min(inverse['weights'])<0
    assert invert_tri6(points,point+[0.,0.,.1],distance_tolerance=1e-12,natural_tolerance=1e-12,max_iterations=30) is None


@pytest.mark.parametrize('mutation',['outside','missing_mask','missing_midside','wrong_static','improper_rotation','physical_time'])
def test_essential_missing_or_invalid_input_cannot_prepare_partial_bcs(mutation):
    field=source();receiver=subdivided_receiver(field);definition=transfer_definition(field)
    if mutation=='outside':receiver['coordinates']=(np.asarray(receiver['coordinates'])+[0.,0.,2.]).tolist()
    elif mutation=='missing_mask':field['valid_mask'][4]=False
    elif mutation=='missing_midside':receiver['boundary_node_ids'].remove(5)
    elif mutation=='wrong_static':definition['source_static']['increment']=2
    elif mutation=='improper_rotation':definition['rotation'][0][0]=-1
    elif mutation=='physical_time':field['axis']={'name':'time','unit':'s','semantics':'PHYSICAL_TIME'}
    original=deepcopy((field,receiver,definition))
    with pytest.raises(TransferError) as caught:prepare_transfer(field,receiver,definition)
    assert caught.value.receipt['status']=='FAILED' and caught.value.receipt['boundary_dofs']==[]
    assert (field,receiver,definition)==original
    if mutation in ('outside','missing_mask'):assert False in caught.value.receipt['mask']


@pytest.mark.parametrize('mutation',['inverted','degenerate','swapped_midsides','duplicate_cell','interior_face'])
def test_bad_ordered_owner_topology_and_geometry_fail_closed(mutation):
    field=source()
    if mutation=='inverted':field['elements'][0]['node_ids'][1:3]=[3,2]
    elif mutation=='degenerate':field['coordinates'][3]=field['coordinates'][0]
    elif mutation=='swapped_midsides':field['coordinates'][4],field['coordinates'][5]=field['coordinates'][5],field['coordinates'][4]
    elif mutation=='duplicate_cell':field['elements'].append({**deepcopy(field['elements'][0]),'element_id':2})
    else:
        receiver=subdivided_receiver(field)
        catalog={(f['element_id'],f['face']) for f in tetra10_boundary(receiver['node_ids'],receiver['coordinates'],receiver['elements'])}
        interior=next([e['element_id'],side] for e in receiver['elements'] for side in (1,2,3,4) if (e['element_id'],side) not in catalog)
        with pytest.raises(ValueError,match='not an exterior'):selected_boundary(receiver['node_ids'],receiver['coordinates'],receiver['elements'],[interior])
        return
    if mutation=='swapped_midsides':
        with pytest.raises(ValueError):invert_tri6(np.asarray(field['coordinates'])[[0,2,1,6,5,4]],[.2,.2,0.],distance_tolerance=1e-10,natural_tolerance=1e-12,max_iterations=30)
    else:
        with pytest.raises(ValueError):tetra10_boundary(field['node_ids'],field['coordinates'],field['elements'])


@pytest.mark.parametrize('kind',['unrelated','midside_only','negative_offedge','not_an_edge'])
def test_multiple_hits_require_actual_corner_or_quadratic_edge_and_absolute_weight_agreement(kind):
    a={'element_id':1,'face':1,'node_ids':[1,2,3,4,5,6],'weights':[.5,.5,0.,0.,0.,0.]}
    b={'element_id':2,'face':1,'node_ids':[1,2,7,4,8,9],'weights':[.5,.5,0.,0.,0.,0.]}
    if kind=='unrelated':b['node_ids']=[11,12,13,14,15,16]
    elif kind=='midside_only':b['node_ids']=[11,12,13,4,15,16]
    elif kind=='negative_offedge':a['weights'][2]=-.01
    elif kind=='not_an_edge':b['node_ids']=[1,2,3,10,11,12]
    with pytest.raises(ValueError,match='AMBIGUOUS_SOURCE_FACES'):_consistent_boundary_hit([a,b],1e-11)


def test_shared_edge_ids_must_preserve_corner_and_midside_roles():
    a={'element_id':1,'face':1,'node_ids':[1,2,3,4,5,6],'weights':[.5,.5,0.,0.,0.,0.]}
    b={'element_id':2,'face':1,'node_ids':[1,4,7,2,8,9],'weights':[.5,0.,0.,.5,0.,0.]}
    with pytest.raises(ValueError,match='AMBIGUOUS_SOURCE_FACES'):_consistent_boundary_hit([a,b],1e-11)


def test_shared_negative_weight_difference_uses_absolute_value():
    a={'element_id':1,'face':1,'node_ids':[1,2,3,4,5,6],'weights':[.5,.5,0.,0.,0.,0.]}
    b={'element_id':2,'face':1,'node_ids':[1,2,7,4,8,9],'weights':[.49,.51,0.,0.,0.,0.]}
    with pytest.raises(ValueError,match='weights disagree'):_consistent_boundary_hit([a,b],1e-11)


def test_cancellation_uses_existing_execution_control_without_mutating_inputs(monkeypatch):
    from caelab.execution_control import ExecutionCancelled
    field=source();receiver=subdivided_receiver(field);original=deepcopy((field,receiver))
    def cancelled():raise ExecutionCancelled('controlled caller cancellation')
    monkeypatch.setattr('caelab.structural_field_transfer.check_cancelled',cancelled)
    with pytest.raises(ExecutionCancelled):prepare_transfer(field,receiver,transfer_definition(field))
    assert (field,receiver)==original


def test_coincident_unrelated_source_surfaces_fail_despite_equal_u():
    field=source();receiver=subdivided_receiver(field)
    field['node_ids']+=list(range(11,21));field['coordinates']+=deepcopy(field['coordinates'])
    field['values']+=deepcopy(field['values']);field['valid_mask']+=[True]*10
    field['elements'].append({'element_id':2,'type':'C3D10','node_ids':list(range(11,21))})
    with pytest.raises(TransferError) as caught:prepare_transfer(field,receiver,transfer_definition(field))
    assert not any(caught.value.receipt['mask'])
    assert all('AMBIGUOUS_SOURCE_FACES' in row['error'] for row in caught.value.receipt['rows'])
    assert caught.value.receipt['boundary_dofs']==[]


def test_an_interior_submodel_boundary_is_not_admitted_as_source_volume_support():
    field=source();receiver=subdivided_receiver(field)
    # Entire small tetra lies strictly inside the actual source tetra. It is
    # deliberately not on any selected source reference face.
    receiver['coordinates']=(np.asarray(receiver['coordinates'])*.2+[1.,.1,.1]).tolist()
    with pytest.raises(TransferError) as caught:prepare_transfer(field,receiver,transfer_definition(field))
    assert caught.value.receipt['boundary_dofs']==[]
    assert caught.value.receipt['invalid_required_node_ids']==list(range(1,35))
    assert all('NO_SOURCE_BOUNDARY_SUPPORT' in row['error'] for row in caught.value.receipt['rows'])
