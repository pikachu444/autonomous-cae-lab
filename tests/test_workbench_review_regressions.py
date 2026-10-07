"""Regression cases independently reproduced during numerical integration review."""
import pytest
from caelab.evaluation import PreparedEvaluation
from caelab.numerical import optimize,fit_model,analyze_candidates


def response(value):
    return {'kind':'series','value':[value,value],'unit':'1',
            'component':'scalar','location':'model','reduction':'none',
            'axes':[{'name':'time','unit':'s','values':[0.,1.]}]}


class GroupEvaluator:
    def __init__(self,status=None):
        self.status=status
        self.calls=[]
    def prepare(self,settings,runtime=None):
        def evaluate(values):
            self.calls.append(values)
            state=self.status if len(self.calls)==2 and self.status else 'SUCCEEDED'
            return {'execution_status':state,'responses':{'y':response(sum(values.values()))} if state=='SUCCEEDED' else {}}
        return PreparedEvaluation(evaluate,settings,batch=lambda values:[evaluate(v) for v in values])


VARIABLES=[{'id':'x','unit':'1','lower':0.,'upper':1.,'value':.9}]
OBJECTIVE={'response':'y','unit':'1','reduction':'abs_max'}


@pytest.mark.parametrize('status',['FAILED','CANCELLED'])
@pytest.mark.parametrize('operation',['optimize','de-fit','least-squares'])
def test_dispatched_group_is_journaled_before_stop(status,operation):
    evaluator=GroupEvaluator(status)
    execution={'mode':'batch','on_failure':'stop'}
    if operation=='optimize':
        result=optimize(evaluator,VARIABLES,OBJECTIVE,execution=execution,
                        options={'max_generations':1,'population_size':6})
    else:
        variables=VARIABLES+([{'id':'z','unit':'1','lower':0.,'upper':1.,'value':.5}] if operation=='least-squares' else [])
        result=fit_model(evaluator,variables,[{'id':'fit','response':'y','observations':response(100.)}],
            method='least_squares' if operation=='least-squares' else 'de',execution=execution,
            options={'max_nfev':2} if operation=='least-squares' else {'max_generations':1,'population_size':6})
    assert len(evaluator.calls)==len(result['candidates'])==(3 if operation=='least-squares' else 6)
    assert result['candidates'][1]['execution_status']==status
    assert result['execution_status']!='SUCCEEDED'


def test_failed_incumbent_cannot_become_success_after_curve_cache_eviction():
    def evaluate(values,settings):
        return {'execution_status':'FAILED','responses':{}} if values['x']<.5 else {
            'execution_status':'SUCCEEDED','responses':{'y':response(values['x'])}}
    result=fit_model(evaluate,VARIABLES,[{'id':'fit','response':'y','observations':response(100.)}],
        method='de',options={'failure_penalty':.001,'population_size':12,'max_generations':3,'seed':0})
    assert len(result['candidates'])>8
    assert result['execution_status']=='FAILED'
    assert 'penalized' in result['failure_reason']
    assert all(curve['execution_status']=='SUCCEEDED' for curve in result['curves'])


def test_compact_declared_reductions_remain_available_for_followup_analysis():
    result=optimize(GroupEvaluator(),VARIABLES,OBJECTIVE,options={'population_size':6,'max_generations':1})
    analysis=analyze_candidates(result,[OBJECTIVE])
    assert not analysis['exclusions']
    assert all(row['responses']=={} and row['response_reductions'] for row in result['candidates'])
