"""Explicit recorded evaluations of existing parameterized native adapters."""
from copy import deepcopy
from pathlib import Path
import uuid
from ..backends import get_backend
from ..contracts import CapabilityUnavailable
from ..evaluation import PreparedEvaluation, run, save_evaluation, file_hash, read_result
from ..model_parameters import bind
from ..storage import canonical_hash, save_json, load_json


class NativeEvaluationFactory:
    """One owned native output per candidate, using the existing checked binding.

    This is file execution, not an in-memory material model or an implicit Study.
    Only inputs advertised by the native adapter can be changed.
    """
    def __init__(self, backend, output, response_selection=None, *, retained_root=None):
        self.backend = backend
        self.output = str(Path(output).resolve())
        self.response_selection = deepcopy(response_selection)
        self.retained_root = str(Path(retained_root).resolve()) if retained_root is not None else None
        if self.retained_root and not Path(self.output).is_relative_to(self.retained_root):
            raise ValueError('Native candidate output must be inside its retained result')
        self.completed = []

    def retained_attempts(self):
        """Collect completed worker-owned receipts after an engine failure.

        A process pool has a separate factory instance, so its in-memory list
        is not the controller's journal. Read only already-published exact
        candidate inputs/results; never execute or assign algorithm ranks here.
        """
        if not self.retained_root:
            return deepcopy(self.completed)
        records = []
        for path in sorted(Path(self.output).glob('candidate-*/candidate_input.json')):
            folder = path.parent.resolve()
            if path.parent.is_symlink() or not folder.is_relative_to(self.retained_root):
                raise ValueError('Native candidate receipt is outside its retained result')
            request = load_json(path)
            saved = read_result(folder, selection={'responses': [], 'include_settings': True})
            if (request.get('backend') != self.backend or saved.get('backend') != self.backend or
                    canonical_hash(saved.get('settings')) != request.get('settings_sha256')):
                raise ValueError('Native candidate receipt differs from its exact evaluated input')
            records.append({'relative': folder.relative_to(self.retained_root).as_posix(),
                'result_sha256': file_hash(folder / 'result.json'), 'backend': self.backend,
                'execution_status': saved['execution_status'], 'input_sha256': request['settings_sha256'],
                'selected_execution_status': request['selected_execution_status'], 'values': deepcopy(request['values'])})
        return records

    def prepare(self, settings, *, runtime=None):
        if runtime and set(runtime) - {'threads', 'memory_mb'}:
            raise ValueError('Native adapters use their documented operator runtime configuration')
        adapter = get_backend(self.backend)
        if self.backend == 'material.mfront.prepared':
            if 'output_root' in settings:
                raise ValueError('Prepared native output directories are controller-owned')
            return adapter.prepare({**deepcopy(settings),
                'output_root':str(Path(self.output)/('prepared-'+uuid.uuid4().hex))},runtime=runtime)
        if (not any(callable(getattr(adapter, name, None)) for name in ('solve', 'run')) or
                not all(callable(getattr(adapter, name, None)) for name in ('describe_inputs', 'bind_inputs', 'describe_model'))):
            raise CapabilityUnavailable(f'{self.backend}: native numerical studies require declared input binding')
        template = deepcopy(settings)
        adapter.describe_inputs(template)
        def candidate(values):
            folder = Path(self.output)/('candidate-'+uuid.uuid4().hex)
            # Reserve the attempt identity before binding, including rejected
            # assignments. run() still owns creation of its result directory.
            folder.parent.mkdir(parents=True, exist_ok=True)
            attempt = folder.with_suffix('.request.json')
            request = {'attempt_id': folder.name, 'backend': self.backend,
                       'template_sha256': canonical_hash(template), 'values': deepcopy(values),
                       'state': 'BINDING', 'phase': 'binding'}
            save_json(attempt, request)
            bound, phase = deepcopy(template), 'binding'
            try:
                from ..execution_control import check_cancelled
                check_cancelled()
                bound = bind(adapter, template, values)
                phase = 'evaluation'
                save_json(attempt, {**request, 'state': 'RUNNING', 'phase': phase,
                                   'bound_sha256': canonical_hash(bound)})
                result = run(adapter, bound, output=folder, selection=self.response_selection)
            except Exception as error:
                from ..execution_control import ExecutionCleanupFailed, ExecutionCancelled
                if isinstance(error, ExecutionCleanupFailed):
                    raise
                # run already retains the actual native files. A failed
                # selector must not erase a completed native calculation or
                # quietly rerun it to obtain a different response.
                result = {'execution_status': 'CANCELLED' if isinstance(error, ExecutionCancelled) else 'FAILED',
                          'responses': {}, 'checks': [],
                          'backend': self.backend, 'settings': deepcopy(bound),
                          'diagnostics': {'phase': phase, 'reason': str(error), 'error_type': type(error).__name__}}
                if not (folder / 'result.json').exists():
                    save_evaluation(result, folder, existing=folder.exists())
            save_json(attempt, {**request, 'state': result['execution_status'], 'phase': phase,
                               'bound_sha256': canonical_hash(bound)})
            result.setdefault('diagnostics', {})['evaluation_mode'] = 'FILE_BASED_NATIVE'
            result['diagnostics']['candidate_values'] = deepcopy(values)
            if self.retained_root:
                saved = read_result(folder, selection={'responses': [], 'metadata_only': True})
                request = {'backend': self.backend, 'values': deepcopy(values),
                           'settings_sha256': canonical_hash(bound),
                           'response_selection': deepcopy(self.response_selection),
                           'selected_execution_status': result['execution_status']}
                save_json(folder / 'candidate_input.json', request)
                reference = {'relative': folder.relative_to(self.retained_root).as_posix(),
                    'result_sha256': file_hash(folder / 'result.json'), 'backend': self.backend,
                    'execution_status': saved['execution_status'], 'input_sha256': canonical_hash(bound),
                    'selected_execution_status': result['execution_status']}
                self.completed.append({**deepcopy(reference), 'values': deepcopy(values)})
                result['evaluation_refs'] = [reference]
            return result
        return PreparedEvaluation(candidate, template)
