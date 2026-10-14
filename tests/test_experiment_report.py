"""Exact frozen report assets on the existing owner, no report-triggered jobs."""
from copy import deepcopy
import pytest
from caelab.report_document import default_draft,check_selection
from caelab.storage import canonical_hash
from caelab.workbench import Workbench
from test_experiment_calibration import imported,command


def row(binding):
    return {'id':'Eforce','title':'힘 시험','text':'공개 합성 자료','include':True,'table':True,'curve':True,'asset':binding}


def test_frozen_original_rows_undo_cold_open_missing_source_and_no_new_job(tmp_path):
    root=tmp_path/'store';wb=Workbench(root)
    try:
        data,job,_,_=imported(wb)
        exact=wb.document_result_reference(data['id'],job)
        report=wb.document_open(kind='report')
        reference={'kind':'result',**exact,'selection':{'responses':['force'],'source_rows':[2,4]}}
        binding=wb.report_capture(report['id'],reference)
        draft=default_draft();draft['sections']=[row(binding)]
        report=command(wb,report,'report.update',{'draft':draft})['document']
        report=command(wb,report,'document.save')['document']
        asset=wb.report_content(report['id'],[binding])['assets'][0]
        force=asset['content']['result']['responses']['force']
        assert force['value']==[2.5] and force['raw_samples']['transformed_value']==[2.5,8.5]
        assert force['raw_samples']['sensor_saturated']==[False,True]
        changed=deepcopy(draft);changed['sections'][0]['text']='판단은 미승인'
        report=command(wb,report,'report.update',{'draft':changed})['document']
        report=command(wb,report,'document.undo')['document']
        assert report['draft']==draft
        report=command(wb,report,'document.save')['document']
        assert report['runs']==[]
    finally:wb.shutdown()
    fresh=Workbench(root)
    try:
        restored=fresh.document_open(kind='report',document_id=report['id'])
        assert restored['draft']==draft
        owner=fresh.report_documents
        owner.resolve_reference=lambda r: (_ for _ in ()).throw(FileNotFoundError('original is unavailable'))
        unavailable=owner.content(report['id'],[binding])['assets'][0]
        assert unavailable['source_status']=='UNAVAILABLE'
        assert unavailable['content']==asset['content']
        assert restored['runs']==[]
    finally:fresh.shutdown()


def test_report_exact_absent_time_rejects_instead_of_nearest():
    reference={'kind':'result','selection':{'responses':['stress'],'time_range':[.03,.03]}}
    for times,values in [([] ,[]),([.02],[3.])]:
        payload={'result':{'responses':{'stress':{'kind':'series','value':values,
            'axes':[{'name':'time','unit':'s','values':times}]}}}}
        with pytest.raises(ValueError):check_selection(reference,payload)


def test_literature_only_study_is_freezable_without_model(tmp_path):
    # Explicit knowledge read double: archive/access behavior is tested by KnowledgeStore.
    root=tmp_path/'store';wb=Workbench(root)
    source={'status':'AVAILABLE','document_id':'7ab1c3d4e5f647829abcdef01234567890','revision':1,'sha256':'c'*64,
        'title':'공개 문헌','segments':[{'text':'실험 조건을 먼저 기록한다.','locator':{'page':1}}],
        'failed_segments':[],'collection':'local'}
    wb.assistance_call=lambda operation,args:deepcopy(source)
    try:
        ref={'kind':'knowledge','document_id':'7ab1c3d4e5f647829abcdef01234567890','revision':1,'locator':{},
             'source_sha256':'c'*64,'content_sha256':canonical_hash(source)}
        from caelab.study_document import default_draft as study_draft
        study=study_draft()
        study['evidence']=[{'id':'Epaper','label':'공개 문헌','kind':'knowledge','reference':ref,'note':''}]
        doc=wb.document_open(kind='study',draft=study)
        doc=command(wb,doc,'document.save')['document']
        report=wb.document_open(kind='report')
        asset=wb.report_capture(report['id'],ref)
        content=wb.report_content(report['id'],[asset])['assets'][0]['content']
        assert content['source']['segments'][0]['text']==source['segments'][0]['text']
        source['revision']=2
        assert wb.report_content(report['id'],[asset])['assets'][0]['source_status']=='UNAVAILABLE'
        assert report['runs']==[]
    finally:wb.shutdown()


def test_snapshot_numeric_scalars_nonfinite_and_legacy_response_preserve_values():
    import json
    import numpy as np
    from caelab.report_document import compact_payload,snapshot_value
    reference={'kind':'result','response':'force'}
    payload={'kind':'result','reference':reference,'result':{'execution_status':'SUCCEEDED',
        'responses':{'force':{'kind':'series','unit':'N','value':[np.float64(2.5)],
            'source_rows':[np.int64(2)],'mask':[np.bool_(True)],
            'axes':[{'name':'time','unit':'s','values':np.array([1.])}]}}}}
    check_selection(reference,payload)
    frozen=compact_payload(payload)
    assert frozen['result']['responses']['force']['source_rows']==[2]
    assert json.loads(json.dumps(frozen,allow_nan=False))==frozen
    assert snapshot_value([np.nan,np.inf,-np.inf,None])==['nan','inf','-inf',None]


@pytest.mark.parametrize('key,status',[('candidates','SUCCEEDED'),('predictions','PREDICTED')])
def test_exact_nested_candidate_snapshot_and_absent_candidate_rejection(key,status):
    from caelab.research_workflows import _candidate_reference_view
    from caelab.report_document import compact_payload
    def row(identifier,value):
        return {'candidate_id':identifier,'values':{'E':value},'execution_status':status,
            'responses':{'stress':{'kind':'scalar','value':value,'unit':'MPa','valid':True}}}
    result={key:[row('Cfirst',1.),row('Csecond',2.)],'execution_status':'SUCCEEDED'}
    selection={'candidate_ids':['Csecond'],'responses':['stress']}
    selected=_candidate_reference_view(result,selection)
    reference={'kind':'result','selection':selection}
    payload={'kind':'result','reference':reference,'result':selected}
    check_selection(reference,payload)
    frozen=compact_payload(payload)['result']
    assert len(frozen[key])==1 and frozen[key][0]['candidate_id']=='Csecond'
    assert frozen[key][0]['responses']['stress']['value']==2.
    assert result[key][0]['responses']['stress']['value']==1.
    with pytest.raises(ValueError):
        _candidate_reference_view(result,{**selection,'candidate_ids':['Cmissing']})
    metadata=_candidate_reference_view(result,{'candidate_ids':['Csecond'],'metadata_only':True})
    assert metadata[key][0]['values']=={'E':2.} and metadata[key][0]['responses']=={}
