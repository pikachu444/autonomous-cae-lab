"""Local imposed-displacement history editor; no Core command or solver owner."""
from copy import deepcopy
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget)

from caelab.impact_interface_history import validate
from caelab.impact_model import model_from_settings
from .appearance import configure_plot_fonts


def _number(text):
    try:
        value = float(text)
        return value if math.isfinite(value) else text
    except (TypeError, ValueError):
        return text


class InterfaceHistoryDialog(QDialog):
    """Return a deep-copied full settings draft only on explicit acceptance."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle('계면 변위 이력')
        self.resize(980, 740)
        self._settings = deepcopy(settings)
        self._loading = False
        self._undo, self._redo = [], []
        self._index = -1
        try:
            self.model = model_from_settings(settings)
            self._model_error = ''
        except (ValueError, KeyError, TypeError, OSError) as error:
            self.model = None
            self._model_error = str(error)

        layout = QVBoxLayout(self)
        title = settings.get('source', {}).get('title') or '원 입력 모델'
        self.context = QLabel(str(title) + ' / 종료 시각 ' + str(settings.get('time', {}).get('end_s', '미지정')) + ' s')
        self.context.setWordWrap(True)
        layout.addWidget(self.context)
        note = QLabel('원 절점 집합에 전역 병진 변위를 부과합니다. 이 표는 실제 계면 벌어짐이나 피로 법칙이 아닙니다.')
        note.setWordWrap(True)
        layout.addWidget(note)
        split = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(split, 1)
        left = QWidget(); left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel('변위 이력'))
        self.histories = QListWidget(); self.histories.setObjectName('interfaceHistories')
        self.histories.setMinimumWidth(145)
        left_layout.addWidget(self.histories, 1)
        left_buttons = QHBoxLayout()
        self.add_history = QPushButton('이력 추가'); self.remove_history = QPushButton('삭제')
        left_buttons.addWidget(self.add_history); left_buttons.addWidget(self.remove_history)
        left_layout.addLayout(left_buttons)
        split.addWidget(left)

        right = QWidget(); right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout(); form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.name = QLineEdit(); self.name.setObjectName('historyName')
        self.name.setPlaceholderText('영문으로 구분할 이름')
        form.addRow('이력 이름', self.name)
        self.material = QComboBox(); self.material.setObjectName('historyMaterial')
        self.node_set = QComboBox(); self.node_set.setObjectName('historyNodeSet')
        self.component = QComboBox(); self.component.setObjectName('historyComponent')
        self.frame = QComboBox(); self.frame.setObjectName('historyFrame')
        for combo in (self.material, self.node_set, self.component, self.frame):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)
        form.addRow('원 응집 재료', self.material)
        form.addRow('원 절점 집합', self.node_set)
        axes = QHBoxLayout(); axes.addWidget(self.component); axes.addWidget(self.frame, 1)
        form.addRow('변위 축 / 기준계', axes)
        right_layout.addLayout(form)
        self.tabs = QTabWidget(); right_layout.addWidget(self.tabs, 1)
        table_page = QWidget(); table_layout = QVBoxLayout(table_page)
        table_layout.setContentsMargins(0, 4, 0, 0)
        self.table = QTableWidget(0, 2); self.table.setObjectName('historyPoints')
        self.table.setHorizontalHeaderLabels(['시간 [s]', '부과 변위 [mm]'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table_layout.addWidget(self.table, 1)
        points = QHBoxLayout()
        self.add_point = QPushButton('행 추가'); self.remove_point = QPushButton('선택 행 삭제')
        points.addWidget(self.add_point); points.addWidget(self.remove_point); points.addStretch()
        table_layout.addLayout(points)
        self.tabs.addTab(table_page, '시간과 변위')
        configure_plot_fonts()
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        self.figure = Figure(figsize=(5, 3), layout='constrained')
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.tabs.addTab(self.canvas, '입력 곡선')
        split.addWidget(right); split.setStretchFactor(0, 0); split.setStretchFactor(1, 1)
        split.setSizes([175, 760])

        self.status = QLabel('이력을 선택하거나 추가하세요. 표를 편집한 뒤 입력을 검토할 수 있습니다.')
        self.status.setObjectName('historyValidation'); self.status.setWordWrap(True)
        layout.addWidget(self.status)
        tools = QHBoxLayout()
        self.undo_action = QAction('되돌리기', self); self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.redo_action = QAction('다시 실행', self); self.redo_action.setShortcuts([QKeySequence.StandardKey.Redo, QKeySequence('Ctrl+Shift+Z')])
        for action, callback in ((self.undo_action, self.undo), (self.redo_action, self.redo)):
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.addAction(action); action.triggered.connect(callback)
            from PySide6.QtWidgets import QToolButton
            button = QToolButton(); button.setDefaultAction(action); tools.addWidget(button)
        self.check_button = QPushButton('입력 검토'); self.check_button.clicked.connect(self.check)
        tools.addWidget(self.check_button); tools.addStretch()
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('초안에 반영')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        tools.addWidget(self.buttons); layout.addLayout(tools)
        self.buttons.accepted.connect(self.accept); self.buttons.rejected.connect(self.reject)
        self.histories.currentRowChanged.connect(self._select)
        self.add_history.clicked.connect(self._add_history); self.remove_history.clicked.connect(self._remove_history)
        self.add_point.clicked.connect(self._add_point); self.remove_point.clicked.connect(self._remove_points)
        self.name.textEdited.connect(self._edited)
        for combo in (self.material, self.node_set, self.component, self.frame):
            combo.currentIndexChanged.connect(self._edited)
        self.table.itemChanged.connect(self._edited)
        self.tabs.currentChanged.connect(lambda index: self._preview() if index == 1 else None)
        self._refresh(0)

    @property
    def draft(self):
        return deepcopy(self._settings)

    def _rows(self):
        value = self._settings.get('interface_histories', [])
        return value if isinstance(value, list) else []

    def _replace(self, rows, index=None):
        value = deepcopy(self._settings); value['interface_histories'] = rows
        if value == self._settings:
            return
        self._undo.append((deepcopy(self._settings), self._index)); self._redo.clear()
        self._settings = value
        if index is not None:
            self._refresh(index)
        else:
            self._actions()
            if 0 <= self._index < self.histories.count():
                self.histories.item(self._index).setText(str(rows[self._index].get('name') or '이름 없는 이력'))
        self.status.setText('편집한 초안입니다. 입력 검토 후 반영하세요.')

    def _actions(self):
        self.undo_action.setEnabled(bool(self._undo)); self.redo_action.setEnabled(bool(self._redo))

    def undo(self):
        if self._undo:
            self._redo.append((deepcopy(self._settings), self._index))
            self._settings, index = self._undo.pop(); self._refresh(index)

    def redo(self):
        if self._redo:
            self._undo.append((deepcopy(self._settings), self._index))
            self._settings, index = self._redo.pop(); self._refresh(index)

    def _refresh(self, index):
        self.histories.blockSignals(True); self.histories.clear()
        for row in self._rows():
            self.histories.addItem(str(row.get('name') or '이름 없는 이력') if isinstance(row, dict) else '수정할 수 없는 이력 — 삭제 후 다시 추가')
        index = min(index, self.histories.count() - 1)
        self.histories.setCurrentRow(index); self.histories.blockSignals(False)
        self._select(index); self._actions()

    def _choices(self, combo, choices, value):
        combo.clear(); combo.addItem('선택하세요', '')
        for label, code in choices:
            combo.addItem(label, code)
        index = combo.findData(value)
        if index < 0:
            combo.addItem(str(value) + ' (원값 확인 필요)', value); index = combo.count() - 1
        combo.setCurrentIndex(index)

    def _select(self, index):
        self._loading = True; self._index = index
        rows = self._rows(); row = rows[index] if 0 <= index < len(rows) else None
        valid = isinstance(row, dict)
        for widget in (self.name, self.material, self.node_set, self.component, self.frame, self.table, self.add_point, self.remove_point):
            widget.setEnabled(valid)
        self.remove_history.setEnabled(index >= 0)
        row = row if valid else {}
        self.name.setText(str(row.get('name', '')))
        materials = []
        if self.model:
            for material in sorted(set(self.model['assignment'].values())):
                elements = [e for e, m in self.model['assignment'].items() if m == material]
                if elements and all(self.model['elements'][e]['type'] == 'COH3D8' for e in elements):
                    materials.append((material, material))
        self._choices(self.material, materials, row.get('material', ''))
        self._choices(self.node_set, [(name + ' (' + str(len(nodes)) + '절점)', name) for name, nodes in sorted((self.model or {}).get('nsets', {}).items())], row.get('node_set', ''))
        self._choices(self.component, [(axis, axis) for axis in 'XYZ'], row.get('component', ''))
        self._choices(self.frame, [('모델 전역 좌표', 'MODEL_GLOBAL')], row.get('frame', ''))
        times, values = row.get('time_s', []), row.get('displacement_mm', [])
        times = times if isinstance(times, list) else [times]
        values = values if isinstance(values, list) else [values]
        self.table.setRowCount(max(len(times), len(values)))
        for i in range(self.table.rowCount()):
            for j, entries in enumerate((times, values)):
                self.table.setItem(i, j, QTableWidgetItem(str(entries[i]) if i < len(entries) else ''))
        self._loading = False
        if self.tabs.currentIndex() == 1:
            self._preview()

    def _edited(self, *args):
        if self._loading or self._index < 0:
            return
        rows = deepcopy(self._rows()); row = rows[self._index]
        if not isinstance(row, dict):
            return
        row.update(name=self.name.text(), material=self.material.currentData(), node_set=self.node_set.currentData(),
            component=self.component.currentData(), frame=self.frame.currentData())
        row['time_s'] = [_number(self.table.item(i, 0).text()) for i in range(self.table.rowCount())]
        row['displacement_mm'] = [_number(self.table.item(i, 1).text()) for i in range(self.table.rowCount())]
        self._replace(rows)

    def _add_history(self):
        rows = deepcopy(self._rows())
        if len(rows) >= 64:
            self.status.setText('이력은 최대 64개까지 추가할 수 있습니다.'); return
        rows.append(dict(name='', material='', node_set='', component='', frame='MODEL_GLOBAL', time_s=['', ''], displacement_mm=['', '']))
        self._replace(rows, len(rows) - 1); self.name.setFocus()

    def _remove_history(self):
        if self._index >= 0:
            rows = deepcopy(self._rows()); rows.pop(self._index); self._replace(rows, max(0, self._index - 1))

    def _add_point(self):
        rows = deepcopy(self._rows()); row = rows[self._index]
        if self.table.rowCount() >= 256:
            self.status.setText('시간·변위 표는 최대 256행입니다.'); return
        at = self.table.currentRow() + 1 if self.table.currentRow() >= 0 else self.table.rowCount()
        # Use the visible paired table, including any missing original counterpart.
        row['time_s'] = [_number(self.table.item(i, 0).text()) for i in range(self.table.rowCount())]
        row['displacement_mm'] = [_number(self.table.item(i, 1).text()) for i in range(self.table.rowCount())]
        row['time_s'].insert(at, ''); row['displacement_mm'].insert(at, '')
        self._replace(rows, self._index); self.table.setCurrentCell(at, 0); self.table.setFocus()

    def _remove_points(self):
        selected = sorted({item.row() for item in self.table.selectedIndexes()}, reverse=True)
        if not selected:
            return
        rows = deepcopy(self._rows()); row = rows[self._index]
        for key, col in (('time_s', 0), ('displacement_mm', 1)):
            values = [_number(self.table.item(i, col).text()) for i in range(self.table.rowCount())]
            for i in selected:
                values.pop(i)
            row[key] = values
        self._replace(rows, self._index)

    def _preview(self):
        self.figure.clear(); axes = self.figure.add_subplot(111)
        row = self._rows()[self._index] if 0 <= self._index < len(self._rows()) else {}
        row = row if isinstance(row, dict) else {}
        times, values = row.get('time_s', []), row.get('displacement_mm', [])
        if isinstance(times, list) and isinstance(values, list) and len(times) == len(values) and times and all(type(v) in (int, float) and math.isfinite(v) for v in times + values):
            axes.plot(times, values, 'o-'); axes.set_title('부과 변위 입력 — ' + str(row.get('component', '')))
        else:
            axes.text(.5, .5, '시간과 변위의 유한한 숫자 쌍을 입력하세요.', ha='center', transform=axes.transAxes)
        axes.set_xlabel('시간 [s]'); axes.set_ylabel('전역 부과 변위 [mm]'); self.canvas.draw_idle()

    def check(self):
        try:
            if self.model is None:
                raise ValueError('원 모델을 읽을 수 없습니다: ' + self._model_error)
            validate(self.model, self._settings)
        except (ValueError, KeyError, TypeError, IndexError) as error:
            # Reuse the same admission helper to locate a broken history. This
            # selects an editor only; the whole-settings verdict above owns admission.
            label = ''
            if self.model is not None:
                for index, row in enumerate(self._rows()):
                    try:
                        validate(self.model, {**self._settings, 'interface_histories': [row]})
                    except (ValueError, KeyError, TypeError, IndexError):
                        self.histories.setCurrentRow(index)
                        label = '이력 ' + str(index + 1) + ' / '
                        break
            self.status.setText(label + '입력 확인: ' + str(error)); self.tabs.setCurrentIndex(0)
            self.table.setFocus()
            return False
        self.status.setText('이력 입력을 확인했습니다. 초안에 반영해도 계산을 시작하지 않습니다.')
        return True

    def accept(self):
        # Commit a focused table delegate before checking the authoritative draft.
        self.check_button.setFocus()
        if self.check():
            super().accept()
