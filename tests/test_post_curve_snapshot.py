"""Actual Data import/retention → native table admission receipt, no solver."""
from copy import deepcopy
import json
import time
from pathlib import Path
import pytest
from caelab.workbench import Workbench
from caelab.data_document import default_draft
from caelab.post_curves import load_curve


def imported(wb):
    source=wb.upload('load.csv',b't,F\n0,0\n1000,nan\n2000,0.004\n')
    draft=default_draft();draft['data_id']=source['id'];draft['mapping']['skip_header']=1
    spec=draft['mapping']['columns']['response']
    spec.update(unit='kN',component='x',location='load cell',measure='force',frame='global',
                row_selection={'exclude_rows':[2], 'reasons':{'2':'missing sample'}})
    spec['axis'].update(name='elapsed',unit='ms')
    doc=wb.document_open(kind='data',title='시험 하중',draft=draft)
    receipt=wb.document_command(doc['id'],'data.import',{},session_id=doc['session_id'],expected_generation=doc['generation'])
    job=receipt['job']['id']
    end=time.monotonic()+8
    while time.monotonic()<end:
        state=wb.manager.status(job)['state']
        if state in ('SUCCEEDED','FAILED'):break
        time.sleep(.005)
    assert state=='SUCCEEDED',wb.manager.status(job)
    # The existing owner collects and retains the completed import here.
    doc=wb.document_read(doc['id'])
    saved=wb.document_command(doc['id'],'document.save',{},session_id=doc['session_id'],expected_generation=doc['generation'])
    return wb.document_result_reference(doc['id'],job),draft


def test_registered_snapshot_exact_rows_no_new_job_cold_read(tmp_path):
    wb=Workbench(tmp_path)
    try:
        ref,draft=imported(wb)
        before=len(wb.manager.list())
        receipt=wb.post_curve_snapshot(ref,'response')
        native=wb.native_input(receipt['id'])
        curve,_=load_curve(native['path'],native['native_metadata'])
        assert [r['identity']['row'] for r in curve['rows']]==[1,2,3]
        assert [r['y'] for r in curve['rows']]==[0.,None,.004]
        assert not curve['rows'][1]['calculation']
        assert curve['origin']['reference']==ref
        assert curve['declaration']['observable']['selection']=='x'
        assert native['kind']=='native_curve' and len(native['source_pins'])==2
        assert len(wb.manager.list())==before
        assert wb.document_read(ref['document_id'])['draft']==draft
    finally:
        wb.shutdown()
    fresh=Workbench(tmp_path)
    try:
        native_again=fresh.native_input(receipt['id'])
        assert load_curve(native_again['path'],native_again['native_metadata'])[0]==curve
        assert len(fresh.manager.list())==before
        sidecar=Path(native_again['path']).parent/'curve.json'
        sidecar.write_text(sidecar.read_text(encoding='utf-8')+' ',encoding='utf-8')
        with pytest.raises(ValueError,match='changed'):
            fresh.native_input(receipt['id'])
    finally:
        fresh.shutdown()


def test_snapshot_stale_result_and_ordinary_upload_not_admitted(tmp_path):
    wb=Workbench(tmp_path)
    try:
        ref,_=imported(wb)
        wrong=deepcopy(ref);wrong['result_sha256']='0'*64
        with pytest.raises(ValueError,match='hash'):
            wb.post_curve_snapshot(wrong,'response')
        ordinary=wb.upload('fake.json',b'{"kind":"retained_curve"}')
        with pytest.raises(ValueError,match='registered native'):
            wb.native_input(ordinary['id'])
    finally:
        wb.shutdown()


def test_snapshot_write_failure_never_publishes_broken_input(tmp_path, monkeypatch):
    import caelab.post_curves as module
    wb = Workbench(tmp_path)
    try:
        ref, _ = imported(wb)
        before = deepcopy(wb.inputs())
        folders = set((wb.root/'inputs').iterdir())
        def interrupted(path, curve):
            # Registry readers see only complete earlier entries while writing.
            assert wb.inputs() == before
            path.write_bytes(b'partial')
            raise OSError('controlled full disk')
        monkeypatch.setattr(module, 'write_table', interrupted)
        with pytest.raises(OSError, match='controlled'):
            wb.post_curve_snapshot(ref, 'response')
        assert wb.inputs() == before
        assert set((wb.root/'inputs').iterdir()) == folders
    finally:
        wb.shutdown()
