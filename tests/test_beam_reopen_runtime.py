"""Actual FreeCAD test entry, opt-in; no absent runtime substitution."""
import importlib.util
import json
import os

import pytest


def test_actual_freecad_project_reopen_edit_and_current_id_export(tmp_path):
    if importlib.util.find_spec('FreeCAD') is None:
        pytest.skip('FreeCAD 1.1.4 unavailable; run VerifyBeamReopen.FCMacro on Windows')
    if os.environ.get('CAE_BEAM_NATIVE_ACCEPTANCE') != '1':
        pytest.skip('Run only in a separate native GUI process with CAE_BEAM_NATIVE_ACCEPTANCE=1')
    from examples.beam.beam_reopen_acceptance import run
    report = json.loads(run(tmp_path).read_text(encoding='utf-8'))
    assert report['status'] == 'PASS' and not report['solver_executed'], report
