"""CAD-free studies over the same prepared evaluations used by direct Python.

NumPy/SciPy perform the numerical work. Candidates retain actual evaluation
status; predictions, unevaluated exchange rows and failed runs stay distinct.
No study registry, AI provider or native solver is needed to analyze a table.
"""
from __future__ import annotations

import atexit
from contextlib import ExitStack
from copy import deepcopy
from concurrent.futures import ProcessPoolExecutor
from itertools import product
import math
import multiprocessing
from pathlib import Path
import pickle
from time import perf_counter

import numpy as np
import scipy
from scipy.interpolate import RBFInterpolator
from scipy.optimize import least_squares
from scipy.stats import qmc, norm, truncnorm, lognorm

from .optimizers.scipy_de import ScipyDifferentialEvolution
from .optimizers import campaign_analysis as analysis
from .execution_control import ExecutionCleanupFailed


class StudyCancelled(RuntimeError):
    """Cancellation at a safe candidate boundary, with completed rows retained."""


class EvaluationFailed(RuntimeError):
    """An actual evaluation cannot supply the declared numerical response."""


class EvaluationBudgetExceeded(RuntimeError):
    """A candidate group would exceed its declared total model evaluation budget."""


class _Budget:
    def __init__(self, limit=None):
        self.limit, self.used = limit, 0
    def reserve(self, count):
        if self.limit is not None and self.used + count > self.limit:
            raise EvaluationBudgetExceeded(f"Evaluation budget {self.limit} exhausted: {self.used} dispatched; next group needs {count}")
        self.used += count


def _number(value, label):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)):
        raise ValueError(f"{label} must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return value


def _variables(variables):
    if not isinstance(variables, list) or not variables:
        raise ValueError("Declare at least one numerical variable")
    result = []
    for item in variables:
        name = item.get('id', item.get('parameter_id'))
        if not isinstance(name, str) or not name or name in {v['id'] for v in result}:
            raise ValueError("Variable IDs must be nonempty and distinct")
        unit = item.get('unit')
        if not isinstance(unit, str) or not unit:
            raise ValueError(f"Declare the unit of {name}")
        low = _number(item.get('lower', item.get('lower_bound')), f'{name} lower bound')
        high = _number(item.get('upper', item.get('upper_bound')), f'{name} upper bound')
        if low >= high or not math.isfinite(high - low) or not math.isfinite(high + low):
            raise ValueError(f"{name} requires increasing finite bounds")
        transform = item.get('transform', 'linear')
        if transform not in ('linear', 'log') or (transform == 'log' and low <= 0):
            raise ValueError("Transform must be linear or log with positive bounds")
        initial = _number(item.get('value', item.get('initial', (low + high) / 2)), f'{name} initial value')
        if not low <= initial <= high:
            raise ValueError(f"{name} initial value lies outside its bounds")
        result.append(dict(id=name, unit=unit, lower=low, upper=high, value=initial, transform=transform))
    return result


def _encoded(variables):
    return [dict(parameter_id=v['id'], target='numerical', kind='continuous', mode='free',
                 lower_bound=math.log(v['lower']) if v['transform'] == 'log' else v['lower'],
                 upper_bound=math.log(v['upper']) if v['transform'] == 'log' else v['upper'])
            for v in variables]


def _decode(values, variables):
    return {v['id']: float(math.exp(values[v['id']]) if v['transform'] == 'log' else values[v['id']])
            for v in variables}


def _initial(variables):
    return {v['id']: math.log(v['value']) if v['transform'] == 'log' else v['value'] for v in variables}


def _execution(execution):
    opts = dict(execution or {})
    unknown = set(opts) - {'mode', 'workers', 'threads', 'memory_mb', 'on_failure', 'cancelled', 'runtime', 'max_evaluations'}
    if unknown:
        raise ValueError(f"Unknown execution options: {sorted(unknown)}")
    opts.setdefault('mode', 'serial')
    opts.setdefault('workers', 1)
    opts.setdefault('on_failure', 'continue')
    if opts['mode'] not in ('serial', 'batch', 'process'):
        raise ValueError("Execution mode must be serial, batch or process")
    if type(opts['workers']) is not int or opts['workers'] < 1:
        raise ValueError("workers must be a positive integer")
    if opts['mode'] != 'process' and opts['workers'] != 1:
        raise ValueError("Multiple workers require process mode")
    if opts['on_failure'] not in ('continue', 'stop'):
        raise ValueError("on_failure must be continue or stop")
    if opts.get('cancelled') is not None and not callable(opts['cancelled']):
        raise ValueError("cancelled must be a local callable")
    for key in ('threads', 'memory_mb', 'max_evaluations'):
        if key in opts and (type(opts[key]) is not int or opts[key] < 1):
            raise ValueError(f"{key} must be a positive integer")
    return opts


def _failure(reason, status='FAILED'):
    return {'execution_status': status, 'responses': {}, 'checks': [], 'diagnostics': {'failure_reason': str(reason)}}


def _safe_evaluate(prepared, values):
    started = perf_counter()
    try:
        result = prepared.evaluate(values)
    except ExecutionCleanupFailed:
        # Mutable/unreaped native outputs cannot be sealed as a failed row.
        raise
    except Exception as error:
        from .execution_control import ExecutionCancelled
        result = _failure(f'{type(error).__name__}: {error}',
                          'CANCELLED' if isinstance(error, ExecutionCancelled) else 'FAILED')
    return result, perf_counter() - started


_worker_models = None
_worker_token = None


def _worker_init(evaluator, configurations, runtime, cancel_event):
    from .evaluation import prepare
    global _worker_models, _worker_token
    from .execution_control import CancellationToken
    _worker_token = CancellationToken()
    _worker_token._requested = cancel_event
    _worker_models = []
    try:
        for settings in configurations:
            _worker_models.append(prepare(evaluator, settings, runtime=runtime))
    except Exception:
        for model in _worker_models:
            model.close()
        raise
    atexit.register(lambda: [model.close() for model in _worker_models])


def _worker_evaluate(values):
    from .execution_control import cancellation_scope
    with cancellation_scope(_worker_token):
        try:
            return [_safe_evaluate(model, values) for model in _worker_models]
        except ExecutionCleanupFailed as error:
            # Keep the live process owner in its worker until cleanup is proven.
            # The parent remains running/cancel-requested and retains resources.
            owned_pending = _worker_token.cleanup_pending
            while _worker_token.cleanup_pending:
                _worker_token.retry_cleanup(timeout=1)
            if owned_pending:
                status = 'CANCELLED' if _worker_token.requested else 'FAILED'
                return [(_failure(f'{error}; owned cleanup subsequently confirmed',status),0.) for _ in _worker_models]
            raise


class _Evaluators:
    def __init__(self, evaluator, configurations, execution=None, *, budget=None):
        self.evaluator = evaluator
        self.configurations = configurations
        self.options = _execution(execution)
        self.stack = ExitStack()
        self.models = []
        self.executor = None
        self.cancel_event = None
        self.preparation_seconds = 0.0
        self.model_seconds = 0.0
        self.model_calls = 0
        self.budget = budget or _Budget(self.options.get('max_evaluations'))

    def __enter__(self):
        from .evaluation import prepare
        start = perf_counter()
        runtime = dict(self.options.get('runtime') or {})
        runtime.update({key: self.options[key] for key in ('threads', 'memory_mb') if key in self.options})
        try:
            if self.options['mode'] == 'process':
                if hasattr(self.evaluator, 'evaluate') and not hasattr(self.evaluator, 'prepare'):
                    raise ValueError("Process execution requires a backend or serializable factory, not a prepared handle")
                try:
                    pickle.dumps((self.evaluator, self.configurations, runtime))
                except Exception as error:
                    raise ValueError("Process execution requires a serializable evaluator/factory and settings") from error
                context = multiprocessing.get_context('spawn')
                self.cancel_event = context.Event()
                self.executor = self.stack.enter_context(ProcessPoolExecutor(
                    max_workers=self.options['workers'], mp_context=context,
                    initializer=_worker_init, initargs=(self.evaluator, self.configurations, runtime,self.cancel_event)))
            else:
                for settings in self.configurations:
                    model = prepare(self.evaluator, settings, runtime=runtime)
                    self.stack.callback(model.close)
                    self.models.append(model)
                if self.options['mode'] == 'batch' and any(not callable(getattr(model, 'evaluate_batch', None)) for model in self.models):
                    raise ValueError("Batch execution requires an explicit evaluate_batch capability")
        except BaseException:
            self.stack.close()
            raise
        self.preparation_seconds = perf_counter() - start
        return self

    def __exit__(self, *args):
        return self.stack.__exit__(*args)

    def cancelled(self):
        from .execution_control import check_cancelled, ExecutionCancelled
        try:
            check_cancelled()
        except ExecutionCancelled:
            return True
        callback = self.options.get('cancelled')
        return callback is not None and bool(callback())

    def many(self, values):
        if self.cancelled():
            raise StudyCancelled('Cancelled before next candidate evaluation')
        self.budget.reserve(len(values) * len(self.configurations))
        mode = self.options['mode']
        if mode == 'batch':
            by_model = []
            for model in self.models:
                start = perf_counter()
                try:
                    outputs = model.evaluate_batch(values)
                    if len(outputs) != len(values):
                        raise ValueError("Batch output count differs from candidate count")
                except ExecutionCleanupFailed:
                    raise
                except Exception as error:
                    outputs = [_failure(f'{type(error).__name__}: {error}') for _ in values]
                elapsed = (perf_counter() - start) / max(1, len(values))
                by_model.append([(out, elapsed) for out in outputs])
            completed = [list(group) for group in zip(*by_model)]
        elif mode == 'process':
            from concurrent.futures import wait
            from concurrent.futures.process import BrokenProcessPool
            futures = [self.executor.submit(_worker_evaluate, item) for item in values]
            pending = set(futures)
            while pending:
                if self.cancelled():
                    self.cancel_event.set()
                _, pending = wait(pending, timeout=.1)
            try:
                completed = [future.result() for future in futures]
            except BrokenProcessPool as error:
                raise ExecutionCleanupFailed('A numerical worker disappeared; descendant cleanup cannot be confirmed') from error
        else:
            completed = [[_safe_evaluate(model, item) for model in self.models] for item in values]
        self.model_calls += len(values) * len(self.configurations)
        self.model_seconds += sum(elapsed for group in completed for _, elapsed in group)
        return [[out for out, _ in group] for group in completed]

    def one(self, values):
        return self.many([values])[0]

    def timing(self):
        return {'preparation_seconds': self.preparation_seconds, 'model_seconds_sum': self.model_seconds,
                'model_calls': self.model_calls, 'mode': self.options['mode'], 'workers': self.options['workers'],
                'max_evaluations': self.budget.limit, 'dispatched_evaluations_total': self.budget.used,
                'process_startup_in_first_evaluation': self.options['mode'] == 'process'}


def _reason(evaluation):
    if evaluation.get('execution_status') == 'SUCCEEDED':
        return None
    return evaluation.get('diagnostics', {}).get('failure_reason', evaluation.get('execution_status', 'Missing status'))


def _row(identifier, values, evaluation):
    return {'candidate_id': identifier, 'values': deepcopy(values),
            'execution_status': evaluation.get('execution_status', 'FAILED'),
            'failure_reason': _reason(evaluation), 'responses': deepcopy(evaluation.get('responses', {})),
            'checks': deepcopy(evaluation.get('checks', [])), 'diagnostics': deepcopy(evaluation.get('diagnostics', {}))}


def _record(result, record):
    if record is None or record == 'none':
        return result
    if not isinstance(record, dict) or set(record) - {'path', 'level', 'selected'}:
        raise ValueError("record is {path, level: summary|selected, selected?: candidate IDs}")
    level = record.get('level', 'summary')
    if level == 'none':
        return result
    if level not in ('summary', 'selected') or not record.get('path'):
        raise ValueError("Recorded studies require a path and summary or selected level")
    retained = deepcopy(result)
    selected = set(record.get('selected', []))
    if selected - {row['candidate_id'] for row in retained.get('candidates', [])}:
        raise ValueError("Selected record IDs must belong to the current candidate table")
    for row in retained.get('candidates', []):
        if level == 'summary' or row['candidate_id'] not in selected:
            row['responses'] = {name: response for name, response in row.get('responses', {}).items()
                                if response.get('kind') in ('scalar', 'event')}
    from .evaluation import save_evaluation
    start = perf_counter()
    save_evaluation(retained, record['path'])
    result['record'] = {'path': str(record['path']), 'level': level, 'seconds': perf_counter() - start}
    return result


def _candidates(candidates, variables):
    rows, names = [], {v['id'] for v in variables}
    for index, candidate in enumerate(candidates):
        values = candidate.get('values', candidate)
        if set(values) != names:
            raise ValueError("Every candidate must contain exactly the declared variables")
        values = {name: _number(value, name) for name, value in values.items()}
        if any(not v['lower'] <= values[v['id']] <= v['upper'] for v in variables):
            raise ValueError("Candidate value outside declared bounds")
        identifier = candidate.get('candidate_id', f'C{index:06d}') if 'values' in candidate else f'C{index:06d}'
        if not isinstance(identifier, str) or not identifier or identifier in {r['candidate_id'] for r in rows}:
            raise ValueError("Candidate IDs must be nonempty and distinct")
        rows.append({'candidate_id': identifier, 'values': values})
    if not rows:
        raise ValueError("At least one candidate is required")
    return rows


def run_doe(evaluator_or_factory, variables, *, settings=None, candidates=None, count=16, seed=0,
            execution=None, record=None):
    """Evaluate specified or SciPy LHS candidates; failures/cancellations retain IDs."""
    variables = _variables(variables)
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("seed must be an unsigned 32-bit integer")
    if candidates is None:
        if type(count) is not int or count < 1:
            raise ValueError("count must be a positive integer")
        encoded = _encoded(variables)
        cube = qmc.LatinHypercube(len(variables), rng=np.random.default_rng(seed)).random(count)
        points = qmc.scale(cube, [v['lower_bound'] for v in encoded], [v['upper_bound'] for v in encoded])
        candidates = [_decode(dict(zip([v['id'] for v in variables], point)), variables) for point in points]
        sampling = {'method': 'scipy.latin_hypercube', 'seed': seed, 'count': count, 'scipy_version': scipy.__version__,
                    'coordinates': [v['transform'] for v in variables]}
    else:
        sampling = {'method': 'specified', 'count': len(candidates)}
    pending = _candidates(candidates, variables)
    rows, stop_reason = [], None
    started = perf_counter()
    with _Evaluators(evaluator_or_factory, [settings or {}], execution) as models:
        # Bound process submissions so cancellation retains completed work and
        # does not queue the whole study into an uninterruptible executor.
        width = models.options['workers'] if models.options['mode'] == 'process' else (len(pending) if models.options['mode'] == 'batch' else 1)
        if models.budget.limit is not None:
            width = min(width, models.budget.limit)
        for offset in range(0, len(pending), width):
            group = pending[offset:offset + width]
            if stop_reason or models.cancelled():
                stop_reason = stop_reason or 'USER_CANCELLED'
                rows.extend(_row(item['candidate_id'], item['values'], _failure(stop_reason, 'REJECTED' if stop_reason == 'EVALUATION_BUDGET_EXHAUSTED' else 'CANCELLED')) for item in group)
                continue
            try:
                outputs = models.many([item['values'] for item in group])
            except StudyCancelled:
                stop_reason = 'USER_CANCELLED'
                outputs = [[_failure(stop_reason, 'CANCELLED')] for _ in group]
            except EvaluationBudgetExceeded:
                stop_reason = 'EVALUATION_BUDGET_EXHAUSTED'
                outputs = [[_failure(stop_reason, 'REJECTED')] for _ in group]
            except ExecutionCleanupFailed:
                raise
            except Exception as error:
                outputs = [[_failure(f'{type(error).__name__}: {error}')] for _ in group]
            for item, evaluations in zip(group, outputs):
                rows.append(_row(item['candidate_id'], item['values'], evaluations[0]))
                if rows[-1]['execution_status'] == 'CANCELLED':
                    stop_reason = 'USER_CANCELLED'
                if rows[-1]['execution_status'] != 'SUCCEEDED' and models.options['on_failure'] == 'stop':
                    stop_reason = stop_reason or 'STOPPED_AFTER_FAILURE'
        timing = models.timing()
    timing['total_seconds'] = perf_counter() - started
    return _record({'kind': 'doe', 'variables': variables, 'sampling': sampling, 'candidates': rows,
                    'execution_status': ('REJECTED' if stop_reason == 'EVALUATION_BUDGET_EXHAUSTED' else 'CANCELLED') if stop_reason else ('SUCCEEDED' if all(r['execution_status'] == 'SUCCEEDED' for r in rows) else 'PARTIAL_FAILURE'),
                    'termination_reason': stop_reason or 'ALL_CANDIDATES_EVALUATED', 'timing': timing}, record)


def _scalar(evaluation, definition):
    if evaluation.get('execution_status') != 'SUCCEEDED':
        raise EvaluationFailed(str(_reason(evaluation)))
    name = definition.get('response', definition.get('metric'))
    response = evaluation.get('responses', {}).get(name)
    if response is None:
        response = next((entry for entry in evaluation.get('response_reductions', [])
                         if entry.get('response') == name and entry.get('reduction') == definition.get('reduction')), None)
    if response is None:
        raise EvaluationFailed(f'{name} is not an available scalar response')
    if response.get('unit') != definition.get('unit'):
        raise ValueError(f'{name} response unit differs from the declared unit')
    for key in ('component', 'location'):
        if key in definition and response.get(key) != definition[key]:
            raise ValueError(f'{name} response {key} differs from declaration')
    if response.get('kind') == 'scalar':
        if 'reduction' in definition and definition['reduction'] != response.get('reduction', 'none'):
            raise ValueError(f'{name} scalar reduction differs from declaration')
        return _number(response['value'], name)
    reduction = definition.get('reduction')
    if response.get('kind') not in ('series', 'field') or reduction not in ('max', 'min', 'final', 'mean', 'abs_max'):
        raise ValueError(f'{name}: a non-scalar response requires an explicit max/min/final/mean/abs_max reduction')
    data = np.asarray(response.get('value'), dtype=float)
    if not data.size or not np.all(np.isfinite(data)):
        raise EvaluationFailed(f'{name} cannot be reduced from missing/nonfinite data')
    if reduction == 'final':
        axes = response.get('axes', [])
        if response['kind'] != 'series' or data.ndim != 1 or len(axes) != 1:
            raise ValueError('final reduction requires a one-dimensional series and its ordered axis')
        coordinates = np.asarray(axes[0].get('values'), dtype=float)
        if coordinates.shape != data.shape or not np.all(np.isfinite(coordinates)) or np.any(np.diff(coordinates) <= 0):
            raise ValueError('final reduction requires strictly increasing finite coordinates')
        value = data[-1]
    else:
        value = {'max': np.max, 'min': np.min, 'mean': np.mean, 'abs_max': lambda x: np.max(abs(x))}[reduction](data)
    return _number(value, name)


def optimize(evaluator_or_factory, variables, objective, *, settings=None, constraints=None,
             seed=0, options=None, execution=None, record=None):
    """Existing differential evolution over direct variables and actual responses."""
    variables = _variables(variables)
    constraints = list(constraints or [])
    direction = objective.get('direction', 'minimize')
    if direction not in ('minimize', 'maximize'):
        raise ValueError("Objective direction must be minimize or maximize")
    scale = _number(objective.get('scale', 1), 'objective scale')
    if scale <= 0:
        raise ValueError("Objective scale must be positive")
    for constraint in constraints:
        if constraint.get('operator') not in ('<=', '>='):
            raise ValueError("Constraint operator must be <= or >=")
        _number(constraint.get('limit'), 'constraint limit')
        if _number(constraint.get('scale', 1), 'constraint scale') <= 0:
            raise ValueError("Constraint scale must be positive")
    opts = dict(options or {})
    if set(opts) - {'max_generations', 'population_size', 'initial_values', 'retain_responses'}:
        raise ValueError("Unknown DE options")
    retention = opts.get('retain_responses', 'summary')
    if retention not in {'summary', 'all'}:
        raise ValueError('retain_responses must be summary or all')
    physical_initial = opts.get('initial_values')
    initial = _initial(variables) if physical_initial is None else {
        v['id']: math.log(physical_initial[v['id']]) if v['transform'] == 'log' else physical_initial[v['id']] for v in variables}
    rows, cache, termination, algorithm = [], {}, None, None
    started = perf_counter()
    with _Evaluators(evaluator_or_factory, [settings or {}], execution) as models:
        prefetched, best_response = {}, None
        def feedback(encoded_values, *, journal_only=False):
            nonlocal best_response
            values = _decode(encoded_values, variables)
            key = tuple(values[v['id']].hex() for v in variables)
            if key in cache:
                return cache[key]
            if not journal_only and models.cancelled():
                raise StudyCancelled('USER_CANCELLED')
            try:
                evaluation = prefetched.pop(key) if key in prefetched else models.one(values)[0]
            except EvaluationBudgetExceeded:
                rows.append(dict(_row(f'C{len(rows):06d}', values,
                                      _failure('EVALUATION_BUDGET_EXHAUSTED', 'REJECTED')),
                                 objective=None, constraint_residuals=[None] * len(constraints), feasible=False))
                raise
            row = _row(f'C{len(rows):06d}', values, evaluation)
            row.update(objective=None, constraint_residuals=[None] * len(constraints), feasible=False)
            rows.append(row)
            if evaluation.get('execution_status') == 'CANCELLED' and not journal_only:
                raise StudyCancelled(str(row['failure_reason']))
            try:
                value = _scalar(evaluation, objective)
                residuals = [(_scalar(evaluation, c) - c['limit']) / c.get('scale', 1) * (1 if c['operator'] == '<=' else -1) for c in constraints]
                row.update(objective=value, constraint_residuals=residuals, feasible=all(r <= 0 for r in residuals))
                numeric = value / scale * (1 if direction == 'minimize' else -1)
            except EvaluationFailed as error:
                row['failure_reason'] = str(error)
                numeric, residuals = None, [None] * len(constraints)
            cache[key] = {'objective': numeric, 'constraint_residuals': residuals}
            if row['feasible'] and (best_response is None or numeric < best_response[0]):
                best_response = (numeric, row['candidate_id'], deepcopy(row['responses']))
            if retention == 'summary':
                row['response_reductions']=[]
                if evaluation.get('execution_status')=='SUCCEEDED':
                    for declaration in [objective]+constraints:
                        name=declaration.get('response',declaration.get('metric'))
                        original=row['responses'].get(name,{})
                        if original.get('kind') in {'series','field'}:
                            try:
                                reduced=_scalar(evaluation,declaration)
                            except EvaluationFailed:
                                continue
                            row['response_reductions'].append({
                                **{key:deepcopy(original[key]) for key in ('unit','component','location','source','coordinate_system') if key in original},
                                'response':name,'kind':'scalar','value':reduced,'reduction':declaration['reduction'],
                                'original_kind':original['kind']})
                row['responses'] = {name: response for name, response in row['responses'].items()
                                    if response.get('kind') in {'scalar', 'event'}}
            if not journal_only and row['execution_status'] != 'SUCCEEDED' and models.options['on_failure'] == 'stop':
                raise EvaluationFailed(row['failure_reason'])
            return cache[key]
        def feedback_many(points):
            # Bound outstanding native handles/results to one worker-width
            # group, while preserving deterministic journal order.
            width = models.options['workers'] if models.options['mode'] == 'process' else len(points)
            answers = []
            for offset in range(0, len(points), max(1, width)):
                group = points[offset:offset + width]
                pending = {}
                for point in group:
                    values = _decode(point, variables)
                    key = tuple(values[v['id']].hex() for v in variables)
                    if key not in cache:
                        pending[key] = values
                if pending:
                    try:
                        outputs = models.many(list(pending.values()))
                    except EvaluationBudgetExceeded:
                        for values in pending.values():
                            rows.append(dict(_row(f'C{len(rows):06d}', values,
                                _failure('EVALUATION_BUDGET_EXHAUSTED', 'REJECTED')),
                                objective=None, constraint_residuals=[None] * len(constraints), feasible=False))
                        raise
                    prefetched.update((key, output[0]) for key, output in zip(pending, outputs))
                first_row=len(rows)
                answers.extend(feedback(point,journal_only=True) for point in group)
                completed_rows=rows[first_row:]
                if any(row['execution_status']=='CANCELLED' for row in completed_rows) or models.cancelled():
                    raise StudyCancelled('USER_CANCELLED')
                if models.options['on_failure']=='stop' and any(row['execution_status']!='SUCCEEDED' for row in completed_rows):
                    raise EvaluationFailed('Completed candidate group contains a failed evaluation')
            return answers
        try:
            result = ScipyDifferentialEvolution().run(
                _encoded(variables), feedback, seed=seed,
                max_generations=opts.get('max_generations', 40), population_size=opts.get('population_size', 12),
                initial_values=initial, constraint_count=len(constraints),
                evaluate_many=feedback_many if models.options['mode'] in {'process', 'batch'} else None)
            termination, algorithm = result['termination_reason'], result['algorithm']
        except (StudyCancelled, EvaluationBudgetExceeded) as error:
            termination = 'USER_CANCELLED' if isinstance(error, StudyCancelled) else 'EVALUATION_BUDGET_EXHAUSTED'
        except EvaluationFailed:
            termination = 'STOPPED_AFTER_FAILURE'
        timing = models.timing()
    eligible = [row for row in rows if row['feasible'] and row['objective'] is not None]
    best = min(eligible, key=lambda row: row['objective'] * (1 if direction == 'minimize' else -1)) if eligible else None
    best = deepcopy(best)
    if best is not None and best_response is not None:
        best['responses'] = best_response[2]
    timing['total_seconds'] = perf_counter() - started
    return _record({'kind': 'optimization', 'variables': variables, 'objective_definition': deepcopy(objective),
                    'constraint_definitions': constraints, 'algorithm': algorithm, 'candidates': rows, 'best': best,
                    'response_retention': {'candidates': retention, 'best': 'all', 'native_originals': 'retained'},
                    'execution_status': 'CANCELLED' if termination == 'USER_CANCELLED' else ('REJECTED' if termination == 'EVALUATION_BUDGET_EXHAUSTED' else ('PARTIAL_FAILURE' if termination == 'STOPPED_AFTER_FAILURE' else ('SUCCEEDED' if best else 'FAILED'))),
                    'termination_reason': termination, 'timing': timing,
                    'limitations': ['Termination does not prove global optimality; a warm start is a new optimization run.']}, record)


def load_observations(path, mapping):
    """Read an explicit CSV/ASCII or NPZ curve mapping, retaining missing values.

    mapping contains value_column (CSV name/index or NPZ key), axis_column,
    axis_name, axis_unit, unit, component, location, reduction; optional delimiter,
    skip_header and numeric value_scale/axis_scale. Conversion is explicit.
    """
    path = Path(path)
    if path.suffix.lower() == '.npz':
        with np.load(path, allow_pickle=False) as data:
            values = np.asarray(data[mapping['value_column']], dtype=float)
            axis = np.asarray(data[mapping['axis_column']], dtype=float) if 'axis_column' in mapping else None
    else:
        named = isinstance(mapping['value_column'], str)
        data = np.genfromtxt(path, delimiter=mapping.get('delimiter', ','),
                             names=True if named else None, dtype=float,
                             skip_header=mapping.get('skip_header', 0),
                             ndmin=1 if named else 2, encoding='utf-8', invalid_raise=True)
        def column(key):
            return np.atleast_1d(data[key] if named else data[:, int(key)]).astype(float)
        values = column(mapping['value_column'])
        axis = column(mapping['axis_column']) if 'axis_column' in mapping else None
    response = {key: mapping[key] for key in ('unit', 'component', 'location', 'reduction')}
    response.update(kind='series' if axis is not None else 'scalar',
                    value=values * _number(mapping.get('value_scale', 1), 'value_scale'))
    if axis is not None:
        response['axes'] = [dict(name=mapping['axis_name'], unit=mapping['axis_unit'],
                                values=axis * _number(mapping.get('axis_scale', 1), 'axis_scale'))]
    return response


def _experiment(experiment):
    result = deepcopy(experiment)
    if not isinstance(result.get('id'), str) or not result['id']:
        raise ValueError("Every experiment needs an ID")
    if result.get('role', 'fit') not in ('fit', 'holdout'):
        raise ValueError("Experiment role must be fit or holdout")
    result.setdefault('role', 'fit')
    obs = result.get('observations')
    if isinstance(obs, dict) and 'path' in obs:
        obs = load_observations(obs['path'], obs['mapping'])
        result['observations'] = obs
    if not isinstance(obs, dict) or obs.get('kind') not in ('scalar', 'series', 'event'):
        raise ValueError("Observations declare scalar, series or event responses")
    for key in ('unit', 'component', 'location', 'reduction'):
        if not isinstance(obs.get(key), str):
            raise ValueError(f"Observation {key} must be declared explicitly")
    if obs['kind'] == 'event':
        # Events contribute one fixed residual; unknown events remain unknown
        # and stop LSQ rather than disappearing from the objective vector.
        if obs.get('state') not in ('OCCURRED', 'NOT_OBSERVED', 'UNKNOWN') or not isinstance(obs.get('event_definition'), dict):
            raise ValueError("Observed events require state and event_definition")
        result['_mask'] = np.array([True])
        result['weight'] = _number(result.get('weight', 1), 'event weight')
        result['scale'] = _number(result.get('scale', 1), 'event scale')
        if result['weight'] <= 0 or result['scale'] <= 0 or not isinstance(result.get('response'), str) or not result['response']:
            raise ValueError("Declare event response, positive weight and scale")
        return result
    values = np.asarray(obs.get('value'), dtype=float)
    if obs['kind'] == 'scalar':
        values = values.reshape(1) if values.size == 1 else values
    if values.ndim != 1 or not len(values):
        raise ValueError("Observations must be a nonempty scalar or one-dimensional curve")
    mask = np.asarray(result.get('mask', np.isfinite(values)), dtype=bool)
    if mask.shape != values.shape or not mask.any() or not np.all(np.isfinite(values[mask])):
        raise ValueError("Fixed observation mask must retain finite values")
    result['_mask'] = mask
    obs['value'] = values
    if obs['kind'] == 'series':
        axes = obs.get('axes', [])
        if len(axes) != 1 or not all(isinstance(axes[0].get(k), str) for k in ('name', 'unit')):
            raise ValueError("A curve requires one named axis and its unit")
        axis = np.asarray(axes[0].get('values'), dtype=float)
        if axis.shape != values.shape or not np.all(np.isfinite(axis)) or np.any(np.diff(axis) <= 0):
            raise ValueError("Observation axis must be finite and strictly increasing")
        axes[0]['values'] = axis
    result['weight'] = _number(result.get('weight', 1), 'curve weight')
    result['scale'] = _number(result.get('scale', 1), 'curve scale')
    if result['weight'] <= 0 or result['scale'] <= 0:
        raise ValueError("Curve weight and scale must be positive")
    if not isinstance(result.get('response'), str) or not result['response']:
        raise ValueError("Each experiment must select a model response")
    return result


def _aligned(evaluation, experiment):
    if evaluation.get('execution_status') != 'SUCCEEDED':
        raise EvaluationFailed(str(_reason(evaluation)))
    pred = evaluation.get('responses', {}).get(experiment['response'])
    obs = experiment['observations']
    if pred is None:
        raise EvaluationFailed(f"Missing response {experiment['response']}")
    if obs['kind'] == 'event':
        comparison = compare_events(pred, obs, nonoccurrence_penalty=experiment.get('nonoccurrence_penalty'),
                                    weight=experiment['weight'], scale=experiment['scale'])
        if not comparison['comparable']:
            raise EvaluationFailed(comparison['reason'])
        return np.array([pred.get('value') if pred.get('value') is not None else np.nan]), np.array([comparison['residual']])
    for key in ('kind', 'unit', 'component', 'location', 'reduction'):
        if pred.get(key) != obs[key]:
            raise ValueError(f"Experiment {experiment['id']} response {key} mismatch")
    for key in ('measure', 'frame', 'coordinate_system', 'coordinate_frame'):
        if key in obs and pred.get(key) != obs[key]:
            raise ValueError(f"Experiment {experiment['id']} response {key} mismatch")
    values = np.asarray(pred['value'], dtype=float)
    if obs['kind'] == 'scalar':
        if values.size != 1:
            raise ValueError("Scalar response must have exactly one value")
        aligned = values.reshape(1)
    else:
        axes = pred.get('axes', [])
        if len(axes) != 1 or any(axes[0].get(key) != obs['axes'][0][key] for key in ('name', 'unit')):
            raise ValueError("Prediction and observation axis name/unit must match")
        axis = np.asarray(axes[0].get('values'), dtype=float)
        if values.ndim != 1 or axis.shape != values.shape or not len(axis) or not np.all(np.isfinite(axis)) or np.any(np.diff(axis) <= 0):
            raise ValueError("Prediction axis must be finite and strictly increasing")
        target = obs['axes'][0]['values']
        # Unmasked values are the only observations that participate in the
        # fixed objective; masked points need not be extrapolated for a fit.
        used = target[experiment['_mask']]
        if used[0] < axis[0] or used[-1] > axis[-1]:
            raise ValueError("Observation axis lies outside prediction support; extrapolation is forbidden")
        aligned = np.full(target.shape, np.nan)
        aligned[experiment['_mask']] = np.interp(used, axis, values)
    used_values = aligned[experiment['_mask']]
    if not np.all(np.isfinite(used_values)):
        raise EvaluationFailed("Predictions are nonfinite at retained observations")
    residual = (used_values - obs['value'][experiment['_mask']]) * math.sqrt(experiment['weight'] / len(used_values)) / experiment['scale']
    return aligned, residual


def _nullable(value):
    """Unknown/masked observations are JSON null, never fabricated zero or NaN."""
    if isinstance(value, np.ndarray):
        return _nullable(value.tolist())
    if isinstance(value, dict):
        return {key: _nullable(item) for key,item in value.items()}
    if isinstance(value, (list,tuple)):
        return [_nullable(item) for item in value]
    if isinstance(value, (float,np.floating)) and not math.isfinite(value):
        return None
    return value


def compare_curves(prediction, observation, *, weight=1, scale=1, mask=None):
    """Compare imported or in-memory responses using the fitting residual contract."""
    experiment = {'id': 'comparison', 'response': 'response', 'observations': observation,
                  'weight': weight, 'scale': scale}
    if mask is not None:
        experiment['mask'] = mask
    experiment = _experiment(experiment)
    aligned, residual = _aligned({'execution_status': 'SUCCEEDED', 'responses': {'response': prediction}}, experiment)
    retained = experiment['_mask']
    difference = aligned[retained] - experiment['observations']['value'][retained]
    return {'method': 'linear_axis_alignment', 'unit': observation['unit'], 'weight': weight, 'scale': scale,
            'prediction': _nullable(aligned), 'observation': _nullable(experiment['observations']),
            'prediction_metadata': _nullable({k: v for k, v in prediction.items() if k not in ('value','axes','mask')}),
            'mask': retained.tolist(), 'residual': residual,
            'rmse': float(np.sqrt(np.mean(difference ** 2))), 'mae': float(np.mean(abs(difference))),
            'count': int(retained.sum()), 'objective': float(residual @ residual)}


def detect_event(response, threshold, *, direction='rising'):
    """First threshold crossing, observed nonoccurrence, or explicit unknown data.

    Threshold has the response's unit. Event time has the declared axis unit.
    Linear interpolation defines the crossing between adjacent output samples.
    """
    threshold = _number(threshold, 'threshold')
    if direction not in ('rising', 'falling'):
        raise ValueError("Event direction must be rising or falling")
    axes = response.get('axes', [])
    if response.get('kind') != 'series' or len(axes) != 1 or not axes[0].get('name') or not axes[0].get('unit'):
        raise ValueError("Event detection requires a series with one explicit axis and unit")
    if not response.get('unit') or not response.get('component') or not response.get('location'):
        raise ValueError("Event detection requires explicit response unit, component and location")
    time = np.asarray(axes[0].get('values', []), dtype=float)
    data = np.asarray(response.get('value', []), dtype=float)
    event = {'kind': 'event', 'value': None, 'state': 'UNKNOWN', 'unit': axes[0]['unit'],
             'component': response.get('component'), 'location': response.get('location'),
             'reduction': 'first_threshold_crossing', 'observed_interval': None,
             'event_definition': {'threshold': threshold, 'response_unit': response.get('unit'),
                                  'direction': direction, 'axis_name': axes[0]['name'],
                                  'interpolation': 'linear'}}
    if time.ndim != 1 or not len(time) or not np.all(np.isfinite(time)) or np.any(np.diff(time) <= 0):
        event['failure_reason'] = 'Missing, nonfinite or unordered observation axis'
        return event
    event['observed_interval'] = [float(time[0]), float(time[-1])]
    if data.shape != time.shape or not np.all(np.isfinite(data)):
        event['failure_reason'] = 'Missing or nonfinite response samples; event occurrence is unknown'
        return event
    passed = data >= threshold if direction == 'rising' else data <= threshold
    crossings = np.flatnonzero(passed)
    if not len(crossings):
        event['state'] = 'NOT_OBSERVED'
    else:
        index = int(crossings[0])
        if index == 0 and data[0] != threshold:
            event['failure_reason'] = 'Threshold already exceeded at the first sample; crossing time is outside recorded support'
            event['occurrence_known_before_or_at_window_start'] = True
            return event
        crossing = time[0] if index == 0 else time[index - 1] + (threshold - data[index - 1]) / (data[index] - data[index - 1]) * (time[index] - time[index - 1])
        event.update(state='OCCURRED', value=float(crossing))
    return event


def compare_events(prediction, observation, *, nonoccurrence_penalty=None, weight=1, scale=1):
    """Compare matched event definitions without turning missing times into zero."""
    weight, scale = _number(weight, 'event weight'), _number(scale, 'event scale')
    if weight <= 0 or scale <= 0:
        raise ValueError("Event weight and scale must be positive")
    for key in ('kind', 'unit', 'component', 'location', 'reduction', 'event_definition'):
        if key not in observation or prediction.get(key) != observation[key]:
            raise ValueError(f"Event {key} mismatch")
    if observation['kind'] != 'event':
        raise ValueError("Event comparison requires event responses")
    states = prediction.get('state'), observation.get('state')
    if any(state not in ('OCCURRED', 'NOT_OBSERVED', 'UNKNOWN') for state in states):
        raise ValueError("Event state must be OCCURRED, NOT_OBSERVED or UNKNOWN")
    result = {'prediction': deepcopy(prediction), 'observation': deepcopy(observation),
              'comparable': False, 'difference': None, 'residual': None, 'unit': observation['unit']}
    if 'UNKNOWN' in states:
        result['reason'] = 'MISSING_OR_UNDETERMINED_EVENT'
        return result
    intervals = []
    for event in (prediction, observation):
        interval = event.get('observed_interval')
        if not isinstance(interval, (list, tuple)) or len(interval) != 2:
            raise ValueError("Events require explicit observed intervals")
        start, end = [_number(value, 'observed interval') for value in interval]
        if start > end:
            raise ValueError("Observed interval is reversed")
        intervals.append((start, end))
        if event['state'] == 'OCCURRED' and not start <= _number(event.get('value'), 'event time') <= end:
            raise ValueError("Event time lies outside its observed interval")
    if states == ('OCCURRED', 'OCCURRED'):
        difference = prediction['value'] - observation['value']
        reason = 'EVENT_TIME_DIFFERENCE'
    elif states == ('NOT_OBSERVED', 'NOT_OBSERVED'):
        if intervals[0] != intervals[1]:
            result['reason'] = 'DIFFERENT_CENSORING_WINDOWS'
            return result
        difference, reason = 0., 'AGREEMENT_WITHIN_DECLARED_OBSERVATION_WINDOW'
    else:
        event_index = 0 if states[0] == 'OCCURRED' else 1
        if not intervals[1 - event_index][0] <= (prediction if event_index == 0 else observation)['value'] <= intervals[1 - event_index][1]:
            result['reason'] = 'EVENT_OUTSIDE_COMMON_OBSERVATION_WINDOW'
            return result
        if nonoccurrence_penalty is None:
            raise ValueError("Occurrence disagreement requires an explicitly configured nonoccurrence penalty")
        difference = _number(nonoccurrence_penalty, 'nonoccurrence penalty')
        if difference < 0:
            raise ValueError("Nonoccurrence penalty must be nonnegative")
        reason = 'CONFIGURED_OCCURRENCE_DISAGREEMENT_PENALTY'
    result.update(comparable=True, difference=float(difference), residual=float(difference * math.sqrt(weight) / scale), reason=reason)
    return result


def fit_model(evaluator_or_factory, variables, experiments, *, method='least_squares',
              options=None, execution=None, record=None):
    """Fit bounded coefficients to independent fit histories; holdout never tunes.

    Each experiment is {id, role, settings, response, observations, weight, scale,
    mask?}. Observation response metadata must match the evaluated response.
    Residuals are sqrt(weight / retained_count) * (prediction-observation)/scale.
    Missing masks are fixed once from finite observations before optimization.
    """
    variables = _variables(variables)
    experiments = [_experiment(e) for e in experiments]
    if len({e['id'] for e in experiments}) != len(experiments):
        raise ValueError("Experiment IDs must be distinct")
    fitted = [e for e in experiments if e['role'] == 'fit']
    if not fitted:
        raise ValueError("At least one fit experiment is required")
    if method not in ('least_squares', 'differential_evolution', 'de'):
        raise ValueError("Fit method must be least_squares or differential_evolution")
    opts = dict(options or {})
    penalty = opts.pop('failure_penalty', None)
    if penalty is not None and _number(penalty, 'failure penalty') <= 0:
        raise ValueError("Explicit failure penalty must be positive and finite")
    rows, cache, best_values, termination, failure_reason = [], {}, None, None, None
    candidate_status = {}
    names = [v['id'] for v in variables]
    encoded = _encoded(variables)
    x0 = np.asarray([_initial(variables)[name] for name in names])
    lower, upper = [v['lower_bound'] for v in encoded], [v['upper_bound'] for v in encoded]
    started = perf_counter()
    budget = _Budget(_execution(execution).get('max_evaluations'))
    with _Evaluators(evaluator_or_factory, [e.get('settings', {}) for e in fitted], execution, budget=budget) as models:
        prefetched = {}
        best_cached = None
        def residual_at(x, *, journal_only=False):
            nonlocal best_cached
            values = _decode(dict(zip(names, x)), variables)
            key = tuple(values[name].hex() for name in names)
            if key in cache:
                return cache[key][0]
            try:
                outputs = prefetched.pop(key) if key in prefetched else models.one(values)
            except EvaluationBudgetExceeded:
                rows.append({'candidate_id': f'C{len(rows):06d}', 'values': values, 'responses': {},
                             'execution_status': 'REJECTED', 'failure_reason': 'EVALUATION_BUDGET_EXHAUSTED', 'objective': None})
                raise
            cancelled = any(output.get('execution_status') == 'CANCELLED' for output in outputs)
            if cancelled:
                rows.append({'candidate_id': f'C{len(rows):06d}', 'values': values, 'responses': {},
                             'execution_status': 'CANCELLED', 'failure_reason': 'USER_CANCELLED', 'objective': None})
                candidate_status[key]='CANCELLED'
                cache[key]=None,outputs
                if not journal_only:
                    raise StudyCancelled('USER_CANCELLED')
                return None
            residuals, reasons = [], []
            for experiment, evaluation in zip(fitted, outputs):
                try:
                    residuals.append(_aligned(evaluation, experiment)[1])
                except EvaluationFailed as error:
                    reasons.append(f"{experiment['id']}: {error}")
            row = {'candidate_id': f'C{len(rows):06d}', 'values': values, 'responses': {},
                   'execution_status': 'FAILED' if reasons else 'SUCCEEDED',
                   'failure_reason': '; '.join(reasons) if reasons else None, 'objective': None}
            rows.append(row)
            candidate_status[key]=row['execution_status']
            if reasons:
                if penalty is not None:
                    residual = np.full(sum(int(e['_mask'].sum()) for e in fitted), penalty)
                    row['penalty_applied'] = penalty
                elif method == 'least_squares' and not journal_only:
                    raise EvaluationFailed(row['failure_reason'])
                else:
                    residual = None
            else:
                residual = np.concatenate(residuals)
                row['objective'] = float(residual @ residual)
            cache[key] = residual, outputs
            if not reasons and (best_cached is None or row['objective'] < best_cached[1]):
                best_cached = (key, row['objective'], residual, outputs)
            # Keep a small finite-difference neighborhood and the best actual
            # curves. A long fit must not retain every full native history.
            while len(cache)>8:
                del cache[next(iter(cache))]
            if reasons and not journal_only and models.options['on_failure']=='stop':
                raise EvaluationFailed(row['failure_reason'])
            return residual
        def check_group(first_row):
            completed_rows=rows[first_row:]
            if any(row['execution_status']=='CANCELLED' for row in completed_rows) or models.cancelled():
                raise StudyCancelled('USER_CANCELLED')
            failed=any(row['execution_status']!='SUCCEEDED' for row in completed_rows)
            if failed and (models.options['on_failure']=='stop' or (method=='least_squares' and penalty is None)):
                raise EvaluationFailed('Completed candidate group contains a failed evaluation')
        try:
            if method == 'least_squares':
                allowed = {'jac', 'ftol', 'xtol', 'gtol', 'x_scale', 'loss', 'f_scale', 'diff_step', 'max_nfev', 'verbose'}
                if set(opts) - allowed:
                    raise ValueError(f"Unknown least-squares options: {sorted(set(opts) - allowed)}")
                if opts.get('jac') == 'cs':
                    raise ValueError("Complex-step differentiation requires complex-valued backends; this evaluation contract supports real values")
                def derivative_map(fun, iterable):
                    # SciPy owns finite-difference construction. Only actual
                    # candidate evaluation is dispatched to prepared workers;
                    # residual assembly remains here with its fixed masks.
                    points = list(iterable)
                    pending_values, pending_keys = [], []
                    for point in points:
                        values = _decode(dict(zip(names, point)), variables)
                        key = tuple(values[name].hex() for name in names)
                        if key not in cache and key not in pending_keys:
                            pending_values.append(values)
                            pending_keys.append(key)
                    if pending_values:
                        try:
                            prefetched.update(zip(pending_keys, models.many(pending_values)))
                        except EvaluationBudgetExceeded:
                            first_id = len(rows)
                            rows.extend({'candidate_id': f'C{first_id + i:06d}', 'values': value, 'responses': {},
                                         'execution_status': 'REJECTED', 'failure_reason': 'EVALUATION_BUDGET_EXHAUSTED', 'objective': None}
                                        for i, value in enumerate(pending_values))
                            raise
                    first_row=len(rows)
                    completed=[residual_at(point,journal_only=True) for point in points]
                    check_group(first_row)
                    # SciPy's callable may apply its shape checks around our
                    # residual. Retain this bounded derivative group while it
                    # consumes it, even when the general curve cache is small.
                    for point,residual in zip(points,completed):
                        values=_decode(dict(zip(names,point)),variables)
                        key=tuple(values[name].hex() for name in names)
                        if key not in cache:
                            cache[key]=(residual,None)
                    return [fun(point) for point in points]
                worker_map = derivative_map if models.options['mode'] in ('batch', 'process') else None
                result = least_squares(residual_at, x0, bounds=(lower, upper), workers=worker_map, **opts)
                best_values = _decode(dict(zip(names, result.x)), variables)
                termination = str(result.message)
                convergence = bool(result.success)
                jacobian_rank = int(np.linalg.matrix_rank(result.jac))
                condition = float(np.linalg.cond(result.jac))
                identification = {'jacobian_rank': jacobian_rank, 'coefficient_count': len(variables),
                                  'condition_number': condition if math.isfinite(condition) else None}
            else:
                if set(opts) - {'seed', 'max_generations', 'population_size'}:
                    raise ValueError("Unknown differential-evolution fit options")
                def feedback(values):
                    residual = residual_at([values[name] for name in names])
                    return {'objective': None if residual is None else float(residual @ residual), 'constraint_residuals': []}
                def feedback_many(points):
                    width = models.options['workers'] if models.options['mode'] == 'process' else len(points)
                    answers = []
                    for offset in range(0, len(points), max(1, width)):
                        group = points[offset:offset + width]
                        pending = {}
                        for point in group:
                            values = _decode(point, variables)
                            key = tuple(values[name].hex() for name in names)
                            if key not in cache:
                                pending[key] = values
                        if pending:
                            try:
                                prefetched.update(zip(pending, models.many(list(pending.values()))))
                            except EvaluationBudgetExceeded:
                                for values in pending.values():
                                    rows.append({'candidate_id': f'C{len(rows):06d}', 'values': values, 'responses': {},
                                                 'execution_status': 'REJECTED', 'failure_reason': 'EVALUATION_BUDGET_EXHAUSTED', 'objective': None})
                                raise
                        first_row=len(rows)
                        for point in group:
                            residual=residual_at([point[name] for name in names],journal_only=True)
                            answers.append({'objective':None if residual is None else float(residual @ residual),
                                            'constraint_residuals':[]})
                        check_group(first_row)
                    return answers
                result = ScipyDifferentialEvolution().run(encoded, feedback, seed=opts.get('seed', 0),
                    max_generations=opts.get('max_generations', 40), population_size=opts.get('population_size', 12),
                    initial_values=_initial(variables), constraint_count=0,
                    evaluate_many=feedback_many if models.options['mode'] in {'batch', 'process'} else None)
                best_values = _decode(result['candidate_values'], variables) if result['objective'] is not None else None
                termination, convergence, identification = result['termination_reason'], result['converged'], {}
        except (StudyCancelled, EvaluationFailed, EvaluationBudgetExceeded) as error:
            termination = ('USER_CANCELLED' if isinstance(error, StudyCancelled) else
                           'EVALUATION_BUDGET_EXHAUSTED' if isinstance(error, EvaluationBudgetExceeded) else 'EVALUATION_FAILED')
            failure_reason, convergence, identification = str(error), False, {}
        eligible = [r for r in rows if r['execution_status'] == 'SUCCEEDED' and r['objective'] is not None]
        if best_cached is not None:
            cache[best_cached[0]] = best_cached[2], best_cached[3]
        if best_values is not None:
            key = tuple(best_values[name].hex() for name in names)
            if candidate_status.get(key) != 'SUCCEEDED':
                best_values = None
                failure_reason = 'Optimizer selected an explicitly penalized failed candidate'
                convergence = False
        if best_values is None and eligible:
            best_values = min(eligible, key=lambda r: r['objective'])['values']
        curves = []
        if best_values is not None:
            # Fit outputs already cached at the final candidate are reused.
            key = tuple(best_values[name].hex() for name in names)
            outputs = cache[key][1] if key in cache and cache[key][1] is not None else models.one(best_values)
            for e, output in zip(fitted, outputs):
                curves.append(_fit_curve(e, output))
            if any(curve['execution_status']!='SUCCEEDED' for curve in curves):
                failure_reason='Final candidate could not reproduce successful fit responses'
                convergence=False
        timing = models.timing()
    holdout = [e for e in experiments if e['role'] == 'holdout']
    if best_values is not None and holdout:
        with _Evaluators(evaluator_or_factory, [e.get('settings', {}) for e in holdout], execution, budget=budget) as models:
            try:
                outputs = models.one(best_values)
                curves.extend(_fit_curve(e, output) for e, output in zip(holdout, outputs))
            except StudyCancelled:
                curves.extend({'experiment_id': e['id'], 'role': 'holdout', 'execution_status': 'CANCELLED'} for e in holdout)
                termination, failure_reason = 'USER_CANCELLED', 'Holdout evaluation was cancelled'
            except EvaluationBudgetExceeded as error:
                curves.extend({'experiment_id': e['id'], 'role': 'holdout', 'execution_status': 'REJECTED',
                               'failure_reason': 'EVALUATION_BUDGET_EXHAUSTED'} for e in holdout)
                termination, failure_reason = 'EVALUATION_BUDGET_EXHAUSTED', str(error)
            extra = models.timing()
            timing['model_calls'] += extra['model_calls']
            timing['model_seconds_sum'] += extra['model_seconds_sum']
            timing['preparation_seconds'] += extra['preparation_seconds']
    timing['total_seconds'] = perf_counter() - started
    timing['dispatched_evaluations_total'] = budget.used
    return _record({'kind': 'fit', 'method': method, 'variables': variables, 'parameters': best_values,
                    'parameter_units': {v['id']: v['unit'] for v in variables}, 'curves': curves, 'candidates': rows,
                    'execution_status': 'CANCELLED' if termination == 'USER_CANCELLED' else ('REJECTED' if termination == 'EVALUATION_BUDGET_EXHAUSTED' else ('FAILED' if failure_reason or best_values is None else 'SUCCEEDED')),
                    'converged': convergence, 'termination_reason': termination, 'failure_reason': failure_reason,
                    'identification': identification, 'timing': timing,
                    'limitations': ['Small residuals do not establish parameter uniqueness or physical qualification.',
                                    'Fit and holdout are separated by experiment/history; no holdout data tunes the coefficients.']}, record)


def _fit_curve(experiment, evaluation):
    curve = {'experiment_id': experiment['id'], 'role': experiment['role'], 'response': experiment['response'],
             'observations': deepcopy(experiment['observations']), 'mask': experiment['_mask'].tolist(),
             'weight': experiment['weight'], 'scale': experiment['scale'],
             'execution_status': evaluation.get('execution_status', 'FAILED')}
    try:
        prediction, residual = _aligned(evaluation, experiment)
        if experiment['observations']['kind'] == 'event':
            predicted_event = evaluation['responses'][experiment['response']]
            comparison = compare_events(predicted_event, experiment['observations'],
                                        nonoccurrence_penalty=experiment.get('nonoccurrence_penalty'),
                                        weight=experiment['weight'], scale=experiment['scale'])
            curve.update(prediction=deepcopy(predicted_event), residual=residual, rmse=abs(comparison['difference']))
        else:
            curve['prediction_metadata'] = {k: v for k, v in evaluation['responses'][experiment['response']].items() if k not in ('value','axes','mask')}
            curve.update(prediction=prediction, residual=residual, rmse=float(np.sqrt(np.mean((prediction[experiment['_mask']] - experiment['observations']['value'][experiment['_mask']]) ** 2))))
    except EvaluationFailed as error:
        curve.update(execution_status='FAILED', failure_reason=str(error))
    return _nullable(curve)


def analyze_candidates(table, responses, *, seed=13):
    """Reuse existing statistics, regression influence, holdout fit and Pareto IDs."""
    variables = _variables(table['variables'])
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("Analysis seed must be an unsigned 32-bit integer")
    declarations = []
    for requested in responses:
        declaration = {'response': requested} if isinstance(requested, str) else dict(requested)
        name = declaration.get('response', declaration.get('metric'))
        declaration['response'] = name
        available = [row['responses'][name] for row in table['candidates'] if name in row.get('responses', {})]
        available += [entry for row in table['candidates'] for entry in row.get('response_reductions',[])
                      if entry['response']==name and entry['reduction']==declaration.get('reduction')]
        if isinstance(requested, str) and any(r.get('kind') != 'scalar' for r in available):
            raise ValueError(f'{name}: non-scalar analysis requires a declared reduction')
        if 'unit' not in declaration:
            units = {r.get('unit') for r in available}
            if len(units) != 1 or None in units:
                raise ValueError(f'{name}: an explicit unit is required for unavailable or inconsistent responses')
            declaration['unit'] = units.pop()
        declarations.append(declaration)
    definitions = [dict(metric=r.get('id', r['response']), unit=r['unit'], direction=r.get('direction', 'minimize')) for r in declarations]
    if not definitions or len({d['metric'] for d in definitions}) != len(definitions) or any(not isinstance(d['metric'], str) or not d['metric'] or not d['unit'] or d['direction'] not in ('minimize', 'maximize') for d in definitions):
        raise ValueError("Declare distinct named scalar responses, their units and directions")
    _candidates(table['candidates'], variables)
    samples = []
    for row in table['candidates']:
        metrics = {}
        for definition, declaration in zip(definitions, declarations):
            name = definition['metric']
            try:
                value = _scalar(row, declaration)
                valid = True
            except EvaluationFailed:
                value, valid = None, False
            metrics[name] = {'value': value, 'unit': definition['unit'], 'valid': valid}
            if not valid:
                metrics[name]['reason'] = row.get('failure_reason') or 'Missing scalar response'
        samples.append({'id': row['candidate_id'], 'values': row['values'], 'responses': metrics,
                        'usable': row.get('execution_status') == 'SUCCEEDED'})
    # Reuse the numerical routines without the old saved-campaign schema's
    # arbitrary 512-row/16-variable caps. This bridge validates ordinary numeric
    # rows above; the regression/Pareto/surrogate mathematics has one owner.
    cohort = sorted([s for s in samples if s['usable'] and all(r['valid'] for r in s['responses'].values())], key=lambda s: s['id'])
    ids = [s['id'] for s in cohort]
    var_defs = [dict(parameter_id=v['id'], unit=v['unit'], lower_bound=v['lower'], upper_bound=v['upper']) for v in variables]
    x = np.asarray([[s['values'][v['id']] for v in variables] for s in cohort], dtype=float).reshape(len(cohort), len(variables))
    y = np.asarray([[s['responses'][d['metric']]['value'] for d in definitions] for s in cohort], dtype=float).reshape(len(cohort), len(definitions))
    shuffled = np.random.default_rng(seed).permutation(len(cohort))
    cutoff = max(1, math.ceil(len(cohort) / 4))
    test, train = sorted(shuffled[:cutoff].tolist()), sorted(shuffled[cutoff:].tolist())
    result = {'statistics': [analysis._statistics(y[:, i], d) for i, d in enumerate(definitions)],
              'sensitivity': [analysis._sensitivity(x, y[:, i], var_defs, d, ids) for i, d in enumerate(definitions)],
              'surrogate': [analysis._surrogate(x, y[:, i], var_defs, d, ids, seed, train, test) for i, d in enumerate(definitions)],
              'pareto': analysis._pareto(y, definitions, ids),
              'exclusions': [{'id': s['id'], 'reason': 'ROW_UNUSABLE' if not s['usable'] else 'INVALID_RESPONSE'} for s in samples if s['id'] not in set(ids)],
              'qualification': 'NUMERICAL_SAMPLE_ANALYSIS_ONLY', 'decision': 'NOT_RELEASED',
              'limitations': analysis._LIMITATIONS[:]}
    result.update(candidate_count=len(samples), failure_count=sum(not row['usable'] for row in samples),
                  sampling=deepcopy(table.get('sampling')), variable_ranges=variables,
                  response_definitions=deepcopy(declarations))
    return result


def run_uq(evaluator_or_factory, variables, distributions, *, settings=None, count=128, seed=0,
           independence='INDEPENDENT_USER_DECLARED', source=None, thresholds=None, execution=None, record=None):
    """Declared independent input laws; optimization populations are never reused."""
    variables = _variables(variables)
    if independence != 'INDEPENDENT_USER_DECLARED' or not isinstance(source, dict) or source.get('origin') not in ('ASSUMED', 'MEASURED_REPORTED', 'PUBLISHED_REFERENCE', 'SYNTHETIC') or not source.get('reference'):
        raise ValueError("Declare independent marginals and their distribution source")
    if type(count) is not int or count < 2 or type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("UQ requires count >=2 and an unsigned seed")
    if set(distributions) != {v['id'] for v in variables}:
        raise ValueError("Declare one distribution for every variable")
    uniform = qmc.LatinHypercube(len(variables), rng=np.random.default_rng(seed)).random(count)
    points = np.empty_like(uniform)
    for index, v in enumerate(variables):
        law = distributions[v['id']]
        if law.get('unit', v['unit']) != v['unit']:
            raise ValueError("Distribution unit differs from variable unit")
        kind = law.get('distribution')
        if kind == 'uniform':
            low = _number(law.get('lower', v['lower']), 'uniform lower')
            high = _number(law.get('upper', v['upper']), 'uniform upper')
            if not v['lower'] <= low < high <= v['upper']:
                raise ValueError("Uniform support must lie within evaluation bounds")
            points[:, index] = low + (high - low) * uniform[:, index]
        elif kind in ('normal', 'truncnorm', 'lognormal'):
            mean = _number(law.get('mean'), 'distribution mean')
            std = _number(law.get('std'), 'distribution std')
            if std <= 0:
                raise ValueError("Distribution std must be positive")
            if kind == 'normal':
                points[:, index] = norm.ppf(uniform[:, index], loc=mean, scale=std)
            elif kind == 'truncnorm':
                points[:, index] = truncnorm.ppf(uniform[:, index], (v['lower'] - mean) / std, (v['upper'] - mean) / std, loc=mean, scale=std)
            else:
                if mean <= 0:
                    raise ValueError("Lognormal arithmetic mean must be positive")
                sigma = math.sqrt(math.log1p((std / mean) ** 2))
                points[:, index] = lognorm.ppf(uniform[:, index], sigma, scale=mean / math.exp(sigma ** 2 / 2))
            if np.any((points[:, index] < v['lower']) | (points[:, index] > v['upper'])):
                raise ValueError("Sampled distribution extends outside evaluation bounds; widen bounds or explicitly use truncnorm")
        else:
            raise ValueError("Supported distributions: uniform, normal, truncnorm, lognormal")
    candidates = [dict(zip([v['id'] for v in variables], point)) for point in points]
    table = run_doe(evaluator_or_factory, variables, settings=settings, candidates=candidates, execution=execution)
    table.update(kind='uq', sampling={'method': 'independent_lhs_inverse_cdf', 'seed': seed, 'count': count,
                                     'independence': independence, 'source': deepcopy(source), 'distributions': deepcopy(distributions)})
    statistics = []
    if thresholds is None:
        inferred = {}
        for row in table['candidates']:
            for name, response in row.get('responses', {}).items():
                if response.get('kind') == 'scalar':
                    inferred[name] = {'response': name, 'unit': response['unit']}
        definitions = list(inferred.values())
    else:
        definitions = list(thresholds)
    for definition in definitions:
        values, missing = [], 0
        for row in table['candidates']:
            try:
                values.append(_scalar(row, definition))
            except EvaluationFailed:
                missing += 1
        value = np.asarray(values)
        limit = _number(definition['limit'], 'threshold limit') if 'limit' in definition else None
        if definition.get('operator', '>') not in ('>', '>=', '<', '<='):
            raise ValueError("Unknown threshold operator")
        operation = {'>': np.greater, '>=': np.greater_equal, '<': np.less, '<=': np.less_equal}[definition.get('operator', '>')]
        statistics.append({'response': definition.get('response', definition.get('metric')), 'unit': definition['unit'],
                           'valid_count': len(values), 'failed_count': missing, 'failure_fraction': missing / count,
                           'mean': float(value.mean()) if len(value) else None,
                           'std': float(value.std(ddof=1)) if len(value) >= 2 else None,
                           'min': float(value.min()) if len(value) else None, 'max': float(value.max()) if len(value) else None,
                           'quantiles': dict(zip(['q05', 'q50', 'q95'], np.quantile(value, [.05, .5, .95]).tolist())) if len(value) else {},
                           'threshold': deepcopy(definition), 'exceedance_fraction_valid': float(operation(value, limit).mean()) if len(value) and limit is not None else None,
                           'limitations': ['Statistics condition on successful evaluations; failures may bias the estimated distribution.']})
    table['probability_statistics'] = statistics
    return _record(table, record)


class Surrogate:
    """SciPy RBF interpolation with a disjoint confirmation table."""
    def __init__(self, model, variables, response, validation, support):
        self.model, self.variables, self.response, self.validation, self.support = model, variables, response, validation, support

    def predict(self, candidates):
        names = [v['id'] for v in self.variables]
        x = np.asarray([[_number(row[name], name) for name in names] for row in candidates])
        low, high = np.asarray([v['lower'] for v in self.variables]), np.asarray([v['upper'] for v in self.variables])
        normalized = (x - low) / (high - low)
        predictions = self.model(normalized)
        return [{'candidate_id': f'P{i:06d}', 'values': dict(zip(names, row)), 'execution_status': 'PREDICTED',
                 'out_of_range': bool(np.any((row < self.support[0]) | (row > self.support[1]))),
                 'responses': {self.response['response']: {'kind': 'scalar', 'value': float(value), 'unit': self.response['unit'],
                                                         'component': self.response.get('component', ''), 'location': self.response.get('location', ''),
                                                         'reduction': 'surrogate prediction'}}}
                for i, (row, value) in enumerate(zip(x, predictions))]


def fit_surrogate(training, holdout, response, *, variables=None, options=None):
    """Fit SciPy RBF only on training rows, then report independent holdout errors."""
    variables = _variables(variables or training['variables'])
    response = dict(response)
    response['response'] = response.get('response', response.get('metric'))
    train, test = training['candidates'], holdout['candidates']
    if not train or not test:
        raise ValueError("Separate nonempty training and holdout tables are required")
    # Candidate identifiers are local to each table (independent DOE runs both
    # start at C000000). Physical parameter overlap below prevents reused data.
    names = [v['id'] for v in variables]
    train_x = np.asarray([[row['values'][name] for name in names] for row in train], dtype=float)
    test_x = np.asarray([[row['values'][name] for name in names] for row in test], dtype=float)
    if {tuple(row) for row in train_x} & {tuple(row) for row in test_x}:
        raise ValueError("Training and holdout parameter points overlap")
    low, high = np.asarray([v['lower'] for v in variables]), np.asarray([v['upper'] for v in variables])
    if not np.all(np.isfinite(train_x)) or not np.all(np.isfinite(test_x)) or np.any((train_x < low) | (train_x > high)):
        raise ValueError("Training coordinates must be finite and within declared bounds")
    support = train_x.min(axis=0), train_x.max(axis=0)
    train_y = np.asarray([_scalar(row, response) for row in train])
    test_y = np.asarray([_scalar(row, response) for row in test])
    opts = dict(options or {})
    if set(opts) - {'neighbors', 'smoothing', 'kernel', 'epsilon', 'degree'}:
        raise ValueError("Unknown SciPy RBF options")
    model = RBFInterpolator((train_x - low) / (high - low), train_y, **opts)
    predictions = model((test_x - low) / (high - low))
    error = predictions - test_y
    validation = {'method': 'scipy.interpolate.RBFInterpolator', 'options': opts,
                  'train_ids': [r['candidate_id'] for r in train], 'holdout_ids': [r['candidate_id'] for r in test],
                  'identity_scope': 'IDs are local to the separately supplied training and holdout tables',
                  'holdout_prediction': predictions.tolist(), 'mae': float(np.mean(abs(error))),
                  'rmse': float(np.sqrt(np.mean(error ** 2))), 'max_error': float(np.max(abs(error))),
                  'unit': response['unit'], 'range': deepcopy(variables),
                  'training_support_bounds': [support[0].tolist(), support[1].tolist()],
                  'holdout_out_of_range': np.any((test_x < support[0]) | (test_x > support[1]), axis=1).tolist(),
                  'limitations': ['Hyperparameters are supplied before holdout evaluation; predictions are not solver evaluations.']}
    return Surrogate(model, variables, response, validation, support)


def sample_sensitivity(variables, *, count=128, seed=0, second_order=False):
    """Optional SALib matched Sobol plan, distinct from an ordinary LHS table."""
    try:
        from SALib.sample.sobol import sample
    except ImportError as error:
        raise RuntimeError("Global sensitivity requires the optional SALib dependency") from error
    variables = _variables(variables)
    if any(v['transform'] != 'linear' for v in variables):
        raise ValueError("This Sobol interface currently uses independent uniform physical coordinates")
    if type(count) is not int or count < 2 or count & (count - 1):
        raise ValueError("Sobol base count must be a power of two >=2")
    problem = {'num_vars': len(variables), 'names': [v['id'] for v in variables], 'bounds': [[v['lower'], v['upper']] for v in variables]}
    matrix = sample(problem, count, calc_second_order=second_order, seed=seed)
    return {'variables': variables, 'sampling': {'method': 'SALib.sobol', 'problem': problem, 'base_count': count,
            'second_order': second_order, 'seed': seed}, 'candidates': [{'candidate_id': f'S{i:06d}', 'values': dict(zip(problem['names'], row))} for i, row in enumerate(matrix)]}


def analyze_sensitivity(plan, table, response):
    try:
        from SALib.analyze.sobol import analyze
    except ImportError as error:
        raise RuntimeError("Global sensitivity requires the optional SALib dependency") from error
    sampling = plan.get('sampling', {})
    if sampling.get('method') != 'SALib.sobol':
        raise ValueError("Sobol analysis requires its matched SALib sampling plan, never ordinary LHS")
    expected, rows = plan['candidates'], table['candidates']
    if len(expected) != len(rows) or any(a['candidate_id'] != b['candidate_id'] or a['values'] != b['values'] for a, b in zip(expected, rows)):
        raise ValueError("Response identities/order/values differ from the sensitivity sampling plan")
    y = np.asarray([_scalar(row, response) for row in rows])
    if not np.all(np.isfinite(y)) or np.ptp(y) == 0:
        raise ValueError("Sobol analysis requires complete finite nonconstant model outputs")
    result = analyze(sampling['problem'], y, calc_second_order=sampling['second_order'], seed=sampling['seed'])
    return {'method': 'SALib.sobol', 'sampling': deepcopy(sampling), 'response': deepcopy(response),
            'indices': {key: np.asarray(value).tolist() for key, value in result.items()},
            'candidate_ids': [row['candidate_id'] for row in rows]}


def epsilon_optimize(evaluator_or_factory, variables, objectives, *, threshold_grid, primary_index=0,
                     settings=None, constraints=None, seed=0, options=None, total_evaluation_budget=1000,
                     execution=None, record=None):
    """Epsilon child searches reuse the existing DE and Pareto numerical modules."""
    if not 0 <= primary_index < len(objectives) or len(objectives) < 2:
        raise ValueError("Select a primary objective among at least two objectives")
    secondary = [o for i, o in enumerate(objectives) if i != primary_index]
    if len(threshold_grid) != len(secondary) or any(not points for points in threshold_grid):
        raise ValueError("Declare threshold points for each secondary objective")
    opts = dict(options or {})
    maximum = opts.get('population_size', 12) * (opts.get('max_generations', 40) + 1)
    combinations = list(product(*threshold_grid))
    if type(total_evaluation_budget) is not int or total_evaluation_budget < len(combinations) * maximum:
        raise ValueError("Epsilon plan exceeds its declared total evaluation budget")
    all_rows, children = [], []
    execution_options = _execution(execution)
    remaining = execution_options.get('max_evaluations', total_evaluation_budget)
    stopped = None
    for index, limits in enumerate(combinations):
        if remaining <= 0:
            stopped = 'EVALUATION_BUDGET_EXHAUSTED'
            children.append({'child_id': f'E{index:04d}', 'thresholds': list(limits), 'termination_reason': stopped,
                             'evaluation_count': 0, 'execution_status': 'NOT_EVALUATED'})
            break
        epsilon = [dict(o, operator='<=' if o.get('direction', 'minimize') == 'minimize' else '>=', limit=_number(limit, 'epsilon limit')) for o, limit in zip(secondary, limits)]
        child = optimize(evaluator_or_factory, variables, objectives[primary_index], settings=settings,
                         constraints=list(constraints or []) + epsilon, seed=seed + index, options=opts,
                         execution=dict(execution_options, max_evaluations=remaining))
        for row in child['candidates']:
            row['candidate_id'] = f'E{index:04d}_{row["candidate_id"]}'
        all_rows.extend(child['candidates'])
        children.append({'child_id': f'E{index:04d}', 'thresholds': list(limits), 'termination_reason': child['termination_reason'],
                         'evaluation_count': len(child['candidates'])})
        remaining -= child['timing']['dispatched_evaluations_total']
        if child['execution_status'] in ('CANCELLED', 'REJECTED'):
            stopped = child['termination_reason']
            break
    table = {'kind': 'epsilon_optimization', 'variables': _variables(variables), 'candidates': all_rows, 'children': children,
             'sampling': {'method': 'epsilon_constraints', 'adaptive': True, 'total_evaluation_budget': total_evaluation_budget},
             'execution_status': 'CANCELLED' if stopped == 'USER_CANCELLED' else 'REJECTED' if stopped else 'SUCCEEDED',
             'termination_reason': stopped or 'CHILD_SEARCHES_COMPLETED'}
    # Existing componentwise nondominance is used; exclude infeasible child
    # rows before analysis, while retaining every actual row in the study.
    archive_table = dict(table, candidates=[row for row in all_rows if row.get('feasible')])
    table['pareto'] = analyze_candidates(archive_table, objectives)['pareto'] if len(archive_table['candidates']) >= 2 else {'nondominated_ids': [r['candidate_id'] for r in archive_table['candidates']]}
    return _record(table, record)


def export_batch(variables, candidates, directory, *, case_id, settings=None):
    """Export explicit candidate/case exchange identities; this performs no solve."""
    from .evaluation import save_evaluation
    from uuid import uuid4
    variables = _variables(variables)
    rows = _candidates(candidates, variables)
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("A file exchange requires an explicit case_id")
    exchange_id = 'X' + uuid4().hex
    manifest = {'kind': 'file_batch', 'case_id': case_id, 'exchange_id':exchange_id,
                'variables': variables, 'settings': deepcopy(settings or {}),
                'candidates': [dict(row, case_id=case_id, exchange_id=exchange_id, execution_status='NOT_EVALUATED', responses={}, failure_reason='Awaiting real external evaluation') for row in rows]}
    directory = Path(directory)
    save_evaluation(manifest, directory)
    return manifest


def import_batch(manifest, results):
    """Recover only actual matching results; omitted candidates remain unknown."""
    if manifest.get('kind') != 'file_batch':
        raise ValueError("Expected a file batch manifest")
    expected = {row['candidate_id']: row for row in manifest['candidates']}
    received = {}
    for result in results:
        identifier = result.get('candidate_id')
        if identifier not in expected or identifier in received or result.get('case_id') != manifest['case_id']:
            raise ValueError("External result has unknown/duplicate candidate or mismatched case identity")
        if manifest.get('exchange_id') and result.get('exchange_id') != manifest['exchange_id']:
            raise ValueError('External result has missing or stale exchange identity')
        if result.get('values') != expected[identifier]['values']:
            raise ValueError("External result parameter values differ from exported candidate")
        if result.get('execution_status') not in ('SUCCEEDED', 'FAILED', 'REJECTED', 'CANCELLED'):
            raise ValueError("Imported results must declare an actual execution status")
        from .evaluation import normalize_evaluation
        received[identifier] = normalize_evaluation(result)
    rows = []
    for identifier, original in expected.items():
        rows.append(dict(_row(identifier, original['values'], received[identifier]), case_id=manifest['case_id'], exchange_id=manifest.get('exchange_id')) if identifier in received else deepcopy(original))
    return dict(manifest, kind='imported_batch', candidates=rows,
                identity_assurance='EXCHANGE_CASE_VALUES' if manifest.get('exchange_id') else 'LEGACY_CASE_VALUES_ONLY',
                imported_count=len(received), missing_count=len(rows) - len(received))
