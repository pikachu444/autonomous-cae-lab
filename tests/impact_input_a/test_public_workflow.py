"""Runnable-public-script checks; synthetic fields are explicitly unit evidence."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
import pytest

from caelab.execution_control import run_owned_command
from caelab.storage import canonical_hash,save_json
from caelab.workbench import Workbench
from caelab.impact_model import BACKEND
from support import install_boundary_double
from test_native import definition
from test_owner_and_results import change,wait

SCRIPT=Path(__file__).resolve().parents[2]/'examples/impact/input_a/run_public.py'
spec=importlib.util.spec_from_file_location('input_a_public_exercise',SCRIPT)
public=importlib.util.module_from_spec(spec);spec.loader.exec_module(public)


@pytest.mark.parametrize('route',['native','assembly'])
def test_real_cli_import_edit_save_and_independent_process_read(tmp_path,route):
    output=tmp_path/'command';output.mkdir();workspace=tmp_path/'saved'
    process=run_owned_command([sys.executable,str(SCRIPT),'--workspace',str(workspace),'--route',route],
                              output,'public_input',timeout=30,owned_tree=True)
    assert process.returncode==0,process.stdout
    receipt=json.loads((workspace/public.REPORT).read_text())
    assert receipt['native_execution']=='NOT_RUN' and receipt['new_jobs_requested']==0
    assert receipt['status']=='INPUT_CHECK_ONLY' and receipt['cold_reopen']=='PASS'
    cold=json.loads((workspace/public.COLD_REPORT).read_text())
    assert cold['new_jobs']==0 and cold['solver_execution']=='NOT_PERFORMED'
    assert cold['shutdown']['joined']
    child=json.loads((workspace/'input_a_cold_read.execution.json').read_text())
    assert child['pid']!=os.getpid() and child['status']=='COMPLETED'


@pytest.mark.skipif(os.name=='nt',reason='Linux NOT_RUN guard test, not Windows native evidence')
def test_explicit_native_request_on_non_windows_is_not_success(tmp_path):
    output=tmp_path/'command';output.mkdir();workspace=tmp_path/'saved'
    process=run_owned_command([sys.executable,str(SCRIPT),'--workspace',str(workspace),'--run-native'],
                              output,'public_not_run',timeout=30,owned_tree=True)
    assert process.returncode==2
    receipt=json.loads((workspace/public.REPORT).read_text())
    assert receipt['native_execution']=='NOT_RUN' and receipt['status']=='NOT_RUN'
    assert receipt['new_jobs_requested']==0 and receipt['cold_reopen']=='PASS'


def test_public_expected_quantities_and_child_reopen_of_retained_selection(tmp_path,monkeypatch):
    # The parent uses explicit synthetic TH/ANIM boundary data and real readers.
    # The child is a real new Python process with NO monkeypatch and solver0.
    install_boundary_double(monkeypatch);workspace=tmp_path/'saved'
    owner=Workbench(workspace,configuration={'workers':1})
    try:
        doc=owner.document_open(kind='simulation',draft={'backend':BACKEND,'settings':definition()})
        reply=change(owner,doc,'simulation.evaluate');doc=reply['document'];job=wait(owner,reply['job'])
        assert job['state']=='SUCCEEDED'
        result=owner.document_result(doc['id'],job['id'],selection={'responses':public.selectors(2)})
        assert public.check_expected(result,'native',2)['kinetic_energy']['status']=='PASS'
        wrong=deepcopy(result);wrong['responses']['global_6']['unit']='Mg'
        with pytest.raises(ValueError,match='unit'):public.check_expected(wrong,'native',2)
        wrong=deepcopy(result);wrong['responses']['impact.velocity.Z@2']['value'][1]=-1000.
        with pytest.raises(ValueError,match='differs'):public.check_expected(wrong,'native',2)
        doc=change(owner,doc,'document.save')['document']
        save_json(workspace/public.REPORT,{'document_id':doc['id'],'job_id':job['id'],
            'draft_sha256':canonical_hash(doc['draft']),'selection':public.selectors(2),
            'selected_sha256':canonical_hash(result),'evidence_kind':'SYNTHETIC_UNIT_OUTPUTS_NOT_NATIVE'})
    finally:assert owner.shutdown()['joined']
    output=tmp_path/'command';output.mkdir()
    process=run_owned_command([sys.executable,str(SCRIPT),'--workspace',str(workspace),'--reopen-only'],
                              output,'saved_selected_read',timeout=30,owned_tree=True)
    assert process.returncode==0,(process.stdout,(workspace/public.COLD_REPORT).read_text())
    cold=json.loads((workspace/public.COLD_REPORT).read_text())
    assert cold['selected_result']=='PASS' and cold['new_jobs']==0


def test_qt_normalized_text_selection_does_not_normalize_untouched_native_bytes():
    from caelab.impact_input_workflow import editor_buffer,apply_display_range
    from caelab.impact_input_edits import edited_files,original_files
    settings=definition();file='impact_0001.rad';buffer=editor_buffer(settings,file)
    visible=buffer['effective_text'];start=visible.index('0.001\n')
    reply=apply_display_range(settings,file=file,start=start,end=start+5,replacement='0.0012',
        reason='표시 원문의 종료 시간 선택 편집',expected_definition_sha256=buffer['definition_sha256'])
    new=reply['settings'];old=original_files(settings['source'])[file];expected=old.replace(b'0.001\r\n',b'0.0012\r\n',1)
    assert edited_files(new['source'])[file]==expected
    assert new['time']['end_s']==.0012
    # Inserting a comment line changes only the selected empty range; CRLF kept.
    buffer=editor_buffer(new,file);start=buffer['effective_text'].index('/STOP')
    again=apply_display_range(new,file=file,start=start,end=start,replacement='# explicit note\n',
        reason='설명 한 줄 추가',expected_definition_sha256=buffer['definition_sha256'])['settings']
    assert edited_files(again['source'])[file]==expected.replace(b'/STOP',b'# explicit note\r\n/STOP')
    assert original_files(again['source'])==original_files(settings['source'])
    with pytest.raises(ValueError):apply_display_range(again,file=file,start=0,end=999999,replacement='',
        reason='out of range',expected_definition_sha256=canonical_hash(again))
    with pytest.raises(ValueError):apply_display_range(again,file=file,start=0,end=0,replacement='한글',
        reason='ASCII gate',expected_definition_sha256=canonical_hash(again))
