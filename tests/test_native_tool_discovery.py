"""File discovery and actual Qt choices; native process publication is controlled."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace as NS

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtWidgets import QApplication, QInputDialog, QComboBox

from caelab import native_tools
from apps.research import desktop

HOST_LOCALAPPDATA = os.environ.get('LOCALAPPDATA')


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    # These fixtures create Windows .exe installations on every test host.
    # Keep real file discovery, with explicit platform overrides still honored.
    discover = native_tools.discover
    monkeypatch.setattr(native_tools, 'discover',
        lambda key, **kwargs: discover(key, **{'platform': 'win32', **kwargs}))
    for key in ('CAELAB_FREECAD_EXE','CAELAB_PARAVIEW_EXE','CAE_POST_EXIT_PLUGIN',
                'CAE_POST_PARAVIEW_ROOT','ProgramFiles','ProgramFiles(x86)','LOCALAPPDATA'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('PATH', '')
    monkeypatch.setattr(native_tools, '_windows_app_paths', lambda name: [])
    monkeypatch.setattr(native_tools, 'saved_executable', lambda key: None)
    preference_file = tmp_path / 'preferences.ini'
    monkeypatch.setattr(desktop, '_native_settings', lambda: QSettings(str(preference_file), QSettings.Format.IniFormat))
    monkeypatch.setattr(desktop, '_choose_file', lambda *args: pytest.fail('Unexpected file picker for this installed-file fixture'))


def installed(tmp_path, name='FreeCAD.exe'):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'TEST_ONLY_NOT_AN_EXECUTABLE')
    if os.name != 'nt':
        path.chmod(0o755)
    return path.resolve()


@pytest.mark.parametrize('level', ['override','context','environment','saved'])
def test_explicit_precedence_and_saved_before_automatic(tmp_path, monkeypatch, level):
    paths = [installed(tmp_path/str(n)) for n in range(5)]
    arguments = dict(override=str(paths[0]), context={'freecad_executable':str(paths[1])},
                     environment={'CAELAB_FREECAD_EXE':str(paths[2]),'PATH':str(paths[4].parent)}, saved=str(paths[3]))
    expected = {'override':0,'context':1,'environment':2,'saved':3}[level]
    if expected >= 1: arguments['override'] = None
    if expected >= 2: arguments['context'] = {}
    if expected >= 3: arguments['environment'].pop('CAELAB_FREECAD_EXE')
    row = native_tools.discover('freecad_executable', **arguments)
    assert row['status']=='FOUND' and row['path']==str(paths[expected])


@pytest.mark.parametrize('field', ['override','context','environment'])
def test_invalid_explicit_never_falls_back_to_other_installed_file(tmp_path, monkeypatch, field):
    valid = installed(tmp_path/'available')
    missing = str(tmp_path/'없어진 실행 파일.exe')
    arguments = dict(saved=str(valid), environment={'PATH':str(valid.parent)})
    if field=='override': arguments['override']=missing
    if field=='context': arguments['context']={'freecad_executable':missing}
    if field=='environment': arguments['environment']['CAELAB_FREECAD_EXE']=missing
    row=native_tools.discover('freecad_executable',**arguments)
    assert row['status']=='INVALID' and row['path']==missing and not row['candidates']
    if field=='environment': monkeypatch.setenv('CAELAB_FREECAD_EXE',missing)
    monkeypatch.setattr(desktop,'_native_settings',lambda:pytest.fail('Explicit errors never consult preferences'))
    with pytest.raises(ValueError, match='지정한 실행 파일'):
        desktop._executable(arguments.get('context',{}),'freecad_executable',arguments.get('override'))


def test_windows_bounded_folders_app_paths_path_and_sdk_deduplicate_without_version_guess(tmp_path,monkeypatch):
    pf=tmp_path/'Program Files'; local=tmp_path/'Local'
    one=installed(pf/'FreeCAD 1.0'/'bin')
    launcher=installed(pf/'FreeCAD 1.0')
    two=installed(local/'Programs'/'FreeCAD 1.1'/'bin')
    ignored=installed(tmp_path/'whole-drive'/'FreeCAD 9'/'bin')
    monkeypatch.setattr(native_tools,'_windows_app_paths',lambda name:[str(launcher)])
    env={'ProgramFiles':str(pf),'LOCALAPPDATA':str(local),'PATH':str(one.parent)}
    row=native_tools.discover('freecad_executable',environment=env,platform='win32')
    assert row['status']=='MULTIPLE' and row['path'] is None
    assert {p['path'] for p in row['candidates']}=={str(one),str(two)}
    assert str(ignored) not in str(row)
    assert native_tools.discover('freecad_executable',override=str(launcher),environment=env)['path']==str(launcher)
    sdk=installed(tmp_path/'sdk'/'bin','paraview.exe')
    monkeypatch.setattr(native_tools,'_windows_app_paths',lambda name:[])
    env={'PATH':'','CAE_POST_PARAVIEW_ROOT':str(sdk.parent.parent)}
    assert native_tools.discover('paraview_executable',environment=env,platform='win32')['status']=='NOT_FOUND'
    env['CAE_POST_EXIT_PLUGIN']='explicit-plugin-path'
    assert native_tools.discover('paraview_executable',environment=env,platform='win32')['path']==str(sdk)


def test_non_windows_uses_explicit_or_path_without_windows_registry(tmp_path,monkeypatch):
    path=installed(tmp_path,'freecad')
    monkeypatch.setattr(native_tools,'_windows_app_paths',lambda name:pytest.fail('No Windows registry'))
    monkeypatch.setattr(native_tools.shutil,'which',lambda name,path=None:str(tmp_path/name) if name=='freecad' else None)
    row=native_tools.discover('freecad_executable',environment={'PATH':str(tmp_path)},platform='linux')
    assert row['status']=='FOUND' and row['path']==str(path)


def test_auto_single_no_preference_write_and_stale_saved_manual_cancel_preserved(tmp_path,monkeypatch):
    key='freecad_executable'; settings=desktop._native_settings()
    stale=str(tmp_path/'old FreeCAD.exe'); settings.setValue(key,stale); settings.setValue('paraview_executable','keep-other')
    one=installed(tmp_path/'auto')
    monkeypatch.setenv('PATH',str(one.parent))
    assert desktop._executable({},key)==one
    assert settings.value(key)==stale
    monkeypatch.setenv('PATH','')
    monkeypatch.setattr(desktop,'_choose_file',lambda *args:(_ for _ in ()).throw(ValueError('cancel')))
    with pytest.raises(ValueError,match='cancel'): desktop._executable({},key)
    assert settings.value(key)==stale and settings.value('paraview_executable')=='keep-other'
    chosen=installed(tmp_path/'chosen')
    monkeypatch.setattr(desktop,'_choose_file',lambda *args:chosen)
    assert desktop._executable({},key)==chosen
    assert settings.value(key)==str(chosen) and settings.value('paraview_executable')=='keep-other'


def test_multiple_actual_qt_choice_cancel_and_headless_require_explicit_selection(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    one=installed(tmp_path/'版本一'); two=installed(tmp_path/'한글 설치')
    monkeypatch.setenv('PATH',os.pathsep.join([str(one.parent),str(two.parent)]))
    with pytest.raises(ValueError,match='여러 설치'): desktop._executable({},'freecad_executable',interactive=False)
    for accept in (False,True):
        def answer():
            dialog=app.activeModalWidget()
            assert isinstance(dialog,QInputDialog)
            combo=dialog.findChild(QComboBox)
            assert {combo.itemData(n,Qt.ItemDataRole.ToolTipRole) for n in (0,1)}=={str(one),str(two)}
            combo.setCurrentIndex(1)
            dialog.accept() if accept else dialog.reject()
        QTimer.singleShot(0,answer)
        if accept:
            assert desktop._executable({},'freecad_executable')==two
        else:
            with pytest.raises(ValueError,match='취소'): desktop._executable({},'freecad_executable')
            assert not desktop._native_settings().contains('freecad_executable')
    assert desktop._native_settings().value('freecad_executable')==str(two)


def test_native_launchers_keep_exact_user_model_project_and_same_service(tmp_path,monkeypatch):
    native=tmp_path/'installed'; freecad=installed(native); paraview=installed(native,'paraview.exe')
    monkeypatch.setenv('PATH',str(native))
    context={'python':sys.executable,'repo_root':str(tmp_path),'export_root':str(tmp_path/'exchange')}
    client=NS(url='http://127.0.0.1:18765',desktop_context=lambda:deepcopy(context))
    calls=[]
    monkeypatch.setattr(desktop.subprocess,'Popen',lambda argv,**kw:(calls.append((argv,kw)) or NS(pid=321)))
    monkeypatch.setattr(desktop.subprocess,'run',lambda *a,**kw:pytest.fail('No native preparation in this test'))
    model=tmp_path/'내 모델.FCStd'; model.write_bytes(b'OWN_MODEL_UNCHANGED')
    result=desktop._pre(client,desktop._arguments(['--service',client.url,'pre','--source',str(model)]))
    config=json.loads(Path(result['output'],'config.json').read_text(encoding='utf-8'))
    assert calls[0][0][0]==str(freecad) and config['source']==str(model)
    assert config['service_url']==client.url and config['paraview_executable']==str(paraview)
    state=tmp_path/'내 작업.pvsm'; state.write_bytes(b'ORIGINAL_STATE')
    project=tmp_path/'project.json'; project.write_text(json.dumps({'kind':'external-result','workspace_file':state.name}),encoding='utf-8')
    before=project.read_bytes()
    result=desktop._post(client,desktop._arguments(['--service',client.url,'post','--project',str(project)]))
    assert calls[1][0][0]==str(paraview) and calls[1][1]['env']['CAE_POST_PROJECT']==str(project)
    assert calls[1][1]['env']['CAE_POST_SERVICE_URL']==client.url
    assert project.read_bytes()==before and state.read_bytes()==b'ORIGINAL_STATE' and model.read_bytes()==b'OWN_MODEL_UNCHANGED'


def test_sdk_mismatch_guard_still_rejects_before_launch(tmp_path,monkeypatch):
    stock=installed(tmp_path/'stock','paraview.exe'); sdk=installed(tmp_path/'sdk'/'bin','paraview.exe')
    monkeypatch.setenv('CAE_POST_EXIT_PLUGIN','explicit-plugin-path')
    monkeypatch.setenv('CAE_POST_PARAVIEW_ROOT',str(sdk.parent.parent))
    client=NS(url='http://127.0.0.1:18765',desktop_context=lambda:{'paraview_executable':str(stock)})
    monkeypatch.setattr(desktop.subprocess,'Popen',lambda *a,**kw:pytest.fail('No mismatched launch'))
    with pytest.raises(ValueError,match='종료 보호'):
        desktop._post(client,desktop._arguments(['post','--project',str(tmp_path/'unused.json')]))


@pytest.mark.skipif(sys.platform!='win32',reason='Windows PowerShell report')
def test_powershell_given_or_managed_python_uses_same_finder_and_reports_invalid_explicit(tmp_path):
    powershell=Path(os.environ['SYSTEMROOT'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    script=Path(__file__).parents[1]/'scripts/check-native-tools.ps1'
    fc=installed(tmp_path,'FreeCAD.exe'); pv=installed(tmp_path,'paraview.exe')
    missing=tmp_path/'missing FreeCAD.exe'
    config=tmp_path/'config.json'; config.write_text(json.dumps({'desktop':{'freecad_executable':str(fc),'paraview_executable':str(pv)}}))
    for explicit in (True,False):
        if not explicit and not Path(HOST_LOCALAPPDATA or '', 'AutonomousCAELab/windows-runtime/venv/Scripts/python.exe').is_file():
            continue
        python=" -Python '"+sys.executable.replace("'","''")+"'" if explicit else ''
        code="[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false); & '"+str(script).replace("'","''")+"'"+python+" -ConfigPath '"+str(config).replace("'","''")+"' -FreeCADExe '"+str(missing).replace("'","''")+"' | ConvertTo-Json -Depth 6 -Compress"
        result=subprocess.run([str(powershell),'-NoProfile','-Command',code],capture_output=True,timeout=15,
                              env={**os.environ,'LOCALAPPDATA':HOST_LOCALAPPDATA or ''})
        assert result.returncode==0,result.stderr
        rows=json.loads(result.stdout.decode('utf-8-sig'))
        assert rows[0]['Status']=='경로 복구 필요' and rows[0]['Path']==str(missing)
        assert rows[1]['Path']==str(pv) and rows[1]['PathSource']=='연결 설정'
        assert '같은 경로 탐색' in rows[1]['CheckScope']


def test_pre_native_post_invalid_explicit_does_not_use_saved_or_prompt(tmp_path,monkeypatch):
    from apps.desktop_pre.connection import Connection
    saved=installed(tmp_path/'saved','paraview.exe')
    settings=desktop._native_settings();settings.setValue('paraview_executable',str(saved))
    connection=Connection.__new__(Connection)
    connection.config={'paraview_executable':str(tmp_path/'missing.exe')}
    connection.QtCore=NS(QSettings=lambda *args:settings)
    connection.QtWidgets=NS(QFileDialog=NS(getOpenFileName=lambda *args:pytest.fail('Explicit invalid is not silently replaced')))
    connection.dock=None
    with pytest.raises(ValueError,match='지정한 ParaView'): connection._native_paraview()
    connection.config={}
    monkeypatch.setenv('CAELAB_PARAVIEW_EXE',str(tmp_path/'missing2.exe'))
    with pytest.raises(ValueError,match='지정한 ParaView'): connection._native_paraview()
    monkeypatch.delenv('CAELAB_PARAVIEW_EXE')
    assert connection._native_paraview()==saved
    assert settings.value('paraview_executable')==str(saved)
