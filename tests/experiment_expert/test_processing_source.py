"""Actual current Data publish/read/retain, with the original FN05 signed trace.
No test-only second owner hook or direct producer apply bypass.
"""
from copy import deepcopy
import shutil
import pytest
from caelab.data_document import DataDocuments
from caelab.storage import canonical_hash
from caelab import data_processing_document as producer
from caelab.experiment_analysis_service import source_problem,uncertainty_request
from .support import ServiceHost
from .test_file_workflow import import_source
from .test_uncertainty import spec


# The current owner has these hooks already; no test-only second retention or
# direct apply is needed. All changes go through its existing public command.
SuppliedC1DataFixture = DataDocuments


def publish_fixture(owner, document_id):
    document = owner.read(document_id)
    preview = owner.processing_preview(document_id)
    response = owner.command(document_id, 'data.processing.apply',
        {'preview_sha256': preview['preview_sha256']},
        session_id=document['session_id'], expected_generation=document['generation'],
        command_id='Cpublicprocessing')
    return response['processing']


def test_published_processing_channel_explicit_propagation_and_cold_reopen(tmp_path):
    root=tmp_path/'wb'
    with ServiceHost(root,data_owner_type=SuppliedC1DataFixture) as h:
        data,job,source=import_source(h)
        run=next(r for r in h.data.read(data)['runs'] if r['job_id']==job)
        origin={k:run[k] for k in ('job_id','input_revision','input_sha256')};origin['document_id']=data
        draft=deepcopy(h.data.read(data)['draft'])
        draft['processing']={'source':origin,'recipe':{'version':1,'operations':[
            {'id':'grid','operation':'resample','input':'force','output':'Fgrid',
             'settings':{'method':'linear','max_gap':1.1,'range':[0.,2.],'step':.5}}]}}
        h.command(data,'data.update',{'draft':draft})
        record=publish_fixture(h.data,data);h.save(data)
        result=producer.result(h.data,data,record['id']);channel=result['channels']['Fgrid']
        selection={'kind':'processing_channel','document_id':data,'revision':record['id'],
            'channel':'Fgrid','channel_sha256':canonical_hash(channel)}
        problem=source_problem(h.core,{'source':selection})
        assert problem['processing_record']['id']==record['id']
        assert problem['sample_ids']==[s['sample_id'] for s in channel['samples']]
        assert problem['trace'][1]['terms']
        request=uncertainty_request(selection,spec(problem))
        doc,attempt,raw=h.run_plan(request);assert raw['execution_status']=='SUCCEEDED',raw
        h.save(doc);digest=canonical_hash(h.owner.result(doc,attempt));calls=len(h.manager.list())
        with pytest.raises(ValueError,match='published'):
            source_problem(h.core,{'source':{**selection,'revision':'Porphan'}})
        with pytest.raises(ValueError,match='달라졌'):
            source_problem(h.core,{'source':{**selection,'channel_sha256':'b'*64}})
        shutil.rmtree(h.data._folder(data)/'processing')
        shutil.rmtree(h.root/'results')
    with ServiceHost(root,data_owner_type=SuppliedC1DataFixture) as cold:
        # Re-read via normal saved Data revision, not the removed volatile folder.
        assert source_problem(cold.core,{'source':selection})['processing_record']['id']==record['id']
        assert canonical_hash(cold.owner.result(doc,attempt))==digest
        assert len(cold.manager.list())==calls


def test_processing_read_client_and_exact_existing_handoff_no_new_adapter_store(tmp_path):
    from .test_actions import Client
    from caelab.experiment_analysis_actions import read_analysis_source,ExplicitAnalysisAction
    class ContractClient(Client):
        def request(self,path,body):
            # Only HTTP transport is composed; actual provided Data reader runs.
            assert path=='/api/workbench/data-material' and body['operation']=='data.processing.result'
            a=body['arguments'];return producer.result(self.h.data,a['document_id'],a['processing_revision'])
    with ServiceHost(tmp_path,data_owner_type=SuppliedC1DataFixture) as h:
        data,job,_=import_source(h);d=h.data.read(data);run=d['runs'][-1]
        origin={k:run[k] for k in ('job_id','input_revision','input_sha256')};origin['document_id']=data
        draft=deepcopy(d['draft']);draft['processing']={'source':origin,'recipe':{'version':1,'operations':[]}}
        h.command(data,'data.update',{'draft':draft});record=publish_fixture(h.data,data);h.save(data)
        channel=producer.result(h.data,data,record['id'])['channels']['force']
        source={'kind':'processing_channel','document_id':data,'revision':record['id'],
            'channel':'force','channel_sha256':canonical_hash(channel)}
        client=ContractClient(h);n=len(h.manager.list());view=read_analysis_source(client,source=source)
        assert len(h.manager.list())==n
        request=uncertainty_request(source,spec(view['problem']))
        action=ExplicitAnalysisAction(request,'run',source_reference=view['source_reference'],session_id=view['session_id'])
        result=action.perform(client);h.wait(result['job']['id'])
        assert h.owner.result(result['document']['id'],result['job']['id'])['execution_status']=='SUCCEEDED'
        assert len(h.manager.list())==n+1
