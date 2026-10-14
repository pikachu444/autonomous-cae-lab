"""Edit a uniaxial protocol through the service's existing Pro-authored compiler."""
from copy import deepcopy
import math

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHeaderView, QLabel, QSplitter, QTableWidgetItem, QVBoxLayout)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from .material_editing import MaterialTable


class MaterialControlDialog(QDialog):
    def __init__(self, client, settings, parent=None):
        super().__init__(parent)
        self.client, self.base = client, deepcopy(settings)
        self.result_settings = None
        self._worker = None
        self._cancelled = False
        self.setWindowTitle('단축 시험 조건')
        self.resize(960, 610)
        self.setMinimumSize(680, 460)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        law = '선형 탄성 / 미소변형 Cauchy' if settings['model'] == 'linear_elastic' else 'Neo-Hooke / 제1 Piola'
        form.addRow('재료 및 응력 정의', QLabel(law))
        self.control, self.lateral = QComboBox(), QComboBox()
        for label, value in [('신장비 F11', 'stretch'), ('공학 변형률', 'engineering_strain'), ('축응력', 'stress')]:
            self.control.addItem(label, value)
        for label, value in [('자유 횡변형 (횡응력 0)', 'free'), ('횡변형 고정 (F22 = F33 = 1)', 'fixed'),
                             ('횡방향 신장비 지정', 'prescribed')]:
            self.lateral.addItem(label, value)
        form.addRow('축방향 제어', self.control)
        form.addRow('횡방향 조건', self.lateral)
        layout.addLayout(form)
        split = QSplitter()
        layout.addWidget(split, 1)
        self.table = MaterialTable(len(settings['time']), 4)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        split.addWidget(self.table)
        self.figure = Figure(figsize=(4, 3), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes = self.figure.add_subplot(111)
        split.addWidget(self.canvas)
        split.setSizes([480, 450])
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('시험 조건 설정')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.buttons.accepted.connect(self._compile)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        gradients = settings['deformation_gradient']
        targets = settings.get('boundary_control', {}).get('stress_components', {})
        self._buffers = {
            'stretch': [str(F[0][0]) for F in gradients],
            'engineering_strain': [str(F[0][0] - 1) if isinstance(F[0][0], (int, float)) else str(F[0][0]) for F in gradients],
            'stress': [str(value) for value in targets.get('xx', [0.] * len(gradients))],
        }
        self._current_control = 'stress' if 'xx' in targets else 'stretch'
        self.control.setCurrentIndex(self.control.findData(self._current_control))
        lateral = ('free' if {'yy', 'zz'} <= targets.keys() else
                   'fixed' if all(F[1][1] == F[2][2] == 1 for F in gradients) else 'prescribed')
        self.lateral.setCurrentIndex(self.lateral.findData(lateral))
        for row, (time, F) in enumerate(zip(settings['time'], gradients)):
            for column, value in enumerate((time, self._buffers[self._current_control][row], F[1][1], F[2][2])):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.control.currentIndexChanged.connect(self._control_changed)
        self.lateral.currentIndexChanged.connect(self._visibility)
        self.table.itemChanged.connect(self._draw)
        self.table.editBatchFinished.connect(self._draw)
        self.table.pasteRejected.connect(self.message.setText)
        self._visibility()

    def _commit_editor(self):
        focus = QApplication.focusWidget()
        if focus and self.table.isAncestorOf(focus):
            focus.clearFocus()

    def _control_changed(self):
        self._commit_editor()
        self._buffers[self._current_control] = [self.table.item(row, 1).text() for row in range(self.table.rowCount())]
        self._current_control = self.control.currentData()
        self.table.blockSignals(True)
        for row, text in enumerate(self._buffers[self._current_control]):
            self.table.item(row, 1).setText(text)
        self.table.blockSignals(False)
        self._visibility()

    def _visibility(self):
        label = self.control.currentText()
        unit = self.base['stress_unit'] if self.control.currentData() == 'stress' else '1'
        self.table.setHorizontalHeaderLabels([f"시간 [{self.base['time_unit']}]", f'{label} [{unit}]', 'F22 [1]', 'F33 [1]'])
        prescribed = self.lateral.currentData() == 'prescribed'
        self.table.setColumnHidden(2, not prescribed)
        self.table.setColumnHidden(3, not prescribed)
        for row in range(self.table.rowCount()):
            for column in (2, 3):
                item = self.table.item(row, column)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable if prescribed else item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._draw()

    def _draw(self, *_):
        self.axes.clear()
        try:
            times, values = ([float(self.table.item(row, column).text()) for row in range(self.table.rowCount())] for column in (0, 1))
            if not all(math.isfinite(value) for value in times + values):
                raise ValueError()
            self.axes.plot(times, values, marker='o', markersize=3)
            self.axes.set_xlabel(f"시간 [{self.base['time_unit']}]")
            self.axes.set_ylabel(self.table.horizontalHeaderItem(1).text())
            self.axes.set_title('지정한 하중 이력')
            self.axes.grid(True, alpha=.25)
        except (ValueError, TypeError):
            self.axes.text(.5, .5, '입력 확인 필요', ha='center', va='center', transform=self.axes.transAxes)
        self.canvas.draw()

    def _compile(self):
        if self._worker:
            return
        self._commit_editor()
        from .material_window import _Call, edited_number
        columns = [[edited_number(self.table.item(row, column).text()) for row in range(self.table.rowCount())] for column in range(4)]
        base = deepcopy(self.base)
        base['time'] = columns[0]
        arguments = {'base': base, 'values': columns[1], 'control': self.control.currentData(), 'lateral': self.lateral.currentData()}
        if self.lateral.currentData() == 'prescribed':
            arguments.update(lateral_22=columns[2], lateral_33=columns[3])
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.table.setEnabled(False)
        self.control.setEnabled(False)
        self.lateral.setEnabled(False)
        worker = _Call(lambda: self.client.data_material('material.control.uniaxial_preview', arguments))
        self._worker = worker

        def finished(result, error):
            self._worker = None
            if self._cancelled:
                return
            for widget in (self.table, self.control, self.lateral):
                widget.setEnabled(True)
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
            if error:
                self.message.setText('시험 조건을 확인하세요. ' + error)
            else:
                self.result_settings = result
                self.accept()
        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    def reject(self):
        self._cancelled = True
        super().reject()
