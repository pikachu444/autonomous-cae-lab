"""Retained synthetic bytes only. No solver, ParaView or physical acceptance."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import pytest

from test_contact_execution import model, native_outputs
from caelab.adapters.contact_results import write_post, read_dat
from caelab.adapters.frozen_fem import read_frd
from caelab.contact_deck import validate_model
from caelab.contact_inspection import load, inspect, file_pin, force_history
from caelab.native_inputs import register_native_input


@pytest.fixture
def bundle_files(model, tmp_path):
    frd, dat, materials = native_outputs(model)
    frd_path, dat_path = tmp_path/'contact.frd', tmp_path/'contact.dat'
    frd_path.write_text(frd, encoding='ascii', newline='\n')
    dat_path.write_text(dat, encoding='ascii', newline='\n')
    nodes, elements, _ = validate_model(model)
    frames = read_frd(frd_path, nodes, elements, contact_materials=materials)['frames']
    rows = read_dat(dat_path, model['contacts'], frames)
    # A finite genuine zero and a missing quantity must remain distinguishable.
    rows[1]['force_N'][0] = 0.
    rows[4]['force_N'][0] = None
    rows[4]['quality_reasons'][0][0] = 'native_nonfinite_or_overflow:NaN'
    folder = tmp_path/'post'
    metadata = write_post(folder, model, frames, rows, provenance={
        'snapshot_id': 'Ftest', 'raw_frd_sha256': hashlib.sha256(frd_path.read_bytes()).hexdigest(),
        'raw_dat_sha256': hashlib.sha256(dat_path.read_bytes()).hexdigest()})
    return folder, metadata


def test_bundle_admission_exact_faces_frames_and_pair_force(bundle_files, tmp_path):
    folder, metadata = bundle_files
    entry = folder/'contact.pvd'
    bundle = load(entry, metadata['contact_inspection'])
    selection = inspect(bundle, 'Contact', 'both', 0, 'CPRESS', 'CFN', 2)
    assert selection['static'] == {'step': 1, 'increment': 1, 'load_parameter': .5}
    assert selection['scope'] == 'shared_nodal_projection'
    assert {row['value'] for row in selection['rows']} == {6.}
    assert selection['active_state'] == 'UNKNOWN'
    assert [row['value'] for row in selection['history']['rows']] == [1., 2.]
    a, b = bundle['pairs']['Contact']['a'], bundle['pairs']['Contact']['b']
    assert not set(a['node_ids']) & set(b['node_ids'])
    assert a['surface_index'] != b['surface_index']
    zero_missing = force_history(bundle, 'Contact', 'CFN', 0)
    assert zero_missing['rows'][0]['value'] == 0 and zero_missing['rows'][0]['valid']
    assert zero_missing['rows'][1]['value'] is None and not zero_missing['rows'][1]['valid']
    assert 'native_nonfinite' in zero_missing['rows'][1]['reason']
    assert zero_missing['axis'] == {'name': 'load_parameter', 'unit': '1', 'semantics': 'STATIC_LOAD_PARAMETER'}
    receipt = register_native_input(tmp_path/'store', folder, entry, 'Dcontact',
        root_id='job:Jretained', relative='contact.pvd', limit=16*1024**2, native_metadata=metadata)
    retained = tmp_path/'store'/receipt['file']
    admitted = load(retained, receipt['native_metadata']['contact_inspection'])
    assert admitted['frames'] == bundle['frames']
    assert receipt['origin']['root_id'] == 'job:Jretained'
    assert 'contact-topology.json' in {Path(pin['relative']).name for pin in receipt['files']}
    # Ordinary PVD registration never adopts neighbouring sidecars.
    ordinary = register_native_input(tmp_path/'ordinary', folder, entry, 'Dplain',
        root_id='local', relative='contact.pvd', limit=16*1024**2)
    assert all(Path(pin['relative']).suffix in ('.pvd', '.vtu') for pin in ordinary['files'])
    assert not any(Path(pin['relative']).name == 'contact-surfaces.vtu' for pin in ordinary['files'])


def test_sidecar_tamper_and_exact_relocation(bundle_files, tmp_path):
    folder, metadata = bundle_files
    clone = tmp_path/'relocated'
    shutil.copytree(folder, clone)
    assert load(clone/'contact.pvd', metadata['contact_inspection'])['frames'] == load(
        folder/'contact.pvd', metadata['contact_inspection'])['frames']
    (clone/'frame0001.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='Contact member'):
        load(clone/'contact.pvd', metadata['contact_inspection'])
    manifest_path = folder/'contact-inspection.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['frames'][0]['static']['load_parameter'] = .7
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='increment'):
        load(folder/'contact.pvd', file_pin(manifest_path, folder))
