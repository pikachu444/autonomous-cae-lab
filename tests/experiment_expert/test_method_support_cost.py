"""Current-request support costs use the same retained gates as preparation."""
from copy import deepcopy

import pytest

from caelab.experiment_analysis_actions import read_analysis_source
from caelab.experiment_analysis_service import final_request, prepare_request
from caelab.storage import canonical_hash
from .support import ServiceHost
from .test_actions import Client
from .test_final_diagnosis import direct_problem, algebra
from .test_service import algebra_registered


def test_near_boundary_preview_tracks_current_step_without_model_calls(tmp_path, algebra_registered):
    problem=direct_problem(two=False)
    problem['variables'][0].update(lower=0.,upper=1.)
    problem['candidate']['values']['x']=5e-5
    from caelab.numerical_candidate_detail import trial_detail
    problem['selected_trials']=[trial_detail(e,algebra(problem['candidate']['values'],e['settings']),
        origin={'kind':'fit_candidate','candidate_id':'Cselected'}) for e in problem['experiments']]
    with ServiceHost(tmp_path) as host:
        _,_,reference=host.original(problem)
        client=Client(host);jobs=len(host.manager.list())
        for step,cost in ((1e-4,4),(1e-5,5)):
            preview=read_analysis_source(client,evidence_reference=reference,relative_step=step)
            prepared=prepare_request(host.core,final_request(reference,evaluations=5,relative_step=step))
            assert preview['model_evaluations']==prepared['cost']['model_evaluations']==cost
            assert preview['derivative_methods'][1]['cost']==cost
            assert preview['performed_model_calls']==0
        assert len(host.manager.list())==jobs


def test_preview_validates_exact_reused_jacobian_and_reports_zero(tmp_path, algebra_registered):
    with ServiceHost(tmp_path) as host:
        _,_,reference=host.original(direct_problem())
        plan,job,result=host.run_plan(final_request(reference,evaluations=9))
        host.save(plan)
        reuse=host.core.document_result_reference(plan,job)
        before=canonical_hash(result);jobs=len(host.manager.list())
        request=final_request(reference,evaluations=1,reuse_result=reuse)
        preview=read_analysis_source(Client(host),evidence_reference=reference,
                                     relative_step=1e-5,reuse_result=reuse)
        assert preview['model_evaluations']==prepare_request(host.core,request)['cost']['model_evaluations']==0
        assert preview['derivative_methods'][1]['cost']==0
        changed=deepcopy(reuse);changed['result_sha256']='a'*64
        with pytest.raises(ValueError,match='hash changed'):
            read_analysis_source(Client(host),evidence_reference=reference,reuse_result=changed)
        assert len(host.manager.list())==jobs
        assert canonical_hash(host.owner.result(plan,job))==before
