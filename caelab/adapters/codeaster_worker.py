"""Pinned Code_Aster 17.4 command worker and strict native-table parser.

The parser imports only the standard library. Code_Aster and its numerical
libraries are imported only by solve_level inside the isolated vendor image.
Raw table columns, node/element names and every integration point are retained.
"""

from __future__ import annotations

import hashlib
import importlib
import itertools
import json
import math
from pathlib import Path
import platform
import re
from typing import Any


STRESS_COMPONENTS = ("SIXX", "SIYY", "SIZZ", "SIXY", "SIXZ", "SIYZ")
VECTOR_COMPONENTS = ("DX", "DY", "DZ")
COORDINATE_COMPONENTS = ("COOR_X", "COOR_Y", "COOR_Z")
GAUSS_POINT_IDS = (1, 2, 3, 4, 5)
_GMSH_TET_EDGES = ((0, 1), (1, 2), (2, 0), (0, 3), (2, 3), (1, 3))
_ASTER_TET_EDGES = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))


def coordinate_bijection(a: list[list[float]], b: list[list[float]]) -> list[int] | None:
    """Unique mapping a rows to b rows, retaining component tolerances 1e-12.

    Buckets select candidates only. Every accepted component is checked with
    math.isclose(rel_tol=1e-12, abs_tol=1e-12); duplicate/ambiguous matches fail.
    """
    if len(a) != len(b) or not a:
        return None
    if any(not isinstance(point, (list, tuple)) or len(point) != 3 or
           any(type(value) not in (int, float) or not math.isfinite(value) for value in point)
           for points in (a, b) for point in points):
        return None
    scale = max(1.0, max(abs(value) for points in (a, b) for point in points for value in point))
    width = 2 * (1e-12 * scale)

    def key(point):
        return tuple(math.floor(value / width) for value in point)

    buckets = {}
    for index, point in enumerate(b):
        buckets.setdefault(key(point), []).append(index)
    used, mapping = set(), []
    for point in a:
        center = key(point)
        candidates = []
        for offset in itertools.product((-1, 0, 1), repeat=3):
            nearby = tuple(value + shift for value, shift in zip(center, offset))
            for index in buckets.get(nearby, ()):
                if all(math.isclose(x, y, rel_tol=1e-12, abs_tol=1e-12)
                       for x, y in zip(point, b[index])):
                    candidates.append(index)
                    if len(candidates) > 1:
                        return None
        if len(candidates) != 1 or candidates[0] in used:
            return None
        used.add(candidates[0])
        mapping.append(candidates[0])
    return mapping if len(used) == len(b) else None


def _finite(value: Any, label: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"Non-numeric or missing Code_Aster observation: {label}")
    try:
        answer = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"Unrepresentable Code_Aster observation: {label}") from exc
    if not math.isfinite(answer):
        raise ValueError(f"Nonfinite Code_Aster observation: {label}")
    return answer


def _identifier(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"Code_Aster {label} must be a positive integer")
    return value


def _name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing Code_Aster {label}")
    return value.strip()


def _table_identifier(value: Any, label: str) -> int:
    """Pinned 17.4 CREA_TABLE serializes actual 1-based indices in char8.

    ctnotb/cteltb use int_to_char8(ino/ima), not optional mesh label arrays.
    Keep the original table string as evidence and verify its decoded identity.
    """
    text = _name(value, label)
    if not re.fullmatch(r"[1-9][0-9]*", text):
        raise ValueError(f"Code_Aster 17.4 {label} must be an actual decimal internal identifier")
    return int(text)


def _vector(value: Any, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"Code_Aster {label} must have exactly three finite components")
    return [_finite(item, label) for item in value]


def _table(value: Any, required: tuple[str, ...], label: str) -> tuple[dict, int]:
    if not isinstance(value, dict) or not set(required) <= value.keys():
        raise ValueError(f"Code_Aster {label} is missing required columns")
    if any(not isinstance(column, list) for column in value.values()):
        raise ValueError(f"Code_Aster {label} columns must be complete lists")
    lengths = {len(column) for column in value.values()}
    if len(lengths) != 1 or not lengths or next(iter(lengths)) == 0:
        raise ValueError(f"Code_Aster {label} has empty or incomplete columns")
    return value, next(iter(lengths))


def _field_order(table: dict, row: int, order: int, label: str) -> None:
    if ("NUME_ORDRE" not in table or type(table["NUME_ORDRE"][row]) is not int or
            table["NUME_ORDRE"][row] != order):
        raise ValueError(f"Unexpected Code_Aster order in {label}")


def parse_field_tables(raw: dict, mesh_size_mm: float) -> dict:
    """Require every node and all five TETRA10 points, with no row filtering.

    Reaction forces are summed once over the deduplicated union of supports.
    Nodal reaction and POST_RELEVE_T resultants must independently agree.
    This is table completeness/consistency, not an analytical PASS verdict.
    """
    if (not isinstance(raw, dict) or raw.get("schema_version") != "1" or
            raw.get("solver_status") != "COMPLETED" or raw.get("converged") is not True):
        raise ValueError("Incomplete Code_Aster native result")
    order = _identifier(raw.get("order"), "result order")
    catalog = raw.get("mesh")
    if not isinstance(catalog, dict):
        raise ValueError("Code_Aster mesh catalog is missing")
    nodes = catalog.get("nodes")
    elements = catalog.get("body_elements")
    if not isinstance(nodes, list) or len(nodes) < 4 or not isinstance(elements, list) or not elements:
        raise ValueError("Code_Aster mesh catalog is empty")
    node_by_name = {}
    node_by_id = {}
    for item in nodes:
        if not isinstance(item, dict):
            raise ValueError("Malformed Code_Aster node catalog")
        identifier = _identifier(item.get("node_id"), "node id")
        name = _name(item.get("name"), "node name")
        if _table_identifier(name, "node identifier") != identifier:
            raise ValueError("Code_Aster node table identifier disagrees with its actual mesh index")
        coordinate = _vector(item.get("coordinates_mm"), "node coordinates")
        if identifier in node_by_id or name in node_by_name:
            raise ValueError("Duplicate Code_Aster node id/name")
        node_by_name[name] = {"node_id": identifier, "coordinates_mm": coordinate}
        node_by_id[identifier] = name
    element_by_name = {}
    element_ids = set()
    for item in elements:
        if not isinstance(item, dict):
            raise ValueError("Malformed Code_Aster element catalog")
        identifier = _identifier(item.get("element_id"), "element id")
        name = _name(item.get("name"), "element name")
        if _table_identifier(name, "element identifier") != identifier:
            raise ValueError("Code_Aster element table identifier disagrees with its actual mesh index")
        if identifier in element_ids or name in element_by_name:
            raise ValueError("Duplicate Code_Aster element id/name")
        element_ids.add(identifier)
        element_by_name[name] = identifier
    groups = catalog.get("group_node_ids")
    if not isinstance(groups, dict) or set(groups) != {"X0", "XL", "Y0", "Z0"}:
        raise ValueError("Missing Code_Aster boundary-group node catalog")
    normalized_groups = {}
    for name, identifiers in groups.items():
        if not isinstance(identifiers, list) or not identifiers:
            raise ValueError(f"Empty Code_Aster boundary group: {name}")
        checked = [_identifier(item, "boundary node id") for item in identifiers]
        if len(set(checked)) != len(checked) or not set(checked) <= node_by_id.keys():
            raise ValueError(f"Duplicate or unknown Code_Aster boundary node: {name}")
        normalized_groups[name] = checked
    support = catalog.get("support_node_ids")
    if not isinstance(support, list) or not support:
        raise ValueError("Missing Code_Aster support union")
    support = [_identifier(item, "support node id") for item in support]
    expected_union = set(normalized_groups["X0"]) | set(normalized_groups["Y0"]) | set(normalized_groups["Z0"])
    if len(support) != len(set(support)) or set(support) != expected_union:
        raise ValueError("Code_Aster support union is incomplete or contains duplicate nodes")
    if catalog.get("gauss_point_ids") != list(GAUSS_POINT_IDS):
        raise ValueError("Code_Aster TETRA10 RIGI requires the five verified FPG5 points")
    tables = raw.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("Missing Code_Aster field tables")
    displacement, displacement_count = _table(tables.get("DEPL"),
        ("NOEUD", "NUME_ORDRE", *COORDINATE_COMPONENTS, *VECTOR_COMPONENTS), "DEPL table")
    reactions, reaction_count = _table(tables.get("REAC_NODA"),
        ("NOEUD", "NUME_ORDRE", *COORDINATE_COMPONENTS, *VECTOR_COMPONENTS), "REAC_NODA table")
    if displacement_count != len(nodes) or reaction_count != len(nodes):
        raise ValueError("Code_Aster nodal tables must cover every mesh node")

    def nodal(table: dict, count: int, label: str) -> dict:
        values = {}
        for row in range(count):
            name = _name(table["NOEUD"][row], label + " node name")
            if name not in node_by_name or name in values:
                raise ValueError(f"Unknown or duplicate node in Code_Aster {label}")
            _field_order(table, row, order, label)
            coords = [_finite(table[key][row], label + " coordinate") for key in COORDINATE_COMPONENTS]
            expected = node_by_name[name]["coordinates_mm"]
            if any(not math.isclose(a, b, rel_tol=1e-13, abs_tol=1e-13)
                   for a, b in zip(coords, expected)):
                raise ValueError(f"Code_Aster {label} coordinates differ from the actual mesh")
            values[name] = [_finite(table[key][row], label + " component") for key in VECTOR_COMPONENTS]
        if set(values) != set(node_by_name):
            raise ValueError(f"Missing mesh nodes in Code_Aster {label}")
        return values

    displacements = nodal(displacement, displacement_count, "DEPL")
    reaction_values = nodal(reactions, reaction_count, "REAC_NODA")
    stress, stress_count = _table(tables.get("SIEF_ELGA"),
        ("MAILLE", "POINT", "SOUS_POINT", "NUME_ORDRE", *COORDINATE_COMPONENTS, *STRESS_COMPONENTS), "SIEF_ELGA table")
    if stress_count != 5 * len(elements):
        raise ValueError("Code_Aster stress table must cover five points per TETRA10 volume element")
    identifiers = set()
    point_ids = {name: set() for name in element_by_name}
    stress_rows, stress_coordinates, stress_identifiers = [], [], []
    for row in range(stress_count):
        name = _name(stress["MAILLE"][row], "stress element name")
        point = _identifier(stress["POINT"][row], "stress point")
        subpoint = _identifier(stress["SOUS_POINT"][row], "stress subpoint")
        key = (name, point, subpoint, order)
        if name not in element_by_name or key in identifiers or point not in GAUSS_POINT_IDS or subpoint != 1:
            raise ValueError("Unknown/duplicate Code_Aster element-point-subpoint/order")
        _field_order(stress, row, order, "SIEF_ELGA")
        identifiers.add(key)
        point_ids[name].add(point)
        stress_coordinates.append([_finite(stress[col][row], "stress point coordinate")
                                   for col in COORDINATE_COMPONENTS])
        stress_rows.append([_finite(stress[col][row], "stress component") for col in STRESS_COMPONENTS])
        stress_identifiers.append({"element_id": element_by_name[name], "element_name": name,
                                   "point": point, "subpoint": subpoint, "order": order})
    if any(points != set(GAUSS_POINT_IDS) for points in point_ids.values()):
        raise ValueError("Incomplete Code_Aster TETRA10 stress integration-point coverage")
    reaction_n = [math.fsum(reaction_values[node_by_id[node]][axis] for node in support)
                  for axis in range(3)]
    post = tables.get("SUPPORT_RESULTANT")
    post, post_count = _table(post, ("INTITULE", "NUME_ORDRE", *VECTOR_COMPONENTS),
                             "POST_RELEVE_T support resultant")
    if post_count != 1:
        raise ValueError("Code_Aster support resultant requires exactly one actual result order")
    _field_order(post, 0, order, "POST_RELEVE_T")
    if _name(post["INTITULE"][0], "resultant title") != "SUPPORT":
        raise ValueError("Code_Aster resultant does not name the deduplicated SUPPORT union")
    resultant = [_finite(post[key][0], "POST_RELEVE_T resultant") for key in VECTOR_COMPONENTS]
    tolerance = 1e-12 * max(1.0, *(abs(value) for value in [*reaction_n, *resultant]))
    if any(abs(a - b) > tolerance for a, b in zip(reaction_n, resultant)):
        raise ValueError("Deduplicated REAC_NODA sum disagrees with the native support resultant")
    sorted_ids = sorted(node_by_id)
    return {"mesh_size_mm": _finite(mesh_size_mm, "mesh size"), "node_ids": sorted_ids,
            "coordinates_mm": [node_by_name[node_by_id[node]]["coordinates_mm"] for node in sorted_ids],
            "displacements_mm": [displacements[node_by_id[node]] for node in sorted_ids],
            "stresses_mpa": stress_rows, "reaction_n": reaction_n, "element_count": len(elements),
            "native_node_names": [node_by_id[node] for node in sorted_ids],
            "native_element_names": list(element_by_name), "stress_identifiers": stress_identifiers,
            "stress_point_coordinates_mm": stress_coordinates,
            "nodal_reactions_n": [reaction_values[node_by_id[node]] for node in sorted_ids],
            "support_node_ids": support, "group_node_ids": normalized_groups,
            "native_support_resultant_n": resultant, "actual_result_order": order,
            "stress_component_order": ["xx", "yy", "zz", "xy", "xz", "yz"]}


def _json_safe(value: Any) -> Any:
    """Retain invalid numeric observations as explicit tokens, never drop rows."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        return _json_safe(value.tolist())
    if hasattr(value, "item"):
        return _json_safe(value.item())
    if type(value) is float and not math.isfinite(value):
        return {"invalid_numeric": repr(value)}
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise TypeError(f"Unsupported raw Code_Aster observation type: {type(value).__name__}")


def _save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(_json_safe(value), indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


def _runtime_versions() -> tuple[dict, dict]:
    from code_aster.Utilities import ExecutionParameter
    parameter = ExecutionParameter()
    metadata = {key: _json_safe(parameter.get_option(key))
                for key in ("version", "parentid", "branch", "uncommitted")}
    versions = {"code_aster": metadata["version"], "python": platform.python_version()}
    for name in ("numpy", "scipy", "mpi4py", "petsc4py"):
        try:
            module = importlib.import_module(name)
        except ImportError:
            versions[name] = None
        else:
            versions[name] = getattr(module, "__version__", None)
    try:
        from petsc4py import PETSc
    except ImportError:
        versions["petsc"] = None
    else:
        versions["petsc"] = ".".join(map(str, PETSc.Sys.getVersion()))
    return versions, metadata


def validate_native_mesh(mesh: Any, expected: dict) -> dict:
    """Block MECA unless imported geometry, topology and load/support groups match.

    Coordinates keep the host's original 1e-12 component tolerances. Native
    TETRA10 corner roles and each edge's midpoint ID must match the checked
    Gmsh source; 17.4 swaps Gmsh slots 9/10 during import (inigms.F90).
    """
    if not isinstance(expected, dict) or expected.get("schema_version") != "1":
        raise ValueError("Expected checked mesh catalogue is missing")
    source_ids = expected.get("node_ids")
    source_coordinates = expected.get("coordinates_mm")
    tetrahedra = expected.get("tetrahedra")
    source_groups = expected.get("group_node_ids")
    if (not isinstance(source_ids, list) or len(source_ids) < 4 or
            any(type(node) is not int or node <= 0 for node in source_ids) or
            len(set(source_ids)) != len(source_ids) or not isinstance(source_coordinates, list) or
            len(source_coordinates) != len(source_ids) or not isinstance(tetrahedra, list) or not tetrahedra or
            not isinstance(source_groups, dict) or set(source_groups) != {"X0", "XL", "Y0", "Z0"}):
        raise ValueError("Malformed checked source mesh catalogue")
    source_id_set = set(source_ids)
    coordinates = mesh.getCoordinates().toNumpy().tolist()
    node_indexes = list(mesh.getNodes())
    if (mesh.getNumberOfNodes() != len(coordinates) or len(node_indexes) != len(coordinates) or
            any(type(index) is not int for index in node_indexes) or
            set(node_indexes) != set(range(len(coordinates)))):
        raise ValueError("Incomplete native numeric node catalogue before MECA")
    mapping = coordinate_bijection(coordinates, source_coordinates)
    if mapping is None:
        raise ValueError("Native/source coordinates have no unique bijection at the original 1e-12 tolerances")
    source_by_native = [source_ids[row] for row in mapping]
    connectivity = mesh.getConnectivity()
    cell_count = mesh.getNumberOfCells()
    if cell_count != expected.get("total_cell_count") or len(connectivity) != cell_count:
        raise ValueError("Native total cell count differs from the checked source mesh")
    body = list(mesh.getCells("BODY"))
    if (len(body) != len(tetrahedra) or len(set(body)) != len(body) or
            any(type(index) is not int or not 0 <= index < cell_count for index in body)):
        raise ValueError("Native BODY count/indices differ from the checked source tetrahedra")
    source_tets = {}
    element_ids = set()
    for tet in tetrahedra:
        if not isinstance(tet, dict):
            raise ValueError("Malformed source TETRA10 catalogue")
        element_id = _identifier(tet.get("element_id"), "source element id")
        nodes = tet.get("node_ids")
        if (not isinstance(nodes, list) or len(nodes) != 10 or
                any(type(node) is not int for node in nodes) or len(set(nodes)) != 10 or
                not set(nodes) <= source_id_set or element_id in element_ids):
            raise ValueError("Malformed or duplicated source TETRA10 connectivity")
        corners = tuple(sorted(nodes[:4]))
        if corners in source_tets:
            raise ValueError("Duplicate source TETRA10 corners")
        source_tets[corners] = tet
        element_ids.add(element_id)
    matched, element_mapping, determinants = set(), [], []
    for index in body:
        nodes = connectivity[index]
        if (mesh.getCellTypeName(index) != "TETRA10" or len(nodes) != 10 or len(set(nodes)) != 10 or
                any(type(node) is not int or not 0 <= node < len(coordinates) for node in nodes)):
            raise ValueError("Native BODY must contain complete TETRA10 cells with ten unique actual nodes")
        mapped = [source_by_native[node] for node in nodes]
        corners = tuple(sorted(mapped[:4]))
        tet = source_tets.get(corners)
        if tet is None or corners in matched or set(mapped[4:]) != set(tet["node_ids"][4:]):
            raise ValueError("Native TETRA10 corner/midside roles differ from the checked source")
        source_nodes = tet["node_ids"]
        expected_native_order = [source_nodes[slot] for slot in (0, 1, 2, 3, 4, 5, 6, 7, 9, 8)]
        if mapped != expected_native_order:
            raise ValueError("Native all-ten TETRA10 node ordering differs from the pinned 17.4 Gmsh import permutation")
        expected_edges = {tuple(sorted((source_nodes[a], source_nodes[b]))): middle
                          for middle, (a, b) in zip(source_nodes[4:], _GMSH_TET_EDGES)}
        if any(expected_edges.get(tuple(sorted((mapped[a], mapped[b])))) != middle
               for middle, (a, b) in zip(mapped[4:], _ASTER_TET_EDGES)):
            raise ValueError("Native TETRA10 edge/midpoint association differs from the checked source")
        p, q, r, s = [coordinates[node] for node in nodes[:4]]
        u, v, w = ([end[axis] - p[axis] for axis in range(3)] for end in (q, r, s))
        determinant = math.fsum((u[0] * (v[1] * w[2] - v[2] * w[1]),
                                 u[1] * (v[2] * w[0] - v[0] * w[2]),
                                 u[2] * (v[0] * w[1] - v[1] * w[0])))
        if not math.isfinite(determinant) or determinant <= 0:
            raise ValueError("Native TETRA10 has a nonpositive affine Jacobian before MECA")
        determinants.append(determinant)
        matched.add(corners)
        element_mapping.append({"native_cell_index": index, "source_element_id": tet["element_id"]})
    native_groups = {}
    for name, identifiers in source_groups.items():
        if (not isinstance(identifiers, list) or not identifiers or len(set(identifiers)) != len(identifiers) or
                any(type(node) is not int for node in identifiers) or not set(identifiers) <= source_id_set):
            raise ValueError("Malformed source boundary node group")
        native = list(mesh.getNodesFromCells(name))
        if (not native or len(native) != len(set(native)) or
                any(type(node) is not int or not 0 <= node < len(coordinates) for node in native) or
                {source_by_native[node] for node in native} != set(identifiers)):
            raise ValueError(f"Native {name} group differs from the checked source before MECA")
        native_groups[name] = native
    return {"status": "PASS", "node_count": len(coordinates), "volume_element_count": len(body),
            "total_cell_count": cell_count, "coordinate_tolerances": {"relative": 1e-12, "absolute": 1e-12},
            "minimum_native_jacobian_mm3": min(determinants),
            "source_node_ids_by_native_index": source_by_native,
            "source_element_mapping": element_mapping, "native_group_node_indices": native_groups,
            "topology": "Pinned 17.4 all-ten Gmsh->Aster node order (slots9/10 swapped), corner/midside roles and positive Jacobian match source",
            "solver_gate": "Verified before MECA_STATIQUE"}


def _native_mesh_catalog(mesh: Any, tables: dict, order: int) -> dict:
    """Map actual numeric mesh indices to actual decimal CREA_TABLE strings.

    Mesh node coordinates and BODY indices independently verify a complete
    bijection. No optional NOMNOE/NOMMAI labels or invented prefixes are used.
    """
    coordinates = mesh.getCoordinates().toNumpy().tolist()
    node_indexes = list(mesh.getNodes())
    node_index_set = set(node_indexes)
    body_indexes = list(mesh.getCells("BODY"))
    node_count, cell_count = mesh.getNumberOfNodes(), mesh.getNumberOfCells()
    if (node_count != len(coordinates) or len(node_indexes) != len(coordinates) or
            node_index_set != set(range(len(coordinates))) or
            any(type(index) is not int for index in node_indexes) or not body_indexes or
            len(body_indexes) != len(set(body_indexes)) or
            any(type(index) is not int or index < 0 or index >= cell_count for index in body_indexes)):
        raise ValueError("Incomplete Code_Aster actual numeric mesh catalog")
    displacement, count = _table(tables.get("DEPL"),
        ("NOEUD", "NUME_ORDRE", *COORDINATE_COMPONENTS, *VECTOR_COMPONENTS), "DEPL table")
    if count != len(node_indexes):
        raise ValueError("Code_Aster DEPL identifiers must cover every actual mesh node")
    node_names = {}
    for row in range(count):
        raw_name = displacement["NOEUD"][row]
        identifier = _table_identifier(raw_name, "NOEUD")
        if identifier - 1 not in node_index_set or identifier in node_names:
            raise ValueError("Duplicate or unknown actual Code_Aster NOEUD index")
        _field_order(displacement, row, order, "DEPL")
        actual = _vector(coordinates[identifier - 1], "actual node coordinates")
        observed = [_finite(displacement[key][row], "DEPL node coordinate") for key in COORDINATE_COMPONENTS]
        if any(not math.isclose(a, b, rel_tol=1e-13, abs_tol=1e-13) for a, b in zip(actual, observed)):
            raise ValueError("Code_Aster NOEUD decimal index/XYZ does not match the actual native mesh")
        node_names[identifier] = raw_name
    stress, _ = _table(tables.get("SIEF_ELGA"),
        ("MAILLE", "POINT", "SOUS_POINT", "NUME_ORDRE", *COORDINATE_COMPONENTS, *STRESS_COMPONENTS), "SIEF_ELGA table")
    element_names = {}
    body_ids = {index + 1 for index in body_indexes}
    for raw_name in stress["MAILLE"]:
        identifier = _table_identifier(raw_name, "MAILLE")
        if identifier not in body_ids:
            raise ValueError("Code_Aster stress MAILLE identifier is not an actual BODY cell")
        element_names.setdefault(identifier, raw_name)
    if set(element_names) != body_ids:
        raise ValueError("Code_Aster stress MAILLE identifiers must cover every actual BODY cell")
    return {"nodes": [{"node_id": index + 1, "name": node_names[index + 1],
                       "coordinates_mm": coordinates[index]} for index in node_indexes],
            "body_elements": [{"element_id": index + 1, "name": element_names[index + 1]}
                              for index in body_indexes],
            "group_node_ids": {group: [index + 1 for index in mesh.getNodesFromCells(group)]
                               for group in ("X0", "XL", "Y0", "Z0")},
            "support_node_ids": [index + 1 for index in mesh.getNodes("SUPPORT")],
            "gauss_point_ids": list(GAUSS_POINT_IDS),
            "name_api": "Pinned 17.4 CREA_TABLE decimal internal indices verified against Mesh numeric indices/XYZ"}


def solve_level(input_path: str) -> None:
    """Executed by the trusted .comm inside the pinned solver-only image."""
    from code_aster.Commands import (AFFE_CHAR_MECA, AFFE_MATERIAU, AFFE_MODELE, CALC_CHAMP,
                                     CREA_TABLE, DEBUT, DEFI_GROUP, DEFI_MATERIAU, FIN,
                                     IMPR_RESU, LIRE_MAILLAGE, MECA_STATIQUE, POST_RELEVE_T)
    from code_aster.Cata.Syntax import _F

    input_file = Path(input_path)
    config = json.loads(input_file.read_text(encoding="utf-8"))
    settings = config["settings"]
    output = input_file.parent
    # run_aster passes data inputs as --link arguments; DEBUT initializes those
    # deferred links before fort.20 can be inspected or LIRE_MAILLAGE called.
    DEBUT()
    unit20 = Path("fort.20")
    if not unit20.is_file():
        raise RuntimeError("Code_Aster unit 20 mesh input is missing")
    mesh_input_sha256 = hashlib.sha256(unit20.read_bytes()).hexdigest()
    if mesh_input_sha256 != config["mesh_sha256"]:
        raise RuntimeError("Code_Aster unit 20 differs from the checked immutable Gmsh mesh")
    versions, runtime = _runtime_versions()
    _save(output / "runtime.json", {"versions": versions, "code_aster_runtime": runtime})
    if versions.get("code_aster") != "17.4.0":
        raise RuntimeError("The native mesh import policy requires actual Code_Aster 17.4.0")
    mesh = LIRE_MAILLAGE(FORMAT="GMSH", UNITE=20)
    try:
        expected_file = output / "expected_mesh.json"
        expected_sha = hashlib.sha256(expected_file.read_bytes()).hexdigest()
        if expected_sha != config.get("expected_mesh_sha256"):
            raise ValueError("Checked source mesh catalogue SHA256 drifted before MECA")
        native_checks = validate_native_mesh(mesh, json.loads(expected_file.read_text(encoding="utf-8")))
        native_checks.update({"expected_mesh_sha256": expected_sha, "checked_msh_sha256": mesh_input_sha256})
        _save(output / "native_mesh_checks.json", native_checks)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        _save(output / "native_mesh_checks.json", {"status": "FAIL", "error": str(exc),
              "solver_status": "NOT_RUN", "expected_mesh_sha256": config.get("expected_mesh_sha256"),
              "checked_msh_sha256": mesh_input_sha256})
        raise RuntimeError(f"Native mesh pre-MECA guard rejected the import: {exc}") from exc
    mesh = DEFI_GROUP(reuse=mesh, MAILLAGE=mesh, CREA_GROUP_NO=(
        _F(NOM="NX0", GROUP_MA="X0", CRIT_NOEUD="TOUS"),
        _F(NOM="NY0", GROUP_MA="Y0", CRIT_NOEUD="TOUS"),
        _F(NOM="NZ0", GROUP_MA="Z0", CRIT_NOEUD="TOUS")))
    mesh = DEFI_GROUP(reuse=mesh, MAILLAGE=mesh,
                      CREA_GROUP_NO=_F(NOM="SUPPORT", UNION=("NX0", "NY0", "NZ0")))
    support = list(mesh.getNodes("SUPPORT"))
    support_expected = set().union(*(set(native_checks["native_group_node_indices"][name])
                                    for name in ("X0", "Y0", "Z0")))
    if len(support) != len(set(support)) or set(support) != support_expected:
        native_checks.update({"status": "FAIL", "error": "Native support union differs from verified groups",
                              "solver_status": "NOT_RUN"})
        _save(output / "native_mesh_checks.json", native_checks)
        raise RuntimeError("Native support union failed before MECA")
    native_checks["support_union_verified"] = True
    _save(output / "native_mesh_checks.json", native_checks)
    model = AFFE_MODELE(MAILLAGE=mesh,
                        AFFE=_F(TOUT="OUI", PHENOMENE="MECANIQUE", MODELISATION="3D"))
    material = DEFI_MATERIAU(ELAS=_F(E=settings["material"]["youngs_modulus_mpa"],
                                    NU=settings["material"]["poisson_ratio"]))
    material_field = AFFE_MATERIAU(MAILLAGE=mesh, AFFE=_F(TOUT="OUI", MATER=material))
    load = AFFE_CHAR_MECA(MODELE=model, DDL_IMPO=(
        _F(GROUP_MA="X0", DX=0.0), _F(GROUP_MA="Y0", DY=0.0), _F(GROUP_MA="Z0", DZ=0.0)),
        FORCE_FACE=_F(GROUP_MA="XL", FX=settings["traction_mpa"]))
    result = MECA_STATIQUE(MODELE=model, CHAM_MATER=material_field,
                           EXCIT=_F(CHARGE=load), SOLVEUR=_F(METHODE="MUMPS"))
    result = CALC_CHAMP(reuse=result, RESULTAT=result, FORCE="REAC_NODA")
    indexes = list(result.getIndexes())
    if len(indexes) != 1 or type(indexes[0]) is not int or indexes[0] <= 0:
        raise RuntimeError("The linear-static benchmark requires one actual result order")
    order = indexes[0]
    tables = {}
    for field, components in (("DEPL", VECTOR_COMPONENTS), ("SIEF_ELGA", STRESS_COMPONENTS),
                              ("REAC_NODA", VECTOR_COMPONENTS)):
        selection = {"GROUP_MA": "BODY"} if field == "SIEF_ELGA" else {"TOUT": "OUI"}
        table = CREA_TABLE(RESU=_F(RESULTAT=result, NOM_CHAM=field, NUME_ORDRE=order,
                                   NOM_CMP=components, **selection))
        tables[field] = table.EXTR_TABLE().values()
        _save(output / f"{field.lower()}.table.json", tables[field])
    catalog = _native_mesh_catalog(mesh, tables, order)
    _save(output / "mesh_catalog.json", catalog)
    resultant = POST_RELEVE_T(ACTION=_F(
        INTITULE="SUPPORT", OPERATION="EXTRACTION", REPERE="GLOBAL", RESULTAT=result,
        NOM_CHAM="REAC_NODA", NUME_ORDRE=order, GROUP_NO="SUPPORT", RESULTANTE=VECTOR_COMPONENTS))
    tables["SUPPORT_RESULTANT"] = resultant.EXTR_TABLE().values()
    _save(output / "support_resultant.table.json", tables["SUPPORT_RESULTANT"])
    IMPR_RESU(FORMAT="MED", UNITE=80,
               RESU=_F(RESULTAT=result, NOM_CHAM=("DEPL", "SIEF_ELGA", "REAC_NODA"), NUME_ORDRE=order))
    # The vendor's Spack lock records the exact bundled numerical dependencies.
    lock = Path("/opt/spack/var/spack/environments/simvia_env/spack.lock")
    libraries = None
    if lock.is_file():
        lock_data = json.loads(lock.read_text(encoding="utf-8"))
        _save(output / "spack.lock.json", lock_data)
        libraries = [{"name": spec.get("name"), "version": spec.get("version"), "hash": digest}
                     for digest, spec in lock_data.get("concrete_specs", {}).items()]
    raw = {"schema_version": "1", "solver_status": "COMPLETED", "converged": True,
           "order": order, "available_orders": indexes, "versions": versions,
           "access_parameters": result.getAccessParameters(),
           "code_aster_runtime": runtime, "numerical_libraries": libraries,
           "input_sha256": hashlib.sha256(input_file.read_bytes()).hexdigest(),
           "mesh_input_sha256": mesh_input_sha256,
           "native_mesh_checks": native_checks,
           "mesh": catalog, "tables": tables,
           "linear_solver": {"method": "MUMPS", "measured_linear_residual": None,
                             "residual_status": "UNKNOWN: no assembled A/u/b was exported"}}
    _save(output / "worker_result.json", raw)
    FIN()
