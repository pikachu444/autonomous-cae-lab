"""Real Qt button -> actual generator draft -> unchanged step compiler.

No Qt widget double: skip, rather than report a GUI pass, when Qt is absent.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
W=pytest.importorskip('PySide6.QtWidgets',reason='PySide6 absent: actual Qt acceptance NOT RUN')
from PySide6 import QtCore as C, QtTest
from apps.desktop_pre.dynamic_panel import make_panel
from caelab.contact_steps import compile_program
from caelab.dynamic_model import attach
from test_dynamic_correction_steps import example


@pytest.mark.parametrize('size',[(470,740),(1100,840)])
@pytest.mark.parametrize('case',['initial-velocity','preload-release','preload-hold'])
def test_real_add_step_button_then_apply_compiles_without_automatic_run(size,case,tmp_path,monkeypatch):
    app=W.QApplication.instance() or W.QApplication([])
    model,_,draft=example(case)
    info={'record':{'draft':deepcopy(draft)},'errors':[],'can_freeze':True,
        'bodies':[{'id':'Solid','mesh_id':'Mesh','native_node_ids':[51]}]}
    catalog={'analyses':[{'id':'Analysis','label':'한글 동해석',
        'solvers':[{'id':'Solver','label':'CalculiX'}]}], 'models':{'Analysis':info['record']}}
    editor=NS(inspect=lambda key=None:deepcopy(catalog if key is None else info))
    calls=[]
    def submit(op,args,target=None,on_done=None):
        calls.append((op,deepcopy(args)))
        assert op=='pre.dynamic.apply'
        attach(model,args['draft'])  # Real numerical/DOF/material/step admission.
        saved={**info,'record':{'draft':deepcopy(args['draft'])}}
        if on_done:on_done(saved)
    monkeypatch.setattr(W.QMessageBox,'warning',lambda *a:pytest.fail(str(a)))
    p=make_panel(W,C,editor,submit,Gui=NS(),on_run=lambda *a:pytest.fail('implicit run'),
        on_results=lambda:None,on_runner=lambda:None,on_save=lambda:None)
    try:
        p.resize(*size);p.show();app.processEvents();p.tabs.setCurrentIndex(1)
        source_index=1 if case.startswith('preload') else 0
        p.steps.setCurrentCell(source_index,0)
        buttons=[b for b in p.findChildren(W.QPushButton) if b.text()=='단계 추가']
        assert len(buttons)==1
        QtTest.QTest.mouseClick(buttons[0],C.Qt.LeftButton);app.processEvents();p.sync()
        current=p.buffer.value
        assert len(current['program']['steps'])==len(draft['program']['steps'])+1
        assert p.steps.currentRow()==source_index+1
        new=current['program']['steps'][source_index+1]
        assert new['id']!=draft['program']['steps'][source_index]['id']
        if case.startswith('preload'):
            mode='release' if case.endswith('release') else 'hold'
            assert all(row['mode']==mode for row in new['curves'])
        compile_program(current['program'],model['conditions'])
        assert not p.buttons['run'].isEnabled() and not p.buttons['export'].isEnabled()
        QtTest.QTest.mouseClick(p.buttons['apply'],C.Qt.LeftButton);app.processEvents()
        assert len(calls)==1 and p.buttons['run'].isEnabled() and p.buttons['export'].isEnabled()
        assert info['record']['draft']==draft  # Owner record not edited in place.
        p.grab().save(str(tmp_path/(case+'-'+str(size[0])+'.png')))
    finally:
        p.close();p.deleteLater();app.processEvents()
