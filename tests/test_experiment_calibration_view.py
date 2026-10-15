"""Read exact saved calibration and recover presentation without another import."""
from copy import deepcopy

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QTabWidget
from apps.research.appearance import apply_appearance
from apps.research.experiment_dialogs import CalibrationDialog, AcquisitionDialog
from caelab.workbench import Workbench
from test_experiment_calibration import calibration, imported, mapping


@pytest.fixture
def app():
    app=QApplication.instance() or QApplication([])
    apply_appearance(app)
    return app


def test_cold_saved_calibration_separates_quality_selection_and_visibility(app,tmp_path,monkeypatch):
    import apps.research.experiment_dialogs as module
    store=tmp_path/'store'
    wb=Workbench(store)
    try:
        document,job,_,_=imported(wb)
    finally:wb.shutdown()
    wb=Workbench(store)
    try:
        response=wb.document_result(document['id'],job)['responses']['force']
    finally:wb.shutdown()
    original=deepcopy(response)
    monkeypatch.setattr(module,'calibrate',lambda *a:pytest.fail('saved view recalculated'))
    # A later mapping must not become the labels/settings of this retained import.
    later=mapping(calibration())['columns']['force'];later['calibration']['a']=999
    window=CalibrationDialog(None,later,None,retained_response=response)
    try:
        window.resize(800,650);window.show();app.processEvents()
        assert window.width()==800
        assert window.fields['a'].text()=='2.0' and window.fields['a'].isReadOnly()
        assert not window.ukind.isEnabled() and not window.upload.isVisible()
        assert window.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok) is None
        assert window.fields['uncertainty/k'].text()==''
        assert window.correlation.currentData()=='UNKNOWN'
        assert window.values.item(2,4).text()=='유효'
        assert window.values.item(2,5).text()=='사용'
        assert window.values.item(2,6).text()=='숨김'
        assert window.values.item(3,3).text()=='범위 밖; 센서 포화'
        assert window.values.item(3,4).text()=='제외'
        assert window.values.item(3,5).text()=='사용 안 함'
        assert window.values.item(3,6).text()=='표시'
        before=window.values.item(1,2).text()
        window.values.selectRow(1);window.values.setFocus()
        QTest.keyClick(window.values,Qt.Key.Key_Return)
        assert window.isVisible() and window.values.item(1,2).text()==before
        # Missing/short retained arrays must not partly clear the last good view.
        window.retained_response['raw_samples']['calculation_valid'].pop()
        window.refresh_preview()
        assert '행 수가 다릅니다' in window.message.text()
        assert window.values.currentRow()==1 and window.values.item(1,2).text()==before
        window.retained_response=deepcopy(response);window.refresh_preview()
        assert window.values.currentRow()==1 and '보존' in window.message.text()
        assert response==original
    finally:window.close();window.deleteLater();app.processEvents()


def test_editing_partial_uncertainty_remains_a_draft_and_enter_does_not_apply(app):
    recipe=calibration()
    window=CalibrationDialog(None,mapping(recipe)['columns']['force'],{
        'table_preview':{'headers':['t','voltage'],'rows':[[0,.001],[1,.005]],'row_numbers':[1,2]}})
    try:
        window.show();app.processEvents()
        before=window.values.item(1,2).text()
        window.fields['uncertainty/value'].setText('1e')
        window.fields['uncertainty/value'].textEdited.emit('1e')
        window.findChild(QTabWidget).setCurrentIndex(3)
        window.fields['uncertainty/value'].setFocus()
        QTest.keyClick(window.fields['uncertainty/value'],Qt.Key.Key_Return)
        assert window.isVisible()
        window.refresh_preview()
        assert window.edited()['uncertainty']['value']=='1e'
        assert window.values.item(1,2).text()==before
        assert '미적용' in window.message.text()
        window.fields['uncertainty/value'].setText('.2');window.refresh_preview()
        assert window.edited()['uncertainty']['k'] is None
        assert window.edited()['uncertainty']['correlation']=='UNKNOWN'
        assert '미리보기' in window.message.text()
        assert recipe['uncertainty']['value']==.1
    finally:window.close();window.deleteLater();app.processEvents()


def test_acquisition_enter_edits_without_applying_until_button_is_selected(app):
    window=AcquisitionDialog(None,{})
    try:
        window.show();app.processEvents()
        window.fields['sample_rate_hz'].setFocus()
        QTest.keyClicks(window.fields['sample_rate_hz'],'1e')
        QTest.keyClick(window.fields['sample_rate_hz'],Qt.Key.Key_Return)
        assert window.isVisible() and window.edited()['sample_rate_hz']=='1e'
        apply=window.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)
        apply.setFocus();QTest.keyClick(apply,Qt.Key.Key_Return)
        assert not window.isVisible() and window.result()==window.DialogCode.Accepted
        assert window.edited()['sample_rate_hz']=='1e'
    finally:window.close();window.deleteLater();app.processEvents()
