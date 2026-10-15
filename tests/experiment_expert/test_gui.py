"""Native Qt smoke only when PySide6 is installed; NOT a Windows claim."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication,QMessageBox
from apps.research.experiment_analysis_window import ExperimentAnalysisWindow
from .support import ServiceHost
from .test_actions import Client
from .test_file_workflow import import_source


def pump(window,app):
    limit=time.monotonic()+8
    while window._worker is not None and time.monotonic()<limit:
        app.processEvents();time.sleep(.005)
    app.processEvents();assert window._worker is None


@pytest.mark.parametrize('size',[(980,720),(1440,900)])
def test_actual_qt_two_sizes_unknown_defaults_save_and_no_read_evaluation(tmp_path,size):
    app=QApplication.instance() or QApplication([])
    with ServiceHost(tmp_path) as h:
        _,_,source=import_source(h);client=Client(h);n=len(h.manager.list())
        window=ExperimentAnalysisWindow(client,source=source);window.resize(*size);window.show();pump(window,app)
        assert window._view is not None,window.message.text()
        assert len(h.manager.list())==n and len(h.owner.list())==0
        request=window.request_value()
        assert request['inputs']['specification']['dependence']=={'kind':'UNKNOWN'}
        assert all(v['value'] is None for v in request['inputs']['specification']['uncertainties'].values())
        window._start('save');pump(window,app)
        assert window.document and window.document['saved_revision']
        assert len(h.manager.list())==n
        window.dirty=False;window.done(0)
        assert not window.timer.isActive()


def test_gui_callback_failure_keeps_input_and_blocks_stale_delivery(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    with ServiceHost(tmp_path) as h:
        _,_,source=import_source(h);client=Client(h)
        window=ExperimentAnalysisWindow(client,source=source);pump(window,app)
        window.inputs.item(0,4).setText('unfinished input')
        before=window.inputs.item(0,4).text()
        window._callback=lambda _:(_ for _ in ()).throw(ValueError('display failure'))
        window._finished({},None)
        assert window.inputs.item(0,4).text()==before
        assert '보존' in window.message.text()
        window._closed=True;window._callback=lambda _:pytest.fail('late callback')
        window._finished({},None)
        window.dirty=False;window.done(0)


def test_qt_reopen_preserves_covariance_units_and_supplied_source(tmp_path):
    from caelab.experiment_analysis_actions import read_analysis_source,ExplicitAnalysisAction
    from caelab.experiment_analysis_service import uncertainty_request
    app=QApplication.instance() or QApplication([])
    with ServiceHost(tmp_path) as h:
        _,_,source=import_source(h);client=Client(h);view=read_analysis_source(client,source=source)
        variables=view['problem']['variables'];n=len(variables);units=[v['unit'] for v in variables];units[-1]='kN'
        s={'uncertainties':{variables[0]['id']:{'kind':'standard','value':.001,'unit':'V','source':{'certificate':'provided'}}},
           'dependence':{'kind':'covariance','order':[v['id'] for v in variables], 'units':units,'matrix':[[None]*n for _ in range(n)],'note':'provided'},
           'axis_uncertainty':'UNKNOWN'}
        request=uncertainty_request(source,s)
        receipt=ExplicitAnalysisAction(request,'save',source_reference=view['source_reference'],session_id=view['session_id']).perform(client)
        window=ExperimentAnalysisWindow(client,document_id=receipt['document']['id']);pump(window,app)
        value=window.request_value()['inputs']['specification']
        assert value['dependence']['units']==units
        assert value['uncertainties'][variables[0]['id']]['source']=={'certificate':'provided'}
        window.dirty=False;window.close();app.processEvents();assert window._closed
