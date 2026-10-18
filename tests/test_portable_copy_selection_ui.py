"""Exact portable content policy and same-request recovery over existing HTTP owners."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import time

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QTimer,QThreadPool
from PySide6.QtWidgets import QApplication,QDialog,QMainWindow,QLabel,QPushButton,QPlainTextEdit
from apps.lab.service import LabService
from apps.research.connection_window import ConnectionWindow
from apps.research.connection_window_recovery import RecoverySelectionDialog
from apps.research.portable_research_actions import prepare_copy,close_children
from caelab.workbench_client import Client
from test_lab_server import running


def wait(app,condition):
    end=time.monotonic()+10
    while time.monotonic()<end:
        app.processEvents()
        if condition():return
        time.sleep(.005)
    raise AssertionError('Portable UI did not settle')


def save(client,doc,command):
    return client.document_command(doc['id'],'document.save',{},session_id=doc['session_id'],
        expected_generation=doc['generation'],command_id=command)['document']


def test_kept_choice_reads_saved_base_and_preserves_acknowledged_and_widget_text(tmp_path):
    app=QApplication.instance() or QApplication([])
    with running(LabService(tmp_path/'store')) as transport:
        client=Client('http://127.0.0.1:'+str(transport.server.server_port))
        doc=save(client,client.document_open(kind='study'),'Cbase')
        saved_revision=doc['saved_revision'];draft=deepcopy(doc['draft']);draft['question']='서버에 반영한 미저장 질문'
        doc=client.document_command(doc['id'],'study.update',{'draft':draft},session_id=doc['session_id'],
            expected_generation=doc['generation'],command_id='Cedited')['document']
        editor=QMainWindow();editor.client=client;editor.document=deepcopy(doc);editor._busy=editor._closed=editor.conflict=False
        editor.message=QLabel();raw=QPlainTextEdit('아직 적용하지 않은 1e');editor.setCentralWidget(raw)
        editor.show();inspections=[];child=None
        watchdog=QTimer();watchdog.setSingleShot(True)
        def release_modal():
            modal=app.activeModalWidget()
            if modal:
                print('UNEXPECTED_MODAL',type(modal).__name__,modal.windowTitle(),flush=True)
                modal.reject()
        watchdog.timeout.connect(release_modal);watchdog.start(8000)
        def choose_kept():
            modal=app.activeModalWidget()
            if not modal:QTimer.singleShot(5,choose_kept);return
            next(b for b in modal.findChildren(QPushButton) if b.text()=='저장된 내용만').click()
        try:
            QTimer.singleShot(5,choose_kept);child=prepare_copy(editor)
            child._persist_view=False
            wait(app,lambda:child.graph is not None and not child._busy)
            assert child._copy_draft_policy=='saved_only'
            child._review_copy=lambda value:inspections.append(value)
            child.prepare_copy()
            wait(app,lambda:inspections and not child._busy)
            result=inspections[0]
            assert result['status']=='READY' and result['draft_policy']=='saved_only'
            assert result['selections']==[{'document_id':doc['id'],'saved_revision':saved_revision}]
            assert not result['documents'][0]['draft_included']
            assert client.document_read(doc['id'])['draft']==draft
            assert raw.toPlainText()=='아직 적용하지 않은 1e'
            assert transport.server.workbench.manager.list()==[]
        finally:
            watchdog.stop()
            if child:child._layout_dirty=False
            close_children(editor);editor.close();assert QThreadPool.globalInstance().waitForDone(5000)


@pytest.mark.parametrize('failure',['reply_loss','timeout','http500','unmarked400'])
def test_copy_reply_loss_preserves_pending_request_and_other_selection_cannot_replace_it(tmp_path,monkeypatch,failure):
    app=QApplication.instance() or QApplication([])
    with running(LabService(tmp_path/'store')) as transport:
        client=Client('http://127.0.0.1:'+str(transport.server.server_port))
        first=save(client,client.document_open(kind='study'),'Cfirst')
        second=save(client,client.document_open(kind='study'),'Csecond')
        inspection=client.portable_inspect([first['id']])
        window=ConnectionWindow(client,document_id=first['id'],persist_view=False)
        original=client.portable_create;requests=[]
        if failure in {'http500','unmarked400'}:
            server_create=transport.server.workbench.portable_create;delivered=[]
            def server_lost(**kwargs):
                receipt=server_create(**kwargs);delivered.append(receipt)
                if len(delivered)==1:
                    error=RuntimeError if failure=='http500' else ValueError
                    raise error('copy published, response failed without a not-applied witness')
                return receipt
            monkeypatch.setattr(transport.server.workbench,'portable_create',server_lost)
        def lost(**kwargs):
            requests.append(deepcopy(kwargs));receipt=original(**kwargs)
            if len(requests)==1:
                error=TimeoutError if failure=='timeout' else ConnectionError
                raise error('labelled copy committed, reply lost')
            return receipt
        monkeypatch.setattr(client,'portable_create',lost)
        monkeypatch.setattr(window,'_text_dialog',lambda *a,**k:None)
        try:
            window.show();wait(app,lambda:window.graph is not None and not window._busy)
            request={'inspection':inspection,'destination':str(tmp_path/'새 경로 사본'),'approved':True,
                'command_id':'Cretained','session_id':inspection['service_session_id']}
            window._copy_pending=deepcopy(request);window.retry_copy()
            wait(app,lambda:not window._busy and len(requests)==1)
            assert window._copy_pending==request
            for i in range(window.tree.topLevelItemCount()):
                item=window.tree.topLevelItem(i)
                if item.data(0,256)==second['id']:window.tree.setCurrentItem(item)
            assert window.prepare_copy(draft_policy='saved_only') is False
            assert window._copy_pending==request and len(requests)==1
            window.retry_copy();wait(app,lambda:not window._busy and window._copy_pending is None)
            assert requests==[request,request]
            assert client.portable_verify(tmp_path/'새 경로 사본')['status']=='READY'
            assert transport.server.workbench.manager.list()==[]
        finally:
            window._copy_pending=None;window._layout_dirty=False;window.close()
            assert QThreadPool.globalInstance().waitForDone(5000)


@pytest.mark.parametrize('change_selection',[False,True])
def test_mixed_selection_catalogs_only_raw_edit_owners_and_inspects_every_document(tmp_path,monkeypatch,change_selection):
    app=QApplication.instance() or QApplication([])
    with running(LabService(tmp_path/'store')) as transport:
        client=Client('http://127.0.0.1:'+str(transport.server.server_port))
        study=save(client,client.document_open(kind='study'),'Cstudy')
        data=save(client,client.document_open(kind='data'),'Cdata')
        window=ConnectionWindow(client,persist_view=False)
        catalogs=[];inspections=[];original=client.portable_recovery_catalog
        def catalog(identifiers):catalogs.append(identifiers);return original(identifiers)
        monkeypatch.setattr(client,'portable_recovery_catalog',catalog)
        monkeypatch.setattr(window,'_review_copy',lambda value:inspections.append(value))
        timer=QTimer();selected=[]
        def accept_catalog():
            dialog=app.activeModalWidget()
            if isinstance(dialog,RecoverySelectionDialog):
                if change_selection:
                    from PySide6.QtCore import Qt
                    for index in range(window.tree.topLevelItemCount()):
                        item=window.tree.topLevelItem(index)
                        if item.data(0,Qt.ItemDataRole.UserRole)==study['id']:
                            item.setCheckState(0,Qt.CheckState.Unchecked)
                selected.append(True);dialog.accept();timer.stop()
        timer.timeout.connect(accept_catalog);timer.start(10)
        try:
            window.show();wait(app,lambda:window.graph is not None and not window._busy)
            window.prepare_copy(draft_policy='saved_only')
            wait(app,lambda:selected and not window._busy and (change_selection or inspections))
            assert catalogs==[[data['id']]]
            if change_selection:
                assert inspections==[] and '선택이 바뀌었습니다' in window.message.text()
            else:
                assert {row['document_id'] for row in inspections[0]['selections']}=={study['id'],data['id']}
                assert inspections[0]['status']=='READY' and inspections[0]['draft_policy']=='saved_only'
            assert transport.server.workbench.manager.list()==[]
        finally:
            timer.stop();window._layout_dirty=False;window.close()
            assert QThreadPool.globalInstance().waitForDone(5000)


def test_confirmed_stale_inspection_releases_pending_for_fresh_review(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    with running(LabService(tmp_path/'store')) as transport:
        client=Client('http://127.0.0.1:'+str(transport.server.server_port))
        doc=save(client,client.document_open(kind='study'),'Cbase')
        inspection=client.portable_inspect([doc['id']])
        window=ConnectionWindow(client,persist_view=False)
        inspections=[];original=client.portable_create;changed=[];dialogs=[]
        def concurrent_edit(**request):
            draft=deepcopy(doc['draft']);draft['question']='검토 뒤 다른 창에서 반영한 질문'
            updated=client.document_command(doc['id'],'study.update',{'draft':draft},
                session_id=doc['session_id'],expected_generation=doc['generation'],command_id='Cconcurrent')
            changed.append(updated['document'])
            return original(**request)
        monkeypatch.setattr(client,'portable_create',concurrent_edit)
        monkeypatch.setattr(window,'_text_dialog',lambda title,text:dialogs.append(text))
        monkeypatch.setattr(window,'_review_copy',lambda value:inspections.append(value))
        try:
            window.show();wait(app,lambda:window.graph is not None and not window._busy)
            request={'inspection':inspection,'destination':str(tmp_path/'바뀐 자료 사본'),
                'approved':True,'command_id':'Cstale','session_id':inspection['service_session_id']}
            window._copy_pending=deepcopy(request);window.retry_copy()
            wait(app,lambda:changed and not window._busy)
            assert window._copy_pending is None
            assert dialogs and '포함 자료나 문서 입력/저장 개정이 바뀌었습니다' in dialogs[0]
            assert 'not_applied' not in dialogs[0] and '"issues"' not in dialogs[0]
            assert not (tmp_path/'바뀐 자료 사본').exists()
            assert client.document_read(doc['id'])['draft']==changed[0]['draft']
            window.prepare_copy();wait(app,lambda:inspections and not window._busy)
            assert inspections[0]['status']=='READY'
            assert inspections[0]['inspection_sha256']!=inspection['inspection_sha256']
            assert transport.server.workbench.manager.list()==[]
        finally:
            window._copy_pending=None;window._layout_dirty=False;window.close()
            assert QThreadPool.globalInstance().waitForDone(5000)
