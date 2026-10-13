"""Actual FELUPE plus exact HTTP transfer reader using explicit controlled native fields."""
from copy import deepcopy
import numpy as np
import pytest
from caelab.material_document import default_draft
from caelab.jobs import TERMINAL
from caelab.storage import canonical_hash
from test_connected_evaluation_study import service,controlled,sources,change,wait


def test_independent_felupe_probe_same_baseline_and_cold_inspection(service):
    pytest.importorskip('felupe')
    wb,client=service;draft=default_draft()
    draft['settings'].update(model='neo_hooke',parameters={'mu':30.,'lmbda':50.})
    draft['settings']['deformation_gradient'][1]=[[1.08,.12,0.],[.03,.98,0.],[0.,0.,1.02]]
    draft['settings']['tangent_probe']={'increment':1,'input_component':'xy','steps':[1e-5,1e-6,1e-7]}
    doc=client.document_open(kind='material',draft=draft)
    receipt=change(client,doc,'material.evaluate');job=receipt['job']['id']
    wait(lambda:client.status(job)['state'] in TERMINAL)
    result=client.document_result(doc['id'],job);assert result['execution_status']=='SUCCEEDED',result
    view=client.constitutive_inspect(doc['id'],job,1)
    assert view['increment']==1 and view['pair'].startswith('dP')
    quantities=view['quantities'];stress=next(q for q in quantities if q['measure']=='first_Piola')
    gradient=next(q for q in quantities if q['measure']=='deformation_gradient')
    assert stress['components']==gradient['components']==[a+b for a in 'xyz' for b in 'xyz']
    actual=result['diagnostics']['constitutive_increments'][1]
    assert np.array_equal(np.asarray(stress['values']).reshape(3,3),actual['stress'])
    assert not np.isclose(stress['values'][1],stress['values'][3]) # PK1 need not be symmetric
    assert gradient['unit']=='1' and gradient['values']==np.asarray(draft['settings']['deformation_gradient'][1]).reshape(-1).tolist()
    for probe in view['finite_differences']:
        minus=np.asarray(probe['minus_input']);plus=np.asarray(probe['plus_input'])
        assert plus[0,1]-minus[0,1]==pytest.approx(2*probe['h'])
        assert probe['initial_state']['internal_variables']==[]
    # A real old result without the new tensor record is read as six retained
    # scalars; missing PK1 components remain absent, never transposed.
    from caelab.constitutive_inspection import physical_quantities
    old=deepcopy(result);old['diagnostics'].pop('constitutive_increments')
    legacy=physical_quantities('material.felupe',draft['settings'],old,{'index':1},'material_cartesian')
    saved_stress=next(q for q in legacy if q['measure']=='first_Piola')
    assert [saved_stress['values'][i] for i in (3,6,7)]==[None,None,None]
    assert view['state_trial'] is None and view['state_committed'] is None and view['residual'] is None
    for probe in view['finite_differences']:
        assert np.allclose(probe['finite_difference'],probe['analytic'],rtol=2e-5,atol=1e-5)
    before=client.document_read(doc['id']);assert before['draft']==draft
    saved=change(client,before,'document.save')['document']
    from caelab.workbench import Workbench
    assert wb.shutdown()['joined']
    fresh=Workbench(wb.workspace)
    try:
        fresh.document_open(kind='material',document_id=saved['id'])
        again=fresh.constitutive_inspect(doc['id'],job,1)
        assert again['tangent']==view['tangent'] and again['source'] is not None
    finally:fresh.shutdown()
    assert len(wb.manager.list())==1


def test_exact_transfer_rows_bound_values_failed_run_and_saved_read(service,controlled):
    wb,client=service;original,draft=sources(client)
    doc=client.document_open(kind='evaluation',draft=draft)
    first=change(client,doc,'evaluation.run')['job']['id']
    wait(lambda:client.status(first)['state'] in TERMINAL)
    failed=client.evaluation_transfer(doc['id'],first,'TtoU',0)
    # The real execution wrapper saves actual bound settings even when the
    # controlled structural solver fails. Failure is never inferred from equality.
    assert failed['target_attempt']['state']=='FAILED'
    assert all(r['supplied']==320. and r['received']==320. for r in failed['rows'])
    second=change(client,client.document_read(doc['id']),'evaluation.run')['job']['id']
    wait(lambda:client.status(second)['state'] in TERMINAL)
    view=client.evaluation_transfer(doc['id'],second,'TtoU',0,start=1,count=2)
    assert view['exact_values_match'] and view['metadata']['unit']=='K'
    assert view['metadata']['coordinate_units']=='m' and len(view['rows'])==2
    assert all(row['available'] and row['required'] and row['difference']==0 for row in view['rows'])
    assert view['reference_temperature']==original[1]['draft']['settings']['material']['reference_temperature']
    assert view['reference_temperature_unit']=='K'
    for source in original:assert client.document_read(source['id'])['draft']==source['draft']
    count=len(wb.manager.list())
    with pytest.raises(Exception):client.evaluation_transfer(doc['id'],second,'TtoU',9)
    assert len(wb.manager.list())==count
    saved=change(client,client.document_read(doc['id']),'document.save')['document']
    from caelab.workbench import Workbench
    assert wb.shutdown()['joined']
    fresh=Workbench(wb.workspace)
    try:
        fresh.document_open(kind='evaluation',document_id=saved['id'])
        assert fresh.evaluation_transfer(doc['id'],second,'TtoU',0,start=1,count=2)['rows']==view['rows']
    finally:fresh.shutdown()



def test_failed_binding_keeps_supplied_values_without_invented_receipt(service,controlled,monkeypatch):
    from caelab.adapters.thermoelastic_fenicsx import ThermalFenicsxAdapter
    from plugins.thermoelastic.reference import seal_field
    actual=ThermalFenicsxAdapter.run
    def wrong_clock(self,settings,*,output,runtime=None):
        result=actual(self,settings,output=output,runtime=runtime)
        response=deepcopy(result['responses']['temperature'])
        response['time']+=1.
        result['responses']['temperature']=seal_field(response)
        return result
    monkeypatch.setattr(ThermalFenicsxAdapter,'run',wrong_clock)
    wb,client=service;_,draft=sources(client)
    doc=client.document_open(kind='evaluation',draft=draft)
    job=change(client,doc,'evaluation.run')['job']['id']
    wait(lambda:client.status(job)['state'] in TERMINAL)
    progress=client.evaluation_progress(doc['id'],job)
    assert progress['stages'][-1]['state']=='FAILED' and not progress['stages'][-1]['dispatched']
    assert not progress['transfers'] and controlled['calls']==['thermal']
    catalog=client.evaluation_transfer(doc['id'],job)
    assert catalog['transfers'][0]['receipt_recorded'] is False
    view=client.evaluation_transfer(doc['id'],job,'TtoU',0)
    assert view['transfer'] is None and view['transfer_confirmation']=='NOT_RECORDED'
    assert view['unavailable'] and not view['exact_values_match']
    assert all(row['supplied']==320. and row['received'] is None for row in view['rows'])
    assert len(wb.manager.list())==1


def test_exact_native_history_layouts():
    from caelab.constitutive_inspection import native_steps
    scalar={'time_s':1.,'tangent_kelvin_mpa':[[1.]],'nominal_after_update':{'s0':'actual'}}
    svk={'time_s':2.,'pk1_tangent_mpa':[[float(i==j) for j in range(9)] for i in range(9)],
         'nominal_after_update':{'s0':'actual finite strain'}}
    assert native_steps('material.mfront',{'mgis':{'steps':[scalar]}})==[scalar]
    assert native_steps('material.mfront.viscoelastic',{'mgis':{'steps':[scalar]}})==[scalar]
    actual=native_steps('material.mfront.hyperelastic',{'steps':[svk]})[0]
    assert actual['time_s']==2. and len(actual['pk1_tangent_mpa'])==9
    assert actual['nominal_after_update']==svk['nominal_after_update']


def test_missing_supplied_field_is_explained_but_corruption_is_not_hidden(service,controlled,monkeypatch):
    from caelab.adapters.thermoelastic_fenicsx import ThermalFenicsxAdapter
    from caelab.research_workflows import result_folder
    actual=ThermalFenicsxAdapter.run
    def omitted_field(self,settings,*,output,runtime=None):
        result=actual(self,settings,output=output,runtime=runtime)
        del result['responses']['temperature']
        return result
    monkeypatch.setattr(ThermalFenicsxAdapter,'run',omitted_field)
    wb,client=service;_,draft=sources(client)
    doc=client.document_open(kind='evaluation',draft=draft)
    job=change(client,doc,'evaluation.run')['job']['id']
    wait(lambda:client.status(job)['state'] in TERMINAL)
    progress=client.evaluation_progress(doc['id'],job)
    assert progress['stages'][0]['state']=='SUCCEEDED'
    assert progress['stages'][-1]['state']=='FAILED' and not progress['stages'][-1]['dispatched']
    view=client.evaluation_transfer(doc['id'],job,'TtoU',0)
    assert view['transfer'] is None and view['transfer_confirmation']=='NOT_RECORDED'
    assert view['rows']==[] and view['total']==0 and '선택한 장이 없습니다' in view['unavailable']
    assert controlled['calls']==['thermal'] and len(wb.manager.list())==1
    # Exact artifact validation still runs before absence is reported.
    folder,_=result_folder(wb,doc['id'],job)
    stage=folder/progress['stages'][0]['result_directory']/'result.json'
    stage.write_bytes(stage.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='hash differs'):
        wb.evaluation_transfer(doc['id'],job,'TtoU',0)
