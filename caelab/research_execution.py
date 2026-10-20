"""Execute and retain research domain stages through the existing evaluator.

The caller supplies a service-owned output folder. This module does not create
another queue, alter runtime configuration or reconstruct a field numerically.
"""
from copy import deepcopy
from pathlib import Path
import shutil
import uuid

from . import evaluation
from .execution_control import ExecutionCleanupFailed
from .storage import check_id


def retain_native_artifacts(result, source, destination):
    """Keep declared native files in the same saved result as its responses."""
    source, destination = Path(source).resolve(), Path(destination)
    records = result.get('artifacts', [])
    if not records:
        return
    files = []
    for record in records:
        relative = record.get('relative', record.get('path'))
        if (not isinstance(relative, str) or not relative or Path(relative).anchor
                or '..' in Path(relative).parts):
            raise ValueError('Native artifact needs a local relative path')
        original = source / relative
        if (any(path.is_symlink() for path in (original, *original.parents) if path != source and source in path.parents)
                or not original.resolve().is_relative_to(source)):
            raise ValueError('Native artifact is outside its execution directory')
        if evaluation.file_hash(original) != record['sha256']:
            raise ValueError('Native artifact changed before retention')
        files.append((original, relative, record['sha256']))
    destination.mkdir(parents=True, exist_ok=False)
    retained = []
    for original, relative, digest in files:
        target = destination / 'calculation' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        if evaluation.file_hash(target) != digest or evaluation.file_hash(original) != digest:
            raise ValueError('Native artifact changed while retaining the result')
        retained.append({'path': target.relative_to(destination).as_posix(), 'sha256': digest})
    if result.get('native_result'):
        directory = result['native_result']['directory']
        result['native_result']['directory'] = 'calculation' if directory == source.name else 'calculation/' + directory
    result['artifacts'] = retained
    evaluation.save_evaluation(result, destination, existing=True)


def run_domain(workbench, model, output, *, runtime=None):
    backend, settings = model['backend'], deepcopy(model['settings'])
    if backend.startswith('pde.'):
        from .pde_document import validate_draft, support_details
    elif backend in ('material.felupe', 'material.law_native'):
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
        execution_backend=backend
        if backend=='damage.rainflow':
            from .fatigue import resolved_adapter
            execution_backend=resolved_adapter(workbench,settings)
        options = {} if runtime is None else {'runtime': runtime}
        result = evaluation.run(execution_backend, settings, output=calculation, **options)
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
    # Frozen native adapters retain their established single-artifact contract.
    legacy = ([result['post_artifact']] if result.get('post_artifact') else [])
    legacy += result.get('additional_post_artifacts', [])
    for entry in legacy:
        from .workbench import contained
        source = contained(output / 'calculation', entry['relative'])
        if source.stat().st_size != entry['bytes'] or evaluation.file_hash(source) != entry['sha256']:
            raise ValueError('Native Post artifact changed before registration')
        sets.append({'path': source, 'native_metadata': entry.get('native_metadata')})
    # Adapter-produced mixed native FE fields use the same immutable registrar.
    # No arbitrary caller path; only a contained, hashed artifact of this run.
    for entry in result.get('post_artifacts', []):
        relative = entry.get('relative')
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise ValueError('Native Post artifact must be relative to its calculation')
        source = (output / 'calculation' / relative).resolve(strict=True)
        if not source.is_relative_to((output / 'calculation').resolve()) or source.is_symlink():
            raise ValueError('Native Post artifact escapes this calculation')
        if evaluation.file_hash(source) != entry.get('sha256'):
            raise ValueError('Native Post artifact changed before registration')
        from xml.etree import ElementTree as ET
        dependencies=entry.get('dependencies')
        named=[node.get('file') for node in ET.parse(source).findall('.//DataSet')]
        if not isinstance(dependencies,dict) or set(named)!=set(dependencies):
            raise ValueError('Native Post dependency manifest differs')
        for name,digest in dependencies.items():
            if Path(name).name!=name or not name.endswith('.vtu'):
                raise ValueError('Native Post dependency must be a sibling VTU')
            child=source.parent/name
            if child.is_symlink() or evaluation.file_hash(child)!=digest:
                raise ValueError('Native Post field changed before registration')
        sets.append({'path': source, 'native_metadata': entry['native_metadata'],
                     'response': entry.get('response'),'dependencies':dependencies})
    if not sets:
        return
    result['post_inputs'] = []
    for index, entry in enumerate(sets):
        source = Path(entry['path'])
        receipt = register_native_input(workbench.root, output, source, 'D' + uuid.uuid4().hex,
            root_id='research-result', relative=source.relative_to(output).as_posix(),
            limit=workbench.config.get('local_input_max_bytes', 2 * 1024**3),
            native_metadata=entry['native_metadata'])
        for name,digest in entry.get('dependencies',{}).items():
            if evaluation.file_hash(source.parent/name)!=digest:
                raise ValueError('Native Post field changed during registration')
        result['post_inputs'].append({'id': receipt['id'], 'format': receipt['format'],
            'sha256': receipt['sha256'], 'study_index': entry.get('study_index', index),
            'response': entry.get('response')})
    result['post_input'] = deepcopy(result['post_inputs'][-1])
