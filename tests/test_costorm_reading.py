"""Focused owner/reference and citation reads. No provider or solver execution."""
from copy import deepcopy
from types import SimpleNamespace
import pytest

from apps.lab.workbench_routes import handle
from apps.lab.service import ServiceError
from apps.research.desktop import open_evidence_reference
from caelab.study_document import StudyDocuments
from test_study_documents import research_draft, NeverRun


def test_available_reference_replaces_initial_unknown_message(tmp_path):
    owner = StudyDocuments(tmp_path, 'Ssession', NeverRun(), NeverRun(),
        resolve_reference=lambda reference: {'status': 'AVAILABLE'})
    rows = owner.validate_references(research_draft())
    assert all(row['status'] == 'AVAILABLE' and row['message'] == 'Exact saved source is available' for row in rows)
    owner.resolve_reference = lambda reference: {'status': 'UNAVAILABLE', 'message': 'Saved source missing'}
    assert all(row['message'] == 'Saved source missing' for row in owner.validate_references(research_draft()))


class ReadOnlyClient:
    """Transport spy for exact local reads, never a fake inference result."""
    def __init__(self):
        self.calls = []

    def request(self, path, payload=None):
        self.calls.append((path, deepcopy(payload)))
        if path.endswith('/assist'):
            return {'status': 'abstract_only', 'paper': {'title': 'Archived paper'}, 'segments': []}
        assert path == '/api/workbench/jobs/Jrecord'
        return {'id': 'Jrecord', 'state': 'RUNNING'}

    def result(self, identifier, *, selection):
        self.calls.append((identifier, deepcopy(selection)))
        return {'execution_status': 'SUCCEEDED', 'responses': {}}


def test_citations_keep_archive_channel_scope_and_do_not_invent_document_refs():
    client = ReadOnlyClient()
    reference = {'paper_id': 'doi:10.0000/test', 'locator': {'archive_id': 'a' * 64, 'page': 2}}
    assert open_evidence_reference(client, reference)['source']['title'] == 'Archived paper'
    assert client.calls[-1][1]['arguments'] == reference
    with pytest.raises(ValueError, match='no retained'):
        open_evidence_reference(client, {'paper_id': reference['paper_id'], 'locator': {'page': 2}})
    assert len(client.calls) == 1
    result = {'run_id': 'Jrecord', 'response_selection': ['stress']}
    opened = open_evidence_reference(client, result)
    assert opened['reference'] == result and 'document_id' not in opened['reference']
    assert client.calls[-1] == ('Jrecord', {'responses': ['stress'], 'rows': [0, 256]})
    status = open_evidence_reference(client, {'run_id': 'Jrecord', 'response_selection': []})
    assert status['payload']['job']['state'] == 'RUNNING'
    assert client.calls[-1] == ('/api/workbench/jobs/Jrecord', None)


def test_sync_literature_route_requires_exact_archive_and_preserves_locator():
    calls = []
    workbench = SimpleNamespace(assistance_call=lambda operation, arguments:
        calls.append((operation, deepcopy(arguments))) or {'segments': []})
    body = {'operation': 'literature.read',
            'arguments': {'paper_id': 'doi:10.0000/test', 'locator': {'archive_id': 'b' * 64, 'page': 3}}}
    handler = SimpleNamespace(server=SimpleNamespace(workbench=workbench),
        _json_body=lambda: deepcopy(body), _json=lambda status, payload: (status, payload))
    assert handle(handler, 'POST', '/api/workbench/assist', {}) == (200, {'segments': []})
    assert calls == [('literature.read', body['arguments'])]
    for locator in ({}, {'page': 3}, {'archive_id': '../outside'}, {'archive_id': None}):
        body['arguments']['locator'] = locator
        with pytest.raises(ServiceError):
            handle(handler, 'POST', '/api/workbench/assist', {})
    assert len(calls) == 1


def test_actual_packed_candidate_reference_reads_nested_values_and_masks(tmp_path):
    pytest.importorskip('numpy')
    from caelab.evaluation import save_evaluation, read_result
    from caelab.research_workflows import resolve_reference
    from caelab.storage import canonical_hash
    result = {'kind': 'doe', 'candidates': [
        {'candidate_id': 'Csuccess', 'execution_status': 'SUCCEEDED', 'responses': {
            'stress': {'kind': 'series', 'unit': 'MPa', 'value': [0, 2, 3],
                'axes': [{'name': 'strain', 'unit': '1', 'values': [0, .1, .2]}],
                'mask': [True, False, True], 'source_rows': [11, 12, 13]}}},
        {'candidate_id': 'Cfailed', 'execution_status': 'FAILED', 'failure_reason': 'Binding failed', 'responses': {}}]}
    folder = tmp_path / 'retained'
    save_evaluation(result, folder)
    actual = read_result(folder, verify='all')
    reference = {'kind': 'result', 'document_id': 'Noriginal', 'job_id': 'Jactual',
        'input_revision': 'Isaved', 'input_sha256': 'a' * 64, 'result_sha256': canonical_hash(actual),
        'selection': {'responses': ['stress'], 'rows': [1, 3]}}
    reads = []
    def read(document_id, job_id, selection=None):
        assert (document_id, job_id) == ('Noriginal', 'Jactual')
        reads.append(deepcopy(selection))
        return read_result(folder, verify='all', selection=selection)
    wb = SimpleNamespace(
        document_read=lambda identifier: {'id': identifier, 'runs': [{'job_id': 'Jactual',
            'input_revision': 'Isaved', 'input_sha256': 'a' * 64,
            'retention_complete': True, 'retained_result': {'revision': 'Rresult'}}]},
        document_result=read)
    opened = resolve_reference(wb, reference)
    response = opened['result']['candidates'][0]['responses']['stress']
    assert response['value'] == [2, 3] and response['mask'] == [False, True]
    assert response['axes'][0]['values'] == [.1, .2] and response['source_rows'] == [12, 13]
    assert response['unit'] == 'MPa'
    assert opened['result']['candidates'][1] == actual['candidates'][1]
    assert opened['reference'] == reference and reads == [None]
    assert canonical_hash(read_result(folder, verify='all')) == reference['result_sha256']
    with pytest.raises(ValueError, match='Unknown candidate'):
        resolve_reference(wb, {**reference, 'selection': {'responses': ['missing']}})
