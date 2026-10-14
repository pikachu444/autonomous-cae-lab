"""Retained increment read failures never display another increment's evidence."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import threading
import time

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from apps.research.constitutive_inspection_window import ConstitutiveInspectionWindow


def retained(index):
    return {'increment':index,'increments':[{'index':i,'time':float(i),'unit':'s'} for i in (0,1)],
        'backend':'material.mfront.hyperelastic','pair':'dP / dF','tangent_unit':'MPa',
        'frame':'material_cartesian','tangent':[[30.+index]],'components':['xx'],
        'state_initial':{'alpha':0.},'state_trial':{'alpha':float(index)},
        'state_committed':{'alpha':float(index)},'quantities':[],
        'finite_differences':[],'build':{},'unavailable':['보존하지 않은 독립 섭동']}


class Client:
    def __init__(self):
        self.calls=[];self.block=threading.Event();self.entered=threading.Event();self.fail=True
    def constitutive_inspect(self,document,job,index):
        self.calls.append((document,job,index))
        if index==1:
            self.entered.set();assert self.block.wait(5)
            if self.fail:raise RuntimeError('retained read unavailable at exact increment 1')
        return deepcopy(retained(index))


def wait(app,predicate):
    until=time.monotonic()+8
    while time.monotonic()<until:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise AssertionError('Retained increment read did not settle')


def test_exact_increment_retry_clears_stale_evidence_without_evaluation():
    app=QApplication.instance() or QApplication([]);client=Client()
    window=ConstitutiveInspectionWindow(client,'Mexact','Jexact');window.show()
    try:
        wait(app,lambda:window._data is not None)
        assert window.availability.text() and window.status.toolTip()=='material_cartesian'
        window.increment.setCurrentIndex(window.increment.findData(1))
        wait(app,client.entered.is_set)
        assert window._data is None and not window.retry.isEnabled() and not window.probe.isEnabled()
        assert not window.status.toolTip() and not window.availability.text()
        assert window.tangent.rowCount()==window.states.rowCount()==window.probes.rowCount()==0
        client.block.set();wait(app,lambda:window.retry.isEnabled())
        assert window._data is None and '다시 읽기' in window.status.text()
        assert window.status.toolTip()=='retained read unavailable at exact increment 1'
        client.fail=False;QTest.mouseClick(window.retry,Qt.MouseButton.LeftButton)
        wait(app,lambda:window._data is not None)
        assert window._data['increment']==1 and window.tangent.item(0,0).text()=='31'
        assert client.calls==[('Mexact','Jexact',0),('Mexact','Jexact',1),('Mexact','Jexact',1)]
        assert not window.probe.isEnabled() and window.status.toolTip()=='material_cartesian'
    finally:
        client.block.set();window.close();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()


def test_explicit_probe_submission_cannot_be_displaced_by_read_retry(monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    from caelab.material_document import default_draft
    app=QApplication.instance() or QApplication([]);client=Client();entered=threading.Event();release=threading.Event()
    commands=[]
    def open_document(**kwargs):
        commands.append(kwargs);entered.set();assert release.wait(5)
        raise RuntimeError('creation reply lost')
    client.document_open=open_document
    monkeypatch.setattr(QInputDialog,'getItem',lambda *a,**k:('xx',True))
    monkeypatch.setattr(QInputDialog,'getText',lambda *a,**k:('1e-6',True))
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    window=ConstitutiveInspectionWindow(client,'Mexact','Jexact');window.show()
    try:
        wait(app,lambda:window._data is not None)
        window._data.update(backend='material.felupe',draft=default_draft())
        window.request_probe();wait(app,entered.is_set)
        assert not window.retry.isEnabled() and not window.increment.isEnabled()
        release.set();wait(app,lambda:window.retry.isEnabled())
        assert window.increment.isEnabled() and not window.probe.isEnabled()
        assert window.status.toolTip()=='creation reply lost' and '미확인' in window.status.text()
        assert len(commands)==1 and len(client.calls)==1
    finally:
        release.set();window.close();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
