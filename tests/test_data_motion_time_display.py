"""Local Data window keeps NumPy values intact while rendering diagnostics."""
import json
from copy import deepcopy
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
from PySide6.QtWidgets import QApplication
from apps.research.data_window import DataWindow,display
from test_research_data_numerical_ui import data_document


def test_local_numpy_diagnostics_and_motion_time_labels_preserve_source_values():
    app=QApplication.instance() or QApplication([])
    window=DataWindow(object(),auto_open=False,poll_interval=0)
    try:
        window._show_document(data_document())
        window._result_channel='Z';key=window._result_key()
        response={'kind':'series','value':[0.,90.,180.],'unit':'mm','source_rows':[np.int64(3),np.int64(4),np.int64(5)],
            'component':'z','location':'trace_point:운반대 끝점','frame':'document_global','measure':'position',
            'axes':[{'name':'time','unit':'s','values':[0.,.5,1.]}]}
        receipt={'status':{'state':'SUCCEEDED'},'result':{'responses':{'Z':response}}}
        window._results[key]=receipt
        window._preview={'source_rows':np.array([2,3,4,5],dtype=np.int64),'offset':np.int64(2)}
        original=deepcopy(response);original_bytes=window._preview['source_rows'].tobytes()
        for axis,label in [('time','계산 시각 [s]'),('nominal_time','출력 격자 시간 [s]')]:
            response['axes'][0]['name']=axis
            window._draw_result(receipt,key)
            parsed=json.loads(window.details.toPlainText())
            assert parsed['source_preview']['source_rows']==[2,3,4,5] and parsed['source_preview']['offset']==2
            assert parsed['selected_result']['result']['responses']['Z']['source_rows']==[3,4,5]
            assert window.axes.get_xlabel()==label and '세계 좌표' in window.axes.get_title()
            assert [list(line.get_xdata()) for line in window.axes.lines]==[[0.,.5,1.]]
            assert [list(line.get_ydata()) for line in window.axes.lines]==[[0.,90.,180.]]
        assert response['value']==original['value'] and response['axes'][0]['values']==original['axes'][0]['values']
        assert all(isinstance(row,np.int64) for row in response['source_rows'])
        assert window._preview['source_rows'].tobytes()==original_bytes
        assert display(np.int64(9))=='9' and display(np.array([1,2]))=='[1, 2]'
        assert window.sheets.currentWidget() is not window.details
        window.sheets.setCurrentWidget(window.details);app.processEvents()
        assert json.loads(window.details.toPlainText())['selected_result']['result']['responses']['Z']['value']==[0.,90.,180.]
    finally:
        window._allow_close=True;window.close();window.deleteLater();app.processEvents()
