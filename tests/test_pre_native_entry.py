"""Default native entry does not opt a document into managed execution."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest


@pytest.fixture
def prep(monkeypatch):
    queued = []
    doc = NS(Name='NativeModel', Label='Native model', Objects=[], FileName='')
    view = NS(viewAxonometric=lambda: None, fitAll=lambda: None)
    main = NS(findChildren=lambda kind: [], showMaximized=lambda: None,
              setWindowTitle=lambda title: None,
              statusBar=lambda: NS(showMessage=lambda text: None))
    app = NS(ActiveDocument=doc, Console=NS(PrintError=lambda text: None),
             ParamGet=lambda path: NS(SetBool=lambda *args: None),
             Version=lambda: ('1', '1', '4'))
    gui = NS(activateWorkbench=lambda name: None, getMainWindow=lambda: main,
             activeDocument=lambda: NS(activeView=lambda: view), listCommands=lambda: [])
    qt = NS(QTimer=NS(singleShot=lambda delay, callback: queued.append(callback)))
    widgets = NS(QDockWidget=object)
    monkeypatch.setitem(sys.modules, 'FreeCAD', app)
    monkeypatch.setitem(sys.modules, 'FreeCADGui', gui)
    monkeypatch.setitem(sys.modules, 'PySide', NS(QtCore=qt, QtGui=NS(), QtWidgets=widgets))
    spec = importlib.util.spec_from_file_location('native_prep_entry',
        Path(__file__).parents[1] / 'apps/desktop_pre/cae_prep.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return NS(module=module, app=app, gui=gui, doc=doc, queued=queued)


def test_service_url_alone_leaves_native_document_independent(prep, monkeypatch, tmp_path):
    from apps.desktop_pre import native_solver_guard, portable_project, connector_menu
    module = prep.module
    calls = []
    monkeypatch.setattr(module, 'add_native_actions', lambda: calls.append('native'))
    monkeypatch.setattr(module, 'add_toolbar', lambda: calls.append('toolbar'))
    monkeypatch.setattr(module, 'enable_managed', lambda *args: calls.append('managed'))
    monkeypatch.setattr(native_solver_guard, 'install', lambda: calls.append('omission-guard'))
    monkeypatch.setattr(portable_project, 'install_file_actions', lambda config, **kw: kw)
    monkeypatch.setattr(connector_menu, 'install', lambda *args, **kw: None)
    config = tmp_path / 'launch.json'
    config.write_text(json.dumps({'output': str(tmp_path), 'service_url': 'http://127.0.0.1:8766'}))
    module.start(config)
    prep.queued.pop(0)()
    assert calls == ['omission-guard', 'native']
    assert module.CONNECTION is None
    assert 'startup_error' not in (tmp_path / 'events.jsonl').read_text()


def test_managed_entry_is_explicit(prep, monkeypatch, tmp_path):
    from apps.desktop_pre import native_solver_guard, portable_project, connector_menu
    module = prep.module
    calls = []
    monkeypatch.setattr(module, 'add_native_actions', lambda: None)
    monkeypatch.setattr(module, 'add_toolbar', lambda: calls.append('toolbar'))
    monkeypatch.setattr(module, 'enable_managed', lambda *args: calls.append('managed'))
    monkeypatch.setattr(native_solver_guard, 'install', lambda: None)
    monkeypatch.setattr(portable_project, 'install_file_actions', lambda config, **kw: kw)
    monkeypatch.setattr(connector_menu, 'install', lambda *args, **kw: None)
    config = tmp_path / 'launch.json'
    config.write_text(json.dumps({'output': str(tmp_path), 'entry_mode': 'managed',
                                  'service_url': 'http://127.0.0.1:8766'}))
    module.start(config)
    prep.queued.pop(0)()
    assert calls == ['toolbar', 'managed']


@pytest.mark.parametrize('mode', ['native', 'managed'])
def test_fcstd_native_open_uses_actual_path_while_managed_retains_copy(prep, monkeypatch, tmp_path, mode):
    from apps.desktop_pre import projects, native_presentation
    module = prep.module
    source = tmp_path / 'user.FCStd'
    source.touch()
    copy = tmp_path / 'managed.FCStd'
    copy.touch()
    opened, copied, presented = [], [], []
    def open_document(path):
        opened.append(path)
        prep.doc.FileName = path
        return prep.doc
    prep.app.openDocument = open_document
    monkeypatch.setattr(projects, 'remember_open', lambda *args: None)
    monkeypatch.setattr(native_presentation, 'restore_fem_viewproviders', lambda doc: presented.append(doc))
    monkeypatch.setattr(module, 'record', lambda *args, **kw: None)
    monkeypatch.setattr(module, 'working_copy', lambda *args: (copied.append(args) or copy, {}))
    module.CONFIG = {'entry_mode': mode}
    assert module.load(source) is prep.doc
    assert opened == [str(source if mode == 'native' else copy)]
    assert bool(copied) == (mode == 'managed')
    assert presented == [prep.doc]


@pytest.mark.parametrize('saved', [False, True])
def test_native_question_preserves_selected_faces_and_live_unsaved_values(prep, monkeypatch, tmp_path, saved):
    from apps.desktop_pre import native_context
    import io
    module = prep.module
    path = tmp_path / '모델.FCStd'
    path.touch()
    prep.doc.FileName = str(path) if saved else ''
    prep.gui.Selection = NS(getSelectionEx=lambda name: [
        NS(Object=NS(Name='UserSolid'), SubElementNames=['Face3', 'Face9'])])
    snapshot = {'model_state': 'current_editing_model', 'conditions': [{'force': '27 N'}]}
    monkeypatch.setattr(native_context, 'model_snapshot', lambda doc, selection: snapshot)
    captured = {}
    class Input(io.BytesIO):
        def close(self):
            captured['payload'] = json.loads(self.getvalue().decode('utf-8'))
            super().close()
    def launch(command, **kwargs):
        captured['command'], captured['kwargs'] = command, kwargs
        return NS(stdin=Input())
    monkeypatch.setattr(module.subprocess, 'Popen', launch)
    module.CONFIG = {'output': str(tmp_path), 'python': 'python', 'service_url': 'http://localhost:8766',
                     'discussion_id': 'original-discussion'}
    module.discuss_selection()
    assert captured['payload']['scope'] == {
        'kind': 'native_objects', 'objects': [{'object': 'UserSolid', 'subelements': ['Face3', 'Face9']}]}
    assert captured['payload']['model_snapshot'] == snapshot
    assert ('path' in captured['payload']) is saved
    assert captured['command'][1:3] == ['-m', 'apps.research.selection_discussion']
    assert captured['command'][captured['command'].index('--discussion') + 1] == 'original-discussion'
    assert '--selection-stdin' in captured['command']
    assert module.CONNECTION is None


def test_prepared_bundle_keeps_origin_and_manifest_for_native_restore(prep, monkeypatch, tmp_path):
    from apps.desktop_pre import projects
    source = tmp_path / 'bundle-entry.FCStd'
    source.touch()
    manifest = {'kind': 'bundle'}
    origin = tmp_path / 'original.caepre'
    prep.module.CONFIG = {'source': str(source), 'source_origin': str(origin), 'source_manifest': manifest}
    prep.app.openDocument = lambda path: prep.doc
    prep.module.record = lambda *args, **kwargs: None
    captured = []
    monkeypatch.setattr(projects, 'remember_open', lambda *args: captured.append(args))
    prep.module.load(source)
    assert captured == [(prep.doc, manifest, str(origin))]


def test_managed_receipt_cannot_be_silently_ignored_in_native_entry(prep, tmp_path):
    config = tmp_path / 'launch.json'
    config.write_text(json.dumps({'output': str(tmp_path), 'input_receipt': {'path': 'input'}}))
    with pytest.raises(ValueError, match='managed'):
        prep.module.start(config)


def test_native_menu_exposes_question_and_explicit_condition_editor(prep, monkeypatch):
    widgets = pytest.importorskip('PySide6.QtWidgets')
    gui = pytest.importorskip('PySide6.QtGui')
    core = pytest.importorskip('PySide6.QtCore')
    app = widgets.QApplication.instance() or widgets.QApplication([])
    class NativeMain(widgets.QMainWindow):
        workbenchActivated = core.Signal(str)
    main = NativeMain()
    calls = []
    monkeypatch.setattr(prep.gui, 'getMainWindow', lambda: main)
    monkeypatch.setattr(prep.module, 'discuss_selection', lambda: calls.append('question'))
    monkeypatch.setattr(prep.module, 'enable_managed', lambda: calls.append('conditions'))
    monkeypatch.setattr(prep.module, 'QtWidgets', widgets)
    monkeypatch.setattr(prep.module, 'QtCore', core)
    menu = prep.module.add_native_actions()
    assert menu.menuAction().data() == 'CAE 연구'
    # FreeCAD MenuManager.retranslate uses this data as the source title.
    menu.setTitle(app.translate('Workbench', menu.menuAction().data()))
    assert menu.title() == 'CAE 연구'
    actions = {action.objectName(): action for action in main.findChildren(gui.QAction)}
    actions['CAELabSelectionDiscussion'].trigger()
    actions['CAELabManagedConditions'].trigger()
    app.processEvents()
    assert calls == ['question', 'conditions']
    assert len(main.menuBar().actions()) == 1
    assert prep.module.add_native_actions() is menu
    main.menuBar().clear()
    main.workbenchActivated.emit('PartWorkbench')
    app.processEvents()
    assert main.menuBar().actions() == [menu.menuAction()]
    main.close()
