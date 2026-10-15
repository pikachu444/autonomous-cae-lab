"""Reusable ordered evaluations over exact saved domain documents.

This is a document and a sequential adapter composition, not another job engine.
JobManager owns the parent job; each inline stage uses the existing evaluation
entry point and the same cooperative cancellation token. Stage attempts and raw
files are retained below that job even when a later stage fails.
"""
from copy import deepcopy
from pathlib import Path
import math
import shutil
import uuid

from .material_document import MaterialDocuments
from .storage import canonical_hash, check_id, load_json, save_json, utc_now
from .evaluation import PreparedEvaluation, file_hash, read_result, save_evaluation
from .execution_control import check_cancelled, ExecutionCancelled, ExecutionCleanupFailed

DOMAIN_KINDS = {'material': 'M', 'pde': 'Q', 'simulation': 'V'}
REFERENCE_KEYS = {'document_id', 'kind', 'saved_revision', 'input_revision', 'input_sha256'}


def document_reference(document):
    if not document.get('saved_revision') or document.get('dirty'):
        raise ValueError('Save the exact domain inputs before selecting them as an evaluation stage')
    return {'document_id': document['id'], 'kind': document['kind'],
            'saved_revision': document['saved_revision'], 'input_revision': document['input_revision'],
            'input_sha256': canonical_hash(document['draft'])}


def check_reference(reference, kinds=None):
    kinds = kinds or DOMAIN_KINDS
    if not isinstance(reference, dict) or set(reference) != REFERENCE_KEYS or reference['kind'] not in kinds:
        raise ValueError('Choose an exact saved domain document revision')
    for key in ('document_id', 'saved_revision', 'input_revision'):
        check_id(reference[key])
    if not reference['document_id'].startswith(kinds[reference['kind']]):
        raise ValueError('Document identity and domain kind differ')
    digest = reference['input_sha256']
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Domain input requires its exact content hash')
    return reference


def verify_reference(reference, document):
    if (document.get('id') != reference['document_id'] or document.get('kind') != reference['kind']
            or document.get('input_revision') != reference['input_revision']
            or canonical_hash(document['draft']) != reference['input_sha256']):
        raise ValueError('The saved domain input differs from the selected reference')
    return deepcopy(document['draft'])


def default_draft():
    return {'stages': [], 'transfers': [], 'bindings': [], 'responses': [],
            'iteration': {'enabled': False, 'maximum': 20, 'checks': []}, 'reuse': None}


def _number(value, label, *, minimum=0):
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum:
        raise ValueError(label + ' must be a finite number >= ' + str(minimum))
    return value


def definition_hash(draft):
    return canonical_hash({key: value for key, value in draft.items() if key != 'reuse'})


def validate_draft(draft):
    if not isinstance(draft, dict) or set(draft) != set(default_draft()):
        raise ValueError('Evaluation requires stages, transfers, bindings, responses, iteration and explicit reuse')
    if not isinstance(draft['stages'], list) or not 1 <= len(draft['stages']) <= 32:
        raise ValueError('Add one to 32 ordered domain stages')
    ids = []
    for stage in draft['stages']:
        if not isinstance(stage, dict) or set(stage) != {'id', 'name', 'source'}:
            raise ValueError('Each stage requires a stable ID, name and exact source revision')
        check_id(stage['id'])
        if stage['id'] in ids or not isinstance(stage['name'], str) or not stage['name'].strip():
            raise ValueError('Stage IDs must be distinct and names nonempty')
        ids.append(stage['id'])
        check_reference(stage['source'])
    for key in ('transfers', 'bindings', 'responses'):
        if not isinstance(draft[key], list) or len(draft[key]) > 128:
            raise ValueError(key + ' requires a bounded editable list')
    transfers, destinations = set(), set()
    for row in draft['transfers']:
        from .evaluation_temperature_mapping import validate_row
        validate_row(row, ids)
        check_id(row['id'])
        if row['id'] in transfers or (row['to_stage'], row['input']) in destinations:
            raise ValueError('Declare each transfer ID and destination port only once')
        transfers.add(row['id']); destinations.add((row['to_stage'], row['input']))
        if row['from_stage'] not in ids or row['to_stage'] not in ids:
            raise ValueError('Transfer refers to a missing stage')
        if type(row['lag']) is not int or row['lag'] not in (0, 1):
            raise ValueError('Field transfer requires lag 0 or explicitly lagged feedback 1')
        if row['lag'] == 0 and ids.index(row['from_stage']) >= ids.index(row['to_stage']):
            raise ValueError('An immediate input must be produced by an earlier stage')
        for key in ('input', 'output'):
            if not isinstance(row[key], str) or not row[key].strip():
                raise ValueError('Choose the exact advertised field port')
    from .evaluation_shared_inputs import validate_binding, targets
    bindings, binding_targets = set(), set()
    for row in draft['bindings']:
        validate_binding(row, ids)
        if row['id'] in bindings:
            raise ValueError('Binding ID must be distinct and refer to a stage')
        bindings.add(row['id'])
        for target in targets(row):
            key = target['stage'], target['input_id']
            if key in binding_targets:
                raise ValueError('An actual stage input cannot be owned by two bindings')
            binding_targets.add(key)
    outputs = set()
    for row in draft['responses']:
        if not isinstance(row, dict) or set(row) != {'id', 'stage', 'response', 'unit'}:
            raise ValueError('Output requires research ID, stage response and declared unit')
        check_id(row['id'])
        if row['id'] in outputs or row['stage'] not in ids or not all(isinstance(row[k], str) and row[k].strip() for k in ('response', 'unit')):
            raise ValueError('Outputs require distinct IDs, existing stages and explicit response/unit')
        outputs.add(row['id'])
    iteration = draft['iteration']
    if (not isinstance(iteration, dict) or set(iteration) != {'enabled', 'maximum', 'checks'}
            or type(iteration['enabled']) is not bool or type(iteration['maximum']) is not int
            or not 1 <= iteration['maximum'] <= 1000 or not isinstance(iteration['checks'], list)):
        raise ValueError('Iteration requires enabled, maximum 1..1000 and explicit convergence checks')
    if any(row['lag'] for row in draft['transfers']) and not iteration['enabled']:
        raise ValueError('Lagged feedback requires explicit iteration')
    if iteration['enabled'] and (not any(row['lag'] for row in draft['transfers']) or not iteration['checks']):
        raise ValueError('Iteration requires supported feedback and a declared physical residual')
    for row in iteration['checks']:
        if not isinstance(row, dict) or set(row) != {'stage', 'response', 'unit', 'absolute', 'relative', 'scale'}:
            raise ValueError('Convergence check requires stage/response/unit, absolute and relative tolerances, scale')
        if row['stage'] not in ids:
            raise ValueError('Convergence stage is missing')
        for key in ('absolute', 'relative', 'scale'):
            _number(row[key], 'Convergence ' + key)
        if row['absolute'] == row['relative'] == 0 or row['scale'] <= 0:
            raise ValueError('Convergence requires a positive tolerance and physical scale')
    if draft['reuse'] is not None:
        from .research_operations import validate_result_reference
        reuse = draft['reuse']
        if not isinstance(reuse, dict) or set(reuse) != {'source', 'stages'}:
            raise ValueError('Reuse requires an exact retained evaluation and a stage prefix')
        validate_result_reference(reuse['source'])
        if not isinstance(reuse['stages'], list) or reuse['stages'] != ids[:len(reuse['stages'])]:
            raise ValueError('Only an unchanged successful stage prefix may be reused')
        if iteration['enabled'] and reuse['stages']:
            raise ValueError('Restart this iteration from its initial state; partial loop-state reuse is unsupported')
    return deepcopy(draft)


def diagnostics(draft):
    try:
        validate_draft(draft)
    except (ValueError, KeyError, TypeError, OverflowError) as error:
        return [{'severity': 'error', 'path': 'definition', 'message': str(error), 'blocks_evaluation': True}]
    return []


def input_descriptors(draft):
    from .backends import get_backend
    backend, settings = draft['backend'], draft['settings']
    if backend == 'material.felupe':
        return [{'id': key, 'label': key, 'unit': '1' if key == 'nu' else settings['stress_unit'], 'value': value}
                for key, value in settings['parameters'].items()]
    adapter = get_backend(backend)
    return deepcopy(adapter.describe_inputs(settings)) if callable(getattr(adapter, 'describe_inputs', None)) else []


def bind_values(draft, values):
    if not values:
        return deepcopy(draft)
    from .backends import get_backend
    result = deepcopy(draft)
    if draft['backend'] == 'material.felupe':
        from .adapters.felupe_material import validate_settings
        if set(values) - set(result['settings']['parameters']):
            raise ValueError('Unknown Material coefficient')
        result['settings']['parameters'].update(deepcopy(values))
        validate_settings(result['settings'])
    else:
        adapter = get_backend(draft['backend'])
        if not callable(getattr(adapter, 'bind_inputs', None)):
            raise ValueError('This domain has no declared numerical input bindings')
        result['settings'] = adapter.bind_inputs(deepcopy(result['settings']), deepcopy(values))
    return result


def compile_definition(draft, snapshots):
    from .backends import get_backend
    draft = validate_draft(draft)
    compiled, descriptors = {}, []
    for stage in draft['stages']:
        model = verify_reference(stage['source'], snapshots[stage['id']])
        owner_check = {'material': ('material_document', 'diagnostics'), 'pde': ('pde_document', 'diagnostics'),
                       'simulation': ('simulation_document', 'diagnostics')}[stage['source']['kind']]
        from importlib import import_module
        errors = getattr(import_module('caelab.' + owner_check[0]), owner_check[1])(model)
        if errors:
            raise ValueError(stage['id'] + ': ' + errors[0]['message'])
        adapter = get_backend(model['backend'])
        ports = adapter.describe_ports(model['settings']) if callable(getattr(adapter, 'describe_ports', None)) else {'inputs': {}, 'outputs': {}}
        if draft['iteration']['enabled'] and not getattr(adapter, 'restart_safe', False):
            raise ValueError(stage['id'] + ': this adapter has no stateless iteration restart contract')
        compiled[stage['id']] = {'model': model, 'ports': ports}
    for row in draft['transfers']:
        if row['mapping'] == 'p1_temperature':
            from .evaluation_temperature_mapping import compile_transfer
            compile_transfer(row, compiled)
            continue
        source = compiled[row['from_stage']]['ports']['outputs'].get(row['output'])
        target = compiled[row['to_stage']]['ports']['inputs'].get(row['input'])
        if not source or not target or target.get('transfer') != row['mapping']:
            raise ValueError(row['id'] + ': choose an actually advertised output/input transfer')
        for key in ('kind', 'unit', 'quantity', 'association', 'component', 'location', 'measure',
                    'frame', 'coordinate_units', 'coordinate_frame'):
            if source.get(key) != target.get(key):
                raise ValueError(row['id'] + ': incompatible ' + key + '; no inferred conversion/mapping')
        if row['lag'] and target.get('required'):
            raise ValueError('The initial iteration needs an explicitly optional/seeded feedback port')
    for stage_id, item in compiled.items():
        for name, port in item['ports']['inputs'].items():
            if port.get('required') and item['model']['settings'].get(name) is None and not any(
                    row['to_stage'] == stage_id and row['input'] == name for row in draft['transfers']):
                raise ValueError(stage_id + ': required input port ' + name + ' is not connected')
    from .evaluation_shared_inputs import compile_bindings
    descriptors = compile_bindings(draft['bindings'], {k:v['model'] for k,v in compiled.items()},
                                   input_descriptors, bind_values)
    result = {'definition': draft, 'stages': compiled, 'inputs': descriptors, 'definition_sha256': definition_hash(draft)}
    from .linear_adjoint_contract import describe_definition
    result['derivative_capability'] = describe_definition(result)
    return result


class EvaluationDocuments(MaterialDocuments):
    kind, prefix = 'evaluation', 'E'
    update_operation, evaluate_operation = 'evaluation.update', 'evaluation.run'
    evaluation_operation = 'evaluation.coupled'
    default_draft, diagnostics = staticmethod(default_draft), staticmethod(diagnostics)

    def __init__(self, root, session_id, submit, manager, *, resolve_revision):
        super().__init__(root, session_id, submit, manager)
        self.resolve_revision = resolve_revision

    def snapshots(self, draft, document=None):
        retained = (document or {}).get('_stage_snapshots', {})
        result = {}
        for stage in draft['stages']:
            reference = stage['source']
            check_reference(reference)
            snapshot = retained.get(canonical_hash(reference))
            if snapshot is None:
                snapshot = self.resolve_revision(reference['document_id'], reference['saved_revision'])
            verify_reference(reference, snapshot)
            # Keep only immutable input identity, not another owner's mutable Undo/jobs.
            result[stage['id']] = {key: deepcopy(snapshot[key]) for key in ('id', 'kind', 'input_revision', 'draft')}
        return result

    def inspect_definition(self, identifier):
        document = self.read(identifier)
        stages, errors = [], []
        # A disconnected required port must remain selectable in the editor.
        # Describe each admitted source independently of whole-graph validity.
        from .backends import get_backend
        for stage in document['draft'].get('stages', []):
            try:
                model = verify_reference(stage['source'], self.snapshots({'stages': [stage]}, self._documents[identifier])[stage['id']])
                adapter = get_backend(model['backend'])
                ports = adapter.describe_ports(model['settings']) if callable(getattr(adapter, 'describe_ports', None)) else {'inputs': {}, 'outputs': {}}
                stages.append({'id': stage['id'], 'backend': model['backend'], 'ports': ports,
                               'inputs': input_descriptors(model), 'clock': deepcopy(model['settings'].get('time'))})
            except (ValueError, KeyError, TypeError, OSError, ImportError) as error:
                errors.append({'path': 'stages.' + str(stage.get('id', '?')), 'message': str(error), 'blocks_evaluation': True})
        try:
            compiled = compile_definition(document['draft'], self.snapshots(document['draft'], self._documents[identifier]))
            return {'document_id': identifier, 'definition_sha256': compiled['definition_sha256'],
                    'stages': stages,
                    'inputs': compiled['inputs'], 'derivative_capability': compiled['derivative_capability'], 'diagnostics': [], 'runtime': 'NOT_PROBED'}
        except (ValueError, KeyError, TypeError, OSError, ImportError) as error:
            return {'document_id': identifier, 'stages': stages, 'inputs': [], 'runtime': 'NOT_PROBED',
                    'diagnostics': errors + [{'path': 'definition', 'message': str(error), 'blocks_evaluation': True}]}

    def prepare_job_arguments(self, draft, document):
        snapshots = self.snapshots(draft, document)
        compile_definition(draft, snapshots)
        return {'definition': deepcopy(draft), 'snapshots': snapshots,
                'definition_source': {'document_id': document['id'], 'session_id': self.session_id,
                    'generation': document['generation'], 'input_revision': document['input_revision'],
                    'input_sha256': canonical_hash(draft)}}

    def _public(self, document):
        from .portable_project_execution import public_execution
        return public_execution(self, super()._public(document))

    def _retain_inputs(self, saved, folder):
        from .portable_project_execution import retain_execution_inputs
        retain_execution_inputs(self, saved, folder)
        retained = deepcopy(saved.get('_stage_snapshots', {}))
        for stage in saved['draft'].get('stages', []):
            try:
                snapshots = self.snapshots({'stages': [stage]}, saved)
                retained[canonical_hash(stage['source'])] = snapshots[stage['id']]
            except (ValueError, TypeError, KeyError, OSError):
                # Invalid/incomplete drafts remain saveable; running compiles all refs.
                continue
        saved['_stage_snapshots'] = retained
        save_json(folder / 'stage_inputs.json', retained)

    def from_reference(self, reference):
        check_reference(reference, {'evaluation': 'E'})
        saved = self._verify_revision(reference['document_id'], reference['saved_revision'])
        draft = verify_reference(reference, saved)
        return compile_definition(draft, self.snapshots(draft, saved))


def _copy_files(source, destination):
    source, destination = Path(source), Path(destination)
    for path in source.rglob('*'):
        if path.is_symlink():
            raise ValueError('Stage output contains an unsupported symbolic link')
        if path.is_file():
            target = destination / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            expected = file_hash(path)
            shutil.copyfile(path, target)
            if file_hash(path) != expected or file_hash(target) != expected:
                raise ValueError('Stage files changed during retention')


def execute(compiled, output, run_stage, *, values=None, reuse_result=None, reuse_folder=None,
            reserve=None, derivative_request=None, cost_role='primal'):
    """Run ordered existing evaluators inline; stage receipts stay under one job."""
    from .backends import get_backend
    import numpy as np
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    definition = deepcopy(compiled['definition'])
    stage_models = {key: deepcopy(item['model']) for key, item in compiled['stages'].items()}
    values = deepcopy(values or {})
    save_json(output / 'input.json', {'definition': definition, 'definition_sha256': compiled['definition_sha256'],
                                    'models': stage_models, 'values': values})
    result = {'kind': 'coupled_evaluation', 'execution_status': 'FAILED', 'responses': {}, 'checks': [],
              'definition_sha256': compiled['definition_sha256'], 'values': values,
              'stages': [], 'iterations': [], 'transfers': [],
              'stage_names': {row['id']: row['name'] for row in definition['stages']}, 'derivative_attempts': [], 'gradients': None,
              'diagnostics': {'decision': 'NOT_RELEASED', 'convergence_status': 'NOT_STARTED'}}
    def progress(phase, **extra):
        save_json(output / 'progress.json', {**deepcopy(result), 'phase': phase, **extra})
    previous, current = {}, {}
    reuse = definition.get('reuse')
    maximum = definition['iteration']['maximum'] if definition['iteration']['enabled'] else 1
    failed_stage = None
    try:
        from .evaluation_shared_inputs import assign
        stage_models, result['input_bindings'] = assign(definition['bindings'], stage_models, values,
                                                       input_descriptors, bind_values)
        result['initial_state_sha256'] = canonical_hash(stage_models)
        save_json(output / 'input.json', {'definition': definition, 'definition_sha256': compiled['definition_sha256'],
                                        'models': stage_models, 'values': values})
        if reuse and reuse['stages']:
            if (reuse_result is None or reuse_folder is None or reuse_result.get('definition_sha256') != compiled['definition_sha256']
                    or reuse_result.get('values', {}) != values):
                raise ValueError('Reuse input/definition differs from the selected actual run')
        for iteration in range(maximum):
            current = {}
            for stage in definition['stages']:
                check_cancelled()
                stage_id = stage['id']
                folder = output / 'stages' / (f'i{iteration:04d}-' + stage_id)
                attempt_id = 'A' + uuid.uuid4().hex
                record = {'stage_id': stage_id, 'iteration': iteration, 'attempt_id': attempt_id,
                          'backend': stage_models[stage_id]['backend'], 'state': 'RUNNING',
                          'dispatched': False,
                          'result_directory': folder.relative_to(output).as_posix(), 'started_utc': utc_now()}
                result['stages'].append(record)
                failed_stage = stage_id
                progress('STAGE_RUNNING', active_attempt=attempt_id)
                model = deepcopy(stage_models[stage_id])
                for transfer in [row for row in definition['transfers'] if row['to_stage'] == stage_id]:
                    source_set = previous if transfer['lag'] else current
                    if transfer['lag'] and iteration == 0:
                        continue  # Adapter explicitly declares an optional, domain-owned initial seed.
                    if transfer['mapping'] == 'p1_temperature':
                        from .evaluation_temperature_mapping import bind_transfer
                        model['settings'] = bind_transfer(transfer, model, source_set, result, iteration, output, definition['stages'])
                        progress('TRANSFER_VALIDATED', active_attempt=attempt_id)
                        continue
                    upstream = source_set[transfer['from_stage']]
                    if upstream.get('execution_status') != 'SUCCEEDED':
                        raise ValueError('Failed stage cannot supply a field')
                    response = deepcopy(upstream['responses'][transfer['output']])
                    model['settings'] = get_backend(model['backend']).bind_port(model['settings'], transfer['input'], response)
                    result['transfers'].append({'id': transfer['id'], 'iteration': iteration,
                        'from_stage': transfer['from_stage'], 'to_stage': stage_id, 'input': transfer['input'],
                        'mapping': transfer['mapping'], 'source_response_sha256': canonical_hash(response),
                        'source_iteration': iteration - transfer['lag'], 'status': 'VALIDATED',
                        'unit': response['unit'], 'time': response.get('time'),
                        'mesh_sha256': response.get('mesh_sha256'), 'association': response.get('association')})
                check_cancelled()  # Mapping may finish after cancellation; never dispatch its receiver.
                if iteration == 0 and reuse and stage_id in reuse['stages']:
                    original = next((row for row in reuse_result['stages'] if row['stage_id'] == stage_id and row['iteration'] == 0), None)
                    if not original or original['state'] != 'SUCCEEDED' or original['input_sha256'] != canonical_hash(model):
                        raise ValueError('Reuse requires this exact successful stage input')
                    directory = Path(reuse_folder) / original['result_directory']
                    if not directory.resolve().is_relative_to(Path(reuse_folder).resolve()):
                        raise ValueError('Stage result reference escapes its retained run')
                    read_result(directory, verify='all')
                    _copy_files(directory, folder)
                    stage_result = read_result(folder, verify='all')
                    record.update(reused_from=deepcopy(reuse['source']), original_attempt_id=original['attempt_id'])
                else:
                    if reserve:
                        reserve(1, role=cost_role)
                    check_cancelled()
                    record['dispatched'] = True
                    record['input_sha256'] = canonical_hash(model)
                    progress('STAGE_RUNNING', active_attempt=attempt_id)
                    stage_result = run_stage(model, folder)
                    if not (folder / 'result.json').exists():
                        save_evaluation(stage_result, folder, existing=folder.exists())
                    # Consume the existing writer's detached JSON/array values,
                    # not a live ndarray result in progress/hash publication.
                    # Reading the completed stage never invokes its evaluator.
                    stage_result = read_result(folder, verify='all')
                record.update(state=stage_result.get('execution_status', 'FAILED'), finished_utc=utc_now(),
                              input_sha256=canonical_hash(model), result_sha256=canonical_hash(stage_result))
                current[stage_id] = stage_result
                progress('STAGE_FINISHED', active_attempt=attempt_id)
                check_cancelled()  # Keep a late result, but do not start another stage after cancellation.
                if record['state'] != 'SUCCEEDED':
                    result['diagnostics'].update(reason='Stage did not succeed', failed_stage=stage_id)
                    raise ValueError(stage_id + ': ' + record['state'])
            failed_stage = None
            convergence = []
            for check in definition['iteration']['checks']:
                now = current[check['stage']]['responses'][check['response']]
                if now['unit'] != check['unit']:
                    raise ValueError('Convergence response unit differs from its declared tolerance')
                row = {**check, 'iteration': iteration, 'norm': 'L_INFINITY', 'observed': None, 'passed': False}
                if check['stage'] in previous:
                    old = previous[check['stage']]['responses'][check['response']]
                    metadata = ('unit', 'kind', 'component', 'location', 'association', 'frame', 'measure',
                                'mesh_sha256', 'time', 'time_units', 'time_origin')
                    if any(old.get(k) != now.get(k) for k in metadata):
                        raise ValueError('Iteration response position/basis/time/meaning changed')
                    a, b = np.asarray(old['value'], dtype=float), np.asarray(now['value'], dtype=float)
                    if a.shape != b.shape or not a.size or not np.isfinite(a).all() or not np.isfinite(b).all():
                        raise ValueError('Iteration requires complete finite same-shape responses')
                    norm = float(np.max(np.abs(b - a)))
                    limit = check['absolute'] + check['relative'] * max(float(np.max(np.abs(b))), check['scale'])
                    row.update(observed=norm, limit=limit, passed=norm <= limit)
                convergence.append(row)
            result['iterations'].append({'iteration': iteration, 'checks': convergence})
            if not definition['iteration']['enabled'] or all(row['passed'] for row in convergence):
                result.update(execution_status='SUCCEEDED')
                result['diagnostics']['convergence_status'] = 'CONVERGED' if definition['iteration']['enabled'] else 'ONE_WAY_COMPLETED'
                for export in definition['responses']:
                    response = current[export['stage']]['responses'][export['response']]
                    if response['unit'] != export['unit']:
                        raise ValueError('Exported response unit differs from the actual stage result')
                    result['responses'][export['id']] = deepcopy(response)
                break
            previous = current
            progress('ITERATING')
        else:
            result['diagnostics'].update(convergence_status='NOT_CONVERGED', reason='Maximum iterations reached')
        if result['execution_status'] == 'SUCCEEDED' and derivative_request is not None:
            from .evaluation_adjoint import compute
            compute(compiled, stage_models, result, output, derivative_request, reserve, progress)
    except ExecutionCleanupFailed:
        progress('CLEANUP_UNCONFIRMED', failed_stage=failed_stage)
        raise
    except ExecutionCancelled as error:
        result.update(execution_status='CANCELLED', responses={}, gradients=None)
        result['diagnostics'].update(reason=str(error), failed_stage=failed_stage, convergence_status='CANCELLED')
        if result['stages'] and result['stages'][-1]['state'] == 'RUNNING':
            result['stages'][-1].update(state='CANCELLED', finished_utc=utc_now())
    except Exception as error:
        result.update(execution_status='FAILED', responses={}, gradients=None)
        result['diagnostics'].update(reason=str(error), error_type=type(error).__name__, failed_stage=failed_stage)
        if getattr(error, 'budget_exhausted', False):
            result['diagnostics']['stop_reason'] = 'EVALUATION_BUDGET_EXHAUSTED'
        if result['stages'] and result['stages'][-1]['state'] == 'RUNNING':
            result['stages'][-1].update(state='FAILED', error=str(error), finished_utc=utc_now())
    result['stage_execution_count'] = sum(row['dispatched'] for row in result['stages'])
    result['adjoint_execution_count'] = sum(row['dispatched'] for row in result['derivative_attempts'])
    result['cost_unit'] = 'stage_or_adjoint_dispatch'
    progress('FINISHED')
    result['artifacts'] = [{'path': p.relative_to(output).as_posix(), 'sha256': file_hash(p)}
                           for p in sorted(output.rglob('*')) if p.is_file()]
    save_evaluation(result, output, existing=True)
    return result


class DefinitionFactory:
    """Existing numerical engines call this prepared evaluator, with frozen inputs."""
    @property
    def uses_stage_budget(self):
        return self._stage_costs

    def __init__(self, compiled, output, run_stage):
        self.compiled, self.output, self.run_stage = deepcopy(compiled), Path(output), run_stage
        self.completed = []
        self.derivative_request = None
        self.cost_role = 'primal'
        # New fan-out and explicit adjoint use actual stage/transpose costs.
        # Legacy single-target Plans retain their saved complete-evaluation budget.
        self._stage_costs = any('targets' in b for b in self.compiled['definition']['bindings'])

    def configure_adjoint(self, variables, responses):
        from .linear_adjoint_contract import configure
        self.derivative_request = configure(self.compiled, variables, responses)
        self._stage_costs = True
        return deepcopy(self.derivative_request)

    def primal_only(self):
        result = DefinitionFactory(self.compiled, self.output, self.run_stage)
        result.cost_role = 'verification_primal'
        result._stage_costs = self._stage_costs
        return result

    def prepare(self, settings=None, *, runtime=None):
        if runtime and set(runtime) - {'threads', 'memory_mb'}:
            raise ValueError('Unsupported composite evaluator runtime options')
        control = {'budget': None}
        admission=deepcopy(self.derivative_request)
        cost_role=self.cost_role
        def evaluate(values):
            folder = self.output / ('candidate-' + uuid.uuid4().hex)
            result = execute(self.compiled, folder, self.run_stage, values=values,
                reserve=control['budget'].reserve if control['budget'] is not None else None,
                derivative_request=admission, cost_role=cost_role)
            # The numerical row receives an exact link to already-saved bytes.
            # It is not stored inside itself and never causes another evaluation.
            reference = {'relative': folder.relative_to(self.output.parent).as_posix(),
                'result_sha256': file_hash(folder / 'result.json'),
                'execution_status': result['execution_status'],
                'stage_execution_count': result['stage_execution_count'],
                'adjoint_execution_count': result['adjoint_execution_count'],
                'definition_sha256': result['definition_sha256']}
            self.completed.append({**deepcopy(reference), 'values': deepcopy(values)})
            return {**result, 'evaluation_refs': [reference]}
        prepared = PreparedEvaluation(evaluate, deepcopy(settings or {}))
        prepared.set_budget = lambda budget: control.update(budget=budget)
        return prepared
