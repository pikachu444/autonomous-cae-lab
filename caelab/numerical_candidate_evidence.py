"""C03 evidence gates for one original fit candidate and one explicit detail view.

Readers never submit work. Capturing is an explicit Numerical owner command:
its existing revision writer publishes inputs, jobs, results and this snapshot
before a completion gate can succeed. A working JSON or a GUI readiness flag is
not authority. No coordinator, database, provider or numerical engine is added.
"""
from __future__ import annotations

from copy import deepcopy
from contextvars import ContextVar
import json
import math
import re
from types import SimpleNamespace
import uuid

from .storage import canonical_hash, check_id, load_json, save_json
from .numerical_candidate_detail import (
    DetailIdentityError, SCHEMA, OPERATION, TERMINAL,
    _source, _status, _validate_trial, plain, read_candidate_detail,
    table_rows, trial_detail, validate_detail_arguments,
)
from .numerical_fit_lineage import lineage_assessment

EVIDENCE_SCHEMA = 'caelab.candidate-evidence.v1'
EVIDENCE_KIND = 'numerical_candidate_evidence'
CAPTURE = 'numerical.evidence.capture'
READ = 'numerical.evidence.read'
COMPARE = 'numerical.evidence.compare'
ADOPTION_PREVIEW = 'numerical.evidence.adoption_preview'
EVIDENCE_COMMANDS = {CAPTURE, READ, COMPARE, ADOPTION_PREVIEW}
SUCCESS = 'success_judgment'
FAILURE = 'failure_diagnostic'
CONSUMERS = {'read', 'comparison', 'adoption', 'success_report', 'failure_report'}
FAILURE_STATES = {'FAILED', 'CANCELLED', 'PARTIAL_FAILURE', 'REJECTED', 'INTERRUPTED'}
_UNSET = object()
_CAPTURE_SCOPE_SCHEMA = 'caelab.candidate-capture-scope.v1'
# Only the existing revision writer called by CAPTURE receives this context.
# A later ordinary save must NOT be mistaken for completion of a failed CAPTURE.
_CAPTURE_SAVE = ContextVar('caelab_candidate_capture_save', default=None)
_PUBLICATIONS = '_candidate_evidence_publications'


class DetailEvidenceBlocked(ValueError):
    """Readable history lacks the evidence required for this declared action."""
    def __init__(self, message, readiness=None):
        super().__init__(message)
        self.readiness = deepcopy(readiness)


class DetailEvidenceConflict(ValueError):
    """A retry no longer owns the exact state it was authorized to publish."""
    code = 'STALE_CAPTURE'

    def __init__(self, message):
        super().__init__('STALE_CAPTURE: ' + message)


def _scope(view, required_experiments):
    experiments = view['fit_input']['inputs']['experiments']
    ids = [e['id'] for e in experiments]
    selected = ids if required_experiments is None else required_experiments
    if (not isinstance(selected, list) or not selected or
            any(not isinstance(item, str) for item in selected) or
            len(set(selected)) != len(selected) or set(selected) - set(ids)):
        raise DetailIdentityError('Choose nonempty distinct experiments from this exact original fit')
    return [{'experiment_id': e['id'], 'response': e['response'], 'role': e['role'],
             'unit': e['observations']['unit'], 'scale_unit': e['observations']['unit'],
             'experiment_sha256': canonical_hash(e), 'inclusion': 'FROZEN_FIT_MASK'}
            for e in experiments if e['id'] in selected]


def _trial_issue(trial, experiment):
    """Validate retained actual output and its existing-engine curve, not a model call.

    Recomputing the *validation* curve from preserved bytes does not replace the
    preserved curve. Hash inequality is corruption. Excluded nulls remain null;
    a retained event non-occurrence is not forced into a made-up numeric zero.
    """
    _validate_trial(trial, experiment)
    if trial.get('retention') != 'RETAINED':
        return 'DETAIL_' + str(trial.get('retention', 'UNKNOWN'))
    if trial.get('execution_status') != 'SUCCEEDED' or trial.get('evaluation_status') != 'SUCCEEDED':
        return 'TRIAL_' + str(trial.get('execution_status', 'UNKNOWN'))
    raw, curve = trial.get('raw_evaluation'), trial.get('curve')
    if not isinstance(raw, dict) or not isinstance(curve, dict):
        return 'RAW_OR_CURVE_NOT_RETAINED'
    if raw.get('execution_status') != 'SUCCEEDED' or curve.get('execution_status') != 'SUCCEEDED':
        return 'RAW_OR_CURVE_NOT_SUCCEEDED'
    checked = trial_detail(experiment, raw, origin=trial.get('origin'))
    if checked['execution_status'] != 'SUCCEEDED':
        raise DetailIdentityError('Successful trial has invalid raw response / units / support: ' + experiment['id'])
    if canonical_hash(plain(checked['curve'])) != canonical_hash(plain(curve)):
        raise DetailIdentityError('Retained raw response and curve/residual evidence differ: ' + experiment['id'])
    # The original engine owns event comparability (including declared absence
    # penalties). For curves/scalars every included sample must be actual.
    probe = {'candidate': {'candidate_id': 'check'}, 'fit_input': {'inputs': {'experiments': [experiment]}},
             'trials': [trial], 'attempt_job_id': None}
    rows = table_rows(probe, experiment['id'])
    for row in rows:
        if not row['included']:
            continue
        fields = ['weighted_residual'] if experiment['observations']['kind'] == 'event' else [
            'observation', 'prediction', 'raw_residual', 'weighted_residual']
        if any(type(row.get(key)) not in (int, float) or not math.isfinite(row[key]) for key in fields):
            return 'REQUIRED_SAMPLE_NOT_FINITE'
    return None


def candidate_detail_readiness(view, *, required_experiments=None, purpose=SUCCESS):
    """Read-only readiness. Even READY_TO_PRESERVE is NOT a completion permit.

    Adoption always requires all frozen fit and holdout experiments. Comparison
    and reporting may explicitly select a subset; the subset is in the immutable
    scope and is never described as completion of the whole candidate/holdout.
    """
    if purpose not in {SUCCESS, FAILURE}:
        raise ValueError('Declare success_judgment or failure_diagnostic; reads need neither gate')
    scope = _scope(view, required_experiments)
    experiments = {e['id']: e for e in view['fit_input']['inputs']['experiments']}
    trials = {t['experiment_id']: t for t in view['trials']}
    issues, trial_states = [], []
    for entry in scope:
        trial = trials.get(entry['experiment_id'])
        if trial is None:
            raise DetailIdentityError('Selected required trial is missing from this view')
        issue = _trial_issue(trial, experiments[entry['experiment_id']])
        trial_states.append({**entry, 'retention': trial['retention'], 'execution_status': trial['execution_status'],
                             'issue': issue})
        if issue:
            issues.append({'experiment_id': entry['experiment_id'], 'code': issue})
    candidate = view['candidate']
    failure_records = []
    if candidate.get('execution_status') in FAILURE_STATES:
        failure_records.append({'kind': 'original_candidate', 'state': candidate['execution_status'],
                                'failure_reason': deepcopy(candidate.get('failure_reason'))})
    if view.get('attempt_state') in FAILURE_STATES:
        failure_records.append({'kind': 'selected_detail_attempt', 'job_id': view.get('attempt_job_id'),
                                'state': view['attempt_state']})
    for item in trial_states:
        trial = trials[item['experiment_id']]
        if trial.get('execution_status') in FAILURE_STATES:
            failure_records.append({'kind': 'trial', 'experiment_id': trial['experiment_id'],
                'state': trial['execution_status'], 'retention': trial['retention'],
                'failure_reason': deepcopy((trial.get('curve') or {}).get('failure_reason'))})
    if purpose == SUCCESS:
        if candidate.get('execution_status') != 'SUCCEEDED' or candidate.get('prediction_status'):
            issues.append({'code': 'ORIGINAL_CANDIDATE_NOT_SUCCEEDED'})
        if type(candidate.get('objective')) not in (int, float) or not math.isfinite(candidate['objective']):
            issues.append({'code': 'ORIGINAL_OBJECTIVE_NOT_FINITE'})
        # A successful prefix of a stopped/partially failed selected attempt is
        # readable, but cannot be promoted into a completed success judgment.
        if view.get('attempt_job_id') is not None and view.get('attempt_state') != 'SUCCEEDED':
            issues.append({'code': 'SELECTED_ATTEMPT_NOT_SUCCEEDED'})
        ready = not issues
    else:
        ready = bool(failure_records)
        if not ready:
            issues.append({'code': 'NO_RECORDED_FAILURE; MISSING_DETAIL_IS_NOT_A_FAILURE'})
    return {'purpose': purpose, 'state': 'READY_TO_PRESERVE' if ready else 'BLOCKED',
            'ready_to_preserve': ready, 'success_judgment_permitted': False,
            'failure_diagnostic_permitted': False, 'preservation': 'NOT_VERIFIED',
            'scope': scope, 'trials': trial_states, 'issues': issues,
            'failure_records': failure_records,
            'holdout_scope': [e['experiment_id'] for e in scope if e['role'] == 'holdout'],
            'holdout_acceptance': 'NOT_ASSESSED', 'engineering_release': 'NOT_RELEASED',
            'lineage': lineage_assessment(list(experiments.values()))}


def _run_record(owner, run, result, *, verified_result_sha256=None):
    state, error = _status(owner, run)
    if state not in TERMINAL:
        raise DetailEvidenceBlocked('The original fit and selected attempt chain must be terminal; UNKNOWN is not success')
    return {'job_id': run['job_id'], 'operation': run['operation'],
            'input_revision': run['input_revision'], 'input_sha256': run['input_sha256'],
            'arguments_sha256': canonical_hash(plain(run['arguments'])),
            'state': state, 'error': plain(error),
            'result_sha256': (verified_result_sha256 or canonical_hash(plain(result))) if result is not None else None}


def _attempt_result(owner, document_id, run):
    state, _ = _status(owner, run)
    if state not in TERMINAL:
        raise DetailEvidenceBlocked('Selected detail attempt is not terminal')
    has_result = (bool(run.get('retained_result')) if run.get('retention_complete')
                  else bool(owner.manager.status(run['job_id']).get('result_refs')))
    return owner.result(document_id, run['job_id']) if has_result else None


def _verified_chain(owner, document, source, candidate, selected):
    """Validate exact ancestry; neither another candidate nor 'latest' is a parent."""
    by_job = {r['job_id']: r for r in document['runs']}
    chain, seen = [], set()
    while selected is not None:
        check_id(selected)
        if selected in seen or selected not in by_job:
            raise DetailIdentityError('Detail ancestry is cyclic or belongs to a different job')
        seen.add(selected)
        run = by_job[selected]
        context = run.get('arguments', {}).get('context', {})
        if (run.get('operation') != OPERATION or context.get('source') != source
                or context.get('candidate_id') != candidate['candidate_id']):
            raise DetailIdentityError('Detail ancestry belongs to a different original candidate / job')
        chain.append(run)
        selected = context.get('base_attempt_job_id')
    chain.reverse()
    evidence = []
    for run in chain:
        validate_detail_arguments(owner, run['arguments'], allow_active=True)
        context = run['arguments']['context']
        result = _attempt_result(owner, source['document_id'], run)
        receipt = _run_record(owner, run, result)
        view = read_candidate_detail(owner, source['document_id'], source['job_id'], candidate['candidate_id'],
                                     source=source, attempt_job_id=run['job_id'])
        if result is not None:
            if (result.get('execution_status') != receipt['state'] or result.get('context') != context
                    or result.get('kind') != 'candidate_detail' or result.get('schema') != SCHEMA):
                raise DetailIdentityError('Detail result status/context differs from the exact job receipt')
        elif receipt['state'] == 'SUCCEEDED':
            raise DetailIdentityError('Succeeded detail receipt has no retained result')
        inherited = {t['experiment_id']: t for t in run['arguments']['retained_trials']}
        for trial in view['trials']:
            identifier = trial['experiment_id']
            if identifier in inherited:
                if canonical_hash(trial) != canonical_hash(inherited[identifier]):
                    raise DetailIdentityError('Detail result substituted an inherited trial from another attempt')
            elif trial.get('origin') != {'kind': 'detail_eval', 'attempt_id': context['attempt_id']}:
                raise DetailIdentityError('New trial origin differs from the selected detail attempt')
        evidence.append({'record': receipt, 'attempt_id': context['attempt_id'],
                         'context': deepcopy(context), 'trials': deepcopy(view['trials'])})
    return evidence


def prepare_candidate_evidence(owner, source, candidate_id, *, attempt_job_id=None,
                               required_experiments=None, purpose=SUCCESS):
    """Prepare from owner-verified history. No write, save, evaluator or submission."""
    from .portable_project_execution import prepare_evidence
    portable = prepare_evidence(owner, source, candidate_id, attempt_job_id=attempt_job_id,
        required_experiments=required_experiments, purpose=purpose)
    if portable is not None:
        return portable
    document, run, result, exact = _source(owner, source['document_id'], source['job_id'], source)
    from .numerical_candidate_detail import _read_verified_candidate_detail
    view = _read_verified_candidate_detail(owner, (document, run, result, exact), candidate_id,
                                          attempt_job_id=attempt_job_id)
    original_record = _run_record(owner, run, result, verified_result_sha256=exact['result_sha256'])
    chain = _verified_chain(owner, document, exact, view['candidate'], attempt_job_id)
    readiness = candidate_detail_readiness(view, required_experiments=required_experiments, purpose=purpose)
    if not readiness['ready_to_preserve']:
        raise DetailEvidenceBlocked('Required selected detail evidence is not ready: ' +
                                    ', '.join(i['code'] for i in readiness['issues']), readiness)
    # Exact trial refs include raw/curve hashes and the result that actually
    # produced them. Inherited original fit outputs never become detail outputs.
    trial_refs = []
    for trial in view['trials']:
        origin = trial.get('origin') or {}
        ref = {'job_id': source['job_id'], 'result_sha256': source['result_sha256'], 'attempt_id': None}
        if origin.get('kind') == 'detail_eval':
            parents = [a for a in chain if a['attempt_id'] == origin.get('attempt_id')]
            if len(parents) != 1:
                raise DetailIdentityError('Trial has no unique producing attempt in the explicit ancestry')
            parent = parents[0]
            actual = next(t for t in parent['trials'] if t['experiment_id'] == trial['experiment_id'])
            if canonical_hash(actual) != canonical_hash(trial):
                raise DetailIdentityError('Trial differs from its producing attempt result')
            ref.update(job_id=parent['record']['job_id'], result_sha256=parent['record']['result_sha256'],
                       attempt_id=parent['attempt_id'], receipt_sha256=canonical_hash(parent['record']))
        elif origin and (origin.get('kind') not in {'fit_candidate', 'fit_final'}
                         or origin.get('candidate_id') != candidate_id):
            raise DetailIdentityError('Retained trial origin belongs to another original candidate')
        if origin.get('kind') == 'fit_candidate' and trial['role'] != 'fit':
            raise DetailIdentityError('Search candidate cannot retroactively own a holdout result')
        trial_refs.append({**ref, 'candidate_id': candidate_id, 'experiment_id': trial['experiment_id'],
            'role': trial['role'], 'experiment_sha256': trial['experiment_sha256'],
            'trial_sha256': canonical_hash(trial),
            'raw_sha256': canonical_hash(trial['raw_evaluation']) if trial.get('raw_evaluation') is not None else None,
            'curve_sha256': canonical_hash(trial['curve']) if trial.get('curve') is not None else None})
    selected = chain[-1] if chain else None
    original_holdout = [deepcopy(c) for c in result.get('curves', []) if c.get('role') == 'holdout']
    # Deliberately no generation, wall-clock, latest attempt or current draft:
    # identical chosen evidence has identical bytes after save/reopen/path move.
    return plain({'schema': EVIDENCE_SCHEMA, 'purpose': purpose, 'source': exact,
        'original_record': original_record, 'original_candidate': view['candidate'],
        'candidate_sha256': canonical_hash(view['candidate']), 'original_plan': view['original_plan'],
        'fit_input': view['fit_input'], 'scope': readiness['scope'],
        'selected_attempt_job_id': attempt_job_id,
        'selected_attempt': deepcopy(selected['record']) if selected else None,
        'attempt_chain': [{k: deepcopy(a[k]) for k in ('record', 'attempt_id', 'context')} for a in chain],
        'trials': view['trials'], 'trial_refs': trial_refs,
        'original_fit_status': result.get('execution_status', 'UNKNOWN'),
        'original_fit_holdout': original_holdout,
        'original_fit_holdout_sha256': canonical_hash(plain(original_holdout)),
        'selected_holdout_refs': [ref for ref in trial_refs if ref['role'] == 'holdout'],
        'holdout_attribution': 'ORIGINAL_FIT_UNCHANGED; selected detail holdout is a separate attempt',
        'readiness': readiness})


def _binding(snapshot):
    return {'source': deepcopy(snapshot['source']), 'candidate_id': snapshot['original_candidate']['candidate_id'],
            'candidate_sha256': snapshot['candidate_sha256'],
            'attempt_job_id': snapshot['selected_attempt_job_id'],
            'attempt_chain_sha256': canonical_hash(snapshot['attempt_chain']),
            'scope_sha256': canonical_hash(snapshot['scope']), 'purpose': snapshot['purpose']}


def evidence_reference(document_id, revision, snapshot, *, owner=None):
    from .portable_project_execution import reference_source
    binding = _binding(snapshot)
    binding['source'] = reference_source(owner, document_id, revision, snapshot['source'])
    digest = canonical_hash(snapshot)
    return {'kind': EVIDENCE_KIND, 'document_id': document_id, 'saved_revision': revision,
            'evidence_id': 'H' + digest, 'snapshot_sha256': digest, **binding}


def validate_evidence_reference(reference):
    keys = {'kind', 'document_id', 'saved_revision', 'evidence_id', 'snapshot_sha256', 'source',
            'candidate_id', 'candidate_sha256', 'attempt_job_id', 'attempt_chain_sha256', 'scope_sha256', 'purpose'}
    if not isinstance(reference, dict) or set(reference) != keys or reference['kind'] != EVIDENCE_KIND:
        raise DetailIdentityError('Choose an exact saved Numerical candidate evidence reference')
    if not isinstance(reference.get('source'), dict) or set(reference['source']) != {
            'document_id', 'job_id', 'input_revision', 'input_sha256', 'result_sha256'}:
        raise DetailIdentityError('Evidence requires the exact original source identity')
    for key in ('document_id', 'job_id', 'input_revision'):
        check_id(reference['source'][key])
    for key in ('input_sha256', 'result_sha256'):
        if not isinstance(reference['source'][key], str) or not re.fullmatch('[0-9a-f]{64}', reference['source'][key]):
            raise DetailIdentityError('Invalid original source hash')
    for key in ('document_id', 'saved_revision', 'evidence_id', 'candidate_id'):
        check_id(reference[key])
    if reference['attempt_job_id'] is not None:
        check_id(reference['attempt_job_id'])
    for key in ('snapshot_sha256', 'candidate_sha256', 'attempt_chain_sha256', 'scope_sha256'):
        if not isinstance(reference[key], str) or not re.fullmatch('[0-9a-f]{64}', reference[key]):
            raise DetailIdentityError('Invalid evidence hash: ' + key)
    if (reference['purpose'] not in {SUCCESS, FAILURE} or reference['evidence_id'] != 'H' + reference['snapshot_sha256']
            or reference['document_id'] != reference['source'].get('document_id')):
        raise DetailIdentityError('Evidence reference identity / purpose differs')


def _saved_owner(owner, document_id, revision):
    """Read the exact saved revision, not working.json or the newest saved pointer."""
    saved = owner._verify_revision(document_id, revision)
    from .connection_graph import is_acknowledged_container
    if is_acknowledged_container(saved):
        raise DetailIdentityError('Acknowledged container is not published candidate evidence; explicitly save with the current owner')
    if saved['id'] != document_id or saved['kind'] != 'numerical':
        raise DetailIdentityError('Evidence belongs to a different owner')
    def read(identifier):
        if identifier != document_id:
            raise DetailIdentityError('Evidence read attempted another owner')
        return deepcopy(saved)
    def result_folder(identifier, job_id):
        if identifier != document_id:
            raise DetailIdentityError('Result belongs to another evidence owner')
        run = next((r for r in saved['runs'] if r['job_id'] == job_id), None)
        if run is None or not run.get('retention_complete') or not run.get('retained_result'):
            raise DetailIdentityError('Saved evidence run does not retain this result')
        original_revision = run['retained_result']['revision']
        owner._verify_revision(document_id, original_revision)
        return owner._folder(document_id) / 'revisions' / check_id(original_revision) / 'results' / check_id(job_id)
    def result(identifier, job_id, **kwargs):
        from .evaluation import read_result
        return read_result(result_folder(identifier,job_id),verify='all',**kwargs)
    return saved, SimpleNamespace(read=read, result=result, manager=None, _portable_storage_owner=owner,
        _verified_candidate_result_location=lambda identifier,job_id:(owner,result_folder(identifier,job_id)))


def resolve_candidate_evidence(owner, reference, *, consumer='read', source=None,
                               candidate_id=None, attempt_job_id=_UNSET):
    """Authority used by Python, CLI/service, adoption, comparison and reporting."""
    if consumer not in CONSUMERS:
        raise ValueError('Declare the actual candidate-evidence consumer')
    validate_evidence_reference(reference)
    document_id, revision = reference['document_id'], reference['saved_revision']
    with owner._lock(document_id):
        saved, historical = _saved_owner(owner, document_id, revision)
        row = next((r for r in saved.get('candidate_evidence', []) if r['id'] == reference['evidence_id']), None)
        if row is None or row['sha256'] != reference['snapshot_sha256']:
            raise DetailIdentityError('Candidate evidence was not published in this exact saved revision')
        path = owner._folder(document_id) / 'revisions' / check_id(revision) / 'candidate_evidence' / (row['id'] + '.json')
        snapshot = load_json(path)
        if canonical_hash(snapshot) != row['sha256'] or evidence_reference(document_id, revision, snapshot, owner=owner) != reference:
            raise DetailIdentityError('Snapshot content / original candidate / selected attempt reference changed')
        if (source is not None and source != reference['source'] or
                candidate_id is not None and candidate_id != snapshot['original_candidate']['candidate_id'] or
                attempt_job_id is not _UNSET and attempt_job_id != snapshot['selected_attempt_job_id']):
            raise DetailIdentityError('Consumer selection differs from the saved source candidate or detail attempt')
        checked = prepare_candidate_evidence(historical, reference['source'], snapshot['original_candidate']['candidate_id'],
            attempt_job_id=snapshot['selected_attempt_job_id'],
            required_experiments=[e['experiment_id'] for e in snapshot['scope']], purpose=snapshot['purpose'])
        if canonical_hash(checked) != row['sha256']:
            raise DetailIdentityError('Saved evidence differs from its exact original results or inputs')
        success = consumer in {'comparison', 'adoption', 'success_report'}
        if success and snapshot['purpose'] != SUCCESS:
            raise DetailEvidenceBlocked('Failure diagnostics cannot authorize a success judgment or adoption')
        if consumer == 'failure_report' and snapshot['purpose'] != FAILURE:
            raise DetailEvidenceBlocked('Failure reporting requires an explicitly preserved failure diagnostic')
        if consumer == 'adoption':
            all_ids = [e['id'] for e in snapshot['fit_input']['inputs']['experiments']]
            if [e['experiment_id'] for e in snapshot['scope']] != all_ids:
                raise DetailEvidenceBlocked('Adoption requires every frozen fit and holdout response, not a comparison subset')
        readiness = deepcopy(snapshot['readiness'])
        readiness.update(preservation='IMMUTABLE_REVISION_VERIFIED', state='EVIDENCE_VERIFIED',
            success_judgment_permitted=success,
            failure_diagnostic_permitted=consumer == 'failure_report')
        return {'reference': deepcopy(reference), 'snapshot': snapshot, 'readiness': readiness}


def require_adoption_evidence(owner, reference, run, result, candidate_id):
    if owner is None or reference is None:
        raise DetailEvidenceBlocked('Preserve the selected original candidate/detail evidence before fit adoption')
    resolved = resolve_candidate_evidence(owner, reference, consumer='adoption', candidate_id=candidate_id)
    snapshot = resolved['snapshot']
    from .portable_project_execution import adoption_run
    run = adoption_run(owner, reference, run)
    if (run.get('job_id') != snapshot['source']['job_id']
            or run.get('input_revision') != snapshot['source']['input_revision']
            or run.get('input_sha256') != snapshot['source']['input_sha256']
            or canonical_hash(plain(run.get('draft'))) != snapshot['source']['input_sha256']
            or canonical_hash(plain(result)) != snapshot['source']['result_sha256']):
        raise DetailIdentityError('Adoption attempted a different original job/result/input')
    return resolved


def candidate_adoption_preview(owner, reference):
    from .numerical_document import adopted_draft
    resolved = resolve_candidate_evidence(owner, reference, consumer='adoption')
    snapshot = resolved['snapshot']
    _, historical = _saved_owner(owner, reference['document_id'], reference['saved_revision'])
    _, run, result, _ = _source(historical, reference['document_id'], snapshot['source']['job_id'], reference['source'])
    return {'proposed_draft': adopted_draft(run, result, reference['candidate_id'],
                evidence_owner=owner, detail_evidence=reference),
            'reference': deepcopy(reference), 'readiness': resolved['readiness']}


def _snapshot_view(snapshot):
    return {'source': snapshot['source'], 'candidate': snapshot['original_candidate'],
            'fit_input': snapshot['fit_input'], 'trials': snapshot['trials'],
            'attempt_job_id': snapshot['selected_attempt_job_id'],
            'attempt_state': (snapshot.get('selected_attempt') or {}).get('state')}


def compare_selected_candidate_evidence(owner, left, right, experiment_id):
    from .numerical_candidate_detail import compare_candidate_details
    a = resolve_candidate_evidence(owner, left, consumer='comparison')
    b = resolve_candidate_evidence(owner, right, consumer='comparison')
    for item in (a, b):
        if experiment_id not in [e['experiment_id'] for e in item['snapshot']['scope']]:
            raise DetailEvidenceBlocked('Compared experiment is outside the preserved evidence scope')
    result = compare_candidate_details(_snapshot_view(a['snapshot']), _snapshot_view(b['snapshot']), experiment_id)
    result.update(completion='EVIDENCE_VERIFIED_COMPARISON', success_judgment_permitted=True,
                  evidence_references={'left': deepcopy(left), 'right': deepcopy(right)},
                  readiness={'left': a['readiness'], 'right': b['readiness']},
                  preservation='IMMUTABLE_REVISION_VERIFIED',
                  holdout_acceptance='NOT_ASSESSED', engineering_release='NOT_RELEASED')
    return result


def candidate_report_payload(owner, reference):
    consumer = 'success_report' if reference.get('purpose') == SUCCESS else 'failure_report'
    resolved = resolve_candidate_evidence(owner, reference, consumer=consumer)
    return {'status': 'AVAILABLE', 'kind': EVIDENCE_KIND, 'reference': deepcopy(reference),
            'report_intent': consumer, 'candidate_evidence': resolved}


def _capture_scope(owner, document, pending):
    """Hash the raw owner, not its public generation/Plan-only fingerprint.

    Runs and saves do not necessarily advance generation. Undo/Redo, input
    revision, saved pointer, undo stacks and previous publication witnesses are
    all in this exact hash. Session identity is deliberately not normalized.
    """
    identifier = document['id']
    manifest = owner._manifest(identifier)
    if (manifest or {}).get('revision') != document['_disk_revision']:
        raise DetailEvidenceConflict('Saved document changed outside the current owner')
    working = load_json(owner._folder(identifier) / 'working.json')
    disk_hash = canonical_hash(working)
    if disk_hash != canonical_hash(document):
        # The existing document.save publishes the revision but deliberately
        # does not refresh working.json. Match its exact cold-open fallback;
        # do not reject that normal first capture, or accept a foreign draft.
        if manifest is None or working.get('saved_revision') == manifest['revision']:
            raise DetailEvidenceConflict('Working state differs from the current owner')
        saved = owner._verify_revision(identifier, manifest['revision'])
        saved.update(session_id=owner.session_id, saved_revision=manifest['revision'],
                     _disk_revision=manifest['revision'], _saved_fingerprint=manifest['fingerprint'])
        if canonical_hash(saved) != canonical_hash(document):
            raise DetailEvidenceConflict('Current owner is not the exact saved fallback state')
    return {'schema': _CAPTURE_SCOPE_SCHEMA, 'document_id': document['id'],
            'session_id': document['session_id'], 'generation': document['generation'],
            'pending_generation': pending['generation'],
            'input_revision': document['input_revision'],
            'approved_sha256': canonical_hash(document), 'approved_working_sha256': disk_hash,
            'pending_sha256': canonical_hash(pending),
            'manifest': deepcopy(manifest)}


def _capture_current(owner, identifier, prior):
    """Check scope before opening/recovering an owner or writing any file.

    PREPARED permits only the original state or this command's exact row
    registration. REGISTERED permits only the latter. A cold owner with a new
    session cannot inherit write approval; immutable result recovery is separate.
    """
    scope = prior.get('capture_scope')
    if not isinstance(scope, dict) or scope.get('schema') != _CAPTURE_SCOPE_SCHEMA:
        raise DetailEvidenceConflict('Legacy/unknown PRESERVING receipt has no approved owner capsule')
    if scope.get('document_id') != identifier or scope.get('session_id') != owner.session_id:
        raise DetailEvidenceConflict('Owner identity/session changed; pending write approval is stale')
    if owner._manifest(identifier) != scope['manifest']:
        raise DetailEvidenceConflict('A save or external publication changed the approved owner')
    working = owner._folder(identifier) / 'working.json'
    if not working.exists():
        raise DetailEvidenceConflict('The approved recoverable working state is missing')
    on_disk = load_json(working)
    document = deepcopy(owner._documents.get(identifier, on_disk))
    memory_hash, disk_hash = canonical_hash(document), canonical_hash(on_disk)
    pending, approved = scope['pending_sha256'], scope['approved_sha256']
    registered = memory_hash == pending and disk_hash == pending
    prepared = (prior.get('phase') == 'PREPARED' and memory_hash == approved
                and disk_hash in {scope['approved_working_sha256'], pending})
    if not registered and not prepared:
        raise DetailEvidenceConflict('Peer edit/run/save/Undo/Redo or cold recovery changed the approved state')
    return document


def _record_capture_publication(owner, saved, folder):
    """Bind the existing save transaction to this exact command, before commit.

    The witness is added to the save writer's COPY, never the pending working
    document. An unpublished/orphan revision or a later peer save therefore
    cannot claim CAPTURE completion. The normal manifest is still the sole
    commit pointer; this is not a second transaction coordinator.
    """
    context = _CAPTURE_SAVE.get()
    if context is None or context['owner'] is not owner or saved['id'] != context['identifier']:
        return
    prior = load_json(context['receipt'])
    if prior.get('request_hash') != context['signature'] or prior.get('capture_scope') != context['scope']:
        raise DetailIdentityError('Capture receipt changed during preservation')
    _capture_current(owner, saved['id'], prior)
    if canonical_hash(saved) != context['scope']['pending_sha256']:
        raise DetailEvidenceConflict('The save writer did not receive the approved pending state')
    witness = {'command_id': context['command_id'], 'request_hash': context['signature'],
               'saved_revision': check_id(folder.name), 'snapshot_sha256': prior['snapshot_sha256'],
               'scope_sha256': canonical_hash(context['scope'])}
    # A provisional revision locator alone is never proof of publication.
    prior['publication'] = witness
    save_json(context['receipt'], prior)
    saved.setdefault(_PUBLICATIONS, {})[context['command_id']] = deepcopy(witness)


def retain_evidence_inputs(owner, saved, folder):
    """Called by the existing owner revision transaction before publication."""
    for row in saved.get('candidate_evidence', []):
        base = (owner._folder(saved['id']) / 'revisions' / check_id(row['retained_revision'])
                if row.get('retained_revision') else owner._folder(saved['id']))
        if row.get('retained_revision'):
            owner._verify_revision(saved['id'], row['retained_revision'])
        value = load_json(base / 'candidate_evidence' / (check_id(row['id']) + '.json'))
        if canonical_hash(value) != row['sha256']:
            raise DetailIdentityError('Working candidate evidence changed; previous revision is preserved')
        from .portable_project_execution import retain_snapshot_bytes
        destination = folder / 'candidate_evidence' / (row['id'] + '.json')
        if not retain_snapshot_bytes(saved, base / 'candidate_evidence' / (row['id'] + '.json'), destination):
            save_json(destination, value)
        row['retained_revision'] = folder.name


def _capture_response(owner, document, reference, command_id):
    verified = resolve_candidate_evidence(owner, reference)
    return {'document': owner._public(document), 'reference': deepcopy(reference),
            'readiness': verified['readiness'], 'command_id': command_id,
            'completion': 'EVIDENCE_PRESERVED; NOT_ENGINEERING_QUALIFICATION'}


def _replay_capture(owner, response, arguments, command_id):
    """No owner.read(): even its generic job recovery can mutate current state."""
    if response.get('command_id') != command_id:
        raise DetailIdentityError('Completed evidence receipt has another command identity')
    resolved = resolve_candidate_evidence(owner, response['reference'], source=arguments['source'],
        candidate_id=arguments['candidate_id'], attempt_job_id=arguments['attempt_job_id'])
    snapshot = resolved['snapshot']
    expected = _scope(_snapshot_view(snapshot), arguments.get('required_experiments'))
    if snapshot['purpose'] != arguments['purpose'] or snapshot['scope'] != expected:
        raise DetailIdentityError('Completed receipt purpose/scope differs from the exact request')
    return deepcopy(response)


def _recover_capture_publication(owner, identifier, prior, arguments, command_id):
    """Read-only recovery, even after peer edits/saves or a new owner session.

    Verify BOTH the published lineage witness and the exact original revision.
    A complete-looking revision folder without a published witness is UNKNOWN.
    Never use the newest candidate row as a substitute for this command's ref.
    """
    witness = prior.get('publication')
    if not witness:
        return None
    scope = prior.get('capture_scope')
    expected = {'command_id': command_id, 'request_hash': prior['request_hash'],
                'saved_revision': witness.get('saved_revision'),
                'snapshot_sha256': prior.get('snapshot_sha256'), 'scope_sha256': canonical_hash(scope)}
    if witness != expected:
        raise DetailIdentityError('Capture publication witness differs from its approved capsule')
    manifest = owner._manifest(identifier)
    if manifest is None:
        return None
    from .evaluation import file_hash
    revision_file = owner._folder(identifier) / 'revisions' / check_id(manifest['revision']) / 'revision.json'
    if file_hash(revision_file) != manifest['revision_sha256']:
        raise DetailIdentityError('Published revision manifest changed')
    published = owner._verify_revision(identifier, manifest['revision'])
    retained = published.get(_PUBLICATIONS, {}).get(command_id)
    if retained is None:
        return None  # orphan write or an unrelated save; not CAPTURE completion
    if retained != witness:
        raise DetailIdentityError('Published capture witness differs from the command receipt')
    revision = check_id(witness['saved_revision'])
    saved = owner._verify_revision(identifier, revision)
    if (saved.get(_PUBLICATIONS, {}).get(command_id) != witness or saved.get('saved_revision') != revision
            or saved.get('session_id') != scope['session_id']
            or saved.get('generation') != scope['pending_generation']
            or saved.get('input_revision') != scope['input_revision']):
        raise DetailIdentityError('Exact saved CAPTURE identity differs from the approved pending state')
    snapshot = load_json(owner._folder(identifier) / 'revisions' / revision / 'candidate_evidence' /
                         ('H' + prior['snapshot_sha256'] + '.json'))
    reference = evidence_reference(identifier, revision, snapshot, owner=owner)
    if reference['snapshot_sha256'] != witness['snapshot_sha256']:
        raise DetailIdentityError('Committed capture snapshot changed')
    response = _capture_response(owner, saved, reference, command_id)
    return _replay_capture(owner, response, arguments, command_id)


def evidence_command(owner, identifier, operation, arguments, *, session_id, expected_generation, command_id=None):
    if not isinstance(arguments, dict):
        raise ValueError('Candidate evidence command requires object arguments')
    if type(expected_generation) is not int or expected_generation < 0:
        raise ValueError('Candidate evidence command requires an exact generation')
    identifier = check_id(identifier)
    with owner._lock(identifier):
        if operation != CAPTURE:
            if session_id != owner.session_id:
                raise ValueError('Candidate evidence command requires current owner session')
            owner.read(identifier)
            document = deepcopy(owner._documents[identifier])
            if document['generation'] != expected_generation:
                raise ValueError('Document generation changed; reread the owner')
            if operation == READ and set(arguments) <= {'reference', 'consumer'} and 'reference' in arguments:
                value = resolve_candidate_evidence(owner, arguments['reference'], consumer=arguments.get('consumer', 'read'))
            elif operation == COMPARE and set(arguments) == {'left', 'right', 'experiment_id'}:
                value = compare_selected_candidate_evidence(owner, arguments['left'], arguments['right'], arguments['experiment_id'])
            elif operation == ADOPTION_PREVIEW and set(arguments) == {'reference'}:
                value = candidate_adoption_preview(owner, arguments['reference'])
            else:
                raise ValueError('Invalid candidate evidence read/comparison/preview arguments')
            refs = [arguments[k] for k in ('reference', 'left', 'right') if k in arguments]
            if any(ref['document_id'] != identifier for ref in refs):
                raise DetailIdentityError('Evidence command belongs to a different Numerical owner')
            return {'document': owner._public(document), 'evidence': value}
        required = {'source', 'candidate_id', 'attempt_job_id', 'purpose'}
        if not required <= set(arguments) or set(arguments) - required - {'required_experiments'}:
            raise ValueError('Capture requires exact source/candidate/explicit attempt (or null)/purpose')
        if not isinstance(arguments['source'], dict) or arguments['source'].get('document_id') != identifier:
            raise DetailIdentityError('Evidence capture belongs to another owner')
        command_id = check_id(command_id or 'C' + uuid.uuid4().hex)
        signature = canonical_hash({'document_id': identifier, 'operation': operation, 'arguments': arguments,
                                    'session_id': session_id, 'expected_generation': expected_generation})
        receipt = owner._folder(identifier) / 'commands' / (command_id + '.json')
        prior = load_json(receipt) if receipt.exists() else None
        if prior:
            if prior.get('request_hash') != signature:
                raise ValueError('Evidence command_id conflicts with another request')
            if 'response' in prior:
                return _replay_capture(owner, prior['response'], arguments, command_id)
            if prior.get('state') != 'PRESERVING':
                raise DetailEvidenceConflict('Unknown prior command outcome; no write is authorized')
            recovered = _recover_capture_publication(owner, identifier, prior, arguments, command_id)
            if recovered is not None:
                return recovered
        if session_id != owner.session_id:
            raise DetailEvidenceConflict('Owner session changed; only exact committed response replay is permitted')
        if prior:
            document = _capture_current(owner, identifier, prior)
            # This is now an exact same-session cold restore, not a fresh approval.
            owner._documents.setdefault(identifier, deepcopy(document))
        else:
            owner.read(identifier)
            document = deepcopy(owner._documents[identifier])
            if document['generation'] != expected_generation:
                raise ValueError('Document generation changed; reread before evidence capture')
        snapshot = prepare_candidate_evidence(owner, arguments['source'], arguments['candidate_id'],
            attempt_job_id=arguments['attempt_job_id'], required_experiments=arguments.get('required_experiments'),
            purpose=arguments['purpose'])
        encoded = json.dumps(snapshot, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(encoded) > 64 * 1024 * 1024:
            raise DetailEvidenceBlocked('Selected evidence exceeds 64 MiB; no completion is recorded')
        digest = canonical_hash(snapshot)
        if prior and digest != prior.get('snapshot_sha256'):
            raise DetailIdentityError('Retry changed the original candidate / selected detail snapshot')
        evidence_id = 'H' + digest
        row = next((r for r in document.get('candidate_evidence', []) if r['id'] == evidence_id), None)
        if not prior and row and row.get('retained_revision'):
            reference = evidence_reference(identifier, row['retained_revision'], snapshot, owner=owner)
            response = _capture_response(owner, document, reference, command_id)
        else:
            pending = deepcopy(document)
            if row is None:
                pending.setdefault('candidate_evidence', []).append({'id': evidence_id, 'sha256': digest,
                                                                     'binding': _binding(snapshot)})
                pending['generation'] += 1  # solely this CAPTURE's snapshot registration
            if prior is None:
                prior = {'request_hash': signature, 'operation': CAPTURE, 'state': 'PRESERVING',
                         'phase': 'PREPARED', 'snapshot_sha256': digest,
                         'capture_scope': _capture_scope(owner, document, pending)}
                # Check the disk/owner agreement before even publishing a receipt.
                _capture_current(owner, identifier, prior)
                save_json(receipt, prior)
            if canonical_hash(pending) != prior['capture_scope']['pending_sha256']:
                raise DetailEvidenceConflict('Retry is not the exact CAPTURE registration transition')
            path = owner._folder(identifier) / 'candidate_evidence' / (evidence_id + '.json')
            if path.exists():
                if canonical_hash(load_json(path)) != digest:
                    raise DetailIdentityError('Candidate snapshot already exists with different bytes')
            else:
                save_json(path, snapshot)
            _capture_current(owner, identifier, prior)
            owner._persist_draft(pending)
            owner._documents[identifier] = pending
            prior['phase'] = 'REGISTERED'
            save_json(receipt, prior)
            context = {'owner': owner, 'identifier': identifier, 'receipt': receipt,
                       'signature': signature, 'scope': prior['capture_scope'], 'command_id': command_id}
            token = _CAPTURE_SAVE.set(context)
            try:
                _capture_current(owner, identifier, prior)
                owner._save(pending)  # unchanged owner transaction and manifest CAS
            finally:
                _CAPTURE_SAVE.reset(token)
            owner._persist_draft(pending)
            reference = evidence_reference(identifier, pending['saved_revision'], snapshot, owner=owner)
            response = _capture_response(owner, pending, reference, command_id)
            prior = load_json(receipt)  # keep the exact publication witness recorded by the save hook
        save_json(receipt, {**(prior or {}), 'request_hash': signature, 'operation': CAPTURE,
                            'state': 'COMPLETED', 'response': response})
        return response


def evidence_adopt_command(workbench, identifier, arguments, *, session_id, expected_generation, command_id):
    """Bridge the existing document-command HTTP/CLI path to existing adoption."""
    if not isinstance(arguments, dict) or set(arguments) != {
            'reference', 'target_document_id', 'target_kind', 'target_generation'}:
        raise ValueError('Evidence adoption requires a saved ref and the exact target generation')
    owner = workbench.numerical_documents
    document = owner.read(identifier)
    if (session_id != owner.session_id or type(expected_generation) is not int or
            document['generation'] != expected_generation):
        raise ValueError('Numerical owner session/generation changed')
    reference = arguments['reference']
    resolve_candidate_evidence(owner, reference, consumer='adoption')
    if reference['document_id'] != identifier:
        raise DetailIdentityError('Evidence adoption belongs to another Plan')
    common = {'session_id': session_id, 'expected_generation': arguments['target_generation'],
              'command_id': check_id(command_id), 'detail_evidence': reference}
    identity = (identifier, reference['source']['job_id'], reference['candidate_id'])
    if arguments['target_kind'] == 'material':
        return workbench.desktop.adopt(*identity, material_document_id=arguments['target_document_id'], **common)
    if arguments['target_kind'] == 'pde':
        return workbench.desktop.pde_adopt(*identity, pde_document_id=arguments['target_document_id'], **common)
    if arguments['target_kind'] == 'domain':
        return workbench.domain_candidate_adopt(*identity, target_document_id=arguments['target_document_id'], **common)
    raise ValueError('Choose the original material, PDE or explicitly bound domain target')
