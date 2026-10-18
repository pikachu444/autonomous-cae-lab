"""New view of an existing Plan owner; no window/table reparent or second owner."""
from copy import deepcopy
import math
import uuid

from PySide6.QtCore import QEvent, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QHBoxLayout, QLabel,
    QComboBox, QLineEdit, QPushButton, QTableWidgetItem, QVBoxLayout, QWidget)

from caelab.storage import canonical_hash
from .data_window import _Read
from .numerical_editing import PlanTable
from .numerical_methods import choice_label, choice_value
from .numerical_window import number_or_raw
from .request_plan_window import DATA, CHOICE_DATA, _WorksheetDelegate, value_text


class _VariableNumberDelegate(_WorksheetDelegate):
    def displayText(self, value, locale):
        parsed = number_or_raw(str(value))
        return format(parsed, '.6g') if type(parsed) in (int, float) and math.isfinite(parsed) else str(value)


class _VariableTable(PlanTable):
    undoRequested = Signal()
    redoRequested = Signal()

    def paste_cells(self):
        raw=QApplication.clipboard().text()
        accepted=super().paste_cells()
        if accepted:self.raw_paste=dict(raw_text=raw,committed=False,anchor=[self.currentRow(),self.currentColumn()])
        return accepted

    def event(self, event):
        if event.type() == QEvent.Type.ShortcutOverride and (
                event.matches(QKeySequence.StandardKey.Undo) or event.matches(QKeySequence.StandardKey.Redo)):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Undo):
            self.undoRequested.emit();event.accept()
        elif event.matches(QKeySequence.StandardKey.Redo):
            self.redoRequested.emit();event.accept()
        else:super().keyPressEvent(event)


class NumericalPlanVariablesWidget(QWidget):
    """Consume Pro's PlanOwnerAdapter contract. Hosts own review/apply/save."""
    patchPreviewRequested = Signal(object)
    dirtyChanged = Signal(bool)
    ownerActivated = Signal(str)
    activityChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._adapter = self._document = None
        self._variable_labels = {}
        self._history, self._index = [], 0
        self._populating = self._pending_history = self._busy = False
        self._worker = None
        self._serial = 0
        self._dirty = False
        self._history_command = None
        self.owner_history_allowed = lambda: True
        self.destroyed.connect(self._abandon)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.owner_label, self.message = QLabel('계획을 선택하세요.'), QLabel()
        self.owner_label.setWordWrap(True);self.message.setWordWrap(True)
        layout.addWidget(self.owner_label)
        self.table = _VariableTable(0, 7)
        self.table.setHorizontalHeaderLabels(['변수', '단위', '시작값', '하한', '상한', '탐색', '변환'])
        self.table.setItemDelegate(_WorksheetDelegate(self.table))
        self._number_delegate = _VariableNumberDelegate(self.table)
        for column in (2, 3, 4):self.table.setItemDelegateForColumn(column, self._number_delegate)
        self.table.itemChanged.connect(self._edited)
        self.table.pasteRejected.connect(self.message.setText)
        self.table.undoRequested.connect(self.undo)
        self.table.redoRequested.connect(self.redo)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        self.undo_button, self.redo_button = QPushButton('실행 취소'), QPushButton('다시 실행')
        self.preview_button = QPushButton('변경 검토…')
        self.undo_button.clicked.connect(self.undo);self.redo_button.clicked.connect(self.redo)
        self.preview_button.clicked.connect(self.preview_changes)
        for button in (self.undo_button,self.redo_button,self.preview_button):actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions);layout.addWidget(self.message)
        self._buttons()

    @staticmethod
    def _identity(document):
        return (document['id'],document['session_id'],document['generation'],document['input_revision'],
                canonical_hash(document['draft']))

    @staticmethod
    def _public_identity(document):
        return dict(document_id=document['id'],kind=document['kind'],session_id=document['session_id'],
                    generation=document['generation'],input_revision=document['input_revision'],
                    input_sha256=canonical_hash(document['draft']),saved_revision=document.get('saved_revision'))

    def bind_owner(self, adapter, document):
        if self._history_command is not None:
            raise ValueError('앞선 실행 취소 또는 다시 실행 결과를 먼저 확인하세요.')
        if document.get('kind') != 'numerical' or document.get('id') != adapter.document_id:
            raise ValueError('선택한 계획의 연결과 문서가 다릅니다.')
        same = self._document is not None and self._identity(document) == self._identity(self._document)
        same_review=(self._document is not None and self._public_identity(document)==self._public_identity(self._document))
        if self._document is not None and not same_review and self.has_unapplied_buffer():
            raise ValueError('편집 중인 계획을 먼저 적용하거나 실행 취소하세요. 편집을 유지했습니다.')
        if self._busy:
            raise ValueError('계획의 요청 결과를 먼저 확인하세요.')
        self._adapter, self._document = adapter, deepcopy(document)
        self.owner_label.setText(document.get('title') or '계획 변수')
        self.owner_label.setToolTip(document['id'])
        if not same:
            self._history, self._index = [deepcopy(document['draft'])], 0
            self.table.raw_paste=None
            self._show_table(document['draft'])
        self.ownerActivated.emit(document['id'])
        self._update_dirty();self._buttons()

    def reset_view(self, adapter, document):
        """Host explicitly opened or acknowledged this input; abandon the old view."""
        self._abandon()
        self._document = None
        self._history_command = None
        self.bind_owner(adapter, document)

    @staticmethod
    def _variable_path(draft):
        return ('request','inputs','variables') if draft.get('mode') == 'request' else ('variables',)

    @staticmethod
    def _at(draft, path):
        for key in path:draft=draft[key]
        return draft

    def _show_table(self, draft):
        self._populating=True
        try:
            path=self._variable_path(draft)
            try:variables=self._at(draft,path)
            except (KeyError,TypeError):variables=[]
            variables=variables if isinstance(variables,list) else []
            self._shown_variables=deepcopy(variables)
            self.table.setRowCount(len(variables))
            request=draft.get('mode')=='request'
            for row,variable in enumerate(variables):
                if not isinstance(variable,dict):continue
                protected=bool(variable.get('readonly') or variable.get('dependent') or variable.get('dependency'))
                for column,key in enumerate(('id','unit','value','lower','upper','free','transform')):
                    value=variable.get(key,True if key=='free' and request else None)
                    choices=(True,False) if key=='free' else ('linear','log') if key=='transform' else ()
                    shown=choice_label(value,choices) if choices else value_text(value)
                    if key=='id' and isinstance(value,str):shown=self._variable_labels.get(value,shown)
                    editable=column>=2 and not protected and not (request and key=='free')
                    binding=dict(path=path+(row,key) if editable else None,value=deepcopy(value),shown=shown,
                                 numeric=key in ('value','lower','upper'),choices=choices)
                    item=QTableWidgetItem(shown)
                    item.setData(DATA,binding);item.setToolTip(value_text(value))
                    if not editable:item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(row,column,item)
            self.table.resizeColumnsToContents()
        finally:self._populating=False

    def set_variable_labels(self, labels):
        """Host supplies labels for its known physical variables; IDs stay canonical."""
        self._variable_labels={key:value for key,value in labels.items() if isinstance(key,str) and isinstance(value,str)}
        for row in range(self.table.rowCount()):
            item=self.table.item(row,0)
            if item:
                binding=item.data(DATA);identifier=binding['value']
                item.setText(self._variable_labels.get(identifier,value_text(identifier)) if isinstance(identifier,str) else value_text(identifier))
        self.table.resizeColumnToContents(0)

    def _commit_editor(self):
        focus=QApplication.focusWidget()
        if focus and self.isAncestorOf(focus):focus.clearFocus()

    def buffer_snapshot(self):
        return self._buffer_snapshot(commit=True)

    def document_snapshot(self):
        """Return the exact bound receipt without reading or committing an editor."""
        return deepcopy(self._document) if self._adapter is not None else None

    def recovery_ready(self):
        """Allow raw capture only outside unresolved owner/history commands."""
        return bool(self._adapter is not None and self._document is not None
            and not self._busy and self._history_command is None)

    def refresh_saved_metadata(self, document, *, previous_saved_revision):
        """Accept a save receipt for this exact acknowledged input without GUI edits."""
        if not self.recovery_ready():return False
        if not isinstance(document,dict) or not isinstance(document.get('saved_revision'),str) or not document['saved_revision']:
            return False
        if type(document.get('generation')) is not int or type(self._document.get('generation')) is not int:return False
        if self._document.get('saved_revision') not in (previous_saved_revision,document['saved_revision']):return False
        try:
            same=(document['kind']==self._document['kind'] and self._identity(document)==self._identity(self._document)
                  and document['id']==self._adapter.document_id and type(document['dirty']) is bool)
        except (KeyError,TypeError,ValueError):return False
        if not same:return False
        self._document['saved_revision']=document['saved_revision']
        self._document['dirty']=document['dirty']
        return True

    def _live_editor(self):
        if self.table.state()!=QAbstractItemView.State.EditingState:return None
        for kind in (QComboBox,QLineEdit):
            for editor in self.table.findChildren(kind):
                if editor.isVisible():return editor
        return None

    def recovery_snapshot(self):
        """Read exact raw GUI state against the acknowledged owner; never commit."""
        if self._document is None or self._adapter is None:return None
        editor=self._live_editor();active=(self.table.currentRow(),self.table.currentColumn())
        cells=[];focus=None
        for row in range(self.table.rowCount()):
            for column in range(self.table.columnCount()):
                item=self.table.item(row,column);binding=item.data(DATA) if item else None
                if not binding or not binding.get('path'):continue
                path=binding['path'];original=deepcopy(self._at(self._document['draft'],path))
                live=editor is not None and (row,column)==active
                text=editor.currentText() if live and isinstance(editor,QComboBox) else editor.text() if live else item.text()
                if live or text!=binding['shown']:
                    cells.append(dict(field_path=list(path),raw_text=text,original_value=original,
                        original_exists=True,position=dict(table='계획 변수',row=row,column=column),
                        editor_kind='unfinished' if live else 'cell'))
                if live:
                    line=editor.lineEdit() if isinstance(editor,QComboBox) else editor
                    focus=dict(field_path=list(path),cursor=line.cursorPosition() if line is not None else 0,
                        selection_start=line.selectionStart() if line is not None else -1,
                        selection_length=line.selectionLength() if line is not None else 0)
        raw=dict(cells=cells,local_draft=self._buffer_snapshot(),focus=focus,
                 selection=sorted([[index.row(),index.column()] for index in self.table.selectedIndexes()]))
        if getattr(self.table,'raw_paste',None):raw['paste']=deepcopy(self.table.raw_paste)
        raw['editor_revision']='E'+canonical_hash(raw)
        return raw

    def restore_recovery(self, raw):
        """Host validates capsule identity first; restore only this fresh view's fields."""
        if self._adapter is None or self._busy or self.has_unapplied_buffer():
            raise ValueError('현재 계획 편집을 먼저 보관하거나 해결하세요.')
        if not isinstance(raw,dict) or not isinstance(raw.get('cells'),list):
            raise ValueError('보관한 계획 편집 형식을 확인하세요.')
        bound={}
        for row in range(self.table.rowCount()):
            for column in range(self.table.columnCount()):
                item=self.table.item(row,column);binding=item.data(DATA) if item else None
                if binding and binding.get('path'):bound[tuple(binding['path'])]=(item,binding)
        entries=[];pending=[];seen=set()
        for cell in raw['cells']:
            path=tuple(cell.get('field_path',()))
            if path not in bound or path in seen or not isinstance(cell.get('raw_text'),str):
                raise ValueError('보관한 편집이 현재 계획의 편집 가능한 변수와 다릅니다.')
            seen.add(path)
            if canonical_hash(cell.get('original_value'))!=canonical_hash(self._at(self._document['draft'],path)):
                raise ValueError('보관 당시의 계획 값과 현재 값이 다릅니다.')
            entries.append((bound[path][0],cell))
            if cell.get('editor_kind')=='unfinished':pending.append((bound[path][0],cell))
        if len(pending)>1:raise ValueError('보관한 미확정 편집 위치를 확인하세요.')
        if pending and not self.table.isVisible():
            raise ValueError('계획 변수 표를 연 뒤 미확정 편집을 복구하세요.')
        focus=raw.get('focus') or {}
        if pending:
            if not isinstance(focus,dict):raise ValueError('보관한 편집의 커서와 선택 범위를 확인하세요.')
            cell=pending[0][1]
            length=len(cell['raw_text'].encode('utf-16-le',errors='surrogatepass'))//2
            cursor=focus.get('cursor',length)
            start=focus.get('selection_start',-1);selected=focus.get('selection_length',0)
            if (focus.get('field_path',cell['field_path'])!=cell['field_path']
                    or any(type(value) is not int for value in (cursor,start,selected))
                    or not 0<=cursor<=length or selected<0
                    or not (start==-1 and selected==0 or 0<=start<=length and start+selected<=length)
                    or selected and cursor not in (start,start+selected)):
                raise ValueError('보관한 편집의 커서와 선택 범위를 확인하세요.')
        local=raw.get('local_draft',self._document['draft'])
        shown=[];scoped=deepcopy(self._document['draft'])
        for path,(item,binding) in bound.items():
            try:value=self._at(local,path)
            except (KeyError,IndexError,TypeError):raise ValueError('보관한 계획 변수 범위가 다릅니다.') from None
            self._at(scoped,path[:-1])[path[-1]]=deepcopy(value)
            shown.append((item,choice_label(value,binding.get('choices',())) if binding.get('choices') else value_text(value)))
        if canonical_hash(scoped)!=canonical_hash(local):
            raise ValueError('보관한 편집에 이 변수 표가 다루지 않는 변경이 있습니다.')
        self._populating=True
        try:
            for item,text in shown:item.setData(CHOICE_DATA,None);item.setText(text)
            for item,cell in entries:
                if cell.get('editor_kind')!='unfinished':item.setData(CHOICE_DATA,None);item.setText(cell['raw_text'])
            self.table.raw_paste=deepcopy(raw.get('paste'))
        finally:self._populating=False
        self._capture_history()
        if pending:
            item,cell=pending[0];self.table.setCurrentItem(item);self.table.editItem(item)
            editor=self._live_editor()
            if isinstance(editor,QLineEdit):
                editor.setText(cell['raw_text'])
                line=editor
            elif isinstance(editor,QComboBox):
                index=editor.findText(cell['raw_text'])
                if index<0:editor.setEditText(cell['raw_text'])
                else:editor.setCurrentIndex(index)
                line=editor.lineEdit()
            else:line=None
            if line is not None:
                if selected:
                    line.setSelection(start+selected,-selected) if cursor==start else line.setSelection(start,selected)
                else:line.setCursorPosition(cursor)
        self.table.clearSelection()
        for row,column in raw.get('selection',[]):
            item=self.table.item(row,column)
            if item:item.setSelected(True)
        self._buttons();return True

    def _buffer_snapshot(self, *, commit=False):
        if self._document is None:return {}
        if commit:self._commit_editor()
        draft=deepcopy(self._document['draft'])
        path=self._variable_path(draft)
        try:
            target=self._at(draft,path[:-1])
            if isinstance(target.get(path[-1]),list):target[path[-1]]=deepcopy(self._shown_variables)
        except (KeyError,TypeError,AttributeError):pass
        for row in range(self.table.rowCount()):
            for column in range(self.table.columnCount()):
                item=self.table.item(row,column)
                if item is None:continue
                binding=item.data(DATA) or {}
                if not binding.get('path'):continue
                selected=item.data(CHOICE_DATA)
                if isinstance(selected,dict) and selected.get('label')==item.text():value=deepcopy(selected['value'])
                elif item.text()==binding.get('shown'):value=deepcopy(binding['value'])
                else:
                    value=choice_value(item.text(),binding.get('choices',()))
                    if binding.get('numeric') and isinstance(value,str):value=number_or_raw(value)
                    elif binding['path'][-1]=='free' and value in ('true','false'):value=value=='true'
                target=self._at(draft,binding['path'][:-1]);target[binding['path'][-1]]=value
        return draft

    def has_unapplied_buffer(self):
        return bool(self._document and (self._history_command or self.table.state()==QAbstractItemView.State.EditingState or
                    canonical_hash(self._buffer_snapshot())!=canonical_hash(self._document['draft'])))

    def _edited(self, *_):
        if self._populating:return
        if _ and isinstance(_[0], QTableWidgetItem):
            blocked=self.table.blockSignals(True)
            _[0].setToolTip(_[0].text())
            self.table.blockSignals(blocked)
        if not self._pending_history:
            self._pending_history=True;QTimer.singleShot(0,self._capture_history)
        self._update_dirty();self._buttons()

    def _capture_history(self):
        self._pending_history=False
        if self._populating or self._document is None:return
        draft=self._buffer_snapshot()
        if self._history and canonical_hash(draft)==canonical_hash(self._history[self._index]):return
        self._history=self._history[:self._index+1]+[draft];self._index=len(self._history)-1
        self._update_dirty();self._buttons()

    def _update_dirty(self):
        dirty=bool(self._document and canonical_hash(self._buffer_snapshot())!=canonical_hash(self._document['draft']))
        if dirty!=self._dirty:self._dirty=dirty;self.dirtyChanged.emit(dirty)

    def undo(self):
        if self._busy or self._document is None:return
        self._commit_editor()
        self._capture_history()
        if self._index:
            self._index-=1;self._show_table(self._history[self._index]);self._update_dirty();self._buttons()
        elif self._adapter and self._document.get('can_undo') and self.owner_history_allowed():
            self._send_history('undo')

    def redo(self):
        if self._busy:return
        self._commit_editor();self._capture_history()
        if self._index+1<len(self._history):
            self._index+=1;self._show_table(self._history[self._index]);self._update_dirty();self._buttons()
        elif self._adapter and self._document and self._document.get('can_redo') and self.owner_history_allowed() and callable(getattr(self._adapter,'redo',None)):
            self._send_history('redo')

    def _send_history(self, kind):
        pending=self._history_command
        if pending is not None and pending['kind']!=kind:
            self.message.setText('앞선 실행 취소 또는 다시 실행 결과를 먼저 확인하세요.')
            return
        if pending is None:
            pending=self._history_command=dict(kind=kind,adapter=self._adapter,
                document=deepcopy(self._document),command_id='C'+uuid.uuid4().hex)
        def send():
            response=getattr(pending['adapter'],kind)(pending['document'],command_id=pending['command_id'])
            return response,pending['adapter'].read()
        self._call(send,lambda result:self._undo_received(result,redo=kind=='redo'))

    def _undo_received(self, result, *, redo=False):
        response,current=result
        self._history_command=None
        document=response.get('document',response)
        if self._public_identity(document)!=self._public_identity(current):
            self.message.setText('계획이 다른 창에서 변경되었습니다. 편집을 보관한 뒤 계획을 다시 선택하세요.')
            return
        self.bind_owner(self._adapter,document)
        self.message.setText('계획의 적용을 다시 실행했습니다.' if redo else '계획의 마지막 적용을 실행 취소했습니다.')

    def preview_changes(self):
        if self._history_command:
            self.message.setText('앞선 실행 취소 또는 다시 실행 결과를 먼저 확인하세요.')
            return
        if not self._adapter or self._busy or not self.has_unapplied_buffer():return
        base,buffer=deepcopy(self._document),self.buffer_snapshot()
        if canonical_hash(base['draft'])==canonical_hash(buffer):
            self.message.setText('변경할 변수가 없습니다.')
            return
        adapter=self._adapter
        self._call(lambda:adapter.preview(base,buffer),self.patchPreviewRequested.emit)

    def _call(self, function, after):
        if self._busy:return
        self._busy=True;self._buttons()
        serial=self._serial
        worker=self._worker=_Read(function)
        def done(value,error):
            if serial!=self._serial or worker is not self._worker:return
            self._busy=False;self._worker=None
            if error:
                self.message.setText('요청 결과를 확인하지 못했습니다. 편집을 유지했습니다.')
                self.message.setToolTip(str(error))
            else:after(value)
            self._buttons()
        worker.signals.finished.connect(done);QThreadPool.globalInstance().start(worker)

    def show_patch_result(self, outcome):
        if self._document is None:return False
        if self._history_command:
            self.message.setText('앞선 실행 취소 또는 다시 실행 결과를 먼저 확인하세요.')
            return False
        if 'outcomes' in outcome:
            matches=[item for item in outcome['outcomes'] if item.get('document_id')==self._document['id']]
            if len(matches)!=1:raise ValueError('선택한 계획의 처리 결과를 찾을 수 없습니다.')
            outcome=matches[0]
        if outcome.get('document_id')!=self._document['id']:
            raise ValueError('다른 계획의 처리 결과로 편집을 바꾸지 않습니다.')
        editing=self.table.state()==QAbstractItemView.State.EditingState
        buffer=self._buffer_snapshot()
        response=outcome.get('response',{}).get('document')
        current=outcome.get('current_identity')
        acknowledged=(isinstance(response,dict) and response.get('id')==self._document['id'] and
                      response.get('session_id')==self._document['session_id'] and canonical_hash(response.get('draft'))==canonical_hash(buffer))
        current_matches=current==self._public_identity(response) if acknowledged else False
        reviewed=outcome.get('reviewed_identity')==self._public_identity(self._document)
        if (not editing and outcome.get('state')=='APPLIED' and reviewed and
                canonical_hash(outcome.get('reviewed_buffer'))==canonical_hash(buffer) and acknowledged and current_matches):
            self._document=deepcopy(response);self._history=[deepcopy(buffer)];self._index=0
            self.table.raw_paste=None
            self._show_table(buffer);self._update_dirty();self._buttons()
            self.message.setText('변경을 계획에 적용했습니다. 저장은 별도로 실행하세요.')
            return True
        self.message.setText({'CONFLICT':'계획이 변경되었습니다. 현재 편집을 보관한 뒤 다시 검토하세요.',
            'UNKNOWN':'적용 여부를 확인하지 못했습니다. 편집과 검토 결과를 유지하세요.',
            'FAILED':'계획에 적용하지 못했습니다. 편집을 유지했습니다.'}.get(outcome.get('state'),
            '처리 결과와 현재 편집이 다릅니다. 편집을 유지했습니다.'))
        self.message.setToolTip(str(outcome.get('error','')))
        return False

    def detach_owner(self):
        self._commit_editor();self._abandon()
        self.ownerActivated.emit('');self._buttons()

    def _abandon(self, *_):
        self._serial+=1
        if self._worker:self._worker.abandon()
        self._worker=None;self._busy=False;self._adapter=None

    def _buttons(self):
        available=self._adapter is not None and not self._busy
        self.table.setEnabled(available)
        self.preview_button.setEnabled(available)
        self.undo_button.setEnabled(available and (self._index>0 or bool(self._document and self._document.get('can_undo') and self.owner_history_allowed())))
        self.redo_button.setEnabled(available and (self._index+1<len(self._history) or
            bool(self._document and self._document.get('can_redo') and self.owner_history_allowed() and callable(getattr(self._adapter,'redo',None)))))
        pending=self._history_command
        self.undo_button.setText('실행 취소 결과 확인' if pending and pending['kind']=='undo' and self._index==0 else '실행 취소')
        self.redo_button.setText('다시 실행 결과 확인' if pending and pending['kind']=='redo' and self._index+1==len(self._history) else '다시 실행')
        self.activityChanged.emit()
