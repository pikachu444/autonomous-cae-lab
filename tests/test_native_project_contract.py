"""Strict saved reference/selection and source-basis checks, no native app."""
from copy import deepcopy

import pytest

from caelab.native_project_contract import (validate_native_reference,validate_snapshot,finalize_snapshot,
    validate_native_selection,snapshot_digest,saved_revision_for,require_open_binding)
from test_native_project_inputs import registered


def test_reference_strict_keys_and_exact_versions(tmp_path):
    _,_,reference,_=registered(tmp_path)
    assert validate_native_reference(reference)==reference
    for changed in [{**reference,'path':'C:/old/file'},{**reference,'version':True},{**reference,'snapshot_sha256':'A'*64}]:
        with pytest.raises(ValueError):validate_native_reference(changed)
    with pytest.raises(ValueError,match='Caller dictionaries'):
        require_open_binding({'reference':reference})


def test_basis_has_no_local_input_identity_and_source_hash_detects_mutation(tmp_path):
    context,_,reference,_=registered(tmp_path)
    from caelab.native_project_inputs import verify_registered
    snapshot=verify_registered(context,reference).snapshot
    assert snapshot['saved_revision']==saved_revision_for(snapshot)
    changed=deepcopy(snapshot);changed['producer']['version']='other'
    assert saved_revision_for(changed)==snapshot['saved_revision']
    assert snapshot_digest(changed)!=snapshot['snapshot_sha256']
    with pytest.raises(ValueError,match='SNAPSHOT_CHANGED'):validate_snapshot(changed)
    changed=deepcopy(snapshot);changed['members'][0]['relative']='../escape.FCStd'
    with pytest.raises(ValueError):finalize_snapshot(changed)


def test_selection_is_bound_to_snapshot_without_guessing_object(tmp_path):
    context,_,reference,_=registered(tmp_path)
    from caelab.native_project_inputs import verify_registered
    snapshot=verify_registered(context,reference).snapshot
    selected={'version':1,'native_kind':'pre','snapshot_sha256':snapshot['snapshot_sha256'],
        'selection':{'document_member':'document0','occurrence_chain':[],'object_name':'Part','subelements':['Face1']}}
    assert validate_native_selection(selected,snapshot)==selected
    for invalid in [{**selected,'snapshot_sha256':'f'*64},
                    {**selected,'selection':{**selected['selection'],'document_member':'unknown'}}]:
        with pytest.raises(ValueError):validate_native_selection(invalid,snapshot)


def test_declared_history_preserves_original_failed_state_null_files_and_no_authority(tmp_path):
    from caelab.native_project_contract import metadata_declared_links,validate_declared_links
    from caelab.native_project_inputs import bind_declared_links
    context,_,reference,_=registered(tmp_path)
    original={'links':[{'job_id':'JOriginal','operation':'solver.original','state_when_recorded':'FAILED',
        'origin':{'kind':'pre','document_id':'POriginal'},'result_refs':[{'file':'C:/old/result.vtu'}]}]}
    before=deepcopy(original);links=metadata_declared_links(original,native_kind='pre')['links']
    assert original==before and links[0]['authority']=='HISTORY_ONLY'
    assert links[0]['target']['state_when_recorded']=='FAILED' and set(links[0]['target']['records'].values())=={None}
    assert links[0]['target']['output_members']==[]
    assert bind_declared_links(context,links,members=[])['availability'][0]['state']=='ORIGINAL_FILES_NOT_RETAINED'
    for invalid in [{**links[0],'authority':'EXECUTE'},{**links[0],'target':{**links[0]['target'],'path':'C:/somewhere'}}]:
        with pytest.raises(ValueError):validate_declared_links([invalid],native_kind='pre')
    native={'version':1,'relation':'native_source','source':{'kind':'project'},'authority':'HISTORY_ONLY',
        'target':{'kind':'exact','form':'native_pre','reference':reference}}
    assert bind_declared_links(context,[native],members=[])['availability'][0]['state']=='AVAILABLE'
    from caelab.native_project_inputs import verify_registered
    verify_registered(context,reference).entry_path.write_bytes(b'changed')
    assert bind_declared_links(context,[native],members=[])['availability'][0]['state']=='UNAVAILABLE'
