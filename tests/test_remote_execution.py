"""Controlled SSH boundary, real JobManager/exchange/retention; no remote host."""
import base64
from copy import deepcopy
import json
import time

import pytest
from caelab import remote_execution as remote
from caelab.evaluation import file_hash
from caelab.jobs import TERMINAL
from caelab.storage import load_json, save_json
from caelab.workbench import Workbench


def host():
    return {'enabled':True,'label':'공개 계산 서버', 'target':'public-fixture.invalid',
        'scheduler':'slurm','root':'/public/jobs','queue':'research','account':'public',
        'python':'python3','command':['python3','existing-worker.py'],
        'runtime':{'id':'public.external','version':'fixture-1'},
        'responses':{'force':{'kind':'scalar','unit':'N'}},
        'max_threads':4,'max_memory_mb':4096,'max_wall_seconds':3600,
        'monitor_seconds':1,'cancel_seconds':1,'poll_seconds':.05}


def wait(wb, job):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        value=wb.manager.status(job['id'])
        if value['state'] in TERMINAL or value['state']=='CLEANUP_PENDING': return value
        time.sleep(.005)
    raise AssertionError('Controlled job did not finish')


class ControlledSSH:
    def __init__(self):
        self.calls=[]; self.payload=None; self.lost=False; self.submitted=False
        self.terminated=True; self.state='COMPLETED'; self.mutate=None; self.extra={}
    def request(self, action, payload, folder):
        self.calls.append(action); self.payload=payload
        receipt={'scheduler_id':'731','state':self.state if self.terminated else 'RUNNING',
            'terminated':self.terminated,'exit_code':'0:0' if self.terminated else None,
            'termination_confirmation':'SCHEDULER_ACCOUNTING' if self.terminated else None}
        if action=='prepare':
            self.manifest=json.loads(base64.b64decode(payload['files']['batch.json']['base64']))
            return {'state':'PREPARED','input_sha256':payload['intent']['files'],'terminated':False}
        if action=='submit':
            assert not self.submitted; self.submitted=True
            if self.lost: raise OSError('CONTROLLED response lost after accepted submit')
            return dict(receipt,terminated=False,state='SUBMITTED')
        if action=='cancel':
            self.state='CANCELLED'; self.terminated=True
            return dict(receipt,state='CANCELLED',terminated=True,termination_confirmation='SCHEDULER_ACCOUNTING')
        if action=='query': return receipt
        if action=='fetch':
            assert self.terminated
            rows=[{**deepcopy(row),'execution_status':'SUCCEEDED',
                'responses':{'force':{'kind':'scalar','unit':'N','value':row['values']['x']*2}}}
                for row in self.manifest['candidates']]
            if self.mutate: self.mutate(rows)
            raw=json.dumps({'input_manifest_sha256':payload['intent']['batch_sha256'],
                'runtime':payload['intent']['runtime'],'results':rows},allow_nan=False).encode()
            files={'results.json':raw,**self.extra}
            return dict(receipt,input_sha256=payload['intent']['files'],files={name:{
                'base64':base64.b64encode(data).decode(),'sha256':remote.digest(data)} for name,data in files.items()})
        raise AssertionError(action)


@pytest.fixture
def setup(tmp_path,monkeypatch):
    ssh=ControlledSSH()
    monkeypatch.setattr('caelab.remote_transport.SSHTransport',lambda config:ssh)
    configuration={'remote_hosts':{'public':host()}}
    wb=Workbench(tmp_path/'store',configuration=configuration)
    job=wb.submit('batch_export',{'variables':[{'id':'x','unit':'1','lower':0.,'upper':4.}],
        'candidates':[{'x':1.},{'x':3.}], 'case_id':'public-case','label':'공개 하중 비교'})
    wait(wb,job)
    try: yield wb,ssh,job['id'],configuration
    finally: wb.shutdown()


def run(wb,batch):
    job=wb.submit('remote.run',{'host_id':'public','batch_job':batch},request_id='stable-submit')
    return wait(wb,job)


def action(wb,operation,source,request='action'):
    return wait(wb,wb.submit('remote.'+operation,{'source_job':source},request_id=request))


def test_pure_inspection_and_local_work_do_not_connect(setup):
    wb,ssh,batch,_=setup
    assert remote.catalog(wb)['hosts'][0]['label']=='공개 계산 서버'
    review=remote.inspect(wb,'public',batch)
    assert review['resources']['threads']==1 and review['network_calls']==0 and ssh.calls==[]
    wb.config.pop('remote_hosts')
    assert remote.catalog(wb)['hosts']==[]
    local=wb.submit('batch_import',{'batch_job':batch,'results':[]})
    assert wait(wb,local)['state']=='SUCCEEDED'
    assert wb.result(local['id'])['missing_count']==2


def test_submit_query_collect_and_reader_are_separate(setup):
    wb,ssh,batch,_=setup
    job=run(wb,batch); assert job['state']=='SUCCEEDED'
    assert ssh.calls==['prepare','submit','query']
    assert remote.status(wb,job['id'])['terminated'] is True
    before=list(ssh.calls)
    again=wb.submit('remote.run',job['arguments'],request_id='stable-submit')
    assert again['id']==job['id'] and ssh.calls==before
    queried=action(wb,'reconnect',job['id'])
    assert ssh.calls[-1]=='query' and 'fetch' not in ssh.calls
    result=action(wb,'collect',queried['id'],'collect')
    assert result['state']=='SUCCEEDED'
    saved=wb.result(result['id'])
    assert saved['table']['imported_count']==2 and saved['table']['missing_count']==0
    assert saved['responses']['후보 1 / force']['value']==2.
    assert len(saved['candidates'])==2 and saved['diagnostics']['decision']=='NOT_RELEASED'


def test_lost_submit_cold_reconnect_never_submits_again(setup):
    wb,ssh,batch,config=setup; ssh.lost=True
    original=run(wb,batch); assert original['state']=='FAILED'
    workspace=wb.workspace; before=file_hash(wb.root/'results'/original['id']/'inputs'/'batch.json')
    wb.shutdown(); reopened=Workbench(workspace,configuration=config)
    try:
        assert remote.catalog(reopened)['attempts']
        recovered=action(reopened,'reconnect',original['id'],'cold-query')
        assert recovered['state']=='SUCCEEDED'
        assert ssh.calls.count('submit')==1 and 'fetch' not in ssh.calls
        result=action(reopened,'collect',recovered['id'],'cold-collect')
        assert result['state']=='SUCCEEDED' and ssh.calls.count('submit')==1
        assert file_hash(reopened.root/'results'/original['id']/'inputs'/'batch.json')==before
    finally: reopened.shutdown()


@pytest.mark.parametrize('mutation',[lambda rows:rows.append(deepcopy(rows[0])),
    lambda rows:rows[0].update(exchange_id='stale'),lambda rows:rows[0]['values'].update(x=2.),
    lambda rows:rows[0]['responses']['force'].update(unit='Pa'),
    lambda rows:rows[0]['responses']['force'].update(value={'data_ref':{'path':'outside.npy'}})])
def test_invalid_remote_rows_rejected_but_exact_outputs_preserved(setup,mutation):
    wb,ssh,batch,_=setup; original=run(wb,batch); ssh.mutate=mutation
    result=action(wb,'collect',original['id'])
    assert result['state']=='FAILED'
    assert (wb.root/'results'/result['id']/'recovered'/'results.json').is_file()
    assert wb.result(result['id'])['responses']=={}


def test_missing_and_failed_rows_never_improve_the_candidate(setup):
    wb,ssh,batch,_=setup; original=run(wb,batch)
    def change(rows):
        rows.pop(); rows[0].update(execution_status='FAILED',responses={},failure_reason='actual nonconvergence')
    ssh.mutate=change; result=action(wb,'collect',original['id'])
    saved=wb.result(result['id'])
    assert result['state']=='FAILED' and saved['table']['missing_count']==1
    assert [row['execution_status'] for row in saved['candidates']]==['FAILED','NOT_EVALUATED']


def test_unconfirmed_termination_blocks_fetch_then_explicit_cancel(setup):
    wb,ssh,batch,_=setup; ssh.terminated=False
    original=run(wb,batch); assert original['state']=='FAILED'
    collected=action(wb,'collect',original['id']); assert collected['state']=='FAILED'
    assert 'fetch' not in ssh.calls
    cancelled=action(wb,'cancel',original['id'],'cancel')
    assert cancelled['state']=='CANCELLED' and 'fetch' not in ssh.calls


@pytest.mark.parametrize('operation',['reconnect','collect'])
@pytest.mark.parametrize('source_state',['RUNNING','PREPARING'])
def test_local_query_or_transfer_cancel_never_cancels_or_terminates_remote_job(setup,operation,source_state):
    from caelab.execution_control import ExecutionCancelled
    wb,ssh,batch,_=setup;ssh.terminated=False;original=run(wb,batch)
    path=wb.root/'results'/original['id']/'remote.json';record=load_json(path);record['state']=source_state;save_json(path,record)
    before=len(ssh.calls);previous=ssh.request
    def cancelled(action,payload,folder):
        if action=='query':ssh.calls.append(action);raise ExecutionCancelled('CONTROLLED local observation cancelled')
        return previous(action,payload,folder)
    ssh.request=cancelled
    result=action(wb,operation,original['id'])
    assert result['state']=='CANCELLED' and ssh.calls[before:]==['query']
    saved=wb.result(result['id'])
    assert saved['remote']['terminated'] is False and not saved['remote'].get('cancel_requested')
    assert saved['remote']['state']==source_state


@pytest.mark.parametrize('key,value',[('token','R'+'f'*32),('batch_job','Jwrong'),('origin_job','Jwrong')])
def test_retained_identity_tamper_blocks_before_network(setup,key,value):
    wb,ssh,batch,_=setup; original=run(wb,batch)
    path=wb.root/'results'/original['id']/'remote.json'; record=load_json(path); record[key]=value; save_json(path,record)
    before=list(ssh.calls)
    with pytest.raises((ValueError,KeyError,FileNotFoundError)):
        wb.submit('remote.reconnect',{'source_job':original['id']},request_id='tamper')
    assert ssh.calls==before


def test_config_resources_and_request_identity_are_admitted(setup):
    wb,ssh,batch,_=setup
    with pytest.raises(ValueError,match='request_id'):
        wb.submit('remote.run',{'host_id':'public','batch_job':batch})
    with pytest.raises(ValueError,match='budget'):
        remote.inspect(wb,'public',batch,{'threads':5})
    wb.config['remote_hosts']['public']['password']='must not be read'
    with pytest.raises(ValueError,match='credentials'): remote.host_configuration(wb,'public')
    assert ssh.calls==[]


def test_typed_integer_and_category_source_is_not_reinterpreted(setup):
    wb,ssh,_,_=setup
    declarations=[{'id':'x','unit':'1','kind':'integer','lower':1,'upper':3},
        {'id':'material','unit':'1','kind':'categorical','choices':[
            {'id':'a','label':'재료 A','value':'steel'},{'id':'b','label':'재료 B','value':'alloy'}]}]
    batch=wb.submit('batch_export',{'variables':declarations,'candidates':[{'x':1,'material':'steel'},
        {'x':3,'material':'alloy'}],'case_id':'typed-public'})
    assert wait(wb,batch)['state']=='SUCCEEDED'
    original=run(wb,batch['id']); collected=action(wb,'collect',original['id'])
    result=wb.result(collected['id'])
    assert collected['state']=='SUCCEEDED'
    assert type(result['candidates'][0]['values']['x']) is int
    assert result['candidates'][0]['values']['material']=='steel'
    assert result['table']['domain_input']==wb.result(batch['id'])['manifest']['domain_input']


VTU=b'''<?xml version="1.0"?><VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian"><UnstructuredGrid><Piece NumberOfPoints="1" NumberOfCells="1"><Points><DataArray type="Float64" NumberOfComponents="3" format="ascii">0 0 0</DataArray></Points><Cells><DataArray type="Int32" Name="connectivity" format="ascii">0</DataArray><DataArray type="Int32" Name="offsets" format="ascii">1</DataArray><DataArray type="UInt8" Name="types" format="ascii">1</DataArray></Cells><PointData><DataArray type="Float64" Name="force" format="ascii">2</DataArray></PointData></Piece></UnstructuredGrid></VTKFile>'''


@pytest.mark.parametrize('second_missing',[False,True])
def test_explicit_spatial_outputs_reuse_native_registration_and_navigation(setup,second_missing):
    wb,ssh,batch,_=setup
    config=wb.config['remote_hosts']['public']
    config['outputs']=['public.vtu','second.vtu']
    metadata={'coordinate_units':'mm','coordinate_frame':'global','arrays':[
        {'name':'force','units':'N','association':'POINTS','components':1,'frame':'global',
        'measure':'CONTROLLED_PUBLIC_FIXTURE'}], 'static':{'step':1,'increment':1,'load_parameter':1.}}
    config['post_outputs']=[{'relative':name,'native_metadata':metadata} for name in config['outputs']]
    ssh.extra={'public.vtu':VTU}
    if not second_missing: ssh.extra['second.vtu']=VTU
    original=run(wb,batch); collected=action(wb,'collect',original['id'])
    result=wb.result(collected['id']);navigation=wb.desktop.navigation(collected['id'])
    assert len(navigation['post_inputs'])==(1 if second_missing else 2)
    assert (wb.root/'results'/collected['id']/'recovered'/'public.vtu').read_bytes()==VTU
    assert result['responses']['후보 1 / force']['unit']=='N'
    if second_missing:
        assert collected['state']=='FAILED' and result['post_registration']['status']=='FAILED'
        assert navigation['post_input'] is None
    else:
        assert collected['state']=='SUCCEEDED' and navigation['post_input']
        assert wb.native_input(navigation['post_input']['id'])['native_metadata']==metadata
