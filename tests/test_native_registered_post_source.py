"""Exact registered source admission; real codecs, no native process."""
from copy import deepcopy
from pathlib import Path

import pytest

from caelab.native_inputs import _register_set
from caelab.native_project_inputs import NativeOnlyContext,register_saved,verify_registered
from caelab.portable_project_io import fingerprint_file
from caelab.storage import canonical_hash,save_json
from test_native_post_dependencies import state,write


def fixture(tmp_path):
    raw=tmp_path/'raw'
    frame=write(raw/'frame.vtu',b'exact raw leaf bytes')
    entry=write(raw/'series.pvd','<VTKFile type="Collection"><Collection><DataSet timestep="1" file="frame.vtu"/></Collection></VTKFile>')
    saved=tmp_path/'saved';saved.mkdir()
    context=NativeOnlyContext(tmp_path/'store',approved_roots={'Saved':saved})
    receipt=_register_set(context.root,raw,entry,[entry,frame],None,'DSource',
        root_id='Original',relative=entry.name,limit=100000,kind='native_result',format='pvd')
    registered=context.root/receipt['file']
    pins=[{'path':str(context.root/row['file']),**{key:row[key] for key in ('bytes','sha256')}}
        for row in receipt['files']]
    record={'input_id':receipt['id'],'entry_path':str(registered),'source_pins':pins,
        'reader_name':'Result','reader_type':'PVDReader','registration_origin':receipt.get('origin')}
    record['source_revision']=canonical_hash({'format':'.pvd','files':sorted([
        {'relative':Path(pin['path']).relative_to(registered.parent).as_posix(),
         **{key:pin[key] for key in ('bytes','sha256')}} for pin in pins],key=lambda row:row['relative'])})
    workspace=state(saved/'analysis.pvsm',[('Result','PVDReader',[registered])])
    document={'kind':'external-result','document_id':'DSaved','project_root':str(saved),
        'workspace_file':workspace.name,'workspace_sha256':fingerprint_file(workspace)['sha256'],
        'sources':{'Result':record},'native_readers':[{'reader_name':'Result','reader_type':'PVDReader',
        'input_paths':[str(registered)]}],'native_reader_files':{pin['path']:pin['sha256'] for pin in pins},
        'analysis':{'version':1,'objects':{}}}
    project=saved/'project.json';save_json(project,document)
    request={'mode':'selected_file','native_kind':'post','root_id':'Saved','relative':project.name}
    return context,request,project,document


def test_first_post_save_owns_exact_registered_source_without_parent_root(tmp_path):
    context,request,project,document=fixture(tmp_path)
    before=project.read_bytes()
    result=register_saved(context,request,command_id='CRegister')
    assert project.read_bytes()==before
    verified=verify_registered(context,result['reference'],full=True)
    assert verified.full and verified.snapshot['validation']['closure']=='COMPLETE'
    assert len(verified.member_paths)==4
    # Once copied, neither the original saved project nor registered result is needed.
    project.rename(project.with_suffix('.blocked'))
    for pin in document['sources']['Result']['source_pins']:
        Path(pin['path']).rename(Path(pin['path']).with_suffix('.blocked'))
    assert verify_registered(context,result['reference'],full=True).full


@pytest.mark.parametrize('change',['missing_pin','duplicate_pin','foreign_path','input_id',
    'entry_path','revision','metadata','origin','registry_byte','rogue_reader','rogue_pvsm'])
def test_first_post_save_rejects_changed_or_unregistered_dependencies(tmp_path,change):
    context,request,project,document=fixture(tmp_path)
    row=document['sources']['Result'];pins=row['source_pins']
    if change=='missing_pin':pins.pop()
    elif change=='duplicate_pin':pins.append(deepcopy(pins[-1]))
    elif change=='foreign_path':pins[-1]['path']=str(write(tmp_path/'foreign.vtu',b'exact raw leaf bytes'))
    elif change=='input_id':row['input_id']='DAbsent'
    elif change=='entry_path':row['entry_path']=str(tmp_path/'different.pvd')
    elif change=='revision':row['source_revision']='0'*64
    elif change=='metadata':row['native_metadata']={'changed':True}
    elif change=='origin':row['registration_origin']={'job_id':'JOther'}
    elif change=='registry_byte':Path(pins[-1]['path']).write_bytes(b'changed')
    elif change=='rogue_reader':
        rogue=write(tmp_path/'rogue.vtu',b'not registered')
        document['native_reader_files'][str(rogue)]=fingerprint_file(rogue)['sha256']
    elif change=='rogue_pvsm':
        rogue=write(tmp_path/'rogue.vtu',b'not registered')
        workspace=state(project.parent/'analysis.pvsm',[('Result','PVDReader',[rogue])])
        document['workspace_sha256']=fingerprint_file(workspace)['sha256']
    save_json(project,document)
    with pytest.raises((ValueError,FileNotFoundError)):
        register_saved(context,request,command_id='CRegister')
