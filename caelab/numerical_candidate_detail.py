"""Read retained fit candidates, or explicitly evaluate missing detail in a new run.

No optimizer, source-row compiler, Material controller or new storage is defined
here. NumericalDocuments supplies the command lock/receipts and revision store;
JobManager and numerical._Evaluators own execution. Read APIs never prepare an
adapter. A historical candidate is identified by its *source run*, not by the
currently edited Plan or Material. See docs/NUMERICAL_CANDIDATE_DETAIL_KO.md.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
from typing import Any
import uuid

from .storage import canonical_hash, check_id, load_json, save_json

SCHEMA = 'caelab.candidate-detail.v1'
INPUT_SCHEMA = 'caelab.frozen-fit-input.v1'
INCLUSION_SCHEMA = 'caelab.frozen-fit-inclusion.v1'
COMMAND = 'numerical.detail_eval'
OPERATION = 'detail_eval'
AVAILABLE = {'RETAINED'}
TERMINAL = {'SUCCEEDED', 'FAILED', 'CANCELLED', 'PARTIAL_FAILURE', 'REJECTED', 'INTERRUPTED'}


class DetailIdentityError(ValueError):
    """The retained source, input, trial or candidate no longer has this identity."""


def plain(value: Any) -> Any:
    """Use the existing null policy, including NumPy scalar JSON conversion."""
    from .numerical import _nullable
    import numpy as np
    # Normalize nulls once at the transport boundary, not once for every
    # descendant of a full processing DAG. Preserve the identical JSON values.
    def convert(item):
        if isinstance(item, dict):
            return {key: convert(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [convert(child) for child in item]
        if isinstance(item, np.generic):
            return convert(item.item())
        return item
    return convert(_nullable(value))


def experiment_snapshot(experiment: dict) -> dict:
    """Freeze the mask the original engine actually used; do not 'repair' it.

    In particular, observations.mask and the fit mask are not interchangeable.
    Both remain visible. Canonical Data inputs carry their explicitly adopted fit mask.
    """
    from .numerical import _experiment
    from .numerical_fit_lineage import validate_lineage_fields, validate_experiment_extensions
    validate_experiment_extensions(experiment)
    normalized = _experiment(experiment)
    validate_lineage_fields(normalized['observations'], count=len(normalized['_mask']))
    normalized['mask'] = normalized.pop('_mask').tolist()
    return plain(normalized)


def consume_frozen_fit_inclusion(experiments: list[dict], packet: dict) -> list[dict]:
    """Consume canonical Data packets through Data's validator; keep legacy separate.

    Legacy per-experiment packet fields remain documented in the usage file.
    Source rows/role/mask/normalization and observation, protocol and source
    hashes must already agree. Nothing is selected, converted or imputed here.
    Extension fields in the supplied experiments are copied unchanged.
    """
    if isinstance(packet, dict) and packet.get('format') == 'frozen-fit-inclusion.v1':
        from .data_processing_selection import consume_frozen_fit_inclusion as consume_data
        return consume_data(experiments, packet)
    if not isinstance(packet, dict) or packet.get('schema') != INCLUSION_SCHEMA:
        raise DetailIdentityError('Unsupported frozen fit-inclusion packet')
    entries = packet.get('experiments')
    if not isinstance(entries, list) or len(entries) != len(experiments):
        raise DetailIdentityError('Frozen fit-inclusion experiment count differs')
    for experiment, entry in zip(experiments, entries):
        frozen = experiment_snapshot(experiment)
        obs = frozen['observations']
        expected = dict(experiment_id=frozen['id'], source_rows=obs.get('source_rows'),
            mask=frozen['mask'], role=frozen['role'], weight=frozen['weight'], scale=frozen['scale'],
            unit=obs['unit'], observations_sha256=canonical_hash(obs),
            settings_sha256=canonical_hash(frozen.get('settings', {})),
            observation_source_sha256=canonical_hash(frozen.get('observation_source')))
        if (not isinstance(entry, dict) or not set(expected) <= set(entry)
                or any(canonical_hash(entry[key]) != canonical_hash(value) for key, value in expected.items())):
            raise DetailIdentityError('Frozen source_rows / inclusion / protocol identity differs: ' + frozen['id'])
    return deepcopy(experiments)


def freeze_fit_input(backend: str, inputs: dict, submitted_arguments: dict, *, inclusion_packet=None, evaluator_binding=None) -> dict:
    """Capture *resolved original* inputs at fit execution, before cache eviction."""
    from .numerical import _variables
    from .identification import require_independent_rows
    value = deepcopy(inputs)
    value.pop('backend', None)
    value.pop('settings', None)  # fit's per-experiment settings are authoritative
    experiments = value.get('experiments')
    if (not isinstance(backend, str) or not backend or not isinstance(experiments, list)
            or not experiments or any(not isinstance(e.get('observations'), dict)
                                      or 'path' in e['observations'] for e in experiments)):
        raise DetailIdentityError('Original resolved inline fit inputs were not retained; current sources cannot replace them')
    from .data_processing_consumer import admit_snapshot
    experiments, data_admission = admit_snapshot(value, submitted_arguments, legacy_packet=inclusion_packet)
    if inclusion_packet is not None:
        consume_frozen_fit_inclusion(experiments, inclusion_packet)
    value['experiments'] = [experiment_snapshot(e) for e in experiments]
    if len({e['id'] for e in value['experiments']}) != len(experiments):
        raise DetailIdentityError('Duplicate original experiment identity')
    # The shared check delegates canonical derived contributors to Data and
    # retains the original raw-row check for explicitly legacy inputs.
    require_independent_rows(value['experiments'])
    value['variables'] = _variables(value['variables'])
    value['backend'] = backend
    value = plain(value)
    result = dict(schema=INPUT_SCHEMA, submitted_arguments_sha256=canonical_hash(plain(submitted_arguments)),
                  inputs=value, inputs_sha256=canonical_hash(value))
    if inclusion_packet is not None:
        result['inclusion_packet'] = deepcopy(inclusion_packet)
    if data_admission is not None:
        result['data_inclusion'] = data_admission
    if evaluator_binding is not None:
        result['evaluator_binding'] = deepcopy(evaluator_binding)
    return result


def _frozen_input(run: dict, result: dict) -> dict:
    snapshot = result.get('fit_input_snapshot')
    if snapshot is None:
        # Pre-delivery Material Plans already retain resolved observations in
        # run.arguments. Never resolve a legacy mutable observation_job here.
        args = run['arguments']
        return freeze_fit_input(args.get('backend'), args, args)
    if (not isinstance(snapshot, dict) or snapshot.get('schema') != INPUT_SCHEMA
            or canonical_hash(snapshot.get('inputs')) != snapshot.get('inputs_sha256')
            or snapshot.get('submitted_arguments_sha256') != canonical_hash(plain(run['arguments']))):
        raise DetailIdentityError('Original fit input snapshot / submitted arguments hash changed')
    checked = freeze_fit_input(snapshot['inputs']['backend'], snapshot['inputs'], run['arguments'],
                               inclusion_packet=snapshot.get('inclusion_packet'))
    if checked.get('data_inclusion') != snapshot.get('data_inclusion'):
        raise DetailIdentityError('Canonical Data admission differs from original frozen evidence')
    if checked['inputs_sha256'] != snapshot['inputs_sha256']:
        raise DetailIdentityError('Frozen input interpretation changed')
    return deepcopy(snapshot)


def backend_binding(workbench, backend: str) -> dict:
    """Freeze registration/config and Python adapter identity without solver probes.

    External configuration is hashed, never copied into a result (it may contain
    private execution settings). Native executable/build qualification remains
    the existing adapter's responsibility; this is not a claim of binary parity.
    This function runs at explicit submission/execution, never during a read.
    """
    from importlib import metadata
    import inspect
    from pathlib import Path
    from .evaluation import file_hash
    registration = next((r for r in workbench.backends() if r['id'] == backend), None)
    if registration is None:
        raise DetailIdentityError('Original evaluator is no longer registered')
    result = {'backend': backend, 'registration_sha256': canonical_hash(registration),
              'native_binary_qualification': 'EXISTING_ADAPTER; NOT_PROBED_HERE'}
    external = workbench.config.get('external_backends', {})
    if backend in external:
        result['external_configuration_sha256'] = canonical_hash(external[backend])
    elif backend != 'evaluation.definition':
        from .backends import get_backend
        adapter = get_backend(backend)
        target = adapter if inspect.isfunction(adapter) or inspect.isclass(adapter) else type(adapter)
        path = inspect.getsourcefile(target)
        if path and Path(path).is_file():
            result['adapter_source_sha256'] = file_hash(path)
        result['adapter_version'] = str(getattr(adapter, 'version', 'UNKNOWN'))
    dependency = registration.get('optional_dependency')
    if dependency:
        try:
            result['python_dependency_version'] = metadata.version(dependency)
        except metadata.PackageNotFoundError:
            result['python_dependency_version'] = 'NOT_INSTALLED'
    return result


def validate_backend_binding(workbench, arguments: dict) -> None:
    """Reject mutable evaluator substitution before admission and again at run."""
    context = arguments['context']
    source = context['source']
    _, run, result, _ = _source(workbench.numerical_documents, source['document_id'],
                                source['job_id'], source)
    expected = _frozen_input(run, result).get('evaluator_binding')
    actual = backend_binding(workbench, arguments['backend'])
    if expected is not None and expected != actual:
        raise DetailIdentityError('Evaluator registration/config/version differs from the original fit')
    if expected is None and arguments['backend'] in workbench.config.get('external_backends', {}):
        raise DetailIdentityError('Legacy fit did not retain its external evaluator configuration identity')


def trial_detail(experiment: dict, evaluation: dict, *, origin: dict) -> dict:
    """Retain all actual outputs, even when alignment or this trial failed."""
    from .numerical import _experiment, _fit_curve
    frozen = experiment_snapshot(experiment)
    try:
        curve = _fit_curve(_experiment(frozen), evaluation)
    except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
        # A units/measure/time mismatch is a failed comparison, not zero error.
        curve = dict(experiment_id=frozen['id'], role=frozen['role'], response=frozen['response'],
                     observations=frozen['observations'], mask=frozen['mask'],
                     weight=frozen['weight'], scale=frozen['scale'],
                     execution_status='FAILED', failure_reason=f'{type(error).__name__}: {error}')
    status = curve.get('execution_status', 'UNKNOWN')
    retention = 'RETAINED'
    if evaluation.get('execution_status') == 'CANCELLED':
        status = curve['execution_status'] = 'CANCELLED'
        # A stopped trial may have raw output but is not a completed protocol.
        # Keep that output in this attempt; a new explicit attempt may retry it.
        retention = 'PARTIAL_OUTPUT' if evaluation.get('responses') else 'NOT_EVALUATED'
    return plain(dict(experiment_id=frozen['id'], experiment_sha256=canonical_hash(frozen),
        role=frozen['role'], retention=retention, execution_status=status,
        evaluation_status=evaluation.get('execution_status', 'UNKNOWN'),
        origin=deepcopy(origin), curve=curve, raw_evaluation=deepcopy(evaluation)))


def _unavailable(experiment: dict, *, reason='NOT_RETAINED', status='NOT_EVALUATED', origin=None) -> dict:
    frozen = experiment_snapshot(experiment)
    return dict(experiment_id=frozen['id'], experiment_sha256=canonical_hash(frozen), role=frozen['role'],
        retention=reason, execution_status=status, evaluation_status='UNKNOWN',
        origin=deepcopy(origin), curve=None, raw_evaluation=None)


class FitDetailRetention:
    """Bounded capture of actual search outputs; never evaluates holdout.

    The default captures at most 32 candidate records and 16 MiB. Explicit
    limits cap added result size, and exhausted limits remain visible. The
    optimizer's original eight-entry working cache is unchanged.
    """
    def __init__(self, policy=None):
        policy = deepcopy(policy)
        if policy is None:
            policy = {'candidate_limit': 32, 'byte_limit': 16 * 1024 * 1024}
        if (not isinstance(policy, dict) or set(policy) != {'candidate_limit', 'byte_limit'}
                or type(policy['candidate_limit']) is not int or not 0 <= policy['candidate_limit'] <= 128
                or type(policy['byte_limit']) is not int or not 0 <= policy['byte_limit'] <= 64 * 1024 * 1024
                or bool(policy['candidate_limit']) != bool(policy['byte_limit'])):
            raise ValueError('detail_retention requires candidate_limit 0..128 and byte_limit 0..67108864; both zero disables it')
        self.policy, self.count, self.bytes = policy, 0, 0
        self.final = None

    def capture(self, row: dict, experiments: list[dict], outputs: list[dict]) -> None:
        if not self.policy['candidate_limit']:
            return
        if self.count >= self.policy['candidate_limit']:
            row['detail_retention'] = 'NOT_RETAINED_CANDIDATE_LIMIT'
            return
        if len(experiments) != len(outputs):
            raise DetailIdentityError('Original candidate output count differs from experiment count')
        origin = {'kind': 'fit_candidate', 'candidate_id': row['candidate_id']}
        detail = dict(schema=SCHEMA, candidate_id=row['candidate_id'], values_sha256=canonical_hash(row['values']),
            trials=[trial_detail(e, output, origin=origin) for e, output in zip(experiments, outputs)])
        size = len(json.dumps(detail, ensure_ascii=False, allow_nan=False).encode('utf-8'))
        if self.bytes + size > self.policy['byte_limit']:
            row['detail_retention'] = 'NOT_RETAINED_BYTE_LIMIT'
            return
        row['candidate_detail'] = detail
        row['detail_retention'] = 'RETAINED_FIT_TRIALS'
        self.bytes += size
        self.count += 1

    def capture_final(self, candidates: list[dict], values: dict | None,
                      experiments: list[dict], outputs: list[dict]) -> None:
        """Bind original final fit/holdout outputs only to an unambiguous row.

        This adds no model call. Both count and byte exhaustion stay explicit.
        Never guess which of several identical coefficient rows was selected.
        """
        if not self.policy['candidate_limit'] or values is None:
            return
        matches = [r for r in candidates if r['execution_status'] == 'SUCCEEDED'
                   and r['values'] == values]
        if len(matches) != 1:
            self.final = {'retention': 'NOT_RETAINED_AMBIGUOUS_FINAL_CANDIDATE'}
            return
        candidate = matches[0]
        if len(experiments) != len(outputs):
            raise DetailIdentityError('Final trial and raw output counts differ')
        detail = dict(schema=SCHEMA, candidate_id=candidate['candidate_id'],
            values_sha256=canonical_hash(candidate['values']), trials=[], retention='RETAINED')
        for experiment, output in zip(experiments, outputs):
            trial = trial_detail(experiment, output, origin={
                'kind': 'fit_final', 'candidate_id': candidate['candidate_id']})
            size = len(json.dumps(trial, ensure_ascii=False, allow_nan=False).encode('utf-8'))
            if self.bytes + size <= self.policy['byte_limit']:
                detail['trials'].append(trial)
                self.bytes += size
            else:
                detail['trials'].append(_unavailable(experiment, reason='NOT_RETAINED_BYTE_LIMIT'))
                detail['retention'] = 'PARTIAL_RETENTION'
        self.final = detail

    def summary(self) -> dict:
        return dict(**self.policy, retained_candidates=self.count, retained_bytes=self.bytes,
                    holdout='FINAL_CANDIDATE_ONLY; other candidates require explicit detail_eval')


def _source(owner, document_id: str, job_id: str, expected: dict | None = None):
    document = owner.read(check_id(document_id))
    if document.get('kind') != 'numerical' or document.get('id') != document_id:
        raise DetailIdentityError('Select a Numerical owner and its original fit run')
    runs = [r for r in document.get('runs', []) if r.get('job_id') == check_id(job_id)]
    if len(runs) != 1 or runs[0].get('operation') != 'fit':
        raise DetailIdentityError('Select one original fit run, not another detail attempt')
    run = runs[0]
    if canonical_hash(plain(run.get('draft'))) != run.get('input_sha256'):
        raise DetailIdentityError('Original submitted Plan hash changed')
    from .storage import revision_read_cache
    cache=revision_read_cache();key=None
    location=getattr(owner,'_verified_candidate_result_location',None)
    if cache is not None and location is not None:
        # Only an internal saved-owner facet supplies this verified immutable
        # location. Client/live/Q archive facets retain their existing reads.
        storage,folder=location(document_id,job_id)
        key=('candidate_full_result',id(storage),str(folder.resolve()),document_id,job_id,
             canonical_hash(run.get('retained_result')),run['input_revision'],run['input_sha256'],'FULL')
    fresh=False
    if key is not None and key in cache:
        result,digest=deepcopy(cache[key])
    else:
        result=owner.result(document_id,job_id)
        digest=canonical_hash(plain(result))
        fresh=True
    if result.get('kind') != 'fit':
        raise DetailIdentityError('Source result is not the original fit result')
    reference = dict(document_id=document_id, job_id=job_id, input_revision=run['input_revision'],
                     input_sha256=run['input_sha256'], result_sha256=digest)
    if expected is not None and reference != expected:
        raise DetailIdentityError('Stale result: the exact source reference no longer matches')
    if key is not None and fresh:cache[key]=deepcopy((result,digest))
    return document, run, result, reference


def _candidate(result: dict, candidate_id: str, snapshot: dict) -> dict:
    from .numerical import _variables, _candidates
    rows = [r for r in result.get('candidates', []) if r.get('candidate_id') == check_id(candidate_id)]
    if len(rows) != 1:
        raise DetailIdentityError('Candidate is absent or ambiguous in this exact original fit run')
    row = rows[0]
    if row.get('prediction_status') or row.get('execution_status') == 'PREDICTED':
        raise DetailIdentityError('A predicted point is not an original fit candidate')
    variables = snapshot['inputs']['variables']
    if _variables(result.get('variables')) != variables:
        raise DetailIdentityError('Original result variables / units / bounds / transforms differ from fit inputs')
    _candidates([row], variables)  # bounds and exact coefficient names, not material admissibility
    return deepcopy(row)


def _validate_trial(trial: dict, experiment: dict) -> None:
    frozen = experiment_snapshot(experiment)
    if (trial.get('experiment_id') != frozen['id'] or trial.get('role') != frozen['role']
            or trial.get('experiment_sha256') != canonical_hash(frozen)):
        raise DetailIdentityError('Retained trial input / source_rows / mask / role identity changed')
    curve = trial.get('curve')
    if curve is not None:
        expected = dict(experiment_id=frozen['id'], role=frozen['role'], response=frozen['response'],
                        observations=frozen['observations'], mask=frozen['mask'],
                        weight=frozen['weight'], scale=frozen['scale'])
        if any(canonical_hash(plain(curve.get(key))) != canonical_hash(value) for key, value in expected.items()):
            raise DetailIdentityError('Retained curve and original trial identity differ')


def _original_trials(result: dict, candidate: dict, snapshot: dict) -> list[dict]:
    experiments = snapshot['inputs']['experiments']
    by_id = {e['id']: _unavailable(e, status='NOT_EVALUATED' if e['role'] == 'holdout' else 'UNKNOWN') for e in experiments}
    detail = candidate.get('candidate_detail')
    if detail is not None:
        if (detail.get('schema') != SCHEMA or detail.get('candidate_id') != candidate['candidate_id']
                or detail.get('values_sha256') != canonical_hash(candidate['values'])):
            raise DetailIdentityError('Original retained candidate detail identity changed')
        seen = set()
        for trial in detail.get('trials', []):
            identifier = trial.get('experiment_id')
            if identifier not in by_id or identifier in seen:
                raise DetailIdentityError('Retained candidate trials are absent or duplicated')
            seen.add(identifier)
            _validate_trial(trial, next(e for e in experiments if e['id'] == identifier))
            by_id[identifier] = deepcopy(trial)
    final = result.get('final_candidate_detail')
    if isinstance(final, dict) and final.get('candidate_id') == candidate['candidate_id']:
        if final.get('schema') != SCHEMA or final.get('values_sha256') != canonical_hash(candidate['values']):
            raise DetailIdentityError('Original final evaluation and candidate values differ')
        seen = set()
        for trial in final.get('trials', []):
            identifier = trial.get('experiment_id')
            if identifier not in by_id or identifier in seen:
                raise DetailIdentityError('Original final detail trial identity is absent or duplicated')
            seen.add(identifier)
            _validate_trial(trial, next(e for e in experiments if e['id'] == identifier))
            if trial.get('retention') == 'RETAINED' and by_id[identifier]['retention'] not in AVAILABLE:
                by_id[identifier] = deepcopy(trial)
    # Old results do not attach candidate_id to final curves. Infer association
    # ONLY for a unique successful row with exactly the final parameter values.
    matches = [r for r in result.get('candidates', []) if r.get('execution_status') == 'SUCCEEDED'
               and r.get('values') == result.get('parameters')]
    if len(matches) == 1 and matches[0]['candidate_id'] == candidate['candidate_id']:
        seen = set()
        for curve in result.get('curves', []):
            identifier = curve.get('experiment_id')
            if identifier not in by_id or identifier in seen:
                raise DetailIdentityError('Final curve experiment identity is absent or ambiguous')
            seen.add(identifier)
            if by_id[identifier]['retention'] == 'RETAINED':
                continue
            e = next(e for e in experiments if e['id'] == identifier)
            trial = _unavailable(e, reason='CURVE_ONLY', status=curve.get('execution_status', 'UNKNOWN'),
                origin={'kind': 'fit_final', 'candidate_id': candidate['candidate_id']})
            # Budget/cancellation-only final records do not contain a curve.
            if not all(key in curve for key in ('observations', 'mask', 'weight', 'scale', 'response')):
                trial.update(retention='NOT_RETAINED', curve=None)
            else:
                trial['curve'] = deepcopy(curve)
                _validate_trial(trial, e)
            by_id[identifier] = trial
    return list(by_id.values())


def _status(owner, run: dict) -> tuple[str, dict | None]:
    if run.get('retention_complete'):
        return run.get('retained_state', 'UNKNOWN'), run.get('retained_error')
    try:
        job = owner.manager.status(run['job_id'])
        return job.get('state', 'UNKNOWN'), job.get('error')
    except (KeyError, ValueError, OSError):
        return 'UNKNOWN', {'message': 'Job state is unavailable; no completion is inferred'}


def read_candidate_detail(owner, document_id: str, job_id: str, candidate_id: str, *,
                          attempt_job_id: str | None = None, source: dict | None = None) -> dict:
    """Pure retained read, also usable over the existing Client read endpoints."""
    from .portable_project_execution import detail_view
    portable = detail_view(owner, document_id, job_id, candidate_id,
                           source=source, attempt_job_id=attempt_job_id)
    if portable is not None:
        return portable
    return _read_verified_candidate_detail(owner, _source(owner, document_id, job_id, source),
                                           candidate_id, attempt_job_id=attempt_job_id)


def _read_verified_candidate_detail(owner, verified_source, candidate_id, *, attempt_job_id=None):
    """Use an already identity-checked source within the same evidence read."""
    document, run, result, reference = verified_source
    document_id=reference['document_id']
    snapshot = _frozen_input(run, result)
    candidate = _candidate(result, candidate_id, snapshot)
    trials = _original_trials(result, candidate, snapshot)
    attempts = []
    selected_run = None
    for attempt in document['runs']:
        context = attempt.get('arguments', {}).get('context', {})
        if (attempt.get('operation') == OPERATION and context.get('source') == reference
                and context.get('candidate_id') == candidate_id):
            status, error = _status(owner, attempt)
            attempts.append(dict(job_id=attempt['job_id'], attempt_id=context.get('attempt_id'),
                state=status, error=error, created_utc=attempt.get('created_utc'),
                requested_experiments=deepcopy(context.get('requested_experiments', []))))
            if attempt['job_id'] == attempt_job_id:
                selected_run = attempt
    active_state = None
    if attempt_job_id is not None:
        if selected_run is None:
            raise DetailIdentityError('Detail attempt does not belong to this exact source candidate')
        context = selected_run['arguments']['context']
        if (context.get('candidate_sha256') != canonical_hash(plain(candidate))
                or context.get('fit_input_sha256') != snapshot['inputs_sha256']
                or selected_run.get('input_sha256') != run['input_sha256']
                or canonical_hash(plain(selected_run.get('draft'))) != run['input_sha256']
                or selected_run['arguments'].get('backend') != snapshot['inputs']['backend']
                or selected_run['arguments'].get('variables') != snapshot['inputs']['variables']
                or canonical_hash(selected_run['arguments'].get('experiments')) != canonical_hash(snapshot['inputs']['experiments'])):
            raise DetailIdentityError('Detail attempt was submitted against different candidate inputs')
        active_state, error = _status(owner, selected_run)
        if active_state in TERMINAL:
            if selected_run.get('retention_complete'):
                has_result = bool(selected_run.get('retained_result'))
            else:
                has_result = bool(owner.manager.status(attempt_job_id).get('result_refs'))
            # A hash/array/reader failure is corruption, never missing detail.
            # Queued cancellation or preflight failure has a receipt but no result.
            detail = owner.result(document_id, attempt_job_id) if has_result else None
            if detail is None and active_state in {'SUCCEEDED', 'PARTIAL_FAILURE'}:
                raise DetailIdentityError('Terminal successful detail receipt has no retained result')
            if detail is not None:
                if (detail.get('kind') != 'candidate_detail' or detail.get('schema') != SCHEMA
                        or detail.get('context') != context):
                    raise DetailIdentityError('Retained detail result and submitted attempt differ')
                trial_ids = [t.get('experiment_id') for t in detail.get('trials', [])]
                if trial_ids != [e['id'] for e in snapshot['inputs']['experiments']]:
                    raise DetailIdentityError('Detail result trial order/count differs from frozen inputs')
                trials = deepcopy(detail['trials'])
                for trial, experiment in zip(trials, snapshot['inputs']['experiments']):
                    _validate_trial(trial, experiment)
            else:
                trials = deepcopy(selected_run['arguments'].get('retained_trials', []))
                retained = {t['experiment_id']: t for t in trials}
                trials = [retained.get(e['id']) or _unavailable(e, status=active_state,
                          origin={'kind': 'detail_eval', 'attempt_id': context['attempt_id']})
                          for e in snapshot['inputs']['experiments']]
        else:
            retained = {t['experiment_id']: t for t in selected_run['arguments'].get('retained_trials', [])}
            trials = [deepcopy(retained.get(e['id'])) or _unavailable(e, status=active_state,
                      origin={'kind': 'detail_eval', 'attempt_id': context['attempt_id']})
                      for e in snapshot['inputs']['experiments']]
    missing = [t['experiment_id'] for t in trials if t['retention'] not in AVAILABLE]
    pending = [a for a in attempts if a['state'] not in TERMINAL]
    latest = attempts[-1]['job_id'] if attempts else None
    # Attempts form a linear continuation. To retry missing trials, the user
    # explicitly opens the latest receipt. Earlier views never hide later detail
    # and cannot redispatch a trial whose output is already retained there.
    current_attempt = not attempts or attempt_job_id == latest
    return plain(dict(schema=SCHEMA, source=reference, candidate=candidate,
        session_id=document['session_id'], generation=document['generation'], dirty=document.get('dirty', False),
        original_plan=deepcopy(run['draft']), fit_input=snapshot, trials=trials,
        attempts=attempts, attempt_job_id=attempt_job_id, attempt_state=active_state,
        missing_experiments=missing, can_detail_eval=bool(missing) and not pending and current_attempt,
        latest_attempt_job_id=latest,
        detail_eval_blocked=('ACTIVE_OR_UNKNOWN_ATTEMPT' if pending else 'SELECT_LATEST_ATTEMPT'
            if not current_attempt else 'ALL_DETAIL_RETAINED' if not missing else None),
        candidates=[{k: deepcopy(r.get(k)) for k in ('candidate_id', 'values', 'execution_status', 'objective', 'failure_reason')}
                    for r in result.get('candidates', [])],
        engineering_release='NOT_RELEASED'))


def prepare_detail_arguments(owner, source: dict, candidate_id: str, *, base_attempt_job_id=None, attempt_id=None) -> dict:
    """Build a new bounded execution from owner-verified history, never UI values."""
    view = read_candidate_detail(owner, source['document_id'], source['job_id'], candidate_id,
                                 source=source, attempt_job_id=base_attempt_job_id)
    if not view['can_detail_eval']:
        raise ValueError('No missing detail, or select the latest completed detail attempt before continuing')
    inputs = view['fit_input']['inputs']
    original_execution = inputs.get('execution', {})
    execution = {key: original_execution[key] for key in ('threads', 'memory_mb') if key in original_execution}
    execution.update(mode='serial', workers=1, on_failure='continue', max_evaluations=len(view['missing_experiments']))
    return plain(dict(backend=inputs['backend'], variables=inputs['variables'], experiments=inputs['experiments'],
        execution=execution, retained_trials=[t for t in view['trials'] if t['retention'] in AVAILABLE],
        context=dict(source=deepcopy(source), candidate_id=candidate_id,
            candidate_sha256=canonical_hash(view['candidate']), candidate_values=view['candidate']['values'],
            source_candidate_status=view['candidate'].get('execution_status', 'UNKNOWN'),
            source_candidate_failure=view['candidate'].get('failure_reason'),
            fit_input_sha256=view['fit_input']['inputs_sha256'],
            base_attempt_job_id=base_attempt_job_id, attempt_id=check_id(attempt_id or 'A'+uuid.uuid4().hex),
            requested_experiments=view['missing_experiments'], budget_evaluations=len(view['missing_experiments']))))


def validate_detail_arguments(owner, arguments: dict, *, allow_active=False) -> None:
    """Service/queued-execution admission: reject caller-supplied replacement inputs."""
    context = arguments.get('context', {})
    source = context.get('source', {})
    # Reconstruct without considering the new run itself an outstanding request.
    view = read_candidate_detail(owner, source.get('document_id'), source.get('job_id'), context.get('candidate_id'),
                                 source=source, attempt_job_id=context.get('base_attempt_job_id'))
    inputs = view['fit_input']['inputs']
    required = {t['experiment_id'] for t in view['trials'] if t['retention'] not in AVAILABLE}
    if (set(arguments) != {'backend', 'variables', 'experiments', 'execution', 'retained_trials', 'context'}
            or arguments['backend'] != inputs['backend'] or arguments['variables'] != inputs['variables']
            or canonical_hash(arguments['experiments']) != canonical_hash(inputs['experiments'])
            or context.get('candidate_sha256') != canonical_hash(view['candidate'])
            or context.get('candidate_values') != view['candidate']['values']
            or context.get('fit_input_sha256') != view['fit_input']['inputs_sha256']
            or context.get('source_candidate_status') != view['candidate'].get('execution_status', 'UNKNOWN')
            or context.get('source_candidate_failure') != view['candidate'].get('failure_reason')
            or context.get('requested_experiments') != [e['id'] for e in inputs['experiments'] if e['id'] in required]
            or context.get('budget_evaluations') != len(required)
            or arguments.get('retained_trials') != [t for t in view['trials'] if t['retention'] in AVAILABLE]):
        raise DetailIdentityError('Detail arguments differ from the frozen original candidate / missing trials')
    if set(context) != {'source', 'candidate_id', 'candidate_sha256', 'candidate_values',
            'source_candidate_status', 'source_candidate_failure', 'fit_input_sha256',
            'base_attempt_job_id', 'attempt_id', 'requested_experiments', 'budget_evaluations'}:
        raise DetailIdentityError('Unknown or missing detail attempt context fields')
    check_id(context.get('attempt_id'))
    expected_execution = {key: inputs.get('execution', {})[key] for key in ('threads', 'memory_mb') if key in inputs.get('execution', {})}
    expected_execution.update(mode='serial', workers=1, on_failure='continue', max_evaluations=len(required))
    if arguments['execution'] != expected_execution or not required:
        raise DetailIdentityError('Detail execution budget / resources differ from the explicit request')
    if not allow_active and not view['can_detail_eval']:
        raise ValueError('A detail attempt is already active for this candidate')


def evaluate_candidate_detail(evaluator_or_factory, variables: list[dict], experiments: list[dict], *,
                              context: dict, retained_trials=None, execution=None) -> dict:
    """One new attempt. Each trial gets its own prepared lifetime and raw result.

    This is deliberately not fit_model: no optimizer or new coefficient search.
    Existing numerical preparation, evaluation, residual and cancellation rules
    are reused. Successful completed trials survive another trial's failure.
    """
    from .numerical import (_variables, _candidates, _Evaluators, _Budget, _execution,
                            StudyCancelled, EvaluationBudgetExceeded)
    from .execution_control import ExecutionCancelled, ExecutionCleanupFailed, check_cancelled
    variables = _variables(variables)
    values = deepcopy(context['candidate_values'])
    _candidates([{'candidate_id': context['candidate_id'], 'values': values}], variables)
    experiments = [experiment_snapshot(e) for e in experiments]
    requested = context['requested_experiments']
    if (len(set(requested)) != len(requested) or not set(requested) <= {e['id'] for e in experiments}
            or not requested or context['budget_evaluations'] != len(requested)):
        raise DetailIdentityError('Detail attempt requires an exact nonempty missing-trial list')
    options = _execution(execution)
    if options['mode'] != 'serial' or options['workers'] != 1 or options.get('max_evaluations') != len(requested):
        raise ValueError('Detail evaluation uses one serial worker and one budget slot per missing trial')
    retained = {t['experiment_id']: deepcopy(t) for t in (retained_trials or [])}
    if len(retained) != len(retained_trials or []) or set(retained) != {e['id'] for e in experiments} - set(requested):
        raise DetailIdentityError('Every trial must be either explicitly requested or exactly retained')
    budget = _Budget(options['max_evaluations'])
    trials, cancelled, model_calls = [], False, 0
    origin = {'kind': 'detail_eval', 'attempt_id': context['attempt_id']}

    def cancel_check():
        try:
            check_cancelled()
        except ExecutionCancelled:
            return True
        return bool(options.get('cancelled') and options['cancelled']())

    for experiment in experiments:
        identifier = experiment['id']
        if identifier in retained:
            _validate_trial(retained[identifier], experiment)
            trials.append(retained[identifier])
            continue
        if cancelled or cancel_check():
            cancelled = True
            trials.append(_unavailable(experiment, reason='NOT_EVALUATED', status='CANCELLED', origin=origin))
            continue
        try:
            with _Evaluators(evaluator_or_factory, [experiment.get('settings', {})], options, budget=budget) as models:
                evaluation = models.one(deepcopy(values))[0]
                model_calls += models.model_calls
            trial = trial_detail(experiment, evaluation, origin=origin)
            if evaluation.get('execution_status') == 'CANCELLED':
                cancelled = True
            trials.append(trial)
        except ExecutionCleanupFailed:
            raise  # never seal mutable/unreaped native outputs as a finished run
        except (StudyCancelled, ExecutionCancelled):
            cancelled = True
            trials.append(_unavailable(experiment, reason='NOT_EVALUATED', status='CANCELLED', origin=origin))
        except EvaluationBudgetExceeded as error:
            trials.append(trial_detail(experiment, {'execution_status': 'REJECTED', 'responses': {},
                'diagnostics': {'failure_reason': str(error)}}, origin=origin))
        except Exception as error:
            # A prepare/close failure is also an actual failed trial with its
            # original protocol and exception, not an absent successful curve.
            trials.append(trial_detail(experiment, {'execution_status': 'FAILED', 'responses': {},
                'diagnostics': {'failure_reason': f'{type(error).__name__}: {error}', 'phase': 'PREPARE_OR_CLOSE'}}, origin=origin))
    cancelled = cancelled or cancel_check()
    successful = sum(t['execution_status'] == 'SUCCEEDED' for t in trials)
    status = ('CANCELLED' if cancelled else 'SUCCEEDED' if successful == len(trials)
              else 'PARTIAL_FAILURE' if successful else 'FAILED')
    return plain(dict(kind='candidate_detail', schema=SCHEMA, context=deepcopy(context),
        execution_status=status, trials=trials, timing={'model_calls': model_calls, 'budget_used': budget.used},
        optimization_performed=False, engineering_release='NOT_RELEASED'))


def table_rows(view: dict, experiment_id: str) -> list[dict]:
    """One source for the table and curves. No alignment or evaluation on read."""
    experiments = view['fit_input']['inputs']['experiments']
    experiment = next((e for e in experiments if e['id'] == experiment_id), None)
    trial = next((t for t in view['trials'] if t['experiment_id'] == experiment_id), None)
    if experiment is None or trial is None:
        raise DetailIdentityError('Choose a trial from this candidate view')
    _validate_trial(trial, experiment)
    observation = experiment['observations']
    if observation['kind'] == 'event':
        curve = trial.get('curve') or {}
        prediction = curve.get('prediction') if isinstance(curve.get('prediction'), dict) else {}
        prediction = prediction or {}
        observed_value, predicted_value = observation.get('value'), prediction.get('value')
        difference = (predicted_value-observed_value
            if observation.get('state') == prediction.get('state') == 'OCCURRED'
            and observed_value is not None and predicted_value is not None else None)
        return [dict(candidate_id=view['candidate']['candidate_id'], experiment_id=experiment_id,
            attempt_job_id=view.get('attempt_job_id'), role=experiment['role'], index=0,
            source_row=None, axis=None, axis_name=None, axis_unit=None, unit=observation['unit'],
            observation=observed_value, observation_state=observation.get('state'),
            prediction=predicted_value, prediction_state=prediction.get('state'),
            included=bool(experiment['mask'][0]), observation_mask=observation.get('mask'),
            weight=experiment['weight'], scale=experiment['scale'], deformation_gradient=None,
            raw_residual=difference, weighted_residual=(curve.get('residual') or [None])[0],
            status=trial['execution_status'], retention=trial['retention'])]
    observed = observation['value'] if isinstance(observation['value'], list) else [observation['value']]
    count = len(observed)
    source_rows = observation.get('source_rows')
    from .numerical_fit_lineage import validate_lineage_fields
    validate_lineage_fields(observation, count=count)
    if source_rows is not None and (not isinstance(source_rows, list) or len(source_rows) != count
            or not observation.get('sample_ids') and len(set(source_rows)) != count):
        raise DetailIdentityError('Retained source_rows length / uniqueness differs from observations')
    mask = experiment['mask']
    curve = trial.get('curve') or {}
    prediction = curve.get('prediction')
    if prediction is not None and (not isinstance(prediction, list) or len(prediction) != count):
        raise DetailIdentityError('Retained prediction length differs from original observation count')
    residual = curve.get('residual')
    if residual is not None and (not isinstance(residual, list) or len(residual) != sum(mask)):
        raise DetailIdentityError('Retained packed residual length differs from the fixed fit mask')
    observation_mask = observation.get('mask')
    if observation_mask is not None and (not isinstance(observation_mask, list) or len(observation_mask) != count):
        raise DetailIdentityError('Observation mask count differs from frozen observations')
    residual_iter = iter(residual or [])
    axes = observation.get('axes', [])
    axis = axes[0]['values'] if axes else [None] * count
    settings = experiment.get('settings', {})
    times, gradients = settings.get('time', []), settings.get('deformation_gradient', [])
    gradients_at_time = dict(zip(times, gradients)) if len(times) == len(gradients) else {}
    result = []
    for index, observed_value in enumerate(observed):
        predicted = prediction[index] if prediction is not None else None
        used = bool(mask[index])
        from .data_processing_consumer import candidate_sample_metadata
        from .finite_measure_prediction import row_metadata
        result.append(dict(**candidate_sample_metadata(experiment, index),
            **row_metadata(curve, axis[index], axes[0]['unit'] if axes else None),
            candidate_id=view['candidate']['candidate_id'], experiment_id=experiment_id,
            attempt_job_id=view.get('attempt_job_id'), role=experiment['role'], index=index,
            source_row=source_rows[index] if source_rows is not None else None,
            sample_id=(observation['sample_ids'][index] if observation.get('sample_ids') is not None else None),
            contributors=(deepcopy(observation['contributors'][index]) if observation.get('contributors') is not None else None),
            operation_refs=deepcopy(observation.get('operation_refs')),
            operation_metadata=deepcopy(observation.get('operation_metadata')),
            lineage_extensions=deepcopy(observation.get('extensions')),
            axis=axis[index], axis_name=axes[0]['name'] if axes else None,
            axis_unit=axes[0]['unit'] if axes else None, unit=observation['unit'],
            observation=observed_value, prediction=predicted,
            raw_residual=predicted-observed_value if used and predicted is not None and observed_value is not None else None,
            weighted_residual=next(residual_iter, None) if used else None,
            included=used, observation_mask=observation_mask[index] if observation_mask is not None else None,
            weight=experiment['weight'], scale=experiment['scale'],
            deformation_gradient=(deepcopy(gradients_at_time.get(axis[index])) if axes and axes[0].get('name') == 'time'
                                  and axes[0].get('unit') == settings.get('time_unit') else None),
            status=trial['execution_status'], retention=trial['retention']))
    return result


def compare_candidate_details(left: dict, right: dict, experiment_id: str) -> dict:
    """Compare retained values only; incomplete candidates receive no ranking."""
    if left['source'] != right['source'] or left['fit_input']['inputs_sha256'] != right['fit_input']['inputs_sha256']:
        raise DetailIdentityError('Candidate comparison requires the same original fit input and result')
    rows_left, rows_right = table_rows(left, experiment_id), table_rows(right, experiment_id)
    if len(rows_left) != len(rows_right):
        raise DetailIdentityError('Candidate comparison row counts differ')
    rows = []
    for a, b in zip(rows_left, rows_right):
        if any(a.get(key) != b.get(key) for key in ('source_row', 'sample_id', 'contributors', 'operation_refs', 'operation_metadata',
                    'lineage_extensions', 'axis', 'axis_unit', 'unit', 'observation', 'included',
                    'observation_mask', 'weight', 'scale', 'deformation_gradient', 'role')):
            raise DetailIdentityError('Candidate comparison source/observation/role identities differ')
        rows.append(dict(source_row=a.get('source_row'), sample_id=a.get('sample_id'),
            contributors=deepcopy(a.get('contributors')), operation_refs=deepcopy(a.get('operation_refs')),
            operation_metadata=deepcopy(a.get('operation_metadata')),
            axis=a.get('axis'), axis_unit=a.get('axis_unit'), observation=a['observation'],
            unit=a['unit'], included=a['included'], left_prediction=a['prediction'], right_prediction=b['prediction'],
            left_residual=a['weighted_residual'], right_residual=b['weighted_residual']))
    from .numerical_candidate_evidence import candidate_detail_readiness
    readiness = {name: candidate_detail_readiness(view, required_experiments=[experiment_id])
                 for name, view in (('left', left), ('right', right))}
    return dict(source=deepcopy(left['source']), inputs_sha256=left['fit_input']['inputs_sha256'],
        left_attempt_job_id=left.get('attempt_job_id'), right_attempt_job_id=right.get('attempt_job_id'),
        experiment_id=experiment_id, left_candidate_id=left['candidate']['candidate_id'],
        right_candidate_id=right['candidate']['candidate_id'], rows=rows, ranking='NOT_PERFORMED',
        completion='READ_ONLY_NOT_A_SUCCESS_JUDGMENT', success_judgment_permitted=False,
        readiness=readiness, engineering_release='NOT_RELEASED')


class CandidateDetailMixin:
    """Numerical owner extension; shares existing runs, saves and command receipts."""
    @property
    def operations(self):
        from .numerical_candidate_evidence import EVIDENCE_COMMANDS
        return super().operations | {COMMAND} | EVIDENCE_COMMANDS

    @staticmethod
    def _fingerprint(document):
        from .material_document import MaterialDocuments
        base = MaterialDocuments._fingerprint(document)
        return canonical_hash({'base': base, 'candidate_evidence': document['candidate_evidence']}) if document.get('candidate_evidence') else base

    def _public(self, document):
        from .portable_project_execution import public_execution
        return public_execution(self, super()._public(document))

    def _retain_inputs(self, saved, folder):
        from .numerical_candidate_evidence import _record_capture_publication
        _record_capture_publication(self, saved, folder)
        super()._retain_inputs(saved, folder)
        from .numerical_candidate_evidence import retain_evidence_inputs
        retain_evidence_inputs(self, saved, folder)
        from .portable_project_execution import retain_execution_inputs
        retain_execution_inputs(self, saved, folder)

    def command(self, identifier, operation, arguments, *, session_id, expected_generation, command_id=None):
        from .numerical_candidate_evidence import EVIDENCE_COMMANDS, evidence_command
        if operation in EVIDENCE_COMMANDS:
            return evidence_command(self, identifier, operation, arguments, session_id=session_id,
                                    expected_generation=expected_generation, command_id=command_id)
        if operation != COMMAND:
            return super().command(identifier, operation, arguments, session_id=session_id,
                                   expected_generation=expected_generation, command_id=command_id)
        if (not isinstance(arguments, dict) or not {'source', 'candidate_id'} <= set(arguments)
                or set(arguments) - {'source', 'candidate_id', 'base_attempt_job_id'}):
            raise ValueError('Detail evaluation takes an exact source/candidate and optional base attempt, not replacement inputs')
        if session_id != self.session_id or type(expected_generation) is not int or expected_generation < 0:
            raise ValueError('Detail command requires the current owner session and exact generation')
        if not isinstance(arguments['source'], dict) or arguments['source'].get('document_id') != identifier:
            raise DetailIdentityError('Source fit belongs to another Numerical owner')
        command_id = check_id(command_id or 'C'+uuid.uuid4().hex)
        signature = canonical_hash(dict(document_id=identifier, operation=operation, arguments=arguments,
                                        session_id=session_id, expected_generation=expected_generation))
        with self._lock(identifier):
            self.read(identifier)
            document = deepcopy(self._documents[identifier])
            receipt = self._folder(identifier)/'commands'/(command_id+'.json')
            if receipt.exists():
                prior = load_json(receipt)
                if prior['request_hash'] != signature:
                    raise ValueError('command_id conflicts with an earlier request')
                if 'response' not in prior:
                    raise ValueError('Previous detail submission is unconfirmed; reread before issuing another command')
                return prior['response']
            if document['generation'] != expected_generation:
                raise ValueError('Document generation changed; reread before applying')
            submitted = prepare_detail_arguments(self, arguments['source'], arguments['candidate_id'],
                                                  base_attempt_job_id=arguments.get('base_attempt_job_id'))
            original = next(r for r in document['runs'] if r['job_id'] == arguments['source']['job_id'])
            prior = dict(request_hash=signature, operation=COMMAND, state='APPLYING',
                submitted_operation=OPERATION, submitted_arguments=submitted,
                input=deepcopy(original['draft']), input_generation=original['input_generation'],
                input_revision=original['input_revision'], session_id=session_id)
            save_json(receipt, prior)
            job = self.submit(OPERATION, submitted, request_id='numerical-detail:'+identifier+':'+command_id)
            document['runs'].append(self._run_record(job, prior['input'], prior['input_generation'],
                                                    prior['input_revision'], session_id))
            self._persist_draft(document)
            self._documents[identifier] = document
            response = {'document': self._public(document), 'job': job, 'command_id': command_id}
            save_json(receipt, {**prior, 'response': response})
            return response

    def _recover_evaluations(self, document):
        super()._recover_evaluations(document)
        for receipt in (self._folder(document['id'])/'commands').glob('*.json'):
            prior = load_json(receipt)
            if prior.get('operation') != COMMAND or 'response' in prior:
                continue
            request_id = 'numerical-detail:'+document['id']+':'+receipt.stem
            job = next((j for j in self.manager.list() if j.get('request_id') == request_id), None)
            if job is None:
                continue  # reading never submits/retries a job
            if job['operation'] != OPERATION or job['arguments'] != prior['submitted_arguments']:
                raise DetailIdentityError('Recovered detail job differs from the prepared command receipt')
            if not any(r['job_id'] == job['id'] for r in document['runs']):
                record = self._run_record(job, prior['input'], prior['input_generation'],
                                          prior['input_revision'], prior['session_id'])
                record['recovered_after_response_loss'] = True
                document['runs'].append(record)
            self._persist_draft(document)
            prior['response'] = dict(document=self._public(document), job=job, command_id=receipt.stem,
                                     recovered_after_response_loss=True)
            save_json(receipt, prior)


def client_read_candidate_detail(client, document_id, job_id, candidate_id, **kwargs):
    """Use existing HTTP reads; no new route, second controller or file copying."""
    from types import SimpleNamespace
    owner = SimpleNamespace(read=client.document_read, result=client.document_result,
                            manager=SimpleNamespace(status=client.status), _portable_client_read=True)
    return read_candidate_detail(owner, document_id, job_id, candidate_id, **kwargs)
