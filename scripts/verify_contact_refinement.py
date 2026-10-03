"""One fresh uniform2 contact run; reuse the SHA-qualified original baseline.

No original solve is repeated. Pair differences are sensitivity diagnostics,
not an asymptotic convergence, cross-solver, fixture or engineering verdict.
"""
import argparse
from copy import deepcopy
import hashlib
import math
from pathlib import Path

from caelab import Lab
from caelab.storage import canonical_hash, load_json, save_json

BACKEND = 'structural.code_aster.contact_patch'
VARIANT = 'uniform_quad4_2x'
BASELINE_RECORD = 'benchmarks/records/20261004-contact-native-r01-qualified.json'
BASELINE_SHA256 = '974a1fe42338fb31367f75fcf2858b04ffe1152d08379a7dbdf556163b336fff'
BASELINE_PRODUCER = '9d0d613bd8d6ec5a1d5c1a59805c002c84e71c92'
FIELDS = {f'{point}_{field}': (unit, reference)
          for point in ('A', 'B', 'N14')
          for field, unit, reference in (('normal_traction', 'Pa', -1e5),
                                         ('vertical_displacement', 'm', -.05))}
PENDING = {'model_qualification', 'material_qualification', 'physical_validation',
           'static_strength', 'fatigue_durability', 'pointwise_contact_gap',
           'cross_solver_contact', 'fixture_joint_contact',
           'corporate_license_approval', 'corporate_security_approval'}


def specification():
    return {'case': 'ssnp121a_frictionless_patch',
            'material': {'youngs_modulus_pa': 2e6, 'poisson_ratio': 0.0},
            'top_displacement_m': -0.1,
            'limits': {'reference_relative': 0.01, 'force_balance_relative': 1e-6},
            'mesh_variant': VARIANT}


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def qualified_baseline(root):
    """Missing historical evidence blocks a new solve, without guessing a run."""
    root = Path(root).resolve()
    record_file = root / BASELINE_RECORD
    if _sha(record_file) != BASELINE_SHA256:
        raise ValueError('Original qualified contact record drifted')
    record = load_json(record_file)
    if record['producer_commit'] != BASELINE_PRODUCER:
        raise ValueError('Original contact producer identity differs')
    case = record['cases']['E-ssnp121a-canonical']
    relative = Path(case['result']['path'])
    result_file = (root / relative).resolve()
    if relative.is_absolute() or not result_file.is_relative_to(root):
        raise ValueError('Original contact result path escaped the evidence root')
    if result_file.stat().st_size != case['result']['bytes'] or _sha(result_file) != case['result']['sha256']:
        raise ValueError('Original qualified contact result drifted')
    original = load_json(result_file)
    if original['model_revision'] != case['model_revision']:
        raise ValueError('Original contact revision differs')
    for key, (unit, _) in FIELDS.items():
        metric = original['metrics'][key]
        if metric['unit'] != unit or metric['valid'] is not True or metric['value'] != case['metrics'][key]:
            raise ValueError('Original signed response no longer matches qualified evidence')
    return original, {'producer_commit': BASELINE_PRODUCER,
        'record': {'path': BASELINE_RECORD, 'sha256': BASELINE_SHA256},
        'result': deepcopy(case['result']), 'model_revision': original['model_revision']}


def comparison(original, refined):
    """Preserve failed/missing measured responses; no pair PASS threshold."""
    rows = []
    for key, (unit, reference) in FIELDS.items():
        prior = original['metrics'][key]
        current = refined.get('metrics', {}).get(key)
        available = (isinstance(current, dict) and current.get('unit') == unit and
                     type(current.get('value')) in (int, float))
        if available:
            try:
                available = math.isfinite(current['value'])
            except (OverflowError, ValueError):
                available = False
        value = current['value'] if available else None
        delta, relative, arithmetic_available = None, None, False
        if available:
            try:
                difference = value - prior['value']
                if math.isfinite(difference):
                    delta = difference
                    ratio = abs(difference) / abs(reference)
                    if math.isfinite(ratio):
                        relative, arithmetic_available = ratio, True
            except (OverflowError, ValueError):
                pass
        rows.append({'metric': key, 'unit': unit, 'analytical_reference': reference,
            'original': prior['value'], 'refined': value,
            'refined_metric_valid': available and current.get('valid') is True,
            'refined_metric_reason': (current.get('reason') if available else
                                      'Required finite measured response or unit unavailable'),
            'signed_difference': delta,
            'absolute_difference': abs(delta) if delta is not None else None,
            'difference_relative_to_fixed_analytical_reference': relative,
            'comparison_arithmetic_available': arithmetic_available,
            'comparison_reason': (None if arithmetic_available else
                'Required measured response or derived difference/ratio is not finitely representable'),
            'verdict': 'DIAGNOSTIC_NO_PAIR_THRESHOLD' if arithmetic_available else 'UNKNOWN'})
    return rows


def unknown_validation_types(result):
    """Read the common Core validation shape, separate from Domain check codes."""
    return {v['type'] for v in result['validations'] if v['status'] == 'UNKNOWN'}


def run(store, *, baseline_root=None):
    store = Path(store)
    if store.exists():
        raise FileExistsError('Refinement acceptance requires a new store')
    root = Path(baseline_root) if baseline_root is not None else Path(__file__).resolve().parents[1]
    original, baseline = qualified_baseline(root)
    lab = Lab(store)
    lab.create_study('S-contact-refinement', 'SSNP121A uniform2 mesh sensitivity',
        'How do the signed A/B/N14 responses change under one uniform subdivision?',
        'The same analytical solution applies; one subdivision is not asymptotic convergence proof.',
        'Reuse the qualified original result and perform one new native mesh run through common records.')
    settings = specification()
    result = lab.run_model_analysis(study_id='S-contact-refinement',
        experiment_id='E-ssnp121a-uniform2', backend=BACKEND, settings=settings)
    rows = comparison(original, result)
    proposal_file = store / 'experiments/E-ssnp121a-uniform2/proposal.json'
    proposal = load_json(proposal_file)
    mesh = proposal['model']['mesh']
    expected_revision = canonical_hash({'settings': settings,
        'declaration': proposal['extensions']['model_analysis']['declaration']})
    unknown = unknown_validation_types(result)
    controls = {
        'original_baseline_unchanged': _sha(root / baseline['result']['path']) == baseline['result']['sha256'],
        'same_common_record': lab.inspect_experiment('E-ssnp121a-uniform2') == result,
        'new_declared_revision': result['model_revision'] == expected_revision != original['model_revision'],
        'selected_declared_mesh': (mesh['node_count'], mesh['solid_cell_count'], mesh['boundary_segment_count'],
            mesh['slave_contact_segment_count'], mesh['master_contact_segment_count']) == (1154, 1060, 184, 24, 22),
        'original_coordinates_preserved': mesh.get('original_coordinates_preserved') is True,
        'existing_reference_native_gates_pass': result['status'] == 'COMPLETED_REVIEW_REQUIRED' and
            result['solver_status'] == 'COMPLETED' and result['converged'] is True and
            not any(v['status'] == 'FAIL' for v in result['validations']),
        'all_six_measured_samples_valid': all(row['refined_metric_valid'] for row in rows),
        'all_six_signed_comparisons_representable': all(row['comparison_arithmetic_available'] for row in rows),
        'all_qualifications_remain_unknown': PENDING <= unknown,
        'not_released': result['decision'] == 'NOT_RELEASED' and result['cad_revision'] is None,
    }
    native_file = store / 'experiments/E-ssnp121a-uniform2/simulation/level_0/worker_result.json'
    counts = None
    if native_file.is_file():
        native = load_json(native_file)
        fields = native['observation']['fields']
        counts = {'nodes': len(fields['node_ids']), 'displacements': len(fields['displacements_m']),
            'reactions': len(fields['nodal_reactions_n_per_m']), 'stress_locations': len(fields['stresses_pa']),
            'slave_pressure_samples': len(native['observation']['slave_contact']['node_ids'])}
    controls['actual_complete_native_fields'] = counts == {'nodes': 1154, 'displacements': 1154,
        'reactions': 1154, 'stress_locations': 4240, 'slave_pressure_samples': 25}
    report = {'status': 'PASS' if all(controls.values()) else 'FAIL', 'decision': 'NOT_RELEASED',
        'settings': settings, 'baseline': baseline, 'new_model_analysis_calls': 1,
        'original_model_analysis_calls_repeated': 0, 'expected_new_native_processes': 1,
        'actual_native_process_count_scope': 'Separate retained owned-process receipts, not this control count',
        'controls': controls,
        'native_field_counts': counts, 'refined': lab.research_summary('E-ssnp121a-uniform2'),
        'signed_sample_comparison': rows,
        'mesh_convergence_qualification': 'UNKNOWN; two mesh levels establish sensitivity only',
        'cross_solver_contact': 'UNKNOWN; the separate CalculiX original pilot remains failed',
        'limitations': ['Original six1% and reaction1%/balance1e-6/native2e-8 gates are unchanged',
            'No new pair threshold, extrapolated replacement or passing-sample selection',
            'Native gap, material/physical/strength/durability, fixture joint and release remain UNKNOWN']}
    save_json(store / 'acceptance.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--store', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.store)
    print(f"SSNP121A uniform2 sensitivity: {report['status']} / {report['decision']}")
    raise SystemExit(0 if report['status'] == 'PASS' else 1)
