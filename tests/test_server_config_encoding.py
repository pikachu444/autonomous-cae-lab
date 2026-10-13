"""Operator configuration encoding at the real server entry point.

Only server/service lifetime is replaced. Unspecified text reads deliberately
use cp949 to reproduce the reported Windows default; no native app is started.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.lab import server


@pytest.mark.parametrize('bom', [False, True])
def test_operator_config_is_utf8_independent_of_windows_default(tmp_path, monkeypatch, bom):
    configuration = {'workspace_id': '연구실', 'experts': [], 'label': '토론 — 원본 보존'}
    path = tmp_path / 'workbench_config.json'
    content = json.dumps(configuration, ensure_ascii=False).encode('utf-8')
    path.write_bytes((b'\xef\xbb\xbf' if bom else b'') + content)
    read = Path.read_text

    def cp949_default(self, *args, **kwargs):
        if not args and kwargs.get('encoding') is None:
            kwargs['encoding'] = 'cp949'
        return read(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', cp949_default)
    seen = []
    service = SimpleNamespace(shutdown=lambda **kwargs: {'joined': True, 'pending': []})
    monkeypatch.setattr(server, 'LabService', lambda *args, **kwargs: service)
    monkeypatch.setattr(server, 'HTTPJobJournal', lambda *args: None)

    class LifetimeDouble:
        def __init__(self, actual_service, port, *, workbench_config, operator_config_path):
            assert operator_config_path == path
            assert actual_service is service
            seen.append(workbench_config)
            self.service, self.server_port = actual_service, 0
        def serve_forever(self):
            pass
        def server_close(self):
            pass

    monkeypatch.setattr(server, 'LabHTTPServer', LifetimeDouble)
    server.main(['--store', str(tmp_path / 'store'), '--port', '0', '--workbench-config', str(path)])
    assert seen == [configuration]
