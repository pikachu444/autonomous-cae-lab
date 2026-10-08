"""Local Qt design-review applications. No browser or service is required."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QAction, QKeySequence, QColor, QPalette, QFont
from PySide6.QtWidgets import (QApplication, QMainWindow, QFileDialog, QMessageBox,
    QToolBar, QLabel, QDialog, QVBoxLayout, QLineEdit, QListWidget,
    QDialogButtonBox, QStyle)

ROOT = Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
NAMES = {'pre':'전처리', 'runner':'솔버 실행기', 'post':'후처리', 'opt':'최적화', 'expert':'전문가 자문', 'workbench':'Workbench'}
EXT = {'pre':'caeprep','runner':'caerun','post':'caepost','opt':'caestudy','expert':'caechat','workbench':'caeproject'}
DATA = ROOT / 'user-data'

def content_hash(doc):
    """Exclude document chrome and view selection from dependency invalidation."""
    value=copy.deepcopy(doc)
    for key in ('id','schema','revision','path','name','content_hash','source_path'):
        value.pop(key,None)
    view_keys=('selection','selected','selected_run','selected_candidate','selected_node','selected_message','view_state','frame','legend','mode','paused','draft')
    for container in (value,value.get('data',{})):
        if isinstance(container,dict):
            for key in view_keys:container.pop(key,None)
    if value.get('kind')=='post' and value.get('data',{}).get('source_type')=='demo':
        # Selecting an existing demo field changes only its displayed component.
        # Imported curve quantity/unit metadata remains part of the input hash.
        value['data'].pop('component',None);value['data'].pop('unit',None)
    if isinstance(value.get('source_ref'),dict):value['source_ref'].pop('path',None)
    # Names and IDs inside variables/materials/conditions are scientific input.
    # Do not recursively strip them as if they were document chrome.
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()

STYLE = """
QMainWindow, QDialog { background:#edf0f3; }
QWidget { font-family:'Malgun Gothic'; font-size:12px; color:#263746; }
QMenuBar { background:#f8f9fb; border-bottom:1px solid #bdc8d2; padding:2px; }
QMenuBar::item { padding:5px 10px; }
QMenuBar::item:selected,QMenu::item:selected { background:#dceaf7; color:#163e67; }
QMenu { background:white; border:1px solid #aab7c5; padding:4px; }
QMenu::item { padding:6px 26px; }
QToolBar { background:#f4f6f8; border:0; border-bottom:1px solid #bac6d1; spacing:3px; padding:3px; }
QToolButton { padding:5px 7px; border:1px solid transparent; border-radius:2px; }
QToolButton:hover { background:#dceafa; border-color:#a9bfd3; }
QToolButton:pressed,QToolButton:checked { background:#c7def4; border-color:#6d9dcc; }
QPushButton { background:#f8fafc; border:1px solid #aebfce; padding:5px 10px; border-radius:2px; min-height:18px; }
QPushButton:hover { background:#e4eff9; border-color:#749cbe; }
QPushButton:disabled { color:#82909c; background:#edf0f3; border-color:#d2d9df; }
QPushButton[primary="true"] { background:#276396; color:white; border-color:#205582; }
QLabel[section="true"] { background:#dfe6ed; color:#283f55; padding:6px; font-weight:600; border-bottom:1px solid #bdc8d1; }
QLabel[note="true"] { color:#6a4e17; background:#fff5da; padding:5px; border:1px solid #e7d8b6; }
QLineEdit,QTextEdit,QPlainTextEdit,QSpinBox,QDoubleSpinBox,QComboBox { background:white; border:1px solid #b8c5d1; padding:4px; selection-background-color:#d1e6f8; selection-color:#183a59; }
QLineEdit:focus,QTextEdit:focus,QPlainTextEdit:focus { border:1px solid #3d83b7; }
QTreeWidget,QTableWidget,QListWidget,QTextBrowser,QGraphicsView { background:white; border:1px solid #c1ccd5; alternate-background-color:#f4f7fa; }
QTreeWidget::item,QListWidget::item { min-height:24px; }
QTreeWidget::item:selected,QListWidget::item:selected { background:#d5e7f8; color:#163f65; }
QHeaderView::section { background:#e8edf2; border:0; border-right:1px solid #c6d1db; border-bottom:1px solid #b8c5d1; padding:5px; font-weight:600; }
QTableWidget { gridline-color:#dfe5eb; selection-background-color:#d5e7f8; selection-color:#183a59; }
QTabWidget::pane { border:1px solid #bbc8d4; background:white; }
QTabBar::tab { background:#e6ecf1; border:1px solid #bbc8d4; padding:7px 15px; margin-right:1px; }
QTabBar::tab:selected { background:white; border-bottom-color:white; color:#164c7c; font-weight:600; }
QGroupBox { border:1px solid #c3cdd7; margin-top:12px; padding:8px; font-weight:600; }
QGroupBox::title { subcontrol-origin:margin; left:8px; padding:0 4px; }
QSplitter::handle { background:#d5dde5; }
QStatusBar { background:#e3eaf1; border-top:1px solid #bbc8d3; }
QScrollBar:vertical { background:#f0f3f6; width:12px; margin:0; }
QScrollBar::handle:vertical { background:#b6c4d1; min-height:30px; border-radius:3px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
"""

def read_document(path):
    p = Path(path)
    doc = json.loads(p.read_text(encoding='utf-8'))
    if doc.get('kind') not in NAMES or not isinstance(doc.get('revision',0),int):
        raise ValueError('지원하는 CAE Lab 문서가 아닙니다.')
    if doc.get('schema',1) != 1:
        raise ValueError('이 문서의 스키마 버전은 지원하지 않습니다.')
    doc['path']=str(p.resolve())
    return doc

def write_document(path, doc, expected=None):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and expected is not None:
        existing=read_document(p)
        if existing.get('id')!=doc.get('id') or existing['revision']!=expected:
            raise RuntimeError(f'다른 창에서 저장되었습니다. 현재 편집 r{expected}, 파일 r{existing["revision"]}. 편집 내용은 보존됩니다. 다른 이름으로 저장하거나 파일을 다시 여세요.')
    value=copy.deepcopy(doc)
    value['schema']=1
    value['revision']=int(doc.get('revision',0))+1
    value['path']=str(p.resolve())
    value['content_hash']=content_hash(value)
    persisted=copy.deepcopy(value)
    persisted.pop('path',None)
    raw=json.dumps(persisted,ensure_ascii=False,indent=2)
    history=p.parent/'.history'/value['id']
    history.mkdir(parents=True,exist_ok=True)
    (history/f'{value["revision"]}.json').write_text(raw,encoding='utf-8')
    temp=p.with_suffix(p.suffix+'.tmp')
    temp.write_text(raw,encoding='utf-8')
    os.replace(temp,p)
    return value

def launch(kind, doc=None, revision=None):
    argv=[sys.executable] + ([] if getattr(sys,'frozen',False) else [str(ROOT/'desktop.py')]) + ['--app',kind]
    if doc:
        argv += ['--file',str(doc)]
    if revision is not None: argv += ['--revision',str(revision)]
    return subprocess.Popen(argv,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

class MainWindow(QMainWindow):
    def __init__(self,kind,filename=None,revision=None):
        super().__init__()
        self.kind=kind; self.filename=Path(filename).resolve() if filename else None
        self.readonly=revision is not None
        self.dirty=False; self.undo_stack=[]; self.redo_stack=[]; self.actions=[]
        self.doc={'id':uuid.uuid4().hex,'kind':kind,'name':f'{NAMES[kind]} 검토 예제','revision':0,'schema':1}
        if self.filename:
            self.doc=read_document(self.filename)
            if revision is not None:
                self.doc=read_document(self.filename.parent/'.history'/self.doc['id']/f'{revision}.json')
                self.doc['path']=str(self.filename)
            if self.doc['kind']!=kind: raise ValueError('문서 종류와 프로그램이 다릅니다.')
        self.resize(1480,940); self.setMinimumSize(1050,700)
        self.build_workspace()
        self.make_menus()
        self.status_label=QLabel(); self.statusBar().addPermanentWidget(self.status_label)
        self.statusBar().showMessage('설계 검토 시안 · 문서 편집/저장은 실제 동작 · 계산/전문가 생성은 명시된 시연')
        self.update_title()

    def build_workspace(self):
        if self.kind in ('expert','workbench'):
            from collaboration_spaces import create_workspace
        else:
            from workspaces import create_workspace
        self.workspace=create_workspace(self.kind,copy.deepcopy(self.doc),self.changed,self.open_tool)
        self.doc=self.workspace.document()
        self.setCentralWidget(self.workspace)
        self.readonly_snapshot=copy.deepcopy(self.doc) if self.readonly else None

    def action(self,label,callback,shortcut=None,icon=None):
        a=QAction(label,self); a.triggered.connect(callback)
        if shortcut: a.setShortcut(QKeySequence(shortcut))
        if icon: a.setIcon(self.style().standardIcon(icon))
        a.setToolTip(label+(f' ({shortcut})' if shortcut else ''))
        self.actions.append(a)
        return a

    def make_menus(self):
        f=self.menuBar().addMenu('파일(&F)'); e=self.menuBar().addMenu('편집(&E)'); v=self.menuBar().addMenu('보기(&V)')
        groups=self.workspace.tool_menus() if hasattr(self.workspace,'tool_menus') else {'작업':[]}
        domain_menus={name:self.menuBar().addMenu(name) for name in groups};h=self.menuBar().addMenu('도움말(&H)')
        std=QStyle.StandardPixmap
        new=self.action('새 문서',self.new,'Ctrl+N',std.SP_FileIcon)
        op=self.action('열기…',self.open,'Ctrl+O',std.SP_DialogOpenButton)
        self.save_action=self.action('저장',self.save,'Ctrl+S',std.SP_DialogSaveButton)
        sa=self.action('다른 이름으로 저장…',lambda:self.save(True),'Ctrl+Shift+S')
        for a in [new,op,self.save_action,sa]: f.addAction(a)
        f.addSeparator(); f.addAction(self.action('닫기',self.close,'Alt+F4'))
        self.undo_action=self.action('실행 취소',self.undo,'Ctrl+Z',std.SP_ArrowBack)
        self.redo_action=self.action('다시 실행',self.redo,'Ctrl+Y',std.SP_ArrowForward)
        e.addActions([self.undo_action,self.redo_action]); e.addAction(self.action('명령 찾기…',self.palette,'Ctrl+K'))
        v.addAction(self.action('검토 크기 1480 × 940',lambda:self.resize(1480,940)))
        v.addAction(self.action('작은 창 1100 × 760',lambda:self.resize(1100,760)))
        v.addAction(self.action('화면 캡처 저장…',self.capture,'F12'))
        common=QToolBar('문서',self);common.setObjectName('document');common.setMovable(False);common.setIconSize(QSize(18,18));common.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(common);common.addActions([new,op,self.save_action]);common.addSeparator();common.addActions([self.undo_action,self.redo_action])
        common.addSeparator(); common.addAction(self.action('명령 찾기',self.palette,None,std.SP_FileDialogContentsView))
        self.addToolBarBreak()
        domain=QToolBar(NAMES[self.kind]+' 명령',self);domain.setMovable(False);domain.setIconSize(QSize(18,18));domain.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon);self.addToolBar(domain)
        icons={'open':std.SP_DialogOpenButton,'import':std.SP_DialogOpenButton,'save':std.SP_DialogSaveButton,'add':std.SP_FileDialogNewFolder,'run':std.SP_MediaPlay,'play':std.SP_MediaPlay,'stop':std.SP_MediaStop,'pause':std.SP_MediaPause,'validate':std.SP_DialogApplyButton,'check':std.SP_DialogApplyButton,'export':std.SP_DialogSaveButton,'refresh':std.SP_BrowserReload,'help':std.SP_MessageBoxInformation,'link':std.SP_ArrowRight,'compare':std.SP_FileDialogDetailedView,'edit':std.SP_FileDialogContentsView,'delete':std.SP_TrashIcon}
        for label,icon,cb,shortcut in self.workspace.tool_actions():
            a=self.action(label,cb,shortcut or None,icons.get(icon,std.SP_FileDialogDetailedView))
            menu=next((domain_menus[name] for name,labels in groups.items() if label in labels),next(iter(domain_menus.values())))
            menu.addAction(a);domain.addAction(a)
            if self.readonly:a.setEnabled(False)
        h.addAction(self.action('시안의 범위',lambda:QMessageBox.information(self,'시안 범위','Windows Qt Widgets 독립 창과 파일 저장을 검토하는 시안입니다.\nCSV 가져오기·문서 편집·선택·저장은 실제 동작합니다.\n솔버/DOE/전문가 답변은 표시된 시연 데이터이며 제품 완성본이 아닙니다.\n이전 웹 시안은 사용자 거부로 폐기된 설계 방향입니다.')))
        if self.readonly:self.save_action.setEnabled(False)

    def update_title(self):
        doc=self.workspace.document();self.doc=doc
        suffix=' · 과거 버전 읽기 전용' if self.readonly else (' *' if self.dirty else '')
        self.setWindowTitle(f'{NAMES[self.kind]} — {doc.get("name","이름 없음")} · r{doc.get("revision",0)}{suffix} — CAE Lab')
        self.status_label.setText(f'{"읽기 전용" if self.readonly else "수정됨" if self.dirty else "저장됨" if self.filename else "새 문서"}  |  {self.filename.name if self.filename else "파일 미지정"}  |  r{doc.get("revision",0)}')
        self.undo_action.setEnabled(bool(self.undo_stack) and not self.readonly);self.redo_action.setEnabled(bool(self.redo_stack) and not self.readonly)

    def changed(self,reason='',before=None):
        if self.readonly and hasattr(self,'readonly_snapshot') and self.readonly_snapshot is not None:
            if content_hash(self.workspace.document())==content_hash(self.readonly_snapshot):
                self.statusBar().showMessage('과거 버전 보기 · 입력과 결과는 변경되지 않습니다.',5000)
                return
            self.workspace.set_document(copy.deepcopy(self.readonly_snapshot))
            QMessageBox.information(self,'과거 버전','이 버전은 읽기 전용입니다. 편집하려면 다른 이름으로 저장하세요.')
            return
        if before is not None:self.undo_stack.append(copy.deepcopy(before));self.undo_stack=self.undo_stack[-30:]
        self.redo_stack=[];self.dirty=True
        if hasattr(self,'status_label'):self.update_title();self.statusBar().showMessage(str(reason),6000)

    def undo(self):
        if not self.undo_stack:return
        self.redo_stack.append(copy.deepcopy(self.workspace.document()));self.workspace.set_document(self.undo_stack.pop());self.dirty=True;self.update_title()

    def redo(self):
        if not self.redo_stack:return
        self.undo_stack.append(copy.deepcopy(self.workspace.document()));self.workspace.set_document(self.redo_stack.pop());self.dirty=True;self.update_title()

    def save(self,as_new=False):
        if self.readonly and not as_new:return False
        doc=copy.deepcopy(self.workspace.document()); path=self.filename
        if as_new or path is None:
            DATA.mkdir(exist_ok=True)
            p,_=QFileDialog.getSaveFileName(self,'문서 저장',str(DATA/f'{doc.get("name",NAMES[self.kind])}.{EXT[self.kind]}'),f'CAE Lab (*.{EXT[self.kind]})')
            if not p:return False
            path=Path(p)
            if path.suffix!='.'+EXT[self.kind]:path=path.with_suffix('.'+EXT[self.kind])
            if as_new:doc['id']=uuid.uuid4().hex;doc['revision']=0
            doc['name']=path.stem
        try:
            saved=write_document(path,doc,doc['revision'] if path.exists() else None)
        except Exception as exc:QMessageBox.warning(self,'저장하지 못했습니다',str(exc));return False
        if self.readonly and as_new:
            launch(self.kind,path)
            self.statusBar().showMessage('새 사본을 편집 가능한 별도 창으로 열었습니다.',8000)
            return True
        self.filename=path; self.workspace.set_document(saved);self.dirty=False;self.undo_stack=[];self.redo_stack=[];self.update_title();self.statusBar().showMessage(f'저장 완료 · {path}',8000);return True

    def open(self):
        path,_=QFileDialog.getOpenFileName(self,'문서 열기',str(DATA),f'CAE Lab (*.{EXT[self.kind]})')
        if path:launch(self.kind,path)

    def new(self):launch(self.kind)

    def open_tool(self,kind,document_or_id=None,revision=None):
        if kind not in NAMES:return
        if isinstance(document_or_id,dict):
            d=copy.deepcopy(document_or_id);d.setdefault('id',uuid.uuid4().hex);d['kind']=kind;d.setdefault('revision',0);d.setdefault('name',f'{NAMES[kind]} 전달 문서');d['schema']=1
            DATA.mkdir(exist_ok=True);path=DATA/f'{d["id"]}.{EXT[kind]}'
            if d.get('path') and Path(d['path']).exists() and d.get('kind')==kind:path=Path(d['path'])
            else:write_document(path,d,None)
            launch(kind,path,revision)
        elif isinstance(document_or_id,str):
            p=Path(document_or_id)
            if not p.exists():
                matches=[x for x in DATA.glob('*') if x.is_file() and x.suffix[1:] in EXT.values() and read_document(x).get('id')==document_or_id]
                if not matches:QMessageBox.warning(self,'참조를 찾지 못했습니다','파일 위치를 다시 연결하세요.');return
                p=matches[0]
            launch(kind,p,revision)
        else:launch(kind)

    def palette(self):
        dialog=QDialog(self);dialog.setWindowTitle('명령 찾기 · Ctrl+K');dialog.resize(480,470)
        layout=QVBoxLayout(dialog);search=QLineEdit();search.setPlaceholderText('명령 이름으로 검색');items=QListWidget();layout.addWidget(search);layout.addWidget(items)
        def refresh(text=''):
            items.clear()
            for i,a in enumerate(self.actions):
                if a.isEnabled() and text.lower() in a.text().lower():items.addItem(a.text()+'    '+a.shortcut().toString());items.item(items.count()-1).setData(Qt.ItemDataRole.UserRole,i)
        def run(item):
            a=self.actions[item.data(Qt.ItemDataRole.UserRole)];dialog.accept();a.trigger()
        search.textChanged.connect(refresh);items.itemActivated.connect(run);refresh();search.setFocus();dialog.exec()

    def capture(self):
        path,_=QFileDialog.getSaveFileName(self,'현재 화면 캡처',str(DATA/f'{self.kind}.png'),'PNG (*.png)')
        if path:self.grab().save(path)

    def closeEvent(self,event):
        if self.dirty:
            answer=QMessageBox.question(self,'저장하지 않은 변경','변경을 저장하고 닫을까요?',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
            if answer==QMessageBox.StandardButton.Cancel or (answer==QMessageBox.StandardButton.Save and not self.save()):event.ignore();return
        event.accept()

def main():
    p=argparse.ArgumentParser();p.add_argument('--app',choices=NAMES,default='workbench');p.add_argument('--file');p.add_argument('--revision',type=int);args=p.parse_args()
    app=QApplication(sys.argv);app.setApplicationName('Autonomous CAE Lab');app.setOrganizationName('CAE Lab');app.setStyle('Fusion');app.setStyleSheet(STYLE)
    palette=QPalette();palette.setColor(QPalette.ColorRole.Window,QColor('#edf0f3'));palette.setColor(QPalette.ColorRole.Base,QColor('white'));palette.setColor(QPalette.ColorRole.Text,QColor('#263746'));palette.setColor(QPalette.ColorRole.WindowText,QColor('#263746'));palette.setColor(QPalette.ColorRole.ButtonText,QColor('#263746'));palette.setColor(QPalette.ColorRole.Highlight,QColor('#cfe3f6'));palette.setColor(QPalette.ColorRole.HighlightedText,QColor('#183a59'));app.setPalette(palette)
    try:w=MainWindow(args.app,args.file,args.revision)
    except Exception as exc:QMessageBox.critical(None,'문서를 열지 못했습니다',str(exc));return 1
    w.show();return app.exec()

if __name__=='__main__':sys.exit(main())
