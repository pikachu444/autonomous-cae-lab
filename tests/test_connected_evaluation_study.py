"""New shared workflows over real owners/HTTP/Qt with an explicit controlled solver boundary.

These checks exercise no FEniCSx, CAD, material solver or provider. Native fields
below are labelled test captures; production execution/transfer/retention is real.
"""
from copy import deepcopy
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import threading
import time

import pytest
from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from caelab.workbench_client import Client
from caelab.evaluation_definition import default_draft, document_reference
from caelab.simulation_document import default_draft as simulation_draft
from caelab.storage import canonical_hash
from caelab.jobs import TERMINAL
from test_thermoelastic_stages import small_settings, captured_temperature


def wait(predicate, app=None):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        if app: app.processEvents()
        if predicate(): return
        time.sleep(.005)
    raise AssertionError('Actual owner/HTTP transition did not finish')


def change(client, doc, operation, arguments=None):
    return client.document_command(doc['id'],operation,arguments or {},session_id=doc['session_id'],
        expected_generation=doc['generation'])


@pytest.fixture
def service(tmp_path):
    server=LabHTTPServer(LabService(tmp_path/'store'),0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True); thread.start()
    client=Client('http://127.0.0.1:'+str(server.server_port))
    try: yield server.workbench,client
    finally:
        server.shutdown(); server.server_close(); thread.join(3)


@pytest.fixture
def controlled(monkeypatch):
    from caelab.adapters.thermoelastic_fenicsx import ThermalFenicsxAdapter, ThermoelasticFenicsxAdapter
    from plugins.thermoelastic.reference import seal_field
    state={'calls':[],'fail_structure':True,'alternate':False,'block':False,
           'started':threading.Event(),'release':threading.Event()}
    def thermal(self, settings, *, output, runtime=None):
        state['calls'].append('thermal')
        if state['block']:
            state['started'].set(); assert state['release'].wait(6)
        value=320. if not state['alternate'] else 320.+len(state['calls'])%2
        return {'execution_status':'SUCCEEDED','responses':{'temperature':captured_temperature(settings,[value]*4),
            'mean_temperature':{'kind':'scalar','value':value,'unit':'K'}},'checks':[],
            'diagnostics':{'scope':'CONTROLLED native adapter boundary; not a solver result'}}
    def structural(self, settings, *, output, runtime=None):
        self.validate_settings(settings)
        state['calls'].append('structural')
        if state['fail_structure']:
            state['fail_structure']=False
            raise RuntimeError('Controlled second-stage failure')
        field=deepcopy(settings['temperature']); state['received_temperature']=deepcopy(field)
        field.update(value=[[0.,0.],[1e-4,0.],[0.,2e-5],[1e-4,2e-5]],unit='m',quantity='displacement',
                     measure='small_strain_displacement',component=['x','y'])
        field=seal_field(field)
        return {'execution_status':'SUCCEEDED','responses':{'displacement':field},'checks':[],
            'diagnostics':{'scope':'CONTROLLED native adapter boundary; not a solver result'}}
    monkeypatch.setattr(ThermalFenicsxAdapter,'run',thermal)
    monkeypatch.setattr(ThermoelasticFenicsxAdapter,'run',structural)
    yield state
    state['release'].set()


def sources(client):
    docs=[]
    for backend,stage in [('thermal.fenicsx.rectangle','thermal'),('structural.fenicsx.thermoelastic_rectangle','structural')]:
        doc=client.document_open(kind='simulation',draft={'backend':backend,'settings':small_settings(stage)})
        docs.append(change(client,doc,'document.save')['document'])
    draft=default_draft()
    draft['stages']=[{'id':'Heat','name':'Temperature','source':document_reference(docs[0])},
                     {'id':'Structure','name':'Thermal strain','source':document_reference(docs[1])}]
    draft['transfers']=[{'id':'TtoU','from_stage':'Heat','output':'temperature','to_stage':'Structure',
                        'input':'temperature','mapping':'exact_same_mesh','lag':0}]
    draft['responses']=[{'id':'displacement','stage':'Structure','response':'displacement','unit':'m'}]
    return docs,draft


def test_http_exact_transfer_failure_prefix_reuse_study_and_reopen(service,controlled):
    wb,client=service
    original,draft=sources(client)
    unconnected=deepcopy(draft); unconnected['transfers']=[]
    doc=client.document_open(kind='evaluation',draft=unconnected)
    inspection=client.evaluation_inspect(doc['id'])
    assert inspection['stages'][1]['ports']['inputs']['temperature']['required'] is True
    assert inspection['diagnostics']  # Repair ports remain visible in the editor.
    doc=change(client,doc,'evaluation.update',{'draft':draft})['document']
    receipt=change(client,doc,'evaluation.run'); first=receipt['job']['id']; doc=receipt['document']
    wait(lambda:client.status(first)['state'] in TERMINAL)
    failed=client.document_result(doc['id'],first)
    assert failed['execution_status']=='FAILED' and controlled['calls']==['thermal','structural']
    progress=client.evaluation_progress(doc['id'],first)
    assert progress['stages'][0]['state']=='SUCCEEDED' and progress['stages'][1]['state']=='FAILED'
    heat=client.evaluation_stage_result(doc['id'],first,progress['stages'][0]['attempt_id'])
    assert heat['responses']['temperature']['value']==[320.]*4 and heat['post_input']['format']=='pvd'
    doc=change(client,doc,'document.save')['document']
    ref=client.document_result_reference(doc['id'],first)
    retry=deepcopy(doc['draft']); retry['reuse']={'source':ref,'stages':['Heat']}
    doc=change(client,doc,'evaluation.update',{'draft':retry})['document']
    second=change(client,doc,'evaluation.run')['job']['id']
    wait(lambda:client.status(second)['state'] in TERMINAL)
    result=client.document_result(doc['id'],second)
    assert result['execution_status']=='SUCCEEDED',result
    assert controlled['calls']==['thermal','structural','structural']
    assert result['stages'][0]['reused_from']==ref
    assert result['transfers'][0]['source_response_sha256']==canonical_hash(controlled['received_temperature'])
    assert result['responses']['displacement']['frame']=='global_cartesian'
    assert client.document_read(original[1]['id'])['draft']['settings']['temperature'] is None
    doc=change(client,client.document_read(doc['id']),'document.save')['document']
    result_ref=client.document_result_reference(doc['id'],second)
    study=client.result_followup(result_ref,'study',session_id=doc['session_id'],command_id='Cstudy')['document']
    study_draft=deepcopy(study['draft']); study_draft['hypotheses']=[{'id':'Hct','title':'CTE hypothesis','statement':'Does temperature explain displacement?','status':'UNKNOWN'}]
    study=change(client,study,'study.update',{'draft':study_draft})['document']
    study=change(client,study,'document.save')['document']
    assert client.study_references(study['id'])['references'][0]['status']=='AVAILABLE'
    context={'study_id':study['id'],'saved_revision':study['saved_revision'],'input_revision':study['input_revision'],
             'input_sha256':canonical_hash(study['draft']),'selected_kind':'evidence','selected_id':'Eresult'}
    discussion=client.study_followup(context,'expert',session_id=study['session_id'],command_id='Cdiscuss')
    assert discussion['executed'] is False and discussion['document']['draft']['composer']['evidence'][0]['job_id']==second
    assert len(wb.manager.list())==2  # No inference/extra calculation from navigation.
    # New owner process-equivalent: actual service shutdown and new owner store.
    assert wb.shutdown()['joined']
    from caelab.workbench import Workbench
    reopened=Workbench(wb.workspace)
    try:
        restored=reopened.document_open(kind='evaluation',document_id=doc['id'])
        assert restored['draft']==retry
        assert reopened.document_result(doc['id'],second)==result
        assert reopened.study_references(study['id'])['references'][0]['status']=='AVAILABLE'
        assert reopened.document_result(doc['id'],first)['execution_status']=='FAILED'
        assert controlled['calls']==['thermal','structural','structural']
    finally: reopened.shutdown()


def test_cancel_keeps_late_stage_and_never_starts_downstream(service,controlled):
    wb,client=service; _,draft=sources(client)
    controlled['block']=True
    doc=client.document_open(kind='evaluation',draft=draft)
    job=change(client,doc,'evaluation.run')['job']['id']
    assert controlled['started'].wait(5)
    assert client.cancel(job)['cancel_requested'] is True
    controlled['release'].set()
    wait(lambda:client.status(job)['state'] in TERMINAL)
    result=client.document_result(doc['id'],job)
    assert result['execution_status']=='CANCELLED' and controlled['calls']==['thermal']
    assert len(result['stages'])==1 and result['stages'][0]['state']=='SUCCEEDED'
    stage=client.evaluation_stage_result(doc['id'],job,result['stages'][0]['attempt_id'])
    assert stage['responses']['temperature']['value']==[320.]*4
    change(client,client.document_read(doc['id']),'document.save')


def test_iteration_nonconvergence_is_retained_not_released(service,controlled):
    _,client=service; sources_,draft=sources(client)
    controlled['alternate']=True
    draft['stages']=draft['stages'][:1]; draft['responses']=[]
    draft['transfers']=[{'id':'LagT','from_stage':'Heat','output':'temperature','to_stage':'Heat',
        'input':'linearization_temperature','mapping':'exact_same_mesh','lag':1}]
    draft['iteration']={'enabled':True,'maximum':3,'checks':[{'stage':'Heat','response':'temperature','unit':'K',
        'absolute':1e-9,'relative':0.,'scale':1.}]}
    doc=client.document_open(kind='evaluation',draft=draft)
    job=change(client,doc,'evaluation.run')['job']['id']; wait(lambda:client.status(job)['state'] in TERMINAL)
    result=client.document_result(doc['id'],job)
    assert result['execution_status']=='FAILED' and result['diagnostics']['convergence_status']=='NOT_CONVERGED'
    assert len(result['iterations'])==3 and len(result['transfers'])==2 and not result['responses']
    assert result['diagnostics']['decision']=='NOT_RELEASED'
    change(client,client.document_read(doc['id']),'document.save')


def test_simulation_actual_qt_edit_undo_save_and_plan(service):
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    from apps.research.simulation_window import SimulationWindow
    app=QApplication.instance() or QApplication([])
    wb,client=service
    source=client.document_open(kind='simulation',draft=simulation_draft('thermal.fenicsx.rectangle'))
    window=SimulationWindow(client,auto_open=False,poll_interval=0)
    window._opened(source)
    try:
        window.tree.setCurrentItem(window._nodes[('settings','conductivity')])
        control=window.fields[('settings','conductivity','value')][0]
        control.setText('350'); control.textEdited.emit('350')
        window.save_document(); wait(lambda:not window._busy and not window.local_dirty,app)
        assert window.document['draft']['settings']['conductivity']['value']==350.
        window.command('document.undo'); wait(lambda:not window._busy,app)
        assert window.document['draft']['settings']['conductivity']['value']==200.
        receipt=client.domain_plan(source['id'],session_id=window.document['session_id'],
            expected_generation=window.document['generation'],command_id='CsimPlan')
        assert receipt['document']['diagnostics']==[] and receipt['executed'] is False
        assert not wb.manager.list()
    finally:
        wait(lambda:not window._busy,app); window._allow_close=True; window.close()
