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
    wb = Workbench(tmp_path/'workspace')
    try:
        completed_export(wb, native)
        opened = wb.desktop.open_frozen_simulation('Cfreeze')
        draft = opened['document']['draft']
        result = wb._execute(operation, draft, 'Jexplicit')
        assert result['execution_status'] == 'SUCCEEDED'
        assert calls == [('structure.calculix.frozen', {
            'data_id': opened['input']['id'],
            'snapshot_path': str(wb.input_path(opened['input']['id']))})]
        with pytest.raises(ValueError, match='public declaration'):
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
