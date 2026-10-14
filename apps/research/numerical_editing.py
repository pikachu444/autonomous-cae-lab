"""Clipboard editing for bounded Plan tables; never creates or evaluates a row."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QTableWidget


class PlanTable(QTableWidget):
    pasteRejected = Signal(str)

    def _reject_paste(self, message):
        self.setToolTip(message)
        self.pasteRejected.emit(message)
        return False

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_cells()
            event.accept()
        elif event.matches(QKeySequence.StandardKey.Copy):
            indexes = self.selectedIndexes()
            if indexes:
                rows = sorted({index.row() for index in indexes})
                columns = sorted({index.column() for index in indexes if not self.isColumnHidden(index.column())})
                QApplication.clipboard().setText('\n'.join('\t'.join(
                    self.item(row, column).text() if self.item(row, column) else ''
                    for column in columns) for row in rows))
            event.accept()
        else:
            super().keyPressEvent(event)

    def paste_cells(self):
        if not self.isEnabled() or self.currentRow() < 0:
            return False
        text = QApplication.clipboard().text().replace('\r\n', '\n').replace('\r', '\n')
        if not text:
            return False
        rows = text.removesuffix('\n').split('\n')
        values = [row.split('\t') for row in rows]
        if len({len(row) for row in values}) != 1:
            return self._reject_paste('붙여넣을 행의 열 수를 맞추세요. 입력을 유지했습니다.')
        first = self.currentColumn()
        columns = [column for column in range(first, self.columnCount()) if not self.isColumnHidden(column)]
        if len(values[0]) > len(columns) or self.currentRow() + len(values) > self.rowCount():
            return self._reject_paste('붙여넣을 값이 표의 범위를 벗어납니다. 입력을 유지했습니다.')
        changes = []
        for offset, row in enumerate(values):
            for col, value in zip(columns, row):
                item = self.item(self.currentRow() + offset, col)
                if item is None or not item.flags() & Qt.ItemFlag.ItemIsEditable:
                    return self._reject_paste('선택 범위에 읽기 전용 항목이 있습니다. 편집할 셀부터 선택하세요.')
                changes.append((item, value))
        # Commit the block before updating the typed buffer one bound cell at a time.
        blocked = self.blockSignals(True)
        try:
            for item, value in changes:
                item.setData(Qt.ItemDataRole.UserRole + 1, None)
                item.setText(value)
        finally:
            self.blockSignals(blocked)
        if not blocked:
            for item, _ in changes:
                self.itemChanged.emit(item)
        return True
