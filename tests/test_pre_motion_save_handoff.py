"""Save serializes the current motion selection before writing the native file."""
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from apps.desktop_pre.connection import Connection


@pytest.fixture
def setup():
    pending = {'assembly_id': 'Assembly', 'view': {'joint_id': 'Joint', 'drive_row': 1, 'trace_row': 0}}
    accepted, sent, completed = [], [], []
    controller = NS(pending_view=lambda: pending, accept_saved_view=accepted.append)
    owner = NS(doc=NS(Name='Model'), document_id='Dmodel', session_id='Ssession', generation=1, refresh=lambda: None)
    broker = NS(stop=NS(is_set=lambda: False), registered=NS(is_set=lambda: True))
    connection = Connection.__new__(Connection)
    connection.Gui=NS(getMainWindow=lambda:NS())
    connection.owners = {'Model': (owner, None, broker)}
    connection.panels = {'Model': {'motion': NS(widget=lambda: NS(motion_controller=controller))}}
    connection.native_requests = {}
    connection.message = NS(setText=lambda text: None)
    connection._send_native = lambda identifier: sent.append(identifier)
    return connection, owner, controller, pending, accepted, sent, completed


def finish(connection, identifier, *, failed=False):
    value = {'status': 'SAVED', 'path': 'model.FCStd'}
    command = {'command_id': identifier, 'state': 'FAILED' if failed else 'SUCCEEDED',
               'outcome': {'result': {'result': value, 'error': {'message': 'test failure'}}}}
    connection._native_status(command)


def test_selection_then_file_save_keep_original_request_and_new_generation(setup):
    connection, owner, controller, pending, accepted, sent, completed = setup
    before = deepcopy(pending)
    receipt = connection.submit_native('document.save', {'path': 'model.FCStd'}, on_done=completed.append, owner=owner)
    first = connection.native_requests[receipt['command_id']]
    assert first['operation'] == 'pre.motion.set_view'
    assert first['arguments'] == {'view': before['view'], 'target': {'assembly_id': 'Assembly'}}
    pending['view']['joint_id'] = 'ChangedWhileSaving'
    owner.generation = 2
    finish(connection, sent[0])
    second = connection.native_requests[sent[1]]
    assert second['operation'] == 'document.save' and second['generation'] == 2
    assert second['arguments'] == {'path': 'model.FCStd'}
    assert not completed and not accepted
    finish(connection, sent[1])
    assert accepted == [before] and completed[0]['status'] == 'SAVED'
    assert len(sent) == 2 and not connection.native_requests


@pytest.mark.parametrize('fail_selection', [True, False])
def test_failure_never_marks_view_saved(setup, fail_selection):
    connection, owner, controller, pending, accepted, sent, completed = setup
    connection.submit_native('document.save', {}, on_done=completed.append, owner=owner)
    finish(connection, sent[0], failed=fail_selection)
    if not fail_selection:
        finish(connection, sent[1], failed=True)
    assert len(sent) == (1 if fail_selection else 2)
    assert not accepted and completed[0]['status'] == 'FAILED'


def test_closed_panel_or_no_pending_selection_uses_original_save(setup):
    connection, owner, controller, pending, accepted, sent, completed = setup
    controller.pending_view = lambda: None
    connection.submit_native('document.save', {}, on_done=completed.append, owner=owner)
    assert connection.native_requests[sent[0]]['operation'] == 'document.save'
    finish(connection, sent[0])
    connection.panels = {}
    connection.submit_native('document.save', {}, owner=owner)
    assert connection.native_requests[sent[1]]['operation'] == 'document.save'


def test_raw_editor_is_captured_before_save_and_late_edit_is_not_accepted(setup):
    connection, owner, controller, pending, accepted, sent, completed = setup
    editor = {'assembly_id': 'Assembly', 'editor': {'view': pending['view'],
        'joint_draft': {'raw': 'Face99'}, 'definition_draft': {'raw': '1e'}}}
    controller.pending_editor = lambda: editor
    controller.accept_saved_editor = accepted.append
    before = deepcopy(editor)
    connection.submit_native('document.save', {}, on_done=completed.append, owner=owner)
    first = connection.native_requests[sent[0]]
    assert first['operation'] == 'pre.motion.save_editor'
    assert first['arguments'] == {'editor': before['editor'], 'target': {'assembly_id': 'Assembly'}}
    editor['editor']['definition_draft']['raw'] = '2e'
    finish(connection, sent[0]); finish(connection, sent[1])
    assert accepted == [before] and editor['editor']['definition_draft']['raw'] == '2e'


@pytest.mark.parametrize('save_fails', [False, True])
@pytest.mark.parametrize('with_beam', [False, True])
def test_shell_and_motion_edits_share_one_document_save(setup, save_fails, with_beam):
    from apps.desktop_pre.shell_panel import DraftBuffer
    connection, owner, controller, pending, accepted, sent, completed = setup
    buffer = DraftBuffer()
    buffer.read('ShellAnalysis', {'thickness_mm': '3'})
    buffer.fields['thickness_mm'] = '1e'
    shell = NS(buffer=buffer, busy=False, pending_changes=buffer.pending_changes,
               update_enabled=lambda: None, show_errors=lambda: None)
    connection.panels['Model']['shell'] = NS(widget=lambda: NS(shell_controller=shell))
    if with_beam:
        beam_draft = {'analysis_id': 'BeamAnalysis', 'section': {'width_mm': '1e'}}
        beam = NS(pending_snapshot=lambda: beam_draft, accept_saved_snapshot=lambda *_: None)
        connection.panels['Model']['beam'] = NS(widget=lambda: beam)
    connection.submit_native('document.save', {}, owner=owner, on_done=completed.append)
    expected_operations = ['pre.shell.save_draft']
    if with_beam:
        expected_operations.append('pre.beam.draft')
    expected_operations.extend(('pre.motion.set_view', 'document.save'))
    for index, expected in enumerate(expected_operations):
        request = connection.native_requests[sent[index]]
        assert request['operation'] == expected
        finish(connection, sent[index], failed=save_fails and expected == 'document.save')
    assert len(sent) == len(expected_operations) and len(completed) == 1 and not shell.busy
    assert buffer.fields['thickness_mm'] == '1e'
    assert buffer.pending_changes() is save_fails
    assert bool(accepted) is not save_fails
