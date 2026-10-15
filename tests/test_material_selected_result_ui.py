"""Selected Core reads use transport doubles; no physics/backend execution."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import threading
import time
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication, QDialog
from apps.research.material_test_dialog import ExperimentDialog
from caelab.material_document import default_draft


def data():
    axis=[dict(name='time',unit='s',values=[0.,1.])]
    shared=dict(kind='series',component='xx',frame='material_cartesian',location='material_point',reduction='none',axes=axis)
    return dict(execution_status='FAILED',diagnostics={'processing_status':'PARTIAL'},responses={
        'P':dict(shared,unit='MPa',measure='first_Piola',value=[0.,2.]),
        'e':dict(shared,unit='1',measure='engineering_strain',value=[0.,.01])})


@pytest.fixture
def app():
    app=QApplication.instance() or QApplication([])
    yield app
    for window in app.topLevelWidgets():
        if isinstance(window,ExperimentDialog): window.reject()
    assert QThreadPool.globalInstance().waitForDone(3000)
    app.processEvents()


def wait(app,condition):
    end=time.monotonic()+3
    while time.monotonic()<end:
        app.processEvents()
        if condition(): return
        time.sleep(.005)
    raise AssertionError('Selected result callback did not settle')


def dialog(reader):
    result=data(); before=deepcopy(result)
    window=ExperimentDialog(default_draft()['settings'],result,selected_result_reader=reader)
    window.protocol.setCurrentIndex(window.protocol.findData('measured'))
    window.driver.setCurrentIndex(window.driver.findData('e'))
    window.lateral_22.setText('1'); window.lateral_33.setText('1')
    window.weight.setText('1e')
    return window,result,before


def test_partial_accept_uses_only_actual_successful_selected_read(app):
    calls=[]; main=threading.get_ident()
    def reader(names):
        calls.append((names,threading.get_ident()))
        result=data(); result['execution_status']='SUCCEEDED'; return result
    window,source,before=dialog(reader)
    window._accept(); window._accept()
    wait(app,lambda:window.value is not None)
    assert calls[0][0]==['P','e'] and calls[0][1]!=main and len(calls)==1
    assert window.result()==QDialog.DialogCode.Accepted
    assert window.value['settings']['deformation_gradient'][1][0][0]==1.01
    assert window.value['weight']=='1e' and source==before and window.imported==before


def test_selected_read_failure_preserves_incomplete_text_and_can_retry(app):
    def reader(names): raise ValueError('원 처리 결과가 바뀌었습니다.')
    window,source,before=dialog(reader)
    window._accept(); wait(app,lambda:window._selection_worker is None)
    assert window.value is None and window.weight.text()=='1e'
    assert window._inputs.isEnabled() and '선택한 범위' in window.message.text()
    assert window.message.toolTip()=='원 처리 결과가 바뀌었습니다.'
    assert source==before and window.imported==before


def test_cancel_while_reading_ignores_late_success(app):
    release=threading.Event(); started=threading.Event()
    def reader(names):
        started.set(); release.wait(2)
        result=data(); result['execution_status']='SUCCEEDED'; return result
    window,source,before=dialog(reader)
    window._accept(); wait(app,started.is_set)
    window.reject(); release.set()
    assert QThreadPool.globalInstance().waitForDone(3000)
    app.processEvents()
    assert window.result()==QDialog.DialogCode.Rejected and window.value is None
    assert window.weight.text()=='1e' and source==before and window.imported==before


@pytest.mark.parametrize('status,names',[('FAILED',['P','e']),('SUCCEEDED',['P'])])
def test_incomplete_or_different_selected_result_is_not_accepted(app,status,names):
    def reader(request):
        result=data(); result['execution_status']=status
        result['responses']={name:result['responses'][name] for name in names}
        return result
    window,source,before=dialog(reader)
    window._accept(); wait(app,lambda:window._selection_worker is None)
    assert window.value is None and window.weight.text()=='1e' and window.imported==before
