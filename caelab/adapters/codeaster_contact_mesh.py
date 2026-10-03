"""Two admitted contact meshes; deterministic topology, deferred native MED I/O.

Generator source is stable. Refined byte/canonical pins live in a separately
sealed profile asset, never in a circular hash of this generator's own source.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import struct


VARIANT = "uniform_quad4_2x"
PROFILE_NAME = "ssnp121a-17.4.0.uniform_quad4_2x.profile.json"
ORIGINAL = {
    "variant": None, "mesh_sha256": "825e79a01b983b14b136d4fc2490c2bc40e85ccc25ebd8ae6aa32e88dd544f91",
    "catalog_sha256": "7398ce4349f076e225e76d1d840d60da1dfe24b57181c1ae1d7b5cfc069d8291",
    "canonical_sha256": "583407113cbf7d20543bf8a2b1f44e2f0ba814281747e160bd0ff84788ace739",
    "node_count": 313, "quad4_count": 265, "seg2_count": 92, "total_cell_count": 357,
    "body_counts": {"PLAQUE1": 144, "PLAQUE2": 121}, "slave_nodes": 13,
    "slave_segments": 12, "master_nodes": 12, "master_segments": 11,
}
REFINED_SHAPE = {
    "variant": VARIANT, "node_count": 1154, "quad4_count": 1060, "seg2_count": 184,
    "total_cell_count": 1244, "body_counts": {"PLAQUE1": 576, "PLAQUE2": 484},
    "slave_nodes": 25, "slave_segments": 24, "master_nodes": 23, "master_segments": 22,
}


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def variant(settings):
    if "mesh_variant" not in settings:
        return None
    if type(settings["mesh_variant"]) is not str or settings["mesh_variant"] != VARIANT:
        raise ValueError("Only the optional uniform_quad4_2x mesh variant is admitted")
    return VARIANT


def contract(selected=None, profile=None):
    if selected is None:
        return deepcopy(ORIGINAL)
    if type(selected) is not str or selected != VARIANT or not isinstance(profile, dict):
        raise ValueError("Missing or unsupported sealed contact mesh profile")
    if profile.get("kind") != "SEALED_UNIFORM_QUAD4_2X_CONTACT_PROFILE" or profile.get("shape") != REFINED_SHAPE:
        raise ValueError("Refined profile shape differs from fixed uniform2 contract")
    if profile.get("parent") != {key: ORIGINAL[key] for key in ("mesh_sha256", "catalog_sha256", "canonical_sha256")}:
        raise ValueError("Refined profile does not derive from the exact original mesh")
    pins = profile.get("pins")
    if not isinstance(pins, dict) or set(pins) != {"mesh_sha256", "catalog_sha256", "canonical_sha256", "recipe_sha256", "generator_sha256"}:
        raise ValueError("Incomplete sealed refined profile pins")
    if any(type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value) for value in pins.values()):
        raise ValueError("Malformed sealed refined digest")
    return {**deepcopy(REFINED_SHAPE), **pins, "parent": deepcopy(profile["parent"])}


def load_profile(path, expected_sha256):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("Sealed refined contact profile bytes changed")
    profile = json.loads(data.decode("utf-8"))
    contract(VARIANT, profile)
    return profile


def _bits(value):
    return struct.pack(">d", value)


def _area(xy, cell):
    return math.fsum(xy[cell[i]][0] * xy[cell[(i + 1) % 4]][1] -
                     xy[cell[(i + 1) % 4]][0] * xy[cell[i]][1] for i in range(4)) / 2.0


def _positive_gauss_jacobians(xy, cell):
    a = 1.0 / math.sqrt(3.0)
    corners = [xy[n] for n in cell]
    for xi, eta in ((-a, -a), (a, -a), (a, a), (-a, a)):
        dxi = [-(1 - eta) / 4, (1 - eta) / 4, (1 + eta) / 4, -(1 + eta) / 4]
        deta = [-(1 - xi) / 4, -(1 + xi) / 4, (1 + xi) / 4, (1 - xi) / 4]
        dx, dy = [math.fsum(w * p[axis] for w, p in zip(dxi, corners)) for axis in range(2)]
        ex, ey = [math.fsum(w * p[axis] for w, p in zip(deta, corners)) for axis in range(2)]
        determinant = dx * ey - dy * ex
        if not math.isfinite(determinant) or determinant <= 0:
            raise ValueError("Nonpositive child QUAD4 FPG4 Jacobian")


def subdivide_original_catalog(original):
    """Preserve original313, sorted topological edges, then parent-order centers."""
    if canonical_sha(original) != ORIGINAL["canonical_sha256"] or original.get("source_sha256") != ORIGINAL["mesh_sha256"]:
        raise ValueError("Subdivision requires the sealed original full catalogue")
    source_xy = original["coordinates_in_native_order"]
    quads = original["levels"]["0"]["cell_connectivity_in_native_order"]
    segments = original["levels"]["-1"]["cell_connectivity_in_native_order"]
    edges = sorted({tuple(sorted((cell[i], cell[(i + 1) % 4]))) for cell in quads for i in range(4)})
    if len(source_xy) != 313 or len(quads) != 265 or len(segments) != 92 or len(edges) != 576:
        raise ValueError("Original topology does not have the admitted edge/cell/node counts")
    xy = deepcopy(source_xy)
    node_parent = [{"node_id": n, "origin": "original", "source_node_id": n} for n in range(313)]
    midpoints = {}
    for a, b in edges:
        index = len(xy)
        midpoints[(a, b)] = index
        xy.append([math.fsum((source_xy[a][axis], source_xy[b][axis])) / 2.0 for axis in range(2)])
        node_parent.append({"node_id": index, "origin": "edge_midpoint", "source_edge_node_ids": [a, b]})
    centers = []
    for parent, cell in enumerate(quads):
        index = len(xy)
        centers.append(index)
        xy.append([math.fsum(source_xy[n][axis] for n in cell) / 4.0 for axis in range(2)])
        node_parent.append({"node_id": index, "origin": "parent_center", "source_level": "0", "source_cell_id": parent})
    children, cell_parent = [], {"0": [], "-1": []}
    for parent, (a, b, c, d) in enumerate(quads):
        mab, mbc, mcd, mda = (midpoints[tuple(sorted(pair))] for pair in ((a, b), (b, c), (c, d), (d, a)))
        q = centers[parent]
        for local, cell in enumerate(((a, mab, q, mda), (mab, b, mbc, q), (q, mbc, c, mcd), (mda, q, mcd, d))):
            index = len(children)
            children.append(list(cell))
            cell_parent["0"].append({"cell_id": index, "source_level": "0", "source_cell_id": parent, "local_child": local})
    child_segments = []
    for parent, (a, b) in enumerate(segments):
        midpoint = midpoints[tuple(sorted((a, b)))]
        for local, cell in enumerate(((a, midpoint), (midpoint, b))):
            index = len(child_segments)
            child_segments.append(list(cell))
            cell_parent["-1"].append({"cell_id": index, "source_level": "-1", "source_cell_id": parent, "local_child": local})
    levels = {}
    for level, cells, multiplier in (("0", children, 4), ("-1", child_segments, 2)):
        groups = {}
        for name, group in original["levels"][level]["groups"].items():
            ids = [parent * multiplier + local for parent in group["cell_ids"] for local in range(multiplier)]
            nodes = sorted({n for cell in ids for n in cells[cell]})
            selected_xy = [xy[n] for n in nodes]
            record = {"cell_ids": ids, "cell_count": len(ids), "node_ids": nodes,
                "bounds": [[min(point[axis] for point in selected_xy) for axis in range(2)],
                           [max(point[axis] for point in selected_xy) for axis in range(2)]]}
            if level == "-1":
                record["directed_segments"] = [[xy[n] for n in cells[cell]] for cell in ids]
            groups[name] = record
        levels[level] = {"node_count": len(xy), "cell_count": len(cells),
            "cell_types": deepcopy(original["levels"][level]["cell_types"]),
            "cell_connectivity_in_native_order": cells, "groups": groups}
    old_names = original["node_name_field"]
    if not isinstance(old_names, list) or len(old_names) != 313:
        raise ValueError("Original genuine MED labels must be retained")
    labels = list(old_names) + [f"R{n + 1}" for n in range(313, 1154)]
    if len(set(labels)) != 1154:
        raise ValueError("Generated declared node labels collide with original labels")
    plan = {"coordinates_in_native_order": xy, "levels": levels,
        "node_groups": deepcopy(original["node_groups"]), "node_name_field": labels,
        "node_parent_map": node_parent, "cell_parent_map": cell_parent,
        "label_policy": "Original313 MED input labels preserved; R314..R1154 are declared generated INPUT labels, not observed Mesh API labels",
        "arithmetic": "Sorted original endpoint-index pairs; midpoint math.fsum(two original components)/2.0; center math.fsum(four original components)/4.0",
        "parent": {key: ORIGINAL[key] for key in ("mesh_sha256", "catalog_sha256", "canonical_sha256")},
        "shape": deepcopy(REFINED_SHAPE)}
    validate_refined_plan(plan, original)
    return plan


def validate_refined_plan(plan, original):
    """Physical parent/prefix, direction, incidence and complete child coverage."""
    xy, source_xy = plan["coordinates_in_native_order"], original["coordinates_in_native_order"]
    if len(xy) != 1154 or len(plan["node_parent_map"]) != 1154 or plan["shape"] != REFINED_SHAPE:
        raise ValueError("Refined node/parent/shape count differs from fixed contract")
    for index, point in enumerate(xy):
        if len(point) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in point):
            raise ValueError("Refined coordinates must be finite genuine two-component XY")
        if plan["node_parent_map"][index]["node_id"] != index:
            raise ValueError("Generated node parent mapping/order drift")
        if index < 313 and any(_bits(a) != _bits(b) for a, b in zip(point, source_xy[index])):
            raise ValueError("Original313 coordinate bits/order changed")
    if plan["node_groups"] != original["node_groups"] or plan["node_name_field"][:313] != original["node_name_field"]:
        raise ValueError("Original named-node identities/labels changed")
    source_quads = original["levels"]["0"]["cell_connectivity_in_native_order"]
    source_edges = sorted({tuple(sorted((cell[i], cell[(i + 1) % 4]))) for cell in source_quads for i in range(4)})
    midpoint_ids = {}
    for offset, (a, b) in enumerate(source_edges):
        index = 313 + offset
        midpoint_ids[(a, b)] = index
        expected_parent = {"node_id": index, "origin": "edge_midpoint", "source_edge_node_ids": [a, b]}
        expected_xy = [math.fsum((source_xy[a][axis], source_xy[b][axis])) / 2.0 for axis in range(2)]
        if plan["node_parent_map"][index] != expected_parent or any(_bits(a) != _bits(b) for a, b in zip(xy[index], expected_xy)):
            raise ValueError("Sorted shared-edge midpoint arithmetic/parent identity changed")
    centers = {}
    for parent, cell in enumerate(source_quads):
        index = 889 + parent
        centers[parent] = index
        expected_parent = {"node_id": index, "origin": "parent_center", "source_level": "0", "source_cell_id": parent}
        expected_xy = [math.fsum(source_xy[n][axis] for n in cell) / 4.0 for axis in range(2)]
        if plan["node_parent_map"][index] != expected_parent or any(_bits(a) != _bits(b) for a, b in zip(xy[index], expected_xy)):
            raise ValueError("Parent-center arithmetic/order/identity changed")
    edges = {}
    for level, count, multiplier, arity in (("0", 1060, 4, 4), ("-1", 184, 2, 2)):
        data = plan["levels"][level]
        cells = data["cell_connectivity_in_native_order"]
        if data["cell_count"] != count or len(cells) != count or len(plan["cell_parent_map"][level]) != count:
            raise ValueError("Refined cell/parent coverage drift")
        source_data = original["levels"][level]
        if set(data["groups"]) != set(source_data["groups"]):
            raise ValueError("Refinement lost an original body/boundary group")
        for index, cell in enumerate(cells):
            if len(cell) != arity or len(set(cell)) != arity or any(type(n) is not int or not 0 <= n < 1154 for n in cell):
                raise ValueError("Invalid refined connectivity")
            expected_map = {"cell_id": index, "source_level": level, "source_cell_id": index // multiplier, "local_child": index % multiplier}
            if plan["cell_parent_map"][level][index] != expected_map:
                raise ValueError("Refined parent-cell mapping/order drift")
            if level == "0":
                if _area(xy, cell) <= 0:
                    raise ValueError("Nonpositive child QUAD4 area")
                _positive_gauss_jacobians(xy, cell)
                a, b, c, d = source_quads[index // 4]
                mab, mbc, mcd, mda = (midpoint_ids[tuple(sorted(pair))] for pair in ((a, b), (b, c), (c, d), (d, a)))
                q = centers[index // 4]
                expected_child = ((a, mab, q, mda), (mab, b, mbc, q), (q, mbc, c, mcd), (mda, q, mcd, d))[index % 4]
                if cell != list(expected_child):
                    raise ValueError("Oriented child connectivity differs from the parent subdivision")
                for a, b in zip(cell, cell[1:] + cell[:1]):
                    key = tuple(sorted((a, b)))
                    edges.setdefault(key, []).append((a, b))
            else:
                a, b = source_data["cell_connectivity_in_native_order"][index // 2]
                m = midpoint_ids[tuple(sorted((a, b)))]
                if cell != list(((a, m), (m, b))[index % 2]):
                    raise ValueError("Directed boundary child differs from the source SEG2")
        for name, group in data["groups"].items():
            expected_ids = [parent * multiplier + local for parent in source_data["groups"][name]["cell_ids"] for local in range(multiplier)]
            nodes = sorted({n for cell in expected_ids for n in cells[cell]})
            if group["cell_ids"] != expected_ids or group["node_ids"] != nodes or group["cell_count"] != len(expected_ids):
                raise ValueError("Refined boundary/body membership drift")
    if any(len(uses) not in (1, 2) or (len(uses) == 2 and uses[0] != tuple(reversed(uses[1]))) for uses in edges.values()):
        raise ValueError("Nonconforming or inconsistently oriented body edge incidence")
    boundaries = plan["levels"]["-1"]
    seg = boundaries["cell_connectivity_in_native_order"]
    if {tuple(sorted(cell)) for cell in seg} != {key for key, uses in edges.items() if len(uses) == 1}:
        raise ValueError("Boundary SEG2 coverage differs from all actual exterior edges")
    for name, sign, number in (("AB", 1, 24), ("EF", -1, 22)):
        group = boundaries["groups"][name]
        if group["cell_count"] != number:
            raise ValueError("Contact edge count changed")
        for index in group["cell_ids"]:
            a, b = [xy[n] for n in seg[index]]
            if a[1] != 0.0 or b[1] != 0.0 or (b[0] - a[0]) * sign <= 0:
                raise ValueError("Refined directed contact normal changed")
    if set(boundaries["groups"]["AB"]["node_ids"]) & set(boundaries["groups"]["EF"]["node_ids"]):
        raise ValueError("Refined interface coincident nodes were merged")
    quads = plan["levels"]["0"]["cell_connectivity_in_native_order"]
    for name, count in REFINED_SHAPE["body_counts"].items():
        ids = plan["levels"]["0"]["groups"][name]["cell_ids"]
        source_ids = original["levels"]["0"]["groups"][name]["cell_ids"]
        source_area = math.fsum(_area(source_xy, original["levels"]["0"]["cell_connectivity_in_native_order"][index]) for index in source_ids)
        area = math.fsum(_area(xy, quads[index]) for index in ids)
        if len(ids) != count or not math.isclose(area, source_area, rel_tol=1e-13, abs_tol=1e-13):
            raise ValueError("Refinement changed body area/count")
    return {"status": "PASS", "node_count": 1154, "quad4_count": 1060, "seg2_count": 184,
        "original_prefix_bits_preserved": True, "separate_interface_node_sets": True}


def write_and_read_med(original_path, plan, destination, api_evidence_path):
    """One deferred native preparation/read-back; no Code_Aster commands."""
    import MEDLoader as med
    import medcoupling as mc
    destination = Path(destination)
    if destination.exists() or destination.is_symlink() or Path(api_evidence_path).exists():
        raise FileExistsError("Refined MED preparation artifacts must be fresh")
    if not str(mc.MEDCouplingVersionStr()).startswith("9.14"):
        raise RuntimeError("Only the retained native MEDLoader9.14 environment is admitted")
    source = med.MEDFileUMesh.New(str(original_path))
    names = source.getNameFieldAtLevel(1)
    required = {"MEDFileUMesh": (med.MEDFileUMesh, ("New", "setMeshAtLevel", "setGroupsAtLevel", "setNameFieldAtLevel", "write")),
        "MEDCouplingUMesh": (mc.MEDCouplingUMesh, ("New", "setCoords", "allocateCells", "insertNextCell", "finishInsertingCells")),
        "DataArrayAsciiChar": (type(names), ("New", "alloc", "getIJ", "setIJ"))}
    api = {"medcoupling_version": str(mc.MEDCouplingVersionStr()), "MEDLoader_module": med.__file__,
        "original_name_width": names.getNumberOfComponents(), "methods": {}, "mechanical_solver_calls": 0}
    for label, (owner, methods) in required.items():
        for name in methods:
            method = getattr(owner, name, None)
            api["methods"][label + "." + name] = {"available": callable(method), "documentation": getattr(method, "__doc__", None)}
    with Path(api_evidence_path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(api, stream, indent=2, sort_keys=True)
        stream.write("\n")
    if any(not item["available"] or not item["documentation"] for item in api["methods"].values()):
        raise RuntimeError("Required native MED writer API/documentation unavailable; no write admitted")
    coordinates = mc.DataArrayDouble(plan["coordinates_in_native_order"])
    file_mesh = med.MEDFileUMesh.New()
    for level, dimension, cell_type in ((0, 2, mc.NORM_QUAD4), (-1, 1, mc.NORM_SEG2)):
        body = mc.MEDCouplingUMesh.New("plaques_uniform2", dimension)
        body.setCoords(coordinates)
        cells = plan["levels"][str(level)]["cell_connectivity_in_native_order"]
        body.allocateCells(len(cells))
        for cell in cells:
            body.insertNextCell(cell_type, cell)
        body.finishInsertingCells()
        file_mesh.setMeshAtLevel(level, body)
        groups = []
        for name, group in plan["levels"][str(level)]["groups"].items():
            array = mc.DataArrayInt(group["cell_ids"])
            array.setName(name)
            groups.append(array)
        file_mesh.setGroupsAtLevel(level, groups)
    groups = []
    for name, group in plan["node_groups"].items():
        array = mc.DataArrayInt(group["node_ids"])
        array.setName(name)
        groups.append(array)
    file_mesh.setGroupsAtLevel(1, groups)
    width = names.getNumberOfComponents()
    declared_names = plan["node_name_field"]
    if any(len(name) > width for name in declared_names):
        raise ValueError("Declared generated labels exceed genuine original MED name width")
    new_names = type(names).New()
    new_names.alloc(1154, width)
    example = names.getIJ(0, 0)
    for row, label in enumerate(declared_names):
        padded = label.ljust(width)
        for column, char in enumerate(padded):
            value = names.getIJ(row, column) if row < 313 else (ord(char) if isinstance(example, int) else char)
            new_names.setIJ(row, column, value)
    file_mesh.setNameFieldAtLevel(1, new_names)
    file_mesh.write(str(destination), 2)
    actual = med.MEDFileUMesh.New(str(destination))
    actual_xy = actual.getCoords().toNumPyArray().tolist()
    result = {"kind": "GENERATED_UNIFORM_QUAD4_2X_NATIVE_MED_READBACK_NO_SOLVER", "mesh_name": actual.getName(),
        "source_file": destination.name, "source_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "node_indexing": "ZERO_BASED_MEDLOADER_UNRENUMBERED", "coordinate_unit": "m_FROM_OFFICIAL_REFERENCE_DOC_NOT_MED_UNIT_METADATA",
        "coordinates_in_native_order": actual_xy, "levels": {}, "node_groups": {},
        "medcoupling_version": str(mc.MEDCouplingVersionStr()), "solver_calls": 0}
    for level in (0, -1):
        body = actual.getMeshAtLevel(level)
        cells = [list(body.getNodeIdsOfCell(index)) for index in range(body.getNumberOfCells())]
        groups = {}
        for name in actual.getGroupsOnSpecifiedLev(level):
            ids = list(actual.getGroupArr(level, name).getValues())
            nodes = sorted({n for cell in ids for n in cells[cell]})
            points = [actual_xy[n] for n in nodes]
            record = {"cell_ids": ids, "cell_count": len(ids), "node_ids": nodes,
                "bounds": [[min(p[axis] for p in points) for axis in range(2)],
                           [max(p[axis] for p in points) for axis in range(2)]]}
            if level == -1:
                record["directed_segments"] = [[actual_xy[n] for n in cells[cell]] for cell in ids]
            groups[name] = record
        result["levels"][str(level)] = {"node_count": body.getNumberOfNodes(),
            "cell_count": body.getNumberOfCells(), "cell_types": list(body.getAllGeoTypes()),
            "cell_connectivity_in_native_order": cells, "groups": groups}
    for name in actual.getGroupsOnSpecifiedLev(1):
        ids = list(actual.getNodeGroupArr(name).getValues())
        result["node_groups"][name] = {"node_ids": ids, "coordinates": [actual_xy[n] for n in ids]}
    field = actual.getNameFieldAtLevel(1)
    read_names = []
    for row in range(field.getNumberOfTuples()):
        characters = [field.getIJ(row, column) for column in range(field.getNumberOfComponents())]
        read_names.append("".join(chr(c) if isinstance(c, int) else c for c in characters).rstrip(" \x00"))
    result["node_name_field"] = read_names
    result["generated_label_basis"] = "Actual MED read-back of declared INPUT labels; not observations of optional Code_Aster Mesh.getNodeName"
    with (destination.parent / "med-readback-raw.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    # Preserve the entire genuine read-back before any candidate admission.
    if actual_xy != plan["coordinates_in_native_order"] or any(_bits(a) != _bits(b) for p, q in zip(actual_xy, plan["coordinates_in_native_order"]) for a, b in zip(p, q)):
        raise ValueError("Actual MED coordinate/index bits changed on write/read-back")
    for level, cell_type in ((0, mc.NORM_QUAD4), (-1, mc.NORM_SEG2)):
        data, expected = result["levels"][str(level)], plan["levels"][str(level)]
        if (data["node_count"] != 1154 or data["cell_count"] != expected["cell_count"] or
                data["cell_connectivity_in_native_order"] != expected["cell_connectivity_in_native_order"] or
                set(data["cell_types"]) != {cell_type} or data["groups"] != expected["groups"]):
            raise ValueError("Actual MED level/type/order/connectivity/group coverage differs from the deterministic plan")
    if result["node_groups"] != plan["node_groups"] or read_names != declared_names:
        raise ValueError("Actual MED changed original named-node or declared label identities")
    return result
