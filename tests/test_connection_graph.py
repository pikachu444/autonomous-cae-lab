"""Actual owner catalog, exact references and read-only relationship inspection."""
from copy import deepcopy
import shutil

import pytest

from caelab.connection_graph import build_graph, saved_reference
from caelab.connection_graph_refs import TypedReference, draft_references
from caelab.evaluation import file_hash
from caelab.storage import canonical_hash
from examples.portable_connection_public import create_public_store, command, save


@pytest.fixture
def source(tmp_path):
    wb, docs = create_public_store(tmp_path / '연결 원본')
    try:
        yield wb, docs
    finally:
        wb.shutdown()


def snapshot(wb):
    runtime_lock = wb.workspace / 'workbench' / 'controller.lock'
    return {p.relative_to(wb.workspace).as_posix():
            (('runtime-lock', p.stat().st_size, p.stat().st_mtime_ns) if p == runtime_lock else file_hash(p))
            for p in wb.workspace.rglob('*') if p.is_file()}


def test_multiple_real_document_ids_no_tool_catalog_and_no_writes(source):
    wb, docs = source
    before = snapshot(wb)
    memory = {owner.kind: deepcopy(owner._documents) for owner in wb.research_owners()}
    graph = build_graph(wb)
    assert snapshot(wb) == before
    assert {owner.kind: owner._documents for owner in wb.research_owners()} == memory
    actual = {n['owner_id'] for n in graph['nodes'] if n['node_type'] == 'document'}
    assert {docs[k]['id'] for k in ('data', 'material', 'plan', 'second_plan')} == actual
    assert len([n for n in graph['nodes'] if n['node_type'] == 'document' and n['kind'] == 'numerical']) == 2
    assert not ({'material', 'numerical', 'fixture.cadquery'} & actual)
    assert {'FAILED', 'SUCCEEDED'} <= {n['status'] for n in graph['nodes']}
    assert graph['read_only'] and not graph['executed'] and wb._assistance is None


def test_saved_newer_revision_changed_input_and_missing_are_distinct(source):
    wb, docs = source
    # Material binding intentionally has no saved_revision; test recency on an
    # ACTUAL saved-revision reference, not a fabricated extension of that API.
    study = wb.document_open(kind='study')
    draft = deepcopy(study['draft'])
    draft['evidence'] = [{'id': 'Em', 'label': '저장 재료', 'kind': 'document',
                          'reference': saved_reference(docs['material']), 'note': ''}]
    study = save(wb, command(wb, study, 'study.update', {'draft': draft}))
    graph = build_graph(wb, [study['id']])
    def material_node(graph):
        return next(n for n in graph['nodes'] if n['node_type'] == 'reference' and n['owner_kind'] == 'material')
    before = material_node(graph)
    assert before['status'] == 'AVAILABLE'
    exact = deepcopy(before['exact_reference'])
    material = save(wb, docs['material'])  # same input, new saved revision
    assert material_node(build_graph(wb, [study['id']]))['status'] == 'NEWER_REVISION'
    draft = deepcopy(material['draft']); draft['settings']['parameters']['E'] += 100
    command(wb, material, 'material.update', {'draft': draft})
    changed = material_node(build_graph(wb, [study['id']]))
    assert changed['status'] == 'INPUT_CHANGED'
    assert changed['exact_reference'] == exact
    original = wb.research_reference(changed['exact_reference'])
    assert original['document']['draft'] == docs['material']['draft']
    # Both copies of the old exact input are unavailable; do not bind current draft.
    shutil.rmtree(wb.material_documents._folder(material['id']) / 'revisions')
    missing = build_graph(wb, [study['id']])
    assert any(n['node_type'] == 'reference' and n['status'] == 'BROKEN' and n['exact_reference'] is None
               for n in missing['nodes'])


def test_changed_saved_result_is_broken_not_success(source):
    wb, docs = source
    data = docs['data']
    run = data['runs'][0]
    result_path = (wb.data_documents._folder(data['id']) / 'revisions' /
                   run['retained_result']['revision'] / 'results' / run['job_id'] / 'result.json')
    result_path.write_text('tampered', encoding='utf-8')
    graph = build_graph(wb, [data['id']])
    assert any(n['node_type'] == 'run' and n['job_id'] == run['job_id'] and n['status'] == 'BROKEN'
               for n in graph['nodes'])
    assert not any(n['node_type'] == 'run' and n['job_id'] == run['job_id'] and n['status'] == 'SUCCEEDED'
                   for n in graph['nodes'])


def test_study_and_request_observation_typed_refs_only(source):
    wb, docs = source
    reference = saved_reference(docs['material'])
    study = wb.document_open(kind='study')
    draft = deepcopy(study['draft'])
    draft['question'] = 'Opaque text ' + docs['data']['id']
    draft['evidence'] = [{'id': 'Eref', 'label': '재료 근거', 'kind': 'document', 'reference': reference, 'note': ''}]
    study = save(wb, command(wb, study, 'study.update', {'draft': draft}))
    graph = build_graph(wb, [study['id']])
    refs = [n for n in graph['nodes'] if n['node_type'] == 'reference']
    assert len(refs) == 1 and refs[0]['owner_id'] == docs['material']['id']
    assert refs[0]['exact_reference'] == reference
    # Known inline typed positions only; similar keys elsewhere do not create relationships.
    raw = {'mode': 'request', 'source': None,
           'request': {'inputs': {'experiments': [{'observation_ref': {'result': {'document_id': docs['data']['id']}}}]}},
           'unknown_notes': {'document_id': docs['material']['id']}}
    values = list(draft_references('numerical', raw))
    assert len(values) == 1 and values[0].path == ('request', 'inputs', 'experiments', 0, 'observation_ref', 'result')


def test_exact_expert_turn_owner_id_not_confused_with_document_id():
    ref = TypedReference((), '근거', 'exact', {'kind': 'expert_turn', 'discussion_id': 'Xactual', 'turn_id': 'Tturn'})
    assert ref.document_id == 'Xactual'


def test_external_knowledge_does_not_query_provider_or_content(source, monkeypatch):
    wb, docs = source
    study = wb.document_open(kind='study')
    reference = {'kind': 'knowledge', 'document_id': 'Kpublic', 'revision': 1,
                 'locator': {}, 'source_sha256': 'a' * 64, 'content_sha256': 'b' * 64}
    draft = deepcopy(study['draft'])
    draft['evidence'] = [{'id': 'Ek', 'label': '명시 외부문헌', 'kind': 'knowledge', 'reference': reference, 'note': ''}]
    study = command(wb, study, 'study.update', {'draft': draft})
    def forbidden(*args, **kwargs):
        raise AssertionError('Graph may not call providers, saves, opens, readers with recovery, or result follow-ups')
    monkeypatch.setattr(wb, 'assistance_call', forbidden)
    monkeypatch.setattr(wb, 'document_open', forbidden)
    monkeypatch.setattr(wb, 'document_command', forbidden)
    graph = build_graph(wb, [study['id']])
    assert any(n['status'] == 'EXTERNAL' for n in graph['nodes'])


def test_missing_document_and_malformed_reference_visible(source):
    wb, docs = source
    graph = build_graph(wb, ['Mdoes_not_exist'])
    assert graph['nodes'][0]['status'] == 'BROKEN'
    assert graph['issues']
    fake = build_graph(wb, ['material'])
    assert all(n['status'] == 'BROKEN' for n in fake['nodes'])
    with pytest.raises(ValueError):
        build_graph(wb, ['../outside'])


def test_native_registered_ids_and_pre_explicit_job_links_read_only(source, monkeypatch):
    """Contract test with TEST_ONLY descriptors; NOT native GUI/physics acceptance."""
    import json
    wb, docs = source
    identifier = 'native_test_only_pre'
    origin = {'kind': 'pre', 'document_id': identifier, 'generation': 3, 'session_id': 'Snative'}
    link = {'job_id': 'Jabsent', 'origin': origin, 'operation': 'run', 'state_when_recorded': 'FAILED'}
    registration = wb.native_commands.register(host_id='Htest', session_id='Snative', application='freecad',
        version='TEST_ONLY', execution_mode='gui', registration_nonce='n' * 32,
        documents=[{'id': identifier, 'kind': 'pre', 'title': '검사용 CAD 원문서', 'generation': 3,
                    'view_generation': 1, 'dirty': True, 'project': {'links': [link]}}])
    def forbidden():
        raise AssertionError('Reading a graph must not expire/disconnect a native owner')
    monkeypatch.setattr(wb.native_commands, '_expire', forbidden)
    before = snapshot(wb)
    state = deepcopy(wb.native_commands._hosts)
    graph = build_graph(wb)
    assert snapshot(wb) == before and wb.native_commands._hosts == state
    doc = next(n for n in graph['nodes'] if n['key'] == 'document/' + identifier)
    assert doc['status'] == 'AVAILABLE' and doc['exact_reference'] is None
    assert any(n['node_type'] == 'run' and n['job_id'] == 'Jabsent' and n['status'] == 'BROKEN' for n in graph['nodes'])
    assert registration['host_token'] not in json.dumps(graph)
    assert 'host_token' not in json.dumps(graph) and 'registration_nonce' not in json.dumps(graph)
    # Old report is UNKNOWN without secretly disconnecting the host or replaying a command.
    wb.native_commands._hosts['Htest']['_seen'] -= 120
    graph = build_graph(wb, [identifier])
    assert graph['nodes'][0]['status'] == 'UNKNOWN'
    assert wb.native_commands._hosts['Htest']['connected']


def test_real_report_capture_and_evaluation_stage_are_exact_owner_references(source):
    from caelab.evaluation_definition import default_draft, document_reference
    wb, docs = source
    ref = saved_reference(docs['material'])
    report = wb.document_open(kind='report')
    asset = wb.report_capture(report['id'], ref)
    draft = deepcopy(report['draft'])
    draft['sections'] = [{'id': 'Asection', 'title': '재료 근거', 'text': '편집 가능한 본문',
                          'include': True, 'table': True, 'curve': False, 'asset': asset}]
    report = save(wb, command(wb, report, 'report.update', {'draft': draft}))
    draft = default_draft()
    draft['stages'] = [{'id': 'Ffirst', 'name': '재료 단계', 'source': document_reference(docs['material'])}]
    evaluation = save(wb, wb.document_open(kind='evaluation', draft=draft))
    before = snapshot(wb)
    graph = build_graph(wb, [report['id'], evaluation['id']])
    assert snapshot(wb) == before
    refs = [n for n in graph['nodes'] if n['node_type'] == 'reference']
    assert len(refs) == 2 and all(n['owner_id'] == docs['material']['id'] for n in refs)
    assert all(n['status'] == 'AVAILABLE' and n['exact_reference'] == ref for n in refs)
