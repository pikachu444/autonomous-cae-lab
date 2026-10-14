"""Explicit process doubles verify ownership and preservation, not real ccx."""
from pathlib import Path
import subprocess
import pytest
from caelab.adapters import shell_fem
from caelab.adapters.shell_fem import ShellFemCalculixAdapter
from caelab.execution_control import ExecutionCancelled,ExecutionCleanupFailed
if __package__:
    from .test_shell_support import snapshot,model,raw_sources
else:
    from test_shell_support import snapshot,model,raw_sources

@pytest.mark.parametrize('mode',['ok','fail','cancel','cleanup'])
def test_existing_process_owner_is_used_and_native_failure_never_promoted(tmp_path,monkeypatch,mode):
    data=model(); source=snapshot(tmp_path/'input',data);binary=tmp_path/'ccx.exe';binary.write_bytes(b'EXPLICIT_TEST_DOUBLE')
    monkeypatch.setattr(shell_fem.shutil,'which',lambda name:str(binary) if name=='ccx' else None)
    calls=[]
    def owned(argv,cwd,label,**kwargs):
        calls.append((argv,label,kwargs));assert kwargs['owned_tree'] is True
        assert argv==[str(binary),'-i','shell']
        raw_sources(cwd,data,fields=('DISP',) if mode=='cancel' else ('DISP','STRESS','TOSTRAIN'),end=mode!='cancel')
        if mode=='cleanup':raise ExecutionCleanupFailed('TEST_DOUBLE owned process cleanup unconfirmed')
        if mode=='cancel':raise ExecutionCancelled('TEST_DOUBLE cancellation')
        return subprocess.CompletedProcess(argv,1 if mode=='fail' else 0,'TEST_DOUBLE','')
    monkeypatch.setattr(shell_fem,'run_owned_command',owned)
    out=tmp_path/'new-job'
    if mode=='cleanup':
        with pytest.raises(ExecutionCleanupFailed):ShellFemCalculixAdapter().run({'snapshot_path':str(source)},output=out)
        assert not (out/'shell_execution.json').exists()
        assert (out/'solver'/'shell.frd').exists()
        return
    result=ShellFemCalculixAdapter().run({'snapshot_path':str(source)},output=out)
    assert result['execution_status']=={'ok':'SUCCEEDED','fail':'FAILED','cancel':'CANCELLED'}[mode]
    assert result['engineering_valid'] is False
    assert (out/'solver'/'shell.12d').exists() and (out/'retained_inputs'/'editable.FCStd').exists()
    before=(out/'shell_execution.json').read_bytes()
    with pytest.raises(ValueError):ShellFemCalculixAdapter().run({'snapshot_path':str(source)},output=out)
    assert (out/'shell_execution.json').read_bytes()==before
    assert len(calls)==1


@pytest.mark.parametrize('version',['2.21','2.23','missing','duplicate'])
def test_native_exit_zero_cannot_admit_wrong_or_missing_result_version(tmp_path,monkeypatch,version):
    data=model();source=snapshot(tmp_path/'input',data)
    binary=tmp_path/'ccx.exe';binary.write_bytes(b'EXPLICIT_TEST_DOUBLE')
    monkeypatch.setattr(shell_fem.shutil,'which',lambda _:str(binary))
    def owned(argv,cwd,label,**kwargs):
        assert argv==[str(binary),'-i','shell']
        raw_sources(cwd,data)
        path=cwd/'shell.frd';raw=path.read_bytes()
        header=next(line for line in raw.splitlines(keepends=True) if b'1UVERSION' in line)
        replacement=b'' if version=='missing' else header*2 if version=='duplicate' else header.replace(b'2.22',version.encode('ascii'))
        path.write_bytes(raw.replace(header,replacement))
        return subprocess.CompletedProcess(argv,0,'TEST_DOUBLE','')
    monkeypatch.setattr(shell_fem,'run_owned_command',owned)
    out=tmp_path/'job'
    result=ShellFemCalculixAdapter().run({'snapshot_path':str(source)},output=out)
    assert result['execution_status']=='FAILED' and result['responses']=={}
    assert not result.get('post_artifact')
    assert (out/'solver'/'shell.frd').is_file()

def test_missing_solver_retains_input_and_structured_failure(tmp_path,monkeypatch):
    source=snapshot(tmp_path/'input');monkeypatch.setattr(shell_fem.shutil,'which',lambda _:None)
    result=ShellFemCalculixAdapter().run({'snapshot_path':str(source)},output=tmp_path/'job')
    assert result['execution_status']=='FAILED' and not result['responses']
    assert (tmp_path/'job'/'solver'/'shell.inp').exists()
    assert not result.get('post_artifact')
