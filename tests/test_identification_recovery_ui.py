"""Saved-fit read recovery only. No new numerical/provider evaluation."""
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import QThreadPool
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from apps.research.identification_window import IdentificationWindow


def wait(app, predicate):
    limit=time.monotonic()+5
    while time.monotonic()<limit:
        app.processEvents()
        if predicate():return
        time.sleep(.005)
    raise AssertionError('Saved read did not settle')


def test_failed_saved_fit_read_retry_keeps_authored_question_and_exact_result():
    app=QApplication.instance() or QApplication([])
    class Client:
        reads=[]
        fail=True
        def document_read(self, identifier):
            self.reads.append(('document',identifier))
            if self.fail:
                self.fail=False
                raise OSError('saved source temporarily unavailable')
            return {'runs':[{'job_id':'Jfit','draft':{'variables':[]}}]}
        def document_result(self,identifier,job_id):
            self.reads.append(('result',identifier,job_id))
            return {'kind':'fit','parameters':{},'identification':{'reason':'No retained diagnosis'}}
        def document_result_reference(self,identifier,job_id):
            return {'document_id':identifier,'job_id':job_id,'input_revision':'Rinput','result_sha256':'a'*64}
    client=Client();window=IdentificationWindow(client,'Nsaved','Jfit')
    try:
        window.question.setText('다음 시험에서 측정 위치의 영향을 확인한다')
        window.note.setPlainText('제공되지 않은 불확실성은 추정하지 않는다')
        window.show()
        wait(app,lambda:not window._workers)
        window.question.setFocus()
        QTest.keyClick(window.question,Qt.Key.Key_Return)
        assert window.isVisible()
        assert not window.keep.isEnabled() and not window.report.isEnabled()
        assert window.reload_result.isEnabled()
        assert 'saved source temporarily unavailable' in window.message.text()
        authored=(window.question.text(),window.note.toPlainText())
        QTest.mouseClick(window.reload_result,Qt.MouseButton.LeftButton)
        wait(app,lambda:not window._workers and window._payload is not None)
        assert (window.question.text(),window.note.toPlainText())==authored
        assert window.keep.isEnabled() and window.report.isEnabled()
        assert client.reads==[('document','Nsaved'),('document','Nsaved'),('result','Nsaved','Jfit')]
        assert window._payload[3]['input_revision']=='Rinput'
    finally:
        window.close()
        assert QThreadPool.globalInstance().waitForDone(5000)
        window.deleteLater();app.processEvents()
