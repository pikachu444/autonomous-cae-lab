"""Existing portable transaction with native bytes; native rendering NOT_RUN."""
from copy import deepcopy
import shutil

import pytest

from caelab.native_project_inputs import NativeOnlyContext,verify_registered
from caelab.portable_project_native import prepare_open,verify_opened,_native_open_readback
from caelab import portable_project as portable
from test_native_project_inputs import registered


def copy_native(context,reference,destination,command_id='CCopy'):
    inspection=portable.inspect_copy(context,[{'native':reference,'copy_intent':'complete','working_target':True}])
    assert inspection['status']=='READY'
    portable.create_copy(context,inspection,destination,approved=True,command_id=command_id,session_id=context.session_id)
    return destination


def test_two_copies_without_source_and_exact_current_head(tmp_path):
    context,_,reference,source=registered(tmp_path,('child.FCStd',))
    first=copy_native(context,reference,tmp_path/'first')
    shutil.rmtree(context.workspace);shutil.rmtree(source)
    assert portable.verify_project(first)['status']=='READY'
    local=portable.open_project(first)
    assert type(local) is NativeOnlyContext
    checked=portable.verify_project(first);target=checked['native_projects'][0]
    from caelab.portable_project_io import json_file
    head=json_file(first/target['head_file'])
    second=copy_native(local,head['reference'],tmp_path/'second','CSecond')
    shutil.rmtree(first)
    assert portable.verify_project(second)['status']=='READY'
    assert all(p.read_bytes()!=b'changed' for p in second.rglob('*.FCStd'))


def test_open_ticket_final_location_no_native_launch_and_stale_guard(tmp_path):
    context,_,reference,_=registered(tmp_path)
    folder=copy_native(context,reference,tmp_path/'copied')
    local=portable.open_project(folder);target=portable.verify_project(folder)['native_projects'][0]
    from caelab.portable_project_io import json_file
    head=json_file(folder/target['head_file'])
    request={'reference':head['reference'],'intent':'working','target_id':target['target_id'],
        'expected_head':{'generation':0,'reference':head['reference']},'selection':None,'allow_partial':False}
    ticket=prepare_open(local,request,command_id='COpen')
    assert ticket.binding.working_root.is_relative_to(folder)
    assert not ticket.binding.working_root.exists()  # FreeCAD owns its materialization.
    assert prepare_open(local,request,command_id='COpen') is ticket
    with pytest.raises(ValueError,match='public caller dictionary'):verify_opened(local,ticket.binding.open_id,{'status':'OPENED'})
    cold=NativeOnlyContext(folder,approved_roots={})
    with pytest.raises(ValueError,match='OPEN_UNCONFIRMED'):prepare_open(cold,request,command_id='COpen')
    changed={**request,'expected_head':{'generation':3,'reference':head['reference']}}
    with pytest.raises(ValueError,match='STALE_TARGET'):prepare_open(local,changed,command_id='CStale')


def test_private_startup_restores_only_current_owned_ticket(tmp_path):
    from caelab.portable_project_native import resume_open_ticket,claim_open_launch,open_ticket_view
    from caelab.portable_project_io import json_file
    context,_,reference,_=registered(tmp_path)
    folder=copy_native(context,reference,tmp_path/'copy')
    local=portable.open_project(folder);target=portable.verify_project(folder)['native_projects'][0]
    head=json_file(folder/target['head_file'])
    request={'reference':head['reference'],'intent':'working','target_id':target['target_id'],
        'expected_head':{'generation':0,'reference':head['reference']},'selection':None,'allow_partial':False}
    ticket=prepare_open(local,request,command_id='CStartup')
    claim_open_launch(local,ticket.binding.open_id)
    with pytest.raises(ValueError,match='OPEN_UNCONFIRMED'):claim_open_launch(local,ticket.binding.open_id)
    view=open_ticket_view(local,ticket.binding.open_id)
    assert view['status']=='LAUNCHING' and not any(view['effects'].values())
    child,restored=resume_open_ticket(ticket.derived['launch_config'])
    assert child.session_id==local.session_id and restored.binding==ticket.binding
    other=tmp_path/'not-owned.json';other.write_bytes(__import__('pathlib').Path(ticket.derived['launch_config']).read_bytes())
    with pytest.raises(ValueError,match='outside its owned'):resume_open_ticket(other)
    payload={'open_id':restored.binding.open_id,'reference':restored.binding.reference,'target_id':restored.binding.target_id,
        'working_document_id':restored.binding.working_document_id,'context_session':child.session_id,
        'status':'OPENED','native_owner_session':'SControlledOwner','native_kind':'pre'}
    # Controlled owner readback, not a real native Open.
    assert verify_opened(child,restored.binding.open_id,_native_open_readback(payload))==payload
    with pytest.raises(ValueError,match='OPEN_UNCONFIRMED'):resume_open_ticket(ticket.derived['launch_config'])


@pytest.mark.parametrize('operation',['document.save','pre.project.save'])
def test_authenticated_save_completion_only_not_public_result_or_interrupted(tmp_path,operation):
    from types import SimpleNamespace
    from caelab.native_commands import NativeCommands
    from caelab.native_project_inputs import context_from_workbench,_save_witness_receipt,resolve_completed_command
    from caelab.native_project_contract import _completed_save_witness
    from caelab.portable_project_io import json_file
    context,_,reference,_=registered(tmp_path)
    folder=copy_native(context,reference,tmp_path/'copy')
    wb=SimpleNamespace(workspace=folder,root=folder/'workbench',config={},session_id='SControlledService')
    local=context_from_workbench(wb);target=portable.verify_project(folder)['native_projects'][0]
    head=json_file(folder/target['head_file'])
    ticket=prepare_open(local,{'reference':head['reference'],'intent':'working','target_id':target['target_id'],
        'expected_head':{'generation':0,'reference':head['reference']},'selection':None,'allow_partial':False},command_id='CForSave')
    saved=ticket.binding.target_root/'controlled-save.caepre';saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(b'controlled completed file')
    stamp={'document_id':target['working_document_id'],'kind':'pre','session_id':'SNative',
        'generation':1,'view_generation':0,'saved_revision':'RControlled','graph_version':'graph'}
    witness=_completed_save_witness('pre',saved,owner_stamp=stamp,command_id='CBrokerSave',publication_complete=True,source={})
    receipt=_save_witness_receipt(witness,ticket.binding)
    broker=wb.native_commands=NativeCommands(wb.root,wb.session_id)
    document={'id':target['working_document_id'],'kind':'pre','title':'Controlled native adapter','generation':0,
        'view_generation':0,'dirty':True,'saved_revision':None,'capabilities':[operation],'state':{}}
    auth=broker.register(host_id='HControlled',session_id='SNative',application='freecad',version='controlled',
        execution_mode='headless',documents=[document],registration_nonce='n'*32)
    auth={key:auth[key] for key in ('session_id','host_token')}
    broker.submit(document['id'],operation,{},session_id='SNative',expected_generation=0,command_id='CBrokerSave')
    with pytest.raises(ValueError,match='SAVE_UNCONFIRMED'):resolve_completed_command(wb,'CBrokerSave')

    broker.next('HControlled',**auth)
    broker.event('HControlled',**auth,event='started',command_id='CBrokerSave')
    response={'status':'COMPLETED','command_id':'CBrokerSave','document_id':document['id'],'session_id':'SNative',
        'result':{'native_save_receipt':receipt}}
    broker.event('HControlled',**auth,event='finished',command_id='CBrokerSave',
        outcome={'state':'SUCCEEDED','result':response},documents=[{**document,'generation':1}])
    resolved=resolve_completed_command(wb,'CBrokerSave')
    assert resolved.pin==witness.pin and resolved.command_id=='CBrokerSave'
    wb.session_id='SAnotherService'
    with pytest.raises(ValueError,match='SAVE_UNCONFIRMED'):resolve_completed_command(wb,'CBrokerSave')


def test_os_head_publication_lock_releases_on_error_without_pointer_change(tmp_path):
    from caelab.native_project_inputs import _head_publication
    context,_,reference,_=registered(tmp_path)
    folder=copy_native(context,reference,tmp_path/'copy')
    local=portable.open_project(folder);target=portable.verify_project(folder)['native_projects'][0]
    before=(folder/target['head_file']).read_bytes()
    with pytest.raises(InterruptedError):
        with _head_publication(local,target['target_id']):
            with pytest.raises(ValueError,match='HEAD_BUSY'):
                with _head_publication(local,target['target_id']):pytest.fail('Second publisher acquired the head')
            raise InterruptedError('controlled publication interruption')
    with _head_publication(local,target['target_id']):assert (folder/target['head_file']).read_bytes()==before


def test_no_overwrite_and_registered_byte_change_blocks_creation(tmp_path):
    context,_,reference,_=registered(tmp_path)
    plan=portable.inspect_copy(context,[{'native':reference,'copy_intent':'complete','working_target':True}])
    destination=tmp_path/'exists';destination.mkdir();(destination/'keep').write_bytes(b'user')
    with pytest.raises(FileExistsError):portable.create_copy(context,plan,destination,approved=True,command_id='CNoOverwrite',session_id=context.session_id)
    assert (destination/'keep').read_bytes()==b'user'
    verify_registered(context,reference).entry_path.write_bytes(b'changed')
    with pytest.raises(ValueError):portable.create_copy(context,plan,tmp_path/'changed',approved=True,command_id='CChanged',session_id=context.session_id)
    assert not (tmp_path/'changed').exists()


def test_native_save_register_head_reconcile_and_lineage_recopy(tmp_path,monkeypatch):
    context,_,reference,_=registered(tmp_path)
    first=copy_native(context,reference,tmp_path/'first')
    local=portable.open_project(first);target=portable.verify_project(first)['native_projects'][0]
    from caelab.portable_project_io import json_file,fingerprint_file
    from caelab.native_project_contract import _completed_save_witness
    from caelab.native_cad import publish_project,KIND
    import caelab.portable_project_native as module
    head=json_file(first/target['head_file']);expected={'generation':0,'reference':head['reference']}
    native=first/'native'/target['target_id'];native.mkdir(exist_ok=True,parents=True)
    old=verify_registered(local,head['reference']).entry_path
    document_pin=fingerprint_file(old)
    row={'file':'documents/part.FCStd','native_name':'part',**document_pin}
    saved=native/'new.caepre'
    manifest={'kind':KIND,'schema_version':1,'document_id':target['working_document_id'],'revision':'RNewSave',
        'entry':row['file'],'metadata':{'document_id':target['working_document_id']},'documents':[row],'unavailable_dependencies':[]}
    publish_project(saved,manifest,{row['file']:old})
    stamp={'document_id':target['working_document_id'],'kind':'pre','session_id':'SNative',
        'generation':1,'view_generation':0,'saved_revision':'RNewSave','graph_version':'native-graph'}
    witness=_completed_save_witness('pre',saved,owner_stamp=stamp,command_id='CActualSave',publication_complete=True,source={'path':str(saved)})
    original_save=module.save_json;original_register=module.register_saved
    def interrupted(path,data):
        if data.get('state')=='PUBLISHED':raise InterruptedError('controlled response-loss after head CAS')
        original_save(path,data)
    monkeypatch.setattr(module,'save_json',interrupted)
    with pytest.raises(InterruptedError):module.publish_registered_head(local,target['target_id'],witness,expected_head=expected,command_id='CPublish')
    new_head=json_file(first/target['head_file'])
    assert new_head['head_generation']==1 and new_head['reference']['document_id']==target['working_document_id']
    monkeypatch.setattr(module,'save_json',original_save)
    monkeypatch.setattr(module,'register_saved',lambda *a,**kw: pytest.fail('Reconciliation must not Save/register again'))
    result=module.publish_registered_head(local,target['target_id'],witness,expected_head=expected,command_id='CPublish')
    assert result['head']==new_head
    second=copy_native(local,new_head['reference'],tmp_path/'second','CReCopySaved')
    shutil.rmtree(first);shutil.rmtree(context.workspace)
    check=portable.verify_project(second)
    assert check['status']=='READY' and len(check['native_inputs'])==2
    # Two raw source snapshots, exactly one current working target.
    assert len(check['native_projects'])==1
    monkeypatch.setattr(module,'register_saved',original_register)
    local2=portable.open_project(second);target2=check['native_projects'][0]
    head2=json_file(second/target2['head_file']);verified2=verify_registered(local2,head2['reference'])
    import zipfile
    member2=next(m for m in verified2.snapshot['members'] if m['role']=='pre_document')
    old2=tmp_path/'retained.FCStd'
    with zipfile.ZipFile(verified2.entry_path) as archive:old2.write_bytes(archive.read(member2['archive_member']))
    native2=second/'native'/target2['target_id'];saved2=native2/'third.caepre'
    manifest2={**manifest,'document_id':target2['working_document_id'],'revision':'RThirdSave',
        'metadata':{'document_id':target2['working_document_id']}}
    publish_project(saved2,manifest2,{row['file']:old2})
    witness2=_completed_save_witness('pre',saved2,owner_stamp={**stamp,'document_id':target2['working_document_id'],
        'saved_revision':'RThirdSave'},command_id='CThirdSave',publication_complete=True,source={})
    third_head=module.publish_registered_head(local2,target2['target_id'],witness2,
        expected_head={'generation':0,'reference':head2['reference']},command_id='CThirdHead')
    third=copy_native(local2,third_head['reference'],tmp_path/'third','CThirdCopy')
    shutil.rmtree(second)
    third_check=portable.verify_project(third)
    assert third_check['status']=='READY' and len(third_check['native_inputs'])==3
    assert reference['snapshot_sha256'] in {row['reference']['snapshot_sha256'] for row in third_check['native_inputs']}



def test_saved_import_first_save_same_live_id_reserved_once_and_recopy(tmp_path,monkeypatch):
    from caelab.native_project_inputs import prepare_target_save,publish_head,_record_target_save_failure
    from caelab.native_project_contract import _completed_save_witness
    from caelab.native_cad import publish_project,KIND
    from caelab.portable_project_io import fingerprint_file
    context,_,reference,_=registered(tmp_path)
    request={'reference':reference,'intent':'saved','target_id':None,'expected_head':None,'selection':None,'allow_partial':False}
    ticket=prepare_open(context,request,command_id='CImport')
    assert ticket.binding.owner_document_id!=reference['document_id']
    payload={'open_id':ticket.binding.open_id,'reference':reference,'target_id':None,
        'working_document_id':ticket.binding.owner_document_id,'context_session':context.session_id,
        'status':'OPENED','native_owner_session':'SActualOwner','native_kind':'pre'}
    verify_opened(context,ticket.binding.open_id,_native_open_readback(payload))
    assert not list((context.workspace/'native').glob('K*')) if (context.workspace/'native').exists() else True
    stamp={'document_id':ticket.binding.owner_document_id,'kind':'pre','session_id':'SActualOwner',
        'generation':1,'view_generation':0,'saved_revision':None,'graph_version':'graph'}
    first=prepare_target_save(context,ticket.binding.open_id,expected_stamp=stamp,expected_head=None,command_id='CFirstSave')
    assert first.creation=='NEW_TARGET' and first.owner_document_id==ticket.binding.owner_document_id
    assert prepare_target_save(context,ticket.binding.open_id,expected_stamp=stamp,expected_head=None,command_id='CFirstSave')==first
    with pytest.raises(ValueError,match='UNPUBLISHED'):
        prepare_target_save(context,ticket.binding.open_id,expected_stamp=stamp,expected_head=None,command_id='COtherSave')
    _record_target_save_failure(context,first,OSError('controlled disk full before publication'))
    stamp={**stamp,'generation':2}
    second=prepare_target_save(context,ticket.binding.open_id,expected_stamp=stamp,expected_head=None,command_id='CExplicitRetry')
    assert second.target_id==first.target_id and second.save_command_id!=first.save_command_id
    path=second.native_save_root/'design.caepre';path.parent.mkdir(parents=True)
    original=verify_registered(context,reference).entry_path
    row={'file':'documents/part.FCStd','native_name':'part',**fingerprint_file(original)}
    manifest={'kind':KIND,'schema_version':1,'document_id':second.owner_document_id,'revision':'RFirstActualSave',
        'entry':row['file'],'metadata':{'document_id':second.owner_document_id},'documents':[row],'unavailable_dependencies':[]}
    publish_project(path,manifest,{row['file']:original})
    witness=_completed_save_witness('pre',path,owner_stamp=stamp,command_id=second.save_command_id,publication_complete=True,source={})
    import caelab.portable_project_native as module
    save_json=module.save_json
    def interrupted(path,value):
        if value.get('state')=='PUBLISHED':raise InterruptedError('controlled first-head response loss')
        save_json(path,value)
    monkeypatch.setattr(module,'save_json',interrupted)
    with pytest.raises(InterruptedError):publish_head(context,second.target_id,witness,expected_head=None,command_id='CFirstHead',_target_save=second)
    monkeypatch.setattr(module,'save_json',save_json)
    monkeypatch.setattr(module,'register_saved',lambda *a,**kw:pytest.fail('First-head reconciliation must not Save/register again'))
    result=publish_head(context,second.target_id,witness,expected_head=None,command_id='CFirstHead',_target_save=second)
    assert result['head']['head_generation']==1 and result['head']['reference']['document_id']==ticket.binding.owner_document_id
    assert result['head']['parent_reference']==reference and ticket.binding.target_id is None
    assert publish_head(context,second.target_id,witness,expected_head=None,command_id='CFirstHead',_target_save=second)==result
    copy=copy_native(context,result['reference'],tmp_path/'copied-first-save','CCopyFirstSave')
    shutil.rmtree(context.workspace)
    checked=portable.verify_project(copy)
    assert checked['status']=='READY' and len(checked['native_inputs'])==2
