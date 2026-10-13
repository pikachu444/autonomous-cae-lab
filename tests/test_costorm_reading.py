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
