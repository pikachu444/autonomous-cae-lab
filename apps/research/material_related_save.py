"""Explicit related-save UI over Pro's existing owner coordinator."""
from copy import deepcopy
import uuid
from PySide6.QtCore import Qt, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)


STATES = {'SAVED': '저장됨', 'FAILED': '저장 실패', 'CONFLICT': '문서 변경됨',
    'BLOCKED': '적용 전 입력 있음', 'UNKNOWN': '결과 확인 필요',
    'APPLYING': '결과 확인 필요', 'NOT_STARTED': '저장 전'}


class RelatedSaveDialog(QDialog):
    saveAttempted = Signal(object)

    def __init__(self, client, material, plan, parent=None, *, receipt_id=None,
                 pending_preview=None, allow_writes=True):
        super().__init__(parent)
        from caelab.related_save import input_identity
        self.client = client
        self.documents = {document['id']: deepcopy(document) for document in (material, plan)}
        self.requests = [{'identity': input_identity(document), 'buffer': deepcopy(document['draft'])}
                         for document in (material, plan)]
        self.allow_writes = allow_writes
        self._initial_receipt_id = receipt_id
        self.pending_preview = deepcopy(pending_preview)
        self.preview = (deepcopy(pending_preview) if pending_preview else {'receipt_id': receipt_id}) if receipt_id else None
        self.receipt = None
        self._busy = False; self._worker = None
        self.setWindowTitle('재료와 피팅 계획 저장'); self.resize(760, 370)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['문서', '저장 상태', '확인할 내용'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        self.message = QLabel('적용된 재료와 계획의 입력을 확인합니다.'); self.message.setWordWrap(True)
        layout.addWidget(self.message)
        row = QHBoxLayout(); layout.addLayout(row)
        link_row = QHBoxLayout(); layout.addLayout(link_row)
        self.save_button = QPushButton('두 문서 저장')
        self.retry_button = QPushButton('선택한 실패 문서 재시도')
        self.check_button = QPushButton('결과 다시 확인')
        self.link_button = QPushButton('저장한 재료로 연결')
        self.close_button = QPushButton('닫기')
        for button in (self.save_button, self.retry_button, self.check_button): row.addWidget(button)
        link_row.addWidget(self.link_button); link_row.addStretch(); link_row.addWidget(self.close_button)
        self.save_button.clicked.connect(self.save)
        self.retry_button.clicked.connect(self.retry_selected)
        self.check_button.clicked.connect(self.check)
        self.link_button.clicked.connect(self.publish)
        self.close_button.clicked.connect(self.reject)
        self.table.itemSelectionChanged.connect(self._buttons)
        self._buttons(); QTimer.singleShot(0, self.check if receipt_id else self.review)

    def _call(self, operation, arguments, after):
        if self._busy: return False
        from .material_window import _Call
        self._busy = True; self._buttons()
        worker = self._worker = _Call(lambda: self.client.data_material(operation, deepcopy(arguments)))
        def done(value, error):
            self._busy = False; self._worker = None
            if error:
                self.message.setText('요청 결과를 확인하지 못했습니다. 편집과 원래 계획 참조는 보존됩니다. 결과를 다시 확인하세요.')
                self.message.setToolTip(error)
            else:
                after(value)
            self._buttons()
        worker.signals.finished.connect(done, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def _buttons(self):
        ready = not self._busy
        self.save_button.setEnabled(ready and self.preview is not None and self.receipt is None
                                    and self.allow_writes and self._initial_receipt_id is None
                                    and self.preview.get('saveable_count') == len(self.requests))
        selected = self._selected_failed() if self.receipt else []
        self.retry_button.setEnabled(ready and self.allow_writes and bool(selected))
        self.check_button.setEnabled(ready and self.preview is not None)
        publication = (self.receipt or {}).get('publication', {})
        self.link_button.setEnabled(ready and self.allow_writes and bool((self.receipt or {}).get('all_saved'))
            and publication.get('state') in ('NOT_REQUESTED', 'LINK_SAVE_FAILED'))
        self.link_button.setText('연결 저장 재시도' if publication.get('state') == 'LINK_SAVE_FAILED' else '저장한 재료로 연결')
        self.close_button.setEnabled(ready)

    def _selected_failed(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        targets = (self.receipt or {}).get('targets', [])
        return [targets[row] for row in rows if row < len(targets) and targets[row]['state'] in ('FAILED', 'CONFLICT', 'BLOCKED')]

    def _show(self, targets):
        self.table.setRowCount(len(targets))
        for row, target in enumerate(targets):
            identifier = target['identity']['document_id']
            problems = target.get('preview_problems', [])
            state = target.get('state', 'BLOCKED' if problems else 'NOT_STARTED')
            detail = ('입력을 먼저 적용하세요.' if 'UNAPPLIED_BUFFER' in problems else '원래 입력과 문서가 다릅니다.' if problems else '')
            error = (target.get('attempts') or [{}])[-1].get('error')
            if error: detail = '저장 위치와 연결, 문서 변경을 확인하세요.'
            for column, value in enumerate((self.documents[identifier]['title'], STATES.get(state, '결과 확인 필요'), detail)):
                item = QTableWidgetItem(value)
                item.setToolTip(error.get('message', value) if error and column == 2 else value)
                self.table.setItem(row, column, item)

    def review(self):
        def received(preview):
            self.preview = preview; self._show(preview['targets'])
            self.message.setText('두 문서의 입력을 각각 저장합니다. 계획의 재료 참조는 별도 연결 전까지 유지됩니다.'
                if preview['saveable_count'] == len(self.requests) else '변경된 문서를 확인하고 미적용 입력을 먼저 적용하세요. 편집은 보존됩니다.')
        return self._call('related_save.preview', {'requests': self.requests}, received)

    def _received(self, receipt):
        if ({target['identity']['document_id'] for target in receipt['targets']} != set(self.documents)):
            self.message.setText('이 재료와 계획의 저장 결과가 아닙니다. 원래 문서를 확인하세요.')
            return
        self.receipt = deepcopy(receipt); self._show(receipt['targets'])
        self.requests = [{'identity': deepcopy(target['identity']), 'buffer': deepcopy(target['buffer'])}
                         for target in receipt['targets']]
        state = receipt.get('publication', {}).get('state')
        self.message.setText('저장한 재료와 계획의 연결을 저장했습니다.' if state == 'PUBLISHED' else
            '연결 초안의 저장에 실패했습니다. 이전에 저장한 계획 참조는 보존됩니다.' if state == 'LINK_SAVE_FAILED' else
            '연결 결과를 확인해야 합니다. 결과 다시 확인을 누르세요.' if state in ('UNKNOWN', 'UPDATING', 'SAVING') else
            '두 문서를 저장했습니다. 필요하면 저장한 재료로 계획을 명시적으로 연결하세요.' if receipt.get('all_saved') else
            '저장된 문서는 다시 저장하지 않습니다. 실패 문서를 선택해 재시도하거나 결과를 확인하세요.')

    def save(self):
        if (self._busy or not self.allow_writes or self._initial_receipt_id is not None
                or self.preview is None or self.receipt is not None): return False
        self.pending_preview = deepcopy(self.preview)
        self.saveAttempted.emit(deepcopy(self.pending_preview))
        return self._call('related_save.execute', {'preview': self.preview}, self._received)

    def retry_selected(self):
        targets = self._selected_failed()
        if not self.allow_writes or not targets or self._busy: return False
        selected = {target['identity']['document_id'] for target in targets}
        requests = [request for request in self.requests if request['identity']['document_id'] in selected]
        receipt_id = self.receipt['receipt_id']
        def reviewed(preview):
            if preview['saveable_count'] != len(requests):
                self.message.setText('원래 입력과 문서가 달라 재시도하지 않았습니다. 편집을 확인한 뒤 새로 저장하세요.'); return
            self._call('related_save.retry', {'receipt_id': receipt_id, 'preview': preview}, self._received)
        return self._call('related_save.preview', {'requests': requests}, reviewed)

    def check(self):
        if self._busy or self.preview is None: return False
        operation = ('related_save.reconcile' if (self.receipt or {}).get('publication', {}).get('state')
                     in ('UNKNOWN', 'UPDATING', 'SAVING') else 'related_save.receipt')
        return self._call(operation, {'receipt_id': self.preview['receipt_id']}, self._received)

    def publish(self):
        if self._busy or not self.allow_writes or not self.receipt or not self.receipt.get('all_saved'): return False
        from caelab.related_save import input_identity
        material = next(t for t in self.receipt['targets'] if t['identity']['kind'] == 'material')
        plan = next(t for t in self.receipt['targets'] if t['identity']['kind'] == 'numerical')
        publication = self.receipt.get('publication', {})
        identity = (publication['linked_identity'] if publication.get('state') == 'LINK_SAVE_FAILED'
                    else input_identity(plan['attempts'][-1]['response']['document']))
        return self._call('related_save.publish', {'receipt_id': self.receipt['receipt_id'],
            'material_id': material['identity']['document_id'], 'plan_id': plan['identity']['document_id'],
            'expected_plan': identity, 'command_id': 'C' + uuid.uuid4().hex}, self._received)

    def reject(self):
        if self._busy:
            self.message.setText('저장 결과를 기다리고 있습니다. 원래 입력은 보존됩니다.'); return
        super().reject()
