"""Compatible PDE operation over the shared declared-model experiment runner."""

from .declared_model import run_declared_model


def run_pde(lab, *, study_id: str, experiment_id: str, backend: str,
            settings: dict, hypothesis_id: str | None) -> dict:
    adapter = lab.pde_adapters.get(backend)
    # A shared describe_model method may already exist on a legacy adapter.
    # Only an explicit PDE opt-in may change its historical revision identity.
    description = (getattr(adapter, "pde_model_declaration", False) is True and
                   callable(getattr(adapter, "describe_model", None)))
    return run_declared_model(lab, study_id=study_id, experiment_id=experiment_id,
                              backend=backend, settings=settings, hypothesis_id=hypothesis_id,
                              adapters=lab.pde_adapters, namespace="pde", output_directory="pde",
                              description=description)


def evaluate_document(workbench, job_id, backend, settings):
    """Run an independent frozen draft through the existing direct model runner.

    The declared-model and direct APIs share evaluation.execute_model. A GUI
    document does not create a fictitious CAD/Study parent to use that runner.
    The job result retains its own native files so document Save/Open is enough
    to read it, without the original runtime or global native job directory.
    """
    from copy import deepcopy
    from pathlib import Path
    import shutil
    import uuid
    from . import evaluation
    from .execution_control import ExecutionCleanupFailed
    from .native_inputs import register_native_input
    from .pde_document import validate_draft, support_details
    from .pde_results import collect_fields, write_post_sets
    from .storage import check_id

    check_id(job_id)
    draft = {'backend': backend, 'settings': deepcopy(settings)}
    validate_draft(draft)
    description = support_details(draft)
    native = workbench.root / 'native' / job_id
    try:
        result = evaluation.run(backend, settings, output=native)
    except ExecutionCleanupFailed:
        raise
    except Exception as error:
        # Preserve actual input/logs and the reason even when a worker is absent.
        result = {'execution_status': 'FAILED', 'backend': backend,
                  'settings': deepcopy(settings), 'responses': {}, 'checks': [],
                  'diagnostics': {'reason': str(error), 'error_type': type(error).__name__}}
    result['pde_document_result'] = True
    diagnostics = result.setdefault('diagnostics', {})
    diagnostics.update(declaration=description['declaration'], decision='NOT_RELEASED')
    outcome = diagnostics.get('native_outcome', {})
    if outcome.get('solver_status') == 'COMPLETED':
        try:
            diagnostics['native_fields'] = collect_fields(native, outcome, settings)
        except (OSError, ValueError, KeyError, TypeError) as error:
            result.update(execution_status='FAILED', native_execution_status=result['execution_status'])
            diagnostics['field_delivery_error'] = str(error)
    destination = workbench.root / 'results' / job_id
    destination.mkdir(parents=True, exist_ok=False)
    # Only copy files created in the fixed, service-owned output directory.
    assets = []
    if (native / 'pde').is_dir():
        for source in sorted((native / 'pde').rglob('*')):
            if source.is_symlink():
                raise ValueError('PDE output contains an unsupported symbolic link')
            if not source.is_file():
                continue
            relative = source.relative_to(native)
            target = destination / relative
            digest = evaluation.file_hash(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if evaluation.file_hash(source) != digest or evaluation.file_hash(target) != digest:
                raise ValueError('PDE output changed while retaining the result')
            assets.append({'path': relative.as_posix(), 'sha256': digest})
    result['artifacts'] = assets
    fields = diagnostics.get('native_fields', [])
    if fields:
        try:
            sets = write_post_sets(fields, destination / 'post')
            result['post_inputs'] = []
            for item in sets:
                source = Path(item['path'])
                receipt = register_native_input(workbench.root, destination, source,
                    'D' + uuid.uuid4().hex, root_id='job:' + job_id,
                    relative=source.relative_to(destination).as_posix(),
                    limit=workbench.config.get('local_input_max_bytes', 2 * 1024**3),
                    native_metadata=item['native_metadata'])
                result['post_inputs'].append({'id': receipt['id'], 'format': receipt['format'],
                    'sha256': receipt['sha256'], 'study_index': item['study_index']})
            if result['post_inputs']:
                result['post_input'] = deepcopy(result['post_inputs'][-1])
        except (OSError, ValueError, KeyError, TypeError) as error:
            # A Post delivery failure never loses calculated fields or reruns a solver.
            result['post_registration'] = {'status': 'FAILED', 'message': str(error)}
    evaluation.save_evaluation(result, destination, existing=True)
    return result
