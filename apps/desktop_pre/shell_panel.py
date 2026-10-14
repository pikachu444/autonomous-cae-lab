"""Object-first, native Qt shell panel; Qt binding is injected by FreeCAD.

No web UI. Editor buffers keep literal incomplete numbers until explicitly
saved/applied. Opening/refreshing this panel does not mutate a native model.
"""
from copy import deepcopy
import importlib

from caelab.shell_model import FIELDS, validate_draft

LABELS={'thickness_mm':'두께 (mm)','offset':'기준면 오프셋 / 두께',
        'young_MPa':'탄성계수 (MPa)','poisson':'포아송비',
        'pressure_MPa':'압력 (MPa)','axis_x':'국부 1축 X','axis_y':'국부 1축 Y','axis_z':'국부 1축 Z'}


class DraftBuffer:
    """Pure editor-buffer contract, also used by Save/close regression tests."""
    def __init__(self):
        self.analysis_id=None; self.base={}; self.fields={}

    def read(self, analysis_id, draft):
        self.analysis_id=analysis_id
        self.base={k:deepcopy(draft.get(k,'' if k!='fixed_nodes' else [])) for k in (*FIELDS,'orientation','fixed_nodes')}
        self.fields=deepcopy(self.base)

    def pending_changes(self):
        return self.fields!=self.base

    def snapshot(self):
        return {'analysis_id':self.analysis_id,'fields':deepcopy(self.fields)}

    def acknowledge(self, snapshot):
        if snapshot['analysis_id']!=self.analysis_id: return
        self.base=deepcopy(snapshot['fields'])
        # Do not overwrite a newer edit made while an asynchronous save ran.


def make_panel(W, C, editor, submit):
    G=importlib.import_module(W.__package__+'.QtGui')
    class Panel(W.QWidget):
        def __init__(self):
            super().__init__()
            self.shell_controller=self; self.buffer=DraftBuffer(); self.editor=editor
            self.connection=None; self.shell_actions=None; self.pending_selection=None; self.prepared=None
            self.busy=False; self.loading=False; self.row=None
            self.setObjectName('shellEditor')
            font=self.font();font.setFamily('Malgun Gothic');font.setPointSize(max(9,font.pointSize()));self.setFont(font)
            self.setStyleSheet('''
                QLabel#shellHeading { font-size: 15px; font-weight: bold; }
                QLabel[shellSection="true"] { font-weight: bold; color: #263e58; }
                QTableWidget { alternate-background-color: #f4f7fa; gridline-color: #dbe2e8; }
                QHeaderView::section { padding: 5px; border: none; border-bottom: 1px solid #bdcad6; }
                QLineEdit[invalid="true"] { background: #fff1ef; border: 1px solid #be564a; }
                QPushButton#applyShellProperties { background: #245f9e; color: white; border: 1px solid #245f9e;
                    border-radius: 3px; padding: 5px 12px; }
                QPushButton#applyShellProperties:hover { background: #1d528c; }
                QPushButton#applyShellProperties:pressed { background: #143f6d; }
                QPushButton#applyShellProperties:focus { border: 2px solid #102f4f; padding: 4px 11px; }
                QPushButton#applyShellProperties:disabled { background: #e9eef4; color: #778697; border-color: #c8d2dc; }
            ''')
            layout=W.QVBoxLayout(self); layout.setContentsMargins(10,10,10,10); layout.setSpacing(8)
            self.analysis=W.QComboBox(); self.analysis.setAccessibleName('셸 해석')
            heading=W.QLabel('판재 셸');heading.setObjectName('shellHeading');layout.addWidget(heading);layout.addWidget(self.analysis)
            self.begin_box=W.QWidget(); begin_layout=W.QFormLayout(self.begin_box)
            self.mesh=W.QComboBox(); self.solver=W.QComboBox()
            begin_layout.addRow('메시',self.mesh); begin_layout.addRow('솔버',self.solver)
            self.begin_button=W.QPushButton('선택 모델로 시작'); begin_layout.addRow(self.begin_button)
            self.begin_button.clicked.connect(self.begin); layout.addWidget(self.begin_box)
            self.summary=W.QLabel('해석과 면 메시를 선택하세요.'); self.summary.setWordWrap(True); layout.addWidget(self.summary)
            self.selection=W.QTableWidget(1,3); self.selection.setHorizontalHeaderLabels(['대상','참여 요소','상태'])
            self.selection.setEditTriggers(W.QAbstractItemView.NoEditTriggers)
            self.selection.verticalHeader().hide();self.selection.setShowGrid(False)
            self.selection.horizontalHeader().setSectionResizeMode(0,W.QHeaderView.Stretch)
            for col in (1,2):self.selection.horizontalHeader().setSectionResizeMode(col,W.QHeaderView.ResizeToContents)
            self.selection.setFixedHeight(self.selection.horizontalHeader().sizeHint().height()+36);layout.addWidget(self.selection)
            select_buttons=W.QGridLayout()
            self.face_button=W.QPushButton('선택 면 확인')
            self.elements_button=W.QPushButton('요소 선택…')
            self.accept_selection=W.QPushButton('대상 적용'); self.cancel_selection=W.QPushButton('선택 취소')
            self.face_button.clicked.connect(lambda:self.select_faces())
            self.elements_button.clicked.connect(lambda:self.choose_mesh_ids(False))
            self.accept_selection.clicked.connect(self.accept_target); self.cancel_selection.clicked.connect(self.cancel_target)
            for i,b in enumerate((self.face_button,self.elements_button,self.accept_selection,self.cancel_selection)):
                select_buttons.addWidget(b,i//2,i%2)
            layout.addLayout(select_buttons)
            self.scroll=W.QScrollArea(); self.scroll.setWidgetResizable(True)
            self.scroll.setFrameShape(W.QFrame.NoFrame)
            body=W.QWidget(); form=W.QVBoxLayout(body); form.setContentsMargins(0,0,0,0)
            section=W.QLabel('단면과 하중');section.setProperty('shellSection',True);form.addWidget(section)
            self.properties=W.QTableWidget(len(FIELDS),3)
            self.properties.setHorizontalHeaderLabels(['속성','값','확인'])
            self.properties.verticalHeader().setVisible(False)
            self.properties.setShowGrid(False);self.properties.setWordWrap(True);self.properties.setTextElideMode(C.Qt.ElideNone)
            self.properties.horizontalHeader().setSectionResizeMode(0,W.QHeaderView.ResizeToContents)
            self.properties.horizontalHeader().setSectionResizeMode(1,W.QHeaderView.Fixed)
            self.properties.horizontalHeader().setSectionResizeMode(2,W.QHeaderView.Stretch)
            self.properties.setColumnWidth(1,130)
            self.properties.setMinimumHeight(260)
            self.edits={}
            for i,key in enumerate(FIELDS):
                label=W.QTableWidgetItem(LABELS[key]); label.setFlags(label.flags()&~C.Qt.ItemIsEditable)
                self.properties.setItem(i,0,label)
                edit=W.QLineEdit(); edit.setAccessibleName(LABELS[key]); self.edits[key]=edit
                edit.textEdited.connect(lambda text,key=key:self.changed(key,text))
                self.properties.setCellWidget(i,1,edit)
                item=W.QTableWidgetItem(''); item.setFlags(item.flags()&~C.Qt.ItemIsEditable); self.properties.setItem(i,2,item)
            self.edits['offset'].setToolTip('기준면 위치 / 두께. 위쪽 표면은 (0.5 - Offset) × 두께입니다.')
            self.edits['pressure_MPa'].setToolTip('양수는 +법선과 반대 방향입니다. 단위는 MPa입니다.')
            self.base_tooltips={key:field.toolTip() or field.accessibleName() for key,field in self.edits.items()}
            form.addWidget(self.properties)
            self.direction=W.QLabel('법선 미확정'); self.direction.setWordWrap(True); form.addWidget(self.direction)
            direction_buttons=W.QHBoxLayout()
            self.confirm_normal=W.QPushButton('메시 법선 확인'); self.flip=W.QPushButton('법선 반전')
            self.confirm_normal.clicked.connect(self.confirm_direction); self.flip.clicked.connect(self.reverse_direction)
            direction_buttons.addWidget(self.confirm_normal); direction_buttons.addWidget(self.flip); form.addLayout(direction_buttons)
            self.keep_pressure=W.QCheckBox('반전해도 물리적 압력 방향 유지'); self.keep_pressure.setChecked(True); form.addWidget(self.keep_pressure)
            supports=W.QHBoxLayout()
            self.support=W.QPushButton('고정 절점…');self.support.clicked.connect(lambda:self.choose_mesh_ids(True));supports.addWidget(self.support)
            self.support_count=W.QLabel();self.support_count.setToolTip('추가로 지정한 절점 수입니다. 기존 고정 조건과 함께 적용합니다.')
            supports.addWidget(self.support_count,1);form.addLayout(supports)
            self.repair=W.QPushButton('대상 연결 복구…');self.repair.clicked.connect(self.repair_objects);form.addWidget(self.repair)
            self.scroll.setWidget(body); layout.addWidget(self.scroll,1)
            buttons=W.QGridLayout()
            self.save_button=W.QPushButton('초안 저장'); self.apply_button=W.QPushButton('속성 적용')
            self.apply_button.setObjectName('applyShellProperties')
            self.preview_button=W.QPushButton('두께·방향 보기'); self.reload_button=W.QPushButton('초안 다시 읽기')
            self.save_button.clicked.connect(self.save_document); self.apply_button.clicked.connect(self.apply)
            self.preview_button.clicked.connect(self.preview); self.reload_button.clicked.connect(self.restore)
            for i,b in enumerate((self.preview_button,self.apply_button,self.save_button,self.reload_button)):
                buttons.addWidget(b,i//2,i%2)
            layout.addLayout(buttons)
            calculation=W.QLabel('계산');calculation.setProperty('shellSection',True);layout.addWidget(calculation)
            runbuttons=W.QGridLayout()
            self.prepare_button=W.QPushButton('입력 준비…'); self.run_button=W.QPushButton('계산 실행')
            self.cancel_prepare_button=W.QPushButton('준비 취소'); self.post_button=W.QPushButton('결과 열기')
            self.prepare_button.clicked.connect(lambda:self.action('prepare'))
            self.run_button.clicked.connect(lambda:self.action('run_prepared'))
            self.cancel_prepare_button.clicked.connect(lambda:self.action('cancel_prepare'))
            self.post_button.clicked.connect(lambda:self.action('open_result'))
            for i,b in enumerate((self.prepare_button,self.run_button,self.cancel_prepare_button,self.post_button)):
                runbuttons.addWidget(b,i//2,i%2)
            layout.addLayout(runbuttons)
            self.status=W.QLabel(); self.status.setWordWrap(True); self.status.setAccessibleName('셸 편집 상태'); layout.addWidget(self.status)
            self.analysis.currentIndexChanged.connect(self.change_analysis)
            self.reload()

        def attach(self, connection):
            from .shell_controls import ShellActions
            self.connection=connection; self.shell_actions=ShellActions(connection,self,editor)
            self.update_enabled()

        def pending_changes(self): return self.buffer.pending_changes()

        def set_status(self, text): self.status.setText(str(text))

        def safe(self, fn):
            try: return fn()
            except Exception as error: self.set_status(str(error)); return None

        def _send(self, operation, arguments, on_done=None, on_failure=None):
            if self.busy: raise ValueError('현재 셸 작업의 응답을 먼저 확인하세요.')
            self.busy=True; self.update_enabled()
            def done(value):
                self.busy=False; self.update_enabled()
                if value.get('status')=='FAILED':
                    self.set_status(value.get('error',{}).get('message','작업 실패'))
                    if on_failure: self.safe(lambda:on_failure(value))
                    return
                if on_done: self.safe(lambda:on_done(value))
            try: return submit(operation,arguments,on_done=done)
            except Exception:
                self.busy=False; self.update_enabled(); raise

        def update_enabled(self):
            have=self.row is not None
            self.begin_button.setEnabled(not self.busy)
            self.analysis.setEnabled(not self.busy)
            for b in (self.face_button,self.elements_button,self.save_button,self.apply_button,self.preview_button,
                      self.reload_button,self.support,self.flip,self.confirm_normal,self.repair):
                b.setEnabled(have and not self.busy)
            self.properties.setEnabled(have and not self.busy)
            self.confirm_normal.setEnabled(bool(have and not self.busy and not self.buffer.fields.get('orientation')))
            self.accept_selection.setEnabled(bool(self.pending_selection) and not self.busy)
            self.cancel_selection.setEnabled(bool(self.pending_selection) and not self.busy)
            ready=have and self.row.get('ready') and not self.pending_changes() and not self.busy
            self.prepare_button.setEnabled(bool(ready and self.connection))
            self.run_button.setEnabled(bool(ready and self.prepared and not self.prepared.get('job_id')))
            self.post_button.setEnabled(bool(self.prepared and self.prepared.get('job_id')))
            self.cancel_prepare_button.setEnabled(bool(self.shell_actions and self.shell_actions.preparing))

        def reload(self, value=None, *, selected=None):
            data=value if isinstance(value,dict) and 'analyses' in value else editor.inspect()
            aid=selected or self.buffer.analysis_id or self.analysis.currentData()
            self.loading=True
            for combo,rows in ((self.analysis,data['analyses']),(self.mesh,data['meshes']),(self.solver,data['solvers'])):
                current=combo.currentData(); combo.clear()
                for row in rows: combo.addItem(row['label'],row['id'])
                index=combo.findData(aid if combo is self.analysis else current)
                if index>=0: combo.setCurrentIndex(index)
            # Keep an orphaned saved draft readable/saveable instead of hiding it.
            for row in data['records']:
                if self.analysis.findData(row['analysis_id'])<0:
                    self.analysis.addItem('참조 상실된 해석 (저장 초안)',row['analysis_id'])
            if aid is not None and self.analysis.findData(aid)>=0: self.analysis.setCurrentIndex(self.analysis.findData(aid))
            aid=self.analysis.currentData()
            self.row=next((r for r in data['records'] if r['analysis_id']==aid),None)
            if self.row:
                self.buffer.read(aid,self.row['draft'])
                for key,edit in self.edits.items(): edit.setText(self.buffer.fields[key])
                mesh_label=next((r['label'] for r in data['meshes'] if r['id']==self.row['draft']['mesh_id']),'참조 상실된 메시')
                values=(mesh_label,str(len(self.row['draft'].get('elements',[]))), '적용됨' if self.row['ready'] else '수정 필요')
                for i,text in enumerate(values): self.selection.setItem(0,i,W.QTableWidgetItem(text))
                self.summary.setText(self.analysis.currentText()+' / '+mesh_label)
                self.begin_box.setVisible(False)
            else:
                self.buffer=DraftBuffer(); self.begin_box.setVisible(True); self.selection.clearContents()
                self.summary.setText('해석과 S8 면 메시를 선택하세요.')
            self.loading=False; self.show_errors(); self.update_enabled()

        def changed(self,key,text):
            if self.loading or self.row is None: return
            self.buffer.fields[key]=text; self.prepared=None; self.show_errors(); self.update_enabled()

        def show_errors(self):
            errors=[]
            if self.row:
                draft={**self.row['draft'],**self.buffer.fields}
                errors,_=validate_draft(draft)
                if not self.pending_changes(): errors+=self.row.get('errors',[])
            for i,key in enumerate(FIELDS):
                text='; '.join(dict.fromkeys(e['message'] for e in errors if e['path']==key))
                self.properties.item(i,2).setText('오류: '+text if text else '')
                self.edits[key].setToolTip((text+'\n' if text else '')+self.base_tooltips[key])
                self.edits[key].setProperty('invalid',bool(text))
                self.edits[key].style().unpolish(self.edits[key]);self.edits[key].style().polish(self.edits[key])
                self.properties.item(i,2).setForeground(G.QColor('#9c3128'))
            self.properties.setColumnHidden(2,not any(e['path'] in FIELDS for e in errors))
            self.properties.horizontalHeader().setSectionResizeMode(1,W.QHeaderView.Stretch if self.properties.isColumnHidden(2) else W.QHeaderView.Fixed)
            if not self.properties.isColumnHidden(2):self.properties.setColumnWidth(1,130)
            self.properties.resizeRowsToContents()
            self.support_count.setText('추가 고정 '+str(len(self.buffer.fields.get('fixed_nodes',[])))+'개')
            direction=self.buffer.fields.get('orientation')
            self.direction.setText({'native':'현재 메시 순서의 법선','reversed':'현재 메시 순서와 반대 법선'}.get(direction,'법선 미확정 — 화면에서 확인하세요.'))
            self.confirm_normal.setEnabled(bool(self.row and not direction and not self.busy))
            global_errors=[e['message'] for e in errors if e['path'] not in FIELDS]
            self.set_status('\n'.join(dict.fromkeys(global_errors)) if global_errors else
                            ('미적용 수정이 있습니다.' if self.pending_changes() else ''))

        def change_analysis(self,*_):
            if self.loading: return
            next_id=self.analysis.currentData()
            if self.pending_changes():
                self.loading=True; self.analysis.setCurrentIndex(self.analysis.findData(self.buffer.analysis_id)); self.loading=False
                self.set_status('현재 초안을 저장하거나 저장본을 다시 읽은 뒤 다른 해석을 선택하세요.'); return
            self.prepared=None; self.pending_selection=None; self.safe(lambda:self.reload(selected=next_id))

        def begin(self):
            self.safe(lambda:self._send('pre.shell.begin',{'analysis_id':self.analysis.currentData(),
                'mesh_id':self.mesh.currentData(),'solver_id':self.solver.currentData()},lambda value:self.reload(value)))

        def save_editor_then(self, done):
            """Called by native document Save as well as this panel's buttons."""
            snapshot=self.buffer.snapshot()
            if not snapshot['analysis_id'] or not self.pending_changes(): done(); return None
            def saved(value):
                self.buffer.acknowledge(snapshot)
                if not self.pending_changes(): self.reload(value,selected=snapshot['analysis_id'])
                done()
            return self._send('pre.shell.save_draft',snapshot,saved)

        def save_document(self):
            def save():
                self._send('document.save',{},lambda _:self.set_status('초안을 저장했습니다. 미완성 숫자는 적용되지 않습니다.'))
            self.safe(lambda:self.save_editor_then(save))

        def apply(self):
            aid=self.buffer.analysis_id
            def apply_saved():
                self._send('pre.shell.apply',{'analysis_id':aid},lambda value:self.reload(value,selected=aid))
            self.safe(lambda:self.save_editor_then(apply_saved))

        def preview(self):
            aid=self.buffer.analysis_id
            self.safe(lambda:self.save_editor_then(lambda:self._send('pre.shell.preview',{'analysis_id':aid},
                lambda _:self.set_status('기하 법선 기준의 미리보기입니다. 계산 결과는 두께 방향으로 확장된 절점에서 확인합니다.'))))

        def restore(self):
            if self.pending_changes():
                answer=W.QMessageBox.question(self,'초안 다시 읽기','저장하지 않은 셸 편집을 버리고 저장된 초안을 읽습니까?',
                    W.QMessageBox.Yes|W.QMessageBox.No,W.QMessageBox.No)
                if answer!=W.QMessageBox.Yes: return
            self.prepared=None; self.safe(self.reload)

        def confirm_direction(self):
            if not self.buffer.fields.get('orientation'):
                self.buffer.fields['orientation']='native'; self.prepared=None; self.show_errors(); self.update_enabled()

        def reverse_direction(self):
            aid=self.buffer.analysis_id
            self.safe(lambda:self.save_editor_then(lambda:self._send('pre.shell.reverse',
                {'analysis_id':aid,'keep_physical_load':self.keep_pressure.isChecked()},lambda value:self.reload(value,selected=aid))))

        def select_faces(self):
            aid=self.buffer.analysis_id
            self.safe(lambda:self.save_editor_then(lambda:self._send('pre.shell.preview_rebind',
                {'analysis_id':aid},self.target_previewed)))

        def target_previewed(self,value):
            self.pending_selection=value['token']; self.prepared=None
            self.set_status(f"{value['mesh_label']}: {value['selected_count']}개 요소 미리보기. ‘대상 적용’으로 확정하세요.")
            self.update_enabled()

        def accept_target(self):
            key=self.pending_selection
            def accepted(value): self.pending_selection=None; self.prepared=None; self.reload(value)
            self.safe(lambda:self._send('pre.shell.apply_rebind',{'token':key},accepted))

        def cancel_target(self):
            def cancelled(_): self.pending_selection=None; self.reload()
            self.safe(lambda:self._send('pre.shell.cancel_rebind',{},cancelled))

        def choose_mesh_ids(self,nodes):
            def choose():
                # Native element/node numbers are engineering identities, not internal UUIDs.
                draft=self.row['draft']; meshes=editor.inspect()['meshes']
                if not nodes:
                    picker=W.QDialog(self); picker.setWindowTitle('셸 메시')
                    layout=W.QVBoxLayout(picker); layout.addWidget(W.QLabel('요소를 선택할 메시'))
                    choice=W.QComboBox()
                    for candidate in meshes:
                        choice.addItem(candidate['label'],candidate['id'])
                    selected=choice.findData(draft['mesh_id'])
                    if selected>=0:choice.setCurrentIndex(selected)
                    layout.addWidget(choice)
                    buttons=W.QDialogButtonBox(W.QDialogButtonBox.Ok|W.QDialogButtonBox.Cancel)
                    buttons.accepted.connect(picker.accept); buttons.rejected.connect(picker.reject)
                    layout.addWidget(buttons)
                    if picker.exec()!=W.QDialog.Accepted:return
                    mesh_id=choice.currentData()
                    if not mesh_id:raise ValueError('사용할 수 있는 셸 메시가 없습니다.')
                    draft={**draft,'mesh_id':mesh_id}
                else: mesh_id=draft['mesh_id']
                _,xyz,elements=editor._mesh(draft)
                ids=sorted(xyz if nodes else elements)
                if len(ids)>20000:
                    raise ValueError('표 선택은 20,000개까지입니다. 모델 화면에서 면 또는 메시 전체를 선택하세요.')
                dialog=W.QDialog(self); dialog.setWindowTitle('고정 절점' if nodes else '셸 참여 요소')
                box=W.QVBoxLayout(dialog)
                box.addWidget(W.QLabel('선택 절점은 1–6 자유도를 고정합니다.' if nodes else '계산에 참여할 S8 요소를 선택하세요.'))
                table=W.QTableWidget(len(ids),4); table.setHorizontalHeaderLabels(['절점' if nodes else '요소','X (mm)','Y (mm)','Z (mm)'])
                table.setSelectionBehavior(W.QAbstractItemView.SelectRows); table.setSelectionMode(W.QAbstractItemView.ExtendedSelection)
                table.setEditTriggers(W.QAbstractItemView.NoEditTriggers)
                for i,n in enumerate(ids):
                    point=xyz[n] if nodes else [sum(xyz[j][c] for j in elements[n][:4])/4 for c in range(3)]
                    for j,text in enumerate([str(n),*(format(v,'.8g') for v in point)]): table.setItem(i,j,W.QTableWidgetItem(text))
                selected=set(self.buffer.fields.get('fixed_nodes',[]) if nodes else draft.get('elements',[]) if mesh_id==self.row['draft']['mesh_id'] else [])
                for i,n in enumerate(ids):
                    if n in selected:table.selectionModel().select(table.model().index(i,0),C.QItemSelectionModel.Select|C.QItemSelectionModel.Rows)
                box.addWidget(table,1)
                buttons=W.QDialogButtonBox(W.QDialogButtonBox.Ok|W.QDialogButtonBox.Cancel)
                buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); box.addWidget(buttons)
                dialog.resize(620,480)
                if dialog.exec()!=W.QDialog.Accepted: return
                chosen=[ids[index.row()] for index in table.selectionModel().selectedRows()]
                if nodes:
                    self.buffer.fields['fixed_nodes']=sorted(chosen); self.prepared=None
                    self.show_errors(); self.set_status(str(len(chosen))+'개 추가 고정 절점. 기존 고정 조건과 함께 적용됩니다.'); self.update_enabled()
                else:
                    self.save_editor_then(lambda:self._send('pre.shell.preview_rebind',
                        {'analysis_id':self.buffer.analysis_id,'mesh_id':mesh_id,'elements':sorted(chosen)},self.target_previewed))
            self.safe(choose)

        def repair_objects(self):
            def repair():
                from .shell_edit import native_type
                analysis=editor._object(self.buffer.analysis_id)
                dialog=W.QDialog(self); dialog.setWindowTitle('대상 연결 복구'); form=W.QFormLayout(dialog)
                combos={}
                for key,kind,label in (('solver_id','Fem::SolverCcxTools','솔버'),('material_id','Fem::MaterialCommon','재료'),
                    ('geometry_id','Fem::ElementGeometry2D','단면'),('pressure_id','Fem::ConstraintPressure','압력')):
                    combo=W.QComboBox()
                    if key!='solver_id': combo.addItem('다음 속성 적용 때 새 객체 생성',None)
                    for obj in analysis.Group:
                        if native_type(obj)==kind and not getattr(obj,'Suppressed',False): combo.addItem(obj.Label,obj.Name)
                    index=combo.findData(self.row['draft'].get(key))
                    if index>=0: combo.setCurrentIndex(index)
                    form.addRow(label,combo); combos[key]=combo
                buttons=W.QDialogButtonBox(W.QDialogButtonBox.Ok|W.QDialogButtonBox.Cancel)
                buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
                if dialog.exec()!=W.QDialog.Accepted:return
                objects={key:combo.currentData() for key,combo in combos.items()}
                aid=self.buffer.analysis_id
                self.save_editor_then(lambda:self._send('pre.shell.repair_objects',{'analysis_id':aid,'objects':objects},self.reload))
            self.safe(repair)

        def action(self,name):
            if not self.connection: self.set_status('기존 계산 연결을 확인하세요.'); return
            self.safe(lambda:getattr(self.shell_actions,name)())

    return Panel()
