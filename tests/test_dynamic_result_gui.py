"""Qt presentation of explicit retained-output doubles; no solver execution."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import json
import pytest
W=pytest.importorskip('PySide6.QtWidgets')
from PySide6 import QtCore as C
from PySide6.QtTest import QTest
from apps.desktop_pre import dynamic_result_window as result_ui


@pytest.fixture(scope='module')
def app():
    from PySide6.QtGui import QFontDatabase
    application=W.QApplication.instance() or W.QApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/malgun.ttf')
    return application


def retained_double():
    stages=[{'id':'Sstatic','label':'선행 하중','index':1,'procedure':'static'},
            {'id':'Sdynamic','label':'자유 진동','index':2,'procedure':'dynamic'}]
    frames=[]
    for i,t in enumerate((None,.2,.5,1.)):
        dynamic=t is not None;stage=stages[int(dynamic)]
        frames.append({'native':{'step':stage['index'],'increment':i or 1,'load_parameter':1.+(t or 0.)},
            'native_time_token':str(1.+(t or 0.)),
            'location':{**stage,'native_global_coordinate':1.+(t or 0.),
                'native_step_coordinate_derived':t or 1.,'physical_time_s':t,'physical_time_available':dynamic},
            'fields':{'DISP':{1:[t or 0.,0.,0.]},'VELO':{1:[1.,0.,0.]},'FORC':{1:[2.,0.,0.]}},
            'restrained_dofs':[[1,1]],
            'acceleration':{'values':{1:[3. if i==2 else None]*3},
                'missing':{1:[None if i==2 else 'step_output_boundary']*3}},
            'energy':{q:{'rows':[{'element_id':1,'integration_point':1,'value':4.,'missing_reason':None}],
                'total':4.,'reason':None} for q in ('ELKE','ELSE','ENER')}})
    return {'execution_status':'FAILED','frames':frames,'stages':stages,
            'nodes':[{'node_id':1,'body_id':'Solid','native_node_id':17}],
            'elements':[{'element_id':1,'body_id':'Solid','native_element_id':23}],
            'meanings':deepcopy(result_ui.MEANINGS)}


@pytest.mark.parametrize('width',[760,980])
def test_exact_result_selection_masks_and_post_failure_remain_actionable(tmp_path,monkeypatch,app,width):
    data=retained_double();original=deepcopy(data);reads=[];warnings=[];launches=[]
    app_style=app.styleSheet()
    (tmp_path/'contact_execution.json').write_text(json.dumps({'dynamic_result':{'relative':'double.json'}}))
    def read(path):reads.append(path);return deepcopy(data)
    def post(path):launches.append(path);raise ValueError('이 실행의 저장된 공간 결과가 없습니다.')
    monkeypatch.setattr(result_ui,'read_attempt',read)
    monkeypatch.setattr(W.QMessageBox,'warning',lambda _,title,message:warnings.append((title,message)))
    window=result_ui.open_result(W,C,attempt=tmp_path,on_post=post)
    try:
        window.resize(width,560 if width==760 else 740);window.show();app.processEvents()
        summary=window.findChild(W.QLabel,'dynamicResultSummary')
        assert '계산 실패' in summary.text() and 'FAILED' not in summary.text()
        assert str(tmp_path) not in summary.text() and str(tmp_path) in summary.toolTip()
        assert 'UNKNOWN / NOT_RELEASED' in summary.toolTip()
        assert app.styleSheet()==app_style
        assert window.frame_table.horizontalHeaderItem(2).text()=='원본 증분'
        assert window.frame_table.item(0,4).text()=='1.0 [1]'
        assert window.frame_table.item(0,5).text()=='해당 없음(정적)'
        assert window.frame_table.item(1,4).text()=='0.2 [s]'
        assert window.frame_table.item(1,5).text()=='0.2'
        assert result_ui.physical_time_text({'procedure':'dynamic','physical_time_s':None})=='결측'
        assert '가상좌표' in window.coordinate_note.text()
        tabs=window.findChildren(W.QTabWidget)[0];tabs.setCurrentIndex(1);app.processEvents()
        window.grab().save(str(tmp_path/('mixed-static-'+str(width)+'.png')))
        window.frame_table.setFocus();QTest.keyClick(window.frame_table,C.Qt.Key_Down);app.processEvents()
        assert window.frame_table.currentRow()==1 and '누적 시간' in window.coordinate_note.text()
        assert '정적' not in window.coordinate_note.text()
        assert window.frame_table.item(1,3).toolTip().endswith('원값: 1.2')
        window.grab().save(str(tmp_path/('mixed-dynamic-'+str(width)+'.png')))
        tabs.setCurrentIndex(0)
        assert window.step.itemText(1)=='2: 자유 진동' and window.step.itemData(1)=='Sdynamic'
        assert window.values.rowCount()==3 and window.values.item(0,0).text()=='0.2'
        window.quantity.setCurrentIndex(window.quantity.findData('A_DERIVED'));app.processEvents()
        assert [window.values.item(i,4).text() for i in range(3)]==['결측','3','결측']
        assert window.values.item(0,5).text()=='단계의 첫·마지막 출력'
        assert window.values.item(0,5).toolTip()=='step_output_boundary'
        assert [row['value'] for row in window.plot.rows]==[None,3.,None]
        window.quantity.setCurrentIndex(window.quantity.findData('FORC'));app.processEvents()
        assert window.values.item(0,5).text()=='구속 자유도의 반력'
        window.component.setFocus();QTest.keyClick(window.component,C.Qt.Key_Down);app.processEvents()
        assert window.values.item(0,5).text()=='비구속 자유도의 절점력'
        window.quantity.setCurrentIndex(window.quantity.findData('ELKE'));app.processEvents()
        assert window.values.item(0,4).text()=='4' and not window.node.isEnabled()
        next(b for b in window.findChildren(W.QPushButton) if b.text()=='계산 목록에서 후처리 열기').click()
        assert launches==[tmp_path] and warnings==[('후처리 열기 실패','이 실행의 저장된 공간 결과가 없습니다.')]
        assert reads==[tmp_path] and data==original
        window.grab().save(str(tmp_path/('physical-history-'+str(width)+'.png')))
    finally:
        window.close();app.processEvents();C.QCoreApplication.sendPostedEvents(None,C.QEvent.DeferredDelete)


def test_failed_attempt_without_fields_keeps_original_status_in_details(tmp_path,app):
    (tmp_path/'contact_execution.json').write_text(json.dumps({'execution_status':'REJECTED','artifacts':[]}))
    window=result_ui.open_result(W,C,attempt=tmp_path)
    try:
        summary=window.findChild(W.QLabel,'dynamicResultSummary')
        assert '계산 거절' in summary.text() and 'REJECTED' in summary.toolTip()
        assert str(tmp_path) not in summary.text()
    finally:
        window.close();app.processEvents();C.QCoreApplication.sendPostedEvents(None,C.QEvent.DeferredDelete)


@pytest.mark.parametrize('width',[760,980])
def test_v2_stage_catalog_does_not_read_frame_arrays_again(tmp_path,monkeypatch,app,width):
    from PySide6.QtGui import QFont,QFontDatabase
    from test_dynamic_results import run_double
    from test_dynamic_support import dynamic_model
    from caelab import dynamic_result_store as store
    _,output=run_double(monkeypatch,tmp_path,dynamic_model())
    original=store._json;reads=[]
    def tracked(root,pin,limit=store.MAX_BYTES):
        reads.append(pin['relative']);return original(root,pin,limit)
    monkeypatch.setattr(store,'_json',tracked)
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/malgun.ttf')
    app.setFont(QFont('Malgun Gothic',10))
    window=result_ui.open_result(W,C,attempt=output)
    try:
        window.resize(width,560 if width==760 else 740);window.show();app.processEvents()
        # The explicitly displayed DISP history reads each frame once. The stage catalog uses only index metadata.
        assert len([p for p in reads if '/frame' in p])==3
        assert window.values.rowCount()==3
        tabs=window.findChildren(W.QTabWidget)[0];tabs.setCurrentIndex(1);app.processEvents()
        assert '동적 단계' in window.coordinate_note.text() and '정적' not in window.coordinate_note.text()
        assert window.frame_table.item(0,4).text()=='0.2 [s]'
        assert app.styleSheet()=='' or '#DynamicResult' not in app.styleSheet()
        assert len([p for p in reads if '/frame' in p])==3
        window.grab().save(str(tmp_path/('v2-stage-catalog-'+str(width)+'.png')))
        tabs.setCurrentIndex(0);window.quantity.setFocus();QTest.keyClick(window.quantity,C.Qt.Key_Down)
        assert window.quantity.currentData()=='VELO' and window.values.rowCount()==3
        assert len([p for p in reads if '/frame' in p])==6
    finally:
        window.close();app.processEvents();C.QCoreApplication.sendPostedEvents(None,C.QEvent.DeferredDelete)
