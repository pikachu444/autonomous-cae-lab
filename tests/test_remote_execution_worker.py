"""Real existing external-files adapter with a tiny public file-writing process.

This is neither a remote-host run nor an engineering solver qualification.
"""
import json
import sys
import pytest

from caelab import numerical
from caelab.remote_execution import worker,digest


def test_worker_reuses_external_adapter_and_keeps_case_values_exchange(tmp_path):
    manifest=numerical.export_batch([{'id':'x','unit':'1','lower':0.,'upper':4.}],
        [{'x':1.},{'x':3.}],tmp_path/'export',case_id='public')
    raw=json.dumps(manifest,allow_nan=False).encode(); batch=tmp_path/'batch.json'; batch.write_bytes(raw)
    script="from pathlib import Path; import json; x=json.loads(Path('candidate.json').read_text())['values']['x']; Path('response.csv').write_text('time,force\\n0,'+str(2*x)+'\\n1,'+str(3*x)+'\\n')"
    config={'command':[sys.executable,'-c',script], 'variables':{'x':{'lower':0.,'upper':4.}},
        'result':{'path':'response.csv','delimiter':',','columns':{
            'force':{'column':'force','unit':'N','component':'axial','location':'public-point',
                'axis':{'column':'time','name':'time','unit':'s'}}}}}
    path=tmp_path/'external.json'; path.write_text(json.dumps(config),encoding='utf-8')
    result=worker(batch,path,{'id':'public.external','version':'fixture-1'},output=tmp_path/'results.json')
    assert result['input_manifest_sha256']==digest(raw)
    table=numerical.import_batch(manifest,result['results'])
    assert table['missing_count']==0
    retained=json.loads((tmp_path/'results.json').read_text(encoding='utf-8'))
    assert retained['results'][0]['responses']['force']['value']==[2.,3.]
    assert all(row['execution_status']=='SUCCEEDED' for row in table['candidates'])
    assert len(list((tmp_path/'candidates').glob('*/external.execution.json')))==2


@pytest.mark.parametrize('cleanup_ok',[True,False])
def test_worker_cancellation_receipt_binds_token_intent_and_existing_cleanup(tmp_path,monkeypatch,cleanup_ok):
    from caelab import remote_execution as remote
    from caelab.execution_control import ExecutionCancelled,ExecutionCleanupFailed,_current
    from caelab.storage import load_json,save_json
    folder=tmp_path/('R'+'2'*32);folder.mkdir();batch=folder/'batch.json';batch.write_bytes(b'{}')
    runtime={'id':'public.external','version':'fixture-1'}
    intent={'runtime':runtime,'batch_sha256':digest(b'{}'),'resources':{'threads':1}};save_json(folder/'.cae-intent.json',intent)
    def interrupted(*args,**kwargs):
        token=_current.get();assert token is not None;token.request()
        if not cleanup_ok: raise ExecutionCleanupFailed('CONTROLLED unconfirmed native child')
        token.check()
    monkeypatch.setattr(remote,'_worker',interrupted)
    with pytest.raises(ExecutionCancelled if cleanup_ok else ExecutionCleanupFailed):
        remote.worker(batch,folder/'operator-config.json',runtime,output=folder/'results.json')
    receipt=load_json(folder/'.cae-runtime-exit.json')
    assert receipt['token']==folder.name and receipt['intent_sha256']==remote.fingerprint(intent)
    assert receipt['cleanup_confirmed'] is cleanup_ok
