"""Scientific checks of normalized embedded meshes and complete scalar fields.

No backend file parser, native Gmsh import or native solve belongs here.
"""

from collections import defaultdict
import copy
import json
import math

if __name__ == "imported_reference":
    from domain_reference import ATOL, _ids, _keys, _number, _same, expression_value
    from fenicsx_expression import PDEInputError, finite_number, parse_expression
else:
    from plugins.pde_elliptic.reference import ATOL, _ids, _keys, _number, _same, expression_value
    from caelab.adapters.fenicsx_worker import PDEInputError, finite_number, parse_expression

VERSION = "1"
VALIDATIONS = {"max_l2_error", "min_l2_rate", "max_h1_seminorm_error", "min_h1_rate", "max_residual_relative"}
FIELD_KEYS = {"schema_version", "coordinates_unit", "field_unit", "node_ids", "coordinates", "values", "source_node_ids",
              "cell_ids", "source_cell_ids", "cell_node_ids", "dirichlet_node_ids", "boundaries"}
BOUNDARY_KEYS = {"facet_ids", "facet_node_ids", "dof_ids", "measure", "normal_integral", "prescribed_values", "prescribed_integral", "source_element_ids"}
MAPPING_KEYS = {"schema_version", "original_sha256", "dense_sha256", "dense_node_ids", "original_node_ids", "geometry_input_indices", "geometry_source_node_ids",
                "vertex_ids", "vertex_geometry_indices", "vertex_dof_ids", "cell_ids", "original_cell_index", "importer_cell_source_ids", "source_cell_ids",
                "physical_groups", "boundary_source_elements", "gmsh_initialization"}
BINDING_KEYS = {"schema_version", "source_sha256", "dense_sha256", "node_ids", "source_node_ids", "diffusion", "reaction", "rhs_values", "reference_values"}
STUDY_KEYS = {"level", "degree", "cell_type", "max_edge_h", "global_cells", "global_nodes", "global_dofs", "dirichlet_nodes", "dirichlet_dofs",
              "boundary_value_error", "l2_error", "h1_seminorm_error", "l2_convergence_rate", "h1_seminorm_convergence_rate", "linear_residual",
              "ksp_convergence_reason", "ksp_iterations", "solver_policy", "solution_synchronization", "physical_groups", "coefficients", "source_sha256", "dense_sha256"}
LIMITATIONS = [
    "Dimensionless stationary scalar real P1 triangles on one connected conforming planar polygon without holes.",
    "Named physical exterior groups admit Dirichlet or outward diffusion*grad(u).normal Neumann data; at least one complete group is Dirichlet.",
    "Original sparse IDs/bytes and derived import copies are distinct; native DOF/geometry/vertex/cell/facet identities require full mappings.",
    "Native degree8 symbolic L2 and full-gradient H1 errors use the declared reference, never an interpolated reference.",
    "Domain independently checks normalized embedding/coverage, native fields/input bindings, mappings, residual normalization and every actual-h mesh-pair order.",
    "Prescribed Neumann integrals are input observations, not a complete measured boundary flux or physical balance.",
    "MSH4, curved/high-order/3D/holes/MPI/Robin/time/vector/coupled/nonlinear/large input assets and physical qualification remain unsupported or unverified.",
    "Numerical reference agreement does not qualify material, engineering strength or physical use; UNKNOWN and NOT_RELEASED remain.",
]


def _sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise PDEInputError("Incomplete source hash identity")
    return value


def _positive_ids(value, label):
    result = _ids(value, label)
    if any(node <= 0 or node > 2**31-1 for node in result):
        raise PDEInputError("Normalized original identifiers require bounded positive integers")
    return result


def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _collinear(a, b, c):
    return abs(_cross(a, b, c)) <= ATOL*max(1., math.dist(a, b)*math.dist(a, c))


def _on_segment(p, a, b):
    return _collinear(a, b, p) and all(min(a[d], b[d])-ATOL <= p[d] <= max(a[d], b[d])+ATOL for d in (0, 1))


def _embedding(edges, xyz):
    """Reject crossings, overlap and hanging vertices with a bounding-box sweep."""
    segments = sorted((min(xyz[a][0], xyz[b][0]), max(xyz[a][0], xyz[b][0]), min(xyz[a][1], xyz[b][1]), max(xyz[a][1], xyz[b][1]), a, b) for a, b in edges)
    active = []
    for edge in segments:
        xmin, xmax, ymin, ymax, a, b = edge
        active = [old for old in active if old[1]+ATOL >= xmin]
        p, q = xyz[a], xyz[b]
        for old in active:
            if old[3]+ATOL < ymin or ymax+ATOL < old[2]:
                continue
            c, d = old[4:]
            r, s = xyz[c], xyz[d]
            common = {a, b} & {c, d}
            if any(node not in common and _on_segment(xyz[node], p, q) for node in (c, d)) or any(node not in common and _on_segment(xyz[node], r, s) for node in (a, b)):
                raise PDEInputError("Unsupported hanging vertex, touching or overlapping embedded edges")
            if _cross(p, q, r)*_cross(p, q, s) < 0 and _cross(r, s, p)*_cross(r, s, q) < 0:
                raise PDEInputError("Crossing embedded edges")
        active.append(edge)


def _compact(points):
    remaining = list(points)
    changed = True
    while changed and len(remaining) > 3:
        changed = False
        for i in range(len(remaining)):
            if _collinear(remaining[i-1], remaining[i], remaining[(i+1) % len(remaining)]):
                remaining.pop(i)
                changed = True
                break
    start = min(range(len(remaining)), key=lambda i: remaining[i])
    return remaining[start:]+remaining[:start]


def mesh_geometry(mesh):
    """Validate normalized scientific geometry, independent of MSH syntax."""
    _keys(mesh, {"source_sha256", "body", "nodes", "cells", "boundaries"}, "normalized mesh")
    _sha(mesh["source_sha256"])
    body = _keys(mesh["body"], {"name", "tag"}, "normalized body")
    if not isinstance(body["name"], str) or not body["name"] or type(body["tag"]) is not int or body["tag"] <= 0:
        raise PDEInputError("Incomplete normalized body")
    if not isinstance(mesh["nodes"], list) or len(mesh["nodes"]) < 3 or not isinstance(mesh["cells"], list) or not mesh["cells"]:
        raise PDEInputError("Complete normalized nodes/cells are required")
    xyz, coordinate_ids = {}, {}
    for row in mesh["nodes"]:
        _keys(row, {"id", "coordinates"}, "normalized node")
        _positive_ids([row["id"]], "source node ID")
        point = row["coordinates"]
        if not isinstance(point, list) or len(point) != 2 or any(not finite_number(v) or abs(v) > 1000 for v in point):
            raise PDEInputError("Malformed normalized planar coordinates")
        if row["id"] in xyz or tuple(point) in coordinate_ids:
            raise PDEInputError("Duplicate source IDs or coordinate positions")
        xyz[row["id"]] = point
        coordinate_ids[tuple(point)] = row["id"]
    if [row["id"] for row in mesh["nodes"]] != sorted(xyz) or any(not .001 <= max(p[d] for p in xyz.values())-min(p[d] for p in xyz.values()) <= 1000 for d in (0, 1)):
        raise PDEInputError("Normalized node ordering or bounding-box extents differ")
    cells, identities, edges, used, areas = {}, set(), defaultdict(list), set(), []
    for row in mesh["cells"]:
        _keys(row, {"id", "node_ids", "physical_tag", "entity_tag"}, "normalized triangle")
        _positive_ids([row["id"]], "source cell ID")
        nodes = row["node_ids"]
        if not isinstance(nodes, list) or len(nodes) != 3 or len(_positive_ids(nodes, "source cell nodes")) != 3 or not set(nodes) <= set(xyz):
            raise PDEInputError("Incomplete normalized triangle nodes")
        if row["id"] in cells or tuple(sorted(nodes)) in identities or type(row["physical_tag"]) is not int or row["physical_tag"] != body["tag"] or type(row["entity_tag"]) is not int or row["entity_tag"] <= 0:
            raise PDEInputError("Duplicate triangle or unexpected body membership")
        determinant = _cross(*(xyz[node] for node in nodes))
        if not math.isfinite(determinant) or determinant == 0:
            raise PDEInputError("Degenerate normalized triangle")
        cells[row["id"]] = row
        identities.add(tuple(sorted(nodes)))
        used.update(nodes)
        areas.append(abs(determinant)/2)
        oriented = nodes if determinant > 0 else list(reversed(nodes))
        for a, b in zip(oriented, oriented[1:]+oriented[:1]):
            edges[tuple(sorted((a, b)))].append((row["id"], a, b, next(node for node in nodes if node not in (a, b))))
    if [row["id"] for row in mesh["cells"]] != sorted(cells) or used != set(xyz) or any(len(rows) not in (1, 2) for rows in edges.values()):
        raise PDEInputError("Unused nodes, unsorted cells or nonmanifold topology")
    adjacency = defaultdict(set)
    for (a, b), rows in edges.items():
        if len(rows) == 2:
            if _cross(xyz[a], xyz[b], xyz[rows[0][3]])*_cross(xyz[a], xyz[b], xyz[rows[1][3]]) >= 0:
                raise PDEInputError("Adjacent triangles overlap on the same side of a common edge")
            adjacency[rows[0][0]].add(rows[1][0])
            adjacency[rows[1][0]].add(rows[0][0])
    seen, pending = set(), [next(iter(cells))]
    while pending:
        cell = pending.pop()
        if cell not in seen:
            seen.add(cell)
            pending.extend(adjacency[cell]-seen)
    if seen != set(cells):
        raise PDEInputError("Disconnected triangle components are unsupported")
    _embedding(edges, xyz)
    exterior = {edge: rows[0] for edge, rows in edges.items() if len(rows) == 1}
    next_node, indegree = {}, defaultdict(int)
    for _, a, b, _ in exterior.values():
        if a in next_node:
            raise PDEInputError("Exterior is not one simple polygon")
        next_node[a] = b
        indegree[b] += 1
    if not exterior or set(next_node) != set(indegree) or any(v != 1 for v in indegree.values()):
        raise PDEInputError("Incomplete exterior polygon")
    polygon_ids, node = [], min(next_node)
    while node not in polygon_ids:
        polygon_ids.append(node)
        node = next_node[node]
    if node != polygon_ids[0] or len(polygon_ids) != len(exterior) or len(xyz)-len(edges)+len(cells) != 1:
        raise PDEInputError("Holes or multiple exterior cycles are unsupported")
    points = [xyz[node] for node in polygon_ids]
    polygon_area = sum(p[0]*q[1]-p[1]*q[0] for p, q in zip(points, points[1:]+points[:1]))/2
    if polygon_area <= 0:
        raise PDEInputError("Exterior orientation or polygon coverage differs")
    _same(math.fsum(areas), polygon_area, "complete triangle/polygon area")
    boundaries = mesh["boundaries"]
    if not isinstance(boundaries, dict) or not boundaries or body["name"] in boundaries:
        raise PDEInputError("Complete distinct named normalized boundaries are required")
    covered, element_ids, tags, edge_name, group_info = set(), set(cells), set(), {}, {}
    for name, group in sorted(boundaries.items()):
        _keys(group, {"tag", "elements"}, "normalized boundary")
        if not isinstance(name, str) or not name or type(group["tag"]) is not int or group["tag"] <= 0 or group["tag"] in tags or not isinstance(group["elements"], list) or not group["elements"]:
            raise PDEInputError("Malformed normalized boundary tag/membership")
        tags.add(group["tag"])
        measure, normal, ids, nodes = 0., [0., 0.], [], set()
        for row in group["elements"]:
            _keys(row, {"id", "node_ids", "entity_tag"}, "normalized exterior element")
            _positive_ids([row["id"]], "source exterior ID")
            pair = row["node_ids"]
            if not isinstance(pair, list) or len(pair) != 2 or len(_positive_ids(pair, "boundary endpoints")) != 2 or not set(pair) <= set(xyz) or type(row["entity_tag"]) is not int or row["entity_tag"] <= 0:
                raise PDEInputError("Incomplete exterior endpoints")
            edge = tuple(sorted(pair))
            if row["id"] in element_ids or edge not in exterior or edge in covered:
                raise PDEInputError("Exterior source partition omits, duplicates or uses an interior edge")
            covered.add(edge)
            element_ids.add(row["id"])
            ids.append(row["id"])
            nodes.update(pair)
            edge_name[edge] = name
            _, a, b, _ = exterior[edge]
            p, q = xyz[a], xyz[b]
            measure += math.dist(p, q)
            normal[0] += q[1]-p[1]
            normal[1] += p[0]-q[0]
        if ids != sorted(ids) or not finite_number(measure, positive=True):
            raise PDEInputError("Boundary source ordering or positive measure differs")
        group_info[name] = {"node_ids": nodes, "source_element_ids": set(ids), "measure": measure, "normal_integral": normal}
    if covered != set(exterior):
        raise PDEInputError("Named exterior groups do not cover every exterior edge exactly once")
    segments = []
    for a, b in zip(polygon_ids, polygon_ids[1:]+polygon_ids[:1]):
        name = edge_name[tuple(sorted((a, b)))]
        p, q = xyz[a], xyz[b]
        if segments and segments[-1][0] == name and _collinear(segments[-1][1], p, q):
            segments[-1] = (name, segments[-1][1], q)
        else:
            segments.append((name, p, q))
    if len(segments) > 1 and segments[-1][0] == segments[0][0] and _collinear(segments[-1][1], segments[0][1], segments[0][2]):
        segments[0] = (segments[0][0], segments[-1][1], segments[0][2])
        segments.pop()
    return {"xyz": xyz, "cells": cells, "exterior": exterior, "groups": group_info, "polygon": _compact(points),
            "named_segments": sorted((name, tuple(p), tuple(q)) for name, p, q in segments), "area": polygon_area,
            "max_edge_h": max(math.dist(xyz[a], xyz[b]) for a, b in edges), "edge_count": len(edges)}


def mesh_series(meshes):
    if not isinstance(meshes, list) or not 3 <= len(meshes) <= 8:
        raise PDEInputError("Complete normalized refining mesh sequence is required")
    geometry = [mesh_geometry(mesh) for mesh in meshes]
    first = meshes[0]
    for i in range(1, len(meshes)):
        mesh, current, previous = meshes[i], geometry[i], geometry[i-1]
        if mesh["body"] != first["body"] or {name: group["tag"] for name, group in mesh["boundaries"].items()} != {name: group["tag"] for name, group in first["boundaries"].items()}:
            raise PDEInputError("Body or named physical boundary identities changed between levels")
        for key in ("polygon", "named_segments"):
            if len(current[key]) != len(geometry[0][key]):
                raise PDEInputError("Refined polygon or physical boundary geometry changed")
            for actual, expected in zip(current[key], geometry[0][key]):
                if key == "named_segments":
                    if actual[0] != expected[0]: raise PDEInputError("Refined physical boundary geometry changed")
                    actual, expected = actual[1:], expected[1:]
                    for p, q in zip(actual, expected):
                        for a, b in zip(p, q): _same(a, b, "refined named boundary geometry")
                else:
                    for a, b in zip(actual, expected): _same(a, b, "refined polygon")
        if current["max_edge_h"] >= previous["max_edge_h"] or len(mesh["nodes"]) <= len(meshes[i-1]["nodes"]) or len(mesh["cells"]) <= len(meshes[i-1]["cells"]):
            raise PDEInputError("Actual largest edge must decrease while source nodes/cells increase")
    return geometry


def validate_settings(settings, meshes):
    _keys(settings, {"problem", "mesh", "validation"}, "imported settings")
    problem = _keys(settings["problem"], {"domain", "weak_form", "boundaries", "reference"}, "imported problem")
    declared = _keys(problem["domain"], {"type", "body"}, "imported domain")
    if declared["type"] != "imported_mesh": raise PDEInputError("Unsupported domain declaration")
    _keys(settings["mesh"], {"degree", "levels"}, "mesh declaration")
    levels = settings["mesh"]["levels"]
    if type(settings["mesh"]["degree"]) is not int or settings["mesh"]["degree"] != 1 or not isinstance(levels, list) or len(levels) != len(meshes):
        raise PDEInputError("Normalized meshes differ from the frozen scalar P1 sequence")
    geometry = mesh_series(meshes)
    for level, mesh in zip(levels, meshes):
        if not isinstance(level, dict) or level.get("sha256") != mesh["source_sha256"] or declared["body"] != mesh["body"]["name"]:
            raise PDEInputError("Normalized source/body identity differs from the declaration")
    weak = _keys(problem["weak_form"], {"diffusion", "reaction", "rhs"}, "weak form")
    _number(weak["diffusion"], "diffusion", positive=True)
    _number(weak["reaction"], "reaction", nonnegative=True)
    parse_expression(weak["rhs"])
    reference = _keys(problem["reference"], {"solution", "source"}, "reference")
    parse_expression(reference["solution"])
    if not isinstance(reference["source"], str) or not reference["source"].strip() or len(reference["source"]) > 2000:
        raise PDEInputError("An explicit bounded reference source is required")
    thresholds = _keys(settings["validation"], VALIDATIONS, "numerical thresholds")
    for name, value in thresholds.items(): _number(value, name, positive=True)
    names = set(meshes[0]["boundaries"])
    boundaries = _keys(problem["boundaries"], names, "physical boundary declarations")
    for name, row in boundaries.items():
        _keys(row, {"type", "value"}, "boundary declaration")
        if row["type"] not in ("dirichlet", "neumann"): raise PDEInputError("Only Dirichlet or outward Neumann data are supported")
        parse_expression(row["value"])
    if not any(row["type"] == "dirichlet" for row in boundaries.values()):
        raise PDEInputError("At least one complete positive-length Dirichlet group is required")
    for info in geometry:
        selected = {}
        for point in info["xyz"].values():
            expression_value(weak["rhs"], *point)
            expression_value(reference["solution"], *point)
        for name, group in info["groups"].items():
            for node in group["node_ids"]:
                value = expression_value(boundaries[name]["value"], *info["xyz"][node])
                if boundaries[name]["type"] == "dirichlet":
                    if node in selected and not math.isclose(selected[node], value, rel_tol=ATOL, abs_tol=ATOL):
                        raise PDEInputError("Conflicting prescribed values at a shared Dirichlet node")
                    selected[node] = value
    return json.loads(json.dumps(settings, allow_nan=False))


def manufactured_problem(case="mixed", shape="l_shape", diffusion=1., reaction=0.):
    if case not in ("mixed", "all_dirichlet", "harmonic") or shape not in ("l_shape", "rectangle"):
        raise PDEInputError("Unsupported synthetic manufactured imported problem")
    k, c = _number(diffusion, "diffusion", positive=True), _number(reaction, "reaction", nonnegative=True)
    solution = "x[0]**2-x[1]**2+x[0]+2*x[1]+1" if case == "harmonic" else "x[0]**2+x[1]**2+x[0]+2*x[1]+1"
    rhs = "0.0" if case == "harmonic" and c == 0 else f"{c!r}*({solution})" if case == "harmonic" else f"{-4*k!r}+{c!r}*({solution})"
    normals = {"west": (-1, 0), "south": (0, -1), "north": (0, 1)}
    normals.update({"east_lower": (1, 0), "notch_horizontal": (0, 1), "notch_vertical": (1, 0)} if shape == "l_shape" else {"east": (1, 0)})
    boundaries = {}
    for name, (nx, ny) in normals.items():
        kind = "dirichlet" if case == "all_dirichlet" or name in ("west", "south") else "neumann"
        value = solution if kind == "dirichlet" else f"{k!r}*({nx}*(2*x[0]+1)+{ny}*({'-2' if case == 'harmonic' else '2'}*x[1]+2))"
        boundaries[name] = {"type": kind, "value": value}
    return {"domain": {"type": "imported_mesh", "body": "body"}, "weak_form": {"diffusion": k, "reaction": c, "rhs": rhs},
            "boundaries": boundaries, "reference": {"solution": solution, "source": "Independent manufactured polynomial derivatives on the labelled synthetic source polygon; not NAFEMS or physical qualification"}}


def model_declaration(settings, meshes):
    normalized = validate_settings(settings, meshes)
    geometry = mesh_series(meshes)
    problem, weak = normalized["problem"], normalized["problem"]["weak_form"]
    return {"case": "imported_scalar_elliptic", "version": VERSION,
            "model": {"geometry": {"type": "imported_mesh", "dimension": 2, "unit": "1", "body": problem["domain"]["body"]},
                      "mesh": {"degree": 1, "levels": [{"source_sha256": mesh["source_sha256"], "source": level["source"], "node_count": len(mesh["nodes"]),
                          "cell_count": len(mesh["cells"]), "max_edge_h": info["max_edge_h"], "body": copy.deepcopy(mesh["body"]),
                          "boundaries": {name: {"tag": group["tag"]} for name, group in mesh["boundaries"].items()}} for level, mesh, info in zip(normalized["mesh"]["levels"], meshes, geometry)]}},
            "constitutive_law": {"type": "constant_scalar_diffusion_reaction", "diffusion": {"value": weak["diffusion"], "unit": "1"}, "reaction": {"value": weak["reaction"], "unit": "1"}},
            "boundary_conditions": [{"boundary": name, "type": row["type"], "value": {"expression": row["value"], "unit": "1"}} for name, row in sorted(problem["boundaries"].items())],
            "loads": [{"type": "source", "value": {"expression": weak["rhs"], "unit": "1"}}],
            "outputs": {"fields": [{"field": "u", "type": "scalar", "unit": "1"}]}, "reference": copy.deepcopy(problem["reference"])}


def convergence_rate(coarse, fine, previous_h, current_h):
    if coarse <= 0 or fine <= 0:
        return None
    return (math.log(coarse)-math.log(fine))/(math.log(previous_h)-math.log(current_h))


def _mapping_check(mesh, field, mapping):
    _keys(mapping, MAPPING_KEYS, "complete import mapping")
    if mapping["schema_version"] != "1" or mapping["original_sha256"] != mesh["source_sha256"]:
        raise PDEInputError("Original import mapping identity differs")
    _sha(mapping["dense_sha256"])
    node_ids, cell_ids = field["node_ids"], field["cell_ids"]
    size, count = len(node_ids), len(cell_ids)
    source_nodes = [row["id"] for row in mesh["nodes"]]
    source_cells = [row["id"] for row in mesh["cells"]]
    for key in ("dense_node_ids", "original_node_ids", "geometry_source_node_ids", "source_cell_ids"):
        _positive_ids(mapping[key], key)
    _ids(mapping["cell_ids"], "mapped native cells", size=count)
    if mapping["dense_node_ids"] != list(range(1, size+1)) or mapping["original_node_ids"] != source_nodes:
        raise PDEInputError("Complete dense/original node bijection differs")
    for key in ("geometry_input_indices", "vertex_ids", "vertex_geometry_indices", "vertex_dof_ids"):
        if _ids(mapping[key], key, size=size) != set(range(size)) or len(mapping[key]) != size:
            raise PDEInputError("Native geometry/vertex/DOF mapping is not bijective")
    if mapping["vertex_ids"] != sorted(mapping["vertex_ids"]): raise PDEInputError("Native vertex records must be sorted")
    expected_geometry = [source_nodes[index] for index in mapping["geometry_input_indices"]]
    if mapping["geometry_source_node_ids"] != expected_geometry:
        raise PDEInputError("Native input geometry mapping differs from the preserved dense table")
    by_dof = dict(zip(node_ids, field["source_node_ids"]))
    for geometry_index, dof in zip(mapping["vertex_geometry_indices"], mapping["vertex_dof_ids"]):
        if expected_geometry[geometry_index] != by_dof[dof]:
            raise PDEInputError("Native vertex geometry and scalar DOF source IDs disagree")
    if mapping["cell_ids"] != cell_ids or mapping["source_cell_ids"] != field["source_cell_ids"]:
        raise PDEInputError("Native/source cell mapping differs from saved fields")
    if _ids(mapping["original_cell_index"], "importer input cell rows", size=count) != set(range(count)) or len(mapping["original_cell_index"]) != count:
        raise PDEInputError("Native original-cell row mapping is not bijective")
    if _positive_ids(mapping["importer_cell_source_ids"], "captured importer element IDs") != set(source_cells) or len(mapping["importer_cell_source_ids"]) != count:
        raise PDEInputError("Captured importer source cells are incomplete")
    if [mapping["importer_cell_source_ids"][row] for row in mapping["original_cell_index"]] != field["source_cell_ids"]:
        raise PDEInputError("Native cell indices do not map through actual importer rows")
    expected_groups = {mesh["body"]["name"]: {"dim": 2, "tag": mesh["body"]["tag"]}, **{name: {"dim": 1, "tag": group["tag"]} for name, group in mesh["boundaries"].items()}}
    if mapping["physical_groups"] != expected_groups:
        raise PDEInputError("Actual imported physical names/dimensions/tags differ")
    for group in mapping["physical_groups"].values():
        if type(group["dim"]) is not int or type(group["tag"]) is not int:
            raise PDEInputError("Malformed actual physical tag types")
    if mapping["boundary_source_elements"] != {name: row["source_element_ids"] for name, row in field["boundaries"].items()}:
        raise PDEInputError("Actual boundary import mappings differ from retained facets")
    for row in mapping["boundary_source_elements"].values(): _positive_ids(row, "mapped source exterior IDs")
    initialization = _keys(mapping["gmsh_initialization"], {"argv", "read_config_files", "finalized"}, "Gmsh initialization")
    if initialization["argv"] != [] or initialization["read_config_files"] is not False or initialization["finalized"] is not True:
        raise PDEInputError("Actual owned Gmsh initialization/finalization differs")


def _field_check(settings, mesh, geometry, study, field, binding, mapping):
    _keys(field, FIELD_KEYS, "complete imported scalar field")
    size, count = len(mesh["nodes"]), len(mesh["cells"])
    if any(field[key] != "1" for key in ("schema_version", "coordinates_unit", "field_unit")):
        raise PDEInputError("Native field schema/units differ")
    ids, source_ids = field["node_ids"], field["source_node_ids"]
    if _ids(ids, "native scalar DOF IDs", size=size) != set(range(size)) or ids != sorted(ids) or _positive_ids(source_ids, "native source node IDs") != set(geometry["xyz"]):
        raise PDEInputError("Complete native/source scalar DOF bijection differs")
    if len(source_ids) != size or not isinstance(field["coordinates"], list) or len(field["coordinates"]) != size or not isinstance(field["values"], list) or len(field["values"]) != size:
        raise PDEInputError("Incomplete scalar fields or coordinates")
    xyz, values, to_source = {}, {}, dict(zip(ids, source_ids))
    for node, source, point, value in zip(ids, source_ids, field["coordinates"], field["values"]):
        if not isinstance(point, list) or len(point) != 2: raise PDEInputError("Malformed native scalar coordinates")
        for actual, expected in zip(point, geometry["xyz"][source]): _same(actual, expected, "actual original node coordinate")
        xyz[node], values[node] = point, _number(value, "native scalar field")
    cell_ids = field["cell_ids"]
    if _ids(cell_ids, "native cells", size=count) != set(range(count)) or cell_ids != sorted(cell_ids) or _positive_ids(field["source_cell_ids"], "native source cells") != set(geometry["cells"]):
        raise PDEInputError("Complete native/source cell bijection differs")
    tuples = field["cell_node_ids"]
    if not isinstance(tuples, list) or len(tuples) != count or len(field["source_cell_ids"]) != count: raise PDEInputError("Incomplete native cell tuples")
    for source, nodes in zip(field["source_cell_ids"], tuples):
        if not isinstance(nodes, list) or len(nodes) != 3 or len(_ids(nodes, "native cell DOFs", size=size)) != 3 or {to_source[node] for node in nodes} != set(geometry["cells"][source]["node_ids"]):
            raise PDEInputError("Native cell geometry/DOF tuple differs from exact original connectivity")
    boundaries = _keys(field["boundaries"], mesh["boundaries"], "native physical boundaries")
    selected, facets_seen, error, pointwise = set(), set(), 0., True
    problem = settings["problem"]
    for name, info in geometry["groups"].items():
        row = _keys(boundaries[name], BOUNDARY_KEYS, "complete actual physical boundary")
        facets = row["facet_ids"]
        if len(_ids(facets, "native boundary facets", size=geometry["edge_count"])) != len(info["source_element_ids"]) or facets != sorted(facets) or set(facets) & facets_seen:
            raise PDEInputError("Native physical facet coverage overlaps or differs")
        facets_seen.update(facets)
        elements = row["source_element_ids"]
        if _positive_ids(elements, "source exterior elements") != info["source_element_ids"] or len(elements) != len(facets):
            raise PDEInputError("Exact native/source exterior element bijection differs")
        endpoints = row["facet_node_ids"]
        original_elements = {item["id"]: item for item in mesh["boundaries"][name]["elements"]}
        if not isinstance(endpoints, list) or len(endpoints) != len(elements): raise PDEInputError("Incomplete native facet tuples")
        for identifier, pair in zip(elements, endpoints):
            if not isinstance(pair, list) or len(pair) != 2 or len(_ids(pair, "native facet DOFs", size=size)) != 2 or {to_source[node] for node in pair} != set(original_elements[identifier]["node_ids"]):
                raise PDEInputError("Native facet endpoint identities differ from original named lines")
        dofs = row["dof_ids"]
        if _ids(dofs, "native boundary DOFs", size=size) != {node for node in ids if to_source[node] in info["node_ids"]} or dofs != sorted(dofs):
            raise PDEInputError("Native named boundary scalar DOFs differ")
        _same(row["measure"], info["measure"], "actual physical boundary measure")
        if not isinstance(row["normal_integral"], list) or len(row["normal_integral"]) != 2: raise PDEInputError("Incomplete native outward normal")
        for actual, expected in zip(row["normal_integral"], info["normal_integral"]): _same(actual, expected, "actual polygon outward normal integral")
        inputs = row["prescribed_values"]
        if not isinstance(inputs, list) or len(inputs) != len(dofs): raise PDEInputError("Incomplete physical boundary input values")
        for node, actual in zip(dofs, inputs):
            expected = expression_value(problem["boundaries"][name]["value"], *xyz[node])
            _same(actual, expected, "actual prescribed boundary expression")
            if problem["boundaries"][name]["type"] == "dirichlet":
                selected.add(node)
                error = max(error, abs(values[node]-expected))
                pointwise = pointwise and math.isclose(values[node], expected, rel_tol=ATOL, abs_tol=ATOL)
        _number(row["prescribed_integral"], "actual prescribed group integral")
    if _ids(field["dirichlet_node_ids"], "native Dirichlet union", size=size) != selected or field["dirichlet_node_ids"] != sorted(selected):
        raise PDEInputError("Native Dirichlet selection differs from the exact physical-group union")
    if any(study[key] != expected for key, expected in (("global_nodes", size), ("global_dofs", size), ("global_cells", count), ("dirichlet_nodes", len(selected)), ("dirichlet_dofs", len(selected)))):
        raise PDEInputError("Actual native count summaries differ from full fields")
    _same(study["max_edge_h"], geometry["max_edge_h"], "actual original/native maximum edge")
    _same(study["boundary_value_error"], error, "independently recomputed Dirichlet field error")
    _mapping_check(mesh, field, mapping)
    _keys(binding, BINDING_KEYS, "complete scalar source binding")
    _ids(binding["node_ids"], "bound native scalar DOFs", size=size)
    _positive_ids(binding["source_node_ids"], "bound source node IDs")
    if binding["schema_version"] != "1" or binding["source_sha256"] != mesh["source_sha256"] or binding["dense_sha256"] != mapping["dense_sha256"] or binding["node_ids"] != ids or binding["source_node_ids"] != source_ids:
        raise PDEInputError("Actual scalar input binding identity/rows differ")
    coefficients = _keys(study["coefficients"], {"diffusion", "reaction"}, "actual scalar coefficients")
    for key in ("diffusion", "reaction"):
        _same(binding[key], problem["weak_form"][key], "actual native Constant")
        _same(coefficients[key], binding[key], "observed native Constant")
    for key, source in (("rhs_values", problem["weak_form"]["rhs"]), ("reference_values", problem["reference"]["solution"])):
        inputs = binding[key]
        if not isinstance(inputs, list) or len(inputs) != size: raise PDEInputError("Incomplete source/reference native binding")
        for node, actual in zip(ids, inputs): _same(actual, expression_value(source, *xyz[node]), "actual scalar RHS/reference expression")
    if study["physical_groups"] != mapping["physical_groups"] or study["source_sha256"] != mesh["source_sha256"] or study["dense_sha256"] != mapping["dense_sha256"]:
        raise PDEInputError("Actual study import identities differ from retained mapping")
    sync = _keys(study["solution_synchronization"], {"max_abs_difference", "passed"}, "actual solved-vector synchronization")
    maximum = _number(sync["max_abs_difference"], "actual solved-vector difference", nonnegative=True)
    if sync["passed"] is not True or maximum > ATOL+ATOL*max(abs(value) for value in values.values()):
        raise PDEInputError("Actual constrained x and saved scalar Function synchronization differs")
    return error, pointwise


def assess(settings, meshes, studies, fields, bindings, mappings):
    normalized = validate_settings(settings, meshes)
    geometry = mesh_series(meshes)
    if any(not isinstance(rows, list) or len(rows) != len(meshes) for rows in (studies, fields, bindings, mappings)):
        raise PDEInputError("Complete imported native observations are required for every level")
    observed, boundary_checks, residuals = copy.deepcopy(studies), [], []
    for i, (mesh, info, study, field, binding, mapping) in enumerate(zip(meshes, geometry, observed, fields, bindings, mappings)):
        if not isinstance(study, dict) or not STUDY_KEYS <= set(study): raise PDEInputError("Incomplete actual imported study observations")
        for key in ("level", "degree", "global_cells", "global_nodes", "global_dofs", "dirichlet_nodes", "dirichlet_dofs", "ksp_convergence_reason", "ksp_iterations"):
            if type(study[key]) is not int or (key != "ksp_convergence_reason" and study[key] < 0): raise PDEInputError("Malformed actual native integer observation")
        if study["level"] != i or study["degree"] != 1 or study["cell_type"] != "triangle" or study["solver_policy"] != {"ksp_type": "preonly", "pc_type": "lu"}:
            raise PDEInputError("Actual imported study identity or native solver policy differs")
        for key in ("l2_error", "h1_seminorm_error", "boundary_value_error"): _number(study[key], key, nonnegative=True)
        error, passed = _field_check(normalized, mesh, info, study, field, binding, mapping)
        study["recomputed_boundary_value_error"] = error
        boundary_checks.append({"level": i, "observed": error, "pointwise_passed": passed})
        residual = _keys(study["linear_residual"], {"absolute", "rhs_norm", "relative", "normalization"}, "actual constrained residual")
        for key in ("absolute", "rhs_norm", "relative"): _number(residual[key], key, nonnegative=True)
        expected = residual["absolute"]/residual["rhs_norm"] if residual["rhs_norm"] > 0 else residual["absolute"]
        if residual["normalization"] != ("rhs_l2_norm" if residual["rhs_norm"] > 0 else "absolute_for_zero_rhs"):
            raise PDEInputError("Actual constrained residual normalization differs")
        if not math.isclose(residual["relative"], expected, rel_tol=ATOL, abs_tol=0.): raise PDEInputError("Actual constrained residual is internally inconsistent")
        residuals.append(max(expected, residual["relative"]))
        for metric, rate in (("l2_error", "l2_convergence_rate"), ("h1_seminorm_error", "h1_seminorm_convergence_rate")):
            expected_rate = convergence_rate(observed[i-1][metric], study[metric], geometry[i-1]["max_edge_h"], info["max_edge_h"]) if i else None
            if expected_rate is None:
                if study[rate] is not None: raise PDEInputError("Zero error or initial level cannot establish an order")
            else:
                _same(study[rate], expected_rate, "every actual-h adjacent mesh convergence order")
    limits, fine = normalized["validation"], observed[-1]
    l2_rates, h1_rates = [row["l2_convergence_rate"] for row in observed[1:]], [row["h1_seminorm_convergence_rate"] for row in observed[1:]]
    numerical = [("pde_solver_convergence", all(row["ksp_convergence_reason"] > 0 for row in observed), [row["ksp_convergence_reason"] for row in observed], "Positive native KSP reason"),
                 ("pde_boundary_and_mesh", all(row["pointwise_passed"] for row in boundary_checks), boundary_checks, "Complete source/native bijections and pointwise Dirichlet abs/rel1e-12"),
                 ("pde_analytical_l2_error", fine["l2_error"] <= limits["max_l2_error"], fine["l2_error"], limits["max_l2_error"]),
                 ("pde_analytical_h1_seminorm_error", fine["h1_seminorm_error"] <= limits["max_h1_seminorm_error"], fine["h1_seminorm_error"], limits["max_h1_seminorm_error"]),
                 ("pde_l2_convergence_rate", all(rate is not None and rate >= limits["min_l2_rate"] for rate in l2_rates), l2_rates, limits["min_l2_rate"]),
                 ("pde_h1_seminorm_convergence_rate", all(rate is not None and rate >= limits["min_h1_rate"] for rate in h1_rates), h1_rates, limits["min_h1_rate"]),
                 ("pde_linear_residual", max(residuals) <= limits["max_residual_relative"], residuals, limits["max_residual_relative"])]
    checks = [{"code": code, "status": "PASS" if passed else "FAIL", "observed": value, "limit": limit} for code, passed, value, limit in numerical]
    passed = all(row["status"] == "PASS" for row in checks)
    reason = ", ".join(row["code"] for row in checks if row["status"] == "FAIL")
    metric_values = {"l2_error": fine["l2_error"], "h1_seminorm_error": fine["h1_seminorm_error"], "l2_convergence_rate": fine["l2_convergence_rate"], "h1_seminorm_convergence_rate": fine["h1_seminorm_convergence_rate"], "linear_residual_relative": max(residuals)}
    return {"checks": checks, "metrics": {name: {"value": value, "unit": "1", "valid": passed, **({"reason": "Imported scalar numerical validation failed: "+reason} if not passed else {})} for name, value in metric_values.items()},
            "mesh_studies": observed, "reference": {**copy.deepcopy(normalized["problem"]["reference"]), "domain": copy.deepcopy(normalized["problem"]["domain"]),
                "diffusion": normalized["problem"]["weak_form"]["diffusion"], "reaction": normalized["problem"]["weak_form"]["reaction"], "units": "dimensionless",
                "neumann_semantics": "diffusion*grad(u).outward_normal", "h1_semantics": "full gradient seminorm", "error_quadrature_degree": 8,
                "rate_semantics": "Every actual max-edge-h mesh pair must pass"}, "pending_validations": ["physical_validation", "model_qualification"], "limitations": list(LIMITATIONS)}
