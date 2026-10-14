"""Actual offscreen Qt, supplied native logs, synthetic owner commands/errors."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
import json
import pytest
from PySide6 import QtCore as C, QtWidgets as W, QtGui as G, QtTest as T
from test_pre_fem_edit import native, Object
from test_pre_fem_panel_ui import app
from test_ns1_convergence_controls import draft
from test_ns1_convergence_logs import supplied, FIXTURE, cvgrow, header, stdoutblock, stdout
from apps.desktop_pre.fem_panel import make_panel
from apps.desktop_pre import convergence
from apps.research.contact_run_dialog import ContactRunDialog
from apps.research.convergence_view import metric_value, ConvergenceView
from caelab.calculix_convergence import read_convergence, read_cvg, read_stdout, combine


@pytest.fixture(scope='module',autouse=True)
def installed_offscreen_font(app):
    # Windows offscreen does not enumerate system fonts; normal Windows entry does.
    path=Path('C:/Windows/Fonts/malgun.ttf')
    identifier=G.QFontDatabase.addApplicationFont(str(path)) if app.platformName()=='offscreen' and path.is_file() else -1
    yield
    if identifier>=0:G.QFontDatabase.removeApplicationFont(identifier)


@pytest.fixture
def pre(native,app):
    pending=[]
    def submit(op,args,target,on_done=None):
        pending.append((op,deepcopy(args),deepcopy(target),on_done));return {'queued':True}
    n=native;n.solver.IterationsControlParameterTimeUse=True
    n.solver.IterationsControlParameterIter=draft()['iterations'];n.solver.IterationsControlParameterCutb=draft()['factors']
    widget=make_panel(W,C,n.editor,submit);widget.timer.stop()
    widget.tabs.setCurrentWidget(widget.convergence_page)
    def finish():
        op,args,target,done=pending.pop(0)
        done({'status':'COMPLETED','result':convergence.dispatch(n.editor,op,args,target)})
    widget.pending=pending;widget.finish=finish
    yield widget
    widget.close();widget.deleteLater();app.processEvents()


@pytest.mark.parametrize('width',[480,1100])
def test_native_convergence_table_save_invalid_repair_and_keyboard(pre,native,app,width):
    p=pre.convergence_page
    pre.resize(width,820);pre.show();app.processEvents()
    assert pre.width()==width
    assert p.solver.currentData()==('Analysis','Solver')
    p.enabled.setChecked(True)
    p.table.setCurrentCell(0,1);p.table.editItem(p.table.item(0,1));app.processEvents()
    editor=next((e for e in p.table.findChildren(W.QLineEdit) if e.isVisible()),None)
    assert editor
    T.QTest.keyClicks(editor,'1e-');T.QTest.keyClick(editor,C.Qt.Key_Tab);app.processEvents()
    assert p.buffer['field'].split(',')[0]=='1e-'
    assert not p.apply_button.isEnabled() and p.save_button.isEnabled()
    p.save_button.click();assert pre._command_busy and not p.table.isEnabled()
    pre.finish();app.processEvents()
    assert native.metadata['convergence_drafts'][0]['draft']['field'].startswith('1e-')
    assert p.state.text().startswith('실행 차단')
    target=os.environ.get('NS1_RENDER_DIR')
    if target:
        folder=Path(target);folder.mkdir(parents=True,exist_ok=True)
        pre.grab().save(str(folder/f'convergence-settings-error-{width}.png'))
    p.error_button.click();app.processEvents()
    editor=next((e for e in p.table.findChildren(W.QLineEdit) if e.isVisible()),None)
    assert editor
    T.QTest.keyClick(editor,C.Qt.Key_A,C.Qt.ControlModifier)
    T.QTest.keyClicks(editor,'0.005');T.QTest.keyClick(editor,C.Qt.Key_Tab);app.processEvents()
    assert p.apply_button.isEnabled(), (p.buffer,p.errors,p.state.text())
    p.apply_button.click();pre.finish();app.processEvents()
    assert p.info['applied'] and native.solver.IterationsControlParameterIter==draft()['iterations']
    assert p.table.horizontalHeaderItem(3).text()=='단위'
    assert p.width()<=pre.width() and p.table.width()>300
    scroll=p.parentWidget().parentWidget()
    assert isinstance(scroll,W.QScrollArea)
    origin=p.enabled.mapTo(scroll.viewport(),C.QPoint(0,0))
    assert origin.x()>=0 and origin.x()+p.enabled.width()<=scroll.viewport().width()
    assert p.enabled.width()>=p.enabled.sizeHint().width()
    root=os.environ.get('NS1_RENDER_DIR')
    if root:
        folder=Path(root);folder.mkdir(parents=True,exist_ok=True)
        pre.grab().save(str(folder/f'convergence-settings-{width}.png'))


def test_late_receipt_cannot_replace_other_solver_selection(pre,native,app):
    p=pre.convergence_page;p.enabled.setChecked(True);p.table.item(0,1).setText('.006');p.save_button.click()
    other=Object(native.doc,'OtherSolver','Fem::SolverCcxTools',Suppressed=False)
    native.analysis.Group.append(other)
    p.refresh(load_forms=True)
    p.solver.setCurrentIndex(1)
    p.table.item(0,1).setText('.009')  # Programmatic adversarial edit while former receipt is pending.
    pre.finish()
    assert p.loaded==('Analysis','OtherSolver')
    assert p.buffer['field'].startswith('.009')
    assert native.metadata['convergence_drafts'][0]['solver_id']=='Solver'
    p.solver.setCurrentIndex(0)
    assert p.buffer['field'].startswith('.006')


def record():
    r=supplied();r['convergence_history']=read_convergence(FIXTURE,r['executed_setup'],r['increment_history'],execution_status=r['execution_status'],flat=True)
    return r


@pytest.mark.parametrize('width',[740,1100])
def test_retained_iteration_graph_units_original_values_and_reopen_selection(app,tmp_path,width,monkeypatch):
    from apps.research.appearance import apply_appearance
    apply_appearance(app)
    C.QSettings.setDefaultFormat(C.QSettings.IniFormat)
    C.QSettings.setPath(C.QSettings.IniFormat,C.QSettings.UserScope,str(tmp_path/'prefs'))
    r=record();before=deepcopy(r);parent=W.QWidget()
    d=ContactRunDialog(parent,'retained-'+str(width),r);d.resize(width,880);d.show();app.processEvents()
    d.views.setCurrentIndex(0);d.convergence.canvas.draw()
    assert d.width()==width and d.convergence.ratios.rowCount()==5
    v=d.convergence
    assert v.ratios.item(4,1).text()=='0.003752'
    assert v.ratios.item(4,2).text()=='0.08743'
    assert '수렴' in v.ratios.item(4,4).text()
    v.ratios.selectRow(4);app.processEvents()
    assert v.raw.item(0,1).text()=='0.002095'
    assert v.raw.item(0,3).text()=='93' and v.raw.item(0,4).text()=='2'
    assert v.raw.item(0,2).text()=='N'
    v.metric.setCurrentIndex(6);app.processEvents();v.canvas.draw()
    assert v.figure.axes[0].get_ylabel()=='최대 변위 보정 [mm]'
    assert not v.criterion.isEnabled()
    v.metric.setCurrentIndex(1);v.criterion.setChecked(True);app.processEvents();v.canvas.draw()
    assert v.figure.axes[0].get_ylabel()=='변위 보정 비율 [%]'
    assert len(v.figure.axes[0].lines)==2
    bbox=v.figure.bbox;renderer=v.canvas.get_renderer()
    for axis in (v.figure.axes[0].xaxis,v.figure.axes[0].yaxis):
        b=axis.label.get_window_extent(renderer)
        assert b.x0>=bbox.x0 and b.x1<=bbox.x1 and b.y0>=bbox.y0 and b.y1<=bbox.y1
    target=os.environ.get('NS1_RENDER_DIR')
    if target:
        folder=Path(target);folder.mkdir(parents=True,exist_ok=True)
        d.grab().save(str(folder/f'convergence-monitor-{width}.png'))
        v.tables.setCurrentIndex(1);v.metric.setCurrentIndex(2);app.processEvents()
        d.grab().save(str(folder/f'convergence-original-values-{width}.png'))
    d.attempts.selectRow(7);v.metric.setCurrentIndex(6);d.close();app.processEvents()
    restored=ContactRunDialog(parent,'retained-'+str(width),r)
    assert restored.rows[restored.attempts.currentRow()]['increment']==8
    assert restored.convergence.metric.currentIndex()==6
    assert r==before
    restored.close();parent.close()


def test_missing_sentinel_failed_partial_are_not_plotted_as_physical_zero(app):
    setup={'step':{'period':1}}
    out=read_stdout('x',setup,data=stdout(stdoutblock(decision='no convergence'))+b' iteration 2\n largest residual force=1e-')
    cvg=read_cvg('x',data=(header()+cvgrow(r=1e30,c=1e-30)).encode())
    sta={'rows':[{'step':1,'increment':1,'attempt':1,'iterations':2,'converged':False,'line':1,'total':0,'increment_size':.1}]}
    h={'rows':combine(cvg,out,sta,execution_status='FAILED'),'sources':{'cvg':cvg,'stdout':out}}
    w=ConvergenceView(h);w.select_attempt((1,1,1));w.show();app.processEvents();w.canvas.draw()
    assert '거절 시도' in w.status.text() and '끝부분 미완성' in w.status.text()
    assert '분모 극소' in w.ratios.item(0,1).text()
    assert metric_value(w.rows[0],'cvg','residual_force_pct') is None
    assert len(w.figure.axes[0].lines)==0
    assert w.ratios.item(1,1).text()=='미기록'
    w.close()


@pytest.mark.parametrize('wrong_attempt',[False,True])
def test_legacy_log_button_verifies_exact_attempt_and_keeps_selection(app,tmp_path,monkeypatch,wrong_attempt):
    import shutil
    source=supplied()
    old=deepcopy(source)
    # Simulate a legacy result that recorded no STA first row. Restoring the CVG
    # row inserts an earlier unconfirmed attempt, not a shift of the selection.
    old['increment_history']['rows']=old['increment_history']['rows'][1:]
    solver=tmp_path/'solver';solver.mkdir()
    for name in ('contact.cvg','ccx_contact.stdout.log'):
        shutil.copyfile(FIXTURE/name,solver/name)
    if wrong_attempt:
        for pin in source['artifacts']:
            if pin['relative']=='solver/contact.cvg':pin['sha256']='0'*64
    path=tmp_path/'contact_execution.json';path.write_text(json.dumps(source))
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    class Parent(W.QWidget):
        def __init__(self):super().__init__();self.errors=[];self.calls=[]
        def _request(self,key,work,done,**kwargs):
            self.calls.append(key)
            try: value=work()
            except ValueError as e:self.errors.append(str(e));return
            done(value,None)
    parent=Parent();d=ContactRunDialog(parent,'legacy-read-'+str(wrong_attempt),old)
    d.show();app.processEvents()
    for i,r in enumerate(d.rows):
        if r['increment']==8:d.attempts.selectRow(i);break
    monkeypatch.setattr(W.QFileDialog,'getOpenFileName',lambda *_:(str(path),''))
    d.open_logs();app.processEvents()
    if wrong_attempt:
        assert parent.errors and not d.history.get('rows')
    else:
        assert not parent.errors and len(d.history['rows'])==25
        assert d.rows[d.attempts.currentRow()]['increment']==8
        assert d.rows[0]['converged'] is None  # missing STA never promoted
    assert len(parent.calls)==1 and parent.calls[0].startswith('contact-logs:')
    assert all(p.read_bytes()==raw for p,raw in before.items())
    d.close();parent.close()


@pytest.mark.parametrize('export_only',[False,True])
def test_pending_convergence_editor_blocks_prepare_and_run(pre,native,app,monkeypatch,export_only):
    import sys
    from apps.desktop_pre.connection import Connection
    p=pre.convergence_page;p.enabled.setChecked(True);p.table.item(0,1).setText('1e-')
    assert p.pending_changes('Analysis','Solver') and not p.pending_changes('Other','Solver')
    monkeypatch.setitem(sys.modules,'femtools',NS(femutils=NS(type_of_obj=lambda obj:obj.TypeId)))
    monkeypatch.setitem(sys.modules,'FemGui',NS(getActiveAnalysis=lambda:native.analysis))
    c=Connection.__new__(Connection);c.pending=None;c.App=native.App
    c.owners={native.doc.Name:(native,)};c.panels={native.doc.Name:{'fem':NS(widget=lambda:pre)}}
    c.message=W.QLabel()
    c.run(export_only=export_only)
    assert c.pending is None and '수렴 설정에 미저장' in c.message.text()
    assert pre.pending==[]  # No native command or solver submission was sent.
