"""Real pure declarations and SciPy owner flow; native test is explicit opt-in."""
from copy import deepcopy
import math
import os
import pytest
from caelab import dimensioned_models as domain
from caelab.pde_document import default_draft,diagnostics
from caelab.dimensioned_expression import ExpressionError,parse,Meaning,unit_dimension
from caelab.model_parameters import bind
from caelab.adapters.dimensioned_ode import DimensionedODEAdapter
from caelab.storage import canonical_hash
from test_connected_evaluation_study import service,change,wait
from caelab.jobs import TERMINAL


def test_dimensioned_defaults_binds_and_real_scipy(tmp_path):
    from caelab.evaluation import run
    adapter=DimensionedODEAdapter();settings=domain.default_settings(domain.ODE)
    draft=default_draft(domain.ODE);assert diagnostics(draft)==[]
    altered=bind(adapter,settings,{'rate':.75})
    assert settings['parameters'][0]['value']==.5 and altered['parameters'][0]['value']==.75
    result=run(domain.ODE,altered,output=tmp_path/'ode')
    response=result['responses']['temperature']
    assert result['execution_status']=='SUCCEEDED'
    expected=[290+10*math.exp(-.75*t) for t in response['axes'][0]['values']]
    assert response['unit']=='K' and response['axes'][0]['unit']=='s'
    assert max(abs(a-b) for a,b in zip(response['value'],expected))<1e-4
    assert len(response['value'])==101 and 'native_fields' not in result['diagnostics']


def test_dimensions_arity_and_no_python_execution():
    weak=default_draft(domain.WEAK);assert diagnostics(weak)==[]
    bad=deepcopy(weak);bad['settings']['parameters'][1]['unit']='K'
    assert diagnostics(bad)[0]['path']=='settings.forms'
    bad=deepcopy(weak);bad['settings']['forms']['bilinear']='k*inner(grad(u),grad(u))*v'
    assert diagnostics(bad)
    ode=default_draft(domain.ODE);ode['settings']['states'][0]['rhs']='temperature + rate'
    assert diagnostics(ode)[0]['path']=='settings.states.0.rhs'
    ode['settings']['states'][0]['rhs']='__import__("os").system("false")'
    assert diagnostics(ode)[0]['column'] is not None
    with pytest.raises(ExpressionError):unit_dimension('mm')
    with pytest.raises(ExpressionError):parse('sin(q)',{'q':Meaning(unit_dimension('K'))})


def test_actual_ode_invalid_save_reopen_repair_and_result(service):
    wb,client=service
    draft=default_draft(domain.ODE);draft['settings']['parameters'][0]['value']='1e'
    doc=client.document_open(kind='pde',title='온도 초기값',draft=draft)
    saved=change(client,doc,'document.save')['document']
    before=len(wb.manager.list())
    with pytest.raises(Exception):change(client,saved,'pde.evaluate')
    assert len(wb.manager.list())==before
    # Reopen through the actual PDE owner, never the Material default.
    reopened=client.document_open(kind='pde',document_id=saved['id'])
    assert reopened['draft']==draft and reopened['diagnostics']
    repaired=default_draft(domain.ODE)
    doc=change(client,reopened,'pde.update',{'draft':repaired})['document']
    started=change(client,doc,'pde.evaluate');job=started['job']['id']
    wait(lambda:client.status(job)['state'] in TERMINAL)
    result=client.document_result(doc['id'],job);assert result['execution_status']=='SUCCEEDED',result
    doc=change(client,client.document_read(doc['id']),'document.save')['document']
    from caelab.workbench import Workbench
    fresh=Workbench(wb.workspace)
    try:
        again=fresh.document_open(kind='pde',document_id=doc['id'])
        assert again['draft']==repaired
        assert canonical_hash(fresh.document_result(doc['id'],job))==canonical_hash(result)
    finally:fresh.shutdown()
    assert len(wb.manager.list())==before+1


@pytest.mark.skipif(os.environ.get('CAELAB_RUN_DIMENSIONED_WEAK_NATIVE')!='1',reason='explicit installed FEniCSx check')
def test_installed_dimensioned_weak_reference_and_post(tmp_path):
    from caelab.evaluation import run,read_result
    from caelab.pde_results import write_post_sets
    result=run(domain.WEAK,domain.default_settings(domain.WEAK),output=tmp_path/'weak')
    assert result['execution_status']=='SUCCEEDED',result
    studies=result['diagnostics']['mesh_studies']
    assert len(studies)==2 and max(r['l2_error'] for r in studies)<1e-8
    assert max(r['h1_seminorm_error'] for r in studies)<1e-7
    assert studies[0]['l2_unit']=='(K)*m' and studies[0]['h1_unit']=='K'
    fields=result['diagnostics']['native_fields']
    assert all(f['field']['coordinates_unit']=='m' and f['field']['field_unit']=='K' for f in fields)
    assert len(write_post_sets(fields,tmp_path/'post'))==2
    assert read_result(tmp_path/'weak',verify='all')['execution_status']=='SUCCEEDED'



def test_ode_names_do_not_overwrite_actual_states_or_failed_reference(tmp_path):
    from caelab.evaluation import run
    s=domain.default_settings(domain.ODE)
    row=s['states'][0];row.update(name='q',rhs='-rate*(q-ambient)')
    other=deepcopy(row);other.update(name='q_reference',label='다른 온도',initial=305.,
        rhs='-rate*(q_reference-ambient)',reference='')
    s['states'].append(other)
    result=run(domain.ODE,s,output=tmp_path/'distinct')
    assert result['execution_status']=='SUCCEEDED'
    channels=result['diagnostics']['response_channels']['q']
    assert channels['reference']!='q_reference'
    assert result['responses']['q_reference']['value'][0]==305.
    assert result['responses'][channels['reference']]['value'][0]==300.
    s['states'][0]['reference']='ambient*log(-1)'
    bad=run(domain.ODE,s,output=tmp_path/'bad-reference')
    assert bad['execution_status']=='SUCCEEDED'
    assert len(bad['responses']['q']['value'])==101
    assert bad['diagnostics']['reference_errors']['q']
    assert bad['diagnostics']['response_channels']['q']=={'state':'q'}
    assert bad['responses']['q_reference']['value'][0]==305.


def test_actual_scipy_cancel_retains_accepted_clock_not_trial_rhs(tmp_path,monkeypatch):
    from caelab.evaluation import run,read_result
    from caelab.adapters import dimensioned_ode
    from caelab.execution_control import ExecutionCancelled
    calls=0
    def cancel():
        nonlocal calls
        calls+=1
        if calls>60:raise ExecutionCancelled('controlled cancellation of real SciPy')
    monkeypatch.setattr(dimensioned_ode,'check_cancelled',cancel)
    result=run(domain.ODE,domain.default_settings(domain.ODE),output=tmp_path/'cancel')
    assert result['execution_status']=='CANCELLED'
    clock=result['responses']['temperature']['axes'][0]['values']
    assert 1<len(clock)<101 and list(clock)==sorted(clock)
    assert clock[-1]<=result['diagnostics']['last_accepted']['time']
    assert result['diagnostics']['accepted_steps']>0 and result['diagnostics']['partial_output']
    import numpy as np
    assert np.array_equal(read_result(tmp_path/'cancel',verify='all')['responses']['temperature']['value'],result['responses']['temperature']['value'])


def test_ode_tolerance_and_operation_capabilities():
    from caelab.backends import list_backends
    draft=default_draft(domain.ODE);draft['settings']['solver']['rtol']=1e-25
    assert diagnostics(draft)[0]['path']=='settings.solver.rtol'
    rows={row['id']:row for row in list_backends()}
    for name in (domain.ODE,domain.WEAK,'material.mfront.user'):
        assert rows[name]['roles']==['evaluation'] # run owner/candidates, not legacy solve API
