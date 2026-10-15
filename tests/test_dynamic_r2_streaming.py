"""R2 bounded transport; SAME strict grammar, synthetic versus supplied native explicit."""
from pathlib import Path
from copy import deepcopy
import json
import pytest
from test_dynamic_support import dynamic_model, outputs
from caelab.adapters.frozen_fem import read_frd
from caelab.contact_deck import validate_model
from caelab.contact_steps import profile, validate_frames
from caelab.contact_status import read_status, retained_prefix
from caelab.dynamic_native_stream import read_dynamic_frd, release
from caelab.execution_control import ExecutionCancelled


def options(model):
    nodes,elements,bodies=validate_model(model)
    ids={b:i+1 for i,b in enumerate(sorted(bodies))}
    materials={'names':['M'+str(i) for i in ids.values()]+[
        'INT'+p['object_id'].upper() for p in model['contacts']],
        'elements':{e['element_id']:'M'+str(ids[e['body_id']]) for e in model['elements']}}
    return nodes,elements,dict(contact_materials=materials,contact_profile=profile(model),
                               require_contact=bool(model['contacts']))


@pytest.mark.parametrize('model',[dynamic_model(),dynamic_model(mixed=True),dynamic_model(two=True)])
@pytest.mark.parametrize('crlf',[False,True])
def test_stream_grammar_exact_equal_all_frames(tmp_path,model,crlf):
    frd,_,_=outputs(model);path=tmp_path/'in.frd'
    path.write_bytes(frd.replace('\n','\r\n').encode() if crlf else frd.encode())
    n,e,k=options(model)
    old=read_frd(path,n,e,**k);new=read_dynamic_frd(path,n,e,parent=tmp_path,**k)
    try:
        validate_frames(model,old,complete=True);validate_frames(model,new,complete=True)
        assert list(new['frames'])==old['frames']
        assert {k:v for k,v in new.items() if k not in {'frames','native_transport'}} == {
            k:v for k,v in old.items() if k!='frames'}
        assert new['frames'].max_resident_frames<=3
    finally:release(new)
    assert not list(tmp_path.glob('.dynamic-native-*'))


@pytest.mark.parametrize('change',[
    lambda x:x.replace(' -3\n',' -3 BAD\n',1),
    lambda x:x.replace('Version 2.22','Version UNKNOWN'),
    lambda x:x+'GARBAGE\n',
    lambda x:x.replace(' 9999\n',''),
    lambda x:x.replace(' 9999\n',' 99'),
    lambda x:x.replace(' 0.00000E+00','           0',1),
])
def test_corruption_reuses_strict_rejection_and_cleans_spool(tmp_path,change):
    m=dynamic_model();p=tmp_path/'bad.frd';p.write_text(change(outputs(m)[0]))
    n,e,k=options(m)
    # No new permissive parser: whatever original grammar rejects is rejected.
    with pytest.raises((ValueError,UnicodeError)):read_frd(p,n,e,**k)
    with pytest.raises((ValueError,UnicodeError)):read_dynamic_frd(p,n,e,parent=tmp_path,**k)
    assert not list(tmp_path.glob('.dynamic-native-*'))


@pytest.mark.parametrize('torn',['missing_end','partial_end','field_prefix'])
def test_failed_prefix_policy_is_exactly_the_existing_policy(tmp_path,torn):
    m=dynamic_model();frd,_,sta=outputs(m)
    if torn=='missing_end':frd=frd.replace(' 9999\n','')
    elif torn=='partial_end':frd=frd.replace(' 9999\n',' 99')
    else:frd=frd[:frd.rfind('    1PSTEP')+8]
    p=tmp_path/'raw.frd';p.write_text(frd);s=tmp_path/'raw.sta';s.write_text(sta)
    n,e,k=options(m);status=read_status(s,m);before=p.read_bytes()
    a=retained_prefix(p,tmp_path/'a.frd',n,e,k['contact_materials'],m,status)
    b=retained_prefix(p,tmp_path/'b.frd',n,e,k['contact_materials'],m,status,streaming=True)
    try:
        assert (tmp_path/'a.frd').read_bytes()==(tmp_path/'b.frd').read_bytes()
        assert list(b['frames'])==a['frames'] and b['retention']==a['retention']
    finally:release(b)
    assert p.read_bytes()==before


def test_cancel_during_streamed_frame_write_keeps_original(monkeypatch,tmp_path):
    from caelab import dynamic_native_stream as stream
    m=dynamic_model(two=True);p=tmp_path/'raw.frd';p.write_text(outputs(m)[0]);before=p.read_bytes()
    original=stream.NativeFrames.append
    def cancel(self,frame):
        if len(self)==1:raise ExecutionCancelled('R2_INJECTED_CANCEL')
        return original(self,frame)
    monkeypatch.setattr(stream.NativeFrames,'append',cancel)
    n,e,k=options(m)
    with pytest.raises(ExecutionCancelled):read_dynamic_frd(p,n,e,parent=tmp_path,**k)
    assert p.read_bytes()==before and not list(tmp_path.glob('.dynamic-native-*'))


def test_supplied_actual_three_frames_and_windows_rout_read_only(tmp_path):
    from caelab.dynamic_restart import checkpoint_inventory
    import hashlib
    sample=Path(__file__).parent/'fixtures/dynamic_r2_public_native'
    m=json.loads((sample/'frozen_input/mesh.json').read_text())
    p=sample/'first-three-frames.frd';n,e,k=options(m)
    old=read_frd(p,n,e,**k);actual=read_dynamic_frd(p,n,e,parent=tmp_path,**k)
    try:
        assert len(actual['frames'])==3 and list(actual['frames'])==old['frames']
    finally:release(actual)
    rout=sample/'contact.rout'
    before=hashlib.sha256(rout.read_bytes()).hexdigest()
    assert before=='b31d56c16819c40449903877ea47f51c511ae7ec611ffc1353d42788264727ef'
    inv=checkpoint_inventory(rout,m,read_status(sample/'contact.sta',m))
    assert [r['step'] for r in inv['checkpoints']]==[1,2]
    assert hashlib.sha256(rout.read_bytes()).hexdigest()==before
