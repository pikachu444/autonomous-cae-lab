"""Synthetic C1 acceptance. Only deletes the example's newly-created source store.

Run with --output NEW_DIRECTORY. --cold-check is used by a separate process.
No provider/native solver is submitted; real success/failure are CSV import jobs.
"""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys

from caelab.connection_graph import SnapshotReader, build_graph
from caelab.connection_graph_edit import target_selection, source_selection, preview_edit, apply_edit
from caelab.connection_graph_view import read_view, save_view, merge_bindings
from caelab.numerical_document import material_reference
from caelab.portable_project import MANIFEST, inspect_copy, create_copy, open_project, verify_project
from caelab.portable_project_drafts import WORKING, snapshot_bytes
from caelab.evaluation import file_hash
from caelab.storage import canonical_hash, load_json, save_json
from examples.portable_connection_public import create_public_store, command, save, wait


def dirty_fixture(folder):
    wb, docs = create_public_store(folder)
    try:
        # Saved E remains in its original revision, acknowledged E is not saved.
        draft = deepcopy(docs['material']['draft'])
        draft['settings']['parameters']['E'] += 321.
        docs['material'] = command(wb, docs['material'], 'material.update', {'draft': draft})
        # A second explicitly registered input used only by acknowledged history.
        source = wb.upload('합성 추가 원자료.csv', b'time,stress\n0,0\n1,2.5\n2,5\n')
        draft = deepcopy(docs['data']['draft'])
        draft['data_id'] = source['id']
        draft['test_metadata']['protocol'] = '저장 전 받아들인 추가 자료'
        docs['data'] = command(wb, docs['data'], 'data.update', {'draft': draft})
        for column, expected in ((1, 'SUCCEEDED'), (20, 'FAILED')):
            draft['mapping']['columns']['stress']['column'] = column
            docs['data'] = command(wb, docs['data'], 'data.update', {'draft': draft})
            response = wb.document_command(docs['data']['id'], 'data.import', {},
                session_id=wb.session_id, expected_generation=docs['data']['generation'])
            assert wait(wb, response['job']['id'])['state'] == expected
            docs['data'] = wb.document_read(docs['data']['id'])
        # Invalid/unknown editable payload was explicitly acknowledged by owner.
        # This is NOT a raw Qt-cell buffer or a claimed C01 capsule.
        draft['mapping']['columns']['stress']['column'] = '1e'
        draft['test_metadata'].update(temperature='UNKNOWN', future_note={'blank': '', 'unconfirmed': None})
        docs['data'] = command(wb, docs['data'], 'data.update', {'draft': draft})
        plan = deepcopy(docs['plan']['draft'])
        plan['material'] = material_reference(docs['material'])
        docs['plan'] = command(wb, docs['plan'], 'numerical.update', {'draft': plan})
        plan2 = deepcopy(docs['second_plan']['draft']); plan2['count'] = '1e'
        docs['second_plan'] = command(wb, docs['second_plan'], 'numerical.update', {'draft': plan2})
        graph = build_graph(wb)
        view = read_view(wb)
        state, keys = merge_bindings(graph, view['state'])
        material_key = keys['document/' + docs['material']['id']]
        state['positions'][material_key] = [421.5, -112.25]
        state['selected'] = material_key
        state['checked_documents'] = [docs[k]['id'] for k in ('data', 'material', 'plan', 'second_plan')]
        state['filter'] = '공개'
        state['panel']['tab'] = 1
        save_view(wb, state, scope=view['scope'], expected_revision=view['revision'],
            expected_sha256=view['state_sha256'], command_id='Csynthetic_layout')
        return wb, docs
    except BaseException:
        wb.shutdown(); raise


def cold_check(folder, *, edit=True):
    folder = Path(folder)
    manifest = load_json(folder / MANIFEST)
    wb = open_project(folder)
    try:
        assert wb._assistance is None and not wb.manager.list()
        reader = SnapshotReader(wb)
        records = {r['source_document_id']: r for r in manifest['documents']}
        documents = {r['kind']: wb.document_read(r['document_id']) for r in records.values() if r['kind'] != 'numerical'}
        material, data = documents['material'], documents['data']
        base = reader.revision(material['id'], material['saved_revision'])
        assert material['dirty'] and base['draft']['settings']['parameters']['E'] + 321. == material['draft']['settings']['parameters']['E']
        assert data['dirty'] and data['draft']['mapping']['columns']['stress']['column'] == '1e'
        assert data['draft']['test_metadata']['temperature'] == 'UNKNOWN'
        assert data['draft']['test_metadata']['future_note'] == {'blank': '', 'unconfirmed': None}
        assert wb.document_source_preview(data['id'])['retained'] is True
        state = read_view(wb)['state']
        assert state['positions'][state['selected']] == [421.5, -112.25]
        assert state['filter'] == '공개' and state['panel']['tab'] == 1
        selected_anchor = next(x['anchor'] for x in state['bindings'] if x['view_key'] == state['selected'])
        assert selected_anchor['document_id'] == material['id']
        states, result_hashes = [], {}
        for run in data['runs']:
            job = wb.desktop.job_record(run['job_id']); states.append(job['state'])
            if run.get('retained_result'):
                result = wb.document_result(data['id'], run['job_id'])
                assert result['responses']['stress']['unit'] == 'MPa'
                assert result['responses']['stress']['frame'] == 'material_cartesian'
                result_hashes[run['job_id']] = canonical_hash(result)
            if job['state'] == 'FAILED':
                assert job['error']['message']
        assert sorted(states) == ['FAILED', 'FAILED', 'SUCCEEDED', 'SUCCEEDED']
        plans = [wb.document_read(r['document_id']) for r in records.values() if r['kind'] == 'numerical']
        plan = next(p for p in plans if p['draft']['mode'] == 'fit')
        assert plan['dirty'] and plan['draft']['material'] == material_reference(material)
        assert wb.numerical_documents.job_arguments(plan['draft'])['experiments'][0]['observations']['unit'] == 'MPa'
        invalid_plan = next(p for p in plans if p['draft']['mode'] == 'doe')
        assert invalid_plan['dirty'] and invalid_plan['draft']['count'] == '1e' and invalid_plan['diagnostics']
        # Every original acknowledged snapshot remains archived byte-for-byte.
        for old_id, record in records.items():
            raw = load_json(folder / 'portable/originals' / old_id / WORKING / 'document.json')
            live = reader.current(record['document_id'])
            assert live['generation'] == raw['generation']
            assert len(live['_undo']) == len(raw['_undo']) and len(live['_redo']) == len(raw['_redo'])
        before_domain = {p.relative_to(folder).as_posix(): file_hash(p) for p in (folder / 'workbench/documents').rglob('*') if p.is_file()}
        view = read_view(wb); new_state = deepcopy(view['state'])
        new_state['positions'][new_state['selected']][0] += 8.
        save_view(wb, new_state, scope=view['scope'], expected_revision=view['revision'],
            expected_sha256=view['state_sha256'], command_id='Ccold_layout')
        after_domain = {p.relative_to(folder).as_posix(): file_hash(p) for p in (folder / 'workbench/documents').rglob('*') if p.is_file()}
        assert before_domain == after_domain
        if edit:
            # Explicit owner edit -> undo returns the acknowledged draft, not saved base.
            for document in (material, data, plan, invalid_plan):
                original_draft = deepcopy(document['draft'])
                draft = deepcopy(original_draft)
                if document['kind'] == 'material': draft['settings']['parameters']['E'] += 5.
                elif document['kind'] == 'data': draft['test_metadata']['protocol'] = '재개 편집'
                else: draft['seed'] += 1
                op = wb._document_owner(document['id']).update_operation
                changed = command(wb, document, op, {'draft': draft})
                undone = command(wb, changed, 'document.undo')
                assert undone['draft'] == original_draft and undone['can_redo']
                saved = save(wb, undone)
                assert not saved['dirty']
            for job, digest in result_hashes.items():
                assert canonical_hash(wb.document_result(data['id'], job)) == digest
        assert not wb.manager.list() and wb._assistance is None
        return {'status': 'PASSED', 'saved_base_and_dirty_draft_separate': True,
                'states': sorted(states), 'history_generation_preserved': True,
                'unknown_invalid_payload_preserved': True, 'units': ['MPa', 's'],
                'layout_restored_without_domain_write': before_domain == after_domain,
                'owner_edit_undo_save': edit, 'jobs_on_reopen': 0,
                'capsule': 'NOT_INTEGRATED', 'engineering_release': 'NOT_RELEASED'}
    finally:
        wb.shutdown()


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output'); parser.add_argument('--cold-check')
    args = parser.parse_args(argv)
    if args.cold_check:
        print(json.dumps(cold_check(args.cold_check), ensure_ascii=False)); return 0
    if not args.output: parser.error('--output NEW_DIRECTORY required')
    root = Path(args.output).absolute(); root.mkdir(parents=False, exist_ok=False)
    original = root / '합성 원본'; wb, docs = dirty_fixture(original)
    try:
        chosen = [docs[k]['id'] for k in ('data', 'material', 'plan', 'second_plan')]
        inventory = inspect_copy(wb, chosen)
        if inventory['status'] != 'READY': raise RuntimeError(inventory)
        create_copy(wb, inventory, root / '이동 전', approved=True,
            command_id='Cc1_public', session_id=wb.session_id)
    finally: wb.shutdown()
    shutil.rmtree(original)  # Created exclusively above. Never a supplied store.
    moved = root / '한글 공백 초안 사본'; (root / '이동 전').rename(moved)
    # Keep a distributable dirty-draft copy; run destructive editing in its clone.
    checking = root / '별도 프로세스 편집 검사'; shutil.copytree(moved, checking)
    process = subprocess.run([sys.executable, '-m', __spec__.name, '--cold-check', str(checking)],
                             text=True, encoding='utf-8', capture_output=True, timeout=90, check=True)
    result = json.loads(process.stdout)
    result.update(original_store_deleted=not original.exists(), moved_workspace=str(moved),
                  separate_process=True, verification_after_edit=verify_project(checking)['status'])
    save_json(root / 'c1-public-check.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0


if __name__ == '__main__':
    raise SystemExit(main())
