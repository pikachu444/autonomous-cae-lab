"""Research entry-point routing without Qt, native apps, or a live service."""
import builtins
import importlib
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

import pytest

from apps.research import desktop
import caelab.workbench_client as workbench_client


@pytest.mark.parametrize("tool", sorted(desktop.TOOLS))
@pytest.mark.parametrize("selected", [False, True])
def test_research_entrypoint_preserves_service_and_typed_selection(monkeypatch, tool, selected):
    if tool == 'workbench' and selected:
        pytest.skip('Workbench starts from local files, without a service document selection')
    from apps.research import native_data_runtime
    monkeypatch.setattr(native_data_runtime, 'installed_runtime', lambda: None)
    monkeypatch.setattr(desktop.subprocess, 'Popen', lambda *a, **kw: pytest.fail('Compatibility routing must not launch a native app'))
    url = "http://127.0.0.1:8877"
    flag = "--job-id" if tool == "runner" else "--document-id"
    identifier = "Jexact_02" if tool == "runner" else "Dexact_02"
    calls = []
    monkeypatch.setattr(desktop, "Client", lambda service: SimpleNamespace(url=service))
    application = object()
    monkeypatch.setitem(sys.modules, 'PySide6.QtWidgets',
                        SimpleNamespace(QApplication=SimpleNamespace(instance=lambda: application)))
    monkeypatch.setitem(sys.modules, 'apps.research.appearance',
                        SimpleNamespace(apply_appearance=lambda app: calls.append(('appearance', app))))

    def load_window(name):
        calls.append(("module", name))

        def main(arguments):
            calls.append(("arguments", arguments))
            return 23

        return SimpleNamespace(main=main)

    monkeypatch.setattr(importlib, "import_module", load_window)
    selection = [flag, identifier] if selected else []
    assert desktop.main(["--service", url, tool, *selection]) == 23
    assert calls == [
        ("appearance", application),
        ("module", "apps.research." + tool + "_window"),
        ("arguments", ["--service", url, *selection]),
    ]


@pytest.mark.parametrize('flag', ['--job-id', '--document-id'])
def test_workbench_rejects_service_selection_before_opening_window(monkeypatch, flag):
    monkeypatch.setattr(desktop, 'Client', lambda *args: pytest.fail('Invalid selection must not contact service'))
    with pytest.raises(SystemExit):
        desktop.main(['--service', 'http://127.0.0.1:8877', 'workbench', flag, 'Jselection'])


@pytest.mark.parametrize("tool,flag", [("runner", "--job-id"), ("numerical", "--document-id")])
def test_invalid_identifier_never_imports_a_window(monkeypatch, tool, flag):
    monkeypatch.setattr(desktop, "Client", lambda service: SimpleNamespace(url=service))
    monkeypatch.setattr(importlib, "import_module",
                        lambda name: pytest.fail("An invalid selection must not open a window"))
    with pytest.raises(ValueError):
        desktop.main(["--service", "http://127.0.0.1:8877", tool, flag, "../invalid"])


@pytest.mark.parametrize('task', ['processing', 'acquisition'])
def test_native_data_companion_opens_existing_task_on_exact_document(monkeypatch, task):
    url = 'http://127.0.0.1:8877'; calls = []
    monkeypatch.setattr(desktop, 'Client', lambda service: SimpleNamespace(url=service))
    application = object()
    monkeypatch.setitem(sys.modules, 'PySide6.QtWidgets',
        SimpleNamespace(QApplication=SimpleNamespace(instance=lambda: application)))
    monkeypatch.setitem(sys.modules, 'apps.research.appearance', SimpleNamespace(apply_appearance=lambda app: None))
    monkeypatch.setattr(importlib, 'import_module', lambda name:
        SimpleNamespace(main=lambda args: calls.append((name, args)) or 0))
    assert desktop.main(['--service', url, 'data', '--pyside', '--document-id', 'Texact', '--data-task', task]) == 0
    assert calls == [('apps.research.data_window', ['--service', url, '--document-id', 'Texact', '--data-task', task])]


@pytest.mark.parametrize("tool", ["pre", "post"])
@pytest.mark.parametrize("flag,exit_code,error_text", [
    ("--prepare-only", 1, "Desktop launch failed: Preparation context is unavailable"),
    ("--prepare-onl", 2, "unrecognized arguments: --prepare-onl"),
])
def test_prepare_failure_is_stderr_nonzero_without_importing_qt(
        monkeypatch, capsys, tool, flag, exit_code, error_text):
    class UnavailableService:
        def __init__(self, url):
            self.url = url

        def desktop_context(self):
            raise RuntimeError("Preparation context is unavailable")

    monkeypatch.setattr(workbench_client, "Client", UnavailableService)
    original_import = builtins.__import__

    def no_qt_import(name, *args, **kwargs):
        if name == "PySide6" or name.startswith("PySide6."):
            pytest.fail("Headless preparation must not import Qt or create a message box")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_qt_import)
    monkeypatch.setattr(sys, "argv", [
        str(Path(desktop.__file__)),
        "--service", "http://127.0.0.1:8877", tool, flag,
    ])
    # Exercise the real executable block, including its exception handler.
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(desktop.__file__, run_name="__main__")
    assert stopped.value.code == exit_code
    captured = capsys.readouterr()
    assert captured.out == ""
    assert error_text in captured.err
