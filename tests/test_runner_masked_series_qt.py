"""Existing retained-result navigation only; no solver or provider calls."""
import math
from copy import deepcopy
import pytest

from test_research_runner_ui import app, runner, until, series
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest


@pytest.mark.parametrize('width,height',[(980,650),(1420,900)])
def test_partial_history_gap_retains_original_values_and_selection(runner,app,tmp_path,width,height):
    viewer,client,_=runner
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/malgun.ttf')
    viewer.setFont(QFont('Malgun Gothic',10))
    response=series([0.,2.,None,6.,8.]);response['mask']=[True,True,False,True,True]
    saved=deepcopy(response)
    client.results['JA'].update(execution_status='PARTIAL_FAILURE',responses={'stress_xx':response})
    viewer.resize(width,height);viewer.show();viewer.result_button.click()
    until(app,lambda:viewer.values.rowCount()==5 and not viewer._pending)
    assert viewer.selected_job_id=='JA' and '전체 계산이 완료된 결과가 아닙니다' in viewer.result_summary.text()
    assert viewer.result_views.currentWidget() is viewer.canvas
    assert viewer.axes.lines[0].get_xdata().tolist()==[0.,1.,2.,3.,4.]
    plotted=viewer.axes.lines[0].get_ydata()
    assert plotted[0]==0. and plotted[1]==2. and math.isnan(plotted[2]) and plotted[3]==6.
    assert '제외 표본 1개' in viewer.response_label.text()
    assert client.results['JA']['responses']['stress_xx']==saved
    assert viewer.values.item(2,2).text()=='기록 없음 MPa' and viewer.values.item(2,3).text()=='false'
    assert 'None' not in viewer.values.item(2,2).text()
    app.processEvents();assert viewer.grab().save(str(tmp_path/f'after-{width}.png'))
    assert viewer.axes.bbox.height>100
    viewer.result_views.setCurrentWidget(viewer.values)
    viewer.values.setCurrentCell(2,2);viewer.values.setFocus()
    QTest.keyClick(viewer.values,Qt.Key.Key_Down)
    assert viewer.values.currentRow()==3
    # A new bounded read uses the same retained job and preserves its raw gap.
    viewer.row_start.setValue(1);viewer.row_count.setValue(3);viewer.read_rows_button.click()
    until(app,lambda:viewer.values.rowCount()==3 and not viewer._pending)
    assert client.calls[-1]==('response','JA',{'responses':['stress_xx'],'rows':[1,4]})
    assert math.isnan(viewer.axes.lines[0].get_ydata()[1])
    assert client.results['JA']['execution_status']=='PARTIAL_FAILURE'


@pytest.mark.parametrize('values,mask,valid',[
    ([0.,None,2.],[True,True,True],True),
    ([0.,float('inf'),2.],[True,True,True],True),
    ([0.,1.,2.],[True,False],True),
    ([0.,1.,2.],[True,0,True],True),
    ([0.,1.,2.],None,False),
    ([None,None,None],[False,False,False],True),
])
def test_invalid_or_empty_history_does_not_draw_a_curve(runner,app,values,mask,valid):
    viewer,_,_=runner
    response=series(values);response.update(mask=mask,valid=valid)
    viewer._draw_response('stress_xx',response,0)
    assert not viewer.axes.lines
    assert viewer.result_views.currentWidget() is viewer.values
    assert viewer.values.rowCount()==len(values)
