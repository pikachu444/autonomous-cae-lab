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
        'snapshot_id': 'Ftest', 'snapshot_sha256': '1'*64, 'raw_frd_sha256': hashlib.sha256(frd_path.read_bytes()).hexdigest(),
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
    with pytest.raises(ValueError, match='increment|physical declaration'):
        load(folder/'contact.pvd', file_pin(manifest_path, folder))


@pytest.mark.parametrize('field,value', [('force_unit', 'kN'), ('force_frame', 'LOCAL'),
    ('clock', {'unit': 's', 'semantics': 'PHYSICAL_TIME'}), ('active_state', 'ACTIVE'), ('source', {})])
def test_physical_declarations_are_verified_not_relabelled(bundle_files, field, value):
    folder, metadata = bundle_files
    path = folder/'contact-inspection.json'
    manifest = json.loads(path.read_text())
    manifest[field] = value
    path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='physical declaration|identities'):
        load(folder/'contact.pvd', file_pin(path, folder))


def force_snapshot(tmp_path, bundle_files, component=2):
    """Saved native transport fixture, explicitly distinct from ParaView execution."""
    from test_post_numerical import fixture_snapshot
    from caelab.post_observation import file_pin as absolute_pin
    from caelab.storage import canonical_hash
    snapshot, command = fixture_snapshot(tmp_path)
    folder, metadata = bundle_files
    bundle = load(folder/'contact.pvd', metadata['contact_inspection'])
    history = force_history(bundle, 'Contact', 'CFN', component)
    recipe = {'source_ref': 'Sfirst', 'measurement': 'contact_force', 'association': 'ROWS',
        'pair_id': 'Contact', 'quantity': 'CFN', 'component': component, 'array': history['array'],
        'units': 'N', 'frame': history['frame'], 'measure': history['measure'],
        'axis_name': 'load_parameter', 'axis_unit': '1', 'time_units': '1',
        'time_origin': 'STATIC_LOAD_PARAMETER', 'inspection_sha256': metadata['contact_inspection']['sha256']}
    summary = {**recipe, 'component_label': 'CFN global ' + 'XYZ'[component],
        'location': 'Pad contact / Contact', 'axis_values': [.5, 1.], 'force_rows': history['rows']}
    rows = [{'block': [], 'row': i, 'values': {
        'load_parameter': row['static']['load_parameter'], history['array']: row['value'],
        'vtkValidMask': int(row['valid']), 'step': 1, 'increment': i+1},
        'validity': {history['array']: 'valid' if row['valid'] else row['reason']}}
        for i, row in enumerate(history['rows'])]
    origin = snapshot['origin']
    path = Path(origin['project']['path'])
    project = json.loads(path.read_text())
    obj = project['analysis']['objects']['Ameasure']
    obj['draft'] = recipe
    record = obj['history'][0]
    record.update(recipe=recipe, summary=summary)
    result = Path(record['result_file'])
    result.write_text('load_parameter,' + history['array'] + '\n' +
        '\n'.join(str(r['static']['load_parameter']) + ',' + (str(r['value']) if r['valid'] else 'nan')
                  for r in history['rows']) + '\n', encoding='utf-8', newline='\n')
    record.update(result_files=[absolute_pin(result)], result_sha256=absolute_pin(result)['sha256'])
    path.write_text(json.dumps(project), encoding='utf-8')
    origin.update(project=absolute_pin(path), recipe_sha256=canonical_hash(recipe),
        result_files_sha256=canonical_hash(record['result_files']), result_sha256=record['result_sha256'])
    snapshot.update(recipe=recipe, summary=summary, rows=rows)
    payload = command['outcome']['result']['result']
    output = Path(payload['snapshot']['path'])
    output.write_text(json.dumps(snapshot), encoding='utf-8')
    payload.update(origin=origin, snapshot=absolute_pin(output), rows=len(rows))
    return snapshot, command


def force_selection(snapshot):
    return {'block': [], 'value_array': snapshot['recipe']['array'], 'value_component': None,
        'axis': {'kind': 'array', 'name': 'load_parameter', 'component': None},
        'unit': 'N', 'axis_name': 'load_parameter', 'axis_unit': '1',
        'component_label': snapshot['summary']['component_label'], 'location': snapshot['summary']['location'],
        'frame': 'FREECAD_DOCUMENT_GLOBAL', 'measure': 'contact_pair_force_resultant',
        'role': 'fit', 'exclude_invalid': False}


def test_force_projection_exact_axis_raw_quality_and_explicit_manifest(bundle_files, tmp_path):
    from caelab.post_observation import project_samples, completed_snapshot
    from caelab.adapters.file_table import read_table
    from caelab.contact_inspection import explicit_manifest
    folder, metadata = bundle_files
    entry, declared = explicit_manifest(folder/'contact-inspection.json')
    assert entry == folder/'contact.pvd' and declared == metadata
    snapshot, command = force_snapshot(tmp_path, bundle_files, component=0)
    assert completed_snapshot(command) == snapshot
    selected = force_selection(snapshot)
    projected = project_samples(snapshot, selected)
    assert [r['axis'] for r in projected['rows']] == [.5, 1.]
    assert projected['rows'][0]['value'] == 0 and projected['rows'][0]['valid']
    assert projected['rows'][1]['value'] is None and not projected['importable']
    projected = project_samples(snapshot, dict(selected, exclude_invalid=True))
    table = tmp_path/'force.csv'
    table.write_bytes(projected['csv'])
    raw = read_table(table, projected['mapping'])['responses']['measured']['raw_samples']
    assert raw['value'][0] == 0 and raw['quality_valid'] == [True, False]
    assert raw['calculation_valid'] == [True, False]
    assert raw['quality_reasons'][1] == 'native_nonfinite_or_overflow:NaN'
    for edit in ({'axis_unit': 's'}, {'component_label': 'CFN global Y'}, {'location': 'Master B'}):
        with pytest.raises(ValueError, match='saved pair'):
            project_samples(snapshot, dict(selected, **edit))


@pytest.mark.parametrize('edit', ['missing', 'units', 'frame', 'measure', 'components'])
def test_geometric_gap_declaration_cannot_be_relabelled(bundle_files, edit):
    folder, _ = bundle_files
    path = folder/'contact-inspection.json'
    manifest = json.loads(path.read_text())
    arrays = manifest['native_metadata']['arrays']
    gap = next(row for row in arrays if row['name'] == 'GeomGap_mm')
    if edit == 'missing':
        arrays.remove(gap)
    else:
        gap[edit] = {'units': 'm', 'frame': 'GLOBAL', 'measure': 'solver_clearance', 'components': 3}[edit]
    path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='geometric gap native physical declaration'):
        load(folder/'contact.pvd', file_pin(path, folder))


@pytest.mark.parametrize('key,value', [('method', 'nearest_node_distance'),
    ('sign', 'positive_penetration'), ('deformed_mesh', False), ('subdivisions_per_edge', 0)])
def test_geometric_gap_recipe_requires_supported_meaning(bundle_files, key, value):
    folder, _ = bundle_files
    path = folder/'contact-inspection.json'
    manifest = json.loads(path.read_text())
    pin = manifest['frames'][0]['inspection']
    frame_path = folder/pin['relative']
    frame = json.loads(frame_path.read_text())
    frame['gap']['recipe'][key] = value
    frame_path.write_text(json.dumps(frame), encoding='utf-8')
    manifest['frames'][0]['inspection'] = file_pin(frame_path, folder)
    path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='projection/gap physical declaration'):
        load(folder/'contact.pvd', file_pin(path, folder))
