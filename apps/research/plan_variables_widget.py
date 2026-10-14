"""New view of an existing Plan owner; no window/table reparent or second owner."""
from copy import deepcopy
import uuid

from PySide6.QtCore import QEvent, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QHBoxLayout, QLabel,
    QPushButton, QTableWidgetItem, QVBoxLayout, QWidget)

from caelab.storage import canonical_hash
from .data_window import _Read
from .numerical_editing import PlanTable
from .numerical_methods import choice_label, choice_value
from .numerical_window import number_or_raw
from .request_plan_window import DATA, CHOICE_DATA, _WorksheetDelegate, value_text


class _VariableTable(PlanTable):
    undoRequested = Signal()
    redoRequested = Signal()

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._adapter = self._document = None
        self._history, self._index = [], 0
        self._populating = self._pending_history = self._busy = False
        self._worker = None
        self._serial = 0
        self._dirty = False
        self._history_command = None
        self.destroyed.connect(self._abandon)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.owner_label, self.message = QLabel('계획을 선택하세요.'), QLabel()
        self.owner_label.setWordWrap(True);self.message.setWordWrap(True)
        layout.addWidget(self.owner_label)
        self.table = _VariableTable(0, 7)
        self.table.setHorizontalHeaderLabels(['변수', '단위', '시작값', '하한', '상한', '탐색', '변환'])
        self.table.setItemDelegate(_WorksheetDelegate(self.table))
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
            self._show_table(document['draft'])
        self.ownerActivated.emit(document['id'])
        self._update_dirty();self._buttons()

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
            self.table.setRowCount(len(variables))
            request=draft.get('mode')=='request'
            for row,variable in enumerate(variables):
                if not isinstance(variable,dict):continue
                protected=bool(variable.get('readonly') or variable.get('dependent') or variable.get('dependency'))
                for column,key in enumerate(('id','unit','value','lower','upper','free','transform')):
                    value=variable.get(key,True if key=='free' and request else None)
                    choices=(True,False) if key=='free' else ('linear','log') if key=='transform' else ()
                    shown=choice_label(value,choices) if choices else value_text(value)
                    editable=column>=2 and not protected and not (request and key=='free')
                    binding=dict(path=path+(row,key) if editable else None,value=deepcopy(value),shown=shown,
                                 numeric=key in ('value','lower','upper'),choices=choices)
                    item=QTableWidgetItem(shown)
                    item.setData(DATA,binding);item.setToolTip(value_text(value))
                    if not editable:item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(row,column,item)
            self.table.resizeColumnsToContents()
        finally:self._populating=False

    def _commit_editor(self):
        focus=QApplication.focusWidget()
        if focus and self.isAncestorOf(focus):focus.clearFocus()

    def buffer_snapshot(self):
        return self._buffer_snapshot(commit=True)

    def _buffer_snapshot(self, *, commit=False):
        if self._document is None:return {}
        if commit:self._commit_editor()
        draft=deepcopy(self._document['draft'])
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
        elif self._adapter and self._document.get('can_undo'):
            self._send_history('undo')

    def redo(self):
        if self._busy:return
        self._commit_editor();self._capture_history()
        if self._index+1<len(self._history):
            self._index+=1;self._show_table(self._history[self._index]);self._update_dirty();self._buttons()
        elif self._adapter and self._document and self._document.get('can_redo') and callable(getattr(self._adapter,'redo',None)):
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
        self.undo_button.setEnabled(available and (self._index>0 or bool(self._document and self._document.get('can_undo'))))
        self.redo_button.setEnabled(available and (self._index+1<len(self._history) or
            bool(self._document and self._document.get('can_redo') and callable(getattr(self._adapter,'redo',None)))))
        pending=self._history_command
        self.undo_button.setText('실행 취소 결과 확인' if pending and pending['kind']=='undo' and self._index==0 else '실행 취소')
        self.redo_button.setText('다시 실행 결과 확인' if pending and pending['kind']=='redo' and self._index+1==len(self._history) else '다시 실행')
