"""Actual offscreen Qt owner/editor checks; no PDE backend is run."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from copy import deepcopy
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from apps.research.pde_window import PDEWindow, typed_value
from caelab.pde_document import PDEDocuments, default_draft


class EmptyJobs:
    def list(self):
        return []


class OwnerClient:
    def __init__(self, root):
        def absent(*args, **kwargs):
            raise AssertionError('Native evaluation forbidden in this edit/save UI test')
        self.owner = PDEDocuments(root, 'Sqt', absent, EmptyJobs())
        self.calls = []

    def document_open(self, **kwargs):
        assert kwargs.pop('kind') == 'pde'
        self.calls.append(('open', deepcopy(kwargs)))
        return self.owner.open(**kwargs)

    def document_read(self, identifier):
        return self.owner.read(identifier)

    def document_command(self, identifier, operation, arguments, **options):
        self.calls.append((operation, deepcopy(arguments)))
        return self.owner.command(identifier, operation, arguments, **options)

    def documents(self):
        return self.owner.list()


@pytest.fixture(scope='module')
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


def settle(app, window, predicate=lambda: True):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        app.processEvents()
        if not window._busy and predicate():
            app.processEvents()
            return
        QTest.qWait(10)
    raise AssertionError('Offscreen owner/editor operation did not finish: ' + window.message.text())


@pytest.fixture
def window(app, tmp_path):
    result = PDEWindow(OwnerClient(tmp_path), poll_interval=0)
    result.show()
    settle(app, result, lambda: result.document is not None)
    yield result
    settle(app, result)
    result._allow_close = True
    result.close()
    app.processEvents()


def edit(window, path, value):
    widget = window.fields[path][0]
    widget.setFocus()
    if hasattr(widget, 'toPlainText'):
        widget.selectAll()
    else:
        widget.selectAll()
    QTest.keyClicks(widget, value)


def test_actual_typed_equation_invalid_save_undo_reopen(window, app):
    window.tree.setCurrentItem(window._nodes[('settings', 'problem', 'weak_form')])
    original = deepcopy(window.document['draft'])
    edit(window, ('settings', 'problem', 'weak_form', 'rhs'), 'sin(')
    window.validate_inputs()
    settle(app, window)
    assert window.local_dirty and 'failed' in window.message.text()
    window.save_document()
    settle(app, window, lambda: bool(window.document['saved_revision']))
    identifier = window.document['id']
    assert window.document['draft']['settings']['problem']['weak_form']['rhs'] == 'sin('
    assert window.document['diagnostics'] and not window.evaluate_button.isEnabled()
    assert not window.document['dirty']
    window.command('document.undo')
    settle(app, window)
    assert window.document['draft'] == original
    # The editor must not accidentally reapply old widgets while showing Undo.
    assert window.edited_draft() == original
    window.command('document.redo')
    settle(app, window)
    assert window.document['draft']['settings']['problem']['weak_form']['rhs'] == 'sin('
    window.open_document(document_id=identifier)
    settle(app, window)
    assert window.document['diagnostics']
    assert not any(name == 'pde.evaluate' for name, _ in window.client.calls)


def test_domain_boundaries_space_and_time_are_separate_editable_nodes(window, app):
    draft = default_draft('pde.fenicsx.transient')
    window.open_document(draft=draft)
    settle(app, window)
    for path in [('settings', 'problem', 'domain'), ('settings', 'mesh', 'degree'),
                 ('settings', 'problem', 'initial'), ('settings', 'problem', 'boundaries', 'xmin'),
                 ('settings', 'time'), ('settings', 'validation')]:
        window.tree.setCurrentItem(window._nodes[path])
        assert window.fields
    window.tree.setCurrentItem(window._nodes[('settings', 'time')])
    edit(window, ('settings', 'time', 'end'), 'unfinished')
    window.tree.setCurrentItem(window._nodes[('settings', 'problem', 'initial')])
    edit(window, ('settings', 'problem', 'initial', 'value'), '0.0')
    assert window.edited_draft()['settings']['time']['end'] == 'unfinished'
    window.apply_inputs()
    settle(app, window)
    assert window.document['diagnostics']
    window.save_document()
    settle(app, window)
    assert window.document['saved_revision']


def test_save_before_open_continues_after_owner_save(window, app, monkeypatch):
    original = window.document['id']
    window.tree.setCurrentItem(window._nodes[('settings', 'problem', 'weak_form')])
    edit(window, ('settings', 'problem', 'weak_form', 'diffusion'), '2')
    monkeypatch.setattr(QMessageBox, 'question', lambda *args, **kwargs: QMessageBox.StandardButton.Save)
    window._abandon(lambda: window.open_document(title='Second document', draft=default_draft('pde.fenicsx.coupled')))
    settle(app, window, lambda: window.document['id'] != original)
    old = window.client.owner.read(original)
    assert old['saved_revision'] and old['draft']['settings']['problem']['weak_form']['diffusion'] == 2
    assert window.document['draft']['backend'] == 'pde.fenicsx.coupled'


def test_malformed_backend_and_settings_remain_openable(window, app):
    draft = {'backend': [], 'settings': {'problem': []}, 'hidden': {'preserved': True}}
    window.open_document(draft=draft)
    settle(app, window)
    assert window.edited_draft() == draft
    window.validate_inputs()
    settle(app, window)
    window.save_document()
    settle(app, window)
    assert window.document['draft'] == draft and window.document['diagnostics']


def test_exact_field_components_nodes_time_and_post_study(window, app):
    opened = []
    window.result_open = lambda *args, **kwargs: opened.append((args, kwargs))
    window._selected_job = 'Jretained'
    result = {'execution_status': 'SUCCEEDED', 'responses': {}, 'checks': [], 'diagnostics': {
        'fixture': 'SOFTWARE DISPLAY FIXTURE, NO PHYSICS RUN', 'native_fields': [
            {'name': 'recorded time field', 'study_index': 2, 'step_index': 4, 'time': .25,
             'source': {'artifact': 'pde/study_2/step_4/dofs.json', 'sha256': 'b'*64},
             'field': {'node_ids': [100, 900, 700], 'coordinates': [[0, 0], [1, 0], [0, 1]],
                       'values': [[1, 10], [2, 20], [3, 30]], 'components': ['u0', 'u1'],
                       'coordinates_unit': '1', 'field_unit': '1'}}]}}
    window._accept_result(result)
    window.result_selector.setCurrentIndex(1)
    window.field_node.setCurrentIndex(window.field_node.findData(900))
    app.processEvents()
    assert 'Node 900' in window.point_label.text() and 'value 20' in window.point_label.text()
    assert 'model time 0.25 [1]' in window.point_label.text()
    assert 'b'*64 not in window.point_label.text()
    assert 'b'*64 in window.point_label.toolTip()
    assert len(window.result_figure.axes) == 2  # One field axes and one colorbar; no accumulated colorbars.
    window.open_post()
    assert opened == [((window.document['id'], 'Jretained'), {'study_index': 2})]
    assert not window.client.calls[-1][0].startswith('pde.evaluate')


def test_typed_repair_never_evaluates_or_erases_invalid_original():
    assert typed_value('bad', 'bad', ('settings', 'mesh', 'degree')) == 'bad'
    assert typed_value('2', 'bad', ('settings', 'mesh', 'degree')) == 2
    assert typed_value('nan', 1, ('settings', 'problem', 'weak_form', 'diffusion')) == 'nan'
    assert typed_value('3', 'bad', ('settings', 'problem', 'weak_form', 'diffusion', 'left', 0, 1)) == 3


def test_open_chooser_reads_real_workbench_documents_envelope(window, app, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    first = window.document['id']
    second = window.client.owner.open(title='Another PDE model')
    window.client.documents = lambda: {'service_session_id': 'Sqt', 'documents': window.client.owner.list()}
    seen = []
    def choose(*args, **kwargs):
        choices = args[3]
        seen.extend(choices)
        return next(choice for choice in choices if second['id'] in choice), True
    monkeypatch.setattr(QInputDialog, 'getItem', choose)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args, **kwargs: QMessageBox.StandardButton.Discard)
    window.choose_document()
    settle(app, window, lambda: window.document['id'] != first)
    assert window.document['id'] == second['id'] and len(seen) == 2


def test_standalone_launcher_matches_desktop_document_id_and_navigation(monkeypatch):
    from types import SimpleNamespace
    from apps.research import pde_window, desktop
    opened, navigation = [], []
    class Window:
        def __init__(self, client, **kwargs):
            opened.append((client, kwargs))
        def show(self):
            pass
    monkeypatch.setattr(pde_window, 'PDEWindow', Window)
    monkeypatch.setattr(pde_window, 'QApplication', SimpleNamespace(instance=lambda: SimpleNamespace(exec=lambda: 0)))
    monkeypatch.setattr(desktop, 'launch_tool', lambda *args, **kwargs: navigation.append(('runner', args, kwargs)))
    monkeypatch.setattr(desktop, 'open_document_result', lambda *args, **kwargs: navigation.append(('post', args, kwargs)), raising=False)
    assert pde_window.main(['--service', 'http://127.0.0.1:9912', '--document-id', 'Qselected']) == 0
    client, options = opened[0]
    assert options['document_id'] == 'Qselected' and client.url == 'http://127.0.0.1:9912'
    options['runner_open']('Jrecorded')
    options['result_open']('Qselected', 'Jrecorded', study_index=2)
    assert navigation[0] == ('runner', (client, 'runner'), {'job_id': 'Jrecorded'})
    assert navigation[1] == ('post', (client, 'Qselected', 'Jrecorded'), {'study_index': 2})
    monkeypatch.delenv('CAELAB_SERVICE_URL', raising=False)
    with pytest.raises(SystemExit) as error:
        pde_window.main([])
    assert error.value.code == 2


def test_numerical_plan_requires_applied_generation_and_retries_same_creation(window, app):
    calls = []
    first = True
    def open_plan(identifier, **options):
        nonlocal first
        calls.append((identifier, options))
        if first:
            first = False
            raise RuntimeError('TEST ONLY: creation response lost; retry the same command')
        return {'document_id': 'Nfrozenrequest', 'executed': False, 'status': 'LAUNCH_REQUESTED'}
    window.plan_open = open_plan
    assert window.plan_button.isEnabled() and window.plan_action.isEnabled()
    assert window.document['runs'] == []
    window.tree.setCurrentItem(window._nodes[('settings', 'problem', 'weak_form')])
    edit(window, ('settings', 'problem', 'weak_form', 'diffusion'), '3')
    assert not window.plan_button.isEnabled()
    assert window.open_numerical_plan() is False
    assert 'Apply' in window.message.text() and calls == []
    window.apply_inputs()
    settle(app, window)
    assert window.document['generation'] == 1 and window.plan_button.isEnabled()
    window.open_numerical_plan()
    settle(app, window)
    assert 'response lost' in window.message.text() and window.plan_button.isEnabled()
    window.open_numerical_plan()
    settle(app, window)
    assert len(calls) == 2 and calls[0] == calls[1]
    identifier, options = calls[1]
    assert identifier == window.document['id']
    assert options['session_id'] == window.document['session_id'] and options['expected_generation'] == 1
    assert options['command_id'].startswith('C')
    assert 'Nfrozenrequest' in window.message.text() and 'no evaluation' in window.message.text()
    assert window.document['runs'] == []
    assert not any(operation == 'pde.evaluate' for operation, _ in window.client.calls)
