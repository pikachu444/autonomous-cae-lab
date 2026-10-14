"""Existing registry and Post admission/select/save/reopen, using real VTK.

ParaView proxy/state boundaries are explicitly doubled; native Windows PVSM
acceptance is provided separately in examples/beam/beam_post_acceptance.py.
"""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import os
from types import SimpleNamespace as NS
import pytest
from caelab.native_inputs import register_native_input
from caelab.workbench import Workbench
from caelab.storage import save_json
from caelab.beam_results import CHANNELS
from test_beam_post_bundle import produced
from test_beam_post_support import install


@pytest.fixture
def native(monkeypatch):
    pytest.importorskip('vtk')
    monkeypatch.delenv('CAE_POST_PROJECT',raising=False)
    return install(monkeypatch)


def register(tmp_path,produced):
    _,view,metadata=produced
    # Exercise real registrar and resolver methods; no unrelated document/job
    # initialization is needed in the partial supplied source archive.
    w=Workbench.__new__(Workbench);w.root=tmp_path/'workbench';w.config={'input_roots':{'raw':str(view.parent)}}
    receipt=w.register_local_input('raw','beam_inspection.json')
    resolved=w.native_input(receipt['id'])
    return w,receipt,resolved


def test_real_registration_copies_bundle_metadata_and_raw_members(tmp_path,produced,native):
    w,receipt,resolved=register(tmp_path,produced)
    _,_,external=native
    assert receipt['native_metadata']['time']['unit']=='1'
    assert resolved['native_metadata']==produced[2]
    expected=external.source_files(resolved['path'],resolved['native_metadata'])
    assert [str(p) for p in expected]==[row['path'] for row in resolved['source_pins']]
    assert all(Path(p).is_relative_to(w.root) for p in expected)
    assert any(p.name=='beam.frd' for p in expected)
    shutil.rmtree(produced[0])
    source,record=external.admit_result(resolved['path'],resolved['id'],resolved['source_pins'],resolved['native_metadata'])
    assert record['metadata']['metadata_status']=='DECLARED'
    assert record['metadata']['beam']['selected_static']['load_parameter']==.5


@pytest.mark.parametrize('damage',['none','missing_reference','missing_beam','unknown_clock','wrong_unit','wrong_axis','no_static'])
def test_registration_and_post_refuse_missing_or_forged_declarations(tmp_path,produced,native,damage):
    _,view,metadata=produced;_,_,external=native
    if damage=='none':metadata=None
    elif damage=='missing_reference':metadata.pop('beam_inspection')
    elif damage=='missing_beam':metadata.pop('beam')
    elif damage=='unknown_clock':metadata['time']['semantics']='UNKNOWN'
    elif damage=='wrong_unit':metadata['arrays'][-1]['units']='MPa'
    elif damage=='wrong_axis':metadata['beam']['axes']['local1']=[0,0,1]
    else:metadata.pop('static')
    with pytest.raises(ValueError):
        register_native_input(tmp_path/'wb',view.parent,view,'Dfailed',root_id='raw',relative='beam.pvd',limit=8*1024**2,native_metadata=metadata)
    with pytest.raises(ValueError):external.source_files(view,metadata)
    assert not (tmp_path/'wb/inputs/Dfailed/input.json').exists()


@pytest.mark.parametrize('channel',list(CHANNELS))
def test_component_selection_real_vtk_unit_location_and_scalar_legend(tmp_path,produced,native,channel):
    p,_,external=native
    _,_,resolved=register(tmp_path,produced)
    path=external.open_result(resolved['path'],tmp_path/'project',resolved['id'],resolved['source_pins'],resolved['native_metadata'])
    source=p.GetActiveSource()
    selected=external.select_array(source,'POINTS',channel,time=1.)
    assert selected['units']==CHANNELS[channel][2] and selected['metadata_status']=='DECLARED'
    assert selected['location']=='ORIGINAL_BEAM_NODES' and selected['time_units']=='1'
    assert selected['time_semantics']=='STATIC_LOAD_PARAMETER'
    assert selected['beam']['selected_static']=={'step':1,'increment':2,'load_parameter':1.}
    bar=p.GetScalarBar(channel,p.GetActiveView())
    assert bar.Title==CHANNELS[channel][4]+' ['+CHANNELS[channel][2]+']'
    assert 'MPa' not in bar.Title


def test_vector_names_select_and_saved_metadata_reopen_in_new_process(tmp_path,produced,native):
    p,_,external=native
    _,_,resolved=register(tmp_path,produced)
    project=external.open_result(resolved['path'],tmp_path/'project',resolved['id'],resolved['source_pins'],resolved['native_metadata'])
    source=p.GetActiveSource()
    external.select_array(source,'POINTS','U_mm',component='UZ',time=.5)
    assert p.GetScalarBar('U_mm',p.GetActiveView()).ComponentTitle=='UZ'
    chosen=external.select_array(source,'POINTS','M1',time=1.)
    document=json.loads(project.read_text(encoding='utf-8'));saved=external.save_project(project,document)
    snapshot=json.loads(saved.read_text(encoding='utf-8'))
    assert snapshot['sources']['result']['native_metadata']==resolved['native_metadata']
    assert len(snapshot['sources']['result']['source_pins'])>10
    # Remove the calculation origin: only the registered copy may be used.
    shutil.rmtree(produced[0])
    code=r'''
import json,sys,os
from pathlib import Path
from test_beam_post_support import install
p,sm,external=install()
path=Path(sys.argv[1]);doc=json.loads(path.read_text(encoding='utf-8'));os.environ['CAE_POST_PROJECT']=str(path)
external.restore_workspace(path,doc)
source=p.GetActiveSource();view=p.GetActiveView()
assert p.Show(source,view).selection==('POINTS','M1')
assert p.GetScalarBar('M1',view).Title=='1축 굽힘 모멘트 [Nmm]'
assert p.GetAnimationScene().AnimationTime==1.
meta=external.inspect_result(source)
assert meta['beam']['selected_static']['increment']==2
assert meta['time_units']=='1' and meta['time_semantics']=='STATIC_LOAD_PARAMETER'
assert meta['beam']['unavailable']['rotation_rad']
external.select_array(source,'POINTS','RF_X_raw',time=.5)
assert p.GetScalarBar('RF_X_raw',view).Title=='X 절점 RF (원출력) [N]'
print('FRESH_PROCESS_POST_CONTRACT_OK')
'''
    root=Path(__file__).resolve().parents[1]
    env={**os.environ,'PYTHONPATH':str(root)+os.pathsep+str(root/'tests')}
    result=subprocess.run([sys.executable,'-c',code,str(saved)],capture_output=True,text=True,cwd=root,env=env)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'FRESH_PROCESS_POST_CONTRACT_OK' in result.stdout


def test_changed_copied_raw_source_blocks_post_reopen(tmp_path,produced,native):
    p,_,external=native;_,_,resolved=register(tmp_path,produced)
    project=external.open_result(resolved['path'],tmp_path/'project',resolved['id'],resolved['source_pins'],resolved['native_metadata'])
    document=json.loads(project.read_text(encoding='utf-8'))
    frd=Path(resolved['path']).parent/'source/solver/beam.frd';frd.write_bytes(frd.read_bytes()+b'changed')
    with pytest.raises((ValueError,RuntimeError)):external.restore_workspace(project,document)
