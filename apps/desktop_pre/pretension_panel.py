"""Selected native FEM pretension editor; Qt comes from the existing host."""
from copy import deepcopy
import uuid
import math


def add_pretension_page(panel,W,C):
    from . import pretension_native as native
    def number(text):
        try:
            value=float(text)
            return value if math.isfinite(value) else text
        except ValueError:return text
    class Page(W.QWidget):
        def __init__(self):
            super().__init__();self.info={};self.record=None;self.loaded_analysis=None
            self.modified=False;self.loading=False;self.pending=None;self.faces=[];self.binding=None;self._saved_snapshot=None
            layout=W.QVBoxLayout(self)
            row=W.QHBoxLayout();self.records=W.QComboBox();row.addWidget(self.records,1)
            panel._button('새 체결',self.new,row);layout.addLayout(row)
            self.records.currentIndexChanged.connect(self.choose)
            form=W.QFormLayout();self.label=W.QLineEdit();form.addRow('이름',self.label)
            self.mesh=W.QComboBox();form.addRow('볼트 메시',self.mesh);layout.addLayout(form)
            row=W.QHBoxLayout();panel._button('내부 절단면 선택…',self.select_faces,row)
            panel._button('적용한 절점 강조',self.highlight,row,mutate=False);layout.addLayout(row)
            self.target=W.QLabel('실제 내부 요소면을 선택하세요.');self.target.setWordWrap(True);layout.addWidget(self.target)
            form=W.QFormLayout();axis=W.QWidget();axis_row=W.QHBoxLayout(axis);axis_row.setContentsMargins(0,0,0,0)
            self.axis=[]
            for key in 'XYZ':
                axis_row.addWidget(W.QLabel(key));entry=W.QLineEdit();entry.setMaximumWidth(95);self.axis.append(entry);axis_row.addWidget(entry)
                entry.textChanged.connect(self.mark)
            form.addRow('인장 축',axis)
            self.kind=W.QComboBox();self.kind.addItem('조임력 [N]','force_N');self.kind.addItem('절단면 길이 변화 [mm]','section_displacement_mm')
            self.value=W.QLineEdit();form.addRow('조임 방식',self.kind);form.addRow('조임값',self.value);layout.addLayout(form)
            self.scope=W.QLabel('조임 뒤에는 절단면 길이 변화를 고정하고 외력을 적용합니다. 볼트 전체의 탄성 변형을 고정하는 조건은 아닙니다.')
            self.scope.setWordWrap(True);layout.addWidget(self.scope)
            row=W.QHBoxLayout();panel._button('세 단계 준비…',self.prepare_steps,row)
            panel._button('해석 단계 편집',lambda:panel.tabs.setCurrentWidget(panel.steps_page),row,mutate=False);layout.addLayout(row)
            row=W.QHBoxLayout();panel._button('조건 적용',self.apply,row);panel._button('수정 취소',self.revert,row,mutate=False)
            panel._button('삭제',self.remove,row);layout.addLayout(row)
            row=W.QHBoxLayout();panel._button('요청 다시 확인',self.retry,row,mutate=False);layout.addLayout(row)
            self.state=W.QLabel();self.state.setWordWrap(True);layout.addWidget(self.state);layout.addStretch()
            for obj,signal in ((self.label,'textChanged'),(self.mesh,'currentIndexChanged'),(self.kind,'currentIndexChanged'),(self.value,'textChanged')):
                getattr(obj,signal).connect(self.mark)
            self.mesh.currentIndexChanged.connect(self.mesh_changed)
            panel.tabs.addTab(self,'볼트 체결')
            import weakref
            panel.editor._pretension_page = weakref.ref(self)
            panel.analysis.currentIndexChanged.connect(lambda *_:self.refresh())

        def mark(self,*args):
            if not self.loading:self.modified=True;panel._edited();self.state.setText('미적용 체결 초안입니다.')

        def mesh_changed(self,*args):
            if not self.loading:self.faces=[];self.binding=None;self.target.setText('바꾼 메시의 내부 절단면을 선택하세요.')

        def refresh(self,load_forms=True):
            aid=panel.analysis.currentData()
            if not aid or self.modified or self.pending or (not load_forms and aid==self.loaded_analysis):return
            self.loaded_analysis=aid;self.info=native.read(panel.editor,panel.editor.owner._object(aid))
            current=(self.record or {}).get('id') or (self.info.get('editor') or {}).get('id');self.loading=True
            self.records.clear();self.records.addItem('새 체결 조건',None)
            for row in self.info['sections']:self.records.addItem(row['draft']['label'] or '이름 없는 체결',row['id'])
            stored=self.info.get('editor')
            if stored and self.records.findData(stored['id'])<0:self.records.addItem(stored['draft'].get('label') or '미적용 체결 초안',stored['id'])
            self.mesh.clear()
            for mesh in self.info['meshes']:self.mesh.addItem(mesh['label'],mesh['id'])
            self.records.setCurrentIndex(max(0,self.records.findData(current)));self.loading=False;self.choose()

        def choose(self,*args):
            if self.loading:return
            if self.modified:
                self.loading=True;self.records.setCurrentIndex(max(0,self.records.findData((self.record or {}).get('id'))));self.loading=False
                self.state.setText('현재 초안을 적용하거나 수정 취소한 뒤 다른 체결을 선택하세요.');return
            self.record=next((deepcopy(r) for r in self.info.get('sections',[]) if r['id']==self.records.currentData()),None)
            stored=self.info.get('editor')
            if stored and stored['id']==self.records.currentData():
                self.identifier=stored['id'];self.populate(stored['draft'],stored['mesh_binding'])
                self._saved_snapshot=deepcopy(stored);self.modified=True
                self.state.setText('저장된 미적용 초안입니다. 조건 적용 또는 수정 취소 후 계산하세요.')
            elif self.record:
                self.populate(self.record['draft'],self.record['mesh_binding']);self._saved_snapshot=None
                self.state.setText('; '.join(self.record['errors']) or '적용된 체결 조건입니다.')
            else:self.new()

        def new(self):
            if self.modified or self.pending:raise ValueError('현재 체결 초안과 미확인 요청을 먼저 확인하세요.')
            self.record=None;self.identifier='P'+uuid.uuid4().hex;self._saved_snapshot=None
            self.populate({'label':'새 체결','mesh_id':self.mesh.currentData() or '',
                'element_faces':[],'axis':['','',''],'control':{'kind':'force_N','value':''}},None)
            self.state.setText('원 메시의 내부 면과 인장 축, 조임값을 선택하세요.')

        def populate(self,draft,binding):
            self.loading=True
            self.label.setText(draft['label']);self.mesh.setCurrentIndex(self.mesh.findData(draft['mesh_id']))
            self.faces=deepcopy(draft['element_faces']);self.binding=deepcopy(binding)
            for edit,value in zip(self.axis,draft['axis']):edit.setText(str(value))
            self.kind.setCurrentIndex(self.kind.findData(draft['control']['kind']));self.value.setText(str(draft['control']['value']))
            self.target.setText('내부 요소면 '+str(len(self.faces))+'개 선택됨' if self.faces else '실제 내부 요소면을 선택하세요.')
            self.loading=False;self.modified=False

        def draft(self):
            return {'label':self.label.text(),'mesh_id':self.mesh.currentData(),'element_faces':deepcopy(self.faces),
                'axis':[number(e.text()) for e in self.axis],
                'control':{'kind':self.kind.currentData(),'value':number(self.value.text())}}

        def current_analysis(self):
            if panel.analysis.currentData()!=self.loaded_analysis:raise ValueError('초안을 편집한 원 해석을 다시 선택하세요.')
            return self.loaded_analysis

        def select_faces(self):
            aid=self.current_analysis();mid=self.mesh.currentData()
            if not mid:raise ValueError('현재 해석의 볼트 메시를 선택하세요.')
            dialog=W.QDialog(self);dialog.setWindowTitle('실제 내부 절단면 선택');dialog.resize(900,540)
            layout=W.QVBoxLayout(dialog);table=W.QTableWidget(0,8)
            table.setHorizontalHeaderLabels(['원 요소','면','중심 X [mm]','중심 Y [mm]','중심 Z [mm]','법선 X','법선 Y','법선 Z'])
            table.setSelectionBehavior(W.QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(W.QAbstractItemView.SelectionMode.ExtendedSelection)
            table.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers);layout.addWidget(table,1)
            navigation=W.QHBoxLayout();previous=W.QPushButton('이전');following=W.QPushButton('다음');status=W.QLabel()
            for button in (previous,following):navigation.addWidget(button)
            navigation.addWidget(status,1);layout.addLayout(navigation)
            note=W.QLabel('양쪽 중 인장 축을 향한 한쪽 면을 고르세요. 표시용 평면은 사용하지 않습니다.');note.setWordWrap(True);layout.addWidget(note)
            buttons=W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Ok|W.QDialogButtonBox.StandardButton.Cancel);layout.addWidget(buttons)
            selection={tuple(f) for f in self.faces};page={};selected_axis=None
            def remember():
                visible={tuple(r['element_face']) for r in page.get('faces',[])};selection.difference_update(visible)
                selection.update(tuple(page['faces'][i.row()]['element_face']) for i in table.selectionModel().selectedRows())
            def show(start):
                if page:remember()
                value=native.dispatch(panel.editor,'pre.fem.pretension_faces',{'mesh_id':mid,'start':max(0,start),'count':200},{'object_id':aid})
                if page and value['mesh_binding']!=page['mesh_binding']:raise ValueError('면을 고르는 동안 메시가 바뀌었습니다. 다시 여세요.')
                page.clear();page.update(value);table.setRowCount(len(value['faces']))
                for i,r in enumerate(value['faces']):
                    for j,v in enumerate([r['element_face'][0],'S'+str(r['element_face'][1]),*r['centroid_mm'],*r['normal']]):
                        table.setItem(i,j,W.QTableWidgetItem(format(v,'.8g') if isinstance(v,float) else str(v)))
                    if tuple(r['element_face']) in selection:
                        table.selectionModel().select(table.model().index(i,0),
                            C.QItemSelectionModel.SelectionFlag.Select|C.QItemSelectionModel.SelectionFlag.Rows)
                table.resizeColumnsToContents();previous.setEnabled(value['start']>0);following.setEnabled(value['start']+200<value['total'])
                status.setText(str(value['start']+1 if value['total'] else 0)+'–'+str(value['start']+len(value['faces']))+' / '+str(value['total'])+'면')
                buttons.button(W.QDialogButtonBox.StandardButton.Ok).setEnabled(bool(value['total']))
            previous.clicked.connect(lambda:show(page['start']-200));following.clicked.connect(lambda:show(page['start']+200))
            buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);show(0)
            if dialog.exec()!=W.QDialog.DialogCode.Accepted:return
            remember()
            if not selection:raise ValueError('실제 내부 요소면을 하나 이상 선택하세요.')
            self.faces=[list(f) for f in sorted(selection)];self.binding=deepcopy(page['mesh_binding'])
            # Direction remains explicit: the picked normal is offered, never silently applied.
            first=next((r for r in page['faces'] if tuple(r['element_face']) in selection),None)
            if first and all(not edit.text().strip() for edit in self.axis):
                yes=W.QMessageBox.StandardButton.Yes
                if W.QMessageBox.question(self,'인장 축','선택한 면의 법선을 인장 축으로 사용할까요?',yes|W.QMessageBox.StandardButton.No,W.QMessageBox.StandardButton.No)==yes:
                    for edit,v in zip(self.axis,first['normal']):edit.setText(format(v,'.13g'))
            self.target.setText('내부 요소면 '+str(len(self.faces))+'개 선택됨');self.mark()

        def highlight(self):
            if not self.record or self.modified or self.pending:raise ValueError('현재 체결 조건을 적용하고 요청을 확인한 뒤 강조하세요.')
            panel._send('pre.fem.pretension_highlight',{'id':self.record['id']},self.current_analysis())

        def prepare_steps(self):
            aid=self.current_analysis();info=panel.editor.contact.step_inputs(panel.editor.owner._object(aid))
            yes=W.QMessageBox.StandardButton.Yes
            if W.QMessageBox.question(self,'체결 단계 준비','조임→길이 고정→외력의 세 단계로 바꿀까요? 기존 단계는 문서 이력에 보존됩니다.',yes|W.QMessageBox.StandardButton.Cancel,W.QMessageBox.StandardButton.Cancel)!=yes:return
            from caelab.pretension import three_step_program
            step=info['step_defaults'];draft=three_step_program({'period':step['duration'],**step},info['conditions'])
            panel._send('pre.contact.steps_set',{'draft':draft,'expected_revision':info['revision'],'request_id':uuid.uuid4().hex},aid,
                on_done=lambda _:panel.steps_page.refresh())

        def revert(self):
            if self.pending:raise ValueError('같은 요청의 결과를 먼저 확인하세요.')
            if self.modified:
                yes=W.QMessageBox.StandardButton.Discard
                if W.QMessageBox.question(self,'수정 취소','미적용 체결 초안을 버릴까요?',yes|W.QMessageBox.StandardButton.Cancel,W.QMessageBox.StandardButton.Cancel)!=yes:return
            if self._saved_snapshot is not None:
                from caelab.storage import canonical_hash
                serial=panel._edit_serial;aid=self.current_analysis()
                def discarded(result):
                    self._saved_snapshot=None
                    if panel._edit_serial==serial and panel.analysis.currentData()==aid:
                        self.modified=False;self.refresh()
                    else:self.state.setText('저장된 이전 초안을 취소했습니다. 현재 새 편집은 유지합니다.')
                panel._send('pre.fem.pretension_save_editor',{'editor':None,
                    'expected_editor_sha256':canonical_hash(self._saved_snapshot)},aid,on_done=discarded)
                return
            self.modified=False;self.refresh()

        def editor_snapshot(self):
            return {'id':self.record['id'] if self.record else self.identifier,'draft':self.draft(),
                'mesh_binding':deepcopy(self.binding),'expected_revision':(self.record or {}).get('revision')}

        def pending_changes(self):
            return bool(self.pending or (self.modified and self.editor_snapshot()!=self._saved_snapshot))

        def pending_snapshot(self):
            if self.pending:raise ValueError('체결 조건의 미확인 요청을 먼저 확인하세요. 현재 편집은 유지합니다.')
            return self.editor_snapshot() if self.pending_changes() else None

        def accept_saved_snapshot(self,snapshot,result):
            self._saved_snapshot=deepcopy(snapshot)
            if self.editor_snapshot()==snapshot:
                self.state.setText('편집 초안을 저장했습니다. 계산 전 조건 적용 또는 수정 취소가 필요합니다.')
            else:self.state.setText('이전 편집 초안을 저장했습니다. 현재 새 편집은 유지합니다.')

        def apply(self):
            if self.pending:return self.retry()
            aid=self.current_analysis();args={'id':self.record['id'] if self.record else self.identifier,
                'draft':self.draft(),'mesh_binding':deepcopy(self.binding),'expected_revision':(self.record or {}).get('revision'),'request_id':uuid.uuid4().hex}
            from caelab.storage import canonical_hash
            args['expected_editor_sha256']=canonical_hash(self._saved_snapshot) if self._saved_snapshot is not None else None
            self.pending=('pre.fem.pretension_set',args,aid,panel._edit_serial);self.retry()

        def remove(self):
            if self.pending:raise ValueError('같은 요청을 먼저 확인하세요.')
            if not self.record or self.modified:raise ValueError('적용된 체결을 선택하고 미적용 수정을 먼저 확인하세요.')
            yes=W.QMessageBox.StandardButton.Yes
            if W.QMessageBox.question(self,'체결 삭제','선택한 체결 조건을 삭제할까요?',yes|W.QMessageBox.StandardButton.Cancel,W.QMessageBox.StandardButton.Cancel)!=yes:return
            from caelab.storage import canonical_hash
            self.pending=('pre.fem.pretension_remove',{'id':self.record['id'],'expected_revision':self.record['revision'],
                'expected_editor_sha256':canonical_hash(self._saved_snapshot) if self._saved_snapshot is not None else None,
                'request_id':uuid.uuid4().hex},self.current_analysis(),panel._edit_serial);self.retry()

        def retry(self):
            if not self.pending:raise ValueError('다시 확인할 요청이 없습니다.')
            operation,args,aid,serial=self.pending
            if self.current_analysis()!=aid:raise ValueError('원래 해석을 선택하세요.')
            submitted=deepcopy(args.get('draft'))
            def done(result):
                self.pending=None
                applied=next((r for r in result['state']['sections'] if r['id']==args['id']),None)
                if panel.analysis.currentData()==aid and (self.record is None or self.record['id']==args['id']):
                    self.record=deepcopy(applied);self._saved_snapshot=deepcopy(result['state'].get('editor'))
                if panel.analysis.currentData()==aid and panel._edit_serial==serial and (submitted is None or self.draft()==submitted):
                    self.modified=False;self.record=next((r for r in result['state']['sections'] if r['id']==args['id']),None);self.refresh()
                else:self.state.setText('이전 초안이 적용됐습니다. 현재 수정은 유지합니다. 문서를 다시 읽고 이어서 적용하세요.')
            def failed(error):
                if getattr(error,'native_terminal',False):self.pending=None
                self.state.setText(str(error)+' / 현재 초안 유지')
            panel._send(operation,deepcopy(args),aid,on_done=done,on_error=failed)
    return Page()
