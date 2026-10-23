"""Execute and retain research domain stages through the existing evaluator.

The caller supplies a service-owned output folder. This module does not create
another queue, alter runtime configuration or reconstruct a field numerically.
"""
from copy import deepcopy
from pathlib import Path
import uuid

from . import evaluation
from .execution_control import ExecutionCleanupFailed
from .storage import check_id


def run_domain(workbench, model, output):
    backend, settings = model['backend'], deepcopy(model['settings'])
    if backend.startswith('pde.'):
        from .pde_document import validate_draft, support_details
    elif backend == 'material.felupe':
        from .material_document import diagnostics
        errors = diagnostics(model)
        if errors:
            raise ValueError(errors[0]['message'])
        validate_draft = lambda _: None
        support_details = lambda _: {'declaration': {}, 'limitations': []}
    else:
        from .simulation_document import validate_draft, support_details
    validate_draft(model)
    description = support_details(model)
    settings = workbench._settings(backend, settings)
    output = Path(output)
    if output.exists():
        raise ValueError('An actual stage requires a fresh owned output directory')
    calculation = output / 'calculation'
    try:
        result = evaluation.run(backend, settings, output=calculation)
    except ExecutionCleanupFailed:
        raise
    except Exception as error:
        output.mkdir(parents=True, exist_ok=True)
        result = {'execution_status': 'FAILED', 'responses': {}, 'checks': [],
                  'backend': backend, 'settings': settings,
                  'diagnostics': {'reason': str(error), 'error_type': type(error).__name__}}
    result['research_document_result'] = True
    result.setdefault('diagnostics', {}).update(declaration=description.get('declaration', {}),
        limitations=description.get('limitations', []), decision='NOT_RELEASED')
    if result.get('native_result'):
        # Native channel readers resolve inside the retained result, never the
        # global native job directory or a user-supplied path.
        result['native_result']['directory'] = 'calculation/' + result['native_result']['directory']
    outcome = result['diagnostics'].get('native_outcome', {})
    if backend.startswith('pde.') and outcome.get('solver_status') == 'COMPLETED':
        from .pde_results import collect_fields
        try:
            result['diagnostics']['native_fields'] = collect_fields(calculation, outcome, settings)
        except (ValueError, OSError, KeyError, TypeError) as error:
            result['native_execution_status'] = result['execution_status']
            result['execution_status'] = 'FAILED'
            result['diagnostics']['field_delivery_error'] = str(error)
    try:
        publish_fields(workbench, result, output)
    except (ValueError, OSError, KeyError, TypeError) as error:
        result['post_registration'] = {'status': 'FAILED', 'message': str(error)}
    result['artifacts'] = [{'path': path.relative_to(output).as_posix(), 'sha256': evaluation.file_hash(path)}
                           for path in sorted(output.rglob('*')) if path.is_file() and not path.is_symlink()]
    if any(path.is_symlink() for path in output.rglob('*')):
        raise ValueError('Native result contains an unsupported symbolic link; original output remains')
    evaluation.save_evaluation(result, output, existing=True)
    return result


def publish_fields(workbench, result, output):
    """Register only existing native fields; retain exact units/basis/clock."""
    from .native_inputs import register_native_input
    from .pde_results import write_post_sets
    output = Path(output)
    fields = result.get('diagnostics', {}).get('native_fields', [])
    sets = write_post_sets(fields, output / 'post') if fields else []
    # This bounded new physical-field path reuses the P1 VTU writer and overrides
    # its mathematical-PDE labels with the adapter's explicit physical metadata.
    for name, response in result.get('responses', {}).items():
        if response.get('kind') != 'field' or response.get('association') not in ('POINTS', 'CELLS') or 'mesh_sha256' not in response:
            continue
        from .physical_fields import write_field
        sets.append(write_field(name, response, output / ('post-' + check_id(name))))
    if not sets:
        return
    result['post_inputs'] = []
    for index, entry in enumerate(sets):
        source = Path(entry['path'])
        receipt = register_native_input(workbench.root, output, source, 'D' + uuid.uuid4().hex,
            root_id='research-result', relative=source.relative_to(output).as_posix(),
            limit=workbench.config.get('local_input_max_bytes', 2 * 1024**3),
            native_metadata=entry['native_metadata'])
        result['post_inputs'].append({'id': receipt['id'], 'format': receipt['format'],
            'sha256': receipt['sha256'], 'study_index': entry.get('study_index', index),
            'response': entry.get('response')})
    result['post_input'] = deepcopy(result['post_inputs'][-1])
