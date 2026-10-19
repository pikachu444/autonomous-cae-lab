"""Real HTTP/owners/retention with explicitly CONTROLLED numerical adapters.

No test in this module claims a scikit-fem calculation or Windows/Qt execution.
"""
from copy import deepcopy
import json
import subprocess
import sys
from pathlib import Path
import threading
import time

import numpy as np
import pytest
from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from caelab.workbench_client import Client
from caelab.evaluation_definition import default_draft, document_reference
from caelab.storage import canonical_hash
from caelab.jobs import TERMINAL
from caelab import scikit_fem_models as domain
from caelab import p1_temperature_transfer as t
from test_s1_p1_temperature import settings, analytic_field, options


def wait(predicate, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate(): return
        time.sleep(.01)
    raise AssertionError('Actual owner transition exceeded the explicit test timeout')


def change(client, doc, operation, arguments=None):
    return client.document_command(doc['id'], operation, arguments or {}, session_id=doc['session_id'],
                                   expected_generation=doc['generation'])


@pytest.fixture
def service(tmp_path):
    server = LabHTTPServer(LabService(tmp_path/'S1 한글 공백 저장소'), 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval':.02}, daemon=True)
    thread.start()
    client = Client('http://127.0.0.1:'+str(server.server_port))
    try:
        yield server.workbench, client
    finally:
        for job in server.workbench.manager.list():
            if job['state'] not in TERMINAL:
                server.workbench.manager.cancel(job['id'])
        server.shutdown(); server.server_close(); thread.join(5)
        assert not thread.is_alive()


@pytest.fixture
def controlled(monkeypatch):
    from caelab.adapters.scikit_fem_spatial import ScikitFemThermalAdapter, ScikitFemThermoelasticAdapter
    state = {'calls': [], 'fault': None, 'block': False, 'started': threading.Event(), 'release': threading.Event()}
    def thermal(self, s, *, output, runtime=None):
        self.validate_settings(s); state['calls'].append(('thermal', s['time']['value']))
        if state['block']:
            state['started'].set()
            if not state['release'].wait(8): raise RuntimeError('CONTROLLED test gate timed out')
        field = analytic_field(s, lambda x, y: 300+4*x-2*y+5*s['time']['value'])
        if state['fault'] == 'mask': field['valid_mask'][0] = False; field = t.original.seal_field(field)
        if state['fault'] == 'hole': field['cell_node_ids'].pop(); field['mesh_sha256'] = t.original.mesh_digest(field['coordinates'],field['cell_node_ids']); field = t.original.seal_field(field)
        if state['fault'] == 'clock': field['time_origin'] = 'different_origin'; field = t.original.seal_field(field)
        responses = {'temperature':field}
        if state['fault'] == 'missing': responses = {}
        return {'execution_status':'SUCCEEDED', 'responses':responses, 'checks':[],
                'diagnostics':{'numerical_boundary':'CONTROLLED_SYNTHETIC_NOT_A_SOLVER'}}
    def structural(self, s, *, output, runtime=None):
        self.validate_settings(s); state['calls'].append(('structural',s['time']['value']))
        if state['fault'] == 'receiver': raise RuntimeError('CONTROLLED receiver failure; not a physical solver failure')
        field = deepcopy(s['temperature'])
        xy = np.asarray(field['coordinates']); absolute = np.asarray(t._absolute_values(field))
        # Controlled fields only test store/Post plumbing; not an elastic solution.
        displacement = {k:v for k,v in field.items() if k not in ('capture_sha256','temperature_reference')}
        displacement.update(value=(1e-5*(absolute-s['material']['reference_temperature'])[:,None]*xy).tolist(),
            unit='m', quantity='displacement', measure='small_strain_displacement', component='vector',components=['x','y'])
        displacement = t.original.seal_field(displacement)
        geometry = t.rectangle_geometry(s); cells = np.asarray(geometry['cell_node_ids'])
        stress = dict(geometry, kind='field', value=[[1.,2.,3.]]*len(cells), unit='Pa', quantity='stress',
            component='tensor_components',components=['xx','yy','xy'],location='cell',reduction='cell_average',association='CELLS',
            measure='infinitesimal_Cauchy',frame='global_cartesian',coordinate_units='m',coordinate_frame='global_cartesian',
            mesh_coordinates=geometry['coordinates'],coordinates=xy[cells].mean(axis=1).tolist(),cell_ids=list(range(len(cells))),
            time=s['time']['value'],time_units=s['time']['unit'],time_origin=s['time']['origin'],basis='DG0',valid_mask=[True]*len(cells),snapshot_kind='physical_snapshot')
        stress = t.original.seal_field(stress)
        return {'execution_status':'SUCCEEDED','responses':{'displacement':displacement,'stress':stress},'checks':[],
                'diagnostics':{'numerical_boundary':'CONTROLLED_SYNTHETIC_NOT_A_SOLVER'}}
    monkeypatch.setattr(ScikitFemThermalAdapter,'run',thermal)
    monkeypatch.setattr(ScikitFemThermoelasticAdapter,'run',structural)
    try:
        yield state
    finally:
        state['release'].set()


def sources(client, *, outside=False):
    models = [(domain.THERMAL,settings(cells=(2,1),instant=0.)),
              (domain.THERMAL,settings(cells=(4,2),instant=2.)),
              (domain.STRUCTURAL,settings(domain.STRUCTURAL,(3,2),instant=1.))]
    models[-1][1]['validation']['free_expansion_max_error'] = None
    if outside: models[-1][1]['domain']['lengths'][0] = 1.1
    docs = []
    for backend,s in models:
        doc = client.document_open(kind='simulation',title='온도 / 열변형',draft={'backend':backend,'settings':s})
        assert not doc['diagnostics'],doc
        docs.append(change(client,doc,'document.save')['document'])
    draft = default_draft()
    draft['stages'] = [{'id':i,'name':n,'source':document_reference(d)} for i,n,d in zip(
        ['Start','End','Structure'],['0초 공급','2초 공급','다른 메시 구조'],docs)]
    draft['transfers'] = [{'id':'TtoU','from_stage':'Start','output':'temperature','to_stage':'Structure','input':'temperature',
        'mapping':t.MAPPING,'lag':0,'options':options(models[-1][1],('Start','End'),'linear')}]
    draft['responses'] = [{'id':'u','stage':'Structure','response':'displacement','unit':'m'},
                          {'id':'stress','stage':'Structure','response':'stress','unit':'Pa'}]
    return docs,draft


def run(client, draft):
    doc = client.document_open(kind='evaluation',title='S1 서로 다른 메시',draft=draft)
    assert not doc['diagnostics'],doc
    check = client.evaluation_inspect(doc['id'])
    assert not check['diagnostics'],check
    receipt = change(client,doc,'evaluation.run'); job = receipt['job']['id']
    wait(lambda: client.status(job)['state'] in TERMINAL)
    return client.document_read(doc['id']),job,client.document_result(doc['id'],job)


@pytest.fixture
def controlled_hex8(controlled,monkeypatch):
    from caelab.adapters.law_native_fe import LawNativeFEAdapter
    from caelab.law_native_thermal_regions import validate_settings
    state={'calls':[],'fail':False}
    def receiver(self,s,*,output,runtime=None):
        s=validate_settings(s)
        state['calls'].append(deepcopy(s))
        if state['fail']:
            return {'execution_status':'FAILED','settings':deepcopy(s),'responses':{},'checks':[],
                    'diagnostics':{'reason':'CONTROLLED_RECEIVER_FAILURE_NOT_FE','physical_qualification':'UNKNOWN'}}
        history=s['thermal_regions']
        return {'execution_status':'SUCCEEDED','settings':deepcopy(s),'checks':[],
                'responses':{'mean_temperature':{'kind':'series','value':[float(np.mean(v)) for v in history['temperature']['values']],
                    'unit':'K','axes':[{'name':'time','unit':'s','values':history['time_s']}],
                    'component':'scalar','location':'controlled_receiver'}},
                'diagnostics':{'numerical_boundary':'CONTROLLED_HEX8_SLOT_CONSUMER_NOT_FE',
                               'physical_qualification':'UNKNOWN','decision':'NOT_RELEASED'}}
    monkeypatch.setattr(LawNativeFEAdapter,'run',receiver)
    return state


def hex8_sources(client):
    from test_s1_p1_temperature import _hex8_temperature_receiver
    models=[(domain.THERMAL,settings(cells=(2,1),instant=0.)),
            (domain.THERMAL,settings(cells=(4,2),instant=2.)),
            ('structure.felupe.law_native',_hex8_temperature_receiver())]
    docs=[]
    for index,(backend,s) in enumerate(models):
        doc=client.document_open(kind='simulation',title=['선택한 첫 온도','선택한 다음 온도','사용자 Hex8 수신 모델'][index],
                                 draft={'backend':backend,'settings':s})
        assert not doc['diagnostics'],doc
        docs.append(change(client,doc,'document.save')['document'])
    draft=default_draft()
    draft['stages']=[{'id':name,'name':doc['title'],'source':document_reference(doc)}
                     for name,doc in zip(('Start','End','Bulk'),docs)]
    for slot,instant in enumerate((0.,1.,2.)):
        opts=t.default_options('End' if slot==2 else 'Start',receiver_time={'value':instant,'unit':'s','origin':'test_origin'})
        if slot==1:opts['time'].update(mode='linear',sources=[{'stage':'Start','output':'temperature'},{'stage':'End','output':'temperature'}])
        draft['transfers'].append({'id':'Tslot'+str(slot),'from_stage':'End' if slot==2 else 'Start',
            'output':'temperature','to_stage':'Bulk','input':'temperature_'+str(slot),'mapping':t.MAPPING,'lag':0,'options':opts})
    draft['responses']=[{'id':'chosen_temperature','stage':'Bulk','response':'mean_temperature','unit':'K'}]
    return docs,draft


def test_hex8_response_provenance_guard_accepts_only_exact_response_name_without_jobs(service):
    """Configuration admission only; exact saved-source ownership is tested above."""
    from test_s1_p1_temperature import _hex8_temperature_receiver
    wb,_=service
    authored=_hex8_temperature_receiver()
    reference={'stage':'UserTemperature','attempt_id':'Aselected', 'output':'temperature_1-K'}
    authored['thermal_regions']['temperature']['source']=[{'source_refs':[reference]},None,None]
    original=deepcopy(authored)
    assert wb._settings('structure.felupe.law_native',authored)==original
    assert authored==original and not wb.manager.list()

    # The exception is a response identifier at this one typed location, never
    # an executable, directory, path, arbitrary nested output, or other backend.
    for key,value in [('command','temperature'),('output_root','temperature'),('path','temperature'),
                      ('output','../temperature'),('output','folder/temperature'),
                      ('output','C:\\temperature'),('output',''),('output',123)]:
        rejected=deepcopy(original)
        rejected['thermal_regions']['temperature']['source'][0]['source_refs'][0]={key:value}
        before=deepcopy(rejected)
        with pytest.raises(ValueError):wb._settings('structure.felupe.law_native',rejected)
        assert rejected==before and not wb.manager.list()
    misplaced=deepcopy(original);misplaced['thermal_regions']['temperature']['source'][0]['output']='temperature'
    with pytest.raises(ValueError):wb._settings('structure.felupe.law_native',misplaced)
    with pytest.raises(ValueError):wb._settings(domain.THERMAL,original)
    assert authored==original and not wb.manager.list()


def test_http_hex8_multiple_slots_saved_inspection_and_cold_read_without_solver(service,controlled,controlled_hex8,tmp_path):
    wb,client=service;docs,draft=hex8_sources(client)
    originals=[deepcopy(client.document_read(doc['id'])) for doc in docs]
    doc,job,result=run(client,draft)
    assert result['execution_status']=='SUCCEEDED',result
    assert controlled['calls']==[('thermal',0.),('thermal',2.)]
    assert len(controlled_hex8['calls'])==1
    bound=controlled_hex8['calls'][0]
    assert all(row is not None for row in bound['thermal_regions']['temperature']['values'])
    inspections=[client.evaluation_transfer(doc['id'],job,'Tslot'+str(i),0) for i in range(3)]
    for i,view in enumerate(inspections):
        assert view['exact_values_match'] and view['metadata']['basis']=='Hex8_nodal_samples'
        assert view['metadata']['time']==float(i) and view['metadata']['unit']=='K'
        assert view['extrusion']['axis']=='z' and view['extrusion']['invariant'] is True
        assert len(view['receiver_rows'])==len(bound['mesh']['points'])
        for row in view['receiver_rows']:
            x,y,z=row['coordinates']
            assert abs(row['mapped']-(300.+5*i+4*x-2*y))<=1e-10
            assert row['received']==row['mapped'] and row['difference']==0.
        assert view['temperature']['reference_subtractions_in_mapping']==0
    assert inspections[1]['clock']['weights']==[.5,.5]
    assert len(inspections[0]['source_snapshots'])==1 and len(inspections[1]['source_snapshots'])==2
    assert bound['thermal_regions']['temperature']['source'][0]['capture_sha256'] != bound['thermal_regions']['temperature']['source'][1]['capture_sha256']
    for original in originals:
        current=client.document_read(original['id'])
        assert current['draft']==original['draft'] and current['saved_revision']==original['saved_revision']
    saved=change(client,client.document_read(doc['id']),'document.save')['document']
    expected={'workspace':str(wb.workspace),'document_id':saved['id'],'job_id':job,
              'result_sha256':canonical_hash(result),'draft':saved['draft'],
              'values':[[r['mapped'] for r in view['receiver_rows']] for view in inspections]}
    request=tmp_path/'hex8-cold-request.json';request.write_text(json.dumps(expected),encoding='utf-8')
    assert wb.shutdown()['joined']
    code='''import builtins,json,sys
from pathlib import Path
from caelab.workbench import Workbench
from caelab.storage import canonical_hash
from caelab.adapters.scikit_fem_spatial import _Spatial
from caelab.adapters.law_native_fe import LawNativeFEAdapter
from caelab import p1_temperature_transfer as p1,temperature_receiver_3d as bridge
def forbidden(*a,**k):raise AssertionError('Cold read cannot solve or remap')
_Spatial.run=LawNativeFEAdapter.run=p1.map_temperature=bridge.map_temperature=forbidden
original=builtins.__import__
def guard(name,*a,**k):
 if name.split('.')[0] in {'felupe','skfem','scipy','dolfinx','petsc4py'}:raise AssertionError('Cold read imported a solver')
 return original(name,*a,**k)
builtins.__import__=guard
expected=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'));wb=Workbench(Path(expected['workspace']))
try:
 d=wb.document_open(kind='evaluation',document_id=expected['document_id'])
 assert d['draft']==expected['draft']
 r=wb.document_result(d['id'],expected['job_id']);assert canonical_hash(r)==expected['result_sha256']
 before=wb.manager.list()
 for slot in range(3):
  v=wb.evaluation_transfer(d['id'],expected['job_id'],'Tslot'+str(slot),0)
  assert v['exact_values_match'] and [row['mapped'] for row in v['receiver_rows']]==expected['values'][slot]
 assert wb.manager.list()==before
 print(json.dumps({'status':'PASS','new_process':True,'solver_calls':0,'mapping_calls':0}))
finally:assert wb.shutdown()['joined']
'''
    child=None
    try:
        child=subprocess.Popen([sys.executable,'-c',code,str(request)],cwd=Path(__file__).parents[1],
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        stdout,stderr=child.communicate(timeout=30)
        assert child.returncode==0,(stdout,stderr)
        assert json.loads(stdout)['status']=='PASS'
    finally:
        if child is not None:
            if child.poll() is None:child.kill()
            child.wait(timeout=5)
            if child.stdout:child.stdout.close()
            if child.stderr:child.stderr.close()


def test_http_hex8_duplicate_slot_and_failed_source_keep_provenance_before_dispatch(service,controlled,controlled_hex8):
    wb,client=service;docs,draft=hex8_sources(client)
    duplicate=deepcopy(draft['transfers'][0]);duplicate['id']='Tduplicate'
    draft['transfers'].insert(1,duplicate)
    doc=client.document_open(kind='evaluation',title='중복 슬롯 원문 보존',draft=draft)
    assert any('destination port only once' in row['message'] for row in doc['diagnostics'])
    from caelab.workbench_client import WorkbenchHTTPError
    with pytest.raises(WorkbenchHTTPError):change(client,doc,'evaluation.run')
    assert not wb.manager.list() and not controlled['calls'] and not controlled_hex8['calls']
    assert client.document_read(doc['id'])['draft']==draft
    assert client.document_read(docs[-1]['id'])['draft']['settings']['thermal_regions']['temperature']['values']==[None]*3
    controlled['fault']='mask'
    _,fresh=hex8_sources(client)
    failed,failed_job,result=run(client,fresh)
    assert result['execution_status']=='FAILED' and not controlled_hex8['calls']
    failure=client.evaluation_transfer(failed['id'],failed_job,'Tslot0',0)
    assert failure['transfer_confirmation']=='FAILED' and not failure['exact_values_match']
    assert failure['source_snapshots'][0]['reference']['attempt_id']


def test_http_two_snapshots_receipt_Post_CLI_and_cold_process(service,controlled,tmp_path):
    wb,client = service; docs,draft = sources(client)
    assert not controlled['calls'] and not wb.manager.list()
    doc,job,result = run(client,draft)
    assert result['execution_status']=='SUCCEEDED',result
    inspection = client.evaluation_transfer(doc['id'],job,'TtoU',0)
    assert inspection['exact_values_match'] and inspection['clock']['weights']==[.5,.5]
    assert [len(s['rows']) for s in inspection['source_snapshots']]==[6,15]
    assert len(inspection['receiver_rows'])==12 and inspection['original_source_and_receiver_are_different_meshes']
    assert all(abs(r['mapped']-(305+4*r['coordinates'][0]-2*r['coordinates'][1])) <= 1e-10 for r in inspection['receiver_rows'])
    assert inspection['reference_temperature']==293.15
    last=result['stages'][-1]
    stage=client.evaluation_stage_result(doc['id'],job,last['attempt_id'])
    assert stage['post_registration']['status']!='FAILED' if 'post_registration' in stage else True
    assert {r['response'] for r in stage['post_inputs']}=={'displacement','stress'}
    from apps.research.scikit_fem_result_view import fields
    captures=fields(stage); assert len(captures)==2
    assert captures[1]['field']['association']=='CELLS' and captures[1]['time_unit']=='s'
    # Existing Plan uses the saved domain owner; creating/opening it evaluates nothing.
    before=list(controlled['calls'])
    plan=client.domain_plan(docs[0]['id'],session_id=docs[0]['session_id'],expected_generation=docs[0]['generation'],command_id='CS1Plan')
    assert plan['executed'] is False and controlled['calls']==before
    doc=change(client,client.document_read(doc['id']),'document.save')['document']
    from caelab.temperature_transfer_mcp import register_transfer_tool
    class DeclaredTransport:
        def __init__(self): self.tools={}
        def tool(self):
            def register(fn): self.tools[fn.__name__]=fn; return fn
            return register
    transport=DeclaredTransport();register_transfer_tool(transport,lambda:client)
    # Controlled MCP registration only; the registered function uses REAL HTTP.
    via_mcp=transport.tools['evaluation_transfer_read'](doc['id'],job,'TtoU',0)
    assert via_mcp['clock']['weights']==[.5,.5] and via_mcp['exact_values_match']
    from caelab.workbench_cli import main
    # CLI is an actual read against the same HTTP owner, not a copied result.
    assert main(['documents','transfer',doc['id'],job,'--url',client.url,'--transfer-id','TtoU','--iteration','0'])==0
    expected={'document_id':doc['id'],'job_id':job,'result_sha256':canonical_hash(result),
              'mapped_values':[r['mapped'] for r in inspection['receiver_rows']], 'workspace':str(wb.workspace)}
    request=tmp_path/'cold-request.json';request.write_text(json.dumps(expected),encoding='utf-8')
    assert wb.shutdown()['joined']
    code = '''import builtins,json,sys
from pathlib import Path
from caelab.workbench import Workbench
from caelab.storage import canonical_hash
from caelab.adapters.scikit_fem_spatial import _Spatial
from caelab import p1_temperature_transfer as transfer
calls=[]
def forbidden(*a,**kw):
 calls.append('FORBIDDEN');raise AssertionError('Cold read attempted a solve or mapping')
_Spatial.run=forbidden;transfer.map_temperature=forbidden
original=builtins.__import__
def guard(name,*a,**kw):
 if name.split('.')[0] in {'skfem','scipy','dolfinx','petsc4py'}: raise AssertionError('Cold read imported a solver')
 return original(name,*a,**kw)
builtins.__import__=guard
expected=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
wb=Workbench(Path(expected['workspace']))
try:
 d=wb.document_open(kind='evaluation',document_id=expected['document_id'])
 r=wb.document_result(d['id'],expected['job_id'])
 assert canonical_hash(r)==expected['result_sha256']
 x=wb.evaluation_transfer(d['id'],expected['job_id'],'TtoU',0)
 assert [v['mapped'] for v in x['receiver_rows']]==expected['mapped_values']
 for row in r['stages']:
  stage=wb.evaluation_stage_result(d['id'],expected['job_id'],row['attempt_id'])
  for post in stage.get('post_inputs',[]): wb.native_input(post['id'])
 assert not calls
 print(json.dumps({'status':'PASS','new_process':True,'solve_calls':len(calls),'transfer_rows':len(x['rows'])}))
finally:
 assert wb.shutdown()['joined']
'''
    process=None
    try:
        process=subprocess.Popen([sys.executable,'-c',code,str(request)],cwd=Path(__file__).parents[1],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        stdout,stderr=process.communicate(timeout=20)
        assert process.returncode==0,(stdout,stderr)
        assert json.loads(stdout)['solve_calls']==0
    finally:
        if process is not None:
            if process.poll() is None: process.kill()
            process.wait(timeout=5)
            if process.stdout:process.stdout.close()
            if process.stderr:process.stderr.close()


@pytest.mark.parametrize('fault',['mask','hole','clock','missing','outside'])
def test_mapping_failure_retained_before_receiver_dispatch(service,controlled,fault):
    wb,client=service;_,draft=sources(client,outside=fault=='outside');controlled['fault']=fault
    doc,job,result=run(client,draft)
    assert result['execution_status']=='FAILED' and not result['responses'],result
    assert controlled['calls']==[('thermal',0.),('thermal',2.)]
    assert result['stages'][-1]['dispatched'] is False and result['transfers'][0]['status']=='FAILED'
    view=client.evaluation_transfer(doc['id'],job,'TtoU',0)
    assert view['transfer_confirmation']=='FAILED' and view['unavailable'] and not view['exact_values_match']
    if fault=='outside':assert view['invalid_receiver_ids']
    doc=change(client,doc,'document.save')['document']
    assert client.evaluation_transfer(doc['id'],job,'TtoU',0)['transfer_confirmation']=='FAILED'
    assert client.evaluation_stage_result(doc['id'],job,result['stages'][0]['attempt_id'])['execution_status']=='SUCCEEDED'


def test_receiver_failure_and_new_attempt_leave_prior_exact_files(service,controlled):
    wb,client=service;_,draft=sources(client);controlled['fault']='receiver'
    doc,first,failed=run(client,draft)
    assert failed['execution_status']=='FAILED' and not failed['responses']
    assert failed['stages'][-1]['dispatched'] and failed['transfers'][0]['status']=='VALIDATED'
    assert client.evaluation_transfer(doc['id'],first,'TtoU',0)['exact_values_match']
    controlled['fault']=None
    second=change(client,doc,'evaluation.run')['job']['id'];wait(lambda:client.status(second)['state'] in TERMINAL)
    success=client.document_result(doc['id'],second)
    assert first!=second and success['execution_status']=='SUCCEEDED'
    assert client.document_result(doc['id'],first)==failed
    assert {r['attempt_id'] for r in failed['stages']}.isdisjoint({r['attempt_id'] for r in success['stages']})


def test_late_producer_cancel_never_starts_next_snapshot(service,controlled):
    wb,client=service;_,draft=sources(client);controlled['block']=True
    doc=client.document_open(kind='evaluation',draft=draft)
    job=change(client,doc,'evaluation.run')['job']['id']
    try:
        assert controlled['started'].wait(5)
        client.cancel(job)
    finally:
        controlled['release'].set()
    wait(lambda:client.status(job)['state'] in TERMINAL)
    result=client.document_result(doc['id'],job)
    assert result['execution_status']=='CANCELLED' and controlled['calls']==[('thermal',0.)]
    assert result['stages'][0]['state']=='SUCCEEDED' and not result['responses']
    assert client.evaluation_stage_result(doc['id'],job,result['stages'][0]['attempt_id'])['responses']['temperature']['value']


def test_invalid_dimensioned_draft_save_check_and_repair_zero_solve(service,controlled):
    wb,client=service
    s=domain.default_settings(domain.WEAK);s['forms']['linear']='unknown*v'
    doc=client.document_open(kind='pde',draft={'backend':domain.WEAK,'settings':s})
    assert doc['diagnostics'] and not wb.manager.list()
    saved=change(client,doc,'document.save')['document']
    assert saved['draft']['settings']['forms']['linear']=='unknown*v'
    assert client.document_read(doc['id'])['diagnostics'] and not wb.manager.list()
    s['forms']['linear']='q*v'
    repaired=change(client,saved,'pde.update',{'draft':{'backend':domain.WEAK,'settings':s}})['document']
    assert not repaired['diagnostics'] and not wb.manager.list() and not controlled['calls']


def test_explicit_successful_prefix_reuse_new_mapping_and_no_drift(service,controlled):
    wb,client=service;_,draft=sources(client);controlled['fault']='receiver'
    doc,first,failed=run(client,draft)
    doc=change(client,doc,'document.save')['document']
    ref=client.document_result_reference(doc['id'],first)
    draft['reuse']={'source':ref,'stages':['Start','End']}
    doc=change(client,doc,'evaluation.update',{'draft':draft})['document']
    controlled['fault']=None;before=len(controlled['calls'])
    second=change(client,doc,'evaluation.run')['job']['id'];wait(lambda:client.status(second)['state'] in TERMINAL)
    result=client.document_result(doc['id'],second)
    assert result['execution_status']=='SUCCEEDED',result
    assert controlled['calls'][before:]==[('structural',1.)]
    assert all(r.get('reused_from')==ref for r in result['stages'][:2])
    assert client.evaluation_transfer(doc['id'],second,'TtoU',0)['exact_values_match']
    draft['transfers'][0]['options']['target_unit']='degC' # No silent normalization of a drifted definition.
    current=client.document_read(doc['id']);edited=change(client,current,'evaluation.update',{'draft':draft})['document']
    assert edited['diagnostics']
    count=len(wb.manager.list())
    with pytest.raises(Exception):change(client,edited,'evaluation.run')
    assert len(wb.manager.list())==count


def test_cancellation_during_mapping_keeps_receipt_but_receiver_calls_zero(service,controlled,monkeypatch):
    wb,client=service;_,draft=sources(client)
    original=t.map_temperature
    def late(*a,**kw):
        mapped=original(*a,**kw)
        live=[r for r in wb.manager.list() if r['state']=='RUNNING']
        assert len(live)==1
        wb.manager.cancel(live[0]['id'])
        return mapped
    monkeypatch.setattr(t,'map_temperature',late)
    doc,job,result=run(client,draft)
    assert result['execution_status']=='CANCELLED'
    assert controlled['calls']==[('thermal',0.),('thermal',2.)]
    assert result['transfers'][0]['status']=='VALIDATED' and result['stages'][-1]['dispatched'] is False
    view=client.evaluation_transfer(doc['id'],job,'TtoU',0)
    assert len(view['rows'])==12 and all(r['received'] is None for r in view['rows'])


@pytest.mark.parametrize('damage',['missing','changed'])
def test_damaged_receipt_is_never_recomputed_or_repaired(service,controlled,damage):
    wb,client=service;_,draft=sources(client);doc,job,result=run(client,draft)
    from caelab.research_workflows import result_folder
    folder,_=result_folder(wb,doc['id'],job)
    path=folder/result['transfers'][0]['receipt_path'];before=list(controlled['calls'])
    if damage=='missing':path.unlink()
    else:path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(Exception):client.evaluation_transfer(doc['id'],job,'TtoU',0)
    assert controlled['calls']==before
    if damage=='missing':assert not path.exists()
