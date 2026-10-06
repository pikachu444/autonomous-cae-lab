"""Closed numerical references and immutable report/native joins; no native solver."""
from copy import deepcopy

import pytest

from caelab.optimizers.scipy_lhs import ScipyLatinHypercube
from caelab.storage import load_json, save_json
from test_model_parameters import STUDY, register_x, synthetic_lab, template_settings


def completed(lab):
    lab.doe_adapters = {'scipy.latin_hypercube': ScipyLatinHypercube()}
    register_x(lab, upper=2.0)
    lab.plan_model_doe(study_id=STUDY,campaign_id='C-report-doe',backend='test.model.parameterized',
                       settings=template_settings(),parameter_ids=['research_x'],sample_count=8,seed=13)
    return lab.run_doe('C-report-doe')


def arguments():
    return dict(campaign_id='C-report-doe',report_id='R-report',purpose='TEST ONLY linear+quadratic responses',
                origin='SYNTHETIC',reference='Closed TEST ONLY y=1, x in[0,2]',
                response_definitions=[{'metric':'synthetic_constraint','unit':'1','direction':'minimize'},
                                      {'metric':'synthetic_objective','unit':'1','direction':'minimize'}],
                uncertainty={'interpretation':'USER_DECLARED_UNIFORM_INPUTS','reference':'TEST ONLY bounded uniform x'},seed=13)


def test_saved_report_preserves_native_samples_and_closed_reference(tmp_path):
    lab,adapter=synthetic_lab(tmp_path); result=completed(lab)
    original={p:p.read_bytes() for p in (lab.store/'experiments').rglob('*') if p.is_file()}
    report=lab.create_campaign_report(**arguments())
    rows=report['samples']; linear=[s['responses']['synthetic_constraint']['value'] for s in rows]
    assert linear==pytest.approx([s['values']['research_x']+1 for s in rows])
    assert report['analysis']['statistics'][0]['mean']==pytest.approx(sum(linear)/len(linear))
    for model in report['analysis']['surrogate']:
        assert model['valid'] is True
        assert model['test_max_error'] < 1e-10
    calls=adapter.calls
    assert lab.inspect_campaign_report('R-report')==report
    assert lab.campaign_reports('C-report-doe')[0]['integrity']=='NOT_CHECKED'
    assert adapter.calls==calls and all(p.read_bytes()==b for p,b in original.items())
    assert report['decision']=='NOT_RELEASED' and report['engineering_qualification']=='UNKNOWN'
    assert report['source']['sample_ids']==[r['model_experiment_id'] for r in result['samples']]
    with pytest.raises(FileExistsError): lab.create_campaign_report(**arguments())


@pytest.mark.parametrize('field,change', [('reference',' '),('origin','VERIFIED_PHYSICS'),
    ('response_definitions',[{'metric':'synthetic_constraint','unit':'MPa','direction':'minimize'}]),
    ('response_definitions',[{'metric':'missing','unit':'1','direction':'minimize'}]),
    ('seed',True)])
def test_wrong_report_declaration_refuses_without_append(tmp_path,field,change):
    lab,_=synthetic_lab(tmp_path); completed(lab); args=arguments();args[field]=change
    with pytest.raises(ValueError):lab.create_campaign_report(**args)
    assert not (lab.store/'campaign_reports'/'R-report').exists()


@pytest.mark.parametrize('target',['report','result','sample'])
def test_report_source_tamper_refused(tmp_path,target):
    lab,_=synthetic_lab(tmp_path); completed(lab);lab.create_campaign_report(**arguments())
    if target=='report':path=lab.store/'campaign_reports/R-report/record.json'
    elif target=='result':path=lab.store/'campaigns/C-report-doe/result.json'
    else:path=lab.store/'experiments/E-C-report-doe-0001/result.json'
    record=load_json(path);record['decision']='RELEASED';save_json(path,record)
    with pytest.raises((ValueError,KeyError)):lab.inspect_campaign_report('R-report')


def test_completed_campaign_required_and_report_symlink_denied(tmp_path):
    lab,_=synthetic_lab(tmp_path);lab.doe_adapters={'scipy.latin_hypercube':ScipyLatinHypercube()};register_x(lab,upper=2.0)
    lab.plan_model_doe(study_id=STUDY,campaign_id='C-report-doe',backend='test.model.parameterized',
        settings=template_settings(),parameter_ids=['research_x'],sample_count=8,seed=13)
    with pytest.raises(ValueError,match='Complete'):lab.create_campaign_report(**arguments())
    lab.run_doe('C-report-doe');lab.create_campaign_report(**arguments())
    folder=lab.store/'campaign_reports/R-report'; record=folder/'record.json';external=lab.store/'outside.json'
    record.replace(external);record.symlink_to(external)
    with pytest.raises(ValueError,match='symlink'):lab.inspect_campaign_report('R-report')


@pytest.mark.parametrize('change', ['removed', 'metric_catalogue'])
def test_sealed_report_reopens_without_current_backend_admission(tmp_path, change):
    lab, adapter = synthetic_lab(tmp_path)
    completed(lab)
    report = lab.create_campaign_report(**arguments())
    originals = {p: p.read_bytes() for p in lab.store.rglob('*') if p.is_file()}
    calls = adapter.calls
    if change == 'removed':
        lab.model_analysis_adapters = {}
        lab.doe_adapters = {}
    else:
        adapter.default_metrics = []
    assert lab.inspect_campaign_report('R-report') == report
    assert adapter.calls == calls
    assert all(p.read_bytes() == value for p, value in originals.items())
    args = arguments(); args['report_id'] = 'R-new-without-admission'
    with pytest.raises(ValueError, match='advertised'):
        lab.create_campaign_report(**args)
    assert not (lab.store / 'campaign_reports' / args['report_id']).exists()
