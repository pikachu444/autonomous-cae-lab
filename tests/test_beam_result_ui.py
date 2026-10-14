"""Display bounds of the existing Qt curve; no solver or new field calculation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest


def test_constant_curve_labels_use_the_same_padded_range_as_coordinates():
    from PySide6 import QtCore as C,QtWidgets as W
    from apps.desktop_pre.beam_visuals import curve_view
    app=W.QApplication.instance() or W.QApplication([])
    curve=curve_view(W,C);curve.resize(500,260)
    try:
        points=[(11,0.,1000.),(29,1000.,1000.)];curve.set_values(points,'1축 굽힘 모멘트 [Nmm]')
        assert curve.value_limits()==(920.,1080.) and curve.points==points
        assert [y for x,y in curve.coordinates()]==pytest.approx([130.,130.])
        curve.set_values([(11,0.,920.),(29,1000.,1080.)],'범위 [Nmm]')
        assert curve.value_limits()==(920.,1080.)
        assert [y for x,y in curve.coordinates()]==pytest.approx([220.,40.])
    finally:curve.close()
