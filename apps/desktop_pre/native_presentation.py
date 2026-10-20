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
        if view is None or not hasattr(view, 'Proxy') or view.Proxy is not None:
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
        restored.append(obj.Name)
    return restored
