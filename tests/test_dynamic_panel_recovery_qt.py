"""Qt draft correction only: no FreeCAD, native solver or provider calls."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest
QtWidgets=pytest.importorskip('PySide6.QtWidgets')
from PySide6 import QtCore, QtGui, QtTest
from apps.desktop_pre.dynamic_panel import make_panel
from test_dynamic_support import base_model, draft_for


@pytest.fixture
def catalog_panel():
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    state={'analyses':[],'models':{},'details':{}};reads=[];commands=[]
    def inspect(key=None):
        reads.append(key)
        return deepcopy(state['details'][key] if key is not None else
                        {name:state[name] for name in ('analyses','models')})
    panel=make_panel(QtWidgets,QtCore,NS(inspect=inspect),
        lambda *args,**kwargs:commands.append((args,kwargs)),Gui=NS(),
        on_run=lambda *a:pytest.fail('implicit solve'),on_results=lambda:None,
        on_runner=lambda:None,on_save=lambda:None)
    yield app,panel,state,reads,commands
    panel.close();panel.deleteLater();app.processEvents()


def test_empty_native_model_reload_and_reopen_refresh_analysis_and_solver(catalog_panel):
    app,panel,state,reads,commands=catalog_panel
    assert panel.analysis.count()==0 and not panel.create.isEnabled()
    row={'id':'UserAnalysis','label':'해석 1','solvers':[]}
    state['analyses'].append(row)
    panel.reload_button.click();app.processEvents()
    assert panel.analysis.currentData()=='UserAnalysis'
    assert panel.analysis.currentText()=='해석 1' and not panel.create.isEnabled()
    row['solvers'].append({'id':'UserSolver','label':'CalculiX'})
    assert panel.refresh_context() is True
    assert panel.solver.currentData()=='UserSolver' and panel.create.isEnabled()
    panel.refresh_context()
    assert panel.analysis.count()==1 and panel.solver.count()==1 and not commands


def test_catalog_refresh_preserves_analysis_and_uncreated_solver_selection(catalog_panel):
    app,panel,state,reads,commands=catalog_panel
    state['analyses']=[{'id':name,'label':name,'solvers':[
        {'id':name+'Solver1','label':'첫 솔버'},{'id':name+'Solver2','label':'두 번째 솔버'}]}
        for name in ('First','Chosen')]
    panel.reload_button.click();panel.analysis.setCurrentIndex(1);panel.solver.setCurrentIndex(1)
    state['analyses'].reverse();state['analyses'][0]['label']='사용자 해석'
    state['analyses'][0]['solvers'].reverse()
    panel.reload_button.click();app.processEvents()
    assert panel.analysis.currentData()=='Chosen' and panel.analysis.currentText()=='사용자 해석'
    assert panel.solver.currentData()=='ChosenSolver2' and not commands


def test_dirty_and_busy_refresh_keep_raw_input_and_reload_cancel(catalog_panel,monkeypatch):
    app,panel,state,reads,commands=catalog_panel
    draft=draft_for(base_model())
    state['analyses']=[{'id':'Analysis','label':'해석 1','solvers':[{'id':'Solver','label':'CalculiX'}]}]
    state['models']['Analysis']={'draft':deepcopy(draft)}
    state['details']['Analysis']={'record':{'draft':deepcopy(draft)},'can_freeze':True,'errors':[]}
    panel.reload_button.click();app.processEvents()
    assert panel.refresh_context() is True  # no edit is not a pending raw draft
    field=panel.fields['alpha_per_s'];field.setText('1e');field.textEdited.emit('1e')
    field.setSelection(0,1);token=panel.editor_token();raw=deepcopy(panel.buffer.value)
    before=len(reads)
    state['analyses'].append({'id':'Later','label':'새 해석','solvers':[]})
    assert panel.refresh_context() is False
    assert panel.editor_token()==token and panel.buffer.value==raw and len(reads)==before
    assert field.text()=='1e' and field.selectedText()=='1'
    questions=[]
    def cancel(*args):questions.append(args);return QtWidgets.QMessageBox.No
    monkeypatch.setattr(QtWidgets.QMessageBox,'question',cancel)
    panel.reload_button.click();app.processEvents()
    assert len(questions)==1 and len(reads)==before and field.text()=='1e'
    panel.buffer.busy=True
    assert panel.refresh_context() is False
    assert panel.reload() is False and len(questions)==1 and len(reads)==before
    assert panel.editor_token()==token and not commands
    panel.buffer.busy=False
    monkeypatch.setattr(QtWidgets.QMessageBox,'question',lambda *args:QtWidgets.QMessageBox.Yes)
    panel.reload_button.click();app.processEvents()
    assert panel.analysis.count()==2 and panel.analysis.currentData()=='Analysis'
    assert field.text()==draft['rayleigh']['alpha_per_s'] and not panel.buffer.pending()
    assert state['details']['Analysis']['record']['draft']==draft
    assert state['models']['Analysis']['draft']==draft
    assert not commands


@pytest.mark.parametrize('size',[(470,740),(1100,840)])
def test_error_activation_reaches_exact_editable_cell_without_applying(size,tmp_path):
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    # Windows offscreen font lookup needs the installed font explicitly loaded.
    from pathlib import Path
    korean_font=Path('C:/Windows/Fonts/malgun.ttf')
    if korean_font.is_file():QtGui.QFontDatabase.addApplicationFont(str(korean_font))
    draft=draft_for(base_model())
    second=deepcopy(draft['program']['steps'][0]);second.update(id='Step2',label='후속 진동')
    draft['program']['steps'].append(second)
    draft['initial_conditions']=[{'id':'ICtest','label':'끝단 속도','kind':'V','component':3,
        'value':'1e','target':{'body_id':'Solid','native_node_ids':[51]}}]
    info={'record':{'draft':draft},'can_freeze':False,'bodies':[],
          'errors':[{'path':'initial_conditions.0.value','message':'완전한 유한 초기값을 입력하세요.'}]}
    cat={'analyses':[{'id':'Analysis','label':'보 동해석','solvers':[{'id':'Solver','label':'CalculiX'}]}],
         'models':{'Analysis':info['record']}}
    calls=[]
    panel=make_panel(QtWidgets,QtCore,NS(inspect=lambda key=None:deepcopy(cat if key is None else info)),
        lambda *args,**kwargs:calls.append((args,kwargs)),Gui=NS(),
        on_run=lambda *a:pytest.fail('implicit solve'),on_results=lambda:None,
        on_runner=lambda:None,on_save=lambda:None)
    try:
        panel.resize(*size);panel.show();app.processEvents()
        panel.initial.setCurrentCell(0,0)
        panel.grab().save(str(tmp_path/f'dynamic-recovery-before-{size[0]}.png'))
        panel.errors.setCurrentRow(0);panel.errors.setFocus()
        QtTest.QTest.keyClick(panel.errors,QtCore.Qt.Key_Return);app.processEvents()
        assert panel.tabs.currentIndex()==0
        assert (panel.initial.currentRow(),panel.initial.currentColumn())==(0,3)
        assert panel.initial.hasFocus()
        cell=panel.initial.visualRect(panel.initial.model().index(0,3)).center()
        point=panel.initial.viewport().mapTo(panel.initial_scroll.viewport(),cell)
        assert panel.initial_scroll.viewport().rect().contains(point)
        panel.grab().save(str(tmp_path/f'dynamic-recovery-initial-{size[0]}.png'))
        QtTest.QTest.keyClick(panel.initial,QtCore.Qt.Key_F2);app.processEvents()
        edit=panel.initial.findChild(QtWidgets.QLineEdit)
        assert edit is not None
        edit.selectAll();QtTest.QTest.keyClicks(edit,'125')
        QtTest.QTest.keyClick(edit,QtCore.Qt.Key_Return);app.processEvents()
        assert panel.buffer.value['initial_conditions'][0]['value']=='125'
        assert panel.pending_snapshot()['initial_conditions'][0]['value']=='125'
        assert not panel.buttons['run'].isEnabled() and not calls
        for path,target,row,column in [('densities.0.kg_m3',panel.densities,0,1),
            ('initial_conditions.0.component',panel.initial,0,2),
            ('program.steps.1.minimum',panel.steps,1,4)]:
            item=QtWidgets.QListWidgetItem('입력 확인');item.setData(QtCore.Qt.UserRole,path)
            panel.focus_error(item);app.processEvents()
            assert (target.currentRow(),target.currentColumn())==(row,column)
            assert (target.cellWidget(row,column) or target).hasFocus()
        panel.grab().save(str(tmp_path/f'dynamic-recovery-{size[0]}.png'))
        assert not calls
    finally:
        panel.close();panel.deleteLater();app.processEvents()
