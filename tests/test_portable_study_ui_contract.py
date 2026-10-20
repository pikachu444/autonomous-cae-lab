"""Helper contracts plus bounded Qt/HTTP portable-editor acceptance.

Qt cases skip when the optional PySide6 runtime is absent. Shown Windows Qt
checks use QTest; OS mouse/focus, native physics and live providers are separate.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
from apps.research import portable_research_actions as actions
from caelab.portable_research_owner import HISTORY


@pytest.mark.parametrize('change', [{}, {'_busy':True}, {'conflict':True}, {'_closed':True}, {'document':None}])
def test_current_editor_state_controls_copy_without_collecting_text(change):
    window=SimpleNamespace(document={'id':'Sone'},_busy=False,conflict=False,_closed=False,**{})
    window.__dict__.update(change)
    assert actions.copy_allowed(window)==(not bool(change))


def test_only_current_rounds_enable_explicit_continuation():
    archived={'id':'Borigin','status':'READY'}
    current={'id':'Bcurrent','status':'READY'}
    document={HISTORY:{'rounds':{'Borigin':'historical digest'}},'discussion':{'rounds':[archived,current]}}
    assert actions.local_rounds(document)==[current]
    assert document['discussion']['rounds']==[archived,current]


def test_verified_navigation_does_not_mutate_original_or_fallback_when_unavailable():
    source={'kind':'document','document_id':'Sorigin'}
    current={'kind':'document','document_id':'Slocal'}
    doc={'portable_reference_navigation':[{'reference':source,'navigation_reference':current}]}
    moved=actions.navigation(doc,source)
    assert moved==current and source['document_id']=='Sorigin'
    moved['document_id']='changed'
    assert doc['portable_reference_navigation'][0]['navigation_reference']==current
    doc['portable_reference_navigation'][0]['navigation_reference']=None
    with pytest.raises(ValueError,match='자동'):actions.navigation(doc,source)


def test_reading_pane_has_bibliography_exact_page_line_section_and_limits():
    payload={'source':{'revision':1,'segments':[{'text':'보존한 원문','locator':{'section':'관측','page':3,
            'line_start':7,'line_end':9,'segment_id':'2'},'limitations':['표 추출 한계']}],
            'failed_segments':[{'reason':'그림은 추출하지 않음'}]},
        'source_metadata':{'metadata':{'author':'공개 저자','year':2026,'source':'공개 합성 자료'}}}
    text=actions.source_description(payload)
    assert all(s in text for s in ['공개 저자','2026','문헌 개정 1','관측','쪽 3','줄 7–9','보존한 원문','표 추출 한계','그림은 추출하지 않음'])
    assert 'sha256' not in text and 'segment_id' not in text


def test_menu_adds_explicit_next_role_without_dispatch_on_install():
    calls=[]
    class Signal:
        def connect(self,handler):self.handler=handler
    class Menu:
        def addAction(self,text):calls.append(text);return SimpleNamespace(triggered=Signal())
    window=SimpleNamespace(document={'id':'Xone'},_busy=False,conflict=False,_closed=False,
        _progress_command=lambda *a,**k:calls.append((a,k)),refresh_document=lambda:None)
    actions.install(window,Menu(),'expert')
    assert calls==['작업 사본 만들기…','현재 요청의 다음 역할 응답 받기']
    window.portable_next_response_action.triggered.handler()
    assert calls[-1][0]==('expert.advance',)


def test_close_touches_only_helper_owned_child_windows():
    touched=[]
    own=SimpleNamespace(close=lambda:touched.append('owned'))
    other=SimpleNamespace(close=lambda:touched.append('unrelated'))
    actions.close_children(SimpleNamespace(_portable_research_children=[own],other_window=other))
    assert touched==['owned']


@pytest.mark.parametrize('portable',[False,True])
def test_expert_refresh_advances_ready_round_only_for_nonportable_owner(monkeypatch,portable):
    pytest.importorskip('PySide6')
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from apps.research.expert_window import ExpertWindow
    from caelab.discussion_document import default_draft
    import time
    app=QApplication.instance() or QApplication([])
    draft=default_draft();draft['composer']['text']='Saved question'
    document={'id':'Xcurrent','kind':'expert','session_id':'Sowner','generation':0,
        'title':'Controlled refresh owner','draft':draft,'turns':[],
        'discussion':{'rounds':[{'id':'Bcurrent','status':'READY'}],'paused':False},
        'portable_research_owner':{'kind':'copy'} if portable else None}
    reads=[];commands=[]
    def read(identifier):
        reads.append(identifier)
        return deepcopy(document)
    window=ExpertWindow(SimpleNamespace(document_read=read),auto_open=False,poll_interval=0)
    try:
        window._show_document(document)
        # A user-started round is ready for the next response. Only the
        # transport effect is controlled; the refresh/Qt callback is real.
        window._round_started_here=True;window._auto_round_id='Bcurrent'
        monkeypatch.setattr(window,'_progress_command',lambda operation:commands.append(operation))
        window.refresh_document()
        deadline=time.monotonic()+5
        while window._busy and time.monotonic()<deadline:
            app.processEvents();QTest.qWait(5)
        assert not window._busy and reads==['Xcurrent']
        QTest.qWait(10);app.processEvents()
        assert commands==([] if portable else ['expert.advance'])
        assert window.question.toPlainText()=='Saved question'
        assert window.document['discussion']['rounds']==document['discussion']['rounds']
    finally:
        window._allow_close=True;window.close();app.processEvents()

@pytest.mark.parametrize('choice',['취소','저장된 내용만','저장 후 계속'])
def test_qt_explicit_copy_choice_keeps_unapplied_editor_and_owns_only_its_children(monkeypatch,choice):
    pytest.importorskip('PySide6')
    from PySide6.QtCore import QTimer,Qt
    from PySide6.QtWidgets import QApplication,QMainWindow,QPlainTextEdit,QLabel,QPushButton,QDialog
    from PySide6.QtTest import QTest
    from PySide6.QtGui import QTextCursor
    from apps.research import connection_window
    app=QApplication.instance() or QApplication([])
    class Child(QMainWindow):
        def __init__(self,*a,**k):super().__init__();self.closed=False
        def closeEvent(self,event):self.closed=True;event.accept()
    monkeypatch.setattr(connection_window,'ConnectionWindow',Child)
    window=QMainWindow();window.document={'id':'Sone','session_id':'Sowner'}
    window._busy=window.conflict=window._closed=False;window.client=object()
    window.message=QLabel();question=QPlainTextEdit('아직 적용하지 않은 연구 판단');window.setCentralWidget(question)
    cursor=question.textCursor();cursor.select(QTextCursor.SelectionType.Document);question.setTextCursor(cursor)
    selected=cursor.selectedText();saves=[]
    def save(*,after):saves.append('explicit');return after()
    window.save_document=save
    other=Child();other.show();window.show();app.processEvents()
    def choose():
        dialog=app.activeModalWidget();assert isinstance(dialog,QDialog)
        button=next(b for b in dialog.findChildren(QPushButton) if b.text()==choice)
        QTest.mouseClick(button,Qt.MouseButton.LeftButton)
    QTimer.singleShot(0,choose)
    try:
        result=actions.prepare_copy(window);app.processEvents()
        assert question.toPlainText()=='아직 적용하지 않은 연구 판단'
        assert question.textCursor().selectedText()==selected
        assert saves==(['explicit'] if choice=='저장 후 계속' else [])
        assert bool(result)==(choice!='취소')
        if result:
            assert len(window._portable_research_children)==1
            actions.close_children(window);app.processEvents()
        assert not other.closed
    finally:
        actions.close_children(window);window.close();other.close();app.processEvents()

def test_qt_http_portable_editors_read_without_dispatch_and_keep_copy_buffers(tmp_path,monkeypatch):
    """Shown native Qt + real loopback HTTP; no OS mouse/focus or provider claim."""
    pytest.importorskip('PySide6')
    import os,threading,time
    from PySide6.QtCore import QTimer,Qt,QThreadPool
    from PySide6.QtWidgets import QApplication,QDialog,QPushButton,QMessageBox
    from PySide6.QtGui import QTextCursor
    from PySide6.QtTest import QTest
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from apps.research.appearance import apply_appearance
    from apps.research.expert_window import ExpertWindow
    from apps.research.study_window import StudyWindow
    from apps.research.report_window import ReportWindow
    from apps.research.connection_window import CopyReviewDialog
    from caelab.workbench_client import Client
    from caelab.portable_project import open_project,inspect_copy
    from examples.portable_study_expert_public import fixture,publish,rows,source_free
    from test_portable_study_expert import workspace
    with workspace(tmp_path/'origin') as origin:
        case=fixture(origin)
        made=publish(origin,case['documents'],tmp_path/'copy')
    (tmp_path/'origin').rename(tmp_path/'origin-preserved')
    server=LabHTTPServer(LabService(tmp_path/'copy'),0);wb=server.workbench
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    app=QApplication.instance() or QApplication([]);apply_appearance(app)
    client=Client('http://127.0.0.1:'+str(server.server_port));windows=[]
    def wait(condition,message):
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            app.processEvents()
            if condition():return
            time.sleep(.005)  # Existing Qt/HTTP wait pattern releases the GIL.
        raise AssertionError(message())
    def capture(window,name,size):
        output=os.environ.get('CAELAB_PORTABLE_RENDER_DIR')
        window.resize(*size);window.show();app.processEvents()
        if output:
            folder=Path(output);folder.mkdir(parents=True,exist_ok=True)
            assert window.grab().save(str(folder/(name+'.png')))
    try:
        with source_free(wb):
            ids=rows(made)
            expert=ExpertWindow(client,document_id=ids['expert'],poll_interval=0);windows.append(expert)
            study=StudyWindow(client,document_id=ids['study'],poll_interval=0);windows.append(study)
            report=ReportWindow(client,document_id=ids['report']);windows.append(report)
            for window in windows:
                window.show();wait(lambda w=window:w.document is not None and not w._busy,lambda w=window:w.message.text())
            wait(lambda:bool(report.assets) and not report._busy,lambda:report.message.text())
            assert not wb.manager.list()
            assert expert.document.get('portable_research_owner')
            expert.question.setPlainText('새 위치에서 아직 적용하지 않은 질문')
            expert.question.setFocus();cursor=expert.question.textCursor();cursor.select(QTextCursor.SelectionType.Document);expert.question.setTextCursor(cursor)
            before=expert.question.toPlainText();selected=cursor.selectedText()
            for choice in ('취소','저장된 내용만'):
                def choose(choice=choice):
                    dialog=app.activeModalWidget();assert isinstance(dialog,QDialog)
                    capture(dialog,'copy-choice', (540,240))
                    button=next(b for b in dialog.findChildren(QPushButton) if b.text()==choice)
                    QTest.mouseClick(button,Qt.MouseButton.LeftButton)
                QTimer.singleShot(0,choose)
                child=actions.prepare_copy(expert)
                assert expert.question.toPlainText()==before and expert.question.textCursor().selectedText()==selected
                if child:
                    windows.append(child)
                    wait(lambda:child.graph is not None and not child._busy,lambda:child.error or child.statusBar().currentMessage())
            for name,window in [('expert',expert),('study',study),('report',report)]:
                for suffix,size in [('normal',(1200,800)),('narrow',(900,700))]:capture(window,name+'-'+suffix,size)
            plan=inspect_copy(wb,list(ids.values()))
            assert plan['status']=='READY',plan['issues']
            dialog=CopyReviewDialog(plan);windows.append(dialog)
            for suffix,size in [('normal',(880,600)),('narrow',(720,500))]:capture(dialog,'copy-review-'+suffix,size)
            assert not dialog.approval.isChecked()
            dialog.reject()
            # An unapplied Report section is routed back to its existing editor.
            report.sections.setCurrentRow(0);report.edit_section()
            report.section_text.setPlainText('아직 적용하지 않은 보고서 설명')
            cursor=report.section_text.textCursor();cursor.select(QTextCursor.SelectionType.Document);report.section_text.setTextCursor(cursor)
            draft=deepcopy(report.draft)
            assert report.prepare_portable_copy() is False
            assert report.section_text.toPlainText()=='아직 적용하지 않은 보고서 설명' and report.draft==draft
            assert not wb.manager.list()
    finally:
        monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Discard)
        for window in reversed(windows):
            if hasattr(window,'_allow_close'):window._allow_close=True
            window.close()
        app.processEvents();QThreadPool.globalInstance().waitForDone(10000)
        server.shutdown();server.server_close();thread.join(3)
        closed=wb.shutdown();assert closed['joined'] and not closed['pending']
