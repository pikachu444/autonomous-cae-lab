"""Retained-record and native-shaped Save checks; no native application/solve."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from caelab.adapters import retained_law_responses as retained
from caelab.adapters.native_responses import catalog_native_responses, read_native_response
from test_retained_law_responses import saved_material, write_json, pin, no_solver
from test_desktop_post_bridge import bridge, save_commands
from test_post_r3_repairs import post_modules, state_xml


def saved_svk(path):
    """Existing manufactured observation, with the actual producer envelope."""
    outcome, raw = saved_material(path, retained.SVK)
    settings = json.loads((path / 'input.json').read_text(encoding='utf-8'))['settings']
    policy = {'solver_memory_mb': 1024, 'solver_time_seconds': 86400,
              'subprocess_timeout_seconds': None, 'solver_time_source': 'PINNED_RUN_ASTER_DEFAULT',
              'wall_time_source': 'NO_WALL_TIME_LIMIT', 'qualification': 'UNKNOWN'}
    envelope = {'settings': settings, 'captured_source_sha256': deepcopy(raw['captured_source_sha256']),
                'process_policy': deepcopy(policy)}
    write_json(path / 'input.json', envelope)
    raw.update(input_sha256=pin(path / 'input.json'), process_policy=deepcopy(policy))
    outcome['provenance'].update(input_sha256=raw['input_sha256'], process_policy=deepcopy(policy))
    write_json(path / 'native_raw.json', raw)
    write_json(path / 'analysis_raw.json', outcome)
    return outcome, raw, envelope


def test_svk_actual_input_envelope_reads_captured_native_stress_and_energy(tmp_path):
    outcome, raw, envelope = saved_svk(tmp_path)
    catalog = catalog_native_responses(retained.SVK, outcome, tmp_path)
    stress = read_native_response(retained.SVK, outcome, tmp_path, 'mgis-pk1-xx', start=1, stop=3)
    energy = read_native_response(retained.SVK, outcome, tmp_path, 'mgis-stored', start=1, stop=3)
    assert stress['value'] == [step['pk1_stress_mpa'][0] for step in raw['steps'][1:3]]
    assert energy['value'] == [step['stored_energy_density_mpa'] for step in raw['steps'][1:3]]
    assert stress['axes'][0]['values'] == [row['time_s'] for row in envelope['settings']['history'][2:4]]
    assert stress['source']['sha256'] == catalog['mgis-pk1-xx']['source']['sha256']
    assert stress['source']['value_origin'] == energy['source']['value_origin'] == 'NATIVE'
    assert stress['initial_state']['kind'] == 'UNPREPARED_INITIAL_CONDITION_EXCLUDED'
    assert stress['qualification'] == {'physical': 'UNKNOWN', 'decision': 'NOT_RELEASED'}


@pytest.mark.parametrize('change', ['input_inventory', 'input_policy', 'raw_policy', 'original_source',
                                   'input_settings', 'input_shape', 'native_stress', 'input_bytes'])
def test_svk_envelope_capture_policy_and_observation_tampering_refused(tmp_path, change):
    outcome, raw, envelope = saved_svk(tmp_path)
    if change == 'input_inventory':
        envelope['captured_source_sha256']['domain_reference.py'] = '0' * 64
    elif change == 'input_policy':
        envelope['process_policy']['solver_time_seconds'] = 1
        envelope['process_policy']['solver_time_source'] = 'USER_ENVIRONMENT'
    elif change == 'raw_policy':
        raw['process_policy']['solver_time_seconds'] = 1
    elif change == 'original_source':
        (tmp_path / 'domain_reference.py').write_bytes(b'CHANGED_CAPTURE_NOT_A_CURRENT_SOURCE')
    elif change == 'input_settings':
        envelope['settings']['history'][1]['time_s'] += .01
    elif change == 'input_shape':
        envelope = envelope['settings']
    elif change == 'native_stress':
        raw['steps'][1]['pk1_stress_mpa'][0] += 1
    if change == 'input_bytes':
        (tmp_path / 'input.json').write_bytes((tmp_path / 'input.json').read_bytes() + b' ')
    else:
        write_json(tmp_path / 'input.json', envelope)
        # Rebind byte hashes deliberately: envelope inventory/policy/physical
        # meaning must still be verified beyond a self-consistent input hash.
        raw['input_sha256'] = pin(tmp_path / 'input.json')
        outcome['provenance']['input_sha256'] = raw['input_sha256']
        write_json(tmp_path / 'native_raw.json', raw)
        write_json(tmp_path / 'analysis_raw.json', outcome)
    with pytest.raises(ValueError):
        catalog_native_responses(retained.SVK, outcome, tmp_path)


def test_managed_macro_reaches_same_actual_owner_without_global_source_guard(bridge, save_commands, monkeypatch):
    owner = bridge.module.Owner(); save_commands.set_save_owner(owner)
    bridge.source.edit('PointArrays', ['response', 'edited'])
    calls = []
    def unavailable():
        calls.append('global_guard')
        raise FileNotFoundError('B.vtu unavailable; healthy A remains')
    monkeypatch.setattr(save_commands, 'verify_sources', unavailable)
    saved = save_commands.save_project()
    assert saved.is_file() and not calls
    assert len(bridge.saved) == 1 and not owner.descriptor()['dirty']
    assert bridge.saved[0]['generation'] == owner.generation
    save_commands.clear_save_owner(owner)


def test_standalone_macro_keeps_original_global_source_safeguard(bridge, save_commands, monkeypatch):
    save_commands._save_owner = None
    def unavailable(): raise FileNotFoundError('B.vtu unavailable')
    monkeypatch.setattr(save_commands, 'verify_sources', unavailable)
    with pytest.raises(FileNotFoundError, match='B.vtu'):
        save_commands.save_project()
    assert bridge.saved == []


def test_managed_macro_partial_save_preserves_b_recipe_and_healthy_a_state(post_modules, tmp_path, monkeypatch):
    vtk = pytest.importorskip('vtk')
    commands, external, native = post_modules.commands, post_modules.external, post_modules.native
    path = tmp_path / 'A.vtu'
    writer = vtk.vtkXMLUnstructuredGridWriter(); writer.SetFileName(str(path))
    writer.SetInputData(vtk.vtkUnstructuredGrid()); assert writer.Write() == 1
    a = {'reader_name': 'A', 'reader_type': 'XMLUnstructuredGridReader', 'entry_path': str(path), 'source_pins': external.pins([path])}
    b = deepcopy(a); b.update(reader_name='B', entry_path=str(tmp_path / 'B.vtu'))
    b['source_pins'][0]['path'] = b['entry_path']
    source = SimpleNamespace(FileName=[str(path)], GetXMLName=lambda: 'XMLUnstructuredGridReader')
    source.SMProxy = source; native.sources = {('A', 0): source}; native.active = source
    original = state_xml(tmp_path / 'original.pvsm')
    native.SaveState = lambda target: post_modules.source_repair.partial_state(original, {}, [{'reader_name': 'B'}], target)
    document = {'kind': external.KIND, 'project_root': str(tmp_path), 'sources': {'SA': a, 'SB': b}, 'partial_workspace': True,
        'native_readers': [{'reader_name': record['reader_name'], 'reader_type': record['reader_type'], 'input_paths': [record['entry_path']]} for record in (a, b)]}
    project = tmp_path / 'project.json'; project.write_text(json.dumps(document), encoding='utf-8')
    monkeypatch.setenv('CAE_POST_PROJECT', str(project))
    with pytest.raises(FileNotFoundError): commands.save_project()
    managed = SimpleNamespace(assert_thread=lambda: None, save_project=lambda: external.save_project(project, document))
    commands.set_save_owner(managed)
    saved = json.loads(commands.save_project().read_text(encoding='utf-8'))
    assert saved['sources']['SB'] == b
    assert saved['repair'][0]['source_ref'] == 'SB'
    assert [reader['reader_name'] for reader in saved['native_readers']] == ['A']
    assert path.is_file() and not (tmp_path / 'B.vtu').exists()
    commands.clear_save_owner(managed)
