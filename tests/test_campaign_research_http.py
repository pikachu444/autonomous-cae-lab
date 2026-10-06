"""Real Core/HTTP model DOE, observed targets and saved report transport."""
from copy import deepcopy

from apps.lab.service import LabService
from caelab.optimizers.scipy_lhs import ScipyLatinHypercube
from test_campaign_report import arguments
from test_lab_server import running
from test_model_parameters import STUDY,register_x,synthetic_lab,template_settings


def factory(path):
    lab,_=synthetic_lab(path,create_study=False)
    lab.doe_adapters={'scipy.latin_hypercube':ScipyLatinHypercube()}
    return lab


def test_model_doe_reports_reopen_after_http_restart(tmp_path):
    lab,_=synthetic_lab(tmp_path);register_x(lab,upper=2.0)
    with running(LabService(lab.store,lab_factory=factory)) as client:
        plan=client.job('model_doe_plan',{'study_id':STUDY,'campaign_id':'C-report-doe',
            'backend':'test.model.parameterized','settings':template_settings(),'parameter_ids':['research_x'],
            'sample_count':8,'seed':13})['result']
        assert plan['objective'] is None
        result=client.job('doe_run',{'campaign_id':'C-report-doe'})['result']
        assert len(result['samples'])==8
        report=client.job('campaign_report_create',arguments())['result']
        assert client.request('/api/campaign-reports/R-report')==report
        opened=client.request('/api/campaigns/C-report-doe')
        assert opened['record']==result and opened['reports'][0]['report_id']=='R-report'
        client.request('/api/campaign-reports/R-report?untrusted=1',expected=400)
        client.request('/api/campaign-reports/..%2fescape',expected=400)
    with running(LabService(lab.store,lab_factory=factory)) as client:
        assert client.request('/api/campaign-reports/R-report')==report
        assert client.request('/api/campaigns/C-report-doe')['record']==result
        assert client.job('doe_run',{'campaign_id':'C-report-doe'})['result']==result
