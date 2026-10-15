"""Data C2 fixture/foreground cold phases on the existing owners, not a host.

Preparation reuses C3A create_case (one actual CSV import + one intended failed
import). All later phases use the existing cold execution tripwires. Each phase
opens and closes its own Workbench in finally; no GUI/native assertion is made.
"""
from copy import deepcopy
from pathlib import Path
import argparse
import json
import shutil

from caelab.storage import canonical_hash, load_json, save_json
from caelab.evaluation import file_hash
from caelab.portable_project import inspect_copy, create_copy, open_project, MANIFEST
from caelab.portable_project_recovery import archive_row, read_archive
from caelab.portable_recovery_resume import buffer_token, preview_resume, resume
from caelab.related_save_recovery import RawRecoveryDrafts
from examples.portable_connection_c3a_public import create_case
from examples.portable_connection_c3a_c1_public import guarded, file_tree
from examples.portable_connection_public import command, save


def prepare(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    source, copied = folder / 'source', folder / 'copy'
    wb = None
    report = {'phase': 'prepare', 'status': 'STARTED', 'native_FE_provider_calls': 0}
    try:
        wb, case = create_case(source)
        did = case['documents']['data']['id']
        choices = [r for r in case['recovery_selections'] if r['document_id'] == did]
        plan = inspect_copy(wb, [did], draft_policy='saved_only', recovery_archives=choices)
        save_json(folder / 'initial-inspection.json', plan)
        assert plan['status'] == 'READY', plan
        create_copy(wb, plan, copied, approved=True, command_id='CDataC2Copy', session_id=wb.session_id)
        jobs = wb.manager.list()
        assert sorted(j['state'] for j in jobs) == ['FAILED', 'SUCCEEDED']
        report['fixture_jobs'] = [{k: j.get(k) for k in ('id', 'state', 'operation', 'error')} for j in jobs]
        report['related_save'] = case['related_save']
        report['status'] = 'PASS'
    finally:
        if wb is not None:
            report['shutdown'] = wb.shutdown()
        save_json(folder / 'prepare.json', report)
    assert report['shutdown']['joined'] and not report['shutdown']['pending']
    source_tree = file_tree(source)
    offline = folder / 'source-offline-preserved'
    source.rename(offline)  # only this newly created fixture, never user data
    assert not source.exists() and file_tree(offline) == source_tree
    save_json(folder / 'source-sha256.json', source_tree)
    save_json(folder / 'copy-portable-sha256.json', file_tree(copied / 'portable'))
    return copied


def selection(folder):
    rows = load_json(Path(folder) / MANIFEST)['recovery_archives']
    return next(r for r in rows if r['original_identity']['kind'] == 'data')


def review(wb, row):
    current = wb.document_read(row['document_id'])
    recovery = RawRecoveryDrafts(wb.root, wb._document_owner)
    token = buffer_token({'cells': [], 'editor_revision': 'UDataC2Fresh', 'local_draft': deepcopy(current['draft'])})
    return token, preview_resume(wb, row['archive_id'], target_identity=recovery.identity(current), buffer=token)


def execute(wb, token, proposal):
    return resume(wb, proposal, approved=True, overwrite_approved=True,
                  live_buffer=token, command_id=proposal['command_id'])


def certificate(layer):
    return layer['capsule']['acknowledged']['document']['draft']['mapping']['columns']['stress']['calibration']['source']['data_id']



def current_sources(wb, document, layer):
    """Use the actual owner freeze/resolve path for both CSV and certificate."""
    owner = wb.data_documents
    args = owner.prepare_job_arguments(document['draft'], document)  # read/verify, not import
    required = {r['data_id']: r for r in layer['capsule']['acknowledged']['data_inputs'] if r['state'] == 'RETAINED'}
    references = [args['source_ref'], *args.get('calibration_sources', [])]
    result = {}
    for ref in references:
        identifier = ref['data_id']
        source, receipt = owner.resolve_job_source(identifier, ref)
        binding = document['retained_inputs'][identifier]
        metadata = owner._folder(document['id']) / 'revisions' / binding['revision'] / binding['metadata']
        assert file_hash(source) == required[identifier]['sha256']
        assert receipt == required[identifier]['receipt']
        assert file_hash(metadata) == required[identifier]['metadata_sha256']
        result[identifier] = {'source_sha256': file_hash(source), 'metadata_sha256': file_hash(metadata),
                              'receipt_sha256': canonical_hash(receipt), 'reference': ref,
                              'text': Path(source).read_text(encoding='utf-8-sig')}
    assert set(result) == {document['draft']['data_id'], certificate(layer)}
    assert 'time,stress' in wb.document_source_preview(document['id'])['text']
    return result


def finish(folder):
    """Separate cold phase: original -> current resume/read/edit/save/Keep/close."""
    folder = Path(folder)
    original_tree = file_tree(folder / 'portable')
    report = {'phase': 'finish', 'status': 'STARTED', 'windows': 'NOT_RUN', 'qt': 'NOT_RUN', 'native': 'NOT_RUN'}
    with guarded() as calls:
        wb = open_project(folder)
        try:
            row = selection(folder)
            layers = read_archive(folder, row['archive_id'])
            cert = certificate(layers)
            assert layers['resume_permission'] == layers['discard_permission'] == 'NOT_GRANTED'
            saved_layer = read_archive(folder, row['archive_id'], facet='saved')['document']
            assert 'calibration' not in saved_layer['draft']['mapping']['columns']['stress']
            owner = wb.data_documents
            pointer = owner._folder(row['document_id']) / 'document.json'
            pointer_before = pointer.read_bytes()
            token, proposal = review(wb, row)
            packet = execute(wb, token, proposal)
            assert execute(wb, token, proposal) == packet  # actual same-command response-loss retry
            assert pointer.read_bytes() == pointer_before  # no implicit saved-head publication
            assert cert in packet['document']['retained_inputs']
            binding = packet['document']['retained_inputs'][cert]
            container = owner._verify_revision(row['document_id'], binding['revision'])
            from caelab.connection_graph import is_acknowledged_container
            assert is_acknowledged_container(container)
            assert container['portable_recovery_input_origin']['authority'] == 'HISTORY_ONLY'
            assert not (owner._folder(row['document_id']) / 'raw-recovery').exists()
            assert not packet['raw_applied'] and not packet['job_submitted'] and not packet['saved_revision_created']
            assert packet['raw']['cells'][0]['raw_text'] == '1e'
            report['current_sources_after_resume'] = current_sources(wb, packet['document'], layers)
            draft = deepcopy(packet['document']['draft'])
            draft['test_metadata']['protocol'] += ' / 사본에서 명시 편집'
            edited = command(wb, packet['document'], 'data.update', {'draft': draft})
            saved = save(wb, edited)
            assert not saved.get('unresolved_inputs'), saved.get('unresolved_inputs')
            report['current_sources_after_save'] = current_sources(wb, saved, layers)
            # Original recorded success and deliberate import failure, not a new run.
            report['run_states'] = [r['retained_state'] for r in saved['runs']]
            assert sorted(report['run_states']) == ['FAILED', 'SUCCEEDED']
            raw = deepcopy(packet['raw'])
            raw['local_draft']['test_metadata']['protocol'] = draft['test_metadata']['protocol']
            recovery = RawRecoveryDrafts(wb.root, wb._document_owner)
            keep_review = recovery.prepare([{'identity': recovery.identity(saved), 'raw': raw}])
            assert not any(t['problems'] for t in keep_review['targets']), keep_review
            kept = recovery.execute(keep_review)
            assert kept['all_kept'] and kept['close_permitted'], kept
            cid = kept['targets'][0]['capsule_id']
            assert cid != row['capsule_id']
            assert not (owner._folder(saved['id']) / 'raw-recovery' / (row['capsule_id'] + '.json')).exists()
            assert 'gain,offset' in recovery.source_preview(saved['id'], cid, cert)['text']
            assert recovery.close_permitted(keep_review, [{'identity': recovery.identity(saved), 'raw': raw}])['close_permitted']
            save_json(folder / 'data-c2-current-keep.json', {'document_id': saved['id'], 'capsule_id': cid,
                'archive_id': row['archive_id'], 'certificate_id': cert, 'raw': raw,
                'original_raw_sha256': canonical_hash(layers['capsule']['raw'])})
            report.update(status='PASS', current_keep=cid, keep_receipt=kept, raw_text='1e',
                original_raw_sha256=canonical_hash(layers['capsule']['raw']), saved_revision=saved['saved_revision'],
                implicit_saved_head_change=False, new_job_count=len(wb.manager.list()))
            assert not wb.manager.list() and wb._assistance is None and not calls
            assert file_tree(folder / 'portable') == original_tree
        finally:
            report['shutdown'] = wb.shutdown()
            report['cold_execution_calls'] = list(calls)
            save_json(folder / 'data-c2-finish.json', report)
    assert report['shutdown']['joined'] and not report['shutdown']['pending']
    return report


def recover_and_recopy(folder, destination):
    """New process: explicitly recover NEW current Keep, then publish a recopy."""
    folder, destination = Path(folder), Path(destination)
    before = file_tree(folder / 'portable')
    report = {'phase': 'recover-recopy', 'status': 'STARTED'}
    with guarded() as calls:
        wb = open_project(folder)
        try:
            q = load_json(folder / 'data-c2-current-keep.json')
            recovery = RawRecoveryDrafts(wb.root, wb._document_owner)
            current = wb.document_read(q['document_id'])
            recovered = recovery.recover(current['id'], q['capsule_id'], identity=recovery.identity(current), acknowledge_session_change=True)
            assert recovered['state'] == 'RESUME_READY', recovered
            assert recovered['raw'] == q['raw']
            assert 'gain,offset' in recovery.source_preview(current['id'], q['capsule_id'], q['certificate_id'])['text']
            original = read_archive(folder, q['archive_id'])
            assert canonical_hash(original['capsule']['raw']) == q['original_raw_sha256']
            current_sources(wb, current, original)
            choices = [{'archive_id': q['archive_id']}, {k: q[k] for k in ('document_id', 'capsule_id')}]
            plan = inspect_copy(wb, [current['id']], recovery_archives=choices)
            save_json(folder / 'data-c2-recopy-inspection.json', plan)
            assert plan['status'] == 'READY', plan
            create_copy(wb, plan, destination, approved=True, command_id='CDataC2Recopy', session_id=wb.session_id)
            assert not wb.manager.list() and wb._assistance is None and not calls
            assert file_tree(folder / 'portable') == before
            report.update(status='PASS', new_current_keep_recovered=True, recopy_status=plan['status'],
                          new_job_count=0, original_and_current_q_count=2)
        finally:
            report['shutdown'] = wb.shutdown()
            report['cold_execution_calls'] = list(calls)
            save_json(folder / 'data-c2-recover-recopy.json', report)
    assert report['shutdown']['joined'] and not report['shutdown']['pending']
    return report


def read_recopied(folder):
    """Another process/store: both Qs and current Data sources/results remain exact."""
    folder = Path(folder)
    before = file_tree(folder / 'portable')
    report = {'phase': 'read-recopied', 'status': 'STARTED'}
    with guarded() as calls:
        wb = open_project(folder)
        try:
            manifest = load_json(folder / MANIFEST)
            rows = manifest['recovery_archives']
            assert len(rows) == 2
            original_qs = []
            for row in rows:
                layer = read_archive(folder, row['archive_id'])
                assert layer['resume_permission'] == layer['discard_permission'] == 'NOT_GRANTED'
                cert = certificate(layer)
                preview = read_archive(folder, row['archive_id'], facet='source-preview', selection={'data_id': cert})
                assert 'gain,offset' in preview['text']
                assert layer['capsule']['raw']['cells'][0]['raw_text'] == '1e'
                current = wb.document_read(row['document_id'])
                current_sources(wb, current, layer)
                original_qs.append({'capsule_sha256': row['capsule_sha256'],
                    'capsule_file_sha256': row['capsule_file_sha256'],
                    'raw_sha256': canonical_hash(layer['capsule']['raw'])})
                for job in layer['capsule']['acknowledged']['jobs']:
                    retained = read_archive(folder, row['archive_id'], facet='job', selection={'job_id': job['job_id'],
                        'include_result': job['result_at_review'] == 'PUBLISHED'})
                    assert retained['job']['state_at_review'] == job['state_at_review']
            assert sorted(r['retained_state'] for r in current['runs']) == ['FAILED', 'SUCCEEDED']
            assert not wb.manager.list() and wb._assistance is None and not calls
            assert file_tree(folder / 'portable') == before
            report.update(status='PASS', archives=original_qs, new_job_count=0)
        finally:
            report['shutdown'] = wb.shutdown()
            report['cold_execution_calls'] = list(calls)
            save_json(folder / 'data-c2-read-recopied.json', report)
    assert report['shutdown']['joined'] and not report['shutdown']['pending']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['prepare', 'finish', 'recover-recopy', 'read-recopied'])
    parser.add_argument('folder', type=Path)
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args()
    if args.phase == 'prepare':
        result = {'copy': str(prepare(args.folder))}
    elif args.phase == 'finish':
        result = finish(args.folder)
    elif args.phase == 'recover-recopy':
        if args.destination is None: parser.error('--destination is required')
        result = recover_and_recopy(args.folder, args.destination)
    else:
        result = read_recopied(args.folder)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
