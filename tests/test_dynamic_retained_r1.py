"""R1 integration checks using small synthetic native files and owned-run doubles."""
from copy import deepcopy
import hashlib
import json

import pytest

from test_dynamic_support import dynamic_model
from test_dynamic_results import run_double, parsed
from caelab import dynamic_result_store as store
from caelab.dynamic_results import bundle, read_attempt
from caelab.dynamic_execution import read_terminal


def fingerprints(folder):
    return {p.relative_to(folder).as_posix():hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
            for p in folder.rglob('*') if p.is_file()}


def test_v2_preserves_v1_native_values_missing_boundaries_and_energy(monkeypatch,tmp_path):
    model=dynamic_model(mixed=True)
    _,output=run_double(monkeypatch,tmp_path,model)
    actual=read_attempt(output)
    reference_folder=tmp_path/'reference';reference_folder.mkdir()
    frames=parsed(model,reference_folder)
    reference=bundle(model,frames,reference_folder/'contact.dat',execution_status='SUCCEEDED',
                     source_pins=actual['source_pins'],snapshot_id=actual['snapshot_id'])
    # Only JSON key normalization; no floating tolerance, downsampling or missing-value substitution.
    reference=json.loads(json.dumps(reference))
    assert deepcopy(actual)['frames']==reference['frames']
    assert actual['meanings']==reference['meanings']
    assert actual['stages']==reference['stages']


def test_metadata_and_one_selected_frame_use_the_existing_lazy_reader(monkeypatch,tmp_path):
    _,output=run_double(monkeypatch,tmp_path,dynamic_model())
    original=store._json;reads=[]
    def tracked(root,pin,limit=store.MAX_BYTES):
        reads.append(pin['relative']);return original(root,pin,limit)
    monkeypatch.setattr(store,'_json',tracked)
    metadata=store.load_result(output/'dynamic_result.json',metadata_only=True)
    assert reads==[] and len(store.frame_metadata(metadata))==3
    data=store.load_result(output/'dynamic_result.json')
    assert reads==['dynamic-frames/topology.json']
    assert data['frames'][1]['location']['physical_time_s']==.5
    assert reads==['dynamic-frames/topology.json','dynamic-frames/frame0002.json']
    with (output/'dynamic-frames/frame0002.json').open('ab') as stream:stream.write(b' ')
    with pytest.raises(ValueError,match='changed'):data['frames'][1]


def test_native_terminal_and_restart_bytes_survive_readback_failure(monkeypatch,tmp_path):
    from caelab.adapters import dynamic_fem
    def reject(*args,**kwargs):raise OSError('EXPLICIT_TEST_POSTPROCESSING_WRITE_FAILURE')
    monkeypatch.setattr(dynamic_fem,'write_result',reject)
    result,output=run_double(monkeypatch,tmp_path,dynamic_model(),rout=True)
    assert result['execution_status']=='FAILED' and not result.get('dynamic_result')
    assert result['postprocessing']['result']=='FAILED'
    terminal=read_terminal(output)
    assert terminal['status']=='COMPLETED' and terminal['execution_status']=='FAILED'
    assert terminal['solver_execution']=='NOT_PERFORMED'
    assert 'solver/contact.rout' in terminal['source_pins']
    assert (output/'solver/contact.rout').is_file()


def test_explicit_failed_output_reprocess_keeps_parent_and_does_not_solve(monkeypatch,tmp_path):
    from caelab.adapters import contact_fem
    from caelab.dynamic_recovery import reprocess
    _,output=run_double(monkeypatch,tmp_path,dynamic_model(),failed=True,rout=True)
    before=fingerprints(output)
    monkeypatch.setattr(contact_fem,'run_owned_command',lambda *a,**k:pytest.fail('Readback launched a solver'))
    receipt=reprocess(output,tmp_path/'new-readback')
    assert receipt['readback_status']=='SUCCEEDED',receipt
    assert receipt['execution_status']=='FAILED' and receipt['responses']=={}
    assert receipt['solver_execution']=='NOT_PERFORMED'
    assert receipt['derivation']['original_execution_status']=='FAILED'
    assert read_attempt(tmp_path/'new-readback')['execution_status']=='FAILED'
    assert fingerprints(output)==before
