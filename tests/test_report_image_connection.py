"""SCRIPTED client transport tests. No actual provider/native process is used."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from apps.research.report_image_connection import CaptureSession,candidates
from caelab.report_document import ReportDocuments
from report_image_fixture import fixture


def setup(tmp_path):
    f=fixture(tmp_path/'post')
    store=ReportDocuments(tmp_path/'store','Sservice',lambda *a:pytest.fail('no jobs'),None,
                          resolve_reference=lambda *a:pytest.fail('no reference execution'))
    report=store.open()
    document={'id':'Dpost','session_id':'Snative','kind':'post','title':'결과',
              'generation':4,'connected':True,'state':{'analysis':{'objects':[f['object']]}}}
    class Client:
        count=0;status_count=0;capture_count=0;raise_after_send=False;on_content=None
        def document_read(self,identifier):return deepcopy(document)
        def document_command(self,identifier,operation,arguments,**kwargs):
            self.count+=1
            self.command=deepcopy(f['command']);self.command.update(command_id=kwargs['command_id'],state='QUEUED',arguments=arguments)
            self.command['outcome']['result']['command_id']=kwargs['command_id']
            if self.raise_after_send:raise ConnectionError('response lost after dispatch')
            return deepcopy(self.command)
        def command_status(self,identifier):
            self.status_count+=1;assert identifier==self.command['command_id'];return deepcopy(self.command)
        def report_capture(self,identifier,ref):
            self.capture_count+=1
            assert ref=={'kind':'post_image_command','command_id':self.command['command_id']}
            return store.capture_image(identifier,self.command)
        def report_content(self,identifier,bindings):
            result=store.content(identifier,bindings)
            if self.on_content:self.on_content()
            return result
    client=Client();candidate=candidates([document])[0]
    return SimpleNamespace(f=f,store=store,report=report,document=document,client=client,candidate=candidate)


def test_lost_dispatch_response_only_reads_same_request_no_replay(tmp_path):
    x=setup(tmp_path);session=CaptureSession(x.client,x.report['id'],x.candidate)
    x.client.raise_after_send=True
    with pytest.raises(ConnectionError):session.submit()
    with pytest.raises(ValueError):session.submit()
    assert session.stage=='SUBMITTED_UNCONFIRMED' and x.client.count==1
    x.client.command['state']='SUCCEEDED';session.poll()
    binding,asset=session.retain()
    assert asset['content']['kind']=='post_image' and x.client.count==1
    assert x.store.read(x.report['id'])['draft']==x.report['draft']
    assert binding['reference']['command_id']==session.request['command_id']


@pytest.mark.parametrize('state',['FAILED','UNKNOWN','INTERRUPTED','CANCELLED','RUNNING','QUEUED'])
def test_unsuccessful_receipt_cannot_replace_report(tmp_path,state):
    x=setup(tmp_path);session=CaptureSession(x.client,x.report['id'],x.candidate)
    session.submit();x.client.command['state']=state;session.poll()
    with pytest.raises(ValueError):session.retain()
    assert x.client.capture_count==0 and x.store.read(x.report['id'])['draft']==x.report['draft']


def test_cancel_and_late_read_do_not_adopt_or_claim_physical_stop(tmp_path):
    x=setup(tmp_path);session=CaptureSession(x.client,x.report['id'],x.candidate)
    session.submit();x.client.command['state']='SUCCEEDED';session.poll()
    x.client.on_content=session.abandon
    with pytest.raises(ValueError):session.retain()
    assert session.binding is None and session.asset is None
    assert x.store.read(x.report['id'])['draft']==x.report['draft']
    with pytest.raises(ValueError):session.poll()
    assert x.client.count==1


def test_candidate_mutation_cannot_retarget_dispatched_request(tmp_path):
    x=setup(tmp_path);session=CaptureSession(x.client,x.report['id'],x.candidate)
    x.candidate['document']['id']='Dother';x.candidate['object']['id']='Fother'
    session.submit()
    assert session.request['document_id']=='Dpost' and session.request['arguments']['object_ref']=='Fresult'
    x.client.command['session_id']='Sother'
    with pytest.raises(ValueError):session.poll()


def test_owner_change_blocks_before_dispatch(tmp_path):
    x=setup(tmp_path);session=CaptureSession(x.client,x.report['id'],x.candidate)
    x.document['generation']+=1
    with pytest.raises(ValueError):session.submit()
    assert session.stage=='NEW' and x.client.count==0
