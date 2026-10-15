"""Optional Qt contract checks. Offscreen is NOT Windows live-window acceptance."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6',reason='NOT_RUN: installed PySide6 required; no installation attempted')
from copy import deepcopy
import json
from pathlib import Path
from PySide6.QtWidgets import QApplication
from apps.research.finite_measure_dialog import FiniteColumnsDialog,FiniteAuditDialog,FinitePredictionDialog
from apps.research.material_test_dialog import ExperimentDialog
from caelab.finite_measure_input import mapping,recipe
from caelab.adapters.file_table import read_table
from caelab.data_processing import preview_recipe
from caelab.storage import canonical_hash

@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])


def test_cancel_raw_number_and_numeric_table(app):
    c=json.loads((Path(__file__).resolve().parents[2]/'examples/finite-measure/train-config.json').read_text())
    original=deepcopy(c);preview={'headers':['t','F','u','A','J'],'rows':[[0,1000,1.25,17.6,1.1]]}
    dialog=FiniteColumnsDialog(preview,c);dialog.geometry['L0'][0].setText('1e')
    assert dialog.draft_config()['geometry']['L0']['value']=='1e'
    dialog.calculate();assert dialog.table.rowCount()==1
    dialog.reject();assert dialog.result_config is None and c==original
    dialog=FiniteColumnsDialog(preview,c);dialog.geometry['L0'][0].setText('1e');dialog._accept()
    assert dialog.result_config['geometry']['L0']['value']=='1e'


def test_retained_audit_complete_rows_and_actual_prediction(app,tmp_path):
    root=Path(__file__).resolve().parents[2]/'examples/finite-measure'
    c=json.loads((root/'train-config.json').read_text());m=mapping(c);raw=read_table(root/'train.csv',m)
    result=preview_recipe(raw,dict(document_id='Tui',job_id='Jui',input_revision='Iui',input_sha256=canonical_hash(m)),recipe(c))
    dialog=FiniteAuditDialog(result);assert dialog.table.rowCount()==6
    from test_prediction import records
    raw=records();dialog=FinitePredictionDialog(raw);assert dialog.table.rowCount()==3
    assert '1.1' in dialog.table.item(1,3).text()
