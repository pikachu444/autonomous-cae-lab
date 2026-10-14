"""Clipboard operations for Material's existing typed cell editor."""
import csv
import io

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem


class MaterialTable(QTableWidget):
    editBatchFinished = Signal()
    pasteRejected = Signal(str)

    def copy_selection(self):
        selected = {(index.row(), index.column()) for index in self.selectedIndexes()}
        if not selected:
            return
        rows, columns = zip(*selected)
        output = io.StringIO()
        writer = csv.writer(output, delimiter='\t', lineterminator='\n')
        for row in range(min(rows), max(rows) + 1):
            writer.writerow([self.item(row, col).text() if (row, col) in selected and self.item(row, col)
                             else '' for col in range(min(columns), max(columns) + 1)])
        QApplication.clipboard().setText(output.getvalue().removesuffix('\n'))

    def paste_selection(self):
        if not self.isEnabled() or self.currentRow() < 0:
            return False
        try:
            values = list(csv.reader(io.StringIO(QApplication.clipboard().text()), delimiter='\t', strict=True))
        except csv.Error:
            self.pasteRejected.emit('붙여넣을 표의 따옴표 형식을 확인하세요.')
            return False
        if not values:
            return False
        row, column = self.currentRow(), self.currentColumn()
        edits = [(row + r, column + c, value) for r, line in enumerate(values) for c, value in enumerate(line)]
        for r, c, _ in edits:
            if r >= self.rowCount() or c >= self.columnCount():
                self.pasteRejected.emit('붙여넣을 범위가 표보다 큽니다. 필요한 행을 먼저 추가하세요.')
                return False
            item = self.item(r, c)
            if item is not None and not item.flags() & Qt.ItemFlag.ItemIsEditable:
                self.pasteRejected.emit('계수 이름과 단위는 읽기 전용입니다. 값 열을 선택하세요.')
                return False
        blocked = self.blockSignals(True)
        try:
            for r, c, value in edits:
                if self.item(r, c) is None:
                    self.setItem(r, c, QTableWidgetItem(value))
                else:
                    self.item(r, c).setText(value)
        finally:
            self.blockSignals(blocked)
        self.editBatchFinished.emit()
        return True

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
            event.accept()
        elif event.matches(QKeySequence.StandardKey.Paste):
            self.paste_selection()
            event.accept()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.currentItem() is not None:
            if self.currentItem().flags() & Qt.ItemFlag.ItemIsEditable:
                self.editItem(self.currentItem())
            event.accept()
        else:
            super().keyPressEvent(event)
