"""Explicit pure candidate binding to saved Simulation/Evaluation owners.

Evaluation adoption prepares independent saved domain branches, then edits only
its original Evaluation owner. All work uses existing document locks, command
receipts and revision publication; no calculation or inference is performed.
"""
from copy import deepcopy

from .backends import get_backend
from . import variable_binding, variable_domains
from .evaluation_definition import (bind_values, check_reference, compile_definition,
    document_reference, input_descriptors, verify_reference)
from .pde_candidate import _KINDS, _finite, _normalized_variables
from .storage import canonical_hash, check_id, load_json, save_json


def _owner(wb, kind):
    return {'simulation': wb.simulation_documents, 'evaluation': wb.evaluation_documents,
            'material': wb.material_documents, 'pde': wb.pde_documents}[kind]


def _run(wb, plan_id, job_id):
    plan = wb.numerical_documents.read(check_id(plan_id))
    run = next((row for row in plan.get('runs', []) if row['job_id'] == check_id(job_id)), None)
    if run is None:
        raise ValueError('The selected run does not belong to this Numerical Plan')
    draft = run.get('draft')
    if not isinstance(draft, dict) or draft.get('mode') != 'request':
        raise ValueError('Domain adoption requires an actual submitted Request Plan')
    if run.get('input_sha256') != canonical_hash(draft):
        raise ValueError('The frozen submitted Plan input changed')
    source = draft.get('model_source') or draft.get('source')
    if isinstance(source, dict) and source.get('kind') == 'study':
        raise ValueError('Study evidence does not declare an original domain adoption target; bind an explicit Simulation/Evaluation source')
    check_reference(source, {'simulation': 'V', 'evaluation': 'E', 'material': 'M'})
    result = wb.numerical_documents.result(plan_id, job_id)
    return plan, run, result, source


def _candidate(run, result, candidate_id):
    request = run['draft'].get('request')
    if not isinstance(request, dict) or request.get('operation') not in _KINDS:
        raise ValueError('Domain candidates require doe, fit, optimize, uq or epsilon')
    operation = request['operation']
    inputs = request.get('inputs')
    if not isinstance(inputs, dict) or result.get('kind') != _KINDS[operation]:
        raise ValueError('The retained result kind differs from the submitted operation')
    variables = _normalized_variables(inputs.get('variables'), 'Submitted Plan')
    if variables != _normalized_variables(result.get('variables'), 'Retained result'):
        raise ValueError('Retained variable IDs, units or bounds differ from the submitted Plan')
    if not isinstance(candidate_id, str) or not candidate_id:
        raise ValueError('Select an exact retained candidate identity')
    rows = result.get('candidates')
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('The retained result requires actual candidate rows')
    matches = [row for row in rows if row.get('candidate_id') == candidate_id]
    if len(matches) != 1:
        raise ValueError('The selected candidate must occur exactly once in this retained result')
    row = matches[0]
    diagnostics = row.get('diagnostics', {})
    if (not isinstance(diagnostics, dict) or row.get('execution_status') != 'SUCCEEDED'
            or row.get('prediction_status') or diagnostics.get('evaluation_mode') == 'PREDICTED'):
        raise ValueError('Only an actually evaluated successful candidate can be adopted')
    if operation in {'fit', 'optimize', 'epsilon'}:
        _finite(row.get('objective'), 'Search objective')
    values = variable_binding.verify_candidate(result, variables, row, raw_declarations=inputs['variables'])
    return request, variables, deepcopy(values)


def _admitted(variables, descriptors):
    return variable_binding.admit_domains(variables, descriptors)


def _changes(model, bound, values, *, stage=None):
    before = {row['id']: row for row in input_descriptors(model)}
    after = {row['id']: row for row in input_descriptors(bound)}
    changes = []
    for name, value in values.items():
        if name not in before or name not in after or after[name].get('unit') != before[name].get('unit'):
            raise ValueError('Binding changed the advertised input identity or unit: ' + name)
        if not variable_binding.admits_value(after[name], value) or after[name]['value'] != value:
            raise ValueError('Domain binding did not apply the advertised scalar assignment: ' + name)
        if before[name]['value'] != after[name]['value']:
            path = ['inputs', name] if stage is None else ['stages', stage, 'inputs', name]
            changes.append({'path': path, 'before': deepcopy(before[name]['value']),
                            'after': deepcopy(after[name]['value']), 'unit': before[name]['unit'],
                            **({'stage': stage} if stage is not None else {})})
    return changes


def _prepare(wb, plan_id, job_id, candidate_id):
    _, run, result, source = _run(wb, plan_id, job_id)
    request, variables, values = _candidate(run, result, candidate_id)
    owner = _owner(wb, source['kind'])
    original = owner._verify_revision(source['document_id'], source['saved_revision'])
    model = verify_reference(source, original)
    if original.get('saved_revision') != source['saved_revision']:
        raise ValueError('The original saved revision differs from the Plan source')
    inputs, changes, branches = request['inputs'], [], []
    if source['kind'] in {'simulation', 'material'}:
        if inputs.get('backend') != model['backend']:
            raise ValueError('Candidate backend differs from the original Simulation')
        if (request['operation'] != 'fit' or 'settings' in inputs) and canonical_hash(inputs.get('settings')) != canonical_hash(model['settings']):
            raise ValueError('Submitted fixed settings differ from the saved Simulation template')
        if request['operation'] == 'fit':
            experiments = inputs.get('experiments')
            if (not isinstance(experiments, list) or not experiments
                    or any(not isinstance(row, dict)
                           or canonical_hash(row.get('settings')) != canonical_hash(model['settings'])
                           for row in experiments)):
                raise ValueError('Every fit experiment must use the exact saved Simulation settings')
        adapter = get_backend(model['backend'])
        if not callable(getattr(adapter, 'bind_inputs', None)) or not callable(getattr(adapter, 'describe_inputs', None)):
            raise ValueError('This Simulation has no advertised scalar input binding')
        _admitted(variables, input_descriptors(model))
        bound = bind_values(model, values)
        selected = next(row for row in result['candidates'] if row['candidate_id'] == candidate_id)
        variable_binding.verify_actual_binding(selected, adapter, model['settings'], bound['settings'],
            required=variable_domains.typed(list(variables.values())) and
            selected.get('diagnostics', {}).get('evaluation_mode') == 'FILE_BASED_NATIVE')
        changes = _changes(model, bound, values)
        errors = owner.diagnostics(bound)
        if errors:
            raise ValueError(errors[0]['message'])
    else:
        if inputs.get('backend') != 'evaluation.definition':
            raise ValueError('Candidate does not use the selected saved EvaluationDefinition')
        expected = {'definition_ref': source}
        if request['operation'] == 'fit':
            experiments = inputs.get('experiments', [])
            if not experiments or any(row.get('settings') != expected for row in experiments):
                raise ValueError('Fit configurations must use the exact same saved EvaluationDefinition')
            if 'settings' in inputs and inputs['settings'] != expected:
                raise ValueError('Submitted EvaluationDefinition reference differs')
        elif inputs.get('settings') != expected:
            raise ValueError('Submitted EvaluationDefinition reference differs from the original source')
        snapshots = owner.snapshots(model, original)
        compiled = compile_definition(model, snapshots)
        if model.get('reuse'):
            raise ValueError('Numerical candidate adoption cannot carry direct-run reuse state')
        _admitted(variables, compiled['inputs'])
        bound, grouped = deepcopy(model), {}
        from .evaluation_shared_inputs import assign
        adopted_models, receipts = assign(model['bindings'], {key: row['model'] for key, row in compiled['stages'].items()},
            values, input_descriptors, bind_values)
        for binding in bound['bindings']:
            if 'targets' in binding and binding['id'] in values:
                value = values[binding['id']]
                if binding['value'] != value:
                    changes.append({'path': ['bindings', binding['id']], 'before': deepcopy(binding['value']),
                        'after': deepcopy(value), 'unit': binding['unit']})
                binding['value'] = deepcopy(value)
        for stage in model['stages']:
            assignments = {target['input_id']: target['applied_value'] for receipt in receipts
                for target in receipt['targets'] if target['stage'] == stage['id']}
            if not assignments:
                continue
            original_model = compiled['stages'][stage['id']]['model']
            adopted = adopted_models[stage['id']]
            stage_changes = _changes(original_model, adopted, assignments, stage=stage['id'])
            changes.extend(stage_changes)
            if canonical_hash(adopted) == canonical_hash(original_model):
                continue
            key = canonical_hash({'source': stage['source'], 'draft': adopted})
            if key not in grouped:
                grouped[key] = {'key': key, 'kind': stage['source']['kind'], 'source': deepcopy(stage['source']),
                    'draft': adopted, 'stage_ids': [], 'title': ('Candidate ' + candidate_id + ' — ' + stage['name'])[:160]}
            grouped[key]['stage_ids'].append(stage['id'])
        branches = list(grouped.values())
    return {'target_document_id': source['document_id'], 'target_kind': source['kind'],
        'candidate_id': candidate_id, 'source': deepcopy(source), 'draft': bound,
        'changes': changes, 'branch_plan': branches, 'result_sha256': canonical_hash(result),
        'plan_input_sha256': run['input_sha256'], 'parameter_assignments': values,
        'executed': False, 'engineering_release': 'NOT_RELEASED'}


def _basis(owner, prepared, expected_generation=None):
    current = owner.read(prepared['target_document_id'])
    source = prepared['source']
    if (current['input_revision'] != source['input_revision'] or canonical_hash(current['draft']) != source['input_sha256']
            or expected_generation is not None and current['generation'] != expected_generation):
        raise ValueError('The original domain changed after this Plan was bound; rebind explicitly before adoption')
    return current


def preview(wb, plan_id, job_id, candidate_id):
    """Read actual frozen inputs and show pure bindings; create no documents."""
    prepared = _prepare(wb, plan_id, job_id, candidate_id)
    owner = _owner(wb, prepared['target_kind'])
    with owner._lock(prepared['target_document_id']):
        _basis(owner, prepared)
    return deepcopy(prepared)


def _command_id(parent, phase, identifier):
    return 'C' + canonical_hash({'parent': parent, 'phase': phase, 'document': identifier})[:48]


def _save_once(owner, identifier, *, session_id, generation, command_id, draft_sha256):
    """Use the owner Save receipt; recover only a verifiably published Save."""
    with owner._lock(identifier):
        current = owner.read(identifier)
        if current['generation'] != generation or canonical_hash(current['draft']) != draft_sha256:
            raise ValueError('A prepared branch or adopted target changed; the frozen adoption cannot be rebased')
        path = owner._folder(identifier) / 'commands' / (command_id + '.json')
        signature = canonical_hash({'document_id': identifier, 'operation': 'document.save', 'arguments': {},
            'session_id': session_id, 'expected_generation': generation})
        if path.exists():
            receipt = load_json(path)
            if receipt.get('request_hash') != signature:
                raise ValueError('Save receipt conflicts with the frozen adoption')
            if 'response' not in receipt:
                manifest = owner._manifest(identifier)
                if (receipt.get('operation') != 'document.save' or receipt.get('input_revision') != current['input_revision']
                        or current.get('dirty') or not current.get('saved_revision')
                        or not manifest or manifest['revision'] != current['saved_revision']):
                    raise ValueError('Prepared Save outcome is unconfirmed; existing inputs and prepared branches remain')
                saved = owner._verify_revision(identifier, current['saved_revision'])
                if saved['input_revision'] != current['input_revision'] or canonical_hash(saved['draft']) != draft_sha256:
                    raise ValueError('Published Save differs from the prepared adoption')
                response = {'document': current, 'command_id': command_id}
                save_json(path, {'request_hash': signature, 'response': response})
                return current
        return owner.command(identifier, 'document.save', {}, session_id=session_id,
            expected_generation=generation, command_id=command_id)['document']


def adopt(wb, plan_id, job_id, candidate_id, *, target_document_id, session_id, expected_generation, command_id, detail_evidence=None):
    """Prepare saved branches, then explicitly edit the one original owner."""
    plan_id, job_id, target_document_id, command_id = map(check_id, (plan_id, job_id, target_document_id, command_id))
    if session_id != wb.session_id or type(expected_generation) is not int or expected_generation < 0:
        raise ValueError('Domain adoption requires the current service session and exact target generation')
    _, selected_run, selected_result, _ = _run(wb, plan_id, job_id)
    if selected_result.get('kind') == 'fit':
        from .numerical_candidate_evidence import require_adoption_evidence
        require_adoption_evidence(wb.numerical_documents, detail_evidence, selected_run, selected_result, candidate_id)
    request_identity = {'plan_id': plan_id, 'job_id': job_id, 'candidate_id': candidate_id,
        'target_document_id': target_document_id, 'session_id': session_id, 'expected_generation': expected_generation}
    if selected_result.get('kind') == 'fit':
        request_identity['candidate_evidence'] = deepcopy(detail_evidence)
    request_hash = canonical_hash(request_identity)
    path = wb.root / 'domain_adoptions' / (command_id + '.json')
    with wb.desktop._lock:
        if path.exists():
            receipt = load_json(path)
            if receipt.get('request_hash') != request_hash:
                raise ValueError('Domain adoption command_id conflicts with an earlier request')
            if 'response' in receipt:
                return deepcopy(receipt['response'])
            prepared = receipt['prepared']
            _, run, result, source = _run(wb, plan_id, job_id)
            if (source != prepared['source'] or run['input_sha256'] != prepared['plan_input_sha256']
                    or canonical_hash(result) != prepared['result_sha256']):
                raise ValueError('The frozen candidate evidence changed; unresolved adoption remains preserved')
        else:
            prepared = _prepare(wb, plan_id, job_id, candidate_id)
            if prepared['target_document_id'] != target_document_id:
                raise ValueError('The candidate belongs to another original domain document')
            owner = _owner(wb, prepared['target_kind'])
            with owner._lock(target_document_id):
                _basis(owner, prepared, expected_generation)
            plan = wb.numerical_documents.read(plan_id)
            run = next(row for row in plan['runs'] if row['job_id'] == job_id)
            if not run.get('retention_complete') or not run.get('retained_result'):
                plan = wb.numerical_documents.command(plan_id, 'document.save', {}, session_id=session_id,
                    expected_generation=plan['generation'])['document']
            retained = next(row for row in plan['runs'] if row['job_id'] == job_id)
            if not retained.get('retention_complete') or not retained.get('retained_result'):
                raise ValueError('Save and retain the completed candidate result before adoption')
            receipt = {'request_hash': request_hash, 'prepared': prepared, 'plan_revision': retained['retained_result']['revision'],
                       'state': 'PREPARING_BRANCHES', 'branches': {}}
            save_json(path, receipt)
        owner = _owner(wb, prepared['target_kind'])
        with owner._lock(target_document_id):
            # Completed owner.adopt records are recoverable without rebasing.
            current = owner.read(target_document_id)
            applied = any(row.get('command_id') == command_id for row in current.get('adoptions', []))
            if not applied:
                _basis(owner, prepared, expected_generation)
            draft = deepcopy(prepared['draft'])
            for branch in prepared['branch_plan']:
                identifier = {'material': 'M', 'pde': 'Q', 'simulation': 'V'}[branch['kind']] + canonical_hash(
                    {'command_id': command_id, 'request_hash': request_hash, 'branch': branch['key']})[:48]
                branch_owner = _owner(wb, branch['kind'])
                with branch_owner._lock(identifier):
                    if (branch_owner._folder(identifier) / 'working.json').exists() or branch_owner._manifest(identifier):
                        document = branch_owner.read(identifier)
                    else:
                        document = branch_owner.open(_new_id=identifier, title=branch['title'], draft=branch['draft'])
                    if canonical_hash(document['draft']) != canonical_hash(branch['draft']) or document['generation'] != 0:
                        raise ValueError('The prepared branch changed; adoption cannot silently replace it')
                    document = _save_once(branch_owner, identifier, session_id=session_id, generation=0,
                        command_id=_command_id(command_id, 'branch-save', identifier), draft_sha256=canonical_hash(branch['draft']))
                    reference = document_reference(document)
                receipt['branches'][branch['key']] = {'document_id': identifier, 'source': reference, 'stage_ids': branch['stage_ids']}
                save_json(path, receipt)
                for stage in draft['stages']:
                    if stage['id'] in branch['stage_ids']:
                        stage['source'] = deepcopy(reference)
            if prepared['target_kind'] == 'evaluation':
                compile_definition(draft, owner.snapshots(draft, owner._documents[target_document_id]))
            evidence = {'original_domain': prepared['source'], 'plan_id': plan_id, 'job_id': job_id,
                'plan_revision': receipt['plan_revision'], 'candidate_id': candidate_id,
                'input_sha256': prepared['plan_input_sha256'], 'result_sha256': prepared['result_sha256'],
                'parameter_assignments': prepared['parameter_assignments'], 'branches': deepcopy(receipt['branches']),
                'engineering_release': 'NOT_RELEASED'}
            if selected_result.get('kind') == 'fit':
                evidence['candidate_evidence'] = deepcopy(detail_evidence)
            response = owner.adopt(target_document_id, draft, evidence,
                expected_input_revision=prepared['source']['input_revision'], expected_input_hash=prepared['source']['input_sha256'],
                session_id=session_id, expected_generation=expected_generation, command_id=command_id)
            if prepared['target_kind'] == 'evaluation':
                saved = _save_once(owner, target_document_id, session_id=session_id,
                    generation=response['document']['generation'], command_id=_command_id(command_id, 'target-save', target_document_id),
                    draft_sha256=canonical_hash(draft))
                response['document'] = saved
            response.update(executed=False, target_kind=prepared['target_kind'], source=deepcopy(prepared['source']),
                result_sha256=prepared['result_sha256'], branches=deepcopy(receipt['branches']))
            save_json(path, {**receipt, 'state': 'SUCCEEDED', 'response': response})
            return deepcopy(response)
