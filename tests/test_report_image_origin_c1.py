"""Real Report owner and pin I/O; scripted registry/transport/launcher only.

No subprocess, ParaView, provider, solver or operating-system PID probe occurs.
"""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.research import desktop
from apps.research import report_image_origin as navigation
from caelab import report_image as images
from caelab.storage import canonical_hash
from report_image_fixture import fixture
from test_report_image_core import owner, command


class Client:
    url = 'http://127.0.0.1:18766'

    def __init__(self, f, store, doc, binding):
        self.f, self.store, self.doc, self.binding = f, store, doc, binding
        self.native = {'id': 'Dpost', 'kind': 'post', 'session_id': 'Snative', 'connected': True,
            'saved_revision': f['snapshot']['origin']['workspace']['sha256'], 'generation': 4, 'view_generation': 3,
            'dirty': False, 'capabilities': ['post.report_image_verify', 'document.activate'],
            'state': {'fresh': True, 'pid': 456789, 'analysis': {'objects': [deepcopy(f['object'])]}}}
        self.commands, self.polls, self.receipts = [], [], {}
        self.additional = []
        self.modify_reply = lambda command: None
        self.modify_read = lambda document: None
        self.reads = 0
        self.lose_reply = False

    def report_content(self, identifier, bindings):
        return self.store.content(identifier, bindings)

    def documents(self):
        return {'documents': deepcopy(([self.native] if self.native else []) + self.additional)}

    def document_read(self, identifier):
        assert identifier == 'Dpost'; self.reads += 1
        value = deepcopy(self.native); self.modify_read(value)
        return value

    def document_command(self, identifier, operation, arguments, **kwargs):
        assert operation == 'post.report_image_verify'  # No capture/calculation mutation may hide here.
        request = {'document_id': identifier, 'operation': operation, 'arguments': deepcopy(arguments), **kwargs}
        result = {'status': 'SOURCE_VERIFIED', 'origin_sha256': canonical_hash(arguments['origin']),
            **{key: arguments['origin'][key] for key in ('object_ref', 'revision', 'result_sha256')},
            'native_pid': self.native['state']['pid'], 'generation': self.native['generation'],
            'view_generation': self.native['view_generation'], 'historical_view_restored': False}
        reply = {**request, 'state': 'SUCCEEDED', 'outcome': {'state': 'SUCCEEDED', 'result': {
            **{key: request[key] for key in ('command_id', 'document_id', 'session_id')},
            'status': 'COMPLETED', 'result': result}}}
        self.commands.append(deepcopy(request)); self.modify_reply(reply)
        self.receipts[request['command_id']] = deepcopy(reply)
        if self.lose_reply:
            raise OSError('scripted receipt loss after dispatch')
        return reply

    def command_status(self, identifier):
        self.polls.append(identifier)
        return deepcopy(self.receipts[identifier])


@pytest.fixture
def setup(tmp_path, monkeypatch):
    f = fixture(tmp_path/'원 Post'); store = owner(tmp_path/'Report'); doc = store.open()
    binding = store.capture_image(doc['id'], f['command']); asset = store.asset(doc['id'], binding)
    draft = images.apply_binding(doc['draft'], binding, asset['content'])
    draft['sections'][0]['text'] = '기존 본문·Study 판단·다음 연구는 보존한다.'
    doc = command(store, doc, 'report.update', {'draft': draft}); doc = command(store, doc, 'document.save')
    client = Client(f, store, doc, binding)
    calls = {'spawn': [], 'activate': [], 'confirm': []}
    monkeypatch.setattr(desktop, '_native_pid_alive', lambda pid: False)
    def spawn(client, args):
        calls['spawn'].append(deepcopy(args)); return {'status': 'LAUNCH_REQUESTED', 'pid': 123456, 'service_url': client.url}
    def activate(client, tool, **kwargs):
        assert tool == 'post'; calls['activate'].append(kwargs)
        return {'status': 'ACTIVATED', 'document_id': kwargs['document_id'], 'command_id': 'Cactivate'}
    monkeypatch.setattr(desktop, '_spawn', spawn)
    monkeypatch.setattr(desktop, 'launch_tool', activate)
    monkeypatch.setattr(desktop, '_confirm_post_launch', lambda *args: calls['confirm'].append(args[2]))
    session = navigation.OriginSession(client, doc['id'], binding)
    return SimpleNamespace(f=f, store=store, doc=doc, binding=binding, asset=asset,
                           client=client, calls=calls, session=session, tmp=tmp_path)


def preserved(s):
    assert s.store.read(s.doc['id']) == s.doc
    assert s.store.asset(s.doc['id'], s.binding) == s.asset
    assert s.store.read(s.doc['id'])['runs'] == []


def test_exact_live_source_verified_then_existing_native_activation(setup):
    s = setup; result = s.session.open()
    assert result['status'] == 'SOURCE_OPENED' and result['activation_status'] == 'CONFIRMED'
    assert result['historical_view_restored'] is False
    assert len(s.client.commands) == 1 and s.calls['activate'] == [{'document_id': 'Dpost'}]
    assert s.calls['spawn'] == [] and s.calls['confirm'] == [456789]
    preserved(s)


@pytest.mark.parametrize('change', ['content', 'view', 'revision', 'workspace', 'fresh', 'missingObject', 'capability', 'duplicate'])
def test_live_changed_state_never_overwritten_or_opened_as_past_exact_result(setup, change):
    s = setup; n = s.client.native
    if change == 'content': n['generation'] += 1
    if change == 'view': n['view_generation'] += 1
    if change == 'revision': n['state']['analysis']['objects'][0]['history'][0]['id'] = 'Rother'
    if change == 'workspace': n['saved_revision'] = 'b'*64
    if change == 'fresh': n['state']['fresh'] = False
    if change == 'missingObject': n['state']['analysis']['objects'] = []
    if change == 'capability': n['capabilities'] = ['document.activate']
    if change == 'duplicate': s.client.additional = [deepcopy(n)]
    with pytest.raises(ValueError): s.session.open()
    assert not s.client.commands and not s.calls['spawn'] and not s.calls['activate']
    preserved(s)


@pytest.mark.parametrize('state', ['FAILED', 'UNKNOWN', 'CANCELLED', 'INTERRUPTED'])
def test_native_failure_unknown_does_not_fallback_to_another_window(setup, state):
    s = setup; s.client.modify_reply = lambda reply: reply.update(state=state)
    with pytest.raises(RuntimeError): s.session.open()
    with pytest.raises(RuntimeError): s.session.poll()
    assert len(s.client.commands) == 1 and s.client.polls == [s.client.commands[0]['command_id']]
    assert not s.calls['spawn'] and not s.calls['activate']; preserved(s)


@pytest.mark.parametrize('fault', ['commandId', 'session', 'operation', 'argument', 'outcome', 'envelope', 'originHash', 'resultHash', 'pid', 'generation', 'viewGeneration'])
def test_wrong_receipt_is_not_source_open_success(setup, fault):
    s = setup
    def alter(reply):
        result = reply['outcome']['result']['result']
        if fault == 'commandId': reply['command_id'] = 'Cwrong'
        if fault == 'session': reply['session_id'] = 'Sother'
        if fault == 'operation': reply['operation'] = 'post.export'
        if fault == 'argument': reply['arguments']['expected_view_generation'] = 99
        if fault == 'outcome': reply['outcome']['state'] = 'FAILED'
        if fault == 'envelope': reply['outcome']['result']['status'] = 'UNKNOWN'
        if fault == 'originHash': result['origin_sha256'] = 'c'*64
        if fault == 'resultHash': result['result_sha256'] = 'd'*64
        if fault == 'pid': result['native_pid'] = 987654
        if fault == 'generation': result['generation'] += 1
        if fault == 'viewGeneration': result['view_generation'] += 1
    s.client.modify_reply = alter
    with pytest.raises((ValueError, RuntimeError)): s.session.open()
    assert not s.calls['activate'] and not s.calls['spawn']; preserved(s)


def test_lost_verify_reply_polls_same_command_id_not_resubmission(setup):
    s = setup; s.client.lose_reply = True
    with pytest.raises(OSError): s.session.open()
    result = s.session.poll()
    assert result['status'] == 'SOURCE_OPENED'
    assert len(s.client.commands) == 1 and s.client.polls == [s.client.commands[0]['command_id']]
    assert not s.calls['spawn']; preserved(s)


def test_native_without_activation_does_not_claim_focus_but_real_verification_is_separate(setup):
    s = setup; s.client.native['capabilities'].remove('document.activate')
    result = s.session.open()
    assert result['status'] == 'SOURCE_VERIFIED' and result['activation_status'] == 'NOT_PERFORMED'
    assert '활성화는 확인되지' in result['message'] and not s.calls['activate']
    assert not s.calls['spawn']; preserved(s)


@pytest.mark.parametrize('target', ['source', 'result', 'state', 'manifest'])
@pytest.mark.parametrize('fault', ['missing', 'hash'])
def test_file_pin_failure_preserves_report_and_does_not_launch(setup, target, fault):
    s = setup
    if fault == 'missing': s.f[target].unlink()
    else: s.f[target].write_bytes(s.f[target].read_bytes() + b'CHANGED')
    with pytest.raises(ValueError, match='원 Post project/result'): s.session.open()
    assert not s.client.commands and not s.calls['spawn'] and not s.calls['activate']; preserved(s)


def test_tampered_report_binding_is_not_a_launch_specification(setup):
    s = setup; s.session.spec['binding']['reference']['snapshot_sha256'] = 'e'*64
    with pytest.raises(ValueError): s.session.open()
    assert not s.calls['spawn'] and not s.calls['activate']; preserved(s)


@pytest.mark.parametrize('alive', [True, None])
def test_disconnected_pid_uncertainty_does_not_spawn(setup, monkeypatch, alive):
    s = setup; s.client.native['connected'] = False
    monkeypatch.setattr(desktop, '_native_pid_alive', lambda pid: alive)
    with pytest.raises(ValueError, match='종료 여부'): s.session.open()
    assert not s.calls['spawn']; preserved(s)


def test_cold_launch_request_is_not_success_poll_does_not_spawn_again(setup):
    s = setup; native = s.client.native; s.client.native = None
    result = s.session.open()
    assert result['status'] == 'LAUNCH_REQUESTED' and len(s.calls['spawn']) == 1
    args = s.calls['spawn'][0]
    assert args[:2] == ['post', '--report-image']
    assert json.loads(args[2]) == s.session.spec
    assert s.session.poll()['status'] == 'LAUNCH_UNCONFIRMED'
    assert len(s.calls['spawn']) == 1 and not s.client.commands
    s.client.native = native; native.update(session_id='Sreopened', generation=8, view_generation=2, dirty=False)
    result = s.session.poll()
    assert result['status'] == 'SOURCE_OPENED' and len(s.calls['spawn']) == 1
    assert result['historical_view_restored'] is False
    with pytest.raises(ValueError): s.session.open()
    preserved(s)


def test_cold_reopened_but_edited_owner_is_not_report_origin(setup):
    s = setup; s.client.native.update(session_id='Sreopened', dirty=True)
    with pytest.raises(ValueError, match='다른 상태'): s.session.open()
    assert not s.calls['spawn'] and not s.calls['activate']; preserved(s)


def test_change_between_verify_and_activation_is_detected(setup):
    s = setup
    def read(value):
        if s.client.reads >= 2: value['view_generation'] += 1
    s.client.modify_read = read
    with pytest.raises(ValueError, match='검증 뒤'): s.session.open()
    assert not s.calls['activate']; preserved(s)


def test_change_during_activation_is_not_claimed_past_exact(setup, monkeypatch):
    s = setup
    def activation(*args, **kwargs):
        s.client.native['generation'] += 1
        return {'status': 'ACTIVATED', 'document_id': 'Dpost'}
    monkeypatch.setattr(desktop, 'launch_tool', activation)
    with pytest.raises(ValueError, match='활성화 중'): s.session.open()
    assert not s.calls['spawn']; preserved(s)


def test_file_removed_after_native_receipt_prevents_activation(setup):
    s = setup; s.client.modify_reply = lambda receipt: s.f['source'].unlink()
    with pytest.raises(OSError): s.session.open()
    assert not s.calls['activate']; preserved(s)


def test_activation_failure_has_no_browser_or_second_window_fallback(setup, monkeypatch):
    s = setup
    monkeypatch.setattr(desktop, 'launch_tool', lambda *args, **kwargs: {'status': 'UNKNOWN'})
    with pytest.raises(RuntimeError, match='활성화'): s.session.open()
    assert not s.calls['spawn']; preserved(s)


def child_args(s):
    return desktop._arguments(['post', '--report-image', json.dumps(s.session.spec, ensure_ascii=False)])


@pytest.mark.parametrize('fault,phase,removed', [('preflight', 'PREPARING', True), ('spawn', 'NOT_CREATED', True),
    ('interrupt', 'SPAWNING', False), ('afterSpawn', 'CREATED', False)])
def test_child_claim_confirmed_failure_vs_unknown_recovery(setup, monkeypatch, fault, phase, removed):
    s = setup; marker = s.tmp/'existing-native-launch.json'; locks = []
    monkeypatch.setattr(navigation, '_open', lambda *args, **kwargs: None)
    monkeypatch.setattr(desktop, '_post_launch_claim', lambda *args: (SimpleNamespace(unlock=lambda: locks.append('released')), marker))
    def start(client, args, **kwargs):
        assert args.project == s.f['snapshot']['origin']['project']['path'] and args.report_image is None
        kwargs['_report_launch']['phase'] = phase
        if fault == 'interrupt': raise KeyboardInterrupt('scripted interrupt')
        raise OSError('scripted failure')
    monkeypatch.setattr(desktop, '_post', start)
    with pytest.raises((OSError, KeyboardInterrupt)): navigation.launch_saved_project(s.client, child_args(s))
    assert marker.exists() != removed and locks == ['released']; preserved(s)


def test_child_reuses_saved_project_launch_and_marks_only_verified_native_pid(setup, monkeypatch):
    s = setup; marker = s.tmp/'existing-native-launch.json'; starts = []; locks = []; sequence = []
    def open_(client, spec, **kwargs):
        sequence.append(kwargs)
        return None if len(sequence) < 3 else {'status': 'SOURCE_VERIFIED', 'native_pid': 445566, 'historical_view_restored': False}
    monkeypatch.setattr(navigation, '_open', open_)
    monkeypatch.setattr(desktop, '_post_launch_claim', lambda *args: (SimpleNamespace(unlock=lambda: locks.append('released')), marker))
    def start(client, args, **kwargs):
        assert args.project == str(s.f['manifest']) and args.report_image is None
        assert kwargs['_report_origin'] == s.f['snapshot']['origin']
        kwargs['_report_launch'].update(phase='CREATED', pid=8899); starts.append(args)
        return {'status': 'LAUNCHED', 'pid': 8899}
    monkeypatch.setattr(desktop, '_post', start)
    result = navigation.launch_saved_project(s.client, child_args(s))
    assert len(starts) == 1 and result['launch_status'] == 'CONFIRMED'
    assert json.loads(marker.read_text())['native_pid'] == 445566
    assert locks == ['released']; preserved(s)


def test_child_launch_timeout_preserves_unknown_claim_no_automatic_retry(setup, monkeypatch):
    s = setup; marker = s.tmp/'existing-native-launch.json'; starts = []; ticks = iter([0., 100.])
    monkeypatch.setattr(navigation, '_open', lambda *args, **kwargs: None)
    monkeypatch.setattr(desktop, '_post_launch_claim', lambda *args: (SimpleNamespace(unlock=lambda: None), marker))
    def start(client, args, **kwargs):
        kwargs['_report_launch'].update(phase='CREATED', pid=3333); starts.append(args)
        return {'status': 'LAUNCHED', 'pid': 3333}
    monkeypatch.setattr(desktop, '_post', start)
    monkeypatch.setattr(navigation, 'time', SimpleNamespace(monotonic=lambda: next(ticks), sleep=lambda _: None))
    with pytest.raises(RuntimeError, match='미확인'): navigation.launch_saved_project(s.client, child_args(s))
    assert len(starts) == 1 and json.loads(marker.read_text())['state'] == 'LAUNCH_REQUESTED'
    preserved(s)


@pytest.mark.parametrize('flag', ['job_id', 'research_source', 'prepare_only'])
def test_child_cannot_mix_other_jobs_or_preparation(setup, flag):
    s = setup; args = child_args(s); setattr(args, flag, True if flag == 'prepare_only' else 'not permitted')
    with pytest.raises(ValueError, match='섞지'): navigation.launch_saved_project(s.client, args)
    assert not s.calls['spawn']; preserved(s)


def test_successful_poll_does_not_dispatch_activation_again(setup):
    s = setup
    assert s.session.open()['status'] == 'SOURCE_OPENED'
    assert s.session.poll()['status'] == 'SOURCE_OPENED'
    assert len(s.client.commands) == 1 and len(s.calls['activate']) == 1
    preserved(s)


def test_activation_receipt_loss_never_reissues_activation_or_launch(setup, monkeypatch):
    s = setup
    def lose(*args, **kwargs):
        s.calls['activate'].append(kwargs)
        raise OSError('scripted activation receipt loss')
    monkeypatch.setattr(desktop, 'launch_tool', lose)
    with pytest.raises(OSError):
        s.session.open()
    with pytest.raises(RuntimeError, match='다시 보내지'):
        s.session.poll()
    assert len(s.calls['activate']) == 1 and len(s.client.commands) == 1
    assert not s.calls['spawn']
    preserved(s)
