"""Qt curve choices/partial drafts/cancel and linked retained plots."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtWidgets import QApplication,QDialog
from apps.research.post_curve_editor import CurveEditor,default_recipe,identity
from apps.research.post_curve_plot import CurvePlot


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def catalog():
    return [{'source_ref':'Sone','revision':'Rexact','label':'인장 시험','column':'force','component':0,
        'block':[0],'axis_column':'Time','row_count':3,
        'declaration':{'units':'N','quantity':'force','measure':'force','frame':'global','location':'upper',
                       'reduction':'none','observable':{'version':1,'operation':'value','source_kind':'vector','selection':'x'}},
        'axis':{'name':'elapsed','unit':'s'}}]


def test_exact_choices_partial_edit_cancel_and_reopen(app,monkeypatch):
    rows=catalog();rows.append({**deepcopy(rows[0]),'source_ref':'Stwo','block':[1]})
    editor=CurveEditor(default_recipe(),rows);editor.resize(760,280);editor.show();app.processEvents()
    select=editor.selectors['a'];select.setCurrentIndex(select.findData(identity(rows[1])))
    assert editor.draft()['a']['source_ref']=='Stwo'
    assert editor.draft()['a']['block']==[1]
    draft=editor.draft();draft['max_gap']='1e';draft['a']['rows']=['1e','-']
    reopened=CurveEditor(draft,rows)
    monkeypatch.setattr(QDialog,'exec',lambda dialog: QDialog.DialogCode.Rejected)
    reopened.meaning('a');reopened.settings()
    assert reopened.draft()==draft
    assert editor.width()==760
    editor.close();reopened.close()


def test_retained_plot_preserves_gap_and_row_selection(app):
    rows=[{'row_index':i,'identity':{'row':r},'x':float(i),'y':float(i+1),'quality':True,
           'calculation':i!=1,'visible':True,'segment':0} for i,r in enumerate([1,2,7])]
    aligned=[{'row_index':i,'a_row':{'row':r},'b_rows':[{'row':r}],'x':float(i),'a':float(i+1),
              'b':None if i==1 else float(i+1),'delta':None if i==1 else 0.,'percent':None if i==1 else 0.,
              'valid':i!=1,'a_valid':True,'b_valid':i!=1,'a_segment':0,'b_segment':i,
              'reason':'b_excluded_or_missing' if i==1 else 'valid','percent_reason':'valid'} for i,r in enumerate([1,2,7])]
    source={'title':'시험','axis':{'name':'elapsed','unit':'s'},'declaration':{'units':'N'}}
    payload={'rows':aligned,'originals':{'a':deepcopy(rows),'b':deepcopy(rows)},
        'summary':{'sources':{'a':source,'b':source},'blocked':None,'valid_count':2,'count_a':3,'recipe':{'target_unit':'N'}}}
    dialog=CurvePlot(payload,{'revision':'Rexact'})
    selected=[];dialog.rowSelected.connect(selected.append)
    dialog.show();app.processEvents()
    assert dialog.width()==1100 and dialog.height()==780
    assert len(dialog.axes['b'].lines)==2
    assert all(len(line.get_xdata())==1 for line in dialog.axes['b'].lines)
    dialog.tables['aligned'].selectRow(2);app.processEvents()
    assert selected[-1]==2
    assert dialog.tables['aligned'].item(2,1).text()=='7'
    assert dialog.tables['a'].item(0,4).text()=='정상'
    assert '대응 좌표 [s]' in dialog.tables['aligned'].item(2,2).toolTip()
    dialog.close()


def test_all_plotted_series_select_their_actual_row(app):
    from types import SimpleNamespace
    xs, av, bv = [0.,1.,100.], [1000.,1000.,1000.], [1100.,2000.,1100.]
    source = {'title':'힘', 'axis':{'name':'시간','unit':'s'}, 'declaration':{'units':'N'}}
    def original(values):
        return [{'row_index':i,'identity':{'row':i+1},'x':x,'y':values[i],
            'quality':True,'calculation':True,'visible':True,'segment':0} for i,x in enumerate(xs)]
    rows = [{'row_index':i,'a_row':{'row':i+1},'b_rows':[{'row':i+1}], 'x':x,'a':av[i],'b':bv[i],
        'delta':bv[i]-av[i],'percent':None,'valid':True,'a_valid':True,'b_valid':True,
        'a_segment':0,'b_segment':0,'reason':'valid','percent_reason':'valid'} for i,x in enumerate(xs)]
    dialog = CurvePlot({'rows':rows,'originals':{'a':original(av),'b':original(bv)},
        'summary':{'sources':{'a':source,'b':source},'valid_count':3,'count_a':3,
                   'recipe':{'target_unit':'N'}}}, {'revision':'R'})
    selected=[];dialog.rowSelected.connect(selected.append)
    dialog.show();app.processEvents();dialog.canvas.draw()
    x,y = dialog.axes['aligned'].transData.transform((xs[0],av[0]))
    dialog.pick(SimpleNamespace(inaxes=dialog.axes['aligned'],x=x,y=y))
    assert selected[-1] == 0
    assert dialog.tables['aligned'].currentRow() == 0
    dialog.close()


def test_earlier_curve_revision_cannot_select_current_table(app):
    from types import SimpleNamespace
    from apps.research.post_window import PostWindow
    calls, selected = [], []
    view = SimpleNamespace(document_id='D', session_id='S', _object_ref='C', _sample_basis={'revision':'R0'},
        _current_sample_revision=lambda preview:'R1' if preview else 'R0',
        message=SimpleNamespace(setText=lambda text:None),
        sampleSelectionChanged=SimpleNamespace(emit=lambda *args:None),
        _samples={'rows':[{'row_index':0}]}, samples=SimpleNamespace(selectRow=selected.append),
        queue_command=lambda *args,**kw: calls.append((args,kw)) or True)
    basis={'document_id':'D','session_id':'S','object_ref':'C','revision':'R1','preview':True}
    assert PostWindow.select_curve_row(view,0,basis) is False
    assert not calls and not selected
    view._sample_basis={'revision':'R1'}
    assert PostWindow.select_curve_row(view,0,basis) is True
    view._sample_basis={'revision':'R0'}
    calls[-1][1]['accepted']({'object_ref':'C','revision':'R1'})
    assert not selected


def test_changed_channel_discards_pending_exact_reference(app, monkeypatch):
    import threading
    import time
    from types import SimpleNamespace
    from PySide6.QtCore import QThreadPool
    from apps.research.post_curve_editor import DataCurvePicker
    started, release = threading.Event(), threading.Event()
    def reference(*args):
        started.set()
        if not release.wait(3):
            raise RuntimeError('test did not release controlled read')
        return {'document_id':'D', 'job_id':'J'}
    monkeypatch.setattr(DataCurvePicker, 'load', lambda self:None)
    dialog = DataCurvePicker(SimpleNamespace(document_result_reference=reference))
    try:
        for combo, items in ((dialog.documents,[('자료','D')]),(dialog.jobs,[('저장','J')]),
                             (dialog.responses,[('힘 X','x'),('힘 Y','y')])):
            combo.blockSignals(True)
            for label, value in items:
                combo.addItem(label,value)
            combo.blockSignals(False)
        dialog.show();app.processEvents();dialog.pick()
        assert started.wait(1)
        dialog.responses.setCurrentIndex(1)
        release.set()
        end = time.monotonic()+3
        while dialog._workers and time.monotonic()<end:
            app.processEvents();time.sleep(.001)
        app.processEvents()
        assert not dialog._workers
        assert dialog.selected is None and dialog.isVisible()
        assert dialog.responses.currentData() == 'y'
    finally:
        release.set();dialog.close()
        QThreadPool.globalInstance().waitForDone(3500)
        app.processEvents()
