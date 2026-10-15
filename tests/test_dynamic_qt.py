"""Optional actual Qt widget checks. Skipped without Qt, never native FreeCAD proof."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
QtWidgets=pytest.importorskip('PySide6.QtWidgets',reason='Native Qt not installed; Windows GUI acceptance remains required')
from PySide6 import QtCore
from copy import deepcopy
from types import SimpleNamespace as NS
from apps.desktop_pre.dynamic_panel import make_panel
from test_dynamic_support import dynamic_model


@pytest.mark.parametrize('size',[(470,740),(1100,840)])
def test_two_sizes_invalid_draft_and_explicit_cancel(size,tmp_path):
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    d=dynamic_model()['dynamic']['draft'];info={'record':{'draft':d},'errors':[],'can_freeze':True,
         'bodies':[{'id':'Solid','mesh_id':'Mesh','native_node_ids':[51]}]}
    cat={'analyses':[{'id':'Analysis','label':'한글 해석','solvers':[{'id':'Solver','label':'CalculiX'}]}],'models':{'Analysis':info['record']}}
    e=NS(inspect=lambda key=None:deepcopy(cat if key is None else info));calls=[]
    def submit(op,args,target=None,on_done=None):
        calls.append((op,deepcopy(args)));saved=deepcopy(info);saved['record']['draft']=deepcopy(args['draft'])
        saved['can_freeze']=False;saved['errors']=[{'path':'rayleigh.alpha_per_s','message':'입력이 끝나지 않았습니다.'}]
        if on_done:on_done(saved)
    p=make_panel(QtWidgets,QtCore,e,submit,Gui=NS(),on_run=lambda *a:pytest.fail('implicit run'),
        on_results=lambda:None,on_runner=lambda:None,on_save=lambda:None)
    p.resize(*size);p.show();app.processEvents()
    p.fields['alpha_per_s'].setText('1e');p.changed()
    assert not p.buttons['run'].isEnabled() and not p.buttons['export'].isEnabled()
    p.buttons['draft'].click();app.processEvents()
    assert calls[-1][0]=='pre.dynamic.draft' and p.buffer.value['rayleigh']['alpha_per_s']=='1e'
    assert not p.buttons['run'].isEnabled()
    p.grab().save(str(tmp_path/('dynamic-'+str(size[0])+'.png')))
    p.close();p.deleteLater();app.processEvents()
