"""Real Client/strict HTTP/CLI parity, no new service type or buffers in POST."""
from contextlib import contextmanager
from copy import deepcopy
import http.client
import json
from pathlib import Path
import subprocess
import sys
import threading
import pytest
from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from caelab.workbench_client import Client, WorkbenchHTTPError
from caelab.portable_recovery_resume import buffer_token
from caelab.storage import load_json,save_json
from examples.portable_connection_c3a_public import create_case,make_copy
from _portable_connection_c2_support import cold_guard


@contextmanager
def serving(folder):
    service=LabService(folder);server=None;thread=None
    try:
        server=LabHTTPServer(service,port=0)
        thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
        yield server,Client('http://127.0.0.1:'+str(server.server_port))
    finally:
        if server:
            if thread and thread.is_alive():server.shutdown()
            server.server_close()
        service.shutdown()
        if thread:thread.join(5);assert not thread.is_alive()


def test_http_cold_read_preview_same_command_resume_strict_fields_cli(tmp_path):
    wb,case=create_case(tmp_path/'source')
    try:make_copy(wb,case,tmp_path/'copy')
    finally:wb.shutdown()
    import shutil
    shutil.rmtree(tmp_path/'source')
    with cold_guard() as calls, serving(tmp_path/'copy') as (server,client):
        rows=load_json(tmp_path/'copy/portable-project.json')['recovery_archives']
        ids=[r['document_id'] for r in rows]
        catalog=client.portable_recovery_catalog(ids)
        assert len(catalog['archives'])==4 and not catalog['unkept_buffers_included']
        row=next(r for r in rows if r['original_identity']['kind']=='data')
        layers=client.portable_recovery_read(row['archive_id'])
        assert layers['capsule']['raw']['cells'][0]['raw_text']=='1e'
        doc=client.document_read(row['document_id'])
        identity=client.data_material('recovery.identity',{'document_id':doc['id']})
        token=buffer_token({'cells':[],'editor_revision':'Uhttp','local_draft':doc['draft']})
        preview=client.portable_recovery_preview(row['archive_id'],target_identity=identity,buffer=token)
        request=dict(preview=preview,approved=True,overwrite_approved=True,live_buffer=token,command_id=preview['command_id'])
        result=client.portable_recovery_resume(**request)
        assert result==client.portable_recovery_resume(**request)
        assert result['state']=='BUFFER_READY' and not result['raw_applied']
        for body in ({'document_ids':ids,'collect_widgets':True},{'document_ids':ids,'recover_permission':'GRANTED'}):
            with pytest.raises(WorkbenchHTTPError):client.request('/api/workbench/portable-project/recovery-catalog',body)
        with pytest.raises(WorkbenchHTTPError):
            client.portable_recovery_resume(**{**request,'live_buffer':{**token,'raw_sha256':'f'*64}})
        # Real loopback body cap, no giant JSON allocation/no source bytes upload.
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
        try:
            connection.putrequest('POST','/api/workbench/portable-project/recovery-preview')
            connection.putheader('Content-Type','application/json')
            connection.putheader('X-CAE-Token',client.token)
            connection.putheader('Content-Length',str(128*1024+1));connection.endheaders()
            assert connection.getresponse().status==413
        finally:connection.close()
        path=tmp_path/'read-request.json';save_json(path,{'archive_id':row['archive_id'],'facet':'layers','selection':None})
        process=None
        try:
            process=subprocess.Popen([sys.executable,'-B','-m','caelab.portable_recovery_commands','read','--service',client.url,
                '--request',str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
            output,error=process.communicate(timeout=20)
            assert process.returncode==0,error
            assert json.loads(output)['capsule']==layers['capsule']
        finally:
            if process:
                if process.poll() is None:process.kill()
                process.wait(timeout=5)
                if process.stdout:process.stdout.close()
                if process.stderr:process.stderr.close()
        assert calls==[] and server.workbench.manager.list()==[] and server.workbench._assistance is None
