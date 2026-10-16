"""Actual Qt widgets with explicit editor/transport doubles, not native execution."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from examples.composite.generate_laminate import model


@pytest.fixture
def panel_case():
    from PySide6 import QtWidgets as W,QtCore as C
    from apps.desktop_pre.composite_panel import make_panel
    app=W.QApplication.instance() or W.QApplication([]);draft=model()['draft']
    materials=[{'id':key,**record} for key,record in draft['materials'].items()]
    inspection={'draft':deepcopy(draft),'materials':materials,'can_freeze':True}
    editor=SimpleNamespace(inspect=lambda *_:{'analyses':[{'id':draft['analysis_id'],'label':'적층 평판'}],
        'meshes':[{'id':draft['mesh_id'],'label':'판재 메시'}],'solvers':[{'id':draft['solver_id'],'label':'CalculiX'}],'materials':materials})
    pending=[]
    def submit(operation,args,on_done=None):pending.append((operation,deepcopy(args),on_done));return {'command_id':'Cfixture'}
    panel=make_panel(W,C,editor,submit,**{key:lambda:None for key in ('on_save','on_freeze','on_run','on_simulation','on_post','on_results')})
    panel.inspect_result(inspection);panel.show();app.processEvents()
    try:yield panel,pending,inspection,W
    finally:panel.close();panel.deleteLater();app.processEvents()


def test_reorder_undo_and_incomplete_raw_late_edit_are_preserved(panel_case):
    panel,pending,inspection,W=panel_case;before=panel.current_draft();panel.composite_table.selectRow(0)
    def click(text):next(b for b in panel.findChildren(W.QPushButton) if b.text()==text).click()
    click('아래로');assert panel.current_draft()['regions'][0]['plies'][0]['id']==before['regions'][0]['plies'][1]['id']
    click('되돌리기');assert panel.current_draft()==before
    panel.composite_table.item(0,2).setText('1e');panel.save_then()
    operation,args,callback=pending.pop();assert operation=='pre.composite.draft' and args['draft']['regions'][0]['plies'][0]['thickness_mm']=='1e'
    panel.composite_table.item(0,2).setText('.8');callback({**inspection,'draft':args['draft']})
    assert panel.pending_changes() and panel.current_draft()['regions'][0]['plies'][0]['thickness_mm']=='.8'


def test_other_analysis_selection_and_reload_do_not_discard_dirty_edit_without_consent(panel_case,monkeypatch):
    panel,pending,inspection,W=panel_case;panel.composite_table.item(0,2).setText('1e')
    before=panel.current_draft();monkeypatch.setattr(W.QMessageBox,'question',lambda *_:W.QMessageBox.No)
    next(b for b in panel.findChildren(W.QPushButton) if b.text()=='저장본 읽기').click()
    assert panel.current_draft()==before and panel.pending_changes() and pending==[]
