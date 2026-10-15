"""Optional real installed FELUPE, never replaced by the algebra fixtures."""
from copy import deepcopy
import pytest
pytest.importorskip('felupe',reason='NOT_RUN: installed FELUPE material runtime required')
from caelab.evaluation import evaluate
from caelab.numerical_candidate_detail import plain
from caelab.numerical_candidate_evidence import DetailEvidenceBlocked, FAILURE, resolve_candidate_evidence
from caelab.storage import canonical_hash
from _numerical_candidate_detail_support import DetailHost, intermediate
from test_numerical_candidate_detail_felupe import histories
from test_numerical_candidate_evidence_c1 import capture, complete


def test_real_felupe_bounded_multi_trial_candidate_evidence_success_and_failure(tmp_path):
    experiments=[]
    for i,protocol in enumerate(histories()):
        response='stress_xy' if i==1 else 'stress_xx'
        actual=plain(evaluate('material.felupe',protocol,values={'mu':1.25}))
        assert actual['execution_status']=='SUCCEEDED' and actual['diagnostics']['library']=='felupe'
        obs=deepcopy(actual['responses'][response])
        obs.update(source_rows=[i*100+j for j in (2,5,9,12)],source_column_identity=3,
                   mask=[True,False,True,True])
        experiments.append(dict(id='Trial'+str(i),role='holdout' if i==2 else 'fit',response=response,
            observations=obs,settings=deepcopy(protocol),weight=2.+i,scale=2.,mask=[True,True,False,True],
            observation_source={'source_sha256':canonical_hash(actual)}))
    inputs=dict(backend='material.felupe',variables=[dict(id='mu',unit='MPa',value=1.,lower=-2.,upper=3.,transform='linear')],
        experiments=experiments,method='de',options=dict(seed=7,max_generations=1,population_size=6,
            detail_retention={'candidate_limit':0,'byte_limit':0}),
        execution=dict(mode='serial',workers=1,on_failure='continue',max_evaluations=128))
    with DetailHost(tmp_path,evaluator='material.felupe') as host:
        doc,job=host.create_fit(inputs)
        good,bad=intermediate(host,doc,job),intermediate(host,doc,job,'FAILED')
        original_hash=canonical_hash(host.owner.result(doc,job))
        for cid in (good,bad):
            before=host.view(doc,job,cid)
            assert all(t['retention']=='NOT_RETAINED' for t in before['trials'])
            with pytest.raises(DetailEvidenceBlocked): capture(host,before)
        assert len(host.manager.list())==1
        good_view=complete(host,doc,job,good)
        good_ref=capture(host,good_view)['reference']
        success=resolve_candidate_evidence(host.owner,good_ref,consumer='adoption')
        assert success['readiness']['success_judgment_permitted']
        assert all(t['raw_evaluation']['diagnostics']['library']=='felupe' for t in success['snapshot']['trials'])
        task=host.detail(host.view(doc,job,bad))['job']['id']
        assert host.wait(task)['state']=='FAILED'
        bad_view=host.view(doc,job,bad,attempt_job_id=task)
        bad_ref=capture(host,bad_view,purpose=FAILURE)['reference']
        failure=resolve_candidate_evidence(host.owner,bad_ref,consumer='failure_report')
        assert failure['readiness']['failure_diagnostic_permitted']
        with pytest.raises(DetailEvidenceBlocked): resolve_candidate_evidence(host.owner,bad_ref,consumer='adoption')
        assert canonical_hash(host.owner.result(doc,job))==original_hash
        assert all(t['retention']=='NOT_RETAINED' for t in host.view(doc,job,good)['trials'])
        assert len(host.manager.list())==3
