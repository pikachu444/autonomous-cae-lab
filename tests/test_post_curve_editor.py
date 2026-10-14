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
    draft=editor.draft();draft['max_gap']='1e';draft['a']['rows']=[0,'-']
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
    dialog.close()
