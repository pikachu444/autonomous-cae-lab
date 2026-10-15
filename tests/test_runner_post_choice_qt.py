"""Controlled registered-result selection; no Aster calculation or native Post launch."""
from copy import deepcopy
import os
from pathlib import Path
import threading

import pytest

from test_runner_dynamic_readback_qt import app, until, ControlledClient
from apps.research import desktop, runner_window
from apps.research.runner_window import RunnerWindow
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QInputDialog


def choose_with(monkeypatch, choose):
    class Choice(QInputDialog):
        def exec(self):
            combo = self.findChild(QComboBox)
            selected, accepted = choose(self.parent(), self.windowTitle(), self.labelText(),
                [combo.itemText(i) for i in range(combo.count())], combo.currentIndex(), combo.isEditable())
            combo.setCurrentIndex(selected if type(selected) is int else combo.findText(selected))
            return int(accepted)
    monkeypatch.setattr(runner_window, 'QInputDialog', Choice)


class PostClient(ControlledClient):
    def __init__(self):
        super().__init__()
        self.jobs['Joriginal'].update(state='SUCCEEDED', result_refs=['Roriginal'])
        self.jobs['Joriginal'].pop('error', None)
        self.jobs['Joriginal']['arguments'].update(backend='structure.codeaster.frozen', label='곡면 클램프')
        self.navigation = {'post_input': {'id': 'Dnodes'},
                           'post_inputs': [{'id': 'Dnodes'}, {'id': 'Dstress'}]}
        self.records = {
            'Dnodes': {'id': 'Dnodes', 'path': '/registered/displacement.vtu', 'native_metadata': {'arrays': [
                {'measure': 'displacement', 'units': 'mm'}, {'measure': 'nodal_reaction', 'units': 'N'}]}},
            'Dstress': {'id': 'Dstress', 'path': '/registered/stress_points.vtu', 'native_metadata': {'arrays': [
                {'measure': 'cauchy_stress_at_native_integration_point', 'units': 'MPa'},
                {'measure': 'identity', 'units': '1'}]}}}
        self.gate = None
        self.wait_at = None
        self.started = threading.Event()
        self.metadata_threads = []

    def _wait(self, phase):
        if self.wait_at == phase:
            self.started.set()
            assert self.gate.wait(5)

    def job_navigation(self, identifier):
        self.calls.append(('navigation', identifier))
        self._wait('navigation')
        return deepcopy(self.navigation)

    def native_input(self, identifier):
        self.calls.append(('native_input', identifier))
        self.metadata_threads.append(threading.get_ident())
        self._wait('metadata')
        return deepcopy(self.records[identifier])


@pytest.fixture
def viewer(app, monkeypatch):
    client = PostClient()
    opened = []
    monkeypatch.setattr(desktop, 'launch_post',
                        lambda c, data, **kw: opened.append((data, kw)) or {'status': 'SHOWN'})
    window = RunnerWindow(client, job_id='Joriginal', poll_interval=0)
    until(app, lambda: window.selected_job_id == 'Joriginal' and not window._pending)
    yield window, client, opened
    if client.gate:
        client.gate.set()
    until(app, lambda: not window._pending)
    window.close()
    app.processEvents()


def test_single_duplicate_primary_keeps_one_click_without_metadata_or_dialog(viewer, app, monkeypatch):
    window, client, opened = viewer
    client.navigation['post_inputs'] = [{'id': 'Dnodes'}]
    choose_with(monkeypatch, lambda *a: pytest.fail('Single result asked a question'))
    window.post_button.click()
    until(app, lambda: not window._pending)
    assert opened == [('Dnodes', {'job_id': 'Joriginal'})]
    assert not client.metadata_threads


def test_multiple_choices_use_verified_physical_labels_and_exact_selected_input(viewer, app, monkeypatch):
    window, client, opened = viewer
    main_thread = threading.get_ident()
    def choose(parent, title, prompt, labels, current, editable):
        assert threading.get_ident() == main_thread
        assert labels == ['변위와 반력 (mm, N)', '적분점 응력 (MPa)']
        assert editable is False
        return labels[1], True
    choose_with(monkeypatch, choose)
    window.post_button.click()
    until(app, lambda: not window._pending)
    assert opened == [('Dstress', {'job_id': 'Joriginal'})]
    assert [call[1] for call in client.calls if call[0] == 'native_input'] == ['Dnodes', 'Dstress']
    assert client.metadata_threads and all(t != main_thread for t in client.metadata_threads)


@pytest.mark.parametrize('accepted,selection', [(False, '적분점 응력 (MPa)'), (True, 'Dunregistered')])
def test_cancel_or_unlisted_choice_never_launches(viewer, app, monkeypatch, accepted, selection):
    window, client, opened = viewer
    choose_with(monkeypatch, lambda *a: (selection, accepted))
    window.post_button.click()
    until(app, lambda: not window._pending)
    assert opened == []


@pytest.mark.parametrize('phase', ['navigation', 'metadata'])
def test_late_reply_after_job_selection_change_has_no_dialog_or_launch(viewer, app, monkeypatch, phase):
    window, client, opened = viewer
    client.wait_at, client.gate = phase, threading.Event()
    choose_with(monkeypatch, lambda *a: pytest.fail('Stale result opened a dialog'))
    window.post_button.click()
    until(app, client.started.is_set)
    window.select_job('Jother')
    client.gate.set()
    until(app, lambda: not window._pending)
    assert window.selected_job_id == 'Jother' and opened == []


def test_selection_changed_during_modal_choice_never_launches_old_result(viewer, app, monkeypatch):
    window, client, opened = viewer
    def choose(*args):
        window.select_job('Jother')
        return args[3][1], True
    choose_with(monkeypatch, choose)
    window.post_button.click()
    until(app, lambda: not window._pending)
    assert opened == []


def test_generic_names_disambiguate_without_ids_and_wrong_receipt_is_rejected(viewer, app, monkeypatch):
    window, client, opened = viewer
    for record in client.records.values():
        record.update(name='압력 분포', native_metadata={'arrays': [{'units': 'Pa'}]})
    def choose(*args):
        assert args[3] == ['1. 압력 분포 (Pa)', '2. 압력 분포 (Pa)']
        return args[3][1], True
    choose_with(monkeypatch, choose)
    window.post_button.click()
    until(app, lambda: not window._pending)
    assert opened == [('Dstress', {'job_id': 'Joriginal'})]
    opened.clear()
    client.records['Dstress']['id'] = 'Dunregistered'
    window.post_button.click()
    until(app, lambda: not window._pending)
    assert opened == [] and '등록한 결과를 확인할 수 없습니다' in window.message.text()


def test_colliding_display_suffix_still_opens_the_exact_third_combo_row(viewer, app, monkeypatch):
    window, client, opened = viewer
    client.navigation['post_inputs'].append({'id': 'Dthird'})
    client.records['Dthird'] = {'id': 'Dthird', 'name': '압력 / 결과 1'}
    for identifier in ('Dnodes', 'Dstress'):
        client.records[identifier] = {'id': identifier, 'name': '압력'}
    def choose(*args):
        assert args[3] == ['1. 압력', '2. 압력', '3. 압력 / 결과 1']
        return 2, True
    choose_with(monkeypatch, choose)
    window.post_button.click()
    until(app, lambda: not window._pending)
    assert opened == [('Dthird', {'job_id': 'Joriginal'})]


def test_actual_qt_choice_render_normal_and_narrow(viewer, app):
    window, client, opened = viewer
    errors = []
    capture = os.environ.get('CAE_POST_CHOICE_CAPTURE_DIR')
    def inspect_dialog():
        dialog = QApplication.activeModalWidget()
        if dialog is None and window._pending:
            QTimer.singleShot(10, inspect_dialog)
            return
        try:
            assert isinstance(dialog, QInputDialog)
            assert dialog.okButtonText() == '열기' and dialog.cancelButtonText() == '취소'
            combo = dialog.findChild(QComboBox)
            assert [combo.itemText(i) for i in range(combo.count())] == ['변위와 반력 (mm, N)', '적분점 응력 (MPa)']
            combo.setCurrentIndex(1)
            for label, size in [('normal', (1320, 840)), ('narrow', (900, 650))]:
                window.resize(*size)
                app.processEvents()
                if capture:
                    folder = Path(capture)
                    folder.mkdir(parents=True, exist_ok=True)
                    assert window.grab().save(str(folder / (label + '-runner.png')))
                    assert dialog.grab().save(str(folder / (label + '-choice.png')))
        except BaseException as error:
            errors.append(error)
        finally:
            if isinstance(dialog, QInputDialog):
                dialog.accept()
    window.show()
    QTimer.singleShot(100, inspect_dialog)
    window.post_button.click()
    until(app, lambda: not window._pending)
    assert not errors, errors
    assert opened == [('Dstress', {'job_id': 'Joriginal'})]
