"""Study layout/selection checks over existing owners and labelled read fixtures."""
from copy import deepcopy
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QScrollArea, QTabWidget

from apps.research.study_window import StudyWindow
from test_costorm_ui import SourceClient
from test_research_study_ui import app, close, wait


def test_reading_stays_visible_while_note_is_written_and_window_changes_width(app, tmp_path):
    client = SourceClient(tmp_path)
    window = StudyWindow(client, auto_open=False, poll_interval=0)
    window._opened(client.doc)
    window.show()
    try:
        wait(app, lambda: not window._busy and window.reading.values.rowCount() == 3)
        assert window.question.isHidden() and window.editor.isHidden()
        assert window.evidence.parent() is not window.reading_page
        assert all(tab.tabText(i) not in {'자료·결과', '메모·판단'}
                   for tab in window.findChildren(QTabWidget) for i in range(tab.count()))
        window.edit_evidence_note()
        window.detail_text.setPlainText('현재 선택한 응력의 제외된 측정점을 확인한다.')
        before = deepcopy(window.edited_draft())
        for width, orientation in ((1100, Qt.Orientation.Vertical), (1440, Qt.Orientation.Horizontal)):
            window.resize(width, 780)
            app.processEvents()
            assert window.content_splitter.orientation() == orientation
            assert window.editor.isVisible() and window.reading_page.isVisible()
            assert window.edited_draft() == before
            assert window.detail_text.toPlainText() == before['evidence'][0]['note']
        window.close_editor_button.click()
        assert window.editor.isHidden() and window.edited_draft() == before
        window.toggle_question()
        window.question.setPlainText('다음 시험은 어떤 조건을 구별하는가?')
        window.toggle_question()
        assert window.question.isHidden()
        assert window.question_preview.text() == window.edited_draft()['question']
    finally:
        close(app, window, client)


def test_judgment_selection_keeps_reading_target_until_link_is_chosen(app, tmp_path):
    client = SourceClient(tmp_path)
    window = StudyWindow(client, auto_open=False, poll_interval=0)
    window._opened(client.doc)
    window.show()
    try:
        window._select(('evidence', 'Eturn'))
        wait(app, lambda: not window._busy and window.reading.payload and window.reading.payload['kind'] == 'expert_turn')
        before = deepcopy(window.edited_draft())
        window._select(('decisions', 'Ddecision'))
        window._show_editor()
        window.resize(1100, 780)
        app.processEvents()
        assert window.width() == 1100 and window.height() == 780
        assert window.reading.canvas.height() >= 140
        window.detail_status.setFocus()
        for _ in range(3):
            QTest.keyClick(window.focusWidget(), Qt.Key.Key_Tab)
        app.processEvents()
        assert window.link_lists['conflicting'].hasFocus()
        assert window.editor.findChild(QScrollArea).verticalScrollBar().value() > 0
        wait(app, lambda: not window._busy and window._content_pending is None)
        assert window._reading_evidence_id == 'Eturn'
        assert window.reading.payload['kind'] == 'expert_turn'
        assert 'Current provisional interpretation' in window.followup_basis.text()
        window.read_linked_evidence('Eresult')
        wait(app, lambda: not window._busy and window.reading.payload['kind'] == 'result')
        assert window._selected == ('decisions', 'Ddecision')
        assert window._reading_evidence_id == 'Eresult'
        assert window.edited_draft() == before
        assert not client.calls
    finally:
        close(app, window, client)


def test_preview_difference_requires_explicit_connection_before_saved_followup(app, tmp_path):
    client = SourceClient(tmp_path)
    original = client.research_reference
    def read(reference):
        payload = original(reference)
        if reference['kind'] == 'result':
            name = reference.get('selection', {}).get('responses', ['stress'])[0]
            payload['metadata']['responses'][0]['response'] = name
            payload['result']['responses'][name] = payload['result']['responses'].pop('stress')
        return payload
    client.research_reference = read
    window = StudyWindow(client, auto_open=False, poll_interval=0)
    window._opened(client.doc)
    window.show()
    try:
        wait(app, lambda: not window._busy and window.reading.values.rowCount() == 3)
        original_reference = deepcopy(window._row()['reference'])
        assert window.preview_difference.isHidden()
        window.read_response('tangent')
        wait(app, lambda: not window._busy and window.reading.channel.currentData() == 'tangent')
        assert window._row()['reference'] == original_reference
        assert window.preview_difference.isVisible() and window.pin_response.isVisible()
        assert 'stress' in window.preview_difference.text()
        window.keep_response_selection()
        wait(app, lambda: not window._busy and window._content_pending is None)
        assert window._row()['reference']['selection']['responses'] == ['tangent']
        assert window.preview_difference.isHidden() and window.local_dirty
        window.save_document()
        wait(app, lambda: not window._busy and not window.local_dirty and not window.document['dirty'])
        assert window._navigation_context()['evidence'][0]['selection']['responses'] == ['tangent']
    finally:
        close(app, window, client)
