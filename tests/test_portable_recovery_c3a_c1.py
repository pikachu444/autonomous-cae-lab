"""C1 actual-owner counterexamples. No Qt, native, solver or provider dispatch."""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
import shutil
import pytest

from caelab.workbench import Workbench
from caelab.storage import canonical_hash, load_json, save_json, utc_now
from caelab.numerical_document import from_material_document
from caelab.portable_project import inspect_copy, create_copy, open_project, MANIFEST
from caelab.portable_project_recovery import read_archive, projected_buffer
from caelab.portable_recovery_resume import buffer_token, preview_resume, resume
from caelab.related_save_recovery import RawRecoveryDrafts
from caelab.related_save import input_identity
from examples.portable_connection_public import command, save
from examples.portable_connection_c3a_public import raw_for
from _portable_connection_c2_support import cold_guard
from examples.portable_connection_c3a_c1_public import (keep, historical_case, preview, execute, publish, file_tree)












def test_r1_saved_only_original_counterexample(tmp_path):
    source, target = tmp_path/'원본', tmp_path/'사본'
    wb, case = historical_case(source)
    try:
        publish(wb, case, target)
    finally:
        wb.shutdown()
    shutil.rmtree(source)
    with cold_guard() as calls:
        wb = open_project(target)
        try:
            for row in load_json(target/MANIFEST)['recovery_archives']:
                token, proposal = preview(wb, row)
                packet = execute(wb, token, proposal)
                material = packet['document']['draft']['material']
                exact = wb.material_documents._verify_revision(material['document_id'], material['saved_revision'])
                assert exact['draft'] == case['m2']['draft']
                assert exact['input_revision'] == material['input_revision']
            assert calls == []
        finally:
            wb.shutdown()


@contextmanager
def material_copy(tmp_path):
    source, target = tmp_path/'original', tmp_path/'copy'
    wb = Workbench(source)
    try:
        saved = save(wb, wb.document_open(kind='material'))
        draft = deepcopy(saved['draft']); draft['settings']['parameters']['E'] += 20
        ack = command(wb, saved, 'material.update', {'draft': draft})
        raw = raw_for(ack, ['settings','parameters','E'], '1e', {'table':'parameters','row':0,'column':1})
        q = keep(wb, [ack], [raw])
        plan = inspect_copy(wb, [saved['id']], draft_policy='saved_only', recovery_archives=q)
        assert plan['status'] == 'READY', plan['issues']
        create_copy(wb, plan, target, approved=True, command_id='CC1material', session_id=wb.session_id)
    finally:
        wb.shutdown()
    shutil.rmtree(source)
    with cold_guard() as calls:
        wb = open_project(target)
        try:
            yield wb, load_json(target/MANIFEST)['recovery_archives'][0], calls
        finally:
            wb.shutdown()


def test_r2_lost_reply_then_actual_evaluate_changes_runs(tmp_path, monkeypatch):
    with material_copy(tmp_path) as (wb, row, calls):
        token, proposal = preview(wb, row)
        first = execute(wb, token, proposal)  # committed reply deliberately not delivered to UI
        before = input_identity(first['document'])
        submitted = []
        def bounded_submit(operation, arguments, **kwargs):
            submitted.append((operation, deepcopy(arguments)))
            return {'id':'JC1BoundedFailed', 'operation':operation, 'arguments':deepcopy(arguments),
                    'created_utc':utc_now(), 'state':'FAILED', 'result_refs':[],
                    'error':{'message':'C1 bounded fixture; no evaluator dispatched'}}
        monkeypatch.setattr(wb.material_documents, 'submit', bounded_submit)
        current = command(wb, first['document'], 'material.evaluate')
        assert len(submitted) == 1 and len(current['runs']) == 1 and input_identity(current) == before
        durable = wb.material_documents.acknowledged_state(current['id'])['document']
        with pytest.raises(ValueError, match='after the recorded'):
            execute(wb, token, proposal)
        assert wb.material_documents.acknowledged_state(current['id'])['document'] == durable
        assert calls == [] and not wb.manager.list()


@pytest.mark.parametrize('policy', ['saved_only', 'acknowledged'])
@pytest.mark.parametrize('detach', [False, True])
def test_r1_q_only_reference_and_source_evidence(tmp_path, policy, detach):
    from caelab.connection_graph_refs import document_references
    source, target = tmp_path/'original', tmp_path/'copy'
    wb, case = historical_case(source, detach_q_only=detach)
    try:
        for p in case['plans']:
            doc = wb.numerical_documents.acknowledged_state(p['id'])['document']
            assert all(t.value.get('input_revision') != case['m2']['input_revision']
                       for t in document_references(doc, include_history=True))
        plan = publish(wb, case, target, policy)
        exact = (case['m2']['id'], case['m2']['saved_revision'])
        assert exact in {(r['document_id'],r['saved_revision']) for r in plan['revisions']}
        assets = [r for r in plan['files'] if (r['document_id'],r['saved_revision']) == exact]
        assert assets and all(('.assets/' in r['path']) == detach for r in assets)
        # The editable head is still the expressly selected R1/R3, not Q's R2.
        manifest = load_json(target/MANIFEST)
        m = next(d for d in manifest['documents'] if d['kind'] == 'material')
        expected = case['m1'] if policy == 'saved_only' else case['m3']
        assert m['source_saved_revision'] == expected['saved_revision']
    finally:
        wb.shutdown()
    shutil.rmtree(source)
    with cold_guard() as calls:
        wb = open_project(target)
        try:
            texts = {}
            for row in manifest['recovery_archives']:
                cap = read_archive(target,row['archive_id'])['capsule']
                old_saved = read_archive(target,row['archive_id'],facet='saved')['document']
                assert old_saved['draft']['material']['input_revision'] == case['m1']['input_revision']
                assert cap['acknowledged']['document']['draft']['material']['input_revision'] == case['m2']['input_revision']
                token, proposal = preview(wb, row); packet = execute(wb, token, proposal)
                material = packet['document']['draft']['material']
                exact = wb.material_documents._verify_revision(material['document_id'],material['saved_revision'])
                assert material['input_revision'] == exact['input_revision']
                assert canonical_hash(material['draft']) == material['input_sha256'] == canonical_hash(exact['draft'])
                assert exact['draft'] == case['m2']['draft']
                assert packet['raw']['local_draft']['material'] == material
                texts[row['original_identity']['document_id']] = packet['raw']['cells'][0]['raw_text']
                saved = save(wb, packet['document'])
                keep(wb, [saved], [packet['raw']])
            assert texts == {p['id']:text for p,text in zip(case['plans'],('', '1e'))}
            assert calls == [] and not wb.manager.list()
        finally:
            wb.shutdown()




def test_r1_unselected_peer_and_duplicate_do_not_change_any_q(tmp_path):
    from caelab.portable_recovery_archive import inspect_capsule
    wb, case = historical_case(tmp_path/'original')
    try:
        before = file_tree(wb.workspace)
        without_material = case['selected'][1:]
        plan = inspect_copy(wb, without_material, draft_policy='saved_only', recovery_archives=case['q'])
        assert plan['status'] == 'BLOCKED'
        assert any(i['code'] == 'DOCUMENT_NOT_SELECTED' for i in plan['issues']), plan['issues']
        duplicate = inspect_copy(wb, case['selected'], draft_policy='saved_only',
                                 recovery_archives=[case['q'][0],case['q'][0],case['q'][1]])
        assert duplicate['status'] == 'BLOCKED'
        assert any('once' in i['message'] for i in duplicate['issues'])
        for q in case['q']:
            path = wb.numerical_documents._folder(q['document_id'])/'raw-recovery'/(q['capsule_id']+'.json')
            assert inspect_capsule(path)['verification'] == 'VERIFIED'
        assert file_tree(wb.workspace) == before
        assert inspect_copy(wb,case['selected'],draft_policy='saved_only',recovery_archives=case['q'])['status'] == 'READY'
    finally:
        wb.shutdown()


@pytest.mark.parametrize('fault', ['missing_asset', 'changed_asset', 'changed_live_revision'])
def test_r1_tamper_never_falls_back_to_new_current_values(tmp_path, fault):
    wb, case = historical_case(tmp_path/'original')
    try:
        q = case['q'][0]
        folder = wb.numerical_documents._folder(q['document_id'])/'raw-recovery'/(q['capsule_id']+'.assets')
        name = f"documents/{case['m2']['id']}/revisions/{case['m2']['saved_revision']}/document.json"
        path = folder/name
        if fault == 'changed_live_revision':
            path = wb.material_documents._folder(case['m2']['id'])/'revisions'/case['m2']['saved_revision']/'document.json'
        if fault == 'missing_asset': path.unlink()
        else: path.write_bytes(path.read_bytes()+b' ')
        before = file_tree(wb.workspace)
        plan = inspect_copy(wb,case['selected'],draft_policy='saved_only',recovery_archives=case['q'])
        assert plan['status'] == 'BLOCKED', plan
        assert file_tree(wb.workspace) == before
    finally:
        wb.shutdown()


def test_r1_unapplied_local_reference_never_expands_or_gains_mapping(tmp_path):
    wb, case = historical_case(tmp_path/'original')
    try:
        # Another actual Keep: unsubmitted local_draft points at an arbitrary
        # owner/path, while its acknowledged binding remains a verified M/R2.
        p = wb.document_read(case['plans'][0]['id'])
        raw = raw_for(p,['variables',0,'lower'],'1e',{'table':'variables','row':0,'column':3})
        foreign = {'document_id':'MUnapproved','saved_revision':'RRawOnly','input_revision':'IRawOnly',
                   'generation':0,'input_sha256':'0'*64,'draft':{'path':'C:/do-not-collect.csv'}}
        raw['local_draft']['material'] = deepcopy(foreign)
        q = keep(wb,[p],[raw])
        case['q'] = q
        target = tmp_path/'copy'; publish(wb,case,target)
        row = load_json(target/MANIFEST)['recovery_archives'][0]
        _, _, draft, restored = projected_buffer(target,row['archive_id'])
        assert restored['local_draft']['material'] == foreign
        assert draft['material']['document_id'] != p['draft']['material']['document_id']
        assert not any('MUnapproved' in r['path'] or 'do-not-collect' in r['path']
                       for r in load_json(target/MANIFEST)['files'])
    finally:
        wb.shutdown()


@pytest.mark.parametrize('base_change', [False, True])
def test_r2_true_lost_reply_exact_retry_full_owner_state(tmp_path, base_change):
    with material_copy(tmp_path) as (wb,row,calls):
        if not base_change:
            draft = read_archive(wb.workspace,row['archive_id'])['capsule']['acknowledged']['document']['draft']
            current = wb.document_read(row['document_id'])
            command(wb,current,'material.update',{'draft':draft})
        token, proposal = preview(wb,row)
        assert proposal['base_change_required'] == base_change
        packet = execute(wb,token,proposal)
        before = file_tree(wb.root/'documents')
        assert execute(wb,token,proposal) == packet
        assert file_tree(wb.root/'documents') == before and calls == []


@pytest.mark.parametrize('fault', ['title','no_op_update','hidden_history','extension'])
def test_r2_same_input_whole_document_changes_are_not_replay(tmp_path, fault):
    with material_copy(tmp_path) as (wb,row,calls):
        token, proposal = preview(wb,row); packet = execute(wb,token,proposal)
        owner = wb.material_documents; did = row['document_id']
        identity = input_identity(packet['document'])
        if fault == 'no_op_update':
            command(wb,packet['document'],'material.update',{'draft':packet['document']['draft']})
        else:
            # Focused durability fault: includes hidden/unknown fields which
            # neither the input identity nor a public-response comparison covers.
            with owner._lock(did):
                document = owner._documents[did]
                if fault == 'title': document['title'] += ' changed'
                elif fault == 'hidden_history': document['_undo'].append(deepcopy(document['draft']))
                else: document['future_owner_metadata'] = {'retained':True}
                owner._persist_draft(document)
        assert input_identity(owner.read(did)) == identity
        state = file_tree(wb.root/'documents')
        with pytest.raises(ValueError, match='after the recorded'):
            execute(wb,token,proposal)
        assert file_tree(wb.root/'documents') == state and calls == []


def test_r2_lost_owner_receipt_uses_original_full_mutation_marker(tmp_path, monkeypatch):
    import caelab.material_document as material_module
    with material_copy(tmp_path) as (wb,row,calls):
        token,proposal=preview(wb,row); original=material_module.save_json
        def lose_response(path, value, *args, **kwargs):
            if Path(path).name == proposal['command_id']+'.json' and 'response' in value:
                raise OSError('C1 injected response receipt write loss after durable mutation')
            return original(path,value,*args,**kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(material_module,'save_json',lose_response)
            with pytest.raises(OSError,match='receipt write loss'):
                execute(wb,token,proposal)
        packet=execute(wb,token,proposal)
        assert packet['state']=='BUFFER_READY' and packet['raw']['cells'][0]['raw_text']=='1e'
        before=file_tree(wb.root/'documents');assert execute(wb,token,proposal)==packet
        assert file_tree(wb.root/'documents')==before and calls==[]


def test_r2_actual_comparison_retention_preserves_new_record(tmp_path):
    with material_copy(tmp_path) as (wb,row,calls):
        token,proposal=preview(wb,row);packet=execute(wb,token,proposal)
        owner=wb.material_documents;did=row['document_id']
        record={'binding':{'fixture':'C1 explicitly selected two-sample curves'},
                'comparison':{'observation':{'value':[1.,2.]},'prediction':[1.1,1.9],
                              'mask':[True,True],'residual':[.1,-.1],'count':2,'rmse':.1,
                              'unit':'MPa','method':'bounded-fixture','alignment_policy':'exact'}}
        comparison=owner.retain_comparison(did,record)  # Actual owner persistence + verified read.
        current=owner.read(did)
        assert current['input_revision']==packet['document']['input_revision']
        assert current['generation']!=packet['document']['generation']  # Do not misreport the existing owner semantics.
        before=file_tree(wb.root/'documents')
        with pytest.raises(ValueError,match='after the recorded'):
            execute(wb,token,proposal)
        assert owner.comparison(did,comparison['id'])==comparison
        assert file_tree(wb.root/'documents')==before and calls==[]


def test_r2_published_mutation_before_memory_assignment_loss(tmp_path,monkeypatch):
    with material_copy(tmp_path) as (wb,row,calls):
        token,proposal=preview(wb,row);owner=wb.material_documents;original=owner._persist_draft
        def durable_then_loss(document):
            original(document)
            raise OSError('C1 injected lost in-memory assignment after durable owner write')
        with monkeypatch.context() as patch:
            patch.setattr(owner,'_persist_draft',durable_then_loss)
            with pytest.raises(OSError,match='lost in-memory assignment'):
                execute(wb,token,proposal)
        packet=execute(wb,token,proposal)
        assert packet['state']=='BUFFER_READY'
        assert calls==[] and execute(wb,token,proposal)==packet


@pytest.mark.parametrize('fault', ['run','hidden_history'])
def test_r2_incomplete_response_receipt_cannot_absorb_later_whole_document(tmp_path,monkeypatch,fault):
    import caelab.material_document as material_module
    with material_copy(tmp_path) as (wb,row,calls):
        token,proposal=preview(wb,row);original=material_module.save_json
        def lose_response(path,value,*args,**kwargs):
            if Path(path).name==proposal['command_id']+'.json' and 'response' in value:
                raise OSError('C1 receipt response absent')
            return original(path,value,*args,**kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(material_module,'save_json',lose_response)
            with pytest.raises(OSError,match='receipt response absent'):
                execute(wb,token,proposal)
        owner=wb.material_documents;did=row['document_id']
        if fault=='run':
            def bounded(operation,arguments,**kwargs):
                return {'id':'JC1AfterLostReceipt','operation':operation,'arguments':deepcopy(arguments),
                        'created_utc':utc_now(),'state':'FAILED','result_refs':[],
                        'error':{'message':'C1 no solver dispatched'}}
            monkeypatch.setattr(owner,'submit',bounded)
            command(wb,owner.read(did),'material.evaluate')
        else:
            with owner._lock(did):
                owner._documents[did]['_undo'].append(deepcopy(owner._documents[did]['draft']))
                owner._persist_draft(owner._documents[did])
        before=file_tree(wb.root/'documents')
        with pytest.raises(ValueError,match='after the recorded'):
            execute(wb,token,proposal)
        assert file_tree(wb.root/'documents')==before and calls==[]


def test_r1_exact_saved_revision_is_not_replaced_by_an_equal_input_copy(tmp_path):
    wb,case=historical_case(tmp_path/'source')
    try:
        # Related-save saved the same M input AGAIN. That revision is not the
        # exact R2 pinned by Q; do not replace R2 just because input hashes match.
        other=case['partial_receipt']['targets'][0]['saved_reference']['saved_revision']
        assert other!=case['m2']['saved_revision']
        case['selected'][0]['saved_revision']=other
        target=tmp_path/'copy';plan=publish(wb,case,target)
        assert {other,case['m2']['saved_revision']} <= {r['saved_revision'] for r in plan['revisions']
                                                         if r['document_id']==case['m2']['id']}
        manifest=load_json(target/MANIFEST)
        actual_head=next(d['saved_revision'] for d in manifest['documents'] if d['kind']=='material')
        for row in manifest['recovery_archives']:
            _,_,draft,_=projected_buffer(target,row['archive_id'])
            assert draft['material']['saved_revision']!=actual_head
    finally:
        wb.shutdown()


def test_r2_lost_reply_cannot_grant_a_new_store_session(tmp_path):
    with material_copy(tmp_path) as (wb,row,calls):
        token,proposal=preview(wb,row);execute(wb,token,proposal)
        folder=wb.workspace
        wb.shutdown()
        reopened=open_project(folder)
        try:
            before=file_tree(reopened.root/'documents')
            with pytest.raises(ValueError,match='session changed'):
                execute(reopened,token,proposal)
            assert file_tree(reopened.root/'documents')==before and calls==[]
        finally:
            reopened.shutdown()


def test_r1_incomplete_old_map_blocks_readiness_not_original_q_read(tmp_path):
    from caelab.portable_project import verify_project
    from caelab.portable_project_io import fingerprint_file
    wb,case=historical_case(tmp_path/'source')
    try:
        target=tmp_path/'copy';publish(wb,case,target)
    finally:
        wb.shutdown()
    manifest=load_json(target/MANIFEST);row=manifest['recovery_archives'][0]
    before=read_archive(target,row['archive_id'])['capsule']
    mapping_path=target/row['hops'][-1]['file'];mapping=load_json(mapping_path)
    # Simulate the pre-C1 writer's integrity-pinned but semantically incomplete map.
    mapping['revisions']=[r for r in mapping['revisions'] if r['source_revision']!=case['m2']['saved_revision']]
    save_json(mapping_path,mapping);identity=fingerprint_file(mapping_path)
    for archive in manifest['recovery_archives']:
        archive['hops'][-1].update(identity)
    for file in manifest['files']:
        if file['path']==row['hops'][-1]['file']:file.update(identity)
    manifest['manifest_sha256']=canonical_hash({k:v for k,v in manifest.items() if k!='manifest_sha256'})
    save_json(target/MANIFEST,manifest)
    assert read_archive(target,row['archive_id'])['capsule']==before
    assert verify_project(target)['status']=='BLOCKED'
    with pytest.raises((KeyError,ValueError)):
        projected_buffer(target,row['archive_id'])
