"""Attach an actual linear adjoint to the same retained Evaluation candidate."""
from copy import deepcopy
from pathlib import Path
import uuid
from .evaluation import read_result, save_evaluation, file_hash
from .storage import canonical_hash, utc_now
from .execution_control import check_cancelled, ExecutionCancelled, ExecutionCleanupFailed


def compute(compiled, models, result, output, admission, reserve=None, progress=None):
    from .backends import get_backend
    from .evaluation_shared_inputs import targets
    stage = admission['stage']
    original = next(row for row in result['stages'] if row['stage_id'] == stage and row['state'] == 'SUCCEEDED')
    source = output / original['result_directory']
    retained = read_result(source, verify='all')
    if canonical_hash(retained) != original['result_sha256']:
        raise ValueError('Primal stage result differs from its exact attempt')
    possible = [p for p in (source/'calculation/native',source/'native') if p.is_dir()]
    if len(possible) != 1:
        raise ValueError('Exact retained primal operator location is unavailable/ambiguous')
    reference = {key:deepcopy(original[key]) for key in ('stage_id','attempt_id','input_sha256','result_sha256','result_directory')}
    reference['result_file_sha256'] = file_hash(source/'result.json')
    folder = output / ('derivatives/adjoint-' + uuid.uuid4().hex)
    record = {'attempt_id':'A'+uuid.uuid4().hex,'stage_id':stage,'state':'RUNNING','dispatched':False,
              'started_utc':utc_now(),'result_directory':folder.relative_to(output).as_posix(),
              'primal_reference':reference}
    result['derivative_attempts'].append(record)
    try:
        check_cancelled()
        if reserve:
            reserve(1, role='adjoint')
        check_cancelled()
        record['dispatched'] = True
        if progress: progress('ADJOINT_RUNNING', active_attempt=record['attempt_id'])
        model = models[stage]
        raw = get_backend(model['backend']).run_adjoint(model['settings'], output=folder,
            primal=possible[0], request=admission['request'], reference=reference)
        raw.update(backend=model['backend'],settings=deepcopy(model['settings']))
        # A failed/cancelled worker may only have partial files; preserve those too.
        raw['artifacts'] = [{'path':p.relative_to(folder).as_posix(),'sha256':file_hash(p)}
                            for p in sorted(folder.rglob('*')) if p.is_file()]
        save_evaluation(raw,folder,existing=True)
        raw = read_result(folder,verify='all')
        record.update(state=raw['execution_status'], finished_utc=utc_now(),
                      result_sha256=canonical_hash(raw),result_file_sha256=file_hash(folder/'result.json'))
        if progress: progress('ADJOINT_FINISHED',active_attempt=record['attempt_id'])
        check_cancelled()  # Late successful data are evidence, never a post-cancel gradient.
        if raw['execution_status'] == 'CANCELLED':
            raise ExecutionCancelled('Adjoint worker cancelled; late artifacts retained')
        if raw['execution_status'] != 'SUCCEEDED':
            raise ValueError('Adjoint worker did not succeed')
        derivatives = raw['derivatives']
        bindings = {b['id']: b for b in compiled['definition']['bindings']}
        gradient = {}
        for logical in admission['logical_inputs']:
            b = bindings[logical]
            parts = [deepcopy(derivatives[t['input_id']]) for t in targets(b)]
            gradient[logical] = {'value':sum(p['value'] for p in parts), 'unit':'K/('+b['unit']+')',
                                'input_unit':b['unit'],'response_unit':'K','target_partials':parts,
                                'chain_rule':'sum target partials * identity fan-out derivative 1'}
        result['gradients'] = {name:deepcopy(gradient) for name in admission['responses']}
        result['gradient_provenance'] = {'algorithm':'discrete_linear_adjoint',
            'state':'steady_linear_fixed_mesh','adjoint_attempt_id':record['attempt_id'],
            'primal_reference':reference,'adjoint_result_sha256':record['result_sha256'],
            'adjoint_receipt':deepcopy(raw['diagnostics']['adjoint']),
            'versions':deepcopy(raw['diagnostics']['versions']), 'finite_difference_calls':0}
    except ExecutionCleanupFailed:
        record['state'] = 'CLEANUP_UNCONFIRMED'
        raise
    except Exception as error:
        if record['state'] == 'RUNNING':
            record.update(state='CANCELLED' if isinstance(error,ExecutionCancelled) else 'FAILED',
                          error=str(error), finished_utc=utc_now())
        raise
