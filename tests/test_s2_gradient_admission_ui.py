"""Real Qt display/reader contract over controlled raw records, not adjoint math."""
from copy import deepcopy
import json
import time
import pytest
from PySide6.QtCore import QCoreApplication,QEvent,QThreadPool
from PySide6.QtWidgets import QApplication
from apps.research.appearance import apply_appearance,configure_plot_fonts
from apps.research.candidate_results_window import CandidateResultsWindow


def ready(app,predicate):
    end=time.monotonic()+6
    while time.monotonic()<end:
        app.processEvents()
        if predicate():return
        time.sleep(.005)
    raise AssertionError('Controlled S2 read did not settle')


class ControlledReader:
    """Same read API/parent identity fields; no solver, owner command or native app."""
    def __init__(self,path,verification='PASS',*,status='SUCCEEDED',purpose='optimization',admission=None,parent_status=None):
        self.calls=[];self.path=path
        self.identity=dict(document_id='Ncontrolled',job_id='Jcontrolled',candidate_id='Ccontrolled',
            candidate_purpose=purpose,candidate_gradient_admission=admission,candidate_execution_status=status)
        if parent_status is not None:self.identity['parent_execution_status']=parent_status
        if verification is not None:
            self.identity['gradient_verification']={'status':verification,'directions':[]}
        self.attempt=dict(iteration=0,stage_id='Heat',attempt_id='Aexact-adjoint',state='SUCCEEDED',
            backend='thermal.scikit_fem.rectangle',primal_reference={'attempt_id':'Aexact-primal'})
        self.raw=dict(execution_status='SUCCEEDED',derivatives={'heat_source':
            {'response':'mean_temperature','value':.25,'unit':'K/(W/m^3)'}},
            diagnostics={'adjoint':{'primal_relative_residual':1e-13,'adjoint_relative_residual':2e-13,
                'free_dofs':9,'adjoint_solve_calls':1,'finite_difference_calls':0}},
            artifacts=[{'path':'raw-adjoint.json','sha256':'a'*64}])
        self.path.write_text(json.dumps(self.raw,sort_keys=True),encoding='utf-8')

    def numerical_evaluation_result(self,document,job,candidate,*,evaluation_index=None,attempt_id=None,selection=None):
        self.calls.append((document,job,candidate,evaluation_index,attempt_id,deepcopy(selection)))
        assert (document,job,candidate)==('Ncontrolled','Jcontrolled','Ccontrolled')
        if evaluation_index is None:
            return {**deepcopy(self.identity),'evaluations':[{'evaluation_index':0,
                'execution_status':'SUCCEEDED','stage_execution_count':1}]}
        assert evaluation_index==0 and selection=={'metadata_only':True}
        answer={**deepcopy(self.raw),**deepcopy(self.identity),'evaluation_index':0}
        if attempt_id is None:
            answer.update(derivative_attempts=[deepcopy(self.attempt)],stage_names={'Heat':'정상 열전도'})
        else:
            assert attempt_id=='Aexact-adjoint'
            answer.update(stage_attempt=deepcopy(self.attempt),attempt_kind='adjoint')
        return answer


@pytest.fixture
def app():
    app=QApplication.instance() or QApplication([]);apply_appearance(app);configure_plot_fonts()
    yield app
    assert QThreadPool.globalInstance().waitForDone(5000)
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()


@pytest.mark.parametrize('verification,status,purpose,admission,usable',[
    ('PASS','SUCCEEDED','optimization',None,True),
    ('FAIL','SUCCEEDED','optimization','VERIFICATION_FAIL',False),
    ('INCOMPLETE','SUCCEEDED','optimization','VERIFICATION_INCOMPLETE',False),
    (None,'SUCCEEDED',None,None,True),
    ('RUNNING','SUCCEEDED','optimization',None,False),
    ('PASS','FAILED','optimization',None,False),
    ('PASS','CANCELLED','optimization',None,False),
    ('PASS','REJECTED','optimization',None,False),
    ('PASS','SUCCEEDED','gradient_verification',None,False),
    ('PASS','SUCCEEDED','optimization','VERIFICATION_UNKNOWN',False),
])
def test_parent_admission_survives_exact_raw_adjoint_read(app,tmp_path,verification,status,purpose,admission,usable):
    client=ControlledReader(tmp_path/'raw-adjoint.json',verification,status=status,purpose=purpose,admission=admission)
    before=(deepcopy(client.identity),deepcopy(client.raw),client.path.read_bytes())
    window=CandidateResultsWindow(client,document_id='Ncontrolled',session_id='Scontrolled',
        job_id='Jcontrolled',candidate_id='Ccontrolled')
    try:
        window.show();ready(app,lambda:not window._busy and window._composite is not None)
        def check():
            table=window.gradient_evidence.gradients
            assert table.rowCount()==1 and table.item(0,3).text()=='0.25' and table.item(0,4).text()=='K/(W/m^3)'
            assert table.item(0,5).text()==('최적화 사용 가능' if usable else
                '독립 검사 전용' if purpose=='gradient_verification' else '최적화 사용 불가')
        check();window.stages.selectRow(0)
        ready(app,lambda:not window._busy and window._stage_result is not None);check()
        assert client.calls[-1][4]=='Aexact-adjoint'
        assert window._stage_result['execution_status']=='SUCCEEDED'
        assert window._stage_result['diagnostics']==client.raw['diagnostics']
        assert (client.identity,client.raw,client.path.read_bytes())==before
        details=json.loads(window.diagnostics.toPlainText())
        assert details['candidate_execution_status']==status and details['candidate_purpose']==purpose
        if verification is not None:assert details['gradient_verification']['status']==verification
        assert 'Aexact-adjoint' not in window.message.text()
        if not usable:assert '최적화' in window.gradient_evidence.summary.text()
    finally:
        window.close();ready(app,lambda:not window._busy);window.deleteLater()


@pytest.mark.parametrize('parent_status,label',[('FAILED','실패'),('CANCELLED','취소')])
def test_successful_raw_candidate_cannot_override_failed_parent_run(app,tmp_path,parent_status,label):
    client=ControlledReader(tmp_path/'raw-adjoint.json',parent_status=parent_status)
    before=(deepcopy(client.identity),deepcopy(client.raw),client.path.read_bytes())
    window=CandidateResultsWindow(client,document_id='Ncontrolled',session_id='Scontrolled',
        job_id='Jcontrolled',candidate_id='Ccontrolled')
    try:
        window.show();ready(app,lambda:not window._busy and window._composite is not None)
        assert window.gradient_evidence.gradients.item(0,5).text()=='최적화 사용 불가'
        window.stages.selectRow(0);ready(app,lambda:not window._busy and window._stage_result is not None)
        assert window.gradient_evidence.gradients.item(0,3).text()=='0.25'
        assert window.gradient_evidence.gradients.item(0,5).text()=='최적화 사용 불가'
        assert '원 최적화 실행: '+label in window.gradient_evidence.summary.text()
        assert window._stage_result['execution_status']=='SUCCEEDED'
        assert window._stage_result['candidate_execution_status']=='SUCCEEDED'
        assert json.loads(window.diagnostics.toPlainText())['parent_execution_status']==parent_status
        assert (client.identity,client.raw,client.path.read_bytes())==before
    finally:
        window.close();ready(app,lambda:not window._busy);window.deleteLater()
