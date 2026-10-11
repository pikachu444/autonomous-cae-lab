"""Controlled retained-output protocols; no native solver or physical proof."""
from copy import deepcopy
from pathlib import Path
import subprocess

import pytest

from caelab.adapters.native_responses import catalog_native_responses, read_native_response
from caelab.adapters import retained_law_responses as retained
from test_plasticity_response_fields import Fixture, payload


@pytest.fixture(autouse=True)
def no_solver(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Saved response reads must not execute a native process')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)


def saved_j2(tmp_path, *, selected=False, rejected=False):
    fixture = Fixture(selected=selected, rejected=rejected)
    for name, value in fixture.files.items():
        path = tmp_path / name.removeprefix('simulation/')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload(value))
    return fixture.files['simulation/analysis_raw.json'], fixture


@pytest.mark.parametrize('selected,rejected', [(False, False), (True, True)])
def test_j2_catalog_and_exact_native_point_histories(tmp_path, selected, rejected):
    outcome, fixture = saved_j2(tmp_path, selected=selected, rejected=rejected)
    catalog = catalog_native_responses(retained.J2, outcome, tmp_path)
    assert catalog['j2-gauss-mean-sixx']['reduction'] == 'unweighted_arithmetic_mean'
    assert catalog['j2-gauss-mean-sixx']['source']['native_origin']['aggregation']['volume_average'] is False
    assert catalog['j2.mesh0.DEPL.DX']['selector_template'] == 'j2.mesh0.DEPL.DX@<node_id>'
    choices = catalog['j2.mesh0.SIEF_ELGA.SIXX']['selectors']
    assert choices and len(choices) <= 256
    assert choices[0]['selector'].startswith('j2.mesh0.SIEF_ELGA.SIXX@')
    response = read_native_response(retained.J2, outcome, tmp_path, 'j2.mesh0.DEPL.DX@1', start=1, stop=3)
    record = outcome['mesh_records'][0]
    assert response['value'] == [state['displacements_mm'][0][0] for state in record['states'][1:3]]
    assert response['axes'][0]['values'] == [state['time_s'] for state in record['states'][1:3]]
    assert response['source']['sha256'] == catalog['j2.mesh0.DEPL.DX']['source']['sha256']
    assert response['source']['sample_sources'][1]['actual_result_order'] == record['states'][1]['actual_result_order']
    stress = read_native_response(retained.J2, outcome, tmp_path, 'j2.mesh0.SIEF_ELGA.SIXX@9:1:1')
    assert stress['unit'] == 'MPa' and stress['source']['exact_selection']['element_id'] == 9
    assert stress['qualification']['physical'] == 'UNKNOWN'
    for selector in ('j2.mesh0.DEPL.DX@999', 'j2.mesh0.DEPL.DX@1:1', 'j2.mesh0.SIEF_ELGA.SIXX@9:6:1',
                     'j2.mesh0.VARI_ELGA.V1@9:1:2', 'j2.mesh0.DEPL.DX', 'j2-gauss-mean-sixx@1'):
        with pytest.raises(ValueError):
            read_native_response(retained.J2, outcome, tmp_path, selector)


def test_j2_changed_table_source_or_foreign_outcome_is_refused(tmp_path):
    outcome, fixture = saved_j2(tmp_path)
    catalog_native_responses(retained.J2, outcome, tmp_path)
    foreign = deepcopy(outcome)
    foreign['mesh_records'][0]['node_ids'][0] = 999
    with pytest.raises(ValueError, match='retained bytes'):
        catalog_native_responses(retained.J2, foreign, tmp_path)
    table = tmp_path / 'level_1/order_3_depl.table.json'
    table.write_bytes(table.read_bytes().replace(b'0.000', b'0.001'))
    if table.read_bytes() == payload(fixture.files['simulation/level_1/order_3_depl.table.json']):
        table.write_bytes(table.read_bytes() + b' ')
    with pytest.raises(ValueError, match='manifested native table'):
        read_native_response(retained.J2, outcome, tmp_path, 'j2-x0-fx')


def test_j2_native_binary_hash_is_bound_to_saved_catalog_and_symlink_rejected(tmp_path):
    outcome, fixture = saved_j2(tmp_path)
    old = catalog_native_responses(retained.J2, outcome, tmp_path)
    med = tmp_path / 'level_0/results.med'
    med.write_bytes(b'CHANGED_TEST_ONLY_UNSOLVED_MED')
    new = catalog_native_responses(retained.J2, outcome, tmp_path)
    assert new['j2.mesh0.DEPL.DX']['source']['sha256'] != old['j2.mesh0.DEPL.DX']['source']['sha256']
    med.unlink()
    med.symlink_to(tmp_path / 'level_1/results.med')
    with pytest.raises(ValueError, match='symbolic link'):
        catalog_native_responses(retained.J2, outcome, tmp_path)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload(value))


def pin(path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def saved_material(tmp_path, backend):
    """Manufactured retained protocol only, explicitly not native execution."""
    if backend == retained.ELASTIC:
        from test_material_point_reference import observations
        from plugins.material_point import reference as domain
        from caelab.adapters import mfront_material as adapter
        (tmp_path / 'double').mkdir()
        settings, raw = observations(tmp_path / 'double')
        captures = {'domain_reference.py': b'TEST_ONLY_OLD_DOMAIN_SOURCE',
                    'mfront_material_worker.py': b'TEST_ONLY_OLD_WORKER_SOURCE'}
    elif backend == retained.SVK:
        from test_hyperelastic_reference import synthetic_raw
        from plugins.hyperelastic import reference as domain
        from caelab.adapters import mfront_hyperelastic as adapter
        settings = domain.canonical_settings()
        raw = synthetic_raw(settings)
        captures = {name: b'TEST_ONLY_OLD_SOURCE_' + name.encode() for name in adapter._SOURCES}
    else:
        from test_viscoelastic_reference import make_raw
        from plugins.material_point import viscoelastic_reference as domain
        from caelab.adapters import mfront_viscoelastic as adapter
        settings = domain.canonical_settings()
        work = tmp_path / 'double'
        work.mkdir()
        raw = make_raw(work, settings)
        captures = {name: b'TEST_ONLY_OLD_SOURCE_' + name.encode() for name in adapter.CAPTURE_NAMES.values()}
    for name, value in captures.items():
        (tmp_path / name).write_bytes(value)
    write_json(tmp_path / 'input.json', settings)
    library = tmp_path / 'build/src/libBehaviour.so'
    library.parent.mkdir(parents=True)
    library.write_bytes(b'TEST_ONLY_NOT_A_NATIVE_LIBRARY')
    library_sha = pin(library)
    raw['library_sha256'] = library_sha
    raw['mtest']['library_sha256'] = library_sha
    if 'mgis' in raw:
        raw['mgis']['library_sha256'] = library_sha
    raw.update(schema_version='1', input_sha256=pin(tmp_path / 'input.json'))
    runtime = {'python': 'TEST_ONLY_UNSOLVED', 'mgis': '3.0', 'tfel': 'tfel-config 5.0.0'}
    raw['runtime'] = runtime
    build = {'library_sha256': library_sha, 'library_path': 'build/src/libBehaviour.so'}
    write_json(tmp_path / 'runtime.json', runtime)
    write_json(tmp_path / 'build_identity.json', build)
    p = {'adapter': backend, 'adapter_version': '1', 'input_sha256': raw['input_sha256'], 'build': build,
         'versions': runtime, 'behaviour_description': raw.get('behaviour_description', {'TEST_ONLY': 'controlled capture'})}
    raw['behaviour_description'] = p['behaviour_description']
    if backend == retained.ELASTIC:
        raw.update(worker_sha256=pin(tmp_path / 'mfront_material_worker.py'), source_sha256='a' * 64,
                   conventions={'physical': 'xx,yy,zz,xy,xz,yz', 'native': 'xx,yy,zz,sqrt2*xy,sqrt2*xz,sqrt2*yz',
                                'strain': 'infinitesimal, not engineering shear', 'stress_unit': 'MPa'})
        p.update(worker_sha256=raw['worker_sha256'], behaviour_source_sha256=raw['source_sha256'],
                 domain_plugin={'source_sha256': pin(tmp_path / 'domain_reference.py')})
    elif backend == retained.SVK:
        raw.update(worker_sha256=pin(tmp_path / 'mfront_hyperelastic_worker.py'), source_sha256='a' * 64,
                   captured_source_sha256={name: pin(tmp_path / name) for name in captures},
                   finite_strain_options={'stress_measure': 'PK1', 'tangent_operator': 'DPK1_DF'},
                   conventions={'general_order': list(domain.F_COMPONENTS), 'stress_measure': 'PK1', 'tangent': 'rows_P_columns_F',
                                'stored_energy': 'native_per_reference_volume_MPa', 'MTest': 'Cauchy_Kelvin6'})
        p.update(captured_source_sha256=raw['captured_source_sha256'], finite_strain_options=raw['finite_strain_options'],
                 behaviour_source_sha256=raw['source_sha256'])
    else:
        from caelab.adapters import mfront_viscoelastic_worker as worker
        from caelab.storage import canonical_hash
        sources = {original: pin(tmp_path / name) for original, name in adapter.CAPTURE_NAMES.items()}
        raw.update(worker_sha256=sources['caelab/adapters/mfront_viscoelastic_worker.py'], source_files=sources,
                   transport_sha256=sources[worker.TRANSPORT_KEY], compiler_helper_sha256=sources[worker.COMPILER_HELPER_KEY],
                   conventions={'physical': 'xx,yy,zz,xy,xz,yz', 'native': 'xx,yy,zz,sqrt2*xy,sqrt2*xz,sqrt2*yz',
                                'strain': 'infinitesimal_tensor_not_engineering_shear', 'stress_unit': 'MPa',
                                'energy_unit': 'MPa = MJ/m^3 per reference volume'})
        p['source_files'] = sources
        policy = {'source_files': sources, 'domain_sha256': sources['plugins/material_point/viscoelastic_reference.py'],
                  'settings_sha256': canonical_hash(settings), 'limits': settings['limits'],
                  'transport_sha256': raw['transport_sha256'], 'compiler_helper_sha256': raw['compiler_helper_sha256']}
        write_json(tmp_path / 'source_inventory.json', sources)
        write_json(tmp_path / 'frozen_execution_policy.json', policy)
        lines = ['# first column: time']
        for col in range(2, 22):
            name = 'strain' if col < 8 else 'stress' if col < 14 else 'BranchStress' if col < 20 else 'stored energy' if col == 20 else 'disspated energy'
            lines.append(f'# {col} column: {name}')
        for row in raw['mtest']['states']:
            values = [row['time_s'], *row['global_u0'][:6], *row['committed_s0_kelvin_mpa'], *row['committed_iv0'],
                      row['stored_energy_mpa'], row['dissipated_energy_mpa']]
            lines.append(' '.join(repr(value) for value in values))
        (tmp_path / 'mtest.res').write_text('\n'.join(lines) + '\n')
        raw['mtest']['native_output_table'] = worker.parse_mtest_table(tmp_path / 'mtest.res', raw['mtest']['states'])
    assessment = domain.assess(settings, raw)
    outcome = {'status': 'COMPLETED' if all(row['status'] != 'FAIL' for row in assessment['checks']) else 'REJECTED',
               'solver_status': 'COMPLETED', 'converged': True, 'metrics': assessment['metrics'],
               'checks': assessment['checks'], 'assessment': assessment, 'provenance': p}
    write_json(tmp_path / 'native_raw.json', raw)
    write_json(tmp_path / 'analysis_raw.json', outcome)
    return outcome, raw


@pytest.mark.parametrize('backend', [retained.ELASTIC, retained.SVK, retained.MAXWELL])
def test_retained_material_stress_energy_and_original_capture_read_without_runtime(tmp_path, backend, monkeypatch):
    outcome, raw = saved_material(tmp_path, backend)
    # The captured original source intentionally differs from current adapter
    # bytes. Reading requires neither the old SIF nor a matching running adapter.
    for key in ('CAELAB_MFRONT_IMAGE', 'CAELAB_CODEASTER_IMAGE', 'CAELAB_MFRONT_IMAGE_SHA256'):
        monkeypatch.delenv(key, raising=False)
    catalog = catalog_native_responses(backend, outcome, tmp_path)
    if backend == retained.SVK:
        assert catalog['mgis-cauchy-xy']['source']['value_origin'] == 'DERIVED'
        assert catalog['mgis-pk1-xy']['source']['value_origin'] == 'NATIVE'
        assert catalog['mgis-pk1-xy']['initial_state']['kind'] == 'UNPREPARED_INITIAL_CONDITION_EXCLUDED'
        selector = 'mgis-stored'
        expected = [row['stored_energy_density_mpa'] for row in raw['steps']]
        assert read_native_response(backend, outcome, tmp_path, selector)['axes'][0]['values'][0] > 0
        assert 'mtest-stored' not in catalog
    elif backend == retained.ELASTIC:
        assert catalog['derived-elastic-energy']['source']['value_origin'] == 'DERIVED'
        assert catalog['mgis-stress-xy']['source']['value_origin'] == 'NATIVE'
        assert 'mgis-stored' not in catalog
        selector = 'mgis-stress-xy'
        expected = [row['stress_physical_mpa'][3] for row in [raw['mgis']['initial'], *raw['mgis']['steps']]]
    else:
        assert len(catalog) == 16
        assert catalog['mgis-branch-xy']['source']['value_origin'] == 'NATIVE'
        selector = 'mtest-dissipated'
        expected = [row['dissipated_energy_mpa'] for row in raw['mtest']['states']]
        assert 'reference-work' not in catalog
    response = read_native_response(backend, outcome, tmp_path, selector, start=1, stop=3)
    assert response['value'] == expected[1:3]
    assert response['unit'] == 'MPa'
    assert response['source']['sha256'] == catalog[selector]['source']['sha256']
    assert response['source']['selector'] == selector
    (tmp_path / 'build/src/libBehaviour.so').write_bytes(b'CHANGED_TEST_ONLY_NOT_A_LIBRARY')
    with pytest.raises(ValueError, match='differs'):
        catalog_native_responses(backend, outcome, tmp_path)


def test_saved_material_original_thresholds_or_recorded_metrics_cannot_be_changed(tmp_path):
    outcome, raw = saved_material(tmp_path, retained.MAXWELL)
    foreign = deepcopy(outcome)
    foreign['metrics']['stress_history']['value'][1][0] += 1.
    write_json(tmp_path / 'analysis_raw.json', foreign)
    with pytest.raises(ValueError, match='verdict differs'):
        catalog_native_responses(retained.MAXWELL, foreign, tmp_path)


def test_saved_catalog_hash_is_enforced_by_existing_evaluation_selection(tmp_path):
    from caelab.evaluation import _select_native
    output = tmp_path / 'native'
    output.mkdir()
    outcome, fixture = saved_j2(output)
    catalog = catalog_native_responses(retained.J2, outcome, output)
    result = {'native_result': {'directory': 'native', 'backend': retained.J2}, 'native_channels': catalog,
              'responses': {}}
    _select_native(result, tmp_path, ['j2.mesh0.DEPL.DX@1'], outcome)
    assert result['responses']['j2.mesh0.DEPL.DX@1']['source']['sha256'] == catalog['j2.mesh0.DEPL.DX']['source']['sha256']
    (output / 'level_0/results.med').write_bytes(b'CHANGED_TEST_ONLY_UNSOLVED_MED')
    with pytest.raises(ValueError, match='source hash differs from the saved result'):
        _select_native(result, tmp_path, ['j2.mesh0.DEPL.DX@1'], outcome)


@pytest.mark.parametrize('backend', [retained.ELASTIC, retained.SVK, retained.MAXWELL])
def test_unreliable_native_increment_preserves_failed_outcome_without_invented_curves(tmp_path, backend):
    outcome = {'status': 'REJECTED', 'solver_status': 'COMPLETED', 'converged': False,
               'provenance': {'adapter': backend, 'adapter_version': '1'},
               'checks': [{'code': 'reliable_integrations', 'status': 'FAIL'}],
               'metrics': {'native_integration_return': {'value': 0, 'unit': '1', 'valid': False}}}
    raw = {'native_rejection': {'integration_return': 0, 'time_s': .1}, 'TEST_ONLY': True}
    write_json(tmp_path / 'analysis_raw.json', outcome)
    write_json(tmp_path / 'native_raw.json', raw)
    assert catalog_native_responses(backend, outcome, tmp_path) == {}
    assert (tmp_path / 'native_raw.json').exists()
