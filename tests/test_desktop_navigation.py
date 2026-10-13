"""Portable desktop routing doubles; no native application or solver is started."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace as NS

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest

from apps.research import desktop
from test_desktop_post_external import native as post_native


@pytest.fixture
def client(tmp_path):
    class ClientDouble:
        url = 'http://127.0.0.1:8766'
        def __init__(self):
            self.navigation = {'origin_document':None, 'retained_design_input_id':None, 'post_input':None}
            self.commands = []
            self.context = {'python':sys.executable, 'repo_root':str(tmp_path), 'export_root':str(tmp_path / 'exchange')}
            self.state = 'SUCCEEDED'
        def desktop_context(self): return self.context
        def job_navigation(self, job_id): return self.navigation
        def document_command(self, identifier, operation, arguments, **keywords):
            self.commands.append((identifier, operation, arguments, keywords))
            return {'command_id':'Cactivate', 'state':self.state}
        def native_input(self, identifier):
            return {'id':identifier, 'kind':'frozen_fem', 'editable_path':str(tmp_path / 'retained.FCStd')}
        def command_status(self, identifier): raise AssertionError('No retry expected in terminal receipt tests')
    return ClientDouble()


@pytest.fixture
def processes(monkeypatch):
    calls = []
    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return NS(pid=321)
    monkeypatch.setattr(desktop.subprocess, 'Popen', popen)
    # Any unintended native preparation fails unless the focused test opts into
    # its own explicit portable collaborator double.
    monkeypatch.setattr(desktop.subprocess, 'run', lambda *a, **k: pytest.fail('Native preparation must not execute'))
    return calls


def test_launch_post_spawns_primary_helper_with_exact_input_job_and_service(client, processes):
    result = desktop.launch_post(client, 'Dresult', job_id='Jrun')
    command, settings = processes[0]
    assert command == [sys.executable, '-m', 'apps.research.desktop', '--service', client.url,
                       'post', '--input-id', 'Dresult', '--job-id', 'Jrun']
    assert settings['cwd'] == Path(client.context['repo_root'])
    assert settings['env']['CAELAB_SERVICE_URL'] == client.url
    assert result['status'] == 'LAUNCH_REQUESTED'


def test_live_pre_activation_uses_current_exact_owner_and_no_file_or_launch(client, processes):
    client.navigation['origin_document'] = {'id':'Pdesign', 'kind':'pre', 'connected':True,
                                           'session_id':'Scurrent', 'generation':7}
    client.navigation['frozen_origin'] = {'session_id':'Sold', 'generation':2}
    client.navigation['retained_design_input_id'] = 'Dfrozen'
    result = desktop.open_origin(client, 'Jrun')
    assert result['status'] == 'ACTIVATED'
    assert client.commands[0][0:3] == ('Pdesign', 'document.activate', {})
    assert client.commands[0][3]['session_id'] == 'Scurrent'
    assert client.commands[0][3]['expected_generation'] == 7
    assert processes == []


@pytest.mark.parametrize('state', ['FAILED', 'CANCELLED', 'INTERRUPTED', 'REJECTED'])
def test_failed_or_ambiguous_live_activation_never_falls_back_to_copy(client, processes, state):
    client.navigation.update(origin_document={'id':'Pdesign', 'kind':'pre', 'connected':True, 'session_id':'Slive', 'generation':4},
                             retained_design_input_id='Dfrozen')
    client.state = state
    with pytest.raises(RuntimeError): desktop.open_origin(client, 'Jrun')
    assert len(client.commands) == 1 and processes == []


def test_closed_pre_opens_explicit_retained_copy_in_new_native_session(client, processes):
    client.navigation.update(origin_document={'id':'Pdesign','kind':'pre','connected':False}, retained_design_input_id='Dfrozen')
    desktop.open_origin(client, 'Jrun')
    command = processes[0][0]
    assert command[-5:] == ['pre', '--source', str(Path(client.context['repo_root']) / 'retained.FCStd'),
                           '--source-label', 'Retained design copy — Jrun']
    assert client.commands == []


@pytest.mark.parametrize('kind', ['material', 'data', 'numerical'])
def test_origin_routes_to_exact_research_document(client, processes, kind):
    client.navigation['origin_document'] = {'id':'Dexact', 'kind':kind}
    desktop.open_origin(client, 'Jrun')
    assert processes[0][0][-3:] == [kind, '--document-id', 'Dexact']


def test_pre_config_has_service_export_primary_python_and_no_fixture_defaults(client, processes, tmp_path):
    executable = tmp_path / 'FreeCAD.exe'; executable.write_bytes(b'TEST_ONLY')
    client.context['freecad_executable'] = str(executable)
    args = desktop._arguments(['--service', client.url, 'pre'])
    result = desktop._pre(client, args)
    config = json.loads((Path(result['output']) / 'config.json').read_text(encoding='utf-8'))
    assert config['service_url'] == client.url
    assert config['export_root'] == client.context['export_root']
    assert config['python'] == sys.executable
    assert 'source' not in config and 'assembly' not in config and 'gmsh' not in config
    assert processes[0][0][0] == str(executable)
    assert '-u' in processes[0][0] and '-s' in processes[0][0]


def test_pre_recorded_source_is_handed_to_copying_loader_not_opened_in_place(client, processes, tmp_path):
    executable = tmp_path / 'FreeCAD.exe'; executable.write_bytes(b'TEST_ONLY')
    retained = tmp_path / 'source.FCStd'; retained.write_bytes(b'original')
    client.context['freecad_executable'] = str(executable)
    args = desktop._arguments(['--service', client.url, 'pre', '--source', str(retained), '--source-label', 'Retained design copy — Jrun'])
    result = desktop._pre(client, args)
    config = json.loads((Path(result['output']) / 'config.json').read_text(encoding='utf-8'))
    assert config['source'] == str(retained)
    assert config['source_label'] == 'Retained design copy — Jrun'
    command = processes[0][0]
    assert str(retained) not in command  # Only the cae_prep startup macro is launched.
    assert 'cae_prep.start' in Path(command[-1]).read_text()
    assert retained.read_bytes() == b'original'


def post_install(client, tmp_path):
    executable = tmp_path / 'paraview.exe'; executable.write_bytes(b'TEST_ONLY')
    (tmp_path / 'pvpython.exe').write_bytes(b'TEST_ONLY')
    client.context['paraview_executable'] = str(executable)
    home = tmp_path / 'apps/desktop_post'; home.mkdir(parents=True)
    return executable


def test_post_preparation_is_exact_registered_external_reader_and_child_environment(client, processes, tmp_path, monkeypatch):
    executable = post_install(client, tmp_path)
    client.navigation['post_input'] = {'id':'Dfield'}
    prepared = []
    def prepare(command, **kwargs):
        prepared.append(command)
        folder = Path(command[3]); folder.mkdir()
        (folder / 'state.pvsm').write_text('TEST_ONLY native state')
        (folder / 'project.json').write_text(json.dumps({'kind':'external-result','workspace_file':'state.pvsm',
            'sources':{'result':{'input_id':'Dfield'}}}))
        return NS(returncode=0)
    monkeypatch.setattr(desktop.subprocess, 'run', prepare)
    monkeypatch.setenv('CAELAB_ORIGIN_JOB_ID', 'Jwrong_inherited')
    args = desktop._arguments(['--service',client.url,'post','--input-id','Dfield','--job-id','Jrun'])
    result = desktop._post(client, args)
    assert prepared[0][0] == str(tmp_path / 'pvpython.exe')
    assert prepared[0][2].endswith('external.py')
    assert prepared[0][-4:] == ['--registered-input','Dfield','--service-url',client.url]
    command, settings = processes[0]
    assert command[0] == str(executable)
    assert settings['env']['CAELAB_ORIGIN_JOB_ID'] == 'Jrun'
    assert settings['env']['CAE_POST_SERVICE_URL'] == client.url
    assert settings['env']['CAELAB_DESKTOP_PYTHON'] == sys.executable
    assert settings['env']['PV_MACRO_PATH'].endswith('macros_external')
    assert (Path(result['project']).parent.parent / 'prepare.stderr.log').is_file()
    assert os.environ['CAELAB_ORIGIN_JOB_ID'] == 'Jwrong_inherited'  # Parent is untouched.


def test_post_existing_project_requires_no_solver_or_native_preparation(client, processes, tmp_path, monkeypatch):
    post_install(client, tmp_path)
    monkeypatch.setenv('CAELAB_ORIGIN_JOB_ID','Junrelated')
    state = tmp_path / 'existing.pvsm'; state.write_text('TEST_ONLY')
    project = tmp_path / 'project.json'; project.write_text(json.dumps({'kind':'external-result','workspace_file':state.name}))
    args = desktop._arguments(['--service',client.url,'post','--project',str(project)])
    desktop._post(client, args)
    assert 'CAELAB_ORIGIN_JOB_ID' not in processes[0][1]['env']


def test_prepare_only_keeps_exact_candidate_stage_origin_for_later_open(client, processes, tmp_path, monkeypatch):
    post_install(client, tmp_path)
    source = {'document_id': 'Nplan', 'candidate_id': 'Cchosen', 'evaluation_index': 1, 'attempt_id': 'Astress'}
    requests = []
    def candidate(document_id, job_id, candidate_id, **kwargs):
        requests.append((document_id, job_id, candidate_id, kwargs))
        return {'post_input': {'id': 'Dfield', 'sha256': 'retained-field'}}
    client.numerical_evaluation_result = candidate
    def prepare(command, **kwargs):
        folder = Path(command[3]); folder.mkdir()
        (folder / 'state.pvsm').write_text('TEST_ONLY native state', encoding='utf-8')
        (folder / 'project.json').write_text(json.dumps({'kind': 'external-result', 'workspace_file': 'state.pvsm',
            'sources': {'result': {'input_id': 'Dfield'}}}), encoding='utf-8')
        return NS(returncode=0)
    monkeypatch.setattr(desktop.subprocess, 'run', prepare)
    args = desktop._arguments(['--service', client.url, 'post', '--input-id', 'Dfield', '--job-id', 'Jrun',
        '--research-source', json.dumps(source), '--prepare-only'])
    result = desktop._post(client, args)
    assert result['status'] == 'PREPARED' and not processes
    project = Path(result['project'])
    retained = project.read_bytes()
    document = json.loads(retained)
    assert document['origin_job_id'] == 'Jrun' and document['origin_research_source'] == source
    assert document['desktop_python'] == sys.executable and document['service_url'] == client.url
    assert all(row[:3] == ('Nplan', 'Jrun', 'Cchosen') and row[3]['attempt_id'] == 'Astress'
               and row[3]['evaluation_index'] == 1 for row in requests)
    monkeypatch.setattr(desktop.subprocess, 'run', lambda *a, **k: pytest.fail('Opening must not prepare again'))
    desktop._post(client, desktop._arguments(['--service', client.url, 'post', '--project', str(project)]))
    assert project.read_bytes() == retained
    assert processes[-1][1]['env']['CAELAB_ORIGIN_JOB_ID'] == 'Jrun'


def test_post_wrong_job_input_refused_before_any_native_preparation(client, processes, tmp_path):
    post_install(client, tmp_path)
    client.navigation['post_input'] = {'id':'Dactual'}
    args = desktop._arguments(['--service',client.url,'post','--input-id','Dwrong','--job-id','Jrun'])
    with pytest.raises(ValueError): desktop._post(client, args)
    assert processes == []


def test_native_launcher_scripts_use_private_bootstrap_without_historical_sources():
    root = Path(__file__).resolve().parents[1]
    for name in ('start_cae_pre.ps1','start_cae_post.ps1','start_cae_research.ps1'):
        text = (root / 'scripts' / name).read_text()
        assert 'start-windows.ps1' in text and '-ResearchUI' in text
        assert 'apps.research.desktop' in text
        assert 'prepost-session-20261008' not in text
        assert 'requires PowerShell 7.4' not in text and '-Environment' not in text
    assert "'data','numerical'" in (root / 'scripts/start_cae_research.ps1').read_text()


@pytest.fixture
def qt_app():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.mark.parametrize('kind', ['material','pre','data','numerical'])
def test_runner_preserves_material_callback_only_for_material(qt_app, client, monkeypatch, kind):
    from apps.research.runner_window import RunnerWindow
    monkeypatch.setattr(RunnerWindow, 'refresh', lambda self: None)
    window = RunnerWindow(client, poll_interval=0, on_open_origin=lambda job: callback.append(job))
    callback, routed = [], []
    window.selected_job_id = 'Jrun'
    window.jobs['Jrun'] = {'id':'Jrun','result_refs':['result.json']}
    client.navigation['origin_document'] = {'id':'Dsource','kind':kind}
    def immediate(key, function, accepted, **kwargs):
        accepted(function(), 1); return True
    monkeypatch.setattr(window, '_request', immediate)
    monkeypatch.setattr(desktop, 'open_origin', lambda cli, job: routed.append(job) or {'status':'ACTIVATED'})
    window.open_selected_origin()
    assert callback == (['Jrun'] if kind == 'material' else [])
    assert routed == ([] if kind == 'material' else ['Jrun'])
    window.close()


def test_runner_post_action_passes_exact_input_and_origin_job(qt_app, client, monkeypatch):
    from apps.research.runner_window import RunnerWindow
    monkeypatch.setattr(RunnerWindow, 'refresh', lambda self: None)
    window = RunnerWindow(client, poll_interval=0)
    window.selected_job_id = 'Jrun'; window.jobs['Jrun'] = {'id':'Jrun','result_refs':['result.json']}
    client.navigation['post_input'] = {'id':'Dfield'}
    calls = []
    monkeypatch.setattr(window, '_request', lambda key, fn, received, **kw: received(fn(),1))
    monkeypatch.setattr(desktop, 'launch_post', lambda cli, input_id, job_id: calls.append((input_id,job_id)) or {'status':'LAUNCH_REQUESTED'})
    window.open_selected_post()
    assert calls == [('Dfield','Jrun')]
    window.close()



def test_post_origin_and_primary_helper_metadata_survive_native_save_and_reopen(client, processes, tmp_path, monkeypatch, post_native):
    # Use the existing ParaView API double while executing the real native
    # project save function; no ParaView executable or reader is launched.
    _, _, external = post_native
    post_install(client, tmp_path)
    source = tmp_path / 'retained.vtu'; source.write_bytes(b'TEST_ONLY reader data')
    client.navigation['post_input'] = {'id':'Dfield'}
    def prepare(command, **kwargs):
        external.open_result(source, command[3], input_id='Dfield', source_pins=external.pins([source]))
        return NS(returncode=0)
    monkeypatch.setattr(desktop.subprocess, 'run', prepare)
    args = desktop._arguments(['--service',client.url,'post','--input-id','Dfield','--job-id','Jrun'])
    launched = desktop._post(client, args)
    project = Path(launched['project'])
    document = json.loads(project.read_text())
    saved = external.save_project(project, document)
    saved_document = json.loads(saved.read_text())
    assert saved_document['origin_job_id'] == 'Jrun'
    assert saved_document['desktop_python'] == sys.executable
    assert saved_document['repo_root'] == client.context['repo_root']
    assert saved_document['service_url'] == client.url
    original_saved_bytes=saved.read_bytes()
    reopened = desktop._arguments(['--service',client.url,'post','--project',str(saved)])
    desktop._post(client, reopened)
    assert saved.read_bytes()==original_saved_bytes
    assert processes[-1][1]['cwd'] != saved.parent
    assert processes[-1][1]['env']['CAELAB_ORIGIN_JOB_ID'] == 'Jrun'
    assert processes[-1][1]['env']['CAELAB_DESKTOP_PYTHON'] == sys.executable



def test_post_document_activation_requires_explicit_native_owner_capability(client, processes):
    client.document_read = lambda identifier: {'id':identifier, 'kind':'post', 'connected':True,
        'session_id':'Spost', 'generation':1, 'capabilities':['post.save_project']}
    with pytest.raises(ValueError, match='does not support live activation'):
        desktop.launch_tool(client, 'post', document_id='Ppost')
    assert client.commands == [] and processes == []



@pytest.mark.parametrize('state', ['SUCCEEDED', 'FAILED', 'CANCELLED'])
def test_contact_attempt_closed_origin_uses_exact_retained_design(client, processes, state, monkeypatch):
    from caelab.desktop_links import DesktopLinks

    def disconnected(identifier):
        assert identifier == 'Pcontact'
        raise KeyError(identifier)

    links = DesktopLinks.__new__(DesktopLinks)
    links.workbench = NS(native_commands=NS(read=disconnected))
    job = {'id': 'Jcontact', 'state': state, 'result_refs': [],
           'arguments': {'backend': 'structure.calculix.contact',
                         'settings': {'data_id': 'Dcontact'},
                         'origin': {'kind': 'pre', 'document_id': 'Pcontact',
                                    'session_id': 'Sclosed', 'generation': 9}}}
    links.job_record = lambda identifier: job if identifier == job['id'] else pytest.fail('Wrong job')
    client.job_navigation = links.navigation
    path = str(Path(client.context['repo_root']) / '한글 retained contact.FCStd')
    reads = []
    def retained(identifier):
        reads.append(identifier)
        return {'id': identifier, 'kind': 'frozen_contact', 'editable_path': path}
    client.native_input = retained
    navigation = links.navigation('Jcontact')
    assert navigation['origin_document'] is None
    assert navigation['retained_design_input_id'] == 'Dcontact'
    assert navigation['frozen_origin'] == job['arguments']['origin']
    assert navigation['post_input'] is None
    result = desktop.open_origin(client, 'Jcontact')
    assert result['status'] == 'LAUNCH_REQUESTED'
    assert reads == ['Dcontact']
    assert processes[0][0][-5:] == [
        'pre', '--source', path, '--source-label', 'Retained design copy — Jcontact']
    assert not client.commands
    assert job['state'] == state


def test_closed_origin_still_rejects_unrelated_native_receipt_kind(client, processes):
    client.navigation.update(origin_document=None, retained_design_input_id='Dresult')
    client.native_input = lambda identifier: {
        'id': identifier, 'kind': 'external_result', 'editable_path': 'wrong.FCStd'}
    with pytest.raises(ValueError, match='editable FEM copy'):
        desktop.open_origin(client, 'Jcontact')
    assert not processes and not client.commands
