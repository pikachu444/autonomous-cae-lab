"""Synthetic native-shaped results, real raw admission and VTK, no solver evidence."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import pytest
from caelab import beam_inspection as api
from caelab.beam_results import CHANNELS, sha
from caelab.storage import save_json
from caelab.adapters import beam_fem
from test_beam_support import model, snapshot
from test_beam_adapter import runner


@pytest.fixture
def produced(tmp_path,monkeypatch):
    source=snapshot(tmp_path/'input');calls=runner(monkeypatch,tmp_path)
    folder=tmp_path/'run'
    execution=beam_fem.BeamFemCalculixAdapter().run({'snapshot_path':str(source)},output=folder)
    assert execution['execution_status']=='SUCCEEDED',execution
    assert len(calls)==1 and calls[0][0][-2:]==['-i','beam']  # Windows -v fix is preserved.
    artifact=execution['post_artifact'];view=folder/artifact['relative']
    return folder,view,deepcopy(artifact['native_metadata'])


def reseal(view):
    """Adversarial rehash, not a way to regenerate engineering observations."""
    path=view.parent/api.MANIFEST;manifest=json.loads(path.read_text(encoding='utf-8'))
    for row in manifest['files']:
        source=view.parent/row['relative'];row.update(bytes=source.stat().st_size,sha256=sha(source))
    save_json(path,manifest)
    return {'relative':api.MANIFEST,'bytes':path.stat().st_size,'sha256':sha(path)}


def test_bundle_retains_raw_source_and_real_static_parameters(produced):
    folder,view,metadata=produced
    result=api.validate_metadata(view,metadata)
    assert metadata['static'] is None
    assert metadata['time']=={'unit':'1','semantics':'STATIC_LOAD_PARAMETER','values':[.5,1.]}
    assert metadata['beam']['frames'][0]=={'step':1,'increment':1,'load_parameter':.5}
    names={p.relative_to(view.parent).as_posix() for p in result['paths']}
    assert {'source/solver/beam.frd','source/solver/beam.inp','source/frozen_input/mesh.json',
        'source/frozen_input/editable.FCStd','source/frozen_input/editable.caepre','source/frozen_input/snapshot.json',
        'beam_0000.csv','beam_0001.vtu','beam_fields.json','source/execution.json'}<=names
    assert not any(Path(p).is_absolute() for p in names)
    chosen=api.inspect(view,node_id=101,component='M1',load_parameter=.5)
    assert chosen['value']==27.5 and chosen['unit']=='Nmm' and chosen['source_component']=='SYZ'
    assert chosen['static']['load_parameter']==.5 and 'rotation_rad' in chosen['unavailable']


@pytest.mark.parametrize('channel',list(CHANNELS))
def test_all_components_real_vtk_values_names_and_units(produced,channel):
    vtk=pytest.importorskip('vtk')
    _,view,metadata=produced
    reader=vtk.vtkXMLUnstructuredGridReader();reader.SetFileName(str(view.parent/'beam_0001.vtu'));reader.Update()
    grid=reader.GetOutput();assert grid.GetNumberOfPoints()==5 and grid.GetNumberOfCells()==2
    assert grid.GetCellType(0)==21
    vector=grid.GetPointData().GetArray('U_mm')
    assert [vector.GetComponentName(i) for i in range(3)]==['UX','UY','UZ']
    expected=api.inspect(view,node_id=101,component=channel)
    assert grid.GetPointData().GetArray(channel).GetTuple1(0)==expected['value']
    decl=next(r for r in metadata['arrays'] if r['name']==channel)
    assert decl['units']==expected['unit'] and decl['location']=='ORIGINAL_BEAM_NODES'
    assert grid.GetPointData().GetArray('STRESS') is None


@pytest.mark.parametrize('damage',['raw_value','raw_mesh','deck','model_axes','values','vtu_value','vtu_order',
                                   'csv','pvd','frame_meaning','unit','partial','execution','source_binding'])
def test_rehashed_manipulations_still_reject_numerical_or_semantic_mismatch(produced,damage):
    _,view,_=produced;root=view.parent
    if damage in ('raw_value','raw_mesh'):
        path=root/'source/solver/beam.frd'
        raw=path.read_text(encoding='utf-8')
        raw=raw.replace(' 5.50000E+01',' 7.50000E+01') if damage=='raw_value' else raw.replace(' -2       207       509       913',' -2       207       913       509')
        path.write_text(raw)
    elif damage=='deck':
        path=root/'source/solver/beam.inp';path.write_text(path.read_text(encoding='utf-8').replace('509,5,1000','509,5,2000'))
    elif damage=='model_axes':
        path=root/'source/frozen_input/mesh.json';data=json.loads(path.read_text(encoding='utf-8'));data['axes']['local1']=[0,0,1];save_json(path,data)
        # Even update the snapshot hashes and context input pins: axis/model contract must reject.
        sp=root/'source/frozen_input/snapshot.json';sm=json.loads(sp.read_text(encoding='utf-8'))
        for row in sm['files']:
            p=sp.parent/row['relative'];row.update(bytes=p.stat().st_size,sha256=sha(p))
        save_json(sp,sm)
        cp=root/api.CONTEXT;c=json.loads(cp.read_text(encoding='utf-8'))
        c['input_pins']={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sp.parent.iterdir()};save_json(cp,c)
    elif damage in ('values','frame_meaning','unit','partial','source_binding'):
        path=root/'beam_fields.json';data=json.loads(path.read_text(encoding='utf-8'))
        if damage=='values':data['observed']['frames'][-1]['native_fields']['STRESS']['101'][4]=1234
        if damage=='frame_meaning':data['native_metadata']['time']['unit']='s'
        if damage=='unit':data['native_metadata']['arrays'][-1]['units']='MPa'
        if damage=='partial':data['observed']['complete_file']=False
        if damage=='source_binding':data['model']['draft']['mesh_id']='OtherMesh'
        save_json(path,data)
        # Keep manifest and table meanings consistent with each other, but not native FRD.
        mp=root/api.MANIFEST;m=json.loads(mp.read_text(encoding='utf-8'));m['native_metadata']=data['native_metadata'];save_json(mp,m)
    elif damage in ('vtu_value','vtu_order'):
        path=root/'beam_0001.vtu';tree=ET.parse(path)
        elem=tree.find(".//DataArray[@Name='M1']" if damage=='vtu_value' else ".//DataArray[@Name='connectivity']")
        elem.text='1234 55 55 55 55' if damage=='vtu_value' else '3 1 4 0 1 2'
        tree.write(path,encoding='utf-8',xml_declaration=True)
    elif damage=='csv':
        path=root/'beam_0000.csv';path.write_bytes(path.read_bytes().replace(b'27.5',b'99.9'))
    elif damage=='pvd':
        view.write_bytes(view.read_bytes().replace(b'timestep="0.5"',b'timestep="0.6"'))
    else:
        path=root/api.CONTEXT;data=json.loads(path.read_text(encoding='utf-8'));data['native_return_code']=201;save_json(path,data)
    reference=reseal(view)
    with pytest.raises(ValueError):api.load(view,reference)


@pytest.mark.parametrize('damage',['traversal','absolute','duplicate','symlink','missing','unavailable'])
def test_bundle_paths_missing_data_and_metadata_forgery_are_rejected(produced,damage,tmp_path):
    _,view,_=produced;path=view.parent/api.MANIFEST;m=json.loads(path.read_text(encoding='utf-8'))
    if damage=='traversal':m['files'][0]['relative']='../beam_fields.json'
    elif damage=='absolute':m['files'][0]['relative']=str(view)
    elif damage=='duplicate':m['files'].append(m['files'][0])
    elif damage=='missing':m['files']=[r for r in m['files'] if r['relative']!='source/solver/beam.frd']
    elif damage=='unavailable':m['native_metadata']['beam']['unavailable']={}
    else:
        src=view.parent/'source/solver/beam.frd';dst=tmp_path/'foreign.frd';shutil.copyfile(src,dst);src.unlink()
        try:
            src.symlink_to(dst)
        except OSError as exc:
            if getattr(exc, 'winerror', None) == 1314:
                pytest.skip('Windows account cannot create a symlink; rejection remains covered on capable hosts')
            raise
    save_json(path,m)
    with pytest.raises(ValueError):api.load(view)


def test_new_process_reopens_after_original_run_is_removed(produced,tmp_path):
    folder,view,metadata=produced
    exported=api.export_saved_run(folder,tmp_path/'portable')
    assert api.load(view)['manifest']['native_metadata']==api.load(exported.parent/'beam.pvd')['manifest']['native_metadata']
    shutil.rmtree(folder)
    command=[sys.executable,'-m','caelab.beam_inspection',str(exported)]
    done=subprocess.run(command,capture_output=True,text=True,check=True,cwd=Path(__file__).resolve().parents[1])
    data=json.loads(done.stdout)
    assert data['time']['values']==[.5,1.] and data['beam']['source_execution_status']=='SUCCEEDED'
    assert data['beam']['unavailable']['support_reaction_moment_Nmm']


@pytest.mark.parametrize('status,stop',[('FAILED',None),('CANCELLED',beam_fem.ExecutionCancelled)])
def test_partial_failure_and_cancel_bundle_keeps_only_complete_frames(tmp_path,monkeypatch,status,stop):
    source=snapshot(tmp_path/'input');runner(monkeypatch,tmp_path,cut=True,stop=stop)
    out=tmp_path/'run';result=beam_fem.BeamFemCalculixAdapter().run({'snapshot_path':str(source)},output=out)
    assert result['execution_status']==status
    meta=result['post_artifact']['native_metadata'];checked=api.validate_metadata(out/'post/beam.pvd',meta)
    assert meta['time']['values']==[.5] and meta['beam']['observation_status']=='PARTIAL'
    assert checked['data']['observed']['complete_file'] is False
    assert len(checked['data']['observed']['frames'])==1


def test_replaced_frd_and_matching_observation_table_cannot_hide_stale_view(produced):
    _,view,_=produced;root=view.parent
    raw=root/'source/solver/beam.frd';raw.write_bytes(raw.read_bytes().replace(b' 5.50000E+01',b' 7.50000E+01'))
    table=root/'beam_fields.json';data=json.loads(table.read_text(encoding='utf-8'))
    for rows in data['observed']['frames'][-1]['native_fields']['STRESS'].values():rows[4]=75.
    save_json(table,data)
    with pytest.raises(ValueError,match='numeric observations'):api.load(view,reseal(view))


def test_swapped_local_axes_with_rehashed_derived_meanings_still_reject(produced):
    _,view,_=produced;root=view.parent
    for name in ('beam_fields.json',api.MANIFEST):
        path=root/name;data=json.loads(path.read_text(encoding='utf-8'));axis=data['native_metadata']['beam']['axes']
        axis['local1'],axis['local2']=axis['local2'],axis['local1'];save_json(path,data)
    with pytest.raises(ValueError):api.load(view,reseal(view))


def test_export_does_not_mutate_old_attempt_or_execute(produced,tmp_path,monkeypatch):
    folder,view,_=produced
    before={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob('*') if p.is_file()}
    monkeypatch.setattr(beam_fem,'run_owned_command',lambda *a,**kw:pytest.fail('Read/export must not execute a solver'))
    exported=api.export_saved_run(folder,tmp_path/'portable')
    assert before=={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob('*') if p.is_file()}
    assert api.explicit_manifest(exported)[1]['beam']['source_execution_status']=='SUCCEEDED'


@pytest.mark.parametrize('damage', ['missing_source', 'document', 'endpoint', 'mesh_binding'])
def test_rehashed_native_source_identity_is_required_and_matches_snapshot(tmp_path, monkeypatch, damage):
    value = model()
    source = snapshot(tmp_path/'input', value)
    mesh = source.parent/'mesh.json'; data = json.loads(mesh.read_text(encoding='utf-8'))
    if damage == 'missing_source': data.pop('source')
    elif damage == 'document': data['source']['document_id'] = 'DifferentDocument'
    elif damage == 'endpoint': data['source']['binding']['ends'][1]['subelement'] = 'Vertex1'
    else: data['source']['binding']['mesh_sha256'] = '0'*64
    save_json(mesh, data)
    manifest = json.loads(source.read_text(encoding='utf-8'))
    for row in manifest['files']:
        path = source.parent/row['relative']; row.update(bytes=path.stat().st_size, sha256=sha(path))
    save_json(source, manifest)
    runner(monkeypatch, tmp_path)
    result = beam_fem.BeamFemCalculixAdapter().run({'snapshot_path':str(source)}, output=tmp_path/'run')
    assert result['execution_status'] == 'FAILED'
    assert 'post_artifact' not in result
    assert (tmp_path/'run/solver/beam.frd').is_file()  # Preserve original failed attempt.
