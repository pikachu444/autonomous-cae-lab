"""Predeclared synthetic comparisons; no native or provider calls."""
from copy import deepcopy
import math
import numpy as np
import pytest

from caelab import fatigue
from caelab.fatigue_life import solve_life, calibration_draft
from caelab.fatigue_cycles import associate_cycles
from caelab.fatigue_strain import default_settings, analyze, select_result
from caelab.fatigue_tensor import COMPONENTS, admit_bundle, project, plane_grid
from caelab.storage import canonical_hash


def calibration():
    c = calibration_draft()
    c.update(E=200000., sigma_f=1000., epsilon_f=.5, b=-.1, c=-.5,
             cycles_min=1., cycles_max=1e9, strain_amplitude_min=1e-6, strain_amplitude_max=1.,
             max_stress_min=1e-6, max_stress_max=20000., temperature_min_k=293., temperature_max_k=294.,
             reference='SYNTHETIC PREDECLARED / not a measured material', conditions='Fully reversed axial synthetic coefficients',
             failure_definition='Synthetic D=1 convention; not engineering qualification', cyclic_state='STABILIZED')
    return c


def cmb_forward(n):
    return .005 * (2*n)**(-.1) + .5 * (2*n)**(-.5)


def cases(e=None, stress=None, *, method='CP_SWT', mean='SWT'):
    e = np.asarray(e if e is not None else [[.01,0,0,0,0,0],[-.01,0,0,0,0,0],[.01,0,0,0,0,0]],dtype=float)
    stress = np.asarray(stress if stress is not None else [[500,0,0,0,0,0],[-500,0,0,0,0,0],[500,0,0,0,0,0]],dtype=float)
    s = default_settings(method, mean)
    s['source'] = {'result': {'document_id':'Tsynthetic','job_id':'Jsynthetic','input_revision':'Isynthetic',
                             'input_sha256':'a'*64,'result_sha256':'b'*64},'title':'공개 합성 tensor',
                   'channels': {'strain': {}, **({'stress': {}} if mean=='SWT' else {})}}
    s['calibration'] = calibration(); s['temperature_k']=293.15
    s['interpretation'].update(strain_shear='TENSOR', history_state='STABILIZED_CYCLIC',
                               constitutive_source='Supplied synthetic tensor; no constitutive solver')
    s['search'].update(polar_steps=2, refinement_levels=0)
    responses = {}
    components = COMPONENTS if method=='CP_SWT' else COMPONENTS[:1]
    for role, tensor in [('strain',e),*([('stress',stress)] if mean=='SWT' else [])]:
        for component in components:
            name=role+'_'+component;s['source']['channels'][role][component]=name
            responses[name]={'kind':'series','unit':'1' if role=='strain' else 'MPa','component':component,
                'location':{'element':7,'gauss':2,'layer':'top'},'frame':'fixed_model_basis','reduction':'none',
                'measure':'infinitesimal_total_strain_tensor' if role=='strain' else 'infinitesimal_Cauchy',
                'axes':[{'name':'time','unit':'s','values':[float(i) for i in range(len(e))]}],
                'source_rows':list(range(10,10+len(e))),'source_row_kind':'physical_line',
                'value':tensor[:,COMPONENTS.index(component)].tolist()}
    bundle={'source':deepcopy(s['source']),'source_result_sha256':s['source']['result']['result_sha256'],
            'origin':'EXACT_RETAINED_RESULT','responses':responses}
    return s,bundle


@pytest.mark.parametrize('n',[10.,1000.,1000000.])
@pytest.mark.parametrize('mean',['NONE','SWT'])
def test_forward_generated_life_cycles_reversals_and_residual(n,mean):
    amplitude=cmb_forward(n)
    sigma=1000*(2*n)**(-.1)
    r=solve_life(amplitude,sigma,calibration(),mean_stress=mean,temperature_k=293.15)
    assert r['status']=='CALCULATED',r
    assert r['Nf_cycles']==pytest.approx(n,rel=2e-9)
    assert r['reversals']==pytest.approx(2*n,rel=2e-9)
    assert r['relative_residual']<=1e-10
    assert r['elastic_term']>0 and r['plastic_term']>0
    assert r['bracket_initial_cycles']==[1.,1e9]


def test_calibration_pa_percent_none_swt_and_no_double_mean_correction():
    n=1000.;a=cmb_forward(n);sigma=1000*(2*n)**(-.1)
    c=calibration();c.update(stress_unit='Pa',strain_unit='%')
    for key in ('E','sigma_f','max_stress_min','max_stress_max'):c[key]*=1e6
    for key in ('epsilon_f','strain_amplitude_min','strain_amplitude_max'):c[key]*=100
    r=solve_life(a,sigma,c,mean_stress='SWT',temperature_k=293.15)
    base=solve_life(a,sigma,calibration(),mean_stress='SWT',temperature_k=293.15)
    assert r['Nf_cycles']==pytest.approx(base['Nf_cycles'],rel=2e-12)
    higher=solve_life(a,2*sigma,calibration(),mean_stress='SWT',temperature_k=293.15)
    none=solve_life(a,None,calibration(),mean_stress='NONE',temperature_k=293.15)
    assert higher['Nf_cycles']<base['Nf_cycles'] and none['Nf_cycles']==pytest.approx(n,rel=2e-9)
    c['coefficient_basis']='MEAN_STRESS_ALREADY_CORRECTED'
    assert solve_life(a,sigma,c,mean_stress='SWT',temperature_k=293.15)['status']=='UNKNOWN'


@pytest.mark.parametrize('mutation,code',[
    ({'amplitude':0},'ZERO'),({'sigma_max_mpa':0},'NON_TENSILE'),({'sigma_max_mpa':-10},'NON_TENSILE'),
    ({'amplitude':1e-8},'STRAIN_AMPLITUDE'),({'amplitude':.9,'sigma_max_mpa':19999},'NO_ROOT'),
    ({'temperature_k':500},'TEMPERATURE'),({'root':{'relative_tolerance':1e-10,'residual_relative_tolerance':1e-10,'max_iterations':1}},'CONVERGE')])
def test_unknown_not_safe_or_infinite(mutation,code):
    kw=dict(amplitude=.01,sigma_max_mpa=500,calibration=calibration(),mean_stress='SWT',temperature_k=293.15)
    kw.update(mutation);r=solve_life(**kw)
    assert r['status']=='UNKNOWN' and r['Nf_cycles'] is None and code in r['reason']
    kw['calibration']['E']=None
    assert solve_life(**kw)['status']=='UNKNOWN'


def test_return_branch_peak_and_nested_excision_are_not_endpoint_slice():
    e=[0,4,1,2,3,4,5,0]
    rows=associate_cycles(e)
    inner=next(r for r in rows if r['count']==1.)
    assert (inner['start_row'],inner['end_row'])==(1,2)
    assert inner['member_indices']==[1,2,3,4,5]
    assert inner['closure_index']==5 and inner['closing_reversal_index']==6
    enclosing=next(r for r in rows if (r['start_row'],r['end_row'])==(0,6))
    assert enclosing['member_indices']==[0,1,5,6]
    tensor=np.zeros((8,6));tensor[:,0]=np.array(e)*.001
    sigma=np.zeros((8,6));sigma[:,0]=[10,20,30,400,900,50,60,10]
    s,b=cases(tensor,sigma,method='STRAIN_LIFE')
    r=analyze(s,b);cycle=next(c for c in r['cycles'] if c['count']==1.)
    assert cycle['sigma_max_mpa']==900 and cycle['sigma_max_source_rows']==[14]
    assert cycle['closure_source_row']==15 and cycle['member_times_s']==[1.,2.,3.,4.,5.]
    assert b['responses']['stress_xx']['value'][cycle['end_row']]==30


def test_bracketed_closure_never_samples_past_loop_or_interpolates():
    rows=associate_cycles([0.,4.,1.,3.,5.,0.])
    inner=next(r for r in rows if r['count']==1.)
    assert inner['member_indices']==[1,2,3]
    assert inner['closure_index'] is None and inner['closure_bracket_indices']==[3,4]
    assert inner['association']=='BRACKETED_SAMPLED_LOOP'


@pytest.mark.parametrize('kind',['component','time','location','layer','shear','mask','gap','nan','measure','frame','rows','quantity','clock'])
def test_tensor_admission_rejects_missing_or_misaligned_data(kind):
    s,b=cases();r=b['responses']['strain_xy']
    if kind=='component':del s['source']['channels']['strain']['xy']
    elif kind=='time':r['axes'][0]['values'][1]=1.1
    elif kind=='location':r['location']['gauss']=3
    elif kind=='layer':r['location']['layer']='bottom'
    elif kind=='shear':r['measure']='infinitesimal_total_strain_engineering_shear'
    elif kind=='mask':r['mask']=[True,False,True]
    elif kind=='gap':r['has_calculation_gaps']=True
    elif kind=='nan':r['value'][1]=float('nan')
    elif kind=='measure':r['measure']='Green_Lagrange_total_strain'
    elif kind=='frame':r['frame']='UNKNOWN'
    elif kind=='rows':r['source_rows'][1]=50
    elif kind=='quantity':r['derived_from_stress']=True
    elif kind=='clock':r['axes'][0]['semantics']='LOAD_FACTOR'
    with pytest.raises(ValueError):admit_bundle(b,s)


def test_known_model_basis_is_not_unknown_world_alignment():
    s,b=cases()
    for r in b['responses'].values():r['frame']='Tridimensional model component basis; sensor/world alignment UNKNOWN'
    a=admit_bundle(b,s)
    assert a['external_alignment']=='UNKNOWN'
    assert analyze(s,b)['diagnostics']['assessment']=='CALCULATED'


def test_uniaxial_cmb_needs_no_stress_tensor_and_no_default_calibration():
    a=cmb_forward(1000.)
    e=np.zeros((3,6));e[:,0]=[a,-a,a]
    s,b=cases(e,method='STRAIN_LIFE',mean='NONE');s['repeat_block']=True
    s['calibration']['max_stress_min']=s['calibration']['max_stress_max']=None
    r=fatigue.analyze(s,b)
    assert set(b['responses'])=={'strain_xx'}
    assert sum(c['count'] for c in r['cycles'])==1.
    assert r['responses']['miner_damage']['value']==pytest.approx(.001,rel=2e-9)
    assert all(c['damage']==pytest.approx(.0005,rel=2e-9) for c in r['cycles'])
    assert r['responses']['repeating_blocks_to_D1']['value']==pytest.approx(1000.,rel=2e-9)
    s['calibration']['E']='1e'
    with pytest.raises(ValueError):fatigue.validate_settings(s)


def test_pure_shear_projection_and_actual_engineering_conversion():
    q=np.array([1.,0.,-1.,0.,1.]);e=np.zeros((5,6));e[:,3]=.01*q
    t=np.zeros((5,6));t[:,3]=500*q
    s,b=cases(e,t)
    n=[1/math.sqrt(2),1/math.sqrt(2),0]
    assert project(e,n)==pytest.approx(.01*q,rel=2e-12)
    r=analyze(s,b)
    critical=[p for p in r['planes'] if p['plane_id'] in r['critical_plane_ids']]
    assert all(p['normal_strain_range']==pytest.approx(.02,rel=2e-12) for p in critical)
    assert any(abs(np.dot(p['normal_model'],n))>1-1e-12 for p in critical)
    eng=deepcopy(b);se=deepcopy(s);se['interpretation']['strain_shear']='ENGINEERING'
    for component,name in se['source']['channels']['strain'].items():
        ch=eng['responses'][name];ch['unit']='%';ch['measure']='infinitesimal_total_strain_engineering_shear'
        ch['value']=[v*100*(2 if component in COMPONENTS[3:] else 1) for v in ch['value']]
    for name in se['source']['channels']['stress'].values():
        eng['responses'][name]['unit']='Pa';eng['responses'][name]['value']=[v*1e6 for v in eng['responses'][name]['value']]
    eng['source']=deepcopy(se['source'])
    converted=admit_bundle(eng,se)
    assert converted['strain']==pytest.approx(e,rel=2e-12)
    assert converted['stress']==pytest.approx(t,rel=2e-12)
    rr=analyze(se,eng)
    assert rr['responses']['miner_damage']['value']==pytest.approx(r['responses']['miner_damage']['value'],rel=2e-12)


def test_max_strain_plane_is_not_max_swt_or_damage_plane():
    q=np.array([1.,-1.,1.]);e=np.zeros((3,6));e[:,0]=.01*q;e[:,1]=.006*q
    t=np.zeros((3,6));t[:,0]=100;t[:,1]=400
    s,b=cases(e,t);r=analyze(s,b)
    crit=next(p for p in r['planes'] if p['plane_id']==r['display_plane_id'])
    assert abs(crit['normal_model'][0])==pytest.approx(1.)
    assert crit['max_cycle_swt_mpa']==pytest.approx(1.)
    y=next(p for p in r['planes'] if abs(p['normal_model'][1])>1-1e-12)
    assert y['max_cycle_swt_mpa']==pytest.approx(2.4)
    assert set(r['critical_plane_ids']).isdisjoint(r['diagnostic_max_swt_plane_ids'])
    assert set(r['critical_plane_ids']).isdisjoint(r['diagnostic_max_damage_plane_ids'])
    assert r['diagnostics']['plane_selection']=='MAXIMUM_NORMAL_STRAIN_RANGE'


def tensor_rotate(six,R):
    result=[]
    for xx,yy,zz,xy,yz,xz in six:
        T=np.array([[xx,xy,xz],[xy,yy,yz],[xz,yz,zz]])
        v=R@T@R.T;result.append([v[0,0],v[1,1],v[2,2],v[0,1],v[1,2],v[0,2]])
    return np.array(result)


@pytest.mark.parametrize('phase',[0.,math.pi/2])
def test_proportional_nonproportional_projection_and_covariant_grid_rotation(phase):
    times=np.linspace(0,2*math.pi,17);q=np.cos(times);r=np.cos(times+phase)
    e=np.zeros((17,6));e[:,0]=.015*q;e[:,1]=-.003*q;e[:,3]=.004*r
    t=np.zeros((17,6));t[:,0]=200+600*q;t[:,1]=50+100*q;t[:,3]=150*r
    theta=.37;phi=.29
    R=np.array([[math.cos(theta),-math.sin(theta),0],[math.sin(theta),math.cos(theta),0],[0,0,1]]) @ np.array([[1,0,0],[0,math.cos(phi),-math.sin(phi)],[0,math.sin(phi),math.cos(phi)]])
    s,b=cases(e,t);s['search'].update(polar_steps=3)
    original=analyze(s,b)
    sr,br=cases(tensor_rotate(e,R),tensor_rotate(t,R));sr['search'].update(polar_steps=3,basis=R.tolist())
    rotated=analyze(sr,br)
    p=next(p for p in original['planes'] if p['plane_id']==original['display_plane_id'])
    pr=next(p for p in rotated['planes'] if p['plane_id']==rotated['display_plane_id'])
    assert abs(np.dot(pr['normal_model'],R@np.array(p['normal_model'])))>=1-1e-12
    for key in ('normal_strain_range','max_cycle_swt_mpa','miner_damage'):
        assert pr[key]==pytest.approx(p[key],rel=2e-9)
    for plane in original['planes']:
        n=np.array(plane['normal_model'])
        expected=[n@np.array([[a,d,f],[d,c,g],[f,g,h]])@n for a,c,h,d,g,f in e]
        assert plane['history']['strain']==pytest.approx(expected,rel=2e-12,abs=1e-15)


def test_angular_grid_convergence_against_rank_one_exact_value():
    u=np.array([.83,.41,.37]);u/=np.linalg.norm(u);a=.01
    q=[1.,-1.,1.];T=np.outer(u,u)
    six=np.array([[a*v*T[0,0],a*v*T[1,1],a*v*T[2,2],a*v*T[0,1],a*v*T[1,2],a*v*T[0,2]] for v in q])
    ranges=[]
    for p in [3,6,12]:
        grid=plane_grid(p,np.eye(3).tolist());ranges.append(max(np.ptp(project(six,n['normal_model'])) for n in grid))
    assert ranges[0]<=ranges[1]+1e-15<=ranges[2]+2e-15
    assert abs(2*a-ranges[-1])<abs(2*a-ranges[0])
    assert ranges[-1]<=2*a+1e-15


def test_repeat_boundary_and_residual_stress_correspondence():
    e=np.zeros((5,6));e[:,0]=[.01,0,-.01,0,.01]
    t=np.zeros((5,6));t[:,0]=[100,500,-100,900,100]
    s,b=cases(e,t,method='STRAIN_LIFE');s['repeat_block']=True
    r=analyze(s,b)
    assert 'miner_damage' in r['responses'] and 'repeating_blocks_to_D1' not in r['responses']
    assert r['planes'][0]['repeating_block']['reason']=='RESIDUAL_SWT_MAX_MISMATCH'
    # Same scalar strain and same normal boundary, but another tensor component changes.
    ss,bb=cases(e,t);ss['repeat_block']=True;bb['responses']['stress_yz']['value'][-1]=1
    rr=analyze(ss,bb)
    selected=next(p for p in rr['planes'] if p['plane_id']==rr['display_plane_id'])
    assert selected['repeating_block']['reason']=='SIMULTANEOUS_TENSOR_BLOCK_BOUNDARY_MISMATCH'
    # Equal full tensor endpoints at arbitrary phase are still not claimed periodic.
    e[:,0]=[0,.01,0,-.01,0];s,b=cases(e,t,method='STRAIN_LIFE');s['repeat_block']=True
    r=analyze(s,b)
    assert r['planes'][0]['repeating_block']['reason']=='PROJECTED_BLOCK_NOT_CLOSED_AT_GLOBAL_STRAIN_EXTREMUM'


def test_partial_unknown_selection_and_cancelled_planes_preserved(monkeypatch):
    s,b=cases();s['calibration']['max_stress_max']=300.
    r=analyze(s,b)
    assert r['diagnostics']['assessment']=='PARTIAL' and 'miner_damage' not in r['responses']
    assert r['cycles'][0]['damage'] is None
    before=canonical_hash(r)
    selection=select_result(r,job_id='Jtest',plane_id=r['display_plane_id'],cycle=1,source_row=10)
    assert selection['result_sha256']==before and canonical_hash(r)==before
    with pytest.raises(ValueError):select_result(r,job_id='Jtest',plane_id=r['display_plane_id'],cycle=1,source_row=999)
    from caelab.execution_control import CancellationToken,cancellation_scope
    from caelab import fatigue_strain
    token=CancellationToken();original=fatigue_strain._plane;count=[0]
    def cancel_after_first(*args):
        v=original(*args);count[0]+=1
        if count[0]==1:token.request()
        return v
    monkeypatch.setattr(fatigue_strain,'_plane',cancel_after_first)
    with cancellation_scope(token):cancelled=analyze(*cases())
    assert token.observed and cancelled['execution_status']=='CANCELLED'
    assert len(cancelled['planes'])==1 and cancelled['critical_plane_ids']==[]
    assert 'miner_damage' not in cancelled['responses']


def test_scalar_none_does_not_require_shear_or_stress_and_mixed_partial_damage():
    a=cmb_forward(1000);e=np.zeros((5,6));e[:,0]=[a,-a,a,-2*a,a]
    s,b=cases(e,np.zeros_like(e),method='STRAIN_LIFE',mean='NONE')
    s['interpretation']['strain_shear']='UNKNOWN'
    s['calibration']['strain_amplitude_max']=1.25*a
    s['repeat_block']=True
    r=analyze(s,b);p=r['planes'][0]
    assert p['unknown_cycle_count']>0
    assert p['admitted_partial_damage']==pytest.approx(.001,rel=2e-9)
    assert p['miner_damage'] is None and 'miner_damage' not in r['responses']
    assert p['repeating_block']['blocks_to_D1'] is None
    assert r['diagnostics']['plane_selection']=='EXPLICIT_UNIAXIAL_COMPONENT'


@pytest.mark.parametrize('key,value',[
    ('quantity','plastic_strain'),('frame','미확인 기준계'),('location','UNKNOWN'),
    ('location',{'element':1,'gauss':None}),('sample_ids',['same','same','same'])])
def test_unknown_physical_identity_and_quantity_are_not_silently_admitted(key,value):
    s,b=cases();b['responses']['strain_xx'][key]=value
    with pytest.raises(ValueError):admit_bundle(b,s)


def test_compression_only_tensor_does_not_become_safe_or_infinite():
    e=np.zeros((3,6));e[:,0]=[.01,-.01,.01]
    stress=np.zeros((3,6));stress[:,:3]=-100
    s,b=cases(e,stress);s['repeat_block']=True;r=analyze(s,b)
    assert r['responses'].get('miner_damage') is None
    assert r['responses'].get('repeating_blocks_to_D1') is None
    assert all(c['reason']=='SWT_NON_TENSILE_CYCLE_OUTSIDE_MODEL' for c in r['cycles'])


def test_partial_plane_failure_is_retained_not_relabelled_success(monkeypatch):
    from caelab import fatigue_strain
    original=fatigue_strain._plane;calls=[0]
    def fail_third(*args):
        calls[0]+=1
        if calls[0]==3:raise ValueError('INJECTED cycle association failure')
        return original(*args)
    monkeypatch.setattr(fatigue_strain,'_plane',fail_third)
    result=analyze(*cases())
    assert result['execution_status']=='FAILED' and len(result['planes'])==2
    assert result['critical_plane_ids']==[] and 'miner_damage' not in result['responses']
    assert result['diagnostics']['plane_search_failure']['message']=='INJECTED cycle association failure'


def test_residual_peak_comparison_has_no_scale_dependent_absolute_floor():
    e=np.zeros((5,6));e[:,0]=[.01,0,-.01,0,.01]
    stress=np.zeros_like(e);stress[:,0]=[.05,.1,-.05,.1000000005,.05]
    s,b=cases(e,stress,method='STRAIN_LIFE');s['repeat_block']=True
    s['calibration'].update(E=200.,sigma_f=1.)
    r=analyze(s,b)
    assert 'miner_damage' in r['responses']
    block=r['planes'][0]['repeating_block']
    assert block['reason']=='RESIDUAL_SWT_MAX_MISMATCH' and block['blocks_to_D1'] is None
    assert block['residual_match_tolerance']['stress_mpa_absolute']==0
