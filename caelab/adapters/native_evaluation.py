"""Explicit recorded evaluations of existing parameterized native adapters."""
from copy import deepcopy
from pathlib import Path
import uuid
from ..backends import get_backend
from ..contracts import CapabilityUnavailable
from ..evaluation import PreparedEvaluation, run
from ..model_parameters import bind


class NativeEvaluationFactory:
    """One owned native output per candidate, using the existing checked binding.

    This is file execution, not an in-memory material model or an implicit Study.
    Only inputs advertised by the native adapter can be changed.
    """
    def __init__(self, backend, output, response_selection=None):
        self.backend = backend
        self.output = str(Path(output).resolve())
        self.response_selection = deepcopy(response_selection)

    def prepare(self, settings, *, runtime=None):
        if runtime and set(runtime) - {'threads', 'memory_mb'}:
            raise ValueError('Native adapters use their documented operator runtime configuration')
        adapter = get_backend(self.backend)
        if self.backend == 'material.mfront.prepared':
            if 'output_root' in settings:
                raise ValueError('Prepared native output directories are controller-owned')
            return adapter.prepare({**deepcopy(settings),
                'output_root':str(Path(self.output)/('prepared-'+uuid.uuid4().hex))},runtime=runtime)
        if not all(callable(getattr(adapter, name, None)) for name in ('solve', 'describe_inputs', 'bind_inputs', 'describe_model')):
            raise CapabilityUnavailable(f'{self.backend}: native numerical studies require declared input binding')
        template = deepcopy(settings)
        adapter.describe_inputs(template)
        def candidate(values):
            bound = bind(adapter, template, values)
            result = run(adapter, bound, output=Path(self.output)/('candidate-'+uuid.uuid4().hex),
                         selection=self.response_selection)
            result['diagnostics']['evaluation_mode'] = 'FILE_BASED_NATIVE'
            result['diagnostics']['candidate_values'] = deepcopy(values)
            return result
        return PreparedEvaluation(candidate, template)
