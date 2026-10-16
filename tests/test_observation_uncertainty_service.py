"""One actual HTTP/JobManager/Plan/Study/Report and cold owner path; no solver."""
from copy import deepcopy
from pathlib import Path
import shutil
import threading
import time
from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from caelab.workbench_client import Client
from caelab.experiment_analysis_actions import ExplicitAnalysisAction,read_analysis_source
from caelab.experiment_analysis_service import uncertainty_request
from caelab.experiment_observation_uncertainty import template
from caelab.experiment_analysis_reporting import study_draft,blocks
from caelab.storage import canonical_hash
from tests.experiment_expert.test_uncertainty import calibration
from tests.experiment_expert.support import ServiceHost
from caelab.report_document import default_draft as report_draft


def wait(client,job):
    limit=time.monotonic()+25
    while time.monotonic()<limit:
        status=client.status(job)
        if status['state'] in ('SUCCEEDED','FAILED','CANCELLED','REJECTED'):return status
        time.sleep(.02)
    raise AssertionError('owned local analytic job timed out')


def test_http_analysis_study_report_saved_cold_without_recomputation(tmp_path):
    server=LabHTTPServer(LabService(tmp_path/'workspace'),0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client('http://127.0.0.1:'+str(server.server_port))
    wb=server.workbench
    try:
        # Existing upload/import owner operations, with a genuine retained raw table.
        raw=wb.upload('공개 힘.csv',b't,v\n0,0.001\n1,0.002\n2,0.003\n')
        cert=wb.upload('공개 교정.txt',b'Public synthetic certificate; no physical qualification')
        recipe=calibration();recipe['source']={'data_id':cert['id'],'sha256':cert['sha256'],'name':cert['name']}
        mapping={'delimiter':',','skip_header':1,'columns':{'force':{'column':1,'unit':'N','component':'x','location':'gauge_A','measure':'force','frame':'lab',
            'axis':{'column':0,'name':'time','unit':'s'},'calibration':recipe}}}
        d=wb.data_documents.open(title='공개 원 시험',draft={'data_id':raw['id'],'mapping':mapping})
        receipt=client.document_command(d['id'],'data.import',{},session_id=d['session_id'],expected_generation=d['generation'])
        assert wait(client,receipt['job']['id'])['state']=='SUCCEEDED'
        d=client.document_read(d['id']);client.document_command(d['id'],'document.save',{},session_id=d['session_id'],expected_generation=d['generation'])
        ref=client.document_result_reference(d['id'],receipt['job']['id']);base={'kind':'result_response','reference':ref,'response':'force'}
        original=canonical_hash(client.document_result(d['id'],receipt['job']['id']))
        source=template(client,base);source['operands']['A'].update(quantity='nominal_stress',channels={'force':base},max_gap_s=2.,
            parameters={'A0':{'value':2.,'unit':'mm^2','identity':'measured_area','source':'공개 합성 시험편 치수'}})
        before=len(wb.manager.list());view=read_analysis_source(client,source=source)
        p=view['problem'];specification={'uncertainties':{v['id']:{'kind':'standard','value':.01,'unit':v['unit']} for v in p['variables']},
            'dependence':{'kind':'independent_declared','note':'합성 fixture의 명시 독립성'},'axis_uncertainty':'fixed_coordinates_declared','output_coverage_factor':2.}
        request=uncertainty_request(source,specification)
        action=ExplicitAnalysisAction(request,'run',source_reference=view['source_reference'],session_id=view['session_id'])
        run=action.perform(client);plan=run['document']['id'];job=run['job']['id']
        assert wait(client,job)['state']=='SUCCEEDED'
        result=client.document_result(plan,job)
        assert result['execution_status']=='SUCCEEDED',result
        assert len(wb.manager.list())==before+1 and result['experiment_analysis']['model_calls']==0
        assert result['experiment_analysis']['source_problem']['values']==[.25,1.25,2.25]
        dplan=client.document_read(plan);client.document_command(plan,'document.save',{},session_id=dplan['session_id'],expected_generation=dplan['generation'])
        exact=client.document_result_reference(plan,job)
        study=wb.study_documents.open(draft=study_draft(result,exact,question='면적 측정의 불확실성이 응력 비교에 미치는 영향은?'))
        wb.document_command(study['id'],'document.save',{},session_id=study['session_id'],expected_generation=study['generation'])
        report=wb.report_documents.open();asset=wb.report_capture(report['id'],{'kind':'result',**exact})
        report_definition=report_draft();report_definition['title']='공개 관측 변환 결과'
        report_definition['sections']=[{'id':'observation','title':'공칭 응력과 제공 불확실성','text':'국소 1차 전파, 공학 승인 아님',
            'include':True,'table':True,'curve':True,'asset':asset}]
        wb.document_command(report['id'],'report.update',{'draft':report_definition},session_id=report['session_id'],expected_generation=report['generation'])
        report=wb.report_documents.read(report['id']);wb.document_command(report['id'],'document.save',{},session_id=report['session_id'],expected_generation=report['generation'])
        report_result=wb.report_content(report['id'],[asset])['assets'][0]['content']['result'];report_digest=canonical_hash(report_result)
        assert any(kind=='table' and '확장불확실성' in content[0] for kind,content in blocks(result))
        assert canonical_hash(client.document_result(base['reference']['document_id'],base['reference']['job_id']))==original
        digest=canonical_hash(result);root=wb.root;total=len(wb.manager.list())
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
        assert not thread.is_alive()
    # Existing saved Numerical and Study owners supply the cold read.
    shutil.rmtree(root/'results');shutil.rmtree(root/'inputs')
    with ServiceHost(root) as cold:
        assert canonical_hash(cold.owner.result(plan,job))==digest
        assert cold.study.read(study['id'])['draft']['question']=='면적 측정의 불확실성이 응력 비교에 미치는 영향은?'
        assert canonical_hash(cold.core.report_content(report['id'],[asset])['assets'][0]['content']['result'])==report_digest
        assert len(cold.manager.list())==total
