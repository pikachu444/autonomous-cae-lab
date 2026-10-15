"""Parent verification follows retained nested reads; raw success stays intact."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from caelab import research_workflows as workflows
from caelab.evaluation import file_hash
from caelab.numerical_adjoint import invalidate_unverified_candidates


@pytest.mark.parametrize('status', [None, 'PASS', 'FAIL', 'INCOMPLETE'])
@pytest.mark.parametrize('parent_status', ['SUCCEEDED', 'FAILED', 'CANCELLED'])
def test_parent_verification_survives_catalog_composite_and_attempt(tmp_path, monkeypatch, status, parent_status):
    native = tmp_path / 'candidate' / 'derivatives' / 'AFirst'
    native.mkdir(parents=True)
    raw = {'execution_status': 'SUCCEEDED', 'derivatives': {'k': {'value': -0.1, 'unit': 'K m/W'}}}
    (native / 'result.json').write_text(json.dumps(raw), encoding='utf-8')
    composite = {'execution_status': 'SUCCEEDED', 'stages': [], 'derivative_attempts': [
        {'attempt_id': 'AFirst', 'result_directory': 'derivatives/AFirst', 'primal_reference': {}}]}
    directory = native.parent.parent
    (directory / 'result.json').write_text(json.dumps(composite), encoding='utf-8')
    candidate = {'candidate_id': 'CFirst', 'execution_status': 'SUCCEEDED', 'purpose': 'optimization',
        'gradients': {'temperature': {'k': {'value': -0.1, 'unit': 'K m/W'}}},
        'evaluation_refs': [{'relative': 'candidate', 'result_sha256': file_hash(directory / 'result.json')}]}
    parent = {'execution_status': parent_status, 'candidates': [candidate]}
    if status is not None:
        parent['gradient_verification'] = {'status': status}
        invalidate_unverified_candidates(parent['candidates'], parent['gradient_verification'])
    before = {p: p.read_bytes() for p in (directory / 'result.json', native / 'result.json')}

    owner = object()
    wb = SimpleNamespace(numerical_documents=owner, _document_owner=lambda _: owner)
    monkeypatch.setattr(workflows, 'result_folder', lambda *args: (tmp_path, owner))
    def retained_read(folder, **kwargs):
        if folder == tmp_path:
            return deepcopy(parent)
        return json.loads((folder / 'result.json').read_text(encoding='utf-8'))
    monkeypatch.setattr(workflows, 'read_result', retained_read)

    for choice in ({}, {'evaluation_index': 0}, {'evaluation_index': 0, 'attempt_id': 'AFirst'}):
        viewed = workflows.numerical_evaluation_result(wb, 'NFirst', 'JFirst', 'CFirst', **choice)
        assert viewed['candidate_purpose'] == 'optimization'
        assert viewed['parent_execution_status'] == parent_status
        assert viewed['candidate_execution_status'] == 'SUCCEEDED'
        assert viewed['candidate_gradient_admission'] == candidate.get('gradient_admission')
        assert viewed.get('gradient_verification') == parent.get('gradient_verification')
        if choice:
            assert viewed['execution_status'] == 'SUCCEEDED'
        if 'attempt_id' in choice:
            assert viewed['derivatives'] == raw['derivatives']
    assert {p: p.read_bytes() for p in before} == before
