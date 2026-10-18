import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import json
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication, QScrollArea
from apps.research.material_test_dialog import ExperimentDialog
from apps.research.finite_measure_dialog import FiniteAuditDialog
from caelab.adapters.file_table import read_table
from caelab.data_processing import preview_recipe
from caelab.finite_measure_input import mapping,recipe
from caelab.finite_measure_protocol import recipe as driver_recipe
from caelab.finite_measure_prediction import comparison_extension
from caelab.storage import canonical_hash


@pytest.fixture
def context_case():
    root=Path(__file__).resolve().parents[2]/'examples/finite-measure'
    config=json.loads((root/'train-config.json').read_text(encoding='utf-8'));m=mapping(config)
    result=preview_recipe(read_table(root/'train.csv',m),dict(document_id='Tui',job_id='Jui',input_revision='Iui',input_sha256=canonical_hash(m)),recipe(config))
    settings=dict(model='neo_hooke',parameters={'mu':.8,'lmbda':5.},stress_unit='MPa',time_unit='s')
    trial=dict(source={'response':'finite_sigma'},role='holdout',response='stress_xx',weight=2.5,scale=.4,
        kinematics=driver_recipe('finite_lambda','x',lateral='free'),extensions={'finite_measure':comparison_extension('x')})
    return QApplication.instance() or QApplication([]),result,settings,trial


def test_same_measure_context_is_explicit_and_cancel_preserves_input(context_case):
    app,result,settings,trial=context_case;original=deepcopy((result,settings,trial))
    dialog=ExperimentDialog(settings,result,experiment=trial)
    try:
        assert 'Neo-Hooke' in dialog.measure_context.text()
        assert '원 응력: 공칭 응력 P [MPa]' in dialog.measure_context.text()
        assert '관측: 유한변형 진응력 σ' in dialog.measure_context.text()
        assert '각 후보의 실제 수락 F/J' in dialog.measure_context.text()
        assert '관측 정의 일치' in dialog.measure_context.text() and '6표본' in dialog.measure_context.text()
        dialog.finite_comparison.setChecked(False)
        assert '관측 정의를 확인' in dialog.measure_context.text()
        dialog.weight.setText('1e');dialog.resize(760,640);dialog.show();app.processEvents()
        assert dialog.findChild(QScrollArea).widgetResizable()
        dialog.reject();assert dialog.value is None and (result,settings,trial)==original
    finally:dialog.close();app.processEvents()


def test_alignment_failure_is_visible_without_reordering_or_new_values(context_case):
    app,result,settings,trial=context_case
    result['responses']['finite_lambda']['axes'][0]['values'][2]+=.01
    original=deepcopy(result);dialog=ExperimentDialog(settings,result,experiment=trial)
    try:
        assert '원행·시각 대응 확인' in dialog.measure_context.text()
        assert '원행·시각 대응: 6표본' not in dialog.measure_context.text()
        assert result==original
    finally:dialog.close();app.processEvents()


def test_audit_selected_row_exposes_stored_geometry_and_observation_J(context_case):
    app,result,settings,trial=context_case;original=deepcopy(result)
    dialog=FiniteAuditDialog(result)
    try:
        dialog.channels.setCurrentIndex(dialog.channels.findData('finite_sigma'))
        dialog.table.setCurrentCell(2,0)
        text=dialog.detail.text()
        assert '값 기여 원행: 3' in text and '판정 원행: 3' in text
        assert 'A0=20 mm²' in text and 'L0=50 mm' in text and '입력 관측 J=' in text
        assert '접촉식 표점 변위' in text and '표점 λ와 관측 J' in text
        dialog.channels.setCurrentIndex(dialog.channels.findData('finite_lambda'))
        assert dialog.table.currentRow()==2 and '값 기여 원행: 3' in dialog.detail.text()
        assert result==original
    finally:dialog.close();app.processEvents()


@pytest.mark.parametrize('basis,origin,has_J,label',[('jacobian',None,True,'입력 관측 J='),
    ('full_F',None,False,'관측 F에서 계산한 det(F)='),
    ('full_F',None,True,'입력 J — F의 det와 일치 확인='),
    ('isochoric_assumption','EXPLICIT_ASSUMPTION_NOT_MEASURED',True,'명시 가정 J=1')])
def test_audit_J_caption_respects_stored_origin(context_case,basis,origin,has_J,label):
    app,result,settings,trial=context_case
    channel=result['channels']['finite_sigma']
    channel['metadata']['extensions']['finite_measure']['payload']['basis']=basis
    if origin:
        channel['lineage']['nodes'][channel['samples'][0]['sample_id']]['nonlinear_relation']['audit']['J_origin']=origin
    if not has_J:
        channel['lineage']['nodes'][channel['samples'][0]['sample_id']]['nonlinear_relation']['operands'].pop('J',None)
    dialog=FiniteAuditDialog(result)
    try:
        dialog.channels.setCurrentIndex(dialog.channels.findData('finite_sigma'))
        assert label in dialog.detail.text()
        if origin:assert '입력 관측 J=' not in dialog.detail.text()
    finally:dialog.close();app.processEvents()


def test_incomplete_material_context_stays_editable_and_cancelable():
    app=QApplication.instance() or QApplication([])
    dialog=ExperimentDialog({}, {'responses':{}})
    try:
        assert '미지정' in dialog.measure_context.text()
        dialog.weight.setText('1e');assert dialog.weight.text()=='1e'
        dialog.reject();assert dialog.value is None
    finally:dialog.close();app.processEvents()
