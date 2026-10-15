"""Existing owners and actual algebra evaluators; no native solver or provider."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest
from caelab.backends import Backend, _registry
from caelab.numerical_document import request_draft
from caelab.storage import canonical_hash
from caelab.workbench import Workbench
from caelab import numerical as n


VARIABLES=[dict(id='x',unit='1',value=.5,lower=0.,upper=1.,transform='linear'),
           dict(id='y',unit='1',value=.5,lower=0.,upper=1.,transform='linear')]
RESPONSE=dict(response='cost',unit='N',component='scalar',location='model',reduction='none')


def command(wb,doc,operation):
    return wb.document_command(doc['id'],operation,{},session_id=doc['session_id'],
        expected_generation=doc['generation'])


def run_plan(wb,operation,inputs,budget):
    doc=wb.document_open(kind='numerical',title='공개 대수 예제',draft=request_draft({
        'purpose':'공개 대수 예제','operation':operation,'inputs':deepcopy(inputs),'budget':{'evaluations':budget}}))
    assert not doc['diagnostics'],doc['diagnostics']
    reply=command(wb,doc,'numerical.run');doc=reply['document'];job=reply['job']['id']
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        status=wb.manager.status(job)
        if status['state'] in {'SUCCEEDED','PARTIAL_FAILURE','FAILED','REJECTED','CANCELLED'}:break
        time.sleep(.005)
    assert status['state'] in {'SUCCEEDED','PARTIAL_FAILURE'},status
    result=wb.document_result(doc['id'],job)
    doc=command(wb,doc,'document.save')['document']
    return doc,job,result,wb.document_result_reference(doc['id'],job)


@pytest.fixture
def algebra(monkeypatch):
    calls=[]
    def evaluate(values,settings):
        calls.append(deepcopy(values))
        if settings.get('fail') and values['x']>.5:
            return {'execution_status':'FAILED','responses':{},'diagnostics':{'failure_reason':'Declared algebra failure'}}
        return {'execution_status':'SUCCEEDED','responses':{'cost':{
            **{k:v for k,v in RESPONSE.items() if k!='response'},'kind':'scalar',
            'value':values['x']+2*values.get('y',0.)}}}
    monkeypatch.setitem(_registry,'test.extensions.algebra',Backend('test.extensions.algebra',('prepared',),lambda:evaluate))
    return calls


def test_actual_joint_uq_and_matched_sobol_owner_comparison(tmp_path,algebra):
    wb=Workbench(tmp_path)
    try:
        inp={'backend':'test.extensions.algebra','settings':{'fail':True},'variables':VARIABLES,
            'count':32,'seed':31,'independence':'JOINT_USER_DECLARED',
            'source':{'origin':'SYNTHETIC','reference':'Public x+2y; declared failure x>0.5'},
            'distributions':{name:{'distribution':'uniform','unit':'1','lower':0.,'upper':1.} for name in ('x','y')},
            'joint':{'family':'gaussian_copula','correlation':{'variables':['x','y'],'matrix':[[1.,.4],[.4,1.]]}},
            'thresholds':[{**RESPONSE,'operator':'>','limit':1.}]}
        doc,job,uq,_=run_plan(wb,'uq',inp,32)
        stat=uq['probability_statistics'][0]
        assert stat['total_count']==32 and stat['valid_count']+stat['failed_count']==32 and stat['failed_count']>0
        assert stat['exceedance_fraction_total_bounds'][1]>stat['exceedance_fraction_total_bounds'][0]
        analyses=[];refs=[]
        # Fixed fixture: y=x+2y, independent U(0,1), S1=ST=[.2,.8].
        # N=64/128, seed=17, first-order design, absolute tolerance .08.
        for count in (64,128):
            _,_,_,sampling_ref=run_plan(wb,'sample_sensitivity',{'variables':VARIABLES,'count':count,'seed':17,'second_order':False},count*4)
            _,_,_,table_ref=run_plan(wb,'doe',{'backend':'test.extensions.algebra','settings':{},
                'result_refs':{'candidates':sampling_ref}},count*4)
            _,_,analysis,ref=run_plan(wb,'sensitivity',{'result_refs':{'table':table_ref,'plan':sampling_ref},'response':RESPONSE},1)
            assert analysis['indices']['S1']==pytest.approx([.2,.8],abs=.08)
            assert analysis['indices']['ST']==pytest.approx([.2,.8],abs=.08)
            analyses.append(analysis);refs.append(ref)
        before=len(algebra)
        cdoc,cjob,comparison,_=run_plan(wb,'sensitivity',{'result_refs':dict(zip(('baseline','refined'),refs))},1)
        assert len(algebra)==before and comparison['analyses']==analyses
        assert comparison['source_refs']==dict(zip(('baseline','refined'),refs))
        assert comparison['base_counts']==[64,128]
        assert wb.document_result(doc['id'],job)==uq
        assert wb.document_result(cdoc['id'],cjob)==comparison
    finally:
        assert wb.shutdown()['joined']


def cold_read(folder,expected,*,query=False):
    """Fresh Python process: forbid hidden training/prediction/dispatch on read."""
    code='''
import json,sys,time
from pathlib import Path
from caelab.workbench import Workbench
from caelab import numerical as n
from caelab.surrogate_archive import restore
from caelab.storage import canonical_hash
def forbidden(*a,**k):raise AssertionError('cold read executed')
call=n.RBFInterpolator.__call__
n.fit_surrogate=forbidden;n.RBFInterpolator.__init__=forbidden;n.RBFInterpolator.__call__=forbidden
n.run_doe=forbidden
w=Workbench(Path(sys.argv[1]));submit=w.submit;w.submit=forbidden
before=w.manager.list()
added=None
try:
 for item in json.loads(sys.argv[2]):
  doc=w.document_open(kind='numerical',document_id=item['document_id'])
  result=w.document_result(doc['id'],item['job_id'])
  assert canonical_hash(result)==item['result_sha256']
  if 'model_artifact' in result:restore(result['model_artifact'])
 assert w.manager.list()==before
 if sys.argv[3]=='query':
  from caelab.numerical_document import request_draft
  n.RBFInterpolator.__call__=call;w.submit=submit
  reference=json.loads(sys.argv[2])[0]
  doc=w.document_open(kind='numerical',title='Moved model explicit query',draft=request_draft({
   'purpose':'Explicit query at moved location','operation':'surrogate','budget':{'evaluations':1},
   'inputs':{'result_refs':{'model':reference},'points':[{'x':.55}]}}))
  def command(operation):
   return w.document_command(doc['id'],operation,{},session_id=doc['session_id'],expected_generation=doc['generation'])
  reply=command('numerical.run');doc=reply['document'];job=reply['job']['id']
  deadline=time.monotonic()+15
  while time.monotonic()<deadline and w.manager.status(job)['state'] not in {'SUCCEEDED','FAILED','REJECTED'}:time.sleep(.005)
  assert w.manager.status(job)['state']=='SUCCEEDED',w.manager.status(job)
  result=w.document_result(doc['id'],job)
  assert abs(result['predictions'][0]['responses']['cost']['value']-.55)<1e-12
  assert result['local_coefficients_computed'] and not result['training_performed']
  doc=command('document.save')['document'];added=w.document_result_reference(doc['id'],job)
finally:assert w.shutdown()['joined']
print(json.dumps({'cold_read_fit_predict_physics':0,'explicit_new_query':added}))
'''
    completed=subprocess.run([sys.executable,'-c',code,str(folder),json.dumps(expected),'query' if query else 'read'],
        capture_output=True,text=True,timeout=35)
    assert completed.returncode==0,completed.stdout+completed.stderr
    return json.loads(completed.stdout)['explicit_new_query']


def test_local_archive_move_read_explicit_query_search_actual_and_cold(tmp_path,algebra,monkeypatch):
    origin=tmp_path/'origin';wb=Workbench(origin);closed=False
    try:
        variables=VARIABLES[:1];refs=[];saved=[]
        for points in ((0.,.2,.4,.6,.8,1.),(.1,.3,.5,.7,.9)):
            doc,job,result,ref=run_plan(wb,'doe',{'backend':'test.extensions.algebra','settings':{},
                'variables':variables,'candidates':[{'values':{'x':x}} for x in points]},len(points))
            refs.append(ref)
        doc,job,trained,ref=run_plan(wb,'surrogate',{'result_refs':dict(zip(('training','holdout'),refs)),
            'response':RESPONSE,'points':[{'x':.35}],'options':{'neighbors':3}},1)
        assert trained['model_artifact']['format']=='scipy-local-rbf-v1'
        saved.append(ref);original=canonical_hash(trained)
        before=len(algebra)
        def forbidden(*a,**k):raise AssertionError('Implicit retraining')
        monkeypatch.setattr(n,'fit_surrogate',forbidden)
        query=run_plan(wb,'surrogate',{'result_refs':{'model':ref},'points':[{'x':.45}]},1)
        assert query[2]['predictions'][0]['responses']['cost']['value']==pytest.approx(.45)
        assert query[2]['local_coefficients_computed'] and not query[2]['training_performed']
        saved.append(query[3])
        recommended=run_plan(wb,'surrogate',{'result_refs':{'model':ref},'search':{'variables':variables,
            'objective':{**RESPONSE,'direction':'minimize'},'seed':5,
            'options':{'max_generations':1,'population_size':5}}},10)
        recommendation=recommended[2]
        assert len(algebra)==before and recommendation['actual_evaluation_count']==0
        point=recommendation['best']['values'];assert recommendation['best']['execution_status']=='PREDICTED'
        saved.append(recommended[3])
        actual=run_plan(wb,'doe',{'backend':'test.extensions.algebra','settings':{},'variables':variables,
            'candidates':[{'candidate_id':'Confirmation','values':point}]},1)
        from caelab.surrogate_archive import confirmation_values
        paired=confirmation_values(recommendation,actual[2]['candidates'][0],point)
        assert paired['difference']==pytest.approx(0,abs=1e-12) and len(algebra)==before+1
        saved.append(actual[3])
        assert canonical_hash(wb.document_result(doc['id'],job))==original
        assert wb.shutdown()['joined'];closed=True
        moved=tmp_path/'moved';shutil.copytree(origin,moved)
        # Only this test's new temporary directories move; the original path is unavailable.
        for path in (origin,tmp_path/'sealed-origin',moved,tmp_path/'sealed-first-copy'):
            path.resolve().relative_to(tmp_path.resolve())
        origin.rename(tmp_path/'sealed-origin')
        saved.append(cold_read(moved,saved,query=True))
        recopied=tmp_path/'recopied';shutil.copytree(moved,recopied)
        moved.rename(tmp_path/'sealed-first-copy')
        cold_read(recopied,saved)
    finally:
        if not closed:assert wb.shutdown()['joined']
