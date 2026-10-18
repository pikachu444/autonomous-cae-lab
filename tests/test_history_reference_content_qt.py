"""A saved history keeps its transformed unit and visible missing interval."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from types import SimpleNamespace
import math
import pytest
from PySide6.QtWidgets import QApplication,QLabel
from caelab.impact_bulk_results import response
from caelab.impact_responses import select_history
from caelab.impact_history_binding import capsule,selected_result
from caelab.storage import canonical_hash
from apps.research.reference_content import ReferenceContent
from apps.research.study_window import StudyWindow


def test_fixed_history_unit_gap_and_channel_recovery():
    app=QApplication.instance() or QApplication([])
    channel=response([0.,.1,.2],[1.,None,-2.],unit='N s',label='원 충격량',
        measure='native_cumulative_contact_impulse',selection={'scope':'pair','identity':0,'quantity':'impulse','component':'FNZ'})
    result={'execution_status':'FAILED','responses':{'impulse':channel}}
    source={'document_id':'Vtest','job_id':'Jtest','input_revision':'Itest',
        'input_sha256':'1'*64,'result_sha256':canonical_hash(result)}
    packet=select_history({'source':source,'result':result},
        dict(response='impulse',start_s=0.,end_s=.2,side='native',transform='identity'))
    reference={'kind':'result',**source,'response':'impulse','selection':capsule(packet)}
    payload={'kind':'result','status':'AVAILABLE','reference':reference,
        'metadata':{'responses':[{'response':'impulse','unit':'N'},{'response':'other','unit':'MPa'}]},
        'result':selected_result(source,result,capsule(packet))}
    view=ReferenceContent();view.show()
    try:
        view.set_payload(payload);app.processEvents()
        assert view.channel.count()==1 and view.channel.currentText()=='impulse [N s]'
        assert view.values.rowCount()==2
        y=list(view.axes.lines[0].get_ydata())
        assert y[0]==1. and math.isnan(y[1]) and y[2]==-2.
        # A stale wider catalog must also recover the existing fixed view.
        view.channel.addItem('other [MPa]','other');view.channel.setCurrentIndex(1)
        view._draw_result();assert view.values.rowCount()==0
        owner=SimpleNamespace(_content_reference=reference,reading=view,message=QLabel())
        StudyWindow.read_response(owner,'other');app.processEvents()
        assert view.channel.currentData()=='impulse' and view.values.rowCount()==2
        assert view.axes.get_ylabel()=='impulse [N s]'
        assert math.isnan(list(view.axes.lines[0].get_ydata())[1])
        assert owner._content_reference==reference
    finally:view.close();app.processEvents()
