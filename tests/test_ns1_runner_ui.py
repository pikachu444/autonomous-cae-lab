"""Actual Qt monitor for a retained, synthetic NS1 failure; no solver or native CAD."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
W=pytest.importorskip('PySide6.QtWidgets')
from test_pre_fem_panel_ui import app
from apps.research.contact_run_dialog import ContactRunDialog


@pytest.mark.parametrize('width',[740,1100])
def test_retained_material_attempts_and_missing_information_are_not_execution(app,monkeypatch,width):
    from apps.research import desktop
    calls=[]
    class Runner(W.QWidget):
        def __init__(self):
            super().__init__()
            self.client=NS(job_navigation=lambda job:{'retained_design_input_id':'Dfailed',
                'post_input':{'id':'Dpartial'}}, native_input=lambda identifier:{'id':identifier,
                'kind':'frozen_contact','editable_path':'retained/failed/editable.caepre'})
        def _request(self,key,work,done,**kwargs): done(work(),None)
    monkeypatch.setattr(desktop,'_spawn',lambda client,args:calls.append(args))
    monkeypatch.setattr(desktop,'launch_post',lambda client,identifier,**kw:calls.append(('post',identifier,kw)))
    result={'execution_status':'FAILED','executed_setup':{'axis':{'unit':'1'},'materials':[
        {'body_id':'인장 시편','law':'j2_isotropic_hardening',
         'plasticity':{'stress_unit':'MPa','strain_unit':'1','yield_points':[[250,0],[270,.001],[300,.02]]}}]},
        'increment_history':{'rejected_attempt_count':2,'observed_cutbacks':[{'old_increment':.5,'new_increment':.25}],
        'rows':[{'step':1,'increment':2,'attempt':1,'iterations':16,'total':.5,'increment_size':.5,
                 'converged':False,'raw':'1 2 1U 16 .5 .5 .5','step_location':{'label':'하중 단계'}},
                {'step':1,'increment':2,'attempt':2,'iterations':16,'total':.5,'increment_size':.25,
                 'converged':False,'raw':'1 2 2U 16 .5 .5 .25','step_location':{'label':'하중 단계'}}]}}
    original=deepcopy(result); runner=Runner(); dialog=ContactRunDialog(runner,'Jfailed',result)
    dialog.resize(width,780); dialog.show(); app.processEvents()
    assert dialog.width()==width
    assert dialog.condition.currentText()=='인장 시편 / J2 경화 곡선'
    assert dialog.points.item(1,0).text()=='0.001' and dialog.points.item(1,1).text()=='270'
    assert '등가 소성변형률' in dialog.points.horizontalHeaderItem(0).text()
    assert '진응력' in dialog.points.horizontalHeaderItem(1).text()
    assert '거절 시도: 2' in dialog.summary.text() and '관측 증분 축소: 1' in dialog.summary.text()
    assert 'STA에 없음' in dialog.summary.text()
    assert '누적 단계 진행값' in dialog.attempts.horizontalHeaderItem(4).text()
    assert dialog.attempts.item(1,5).text()=='0.25'
    assert calls==[] and result==original
    target=os.environ.get('NS1_RENDER_DIR')
    if target:
        folder=Path(target); folder.mkdir(parents=True,exist_ok=True)
        assert dialog.grab().save(str(folder/f'ns1-runner-{width}.png'))
    dialog.open_saved(); dialog.open_post()
    assert calls==[['pre','--source','retained/failed/editable.caepre','--source-label','계산 조건 수정'],
                   ('post','Dpartial',{'job_id':'Jfailed'})]
    assert result==original
    dialog.close(); runner.close(); app.processEvents()
