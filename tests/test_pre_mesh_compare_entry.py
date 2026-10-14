"""Native menu routing with Qt controls and explicit FreeCAD stand-ins."""
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace as NS

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest

QtWidgets = pytest.importorskip('PySide6.QtWidgets')
QtCore = pytest.importorskip('PySide6.QtCore')
QtGui = pytest.importorskip('PySide6.QtGui')


def test_menu_comparison_selects_same_document_mesh_and_releases_closed_dialog(monkeypatch):
    from apps.desktop_pre import mesh_compare_panel
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    main = QtWidgets.QMainWindow()
    document = NS(Objects=[])
    mesh = NS(Name='MeshGmsh', Document=document, TypeId='Fem::FemMeshShapeBaseObjectPython',
              Proxy=NS(Type='Fem::FemMeshGmsh'))
    document.Objects.append(mesh)
    selection = []
    gui = NS(Selection=NS(getSelection=lambda: selection), getMainWindow=lambda: main,
             getIcon=lambda _: QtGui.QIcon())
    monkeypatch.setitem(sys.modules, 'FreeCAD', NS())
    monkeypatch.setitem(sys.modules, 'FreeCADGui', gui)
    monkeypatch.setitem(sys.modules, 'PySide', NS(QtWidgets=QtWidgets, QtCore=QtCore, QtGui=QtGui))
    spec = importlib.util.spec_from_file_location('cae_prep_entry_test',
        Path(__file__).parents[1] / 'apps/desktop_pre/cae_prep.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    owner = NS(doc=document, fem=NS(_mesh=lambda target: mesh))
    module.CONNECTION = NS(active_owner=lambda: owner)
    def create(widgets, core, bound_owner, bound_mesh, parent):
        calls.append((bound_owner, bound_mesh))
        return widgets.QDialog(parent)
    monkeypatch.setattr(mesh_compare_panel, 'make_dialog', create)
    window = module.compare_mesh_quality()
    assert calls == [(owner, mesh)] and window.isVisible() and window in module.KEEP
    window.close()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    app.processEvents()
    assert not module.KEEP
    foreign = NS(Name='Other', Document=NS(), TypeId='Fem::FemMeshGmsh')
    selection.append(foreign)
    with pytest.raises(ValueError, match='현재 메시 하나'):
        module.compare_mesh_quality()
    selection.clear()
    selection.append(NS(Name='Body', Document=document, TypeId='PartDesign::Body'))
    with pytest.raises(ValueError, match='현재 메시 하나'):
        module.compare_mesh_quality()
    selection.clear()
    document.Objects.append(NS(Name='Second', Document=document, TypeId='Fem::FemMeshGmsh'))
    with pytest.raises(ValueError, match='현재 메시 하나'):
        module.compare_mesh_quality()
    selection.append(mesh)
    reopened = module.compare_mesh_quality()
    assert calls == [(owner, mesh), (owner, mesh)]
    reopened.close()
    module.add_toolbar()
    action = main.findChild(QtGui.QAction, 'caeCompareMeshQuality')
    assert action is not None and action.text() == '메시 품질 비교…'
    action.trigger()
    assert calls == [(owner, mesh)] * 3
    main.close()
