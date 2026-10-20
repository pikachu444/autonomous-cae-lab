"""Pinned Code_Aster HEXA20 worker; pure strict extraction outside the solver.

Native syntax is checked against official tag 17.4.0, commit
50ebc13c70ee9df62faf93ddcb746a3757b3042a: inigms.F90,
meca_3d.py, defi_group.py and affe_char_meca.py. Public tables contain actual
decimal internal indices; they are never assumed to be external catalogue IDs.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
from typing import Any

if __package__:
    from .codeaster_worker import (COORDINATE_COMPONENTS, STRESS_COMPONENTS, VECTOR_COMPONENTS,
        _finite, _field_order, _identifier, _runtime_versions, _save, _table,
        _table_identifier, _vector, coordinate_bijection)
    from .structural_family_mesh import hexa20_point_coordinates
else:  # Copied, hash-bound worker inside the isolated vendor image.
    from codeaster_worker import (COORDINATE_COMPONENTS, STRESS_COMPONENTS, VECTOR_COMPONENTS,
        _finite, _field_order, _identifier, _runtime_versions, _save, _table,
        _table_identifier, _vector, coordinate_bijection)
    from structural_family_mesh import hexa20_point_coordinates

ASTER_FROM_CANONICAL = (*range(12), *range(16, 20), *range(12, 16))
GMSH_FROM_CANONICAL = (0, 1, 2, 3, 4, 5, 6, 7, 8, 11, 16, 9, 17, 10, 18, 19, 12, 15, 13, 14)
_G = math.sqrt(3.0 / 5.0)
ASTER_GAUSS27 = tuple(itertools.product((-_G, 0.0, _G), repeat=3))
CANONICAL_GAUSS27 = tuple((x, y, z) for z in (-_G, 0.0, _G)
                         for y in (-_G, 0.0, _G) for x in (-_G, 0.0, _G))
_SOURCE_FILES = ("structural_family_codeaster_worker.py", "codeaster_worker.py", "structural_family_mesh.py")
_PHYSICAL_NAME_POLICY = "Code_Aster17.4-GMSH-character8-case-preserved"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_catalogue(mesh: dict) -> tuple[dict[int, list[float]], dict[int, list[int]]]:
    """Strict structural catalogue admission independent of any native result."""
    if not isinstance(mesh, dict) or mesh.get("schema_version") != "1" or mesh.get("element_type") != "HEXA20":
        raise ValueError("Missing shared HEXA20 catalogue")
    rows, cells = mesh.get("nodes"), mesh.get("elements")
    if not isinstance(rows, list) or not 20 <= len(rows) <= 10000 or not isinstance(cells, list) or not 1 <= len(cells) <= 1024:
        raise ValueError("Incomplete or unbounded shared node/element catalogue")
    nodes = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Malformed shared node")
        identifier = _identifier(row.get("id"), "shared node")
        if identifier in nodes:
            raise ValueError("Duplicate shared node")
        nodes[identifier] = _vector(row.get("coordinates_mm"), "shared coordinates")
    if coordinate_bijection(list(nodes.values()), list(nodes.values())) is None:
        raise ValueError("Shared nodes have duplicate or ambiguous coordinates")
    elements = {}
    for row in cells:
        if not isinstance(row, dict):
            raise ValueError("Malformed shared element")
        identifier = _identifier(row.get("id"), "shared element")
        connectivity = row.get("node_ids")
        if identifier in elements or not isinstance(connectivity, list) or len(connectivity) != 20 or len(set(connectivity)) != 20:
            raise ValueError("Duplicate or incomplete shared HEXA20 element")
        if any(type(node) is not int or node not in nodes for node in connectivity):
            raise ValueError("Unknown shared HEXA20 node")
        elements[identifier] = connectivity
    if set(nodes) != {node for connectivity in elements.values() for node in connectivity}:
        raise ValueError("Every shared node must belong to a volume element")
    groups = mesh.get("groups")
    if not isinstance(groups, dict) or not groups:
        raise ValueError("Shared node groups are missing")
    for name, identifiers in groups.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,23}", name) or name == "SOLID" or name == "CAE_ALL" or name.startswith("CAE_N"):
            raise ValueError("Invalid or reserved shared group name")
        if not isinstance(identifiers, list) or not identifiers or len(set(identifiers)) != len(identifiers) or any(type(node) is not int or node not in nodes for node in identifiers):
            raise ValueError("Duplicate or unknown shared group node")
    supports = mesh.get("supports")
    if not isinstance(supports, list) or not supports:
        raise ValueError("Shared supports are missing")
    seen = set()
    for row in supports:
        if not isinstance(row, dict) or type(row.get("node_id")) is not int or row["node_id"] not in nodes or row["node_id"] in seen:
            raise ValueError("Duplicate or unknown shared support node")
        components = row.get("components")
        if not isinstance(components, list) or not components or len(set(components)) != len(components) or any(type(axis) is not int or axis not in (1, 2, 3) for axis in components):
            raise ValueError("Malformed shared restrained DOFs")
        seen.add(row["node_id"])
    loads = mesh.get("nodal_loads_n")
    if not isinstance(loads, list) or not loads:
        raise ValueError("Shared equivalent nodal loads are missing")
    seen = set()
    for row in loads:
        if not isinstance(row, dict) or type(row.get("node_id")) is not int or row["node_id"] not in nodes or row["node_id"] in seen:
            raise ValueError("Duplicate or unknown shared force node")
        _vector(row.get("value"), "shared nodal force")
        seen.add(row["node_id"])
    responses = mesh.get("response_node_ids")
    if not isinstance(responses, dict) or not responses:
        raise ValueError("Shared response locations are missing")
    for identifiers in responses.values():
        if not isinstance(identifiers, list) or not identifiers or len(set(identifiers)) != len(identifiers) or any(type(node) is not int or node not in nodes for node in identifiers):
            raise ValueError("Unknown or duplicate shared response node")
    return nodes, elements


def _physical_groups(mesh: dict) -> dict:
    return {"SOLID": {"dimension": 3, "tag": 1},
            **{name: {"dimension": 0, "tag": index + 2}
               for index, name in enumerate(sorted(mesh["groups"]))}}


def _native_group_name_map(physical_groups: dict) -> dict:
    """Model pinned pregms.F90 character(len=8); never rename source groups."""
    if not isinstance(physical_groups, dict) or not physical_groups:
        raise ValueError("Missing canonical physical groups for the native name map")
    mapping = {}
    for name, descriptor in physical_groups.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,23}", name):
            raise ValueError("Malformed canonical physical group name")
        if not isinstance(descriptor, dict) or set(descriptor) != {"dimension", "tag"} or type(descriptor["dimension"]) is not int or type(descriptor["tag"]) is not int or descriptor["dimension"] not in (0, 3) or descriptor["tag"] < 1:
            raise ValueError("Malformed canonical physical group dimension/tag")
        mapping[name] = name[:8]
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("Pinned eight-character native physical group names collide")
    return mapping


def _checked_native_group_name_map(expected: dict) -> dict:
    imported = expected.get("native_import")
    if not isinstance(imported, dict) or imported.get("schema_version") != "1":
        raise ValueError("Missing checked native import contract")
    physical_groups = _physical_groups(expected)
    mapping = _native_group_name_map(physical_groups)
    if imported.get("physical_groups") != physical_groups or imported.get("physical_name_policy") != _PHYSICAL_NAME_POLICY or imported.get("canonical_to_native_group_names") != mapping or imported.get("native_physical_group_names") != sorted(mapping.values()):
        raise ValueError("Native physical group name map differs from the checked source")
    # Validate metadata value types as well as equality (True is not a tag).
    _native_group_name_map(imported["physical_groups"])
    return mapping


def gmsh_import_contract(mesh: dict, path: Path) -> dict:
    """Verify emitted ASCII MSH against the catalogue, preserving every POI1."""
    nodes, elements = validate_catalogue(mesh)
    physical_groups = _physical_groups(mesh)
    native_names = _native_group_name_map(physical_groups)
    if not path.is_file() or path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("Missing or oversized shared Gmsh source")
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]

    def section(name):
        if lines.count("$" + name) != 1 or lines.count("$End" + name) != 1:
            raise ValueError("Incomplete or duplicate Gmsh section")
        begin, end = lines.index("$" + name), lines.index("$End" + name)
        if begin >= end:
            raise ValueError("Malformed Gmsh section")
        return lines[begin + 1:end]

    if section("MeshFormat") != ["2.2 0 8"]:
        raise ValueError("Only shared ASCII MSH2.2 is admitted")
    physical = section("PhysicalNames")
    tags = {}
    for row in physical[1:]:
        match = re.fullmatch(r'(\d+)\s+(\d+)\s+"([A-Za-z][A-Za-z0-9_]*)"', row)
        if not match or int(match[2]) in tags:
            raise ValueError("Malformed/duplicate shared physical group")
        tags[int(match[2])] = (int(match[1]), match[3])
    expected_names = {"SOLID": 3, **{name: 0 for name in mesh["groups"]}}
    if not physical or int(physical[0]) != len(tags) or len({name for _, name in tags.values()}) != len(tags) or {name: dim for dim, name in tags.values()} != expected_names:
        raise ValueError("Gmsh groups differ from the shared catalogue")
    if {name: {"dimension": dim, "tag": tag} for tag, (dim, name) in tags.items()} != physical_groups:
        raise ValueError("Gmsh physical group dimensions/tags differ from the exact shared writer")
    raw_nodes = section("Nodes")
    observed = {}
    for row in raw_nodes[1:]:
        items = row.split()
        if len(items) != 4:
            raise ValueError("Malformed Gmsh node row")
        identifier = int(items[0])
        if identifier in observed:
            raise ValueError("Duplicate Gmsh node")
        observed[identifier] = [float(value) for value in items[1:]]
    if not raw_nodes or int(raw_nodes[0]) != len(nodes) or set(observed) != set(nodes) or len(raw_nodes) != len(nodes) + 1:
        raise ValueError("Gmsh nodes differ from the shared catalogue")
    for identifier in nodes:
        if observed[identifier] != nodes[identifier]:
            raise ValueError("Gmsh source coordinates differ from the shared catalogue")
    raw_cells = section("Elements")
    seen, volume_ids, group_nodes, cells = set(), set(), {name: [] for name in mesh["groups"]}, []
    for row in raw_cells[1:]:
        items = [int(value) for value in row.split()]
        if len(items) < 5 or items[0] <= 0 or items[0] in seen or items[2] != 2:
            raise ValueError("Malformed or duplicate Gmsh cell")
        identifier, kind, _, physical_tag, geometric_tag, *connectivity = items
        if physical_tag not in tags:
            raise ValueError("Unknown Gmsh physical group")
        dim, name = tags[physical_tag]
        if geometric_tag in tags and geometric_tag != physical_tag and tags[geometric_tag][0] == dim:
            raise ValueError("Gmsh geometry tag aliases another physical group under the pinned importer")
        if any(node not in nodes for node in connectivity):
            raise ValueError("Gmsh cell references unknown catalogue nodes")
        if kind == 17 and name == "SOLID" and identifier in elements:
            if connectivity != [elements[identifier][index] for index in GMSH_FROM_CANONICAL]:
                raise ValueError("Gmsh HEXA20 ordering differs from the canonical catalogue")
            native = [elements[identifier][index] for index in ASTER_FROM_CANONICAL]
            volume_ids.add(identifier)
            cells.append({"source_cell_id": identifier, "type": "HEXA20", "node_ids": native, "group": name})
        elif kind == 15 and dim == 0 and len(connectivity) == 1:
            group_nodes[name].append(connectivity[0])
            cells.append({"source_cell_id": identifier, "type": "POI1", "node_ids": connectivity, "group": name})
        else:
            raise ValueError("Only exact shared HEXA20 and grouped POI1 cells are admitted")
        seen.add(identifier)
    if not raw_cells or len(raw_cells) != len(cells) + 1 or int(raw_cells[0]) != len(cells) or volume_ids != set(elements):
        raise ValueError("Gmsh cells do not cover the shared volume catalogue")
    if any(len(ids) != len(set(ids)) or set(ids) != set(mesh["groups"][name]) for name, ids in group_nodes.items()):
        raise ValueError("Gmsh POI1 groups differ from exact catalogue node selections")
    return {"schema_version": "1", "format": "GMSH2.2", "total_cell_count": len(cells),
            "cells": cells, "physical_groups": physical_groups,
            "physical_name_policy": _PHYSICAL_NAME_POLICY,
            "canonical_to_native_group_names": native_names,
            "native_physical_group_names": sorted(native_names.values())}


def validate_native_mesh(mesh: Any, expected: dict) -> dict:
    """Prove complete coordinate, cell-role and physical-group bijections."""
    nodes, elements = validate_catalogue(expected)
    native_names = _checked_native_group_name_map(expected)
    imported = expected.get("native_import")
    coordinates = mesh.getCoordinates().toNumpy().tolist()
    indexes = list(mesh.getNodes())
    if mesh.getNumberOfNodes() != len(nodes) or len(coordinates) != len(nodes) or len(indexes) != len(nodes) or any(type(index) is not int for index in indexes) or set(indexes) != set(range(len(nodes))):
        raise ValueError("Incomplete actual native node catalogue")
    external_ids = list(nodes)
    mapping = coordinate_bijection(coordinates, [nodes[node] for node in external_ids])
    if mapping is None:
        raise ValueError("Native/source coordinates have no unique 1e-12 bijection")
    external_by_native = [external_ids[index] for index in mapping]
    native_by_external = {node: index for index, node in enumerate(external_by_native)}
    connectivity = mesh.getConnectivity()
    count = mesh.getNumberOfCells()
    if count != imported.get("total_cell_count") or len(connectivity) != count:
        raise ValueError("Native total cell count differs from the complete source")
    names = set(imported["physical_groups"])
    actual_names = list(mesh.getGroupsOfCells())
    if len(actual_names) != len(set(actual_names)) or set(actual_names) != set(native_names.values()):
        raise ValueError("Native physical group names differ from the checked source")
    native_groups, memberships = {}, {index: [] for index in range(count)}
    for name in names:
        cells = list(mesh.getCells(native_names[name]))
        if not cells or len(cells) != len(set(cells)) or any(type(index) is not int or not 0 <= index < count for index in cells):
            raise ValueError("Malformed native physical group cell indices")
        native_groups[name] = cells
        for index in cells:
            memberships[index].append(name)
    source = {}
    for cell in imported["cells"]:
        key = (cell["type"], tuple(cell["node_ids"]), (cell["group"],))
        if key in source:
            raise ValueError("Ambiguous checked source cells")
        source[key] = cell["source_cell_id"]
    matched, native_cells, volume_mapping = set(), [], []
    for index, cell in enumerate(connectivity):
        if any(type(node) is not int or not 0 <= node < len(nodes) for node in cell):
            raise ValueError("Native connectivity contains unknown node indices")
        mapped = tuple(external_by_native[node] for node in cell)
        key = (mesh.getCellTypeName(index), mapped, tuple(sorted(memberships[index])))
        source_id = source.get(key)
        if source_id is None or source_id in matched:
            raise ValueError("Native all-cell type/order/group bijection differs from the checked source")
        matched.add(source_id)
        native_cells.append({"native_cell_index": index, "source_cell_id": source_id})
        if key[0] == "HEXA20":
            if source_id not in elements or list(mapped) != [elements[source_id][slot] for slot in ASTER_FROM_CANONICAL]:
                raise ValueError("Native HEXA20 bottom/vertical/top order differs from canonical C3D20")
            volume_mapping.append({"native_cell_index": index, "source_element_id": source_id})
    if matched != {cell["source_cell_id"] for cell in imported["cells"]} or len(volume_mapping) != len(elements):
        raise ValueError("Native cell catalogue is not bijective")
    normalized_groups = {}
    for name, identifiers in expected["groups"].items():
        actual = list(mesh.getNodesFromCells(native_names[name]))
        if len(actual) != len(set(actual)) or any(type(node) is not int or not 0 <= node < len(nodes) for node in actual) or {external_by_native[node] for node in actual} != set(identifiers):
            raise ValueError("Native node group differs from the catalogue")
        normalized_groups[name] = actual
    return {"status": "PASS", "node_count": len(nodes), "volume_element_count": len(elements),
            "total_cell_count": count, "source_node_ids_by_native_index": external_by_native,
            "native_node_index_by_source_id": {str(node): index for node, index in native_by_external.items()},
            "source_element_mapping": volume_mapping, "source_cell_mapping": native_cells,
            "native_group_node_indices": normalized_groups,
            "physical_name_policy": _PHYSICAL_NAME_POLICY,
            "canonical_to_native_group_names": native_names,
            "canonical_physical_group_names": sorted(names),
            "actual_native_physical_group_names": sorted(actual_names),
            "coordinate_tolerances": {"relative": 1e-12, "absolute": 1e-12},
            "topology": "Complete HEXA20/POI1 cell, exact node/group bijection; canonical bottom/top/vertical converted to Aster bottom/vertical/top",
            "solver_gate": "Verified before MECA_STATIQUE"}


def _resultants(nodes: dict, vectors: dict[int, list[float]]) -> tuple[list[float], list[float]]:
    force = [math.fsum(value[axis] for value in vectors.values()) for axis in range(3)]
    moments = []
    for node, value in vectors.items():
        x, y, z = nodes[node]
        fx, fy, fz = value
        moments.append((y * fz - z * fy, z * fx - x * fz, x * fy - y * fx))
    return force, [math.fsum(value[axis] for value in moments) for axis in range(3)]


def parse_field_tables(raw: dict, expected: dict) -> dict:
    """Require every three-component nodal field and all 27 physical Gauss points."""
    nodes, elements = validate_catalogue(expected)
    if not isinstance(raw, dict) or raw.get("schema_version") != "1" or raw.get("solver_status") != "COMPLETED" or raw.get("converged") is not True:
        raise ValueError("Incomplete native family result")
    order = _identifier(raw.get("order"), "order")
    available_orders = raw.get("available_orders")
    if not isinstance(available_orders, list) or any(type(value) is not int for value in available_orders) or available_orders != [order]:
        raise ValueError("Native fields require exactly one actual result order")
    guard = raw.get("native_mesh_checks")
    if not isinstance(guard, dict) or guard.get("status") != "PASS" or guard.get("support_and_load_groups_verified") is not True:
        raise ValueError("Missing native pre-MECA gate")
    native_names = _checked_native_group_name_map(expected)
    if guard.get("physical_name_policy") != _PHYSICAL_NAME_POLICY or guard.get("canonical_to_native_group_names") != native_names or guard.get("canonical_physical_group_names") != sorted(native_names) or guard.get("actual_native_physical_group_names") != sorted(native_names.values()):
        raise ValueError("Native field guard physical name map drifted from the checked source")
    by_native = guard.get("source_node_ids_by_native_index")
    mapping = guard.get("source_element_mapping")
    if not isinstance(by_native, list) or len(by_native) != len(nodes) or len(set(by_native)) != len(nodes) or set(by_native) != set(nodes) or not isinstance(mapping, list):
        raise ValueError("Native/source node mapping is incomplete")
    external_elements = {}
    for row in mapping:
        if not isinstance(row, dict) or type(row.get("native_cell_index")) is not int or row["native_cell_index"] < 0 or row.get("source_element_id") not in elements or row["native_cell_index"] + 1 in external_elements:
            raise ValueError("Native/source element mapping is incomplete")
        external_elements[row["native_cell_index"] + 1] = row["source_element_id"]
    if len(external_elements) != len(elements) or set(external_elements.values()) != set(elements):
        raise ValueError("Native/source element mapping is not bijective")
    catalog = raw.get("native_coordinates_mm")
    if not isinstance(catalog, list) or len(catalog) != len(nodes):
        raise ValueError("Actual native coordinates are missing")
    for index, coordinate in enumerate(catalog):
        coordinate = _vector(coordinate, "actual coordinate")
        if any(not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12) for a, b in zip(coordinate, nodes[by_native[index]])):
            raise ValueError("Native coordinates differ from checked catalogue")
    tables = raw.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("Native field tables are missing")

    def nodal(field):
        table, count = _table(tables.get(field), ("NOEUD", "NUME_ORDRE", *COORDINATE_COMPONENTS, *VECTOR_COMPONENTS), field)
        if count != len(nodes):
            raise ValueError("Every nodal field must cover every source node")
        result = {}
        for row in range(count):
            index = _table_identifier(table["NOEUD"][row], "NOEUD") - 1
            if not 0 <= index < len(nodes) or by_native[index] in result:
                raise ValueError("Duplicate or unknown native node field identifier")
            _field_order(table, row, order, field)
            coordinate = [_finite(table[key][row], "nodal coordinate") for key in COORDINATE_COMPONENTS]
            if any(not math.isclose(a, b, rel_tol=1e-13, abs_tol=1e-13) for a, b in zip(coordinate, catalog[index])):
                raise ValueError("Native nodal table coordinate/index mismatch")
            result[by_native[index]] = [_finite(table[key][row], "nodal component") for key in VECTOR_COMPONENTS]
        if set(result) != set(nodes):
            raise ValueError("Missing source node field rows")
        return result

    displacements, reactions = nodal("DEPL"), nodal("REAC_NODA")
    stress, count = _table(tables.get("SIEF_ELGA"), ("MAILLE", "POINT", "SOUS_POINT", "NUME_ORDRE", *COORDINATE_COMPONENTS, *STRESS_COMPONENTS), "SIEF_ELGA")
    if count != 27 * len(elements):
        raise ValueError("Stress field must cover all 27 HEXA20 integration points per element")
    points, seen = [], set()
    for row in range(count):
        native_element = _table_identifier(stress["MAILLE"][row], "MAILLE")
        point = _identifier(stress["POINT"][row], "POINT")
        subpoint = _identifier(stress["SOUS_POINT"][row], "SOUS_POINT")
        _field_order(stress, row, order, "SIEF_ELGA")
        key = (native_element, point)
        if native_element not in external_elements or not 1 <= point <= 27 or subpoint != 1 or key in seen:
            raise ValueError("Unknown, extra or duplicate native element/Gauss point")
        source_element = external_elements[native_element]
        coordinates = [_finite(stress[key][row], "actual Gauss coordinate") for key in COORDINATE_COMPONENTS]
        physical = [nodes[node] for node in elements[source_element]]
        expected_coordinate = hexa20_point_coordinates(physical, ASTER_GAUSS27[point - 1])
        if any(not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12) for a, b in zip(coordinates, expected_coordinate)):
            raise ValueError("Actual COOR_ELGA coordinate does not match native FPG27 order and checked topology")
        canonical_point = CANONICAL_GAUSS27.index(ASTER_GAUSS27[point - 1]) + 1
        points.append({"element_id": source_element, "point_id": canonical_point,
                       "coordinates_mm": coordinates,
                       "components_mpa": [_finite(stress[key][row], "stress component") for key in STRESS_COMPONENTS]})
        seen.add(key)
    if seen != {(element, point) for element in external_elements for point in range(1, 28)}:
        raise ValueError("Incomplete native FPG27 point coverage")
    # A coordinate bijection independently proves each element's physical point
    # set. Native POINT labels alone can never establish cross-solver agreement.
    for element, connectivity in elements.items():
        actual = [point["coordinates_mm"] for point in points if point["element_id"] == element]
        physical = [nodes[node] for node in connectivity]
        wanted = [list(hexa20_point_coordinates(physical, point)) for point in CANONICAL_GAUSS27]
        if coordinate_bijection(actual, wanted) is None:
            raise ValueError("Native FPG27 physical coordinates have no unique checked bijection")
    restrained = {row["node_id"]: row["components"] for row in expected["supports"]}
    selected = {node: [reactions[node][axis] if axis + 1 in axes else 0.0 for axis in range(3)]
                for node, axes in restrained.items()}
    reaction, reaction_moment = _resultants(nodes, selected)
    applied, applied_moment = _resultants(nodes, {row["node_id"]: row["value"] for row in expected["nodal_loads_n"]})
    identifiers = sorted(nodes)
    native_by_source = {node: index for index, node in enumerate(by_native)}
    return {"cells": deepcopy(expected["cells"]), "node_ids": identifiers,
            "coordinates_mm": [catalog[native_by_source[node]] for node in identifiers],
            "displacements_mm": [displacements[node] for node in identifiers],
            "reaction_n": reaction, "reaction_moment_n_mm": reaction_moment,
            "applied_force_n": applied, "applied_moment_n_mm": applied_moment,
            "stress_points": sorted(points, key=lambda point: (point["element_id"], point["point_id"])),
            "element_count": len(elements), "field_completeness": {"displacement": True, "stress": True, "reaction": True, "native_mesh": True},
            "native_fields_artifact": "simulation/results.med"}


def _assert_sources(output: Path, config: dict) -> None:
    expected = config.get("source_hashes")
    if not isinstance(expected, dict) or set(expected) != set(_SOURCE_FILES):
        raise ValueError("Missing copied native source identity")
    for name, digest in expected.items():
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) or _digest(output.parent / name) != digest:
            raise ValueError("Copied native source hash drifted")


def solve_level(input_path: str) -> None:
    """Run only in the admitted image; pre-MECA failures retain all artifacts."""
    from code_aster.Commands import (AFFE_CHAR_MECA, AFFE_MATERIAU, AFFE_MODELE, CALC_CHAMP,
        CREA_TABLE, DEBUT, DEFI_GROUP, DEFI_MATERIAU, FIN, IMPR_RESU, LIRE_MAILLAGE, MECA_STATIQUE)
    from code_aster.Cata.Syntax import _F

    input_file = Path(input_path)
    input_sha = _digest(input_file)
    config = json.loads(input_file.read_text(encoding="utf-8"))
    output = input_file.parent
    # Refuse collisions or drift before the first native command, independently
    # of the host's source/catalogue preflight. Raw source names stay unchanged.
    try:
        expected_file = output / "expected_mesh.json"
        if _digest(expected_file) != config.get("expected_mesh_sha256") or _digest(input_file) != input_sha:
            raise ValueError("Input or source catalogue drifted before native commands")
        expected = json.loads(expected_file.read_text(encoding="utf-8"))
        validate_catalogue(expected)
        _checked_native_group_name_map(expected)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        _save(output / "native_mesh_checks.json", {"status": "FAIL", "solver_status": "NOT_RUN", "error": str(exc)})
        raise RuntimeError(f"Native family pre-command name guard rejected the source: {exc}") from exc
    DEBUT()  # Initializes run_aster's deferred unit-20 link.
    if not Path("fort.20").is_file() or _digest(Path("fort.20")) != config.get("mesh_sha256"):
        raise RuntimeError("Native unit20 differs from the checked shared Gmsh source")
    versions, runtime = _runtime_versions()
    _save(output / "runtime.json", {"versions": versions, "code_aster_runtime": runtime})
    if versions.get("code_aster") != "17.4.0":
        raise RuntimeError("The native HEXA20 policy requires actual Code_Aster 17.4.0")
    mesh = LIRE_MAILLAGE(FORMAT="GMSH", UNITE=20)
    try:
        _assert_sources(output, config)
        expected_file = output / "expected_mesh.json"
        if _digest(expected_file) != config.get("expected_mesh_sha256") or _digest(input_file) != input_sha:
            raise ValueError("Input or source catalogue drifted before MECA")
        expected = json.loads(expected_file.read_text(encoding="utf-8"))
        checks = validate_native_mesh(mesh, expected)
        # One verified complete node group supplies exact internal ordinals;
        # user/external node IDs are never guessed as native labels.
        mesh = DEFI_GROUP(reuse=mesh, MAILLAGE=mesh, CREA_GROUP_NO=_F(NOM="CAE_ALL", GROUP_MA="SOLID", CRIT_NOEUD="TOUS"))
        all_nodes = list(mesh.getNodes("CAE_ALL"))
        if all_nodes != list(range(checks["node_count"])):
            raise ValueError("Complete native node-group ordering is not the verified internal ordering")
        used = sorted({row["node_id"] for row in expected["supports"]} | {row["node_id"] for row in expected["nodal_loads_n"]})
        source_to_native = checks["native_node_index_by_source_id"]
        definitions = [_F(NOM=f"CAE_N{source_to_native[str(node)]}", GROUP_NO="CAE_ALL",
                          NUME_INIT=source_to_native[str(node)] + 1, NUME_FIN=source_to_native[str(node)] + 1) for node in used]
        mesh = DEFI_GROUP(reuse=mesh, MAILLAGE=mesh, CREA_GROUP_NO=tuple(definitions))
        for node in used:
            index = source_to_native[str(node)]
            if list(mesh.getNodes(f"CAE_N{index}")) != [index]:
                raise ValueError("Native singleton force/support group is not the exact source node")
        checks.update({"support_and_load_groups_verified": True, "expected_mesh_sha256": config["expected_mesh_sha256"],
                       "checked_msh_sha256": config["mesh_sha256"], "input_sha256": input_sha})
        _save(output / "native_mesh_checks.json", checks)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        _save(output / "native_mesh_checks.json", {"status": "FAIL", "solver_status": "NOT_RUN", "error": str(exc)})
        raise RuntimeError(f"Native family pre-MECA guard rejected the import: {exc}") from exc
    material = config.get("material")
    if not isinstance(material, dict) or set(material) != {"youngs_modulus_mpa", "poisson_ratio"}:
        raise ValueError("Trusted numeric material is missing")
    young = _finite(material["youngs_modulus_mpa"], "Young modulus")
    poisson = _finite(material["poisson_ratio"], "Poisson ratio")
    if young <= 0 or not -1 < poisson < 0.5:
        raise ValueError("Trusted material is outside the linear isotropic range")
    model = AFFE_MODELE(MAILLAGE=mesh, AFFE=_F(GROUP_MA="SOLID", PHENOMENE="MECANIQUE", MODELISATION="3D"))
    elastic = DEFI_MATERIAU(ELAS=_F(E=young, NU=poisson))
    material_field = AFFE_MATERIAU(MAILLAGE=mesh, AFFE=_F(GROUP_MA="SOLID", MATER=elastic))
    imposed = tuple(_F(GROUP_NO=f"CAE_N{source_to_native[str(row['node_id'])]}",
                       **{VECTOR_COMPONENTS[axis - 1]: 0.0 for axis in row["components"]}) for row in expected["supports"])
    forces = tuple(_F(GROUP_NO=f"CAE_N{source_to_native[str(row['node_id'])]}",
                      **dict(zip(("FX", "FY", "FZ"), row["value"]))) for row in expected["nodal_loads_n"])
    load = AFFE_CHAR_MECA(MODELE=model, DDL_IMPO=imposed, FORCE_NODALE=forces)
    _assert_sources(output, config)
    if _digest(expected_file) != config["expected_mesh_sha256"] or _digest(input_file) != input_sha:
        raise RuntimeError("Source/input drifted at the final pre-MECA gate")
    result = MECA_STATIQUE(MODELE=model, CHAM_MATER=material_field, EXCIT=_F(CHARGE=load), SOLVEUR=_F(METHODE="MUMPS"))
    result = CALC_CHAMP(reuse=result, RESULTAT=result, FORCE="REAC_NODA")
    indexes = list(result.getIndexes())
    if len(indexes) != 1 or type(indexes[0]) is not int or indexes[0] <= 0:
        raise RuntimeError("Exactly one actual native static result order is required")
    order, tables = indexes[0], {}
    for field, components in (("DEPL", VECTOR_COMPONENTS), ("SIEF_ELGA", STRESS_COMPONENTS), ("REAC_NODA", VECTOR_COMPONENTS)):
        selection = {"GROUP_MA": "SOLID"} if field == "SIEF_ELGA" else {"TOUT": "OUI"}
        table = CREA_TABLE(RESU=_F(RESULTAT=result, NOM_CHAM=field, NUME_ORDRE=order, NOM_CMP=components, **selection))
        tables[field] = table.EXTR_TABLE().values()
        _save(output / f"{field.lower()}.table.json", tables[field])
    IMPR_RESU(FORMAT="MED", UNITE=80, RESU=_F(RESULTAT=result, NOM_CHAM=("DEPL", "SIEF_ELGA", "REAC_NODA"), NUME_ORDRE=order))
    raw = {"schema_version": "1", "solver_status": "COMPLETED", "converged": True,
           "order": order, "available_orders": indexes, "versions": versions, "code_aster_runtime": runtime,
           "input_sha256": input_sha, "mesh_input_sha256": config["mesh_sha256"], "native_mesh_checks": checks,
           "native_coordinates_mm": mesh.getCoordinates().toNumpy().tolist(), "tables": tables,
           "access_parameters": result.getAccessParameters(),
           "linear_solver": {"method": "MUMPS", "measured_linear_residual": None,
                             "residual_status": "UNKNOWN: no assembled A/u/b was exported"}}
    _save(output / "worker_result.json", raw)
    parse_field_tables(raw, expected)  # Incomplete fields remain raw, but cannot be accepted.
    _assert_sources(output, config)
    if _digest(input_file) != input_sha or _digest(expected_file) != config["expected_mesh_sha256"]:
        raise RuntimeError("Native inputs changed during execution; raw evidence preserved")
    FIN()
