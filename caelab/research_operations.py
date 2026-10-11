"""Small retained-input bridges for the existing numerical research engines.

Edited plans carry exact result identities, not copied candidate tables or server
paths. Resolution happens at execution, through the existing document owners.
"""
from copy import deepcopy
import math

from .storage import canonical_hash, check_id

RESULT_REF_KEYS = {'document_id', 'job_id', 'input_revision', 'input_sha256', 'result_sha256'}
RESULT_REF_SCHEMA = {'type': 'object', 'additionalProperties': False,
    'required': sorted(RESULT_REF_KEYS), 'properties': {
        **{key: {'type': 'string', 'pattern': '^[A-Za-z][A-Za-z0-9_-]{0,79}$'}
           for key in ('document_id', 'job_id', 'input_revision')},
        **{key: {'type': 'string', 'pattern': '^[a-f0-9]{64}$'}
           for key in ('input_sha256', 'result_sha256')}}}
RESULT_ROLES = {'doe': {'candidates'}, 'analyze': {'table'}, 'surrogate': {'training', 'holdout'},
                'sensitivity': {'table'}, 'batch_export': {'candidates'}, 'batch_import': {'batch'}}


def result_metadata(result):
    """Bounded physical response catalog from actual retained rows, no values."""
    candidates=result.get('candidates',result.get('predictions',[]))
    rows=candidates or [result]
    catalog,meanings,diagnostics,counts={},{},[],{}
    keys=('unit','component','location','measure','frame','coordinate_system','coordinate_frame')
    for row in rows:
        state='PREDICTED' if row.get('prediction_status') == 'PREDICTED' else row.get('execution_status','UNKNOWN')
        counts[state]=counts.get(state,0)+1
        definitions=[(name,response,False) for name,response in row.get('responses',{}).items()]
        definitions.extend((entry.get('response'),entry,True) for entry in row.get('response_reductions',[]))
        for name,response,reduced in definitions:
            if not name or response.get('kind') not in ('scalar','series','field'):
                continue
            descriptor={key:deepcopy(response[key]) for key in keys if key in response}
            descriptor.update(response=name,kind=response.get('original_kind',response['kind']))
            signature=canonical_hash(descriptor)
            meanings.setdefault(name,set()).add(signature)
            if signature not in catalog and len(catalog)>=512:
                if 'Response catalog truncated to 512 distinct physical definitions' not in diagnostics:
                    diagnostics.append('Response catalog truncated to 512 distinct physical definitions')
                continue
            item=catalog.setdefault(signature,{**descriptor,'reductions':[],'row_count':0})
            if reduced or response['kind']=='scalar':
                reductions=[response.get('reduction','none')]
            elif response['kind']=='series':
                reductions=['max','min','mean','final','abs_max']
            else:
                reductions=[]  # Field reductions require a supported explicit field selector.
            item['reductions']=sorted(set(item['reductions'])|set(reductions))
            item['row_count']+=1
    for name,versions in meanings.items():
        if len(versions)>1:
            diagnostics.append('Physical metadata conflict for '+name+'; definitions are separate and cannot be relabelled')
    sampling=result.get('sampling',{})
    # Never copy a complete sampling matrix/plan or response table into a catalog.
    sampling={key:deepcopy(sampling[key]) for key in ('method','adaptive','seed','base_count','second_order') if key in sampling}
    native = {}
    for name, descriptor in result.get('native_channels', {}).items():
        if len(native) >= 512:
            diagnostics.append('Native channel catalog is limited to 512 definitions; use the exact result reader for further selections')
            break
        if not isinstance(descriptor, dict):
            continue
        item = {key: deepcopy(descriptor[key]) for key in (*keys, 'quantity', 'kind', 'location',
            'selector_template', 'selector_count', 'selectors_truncated') if key in descriptor}
        item['axes'] = [{key: deepcopy(axis[key]) for key in ('name', 'unit', 'semantics') if key in axis}
                        for axis in descriptor.get('axes', [])]
        item['source'] = {key: deepcopy(descriptor.get('source', {})[key]) for key in
                          ('backend', 'artifact', 'sha256', 'selector') if key in descriptor.get('source', {})}
        for key in ('node_ids', 'selectors'):
            choices = descriptor.get(key)
            if isinstance(choices, list):
                item[key] = deepcopy(choices[:256])
                if len(choices) > 256:
                    item['selector_count'] = len(choices)
                    item['selectors_truncated'] = True
        native[name] = item
    return {'kind':result.get('kind'), 'variables':deepcopy(result.get('variables',[])),
            'responses':list(catalog.values()), 'candidate_count':len(candidates),
            'native_channels': native,
            'execution_counts':counts,'sampling':sampling,'diagnostics':diagnostics,
            'manifest_kind':result.get('manifest',{}).get('kind')}


def _hash(value, label):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError(label + ' requires an exact SHA-256 hash')
    return value


def validate_result_reference(reference):
    if not isinstance(reference, dict) or set(reference) != RESULT_REF_KEYS:
        raise ValueError('Retained result requires exact document, job, input revision and input/result hashes')
    for key in ('document_id', 'job_id', 'input_revision'):
        check_id(reference[key])
    if reference['document_id'][0] not in {'T', 'M', 'N', 'Q', 'V', 'E'}:
        raise ValueError('Select a retained research evaluation result')
    for key in ('input_sha256', 'result_sha256'):
        _hash(reference[key], key)
    return deepcopy(reference)


def result_reference(document, job_id, result):
    """Bind one actual retained run while keeping the draft reference bounded."""
    run = next((row for row in document.get('runs', []) if row.get('job_id') == job_id), None)
    if run is None or not run.get('retention_complete') or not run.get('retained_result'):
        raise ValueError('Save and retain the exact source result before selecting it for a Plan')
    return validate_result_reference({'document_id': document['id'], 'job_id': job_id,
        'input_revision': run['input_revision'], 'input_sha256': run['input_sha256'],
        'result_sha256': canonical_hash(result)})


def validate_result_refs(operation, inputs):
    """Validate bounded source identities without loading numeric response rows."""
    references = inputs.get('result_refs')
    if references is None:
        return  # Legacy direct engine APIs retain their existing job-ID contract.
    roles = RESULT_ROLES.get(operation)
    alternatives = [roles]
    if operation == 'sensitivity':
        alternatives.append({'table', 'plan'})
    elif operation == 'batch_import':
        alternatives.append({'batch', 'results'})
    if roles is None or not isinstance(references, dict) or set(references) not in alternatives:
        raise ValueError('Declare the exact retained result roles for ' + str(operation))
    forbidden = {'table', 'job_id', 'training', 'holdout', 'training_job', 'holdout_job', 'batch_job', 'manifest'}
    if operation == 'sensitivity' and 'plan' in references:
        forbidden.add('plan')
    if operation == 'batch_import' and 'results' in references:
        forbidden.add('results')
    if operation in {'batch_export','doe'}:
        forbidden.add('candidates')
    if forbidden & set(inputs):
        raise ValueError('Pinned result references cannot be mixed with replacement tables or unpinned job IDs')
    for reference in references.values():
        validate_result_reference(reference)
    if operation == 'surrogate':
        training, holdout = references['training'], references['holdout']
        if (training['document_id'], training['job_id']) == (holdout['document_id'], holdout['job_id']):
            raise ValueError('Training and holdout must be separate retained runs')
        if training['result_sha256'] == holdout['result_sha256']:
            raise ValueError('Training and holdout cannot be copies of the same retained result')


def _resolve(reference, resolve_document, resolve_result):
    reference = validate_result_reference(reference)
    document = resolve_document(reference['document_id'])
    if document.get('id') != reference['document_id']:
        raise ValueError('Retained source resolver returned a different document')
    run = next((row for row in document.get('runs', []) if row.get('job_id') == reference['job_id']), None)
    if (run is None or not run.get('retention_complete') or not run.get('retained_result')
            or any(run.get(key) != reference[key] for key in ('input_revision', 'input_sha256'))):
        raise ValueError('Retained source result or its submitted input identity changed')
    result = resolve_result(reference['document_id'], reference['job_id'])
    if canonical_hash(result) != reference['result_sha256']:
        raise ValueError('Retained source result hash changed')
    return result


def resolve_request_inputs(operation, inputs, *, resolve_document, resolve_result):
    """Resolve retained objects only for an actual execution; never execute models.

    Returned tables preserve failures and original row order. The caller invokes
    the existing analyze/surrogate/sensitivity/batch engine with these objects.
    """
    validate_result_refs(operation, inputs)
    result = deepcopy(inputs)
    references = result.pop('result_refs', None)
    if references is None:
        return result
    resolved = {role: _resolve(reference, resolve_document, resolve_result)
                for role, reference in references.items()}
    if operation in {'analyze', 'sensitivity'}:
        result['table'] = resolved['table']
        if operation == 'sensitivity' and 'plan' in resolved:
            result['plan'] = resolved['plan']
    elif operation == 'surrogate':
        result.update(training=resolved['training'], holdout=resolved['holdout'])
    elif operation in {'batch_export','doe'}:
        table = resolved['candidates']
        if not isinstance(table.get('candidates'), list) or not isinstance(table.get('variables'), list):
            raise ValueError('Batch export requires an actual retained candidate table with variable declarations')
        if 'variables' in result:
            from .numerical import _variables
            meanings = lambda rows: {row['id']: (row['unit'], row['transform']) for row in _variables(rows)}
            if meanings(result['variables']) != meanings(table['variables']):
                raise ValueError('Batch variables cannot relabel retained candidate coordinate units or transforms')
        else:
            result['variables'] = table['variables']
        result['candidates'] = table['candidates']
        if operation=='doe':
            # Original coordinates/order/IDs from the matched sampling plan.
            # DOE evaluates these exact rows; it does not draw replacement LHS.
            result.pop('count',None)
    else:
        batch = resolved['batch']
        manifest = batch.get('manifest')
        if not isinstance(manifest, dict) or manifest.get('kind') != 'file_batch':
            raise ValueError('Select an actual retained batch export manifest')
        result['manifest'] = manifest
        if 'results' in resolved:
            rows = resolved['results'].get('candidates')
            if not isinstance(rows, list):
                raise ValueError('Batch recovery requires exact retained result candidate rows')
            result['results'] = rows
    return result


def surrogate_result(training, holdout, response, points, *, variables=None, options=None):
    """Use existing SciPy fitting with explicit exclusions and independent holdout.

    Failed or missing responses remain in their retained source tables, and their
    exclusion identities/reasons are reported. Predictions remain PREDICTED.
    """
    from .numerical import _scalar, _variables, fit_surrogate, EvaluationFailed
    training_variables = _variables(training.get('variables'))
    holdout_variables = _variables(holdout.get('variables'))
    meanings = lambda rows: {row['id']: (row['unit'], row['transform']) for row in rows}
    if meanings(training_variables) != meanings(holdout_variables):
        raise ValueError('Training and holdout variable identities, units and transforms must match explicitly')
    if variables is not None and meanings(_variables(variables)) != meanings(training_variables):
        raise ValueError('Surrogate variables cannot relabel the retained coordinate units or transforms')
    def usable(table):
        rows, exclusions = [], []
        for row in table.get('candidates', []):
            try:
                if row.get('execution_status') != 'SUCCEEDED':
                    raise EvaluationFailed(row.get('failure_reason') or row.get('execution_status') or 'Missing execution status')
                value = _scalar(row, response)
                if not math.isfinite(value):
                    raise EvaluationFailed('Nonfinite response')
                rows.append(row)
            except EvaluationFailed as error:
                exclusions.append({'candidate_id': row.get('candidate_id'), 'values': deepcopy(row.get('values')),
                                   'execution_status': row.get('execution_status'),
                                   'failure_reason': row.get('failure_reason'), 'reason': str(error)})
        return dict(table, candidates=rows), exclusions
    train, excluded_train = usable(training)
    test, excluded_test = usable(holdout)
    model = fit_surrogate(train, test, response, variables=variables, options=options)
    return {'kind': 'surrogate', 'execution_status': 'SUCCEEDED', 'predictions': model.predict(points),
            'validation': {**model.validation, 'exclusions': {'training': excluded_train, 'holdout': excluded_test},
                           'training_count': len(training.get('candidates', [])),
                           'holdout_count': len(holdout.get('candidates', []))},
            'limitations': ['Excluded failed responses remain in the exact retained input tables; validation conditions on usable rows.']}
