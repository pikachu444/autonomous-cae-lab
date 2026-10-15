"""Coordinator failure semantics. Scripted registry/native receipts, no process."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from caelab.storage import canonical_hash
from apps.research.post_curve_origin import NativeReturn, live_owner, _command, launch_saved_measurement
from apps.research import desktop
from test_post_numerical import fixture_snapshot


class Client:
    def __init__(self, target):
        self.target=deepcopy(target); self.origin=target['saved_origin']; self.commands={}; self.submits=[];self.polls=[]
        self.lost=set(); self.malformed=False; self.mutate_after=None
        self.document={'id':'Dpost','session_id':'Scurrent','service_session_id':'Sservice','connected':True,'kind':'post',
            'generation':3,'view_generation':4,'dispatcher_status':'IDLE','state':{'pid':4444,'fresh':True},
            'capabilities':['post.curve_origin_verify','post.curve_origin_select','document.activate']}
    def documents(self):return {'documents':[deepcopy(self.document)]}
    def document_read(self,id):return deepcopy(self.document)
    def document_command(self,id,operation,arguments,**kwargs):
        request={'document_id':id,'operation':operation,'arguments':deepcopy(arguments),**kwargs}
        self.submits.append(deepcopy(request));origin=self.origin
        verified={'status':'SOURCE_VERIFIED','target_sha256':canonical_hash(self.target),
            'origin_sha256':canonical_hash(origin),'object_ref':origin['object_ref'],'revision':origin['revision'],
            'result_sha256':origin['result_sha256'],'native_pid':4444,'generation':3,'view_generation':4,
            'row':{'block':[0],'row':1,'values':{'Time':.02,'U':[.2294,2.294,0]}},
            'selection':{'block':[0],'value_array':'U','value_component':0,
                         'axis':{'kind':'array','name':'Time','component':None}},
            'raw':{'identity':{'block':[0],'row':1},'raw_x':.02,'raw_y':.2294},'clock_changed':False}
        if operation=='post.curve_origin_verify':result=verified
        elif operation=='post.curve_origin_select':
            self.document.update(generation=4,view_generation=5)
            result={**verified,'status':'SOURCE_SELECTED','generation':4,'view_generation':5,
                    'selection_sha256':canonical_hash([verified['row']])}
        elif operation=='document.activate':result={'status':'ACTIVATED','native_pid':4444,'foreground_confirmed':True}
        else:raise AssertionError(operation)
        if self.malformed:result['target_sha256']='0'*64
        command={**request,'state':'SUCCEEDED','outcome':{'state':'SUCCEEDED','result':{
            'command_id':kwargs['command_id'],'document_id':id,'session_id':kwargs['session_id'],
            'status':'COMPLETED','result':result}}}
        self.commands[kwargs['command_id']]=command
        if self.mutate_after:self.mutate_after()
        if operation in self.lost:
            self.lost.remove(operation);raise OSError('SCRIPTED lost reply AFTER execute')
        return deepcopy(command)
    def command_status(self,id):self.polls.append(id);return deepcopy(self.commands[id])


@pytest.fixture
def flow(tmp_path,monkeypatch):
    snapshot,_=fixture_snapshot(tmp_path);target={'kind':'native_curve','saved_origin':snapshot['origin'],'fixture':'raw original'}
    client=Client(target)
    monkeypatch.setattr(desktop,'_confirm_post_launch',lambda *args:None)
    calls=[]
    monkeypatch.setattr(desktop,'_spawn',lambda *args:calls.append(args) or {'pid':111,'status':'LAUNCH_REQUESTED'})
    return SimpleNamespace(client=client,target=target,operation=NativeReturn(client,target),calls=calls)


def test_verification_selection_activation_are_separate(flow):
    f=flow;before=deepcopy(f.client.document)
    assert f.operation.verify()['status']=='SOURCE_VERIFIED'
    assert f.client.document==before and not f.calls
    assert len(f.client.submits)==1
    assert f.operation.select()['status']=='SOURCE_SELECTED'
    assert f.operation.activate()['status']=='ACTIVATED'
    assert [x['operation'] for x in f.client.submits]==['post.curve_origin_verify','post.curve_origin_select','document.activate']


@pytest.mark.parametrize('phase',['verify','select','activate'])
def test_lost_response_checks_same_id_once_without_reexecution(flow,phase):
    f=flow
    if phase!='verify':f.operation.verify()
    if phase=='activate':f.operation.select()
    operation='document.activate' if phase=='activate' else 'post.curve_origin_'+phase
    f.client.lost.add(operation)
    with pytest.raises(OSError):getattr(f.operation,phase)()
    count=len(f.client.submits);id=f.client.submits[-1]['command_id']
    result=getattr(f.operation,phase)()
    assert result['status'] in ('SOURCE_VERIFIED','SOURCE_SELECTED','ACTIVATED')
    assert len(f.client.submits)==count and f.client.polls[-1]==id and not f.calls


@pytest.mark.parametrize('change',['session','service','revision','view','pid','disconnect','invalidated'])
def test_late_gui_basis_or_owner_change_never_dispatches_selection(flow,change):
    f=flow;f.operation.verify();count=len(f.client.submits)
    if change=='session':f.client.document['session_id']='Sother'
    elif change=='service':f.client.document['service_session_id']='Srestarted'
    elif change=='revision':f.client.document['generation']+=1
    elif change=='view':f.client.document['view_generation']+=1
    elif change=='pid':f.client.document['state']['pid']=5555
    elif change=='disconnect':f.client.document['connected']=False
    else:f.operation.invalidate()
    with pytest.raises(ValueError):f.operation.select()
    assert len(f.client.submits)==count and not f.calls


def test_malformed_verified_result_never_authorizes_select(flow):
    f=flow;f.client.malformed=True
    with pytest.raises(ValueError):f.operation.verify()
    with pytest.raises(ValueError):f.operation.select()
    assert len(f.client.submits)==1


def test_changed_owner_during_read_rejects_completed_receipt(flow):
    f=flow;f.client.mutate_after=lambda:f.client.document.update(session_id='Snew')
    with pytest.raises(ValueError):f.operation.verify()
    with pytest.raises(ValueError):f.operation.select()
    assert len(f.client.submits)==1


@pytest.mark.parametrize('state',['QUEUED','RUNNING','INTERRUPTED','CANCELLED','FAILED','REJECTED'])
def test_unconfirmed_and_terminal_failures_do_not_replay(flow,state):
    f=flow;native=f.client.document;track={}
    f.client.lost.add('post.curve_origin_verify')
    with pytest.raises(OSError):_command(f.client,native,'post.curve_origin_verify',{},track,timeout=0)
    id=track['request']['command_id'];f.client.commands[id]['state']=state
    with pytest.raises(RuntimeError):_command(f.client,native,'post.curve_origin_verify',{},track,timeout=0)
    assert len(f.client.submits)==1 and f.client.polls==[id]
    del f.client.commands[id]
    with pytest.raises(KeyError):_command(f.client,native,'post.curve_origin_verify',{},track,timeout=0)
    assert len(f.client.submits)==1


@pytest.mark.parametrize('issue',['busy','multiple','pid_unknown','no_freshness'])
def test_uncertain_owner_is_not_auto_launched(flow,monkeypatch,issue):
    f=flow
    if issue=='busy':f.client.document['dispatcher_status']='APPLYING_UNCONFIRMED'
    elif issue=='multiple':monkeypatch.setattr(f.client,'documents',lambda:{'documents':[f.client.document,f.client.document]})
    elif issue=='pid_unknown':f.client.document['state']['pid']=None
    else:f.client.document['state']['fresh']=False
    with pytest.raises(ValueError):f.operation.verify()
    assert not f.client.submits and not f.calls


def test_cancel_and_wrong_saved_file_are_no_ops(flow,tmp_path):
    f=flow
    assert f.operation.launch(None)=={'status':'CANCELLED','executed':False}
    other=tmp_path/'clone.json';other.write_bytes(Path(f.target['saved_origin']['project']['path']).read_bytes())
    with pytest.raises(ValueError):f.operation.launch(other)
    assert not f.calls


def test_closed_owner_launch_once_then_only_poll_with_new_session(flow,monkeypatch):
    f=flow;f.client.document['connected']=False
    monkeypatch.setattr(desktop,'_native_pid_alive',lambda pid:False)
    assert f.operation.verify()['status']=='CLOSED'
    f.operation.launch(f.target['saved_origin']['project']['path'])
    assert len(f.calls)==1 and not f.client.submits
    with pytest.raises(ValueError):f.operation.launch(f.target['saved_origin']['project']['path'])
    assert f.operation.poll_launch()['status']=='LAUNCH_UNCONFIRMED'
    f.client.document.update(connected=True,session_id='Snewly_registered')
    assert f.operation.poll_launch()['status']=='OWNER_AVAILABLE'
    assert not f.client.submits
    assert f.operation.verify()['status']=='SOURCE_VERIFIED'
    assert f.client.submits[-1]['session_id']=='Snewly_registered'


def test_pid_closure_unknown_disallows_spawn(flow,monkeypatch):
    f=flow;f.client.document['connected']=False
    monkeypatch.setattr(desktop,'_native_pid_alive',lambda pid:None)
    with pytest.raises(ValueError):f.operation.verify()
    with pytest.raises(ValueError):f.operation.launch(f.target['saved_origin']['project']['path'])
    assert not f.calls


def test_plain_data_never_cast_to_full_origin(flow):
    with pytest.raises(ValueError):NativeReturn(flow.client,{'kind':'data_curve','origin':flow.target['saved_origin']})
