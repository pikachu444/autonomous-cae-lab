"""Read-only GUI adapter: exact original execution, including portable facet."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from caelab.storage import canonical_hash
from caelab.experiment_analysis_actions import read_analysis_source


@pytest.mark.parametrize('portable',[False,True])
def test_selected_source_passes_original_arguments_without_plan_or_evaluation(monkeypatch,portable):
    import caelab.experiment_final_diagnosis as diagnosis
    import caelab.portable_project_execution as execution
    result={'kind':'fit'};draft={'mode':'fit'};arguments={'original':'exact submitted values'}
    original={'id':'Noriginal','kind':'numerical','runs':[{'job_id':'Jselected','operation':'fit',
        'draft':draft,'input_revision':'Roriginal','input_sha256':canonical_hash(draft),'arguments':arguments}]}
    exact={'document_id':original['id'],'job_id':'Jselected','input_revision':'Roriginal',
        'input_sha256':canonical_hash(draft),'result_sha256':canonical_hash(result)}
    current=deepcopy(original);current.update(session_id='Ssession',generation=4)
    reference={'source':deepcopy(exact)}
    resolved={'snapshot':{'source':deepcopy(exact),'fit_input':{'inputs':{'frozen_inclusion':{'exact':'retained packet'}}}}}
    original_reader=SimpleNamespace(read=lambda identifier:deepcopy(original),result=lambda *args:deepcopy(result))
    if portable:
        current['id']='Nportable';current['runs'][0]['arguments']={'projected':'editable owner references'}
        current_ref={**exact,'document_id':current['id'],'input_revision':'Rportable','input_sha256':'a'*64}
        reference['source']=current_ref
        bridge=SimpleNamespace(reader=original_reader,source=current_ref,execution_source=exact)
    else:bridge=None
    reference['document_id']=current['id']
    monkeypatch.setattr(execution,'execution_read',lambda owner,identifier,job:bridge)
    accepted=[]
    def consume(evidence,*,submitted_arguments):
        assert evidence==resolved
        accepted.append(deepcopy(submitted_arguments))
        return {'selection':'original'}
    monkeypatch.setattr(diagnosis,'problem_from_evidence',consume)
    monkeypatch.setattr(diagnosis,'_admission',lambda problem:'Read-only preview')
    class Client:
        def __init__(self):self.commands=[]
        def document_read(self,identifier):
            assert identifier==current['id'];return deepcopy(current)
        def document_result(self,identifier,job):
            assert (identifier,job)==(current['id'],'Jselected');return deepcopy(result)
        def document_command(self,identifier,operation,payload,**kwargs):
            assert operation=='numerical.evidence.read'
            self.commands.append(operation);return {'evidence':deepcopy(resolved)}
    client=Client();view=read_analysis_source(client,evidence_reference=reference)
    assert accepted==[arguments] and client.commands==['numerical.evidence.read']
    assert view['source_reference']==reference['source'] and view['performed_model_calls']==0
    if portable:
        bridge.source={**bridge.source,'input_sha256':'b'*64}
        with pytest.raises(ValueError,match='원 실행'):
            read_analysis_source(client,evidence_reference=reference)
        assert accepted==[arguments]


def test_missing_exact_run_never_uses_the_latest_run(monkeypatch):
    import caelab.portable_project_execution as execution
    monkeypatch.setattr(execution,'execution_read',lambda *_:None)
    class Client:
        def document_read(self,identifier):
            return {'id':identifier,'kind':'numerical','session_id':'Ssession','generation':1,
                'runs':[{'job_id':'Jlatest','operation':'fit'}]}
        def document_command(self,*args,**kwargs):
            return {'evidence':{'snapshot':{'source':{},'fit_input':{'inputs':{'frozen_inclusion':{}}}}}}
        def document_result(self,*args):pytest.fail('Missing original selected another result')
    with pytest.raises(ValueError,match='original fit'):
        read_analysis_source(Client(),evidence_reference={'document_id':'Noriginal','source':{'job_id':'Jmissing'}})


def test_inline_legacy_read_does_not_require_a_canonical_execution_projection(monkeypatch):
    import caelab.experiment_final_diagnosis as diagnosis
    import caelab.portable_project_execution as execution
    monkeypatch.setattr(execution,'execution_read',lambda *_:pytest.fail('Legacy read requested a canonical execution facet'))
    monkeypatch.setattr(diagnosis,'problem_from_evidence',lambda evidence:{'selection':'legacy'})
    monkeypatch.setattr(diagnosis,'_admission',lambda problem:'Read-only preview')
    class Client:
        def document_read(self,identifier):return {'id':identifier,'session_id':'Ssession','generation':1}
        def document_command(self,*args,**kwargs):return {'evidence':{'snapshot':{'fit_input':{'inputs':{}}}}}
    source={'document_id':'Noriginal','job_id':'Jselected','input_revision':'Roriginal',
        'input_sha256':'a'*64,'result_sha256':'b'*64}
    view=read_analysis_source(Client(),evidence_reference={'document_id':'Noriginal','source':source})
    assert view['problem']=={'selection':'legacy'} and view['performed_model_calls']==0
