from copy import deepcopy
import numpy as np
import pytest
from caelab.conservative_load_transfer import interpolation,map_load,reaction_field,TransferError


def target():
    return {'node_ids':[11,23,37,49,51,63],
            'coordinates':[[0,0,0],[2,0,0],[0,2,0],[1,0,0],[1,1,0],[0,1,0]],
            'faces':[[11,23,37,49,51,63]]}


def field(x=None):
    x=x or [[.4,.6,0],[1.,.2,0],[0.,0.,0.]]
    return reaction_field([7,19,43],x,[[1.,2.,3.],[-4.,5.,-6.],[2.,3.,4.]],
        source={'raw_field':'FORC','selected_node_ids':[7,19,43]},
        static={'step':1,'increment':3,'load_parameter':1.})


def test_transpose_sign_affine_and_arbitrary_virtual_work():
    f=field();t=target();mapped,receipt=map_load(f,t,moment_origin_mm=[3.,-2.,7.])
    H=np.asarray(receipt['H']);fs=-np.asarray(f['value']);ft=np.asarray(mapped['value'])
    assert np.allclose(ft,H.T@fs,rtol=0,atol=1e-14)
    assert receipt['R_source_N']==f['value']
    assert np.max(np.abs(H@np.asarray(t['coordinates'])-f['coordinates']))<1e-14
    u=np.random.default_rng(103).normal(size=(6,3))
    assert abs(np.sum(fs*(H@u))-np.sum(ft*u))<1e-13
    assert all(receipt['checks'][k]<1e-10 for k in ('force_error','moment_error','virtual_work_error'))
    assert f==field() and t==target()


def test_quadratic_signed_weights_are_preserved():
    H,_=interpolation([[.4,.4,0]],target())
    assert np.any(H<0)
    assert abs(H.sum()-1)<1e-14


def test_curved_in_plane_geometry_uses_six_nodes_not_linear_corner_map():
    from caelab.quadratic_surface import tri6_shape
    t=target();t['coordinates'][3]=[1.,-.12,0.];t['coordinates'][4]=[1.15,1.05,0.]
    shape=tri6_shape(.21,.34);x=(shape@np.asarray(t['coordinates'])).tolist()
    H,_=interpolation([x],t)
    assert np.max(np.abs(H[0]-shape))<1e-10


@pytest.mark.parametrize('change,match',[
    (lambda t:t['coordinates'][3].__setitem__(2,.1),'planar'),
    (lambda t:t['faces'].append(list(t['faces'][0])),'Duplicate'),
    (lambda t:t['node_ids'].append(11),'Unique'),
    (lambda t:t['coordinates'].__setitem__(3,[10.,0.,0.]),'Folded'),
])
def test_bad_target_rejected(change,match):
    t=target();change(t)
    with pytest.raises((ValueError,TransferError),match=match):map_load(field(),t,moment_origin_mm=[0,0,0])


def test_uncovered_source_does_not_extrapolate_or_zero_fill():
    with pytest.raises(TransferError,match='outside') as error:
        map_load(field([[3,3,0],[1,.2,0],[0,0,0]]),target(),moment_origin_mm=[0,0,0])
    assert error.value.receipt['status']=='FAILED'
    assert 'f_target_N' not in error.value.receipt


def test_changed_field_or_wrong_force_semantics_rejected():
    f=field();f['value'][0][0]=23.
    with pytest.raises(TransferError,match='changed'):map_load(f,target(),moment_origin_mm=[0,0,0])
    f=field();f['measure']='contact_stress'
    with pytest.raises(TransferError,match='measure'):map_load(f,target(),moment_origin_mm=[0,0,0])


def test_boundary_rejects_internal_or_foreign_faces():
    from caelab.adapters.conservative_load import boundary
    from test_dynamic_support import base_model
    m=base_model();a=boundary(m,[[1,1]])
    assert len(a['node_ids'])==6 and len(a['faces'][0])==6
    with pytest.raises(ValueError,match='foreign'):boundary(m,[[23,1]])


def test_public_validators_do_not_read_snapshot_path(monkeypatch):
    from caelab.adapters.conservative_load import ConservativeLoadAdapter,SupportReactionAdapter
    monkeypatch.setattr('caelab.adapters.conservative_load._read',lambda *a,**k:pytest.fail('public diagnostic read'))
    for adapter in (ConservativeLoadAdapter(),SupportReactionAdapter()):
        with pytest.raises(ValueError):adapter.validate_settings({'data_id':'Dpublic','snapshot_path':'C:/secret'})


def test_failed_mapping_keeps_receipt_and_never_binds_receiver(tmp_path,monkeypatch):
    from caelab.evaluation_load_mapping import bind_transfer
    from caelab import backends
    monkeypatch.setattr(backends,'get_backend',lambda *a:pytest.fail('receiver binding after rejected map'))
    row={'id':'Fload','from_stage':'Ssource','to_stage':'Starget','output':'support_reaction',
         'input':'nodal_load','mapping':'tri6_conservative_load','lag':0,
         'options':{'target':target(),'moment_origin_mm':[0,0,0]}}
    state={'transfers':[],'stages':[{'stage_id':'Ssource','iteration':0,'state':'SUCCEEDED',
                                   'attempt_id':'Asource','result_sha256':'a'*64}]}
    f=field([[3,3,0],[1,.2,0],[0,0,0]])
    with pytest.raises(TransferError):bind_transfer(row,{'backend':'unused','settings':{}},
        {'Ssource':{'execution_status':'SUCCEEDED','responses':{'support_reaction':f}}},state,0,tmp_path,
        [{'id':'Ssource','source':{'kind':'simulation'}}])
    assert state['transfers'][0]['status']=='FAILED'
    assert (tmp_path/'transfers/i0000-Fload.json').is_file()


def test_declaration_validation_does_not_construct_H(monkeypatch):
    from caelab import conservative_load_transfer
    from caelab.evaluation_load_mapping import validate_options
    monkeypatch.setattr(conservative_load_transfer,'interpolation',lambda *a:pytest.fail('H during metadata validation'))
    assert validate_options({'target':target(),'moment_origin_mm':[0,0,0]})['target']==target()


def user_receiver():
    from test_dynamic_support import base_model
    from caelab.contact_steps import default_program
    model=base_model();model['conditions'][0].update(object_id='FixtureFeet37',label='고정 다리')
    model['conditions'][1].update(object_id='ActuatorSideLoad',label='작동기 하중')
    model['step'].update(period=2.75,initial=.25,maximum=.5)
    model['analysis_steps']=default_program(model['step'],model['conditions'])
    stage=model['analysis_steps']['steps'][0]
    stage.update(id='UserSettleStage',label='사용자 정적 단계',output_frequency=7)
    stage['curves'][0]['points']=[[0.,0.],[.9,2.],[2.75,7.5]]
    return model


def mapped_receiver(model,force=-3.):
    from caelab.adapters.conservative_load import boundary
    surface=boundary(model,[[1,2]])
    return dict(kind='field',unit='N',component='VECTOR',association='POINTS',
        measure='applied_nodal_force',frame='global_cartesian',coordinate_units='mm',
        node_ids=surface['node_ids'],coordinates=surface['coordinates'],
        value=[[0.,0.,force if n==4 else 0.] for n in surface['node_ids']],
        source={'job_id':'JuserChosenResult'},mapping='tri6_conservative_load',receipt_sha256='a'*64)


def test_receiver_preserves_user_conditions_loads_and_authored_static_curves():
    from caelab.adapters.conservative_load import bind_receiver_model
    from caelab.contact_steps import compile_program
    original=user_receiver();before=deepcopy(original)
    bound=bind_receiver_model(original,mapped_receiver(original),[[1,2]])
    assert original==before
    assert bound['conditions'][:-1]==before['conditions']
    assert bound['step']==before['step'] and bound['output']==before['output']
    stage=bound['analysis_steps']['steps'][0];old=before['analysis_steps']['steps'][0]
    assert {k:v for k,v in stage.items() if k!='curves'}=={k:v for k,v in old.items() if k!='curves'}
    assert stage['curves'][:-1]==old['curves']
    assert stage['curves'][-1]['points']==[[0,0],[2.75,1.]]
    assert bound['loads']==[{'node_id':4,'component':3,'force_N':-13.}]
    assert compile_program(bound['analysis_steps'],bound['conditions'])[0]['loads'][4,3][-1]==[2.75,-10.5]
    assert bound['conservative_load_binding']['original_loads']==before['loads']


def test_receiver_equilibrium_includes_preserved_authored_external_load():
    from caelab.adapters.conservative_load import bind_receiver_model,receiver_equilibrium
    original=user_receiver();bound=bind_receiver_model(original,mapped_receiver(original),[[1,2]])
    static={'step':1,'increment':9,'load_parameter':2.75}
    reactions={1:[0.,0.,0.],2:[0.,0.,10.5],3:[0.,0.,0.]}
    balance=receiver_equilibrium(bound,reactions,static=static)
    assert balance['applied_force_N']==[0.,0.,-10.5]
    assert balance['force_error']==0. and balance['moment_error']==0.
    reactions[2][2]=3.
    assert receiver_equilibrium(bound,reactions,static=static)['force_error']>balance['limit']


def test_receiver_nonzero_import_on_prescribed_dof_is_supported_boundary_error():
    from caelab.adapters.conservative_load import bind_receiver_model
    model=user_receiver();value=mapped_receiver(model)
    value['value'][0]=[1.,0.,0.]
    with pytest.raises(ValueError):
        bind_receiver_model(model,value,[[1,2]])


def test_receiver_foreign_selection_or_nonfinite_force_cannot_bind():
    from caelab.adapters.conservative_load import bind_receiver_model
    model=user_receiver();value=mapped_receiver(model);value['coordinates'][0][0]+=1
    with pytest.raises(ValueError,match='differs'):bind_receiver_model(model,value,[[1,2]])
    value=mapped_receiver(model);value['value'][0][0]=float('nan')
    with pytest.raises(ValueError,match='incomplete'):bind_receiver_model(model,value,[[1,2]])


def test_retained_nonunit_static_coordinate_is_not_relabelled_time():
    from caelab.storage import canonical_hash
    f=field();f['static']={'step':1,'increment':9,'load_parameter':2.75}
    f['capture_sha256']=canonical_hash({k:v for k,v in f.items() if k!='capture_sha256'})
    mapped,receipt=map_load(f,target(),moment_origin_mm=[3.,-2.,7.])
    assert receipt['checks']['virtual_work_error']<1e-10
    assert f['static']['load_parameter']==2.75 and mapped['unit']=='N'
