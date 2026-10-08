"""Native two-column mapping for external CSV/ASCII response tables.

Parsing is separate from the dialog so the selected-column behavior can be
verified without claiming that an offscreen test exercised the UI.
"""
from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)


DELIMITERS = {"쉼표 (,)": ",", "세미콜론 (;)": ";", "탭": "\t", "파이프 (|)": "|", "공백": "whitespace"}


@dataclass(frozen=True)
class TableMapping:
    points: list[list[float]]
    x_name: str
    x_unit: str
    y_name: str
    y_unit: str
    delimiter: str
    has_header: bool
    x_column: int
    y_column: int


def detect_delimiter(path):
    sample = Path(path).read_text(encoding="utf-8-sig", errors="replace")[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return "whitespace" if sample and any(len(line.split()) >= 2 for line in sample.splitlines()[:4]) else ","


def _split_rows(path, delimiter):
    with open(path, encoding="utf-8-sig", newline="") as file:
        if delimiter == "whitespace":
            rows = [re.split(r"\s+", line.strip()) for line in file if line.strip()]
        else:
            rows = [row for row in csv.reader(file, delimiter=delimiter) if row and any(cell.strip() for cell in row)]
    if not rows:
        raise ValueError("파일이 비어 있습니다")
    return rows


def guess_header(first_row):
    if len(first_row) < 2:
        return True
    try:
        return not all(math.isfinite(float(value)) for value in first_row[:2])
    except ValueError:
        return True


def axis_label(header):
    match = re.match(r"^(.+?)\s*\[([^\]]+)\]\s*$", header.strip())
    return (match.group(1).strip(), match.group(2).strip()) if match else (header.strip(), "—")


def preview_table(path, delimiter, has_header):
    rows = _split_rows(path, delimiter)
    width = max(len(row) for row in rows[:12])
    headers = [rows[0][i].strip() if i < len(rows[0]) else f"열 {i + 1}" for i in range(width)] if has_header else [f"열 {i + 1}" for i in range(width)]
    data = rows[1:] if has_header else rows
    return headers, data[:8], len(data)


def parse_mapping(path, delimiter, has_header, x_column, y_column, x_name, x_unit, y_name, y_unit):
    if delimiter not in (*DELIMITERS.values(),):
        raise ValueError("지원하지 않는 구분자입니다")
    if x_column == y_column or x_column < 0 or y_column < 0:
        raise ValueError("X와 응답은 서로 다른 열을 선택하세요")
    if not all(value.strip() for value in (x_name, x_unit, y_name, y_unit)):
        raise ValueError("축 이름과 단위를 입력하세요. 미정 단위는 '—'로 표시하세요")
    rows = _split_rows(path, delimiter)
    values = rows[1:] if has_header else rows
    points = []
    for number, row in enumerate(values, start=2 if has_header else 1):
        if len(row) <= max(x_column, y_column):
            raise ValueError(f"{number}행에 선택한 열이 없습니다")
        try:
            x, y = float(row[x_column]), float(row[y_column])
        except ValueError as exc:
            raise ValueError(f"{number}행 선택 열은 숫자여야 합니다") from exc
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError(f"{number}행에 NaN/무한대가 있습니다")
        points.append([x, y])
    if len(points) < 2:
        raise ValueError("숫자 데이터가 두 행 이상 필요합니다")
    return TableMapping(points, x_name.strip(), x_unit.strip(), y_name.strip(), y_unit.strip(),
                        delimiter, has_header, x_column, y_column)


class TableMappingDialog(QDialog):
    def __init__(self, parent, path):
        super().__init__(parent)
        self.path = path
        self.result_data = None
        self.setWindowTitle("표 데이터 열·단위 매핑")
        self.resize(680, 530)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(Path(path).name + " · 선택한 X/응답 열만 가져옵니다"))
        controls = QHBoxLayout()
        self.delimiter = QComboBox(); self.delimiter.addItems(DELIMITERS)
        detected = detect_delimiter(path)
        self.delimiter.setCurrentIndex(list(DELIMITERS.values()).index(detected))
        controls.addWidget(QLabel("구분자")); controls.addWidget(self.delimiter)
        self.header = QCheckBox("첫 행은 열 이름")
        self.header.setChecked(guess_header(_split_rows(path, detected)[0]))
        controls.addWidget(self.header); controls.addStretch()
        layout.addLayout(controls)
        self.preview = QTableWidget(); self.preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.preview, 1)
        form = QFormLayout()
        self.x_column = QComboBox(); self.y_column = QComboBox()
        form.addRow("X 열", self.x_column); form.addRow("응답 열", self.y_column)
        self.x_name = QLineEdit(); self.y_name = QLineEdit()
        form.addRow("X 물리량", self.x_name); form.addRow("응답 물리량", self.y_name)
        self.x_unit = QComboBox(); self.y_unit = QComboBox()
        for combo in (self.x_unit, self.y_unit):
            combo.setEditable(True); combo.addItems(["—", "s", "ms", "mm", "m", "N", "kN", "Pa", "MPa", "°C", "%"])
        form.addRow("X 단위", self.x_unit); form.addRow("응답 단위", self.y_unit)
        layout.addLayout(form)
        self.rows_label = QLabel(); layout.addWidget(self.rows_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("매핑 확인·가져오기")
        buttons.accepted.connect(self._accept_mapping); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.delimiter.currentIndexChanged.connect(self._refresh_preview)
        self.header.toggled.connect(self._refresh_preview)
        self.x_column.currentIndexChanged.connect(self._column_changed)
        self.y_column.currentIndexChanged.connect(self._column_changed)
        self._refresh_preview()

    def _refresh_preview(self):
        try:
            headers, rows, count = preview_table(self.path, self._delimiter(), self.header.isChecked())
        except (OSError, ValueError) as exc:
            self.rows_label.setText(f"미리보기 오류: {exc}"); return
        selected_x, selected_y = self.x_column.currentIndex(), self.y_column.currentIndex()
        self.x_column.blockSignals(True); self.y_column.blockSignals(True)
        self.x_column.clear(); self.y_column.clear()
        self.x_column.addItems([f"{i + 1}: {name}" for i, name in enumerate(headers)])
        self.y_column.addItems([f"{i + 1}: {name}" for i, name in enumerate(headers)])
        self.x_column.setCurrentIndex(selected_x if 0 <= selected_x < len(headers) else 0)
        self.y_column.setCurrentIndex(selected_y if 0 <= selected_y < len(headers) else min(1, len(headers) - 1))
        if self.x_column.currentIndex() == self.y_column.currentIndex() and len(headers) > 1:
            self.y_column.setCurrentIndex(1)
        self.x_column.blockSignals(False); self.y_column.blockSignals(False)
        self.preview.setColumnCount(len(headers)); self.preview.setHorizontalHeaderLabels(headers)
        self.preview.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row): self.preview.setItem(i, j, QTableWidgetItem(value))
        self.rows_label.setText(f"미리보기 {len(rows)}행 · 데이터 {count}행")
        self._column_changed()

    def _column_changed(self):
        headers = [self.preview.horizontalHeaderItem(i).text() for i in range(self.preview.columnCount())]
        if not headers: return
        for index, name_edit, unit_combo in ((self.x_column.currentIndex(), self.x_name, self.x_unit),
                                             (self.y_column.currentIndex(), self.y_name, self.y_unit)):
            if 0 <= index < len(headers):
                name, unit = axis_label(headers[index])
                name_edit.setText(name); unit_combo.setCurrentText(unit)

    def _delimiter(self):
        return list(DELIMITERS.values())[self.delimiter.currentIndex()]

    def _accept_mapping(self):
        try:
            self.result_data = parse_mapping(self.path, self._delimiter(), self.header.isChecked(),
                                             self.x_column.currentIndex(), self.y_column.currentIndex(),
                                             self.x_name.text(), self.x_unit.currentText(),
                                             self.y_name.text(), self.y_unit.currentText())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "열 매핑 오류", str(exc)); return
        self.accept()


def map_table_file(parent, path):
    dialog = TableMappingDialog(parent, path)
    return dialog.result_data if dialog.exec() == QDialog.DialogCode.Accepted else None
