"""Pure declared-input admission for the retained seven-body assembly.

Core/adapter must first verify the CAD/catalog/retained-mesh bytes. This module
checks their semantic join only, without files, native commands, auto supports,
contact pairing, solver eligibility or physical/engineering qualification.
"""

from copy import deepcopy
import math
import re

from .assembly_mesh import ACTIVE, INACTIVE, INACTIVE_REASON


_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,79}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_BASIS = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
_NATIVE_FRAME = "global_assembly_cartesian_mm"
_LIMITATIONS = (
    "Declared material sources remain USER_DECLARED_UNVERIFIED; actual material/process/strength is UNKNOWN.",
    "Partial declared constraints do not establish actual mounting, anchors, guides or rigid-body stability.",
    "Contact laws, master sides and bonded distances are user declarations; contact/load transfer is UNKNOWN.",
    "Eight original fasteners are omitted: " + INACTIVE_REASON,
    "Native node overlaps, master volumes and tie/contact syntax require adapter/worker verification.",
    "Retained coarse3 input does not establish mesh independence, physical validation, durability or release.",
)


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("An explicit safe declaration/selection ID is required")
    return value


def _text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise ValueError("A nonempty declared source is required")


def _object(value, required, optional=()):
    if (type(value) is not dict or not set(required) <= set(value)
            or not set(value) <= set(required) | set(optional)):
        raise ValueError("Declared semantic fields are missing or unsupported")


def _json(value, depth=0):
    if depth > 64:
        raise ValueError("Semantic snapshot is too deeply nested")
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("Semantic snapshot requires JSON string keys")
        for item in value.values():
            _json(item, depth + 1)
    elif type(value) is list:
        for item in value:
            _json(item, depth + 1)
    elif type(value) in (int, float):
        if not _finite(value):
            raise ValueError("Semantic snapshot requires finite JSON numbers")
    elif type(value) not in (str, bool, type(None)):
        raise ValueError("Semantic snapshot must contain JSON values only")


def _vector(value):
    if type(value) is not list or len(value) != 3 or any(not _finite(v) for v in value):
        raise ValueError("Three finite nonboolean global coordinates are required")


def _cartesian(value):
    _vector(value.get("origin"))
    basis = value.get("basis")
    if type(basis) is not list or len(basis) != 3:
        raise ValueError("Explicit global Cartesian basis is required")
    for row in basis:
        _vector(row)
    if value["origin"] != [0, 0, 0] or basis != _BASIS:
        raise ValueError("The retained assembly supports its recorded global origin/basis only")


def _geometry(selection):
    _vector(selection.get("center_mm"))
    bounds = selection.get("bounds_mm")
    _object(bounds, ("min_mm", "max_mm", "size_mm"))
    for key in bounds:
        _vector(bounds[key])
    if (any(a > b for a, b in zip(bounds["min_mm"], bounds["max_mm"]))
            or any(size < 0 for size in bounds["size_mm"])):
        raise ValueError("Native catalog bounds are invalid")


def _catalog(catalog):
    if (type(catalog) is not dict or catalog.get("cad_backend") != "fixture.assembly"
            or catalog.get("model") != "bending_assembly"
            or not isinstance(catalog.get("cad_revision"), str)
            or not _SHA.fullmatch(catalog["cad_revision"])
            or catalog.get("integrity", "VERIFIED") != "VERIFIED"):
        raise ValueError("A verified original bending-assembly CAD catalog is required")
    mesh = catalog.get("retained_mesh")
    if (type(mesh) is not dict or mesh.get("profile") != "coarse3"
            or mesh.get("cad_revision") != catalog["cad_revision"]
            or not isinstance(mesh.get("mesh_revision"), str) or not _SHA.fullmatch(mesh["mesh_revision"])
            or mesh.get("integrity", "VERIFIED") != "VERIFIED"
            or type(mesh.get("active_components")) is not list or len(mesh["active_components"]) != len(ACTIVE)
            or any(type(value) is not str for value in mesh["active_components"])
            or set(mesh["active_components"]) != set(ACTIVE)):
        raise ValueError("The same CAD revision's retained coarse3 seven-body mesh is required")
    frames = catalog.get("coordinate_systems")
    if type(frames) is not list or any(type(row) is not dict for row in frames):
        raise ValueError("An explicit global frame catalog is required")
    global_frames = [row for row in frames if row.get("id") == "global"]
    if (len(global_frames) != 1 or global_frames[0].get("unit") != "mm"
            or global_frames[0].get("type") != "cartesian"):
        raise ValueError("Exactly one millimetre global Cartesian frame is required")
    _cartesian(global_frames[0])
    mapping = catalog.get("native_frame_mapping")
    if (type(mapping) is not dict or mapping.get("source") != _NATIVE_FRAME or mapping.get("target") != "global"
            or mapping.get("sensor_world_alignment") != "UNKNOWN"):
        raise ValueError("The native/global frame mapping must be explicit; world alignment remains UNKNOWN")
    _cartesian(mapping)
    rows = catalog.get("selections")
    if type(rows) is not list:
        raise ValueError("Assembly body and native face selections are required")
    selections, bodies, native_faces, interior_faces = {}, {}, set(), []
    for row in rows:
        if type(row) is not dict:
            raise ValueError("Catalog selections must be objects")
        name, component = _id(row.get("id")), row.get("component_id")
        if (name in selections or component not in ACTIVE + INACTIVE
                or row.get("coordinate_system") != "global" or row.get("native_coordinate_system") != _NATIVE_FRAME
                or row.get("cad_revision", catalog["cad_revision"]) != catalog["cad_revision"]
                or type(row.get("roles")) is not list or any(type(role) is not str for role in row["roles"])):
            raise ValueError("Selection identity, component, CAD revision or frame differs")
        _geometry(row)
        if row.get("kind") == "native_assembly_body":
            if name != f"B-{component}" or component in bodies or "material" not in row["roles"]:
                raise ValueError("Native body selections must uniquely identify their material component")
            bodies[component] = row
        elif row.get("kind") in ("native_assembly_face", "assembly_face_interior_nodes"):
            interior = row["kind"] == "assembly_face_interior_nodes"
            ordinal = row.get("native_ordinal")
            native_id = row.get("catalog_face_id")
            if (type(ordinal) is not int or ordinal <= 0 or row.get("local_ordinal") != ordinal
                    or type(row.get("local_ordinal")) is not int
                    or name != f"{'I' if interior else 'S'}-{component}-{ordinal}"
                    or not isinstance(native_id, str)
                    or not re.fullmatch(re.escape(component) + rf":face:{ordinal}:[0-9a-f]{{64}}", native_id)
                    or (not interior and native_id in native_faces)
                    or not _finite(row.get("area_mm2")) or row["area_mm2"] <= 0):
                raise ValueError("Native face identity, ordinal, component or positive area differs")
            if interior:
                if (component not in ACTIVE or row.get("node_scope") != "FACE_INTERIOR_EXCLUDING_OTHER_FACE_BOUNDARIES"
                        or len(row["roles"]) != 2 or set(row["roles"]) != {"boundary", "load"}
                        or row.get("geometry_metadata_scope", "ORIGINAL_SOURCE_FACE_NOT_SUBSET") != "ORIGINAL_SOURCE_FACE_NOT_SUBSET"):
                    raise ValueError("Interior nodes require explicit active source-face scope and boundary/load roles only")
                interior_faces.append(row)
            else:
                native_faces.add(native_id)
        else:
            raise ValueError("Only native assembly body/face and explicit face-interior node selections are supported")
        selections[name] = row
    for row in interior_faces:
        face = selections.get(f"S-{row['component_id']}-{row['native_ordinal']}")
        metadata = ("component_id", "catalog_face_id", "native_ordinal", "local_ordinal", "bounds_mm", "center_mm",
                    "area_mm2", "coordinate_system", "native_coordinate_system", "native_geometry_sha256", "geom_type", "orientation")
        if (face is None or face["kind"] != "native_assembly_face"
                or any((key in row) != (key in face) or row.get(key) != face.get(key) for key in metadata)):
            raise ValueError("Interior nodes must reference their exact retained original native face and metadata")
    if not set(ACTIVE) <= set(bodies):
        raise ValueError("All seven active native body selections are required")
    return mesh, selections


def validate_declaration(catalog, declaration):
    """Return an independent exact semantic snapshot, never native syntax."""
    _json(catalog)
    _json(declaration)
    mesh, selections = _catalog(catalog)
    _object(declaration, ("analysis_type", "units", "coordinate_system", "materials", "boundary_conditions",
                          "loads", "contact", "mesh"))
    if (declaration["analysis_type"] != "nonlinear_static" or declaration["coordinate_system"] != "global"
            or declaration["units"] != {"length": "mm", "force": "N", "stress": "MPa"}):
        raise ValueError("Only declared nonlinear_static mm/N/MPa/global assembly mechanics is supported")
    _object(declaration["mesh"], ("mode", "mesh_revision"))
    if declaration["mesh"] != {"mode": "retained", "mesh_revision": mesh["mesh_revision"]}:
        raise ValueError("Declaration must explicitly select the catalog's retained mesh revision")

    def selected(identifier, role, kind):
        row = selections.get(_id(identifier))
        kinds = (kind,) if isinstance(kind, str) else kind
        if (row is None or row["component_id"] not in ACTIVE or row["kind"] not in kinds or role not in row["roles"]):
            raise ValueError("Condition must select a known active body/face with the declared role")
        return row

    assigned, nonzero_load, nonzero_displacement = set(), False, False
    for group in ("materials", "boundary_conditions", "loads"):
        entries = declaration[group]
        if type(entries) is not list or len(entries) > 64:
            raise ValueError("Declared conditions must be bounded arrays")
        identities = set()
        for item in entries:
            material = group == "materials"
            required = (("id", "selection_id", "law", "young_modulus_MPa", "poisson_ratio", "source") if material else
                        ("id", "selection_id", "type", "components", "unit", "coordinate_system", "source"))
            _object(item, required)
            identity = _id(item["id"])
            if identity in identities:
                raise ValueError("Condition IDs must be unique per kind")
            identities.add(identity)
            if material:
                row = selected(item["selection_id"], "material", "native_assembly_body")
                component = row["component_id"]
                if (component in assigned or item["law"] != "isotropic_linear_elastic"
                        or not _finite(item["young_modulus_MPa"]) or item["young_modulus_MPa"] <= 0
                        or not _finite(item["poisson_ratio"]) or not -1 < item["poisson_ratio"] < .5):
                    raise ValueError("Every active body needs exactly one finite isotropic E>0, -1<nu<0.5 material")
                _object(item["source"], ("category", "description"))
                if item["source"]["category"] not in ("ASSUMED", "MEASURED_REPORTED", "PUBLISHED_REFERENCE"):
                    raise ValueError("An explicit supported material source category is required")
                _text(item["source"]["description"])
                assigned.add(component)
            else:
                boundary = group == "boundary_conditions"
                selected(item["selection_id"], "boundary" if boundary else "load",
                         ("native_assembly_face", "assembly_face_interior_nodes"))
                _text(item["source"])
                components = item["components"]
                expected = {"UX", "UY", "UZ"} if boundary else {"FX", "FY", "FZ"}
                if (item["type"] != ("displacement" if boundary else "resultant_force")
                        or item["unit"] != ("mm" if boundary else "N") or item["coordinate_system"] != "global"
                        or type(components) is not dict or not components or not set(components) <= expected
                        or (not boundary and set(components) != expected)
                        or any(not _finite(value) for value in components.values())):
                    raise ValueError("Explicit finite partial displacement DOFs or complete signed force vectors are required")
                if boundary:
                    nonzero_displacement |= any(value != 0 for value in components.values())
                else:
                    if not any(value != 0 for value in components.values()):
                        raise ValueError("Each declared resultant load vector must be nonzero; omit loads for displacement control")
                    nonzero_load = True
    if assigned != set(ACTIVE):
        raise ValueError("No active body material may be omitted or substituted")
    if not (nonzero_load or nonzero_displacement):
        raise ValueError("An explicitly nonzero resultant load or prescribed displacement is required")

    contact = declaration["contact"]
    _object(contact, ("mode", "source"), ("pairs", "master_union_same_slave", "initial_state"))
    _text(contact["source"])
    mode, pairs = contact["mode"], contact.get("pairs", [])
    union = contact.get("master_union_same_slave", False)
    if type(union) is not bool or (union and mode not in ("frictionless", "mixed")):
        raise ValueError("Master union requires an explicit boolean and frictionless or mixed contact")
    if (mode not in ("none", "bonded", "frictionless", "mixed") or type(pairs) is not list or len(pairs) > 64
            or (mode == "none" and pairs) or (mode != "none" and not pairs)):
        raise ValueError("Contact mode must agree with explicitly declared pairs")
    if "initial_state" in contact and (contact["initial_state"] not in ("OPEN", "GEOMETRIC", "CLOSED_ASSUMED") or
            not any(pair.get("law", mode) == "frictionless" for pair in pairs)):
        raise ValueError("Initial contact state requires explicit frictionless pairs; closed contact is an unverified assumption")
    seen, slave_laws = set(), {}
    for pair in pairs:
        _object(pair, ("selection_a", "selection_b", "law", "master", "source"), ("distance_max_mm",))
        a = selected(pair["selection_a"], "contact", "native_assembly_face")
        b = selected(pair["selection_b"], "contact", "native_assembly_face")
        key = frozenset((pair["selection_a"], pair["selection_b"]))
        if a["component_id"] == b["component_id"] or len(key) != 2 or key in seen:
            raise ValueError("Each contact pair needs two distinct active faces on different bodies, without duplicates")
        seen.add(key)
        _text(pair["source"])
        if (pair["law"] not in ("bonded", "frictionless") or pair["master"] not in ("a", "b")
                or (mode != "mixed" and pair["law"] != mode)):
            raise ValueError("Each pair requires its explicit supported law and master side")
        if pair["law"] == "bonded":
            if not _finite(pair.get("distance_max_mm")) or pair["distance_max_mm"] <= 0:
                raise ValueError("Bonded pairs require an explicit positive finite distance_max_mm")
        elif "distance_max_mm" in pair:
            raise ValueError("Frictionless pairs must not declare a bonded search distance")
        slave = b if pair["master"] == "a" else a
        slave_laws.setdefault(slave["catalog_face_id"], []).append(pair["law"])
    if union and any(len(laws) > 1 and any(law != "frictionless" for law in laws)
                     for laws in slave_laws.values()):
        raise ValueError("Only declared frictionless pairs may share a slave in an opted-in master union")

    return {"catalog": deepcopy(catalog), "declaration": deepcopy(declaration),
            "cad_revision": catalog["cad_revision"], "mesh_revision": mesh["mesh_revision"],
            "active_components": deepcopy(mesh["active_components"]), "inactive_components": list(INACTIVE),
            "engineering": "UNKNOWN", "decision": "NOT_RELEASED", "scope": "USER_DECLARED_UNVERIFIED",
            "limitations": list(_LIMITATIONS)}


def require_initial_translation_support(catalog, declaration):
    """Refuse a provably free translation when every contact starts open.

    Bonded bodies move together. A declared displacement on one of those bodies
    prevents uniform translation in that component. Frictionless OPEN contact
    supplies no initial restraint. This narrow necessary check does not qualify
    rotational stability, geometric contact, preload or a closed assumption.
    """
    contact = declaration["contact"]
    if (any(pair.get("law", contact["mode"]) == "frictionless" for pair in contact.get("pairs", []))
            and contact.get("initial_state", "OPEN") != "OPEN"):
        return
    selections = {item["id"]: item for item in catalog["selections"]}
    parents = {component: component for component in catalog["retained_mesh"]["active_components"]}

    def root(component):
        while parents[component] != component:
            component = parents[component]
        return component

    for pair in contact.get("pairs", []):
        if pair.get("law", contact["mode"]) == "bonded":
            a, b = (selections[pair[key]]["component_id"] for key in ("selection_a", "selection_b"))
            parents[root(b)] = root(a)
    groups = {}
    for component in parents:
        groups.setdefault(root(component), {"bodies": [], "components": set()})["bodies"].append(component)
    for boundary in declaration["boundary_conditions"]:
        component = selections[boundary["selection_id"]]["component_id"]
        groups[root(component)]["components"].update(boundary["components"])
    missing = [f"{','.join(group['bodies'])}: {','.join(sorted({'UX', 'UY', 'UZ'} - group['components']))}"
               for group in groups.values() if group["components"] != {"UX", "UY", "UZ"}]
    if missing:
        raise ValueError("Initially OPEN contact cannot restrain free rigid translation; declare actual guides or an explicit initial contact state: "
                         + "; ".join(missing))
