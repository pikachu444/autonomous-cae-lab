"""Actual existing owners/reader/JobManager; tiny public arithmetic fixtures only."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from caelab.storage import canonical_hash, load_json, save_json
from caelab.evaluation import file_hash, read_result
from caelab.related_save_recovery import RawRecoveryDrafts
from caelab.data_recovery_inputs import (inspect_capsule, resolve_source,
    preview_source, read_table_source, declared_uses)
from caelab.data_material_service import DataMaterialService
from .support import Workbench, basic, import_data, build_history, keep, raw_for, command, plain


@pytest.fixture
def w(tmp_path):
    instance=Workbench(tmp_path/'live 원작업',configuration={'workers':1,'cpu_budget':1})
    yield instance
    assert instance.shutdown()['joined']


def request(w,d):
    r=RawRecoveryDrafts(w.root,w._document_owner)
    req={'identity':r.identity(d),'raw':raw_for(d)}
    return r,req


def test_unsaved_no_import_preserves_actual_source_and_receipt_bytes(w):
    d,source,certificate=basic(w)
    # input.json must be copied verbatim, not reconstructed using save_json.
    p=w.root/'inputs'/source['id']/'input.json'
    p.write_text(json.dumps(load_json(p),ensure_ascii=False,separators=(',', ':'))+'\n\n',encoding='utf-8')
    original=p.read_bytes();before=deepcopy(w.data_documents.acknowledged_state(d['id'])['document'])
    r,pv,target,path=keep(w,d)
    cap=inspect_capsule(path)['capsule'];records=cap['acknowledged']['data_inputs']
    assert len(records)==2 and all(s['state']=='RETAINED' for s in records)
    row=next(s for s in records if s['data_id']==source['id'])
    assert (path.with_suffix('.assets')/row['metadata_file']).read_bytes()==original
    assert resolve_source(path,source['id'])[1]==source
    assert w.data_documents.acknowledged_state(d['id'])['document']==before
    assert not list(w.root.glob('documents/*/revisions/*')) and not w.manager.list()
    assert not list(w.root.glob('documents/*/document.json'))
    assert DataMaterialService(w).dispatch('recovery.source_preview',{
        'document_id':d['id'],'capsule_id':target['capsule_id'],'data_id':certificate['id']})['receipt']==certificate


def test_exact_current_undo_redo_run_acquisition_closure_and_unapplied_separation(w):
    h=build_history(w);d=h['data'];before=deepcopy(w.data_documents._documents[d['id']]);jobs=deepcopy(w.manager.list())
    r,pv,target,path=keep(w,d,h['raw']);value=inspect_capsule(path);ack=value['capsule']['acknowledged']
    assert d['saved_revision'] is None and not list(w.root.glob('documents/*/revisions/*'))
    assert ack['document']==before and w.data_documents._documents[d['id']]==before
    assert w.manager.list()==jobs  # Keep did not submit or alter even a reader job
    assert {s['data_id'] for s in ack['data_inputs']}=={s['id'] for s in h['registrations']}
    assert {u['path'][0] for s in ack['data_inputs'] for u in s['uses']}=={'draft','_undo','_redo','runs'}
    assert any('acquisition' in u['path'] for s in ack['data_inputs'] for u in s['uses'])
    assert h['unacknowledged']['id'] not in {s['data_id'] for s in ack['data_inputs']}
    assert h['unrelated']['id'] not in {s['data_id'] for s in ack['data_inputs']}
    assert ack['document']['draft']['data_id']!=value['capsule']['raw']['local_draft']['data_id']
    assert len([a for a in ack['artifacts'] if a['path'].startswith('inputs/')])==24
    assert h['plan_args']['experiments'][0]['observations']['source_rows']==[1,2,3,4]
    assert h['plan_args']['experiments'][0]['observations']['value']==[0.,1.,2.,3.]
    assert len(w.manager.list())==1 and w.manager.list()[0]['operation']=='import_table'


def test_capsule_only_portable_cold_source_processing_material_plan_provenance(w,tmp_path):
    h=build_history(w);d=h['data'];r,pv,target,path=keep(w,d,h['raw'])
    original=inspect_capsule(path)['capsule'];payload=r.portable_payload(d['id'],target['capsule_id'])
    expected={
        'capsule_sha256':original['capsule_sha256'], 'identity':original['identity'],
        'base_sha256':original['acknowledged']['document_sha256'],
        'source_sha256':{s['id']:s['sha256'] for s in h['registrations']},
        'receipt_sha256':{s['id']:canonical_hash(s) for s in h['registrations']},
        'imported_responses_sha256':canonical_hash(plain(h['imported']['responses'])),
        'processed_response_sha256':canonical_hash(h['processed']['responses']['P11']),
        'plan_observation_values':h['plan_args']['experiments'][0]['observations']['value'],
        'plan_observation_rows':h['plan_args']['experiments'][0]['observations']['source_rows'],
        'plot_axis':h['plot_axis'],'kinematics':h['kinematics'],
        'processing_id':h['processing_id'], 'job_id':h['job_id']}
    # Replace then delete live inputs/results, BEFORE moving the capsule. It is
    # the copied assets, not an accidentally reachable original, that must work.
    for source in h['registrations']:
        w.input_path(source['id']).write_bytes(b'replaced live bytes\n')
    (w.root/'results'/h['job_id']/'result.json').write_text('{}',encoding='utf-8')
    shutil.rmtree(w.root/'inputs');shutil.rmtree(w.root/'results')
    assert r.inspect(d['id'],target['capsule_id'])['source_retention']=='COMPLETE'
    moved=tmp_path/'이동 자료 공백';moved.mkdir()
    dest=moved/path.name;shutil.copy2(path,dest);shutil.copytree(path.with_suffix('.assets'),dest.with_suffix('.assets'))
    assert w.shutdown()['joined'];shutil.rmtree(w.workspace)
    assert not w.root.exists()
    expect=tmp_path/'expected.json';save_json(expect,expected)
    before={p.relative_to(moved).as_posix():file_hash(p) for p in moved.rglob('*') if p.is_file()}
    child=subprocess.run([sys.executable,'-B','-m','tests.data_material_c3.cold_reader',str(dest),str(expect)],
        cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True,encoding='utf-8',timeout=30,
        env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    assert child.returncode==0,child.stdout+'\n'+child.stderr
    evidence=json.loads(child.stdout)
    assert evidence['inputs_verified']==12 and evidence['owner_constructions']==0 and evidence['jobs_submitted']==0
    assert evidence['source_rows']==[1,2,3,4] and evidence['nominal_stress_MPa']==[0.,1.,2.,3.]
    assert evidence['verification']=='COMPLETE' and evidence['solver_execution']=='NOT_PERFORMED'
    after={p.relative_to(moved).as_posix():file_hash(p) for p in moved.rglob('*') if p.is_file()}
    assert after==before
    output=os.environ.get('CAE_C3_EVIDENCE')
    if output:
        out=Path(output);out.mkdir(parents=True,exist_ok=True)
        shutil.copytree(moved,out/'portable capsule',dirs_exist_ok=True)
        save_json(out/'expected.json',expected);save_json(out/'cold-reader-result.json',evidence)
        save_json(out/'portable-payload.json',payload)
        save_json(out/'data-plan-source-contract.json',plain(h['plan_args']))


@pytest.mark.parametrize('where',['data','calibration'])
@pytest.mark.parametrize('fault',['bytes','missing_source','missing_receipt','receipt_id','receipt_fields','coherent_replace'])
def test_used_source_changes_or_missing_fail_without_closing(w,where,fault):
    d,source,cert=basic(w);d,jid=import_data(w,d);r,req=request(w,d)
    selected=source if where=='data' else cert
    path=w.input_path(selected['id']);meta=path.parent/'input.json'
    if fault=='bytes':path.write_bytes(b'changed')
    elif fault=='missing_source':path.unlink()
    elif fault=='missing_receipt':meta.unlink()
    elif fault=='receipt_id':
        value=load_json(meta);value['id']='Dwrong';save_json(meta,value)
    elif fault=='receipt_fields':
        value=load_json(meta);value['name']='renamed receipt.csv';save_json(meta,value)
    else:
        path.write_bytes(b'coherently replaced source\n');value=load_json(meta)
        value.update(sha256=file_hash(path),bytes=path.stat().st_size);save_json(meta,value)
    before=w.data_documents._documents[d['id']]
    pv=r.prepare([req]);assert pv['targets'][0]['problems']
    result=r.execute(pv)
    assert not result['close_permitted'] and result['live_buffers_must_be_preserved']==[d['id']]
    assert not r.read(d['id'])['capsules'] and req['raw']['cells'][0]['raw_text']=='1e'
    assert w.data_documents._documents[d['id']]==before


@pytest.mark.parametrize('fault',['source','receipt','calibration'])
def test_prepare_execute_evidence_cannot_refresh_to_changed_registered_bytes(w,fault):
    d,src,cert=basic(w);r,req=request(w,d);pv=r.prepare([req]);assert not pv['targets'][0]['problems']
    chosen=cert if fault=='calibration' else src
    meta=w.root/'inputs'/chosen['id']/'input.json'
    value=load_json(meta)
    if fault=='receipt': value['name']='peer changed label.csv'
    else:
        p=w.root/value['file'];p.write_bytes(b'new registered bytes\n')
        value.update(sha256=file_hash(p),bytes=p.stat().st_size)
    save_json(meta,value)
    result=r.execute(pv);assert not result['close_permitted'] and not r.read(d['id'])['capsules']


def test_saved_revision_fallback_same_receipt_missing_live_inputs(w,tmp_path):
    d,src,cert=basic(w);d,jid=import_data(w,d)
    d=command(w.data_documents,d,'document.save')['document']
    revision=d['saved_revision'];saved=w.data_documents._verify_revision(d['id'],revision)
    shutil.rmtree(w.root/'inputs')
    # Existing owner resolves a *new import* from the same saved source. C3 then
    # preserves both the old registered-reference job and this retained-ref job.
    d,jid2=import_data(w,d)
    assert w.manager.status(jid2)['arguments']['source_ref']['kind']=='retained_data_input'
    r,pv,target,path=keep(w,d)
    cap=inspect_capsule(path)['capsule']
    assert all(s['resolution']=='retained_data_input' for s in cap['acknowledged']['data_inputs'])
    assert resolve_source(path,src['id'])[1]==src and resolve_source(path,cert['id'])[1]==cert
    shutil.rmtree(w.data_documents._folder(d['id'])/'revisions')
    assert inspect_capsule(path)['source_retention']=='COMPLETE'
    assert read_table_source(path)['table']['responses']['force']['value'].tolist()==[0.,20.,40.,60.]


def test_corrupt_saved_fallback_never_uses_good_live_replacement(w):
    d,src,cert=basic(w);d=command(w.data_documents,d,'document.save')['document']
    retained=w.data_documents._documents[d['id']]['retained_inputs'][src['id']]
    p=w.data_documents._folder(d['id'])/'revisions'/retained['revision']/retained['file']
    p.write_bytes(b'corrupt saved original')
    assert w.input_path(src['id']).exists()
    r,req=request(w,d);pv=r.prepare([req]);result=r.execute(pv)
    assert not result['close_permitted']


@pytest.mark.parametrize('fault',['copy','partial','readback'])
def test_partial_input_asset_failure_keeps_live_raw_and_other_owner_success(w,monkeypatch,fault):
    import caelab.related_save_recovery_assets as assets
    d,src,cert=basic(w);m=w.document_open(kind='material')
    r,req=request(w,d)
    mr={'identity':r.identity(m),'raw':{'editor_revision':'material-editor','cells':[]}}
    pv=r.prepare([mr,req]);assert not any(t['problems'] for t in pv['targets'])
    previous=w.data_documents.acknowledged_state(d['id'])['document'];made=[]
    if fault=='readback':
        original=assets.verify_assets
        def fail(folder,ack):
            if ack['document']['kind']=='data':raise OSError('injected source readback failure')
            return original(folder,ack)
        monkeypatch.setattr(assets,'verify_assets',fail)
    else:
        original=assets.shutil.copyfileobj
        def fail(incoming,outgoing):
            made.append(str(incoming.name))
            if len(made)==2:
                if fault=='partial':outgoing.write(b'half input bytes')
                raise PermissionError('injected partial Data source write denied')
            return original(incoming,outgoing)
        monkeypatch.setattr(assets.shutil,'copyfileobj',fail)
    result=r.execute(pv)
    assert [t['close_permitted'] for t in result['targets']]==[True,False]
    assert result['targets'][1]['state']=='FAILED' and result['live_buffers_must_be_preserved']==[d['id']]
    assert req['raw']['cells'][0]['raw_text']=='1e'
    assert w.data_documents.acknowledged_state(d['id'])['document']==previous
    assert not list(w.root.glob('documents/*/revisions/*'))


@pytest.mark.parametrize('fault',['source','receipt','closure','claim','path','missing_asset'])
def test_capsule_tamper_is_checked_and_close_gate_fails(w,fault):
    d,src,cert=basic(w);d,jid=import_data(w,d);r,pv,target,path=keep(w,d)
    cap=load_json(path);ack=cap['acknowledged'];row=next(s for s in ack['data_inputs'] if s['data_id']==src['id'])
    if fault=='source':(path.with_suffix('.assets')/row['source_file']).write_bytes(b'bad')
    elif fault=='receipt':
        p=path.with_suffix('.assets')/row['metadata_file'];value=load_json(p);value['name']='bad.csv';save_json(p,value)
    elif fault=='missing_asset':(path.with_suffix('.assets')/row['metadata_file']).unlink()
    else:
        if fault=='closure':ack['data_inputs'].remove(row)
        elif fault=='claim':row['uses'][0]['data_id']='Ddifferent'
        else:row['source_file']='../outside.csv'
        # Resealing is not enough to bypass semantic dependency verification.
        ack['acknowledged_sha256']=canonical_hash({k:v for k,v in ack.items() if k!='acknowledged_sha256'})
        cap['capsule_sha256']=canonical_hash({k:v for k,v in cap.items() if k!='capsule_sha256'})
        save_json(path,cap)
    with pytest.raises((ValueError,OSError)):inspect_capsule(path)
    assert not r.close_permitted(pv,[{'identity':r.identity(d),'raw':raw_for(d)}])['close_permitted']


def test_incomplete_acknowledged_identity_is_not_invented_or_used_source_success(w):
    d=w.document_open(kind='data');r,pv,target,path=keep(w,d)
    value=inspect_capsule(path)
    assert value['source_retention']=='INCOMPLETE_UNSUBMITTED_DECLARATIONS'
    assert value['capsule']['acknowledged']['data_inputs'][0]['state']=='UNDECLARED'
    changed=deepcopy(d['draft']);changed['data_id']='Dnot_registered'
    d=command(w.data_documents,d,'data.update',{'draft':changed})['document']
    r,req=request(w,d);review=r.prepare([req]);result=r.execute(review)
    assert not result['close_permitted'] and 'DECLARED_DATA_SOURCE_BYTES_UNAVAILABLE' in result['targets'][0]['close_reasons']
    assert r.inspect(d['id'],result['targets'][0]['capsule_id'])['acknowledged']['document']['draft']['data_id']=='Dnot_registered'


def test_sources_disappearing_from_undo_redo_or_run_cannot_close(w):
    h=build_history(w);d=h['data'];r,req=request(w,d)
    # B exists only in Undo. Delete its whole registration, not merely one file.
    src=h['registrations'][3];shutil.rmtree(w.root/'inputs'/src['id'])
    pv=r.prepare([req]);result=r.execute(pv)
    assert not result['close_permitted']
    # D's known calibration exists only in Redo: absence is a required hash loss.
    cert=h['registrations'][10];shutil.rmtree(w.root/'inputs'/cert['id'])
    pv=r.prepare([req]);assert pv['targets'][0]['problems']
    # Run-only coverage is a pure dependency check even if a future history
    # pruning operation removes Undo; no synthetic owner publication is made.
    doc=deepcopy(w.data_documents._documents[d['id']]);doc['_undo']=[];doc['_redo']=[]
    assert any(u['data_id']==h['registrations'][0]['id'] and u['required'] for u in declared_uses(doc))


def test_legacy_c2_base_remains_readable_without_claiming_original_inputs(w):
    d,src,cert=basic(w);r,pv,target,path=keep(w,d)
    cap=load_json(path);ack=cap['acknowledged'];ack.pop('data_inputs')
    ack['artifacts']=[a for a in ack['artifacts'] if not a['path'].startswith('inputs/')]
    ack['acknowledged_sha256']=canonical_hash({k:v for k,v in ack.items() if k!='acknowledged_sha256'})
    cap['capsule_sha256']=canonical_hash({k:v for k,v in cap.items() if k!='capsule_sha256'})
    save_json(path,cap)
    assert r.inspect(d['id'],target['capsule_id'])['source_retention']=='LEGACY_INPUT_CLOSURE_NOT_RETAINED'
    with pytest.raises(ValueError):resolve_source(path,src['id'])
    assert not r.close_permitted(pv,[{'identity':r.identity(d),'raw':raw_for(d)}])['close_permitted']


def test_pending_owner_change_and_foreign_store_never_grant_resume_or_discard(w,tmp_path):
    from caelab.data_document import DataDocuments
    d,src,cert=basic(w);r,pv,target,path=keep(w,d)
    previous=deepcopy(inspect_capsule(path))
    draft=deepcopy(d['draft']);draft['test_metadata']={'specimen':'peer edited specimen'}
    peer=command(w.data_documents,d,'data.update',{'draft':draft})['document']
    assert r.recover(d['id'],target['capsule_id'],identity=r.identity(peer))['state']=='BLOCKED'
    assert inspect_capsule(path)==previous
    root=tmp_path/'another store';target_path=root/'documents'/d['id']/'raw-recovery'/path.name
    target_path.parent.mkdir(parents=True);shutil.copy2(path,target_path)
    shutil.copytree(path.with_suffix('.assets'),target_path.with_suffix('.assets'))
    other=DataDocuments(root,'Sforeign',lambda *a,**k:pytest.fail('must not submit'),w.manager,
        resolve_input=lambda key:pytest.fail('must not resolve another store input'))
    foreign=RawRecoveryDrafts(root,lambda key:other)
    assert not foreign.inspect(d['id'],target['capsule_id'])['same_store']
    with pytest.raises((ValueError,FileNotFoundError)):
        foreign.recover(d['id'],target['capsule_id'],identity=r.identity(peer),acknowledge_session_change=True)
    with pytest.raises((ValueError,FileNotFoundError)):
        foreign.discard(d['id'],target['capsule_id'],identity=r.identity(peer),capsule_sha256=previous['capsule']['capsule_sha256'])
    assert not list(root.glob('documents/*/working.json'))


def test_valid_saved_fallback_never_adopts_changed_live_same_id(w):
    d,src,cert=basic(w);d,jid=import_data(w,d)
    d=command(w.data_documents,d,'document.save')['document']
    original=w.input_path(src['id']).read_bytes();meta=w.root/'inputs'/src['id']/'input.json'
    live=w.input_path(src['id']);live.write_bytes(b'wrong new version in live registry\n')
    replacement=load_json(meta);replacement.update(sha256=file_hash(live),bytes=live.stat().st_size);save_json(meta,replacement)
    r,pv,target,path=keep(w,d)
    preserved,receipt=resolve_source(path,src['id'])
    assert preserved.read_bytes()==original and receipt==src and receipt!=replacement
    assert w.data_documents._documents[d['id']]['retained_inputs'][src['id']]['sha256']==src['sha256']


def test_raw_missing_identity_stays_incomplete_not_complete_bytes(w):
    d=w.document_open(kind='data',draft={})
    raw={'editor_revision':'blank-data','cells':[]}
    r,pv,target,path=keep(w,d,raw)
    value=inspect_capsule(path)
    assert value['source_retention']=='INCOMPLETE_UNSUBMITTED_DECLARATIONS'
    assert value['capsule']['acknowledged']['document']['draft']=={}
    assert value['capsule']['acknowledged']['data_inputs'][0]['state']=='UNDECLARED'


def test_binary_calibration_original_is_retained_without_decoding_or_registering(w):
    d,src,cert=basic(w)
    binary=w.upload('교정 원본.pdf',b'%PDF-1.4\n%\xff\x80\x00fixture-only-not-a-rendered-document\n')
    draft=deepcopy(d['draft'])
    draft['mapping']['columns']['force']['calibration']['source']={
        'data_id':binary['id'],'sha256':binary['sha256'],'name':binary['name']}
    d=command(w.data_documents,d,'data.update',{'draft':draft})['document']
    r,pv,target,path=keep(w,d)
    preview=preview_source(path,binary['id'])
    assert 'Binary' in preview['preview'] and preview['source_registered'] is False
    assert resolve_source(path,binary['id'])[0].read_bytes()==w.input_path(binary['id']).read_bytes()
    assert len(w.inputs())==3  # source + original undo certificate + binary certificate


def test_source_path_alias_and_cross_owner_receipt_are_not_followed(w,monkeypatch):
    d,src,cert=basic(w);other=w.upload('다른 입력.csv',b'other\n1\n')
    resolver=w.data_documents.resolve_input
    def wrong(key):
        if key==src['id']:
            source,receipt=resolver(other['id']);receipt=deepcopy(receipt);receipt['id']=src['id']
            return source,receipt
        return resolver(key)
    monkeypatch.setattr(w.data_documents,'resolve_input',wrong)
    r,req=request(w,d);pv=r.prepare([req]);result=r.execute(pv)
    assert pv['targets'][0]['problems'] and not result['close_permitted']
