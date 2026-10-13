"""Actual pinned rainflow and existing Data/Simulation/Study owners; no solver."""
from copy import deepcopy
import time
import pytest
from caelab import fatigue
from caelab.workbench import Workbench
from caelab.data_document import default_draft
from caelab.jobs import TERMINAL


def response(values=None):
    values=values if values is not None else [100.,-100.,100.]
    return {'kind':'series','unit':'MPa','component':'xx','location':'gauge','measure':'infinitesimal_Cauchy',
        'frame':'specimen_fixed','reduction':'none','value':values,
        'axes':[{'name':'time','unit':'s','values':list(range(len(values)))}]}


def settings(ref=None):
    value=fatigue.default_settings()
    value.update(source={'result':ref or {'document_id':'Tsample','job_id':'Jsample','input_revision':'Isample',
        'input_sha256':'a'*64,'result_sha256':'b'*64},'response':'response','title':'공개 합성 반복 응력'},
        sn_curve=[{'amplitude_mpa':50.,'cycles':1e7},{'amplitude_mpa':100.,'cycles':1e6},{'amplitude_mpa':200.,'cycles':1e5}],
        calibration={'reference':'Synthetic demonstration, not measured fatigue data','conditions':'Signed axial demonstration only',
            'mean_min_mpa':0.,'mean_max_mpa':0.,'temperature_min_k':293.,'temperature_max_k':294.},
        temperature_k=293.15,repeat_block=True)
    return value


def test_actual_rainflow_closed_extremum_and_no_false_periodic_life():
    result=fatigue.analyze(settings(),response())
    assert sum(row['count'] for row in result['cycles'])==1
    assert result['responses']['miner_damage']['value']==pytest.approx(1e-6)
    assert result['responses']['repeating_blocks_to_D1']['value']==pytest.approx(1e6)
    source=response([0.,100.,-100.,0.])
    draft=settings();draft['calibration'].update(mean_min_mpa=-100.,mean_max_mpa=100.)
    bounded=fatigue.analyze(draft,source)
    assert bounded['diagnostics']['life_status']=='UNKNOWN'
    assert 'repeating_blocks_to_D1' not in bounded['responses']
    assert sum(row['count'] for row in bounded['cycles'])>0
    outside=fatigue.analyze(settings(),response([250.,-250.,250.]))
    assert outside['diagnostics']['assessment']=='UNKNOWN'
    assert 'miner_damage' not in outside['responses'] and outside['cycles'][0]['damage'] is None


def test_no_gap_prediction_equivalent_stress_or_hidden_mean_correction():
    for key,value in (('has_calculation_gaps',True),('component','von_mises'),('frame','UNKNOWN'),('measure','PK1')):
        r=response();r[key]=value
        with pytest.raises(ValueError):fatigue.stress_history(r)
    r=response();r['raw_samples']={'quality_valid':[True,False,True]}
    with pytest.raises(ValueError,match='무효'):fatigue.stress_history(r)
    changed=response([120.,-80.,120.])
    result=fatigue.analyze(settings(),changed)
    assert result['diagnostics']['assessment']=='UNKNOWN' and result['cycles'][0]['reason']
    bad=settings();bad['resolved_response']=response()
    with pytest.raises(ValueError):fatigue.validate_settings(bad)


def wait(wb,job):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        state=wb.manager.status(job['id'])
        if state['state'] in TERMINAL:
            assert state['state']=='SUCCEEDED',state
            return wb.result(job['id'])
        time.sleep(.005)
    raise AssertionError('Bounded actual Data/rainflow job did not finish')


def test_actual_data_import_fatigue_save_study_and_cold_reopen(tmp_path):
    wb=Workbench(tmp_path);fresh=None
    def command(doc,op,args=None):
        return wb.document_command(doc['id'],op,args or {},session_id=doc['session_id'],expected_generation=doc['generation'])
    try:
        upload=wb.upload('public-cyclic.csv',b'time,stress\n0,100\n1,-100\n2,100\n')
        draft=default_draft();draft['data_id']=upload['id'];draft['mapping']['skip_header']=1
        channel=draft['mapping']['columns']['response']
        channel.update(unit='MPa',component='xx',location='gauge',measure='infinitesimal_Cauchy',frame='specimen_fixed')
        channel['axis'].update(name='time',unit='s')
        data=wb.document_open(kind='data',draft=draft,title='공개 합성 반복 응력')
        imported=command(data,'data.import');wait(wb,imported['job'])
        data=command(wb.document_read(data['id']),'document.save')['document']
        ref=wb.document_result_reference(data['id'],imported['job']['id'])
        inputs=settings(ref)
        doc=wb.document_open(kind='simulation',draft={'backend':fatigue.BACKEND,'settings':inputs},title='반복하중 평가')
        run=command(doc,'simulation.evaluate');result=wait(wb,run['job'])
        actual=wb.document_result(doc['id'],run['job']['id'])
        assert actual['diagnostics']['source']['result']==ref
        assert actual['responses']['miner_damage']['value']==pytest.approx(1e-6)
        assert len(wb.manager.list())==2
        doc=command(wb.document_read(doc['id']),'document.save')['document']
        result_ref=wb.document_result_reference(doc['id'],run['job']['id'])
        study=wb.desktop.result_followup(result_ref,'study',session_id=doc['session_id'],command_id='CfatigueStudy')['document']
        assert wb.study_references(study['id'])['references'][0]['status']=='AVAILABLE'
        workspace=wb.workspace
        assert wb.shutdown()['joined']
        fresh=Workbench(workspace)
        reopened=fresh.document_open(kind='simulation',document_id=doc['id'])
        assert reopened['draft']['settings']==inputs
        assert fresh.document_result(doc['id'],run['job']['id'])==actual
        assert len(fresh.manager.list())==2
    finally:
        if fresh:fresh.shutdown()
        else:wb.shutdown()


def test_known_native_stress_metadata_is_interpreted_without_rewriting_source(tmp_path):
    from caelab.adapters.retained_law_responses import _channel_descriptor
    (tmp_path/'native_raw.json').write_text('{"explicit_test_double":true}',encoding='ascii')
    original=response()
    channel={'id':'mgis-stress-xx','label':'MGIS Cauchy stress xx','quantity':'stress','component':'xx',
        'measure':'infinitesimal Cauchy stress; physical tensor components','location':'single homogeneous material point',
        'unit':'MPa','coordinate_frame':'Tridimensional model component basis; sensor/world alignment UNKNOWN',
        'axis':{'unit':'s'},'initial_state':{'kind':'UNPREPARED_INITIAL_CONDITION','index':0},
        'origin':{'kind':'NATIVE','driver':'mgis','native_field':'stress_physical_mpa'}}
    descriptor=_channel_descriptor(channel,'material.mfront','a'*64,tmp_path)
    descriptor.update(value=original['value'],axes=original['axes'])
    before=deepcopy(descriptor)
    result=fatigue.analyze(settings(),descriptor)
    assert descriptor==before and 'frame' not in descriptor
    assert result['responses']['stress_history']['measure']==channel['measure']
    assert result['diagnostics']['stress_interpretation']['component']=='xx'
    assert result['responses']['miner_damage']['value']==pytest.approx(1e-6)
    j2=deepcopy(descriptor)
    j2.update(component='SIEF_ELGA.SIXX',measure='small-strain Cauchy stress at native Gauss point',
        coordinate_frame='global Cartesian model; sensor/world alignment UNKNOWN',
        location={'element_id':1,'point':1,'subpoint':1})
    j2['source'].update(backend='structural.code_aster.plasticity',
        exact_selection={'kind':'fe_gauss','component':'SIEF_ELGA.SIXX','element_id':1,'point':1,'subpoint':1})
    assert fatigue.stress_definition(j2)['component']=='xx'
    for key,value in (('component','SIEF_ELGA.SIXY'),('measure','PK1'),('coordinate_frame','unknown local frame'),
                      ('reduction','unweighted_arithmetic_mean'),('frame','specimen_rotating')):
        broken=deepcopy(j2);broken[key]=value
        with pytest.raises(ValueError):fatigue.stress_history(broken)


def test_counter_is_in_the_installable_package_with_mit_notice():
    from importlib.resources import files
    from caelab._vendor import rainflow
    import tomllib
    from pathlib import Path
    assert rainflow.__version__=='3.2.0'
    assert list(rainflow.extract_cycles([100.,-100.,100.]))
    root=Path(__file__).resolve().parents[1]
    manifest=tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8'))
    assert 'caelab*' in manifest['tool']['setuptools']['packages']['find']['include']
    data=manifest['tool']['setuptools']['package-data']['caelab._vendor']
    for name in ('rainflow.LICENSE.txt','rainflow.NOTICE.md'):
        assert name in data and files('caelab._vendor').joinpath(name).is_file()
    assert 'Permission is hereby granted' in files('caelab._vendor').joinpath('rainflow.LICENSE.txt').read_text(encoding='utf-8')
