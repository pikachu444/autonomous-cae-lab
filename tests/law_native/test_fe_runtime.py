"""Spatial tests require actual pinned FELUPE. Skips are NOT_RUN, not FE proof."""
from copy import deepcopy
from importlib.util import find_spec
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from caelab import law_native_fe as domain
from caelab.adapters.law_native_fe_worker import FelupeConstitutive,solve
from caelab.adapters.law_native_fe import LawNativeFEAdapter
from caelab.evaluation import read_result
from caelab.storage import canonical_hash
from plugins.material_point import law_native as law


@pytest.fixture
def installed_felupe():
    fem=pytest.importorskip('felupe',reason='NOT_RUN: actual FELUPE runtime is unavailable; no stand-in')
    if fem.__version__!=law.FELUPE_VERSION:
        pytest.fail('Installed FELUPE version differs from the declared pinned ABI')
    return fem


def test_fixed_material_abi_state_restore_without_claiming_FE():
    s=law.default_settings();m=FelupeConstitutive(s)
    before=[deepcopy(s['initial_state']) for _ in range(4)]
    m.begin(before,1.)
    F=np.tile(np.asarray(s['deformation_gradient'][2])[:,:,None,None],(1,1,2,2))
    a=m.gradient([F,None]);C=m.hessian([F,None])[0]
    assert a[0].shape==(3,3,2,2) and C.shape==(3,3,3,3,2,2)
    assert canonical_hash(before)==m.accepted_hash
    assert not np.allclose(C[:,:,:,:,0,0].reshape(9,9),C[:,:,:,:,0,0].reshape(9,9).T)
    b=m.gradient([F,None]);np.testing.assert_array_equal(a[0],b[0])
    failed=F.copy();failed[0,0,0,0]=2.
    with pytest.raises(ValueError):m.gradient([failed,None])
    assert canonical_hash(m.accepted)==canonical_hash(before)
    np.testing.assert_array_equal(m.gradient([F,None])[0],a[0])


def test_missing_runtime_is_retained_rejection_not_FE_pass(tmp_path):
    if find_spec('felupe') is not None:pytest.skip('Missing-package path is inapplicable with installed FELUPE')
    result=LawNativeFEAdapter().run(domain.default_settings(),output=tmp_path/'evaluation')
    assert result['execution_status']=='REJECTED'
    assert result['diagnostics']['FE_execution']=='NOT_RUN'
    assert not result['responses']
    retained=read_result(tmp_path/'evaluation/fe',verify='all')
    assert retained['diagnostics']['FE_execution']=='NOT_RUN'
    assert any(a['path'].endswith('law-fe.execution.json') for a in result['artifacts'])


@pytest.mark.parametrize('model',law.MODELS)
def test_actual_spatial_point_pair(installed_felupe,tmp_path,model):
    s=domain.default_settings(model);r=solve(s,tmp_path/'fe')
    assert r['execution_status']=='SUCCEEDED',r.get('diagnostics')
    d=r['diagnostics'];assert d['FE_execution']=='ACTUAL' and d['global_newton_calls']==3
    assert d['pair_comparison']['status']=='PASS'
    assert d['constitutive_calls']['hessian']>0
    assert all(row['actual_free_dofs']>=3 and len(row['local'])==64 for row in d['steps'])
    assert len(read_result(tmp_path/'fe',verify='all')['diagnostics']['steps'])==4
    assert d['runtime']['packages']['felupe']['version']==law.FELUPE_VERSION
    assert d['runtime']['packages']['felupe']['source_and_binary_sha256']


@pytest.mark.parametrize('refined',[False,True])
def test_actual_original_sls_time_path(installed_felupe,tmp_path,refined):
    from plugins.material_point import viscoelastic_reference as original
    seed=original.canonical_settings(refined=refined,relaxation_time_s=.1 if refined else 1.)
    s=domain.default_settings('single_branch_maxwell')
    s['law']=law.from_saved_legacy({'backend':'material.mfront.viscoelastic','settings':seed})
    r=solve(s,tmp_path/'fe');assert r['execution_status']=='SUCCEEDED',r['diagnostics']
    expected=original.analytical_reference(seed)['states'];limits=original.FIXED_LIMITS
    for step,e in zip(r['diagnostics']['steps'],expected):
        for ip in step['local']:
            target=np.asarray(e['stress_kelvin_mpa'])
            assert np.max(abs(np.asarray(ip['stress'])-target)) <= limits['stress_absolute_mpa']+limits['stress_relative']*max(1.,np.max(abs(target)))
            for key in ('stored_energy','dissipated_energy'):
                target=e[key+'_mpa']
                assert abs(ip[key]-target)<=limits['energy_absolute_mpa']+limits['energy_relative']*max(1.,abs(target))


def test_actual_nonzero_viscous_state_and_uniaxial_DP(installed_felupe,tmp_path):
    s=domain.default_settings('single_branch_maxwell')
    s['law']['initial_state']['viscous_strain_kelvin']=[.0001,-.0002,.0001,0,.0001,0]
    r=solve(s,tmp_path/'sls');assert r['execution_status']=='SUCCEEDED',r['diagnostics']
    assert r['diagnostics']['steps'][0]['local'][0]['state']['viscous_strain_kelvin']==s['law']['initial_state']['viscous_strain_kelvin']
    s=domain.default_settings();s['boundary']['mode']='uniaxial_zero_lateral'
    s['law']['boundary_control']={'stress_components':{'yy':[0.]*4,'zz':[0.]*4},'solver':deepcopy(law.BOUNDARY_OPTIONS)}
    r=solve(s,tmp_path/'dp');assert r['execution_status']=='SUCCEEDED',r['diagnostics']


def test_actual_neo_energy_measure_rotation_and_independent_tangent(installed_felupe):
    path=Path(__file__).resolve().parents[2]/'examples/material-tests/law-native/reference_cases.py'
    spec=importlib.util.spec_from_file_location('independent_law_examples',path)
    reference=importlib.util.module_from_spec(spec);spec.loader.exec_module(reference)
    from plugins.material_point.law_native_history import evaluate_history
    s=law.default_settings('neo_hooke')
    angle=.12;c,z=np.cos(angle),np.sin(angle);R=np.array([[c,-z,0],[z,c,0],[0,0,1.]])
    gradients=[np.eye(3),np.array([[1.15,.1,0],[0,.9,.03],[.02,0,1.1]]),R@np.diag([1.05,.96,1.02]),R]
    s['deformation_gradient']=[F.tolist() for F in gradients]
    s['tangent_probe']={'increment':2,'steps':[1e-5,1e-6,1e-7]}
    result=evaluate_history(s);assert result['execution_status']=='SUCCEEDED',result['diagnostics']
    for row,F in zip(result['diagnostics']['constitutive_increments'],gradients):
        expected=reference.neo_reference(F,**s['parameters'])
        np.testing.assert_allclose(row['stress'],expected['P'],rtol=1e-10,atol=1e-11)
        np.testing.assert_allclose(np.asarray(row['tangent']).reshape(9,9),expected['DP_DF'],rtol=1e-10,atol=1e-10)
        assert row['stored_energy']==pytest.approx(expected['raw_energy'],rel=1e-12,abs=1e-12)
    np.testing.assert_allclose(result['diagnostics']['constitutive_increments'][-1]['stress'],0.,atol=1e-10)
