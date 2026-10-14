"""Portable archive/Qt save contracts; no FreeCAD process is launched."""
from copy import deepcopy
import json
import os
from types import SimpleNamespace as NS

import pytest

from apps.desktop_pre import metadata
from apps.desktop_pre.connection import Connection
from apps.desktop_pre.projects import Project
from apps.desktop_pre.bridge import Owner
from caelab import native_cad
from test_pre_project_bundle import graph, native_owner
from test_pre_native_controls_ui import app, controls, questions, QtWidgets


def test_project_fsync_uses_writable_completed_archive_and_keeps_source(tmp_path, monkeypatch):
    _, main, dependency, a, b = graph(tmp_path)
    before = {path: path.read_bytes() for path in (main, dependency)}
    actual, writable = native_cad.os.fsync, []
    def fsync(fd):
        # A zero-byte write rejects a read-only FD on Linux too. The native
        # Windows _commit path also requires the writable publication handle.
        os.write(fd, b'')
        writable.append(fd)
        return actual(fd)
    monkeypatch.setattr(native_cad.os, 'fsync', fsync)
    owner = native_owner(tmp_path, a)
    saved = owner.project.save()
    assert writable and owner.project.is_saved()
    assert native_cad.inspect_project(saved['path'])['design_pose_restored']
    assert all(path.read_bytes() == raw for path, raw in before.items())


def linked_owners(tmp_path):
    _, _, _, a, b = graph(tmp_path)
    parent, child = native_owner(tmp_path / 'parent', a), native_owner(tmp_path / 'child', b)
    parent.closed = child.closed = False
    parent.find_owner = child.find_owner = lambda doc: parent if doc is a else child if doc is b else None
    return parent, child


def test_saved_dependency_version_affects_dirty_and_reconnect_without_parent_edit(tmp_path):
    parent, child = linked_owners(tmp_path)
    parent.project.save()
    saved_generation = parent.generation
    retained = deepcopy(parent.project.connection_state())
    assert parent.project.is_saved()
    child.generation += 1
    assert parent.generation == saved_generation
    assert parent.project.descriptor()['dirty']
    replacement = Project(parent)
    replacement.restore_connection_state(retained)
    assert not replacement.is_saved()
    parent.project = replacement
    replacement.save()
    assert replacement.is_saved()
    child.closed = True
    assert not replacement.is_saved()


def test_external_observer_edit_advances_parent_and_ignores_unrelated_or_preview(tmp_path):
    parent, child = linked_owners(tmp_path)
    parent._preview_depth = child._preview_depth = 0
    parent.project.save()
    old = parent.generation
    Owner.slotChangedObject(parent, NS(Document=child.doc), 'Length')
    assert parent.generation == old + 1 and not parent.project.is_saved()
    Owner.slotChangedObject(parent, NS(Document=NS(Name='Unrelated', Objects=[])), 'Length')
    child._preview_depth = 1
    Owner.slotChangedObject(parent, NS(Document=child.doc), 'Placement')
    assert parent.generation == old + 1


def test_unlinked_document_no_longer_advances_parent_generation(tmp_path):
    parent, child = linked_owners(tmp_path)
    parent._preview_depth = child._preview_depth = 0
    parent.mesh_bindings = NS(slotChangedObject=lambda *args: None)
    parent.project.save()
    parent.doc.Objects[0].LinkedObject = None
    Owner.slotChangedObject(parent, parent.doc.Objects[0], 'LinkedObject')
    parent.project.save()
    before = parent.generation
    Owner.slotChangedObject(parent, NS(Document=child.doc), 'Definition')
    assert parent.generation == before and parent.project.is_saved()


@pytest.fixture
def observed(tmp_path):
    """Real Owner/Project and observer fan-out; only FreeCAD itself is doubled."""
    _, original, dependency, a, b = graph(tmp_path)
    app = NS(observers=[], documents={a.Name: a, b.Name: b})
    app.addDocumentObserver = app.observers.append
    app.removeDocumentObserver = app.observers.remove
    app.listDocuments = lambda: app.documents
    def changed(obj, prop):
        for observer in tuple(app.observers):
            observer.slotChangedObject(obj, prop)
    app.changed = changed
    gui_docs = {doc.Name: NS(Modified=False, getInEdit=lambda: False) for doc in (a, b)}
    gui = NS(Selection=NS(getSelectionEx=lambda name: []), Control=NS(activeDialog=lambda: False),
             activeDocument=lambda: gui_docs[a.Name], getDocument=gui_docs.__getitem__)
    for doc in (a, b):
        doc.openTransaction = lambda title: None
        doc.recompute = doc.commitTransaction = doc.abortTransaction = lambda: None
        record = NS(Name=metadata.NAME, Document=doc, PropertiesList=['Definition'],
                    Definition=json.dumps({'schema': metadata.SCHEMA, 'document_id': 'P' + doc.Name}),
                    getTypeIdOfProperty=lambda prop: 'App::PropertyString')
        doc.Objects.append(record)
        for obj in doc.Objects:
            obj.Label, obj.TypeId, obj.State = obj.Name, 'App::FeaturePython', []
            obj.isDerivedFrom = lambda kind: False
    parent = Owner(a, tmp_path / 'owner-files', App=app, Gui=gui)
    child = Owner(b, tmp_path / 'owner-files', App=app, Gui=gui)
    owners = {a.Name: parent, b.Name: child}
    parent.find_owner = child.find_owner = lambda doc: owners.get(doc.Name)
    yield NS(parent=parent, child=child, app=app, Gui=gui, owners=owners,
             original=original, dependency=dependency, gui_docs=gui_docs)
    for owner in tuple(app.observers):
        owner.close()


def edit_metadata(context, text='new research note'):
    child = context.child
    obj = child.doc.getObject(metadata.NAME)
    before = child.read_metadata()
    obj.Definition = json.dumps({**before, 'research_note': text})
    context.app.changed(obj, 'Definition')


def test_real_owner_metadata_observer_makes_parent_dirty_and_close_cancel_keeps_open(observed, controls, monkeypatch):
    c, parent = controls, observed.parent
    parent.project.save()  # Actual ZIP and fsync, with no fsync substitution.
    c.connection.owners = {parent.doc.Name: (parent, None, None)}
    c.connection.active_owner = lambda: parent
    c.connection.Gui.getDocument = observed.Gui.getDocument
    old = parent.generation
    edit_metadata(observed)
    assert parent.generation == old + 1
    assert parent.descriptor()['dirty'] and parent.descriptor()['project']['dirty']
    seen = questions(monkeypatch, [QtWidgets.QMessageBox.Cancel])
    c.guards.replacements['Std_Close'][1].trigger()
    assert len(seen) == 1 and not parent.closed
    assert c.originals == [] and c.guards.approved_close == {}


def test_publication_failure_keeps_dependency_saved_baseline_and_previous_archive(observed, monkeypatch):
    parent = observed.parent
    saved = parent.project.save()
    path = parent.project.path
    old_bytes, old_save = path.read_bytes(), deepcopy(parent.project.last_save)
    old_generation, old_graph = parent.saved_generation, parent.project.connection_state()['saved_graph_version']
    edit_metadata(observed)
    actual, attempts = native_cad._publish_json, []
    def publish(prepared, target):
        if target == path:
            attempts.append(prepared)
            raise PermissionError('controlled publication refusal')
        return actual(prepared, target)
    monkeypatch.setattr(native_cad, '_publish_json', publish)
    with pytest.raises(PermissionError, match='controlled publication refusal'):
        parent.project.save()
    assert path.read_bytes() == old_bytes and parent.project.last_save == old_save
    assert parent.saved_generation == old_generation
    assert parent.project.connection_state()['saved_graph_version'] == old_graph
    assert parent.project.path == path and parent.project.descriptor()['dirty']
    assert len(attempts) == 1 and native_cad.inspect_project(attempts[0])['revision'] != saved['revision']
    assert not parent.project.in_save and 'controlled publication refusal' in parent.project.last_failure


@pytest.mark.parametrize('dirty', [False, True])
def test_real_owner_reconnect_preserves_clean_or_dirty_dependency_baseline(observed, monkeypatch, tmp_path, dirty):
    parent, child = observed.parent, observed.child
    child.project.save()
    parent.project.save()
    if dirty:
        edit_metadata(observed)
    original_state = parent.project.connection_state()
    old_save = deepcopy(parent.project.last_save)
    assert parent.descriptor()['dirty'] is dirty
    callbacks, events = [], []
    def start(doc, config, qt, **options):
        replacement = Owner(doc, config['export_root'], App=observed.app, Gui=observed.Gui,
                            document_id=options['document_id'])
        return replacement, NS(close=replacement.close), NS()
    monkeypatch.setattr('apps.desktop_pre.connection.bridge.start', start)
    connection = NS(pending=None, native_requests={},
        owners={row.doc.Name: (row, NS(close=row.close), None) for row in (parent, child)},
        panels={}, config={}, QtCore=NS(), log=lambda *a, **kw: None,
        App=observed.app, client=NS(desktop_context=lambda: None),
        message=NS(setText=events.append), request=lambda key, call, accept: callbacks.append(accept),
        show_panel=lambda *a, **kw: pytest.fail('No panels were open'))
    Connection.reconnect(connection)
    callbacks[0]({'export_root': str(tmp_path / 'owner-files'), 'python': 'private-python'})
    reopened = connection.owners[parent.doc.Name][0]
    assert parent.closed and child.closed and reopened.doc is parent.doc
    assert reopened.session_id != parent.session_id and reopened.document_id == parent.document_id
    assert reopened.project.connection_state() == original_state
    assert reopened.project.last_save == old_save and reopened.project.last_save is not old_save
    assert reopened.saved_generation == parent.saved_generation
    assert reopened.descriptor()['dirty'] is dirty
    assert reopened.project.is_saved() is (not dirty)


def install_actual_project(c, tmp_path):
    parent, child = linked_owners(tmp_path)
    target = c.owners[0]
    parent.doc.Name, child.doc.Name = 'One', 'Dependency'
    for key in ('doc', 'read_metadata', 'write_metadata', '_transaction', 'find_owner', 'Gui'):
        setattr(target, key, getattr(parent, key))
    target.find_owner = lambda doc: target if doc is target.doc else child if doc is child.doc else None
    target.project = Project(target)
    target.project.save()
    assert target.project.is_saved()
    return target, child


def test_dependency_edit_prompts_on_parent_close(controls, tmp_path, monkeypatch):
    c = controls
    parent, child = install_actual_project(c, tmp_path)
    before = parent.generation
    child.generation += 1
    seen = questions(monkeypatch, [QtWidgets.QMessageBox.Cancel])
    c.guards.replacements['Std_Close'][1].trigger()
    assert len(seen) == 1 and parent.generation == before
    assert c.originals == [] and c.guards.approved_close == {}


def test_dependency_edit_during_parent_discard_dialog_invalidates_close_choice(controls, tmp_path, monkeypatch):
    c = controls
    parent, child = install_actual_project(c, tmp_path)
    child.generation += 1
    def question(*args):
        child.generation += 1
        return QtWidgets.QMessageBox.Discard
    monkeypatch.setattr(QtWidgets.QMessageBox, 'question', question)
    c.guards.replacements['Std_Close'][1].trigger()
    assert c.originals == [] and c.guards.approved_close == {}
    assert '편집이 바뀌었습니다' in c.connection.message.text()
