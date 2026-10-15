"""Existing HTTP/owner recovery of unsaved widget text; no solver or job submit."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import threading
import time
from pathlib import Path
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt,QTimer,QThreadPool
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QLineEdit,QMessageBox
from apps.lab.service import LabService
from apps.lab.server import LabHTTPServer
from apps.research.data_window import DataWindow
from apps.research.material_window import MaterialWindow
from apps.research.data_material_recovery_dialog import RecoveryKeepDialog
from apps.research.data_material_recovery_read import RecoveryReadDialog
from apps.research.data_material_recovery_host import inspect_recovery
from caelab.workbench_client import Client
from caelab.data_document import default_draft as data_draft
from caelab.material_document import default_draft as material_draft


@pytest.fixture
def app():
    app=QApplication.instance() or QApplication([])
    from apps.research.appearance import apply_appearance
    apply_appearance(app)
    yield app
    for window in app.topLevelWidgets():
        if isinstance(window,(DataWindow,MaterialWindow)):
            window._allow_close=True; window.close()
    assert QThreadPool.globalInstance().waitForDone(5000)
    app.processEvents()


@pytest.fixture
def backend(tmp_path):
    service=LabService(tmp_path); server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    client=Client(f'http://127.0.0.1:{server.server_port}')
    yield server.workbench,client
    server.shutdown();server.server_close();service.shutdown();thread.join(2)


def wait(app,condition):
    end=time.monotonic()+8
    while time.monotonic()<end:
        app.processEvents()
        if condition(): return
        QTest.qWait(5)
    raise AssertionError('Recovery host did not settle')


def later(kind,action):
    def find():
        dialog=next((w for w in QApplication.topLevelWidgets() if isinstance(w,kind) and w.isVisible()),None)
        if dialog is None:QTimer.singleShot(5,find);return
        action(dialog)
    QTimer.singleShot(5,find)


def click_question(text):
    def click(dialog):
        next(button for button in dialog.buttons() if button.text()==text).click()
    later(QMessageBox,click)


def open_view(w,client,kind):
    if kind=='data':
        receipt=w.upload('미저장 원본.csv',b'time,value\n0,0\n1,2\n')
        draft=data_draft();draft['data_id']=receipt['id']
        document=client.document_open(kind='data',draft=draft)
        window=DataWindow(client,auto_open=False,poll_interval=0)
        window._show_document(document);table=window.mapping;cell=table.item(1,8)
    else:
        document=client.document_open(kind='material',draft=material_draft())
        window=MaterialWindow(client,auto_open=False,poll_interval=0)
        window._show_document(document);table=window.coefficients;cell=table.item(0,1)
    window.show();window.activateWindow();wait(QApplication.instance(),lambda:not window._busy)
    table.setCurrentItem(cell);table.editItem(cell)
    QApplication.processEvents();line=next(e for e in table.findChildren(QLineEdit) if e.isVisible())
    line.setText('1e3');line.setSelection(2,-2)
    return window,document,line


def capture(widget,name,size):
    directory=os.environ.get('CAELAB_RECOVERY_RENDER_DIR')
    if not directory:return
    folder=Path(directory);folder.mkdir(parents=True,exist_ok=True)
    widget.resize(*size);QApplication.processEvents();QTest.qWait(40)
    assert widget.grab().save(str(folder/(name+'.png')))


@pytest.mark.parametrize('kind',['material','data'])
def test_cancel_then_keep_and_explicit_reopen_exact_unfinished_cell(app,backend,kind):
    w,client=backend;window,document,line=open_view(w,client,kind)
    before=deepcopy(document['draft']);jobs=w.manager.list()
    click_question('취소');window.close();app.processEvents()
    assert window.isVisible() and line.text()=='1e3' and line.selectedText()=='1e' and line.cursorPosition()==0
    click_question('편집 원문 보관')
    def keep(dialog):
        def ready():
            if dialog.keep_button.isEnabled():
                capture(dialog,kind+'-keep-normal',(720,340));capture(dialog,kind+'-keep-narrow',(600,320));dialog.keep()
            else:QTimer.singleShot(5,ready)
        ready()
    later(RecoveryKeepDialog,keep);window.close()
    wait(app,lambda:not window.isVisible())
    capsules=client.data_material('recovery.read',{'document_id':document['id']})['capsules']
    raw=capsules[-1]['capsule']['raw'];assert any(c['editor_kind']=='unfinished' and c['raw_text']=='1e3' for c in raw['cells'])
    assert raw['focus']['cursor']==0 and client.document_read(document['id'])['draft']==before
    fresh=DataWindow(client,auto_open=False,poll_interval=0) if kind=='data' else MaterialWindow(client,auto_open=False,poll_interval=0)
    fresh._show_document(client.document_read(document['id']));fresh.show();wait(app,lambda:not fresh._busy)
    def resume(dialog):
        def ready():
            if dialog.resume_button.isEnabled():dialog.resume()
            else:QTimer.singleShot(5,ready)
        ready()
    later(RecoveryReadDialog,resume);inspect_recovery(fresh)
    wait(app,lambda:getattr(fresh,'_recovery_review',None) is None)
    table=fresh.mapping if kind=='data' else fresh.coefficients
    restored=next(e for e in table.findChildren(QLineEdit) if e.isVisible())
    capture(fresh,kind+'-restored-normal',(1440,900));capture(fresh,kind+'-restored-narrow',(960 if kind=='data' else 840,690))
    assert restored.text()=='1e3' and restored.selectedText()=='1e' and restored.cursorPosition()==0
    assert client.document_read(document['id'])['draft']==before and w.manager.list()==jobs


def test_remote_owner_change_preserves_pending_cell_and_stops_close(app,backend):
    w,client=backend;window,document,line=open_view(w,client,'material')
    current=client.document_read(document['id']);draft=deepcopy(current['draft']);draft['settings']['parameters']['E']=321.
    client.document_command(current['id'],'material.update',{'draft':draft},session_id=current['session_id'],expected_generation=current['generation'],command_id='Cpeer')
    click_question('편집 원문 보관');window.close()
    wait(app,lambda:getattr(window,'_recovery_review',None) is None)
    assert window.isVisible() and line.text()=='1e3' and line.selectedText()=='1e'
    assert not client.data_material('recovery.read',{'document_id':document['id']})['capsules']
    assert client.document_read(document['id'])['draft']==draft and not w.manager.list()


def test_capsule_write_failure_keeps_window_and_exact_editor(app,backend,monkeypatch):
    import caelab.related_save_recovery as recovery
    w,client=backend;window,document,line=open_view(w,client,'material')
    original=recovery.save_json
    def failed(path,value):
        if Path(path).parent.name=='raw-recovery':raise OSError('injected capsule write failure')
        return original(path,value)
    monkeypatch.setattr(recovery,'save_json',failed)
    click_question('편집 원문 보관')
    observed=[]
    def keep(dialog):
        def ready():
            if dialog.outcome is not None:
                observed.append(dialog.outcome);dialog.reject()
            elif dialog.keep_button.isEnabled():dialog.keep();QTimer.singleShot(5,ready)
            else:QTimer.singleShot(5,ready)
        ready()
    later(RecoveryKeepDialog,keep);window.close()
    wait(app,lambda:getattr(window,'_recovery_review',None) is None)
    assert observed and not observed[0]['all_kept'] and window.isVisible()
    assert line.text()=='1e3' and line.selectedText()=='1e' and line.cursorPosition()==0
    assert client.document_read(document['id'])['draft']==document['draft'] and not w.manager.list()


def test_material_and_two_plan_buffers_keep_independent_owner_capsules(app,backend):
    from caelab.numerical_document import from_material_document
    w,client=backend
    material=client.document_open(kind='material',draft=material_draft())
    plans=[client.document_open(kind='numerical',title='피팅 '+str(i+1),draft=from_material_document(material)) for i in range(2)]
    window=MaterialWindow(client,auto_open=False,poll_interval=0);window._show_document(material);window.show()
    panel=window.open_plan_variables();wait(app,lambda:not panel._busy and panel.plans.count()==2)
    first=panel._widgets[panel.plans.currentData()]
    first.table.item(0,2).setText('2e')
    panel.plans.setCurrentIndex(1);app.processEvents();second=panel._widgets[panel.plans.currentData()]
    item=second.table.item(0,2);second.table.setCurrentItem(item);second.table.editItem(item);app.processEvents()
    line=next(e for e in second.table.findChildren(QLineEdit) if e.isVisible())
    line.setText('3e');line.setSelection(2,-2)
    window.coefficients.item(0,1).setText('1e')
    click_question('편집 원문 보관')
    def keep(dialog):
        def ready():
            if dialog.keep_button.isEnabled():dialog.keep()
            else:QTimer.singleShot(5,ready)
        ready()
    later(RecoveryKeepDialog,keep);window.close();wait(app,lambda:not window.isVisible())
    raws={d['id']:client.data_material('recovery.read',{'document_id':d['id']})['capsules'][-1]['capsule']['raw'] for d in [material,*plans]}
    assert any(c['raw_text']=='1e' for c in raws[material['id']]['cells'])
    for document in plans:
        assert client.document_read(document['id'])['draft']==document['draft']
    assert sorted(c['raw_text'] for p in plans for c in raws[p['id']]['cells'] if c['raw_text'] in ('2e','3e'))==['2e','3e']
    assert client.document_read(material['id'])['draft']==material['draft'] and not w.manager.list()
