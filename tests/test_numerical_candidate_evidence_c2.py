"""C2 owner CAS and exact published-response recovery, no GUI/evaluator doubles.

Uses the unchanged C1 synthetic DetailHost with the real fit engine, JobManager,
NumericalDocuments, manifest CAS, immutable revision verification and receipts.
Only individual I/O fault boundaries are injected. This is NOT a FELUPE claim.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from caelab import numerical_candidate_evidence as evidence
from caelab.numerical_document import NumericalDocuments
from caelab.storage import canonical_hash, load_json, save_json
from _numerical_candidate_detail_support import DetailHost, synthetic_inputs, intermediate
from test_numerical_candidate_evidence_c1 import complete


def selection(host, *, prior_save=True, undo_history=False):
    doc, job = host.create_fit(synthetic_inputs(retain=0))
    cid = intermediate(host, doc, job)
    view = complete(host, doc, job, cid)
    if undo_history:
        edit(host, doc, 'An approved draft with Undo history')
    if prior_save:
        host.command(doc, 'document.save', {})
    current = host.owner.read(doc)
    args = dict(source=view['source'], candidate_id=cid,
                attempt_job_id=view['attempt_job_id'], purpose=evidence.SUCCESS)
    identity = dict(session_id=current['session_id'], expected_generation=current['generation'],
                    command_id='CscopeRetry')
    return doc, job, view, args, identity


def edit(host, doc, purpose):
    draft = deepcopy(host.owner.read(doc)['draft'])
    draft['request']['purpose'] = purpose
    host.command(doc, 'numerical.update', {'draft': draft})


def receipt_path(owner, doc, identity):
    return owner._folder(doc) / 'commands' / (identity['command_id'] + '.json')


def io_failure(*args, **kwargs):
    raise OSError('C2 injected save failure')


def failed_capture(host, doc, args, identity, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(host.owner, '_save', io_failure)
        with pytest.raises(OSError, match='C2 injected'):
            host.owner.command(doc, evidence.CAPTURE, args, **identity)
    prior = load_json(receipt_path(host.owner, doc, identity))
    assert prior['state'] == 'PRESERVING' and prior['phase'] == 'REGISTERED'
    assert 'response' not in prior and 'publication' not in prior
    return prior


def frozen_history(host, doc, job, view):
    result = host.owner.result(doc, job)
    run = next(r for r in host.owner.read(doc)['runs'] if r['job_id'] == job)
    return dict(input_sha256=run['input_sha256'], input_revision=run['input_revision'],
                original_plan=canonical_hash(run['draft']), arguments=canonical_hash(run['arguments']),
                result=canonical_hash(result), holdout=canonical_hash(result.get('curves')),
                candidate=canonical_hash(host.view(doc, job, view['candidate']['candidate_id'])['candidate']),
                attempt=canonical_hash(host.owner.result(doc, view['attempt_job_id'])))


def file_tree(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*') if p.is_file()}


def owner_state(host, doc):
    # Read before installing tripwires; it must be the peer's latest state.
    return {'public': host.owner.read(doc), 'raw': deepcopy(host.owner._documents[doc]),
            'files': file_tree(host.owner._folder(doc)), 'jobs': len(host.manager.list())}


def assert_unchanged(host, doc, before):
    assert host.owner.read(doc) == before['public']
    assert host.owner._documents[doc] == before['raw']
    assert file_tree(host.owner._folder(doc)) == before['files']
    assert len(host.manager.list()) == before['jobs']


def no_current_write(*args, **kwargs):
    raise AssertionError('Old CAPTURE accessed a mutable owner/write path')


def assert_conflict(host, doc, args, identity, monkeypatch):
    before = owner_state(host, doc)
    with monkeypatch.context() as patch:
        patch.setattr(host.owner, '_save', no_current_write)
        patch.setattr(host.owner, '_persist_draft', no_current_write)
        patch.setattr(host.owner, 'read', no_current_write)
        with pytest.raises(evidence.DetailEvidenceConflict, match='STALE_CAPTURE'):
            host.owner.command(doc, evidence.CAPTURE, args, **identity)
    assert_unchanged(host, doc, before)


@pytest.mark.parametrize('prior_save', [False, True])
def test_unchanged_retry_allows_only_its_own_registration(tmp_path, monkeypatch, prior_save):
    with DetailHost(tmp_path) as host:
        doc, job, view, args, identity = selection(host, prior_save=prior_save)
        before = owner_state(host, doc)
        original = frozen_history(host, doc, job, view)
        prior = failed_capture(host, doc, args, identity, monkeypatch)
        current = host.owner.read(doc)
        assert current['generation'] == identity['expected_generation'] + 1
        assert current['input_revision'] == before['public']['input_revision']
        assert current['saved_revision'] == before['public']['saved_revision']
        assert current['dirty']
        pending = prior['capture_scope']
        assert pending['approved_sha256'] == canonical_hash(before['raw'])
        assert pending['pending_sha256'] == canonical_hash(host.owner._documents[doc])
        answer = host.owner.command(doc, evidence.CAPTURE, args, **identity)
        assert answer['document']['generation'] == current['generation']
        assert not answer['document']['dirty']
        resolved = evidence.resolve_candidate_evidence(host.owner, answer['reference'], consumer='adoption')
        assert resolved['readiness']['success_judgment_permitted']
        assert answer['reference']['attempt_job_id'] == view['attempt_job_id']
        assert frozen_history(host, doc, job, view) == original
        assert len(host.manager.list()) == before['jobs']


def test_failure_then_peer_update_preserves_dirty_generation_revision_and_all_hashes(tmp_path, monkeypatch):
    with DetailHost(tmp_path) as host:
        doc, job, view, args, identity = selection(host)
        original = frozen_history(host, doc, job, view)
        saved = host.owner.read(doc)['saved_revision']
        failed_capture(host, doc, args, identity, monkeypatch)
        edit(host, doc, '다른 창: 아직 저장 승인하지 않은 계획')
        before = host.owner.read(doc)
        assert before['generation'] == identity['expected_generation'] + 2
        assert before['dirty'] and before['saved_revision'] == saved
        assert_conflict(host, doc, args, identity, monkeypatch)
        assert frozen_history(host, doc, job, view) == original


@pytest.mark.parametrize('action', ['newrun', 'undo', 'undo_redo', 'save', 'peer_save_after_edit'])
def test_other_owner_actions_invalidate_pending_even_without_generation_change(tmp_path, monkeypatch, action):
    with DetailHost(tmp_path) as host:
        doc, job, view, args, identity = selection(host, undo_history=True)
        original = frozen_history(host, doc, job, view)
        failed_capture(host, doc, args, identity, monkeypatch)
        pending = host.owner.read(doc)
        if action == 'newrun':
            task = host.command(doc, 'numerical.run', {})['job']['id']
            assert host.wait(task)['state'] == 'SUCCEEDED'
        elif action == 'undo':
            host.command(doc, 'document.undo', {})
        elif action == 'undo_redo':
            host.command(doc, 'document.undo', {})
            host.command(doc, 'document.redo', {})
            assert host.owner.read(doc)['draft'] == pending['draft']  # ABA still conflicts
        else:
            if action == 'peer_save_after_edit':
                edit(host, doc, 'Explicit peer edit and peer save, not the original CAPTURE')
            host.command(doc, 'document.save', {})
        if action in {'newrun', 'save'}:
            assert host.owner.read(doc)['generation'] == pending['generation']
        assert_conflict(host, doc, args, identity, monkeypatch)
        assert frozen_history(host, doc, job, view) == original
        prior = load_json(receipt_path(host.owner, doc, identity))
        assert 'response' not in prior and 'publication' not in prior


@pytest.mark.parametrize('completed', [False, True])
@pytest.mark.parametrize('changed', ['args', 'generation', 'session'])
def test_request_id_never_reauthorized_with_new_signature(tmp_path, monkeypatch, completed, changed):
    with DetailHost(tmp_path) as host:
        doc, job, view, args, identity = selection(host)
        if completed:
            host.owner.command(doc, evidence.CAPTURE, args, **identity)
        else:
            failed_capture(host, doc, args, identity, monkeypatch)
        before = owner_state(host, doc)
        if changed == 'args':
            args = {**args, 'required_experiments': ['T0']}
        elif changed == 'generation':
            identity = {**identity, 'expected_generation': before['public']['generation']}
        else:
            identity = {**identity, 'session_id': 'SotherSession'}
        with pytest.raises(ValueError, match='conflicts'):
            host.owner.command(doc, evidence.CAPTURE, args, **identity)
        assert_unchanged(host, doc, before)


def test_completed_response_replay_never_reads_or_saves_current_owner(tmp_path, monkeypatch):
    with DetailHost(tmp_path) as host:
        doc, job, view, args, identity = selection(host)
        response = host.owner.command(doc, evidence.CAPTURE, args, **identity)
        edit(host, doc, 'Peer draft after fully completed CAPTURE')
        before = owner_state(host, doc)
        with monkeypatch.context() as patch:
            patch.setattr(host.owner, '_save', no_current_write)
            patch.setattr(host.owner, '_persist_draft', no_current_write)
            patch.setattr(host.owner, 'read', no_current_write)
            patch.setattr(evidence, 'save_json', no_current_write)
            assert host.owner.command(doc, evidence.CAPTURE, args, **identity) == response
        assert_unchanged(host, doc, before)
        assert response['document']['generation'] < before['public']['generation']


def lose_response(host, doc, args, identity, monkeypatch, point):
    """Leave a real published revision but a response-less command receipt."""
    observed = {}
    with monkeypatch.context() as patch:
        if point == 'receipt':
            writer = evidence.save_json
            def fail(path, value):
                if Path(path) == receipt_path(host.owner, doc, identity) and 'response' in value:
                    observed['response'] = deepcopy(value['response'])
                    raise OSError('C2 lost final response record')
                return writer(path, value)
            patch.setattr(evidence, 'save_json', fail)
        elif point == 'save_return':
            writer = host.owner._save
            def fail(document):
                writer(document)
                raise OSError('C2 lost save return after commit')
            patch.setattr(host.owner, '_save', fail)
        else:
            writer = host.owner._persist_draft
            def fail(document):
                if document.get(evidence._PUBLICATIONS, {}).get(identity['command_id']):
                    raise OSError('C2 lost working write after commit')
                return writer(document)
            patch.setattr(host.owner, '_persist_draft', fail)
        with pytest.raises(OSError, match='C2 lost'):
            host.owner.command(doc, evidence.CAPTURE, args, **identity)
    prior = load_json(receipt_path(host.owner, doc, identity))
    assert 'response' not in prior and prior.get('publication')
    return prior, observed.get('response')


@pytest.mark.parametrize('point', ['receipt', 'save_return', 'working_write'])
@pytest.mark.parametrize('peer_save', [False, True])
def test_real_commit_lost_response_recovers_only_original_revision_after_peer_change(
        tmp_path, monkeypatch, point, peer_save):
    with DetailHost(tmp_path) as host:
        doc, job, view, args, identity = selection(host)
        original = frozen_history(host, doc, job, view)
        prior, sent = lose_response(host, doc, args, identity, monkeypatch, point)
        committed = prior['publication']['saved_revision']
        edit(host, doc, 'Peer state never saved by replay of committed CAPTURE')
        if peer_save:
            host.command(doc, 'document.save', {})
        before = owner_state(host, doc)
        with monkeypatch.context() as patch:
            patch.setattr(host.owner, '_save', no_current_write)
            patch.setattr(host.owner, '_persist_draft', no_current_write)
            patch.setattr(host.owner, 'read', no_current_write)
            patch.setattr(evidence, 'save_json', no_current_write)
            response = host.owner.command(doc, evidence.CAPTURE, args, **identity)
            assert host.owner.command(doc, evidence.CAPTURE, args, **identity) == response
        if sent is not None:
            assert response == sent
        assert response['reference']['saved_revision'] == committed
        assert response['document']['draft']['request']['purpose'] != before['public']['draft']['request']['purpose']
        assert response['document']['generation'] == identity['expected_generation'] + 1
        assert response['reference']['attempt_job_id'] == view['attempt_job_id']
        assert_unchanged(host, doc, before)
        assert frozen_history(host, doc, job, view) == original


@pytest.mark.parametrize('retry', [True, False])
def test_orphan_revision_is_not_a_commit_or_a_later_peer_save(tmp_path, monkeypatch, retry):
    from caelab import material_document
    with DetailHost(tmp_path) as host:
        doc, job, view, args, identity = selection(host)
        previous = host.owner._manifest(doc)
        writer = material_document.save_json
        with monkeypatch.context() as patch:
            def fail(path, value):
                if Path(path) == host.owner._folder(doc) / 'document.json':
                    raise OSError('C2 refused publication pointer')
                return writer(path, value)
            patch.setattr(material_document, 'save_json', fail)
            with pytest.raises(OSError, match='publication pointer'):
                host.owner.command(doc, evidence.CAPTURE, args, **identity)
        prior = load_json(receipt_path(host.owner, doc, identity))
        orphan = prior['publication']['saved_revision']
        assert host.owner._verify_revision(doc, orphan)  # complete bytes alone are NOT publication
        assert host.owner._manifest(doc) == previous
        assert identity['command_id'] not in host.owner._documents[doc].get(evidence._PUBLICATIONS, {})
        if retry:
            answer = host.owner.command(doc, evidence.CAPTURE, args, **identity)
            assert answer['reference']['saved_revision'] != orphan
            assert not answer['document']['dirty']
        else:
            host.command(doc, 'document.save', {})
            assert_conflict(host, doc, args, identity, monkeypatch)


@pytest.mark.parametrize('phase', ['snapshot_write', 'pending_persist', 'pending_persist_return', 'registered_receipt'])
def test_precommit_fault_boundaries_allow_only_exact_self_registration(tmp_path, monkeypatch, phase):
    with DetailHost(tmp_path) as host:
        doc, job, view, args, identity = selection(host)
        with monkeypatch.context() as patch:
            if phase == 'pending_persist':
                patch.setattr(host.owner, '_persist_draft', io_failure)
            elif phase == 'pending_persist_return':
                writer = host.owner._persist_draft
                def fail_after_persist(document):
                    writer(document)
                    raise OSError('C2 injected lost pending write return')
                patch.setattr(host.owner, '_persist_draft', fail_after_persist)
            else:
                writer = evidence.save_json
                def fail(path, value):
                    if ((phase == 'snapshot_write' and Path(path).parent.name == 'candidate_evidence') or
                            (phase == 'registered_receipt' and value.get('phase') == 'REGISTERED')):
                        raise OSError('C2 injected interrupted registration')
                    return writer(path, value)
                patch.setattr(evidence, 'save_json', fail)
            with pytest.raises(OSError, match='C2 injected'):
                host.owner.command(doc, evidence.CAPTURE, args, **identity)
        answer = host.owner.command(doc, evidence.CAPTURE, args, **identity)
        assert answer['document']['generation'] == identity['expected_generation'] + 1
        assert not answer['document']['dirty']
        assert len(host.manager.list()) == 2


def test_legacy_preserving_receipt_is_unknown_not_automatic_reapproval(tmp_path, monkeypatch):
    with DetailHost(tmp_path) as host:
        doc, job, view, args, identity = selection(host)
        prior = failed_capture(host, doc, args, identity, monkeypatch)
        legacy = {k: prior[k] for k in ('request_hash', 'operation', 'state', 'snapshot_sha256')}
        save_json(receipt_path(host.owner, doc, identity), legacy)
        assert_conflict(host, doc, args, identity, monkeypatch)


def test_unchanged_legacy_completed_receipt_still_replays(tmp_path, monkeypatch):
    with DetailHost(tmp_path) as host:
        doc, job, view, args, identity = selection(host)
        response = host.owner.command(doc, evidence.CAPTURE, args, **identity)
        receipt = load_json(receipt_path(host.owner, doc, identity))
        save_json(receipt_path(host.owner, doc, identity),
                  {'request_hash': receipt['request_hash'], 'operation': evidence.CAPTURE, 'response': response})
        edit(host, doc, 'After C1-style complete receipt')
        before = owner_state(host, doc)
        with monkeypatch.context() as patch:
            patch.setattr(host.owner, 'read', no_current_write)
            assert host.owner.command(doc, evidence.CAPTURE, args, **identity) == response
        assert_unchanged(host, doc, before)


def test_external_working_state_changed_without_inmemory_refresh_is_stale(tmp_path, monkeypatch):
    with DetailHost(tmp_path) as host:
        doc, job, view, args, identity = selection(host)
        failed_capture(host, doc, args, identity, monkeypatch)
        path = host.owner._folder(doc) / 'working.json'
        external = load_json(path)
        external['draft']['request']['purpose'] = 'External cold recovery draft'
        external['generation'] += 1
        save_json(path, external)
        assert_conflict(host, doc, args, identity, monkeypatch)


def new_owner(host, session):
    return NumericalDocuments(host.root, session, host._submit, host.manager,
        resolve_document=lambda identifier: host.owner.read(identifier),
        resolve_result=lambda identifier, job: host.owner.result(identifier, job),
        prepare_request=lambda request: deepcopy(request['inputs']))


@pytest.mark.parametrize('change', ['none', 'peer_edit', 'newrun', 'undo', 'new_session', 'missing_working'])
def test_pending_reopen_same_capsule_only_and_no_new_session_write_approval(tmp_path, monkeypatch, change):
    with DetailHost(tmp_path) as host:
        doc, job, view, args, identity = selection(host, undo_history=True)
        failed_capture(host, doc, args, identity, monkeypatch)
        if change == 'peer_edit':
            edit(host, doc, 'Unsaved peer draft before owner replacement')
        elif change == 'newrun':
            task = host.command(doc, 'numerical.run', {})['job']['id']
            host.wait(task)
        elif change == 'undo':
            host.command(doc, 'document.undo', {})
        elif change == 'missing_working':
            (host.owner._folder(doc) / 'working.json').unlink()
        original_files = file_tree(host.owner._folder(doc))
        host.owner = new_owner(host, 'SnewProcess' if change == 'new_session' else identity['session_id'])
        if change == 'none':
            response = host.owner.command(doc, evidence.CAPTURE, args, **identity)
            assert response['document']['generation'] == identity['expected_generation'] + 1
            assert not response['document']['dirty']
        else:
            with monkeypatch.context() as patch:
                patch.setattr(host.owner, '_save', no_current_write)
                patch.setattr(host.owner, '_persist_draft', no_current_write)
                patch.setattr(host.owner, 'read', no_current_write)
                with pytest.raises(evidence.DetailEvidenceConflict):
                    host.owner.command(doc, evidence.CAPTURE, args, **identity)
            assert host.owner._documents == {}
            assert file_tree(host.owner._folder(doc)) == original_files


def test_existing_comparison_retention_hook_is_inside_approved_save_not_a_peer_edit(tmp_path):
    with DetailHost(tmp_path) as host:
        doc, job, view, args, identity = selection(host)
        record = {'execution_status': 'SUCCEEDED', 'binding': {'public': 'existing-comparison'},
                  'comparison': {'unit': 'MPa', 'method': 'exact', 'count': 1,
                                 'rmse': 0., 'observation': {'value': [1.]}, 'prediction': [1.],
                                 'mask': [True], 'residual': [0.]}}
        item = host.owner.retain_comparison(doc, record)
        identity['expected_generation'] = host.owner.read(doc)['generation']
        response = host.owner.command(doc, evidence.CAPTURE, args, **identity)
        assert host.owner.comparison(doc, item['id'])['binding'] == record['binding']
        assert response['reference']['saved_revision'] == host.owner.read(doc)['saved_revision']


@pytest.mark.parametrize('phase', ['pending_current', 'pending_stale', 'pending_new_session',
                                   'committed', 'completed'])
def test_moved_storage_fresh_python_process_scope_and_exact_response(tmp_path, monkeypatch, phase):
    old, moved = tmp_path / 'original', tmp_path / '한글 경로 이동'
    with DetailHost(old) as host:
        doc, job, view, args, identity = selection(host)
        original = frozen_history(host, doc, job, view)
        if phase.startswith('pending'):
            failed_capture(host, doc, args, identity, monkeypatch)
            if phase == 'pending_stale':
                edit(host, doc, 'Peer edit persisted before process exit')
            expected_ref = None
        elif phase == 'completed':
            sent = host.owner.command(doc, evidence.CAPTURE, args, **identity)
            expected_ref = sent['reference']
            edit(host, doc, 'Current unsaved state newer than returned completed response')
        else:
            prior, sent = lose_response(host, doc, args, identity, monkeypatch, 'receipt')
            expected_ref = sent['reference']
            edit(host, doc, 'Current unsaved state after lost final response and before restart')
        parent = owner_state(host, doc)
    shutil.move(old, moved)
    # Published responses must work without manager result files/current owner,
    # not only because the old Python process still has cached data.
    if phase in {'committed', 'completed'}:
        shutil.rmtree(moved / 'results', ignore_errors=True)
    request = dict(doc=doc, args=args, identity=identity, phase=phase,
                   reference=expected_ref, history=original)
    request_path = tmp_path / 'request.json'
    save_json(request_path, request)
    output_path = tmp_path / 'fresh-process.json'
    program = r'''
import json, sys, hashlib
from pathlib import Path
from copy import deepcopy
from _numerical_candidate_detail_support import DetailHost
from caelab.numerical_document import NumericalDocuments
from caelab.numerical_candidate_evidence import CAPTURE, DetailEvidenceConflict, resolve_candidate_evidence
from caelab.storage import canonical_hash
root, request_path, output_path = map(Path, sys.argv[1:])
request = json.loads(request_path.read_text(encoding='utf-8'))
doc, phase = request['doc'], request['phase']
def files():
    folder = root / 'documents' / doc
    return {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*') if p.is_file()}
def forbidden(*args, **kwargs):
    raise AssertionError('Replay/conflict accessed current owner or wrote a file')
with DetailHost(root) as host:
    identity = request['identity']
    same_session = phase in {'pending_current', 'pending_stale'}
    session = identity['session_id'] if same_session else host.owner.session_id
    host.owner = NumericalDocuments(root, session, forbidden, host.manager,
        resolve_document=forbidden, resolve_result=forbidden,
        prepare_request=forbidden)
    before = files()
    if phase != 'pending_current':
        host.owner.read = forbidden
        host.owner._save = forbidden
        host.owner._persist_draft = forbidden
    try:
        answer = host.owner.command(doc, CAPTURE, request['args'], **identity)
    except DetailEvidenceConflict:
        assert phase in {'pending_stale','pending_new_session'}
        assert files() == before and host.owner._documents == {}
        result = {'status':'STALE_CAPTURE', 'files_unchanged':True}
    else:
        assert phase in {'pending_current','committed','completed'}
        if request['reference'] is not None:
            assert answer['reference'] == request['reference']
        verified = resolve_candidate_evidence(host.owner, answer['reference'], consumer='adoption')
        snapshot = verified['snapshot']
        assert snapshot['source']['result_sha256'] == request['history']['result']
        assert snapshot['source']['input_sha256'] == request['history']['input_sha256']
        assert snapshot['candidate_sha256'] == request['history']['candidate']
        assert snapshot['selected_attempt_job_id'] == request['args']['attempt_job_id']
        assert snapshot['selected_holdout_refs'][0]['job_id'] == request['args']['attempt_job_id']
        if phase != 'pending_current':
            assert files() == before and host.owner._documents == {}
            assert host.owner.command(doc, CAPTURE, request['args'], **identity) == answer
        result = {'status':'RECOVERED' if phase != 'pending_current' else 'PRESERVED',
                  'reference':answer['reference'], 'files_unchanged':files()==before,
                  'snapshot_sha256':canonical_hash(snapshot)}
    assert host.dispatched == []
    result['dispatched'] = host.dispatched
    result['job_states'] = [job['state'] for job in host.manager.list()]
output_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
'''
    import os
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join([str(root), str(root / 'tests')])
    child = subprocess.run([sys.executable, '-c', program, str(moved), str(request_path), str(output_path)],
                           cwd=root, env=env, capture_output=True, text=True, timeout=40)
    assert child.returncode == 0, child.stdout + child.stderr
    actual = load_json(output_path)
    assert actual['dispatched'] == []
    if phase in {'pending_stale', 'pending_new_session'}:
        assert actual['status'] == 'STALE_CAPTURE'
    elif phase == 'pending_current':
        assert actual['status'] == 'PRESERVED'
    else:
        assert actual['reference'] == expected_ref and actual['files_unchanged']
    if phase != 'pending_current':
        assert file_tree(moved / 'documents' / doc) == parent['files']


def test_external_owner_save_keeps_original_owner_unchanged_and_blocks_old_retry(tmp_path, monkeypatch):
    with DetailHost(tmp_path) as host:
        doc, job, view, args, identity = selection(host)
        failed_capture(host, doc, args, identity, monkeypatch)
        external = new_owner(host, 'SactualExternalOwner')
        opened = external.open(document_id=doc)
        changed = deepcopy(opened['draft'])
        changed['request']['purpose'] = 'An external owner explicitly saved this peer Plan'
        for operation, arguments in [('numerical.update', {'draft': changed}), ('document.save', {})]:
            current = external.read(doc)
            external.command(doc, operation, arguments, session_id=current['session_id'],
                             expected_generation=current['generation'])
        peer = external.read(doc)
        original_memory = deepcopy(host.owner._documents[doc])
        before_files = file_tree(host.owner._folder(doc))
        with pytest.raises(evidence.DetailEvidenceConflict):
            host.owner.command(doc, evidence.CAPTURE, args, **identity)
        assert host.owner._documents[doc] == original_memory
        assert external.read(doc) == peer
        assert file_tree(host.owner._folder(doc)) == before_files


def test_commit_pointer_write_return_loss_recovers_without_inmemory_completion(tmp_path, monkeypatch):
    from caelab import material_document
    with DetailHost(tmp_path) as host:
        doc, job, view, args, identity = selection(host)
        writer = material_document.save_json
        with monkeypatch.context() as patch:
            def fail_after_write(path, value):
                writer(path, value)
                if Path(path) == host.owner._folder(doc) / 'document.json':
                    raise OSError('C2 publication committed but its writer response was lost')
            patch.setattr(material_document, 'save_json', fail_after_write)
            with pytest.raises(OSError, match='publication committed'):
                host.owner.command(doc, evidence.CAPTURE, args, **identity)
        prior = load_json(receipt_path(host.owner, doc, identity))
        committed = prior['publication']['saved_revision']
        assert host.owner._manifest(doc)['revision'] == committed
        assert host.owner._documents[doc]['saved_revision'] != committed
        assert identity['command_id'] not in host.owner._documents[doc].get(evidence._PUBLICATIONS, {})
        # A stale in-memory owner is not made clean/rebound just to recover an old response.
        before = owner_state(host, doc)
        with monkeypatch.context() as patch:
            patch.setattr(host.owner, 'read', no_current_write)
            patch.setattr(host.owner, '_save', no_current_write)
            patch.setattr(host.owner, '_persist_draft', no_current_write)
            response = host.owner.command(doc, evidence.CAPTURE, args, **identity)
        assert response['reference']['saved_revision'] == committed
        assert_unchanged(host, doc, before)


def test_lost_response_survives_later_capture_of_a_different_candidate(tmp_path, monkeypatch):
    with DetailHost(tmp_path) as host:
        doc, job, view, args, identity = selection(host)
        prior, sent = lose_response(host, doc, args, identity, monkeypatch, 'receipt')
        first = prior['publication']['saved_revision']
        second_id = next(c['candidate_id'] for c in host.owner.result(doc, job)['candidates']
                         if c['execution_status'] == 'SUCCEEDED' and c['candidate_id'] != args['candidate_id'])
        second = complete(host, doc, job, second_id)
        new_args = {**args, 'candidate_id': second_id, 'attempt_job_id': second['attempt_job_id']}
        newer = host.command(doc, evidence.CAPTURE, new_args, command_id='CotherCapture')
        assert newer['reference']['saved_revision'] != first
        before = owner_state(host, doc)
        response = host.owner.command(doc, evidence.CAPTURE, args, **identity)
        assert response == sent
        assert response['reference']['candidate_id'] == args['candidate_id']
        assert response['reference']['attempt_job_id'] == args['attempt_job_id']
        assert response['reference']['saved_revision'] == first
        assert_unchanged(host, doc, before)


@pytest.mark.parametrize('tamper', ['witness', 'scope', 'snapshot_file'])
def test_recovery_witness_or_retained_asset_corruption_never_recovers_success(tmp_path, monkeypatch, tamper):
    with DetailHost(tmp_path) as host:
        doc, job, view, args, identity = selection(host)
        prior, sent = lose_response(host, doc, args, identity, monkeypatch, 'receipt')
        path = receipt_path(host.owner, doc, identity)
        if tamper == 'witness':
            prior['publication']['saved_revision'] = 'RwrongRevision'
            save_json(path, prior)
        elif tamper == 'scope':
            prior['capture_scope']['pending_sha256'] = '0' * 64
            save_json(path, prior)
        else:
            snapshot = (host.owner._folder(doc) / 'revisions' / prior['publication']['saved_revision'] /
                        'candidate_evidence' / ('H' + prior['snapshot_sha256'] + '.json'))
            changed = load_json(snapshot)
            changed['original_candidate']['objective'] = 0.
            save_json(snapshot, changed)
        before = owner_state(host, doc)
        with monkeypatch.context() as patch:
            patch.setattr(host.owner, 'read', no_current_write)
            patch.setattr(host.owner, '_save', no_current_write)
            with pytest.raises(ValueError):
                host.owner.command(doc, evidence.CAPTURE, args, **identity)
        assert_unchanged(host, doc, before)


def test_existing_client_cli_and_service_dispatch_do_not_bypass_stale_capture(tmp_path, monkeypatch):
    from _numerical_candidate_evidence_support import BoundHost, InProcessClient
    from caelab.numerical_candidate_evidence_cli import execute_request
    with BoundHost(tmp_path) as host:
        doc, job, mid = host.create_bound_fit()
        cid = intermediate(host, doc, job)
        view = complete(host, doc, job, cid)
        current = host.owner.read(doc)
        args = dict(source=view['source'], candidate_id=cid, attempt_job_id=view['attempt_job_id'],
                    purpose=evidence.SUCCESS)
        identity = dict(session_id=current['session_id'], expected_generation=current['generation'],
                        command_id='CCliStaleRetry')
        request = dict(document_id=doc, operation=evidence.CAPTURE, arguments=args, **identity)
        client = InProcessClient(host.core)
        with monkeypatch.context() as patch:
            patch.setattr(host.owner, '_save', io_failure)
            with pytest.raises(OSError):
                execute_request(client, request)
        peer = deepcopy(host.owner.read(doc)['draft'])
        peer['experiments'][0]['weight'] += 1.
        host.command(doc, 'numerical.update', {'draft': peer})
        before = owner_state(host, doc)
        with pytest.raises(evidence.DetailEvidenceConflict):
            execute_request(client, request)
        assert_unchanged(host, doc, before)
        assert len(client.requests) == 2
        assert all(body['expected_generation'] == identity['expected_generation']
                   and body['command_id'] == identity['command_id'] for _, body in client.requests)


def test_simultaneous_same_request_saves_once_and_peer_edit_stays_dirty(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    with DetailHost(tmp_path) as host:
        doc, job, view, args, identity = selection(host)
        failed_capture(host, doc, args, identity, monkeypatch)
        entered, release = threading.Event(), threading.Event()
        calls = []
        writer = host.owner._save
        def paused(document):
            calls.append(canonical_hash(document))
            entered.set()
            assert release.wait(10), 'Test did not release the save boundary'
            return writer(document)
        with monkeypatch.context() as patch:
            patch.setattr(host.owner, '_save', paused)
            with ThreadPoolExecutor(max_workers=3) as pool:
                first = pool.submit(host.owner.command, doc, evidence.CAPTURE, args, **identity)
                try:
                    assert entered.wait(10)
                    duplicate = pool.submit(host.owner.command, doc, evidence.CAPTURE, args, **identity)
                    peer = pool.submit(edit, host, doc, 'A peer edit serialized AFTER authorized publication')
                finally:
                    release.set()
                response = first.result(timeout=15)
                assert duplicate.result(timeout=15) == response
                peer.result(timeout=15)
        assert len(calls) == 1
        current = host.owner.read(doc)
        assert current['dirty']
        assert current['generation'] == response['document']['generation'] + 1
        assert current['saved_revision'] == response['reference']['saved_revision']
        before = owner_state(host, doc)
        assert host.owner.command(doc, evidence.CAPTURE, args, **identity) == response
        assert_unchanged(host, doc, before)


def test_explicit_new_command_after_conflict_can_use_peer_saved_evidence_without_writing_plan(tmp_path, monkeypatch):
    with DetailHost(tmp_path) as host:
        doc, job, view, args, identity = selection(host)
        failed_capture(host, doc, args, identity, monkeypatch)
        edit(host, doc, 'Reviewed and explicitly saved by the peer')
        host.command(doc, 'document.save', {})
        assert_conflict(host, doc, args, identity, monkeypatch)
        current = host.owner.read(doc)
        fresh = dict(session_id=current['session_id'], expected_generation=current['generation'],
                     command_id='CnewReviewedRequest')
        before = deepcopy(host.owner._documents[doc])
        with monkeypatch.context() as patch:
            patch.setattr(host.owner, '_save', no_current_write)
            patch.setattr(host.owner, '_persist_draft', no_current_write)
            answer = host.owner.command(doc, evidence.CAPTURE, args, **fresh)
        assert answer['reference']['saved_revision'] == current['saved_revision']
        assert host.owner._documents[doc] == before
        assert len(host.manager.list()) == 2
