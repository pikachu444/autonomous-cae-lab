"""Public research-team example. Controlled generation is explicit and offline.

Only text generation is replaced; owners, scoped tools, budgets and the pinned
Co-STORM step/knowledge-base implementation remain the real application code.
"""
from contextlib import contextmanager
from copy import deepcopy
import argparse
import json
from pathlib import Path
import time
from unittest.mock import patch


@contextmanager
def controlled_generation():
    """Reusable generation-only double, with no account or network fallback."""
    from caelab.assist._vendor.costorm import prompting
    calls = []
    def host(prompt, tools, budget, model, **options):
        if 'Conversation and request JSON: ' in prompt:
            payload = json.loads(prompt.split('Conversation and request JSON: ', 1)[1])
            task = payload['context']['research_task']
            calls.append({'kind': 'role', 'task': deepcopy(task), 'max_steps': options['max_steps']})
            sources = []
            if 'knowledge_source' in tools and payload.get('source_segments'):
                source = payload['source_segments'][0]
                ref = {key: source[key] for key in ('document_id', 'revision', 'locator')}
                assert tools['knowledge_source']['call'](**ref)['segments']
                sources = [ref]
            question = task['kind'] == 'QUESTION'
            return json.dumps({'answer': 'CONTROLLED ' + task['kind'] + ' ' + task['actor_id'],
                'sources': sources, 'assumptions': ['Controlled text, not a live expert answer.'],
                'proposed_actions': [{'purpose': 'Compare a repeat calibration before interpreting the observation.'}],
                'research_reply': {'kind': 'question' if question else 'hypothesis',
                    'claims': [] if question else [{'text': 'Check calibration and load direction.',
                        'basis': 'inferred', 'conditions': ['same measured quantity'],
                        'source_refs': sources, 'missing_evidence': ['repeat observation']}],
                    'questions': [{'expert_id': 'r0', 'target_turn_id': task['target_turn_id'],
                        'target_claim_id': task['target_claim_id'], 'question': 'Which repeat observation distinguishes this?',
                        'discriminating_observation': 'repeat calibration'}] if question else [],
                    'revisions': [], 'unknowns': [{'input': 'repeat observation', 'blocks_judgement': True,
                                                 'next_observation': 'repeat calibration'}]}}, ensure_ascii=False)
        assert tools == {} and options['max_steps'] == 1
        calls.append({'kind': 'service', 'prompt': prompt, 'max_steps': 1})
        # Predict.forward below still crosses the actual Completion adapter,
        # reservation/checkpoint and exact replay journal for every generated text.
        return prompt.split('\nCONTROLLED_SIGNATURE\n', 1)[1]

    def prediction(self, **kwargs):
        name = self.signature.__name__
        values = {'InsertInformationCandidateChoice': {'decision': 'Best placement: [1]'},
            'InsertInformation': {'choice': 'insert'}, 'ExpandSection': {'output': 'None'},
            'KnowledgeBaseSummmary': {'output': 'Calibration observations and limitations.'}}.get(name)
        if name == 'WriteSection':
            import re
            number = re.search(r'\[(\d+)\]', kwargs['info']).group(1)
            values = {'output': 'CONTROLLED: compare the retained calibration observation.[' + number + ']'}
        if values is None:raise AssertionError('Unscripted generation signature: ' + name)
        lm = prompting._current.get()['lm']
        raw = lm(json.dumps({'signature': name, 'inputs': kwargs}, ensure_ascii=False)
                 + '\nCONTROLLED_SIGNATURE\n' + json.dumps(values, ensure_ascii=False))[0]
        return prompting.Prediction(**json.loads(raw))
    with patch('caelab.assist.openscience_host.run_openscience', host), patch.object(prompting.Predict, 'forward', prediction):
        yield calls


def create_case(root, *, limit=4):
    from caelab.workbench import Workbench
    from caelab.discussion_document import default_draft
    roles = json.loads((Path(__file__).with_name('cae_research_experts.json')).read_text(encoding='utf-8'))
    config = {'experts': roles, 'runtime': {'provider': 'openscience', 'model': 'openai-codex/test-double',
        'external_model': False, 'max_model_calls': 8, 'max_tool_calls': 8, 'max_seconds': 120}}
    wb = Workbench(root, configuration=config)
    try:
        source = wb.root / 'public-observation.md'
        source.write_text('# Public observation\nMeasured length is 12 mm. Verify calibration and load direction.', encoding='utf-8')
        saved = wb.assistance().knowledge.ingest(str(source), collection='public')
        reference = {key: saved[key] for key in ('document_id', 'revision')}
        draft = default_draft(); draft['participants'] = [r['id'] for r in roles]
        draft['composer']['text'] = '관측을 해석하기 전에 어떤 조건을 구별해야 하나요?'
        draft['budget'] = {'model_calls': limit, 'tool_calls': 8, 'consultations': 0, 'seconds': 120}
        draft['context'] = {'discussion_mode': 'costorm', 'selected_sources': [reference], 'research_team': {
            'version': 2, 'phase_id': None, 'parent_phase_id': None, 'objective': draft['composer']['text'],
            'deliverable': '근거 가설과 판별 질문', 'assignments': [{'expert_id': role['id'],
                'mode': 'investigator', 'question': role['label'] + ' 관점의 근거와 불확실성을 조사하세요.',
                'checks': [], 'tools': role['tools'], 'source_refs': [deepcopy(reference)], 'result_refs': []} for role in roles],
            'shared_evidence': [], 'carry_forward_turn_ids': [], 'requested_next': None, 'turn_limit': 8, 'stop_when': []}}
        return wb, wb.document_open(kind='expert', draft=draft), config
    except BaseException:
        wb.shutdown(); raise


def command(wb, document, operation):
    return wb.document_command(document['id'], operation, {}, session_id=document['session_id'],
                               expected_generation=document['generation'])


def finish(wb, document, response, *, seconds=40):
    identifier = response['job']['id']; deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        status = wb.manager.status(identifier)
        if status['state'] in {'SUCCEEDED', 'FAILED', 'CANCELLED', 'PARTIAL_FAILURE'}:
            return wb.document_read(document['id']), wb.manager.result(identifier)
        time.sleep(.005)
    raise TimeoutError('The owned controlled action did not finish: ' + identifier)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--controlled', action='store_true', help='Explicit offline generation double; never a live provider.')
    args = parser.parse_args()
    if args.output.exists():raise ValueError('Use a new output directory; existing research is preserved.')
    wb, document, _ = create_case(args.output / 'workbench')
    try:
        results = []; calls = []
        if args.controlled:
            with controlled_generation() as calls:
                for operation in ('expert.ask', 'expert.advance', 'expert.advance'):
                    document, result = finish(wb, document, command(wb, document, operation))
                    results.append({'operation': operation, 'status': result['status'], 'usage': result['costorm']['usage']})
                    if result['status'] != 'ANSWERED':break
        document = command(wb, document, 'document.save')['document']
        summary = {'mode': 'CONTROLLED' if args.controlled else 'PREPARED_NO_INFERENCE',
            'document_id': document['id'], 'saved_revision': document['saved_revision'],
            'actions': results, 'generation_calls': calls, 'live_provider_calls': 0,
            'engineering_qualification': 'UNKNOWN'}
        (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k: v for k, v in summary.items() if k != 'generation_calls'}, ensure_ascii=False))
    finally:
        if not wb.shutdown()['joined']:raise RuntimeError('Owned workers did not join')


if __name__ == '__main__':main()
