"""Focused owner/callback/lifecycle tests. NOT a ParaView or Windows GUI run."""
from copy import deepcopy
import ctypes
import gc
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import weakref

import pytest
from apps.desktop_post import native_exit as adapter
from apps.desktop_post import native_exit_abi as abi
from apps.desktop_post import native_exit_gate as gate
from apps.desktop_post.native_controls import Controls, WM_CLOSE
from test_desktop_post_bridge import bridge, command
from test_post_native_controls import Owner as SmallOwner, Platform


class Library:
    """Native C endpoint double; callbacks still pass through actual CFUNCTYPE."""
    def __init__(self):
        self.registration = self.client = self.attempt = 0
        self.sequence = 0
        self.active = False
        self.busy = 0
        self.choice = 'cancel'
        self.prompt = lambda: None
        self.prompts = 0
        self.errors = []
        self.ui_draft = {'unapplied': False, 'editors': 3, 'sha256': '0'*64}
        self.detach_error = False
        self.callback = None

    def probe(self):
        return abi.Status(abi=1, size=ctypes.sizeof(abi.Status), pid=os.getpid(), window=123,
                          ready=1, installed=bool(self.registration), qt_compiled=0x060900,
                          qt_runtime=0x060900, paraview_compiled=0x060200, pointer_bits=64)

    def attach(self, session, window, client, callback):
        assert not self.registration and session and window == 123
        self.sequence += 1
        self.registration, self.client, self.callback = self.sequence, client, callback
        return self.registration

    def status(self, registration):
        if not registration or self.registration != registration:
            raise abi.NativeExitUnavailable('wrong owner')
        status = self.probe()
        status.registration, status.client = self.registration, self.client
        status.native_busy, status.in_action = self.busy, self.active
        status.attempt = self.attempt
        status.filter_count = 1
        return status

    def draft(self, registration):
        assert registration == self.registration
        return dict(self.ui_draft)

    def detach(self, registration):
        if self.detach_error:
            raise abi.NativeExitUnavailable('native detach failed')
        assert registration == self.registration
        self.registration = self.client = 0
        self.active = False
        return True

    def ask_close(self, registration):
        assert registration == self.registration
        self.prompts += 1
        self.prompt()
        return self.choice

    def error(self, registration, text):
        assert registration == self.registration
        self.errors.append(text)

    def emit(self, event, attempt=None):
        if event == abi.BEGIN:
            self.attempt += 1
            self.active = True
        result = self.callback(self.client, self.registration,
                               self.attempt if attempt is None else attempt, event)
        if event == abi.ABORTED or (event == abi.BEGIN and result != abi.ALLOW):
            self.active = False
        return result


@pytest.fixture
def installed(bridge, monkeypatch):
    monkeypatch.delenv('CAE_POST_EXIT_PLUGIN', raising=False)
    monkeypatch.delenv('CAE_POST_PARAVIEW_ROOT', raising=False)
    owner = bridge.module.Owner()
    dispatch = bridge.module.GuiDispatch(owner).install()
    controls = Controls(owner, Platform(), busy=lambda: dispatch.command_gate.executing,
                        on_closed=dispatch.close)
    dispatch.native_controls = controls
    library = Library()
    session = adapter.Session(dispatch, library, bridge.module.p).install()
    dispatch.native_exit = session
    yield SimpleNamespace(owner=owner, dispatch=dispatch, controls=controls,
                          library=library, session=session, bridge=bridge)
    library.detach_error = False
    if not session.closed:
        session.close()
    if not dispatch.closed:
        dispatch.command_gate.complete()
        dispatch.close()


def dirty(item):
    item.bridge.view.edit('CameraPosition', [4, 5, 6])
    item.owner.refresh()


@pytest.mark.parametrize('choice,decision,saves', [('cancel', abi.BLOCK, 0),
                         ('discard', abi.ALLOW, 0), ('save', abi.ALLOW, 1)])
def test_three_choices_use_existing_owner_and_no_duplicate_win32_prompt(installed, choice, decision, saves):
    i = installed
    dirty(i)
    i.library.choice = choice
    before = deepcopy(i.owner.snapshot)
    assert i.controls.window_message(WM_CLOSE) is False  # Native Qt gate owns this event.
    assert i.library.prompts == 0
    assert i.library.emit(abi.BEGIN) == decision
    assert i.library.prompts == 1
    assert len(i.bridge.saved) == saves
    assert not i.owner.closed
    if decision == abi.ALLOW:
        assert i.library.emit(abi.VALIDATE) == abi.ALLOW
        assert i.library.prompts == 1
        assert i.library.emit(abi.ABORTED) == abi.ALLOW
    assert not i.controls.in_action
    assert i.owner.snapshot['views'] == before['views']


def test_clean_close_still_revalidated_before_actual_close(installed):
    i = installed
    assert i.library.emit(abi.BEGIN) == abi.ALLOW
    assert i.library.prompts == 0
    dirty(i)
    assert i.library.emit(abi.VALIDATE) == abi.BLOCK
    assert not i.owner.closed
    i.library.emit(abi.ABORTED)
    i.library.choice = 'discard'
    assert i.library.emit(abi.BEGIN) == abi.ALLOW
    assert i.library.prompts == 1


def test_same_unchecked_property_name_different_value_is_not_same_state(installed):
    i = installed
    prop = i.bridge.source.props['PointArrays']
    prop.unchecked = ['unapplied first']
    i.owner.refresh()
    initial = deepcopy(i.owner.snapshot)
    i.library.choice = 'discard'
    i.library.prompt = lambda: setattr(prop, 'unchecked', ['unapplied second'])
    assert i.library.emit(abi.BEGIN) == abi.BLOCK
    assert i.owner.snapshot == initial  # Regression: old snapshot could not distinguish this!
    assert prop.unchecked == ['unapplied second']
    assert i.library.errors and not i.owner.closed


def test_pending_save_block_then_retry_after_apply(installed):
    i = installed
    prop = i.bridge.source.props['PointArrays']
    prop.unchecked = ['different']
    i.library.choice = 'save'
    assert i.library.emit(abi.BEGIN) == abi.BLOCK
    assert not i.bridge.saved and prop.unchecked == ['different']
    prop.unchecked = []
    i.bridge.source.edit('PointArrays', ['different'])
    assert i.library.emit(abi.BEGIN) == abi.ALLOW
    assert len(i.bridge.saved) == 1
    assert i.owner.saved_revision == 'saved'


def test_write_failure_preserves_old_revision_then_success(installed, monkeypatch):
    i = installed
    dirty(i)
    original = i.owner.save_project
    old_revision = i.owner.saved_revision
    monkeypatch.setattr(i.owner, 'save_project', lambda: (_ for _ in ()).throw(OSError('disk full')))
    i.library.choice = 'save'
    assert i.library.emit(abi.BEGIN) == abi.BLOCK
    assert i.owner.saved_revision == old_revision and not i.owner.closed
    assert not i.controls.in_action
    monkeypatch.setattr(i.owner, 'save_project', original)
    assert i.library.emit(abi.BEGIN) == abi.ALLOW
    assert i.library.emit(abi.VALIDATE) == abi.ALLOW


def test_save_without_committed_receipt_cannot_authorize_close(installed, monkeypatch):
    i = installed
    dirty(i)
    def fake_save():
        i.owner.saved_generation = i.owner.generation
        i.owner.saved_view_generation = i.owner.view_generation
        i.owner.saved_revision = ''
    monkeypatch.setattr(i.owner, 'save_project', fake_save)
    i.library.choice = 'save'
    assert i.library.emit(abi.BEGIN) == abi.UNKNOWN
    assert not i.owner.closed


def test_change_during_save_stays_dirty(installed, monkeypatch):
    i = installed
    dirty(i)
    original = i.owner.save_project
    def save_then_change():
        original()
        i.bridge.view.edit('CameraPosition', [7, 8, 9])
    monkeypatch.setattr(i.owner, 'save_project', save_then_change)
    i.library.choice = 'save'
    assert i.library.emit(abi.BEGIN) == abi.BLOCK
    assert i.owner.descriptor()['dirty'] and i.owner.saved_revision == 'saved'


@pytest.mark.parametrize('busy,decision', [(1, abi.BLOCK), (2, abi.UNKNOWN)])
def test_native_progress_busy_or_unknown_never_looks_clean(installed, busy, decision):
    i = installed
    i.library.busy = busy
    assert i.library.emit(abi.BEGIN) == decision
    assert i.library.prompts == 0 and not i.owner.closed


def test_busy_after_dialog_and_before_final_review(installed):
    i = installed
    dirty(i)
    i.library.choice = 'discard'
    i.library.prompt = lambda: setattr(i.library, 'busy', 1)
    assert i.library.emit(abi.BEGIN) == abi.BLOCK
    i.library.prompt = lambda: None
    i.library.busy = 0
    assert i.library.emit(abi.BEGIN) == abi.ALLOW
    i.library.busy = 1
    assert i.library.emit(abi.VALIDATE) == abi.BLOCK
    i.library.emit(abi.ABORTED)
    assert not i.owner.closed


def test_native_dispatch_executing_cannot_close(installed):
    i = installed
    i.dispatch.command_gate.stage(command(i.owner), i.dispatch.outgoing)
    i.dispatch.command_gate.acknowledge_started('Cone')
    assert i.dispatch.command_gate.take()
    assert i.library.emit(abi.BEGIN) == abi.BLOCK
    assert not i.dispatch.closed and i.dispatch.command_gate.executing


def test_allow_does_not_cleanup_and_stock_veto_keeps_queue_timer_owner(installed):
    i = installed
    dirty(i)
    i.library.choice = 'discard'
    i.dispatch.incoming.put(command(i.owner))
    assert i.library.emit(abi.BEGIN) == abi.ALLOW
    assert i.controls.in_action
    i.dispatch._tick()
    assert i.dispatch.incoming.qsize() == 1 and i.dispatch.command_gate.request is None
    assert i.bridge.view.interactor.callbacks and not i.owner.closed
    assert i.library.emit(abi.ABORTED) == abi.ALLOW
    assert not i.controls.in_action and not i.session.in_action
    i.dispatch._tick()
    assert i.dispatch.command_gate.request is not None


def test_modal_heartbeat_stays_live_but_does_not_execute_queued_edits(installed):
    i = installed
    i.dispatch._tick()
    i.dispatch._last_heartbeat = 0
    i.dispatch.incoming.put(command(i.owner))
    assert i.library.emit(abi.BEGIN) == abi.ALLOW
    i.dispatch._tick()
    events = []
    while not i.dispatch.outgoing.empty():
        events.append(i.dispatch.outgoing.get())
    assert any(item['event'] == 'heartbeat' for item in events)
    assert i.dispatch.incoming.qsize() == 1


def test_stale_unknown_and_exception_callbacks_fail_closed(installed, monkeypatch):
    i = installed
    callback = adapter._CALLBACK
    assert callback(i.session.client, i.session.registration + 1, 1, abi.BEGIN) == abi.UNKNOWN
    assert callback(i.session.client + 10000, i.session.registration, 1, abi.BEGIN) == abi.UNKNOWN
    assert callback(i.session.client, i.session.registration, 1, 7654) == abi.UNKNOWN
    monkeypatch.setattr(i.owner, 'assert_thread', lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert callback(i.session.client, i.session.registration, 1, abi.BEGIN) == abi.UNKNOWN
    monkeypatch.undo()


def test_stale_final_callback_cannot_retire_current_owner(installed):
    i = installed
    assert i.library.emit(abi.BEGIN) == abi.ALLOW
    assert i.library.emit(abi.CLOSED, attempt=9999) == abi.UNKNOWN
    assert not i.owner.closed
    i.library.emit(abi.ABORTED)
    assert i.library.emit(abi.CLOSED) == abi.UNKNOWN


def test_actual_closed_callback_reuses_existing_receipt_and_cleanup(installed):
    i = installed
    receipts = []
    i.dispatch.broker_close = lambda: receipts.append('closed')
    i.dispatch.incoming.put(command(i.owner))
    assert i.library.emit(abi.BEGIN) == abi.ALLOW
    assert i.library.emit(abi.VALIDATE) == abi.ALLOW
    assert i.library.emit(abi.CLOSED) == abi.ALLOW
    assert i.session.closed and i.owner.closed and i.dispatch.closed
    assert not i.bridge.source.observers and not i.bridge.view.interactor.callbacks
    assert i.bridge.view.interactor.destroyed == 17
    assert i.dispatch.incoming.empty() and receipts == ['closed']
    assert i.session.client not in adapter._clients and not i.library.registration
    i.dispatch.close()
    assert receipts == ['closed']


@pytest.mark.parametrize('event', [abi.DESTROYED, abi.SHUTDOWN])
def test_nonvetoable_lifecycle_is_only_cleanup_not_a_save_dialog(installed, event):
    i = installed
    dirty(i)
    assert i.library.emit(event) == abi.ALLOW
    assert not i.library.prompts and not i.bridge.saved
    assert i.dispatch.closed


def test_detach_failure_retains_registration_and_can_retry(installed):
    i = installed
    i.library.detach_error = True
    with pytest.raises(abi.NativeExitUnavailable):
        i.session.close()
    assert not i.session.closed and i.session.client in adapter._clients
    assert i.controls.qt_close_gate_active
    i.library.detach_error = False
    i.session.close()
    assert i.session.closed and not getattr(i.controls, 'qt_close_gate_active', False)


def test_dispatch_close_detach_failure_keeps_owner_and_pending_work_for_retry(installed):
    item = installed
    item.dispatch.incoming.put(command(item.owner, 'document.save'))
    item.library.detach_error = True
    with pytest.raises(abi.NativeExitUnavailable, match='detach failed'):
        item.dispatch.close()
    assert not item.dispatch.closed and not item.owner.closed and not item.controls.closed
    assert not item.session.closed and item.library.registration == item.session.registration
    assert item.dispatch.incoming.qsize() == 1 and item.owner._observers
    assert item.dispatch.interactor.callbacks
    assert item.dispatch.outgoing.empty()
    item.library.detach_error = False
    item.dispatch.close()
    assert item.dispatch.closed and item.owner.closed and item.session.closed
    assert item.dispatch.incoming.empty() and not item.owner._observers


def test_closed_notification_detach_failure_is_unknown_without_partial_retirement(installed):
    item = installed
    dirty(item)
    item.library.choice = 'discard'
    assert item.library.emit(abi.BEGIN) == abi.ALLOW
    assert item.library.emit(abi.VALIDATE) == abi.ALLOW
    item.library.detach_error = True
    assert item.library.emit(abi.CLOSED) == abi.UNKNOWN
    assert not item.dispatch.closed and not item.owner.closed and not item.controls.closed
    assert item.session.in_action and item.library.registration == item.session.registration
    item.library.detach_error = False
    assert item.library.emit(abi.CLOSED) == abi.ALLOW
    assert item.dispatch.closed and item.owner.closed and item.session.closed


def test_exact_window_mismatch_rejected_without_new_registration(installed):
    i = installed
    i.session.close()
    i.controls.main = 987
    candidate = adapter.Session(i.dispatch, i.library, i.bridge.module.p)
    with pytest.raises(abi.NativeExitUnavailable, match='do not match'):
        candidate.install()
    assert not i.library.registration and candidate.client not in adapter._clients


def test_three_open_close_cycles_have_no_owner_callback_timer_observer_accumulation(bridge, monkeypatch):
    monkeypatch.delenv('CAE_POST_EXIT_PLUGIN', raising=False)
    library = Library()
    references = []
    for _ in range(3):
        owner = bridge.module.Owner()
        dispatch = bridge.module.GuiDispatch(owner).install()
        controls = Controls(owner, Platform(), busy=lambda: dispatch.command_gate.executing)
        dispatch.native_controls = controls
        session = adapter.Session(dispatch, library, bridge.module.p).install()
        dispatch.native_exit = session
        references.append(weakref.ref(owner))
        assert len(bridge.source.observers) == 1
        assert len(bridge.view.interactor.callbacks) == 1
        assert library.emit(abi.BEGIN) == abi.ALLOW
        assert library.emit(abi.VALIDATE) == abi.ALLOW
        assert library.emit(abi.CLOSED) == abi.ALLOW
        assert not bridge.source.observers and not bridge.view.interactor.callbacks
        del owner, dispatch, controls, session
        gc.collect()
        assert all(ref() is None for ref in references)
    assert library.sequence == 3 and not library.registration


@pytest.mark.parametrize('field,value', [('dirty', None), ('dirty', 'UNKNOWN')])
def test_unknown_descriptor_not_coerced_to_boolean(field, value):
    owner = SmallOwner()
    owner.descriptor = lambda: {field: value}
    controls = Controls(owner, Platform('discard'))
    assert controls.close_decision().decision == 'unknown'


def test_unchecked_fingerprint_exception_preserves_window(installed, monkeypatch):
    i = installed
    monkeypatch.setattr(i.controls, 'close_fingerprint', lambda: (_ for _ in ()).throw(RuntimeError('RPC failed')))
    assert i.library.emit(abi.BEGIN) == abi.UNKNOWN
    assert not i.owner.closed


def test_missing_plugin_is_explicit_degraded_mode(installed, monkeypatch, capsys):
    monkeypatch.delenv('CAE_POST_EXIT_PLUGIN', raising=False)
    assert adapter.install(installed.dispatch) is None
    assert 'File > Exit/Ctrl+Q는 보호되지 않습니다' in capsys.readouterr().out


def make_manifest(tmp_path):
    runtime = tmp_path / 'runtime'
    (runtime / 'bin').mkdir(parents=True)
    pins = {}
    for name in ['paraview.exe', 'Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll', 'python312.dll', 'pqCore.dll']:
        path = runtime / 'bin' / name
        path.write_bytes(name.encode())
        pins['bin/' + name] = abi.file_sha256(path)
    plugin = tmp_path / 'CaePostExit.dll'
    plugin.write_bytes(b'identity-test-only-NOT-A-WINDOWS-DLL')
    manifest = dict(schema='cae.post-exit-artifact/1', abi=1,
                    plugin_sha256=abi.file_sha256(plugin), runtime_files=pins,
                    build=dict(paraview='6.2.0', qt='6.9.0', configuration='Release',
                               pointer_bits=64, sdk_evidence_sha256='recorded-evidence'))
    sidecar = plugin.with_suffix('.dll.manifest.json')
    sidecar.write_text(json.dumps(manifest))
    return plugin, runtime, sidecar, manifest


def test_manifest_identity_is_checked_without_loading_dll(tmp_path):
    plugin, runtime, _, manifest = make_manifest(tmp_path)
    assert abi.verify_artifact(plugin, runtime) == manifest
    plugin.write_bytes(b'changed')
    with pytest.raises(abi.NativeExitUnavailable, match='hash mismatch'):
        abi.verify_artifact(plugin, runtime)


@pytest.mark.parametrize('mutate', ['runtime', 'configuration', 'sdk', 'abi', 'incomplete', 'escape'])
def test_incompatible_or_incomplete_manifest_rejected(tmp_path, mutate):
    plugin, runtime, sidecar, manifest = make_manifest(tmp_path)
    if mutate == 'runtime':
        (runtime / 'bin/Qt6Core.dll').write_bytes(b'different Qt build')
    elif mutate == 'configuration':
        manifest['build']['configuration'] = 'Debug'
    elif mutate == 'sdk':
        manifest['build']['sdk_evidence_sha256'] = ''
    elif mutate == 'abi':
        manifest['abi'] = 2
    elif mutate == 'incomplete':
        del manifest['runtime_files']['bin/pqCore.dll']
    else:
        outside = tmp_path / 'outside.dll'
        outside.write_bytes(b'outside')
        manifest['runtime_files']['../outside.dll'] = abi.file_sha256(outside)
    sidecar.write_text(json.dumps(manifest))
    with pytest.raises(abi.NativeExitUnavailable):
        abi.verify_artifact(plugin, runtime)


def test_c_abi_layout_and_callback_types():
    assert ctypes.sizeof(abi.Status) == 96
    assert abi.Status.pid.offset == 8 and abi.Status.client.offset == 40
    assert abi.Status.ready.offset == 48 and abi.Status.last_decision.offset == 88
    assert adapter._CALLBACK(2**63, 2**63, 2**63, abi.BEGIN) == abi.UNKNOWN


def test_invalid_native_text_prompts_but_save_cannot_erase_it(installed):
    i = installed
    i.library.ui_draft['unapplied'] = True
    i.library.choice = 'save'
    assert not i.owner.descriptor()['dirty']
    assert i.library.emit(abi.BEGIN) == abi.BLOCK
    assert i.library.prompts == 1 and not i.bridge.saved and not i.owner.closed
    i.library.choice = 'cancel'
    assert i.library.emit(abi.BEGIN) == abi.BLOCK
    i.library.choice = 'discard'
    assert i.library.emit(abi.BEGIN) == abi.ALLOW


def test_ctrl_s_preserves_native_draft_until_apply(installed):
    i = installed
    i.library.ui_draft['unapplied'] = True
    before = deepcopy(i.library.ui_draft)
    i.controls.key_message()
    assert not i.bridge.saved and not i.owner.closed
    assert i.library.ui_draft == before and not i.controls.in_action
    assert '적용하지 않은 변경' in i.library.errors[-1]
    i.library.ui_draft['unapplied'] = False
    i.controls.key_message()
    assert len(i.bridge.saved) == 1 and not i.owner.closed


@pytest.mark.parametrize('pending', [None, 1])
def test_ctrl_s_unknown_native_draft_does_not_save(installed, pending):
    i = installed
    i.library.ui_draft['unapplied'] = pending
    i.controls.key_message()
    assert not i.bridge.saved and not i.owner.closed and not i.controls.in_action
    assert i.library.errors


def test_ctrl_s_native_draft_read_failure_does_not_save(installed, monkeypatch):
    i = installed

    def unavailable(*args):
        raise OSError('draft unavailable')

    monkeypatch.setattr(i.library, 'draft', unavailable)
    i.controls.key_message()
    assert not i.bridge.saved and not i.owner.closed and not i.controls.in_action
    assert i.library.errors


def test_native_widget_text_change_with_same_sm_snapshot_expires_permission(installed):
    i = installed
    dirty(i)
    i.library.choice = 'discard'
    i.library.prompt = lambda: i.library.ui_draft.update(sha256='f'*64)
    assert i.library.emit(abi.BEGIN) == abi.BLOCK
    assert not i.owner.closed


@pytest.mark.parametrize('result', [None, True, 'allow', 2, -999])
def test_malformed_python_callback_return_is_unknown_not_an_uninitialized_c_result(installed, monkeypatch, result):
    i = installed
    monkeypatch.setattr(i.session, 'on_event', lambda *_: result)
    assert adapter._CALLBACK(i.session.client, i.session.registration, 1, abi.BEGIN) == abi.UNKNOWN


def test_windows_check_refuses_missing_root_job_runner_before_any_launch(tmp_path):
    from scripts.post_native_exit_check import load_job_runner
    with pytest.raises(RuntimeError, match='ROOT_INPUT_MISSING'):
        load_job_runner(tmp_path)


def test_windows_check_refuses_original_project_outside_scratch(tmp_path):
    from scripts.post_native_exit_check import validate_project
    run = tmp_path / 'run'
    (run / 'scratch').mkdir(parents=True)
    original = tmp_path / 'original.json'
    original.write_text(json.dumps({'kind': 'external-result', 'project_root': str(tmp_path)}))
    with pytest.raises(ValueError, match='dedicated project'):
        validate_project(original, run)
    inside = run / 'scratch/project.json'
    inside.write_text(original.read_text())
    with pytest.raises(ValueError, match='outside'):
        validate_project(inside, run)


def test_artifact_tool_refuses_text_renamed_as_a_dll(tmp_path):
    from scripts.post_exit_artifact import require_pe64
    candidate = tmp_path / 'fake.dll'
    candidate.write_text('not a binary')
    with pytest.raises(ValueError, match='Not a Windows PE DLL'):
        require_pe64(candidate)
