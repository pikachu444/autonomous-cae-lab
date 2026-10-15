"""Dedicated identity, failure and actual shared-dispatcher regressions.

The dispatcher test deliberately bypasses only Workbench.__init__ (its native
imports are absent from the supplied packet). It executes the unchanged real
submit/resource/_execute methods, not a replacement HTTP service.
"""
from copy import deepcopy
import shutil
import threading
from types import SimpleNamespace

import pytest

from caelab import numerical
from caelab.evaluation import PreparedEvaluation
from caelab.numerical_candidate_detail import (
    DetailIdentityError, read_candidate_detail, table_rows, compare_candidate_details,
    backend_binding, validate_backend_binding, prepare_detail_arguments,
)
from caelab.storage import canonical_hash
from _numerical_candidate_detail_support import DetailHost, synthetic, synthetic_inputs, intermediate


def test_actual_workbench_submit_and_execute_dispatcher(tmp_path,monkeypatch):
    from caelab import backends
    from caelab.workbench import Workbench
    name='test.candidate-detail.synthetic'
    monkeypatch.setitem(backends._registry,name,backends.Backend(name,('prepared',),lambda:synthetic))
    with DetailHost(tmp_path) as host:
        core=Workbench.__new__(Workbench)
        core.root,core.workspace_id,core.config=tmp_path,'test-dispatcher',{}
        core.manager,core.numerical_documents=host.manager,host.owner
        core._assist_config_lock=threading.RLock()
        host.manager._execute=core._execute
        host.owner.submit=core.submit
        doc,job=host.create_fit()
        candidate=intermediate(host,doc,job)
        original=host.owner.result(doc,job)
        binding=original['fit_input_snapshot']['evaluator_binding']
        assert binding['adapter_source_sha256'] and binding['backend']==name
        view=core.numerical_candidate_detail(doc,job,candidate)
        detail=host.detail(view)['job']['id']
        assert host.wait(detail)['state']=='SUCCEEDED'
        after=host.view(doc,job,candidate,attempt_job_id=detail)
        assert after['trials'][:2]==view['trials'][:2]
        assert host.owner.result(doc,detail)['timing']['model_calls']==1
        # This is an evaluator-registration change, not a current Plan edit.
        failed=intermediate(host,doc,job,'FAILED')
        before_count=len(host.manager.list())
        monkeypatch.setitem(backends._registry,name,backends.Backend(name,('prepared',),lambda:synthetic,threads=2))
        with pytest.raises(DetailIdentityError,match='registration/config/version'):
            host.detail(host.view(doc,job,failed))
        assert len(host.manager.list())==before_count
        assert canonical_hash(host.owner.result(doc,job))==canonical_hash(original)


def test_cancelled_partial_raw_output_is_not_complete_and_can_retry(tmp_path):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0))
        cid=intermediate(host,doc,job)
        def partial(values,settings):
            result=synthetic(values,settings)
            result['execution_status']='CANCELLED'
            result['diagnostics']['partial_output']='Synthetic partial protocol output'
            return result
        host.evaluator=partial
        detail=host.detail(host.view(doc,job,cid))['job']['id']
        assert host.wait(detail)['state']=='CANCELLED'
        stopped=host.view(doc,job,cid,attempt_job_id=detail)
        assert stopped['trials'][0]['retention']=='PARTIAL_OUTPUT'
        assert stopped['trials'][0]['raw_evaluation']['responses']
        assert stopped['missing_experiments']==['T0','T1','T2']
        assert all(r['prediction'] is None for r in table_rows(stopped,'T0'))
        host.evaluator=synthetic
        retry=host.detail(stopped)['job']['id'];assert host.wait(retry)['state']=='SUCCEEDED'
        assert host.view(doc,job,cid,attempt_job_id=detail)['trials']==stopped['trials']
        assert host.view(doc,job,cid,attempt_job_id=retry)['missing_experiments']==[]


def test_trial_prepare_failure_and_metadata_failure_keep_other_trials(tmp_path):
    closed=[]
    class Factory:
        def prepare(self,settings,*,runtime=None):
            if settings['factor']==2:
                raise RuntimeError('Deliberate trial preparation failure')
            def evaluate(values):
                result=synthetic(values,settings)
                if settings['factor']==3:
                    result['responses']['stress']['unit']='Pa'
                return result
            return PreparedEvaluation(evaluate,settings,close=lambda:closed.append(settings['factor']))
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0))
        cid=intermediate(host,doc,job)
        host.evaluator=Factory()
        detail=host.detail(host.view(doc,job,cid))['job']['id']
        assert host.wait(detail)['state']=='PARTIAL_FAILURE'
        view=host.view(doc,job,cid,attempt_job_id=detail)
        assert [t['execution_status'] for t in view['trials']]==['SUCCEEDED','FAILED','FAILED']
        assert closed==[1.,3.]
        assert view['trials'][1]['raw_evaluation']['diagnostics']['phase']=='PREPARE_OR_CLOSE'
        assert view['trials'][2]['evaluation_status']=='SUCCEEDED' # engine succeeded, comparison did not
        assert view['trials'][2]['raw_evaluation']['responses']['stress']['unit']=='Pa'
        assert all(r['prediction'] is None for r in table_rows(view,'T2'))


def test_legacy_inline_missing_and_ambiguous_final_never_evaluates(tmp_path,monkeypatch):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit()
        original=host.owner.result(doc,job)
        cid=intermediate(host,doc,job)
        legacy=deepcopy(original)
        legacy.pop('fit_input_snapshot');legacy.pop('final_candidate_detail')
        for row in legacy['candidates']:
            row.pop('candidate_detail',None)
        monkeypatch.setattr(host.owner,'result',lambda *args,**kwargs:deepcopy(legacy))
        view=host.view(doc,job,cid)
        assert all(t['retention']=='NOT_RETAINED' for t in view['trials'])
        assert all(r['prediction'] is None for r in table_rows(view,'T0'))
        best=next(r for r in legacy['candidates'] if r['values']==legacy['parameters'])
        legacy['candidates'].append({**deepcopy(best),'candidate_id':'DuplicateValues'})
        view=host.view(doc,job,best['candidate_id'])
        assert all(t['retention']=='NOT_RETAINED' for t in view['trials'])
        document=host.owner.read(doc)
        run=next(r for r in document['runs'] if r['job_id']==job)
        run['arguments']['experiments'][0].pop('observations')
        run['arguments']['experiments'][0]['observation_job']='MutableOldJob'
        owner=SimpleNamespace(read=lambda ident:document,result=host.owner.result,manager=host.manager)
        with pytest.raises(DetailIdentityError,match='inline'):
            read_candidate_detail(owner,doc,job,cid)
        assert len(host.manager.list())==1


def test_retention_does_not_change_original_search_results_or_call_count():
    def fit(retain):
        calls=[]
        inputs=synthetic_inputs(retain=retain);inputs.pop('backend')
        result=numerical.fit_model(lambda v,s:(calls.append((v,s)) or synthetic(v,s)),**inputs)
        rows=[{key:row.get(key) for key in ('candidate_id','values','execution_status','objective','failure_reason')}
              for row in result['candidates']]
        return rows,result['parameters'],result['curves'],calls
    assert fit(0)==fit(32)


def test_unknown_attempt_state_blocks_new_submission_without_inventing_results(tmp_path,monkeypatch):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit()
        cid=intermediate(host,doc,job)
        detail=host.detail(host.view(doc,job,cid))['job']['id'];host.wait(detail)
        original=host.manager.status
        def status(ident):
            if ident==detail:
                raise KeyError('Receipt unavailable')
            return original(ident)
        monkeypatch.setattr(host.manager,'status',status)
        view=host.view(doc,job,cid,attempt_job_id=detail)
        assert view['attempt_state']=='UNKNOWN' and not view['can_detail_eval']
        assert view['trials'][2]['retention']=='NOT_RETAINED'
        assert view['trials'][2]['execution_status']=='UNKNOWN'
        assert len(host.manager.list())==2


def test_saved_completed_detail_after_korean_path_move(tmp_path):
    old,new=tmp_path/'original',tmp_path/'이동한 폴더 한글 공백'
    with DetailHost(old) as host:
        doc,job=host.create_fit();cid=intermediate(host,doc,job)
        detail=host.detail(host.view(doc,job,cid))['job']['id'];host.wait(detail)
        view=host.view(doc,job,cid,attempt_job_id=detail)
        host.command(doc,'document.save',{})
    shutil.move(old,new)
    # Transient solver results are not required once saved into the owner revision.
    shutil.rmtree(new/'results')
    with DetailHost(new,evaluator=lambda *args:pytest.fail('Move/reopen evaluated')) as reopened:
        after=reopened.view(doc,job,cid,attempt_job_id=detail)
        assert table_rows(after,'T2')==table_rows(view,'T2')
        assert reopened.dispatched==[] and len(reopened.manager.list())==2


def test_external_binding_is_a_digest_not_private_configuration(tmp_path):
    configuration={'label':'Test executor','argv':['program','--private','not-for-results'],
                   'environment':{'PASSWORD':'not-for-results'},'threads':1}
    core=SimpleNamespace(config={'external_backends':{'custom.file':configuration}},
        backends=lambda:[{'id':'custom.file','roles':['external']}])
    binding=backend_binding(core,'custom.file')
    assert binding['external_configuration_sha256']==canonical_hash(configuration)
    assert 'not-for-results' not in str(binding)
    changed=deepcopy(configuration);changed['threads']=2
    core.config['external_backends']['custom.file']=changed
    assert backend_binding(core,'custom.file')!=binding


def test_event_states_and_retained_absence_are_not_zero_values():
    from caelab.numerical_candidate_detail import trial_detail, experiment_snapshot
    from _numerical_candidate_detail_support import response
    observed=numerical.detect_event(response([0.,1.,2.,3.]),2.)
    predicted=numerical.detect_event(response([0.,.5,1.,1.5]),2.)
    experiment=experiment_snapshot(dict(id='crossing',role='holdout',response='crossing',
        observations=observed,weight=2.,scale=1.,nonoccurrence_penalty=5.))
    trial=trial_detail(experiment,{'execution_status':'SUCCEEDED','responses':{'crossing':predicted}},
                       origin={'kind':'fit_candidate','candidate_id':'C0'})
    view={'candidate':{'candidate_id':'C0'},'fit_input':{'inputs':{'experiments':[experiment]}},'trials':[trial]}
    row=table_rows(view,'crossing')[0]
    assert row['observation_state']=='OCCURRED' and row['prediction_state']=='NOT_OBSERVED'
    assert row['prediction'] is None and row['raw_residual'] is None
    assert row['retention']=='RETAINED' and row['weighted_residual'] is not None
