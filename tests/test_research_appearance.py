"""Readability and native keyboard behavior of the shared research appearance."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QLineEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from apps.research.appearance import apply_appearance


@pytest.fixture
def app():
    application = QApplication.instance() or QApplication([])
    original = (application.style().objectName(), application.font(), application.palette(),
                application.styleSheet(), application.property("caeAppearanceApplied"))
    apply_appearance(application)
    yield application
    application.setStyle(original[0])
    application.setFont(original[1])
    application.setPalette(original[2])
    application.setStyleSheet(original[3])
    application.setProperty("caeAppearanceApplied", original[4])


def contrast(a, b):
    def luminance(color):
        values = [color.redF(), color.greenF(), color.blueF()]
        linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in values]
        return sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))
    first, second = sorted((luminance(a), luminance(b)))
    return (second + .05) / (first + .05)


def test_repeat_apply_preserves_style_and_readable_text(app):
    before = (app.style(), app.font(), app.palette(), app.styleSheet())
    apply_appearance(app)
    assert (app.style(), app.font(), app.palette(), app.styleSheet()) == before
    palette = app.palette()
    for foreground, background in ((QPalette.ColorRole.Text, QPalette.ColorRole.Base),
                                  (QPalette.ColorRole.HighlightedText, QPalette.ColorRole.Highlight),
                                  (QPalette.ColorRole.PlaceholderText, QPalette.ColorRole.Base)):
        assert contrast(palette.color(foreground), palette.color(background)) >= 4.5


def test_styled_controls_keep_keyboard_edit_selection_and_disabled_state(app):
    window = QWidget()
    layout = QVBoxLayout(window)
    edit = QLineEdit("1500 MPa")
    primary = QPushButton("계산 계획")
    primary.setProperty("appearanceRole", "primary")
    checkbox = QCheckBox("선택한 자료 유지")
    disabled = QPushButton("실행 중")
    disabled.setEnabled(False)
    number = QSpinBox()
    number.setRange(1, 4096)
    number.setValue(256)
    table = QTableWidget(2, 2)
    table.setHorizontalHeaderLabels(["자료", "값 [MPa]"])
    table.setItem(0, 0, QTableWidgetItem("인장 시험"))
    table.setItem(1, 0, QTableWidgetItem("횡방향 구속"))
    for widget in (edit, primary, checkbox, disabled, number, table):
        layout.addWidget(widget)
    activated = []
    primary.clicked.connect(lambda: activated.append(True))
    disabled.clicked.connect(lambda: activated.append(False))
    window.show()
    window.activateWindow()
    app.processEvents()
    try:
        edit.setFocus()
        edit.selectAll()
        QTest.keyClicks(edit, "1800 MPa")
        assert edit.text() == "1800 MPa"
        QTest.keyClick(edit, Qt.Key.Key_Tab)
        assert primary.hasFocus()
        QTest.keyClick(primary, Qt.Key.Key_Space)
        assert activated == [True]
        checkbox.setFocus()
        QTest.keyClick(checkbox, Qt.Key.Key_Space)
        assert checkbox.isChecked()
        QTest.mouseClick(disabled, Qt.MouseButton.LeftButton)
        assert activated == [True]
        number.setFocus()
        QTest.keyClick(number, Qt.Key.Key_Up)
        assert number.value() == 257
        table.setCurrentCell(0, 0)
        table.setFocus()
        QTest.keyClick(table, Qt.Key.Key_Down)
        assert table.currentRow() == 1
        assert table.rowHeight(0) <= 32
        assert app.font().pointSizeF() >= 10
    finally:
        window.close()
