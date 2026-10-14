"""M4 wrapper tests with an injected shared runner; no native process is started."""
import ast
from importlib.util import spec_from_file_location,module_from_spec
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS
import pytest


@pytest.fixture
def launcher():
    path=Path(__file__).parents[1]/'examples/assembly-candidate/run_native_correction.py'
    spec=spec_from_file_location('m4_owned_wrapper',path)
    result=module_from_spec(spec);spec.loader.exec_module(result)
    return result


def fake_process(tmp_path,**kw):
    values=dict(timed_out=False,exit_code=0,error=None,cleanup_error=None,cleanup='job_empty',
                pid=724,receipt=str(tmp_path/'native-check.json'))
    values.update(kw);return NS(**values)


def test_shared_runner_receives_exact_command_and_environment_is_restored(launcher,tmp_path,monkeypatch):
    request={'output':str(tmp_path),'phase':'cold-edit','token':'nonce-only-for-this-test'}
    called=[]
    monkeypatch.setenv('CAELAB_M4_OWNED_TOKEN','prior-value')
    monkeypatch.delenv('CAELAB_M4_OWNED_REQUEST',raising=False)
    monkeypatch.delenv('CAELAB_M4_OWNED_PARENT_PID',raising=False)
    def run(command,out,timeout_seconds,cwd):
        called.append((command,out,timeout_seconds,cwd))
        assert command==['test-FreeCAD.exe',str(tmp_path/'cold-edit.FCMacro')]
        assert Path(out)==tmp_path/'cold-edit-process' and not Path(out).exists()
        assert os.environ['CAELAB_M4_OWNED_TOKEN']==request['token']
        assert os.environ['CAELAB_M4_OWNED_PARENT_PID']==str(os.getpid())
        assert os.environ['CAELAB_M4_OWNED_REQUEST']==str(tmp_path/'cold-edit-owned-request.json')
        launcher.write_json(tmp_path/'cold-edit-owned-result.json',{'state':'PASS','pid':724,'phase':'cold-edit'})
        return fake_process(tmp_path)
    monkeypatch.setattr(launcher,'shared_native_check',lambda:run)
    result=launcher.run_phase('test-FreeCAD.exe',request,12.)
    assert len(called)==1 and result['cleanup']=='job_empty'
    assert os.environ['CAELAB_M4_OWNED_TOKEN']=='prior-value'
    assert 'CAELAB_M4_OWNED_REQUEST' not in os.environ and 'CAELAB_M4_OWNED_PARENT_PID' not in os.environ
    # There must be no second Windows/process cleanup implementation in the wrapper.
    tree=ast.parse(Path(launcher.__file__).read_text())
    names={node.name for node in ast.walk(tree) if isinstance(node,(ast.ClassDef,ast.FunctionDef))}
    assert 'WindowsJob' not in names
    imports={alias.name for node in ast.walk(tree) if isinstance(node,ast.Import) for alias in node.names}
    assert not {'ctypes','subprocess'} & imports


@pytest.mark.parametrize('failure',[
    {'timed_out':True},{'exit_code':1},{'cleanup':'kill_on_close_unverified'},
    {'cleanup_error':'unconfirmed'},{'error':'setup failed'},
])
def test_native_report_pass_cannot_hide_failed_process_or_cleanup(launcher,tmp_path,monkeypatch,failure):
    request={'output':str(tmp_path),'phase':'prepare','token':'test'}
    launcher.write_json(tmp_path/'prepare-owned-result.json',{'state':'PASS','pid':724,'phase':'prepare'})
    monkeypatch.setattr(launcher,'shared_native_check',lambda:lambda *a,**k:fake_process(tmp_path,**failure))
    with pytest.raises(RuntimeError,match='process/cleanup'):launcher.run_phase('fake',request,12.)


@pytest.mark.parametrize('answer',[
    {'state':'FAILED','pid':724,'phase':'prepare'},
    {'state':'PASS','pid':999,'phase':'prepare'},
    {'state':'PASS','pid':724,'phase':'cold-edit'},
])
def test_native_answer_must_match_the_actual_root_and_phase(launcher,tmp_path,monkeypatch,answer):
    launcher.write_json(tmp_path/'prepare-owned-result.json',answer)
    monkeypatch.setattr(launcher,'shared_native_check',lambda:lambda *a,**k:fake_process(tmp_path))
    with pytest.raises(RuntimeError):launcher.run_phase('fake',{'output':str(tmp_path),'phase':'prepare','token':'test'},12.)


def test_shared_runner_exception_restores_environment(launcher,tmp_path,monkeypatch):
    keys=['CAELAB_M4_OWNED_TOKEN','CAELAB_M4_OWNED_REQUEST','CAELAB_M4_OWNED_PARENT_PID']
    for key in keys:monkeypatch.setenv(key,'before')
    def fail(*a,**k):raise TimeoutError('injected shared runner error, not a native timeout')
    monkeypatch.setattr(launcher,'shared_native_check',lambda:fail)
    with pytest.raises(TimeoutError):
        launcher.run_phase('fake',{'output':str(tmp_path),'phase':'prepare','token':'test'},12.)
    assert all(os.environ[key]=='before' for key in keys)


def test_missing_shared_runner_is_not_replaced_with_new_cleanup(launcher,tmp_path,monkeypatch):
    monkeypatch.setattr(launcher,'REPOSITORY',tmp_path)
    with pytest.raises(RuntimeError,match='scripts/native_check.py'):launcher.shared_native_check()


@pytest.mark.parametrize('stop',[None,'cold-edit','mutate-input'])
def test_pipeline_rechecks_resaved_file_and_never_hides_failure(launcher,tmp_path,monkeypatch,stop):
    files={name:tmp_path/name for name in ('FreeCAD.exe','source.caepre','selection.json','draft.caepre')}
    for name,path in files.items():path.write_text('test-double: '+name)
    output=tmp_path/'fresh'
    # Only the wrapper's OS gate is replaced; no process or Windows API is used.
    monkeypatch.setattr(launcher,'os',NS(name='nt'))
    calls=[]
    def run(freecad,request,timeout):
        phase=request['phase'];calls.append(phase)
        if phase==stop:raise RuntimeError('injected cold edit failure')
        if stop=='mutate-input':files['source.caepre'].write_text('unexpected change')
        return {'state':'PASS','pid':100+len(calls),'cleanup':'job_empty'}
    monkeypatch.setattr(launcher,'run_phase',run)
    code=launcher.main(['--freecad',str(files['FreeCAD.exe']),'--source',str(files['source.caepre']),
        '--selection',str(files['selection.json']),'--retained-draft',str(files['draft.caepre']),
        '--output',str(output)])
    result=json.loads((output/'native-owned-summary.json').read_text())
    if stop=='cold-edit':
        assert calls==['prepare','cold-edit'] and code==1 and result['state']=='FAILED'
    elif stop=='mutate-input':
        assert code==1 and result['state']=='FAILED' and not result['inputs_unchanged']
    else:
        assert calls==['prepare','cold-edit','cold-resaved'] and code==0
    assert result['cleanup_provider']=='scripts/native_check.py'
    assert result['gui_workflow_acceptance'] is False
    assert result['solver_execution']=='NOT_PERFORMED'
