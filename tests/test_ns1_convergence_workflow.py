"""Settings -> deck -> owned adapter -> retained diagnostics. Solver is a double."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace as NS
import pytest
from test_contact_execution import model
from test_ns1_pipeline import nonlinear_model, snapshot_of, outputs
from test_ns1_convergence_controls import draft
from test_ns1_convergence_logs import header, cvgrow, stdoutblock, stdout
from apps.desktop_pre.convergence import _cards
from caelab.adapters import contact_fem
from caelab.calculix_convergence import reopen_convergence
from caelab.evaluation import normalize_evaluation
from caelab.execution_control import ExecutionCancelled


def block(inc,total,local,delta,converged):
    b=stdoutblock(inc=inc,total=total,local=local,delta=delta,decision='no convergence')
    stem,body=b.split(' iteration 1\n')
    return stem+' iteration 1\n'+body+' iteration 2\n'+body.replace('no convergence','convergence' if converged else 'no convergence')


@pytest.mark.parametrize('single,cancel',[(True,False),(False,False),(False,True)])
def test_failed_settings_corrected_as_new_input_old_attempt_and_logs_unchanged(model,tmp_path,monkeypatch,single,cancel):
    m=nonlinear_model(model,single=single);m['step'].update(_cards(draft()))
    snapshot=snapshot_of(m,tmp_path/'original-input')
    executable=tmp_path/'ccx';executable.write_bytes(b'NOT_A_SOLVER')
    monkeypatch.setattr(contact_fem.shutil,'which',lambda _:str(executable))
    state={'failure':True,'calls':0}
    def command(argv,cwd,label):
        state['calls']+=1
        frd,dat,_=outputs(m);(cwd/'contact.frd').write_text(frd);(cwd/'contact.dat').write_text(dat)
        failed=state['failure']
        (cwd/'contact.sta').write_text('1 1 1 2 .5 .5 .5\n'+('1 2 1U 2 .5 .5 .5\n' if failed else '1 2 1 2 1 1 .5\n'))
        (cwd/'contact.cvg').write_text(header()+''.join(cvgrow(inc=inc,it=i) for inc in (1,2) for i in (1,2)))
        (cwd/'ccx_contact.stdout.log').write_bytes(stdout(block(1,.5,.5,.5,True),block(2,1,1,.5,not failed)))
        if cancel and failed:raise ExecutionCancelled('explicit cancellation double')
        return NS(returncode=2 if failed else 0)
    monkeypatch.setattr(contact_fem,'run_owned_command',command)
    adapter=contact_fem.ContactFemCalculixAdapter()
    first=adapter.run({'snapshot_path':str(snapshot)},output=tmp_path/'first')
    assert first['execution_status']==('CANCELLED' if cancel else 'FAILED'),first
    assert first['partial_result']['frame_count']==1
    history=first['convergence_history']
    assert len(history['rows'])==4 and history['rows'][-1]['attempt_status']=='rejected'
    assert (tmp_path/'first/convergence_history.json').exists()
    pins={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (tmp_path/'first').rglob('*') if p.is_file()}
    # User deliberately changes the maximum-iteration count, NOT the tolerance.
    changed=deepcopy(m);changed['step']['controls'][0]='4,8,9,300,10,400,,200,,'
    new=snapshot_of(changed,tmp_path/'new-input');state['failure']=False
    second=normalize_evaluation(adapter.run({'snapshot_path':str(new)},output=tmp_path/'second'))
    assert second['execution_status']=='SUCCEEDED',second
    assert second['convergence_history']['controls']['iterations']['ic']['value']==300
    assert first['convergence_history']['controls']['iterations']['ic']['value']==200
    assert second['executed_setup']['step']['field_controls']==first['executed_setup']['step']['field_controls']
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==digest for p,digest in pins.items())
    assert state['calls']==2
    executable.unlink()
    reopened=reopen_convergence(tmp_path/'first')
    assert reopened==history and state['calls']==2
