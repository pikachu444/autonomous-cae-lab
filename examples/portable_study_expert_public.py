"""Public exact-literature / S-X-B portable roundtrip (NO AI/provider).

Run: python -m examples.portable_study_expert_public --output <NEW folder>
Creates only beneath a new output folder. Two *separate* cold processes open
without the earlier stores. Scripted completion/dependency boundaries are
labelled TEST DOUBLE; real owners, dispatcher, Runtime source/transmission /
session checks, save/Undo, archive and publication run unchanged. Not a Windows
Qt/native or engineering qualification. No network, provider, install or account.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager, ExitStack
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from unittest.mock import patch

from caelab.workbench import Workbench
from caelab.assist.experts import RuntimeConfig
from caelab.jobs import TERMINAL
from caelab.portable_project import create_copy, inspect_copy, open_project, MANIFEST
from caelab.portable_research_owner import logical_run, live_rounds, live_turns
from caelab.storage import canonical_hash, load_json, save_json
from caelab.evaluation import file_hash

LABEL = 'CONTROLLED RUNTIME TEST RECORD — NOT AN AI ANSWER'
ROLES = [{'id': name, 'label': name, 'instructions': 'Public scripted boundary only.',
          'collections': ['research'], 'tools': ['knowledge.source', 'knowledge.search']}
         for name in ('testing', 'skeptic')]


def cmd(wb, document, operation, arguments=None, command_id=None):
    return wb.document_command(document['id'], operation, arguments or {},
        session_id=wb.session_id, expected_generation=document['generation'], command_id=command_id)


def update(wb, doc, draft):
    return cmd(wb, doc, doc['kind'] + '.update', {'draft': draft})['document']


def saved(wb, doc):
    return cmd(wb, doc, 'document.save')['document']


def finished(wb, document, response):
    job_id = response['job']['id']
    end = time.monotonic() + 20
    while time.monotonic() < end:
        job = wb.manager.status(job_id)
        if job['state'] in TERMINAL:
            return wb.document_read(document['id']), (wb.manager.result(job_id) if job.get('result_refs') else
                {'status': job['state'], 'error': job.get('error'), 'result_available': False})
        time.sleep(.005)
    raise TimeoutError('Owned scripted job did not reach a terminal state')


class ControlledBoundary:
    """Only generation/dependency discovery is substituted; current gates run."""
    def __init__(self, wb):
        self.runtime = wb.assistance().experts
        self.calls = []
        self.failure = False
        self.release = threading.Event()
        self.release.set()

    def complete(self, definition, generator, question, context, session, path, workspace_id, budget, visited):
        # These are the very same primary Runtime guards its real agent uses.
        context, snippets = self.runtime._knowledge_context(context, workspace_id, definition['collections'])
        self.runtime._transmission_check({'question': question, 'context': context, 'sources': snippets}, context)
        budget.consume('model')
        call = {'question': question, 'context': deepcopy(context), 'session_id': session['session_id'],
                'workspace_id': workspace_id, 'label': LABEL}
        self.calls.append(call)
        assert self.release.wait(20), 'owned controlled generation release timed out'
        sources = [{key: deepcopy(row[key]) for key in ('document_id', 'revision', 'locator', 'title', 'collection')}
                   for row in snippets]
        result = {'expert_id': definition['id'], 'session_id': session['session_id'],
            'status': 'FAILED' if self.failure else 'ANSWERED',
            'execution_status': 'FAILED' if self.failure else 'SUCCEEDED',
            'answer': None if self.failure else LABEL + '\n' + question,
            'reason': LABEL + ': scripted failure' if self.failure else None,
            'sources': sources, 'assumptions': [], 'proposed_actions': [], 'tool_events': [],
            'inference_performed': False, 'test_boundary': LABEL}
        session['turns'].append({'question': question, 'response': deepcopy(result)})
        save_json(path, session)
        return result


@contextmanager
def controlled(wb):
    boundary = ControlledBoundary(wb)
    runtime = boundary.runtime
    config = RuntimeConfig(generator=object(), external_model=True,
        transmission={'allow_external_model': True, 'allow_question': True, 'collections': ['research'], 'allow_results': False})
    with ExitStack() as stack:
        stack.enter_context(patch.object(runtime, 'definitions', {row['id']: deepcopy(row) for row in ROLES}))
        stack.enter_context(patch.object(runtime, 'runtime', config))
        stack.enter_context(patch.object(runtime, '_ask', boundary.complete))
        # No installation. The labelled generator does not use Haystack.
        stack.enter_context(patch('caelab.assist.readiness.require_features', return_value=None))
        try:
            yield boundary
        finally:
            boundary.release.set()


@contextmanager
def source_free(wb):
    """Cold reading has no submission/search/extraction, including local providers."""
    def forbidden(*args, **kwargs):
        raise AssertionError('cold read/save/Undo attempted dispatch/search/index/extraction')
    with ExitStack() as stack:
        for obj, name in ((wb, 'submit'), (wb.manager, 'submit'),
                          (wb.assistance().knowledge, 'search'), (wb.assistance().knowledge, 'ingest'),
                          (wb.assistance().literature, 'fetch')):
            stack.enter_context(patch.object(obj, name, forbidden))
        stack.enter_context(patch('caelab.assist.knowledge.read_segments', forbidden))
        yield


def ask_draft(doc, source, *, question='검사 질문', authorized=False, roles=('testing',)):
    draft = deepcopy(doc['draft'])
    draft['participants'] = list(roles)
    draft['composer']['text'] = question
    draft['context'] = {'selected_sources': [{'document_id': source['document_id'], 'revision': 1}],
                        'selected_document_ids': [source['document_id']]}
    if authorized:
        draft['context']['transmission_scope'] = {'allow_question': True, 'collections': ['research'],
            'source_refs': deepcopy(draft['context']['selected_sources']), 'result_ids': []}
    return draft


def fixture(wb, *, history=True):
    """Only public synthetic documents; all captured text carries this label."""
    upload = wb.upload('공개 문헌.md', '# Same title\nPublic revision ONE.\n\n## Observation\nCONTROLLED 17 MPa; not experimental data.\n'.encode())
    store = wb.assistance().knowledge
    source = store.ingest(wb.input_path(upload['id']), 'research',
        metadata={'title': 'Same title', 'author': 'Public fixture', 'year': 2026,
                  'source': 'Synthetic local Markdown', 'access_scope': 'public'}, workspace_id=wb.workspace_id)
    original = store.source(source['document_id'], 1, workspace_id=wb.workspace_id)
    locator = original['segments'][-1]['locator']
    selected = store.source(source['document_id'], 1, locator, workspace_id=wb.workspace_id)
    ref = {'kind': 'knowledge', 'document_id': source['document_id'], 'revision': 1,
           'locator': deepcopy(locator), 'source_sha256': original['sha256'], 'content_sha256': canonical_hash(selected)}
    upload2 = wb.upload('같은 제목 다른 개정.md', b'# Same title\nRevision TWO: NOT the selected evidence.\n')
    store.ingest(wb.input_path(upload2['id']), 'research', document_id=source['document_id'],
        metadata={'title': 'Same title', 'access_scope': 'public'}, workspace_id=wb.workspace_id)
    study = wb.document_open(kind='study')
    draft = deepcopy(study['draft'])
    draft['question'] = '관측이 가설을 구별하는가?'
    draft['hypotheses'] = [{'id': 'Hone', 'title': '가설', 'statement': '공개 합성 관측에 대한 작성 가설', 'status': 'UNKNOWN'}]
    draft['evidence'] = [{'id': 'Epaper', 'label': '첫 개정의 관측 구간', 'kind': 'knowledge', 'reference': ref, 'note': '인용 한계를 유지'}]
    draft['decisions'] = [{'id': 'Djudge', 'title': '보류', 'statement': '상반 근거를 더 관측한다.',
        'hypothesis_ids': ['Hone'], 'supporting': ['Epaper'], 'conflicting': ['Epaper'], 'status': 'UNKNOWN'}]
    draft['next_observations'] = [{'id': 'Onext', 'question': '독립 관측이 필요한가?', 'hypothesis_ids': ['Hone'],
        'evidence_ids': ['Epaper'], 'status': 'PLANNED', 'note': '미실행'}]
    study = saved(wb, update(wb, study, draft))
    expert = wb.document_open(kind='expert')
    expert = update(wb, expert, ask_draft(expert, source, question='이전 질문 — TEST DOUBLE', authorized=True))
    if history:
        with controlled(wb) as runtime:
            expert, result = finished(wb, expert, cmd(wb, expert, 'expert.ask', command_id='CoriginalCompleted'))
            assert result['status'] == 'ANSWERED', result
            expert = update(wb, expert, ask_draft(expert, source, question='이전 실패 질문', authorized=True))
            runtime.failure = True
            expert, result = finished(wb, expert, cmd(wb, expert, 'expert.ask', command_id='CoriginalFailed'))
            assert result['status'] == 'FAILED', result
            runtime.failure = False
            expert = update(wb, expert, ask_draft(expert, source, question='원 READY 시도', authorized=True, roles=('testing', 'skeptic')))
            expert, result = finished(wb, expert, cmd(wb, expert, 'expert.ask', command_id='CoriginalReady'))
            assert expert['discussion']['rounds'][-1]['status'] == 'READY'
    expert = saved(wb, expert)
    # Acknowledged but not yet saved composer: no widget is harvested by copy.
    expert = update(wb, expert, ask_draft(expert, source, question='보관한 미완성 질문 — 새 사본에서 계속 편집', authorized=True))
    report = wb.document_open(kind='report')
    binding = wb.report_capture(report['id'], ref)
    asset = wb.report_documents._folder(report['id']) / 'assets' / (binding['id'] + '.json')
    # Frozen canonical content is unchanged, but its actual raw bytes are unusual.
    asset.write_text(json.dumps(json.loads(asset.read_text()), ensure_ascii=False, indent=5) + '\n', encoding='utf-8')
    raw = asset.read_bytes()
    draft = deepcopy(report['draft'])
    draft['title'] = '문헌에 기반한 연구 보고서'
    draft['sections'] = [{'id': 'Eliterature', 'title': '원 관측', 'text': '새 판단과 원문은 별도로 보존한다.',
        'include': True, 'table': True, 'curve': False, 'asset': binding}]
    report = saved(wb, update(wb, report, draft))
    return {'documents': [study['id'], expert['id'], report['id']], 'study': study, 'expert': expert,
        'report': report, 'reference': ref, 'binding': binding, 'source': source,
        'frozen_bytes_sha256': __import__('hashlib').sha256(raw).hexdigest(),
        'original_turns': deepcopy(expert['discussion']['turns']),
        'original_rounds': deepcopy(expert['discussion']['rounds']),
        'original_runs': [logical_run(row) for row in expert['runs']], 'source_payload': selected}


def publish(wb, identifiers, destination, command_id='CpublicCopy'):
    plan = inspect_copy(wb, identifiers)
    if plan['status'] != 'READY':
        raise AssertionError(plan['issues'])
    made = create_copy(wb, plan, destination, approved=True, command_id=command_id, session_id=wb.session_id)
    # Lost response: exact same command discovers the already published copy.
    confirmed = create_copy(wb, plan, destination, approved=True, command_id=command_id, session_id=wb.session_id)
    assert made['project_id'] == confirmed['project_id']
    return made


def rows(receipt):
    return {row['kind']: row['document_id'] for row in receipt['documents']}


def owned_remove(root, target):
    """Compatibility name: move only generated children aside, preserving bytes."""
    root, target = Path(root).resolve(), Path(target).resolve()
    if target == root or not target.is_relative_to(root) or target.is_symlink():
        raise ValueError('Refuse deletion outside this runnable-owned child')
    # Keep generated evidence while proving the old location is unavailable.
    target.rename(target.with_name(target.name + '.preserved'))


def cold(output, phase):
    evidence = load_json(output / 'evidence.json')
    receipt = load_json(output / ('first.json' if phase == 1 else 'second.json'))
    folder = output / ('사본 1' if phase == 1 else '재복사 2')
    assert not (output / '원 store').exists()
    if phase == 2:
        assert not (output / '사본 1').exists()
    wb = open_project(folder)
    try:
        ids = rows(receipt)
        with source_free(wb):
            source = wb.research_reference(evidence['reference'])
            assert source['source'] == evidence['source_payload']
            assert source['source_metadata']['metadata']['author'] == 'Public fixture'
            docs = {kind: wb.document_read(identifier) for kind, identifier in ids.items()}
            expert = docs['expert']
            assert expert['discussion']['turns'][:len(evidence['original_turns'])] == evidence['original_turns']
            assert expert['discussion']['rounds'][:len(evidence['original_rounds'])] == evidence['original_rounds']
            assert [logical_run(run) for run in expert['runs'][:len(evidence['original_runs'])]] == evidence['original_runs']
            assert not live_rounds(wb.discussion_documents._documents[expert['id']])
            assert not wb.manager.list()
            content = wb.report_content(ids['report'], [evidence['binding']])['assets'][0]
            assert content['source_status'] == 'AVAILABLE' and content['navigation_reference'] == evidence['reference']
            assert content['content']['source'] == evidence['source_payload']
            for kind, doc in docs.items():
                draft = deepcopy(doc['draft'])
                if kind == 'study':
                    draft['question'] += ' / 현재 편집'
                    assert draft['decisions'][0]['status'] == 'UNKNOWN'
                elif kind == 'expert':
                    draft['composer']['text'] += ' / 현재 편집'
                else:
                    draft['title'] += ' / 현재 편집'
                updated = update(wb, doc, draft)
                undo = cmd(wb, updated, 'document.undo')['document']
                assert undo['draft'] == doc['draft']
                redo = cmd(wb, undo, 'document.redo')['document']
                assert redo['draft'] == draft
                docs[kind] = saved(wb, redo)
            assert not wb.manager.list()
            report_doc = docs['report']
            raw = wb.report_documents._folder(ids['report']) / 'revisions' / report_doc['saved_revision'] / 'assets' / (evidence['binding']['id'] + '.json')
            assert file_hash(raw) == evidence['frozen_bytes_sha256']
        if phase == 1:
            runtime = wb.assistance().experts
            runtime.definitions = {row['id']: deepcopy(row) for row in ROLES}
            expert = docs['expert']
            kept_question = expert['draft']['composer']['text']
            expert, result = finished(wb, expert, cmd(wb, expert, 'expert.ask', command_id='ClocalNotConfigured'))
            assert result['status'] == 'NOT_CONFIGURED' and expert['draft']['composer']['text'] == kept_question
            with controlled(wb) as boundary:
                # Copied origin grant must be absent. Current runtime alone is insufficient.
                assert 'transmission_scope' not in expert['draft']['context']
                rejected = cmd(wb, expert, 'expert.ask', command_id='ClocalDenied')
                expert, rejected_result = finished(wb, expert, rejected)
                assert not boundary.calls and expert['draft']['composer']['text'] == kept_question
                assert wb.manager.status(rejected['job']['id'])['state'] == 'FAILED'
                draft = ask_draft(expert, evidence['source'], question=kept_question, authorized=True)
                expert = update(wb, expert, draft)
                response = cmd(wb, expert, 'expert.ask', command_id='ClocalApproved')
                expert, result = finished(wb, expert, response)
                assert result['answer'].startswith(LABEL) and len(boundary.calls) == 1
                sent = boundary.calls[0]
                original_ids = {turn['id'] for turn in evidence['original_turns']}
                assert not any(turn['id'] in original_ids for turn in sent['context']['discussion']['turns'])
                assert sent['workspace_id'] == wb.workspace_id != 'local'
                assert sent['session_id'] not in {sid for record in evidence['original_rounds'] for sid in record['sessions'].values()}
                expert = saved(wb, expert)
                save_json(output / 'controlled-current.json', {'label': LABEL, 'calls': boundary.calls,
                    'result': result, 'paid_provider_calls': 0, 'actual_ai_answer': False})
            second = publish(wb, list(ids.values()), output / '재복사 2', 'Crecopy')
            save_json(output / 'second.json', second)
        else:
            assert any(LABEL in str(turn.get('text')) for turn in docs['expert']['turns'])
        save_json(output / ('cold-' + str(phase) + '.json'), {'status': 'PASS', 'pid': os.getpid(),
            'label': LABEL, 'phase': phase, 'workspace': wb.workspace_id, 'paid_provider_calls': 0,
            'actual_ai_answer': False, 'native_qt_windows': 'NOT_RUN'})
    finally:
        closed = wb.shutdown()
        if not closed['joined'] or closed['pending']:
            raise AssertionError(closed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cold', type=int, choices=(1, 2))
    args = parser.parse_args()
    output = args.output.resolve()
    if args.cold:
        cold(output, args.cold)
        print('PASS cold', args.cold, 'pid', os.getpid(), LABEL, flush=True)
        return
    output.mkdir(parents=True, exist_ok=False)
    wb = Workbench(output / '원 store')
    try:
        case = fixture(wb)
        save_json(output / 'evidence.json', case)
        made = publish(wb, case['documents'], output / '사본 1')
        save_json(output / 'first.json', made)
    finally:
        closed = wb.shutdown()
        if not closed['joined'] or closed['pending']:
            raise AssertionError(closed)
    owned_remove(output, output / '원 store')
    pids = []
    for phase in (1, 2):
        if phase == 2:
            owned_remove(output, output / '사본 1')
        command = [sys.executable, '-m', __name__ if __name__ != '__main__' else 'examples.portable_study_expert_public',
                   '--output', str(output), '--cold', str(phase)]
        result = subprocess.run(command, timeout=150, capture_output=True, text=True, encoding='utf-8')
        (output / ('process-' + str(phase) + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        pids.append(load_json(output / ('cold-' + str(phase) + '.json'))['pid'])
    assert len(set([os.getpid(), *pids])) == 3
    record = {'status': 'PASS', 'parent_pid': os.getpid(), 'cold_pids': pids,
        'two_separate_processes': True, 'origin_store_moved_aside': True, 'first_copy_moved_aside': True,
        'paid_provider_calls': 0, 'actual_ai_answer': False, 'boundary': LABEL, 'windows_qt': 'NOT_RUN'}
    save_json(output / 'result.json', record)
    print(json.dumps(record, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
