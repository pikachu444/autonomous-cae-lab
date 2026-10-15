"""Ordinary, offline Python/CLI example using the existing Numerical/ODE owners.

    python examples/numerical_mixed_domains.py --output <new-directory>
    python examples/numerical_mixed_domains.py --output <new-directory> --owner-cold
    python examples/numerical_mixed_domains.py --output <new-directory> --optimize

No GUI, AI provider, CAD, WSL or new optimizer is involved. The closed form is an
independent reference, not an engineering release or validation of all models.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from caelab import dimensioned_models as dm
from caelab.storage import canonical_hash
from caelab.variable_binding import ODE_METHOD_ID, ode_solver_descriptor
from caelab.variable_domains import VariableDomains, verify_retained


def model_settings():
    settings = dm.default_settings(dm.ODE)
    settings['states'] = [{'name': 'temperature', 'label': '온도', 'unit': 'K',
        'initial': 300., 'rhs': '-sink_rate*(temperature-ambient)',
        'reference': 'ambient+(initial-ambient)*exp(-sink_rate*t)', 'atol': 1e-9}]
    settings['parameters'] = [
        {'name': 'count', 'unit': '1', 'value': 1},
        {'name': 'base_rate', 'unit': '1/s', 'value': .1},
        {'name': 'sink_rate', 'unit': '1/s', 'value': .1},
        {'name': 'ambient', 'unit': 'K', 'value': 290.},
        {'name': 'initial', 'unit': 'K', 'value': 300.}]
    settings['time'] = {'start': 0., 'end': 2., 'samples': 21, 'unit': 's'}
    settings['solver'] = {'method': 'RK45', 'rtol': 1e-8, 'max_step': .005}
    return dm.validate_settings(dm.ODE, settings)


def declarations(methods=('RK45', 'DOP853', 'Radau', 'BDF')):
    choices = [c for c in ode_solver_descriptor(model_settings())['choices'] if c['value'] in methods]
    if len(choices) != len(methods):
        raise ValueError('Select distinct existing ODE methods')
    return [
        {'id': 'count', 'unit': '1', 'kind': 'integer', 'lower': 1, 'upper': 3, 'value': 1},
        {'id': 'base_rate', 'unit': '1/s', 'kind': 'discrete', 'values': [.1, .2], 'value': .1},
        {'id': 'sink_rate', 'unit': '1/s', 'mode': 'dependent',
         'lower': 0., 'upper': 1., 'expression': 'count * base_rate'},
        {'id': 'ambient', 'unit': 'K', 'mode': 'fixed', 'value': 290.},
        {'id': ODE_METHOD_ID, 'unit': '1', 'kind': 'categorical', 'choices': choices}]


def explicit_candidates(methods=('RK45', 'DOP853', 'Radau', 'BDF')):
    return [{'candidate_id': f'C{count}-{int(rate*10)}-{method}',
             'values': {'count': count, 'base_rate': rate, ODE_METHOD_ID: method}}
            for count in (1, 2, 3) for rate in (.1, .2) for method in methods]


def reference_check(table, *, output_root=None):
    """Compare every retained clock point with exp() and an independent solve_ivp call.

    solve_ivp here is the TEST reference; the product still uses its existing
    accepted-step integrators, preserving cancellation and partial output.
    """
    import numpy as np
    from scipy.integrate import solve_ivp
    settings = model_settings()
    rtol, atol = settings['solver']['rtol'], settings['states'][0]['atol']
    records = []
    for row in table['candidates']:
        assert row['execution_status'] == 'SUCCEEDED', row
        verify_retained(table['domain_input'], table['variables'], row)
        values = row['values']
        assert type(values['count']) is int
        assert values['sink_rate'] == values['count'] * values['base_rate']
        response = row['responses']['temperature']
        clock = np.asarray(response['axes'][0]['values'])
        observed = np.asarray(response['value'])
        exact = np.asarray([290. + 10. * math.exp(-values['sink_rate'] * float(t)) for t in clock])
        # A stated pointwise comparison criterion; rtol/atol are local solver
        # controls, not a general theorem bounding the global solution error.
        tolerance = atol + rtol * np.abs(exact)
        normalized_error = np.max(np.abs(observed - exact) / tolerance)
        assert normalized_error <= 1., (row['candidate_id'], normalized_error)
        independent = solve_ivp(lambda t, y: -values['sink_rate'] * (y - 290.),
            [float(clock[0]), float(clock[-1])], [300.], t_eval=clock,
            method=values[ODE_METHOD_ID], rtol=rtol, atol=atol,
            max_step=settings['solver']['max_step'])
        assert independent.success
        assert np.max(np.abs(independent.y[0] - exact) / tolerance) <= 1.
        assert row['diagnostics']['solver_method'] == values[ODE_METHOD_ID]
        binding = row['input_binding']
        assert binding['assignments'] == values
        assert binding['actual_inputs'][ODE_METHOD_ID] == values[ODE_METHOD_ID]
        if output_root is not None:
            native = Path(output_root) / row['evaluation_refs'][0]['relative']
            actual = json.loads((native / 'pde/input.json').read_text(encoding='utf-8'))
            assert actual['solver']['method'] == values[ODE_METHOD_ID]
            params = {v['name']: v['value'] for v in actual['parameters']}
            assert all(params[k] == values[k] for k in values if k != ODE_METHOD_ID)
            assert type(params['count']) is int
            assert canonical_hash(actual) == binding['bound_settings_sha256']
        records.append({'candidate_id': row['candidate_id'], 'method': values[ODE_METHOD_ID],
                        'final_temperature_K': float(observed[-1]),
                        'max_error_over_atol_plus_rtol_reference': float(normalized_error)})
    return {'comparison': 'each retained clock against closed form, atol + rtol*abs(reference)',
            'method_semantics': 'numerical integration setting, not a physical material',
            'rtol': rtol, 'atol_K': atol, 'records': records}


def command(wb, doc, operation, arguments=None):
    return wb.document_command(doc['id'], operation, arguments or {}, session_id=doc['session_id'],
        expected_generation=doc['generation'], command_id='C' + uuid.uuid4().hex)


def forbid_runtime():
    """Tripwires used only by this example/test, never a product execution mode."""
    from caelab.backends import get_backend
    from caelab.workbench import Workbench
    from caelab import numerical, dimensioned_expression
    stack = ExitStack()
    def no_work(*args, **kwargs):
        raise AssertionError('Read/save/preview/adopt/cold must not execute or resolve a candidate')
    stack.enter_context(patch.object(VariableDomains, 'resolve', no_work))
    stack.enter_context(patch.object(VariableDomains, 'sample_free', no_work))
    stack.enter_context(patch.object(VariableDomains, 'candidates', no_work))
    stack.enter_context(patch.object(dimensioned_expression, 'evaluate', no_work))
    stack.enter_context(patch.object(type(get_backend(dm.ODE)), 'run', no_work))
    for name in ('run_doe', 'optimize', 'fit_model'):
        stack.enter_context(patch.object(numerical, name, no_work))
    stack.enter_context(patch.object(Workbench, '_execute', no_work))
    stack.enter_context(patch.object(Workbench, 'submit', no_work))
    return stack


def owner_warm(workspace, *, methods=('RK45', 'DOP853')):
    from caelab.workbench import Workbench
    from caelab.evaluation_definition import document_reference
    wb = Workbench(workspace)
    try:
        source = wb.document_open(kind='pde', title='혼합 변수 온도 모델',
            draft={'backend': dm.ODE, 'settings': model_settings()})
        source = command(wb, source, 'document.save')['document']
        reference = document_reference(source)
        variables, candidates = declarations(methods), explicit_candidates(methods)
        request = {'purpose': '정수 개수·이산 계수·종속 냉각률·적분 방법 대조', 'operation': 'doe',
            'inputs': {'backend': dm.ODE, 'settings': deepcopy(source['draft']['settings']),
                       'variables': variables, 'candidates': candidates, 'responses': ['temperature']},
            'budget': {'evaluations': len(candidates)}}
        plan = wb.document_open(kind='numerical', title='혼합 변수 DOE',
            draft={'mode': 'request', 'request': request, 'source': reference})
        assert not plan['diagnostics'], plan['diagnostics']
        job = command(wb, plan, 'numerical.run')['job']['id']
        wb.manager._futures[job].result(timeout=120)
        assert wb.manager.status(job)['state'] == 'SUCCEEDED', wb.manager.status(job)
        plan = command(wb, wb.document_read(plan['id']), 'document.save')['document']
        table = wb.document_result(plan['id'], job)
        numerical_check = reference_check(table, output_root=wb.root/'results'/job)
        chosen = candidates[-1]['candidate_id']
        result_hash = canonical_hash(table)
        run_before = len(wb.manager.list())
        with forbid_runtime():
            preview = wb.desktop.pde_candidate_preview(plan['id'], job, chosen)
            result = wb.desktop.pde_adopt(plan['id'], job, chosen, pde_document_id=source['id'],
                session_id=source['session_id'], expected_generation=source['generation'],
                command_id='C' + uuid.uuid4().hex)
            adopted = result['document']
            assert adopted['draft'] == preview['draft']
            adopted = command(wb, adopted, 'document.save')['document']
            assert canonical_hash(wb.document_result(plan['id'], job)) == result_hash
            assert wb.numerical_documents.read(plan['id'])['runs'][0]['draft']['source'] == reference
        assert len(wb.manager.list()) == run_before
        return {'workspace': str(Path(workspace).resolve()), 'plan_id': plan['id'], 'job_id': job,
            'source_id': source['id'], 'source_reference': reference,
            'candidate_id': chosen, 'result_sha256': result_hash,
            'adopted_draft': adopted['draft'], 'adoptions': adopted['adoptions'],
            'job_count': run_before, 'numerical_reference': numerical_check,
            'warm_read_save_adopt_runtime_calls': 0}
    finally:
        assert wb.shutdown()['joined']


def cold_verify(workspace, receipt):
    from caelab.workbench import Workbench
    with forbid_runtime():
        wb = Workbench(workspace)
        try:
            plan = wb.document_open(kind='numerical', document_id=receipt['plan_id'])
            source = wb.document_open(kind='pde', document_id=receipt['source_id'])
            result = wb.document_result(plan['id'], receipt['job_id'])
            assert canonical_hash(result) == receipt['result_sha256']
            assert plan['runs'][0]['draft']['source'] == receipt['source_reference']
            assert source['draft'] == receipt['adopted_draft']
            assert source['adoptions'] == receipt['adoptions']
            for row in result['candidates']:
                verify_retained(result['domain_input'], result['variables'], row)
            preview = wb.desktop.pde_candidate_preview(plan['id'], receipt['job_id'], receipt['candidate_id'])
            assert preview['draft'] == receipt['adopted_draft']
            # Ordinary draft edit and re-save after cold reopening, without a job.
            edited = deepcopy(source['draft'])
            edited['settings']['time']['end'] = 3.
            source = command(wb, source, 'pde.update', {'draft': edited})['document']
            source = command(wb, source, 'document.save')['document']
            assert source['draft'] == edited and source['adoptions'] == receipt['adoptions']
            assert canonical_hash(wb.document_result(plan['id'], receipt['job_id'])) == receipt['result_sha256']
            assert len(wb.manager.list()) == receipt['job_count']
            return {'pid': os.getpid(), 'workspace': str(Path(workspace).resolve()),
                'cold_read_preview_save_runtime_calls': 0, 'edited_draft': edited,
                'result_sha256': receipt['result_sha256'], 'job_count': len(wb.manager.list())}
        finally:
            assert wb.shutdown()['joined']


def final_verify(workspace, receipt):
    """Third process verifies that the cold edit was actually persisted."""
    from caelab.workbench import Workbench
    with forbid_runtime():
        wb = Workbench(workspace)
        try:
            plan = wb.document_open(kind='numerical', document_id=receipt['plan_id'])
            source = wb.document_open(kind='pde', document_id=receipt['source_id'])
            assert source['draft'] == receipt['cold']['edited_draft']
            assert source['adoptions'] == receipt['adoptions']
            assert canonical_hash(wb.document_result(plan['id'], receipt['job_id'])) == receipt['result_sha256']
            assert len(wb.manager.list()) == receipt['job_count']
            return {'pid': os.getpid(), 'cold_edit_persisted': True,
                    'read_runtime_calls': 0, 'result_sha256': receipt['result_sha256']}
        finally:
            assert wb.shutdown()['joined']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--owner-cold', action='store_true')
    parser.add_argument('--optimize', action='store_true')
    parser.add_argument('--cold-workspace', type=Path)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--cold-final', action='store_true')
    args = parser.parse_args(argv)
    if args.cold_workspace:
        verify = final_verify if args.cold_final else cold_verify
        result = verify(args.cold_workspace, json.loads(args.receipt.read_text(encoding='utf-8')))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.output is None:
        parser.error('--output requires a new directory')
    args.output.mkdir(parents=True, exist_ok=False)
    if args.owner_cold:
        receipt = owner_warm(args.output / 'original-workspace')
        path = args.output / 'owner-receipt.json'
        path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
        relocated = args.output / 'relocated-workspace'
        shutil.move(str(args.output/'original-workspace'), relocated)
        completed = subprocess.run([sys.executable, str(Path(__file__).resolve()),
            '--cold-workspace', str(relocated.resolve()), '--receipt', str(path.resolve())],
            cwd=relocated, capture_output=True, text=True, encoding='utf-8', timeout=120, check=True)
        (args.output/'cold-stdout.txt').write_text(completed.stdout, encoding='utf-8')
        (args.output/'cold-stderr.txt').write_text(completed.stderr, encoding='utf-8')
        cold = json.loads(completed.stdout.strip().splitlines()[-1])
        assert cold['pid'] != os.getpid()
        cold_path = args.output / 'cold-receipt.json'
        cold_path.write_text(json.dumps({**receipt, 'cold': cold}, ensure_ascii=False, indent=2), encoding='utf-8')
        final_run = subprocess.run([sys.executable, str(Path(__file__).resolve()),
            '--cold-workspace', str(relocated.resolve()), '--receipt', str(cold_path.resolve()), '--cold-final'],
            cwd=relocated, capture_output=True, text=True, encoding='utf-8', timeout=120, check=True)
        (args.output/'final-stdout.txt').write_text(final_run.stdout, encoding='utf-8')
        (args.output/'final-stderr.txt').write_text(final_run.stderr, encoding='utf-8')
        final = json.loads(final_run.stdout.strip().splitlines()[-1])
        assert final['pid'] not in (os.getpid(), cold['pid'])
        complete = {'owner': receipt, 'cold': cold, 'final': final}
        (args.output/'completed.json').write_text(json.dumps(complete, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(complete, ensure_ascii=False, indent=2))
    else:
        from caelab.adapters.native_evaluation import NativeEvaluationFactory
        from caelab.numerical import run_doe, optimize
        from caelab.evaluation import save_evaluation
        output = args.output / 'evaluated'
        factory = NativeEvaluationFactory(dm.ODE, output/'evaluations', ['temperature'], retained_root=output)
        if args.optimize:
            result = optimize(factory, declarations(('RK45', 'DOP853')),
                {'response': 'temperature', 'unit': 'K', 'reduction': 'final', 'direction': 'minimize'},
                settings=model_settings(), seed=4,
                options={'population_size': 16, 'max_generations': 30, 'retain_responses': 'all'},
                execution={'max_evaluations': 12})
            assert result['best']['values']['count'] == 3 and result['best']['values']['base_rate'] == .2
        else:
            result = run_doe(factory, declarations(), settings=model_settings(), candidates=explicit_candidates())
        report = reference_check(result, output_root=output)
        save_evaluation(result, output, existing=True)
        (args.output/'reference.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
