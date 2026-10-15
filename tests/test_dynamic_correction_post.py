"""Exact PVD/sidecar source retention and cold Post contract with REAL VTK.

CalculiX outputs are explicit synthetic records. ParaView proxy/state bindings
use the existing test double; this is not native ParaView/PVSM acceptance.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest
from caelab.dynamic_locations import KEY, load, pin, select, verify_registration
from caelab.native_inputs import register_native_input
from caelab.storage import save_json
from caelab.workbench import Workbench
from test_dynamic_results import run_double
from test_dynamic_support import dynamic_model
from test_beam_post_support import install


@pytest.fixture
def produced(monkeypatch,tmp_path):
    result, output = run_double(monkeypatch,tmp_path,dynamic_model(mixed=True),rout=True)
    assert result['execution_status']=='SUCCEEDED',result
    return result,output


@pytest.fixture
def vtk_post(monkeypatch):
    pytest.importorskip('vtk')
    monkeypatch.delenv('CAE_POST_PROJECT',raising=False)
    return install(monkeypatch)


def register(tmp_path,produced,category='dynamic'):
    result,output=produced
    artifact=result['dynamic_post_artifacts'][category]
    entry=output/artifact['relative']
    wb=Workbench.__new__(Workbench);wb.root=tmp_path/'registry';wb.config={}
    receipt=register_native_input(wb.root,output,entry,'D'+category.replace('-',''),
        root_id='test-source',relative=artifact['relative'],limit=32*1024**2,
        native_metadata=artifact['native_metadata'])
    return wb,receipt,wb.native_input(receipt['id'])


@pytest.mark.parametrize('category,units,semantics,step',[
    ('dynamic','s','PHYSICAL_TIME',2),('static-preload','1','DIMENSIONLESS_MODEL_TIME',1)])
def test_registered_source_includes_exact_locations_original_result_and_snapshot(
        tmp_path,produced,vtk_post,category,units,semantics,step):
    p,_,external=vtk_post
    wb,receipt,native=register(tmp_path,produced,category)
    expected=external.source_files(native['path'],native['native_metadata'])
    assert {str(p) for p in expected}=={row['path'] for row in native['source_pins']}
    assert all(Path(p).is_relative_to(wb.root) for p in expected)
    for filename in (category+'-locations.json','dynamic_result.json','snapshot.json',
                     'contact.inp','contact.frd','contact.rout'):
        assert any(p.name==filename for p in expected)
    shutil.rmtree(produced[1])
    path=external.open_result(native['path'],tmp_path/'project',native['id'],
        native['source_pins'],native['native_metadata'],native['registration_origin'])
    chosen=external.select_array(p.GetActiveSource(),'POINTS','UX_mm',time=1.)
    assert chosen['time_units']==units and chosen['time_semantics']==semantics
    assert chosen['dynamic']['selection_semantics']=='EXACT_NATIVE_LOCATION'
    assert chosen['dynamic']['selected_location']['index']==step
    assert chosen['dynamic']['selected_native']['increment']==3
    assert chosen['dynamic']['origin']==receipt['origin'][KEY]
    assert chosen['dynamic']['origin']['snapshot_id']==produced[0]['snapshot_id']
    assert json.loads(path.read_text(encoding='utf-8'))['sources']['result']['registration_origin']==native['registration_origin']


@pytest.mark.parametrize('category',['dynamic','static-preload','restart'])
def test_saved_source_reopens_in_fresh_process_without_original_attempt_or_solver(tmp_path,produced,vtk_post,category,monkeypatch):
    p,_,external=vtk_post
    extra_origin=None
    if category=='restart':
        from test_dynamic_restart import split_double
        extra_origin=tmp_path/'restart-origin';extra_origin.mkdir()
        _,child,_=split_double(monkeypatch,extra_origin)
        produced=(json.loads((child/'contact_execution.json').read_text(encoding='utf-8')),child)
        category='dynamic'
    _,_,native=register(tmp_path,produced,category)
    exact=load(native['path'],native['native_metadata'])
    selected_time=exact['frames'][1]['timestep']
    path=external.open_result(native['path'],tmp_path/'project',native['id'],
        native['source_pins'],native['native_metadata'],native['registration_origin'])
    chosen=external.select_array(p.GetActiveSource(),'POINTS','UX_mm',time=selected_time)
    doc=json.loads(path.read_text(encoding='utf-8'))
    saved=external.save_project(path,doc)
    selected=chosen['dynamic']
    expectation=tmp_path/'expected.json';save_json(expectation,selected)
    shutil.rmtree(produced[1]);(tmp_path/'ccx').unlink()
    if extra_origin:shutil.rmtree(extra_origin)
    code=r'''
import json,os,sys
from pathlib import Path
from test_beam_post_support import install
from caelab.adapters import contact_fem
contact_fem.run_owned_command=lambda *a,**k:(_ for _ in ()).throw(AssertionError('cold reopen must not run solver'))
p,_,external=install()
path=Path(sys.argv[1]);doc=json.loads(path.read_text(encoding='utf-8'))
os.environ['CAE_POST_PROJECT']=str(path)
external.restore_workspace(path,doc)
source=p.GetActiveSource()
assert p.Show(source,p.GetActiveView()).selection==('POINTS','UX_mm')
assert p.GetAnimationScene().AnimationTime==float(sys.argv[3])
result=external.inspect_result(source)
assert result['dynamic']==json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
assert result['dynamic']['selected_native']['increment']==2
assert result['dynamic']['selected_location']['wall_time_s'] is None
print('DYNAMIC_COLD_POST_CONTRACT_OK')
'''
    root=Path(__file__).resolve().parents[1]
    env={**os.environ,'PYTHONPATH':str(root)+os.pathsep+str(root/'tests')}
    proc=subprocess.run([sys.executable,'-c',code,str(saved),str(expectation),repr(selected_time)],cwd=root,
        env=env,capture_output=True,text=True,timeout=25)
    assert proc.returncode==0,proc.stdout+proc.stderr
    assert 'DYNAMIC_COLD_POST_CONTRACT_OK' in proc.stdout


@pytest.mark.parametrize('member',['dynamic-locations.json','source/dynamic_result.json',
    'source/frozen_input/mesh.json','source/solver/contact.rout'])
def test_tampered_copied_dependency_blocks_registration_resolution_and_post(tmp_path,produced,vtk_post,member):
    _,_,external=vtk_post
    wb,_,native=register(tmp_path,produced)
    changed=Path(native['path']).parent/member
    changed.write_bytes(changed.read_bytes()+b'changed')
    with pytest.raises((ValueError,RuntimeError)):
        wb.native_input(native['id'])
    with pytest.raises((ValueError,RuntimeError)):
        external.admit_result(native['path'],native['id'],native['source_pins'],
            native['native_metadata'],native['registration_origin'])


@pytest.mark.parametrize('forgery',['location','native_increment','clock','source_snapshot','missing_source','duplicate_frame'])
def test_rehashed_sidecar_cannot_relabel_native_location_or_lose_lineage(tmp_path,produced,forgery):
    result,output=produced
    art=result['dynamic_post_artifacts']['dynamic'];entry=output/art['relative']
    metadata=deepcopy(art['native_metadata']);sidecar=entry.parent/'dynamic-locations.json'
    data=json.loads(sidecar.read_text(encoding='utf-8'))
    if forgery=='location':data['locations'][0]['index']=1
    elif forgery=='native_increment':data['frames'][0]['native']['increment']=99
    elif forgery=='clock':
        metadata['time']['unit']='1';metadata['time']['semantics']='DIMENSIONLESS_MODEL_TIME'
        data['native_metadata']=deepcopy({k:v for k,v in metadata.items() if k!=KEY})
    elif forgery=='source_snapshot':data['origin']['snapshot_id']='Fother'
    elif forgery=='missing_source':data['files']=[r for r in data['files'] if r['relative']!='source/solver/contact.dat']
    else:data['frames'][1]['timestep']=data['frames'][0]['timestep']
    save_json(sidecar,data);metadata[KEY]=pin(entry.parent,sidecar)
    with pytest.raises(ValueError):load(entry,metadata)


@pytest.mark.parametrize('chosen_time',[.500000000001,0.,float('nan'),True])
def test_no_nearest_time_or_interpolation_or_boolean_time(produced,chosen_time):
    result,output=produced;art=result['dynamic_post_artifacts']['dynamic']
    with pytest.raises(ValueError):select(output/art['relative'],art['native_metadata'],time=chosen_time)


def test_same_clock_requires_source_and_exact_frame_index(produced):
    result,output=produced;art=result['dynamic_post_artifacts']['dynamic'];entry=output/art['relative']
    chosen=select(entry,art['native_metadata'],time=.5,result_frame_index=4)
    assert chosen['selected_native']=={'step':2,'increment':2,'load_parameter':1.5}
    with pytest.raises(ValueError):select(entry,art['native_metadata'],time=.5,result_frame_index=1)
    with pytest.raises(ValueError):verify_registration(entry,art['native_metadata'],{KEY:{'snapshot_id':'wrong'}})


def test_missing_exact_sidecar_declaration_is_not_silently_anonymous_pvd(tmp_path,produced,vtk_post):
    result,output=produced;art=result['dynamic_post_artifacts']['dynamic'];entry=output/art['relative']
    metadata=deepcopy(art['native_metadata']);metadata.pop(KEY)
    _,_,external=vtk_post
    with pytest.raises(ValueError):external.source_files(entry,metadata)
    with pytest.raises(ValueError):
        register_native_input(tmp_path/'bad',output,entry,'Dbad',root_id='raw',relative=art['relative'],
            limit=32*1024**2,native_metadata=metadata)
    assert not (tmp_path/'bad/inputs/Dbad/input.json').exists()


def test_partial_result_keeps_failure_and_missing_boundary_acceleration(monkeypatch,tmp_path):
    result,output=run_double(monkeypatch,tmp_path,dynamic_model(),failed=True,rout=True)
    assert result['execution_status']=='FAILED'
    artifact=result['dynamic_post_artifacts']['dynamic']
    bundle=load(output/artifact['relative'],artifact['native_metadata'])
    selected=select(output/artifact['relative'],artifact['native_metadata'],time=bundle['frames'][0]['timestep'])
    assert selected['execution_status']=='FAILED' and selected['complete_analysis'] is False
    assert selected['qualification']=='UNKNOWN'
    from caelab.dynamic_result_store import load_result
    cached=load_result(output/'dynamic-post/source/dynamic_result.json')
    assert all(values==[None,None,None] for values in cached['frames'][0]['acceleration']['values'].values())
