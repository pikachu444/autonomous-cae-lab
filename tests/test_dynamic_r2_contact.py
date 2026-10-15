"""Combined VTU and exact legacy contact companion; synthetic native records only."""
from copy import deepcopy
from pathlib import Path
import json
from types import SimpleNamespace
import pytest
from test_contact_execution import model as contact_model
from test_contact_steps import staged
from test_dynamic_support import outputs,snapshot
from test_dynamic_r2_streaming import options
from caelab.dynamic_model import default_draft,attach
from caelab.dynamic_native_stream import read_dynamic_frd,release
from caelab.adapters.frozen_fem import read_frd
from caelab.adapters.contact_results import read_dat,write_post
from caelab.adapters import contact_fem
from caelab import dynamic_locations as loc
from caelab import contact_inspection as inspection


@pytest.fixture
def contact_attempt(contact_model,tmp_path,monkeypatch):
    m=staged(contact_model)
    d=default_draft('Analysis','Solver',m['analysis_steps'],[
        {'body_id':r['body_id'],'material_id':r['object_id'],'kg_m3':'7800'} for r in m['materials']])
    d['program']['procedure']='mixed';d['program']['steps'][0]['procedure']='static'
    m=attach(m,d);frd,dat,sta=outputs(m)
    # Add exact printed DAT step/increment headers (synthetic output helper lacks these).
    lines=[];inc=0
    for line in dat.splitlines(True):
        if line.strip().startswith('kinetic energy'):
            lines.extend([f' S T E P {inc//3+1}\n',f' INCREMENT {inc%3+1}\n']);inc+=1
        lines.append(line)
    dat=''.join(lines)
    # Non-zero signed native contact payloads; no derived pressure/contact classification.
    current=None;rows=[]
    for line in frd.splitlines(True):
        if line.strip().startswith('-4 '):current=line.split()[1]
        if current=='CONTACT' and line.startswith(' -1'):
            line=line[:13]+''.join(f'{v:12.5E}' for v in (-1.2e-5,.01,-.02,12,-3,4))+'\n'
        rows.append(line)
    frd=''.join(rows)
    snap=snapshot(m,tmp_path/'input');exe=tmp_path/'fake-ccx';exe.write_bytes(b'EXPLICIT_PROCESS_DOUBLE')
    monkeypatch.setattr(contact_fem.shutil,'which',lambda _:str(exe))
    def command(args,cwd,label):
        for ext,data in [('frd',frd),('dat',dat),('sta',sta)]:(cwd/('contact.'+ext)).write_text(data)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(contact_fem,'run_owned_command',command)
    out=tmp_path/'run';receipt=contact_fem.ContactFemCalculixAdapter().run({'snapshot_path':str(snap)},output=out)
    assert receipt['execution_status']=='SUCCEEDED',receipt.get('diagnostics')
    return m,receipt,out


def test_combined_retains_original_raw_signs_tokens_gaps_pair_and_frame_semantics(contact_attempt,tmp_path):
    m,r,out=contact_attempt;n,e,k=options(m)
    old=read_frd(out/'solver/contact.frd',n,e,**k)
    parsed=read_dynamic_frd(out/'solver/contact.frd',n,e,**k)
    try:
        assert list(parsed['frames'])==old['frames']
        pairs=read_dat(out/'solver/contact.dat',m['contacts'],parsed['frames'])
        assert pairs==read_dat(out/'solver/contact.dat',m['contacts'],old['frames'])
    finally:release(parsed)
    assert len(list(out.rglob('frame*.vtu')))==6
    a=r['dynamic_post_artifacts']['dynamic'];entry=out/a['relative']
    selected=loc.inspect_contact(entry,a['native_metadata'],time=.25,pair_id='Contact')
    assert selected['history'] is None and not selected['history_requested']
    assert selected['active_state']=='UNKNOWN'
    assert {row['value'] for row in selected['rows']}=={12.}
    assert all(row['raw_tokens'][0].strip()=='-1.20000E-05' for row in selected['rows'])
    assert selected['dynamic']['selected_native']=={'step':2,'increment':2,'load_parameter':.75}
    assert selected['dynamic']['selected_location']['physical_time_s']==.25
    assert (out/r['contact_outputs']['body_map']).is_file()
    raw=json.loads((entry.parent/'frame0005.json').read_text())
    assert raw['pair_resultants']==[p for p in pairs if p['static']==selected['static']]
    assert raw['gap']['recipe']['solver_active_state']=='UNKNOWN'
    audit=loc.audit(entry,a['native_metadata'])
    assert audit['scope']=='ALL_REFERENCED_BYTES'


def test_lazy_contact_preserves_existing_reader_validation_and_filters_history(contact_attempt,monkeypatch):
    _,r,out=contact_attempt;a=r['dynamic_post_artifacts']['dynamic'];entry=out/a['relative']
    bundle,_=loc.contact_bundle(entry,a['native_metadata'])
    legacy=inspection.load(entry.parent/'contact.pvd',bundle['descriptor'])
    assert list(bundle['frames'])==legacy['frames']
    calls=[];original=inspection._read
    def counted(root,pin,**kw):calls.append(pin['relative']);return original(root,pin,**kw)
    monkeypatch.setattr(inspection,'_read',counted)
    bundle,_=loc.contact_bundle(entry,a['native_metadata'])
    assert not any(name.startswith('frame') for name in calls)
    calls.clear();description=inspection.describe(bundle)
    assert len(description['frames'])==6 and calls==[]
    curve=loc.contact_history(entry,a['native_metadata'],pair_id='Contact',step_id='Step2')
    assert curve['result_frame_indices']==[3,4,5]
    assert [n for n in calls if n.startswith('frame')]==[
        'frame0004.vtu','frame0004.json','frame0005.vtu','frame0005.json','frame0006.vtu','frame0006.json']
    assert all(row['valid'] for row in curve['rows'])


def test_unselected_contact_payload_corruption_is_not_a_false_integrity_success(contact_attempt):
    _,r,out=contact_attempt;a=r['dynamic_post_artifacts']['dynamic'];entry=out/a['relative']
    path=entry.parent/'frame0001.json';data=path.read_bytes();i=data.find(b'UNKNOWN');path.write_bytes(data[:i]+b'KNOWNxx'+data[i+7:])
    loc.load(entry,a['native_metadata'])
    loc.inspect_contact(entry,a['native_metadata'],time=.25,pair_id='Contact')
    with pytest.raises(ValueError):loc.audit(entry,a['native_metadata'])
    b=r['dynamic_post_artifacts']['static-preload']
    with pytest.raises(ValueError):loc.inspect_contact(out/b['relative'],b['native_metadata'],time=.1,pair_id='Contact')


def test_explicit_post_only_regeneration_recovers_native_contact_tokens(contact_attempt,tmp_path,monkeypatch):
    from caelab.dynamic_post import write
    from caelab.dynamic_result_store import read_attempt
    m,r,out=contact_attempt;data=read_attempt(out)
    monkeypatch.setattr(contact_fem,'run_owned_command',lambda *a,**k:pytest.fail('Post-only launched solver'))
    target=tmp_path/'new-post';artifacts=write(target,m,data,source_root=out)
    original=json.loads((out/'dynamic-post/frame0005.json').read_text())
    regenerated=json.loads((target/'frame0005.json').read_text())
    for key in ('contact','gap','pair_resultants','static','channels','basis','step_location'):
        assert regenerated[key]==original[key]
    a=artifacts['dynamic']
    assert loc.inspect_contact(target/a['relative'],a['native_metadata'],time=.25,pair_id='Contact')['active_state']=='UNKNOWN'
