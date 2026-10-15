"""GUI transport/draft contracts only; processing and adoption stay in Core."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy

import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication, QDialog
from apps.research.numerical_window import NumericalWindow
from caelab.material_document import default_draft
from caelab.numerical_document import from_material_document


@pytest.fixture
def window():
    app=QApplication.instance() or QApplication([])
    model={'id':'Mmodel','input_revision':'Imodel','generation':0,'draft':default_draft()}
    document={'id':'Nplan','session_id':'Sowner','generation':0,'title':'인장 시험 계획',
        'draft':from_material_document(model),'runs':[],'diagnostics':[],'dirty':False}
    view=NumericalWindow(None,auto_open=False,poll_interval=0)
    view._show_document(document)
    yield view
    view._allow_close=True
    view.close()
    app.processEvents()


def source():
    return {'document_id':'Tdata','job_id':'Jimport','input_revision':'Iimport',
            'input_sha256':'a'*64,'processing_revision':'Pone'}


def result(src):
    return {'execution_status':'SUCCEEDED','responses':{'P_grid':{'component':'xx','unit':'MPa'}},
        'diagnostics':{'processing_revision':src['processing_revision'],
            'processing_record':{'source':{k:v for k,v in src.items() if k!='processing_revision'}}}}


def accepted_dialog(monkeypatch,view,*,edit=None):
    from apps.research import material_test_dialog
    class Dialog:
        def __init__(self,*args,**kwargs):
            self.value={'name':'P_grid','role':'fit','response':'stress_xx','weight':1.,'scale':1.,
                'settings':deepcopy(view._material['draft']['settings']),
                'kinematics':{'channel':'e_grid','kind':'engineering_strain','lateral_22':1.,'lateral_33':1.}}
        def exec(self):
            if edit: edit()
            return QDialog.DialogCode.Accepted
    monkeypatch.setattr(material_test_dialog,'ExperimentDialog',Dialog)


def test_staging_preserves_unfinished_cells_and_owner_without_commands(window,monkeypatch):
    accepted_dialog(monkeypatch,window)
    window.variables.item(0,3).setText('1e')
    before=deepcopy(window.document)
    src=source();payload=result(src);original=deepcopy((src,payload))
    assert window.stage_processed_trial(src,payload)
    assert window.document==before and (src,payload)==original
    draft=window.edited_draft()
    assert draft['variables'][0]['lower']=='1e'
    assert draft['experiments'][0]['source']==dict(src,response='P_grid')
    assert draft['experiments'][0]['kinematics']['channel']=='e_grid'
    assert window.local_dirty


def test_staging_rejects_peer_change_and_wrong_processed_source(window,monkeypatch):
    src=source();payload=result(src)
    wrong=deepcopy(payload);wrong['diagnostics']['processing_record']['source']['job_id']='Jother'
    assert not window.stage_processed_trial(src,wrong)
    accepted_dialog(monkeypatch,window,edit=lambda:window.document.update(generation=1))
    assert not window.stage_processed_trial(src,payload)
    assert not window._experiments


def test_processed_read_is_exact_revision_and_explicit_channel_subset(window):
    src=source();trial={'source':dict(src,response='P_grid'),'kinematics':{'channel':'e_grid'}}
    class Client:
        calls=[]
        def document_read(self,identifier):
            assert identifier=='Tdata'
            return {'kind':'data','title':'인장 처리본','runs':[dict(job_id='Jimport',input_revision='Iimport',input_sha256='a'*64)]}
        def data_material(self,operation,arguments):
            self.calls.append((operation,arguments))
            return result(src)
        def document_result(self,*args):
            raise AssertionError('Processed result must not fall back to raw import')
    window.client=Client()
    payload=window._read_trial_source(trial)
    assert payload['title']=='인장 처리본'
    assert window.client.calls==[('data.processing.result',{
        'document_id':'Tdata','processing_revision':'Pone','selection':['P_grid','e_grid']})]
    other=deepcopy(trial);other['source']['processing_revision']='Ptwo'
    assert window._trial_source_key(other)!=window._trial_source_key(trial)
    other=deepcopy(trial);other['kinematics']['channel']='other_driver'
    assert window._trial_source_key(other)!=window._trial_source_key(trial)


def test_adopted_policy_remains_editable_and_is_not_dropped(window,monkeypatch):
    accepted_dialog(monkeypatch,window)
    assert window.stage_processed_trial(source(),result(source()))
    document=deepcopy(window.document)
    document['draft']=window.edited_draft()
    policy={'format':'caelab.observation-sample-policy/1','overrides':{'sample1':{'included':False}},'domain':{'sample_count':2}}
    document['draft']['experiments'][0]['selection']={'sample_policy':deepcopy(policy)}
    window._show_document(document)
    assert window._view_error is None
    window.experiments.item(0,5).setText('2.5')
    assert window.edited_draft()['experiments'][0]['selection']=={'sample_policy':policy}
    assert '구간 적용' in window.experiments.item(0,7).text()
