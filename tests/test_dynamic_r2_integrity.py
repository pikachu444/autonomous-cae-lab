"""Selected byte integrity is not a cached/global success. Native fixtures are synthetic."""
from copy import deepcopy
from pathlib import Path
import json
import shutil
import pytest
from test_dynamic_support import dynamic_model
from test_dynamic_results import run_double
from caelab import dynamic_result_store as store
from caelab import dynamic_locations as loc
from caelab.dynamic_results import history


@pytest.fixture
def attempt(monkeypatch,tmp_path):
    receipt,root=run_double(monkeypatch,tmp_path,dynamic_model(mixed=True),rout=True)
    assert receipt['execution_status']=='SUCCEEDED',receipt
    return receipt,root


def track(monkeypatch,module,name):
    calls=[];original=getattr(module,name)
    def counted(path,*args,**kwargs):
        calls.append(str(path));return original(path,*args,**kwargs)
    monkeypatch.setattr(module,name,counted);return calls


def mutate_same_size(path):
    data=path.read_bytes();pos=data.find(b'0')
    if pos<0:pos=0
    path.write_bytes(data[:pos]+(b'1' if data[pos:pos+1]!=b'1' else b'2')+data[pos+1:])


def test_metadata_no_frame_or_raw_hash_reads_then_only_selected(monkeypatch,attempt):
    receipt,root=attempt;hashes=track(monkeypatch,store,'_sha')
    arrays=[];original=store._json
    monkeypatch.setattr(store,'_json',lambda folder,pin,*a:(arrays.append(pin['relative']),original(folder,pin,*a))[1])
    data=store.read_attempt(root,metadata_only=True)
    assert data.verification['raw_source_bytes']=='DEFERRED' and arrays==[]
    assert all(Path(p).name=='dynamic_result.json' for p in hashes)
    hashes.clear()
    selected=store.select_frame(root,4,expected_native=store.frame_metadata(data)[4]['native'])
    assert arrays==['dynamic-frames/topology.json','dynamic-frames/frame0005.json']
    assert selected['verification']['selected_frame_bytes']=='VERIFIED'
    assert all('/solver/' not in p and '/frame0' not in p for p in hashes)


def test_unselected_corruption_is_deferred_but_audit_and_selected_reject(attempt):
    _,root=attempt;data=store.read_attempt(root,metadata_only=True)
    changed=root/data.index['frames'][0]['artifact']['relative'];mutate_same_size(changed)
    assert store.read_attempt(root,metadata_only=True).verification['unselected_frame_bytes']=='DEFERRED'
    assert store.select_frame(root,4)['frame']['native']['step']==2
    with pytest.raises(ValueError,match='changed'):store.select_frame(root,0)
    with pytest.raises(ValueError,match='changed'):store.verify_attempt(root)


def test_raw_same_size_change_requires_explicit_source_audit(attempt):
    _,root=attempt;mutate_same_size(root/'solver/contact.rout')
    assert store.read_attempt(root).verification['raw_source_bytes']=='DEFERRED'
    with pytest.raises(ValueError,match='changed'):store.verify_attempt(root)
    from caelab.dynamic_execution import read_terminal
    assert read_terminal(root)['verification']['source_contents']=='DEFERRED'
    with pytest.raises(ValueError):read_terminal(root,full=True)


@pytest.mark.parametrize('case',['missing','truncated','symlink','duplicate','foreign_path','wrong_job','wrong_snapshot','wrong_result','wrong_native'])
def test_exact_selection_rejects_bad_dependency_or_cross_identity(attempt,tmp_path,case):
    _,root=attempt;data=store.read_attempt(root,metadata_only=True);frame=root/data.index['frames'][1]['artifact']['relative']
    kwargs={}
    if case=='missing':frame.unlink()
    elif case=='truncated':frame.write_bytes(frame.read_bytes()[:-1])
    elif case=='symlink':
        outside=tmp_path/'outside';outside.write_bytes(frame.read_bytes());frame.unlink()
        try:frame.symlink_to(outside)
        except OSError as error:
            if getattr(error,'winerror',None)==1314:
                pytest.skip('Windows host cannot create a symlink without the required privilege')
            raise
    elif case=='duplicate':
        p=root/'contact_execution.json';r=json.loads(p.read_text());r['artifacts'].append(r['artifacts'][0]);p.write_text(json.dumps(r))
    elif case=='foreign_path':
        p=root/'contact_execution.json';r=json.loads(p.read_text());r['dynamic_result']['relative']='../dynamic_result.json';p.write_text(json.dumps(r))
    elif case=='wrong_job':kwargs['expected_job_id']='JnotThisJob'
    elif case=='wrong_snapshot':kwargs['expected_snapshot_id']='FnotThisInput'
    elif case=='wrong_result':kwargs['expected_result']={**data.verification['result'],'sha256':'1'*64}
    elif case=='wrong_native':kwargs['expected_native']={**data.index['frames'][1]['native'],'step':99}
    with pytest.raises((ValueError,OSError)):store.select_frame(root,1,**kwargs)


def test_cross_attempt_valid_hash_frame_substitution_is_rejected(monkeypatch,tmp_path,attempt):
    _,root=attempt
    _,other=run_double(monkeypatch,tmp_path,dynamic_model(two=True),output_name='other')
    index_path=root/'dynamic_result.json';index=json.loads(index_path.read_text())
    replacement=store.load_result(other/'dynamic_result.json',metadata_only=True).index['frames'][1]['artifact']
    target=root/index['frames'][1]['artifact']['relative'];shutil.copyfile(other/replacement['relative'],target)
    index['frames'][1]['artifact']=store.file_pin(root,target)
    index_path.write_text(json.dumps(index))
    # Even a locally edited matching outer hash cannot rebind a frame capsule's source identity.
    record_path=root/'contact_execution.json';r=json.loads(record_path.read_text())
    r['dynamic_result'].update(store.file_pin(root,index_path));updates={p['relative']:p for p in (index['frames'][1]['artifact'],store.file_pin(root,index_path))}
    r['artifacts']=[updates.get(p['relative'],p) for p in r['artifacts']];record_path.write_text(json.dumps(r))
    with pytest.raises(ValueError,match='different result'):store.select_frame(root,1)


def test_history_filters_step_before_reading_frames(monkeypatch,attempt):
    _,root=attempt;data=store.read_attempt(root);calls=[];original=store._json
    monkeypatch.setattr(store,'_json',lambda folder,pin,*a:(calls.append(pin['relative']),original(folder,pin,*a))[1])
    curve=history(data,'VELO',body_id='Solid',native_node_id=51,component=1,step_id='Step2')
    assert len(curve['rows'])==3
    assert calls==['dynamic-frames/frame0004.json','dynamic-frames/frame0005.json','dynamic-frames/frame0006.json']


def test_post_metadata_and_selection_are_bounded_and_keep_clocks(monkeypatch,attempt):
    receipt,root=attempt;a=receipt['dynamic_post_artifacts']['dynamic'];entry=root/a['relative']
    hashes=track(monkeypatch,loc,'_sha');reads=track(monkeypatch,store,'_sha')
    bundle=loc.load(entry,a['native_metadata'])
    assert bundle['verification']['raw_and_unselected_bytes']=='DEFERRED'
    assert not any(p.endswith(('.vtu','.frd','.dat','.rout','.FCStd')) for p in hashes+reads)
    hashes.clear();reads.clear()
    result=loc.select(entry,a['native_metadata'],time=.5,result_frame_index=4)
    assert result['selected_native']['step']==2
    assert result['selected_location']['physical_time_s']==.5
    assert len([p for p in hashes if p.endswith('.vtu')])==1
    assert not any(p.endswith(('.frd','.dat','.rout','.FCStd')) for p in hashes+reads)
    with pytest.raises(ValueError):loc.select(entry,a['native_metadata'],time=.50001)
    with pytest.raises(ValueError):loc.select(entry,a['native_metadata'],time=.5,result_frame_index=1)


def test_post_unselected_and_raw_corruption_deferred_selected_audit_reject(attempt):
    receipt,root=attempt;a=receipt['dynamic_post_artifacts']['dynamic'];entry=root/a['relative'];metadata=a['native_metadata']
    bundle=loc.load(entry,metadata);first=entry.parent/bundle['frames'][0]['file'];mutate_same_size(first)
    loc.load(entry,metadata)
    assert loc.select(entry,metadata,time=.5)['selected_native']['increment']==2
    with pytest.raises(ValueError):loc.select(entry,metadata,time=.2)
    with pytest.raises(ValueError):loc.audit(entry,metadata)


def test_one_volume_per_frame_and_all_legacy_raw_files_preserved(attempt):
    receipt,root=attempt
    assert len(list(root.rglob('*.vtu')))==6
    legacy=root/receipt['native_coordinate_post_artifact']['relative']
    assert legacy.name=='contact.pvd' and legacy.is_file()
    assert all((legacy.parent/('frame%04d.json'%i)).is_file() for i in range(1,7))
    from xml.etree import ElementTree as ET
    names={row.get('Name') for row in ET.parse(legacy.parent/'frame0005.vtu').findall('.//DataArray')}
    assert {'UX_mm','UY_mm','UZ_mm'}<=names
    assert any('Velocity' in n or n.startswith('V') for n in names if n)
    assert any('Acceleration' in n or n.startswith('A') for n in names if n)


def test_serializable_catalogue_contains_scope_and_no_array_read(monkeypatch,attempt):
    _,root=attempt
    monkeypatch.setattr(store,'_json',lambda *a,**k:pytest.fail('CATALOGUE_READ_PAYLOAD'))
    value=store.describe_attempt(root)
    restored=json.loads(json.dumps(value))
    assert restored==value
    assert value['solver_execution']=='NOT_PERFORMED'
    assert value['verification']['scope']=='INDEX_ONLY'
    assert value['verification']['unselected_frame_bytes']=='DEFERRED'
    assert len(value['frames'])==6
    assert all('fields' not in row and 'acceleration' not in row for row in value['frames'])
