"""Qt widget/selection/late callback test; NOT_RUN when PySide6 is unavailable.

All created Qt windows are closed in finally, including failed assertions. This
in-process widget check is NOT a real Windows/ParaView/OS-input acceptance test.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
from types import SimpleNamespace
import pytest
pytest.importorskip('PySide6',reason='NOT_RUN: PySide6 absent; Qt/OS acceptance not executed')
from PySide6.QtWidgets import QApplication,QDialog,QVBoxLayout,QLabel
from apps.research.post_curve_origin_ui import OriginDialog
from test_post_curve_origin import curve,recipe,payload,targets


@pytest.mark.parametrize('width',[520,1000])
def test_real_widgets_both_brackets_and_stale_callback_no_followup(width):
    app=QApplication.instance() or QApplication([])
    parent=QDialog();QVBoxLayout(parent);live=[True]
    controls=SimpleNamespace(plot=parent,host=SimpleNamespace(client=None),current=lambda basis:live[0])
    r=recipe();r['alignment']='bracket'
    r['b_axis_offset']=-.1
    data=payload(curve([0.,.5,1.],[0.,2.,4.]),curve([100.,1100.],[0.,.004],unit='kN',axis_unit='ms'),r)
    parent.payload=data
    choices=targets(data,'aligned',1)
    for target in choices:target['kind']='native_curve'
    dialog=None
    try:
        parent.show();dialog=OriginDialog(controls,{}, {'targets':choices});dialog.resize(width,640);dialog.show()
        app.processEvents()
        assert dialog.targets.count()==3 and dialog.raw_table.rowCount()==3
        dialog.targets.setCurrentIndex(2);app.processEvents()
        assert dialog.target()['raw']['identity']['row']==11
        assert dialog.raw_table.currentRow()==2
        assert dialog.open_button.text()=='원 측정 열기'
        assert '1100 ms' in dialog.targets.currentText() and '0.004 kN' in dialog.targets.currentText()
        assert dialog.raw_table.item(2,2).text()=='1100 ms'
        assert dialog.raw_table.item(2,3).text()=='0.004 kN'
        assert dialog.raw_table.item(2,4).text().endswith(' s')
        assert dialog.raw_table.item(2,5).text().endswith(' N')
        calls=[];dialog.phase='verify'
        dialog.operation=SimpleNamespace(invalidate=lambda:calls.append('invalidated'))
        live[0]=False
        dialog.completed({'status':'SOURCE_VERIFIED'},None)
        assert calls==['invalidated'] and dialog.worker is None
    finally:
        if dialog is not None:dialog.close()
        parent.close();app.processEvents()
