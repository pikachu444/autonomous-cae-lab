"""Pinned SSNP121A contact worker; native imports occur only in ``solve_level``.

The official unrenumbered MED node indices are retained, including coincident
nodes belonging to different bodies. CREA_TABLE's decimal, one-based indices
are bound to that catalogue rather than interpreted as optional mesh labels.
This module checks identity/completeness; the contact Domain owns verdicts.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

if __package__:
    from .codeaster_worker import (COORDINATE_COMPONENTS, _field_order, _finite,
        _identifier, _json_safe, _name, _runtime_versions, _table, _table_identifier)
else:
    from codeaster_worker import (COORDINATE_COMPONENTS, _field_order, _finite,
        _identifier, _json_safe, _name, _runtime_versions, _table, _table_identifier)


CASE = "ssnp121a_frictionless_patch"
MESH_SHA256 = "825e79a01b983b14b136d4fc2490c2bc40e85ccc25ebd8ae6aa32e88dd544f91"
MESH_INSPECTION_SHA256 = "7398ce4349f076e225e76d1d840d60da1dfe24b57181c1ae1d7b5cfc069d8291"
FROZEN_CATALOG_CANONICAL_SHA256 = "583407113cbf7d20543bf8a2b1f44e2f0ba814281747e160bd0ff84788ace739"
VECTOR_COMPONENTS = ("DX", "DY")
STRESS_COMPONENTS = ("SIXX", "SIYY", "SIZZ", "SIXY")
STRESS_COORDINATE_COMPONENTS = ("COOR_X", "COOR_Y")
GAUSS_POINT_IDS = (1, 2, 3, 4)
BOUNDARY_GROUPS = ("AB", "CD", "EF", "FG", "GH", "HE")
STRESS_WEIGHT_PROVENANCE = {
    "raw_table_column": "COOR_Z", "native_component": "EGGAU2D.W", "unit": "m^2",
    "basis": "Actual D_PLAN COOR_ELGA X/Y/W table; third column is integration weight, not geometric Z",
    "identity_check": "Bilinear QUAD4 Jacobian determinant at the matching RIGI FPG4 point; each Gauss weight is 1",
    "upstream_tag": "17.4.0", "upstream_commit": "50ebc13c70ee9df62faf93ddcb746a3757b3042a",
    "source_chain": ["catalo/cataelem/Elements/meca_d_plan.py: COOR_ELGA/EGGAU2D",
                     "catalo/cataelem/Commons/located_components.py: EGGAU2D X,Y,W",
                     "bibfor/utilitai/ctdata.F90: COOR_ELGA extraction",
                     "bibfor/utilitai/cteltb.F90: third extracted component labelled COOR_Z"],
}
NATIVE_POLICY = {
    "upstream_tag": "17.4.0", "upstream_commit": "50ebc13c70ee9df62faf93ddcb746a3757b3042a",
    "command": "STAT_NON_LINE", "modelisation": "D_PLAN", "relation": "ELAS", "deformation": "PETIT",
    "contact": {"FORMULATION": "CONTINUE", "FROTTEMENT": "SANS", "REAC_GEOM": "CONTROLE",
        "NB_ITER_GEOM": 2, "ALGO_RESO_CONT": "POINT_FIXE", "ALGO_RESO_GEOM": "POINT_FIXE",
        "VERI_NORM": "OUI", "LISSAGE": "NON",
        "ZONE": {"GROUP_MA_ESCL": "AB", "GROUP_MA_MAIT": "EF", "INTEGRATION": "SIMPSON",
            "ORDRE_INT": 4, "ALGO_CONT": "STANDARD", "COEF_CONT": 1000.0, "CONTACT_INIT": "NON",
            "NORMALE": "MAIT", "VECT_MAIT": "AUTO", "VECT_ESCL": "AUTO"}},
    "newton": {"MATRICE": "TANGENTE", "REAC_ITER": 1, "REAC_INCR": 1},
    "convergence": {"ARRET": "OUI", "ITER_GLOB_MAXI": 30, "RESI_GLOB_MAXI": 2e-8},
    "linear_method": "LDLT", "loading_parameter": [0.0, 1.0], "automatic_subdivision": False,
    "ignored_alarm": "CONTACT3_16",
    "alarm_policy_basis": "Exact original ssnp121a.comm; all native alarms/logs retained",
    "legacy_simpson2_equivalence": "UNKNOWN", "measured_linear_residual": None,
}


def validate_settings(settings: Any) -> None:
    """Defensive native admission, without evaluating scientific responses."""
    if not isinstance(settings, dict) or set(settings) != {"case", "material", "top_displacement_m", "limits"}:
        raise ValueError("Unsupported contact settings shape")
    if settings["case"] != CASE:
        raise ValueError("Unsupported contact case")
    material = settings["material"]
    if not isinstance(material, dict) or set(material) != {"youngs_modulus_pa", "poisson_ratio"}:
        raise ValueError("Unsupported contact material shape")
    young = _finite(material["youngs_modulus_pa"], "Young modulus")
    nu = _finite(material["poisson_ratio"], "Poisson ratio")
    delta = _finite(settings["top_displacement_m"], "top displacement")
    if not 1e4 <= young <= 1e9 or nu != 0.0 or not -0.2 <= delta <= -1e-4:
        raise ValueError("Contact input is outside the admitted analytical family")
    limits = settings["limits"]
    if not isinstance(limits, dict) or set(limits) != {"reference_relative", "force_balance_relative"}:
        raise ValueError("Unsupported contact limits shape")
    if (_finite(limits["reference_relative"], "reference limit") != 0.01 or
            _finite(limits["force_balance_relative"], "force-balance limit") != 1e-6):
        raise ValueError("Contact scientific limits differ from the frozen Domain contract")


def _write_new(path: Path, value: Any) -> None:
    """Never overwrite a previously captured native observation."""
    text = json.dumps(_json_safe(value), indent=2, sort_keys=True, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def _frozen_catalog(expected: Any) -> dict:
    if not isinstance(expected, dict) or expected.get("source_sha256") != MESH_SHA256:
        raise ValueError("Missing pinned SSNP121A source catalogue")
    try:
        encoded = json.dumps(expected, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("Malformed pinned source catalogue") from exc
    if hashlib.sha256(encoded).hexdigest() != FROZEN_CATALOG_CANONICAL_SHA256:
        raise ValueError("Frozen source catalogue differs from the sealed official inspection")
    return expected


def _indices(values: Any, upper: int, label: str, *, count: int | None = None) -> list[int]:
    if (not isinstance(values, list) or not values or (count is not None and len(values) != count) or
            any(type(value) is not int or not 0 <= value < upper for value in values) or
            len(set(values)) != len(values)):
        raise ValueError(f"Invalid actual native {label} indices")
    return values


def capture_native_catalog(mesh: Any) -> dict:
    """Capture numeric mesh APIs before any mechanical/contact command."""
    coordinates = mesh.getCoordinates().toNumpy().tolist()
    nodes, count = list(mesh.getNodes()), mesh.getNumberOfNodes()
    if type(count) is not int or count != 313 or len(coordinates) != count:
        raise ValueError("Native contact mesh must contain the original 313 nodes")
    _indices(nodes, count, "node", count=count)
    if nodes != list(range(count)):
        raise ValueError("Native contact node ordering is not the unrenumbered MED ordering")
    cell_count, connectivity = mesh.getNumberOfCells(), mesh.getConnectivity()
    if type(cell_count) is not int or cell_count != 357 or len(connectivity) != cell_count:
        raise ValueError("Native contact mesh must contain all 265 QUAD4 and 92 SEG2 cells")
    cell_names = list(mesh.getGroupsOfCells())
    node_names = list(mesh.getGroupsOfNodes())
    for names in (cell_names, node_names):
        if any(not isinstance(name, str) or name != name.strip() or not name for name in names) or len(set(names)) != len(names):
            raise ValueError("Native mesh has malformed or duplicate group names")
    # Optional human labels are recorded only when the actual Mesh API exposes
    # them. They are never used as CREA_TABLE identifiers or made up from IDs.
    labels = ([mesh.getNodeName(index) for index in nodes] if hasattr(mesh, "getNodeName") else None)
    return {"schema_version": "1", "node_indexing": "ZERO_BASED_CODE_ASTER_UNRENUMBERED",
        "node_ids": nodes, "coordinates_m": coordinates, "native_node_names": labels,
        "cells": [{"cell_id": index, "cell_type": mesh.getCellTypeName(index),
                   "node_ids": list(connectivity[index])} for index in range(cell_count)],
        "group_cell_ids": {name: list(mesh.getCells(name)) for name in cell_names},
        "group_node_ids": {name: list(mesh.getNodes(name)) for name in node_names}}


def validate_mesh_catalog(catalog: Any, expected: Any) -> dict:
    """Verify all original indices, topology, groups and directed normals.

    Native cell ordering may differ from MED level ordering. Each full ordered
    connectivity has one source match; actual native cell IDs remain unchanged.
    Coincident body nodes must not be merged, reordered or coordinate-matched.
    """
    expected = _frozen_catalog(expected)
    if (not isinstance(catalog, dict) or catalog.get("schema_version") != "1" or
            catalog.get("node_indexing") != "ZERO_BASED_CODE_ASTER_UNRENUMBERED"):
        raise ValueError("Missing actual unrenumbered native contact catalogue")
    nodes = _indices(catalog.get("node_ids"), 313, "node", count=313)
    if nodes != list(range(313)):
        raise ValueError("Native node index/order differs from the original MED")
    coordinates = catalog.get("coordinates_m")
    source_coordinates = expected["coordinates_in_native_order"]
    if not isinstance(coordinates, list) or len(coordinates) != 313:
        raise ValueError("Incomplete native contact coordinates")
    for actual, source in zip(coordinates, source_coordinates):
        if not isinstance(actual, list) or len(actual) != 3:
            raise ValueError("Native contact coordinates require XYZ components")
        values = [_finite(value, "native coordinate") for value in actual]
        if values != [*source, 0.0]:
            raise ValueError("Native coordinate/origin/index drift from the exact MED doubles")
    labels = catalog.get("native_node_names")
    if labels is not None and labels != expected["node_name_field"]:
        raise ValueError("Actual native node labels differ from the MED label field")
    cells = catalog.get("cells")
    if not isinstance(cells, list) or len(cells) != 357:
        raise ValueError("Incomplete native contact cell catalogue")
    source_cells = {}
    source_groups = {}
    for level, cell_type in (("0", "QUAD4"), ("-1", "SEG2")):
        data = expected["levels"][level]
        for index, connectivity in enumerate(data["cell_connectivity_in_native_order"]):
            source_cells[(cell_type, tuple(connectivity))] = (level, index)
        for name, group in data["groups"].items():
            source_groups[name] = {(level, index) for index in group["cell_ids"]}
    if len(source_cells) != 357:
        raise ValueError("Frozen MED contains ambiguous ordered connectivity")
    mapping, native_cells = {}, {}
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict) or type(cell.get("cell_id")) is not int or cell["cell_id"] != index:
            raise ValueError("Duplicate, missing or reordered native cell index")
        cell_type = cell.get("cell_type")
        if cell_type not in ("QUAD4", "SEG2"):
            raise ValueError("Unsupported native contact cell type")
        connectivity = _indices(cell.get("node_ids"), 313, "cell node", count=4 if cell_type == "QUAD4" else 2)
        key = (cell_type, tuple(connectivity))
        match = source_cells.get(key)
        if match is None or match in mapping.values():
            raise ValueError("Native cell connectivity/direction differs from the frozen MED")
        mapping[index] = match
        native_cells[index] = cell
    group_cells = catalog.get("group_cell_ids")
    if not isinstance(group_cells, dict) or set(group_cells) != set(source_groups):
        raise ValueError("Actual native material/boundary groups differ from the MED")
    boundary_nodes = {}
    for name, source_set in source_groups.items():
        actual = _indices(group_cells[name], 357, name + " cell", count=len(source_set))
        if {mapping[index] for index in actual} != source_set:
            raise ValueError(f"Native {name} group does not contain the original directed cells")
        if name not in ("PLAQUE1", "PLAQUE2"):
            boundary_nodes[name] = sorted({node for cell in actual for node in native_cells[cell]["node_ids"]})
    group_nodes = catalog.get("group_node_ids")
    original_groups = expected["node_groups"]
    if not isinstance(group_nodes, dict) or set(group_nodes) not in (
            set(original_groups), set(original_groups) | set(BOUNDARY_GROUPS)):
        raise ValueError("Native named-node groups are incomplete or contain unexpected groups")
    for name, source in original_groups.items():
        actual = _indices(group_nodes[name], 313, name + " node", count=len(source["node_ids"]))
        if set(actual) != set(source["node_ids"]):
            raise ValueError(f"Native named-node group {name} drifted")
    for name in BOUNDARY_GROUPS:
        if name in group_nodes and set(_indices(group_nodes[name], 313, name + " node")) != set(boundary_nodes[name]):
            raise ValueError(f"Generated native {name} node group differs from its directed cells")
    normals = {}
    for name, expected_normal in (("AB", [0.0, -1.0, 0.0]), ("EF", [0.0, 1.0, 0.0])):
        directed = []
        for cell in group_cells[name]:
            a, b = [coordinates[node] for node in native_cells[cell]["node_ids"]]
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            normal = [dy / length, -dx / length, 0.0] if length else None
            if normal != expected_normal:
                raise ValueError(f"Native {name} contact normal/orientation differs from the source")
            directed.append(normal)
        normals[name] = directed
    if set(boundary_nodes["AB"]) & set(boundary_nodes["EF"]):
        raise ValueError("The separate slave/master interface nodes were merged")
    return {"status": "PASS", "node_count": 313, "body_element_count": 265, "boundary_element_count": 92,
        "total_cell_count": 357, "node_indexing": catalog["node_indexing"],
        "coordinate_policy": "Exact original MED double values in original numeric order; no snapping",
        "source_cell_mapping": [{"native_cell_id": index, "source_level": level, "source_cell_id": cell}
                                for index, (level, cell) in mapping.items()],
        "boundary_node_ids": boundary_nodes, "normal_vectors_xyz": normals,
        "normal_basis": "Derived from exact directed source/native SEG2 geometry, not solver output",
        "solver_gate": "Verified before AFFE_MODELE, DEFI_CONTACT and STAT_NON_LINE"}


def validate_native_mesh(mesh: Any, expected: Any) -> dict:
    return validate_mesh_catalog(capture_native_catalog(mesh), expected)


def _final_order(access: Any, indexes: Any) -> int:
    if not isinstance(access, dict) or not isinstance(indexes, list) or len(indexes) not in (1, 2):
        raise ValueError("Missing actual native contact result access/index identity")
    orders, instants = access.get("NUME_ORDRE"), access.get("INST")
    if (any(type(index) is not int or index < 0 for index in indexes) or len(set(indexes)) != len(indexes) or
            not isinstance(orders, list) or not isinstance(instants, list) or
            len(orders) != len(indexes) or len(instants) != len(indexes) or
            any(type(order) is not int or order < 0 for order in orders) or len(set(orders)) != len(orders) or
            set(orders) != set(indexes)):
        raise ValueError("Native order/time/index mapping is incomplete or duplicated")
    mapping = dict(zip(orders, [_finite(value, "native load parameter") for value in instants]))
    if mapping not in ({1: 1.0}, {0: 0.0, 1: 1.0}):
        raise ValueError("Native contact result differs from the original final order1/INST1")
    return 1


def _nodal(table: Any, components: tuple[str, ...], order: int, coordinates: list,
           expected_nodes: list[int], label: str) -> tuple[dict, dict]:
    table, count = _table(table, ("NOEUD", "NUME_ORDRE", *COORDINATE_COMPONENTS, *components), label)
    if count != len(expected_nodes):
        raise ValueError(f"{label} must cover every required native node exactly once")
    values, raw_names = {}, {}
    for row in range(count):
        node = _table_identifier(table["NOEUD"][row], label + " NOEUD") - 1
        if node not in expected_nodes or node in values:
            raise ValueError(f"Unknown or duplicate actual native node in {label}")
        _field_order(table, row, order, label)
        if "INST" in table and _finite(table["INST"][row], label + " instant") != 1.0:
            raise ValueError(f"Wrong native final instant in {label}")
        actual = [_finite(table[key][row], label + " coordinate") for key in COORDINATE_COMPONENTS]
        if any(not math.isclose(a, b, rel_tol=1e-13, abs_tol=1e-13) for a, b in zip(actual, coordinates[node])):
            raise ValueError(f"Native table index/coordinate identity drift in {label}")
        values[node] = [_finite(table[key][row], label + " component") for key in components]
        raw_names[node] = table["NOEUD"][row]
    return values, raw_names


def _quad_gauss_geometry(corners: list[list[float]]) -> list[tuple[list[float], float]]:
    """Expected measured XY and integration W from exact native QUAD4 geometry.

    The pinned D_PLAN/RIGI COOR_ELGA catalogue is EGGAU2D(X,Y,W).
    CREA_TABLE labels W as COOR_Z; it does not measure geometric Z here.
    """
    abscissa = 1.0 / math.sqrt(3.0)
    result = []
    for xi, eta in ((-abscissa, -abscissa), (abscissa, -abscissa),
                    (abscissa, abscissa), (-abscissa, abscissa)):
        shape = [(1 - xi) * (1 - eta) / 4, (1 + xi) * (1 - eta) / 4,
                 (1 + xi) * (1 + eta) / 4, (1 - xi) * (1 + eta) / 4]
        dxi = [-(1 - eta) / 4, (1 - eta) / 4, (1 + eta) / 4, -(1 + eta) / 4]
        deta = [-(1 - xi) / 4, -(1 + xi) / 4, (1 + xi) / 4, (1 - xi) / 4]
        xy = [math.fsum(value * point[axis] for value, point in zip(shape, corners)) for axis in range(2)]
        dx_dxi, dy_dxi = [math.fsum(value * point[axis] for value, point in zip(dxi, corners)) for axis in range(2)]
        dx_deta, dy_deta = [math.fsum(value * point[axis] for value, point in zip(deta, corners)) for axis in range(2)]
        weight = dx_dxi * dy_deta - dx_deta * dy_dxi
        if not math.isfinite(weight) or weight <= 0:
            raise ValueError("Invalid actual QUAD4 Gauss integration weight geometry")
        result.append((xy, weight))
    return result


def _stress(table: Any, order: int, catalog: dict) -> dict:
    values, count = _table(table, ("MAILLE", "POINT", "SOUS_POINT", "NUME_ORDRE",
                                  *COORDINATE_COMPONENTS, *STRESS_COMPONENTS), "SIEF_ELGA")
    body = {index for group in ("PLAQUE1", "PLAQUE2") for index in catalog["group_cell_ids"][group]}
    if count != len(body) * 4:
        raise ValueError("SIEF_ELGA must cover all four RIGI points of every actual body QUAD4")
    coordinates = catalog["coordinates_m"]
    cells = catalog["cells"]
    rows, coordinate_matches = {}, {cell: set() for cell in body}
    gauss = {cell: _quad_gauss_geometry([coordinates[node] for node in cells[cell]["node_ids"]]) for cell in body}
    for row in range(count):
        cell = _table_identifier(values["MAILLE"][row], "SIEF_ELGA MAILLE") - 1
        point = _identifier(values["POINT"][row], "SIEF_ELGA point")
        subpoint = _identifier(values["SOUS_POINT"][row], "SIEF_ELGA subpoint")
        key = (cell, point, subpoint)
        if cell not in body or point not in GAUSS_POINT_IDS or subpoint != 1 or key in rows:
            raise ValueError("Unknown or duplicate native QUAD4 element-point-subpoint")
        _field_order(values, row, order, "SIEF_ELGA")
        if "INST" in values and _finite(values["INST"][row], "stress instant") != 1.0:
            raise ValueError("Wrong native final stress instant")
        observed = [_finite(values[name][row], "stress point XY coordinate") for name in STRESS_COORDINATE_COMPONENTS]
        matching = [index for index, (expected, _) in enumerate(gauss[cell]) if all(
            math.isclose(a, b, rel_tol=1e-13, abs_tol=1e-13) for a, b in zip(observed, expected))]
        if len(matching) != 1 or matching[0] != point - 1 or matching[0] in coordinate_matches[cell]:
            raise ValueError("Stress point XY/index identity does not cover the actual four QUAD4 Gauss locations")
        weight = _finite(values["COOR_Z"][row], "stress integration weight W")
        if weight <= 0 or not math.isclose(weight, gauss[cell][matching[0]][1], rel_tol=1e-13, abs_tol=1e-13):
            raise ValueError("Stress integration weight W differs from the actual QUAD4 Gauss Jacobian")
        coordinate_matches[cell].add(matching[0])
        rows[key] = {"coordinates_m": observed, "integration_weight_m2": weight,
                     "values_pa": [_finite(values[name][row], "stress component") for name in STRESS_COMPONENTS],
                     "raw_element_identifier": values["MAILLE"][row]}
    return rows


def _projected_gaps(catalog: dict, displacement: dict, slave_nodes: list[int]) -> list[float] | None:
    """Signed closest projections on actual displaced directed master segments.

    This is a geometric derivation, not the solver's pairing/gap variable.
    Positive means separation along the master segment's outward right normal.
    """
    coordinates = catalog["coordinates_m"]
    deformed = {node: [coordinates[node][axis] + displacement[node][axis] for axis in range(2)]
                for node in catalog["node_ids"]}
    master = [catalog["cells"][cell]["node_ids"] for cell in catalog["group_cell_ids"]["EF"]]
    gaps = []
    for node in slave_nodes:
        point = deformed[node]
        candidates = []
        for ids in master:
            a, b = (deformed[index] for index in ids)
            dx, dy = b[0] - a[0], b[1] - a[1]
            length_squared = dx * dx + dy * dy
            if not math.isfinite(length_squared) or length_squared <= 0:
                return None
            fraction = max(0.0, min(1.0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length_squared))
            offset = [point[0] - (a[0] + fraction * dx), point[1] - (a[1] + fraction * dy)]
            gap = (offset[0] * dy - offset[1] * dx) / math.sqrt(length_squared)
            candidates.append((math.fsum(value * value for value in offset), gap))
        gaps.append(min(candidates, key=lambda pair: pair[0])[1])
    return gaps


def parse_contact_tables(raw: dict) -> dict:
    """Return complete observed fields; never substitute stress for LAGS_C."""
    if (not isinstance(raw, dict) or raw.get("schema_version") != "1" or
            raw.get("solver_status") != "COMPLETED" or raw.get("converged") is not True):
        raise ValueError("Incomplete native contact result")
    if raw.get("mesh_input_sha256") != MESH_SHA256 or raw.get("mesh_inspection_sha256") != MESH_INSPECTION_SHA256:
        raise ValueError("Native contact input/catalogue identity differs from the fixed source")
    if not isinstance(raw.get("input_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", raw["input_sha256"]):
        raise ValueError("Missing actual native contact input digest")
    order = _final_order(raw.get("access_parameters"), raw.get("available_orders"))
    if type(raw.get("order")) is not int or raw["order"] != order:
        raise ValueError("Native contact table selection differs from final access order")
    catalog = raw.get("mesh")
    guard = validate_mesh_catalog(catalog, raw.get("frozen_mesh"))
    tables = raw.get("native_tables")
    if not isinstance(tables, dict):
        raise ValueError("Missing original native contact tables")
    nodes, coordinates = catalog["node_ids"], catalog["coordinates_m"]
    displacement, names = _nodal(tables.get("DEPL"), VECTOR_COMPONENTS, order, coordinates, nodes, "DEPL")
    reactions, reaction_names = _nodal(tables.get("REAC_NODA"), VECTOR_COMPONENTS, order, coordinates, nodes, "REAC_NODA")
    slave_nodes = guard["boundary_node_ids"]["AB"]
    pressure, pressure_names = _nodal(tables.get("LAGS_C"), ("LAGS_C",), order, coordinates, slave_nodes, "LAGS_C")
    stress = _stress(tables.get("SIEF_ELGA"), order, catalog)
    samples = {}
    for name in ("A", "B", "N14"):
        node = catalog["group_node_ids"][name][0]
        if node not in pressure:
            raise ValueError("Published sample is not an actual slave contact node")
        samples[name] = {"node_id": node, "raw_node_identifier": pressure_names[node],
                         "normal_traction_pa": pressure[node][0], "vertical_displacement_m": displacement[node][1]}
    resultants = {name: [math.fsum(reactions[node][axis] for node in indices) for axis in range(2)]
                  for name, indices in (("top", guard["boundary_node_ids"]["CD"]),
                                        ("bottom", guard["boundary_node_ids"]["GH"]), ("all_nodes", nodes))}
    stress_keys = sorted(stress)
    return {"samples": samples, "boundary_reactions_n_per_m": resultants,
        "slave_contact": {"node_ids": slave_nodes, "normal_traction_pa": [pressure[node][0] for node in slave_nodes],
                          "raw_node_identifiers": [pressure_names[node] for node in slave_nodes],
                          "unit": "Pa", "source_field": "DEPL.LAGS_C", "sign": "Native signed normal traction retained"},
        "fields": {"node_indexing": "ZERO_BASED_CODE_ASTER_UNRENUMBERED", "actual_result_order": order,
            "load_parameter": 1.0, "node_ids": nodes, "coordinates_m": coordinates,
            "raw_node_identifiers": [names[node] for node in nodes],
            "raw_reaction_node_identifiers": [reaction_names[node] for node in nodes],
            "displacement_component_order": ["dx", "dy"], "displacements_m": [displacement[node] for node in nodes],
            "nodal_reactions_n_per_m": [reactions[node] for node in nodes],
            "stress_component_order": ["xx", "yy", "zz", "xy"],
            "stresses_pa": [stress[key]["values_pa"] for key in stress_keys],
            "stress_point_coordinates_m": [stress[key]["coordinates_m"] for key in stress_keys],
            "stress_coordinate_component_order": ["x", "y"],
            "stress_geometric_z_m": None, "stress_geometric_z_status": "UNAVAILABLE; native EGGAU2D measures X/Y/W",
            "stress_integration_weights_m2": [stress[key]["integration_weight_m2"] for key in stress_keys],
            "stress_integration_weight_provenance": dict(STRESS_WEIGHT_PROVENANCE),
            "stress_point_order": "Actual POINT1..4 correspond to (-xi,-eta),(xi,-eta),(xi,eta),(-xi,eta); xi=eta=1/sqrt(3)",
            "stress_identifiers": [{"cell_id": key[0], "point": key[1], "subpoint": key[2], "order": order,
                "raw_element_identifier": stress[key]["raw_element_identifier"]} for key in stress_keys]},
        "projected_gaps_m": _projected_gaps(catalog, displacement, slave_nodes),
        "projected_gap_node_ids": slave_nodes,
        "projected_gap_method": "DERIVED closest projection on actual displaced piecewise-linear EF master segments; not native contact pairing/gap",
        "native_gap_m": None, "native_gap_status": "UNAVAILABLE; no native gap variable has been claimed",
        "reaction_method": "Sum each DX/DY REAC_NODA once over actual CD, GH and complete native nodes; D_PLAN unit thickness"}


def solve_level(input_path: str) -> None:
    input_file = Path(input_path)
    input_bytes = input_file.read_bytes()
    input_sha256 = hashlib.sha256(input_bytes).hexdigest()
    config = json.loads(input_bytes.decode("utf-8"))
    if not isinstance(config, dict) or set(config) != {"settings", "mesh_sha256", "mesh_inspection_sha256"}:
        raise ValueError("Unsupported contact worker input envelope")
    validate_settings(config["settings"])
    if config["mesh_sha256"] != MESH_SHA256 or config["mesh_inspection_sha256"] != MESH_INSPECTION_SHA256:
        raise ValueError("Unsupported contact source mesh/catalogue digest")
    output, settings = input_file.parent, config["settings"]
    mesh_file = output / "mesh.mmed"
    frozen_file = output.parent / "frozen_mesh.json"
    if hashlib.sha256(mesh_file.read_bytes()).hexdigest() != MESH_SHA256:
        raise ValueError("Level mesh.mmed differs from the pinned official MED")
    if hashlib.sha256(frozen_file.read_bytes()).hexdigest() != MESH_INSPECTION_SHA256:
        raise ValueError("Captured frozen_mesh.json differs from the sealed inspection bytes")
    expected = _frozen_catalog(json.loads(frozen_file.read_text(encoding="utf-8")))

    from code_aster.Commands import (AFFE_CHAR_MECA, AFFE_MATERIAU, AFFE_MODELE,
        CALC_CHAMP, CREA_TABLE, DEBUT, DEFI_CONTACT, DEFI_FONCTION, DEFI_GROUP,
        DEFI_LIST_REEL, DEFI_MATERIAU, FIN, IMPR_RESU, LIRE_MAILLAGE, STAT_NON_LINE)
    from code_aster.Cata.Syntax import _F

    DEBUT(CODE="OUI", ERREUR=_F(ALARME="ALARME"), IGNORE_ALARM="CONTACT3_16", DEBUG=_F(SDVERI="OUI"))
    deferred = Path("fort.20")
    if not deferred.is_file() or hashlib.sha256(deferred.read_bytes()).hexdigest() != MESH_SHA256:
        raise RuntimeError("Actual deferred unit20 differs from the pinned official MED")
    versions, runtime = _runtime_versions()
    _write_new(output / "runtime.json", {"versions": versions, "code_aster_runtime": runtime})
    if versions.get("code_aster") != "17.4.0":
        raise RuntimeError("Contact worker requires the exact pinned native17.4.0 API")
    mesh = LIRE_MAILLAGE(FORMAT="MED", UNITE=20)
    try:
        guard = validate_native_mesh(mesh, expected)
        mesh = DEFI_GROUP(reuse=mesh, MAILLAGE=mesh,
                          CREA_GROUP_NO=tuple(_F(GROUP_MA=name) for name in BOUNDARY_GROUPS))
        catalog = capture_native_catalog(mesh)
        guard = validate_mesh_catalog(catalog, expected)
        if not set(BOUNDARY_GROUPS) <= catalog["group_node_ids"].keys():
            raise ValueError("DEFI_GROUP did not create every original boundary node group")
        guard.update({"mesh_sha256": MESH_SHA256, "mesh_inspection_sha256": MESH_INSPECTION_SHA256,
                      "generated_boundary_groups_verified": True})
    except (ValueError, TypeError, KeyError, OSError) as exc:
        _write_new(output / "native_mesh_checks.json", {"status": "FAIL", "error": str(exc), "solver_status": "NOT_RUN"})
        raise RuntimeError(f"Native contact mesh guard rejected input before mechanical/contact solve: {exc}") from exc
    _write_new(output / "native_mesh_checks.json", guard)
    _write_new(output / "mesh_catalog.json", catalog)
    _write_new(output / "native_policy.json", NATIVE_POLICY)
    model = AFFE_MODELE(MAILLAGE=mesh, AFFE=_F(TOUT="OUI", PHENOMENE="MECANIQUE", MODELISATION="D_PLAN"))
    material_spec = {"ELAS": {"E": settings["material"]["youngs_modulus_pa"], "NU": settings["material"]["poisson_ratio"]},
                     "assignment": {"PLAQUE1": "MAT2", "PLAQUE2": "MAT1"}, "unit": "Pa"}
    _write_new(output / "native_material.json", material_spec)
    mat2 = DEFI_MATERIAU(ELAS=_F(**material_spec["ELAS"]))
    mat1 = DEFI_MATERIAU(ELAS=_F(**material_spec["ELAS"]))
    materials = AFFE_MATERIAU(MAILLAGE=mesh, AFFE=(_F(GROUP_MA="PLAQUE1", MATER=mat2), _F(GROUP_MA="PLAQUE2", MATER=mat1)))
    drive = AFFE_CHAR_MECA(MODELE=model, DDL_IMPO=(
        _F(GROUP_NO="CD", DX=0.0, DY=settings["top_displacement_m"]), _F(GROUP_NO="GH", DX=0.0, DY=0.0)))
    contact_spec = NATIVE_POLICY["contact"]
    contact = DEFI_CONTACT(MODELE=model, **{name: value for name, value in contact_spec.items() if name != "ZONE"},
                           ZONE=_F(**contact_spec["ZONE"]))
    increments = DEFI_LIST_REEL(DEBUT=0.0, INTERVALLE=_F(JUSQU_A=1.0, NOMBRE=1))
    ramp = DEFI_FONCTION(NOM_PARA="INST", VALE=(0.0, 0.0, 1.0, 1.0))
    result = STAT_NON_LINE(MODELE=model, CHAM_MATER=materials,
        INCREMENT=_F(LIST_INST=increments, NUME_INST_FIN=1), EXCIT=(_F(CHARGE=drive, FONC_MULT=ramp),),
        CONTACT=contact, COMPORTEMENT=_F(RELATION="ELAS", DEFORMATION="PETIT"),
        NEWTON=_F(**NATIVE_POLICY["newton"]), CONVERGENCE=_F(**NATIVE_POLICY["convergence"]),
        SOLVEUR=_F(METHODE="LDLT"))
    result = CALC_CHAMP(reuse=result, RESULTAT=result, FORCE="REAC_NODA")
    access = _json_safe(result.getAccessParameters())
    indexes = _json_safe(list(result.getIndexes()))
    order = _final_order(access, indexes)
    _write_new(output / "native_access_parameters.json", {"access_parameters": access, "available_orders": indexes})
    tables = {}
    for name, components in (("DEPL", VECTOR_COMPONENTS), ("REAC_NODA", VECTOR_COMPONENTS),
                             ("SIEF_ELGA", STRESS_COMPONENTS), ("LAGS_C", ("LAGS_C",))):
        selection = ({"GROUP_MA": ("PLAQUE1", "PLAQUE2")} if name == "SIEF_ELGA" else
                     {"GROUP_NO": "AB"} if name == "LAGS_C" else {"TOUT": "OUI"})
        native_name = "DEPL" if name == "LAGS_C" else name
        table = CREA_TABLE(RESU=_F(RESULTAT=result, NOM_CHAM=native_name, NUME_ORDRE=order, NOM_CMP=components, **selection))
        tables[name] = _json_safe(table.EXTR_TABLE().values())
        _write_new(output / f"order_{order}_{name.lower()}.table.json", tables[name])
    if input_file.read_bytes() != input_bytes:
        raise RuntimeError("Contact input bytes changed after native model admission; retained tables are not qualified")
    raw = {"schema_version": "1", "solver_status": "COMPLETED", "converged": True, "order": order,
        "input_sha256": input_sha256, "mesh_input_sha256": MESH_SHA256,
        "mesh_inspection_sha256": MESH_INSPECTION_SHA256, "versions": versions, "code_aster_runtime": runtime,
        "native_policy": NATIVE_POLICY, "native_material": material_spec, "native_mesh_checks": guard,
        "access_parameters": access, "available_orders": indexes, "native_tables": tables,
        "mesh": catalog, "frozen_mesh": expected,
        "convergence_evidence": "STAT_NON_LINE returned under original ARRET OUI/absolute2e-8; .mess histories are parsed separately after process exit",
        "measured_linear_residual": None}
    # Tables are already retained if this strict parser refuses the extraction.
    raw["observation"] = parse_contact_tables(raw)
    IMPR_RESU(FORMAT="MED", UNITE=80,
              RESU=_F(RESULTAT=result, NOM_CHAM=("DEPL", "SIEF_ELGA", "REAC_NODA"), NUME_ORDRE=order))
    IMPR_RESU(FORMAT="RESULTAT", UNITE=8,
              RESU=_F(RESULTAT=result, NOM_CHAM=("DEPL", "SIEF_ELGA", "REAC_NODA"), NUME_ORDRE=order))
    _write_new(output / "worker_result.json", raw)
    FIN()
