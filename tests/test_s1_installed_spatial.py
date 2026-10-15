"""Actual pinned scikit-fem assembly/solve tests, NOT controlled fixtures.

Absent dependency => explicit NOT_RUN skip. An installed wrong version FAILS.
Each run uses the product's existing finally-protected owned process supervisor.
"""
from copy import deepcopy
from importlib.util import find_spec
import json
import numpy as np
import pytest
from caelab import scikit_fem_models as d
from caelab import p1_temperature_transfer as t
from caelab.evaluation import run, read_result


@pytest.fixture(autouse=True)
def installed():
    if find_spec('skfem') is None:
        pytest.skip('NOT_RUN: scikit-fem 12.0.2 is not installed; no replacement solver or synthetic success')
    from caelab.adapters.scikit_fem_spatial import discover_runtime
    assert discover_runtime()['versions']==d.VERSIONS


def solve(backend,settings,path):
    result=run(backend,settings,output=path)
    assert result['execution_status']=='SUCCEEDED',result
    assert read_result(path,verify='all')['execution_status']=='SUCCEEDED'
    assert result['diagnostics']['versions']['scikit-fem']=='12.0.2'
    assert result['diagnostics']['physical_qualification']=='UNKNOWN'
    return result


def heat(cells=(2,2),q=0.,k=200.):
    s=d.default_settings(d.THERMAL);s['mesh']['cells']=list(cells)
    s['heat_source']['value']=q;s['conductivity']['value']=k
    return s


def test_actual_affine_conduction_two_meshes_original_norms_A01(tmp_path):
    for cells in ((2,2),(4,3)):
        s=heat(cells);s['boundary_temperature']['value']=300.;s['boundary_gradient']['values']=[4.,-2.]
        result=solve(d.THERMAL,s,tmp_path/str(cells))
        metrics=result['diagnostics']['assembly'];ref=result['diagnostics']['reference']
        assert metrics['dofs']==(cells[0]+1)*(cells[1]+1) and metrics['free_dofs']>0
        assert metrics['linear_solve_calls']==1 and metrics['assembly_calls']==2
        assert metrics['relative_residual']<=1e-10 and ref['nodal_max_error_K']<=1e-10
        assert ref['l2_error_K_m']<=1e-10 and ref['h1_seminorm_error_K']<=1e-9


def test_actual_thermal_source_coefficient_boundary_and_geometry_change_A01(tmp_path):
    a=heat(q=200000.);b=heat(q=200000.,k=400.)
    first=solve(d.THERMAL,a,tmp_path/'k200')['responses']['temperature']
    second=solve(d.THERMAL,b,tmp_path/'k400')['responses']['temperature']
    u,v=np.asarray(first['value']),np.asarray(second['value'])
    assert u.max()>323.15
    np.testing.assert_allclose(v-323.15,(u-323.15)*.5,atol=1e-10,rtol=0)
    c=deepcopy(a);c['boundary_temperature']['value']+=10.
    third=solve(d.THERMAL,c,tmp_path/'boundary')['responses']['temperature']['value']
    np.testing.assert_allclose(np.asarray(third)-u,10.,atol=1e-10,rtol=0)
    c=deepcopy(a);c['domain']['lengths'][1]=.5
    fourth=solve(d.THERMAL,c,tmp_path/'geometry')['responses']['temperature']
    assert fourth['mesh_sha256']!=first['mesh_sha256'] and max(fourth['value'])>max(first['value'])


def test_actual_dimensioned_form_edit_and_independent_quadratic_norm_A02(tmp_path):
    s=d.default_settings(d.WEAK);s['mesh']['levels']=[2,4]
    for p in s['parameters']:
        if p['name']=='k':p['value']=200.
        if p['name']=='q':p['value']=1000.
    s['reference']='left_value+(right_value-left_value)*x/length+q*x*(length-x)/(2*k)'
    first=solve(d.WEAK,s,tmp_path/'weak')
    studies=first['diagnostics']['mesh_studies']
    assert all(r['free_dofs']>0 and r['relative_residual']<=1e-9 for r in studies)
    assert studies[1]['l2_error']<studies[0]['l2_error']
    assert studies[1]['h1_seminorm_error']<studies[0]['h1_seminorm_error']
    edited=deepcopy(s);edited['forms']['linear']='2*q*v';edited['reference']=''
    second=solve(d.WEAK,edited,tmp_path/'edited')
    assert not np.allclose(first['responses']['temperature']['value'],second['responses']['temperature']['value'],atol=1e-10,rtol=0)
    coords=np.asarray(first['responses']['temperature']['coordinates']);linear=300+10*coords[:,0]
    np.testing.assert_allclose(np.asarray(second['responses']['temperature']['value'])-linear,
                              2*(np.asarray(first['responses']['temperature']['value'])-linear),atol=1e-9,rtol=0)


def test_actual_absolute_Celsius_and_delta_structure_A07(tmp_path):
    receivers=[]
    for unit,value in [('K',323.15),('degC',50.)]:
        hs=heat();hs['boundary_temperature']={'value':value,'unit':unit}
        field=solve(d.THERMAL,hs,tmp_path/('heat-'+unit))['responses']['temperature']
        s=d.default_settings(d.STRUCTURAL);s['mesh']['cells']=[3,2]
        policy=t.default_options('Heat',receiver_time=s['time'])
        s['temperature'],_=t.map_temperature([field],s,policy)
        result=solve(d.STRUCTURAL,s,tmp_path/('structure-'+unit));receivers.append(result)
        xy=np.asarray(result['responses']['displacement']['coordinates'])
        actual=np.asarray(result['responses']['displacement']['value'])
        assert np.max(np.linalg.norm(actual-23e-6*30*xy,axis=1))<=1e-10
        stress=np.asarray(result['responses']['stress']['value'])
        assert np.linalg.norm(stress)/(70e9*23e-6*30*max(1,np.sqrt(stress.size)))<=1e-10
        assert result['diagnostics']['reference_subtractions_in_structural_solver']==1
    np.testing.assert_allclose(receivers[0]['responses']['displacement']['value'],receivers[1]['responses']['displacement']['value'],atol=1e-10,rtol=0)
    s['temperature_mode']='difference';policy['target_quantity']=t.DIFFERENCE;policy['target_unit']='delta_K'
    s['temperature'],_=t.map_temperature([field],s,policy)
    delta=solve(d.STRUCTURAL,s,tmp_path/'structure-delta')
    assert delta['diagnostics']['reference_subtractions_in_structural_solver']==0
    np.testing.assert_allclose(delta['responses']['displacement']['value'],receivers[0]['responses']['displacement']['value'],atol=1e-10,rtol=0)
    changed=deepcopy(s);changed['material']['reference_temperature']+=10
    with pytest.raises(ValueError):d.validate_settings(d.STRUCTURAL,changed)


def test_actual_nonuniform_cannot_pass_uniform_benchmark_A07(tmp_path):
    s=heat();s['boundary_gradient']['values']=[4.,-2.]
    f=solve(d.THERMAL,s,tmp_path/'heat')['responses']['temperature']
    receiver=d.default_settings(d.STRUCTURAL);receiver['mesh']['cells']=[3,2]
    receiver['temperature'],_=t.map_temperature([f],receiver,t.default_options('Heat',receiver_time=receiver['time']))
    result=run(d.STRUCTURAL,receiver,output=tmp_path/'structure')
    assert result['execution_status']=='REJECTED'
    assert result['diagnostics']['free_expansion']['status']=='FAIL'
    assert result['responses']['displacement']['value']


@pytest.mark.parametrize('case',['uniform','affine'])
def test_actual_saved_owner_public_example_and_independent_cold_process_A08_A12(tmp_path,case):
    from examples.s1_windows_transfer import main
    assert main(['--workspace',str(tmp_path/('한글 저장 '+case)),'--case',case,'--deadline-seconds','120'])==0
    records=list(tmp_path.rglob('s1-'+case+'-J*.json'));assert len(records)==1
    record=json.loads(records[0].read_text(encoding='utf-8'))
    assert record['execution_status']=='SUCCEEDED' and record['checks']['physics']=='EXECUTED'
    assert record['checks']['thermal_sparse_solves']>=1
