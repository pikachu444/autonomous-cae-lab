"""File-only admission checks; synthetic ZIPs are not native CAD execution."""
from copy import deepcopy
from pathlib import Path
import zipfile

import pytest

from caelab.native_project_inputs import NativeOnlyContext,register_saved,verify_registered,read_registered
from caelab.native_project_contract import require_verified_input


def saved_source(tmp_path,links=()):
    root=tmp_path/'source';root.mkdir(exist_ok=True)
    for name,values in [('child.FCStd',()),('part.FCStd',links)]:
        properties=''.join('<Property name="Link%d"><XLink file="%s" name="Part"/></Property>'%(i,value) for i,value in enumerate(values))
        with zipfile.ZipFile(root/name,'w') as archive:
            archive.writestr('Document.xml','<Document><Objects/><Object name="Part"><Properties>'+properties+'</Properties></Object></Document>')
            archive.writestr('Shape.brp',b'public synthetic geometry')
    return root


def registered(tmp_path,links=()):
    source=saved_source(tmp_path,links)
    context=NativeOnlyContext(tmp_path/'store',approved_roots={'cad':source})
    request={'mode':'selected_file','native_kind':'pre','root_id':'cad','relative':'part.FCStd'}
    result=register_saved(context,request,command_id='CRegister')
    return context,request,result['reference'],source


def test_exact_registration_retry_full_and_metadata_distinct(tmp_path):
    context,request,reference,source=registered(tmp_path,('child.FCStd','child.FCStd'))
    assert register_saved(context,request,command_id='CRegister')['reference']==reference
    full=verify_registered(context,reference)
    assert full.full and len(full.snapshot['edges'])==2
    assert read_registered(context,reference)['verification']=='METADATA_ONLY'
    with pytest.raises(ValueError,match='Full native'):
        require_verified_input(verify_registered(context,reference,full=False))
    (source/'part.FCStd').write_bytes(b'changed source')
    with pytest.raises(ValueError,match='COMMAND_CONFLICT'):
        register_saved(context,request,command_id='CRegister')
    # Once registered, all reads remain independent of the selected source.
    assert verify_registered(context,reference).full


def test_registered_response_loss_reconfirms_without_original_file(tmp_path):
    context,request,reference,source=registered(tmp_path)
    (source/'part.FCStd').unlink()
    assert register_saved(context,request,command_id='CRegister')['reference']==reference
    assert len(list((context.root/'inputs').glob('*/input.json')))==1


def test_existing_workbench_native_sidecar_reader_and_legacy_csv_remain_independent(tmp_path):
    from caelab.workbench import Workbench
    context,_,reference,source=registered(tmp_path)
    (source/'data.csv').write_text('time,value\n0,2\n1,3\n',encoding='utf-8')
    wb=Workbench(context.workspace,configuration={'workers':1,'input_roots':{'CAD':str(source)}})
    try:
        native=wb.native_input(reference['input_id'])
        assert native['native_reference']==reference and len(native['files'])==1
        assert wb.input_path(reference['input_id'])==Path(native['path'])
        assert wb.input_preview(reference['input_id'])['full_verified'] is False
        legacy=wb.register_local_input('CAD','data.csv')
        assert wb.input_path(legacy['id']).read_text(encoding='utf-8')=='time,value\n0,2\n1,3\n'
        assert 'table_preview' in wb.input_preview(legacy['id'])
        assert not list((wb.root/'jobs').glob('*/job.json'))
        assert wb._assistance is None
    finally:wb.shutdown()


def test_current_roots_paths_and_untrusted_witness_denied(tmp_path):
    context,request,reference,_=registered(tmp_path)
    for invalid in [{**request,'relative':'../source/part.FCStd'},{**request,'root_id':'other'},
                    {'mode':'completed_native_save','command_id':'CUserDict'}]:
        with pytest.raises((ValueError,FileNotFoundError)):
            register_saved(context,invalid,command_id='CBad')
    with pytest.raises(ValueError,match='Caller dictionaries'):
        require_verified_input({'reference':reference,'full':True})
    altered={**reference,'snapshot_sha256':'a'*64}
    with pytest.raises(ValueError):verify_registered(context,altered)


def test_registered_member_tamper_and_cross_input_path_not_hidden(tmp_path):
    context,_,reference,_=registered(tmp_path)
    verified=verify_registered(context,reference)
    verified.entry_path.write_bytes(b'changed registered file')
    assert read_registered(context,reference)['full_verified'] is False
    with pytest.raises(ValueError,match='CONTENT_CHANGED'):verify_registered(context,reference)


def test_cancelled_admission_pins_same_command_before_copy(tmp_path,monkeypatch):
    source=saved_source(tmp_path)
    context=NativeOnlyContext(tmp_path/'store',approved_roots={'cad':source})
    request={'mode':'selected_file','native_kind':'pre','root_id':'cad','relative':'part.FCStd'}
    import caelab.native_project_inputs as module
    copy=module.copy_verified
    monkeypatch.setattr(module,'copy_verified',lambda *a,**kw: (_ for _ in ()).throw(InterruptedError('controlled interruption')))
    with pytest.raises(InterruptedError):register_saved(context,request,command_id='CInterrupted')
    monkeypatch.setattr(module,'copy_verified',copy)
    with zipfile.ZipFile(source/'part.FCStd','a') as archive:archive.writestr('Extra.bin',b'changed')
    with pytest.raises(ValueError,match='COMMAND_CONFLICT'):
        register_saved(context,request,command_id='CInterrupted')


def test_controlled_registered_replacement_uses_original_source_pin_and_exact_edge(tmp_path):
    """Controlled adapter boundary; not native Post/Pre repair qualification."""
    from caelab.native_inputs import _register_set
    from caelab.portable_project_io import fingerprint_file,json_file
    from caelab.storage import save_json
    from caelab.native_project_contract import finalize_snapshot,require_replacement_map
    source_root=tmp_path/'source';other_root=tmp_path/'other';source_root.mkdir();other_root.mkdir()
    child=other_root/'frame.vtu';child.write_bytes(b'controlled same original result bytes')
    original_pin={'relative':'frame.vtu',**fingerprint_file(child)}
    source=source_root/'project.json';save_json(source,{'expected':original_pin,'old_path':'Z:/unavailable/frame.vtu'})
    locator={'codec':'post_manifest_v1','field':'sources/Original/entry_path'}
    def inspect(path,*,approved_roots,limits,_replacements=None):
        assert approved_roots==[source_root]  # Other approval is not a root expansion.
        expected=json_file(path)['expected'];mapping=require_replacement_map(_replacements)
        replacement=mapping.resolve('Mparent',locator,expected_child=expected)
        members=[{'id':'Mparent','storage':'file','relative':'project.json','role':'post_manifest',**fingerprint_file(path)},
            {'id':'Mchild','storage':'file','relative':replacement['relative'],'role':'source_data',**{k:replacement[k] for k in ('bytes','sha256')}}]
        snapshot={'version':1,'native_kind':'post','input_kind':'native_post_project','format':'post-project',
            'source_document_id':'DOriginal','saved_revision':'RPending','native_revision':None,'identity_origin':'native_manifest',
            'revision_origin':'registered_snapshot','entry_member':'Mparent','source_manifest_pin':{'member_id':'Mparent',**fingerprint_file(path)},
            'members':members,'edges':[{'parent_member':'Mparent','child_member':'Mchild','locator':locator,'required':True,'original_reference':'Z:/unavailable/frame.vtu'}],
            'reader_bindings':[],'native_metadata_bindings':[],'logical_origins':[{'member_id':'Mparent','original_location':str(path)},
                {'member_id':'Mchild','original_location':'Z:/unavailable/frame.vtu'}],
            'unavailable':[],'source_links':[],'relocation_bases':[],'history_availability':[],
            'producer':{'application':'paraview','version':None,'origin':'saved_metadata'},'required_capabilities':[],
            'validation':{'closure':'COMPLETE','issues':[]},'snapshot_sha256':'0'*64}
        return {'snapshot':finalize_snapshot(snapshot),'files':[{'member_id':'Mparent','source':path,'relative':'project.json',**fingerprint_file(path)},
            {'member_id':'Mchild',**{k:replacement[k] for k in ('source','relative','bytes','sha256')}}], 'bindings':[],'issues':[]}
    def verify(snapshot,paths):
        assert json_file(paths['Mparent'])['expected']==original_pin
        for member in snapshot['members']:assert fingerprint_file(paths[member['id']])=={k:member[k] for k in ('bytes','sha256')}
        return {'complete':True}
    context=NativeOnlyContext(tmp_path/'store',approved_roots={'A':source_root,'B':other_root},adapters={'post':{'inspect':inspect,'verify':verify}})
    _register_set(context.root,other_root,child,[child],None,'DReplacement',root_id='B',relative='frame.vtu',limit=100000,kind='native_result',format='vtu')
    replacement={'parent_member':'Mparent','locator':locator,'expected_child':original_pin,'replacement_input_id':'DReplacement','replacement_member':'frame.vtu'}
    request={'mode':'selected_file','native_kind':'post','root_id':'A','relative':'project.json'}
    registered=register_saved(context,request,replacements=[replacement],command_id='CWithReplacement')
    assert verify_registered(context,registered['reference']).full
    changed={**replacement,'expected_child':{**original_pin,'relative':'third.vtu'}}
    with pytest.raises(ValueError,match='original saved source evidence'):
        register_saved(context,request,replacements=[changed],command_id='CForgedOriginalPin')
    with pytest.raises(ValueError,match='COMMAND_CONFLICT'):
        register_saved(context,request,replacements=[changed],command_id='CWithReplacement')
    with pytest.raises(ValueError,match='REPLACEMENT_UNBOUND'):
        register_saved(context,request,replacements=[{**replacement,'expected_child':None}],command_id='CNoOriginalPin')
    with pytest.raises(ValueError,match='Caller dictionaries'):
        require_replacement_map({'rows':[replacement]})


def test_private_post_save_registered_source_is_exact_same_content_not_root_permission(tmp_path):
    """Pure codec/receipt test; no live reader or native Save is simulated as actual."""
    from test_native_post_dependencies import saved_project
    from caelab.native_project_inputs import _save_registered_source_members
    from caelab.native_project_contract import OpenBinding,_SEAL
    from caelab.native_inputs import _register_set
    from caelab.portable_project_io import json_file,fingerprint_file
    from caelab.storage import canonical_hash,save_json
    source,document=saved_project(tmp_path/'original')
    old=document['sources']['A']
    old['source_revision']=canonical_hash({'format':Path(old['entry_path']).suffix.lower(),
        'files':sorted([{'relative':Path(row['path']).relative_to(Path(old['entry_path']).parent).as_posix(),
                        'bytes':row['bytes'],'sha256':row['sha256']} for row in old['source_pins']],key=lambda row:row['relative'])})
    save_json(source,document)
    context=NativeOnlyContext(tmp_path/'store',approved_roots={'A':source.parent})
    result=register_saved(context,{'mode':'selected_file','native_kind':'post','root_id':'A','relative':'project.json'},command_id='COriginalPost')
    verified=verify_registered(context,result['reference'])
    binding=OpenBinding('OControlled','0'*64,'saved',verified.reference,'DLive',[],None,None,
        tmp_path/'materialized',None,verified,verified.member_paths,{},[],context.session_id,_SEAL)
    entry=Path(old['entry_path']);paths=[Path(pin['path']) for pin in old['source_pins']]
    receipt=_register_set(context.root,entry.parent,entry,paths,None,'DRepaired',root_id='A',relative=entry.name,
        limit=100000,kind='native_result',format='pvd')
    current=deepcopy(old);current.update(input_id=receipt['id'],entry_path=str(context.root/receipt['file']),
        source_pins=[{'path':str(context.root/file['file']),**{key:file[key] for key in ('bytes','sha256')}} for file in receipt['files']])
    allowed=_save_registered_source_members(context,binding,'A',current)
    assert set(allowed)=={Path(pin['path']) for pin in current['source_pins']}
    assert all(fingerprint_file(path)=={key:member[key] for key in ('bytes','sha256')} for path,member in allowed.items())
    for changed in [{**current,'source_revision':'different'}, {**current,'reader_type':'DifferentReader'},
                    {**current,'source_pins':[{**current['source_pins'][0],'path':str(tmp_path/'third'/'series.pvd')},*current['source_pins'][1:]]}]:
        with pytest.raises(ValueError):_save_registered_source_members(context,binding,'A',changed)
    with pytest.raises(ValueError,match='saved native source'):_save_registered_source_members(context,binding,'Unselected',current)
    tampered=context.root/receipt['files'][-1]['file'];tampered.write_bytes(b'changed registered bytes')
    with pytest.raises(ValueError,match='registered source file changed'):_save_registered_source_members(context,binding,'A',current)


@pytest.mark.parametrize('missing_name',['series.pvd','frame.vtu'])
def test_initial_partial_exact_registered_repair_can_be_saved_with_typed_missing_pin(tmp_path,monkeypatch,missing_name):
    """Real file codec/receipts, no native process; candidate F4 correction only."""
    from test_native_post_dependencies import saved_project
    from caelab.native_project_inputs import _save_registered_source_members
    from caelab.native_project_contract import OpenBinding,_SEAL
    from caelab.native_inputs import _register_set
    from caelab.portable_project_io import json_file
    from caelab.storage import canonical_hash,save_json
    from dataclasses import replace
    import caelab.native_project_inputs as module
    source,document=saved_project(tmp_path/'original')
    old=document['sources']['A'];entry=Path(old['entry_path'])
    old['source_revision']=canonical_hash({'format':entry.suffix.lower(),
        'files':sorted([{'relative':Path(row['path']).relative_to(entry.parent).as_posix(),
                        'bytes':row['bytes'],'sha256':row['sha256']} for row in old['source_pins']],key=lambda row:row['relative'])})
    save_json(source,document)
    context=NativeOnlyContext(tmp_path/'store',approved_roots={'A':source.parent})
    receipt=_register_set(context.root,entry.parent,entry,[Path(pin['path']) for pin in old['source_pins']],None,
        'DPartialRepair',root_id='A',relative=entry.name,limit=100000,kind='native_result',format='pvd')
    (entry.parent/missing_name).unlink()
    result=register_saved(context,{'mode':'selected_file','native_kind':'post','root_id':'A','relative':'project.json'},command_id='CPartialOriginal')
    verified=verify_registered(context,result['reference']);raw=verified.entry_path.read_bytes()
    assert verified.snapshot['validation']['closure']=='DECLARED_PARTIAL'
    binding=OpenBinding('OInitialPartial','0'*64,'saved',verified.reference,'DLive',[],None,None,
        tmp_path/'materialized',None,verified,verified.member_paths,{},[],context.session_id,_SEAL)
    current=deepcopy(old);current.update(input_id=receipt['id'],entry_path=str(context.root/receipt['file']),
        source_pins=[{'path':str(context.root/file['file']),**{key:file[key] for key in ('bytes','sha256')}} for file in receipt['files']])
    allowed=_save_registered_source_members(context,binding,'A',current)
    assert set(allowed)=={Path(pin['path']) for pin in current['source_pins']}
    # A missing inventory entry is proof only with its exact typed edge and saved expected pin.
    original_snapshot=deepcopy(verified.snapshot)
    for mutation in ('no_pin','other_source','wrong_original_path'):
        changed=deepcopy(original_snapshot)
        # Repeated PVD occurrences can each prove the same missing frame.
        for missing_index,missing in enumerate(changed['unavailable']):
            saved=original_snapshot['unavailable'][missing_index]
            edge_index=next(i for i,edge in enumerate(original_snapshot['edges']) if edge['parent_member']==saved['parent_member'] and edge['locator']==saved['locator'])
            edge=changed['edges'][edge_index]
            if mutation=='no_pin':missing['expected_child']=None
            elif mutation=='other_source':
                missing['locator']={'codec':'post_manifest_v1','field':'sources/B/entry_path'};edge['locator']=deepcopy(missing['locator'])
            else:edge['original_reference']=str(tmp_path/'different-folder'/missing_name)
        with monkeypatch.context() as patch:
            patch.setattr(module,'verify_registered',lambda *args,**kwargs:replace(verified,snapshot=changed))
            with pytest.raises(ValueError,match='REPLACEMENT_UNBOUND'):_save_registered_source_members(context,binding,'A',current)
    assert verified.entry_path.read_bytes()==raw and verified.snapshot==original_snapshot
