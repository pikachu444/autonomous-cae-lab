"""Scoped Qt presentation/dirty/action checks; no provider or solver."""
from copy import deepcopy

import pytest
from PySide6 import QtCore, QtTest, QtWidgets

from apps.research.expert_window import ExpertWindow
from apps.research.research_team_panel import (TeamReviewDialog, install,
    new_team, TEAM_ROLE, ResultSelectionDialog, team_selection_scope)
from caelab.discussion_document import default_draft


ROLES = [{'id': 'structures', 'label': '구조 검토', 'tools': ['results.read'], 'collections': []},
         {'id': 'testing', 'label': '시험 검토', 'tools': [], 'collections': []}]


@pytest.fixture(scope='module')
def app():
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from apps.research.appearance import apply_appearance
    apply_appearance(application)
    return application


def document():
    draft = default_draft()
    draft['composer']['text'] = '선택한 관측으로 변형 원인을 구별할 수 있는가?'
    draft['participants'] = ['structures']
    draft['context']['discussion_mode'] = 'costorm'
    team = new_team(draft)
    team.update(phase_id='Pcurrent', objective=draft['composer']['text'], deliverable='가설과 다음 관측',
        assignments=[{'expert_id': 'structures', 'mode': 'investigator', 'question': '위치와 단위를 확인하세요.',
            'checks': ['선택한 성분'], 'tools': ['results.read'], 'source_refs': [], 'result_refs': []}])
    draft['context']['research_team'] = team
    return {'id': 'Xpublic', 'session_id': 'Spublic', 'title': '공개 연구 표시 검사',
        'generation': 0, 'input_revision': 'Ipublic', 'draft': draft, 'runs': [], 'turns': [],
        'discussion': {'paused': False, 'turns': [], 'rounds': [], 'research_team': {
            'version': 2, 'revision': 1, 'phases': {'Pcurrent': {'id': 'Pcurrent', 'task_ids': ['Tdone', 'Twait']}},
            'tasks': {'Tdone': {'id': 'Tdone', 'actor_id': 'structures', 'kind': 'INITIAL_RESEARCH', 'status': 'COMPLETED'},
                      'Twait': {'id': 'Twait', 'actor_id': 'testing', 'kind': 'INITIAL_RESEARCH', 'status': 'WAITING_BUDGET'}},
            'actions': {'Dold': {'id': 'Dold', 'phase_id': 'Pcurrent', 'task_ids': ['Tdone'], 'origin': 'archived_origin'}},
            'map_pending': {'MapOld': {'id': 'MapOld', 'status': 'ARCHIVED_PENDING'}},
            'responses': {}, 'map_checkpoints': {}}}}


class NoCalls:
    def __getattr__(self, name):
        raise AssertionError('Display/edit made an unexpected client call: ' + name)


@pytest.fixture
def window(app):
    window = ExpertWindow(NoCalls(), auto_open=False, poll_interval=0)
    window._registry = deepcopy(ROLES)
    # Before root applies the shared hunk this installs through the exact same
    # public entry, without replacing any controller or editor methods.
    split = window.centralWidget().findChild(QtWidgets.QSplitter)
    binding = install(window, split, split.widget(0))
    window._show_document(document())
    binding.populate()
    try:
        yield window
    finally:
        window._allow_close = True
        window.close()
        window.deleteLater()
        app.processEvents()


def test_team_review_cancel_and_new_checked_role_preserve_authored_input(window, app):
    original = deepcopy(window.edited_draft())
    dialog = TeamReviewDialog(window, original)
    try:
        dialog.question.setPlainText('바꾸고 취소할 질문')
        dialog.reject()
        assert window.edited_draft() == original
        dialog.roles.topLevelItem(1).setCheckState(0, QtCore.Qt.CheckState.Checked)
        dialog.apply()
        assert len(dialog.accepted_team['assignments']) == 2
        assert dialog.accepted_team['assignments'][1]['question'] == ''
        assert original == window.edited_draft()
    finally:
        dialog.close(); dialog.deleteLater(); app.processEvents()


def test_archived_pending_read_and_resize_do_not_dispatch_or_touch_buffer(window, app):
    window.show(); window.resize(1400, 900); app.processEvents()
    panel = window.research_team.panel
    window.question.setPlainText('미적용 관측과 부분 입력 1e')
    original = deepcopy(window.edited_draft())
    panel.refresh()
    assert '응답 완료 1' in panel.pending.text() and '남은 과제 1' in panel.pending.text()
    assert not panel.map_retry.isEnabled()
    window.resize(900, 700); app.processEvents()
    assert window.research_team.narrow
    assert window.side.indexOf(window.research_team.stack) >= 0
    window.research_team.reveal(); app.processEvents()
    QtTest.QTest.keyClick(panel.tasks, QtCore.Qt.Key.Key_Down)
    window.resize(1400, 900); app.processEvents()
    assert not window.research_team.narrow
    assert window.edited_draft() == original
    assert window.local_dirty


def test_map_retry_uses_existing_empty_progression_without_new_role_request(window):
    state = window.document['discussion']['research_team']
    state['actions']['Dold']['origin'] = 'local'
    state['map_pending']['MapOld']['status'] = 'FAILED'
    called = []
    window.protocol_action = lambda operation, **kwargs: called.append((operation, kwargs))
    window.research_team.panel.refresh()
    assert window.research_team.panel.map_retry.isEnabled()
    window.research_team.panel.map_retry.click()
    assert called == [('expert.retry', {})]


def test_next_phase_is_local_edit_only_and_cancel_keeps_previous_phase(window, app):
    original = deepcopy(window.edited_draft())
    dialog = TeamReviewDialog(window, original, next_phase=True)
    try:
        dialog.objective.setPlainText('새 관측을 반영한 연구 질문')
        dialog.apply()
        assert dialog.accepted_team['phase_id'] is None
        assert dialog.accepted_team['parent_phase_id'] == 'Pcurrent'
        assert dialog.accepted_team['requested_next'] is None
        assert window.edited_draft() == original
        assert not window._workers
    finally:
        dialog.close(); dialog.deleteLater(); app.processEvents()


def test_real_constructor_legacy_and_team_switch_then_saved_unstarted_phase_asks(window):
    binding = window.research_team
    window.protocol_mode.setCurrentIndex(0)
    draft = binding.apply_draft(window.edited_draft())
    assert 'research_team' not in draft['context']
    window.protocol_mode.setCurrentIndex(binding.mode_index)
    assert window.protocol_mode.currentData() == 'costorm'
    assert binding.apply_draft(draft)['context']['research_team']['version'] == 2
    window.document['discussion']['research_team']['phases'].clear()
    called = []
    window.protocol_action = lambda operation, **kwargs: called.append((operation, kwargs))
    binding.start()
    assert called == [('expert.ask', {})]


class SavedResultClient:
    """Only metadata delivery is controlled; C compiles the actual selector."""
    def __init__(self):
        from caelab.research_team_results import descriptor_from_metadata
        from caelab.storage import canonical_hash
        self.calls = []
        self.reference = {'document_id': 'Mone', 'job_id': 'Jone', 'input_revision': 'Ione',
            'input_sha256': 'a' * 64, 'result_sha256': 'b' * 64}
        descriptor = descriptor_from_metadata({'responses': {'u_z': {'label': '판 끝 Z변위',
            'kind': 'series', 'value': [1., 2., 3.], 'unit': 'mm', 'component': 'z',
            'measure': 'displacement', 'frame': 'global', 'source_rows': [10, 12, 14],
            'axes': [{'name': 'time', 'unit': 's', 'values': [0., 1., 1.]}]}}})
        self.metadata = {'research_team_descriptor': {'descriptor': descriptor,
            'descriptor_digest': canonical_hash(descriptor), 'verified_storage_ref': {'retained_revision': 'Rone'}}}

    def documents(self):
        self.calls.append('list')
        return {'documents': [{'id': 'Mone', 'kind': 'material', 'title': '합성 관측 (물리 계산 아님)'}]}

    def document_read(self, identifier):
        self.calls.append(('read', identifier))
        return {'id': identifier, 'runs': [{'job_id': 'Jone', 'retention_complete': True,
            'retained_result': {'revision': 'Rone'}, 'retained_state': 'FAILED'}]}

    def document_result_reference(self, identifier, job):
        self.calls.append(('reference', identifier, job))
        return deepcopy(self.reference)

    def document_result_metadata(self, identifier, job):
        self.calls.append(('metadata', identifier, job))
        return deepcopy(self.metadata)


def wait_for(app, predicate):
    import time
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        # Yield Python as well as Qt: the loopback server and _Call worker
        # both need the interpreter while the visible window stays responsive.
        time.sleep(.005)
    raise AssertionError('Owned metadata callback did not complete')


def test_exact_result_picker_original_rows_units_failed_state_and_cancel_are_local(app):
    client = SavedResultClient()
    dialog = ResultSelectionDialog(client)
    try:
        dialog.show()
        wait_for(app, lambda: dialog.descriptor is not None and not dialog._workers)
        assert '계산 실패' in dialog.runs.currentText()
        assert '판 끝 Z변위' in dialog.channels.currentItem().text()
        dialog.first.setValue(3)
        dialog.last.setValue(2)
        dialog.apply()
        assert dialog.selection is None
        dialog.last.setValue(3)
        dialog.apply()
        channel = dialog.selection['selector']['channels'][0]
        assert channel['row_intervals'] == [[14, 15]]
        assert channel['frame_indices'] == [2]  # Exact duplicate-time frame, no nearest lookup.
        assert channel['unit'] == 'mm' and channel['component'] == 'z'
        assert dialog.selection['reference'] == client.reference
        assert len(client.calls) == 4  # Prepare only; no update/capture/run command.
    finally:
        dialog.close(); dialog.deleteLater(); app.processEvents()
    cancelled = ResultSelectionDialog(client)
    try:
        cancelled.reject()
        app.processEvents()
        assert cancelled.selection is None
        assert len(client.calls) == 4
    finally:
        cancelled.close(); cancelled.deleteLater(); app.processEvents()


def test_previous_phase_view_and_result_removal_preserve_original_records(window, app):
    original = deepcopy(window.document)
    state = window.document['discussion']['research_team']
    state['phases']['Pprevious'] = {'objective': '이전 공개 관측', 'task_ids': ['Tdone']}
    panel = window.research_team.panel
    panel.refresh()
    panel.history.setCurrentIndex(panel.history.findData('Pprevious'))
    assert panel.tasks.topLevelItemCount() == 1
    assert panel.phase.text() == '이전 공개 관측'
    assert window.edited_draft()['context']['research_team']['phase_id'] == 'Pcurrent'
    draft = window.edited_draft()
    selected = {'source_id': 'Scontrolled', 'selector': {'channels': []}}
    draft['context']['research_team']['assignments'][0]['result_refs'] = [selected]
    dialog = TeamReviewDialog(window, draft)
    try:
        dialog.results.setCurrentRow(0)
        dialog.remove_result()
        dialog.reject()
        assert draft['context']['research_team']['assignments'][0]['result_refs'] == [selected]
        assert original['draft'] == window.document['draft']
    finally:
        dialog.close(); dialog.deleteLater(); app.processEvents()


def test_unsupported_retained_selector_keeps_result_unselected_and_error_readable(app):
    client = SavedResultClient()
    client.metadata['research_team_descriptor'] = {'status': 'UNSUPPORTED_SELECTION',
        'reason': 'CONTROLLED retained field without original row identities'}
    dialog = ResultSelectionDialog(client)
    try:
        dialog.show()
        wait_for(app, lambda: len(client.calls) == 4 and not dialog._workers)
        assert dialog.descriptor is None and dialog.selection is None
        assert not dialog.buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).isEnabled()
        assert '선택할 수 없습니다' in dialog.message.text()
        assert 'CONTROLLED' in dialog.message.toolTip()
    finally:
        dialog.close(); dialog.deleteLater(); app.processEvents()


def test_team_input_selection_reaches_existing_explicit_permission_controls(window, app):
    draft = window.edited_draft()
    old, chosen = {'document_id': 'Kold', 'revision': 1}, {'document_id': 'Kchosen', 'revision': 2}
    draft['context'].update(selected_sources=[old], selected_document_ids=['Kold'],
        transmission_scope={'source_refs': [old], 'result_ids': ['Jold'], 'collections': ['public']})
    role = draft['context']['research_team']['assignments'][0]
    role['source_refs'] = [chosen]
    role['result_refs'] = [{'source_id': 'Snew', 'reference': {'job_id': 'Jchosen'}, 'selector': {'channels': []}}]
    draft = team_selection_scope(draft)
    assert draft['context']['selected_sources'] == [old, chosen]
    assert draft['context']['selected_result_ids'] == ['Jchosen']
    assert draft['context']['transmission_scope']['source_refs'] == [old]
    assert draft['context']['transmission_scope']['result_ids'] == ['Jold']
    window._buffer = deepcopy(draft)
    window.research_team.populate(preserve_buffer=True)
    window._populate_sources()
    assert not window.allow_sources.isChecked() and not window.allow_results.isChecked()
    calls = []
    class SelectedSourceClient:
        def request(self, path, body):
            assert path == '/api/workbench/assist' and body['operation'] == 'knowledge.source'
            assert body['arguments'] in [old, chosen]
            calls.append(deepcopy(body['arguments']))
            return {'document_id': body['arguments']['document_id'], 'collection': 'public'}
    window.client = SelectedSourceClient()
    window.allow_results.click()
    assert window.edited_draft()['context']['transmission_scope']['result_ids'] == ['Jold', 'Jchosen']
    assert window.edited_draft()['context']['transmission_scope']['source_refs'] == [old]
    window.allow_sources.click()
    wait_for(app, lambda: not window._busy and not window._workers)
    assert calls == [old, chosen]
    assert window.edited_draft()['context']['transmission_scope']['source_refs'] == [old, chosen]
    assert window.document['draft']['context'].get('transmission_scope', {}) == {}


def test_real_http_transfer_lost_reply_same_command_opens_authored_study(app, tmp_path):
    """Real GUI/HTTP/owner/C/B path; only the authored role record is a fixture."""
    import threading
    from urllib.error import HTTPError
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.workbench_client import Client
    from caelab.discussion_research_team import empty_state
    from caelab.storage import canonical_hash, save_json
    from caelab.evaluation import file_hash
    server = LabHTTPServer(LabService(tmp_path / 'owned'), 0, workbench_config={'experts': ROLES})
    service = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    service.start()
    client = Client('http://127.0.0.1:' + str(server.server_port))
    window = None
    try:
        owner = server.workbench.discussion_documents
        opened = owner.open(title='공개 합성 연구 (실제 전문가 응답 아님)')
        source = owner._documents[opened['id']]
        source['draft'] = document()['draft']
        raw = {'answer': '공개 합성 가설이며 실제 전문가 응답이 아닙니다.',
               'research_reply': {'claims': [{'text': '별도 관측이 필요하다.', 'basis': 'hypothesized'}]}}
        path = owner._folder(opened['id']) / 'research-team' / 'Bfixture' / 'assets' / 'Rfixture.json'
        save_json(path, raw)
        asset = {'path': path.relative_to(owner._folder(opened['id'])).as_posix(), 'sha256': file_hash(path)}
        claim = 'C' + canonical_hash({'response': 'Rfixture', 'index': 0})[:32]
        state = empty_state()
        state['dependencies']['Dauthored'] = {'id': 'Dauthored', 'kind': 'authored', 'parent_ids': [],
            'exact_ref': {'kind': 'authored_question'}, 'content_digest': canonical_hash('공개 합성 질문')}
        state['responses']['Rfixture'] = {'id': 'Rfixture', 'task_id': 'Tdone', 'phase_id': 'Pcurrent',
            'raw_response_ref': asset, 'dependency_ids': ['Dauthored'], 'input_manifest_ids': ['Mfixture'],
            'claim_refs': [{'id': claim, 'response_id': 'Rfixture', 'index': 0}]}
        state['assets']['Rfixture'] = asset
        state['phases'] = document()['discussion']['research_team']['phases']
        state['tasks'] = document()['discussion']['research_team']['tasks']
        source['discussion']['research_team'] = state
        source['discussion']['turns'] = [{'id': 'Afixture', 'author': 'structures', 'research_response_id': 'Rfixture',
            'text': raw['answer'], 'response': raw}]
        owner._persist_draft(source)
        # Initialize the existing service registry before timing the affected
        # transfer callback; package discovery is not the behavior under test.
        client.request('/api/workbench/assist', {'operation': 'experts.list', 'arguments': {}})
        window = ExpertWindow(client, document_id=opened['id'], poll_interval=0)
        window.show()
        wait_for(app, lambda: window.document is not None and not window._busy)
        original = client.research_team_transfer
        calls, accepted = [], []
        def lost_once(*args, **kwargs):
            calls.append(deepcopy(kwargs))
            response = original(*args, **kwargs)
            accepted.append(response)
            if len(calls) == 1:
                raise OSError('CONTROLLED lost HTTP response after owner commit')
            return response
        client.research_team_transfer = lost_once
        assert window.research_team.prepare_transfer('study', {'claim_ids': [claim]})
        wait_for(app, lambda: len(accepted) == 1 and not window._busy and not window._workers)
        assert window.research_team._transfer_pending is not None
        assert not getattr(window, '_portable_research_children', [])
        target = accepted[0]['document']
        draft = deepcopy(target['draft']); draft['question'] = '내가 보존한 판단 질문'
        client.document_command(target['id'], 'study.update', {'draft': draft}, session_id=target['session_id'],
            expected_generation=target['generation'], command_id='CauthoredStudy')
        assert window.research_team.send_transfer()
        wait_for(app, lambda: bool(getattr(window, '_portable_research_children', [])))
        child = window._portable_research_children[0]
        wait_for(app, lambda: child.document is not None and not child._busy)
        assert calls[0]['command_id'] == calls[1]['command_id']
        assert child.document['id'] == target['id']
        assert child.document['draft']['question'] == '내가 보존한 판단 질문'
        assert len(server.workbench.study_documents.list()) == 1
        assert server.workbench.manager.list() == []
        with pytest.raises(HTTPError):
            client.request('/api/workbench/research-team-transfer', {
                'document_id': opened['id'], 'kind': 'study', 'selection': {'claim_ids': [claim]},
                'session_id': source['session_id'], 'expected_generation': source['generation'],
                'command_id': 'Cextra', 'raw_payload': raw})
        assert len(server.workbench.study_documents.list()) == 1
    finally:
        if window:
            for child in list(getattr(window, '_portable_research_children', [])):
                child._allow_close = True; child.close(); child.deleteLater()
            window._allow_close = True; window.close(); window.deleteLater()
            app.processEvents()
        server.shutdown(); server.server_close(); service.join(timeout=5)
        assert not service.is_alive()

def test_unresolved_context_action_uses_existing_command_and_preserves_input(window, app, monkeypatch):
    panel = window.research_team.panel
    state = window.document['discussion']['research_team']
    state['actions']['Dold']['origin'] = 'local'
    state['tasks']['Twait']['phase_id'] = 'Pcurrent'
    # This is an assigned local task, not the completed other actor's task.
    window._buffer['context']['research_team']['assignments'].append({'expert_id':'testing',
        'source_refs':[], 'result_refs':[]})
    panel.refresh()
    panel.tasks.setCurrentItem(panel.tasks.topLevelItem(1)); app.processEvents()
    assert panel.can_acknowledge()
    original = deepcopy(window.edited_draft())
    calls = []
    window.command = lambda operation, arguments: calls.append((operation, arguments))
    monkeypatch.setattr('apps.research.research_team_panel.QInputDialog.getMultiLineText',
        lambda *a: ('추가 시험 자료를 기다림', False))
    panel.acknowledge_task(); assert calls == []
    monkeypatch.setattr('apps.research.research_team_panel.QInputDialog.getMultiLineText',
        lambda *a: ('추가 시험 자료를 기다림', True))
    panel.acknowledge_task()
    assert calls == [('expert.acknowledge_unresolved', {'task_id':'Twait','reason':'추가 시험 자료를 기다림'})]
    assert window.edited_draft() == original and not window._workers
    for status in ('COMPLETED','RUNNING','OUTCOME_UNCONFIRMED'):
        state['tasks']['Twait']['status'] = status
        assert not panel.can_acknowledge()
    state['tasks']['Twait']['status'] = 'WAITING_BUDGET'
    state['tasks']['Twait']['continuation'] = {'cleanup_unconfirmed':True}
    assert not panel.can_acknowledge()
    state['tasks']['Twait']['continuation'] = None
    state['actions']['Dold']['origin'] = 'archived_origin'
    assert not panel.can_acknowledge()
    state['tasks']['Twait'].update(status='ACKNOWLEDGED_UNRESOLVED', acknowledgement={'reason':'추가 시험 자료를 기다림'})
    panel.refresh()
    assert panel.task_detail.text() == '추가 시험 자료를 기다림'


def test_new_team_result_does_not_inherit_old_checked_permission(window):
    window._buffer['context']['transmission_scope'] = {'result_ids':['Jold']}
    assignment = window._buffer['context']['research_team']['assignments'][0]
    assignment['result_refs'] = [{'reference':{'job_id':'Jold'}}]
    window.research_team.populate(preserve_buffer=True)
    assert window.allow_results.isChecked()
    assignment['result_refs'] = [{'reference':{'job_id':'Jnew'}}]
    window.research_team.populate(preserve_buffer=True)
    assert not window.allow_results.isChecked()
    assert window._buffer['context']['transmission_scope'] == {'result_ids':['Jold']}

def test_map_evidence_uses_only_current_checked_map_and_existing_reader(window, monkeypatch):
    cfg = window.document['draft']['context']['research_team']
    state = window.document['discussion']['research_team']
    state['phases']['Pcurrent']['current_map_revision'] = 'Kmap'
    ref = {'document_id':'Ksource','revision':3,'locator':{'segment_id':'2'}}
    window.document['research_team_local_view'] = {'facets':{'map_checkpoints':{'Kmap':{
        'status':'AVAILABLE','projection':{'info_uuid_to_info_dict':{'7':{'title':'시험 조건','meta':{'source':ref}}}}}}}}
    window.document['discussion']['costorm'] = {'topics':[{'id':'Qmap','citations':['7']}]}
    window.topics.clear()
    item=QtWidgets.QTreeWidgetItem(['현재 논점']);item.setData(0,QtCore.Qt.ItemDataRole.UserRole,'Qmap')
    window.topics.addTopLevelItem(item);window.topics.setCurrentItem(item)
    called=[];window.open_reference=lambda r:called.append(r)
    monkeypatch.setattr('apps.research.research_team_panel.QInputDialog.getItem',lambda *a:('[7] 시험 조건',True))
    window.research_team.open_map_source()
    assert called==[ref]
    window.document['research_team_local_view']['facets']['map_checkpoints']['Kmap']={'status':'BLOCKED_SCOPE','projection':None}
    assert window.research_team.map_sources()==[]
    window.research_team.open_map_source();assert called==[ref]
