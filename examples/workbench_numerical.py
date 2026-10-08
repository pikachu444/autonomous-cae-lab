"""Actual two-coefficient material fit, callable studies and measured overhead.

Run: python examples/workbench_numerical.py --output /tmp/workbench-numerical
Requires optional FELUPE material installation (GPL-3.0-or-later); plots need
matplotlib. This demo uses synthetic observations, not measured calibration.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from time import perf_counter
import tracemalloc

import numpy as np
from caelab import prepare, read_result
from caelab.evaluation import PreparedEvaluation, save_evaluation
from caelab.numerical import (fit_model, run_doe, optimize, run_uq, analyze_candidates,
                             fit_surrogate, export_batch, import_batch, epsilon_optimize)


def response(value):
    return {'kind': 'scalar', 'value': value, 'unit': '1', 'component': 'scalar',
            'location': 'mathematical_model', 'reduction': 'none'}


def mathematical_model(values, settings):
    x, y = values['x'], values['y']
    return {'execution_status': 'SUCCEEDED',
            'responses': {'cost': response((x - .3) ** 2 + (y - .7) ** 2),
                          'second_cost': response((x - .8) ** 2 + (y - .2) ** 2),
                          'sum': response(x + y)}}


class MathematicalBatch:
    def prepare(self, settings, *, runtime=None):
        return PreparedEvaluation(lambda v: mathematical_model(v, settings), settings,
                                  batch=lambda rows: [mathematical_model(v, settings) for v in rows])


def material_history(mode, *, points=51):
    time = np.linspace(0, 1, points)
    F = np.tile(np.eye(3), (points, 1, 1))
    if mode == 'shear':
        F[:, 0, 1] += .01 * np.sin(np.pi * time)
    elif mode == 'holdout':
        F[:, 0, 0] += .006 * np.sin(np.pi * time / 2)
        F[:, 1, 1] += .001 * time
    else:
        F[:, 0, 0] += .005 * np.sin(np.pi * time)
    return {'model': 'linear_elastic', 'time': time.tolist(), 'deformation_gradient': F.tolist(),
            'parameters': {'E': 1500., 'nu': .29}, 'stress_unit': 'MPa'}


def material_experiments():
    experiments = []
    for name, channel, role in [('axial', 'stress_yy', 'fit'), ('shear', 'stress_xy', 'fit'),
                                ('holdout', 'stress_xx', 'holdout')]:
        settings = material_history(name)
        with prepare('material.felupe', settings) as model:
            observations = model.evaluate({})['responses'][channel]
        settings['parameters'] = {'E': 900., 'nu': .2}
        experiments.append({'id': name, 'role': role, 'settings': settings, 'response': channel,
                            'observations': observations, 'weight': 1., 'scale': 1.})
    return experiments


def measure(call):
    tracemalloc.start()
    started = perf_counter()
    result = call()
    elapsed = perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, {'wall_seconds': elapsed, 'parent_python_peak_bytes': peak,
                    'memory_scope': 'Parent Python allocations only; excludes native heaps and process workers'}


def benchmark_material(variables, candidates, settings, output):
    import felupe
    start = perf_counter()
    F = np.moveaxis(np.asarray(settings['deformation_gradient']), 0, -1)[:, :, None, :]
    state = np.zeros((0, 1, len(settings['time'])))
    preparation = perf_counter() - start
    def direct():
        observations = []
        for row in candidates:
            material = felupe.LinearElastic(E=row['E'], nu=row['nu'])
            # Same stress/tangent calculation basis as the prepared adapter.
            stress = material.gradient([F.copy(), state.copy()])[0]
            material.hessian([F, state])
            observations.append(stress[0, 0, 0].copy())
        return observations
    direct_values, direct_timing = measure(direct)
    direct_timing.update(preparation_seconds=preparation, model_calls=len(candidates), file_count=0)
    serial, serial_timing = measure(lambda: run_doe('material.felupe', variables, settings=settings, candidates=candidates))
    process, process_timing = measure(lambda: run_doe('material.felupe', variables, settings=settings, candidates=candidates,
                                                    execution={'mode': 'process', 'workers': 2}))
    for table in (serial, process):
        if table['execution_status'] != 'SUCCEEDED':
            raise RuntimeError(f"Material benchmark failed: {table['termination_reason']}")
        for original, row in zip(direct_values, table['candidates']):
            np.testing.assert_allclose(original, row['responses']['stress_xx']['value'], rtol=1e-12, atol=1e-12)
    start = perf_counter()
    save_evaluation(serial, output / 'material-benchmark')
    record_seconds = perf_counter() - start
    start = perf_counter()
    read_result(output / 'material-benchmark')
    reread_seconds = perf_counter() - start
    serial_timing.update(serial['timing'])
    process_timing.update(process['timing'])
    serial_timing.update(record_seconds=record_seconds, reread_seconds=reread_seconds,
                         file_count=sum(path.is_file() for path in (output / 'material-benchmark').rglob('*')))
    return {'direct_library': direct_timing, 'prepared_serial': serial_timing, 'prepared_process': process_timing,
            'response_agreement': 'Stress history matches at all actual candidates',
            'limitations': ['Process startup dominates small material histories; this is not native solver speed evidence.',
                           'The baseline includes both library stress and tangent; adapter metadata/copies are measured overhead.',
                           'FELUPE preparation is done once per worker; law coefficients are set per candidate.']}


def save_plot(fit, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, len(fit['curves']), figsize=(12, 3), constrained_layout=True)
    for axis, curve in zip(axes, fit['curves']):
        time = curve['observations']['axes'][0]['values']
        axis.plot(time, curve['observations']['value'], label='Synthetic observation')
        axis.plot(time, curve['prediction'], '--', label='Fitted library response')
        axis.set(title=f"{curve['experiment_id']} ({curve['role']})", xlabel='Time [s]', ylabel='Stress [MPa]')
        axis.legend(fontsize=8)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    material_variables = [{'id': 'E', 'unit': 'MPa', 'value': 900., 'lower': 200., 'upper': 2500., 'transform': 'log'},
                          {'id': 'nu', 'unit': '1', 'value': .2, 'lower': .05, 'upper': .45}]
    fit = fit_model('material.felupe', material_variables, material_experiments(),
                    record={'path': output / 'fit', 'level': 'summary'})
    if fit['execution_status'] != 'SUCCEEDED':
        raise RuntimeError(f"Fit failed: {fit['failure_reason']}")
    save_plot(fit, output / 'fit-holdout.png')
    variables = [{'id': name, 'unit': '1', 'value': .5, 'lower': 0., 'upper': 1.} for name in ('x', 'y')]
    objective = {'response': 'cost', 'unit': '1', 'direction': 'minimize'}
    table = run_doe(mathematical_model, variables, count=40, seed=7,
                    record={'path': output / 'callable-doe', 'level': 'summary'})
    analysis = analyze_candidates(table, [objective, {'response': 'sum', 'unit': '1', 'direction': 'minimize'}])
    optimum = optimize(mathematical_model, variables, objective, seed=7,
                        options={'max_generations': 25, 'population_size': 10},
                        record={'path': output / 'optimization', 'level': 'summary'})
    uq = run_uq(mathematical_model, variables, {name: {'distribution': 'uniform'} for name in ('x', 'y')}, count=64,
                source={'origin': 'ASSUMED', 'reference': 'Independent uniform demonstration ranges'}, seed=7,
                thresholds=[{'response': 'sum', 'unit': '1', 'limit': 1.2}],
                record={'path': output / 'uq', 'level': 'summary'})
    holdout = run_doe(mathematical_model, variables,
                      candidates=[{'candidate_id': f'H{i}', 'values': {'x': x, 'y': y}} for i, (x, y) in enumerate([(.1, .2), (.4, .5), (.8, .9)])])
    surrogate = fit_surrogate(table, holdout, objective, options={'kernel': 'cubic'})
    epsilon = epsilon_optimize(mathematical_model, variables,
                               [objective, {'response': 'second_cost', 'unit': '1', 'direction': 'minimize'}],
                               threshold_grid=[[.05, .25]], options={'max_generations': 10, 'population_size': 8},
                               total_evaluation_budget=176, seed=7,
                               record={'path': output / 'epsilon', 'level': 'summary'})
    # Demonstrate file exchange with real computed results; the missing second
    # candidate remains unevaluated, rather than receiving a surrogate value.
    manifest = export_batch(variables, [{'x': .1, 'y': .2}, {'x': .3, 'y': .4}], output / 'exchange', case_id='math-case')
    actual = mathematical_model({'x': .1, 'y': .2}, {})
    actual.update(candidate_id='C000000', case_id='math-case', values={'x': .1, 'y': .2})
    imported = import_batch(manifest, [actual])
    points = [{'E': float(e), 'nu': float(n)} for e, n in zip(np.linspace(1000., 2000., 24), np.linspace(.1, .35, 24))]
    material_benchmark = benchmark_material(material_variables, points, material_history('axial'), output)
    math_candidates = [r['values'] for r in table['candidates']]
    _, batch_timing = measure(lambda: run_doe(MathematicalBatch(), variables, candidates=math_candidates, execution={'mode': 'batch'}))
    summary = {'kind': 'numerical_demo', 'material_fit_parameters': fit['parameters'],
               'fit_holdout_rmse': {c['experiment_id']: c['rmse'] for c in fit['curves']},
               'identification': fit['identification'], 'callable_doe_analysis': analysis,
               'best_candidate': optimum['best'], 'uq_statistics': uq['probability_statistics'],
               'surrogate_validation': surrogate.validation,
               'surrogate_predictions': surrogate.predict([{'x': .3, 'y': .7}, {'x': 1.2, 'y': .5}]),
               'epsilon_pareto': epsilon['pareto'], 'imported_batch': imported,
               'material_benchmark': material_benchmark, 'callable_batch_timing': batch_timing,
               'limitations': ['Observations are synthetic, generated by the same FELUPE law; this verifies fitting integration only.',
                               'No native solver, real measured material, or model provider was invoked.']}
    save_evaluation(summary, output / 'summary')
    print(json.dumps({'output': str(output), 'parameters': fit['parameters'],
                      'fit_holdout_rmse': summary['fit_holdout_rmse'], 'best_candidate': optimum['best']['values'],
                      'material_benchmark': material_benchmark}, indent=2))


if __name__ == '__main__':
    main()
