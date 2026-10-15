"""Report-owned reading windows keep exact references and return without editing."""
from copy import deepcopy
import threading
import time

from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMessageBox
from shiboken6 import isValid

from apps.research.report_window import ReportWindow, section
from test_experiment_report_ui import app


class SavedSource:
    def __init__(self):
        self.reads=[]

    def research_reference(self,reference):
        self.reads.append(deepcopy(reference))
        return {'kind':'result','status':'AVAILABLE','result':{'responses':{}}}


def ready(app,condition):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        app.processEvents()
        if condition():return
        time.sleep(.005)
    raise AssertionError('Report source window did not finish its retained read')


def report(app):
    client=SavedSource();window=ReportWindow(client,auto_open=False)
    reference={'kind':'result','document_id':'Tsource','job_id':'Jsource',
        'input_revision':'Isource','input_sha256':'a'*64,'result_sha256':'b'*64,
        'selection':{'responses':['force'],'source_rows':[3,7]}}
    window.draft['sections']=[section('보존한 시험',asset={'id':'Asource','sha256':'c'*64,'reference':reference})]
    window.populate();window.show();app.processEvents()
    return window,client,reference


def test_return_from_saved_source_keeps_exact_reference_report_edits_and_selection(app):
    window,client,reference=report(app)
    try:
        window.showMaximized();app.processEvents();state=window.windowState()
        source=window.open_source()
        ready(app,lambda:not source._busy)
        window.edit_section();window.section_text.setPlainText('원자료를 읽는 동안 작성한 설명')
        window.section_text.selectAll();window.remember_editor()
        selected_text=window.section_text.textCursor().selectedText()
        buffers=deepcopy(window._edit_buffers)
        draft=deepcopy(window.draft);selected=window.sections.currentRow()
        back=next(action for action in source.findChildren(QAction) if action.text()=='보고서로 돌아가기')
        assert back.shortcut().toString()=='Alt+Left'
        back.trigger();app.processEvents()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        assert client.reads==[reference]
        assert window.draft==draft and window.sections.currentRow()==selected and window.isVisible()
        assert window.windowState()==state and window._edit_buffers==buffers
        assert window.section_text.textCursor().selectedText()==selected_text
        assert not isValid(source) and window._source_windows==[]
        assert not window._return_from_source(source)
    finally:
        window._edit_buffers.clear();window._editing_section=None;window.close();app.processEvents()


def test_closing_report_closes_its_owned_source_readers(app):
    window,_,_=report(app)
    source=window.open_source()
    other=QMainWindow();other.show();window._children.append(other)
    ready(app,lambda:not source._busy)
    try:
        window.close();app.processEvents()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        assert not window.isVisible() and not isValid(source)
        assert other.isVisible()
    finally:other.close()


def test_report_close_cancel_preserves_source_and_unapplied_description(app,monkeypatch):
    window,_,_=report(app);source=window.open_source()
    ready(app,lambda:not source._busy)
    window.document={'dirty':True,'draft':deepcopy(window.draft)}
    window.edit_section();window.section_text.setPlainText('닫기를 취소하면 보존할 설명')
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Cancel)
    try:
        assert not window.close()
        assert window.isVisible() and source.isVisible() and not source._closed
        assert window.section_text.toPlainText()=='닫기를 취소하면 보존할 설명'
        assert window.document['dirty'] and window._edit_buffers
    finally:
        window.document=None;window._edit_buffers.clear();window._editing_section=None
        window.close();app.processEvents()


def test_report_close_during_source_read_discards_late_callback(app):
    window,client,_=report(app);entered=threading.Event();release=threading.Event()
    original=client.research_reference
    def reading(reference):
        entered.set();assert release.wait(5)
        return original(reference)
    client.research_reference=reading
    source=window.open_source()
    try:
        ready(app,entered.is_set)
        assert window.close()
        app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        assert not isValid(source)
    finally:
        release.set();assert QThreadPool.globalInstance().waitForDone(5000)
        app.processEvents()
