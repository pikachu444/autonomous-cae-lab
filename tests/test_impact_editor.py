import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from apps.research.impact_editor import ImpactEditor
from examples.impact.user_model import settings


def test_cancel_precise_and_partial_motion_edit_are_local():
    app=QApplication.instance() or QApplication([])
    original=settings();window=ImpactEditor(original)
    window.resize(1060,700);window.show();app.processEvents()
    window.motion.item(0,5).setText('1e')
    edited=window.edited()
    assert edited['motions'][0]['velocity_mm_s'][2]=='1e'
    assert original['motions'][0]['velocity_mm_s'][2]==-100.
    window.reject();app.processEvents()
    reopened=ImpactEditor(edited)
    reopened.motion.item(0,5).setText('-125.123456789012')
    assert reopened.edited()['motions'][0]['velocity_mm_s'][2]==-125.123456789012
    assert reopened.motion.cellWidget(0,1).currentData()=='velocity'
    reopened.reject()
