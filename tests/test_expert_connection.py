"""Local configuration/import checks only. No credentials, model or solver."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import threading
import time

import pytest

from caelab import expert_connection as setup
from caelab.workbench import Workbench
from caelab.storage import save_json


def definitions():
    return [{'id': 'testing', 'label': 'Testing', 'instructions': 'Inspect actual evidence.',
             'collections': ['project-current'], 'tools': ['calculations.plan'],
             'answer_sections': ['conclusion', 'evidence', 'assumptions', 'next_check']}]


def public_installation(tmp_path):
    """An explicit pinned-file test double, never an installed CLI."""
    profile, runtime = tmp_path / 'profile', tmp_path / 'runtime'
    (profile / 'config').mkdir(parents=True)
    binary = runtime / 'node_modules/@synsci/openscience-windows-x64/bin/openscience.exe'
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b'public executable test double; never launch')
    save_json(profile / 'caelab-profile-owner.json', {
        'kind': 'autonomous-cae-lab.chatgpt-auth-profile', 'provider': 'openai-codex',
        'profile_root': str(profile.resolve()), 'runtime_version': setup.VERSION,
        'runtime_pin': {'NativeBinaries': [{'Path': str(binary.resolve()), 'Sha256': setup.digest(binary)}]}})
    save_json(profile / 'config/openscience.json', {
        'permission': {'*': 'deny'}, 'enabled_providers': ['openai-codex'],
        'model': 'openai-codex/test-model'})
    return profile, runtime


def connection_config(original, profile, runtime):
    return setup.proposal(original, enabled=True, profile=str(profile),
        runtime_prefix=str(runtime), model='openai-codex/test-model',
        definitions=definitions(), role_models={'testing': 'openai-codex/test-role'},
        allow_question=True)


@contextmanager
def transport(tmp_path, config_path):
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.workbench_client import Client
    server = LabHTTPServer(LabService(tmp_path / 'store'), 0,
                          workbench_config=setup.read_config(config_path)[0],
                          operator_config_path=config_path)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    try:
        yield Client('http://127.0.0.1:' + str(server.server_port)), server.workbench
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)


def test_pinned_files_and_auth_are_separate_and_native_host_does_not_use_wsl(tmp_path, monkeypatch):
    profile, runtime = public_installation(tmp_path)
    original = Path.read_bytes
    def read(path):
        assert path.name != 'auth.json', 'Setup must not inspect the credential store'
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', read)
    result = setup.installation(profile, runtime)
    assert result['status'] == 'PINNED_FILES_VERIFIED'
    assert result['authentication'] == result['model_entitlement'] == 'UNVERIFIED'
    assert result['inference'] == 'NOT_RUN'
    monkeypatch.setattr(setup.shutil, 'which', lambda name: 'C:/Existing PowerShell/pwsh.exe' if name == 'pwsh.exe' else None)
    command = setup.powershell_command(tmp_path / 'host script.ps1', platform='nt')
    assert command[0] == 'C:/Existing PowerShell/pwsh.exe' and 'wslpath' not in command
    assert command[-1] == str((tmp_path / 'host script.ps1').resolve())
    (runtime / 'node_modules/@synsci/openscience-windows-x64/bin/openscience.exe').unlink()
    assert setup.installation(profile, runtime)['status'] == 'UNAVAILABLE'
    monkeypatch.setattr(setup.shutil, 'which', lambda name: None)
    monkeypatch.setenv('ProgramFiles', str(tmp_path / 'missing'))
    with pytest.raises(ValueError, match='PowerShell 7'):
        setup.powershell_command(tmp_path / 'host.ps1', platform='nt')


def test_local_save_cas_roles_policy_and_cold_service_reopen(tmp_path):
    profile, runtime = public_installation(tmp_path)
    path = tmp_path / 'settings.json'
    original = {'workspace_id': 'local', 'workers': 1, 'cpu_budget': 1,
                'desktop': {'existing_setting': 'retain'}, 'runtime': None}
    sha = setup.save_local(path, None, original)
    proposal = connection_config(original, profile, runtime)
    assert proposal['desktop'] == original['desktop']
    policy = proposal['runtime']['transmission']
    assert policy == {'allow_question': True, 'allow_external_model': True}
    with pytest.raises(ValueError, match='changed'):
        setup.save_local(path, 'wrong hash', proposal)
    assert setup.read_config(path)[0] == original
    wb = Workbench(tmp_path / 'store', configuration=original, operator_config_path=path)
    try:
        opened = wb.document_open(kind='expert')
        current = wb.document_read(opened['id'])
        wb.document_command(opened['id'], 'document.save', {}, session_id=wb.session_id,
                            expected_generation=current['generation'])
        session = wb.session_id
        archive = wb.assistance().knowledge
        new_sha = setup.save_local(path, sha, proposal)
        assert setup.status(wb)['config_sha256'] == sha  # Saved is not applied.
        assert setup.reload_local(wb, new_sha)['status'] == 'APPLIED'
        assert wb.session_id == session and wb.assistance().knowledge is archive
        assert wb.document_read(opened['id'])['draft'] == current['draft']
        assert wb.assistance().experts.runtime.for_expert('testing').model == 'openai-codex/test-role'
        assert wb.manager.list() == []
    finally:
        wb.shutdown()
    wb = Workbench(tmp_path / 'store', configuration=setup.read_config(path)[0], operator_config_path=path)
    try:
        assert wb.document_open(kind='expert', document_id=opened['id'])['draft'] == current['draft']
        assert setup.status(wb)['config_sha256'] == new_sha
        assert wb.assistance().experts.runtime.model == 'openai-codex/test-model'
        assert wb.manager.list() == []
    finally:
        wb.shutdown()


def test_busy_job_and_direct_request_defer_without_cancelling_or_changing_session(tmp_path, monkeypatch):
    path = tmp_path / 'operator.json'
    initial = {'workers': 1, 'cpu_budget': 1}
    setup.save_local(path, None, initial)
    wb = Workbench(tmp_path / 'store', configuration=initial, operator_config_path=path)
    entered, release = threading.Event(), threading.Event()
    def work(*args):
        entered.set()
        assert release.wait(5)
        return {'execution_status': 'SUCCEEDED', 'responses': {}}
    monkeypatch.setattr(wb, '_execute', work)
    # JobManager holds the original bound executor; replace that explicit test seam.
    monkeypatch.setattr(wb.manager, '_execute', work)
    try:
        job = wb.submit('analyze', {})
        assert entered.wait(3)
        proposed = {**initial, 'experts': definitions(), 'runtime': None}
        sha = setup.save_local(path, setup.digest(path), proposed)
        assert setup.reload_local(wb, sha)['status'] == 'DEFERRED'
        assert wb.manager.status(job['id'])['cancel_requested'] is False
        assert wb.config == initial
        release.set()
        deadline = time.monotonic() + 5
        from caelab.jobs import TERMINAL
        while wb.manager.status(job['id'])['state'] not in TERMINAL and time.monotonic() < deadline:
            time.sleep(.01)
        assert wb.manager.status(job['id'])['state'] == 'SUCCEEDED'
        assert setup.reload_local(wb, sha)['status'] == 'APPLIED'
        assert len(wb.manager.list()) == 1
        wb._assistance_active = 1  # Same guarded state used during a direct HTTP assistance call.
        changed = {**proposed, 'experts': []}
        sha2 = setup.save_local(path, sha, changed)
        assert setup.reload_local(wb, sha2)['status'] == 'DEFERRED'
        wb._assistance_active = 0
        wb._assistance_cleanup_pending = True
        assert setup.reload_local(wb, sha2)['status'] == 'CLEANUP_PENDING'
        assert wb.config == proposed
    finally:
        release.set()
        wb.shutdown()


def test_remote_reload_accepts_no_config_paths_and_never_changes_policy_from_request(tmp_path):
    path = tmp_path / 'operator.json'
    with transport(tmp_path, path) as (client, wb):
        initial = client.expert_connection()
        assert initial['configuration'] == 'NOT_CONFIGURED'
        assert initial['operator_config_path'] == str(path.resolve())
        sha = setup.save_local(path, None, {'experts': definitions(), 'runtime': None})
        with pytest.raises(Exception):
            client.request('/api/workbench/expert-connection/reload',
                           {'expected_sha256': sha, 'runtime': {'provider': 'other'}})
        assert wb.config == {}
        assert client.reload_expert_connection(sha)['status'] == 'APPLIED'
        session = wb.session_id
        changed = {**wb.config, 'workers': 3}
        sha2 = setup.save_local(path, sha, changed)
        with pytest.raises(Exception):
            client.reload_expert_connection(sha2)
        assert wb.session_id == session and 'workers' not in wb.config
        assert setup.status(wb)['config_sha256'] == sha
        assert wb.manager.list() == []


def test_selected_role_runtime_does_not_expand_transmission_or_fall_back():
    from caelab.assist.experts import RuntimeConfig
    policy = {'allow_question': False}
    runtime = RuntimeConfig(provider='openscience', model='openai-codex/default',
        credential_env='', transmission=policy,
        expert_models={'testing': {'provider': 'openscience', 'model': 'openai-codex/role'}})
    selected = runtime.for_expert('testing')
    assert selected.model == 'openai-codex/role'
    assert selected.transmission is runtime.transmission
    assert selected.max_model_calls == runtime.max_model_calls
    assert runtime.selected_generator('testing') == 'openscience'
    assert runtime.model == 'openai-codex/default'
    runtime.expert_models['testing']['provider'] = 'other'
    assert runtime.selected_generator('testing') is None
