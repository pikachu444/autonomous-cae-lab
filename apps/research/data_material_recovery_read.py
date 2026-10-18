"""Explicit inspection/resume/discard of existing Pro recovery capsules."""
from copy import deepcopy
from datetime import datetime
from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)


class RecoveryReadDialog(QDialog):
    def __init__(self, client, document, identity, restore_raw, *, current_identity, parent=None):
        super().__init__(parent)
        self.client, self.document = client, deepcopy(document)
        self.identity, self.restore_raw, self.current_identity = deepcopy(identity), restore_raw, current_identity
        self.records = []; self._busy = False; self._worker = None
        self.setWindowTitle('보관한 편집 원문'); self.resize(820, 560)
        layout = QVBoxLayout(self); layout.addWidget(QLabel(document['title']))
        self.capsules = QTableWidget(0, 3)
        self.capsules.setHorizontalHeaderLabels(['보관 시각', '편집 셀 수', '상태'])
        self.capsules.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.capsules.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.capsules.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.capsules.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.capsules)
        self.cells = QTableWidget(0, 2); self.cells.setHorizontalHeaderLabels(['입력 위치', '보관한 원문'])
        self.cells.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.cells.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.cells, 1)
        self.message = QLabel(); self.message.setWordWrap(True); layout.addWidget(self.message)
        row = QHBoxLayout(); layout.addLayout(row)
        self.resume_button, self.discard_button, self.close_button = [QPushButton(text)
            for text in ('이 원문 복구', '보관 원문 삭제…', '닫기')]
        for button in (self.resume_button, self.discard_button, self.close_button): row.addWidget(button)
        self.resume_button.clicked.connect(self.resume); self.discard_button.clicked.connect(self.discard)
        self.close_button.clicked.connect(self.reject)
        self.capsules.itemSelectionChanged.connect(self._selected)
        self._buttons(); QTimer.singleShot(0, self.read)

    def _record(self):
        row = self.capsules.currentRow()
        return self.records[row] if 0 <= row < len(self.records) and self.capsules.selectedItems() else None

    def _buttons(self):
        record = self._record()
        available = not self._busy and record and record['state'] == 'STORED' and record.get('same_store')
        self.resume_button.setEnabled(bool(available)); self.discard_button.setEnabled(bool(available))
        self.close_button.setEnabled(not self._busy)

    def _call(self, operation, arguments, after):
        if self._busy: return False
        from .material_window import _Call
        self._busy = True; self._buttons()
        worker = self._worker = _Call(lambda: self.client.data_material(operation, deepcopy(arguments)))
        def done(value, error):
            self._busy = False; self._worker = None
            if error:
                self.message.setText('보관 원문을 확인하지 못했습니다. 현재 입력과 보관본을 유지합니다.')
                self.message.setToolTip(error)
            else: after(value)
            self._buttons()
        worker.signals.finished.connect(done, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker); return True

    def read(self):
        def loaded(payload):
            self.records = deepcopy(payload['capsules']); self.capsules.setRowCount(len(self.records))
            for row, record in enumerate(self.records):
                capsule = record['capsule']; stamp = capsule.get('created_utc', '')
                try: stamp = datetime.fromisoformat(stamp.replace('Z', '+00:00')).astimezone().strftime('%Y-%m-%d %H:%M')
                except ValueError: stamp = '보관 시각 확인 필요'
                state = '삭제 표시됨' if record['state'] == 'DISCARDED' else '다른 저장소 보관본' if not record.get('same_store') else '원문 보관됨'
                for column, text in enumerate((stamp, str(len(capsule['raw']['cells'])), state)):
                    self.capsules.setItem(row, column, QTableWidgetItem(text))
            if self.records: self.capsules.selectRow(len(self.records) - 1)
            else: self.message.setText('이 문서에 보관한 편집 원문이 없습니다.')
        return self._call('recovery.read', {'document_id': self.document['id']}, loaded)

    def _selected(self):
        record = self._record(); cells = record['capsule']['raw']['cells'] if record else []
        self.cells.setRowCount(len(cells))
        labels = {'mapping': '열 및 단위', 'history': '변형 이력', 'coefficients': '재료 계수'}
        fields = {'budget':'최대 모델 호출', 'count':'표본 수', 'seed':'난수 seed',
                  'penalty':'실패 벌점', 'mode':'연구 방법', 'method':'피팅 알고리즘',
                  'purpose':'계산 목적', 'evaluations':'허용 호출 수'}
        for row, cell in enumerate(cells):
            position = cell.get('position', {})
            location = fields.get(position.get('field'), labels.get(position.get('table'), position.get('table', '입력')))
            if type(position.get('row')) is int: location += ' ' + str(position['row'] + 1) + '행'
            if type(position.get('column')) is int: location += ' ' + str(position['column'] + 1) + '열'
            for column, text in enumerate((location, cell['raw_text'])):
                item = QTableWidgetItem(text); item.setToolTip(text); self.cells.setItem(row, column, item)
        self._buttons()

    def resume(self):
        record = self._record()
        if self._busy or not record or record['state'] != 'STORED' or not record.get('same_store'): return False
        capsule = deepcopy(record['capsule'])
        session_changed = capsule['identity']['session_id'] != self.identity['session_id']
        if session_changed:
            answer = QMessageBox.question(self, '이전 세션 입력 복구', '이전 세션에서 보관한 원문입니다. 같은 기준 문서인지 확인하고 복구할까요?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Yes: return False
        def recovered(result):
            try: live = self.current_identity()
            except (ValueError, RuntimeError): live = None
            if (result.get('state') != 'RESUME_READY' or result.get('identity') != self.identity
                    or live != self.identity or result.get('capsule_sha256') != capsule['capsule_sha256']):
                self.message.setText('기준 문서가 달라 복구하지 않았습니다. 보관한 원문을 확인하고 현재 편집을 유지하세요.'); return
            try: self.restore_raw(deepcopy(result['raw']))
            except (ValueError, RuntimeError, KeyError) as error:
                self.message.setText('현재 편집에 원문을 복구하지 못했습니다. 보관본과 입력은 유지됩니다.'); self.message.setToolTip(str(error)); return
            self.accept()
        return self._call('recovery.recover', {'document_id': self.document['id'], 'capsule_id': capsule['capsule_id'],
            'identity': self.identity, 'acknowledge_session_change': session_changed}, recovered)

    def discard(self):
        record = self._record()
        if self._busy or not record or record['state'] != 'STORED' or not record.get('same_store'): return False
        answer = QMessageBox.question(self, '보관 원문 삭제', '선택한 보관 원문에 삭제 표시를 남깁니다. 계속할까요?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes: return False
        capsule = record['capsule']
        return self._call('recovery.discard', {'document_id': self.document['id'], 'capsule_id': capsule['capsule_id'],
            'identity': self.identity, 'capsule_sha256': capsule['capsule_sha256']}, lambda _: self.read())

    def reject(self):
        if self._busy: return
        super().reject()
