"""Native Qt controls only; skipped, not accepted, when PySide6 is absent."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import json
from types import SimpleNamespace as NS
import pytest
W=pytest.importorskip('PySide6.QtWidgets')
from PySide6 import QtCore as C
from apps.desktop_pre.beam_output_panel import make_widget
from b13_raw_fixture import raw_model


def test_focused_raw_output_snapshot_and_load_are_distinct():
    app=W.QApplication.instance() or W.QApplication([]);calls=[];d=raw_model()['draft']
    editor=NS(owner=NS(doc=NS(getObject=lambda _:None)))
    widget=make_widget(W,C,editor,lambda:deepcopy(d),lambda:calls.append(True))
    try:
        widget.set_draft(d);widget.show();app.processEvents()
        widget.reference_fields[0].setText('1e');widget.reference_fields[0].setFocus();app.processEvents()
        pending=widget.merge_draft(deepcopy(d))
        assert pending['output']['reference_mm'][0]=='1e' and calls
        assert d['output']['reference_mm'][0]=='0'
        widget.set_draft(d);assert widget.reference_fields[0].text()=='0'
    finally:
        widget.close();widget.deleteLater();app.processEvents()


@pytest.mark.parametrize('tab,expected_quantity,expected_units',[
    ('유도 회전','derived_rotation','rad'),
    ('지지 응답','support_observations',{'force':'N','moment':'Nmm','reference':'mm'})])
def test_export_uses_actual_table_meaning_after_unrelated_field_choices(tmp_path,monkeypatch,tab,expected_quantity,expected_units):
    from apps.desktop_pre.b13_result_window import _open
    app=W.QApplication.instance() or W.QApplication([])
    def build(*_):
        return {'확장 절점':(['EXX [1]'],[[.01]],'변형률'),
            '유도 회전':(['θX [rad]'],[[.1]],'미소 강체-fit'),
            '지지 응답':(['FX [N]'],[[4.]],'원 RF 합')}
    window=_open(W,C,parent=None,title='검사 결과',frames=[{'static':{'step':1,'increment':1,'load_parameter':1.}}],
        builder=build,sources={},status='SUCCEEDED',source_identity='scripted readonly fixture',
        quantities=[('S','응력 [MPa]'),('E','변형률 [1]')],observation_pins=[{'relative':'beam.frd','sha256':'a'*64}])
    try:
        quantity=window.findChild(W.QComboBox,'b13Quantity');basis=window.findChild(W.QComboBox,'b13Basis')
        quantity.setCurrentIndex(1);basis.setCurrentIndex(1)
        tabs=window.findChild(W.QTabWidget);tabs.setCurrentIndex(tabs.indexOf(next(
            tabs.widget(i) for i in range(tabs.count()) if tabs.tabText(i)==tab)))
        app.processEvents()
        assert quantity.currentData()=='E' and basis.currentData() is True
        assert not quantity.isEnabled() and not basis.isEnabled()
        path=tmp_path/'observations.csv'
        monkeypatch.setattr(W.QFileDialog,'getSaveFileName',lambda *a,**k:(str(path),'CSV (*.csv)'))
        window.findChild(W.QPushButton,'exportB13Table').click()
        receipt=json.loads(path.with_name(path.name+'.provenance.json').read_text(encoding='utf-8'))
        assert receipt['quantity']==expected_quantity and receipt['units']==expected_units
        assert receipt['coordinate_frame']=='global' and receipt['display_basis']=='전체 좌표계'
        assert receipt['frame']=={'step':1,'increment':1,'load_parameter':1.}
        assert receipt['source_pins']==[{'relative':'beam.frd','sha256':'a'*64}]
        assert receipt['coordinate_frame']!='declared_element_axes' and receipt['native_engineering_acceptance'] is False
    finally:
        window.close();app.processEvents()
