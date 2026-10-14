"""Runs against patched real native_inputs; no FreeCAD/process is started."""
import json
import pytest
from caelab.native_inputs import register_frozen_input,register_native_input
from caelab.adapters.shell_fem import collect
from caelab.adapters.shell_deck import validate_snapshot
from caelab.shell_inspection import load
if __package__:
    from .test_shell_support import model,snapshot,raw_sources
else:
    from test_shell_support import model,snapshot,raw_sources

def test_shell_receipt_is_separate_and_retains_native_export(tmp_path):
    source=snapshot(tmp_path/'exchange'/'Ptest'/'Ftest')
    row=register_frozen_input(tmp_path/'store',tmp_path/'exchange',source,'Dtest',root_id='test',relative='Ptest/Ftest/snapshot.json',limit=16*1024**2)
    assert row['kind']=='frozen_shell' and row['format']=='freecad-shell'
    path=tmp_path/'store'/row['file'];validate_snapshot(path)
    assert {p['relative'].rsplit('/',1)[-1] for p in row['files']}=={'snapshot.json','shell.inp','native_mesh.inp','mesh.json','editable.FCStd'}

def test_registered_surface_copies_complete_native_bundle_and_can_reopen(tmp_path):
    data=model();mesh,_,_=raw_sources(tmp_path/'job'/'solver',data)
    observed=collect(tmp_path/'job',data,mesh,execution_status='SUCCEEDED');artifact=observed['post_artifact']
    row=register_native_input(tmp_path/'store',tmp_path/'job',tmp_path/'job'/artifact['relative'],'Dresult',root_id='test',relative=artifact['relative'],limit=16*1024**2,native_metadata=artifact['native_metadata'])
    bundle=load(tmp_path/'store'/row['file'],row['native_metadata']['shell_inspection'])
    assert bundle['data']['surface']['status']=='COMPLETE'
    assert len(row['files'])>=9

def test_wrong_bundle_declaration_cannot_publish_receipt(tmp_path):
    data=model();mesh,_,_=raw_sources(tmp_path/'job'/'solver',data)
    artifact=collect(tmp_path/'job',data,mesh,execution_status='SUCCEEDED')['post_artifact']
    artifact['native_metadata']['coordinate_units']='m'
    with pytest.raises(ValueError):
        register_native_input(tmp_path/'store',tmp_path/'job',tmp_path/'job'/artifact['relative'],'Dbad',root_id='test',relative=artifact['relative'],limit=16*1024**2,native_metadata=artifact['native_metadata'])
    assert not (tmp_path/'store'/'inputs'/'Dbad'/'input.json').exists()
