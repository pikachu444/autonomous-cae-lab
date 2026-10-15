"""Exact client-command retry: actual DesktopLinks/owner receipts, no Qt double."""
from copy import deepcopy
import pytest
from caelab.experiment_analysis_actions import ExplicitAnalysisAction,read_analysis_source
from caelab.experiment_analysis_service import final_request,uncertainty_request
from caelab.storage import canonical_hash
from .support import ServiceHost
from .test_file_workflow import import_source
from .test_uncertainty import spec
from .test_service import algebra_registered
from .test_final_diagnosis import direct_problem


class Client:
    def __init__(self,h):self.h=h;self.fail=None;self.requests=[]
    def document_read(self,*a,**k):return self.h.core.document_read(*a,**k)
    def document_result(self,*a,**k):return self.h.core.document_result(*a,**k)
    def document_result_reference(self,*a,**k):return self.h.core.document_result_reference(*a,**k)
    def result_followup(self,*a,**k):
        out=self.h.core.desktop.result_followup(*a,**k)
        if self.fail=='create':self.fail=None;raise OSError('lost create reply')
        return out
    def document_command(self,*a,**k):
        self.requests.append(deepcopy((a,k)))
        out=self.h.core.document_command(*a,**k)
        if self.fail==a[1]:self.fail=None;raise OSError('lost finish reply')
        return out


@pytest.mark.parametrize('lost',['create','numerical.run'])
def test_lost_create_or_run_reply_reuses_same_plan_job_and_payload(tmp_path,lost):
    with ServiceHost(tmp_path) as h:
        _,_,source=import_source(h);client=Client(h)
        count=len(h.manager.list());view=read_analysis_source(client,source=source)
        assert len(h.manager.list())==count and len(h.owner.list())==0
        request=uncertainty_request(source,spec(view['problem']))
        action=ExplicitAnalysisAction(request,'run',source_reference=view['source_reference'],session_id=view['session_id'])
        client.fail=lost
        with pytest.raises(OSError):action.perform(client)
        request['purpose']='later unsent edit'
        result=action.perform(client);h.wait(result['job']['id'])
        assert len(h.owner.list())==1 and len(h.manager.list())==count+1
        assert result['document']['draft']['request']['purpose']!='later unsent edit'
        again=action.perform(client)
        assert again['job']['id']==result['job']['id']


def test_final_source_preview_no_evaluation_and_idempotent_handoff(tmp_path,algebra_registered):
    with ServiceHost(tmp_path) as h:
        _,_,ref=h.original(direct_problem());client=Client(h)
        count=len(h.manager.list());view=read_analysis_source(client,evidence_reference=ref)
        assert view['model_evaluations']==9 and len(h.manager.list())==count
        action=ExplicitAnalysisAction(final_request(ref,evaluations=9),'run',source_reference=view['source_reference'],session_id=view['session_id'])
        receipt=action.perform(client);h.wait(receipt['job']['id'])
        assert h.owner.result(receipt['document']['id'],receipt['job']['id'])['execution_status']=='SUCCEEDED'


def test_stale_input_does_not_overwrite_new_plan_edits(tmp_path):
    with ServiceHost(tmp_path) as h:
        _,_,source=import_source(h);client=Client(h);view=read_analysis_source(client,source=source)
        request=uncertainty_request(source,spec(view['problem']))
        first=ExplicitAnalysisAction(request,'save',source_reference=view['source_reference'],session_id=view['session_id']).perform(client)
        doc=first['document'];draft=deepcopy(doc['draft']);draft['request']['purpose']='other editor'
        h.command(doc['id'],'numerical.update',{'draft':draft})
        revised=deepcopy(request);revised['purpose']='this editor'
        stale=ExplicitAnalysisAction(revised,'save',source_reference=view['source_reference'],session_id=view['session_id'],document=doc)
        with pytest.raises(ValueError,match='generation'):stale.perform(client)
        assert h.owner.read(doc['id'])['draft']['request']['purpose']=='other editor'


def test_saved_result_not_reused_as_editor_input_for_other_source_or_mask():
    from caelab.experiment_analysis_actions import source_request_identity
    request=uncertainty_request({'kind':'result_response','reference':{'job_id':'Jone'},'response':'F'}, {},plan_mask=[True])
    other=deepcopy(request);other['inputs']['source']['reference']['job_id']='Jtwo'
    assert source_request_identity(request)!=source_request_identity(other)
    other=deepcopy(request);other['inputs']['plan_mask']=[False]
    assert source_request_identity(request)!=source_request_identity(other)
    other=deepcopy(request);other['inputs']['specification']={'unfinished':'value'}
    assert source_request_identity(request)==source_request_identity(other)
