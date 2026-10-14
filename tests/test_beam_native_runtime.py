"""Opt-in native GUI acceptance; never replace an absent runtime with a fake."""
import importlib.util
import os
from pathlib import Path
import pytest


def test_native_end_moment_units_survive_fcstd_reopen(tmp_path):
    if not importlib.util.find_spec('FreeCAD'):
        pytest.skip('Native FreeCAD kernel is unavailable')
    import FreeCAD as App
    from apps.desktop_pre.beam_edit import make_end
    doc=App.newDocument('BeamMomentUnits')
    try:
        end=make_end(doc,'End');end.MomentY='1000 N*mm'
        path=tmp_path/'end-moment.FCStd';doc.saveAs(str(path))
        App.closeDocument(doc.Name);doc=App.openDocument(str(path))
        restored=doc.getObject('End')
        assert restored.getTypeIdOfProperty('MomentY')=='App::PropertyMoment'
        assert restored.MomentY.getValueAs('N*mm').Value==1000
        assert restored.MomentX.getValueAs('N*mm').Value==0
    finally:
        App.closeDocument(doc.Name)


def test_legacy_quantity_moment_reopen_preserves_internal_scalar(tmp_path):
    if not importlib.util.find_spec('FreeCAD'):
        pytest.skip('Native FreeCAD kernel is unavailable')
    import FreeCAD as App
    from apps.desktop_pre.beam_edit import BeamEndProxy
    doc=App.newDocument('LegacyBeamMoment')
    try:
        obj=doc.addObject('App::FeaturePython','End');BeamEndProxy(obj)
        for axis in 'XYZ':
            obj.addProperty('App::PropertyQuantity','Moment'+axis)
            setattr(obj,'Moment'+axis,App.Units.Unit('N*mm'));setattr(obj,'Moment'+axis,'1000 N*mm')
        scalar=obj.MomentY.Value;path=tmp_path/'legacy-moment.FCStd';doc.saveAs(str(path))
        App.closeDocument(doc.Name);doc=App.openDocument(str(path))
        assert doc.End.MomentY.Value==scalar and doc.End.MomentY.getValueAs('N*mm').Value==1000
    finally:App.closeDocument(doc.Name)


def test_real_freecad_export_and_fresh_owner(tmp_path):
    if not importlib.util.find_spec('FreeCAD'):
        pytest.skip('FreeCAD 1.1.4 is unavailable; run VerifyBeam.FCMacro on the real installation')
    if os.environ.get('CAE_BEAM_NATIVE_ACCEPTANCE')!='1':
        pytest.skip('Native GUI/owner acceptance is opt-in; use a separate FreeCAD process')
    from examples.beam.beam_native_acceptance import export_and_reopen
    import json
    result=json.loads(export_and_reopen(tmp_path).read_text())
    assert all(row['status']=='PASS' for row in result['cases'].values())


def test_real_qt_widget_construction_and_narrow_layout(tmp_path):
    if not importlib.util.find_spec('PySide6'):
        pytest.skip('No Qt binding: widget layout and OS interactions not verified')
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6 import QtWidgets as W,QtCore as C
    from apps.desktop_pre.beam_visuals import section_view,curve_view
    app=W.QApplication.instance() or W.QApplication([])
    section=section_view(W,C);section.resize(320,240);section.set_section('10','20','90');section.show();app.processEvents()
    assert not section.grab().isNull()
    graph=curve_view(W,C);graph.resize(420,260);graph.set_values([(101,0,1),(408,250,2)],'단면력 [N]');graph.show();app.processEvents()
    assert not graph.grab().isNull()
    section.close();graph.close()
