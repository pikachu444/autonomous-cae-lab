"""Real broker/desktop functions with Popen, HWND and launch lock boundaries doubled.

No operating-system/native process is created. Any future native validation must
use scripts/native_check.py's own Job/finally; never terminate a user's window.
"""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from apps.research import desktop, post_curve_origin as origin
from caelab.native_commands import NativeCommands
from test_post_numerical import fixture_snapshot
from test_native_commands import document


@pytest.fixture
def launch(tmp_path,monkeypatch):
    snapshot,_=fixture_snapshot(tmp_path);saved=snapshot['origin']
    folder=tmp_path/'launch';folder.mkdir();calls=[]
    context={'repo_root':str(Path(__file__).parents[1]),'python':'/SCRIPTED/python',
             'paraview_executable':'/SCRIPTED/paraview'}
    client=SimpleNamespace(url='http://127.0.0.1:18766',desktop_context=lambda:context,
                           documents=lambda:{'documents':[]})
    monkeypatch.setattr(desktop,'_executable',lambda *args,**kwargs:Path('/SCRIPTED/paraview'))
    monkeypatch.setattr(desktop,'_folder',lambda *args:folder)
    monkeypatch.setattr(desktop,'_native_pid_alive',lambda pid:False)
    monkeypatch.setattr(desktop.subprocess,'Popen',lambda *args,**kwargs:
                        calls.append((deepcopy(args),deepcopy(kwargs))) or SimpleNamespace(pid=445566))
    monkeypatch.setattr(desktop.subprocess,'run',lambda *args,**kwargs:pytest.fail('No prepare/provider/solver'))
    args=desktop._arguments(['post','--project',saved['project']['path']])
    return SimpleNamespace(origin=saved,client=client,folder=folder,calls=calls,args=args)


def test_real_saved_launcher_uses_genuine_measurement_not_fake_report(launch,monkeypatch):
    x=launch;before=Path(x.origin['project']['path']).read_bytes();progress={'phase':'PREPARING'}
    monkeypatch.setenv('CAE_POST_REPORT_ORIGIN','unrelated inherited report')
    result=desktop._post(x.client,x.args,_measurement_origin=x.origin,_origin_launch=progress)
    assert result['status']=='LAUNCHED' and progress=={'phase':'CREATED','pid':445566}
    assert len(x.calls)==1
    argv=x.calls[0][0][0];env=x.calls[0][1]['env']
    assert Path(argv[0])==Path('/SCRIPTED/paraview') and '--disable-registry' in argv
    assert 'CAE_POST_REPORT_ORIGIN' not in env
    assert json.loads(Path(env['CAE_POST_MEASUREMENT']).read_text())==x.origin
    assert env['CAE_POST_PROJECT']==x.origin['project']['path']
    assert 'shell' not in x.calls[0][1]
    assert Path(x.origin['project']['path']).read_bytes()==before


@pytest.mark.parametrize('fault',['project','workspace','result','clone'])
def test_changed_pins_never_reach_popen(launch,fault):
    x=launch;path=Path(x.origin['project']['path'])
    if fault=='clone':
        other=x.folder/'clone.json';other.write_bytes(path.read_bytes());x.args.project=str(other)
    elif fault=='workspace':Path(x.origin['workspace']['path']).write_text('changed')
    elif fault=='result':
        p=json.loads(path.read_text());Path(p['analysis']['objects']['Ameasure']['history'][0]['result_file']).write_text('changed')
    else:path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises((ValueError,OSError)):
        desktop._post(x.client,x.args,_measurement_origin=x.origin,_origin_launch={'phase':'PREPARING'})
    assert not x.calls


@pytest.mark.parametrize('outcome',['success','not_created','interrupted'])
def test_claim_always_unlocked_and_ambiguous_spawn_marker_preserved(launch,monkeypatch,outcome):
    x=launch;unlocked=[];marker=x.folder/'existing-launch-claim.json'
    monkeypatch.setattr(desktop,'_post_launch_claim',lambda *args:
        (SimpleNamespace(unlock=lambda:unlocked.append(True)),marker))
    args=desktop._arguments(['post','--curve-origin',json.dumps(x.origin)])
    if outcome!='success':
        def fail(*args,**kwargs):
            if outcome=='not_created':raise OSError('SCRIPTED confirmed not created')
            raise KeyboardInterrupt('SCRIPTED application unknown')
        monkeypatch.setattr(desktop.subprocess,'Popen',fail)
    if outcome=='success':
        receipt=origin.launch_saved_measurement(x.client,args)
        assert receipt['status']=='LAUNCH_REQUESTED' and receipt['source_selection']=='NOT_PERFORMED'
        assert json.loads(marker.read_text())['launcher_pid']==445566
    else:
        with pytest.raises((OSError,KeyboardInterrupt)):origin.launch_saved_measurement(x.client,args)
        assert marker.exists()==(outcome=='interrupted')
    assert unlocked==[True]


def test_read_verify_select_use_existing_nonce_protected_broker(tmp_path):
    broker=NativeCommands(tmp_path,'Sservice');d=document()
    operations=['post.curve_origin_read','post.curve_origin_verify','post.curve_origin_select']
    d['capabilities']+=operations
    kwargs=dict(host_id='Hone',session_id='Snative',application='paraview',version='SCRIPTED',
                execution_mode='headless',documents=[d])
    auth=broker.register(**kwargs,registration_nonce='n'*32)
    with pytest.raises(ValueError,match='proof'):
        broker.register(**kwargs,registration_nonce='w'*32)
    assert auth['host_token'] not in json.dumps(broker.documents())
    for index,operation in enumerate(operations):
        id='Corigin'+str(index)
        queued=broker.submit(document_id='Pone',operation=operation,arguments={},session_id='Snative',
                            expected_generation=0,command_id=id)
        assert queued['state']=='QUEUED'
        assert broker.cancel(id)['state']=='CANCELLED'
    assert broker.next('Hone',session_id='Snative',host_token=auth['host_token'])['command'] is None
