"""Small Post settings pages; native commands and recipes remain in PostWindow."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFormLayout, QLabel, QSizePolicy, QTabWidget, QWidget


TITLES = ('대상', '정의', '단위', '시각')
UNIT_KEYS = {'quantity','units','measure','frame','coordinate_units','coordinate_frame'}
TIME_KEYS = {'time','reference_time','time_range','time_units','time_origin'}
TARGET_KEYS = {'source_ref','array','association','surface_faces'}


class MessageLabel(QLabel):
    """Keep the visible settings notice in sync with existing message writes."""
    textChanged = Signal(str)

    def setText(self, text):
        super().setText(text)
        self.textChanged.emit(text)


class SettingsPages(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('postSettingsPages')
        self.setDocumentMode(True)
        self.forms = []
        self.widgets = []
        for title in TITLES:
            page = QWidget()
            form = QFormLayout(page)
            form.setContentsMargins(8, 8, 8, 8)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
            self.forms.append(form)
            self.widgets.append(page)
            self.addTab(page, title)

    @staticmethod
    def page_for(key, measurement):
        if key in UNIT_KEYS: return 2
        if key in TIME_KEYS: return 3
        if key in TARGET_KEYS or key == 'point_indices' and measurement in ('point','time'): return 0
        return 1

    def field(self, page, label, widget):
        widget.setMinimumWidth(0)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        name = QLabel(label)
        name.setWordWrap(True)
        name.setBuddy(widget)
        self.forms[page].addRow(name, widget)
        name.show(); widget.show()
        return name

    def row(self, page, widget):
        self.forms[page].addRow(widget)
        widget.show()

    def missing(self, pages):
        for index, values in enumerate(pages):
            self.setTabText(index, TITLES[index] + (' 미정' if values else ''))
            self.setTabToolTip(index, '필요: ' + ', '.join(values) if values else TITLES[index])
