"""Declared team closure/current B checks; no provider/search/solver calls."""
from copy import deepcopy

import pytest

from caelab.assist.experts import ExpertRuntime, RuntimeConfig
from caelab.assist.knowledge import KnowledgeStore
from caelab.assist.literature import Literature
from caelab.assist.research_evidence import GenerationLedger, shared_projection
from caelab.portable_research_team import (collect_team_closure,
    project_archived_team, validate_current_team_view)
from caelab.storage import canonical_hash


@pytest.fixture
def case(tmp_path):
    source = tmp_path / 'public.md'
    source.write_text('공개 합성 기록: 표본 조건을 확인해야 한다. 실제 시험값이 아니다.', encoding='utf-8')
    knowledge = KnowledgeStore(tmp_path / 'knowledge', source_roots=[tmp_path])
    added = knowledge.ingest(source, 'public', {'title': '공개 합성 자료', 'access_scope': 'public'})
    pin = {'document_id': added['document_id'], 'revision': 1}
    read = knowledge.source(pin['document_id'], 1)
    segment = read['segments'][0]
    pin['locator'] = segment['locator']
    role = {'id': 'reviewer', 'collections': ['public'], 'tools': ['knowledge.source']}
    runtime = ExpertRuntime(knowledge, Literature(tmp_path / 'literature'), experts=[role],
        runtime=RuntimeConfig(transmission={'allow_external_model': True, 'allow_question': True, 'collections': ['public']}))
    context = {'selected_sources': [{k: pin[k] for k in ('document_id', 'revision')}], 'transmission_scope': {'allow_question': True,
        'collections': ['public'], 'source_refs': [{k: pin[k] for k in ('document_id', 'revision')}]}}
    assets = {}
    ledger = GenerationLedger({'owner_id': 'Xone', 'phase_id': 'Pone', 'task_id': 'Tone',
        'actor_id': 'reviewer', 'attempt_id': 'Aone'}, runtime=runtime, workspace_id='local',
        context=context, checkpoint=lambda *args: {})
    ledger.add_supplied({'kind': 'knowledge', 'exact_ref': pin, 'payload': segment['text']}, dependencies=[], origin='auto_snippet')
    manifest = ledger.begin_model({'question': '공개 조건 확인'}, mode='initial')
    raw = {'answer': '명시한 합성 표시 응답이며 AI 답변이 아니다.', 'sources': []}
    raw_ref = {'path': 'research-team/Bone/assets/Rraw.json', 'sha256': canonical_hash(raw)}
    assets[raw_ref['path']] = raw
    ids = manifest['dependency_ids']
    response = {'id': 'Rone', 'dependency_ids': ids, 'input_manifest_ids': [manifest['id']],
        'raw_response_ref': raw_ref, 'local_status': 'COMPLETED_LOCAL'}
    verification = {'path': 'research-team/inputs/V' + 'a' * 40 + '.json', 'sha256': 'b' * 64}
    team = {'version': 2, 'revision': 1, **deepcopy(ledger.state),
        'responses': {'Rone': response}, 'projections': {}, 'phases': {}, 'tasks': {},
        'actions': {'Done': {'id': 'Done', 'origin': 'local'}},
        'attempts': {'Aone': {'id': 'Aone', 'job_id': 'Joriginal', 'terminal_state': 'FAILED'}},
        'map_pending': {'Kone': {'id': 'Kone', 'status': 'WAITING_BUDGET'}}, 'map_checkpoints': {},
        'assets': {'Rraw': raw_ref, 'Vproof': verification}, 'result_verifications': {'exact': verification}}
    scope = {'ledger_state': team, 'context': context, 'assignments': {'reviewer': {'source_refs': [pin]}},
             'resolve_payload': lambda ref: deepcopy(assets[ref['path']])}
    def project(value):
        return shared_projection(value, ['reviewer'], runtime=runtime, workspace_id='local', current_scope=scope)
    return team, project, knowledge, pin


def test_uncited_supplied_source_and_verification_assets_are_in_closure(case):
    team, project, _, pin = case
    before = deepcopy(team)
    result = collect_team_closure(team, project=project)
    assert pin in result['references']
    assert team['responses']['Rone']['raw_response_ref'] in result['assets']
    assert team['result_verifications']['exact'] in result['assets']
    assert team == before


def test_revoked_dependency_blocks_cached_shared_view_and_export_without_editing_raw(case):
    team, project, store, pin = case
    assert validate_current_team_view(team, project=project)['status'] == 'AVAILABLE'
    before = deepcopy(team)
    store.revoke(pin['document_id'])
    view = validate_current_team_view(team, project=project)
    assert view['status'] == 'PARTIAL'
    assert view['facets']['responses']['Rone']['projection'] is None
    with pytest.raises(PermissionError):
        collect_team_closure(team, project=project)
    assert team == before


def test_missing_declared_asset_or_path_escape_is_refused(case):
    team, project, _, _ = case
    team['assets'].pop('Vproof')
    with pytest.raises(ValueError, match='누락'):
        collect_team_closure(team, project=project)
    team['assets']['Vproof'] = {'path': '../operator.json', 'sha256': 'b' * 64}
    with pytest.raises(ValueError, match='보존 파일'):
        collect_team_closure(team, project=project)


def test_archive_projection_retains_raw_record_and_disables_source_phase_on_all_edit_stacks(case):
    team, _, _, _ = case
    cfg = {'version': 2, 'phase_id': 'Pone', 'parent_phase_id': None, 'requested_next': {'expert_id': 'reviewer'}}
    draft = {'context': {'research_team': cfg}}
    document = {'kind': 'expert', 'discussion': {'research_team': team},
        'draft': draft, '_undo': [deepcopy(draft)], '_redo': [deepcopy(draft)]}
    original = deepcopy(document)
    copied = project_archived_team(document)
    current = copied['discussion']['research_team']
    assert current['actions']['Done']['origin'] == 'archived_origin'
    assert current['map_pending']['Kone']['status'] == 'ARCHIVED_PENDING'
    assert current['archived_origin']['map_pending']['Kone']['status'] == 'WAITING_BUDGET'
    assert current['responses'] == original['discussion']['research_team']['responses']
    assert current['attempts'] == original['discussion']['research_team']['attempts']
    for draft in [copied['draft'], *copied['_undo'], *copied['_redo']]:
        assert draft['context']['research_team']['phase_id'] is None
        assert draft['context']['research_team']['requested_next'] is None
    assert document == original


def test_local_owner_projection_requires_current_source_but_no_runtime_or_role(case):
    from caelab.assist.research_evidence import local_projection
    team, shared, store, pin = case
    raw = {'answer': '현지 원문 열람은 모델 전송이 아니다.'}
    calls = []
    def current_dependency(row):
        calls.append(row['id'])
        store.check_access(row['exact_ref']['document_id'], row['exact_ref']['revision'], workspace_id='local')
        return True
    def project(record):
        return local_projection(record, state=team, resolve_payload=lambda ref: deepcopy(raw),
            check_dependency=current_dependency)
    assert collect_team_closure(team, project=project)['references'] == [pin]
    assert calls
    store.revoke(pin['document_id'])
    assert validate_current_team_view(team, project=project)['status'] == 'PARTIAL'
    assert team['responses']['Rone']['raw_response_ref']


def test_raw_search_error_asset_is_retained_but_not_a_shared_output(case):
    from caelab.portable_research_team import declared_team_assets
    team, project, _, _ = case
    error = {'path': 'research-team/Bone/assets/Eprivate.json', 'sha256': 'c' * 64}
    team['assets']['Eprivate'] = error
    team['public_search_ledgers'] = {'Done': {'entries': [{'raw_error_ref': error}], 'read_entries': []}}
    team['outputs'] = {'lookup:one': {'status': 'FAILED', 'metadata': {'status': 'FAILED'}, 'payload_ref': error}}
    assert error in declared_team_assets(team)
    assert validate_current_team_view(team, project=project)['status'] == 'AVAILABLE'
    team['assets'].pop('Eprivate')
    with pytest.raises(ValueError, match='누락'):
        declared_team_assets(team)


def test_report_action_turn_and_current_map_use_local_facets_without_changing_raw(case):
    from types import SimpleNamespace
    from caelab.portable_research_team import apply_team_local_view
    team, _, store, _ = case
    ids = team['responses']['Rone']['dependency_ids']
    report = {'dependency_ids': ids, 'body_ref': {'path': 'report'}}
    team['actions']['Done']['report'] = report
    team['phases']['Pone'] = {'current_report_action': 'Done', 'current_map_revision': 'Kone', 'objective': '관측 조건을 구별하는 연구 질문'}
    team['map_checkpoints']['Kone'] = {'dependency_ids': ids, 'kb_asset_ref': {'path': 'map'}}
    raw = {'report': {'text': '원 보고서 본문'},
        'map': {'tree': {'name': '검토할 관측', 'children': [], 'content': []}}}
    def dependency(row):
        store.check_access(row['exact_ref']['document_id'], row['exact_ref']['revision'])
        return True
    owner = SimpleNamespace(research_team_transfer_context=lambda doc: {'state': team,
        'resolve_payload': lambda ref: raw.get(ref['path'], {'answer': '원 응답'}),
        'check_local_dependency': dependency})
    document = {'draft': {'context': {'discussion_mode': 'costorm', 'research_team': {'version': 2, 'phase_id': 'Pone'}}},
        'discussion': {'research_team': team, 'turns': [{'id': 'Fone', 'research_action_id': 'Done',
            'text': '원 보고서 본문', 'response': {'answer': '원 보고서 본문'}}]}}
    original = deepcopy(document)
    allowed = apply_team_local_view(owner, document, deepcopy(document))
    assert allowed['turns'][0]['text'] == '원 보고서 본문'
    assert allowed['discussion']['costorm']['topics'][0]['title'] == '관측 조건을 구별하는 연구 질문'
    assert allowed['discussion']['costorm']['report'] == raw['report']
    unstarted = deepcopy(document)
    unstarted['draft']['context']['research_team']['phase_id'] = 'PnewNotStarted'
    unstarted['discussion']['costorm'] = {'topics':[{'title':'이전 비공개 논점'}], 'report':{'text':'이전 비공개 보고서'}}
    empty = apply_team_local_view(owner, unstarted, deepcopy(unstarted))
    assert empty['discussion']['costorm']['topics'] == []
    assert empty['discussion']['costorm']['report'] is None
    before_first_ask = deepcopy(unstarted)
    before_first_ask['discussion'].pop('research_team')
    empty = apply_team_local_view(owner, before_first_ask, deepcopy(before_first_ask))
    assert empty['discussion']['costorm']['topics'] == []
    assert empty['discussion']['costorm']['report'] is None
    store.revoke(next(iter(team['dependencies'].values()))['exact_ref']['document_id'])
    denied = apply_team_local_view(owner, document, deepcopy(document))
    assert '원 보고서 본문' not in str(denied['turns'])
    assert denied['discussion']['costorm']['topics'] == []
    assert denied['discussion']['costorm']['report'] is None
    legacy = deepcopy(document)
    legacy['draft']['context'].pop('research_team')
    legacy['discussion']['costorm'] = {'topics': [{'title': '일반 자료 토론의 현재 지도'}],
        'report': {'text': '일반 자료 토론의 현재 보고서'}, 'ready': True}
    current_legacy = apply_team_local_view(owner, legacy, deepcopy(legacy))
    assert current_legacy['discussion']['costorm'] == legacy['discussion']['costorm']
    assert '원 보고서 본문' not in str(current_legacy['turns'])
    assert document == original
