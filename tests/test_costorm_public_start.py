"""Real discussion admission without network, model execution or submitted jobs."""
from copy import deepcopy

import pytest

from caelab.discussion_costorm import start_record, arguments
from caelab.discussion_document import default_draft
from caelab.workbench import Workbench


@pytest.fixture
def opened(tmp_path):
    workbench = Workbench(tmp_path, configuration={'experts': [{'id': 'testing',
        'instructions': 'Use the selected sources.', 'collections': [], 'tools': []}]})
    draft = default_draft()
    draft['participants'] = ['testing']
    draft['composer']['text'] = 'What should be investigated?'
    draft['context']['discussion_mode'] = 'costorm'
    document = workbench.document_open(kind='expert', draft=draft)
    owner = workbench.discussion_documents
    try:
        yield workbench, owner, owner._documents[document['id']]
    finally:
        workbench.shutdown()


@pytest.mark.parametrize('permission', [None, False, 'true', 1])
def test_no_source_requires_explicit_public_permission(opened, permission):
    workbench, owner, document = opened
    document['draft']['context']['transmission_scope'] = {'allow_public_search': permission}
    with pytest.raises(ValueError, match='공개 문헌 검색'):
        start_record(owner, document, 'Cstart', action='start', turn={'id': 'Uquestion'})
    assert document['discussion']['rounds'] == []
    assert workbench.manager.list() == []


def test_public_topic_prepares_request_without_a_dummy_local_file(opened):
    workbench, owner, document = opened
    document['draft']['context']['transmission_scope'] = {'allow_public_search': True}
    before = deepcopy(document['draft'])
    record = start_record(owner, document, 'Cstart', action='start', turn={'id': 'Uquestion'})
    request = arguments(owner, document, record, 'testing')
    assert request['context']['selected_sources'] == []
    assert request['context']['transmission_scope']['allow_public_search'] is True
    assert record['knowledge_sources'] == [] and record['status'] == 'READY'
    assert document['draft'] == before
    assert workbench.manager.list() == []  # Operator/runtime permission is checked before actual inference.


def test_selected_result_still_requires_its_existing_exact_owner_validation(opened):
    workbench, owner, document = opened
    reference = {'document_id': 'Dsource', 'job_id': 'Jsource',
                 'input_revision': 'Ioriginal', 'input_sha256': 'a' * 64, 'selection': ['displacement']}
    owner.resolve_document = lambda identifier: {'runs': [deepcopy(reference)]}
    reads = []
    owner.resolve_result = lambda document_id, job_id, selection: reads.append((document_id, job_id, selection))
    document['draft']['composer']['evidence'] = [reference]
    record = start_record(owner, document, 'Cstart', action='start', turn={'id': 'Uquestion'})
    assert record['knowledge_sources'] == []
    assert reads == [('Dsource', 'Jsource', ['displacement'])]
    assert workbench.manager.list() == []


def test_wrong_result_revision_does_not_bypass_empty_source_guard(opened):
    workbench, owner, document = opened
    reference = {'document_id': 'Dsource', 'job_id': 'Jsource',
                 'input_revision': 'Iwrong', 'input_sha256': 'a' * 64, 'selection': []}
    owner.resolve_document = lambda identifier: {'runs': [{**reference, 'input_revision': 'Ioriginal'}]}
    owner.resolve_result = lambda *args, **kwargs: pytest.fail('Do not read the wrong result')
    document['draft']['composer']['evidence'] = [reference]
    with pytest.raises(ValueError, match='exact retained job input'):
        start_record(owner, document, 'Cstart', action='start', turn={'id': 'Uquestion'})
    assert not document['discussion']['rounds']
    assert workbench.manager.list() == []
