"""Real vendored runner/owner with explicit scripted completion test doubles.

No account, provider, public search, solver or engineering acceptance is tested.
"""
from copy import deepcopy
import json
import time

import pytest

from caelab.assist._vendor.costorm import prompting
from caelab.assist._vendor.costorm.collaborative_storm.modules.warmstart_hierarchical_chat import SectionToConvTranscript
from caelab.assist.costorm import report_record
from caelab.discussion_document import default_draft
from caelab.workbench import Workbench


def test_prompt_bridge_full_multiline_fields_and_no_provider_defaults():
    class LM:
        def __call__(self, prompt, **kwargs):
            assert 'Now give engaging question only.\nQuestion:' in prompt
            return ['What was measured?\nNow give engaging answer only with all inline citations from original text.\nAnswer:\nStress was measured.[3]']
    with prompting.settings.context(lm=LM()):
        result = prompting.Predict(SectionToConvTranscript)(topic='Test', section_name=['root', 'Test'],
                                                           section_content='Retained evidence.[3]')
    assert result.question == 'What was measured?'
    assert result.answer == 'Stress was measured.[3]'
    with pytest.raises(RuntimeError, match='explicit'):
        prompting.Predict(SectionToConvTranscript)(topic='Test', section_name='Test', section_content='Data')
    from caelab.assist._vendor.costorm.collaborative_storm.engine import CollaborativeStormLMConfigs
    with pytest.raises(ValueError, match='explicit'):
        CollaborativeStormLMConfigs().init('openai')


@pytest.fixture
def scripted(monkeypatch):
    calls = []
    def host(prompt, tools, budget, model, **options):
        assert tools == {} and options['max_steps'] == 1
        calls.append(prompt)
        return prompt.split('\nTEST_SIGNATURE\n', 1)[1]
    monkeypatch.setattr('caelab.assist.openscience_host.run_openscience', host)

    def prediction(self, **kwargs):
        """Only the text-generation boundary is scripted; runner decisions/KB run."""
        name = self.signature.__name__
        values = {
            'QuestionToQuery': {'queries': 'ALPHA stress'},
            'AnswerQuestion': {'answer': 'ALPHA stress is 17 MPa.[1]'},
            'GenerateExpertGeneral': {'experts': '1. Testing: Review measurement.\n2. Mechanics: Review assumptions.'},
            'GenerateExpertWithFocus': {'experts': '1. Testing: Review intervention.\n2. Mechanics: Review assumptions.'},
            'WarmStartModerator': {'question': 'What is ALPHA stress?'},
            'WritePageOutline': {'outline': '# Measurements\n# Assumptions'},
            'GenerateWarmStartOutline': {'outline': '# Measurements\n# Assumptions'},
            'InsertInformationCandidateChoice': {'decision': 'Best placement: [1]'},
            'InsertInformation': {'choice': 'insert'},
            'ExpandSection': {'output': 'None'},
            'KnowledgeBaseSummmary': {'output': 'ALPHA measurement and assumptions.'},
            'GenExpertActionPlanning': {'resposne': 'Potential Answer: Discuss ALPHA stress.'},
            'GroundedQuestionGeneration': {'output': 'How does the ALPHA measurement depend on the test conditions?'},
        }.get(name)
        if name == 'WriteSection':
            import re
            number = re.search(r'\[(\d+)\]', kwargs['info']).group(1)
            values = {'output': 'ALPHA stress is 17 MPa.[' + number + ']'}
        elif name == 'SectionToConvTranscript':
            values = {'question': 'What was measured?', 'answer': kwargs['section_content']}
        elif name == 'ConvertUtteranceStyle':
            values = {'utterance': kwargs['content']}
        assert values is not None, name
        lm = prompting._current.get()['lm']
        payload = json.dumps(values, ensure_ascii=False)
        raw = lm(json.dumps({'signature': name, 'inputs': kwargs}, ensure_ascii=False)
                 + '\nTEST_SIGNATURE\n' + payload)[0]
        return prompting.Prediction(**json.loads(raw))
    monkeypatch.setattr(prompting.Predict, 'forward', prediction)
    return calls


def configured(tmp_path):
    roles = [{'id': name, 'label': name, 'instructions': 'Use actual source evidence.',
              'collections': ['research'], 'tools': ['knowledge.search', 'knowledge.source']}
             for name in ('testing', 'mechanics')]
    config = {'experts': roles, 'runtime': {'provider': 'openscience', 'model': 'openai-codex/test-double',
        'external_model': False, 'max_model_calls': 100, 'max_tool_calls': 100, 'max_seconds': 60}}
    wb = Workbench(tmp_path, configuration=config)
    path = wb.root / 'source.md'
    path.write_text('# ALPHA\nALPHA stress is 17 MPa. Check the measured area.', encoding='utf-8')
    source = wb.assistance().knowledge.ingest(str(path), collection='research')
    other = wb.root / 'unselected.md'
    other.write_text('# ALPHA\nUNSELECTED-B 99999 SECRET.', encoding='utf-8')
    wb.assistance().knowledge.ingest(str(other), collection='research')
    draft = default_draft()
    draft['participants'] = ['testing', 'mechanics']
    draft['composer']['text'] = 'What do the ALPHA measurements show?'
    draft['context'] = {'discussion_mode': 'costorm', 'selected_sources': [
        {'document_id': source['document_id'], 'revision': source['revision']}]}
    draft['budget'] = {'model_calls': 100, 'tool_calls': 100, 'consultations': 0, 'seconds': 60}
    return wb, wb.document_open(kind='expert', draft=draft), source, config


def command(wb, doc, operation, arguments=None):
    return wb.document_command(doc['id'], operation, arguments or {},
        session_id=doc['session_id'], expected_generation=doc['generation'])


def finished(wb, doc, response):
    identifier = response['job']['id']
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        status = wb.manager.status(identifier)
        if status['state'] in {'SUCCEEDED', 'FAILED', 'PARTIAL_FAILURE', 'CANCELLED'}:
            return wb.document_read(doc['id']), wb.manager.result(identifier)
        time.sleep(.005)
    raise AssertionError(wb.manager.status(identifier))


def test_real_runner_intervention_map_report_save_reopen_and_scope(tmp_path, scripted):
    wb, doc, source, config = configured(tmp_path)
    try:
        doc, result = finished(wb, doc, command(wb, doc, 'expert.ask'))
        assert result['status'] == 'ANSWERED', result
        assert result['costorm']['state']['experts']
        assert doc['discussion']['costorm']['topics']
        assert {turn['author'] for turn in doc['turns']} >= {'Testing', 'Mechanics'}
        assert all('UNSELECTED-B' not in prompt for prompt in scripted)
        before = len(wb.manager.list())
        paused = command(wb, doc, 'expert.pause')['document']
        draft = deepcopy(paused['draft'])
        draft['composer']['text'] = 'Please focus next on measured area, not only modulus.'
        edited = command(wb, paused, 'expert.update', {'draft': draft})['document']
        intervened = command(wb, edited, 'expert.intervene')['document']
        assert len(wb.manager.list()) == before
        with pytest.raises(ValueError, match='일시'):
            command(wb, intervened, 'expert.advance')
        resumed = command(wb, intervened, 'expert.resume')['document']
        old_calls = len(scripted)
        doc, result = finished(wb, resumed, command(wb, resumed, 'expert.advance'))
        assert result['status'] == 'ANSWERED', result
        assert any('measured area, not only modulus' in call for call in scripted[old_calls:])
        assert result['costorm']['consumed_user_ids']
        doc, report = finished(wb, doc, command(wb, doc, 'expert.report'))
        assert report['status'] == 'ANSWERED', report
        saved_report = doc['discussion']['costorm']['report']
        assert saved_report['references'] and all(row['source']['revision'] == 1 for row in saved_report['references'])
        doc = command(wb, doc, 'document.save')['document']
        identifier = doc['id']
        calls = len(scripted)
    finally:
        wb.shutdown()
    reopened = Workbench(tmp_path, configuration=config)
    try:
        cold = reopened.document_open(kind='expert', document_id=identifier)
        assert cold['discussion']['costorm']['report'] == saved_report
        assert cold['turns'] == doc['turns']
        assert len(scripted) == calls
        # Generic HTTP/MCP job submissions cannot supply or impersonate runner state.
        forged = {'expert_id': 'testing', 'question': 'X', 'context': {'discussion_mode': 'costorm',
            'costorm': {'document_id': identifier, 'round_id': 'Bmissing'}}}
        with pytest.raises(PermissionError):
            reopened._execute('experts.ask', forged, 'JnotOwner')
    finally:
        reopened.shutdown()


def test_budget_partial_retry_uses_actual_journal_then_revocation_blocks(tmp_path, scripted):
    wb, doc, source, _ = configured(tmp_path)
    try:
        draft = deepcopy(doc['draft']); draft['budget']['model_calls'] = 2
        doc = command(wb, doc, 'expert.update', {'draft': draft})['document']
        doc, result = finished(wb, doc, command(wb, doc, 'expert.ask'))
        assert result['status'] == 'STOPPED'
        assert result['costorm']['retry'] and len(scripted) == 2
        assert result['costorm']['state'].get('conversation_history', []) == []
        draft = deepcopy(doc['draft']); draft['budget']['model_calls'] = 100
        doc = command(wb, doc, 'expert.update', {'draft': draft})['document']
        doc, result = finished(wb, doc, command(wb, doc, 'expert.retry'))
        assert result['status'] == 'ANSWERED', result
        assert result['costorm']['usage']['replayed_completions'] >= 2
        assert result['costorm']['total_usage']['model_calls'] == len(scripted)
        wb.assistance().knowledge.revoke(source['document_id'])
        count = len(scripted)
        with pytest.raises(PermissionError):
            command(wb, doc, 'expert.advance')
        assert len(scripted) == count
    finally:
        wb.shutdown()


def test_unknown_report_citations_remain_explicit():
    report = report_record('Claim.[9]', {'knowledge_base': {'info_uuid_to_info_dict': {}}})
    assert report['status'] == 'INCOMPLETE_CITATIONS'
    assert report['references'] == [{'number': '9', 'source': None, 'status': 'MISSING_SOURCE'}]


def test_failed_worker_carries_exact_completion_before_later_success():
    from caelab.assist._vendor.costorm.concurrency import ContextExecutor
    from caelab.assist.costorm import _retry_journal
    import threading
    journal = []
    release = threading.Event()
    class LM:
        def __call__(self, prompt, **kwargs):
            good = 'good-section' in prompt
            key = 'good-key' if good else 'bad-key'
            if not good:
                assert release.wait(3)
            prompting.last_completion_key.set(key)
            text = ('Question: Measured area?\n'
                    'Now give engaging answer only with all inline citations from original text.\n'
                    'Answer: Exact measurement.[3]') if good else 'Question: Missing answer field'
            journal.append({'key': key, 'text': text, 'prompt': prompt})
            return [text]
    error = None
    with prompting.settings.context(lm=LM()):
        try:
            with ContextExecutor() as executor:
                predictor = prompting.Predict(SectionToConvTranscript)
                bad = executor.submit(predictor, topic='bad-section', section_name='A', section_content='Data')
                good = executor.submit(predictor, topic='good-section', section_name='B', section_content='Data')
                release.set()
                bad.result()
        except ValueError as caught:
            error = caught
    assert good.result().answer == 'Exact measurement.[3]'
    assert journal[-1]['key'] == 'good-key'
    assert error.completion_key == 'bad-key'
    retained = _retry_journal({'journal': journal, 'invalid_completion_key': error.completion_key})
    assert [row['key'] for row in retained] == ['good-key']


def test_unrevised_warmstart_is_displayed_once_without_dropping_new_turns():
    from caelab.assist.costorm import presentation
    turn = {'role': 'Testing', 'utterance': 'Measured value.[1]'}
    state = {'warmstart_conv_archive': [turn], 'conversation_history': [turn, deepcopy(turn)]}
    view = presentation(state)
    assert [row['index'] for row in view['turns']] == [0, 1]


def test_role_without_source_tool_cannot_bypass_permissions(tmp_path, scripted):
    wb, doc, source, _ = configured(tmp_path)
    try:
        wb.assistance().experts.definitions['mechanics']['tools'] = []
        response = command(wb, doc, 'expert.ask')
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and wb.manager.status(response['job']['id'])['state'] not in {'FAILED', 'SUCCEEDED'}:
            time.sleep(.005)
        assert wb.manager.status(response['job']['id'])['state'] == 'FAILED'
        doc = wb.document_read(doc['id'])
        assert doc['discussion']['costorm']['can_retry']
        assert not scripted
    finally:
        wb.shutdown()


def test_source_preflight_failure_does_not_reject_prior_valid_completion():
    from types import SimpleNamespace
    from caelab.assist.costorm import Completion
    prompting.last_completion_key.set('earlier-valid-key')
    def changed_source():
        raise ValueError('Selected retained result changed')
    completion = Completion(None, SimpleNamespace(max_output_tokens=100), {}, 'local',
                            [], None, [], '', changed_source)
    with pytest.raises(ValueError, match='retained result'):
        completion('Next task')
    assert prompting.last_completion_key.get() is None


def test_root_only_evidence_generates_readable_report(scripted):
    from caelab.assist.costorm import _restore, _new_state
    from caelab.assist._vendor.costorm.interface import Information
    from caelab.assist._vendor.costorm.prompting import Prediction
    from caelab.assist._vendor.costorm.vectors import LocalEncoder
    from caelab.assist._vendor.costorm.dataclass import KnowledgeBase
    class LM:
        kwargs = {}
        def __call__(self, prompt, **kwargs):
            return [prompt.split('\nTEST_SIGNATURE\n', 1)[1]]
    kb = KnowledgeBase('ALPHA', LM(), 6, LocalEncoder())
    info = Information('source:exact', 'Retained source', ['ALPHA is 17 MPa'], 'Source',
                       meta={'question': 'What was measured?', 'query': 'ALPHA'})
    kb.insert_information(path='root', information=info)
    report = kb.to_report()
    assert '17 MPa' in report and '[' in report
