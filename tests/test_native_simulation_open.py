"""Frozen-to-document routing only; native applications and solvers are doubles."""
from pathlib import Path
from types import SimpleNamespace
import json
import threading
from urllib.error import HTTPError

import pytest

from test_pre_frozen_analysis import native
from apps.desktop_pre.freeze_analysis import freeze_analysis
from caelab.workbench import Workbench
from caelab import simulation_document


def completed_export(wb, native):
    descriptor = {'id': 'Pdesign', 'kind': 'pre', 'generation': 3, 'view_generation': 0,
                  'title': 'Editable routing double', 'capabilities': ['pre.freeze']}
    auth = wb.native_commands.register(host_id='Hpre', session_id='Snative', application='freecad',
        version='TEST_ONLY', execution_mode='headless', documents=[descriptor], registration_nonce='n'*32)
    wb.document_command('Pdesign', 'pre.freeze', {}, session_id='Snative', expected_generation=3,
                        command_id='Cfreeze')
    wb.native_commands.next('Hpre', session_id='Snative', host_token=auth['host_token'])
    path = freeze_analysis(native.analysis, native.solver, wb.desktop.root/'Pdesign')
    wb.native_commands.event('Hpre', session_id='Snative', host_token=auth['host_token'],
        event='finished', command_id='Cfreeze', documents=[descriptor], outcome={'state': 'SUCCEEDED',
        'result': {'status': 'COMPLETED', 'result': {
            'snapshot_relative': path.relative_to(wb.desktop.root).as_posix(), 'label': '연결 해석'},
            'generation': 3, 'view_generation': 0}})


@pytest.mark.parametrize('reopened', [False, True])
def test_discussion_plan_refreshes_edited_native_input_without_running(native, tmp_path, monkeypatch, reopened):
    from caelab.numerical_document import request_draft
    monkeypatch.setattr('caelab.workbench.run', lambda *args, **kwargs: {
        'execution_status': 'REJECTED', 'responses': {}, 'checks': [], 'diagnostics': {'reason': 'TEST_ONLY no physics'}})
    wb = Workbench(tmp_path / 'workspace')
    try:
        completed_export(wb, native)
        submitted = wb.desktop.submit_frozen('Cfreeze')
        import time
        until = time.monotonic() + 5
        while wb.manager.status(submitted['job']['id'])['state'] not in {'SUCCEEDED', 'FAILED'}:
            assert time.monotonic() < until
            time.sleep(.01)
        discussion = wb.desktop.selection_discussion(job_id=submitted['job']['id'],
            session_id=wb.session_id, command_id='Cdiscuss')['document']
        plan = wb.document_open(kind='numerical', draft=request_draft({
            'purpose': 'Revise the original model', 'operation': 'evaluate',
            'inputs': {'backend': 'structure.calculix.frozen', 'settings': {'data_id': submitted['input']['id']}},
            'budget': {'evaluations': 1}}, source={'discussion_id': discussion['id']}))
        host, session, owner_id = 'Hpre', 'Snative', 'Pdesign'
        auth = wb.native_commands._hosts[host]
        if reopened:
            wb.native_commands.event(host, session_id=session, host_token=auth['host_token'], event='closed')
            host, session, owner_id = 'Hreopened', 'Sreopened', 'Pretained'
            descriptor = {'id': owner_id, 'kind': 'pre', 'generation': 3, 'view_generation': 0,
                'title': 'Reopened editable input', 'capabilities': ['pre.freeze'],
                'project': {'opened_source': wb.native_input(submitted['input']['id'])['editable_path']}}
            auth = wb.native_commands.register(host_id=host, session_id=session, application='freecad',
                version='TEST_ONLY', execution_mode='headless', documents=[descriptor], registration_nonce='r'*32)
        arguments = dict(session_id=wb.session_id, expected_generation=plan['generation'], command_id='Crefresh')
        first = wb.desktop.native_plan_input(plan['id'], **arguments)
        assert first == {'status': 'PREPARING', 'executed': False}
        assert wb.desktop.native_plan_input(plan['id'], **arguments) == first
        queued = wb.native_commands.next(host, session_id=session, host_token=auth['host_token'])
        assert queued['command']['arguments']['_public_arguments'] == {'analysis_id': native.analysis.Name, 'solver_id': native.solver.Name}
        path = freeze_analysis(native.analysis, native.solver, wb.desktop.root / owner_id)
        descriptor = {'id': owner_id, 'kind': 'pre', 'generation': 3, 'view_generation': 0,
                      'title': 'Edited native model', 'capabilities': ['pre.freeze']}
        if reopened:
            descriptor['project'] = {'opened_source': wb.native_input(submitted['input']['id'])['editable_path']}
        wb.native_commands.event(host, session_id=session, host_token=auth['host_token'], event='finished',
            command_id='Crefresh', documents=[descriptor], outcome={'state': 'SUCCEEDED', 'result': {'status': 'COMPLETED',
                'result': {'snapshot_relative': path.relative_to(wb.desktop.root).as_posix()}}})
        updated = wb.desktop.native_plan_input(plan['id'], **arguments)
        assert updated['status'] == 'READY' and updated['executed'] is False
        assert updated['settings']['data_id'] != submitted['input']['id']
        assert updated['origin']['document_id'] == owner_id
        assert len(wb.manager.list()) == 1
        assert wb.document_read(plan['id'])['draft']['request']['inputs']['settings'] == {'data_id': submitted['input']['id']}
    finally:
        assert wb.shutdown()['joined']


def allow_routing_profile(monkeypatch):
    # The existing native pre.freeze workflow runs directly. Supply only a
    # document declaration double so these tests isolate handoff identity.
    monkeypatch.setitem(simulation_document.CATALOG, 'structure.calculix.frozen',
                        (None, None, 'TEST_ONLY routing declaration, no native qualification'))
    monkeypatch.setattr(simulation_document, '_adapter', lambda _: SimpleNamespace(
        validate_settings=lambda value: value, describe_ports=lambda value: {}))


def test_same_input_and_unsaved_document_survive_retry_and_service_restart(native, tmp_path, monkeypatch):
    allow_routing_profile(monkeypatch)
    store = tmp_path/'workspace'
    wb = Workbench(store)
    try:
        completed_export(wb, native)
        opened = wb.desktop.open_frozen_simulation('Cfreeze')
        assert opened['status'] == 'DRAFT_OPENED' and opened['executed'] is False
        document = opened['document']
        assert document['draft']['settings'] == {'data_id': opened['input']['id']}
        assert opened['origin']['document_id'] == 'Pdesign'
        edited = {'backend': 'structure.calculix.frozen', 'settings': {'data_id': 'Dedited'}}
        wb.document_command(document['id'], 'simulation.update', {'draft': edited},
            session_id=wb.session_id, expected_generation=document['generation'])
        again = wb.desktop.open_frozen_simulation('Cfreeze', solver='calculix')
        assert again['document']['id'] == document['id']
        assert again['document']['draft'] == edited
        assert again['input']['id'] == opened['input']['id']
        assert len(list((wb.root/'inputs').iterdir())) == 1
        assert len(wb.manager.list()) == 0
    finally:
        assert wb.shutdown()['joined']
    wb = Workbench(store)
    try:
        again = wb.desktop.open_frozen_simulation('Cfreeze')
        assert again['document']['id'] == document['id']
        assert again['document']['draft'] == edited
        assert len(wb.manager.list()) == 0
    finally:
        assert wb.shutdown()['joined']


def test_creation_receipt_failure_recovers_same_working_document(native, tmp_path, monkeypatch):
    allow_routing_profile(monkeypatch)
    wb = Workbench(tmp_path/'workspace')
    from caelab import desktop_links
    original = desktop_links.save_json
    writes = []
    def lose_final(path, value):
        if Path(path).parent.name == 'simulation_documents':
            writes.append(value['state'])
            if value['state'] == 'SUCCEEDED':
                raise OSError('TEST_ONLY creation acknowledgement loss')
        return original(path, value)
    try:
        completed_export(wb, native)
        with monkeypatch.context() as patch:
            patch.setattr(desktop_links, 'save_json', lose_final)
            with pytest.raises(OSError, match='acknowledgement loss'):
                wb.desktop.open_frozen_simulation('Cfreeze')
        prior = wb.simulation_documents.list()
        assert len(prior) == 1 and writes == ['APPLYING', 'SUCCEEDED']
        recovered = wb.desktop.open_frozen_simulation('Cfreeze')
        assert recovered['document']['id'] == prior[0]['id']
        assert len(wb.simulation_documents.list()) == 1 and len(wb.manager.list()) == 0
    finally:
        assert wb.shutdown()['joined']


def test_unsupported_declaration_and_unknown_export_never_start_a_job(native, tmp_path):
    wb = Workbench(tmp_path/'workspace')
    try:
        with pytest.raises(KeyError):
            wb.desktop.open_frozen_simulation('Cmissing')
        completed_export(wb, native)
        with pytest.raises(ValueError, match='계산창 열기'):
            wb.desktop.open_frozen_simulation('Cfreeze')
        assert not wb.simulation_documents.list() and not wb.manager.list()
    finally:
        assert wb.shutdown()['joined']


def test_client_http_and_cli_open_the_same_owner_without_running(native, tmp_path, monkeypatch, capsys):
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.workbench_client import Client
    from caelab.workbench_cli import main
    allow_routing_profile(monkeypatch)
    server = LabHTTPServer(LabService(tmp_path/'workspace'), 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    client = Client('http://127.0.0.1:' + str(server.server_port))
    try:
        completed_export(server.workbench, native)
        opened = client.native_open_simulation('Cfreeze')
        main(['command', 'Cfreeze', '--url', client.url, '--open-simulation'])
        from_cli = json.loads(capsys.readouterr().out)
        assert opened['document']['id'] == from_cli['document']['id']
        assert opened['input']['id'] == from_cli['input']['id']
        assert from_cli['executed'] is False
        with pytest.raises(HTTPError) as bad:
            client.request('/api/workbench/native-open-simulation', {'command_id': 'Cfreeze', 'extra': True})
        assert bad.value.code == 400
        assert len(server.workbench.simulation_documents.list()) == 1
        assert len(server.workbench.manager.list()) == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


@pytest.mark.parametrize('operation', ['simulation.run', 'evaluate'])
def test_simulation_validates_the_public_input_before_resolving_it_once(native, tmp_path, monkeypatch, operation):
    from caelab import research_execution
    allow_routing_profile(monkeypatch)
    def validate(value):
        if set(value) != {'data_id'}:
            raise ValueError('TEST_ONLY public declaration accepts a registered input only')
        return value
    monkeypatch.setattr(simulation_document, '_adapter', lambda _: SimpleNamespace(
        validate_settings=validate, describe_ports=lambda value: {}))
    calls = []
    def evaluate(backend, settings, *, output, **options):
        assert set(settings) == {'data_id', 'snapshot_path'}
        assert Path(settings['snapshot_path']).is_file()
        calls.append((backend, settings.copy()))
        return {'execution_status': 'SUCCEEDED', 'backend': backend, 'settings': settings,
                'responses': {}, 'checks': []}
    monkeypatch.setattr(research_execution.evaluation, 'run', evaluate)
    if operation == 'evaluate':
        # A standalone native Plan uses the shared native run/publication path.
        monkeypatch.setattr('caelab.workbench.run', evaluate)
    wb = Workbench(tmp_path/'workspace')
    try:
        completed_export(wb, native)
        opened = wb.desktop.open_frozen_simulation('Cfreeze')
        draft = opened['document']['draft']
        result = wb._execute(operation, draft, 'Jexplicit')
        if operation == 'evaluate':
            # This input-routing double supplies no Post artifact: preserve that
            # publication failure rather than claiming the result can be opened.
            assert result['execution_status'] == 'FAILED'
            assert result['native_execution_status'] == 'SUCCEEDED'
        else:
            assert result['execution_status'] == 'SUCCEEDED'
        assert calls == [('structure.calculix.frozen', {
            'data_id': opened['input']['id'],
            'snapshot_path': str(wb.input_path(opened['input']['id']))})]
        with pytest.raises(ValueError, match='public declaration' if operation == 'simulation.run' else 'registered data_id'):
            wb._execute(operation, {'backend': draft['backend'],
                'settings': calls[0][1]}, 'Jinvalid')
        assert len(calls) == 1
    finally:
        assert wb.shutdown()['joined']


def test_editable_input_open_uses_the_exact_registered_source_without_running(monkeypatch):
    from apps.research import desktop
    receipt = {'id': 'Dconnector', 'kind': 'frozen_connector',
               'editable_path': 'C:/registered/input/editable.caepre'}
    client = SimpleNamespace(native_input=lambda identifier: dict(receipt))
    calls = []
    monkeypatch.setattr(desktop, '_spawn', lambda selected, arguments: calls.append(arguments))
    desktop.open_native_input(client, 'Dconnector')
    assert calls == [['pre', '--source', receipt['editable_path'], '--source-label', '해석 입력 모델']]
    for bad in ({**receipt, 'id': 'Dother'}, {**receipt, 'kind': 'native_result'},
                {**receipt, 'editable_path': ''}):
        client.native_input = lambda identifier: bad
        with pytest.raises(ValueError, match='입력 모델'):
            desktop.open_native_input(client, 'Dconnector')
    assert len(calls) == 1


def test_native_plan_retains_output_for_save_and_reopen(native, tmp_path, monkeypatch):
    from caelab.evaluation import file_hash
    from caelab.numerical_document import request_draft
    import time

    def execution_double(backend, settings, *, output, **options):
        output = Path(output)
        output.mkdir(parents=True)
        (output / 'calculation.frd').write_bytes(b'TEST_ONLY native output\n')
        (output / 'calculation.cvg').write_bytes(b'TEST_ONLY convergence history\n')
        return {'execution_status': 'SUCCEEDED', 'responses': {'value': {
            'kind': 'scalar', 'value': 2.0, 'unit': 'mm'}}, 'checks': [],
            'artifacts': [{'relative': path.name, 'sha256': file_hash(path)}
                          for path in output.iterdir()]}

    monkeypatch.setattr('caelab.workbench.run', execution_double)
    store = tmp_path / 'workspace'
    wb = Workbench(store)
    try:
        completed_export(wb, native)
        frozen = wb.desktop.submit_frozen('Cfreeze')
        plan = wb.document_open(kind='numerical', draft=request_draft({
            'purpose': 'Retain the complete native calculation', 'operation': 'evaluate',
            'inputs': {'backend': 'structure.calculix.frozen', 'settings': {'data_id': frozen['input']['id']}},
            'budget': {'evaluations': 1}}))
        started = wb.document_command(plan['id'], 'numerical.run', {},
            session_id=plan['session_id'], expected_generation=plan['generation'])
        job = started['job']['id']
        until = time.monotonic() + 10
        while wb.manager.status(job)['state'] not in {'SUCCEEDED', 'FAILED'}:
            assert time.monotonic() < until
            time.sleep(.01)
        assert wb.manager.status(job)['state'] == 'FAILED'  # Double has no Post field.
        result = wb.document_result(plan['id'], job)
        assert result['native_execution_status'] == 'SUCCEEDED'
        current = wb.document_read(plan['id'])
        saved = wb.document_command(plan['id'], 'document.save', {},
            session_id=current['session_id'], expected_generation=current['generation'])['document']
        assert saved['saved_revision']
    finally:
        assert wb.shutdown()['joined']
    wb = Workbench(store)
    try:
        reopened = wb.document_read(plan['id'])
        assert reopened['saved_revision'] == saved['saved_revision']
        result = wb.document_result(plan['id'], job)
        assert result['responses']['value']['value'] == 2.0
        assert {row['path'] for row in result['artifacts']} == {
            'calculation/calculation.frd', 'calculation/calculation.cvg'}
        before = wb.manager.list()
        retained = wb.numerical_documents._folder(plan['id']) / 'revisions' / saved['saved_revision'] / 'results' / job
        assert (retained / 'calculation/calculation.frd').read_bytes() == b'TEST_ONLY native output\n'
        (retained / 'calculation/calculation.frd').write_bytes(b'changed')
        with pytest.raises(ValueError, match='changed or is missing'):
            wb.document_result(plan['id'], job)
        assert wb.manager.list() == before
    finally:
        assert wb.shutdown()['joined']
