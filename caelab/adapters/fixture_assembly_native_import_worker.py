"""Assembly import observations and body-local comparison, without mechanics.

All Code_Aster imports are confined to run_import. Numeric native indices are
zero-based; sparse source identifiers and optional native labels stay separate.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from types import ModuleType


PERMUTATIONS = {9: (0, 1, 2, 3, 4, 5), 11: (0, 1, 2, 3, 4, 5, 6, 7, 9, 8)}
COORDINATE_ABSOLUTE_MM = 1e-12
SOURCE_COMMIT = "50ebc13c70ee9df62faf93ddcb746a3757b3042a"


def _id(value, *, native=False):
    if type(value) is not int or value < (0 if native else 1):
        raise ValueError("Actual integer index/identifier required")
    return value


def _xyz(value):
    if not isinstance(value, list) or len(value) != 3 or any(
            type(v) not in (int, float) or not math.isfinite(v) for v in value):
        raise ValueError("Complete finite XYZ required")
    return value


def _unique(values, *, native=False):
    if not isinstance(values, list) or not values:
        raise ValueError("Nonempty actual membership required")
    result = [_id(v, native=native) for v in values]
    if len(set(result)) != len(result):
        raise ValueError("Duplicate actual membership")
    return result


def source_catalog(mapping):
    """Selected source quantities only; the qualified bundle owns CAD/quality."""
    if (not isinstance(mapping, dict) or mapping.get("units") != "mm" or
            mapping.get("frame") != "global_assembly_cartesian_mm" or
            type(mapping.get("mesh_size_mm")) not in (int, float) or
            mapping["mesh_size_mm"] not in (3.0, 1.5)):
        raise ValueError("Original assembly mesh frame/profile required")
    nodes = {}
    for node in mapping["nodes"]:
        nid = _id(node["id"])
        if nid in nodes:
            raise ValueError("Duplicate source node")
        nodes[nid] = _xyz(node["xyz_mm"])
    groups, physical, bodies = {}, {}, {}
    for group in mapping["physical_groups"]:
        name, dim, tag = group["name"], group["dim"], _id(group["tag"])
        if type(dim) is not int or dim not in (2, 3) or name in groups or (dim, tag) in physical:
            raise ValueError("Duplicate/unsupported physical group")
        entities = _unique(group["entity_tags"])
        component = group["component_id"]
        if len(entities) != 1 or not isinstance(component, str) or not component:
            raise ValueError("Unique genuine entity/component association required")
        ids = _unique(group["node_ids"])
        if not set(ids) <= nodes.keys():
            raise ValueError("Foreign source group node")
        if dim == 3:
            if component in bodies or group["catalog_face_id"] is not None:
                raise ValueError("Unique source volume/body association required")
            bodies[component] = name
        elif not isinstance(group["catalog_face_id"], str) or not group["catalog_face_id"]:
            raise ValueError("Genuine catalog face association required")
        groups[name] = group
        physical[dim, tag] = group
    if set(groups) != ({f"V{i:04d}" for i in range(1, 8)} |
                       {f"F{i:04d}" for i in range(1, 78)}) or len(bodies) != 7:
        raise ValueError("Complete original seven-volume/77-face scope required")
    if any(g["dim"] != (3 if name.startswith("V") else 2) or
           g["component_id"] not in bodies for name, g in groups.items()):
        raise ValueError("Physical group dimension/body differs")
    elements, group_cells, group_nodes, owners, signatures = {}, {}, {}, {}, set()
    for name in groups:
        group_cells[name], group_nodes[name] = [], set()
    for element in mapping["elements"]:
        eid, kind = _id(element["id"]), element["type"]
        if type(kind) is not int or kind not in PERMUTATIONS or eid in elements:
            raise ValueError("Duplicate/unsupported source element")
        dim = 2 if kind == 9 else 3
        group = physical.get((dim, element["physical_tag"]))
        conn = _unique(element["node_ids"])
        if (group is None or element["dim"] != dim or len(conn) != len(PERMUTATIONS[kind]) or
                not set(conn) <= nodes.keys() or
                element["entity_tag"] != group["entity_tags"][0] or
                element["component_id"] != group["component_id"] or
                element["catalog_face_id"] != group["catalog_face_id"]):
            raise ValueError("Source connectivity/physical/entity/body/face join differs")
        signature = kind, tuple(conn)
        if signature in signatures:
            raise ValueError("Duplicate ordered source cell topology")
        signatures.add(signature)
        for nid in conn:
            if nid in owners and owners[nid] != element["component_id"]:
                raise ValueError("Source nodes shared between bodies")
            owners[nid] = element["component_id"]
        elements[eid] = element
        group_cells[group["name"]].append(eid)
        group_nodes[group["name"]].update(conn)
    if not nodes or set(owners) != set(nodes):
        raise ValueError("Orphan/incomplete source nodes")
    for name, group in groups.items():
        if not group_cells[name] or group_nodes[name] != set(group["node_ids"]):
            raise ValueError("Source physical membership differs from connectivity")
        if group["dim"] == 2 and not group_nodes[name] <= group_nodes[bodies[group["component_id"]]]:
            raise ValueError("Source face does not belong to its volume")
    return {"nodes": nodes, "elements": elements, "groups": groups,
            "bodies": bodies, "group_cells": group_cells, "group_nodes": group_nodes}


def validate_native_catalog(mapping, catalog):
    """Independent host comparison of complete actual import observations."""
    from .codeaster_worker import coordinate_bijection
    source = source_catalog(mapping)
    if (not isinstance(catalog, dict) or type(catalog.get("schema_version")) is not int or catalog.get("schema_version") != 1 or
            catalog.get("index_convention") != "zero_based_native_numeric" or
            catalog.get("units") != "mm"):
        raise ValueError("Unbound native numeric catalogue")
    xyz = catalog["coordinates_mm"]
    indices = _unique(catalog["node_indices"], native=True)
    index_set = set(indices)
    if (len(xyz) != len(source["nodes"]) or len(indices) != len(xyz) or
            set(indices) != set(range(len(xyz))) or type(catalog["node_count"]) is not int or
            catalog["node_count"] != len(xyz)):
        raise ValueError("Incomplete actual native node/index count")
    for point in xyz:
        _xyz(point)
    cells = catalog["cells"]
    if type(catalog["cell_count"]) is not int or catalog["cell_count"] != len(cells) or len(cells) != len(source["elements"]):
        raise ValueError("Incomplete actual native cell count")
    by_index = {}
    for cell in cells:
        index = _id(cell["index"], native=True)
        if index in by_index or index >= len(cells) or cell["type"] not in ("TRIA6", "TETRA10"):
            raise ValueError("Duplicate/unexpected native cell index/type")
        conn = _unique(cell["node_indices"], native=True)
        if len(conn) != (6 if cell["type"] == "TRIA6" else 10) or not set(conn) <= index_set:
            raise ValueError("Incomplete/foreign native connectivity")
        by_index[index] = cell
    if set(by_index) != set(range(len(cells))):
        raise ValueError("Missing actual native cells")
    names = catalog["group_names"]
    cell_groups, node_groups = catalog["group_cell_indices"], catalog["group_node_indices"]
    expected_names = set(source["groups"])
    if (not isinstance(names, list) or len(names) != 84 or len(set(names)) != 84 or
            set(names) != expected_names or set(cell_groups) != expected_names or
            set(node_groups) != expected_names or catalog.get("standalone_node_groups") != {}):
        raise ValueError("Missing/duplicate/unexpected native groups")
    for name in names:
        actual_cells = _unique(cell_groups[name], native=True)
        actual_nodes = _unique(node_groups[name], native=True)
        if not set(actual_cells) <= by_index.keys() or not set(actual_nodes) <= index_set:
            raise ValueError("Foreign native group index")
        connected = set().union(*(set(by_index[i]["node_indices"]) for i in actual_cells))
        if connected != set(actual_nodes) or len(actual_cells) != len(source["group_cells"][name]):
            raise ValueError("Native group membership/connectivity differs")
        wanted_type = "TETRA10" if source["groups"][name]["dim"] == 3 else "TRIA6"
        if any(by_index[i]["type"] != wanted_type for i in actual_cells):
            raise ValueError("Native physical group element type differs")
    native_to_source, body_cells, body_nodes, body_checks = {}, set(), set(), []
    maximum_error = 0.0
    for component, name in source["bodies"].items():
        native_ids, source_ids = sorted(node_groups[name]), sorted(source["group_nodes"][name])
        volume_ids = set(cell_groups[name])
        if body_nodes.intersection(native_ids) or body_cells.intersection(volume_ids):
            raise ValueError("Native volume bodies merged/share indices")
        local = coordinate_bijection([xyz[i] for i in native_ids], [source["nodes"][i] for i in source_ids])
        if local is None:
            raise ValueError("Ambiguous/incomplete body-restricted coordinate bijection")
        for native, relative in zip(native_ids, local):
            source_id = source_ids[relative]
            error = max(abs(a-b) for a, b in zip(xyz[native], source["nodes"][source_id]))
            if error > COORDINATE_ABSOLUTE_MM:
                raise ValueError("Native coordinate error exceeds existing 1e-12 mm")
            maximum_error = max(maximum_error, error)
            native_to_source[native] = source_id
        body_nodes.update(native_ids); body_cells.update(volume_ids)
        body_checks.append({"component_id": component, "volume_group": name,
                            "node_count": len(native_ids), "cell_count": len(volume_ids)})
    if body_nodes != index_set or body_cells != {i for i, c in by_index.items() if c["type"] == "TETRA10"}:
        raise ValueError("Orphan native node/volume cell")
    source_signatures = {}
    for eid, element in source["elements"].items():
        signature = element["type"], tuple(element["node_ids"][i] for i in PERMUTATIONS[element["type"]])
        source_signatures[signature] = eid
    cell_map, used = {}, set()
    for index, cell in by_index.items():
        kind = 9 if cell["type"] == "TRIA6" else 11
        signature = kind, tuple(native_to_source[n] for n in cell["node_indices"])
        eid = source_signatures.get(signature)
        if eid is None or eid in used:
            raise ValueError("Native full ordered connectivity/permutation differs")
        cell_map[index] = eid; used.add(eid)
    if used != set(source["elements"]):
        raise ValueError("Incomplete source/native cell bijection")
    for name in names:
        if ({cell_map[i] for i in cell_groups[name]} != set(source["group_cells"][name]) or
                {native_to_source[i] for i in node_groups[name]} != source["group_nodes"][name]):
            raise ValueError("Native full physical/body/face membership differs")
        group = source["groups"][name]
        if group["dim"] == 2 and not set(node_groups[name]) <= set(node_groups[source["bodies"][group["component_id"]]]):
            raise ValueError("Native face/body association differs")
    labels = catalog["labels"]
    for label, count in (("nodes", len(xyz)), ("cells", len(cells))):
        observed = labels[label]
        if observed["status"] == "UNAVAILABLE":
            if observed["values"] is not None:
                raise ValueError("Unavailable native labels fabricated")
        elif observed["status"] == "OBSERVED":
            values = observed["values"]
            if (not isinstance(values, list) or len(values) != count or
                    any(not isinstance(v, str) or not v.strip() for v in values) or
                    len({v.strip() for v in values}) != count):
                raise ValueError("Incomplete/ambiguous native label/index association")
        else:
            raise ValueError("Native label accessor failed")
    return {"status": "PASS", "scope": "NATIVE_IMPORT_ONLY", "solver_status": "NOT_RUN",
            "decision": "NOT_RELEASED", "node_count": len(xyz), "cell_count": len(cells),
            "group_count": 84, "maximum_coordinate_error_mm": maximum_error,
            "coordinate_absolute_limit_mm": COORDINATE_ABSOLUTE_MM, "bodies": body_checks,
            "source_node_ids_by_native_index": [native_to_source[i] for i in range(len(xyz))],
            "source_element_ids_by_native_index": [cell_map[i] for i in range(len(cells))],
            "element_permutations": {str(k): list(v) for k, v in PERMUTATIONS.items()},
            "ordering_source_commit": SOURCE_COMMIT,
            "compiled_image_source_equivalence": "UNKNOWN"}


def capture_native_catalog(mesh):
    """Observe every API row before host comparison; never rename native IDs."""
    count, cell_count = mesh.getNumberOfNodes(), mesh.getNumberOfCells()
    groups = list(mesh.getGroupsOfCells())
    def labels(attribute):
        try:
            values = getattr(mesh.sdj, attribute).get()
        except AttributeError as exc:
            return {"status": "UNAVAILABLE", "values": None, "reason": str(exc)}
        except Exception as exc:
            return {"status": "ERROR", "values": None, "reason": type(exc).__name__ + ": " + str(exc)}
        if values is None or values == []:
            return {"status": "UNAVAILABLE", "values": None, "reason": "Optional native SD channel absent"}
        return {"status": "OBSERVED", "values": list(values),
                "association": "SD array row is native numeric index; no suffix-derived source ID"}
    connectivity = mesh.getConnectivity()
    return {"schema_version": 1, "index_convention": "zero_based_native_numeric", "units": "mm",
            "node_count": count, "cell_count": cell_count, "node_indices": list(mesh.getNodes()),
            "coordinates_mm": mesh.getCoordinates().toNumpy().tolist(),
            "cells": [{"index": i, "type": mesh.getCellTypeName(i), "node_indices": list(row)}
                      for i, row in enumerate(connectivity)],
            "group_names": groups,
            "group_cell_indices": {g: list(mesh.getCells(g)) for g in groups},
            "group_node_indices": {g: list(mesh.getNodesFromCells(g)) for g in groups},
            "standalone_node_groups": {g: list(mesh.getNodes(g)) for g in mesh.getGroupsOfNodes()},
            "labels": {"nodes": labels("NOMNOE"), "cells": labels("NOMMAI")}}


def _pinned_module(path, pin):
    data = path.read_bytes()
    if {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)} != pin:
        raise RuntimeError("Captured worker/foundation source byte drift")
    module = ModuleType("_assembly_import_foundation")
    module.__file__ = str(path)
    exec(compile(data, str(path), "exec", dont_inherit=True), module.__dict__)
    return module


def run_import(input_path):
    """Pinned vendor process: DEBUT, immutable GMSH import, API capture, FIN."""
    from code_aster.Commands import DEBUT, FIN, LIRE_MAILLAGE
    input_file = Path(input_path)
    input_bytes = input_file.read_bytes()
    config = json.loads(input_bytes.decode("utf-8"))
    output, capsule = input_file.parent, input_file.parent.parent / "capsule"
    foundation = _pinned_module(capsule / "codeaster_worker.py", config["native_sources"]["codeaster_worker.py"])
    self_bytes = Path(__file__).read_bytes()
    self_pin = {"sha256": hashlib.sha256(self_bytes).hexdigest(), "size_bytes": len(self_bytes)}
    if self_pin != config["native_sources"]["fixture_assembly_native_import_worker.py"]:
        raise RuntimeError("Native import worker source byte drift")
    def save(name, value):
        with (output / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(foundation._json_safe(value), sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
    DEBUT()
    mesh_bytes = Path("fort.20").read_bytes()
    observed = {"sha256": hashlib.sha256(mesh_bytes).hexdigest(), "size_bytes": len(mesh_bytes)}
    if observed != config["transport_entry"]:
        raise RuntimeError("Actual unit20 transport bytes differ before LIRE_MAILLAGE")
    versions, runtime = foundation._runtime_versions()
    save("runtime-before.json", {"versions": versions, "code_aster_runtime": runtime})
    if versions.get("code_aster") != "17.4.0":
        raise RuntimeError("Actual Code_Aster17.4.0 required")
    mesh = LIRE_MAILLAGE(FORMAT="GMSH", UNITE=20)
    catalog = capture_native_catalog(mesh)
    save("native-catalog.json", catalog)
    versions_after, runtime_after = foundation._runtime_versions()
    save("runtime-after.json", {"versions": versions_after, "code_aster_runtime": runtime_after})
    if versions_after != versions or runtime_after != runtime:
        raise RuntimeError("Native runtime identity drift during import")
    if input_file.read_bytes() != input_bytes or Path("fort.20").read_bytes() != mesh_bytes:
        raise RuntimeError("Native input bytes drift during import")
    _pinned_module(capsule / "codeaster_worker.py", config["native_sources"]["codeaster_worker.py"])
    if Path(__file__).read_bytes() != self_bytes:
        raise RuntimeError("Native worker source drift during import")
    save("worker-result.json", {"schema_version": 1, "status": "IMPORTED_OBSERVED_NOT_COMPARED",
        "input_entry": {"sha256": hashlib.sha256(input_bytes).hexdigest(), "size_bytes": len(input_bytes)},
        "transport_entry": observed, "native_sources": config["native_sources"],
        "mesh_revision": config["mesh_revision"], "parent": config["parent"], "profile": config["profile"],
        "runtime_before": {"versions": versions, "code_aster_runtime": runtime},
        "runtime_after": {"versions": versions_after, "code_aster_runtime": runtime_after},
        "catalog_entry": {"sha256": hashlib.sha256((output / "native-catalog.json").read_bytes()).hexdigest(),
                          "size_bytes": (output / "native-catalog.json").stat().st_size},
        "solver_status": "NOT_RUN", "converged": None, "decision": "NOT_RELEASED"})
    FIN()
