"""Native terminal evidence in the existing contact_execution record.

This is not a job manager. The common adapter still owns the process. The hook
runs immediately after its owned command, before FRD parsing or Post publication.
Raw evidence remains readable even when the later job is cancelled or failed.
"""
from copy import deepcopy
import json
from pathlib import Path

from .adapters.frozen_fem import _read, _sha
from .dynamic_model import enabled
from .dynamic_result_store import file_pin, verify_pin, admit_pin
from .storage import save_json


def artifact_rows(output):
    """Existing attempt manifest entries, excluding its own mutable record."""
    output = Path(output)
    return [file_pin(output, p) for p in sorted(output.rglob('*'))
            if p.is_file() and not p.is_symlink() and p.name != 'contact_execution.json'
            and not any(part.startswith(('.caelab-', '.dynamic-energy-')) for part in p.relative_to(output).parts)]


def capture_terminal(output, model, manifest, pins, result, *, completed=None):
    """Persist return/termination and raw pins BEFORE any heavy result projection.

    completed is the value returned by the existing owned executor, never a
    guessed PID or an inferred STA success. A command exception uses only that
    executor's explicit terminal receipt; absent evidence stays UNKNOWN.
    """
    if not enabled(model):
        return
    output = Path(output)
    native = {'status': 'UNKNOWN', 'analysis_completion': 'UNKNOWN',
              'snapshot_id': manifest['id'], 'job_id': result.get('job_id'),
              'runtime': deepcopy(result.get('runtime')), 'source_pins': {},
              'terminal_observation': 'NOT_RECORDED', 'return_code': None,
              'postprocessing_is_separate': True}
    result['native_execution'] = native
    result['postprocessing'] = {'result': 'NOT_STARTED', 'post': 'NOT_STARTED'}
    try:
        receipt = output / 'solver/ccx_contact.execution.json'
        observed = json.loads(_read(receipt)) if receipt.is_file() else None
        terminal = {'COMPLETED', 'FAILED_EXECUTION', 'CANCELLED', 'BUDGET_EXHAUSTED',
                    'INTERRUPTED', 'CLEANUP_PENDING'}
        if completed is not None:
            code = completed.returncode
            if type(code) is not int:
                raise ValueError('Owned executor did not return an integer terminal code')
            if observed is not None and (observed.get('return_code') != code or observed.get('status') not in terminal):
                raise ValueError('Owned command return and its terminal receipt differ')
            native.update(status='COMPLETED' if code == 0 else 'FAILED_EXECUTION',
                          return_code=code, terminal_observation='OWNED_COMMAND_RETURN')
        elif observed is not None and observed.get('status') in terminal:
            native.update(status=observed['status'], return_code=observed.get('return_code'),
                          terminal_observation='OWNED_COMMAND_TERMINAL_RECEIPT')
        names = ['frozen_input/' + name for name in pins]
        names += [p.relative_to(output).as_posix() for p in (output / 'solver').iterdir()
                  if p.is_file() and p.name in {'contact.inp', 'contact.frd', 'contact.dat',
                    'contact.sta', 'contact.rout', 'contact.rin', 'ccx_contact.execution.json',
                    'ccx_contact.stdout.log', 'ccx_contact.stderr.log'}]
        for name in sorted(set(names)):
            pin = file_pin(output, output / name)
            native['source_pins'][name] = {k: pin[k] for k in ('bytes', 'sha256')}
        for name, pin in pins.items():
            if native['source_pins']['frozen_input/' + name] != pin:
                raise ValueError('Frozen input changed before native terminal preservation')
        if native['source_pins']['solver/contact.inp'] != pins['contact.inp']:
            raise ValueError('Executed deck differs from admitted native input')
        runtime = result.get('runtime', {})
        if _sha(Path(runtime['executable'])) != runtime['sha256']:
            raise ValueError('Native executable changed before terminal preservation')
        if model.get('restart') and native['source_pins'].get('solver/contact.rin') != {
                k: model['restart']['rin'][k] for k in ('bytes', 'sha256')}:
            raise ValueError('Executed READ bytes differ from original checkpoint')
        native['input_runtime_binding'] = 'VERIFIED_AT_NATIVE_TERMINAL'
        if receipt.is_file():
            native['command_receipt'] = {'relative': 'solver/ccx_contact.execution.json',
                                        **native['source_pins']['solver/ccx_contact.execution.json']}
        sta = output / 'solver/contact.sta'
        if sta.is_file():
            from .contact_status import read_status
            from .calculix_dynamic import stage_contract
            from .adapters.fixture_field import _printed_close
            try:
                status = read_status(sta, model)
                result['increment_history'] = status
                result['failure_location'] = status['failure_location']
                cutoff = model.get('restart', {}).get('checkpoint', {}).get('step', 0)
                completed_steps = []
                stages = [s for s in stage_contract(model) if s['index'] > cutoff]
                for stage in stages:
                    matches = [r for r in status['rows'] if r['converged'] and r['step'] == stage['index']
                               and _printed_close(r['native_tokens'][4], stage['native_global_end'])]
                    if len(matches) == 1:
                        completed_steps.append({'step': stage['index'], 'increment': matches[0]['increment'],
                                                'source_line': matches[0]['line'],
                                                'native_tokens': matches[0]['native_tokens']})
                native['completed_steps'] = completed_steps
                native['status_source'] = status['source']
                if native['status'] == 'COMPLETED' and len(completed_steps) == len(stages) and stages:
                    native['analysis_completion'] = 'REQUESTED_NATIVE_STEP_ENDS_RECORDED'
            except (OSError, ValueError, KeyError, UnicodeError) as exc:
                native['sta_diagnostic'] = str(exc)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        native['input_runtime_binding'] = 'UNVERIFIED'
        native['analysis_completion'] = 'UNKNOWN'
        native['evidence_error'] = str(exc)
    result['artifacts'] = [{'relative': name, **pin} for name, pin in native['source_pins'].items()]
    save_json(output / 'contact_execution.json', result)


def read_terminal(attempt, *, full=False):
    """No FRD/result/frame parse, no executable lookup, no status promotion."""
    attempt = Path(attempt)
    raw = _read(attempt / 'contact_execution.json')
    record = json.loads(raw)
    native = record.get('native_execution')
    if not native:
        return {'status': 'UNKNOWN', 'analysis_completion': 'UNKNOWN',
                'terminal_observation': 'NOT_RECORDED', 'reason': 'legacy_attempt_has_no_terminal_evidence',
                'execution_status': record.get('execution_status', 'UNKNOWN'), 'solver_execution': 'NOT_PERFORMED'}
    if native.get('snapshot_id') != record.get('snapshot_id') or native.get('job_id') != record.get('job_id'):
        raise ValueError('Native terminal evidence belongs to a different job/input')
    for name, pin in native.get('source_pins', {}).items():
        (verify_pin if full else admit_pin)(attempt, {'relative': name, **pin})
    if _read(attempt / 'contact_execution.json') != raw:
        raise ValueError('Attempt record changed during terminal read')
    return {**deepcopy(native), 'execution_status': record['execution_status'],
            'postprocessing': deepcopy(record.get('postprocessing')),
            'verification': {'scope':'ALL_NATIVE_BYTES' if full else 'TERMINAL_RECORD_AND_SOURCE_ADMISSION',
                             'source_contents':'VERIFIED' if full else 'DEFERRED'},
            'solver_execution': 'NOT_PERFORMED'}
