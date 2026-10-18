"""Archived Expert proposals retain their original execution input identity."""
from copy import deepcopy

import pytest

from caelab.connection_graph_refs import TypedReference
from caelab.portable_project_execution import TypedProjection,MAP_SCHEMA


def test_verified_expert_proposal_does_not_require_a_new_current_input_mapping():
    mapping={'schema':MAP_SCHEMA,'source_scope':'origin','target_scope':'copy',
        'documents':[{'source_document_id':'Xold','document_id':'Xcopy','kind':'expert'}],
        'inputs':[],'revisions':[]}
    projection=TypedProjection(mapping)
    reference={'discussion_id':'Xold','job_id':'Joriginal','input_revision':'Ioriginal',
        'input_sha256':'a'*64,'turn_id':'Aoriginal','proposal_index':0,'proposal_sha256':'b'*64}
    before=deepcopy(reference)
    actual=projection.reference(TypedReference((),'검증된 원 제안','proposal',reference))
    assert actual=={**reference,'discussion_id':'Xcopy'}
    assert reference==before


def test_nonexpert_result_still_requires_the_exact_input_mapping():
    projection=TypedProjection({'schema':MAP_SCHEMA,'source_scope':'origin','target_scope':'copy',
        'documents':[{'source_document_id':'Nold','document_id':'Ncopy','kind':'numerical'}],
        'inputs':[],'revisions':[]})
    with pytest.raises(KeyError):
        projection.reference(TypedReference((),'원 결과','result',
            {'document_id':'Nold','job_id':'Joriginal','input_revision':'Ioriginal','input_sha256':'a'*64}))
