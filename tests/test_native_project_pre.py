"""Pure saved-byte tests; these synthetic ZIPs are not native CAD acceptance."""
from copy import deepcopy
import io
import zipfile
from types import SimpleNamespace as NS

import pytest

from apps.desktop_pre import portable_project as pre
from caelab import native_cad


def native_dump(entries=None,*,stamp=(2001,1,1,0,0,0),compression=zipfile.ZIP_STORED):
    entries=entries or [('Persistence.xml',b'<Object/>'),('Shape.brp',b'geometry'),('Mesh.bin',b'mesh')]
    payload=io.BytesIO()
    with zipfile.ZipFile(payload,'w') as archive:
        for name,data in entries:
            item=zipfile.ZipInfo(name,date_time=stamp);item.compress_type=compression
            archive.writestr(item,data)
    return payload.getvalue()


def fcstd(path, links=(), marker=b'original geometry'):
    path.parent.mkdir(parents=True, exist_ok=True)
    properties = ''.join('<Property name="Link%d"><XLink file="%s" name="Part"/></Property>' % (i, value)
                         for i, value in enumerate(links))
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('Document.xml', '<Document><Objects/><Object name="Occurrence"><Properties>'
                         + properties + '</Properties></Object></Document>')
        archive.writestr('PartShape.brp', marker)
    return path


def test_native_object_fingerprint_ignores_only_zip_framing():
    a=NS(dumpContent=lambda:native_dump())
    b=NS(dumpContent=lambda:native_dump(stamp=(2026,10,18,1,2,4),compression=zipfile.ZIP_DEFLATED))
    assert a.dumpContent()!=b.dumpContent()
    assert pre._native_dump_payload_sha256(a)==pre._native_dump_payload_sha256(b)


@pytest.mark.parametrize('member',[0,1,2])
def test_native_object_payload_changes_are_not_metadata(member):
    entries=[('Persistence.xml',b'<Object/>'),('Shape.brp',b'geometry'),('Mesh.bin',b'mesh')]
    changed=deepcopy(entries);name,data=changed[member];changed[member]=(name,data+b'changed')
    assert pre._native_dump_payload_sha256(NS(dumpContent=lambda:native_dump(entries)))!=pre._native_dump_payload_sha256(
        NS(dumpContent=lambda:native_dump(changed)))


def test_native_object_missing_root_duplicate_or_malformed_dump_is_rejected():
    for raw in (b'invalid',native_dump([('Shape.brp',b'geometry')])):
        with pytest.raises((ValueError,zipfile.BadZipFile)):
            pre._native_dump_payload_sha256(NS(dumpContent=lambda:raw))
    with pytest.warns(UserWarning):raw=native_dump([('Persistence.xml',b'a'),('Persistence.xml',b'b')])
    with pytest.raises(ValueError):pre._native_dump_payload_sha256(NS(dumpContent=lambda:raw))


def test_raw_closure_repeated_occurrence_copied_bytes_and_tamper(tmp_path):
    child = fcstd(tmp_path/'source'/'part.FCStd')
    root = fcstd(tmp_path/'source'/'root.FCStd', ['part.FCStd', 'part.FCStd'])
    inspected = pre.pre_snapshot_files(root, approved_roots=[root.parent])
    snapshot = inspected['snapshot']
    assert len(snapshot['members']) == 2 and len(snapshot['edges']) == 2
    assert snapshot['edges'][0]['child_member'] == snapshot['edges'][1]['child_member']
    copies = {}
    for row in inspected['files']:
        target = tmp_path/'copied'/row['relative']; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(row['source'].read_bytes()); copies[row['member_id']] = target
    # Old paths cannot be read: only logical origins participate in resolution.
    root.unlink(); child.unlink()
    assert pre.verify_snapshot_members(snapshot, copies)['complete']
    copies['document1'].write_bytes(b'changed')
    with pytest.raises(ValueError, match='changed'):
        pre.verify_snapshot_members(snapshot, copies)


def test_managed_archive_and_embedded_members_preserved(tmp_path):
    child = fcstd(tmp_path/'part.FCStd')
    root = fcstd(tmp_path/'root.FCStd', ['part.FCStd'])
    rows = [{'file': 'documents/'+path.name, 'native_name': path.stem,
             'bytes': path.stat().st_size, 'sha256': native_cad.sha(path)} for path in (root, child)]
    manifest = {'kind': native_cad.KIND, 'schema_version': 1, 'document_id': 'PTest', 'revision': 'RTest',
                'entry': rows[0]['file'], 'metadata': {'document_id': 'PTest'}, 'documents': rows,
                'unavailable_dependencies': []}
    source = tmp_path/'design.caepre'
    native_cad.publish_project(source, manifest, {row['file']: path for row, path in zip(rows, (root, child))})
    before = source.read_bytes()
    result = pre.pre_snapshot_files(source, approved_roots=[tmp_path])
    assert source.read_bytes() == before
    assert result['snapshot']['source_document_id'] == 'PTest'
    assert result['snapshot']['saved_revision'] == 'RTest'
    assert len(result['files']) == 1 and len(result['snapshot']['members']) == 4


def test_raw_ambiguity_cycle_root_escape_and_source_target_rebind_rejected(tmp_path):
    fcstd(tmp_path/'a'/'part.FCStd'); fcstd(tmp_path/'b'/'part.FCStd')
    root = fcstd(tmp_path/'root.FCStd', ['a/part.FCStd', 'b/part.FCStd'])
    with pytest.raises(ValueError, match='이름'):
        pre.pre_snapshot_files(root, approved_roots=[tmp_path])
    fcstd(root, ['root.FCStd'])
    with pytest.raises(ValueError, match='Cyclic'):
        pre.pre_snapshot_files(root, approved_roots=[tmp_path])
    fcstd(root, ['a/part.FCStd'])
    with pytest.raises(ValueError, match='outside'):
        pre.pre_snapshot_files(root, approved_roots=[tmp_path/'a'])


def test_exact_relocation_never_changes_geometry_or_target(tmp_path):
    original = fcstd(tmp_path/'source.FCStd', ['child.FCStd'])
    relocated = tmp_path/'derived.FCStd'
    native_cad.relocate(original, relocated, lambda link: 'new-child.FCStd')
    link = native_cad.xlinks(original)[0]
    edits = [{'locator': pre._locator('document0', link), 'old_value': 'child.FCStd', 'new_value': 'new-child.FCStd'}]
    assert pre.verify_relocation(original, relocated, edits)['original_data_unchanged']
    bad = fcstd(tmp_path/'bad.FCStd', ['new-child.FCStd'], marker=b'changed geometry')
    with pytest.raises(ValueError, match='archive member'):
        pre.verify_relocation(original, bad, edits)
    with pytest.raises(ValueError, match='outside XLink'):
        pre.verify_relocation(original, relocated, [])


def test_repair_without_original_pin_is_unknown(tmp_path):
    path = fcstd(tmp_path/'part.FCStd')
    snapshot = {'snapshot_sha256': 'a'*64}
    assert pre.inspect_repair(snapshot, [{'path': path, 'expected_child': None}])['replacements'][0]['status'] == 'UNKNOWN'
    expected = {'bytes': path.stat().st_size, 'sha256': native_cad.sha(path), 'relative': 'part.FCStd'}
    assert pre.inspect_repair(snapshot, [{'path': path, 'expected_child': expected}])['applicable']
    expected['sha256'] = '0'*64
    assert not pre.inspect_repair(snapshot, [{'path': path, 'expected_child': expected}])['applicable']


def test_completed_save_same_command_reconfirms_original_bytes_without_saving_again(tmp_path, monkeypatch):
    saved = tmp_path/'retained.caepre'; saved.write_bytes(b'saved bytes')
    calls = []
    owner = NS(project=NS(save=lambda path: calls.append(path) or {
        'retained_project': str(saved), 'path': str(saved), 'revision': 'RFirst'}))
    stamp = {'document_id': 'PTest', 'kind': 'pre', 'session_id': 'STest', 'generation': 2,
             'view_generation': 1, 'saved_revision': None, 'graph_version': 'graph'}
    monkeypatch.setattr(pre, 'saved_offer', lambda unused: {'stamp': deepcopy(stamp)})
    first = pre.complete_save(owner, expected_stamp=stamp, command_id='CSave')
    # Current document may have changed; reconciliation still refers to the completed save.
    monkeypatch.setattr(pre, 'saved_offer', lambda unused: pytest.fail('Must not inspect/resave current state'))
    assert pre.complete_save(owner, expected_stamp=stamp, command_id='CSave') is first
    assert len(calls) == 1
    with pytest.raises(ValueError, match='COMMAND_CONFLICT'):
        pre.complete_save(owner, expected_stamp={**stamp, 'generation': 3}, command_id='CSave')
    saved.write_bytes(b'changed')
    with pytest.raises(ValueError, match='INPUT_CHANGED'):
        pre.complete_save(owner, expected_stamp=stamp, command_id='CSave')


def test_import_identity_is_outside_user_undo_and_preserves_engineering_objects(tmp_path, monkeypatch):
    from apps.desktop_pre import metadata
    from caelab import native_project_contract as contract
    path=tmp_path/'fresh.FCStd';path.write_bytes(b'controlled native file')
    geometry=NS(Name='Boolean',TypeId='Part::Cut',dumpContent=native_dump)
    doc=NS(FileName=str(path),UndoMode=1,UndoCount=0,RedoCount=0,Transacting=False,Partial=False,Objects=[geometry])
    value={'schema':metadata.SCHEMA,'document_id':'PSource','links':[{'job_id':'JOriginal'}]}
    before=deepcopy(value);modes=[]
    monkeypatch.setattr(metadata,'read',lambda unused:deepcopy(value))
    def write(unused,changed):
        modes.append(doc.UndoMode);value.clear();value.update(deepcopy(changed))
    monkeypatch.setattr(metadata,'write',write)
    monkeypatch.setattr(contract,'require_open_binding',lambda binding:binding)
    binding=NS(owner_id_map=[{'member_id':'document0','owner_document_id':'PLocal'}],
               member_paths={'document0':path},reference={'document_id':'PSource'},open_id='OImport')
    receipt=pre.initialize_import_identity(doc,binding,member_id='document0')
    assert modes==[0] and doc.UndoMode==1 and doc.UndoCount==0
    assert value['links']==before['links'] and receipt['geometry_check']['unchanged']
    assert receipt['changed_keys']==['document_id','portable_origin'] and receipt['adapter_recompute_calls']==0
    # Already saved local identity is verified without writing or touching Undo.
    modes.clear();pre.initialize_import_identity(doc,binding,member_id='document0');assert modes==[]
    value.clear();value.update(before);doc.UndoCount=1
    with pytest.raises(ValueError,match='IDENTITY_INIT_NOT_FRESH'):
        pre.initialize_import_identity(doc,binding,member_id='document0')
    assert value==before and doc.UndoMode==1 and modes==[]


@pytest.mark.parametrize('failure,expected_calls,expected_stage', [
    ('preflight', 0, 'before_save'), ('native', 1, 'native_save'), ('after_save', 1, None)])
def test_save_failure_stage_never_relabels_a_returned_save(tmp_path, monkeypatch, failure, expected_calls, expected_stage):
    from caelab import native_project_contract as contract, native_project_inputs as inputs
    stamp={'document_id':'PLocal','kind':'pre','session_id':'SLocal','generation':1,
           'view_generation':0,'saved_revision':None,'graph_version':'graph'}
    reservation=NS(open_id='OLocal',owner_document_id='PLocal',expected_stamp=stamp,
                   save_command_id='CActual',native_save_root=tmp_path,request_sha256='a'*64)
    calls=[];failures=[]
    def save(path):
        calls.append(path)
        if failure=='native':raise OSError('controlled native Save failure')
        return {}  # A missing returned proof is UNKNOWN, never a native failure.
    owner=NS(document_id='PLocal',portable_binding=NS(open_id='OLocal',owner_id_map=[],member_paths={}),
             project=NS(save=save,_documents=lambda:[]),native_project_context=object(),_portable_pending_save={'command_id':'CPrepare'})
    monkeypatch.setattr(contract,'require_target_save',lambda value:value)
    monkeypatch.setattr(pre,'saved_offer',lambda unused:{'stamp':{**stamp,'generation':2} if failure=='preflight' else stamp})
    monkeypatch.setattr(inputs,'_record_target_save_failure',lambda *args,**kw:failures.append(kw.get('stage','native_save')))
    with pytest.raises((ValueError,OSError,KeyError)):
        pre.complete_save(owner,expected_stamp=stamp,command_id='CActual',_target_save=reservation)
    assert len(calls)==expected_calls and failures==([] if expected_stage is None else [expected_stage])
    assert hasattr(owner,'_portable_pending_save')==(expected_stage is None)
    assert not hasattr(owner,'_native_target_save')


def test_saved_job_history_is_typed_without_inventing_job_files(tmp_path):
    from xml.sax.saxutils import quoteattr
    import json
    root=tmp_path/'root.FCStd'
    meta={'schema':'caelab-pre-project/1','document_id':'POriginal','links':[
        {'job_id':'JOriginal','operation':'simulation.run','state_when_recorded':'FAILED','origin':None},
        {'job_id':'JIncomplete'}]}
    with zipfile.ZipFile(root,'w') as archive:
        archive.writestr('Document.xml','<Document><Objects/><Object name="CAELabProject"><Properties>'
            '<Property name="Definition"><String value='+quoteattr(json.dumps(meta))+'/></Property>'
            '</Properties></Object></Document>')
        archive.writestr('PartShape.brp',b'unchanged')
    before=root.read_bytes();snapshot=pre.pre_snapshot_files(root,approved_roots=[tmp_path])['snapshot']
    assert root.read_bytes()==before and snapshot['validation']['closure']=='COMPLETE'
    link=snapshot['source_links'][0];assert link['authority']=='HISTORY_ONLY'
    assert link['target']['state_when_recorded']=='FAILED' and link['target']['records']==dict(job=None,submitted_input=None,result=None)
    assert link['target']['output_members']==[]
    assert snapshot['validation']['issues'][0]['severity']=='warning'


def test_broker_save_adapter_consumes_current_sealed_reservation_only(tmp_path, monkeypatch):
    from caelab import native_project_contract as contract, native_project_inputs as inputs
    stamp={'document_id':'PLocal','session_id':'SLocal'}
    binding=NS(open_id='OLocal')
    reservation=NS(open_id='OLocal',owner_document_id='PLocal',expected_stamp=stamp,save_command_id='CActual')
    owner=NS(document_id='PLocal',session_id='SLocal',portable_binding=binding,native_project_context=object())
    monkeypatch.setattr(contract,'require_open_binding',lambda value:value)
    monkeypatch.setattr(contract,'require_target_save',lambda value:value)
    monkeypatch.setattr(inputs,'resume_target_save',lambda ctx,cmd:reservation if cmd=='CPrepare' else pytest.fail('Wrong prepare command'))
    calls=[]
    monkeypatch.setattr(pre,'complete_save',lambda *args,**kw:calls.append(kw) or NS(source={'path':'kept.caepre'}))
    monkeypatch.setattr(inputs,'_save_witness_receipt',lambda *args,**kw:{'command_id':'CActual'})
    request={'command_id':'CActual','_target_save':{'prepare_command_id':'CPrepare','save_command_id':'CActual','open_id':'OLocal'}}
    assert pre.complete_save_command(owner,request)['native_save_receipt']=={'command_id':'CActual'}
    assert calls==[{'expected_stamp':stamp,'command_id':'CActual','_target_save':reservation}]
    with pytest.raises(ValueError):pre.complete_save_command(owner,{'command_id':'CActual'})
    with pytest.raises(ValueError):pre.complete_save_command(owner,{**request,'command_id':'COther'})
    assert len(calls)==1



def _reserved_pre_dispatch_case(tmp_path):
    """Real file-only N0 reservation; native Owner state is a controlled double."""
    import threading
    from apps.desktop_pre.bridge import Owner
    from caelab.native_project_inputs import NativeOnlyContext, register_saved, prepare_target_save
    from caelab.portable_project_native import prepare_open, verify_opened, _native_open_readback
    from caelab.storage import load_json
    source=fcstd(tmp_path/'source'/'part.FCStd')
    context=NativeOnlyContext(tmp_path/'store',approved_roots={'Public':source.parent})
    reference=register_saved(context,{'mode':'selected_file','native_kind':'pre',
        'root_id':'Public','relative':'part.FCStd'},command_id='CRegister')['reference']
    ticket=prepare_open(context,dict(reference=reference,intent='saved',target_id=None,
        expected_head=None,selection=None,allow_partial=False),command_id='COpen')
    owner=object.__new__(Owner)
    owner.document_id=ticket.binding.owner_document_id;owner.session_id='SCurrent'
    owner.thread_id=threading.get_ident();owner.generation=2;owner.view_generation=0;owner.closed=False
    owner.completed={};owner._portable_save_outcomes={};owner.portable_binding=ticket.binding
    owner.native_project_context=context;owner.refresh=lambda:None;owner._idle=lambda:None
    owner.pose_candidates=NS(busy=False);owner.fem=NS(_pending=False);owner.before_design_action=lambda unused:None
    owner.project=NS(save=lambda *args:pytest.fail('No native Save may run in a pre-dispatch refusal'))
    verify_opened(context,ticket.binding.open_id,_native_open_readback(dict(open_id=ticket.binding.open_id,
        reference=reference,target_id=None,working_document_id=owner.document_id,context_session=context.session_id,
        status='OPENED',native_owner_session=owner.session_id,native_kind='pre')))
    stamp=dict(document_id=owner.document_id,kind='pre',session_id=owner.session_id,generation=1,
        view_generation=0,saved_revision=None,graph_version='controlled-original-graph')
    reservation=prepare_target_save(context,ticket.binding.open_id,expected_stamp=stamp,expected_head=None,command_id='CPrepare')
    request=dict(command_id=reservation.save_command_id,document_id=owner.document_id,session_id=owner.session_id,
        expected_generation=2,operation='document.save',arguments={},target={},
        _target_save=dict(prepare_command_id='CPrepare',save_command_id=reservation.save_command_id,open_id=ticket.binding.open_id))
    path=context.root/'native_project'/'target_saves'/'CPrepare.json'
    return owner,context,stamp,reservation,request,path


@pytest.mark.parametrize('refusal',['stale_generation','busy','required_arguments'])
def test_reserved_save_predispatch_refusal_allows_explicit_current_retry(tmp_path, refusal):
    from caelab.native_project_inputs import prepare_target_save
    from caelab.storage import load_json
    owner,context,stamp,reservation,request,path=_reserved_pre_dispatch_case(tmp_path)
    if refusal=='stale_generation':request['expected_generation']=1
    elif refusal=='busy':owner._idle=lambda:(_ for _ in ()).throw(ValueError('BUSY_EDIT: controlled native task'))
    else:request['arguments']={'unexpected':True}
    result=owner.dispatch(request)
    assert result['status']=='FAILED'
    record=load_json(path)
    assert record['state']=='FAILED_CONFIRMED' and record['failure_stage']=='before_save'
    assert record['native_save_invoked'] is False and not (reservation.native_save_root/'design.caepre').exists()
    current={**stamp,'generation':2,'graph_version':'controlled-current-graph'}
    next_save=prepare_target_save(context,owner.portable_binding.open_id,
        expected_stamp=current,expected_head=None,command_id='CExplicitCurrentRetry')
    assert next_save.target_id==reservation.target_id and next_save.save_command_id!=reservation.save_command_id


@pytest.mark.parametrize('boundary',['wrong_session','wrong_owner','forged_wire','completed_witness'])
def test_reserved_save_unauthenticated_or_completed_evidence_is_not_failed(tmp_path,boundary):
    from caelab.storage import load_json
    from caelab.native_project_contract import _completed_save_witness
    owner,context,stamp,reservation,request,path=_reserved_pre_dispatch_case(tmp_path)
    before=path.read_bytes();request['expected_generation']=1
    if boundary=='wrong_session':request['session_id']='SOther'
    elif boundary=='wrong_owner':request['document_id']='POther'
    elif boundary=='forged_wire':request['_target_save']['save_command_id']='COther'
    else:
        saved=tmp_path/'completed.caepre';saved.write_bytes(b'controlled already completed Save')
        witness=_completed_save_witness('pre',saved,owner_stamp=stamp,command_id=reservation.save_command_id,
            publication_complete=True,source={'boundary':'controlled-completed'})
        owner._portable_save_outcomes[reservation.save_command_id]=('controlled-request-hash',witness)
    assert owner.dispatch(request)['status']=='FAILED'
    assert path.read_bytes()==before and load_json(path)['state']=='RESERVED'


def test_reserved_save_after_adapter_entry_error_stays_unconfirmed(tmp_path,monkeypatch):
    from caelab.storage import load_json
    owner,context,stamp,reservation,request,path=_reserved_pre_dispatch_case(tmp_path)
    before=path.read_bytes();entered=[]
    def after_returned_save(*args):
        entered.append(True)
        raise OSError('controlled after-Save receipt/response loss; native state UNKNOWN')
    monkeypatch.setattr(pre,'complete_save_command',after_returned_save)
    monkeypatch.setattr(pre,'_reject_unstarted_save',lambda *args:pytest.fail('After-entry errors must not be reclassified'))
    assert owner.dispatch(request)['status']=='FAILED' and entered==[True]
    assert path.read_bytes()==before and load_json(path)['state']=='RESERVED'
