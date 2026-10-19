"""Reject a stock ParaView/plugin mismatch before preparing or launching anything."""
from types import SimpleNamespace

import pytest

from apps.research import desktop


@pytest.mark.parametrize('configured,matching,prepare_only,blocked', [
    (True, False, False, True),
    (True, True, False, False),
    (False, False, False, False),
    (True, False, True, False),
])
def test_post_exit_runtime_identity_before_native_work(
        tmp_path, monkeypatch, configured, matching, prepare_only, blocked):
    runtime = tmp_path / '한글 SDK' / 'runtime'
    expected = runtime / 'bin' / 'paraview.exe'
    stock = tmp_path / 'stock' / 'paraview.exe'
    for path in (expected, stock):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'not an executable')
    selected = expected if matching else stock
    project = tmp_path / 'project.json'
    project.write_text('{}', encoding='utf-8')
    if configured:
        monkeypatch.setenv('CAE_POST_EXIT_PLUGIN', str(tmp_path / 'plugin.dll'))
        monkeypatch.setenv('CAE_POST_PARAVIEW_ROOT', str(runtime))
    else:
        monkeypatch.delenv('CAE_POST_EXIT_PLUGIN', raising=False)
        monkeypatch.delenv('CAE_POST_PARAVIEW_ROOT', raising=False)
    calls = []

    def prepared(*args, **kwargs):
        calls.append('preparation')
        raise RuntimeError('test stops before native preparation')

    monkeypatch.setattr(desktop, '_folder', prepared)
    monkeypatch.setattr(desktop.subprocess, 'Popen',
                        lambda *a, **k: pytest.fail('No native process may launch'))
    client = SimpleNamespace(url='http://127.0.0.1:18791',desktop_context=lambda: {
        'paraview_executable': str(selected), 'repo_root': str(tmp_path),
    })
    args = SimpleNamespace(executable=None, prepare_only=prepare_only, project=str(project),
                           input_path=None, input_id=None, job_id=None, output=None)
    if blocked:
        with pytest.raises(ValueError, match='종료 보호에 지정한 ParaView'):
            desktop._post(client, args)
        assert calls == []
    else:
        with pytest.raises(RuntimeError, match='test stops before native preparation'):
            desktop._post(client, args)
        assert calls == ['preparation']
