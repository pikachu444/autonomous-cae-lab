"""Restore absent GUI proxies using FreeCAD's own FEM ViewProviders."""
from importlib import import_module


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
