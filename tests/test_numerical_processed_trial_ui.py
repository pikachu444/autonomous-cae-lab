"""GUI transport/draft contracts only; processing and adoption stay in Core."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy

import pytest
import sys
import time
from types import SimpleNamespace
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
    seen=[]
    class Dialog:
        def __init__(self,*args,**kwargs):
            seen.append(deepcopy(kwargs))
            self.value={'name':'P_grid','role':'fit','response':'stress_xx','weight':1.,'scale':1.,
                'settings':deepcopy(view._material['draft']['settings']),
                'kinematics':{'channel':'e_grid','kind':'engineering_strain','lateral_22':1.,'lateral_33':1.}}
        def exec(self):
            if edit: edit()
            return QDialog.DialogCode.Accepted
    monkeypatch.setattr(material_test_dialog,'ExperimentDialog',Dialog)
    return seen


def test_staging_preserves_unfinished_cells_and_owner_without_commands(window,monkeypatch):
    seen=accepted_dialog(monkeypatch,window)
    window.variables.item(0,3).setText('1e')
    before=deepcopy(window.document)
    src=dict(source(),response='P_grid');payload=result(src);original=deepcopy((src,payload))
    assert window.stage_processed_trial(src,payload)
    assert window.document==before and (src,payload)==original
    assert seen==[{'selected':'P_grid'}]
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


def policy_client(window,monkeypatch,*,lost=False,experiment_weight=1.):
    accepted_dialog(monkeypatch,window)
    assert window.stage_processed_trial(source(),result(source()))
    doc=deepcopy(window.document);doc['draft']=window.edited_draft()
    doc['draft']['experiments'][0]['weight']=experiment_weight
    window.local_dirty=False;window._show_document(doc);window.experiments.selectRow(0)
    initials=[]
    class Dialog:
        entries={'sample1':{'included':True,'role':'holdout','weight':2.}}
        def __init__(self,*args,**kwargs):initials.append(deepcopy(kwargs.get('initial_entries')))
        def exec(self):return QDialog.DialogCode.Accepted
    monkeypatch.setitem(sys.modules,'apps.research.data_sample_policy_dialog',SimpleNamespace(SamplePolicyDialog=Dialog))
    class Client:
        calls=[]
        dialog_initials=initials
        def document_read(self,identifier):
            return {'kind':'data','runs':[dict(job_id='Jimport',input_revision='Iimport',input_sha256='a'*64)]}
        def data_material(self,operation,arguments):
            self.calls.append((operation,deepcopy(arguments)))
            if operation=='data.processing.result':
                return dict(result(source()),channels={'P_grid':{'name':'P_grid'}})
            if operation=='data.sample_policy.preview':return {'domain':{'sample_count':1},'entries':{}}
            assert operation=='data.sample_policy.adopt'
            if lost and sum(op==operation for op,_ in self.calls)==1:
                raise ConnectionError('lost original reply after server commit')
            applied=deepcopy(doc);applied['generation']+=1;applied['dirty']=True
            applied['draft']['experiments'][0]['selection']={'sample_policy':{'adoption':{'command_id':arguments['command_id']}}}
            return {'command_id':arguments['command_id'],'document':applied,'saved':False}
    window.client=Client()
    return window.client


def settle(window):
    app=QApplication.instance();until=time.monotonic()+4
    while time.monotonic()<until:
        app.processEvents();time.sleep(.005)
        if not window._busy and not window._callbacks:
            return
    raise AssertionError('Policy callback did not settle')


def test_explicit_policy_uses_one_adoption_and_does_not_save_or_fit(window,monkeypatch):
    client=policy_client(window,monkeypatch)
    assert window.edit_sample_policy()
    settle(window)
    calls=[(op,args) for op,args in client.calls if op=='data.sample_policy.adopt']
    assert len(calls)==1 and calls[0][1]['expected_generation']==0
    assert calls[0][1]['entries']['sample1']['role']=='holdout'
    assert window._adoption_receipt is None
    assert window.document['generation']==1 and window.document['dirty']
    assert not window.local_dirty and window.edited_draft()==window.document['draft']


def test_new_policy_uses_unit_sample_weight_and_keeps_trial_weight_separate(window,monkeypatch):
    client=policy_client(window,monkeypatch,experiment_weight=2.)
    assert window.edit_sample_policy()
    settle(window)
    previews=[args for operation,args in client.calls if operation=='data.sample_policy.preview']
    assert len(previews)==1 and previews[0]['weight']==1.0
    assert window.document['draft']['experiments'][0]['weight']==2.
    assert window.edited_draft()['experiments'][0]['weight']==2.


def test_lost_policy_ack_reuses_command_and_preserves_later_local_edit(window,monkeypatch):
    client=policy_client(window,monkeypatch,lost=True)
    assert window.edit_sample_policy()
    settle(window)
    assert window._adoption_receipt is not None
    assert not window.run_button.isEnabled()
    window.variables.item(0,3).setText('1e')
    assert window.retry_adoption_receipt()
    settle(window)
    calls=[args for op,args in client.calls if op=='data.sample_policy.adopt']
    assert len(calls)==2 and calls[0]==calls[1]
    assert window._adoption_receipt is None and window.conflict
    assert window.edited_draft()['variables'][0]['lower']=='1e'
    assert window.document['generation']==0


def test_reopening_policy_seeds_existing_roles_and_weights_without_rewriting_proposal(window,monkeypatch):
    client=policy_client(window,monkeypatch)
    policy={'domain':{'sample_count':1},'default':{'included':True,'role':'fit','weight':1.},
        'overrides':{'sample1':{'included':False,'role':'holdout','weight':2.}},'adoption':{'command_id':'Cprevious'}}
    doc=deepcopy(window.document)
    doc['draft']['experiments'][0]['selection']={'sample_policy':deepcopy(policy)}
    window._show_document(doc);window.experiments.selectRow(0)
    validated=[]
    monkeypatch.setitem(sys.modules,'caelab.data_processing_selection',SimpleNamespace(
        validate_sample_policy=lambda value:validated.append(deepcopy(value))))
    # Transport double's proposal exposes the same exact frozen sample ID set.
    original=client.data_material
    def response(operation,arguments):
        payload=original(operation,arguments)
        if operation=='data.sample_policy.preview':payload['entries']={'sample1':{'included':True,'role':'fit','weight':1.}}
        return payload
    client.data_material=response
    assert window.edit_sample_policy()
    settle(window)
    assert validated==[policy]
    assert client.dialog_initials==[policy['overrides']]
    adopt=next(args for op,args in client.calls if op=='data.sample_policy.adopt')
    assert adopt['proposal']['entries']['sample1']=={'included':True,'role':'fit','weight':1.}


def test_policy_receipt_cannot_be_retried_from_another_plan_with_same_session(window,monkeypatch):
    client=policy_client(window,monkeypatch,lost=True)
    assert window.edit_sample_policy()
    settle(window)
    assert window._adoption_receipt is not None
    window.document['id']='Nanother'
    before=deepcopy(client.calls)
    assert not window.retry_adoption_receipt()
    assert client.calls==before
    assert window._adoption_receipt is not None
