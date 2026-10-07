"""Synchronous, independent evaluation using the same native adapter boundary as Lab."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import threading
from .contracts import CapabilityUnavailable
from .storage import save_json, load_json, utc_now


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def normalize_evaluation(value):
    if not isinstance(value, dict) or 'responses' not in value:
        raise ValueError('An evaluator must return execution_status and named responses with units')
    result = deepcopy(value)
    if result.get('execution_status') not in {'SUCCEEDED', 'FAILED', 'REJECTED', 'CANCELLED'}:
        raise ValueError('Invalid evaluation execution_status')
    if not isinstance(result['responses'], dict):
        raise ValueError('Responses must be a mapping')
    import numpy as np
    for name, response in result['responses'].items():
        if not isinstance(name, str) or not name or not isinstance(response, dict):
            raise ValueError('Each response needs a name and metadata')
        if not isinstance(response.get('unit'), str) or not response['unit']:
            raise ValueError(f'{name}: an explicit unit is required (use 1 for dimensionless values)')
        if response.get('kind') not in {'scalar', 'series', 'field', 'event'}:
            raise ValueError(f'{name}: invalid response kind')
        if 'value' in response and response['value'] is not None:
            array = np.asarray(response['value'])
            if array.dtype.kind not in 'iuf' or not np.isfinite(array).all():
                raise ValueError(f'{name}: response values must be finite numeric data')
            if response['kind'] == 'scalar' and array.ndim != 0:
                raise ValueError(f'{name}: a scalar response must have one scalar value')
        elif response.get('kind') != 'event' and 'data_ref' not in response:
            raise ValueError(f'{name}: missing response data')
        for axis in response.get('axes', []):
            if not axis.get('name') or not axis.get('unit'):
                raise ValueError(f'{name}: axes require names and units')
            if 'values' in axis:
                coordinates = np.asarray(axis['values'], dtype=float)
                if coordinates.ndim != 1 or not np.isfinite(coordinates).all():
                    raise ValueError(f'{name}: invalid axis')
                if response['kind'] == 'series' and len(coordinates) != len(response.get('value', [])):
                    raise ValueError(f'{name}: axis length differs from response')
        response.setdefault('component', 'scalar')
        response.setdefault('location', 'model')
        response.setdefault('reduction', 'none')
    result.setdefault('checks', [])
    result.setdefault('diagnostics', {})
    return result


class PreparedEvaluation:
    """A prepared resource belongs to one caller at a time; never share state silently."""
    def __init__(self, evaluator, settings, *, close=None, batch=None):
        self._evaluate = evaluator
        self.settings = deepcopy(settings)
        self._close = close
        self._closed = False
        self._busy = threading.Lock()
        self._batch = batch
        if batch is not None:
            self.evaluate_batch = self._evaluate_batch

    def _evaluate_batch(self, candidates):
        if self._closed or not self._busy.acquire(blocking=False):
            raise RuntimeError('Prepared evaluation is closed or in use')
        try:
            from .execution_control import check_cancelled
            check_cancelled()
            values = list(candidates)
            results = list(self._batch(deepcopy(values)))
            if len(results) != len(values):
                raise ValueError('Batch result count differs from candidate count')
            return [normalize_evaluation(result) for result in results]
        finally:
            self._busy.release()

    def evaluate(self, values=None):
        if self._closed:
            raise RuntimeError('Prepared evaluation is closed')
        if not self._busy.acquire(blocking=False):
            raise RuntimeError('Prepared evaluations cannot be shared concurrently; prepare one per worker')
        try:
            from .execution_control import check_cancelled
            check_cancelled()
            return normalize_evaluation(self._evaluate(deepcopy(values or {})))
        finally:
            self._busy.release()

    def close(self):
        if not self._closed:
            if self._busy.locked():
                raise RuntimeError('Cannot close an active prepared evaluation')
            if self._close:
                self._close()
            self._closed = True

    def __enter__(self):
        if self._closed:
            raise RuntimeError('Prepared evaluation is closed')
        return self

    def __exit__(self, *exc):
        self.close()


def prepare(backend, settings=None, *, runtime=None):
    from .backends import get_backend
    settings = deepcopy(settings or {})
    adapter = get_backend(backend)
    if callable(getattr(adapter, 'prepare', None)):
        resource = adapter.prepare(settings, runtime=runtime)
        if isinstance(resource, PreparedEvaluation):
            return resource
        return PreparedEvaluation(resource.evaluate, settings, close=getattr(resource, 'close', None),
                                  batch=getattr(resource, 'evaluate_batch', None))
    if callable(adapter):
        if runtime and set(runtime)-{'threads','memory_mb'}:
            raise ValueError('Runtime configuration must be handled by a registered adapter')
        return PreparedEvaluation(lambda values: adapter(values, deepcopy(settings)), settings)
    raise CapabilityUnavailable(f'{backend}: prepared evaluation is unsupported; use run with an explicit output')


def evaluate(backend, settings=None, *, values=None, runtime=None):
    with prepare(backend, settings, runtime=runtime) as prepared:
        return prepared.evaluate(values)


def execute_model(adapter, output, settings):
    """The single file-based native call used by both direct run and recorded Lab."""
    from .outcomes import validate_outcome
    outcome = adapter.solve(Path(output), deepcopy(settings))
    validate_outcome(outcome)
    return outcome


def _outcome_evaluation(outcome, *, backend=None, output=None):
    responses = {}
    for name, metric in outcome.get('metrics', {}).items():
        if metric.get('valid'):
            responses[name] = {'kind': 'scalar' if isinstance(metric['value'], (int, float)) else 'field',
                               'value': metric['value'], 'unit': metric['unit'],
                               'component': metric.get('component', name),
                               'location': metric.get('location', 'native_model'),
                               'reduction': metric.get('reduction', 'backend_defined')}
    solver_status = outcome.get('solver_status')
    status = ('CANCELLED' if solver_status == 'CANCELLED' else 'FAILED' if solver_status == 'FAILED_EXECUTION'
              else 'SUCCEEDED' if outcome.get('status') == 'COMPLETED' else 'REJECTED')
    result = {'execution_status': status, 'responses': responses, 'checks': outcome.get('checks', []),
              'diagnostics': {'native_outcome': outcome, 'decision': 'NOT_RELEASED'}}
    if backend and output is not None and solver_status == 'COMPLETED':
        from .adapters.native_responses import catalog_native_responses
        result['native_channels'] = catalog_native_responses(backend, outcome, output)
        result['native_result'] = {'backend':backend, 'directory':Path(output).name}
    return result


def save_evaluation(result, output, *, existing=False):
    """JSON metadata plus individual array files; no pickle or native solver needed to read."""
    import numpy as np
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=existing)
    if (folder / 'result.json').exists():
        raise FileExistsError('A result already exists; choose a new output')
    arrays, shared = [], {}
    def pack(value):
        array = None
        if isinstance(value, np.ndarray):
            array = value
        elif isinstance(value, list) and value and isinstance(value[0], (int, float, list)):
            try:
                candidate = np.asarray(value)
                if candidate.dtype.kind in 'biuf':
                    array = candidate
            except (TypeError, ValueError):
                pass
        if array is not None:
            if array.dtype.kind not in 'biuf':
                raise ValueError('Only numeric arrays can be persisted')
            fingerprint = (array.dtype.str,array.shape,hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest())
            if fingerprint in shared:
                return {'data_ref': shared[fingerprint]}
            relative = f'arrays/a{len(arrays):06d}.npy'
            target = folder / relative
            target.parent.mkdir(exist_ok=True)
            with target.open('xb') as stream:
                np.save(stream, array, allow_pickle=False)
            arrays.append({'path': relative, 'sha256': file_hash(target), 'shape': list(array.shape)})
            shared[fingerprint] = arrays[-1]
            return {'data_ref': arrays[-1]}
        if isinstance(value, dict):
            return {key: pack(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [pack(item) for item in value]
        if isinstance(value, np.generic):
            return value.item()
        return value
    packed = pack(result)
    packed['format'] = 'caelab.evaluation/1'
    packed['created_utc'] = utc_now()
    save_json(folder / 'result.json', packed)
    save_json(folder / 'result.sha256.json', {'sha256': file_hash(folder / 'result.json')})
    return packed


def run(backend, settings, *, output, runtime=None, parent=None, selection=None):
    from .backends import get_backend
    from .execution_control import ExecutionCancelled, ExecutionCleanupFailed
    adapter = get_backend(backend)
    folder = Path(output).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    try:
        if callable(getattr(adapter, 'run', None)):
            result = adapter.run(deepcopy(settings), output=folder, runtime=runtime)
        elif callable(getattr(adapter, 'prepare', None)) or callable(adapter):
            result = evaluate(adapter, settings, runtime=runtime)
        elif callable(getattr(adapter, 'solve', None)):
            if runtime:
                raise CapabilityUnavailable('This native adapter uses its documented environment configuration; runtime overrides unsupported')
            native_folder = folder / ('pde' if str(getattr(adapter, 'backend', '')).startswith('pde.') else 'simulation')
            if parent is None:
                outcome = execute_model(adapter, native_folder, settings)
            else:
                parent_path = Path(parent)
                parent_result = read_result(parent_path)
                outcome = adapter.solve(parent_result, parent_path if parent_path.is_dir() else parent_path.parent,
                                        native_folder, deepcopy(settings))
                from .outcomes import validate_outcome
                validate_outcome(outcome)
            result = _outcome_evaluation(outcome, backend=getattr(adapter,'backend',backend), output=native_folder)
        else:
            raise CapabilityUnavailable(f'{backend}: no file execution or prepared capability')
        result = normalize_evaluation(result)
    except ExecutionCleanupFailed:
        raise
    except ExecutionCancelled as error:
        result = {'execution_status': 'CANCELLED', 'responses': {}, 'checks': [],
                  'diagnostics': {'reason': str(error)}}
    except Exception as error:
        save_json(folder / 'failure.json', {'type': type(error).__name__, 'message': str(error)})
        raise
    result['backend'] = backend if isinstance(backend, str) else getattr(adapter, 'backend', 'trusted.python')
    result['settings'] = deepcopy(settings)
    save_evaluation(result, folder, existing=True)
    if selection is not None:
        return read_result(folder, selection=selection)
    return result


def read_result(path, *, verify='selected', selection=None):
    """Read saved bytes without importing an adapter or inspecting current solver versions."""
    if verify not in {'selected', 'all', 'none'}:
        raise ValueError('verify must be selected, all or none')
    path = Path(path).resolve()
    path = path / 'result.json' if path.is_dir() else path
    root = path.parent
    result = load_json(path)
    receipt = root / 'result.sha256.json'
    if verify != 'none' and receipt.exists() and file_hash(path) != load_json(receipt)['sha256']:
        raise ValueError('Saved result metadata hash differs')
    def verify_refs(value):
        if isinstance(value, dict):
            if set(value) == {'data_ref'}:
                ref = value['data_ref']
                target = (root / ref['path']).resolve()
                if not target.is_relative_to(root) or not target.is_file() or file_hash(target) != ref['sha256']:
                    raise ValueError('Saved response array hash differs or escapes result directory')
            else:
                for item in value.values():
                    verify_refs(item)
        elif isinstance(value, list):
            for item in value:
                verify_refs(item)
    if verify == 'all':
        verify_refs(result)
    def array_value(value):
        if isinstance(value, dict) and set(value) == {'data_ref'}:
            ref = value['data_ref']
            target = (root / ref['path']).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                raise ValueError('Result array is missing or outside its result directory')
            if verify != 'none' and file_hash(target) != ref['sha256']:
                raise ValueError('Saved response array hash differs')
            import numpy as np
            return np.load(target, allow_pickle=False, mmap_mode='r')
        return value
    def unpack(value):
        if isinstance(value, dict) and set(value) == {'data_ref'}:
            return array_value(value).tolist()
        if isinstance(value, dict):
            return {key: unpack(item) for key, item in value.items()}
        if isinstance(value, list):
            return [unpack(item) for item in value]
        return value
    if selection is not None:
        names = selection.get('responses') if isinstance(selection, dict) else selection
        if names is not None:
            if not isinstance(names,(list,tuple)) or not all(isinstance(name,str) for name in names):
                raise ValueError('Response selection must be a list of names')
            native = [name for name in names if name not in result.get('responses',{})]
            if native:
                # The saved outcome itself can contain packed numeric arrays.
                # Restore and verify them before the reader compares identities.
                outcome = unpack(result.get('diagnostics',{}).get('native_outcome',{}))
                _select_native(result,root,native,outcome)
            result['responses'] = {name: result['responses'][name] for name in names}
    if verify == 'all':
        for record in result.get('artifacts', []):
            artifact = (root / record['path']).resolve()
            if not artifact.is_relative_to(root) or file_hash(artifact) != record['sha256']:
                raise ValueError('Saved native artifact hash differs')
    if isinstance(selection,dict) and 'native_channels' in result:
        # Node IDs/coordinates form the selector catalog, not response fields.
        # Clients need these descriptors to select a retained native location.
        result['native_channels'] = unpack(result['native_channels'])
    if isinstance(selection,dict) and selection.get('metadata_only'):
        return result
    if isinstance(selection, dict):
        import numpy as np
        for name, response in list(result.get('responses', {}).items()):
            if any(key in selection and response.get(key) != selection[key] for key in ('component', 'location')):
                del result['responses'][name]
                continue
            if response.get('kind') != 'series':
                continue
            values = np.asarray(array_value(response['value']))
            selected = np.arange(len(values))
            if 'rows' in selection:
                start, stop = selection['rows']
                selected = selected[slice(start, stop)]
            if 'time_range' in selection:
                axis = next((a for a in response.get('axes', []) if a['name'] == 'time'), None)
                if axis is None:
                    raise ValueError('Selected response has no time axis')
                lower, upper = selection['time_range']
                coordinates = np.asarray(array_value(axis['values']))
                selected = selected[(coordinates[selected] >= lower) & (coordinates[selected] <= upper)]
            response['value'] = values[selected].tolist()
            for axis in response.get('axes', []):
                axis['values'] = np.asarray(array_value(axis['values']))[selected].tolist()
    if isinstance(selection, dict):
        # A response selection must not hydrate unrelated, potentially huge
        # diagnostics or saved native fields into an interactive response.
        # Their hashed references remain available for a separate full read.
        result['responses'] = unpack(result.get('responses', {}))
    else:
        result = unpack(result)
    return result


def _select_native(result, root, names, outcome):
    """Resolve only named native channels from this direct run's own directory."""
    native=result.get('native_result',{})
    directory=native.get('directory')
    catalog=result.get('native_channels',{})
    if not directory or not isinstance(directory,str):
        raise ValueError(f'Unknown response selection; available: {list(result.get("responses",{}))}')
    output=(root/directory).resolve()
    if not output.is_relative_to(root) or not output.is_dir():
        raise ValueError('Native result directory is unavailable or outside this result')
    from .adapters.native_responses import read_native_response
    for name in names:
        group=name.split('@',1)[0]
        if group not in catalog:
            raise ValueError(f'Unknown native channel {name!r}; available: {list(catalog)}')
        response=read_native_response(native['backend'],outcome,output,name)
        if response['source']['sha256']!=catalog[group]['source']['sha256']:
            raise ValueError('Native channel source hash differs from the saved result')
        result['responses'][name]=response
