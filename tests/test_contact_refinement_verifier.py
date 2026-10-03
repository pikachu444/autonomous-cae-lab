"""Pure acceptance consumer refusals; no native or Core execution."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import json

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'scripts/verify_contact_refinement.py'
spec = importlib.util.spec_from_file_location('root_contact_refinement_verifier', SOURCE)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


@pytest.fixture
def original(tmp_path):
    # Exact captured historical result; neither a new native run nor fake fields.
    published = ROOT / verifier.BASELINE_RECORD
    record = json.loads(published.read_text(encoding='utf-8'))
    target = tmp_path / verifier.BASELINE_RECORD
    target.parent.mkdir(parents=True)
    target.write_bytes(published.read_bytes())
    result_path = tmp_path / record['cases']['E-ssnp121a-canonical']['result']['path']
    result_path.parent.mkdir(parents=True)
    result_path.write_bytes((ROOT / 'tests/fixtures/codeaster_174_contact/canonical-result.json').read_bytes())
    result, evidence = verifier.qualified_baseline(tmp_path)
    assert evidence['producer_commit'] == verifier.BASELINE_PRODUCER
    return result


def test_signed_pair_differences_have_no_passing_threshold(original):
    refined = deepcopy(original)
    refined['metrics']['A_normal_traction']['value'] = -95000.0
    refined['metrics']['B_vertical_displacement']['value'] = -0.051
    rows = {row['metric']: row for row in verifier.comparison(original, refined)}
    assert rows['A_normal_traction']['signed_difference'] > 0
    assert rows['B_vertical_displacement']['signed_difference'] < 0
    assert {row['verdict'] for row in rows.values()} == {'DIAGNOSTIC_NO_PAIR_THRESHOLD'}
    assert all('limit' not in row for row in rows.values())


def test_failed_finite_measurements_are_retained(original):
    refined = deepcopy(original)
    refined['metrics']['A_normal_traction'].update(value=-95000.0, valid=False, reason='Original1% failed')
    row = verifier.comparison(original, refined)[0]
    assert row['refined'] == -95000.0 and row['refined_metric_valid'] is False
    assert row['refined_metric_reason'] == 'Original1% failed'
    assert row['verdict'] == 'DIAGNOSTIC_NO_PAIR_THRESHOLD'


@pytest.mark.parametrize('bad', [True, float('nan'), float('inf'), '100000', None])
def test_non_measured_or_nonfinite_value_cannot_become_comparison(original, bad):
    refined = deepcopy(original)
    refined['metrics']['A_normal_traction']['value'] = bad
    row = verifier.comparison(original, refined)[0]
    assert row['refined'] is None and row['signed_difference'] is None
    assert row['verdict'] == 'UNKNOWN' and not row['refined_metric_valid']


def test_missing_response_or_wrong_unit_stays_unknown(original):
    refined = deepcopy(original)
    del refined['metrics']['A_normal_traction']
    refined['metrics']['B_vertical_displacement']['unit'] = 'mm'
    rows = {row['metric']: row for row in verifier.comparison(original, refined)}
    assert rows['A_normal_traction']['verdict'] == rows['B_vertical_displacement']['verdict'] == 'UNKNOWN'


def test_baseline_drift_blocks_before_new_study_or_solve(tmp_path):
    record = tmp_path / verifier.BASELINE_RECORD
    record.parent.mkdir(parents=True)
    record.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='record drifted'):
        verifier.run(tmp_path / 'never-created', baseline_root=tmp_path)
    assert not (tmp_path / 'never-created').exists()


def test_existing_store_refused_before_baseline_or_execution(tmp_path):
    with pytest.raises(FileExistsError):
        verifier.run(tmp_path, baseline_root=tmp_path / 'missing')


def test_real_common_validation_rows_use_type_and_retain_ten_unknowns(original):
    assert all('type' in row and 'code' not in row for row in original['validations'])
    assert verifier.unknown_validation_types(original) == verifier.PENDING


def test_finite_failed_measurement_survives_unrepresentable_relative_difference(original):
    refined = deepcopy(original)
    refined['metrics']['A_vertical_displacement'].update(value=1e308, valid=False, reason='Original numerical gate failed')
    row = next(row for row in verifier.comparison(original, refined) if row['metric'] == 'A_vertical_displacement')
    assert row['refined'] == 1e308 and not row['refined_metric_valid']
    assert row['signed_difference'] == 1e308
    assert row['difference_relative_to_fixed_analytical_reference'] is None
    assert row['comparison_arithmetic_available'] is False and row['verdict'] == 'UNKNOWN'
    assert row['refined_metric_reason'] == 'Original numerical gate failed'
    assert json.loads(json.dumps(row, allow_nan=False)) == row
