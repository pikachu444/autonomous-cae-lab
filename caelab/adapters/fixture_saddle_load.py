"""Surface-area weighted load on the central roller saddle of a fixture mesh.

The input is Gmsh's Abaqus INP export containing CPS6 surface triangles.
Only an unambiguous, connected cylindrical surface with a complete half-round
boundary is accepted. The load is integrated over |y| <= half_width_mm on a
four-triangle linear tessellation of each quadratic face. It is a vertical
pressure idealization, not an actual contact or strength analysis.
"""

from __future__ import annotations

from collections import defaultdict, deque
import math
from pathlib import Path
import re
from typing import Any, Mapping


_ELEMENT = re.compile(r"^\*ELEMENT\b", re.IGNORECASE)
_TYPE = re.compile(r"\bTYPE\s*=\s*([A-Z0-9]+)", re.IGNORECASE)
_ELSET = re.compile(r"\bELSET\s*=\s*([A-Z0-9_]+)", re.IGNORECASE)
_SUBTRIANGLES = ((0, 3, 5), (3, 1, 4), (5, 4, 2), (3, 4, 5))
_MIDPOINTS = ((0, 1, 3), (1, 2, 4), (2, 0, 5))


def _surface_groups(path: Path) -> dict[str, list[tuple[int, tuple[int, ...]]]]:
    groups: dict[str, list[tuple[int, tuple[int, ...]]]] = defaultdict(list)
    section = None
    seen_ids = set()
    try:
        lines = Path(path).open(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ValueError(f"Cannot read mesh: {exc}") from exc
    with lines:
        for line_number, raw in enumerate(lines, 1):
            line = raw.strip()
            if not line or line.startswith("**"):
                continue
            if line.startswith("*"):
                section = None
                if _ELEMENT.match(line):
                    element_type, elset = _TYPE.search(line), _ELSET.search(line)
                    if element_type and element_type.group(1).upper() == "CPS6":
                        if not elset:
                            raise ValueError(f"CPS6 surface lacks an ELSET at line {line_number}")
                        section = elset.group(1).upper()
                continue
            if section is None:
                continue
            fields = [part.strip() for part in line.split(",")]
            if len(fields) != 7:
                raise ValueError(f"CPS6 face must have six nodes at line {line_number}")
            try:
                element_id, *face = map(int, fields)
            except ValueError as exc:
                raise ValueError(f"Invalid CPS6 connectivity at line {line_number}") from exc
            if element_id in seen_ids or len(set(face)) != 6:
                raise ValueError(f"Duplicate CPS6 element or node at line {line_number}")
            seen_ids.add(element_id)
            groups[section].append((element_id, tuple(face)))
    if not groups:
        raise ValueError("No CPS6 surface groups in Gmsh Abaqus mesh")
    return dict(groups)


def _area(a: tuple[float, ...], b: tuple[float, ...],
          c: tuple[float, ...]) -> float:
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    cross = (u[1] * v[2] - u[2] * v[1],
             u[2] * v[0] - u[0] * v[2],
             u[0] * v[1] - u[1] * v[0])
    return .5 * math.sqrt(sum(x * x for x in cross))


def _clip(polygon: list[tuple[tuple[float, float, float], tuple[float, float, float]]],
          limit: float, *, lower: bool):
    """Clip at a y plane, retaining each vertex's three linear shape weights."""
    if not polygon:
        return []

    def inside(vertex):
        return vertex[0][1] >= limit - 1e-10 if lower else vertex[0][1] <= limit + 1e-10

    result = []
    previous = polygon[-1]
    for current in polygon:
        before, after = inside(previous), inside(current)
        if before != after:
            denominator = current[0][1] - previous[0][1]
            if abs(denominator) < 1e-14:
                raise ValueError("Degenerate patch clipping edge")
            t = (limit - previous[0][1]) / denominator
            if t < -1e-9 or t > 1 + 1e-9:
                raise ValueError("Patch clipping intersection outside edge")
            t = min(1., max(0., t))
            point = tuple(previous[0][i] + t * (current[0][i] - previous[0][i])
                          for i in range(3))
            weights = tuple(previous[1][i] + t * (current[1][i] - previous[1][i])
                            for i in range(3))
            result.append((point, weights))
        if after:
            result.append(current)
        previous = current
    return result


def _check_topology(faces: list[tuple[int, tuple[int, ...]]], nodes: Mapping,
                    bbox: Any, radius: float, tolerance: float) -> None:
    edges: dict[tuple[int, int], list[tuple[int, int, int, int]]] = defaultdict(list)
    corners_seen = set()
    for face_index, (_, face) in enumerate(faces):
        corners = face[:3]
        key = tuple(sorted(corners))
        if key in corners_seen:
            raise ValueError("Duplicate saddle surface triangle")
        corners_seen.add(key)
        for a, b, midpoint in ((0, 1, 3), (1, 2, 4), (2, 0, 5)):
            first, second = corners[a], corners[b]
            edges[tuple(sorted((first, second)))].append(
                (face_index, first, second, face[midpoint]))
        for a, b, midpoint in _MIDPOINTS:
            xyz = nodes[face[midpoint]]
            target = tuple((nodes[face[a]][d] + nodes[face[b]][d]) / 2 for d in range(3))
            if math.dist(xyz, target) > 1e-5:
                raise ValueError("CPS6 midside node is not linear; unsupported load interpolation")
    neighbors = defaultdict(set)
    boundary = []
    for key, occurrences in edges.items():
        if len(occurrences) > 2:
            raise ValueError("Overlapping or nonmanifold saddle triangles")
        if len(occurrences) == 2:
            left, right = occurrences
            if left[1:3] == right[1:3]:
                raise ValueError("Adjacent saddle triangles have inconsistent orientation")
            if left[3] != right[3]:
                raise ValueError("Adjacent saddle triangles do not share their midside node")
            neighbors[left[0]].add(right[0])
            neighbors[right[0]].add(left[0])
        else:
            boundary.append(key)
    if not boundary:
        raise ValueError("Saddle patch has no boundary")
    connected = {0}
    queue = deque([0])
    while queue:
        for neighbor in neighbors[queue.popleft()]:
            if neighbor not in connected:
                connected.add(neighbor)
                queue.append(neighbor)
    if len(connected) != len(faces):
        raise ValueError("Disconnected saddle surface")
    cx = (bbox.xmin + bbox.xmax) / 2
    observed = {"ymin": 0, "ymax": 0, "left_lip": 0, "right_lip": 0}
    for first, second in boundary:
        a, b = nodes[first], nodes[second]
        if abs(a[1] - bbox.ymin) < tolerance and abs(b[1] - bbox.ymin) < tolerance:
            observed["ymin"] += 1
        elif abs(a[1] - bbox.ymax) < tolerance and abs(b[1] - bbox.ymax) < tolerance:
            observed["ymax"] += 1
        elif all(abs(x[0] - (cx - radius)) < tolerance and
                 abs(x[2] - bbox.zmax) < tolerance for x in (a, b)):
            observed["left_lip"] += 1
        elif all(abs(x[0] - (cx + radius)) < tolerance and
                 abs(x[2] - bbox.zmax) < tolerance for x in (a, b)):
            observed["right_lip"] += 1
        else:
            raise ValueError("Open interior edge in cylindrical saddle mesh")
    if not all(observed.values()):
        raise ValueError("Saddle boundary lacks an end or lip edge")


def saddle_nodal_forces(mesh: Path, nodes: Mapping[int, tuple[float, float, float]],
                        support_bbox: Any, radius_mm: float, force_N: float,
                        half_width_mm: float = 12.0) -> dict:
    """Return negative Z nodal forces and area/topology diagnostics.

    `nodal_loads` has integer node IDs and negative force values. `lip_force_fraction`
    is the load on nodes within 0.15 mm of either saddle lip at zmax, matching
    the former equal-node diagnostic. `outside_patch_force_fraction` records
    load assigned to midside nodes beyond |y|=half_width_mm by interpolation.
    """
    if any(type(value) not in (float, int) or not math.isfinite(value) or value <= 0
           for value in (radius_mm, force_N, half_width_mm)):
        raise ValueError("Positive finite radius, force and patch half-width required")
    if not nodes or not isinstance(nodes, Mapping):
        raise ValueError("Mesh node coordinate mapping required")
    bbox = support_bbox
    try:
        extent = (bbox.xmin, bbox.xmax, bbox.ymin, bbox.ymax, bbox.zmax)
        if not all(math.isfinite(v) for v in extent) or bbox.ymax - bbox.ymin < 2 * half_width_mm:
            raise ValueError("CAD support does not span the central load patch")
    except (AttributeError, TypeError) as exc:
        raise ValueError("CAD support bounding box required") from exc
    groups = _surface_groups(Path(mesh))
    center_x = (bbox.xmin + bbox.xmax) / 2
    tolerance = max(.02, radius_mm * .005)
    candidate_groups = []
    for name, faces in groups.items():
        is_cylinder = True
        for _, face in faces:
            for node_id in face:
                if node_id not in nodes or len(nodes[node_id]) != 3 or not all(
                        math.isfinite(v) for v in nodes[node_id]):
                    raise ValueError(f"Missing or invalid CPS6 node {node_id}")
            for node_id in face[:3]:
                x, y, z = nodes[node_id]
                if (abs(math.hypot(x - center_x, z - bbox.zmax) - radius_mm) > tolerance or
                        y < bbox.ymin - tolerance or y > bbox.ymax + tolerance):
                    is_cylinder = False
        if is_cylinder:
            candidate_groups.append(name)
    if len(candidate_groups) != 1:
        raise ValueError(f"Expected one cylindrical CPS6 ELSET; found {candidate_groups}")
    group_name = candidate_groups[0]
    faces = groups[group_name]
    _check_topology(faces, nodes, bbox, radius_mm, tolerance)

    weighted_areas: dict[int, float] = defaultdict(float)
    full_area = 0.0
    patch_area = 0.0
    for _, face in faces:
        for subtriangle in _SUBTRIANGLES:
            points = [nodes[face[index]] for index in subtriangle]
            face_area = _area(*points)
            if face_area <= 1e-11:
                raise ValueError("Degenerate CPS6 saddle subtriangle")
            full_area += face_area
            polygon = [(points[index], tuple(float(index == k) for k in range(3)))
                       for index in range(3)]
            polygon = _clip(polygon, -half_width_mm, lower=True)
            polygon = _clip(polygon, half_width_mm, lower=False)
            if len(polygon) < 3:
                continue
            for i in range(1, len(polygon) - 1):
                triangle = (polygon[0], polygon[i], polygon[i + 1])
                clipped_area = _area(*(vertex[0] for vertex in triangle))
                if clipped_area <= 1e-12:
                    continue
                patch_area += clipped_area
                for local, node_index in enumerate(subtriangle):
                    consistent_area = clipped_area / 3 * sum(v[1][local] for v in triangle)
                    weighted_areas[face[node_index]] += consistent_area
    expected_area = math.pi * radius_mm * 2 * half_width_mm
    relative_error = abs(patch_area / expected_area - 1)
    if patch_area <= 0 or relative_error > .12 or abs(sum(weighted_areas.values()) / patch_area - 1) > 1e-8:
        raise ValueError("Saddle patch area disagrees with half-cylinder CAD geometry")
    nodal_loads = {node_id: -force_N * area / patch_area
                   for node_id, area in weighted_areas.items() if area > 1e-12}
    if len(nodal_loads) < 10 or abs(sum(nodal_loads.values()) + force_N) > 1e-8 * force_N:
        raise ValueError("Saddle load is incomplete or does not balance")
    lip_load = sum(-force for node_id, force in nodal_loads.items()
                   if abs(abs(nodes[node_id][0] - center_x) - radius_mm) < .15
                   and abs(nodes[node_id][2] - bbox.zmax) < .15)
    outside_load = sum(-force for node_id, force in nodal_loads.items()
                       if abs(nodes[node_id][1]) > half_width_mm + 1e-8)
    return {"nodal_loads": dict(sorted(nodal_loads.items())),
            "loaded_node_ids": sorted(nodal_loads), "loaded_node_count": len(nodal_loads),
            "total_applied_force_N": -sum(nodal_loads.values()),
            "patch_area_mm2": patch_area, "full_saddle_area_mm2": full_area,
            "analytical_patch_area_mm2": expected_area,
            "patch_area_relative_error": relative_error,
            "lip_force_fraction": lip_load / force_N,
            "outside_patch_force_fraction": outside_load / force_N,
            "lip_tolerance_mm": .15, "patch_half_width_mm": half_width_mm,
            "surface_group": group_name, "face_count": len(faces),
            "force_method": "CPS6 -> four linear triangles; clip in y; integrate linear nodal shapes"}
