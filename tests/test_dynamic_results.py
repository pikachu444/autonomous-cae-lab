from copy import deepcopy
from types import SimpleNamespace
import math
import pytest
from test_dynamic_support import dynamic_model,outputs,snapshot,synthetic_rout
from caelab.dynamic_results import accelerations,energy_history,read_attempt,history
from caelab.dynamic_restart import read_rout,checkpoint_inventory
from caelab.contact_status import read_status
from caelab.contact_steps import profile
from caelab.contact_deck import validate_model
from caelab.adapters.frozen_fem import read_frd
from caelab.adapters import contact_fem


def parsed(m,tmp_path):
    frd,dat,sta=outputs(m)
    for ext,data in [('frd',frd),('dat',dat),('sta',sta)]: (tmp_path/('contact.'+ext)).write_text(data)
    n,e,b=validate_model(m)
    return read_frd(tmp_path/'contact.frd',n,e,contact_materials={'names':['M1'],'elements':{1:'M1'}},
                    contact_profile=profile(m),require_contact=False)['frames']


def test_irregular_acceleration_and_static_step_missing(tmp_path):
    m=dynamic_model(mixed=True);frames=parsed(m,tmp_path);before=deepcopy(frames)
    a=accelerations(m,frames)
    assert a[0]['values'][1]==[None,None,None]
    assert a[3]['values'][1]==a[5]['values'][1]==[None,None,None]
    assert a[4]['values'][1]==pytest.approx([3.,2.,0.])  # V = native total time squared, derivative at 1.5
    frames[3]['fields']['VELO'][1][0]=None
    assert accelerations(m,frames)[4]['values'][1][0] is None
    assert before[0]==frames[0]


def test_distinct_native_energy_blocks_no_nodal_sum(tmp_path):
    m=dynamic_model();frames=parsed(m,tmp_path);e=energy_history(tmp_path/'contact.dat',m,frames)
    q=e['frames'][1]['quantities']
    assert q['ELKE']['total']==q['ELSE']['total']==.5
    assert q['ENER']['total'] is None and len(q['ENER']['rows'])==4
    text=(tmp_path/'contact.dat').read_text();(tmp_path/'contact.dat').write_text(text.replace(' 1 2 5.0000000E-01',' 1 2 NaN'))
    changed=energy_history(tmp_path/'contact.dat',m,frames)['frames'][1]['quantities']['ENER']
    assert changed['status']=='unavailable' and changed['rows'][1]['value'] is None


def test_energy_duplicate_and_absent(tmp_path):
    m=dynamic_model();frames=parsed(m,tmp_path);p=tmp_path/'contact.dat'
    p.write_text(p.read_text().replace(' 1 1 2.0000000E-01',' 1 1 2.0000000E-01\n 1 1 2.0000000E-01'))
    with pytest.raises(ValueError,match='Duplicate'):energy_history(p,m,frames)
    p.unlink();assert energy_history(p,m,frames)['frames'][0]['quantities']['ELKE']['total'] is None


@pytest.mark.parametrize('order',['<','>'])
def test_actual_record_reader_on_explicit_synthetic_layout(tmp_path,order):
    m=dynamic_model(two=True);p=tmp_path/'s.rout';p.write_bytes(synthetic_rout(m,order=order))
    index=read_rout(p);assert [c['step'] for c in index['checkpoints']]==[1,2]
    _,_,sta=outputs(m);s=tmp_path/'contact.sta';s.write_text(sta)
    inv=checkpoint_inventory(p,m,read_status(s,m));assert len(inv['checkpoints'])==2
    p.write_bytes(p.read_bytes()[:-1])
    with pytest.raises(ValueError):read_rout(p)


def run_double(monkeypatch,tmp_path,m,*,omit=None,failed=False,rout=False,output_name='run'):
    snap=snapshot(m,tmp_path/('input-'+output_name));exe=tmp_path/'ccx';exe.write_bytes(b'EXPLICIT_PROCESS_DOUBLE')
    monkeypatch.setattr(contact_fem.shutil,'which',lambda _:str(exe))
    frd,dat,sta=outputs(m,omit=omit)
    def process(args,cwd,label):
        for ext,content in [('frd',frd),('dat',dat),('sta',sta)]: (cwd/('contact.'+ext)).write_text(content)
        if rout:(cwd/'contact.rout').write_bytes(synthetic_rout(m))
        return SimpleNamespace(returncode=1 if failed else 0)
    monkeypatch.setattr(contact_fem,'run_owned_command',process)
    output=tmp_path/output_name
    result=contact_fem.ContactFemCalculixAdapter().run({'snapshot_path':str(snap)},output=output)
    return result,output


def test_full_adapter_native_record_double_and_cold_open(monkeypatch,tmp_path):
    result,out=run_double(monkeypatch,tmp_path,dynamic_model(mixed=True),rout=True)
    assert result['execution_status']=='SUCCEEDED',result
    assert result['dynamic_restart']['status']=='available',result['dynamic_restart']
    monkeypatch.setattr(contact_fem,'run_owned_command',lambda *a:pytest.fail('cold open executed solver'))
    data=read_attempt(out)
    assert data['qualification']=='UNKNOWN' and len(data['frames'])==6
    assert history(data,'VELO',body_id='Solid',native_node_id=51,component=1)['rows'][1]['value']==2.25
    assert history(data,'A_DERIVED',body_id='Solid',native_node_id=51,component=1)['rows'][0]['value'] is None
    assert result['post_artifact']['native_metadata']['time']['values']==pytest.approx([.2,.5,1.])
    (out/'solver/contact.dat').write_text('changed')
    with pytest.raises(ValueError,match='changed'):read_attempt(out)


def test_missing_velocity_is_failed_not_zero(monkeypatch,tmp_path):
    result,out=run_double(monkeypatch,tmp_path,dynamic_model(),omit='VELO')
    assert result['execution_status']=='FAILED' and result['responses']=={}
    assert (out/'solver/contact.frd').is_file()


def test_failed_but_converged_prefix_is_read_only(monkeypatch,tmp_path):
    result,out=run_double(monkeypatch,tmp_path,dynamic_model(),failed=True)
    assert result['execution_status']=='FAILED'
    assert result.get('partial_result'),result
    assert result.get('dynamic_result'),result
    data=read_attempt(out)
    assert data['complete_analysis'] is False
    assert data['execution_status']=='FAILED'


def test_missing_energy_does_not_publish_an_empty_or_zero_core_curve(monkeypatch,tmp_path):
    from caelab.adapters.dynamic_fem import _responses
    _,out=run_double(monkeypatch,tmp_path,dynamic_model())
    data=read_attempt(out)
    for frame in data['frames']:
        for name in ('ELKE','ELSE'):
            frame['energy'][name]['total']=None
            frame['energy'][name]['reason']='missing_native_channel'
    result={'execution_status':'SUCCEEDED','responses':{},'diagnostics':{}}
    _responses(result,data)
    assert 'ELKE.structural_sum' not in result['responses']
    assert 'ELSE.structural_sum' not in result['responses']
    assert result['diagnostics']['dynamic_ELKE']
    assert all(f['energy']['ELKE']['total'] is None for f in data['frames'])
