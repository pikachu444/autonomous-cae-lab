"""File reader -> uncertainty owner -> Study/report keeps rejection, no model."""
from copy import deepcopy
import pytest
from caelab.storage import canonical_hash
from caelab.experiment_analysis_service import source_problem, uncertainty_request
from caelab.experiment_analysis_reporting import study_draft, blocks
from .support import ServiceHost
from .test_file_workflow import import_source, capture
from .test_uncertainty import standard


@pytest.mark.parametrize('rho,expected',[(-.9,'REJECTED'),(.2,'SUCCEEDED')])
def test_related_joint_covariance_status_survives_real_owner_and_report(tmp_path,rho,expected):
    with ServiceHost(tmp_path) as h:
        data,original,source=import_source(h)
        digest=canonical_hash(h.data.result(data,original))
        p=source_problem(h.core,{'source':source})
        assert p['included']==[True,True,True,False,False]
        variables=p['variables'];n=len(variables)
        matrix=[[None]*n for _ in range(n)];supplied={}
        for i in range(3):
            supplied[variables[i]['id']]=standard(1.,variables[i]['unit'])
            for j in range(3):matrix[i][j]=1. if i==j else rho
        # Explicit zero uncertainty for coefficients in this analytic test is
        # not inference from fit residuals or missing correlations.
        for i in range(n-3,n):
            supplied[variables[i]['id']]=standard(0.,variables[i]['unit'])
            matrix[i][i]=0.
        s={'uncertainties':supplied,'dependence':{'kind':'covariance',
           'order':[v['id'] for v in variables],'units':[v['unit'] for v in variables],
           'matrix':matrix,'note':'Public supplied analytic block and explicitly fixed coefficients'},
           'axis_uncertainty':'UNKNOWN'}
        doc,job,result=h.run_plan(uncertainty_request(source,s))
        assert result['execution_status']==expected
        assert result['diagnostics']['model_calls']==0
        a=result['experiment_analysis']
        assert a['source_problem']['values']==p['values'] and a['source_problem']['included']==p['included']
        assert a['supplied']==s
        assert all(r['status']=='EXCLUDED' for r in a['rows'][3:])
        if expected=='REJECTED':
            assert a['covariance_validity']=='INVALID'
            assert all(r['standard_uncertainty'] is None for r in a['rows'])
            assert not any(r['status']=='COMPUTED_FIRST_ORDER' for r in a['rows'])
        else:
            assert all(r['status']=='COMPUTED_FIRST_ORDER' for r in a['rows'][:3])
        h.save(doc);report,asset=capture(h,doc,job)
        content=h.core.report_content(report,[asset])['assets'][0]['content']['result']
        assert content['execution_status']==expected
        draft=study_draft(result,h.core.document_result_reference(doc,job),
            question='알려진 공분산의 일관성을 어떻게 확인할까?')
        study=h.study.open(draft=draft);h.save(study['id'])
        assert canonical_hash(h.data.result(data,original))==digest
        report_hash=canonical_hash(content);total=len(h.manager.list())
    with ServiceHost(tmp_path) as cold:
        def forbidden(*a,**k):pytest.fail('read/save unexpectedly submitted')
        cold.manager.submit=forbidden
        content=cold.core.report_content(report,[asset])['assets'][0]['content']['result']
        assert canonical_hash(content)==report_hash
        assert cold.owner.result(doc,job)['execution_status']==expected
        assert cold.study.read(study['id'])['draft']==draft
        assert len(cold.manager.list())==total
