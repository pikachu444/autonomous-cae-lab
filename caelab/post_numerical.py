"""Small Post/Data/Numerical handoff using the existing owners and job manager."""
from copy import deepcopy
import io

from .post_observation import choices, completed_snapshot, project_samples, verify_origin
from .storage import canonical_hash, check_id, load_json, save_json


def preview(workbench, command_id):
    snapshot = completed_snapshot(workbench.native_commands.status(check_id(command_id)))
    return {'command_id': command_id, 'snapshot': snapshot, 'choices': choices(snapshot)}


def prepare(workbench, command_id, selection, *, session_id, handoff_id, target_plan_id=None):
    """Import once, then create a Plan or return an observation for explicit review.

    Only the existing import_table job runs. Existing targets are read only;
    their live editors append after confirmation. No model/provider job runs.
    """
    wb = workbench
    check_id(command_id)
    check_id(handoff_id)
    if session_id != wb.session_id:
        raise ValueError('Reconnect to the current service before creating the Plan')
    target = None
    if target_plan_id is not None:
        target = wb.numerical_documents.read(check_id(target_plan_id))
        if target.get('draft', {}).get('mode') != 'request' or target['draft'].get('request', {}).get('operation') != 'fit':
            raise ValueError('Choose an existing generic fit Plan; no other method is replaced')
    signature_fields = {'command_id': command_id, 'selection': selection}
    if target_plan_id is not None:
        signature_fields['target_plan_id'] = target_plan_id
    signature = canonical_hash(signature_fields)
    path = wb.desktop.root / 'post_measurements' / (handoff_id + '.json')
    with wb.desktop._lock:
        if path.exists():
            state = load_json(path)
            if state['request_hash'] != signature:
                raise ValueError('This handoff belongs to another measurement selection')
        else:
            snapshot = completed_snapshot(wb.native_commands.status(command_id))
            converted = project_samples(snapshot, selection)
            if not converted['importable']:
                raise ValueError('Invalid rows remain visible; explicitly exclude them before importing')
            receipt = wb._store_input('measurement.csv', io.BytesIO(converted['csv']),
                                      len(converted['csv']), origin=converted['origin'])
            identity = canonical_hash({'handoff_id': handoff_id, 'signature': signature})[:32]
            state = {'request_hash': signature, 'input': receipt,
                     'data_id': 'T' + identity, 'plan_id': 'N' + identity,
                     'data_draft': {'data_id': receipt['id'], 'mapping': converted['mapping']},
                     'role': selection['role'], 'phase': 'REGISTERED'}
            save_json(path, state)
        data_owner = wb.data_documents
        def get_or_create(owner, identifier, title, draft):
            with owner._lock(identifier):
                if (owner._folder(identifier) / 'working.json').exists() or owner._manifest(identifier):
                    return owner.read(identifier)
                return owner.open(_new_id=identifier, title=title, draft=draft)
        def command(owner, document, operation, suffix):
            return owner.command(document['id'], operation, {}, session_id=wb.session_id,
                expected_generation=document['generation'],
                command_id='C' + canonical_hash({'handoff': handoff_id, 'step': suffix,
                                                'session': wb.session_id})[:32])
        if state['phase'] == 'OBSERVATION_READY':
            wb.post_observation(state['result_reference'])
            return {'state': 'OBSERVATION_READY', 'target_document': target,
                    'reference': state['result_reference'], 'role': state['role'],
                    'data_document': data_owner.read(state['data_id']), 'executed': False}
        if state['phase'] == 'READY':
            return {'state': 'READY', 'document': wb.numerical_documents.read(state['plan_id']),
                    'data_document': data_owner.read(state['data_id']), 'executed': False}
        data = get_or_create(data_owner, state['data_id'], 'Post measurement', state['data_draft'])
        if data['draft'] != state['data_draft']:
            raise ValueError('The measurement Data draft was edited; open it to finish or repair the import')
        if state['phase'] == 'REGISTERED':
            if not data.get('saved_revision'):
                data = command(data_owner, data, 'document.save', 'save-input')['document']
            state.update(phase='IMPORTING', generation=data['generation'], import_session=wb.session_id)
            save_json(path, state)
        if 'job_id' not in state:
            # If a service restart interrupted submission, the existing owner
            # receipt is authoritative. Do not submit under a new command identity.
            if state['import_session'] != wb.session_id:
                raise ValueError('Import submission needs recovery in the Data document: ' + data['id'])
            submitted = command(data_owner, data, 'data.import', 'import')
            state['job_id'] = submitted['job']['id']
            save_json(path, state)
        data = data_owner.read(data['id'])
        run = next(row for row in data['runs'] if row['job_id'] == state['job_id'])
        status = wb.manager.status(state['job_id']) if not run.get('retention_complete') else {
            'state': run['retained_state'], 'error': run.get('retained_error')}
        if status['state'] not in {'SUCCEEDED', 'FAILED', 'REJECTED', 'CANCELLED', 'INTERRUPTED'}:
            return {'state': status['state'], 'job_id': state['job_id'],
                    'data_document': data, 'executed': False}
        if status['state'] != 'SUCCEEDED':
            return {'state': status['state'], 'job_id': state['job_id'],
                    'data_document': data, 'error': status.get('error'), 'executed': False}
        if not run.get('retention_complete') or not run.get('retained_result'):
            data = command(data_owner, data, 'document.save', 'retain-import')['document']
        reference = wb.document_result_reference(data['id'], state['job_id'])
        if target is not None:
            state.update(phase='OBSERVATION_READY', result_reference=reference)
            save_json(path, state)
            return {'state': 'OBSERVATION_READY', 'target_document': target,
                    'reference': reference, 'role': state['role'],
                    'data_document': data, 'executed': False}
        from .evaluation_definition import document_reference
        from .numerical_document import request_draft
        draft = request_draft({
            'purpose': 'Compare a model with the measured Post curve',
            'operation': 'fit', 'budget': {'evaluations': 100},
            'inputs': {'backend': '', 'variables': [], 'method': 'least_squares',
                'experiments': [{'id': 'measurement', 'role': state['role'],
                    'settings': {}, 'response': '', 'weight': 1.0, 'scale': 1.0,
                    'observation_ref': {'result': reference, 'response': 'measured'}}]}
        }, source=document_reference(data))
        plan = get_or_create(wb.numerical_documents, state['plan_id'], 'Measured response', draft)
        if not plan.get('saved_revision'):
            plan = command(wb.numerical_documents, plan, 'document.save', 'save-plan')['document']
        state.update(phase='READY', result_reference=reference)
        save_json(path, state)
        return {'state': 'READY', 'document': plan, 'data_document': data, 'executed': False}


def observation(workbench, reference):
    """Read the pinned observation and its retained input receipt, not latest Data."""
    from .research_operations import _resolve
    result = _resolve(reference, workbench.document_read, workbench.document_result)
    owner = workbench.data_documents
    if not reference['document_id'].startswith(owner.prefix):
        raise ValueError('This native observation is retained by the Data owner')
    document = owner.read(reference['document_id'])
    run = next(row for row in document['runs'] if row['job_id'] == reference['job_id'])
    retained = run['retained_result']['revision']
    saved = owner._verify_revision(document['id'], retained)
    data_id = run['arguments']['data_id']
    source, receipt = owner._retained_source(saved, data_id)
    owner._check_source(data_id, source, receipt)
    origin = deepcopy(receipt.get('origin'))
    if not origin or origin.get('kind') != 'post_measurement':
        raise ValueError('This Data result does not contain a native Post measurement origin')
    error = None
    try:
        verify_origin(origin)
    except (ValueError, OSError, KeyError) as failure:
        error = str(failure)
    return {'reference': deepcopy(reference), 'response': result['responses']['measured'],
            'origin': origin, 'source_available': error is None, 'source_error': error}
