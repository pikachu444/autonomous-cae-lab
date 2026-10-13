"""Qt response selection only; native CAD/solver are not started."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6 import QtCore, QtWidgets

from apps.desktop_pre.research_panel import response_dialog


def test_contact_response_choices_units_and_cancel():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    pairs = [{'object_id': 'ContactA', 'draft': {'label': 'Feet / base'}}]
    errors = []
    def choose():
        try:
            dialog = app.activeModalWidget()
            kind = dialog.findChild(QtWidgets.QComboBox, 'responseKind')
            kind.setCurrentIndex(kind.findData('contact_field'))
            field = dialog.findChild(QtWidgets.QComboBox, 'responseField')
            field.setCurrentIndex(field.findData('CPRESS'))
            assert dialog.findChild(QtWidgets.QLabel, 'responseUnit').text() == 'MPa'
            field.setCurrentIndex(field.findData('GeomGap_mm'))
            assert dialog.findChild(QtWidgets.QLabel, 'responseUnit').text() == 'mm'
            dialog.findChild(QtWidgets.QLineEdit, 'responseName').setText('gap_max')
            dialog.findChild(QtWidgets.QComboBox, 'responseFrame').setCurrentIndex(1)
            dialog.findChild(QtWidgets.QSpinBox, 'responseFrameIndex').setValue(9)
            dialog.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Ok).click()
        except BaseException as error:
            errors.append(error); app.activeModalWidget().reject()
    QtCore.QTimer.singleShot(0, choose)
    selected = response_dialog(QtWidgets, pairs)
    assert not errors
    assert selected == {'id': 'gap_max', 'kind': 'contact_field', 'pair_id': 'ContactA',
        'field': 'GeomGap_mm', 'side': 'a', 'unit': 'mm', 'increment': 9, 'reduction': 'max'}
    before = dict(selected)
    QtCore.QTimer.singleShot(0, lambda: app.activeModalWidget().reject())
    assert response_dialog(QtWidgets, pairs, selected) is None
    assert selected == before
