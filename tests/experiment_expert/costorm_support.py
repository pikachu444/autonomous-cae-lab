"""Provider/prompt serialization double adapted from public test_costorm_protocol.
Actual vendored runner, permission checks, journal, owner and persistence run.
BM25 search is a selected-source double because Haystack is absent on this host.
"""
from copy import deepcopy
import json
import pytest
from caelab.assist._vendor.costorm import prompting
from caelab.discussion_document import default_draft
from .support import ServiceHost
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


@pytest.fixture
def selected_search(monkeypatch):
    def search(store, query, collections=None, filters=None, top_k=10, *, workspace_id='local', source_refs=None):
        hits=[]
        for ref in source_refs or []:
            source=store.source(**ref,workspace_id=workspace_id,collections=collections)
            hits.extend(deepcopy(source['segments']))
        return {'status':'OK','hits':hits[:top_k]}
    monkeypatch.setattr('caelab.assist.knowledge.KnowledgeStore.search',search)


def configuration():
    roles=[{'id': name,'label':name,'instructions':'Use actual source evidence.',
        'collections':['research'],'tools':['knowledge.search','knowledge.source','results.read']}
        for name in ('testing','mechanics')]
    return {'experts':roles,'runtime':{'provider':'openscience','model':'openai-codex/test-double',
        'external_model':False,'max_model_calls':100,'max_tool_calls':100,'max_seconds':60}}


def discussion(h, calls=2):
    p=h.root/'alpha.md';p.write_text('# ALPHA\nALPHA stress is 17 MPa. Check measured area.',encoding='utf-8')
    source=h.core.assistance().knowledge.ingest(str(p),collection='research')
    d=default_draft();d['participants']=['testing','mechanics']
    d['composer']['text']='What do the ALPHA measurements show?'
    d['context']={'discussion_mode':'costorm','selected_sources':[
        {'document_id':source['document_id'],'revision':source['revision']}]}
    d['budget']={'model_calls':calls,'tool_calls':100,'consultations':0,'seconds':60}
    return h.expert.open(draft=d),source


def execute(h,doc,operation):
    receipt=h.command(doc,operation);job=receipt['job']['id'];h.wait(job)
    h.expert.read(doc) # collect using existing owner
    return job,h.expert.result(doc,job)
