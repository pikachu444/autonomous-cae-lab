"""Public scheduler fixtures and controlled helper commands; no SSH/scheduler run."""
import base64
from copy import deepcopy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from caelab import remote_schedulers as scheduler


TOKEN='R'+'1'*32
NAME='cae_'+TOKEN[1:11]


@pytest.mark.parametrize('kind,text,expected',[('slurm','731;public\n','731'),('pbs','731.public\n','731.public')])
def test_exact_submission_identity(kind,text,expected):
    assert scheduler.parse_submit(kind,text)==expected
    with pytest.raises(ValueError): scheduler.parse_submit(kind,'731;touch forbidden')


def test_slurm_accounting_is_required_and_steps_not_used():
    line=f'731|{NAME}|{TOKEN}|COMPLETED'
    assert not scheduler.parse_slurm(line,TOKEN)['terminated']
    assert scheduler.parse_slurm(line+'|0:0',TOKEN,accounting=True)['state']=='COMPLETED'
    assert scheduler.parse_slurm(line+'|1:0',TOKEN,accounting=True)['state']=='FAILED'
    assert not scheduler.parse_slurm(line.replace('731|','731.batch|')+'|0:0',TOKEN,accounting=True)['terminated']
    with pytest.raises(ValueError): scheduler.parse_slurm(line+'\n'+line.replace('731|','732|'),TOKEN)


def test_pbs_ended_is_not_termination_and_exact_job_and_token_required():
    row={'Job_Name':NAME,'Variable_List':{'CAELAB_SUBMISSION':TOKEN},'job_state':'E'}
    fixture=lambda value:json.dumps({'Jobs':{'731.public':value}})
    assert not scheduler.parse_pbs(fixture(row),TOKEN)['terminated']
    row.update(job_state='F',Exit_status=0)
    assert scheduler.parse_pbs(fixture(row),TOKEN,expected_id='731.public')['state']=='COMPLETED'
    assert not scheduler.parse_pbs(fixture(row),TOKEN,expected_id='732.public')['terminated']
    row['Variable_List']={'CAELAB_SUBMISSION':'different'}
    assert not scheduler.parse_pbs(fixture(row),TOKEN)['terminated']


def intent(kind='slurm'):
    return {'scheduler':kind,'queue':'public','account':'research','python':'python3',
        'command':['existing-solver','input.dat'], 'resources':{'threads':2,'memory_mb':512,'wall_seconds':61},
        'files':{'batch.json':scheduler.digest(b'{}')},'transfer_limit':1024,'outputs':['results.json']}


@pytest.mark.parametrize('kind',['slurm','pbs'])
def test_native_typed_argv_has_resources_and_no_shell(kind,tmp_path):
    argv=scheduler.submit_command(intent(kind),tmp_path,TOKEN)
    assert isinstance(argv,list) and str(tmp_path/'.cae-job.sh')==argv[-1]
    assert ('--parsable' in argv) if kind=='slurm' else ('-v' in argv)
    assert any('00:01:01' in item for item in argv)
    assert any('512' in item for item in argv)


@pytest.fixture
def helper(tmp_path,monkeypatch):
    # Execute actual filesystem protocol on Windows, with the POSIX scheduler boundary controlled.
    monkeypatch.setattr(scheduler,'os',SimpleNamespace(name='posix',getpid=os.getpid,replace=os.replace))
    value=intent(); payload={'base':str(tmp_path.resolve()),'token':TOKEN,'intent':value,
        'intent_sha256':scheduler.fingerprint(value)}
    def call(action,**extra): return scheduler.remote_request(dict(payload,action=action,**extra))
    call('prepare',files={'batch.json':{'base64':base64.b64encode(b'{}').decode()}})
    return call,tmp_path/TOKEN,payload


def test_response_loss_recovered_by_token_and_claim_never_repeats_submit(helper,monkeypatch):
    call,folder,_=helper; calls=[]
    def command(argv):
        calls.append(argv)
        if argv[0]=='sbatch': raise OSError('CONTROLLED response lost')
        if argv[0]=='squeue': return 0,f'731|{NAME}|{TOKEN}|RUNNING\n'
        raise AssertionError(argv)
    monkeypatch.setattr(scheduler,'_call',command)
    with pytest.raises(OSError): call('submit')
    assert call('submit')['scheduler_id']=='731'
    assert len([argv for argv in calls if argv[0]=='sbatch'])==1
    assert call('query')['state']=='RUNNING'
    assert json.loads((folder/'.cae-submission.json').read_text())['recovered_by_token']


def test_cancel_wins_before_submit_atomically(helper,monkeypatch):
    call,_,_=helper
    monkeypatch.setattr(scheduler,'_call',lambda argv:pytest.fail('A cancelled claim cannot submit'))
    state=call('cancel')
    assert state['terminated'] and state['termination_confirmation']=='SUBMISSION_ATOMICALLY_BLOCKED'
    assert call('submit')['state']=='CANCELLED'


def test_terminal_queue_receipt_still_queries_accounting_before_fetch(helper,monkeypatch):
    call,folder,_=helper; commands=[]
    def command(argv):
        commands.append(argv)
        if argv[0]=='sbatch': return 0,'731'
        if argv[0]=='squeue': return 0,f'731|{NAME}|{TOKEN}|COMPLETED\n'
        if argv[0]=='sacct': return 0,f'731|{NAME}|{TOKEN}|COMPLETED|0:0\n'
        raise AssertionError(argv)
    monkeypatch.setattr(scheduler,'_call',command); call('submit')
    (folder/'results.json').write_bytes(b'public-result')
    result=call('fetch')
    assert result['terminated'] and result['files']['results.json']['sha256']==scheduler.digest(b'public-result')
    assert any(argv[0]=='sacct' for argv in commands)


@pytest.mark.parametrize('name',['../secret','/absolute','nested/../secret','.cae-intent.json','a\\b',
    'C:/escape','a:stream','.', 'NUL.txt','trailing.'])
def test_control_and_escape_paths_are_rejected(name):
    with pytest.raises(ValueError): scheduler.relative_path(name)


def test_ssh_disappearance_and_unbound_exit_receipts_do_not_confirm_termination(helper):
    _,folder,_=helper; value=intent('ssh')
    assert scheduler._query(folder,value,TOKEN)['terminated'] is False
    (folder/'.cae-exit.json').write_text(json.dumps({'state':'COMPLETED','child_reaped':True}),encoding='utf-8')
    assert scheduler._query(folder,value,TOKEN)['terminated'] is False
    (folder/'.cae-exit.json').write_text(json.dumps({'state':'COMPLETED','child_reaped':True,
        'token':TOKEN,'intent_sha256':scheduler.fingerprint(value)}),encoding='utf-8')
    assert scheduler._query(folder,value,TOKEN)['termination_confirmation']=='OWNED_CHILD_REAPED'
    compile(scheduler.SUPERVISOR,'remote-supervisor','exec')
