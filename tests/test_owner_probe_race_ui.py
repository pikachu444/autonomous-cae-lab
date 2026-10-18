"""A transient absence probe must not suppress the first actual owner."""
import os
from types import SimpleNamespace
import uuid

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication,QMainWindow,QLabel
from apps.research import result_return as protocol


@pytest.mark.parametrize('held',[False,True])
def test_first_binding_distinguishes_released_probe_from_living_lock(monkeypatch,held):
    app=QApplication.instance() or QApplication([])
    window=QMainWindow();window.message=QLabel(window)
    window.client=SimpleNamespace(url='http://127.0.0.1:19874')
    window.document=None
    document={'id':'M'+uuid.uuid4().hex,'kind':'material','session_id':'S'+uuid.uuid4().hex}
    _,path=protocol._route(protocol.service_identity(window.client.url),document['id'])
    original=protocol._lock
    owner_lock=original(path)
    if held:assert owner_lock.tryLock(0)
    calls=[]
    class ReleasedProbe:
        def __init__(self):self.lock=original(path);self.first=True
        def tryLock(self,timeout):
            if self.first:self.first=False;return False
            return self.lock.tryLock(timeout)
        def unlock(self):return self.lock.unlock()
    def competing_lock(selected):
        calls.append(selected)
        return ReleasedProbe() if len(calls)==1 else original(selected)
    monkeypatch.setattr(protocol,'_lock',competing_lock)
    try:
        accepted=protocol.bind_receiver(window,document)
        assert accepted is (not held)
        if accepted:
            window.document=document
            assert window._result_return.server.isListening()
            receipt=protocol.receive_local({'version':1,'operation':'activate',
                'service':protocol.service_identity(window.client.url),
                'target_id':document['id'],'session_id':document['session_id']})
            assert receipt['status']=='ACTIVATED'
        else:assert window._result_return.server is None
    finally:
        protocol.close_receiver(window)
        if held:owner_lock.unlock()
        window.close();app.processEvents()
