"""Method descriptions never admit a job or rewrite a retained result."""
from copy import deepcopy

import pytest

from caelab.linear_adjoint_contract import describe_methods,describe_result_method
from caelab.research_operations import result_metadata
from caelab.storage import canonical_hash


def test_profile_support_is_separate_from_runtime_and_candidate_diagnostics():
    profile={'available':False,'reasons':['Picard is outside the linear profile']}
    rows=describe_methods(adjoint=profile)
    assert [r['method'] for r in rows]==['slsqp_adjoint','identification_final','differential_evolution']
    assert [r['problem_support'] for r in rows]==['UNSUPPORTED','UNASSESSED','UNASSESSED']
    assert all(r['runtime']=='NOT_PROBED' and r['runtime_available'] is None for r in rows)
    assert rows[0]['reasons']==profile['reasons']
    exact=describe_methods(diagnostic={'available':True,'reasons':[],'cost':5})
    assert exact[1]['problem_support']=='SUPPORTED' and exact[1]['cost']==5
    assert exact[0]['problem_support']=='UNASSESSED'


@pytest.mark.parametrize('result,method',[
    ({'kind':'optimization','method':'slsqp_adjoint','execution_status':'FAILED'},'slsqp_adjoint'),
    ({'kind':'optimization','algorithm':{'engine':'scipy.differential_evolution'}},'differential_evolution'),
    ({'kind':'experiment_identification','optimizer_method':'de',
      'experiment_analysis':{'ordinary_jacobian':{'kind':'ordinary_residual_jacobian'}}},'identification_final'),
    ({'kind':'experiment_identification','optimizer_method':'de','experiment_analysis':{}},None),
    ({'kind':'experiment_identification','experiment_analysis':None},None),
    ({'kind':'experiment_identification','experiment_analysis':{'ordinary_jacobian':'unknown legacy'}},None),
    ({'kind':'optimization','algorithm':None},None),
    ({'kind':'optimization','algorithm':'unknown legacy algorithm'},None),
])
def test_retained_identity_does_not_invent_success_or_relabel_the_source_optimizer(result,method):
    before=deepcopy(result);digest=canonical_hash(result)
    described=describe_result_method(result)
    assert (described['method'] if described else None)==method
    assert result_metadata(result)['derivative_method']==described
    if described:assert described['execution_status']==result.get('execution_status','UNKNOWN')
    assert result==before and canonical_hash(result)==digest
