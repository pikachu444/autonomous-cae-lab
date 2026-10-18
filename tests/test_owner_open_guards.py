"""Actual HTTP/local IPC refusal before a replacement owner can be launched."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import threading
import time
import uuid

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication
from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from apps.research import desktop
from apps.research.result_return import _route,_lock,service_identity
from caelab.workbench_client import Client,WorkbenchHTTPError


@pytest.fixture
def service(tmp_path,monkeypatch):
    server=LabHTTPServer(LabService(tmp_path/'보관소'),0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    def forbidden(*a,**k):raise AssertionError('Owner opening cannot submit')
    monkeypatch.setattr(server.workbench,'submit',forbidden)
    monkeypatch.setattr(server.workbench.manager,'submit',forbidden)
    client=Client(f'http://127.0.0.1:{server.server_port}')
    try:yield client,server.workbench
    finally:server.shutdown();server.server_close();thread.join(3);server.workbench.shutdown()


def wait(app,future):
    deadline=time.monotonic()+10
    while not future.done() and time.monotonic()<deadline:
        app.processEvents();time.sleep(.003)
    assert future.done(),'Local activation did not finish'
    return future.result()


@pytest.mark.parametrize('field',['target_id','session_id'])
def test_forged_activation_receipt_cannot_open_replacement(service,monkeypatch,field):
    app=QApplication.instance() or QApplication([])
    client,wb=service;doc=client.document_open(kind='study',title='같은 이름 연구')
    doc=client.document_command(doc['id'],'document.save',{},session_id=doc['session_id'],
        expected_generation=doc['generation'],command_id='C'+uuid.uuid4().hex)['document']
    name,path=_route(service_identity(client.url),doc['id']);lock=_lock(path);assert lock.tryLock(0)
    server=QLocalServer();server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    sockets=[];received=[];spawned=[]
    assert server.listen(name)
    def connected():
        socket=server.nextPendingConnection();sockets.append(socket)
        def reply():
            if not socket.canReadLine():return
            message=json.loads(bytes(socket.readLine()).decode('utf-8'));received.append(message)
            answer={'status':'ACTIVATED','target_id':message['target_id'],'session_id':message['session_id']}
            answer[field]='Sforged' if field=='session_id' else 'Sdifferent'
            socket.write((json.dumps(answer)+'\n').encode('utf-8'));socket.flush();socket.disconnectFromServer()
        socket.readyRead.connect(reply)
        if socket.bytesAvailable():reply()
    server.newConnection.connect(connected)
    monkeypatch.setattr(desktop,'_spawn',lambda *a,**k:spawned.append((a,k)) or {'status':'LAUNCH_REQUESTED'})
    before=client.document_read(doc['id'])['draft'];jobs={j['id'] for j in wb.manager.list()}
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(desktop.launch_tool,client,'study',document_id=doc['id'])
            with pytest.raises(RuntimeError):wait(app,future)
        assert len(received)==1 and received[0]['target_id']==doc['id']
        assert received[0]['session_id']==doc['session_id'] and received[0]['operation']=='activate'
        assert not spawned
        assert client.document_read(doc['id'])['draft']==before
        assert {j['id'] for j in wb.manager.list()}==jobs
    finally:
        for socket in sockets:socket.abort();socket.deleteLater()
        server.close();QLocalServer.removeServer(name);lock.unlock();app.processEvents()


@pytest.mark.parametrize('target',['missing','other_kind'])
def test_exact_target_checked_before_material_process(service,monkeypatch,target):
    client,wb=service;spawned=[]
    doc=client.document_open(kind='study',title='다른 종류의 같은 이름')
    identifier='M'+uuid.uuid4().hex if target=='missing' else doc['id']
    monkeypatch.setattr(desktop,'_spawn',lambda *a,**k:spawned.append((a,k)) or {'status':'LAUNCH_REQUESTED'})
    with pytest.raises((ValueError,WorkbenchHTTPError,FileNotFoundError)):
        desktop.launch_tool(client,'material',document_id=identifier)
    assert not spawned
    assert client.document_read(doc['id'])['kind']=='study'
    assert not wb.manager.list()
