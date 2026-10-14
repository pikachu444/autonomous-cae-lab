"""Named Data/Material selection; row identity is separate from visible names."""
from copy import deepcopy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox,
    QHeaderView, QLineEdit, QTableWidget, QTableWidgetItem, QVBoxLayout)


class DataMaterialDocumentDialog(QDialog):
    def __init__(self, documents, *, kind, parent=None):
        super().__init__(parent)
        self.documents = deepcopy(documents)
        self.selected_document = None
        self.setWindowTitle('재료 열기' if kind == 'material' else '시험 데이터 열기')
        self.resize(780, 440)
        self.setMinimumSize(540, 320)
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText('문서 이름 또는 내용 검색')
        layout.addWidget(self.search)
        self.table = QTableWidget(len(documents), 3)
        self.table.setHorizontalHeaderLabels(['문서', '내용', '저장 상태'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)
        for row, document in enumerate(documents):
            draft = document.get('draft', {})
            if kind == 'material':
                settings = draft.get('settings', {})
                settings = settings if isinstance(settings, dict) else {}
                model_name = settings.get('model')
                model = {'linear_elastic': '선형 탄성', 'neo_hooke': 'Neo-Hooke'}.get(model_name, '재료 모델') if isinstance(model_name, str) else '재료 모델'
                values = settings.get('parameters', {})
                values = values if isinstance(values, dict) else {}
                unit = settings.get('stress_unit')
                unit = unit if isinstance(unit, str) else '단위 확인'
                labels = {'E': 'E', 'nu': 'ν', 'mu': 'μ', 'lmbda': 'λ'}
                coefficients = [f"{labels[name]}={value if type(value) in (str, int, float) else '입력 확인'} "
                                f"[{1 if name == 'nu' else unit}]"
                                for name, value in values.items() if name in labels]
                description = model + (', ' + ', '.join(coefficients) if coefficients else '')
            else:
                mapping = draft.get('mapping', {})
                columns = mapping.get('columns', {}) if isinstance(mapping, dict) else {}
                description = ', '.join(columns) if isinstance(columns, dict) and columns else '열 설정 전'
            state = ('저장하지 않은 변경' if document.get('dirty') else
                     '저장됨' if document.get('saved_revision') is not None else '새 문서')
            for column, text in enumerate((document.get('title', ''), description, state)):
                item = QTableWidgetItem(str(text))
                item.setToolTip(str(text))
                self.table.setItem(row, column, item)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Open).setText('열기')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.buttons.accepted.connect(self._choose)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.table.itemDoubleClicked.connect(lambda *_: self._choose())
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.search.textChanged.connect(self._filter)
        self._selection_changed()

    def _filter(self, text):
        for row in range(self.table.rowCount()):
            visible = any(text.casefold() in self.table.item(row, column).text().casefold() for column in (0, 1))
            self.table.setRowHidden(row, not visible)
        self._selection_changed()

    def _selection_changed(self):
        row = self.table.currentRow()
        self.buttons.button(QDialogButtonBox.StandardButton.Open).setEnabled(
            row >= 0 and bool(self.table.selectedItems()) and not self.table.isRowHidden(row))

    def _choose(self):
        row = self.table.currentRow()
        if row >= 0 and self.table.selectedItems() and not self.table.isRowHidden(row):
            self.selected_document = deepcopy(self.documents[row])
            self.accept()
