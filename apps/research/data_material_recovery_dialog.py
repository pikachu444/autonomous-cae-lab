"""Review raw recovery using the existing Pro API; never apply an owner draft."""
from copy import deepcopy
from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)


class RecoveryKeepDialog(QDialog):
    def __init__(self, client, documents, capture_live, parent=None):
        super().__init__(parent)
        self.client, self.capture_live = client, capture_live
        self.documents = {document['id']: deepcopy(document) for document in documents}
        self.requests = self.preview = self.outcome = self.gate = None
        self.close_ready = self._busy = False
        self._worker = None
        self.setWindowTitle('편집 원문 보관'); self.resize(720, 340)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['문서', '원문 보관 상태', '확인할 내용'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        self.message = QLabel('미확정 입력과 편집 상태를 원문으로 보관합니다.')
        self.message.setWordWrap(True); layout.addWidget(self.message)
        row = QHBoxLayout(); layout.addLayout(row)
        self.review_button = QPushButton('현재 원문 다시 검토')
        self.keep_button = QPushButton('원문 보관')
        self.cancel_button = QPushButton('취소')
        for button in (self.review_button, self.keep_button, self.cancel_button): row.addWidget(button)
        self.review_button.clicked.connect(self.review)
        self.keep_button.clicked.connect(self.keep)
        self.cancel_button.clicked.connect(self.reject)
        self._buttons(); QTimer.singleShot(0, self.review)

    def _call(self, operation, arguments, after):
        if self._busy: return False
        from .material_window import _Call
        self._busy = True; self._buttons()
        worker = self._worker = _Call(lambda: self.client.data_material(operation, deepcopy(arguments)))
        def done(value, error):
            self._busy = False; self._worker = None
            if error:
                self.message.setText('원문 보관을 확인하지 못했습니다. 창과 미확정 입력을 유지합니다.')
                self.message.setToolTip(error)
            else: after(value)
            self._buttons()
        worker.signals.finished.connect(done, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def _buttons(self):
        self.review_button.setEnabled(not self._busy)
        self.cancel_button.setEnabled(not self._busy)
        self.keep_button.setEnabled(not self._busy and bool(self.preview)
            and all(not target.get('problems') for target in self.preview['targets'])
            and (self.gate is None or self.gate.get('close_permitted')))
        self.keep_button.setText('원문 보관 재시도' if self.outcome and not self.outcome.get('all_kept') else '원문 보관')

    def _show(self, targets):
        self.table.setRowCount(len(targets))
        labels = {'STORED': '보관됨', 'FAILED': '보관 실패', 'CONFLICT': '문서 변경됨', 'DISCARDED': '삭제한 보관 입력'}
        for row, target in enumerate(targets):
            identifier = target.get('document_id', target.get('identity', {}).get('document_id'))
            state = labels.get(target.get('state'), '문서 확인 필요' if target.get('problems') else '보관 전')
            detail = '보관 파일과 문서 입력을 확인하세요.' if target.get('error') or target.get('problems') else ''
            for column, text in enumerate((self.documents.get(identifier, {}).get('title', '선택 문서'), state, detail)):
                item = QTableWidgetItem(text)
                item.setToolTip(str(target.get('error') or target.get('problems') or '') if column == 2 else text)
                self.table.setItem(row, column, item)

    def review(self):
        if self._busy: return False
        self.close_ready = False; self.preview = self.outcome = self.gate = None
        try: self.requests = deepcopy(self.capture_live())
        except (ValueError, RuntimeError) as error:
            self.message.setText(str(error)); self._buttons(); return False
        def reviewed(preview):
            self.preview = preview; self._show(preview['targets'])
            if any(target.get('problems') for target in preview['targets']):
                self.message.setText('인정된 문서와 보관 파일을 확인하지 못했습니다. 창과 원문을 유지하세요.')
        return self._call('recovery.prepare', {'requests': self.requests}, reviewed)

    def keep(self):
        if self._busy or self.preview is None: return False
        if not self._live_matches():
            self.message.setText('검토 뒤 입력이 바뀌었습니다. 현재 원문을 다시 검토하세요.'); return False
        def kept(outcome):
            self.outcome = outcome; self._show(outcome['targets'])
            if not outcome.get('all_kept'):
                self.message.setText('일부 원문을 보관하지 못했습니다. 모든 창과 입력을 유지합니다. 원인이 해결되면 같은 검토로 다시 보관하세요.'); return
            try: live = deepcopy(self.capture_live())
            except (ValueError, RuntimeError):
                self.message.setText('원문 창이 바뀌어 닫기를 보류합니다. 현재 편집을 확인하세요.'); return
            def checked(gate):
                self.gate = gate
                if gate.get('close_permitted') and live == self.requests and self._live_matches():
                    self.close_ready = True; self.accept()
                else:
                    self.message.setText('원문 또는 문서가 바뀌어 창을 유지합니다. 현재 입력을 다시 검토하세요.')
            self._call('recovery.close_permitted', {'preview': self.preview, 'live_requests': live}, checked)
        return self._call('recovery.execute', {'preview': self.preview}, kept)

    def is_still_current(self):
        return self.close_ready and self._live_matches()

    def _live_matches(self):
        try: return self.capture_live() == self.requests
        except (ValueError, RuntimeError): return False

    def reject(self):
        if self._busy:
            self.message.setText('원문 보관 결과를 기다리고 있습니다. 입력은 유지됩니다.'); return
        super().reject()
