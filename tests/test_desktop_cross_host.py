"""Windows research windows retain the WSL owner without executing its Python."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
from apps.research import desktop


@pytest.fixture
def windows_client(monkeypatch):
    monkeypatch.setattr(desktop, 'os', SimpleNamespace(name='nt', environ={}))
    calls = []
    monkeypatch.setattr(desktop.subprocess, 'Popen',
        lambda args, **kw: calls.append((args, kw)) or SimpleNamespace(pid=41))
    context = {'python':'/home/operator/cae/venv/bin/python',
               'repo_root':'/mnt/c/SourceCodes/autonomous-cae-lab',
               'export_root':'/home/operator/cae/exchange'}
    reads = []
    client = SimpleNamespace(url='http://127.0.0.1:18767',
        desktop_context=lambda: deepcopy(context),
        document_read=lambda identifier: {'id':identifier,'kind':'pde','session_id':'Sowner'},
        research_reference=lambda ref: reads.append(deepcopy(ref)))
    monkeypatch.setattr('apps.research.result_return.send_message',lambda message:{'status':'ABSENT'})
    return client, context, calls, reads


def test_wsl_owner_research_launch_uses_client_python_and_exact_selection(windows_client):
    client, original, calls, _ = windows_client
    desktop.launch_tool(client, 'pde', document_id='Qexact')
    args, options = calls[0]
    assert args == [sys.executable, '-m', 'apps.research.desktop', '--service', client.url,
                    'pde', '--document-id', 'Qexact']
    assert Path(options['cwd']) == Path(desktop.__file__).resolve().parents[2]
    assert options['env']['CAELAB_SERVICE_URL'] == client.url
    assert original['python'].startswith('/home/')


def test_wsl_saved_reference_launch_keeps_exact_reference(windows_client):
    import json
    client, _, calls, reads = windows_client
    reference = {'kind':'document', 'document_kind':'pde', 'document_id':'Qexact',
                 'saved_revision':'Rexact', 'input_revision':'Iexact', 'input_sha256':'1'*64}
    desktop.open_saved_reference(client, reference)
    args, options = calls[0]
    assert args[0] == sys.executable and args[2] == 'apps.research.reference_window'
    assert json.loads(args[-1]) == reference and reads == [reference]
    assert options['env']['CAELAB_SERVICE_URL'] == client.url


def test_native_preparation_is_not_silently_moved_to_windows(windows_client):
    client, _, calls, _ = windows_client
    with pytest.raises(ValueError, match='primary Python'):
        desktop.launch_post(client, 'Dretained', job_id='Jexact')
    assert calls == []
