"""CAE preparation workspace, hosted by the unmodified FreeCAD native application.

This is an integration prototype, not a replacement CAD kernel or release gate.
Run only inside FreeCAD; the launcher gives it a private profile and output folder.
"""
from pathlib import Path
import hashlib
import json
import shutil
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui
try:
    from PySide import QtWidgets
except ImportError:
    QtWidgets = QtGui

CONFIG = {}
KEEP = []


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


def working_copy(path):
    source = Path(path).resolve(strict=True)
    with source.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    folder = Path(CONFIG['output']) / 'imports' / (str(time.time_ns()) + '_' + digest[:10])
    folder.mkdir(parents=True)
    copy = folder / source.name
    shutil.copy2(source, copy)
    record('source_copy', source=str(source), copy=str(copy), sha256=digest)
    return copy


def load(path):
    started = time.perf_counter()
    copy = working_copy(path)
    if copy.suffix.lower() == '.fcstd':
        doc = App.openDocument(str(copy))
    else:
        import ImportGui
        doc = App.newDocument('ImportedModel')
        ImportGui.insert(str(copy), doc.Name)
        doc.recompute()
        doc.saveAs(str(copy.with_suffix('.FCStd')))
    doc.UndoMode = 1
    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    record('open', document=doc.Name, objects=len(doc.Objects), seconds=time.perf_counter()-started,
           working_file=doc.FileName)
    update_caption()
    return doc


def open_model():
    path, _ = QtWidgets.QFileDialog.getOpenFileName(Gui.getMainWindow(), '모델 열기 — 원본은 보존됩니다', '',
                                                  'CAD (*.FCStd *.step *.stp *.iges *.igs);;All files (*)')
    if path:
        load(path)


def save_as():
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
    Gui.getMainWindow().setWindowTitle('CAE Lab · 전처리 — ' + name + ' | FreeCAD 기반 시안')


def switch(name):
    if Gui.activeDocument() and Gui.activeDocument().getInEdit():
        raise ValueError('현재 편집을 완료하거나 취소한 후 작업대를 전환하세요.')
    Gui.activateWorkbench(name)
    update_caption()


def analysis():
    import ObjectsFem, FemGui
    doc = App.ActiveDocument
    if not doc:
        raise ValueError('먼저 모델을 여세요.')
    found = [obj for obj in doc.Objects if obj.TypeId == 'Fem::FemAnalysis']
    if found:
        obj = found[0]
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
    doc.openTransaction('선택 부품 격리')
    for obj in doc.Objects:
        if hasattr(obj, 'Shape') and obj.ViewObject.Visibility:
            obj.ViewObject.Visibility = obj in selected
    for obj in selected:
        obj.ViewObject.Visibility = True
    doc.commitTransaction()
    record('isolate', selected=[obj.Name for obj in selected])


class Inspector(QtWidgets.QDockWidget):
    """Only inspect the selection. Never walk/tessellate every face on selection."""
    def __init__(self):
        super().__init__('선택 검사', Gui.getMainWindow())
        self.setObjectName('CaeSelectionInspector')
        self.setMinimumWidth(230)
        box = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(box)
        layout.setContentsMargins(6, 6, 6, 6)
        self.summary = QtWidgets.QLabel('3D 화면 또는 모델 트리에서 개체를 선택하세요.')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QtWidgets.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(['항목', '현재 선택'])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 95)
        layout.addWidget(self.table)
        note = QtWidgets.QLabel('치수·배치·재료·조건은 왼쪽 속성 편집기에서 수정합니다.\nSpace: 표시 전환 · Ctrl+Z: 실행 취소')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.setWidget(box)
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.refresh)
        Gui.Selection.addObserver(self)

    def addSelection(self, *args): self.timer.start(60)
    def removeSelection(self, *args): self.timer.start(60)
    def clearSelection(self, *args): self.timer.start(60)
    def setSelection(self, *args): self.timer.start(60)

    def refresh(self):
        entries = Gui.Selection.getSelectionEx()
        rows = []
        for entry in entries[:32]:
            obj = entry.Object
            rows.extend([('개체', obj.Label), ('내부 ID', obj.Name), ('유형', obj.TypeId)])
            if entry.SubElementNames:
                rows.append(('선택 영역', ', '.join(entry.SubElementNames[:16])))
            if hasattr(obj, 'FemMesh'):
                rows.extend([('절점 수', str(obj.FemMesh.NodeCount)), ('체적 요소 수', str(obj.FemMesh.VolumeCount))])
            if hasattr(obj, 'Shape') and hasattr(obj.Shape, 'BoundBox'):
                # Bounding box is a native cached operation; no Python triangle copy.
                bounds = obj.Shape.BoundBox
                rows.append(('외곽 [mm]', f'{bounds.XLength:.4g} × {bounds.YLength:.4g} × {bounds.ZLength:.4g}'))
            for sub in list(entry.SubObjects)[:4]:
                if hasattr(sub, 'Area'):
                    rows.append(('면적 [mm²]', f'{sub.Area:.6g}'))
        self.summary.setText(f'{len(entries)}개 개체 선택' if entries else '선택 없음')
        self.table.setRowCount(len(rows))
        for i, (key, value) in enumerate(rows):
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(key))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(value))
        record('selection', entries=[{'object': e.ObjectName, 'subelements': list(e.SubElementNames)} for e in entries[:32]])


def add_toolbar():
    main = Gui.getMainWindow()
    bar = QtWidgets.QToolBar('CAE 작업', main)
    bar.setObjectName('CaeMainOperations')
    bar.setIconSize(QtCore.QSize(20, 20))
    bar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
    main.addToolBar(QtCore.Qt.TopToolBarArea, bar)
    main.insertToolBarBreak(bar)
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
        ('전체 맞춤', 'view-fit-all', lambda: Gui.activeDocument().activeView().fitAll()),
    ]
    for item in actions:
        if item is None:
            bar.addSeparator()
            menu.addSeparator()
            continue
        label, icon, fn = item
        action = QtGui.QAction(Gui.getIcon(icon), label, main)
        action.triggered.connect(guarded(fn))
        bar.addAction(action)
        menu.addAction(action)
    KEEP.append(bar)


def start(config_path):
    global CONFIG
    CONFIG = json.loads(Path(config_path).read_text(encoding='utf-8-sig'))
    output = Path(CONFIG['output'])
    output.mkdir(parents=True, exist_ok=True)
    def setup():
        try:
            App.ParamGet('User parameter:BaseApp/Preferences/Mod/Fem/Gmsh').SetString('gmshBinaryPath', CONFIG['gmsh'])
            App.ParamGet('User parameter:BaseApp/Preferences/View').SetBool('UseNewSelection', True)
            Gui.activateWorkbench('FemWorkbench')
            add_toolbar()
            inspector = Inspector()
            Gui.getMainWindow().addDockWidget(QtCore.Qt.RightDockWidgetArea, inspector)
            KEEP.append(inspector)
            for dock in Gui.getMainWindow().findChildren(QtWidgets.QDockWidget):
                if dock.objectName() in ('Python console', 'Report view'):
                    dock.hide()
            Gui.getMainWindow().showMaximized()
            if CONFIG.get('source'):
                load(CONFIG['source'])
            if CONFIG.get('assembly'):
                doc = load(CONFIG['assembly'])
                doc.Label = '굽힘 시험 지그 조립 — STEP 원본 복사'
            Gui.activeDocument().activeView().viewAxonometric()
            Gui.activeDocument().activeView().fitAll()
            def final_view():
                if Gui.activeDocument():
                    Gui.activeDocument().activeView().viewAxonometric()
                    Gui.activeDocument().activeView().fitAll()
            QtCore.QTimer.singleShot(1500, final_view)
            update_caption()
            Gui.getMainWindow().statusBar().showMessage('실제 CAD 편집 · 원본 보존 / 해석·제조 승인 미검증')
            record('ready', freecad='.'.join(App.Version()[:3]), commands=list(Gui.listCommands()))
        except Exception:
            record('startup_error', error=traceback.format_exc())
            App.Console.PrintError(traceback.format_exc())
    QtCore.QTimer.singleShot(300, setup)
