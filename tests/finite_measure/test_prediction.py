"""Deterministic accepted-record contract fixtures; NOT a constitutive execution."""
from copy import deepcopy
import json,math
import numpy as np
import pytest
from caelab.finite_measure_prediction import comparison_extension,derive,row_metadata,request
from caelab.numerical import _experiment,_aligned,_fit_curve,EvaluationFailed
from caelab.material_test import physical_residual,measured_protocol
from caelab.finite_measure_protocol import recipe
from caelab.numerical_candidate_detail import experiment_snapshot,trial_detail
from caelab.storage import canonical_hash


def records():
    gradients=[np.eye(3),np.diag([1.25,math.sqrt(.88),math.sqrt(.88)]),np.diag([1.15,.95,.95])]
    stresses=[np.zeros((3,3)),np.diag([50.,0.,0.]),np.diag([20.,0.,0.])]
    increments=[dict(increment=i,time=float(i),time_unit='s',deformation_gradient=F.tolist(),gradient_unit='1',
        stress=P.tolist(),stress_unit='MPa',stress_measure='first_Piola',frame='material_cartesian',
        residual=0.,tolerance=1e-8,status='SUCCEEDED') for i,(F,P) in enumerate(zip(gradients,stresses))]
    response=dict(kind='series',value=[0.,50.,20.],unit='MPa',component='xx',location='material_point',
        reduction='none',measure='first_Piola',frame='material_cartesian',axes=[dict(name='time',unit='s',values=[0.,1.,2.])])
    return dict(execution_status='SUCCEEDED',responses={'stress_xx':response},diagnostics={
        'controller':'TEST_ONLY_ACCEPTED_RECORD_CONTRACT_NOT_LAW','constitutive_increments':increments,'accepted_count':3,'requested_count':3})


def experiment(raw):
    obs=deepcopy(raw['responses']['stress_xx']);obs.update(measure='finite_Cauchy',value=[0.,55.,20.])
    return dict(id='Axial',role='fit',response='stress_xx',observations=obs,weight=4.,scale=2.,
        mask=[True,True,True],sample_weights=[1.,2.,1.],settings={},extensions={'finite_measure':comparison_extension('x')})


def test_actual_F_J_separate_native_and_physical_vs_scaled_residual():
    raw=records();digest=canonical_hash(raw);e=experiment(raw);ex=_experiment(e)
    aligned,scaled=_aligned(raw,ex)
    expected=np.array([0.,50*1.25/1.1,20/(.95*.95)])
    assert aligned==pytest.approx(expected)
    delta=expected-np.array(e['observations']['value'])
    assert scaled==pytest.approx(delta*math.sqrt(4/3)/2*np.sqrt([1,2,1]))
    curve=_fit_curve(ex,raw);x,physical=physical_residual(curve)
    assert physical==pytest.approx(delta);assert x==[0.,1.,2.]
    assert curve['prediction_metadata']['measure']=='finite_Cauchy'
    assert curve['prediction_metadata']['extensions']['finite_measure']['payload']['raw_evaluation_sha256']==digest
    assert canonical_hash(raw)==digest and raw['responses']['stress_xx']['measure']=='first_Piola'
    # Same supplied P, but the next candidate has different ACTUAL lateral F/J.
    other=deepcopy(raw);other['diagnostics']['constitutive_increments'][1]['deformation_gradient']=[[1.25,0,0],[0,.9,0],[0,0,.9]]
    assert _aligned(other,ex)[0][1]==pytest.approx(50/.81)
    assert _aligned(other,ex)[0][1]!=pytest.approx(expected[1])
    snap=experiment_snapshot(e);detail=trial_detail(snap,raw,origin={'fixture':'contract only'})
    assert detail['execution_status']=='SUCCEEDED' and detail['raw_evaluation']==raw
    row=row_metadata(curve,1.,'s');assert row['actual_J']==pytest.approx(1.1)
    assert row_metadata(curve,.5,'s')['actual_deformation_gradient'] is None


@pytest.mark.parametrize('change', ['missing_F','no_increments','bad_time','bad_component','bad_unit','no_convergence',
                                   'residual_missing','failed_state','wrong_count','noncoaxial','singular'])
def test_prediction_no_fallback_or_convergence_bypass(change):
    raw=records();row=raw['diagnostics']['constitutive_increments'][1]
    if change=='missing_F':row.pop('deformation_gradient')
    elif change=='no_increments':raw['diagnostics'].pop('constitutive_increments')
    elif change=='bad_time':row['time']=1.01
    elif change=='bad_component':raw['responses']['stress_xx']['component']='yy'
    elif change=='bad_unit':row['stress_unit']='Pa'
    elif change=='no_convergence':row['residual']=1e-7
    elif change=='residual_missing':row.pop('residual')
    elif change=='failed_state':row['status']='FAILED'
    elif change=='wrong_count':raw['diagnostics']['accepted_count']=4
    elif change=='noncoaxial':row['deformation_gradient'][0][1]=.1
    elif change=='singular':row['deformation_gradient'][1][1]=0.
    with pytest.raises((ValueError,TypeError)):
        derive(raw,'stress_xx',comparison_extension('x')['payload'])


def test_strict_measure_unit_frame_component_time_and_explicit_conversion():
    raw=records();e=experiment(raw)
    no=deepcopy(e);no.pop('extensions')
    with pytest.raises(ValueError,match='measure mismatch'):_aligned(raw,_experiment(no))
    for key,value in [('unit','kPa'),('frame','spatial_cartesian'),('component','yy'),('measure','infinitesimal_Cauchy')]:
        wrong=deepcopy(e);wrong['observations'][key]=value
        with pytest.raises(ValueError):_aligned(raw,_experiment(wrong))
    wrong=deepcopy(e);wrong['observations']['axes'][0]['unit']='ms'
    with pytest.raises(ValueError,match='axis'):_aligned(raw,_experiment(wrong))
    wrong=deepcopy(e);wrong['observations']['axes'][0]['values']=[0.,1.,3.]
    with pytest.raises(ValueError,match='support'):_aligned(raw,_experiment(wrong))
    wrong=deepcopy(e);wrong['extensions']['finite_measure']['payload']['observed_J']=1.
    with pytest.raises(ValueError,match='수락'):_experiment(wrong)


def test_failed_prefix_read_only_never_score():
    raw=records();raw['execution_status']='FAILED';raw['diagnostics']['failed_increment']={'increment':3,'message':'original failure'}
    prefix=derive(raw,'stress_xx',comparison_extension('x')['payload'],allow_failed_prefix=True)
    assert prefix['extensions']['finite_measure']['payload']['failure_prefix_only']
    ex=_experiment(experiment(raw));curve=_fit_curve(ex,raw)
    assert curve['execution_status']=='FAILED' and 'prediction' not in curve
    with pytest.raises(EvaluationFailed):_aligned(raw,ex)
    assert raw['diagnostics']['failed_increment']['message']=='original failure'


def test_existing_compiler_free_fixed_prescribed_y_axis_and_raw_invalid():
    base=dict(model='neo_hooke',parameters={'mu':1.,'lmbda':5.},stress_unit='MPa',time_unit='s',
        time=[0.,1.,2.],deformation_gradient=[np.eye(3).tolist()]*3)
    driver=dict(kind='series',value=[0.,math.log(1.2),math.log(1.1)],unit='1',component='yy',location='material_point',
        reduction='none',measure='log_strain',frame='material_cartesian',axes=[dict(name='time',unit='s',values=[0.,1.,2.])])
    result={'execution_status':'SUCCEEDED','responses':{'driver':driver}}
    free=measured_protocol(base,result,recipe('driver','y',lateral='free'))
    assert free['deformation_gradient'][1][1][1]==pytest.approx(1.2)
    assert set(free['boundary_control']['stress_components'])=={'xx','zz'}
    from caelab.material_control import DEFAULT_SOLVER
    assert free['boundary_control']['solver']==DEFAULT_SOLVER
    fixed=measured_protocol(base,result,recipe('driver','y',lateral='fixed'))
    assert 'boundary_control' not in fixed
    specified=measured_protocol(base,result,recipe('driver','y',lateral='prescribed',lateral_22=.9,lateral_33=.95))
    assert np.diag(specified['deformation_gradient'][1])==pytest.approx([.9,1.2,.95])
    invalid=recipe('driver','y',lateral='prescribed',lateral_22='1e',lateral_33=.95)
    with pytest.raises(ValueError):measured_protocol(base,result,invalid)
    assert invalid['lateral_22']=='1e'
    bad=deepcopy(result);bad['responses']['driver']['has_calculation_gaps']=True
    with pytest.raises(ValueError):measured_protocol(base,bad,recipe('driver','y',lateral='free'))
