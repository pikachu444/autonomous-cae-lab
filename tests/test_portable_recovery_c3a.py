"""C3A exact bytes, real owner operations, no GUI/native execution claim."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import json
import shutil
import pytest

from caelab.evaluation import file_hash
from caelab.portable_project import MANIFEST, inspect_copy, create_copy, open_project, verify_project
from caelab.portable_project_io import PortableProjectError
from caelab.portable_project_recovery import catalog, read_archive, archive_row, projected_buffer
from caelab.portable_recovery_archive import inspect_capsule, owner_class
from caelab.portable_recovery_resume import buffer_token, preview_resume, resume
from caelab.related_save_recovery import RawRecoveryDrafts
from caelab.storage import load_json, save_json, canonical_hash
from examples.portable_connection_c3a_public import create_case, make_copy, owned_child, raw_for
from examples.portable_connection_public import command, save
from _portable_connection_c2_support import cold_guard


def tree(folder):
    return {p.relative_to(folder).as_posix():file_hash(p) for p in Path(folder).rglob('*')
            if p.is_file() and p.name not in {'controller.lock'}}


@pytest.fixture(scope='module')
def template(tmp_path_factory):
    folder=tmp_path_factory.mktemp('c3a-exact')
    source=folder/'original'; target=folder/'project'
    wb,case=create_case(source)
    try:
        before=tree(source); make_copy(wb,case,target)
        assert tree(source)==before
        manifest=load_json(target/MANIFEST)
        for row in manifest['recovery_archives']:
            origin=next(r for r in case['recovery_selections'] if r['document_id']==row['original_identity']['document_id'])
            q=wb._document_owner(origin['document_id'])._folder(origin['document_id'])/'raw-recovery'/(origin['capsule_id']+'.json')
            assert q.read_bytes()==(target/row['folder']/q.name).read_bytes()
        case['original_ids']=[case['documents'][k]['id'] for k in ('data','material','plan','second_plan')]
    finally:
        wb.shutdown()
    shutil.rmtree(source)  # actual fixture origin no longer exists
    return target,case


@pytest.fixture
def project(template,tmp_path):
    source,case=template; target=tmp_path/'한글 공백 사본'
    shutil.copytree(source,target)
    return target,deepcopy(case)


@contextmanager
def opened(path):
    with cold_guard() as calls:
        wb=open_project(path)
        try: yield wb,calls
        finally: wb.shutdown()


def first(path,kind='material'):
    return next(r for r in load_json(path/MANIFEST)['recovery_archives'] if r['original_identity']['kind']==kind)


def review(wb,row):
    doc=wb.document_read(row['document_id']); recovery=RawRecoveryDrafts(wb.root,wb._document_owner)
    raw={'cells':[],'editor_revision':'Ureview','local_draft':deepcopy(doc['draft'])}
    token=buffer_token(raw)
    preview=preview_resume(wb,row['archive_id'],target_identity=recovery.identity(doc),buffer=token)
    return doc,token,preview


def execute(wb,token,preview,**overrides):
    return resume(wb,preview,**{'approved':True,'overwrite_approved':True,'live_buffer':token,
                               'command_id':preview['command_id'],**overrides})


def test_ownerless_layers_four_real_owners_bytes_and_receipts(project,monkeypatch):
    path,case=project;before=tree(path); manifest=load_json(path/MANIFEST)
    def no_owner(*args,**kwargs): raise AssertionError('An archive reader constructed an owner')
    for kind in ('data','material','numerical'): monkeypatch.setattr(owner_class(kind),'__init__',no_owner)
    raws=[];receipt_hashes=set(); units=[]
    for row in manifest['recovery_archives']:
        value=read_archive(path,row['archive_id']); cap=value['capsule']; ack=cap['acknowledged']
        saved=read_archive(path,row['archive_id'],facet='saved')['document']
        assert value['resume_permission']==value['discard_permission']=='NOT_GRANTED'
        assert cap['identity']==row['original_identity']
        assert value['capsule_file_sha256']!=cap['capsule_sha256']
        assert saved['draft']!=ack['document']['draft']
        assert ack['document']['_undo'] and ack['document']['_redo']
        raws.append(cap['raw']['cells'][0]['raw_text'])
        for receipt in ack['related_save_receipts']:
            assert receipt['snapshot']==case['related_save']
            assert [r['state'] for r in receipt['snapshot']['targets']]==['SAVED','FAILED','BLOCKED']
            receipt_hashes.add(receipt['sha256'])
        if cap['identity']['kind']=='data':
            for source in ack['data_inputs']:
                if source['state']=='UNRESOLVED_UNSUBMITTED': continue
                result=read_archive(path,row['archive_id'],facet='source-preview',selection={'data_id':source['data_id']})
                assert result['source_registered'] is False
            assert 'not-collected.csv' in cap['raw']['paste']['raw_text']
            assert not any('not-collected.csv' in p for p in before)
            read_archive(path,row['archive_id'],facet='table-source')
            states=[]
            for job in ack['jobs']:
                result=read_archive(path,row['archive_id'],facet='job',selection={'job_id':job['job_id']})
                states.append(result['job']['state_at_review'])
            assert sorted(states)==['FAILED','SUCCEEDED']
    assert sorted(raws)==['','1e','1e','invalid']
    assert len(receipt_hashes)==1 and tree(path)==before


def test_no_old_permissions_or_command_markers_installed_and_no_read_mutation(project):
    path,case=project
    with opened(path) as (wb,calls):
        rows=load_json(path/MANIFEST)['recovery_archives']; before=tree(wb.root/'documents')
        for row in rows:
            doc=wb.document_read(row['document_id']);owner=wb._document_owner(doc['id'])
            assert not (owner._folder(doc['id'])/'raw-recovery').exists()
            assert not doc.get('_save_command') and not doc.get('_mutation_command')
            value=read_archive(path,row['archive_id']);old=value['capsule']['identity']
            with pytest.raises((ValueError,FileNotFoundError)):
                RawRecoveryDrafts(wb.root,wb._document_owner).recover(doc['id'],row['capsule_id'],identity=old)
            for record in value['capsule']['acknowledged']['owner_commands']:
                assert not (owner._folder(doc['id'])/'commands'/(record['command_id']+'.json')).exists()
        assert tree(wb.root/'documents')==before and calls==[] and not wb.manager.list()


@pytest.mark.parametrize('fault',['approval','overwrite','buffer','command','preview','peer','session','store'])
def test_explicit_current_buffer_cas_and_identity_boundaries(project,fault):
    path,_=project;row=first(path)
    with opened(path) as (wb,calls):
        doc,token,proposal=review(wb,row);before=tree(wb.root/'documents');changes={}
        if fault=='approval':changes['approved']=False
        if fault=='overwrite':changes['overwrite_approved']=False
        if fault=='buffer':changes['live_buffer']={**token,'raw_sha256':'0'*64}
        if fault=='command':changes['command_id']='Cdifferent'
        if fault=='preview':proposal['base_draft_sha256']='0'*64
        if fault in ('peer','session','store'):
            identity=deepcopy(proposal['target_identity'])
            identity[{'peer':'document_id','session':'session_id','store':'store_id'}[fault]]={
                'peer':first(path,'numerical')['document_id'],'session':'Sdifferent','store':'Storedifferent'}[fault]
            with pytest.raises(ValueError): preview_resume(wb,row['archive_id'],target_identity=identity,buffer=token)
        else:
            with pytest.raises(ValueError): execute(wb,token,proposal,**changes)
        assert tree(wb.root/'documents')==before and calls==[]


def test_review_is_readonly_stale_owner_refused_and_same_command_retry(project):
    path,_=project;row=first(path)
    with opened(path) as (wb,calls):
        before=tree(wb.root/'documents');doc,token,proposal=review(wb,row)
        assert tree(wb.root/'documents')==before
        draft=deepcopy(doc['draft']);draft['settings']['parameters']['E']+=5
        current=command(wb,doc,'material.update',{'draft':draft}); before=tree(wb.root/'documents')
        with pytest.raises(ValueError,match='changed after review'):execute(wb,token,proposal)
        assert tree(wb.root/'documents')==before
        _,token,proposal=review(wb,row)
        packet=execute(wb,token,proposal);state=tree(wb.root/'documents')
        replay=execute(wb,token,proposal)
        assert packet==replay and tree(wb.root/'documents')==state
        assert packet['document']['draft']['settings']['parameters']['E']!=draft['settings']['parameters']['E']
        assert packet['raw']['cells'][0]['raw_text']=='1e' and not packet['raw_applied']
        current=command(wb,packet['document'],'material.update',{'draft':draft})
        state=tree(wb.root/'documents')
        with pytest.raises(ValueError,match='after the recorded'):execute(wb,token,proposal)
        assert tree(wb.root/'documents')==state


def test_current_save_keep_reopen_and_explicit_current_edit_then_recopy(project,tmp_path):
    path,_=project; row=first(path,'data'); immutable=tree(path/'portable')
    with opened(path) as (wb,calls):
        _,token,proposal=review(wb,row); packet=execute(wb,token,proposal)
        # A user explicitly corrects a raw value through the actual existing
        # Data update. No archive resume parses or applies the string itself.
        draft=deepcopy(packet['document']['draft']);draft['mapping']['columns']['stress']['scale']=2.
        current=command(wb,packet['document'],'data.update',{'draft':draft})
        current=save(wb,current)
        raw=raw_for(current,['mapping','columns','stress','scale'],'2e',{'table':'mapping','row':1,'column':8},channel='stress')
        recovery=RawRecoveryDrafts(wb.root,wb._document_owner)
        request={'identity':recovery.identity(current),'raw':raw}; proposed=recovery.prepare([request]);kept=recovery.execute(proposed)
        assert kept['all_kept'] and recovery.close_permitted(proposed,[request])['close_permitted']
        qid=kept['targets'][0]['capsule_id']; current_id=current['id']
    with opened(path) as (wb,calls):
        recovery=RawRecoveryDrafts(wb.root,wb._document_owner);doc=wb.document_read(current_id)
        result=recovery.recover(current_id,qid,identity=recovery.identity(doc),acknowledge_session_change=True)
        assert result['state']=='RESUME_READY' and result['raw']['cells'][0]['raw_text']=='2e'
        assert doc['draft']['mapping']['columns']['stress']['scale']==2.
        rows=load_json(path/MANIFEST)['recovery_archives']
        choices=[{'archive_id':r['archive_id']} for r in rows]+[{'document_id':current_id,'capsule_id':qid}]
        plan=inspect_copy(wb,[r['document_id'] for r in load_json(path/MANIFEST)['documents']],recovery_archives=choices)
        assert plan['status']=='READY',plan
        target=tmp_path/'재복사';create_copy(wb,plan,target,approved=True,command_id='Cc3aAgain',session_id=wb.session_id)
        assert calls==[]
    assert tree(path/'portable')==immutable
    shutil.rmtree(path)
    # Current original archives and new current-Q origin are independently retained.
    rows=load_json(target/MANIFEST)['recovery_archives'];assert len(rows)==5
    texts=[read_archive(target,r['archive_id'])['capsule']['raw']['cells'][0]['raw_text'] for r in rows]
    assert '1e' in texts and '2e' in texts
    assert verify_project(target)['status']=='READY'


@pytest.mark.parametrize('part',['q','asset','map','discard_wrong_owner'])
def test_tampered_originals_rejected_without_repair_or_success(project,part):
    path,_=project;row=first(path);_,q,_=archive_row(path,row['archive_id'])
    if part=='q':q.write_bytes(q.read_bytes()+b' ')
    elif part=='asset':
        asset=next(p for p in q.with_suffix('.assets').rglob('*') if p.is_file());asset.unlink()
    elif part=='map':
        asset=path/row['hops'][0]['file'];value=load_json(asset);value['source_scope']='wrong';save_json(asset,value)
    else:
        marker={'capsule_sha256':row['capsule_sha256'],'identity':{**row['original_identity'],'document_id':'Mwrong'},'discarded_utc':'2026-10-15T00:00:00+00:00'}
        save_json(q.with_suffix('.discard.json'),marker)
    before=tree(path)
    assert verify_project(path)['status']=='BLOCKED'
    with pytest.raises((ValueError,OSError,PortableProjectError)):read_archive(path,row['archive_id'])
    assert tree(path)==before


def rehash_cap(path,cap):
    ack=cap['acknowledged']
    ack['acknowledged_sha256']=canonical_hash({k:v for k,v in ack.items() if k!='acknowledged_sha256'})
    cap['capsule_sha256']=canonical_hash({k:v for k,v in cap.items() if k!='capsule_sha256'})
    save_json(path,cap)


@pytest.mark.parametrize('fault',['path_escape','mixed_receipt','wrong_saved_owner','identity_kind'])
def test_coherently_rehashed_original_semantic_faults_are_rejected(project,fault):
    path,_=project;row=first(path);_,q,inspected=archive_row(path,row['archive_id']);cap=inspected['capsule'];ack=cap['acknowledged']
    if fault=='path_escape':ack['artifacts'][0]['path']='../outside'
    elif fault=='identity_kind':cap['identity']['kind']='numerical'
    elif fault=='wrong_saved_owner':ack['saved_sources'][0]['document_id']='Mwrong'
    else:
        receipt=ack['related_save_receipts'][0];receipt['snapshot']['targets'][1]['identity']['document_id']=cap['identity']['document_id']
        receipt['value_sha256']=canonical_hash(receipt['snapshot'])
        asset=q.with_suffix('.assets')/receipt['artifact_path'];save_json(asset,receipt['snapshot'])
        receipt['sha256']=file_hash(asset)
        artifact=next(a for a in ack['artifacts'] if a['path']==receipt['artifact_path'])
        artifact.update(sha256=receipt['sha256'],size_bytes=asset.stat().st_size)
    rehash_cap(q,cap)
    with pytest.raises((ValueError,OSError,PortableProjectError)):inspect_capsule(q)


def test_legacy_and_discard_readonly_and_exact_raw_retained(project):
    path,_=project;row=first(path);_,q,inspected=archive_row(path,row['archive_id']);cap=inspected['capsule']
    # Original ownerless read supports old incomplete Q without manufacturing a base.
    cap['acknowledged'].pop('document');rehash_cap(q,cap)
    result=inspect_capsule(q)
    assert result['verification']=='LEGACY_BASE_NOT_RETAINED' and 'document' not in result['capsule']['acknowledged']
    assert result['capsule']['raw']['cells'][0]['raw_text']=='1e'
    save_json(q.with_suffix('.discard.json'),{'capsule_sha256':cap['capsule_sha256'],
        'identity':cap['identity'],'discarded_utc':'2026-10-15T00:00:00+00:00'})
    result=inspect_capsule(q);assert result['state']=='DISCARDED' and result['resume_permission']=='NOT_GRANTED'


def test_actual_source_capsule_deletion_blocks_publish_and_keeps_completed_copy(tmp_path):
    wb,case=create_case(tmp_path/'source')
    try:
        completed=tmp_path/'completed';make_copy(wb,case,completed)
        old=tree(completed)
        plan=inspect_copy(wb,[case['documents'][k]['id'] for k in ('data','material','plan','second_plan')],
                          recovery_archives=case['recovery_selections'])
        original=case['recovery_selections'][0]
        q=wb._document_owner(original['document_id'])._folder(original['document_id'])/'raw-recovery'/(original['capsule_id']+'.json')
        asset=next(p for p in q.with_suffix('.assets').rglob('*') if p.is_file());raw=asset.read_bytes();asset.unlink()
        changed=tree(wb.workspace);target=tmp_path/'not-published'
        blocked=inspect_copy(wb,[d['document_id'] for d in plan['selections']],recovery_archives=case['recovery_selections'])
        assert blocked['status']=='BLOCKED'
        with pytest.raises(PortableProjectError):create_copy(wb,plan,target,approved=True,command_id='CmissingQ',session_id=wb.session_id)
        assert not target.exists() and tree(wb.workspace)==changed and tree(completed)==old
        asset.write_bytes(raw)
        # Identical already-published request only, never an overwrite.
        assert make_copy(wb,case,completed)['status']=='ALREADY_CREATED'
        with pytest.raises(FileExistsError):make_copy(wb,case,completed,command_id='CdifferentCopy')
    finally:wb.shutdown()


def test_discarded_and_legacy_are_portable_but_not_resumable(tmp_path):
    wb,case=create_case(tmp_path/'source')
    try:
        selection=case['recovery_selections'][1];recovery=RawRecoveryDrafts(wb.root,wb._document_owner)
        q=recovery._path(recovery._owner(selection['document_id']),selection['document_id'],selection['capsule_id'])
        cap=load_json(q)
        recovery.discard(selection['document_id'],selection['capsule_id'],identity=recovery.identity(wb.document_read(selection['document_id'])),capsule_sha256=cap['capsule_sha256'])
        # A second genuine legacy fixture retains its original acknowledged
        # summary and raw but lacks the old full document.
        other=case['recovery_selections'][2];oq=recovery._path(recovery._owner(other['document_id']),other['document_id'],other['capsule_id'])
        oldcap=load_json(oq);oldcap['acknowledged'].pop('document');rehash_cap(oq,oldcap)
        target=tmp_path/'legacy-and-discard';make_copy(wb,case,target)
    finally:wb.shutdown()
    shutil.rmtree(tmp_path/'source')
    rows=load_json(target/MANIFEST)['recovery_archives']
    for row in rows:
        result=read_archive(target,row['archive_id'])
        if result['state']=='DISCARDED' or result['verification']=='LEGACY_BASE_NOT_RETAINED':
            with pytest.raises(ValueError,match='read-only'):projected_buffer(target,row['archive_id'])
    assert verify_project(target)['status']=='READY'


def test_running_original_job_remains_as_recorded_after_source_finishes(tmp_path):
    import threading
    from caelab.workbench import Workbench
    entered=threading.Event();release=threading.Event()
    wb=Workbench(tmp_path/'original');original_execute=wb.manager._execute
    def paused_public_operation(*args,**kwargs):
        entered.set()
        if not release.wait(5):raise TimeoutError('PUBLIC pending fixture cleanup watchdog')
        raise RuntimeError('PUBLIC fixture deliberately finishes FAILED; no solver was called')
    wb.manager._execute=paused_public_operation
    try:
        doc=wb.document_open(kind='material',title='공개 미완료 실행 원문')
        receipt=wb.document_command(doc['id'],'material.evaluate',{},session_id=doc['session_id'],
                                   expected_generation=doc['generation'],command_id='CpausedPublic')
        assert entered.wait(2)
        doc=wb.document_read(doc['id']);recovery=RawRecoveryDrafts(wb.root,wb._document_owner)
        raw=raw_for(doc,['settings','parameters','E'],'1e',{'table':'재료 계수','row':0,'column':1})
        proposal=recovery.prepare([{'identity':recovery.identity(doc),'raw':raw}]);kept=recovery.execute(proposal)
        assert kept['all_kept'],kept
        q=recovery._path(recovery._owner(doc['id']),doc['id'],kept['targets'][0]['capsule_id'])
        value=inspect_capsule(q);assert value['capsule']['acknowledged']['jobs'][0]['state_at_review']=='RUNNING'
        copied=tmp_path/q.name;shutil.copyfile(q,copied);shutil.copytree(q.with_suffix('.assets'),copied.with_suffix('.assets'))
    finally:
        release.set();wb.shutdown();wb.manager._execute=original_execute
    shutil.rmtree(tmp_path/'original')
    from caelab.portable_recovery_archive import read_job
    value=inspect_capsule(copied);jid=value['capsule']['acknowledged']['jobs'][0]['job_id']
    result=read_job(copied,jid,expected_capsule_sha256=value['capsule']['capsule_sha256'])
    assert result['job']['state_at_review']=='RUNNING' and result['result'] is None
    with pytest.raises(ValueError,match='NOT_PUBLISHED'):
        read_job(copied,jid,expected_capsule_sha256=value['capsule']['capsule_sha256'],include_result=True)


@pytest.mark.parametrize('errno',['ENOSPC','EACCES'])
def test_archive_copy_write_failure_keeps_original_and_prior_copy(tmp_path,monkeypatch,errno):
    import errno as errors
    from caelab import portable_project_recovery as module
    wb,case=create_case(tmp_path/'source')
    try:
        completed=tmp_path/'completed';make_copy(wb,case,completed)
        before,old=tree(wb.workspace),tree(completed)
        def refuse(*args,**kwargs):raise OSError(getattr(errors,errno),'PUBLIC injected archive write refusal')
        monkeypatch.setattr(module,'copy_verified',refuse)
        with pytest.raises(OSError):make_copy(wb,case,tmp_path/'not-published',command_id='CrefusedArchive')
        assert not (tmp_path/'not-published').exists()
        assert tree(wb.workspace)==before and tree(completed)==old
        assert not list(tmp_path.glob('.caelab-copy-*'))
    finally:wb.shutdown()
