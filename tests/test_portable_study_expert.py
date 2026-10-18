"""Actual S/X/B owners, exact literature and controlled dispatcher, no provider.

Scripted completions are not AI answers. Qt/Windows runs are separate; this
suite intentionally uses no solver, native host, account, installation or index.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import shutil
import time
from unittest.mock import patch

import pytest

from caelab.workbench import Workbench
from caelab.portable_project import inspect_copy, create_copy, open_project, verify_project
from caelab.portable_project_io import PortableProjectError
from caelab.portable_research_owner import (HISTORY, MARKER, current_folder, logical_run,
    live_rounds, live_turns, navigation_view)
from caelab.portable_research_knowledge import _archive, _source_rows, frozen_refs
from caelab.storage import canonical_hash, load_json, save_json
from caelab.evaluation import file_hash
from caelab.connection_graph import saved_reference
from examples.portable_study_expert_public import (fixture, publish, rows, update, saved, cmd,
    controlled, ask_draft, finished, source_free, LABEL, ROLES)


@contextmanager
def workspace(path, **kwargs):
    wb = Workbench(path, **kwargs)
    try:
        yield wb
    finally:
        closed = wb.shutdown()
        assert closed['joined'] and not closed['pending']


def make_copy(tmp_path, *, history=False):
    source, target = tmp_path / '원본', tmp_path / '작업 사본'
    with workspace(source) as wb:
        case = fixture(wb, history=history)
        receipt = publish(wb, case['documents'], target)
    shutil.rmtree(source)  # Only this test's generated child, after shutdown/join.
    return case, receipt, target


def local_expert(wb, receipt):
    return wb.document_read(rows(receipt)['expert'])


def policy(wb, doc_id, **change):
    store = wb.assistance().knowledge
    value = load_json(store._manifest)
    value['documents'][doc_id].update(change)
    save_json(store._manifest, value)


def test_old_revision_raw_metadata_exact_hash_and_no_latest_or_unselected_import(tmp_path):
    case, receipt, target = make_copy(tmp_path)
    with workspace(target) as wb, source_free(wb):
        selected = wb.research_reference(case['reference'])
        assert selected['source'] == case['source_payload']
        assert selected['source_metadata']['metadata']['year'] == 2026
        assert selected['source_metadata']['origin_policy']['access_scope'] == 'public'
        assert selected['source_metadata']['current_policy']['access_scope'] == [wb.workspace_id]
        assert wb.workspace_id != 'local'
        directory = wb.assistance().knowledge.root / case['source']['document_id']
        assert not (directory / '2').exists()
        assert file_hash(directory / '1/original.md') == case['reference']['source_sha256']
        with pytest.raises(ValueError, match='ARCHIVED_REVISION_REQUIRED'):
            wb.assistance_call('knowledge.source', {'document_id': case['source']['document_id']})
        assert not (wb.root / 'assistance/operator.json').exists()
        assert not list((wb.root / 'assistance/sessions').glob('*.json'))
        assert not wb.manager.list()


def test_only_report_segment_collected_and_full_revision_ask_is_not_implied(tmp_path):
    with workspace(tmp_path / 'origin') as wb:
        case = fixture(wb, history=False)
        receipt = publish(wb, [case['report']['id']], tmp_path / 'copy')
    with workspace(tmp_path / 'copy') as wb:
        assert wb.research_reference(case['reference'])['source'] == case['source_payload']
        store = wb.assistance().knowledge
        data = load_json(store.root / case['source']['document_id'] / '1/segments.json')
        assert len(data['segments']) == 1
        with pytest.raises(ValueError, match='KNOWLEDGE_PARTIAL_REVISION'):
            store.source(case['source']['document_id'], 1, workspace_id=wb.workspace_id)
        with pytest.raises(ValueError, match='KNOWLEDGE_SEGMENT_NOT_INCLUDED'):
            store.source(case['source']['document_id'], 1, {'segment_id': '0'}, workspace_id=wb.workspace_id)


@pytest.mark.parametrize('fault', ['raw', 'segments', 'descriptor', 'missing_raw', 'locator', 'content_hash', 'source_hash'])
def test_source_tamper_or_reference_mismatch_never_becomes_latest(tmp_path, fault):
    case, receipt, target = make_copy(tmp_path)
    with workspace(target) as wb:
        ref = deepcopy(case['reference'])
        directory = wb.assistance().knowledge.root / case['source']['document_id'] / '1'
        if fault == 'missing_raw': (directory / 'original.md').unlink()
        elif fault in {'raw', 'segments', 'descriptor'}:
            name = {'raw': 'original.md', 'segments': 'segments.json', 'descriptor': 'portable.json'}[fault]
            path = directory / name; data = path.read_bytes(); path.write_bytes(data.replace(b'1', b'9', 1) if b'1' in data else data + b'x')
        elif fault == 'locator': ref['locator']['line_start'] += 1
        elif fault == 'content_hash': ref['content_sha256'] = 'a' * 64
        else: ref['source_sha256'] = 'b' * 64
        with pytest.raises((ValueError, PortableProjectError, FileNotFoundError)):
            wb.research_reference(ref)
        assert not wb.manager.list()


@pytest.mark.parametrize('change', [{'revoked': True}, {'access_scope': ['another-workspace']}, {'access_scope': ['local']}])
def test_scope_denial_no_source_frozen_report_or_expert_context_leak(tmp_path, change):
    case, receipt, target = make_copy(tmp_path, history=True)
    with workspace(target) as wb:
        ids = rows(receipt)
        before = local_expert(wb, receipt)
        policy(wb, case['source']['document_id'], **change)
        with pytest.raises(PermissionError): wb.research_reference(case['reference'])
        with pytest.raises(PermissionError): wb.report_documents.asset(ids['report'], case['binding'])
        content = wb.report_content(ids['report'], [case['binding']])['assets'][0]
        assert content['navigation_reference'] is None and 'content' not in content
        assert content['snapshot_status'] == 'SCOPE_REQUIRED'
        study = wb.document_read(ids['study'])
        assert study['draft']['decisions'][0]['status'] == 'UNKNOWN'
        after = wb.document_read(ids['expert'])
        assert after['draft'] == before['draft']
        assert all(not t.get('text') for t in after['turns'])
        assert all('arguments' not in run for run in after['runs'])
        assert LABEL not in json.dumps(after, ensure_ascii=False)
        with pytest.raises(PermissionError):
            wb.document_result(ids['expert'], case['expert']['runs'][0]['job_id'])
        refs = {'kind': 'expert_turn', 'discussion_id': ids['expert'],
            'saved_revision': after['saved_revision'], 'turn_id': after['turns'][1]['id'],
            'turn_sha256': canonical_hash(case['original_turns'][1])}
        with pytest.raises(PermissionError): wb.research_reference(refs)
        changed = deepcopy(study['draft']); changed['question'] = '권한이 부족해도 남는 현재 판단'
        assert saved(wb, update(wb, study, changed))['draft'] == changed
        plan = inspect_copy(wb, list(ids.values()))
        assert plan['status'] == 'BLOCKED'


def test_matching_literal_local_does_not_recreate_origin_authority(tmp_path):
    case, receipt, target = make_copy(tmp_path)
    with workspace(target, configuration={'workspace_id': 'local'}) as wb:
        with pytest.raises(PermissionError): wb.research_reference(case['reference'])
        assert wb.assistance_call('knowledge.list', {})['documents'] == []
        assert wb.document_read(rows(receipt)['study'])['draft']['question']


@pytest.mark.parametrize('phase', ['review', 'stage'])
def test_revoke_after_inspection_blocks_publication_and_preserves_target_absence(tmp_path, monkeypatch, phase):
    with workspace(tmp_path / 'origin') as wb:
        case = fixture(wb, history=False)
        plan = inspect_copy(wb, case['documents']); assert plan['status'] == 'READY'
        if phase == 'review':
            wb.assistance().knowledge.revoke(case['source']['document_id'], workspace_id=wb.workspace_id)
        else:
            from caelab import portable_project
            original = portable_project._Fork.write
            def change(fork):
                original(fork)
                wb.assistance().knowledge.revoke(case['source']['document_id'], workspace_id=wb.workspace_id)
            monkeypatch.setattr(portable_project._Fork, 'write', change)
        target = tmp_path / 'blocked'
        with pytest.raises((ValueError, PortableProjectError, PermissionError)):
            create_copy(wb, plan, target, approved=True, command_id='Cstale', session_id=wb.session_id)
        assert not (target / 'portable-project.json').exists()
        assert wb.document_read(case['study']['id'])['draft'] == case['study']['draft']


def test_current_id_revision_collision_does_not_replace_either_source(tmp_path):
    case, receipt, target = make_copy(tmp_path)
    with workspace(target) as wb:
        store = wb.assistance().knowledge
        old_bytes = (store.root / case['source']['document_id'] / '1/original.md').read_bytes()
        # Competing native identity removes archived pointer. Do NOT overwrite its original bytes.
        policy(wb, case['source']['document_id'], portable_revisions={})
        with pytest.raises(ValueError, match='KNOWLEDGE_ID_COLLISION'): wb.research_reference(case['reference'])
        assert (store.root / case['source']['document_id'] / '1/original.md').read_bytes() == old_bytes


def test_history_only_exact_ref_survives_undo_and_unavailable_decision_not_rewritten(tmp_path):
    with workspace(tmp_path / 'origin') as wb:
        case = fixture(wb, history=False)
        study = case['study']; draft = deepcopy(study['draft']); draft['evidence'] = []
        draft['decisions'][0]['supporting'] = []; draft['decisions'][0]['conflicting'] = []
        draft['next_observations'][0]['evidence_ids'] = []
        study = saved(wb, update(wb, study, draft))
        made = publish(wb, [study['id']], tmp_path / 'copy')
    with workspace(tmp_path / 'copy') as wb:
        doc = wb.document_read(rows(made)['study'])
        undone = cmd(wb, doc, 'document.undo')['document']
        assert undone['draft']['evidence'][0]['reference'] == case['reference']
        assert wb.research_reference(case['reference'])['source'] == case['source_payload']
        policy(wb, case['source']['document_id'], revoked=True)
        before = deepcopy(undone['draft'])
        checks = wb.study_documents.resolve_references(doc['id'])
        assert checks['references'][0]['status'] == 'UNAVAILABLE'
        assert wb.document_read(doc['id'])['draft'] == before


def test_invalid_study_draft_can_save_cold_and_recopy(tmp_path):
    with workspace(tmp_path / 'origin') as wb:
        study = wb.document_open(kind='study', draft={'question': ['authored invalid'], 'author_note': '보존'})
        study = saved(wb, study)
        first = publish(wb, [study['id']], tmp_path / 'copy')
    with workspace(tmp_path / 'copy') as wb:
        current = wb.document_read(rows(first)['study'])
        assert current['diagnostics'] and current['draft'] == study['draft']
        current = saved(wb, current)
        second = publish(wb, [current['id']], tmp_path / 'recopy')
    with workspace(tmp_path / 'recopy') as wb:
        assert wb.document_read(rows(second)['study'])['draft'] == study['draft']


def test_report_lost_current_source_keeps_frozen_A_but_no_origin_navigation(tmp_path, monkeypatch):
    case, receipt, target = make_copy(tmp_path)
    with workspace(target) as wb:
        def missing(*args, **kwargs): raise FileNotFoundError('current selected source unavailable')
        monkeypatch.setattr(wb.report_documents, 'resolve_reference', missing)
        row = wb.report_content(rows(receipt)['report'], [case['binding']])['assets'][0]
        assert row['source_status'] == 'UNAVAILABLE'
        assert row['navigation_status'] == 'SOURCE_UNAVAILABLE'
        assert row['navigation_reference'] is None
        assert row['content']['source'] == case['source_payload']
        assert row['reference'] == case['reference']


def test_origin_ready_and_history_never_inspects_live_jobs_during_read_undo_save(tmp_path, monkeypatch):
    case, receipt, target = make_copy(tmp_path, history=True)
    with workspace(target) as wb, monkeypatch.context() as mpatch:
        def forbidden(*a, **kw): raise AssertionError('origin job harvest/receipt lookup')
        for name in ('list', 'status', 'submit', 'result'):
            mpatch.setattr(wb.manager, name, forbidden)
        doc = local_expert(wb, receipt)
        assert doc['discussion']['rounds'] == case['original_rounds']
        assert not live_rounds(wb.discussion_documents._documents[doc['id']])
        with pytest.raises(PermissionError, match='EXPERT_ORIGIN_COMMAND'):
            cmd(wb, doc, 'expert.ask', command_id='CoriginalReady')
        draft = deepcopy(doc['draft']); draft['composer']['text'] += ' 새 편집'
        edited = update(wb, doc, draft)
        undo = cmd(wb, edited, 'document.undo')['document']
        redo = cmd(wb, undo, 'document.redo')['document']
        retained = saved(wb, redo)
        assert retained['draft']['composer']['text'] == draft['composer']['text']
        assert retained['discussion']['rounds'] == case['original_rounds']
        assert [logical_run(row) for row in retained['runs']] == case['original_runs']


@pytest.mark.parametrize('state', ['running', 'dispatch_pending'])
def test_copied_live_original_attempt_is_a_readable_nonexecuting_snapshot(tmp_path, monkeypatch, state):
    with workspace(tmp_path / 'origin') as wb:
        case = fixture(wb, history=False)
        doc = wb.document_open(kind='expert')
        doc = saved(wb, update(wb, doc, ask_draft(doc, case['source'], authorized=True)))
        with controlled(wb) as boundary:
            if state == 'running':
                boundary.release.clear()
                requested = cmd(wb, doc, 'expert.ask', command_id='CoriginActive')
                doc = requested['document']
                deadline = time.monotonic() + 5
                while not boundary.calls and time.monotonic() < deadline: time.sleep(.005)
                assert boundary.calls
            else:
                with patch.object(wb.discussion_documents, 'submit', side_effect=ConnectionError('controlled before submit')):
                    with pytest.raises(ConnectionError): cmd(wb, doc, 'expert.ask', command_id='CoriginPending')
            raw = deepcopy(wb.discussion_documents._documents[doc['id']])
            made = publish(wb, [doc['id']], tmp_path / 'copy')
            boundary.release.set()
    with workspace(tmp_path / 'copy') as wb, monkeypatch.context() as mpatch:
        def forbidden(*a, **kw): raise AssertionError('copied pending job used as current authority')
        for name in ('list', 'status', 'submit', 'result'): mpatch.setattr(wb.manager, name, forbidden)
        doc = local_expert(wb, made)
        assert doc['discussion']['rounds'] == raw['discussion']['rounds']
        assert doc['draft']['composer']['text'] == raw['draft']['composer']['text']
        doc = saved(wb, doc)
        assert doc['discussion']['rounds'] == raw['discussion']['rounds']
        if state == 'running':
            assert doc['runs'][0]['retained_state'] == 'RUNNING'
            with pytest.raises(FileNotFoundError, match='EXPERT_ARCHIVED_PARTIAL'):
                wb.document_result(doc['id'], doc['runs'][0]['job_id'])


def test_new_local_same_command_response_loss_recovers_only_its_actual_job(tmp_path):
    case, receipt, target = make_copy(tmp_path, history=True)
    with workspace(target) as wb, controlled(wb) as boundary:
        doc = local_expert(wb, receipt)
        doc = update(wb, doc, ask_draft(doc, case['source'], question='새 현지 유실응답 검사', authorized=True))
        submit = wb.discussion_documents.submit
        calls = []
        def lost(*args, **kwargs):
            job = submit(*args, **kwargs); calls.append(job['id'])
            raise ConnectionError('controlled loss after accepted dispatch')
        with patch.object(wb.discussion_documents, 'submit', lost):
            with pytest.raises(ConnectionError): cmd(wb, doc, 'expert.ask', command_id='ClocalLost')
        assert len(calls) == 1
        current, response = finished(wb, doc, {'job': {'id': calls[0]}})
        confirmed = cmd(wb, doc, 'expert.ask', command_id='ClocalLost')
        assert confirmed['recovered_after_response_loss']
        assert len(boundary.calls) == 1 and len(wb.manager.list()) == 1
        assert current['turns'][-1]['text'].startswith(LABEL)
        assert saved(wb, current)['draft']['composer']['text'] == doc['draft']['composer']['text']


def test_current_runtime_does_not_authorize_origin_scope_and_late_reply_preserves_question(tmp_path):
    case, receipt, target = make_copy(tmp_path, history=True)
    with workspace(target) as wb, controlled(wb) as boundary:
        doc = local_expert(wb, receipt); text = doc['draft']['composer']['text']
        denied = cmd(wb, doc, 'expert.ask')
        doc, result = finished(wb, doc, denied)
        assert not boundary.calls and doc['draft']['composer']['text'] == text
        assert wb.manager.status(denied['job']['id'])['state'] == 'FAILED'
        doc = update(wb, doc, ask_draft(doc, case['source'], question='보낼 질문', authorized=True))
        boundary.release.clear()
        started = cmd(wb, doc, 'expert.ask')
        later = deepcopy(started['document']['draft']); later['composer']['text'] = '응답 중 새로 작성한 질문'
        doc = update(wb, started['document'], later)
        boundary.release.set()
        doc, result = finished(wb, doc, started)
        assert doc['draft']['composer']['text'] == later['composer']['text']
        assert result['answer'].endswith('보낼 질문')
        assert doc['discussion']['rounds'][:len(case['original_rounds'])] == case['original_rounds']


@pytest.mark.parametrize('case_name', ['source_refs', 'collections', 'question', 'payload_bound', 'role_collection', 'revoked'])
def test_current_exact_authorization_failures_never_replay_history(tmp_path, case_name):
    case, receipt, target = make_copy(tmp_path, history=True)
    with workspace(target) as wb, controlled(wb) as boundary:
        doc = local_expert(wb, receipt)
        draft = ask_draft(doc, case['source'], question='현재 권한 검사', authorized=True)
        scope = draft['context']['transmission_scope']
        if case_name == 'source_refs': scope['source_refs'] = []
        elif case_name == 'collections': scope['collections'] = []
        elif case_name == 'question': scope['allow_question'] = False
        elif case_name == 'payload_bound': boundary.runtime.runtime.max_payload_bytes = 5
        elif case_name == 'role_collection':
            # No current role source grant, despite unchanged original source collection metadata.
            policy(wb, case['source']['document_id'], collection='other-collection')
        else: policy(wb, case['source']['document_id'], revoked=True)
        doc = update(wb, doc, draft)
        if case_name == 'revoked':
            with pytest.raises(PermissionError): cmd(wb, doc, 'expert.ask')
        else:
            asked = cmd(wb, doc, 'expert.ask'); doc, result = finished(wb, doc, asked)
            if case_name == 'role_collection':
                # Existing Runtime intersection sends the authored question WITHOUT unauthorized sources.
                assert boundary.calls and boundary.calls[0]['context']['selected_sources'] == []
                assert not boundary.calls[0]['context']['discussion']['turns']
            else: assert not boundary.calls
        assert wb.document_read(doc['id'])['draft']['composer']['text'] == draft['composer']['text']


def test_stale_save_publish_failure_and_existing_destination_leave_current_work(tmp_path, monkeypatch):
    case, receipt, target = make_copy(tmp_path)
    with workspace(target) as wb:
        study = wb.document_read(rows(receipt)['study'])
        draft = deepcopy(study['draft']); draft['question'] = '저장 실패에도 남길 입력'
        changed = update(wb, study, draft)
        with pytest.raises(ValueError, match='generation changed'):
            cmd(wb, study, 'study.update', {'draft': study['draft']})
        old_saved = changed['saved_revision']
        import caelab.material_document as module
        original = module.save_json
        def fail_pointer(path, value):
            if Path(path) == wb.study_documents._folder(study['id']) / 'document.json': raise OSError('controlled durable pointer failure')
            return original(path, value)
        with patch.object(module, 'save_json', fail_pointer):
            with pytest.raises(OSError): saved(wb, changed)
        current = wb.document_read(study['id'])
        assert current['draft'] == draft and current['saved_revision'] == old_saved
        current = saved(wb, current)
        plan = inspect_copy(wb, [current['id']]); assert plan['status'] == 'READY'
        existing = tmp_path / 'exists'; existing.mkdir(); (existing/'keep').write_text('DO NOT REPLACE')
        with pytest.raises((ValueError, PortableProjectError, FileExistsError)):
            create_copy(wb, plan, existing, approved=True, command_id='Cexists', session_id=wb.session_id)
        assert (existing/'keep').read_text() == 'DO NOT REPLACE'


def test_current_and_origin_expert_turn_references_navigate_and_recopy_without_rewriting(tmp_path):
    with workspace(tmp_path/'origin') as wb:
        case = fixture(wb, history=True)
        # A saved public material is explicitly cited in an authored original turn.
        material = saved(wb, wb.document_open(kind='material'))
        ref = saved_reference(material)
        expert = wb.document_open(kind='expert')
        draft = ask_draft(expert, case['source'], authorized=True); draft['composer']['evidence']=[ref]
        expert = update(wb, expert, draft)
        with controlled(wb): expert, _ = finished(wb, expert, cmd(wb, expert, 'expert.ask'))
        expert = saved(wb, expert)
        original_turn = deepcopy(expert['turns'][0])
        made = publish(wb, [expert['id'], material['id']], tmp_path/'copy')
    with workspace(tmp_path/'copy') as wb:
        expert = local_expert(wb,made)
        nav = expert['portable_reference_navigation'][0]
        assert nav['reference'] == ref and nav['navigation_reference']['document_id'] != ref['document_id']
        assert wb.research_reference(nav['navigation_reference'])['status']=='AVAILABLE'
        assert expert['turns'][0] == original_turn
        expert = saved(wb,expert)
        second = publish(wb,[row['document_id'] for row in made['documents']],tmp_path/'recopy')
    with workspace(tmp_path/'recopy') as wb:
        expert=local_expert(wb,second)
        assert expert['turns'][0] == original_turn
        assert wb.research_reference(expert['portable_reference_navigation'][0]['navigation_reference'])['status']=='AVAILABLE'


def test_costorm_report_and_view_only_knowledge_pins_are_in_closure():
    source = {'document_id':'Kpublic','revision':1,'locator':{'page':3,'segment_id':'2'}}
    response = {'costorm':{'view':{'sources':{'1':source},'turns':[]},
        'report':{'text':LABEL+' [1]', 'references':[{'number':'1','source':source}]}}}
    assert list(_source_rows(response)) == [source,source]
    assert list(frozen_refs({'reference':{'kind':'knowledge',**source},
        'content':{'kind':'knowledge','source':{'document_id':'Kpublic','revision':1,'segments':[],'sha256':'a'*64}}}))==[source]


@pytest.mark.parametrize('operation', ['expert.pause', 'document.save', 'expert.update'])
def test_local_command_receipt_rereads_current_scope_without_replay_or_edit_rollback(tmp_path, operation):
    case, receipt, target = make_copy(tmp_path, history=True)
    with workspace(target) as wb:
        doc = local_expert(wb, receipt)
        args = {'draft': deepcopy(doc['draft'])} if operation == 'expert.update' else {}
        response = cmd(wb, doc, operation, args, command_id='ClocalReceipt')
        assert LABEL in json.dumps(response, ensure_ascii=False)
        path = wb.discussion_documents._folder(doc['id']) / 'commands/ClocalReceipt.json'
        raw = path.read_bytes()
        edited = deepcopy(response['document']['draft']); edited['composer']['text'] = '영수증 이후의 현재 질문'
        changed = update(wb, response['document'], edited)
        policy(wb, case['source']['document_id'], revoked=True)
        with source_free(wb):
            checked = cmd(wb, doc, operation, args, command_id='ClocalReceipt')
        assert LABEL not in json.dumps(checked, ensure_ascii=False)
        assert checked['document']['archive_source_status']['status'] == 'SOURCE_UNAVAILABLE'
        assert path.read_bytes() == raw
        assert wb.document_read(doc['id'])['draft'] == changed['draft']
        assert not wb.manager.list()


def test_report_raw_archived_only_pin_survives_delete_sections_and_recopy(tmp_path):
    case, receipt, target = make_copy(tmp_path)
    with workspace(target) as wb:
        report = wb.document_read(rows(receipt)['report'])
        # Undo the original insertion, then author a new branch: the old A
        # leaves both current sections and Redo, but remains in the raw archive.
        report = cmd(wb, report, 'document.undo')['document']
        assert report['draft']['sections'] == []
        draft = deepcopy(report['draft']); draft['title'] = '원 archive만 남긴 새 본문'
        report = saved(wb, update(wb, report, draft))
        raw = wb.report_documents._documents[report['id']]
        assert not any(d.get('sections') for d in raw['_undo'])
        assert raw['portable_knowledge_refs']
        published = publish(wb, [report['id']], tmp_path / 'report-recopy')
        assert len(published['documents']) == 1
        policy(wb, case['source']['document_id'], revoked=True)
        plan = inspect_copy(wb, [report['id']])
        assert plan['status'] == 'BLOCKED'
    with workspace(tmp_path / 'report-recopy') as wb:
        assert wb.research_reference(case['reference'])['source'] == case['source_payload']
        report = wb.document_read(rows(published)['report'])
        assert report['draft']['sections'] == []
        from caelab.portable_project_report import owner_folder
        from caelab.portable_research_knowledge import report_archive_refs
        refs = report_archive_refs(owner_folder(wb.report_documents._folder(report['id']), report), report)
        assert {k:v for k,v in case['reference'].items() if k != 'kind'} in refs


def test_external_scope_reload_invalidates_old_index_and_missing_policy_fails_closed(tmp_path):
    case, receipt, target = make_copy(tmp_path)
    with workspace(target) as wb:
        store = wb.assistance().knowledge
        sentinel = object(); store._store = sentinel
        policy(wb, case['source']['document_id'], revoked=True)
        assert store.list(workspace_id=wb.workspace_id)['documents'] == []
        assert store._store is None
        store._manifest.unlink()
        with pytest.raises(PermissionError): wb.research_reference(case['reference'])


def test_revoked_origin_history_is_not_global_denial_of_a_new_allowed_question(tmp_path):
    case, receipt, target = make_copy(tmp_path, history=True)
    with workspace(target) as wb, controlled(wb) as boundary:
        policy(wb, case['source']['document_id'], revoked=True)
        uploaded = wb.upload('새 현지 공개 문헌.md', '# New local question\nNew source only.\n'.encode())
        source = wb.assistance().knowledge.ingest(wb.input_path(uploaded['id']), 'research', workspace_id=wb.workspace_id)
        doc = local_expert(wb, receipt)
        doc = update(wb, doc, ask_draft(doc, source, question='현재 허용된 문헌만 검토', authorized=True))
        doc, result = finished(wb, doc, cmd(wb, doc, 'expert.ask'))
        assert result['answer'].startswith(LABEL)
        assert len(boundary.calls) == 1
        assert boundary.calls[0]['context']['selected_sources'] == [{'document_id': source['document_id'], 'revision': 1}]
        history = boundary.calls[0]['context']['discussion']['turns']
        assert len(history) == 1 and history[0]['text'] == '현재 허용된 문헌만 검토'
        assert not {turn['id'] for turn in case['original_turns']} & {turn['id'] for turn in history}
        assert any(t.get('text') and t['text'].startswith(LABEL) for t in doc['turns'])
        assert doc['draft']['composer']['text'] == '현재 허용된 문헌만 검토'
        assert all(t['status'] == 'SOURCE_UNAVAILABLE' for t in doc['turns'][:len(case['original_turns'])])


def test_allowed_origin_local_import_creates_only_destination_bound_current_scope(tmp_path):
    with workspace(tmp_path/'origin') as wb:
        upload=wb.upload('현지 원문.md', '# Local source\nOriginal local document.\n'.encode())
        source=wb.assistance().knowledge.ingest(wb.input_path(upload['id']), 'research', workspace_id=wb.workspace_id)
        payload=wb.assistance().knowledge.source(source['document_id'],1,workspace_id=wb.workspace_id)
        reference={'kind':'knowledge','document_id':source['document_id'],'revision':1,'locator':{},
            'source_sha256':payload['sha256'],'content_sha256':canonical_hash(payload)}
        study=wb.document_open(kind='study'); draft=deepcopy(study['draft'])
        draft['evidence']=[{'id':'Elocal','label':'현지 원문','kind':'knowledge','reference':reference,'note':''}]
        study=saved(wb,update(wb,study,draft))
        origin_scope=wb.workspace_id
        receipt=publish(wb,[study['id']],tmp_path/'copy')
    shutil.rmtree(tmp_path/'origin')
    with workspace(tmp_path/'copy') as wb, source_free(wb):
        opened=wb.research_reference(reference)
        assert opened['source']==payload
        assert opened['source_metadata']['origin_policy']['access_scope']==[origin_scope]
        assert opened['source_metadata']['current_policy']['access_scope']==[wb.workspace_id]
        assert wb.workspace_id!=origin_scope
        assert saved(wb,wb.document_read(rows(receipt)['study']))['draft']==draft


def test_explicit_current_cancel_keeps_question_and_original_attempts_without_retry(tmp_path):
    case, receipt, target=make_copy(tmp_path,history=True)
    with workspace(target) as wb, controlled(wb) as boundary:
        from caelab.execution_control import check_cancelled
        original=boundary.complete
        def cancellable(*a,**kw):
            result=original(*a,**kw)
            check_cancelled()  # Model cancellation-aware provider boundary, no provider invoked.
            return result
        doc=local_expert(wb,receipt)
        draft=ask_draft(doc,case['source'],question='취소하여도 남겨둘 질문',authorized=True)
        doc=update(wb,doc,draft)
        boundary.release.clear()
        with patch.object(boundary.runtime,'_ask',cancellable):
            started=cmd(wb,doc,'expert.ask')
            limit=time.monotonic()+5
            while not boundary.calls and time.monotonic()<limit:time.sleep(.005)
            assert boundary.calls
            wb.manager.cancel(started['job']['id'])
            boundary.release.set()
            doc,result=finished(wb,doc,started)
        assert wb.manager.status(started['job']['id'])['state']=='CANCELLED'
        assert doc['draft']['composer']['text']==draft['composer']['text']
        assert doc['discussion']['rounds'][:len(case['original_rounds'])]==case['original_rounds']
        assert len(wb.manager.list())==1
        assert saved(wb,doc)['draft']==draft


@pytest.mark.parametrize('revision',[True,1.0,'1',None])
def test_archived_source_api_rejects_ambiguous_or_latest_revision(tmp_path,revision):
    case,receipt,target=make_copy(tmp_path)
    with workspace(target) as wb:
        with pytest.raises(ValueError,match='ARCHIVED_REVISION_REQUIRED'):
            wb.assistance_call('knowledge.source',{'document_id':case['source']['document_id'],'revision':revision})

@pytest.mark.parametrize('legacy_expert_reference',[False,True])
def test_selected_actual_csv_result_study_expert_report_copy_and_cold_recopy(tmp_path,legacy_expert_reference):
    """Actual tiny CSV import only; no physics/provider. Existing retained reader."""
    from examples.portable_connection_public import create_public_store
    wb, public=create_public_store(tmp_path/'origin')
    try:
        case=fixture(wb,history=False)
        data=public['data'];job=public['success_job']['id']
        ref={'kind':'result',**wb.document_result_reference(data['id'],job)}
        ref['selection']=['stress']
        original=wb.research_reference(ref)
        expert=case['expert'];draft=deepcopy(expert['draft'])
        expert_ref=deepcopy(ref)
        if legacy_expert_reference:expert_ref.pop('kind')
        draft['composer']['evidence']=[expert_ref]
        expert=saved(wb,update(wb,expert,draft))
        study=case['study'];draft=deepcopy(study['draft'])
        draft['evidence'].append({'id':'Eactual','label':'공개 CSV 응력','kind':'result','reference':ref,'note':'실제 CSV 가져오기; 물리 검증 아님'})
        study=saved(wb,update(wb,study,draft))
        report=case['report'];binding=wb.report_capture(report['id'],ref)
        asset=wb.report_documents._folder(report['id'])/'assets'/(binding['id']+'.json')
        raw=asset.read_bytes();draft=deepcopy(report['draft'])
        draft['sections'].append({'id':'Eactual','title':'공개 응력 값','text':'MPa, 원 시각 유지','include':True,'table':True,'curve':False,'asset':binding})
        report=saved(wb,update(wb,report,draft))
        receipt=publish(wb,[data['id'],study['id'],expert['id'],report['id']],tmp_path/'copy')
    finally:wb.shutdown()
    (tmp_path/'origin').rename(tmp_path/'origin-preserved')
    with workspace(tmp_path/'copy') as cold,source_free(cold):
        mapping={r['source_document_id']:r['document_id'] for r in receipt['documents']}
        expert=cold.document_read(mapping[expert['id']]);study=cold.document_read(mapping[study['id']]);report=cold.document_read(mapping[report['id']])
        current=expert['draft']['composer']['evidence'][0]
        assert current['document_id']==mapping[data['id']] and current['job_id']==job and current['selection']==['stress']
        assert ('kind' not in current)==legacy_expert_reference
        actual=cold.research_reference({'kind':'result',**current})
        assert actual['result']==original['result']
        assert actual['result']['responses']['stress']['unit']=='MPa'
        assert actual['result']['responses']['stress']['value']==[0.,1.2,2.4]
        assert study['draft']['evidence'][-1]['reference']=={'kind':'result',**current}
        frozen=cold.report_content(report['id'],[report['draft']['sections'][-1]['asset']])['assets'][0]
        assert frozen['source_status']=='AVAILABLE'
        folder=cold.report_documents._folder(report['id'])/'revisions'/report['saved_revision']
        assert (folder/'assets'/(binding['id']+'.json')).read_bytes()==raw
        made=publish(cold,list(mapping.values()),tmp_path/'recopy')
        assert not cold.manager.list()
    (tmp_path/'copy').rename(tmp_path/'copy-preserved')
    with workspace(tmp_path/'recopy') as last,source_free(last):
        expert=last.document_read(rows(made)['expert']);ref=expert['draft']['composer']['evidence'][0]
        assert ('kind' not in ref)==legacy_expert_reference
        assert last.research_reference({'kind':'result',**ref})['result']==original['result']
        assert not last.manager.list()
