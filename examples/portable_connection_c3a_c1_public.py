"""C1 exact R1/R2 public fixture and owned cold process verification.

Only newly created synthetic folders are removed. Existing owners and Keep/save
commands are used; no solver/provider/native execution or GUI claim is made.
"""
from copy import deepcopy
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import sys

from caelab.workbench import Workbench
from caelab.storage import canonical_hash, load_json, save_json
from caelab.numerical_document import from_material_document
from caelab.portable_project import inspect_copy, create_copy, open_project, MANIFEST, verify_project
from caelab.portable_project_recovery import read_archive
from caelab.portable_recovery_resume import buffer_token, preview_resume, resume
from caelab.related_save_recovery import RawRecoveryDrafts
from caelab.related_save import RelatedSaveCoordinator, input_identity
from examples.portable_connection_public import command, save
from examples.portable_connection_c3a_public import raw_for

def keep(wb, docs, raws):
    recovery = RawRecoveryDrafts(wb.root, wb._document_owner)
    preview = recovery.prepare([{'identity': recovery.identity(d), 'raw': r} for d, r in zip(docs, raws)])
    assert not any(t['problems'] for t in preview['targets']), preview
    receipt = recovery.execute(preview)
    assert receipt['all_kept'], receipt
    return [{'document_id': t['document_id'], 'capsule_id': t['capsule_id']} for t in receipt['targets']]


def historical_case(folder, *, detach_q_only=False):
    """R1 Material + two different Plans, Q carries R2, later working is R3."""
    wb = Workbench(folder)
    try:
        m1 = save(wb, wb.document_open(kind='material', title='C1 원 재료'))
        p1 = save(wb, wb.document_open(kind='numerical', title='C1 첫 계획', draft=from_material_document(m1)))
        p2draft = from_material_document(m1); p2draft.update(mode='doe', count=3)
        p2 = save(wb, wb.document_open(kind='numerical', title='C1 둘째 계획', draft=p2draft))
        draft = deepcopy(m1['draft']); draft['settings']['parameters']['E'] += 200
        m2 = save(wb, command(wb, m1, 'material.update', {'draft': draft}))
        plans = []
        for i, p in enumerate((p1, p2)):
            draft = deepcopy(p['draft']); draft['material'] = {**from_material_document(m2)['material'], 'saved_revision':m2['saved_revision'],
                'input_sha256':canonical_hash(m2['draft'])}
            draft['variables'][0]['lower'] += 1 + i
            plans.append(command(wb, p, 'numerical.update', {'draft': draft}))
        coordinator = RelatedSaveCoordinator(wb.root, wb._document_owner)
        requests = [{'identity':input_identity(d), 'buffer':deepcopy(d['draft'])} for d in (m2,*plans)]
        requests[2]['buffer']['variables'][0]['value'] = ''  # actual unsubmitted-buffer gate
        reviewed = coordinator.preview(requests, receipt_id='SC1Partial')
        actual_save = wb.numerical_documents._save
        def fail_one(document):
            if document['id'] == plans[0]['id']:
                raise OSError('C1 explicit fixture Plan save failure')
            return actual_save(document)
        wb.numerical_documents._save = fail_one
        try:
            receipt = coordinator.execute(reviewed)
        finally:
            wb.numerical_documents._save = actual_save
        assert [r['state'] for r in receipt['targets']] == ['SAVED','FAILED','BLOCKED'], receipt
        raws = [raw_for(p, ['variables', 0, 'lower'], text, {'table':'계획 변수','row':0,'column':3})
                for p, text in zip(plans, ('', '1e'))]
        selections = keep(wb, plans, raws)
        draft = deepcopy(m2['draft']); draft['settings']['parameters']['E'] += 300
        m3 = save(wb, command(wb, m2, 'material.update', {'draft': draft}))
        # Undo then divergent edit removes the Q-only R2 from current/Undo/Redo.
        for p in plans:
            current = command(wb, p, 'document.undo')
            draft = deepcopy(current['draft']); draft['material'] = from_material_document(m3)['material']
            save(wb, command(wb, current, 'numerical.update', {'draft': draft}))
        if detach_q_only:
            shutil.rmtree(wb.material_documents._folder(m2['id']) / 'revisions' / m2['saved_revision'])
        return wb, {'m1':m1, 'm2':m2, 'm3':m3, 'plans':[p1,p2], 'raws':raws,
                    'q':selections, 'partial_receipt':receipt, 'selected':[{'document_id':d['id'], 'saved_revision':d['saved_revision']}
                                              for d in (m1,p1,p2)]}
    except BaseException:
        wb.shutdown()
        raise


def preview(wb, row):
    current = wb.document_read(row['document_id'])
    recovery = RawRecoveryDrafts(wb.root, wb._document_owner)
    token = buffer_token({'cells':[], 'editor_revision':'UC1Fresh', 'local_draft':deepcopy(current['draft'])})
    return token, preview_resume(wb, row['archive_id'], target_identity=recovery.identity(current), buffer=token)


def execute(wb, token, proposal):
    return resume(wb, proposal, approved=True, overwrite_approved=True,
                  live_buffer=token, command_id=proposal['command_id'])


def publish(wb, case, dest, policy='saved_only'):
    selected = case['selected'] if policy == 'saved_only' else [d['document_id'] for d in case['selected']]
    plan = inspect_copy(wb, selected, draft_policy=policy, recovery_archives=case['q'])
    assert plan['status'] == 'READY', plan['issues']
    create_copy(wb, plan, dest, approved=True, command_id='CC1copy', session_id=wb.session_id)
    return plan


def file_tree(folder):
    from caelab.evaluation import file_hash
    return {p.relative_to(folder).as_posix():file_hash(p) for p in Path(folder).rglob('*')
            if p.is_file() and p.name != 'controller.lock'}



def guarded():
    # Reuse the existing fixture tripwires BEFORE opening a cold Workbench.
    tests = str(Path(__file__).resolve().parents[1]/'tests')
    if tests not in sys.path:
        sys.path.insert(0,tests)
    from _portable_connection_c2_support import cold_guard
    return cold_guard()


def cold_check(folder, expectations, *, recopy=None):
    folder=Path(folder)
    assert not Path(expectations['removed_source']).exists()
    manifest=load_json(folder/MANIFEST); immutable=file_tree(folder/'portable')
    with guarded() as calls:
        wb=open_project(folder)
        try:
            recovery=RawRecoveryDrafts(wb.root,wb._document_owner)
            keeps=[]; originals=[]
            for row in manifest['recovery_archives']:
                layers=read_archive(folder,row['archive_id']);cap=layers['capsule']
                assert layers['resume_permission']==layers['discard_permission']=='NOT_GRANTED'
                saved=read_archive(folder,row['archive_id'],facet='saved')['document']
                expected=expectations['archives'].get(row['archive_id'])
                if expected:
                    assert layers['capsule_file_sha256']==expected['capsule_file_sha256']
                    assert cap['capsule_sha256']==expected['capsule_sha256']
                    assert cap['raw']==expected['raw']
                    assert saved['input_revision']==expected['saved_input_revision']
                    assert cap['acknowledged']['document']['input_revision']==expected['ack_input_revision']
                    assert len(cap['acknowledged']['related_save_receipts'])==1
                    assert cap['acknowledged']['related_save_receipts'][0]['snapshot']==expectations['partial_receipt']
                    originals.append(row['archive_id'])
                token,proposal=preview(wb,row); packet=execute(wb,token,proposal)
                ref=packet['document']['draft']['material']
                material=wb.material_documents._verify_revision(ref['document_id'],ref['saved_revision'])
                assert material['draft']==expectations['material_r2_draft']
                assert ref['input_revision']==material['input_revision']
                assert ref['input_sha256']==canonical_hash(material['draft'])
                assert packet['raw']['cells'][0]['raw_text']==cap['raw']['cells'][0]['raw_text']
                # An explicit current owner edit, separate from restoring raw.
                draft=deepcopy(packet['document']['draft']);draft['count']+=1
                edited=command(wb,packet['document'],'numerical.update',{'draft':draft})
                current=save(wb,edited)
                raw=deepcopy(packet['raw']);raw['local_draft']['count']=draft['count']
                q=keep(wb,[current],[raw])[0]
                keeps.append({**q,'raw_text':raw['cells'][0]['raw_text']})
            assert sorted(originals)==sorted(expectations['archives'])
            assert file_tree(folder/'portable')==immutable
            latest={r['document_id']:r for r in keeps}
            save_json(folder/'c1-current-keeps.json',list(latest.values()))
            if recopy is not None:
                choices=[{'archive_id':r['archive_id']} for r in manifest['recovery_archives']]
                choices += [{k:q[k] for k in ('document_id','capsule_id')} for q in latest.values()]
                plan=inspect_copy(wb,[r['document_id'] for r in manifest['documents']],recovery_archives=choices)
                assert plan['status']=='READY',plan['issues']
                create_copy(wb,plan,recopy,approved=True,command_id='CC1Recopy',session_id=wb.session_id)
            assert calls==[] and not wb.manager.list() and wb._assistance is None
            assert verify_project(folder)['status']=='READY'
            return {'status':'PASS','original_q_count':len(originals),'read_archives':len(manifest['recovery_archives']),
                    'distinct_plans':len(latest),'raw_texts':sorted(q['raw_text'] for q in latest.values()),
                    'current_owner_edit_save_keep':True,'immutable_archive_bytes_unchanged':True,
                    'source_store_removed':True,'job_dispatch_evaluator_dag_provider_calls':0,
                    'windows':'NOT_RUN','gui':'NOT_RUN','native':'NOT_RUN'}
        finally:
            wb.shutdown()


def reopen_keeps(folder):
    with guarded() as calls:
        wb=open_project(folder)
        try:
            recovery=RawRecoveryDrafts(wb.root,wb._document_owner)
            rows=load_json(Path(folder)/'c1-current-keeps.json')
            for q in rows:
                current=wb.document_read(q['document_id'])
                response=recovery.recover(current['id'],q['capsule_id'],identity=recovery.identity(current),
                                          acknowledge_session_change=True)
                assert response['state']=='RESUME_READY',response
                assert response['raw']['cells'][0]['raw_text']==q['raw_text']
            assert calls==[] and not wb.manager.list()
            return {'status':'PASS','reopened_current_keeps':len(rows),'job_dispatch_evaluator_dag_provider_calls':0}
        finally:
            wb.shutdown()


def owned_child(args, timeout=40):
    proc=subprocess.Popen([sys.executable,'-B','-m','examples.portable_connection_c3a_c1_public',*args],
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
    try:
        out,err=proc.communicate(timeout=timeout)
        if proc.returncode:
            raise RuntimeError(out+'\n'+err)
        return json.loads(out)
    finally:
        if proc.poll() is None: proc.kill()
        proc.wait(timeout=5)
        if proc.stdout: proc.stdout.close()
        if proc.stderr: proc.stderr.close()


def build_public(output):
    output=Path(output).absolute();output.mkdir(exist_ok=False)
    source,first,second=[output/n for n in ('원본','이동 사본','재복사')]
    with guarded():
        wb,case=historical_case(source,detach_q_only=True)
        try:
            publish(wb,case,first)
            expected={'removed_source':str(source),'material_r2_draft':case['m2']['draft'],
                      'partial_receipt':case['partial_receipt'],'archives':{}}
            for row in load_json(first/MANIFEST)['recovery_archives']:
                value=read_archive(first,row['archive_id']);cap=value['capsule']
                expected['archives'][row['archive_id']]={
                    'capsule_file_sha256':value['capsule_file_sha256'],'capsule_sha256':cap['capsule_sha256'],
                    'raw':cap['raw'],'saved_input_revision':cap['acknowledged']['saved_reference']['input_revision'],
                    'ack_input_revision':cap['acknowledged']['document']['input_revision']}
        finally:
            wb.shutdown()
    shutil.rmtree(source)  # ONLY this example's newly created synthetic source.
    expected_path=output/'expectations.json';save_json(expected_path,expected)
    result={'first_cold':owned_child(['--cold',str(first),'--expectations',str(expected_path),'--recopy',str(second)]),
            'first_keep_reopen':owned_child(['--keeps',str(first)])}
    shutil.rmtree(first)  # This example's first copy is also unavailable on second cold.
    result['second_cold']=owned_child(['--cold',str(second),'--expectations',str(expected_path)])
    result['second_keep_reopen']=owned_child(['--keeps',str(second)])
    result['first_copy_also_removed_before_second_cold']=True
    save_json(output/'verification.json',result)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path);parser.add_argument('--cold',type=Path)
    parser.add_argument('--expectations',type=Path);parser.add_argument('--recopy',type=Path)
    parser.add_argument('--keeps',type=Path);args=parser.parse_args()
    if args.output: result=build_public(args.output)
    elif args.keeps: result=reopen_keeps(args.keeps)
    elif args.cold and args.expectations:
        result=cold_check(args.cold,load_json(args.expectations),recopy=args.recopy)
    else: parser.error('Use --output NEW_FOLDER, --cold COPY --expectations FILE, or --keeps COPY')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
