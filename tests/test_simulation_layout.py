"""Simulation display/edit boundaries; no solver or provider is launched."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import time
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QCloseEvent, QFontDatabase
from PySide6.QtTest import QTest
from apps.research.simulation_window import SimulationWindow, MODELS
from caelab.simulation_document import SimulationDocuments, default_draft


class Client:
    def __init__(self, root):
        def forbidden(*args, **kwargs): raise AssertionError('No native execution in layout checks')
        class Jobs:
            def list(self): return []
        self.owner = SimulationDocuments(root, 'S-layout', forbidden, Jobs())

    def document_open(self, **options):
        assert options.pop('kind') == 'simulation'
        return self.owner.open(**options)

    def document_read(self, identifier): return self.owner.read(identifier)

    def document_command(self, identifier, operation, arguments, **options):
        return self.owner.command(identifier, operation, arguments, **options)

    def documents(self): return self.owner.list()


@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    for name in ('segoeui.ttf', 'malgun.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + name)
    win = SimulationWindow(Client(tmp_path), auto_open=False, poll_interval=0)
    win._opened(win.client.document_open(kind='simulation', title='공개 J2', draft=default_draft()))
    win.show(); app.processEvents()
    yield win, app
    deadline = time.monotonic() + 5
    while win._busy and time.monotonic() < deadline: app.processEvents(); time.sleep(.01)
    win._allow_close = True; win.close(); app.processEvents()


def test_human_model_and_case_labels_keep_exact_values(window):
    win, app = window
    original = deepcopy(win.edited_draft())
    assert win.apply_button.isVisible() and win.evaluate_button.isVisible()
    raw = original['backend']
    assert win.backend.currentText() == raw
    assert win.backend.itemText(win.backend.currentIndex()) == MODELS[raw][0]
    assert win.fields[('settings', 'case')][0].text() == original['settings']['case']
    assert win.edited_draft() == original
    win.backend.lineEdit().selectAll()
    QTest.keyClicks(win.backend.lineEdit(), 'unsupported.future')
    assert win.edited_draft()['backend'] == 'unsupported.future'
    assert win.edited_draft()['settings'] == original['settings']
    assert not win.evaluate_button.isEnabled()
    win.save_document()
    deadline = time.monotonic() + 5
    while win._busy and time.monotonic() < deadline: app.processEvents(); time.sleep(.01)
    assert not win._busy
    saved = win.client.document_read(win.document['id'])
    win._opened(saved)
    assert win.edited_draft()['backend'] == 'unsupported.future'
    malformed = deepcopy(saved); malformed['draft']['backend'] = []
    win._show_document(malformed)
    assert win.edited_draft()['backend'] == []


def test_partial_history_edit_hides_invalid_graph_and_preserves_buffer(window, monkeypatch):
    win, app = window
    win.tree.setCurrentItem(win._nodes[('settings', 'history')])
    path = ('settings', 'history', 'axial_strain', 1)
    field = win.fields[path][0]
    original = win.edited_draft()['settings']['material']['youngs_modulus_mpa']
    field.setText('1e'); field.textEdited.emit('1e')
    win._update_actions()
    assert win.edited_draft()['settings']['history']['axial_strain'][1] == '1e'
    assert win.edited_draft()['settings']['material']['youngs_modulus_mpa'] == original
    assert not win._model_graph_available
    assert win.model_splitter.widget(2).isHidden()
    win.tree.setCurrentItem(win._nodes[('settings', 'material')])
    win.tree.setCurrentItem(win._nodes[('settings', 'history')])
    assert win.fields[path][0].text() == '1e'
    win.fields[path][0].setText('.002'); win.fields[path][0].textEdited.emit('.002')
    assert win._model_graph_available
    assert win.domain_axes.get_aspect() == 'auto'
    assert list(win.domain_axes.lines[0].get_ydata()) == [0., .002]
    win.resize(1100, 780); app.processEvents()
    assert (win.width(), win.height()) == (1100, 780)
    win.fields[path][0].setText('1e\n'); win.fields[path][0].textEdited.emit('1e\n')
    win.tree.setCurrentItem(win._nodes[('settings', 'material')])
    win.tree.setCurrentItem(win._nodes[('settings', 'history')])
    assert win.edited_draft()['settings']['history']['axial_strain'][1] == '1e\n'
    win.fields[path][0].setPlainText('.003')
    assert win.edited_draft()['settings']['history']['axial_strain'][1] == .003
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Cancel)
    event = QCloseEvent()
    win.closeEvent(event)
    assert not event.isAccepted()
    assert win.edited_draft()['settings']['history']['axial_strain'][1] == .003


def test_result_visibility_keeps_selected_response_and_subclass_title(window):
    win, app = window
    win._selected_job = 'J-display-fixture'
    payload = {'execution_status':'SUCCEEDED', 'responses':{'force_z':{'kind':'scalar', 'value':1.23456789123, 'unit':'N'}},
               'diagnostics':{'scope':'TEST_ONLY display payload'}}
    win._accept_result(payload)
    assert win.model_splitter.widget(2).isVisible()
    assert win.graph_tabs.currentIndex() == 1
    assert win.result_selector.currentData() == ('response', 'force_z')
    assert win._result == payload
    document = deepcopy(win.document)
    win.tool_label = 'Material'
    win._show_document(document)
    assert win.windowTitle().endswith(' — Material')
