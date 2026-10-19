"""Reconnect preserves a live native document; no FreeCAD is launched."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS

from apps.desktop_pre.connection import Connection


def test_new_session_keeps_live_generation_managed_save_and_rebinds_docks(monkeypatch, tmp_path):
    doc = NS(Name='Assembly', FileName='editable.FCStd')
    owner = NS(doc=doc, document_id='Psource', generation=7, saved_generation=6, recovery_error=None,
               project=NS(path=tmp_path/'design.caepre', last_save={'revision': 'Rsaved'}, last_failure=None))
    events, callbacks = [], []
    owner.before_design_action = lambda action: events.append(('restore', action))
    dock = NS(isVisible=lambda: True, close=lambda: events.append(('dock', 'close')), deleteLater=lambda: None)
    dispatch = NS(close=lambda: events.append(('old', 'closed')))
    def start(actual, config, qt, **kw):
        assert actual is doc
        new = NS(doc=actual, document_id=kw['document_id'], generation=0, saved_generation=None,
                 project=NS(path=None, last_save=None, last_failure=None), recovery_error=None, session_id='Snew')
        return new, NS(), NS()
    monkeypatch.setattr('apps.desktop_pre.connection.bridge.start', start)
    connection = NS(pending=None, native_requests={}, owners={doc.Name: (owner, dispatch, None)},
        panels={doc.Name: {'motion': dock}}, config={}, QtCore=NS(), Gui=NS(getMainWindow=lambda: NS()), log=lambda *a, **kw: None,
        App=NS(listDocuments=lambda: {doc.Name: doc}), client=NS(desktop_context=lambda: None),
        message=NS(setText=lambda value: events.append(('message', value))),
        request=lambda key, call, accepted: callbacks.append(accepted),
        show_panel=lambda kind, owner: events.append(('panel', kind, owner)))
    Connection.reconnect(connection)
    assert connection.owners[doc.Name][0] is owner and not events
    # Human edit while HTTP context is pending still belongs to the live owner.
    owner.generation = 8
    callbacks[0]({'export_root': str(tmp_path), 'python': 'private-python'})
    new = connection.owners[doc.Name][0]
    assert new is not owner and new.generation == 8 and new.saved_generation == 6
    assert new.project.path == tmp_path/'design.caepre' and new.project.last_save == {'revision': 'Rsaved'}
    assert new.project.last_save is not owner.project.last_save
    assert events[0] == ('restore', 'reconnect')
    assert ('panel', 'motion', new) in events
    assert new.find_owner(doc) is new


def test_freeze_recovery_keeps_exact_command_until_completion():
    messages, submissions, calls = [], [], []
    request = {'command_id': 'Cexact', 'stage': 'command', 'retry': False,
               'document_id': 'Pdesign', 'session_id': 'Soriginal', 'generation': 7,
               'arguments': {'analysis_id': 'Analysis', 'solver_id': 'Solver'}}
    connection = NS(pending=deepcopy(request), working=set(), native_requests={},
        message=NS(setText=messages.append), submit=lambda: submissions.append('submit'),
        client=NS(document_command=lambda *args, **kwargs: calls.append((args, kwargs))),
        request=lambda key, call, accepted: call())
    connection.send_command = lambda: Connection.send_command(connection)
    connection.command_status = lambda value: Connection.command_status(connection, value)
    Connection.command_status(connection, {'command_id': 'Cexact', 'state': 'INTERRUPTED',
                                          'completion_recoverable': True})
    assert connection.pending == {**request, 'retry': True} and not submissions
    Connection.retry(connection)
    assert calls == [(('Pdesign', 'pre.freeze', request['arguments']),
                     {'session_id': 'Soriginal', 'expected_generation': 7, 'command_id': 'Cexact'})]
    Connection.command_status(connection, {'command_id': 'Cunrelated', 'state': 'SUCCEEDED'})
    assert not submissions and connection.pending['command_id'] == 'Cexact'
    Connection.command_status(connection, {'command_id': 'Cexact', 'state': 'SUCCEEDED'})
    assert submissions == ['submit'] and connection.pending['stage'] == 'submit'


def test_new_raw_edit_during_reconnect_context_retains_same_owner_and_dock():
    doc = NS(Name='Model'); state = {'token': 1}; events, callbacks = [], []
    controller = NS(editor_token=lambda: state['token'])
    dock = NS(widget=lambda: NS(motion_controller=controller))
    owner = NS(doc=doc)
    connection = NS(pending=None, native_requests={}, owners={doc.Name: (owner, NS(), NS())},
        panels={doc.Name: {'motion': dock}}, Gui=NS(getMainWindow=lambda: NS()), client=NS(desktop_context=lambda: None),
        message=NS(setText=events.append), request=lambda key, call, accepted: callbacks.append(accepted))
    Connection.reconnect(connection)
    state['token'] = 2
    callbacks[0]({})
    assert connection.owners[doc.Name][0] is owner and connection.panels[doc.Name]['motion'] is dock
    assert '편집이 바뀌었습니다' in events[-1]
