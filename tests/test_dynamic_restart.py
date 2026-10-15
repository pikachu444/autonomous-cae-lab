"""Round-trip protocol tests use explicitly SYNTHETIC bytes/processes, not ccx."""
from copy import deepcopy
from types import SimpleNamespace
import hashlib
import json
import pytest
from test_dynamic_support import dynamic_model,outputs,synthetic_rout
from test_dynamic_results import run_double
from caelab.adapters import contact_fem
from caelab.dynamic_restart import prepare,inspect_attempt,compare_saved_states,stage_read
from caelab.dynamic_results import read_attempt,compare_continuation

TOL={k:1e-12 for k in ('DISP','VELO','FORC','STRESS','TOSTRAIN','ENER','ENER_IP','PE','ELKE','ELSE')}
STATE={k:1e-12 for k in ('vold','veold','sti','eme','ener','xstate','pslavsurf','clearini','xmodal','ctrl','qaold','prestr','xmodal_modes')}


def split_double(monkeypatch,tmp_path):
    m=dynamic_model(two=True)
    first,out=run_double(monkeypatch,tmp_path,m,rout=True)
    before={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}
    inv=inspect_attempt(out);assert inv['status']=='available'
    path=prepare(out,1,m['analysis_steps']['steps'][1:],tmp_path/'restart-inputs')
    assert (path.parent/'contact.rin').read_bytes()==(out/'solver/contact.rout').read_bytes()
    deck=(path.parent/'contact.inp').read_text()
    assert deck.startswith('*RESTART,READ,STEP=1\n')
    assert '*NODE\n' not in deck and '*MATERIAL' not in deck and '*INITIAL CONDITIONS' not in deck
    _,model,_,_=contact_fem.validate_snapshot(path)
    frd,dat,sta=outputs(model)
    def process(args,cwd,label):
        assert (cwd/'contact.rin').read_bytes()==(out/'solver/contact.rout').read_bytes()
        for suffix,text in [('frd',frd),('dat',dat),('sta',sta)]: (cwd/('contact.'+suffix)).write_text(text)
        (cwd/'contact.rout').write_bytes(synthetic_rout(model,steps=[2]))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(contact_fem,'run_owned_command',process)
    resumed=tmp_path/'restart-run'
    result=contact_fem.ContactFemCalculixAdapter().run({'snapshot_path':str(path)},output=resumed)
    assert result['execution_status']=='SUCCEEDED',result
    assert before=={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}
    return out,resumed,path


def test_restart_uses_pinned_native_bytes_and_full_comparison(monkeypatch,tmp_path):
    out,resumed,path=split_double(monkeypatch,tmp_path)
    a,b=read_attempt(out),read_attempt(resumed)
    assert b['state_source']['kind']=='native_restart_read'
    assert b['frames'][0]['native']['step']==2
    comparison=compare_continuation(a,b,absolute_tolerances=TOL,relative_tolerance=0.,time_tolerance=1e-10)
    assert comparison['status']=='PASS',comparison
    assert comparison['qualification']=='UNKNOWN'
    saved=compare_saved_states(out/'solver/contact.rout',resumed/'solver/contact.rout',
        left_step=2,right_step=2,tolerances=STATE,time_tolerance=1e-10)
    assert saved['status']=='PASS',saved
    (path.parent/'contact.rin').write_bytes(b'tampered')
    with pytest.raises(ValueError):contact_fem.validate_snapshot(path)


def test_restart_rejects_missing_samples_and_changed_energy(monkeypatch,tmp_path):
    out,resumed,_=split_double(monkeypatch,tmp_path);a,b=read_attempt(out),read_attempt(resumed)
    args=dict(absolute_tolerances=TOL,relative_tolerance=0.,time_tolerance=1e-10)
    missing=deepcopy(b);missing['frames'].pop(1)
    assert compare_continuation(a,missing,**args)['status']=='INCOMPLETE'
    changed=deepcopy(b);changed['frames'][0]['energy']['ENER']['rows'][0]['value']+=1
    assert compare_continuation(a,changed,**args)['status']=='FAIL'
    changed=deepcopy(b);changed['complete_analysis']=False
    assert compare_continuation(a,changed,**args)['status']=='INCOMPLETE'
    changed=deepcopy(b);changed['state_source'].pop('native_read_observation')
    with pytest.raises(ValueError,match='observation'):compare_continuation(a,changed,**args)


def test_native_state_time_and_values_cannot_hide_behind_success(tmp_path):
    m=dynamic_model(two=True);a=tmp_path/'a.rout';b=tmp_path/'b.rout'
    a.write_bytes(synthetic_rout(m));b.write_bytes(synthetic_rout(m,delta=1.))
    args=dict(left_step=2,right_step=2,tolerances=STATE,time_tolerance=1e-10)
    result=compare_saved_states(a,b,**args)
    assert result['status']=='FAIL' and any(r['array']=='vold' and r['failed_values'] for r in result['arrays'])
    b.write_bytes(synthetic_rout(m));args['right_step']=1
    assert compare_saved_states(a,b,**args)['status']=='FAIL'
    args.update(right_step=2,tolerances={})
    assert compare_saved_states(a,b,**args)['status']=='INCOMPLETE'


def test_missing_checkpoint_and_build_mismatch_never_start_fresh(monkeypatch,tmp_path):
    m=dynamic_model(two=True);_,out=run_double(monkeypatch,tmp_path,m,rout=True)
    with pytest.raises(ValueError,match='no actual'):prepare(out,99,m['analysis_steps']['steps'][1:],tmp_path/'r')
    path=prepare(out,1,m['analysis_steps']['steps'][1:],tmp_path/'r')
    _,model,_,_=contact_fem.validate_snapshot(path)
    native=tmp_path/'native';native.mkdir()
    runtime=deepcopy(model['restart']['parent_runtime']);runtime['sha256']='0'*64
    with pytest.raises(ValueError,match='exact parent'):stage_read(path.parent,native,model,runtime)
    assert not (native/'contact.rin').exists()
    (out/'solver/contact.rout').write_bytes(b'')
    with pytest.raises(ValueError,match='changed'):inspect_attempt(out)


def test_managed_job_identity_is_taken_from_real_job_record(monkeypatch,tmp_path):
    from caelab.adapters.dynamic_fem import before_run
    m=dynamic_model();workspace=tmp_path/'workspace';identifier='J'+'a'*32
    native=workspace/'native'/identifier/'solver';native.mkdir(parents=True)
    (workspace/'jobs').mkdir();job={'id':identifier,'arguments':{'settings':{'data_id':'D1'}},'operation':'run','workspace_id':'local','request_hash':'hash'}
    (workspace/'jobs'/(identifier+'.json')).write_text(json.dumps(job))
    result={};before_run(tmp_path,native,m,{'sha256':'a'*64},result,{'data_id':'D1'})
    assert result['job_id']==identifier
    with pytest.raises(ValueError,match='identity'):before_run(tmp_path,native,m,{'sha256':'a'*64},{},{'data_id':'D2'})
