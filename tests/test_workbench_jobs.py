import asyncio
import json
import os
from pathlib import Path
import sys
import threading
import time
import pytest
from caelab.jobs import JobManager
from caelab.execution_control import check_cancelled
from caelab.workbench import Workbench


@pytest.fixture(autouse=True)
def isolate_registered_backends(monkeypatch):
    from caelab import backends
    monkeypatch.setattr(backends,'_registry',dict(backends._registry))


def finished(manager,identifier):
    for _ in range(300):
        job=manager.status(identifier)
        if job['state'] in {'SUCCEEDED','FAILED','PARTIAL_FAILURE','CANCELLED','INTERRUPTED'}:
            return job
        time.sleep(.01)
    raise AssertionError('job did not finish')


def test_idempotency_parallel_cancel_and_restart(tmp_path):
    barrier=threading.Barrier(2)
    def execute(operation,arguments,identifier):
        if operation=='parallel':
            barrier.wait(timeout=2)
        if operation=='wait':
            while True:
                check_cancelled();time.sleep(.01)
        return {'value':arguments['value']}
    manager=JobManager(tmp_path,execute,workers=2,cpu_budget=2)
    try:
        a=manager.submit('parallel',{'value':1},request_id='one')
        assert manager.submit('parallel',{'value':1},request_id='one')['id']==a['id']
        with pytest.raises(ValueError,match='conflict'):
            manager.submit('parallel',{'value':2},request_id='one')
        b=manager.submit('parallel',{'value':2})
        assert finished(manager,a['id'])['state']=='SUCCEEDED'
        assert finished(manager,b['id'])['state']=='SUCCEEDED'
        c=manager.submit('wait',{'value':3})
        manager.cancel(c['id'])
        assert finished(manager,c['id'])['state']=='CANCELLED'
        with pytest.raises(RuntimeError,match='controller'):
            JobManager(tmp_path,execute)
    finally:
        assert manager.shutdown()['joined']
    manager=JobManager(tmp_path,execute)
    try:
        assert manager.result(a['id'])['value']==1
        assert manager.submit('parallel',{'value':1},request_id='one')['id']==a['id']
    finally:
        manager.shutdown()


def test_owned_external_program_and_failure_preserve_files(tmp_path):
    from caelab.adapters.external_files import register_external_backend
    from caelab import run
    template=tmp_path/'template.txt';template.write_text('$load')
    config={'variables':{'load':{'lower':0,'upper':100,'unit':'N'}},
            'templates':[{'source':str(template),'destination':'load.txt'}],
            'command':[sys.executable,'-c',"from pathlib import Path; x=float(Path('load.txt').read_text());Path('output.csv').write_text('t,f\\n0,0\\n1,'+str(x)+'\\n')"],
            'result':{'path':'output.csv','columns':{'force':{'column':'f','unit':'N','component':'y','location':'support',
                       'axis':{'column':'t','name':'time','unit':'s'}}}}}
    register_external_backend('test.external.program',config)
    result=run('test.external.program',{'values':{'load':12}},output=tmp_path/'first')
    assert result['responses']['force']['value'].tolist()==[0,12]
    assert result['diagnostics']['solver_execution']=='COMPLETED'
    config['command']=[sys.executable,'-c','raise SystemExit(2)']
    register_external_backend('test.external.failure',config)
    with pytest.raises(Exception):
        run('test.external.failure',{'values':{'load':12}},output=tmp_path/'failed')
    assert (tmp_path/'failed/external.execution.json').is_file()


def test_http_and_actual_stdio_share_job(tmp_path):
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.workbench_client import Client
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    service=LabService(tmp_path/'workspace')
    server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    client=Client(f'http://127.0.0.1:{server.server_port}')
    source=server.workbench.upload('data.csv',b't,y\n0,1\n1,3\n')
    mapping={'columns':{'y':{'column':'y','unit':'N','component':'y','location':'support','axis':{'column':'t','name':'time','unit':'s'}}}}
    async def exercise():
        params=StdioServerParameters(command=sys.executable,args=['-m','openscience.workbench_mcp'],
                    env={**os.environ,'CAELAB_SERVICE_URL':client.url})
        async with stdio_client(params) as (reader,writer):
            async with ClientSession(reader,writer) as session:
                await session.initialize()
                names={tool.name for tool in (await session.list_tools()).tools}
                assert {'calculation_submit','job_status','job_cancel','result_read'}<=names
                response=await session.call_tool('job_status',{'job_id':job['id']})
                assert not response.isError
                data=response.structuredContent or json.loads(response.content[0].text)
                assert data['job_id']==job['id']
                response=await session.call_tool('result_read',{'job_id':job['id']})
                assert not response.isError
                assert (response.structuredContent or json.loads(response.content[0].text))['responses']['y']['value']==[1,3]
    try:
        job=client.submit('import_table',{'data_id':source['id'],'mapping':mapping},request_id='http-first')
        assert finished(server.workbench.manager,job['id'])['state']=='SUCCEEDED'
        asyncio.run(exercise())
        with pytest.raises(ValueError):
            server.workbench._settings('files.table',{'path':'/etc/passwd'})
        same=client.submit('import_table',{'data_id':source['id'],'mapping':mapping},request_id='http-first')
        assert same['id']==job['id']
    finally:
        server.shutdown();server.server_close();service.shutdown();thread.join()


def test_access_boundary_and_controller_conflict(tmp_path,monkeypatch):
    from openscience import jobs as legacy
    from apps.lab.service import ServiceError
    workbench=Workbench(tmp_path)
    try:
        with pytest.raises(ValueError,match='operator-owned'):
            workbench.submit('evaluate',{'backend':'files.table','runtime':{'command':'anything'}})
        with pytest.raises(ValueError,match='registered'):
            workbench.submit('shell',{'command':'anything'})
        source=workbench.upload('data.csv',b't,y\n0,1\n1,2\n')
        path=workbench.input_path(source['id']);path.write_text('changed')
        with pytest.raises(ValueError,match='changed'):
            workbench.input_path(source['id'])
        with pytest.raises(ValueError):
            workbench.input_path('../private')
        monkeypatch.setenv('CAELAB_STORE',str(tmp_path))
        monkeypatch.setattr(legacy,'_resident',None)
        with pytest.raises(ServiceError,match='controller'):
            legacy._service()
        monkeypatch.setenv('CAELAB_SERVICE_URL','http://127.0.0.1:8766')
        with pytest.raises(ServiceError,match='second resident'):
            legacy._service()
    finally:
        workbench.shutdown()


def test_real_owned_process_cancellation_retains_lifecycle(tmp_path):
    from caelab.execution_control import run_owned_command
    marker=tmp_path/'started'
    def execute(operation,arguments,identifier):
        output=tmp_path/'native';output.mkdir()
        run_owned_command([sys.executable,'-c',"from pathlib import Path;import time;Path('../started').write_text('owned');time.sleep(30)"],output,'cancel-check')
        return {'unexpected':'completed'}
    manager=JobManager(tmp_path/'control',execute)
    try:
        job=manager.submit('owned',{})
        for _ in range(200):
            if marker.exists():break
            time.sleep(.01)
        assert marker.exists()
        manager.cancel(job['id'])
        assert finished(manager,job['id'])['state']=='CANCELLED'
        assert (tmp_path/'native/cancel-check.execution.json').is_file()
        assert not manager.status(job['id'])['result_refs']
    finally:
        assert manager.shutdown()['joined']


def test_spawned_external_candidate_cancellation_owns_child(tmp_path):
    config={'workers':1,'cpu_budget':2,'external_backends':{'test.slow.process':{
        'variables':{'x':{'lower':0,'upper':1}},
        'command':[sys.executable,'-c',"from pathlib import Path;import time;Path('started').write_text('owned');time.sleep(30);Path('result.csv').write_text('y\\n1\\n')"],
        'result':{'path':'result.csv','columns':{'y':{'column':'y','unit':'1','component':'scalar','location':'model'}}}}}}
    wb=Workbench(tmp_path,configuration=config)
    try:
        job=wb.submit('doe',{'backend':'test.slow.process','variables':[{'id':'x','lower':0,'upper':1,'unit':'1'}],
                            'count':1,'execution':{'mode':'process','workers':1}})
        for _ in range(500):
            if list(wb.root.glob('native/*/*/started')):break
            time.sleep(.02)
        assert list(wb.root.glob('native/*/*/started'))
        wb.manager.cancel(job['id'])
        assert finished(wb.manager,job['id'])['state']=='CANCELLED'
        receipts=[json.loads(p.read_text()) for p in wb.root.glob('native/*/*/external.execution.json')]
        assert len(receipts)==1 and receipts[0]['status']=='CANCELLED'
        assert not list(wb.root.glob('native/*/*/result.csv'))
    finally:
        assert wb.shutdown()['joined']


def test_remote_fit_rejects_observation_path(tmp_path):
    wb=Workbench(tmp_path)
    try:
        job=wb.submit('fit',{'backend':'material.felupe','variables':[],
            'experiments':[{'settings':{},'observations':{'path':'/server/private.csv'}}]})
        end=finished(wb.manager,job['id'])
        assert end['state']=='FAILED'
        assert 'uploaded result' in end['error']['message']
    finally:
        wb.shutdown()


def test_partial_failure_and_native_thread_reservation(tmp_path,monkeypatch):
    manager=JobManager(tmp_path/'partial',lambda *args:{'execution_status':'PARTIAL_FAILURE','candidates':[]})
    try:
        job=manager.submit('doe',{})
        assert finished(manager,job['id'])['state']=='PARTIAL_FAILURE'
    finally:
        manager.shutdown()
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
        monkeypatch.setenv(name,'1')
    wb=Workbench(tmp_path/'native',configuration={'workers':1,'cpu_budget':1})
    try:
        with pytest.raises(ValueError,match='CPU budget'):
            wb.submit('run',{'backend':'explicit.openradioss','settings':{}})
    finally:
        wb.shutdown()


def test_existing_declared_native_binding_joins_managed_doe(tmp_path):
    from test_model_parameters import SyntheticParameterizedModel,template_settings
    from caelab.backends import register_backend
    adapter=SyntheticParameterizedModel()
    register_backend('test.native.binding',lambda:adapter,roles=('model',),replace=True)
    wb=Workbench(tmp_path)
    try:
        variables=[{'id':'input_x','unit':'1','lower':0,'upper':4,'value':1}]
        job=wb.submit('doe',{'backend':'test.native.binding','variables':variables,'settings':template_settings(),
                            'candidates':[{'input_x':.5},{'input_x':1.5}]})
        assert finished(wb.manager,job['id'])['state']=='SUCCEEDED'
        result=wb.manager.result(job['id'])
        assert len(result['candidates'])==2 and adapter.calls==2
        assert all(row['diagnostics']['evaluation_mode']=='FILE_BASED_NATIVE' for row in result['candidates'])
        assert len(list(wb.root.glob('native/*/*/simulation/raw.log')))==2
    finally:
        wb.shutdown()


def test_external_backend_configuration_is_workspace_local(tmp_path):
    definition={'command':[sys.executable,'-c','pass'],'variables':{},'result':{'path':'result.csv','columns':{}}}
    first=Workbench(tmp_path/'first',configuration={'external_backends':{'company.local':definition}})
    second=Workbench(tmp_path/'second')
    try:
        assert 'company.local' in {row['id'] for row in first.backends()}
        assert 'company.local' not in {row['id'] for row in second.backends()}
        with pytest.raises(ValueError,match='not registered'):
            second.submit('run',{'backend':'company.local','settings':{}})
    finally:
        first.shutdown();second.shutdown()


def test_registered_callable_remains_an_in_memory_managed_evaluator(tmp_path):
    from caelab.backends import register_backend
    def function(values,settings):
        return {'execution_status':'SUCCEEDED','responses':{'cost':{'kind':'scalar','unit':'1','value':values['x']**2}}}
    register_backend('test.callable.managed',lambda:function,roles=('prepared',))
    wb=Workbench(tmp_path)
    try:
        job=wb.submit('doe',{'backend':'test.callable.managed',
            'variables':[{'id':'x','unit':'1','lower':0,'upper':1,'value':.5}], 'candidates':[{'x':.2},{'x':.8}]})
        assert finished(wb.manager,job['id'])['state']=='SUCCEEDED'
        result=wb.manager.result(job['id'])
        assert [r['responses']['cost']['value'] for r in result['candidates']]==pytest.approx([.04,.64])
        assert not (wb.root/'native').exists()
    finally:
        wb.shutdown()
