"""Changed D5 contracts and one small existing FELUPE fit; no native/AI campaign."""
from copy import deepcopy
from pathlib import Path
import time
import pytest
from caelab.material_test import column_mapping, measured_protocol, physical_residual, deformation_plot_axis
from caelab.material_document import default_draft
from caelab.numerical_document import from_material_document
from caelab.workbench import Workbench


def mapping(*, shear=False):
    return column_mapping(time_column=0,time_unit='s',response_column=2,response_kind='stress',
        response_unit='MPa',stress_unit='MPa',measure='infinitesimal_Cauchy',
        component='xy' if shear else 'xx',drive_column=1,
        drive_kind='simple_shear' if shear else 'engineering_strain',drive_unit='1')


def test_explicit_units_no_cauchy_from_force_and_physical_residual():
    options=dict(time_column=0,time_unit='ms',response_column=2,response_kind='force',
        response_unit='kN',stress_unit='MPa',measure='first_Piola',component='xx',
        drive_column=1,drive_kind='displacement',drive_unit='mm',area=10,area_unit='mm',
        gauge=50,gauge_unit='mm')
    columns=column_mapping(**options)
    assert columns['stress']['scale']==pytest.approx(100)
    assert columns['stress']['axis']['scale']==.001
    assert columns['deformation']['scale']==pytest.approx(.02)
    with pytest.raises(ValueError,match='Cauchy'):
        column_mapping(**{**options,'measure':'infinitesimal_Cauchy'})
    with pytest.raises(ValueError,match='표점'):
        column_mapping(**{**options,'gauge':'1e'})
    x,residual=physical_residual({'observations':{'axes':[{'values':[0,1,2]}],'value':[1,2,3]},
        'prediction':[1.5,None,2],'mask':[True,True,False],'residual':[99,99,99]})
    assert x==[0,1,2] and residual==[.5,None,None]


def completed(wb,job):
    limit=time.monotonic()+20
    while time.monotonic()<limit:
        state=wb.manager.status(job['id'])
        if state['state'] in {'SUCCEEDED','FAILED','REJECTED','CANCELLED'}:
            assert state['state']=='SUCCEEDED',state
            return wb.result(job['id'])
        time.sleep(.01)
    raise AssertionError(wb.manager.status(job['id']))


def test_selected_trial_once_uses_current_coefficients_without_editing_owners(tmp_path):
    pytest.importorskip('felupe')
    from caelab.storage import canonical_hash
    wb=Workbench(tmp_path)
    def command(doc,op,args=None,**kw):
        return wb.document_command(doc['id'],op,args or {},session_id=doc['session_id'],
            expected_generation=doc['generation'],**kw)
    try:
        material=wb.document_open(kind='material',title='사용자 재료')
        receipt=wb.upload('user-cycle.csv',b'time,strain,stress\n0,0,0\n0.5,0.003,5\n2,0.001,2\n')
        data=wb.document_open(kind='data',title='사용자 반복 이력',draft={'data_id':receipt['id'],
            'mapping':{'delimiter':',','skip_header':1,'columns':mapping()}})
        imported=command(data,'data.import');observation=completed(wb,imported['job'])
        data=wb.document_read(data['id']);run=data['runs'][0]
        recipe=dict(channel='deformation',kind='engineering_strain',lateral_22=1.,lateral_33=1.)
        draft=from_material_document(material)
        draft['experiments']=[{'id':'UserCycle','role':'holdout','source':{
            'document_id':data['id'],'job_id':run['job_id'],'response':'stress',
            'input_revision':run['input_revision'],'input_sha256':run['input_sha256']},
            'response':'stress_xx','settings':measured_protocol(material['draft']['settings'],observation,recipe),
            'weight':2.,'scale':3.,'kinematics':recipe}]
        # Run Once is independent of the optimizer's unfinished starting values.
        for variable in draft['variables']:variable.update(value='1e',free=False)
        plan=wb.document_open(kind='numerical',title='사용자 동정 계획',draft=draft)
        changed=deepcopy(material['draft']);changed['settings']['parameters']['E']=1500.
        material=command(material,'material.update',{'draft':changed})['document']
        before_material=deepcopy(material);before_plan=deepcopy(plan)
        reference={'document_id':plan['id'],'input_revision':plan['input_revision'],
            'input_sha256':canonical_hash(plan['draft']),'experiment_id':'UserCycle'}
        submitted=command(material,'material.evaluate',{'trial':reference},command_id='Cuseronce')
        result=completed(wb,submitted['job'])
        assert submitted['job']['operation']=='evaluate'
        context=result['material_trial'];curve=context['curves'][0]
        assert context['parameters']=={'E':1500.,'nu':.25}
        assert curve['role']=='holdout' and curve['observations']['value']==[0.,5.,2.]
        assert curve['prediction']==pytest.approx([0.,5.4,1.8])
        assert curve['weight']==2. and curve['scale']==3.
        assert curve['observations']['axes'][0]['values']==[0.,.5,2.]
        current=wb.document_read(material['id'])
        assert all(current[key]==before_material[key] for key in ('draft','generation','input_revision'))
        assert wb.document_read(plan['id'])==before_plan
        retained=current['runs'][-1]
        assert retained['draft']['settings']['time']==[0.,.5,2.]
        assert retained['draft']['settings']['parameters']==context['parameters']
        assert retained['arguments']['material_trial']['source']==reference
        assert retained['arguments']['material_trial']['material_source']['input_sha256']==canonical_hash(changed)
        assert command(material,'material.evaluate',{'trial':reference},command_id='Cuseronce')['job']['id']==submitted['job']['id']
        assert len(wb.manager.list())==2
        saved=command(current,'document.save')['document']
        wb.material_documents._documents.clear()
        reopened=wb.document_open(kind='material',document_id=material['id'])
        assert reopened['saved_revision']==saved['saved_revision'] and reopened['draft']==changed
        assert wb.document_result(material['id'],submitted['job']['id'])['material_trial']==context
        jobs=len(wb.manager.list())
        for invalid in ({**reference,'input_sha256':'0'*64},
                        {**reference,'input_revision':'Iother'},
                        {**reference,'experiment_id':'Missing'},
                        {**reference,'settings':changed['settings']}):
            with pytest.raises(ValueError):command(reopened,'material.evaluate',{'trial':invalid})
        with pytest.raises(ValueError):command(reopened,'material.evaluate',{'settings':changed['settings']})
        invalid=deepcopy(plan['draft'])
        invalid['experiments'][0]['settings']['deformation_gradient'][1][0][0]=1.2
        edited=command(plan,'numerical.update',{'draft':invalid})['document']
        exact={**reference,'input_revision':edited['input_revision'],'input_sha256':canonical_hash(invalid)}
        with pytest.raises(ValueError,match='저장된 변형'):
            command(reopened,'material.evaluate',{'trial':exact})
        for field,value in (('stress_unit','Pa'),('time_unit','ms'),('model','neo_hooke')):
            invalid=deepcopy(plan['draft']);invalid['experiments'][0]['settings'][field]=value
            edited=command(edited,'numerical.update',{'draft':invalid})['document']
            exact={**reference,'input_revision':edited['input_revision'],'input_sha256':canonical_hash(invalid)}
            with pytest.raises(ValueError,match='trial model and units'):
                command(reopened,'material.evaluate',{'trial':exact})
        assert len(wb.manager.list())==jobs
    finally:
        assert wb.shutdown()['joined']


def test_trial_evaluation_does_not_wait_on_busy_plan(tmp_path):
    import threading
    from caelab.storage import canonical_hash
    wb=Workbench(tmp_path);held=threading.Event();release=threading.Event()
    material=wb.document_open(kind='material')
    plan=wb.document_open(kind='numerical',draft=from_material_document(material))
    def occupy():
        with wb.numerical_documents._lock(plan['id']):
            held.set();release.wait(5)
    thread=threading.Thread(target=occupy);thread.start()
    try:
        assert held.wait(1)
        reference={'document_id':plan['id'],'input_revision':plan['input_revision'],
            'input_sha256':canonical_hash(plan['draft']),'experiment_id':'UserCycle'}
        start=time.monotonic()
        with pytest.raises(ValueError,match='busy'):
            wb.material_documents.resolve_trial(reference,material)
        assert time.monotonic()-start<1 and not wb.manager.list()
    finally:
        release.set();thread.join(2)
        assert not thread.is_alive() and wb.shutdown()['joined']


def test_http_preparation_rejection_has_a_terminal_matching_receipt(tmp_path):
    import threading
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.storage import canonical_hash, load_json
    from caelab.workbench_client import Client, WorkbenchHTTPError
    service=LabService(tmp_path);server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True)
    thread.start();client=Client(f'http://127.0.0.1:{server.server_port}')
    try:
        material=client.document_open(kind='material')
        draft=from_material_document(material)
        for variable in draft['variables']:variable['free']=False
        plan=client.document_open(kind='numerical',draft=draft)
        request=dict(document_id=plan['id'],operation='numerical.run',arguments={},
            session_id=plan['session_id'],expected_generation=plan['generation'])
        expected=dict(document_id=plan['id'],command_id='Crejectedfit',
            request_hash=canonical_hash(request),outcome='REJECTED')
        for _ in range(2):
            with pytest.raises(WorkbenchHTTPError) as caught:
                client.document_command(plan['id'],'numerical.run',{},session_id=plan['session_id'],
                    expected_generation=plan['generation'],command_id='Crejectedfit')
            assert caught.value.code==400 and caught.value.command_rejection==expected
            assert caught.value.service_message.startswith('ValueError: ')
        assert not server.workbench.manager.list()
        path=server.workbench.root/'documents'/plan['id']/'commands/Crejectedfit.json'
        assert load_json(path)['state']=='REJECTED'
        edited=deepcopy(draft);edited['variables'][0]['free']=True
        updated=client.document_command(plan['id'],'numerical.update',{'draft':edited},
            session_id=plan['session_id'],expected_generation=plan['generation'],command_id='Ccorrectfit')
        assert updated['document']['draft']==edited
        for _ in range(2):
            with pytest.raises(WorkbenchHTTPError) as caught:
                client.document_command(plan['id'],'numerical.run',{},session_id=plan['session_id'],
                    expected_generation=plan['generation'],command_id='Cstalefit')
            assert caught.value.command_rejection=={**expected,'command_id':'Cstalefit'}
        assert client.document_read(plan['id'])['draft']==edited and not server.workbench.manager.list()
    finally:
        server.shutdown();server.server_close();thread.join(3);service.shutdown()
        assert not thread.is_alive()


def test_csv_two_coefficients_holdout_exact_protocol_and_adoption_reopen(tmp_path):
    pytest.importorskip('felupe')
    root=tmp_path/'store'
    wb=Workbench(root)
    def command(doc,op,args=None,**kw):
        return wb.document_command(doc['id'],op,args or {},session_id=doc['session_id'],
            expected_generation=doc['generation'],**kw)
    try:
        model=wb.document_open(kind='material',title='시험 재료')
        draft=from_material_document(model)
        draft['variables'][0].update(value=900,lower=500,upper=2000)
        draft['variables'][1].update(value=.2,lower=.1,upper=.4,free=True)
        for index,(filename,role,shear) in enumerate([('axial.csv','fit',False),('shear.csv','fit',True),('holdout.csv','holdout',False)]):
            receipt=wb.upload(filename,(Path(__file__).parents[1]/'examples/material-tests'/filename).read_bytes())
            data=wb.document_open(kind='data',title=filename,draft={'data_id':receipt['id'],
                'mapping':{'delimiter':',','skip_header':1,'columns':mapping(shear=shear)}})
            imported=command(data,'data.import'); result=completed(wb,imported['job'])
            data=command(wb.document_read(data['id']),'document.save')['document']
            run=data['runs'][0]
            recipe=dict(channel='deformation',kind='simple_shear' if shear else 'engineering_strain',lateral_22=1.,lateral_33=1.)
            settings=measured_protocol(model['draft']['settings'],result,recipe)
            draft['experiments'].append({'id':'Test'+str(index+1),'role':role,'source':{
                'document_id':data['id'],'job_id':run['job_id'],'response':'stress',
                'input_revision':run['input_revision'],'input_sha256':run['input_sha256']},
                'response':'stress_xy' if shear else 'stress_xx','settings':settings,'weight':1.,'scale':1.,
                'kinematics':recipe})
        # Re-importing the same physical samples is not independent holdout evidence.
        first=draft['experiments'][0]['source']
        original_data=wb.document_read(first['document_id'])
        reimport=command(original_data,'data.import');completed(wb,reimport['job'])
        duplicate=deepcopy(draft)
        alias=deepcopy(draft['experiments'][0]);alias.update(id='Alias',role='holdout')
        alias['source']['job_id']=reimport['job']['id']
        duplicate['experiments'].append(alias)
        with pytest.raises(ValueError,match='같은 원본 표본'):
            wb.numerical_documents.job_arguments(duplicate)
        plan=wb.document_open(kind='numerical',title='시편 피팅',draft=draft)
        bad=deepcopy(draft); bad['experiments'][0]['kinematics']['lateral_22']='1e'
        plan=command(plan,'numerical.update',{'draft':bad})['document']
        saved=command(plan,'document.save')['document']
        assert saved['draft']==bad and saved['diagnostics']
        with pytest.raises(ValueError):
            command(saved,'numerical.run')
        plan=command(saved,'numerical.update',{'draft':draft})['document']
        mismatch=deepcopy(draft); mismatch['experiments'][0]['settings']['deformation_gradient'][1][0][0]=1.2
        with pytest.raises(ValueError,match='저장된 변형'):
            wb.numerical_documents.job_arguments(mismatch)
        submitted=command(plan,'numerical.run'); result=completed(wb,submitted['job'])
        assert result['parameters']['E']==pytest.approx(1200,rel=1e-5)
        assert result['parameters']['nu']==pytest.approx(.25,abs=1e-5)
        assert [r['role'] for r in result['curves']]==['fit','fit','holdout']
        assert result['curves'][-1]['rmse']<1e-5
        assert wb.document_read(model['id'])['draft']==model['draft']
        candidate=min((r for r in result['candidates'] if r['execution_status']=='SUCCEEDED'),key=lambda r:r['objective'])
        from caelab.numerical_candidate_detail import COMMAND
        from caelab.numerical_candidate_evidence import CAPTURE, candidate_detail_readiness
        view=wb.numerical_candidate_detail(plan['id'],submitted['job']['id'],candidate['candidate_id'])
        if not candidate_detail_readiness(view)['ready_to_preserve']:
            detail=command(wb.document_read(plan['id']),COMMAND,dict(source=view['source'],
                candidate_id=candidate['candidate_id'],base_attempt_job_id=view['attempt_job_id']))
            completed(wb,detail['job'])
            view=wb.numerical_candidate_detail(plan['id'],submitted['job']['id'],candidate['candidate_id'],attempt_job_id=detail['job']['id'])
        evidence=command(wb.document_read(plan['id']),CAPTURE,dict(source=view['source'],
            candidate_id=candidate['candidate_id'],attempt_job_id=view['attempt_job_id'],purpose='success_judgment'))['reference']
        request=dict(material_document_id=model['id'],session_id=model['session_id'],expected_generation=model['generation'],command_id='Cd5adopt')
        request['detail_evidence']=evidence
        adopted=wb.desktop.adopt(plan['id'],submitted['job']['id'],candidate['candidate_id'],**request)['document']
        repeated=wb.desktop.adopt(plan['id'],submitted['job']['id'],candidate['candidate_id'],**request)['document']
        assert adopted['generation']==repeated['generation']
        material_saved=command(adopted,'document.save')['document']
        plan_saved=command(wb.document_read(plan['id']),'document.save')['document']
        assert wb.shutdown()['joined']
        wb=Workbench(root)
        reopened=wb.document_open(kind='material',document_id=model['id'])
        reopened_plan=wb.document_open(kind='numerical',document_id=plan['id'])
        assert reopened['draft']==material_saved['draft']
        assert reopened_plan['draft']==plan_saved['draft']
        assert wb.document_result(plan['id'],submitted['job']['id'])['parameters']==result['parameters']
    finally:
        assert wb.shutdown()['joined']


def test_derived_protocol_rejects_wrong_physics_and_missing_driver():
    settings=default_draft()['settings']
    recipe=dict(channel='driver',kind='engineering_strain',lateral_22=1,lateral_33=1)
    response=dict(kind='series',unit='1',measure='engineering_strain',component='xx',frame='material_cartesian',
        location='material_point',reduction='none',axes=[dict(name='time',unit='s',values=[0,1])],value=[0,.01])
    result={'execution_status':'SUCCEEDED','responses':{'driver':response}}
    assert measured_protocol(settings,result,recipe)['deformation_gradient'][1][0][0]==1.01
    for patch in ({'measure':'log_strain'},{'has_calculation_gaps':True},{'axes':[dict(name='strain',unit='1',values=[0,1])]}):
        wrong=deepcopy(result);wrong['responses']['driver'].update(patch)
        with pytest.raises(ValueError): measured_protocol(settings,wrong,recipe)


def test_measured_plot_axis_joins_original_rows_and_time_without_sorting():
    driver=dict(kind='series',unit='1',measure='simple_shear',component='xy',frame='material_cartesian',
        location='material_point',reduction='none',source_rows=[4,5,6,7],
        axes=[dict(name='time',unit='s',values=[0,1,2,3])],value=[0,.2,.1,-.1])
    result={'execution_status':'SUCCEEDED','responses':{'deformation':driver}}
    observed={'axes':[dict(name='time',unit='s',values=[0,2,3])],'source_rows':[4,6,7],'value':[0,48,-48]}
    recipe=dict(channel='deformation',kind='simple_shear',lateral_22=1,lateral_33=1)
    axis=deformation_plot_axis(observed,result,recipe)
    assert axis==dict(name='측정 전단량',unit='1',values=[0,.1,-.1])
    for patch in ({'source_rows':[4,8,7]},{'axes':[dict(name='time',unit='s',values=[0,1.99,3])]},
                  {'source_rows':[4,4,7]}):
        with pytest.raises(ValueError):
            deformation_plot_axis({**deepcopy(observed),**patch},result,recipe)
    assert driver['value']==[0,.2,.1,-.1]  # Display selection never edits its source.
