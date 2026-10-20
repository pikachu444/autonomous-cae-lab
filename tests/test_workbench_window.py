"""Workbench navigation on the existing document owner; launches are IO boundaries."""
from copy import deepcopy
import os
from pathlib import Path
import threading

import pytest
from test_research_runner_ui import app, until
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog, QFileSystemModel

from apps.research import desktop, selection_discussion
from apps.research.workbench_window import WorkbenchWindow, _read_preview


class ResearchClient:
    url = 'http://controlled-workbench'

    def __init__(self):
        self.docs = {}
        self.calls = []

    def documents(self):
        self.calls.append(('catalog',))
        return {'documents': deepcopy(list(self.docs.values()))}

    def document_open(self, *, kind='expert', title=None, document_id=None, draft=None):
        self.calls.append(('open', document_id))
        if document_id:
            return self.document_read(document_id)
        from caelab.discussion_document import default_draft
        identifier = 'X' + str(len(self.docs) + 1)
        self.docs[identifier] = {'id': identifier, 'kind': kind, 'title': title or '연구',
            'draft': deepcopy(draft or default_draft()), 'generation': 0, 'session_id': 'Scontrolled'}
        return deepcopy(self.docs[identifier])

    def document_read(self, identifier):
        self.calls.append(('read', identifier))
        return deepcopy(self.docs[identifier])

    def document_command(self, identifier, operation, arguments, *, session_id, expected_generation, command_id):
        self.calls.append((operation, identifier))
        document = self.docs[identifier]
        assert session_id == document['session_id']
        assert expected_generation == document['generation']
        if operation == 'expert.update':
            document['draft'] = deepcopy(arguments['draft'])
            document['generation'] += 1
        elif operation == 'document.save':
            document['saved_revision'] = 'R1'
        else:
            pytest.fail('Workbench unexpectedly executed ' + operation)
        return {'document': deepcopy(document)}


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / 'workbench.ini'), QSettings.Format.IniFormat)


def finish(window, app):
    until(app, lambda: not window._workers)
    window.close()
    app.processEvents()


def choose(window, *names):
    window.source_list.clearSelection()
    for index in range(window.source_list.topLevelItemCount()):
        item = window.source_list.topLevelItem(index)
        item.setSelected(Path(item.data(0, Qt.ItemDataRole.UserRole)).name in names)


def test_start_file_model_and_continue_owner_without_execution(app, settings, tmp_path, monkeypatch):
    client = ResearchClient()
    model = tmp_path / '사용자 모델.FCStd'
    model.write_bytes(b'native model launch boundary')
    opened = []
    monkeypatch.setattr(desktop, 'launch_pre', lambda c, source, **kwargs: opened.append(Path(source)) or {'status': 'LAUNCH_REQUESTED'})
    choice = ['']
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (choice[0], ''))
    window = WorkbenchWindow(client, settings=settings)
    window.show()
    try:
        until(app, lambda: not window._pending)
        assert window.pages.currentWidget() is window.start_page
        assert not window.save_action.isEnabled()
        assert window.findChildren(QFileSystemModel) == []
        window.open_file_action.trigger()
        assert not opened
        choice[0] = str(tmp_path / 'missing.FCStd')
        window.open_file_action.trigger()
        assert not opened and '디스크' in window.message.text()
        choice[0] = str(model)
        window.open_file_action.trigger()
        until(app, lambda: not window._pending)
        identifier = window.document['id']
        assert opened == [model.resolve()]
        assert window.pages.currentWidget() is window.research_page
        assert window.model_path.text() == str(model.resolve())
        state = client.docs[identifier]['draft']['context']['workbench']
        assert state['model'] == {'original_path': str(model.resolve()), 'saved_path': str(model.resolve())}
        window.save_action.trigger()
        until(app, lambda: not window._pending)
        assert client.docs[identifier]['saved_revision'] == 'R1'
        assert settings.allKeys() == ['recentModels']
    finally:
        finish(window, app)
    reopened = WorkbenchWindow(client, settings=settings)
    reopened.show()
    try:
        until(app, lambda: not reopened._pending)
        assert reopened.research_list.topLevelItemCount() == 1
        item = reopened.research_list.topLevelItem(0)
        item.setSelected(True)
        before = len(opened)
        QTest.mouseClick(reopened.continue_button, Qt.MouseButton.LeftButton)
        until(app, lambda: not reopened._pending)
        assert reopened.document['id'] == identifier
        assert reopened.model_path.text() == str(model.resolve())
        assert len(opened) == before
        assert not any(call[0] in {'expert.ask', 'submit', 'cancel'} for call in client.calls)
    finally:
        finish(reopened, app)


def test_select_read_result_discuss_and_same_name_rerun_preserve_conversation(app, settings, tmp_path, monkeypatch):
    client = ResearchClient()
    document = client.document_open(title='설정과 결과 연구')
    document['draft']['composer']['text'] = '보존할 미전송 질문'
    document['draft']['context'] = {'constraints': ['메시 유지'], 'workbench': {}}
    client.docs[document['id']] = deepcopy(document)
    log, result = tmp_path / '계산.sta', tmp_path / '계산.frd'
    log.write_text('actual convergence\n1 2 3\n', encoding='utf8')
    result.write_bytes(b'FRD boundary')
    launches, discussions = [], []
    monkeypatch.setattr(desktop, 'launch_result_file', lambda c, path, **kwargs: launches.append((Path(path), kwargs)) or {'status': 'LAUNCH_REQUESTED'})
    def discuss(c, paths, discussion_id=None, **kwargs):
        discussions.append((paths, discussion_id, deepcopy(kwargs)))
        return {'document': c.document_read(discussion_id), 'executed': False}
    monkeypatch.setattr(selection_discussion, 'open_file_discussion', discuss)
    window = WorkbenchWindow(client, settings=settings, document_id=document['id'])
    window.show()
    try:
        until(app, lambda: not window._pending)
        window.attach_paths([str(log), str(result)])
        until(app, lambda: not window._pending)
        assert window.source_list.topLevelItemCount() == 2
        choose(window, log.name)
        until(app, lambda: not window._pending)
        assert window.preview.toPlainText() == log.read_text(encoding='utf8')
        assert not window.post_button.isEnabled()
        choose(window, result.name)
        until(app, lambda: not window._pending)
        assert window.post_button.isEnabled()
        QTest.mouseClick(window.post_button, Qt.MouseButton.LeftButton)
        until(app, lambda: not window._pending)
        assert launches[0][0] == result
        assert launches[0][1]['discussion_id'] == document['id']
        assert launches[0][1]['workbench'] == window._state()
        choose(window, log.name, result.name)
        QTest.mouseClick(window.discuss_button, Qt.MouseButton.LeftButton)
        until(app, lambda: not window._pending)
        log.write_text('new calculation content\n', encoding='utf8')
        QTest.mouseClick(window.discuss_button, Qt.MouseButton.LeftButton)
        until(app, lambda: not window._pending)
        assert len(discussions) == 2
        assert all(row[1] == document['id'] for row in discussions)
        assert window.document['draft']['composer']['text'] == '보존할 미전송 질문'
        assert window.document['draft']['context']['constraints'] == ['메시 유지']
        assert not any(key.startswith('discussion:') or key == 'workFolder' for key in settings.allKeys())
    finally:
        finish(window, app)


def test_relink_missing_saved_model_retains_original_and_reopen_does_not_launch(app, settings, tmp_path, monkeypatch):
    client = ResearchClient()
    original, missing, moved = tmp_path / 'original.FCStd', tmp_path / 'gone.FCStd', tmp_path / 'moved.FCStd'
    moved.write_bytes(b'moved user model')
    document = client.document_open(title='이동한 모델 연구')
    document['draft']['context']['workbench'] = {'model': {'original_path': str(original), 'saved_path': str(missing)}}
    client.docs[document['id']] = deepcopy(document)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(moved), ''))
    launched = []
    monkeypatch.setattr(desktop, 'launch_pre', lambda *a, **kw: launched.append(kw))
    window = WorkbenchWindow(client, settings=settings, document_id=document['id'])
    try:
        until(app, lambda: not window._pending)
        assert window.model_path.text() == str(missing)
        window.open_connected_model()
        assert not launched and '다시 연결' in window.message.text()
        window.relink_model()
        until(app, lambda: not window._pending)
        assert window.model_path.text() == str(moved)
        assert str(original) in window.original_path.text()
        assert not launched
    finally:
        finish(window, app)


def test_late_source_attachment_does_not_replace_new_research(app, settings, tmp_path, monkeypatch):
    client = ResearchClient()
    first = client.document_open(title='처음 연구')
    second = client.document_open(title='다음 연구')
    log = tmp_path / 'run.log'
    log.write_text('actual log', encoding='utf8')
    started, release = threading.Event(), threading.Event()
    def discuss(c, paths, discussion_id=None, **kwargs):
        started.set()
        assert release.wait(5)
        return {'document': c.document_read(discussion_id), 'executed': False}
    monkeypatch.setattr(selection_discussion, 'open_file_discussion', discuss)
    window = WorkbenchWindow(client, settings=settings, document_id=first['id'])
    try:
        until(app, lambda: not window._pending)
        window.attach_paths([str(log)])
        until(app, lambda: not window._pending)
        window.discuss_files()
        until(app, started.is_set)
        window.continue_research(second['id'])
        until(app, lambda: window.document['id'] == second['id'])
        release.set()
        until(app, lambda: not window._pending)
        assert window.document['id'] == second['id']
    finally:
        release.set()
        finish(window, app)


def test_new_research_preserves_previous_and_records_real_working_copy(app, settings, tmp_path, monkeypatch):
    client = ResearchClient()
    old = client.document_open(title='이전 연구')
    old['draft']['composer']['text'] = '이전 질문'
    client.docs[old['id']] = deepcopy(old)
    source, saved = tmp_path / 'assembly.caepre', tmp_path / 'working.FCStd'
    source.write_bytes(b'portable boundary')
    saved.write_bytes(b'native copy boundary')
    launched = []
    def launch(c, source, **kwargs):
        launched.append((source, kwargs))
        return {'status': 'LAUNCH_REQUESTED', 'saved_path': str(saved)}
    monkeypatch.setattr(desktop, 'launch_pre', launch)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(source), ''))
    window = WorkbenchWindow(client, settings=settings, document_id=old['id'])
    try:
        until(app, lambda: not window._pending)
        window.show_start()
        until(app, lambda: not window._pending)
        window.open_file_action.trigger()
        until(app, lambda: not window._pending)
        assert window.document['id'] != old['id']
        assert client.docs[old['id']]['draft'] == old['draft']
        assert window._state()['model'] == {'original_path': str(source), 'saved_path': str(saved)}
        assert window.model_path.text() == str(saved)
        assert launched[0][1]['discussion_id'] == window.document['id']
    finally:
        finish(window, app)


def test_missing_source_relink_preserves_archived_evidence(app, settings, tmp_path, monkeypatch):
    client = ResearchClient()
    document = client.document_open(title='파일을 옮긴 연구')
    old, moved = tmp_path / 'gone.sta', tmp_path / 'moved.sta'
    moved.write_text('actual moved log', encoding='utf8')
    refs = [{'document_id': 'Kevidence', 'revision': 'R1'}]
    document['draft']['context'] = {'selected_sources': refs, 'workbench': {
        'sources': [{'path': str(old), 'kind': '로그', 'label': old.name}]}}
    client.docs[document['id']] = deepcopy(document)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(moved), ''))
    window = WorkbenchWindow(client, settings=settings, document_id=document['id'])
    try:
        until(app, lambda: not window._pending)
        choose(window, old.name)
        assert '다시 연결' in window.preview_note.text()
        window.relink_source_action.trigger()
        until(app, lambda: not window._pending)
        assert window._state()['sources'][0]['path'] == str(moved)
        assert window.document['draft']['context']['selected_sources'] == refs
    finally:
        finish(window, app)


@pytest.mark.parametrize('width,height', [(1000, 700), (1280, 820)])
def test_start_and_research_layout_fit_and_keep_sources_readable(app, settings, tmp_path, width, height):
    client = ResearchClient()
    document = client.document_open(title='긴 이름의 비선형 구조 해석과 마찰 접촉 연구')
    log = tmp_path / '이름이 긴 사용자 계산 로그.sta'
    log.write_text('actual log', encoding='utf8')
    window = WorkbenchWindow(client, settings=settings)
    try:
        until(app, lambda: not window._pending)
        if os.name == 'nt':
            assert QFontDatabase.addApplicationFont('C:/Windows/Fonts/malgun.ttf') >= 0
            window.setFont(QFont('Malgun Gothic', 10))
            assert window.fontMetrics().inFontUcs4(ord('연'))
        window.resize(width, height)
        window.show()
        app.processEvents()
        assert window.width() == width and window.height() == height
        window.continue_research(document['id'])
        until(app, lambda: not window._pending)
        window.attach_paths([str(log)])
        until(app, lambda: not window._pending)
        assert window.workspace_splitter.widget(1).width() > width * .7
        for button in (window.model_button, window.origin_button, window.add_sources_button, window.discuss_button):
            assert button.isVisible()
            assert button.width() >= button.fontMetrics().horizontalAdvance(button.text()) + 18
            point = button.mapTo(window, QPoint(0, 0))
            assert point.x() + button.width() <= width
        assert window.preview.viewport().height() >= 4 * window.preview.fontMetrics().lineSpacing()
        folder = os.getenv('CAELAB_QT_CAPTURE_DIR')
        if folder:
            Path(folder).mkdir(parents=True, exist_ok=True)
            assert window.grab().save(str(Path(folder) / f'workbench-{width}.png'))
    finally:
        finish(window, app)


def test_log_preview_preserves_unicode_and_reports_truncation(tmp_path):
    path = tmp_path / 'solver.log'
    path.write_text('계산 기록\n' * 30000, encoding='utf8')
    text, note = _read_preview(path)
    assert text.startswith('계산 기록' + os.linesep)
    assert '\ufffd' not in text and '앞' in note
