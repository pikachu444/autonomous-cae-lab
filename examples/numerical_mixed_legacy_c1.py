"""C1: public Lab numeric registry/DOE, with the existing real SciPy ODE.

    python examples/numerical_mixed_legacy_c1.py --output <new-directory>

The attached DimensionedODEAdapter is evaluation-only, not a registered Lab
model adapter. This EXAMPLE-ONLY facade supplies Lab metadata and converts the
existing adapter's actual response into the legacy Outcome envelope. It does
not replace a setter, expression parser, solver, sampler, store or registry.
It is explicitly injected into this Lab instance; no backend is registered.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import scipy
from caelab import Lab, dimensioned_models as dm, dimensioned_expression as expression
from caelab import model_parameters as mp
from caelab.adapters import dimensioned_ode
from caelab.optimizers.scipy_de import ScipyDifferentialEvolution
from caelab.optimizers.scipy_lhs import ScipyLatinHypercube
from caelab.storage import canonical_hash, load_json, save_json

STUDY = 'S-legacy-c1'
CAMPAIGN = 'C-legacy-c1'


def model_settings():
    settings = dm.default_settings(dm.ODE)
    settings['states'] = [{'name': 'temperature', 'label': '온도', 'unit': 'K',
        'initial': 300., 'rhs': '-rate*(temperature-ambient)',
        'reference': 'ambient+(initial-ambient)*exp(-rate*t)', 'atol': 1e-9}]
    settings['parameters'] = [{'name': 'rate', 'unit': '1/s', 'value': .1},
        {'name': 'ambient', 'unit': 'K', 'value': 290.},
        {'name': 'initial', 'unit': 'K', 'value': 300.}]
    settings['time'] = {'start': 0., 'end': 2., 'samples': 21, 'unit': 's'}
    settings['solver'] = {'method': 'RK45', 'rtol': 1e-8, 'max_step': .005}
    return dm.validate_settings(dm.ODE, settings)


class ExampleLabODE(dimensioned_ode.DimensionedODEAdapter):
    """Only the Lab envelope is new; all physics and input setters are original."""
    domain = 'pde'
    physics_domain = 'state_ode'
    analysis_type = 'initial_value'
    default_metrics = ['temperature_final']
    input_source_files = [Path(dimensioned_ode.__file__), Path(dm.__file__),
                          Path(expression.__file__), Path(mp.__file__), Path(__file__)]
    if (ROOT / 'caelab/variable_binding.py').is_file():
        input_source_files.append(ROOT / 'caelab/variable_binding.py')

    def __init__(self):
        self.calls = 0

    def input_runtime_identity(self):
        return {'python': sys.version.split()[0], 'numpy': np.__version__,
                'scipy': scipy.__version__, 'facade': 'example-only-lab-envelope-v1'}

    def solve(self, output, settings):
        self.calls += 1
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        result = super().run(deepcopy(settings), output=output)
        response = result['responses']['temperature']
        history = {'time': response['axes'][0]['values'].tolist(),
                   'temperature': response['value'].tolist(),
                   'diagnostics': result['diagnostics'], 'execution_status': result['execution_status']}
        save_json(output / 'history.json', history)
        complete = result['execution_status'] == 'SUCCEEDED'
        checks = [{'code': c['name'], **{k: deepcopy(v) for k, v in c.items() if k != 'name'}}
                  for c in result['checks']]
        metric = {'value': float(response['value'][-1]) if complete else None, 'unit': 'K', 'valid': complete}
        if not complete:
            metric['reason'] = 'Original ODE integration did not complete'
        return {'status': 'COMPLETED' if complete else 'REJECTED',
                'solver_status': 'COMPLETED' if complete else 'NOT_CONVERGED', 'converged': complete,
                'checks': checks, 'metrics': {'temperature_final': metric},
                'pending_validations': ['physical_validation'],
                'provenance': {'versions': self.input_runtime_identity(),
                               'scope': 'EXAMPLE_ONLY_LAB_ENVELOPE_REAL_EXISTING_ODE'},
                'raw_result': output.name + '/history.json'}


def make_lab(path):
    adapter = ExampleLabODE()
    return Lab(path, adapters={}, pde_adapters={}, analysis_adapters={},
        model_analysis_adapters={dm.ODE: adapter},
        doe_adapters={'scipy.latin_hypercube': ScipyLatinHypercube()},
        optimization_adapters={'scipy.differential_evolution': ScipyDifferentialEvolution()}), adapter


def register_rate(lab, settings=None):
    return lab.register_model_parameter(STUDY, dm.ODE, settings or model_settings(),
        'rate', 'cooling_rate', '냉각 계수', .05, .3)


def reference_records(lab, plan, result):
    records = []
    for sample in plan['samples']:
        folder = lab.store / 'experiments' / sample['model_experiment_id'] / 'simulation'
        actual = load_json(folder / 'pde/input.json')
        history = load_json(folder / 'history.json')
        assert canonical_hash(actual) == canonical_hash(sample['model_settings'])
        assert actual['solver']['method'] == plan['model_template']['solver']['method']
        parameters = {v['name']: v['value'] for v in actual['parameters']}
        assert parameters['rate'] == sample['values']['cooling_rate']
        times, observed = np.asarray(history['time']), np.asarray(history['temperature'])
        reference = parameters['ambient'] + (300. - parameters['ambient']) * np.exp(-parameters['rate'] * times)
        tolerance = actual['states'][0]['atol'] + actual['solver']['rtol'] * np.abs(reference)
        error = float(np.max(np.abs(observed - reference) / tolerance))
        # The same declared pointwise criterion used in the original mixed ODE
        # example; no change to solver settings, policy or numerical tolerance.
        assert history['execution_status'] == 'SUCCEEDED' and error <= 1.
        original = lab.inspect_experiment(sample['model_experiment_id'])
        assert original['input_parameters'] == sample['values']
        assert original['metrics']['temperature_final']['value'] == float(observed[-1])
        records.append({'experiment_id': sample['model_experiment_id'], 'values': sample['values'],
            'actual_rate': parameters['rate'], 'solver_method': actual['solver']['method'],
            'temperature_final_K': float(observed[-1]), 'max_normalized_error': error,
            'actual_input_sha256': canonical_hash(actual)})
    assert len({r['temperature_final_K'] for r in records}) == len(records)
    return records


def run(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    lab, adapter = make_lab(output / 'lab')
    lab.create_study(STUDY, '기존 숫자 계수', '숫자 등록 경로가 보존되는가?',
                     '계수만 바꾸고 적분 방법은 유지', '실제 ODE 응답과 원 입력 대조')
    settings = model_settings()
    original = canonical_hash(settings)
    description = mp.describe(lab, dm.ODE, settings)
    candidates = lab.discover_model_parameters(dm.ODE, settings)
    entry = register_rate(lab, settings)
    assert entry['input_effect']['status'] == 'PASS'
    assert adapter.calls == 0 and canonical_hash(settings) == original
    plan = lab.plan_model_doe(study_id=STUDY, campaign_id=CAMPAIGN, backend=dm.ODE,
        settings=settings, parameter_ids=['cooling_rate'], sample_count=4, seed=13,
        required_validations={'model': ['integration']})
    assert adapter.calls == 0
    result = lab.run_doe(CAMPAIGN)
    assert result['status'] == 'COMPLETED_REVIEW_REQUIRED' and adapter.calls == 4
    records = reference_records(lab, plan, result)
    calls = adapter.calls
    assert canonical_hash(lab.inspect_doe(CAMPAIGN)) == canonical_hash(result)
    assert adapter.calls == calls and canonical_hash(settings) == original
    receipt = {'scope': 'EXAMPLE_FACADE_PLUS_EXISTING_LAB_REGISTRY_MODEL_DOE_AND_REAL_ODE',
        'public_apis': ['Lab.discover_model_parameters', 'Lab.register_model_parameter',
                       'Lab.plan_model_doe', 'Lab.run_doe', 'Lab.inspect_doe'],
        'runtime': adapter.input_runtime_identity(), 'discovered_numeric_ids': [r['native']['path'] for r in candidates],
        'full_descriptors': description['descriptors'], 'source_sha256': entry['source_sha256'],
        'model_revision': entry['model_template_revision'], 'input_effect': entry['input_effect'],
        'calls_after_describe_register_plan': 0, 'real_ode_calls': adapter.calls,
        'read_extra_solver_calls': adapter.calls - calls, 'records': records,
        'result_sha256': canonical_hash(result), 'status': 'PASS',
        'not_run': ['Windows', 'Qt', 'FELUPE', 'full_product_acceptance']}
    save_json(output / 'receipt.json', receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    receipt = run(args.output)
    print(json.dumps({'status': receipt['status'], 'real_ode_calls': receipt['real_ode_calls'],
                      'receipt': str(args.output / 'receipt.json')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
