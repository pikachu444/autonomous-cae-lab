"""Contact DAT scalar controls; the existing ContactDialog remains the owner."""
from copy import deepcopy
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QLabel, QLineEdit,
                              QTableWidget, QTableWidgetItem, QWidget)
from caelab.contact_resultants import IDENTITY, selection


class ResultantControls(QWidget):
    def __init__(self, changed, parent=None):
        super().__init__(parent)
        self._loading = False
        self._changed = changed
        grid = QGridLayout(self)
        self.enabled = QCheckBox('기준점·좌표계를 지정한 합력 / 모멘트')
        self.enabled.setObjectName('contactResultantEnabled')
        grid.addWidget(self.enabled, 0, 0, 1, 3)
        self.response = QComboBox()
        self.response.setObjectName('contactResultantResponse')
        self.response.addItem('A 면 합력', 'force'); self.response.addItem('A 면 합모멘트', 'moment')
        grid.addWidget(self.response, 1, 0)
        self.label = QLineEdit('문서 전체 좌표계'); self.label.setObjectName('contactResultantFrame')
        grid.addWidget(QLabel('좌표계 이름'), 1, 1); grid.addWidget(self.label, 1, 2)
        self.point = QTableWidget(1, 3); self.point.setObjectName('contactMomentReference')
        self.point.setHorizontalHeaderLabels(['문서 X [mm]', '문서 Y [mm]', '문서 Z [mm]'])
        self.point.setVerticalHeaderLabels(['모멘트 기준점'])
        self.point.setMaximumHeight(78); self.point.horizontalHeader().setStretchLastSection(True)
        grid.addWidget(self.point, 2, 0, 1, 3)
        self.basis = QTableWidget(3, 3); self.basis.setObjectName('contactResultantBasis')
        self.basis.setHorizontalHeaderLabels(['문서 X 성분', '문서 Y 성분', '문서 Z 성분'])
        self.basis.setVerticalHeaderLabels(['선택계 X축', '선택계 Y축', '선택계 Z축'])
        self.basis.setMaximumHeight(145); self.basis.horizontalHeader().setStretchLastSection(True)
        grid.addWidget(self.basis, 3, 0, 1, 3)
        note = QLabel('각 행은 문서 좌표로 표시한 단위 축입니다. 오른손 직교 좌표계만 허용합니다. '
                      'DAT는 A면 값이며 B면 힘을 추정하거나 양면을 중복 합산하지 않습니다.')
        note.setWordWrap(True); grid.addWidget(note, 4, 0, 1, 3)
        self.only_frame = QCheckBox('선택한 저장 증분만 측정에 포함 — 보간하지 않음')
        self.only_frame.setObjectName('contactResultantSelectedFrame')
        grid.addWidget(self.only_frame, 5, 0, 1, 3)
        self.load(None)
        self.enabled.toggled.connect(self.change)
        self.only_frame.toggled.connect(self.change)
        self.response.currentIndexChanged.connect(self.change)
        self.label.textChanged.connect(self.change)
        self.point.itemChanged.connect(self.change)
        self.basis.itemChanged.connect(self.change)

    def change(self, *_):
        self.sync(True)
        if not self._loading:
            self._changed()

    def sync(self, idle):
        self.enabled.setEnabled(idle)
        self.only_frame.setEnabled(idle)
        enabled = idle and self.enabled.isChecked()
        for widget in (self.response, self.label, self.point, self.basis):
            widget.setEnabled(enabled)

    def value(self):
        if not self.enabled.isChecked():
            return None
        raw = {'response': self.response.currentData(), 'side': 'a',
               'reference_point_mm': [self.point.item(0, j).text() if self.point.item(0, j) else '' for j in range(3)],
               'basis_rows': [[self.basis.item(i, j).text() if self.basis.item(i, j) else '' for j in range(3)] for i in range(3)],
               'frame_label': self.label.text()}
        try:
            return selection(raw)
        except ValueError:
            # Keep partially typed values. The actual owner returns the specific
            # validation error on Read; no empty or invalid value becomes zero.
            return raw

    def load(self, spec):
        self._loading = True
        try:
            self.enabled.setChecked(spec is not None)
            data = deepcopy(spec) if spec is not None else selection()
            self.response.setCurrentIndex(self.response.findData(data['response']))
            self.label.setText(data['frame_label'])
            for j, value in enumerate(data['reference_point_mm']):
                self.point.setItem(0, j, QTableWidgetItem(str(value)))
            for i, row in enumerate(data['basis_rows']):
                for j, value in enumerate(row):
                    self.basis.setItem(i, j, QTableWidgetItem(str(value)))
        finally:
            self._loading = False
        self.sync(True)
