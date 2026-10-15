"""Scoped GUI checks; result transport is a labelled double, provider execution is zero."""
from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QDialog, QInputDialog, QListWidget

from apps.research.discussion_view import ConversationList
from apps.research.result_attachments import same_result_attachment
from test_research_expert_ui import app, ui_owner, open_window, wait


def test_appended_and_partial_turns_keep_completed_text_selection(app):
    view = ConversationList()
    turns = [{'id': 'Tfirst', 'author': 'user', 'status': 'AUTHORED',
              'text': '보존한 원질문을 읽고 선택합니다.'},
             {'id': 'Tsecond', 'author': 'reviewer', 'status': 'RUNNING', 'text': '받은 첫 문장'}]
    try:
        view.resize(720, 420)
        view.show()
        view.set_turns(turns)
        app.processEvents()
        card = view._cards['Tfirst']
        view.setCurrentItem(card.item)
        cursor = card.body.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        card.body.setTextCursor(cursor)
        selected = cursor.selectedText()
        updated = deepcopy(turns)
        updated[1].update(text='새로 받은 두 번째 문장', status='ANSWERED')
        view.set_turns(updated)
        app.processEvents()
        assert view._cards['Tfirst'] is card
        assert card.body.textCursor().selectedText() == selected
        assert view._cards['Tsecond'].body.toPlainText() == updated[1]['text']
        updated.append({'id': 'Tthird', 'author': 'user', 'status': 'AUTHORED', 'text': '다음 질문'})
        view.set_turns(updated)
        app.processEvents()
        assert view.count() == 3 and view._cards['Tfirst'] is card
        assert card.body.textCursor().selectedText() == selected
        view.set_turns(updated[:1])
        app.processEvents()
        assert view.count() == 1 and view._cards['Tfirst'] is card
    finally:
        view.close()


def test_attachment_identity_keeps_legacy_and_changed_digest_distinct():
    ref = dict(document_id='Nsource', job_id='Jsource', input_revision='Isource', input_sha256='a' * 64,
               result_sha256='b' * 64, selection=['force'])
    legacy = {key: value for key, value in ref.items() if key != 'result_sha256'}
    before = deepcopy(legacy)
    assert same_result_attachment(legacy, ref)
    assert legacy == before
    assert not same_result_attachment(ref, {**ref, 'result_sha256': 'c' * 64})
    assert not same_result_attachment(ref, {**ref, 'selection': []})
    assert not same_result_attachment(ref, {**ref, 'job_id': 'Jother'})
    assert not same_result_attachment({}, {})


def attach_fixture(app, ui_owner, monkeypatch):
    owner, _, calls, _ = ui_owner
    window = open_window(app, owner)
    reference = dict(document_id='Nretained', job_id='Jretained', input_revision='Iretained',
                     input_sha256='a' * 64, result_sha256='b' * 64)
    run = {key: value for key, value in reference.items() if key != 'document_id'}
    reads = []
    window.client.documents = lambda: {'documents': [{'id': 'Nretained', 'title': '보존한 인장 계산',
                                                       'kind': 'numerical', 'runs': [run]}]}
    def ref(*args):
        reads.append(('reference', args))
        return deepcopy(reference)
    def result(*args, **kwargs):
        reads.append(('result', kwargs))
        assert kwargs == {'selection': {'metadata_only': True}}
        return {'responses': {'force': {'unit': 'N'}}}
    def resolved(value):
        reads.append(('resolve', deepcopy(value)))
        return {'status': 'AVAILABLE'}
    window.client.document_result_reference = ref
    window.client.document_result = result
    window.client.research_reference = resolved
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *args, **kwargs: (args[3][0], True))
    def confirm(dialog):
        rows = dialog.findChild(QListWidget)
        rows.item(0).setCheckState(Qt.CheckState.Checked)
        # A late local question must survive attachment.
        window.question.setPlainText('첨부 확인 중 보완한 사용자 질문')
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, 'exec', confirm)
    return window, reference, reads, calls


def close(app, window):
    wait(app, lambda: not window._busy and not window._workers)
    window._allow_close = True
    window.close()
    window.deleteLater()
    app.processEvents()


def test_manual_exact_attachment_preserves_question_permission_and_return_deduplication(app, ui_owner, monkeypatch):
    window, reference, reads, calls = attach_fixture(app, ui_owner, monkeypatch)
    try:
        original = deepcopy(window.document['draft'])
        window.attach_result()
        wait(app, lambda: len(reads) >= 4 and not window._busy)
        attachment = {**reference, 'selection': ['force']}
        draft = window.edited_draft()
        assert draft['composer']['evidence'] == [attachment]
        assert draft['composer']['text'] == '첨부 확인 중 보완한 사용자 질문'
        assert draft['context'] == original['context']
        assert window.document['draft'] == original and window.local_dirty
        message = {'operation': 'attach', 'reference': reference, 'selection': ['force']}
        assert window._result_return.append(message) == 'ALREADY_ATTACHED'
        window.attach_result()
        wait(app, lambda: len(reads) >= 8 and not window._busy)
        assert window.edited_draft()['composer']['evidence'] == [attachment]
        assert calls == [] and window.client.operations == []
    finally:
        close(app, window)


def test_manual_attachment_changed_owner_during_review_keeps_edits(app, ui_owner, monkeypatch):
    window, _, reads, calls = attach_fixture(app, ui_owner, monkeypatch)
    try:
        def changed(dialog):
            window.question.setPlainText('보존할 편집 질문')
            window.document['session_id'] = 'Sdifferent'
            return QDialog.DialogCode.Accepted
        monkeypatch.setattr(QDialog, 'exec', changed)
        window.attach_result()
        wait(app, lambda: len(reads) >= 2 and not window._busy)
        assert window.edited_draft()['composer']['evidence'] == []
        assert window.edited_draft()['composer']['text'] == '보존할 편집 질문'
        assert '변경' in window.message.text()
        assert calls == [] and window.client.operations == []
    finally:
        close(app, window)


def test_manual_attachment_rejects_changed_retained_result_after_confirmation(app, ui_owner, monkeypatch):
    window, reference, reads, calls = attach_fixture(app, ui_owner, monkeypatch)
    original = window.client.document_result_reference
    def changed(*args):
        value = original(*args)
        if len([row for row in reads if row[0] == 'reference']) > 1:
            value['result_sha256'] = 'c' * 64
        return value
    window.client.document_result_reference = changed
    try:
        window.attach_result()
        wait(app, lambda: len(reads) >= 3 and not window._busy)
        assert window.edited_draft()['composer']['evidence'] == []
        assert window.edited_draft()['composer']['text'] == '첨부 확인 중 보완한 사용자 질문'
        assert not any(row[0] == 'resolve' for row in reads)
        assert calls == [] and window.client.operations == []
    finally:
        close(app, window)


def test_attachment_identity_compares_response_set_without_reordering_original():
    reference = dict(document_id='Nsource', job_id='Jsource', input_revision='Isource', input_sha256='a' * 64,
                     result_sha256='b' * 64, selection=['stress_yy', 'stress_xx'])
    original = deepcopy(reference)
    assert same_result_attachment(reference, {**reference, 'selection': ['stress_xx', 'stress_yy']})
    assert reference == original
    assert not same_result_attachment(reference, {**reference, 'selection': ['stress_xx']})


def test_manual_attachment_physical_labels_keep_exact_response_keys(app, ui_owner, monkeypatch):
    window, reference, _, calls = attach_fixture(app, ui_owner, monkeypatch)
    window.client.document_result = lambda *args, **kwargs: {'responses': {
        'stress_xx': {'unit': 'MPa', 'measure': 'infinitesimal_Cauchy', 'component': 'xx'},
        'operator_signal': {'unit': 'mV', 'label': '시험기 신호'}}}
    def confirm(dialog):
        rows = dialog.findChild(QListWidget)
        assert rows.item(0).text() == '미소변형 Cauchy 응력 XX [MPa]'
        assert rows.item(1).text() == '시험기 신호 [mV]'
        assert [rows.item(i).data(Qt.ItemDataRole.UserRole) for i in range(2)] == ['stress_xx', 'operator_signal']
        for i in range(2):
            rows.item(i).setCheckState(Qt.CheckState.Checked)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, 'exec', confirm)
    try:
        window.attach_result()
        wait(app, lambda: not window._busy and bool(window.edited_draft()['composer']['evidence']))
        assert window.edited_draft()['composer']['evidence'] == [{**reference, 'selection': ['stress_xx', 'operator_signal']}]
        assert calls == [] and window.client.operations == []
    finally:
        close(app, window)
