"""Retained read consistency, using controlled captures; no native execution."""
from copy import deepcopy
import math
import subprocess

import pytest

from caelab.adapters import native_responses as reader, retained_law_responses as law
from caelab.storage import canonical_hash, load_json
from plugins.material_point import viscoelastic_reference as domain
from test_retained_law_responses import pin, saved_material, write_json


@pytest.fixture(autouse=True)
def forbid_native(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Retained compatibility checks must not execute native processes')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)


def shifted(value, count):
    for _ in range(count):
        value = math.nextafter(value, math.inf)
    return value


def compatible_capture(path, monkeypatch):
    """Produce a coherent TEST_ONLY other-platform analytical representation.

    Native tensors are unchanged. Independent reassessment on this host has
    nonzero, cancellation-sensitive tangent residuals while this capture's
    tangent residual is exactly zero. The original reference/check/metric
    duplicates and derived limits are produced by the unchanged Domain assess.
    """
    assess, reference = domain.assess, domain.analytical_reference

    def other_platform(settings, raw):
        retained = reference(settings)
        for index, row in enumerate(retained['states'][1:], 1):
            # Some reference components differ by ten ULP, not a global
            # engineering tolerance; exact time/strain/zero entries stay exact.
            for key in ('stress_physical_mpa', 'stress_kelvin_mpa',
                        'branch_stress_physical_mpa', 'branch_stress_kelvin_mpa'):
                row[key] = [shifted(x, 10 if i == 4 else 1) if x else x for i, x in enumerate(row[key])]
            for key in ('stored_energy_mpa', 'dissipated_energy_mpa', 'work_mpa'):
                row[key] = shifted(row[key], 2) if row[key] else row[key]
            # These are the same binary64-scale alternatives from the tensor
            # expression. This changes analytical representation, never raw.
            row['tangent_kelvin_mpa'] = deepcopy(raw['mgis']['steps'][index - 1]['tangent_kelvin_mpa'])
        with monkeypatch.context() as local:
            local.setattr(domain, 'analytical_reference', lambda _: deepcopy(retained))
            return assess(settings, raw)

    with monkeypatch.context() as local:
        local.setattr(domain, 'assess', other_platform)
        outcome, raw = saved_material(path, law.MAXWELL)
    return outcome, raw


def read_positive(path, outcome):
    catalog = reader.catalog_native_responses(law.MAXWELL, outcome, path)
    response = reader.read_native_response(law.MAXWELL, outcome, path, 'mgis-stored')
    assert response['source']['sha256'] == pin(path / 'native_raw.json')
    assert catalog['mgis-stored']['source']['manifest_sha256'] == response['source']['manifest_sha256']
    return response


def test_compatible_representations_pass_before_any_corruption_and_preserve_original(tmp_path, monkeypatch):
    outcome, raw = compatible_capture(tmp_path, monkeypatch)
    settings = load_json(tmp_path / 'input.json')
    fixed = deepcopy(domain.FIXED_LIMITS)
    saved = deepcopy(outcome)
    files = {p.relative_to(tmp_path): pin(p) for p in tmp_path.rglob('*') if p.is_file()}
    current = domain.assess(settings, raw)
    check = 'analytical_tangent_relative_error'
    assert outcome['metrics'][check]['value'] == 0.
    assert 0 < current['metrics'][check]['value'] < 2e-16
    assert outcome['assessment']['stress_limit_mpa'] != current['stress_limit_mpa']
    assert outcome['assessment']['energy_limit_mpa'] != current['energy_limit_mpa']
    value = read_positive(tmp_path, outcome)
    assert value['value'] == [row['stored_energy_mpa'] for row in [raw['mgis']['initial'], *raw['mgis']['steps']]]
    assert outcome == saved and domain.FIXED_LIMITS == fixed
    assert {p.relative_to(tmp_path): pin(p) for p in tmp_path.rglob('*') if p.is_file()} == files


def test_reported_literal_rounding_and_near_zero_are_not_residual_ulp_tests(tmp_path):
    outcome, raw = saved_material(tmp_path, law.MAXWELL)
    settings = load_json(tmp_path / 'input.json')
    current = deepcopy(outcome['assessment'])
    # Root's literal stress/reference/derived limit pair, with each reference
    # owning its own unchanged fixed-coefficient limit expression.
    for key in ('stress_physical_mpa', 'stress_kelvin_mpa'):
        current['reference']['states'][1][key][0] = 4.8753336133149805
    current['stress_scale_mpa'] = 4.8753336133149805
    current['stress_limit_mpa'] = 4.885333613314981e-08
    for check in current['checks']:
        if check.get('limit') == outcome['assessment']['stress_limit_mpa']:
            check['limit'] = current['stress_limit_mpa']
    # The ordinary native/reference differences remain within the actual
    # tangent operand roundoff scale even when ULP(near-zero) is meaningless.
    for assessment, residual in ((current, 9.700612972008478e-17), (outcome['assessment'], 0.)):
        item = next(c for c in assessment['checks'] if c['code'] == 'analytical_tangent_relative_error')
        item['every_step_relative_error'] = [residual] * len(item['every_step_relative_error'])
        item['observed'] = assessment['metrics'][item['code']]['value'] = residual
    assert law.verify_maxwell_assessment(settings, current, outcome)
    assert domain.FIXED_LIMITS['tangent_relative'] == 1e-8


@pytest.mark.parametrize('change', ['native_one_ulp', 'native_energy_one_ulp', 'material_one_ulp',
    'fixed_threshold', 'derived_limit', 'verdict', 'envelope_verdict', 'duplicate', 'analytical_change', 'source'])
def test_positive_then_strict_original_or_meaning_change_is_refused(tmp_path, monkeypatch, change):
    outcome, raw = compatible_capture(tmp_path, monkeypatch)
    # Every negative first admits the compatible original through the real
    # catalog path. Exact native response values were checked in the positive.
    assert 'mgis-stored' in reader.catalog_native_responses(law.MAXWELL, outcome, tmp_path)
    original_native = pin(tmp_path / 'native_raw.json')
    if change == 'native_one_ulp':
        values = raw['mgis']['steps'][0]['stress_physical_mpa']
        values[0] = shifted(values[0], 1)
        write_json(tmp_path / 'native_raw.json', raw)
    elif change == 'native_energy_one_ulp':
        raw['mgis']['steps'][0]['stored_energy_mpa'] = shifted(raw['mgis']['steps'][0]['stored_energy_mpa'], 1)
        write_json(tmp_path / 'native_raw.json', raw)
    elif change in ('material_one_ulp', 'fixed_threshold'):
        settings = load_json(tmp_path / 'input.json')
        group, name = ('material', 'branch_shear_modulus_mpa') if change == 'material_one_ulp' else ('limits', 'stress_relative')
        settings[group][name] = shifted(settings[group][name], 1)
        write_json(tmp_path / 'input.json', settings)
        # Also update transport hashes: refusal must still enforce the native
        # material/frozen threshold contract, not just an out-of-date JSON pin.
        raw['input_sha256'] = pin(tmp_path / 'input.json')
        write_json(tmp_path / 'native_raw.json', raw)
        policy = load_json(tmp_path / 'frozen_execution_policy.json')
        policy['settings_sha256'] = canonical_hash(settings)
        policy['limits'] = deepcopy(settings['limits'])
        write_json(tmp_path / 'frozen_execution_policy.json', policy)
    elif change == 'source':
        source = tmp_path / 'viscoelastic_reference.py'
        source.write_bytes(source.read_bytes() + b'\nchanged')
    else:
        if change == 'derived_limit':
            check = next(c for c in outcome['assessment']['checks'] if c['code'] == 'max_stress_physical_error')
            check['limit'] = shifted(check['limit'], 1)
        elif change == 'verdict':
            outcome['assessment']['checks'][0]['status'] = 'FAIL'
        elif change == 'envelope_verdict':
            outcome['status'] = 'REJECTED'
        elif change == 'duplicate':
            outcome['metrics'] = deepcopy(outcome['metrics'])
            outcome['metrics']['reference_work_history']['value'][-1] = shifted(
                outcome['metrics']['reference_work_history']['value'][-1], 1)
        else:
            # Well below the engineering stress tolerance, but far beyond a
            # representation difference: do not use the acceptance tolerance.
            outcome['assessment']['reference']['states'][1]['branch_stress_physical_mpa'][0] += 1e-9
        write_json(tmp_path / 'analysis_raw.json', outcome)
    with pytest.raises(ValueError):
        reader.catalog_native_responses(law.MAXWELL, outcome, tmp_path)
    if change in ('derived_limit', 'verdict', 'duplicate', 'analytical_change', 'source'):
        assert pin(tmp_path / 'native_raw.json') == original_native


def test_fixed_input_coefficients_expected_flags_and_initial_zero_have_no_allowance(tmp_path):
    outcome, _ = saved_material(tmp_path, law.MAXWELL)
    settings = load_json(tmp_path / 'input.json')
    assert law.verify_maxwell_assessment(settings, outcome['assessment'], outcome)
    for key in domain.FIXED_LIMITS:
        changed = deepcopy(settings)
        if isinstance(changed['limits'][key], list):
            changed['limits'][key][0] = shifted(changed['limits'][key][0], 1)
        else:
            changed['limits'][key] = shifted(changed['limits'][key], 1)
        assert not law.verify_maxwell_assessment(changed, outcome['assessment'], outcome)
    for change in ('expected', 'initial', 'native'):
        computed = deepcopy(outcome['assessment'])
        if change == 'expected':
            computed['checks'][0]['expected'] = False
        elif change == 'initial':
            computed['reference']['states'][0]['stress_physical_mpa'][0] = math.ulp(0.)
        else:
            v = computed['metrics']['stress_history']['value'][1]
            v[0] = shifted(v[0], 1)
        assert not law.verify_maxwell_assessment(settings, computed, outcome)


def test_zero_nominal_history_still_has_nonzero_fd_probe_operands(tmp_path, monkeypatch):
    settings = domain.canonical_settings()
    settings['history'] = [{'time_s': 0., 'strain': [0.] * 6}, {'time_s': 1., 'strain': [0.] * 6}]
    monkeypatch.setattr(domain, 'canonical_settings', lambda: deepcopy(settings))
    outcome, _ = saved_material(tmp_path, law.MAXWELL)
    assert law.verify_maxwell_assessment(settings, outcome['assessment'], outcome)
    current = deepcopy(outcome['assessment'])
    for code in ('max_probe_stress_error', 'max_probe_stored_energy_error'):
        check = next(c for c in current['checks'] if c['code'] == code)
        # The actual h perturbs an otherwise zero tensor. Its subtraction
        # residual can move at that operand's scale while nominal fields cannot.
        scale = 1e-4 if code == 'max_probe_stress_error' else 1e-11
        check['observed'] += math.ulp(scale)
        current['metrics'][code]['value'] = check['observed']
    assert law.verify_maxwell_assessment(settings, current, outcome)
    current['reference']['states'][1]['stress_physical_mpa'][0] = math.ulp(0.)
    assert not law.verify_maxwell_assessment(settings, current, outcome)
