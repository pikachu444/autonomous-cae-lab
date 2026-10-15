"""Native FEM entry/selection/export contracts; no solver or ParaView run."""
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from apps.desktop_pre.connection import Connection


@pytest.fixture
def native(tmp_path, monkeypatch):
    messages, edits = [], []
    doc = NS(Name='Clamp')
    selection = []
    connection = Connection.__new__(Connection)
    connection.App = NS(ActiveDocument=doc)
    connection.Gui = NS(Selection=NS(getSelection=lambda: list(selection)),
        ActiveDocument=NS(setEdit=lambda obj, mode: edits.append((obj, mode))),
        getMainWindow=lambda: NS(findChildren=lambda cls: []))
    connection.owners = {}
    connection.pending = None
    connection.native_requests = {}
    connection.config = {'output':str(tmp_path), 'python':'installed-python', 'service_url':'http://127.0.0.1:8766',
        'repo_root':str(tmp_path/'same-installed-repository')}
    executable=tmp_path/'paraview.exe'; executable.write_bytes(b'controlled existing executable boundary')
    connection.config['paraview_executable']=str(executable)
    saved={}
    connection.QtCore=NS(QSettings=lambda *a: NS(value=lambda key,default: saved.get(key,default),setValue=lambda key,value:saved.update({key:value})))
    connection.QtWidgets=NS(QFileDialog=NS(getOpenFileName=lambda *a: ('','')),QDockWidget=object)
    connection.dock=None
    monkeypatch.delenv('CAELAB_PARAVIEW_EXE',raising=False)
    connection.message = NS(setText=messages.append)
    return NS(connection=connection, doc=doc, selection=selection, messages=messages, edits=edits,executable=executable,saved=saved)


def obj(native, name, kind):
    return NS(Document=native.doc, Name=name, isDerivedFrom=lambda value: value == kind)


def test_native_solver_uses_selected_native_task_without_owner_or_service(native):
    solver = obj(native, 'SolverCcx', 'Fem::FemSolverObjectPython')
    native.selection[:] = [solver]
    native.connection.open_native_solver()
    assert native.edits == [(solver, 0)]
    assert 'FreeCAD 솔버 작업창' in native.messages[-1]
    assert native.connection.owners == {} and native.connection.pending is None


@pytest.mark.parametrize('case', ['none','multiple','wrong_type','foreign_document','busy'])
def test_invalid_native_selection_does_not_open_task(native, case):
    solver = obj(native, 'SolverCcx', 'Fem::FemSolverObjectPython')
    native.selection[:] = [solver]
    if case == 'none': native.selection.clear()
    elif case == 'multiple': native.selection.append(solver)
    elif case == 'wrong_type': solver.isDerivedFrom = lambda value: False
    elif case == 'foreign_document': solver.Document = NS(Name='Other')
    elif case == 'busy': native.connection.pending = {'stage':'command'}
    native.connection.open_native_solver()
    assert not native.edits and native.messages


@pytest.mark.parametrize('kind', ['Fem::FemResultObject','Fem::FemPostObject'])
def test_official_export_exact_selection_fresh_path_same_service_post(native, monkeypatch, kind):
    result = obj(native, 'Result', kind)
    native.selection[:] = [result]
    exports, launches = [], []
    def export(selected, path):
        exports.append((selected,path))
        Path(path).write_bytes(b'controlled VTK boundary')
        # A later selection cannot substitute a different result into this export.
        native.selection.clear()
    monkeypatch.setitem(sys.modules, 'feminout', NS(importVTKResults=NS(export=export)))
    monkeypatch.setattr('apps.desktop_pre.connection.subprocess.Popen',lambda command, **kw: launches.append((command,kw)))
    for name in ('PYTHONHOME','PYTHONPATH','QT_PLUGIN_PATH','QML2_IMPORT_PATH','LD_LIBRARY_PATH'):
        monkeypatch.setenv(name,'inherited-native-runtime')
    native.connection.open_native_result()
    native.selection[:] = [result]
    native.connection.open_native_result()
    assert len(exports) == len(launches) == 2
    assert exports[0][0] == exports[1][0] == [result]
    assert exports[0][1] != exports[1][1]
    for (_,path),(command,options) in zip(exports,launches):
        assert command == ['installed-python','-m','apps.research.desktop','--service',
            native.connection.config['service_url'],'post','--input-path',path,
            '--executable',str(native.executable.resolve())]
        assert options['cwd']==native.connection.config['repo_root']
        assert '--data' not in command and '--job-id' not in command
        assert not set(options['env']).intersection({'PYTHONHOME','PYTHONPATH','QT_PLUGIN_PATH','QML2_IMPORT_PATH','LD_LIBRARY_PATH'})
    assert native.connection.owners == {} and native.connection.pending is None
    assert '같은 연구 작업공간' in native.messages[-1]


def test_export_failure_keeps_original_and_does_not_launch(native,monkeypatch):
    result = obj(native, 'Result', 'Fem::FemResultObject')
    native.selection[:] = [result]
    monkeypatch.setitem(sys.modules,'feminout',NS(importVTKResults=NS(export=lambda *a: None)))
    monkeypatch.setattr('apps.desktop_pre.connection.subprocess.Popen',lambda *a,**kw: pytest.fail('must not launch'))
    native.connection.open_native_result()
    assert '내보내지 못했습니다' in native.messages[-1]
    assert native.selection == [result]


@pytest.mark.parametrize('source',['config','environment','saved','picker'])
def test_installed_paraview_resolution_without_service(native,monkeypatch,source):
    if source!='config':native.connection.config.pop('paraview_executable')
    if source=='environment':monkeypatch.setenv('CAELAB_PARAVIEW_EXE',str(native.executable))
    if source=='saved':native.saved['paraview_executable']=str(native.executable)
    if source=='picker':native.connection.QtWidgets.QFileDialog.getOpenFileName=lambda *a:(str(native.executable),'')
    assert native.connection._native_paraview()==native.executable.resolve()
    if source=='picker':assert native.saved['paraview_executable']==str(native.executable.resolve())


def test_cancel_or_changed_selection_before_export_preserves_result(native,monkeypatch):
    result=obj(native,'Result','Fem::FemResultObject');native.selection[:]=[result]
    native.connection.config.pop('paraview_executable')
    native.connection.open_native_result()
    assert '취소했습니다' in native.messages[-1]
    assert not list(Path(native.connection.config['output']).glob('native-results/*'))
    def choose(*a):
        native.selection.clear()
        return str(native.executable),''
    native.connection.QtWidgets.QFileDialog.getOpenFileName=choose
    native.connection.open_native_result()
    assert '선택하세요' in native.messages[-1]
    assert not list(Path(native.connection.config['output']).glob('native-results/*'))


def test_integrated_launch_failure_retains_exact_export_and_original(native,monkeypatch):
    result=obj(native,'Result','Fem::FemResultObject');native.selection[:]=[result]
    exported=[]
    def export(selected,path):
        assert selected==[result]
        Path(path).write_bytes(b'controlled retained VTU boundary');exported.append(Path(path))
    def fail(*a,**kw):raise OSError('controlled process creation failure')
    monkeypatch.setitem(sys.modules,'feminout',NS(importVTKResults=NS(export=export)))
    monkeypatch.setattr('apps.desktop_pre.connection.subprocess.Popen',fail)
    native.connection.open_native_result()
    assert len(exported)==1 and exported[0].read_bytes()==b'controlled retained VTU boundary'
    assert native.selection==[result]
    assert 'controlled process creation failure' in native.messages[-1]
    assert str(exported[0]) in native.messages[-1]
    assert (exported[0].parent/'launch.stdout.log').is_file()
    assert (exported[0].parent/'launch.stderr.log').is_file()
