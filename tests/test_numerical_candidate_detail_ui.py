"""Optional native PySide6 tests. Offscreen execution is NOT Windows validation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import threading
import time

import pytest
pytest.importorskip('PySide6',reason='Native PySide6 UI runtime unavailable')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest, QSignalSpy

from apps.research.numerical_candidate_detail_window import NumericalCandidateDetailWindow
from caelab.numerical_candidate_detail import client_read_candidate_detail, table_rows
from _numerical_candidate_detail_support import DetailHost, intermediate


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def until(app,predicate,seconds=15):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('Native UI did not reach expected state')


class LocalClient:
    """Same existing owner/client API; no window-specific calculation shortcut."""
    def __init__(self,host):
        self.host=host
        self.reads=[]
    def document_read(self,identifier):return self.host.owner.read(identifier)
    def document_result(self,identifier,job,**kwargs):return self.host.owner.result(identifier,job,**kwargs)
    def document_command(self,identifier,operation,arguments,**kwargs):
        return self.host.owner.command(identifier,operation,arguments,**kwargs)
    def status(self,job):return self.host.manager.status(job)
    def cancel(self,job):return self.host.manager.cancel(job)
    def numerical_candidate_detail(self,doc,job,candidate,**kwargs):
        self.reads.append((doc,job,candidate,deepcopy(kwargs)))
        return client_read_candidate_detail(self,doc,job,candidate,**kwargs)


def test_native_table_curve_same_candidate_explicit_job_save_and_reopen(app,tmp_path):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit();cid=intermediate(host,doc,job)
        client=LocalClient(host)
        window=NumericalCandidateDetailWindow(client,document_id=doc,job_id=job,candidate_id=cid,poll_interval=100)
        window.show()
        until(app,lambda:window.view is not None)
        assert window.model.rows==table_rows(window.view,'T0')
        rows=window.model.rows
        plotted=list(window.figure.axes[0].lines[1].get_ydata())
        for row,value in zip(rows,plotted):
            if row['prediction'] is not None:
                assert value==row['prediction']
        for _ in range(3):window.refresh();QTest.qWait(30)
        until(app,lambda:window._read_worker is None)
        assert len(host.manager.list())==1
        assert not window.table.model().flags(window.model.index(0,0)) & Qt.ItemFlag.ItemIsEditable
        QTest.mouseClick(window.detail_button,Qt.MouseButton.LeftButton)
        until(app,lambda:window.view is not None and window.view['attempt_state']=='SUCCEEDED')
        detail=window.attempt_job_id
        assert len(host.manager.list())==2 and not window.detail_button.isEnabled()
        window.trials.setCurrentItem(window.trials.topLevelItem(2))
        assert window._trial_id()=='T2' and all(row['role']=='holdout' for row in window.model.rows)
        saved_rows=deepcopy(window.model.rows)
        QTest.mouseClick(window.save_button,Qt.MouseButton.LeftButton)
        until(app,lambda:not window._writing and window.view is not None and not window.view['dirty'])
        spy=QSignalSpy(window.destroyed)
        window.close()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        assert spy.count()==1
    with DetailHost(tmp_path,evaluator=lambda *args:pytest.fail('Reopen evaluated')) as reopened:
        window=NumericalCandidateDetailWindow(LocalClient(reopened),document_id=doc,job_id=job,candidate_id=cid)
        until(app,lambda:window.view is not None)
        assert not window.detail_button.isEnabled() # original view requires explicit latest-attempt selection
        QTest.mouseClick(window.latest_button,Qt.MouseButton.LeftButton)
        until(app,lambda:window.view is not None and window.attempt_job_id==detail)
        window.trials.setCurrentItem(window.trials.topLevelItem(2))
        assert window.model.rows==saved_rows and reopened.dispatched==[]
        window.close();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)


def test_native_failure_selection_and_comparison_do_not_run_jobs(app,tmp_path):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit();success=intermediate(host,doc,job);failed=intermediate(host,doc,job,'FAILED')
        window=NumericalCandidateDetailWindow(LocalClient(host),document_id=doc,job_id=job,candidate_id=success)
        until(app,lambda:window.view is not None)
        window.compare_candidates.setCurrentIndex(window.compare_candidates.findData(failed))
        until(app,lambda:window.comparison_view is not None)
        assert all(row['comparison_prediction'] is None for row in window.model.rows)
        window.candidates.setCurrentIndex(window.candidates.findData(failed))
        until(app,lambda:window.view is not None and window.view['candidate']['candidate_id']==failed)
        assert '실패' in window.status.text() and 'FAILED' in window.status.toolTip()
        assert all(row['prediction'] is None for row in window.model.rows)
        assert len(host.manager.list())==1
        window.close();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)


def test_late_read_cannot_replace_new_selection_and_close_abandons_reader(app,tmp_path):
    entered,release=threading.Event(),threading.Event()
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit();first=intermediate(host,doc,job);second=intermediate(host,doc,job,'FAILED')
        class Delayed(LocalClient):
            def numerical_candidate_detail(self,doc,job,cid,**kwargs):
                view=super().numerical_candidate_detail(doc,job,cid,**kwargs)
                if cid==first and not release.is_set():
                    entered.set();assert release.wait(10)
                return view
        window=NumericalCandidateDetailWindow(Delayed(host),document_id=doc,job_id=job,candidate_id=first)
        until(app,entered.is_set)
        window.candidate_id=second;window._selection_changed()
        assert window.model.rows==[] and window.trials.topLevelItemCount()==0
        assert '읽는 중' in window.identity.text()
        until(app,lambda:window.view is not None and window.view['candidate']['candidate_id']==second)
        release.set();QTest.qWait(100);app.processEvents()
        assert window.view['candidate']['candidate_id']==second
        assert all(row['candidate_id']==second for row in window.model.rows)
        spy=QSignalSpy(window.destroyed);window.close()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        assert spy.count()==1 and len(host.manager.list())==1


def test_native_row_point_identity_and_retained_segment_gaps(app,tmp_path):
    from types import SimpleNamespace
    from caelab.numerical_candidate_detail import experiment_snapshot
    from caelab.storage import canonical_hash
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit();cid=intermediate(host,doc,job)
        view=host.view(doc,job,cid)
        # Synthetic immutable display packet with two explicitly retained
        # intervals; this is a GUI fixture, not a new evaluator output.
        experiment=view['fit_input']['inputs']['experiments'][0]
        experiment['observations']['segments']=[{'rows':[0,2]},{'rows':[2,4]}]
        trial=view['trials'][0]
        trial['curve']['observations']=deepcopy(experiment['observations'])
        trial['experiment_sha256']=canonical_hash(experiment_snapshot(experiment))
        view['fit_input']['inputs_sha256']=canonical_hash(view['fit_input']['inputs'])
        window=NumericalCandidateDetailWindow(None,document_id=doc,job_id=job,candidate_id=cid,auto_load=False)
        try:
            window.view=view;window._populate();window.show()
            lines=[line for line in window.figure.axes[0].lines if hasattr(line,'_detail_rows')]
            assert all(len(line.get_xdata())==2 for line in lines)
            window._point_picked(SimpleNamespace(artist=lines[-1],ind=[1]))
            assert window.table.selectionModel().selectedRows()[0].row()==3
            assert window.model.rows[3]['source_row']==7
            assert list(window.figure.axes[0].lines[-1].get_xdata())==[3.]
            window.table.setFocus();QTest.keyClick(window.table,Qt.Key.Key_Up)
            assert window.table.selectionModel().selectedRows()[0].row()==2
            assert list(window.figure.axes[0].lines[-1].get_xdata())==[2.]
            assert len(host.manager.list())==1
        finally:
            window.close();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
