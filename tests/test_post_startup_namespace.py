"""Execute the actual startup script with explicit native import doubles."""
import inspect
import json
from pathlib import Path
import sys
from types import SimpleNamespace, ModuleType

import pytest


@pytest.mark.parametrize('restore_fails', [False, True])
def test_programmable_source_global_log_does_not_replace_startup_logger(tmp_path, monkeypatch, restore_fails):
    monkeypatch.setenv('CAE_POST_PROJECT', str(tmp_path / 'project.json'))
    monkeypatch.setenv('CAE_POST_LAUNCH_DIR', str(tmp_path))
    monkeypatch.setenv('CAE_POST_HOME', str(tmp_path / 'repo' / 'apps' / 'desktop_post'))
    monkeypatch.setenv('CAE_POST_SERVICE_URL', 'http://127.0.0.1:18766')
    monkeypatch.delenv('CAE_POST_MEASUREMENT', raising=False)
    monkeypatch.setattr(sys, 'path', list(sys.path))
    def restore_workspace(**options):
        assert options == {'allow_repair': True}
        def numpy_log(*args, **kwargs):
            raise TypeError('controlled numpy log collision')
        # Models ParaView's shared script global contamination; no native run.
        inspect.currentframe().f_back.f_globals['log'] = numpy_log
        if restore_fails:
            raise RuntimeError('controlled restore failure')
    commands = ModuleType('commands')
    commands.restore_workspace = restore_workspace
    monkeypatch.setitem(sys.modules, 'commands', commands)
    native = ModuleType('paraview')
    native.simple = SimpleNamespace(GetSources=lambda: {('Retained contact', 1): object()},
        GetViews=lambda: [SimpleNamespace(GetXMLName=lambda: 'RenderView')])
    native.servermanager = SimpleNamespace(ActiveConnection='native test double')
    monkeypatch.setitem(sys.modules, 'paraview', native)
    bridge = ModuleType('bridge')
    calls = []
    owner = SimpleNamespace(document_id='Dretained', session_id='Sretained')
    timer = object()
    def start(url, *, log, **native_options):
        assert native_options == {'owner': None, '_portable_binding': None}
        calls.append(url)
        log('controlled_bridge_callback')
        return owner, timer
    bridge.start = start
    monkeypatch.setitem(sys.modules, 'bridge', bridge)
    path = Path(__file__).resolve().parents[1] / 'apps/desktop_post/startup.py'
    namespace = {'__name__': '__main__', '__file__': str(path)}
    if restore_fails:
        with pytest.raises(RuntimeError, match='controlled restore failure'):
            exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), namespace)
    else:
        exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), namespace)
        assert namespace['cae_post_bridge'] == (owner, timer)
        assert calls == ['http://127.0.0.1:18766']
    rows = [json.loads(line) for line in (tmp_path / 'native_startup.jsonl').read_text(encoding='utf-8').splitlines()]
    events = [row['event'] for row in rows]
    assert events[:2] == ['entered', 'module_loaded']
    if restore_fails:
        assert events[-1] == 'failed' and 'controlled restore failure' in rows[-1]['traceback']
        assert calls == []
    else:
        assert events[-3:] == ['loaded', 'controlled_bridge_callback', 'bridge_timer_installed']
