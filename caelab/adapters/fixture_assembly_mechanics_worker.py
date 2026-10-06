"""Pinned same-mesh assembly mechanics worker; no affine/reference solve.

Only ``run_mechanics`` imports Code_Aster. Source IDs are bound to this import's
numeric indices before conditions, orientation and native model construction.
Native INST is a dimensionless load parameter, never an inferred physical time.
The observed fields establish neither physical qualification nor release.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import sys
from types import ModuleType

if __package__:
    from . import codeaster_worker as foundation
    from . import fixture_assembly_native_import_worker as importer
    from . import fixture_assembly_affine_field_worker as shared


_WORKER = "fixture_assembly_mechanics_worker.py"
_CAPSULE = (_WORKER, "codeaster_worker.py", "fixture_assembly_native_import_worker.py",
            "fixture_assembly_field_geometry.py", "assembly_mesh.py",
            "fixture_assembly_affine_field_worker.py")
_GROUP = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,23}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_POLICY = {"load_parameters": [0., .25, .5, .75, 1.], "residual_relative": 1e-6,
           "maximum_iterations": 50, "contact_coefficient": 1000.0}
_AXIS = "DIMENSIONLESS_STATIC_LOAD_PARAMETER_NOT_PHYSICAL_TIME"
_CONTACT_INITIAL_STATE = {"OPEN": "NON", "GEOMETRIC": "INTERPENETRE", "CLOSED_ASSUMED": "OUI"}
_TET_FACES = ((0, 1, 2, 4, 5, 6), (0, 1, 3, 4, 8, 7),
              (0, 2, 3, 6, 9, 7), (1, 2, 3, 5, 9, 8))


def _pin(data):
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def _object(value, keys, label, optional=()):
    if type(value) is not dict or not set(keys) <= set(value) or not set(value) <= set(keys) | set(optional):
        raise ValueError(label + " fields are missing or unsupported")


def _number(value, label):
    if type(value) not in (int, float):
        raise ValueError(label + " requires a finite nonboolean number")
    try:
        if not math.isfinite(value):
            raise ValueError(label + " requires a finite number")
    except OverflowError as error:
        raise ValueError(label + " is outside finite native range") from error
    return float(value)


def _indices(values, label, minimum=0):
    if (type(values) is not list or not values or
            any(type(i) is not int or i < minimum for i in values) or len(set(values)) != len(values)):
        raise ValueError(label + " requires unique exact numeric IDs")
    return values


def _name(value, label):
    if not isinstance(value, str) or not _GROUP.fullmatch(value):
        raise ValueError(label + " requires a bounded native group name")
    return value


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,79}", value):
        raise ValueError("Explicit bounded condition ID required")
    return value


def _list(value, label, maximum=64):
    if type(value) is not list or len(value) > maximum:
        raise ValueError(label + " must be a bounded list")
    return value


def _tria_permutations():
    edges = {frozenset((0, 1)): 3, frozenset((1, 2)): 4, frozenset((2, 0)): 5}
    return tuple(tuple(p) + tuple(edges[frozenset((p[a], p[b]))] for a, b in ((0, 1), (1, 2), (2, 0)))
                 for p in itertools.permutations(range(3)))


TRIA6_ORIENTATION_PERMUTATIONS = _tria_permutations()


def adjacent_volume_cells(catalog, face_group, volume_group):
    """Join an actual TRIA6 face to its unique owning TETRA10 face, by IDs."""
    cells = {cell["index"]: cell for cell in catalog["cells"]}
    volume = catalog["group_cell_indices"][volume_group]
    faces = {}
    for index in volume:
        cell = cells[index]
        if cell["type"] != "TETRA10":
            raise ValueError("Tie master must contain actual TETRA10 volume cells")
        for face in _TET_FACES:
            signature = frozenset(cell["node_indices"][i] for i in face)
            faces.setdefault(signature, []).append(index)
    selected = []
    for index in catalog["group_cell_indices"][face_group]:
        cell = cells[index]
        if cell["type"] != "TRIA6":
            raise ValueError("Tie master must select an actual TRIA6 face group")
        owners = faces.get(frozenset(cell["node_indices"]), [])
        if len(owners) != 1:
            raise ValueError("Declared master face lacks one exact adjacent TETRA10 owner")
        selected.extend(owners)
    if not selected:
        raise ValueError("Empty native tie master adjacency")
    return sorted(set(selected))


def validate_conditions(settings, mapping, catalog, components):
    """Independent native projection, not a replacement for Domain admission."""
    _object(settings, ("schema_version", "components", "materials", "boundary_conditions",
                       "loads", "ties", "contacts", "solver_policy"), "Mechanics settings")
    if (settings["schema_version"] != "1.0" or type(settings["components"]) is not list or
            settings["components"] != list(components) or len(set(components)) != 7):
        raise ValueError("Exact ordered seven-body component scope required")
    policy = settings["solver_policy"]
    _object(policy, _POLICY, "Native solver policy")
    parameters = policy["load_parameters"]
    if type(parameters) is not list or [_number(x, "load parameter") for x in parameters] != _POLICY["load_parameters"]:
        raise ValueError("Declared native load parameter list differs")
    if (type(policy["maximum_iterations"]) is not int or policy["maximum_iterations"] != 50 or
            _number(policy["residual_relative"], "relative residual") != 1e-6 or
            _number(policy["contact_coefficient"], "contact coefficient") != 1000.0):
        raise ValueError("Frozen convergence/contact policy differs")
    comparison = importer.validate_native_catalog(mapping, catalog)
    source, bodies, _ = shared.body_layout(mapping, catalog, components)
    source_nodes = comparison["source_node_ids_by_native_index"]
    original_names = set(catalog["group_names"]) | set(catalog["standalone_node_groups"])
    generated_nodes, generated_cells = {}, {}

    def group(name, dim):
        _name(name, "Original group")
        record = source["groups"].get(name)
        if record is None or record["dim"] != dim:
            raise ValueError("Declared group is absent or has the wrong native dimension")
        return record

    assigned = set()
    for item in _list(settings["materials"], "Materials", 7):
        _object(item, ("component_id", "volume_group", "young_modulus_MPa", "poisson_ratio"), "Material")
        component = item["component_id"]
        if (component not in components or component in assigned or
                item["volume_group"] != source["bodies"][component]):
            raise ValueError("Each native body needs exactly its own material volume")
        if (_number(item["young_modulus_MPa"], "Young modulus") <= 0 or
                not -1 < _number(item["poisson_ratio"], "Poisson ratio") < .5):
            raise ValueError("Finite E>0 and -1<nu<0.5 are required")
        assigned.add(component)
    if assigned != set(components):
        raise ValueError("Missing active native body material")

    constraints, force_dofs, receipts = {}, set(), {"boundary_conditions": [], "loads": [], "ties": [], "contacts": []}
    for kind, component_key, allowed in (("boundary_conditions", "components", {"DX", "DY", "DZ"}),
                                          ("loads", "components_N", {"FX", "FY", "FZ"})):
        identities = set()
        for item in _list(settings[kind], kind):
            _object(item, ("id", "node_group", "face_group", "source_node_ids", component_key), kind, ("node_scope",))
            identity = _id(item["id"])
            if identity in identities:
                raise ValueError("Duplicate native condition ID")
            identities.add(identity)
            face = group(item["face_group"], 2)
            name = _name(item["node_group"], "Generated node group")
            if name in original_names or name in generated_cells:
                raise ValueError("Generated group cannot overwrite original native membership")
            scope = item.get("node_scope", "WHOLE_FACE")
            selected_source = set(source["group_nodes"][item["face_group"]])
            if scope == "FACE_INTERIOR_EXCLUDING_OTHER_FACE_BOUNDARIES":
                others = [name for name, record in source["groups"].items()
                          if record["dim"] == 2 and record["component_id"] == face["component_id"]
                          and name != item["face_group"]]
                selected_source.difference_update(*(source["group_nodes"][name] for name in others))
            elif scope != "WHOLE_FACE":
                raise ValueError("Explicit supported native face node scope required")
            nodes = sorted(i for i in catalog["group_node_indices"][item["face_group"]]
                           if source_nodes[i] in selected_source)
            if not nodes:
                raise ValueError("Declared face node scope is empty; no automatic support repair")
            requested = _indices(item["source_node_ids"], "Selected original source nodes", 1)
            if (set(requested) != {source_nodes[i] for i in nodes} or
                    set(requested) != selected_source):
                raise ValueError("Declared source node IDs differ from the exact imported face")
            if not set(nodes) <= set(catalog["group_node_indices"][source["bodies"][face["component_id"]]]):
                raise ValueError("Selected native nodes escape their original body")
            if name in generated_nodes and generated_nodes[name] != nodes:
                raise ValueError("Generated node group reused for different original nodes")
            generated_nodes[name] = nodes
            values = item[component_key]
            if (type(values) is not dict or not values or not set(values) <= allowed or
                    (kind == "loads" and set(values) != allowed)):
                raise ValueError("Explicit supported partial native components required")
            for key, value in values.items():
                _number(value, "Declared native component")
                for node in nodes:
                    dof = (node, key[1])
                    if kind == "boundary_conditions":
                        if dof in constraints:
                            raise ValueError("Overlapping native boundary DOF declarations")
                        constraints[dof] = identity
                    elif value != 0:
                        force_dofs.add(dof)
            if kind == "loads" and not any(v != 0 for v in values.values()):
                raise ValueError("A declared resultant load must be nonzero")
            receipt = deepcopy(item)
            receipt.update({"component_id": face["component_id"], "node_indices": nodes,
                            "source_node_ids": [source_nodes[i] for i in nodes], "node_count": len(nodes), "node_scope": scope})
            if kind == "loads":
                per_node = {key: _number(value, "Resultant force") / len(nodes) for key, value in values.items()}
                if any(not math.isfinite(value) or (value == 0 and values[key] != 0) for key, value in per_node.items()):
                    raise ValueError("Equal-share force cannot be represented finitely")
                receipt.update({"distribution": "EQUAL_FORCE_PER_DECLARED_NATIVE_SURFACE_NODE",
                                "per_node_components_N": per_node,
                                "applied_resultant_components_N": {key: math.fsum([value] * len(nodes))
                                                                  for key, value in per_node.items()}})
            receipts[kind].append(receipt)
    if not receipts["loads"] and not any(value != 0 for row in receipts["boundary_conditions"] for value in row["components"].values()):
        raise ValueError("An explicit nonzero load or prescribed displacement is required")
    if force_dofs.intersection(constraints):
        raise ValueError("Nonzero load overlaps a declared constrained native DOF")

    slave_nodes, pairs, identities = set(), set(), set()
    for kind in ("ties", "contacts"):
        for number, item in enumerate(_list(settings[kind], kind), 1):
            union = kind == "contacts" and "master_face_groups" in item
            keys = (("id", "master_face_groups", "slave_face_group", "source_pair_ids") if union else
                    ("id", "master_face_group", "slave_face_group"))
            _object(item, keys + (("master_volume_group", "distance_max_mm") if kind == "ties" else ()), kind,
                    optional=("initial_state",) if kind == "contacts" else ())
            if kind == "contacts" and (not isinstance(item.get("initial_state", "OPEN"), str) or
                    item.get("initial_state", "OPEN") not in _CONTACT_INITIAL_STATE):
                raise ValueError("Explicit native contact initialization state is unsupported")
            identity = _id(item["id"])
            if identity in identities:
                raise ValueError("Duplicate native interface ID")
            identities.add(identity)
            master_names = item["master_face_groups"] if union else [item["master_face_group"]]
            if (type(master_names) is not list or not master_names or len(master_names) > 64 or
                    any(not isinstance(name, str) for name in master_names) or
                    len(set(master_names)) != len(master_names) or (union and len(master_names) < 2)):
                raise ValueError("Explicit distinct master face groups required")
            if union:
                pair_ids = item["source_pair_ids"]
                if (type(pair_ids) is not list or len(pair_ids) != len(master_names) or
                        len({_id(value) for value in pair_ids}) != len(pair_ids)):
                    raise ValueError("Explicit source pair IDs must preserve every declared master face")
            masters, slave = [group(name, 2) for name in master_names], group(item["slave_face_group"], 2)
            for name, master in zip(master_names, masters):
                pair = frozenset((name, item["slave_face_group"]))
                if master["component_id"] == slave["component_id"] or pair in pairs:
                    raise ValueError("Native interface must join distinct bodies without repeated face pairs")
                pairs.add(pair)
            nodes = sorted(catalog["group_node_indices"][item["slave_face_group"]])
            if slave_nodes.intersection(nodes):
                raise ValueError("Native slave faces intersect across contact/tie zones")
            slave_nodes.update(nodes)
            if any(node in nodes for node, _ in constraints):
                raise ValueError("Contact/bonded slave nodes collide with native boundary DOFs; no automatic exclusion")
            receipt = deepcopy(item)
            master = masters[0]
            receipt.update({"slave_component_id": slave["component_id"],
                "slave_node_indices": nodes, "slave_source_node_ids": [source_nodes[i] for i in nodes]})
            receipt["master_faces"] = [{"face_group": name, "component_id": record["component_id"],
                "cell_indices": sorted(catalog["group_cell_indices"][name]),
                "source_element_ids": [comparison["source_element_ids_by_native_index"][i]
                                       for i in sorted(catalog["group_cell_indices"][name])],
                "node_indices": sorted(catalog["group_node_indices"][name]),
                "source_node_ids": [source_nodes[i] for i in sorted(catalog["group_node_indices"][name])]}
                for name, record in zip(master_names, masters)]
            if not union:
                receipt["master_component_id"] = master["component_id"]
            if kind == "ties":
                if (item["master_volume_group"] != source["bodies"][master["component_id"]] or
                        _number(item["distance_max_mm"], "Bonded distance") <= 0):
                    raise ValueError("Explicit tie search distance and owning master volume required")
                adjacent = adjacent_volume_cells(catalog, item["master_face_group"], item["master_volume_group"])
                name = f"TM{number:03d}"
                if name in original_names or name in generated_nodes or name in generated_cells:
                    raise ValueError("Generated tie volume group would overwrite native membership")
                generated_cells[name] = adjacent
                receipt.update({"native_master_volume_group": name, "master_volume_cell_indices": adjacent,
                    "master_source_element_ids": [comparison["source_element_ids_by_native_index"][i] for i in adjacent],
                    "projection": "EXACT_TETRA10_FACE_ADJACENCY_OF_DECLARED_MASTER_TRIA6"})
            else:
                if union:
                    master_name = f"CM{number:03d}"
                    if master_name in original_names or master_name in generated_nodes or master_name in generated_cells:
                        raise ValueError("Generated contact master union would overwrite native membership")
                    merged = sorted({i for name in master_names for i in catalog["group_cell_indices"][name]})
                    generated_cells[master_name] = merged
                    receipt.update({"native_master_face_group": master_name, "master_cell_indices": merged,
                                    "projection": "EXPLICIT_DECLARED_MASTER_FACE_UNION_NO_MESH_MERGE"})
                else:
                    receipt["native_master_face_group"] = item["master_face_group"]
                name = f"CS{number:03d}"
                if name in original_names or name in generated_nodes or name in generated_cells:
                    raise ValueError("Generated contact observation group would overwrite native membership")
                generated_nodes[name] = nodes
                receipt["slave_node_group"] = name
            receipts[kind].append(receipt)
    return {"schema_version": 1, "scope": "CHECKED_CURRENT_NATIVE_IMPORT_CONDITIONS",
            "axis": _AXIS, "node_groups": generated_nodes, "cell_groups": generated_cells,
            **receipts, "engineering": "UNKNOWN", "decision": "NOT_RELEASED"}


def validate_orientation(before, after, node_groups=None, cell_groups=None):
    """Allow only six edge-preserving TRIA6 permutations plus explicit groups."""
    node_groups, cell_groups = node_groups or {}, cell_groups or {}
    keys = ("schema_version", "index_convention", "units", "node_count", "cell_count",
            "node_indices", "coordinates_mm", "labels")
    if any(before[key] != after[key] for key in keys):
        raise ValueError("Native orientation changed original indices, coordinates or labels")
    if (set(node_groups) & set(before["group_names"]) or set(cell_groups) & set(before["group_names"]) or
            set(node_groups) & set(cell_groups) or before["standalone_node_groups"]):
        raise ValueError("Native generated groups overwrite an original name")
    if (set(after["group_names"]) != set(before["group_names"]) | set(cell_groups) or
            len(after["group_names"]) != len(set(after["group_names"])) or
            set(after["group_cell_indices"]) != set(after["group_names"]) or
            set(after["group_node_indices"]) != set(after["group_names"]) or
            set(after["standalone_node_groups"]) != set(node_groups)):
        raise ValueError("Native orientation/group mutation changed the exact original group universe")
    original, oriented = ({c["index"]: c for c in value["cells"]} for value in (before, after))
    if len(oriented) != len(after["cells"]) or set(original) != set(oriented):
        raise ValueError("Native orientation changed cell coverage")
    changes = []
    for index, cell in original.items():
        observed = oriented[index]
        if cell["type"] != observed["type"] or set(observed) != set(cell):
            raise ValueError("Native orientation changed element type or metadata")
        a, b = cell["node_indices"], observed["node_indices"]
        if cell["type"] == "TETRA10":
            if a != b:
                raise ValueError("Native orientation altered ordered TETRA10 volume connectivity")
        elif cell["type"] == "TRIA6":
            allowed = [tuple(a[i] for i in p) for p in TRIA6_ORIENTATION_PERMUTATIONS]
            if tuple(b) not in allowed:
                raise ValueError("Native TRIA6 orientation violates corner/edge-preserving permutations")
            if a != b:
                changes.append({"native_cell_index": index, "before_node_indices": a,
                    "after_node_indices": b, "permutation": list(TRIA6_ORIENTATION_PERMUTATIONS[allowed.index(tuple(b))])})
        else:
            raise ValueError("Unsupported native orientation element")
    for name in before["group_names"]:
        for key in ("group_cell_indices", "group_node_indices"):
            if sorted(_indices(before[key][name], name)) != sorted(_indices(after[key][name], name)):
                raise ValueError("Native orientation changed original physical/body membership")
    for name, indices in cell_groups.items():
        if sorted(_indices(after["group_cell_indices"][name], name)) != indices:
            raise ValueError("Generated exact native cell group membership differs")
        expected_nodes = sorted({n for index in indices for n in original[index]["node_indices"]})
        if sorted(_indices(after["group_node_indices"][name], name)) != expected_nodes:
            raise ValueError("Generated exact native cell group node membership differs")
    for name, indices in node_groups.items():
        if sorted(_indices(after["standalone_node_groups"][name], name)) != indices:
            raise ValueError("Generated native node group differs from original selected nodes")
    return {"schema_version": 1, "status": "PASS", "basis": "MODI_MAILLAGE_ORIE_PEAU_ONLY",
            "allowed_tria6_permutations": [list(p) for p in TRIA6_ORIENTATION_PERMUTATIONS],
            "changed_surface_cells": changes, "original_volume_connectivity": "UNCHANGED",
            "original_xyz_and_physical_groups": "UNCHANGED", "engineering": "UNKNOWN"}


def result_orders(indexes, access, policy):
    """Bind actual saved order indices to the declared static load parameter."""
    orders = _indices(indexes, "Actual native orders")
    if type(access) is not dict or access.get("NUME_ORDRE") != orders:
        raise ValueError("Native access parameters do not bind actual saved orders")
    parameters = access.get("INST")
    if type(parameters) is not list or len(parameters) != len(orders):
        raise ValueError("Missing actual native load parameter access column")
    parameters = [_number(x, "Actual native INST/load parameter") for x in parameters]
    declared = policy["load_parameters"]
    if parameters not in (declared, declared[1:]) or len(orders) < 2:
        raise ValueError("Actual saved load parameters differ from requested increments")
    if orders[-1] <= 0 or parameters[-1] != 1.0:
        raise ValueError("Actual final native order at load parameter1.0 required")
    return orders[-1]


def validate_nodal_history(table, catalog, orders, label):
    required = ("NOEUD", "NUME_ORDRE", *foundation.COORDINATE_COMPONENTS, *foundation.VECTOR_COMPONENTS)
    table, count = foundation._table(table, required, label)
    seen, allowed = set(), set(orders)
    for row in range(count):
        order = table["NUME_ORDRE"][row]
        if type(order) is not int or order not in allowed:
            raise ValueError(label + " contains an unbound native order")
        node = foundation._table_identifier(table["NOEUD"][row], label + " NOEUD") - 1
        key = order, node
        if node >= catalog["node_count"] or key in seen:
            raise ValueError(label + " has duplicate/foreign native nodes")
        seen.add(key)
        point = [_number(table[axis][row], label + " coordinate") for axis in foundation.COORDINATE_COMPONENTS]
        if max(abs(a-b) for a, b in zip(point, catalog["coordinates_mm"][node])) > importer.COORDINATE_ABSOLUTE_MM:
            raise ValueError(label + " native coordinates differ from the checked import")
        for axis in foundation.VECTOR_COMPONENTS:
            _number(table[axis][row], label + " component")
    if seen != {(order, node) for order in orders for node in range(catalog["node_count"])}:
        raise ValueError(label + " does not cover every original native node/order")


def validate_contact_observation(table, catalog, orders, nodes, components, label):
    """A nullable channel is observed only with exact selected node/order rows.

    These are original native columns, not RF/area-derived pressures. Classic
    CONTINUE COT6T6 exposes LAGS_C at all six selected TRIA6 slave nodes.
    """
    table, count = foundation._table(table, ("NOEUD", "NUME_ORDRE", *components), label)
    expected = {(order, node) for order in orders for node in nodes}
    seen = set()
    for row in range(count):
        order = table["NUME_ORDRE"][row]
        if type(order) is not int or order not in orders:
            raise ValueError(label + " contains an unbound native order")
        node = foundation._table_identifier(table["NOEUD"][row], label + " NOEUD") - 1
        key = order, node
        if key not in expected or key in seen:
            raise ValueError(label + " has duplicate/foreign selected contact nodes")
        seen.add(key)
        for component in components:
            _number(table[component][row], label + " " + component)
        coordinates = foundation.COORDINATE_COMPONENTS
        if any(axis in table for axis in coordinates):
            if not all(axis in table for axis in coordinates):
                raise ValueError(label + " contains partial coordinate metadata")
            point = [_number(table[axis][row], label + " coordinate") for axis in coordinates]
            if max(abs(a-b) for a, b in zip(point, catalog["coordinates_mm"][node])) > importer.COORDINATE_ABSOLUTE_MM:
                raise ValueError(label + " native coordinates differ from the selected original nodes")
    if seen != expected:
        raise ValueError(label + " is incomplete over actual selected slave nodes/orders")


def _pins(pins):
    if type(pins) is not dict or set(pins) != set(_CAPSULE):
        raise ValueError("Exact native source capsule membership required")
    for name, pin in pins.items():
        _object(pin, ("sha256", "size_bytes"), "Source pin")
        if (not isinstance(pin["sha256"], str) or not _SHA.fullmatch(pin["sha256"]) or
                type(pin["size_bytes"]) is not int or pin["size_bytes"] <= 0):
            raise ValueError("Malformed exact native source pin: " + name)


def _capsule_modules(capsule, pins):
    """Execute captured exact-membership sources in one private namespace."""
    _pins(pins)
    capsule = Path(capsule)
    package_name = "_assembly_mechanics_capsule"
    if any(name == package_name or name.startswith(package_name + ".") for name in sys.modules):
        raise RuntimeError("Unowned preloaded mechanics capsule namespace")

    def capture():
        captured = {}
        if capsule.is_symlink() or set(p.name for p in capsule.iterdir()) != set(_CAPSULE):
            raise RuntimeError("Native capsule directory membership differs")
        for name in _CAPSULE:
            path = capsule / name
            if path.is_symlink():
                raise RuntimeError("Native capsule source alias forbidden")
            data = path.read_bytes()
            if _pin(data) != pins[name]:
                raise RuntimeError("Native capsule source byte drift: " + name)
            captured[name] = data
        return captured

    captured = capture()
    package = ModuleType(package_name)
    package.__path__ = [str(capsule)]
    sys.modules[package_name] = package
    loaded = {}
    try:
        order = ("codeaster_worker.py", "fixture_assembly_native_import_worker.py",
                 "fixture_assembly_field_geometry.py", "assembly_mesh.py",
                 "fixture_assembly_affine_field_worker.py", _WORKER)
        for filename in order:
            fullname = package_name + "." + filename[:-3]
            module = ModuleType(fullname)
            module.__file__, module.__package__ = str(capsule / filename), package_name
            sys.modules[fullname] = module
            setattr(package, filename[:-3], module)
            exec(compile(captured[filename], module.__file__, "exec", dont_inherit=True), module.__dict__)
            loaded[filename] = module
        if capture() != captured:
            raise RuntimeError("Native source capsule drift during code load")
    except Exception:
        for name in list(sys.modules):
            if name == package_name or name.startswith(package_name + "."):
                del sys.modules[name]
        raise
    return loaded


def bootstrap(input_path):
    input_file = Path(input_path)
    data = input_file.read_bytes()
    config = json.loads(data)
    modules = _capsule_modules(input_file.parent.parent / "capsule", config["native_sources"])
    if input_file.read_bytes() != data:
        raise RuntimeError("Native input changed during source capsule load")
    return modules[_WORKER].run_mechanics(input_path, modules)


def run_mechanics(input_path, modules):
    """Import once, validate identity/conditions, then observe real mechanics."""
    from code_aster.Commands import (
        AFFE_CHAR_MECA, AFFE_MATERIAU, AFFE_MODELE, CALC_CHAM_ELEM, CALC_CHAMP,
        CREA_TABLE, DEBUT, DEFI_CONTACT, DEFI_FONCTION, DEFI_LIST_REEL,
        DEFI_MATERIAU, FIN, IMPR_RESU, LIRE_MAILLAGE, MODI_MAILLAGE, POST_ELEM, STAT_NON_LINE,
    )
    from code_aster.Cata.Syntax import _F

    input_file = Path(input_path)
    input_bytes = input_file.read_bytes()
    config = json.loads(input_bytes)
    output, capsule, captured = input_file.parent, input_file.parent.parent / "capsule", input_file.parent.parent / "mesh-reuse"

    def save(name, value):
        data = json.dumps(foundation._json_safe(value), sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode("utf-8") + b"\n"
        with (output / name).open("xb") as stream:
            stream.write(data)
        return _pin(data)

    def read_checked(path, pin):
        data = path.read_bytes()
        if _pin(data) != pin:
            raise RuntimeError("Captured native input/source byte drift: " + path.name)
        return data

    def guard_sources(*, check_unit=True):
        _pins(config["native_sources"])
        if input_file.is_symlink() or input_file.read_bytes() != input_bytes:
            raise RuntimeError("Native input byte drift or alias")
        if set(modules) != set(_CAPSULE) or set(p.name for p in capsule.iterdir()) != set(_CAPSULE):
            raise RuntimeError("Loaded native capsule membership differs")
        for name in _CAPSULE:
            path = capsule / name
            if path.is_symlink():
                raise RuntimeError("Native source alias forbidden")
            read_checked(path, config["native_sources"][name])
            loaded_path = Path(modules[name].__file__)
            if loaded_path.is_symlink():
                raise RuntimeError("Loaded native source alias forbidden")
            read_checked(loaded_path, config["native_sources"][name])
        # run_aster links the export's logical unit during DEBUT. Before that,
        # verify the frozen transport input; afterwards verify both actual paths.
        transport_input = output / "mesh-transport.msh"
        if transport_input.is_symlink():
            raise RuntimeError("Native transport input alias forbidden")
        read_checked(transport_input, config["transport_entry"])
        if check_unit:
            read_checked(Path("fort.20"), config["transport_entry"])
        for name, key in (("mapping.json", "mapping_entry"), ("quality.json", "quality_entry")):
            path = captured / name
            if path.is_symlink():
                raise RuntimeError("Captured qualified source alias forbidden")
            read_checked(path, config[key])
        if "original_mesh_entry" in config:
            read_checked(captured / "mesh.msh", config["original_mesh_entry"])

    phase = "SOURCE_GUARD"
    try:
        _object(config, ("schema_version", "mesh_revision", "parent", "profile", "mapping_entry", "quality_entry",
                         "transport_entry", "native_sources", "settings"), "Native input", ("original_mesh_entry",))
        if type(config["schema_version"]) is not int or config["schema_version"] != 1:
            raise ValueError("Native input schema1 required")
        guard_sources(check_unit=False)
        if (not isinstance(config["mesh_revision"], str) or not _SHA.fullmatch(config["mesh_revision"]) or
                type(config["parent"]) is not dict or not config["parent"] or
                type(config["profile"]) is not dict or config["profile"].get("name") != "coarse3" or
                _number(config["profile"].get("mesh_size_mm"), "Profile mesh size") != 3.0):
            raise ValueError("Captured original parent/revision/coarse3 identity required")
        mapping = json.loads(read_checked(captured / "mapping.json", config["mapping_entry"]))
        quality = json.loads(read_checked(captured / "quality.json", config["quality_entry"]))
        components = list(modules["assembly_mesh.py"].ACTIVE)
        shared.qualified_volumes(quality, components)
        if _number(mapping.get("mesh_size_mm"), "Original mesh size") != 3.0:
            raise ValueError("Original qualified mapping is not coarse3")
        phase = "BEFORE_DEBUT"
        DEBUT()
        guard_sources()
        versions, runtime = foundation._runtime_versions()
        before = {"versions": versions, "code_aster_runtime": runtime}
        save("runtime-before.json", before)
        if versions.get("code_aster") != "17.4.0":
            raise RuntimeError("Actual native Code_Aster17.4.0 required")
        phase = "IMPORT"
        mesh = LIRE_MAILLAGE(FORMAT="GMSH", UNITE=20)
        pre = importer.capture_native_catalog(mesh)
        pre_pin = save("native-catalog.json", pre)
        phase = "PRE_MODEL_IDENTITY"
        comparison = importer.validate_native_catalog(mapping, pre)
        comparison_pin = save("pre-meca-import-comparison.json", comparison)
        projection = validate_conditions(config["settings"], mapping, pre, components)
        source, _, _ = shared.body_layout(mapping, pre, components)
        volumes = [source["bodies"][component] for component in components]
        settings = config["settings"]
        phase = "ORIENTATION"
        orientation_commands = [{"GROUP_MA_PEAU": name,
                                 "GROUP_MA_INTERNE": source["bodies"][record["component_id"]]}
                                for name, record in sorted(source["groups"].items()) if record["dim"] == 2]
        modified = MODI_MAILLAGE(reuse=mesh, MAILLAGE=mesh,
                                ORIE_PEAU=tuple(_F(**command) for command in orientation_commands))
        if modified is not mesh:
            raise RuntimeError("ORIE_PEAU replaced the identity-checked native Mesh")
        oriented = importer.capture_native_catalog(mesh)
        orientation = validate_orientation(pre, oriented)
        phase = "GENERATED_GROUPS"
        for name, indices in projection["node_groups"].items():
            if name in mesh.getGroupsOfCells() or name in mesh.getGroupsOfNodes():
                raise RuntimeError("Generated native node group already exists")
            mesh.setGroupOfNodes(name, indices)
        for name, indices in projection["cell_groups"].items():
            if name in mesh.getGroupsOfCells() or name in mesh.getGroupsOfNodes():
                raise RuntimeError("Generated tie master name already exists")
            mesh.setGroupOfCells(name, indices)
        actual = importer.capture_native_catalog(mesh)
        orientation = validate_orientation(pre, actual, projection["node_groups"], projection["cell_groups"])
        oriented_pin = save("oriented-catalog.json", actual)
        orientation_pin = save("orientation-receipt.json", orientation)
        orientation_commands_pin = save("orientation-commands.json", {
            "command": "MODI_MAILLAGE", "reuse_checked_mesh": True, "ORIE_PEAU": orientation_commands,
            "pre_catalog_entry": pre_pin, "oriented_catalog_entry": oriented_pin})
        application_pin = save("nodal-application-receipt.json", projection)
        guard_sources()
        phase = "MODEL"
        model = AFFE_MODELE(MAILLAGE=mesh, AFFE=_F(GROUP_MA=volumes, PHENOMENE="MECANIQUE", MODELISATION="3D"))
        material_assignments = []
        for record in settings["materials"]:
            material = DEFI_MATERIAU(ELAS=_F(E=record["young_modulus_MPa"], NU=record["poisson_ratio"]))
            material_assignments.append(_F(GROUP_MA=record["volume_group"], MATER=material))
        materials = AFFE_MATERIAU(MAILLAGE=mesh, AFFE=tuple(material_assignments))
        constant_bcs, driven_bcs = [], []
        for record in projection["boundary_conditions"]:
            for values, destination in (({k: v for k, v in record["components"].items() if v == 0}, constant_bcs),
                                        ({k: v for k, v in record["components"].items() if v != 0}, driven_bcs)):
                if values:
                    destination.append(_F(GROUP_NO=record["node_group"], **values))
        tied = [_F(GROUP_MA_MAIT=r["native_master_volume_group"], GROUP_MA_ESCL=r["slave_face_group"],
                   TYPE_RACCORD="MASSIF", DDL=("DX", "DY", "DZ"), ELIM_MULT="OUI", DISTANCE_MAX=r["distance_max_mm"])
                for r in projection["ties"]]
        excitations = []
        constant = {}
        if constant_bcs:
            constant["DDL_IMPO"] = tuple(constant_bcs)
        if tied:
            constant["LIAISON_MAIL"] = tuple(tied)
        if constant:
            excitations.append(_F(CHARGE=AFFE_CHAR_MECA(MODELE=model, **constant)))
        ramp = DEFI_FONCTION(NOM_PARA="INST", VALE=(0., 0., 1., 1.))
        if driven_bcs:
            excitations.append(_F(CHARGE=AFFE_CHAR_MECA(MODELE=model, DDL_IMPO=tuple(driven_bcs)), FONC_MULT=ramp))
        if projection["loads"]:
            forces = [_F(GROUP_NO=r["node_group"], **r["per_node_components_N"]) for r in projection["loads"]]
            excitations.append(_F(CHARGE=AFFE_CHAR_MECA(MODELE=model, FORCE_NODALE=tuple(forces)), FONC_MULT=ramp))
        contact = None
        if projection["contacts"]:
            contact = DEFI_CONTACT(MODELE=model, FORMULATION="CONTINUE", FROTTEMENT="SANS", VERI_NORM="OUI",
                ZONE=tuple(_F(GROUP_MA_MAIT=r["native_master_face_group"], GROUP_MA_ESCL=r["slave_face_group"],
                              VECT_MAIT="AUTO", VECT_ESCL="AUTO", CONTACT_INIT=_CONTACT_INITIAL_STATE[r.get("initial_state", "OPEN")],
                              INTEGRATION="AUTO", ALGO_CONT="STANDARD",
                              COEF_CONT=settings["solver_policy"]["contact_coefficient"]) for r in projection["contacts"]))
        increments = DEFI_LIST_REEL(VALE=tuple(settings["solver_policy"]["load_parameters"]))
        guard_sources()
        validate_orientation(pre, importer.capture_native_catalog(mesh), projection["node_groups"], projection["cell_groups"])
        phase = "STAT_NON_LINE"
        keywords = {"CONTACT": contact} if contact is not None else {}
        result = STAT_NON_LINE(MODELE=model, CHAM_MATER=materials, INCREMENT=_F(LIST_INST=increments),
            EXCIT=tuple(excitations), COMPORTEMENT=_F(GROUP_MA=volumes, RELATION="ELAS", DEFORMATION="PETIT"),
            CONVERGENCE=_F(ARRET="OUI", RESI_GLOB_RELA=settings["solver_policy"]["residual_relative"],
                           ITER_GLOB_MAXI=settings["solver_policy"]["maximum_iterations"]),
            SOLVEUR=_F(METHODE="MUMPS", STOP_SINGULIER="OUI"), **keywords)
        result = CALC_CHAMP(reuse=result, RESULTAT=result, FORCE="REAC_NODA")
        orders = foundation._json_safe(list(result.getIndexes()))
        access = foundation._json_safe(result.getAccessParameters())
        order = result_orders(orders, access, settings["solver_policy"])
        access_pin = save("native-access-parameters.json", {"available_orders": orders, "access_parameters": access,
                                                           "axis": _AXIS, "order": order, "load_parameter": 1.0})
        phase = "FIELDS"
        tables, entries, histories, history_entries = {}, {}, {}, {}
        for field, selected_components in (("DEPL", foundation.VECTOR_COMPONENTS),
                                            ("REAC_NODA", foundation.VECTOR_COMPONENTS),
                                            ("SIEF_ELGA", foundation.STRESS_COMPONENTS)):
            selection = {"GROUP_MA": volumes} if field == "SIEF_ELGA" else {"TOUT": "OUI"}
            table = CREA_TABLE(RESU=_F(RESULTAT=result, NOM_CHAM=field, NUME_ORDRE=order,
                                      NOM_CMP=selected_components, **selection)).EXTR_TABLE().values()
            tables[field] = foundation._json_safe(table)
            entries[field] = save(field.lower() + ".table.json", tables[field])
            if field != "SIEF_ELGA":
                table = CREA_TABLE(RESU=_F(RESULTAT=result, NOM_CHAM=field, NUME_ORDRE=tuple(orders),
                                          NOM_CMP=selected_components, TOUT="OUI")).EXTR_TABLE().values()
                histories[field] = foundation._json_safe(table)
                history_entries[field] = save(field.lower() + "-all-orders.table.json", histories[field])
                validate_nodal_history(tables[field], pre, [order], field)
                validate_nodal_history(histories[field], pre, orders, field + " history")
        geometry = CALC_CHAM_ELEM(MODELE=model, GROUP_MA=volumes, OPTION="COOR_ELGA")
        tables["COOR_ELGA"] = foundation._json_safe(CREA_TABLE(RESU=_F(CHAM_GD=geometry, GROUP_MA=volumes,
            NOM_CMP=("X", "Y", "Z", "W"))).EXTR_TABLE().values())
        entries["COOR_ELGA"] = save("coor_elga.table.json", tables["COOR_ELGA"])
        complete = shared.parse_complete_fields({"order": order, "identity_verified_before_model": True,
            "tables": tables, "geometry_context": {
                "basis": "CHAM_GD from CALC_CHAM_ELEM on the same imported model",
                "result_order_binding": "DERIVED_COMMAND_CONTEXT_NOT_NATIVE_GEOMETRY_ORDER",
                "selected_result_order": order, "volume_groups": volumes}},
            mapping, pre, quality, components, 1e-8)
        completeness = {"scope": "COMPLETE_NATIVE_FIELDS", "geometry_checks": complete["geometry_checks"],
            "per_body_counts": {component: {"nodes": len(body["nodes"]), "gauss_locations": len(body["gauss"])}
                                for component, body in complete["bodies"].items()}}
        native_contact, contact_entries = {}, {}
        for number, record in enumerate(projection["contacts"], 1):
            observations = {}
            for channel, field, selected_components in (("DEPL.LAGS_C", "DEPL", ("LAGS_C",)),
                    ("CONT_NOEU", "CONT_NOEU", ("CONT", "JEU", "RNX", "RNY", "RNZ", "PROJ_X", "PROJ_Y", "PROJ_Z"))):
                selection = {"NOM_CHAM": field, "NUME_ORDRE": orders, "GROUP_NO": record["slave_node_group"]}
                selection["NOM_CMP"] = list(selected_components)
                try:
                    table = CREA_TABLE(RESU=_F(RESULTAT=result, **selection)).EXTR_TABLE().values()
                    observation = {"status": "OBSERVED", "selection": selection, "table": foundation._json_safe(table)}
                    try:
                        validate_contact_observation(observation["table"], pre, orders, record["slave_node_indices"],
                                                     selected_components, channel)
                    except (ValueError, KeyError, TypeError, OverflowError) as error:
                        observation.update(status="UNKNOWN", reason=type(error).__name__ + ": " + str(error))
                except Exception as error:
                    observation = {"status": "UNKNOWN", "selection": selection, "table": None,
                                   "reason": type(error).__name__ + ": " + str(error)}
                observation.update({"axis": _AXIS, "pressure_from_reaction_or_area": "NOT_CONSTRUCTED"})
                observation["native_component_units"] = ({"LAGS_C": "MPa"} if channel == "DEPL.LAGS_C" else
                    {"CONT": "dimensionless", "JEU": "mm", "RNX": "N", "RNY": "N", "RNZ": "N",
                     "PROJ_X": "mm", "PROJ_Y": "mm", "PROJ_Z": "mm"})
                observation["unit_basis"] = "DECLARED_MM_N_MPA_MODEL_AND_NATIVE_CHANNEL_SEMANTICS"
                key = f"contact-{number:03d}-" + ("lags_c" if channel == "DEPL.LAGS_C" else "cont_noeu") + ".table.json"
                entry = save(key, observation)
                observations[channel] = observation
                contact_entries[key] = entry
            native_contact[record["id"]] = observations
        energy, energy_entries = {}, {}
        for component, group in zip(components, volumes):
            selection = {"GROUP_MA": group, "NUME_ORDRE": order, "option": "ENER_POT"}
            try:
                table = POST_ELEM(RESULTAT=result, NUME_ORDRE=order, ENER_POT=_F(GROUP_MA=group)).EXTR_TABLE().values()
                observation = {"status": "OBSERVED", "selection": selection, "table": foundation._json_safe(table)}
                try:
                    energy_table, count = foundation._table(observation["table"], ("TOTALE", "NUME_ORDRE", "LIEU"), "ENER_POT")
                    if count != 1 or foundation._name(energy_table["LIEU"][0], "energy LIEU") != group:
                        raise ValueError("Native body energy selection is absent or differs")
                    foundation._field_order(energy_table, 0, order, "ENER_POT")
                    _number(energy_table["TOTALE"][0], "Native body energy")
                except (ValueError, KeyError, TypeError, OverflowError) as error:
                    observation.update(status="UNKNOWN", reason=type(error).__name__ + ": " + str(error))
            except Exception as error:
                observation = {"status": "UNKNOWN", "selection": selection, "table": None,
                               "reason": type(error).__name__ + ": " + str(error)}
            energy[component] = observation
            energy_entries[component] = save("energy-" + component + ".table.json", observation)
        guard_sources()
        validate_orientation(pre, importer.capture_native_catalog(mesh), projection["node_groups"], projection["cell_groups"])
        phase = "EXPORT"
        IMPR_RESU(FORMAT="MED", UNITE=80, RESU=(
            _F(RESULTAT=result, NOM_CHAM=("DEPL", "SIEF_ELGA", "REAC_NODA"), NUME_ORDRE=order),
            _F(CHAM_GD=geometry, NOM_CHAM_MED="COOR_ELGA_RAW")))
        versions_after, runtime_after = foundation._runtime_versions()
        after = {"versions": versions_after, "code_aster_runtime": runtime_after}
        save("runtime-after.json", after)
        if before != after:
            raise RuntimeError("Actual native runtime drift during assembly mechanics")
        guard_sources()
        validate_orientation(pre, importer.capture_native_catalog(mesh), projection["node_groups"], projection["cell_groups"])
        raw = {"schema_version": 1, "status": "ASSEMBLY_MECHANICS_NATIVE_OBSERVED", "input_entry": _pin(input_bytes),
            "native_sources": config["native_sources"], "transport_entry": config["transport_entry"],
            "mapping_entry": config["mapping_entry"], "quality_entry": config["quality_entry"],
            "mesh_revision": config["mesh_revision"], "parent": config["parent"], "profile": config["profile"],
            "pre_catalog_entry": pre_pin, "catalog_entry": pre_pin, "pre_comparison_entry": comparison_pin,
            "oriented_catalog_entry": oriented_pin, "orientation_receipt_entry": orientation_pin,
            "orientation_receipt": orientation, "orientation_commands": orientation_commands,
            "orientation_commands_entry": orientation_commands_pin, "nodal_application_receipt_entry": application_pin,
            "nodal_application_receipt": projection, "runtime_before": before, "runtime_after": after,
            "identity_verified_before_model": True, "order": order, "load_parameter": 1.0, "axis": _AXIS,
            "available_orders": orders, "access_parameters": access, "access_parameters_entry": access_pin,
            "settings": settings, "table_entries": entries, "tables": tables,
            "field_completeness": completeness,
            "history_tables": histories, "history_table_entries": history_entries,
            "native_contact": native_contact, "contact_table_entries": contact_entries,
            "native_energy": energy, "energy_table_entries": energy_entries,
            "geometry_context": {"basis": "CHAM_GD from CALC_CHAM_ELEM on the same imported model",
                "result_order_binding": "DERIVED_COMMAND_CONTEXT_NOT_NATIVE_GEOMETRY_ORDER",
                "selected_result_order": order, "volume_groups": volumes},
            "solver_status": "COMPLETED", "converged": True, "engineering": "UNKNOWN", "decision": "NOT_RELEASED",
            "convergence_evidence": "STAT_NON_LINE returned under declared ARRET OUI/RESI_GLOB_RELA; native .mess is retained separately",
            "linear_residual": {"value": None, "status": "UNKNOWN", "reason": "No assembled A/u/b exported"}}
        if "original_mesh_entry" in config:
            raw["original_mesh_entry"] = config["original_mesh_entry"]
        save("worker-result.json", raw)
        phase = "FIN"
        FIN()
        return raw
    except Exception as error:
        save("native-failure.json", {"phase": phase, "error": type(error).__name__ + ": " + str(error),
                                    "numerical_verdict": "UNKNOWN", "decision": "NOT_RELEASED"})
        raise
