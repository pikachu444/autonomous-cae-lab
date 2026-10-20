"""Restore absent GUI proxies using FreeCAD's own FEM ViewProviders."""
from importlib import import_module
from pathlib import Path


_PROVIDERS = {
    ('solver_ccxtools', 'SolverCcxTools'): 'VPSolverCcxTools',
    ('material_common', 'MaterialCommon'): 'VPMaterialCommon',
    ('material_mechanicalnonlinear', 'MaterialMechanicalNonlinear'): 'VPMaterialMechanicalNonlinear',
    ('mesh_gmsh', 'MeshGmsh'): 'VPMeshGmsh',
    ('constraint_selfweight', 'ConstraintSelfWeight'): 'VPConstraintSelfWeight',
    ('element_geometry2D', 'ElementGeometry2D'): 'VPElementGeometry2D',
}


def restore_fem_viewproviders(doc):
    """Headless FCStd has App proxies but no GuiDocument; never recreate App objects."""
    restored = []
    for obj in doc.Objects:
        view = getattr(obj, 'ViewObject', None)
        if view is None or not hasattr(view, 'Proxy'):
            continue
        proxy = view.Proxy
        # FreeCAD 1.1 initializes missing Python presentation with the integer 1.
        if proxy is not None and not (type(proxy) is int and proxy == 1):
            continue
        cls = type(getattr(obj, 'Proxy', None))
        package, _, module = cls.__module__.rpartition('.')
        provider = _PROVIDERS.get((module, cls.__name__)) if package == 'femobjects' else None
        if provider is None:
            continue
        # An inherited/custom proxy must keep its own presentation contract.
        if getattr(import_module(cls.__module__), cls.__name__, None) is not cls:
            continue
        native_view = import_module('femviewprovider.view_' + module)
        getattr(native_view, provider)(view)
        # The integer placeholder already attached the C++ provider; replacing
        # it does not repeat the Python attach callback in FreeCAD 1.1.
        if getattr(view.Proxy, 'Object', None) is not obj:
            view.Proxy.attach(view)
        restored.append(obj.Name)
    return restored


def install_restore_observer(App, Gui, QtCore, QtWidgets):
    """Follow native File Open/recent files with the same presentation repair."""
    main = Gui.getMainWindow()
    existing = getattr(main, '_caelab_fem_presentation_observer', None)
    if existing is not None:
        return existing

    class Observer:
        def __init__(self):
            self.pending = {}
            self.completed = {}
            self.closed = False

        def slotActivateDocument(self, doc):
            if (self.closed or self.pending.get(doc.Name) is doc
                    or self.completed.get(doc.Name) is doc):
                return
            self.pending[doc.Name] = doc
            QtCore.QTimer.singleShot(0, lambda: self.restore(doc))

        def restore(self, doc):
            if self.pending.get(doc.Name) is not doc:
                return
            self.pending.pop(doc.Name, None)
            if (self.closed or App.listDocuments().get(doc.Name) is not doc or doc.Restoring
                    or Path(doc.FileName).suffix.lower() != '.fcstd'):
                return
            try:
                restore_fem_viewproviders(doc)
                self.completed[doc.Name] = doc
            except Exception as error:
                App.Console.PrintError(f'{doc.Label}: FEM 편집 화면을 복원하지 못했습니다. '
                                       f'보고서 보기에서 설치된 FreeCAD 모듈을 확인하세요. {error}\n')

        def slotDeletedDocument(self, doc):
            if self.pending.get(doc.Name) is doc:
                self.pending.pop(doc.Name, None)
            if self.completed.get(doc.Name) is doc:
                self.completed.pop(doc.Name, None)

        def close(self):
            if not self.closed:
                self.closed = True
                self.pending.clear()
                self.completed.clear()
                App.removeDocumentObserver(self)

    observer = Observer()
    App.addDocumentObserver(observer)
    main._caelab_fem_presentation_observer = observer
    QtWidgets.QApplication.instance().aboutToQuit.connect(observer.close)
    return observer
