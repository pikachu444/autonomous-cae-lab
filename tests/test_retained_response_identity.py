"""Immutable saved-protocol reads and platform rounding; no native execution."""
from copy import deepcopy
import math
import subprocess

import pytest

from caelab.adapters import native_responses as reader
from caelab.adapters import retained_law_responses as law
from test_retained_law_responses import saved_material, saved_j2, pin, write_json


@pytest.fixture(autouse=True)
def no_native(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Retained response tests must not execute a native process')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)


def test_maxwell_platform_rounding_reads_identical_original_values_and_files(tmp_path, monkeypatch):
    from plugins.material_point import viscoelastic_reference as domain
    outcome, raw = saved_material(tmp_path, law.MAXWELL)
    original = {path.relative_to(tmp_path): pin(path) for path in tmp_path.rglob('*') if path.is_file()}
    reference = domain.analytical_reference

    def other_platform(settings):
        value = deepcopy(reference(settings))
        row = value['states'][-1]
        row['work_mpa'] = math.nextafter(row['work_mpa'], math.inf)
        return value

    # Recompute dependent metrics/limits from that representation. A metric
    # changed without its own reference is an inconsistent duplicate, not a
    # legitimate platform difference.
    monkeypatch.setattr(domain, 'analytical_reference', other_platform)
    catalog = reader.catalog_native_responses(law.MAXWELL, outcome, tmp_path)
    response = reader.read_native_response(law.MAXWELL, outcome, tmp_path, 'mgis-stored')
    assert response['value'] == [row['stored_energy_mpa'] for row in [raw['mgis']['initial'], *raw['mgis']['steps']]]
    source = catalog['mgis-stored']['source']
    assert source['sha256'] == source['native_origin']['sha256'] == pin(tmp_path / 'native_raw.json')
    assert source['sha256'] != source['manifest_sha256']
    assert source['sha256_kind'] == 'ARTIFACT_SHA256'
    assert {path.relative_to(tmp_path): pin(path) for path in tmp_path.rglob('*') if path.is_file()} == original


@pytest.mark.parametrize('change', ['limit', 'status', 'valid', 'large_observation', 'duplicated_metric'])
def test_verdict_meaning_and_saved_duplicates_remain_exact(tmp_path, change):
    outcome, _ = saved_material(tmp_path, law.MAXWELL)
    computed = deepcopy(outcome['assessment'])
    if change == 'limit':
        check = next(item for item in computed['checks'] if type(item.get('limit')) is float)
        check['limit'] = math.nextafter(check['limit'], math.inf)
    elif change == 'status':
        computed['checks'][0]['status'] = 'FAIL' if computed['checks'][0]['status'] == 'PASS' else 'PASS'
    elif change == 'valid':
        computed['metrics']['stress_history']['valid'] = not computed['metrics']['stress_history']['valid']
    elif change == 'large_observation':
        computed['metrics']['reference_work_history']['value'][-1] += 1.e-3
    else:
        outcome = deepcopy(outcome)
        outcome['metrics'] = deepcopy(outcome['metrics'])
        outcome['metrics']['reference_work_history']['value'][-1] = math.nextafter(
            outcome['metrics']['reference_work_history']['value'][-1], math.inf)
    assert not law.verify_saved_assessment(computed, outcome)


def test_elastic_derived_energy_returns_exact_saved_value_not_recalculation(tmp_path):
    outcome, _ = saved_material(tmp_path, law.ELASTIC)
    assessment = outcome['assessment']
    history = assessment['metrics']['energy_density_history']['value']
    history[-1] = math.nextafter(history[-1], math.inf)
    write_json(tmp_path / 'analysis_raw.json', outcome)
    response = reader.read_native_response(law.ELASTIC, outcome, tmp_path, 'derived-elastic-energy')
    assert response['value'] == history
    assert response['source']['value_origin'] == 'DERIVED'


def test_binary64_rounding_bound_is_eight_steps_not_an_engineering_tolerance():
    base = 1.0
    saved = {'checks': [{'code': 'controlled', 'status': 'PASS', 'observed': base, 'limit': 2.}],
             'metrics': {'controlled': {'value': base, 'valid': True, 'unit': '1'}}}
    outcome = {'assessment': saved, 'metrics': saved['metrics'], 'checks': saved['checks']}
    for steps, accepted in ((8, True), (9, False)):
        computed = deepcopy(saved)
        changed = base
        for _ in range(steps):
            changed = math.nextafter(changed, math.inf)
        computed['checks'][0]['observed'] = computed['metrics']['controlled']['value'] = changed
        assert law.verify_saved_assessment(computed, outcome) is accepted
    computed = deepcopy(saved)
    computed['checks'][0]['limit'] = math.nextafter(2., math.inf)
    assert not law.verify_saved_assessment(computed, outcome)
    saved['checks'][0]['limit'] = base
    computed = deepcopy(saved)
    computed['checks'][0]['observed'] = math.nextafter(base, math.inf)
    assert not law.verify_saved_assessment(computed, outcome)


@pytest.mark.parametrize('backend', [law.MAXWELL, law.J2])
def test_r5_aggregate_source_pin_is_explicitly_admitted_and_changed_dependencies_rejected(tmp_path, backend):
    outcome = saved_material(tmp_path, backend)[0] if backend == law.MAXWELL else saved_j2(tmp_path)[0]
    catalog = reader.catalog_native_responses(backend, outcome, tmp_path)
    key = 'mgis-stored' if backend == law.MAXWELL else 'j2.mesh0.DEPL.DX'
    current = catalog[key]['source']
    legacy = deepcopy(current)
    legacy['sha256'] = legacy.pop('manifest_sha256')
    legacy.pop('sha256_kind')
    assert reader.verify_retained_response_source(legacy, current)
    assert reader.verify_retained_response_source(current, current)
    changed = {**current, 'manifest_sha256': '0' * 64}
    assert not reader.verify_retained_response_source(legacy, changed)
    assert not reader.verify_retained_response_source(current, changed)
    wrong_artifact = {**current, 'artifact': 'different.json'}
    assert not reader.verify_retained_response_source(legacy, wrong_artifact)
    origin_changed = deepcopy(current)
    origin_changed['native_origin']['sha256'] = '0' * 64
    assert not reader.verify_retained_response_source(legacy, origin_changed)
    if backend == law.J2:
        assert current['sha256'] == pin(tmp_path / current['artifact'].removeprefix('simulation/'))
        assert current['native_origin']['sha256'] == pin(tmp_path / 'level_0/results.med')


def saved_explicit(tmp_path, case):
    from test_openradioss import native_fixture, small_settings, small_compliant_settings
    from caelab.adapters.openradioss_worker import parse_history
    from plugins.explicit_dynamics import reference as domain
    settings = small_compliant_settings() if case == 'compliant' else small_settings(wall=case == 'wall')
    settings = domain.validate_settings(settings)
    identity = {'archive_sha256': '598ed7b2905a7bacc8d1781470c250ac79d7558c39ba962768edf3644644fe33',
                'release_source_commit': 'a62b27e6baa555d222a580d6218867d0be4d70b5'}
    native_fixture(tmp_path, settings)
    raw = parse_history(tmp_path, settings, identity)
    assessment = domain.assess(settings, raw['rows'])
    outcome = {'status': 'COMPLETED' if all(row['status'] == 'PASS' for row in assessment['checks']) else 'REJECTED',
               'solver_status': 'COMPLETED', 'converged': True, 'provenance': identity,
               'raw_result': 'simulation/analysis_raw.json', 'assessment': assessment,
               'metrics': assessment['metrics'], 'checks': assessment['checks']}
    write_json(tmp_path / 'input.json', settings)
    write_json(tmp_path / 'parsed_history.json', raw)
    write_json(tmp_path / 'analysis_raw.json', outcome)
    return outcome, raw


@pytest.mark.parametrize('case', ['flight', 'wall', 'compliant'])
def test_radioss_typed_original_measures_clocks_and_native_derived_origins(tmp_path, case):
    outcome, raw = saved_explicit(tmp_path, case)
    catalog = reader.catalog_native_responses('explicit.openradioss', outcome, tmp_path)
    native = catalog['radioss-center-vz']
    assert native['source']['value_origin'] == 'NATIVE'
    assert native['axes'][0]['semantics'] == 'NATIVE_HALF_STEP_VELOCITY_TIME'
    assert native['source']['sha256'] == pin(tmp_path / 'parsed_history.json')
    assert native['source']['native_origin']['sha256'] == pin(tmp_path / 'dropT01')
    legacy = {key: value for key, value in native['source'].items()
              if key not in {'manifest_sha256', 'sha256_kind', 'value_origin', 'native_origin'}}
    assert reader.verify_retained_response_source(legacy, native['source'])
    selected = reader.read_native_response('explicit.openradioss', outcome, tmp_path, 'radioss-center-vz')
    assert selected['value'] == [row['velocity_m_s'] for row in raw['rows']]
    assert selected['axes'][0]['values'] == [row['velocity_time_s'] for row in raw['rows']]
    assert selected['qualification'] == {'physical': 'UNKNOWN', 'decision': 'NOT_RELEASED'}
    if case == 'compliant':
        work = reader.read_native_response('explicit.openradioss', outcome, tmp_path, 'radioss-spring-work')
        force = reader.read_native_response('explicit.openradioss', outcome, tmp_path, 'radioss-ground-fz')
        assert work['source']['value_origin'] == 'NATIVE' and 'signed' in work['measure']
        assert work['value'] == [row['spring_internal_energy_j'] for row in raw['rows']]
        assert force['source']['value_origin'] == 'DERIVED'
        assert force['value'] == [row['ground_force_n'] for row in raw['rows']]
        assert 'radioss-wall-fnz' not in catalog
    elif case == 'wall':
        impulse = reader.read_native_response('explicit.openradioss', outcome, tmp_path, 'radioss-wall-fnz')
        assert impulse['unit'] == 'N s' and 'not force' in impulse['measure']
        assert impulse['source']['value_origin'] == 'DERIVED'
        assert impulse['value'] == [row['ground_impulse_n_s'] for row in raw['rows']]
    old_source = selected['source']
    # Alter only native text formatting: values are unchanged, dependency bytes
    # still must change the new catalog fingerprint (no values recomputed here).
    with (tmp_path / 'drop_0001.out').open('a', encoding='ascii') as stream:
        stream.write('\n')
    new = reader.catalog_native_responses('explicit.openradioss', outcome, tmp_path)['radioss-center-vz']['source']
    assert old_source['sha256'] == new['sha256']
    assert not reader.verify_retained_response_source(old_source, new)
