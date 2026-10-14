"""Retry only exact retained transfer reads; no solver or job submission."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
import pytest
pytest.importorskip('PySide6')
from PySide6.QtTest import QTest
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication
from apps.research.transfer_inspection_window import TransferInspectionWindow


def settle(app,predicate):
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        QTest.qWait(5)
    raise AssertionError('Transfer read did not finish')


def test_catalog_read_failure_can_retry_same_frozen_document():
    app=QApplication.instance() or QApplication([])
    class Client:
        calls=[]
        def evaluation_transfer(self,*args,**kwargs):
            self.calls.append((args,kwargs))
            if len(self.calls)==1:raise ValueError('Retained catalog unavailable')
            return {'transfers':[],'iterations':[],'diagnostics':{}}
    client=Client();window=TransferInspectionWindow(client,'Eoriginal','Joriginal')
    try:
        window.show();settle(app,lambda:window.retry.isEnabled())
        assert window.status.text()=='Retained catalog unavailable'
        window.retry.click();settle(app,lambda:'기록된 전달' in window.status.text())
        assert client.calls==[(('Eoriginal','Joriginal'),{}),(('Eoriginal','Joriginal'),{})]
    finally:
        window.close();assert QThreadPool.globalInstance().waitForDone(3000);app.processEvents()


def test_failed_page_hides_old_rows_then_retry_restores_same_selection():
    app=QApplication.instance() or QApplication([])
    class Client:
        calls=[]
        fail=False
        def evaluation_transfer(self,*args,**kwargs):
            self.calls.append((args,kwargs))
            if len(args)==2:return {'transfers':[{'id':'F1','iteration':0,'source_name':'온도','target_name':'구조'}],
                                    'iterations':[],'diagnostics':{}}
            if self.fail:raise ValueError('Selected retained page unavailable')
            start=kwargs['start']
            return {'rows':[{'node':start+1,'coordinates':[0.,0.],'supplied':320.,'received':320.,
                             'difference':0.,'available':True}],
                    'metadata':{'unit':'K','coordinate_units':'m'},'unavailable':None,
                    'exact_values_match':True,'metadata_differences':[],
                    'target_attempt':{'state':'CLEANUP_UNCONFIRMED'},
                    'start':start,'count':1,'total':512,'reference_temperature':300.,
                    'reference_temperature_unit':'K'}
    client=Client();window=TransferInspectionWindow(client,'Eoriginal','Joriginal')
    try:
        window.show();settle(app,lambda:len(window._rows)==1)
        assert '종료 확인 필요' in window.status.text()
        client.fail=True;window.next.click()
        settle(app,lambda:window.status.text()=='Selected retained page unavailable')
        assert window.table.rowCount()==0 and not window._rows
        assert not window.previous.isEnabled() and not window.next.isEnabled() and window.page.text()==''
        assert window.retry.isEnabled()
        client.fail=False;window.retry.click();settle(app,lambda:len(window._rows)==1)
        assert client.calls[-2:]==[(('Eoriginal','Joriginal','F1',0),{'start':256})]*2
        assert window.table.item(0,0).text()=='257'
        assert '기준온도 300 [K]' in window.status.text()
    finally:
        window.close();assert QThreadPool.globalInstance().waitForDone(3000);app.processEvents()
