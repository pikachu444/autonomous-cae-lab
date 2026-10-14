"""Native Qt input-bundle and target selection; local edits never submit a job."""
from copy import deepcopy
from pathlib import Path
from threading import Event
import math

from PySide6.QtCore import Qt, Signal, QThread, QPointF, QItemSelectionModel
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,
    QLineEdit,QLabel,QPushButton,QComboBox,QCheckBox,QFileDialog,QDialogButtonBox,
    QPlainTextEdit,QSplitter,QTreeWidget,QTreeWidgetItem,QTableWidget,QTableWidgetItem,
    QAbstractItemView,QHeaderView,QMessageBox)
from caelab.impact_source import capture, ImportCancelled, resolve
from caelab.impact_model import parse_inp, model_from_settings
from caelab import impact_sets as sets


class _Import(QThread):
    ready=Signal(object,str)
    def __init__(self,entry,root,parent):
        super().__init__(parent);self.entry=entry;self.root=root;self.cancelled=Event()
    def run(self):
        try:
            source=capture(self.entry,self.root,cancel=self.cancelled.is_set)
            try:
                text,spans=resolve(source);model=parse_inp(text,spans)
                message=f"절점 {len(model['nodes']):,}개 / 요소 {len(model['elements']):,}개"
            except ValueError as error:message='계산 전 수정 필요: '+str(error)
            if not self.cancelled.is_set():self.ready.emit(source,message)
        except ImportCancelled:pass
        except (OSError,ValueError,TypeError,KeyError) as error:
            if not self.cancelled.is_set():self.ready.emit(None,str(error))


class ImportDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle('유한요소 입력 가져오기');self.resize(780,540)
        self.source=None;self.worker=None;self._cancel=False
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        self.entry=QLineEdit();self.root=QLineEdit()
        for field,label,call in ((self.entry,'주 입력 파일',self.choose_entry),(self.root,'입력 제출 작업 폴더',self.choose_root)):
            row=QHBoxLayout();row.addWidget(field,1);button=QPushButton('찾기…');button.clicked.connect(call);row.addWidget(button);form.addRow(label,row)
            field.textEdited.connect(self.invalidate)
        self.units=QCheckBox('원 입력 단위: Mg, mm, s, N, MPa');layout.addWidget(self.units)
        row=QHBoxLayout();self.check=QPushButton('입력 확인');self.check.clicked.connect(self.check_input);row.addWidget(self.check)
        self.status=QLabel('포함 파일은 모두 선택한 작업 폴더에서 찾습니다.');self.status.setWordWrap(True);row.addWidget(self.status,1);layout.addLayout(row)
        self.files=QComboBox();self.files.currentIndexChanged.connect(self.show_file);layout.addWidget(self.files)
        self.original=QPlainTextEdit();self.original.setReadOnly(True);layout.addWidget(self.original,1)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.ok=self.buttons.button(QDialogButtonBox.StandardButton.Ok);self.ok.setText('가져오기');self.ok.setEnabled(False)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.units.toggled.connect(lambda _:self.ok.setEnabled(self.source is not None and self.units.isChecked() and self.worker is None))
    def choose_entry(self):
        if self.worker:return
        path,_=QFileDialog.getOpenFileName(self,'주 입력 파일','','Abaqus 입력 (*.inp)')
        if path:self.entry.setText(path);self.invalidate()
        if path and not self.root.text():self.root.setText(str(Path(path).parent))
    def choose_root(self):
        if self.worker:return
        path=QFileDialog.getExistingDirectory(self,'입력 제출 작업 폴더',self.root.text())
        if path:self.root.setText(path);self.invalidate()
    def invalidate(self,*_):
        self.source=None;self.ok.setEnabled(False);self.files.clear();self.original.clear()
    def check_input(self):
        if self.worker:return
        self.invalidate();self._cancel=False
        self.worker=_Import(self.entry.text(),self.root.text(),self)
        self.entry.setEnabled(False);self.root.setEnabled(False);self.check.setEnabled(False)
        self.status.setText('원파일을 읽고 포함 순서를 확인하는 중…')
        self.worker.ready.connect(self.received);self.worker.finished.connect(self.finished_read);self.worker.start()
    def received(self,source,message):
        if self._cancel:return
        self.source=source;self.status.setText(message)
        self.files.clear()
        if source:
            for item in source['bundle']['files']:self.files.addItem(item['path'],item['text'])
            self.files.addItem('펼친 입력',source['text'])
            self.ok.setText('초안으로 가져오기' if message.startswith('계산 전') else '가져오기')
    def finished_read(self):
        worker=self.worker;self.worker=None;worker.deleteLater()
        self.entry.setEnabled(True);self.root.setEnabled(True);self.check.setEnabled(True)
        if self._cancel:super().reject()
        else:self.ok.setEnabled(self.source is not None and self.units.isChecked())
    def show_file(self,*_):self.original.setPlainText(self.files.currentData() or '')
    def reject(self):
        if self.worker:
            self._cancel=True;self.worker.cancelled.set();self.status.setText('가져오기를 취소하는 중…');return
        super().reject()
    def closeEvent(self,event):
        if self.worker:self.reject();event.ignore()
        else:super().closeEvent(event)


class MeshPreview(QWidget):
    faceClicked=Signal(object)
    def __init__(self,parent=None):
        super().__init__(parent);self.setMinimumSize(280,230);self.model=None;self.faces=[]
        self.selected=set();self.nodes=set();self.view='입체';self.polygons=[]
    def set_model(self,model,faces=None,selected=(),nodes=()):
        self.model=model;self.faces=faces if faces is not None else sets.facets(model)
        self.selected=set(map(tuple,selected));self.nodes=set(nodes);self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(),QColor('#f5f7fa'));self.polygons=[]
        if not self.model:
            p.setPen(QColor('#566477'));p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'메시와 집합을 선택하세요');return
        points=self.model['nodes'];middle=sets.center(list(points.values()))
        def project(xyz):
            x,y,z=sets.sub(xyz,middle)
            if self.view=='XY':return x,y,z
            if self.view=='XZ':return x,z,-y
            if self.view=='YZ':return y,z,x
            return .7071*(x-y),.4082*(x+y)-.8165*z,.5774*(x+y+z)
        projected={n:project(x) for n,x in points.items()}
        xmin=min(v[0] for v in projected.values());xmax=max(v[0] for v in projected.values())
        ymin=min(v[1] for v in projected.values());ymax=max(v[1] for v in projected.values())
        scale=min((self.width()-50)/max(xmax-xmin,1e-12),(self.height()-65)/max(ymax-ymin,1e-12))
        def screen(n):
            x,y,_=projected[n];return QPointF(self.width()/2+(x-(xmin+xmax)/2)*scale,self.height()/2+(y-(ymin+ymax)/2)*scale)
        stride=max(1,math.ceil(len(self.faces)/6000))
        context={(f['element'],f['side']):f for f in self.faces[::stride]}
        context.update({(f['element'],f['side']):f for f in self.faces if (f['element'],f['side']) in self.selected})
        displayed=list(context.values())
        for face in sorted(displayed,key=lambda f:sum(projected[n][2] for n in f['corners'])/len(f['corners'])):
            key=(face['element'],face['side']);active=key in self.selected
            polygon=QPolygonF([screen(n) for n in face['corners']])
            p.setPen(QPen(QColor('#17639b' if active else '#a5afbc'),1.4 if active else .7))
            p.setBrush(QColor(52,143,205,190) if active else QColor(212,220,230,70));p.drawPolygon(polygon)
            self.polygons.append((polygon,key))
        p.setPen(QPen(QColor('#c45e13'),3.5))
        for n in sorted(self.nodes)[::max(1,math.ceil(len(self.nodes)/6000))]:p.drawPoint(screen(n))
        p.setPen(QColor('#526175'));p.drawText(12,22,'모델 좌표 [mm]   '+self.view)
        note='모서리 절점 면 미리보기'
        if stride>1:note+=f' / 표시 {len(displayed):,}면, 전체 {len(self.faces):,}면'
        p.drawText(12,self.height()-12,note)
    def mousePressEvent(self,event):
        for polygon,key in reversed(self.polygons):
            if polygon.containsPoint(event.position(),Qt.FillRule.OddEvenFill):self.faceClicked.emit(key);return


def preview_tools(layout,view):
    row=QHBoxLayout();row.addStretch();combo=QComboBox();combo.addItems(['입체','XY','XZ','YZ'])
    combo.currentTextChanged.connect(lambda value:(setattr(view,'view',value),view.update()));row.addWidget(combo);layout.addLayout(row)


def bounds_label(model,nodes,elements=(),faces=0):
    info=sets.summary(model,nodes,elements,faces)
    counts=f"절점 {info['nodes']:,}개 / 요소 {info['elements']:,}개"
    if faces:counts+=f' / 면 {faces:,}개'
    if info['bounds_mm']:
        counts+='\n'+'    '.join(f'{a}: {v[0]:.6g} ~ {v[1]:.6g}' for a,v in zip('XYZ',info['bounds_mm']))+' mm'
    return counts


class TargetDialog(QDialog):
    def __init__(self,settings,elset,kind,definition=None,parent=None):
        super().__init__(parent);self.setWindowTitle('운동 대상 만들기' if kind=='nset' else '접촉면 만들기');self.resize(1000,670)
        self.settings=deepcopy(settings);self.elset=elset;self.kind=kind;self.definition=definition;self.result_definition=None
        if definition:self.settings['generated_sets']=[d for d in self.settings.get('generated_sets',[]) if d!=definition]
        self.model=model_from_settings(self.settings);self.candidate_faces=[];self.all_faces=sets.facets(self.model);self._restore_definition=True
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        self.element_set=QComboBox();self.element_set.addItems(sorted(self.model['elsets']));self.element_set.setCurrentText(elset)
        form.addRow('원 요소 집합',self.element_set);self.name=QLineEdit(definition['name'] if definition else '')
        if definition:self.name.setReadOnly(True)
        form.addRow('이름',self.name)
        if definition:
            used=sets.references(settings,definition)
            if used:
                affected=QLabel('변경 반영 시 대상이 바뀌는 조건: '+', '.join(used));affected.setWordWrap(True);form.addRow(affected)
        self.mode=QComboBox();self.mode.addItem('전체 메시의 외곽면','exterior');self.mode.addItem('요소 면 직접 선택','explicit')
        if definition and kind=='surface':self.mode.setCurrentIndex(self.mode.findData(definition['mode']))
        if kind=='surface':form.addRow('면 선택',self.mode)
        split=QSplitter();layout.addWidget(split,1)
        selection=QWidget(self);sl=QVBoxLayout(selection);sl.setContentsMargins(0,0,0,0)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['요소','면','위치','면적 [mm²]'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        sl.addWidget(self.table,1)
        all_button=QPushButton('모든 면 선택');all_button.clicked.connect(self.table.selectAll);sl.addWidget(all_button)
        self.internal=QCheckBox('선택한 내부면을 사용');sl.addWidget(self.internal)
        if definition:self.internal.setChecked(definition.get('allow_internal',False))
        if kind=='surface':split.addWidget(selection)
        else:selection.hide()
        right=QWidget();rl=QVBoxLayout(right);rl.setContentsMargins(0,0,0,0);self.view=MeshPreview();preview_tools(rl,self.view);rl.addWidget(self.view,1);split.addWidget(right)
        split.setSizes([340,630]);self.info=QLabel();self.info.setWordWrap(True);layout.addWidget(self.info)
        self.message=QLabel();self.message.setWordWrap(True);layout.addWidget(self.message)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('변경 반영' if definition else '만들기');self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.buttons.accepted.connect(self.apply);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.element_set.currentTextChanged.connect(self.change_element_set);self.mode.currentIndexChanged.connect(self.populate);self.table.itemSelectionChanged.connect(self.selection_changed);self.view.faceClicked.connect(self.select_face)
        self.populate()
    def change_element_set(self,name):
        self.elset=name;self.internal.setChecked(False);self.populate()
    def populate(self,*_):
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        self.message.clear()
        try:
            if self.kind=='nset':
                ids={n for e in self.model['elsets'][self.elset] for n in self.model['elements'][e]['nodes']}
                self.view.set_model(self.model,faces=self.all_faces,nodes=ids);self.info.setText(bounds_label(self.model,ids,self.model['elsets'][self.elset]));return
            self.candidate_faces=sets.candidates(self.model,self.elset,self.mode.currentData())
            self.table.blockSignals(True);self.table.clearSelection();self.table.setRowCount(len(self.candidate_faces))
            for i,f in enumerate(self.candidate_faces):
                for j,v in enumerate((f['element'],f['side'],'내부면' if f['internal'] else '외곽면',format(f['area'],'.6g'))):self.table.setItem(i,j,QTableWidgetItem(str(v)))
            if self._restore_definition and self.definition and self.elset==self.definition['elset'] and self.mode.currentData()==self.definition['mode']:
                chosen=set(map(tuple,self.definition['faces']))
                for i,f in enumerate(self.candidate_faces):
                    if (f['element'],f['side']) in chosen:self.table.selectionModel().select(self.table.model().index(i,0),QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
            self._restore_definition=False;self.table.blockSignals(False)
            self.selection_changed()
            self.message.setText('외곽면이 없습니다. 내부면이 필요하면 요소 면 직접 선택을 사용하세요.' if not self.candidate_faces else '')
        except (ValueError,KeyError,TypeError) as error:self.message.setText(str(error));self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
    def chosen(self):return [self.candidate_faces[i.row()] for i in self.table.selectionModel().selectedRows()]
    def selection_changed(self):
        chosen=self.chosen();ids={n for f in chosen for n in f['nodes']}
        self.view.set_model(self.model,faces=self.all_faces,selected=[(f['element'],f['side']) for f in chosen])
        count=sum(f['internal'] for f in chosen);self.internal.setText(f'선택한 내부면 {count}개를 사용');self.internal.setEnabled(count>0)
        self.info.setText(bounds_label(self.model,ids,{f['element'] for f in chosen},len(chosen)))
    def select_face(self,key):
        for i,f in enumerate(self.candidate_faces):
            if (f['element'],f['side'])==key:
                self.table.selectionModel().select(self.table.model().index(i,0),QItemSelectionModel.SelectionFlag.Toggle|QItemSelectionModel.SelectionFlag.Rows)
                self.table.scrollToItem(self.table.item(i,0));return
    def apply(self):
        try:
            if self.kind=='nset':value=sets.create_node_set(self.settings['source'],self.model,self.name.text(),self.elset)
            else:value=sets.create_surface(self.settings['source'],self.model,self.name.text(),self.elset,self.mode.currentData(),[(f['element'],f['side']) for f in self.chosen()],allow_internal=self.internal.isChecked())
            self.result_definition=value;self.accept()
        except (ValueError,KeyError,TypeError) as error:self.message.setText(str(error))


class ProjectPage(QWidget):
    def __init__(self,editor):
        super().__init__(editor);self.editor=editor;layout=QVBoxLayout(self);split=QSplitter();layout.addWidget(split,1)
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['집합','종류']);self.tree.setMinimumWidth(180);split.addWidget(self.tree)
        right=QWidget();rl=QVBoxLayout(right);self.view=MeshPreview();preview_tools(rl,self.view);rl.addWidget(self.view,1);split.addWidget(right);split.setSizes([260,710]);split.setStretchFactor(1,1)
        self.info=QLabel();self.info.setWordWrap(True);layout.addWidget(self.info)
        row=QHBoxLayout();self.actions={}
        for key,label,call in [('motion','운동 대상 만들기…',lambda:self.create('nset')),('surface','접촉면 만들기…',lambda:self.create('surface')),('edit','집합 수정…',self.edit),('delete','집합 삭제',self.remove),('source','원파일 보기…',self.show_source),('check','입력 확인',self.check)]:
            b=QPushButton(label);b.clicked.connect(call);self.actions[key]=b;row.addWidget(b)
        row.addStretch();layout.addLayout(row);self.message=QLabel();self.message.setWordWrap(True);layout.addWidget(self.message)
        self.tree.currentItemChanged.connect(self.selected);self.refresh()
    def refresh(self):
        self.tree.clear();self.model=None
        try:
            self.model=model_from_settings(self.editor.edited());self.all_faces=sets.facets(self.model)
            generated={(d['kind'],d['name']) for d in self.editor.value.get('generated_sets',[])}
            for kind,table,label in [('elset','elsets','요소 집합'),('nset','nsets','절점 집합'),('surface','surfaces','접촉면')]:
                group=QTreeWidgetItem(self.tree,[label]);group.setExpanded(True)
                for name in self.model[table]:
                    item=QTreeWidgetItem(group,[name,'사용자 생성' if (kind,name) in generated else '원 입력']);item.setData(0,Qt.ItemDataRole.UserRole,(kind,name))
            self.view.set_model(self.model,faces=self.all_faces);self.info.setText(bounds_label(self.model,self.model['nodes'],self.model['elements']))
            self.message.clear()
        except (ValueError,KeyError,TypeError) as error:self.view.model=None;self.view.update();self.info.clear();self.message.setText(str(error))
        self.tree.setColumnWidth(0,190);self.selected()
    def key(self):
        item=self.tree.currentItem();return item.data(0,Qt.ItemDataRole.UserRole) if item else None
    def selected(self,*_):
        key=self.key();generated=self.definition()
        for action in ('motion','surface'):self.actions[action].setEnabled(bool(key and key[0]=='elset'))
        for action in ('edit','delete'):self.actions[action].setEnabled(generated is not None)
        if not key or self.model is None:return
        kind,name=key;elements=set();nodes=set();faces=[]
        if kind=='elset':elements=self.model['elsets'][name];nodes={n for e in elements for n in self.model['elements'][e]['nodes']}
        elif kind=='nset':nodes=self.model['nsets'][name]
        else:
            for target,side in self.model['surfaces'][name]:
                faces.extend((e,side) for e in ([int(target)] if target.isdigit() else self.model['elsets'][target]))
            elements={e for e,s in faces};catalog={(f['element'],f['side']):f for f in self.all_faces};nodes={n for k in faces for n in catalog[k]['nodes']}
        self.view.set_model(self.model,faces=self.all_faces,selected=faces,nodes=nodes if kind!='surface' else ())
        self.info.setText(name+'\n'+bounds_label(self.model,nodes,elements,len(faces)))
    def definition(self):
        key=self.key()
        return next((d for d in self.editor.value.get('generated_sets',[]) if key and (d['kind'],d['name'])==tuple(key)),None)
    def create(self,kind,definition=None):
        key=self.key()
        elset=definition['elset'] if definition else key[1]
        try:dialog=TargetDialog(self.editor.edited(),elset,kind,definition,self)
        except (ValueError,KeyError,TypeError) as error:self.message.setText(str(error));return
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        definitions=deepcopy(self.editor.value.get('generated_sets',[]))
        if definition:definitions[definitions.index(definition)]=dialog.result_definition
        else:definitions.append(dialog.result_definition)
        self.editor.value['generated_sets']=definitions;self.refresh()
    def edit(self):
        definition=self.definition()
        if definition:self.create(definition['kind'],definition)
    def remove(self):
        definition=self.definition()
        if not definition:return
        try:
            settings=self.editor.edited();index=settings['generated_sets'].index(definition)
            updated=sets.delete(settings,index)
            if QMessageBox.question(self,'집합 삭제',definition['name']+' 집합을 삭제할까요?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes:return
            self.editor.value['generated_sets']=updated['generated_sets'];self.refresh()
        except ValueError as error:self.message.setText(str(error))
    def check(self):
        try:
            from caelab.impact_model import render
            frozen=deepcopy(self.editor.edited());deck,_=render(frozen);self.message.setText('입력 확인 완료. 계산은 실행하지 않았습니다.')
            dialog=QDialog(self);dialog.setWindowTitle('실행 입력 확인');dialog.resize(800,600);layout=QVBoxLayout(dialog)
            view=QPlainTextEdit();view.setReadOnly(True);view.setPlainText(deck);layout.addWidget(view)
            row=QHBoxLayout();save=QPushButton('INP 저장…');row.addWidget(save);close=QPushButton('닫기');row.addWidget(close);layout.addLayout(row)
            def export():
                path,_=QFileDialog.getSaveFileName(dialog,'실행 입력 저장','impact.inp','INP (*.inp)')
                if path:
                    try:
                        from caelab.impact_source import export_effective
                        export_effective(frozen,path)
                    except (ValueError,OSError) as error:QMessageBox.warning(dialog,'저장 실패',str(error))
            save.clicked.connect(export);close.clicked.connect(dialog.accept);dialog.exec()
        except (ValueError,KeyError,TypeError) as error:self.message.setText(str(error))
    def show_source(self):
        source=self.editor.value['source'];dialog=QDialog(self);dialog.setWindowTitle('보존 원파일');dialog.resize(800,600);layout=QVBoxLayout(dialog)
        files=QComboBox();view=QPlainTextEdit();view.setReadOnly(True);layout.addWidget(files);layout.addWidget(view,1)
        for item in source.get('bundle',{}).get('files',[]):files.addItem(item['path'],item['text'])
        files.addItem('펼친 입력',source.get('text',''));files.currentIndexChanged.connect(lambda _:view.setPlainText(files.currentData() or ''));view.setPlainText(files.currentData() or '')
        close=QPushButton('닫기');close.clicked.connect(dialog.accept);layout.addWidget(close);dialog.exec()
