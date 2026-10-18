"""Finite recipe captions preserve raw values, assumptions, and source bytes."""
from copy import deepcopy
import json
import os
from pathlib import Path

import pytest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from apps.research.data_processing_dialog import DataProcessingRecipeDialog, OPERATIONS, _finite_recipe_summary


def spec(**updates):
    return dict(output='finite_Cauchy',unit='MPa',axis='x',basis='jacobian',
        channels={'J':'authored J','area':'authored area'},geometry={'A0':{'value':'1e','unit':'mm2','evidence':''}},
        measurement='extensometer_gauge_extension',assumptions={},scope='uniaxial_coaxial',frame='material_cartesian',**updates)


@pytest.mark.parametrize('basis,expected', [('none','추가 응력 측도 변환 없음'),('current_area','현재 면적 채널: authored area'),
    ('jacobian','관측 J 채널: authored J'),('full_F','입력 J 일치 확인 대상: authored J'),
    ('isochoric_assumption','J=1 가정 선택 (관측 아님)')])
def test_declared_basis_does_not_confuse_assumptions_and_observed_J(basis,expected):
    value=spec();value['basis']=basis;before=deepcopy(value)
    shown=_finite_recipe_summary(value)
    assert expected in shown and 'A0=1e mm2' in shown
    assert '명시 가정 없음' in shown and value==before


def test_assumptions_missing_unknown_and_disabled_are_not_validated_defaults():
    value=spec();value['assumptions']={'isochoric':{'enabled':True,'reason':''},
        'crosshead_equals_gauge':{'enabled':False,'reason':'old reason'}}
    shown=_finite_recipe_summary(value)
    assert 'J=1 등체적 가정: 사용 (근거 미제공)' in shown
    assert '크로스헤드 = 표점 변위 가정: 미사용' in shown
    value['basis']='authored unknown';value['measurement']='unrecognized measurement'
    assert 'authored unknown' in _finite_recipe_summary(value)
    assert 'unrecognized measurement' in _finite_recipe_summary(value)
    assert 'finite_observation' not in OPERATIONS


def test_unrelated_operation_keeps_original_tooltips():
    app=QApplication.instance() or QApplication([])
    operation=dict(id='Ounchanged',operation='stretch',input='authored input',output='authored output',settings={})
    dialog=DataProcessingRecipeDialog({'version':1,'operations':[operation]},['authored input'])
    try:
        assert all(dialog.table.item(0,col).toolTip()==dialog.table.item(0,col).text() for col in range(4))
        assert dialog.recipe['operations']==[operation]
    finally:
        dialog.close();dialog.deleteLater();app.processEvents()


def test_actual_Te8_recipe_display_cancel_accept_and_bytes_unchanged(tmp_path):
    source=Path(__file__).resolve().parents[1]/'_workspace/data-companion-owner-20261018/owned-source/workbench/documents/Te8f2f17dbfd0447f9708241245dbf069/working.json'
    if not source.exists():pytest.skip('Private exact Te8 retained recipe is not supplied')
    original=source.read_bytes();recipe=json.loads(original)['draft']['processing']['recipe'];before=deepcopy(recipe)
    app=QApplication.instance() or QApplication([])
    from apps.research.appearance import apply_appearance
    apply_appearance(app)
    dialog=DataProcessingRecipeDialog(recipe,['fm_load','fm_deformation','fm_J','fm_area'])
    try:
        dialog.show();app.processEvents()
        for row,op in enumerate(recipe['operations']):
            assert dialog.table.item(row,0).text()=='유한변형 관측 변환'
            assert dialog.table.item(row,1).text()==op['input'] and dialog.table.item(row,2).text()==op['output']
            assert dialog.table.item(row,3).text()==_finite_recipe_summary(op['settings'])
            assert all(dialog.table.item(row,col).toolTip()==repr(op) for col in range(4))
        for width,height in [(1040,650),(800,600)]:
            dialog.resize(width,height);dialog.table.selectRow(1);dialog.table.setFocus();app.processEvents()
            assert dialog.grab().save(str(tmp_path/f'recipe-{width}.png'))
        dialog.reject();assert dialog.recipe==before and source.read_bytes()==original
        dialog.accept();assert dialog.recipe==before and recipe==before and source.read_bytes()==original
    finally:
        dialog.close();dialog.deleteLater();app.processEvents()
