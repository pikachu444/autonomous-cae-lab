"""CAE preparation workspace, hosted by the unmodified FreeCAD native application.

This is an integration prototype, not a replacement CAD kernel or release gate.
Run only inside FreeCAD; the launcher gives it a private profile and output folder.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui

# FreeCAD loads this module from a macro, with its own Python installation.
# Only the thin stdlib bridge/client is imported from the repository here.
repository = str(Path(__file__).resolve().parents[2])
if repository not in sys.path:
    sys.path.insert(0, repository)
try:
    from PySide import QtWidgets
except ImportError:
    QtWidgets = QtGui

CONFIG = {}
KEEP = []
ISOLATION = {}
CONNECTION = None


def record(event, **values):
    dest = Path(CONFIG['output']) / 'events.jsonl'
    with dest.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(dict(event=event, time=time.time(), **values), ensure_ascii=False) + '\n')


def guarded(fn):
    def invoke(*unused):
        try:
            fn()
        except Exception as exc:
            record('error', action=fn.__name__, error=str(exc), traceback=traceback.format_exc())
            App.Console.PrintError(traceback.format_exc())
            QtWidgets.QMessageBox.warning(Gui.getMainWindow(), 'CAE Prep', str(exc))
    return invoke


def working_copy(path, approved_root=None):
    source = Path(path).resolve(strict=True)
    if source.suffix.lower() in {'.fcstd', '.caepre'}:
        from caelab import native_cad
        folder = Path(CONFIG['output']) / 'imports' / str(time.time_ns())
        manifest, copy = native_cad.working_copy(source, folder, approved_root=approved_root)
        return copy, manifest
    with source.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    folder = Path(CONFIG['output']) / 'imports' / (str(time.time_ns()) + '_' + digest[:10])
    folder.mkdir(parents=True)
    copy = folder / source.name
    shutil.copy2(source, copy)
    with copy.open('rb') as stream:
        copied_digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if copied_digest != digest:
        raise RuntimeError('복사 중 입력 파일이 변경되었습니다. 새 작업으로 다시 여세요.')
    record('source_copy', source=str(source), copy=str(copy), sha256=digest)
    return copy, {}


def load(path, approved_root=None):
    started = time.perf_counter()
    source = Path(path).resolve(strict=True)
    if CONFIG.get('entry_mode', 'native') == 'native' and source.suffix.lower() == '.fcstd':
        copy, manifest = source, {}
    else:
        copy, manifest = working_copy(path, approved_root)
    original = path
    if (CONFIG.get('source_origin') and CONFIG.get('source')
            and source == Path(CONFIG['source']).resolve()):
        original = CONFIG['source_origin']
        manifest = CONFIG.get('source_manifest') or manifest
    if copy.suffix.lower() == '.fcstd':
        doc = App.openDocument(str(copy))
        from apps.desktop_pre.native_presentation import restore_fem_viewproviders
        restore_fem_viewproviders(doc)
    else:
        import ImportGui
        doc = App.newDocument('ImportedModel')
        ImportGui.insert(str(copy), doc.Name)
        doc.recompute()
        doc.saveAs(str(copy.with_suffix('.FCStd')))
    doc.UndoMode = 1
    from apps.desktop_pre.projects import remember_open
    remember_open(doc, manifest, original)
    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    record('open', document=doc.Name, objects=len(doc.Objects), seconds=time.perf_counter()-started,
           working_file=doc.FileName)
    update_caption()
    return doc


def open_model():
    path, _ = QtWidgets.QFileDialog.getOpenFileName(Gui.getMainWindow(), '모델 열기', '',
                                                  'CAD/project (*.caepre *.FCStd *.step *.stp *.iges *.igs);;All files (*)')
    if path:
        try:
            load(path)
        except ValueError as error:
            if 'outside the approved CAD root' not in str(error):
                raise
            folder = QtWidgets.QFileDialog.getExistingDirectory(Gui.getMainWindow(),
                '선택한 CAD와 외부 Link 문서를 포함하는 폴더', str(Path(path).parent))
            if folder: load(path, approved_root=folder)


def save_as():
    if CONNECTION is not None:
        CONNECTION.guards.save(as_new=True)
        return
    doc = App.ActiveDocument
    if not doc:
        return
    path, _ = QtWidgets.QFileDialog.getSaveFileName(Gui.getMainWindow(), '편집 가능한 모델 저장',
               str(Path(CONFIG['output']) / (doc.Name + '.FCStd')), 'FreeCAD document (*.FCStd)')
    if path:
        if not path.lower().endswith('.fcstd'):
            path += '.FCStd'
        doc.recompute()
        doc.saveAs(path)
        record('save', path=path, objects=len(doc.Objects))
        update_caption()


def update_caption():
    name = App.ActiveDocument.Label if App.ActiveDocument else '새 작업'
    Gui.getMainWindow().setWindowTitle('CAE Lab · 전처리 — ' + name + ' | FreeCAD')


def switch(name):
    if CONNECTION is not None and App.ActiveDocument is not None:
        CONNECTION.active_owner().before_design_action('workbench switch')
    if Gui.activeDocument() and Gui.activeDocument().getInEdit():
        raise ValueError('현재 편집을 완료하거나 취소한 후 작업대를 전환하세요.')
    Gui.activateWorkbench(name)
    update_caption()


def analysis():
    import ObjectsFem, FemGui
    doc = App.ActiveDocument
    if not doc:
        raise ValueError('먼저 모델을 여세요.')
    active = FemGui.getActiveAnalysis()
    if active and active.Document == doc:
        return active
    selected = [obj for obj in Gui.Selection.getSelection() if obj.TypeId == 'Fem::FemAnalysis']
    found = [obj for obj in doc.Objects if obj.TypeId == 'Fem::FemAnalysis']
    if len(selected) == 1:
        obj = selected[0]
    elif len(found) == 1:
        obj = found[0]
    elif len(found) > 1:
        raise ValueError('해석이 여러 개입니다. 사용할 해석을 트리에서 활성화하세요.')
    else:
        doc.openTransaction('해석 컨테이너 생성')
        obj = ObjectsFem.makeAnalysis(doc)
        doc.commitTransaction()
    FemGui.setActiveAnalysis(obj)
    return obj


def fem_command(name):
    switch('FemWorkbench')
    analysis()
    if name not in Gui.listCommands():
        raise RuntimeError('설치된 FreeCAD가 이 명령을 제공하지 않습니다: ' + name)
    Gui.runCommand(name)


def isolate():
    selected = Gui.Selection.getSelection()
    if not selected:
        raise ValueError('격리할 부품을 트리 또는 3D 화면에서 선택하세요.')
    doc = App.ActiveDocument
    if any(hasattr(obj, 'Group') or not hasattr(obj, 'Shape') or not hasattr(obj.Shape, 'BoundBox') for obj in selected):
        raise ValueError('격리는 형상 부품 선택에 적용됩니다. 그룹을 펼쳐 격리할 부품들을 선택하세요.')
    if doc.Name not in ISOLATION:
        ISOLATION[doc.Name] = {obj.Name: obj.ViewObject.Visibility for obj in doc.Objects if obj.ViewObject}
    parents = [parent for obj in selected for parent in obj.InListRecursive
               if hasattr(parent, 'Group')]
    for obj in doc.Objects:
        if hasattr(obj, 'Shape') and obj.ViewObject.Visibility:
            obj.ViewObject.Visibility = obj in selected or obj in parents
    # A visible leaf stays hidden when its native Part/Body container is hidden.
    for obj in parents + selected:
        obj.ViewObject.Visibility = True
    record('isolate', selected=[obj.Name for obj in selected])


def restore_visibility():
    doc = App.ActiveDocument
    if not doc:
        return
    for name, visible in ISOLATION.pop(doc.Name, {}).items():
        obj = doc.getObject(name)
        if obj and obj.ViewObject:
            obj.ViewObject.Visibility = visible
    record('restore_visibility', document=doc.Name)


def _quality_mesh():
    from apps.desktop_pre.fem_edit import _native_type
    if CONNECTION is None:
        raise ValueError('문서 연결이 준비된 뒤 메시를 선택하세요.')
    owner = CONNECTION.active_owner()
    selected = list(Gui.Selection.getSelection())
    if not selected:
        selected = [obj for obj in owner.doc.Objects if _native_type(obj) == 'Fem::FemMeshGmsh']
    if (len(selected) != 1 or selected[0].Document is not owner.doc
            or _native_type(selected[0]) != 'Fem::FemMeshGmsh'):
        raise ValueError('모델 트리에서 확인할 현재 메시 하나를 선택하세요.')
    mesh = owner.fem._mesh({'object_id': selected[0].Name})
    return owner, mesh


def _open_quality_dialog(make_dialog):
    owner, mesh = _quality_mesh()
    dialog = make_dialog(QtWidgets, QtCore, owner, mesh, Gui.getMainWindow())
    dialog.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
    if dialog not in KEEP:
        KEEP.append(dialog)
        dialog.destroyed.connect(lambda *_: KEEP.remove(dialog) if dialog in KEEP else None)
    dialog.show()
    return dialog


def compare_mesh_quality():
    from apps.desktop_pre.mesh_compare_panel import make_dialog
    return _open_quality_dialog(make_dialog)


def inspect_mesh_quality():
    from apps.desktop_pre.mesh_element_panel import make_dialog
    return _open_quality_dialog(make_dialog)


def add_toolbar():
    main = Gui.getMainWindow()
    menu = main.menuBar().addMenu('CAE 작업')
    actions = [
        ('모델 열기', 'document-open', open_model),
        ('다른 이름으로 저장', 'document-save-as', save_as),
        None,
        ('형상 편집', 'PartWorkbench', lambda: switch('PartWorkbench')),
        ('스케치·피처', 'PartDesignWorkbench', lambda: switch('PartDesignWorkbench')),
        ('조립', 'AssemblyWorkbench', lambda: switch('AssemblyWorkbench')),
        ('메시', 'FEM_MeshGmshFromShape', lambda: fem_command('FEM_MeshGmshFromShape')),
        ('재료', 'FEM_MaterialSolid', lambda: fem_command('FEM_MaterialSolid')),
        ('고정', 'FEM_ConstraintFixed', lambda: fem_command('FEM_ConstraintFixed')),
        ('하중', 'FEM_ConstraintForce', lambda: fem_command('FEM_ConstraintForce')),
        None,
        ('선택 격리', 'view-visible', isolate),
        ('격리 해제', 'view-visible-all', restore_visibility),
        ('전체 맞춤', 'view-fit-all', lambda: Gui.activeDocument().activeView().fitAll()),
    ]
    for item in actions:
        if item is None:
            menu.addSeparator()
            continue
        label, icon, fn = item
        action = QtGui.QAction(Gui.getIcon(icon), label, main)
        action.triggered.connect(guarded(fn))
        menu.addAction(action)
    menu.addSeparator()
    quality_action = menu.addAction('메시 품질 확인…')
    quality_action.setObjectName('caeInspectMeshQuality')
    quality_action.triggered.connect(guarded(inspect_mesh_quality))
    compare_action = menu.addAction('메시 품질 비교…')
    compare_action.setObjectName('caeCompareMeshQuality')
    compare_action.triggered.connect(guarded(compare_mesh_quality))


def enable_managed(initial_owners=()):
    """Opt in to the existing managed tools; a service URL is not consent."""
    global CONNECTION
    if CONNECTION is not None:
        CONNECTION.dock.show()
        CONNECTION.dock.raise_()
        return CONNECTION
    if not CONFIG.get('service_url'):
        raise ValueError('Workbench에서 모델을 연 뒤 CAE 연구의 저장된 확장 조건 편집을 선택하세요.')
    file_actions = getattr(Gui.getMainWindow(), '_caelab_native_file_actions', None)
    if file_actions is not None and not initial_owners:
        file_actions['reconcile']()
        initial_owners = tuple(file_actions['owners'])
    from apps.desktop_pre.connection import Connection
    from apps.desktop_pre.native_controls import install
    CONNECTION = Connection(CONFIG, App, Gui, QtCore, QtWidgets, log=record,
                            initial_owners=initial_owners)
    CONNECTION.guards = install(CONNECTION, guarded(open_model))
    from apps.desktop_pre.beam_menu import install as install_beam
    from apps.desktop_pre.dynamic_menu import install as install_dynamic
    install_beam(CONNECTION)
    install_dynamic(CONNECTION)
    from apps.desktop_pre.portable_project import install_file_actions
    file_actions = install_file_actions(CONFIG, connection=CONNECTION)
    from apps.desktop_pre.connector_menu import install as install_connectors
    install_connectors(CONFIG, connection=CONNECTION, file_actions=file_actions)
    KEEP.append(CONNECTION)
    return CONNECTION


def add_native_actions():
    main = Gui.getMainWindow()
    existing = getattr(main, '_caelab_native_research_menu', None)
    if existing is not None:
        existing['attach']()
        return existing['menu']
    menu = QtWidgets.QMenu('CAE 연구', main)
    menu.setObjectName('CAELabResearchMenu')
    menu.menuAction().setObjectName('CAELabResearchMenu')
    # FreeCAD retranslates menu titles from QAction.data(), not QMenu.title().
    menu.menuAction().setData('CAE 연구')
    discussion = menu.addAction('선택 대상으로 논의…')
    discussion.setObjectName('CAELabSelectionDiscussion')
    discussion.triggered.connect(guarded(discuss_selection))
    action = menu.addAction('저장된 확장 조건 편집…')
    action.setObjectName('CAELabManagedConditions')
    action.triggered.connect(guarded(enable_managed))
    def attach():
        if menu.menuAction() not in main.menuBar().actions():
            main.menuBar().addMenu(menu)
        menu.menuAction().setVisible(True)
    main._caelab_native_research_menu = {'menu': menu, 'attach': attach}
    activated = getattr(main, 'workbenchActivated', None)
    if activated is not None:
        activated.connect(lambda *unused: QtCore.QTimer.singleShot(0, attach))
    attach()
    return menu


def discuss_selection():
    doc = App.ActiveDocument
    if doc is None:
        raise ValueError('논의할 FreeCAD 모델을 열고 대상을 선택하세요.')
    if not CONFIG.get('python') or not CONFIG.get('service_url'):
        raise ValueError('Workbench에서 모델을 열어 토론 연결을 준비하세요.')
    from apps.desktop_pre.native_context import model_snapshot
    selected = [{'object': row.Object.Name, 'subelements': list(row.SubElementNames)}
                for row in Gui.Selection.getSelectionEx(doc.Name)]
    scope = {'scope': {'kind': 'native_objects' if selected else 'document', 'objects': selected},
             'model_snapshot': model_snapshot(doc, selected)}
    if doc.FileName and Path(doc.FileName).is_file():
        scope['path'] = str(Path(doc.FileName).resolve())
    command = [CONFIG['python'], '-m', 'apps.research.selection_discussion',
               '--service', CONFIG['service_url'], '--selection-stdin']
    if CONFIG.get('discussion_id'):
        command.extend(['--discussion', CONFIG['discussion_id']])
    if CONFIG.get('workbench'):
        command.extend(['--workbench', json.dumps(CONFIG['workbench'], ensure_ascii=False)])
    if scope.get('path'):
        command.append(scope['path'])
    env = os.environ.copy()
    for name in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH', 'LD_LIBRARY_PATH'):
        env.pop(name, None)
    output = Path(CONFIG['output']) / 'discussion.log'
    with output.open('ab') as log:
        process = subprocess.Popen(command,
                                   cwd=repository, env=env, stdin=subprocess.PIPE,
                                   stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        process.stdin.write(json.dumps(scope, ensure_ascii=False).encode('utf-8'))
        process.stdin.close()
    Gui.getMainWindow().statusBar().showMessage('선택한 모델과 설정으로 Expert 대화를 여는 중입니다.')
    return process


def start(config_path):
    global CONFIG
    CONFIG = json.loads(Path(config_path).read_text(encoding='utf-8-sig'))
    if CONFIG.get('entry_mode', 'native') not in ('native', 'managed'):
        raise ValueError('Unknown FreeCAD entry mode')
    if CONFIG.get('input_receipt') and CONFIG.get('entry_mode', 'native') != 'managed':
        raise ValueError('보존한 계산 입력은 managed 진입으로 여세요.')
    output = Path(CONFIG['output'])
    output.mkdir(parents=True, exist_ok=True)
    def setup():
        global CONNECTION
        try:
            if CONFIG.get('gmsh'):
                App.ParamGet('User parameter:BaseApp/Preferences/Mod/Fem/Gmsh').SetString('gmshBinaryPath', CONFIG['gmsh'])
            App.ParamGet('User parameter:BaseApp/Preferences/View').SetBool('UseNewSelection', True)
            Gui.activateWorkbench('FemWorkbench')
            from apps.desktop_pre.native_solver_guard import install as install_solver_guard
            install_solver_guard()
            from apps.desktop_pre.native_presentation import install_restore_observer
            install_restore_observer(App, Gui, QtCore, QtWidgets)
            if CONFIG.get('entry_mode', 'native') == 'managed':
                add_toolbar()
            add_native_actions()
            for dock in Gui.getMainWindow().findChildren(QtWidgets.QDockWidget):
                if dock.objectName() in ('Python console', 'Report view'):
                    dock.hide()
            Gui.getMainWindow().showMaximized()
            opened_native_owner = None
            if CONFIG.get('native_project_open'):
                if any(CONFIG.get(key) for key in ('source', 'assembly', 'input_receipt')):
                    raise ValueError('저장본 열기 요청과 다른 원 입력을 함께 지정할 수 없습니다.')
                from apps.desktop_pre.portable_project import open_launch_config
                opened_native_owner, _ = open_launch_config(CONFIG['native_project_open'])
            if CONFIG.get('source'):
                doc = load(CONFIG['source'])
                if CONFIG.get('source_label'):
                    doc.Label = CONFIG['source_label']
            if CONFIG.get('assembly'):
                doc = load(CONFIG['assembly'])
            if not App.ActiveDocument:
                doc = App.newDocument('ResearchDesign')
                doc.UndoMode = 1
            if Gui.activeDocument() and opened_native_owner is None:
                Gui.activeDocument().activeView().viewAxonometric()
                Gui.activeDocument().activeView().fitAll()
            if CONFIG.get('entry_mode', 'native') == 'managed':
                enable_managed(() if opened_native_owner is None else (opened_native_owner,))
                if CONFIG.get('input_receipt'):
                    owner = CONNECTION.active_owner()
                    owner.project.open(CONFIG['input_receipt'])
                    CONNECTION.tick()
            from apps.desktop_pre.portable_project import install_file_actions
            native_file_actions = install_file_actions(CONFIG, connection=CONNECTION, owner=opened_native_owner)
            if CONNECTION is not None:
                from apps.desktop_pre.connector_menu import install as install_connectors
                install_connectors(CONFIG, connection=CONNECTION, file_actions=native_file_actions)
            def final_view():
                if Gui.activeDocument() and opened_native_owner is None:
                    Gui.activeDocument().activeView().viewAxonometric()
                    Gui.activeDocument().activeView().fitAll()
            QtCore.QTimer.singleShot(1500, final_view)
            update_caption()
            Gui.getMainWindow().statusBar().showMessage('FreeCAD FEM에서 모델을 편집하고 저장·계산하세요.')
            record('ready', freecad='.'.join(App.Version()[:3]), commands=list(Gui.listCommands()))
        except Exception:
            record('startup_error', error=traceback.format_exc())
            App.Console.PrintError(traceback.format_exc())
    QtCore.QTimer.singleShot(300, setup)
