"""Public desktop/portable research-team records, with NO AI/provider/solver.

The role replies/pending states and one tiny retained observation are explicitly
CONTROLLED fixtures. Existing document owners, exact result metadata, retention,
portable inventory/publication, source reads, Undo/Redo and two cold Python
processes run unchanged. This is not acceptance of real team investigation.
Run from the repository: python -m examples.research_team_desktop_public --output <NEW folder>
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from contextlib import contextmanager
import json
import subprocess
import sys
from unittest.mock import patch

from caelab.workbench import Workbench
from caelab.discussion_research_team import empty_state, retain_result_verification
from caelab.research_team_results import capture_result_verification, make_result_selection
from caelab.storage import canonical_hash, save_json, load_json
from caelab.evaluation import file_hash
from caelab.portable_project import open_project
from examples.portable_study_expert_public import (fixture, publish, rows, source_free,
    owned_remove, cmd, update, saved, finished, ROLES)

LABEL = '공개 합성 표시 자료 — 실제 전문가 응답·시험·물리 계산 아님'
CONFIG = {'workers': 1, 'experts': [{**row, 'label': ('구조 검토' if row['id'] == 'testing' else '시험 검토'),
    'tools': [*row['tools'], 'results.read']} for row in ROLES]}


@contextmanager
def controlled_korean_generation():
    """Generation-only display fixture; actual A/B owner/runtime paths remain.

    A's shared controlled host still performs its scoped tool read. Only its
    synthetic answer wording is changed before actual validation/checkpointing.
    """
    from examples.research_team_public import controlled_generation
    import caelab.assist.openscience_host as host_module
    with controlled_generation() as calls:
        previous = host_module.run_openscience
        def host(prompt, tools, budget, model, **options):
            returned = previous(prompt, tools, budget, model, **options)
            if 'Conversation and request JSON: ' not in prompt:
                return returned
            value = json.loads(returned)
            supplied = json.loads(prompt.split('Conversation and request JSON: ', 1)[1])
            task = supplied['context']['research_task']
            text = {
                'INITIAL_RESEARCH': '선택 원문의 관측 조건을 확인했습니다. 원인을 구별하려면 교정 조건과 독립 관측이 더 필요합니다.',
                'QUESTION': '교정 조건을 바꾼 반복 관측으로 같은 변화가 나타나는지 구별할 수 있나요?',
                'ANSWER': '반복 관측이 없으므로 가설을 확정할 수 없습니다. 원 판단을 미확인으로 두고 교정 조건을 확인하겠습니다.',
            }.get(task['kind'], '선택한 관측 조건을 검토합니다.')
            value['answer'] = LABEL + '\n\n' + text + ('[1]' if value.get('sources') else '')
            for claim in value['research_reply']['claims']:
                claim.update(text='관측 변화의 원인을 구별하려면 교정 조건과 독립 관측을 확인해야 한다.',
                    conditions=['공개 합성 관측'], missing_evidence=['반복 관측'])
            for question in value['research_reply']['questions']:
                question.update(expert_id='testing' if task['actor_id'] != 'testing' else 'skeptic',
                    question='교정 조건을 바꾼 반복 관측으로 가설을 구별할 수 있나요?',
                    discriminating_observation='같은 물리량의 반복 교정 관측')
            return json.dumps(value, ensure_ascii=False)
        with patch.object(host_module, 'run_openscience', host):
            yield calls


def seed(wb):
    """Labelled producer boundary only. No actual model/physics is replaced silently."""
    import caelab.workbench as module
    records = fixture(wb, history=False)
    original = module.evaluate
    module.evaluate = lambda *args, **kwargs: {'execution_status': 'SUCCEEDED', 'responses': {
        'u_z': {'kind': 'series', 'label': '판 끝 Z변위 (합성)', 'value': [1., 2., 3.],
            'unit': 'mm', 'component': 'z', 'measure': 'displacement', 'frame': 'global',
            'source_rows': [10, 12, 14], 'axes': [{'name': 'time', 'unit': 's', 'values': [0., 1., 1.]}]}}}
    try:
        material = wb.document_open(kind='material', title='공개 합성 관측 (물리 계산 아님)')
        response = cmd(wb, material, 'material.evaluate', command_id='CcontrolledObservation')
        material, _ = finished(wb, material, response)
        material = saved(wb, material)
    finally:
        module.evaluate = original
    reference = wb.document_result_reference(material['id'], response['job']['id'])
    verification = capture_result_verification(wb, reference)
    selection = make_result_selection(verification, source_id='Spublic', selection_request={
        'metadata_only': False, 'channels': [{'response': 'u_z', 'row_intervals': [[14, 15]]}]})
    pin = {k: records['reference'][k] for k in ('document_id', 'revision', 'locator')}
    assignments = [{'expert_id': row['id'], 'mode': 'investigator',
        'question': '선택한 관측과 문헌의 조건을 구별하세요.', 'checks': ['단위와 원 표본'],
        'tools': ['knowledge.source', 'results.read'], 'source_refs': [{k: pin[k] for k in ('document_id', 'revision')}],
        'result_refs': [deepcopy(selection)]} for row in CONFIG['experts']]
    expert = records['expert']
    draft = deepcopy(expert['draft'])
    draft['context']['discussion_mode'] = 'costorm'
    draft['context']['research_team'] = {'version': 2, 'phase_id': 'Ppublic', 'parent_phase_id': None,
        'objective': '판 끝 관측의 변화가 어떤 가설을 구별하는가?', 'deliverable': '가설과 다음 관측',
        'assignments': assignments, 'shared_evidence': [], 'carry_forward_turn_ids': [],
        'requested_next': None, 'turn_limit': 4, 'stop_when': []}
    draft['participants'] = [row['expert_id'] for row in assignments]
    draft['composer']['text'] = draft['context']['research_team']['objective']
    expert = update(wb, expert, draft)
    owner = wb.discussion_documents
    internal = owner._documents[expert['id']]
    team = empty_state()
    team['revision'] = 1
    team['phases']['Ppublic'] = {'id': 'Ppublic', 'objective': draft['composer']['text'],
        'assignments': deepcopy(assignments), 'task_ids': ['Tfirst', 'Tsecond', 'Tquestion', 'Tanswer'],
        'initial_task_ids': ['Tfirst', 'Tsecond'], 'shared_turn_ids': [], 'current_map_revision': None}
    for key, actor, kind, status in [('Tfirst', 'testing', 'INITIAL_RESEARCH', 'COMPLETED'),
            ('Tsecond', 'skeptic', 'INITIAL_RESEARCH', 'COMPLETED'),
            ('Tquestion', 'skeptic', 'QUESTION', 'WAITING_BUDGET'),
            ('Tanswer', 'testing', 'ANSWER', 'PENDING')]:
        team['tasks'][key] = {'id': key, 'phase_id': 'Ppublic', 'actor_id': actor, 'kind': kind,
            'status': status, 'target_turn_id': None, 'target_claim_id': None}
    team['dependencies'] = {
        'Dpaper': {'id': 'Dpaper', 'kind': 'knowledge', 'exact_ref': pin, 'selector': None,
            'content_digest': canonical_hash(records['source_payload']['segments'][0]['text']),
            'parent_ids': [], 'introduced_by': 'auto_snippet'},
        'Dresult': {'id': 'Dresult', 'kind': 'result', 'exact_ref': reference,
            'selector': selection['selector'], 'content_digest': canonical_hash(LABEL),
            'parent_ids': [], 'introduced_by': 'tool_return'}}
    dependencies = list(team['dependencies'])
    team['manifests']['Mpublic'] = {'id': 'Mpublic', 'coverage': 'COMPLETE_SUPPLIED_INPUT',
        'dependency_ids': dependencies, 'status': 'COMPLETED', 'test_boundary': LABEL}
    body = {'status': 'ANSWERED', 'answer': LABEL + '\n\n선택된 마지막 원 표본은 14번이며, 단위는 mm입니다. '
        '이 합성 관측만으로 원인을 확정할 수 없습니다. 독립 관측과 조건 확인이 필요합니다.',
        'sources': [], 'proposed_actions': [], 'research_reply': {'kind': 'hypothesis',
            'claims': [{'text': '변위 변화가 하중 조건 또는 측정 조건과 관련될 수 있다.',
                'basis': 'hypothesized', 'conditions': ['공개 합성 관측'], 'source_refs': [],
                'missing_evidence': ['독립 측정']}], 'questions': [], 'revisions': [], 'unknowns': []}}
    folder = owner._folder(expert['id'])
    raw = folder / 'research-team' / 'Bpublic' / 'assets' / 'Rpublic.json'
    save_json(raw, body)
    ref = {'path': raw.relative_to(folder).as_posix(), 'sha256': file_hash(raw)}
    team['assets']['Rpublic'] = ref
    team['responses']['Rpublic'] = {'id': 'Rpublic', 'actor_id': 'testing', 'task_id': 'Tfirst',
        'phase_id': 'Ppublic', 'raw_response_ref': ref, 'dependency_ids': dependencies,
        'input_manifest_ids': ['Mpublic'], 'local_status': 'COMPLETED_LOCAL',
        'claim_refs': [{'id': 'C' + canonical_hash({'response': 'Rpublic', 'index': 0})[:32],
            'response_id': 'Rpublic', 'index': 0}]}
    team['actions']['Dpublic'] = {'id': 'Dpublic', 'phase_id': 'Ppublic', 'origin': 'local',
        'task_ids': ['Tfirst', 'Tsecond'], 'test_boundary': LABEL}
    team['attempts']['Apublic'] = {'id': 'Apublic', 'action_id': 'Dpublic', 'job_id': None,
        'terminal_state': 'FAILED', 'test_boundary': LABEL}
    team['map_pending']['Kpublic'] = {'id': 'Kpublic', 'phase_id': 'Ppublic', 'status': 'FAILED',
        'dependency_ids': dependencies, 'journal_ref': None, 'conversation_turn_ref': ref}
    internal['discussion']['research_team'] = team
    retain_result_verification(owner, internal, verification)
    internal['discussion']['turns'].append({'id': 'Upublic', 'author': 'testing', 'text': body['answer'],
        'classification': 'answer', 'research_response_id': 'Rpublic', 'research_phase_id': 'Ppublic',
        'response': deepcopy(body), 'evidence': []})
    owner._persist_draft(internal)
    expert = saved(wb, owner.read(expert['id']))
    records.update(expert=expert, material=material, exact_result=reference, selected_result=selection,
        original_team=deepcopy(team), original_response=deepcopy(body), label=LABEL)
    records['documents'].append(material['id'])
    return records


def cold(output, phase):
    evidence = load_json(output / 'evidence.json')
    receipt = load_json(output / ('first.json' if phase == 1 else 'second.json'))
    folder = output / ('사본 1' if phase == 1 else '재복사 2')
    assert not (output / '원 store').exists()
    if phase == 2:
        assert not (output / '사본 1').exists()
    wb = open_project(folder)
    try:
        identifiers = rows(receipt)
        with source_free(wb):
            assert wb.assistance().experts.runtime.generator is None
            expert = wb.document_read(identifiers['expert'])
            assert expert['research_team_local_view']['facets']['responses']['Rpublic']['status'] == 'AVAILABLE'
            team = expert['discussion']['research_team']
            assert all(team['responses'][key] == value for key, value in evidence['original_team']['responses'].items())
            assert all(team['attempts'][key] == value for key, value in evidence['original_team']['attempts'].items())
            assert all(row['origin'] == 'archived_origin' for row in team['actions'].values())
            assert team['map_pending']['Kpublic']['status'] == 'ARCHIVED_PENDING'
            assert expert['draft']['context']['research_team']['phase_id'] is None
            assert 'transmission_scope' not in expert['draft']['context']
            assert not wb.manager.list()
            source = wb.research_reference(evidence['reference'])
            assert source['source'] == evidence['source_payload']
            draft = deepcopy(expert['draft'])
            draft['composer']['text'] = '새 사본에서 계속 작성한 미완성 질문 1e / 열람 ' + str(phase)
            edited = update(wb, expert, draft)
            undone = cmd(wb, edited, 'document.undo')['document']
            assert undone['draft'] == expert['draft']
            redone = cmd(wb, undone, 'document.redo')['document']
            expert = saved(wb, redone)
            # Exact current result reference is mapped; original team stays byte-identical.
            current = expert['draft']['context']['research_team']['assignments'][0]['result_refs'][0]['reference']
            assert current['document_id'] == identifiers['material']
            assert current['result_sha256'] == evidence['exact_result']['result_sha256']
            assert wb.document_result(current['document_id'], current['job_id'])['responses']['u_z']['value'] == [1., 2., 3.]
            assert not wb.manager.list()
        if phase == 1 and evidence.get('controlled_local'):
            from caelab.assist.experts import RuntimeConfig
            from examples.research_team_public import finish
            runtime = wb.assistance().experts
            runtime.definitions = {row['id']: deepcopy(row) for row in CONFIG['experts']}
            runtime.runtime = RuntimeConfig(provider='openscience', model='openai-codex/test-double',
                external_model=False, max_model_calls=8, max_tool_calls=8, max_seconds=120)
            draft = deepcopy(expert['draft'])
            draft['context']['transmission_scope'] = {'allow_question': True, 'allow_results': True,
                'collections': ['research'], 'source_refs': deepcopy(draft['context']['selected_sources']),
                'result_ids': [current['job_id']]}
            proof = capture_result_verification(wb, current)  # Explicit new local picker adoption.
            selected = make_result_selection(proof, source_id='SlocalExplicit',
                selection_request=evidence['selected_result']['selector'])
            for assignment in draft['context']['research_team']['assignments']:
                assignment['result_refs'] = [deepcopy(selected)]
            expert = update(wb, expert, draft)
            before = deepcopy(expert)
            with controlled_korean_generation() as calls:
                response = cmd(wb, before, 'expert.ask', command_id='CexplicitLocalAsk')
                expert, result = finish(wb, before, response)
                count = len(calls)
                assert count and result['status'] == 'ANSWERED', result
                retry = cmd(wb, before, 'expert.ask', command_id='CexplicitLocalAsk')
                assert retry['job']['id'] == response['job']['id'] and len(calls) == count
                wb.document_read(expert['id']); wb.document_read(expert['id'])
                assert len(calls) == count
                for index in (1, 2):
                    expert, result = finish(wb, expert, cmd(wb, expert, 'expert.advance', command_id='CexplicitContinue' + str(index)))
                    assert result['status'] == 'ANSWERED', result
                kinds = [row['task']['kind'] for row in calls if row['kind'] == 'role']
                assert 'QUESTION' in kinds and 'ANSWER' in kinds
                expert = saved(wb, wb.document_read(expert['id']))
                save_json(output / 'controlled-local.json', {'label': LABEL, 'calls': calls,
                    'job_id': response['job']['id'], 'lost_reply_same_job': True, 'paid_provider_calls': 0,
                    'actual_team_owner_budget_and_tools': True, 'actual_model': False})
        if phase == 1:
            second = publish(wb, list(identifiers.values()), output / '재복사 2', 'CteamRecopy')
            save_json(output / 'second.json', second)
        save_json(output / ('cold-' + str(phase) + '.json'), {'status': 'PASSED',
            'pid': __import__('os').getpid(), 'session_id': wb.session_id, 'provider': 'NOT_CONFIGURED',
            'origin_calls': 0, 'solver': 'NOT_RUN', 'label': LABEL, 'result_reference': current})
    finally:
        assert wb.shutdown()['joined']


def run(output, *, controlled_local=False):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('새 출력 폴더를 지정하세요.')
    output.mkdir(parents=True)
    wb = Workbench(output / '원 store', configuration=CONFIG)
    try:
        records = seed(wb)
        records['controlled_local'] = bool(controlled_local)
        save_json(output / 'evidence.json', records)
        save_json(output / 'first.json', publish(wb, records['documents'], output / '사본 1', 'CteamFirstCopy'))
    finally:
        assert wb.shutdown()['joined']
    owned_remove(output, output / '원 store')
    for phase in (1, 2):
        process = subprocess.run([sys.executable, '-m', 'examples.research_team_desktop_public',
            '--output', str(output), '--cold', str(phase)], capture_output=True, text=True, encoding='utf-8')
        save_json(output / ('process-' + str(phase) + '.json'), {'returncode': process.returncode,
            'stdout': process.stdout, 'stderr': process.stderr})
        if process.returncode:
            raise RuntimeError('별도 현지 열람 검사 실패: process-' + str(phase) + '.json')
        if phase == 1:
            owned_remove(output, output / '사본 1')
    receipt = {'status': 'PASSED', 'cold_children': [load_json(output / ('cold-' + str(p) + '.json')) for p in (1, 2)],
        'role_reply': 'CONTROLLED_FIXTURE', 'observation': 'CONTROLLED_FIXTURE', 'actual_ai_answer': False,
        'actual_team_runtime': 'CONTROLLED_GENERATION_ONLY' if controlled_local else 'NOT_TESTED_HERE', 'provider': 'NOT_RUN', 'solver': 'NOT_RUN'}
    save_json(output / 'receipt.json', receipt)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cold', type=int, choices=(1, 2))
    parser.add_argument('--controlled-local', action='store_true', help='Explicit offline generation-only double for one new local Ask.')
    args = parser.parse_args()
    if args.cold:
        cold(args.output.resolve(), args.cold)
    else:
        print(run(args.output, controlled_local=args.controlled_local))
