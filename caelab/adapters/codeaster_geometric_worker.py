"""Pinned 17.4 finite-rotation SEG2 beam extraction, without a Lab import.

Only generic table/order/runtime primitives are reused from the existing
workers. Beam topology, six DOFs, mixed units and FPG1 coverage are explicit.
Native initial fields are required; missing archives are never synthesized.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
import json
import math
from pathlib import Path
from typing import Any

if __package__:
    from .codeaster_worker import (_field_order, _finite, _identifier, _name,
        _runtime_versions, _save, _table, _table_identifier, _vector,
        coordinate_bijection)
    from .codeaster_plasticity_worker import _order_times
else:
    from codeaster_worker import (_field_order, _finite, _identifier, _name,
        _runtime_versions, _save, _table, _table_identifier, _vector,
        coordinate_bijection)
    from codeaster_plasticity_worker import _order_times


DOF_COMPONENTS = ("DX", "DY", "DZ", "DRX", "DRY", "DRZ")
COORDINATE_COMPONENTS = ("COOR_X", "COOR_Y", "COOR_Z")
WRENCH_COMPONENTS = ("N", "VY", "VZ", "MT", "MFY", "MFZ")
CURVATURE_COMPONENTS = ("V1", "V2", "V3")
COMBINED_COMPONENTS = ("RESULT_X", "RESULT_Y", "RESULT_Z", "MOMENT_X", "MOMENT_Y", "MOMENT_Z")
NONLINEAR_POLICY = {"command": "STAT_NON_LINE", "relation": "ELAS_POUTRE_GR",
    "deformation": "GROT_GDEP", "modelisation": "POU_D_T_GD", "linear_method": "MUMPS",
    "relative_residual_limit": 1e-10, "absolute_residual_limit": 1e-8,
    "maximum_iterations": 40, "archive": "Every declared instant including actual initial zero",
    "automatic_subdivision": False}
FIELD_SEMANTICS = {"displacement_components": list(DOF_COMPONENTS),
    "displacement_units": ["mm", "mm", "mm", "rad", "rad", "rad"],
    "reaction_components": list(DOF_COMPONENTS),
    "reaction_units": ["N", "N", "N", "N.mm", "N.mm", "N.mm"],
    "section_wrench_components": list(WRENCH_COMPONENTS),
    "section_wrench_units": ["N", "N", "N", "N.mm", "N.mm", "N.mm"],
    "section_wrenches_basis": "LOCAL_SECTION", "curvature_components": list(CURVATURE_COMPONENTS),
    "curvatures_basis": "GLOBAL", "curvature_units": ["1/mm"] * 3,
    "initial_local_y": [0., 1., 0.], "native_current_orientation": "UNKNOWN"}


def beam_mesh(length_mm: float, element_count: int) -> dict:
    length = _finite(length_mm, "beam length")
    if length <= 0 or type(element_count) is not int or not 8 <= element_count <= 512:
        raise ValueError("Beam mesh requires a positive length and 8..512 integer SEG2 elements")
    nodes = [{"node_id": index + 1, "name": f"N{index + 1}",
              "coordinates_mm": [length * index / element_count, 0., 0.]}
             for index in range(element_count + 1)]
    elements = [{"element_id": index + 1, "name": f"S{index + 1}",
                 "type": "SEG2", "node_ids": [index + 1, index + 2]}
                for index in range(element_count)]
    all_nodes = [node["node_id"] for node in nodes]
    return {"schema_version": "1", "element_count": element_count, "nodes": nodes,
        "beam_elements": elements,
        "group_node_ids": {"BEAM": all_nodes, "CLAMP": [1], "TIP": [element_count + 1], "SUPPORT": all_nodes},
        "support_dof_masks": {str(node): [True] * 6 if node == 1 else [False, False, True, False, False, False]
                              for node in all_nodes},
        "gauss_point_ids": [1], "subpoint_ids": [1]}


def mail_source(expected: dict) -> str:
    _source_catalog(expected)
    lines = ["TITRE", "Declared finite-rotation pure end-moment beam", "FINSF", "%", "COOR_3D"]
    lines += [f"{node['name']} " + " ".join(f"{value:.17e}" for value in node["coordinates_mm"])
              for node in expected["nodes"]]
    lines += ["FINSF", "%", "SEG2"]
    labels = {node["node_id"]: node["name"] for node in expected["nodes"]}
    lines += [f"{cell['name']} " + " ".join(labels[node] for node in cell["node_ids"])
              for cell in expected["beam_elements"]]
    lines += ["FINSF", "%", "GROUP_MA", "BEAM"]
    lines += [cell["name"] for cell in expected["beam_elements"]]
    lines += ["FINSF", "%"]
    for name, nodes in expected["group_node_ids"].items():
        lines += ["GROUP_NO", name, *[labels[node] for node in nodes], "FINSF", "%"]
    return "\n".join([*lines, "FIN", ""])


def native_section(settings: dict) -> dict:
    height = _finite(settings["beam"]["height_y_mm"], "section HY")
    width = _finite(settings["beam"]["width_z_mm"], "section HZ")
    if min(height, width) <= 0:
        raise ValueError("Native section HY/HZ must be positive")
    return {"POUTRE": {"GROUP_MA": "BEAM", "SECTION": "RECTANGLE",
                        "CARA": ["HY", "HZ"], "VALE": [height, width]},
            "ORIENTATION": {"GROUP_MA": "BEAM", "CARA": "VECT_Y", "VALE": [0., 1., 0.]},
            "native_computed_properties": {"status": "UNKNOWN", "reason": "Native section property field not extracted"}}


def _source_catalog(expected: Any) -> tuple[dict, dict]:
    if not isinstance(expected, dict) or expected.get("schema_version") != "1":
        raise ValueError("Missing checked beam source catalogue")
    nodes, cells = expected.get("nodes"), expected.get("beam_elements")
    if not isinstance(nodes, list) or not isinstance(cells, list) or not cells:
        raise ValueError("Incomplete checked beam source catalogue")
    count = expected.get("element_count")
    if type(count) is not int or not 8 <= count <= 512 or len(cells) != count or len(nodes) != count + 1:
        raise ValueError("Beam source must contain N ordered SEG2 and N+1 nodes")
    coordinates, elements, names = {}, {}, set()
    for node in nodes:
        identifier = _identifier(node.get("node_id"), "source node id")
        name = _name(node.get("name"), "source node name")
        if identifier in coordinates or name in names:
            raise ValueError("Duplicate source beam node identity")
        names.add(name)
        coordinates[identifier] = _vector(node.get("coordinates_mm"), "source XYZ")
    ordered = list(coordinates)
    if (any(point[1:] != [0., 0.] for point in coordinates.values()) or coordinates[ordered[0]][0] != 0. or
            any(coordinates[right][0] <= coordinates[left][0] for left, right in zip(ordered, ordered[1:]))):
        raise ValueError("Source beam must be a straight oriented +X chain")
    names = set()
    for index, cell in enumerate(cells):
        identifier = _identifier(cell.get("element_id"), "source element id")
        name = _name(cell.get("name"), "source element name")
        if (cell.get("type") != "SEG2" or cell.get("node_ids") != ordered[index:index + 2] or
                identifier in elements or name in names):
            raise ValueError("Source beam SEG2 order/type/name bijection is invalid")
        names.add(name)
        elements[identifier] = list(cell["node_ids"])
    groups = {"BEAM": ordered, "CLAMP": ordered[:1], "TIP": ordered[-1:], "SUPPORT": ordered}
    masks = {str(node): [True] * 6 if node == ordered[0] else [False, False, True, False, False, False]
             for node in ordered}
    observed_masks = expected.get("support_dof_masks")
    if (not isinstance(observed_masks, dict) or
            any(not isinstance(row, list) or any(type(value) is not bool for value in row) for row in observed_masks.values()) or
            expected.get("group_node_ids") != groups or observed_masks != masks or
            expected.get("gauss_point_ids") != [1] or expected.get("subpoint_ids") != [1]):
        raise ValueError("Source clamp/planar/support/FPG1 identities are incomplete")
    return coordinates, elements


def validate_native_mesh(mesh: Any, expected: dict) -> tuple[dict, dict]:
    """Before STAT_NON_LINE prove all native nodes/SEG2/groups, including index0."""
    source_nodes, source_elements = _source_catalog(expected)
    points = mesh.getCoordinates().toNumpy().tolist()
    nodes = list(mesh.getNodes())
    if (mesh.getNumberOfNodes() != len(source_nodes) or len(points) != len(source_nodes) or
            len(nodes) != len(points) or any(type(node) is not int for node in nodes) or
            set(nodes) != set(range(len(points)))):
        raise ValueError("Incomplete actual beam node indices/coordinates")
    source_ids = list(source_nodes)
    mapping = coordinate_bijection(points, list(source_nodes.values()))
    if mapping is None:
        raise ValueError("Native beam coordinates have no unique checked 1e-12 bijection")
    source_by_native = [source_ids[index] for index in mapping]
    connectivity = mesh.getConnectivity()
    count = mesh.getNumberOfCells()
    beam = list(mesh.getCells("BEAM"))
    if (count != len(source_elements) or len(connectivity) != count or
            len(beam) != count or any(type(cell) is not int for cell in beam) or
            set(beam) != set(range(count)) or list(mesh.getGroupsOfCells()) != ["BEAM"]):
        raise ValueError("Native beam all-cell/BEAM catalogue is incomplete")
    inverse = {tuple(pair): identifier for identifier, pair in source_elements.items()}
    cells, seen = [], set()
    for index, pair in enumerate(connectivity):
        if (mesh.getCellTypeName(index) != "SEG2" or len(pair) != 2 or
                any(type(node) is not int or not 0 <= node < len(points) for node in pair)):
            raise ValueError("Native beam contains unsupported cell/unknown node index")
        mapped = tuple(source_by_native[node] for node in pair)
        source_id = inverse.get(mapped)
        if source_id is None or source_id in seen:
            raise ValueError("Native ordered SEG2/source-cell bijection is invalid")
        seen.add(source_id)
        cells.append({"element_id": index + 1, "name": str(index + 1), "type": "SEG2",
                      "node_ids": [node + 1 for node in pair], "source_element_id": source_id})
    if seen != set(source_elements):
        raise ValueError("Native SEG2 catalogue omits checked source elements")
    group_names = list(mesh.getGroupsOfNodes())
    if len(group_names) != 4 or set(group_names) != {"BEAM", "CLAMP", "TIP", "SUPPORT"}:
        raise ValueError("Native beam named node groups differ from source")
    groups = {}
    for name, required in expected["group_node_ids"].items():
        indexes = list(mesh.getNodes(name))
        if (len(indexes) != len(required) or len(set(indexes)) != len(indexes) or
                any(type(index) is not int or not 0 <= index < len(points) for index in indexes) or
                {source_by_native[index] for index in indexes} != set(required)):
            raise ValueError(f"Native beam group differs from source: {name}")
        groups[name] = sorted(index + 1 for index in indexes)
    clamp = groups["CLAMP"][0]
    masks = {str(node): [True] * 6 if node == clamp else [False, False, True, False, False, False]
             for node in groups["BEAM"]}
    catalog = {"nodes": [{"node_id": index + 1, "name": str(index + 1), "source_node_id": source_by_native[index],
                         "coordinates_mm": points[index]} for index in sorted(nodes)],
               "beam_elements": cells, "group_node_ids": groups, "support_node_ids": groups["SUPPORT"],
               "support_dof_masks": masks, "gauss_point_ids": [1], "subpoint_ids": [1],
               "table_name_policy": "Pinned CREA_TABLE decimal internal node/cell indices; source .mail labels mapped separately"}
    guard = {"status": "PASS", "node_count": len(nodes), "element_count": count,
             "support_union_verified": True, "support_dof_masks": masks,
             "source_node_ids_by_native_index": source_by_native,
             "source_element_ids_by_native_index": [cell["source_element_id"] for cell in cells],
             "coordinate_tolerances": {"relative": 1e-12, "absolute": 1e-12},
             "solver_gate": "Full ordered SEG2/node/name/group bijection verified before STAT_NON_LINE"}
    return guard, catalog


def _catalog(catalog: Any) -> tuple[dict, dict, dict, dict]:
    if not isinstance(catalog, dict):
        raise ValueError("Missing actual beam catalogue")
    nodes, cells = catalog.get("nodes"), catalog.get("beam_elements")
    if not isinstance(nodes, list) or not isinstance(cells, list) or not cells or len(nodes) != len(cells) + 1:
        raise ValueError("Incomplete actual beam catalogue")
    coordinates, elements = {}, {}
    for node in nodes:
        identifier = _identifier(node.get("node_id"), "node id")
        if _table_identifier(node.get("name"), "NOEUD") != identifier or identifier in coordinates:
            raise ValueError("Duplicate/mismatched actual beam NOEUD identity")
        coordinates[identifier] = _vector(node.get("coordinates_mm"), "actual XYZ")
    ordered = sorted(coordinates, key=lambda node: coordinates[node][0])
    if (coordinates[ordered[0]][0] != 0. or any(point[1:] != [0., 0.] for point in coordinates.values()) or
            any(coordinates[right][0] <= coordinates[left][0] for left, right in zip(ordered, ordered[1:]))):
        raise ValueError("Actual beam coordinates are not a unique straight +X chain")
    expected_pairs = {tuple(ordered[index:index + 2]) for index in range(len(cells))}
    for cell in cells:
        identifier = _identifier(cell.get("element_id"), "element id")
        pair = cell.get("node_ids")
        if (cell.get("type") != "SEG2" or not isinstance(pair, list) or any(type(node) is not int for node in pair) or
                _table_identifier(cell.get("name"), "MAILLE") != identifier or identifier in elements or
                tuple(pair) not in expected_pairs):
            raise ValueError("Actual beam cell name/type/ordered connectivity is invalid")
        elements[identifier] = pair
    if len({tuple(pair) for pair in elements.values()}) != len(cells):
        raise ValueError("Duplicate actual beam segment")
    groups = catalog.get("group_node_ids")
    required = {"BEAM": sorted(coordinates), "CLAMP": ordered[:1], "TIP": ordered[-1:], "SUPPORT": sorted(coordinates)}
    if groups != required or catalog.get("support_node_ids") != required["SUPPORT"]:
        raise ValueError("Actual beam clamp/tip/full deduplicated support groups differ")
    masks = {str(node): [True] * 6 if node == ordered[0] else [False, False, True, False, False, False]
             for node in sorted(coordinates)}
    observed_masks = catalog.get("support_dof_masks")
    if (not isinstance(observed_masks, dict) or
            any(not isinstance(row, list) or any(type(value) is not bool for value in row) for row in observed_masks.values()) or
            observed_masks != masks or catalog.get("gauss_point_ids") != [1] or
            catalog.get("subpoint_ids") != [1]):
        raise ValueError("Actual beam component support masks/FPG1 metadata is incomplete")
    return coordinates, elements, groups, masks


def _identity(table: dict, row: int, order: int, instant: float, label: str) -> None:
    _field_order(table, row, order, label)
    if "INST" in table and _finite(table["INST"][row], label + " instant") != instant:
        raise ValueError("Wrong native beam table instant")


def _field_metadata(table: Any, label: str) -> str:
    values, _ = _table(table, ("RESULTAT", "NOM_CHAM"), label)
    names = {_name(value, label + " RESULTAT") for value in values["RESULTAT"]}
    if len(names) != 1 or {_name(value, label + " NOM_CHAM") for value in values["NOM_CHAM"]} != {label}:
        raise ValueError("Native beam table result/field identity is ambiguous or wrong")
    return next(iter(names))


def _nodal(table: Any, order: int, instant: float, coordinates: dict, label: str) -> dict:
    values, count = _table(table, ("NOEUD", "NUME_ORDRE", *COORDINATE_COMPONENTS, *DOF_COMPONENTS), label)
    if count != len(coordinates):
        raise ValueError(f"{label} must cover every actual node and all six DOFs")
    result = {}
    for row in range(count):
        node = _table_identifier(values["NOEUD"][row], label + " NOEUD")
        if node not in coordinates or node in result:
            raise ValueError("Unknown/duplicate actual beam table node")
        _identity(values, row, order, instant, label)
        observed = [_finite(values[key][row], label + " XYZ") for key in COORDINATE_COMPONENTS]
        if any(not math.isclose(a, b, rel_tol=1e-13, abs_tol=1e-13) for a, b in zip(observed, coordinates[node])):
            raise ValueError("Beam table original coordinates differ from catalogue")
        result[node] = [_finite(values[key][row], label + " component") for key in DOF_COMPONENTS]
    return result


def _gauss(table: Any, components: tuple, order: int, instant: float, coordinates: dict,
           elements: dict, label: str) -> dict:
    values, count = _table(table, ("MAILLE", "POINT", "SOUS_POINT", "NUME_ORDRE",
                                  *COORDINATE_COMPONENTS, *components), label)
    if count != len(elements):
        raise ValueError(f"{label} must cover one FPG1 point of every beam SEG2")
    result = {}
    for row in range(count):
        element = _table_identifier(values["MAILLE"][row], label + " MAILLE")
        if (element not in elements or element in result or
                _identifier(values["POINT"][row], "POINT") != 1 or
                _identifier(values["SOUS_POINT"][row], "SOUS_POINT") != 1):
            raise ValueError("Unknown/duplicate beam FPG1 point or subpoint")
        _identity(values, row, order, instant, label)
        pair = elements[element]
        midpoint = [(coordinates[pair[0]][axis] + coordinates[pair[1]][axis]) / 2 for axis in range(3)]
        observed = [_finite(values[key][row], label + " XYZ") for key in COORDINATE_COMPONENTS]
        if any(not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12) for a, b in zip(observed, midpoint)):
            raise ValueError("Actual beam FPG1 coordinates differ from original segment midpoint")
        result[element] = {"coordinates_mm": observed,
                           "components": [_finite(values[key][row], label + " component") for key in components]}
    return result


def _wrench(reactions: dict, coordinates: dict, nodes: list[int]) -> list[float]:
    forces = [math.fsum(reactions[node][axis] for node in nodes) for axis in range(3)]
    moments = []
    for axis, (left, right) in enumerate(((1, 2), (2, 0), (0, 1))):
        moments.append(math.fsum(coordinates[node][left] * reactions[node][right] -
                                 coordinates[node][right] * reactions[node][left] + reactions[node][axis + 3]
                                 for node in nodes))
    return forces + moments


def parse_history_tables(raw: dict, times_s: list[float]) -> dict:
    if (not isinstance(raw, dict) or raw.get("schema_version") != "1" or
            raw.get("solver_status") != "COMPLETED" or raw.get("converged") is not True or
            raw.get("field_semantics") != FIELD_SEMANTICS or raw.get("nonlinear_policy") != NONLINEAR_POLICY):
        raise ValueError("Incomplete/wrong-basis native finite-rotation beam result")
    pairs = _order_times(raw.get("access_parameters"), raw.get("available_orders"), times_s)
    coordinates, elements, groups, masks = _catalog(raw.get("mesh"))
    states = raw.get("states")
    if not isinstance(states, list) or len(states) != len(pairs):
        raise ValueError("Native beam history must include every requested actual archive, including zero")
    nodes = sorted(coordinates)
    ordered_elements = sorted(elements, key=lambda element: coordinates[elements[element][0]][0])
    parsed, result_name = [], None
    for state, (order, instant) in zip(states, pairs):
        if (not isinstance(state, dict) or type(state.get("order")) is not int or state["order"] != order or
                _finite(state.get("time_s"), "state time") != instant or not isinstance(state.get("tables"), dict)):
            raise ValueError("Native beam state order/time identity differs from actual access parameters")
        tables = state["tables"]
        for name in ("DEPL", "REAC_NODA", "SIEF_ELGA", "VARI_ELGA"):
            observed_result = _field_metadata(tables.get(name), name)
            if result_name is not None and result_name != observed_result:
                raise ValueError("Native beam table result identity changes across fields or archives")
            result_name = observed_result
        displacement = _nodal(tables.get("DEPL"), order, instant, coordinates, "DEPL")
        reactions = _nodal(tables.get("REAC_NODA"), order, instant, coordinates, "REAC_NODA")
        wrenches = _gauss(tables.get("SIEF_ELGA"), WRENCH_COMPONENTS, order, instant, coordinates, elements, "SIEF_ELGA")
        curvature = _gauss(tables.get("VARI_ELGA"), CURVATURE_COMPONENTS, order, instant, coordinates, elements, "VARI_ELGA")
        if any(wrenches[cell]["coordinates_mm"] != curvature[cell]["coordinates_mm"] for cell in elements):
            raise ValueError("Native section wrench/curvature point coordinates disagree")
        post, count = _table(tables.get("BOUNDARY_WRENCHES"),
                            ("INTITULE", "NUME_ORDRE", "INST", *COMBINED_COMPONENTS), "BOUNDARY_WRENCHES")
        if count != 2:
            raise ValueError("Combined reaction table requires CLAMP and complete SUPPORT rows")
        resultants = {}
        for row in range(count):
            name = _name(post["INTITULE"][row], "combined wrench title")
            if name not in ("CLAMP", "SUPPORT") or name in resultants:
                raise ValueError("Unknown/duplicate native combined reaction group")
            _identity(post, row, order, instant, "BOUNDARY_WRENCHES")
            actual = [_finite(post[key][row], "native combined wrench") for key in COMBINED_COMPONENTS]
            direct = _wrench(reactions, coordinates, groups[name])
            # Transcription check only. Scientific force/moment tolerances remain
            # distinct mixed-unit Domain checks, including all unconstrained DOFs.
            if any(not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12) for a, b in zip(actual, direct)):
                raise ValueError("Combined reaction table disagrees with complete deduplicated raw nodal wrench")
            resultants[name] = actual
        constrained = {node: [value if mask else 0. for value, mask in zip(reactions[node], masks[str(node)])]
                       for node in nodes}
        parsed.append({"time_s": instant, "actual_result_order": order,
            "displacements_mm": [displacement[node][:3] for node in nodes],
            "rotations_rad": [displacement[node][3:] for node in nodes],
            "nodal_forces_n": [reactions[node][:3] for node in nodes],
            "nodal_moments_n_mm": [reactions[node][3:] for node in nodes],
            "section_wrenches": [wrenches[cell]["components"] for cell in ordered_elements],
            "curvatures_per_mm": [curvature[cell]["components"] for cell in ordered_elements],
            "integration_point_coordinates_mm": [wrenches[cell]["coordinates_mm"] for cell in ordered_elements],
            "integration_point_identifiers": [{"element_id": cell, "point": 1, "subpoint": 1, "order": order}
                                               for cell in ordered_elements],
            "native_boundary_wrenches": resultants,
            "masked_support_wrench": _wrench(constrained, coordinates, groups["SUPPORT"]),
            "clamp_wrench": _wrench(reactions, coordinates, groups["CLAMP"]),
            "all_node_wrench": _wrench(reactions, coordinates, nodes)})
    return {"element_count": len(elements), "node_ids": nodes,
            "coordinates_mm": [coordinates[node] for node in nodes],
            "segments": [elements[cell] for cell in ordered_elements], "states": parsed,
            "element_ids": ordered_elements, "group_node_ids": groups,
            "native_result_name": result_name,
            "support_node_ids": groups["SUPPORT"], "support_dof_masks": masks,
            "field_semantics": deepcopy(FIELD_SEMANTICS),
            "reaction_method": "Native REAC_NODA all six components; component masks and deduplicated support; no load subtraction"}


def _assert_inputs(input_file: Path, input_sha: str, config: dict) -> None:
    root = input_file.parent.parent
    if hashlib.sha256(input_file.read_bytes()).hexdigest() != input_sha:
        raise RuntimeError("Frozen native beam input drifted")
    for name, digest in config["captured_source_sha256"].items():
        if (not isinstance(name, str) or Path(name).name != name or
                hashlib.sha256((root / name).read_bytes()).hexdigest() != digest):
            raise RuntimeError("Captured native beam source drifted")
    for name, key in (("mesh.mail", "mesh_sha256"), ("expected_mesh.json", "expected_mesh_sha256"),
                      ("model.comm", "comm_sha256"), ("model.export", "export_sha256")):
        if hashlib.sha256((input_file.parent / name).read_bytes()).hexdigest() != config[key]:
            raise RuntimeError("Checked beam mesh/catalogue drifted")


def solve_level(input_path: str) -> None:
    from code_aster.Commands import (AFFE_CARA_ELEM, AFFE_CHAR_MECA, AFFE_MATERIAU, AFFE_MODELE,
        CALC_CHAMP, CREA_TABLE, DEBUT, DEFI_FONCTION, DEFI_LIST_REEL, DEFI_MATERIAU,
        FIN, IMPR_RESU, LIRE_MAILLAGE, POST_RELEVE_T, STAT_NON_LINE)
    from code_aster.Cata.Syntax import _F

    input_file = Path(input_path)
    input_sha = hashlib.sha256(input_file.read_bytes()).hexdigest()
    config = json.loads(input_file.read_text(encoding="utf-8"))
    json.dumps(config, allow_nan=False)
    output, settings = input_file.parent, config["settings"]
    _assert_inputs(input_file, input_sha, config)
    DEBUT()
    mesh_file = Path("fort.20")
    if not mesh_file.is_file() or hashlib.sha256(mesh_file.read_bytes()).hexdigest() != config["mesh_sha256"]:
        raise RuntimeError("Native deferred ASTER unit20 differs from frozen mesh.mail")
    versions, runtime = _runtime_versions()
    _save(output / "runtime.json", {"versions": versions, "code_aster_runtime": runtime})
    if versions.get("code_aster") != "17.4.0":
        raise RuntimeError("Finite-rotation beam requires pinned Code_Aster17.4.0 API")
    mesh = LIRE_MAILLAGE(FORMAT="ASTER", UNITE=20)
    try:
        expected = json.loads((output / "expected_mesh.json").read_text(encoding="utf-8"))
        if expected != beam_mesh(settings["beam"]["length_mm"], config["element_count"]):
            raise ValueError("Source beam catalogue differs from exact declared length/count")
        guard, catalog = validate_native_mesh(mesh, expected)
        guard.update(expected_mesh_sha256=config["expected_mesh_sha256"], checked_mail_sha256=config["mesh_sha256"])
        _save(output / "native_mesh_checks.json", guard)
        _save(output / "mesh_catalog.json", catalog)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        _save(output / "native_mesh_checks.json", {"status": "FAIL", "error": str(exc), "solver_status": "NOT_RUN"})
        raise RuntimeError(f"Native beam mesh rejected before nonlinear solve: {exc}") from exc
    model = AFFE_MODELE(MAILLAGE=mesh, AFFE=_F(GROUP_MA="BEAM", PHENOMENE="MECANIQUE", MODELISATION="POU_D_T_GD"))
    material_spec = {"ELAS": {"E": settings["material"]["youngs_modulus_mpa"], "NU": settings["material"]["poisson_ratio"]}}
    _save(output / "native_material.json", material_spec)
    material = DEFI_MATERIAU(ELAS=_F(**material_spec["ELAS"]))
    field = AFFE_MATERIAU(MAILLAGE=mesh, AFFE=_F(GROUP_MA="BEAM", MATER=material))
    section_spec = native_section(settings)
    _save(output / "native_section.json", section_spec)
    section = AFFE_CARA_ELEM(MODELE=model, POUTRE=_F(**section_spec["POUTRE"]), ORIENTATION=_F(**section_spec["ORIENTATION"]))
    # DZ is imposed exactly once per node; the remaining five clamp components
    # are separate. SUPPORT is the full union, not only the origin clamp.
    fixed = AFFE_CHAR_MECA(MODELE=model, DDL_IMPO=(
        _F(GROUP_NO="BEAM", DZ=0.), _F(GROUP_NO="CLAMP", DX=0., DY=0., DRX=0., DRY=0., DRZ=0.)))
    drive = AFFE_CHAR_MECA(MODELE=model, FORCE_NODALE=_F(GROUP_NO="TIP", MZ=1.))
    history = settings["history"]
    moment = DEFI_FONCTION(NOM_PARA="INST", ABSCISSE=history["times_s"], ORDONNEE=history["moments_n_mm"],
                           INTERPOL="LIN", PROL_GAUCHE="EXCLU", PROL_DROITE="EXCLU")
    increments = DEFI_LIST_REEL(VALE=history["times_s"])
    _save(output / "nonlinear_policy.json", NONLINEAR_POLICY)
    _assert_inputs(input_file, input_sha, config)
    result = STAT_NON_LINE(MODELE=model, CHAM_MATER=field, CARA_ELEM=section,
        EXCIT=(_F(CHARGE=fixed), _F(CHARGE=drive, FONC_MULT=moment)),
        COMPORTEMENT=_F(GROUP_MA="BEAM", RELATION="ELAS_POUTRE_GR", DEFORMATION="GROT_GDEP"),
        INCREMENT=_F(LIST_INST=increments), NEWTON=_F(MATRICE="TANGENTE", REAC_ITER=1),
        CONVERGENCE=_F(RESI_GLOB_RELA=NONLINEAR_POLICY["relative_residual_limit"],
                       RESI_GLOB_MAXI=NONLINEAR_POLICY["absolute_residual_limit"],
                       ITER_GLOB_MAXI=NONLINEAR_POLICY["maximum_iterations"], ARRET="OUI", VERIF="TOUT"),
        SOLVEUR=_F(METHODE="MUMPS"), ARCHIVAGE=_F(LIST_INST=increments), MESURE=_F(TABLE="OUI", UNITE=81), INFO=1)
    _assert_inputs(input_file, input_sha, config)
    result = CALC_CHAMP(reuse=result, RESULTAT=result, FORCE="REAC_NODA")
    access, indexes = result.getAccessParameters(), list(result.getIndexes())
    _save(output / "native_access_parameters.json", {"available_orders": indexes, "access_parameters": access})
    # Preserve native MED and text fields before any subsequent table-layout failure.
    IMPR_RESU(FORMAT="MED", UNITE=80, RESU=_F(RESULTAT=result,
        NOM_CHAM=("DEPL", "REAC_NODA", "SIEF_ELGA", "VARI_ELGA"), TOUT_ORDRE="OUI"))
    IMPR_RESU(FORMAT="RESULTAT", UNITE=8, RESU=_F(RESULTAT=result,
        NOM_CHAM=("DEPL", "REAC_NODA", "SIEF_ELGA", "VARI_ELGA"), TOUT_ORDRE="OUI"))
    pairs = _order_times(access, indexes, history["times_s"])
    states = []
    for order, instant in pairs:
        tables = {}
        for name, components in (("DEPL", DOF_COMPONENTS), ("REAC_NODA", DOF_COMPONENTS),
                                 ("SIEF_ELGA", WRENCH_COMPONENTS), ("VARI_ELGA", CURVATURE_COMPONENTS)):
            selection = {"GROUP_MA": "BEAM"} if name.endswith("ELGA") else {"TOUT": "OUI"}
            table = CREA_TABLE(RESU=_F(RESULTAT=result, NOM_CHAM=name, NUME_ORDRE=order, NOM_CMP=components, **selection))
            tables[name] = table.EXTR_TABLE().values()
            _save(output / f"order_{order}_{name.lower()}.table.json", tables[name])
        combined = POST_RELEVE_T(ACTION=tuple(_F(INTITULE=name, OPERATION="EXTRACTION", REPERE="GLOBAL",
            RESULTAT=result, NOM_CHAM="REAC_NODA", NUME_ORDRE=order, GROUP_NO=name,
            RESULTANTE=DOF_COMPONENTS[:3], MOMENT=DOF_COMPONENTS[3:], POINT=(0., 0., 0.))
            for name in ("CLAMP", "SUPPORT")))
        tables["BOUNDARY_WRENCHES"] = combined.EXTR_TABLE().values()
        _save(output / f"order_{order}_boundary_wrenches.table.json", tables["BOUNDARY_WRENCHES"])
        states.append({"order": order, "time_s": instant, "tables": tables})
        _save(output / "native_history.partial.json", {"solver_status": "COMPLETED", "extraction_status": "PARTIAL",
                                                       "states": states, "access_parameters": access})
        _assert_inputs(input_file, input_sha, config)
    lock = Path("/opt/spack/var/spack/environments/simvia_env/spack.lock")
    libraries = None
    if lock.is_file():
        lock_data = json.loads(lock.read_text(encoding="utf-8"))
        _save(output / "spack.lock.json", lock_data)
        libraries = [{"name": spec.get("name"), "version": spec.get("version"), "hash": digest}
                     for digest, spec in lock_data.get("concrete_specs", {}).items()]
    raw = {"schema_version": "1", "solver_status": "COMPLETED", "converged": True,
        "available_orders": indexes, "access_parameters": access, "states": states, "mesh": catalog,
        "versions": versions, "code_aster_runtime": runtime, "numerical_libraries": libraries,
        "input_sha256": input_sha, "mesh_input_sha256": config["mesh_sha256"],
        "native_mesh_checks": guard, "native_material": material_spec, "native_section": section_spec,
        "nonlinear_policy": NONLINEAR_POLICY, "field_semantics": FIELD_SEMANTICS,
        "native_global_energy": {"status": "UNKNOWN", "reason": "No native global energy field extracted"},
        "measured_linear_residual": None}
    # Validate complete coverage before reporting an extraction completion.
    parse_history_tables(raw, history["times_s"])
    _assert_inputs(input_file, input_sha, config)
    _save(output / "worker_result.json", raw)
    FIN()
