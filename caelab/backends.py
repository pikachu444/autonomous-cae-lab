"""Lazy factories; discovery describes capability, never engineering approval."""
from collections.abc import MutableMapping
from dataclasses import dataclass
from importlib import import_module, metadata
from importlib.util import find_spec
from .contracts import CapabilityUnavailable

@dataclass(frozen=True)
class Backend:
    id: str
    roles: tuple[str, ...]
    factory: object
    optional_dependency: str | None = None
    native_runtime: str | None = None
    threads: int = 1

_registry = {}

def register_backend(identifier, factory, *, roles=("model",), optional_dependency=None,
                     native_runtime=None, threads=1, replace=False):
    if not isinstance(identifier, str) or not identifier or not roles:
        raise ValueError("Backend ID and roles are required")
    if identifier in _registry and not replace:
        raise ValueError(f"Backend already registered: {identifier}")
    if type(threads) is not int or threads < 1:
        raise ValueError('Backend thread reservation must be a positive integer')
    _registry[identifier] = Backend(identifier, tuple(roles), factory, optional_dependency, native_runtime,threads)

def _builtin(identifier, module, name, roles, dependency=None, native=None):
    threads=2 if identifier in {'explicit.openradioss','structural.code_aster',
        'structural.code_aster.plasticity','structural.code_aster.geometric_nonlinearity',
        'structural.families.code_aster'} else 1
    register_backend(identifier, f"caelab.{module}:{name}", roles=roles,
                     optional_dependency=dependency, native_runtime=native,threads=threads)

for _id, _module, _name, _roles, _dep, _native in (
    ("fixture.cadquery", "fixture_cadquery", "FixtureCadQueryAdapter", ("cad",), "cadquery", None),
    ("fixture.freecad", "fixture_freecad", "FixtureFreeCADAdapter", ("cad",), None, "FreeCAD"),
    ("fixture.assembly", "fixture_assembly_conditions_catalog", "AssemblyConditionsCADAdapter", ("cad",), None, None),
    ("fixture.calculix", "fixture_calculix", "FixtureCalculiXAdapter", ("analysis",), None, "Gmsh/CalculiX"),
    ("structure.calculix.native", "native_structural", "NativeStructuralAdapter", ("analysis",), "gmsh", "CalculiX/FreeCAD"),
    ("structural.code_aster", "codeaster_elasticity", "CodeAsterElasticityAdapter", ("model",), None, "Code_Aster"),
    ("structural.code_aster.plasticity", "codeaster_plasticity", "CodeAsterPlasticityAdapter", ("model",), None, "Code_Aster"),
    ("structural.code_aster.geometric_nonlinearity", "codeaster_geometric", "CodeAsterGeometricAdapter", ("model",), None, "Code_Aster"),
    ("structural.code_aster.contact_patch", "codeaster_contact", "CodeAsterContactPatchAdapter", ("model",), None, "Code_Aster"),
    ("structural.families.calculix", "structural_family_calculix", "StructuralFamilyCalculiXAdapter", ("model",), None, "Gmsh/CalculiX"),
    ("structural.families.code_aster", "structural_family_codeaster", "StructuralFamilyCodeAsterAdapter", ("model",), None, "Code_Aster"),
    ("material.mfront", "mfront_material", "MFrontMaterialAdapter", ("model",), None, "MFront/MGIS"),
    ("material.mfront.inverse", "mfront_inverse", "MFrontInverseAdapter", ("model",), None, "MFront/MGIS"),
    ("material.mfront.hyperelastic", "mfront_hyperelastic", "MFrontHyperelasticAdapter", ("model",), None, "MFront/MGIS"),
    ("material.mfront.viscoelastic", "mfront_viscoelastic", "MFrontViscoelasticAdapter", ("model",), None, "MFront/MGIS"),
    ("explicit.openradioss", "openradioss", "OpenRadiossAdapter", ("model",), None, "OpenRadioss"),
    ("material.felupe", "felupe_material", "FelupeMaterialAdapter", ("prepared",), "felupe", None),
    ("files.table", "file_table", "TableReaderAdapter", ("reader", "prepared"), "numpy", None),
):
    _builtin(_id, "adapters." + _module, _name, _roles, _dep, _native)
for _suffix, _class in (("", "FenicsxPDEAdapter"), (".nonlinear", "FenicsxNonlinearPDEAdapter"),
                        (".rectangle", "FenicsxRectanglePDEAdapter"), (".transient", "FenicsxTransientPDEAdapter"),
                        (".vector", "FenicsxVectorPDEAdapter"), (".coupled", "FenicsxCoupledPDEAdapter"),
                        (".imported", "FenicsxImportedPDEAdapter")):
    _builtin("pde.fenicsx" + _suffix, "adapters.fenicsx_" + (_suffix[1:] or "pde"), _class,
             ("pde", "model") if _suffix=='.coupled' else ("pde",), native="FEniCSx")
_builtin("scipy.latin_hypercube", "optimizers.scipy_lhs", "ScipyLatinHypercube", ("doe",), "scipy")
_builtin("scipy.differential_evolution", "optimizers.scipy_de", "ScipyDifferentialEvolution", ("optimizer",), "scipy")

def _extensions():
    return {entry.name: entry for entry in metadata.entry_points(group="caelab.backends")}

def list_backends(*, probe=False):
    rows = [{"id": item.id, "roles": list(item.roles), "optional_dependency": item.optional_dependency,
             "native_runtime": item.native_runtime, "threads": item.threads, "source": "registered"} for item in _registry.values()]
    rows.extend({"id": name, "roles": ["extension"], "optional_dependency": None,
                 "native_runtime": None, "source": "entry_point"}
                for name in _extensions() if name not in _registry)
    for row in rows:
        row["readiness"] = "NOT_PROBED"
        if probe:
            dep = row["optional_dependency"]
            row["python_dependency_available"] = dep is None or find_spec(dep) is not None
            row["readiness"] = "MISSING_DEPENDENCY" if not row["python_dependency_available"] else "EXECUTION_NOT_TESTED"
    return rows

def get_backend(identifier, *, store=None):
    if not isinstance(identifier, str):
        return identifier
    entry = _registry.get(identifier)
    try:
        if entry is None:
            extension = _extensions().get(identifier)
            if extension is None:
                raise CapabilityUnavailable(f"Unknown backend: {identifier}")
            factory = extension.load()
        else:
            factory = entry.factory
            if isinstance(factory, str):
                module, name = factory.split(":")
                factory = getattr(import_module(module), name)
        if identifier == "fixture.freecad":
            if store is None:
                raise CapabilityUnavailable("Native editable CAD requires an explicit model store")
            return factory(store)
        return factory()
    except ImportError as error:
        raise CapabilityUnavailable(f"{identifier}: missing optional dependency {error.name}") from error

class LazyAdapters(MutableMapping):
    """Lab-compatible mutable mapping; membership does not construct adapters."""
    def __init__(self, role, *, store=None):
        self.factories = {key: (lambda key=key: get_backend(key, store=store))
                          for key, item in _registry.items() if role in item.roles}
        self.cache = {}
    def __getitem__(self, key):
        if key not in self.cache:
            self.cache[key] = self.factories[key]()
        return self.cache[key]
    def __setitem__(self, key, value):
        self.factories[key] = lambda: value
        self.cache[key] = value
    def __delitem__(self, key):
        del self.factories[key]
        self.cache.pop(key, None)
    def __iter__(self):
        return iter(self.factories)
    def __len__(self):
        return len(self.factories)
    def __contains__(self, key):
        return key in self.factories


def reader_adapters(role):
    mapping = LazyAdapters('reader_internal')
    def add(identifier, module, name, *args):
        mapping.factories[identifier] = lambda: getattr(import_module('caelab.adapters.' + module), name)(*args)
    if role == 'field':
        add('fixture.assembly_mechanics.code_aster', 'assembly_response_fields', 'AssemblyResponseFieldsAdapter')
        for kind in ('rectangle', 'transient', 'vector', 'coupled', 'imported'):
            add('pde.fenicsx.' + kind, 'pde_response_fields', 'PDEResponseFieldsAdapter', 'pde.fenicsx.' + kind)
    else:
        add('explicit.openradioss', 'openradioss_history', 'OpenRadiossHistoryAdapter')
    add('structural.code_aster.plasticity', 'plasticity_response_fields', 'PlasticityResponseFieldsAdapter')
    return mapping
