"""Small independent constitutive checks. No solver/package stand-in is FE evidence."""
from copy import deepcopy
import numpy as np
import pytest
from plugins.material_point import law_native as law
from plugins.material_point import drucker_prager as dp, single_branch_native as sls
from plugins.material_point.law_native_tensors import kelvin,tensor,stiffness
from plugins.material_point.law_native_history import evaluate_history,tangent_probe
from caelab.storage import canonical_hash


def independent_trial(p,e):
    """Physical tensor Hooke + scalar p-q radial equations, no production update."""
    G=p['E']/(2*(1+p['nu']));K=p['E']/(3*(1-2*p['nu']))
    eps=np.array([[e[0],e[3]/np.sqrt(2),e[4]/np.sqrt(2)],
                  [e[3]/np.sqrt(2),e[1],e[5]/np.sqrt(2)],
                  [e[4]/np.sqrt(2),e[5]/np.sqrt(2),e[2]]])
    dev=eps-np.trace(eps)*np.eye(3)/3
    s=2*G*dev;p_trial=-K*np.trace(eps);q=np.sqrt(1.5*np.sum(s*s))
    dg=max(0.,(q-p['alpha']*p_trial-p['k0'])/(3*G+p['alpha']*K*p['beta']+p['H']))
    assert q-3*G*dg>0
    expected=(1-3*G*dg/q)*s-(p_trial+K*p['beta']*dg)*np.eye(3)
    return expected,dg,p_trial,q


@pytest.mark.parametrize('strain',[
    [.005,0,0,0,0,0],[-.005,0,0,0,0,0],[-.003,-.006,-.006,0,0,0],
    [0,0,0,.01,0,0],[.002,-.001,0,.003,.001,-.002]])
def test_dp_independent_pq(strain):
    p=law.default_settings()['parameters'];initial=dp.state();before=deepcopy(initial)
    expected,dg,ptr,qtr=independent_trial(p,strain)
    actual=dp.integrate(p,initial,strain,1.)
    np.testing.assert_allclose(tensor(actual['stress']),expected,rtol=2e-13,atol=3e-10)
    assert actual['state']['kappa']==pytest.approx(dg,rel=1e-13,abs=1e-16)
    assert initial==before
    residual = actual['diagnostics']['local_residual']
    assert abs(residual)<1e-7 if dg>0 else residual<=1e-7


def test_j2_zero_pressure_limit():
    p=law.default_settings()['parameters'];p.update(alpha=0.,beta=0.)
    e=[.006,-.001,.0003,.002,0,0]
    expected,gamma,ptr,qtr=independent_trial(p,e)
    r=dp.integrate(p,dp.state(),e,1)
    np.testing.assert_allclose(tensor(r['stress']),expected,rtol=2e-13,atol=1e-10)
    assert -np.trace(tensor(r['stress']))/3==pytest.approx(ptr)
    assert np.sum(r['state']['plastic_strain_kelvin'][:3])==pytest.approx(0.,abs=1e-16)


def test_dp_discrete_nonsymmetric_and_wrong_tangent_fails():
    s=law.default_settings();F=np.eye(3)+np.diag([.006,-.001,.0002])
    r=law.update(s,s['initial_state'],F,1)
    assert np.linalg.norm(r['tangent']-r['tangent'].T)>1
    initial=deepcopy(s['initial_state'])
    p=tangent_probe(s,initial,F,1,[1e-6,1e-7,1e-8])
    assert p['status']=='PASS'
    wrong=tangent_probe(s,initial,F,1,[1e-7,1e-8],analytic_override=np.zeros((6,6)))
    assert wrong['status']=='FAIL'
    assert initial==s['initial_state']
    assert all(c['probes']['-1']['initial_state_sha256']==canonical_hash(initial)
               for h in p['rows'] for c in h['columns'])


def test_dp_apex_and_nondifferentiable_axis():
    s=law.default_settings()
    axis=np.eye(3)*1.01
    r=law.update(s,s['initial_state'],axis,1)
    assert 'apex' in r['diagnostics']['active_set']
    assert r['tangent'] is None
    assert r['state']['kappa']==pytest.approx(0.)
    assert np.trace(tensor(r['stress']))/3==pytest.approx(s['parameters']['k0']/s['parameters']['alpha'])
    p=tangent_probe(s,s['initial_state'],axis,1,[1e-6,1e-7])
    assert p['status']!='PASS'
    off=np.diag([1.012,1.01,1.01])
    p=tangent_probe(s,s['initial_state'],off,1,[1e-6,1e-7,1e-8])
    assert p['status']=='PASS'
    r=law.update(s,s['initial_state'],off,1)
    assert r['state']['kappa']==pytest.approx(.002*2/3,rel=1e-11)


def test_local_failure_retains_prefix_and_initial_trial_unchanged():
    s=law.default_settings();s['parameters']['beta']=0.
    s['time']=[0.,1.,2.];s['deformation_gradient']=[np.eye(3).tolist(),(np.eye(3)*1.01).tolist(),np.eye(3).tolist()]
    original=deepcopy(s);r=evaluate_history(s)
    assert r['execution_status']=='FAILED'
    assert len(r['diagnostics']['constitutive_increments'])==1
    assert r['diagnostics']['failed_increment']['increment']==1
    assert s==original
    s['deformation_gradient'][1]=(np.eye(3)+np.diag([.0001,0,0])).tolist()
    assert evaluate_history(s)['execution_status']=='SUCCEEDED'


def test_mixed_boundary_uses_existing_controller():
    s=law.default_settings();s['boundary_control']={'stress_components':{'yy':[0.]*4,'zz':[0.]*4},'solver':deepcopy(law.BOUNDARY_OPTIONS)}
    r=evaluate_history(s);assert r['execution_status']=='SUCCEEDED'
    np.testing.assert_allclose(r['responses']['stress_yy']['value'],0.,atol=1e-7)
    np.testing.assert_allclose(r['responses']['stress_zz']['value'],0.,atol=1e-7)
    assert r['diagnostics']['constitutive_increments'][2]['boundary']['iterations']>0


def test_sls_exact_step_and_initial_state():
    p=law.default_settings('single_branch_maxwell')['parameters'];initial=sls.state()
    initial['viscous_strain_kelvin']=[.0003,-.0002,0,0,0,.0001]
    before=deepcopy(initial);e=np.array([.002,-.001,.0003,.0005,0,.0002]);dt=.37
    C0=stiffness(p['K0'],p['G0']);C1=stiffness(p['K1'],p['G1'])
    a=np.exp(-dt/p['tau']);ramp=p['tau']/dt*(1-a)
    expected=C0@e+a*(C1@(-np.asarray(initial['viscous_strain_kelvin'])))+ramp*(C1@e)
    r=sls.integrate(p,initial,e,dt)
    np.testing.assert_allclose(r['stress'],expected,rtol=1e-13,atol=1e-12)
    np.testing.assert_allclose(r['tangent'],C0+ramp*C1,rtol=1e-13,atol=1e-12)
    assert r['dissipated_energy']>=0
    assert initial==before


def test_sls_probe_same_kelvin_state_and_wrong_tangent():
    s=law.default_settings('single_branch_maxwell');s['tangent_probe']={'increment':2,'steps':[1e-7,1e-8,1e-9]}
    r=evaluate_history(s);assert r['execution_status']=='SUCCEEDED'
    row=r['diagnostics']['constitutive_increments'][2]
    assert row['tangent_probe']['status']=='PASS'
    assert tangent_probe(s,row['initial_state'],row['F'],row['time'],[1e-8],
                         analytic_override=np.array(row['tangent'])*1.01)['status']=='FAIL'


def test_neo_contract_does_not_import_or_substitute_svk():
    s=law.default_settings('neo_hooke');law.validate_settings(s)
    assert law.declaration(s)['stress_measure']=='first_Piola'
    with pytest.raises(ValueError):law.from_saved_legacy({'backend':'material.mfront.hyperelastic','settings':{}})
    s['deformation_gradient'][1][0][0]=-1
    with pytest.raises(ValueError,match='det'):law.validate_settings(s)


@pytest.mark.parametrize('refined,tau',[(False,1.),(True,1.),(False,.1),(True,5.)])
def test_preserved_original_sls_canonical_limits(refined,tau):
    from plugins.material_point import viscoelastic_reference as original
    seed=original.canonical_settings(refined=refined,relaxation_time_s=tau)
    s=law.from_saved_legacy({'backend':'material.mfront.viscoelastic','settings':seed})
    r=evaluate_history(s);assert r['execution_status']=='SUCCEEDED'
    expected=original.analytical_reference(seed)['states'];actual=r['diagnostics']['constitutive_increments']
    assert len(actual)==(17 if refined else 9)
    L=original.FIXED_LIMITS
    for a,b in zip(actual,expected):
        scale=max(1.,max(abs(x) for x in b['stress_kelvin_mpa']))
        assert max(abs(np.asarray(a['stress'])-b['stress_kelvin_mpa']))<=L['stress_absolute_mpa']+L['stress_relative']*scale
        for new,old in [('stored_energy','stored_energy_mpa'),('dissipated_energy','dissipated_energy_mpa')]:
            assert abs(a[new]-b[old])<=L['energy_absolute_mpa']+L['energy_relative']*max(1.,abs(b[old]))
        if 'tangent_kelvin_mpa' in b:
            c=np.asarray(b['tangent_kelvin_mpa'])
            assert np.max(abs(np.asarray(a['tangent'])-c))/max(abs(c).flat)<=L['tangent_relative']


def test_retained_inspector_probe_values_are_original_not_filled():
    from caelab.law_native_inspection import populate,selected_probe_rows
    s=law.default_settings();s['tangent_probe']={'increment':2,'steps':[1e-6,1e-7]}
    r=evaluate_history(s);v=populate({'unavailable':[],'backend':law.POINT},r,s,2)
    rows=selected_probe_rows(v,0,3)
    assert rows[0]['minus_input'] is not None and rows[0]['minus_stress'] is not None
    assert rows[0]['signed'][-1]['initial_state']==r['diagnostics']['constitutive_increments'][2]['initial_state']
    assert v['energy']['dissipated'] is None and v['unavailable']


def test_failed_tangent_trial_is_retained_but_not_committed(monkeypatch):
    from caelab.law_native_inspection import populate
    original=dp.integrate
    def wrong(*args,**kwargs):
        r=original(*args,**kwargs)
        if r['tangent'] is not None:r['tangent']=np.asarray(r['tangent'])*1.03
        return r
    monkeypatch.setattr(dp,'integrate',wrong)
    s=law.default_settings();s['tangent_probe']={'increment':2,'steps':[1e-6,1e-7]}
    before=deepcopy(s);r=evaluate_history(s)
    assert r['execution_status']=='FAILED' and s==before
    d=r['diagnostics'];assert len(d['constitutive_increments'])==2
    assert d['unattempted_increments']==[3]
    assert d['last_accepted_state']==d['constitutive_increments'][1]['committed_state']
    v=populate({'unavailable':[],'backend':law.POINT},r,s,2)
    assert v['tangent_probe_report']['status']=='FAIL'
    assert v['state_trial'] is not None and v['state_committed'] is None
    assert v['state_initial']==d['last_accepted_state'] and v['stress'] is not None


def test_original_sls_physical_envelope_is_preserved():
    s=law.default_settings('single_branch_maxwell')
    s['deformation_gradient'][1][0][0]=1.01
    assert evaluate_history(s)['execution_status']=='SUCCEEDED'
    s['deformation_gradient'][1][0][0]=1.01000001
    with pytest.raises(ValueError,match='physical strain'):law.validate_settings(s)
    s=law.default_settings('single_branch_maxwell');s['parameters']['G1']=1e-7
    with pytest.raises(ValueError,match='original envelope'):law.validate_settings(s)


def test_preserved_public_J2_table_and_native_precision():
    from pathlib import Path
    from caelab.calculix_material import default_plasticity,native_yield_points,native_plasticity
    path=Path(__file__).resolve().parents[2]/'examples/material-tests/ns1/j2_example.tsv'
    rows=[[float(v) for v in line.split()] for line in path.read_text().splitlines()]
    assert rows==[[250.,0.],[270.,.001],[300.,.02]]
    draft=default_plasticity();draft['yield_points']=rows
    native=native_yield_points(draft)
    assert all(len(v.strip())<=20 for line in native for v in line.split(','))
    assert native_plasticity(native)['yield_points']==rows
