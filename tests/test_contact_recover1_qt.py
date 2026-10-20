"""Real Qt checks when PySide6 is installed. Native FreeCAD remains a double."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
pytest.importorskip('PySide6', reason='RECOVER1 native Qt module is not installed')
from PySide6 import QtWidgets as W, QtCore as C
from apps.research.post_resultant_controls import ResultantControls
from test_contact_recover1 import moment_spec


@pytest.fixture
def app():
    value=W.QApplication.instance() or W.QApplication([])
    yield value
    value.processEvents()


def test_resultant_controls_keep_reference_frame_and_invalid_draft(app):
    events=[];controls=ResultantControls(lambda:events.append(True))
    try:
        assert controls.value() is None
        controls.load(moment_spec())
        assert controls.value()==moment_spec()
        controls.point.item(0,0).setText('1e')
        assert controls.value()['reference_point_mm'][0]=='1e'
        assert events
        controls.load(moment_spec())
        controls.only_frame.setChecked(True)
        assert controls.only_frame.isChecked() and controls.value()==moment_spec()
    finally:controls.close();controls.deleteLater()




def test_disabling_moment_requires_force_reread_before_save(app):
    from apps.research.post_contact_dialog import ContactDialog
    post=W.QWidget()
    post.document={'id':'Pcontrolled','session_id':'Scontrolled'}
    post.document_id,post.session_id='Pcontrolled','Scontrolled'
    post._busy=False;post._pending=None;post.conflict=False
    post._last_command=None;post.local_dirty=False;post.message=W.QLabel()
    calls=[]
    post.queue_command=lambda operation,args,**kwargs:calls.append((operation,deepcopy(args))) or True
    dialog=ContactDialog(post,'Source')
    try:
        for combo,value in ((dialog.pair,'Pair'),(dialog.frame,0),(dialog.field,'CPRESS')):
            combo.addItem(str(value),value)
        dialog.resultants.load(moment_spec())
        dialog.payload={'selection':deepcopy(dialog.selection()),'offset':0,'next_offset':None}
        original=deepcopy(dialog.payload)
        calls.clear()  # Discard the constructor's initial read request.
        dialog.sync();assert dialog.save_measurement.isEnabled()
        dialog.resultants.enabled.setChecked(False)
        assert not dialog.save_measurement.isEnabled()
        assert dialog.create_measurement() is False and calls==[]
        assert dialog.payload==original
        # Controlled owner response for the explicit force re-read; no calculation.
        dialog.read()
        assert calls[-1][0]=='post.contact_inspect' and calls[-1][1]['resultant'] is None
        dialog.payload={'selection':deepcopy(dialog.selection()),'offset':0,'next_offset':None}
        dialog.sync();assert dialog.save_measurement.isEnabled()
        dialog.create_measurement()
        assert calls[-1][0]=='post.contact_measurement' and calls[-1][1]['resultant'] is None
    finally:
        dialog.close();dialog.deleteLater();post.close();post.deleteLater()
