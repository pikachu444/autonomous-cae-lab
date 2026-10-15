"""Explicit derived readback of pinned native outputs; never starts CalculiX.

Reuse strict FRD/STA admission, the existing converged-prefix reader, dynamic
artifact writer and Post registration contract. Parent attempt files/job status
are read-only. Every recovery has its own artifact directory and exact ancestry.
"""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import uuid

from .adapters.frozen_fem import _read, _sha, read_frd
from .dynamic_result_store import file_pin, verify_pin
from .dynamic_execution import read_terminal, artifact_rows
from .execution_control import check_cancelled, ExecutionCancelled
from .storage import save_json


def reprocess(attempt, output, *, expected_sources=None, expected_record=None,
              readback_job=None, original_job_state=None):
    """Return a NEW readback receipt, preserving original FAILED/CANCELLED/UNKNOWN.

    Legacy attempts without a terminal/owner record need an explicit complete
    expected_sources map (relative -> bytes/sha256). This is provenance admission,
    not permission to infer successful execution from STA or a file name.
    """
    from .adapters.contact_fem import validate_snapshot
    from .adapters.dynamic_fem import finish
    from .contact_deck import validate_model
    from .contact_steps import profile, validate_frames
    from .contact_status import read_status, require_converged, retained_prefix
    from .dynamic_model import enabled
    attempt, output = Path(attempt).absolute(), Path(output).absolute()
    if any(p.is_symlink() for path in (attempt, output) for p in (path, *path.parents)):
        raise ValueError('Recovery requires regular local source/destination directories')
    attempt = attempt.resolve(strict=True)
    output = output.resolve()
    if output.exists() or output.is_relative_to(attempt) or attempt.is_relative_to(output):
        raise ValueError('Choose a new recovery directory outside the original attempt')
    manifest, model, input_pins, _ = validate_snapshot(attempt/'frozen_input/snapshot.json')
    if not enabled(model):
        raise ValueError('This dedicated recovery is for native dynamic structural results')
    record_path = attempt/'contact_execution.json'
    if expected_record is not None:
        if expected_record.get('relative') != 'contact_execution.json':
            raise ValueError('Expected record must pin the original contact_execution.json')
        verify_pin(attempt, expected_record)
    record_bytes = _read(record_path) if record_path.is_file() else None
    parent = json.loads(record_bytes) if record_bytes is not None else None
    if parent is not None:
        if parent.get('snapshot_id') != manifest['id']:
            raise ValueError('Original execution record and frozen snapshot differ')
        native = read_terminal(attempt, full=True)
        if native.get('status') in ('STARTING', 'RUNNING', 'CLEANUP_PENDING'):
            raise ValueError('Original native termination is not established; do not reprocess active output')
        pins = {r['relative']: {k: r[k] for k in ('bytes', 'sha256')} for r in parent['artifacts']}
        # A prior terminal-only publication already contains these raw pins.
        for name, pin in (parent.get('native_execution') or {}).get('source_pins', {}).items():
            if pins.get(name) != pin:
                raise ValueError('Original terminal and execution artifact pins disagree')
        if expected_sources is not None and any(pins.get(k) != v for k, v in expected_sources.items()):
            raise ValueError('Explicit expected raw sources differ from original execution pins')
        original_status = parent.get('execution_status', 'UNKNOWN')
    else:
        if not isinstance(expected_sources, dict) or not expected_sources:
            raise ValueError('Unrecorded legacy output requires explicit expected_sources; status remains UNKNOWN')
        pins = deepcopy(expected_sources)
        parent = {}
        native = {'status': 'UNKNOWN', 'analysis_completion': 'UNKNOWN',
                  'terminal_observation': 'NOT_RECORDED', 'reason': 'unrecorded_legacy_output'}
        original_status = 'UNKNOWN'
    record_execution_status = original_status
    if original_job_state is not None:
        if original_job_state not in {'SUCCEEDED','FAILED','CANCELLED','INTERRUPTED','PARTIAL_FAILURE'}:
            raise ValueError('An exact terminal source job is required for readback')
        if original_job_state != 'SUCCEEDED':
            original_status = ('CANCELLED' if original_job_state == 'CANCELLED' else
                               'UNKNOWN' if original_job_state == 'INTERRUPTED' else 'FAILED')
    if original_status not in ('SUCCEEDED', 'FAILED', 'CANCELLED', 'REJECTED', 'UNKNOWN'):
        raise ValueError('An exact terminal original job status is required')
    names = {'frozen_input/' + name for name in input_pins}
    names |= {'solver/contact.inp', 'solver/contact.frd', 'solver/contact.sta'}
    names |= {name for name in pins if name.startswith('solver/') and Path(name).name in {
        'contact.dat', 'contact.rout', 'contact.rin', 'ccx_contact.execution.json',
        'ccx_contact.stdout.log', 'ccx_contact.stderr.log'}}
    # A file present but never pinned is not quietly omitted or silently trusted.
    for name in ('solver/contact.dat', 'solver/contact.rout', 'solver/contact.rin'):
        if (attempt/name).is_file():
            names.add(name)
    source_pins = {}
    for name in sorted(names):
        if name not in pins:
            raise ValueError('Original raw source was not pinned: ' + name)
        verify_pin(attempt, {'relative': name, **pins[name]})
        source_pins[name] = deepcopy(pins[name])
    if any(source_pins['frozen_input/'+n] != pin for n, pin in input_pins.items()):
        raise ValueError('Recovery source differs from admitted frozen input')
    if source_pins['solver/contact.inp'] != input_pins['contact.inp']:
        raise ValueError('Recovery executed input differs from original frozen deck')
    # No executable path resolution and no before_run/submit/run call here.
    check_cancelled()
    output.mkdir(parents=True)
    result = {k: deepcopy(parent.get(k)) for k in ('job_id', 'job_identity', 'input_origin', 'data_id', 'runtime')}
    result['runtime'] = deepcopy(parent.get('runtime') or {})
    result.update(execution_status=original_status, responses={}, snapshot_id=manifest['id'],
                  input_pins=input_pins, qualification='UNKNOWN', decision='NOT_RELEASED',
                  engineering_valid=False, artifacts=[], diagnostics={},
                  native_execution=deepcopy(parent.get('native_execution', native)),
                  solver_execution='NOT_PERFORMED',
                  derivation={'kind': 'explicit_native_output_readback', 'id': uuid.uuid4().hex,
                              'original_execution_status': original_status,
                              'original_snapshot_id': manifest['id'], 'original_job_id': parent.get('job_id'),
                              'source_pins': source_pins,
                              'original_record_execution_status': record_execution_status,
                              'original_job_state':original_job_state,
                              'readback_job':deepcopy(readback_job)})
    result['native_execution'].setdefault('snapshot_id', manifest['id'])
    result['native_execution'].setdefault('job_id', parent.get('job_id'))
    parsed = None
    try:
        for name in sorted(names):
            check_cancelled()
            dest = output/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            with (attempt/name).open('rb') as src, dest.open('xb') as dst:
                shutil.copyfileobj(src, dst)
            verify_pin(output, {'relative': name, **source_pins[name]})
        if record_bytes is not None:
            (output/'source_execution.json').write_bytes(record_bytes)
            result['derivation']['original_execution_record'] = file_pin(output, output/'source_execution.json')
        validate_snapshot(output/'frozen_input/snapshot.json')
        status = read_status(output/'solver/contact.sta', model)
        result['increment_history'] = status
        result['failure_location'] = status['failure_location']
        nodes, elements, bodies = validate_model(model)
        indices = {b: i+1 for i, b in enumerate(sorted(bodies))}
        materials = {'names': ['M'+str(i) for i in indices.values()] +
                     ['INT'+p['object_id'].upper() for p in model['contacts'] if p['draft']['normal_law'] != 'tie'],
                     'elements': {e['element_id']: 'M'+str(indices[e['body_id']]) for e in model['elements']}}
        if any(p['draft'].get('tie_adjust', False) for p in model['contacts']):
            # Dynamic input admission currently excludes this combination; do not reinterpret geometry.
            raise ValueError('Recovery of adjusted tie coordinates needs the original common tie reader')
        complete = (original_status == 'SUCCEEDED' or native.get('analysis_completion') ==
                    'REQUESTED_NATIVE_STEP_ENDS_RECORDED' and native.get('input_runtime_binding') ==
                    'VERIFIED_AT_NATIVE_TERMINAL')
        if complete:
            reading = output/'solver/contact.frd'
            from .dynamic_native_stream import read_dynamic_frd
            parsed = read_dynamic_frd(reading, nodes, elements, contact_materials=materials,
                              contact_profile=profile(model), require_contact=any(p['draft']['normal_law'] != 'tie' for p in model['contacts']))
            validate_frames(model, parsed, complete=True)
            require_converged(parsed['frames'], status)
            result['derivation']['read_scope'] = 'ALL_REQUESTED_NATIVE_OUTPUT'
        else:
            reading = output/'partial/committed.frd'
            parsed = retained_prefix(output/'solver/contact.frd', reading, nodes, elements, materials, model, status, streaming=True)
            result['partial_result'] = {'status': 'CONVERGED_PREFIX', 'frame_count': len(parsed['frames']),
                                        'complete_analysis': False, 'frd_retention': parsed['retention']}
            result['derivation']['read_scope'] = 'STRICT_CONVERGED_RETAINED_PREFIX'
        # Preserve original execution status even if reprocessing succeeds.
        finish(output, model, manifest, input_pins, result, parsed=parsed,
               parsed_pin=file_pin(output, reading), frd_source=reading.relative_to(output).as_posix())
        result['execution_status'] = original_status
        result['responses'] = {}  # No new successful solve response is manufactured by a read command.
        result['frame_count'] = result.get('dynamic_result', {}).get('frame_count', 0)
        result['readback_status'] = ('SUCCEEDED' if result.get('dynamic_post_artifacts') else
                                    'CANCELLED' if 'CANCELLED' in result.get('postprocessing', {}).values() else 'FAILED')
        for name, pin in source_pins.items():
            verify_pin(attempt, {'relative': name, **pin})
        if record_bytes is not None and _read(record_path) != record_bytes:
            raise ValueError('Original attempt record changed during explicit recovery')
    except (ExecutionCancelled, OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        result['readback_status'] = 'CANCELLED' if isinstance(exc, ExecutionCancelled) else 'FAILED'
        result.setdefault('diagnostics', {})['recovery'] = str(exc)
        # Incomplete derived output stays on disk but is never an advertised completed result.
        for key in ('dynamic_result', 'dynamic_post_artifacts', 'post_artifact'):
            result.pop(key, None)
    finally:
        from .dynamic_native_stream import release
        release(parsed)
    result['execution_status'] = original_status
    result['responses'] = {}
    result['artifacts'] = artifact_rows(output)
    save_json(output/'contact_execution.json', result)
    save_json(output/'post_regeneration.json', {k: deepcopy(result.get(k)) for k in
        ('readback_status', 'execution_status', 'frame_count', 'solver_execution', 'derivation', 'post_artifact')})
    return result


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description='Explicit pinned dynamic output readback; no solver.', allow_abbrev=False)
    parser.add_argument('--from-attempt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-sources', type=Path)
    args = parser.parse_args(argv)
    expected = json.loads(_read(args.expected_sources)) if args.expected_sources else None
    result = reprocess(args.from_attempt, args.output, expected_sources=expected)
    print(json.dumps({k: result.get(k) for k in ('readback_status', 'execution_status', 'frame_count', 'solver_execution')}, allow_nan=False))
    return 0 if result['readback_status'] == 'SUCCEEDED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
