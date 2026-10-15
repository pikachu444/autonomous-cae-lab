"""Public C3A owner+Q fixture. Only new user-selected folders are created.

Two tiny real file-table imports (one deliberately failed), zero native/provider
or Numerical execution. The related-save write failure is explicitly injected.
All Workbench instances and subprocesses owned by this example close in finally.
"""
from __future__ import annotations
from copy import deepcopy
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from caelab.portable_project import inspect_copy, create_copy, open_project, MANIFEST, verify_project
from caelab.portable_project_recovery import read_archive, archive_row
from caelab.portable_recovery_resume import buffer_token, preview_resume, resume
from caelab.related_save import RelatedSaveCoordinator, input_identity
from caelab.related_save_recovery import RawRecoveryDrafts
from caelab.storage import canonical_hash, load_json, save_json
from examples.portable_connection_public import create_public_store, command, save


def raw_for(document, path, text, position, *, channel=None):
    value = document['draft']
    for key in path:
        value = value[key]
    raw = {'cells': [{'field_path': path, 'original_value': deepcopy(value), 'original_exists': True,
        'raw_text': text, 'position': position, 'editor_kind': 'unfinished'}],
        'local_draft': deepcopy(document['draft']),
        'focus': {'field_path': path, 'cursor': len(text), 'selection': [-1, 0]},
        'selection': {'channel': channel, 'tab': 0, 'mapping': []} if channel else
                     {'coefficients': [], 'history': []} if document['kind'] == 'material' else []}
    raw['editor_revision'] = 'U' + canonical_hash(raw)
    return raw


def create_case(folder):
    wb, docs = create_public_store(folder)
    try:
        # Preserve the actual input.json whitespace separately from canonical receipt.
        for path in (wb.root / 'inputs').glob('*/input.json'):
            path.write_text(json.dumps(load_json(path), ensure_ascii=False, separators=(',', ':')) + '\n\n', encoding='utf-8')
        for name, amount in (('material', 20), ('plan', 30), ('second_plan', 40)):
            d = docs[name]; draft = deepcopy(d['draft'])
            if name == 'material': draft['settings']['parameters']['E'] += amount
            else: draft['variables'][0]['value'] += amount
            docs[name] = command(wb, d, 'material.update' if name == 'material' else 'numerical.update', {'draft': draft})
        coordinator = RelatedSaveCoordinator(wb.root, wb._document_owner)
        req = [{'identity': input_identity(docs[name]), 'buffer': deepcopy(docs[name]['draft'])}
               for name in ('material', 'plan', 'second_plan')]
        req[2]['buffer']['variables'][0]['value'] = ''  # real unapplied-buffer gate
        preview = coordinator.preview(req, receipt_id='Sc3aPartial')
        original_save = wb.numerical_documents._save
        def fail_one(document):
            if document['id'] == docs['plan']['id']:
                raise OSError('PUBLIC C3A injected Plan write failure; no success fabricated')
            return original_save(document)
        wb.numerical_documents._save = fail_one
        try:
            receipt = coordinator.execute(preview)
        finally:
            wb.numerical_documents._save = original_save
        assert receipt['state'] == 'PARTIAL', receipt
        for name in ('material', 'plan', 'second_plan'):
            d = wb.document_read(docs[name]['id']); draft = deepcopy(d['draft'])
            if name == 'material': draft['settings']['parameters']['E'] += 11
            else: draft['variables'][0]['lower'] += 7 if name == 'plan' else 9
            op = 'material.update' if name == 'material' else 'numerical.update'
            d = command(wb, d, op, {'draft': draft})
            more = deepcopy(draft)
            if name == 'material': more['settings']['parameters']['E'] += 12
            else: more['variables'][0]['lower'] += 13
            d = command(wb, d, op, {'draft': more})
            docs[name] = command(wb, d, 'document.undo')  # distinct current + Undo + Redo
        d = docs['data']; draft = deepcopy(d['draft'])
        draft['mapping']['columns']['stress']['scale'] = 1.
        # Declared current calibration (not applied to the old runs).
        cert = wb.upload('공개 보정 근거.csv', b'gain,offset\n1,0\n')
        from caelab.experiment_calibration import default_calibration
        calibration = default_calibration('MPa')
        calibration.update(a=1., input_unit='MPa', coefficient_input_unit='MPa', x0_unit='MPa',
                           source={'data_id': cert['id'], 'sha256': cert['sha256'], 'name': cert['name']})
        draft['mapping']['columns']['stress']['calibration'] = calibration
        d = command(wb, d, 'data.update', {'draft': draft})
        more = deepcopy(draft); more['test_metadata']['protocol'] = '원 Undo Redo 자료'
        d = command(wb, d, 'data.update', {'draft': more})
        docs['data'] = command(wb, d, 'document.undo')
        raw = {
            'data': raw_for(docs['data'], ['mapping','columns','stress','scale'], '1e',
                            {'table':'mapping','row':1,'column':8}, channel='stress'),
            'material': raw_for(docs['material'], ['settings','parameters','E'], '1e',
                                {'table':'재료 계수','row':0,'column':1}),
            'plan': raw_for(docs['plan'], ['variables',0,'lower'], '',
                            {'table':'계획 변수','row':0,'column':3}),
            'second_plan': raw_for(docs['second_plan'], ['variables',0,'lower'], 'invalid',
                                   {'table':'계획 변수','row':0,'column':3})}
        raw['data']['paste'] = {'raw_text': r'C:\unapproved\not-collected.csv', 'committed': False}
        recovery = RawRecoveryDrafts(wb.root, wb._document_owner)
        requests = [{'identity': recovery.identity(docs[name]), 'raw': raw[name]}
                    for name in ('data','material','plan','second_plan')]
        review = recovery.prepare(requests, review_id='Rc3aFourOwners')
        assert not any(t['problems'] for t in review['targets']), review
        kept = recovery.execute(review)
        assert kept['all_kept'] and kept['close_permitted'], kept
        selections = [{'document_id': t['document_id'], 'capsule_id': t['capsule_id']} for t in kept['targets']]
        return wb, {'documents': docs, 'raw': raw, 'recovery_selections': selections,
                    'related_save': receipt, 'keep': kept, 'keep_review': review}
    except BaseException:
        wb.shutdown(); raise


def make_copy(wb, case, destination, *, command_id='Cc3aCopy'):
    ids = [case['documents'][k]['id'] for k in ('data','material','plan','second_plan')]
    plan = inspect_copy(wb, ids, recovery_archives=case['recovery_selections'])
    if plan['status'] != 'READY':
        raise AssertionError(plan)
    return create_copy(wb, plan, destination, approved=True, command_id=command_id, session_id=wb.session_id)


def cold_check(folder, *, recopy=None):
    folder = Path(folder); manifest = load_json(folder / MANIFEST)
    wb = open_project(folder)
    try:
        recovery = RawRecoveryDrafts(wb.root, wb._document_owner)
        assert not wb.manager.list() and wb._assistance is None
        results = []
        for row in manifest['recovery_archives']:
            original = read_archive(folder, row['archive_id'])
            capsule = original['capsule']; document = wb.document_read(row['document_id'])
            assert original['resume_permission'] == original['discard_permission'] == 'NOT_GRANTED'
            assert original['verification'] == 'VERIFIED'
            ack = capsule['acknowledged']; assert ack['document']['_undo'] and ack['document']['_redo']
            saved = read_archive(folder, row['archive_id'], facet='saved')['document']
            saved_ack_differ = canonical_hash(saved['draft']) != canonical_hash(ack['document']['draft'])
            if document['kind'] == 'data':
                data = read_archive(folder, row['archive_id'], facet='source-preview',
                    selection={'data_id': ack['document']['draft']['data_id']})
                assert '2.4' in data['text']
                parsed = read_archive(folder, row['archive_id'], facet='table-source')
                assert parsed['interpretation'] == 'READ_ONLY_PARSE_NOT_IMPORT'
                for j in ack['jobs']:
                    job = read_archive(folder, row['archive_id'], facet='job', selection={'job_id':j['job_id']})['job']
                    assert job['state_at_review'] == j['state_at_review']
                    if j['result_at_review'] == 'PUBLISHED':
                        read_archive(folder, row['archive_id'], facet='job', selection={'job_id':j['job_id'],'include_result':True})
            else:
                assert all(r['snapshot']['state'] == 'PARTIAL' for r in ack['related_save_receipts'])
            # Headless transport is not a fake GUI rendering claim. The separate
            # Qt host consumes exactly this packet through existing restore APIs.
            clean_raw = {'cells': [], 'editor_revision': 'Uc3aFreshView', 'local_draft': deepcopy(document['draft'])}
            token = buffer_token(clean_raw)
            preview = preview_resume(wb, row['archive_id'], target_identity=recovery.identity(document), buffer=token)
            packet = resume(wb, preview, approved=True, overwrite_approved=True, live_buffer=token, command_id=preview['command_id'])
            assert packet['raw']['cells'][0]['raw_text'] == capsule['raw']['cells'][0]['raw_text']
            assert not packet['raw_applied'] and not packet['job_submitted']
            # New current Keep is an explicit independent action, not old authority.
            current = save(wb, packet['document'])  # explicit ACK save, never raw apply
            review = recovery.prepare([{'identity': recovery.identity(current), 'raw': packet['raw']}])
            assert not any(t['problems'] for t in review['targets']), review
            kept = recovery.execute(review); assert kept['all_kept'], kept
            assert kept['targets'][0]['capsule_id'] != capsule['capsule_id']
            results.append({'archive_id':row['archive_id'],'kind':document['kind'],
                'raw_text':capsule['raw']['cells'][0]['raw_text'],
                'original_capsule_sha256':capsule['capsule_sha256'], 'saved_ack_differ':saved_ack_differ,
                'document_id':row['document_id'], 'current_keep':kept['targets'][0]['capsule_id']})
        assert not wb.manager.list() and wb._assistance is None
        if recopy is not None:
            chosen = [{'archive_id':row['archive_id']} for row in manifest['recovery_archives']]
            chosen += [{'document_id':r['document_id'],'capsule_id':r['current_keep']} for r in results]
            plan = inspect_copy(wb, [r['document_id'] for r in manifest['documents']], recovery_archives=chosen)
            assert plan['status'] == 'READY', plan
            create_copy(wb, plan, recopy, approved=True, command_id='Cc3aRecopy', session_id=wb.session_id)
        save_json(folder / 'c3a-example-current-keeps.json', results)
        assert verify_project(folder)['status'] == 'READY'
        return {'status':'PASS','archives':results,'new_jobs':0,'provider_calls':0,
                'gui_rendering':'NOT_RUN','native':'NOT_RUN','original_authority':'NOT_GRANTED'}
    finally:
        wb.shutdown()


def current_keep_check(folder):
    wb = open_project(folder)
    try:
        recovery = RawRecoveryDrafts(wb.root, wb._document_owner)
        rows = load_json(Path(folder) / 'c3a-example-current-keeps.json')
        # Multiple explicitly retained original Qs may address the same editing
        # owner. Only the last local Keep corresponds to its CURRENT base.
        latest = {r['document_id']:r for r in rows}
        for did,row in latest.items():
            doc = wb.document_read(did)
            result = recovery.recover(did,row['current_keep'],identity=recovery.identity(doc),
                                      acknowledge_session_change=True)
            assert result['state']=='RESUME_READY', result
            assert result['raw']['cells'][0]['raw_text']==row['raw_text']
        assert not wb.manager.list() and wb._assistance is None
        return {'current_owner_keep_reopened':len(latest),'new_jobs':0,'old_authority_used':False}
    finally:
        wb.shutdown()


def owned_child(args, timeout=60):
    process = subprocess.Popen([sys.executable, '-B', '-m', __name__ if __name__ != '__main__' else
        'examples.portable_connection_c3a_public', *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8')
    try:
        out, err = process.communicate(timeout=timeout)
        if process.returncode:
            raise RuntimeError(out + '\n' + err)
        return json.loads(out)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        if process.stdout: process.stdout.close()
        if process.stderr: process.stderr.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--cold', type=Path)
    parser.add_argument('--recopy', type=Path)
    parser.add_argument('--current-keeps', type=Path)
    args = parser.parse_args()
    if args.current_keeps:
        result = current_keep_check(args.current_keeps)
    elif args.cold:
        result = cold_check(args.cold, recopy=args.recopy)
    else:
        if args.output is None: parser.error('--output NEW_FOLDER or --cold COPY is required')
        args.output.mkdir(exist_ok=False)
        source, first, second = [args.output / x for x in ('원본', '이동 사본', '재복사')]
        wb, case = create_case(source)
        try: make_copy(wb, case, first)
        finally: wb.shutdown()
        shutil.rmtree(source)  # ONLY this newly created public synthetic store
        result = {'first_cold':owned_child(['--cold',str(first),'--recopy',str(second)])}
        result['first_current_keep_cold'] = owned_child(['--current-keeps',str(first)])
        shutil.rmtree(first)
        result['second_cold'] = owned_child(['--cold',str(second)])
        result['second_current_keep_cold'] = owned_child(['--current-keeps',str(second)])
        result['source_unavailable_in_both_cold_processes'] = True
        save_json(args.output / 'verification.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
