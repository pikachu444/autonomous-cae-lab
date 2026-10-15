"""Actual installed SciPy ODE adapter + Numerical evaluator + saved C1 evidence.
Original fit candidate is a labeled fixture at the exact known rate, NOT a
claim that a native GUI optimizer ran. Every new Jacobian evaluation is real.
"""
from copy import deepcopy
import numpy as np
import pytest
from caelab.dimensioned_models import default_settings,ODE
from caelab.adapters.native_evaluation import NativeEvaluationFactory
from caelab.numerical_candidate_detail import experiment_snapshot,trial_detail
from caelab.experiment_analysis_service import final_request
from caelab.storage import canonical_hash
from caelab.experiment_uncertainty import plain
from .support import ServiceHost


def test_actual_supported_scipy_ode_final_jacobian(tmp_path,monkeypatch):
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):monkeypatch.setenv(key,'1')
    s=default_settings(ODE);s['time'].update(end=2.,samples=11)
    # Preserve existing public solver tolerances. No relaxation for diagnosis.
    values={'rate':.5};f=NativeEvaluationFactory(ODE,tmp_path/'original-evaluation',response_selection=['temperature'])
    with f.prepare(s) as evaluator:raw=evaluator.evaluate(values)
    assert raw['execution_status']=='SUCCEEDED',raw
    obs=deepcopy(raw['responses']['temperature']);obs['value']=np.asarray(obs['value']).tolist()
    for axis in obs['axes']:axis['values']=np.asarray(axis['values']).tolist()
    variables=[{'id':'rate','unit':'1/s','value':.5,'lower':.1,'upper':1.,'transform':'linear'}]
    e=experiment_snapshot({'id':'Tcool','role':'fit','settings':s,'response':'temperature','observations':obs,
        'mask':[True]*11,'weight':1.,'scale':1.})
    p={'variables':variables,'experiments':[e],'candidate':{'candidate_id':'Cknown','values':values,
        'execution_status':'SUCCEEDED','objective':0.},'optimizer_method':'de','optimizer_loss':'linear',
        'selected_trials':[trial_detail(e,raw,origin={'kind':'fit_final','candidate_id':'Cknown'})]}
    with ServiceHost(tmp_path/'wb') as h:
        source,original,ref=h.original(p,backend=ODE,raws=[raw])
        doc,job,r=h.run_plan(final_request(ref,evaluations=5))
        assert r['execution_status']=='SUCCEEDED',r
        assert r['timing']['model_calls']==5
        matrix=np.asarray(r['experiment_analysis']['ordinary_jacobian']['matrix'])[:,0]
        t=np.asarray(obs['axes'][0]['values'])
        expected=-10*t*np.exp(-values['rate']*t)/np.sqrt(11)
        assert matrix==pytest.approx(expected,rel=2e-5,abs=1e-7)
        assert r['identification']['relative_rank_tolerance']==1e-6
        for a in r['experiment_analysis']['attempts']:
            assert a['trials'][0]['raw_evaluation']['diagnostics']['library']=='scipy'
        assert r['artifacts']
        assert r['experiment_analysis']['source_problem']['experiments'][0]['settings']['solver']==s['solver']
        h.save(doc);digest=canonical_hash(h.owner.result(doc,job));count=len(h.manager.list())
    with ServiceHost(tmp_path/'wb') as cold:
        assert canonical_hash(cold.owner.result(doc,job))==digest
        assert len(cold.manager.list())==count


@pytest.mark.parametrize('method,options',[('least_squares',{'loss':'soft_l1','max_nfev':50}),
    ('de',{'seed':8,'max_generations':4,'population_size':5})])
def test_actual_scipy_optimizer_final_point_diagnosed_without_optimizer_jacobian(method,options):
    from caelab.numerical import fit_model
    from caelab.experiment_final_diagnosis import evaluate_final
    from .test_final_diagnosis import direct_problem,algebra
    p=direct_problem();original=fit_model(algebra,p['variables'],p['experiments'],method=method,
        options=options,execution={'max_evaluations':200})
    assert original['execution_status']=='SUCCEEDED'
    # Real SciPy execution on a public analytic evaluator, not a native test.
    assert original['identification'].get('status','UNKNOWN')=='UNKNOWN'
    assert not original.get('ordinary_jacobian')
    digest=canonical_hash(plain(original))
    selected=next(c for c in original['candidates'] if c['values']==original['parameters'])
    p['candidate']=deepcopy(selected);p['optimizer_method']=method;p['optimizer_loss']=options.get('loss','linear')
    p['selected_trials']=[trial_detail(e,algebra(selected['values'],e['settings']),
        origin={'kind':'explicit_test_retained_detail','candidate_id':selected['candidate_id']}) for e in p['experiments']]
    diagnosis=evaluate_final(algebra,p,budget_evaluations=9)
    assert diagnosis['execution_status']=='SUCCEEDED'
    assert diagnosis['identification']['status']=='LOCAL_RANK_COMPLETE'
    assert diagnosis['experiment_analysis']['ordinary_jacobian']['parameter_values']==original['parameters']
    assert canonical_hash(plain(original))==digest
    assert diagnosis['timing']['model_calls']==9
