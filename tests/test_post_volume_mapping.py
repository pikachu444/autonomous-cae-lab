"""Manufactured fields through actual VTK volume shapes; no native solve."""
from copy import deepcopy
import json
import numpy as np
import pytest
vtk=pytest.importorskip('vtk')
from caelab.post_volume_mapping import FAMILIES,sample_volume


META={'coordinate_units':'mm','coordinate_frame':'lab','geometry':'reference',
      'clock':{'value':2.75,'unit':'1','semantics':'STATIC_LOAD_PARAMETER'},
      'units':'MPa','frame':'scalar','measure':'Cauchy','quantity':'stress','components':['scalar']}


def case(family,curved=False):
    cell=getattr(vtk,FAMILIES[family][0])();natural=np.asarray(cell.GetParametricCoords()).reshape(-1,3)
    transform=np.array([[2.,.1,0.],[.2,1.3,.1],[0.,.1,1.6]])
    points=natural@transform.T+[-7.,14.,3.]
    if curved:
        points[-1]+=[.025,-.015,.02]
    ids=[31+17*i for i in range(len(points))]
    mesh={'node_ids':ids,'coordinates':points.tolist(),
          'cells':[{'cell_id':709,'type':family,'node_ids':list(ids)}]}
    locations=[[.16,.22,.19],[.21,.18,.23]]
    queries=[]
    for p in locations:
        weights=[0.]*len(points);cell.InterpolateFunctions(p,weights)
        queries.append((np.asarray(weights)@points).tolist())
    query={'node_ids':[17001,81003],'coordinates':queries}
    values=(2+points@np.array([.5,-.3,.2])).tolist()
    return mesh,query,{'association':'POINTS','values':values},natural,locations


def run(mesh,query,field,**kwargs):
    metadata=kwargs.pop('metadata',META)
    return sample_volume(mesh,query,field,source_metadata=metadata,target_metadata=deepcopy(metadata),
        distance_tolerance=1e-10,natural_tolerance=1e-10,**kwargs)


@pytest.mark.parametrize('family',FAMILIES)
@pytest.mark.parametrize('curved',[False,True])
def test_actual_native_shapes_reproduce_affine_field_and_retain_sparse_ids(family,curved):
    mesh,query,field,_,locations=case(family,curved)
    before=deepcopy((mesh,query,field));result=run(mesh,query,field)
    assert result['mask']==[True,True]
    expected=2+np.asarray(query['coordinates'])@np.array([.5,-.3,.2])
    assert result['values']==pytest.approx(expected,abs=2e-10)
    for row,location in zip(result['rows'],locations):
        assert row['source_cell_id']==709 and row['source_node_ids']==mesh['node_ids']
        assert row['natural_coordinates']==pytest.approx(location,abs=1e-9)
        assert row['geometry_certificate']['status']=='CERTIFIED_VOLUME_MAP'
        assert sum(row['weights'])==pytest.approx(1.,abs=1e-12)
    assert (mesh,query,field)==before
    assert json.loads(json.dumps(result,allow_nan=False))==result
    assert result['conservative_transfer'] is False and result['native_shape_runtime']['library']=='VTK'


@pytest.mark.parametrize('family',['TET10','HEX20'])
def test_quadratic_field_uses_all_native_midsides_without_clipping_signed_weights(family):
    mesh,query,field,natural,locations=case(family)
    field['values']=np.sum(natural*natural,axis=1).tolist()
    result=run(mesh,query,field)
    assert result['values']==pytest.approx(np.sum(np.asarray(locations)**2,axis=1),abs=1e-10)
    assert any(weight<0 for weight in result['rows'][0]['weights'])


def test_native_ids_are_joined_instead_of_assuming_value_row_order():
    mesh,query,field,_,_=case('HEX20',True);baseline=run(mesh,query,field)
    permutation=np.random.default_rng(72).permutation(len(mesh['node_ids']))
    for key in ('node_ids','coordinates'):mesh[key]=[mesh[key][i] for i in permutation]
    field['values']=[field['values'][i] for i in permutation]
    result=run(mesh,query,field)
    assert result['values']==pytest.approx(baseline['values'],abs=1e-12)
    assert result['rows'][0]['source_node_ids']==baseline['rows'][0]['source_node_ids']


def test_outside_and_ambiguous_interior_never_extrapolate_or_choose_a_cell():
    mesh,query,field,_,_=case('TET10');query['coordinates'][0]=[30.,40.,50.]
    result=run(mesh,query,field)
    assert result['mask']==[False,True] and result['values'][0] is None
    assert result['rows'][0]['reason'] in ('outside_coverage','failed_inversion')
    other=deepcopy(mesh['cells'][0]);other['cell_id']=911
    offset=50000;other['node_ids']=[n+offset for n in mesh['node_ids']]
    mesh['node_ids']+=other['node_ids'];mesh['coordinates']+=deepcopy(mesh['coordinates'])
    mesh['cells'].append(other);field['values']+=list(field['values'])
    result=run(mesh,query,field)
    assert result['mask']==[False,False] and result['rows'][1]['reason']=='ambiguous_source_cells'


@pytest.mark.parametrize('family',FAMILIES)
def test_degenerate_or_inverted_ordering_and_midside_folds_are_rejected(family):
    mesh,query,field,_,_=case(family)
    mesh['coordinates']=[[x,y,3.] for x,y,z in mesh['coordinates']]
    with pytest.raises(ValueError,match='degenerate|regularity'):run(mesh,query,field)
    mesh,query,field,_,_=case(family)
    mesh['coordinates']=[[-x,y,z] for x,y,z in mesh['coordinates']]
    with pytest.raises(ValueError,match='Inverted'):run(mesh,query,field)
    if family in ('TET10','HEX20'):
        mesh,query,field,_,_=case(family);mesh['coordinates'][-1]=[80.,-50.,20.]
        with pytest.raises(ValueError,match='regularity|Inverted'):run(mesh,query,field)


def test_cell_constants_and_vector_basis_are_explicit_and_ip_recovery_is_rejected():
    mesh,query,field,_,_=case('HEX8')
    assert run(mesh,query,{'association':'CELLS','values':[17.]})['values']==[17.,17.]
    with pytest.raises(ValueError,match='native IP'):
        run(mesh,query,{'association':'IP','values':[17.]})
    field['values']=np.column_stack((field['values'],field['values'],field['values'])).tolist()
    with pytest.raises(ValueError,match='basis'):run(mesh,query,field,metadata={**META,'components':['X','Y','Z']})


@pytest.mark.parametrize('key,value',[('coordinate_units','m'),('geometry','current'),
    ('clock',{'value':1.,'unit':'1','semantics':'STATIC_LOAD_PARAMETER'}),('units','Pa')])
def test_different_geometry_clock_or_units_require_existing_explicit_conversion(key,value):
    mesh,query,field,_,_=case('TET4');target={**META,key:value}
    with pytest.raises(ValueError,match='matching physical metadata'):
        sample_volume(mesh,query,field,source_metadata=META,target_metadata=target,
                      distance_tolerance=1e-10,natural_tolerance=1e-10)


def test_shared_face_joins_global_native_weights_but_cell_constants_remain_ambiguous():
    mesh={'node_ids':[13,29,47,88,301],
        'coordinates':[[0,0,0],[1,0,0],[0,1,0],[0,0,1],[0,0,-1]],
        'cells':[{'cell_id':6,'type':'TET4','node_ids':[13,29,47,88]},
                 {'cell_id':99,'type':'TET4','node_ids':[13,47,29,301]}]}
    query={'node_ids':[7007],'coordinates':[[.2,.3,0.]]}
    result=run(mesh,query,{'association':'POINTS','values':[0.,1.,1.,1.,-1.]})
    assert result['mask']==[True] and result['values']==pytest.approx([.5])
    assert result['rows'][0]['source_cell_ids']==[6,99]
    result=run(mesh,query,{'association':'CELLS','values':[17.,17.]})
    assert result['mask']==[False] and result['rows'][0]['reason']=='ambiguous_source_cells'


def test_missing_midside_duplicate_native_ids_and_changed_field_semantics_are_rejected():
    mesh,query,field,_,_=case('TET10');mesh['cells'][0]['node_ids'].pop()
    with pytest.raises(ValueError,match='complete native node ordering'):run(mesh,query,field)
    mesh,query,field,_,_=case('TET10');mesh['node_ids'][1]=mesh['node_ids'][0]
    with pytest.raises(ValueError,match='unique native IDs'):run(mesh,query,field)
    mesh,query,field,_,_=case('HEX20');metadata={**META,'quantity':'node_id'}
    with pytest.raises(ValueError,match='Identifiers'):
        sample_volume(mesh,query,field,source_metadata=metadata,target_metadata=deepcopy(metadata),
            distance_tolerance=1e-10,natural_tolerance=1e-10)


def test_invalid_source_value_is_retained_as_masked_without_zero_filling():
    mesh,query,field,_,_=case('HEX8');field['values'][0]=float('nan')
    result=run(mesh,query,field)
    assert result['mask']==[False,False] and result['values']==[None,None]
    assert result['rows'][0]['reason']=='nonfinite_source_field'
    json.dumps(result,allow_nan=False)


def test_another_success_cannot_hide_curved_cell_failed_inversion():
    mesh,query,field,_,_=case('TET10',True)
    mesh['cells'].insert(0,{'cell_id':33,'type':'TET4','node_ids':mesh['node_ids'][:4]})
    result=run(mesh,query,field,max_iterations=1)
    assert result['mask']==[False,False] and result['values']==[None,None]
    assert result['rows'][0]['reason']=='source_cell_inversion_unverified'
    assert result['rows'][0]['candidate_cell_ids']==[33]
    assert result['rows'][0]['unverified_cell_ids']==[709]
    full=run(mesh,query,field)
    assert full['mask']==[False,False] and full['rows'][0]['reason']=='ambiguous_source_cells'


def test_outside_curved_newton_root_is_not_a_reference_domain_exclusion_proof():
    mesh,_,field,natural,_=case('TET10',True)
    vtk_cell=vtk.vtkQuadraticTetra();weights=[0.]*10;vtk_cell.InterpolateFunctions([.4,.4,.4],weights)
    point=np.asarray(weights)@np.asarray(mesh['coordinates'])
    old=np.asarray(mesh['coordinates']);large=np.vstack((old[0],old[0]+2*(old[1:4]-old[0])))
    extra=[90011,90023,90037,90051]
    mesh['node_ids']+=extra;mesh['coordinates']+=large.tolist()
    mesh['cells'].insert(0,{'cell_id':33,'type':'TET4','node_ids':extra})
    field['values']+=(2+large@np.array([.5,-.3,.2])).tolist()
    result=run(mesh,{'node_ids':[81001],'coordinates':[point.tolist()]},field)
    assert result['mask']==[False] and result['rows'][0]['reason']=='source_cell_inversion_unverified'
    assert result['rows'][0]['candidate_cell_ids']==[33]
    assert result['rows'][0]['unverified_cell_ids']==[709]


def test_quadratic_bulge_outside_nodal_aabb_is_not_silently_excluded():
    cell=vtk.vtkQuadraticTetra();natural=np.asarray(cell.GetParametricCoords()).reshape(-1,3)
    points=natural.copy();points[:,0]+=.05*natural[:,1]**2-.04*natural[:,1]
    mesh={'node_ids':[11+13*i for i in range(10)],'coordinates':points.tolist(),
        'cells':[{'cell_id':17,'type':'TET10','node_ids':[11+13*i for i in range(10)]}]}
    location=np.array([0.,.4,.1]);query_point=location.copy();query_point[0]+=.05*.4**2-.04*.4
    assert query_point[0]<points[:,0].min()
    field={'association':'POINTS','values':(2+points@np.array([.5,-.3,.2])).tolist()}
    result=run(mesh,{'node_ids':[9007],'coordinates':[query_point.tolist()]},field)
    assert result['mask']==[True] and result['values']==pytest.approx([2+query_point@np.array([.5,-.3,.2])])


def test_ordered_component_labels_and_actual_native_width_are_required():
    mesh,query,field,_,_=case('HEX8')
    source={**META,'frame':'lab','components':['XX','YY','ZZ','XY','YZ','XZ']}
    target={**source,'components':['XX','YY','ZZ','XY','XZ','YZ']}
    field['values']=np.tile(np.arange(6.),(8,1)).tolist()
    with pytest.raises(ValueError,match='matching physical metadata'):
        sample_volume(mesh,query,field,source_metadata=source,target_metadata=target,
            distance_tolerance=1e-10,natural_tolerance=1e-10)
    with pytest.raises(ValueError,match='actual native field width'):run(mesh,query,field)
    valid=run(mesh,query,field,metadata=source)
    assert valid['values']==pytest.approx(np.tile(np.arange(6.),(2,1)))
    assert valid['source_metadata']['components']==source['components']
