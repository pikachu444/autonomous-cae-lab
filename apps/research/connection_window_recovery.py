"""Explicit kept-Q chooser for the existing connection copy workflow."""
from copy import deepcopy
from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView,
    QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout)

STATE = {'STORED':'보관 원문', 'DISCARDED':'삭제 표시된 원문', 'BLOCKED':'보존 자료 확인 필요'}
KIND = {'data':'측정 자료', 'material':'재료', 'numerical':'계획'}


def stamp(value):
    try:
        return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone().strftime('%Y-%m-%d %H:%M')
    except (ValueError, AttributeError):
        return '시각 미기록'


class RecoverySelectionDialog(QDialog):
    def __init__(self, payload, parent=None):
        super().__init__(parent)
        self.records = deepcopy(payload['archives'])
        self.setWindowTitle('함께 옮길 보관 원문 선택'); self.resize(880, 440)
        layout = QVBoxLayout(self)
        note = QLabel('이미 보관한 편집 원문만 직접 선택합니다. 새 셀 입력을 자동 적용·보관하지 않습니다.\n'
            '목록에 없는 미확정 입력은 원 편집기의 「편집 원문 보관」을 먼저 사용하세요.\n'
            '저장본·당시 반영 문서·원문·관련 저장 기록을 함께 옮기며 원 저장소의 복구·삭제 권한은 옮기지 않습니다.')
        note.setWordWrap(True); layout.addWidget(note)
        self.table = QTableWidget(len(self.records),5)
        self.table.setHorizontalHeaderLabels(['포함할 문서','종류','보관 시각','미확정 셀','상태'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        for column in range(1, 5):
            self.table.horizontalHeader().setSectionResizeMode(column,QHeaderView.ResizeMode.ResizeToContents)
        for index, record in enumerate(self.records):
            label = STATE.get(record['state'],'원문 확인 필요')
            if record.get('verification') == 'LEGACY_BASE_NOT_RETAINED': label += ' / 당시 문서 없음'
            if record.get('source') == 'CARRIED_ORIGINAL': label += ' / 이전 사본의 원본'
            values = (record['title'],KIND.get(record['kind'],'문서'),stamp(record.get('created_utc')),
                      str(record.get('raw_cells','')), label)
            for col,value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(record.get('message') or value)
                if col == 0:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Unchecked)
                    if not record['selectable']: item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                self.table.setItem(index,col,item)
        layout.addWidget(self.table,1)
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.table.currentCellChanged.connect(self._explain)
        if self.records:
            self.table.setCurrentCell(0, 0)
            self._explain(0)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('선택한 보관본으로 복사 검토')
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty('appearanceRole','primary')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def _explain(self, row, *_):
        record = self.records[row] if 0 <= row < len(self.records) else {}
        self.message.setText(record.get('message', ''))

    def selections(self):
        return [deepcopy(record['selection']) for index,record in enumerate(self.records)
                if record['selectable'] and self.table.item(index,0).checkState()==Qt.CheckState.Checked]


def prepare_copy(window, chosen):
    chosen = list(chosen)
    def received(payload):
        if window.checked_documents() != chosen:
            window.message.setText('문서 선택이 바뀌었습니다. 현재 선택으로 다시 검토하세요.'); return
        selector = RecoverySelectionDialog(payload, window)
        if selector.exec()!=QDialog.DialogCode.Accepted: return
        archives = selector.selections()
        window._call(lambda:window.client.portable_inspect(chosen,recovery_archives=archives),window._review_copy)
    window._call(lambda:window.client.portable_recovery_catalog(chosen),received)
