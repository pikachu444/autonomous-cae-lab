"""Installed Data routing, exact package checks and preserved prior versions."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from apps.research import desktop, native_data_runtime as runtime


@pytest.mark.skipif(sys.platform != 'win32' or not os.environ.get('CAELAB_NATIVE_DATA_PACKAGE'),
                    reason='Opt-in rendered Windows Data package check')
def test_native_selected_data_opens_discussion_without_preparing_or_inference(tmp_path):
    import psutil
    from PySide6.QtWidgets import QApplication
    from apps.lab.service import LabService
    from caelab.workbench_client import Client
    from caelab.data_document import default_draft
    from test_lab_server import running
    from check_native_data_owner_windows import windows, capture, user, wait, accessible_names, click_button
    app = QApplication.instance() or QApplication([])
    service = LabService(tmp_path / 'store')
    native = None
    window = None
    children = []
    with running(service) as transport:
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        source = client.upload('measurement.csv', b'time,force\n0,4\n1,5\n')
        draft = default_draft()
        draft['data_id'] = source['id']
        draft['mapping']['skip_header'] = 1
        document = client.document_open(kind='data', title='측정 자료', draft=draft)
        package = runtime.verify_package(os.environ['CAELAB_NATIVE_DATA_PACKAGE'])
        try:
            launched = desktop.launch_native_data(client, executable=package['executable'], document_id=document['id'])
            native = psutil.Process(launched['pid'])
            def data_window():
                return next((row for row in windows(native.pid)
                             if any('자료' in name for name in accessible_names(row['hwnd']))), None)
            window = wait(data_window, 30)
            script = '''[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]HWND)
$item=$root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,'자료')))
if (!$item) { $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition) | ForEach-Object { $_.Current.Name }; throw 'Data menu is missing' }
$rect=$item.Current.BoundingRectangle
ConvertTo-Json @{x=$rect.X;y=$rect.Y;width=$rect.Width;height=$rect.Height} -Compress
'''.replace('HWND', str(window['hwnd']))
            bounds = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                    capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15)
            assert bounds.returncode == 0, bounds.stderr
            click_button(window['hwnd'], json.loads(bounds.stdout))
            script = '''[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$desktop=[System.Windows.Automation.AutomationElement]::RootElement
$selected=$desktop.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition) | Where-Object { $_.Current.ProcessId -eq PID -and $_.Current.Name -like '선택 대상으로 논의*' } | Select-Object -First 1
if (!$selected -or !$selected.Current.IsEnabled) { $desktop.FindAll([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,PID))) | ForEach-Object { $_.Current.Name }; throw 'Discussion action is unavailable' }
$invoke=$selected.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
$invoke.Invoke()
'''.replace('HWND', str(window['hwnd'])).replace('PID', str(native.pid))
            invoked = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                     capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20)
            assert invoked.returncode == 0, invoked.stdout + invoked.stderr
            discussions = wait(lambda: transport.server.workbench.discussion_documents.list(), 15)
            def expert_window():
                children.extend(native.children(recursive=True))
                return next((row for child in children for row in windows(child.pid) if row['title'].startswith('Expert')), None)
            expert = wait(expert_window, 30)
            assert len(discussions) == 1
            assert discussions[0]['draft']['context']['selected_model']['input'] == draft
            assert not transport.server.workbench.manager.list()
            assert not discussions[0]['runs']
            capture_root = os.environ.get('CAELAB_GUI_CAPTURE_DIR')
            if capture_root:
                for name, hwnd in [('native-data', window['hwnd']), ('data-discussion', expert['hwnd'])]:
                    capture(hwnd, Path(capture_root) / (name + '.png'))
        finally:
            if native:
                children += native.children(recursive=True) if native.is_running() else []
                for process in {child.pid: child for child in children + [native]}.values():
                    try:
                        for owned in windows(process.pid):
                            user.PostMessageW(owned['hwnd'], 0x0010, 0, 0)
                        process.wait(timeout=5)
                    except psutil.TimeoutExpired:
                        process.terminate()
                        process.wait(timeout=5)
                    except psutil.NoSuchProcess:
                        pass


@pytest.fixture
def package(tmp_path, monkeypatch):
    monkeypatch.delenv('CAELAB_DATA_RUNTIME', raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    root = tmp_path / 'packaged Data'
    files = {'bin/labplot.exe': b'controlled executable', 'bin/platforms/qwindows.dll': b'controlled plugin',
             'bin/qt.conf': b'[Paths]\nPlugins=.\n', 'SOURCE-OBLIGATIONS.txt': b'local package only'}
    rows = []
    for name, data in files.items():
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        rows.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    (root / 'package-manifest.json').write_text(json.dumps({'executable': 'bin/labplot.exe', 'files': rows}), encoding='utf-8')
    return root


def test_install_discovery_and_normal_entry_keep_native_environment_isolated(package, monkeypatch):
    from apps.research import result_return
    installed = runtime.install(package)
    assert runtime.install(package) == installed
    assert runtime.installed_runtime()['root'] == installed
    calls = []
    monkeypatch.setattr(desktop.subprocess, 'Popen', lambda command, **kwargs:
                        calls.append((command, kwargs)) or SimpleNamespace(pid=456))
    client = SimpleNamespace(url='http://127.0.0.1:8766', document_read=lambda identifier: {
        'id': identifier, 'kind': 'data','session_id':'SCurrent'})
    monkeypatch.setattr(result_return,'send_message',lambda message:{'status':'ABSENT'})
    monkeypatch.setattr(desktop, 'Client', lambda service: client)
    monkeypatch.setenv('CAELAB_DONOR_SDK', 'old SDK')
    monkeypatch.setenv('CAELAB_DATA_TRIAL_REPORT', 'unrelated acceptance hook')
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    assert desktop.main(['--service', client.url, 'data']) == 0
    command, options = calls[-1]
    assert command == [str(installed / 'bin/labplot.exe')]
    assert options['env']['QT_PLUGIN_PATH'] == str(installed / 'bin')
    assert not {'CAELAB_DONOR_SDK', 'CAELAB_DATA_TRIAL_REPORT', 'QT_QPA_PLATFORM'} & options['env'].keys()
    assert 'CAELAB_DATA_DOCUMENT_ID' not in options['env']
    assert desktop.main(['--service', client.url, 'data', '--document-id', 'Texact']) == 0
    assert calls[-1][1]['env']['CAELAB_DATA_DOCUMENT_ID'] == 'Texact'


def test_failed_install_or_modified_executable_preserves_previous_pointer(package):
    installed = runtime.install(package)
    pointer = runtime.runtime_root() / 'current.json'
    before = pointer.read_bytes()
    (package / 'bin/platforms/qwindows.dll').write_bytes(b'changed input')
    with pytest.raises(ValueError, match='다릅니다'):
        runtime.install(package)
    assert pointer.read_bytes() == before and runtime.installed_runtime()['root'] == installed
    (installed / 'bin/labplot.exe').write_bytes(b'changed installed executable')
    with pytest.raises(ValueError, match='다릅니다'):
        runtime.installed_runtime()


def test_package_cannot_copy_files_outside_its_root(package):
    path = package / 'package-manifest.json'
    manifest = json.loads(path.read_text())
    manifest['files'][0]['path'] = '../outside.exe'
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='경로'):
        runtime.install(package)
    assert not (runtime.runtime_root() / 'current.json').exists()
