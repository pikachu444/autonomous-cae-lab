from copy import deepcopy
import shutil
import uuid
import numpy as np
import pytest
from caelab.experiment_analysis_service import uncertainty_request, final_request, prepare_request
from caelab.experiment_final_diagnosis import read_jacobian
from caelab.numerical_candidate_detail import backend_binding
from caelab.backends import _registry,Backend
from caelab.evaluation import PreparedEvaluation,save_evaluation,read_result
from caelab.storage import canonical_hash
from .support import ServiceHost
from .test_uncertainty import calibration,imported,calibration_problem,spec
from .test_final_diagnosis import direct_problem,algebra

class PublicAlgebra:
    version='public-fixture-1'
    def prepare(self,settings,runtime=None):
        return PreparedEvaluation(lambda values:algebra(values,settings),settings)

@pytest.fixture
def algebra_registered(monkeypatch):
    monkeypatch.setitem(_registry,'public.algebra',Backend('public.algebra',('model',),PublicAlgebra))


def test_final_plan_actual_service_evidence_owner_save_cold_reopen(tmp_path,algebra_registered):
    with ServiceHost(tmp_path/'wb') as h:
        source,original,reference=h.original(direct_problem(loss='soft_l1'))
        original_hash=canonical_hash(h.owner.result(source,original))
        req=final_request(reference,evaluations=9)
        preview=prepare_request(h.core,req)
        assert preview['cost']['model_evaluations']==9
        calls=len(h.manager.list())
        plan,job,r=h.run_plan(req)
        assert r['execution_status']=='SUCCEEDED',r
        assert r['timing']['model_calls']==9
        assert len(h.manager.list())==calls+1
        assert read_jacobian(r,r['experiment_analysis']['source_problem'])
        saved=h.save(plan)
        selected=h.core.document_result_reference(plan,job)
        p,rj,reused=h.run_plan(final_request(reference,evaluations=1,reuse_result=selected))
        assert reused['timing']['model_calls']==0
        assert canonical_hash(h.owner.result(source,original))==original_hash
        stored=canonical_hash(h.owner.result(plan,job))
    with ServiceHost(tmp_path/'wb') as cold:
        before=len(cold.manager.list())
        actual=cold.owner.result(plan,job)
        assert canonical_hash(actual)==stored
        assert read_jacobian(actual,actual['experiment_analysis']['source_problem'])
        assert len(cold.manager.list())==before


def test_missing_original_evaluator_binding_blocks_new_evaluation_but_not_read(tmp_path,algebra_registered):
    with ServiceHost(tmp_path) as h:
        doc,job,ref=h.original(direct_problem(),binding=False)
        before=len(h.manager.list())
        assert h.owner.result(doc,job)['kind']=='fit'
        with pytest.raises(ValueError,match='evaluator'):
            prepare_request(h.core,final_request(ref,evaluations=9))
        assert len(h.manager.list())==before


def test_failed_source_diagnostic_cannot_be_success_or_evaluated(tmp_path,algebra_registered):
    with ServiceHost(tmp_path) as h:
        source,orig,ref=h.original(direct_problem(),failed=True)
        plan,job,r=h.run_plan(final_request(ref,evaluations=9))
        assert r['execution_status']=='REJECTED'
        assert r['timing']['model_calls']==0
        assert r['identification']['status']=='UNKNOWN'


def test_tampered_prepared_request_not_admitted(tmp_path,algebra_registered):
    with ServiceHost(tmp_path) as h:
        _,_,ref=h.original(direct_problem())
        args=prepare_request(h.core,final_request(ref,evaluations=9))
        before=len(h.manager.list())
        args['problem']['candidate']['values']['x']+=.1
        with pytest.raises(ValueError,match='달라졌'):
            h.core.submit('identification_final',args)
        assert len(h.manager.list())==before
