"""Real local commands and persistence; these tests are not live model/CAE acceptance."""
import ast
from copy import deepcopy
from pathlib import Path
import sys
import time

import pytest

from apps.lab.service import LabService
from caelab.workbench import Workbench
from caelab.workbench_client import Client
from caelab.contracts import CapabilityUnavailable
from test_lab_server import running


def finished(wb, job):
    until = time.monotonic() + 15
    while time.monotonic() < until:
        state = wb.manager.status(job['id'])
        if state['state'] in {'SUCCEEDED', 'FAILED', 'CANCELLED'}:
            return state
        time.sleep(.01)
    raise AssertionError('Local calculation did not finish')


def test_registered_external_single_evaluation_and_unknown_command(tmp_path):
    configuration = {'workers': 1, 'external_backends': {'user.calculation': {
        'variables': {'load': {'lower': 0, 'upper': 100}},
        'command': [sys.executable, '-c', "import json;from pathlib import Path;v=json.loads(Path('candidate.json').read_text())['values']['load'];Path('response.csv').write_text('force\\n'+str(v)+'\\n')"],
        'result': {'path': 'response.csv', 'columns': {'force': {'column': 'force', 'unit': 'N',
            'component': 'Y', 'location': 'support'}}}}}}
    wb = Workbench(tmp_path, configuration=configuration)
    try:
        job = wb.submit('evaluate', {'backend': 'user.calculation', 'settings': {}, 'values': {'load': 17.5}})
        assert finished(wb, job)['state'] == 'SUCCEEDED'
        assert list(wb.result(job['id'])['responses']['force']['value']) == [17.5]
        with pytest.raises((ValueError, KeyError, CapabilityUnavailable)):
            wb._execute('evaluate', {'backend': 'unregistered.command', 'settings': {'command': ['anything']}}, 'Jdenied')
    finally:
        assert wb.shutdown()['joined']


def test_selection_discussion_http_save_restart_without_execution(tmp_path):
    service = LabService(tmp_path / 'store')
    with running(service) as transport:
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        wb = transport.server.workbench
        workspace = wb.workspace
        model = client.document_open(kind='material', title='사용자 재료')
        args = dict(document_id=model['id'], session_id=model['session_id'],
            expected_generation=model['generation'], command_id='Cdiscuss')
        receipt = client.selection_discussion(**args)
        discussion = receipt['document']
        assert receipt['executed'] is False
        assert discussion['draft']['context']['selected_model']['input'] == model['draft']
        assert wb.manager.list() == []
        draft = deepcopy(discussion['draft'])
        draft['composer']['text'] = 'Keep the measured density; discuss only contact assumptions.'
        edited = client.document_command(discussion['id'], 'expert.update', {'draft': draft},
            session_id=discussion['session_id'], expected_generation=discussion['generation'], command_id='Cedit')['document']
        again = client.selection_discussion(**args)
        assert again['document']['id'] == discussion['id']
        assert again['document']['draft'] == edited['draft']
        saved_id = discussion['id']
    assert wb.shutdown()['joined']
    reopened = Workbench(workspace)
    try:
        restored = reopened.document_read(saved_id)
        assert restored['draft']['composer']['text'] == draft['composer']['text']
        assert reopened.manager.list() == []
    finally:
        assert reopened.shutdown()['joined']


def test_context_exposes_actual_native_convergence_logs_without_execution(tmp_path):
    wb = Workbench(tmp_path)
    try:
        job = wb.submit('evaluate', {'backend': 'material.felupe', 'settings': {'law': 'missing.user.law'}})
        assert finished(wb, job)['state'] == 'FAILED'
        folder = wb.root / 'native' / job['id']
        folder.mkdir(parents=True)
        (folder / 'calculation.sta').write_text('INCREMENT 4: NO CONVERGENCE\n', encoding='utf-8')
        (folder / 'calculation.cvg').write_text('ITERATION 12 RESIDUAL 0.17\n', encoding='utf-8')
        (folder / 'secret.txt').write_text('not a solver log', encoding='utf-8')
        jobs = wb.manager.list()
        context = wb.engineering_context(job['id'])
        assert context['state'] == 'FAILED'
        assert context['error']['message']
        assert {row['label'] for row in context['logs']} == {'calculation.sta', 'calculation.cvg'}
        assert any('RESIDUAL 0.17' in row['text'] for row in context['logs'])
        assert wb.manager.list() == jobs
        (folder / 'calculation.dat').write_text('ACTUAL CONTACT FORCE\n', encoding='utf-8')
        for index in range(4):
            (folder / f'a-writer-{index}.log').write_text('' if index < 2 else 'Writer diagnostic\n', encoding='utf-8')
            (folder / f'a-writer-{index}.execution.json').write_text(
                '{"status":"SUCCEEDED","stdout":"a-writer-' + str(index) + '.log"}', encoding='utf-8')
        bounded = wb.engineering_context(job['id'])
        assert len(bounded['logs']) == 6
        assert {'calculation.sta', 'calculation.cvg', 'calculation.dat'} <= {
            row['label'] for row in bounded['logs']}
        assert {'a-writer-2.log', 'a-writer-3.log'} <= {row['label'] for row in bounded['logs']}
        assert bounded['limitations']
        assert wb.manager.list() == jobs
        first = wb.desktop.selection_discussion(job_id=job['id'], session_id=wb.session_id,
            command_id='Cfirst')['document']
        (folder / 'calculation.cvg').write_text('ITERATION 13 RESIDUAL 0.12\n', encoding='utf-8')
        refreshed = wb.desktop.selection_discussion(job_id=job['id'], session_id=wb.session_id,
            command_id='Cnewlog')['document']
        assert refreshed['id'] == first['id']
        assert refreshed['draft']['context']['selected_result_ids'] == [job['id']]
        assert any('RESIDUAL 0.12' in row['text'] for row in refreshed['draft']['context']['engineering_context']['logs'])
        original_path = wb.input_path
        def missing_input(identifier):
            raise FileNotFoundError('Original input is missing')
        wb.input_path = missing_input
        original_job = wb.desktop.job_record
        wb.desktop.job_record = lambda identifier: {**original_job(identifier),
            'arguments': {'settings': {'data_id': 'Dmissing'}}}
        missing = wb.engineering_context(job['id'])
        assert any('Original input is missing' in item for item in missing['limitations'])
        assert any('RESIDUAL 0.12' in row['text'] for row in missing['logs'])
        wb.input_path = original_path
        wb.desktop.job_record = original_job
        with pytest.raises(ValueError):
            wb.job_monitor(job['id'], log='../secret.txt')
    finally:
        assert wb.shutdown()['joined']


@pytest.mark.parametrize('backend', ['structure.calculix.frozen', 'structure.calculix.contact',
    'structure.calculix.shell', 'structure.calculix.shell.composite', 'structure.calculix.beam'])
def test_independent_plan_keeps_native_editing_without_a_managed_job(tmp_path, backend):
    from caelab.discussion_document import default_draft
    from caelab.numerical_document import request_draft
    wb = Workbench(tmp_path)
    try:
        model_path = str(tmp_path / 'saved.FCStd')
        draft = default_draft()
        draft['context']['workbench'] = {'model': {'original_path': model_path, 'saved_path': model_path}}
        discussion = wb.document_open(kind='expert', draft=draft)
        source = {'discussion_id': discussion['id'], 'turn_id': 'Aoriginal', 'proposal_index': 0,
            'job_id': 'Jquestion', 'input_revision': 'Ioriginal', 'input_sha256': 'a' * 64,
            'proposal_sha256': 'b' * 64}
        plan = wb.document_open(kind='numerical', draft=request_draft({
            'purpose': 'Edit the native model', 'operation': 'evaluate',
            'inputs': {'backend': backend, 'settings': {'data_id': 'Doriginal'}},
            'budget': {'evaluations': 1}}, source=source))
        receipt = wb.desktop.native_plan_input(plan['id'], session_id=plan['session_id'],
            expected_generation=plan['generation'], command_id='CnativeEdit')
        assert receipt == {'status': 'NATIVE_EDIT_REQUIRED', 'model_path': model_path, 'executed': False}
        assert wb.manager.list() == [] and wb.native_commands.documents() == []
        for invalid in ('structure.calculix.unknown', 'structure.codeaster.frozen'):
            rejected = wb.document_open(kind='numerical', draft=request_draft({
                'purpose': 'Inspect a bound model', 'operation': 'evaluate',
                'inputs': {'backend': invalid, 'settings': {}},
                'budget': {'evaluations': 1}}, source=source))
            with pytest.raises(ValueError, match='Choose a CalculiX Plan'):
                wb.desktop.native_plan_input(rejected['id'], session_id=rejected['session_id'],
                    expected_generation=rejected['generation'], command_id='Cinvalid')
        managed_draft = deepcopy(draft)
        managed_draft['context']['engineering_context'] = {'job_id': 'Jmanaged'}
        managed = wb.document_open(kind='expert', draft=managed_draft)
        managed_plan = wb.document_open(kind='numerical', draft=request_draft({
            'purpose': 'Refresh a managed shell export', 'operation': 'evaluate',
            'inputs': {'backend': 'structure.calculix.shell', 'settings': {}},
            'budget': {'evaluations': 1}}, source={**source, 'discussion_id': managed['id']}))
        with pytest.raises(ValueError, match='supported managed model export'):
            wb.desktop.native_plan_input(managed_plan['id'], session_id=managed_plan['session_id'],
                expected_generation=managed_plan['generation'], command_id='CmanagedUnsupported')
        assert wb.manager.list() == [] and wb.native_commands.documents() == []
    finally:
        assert wb.shutdown()['joined']


def test_independent_file_context_history_save_restart_has_no_execution(tmp_path):
    source = tmp_path / 'user.inp'
    source.write_text('*NODE\n1,0,0,0\n*STEP\n*STATIC\n*END STEP\n')
    log = source.with_suffix('.cvg')
    log.write_text('ITERATION 4 RESIDUAL 0.17\n')
    with running(LabService(tmp_path / 'store')) as transport:
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        wb = transport.server.workbench
        workspace = wb.workspace
        selection = {'path': str(source), 'scope': {'step': 1}}
        observed = client.engineering_context(selection=selection)
        assert 'job_id' not in observed
        assert observed['source']['scope'] == {'step': 1}
        first = client.selection_discussion(session_id=wb.session_id, command_id='Cinput',
            selection=selection, workbench={'model': {'original_path': str(source), 'saved_path': str(source)}})['document']
        log.write_text('ITERATION 5 RESIDUAL 0.12\n')
        second = client.selection_discussion(session_id=wb.session_id, command_id='Cupdated',
            selection=selection, discussion_id=first['id'])['document']
        context = second['draft']['context']
        assert '0.17' in context['engineering_context_history'][0]['logs'][0]['text']
        assert '0.12' in context['engineering_context']['logs'][0]['text']
        assert context['workbench']['model']['saved_path'] == str(source)
        assert wb.manager.list() == []
        identifier = second['id']
    reopened = Workbench(workspace)
    try:
        assert reopened.document_read(identifier)['draft']['context'] == context
        assert reopened.manager.list() == []
    finally:
        assert reopened.shutdown()['joined']


@pytest.mark.parametrize('run_count', [2, 3])
def test_archived_native_reruns_reach_expert_with_bounded_observations_and_readable_originals(run_count, tmp_path, monkeypatch):
    """Public owner/jobs with a labelled injected provider; no live inference/solver."""
    import json
    import uuid
    from caelab.storage import canonical_hash
    calls, references, archived = [], [], []
    policy = {'allow_external_model': True, 'allow_question': True, 'collections': ['materials']}
    wb = Workbench(tmp_path / 'workbench', configuration={
        'experts': [{'id': 'materials', 'instructions': 'Discuss actual selected observations.',
                     'collections': ['materials'], 'tools': ['knowledge.search', 'knowledge.source']}],
        'runtime': {'provider': 'openscience', 'model': 'openai-codex/injected-test-provider',
                    'transmission': policy}})
    def command(document, operation, arguments=None):
        return wb.document_command(document['id'], operation, arguments or {},
            session_id=document['session_id'], expected_generation=document['generation'],
            command_id='C' + uuid.uuid4().hex)['document']
    def provider(prompt, tools, _budget, _model, **_kwargs):
        calls.append(prompt)
        if len(calls) == 1:
            raise RuntimeError('CONTROLLED prior model failure; preserve the user objection.')
        payload = json.loads(prompt.split('Conversation and request JSON: ', 1)[1])
        context = payload['context']
        assert len(prompt.encode()) < 100_000
        assert payload['source_segments'] == []
        assert context['selected_sources'] == references
        assert len(context['selected_source_catalog']) == run_count * 4
        assert all(row['sha256'] and row['segment_count'] for row in context['selected_source_catalog'])
        assert context['constraints'] == ['Keep the original mesh and material; compare only the imposed displacement.']
        history = context['discussion']['turns']
        assert any('CONTROLLED prior model failure' in json.dumps(row) for row in history)
        assert any(row['text'] == 'The earlier answer ignored contact; retain this objection.' for row in history)
        observations = context['engineering_context_history'][1:]
        assert len(observations) == run_count
        for index, observed in enumerate(observations):
            value = .004 + .001 * index
            model = observed['sources'][0]['model']
            assert model['constraints'][0]['rows'] == [f'Loaded, 1, 1, {value:g}']
            convergence = observed['convergence'][0]
            assert convergence['columns'][1] == 'increment'
            assert convergence['rows'][-1][1] == '20'
            assert convergence['rows'][-1][5] == '1.0000E-03'
            assert any('WARNING: retained contact warning' in line for log in observed['logs']
                       for line in log.get('diagnostic_lines', []))
        current = context['engineering_context']
        assert current['source']['scope'] == {'association': 'POINTS', 'array': 'DISP', 'component': 'D1', 'time': 1.0}
        assert current['result']['time'] == 1.0 and current['result']['units'] is None
        assert current['result']['arrays'][0]['range'] == [0.0, .004 + .001 * (run_count - 1)]
        original = tools['knowledge_source']['call'](**references[0])
        assert 'Loaded, 1, 1, 0.004' in original['segments'][0]['text']
        latest = tools['knowledge_source']['call'](**references[-1])
        assert f'1199, {1199 * run_count / 1_000_000:.6f}' in ''.join(row['text'] for row in latest['segments'])
        marker = {key: original['segments'][0][key] for key in ('document_id', 'revision', 'locator')}
        return json.dumps({'answer': 'INJECTED TEST PROVIDER: observations and original archives are available.',
                           'sources': [marker], 'assumptions': ['Units are not established.']})
    monkeypatch.setattr('caelab.assist.openscience_host.run_openscience', provider)
    try:
        document = wb.desktop.selection_discussion(session_id=wb.session_id, command_id='Cinitial',
            selection={'model_snapshot': {'kind': 'freecad-model', 'materials': [{'name': 'Preserved material'}]},
                       'scope': {'objects': ['Loaded']}})['document']
        draft = deepcopy(document['draft']); draft['participants'] = ['materials']
        draft['composer']['text'] = 'Initial model question.'
        draft['context']['transmission_scope'] = {'allow_question': True}
        draft['context']['constraints'] = ['Keep the original mesh and material; compare only the imposed displacement.']
        document = command(document, 'expert.update', {'draft': draft})
        document = command(document, 'expert.ask')
        finished(wb, {'id': document['runs'][-1]['job_id']})
        document = wb.document_read(document['id'])
        assert document['turns'][-1]['status'] == 'FAILED'
        draft = deepcopy(document['draft']); draft['composer']['text'] = 'The earlier answer ignored contact; retain this objection.'
        document = command(document, 'expert.update', {'draft': draft})
        document = command(document, 'expert.intervene')
        for index in range(run_count):
            folder = tmp_path / str(index); folder.mkdir()
            source = folder / 'Mesh.inp'
            source.write_text('*NODE\n1,0,0,0\n*MATERIAL,NAME=Preserved\n*ELASTIC\n210000,.3\n'
                f'*BOUNDARY\nLoaded, 1, 1, {.004 + .001 * index:g}\n*STEP\n*STATIC\n.05,1\n*END STEP\n')
            source.with_suffix('.sta').write_text('INCREMENT 20 TOTAL TIME 1.0\n')
            source.with_suffix('.cvg').write_text('SUMMARY OF CONVERGENCE INFORMATION\n' + ''.join(
                f'1 {increment} 1 1 0 1.0000E-03 2.0000E-04 0.0000E+00 0.0000E+00\n' for increment in range(1, 21)))
            source.with_suffix('.dat').write_text(''.join(
                f'{node}, {node * (index + 1) / 1_000_000:.6f}\n' for node in range(1200)) + 'WARNING: retained contact warning\n')
            selected = [source.with_suffix(extension) for extension in ('.inp', '.sta', '.cvg', '.dat')]
            for path in selected:
                uploaded = wb.upload(path.name, path.read_bytes())
                archive = wb.assistance().knowledge.ingest(wb.input_path(uploaded['id']), 'materials',
                    {'title': path.name}, workspace_id=wb.workspace_id)
                references.append({key: archive[key] for key in ('document_id', 'revision')})
                archived.append(wb.assistance().knowledge.source(**references[-1], workspace_id=wb.workspace_id))
            document = wb.desktop.selection_discussion(session_id=wb.session_id, command_id='Crun' + str(index),
                discussion_id=document['id'], source_refs=references[-4:],
                selection={'sources': [{'path': str(path)} for path in selected]})['document']
        document = wb.desktop.selection_discussion(session_id=wb.session_id, command_id='Cpost', discussion_id=document['id'],
            selection={'path': str(source), 'scope': {'association': 'POINTS', 'array': 'DISP', 'component': 'D1', 'time': 1.0},
                'result_metadata': {'time': 1.0, 'units': None, 'arrays': [{'name': 'DISP', 'component': 'D1',
                    'range': [0.0, .004 + .001 * (run_count - 1)]}]}})['document']
        draft = deepcopy(document['draft']); draft['composer']['text'] = 'Compare the actual archived runs and selected displacement.'
        draft['context']['transmission_scope'] = {'allow_question': True, 'source_refs': deepcopy(references), 'collections': ['materials']}
        document = command(document, 'expert.update', {'draft': draft})
        original_context = deepcopy(document['draft']['context'])
        assert len(json.dumps(archived, ensure_ascii=False).encode()) + len(json.dumps(original_context).encode()) > 100_000
        document = command(document, 'expert.ask')
        assert finished(wb, {'id': document['runs'][-1]['job_id']})['state'] == 'SUCCEEDED', wb.document_result(
            document['id'], document['runs'][-1]['job_id'])
        document = wb.document_read(document['id'])
        assert document['turns'][-1]['status'] == 'ANSWERED' and len(calls) == 2
        assert document['draft']['context'] == original_context
        assert [canonical_hash(wb.assistance().knowledge.source(**ref, workspace_id=wb.workspace_id))
                for ref in references] == [canonical_hash(row) for row in archived]
        assert wb.config['runtime']['transmission'] == policy
    finally:
        wb.shutdown()


def test_product_modules_do_not_import_test_or_example_code():
    root = Path(__file__).resolve().parents[1]
    violations = []
    for package in ('caelab', 'apps', 'openscience'):
        for path in (root / package).rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
                modules = ([node.module or ''] if isinstance(node, ast.ImportFrom) and node.level == 0 else
                           [item.name for item in node.names] if isinstance(node, ast.Import) else [])
                if any(module.split('.')[0] in {'tests', 'scripts', 'examples'} for module in modules):
                    violations.append(str(path.relative_to(root)) + ':' + str(node.lineno))
    assert not violations, violations
