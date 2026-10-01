"""Bounded, solver-independent HEXA20 catalogue for the frozen solid families.

The numerical helpers deliberately depend only on the Python standard library:
the same source is copied into the isolated Code_Aster worker. Domain and file
access occur only when constructing/checking a catalogue. Native numbering is
an adapter concern; stress points must be matched by physical coordinates.
"""

from __future__ import annotations

import math


HEXA20_NATURAL_NODES = (
    (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
    (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
    (0, -1, -1), (1, 0, -1), (0, 1, -1), (-1, 0, -1),
    (0, -1, 1), (1, 0, 1), (0, 1, 1), (-1, 0, 1),
    (-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0),
)
_QUAD8_NATURAL_NODES = ((-1, -1), (1, -1), (1, 1), (-1, 1),
                        (0, -1), (1, 0), (0, 1), (-1, 0))
_ABSCISSA = (-math.sqrt(3 / 5), 0.0, math.sqrt(3 / 5))
_WEIGHTS = (5 / 9, 8 / 9, 5 / 9)
# x fastest, y middle, z slowest. This is a helper convention, not a claim that
# every solver's native POINT number follows it.
GAUSS27 = tuple((x, y, z, _WEIGHTS[i] * _WEIGHTS[j] * _WEIGHTS[k])
                for k, z in enumerate(_ABSCISSA)
                for j, y in enumerate(_ABSCISSA)
                for i, x in enumerate(_ABSCISSA))
GAUSS9 = tuple((x, y, _WEIGHTS[i] * _WEIGHTS[j])
               for j, y in enumerate(_ABSCISSA)
               for i, x in enumerate(_ABSCISSA))
_JACOBIAN_POINTS = tuple(p[:3] for p in GAUSS27) + tuple(
    (x, y, z) for z in (-1.0, 0.0, 1.0)
    for y in (-1.0, 0.0, 1.0) for x in (-1.0, 0.0, 1.0))

# Gmsh's official HEXA20 diagram gives edges (0,1),(0,3),(0,4),
# (1,2),(1,5),(2,3),(2,6),(3,7),(4,5),(4,7),(5,6),(6,7).
# https://gmsh.info/doc/texinfo/#Node-ordering (Hexahedron20).
# Canonical C3D20 edges are bottom, top, vertical instead.
GMSH_HEXA20_FROM_CANONICAL = (
    0, 1, 2, 3, 4, 5, 6, 7, 8, 11, 16, 9, 17, 10, 18, 19, 12, 15, 13, 14,
)


def _finite_vector(value, length, name):
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise ValueError(f"{name} must contain exactly {length} numbers")
    converted = []
    for v in value:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"{name} must contain finite numbers")
        try:
            number = float(v)
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"{name} contains an unrepresentable number") from exc
        if not math.isfinite(number):
            raise ValueError(f"{name} must contain finite numbers")
        converted.append(number)
    return tuple(converted)


def hexa20_shape(point):
    """Return 20 serendipity weights and their 20x3 natural derivatives."""
    r, s, t = _finite_vector(point, 3, "natural point")
    values, gradients = [], []
    for a, b, c in HEXA20_NATURAL_NODES:
        if a and b and c:
            ar, bs, ct = a * r, b * s, c * t
            values.append((1 + ar) * (1 + bs) * (1 + ct)
                          * (ar + bs + ct - 2) / 8)
            gradients.append((
                a * (1 + bs) * (1 + ct) * (2 * ar + bs + ct - 1) / 8,
                b * (1 + ar) * (1 + ct) * (ar + 2 * bs + ct - 1) / 8,
                c * (1 + ar) * (1 + bs) * (ar + bs + 2 * ct - 1) / 8,
            ))
        elif not a:
            values.append((1 - r * r) * (1 + b * s) * (1 + c * t) / 4)
            gradients.append((-r * (1 + b * s) * (1 + c * t) / 2,
                              b * (1 - r * r) * (1 + c * t) / 4,
                              c * (1 - r * r) * (1 + b * s) / 4))
        elif not b:
            values.append((1 + a * r) * (1 - s * s) * (1 + c * t) / 4)
            gradients.append((a * (1 - s * s) * (1 + c * t) / 4,
                              -s * (1 + a * r) * (1 + c * t) / 2,
                              c * (1 + a * r) * (1 - s * s) / 4))
        else:
            values.append((1 + a * r) * (1 + b * s) * (1 - t * t) / 4)
            gradients.append((a * (1 + b * s) * (1 - t * t) / 4,
                              b * (1 + a * r) * (1 - t * t) / 4,
                              -t * (1 + a * r) * (1 + b * s) / 2))
    if not all(math.isfinite(v) for v in values + [v for row in gradients for v in row]):
        raise ValueError("nonfinite HEXA20 shape function")
    return tuple(values), tuple(gradients)


def hexa20_point_coordinates(coordinates, point):
    """Interpolate a physical point from the checked canonical 20-node order."""
    if not isinstance(coordinates, (list, tuple)) or len(coordinates) != 20:
        raise ValueError("HEXA20 coordinates must contain exactly 20 rows")
    rows = [_finite_vector(row, 3, "node coordinates") for row in coordinates]
    values, _ = hexa20_shape(point)
    result = [math.fsum(n * row[axis] for n, row in zip(values, rows))
              for axis in range(3)]
    if not all(math.isfinite(v) for v in result):
        raise ValueError("nonfinite interpolated coordinates")
    return result


def quad8_shape(point):
    """Return QUAD8 weights/derivatives in counterclockwise face order."""
    u, v = _finite_vector(point, 2, "face point")
    values, gradients = [], []
    for a, b in _QUAD8_NATURAL_NODES:
        if a and b:
            au, bv = a * u, b * v
            values.append((1 + au) * (1 + bv) * (au + bv - 1) / 4)
            gradients.append((a * (1 + bv) * (2 * au + bv) / 4,
                              b * (1 + au) * (au + 2 * bv) / 4))
        elif not a:
            values.append((1 - u * u) * (1 + b * v) / 2)
            gradients.append((-u * (1 + b * v), b * (1 - u * u) / 2))
        else:
            values.append((1 + a * u) * (1 - v * v) / 2)
            gradients.append((a * (1 - v * v) / 2, -v * (1 + a * u)))
    if not all(math.isfinite(v) for v in values + [v for row in gradients for v in row]):
        raise ValueError("nonfinite QUAD8 shape function")
    return tuple(values), tuple(gradients)


shape20 = hexa20_shape


def _context(settings, cells):
    # Lazy imports preserve the isolated worker's pure helper interface.
    import json
    from pathlib import Path
    from plugins.structural_families.reference import case_definition, validate_settings

    canonical = validate_settings(settings)
    definition = json.loads((Path(__file__).resolve().parents[2]
                             / "benchmarks/specifications/structural-families-v1.json")
                            .read_text(encoding="utf-8"))
    limits = definition["execution_limits"]
    if not isinstance(cells, (list, tuple)) or len(cells) != 3:
        raise ValueError("cells must be a three-axis grid")
    if any(type(n) is not int or n < 1 or n > limits["max_axis_cells"]
           for n in cells):
        raise ValueError("cells exceed the frozen axis workload")
    nx, ny, nz = cells
    count = ((nx + 1) * (ny + 1) * (nz + 1)
             + nx * (ny + 1) * (nz + 1)
             + (nx + 1) * ny * (nz + 1)
             + (nx + 1) * (ny + 1) * nz)
    if nx * ny * nz > limits["max_elements_per_level"] or count > limits["max_nodes_per_level"]:
        raise ValueError("cells exceed the frozen element/node workload")
    if list(cells) not in canonical["mesh_cells"]:
        raise ValueError("cells are not a declared level in settings")
    raw_case = case_definition(canonical["case"])
    if raw_case != definition["cases"][canonical["case"]]:
        raise ValueError("domain case differs from frozen public definition")
    return canonical, raw_case, definition, tuple(cells)


def _geometry(case, raw, units):
    g = raw["geometry"]
    if case == "ansys_vmd1_regular":
        lengths = [v * units["in_to_mm"] for v in g["dimensions_in"]]
        return lambda a, b, c: [a * lengths[0], b * lengths[1], c * lengths[2]], lengths
    angles = [math.radians(v) for v in g["angle_degrees"]]
    if case == "lame_cylinder_plane_strain":
        ri, ro, height = g["inner_radius_mm"], g["outer_radius_mm"], g["height_mm"]

        def cylinder(a, b, c):
            r, theta = ri + a * (ro - ri), angles[0] + b * (angles[1] - angles[0])
            cosine = 0.0 if b == 1.0 and g["angle_degrees"][1] == 90.0 else math.cos(theta)
            return [r * cosine, r * math.sin(theta), c * height]

        return cylinder, (ri, ro, height, *angles)
    if case == "scordelis_lo_solid":
        length = g["longitudinal_half_length_ft"] * units["ft_to_mm"]
        radius = g["midsurface_radius_ft"] * units["ft_to_mm"]
        thickness = g["thickness_ft"] * units["ft_to_mm"]
        ri, ro = radius - thickness / 2, radius + thickness / 2

        def roof(a, b, c):
            r, theta = ri + c * (ro - ri), angles[0] + b * (angles[1] - angles[0])
            return [a * length, r * math.sin(theta), r * math.cos(theta)]

        return roof, (ri, ro, length, *angles)
    raise ValueError("unsupported frozen geometry")


def _topology(settings, raw, units, cells):
    nx, ny, nz = cells
    coordinate, geometry = _geometry(settings["case"], raw, units)
    nodes, indices = [], {}
    for k in range(2 * nz + 1):
        for j in range(2 * ny + 1):
            for i in range(2 * nx + 1):
                if sum(v % 2 for v in (i, j, k)) <= 1:
                    node_id = len(nodes) + 1
                    indices[(i, j, k)] = node_id
                    nodes.append({"id": node_id,
                                  "coordinates_mm": coordinate(i / (2 * nx), j / (2 * ny), k / (2 * nz))})
    elements, element_indices = [], []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                elements.append({"id": len(elements) + 1, "node_ids": [
                    indices[(2 * i + r + 1, 2 * j + s + 1, 2 * k + t + 1)]
                    for r, s, t in HEXA20_NATURAL_NODES]})
                element_indices.append((i, j, k))

    def selected(predicate):
        return sorted(node_id for index, node_id in indices.items() if predicate(*index))

    groups = {"ALL_NODES": list(range(1, len(nodes) + 1))}
    support_sets = []
    case = settings["case"]
    if case == "ansys_vmd1_regular":
        groups.update(ROOT=selected(lambda i, j, k: i == 0),
                      TIP=selected(lambda i, j, k: i == 2 * nx))
        support_sets = [(groups["ROOT"], [1, 2, 3])]
        responses = {"tip": [indices[(2 * nx, 0, 0)], indices[(2 * nx, 2 * ny, 0)]]}
    elif case == "lame_cylinder_plane_strain":
        groups.update(INNER=selected(lambda i, j, k: i == 0),
                      OUTER=selected(lambda i, j, k: i == 2 * nx),
                      X_SYMMETRY=selected(lambda i, j, k: j == 2 * ny),
                      Y_SYMMETRY=selected(lambda i, j, k: j == 0))
        support_sets = [(groups["X_SYMMETRY"], [1]), (groups["Y_SYMMETRY"], [2]),
                        (groups["ALL_NODES"], [3])]
        responses = {"inner": list(groups["INNER"]), "outer": list(groups["OUTER"])}
    else:
        groups.update(DIAPHRAGM=selected(lambda i, j, k: i == 0),
                      LONGITUDINAL_SYMMETRY=selected(lambda i, j, k: i == 2 * nx),
                      CROWN=selected(lambda i, j, k: j == 0),
                      INNER=selected(lambda i, j, k: k == 0),
                      OUTER=selected(lambda i, j, k: k == 2 * nz),
                      POINT_B=[indices[(2 * nx, 2 * ny, 0)]])
        support_sets = [(groups["DIAPHRAGM"], [2, 3]),
                        (groups["LONGITUDINAL_SYMMETRY"], [1]), (groups["CROWN"], [2])]
        responses = {"point_b": list(groups["POINT_B"])}
    by_node = {}
    for node_ids, components in support_sets:
        for node_id in node_ids:
            by_node.setdefault(node_id, set()).update(components)
    supports = [{"node_id": node_id, "components": sorted(components)}
                for node_id, components in sorted(by_node.items())]
    return nodes, elements, groups, supports, responses, element_indices, geometry


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _continuous_reference(settings, raw, units, geometry):
    case, factor = settings["case"], settings["load_factor"]
    load = raw["load_cases"][settings["load_case"]]
    if case == "ansys_vmd1_regular":
        lx, ly, lz = geometry
        force = [0.0, 0.0, 0.0]
        force["xyz".index(load["component"])] = load["force_lbf"] * units["lbf_to_n"] * factor
        return lx * ly * lz, force, _cross([lx, ly / 2, lz / 2], force), ly * lz
    ri, ro, extent, a0, a1 = geometry
    volume = extent * (ro * ro - ri * ri) * (a1 - a0) / 2
    if case == "lame_cylinder_plane_strain":
        pressure = load["pressure_mpa"] * factor
        force = [pressure * ri * extent * (math.sin(a1) - math.sin(a0)),
                 pressure * ri * extent * (math.cos(a0) - math.cos(a1)), 0.0]
        return volume, force, [-extent / 2 * force[1], extent / 2 * force[0], 0.0], ri * extent * (a1 - a0)
    density = load["weight_density_lbf_per_ft3"] * units["lbf_to_n"] / units["ft_to_mm"] ** 3 * factor
    first_y = extent * (ro ** 3 - ri ** 3) * (math.cos(a0) - math.cos(a1)) / 3
    force = [0.0, 0.0, -density * volume]
    moment = [-density * first_y, density * extent / 2 * volume, 0.0]
    return volume, force, moment, None


def _integrate(settings, raw, definition, nodes, elements, element_indices, geometry):
    # NumPy is an existing project dependency; it is not imported by pure helpers.
    import numpy as np

    coordinates = np.asarray([node["coordinates_mm"] for node in nodes], dtype=float)
    connectivity = np.asarray([element["node_ids"] for element in elements], dtype=int) - 1
    local = coordinates[connectivity]
    shapes = np.asarray([hexa20_shape(p[:3])[0] for p in GAUSS27])
    gradients = np.asarray([hexa20_shape(p)[1] for p in _JACOBIAN_POINTS])
    jacobians = np.einsum("enk,pnj->epkj", local, gradients)
    determinants = np.linalg.det(jacobians)
    if not np.isfinite(determinants).all() or (determinants <= 0).any():
        raise ValueError("nonpositive/nonfinite sampled HEXA20 Jacobian; "
                         f"minimum_sampled_jacobian_mm3={float(np.min(determinants))!r}")
    volume_weights = determinants[:, :27] * np.asarray([p[3] for p in GAUSS27])
    volume = float(np.sum(volume_weights))
    forces = np.zeros_like(coordinates)
    case = settings["case"]
    units = definition["unit_conversion"]
    expected_volume, expected_force, expected_moment, expected_area = _continuous_reference(settings, raw, units, geometry)
    surface_area = None
    if case == "scordelis_lo_solid":
        load = raw["load_cases"][settings["load_case"]]
        density = load["weight_density_lbf_per_ft3"] * units["lbf_to_n"] / units["ft_to_mm"] ** 3 * settings["load_factor"]
        weights = np.einsum("pn,ep->en", shapes, volume_weights)
        local_force = weights[:, :, None] * np.asarray(load["direction"])[None, None, :] * density
        np.add.at(forces, connectivity.ravel(), local_force.reshape(-1, 3))
        method = "HEXA20_FPG27_body_force"
    else:
        if case == "ansys_vmd1_regular":
            face_order = [1, 2, 6, 5, 9, 18, 13, 17]
            selected = [i for i, index in enumerate(element_indices) if index[0] == settings["_cells"][0] - 1]
        else:
            face_order = [0, 3, 7, 4, 11, 19, 15, 16]
            selected = [i for i, index in enumerate(element_indices) if index[0] == 0]
        face_ids = connectivity[np.asarray(selected)][:, face_order]
        face_coordinates = coordinates[face_ids]
        face_shapes = np.asarray([quad8_shape(p[:2])[0] for p in GAUSS9])
        face_gradients = np.asarray([quad8_shape(p[:2])[1] for p in GAUSS9])
        tangents = np.einsum("enk,pnj->epkj", face_coordinates, face_gradients)
        area_vectors = np.cross(tangents[:, :, :, 0], tangents[:, :, :, 1])
        magnitudes = np.linalg.norm(area_vectors, axis=2)
        if not np.isfinite(magnitudes).all() or (magnitudes <= 0).any():
            raise ValueError("nonpositive/nonfinite loaded face area")
        weights = np.asarray([p[2] for p in GAUSS9])
        surface_area = float(np.sum(magnitudes * weights))
        if case == "ansys_vmd1_regular":
            integrated_vectors = magnitudes[:, :, None] * (np.asarray(expected_force) / expected_area)
            method = "QUAD8_FPG9_constant_face_traction"
        else:
            # The chosen theta/z face orientation is outward radial: pressure
            # acts opposite the outward INNER-material normal. Retain its
            # consistent area vector, not a chord/radial average or equal shares.
            pressure = raw["load_cases"][settings["load_case"]]["pressure_mpa"] * settings["load_factor"]
            integrated_vectors = pressure * area_vectors
            method = "QUAD8_FPG9_inner_pressure_outward_radial"
        local_force = np.einsum("pn,epc,p->enc", face_shapes, integrated_vectors, weights)
        np.add.at(forces, face_ids.ravel(), local_force.reshape(-1, 3))
    if not np.isfinite(forces).all() or not math.isfinite(volume):
        raise ValueError("nonfinite integrated geometry/loads")
    resultant = [math.fsum(float(v) for v in forces[:, axis]) for axis in range(3)]
    moment_rows = np.cross(coordinates, forces)
    moment = [math.fsum(float(v) for v in moment_rows[:, axis]) for axis in range(3)]
    norm = lambda vector: math.hypot(*vector)
    force_scale = max(norm(expected_force), 1e-12)
    moment_scale = max(force_scale * definition["normalization"]["characteristic_length_mm"][case], 1e-12)
    volume_error = abs(volume - expected_volume) / expected_volume
    force_error = norm([a - b for a, b in zip(resultant, expected_force)]) / force_scale
    moment_error = norm([a - b for a, b in zip(moment, expected_moment)]) / moment_scale
    limit = definition["numerical_limits"]["mesh_volume_relative"]
    area_error = None if expected_area is None else abs(surface_area - expected_area) / expected_area
    values = [expected_volume, volume, *expected_force, *expected_moment,
              volume_error, force_error, moment_error]
    if not all(math.isfinite(v) for v in values) or expected_volume <= 0 or norm(expected_force) == 0:
        raise ValueError("nonfinite/unrepresentable continuous reference")
    if any(error > limit for error in (volume_error, force_error, moment_error)) or (area_error is not None and area_error > limit):
        raise ValueError("quadratic geometry/load integral exceeds frozen analytic limit; "
                         f"volume_mm3={volume!r}, analytical_volume_mm3={expected_volume!r}, "
                         f"volume_relative_error={volume_error!r}, "
                         f"applied_force_n={resultant!r}, applied_moment_n_mm={moment!r}, "
                         f"force_relative_error={force_error!r}, moment_relative_error={moment_error!r}, "
                         f"area_relative_error={area_error!r}, limit={limit!r}")
    checks = {
        "positive_sampled_jacobians": True,
        "jacobian_sample_count_per_element": len(_JACOBIAN_POINTS),
        "minimum_sampled_jacobian_mm3": float(np.min(determinants)),
        "volume_mm3": volume, "analytical_volume_mm3": expected_volume,
        "volume_relative_error": volume_error,
        "loaded_area_mm2": surface_area, "analytical_loaded_area_mm2": expected_area,
        "loaded_area_relative_error": area_error,
        "applied_force_n": resultant, "applied_moment_n_mm": moment,
        "analytical_force_n": expected_force, "analytical_moment_n_mm": expected_moment,
        "applied_force_relative_error": force_error, "applied_moment_relative_error": moment_error,
        "analytic_integral_relative_limit": limit, "equivalent_nodal_load_method": method,
        "jacobian_limitation": "Positive at FPG27 and tensor {-1,0,1} samples; not a proof at every continuum point.",
    }
    loads = [{"node_id": node["id"], "value": [float(v) for v in forces[i]]}
             for i, node in enumerate(nodes)]
    return loads, checks


def _catalogue(settings, raw, definition, cells):
    nodes, elements, groups, supports, responses, indices, geometry = _topology(
        settings, raw, definition["unit_conversion"], cells)
    internal = dict(settings, _cells=cells)
    loads, checks = _integrate(internal, raw, definition, nodes, elements, indices, geometry)
    return {"schema_version": "1", "case": settings["case"], "cells": list(cells),
            "element_type": "HEXA20", "nodes": nodes, "elements": elements,
            "groups": groups, "supports": supports, "nodal_loads_n": loads,
            "response_node_ids": responses, "checks": checks}


def build_mesh(settings, cells):
    """Build a new deterministic catalogue, refusing undeclared/bounded workloads."""
    canonical, raw, definition, cells = _context(settings, cells)
    return _catalogue(canonical, raw, definition, cells)


def check_mesh(mesh, settings):
    """Recompute catalogue and analytic checks; raise ValueError on any mismatch.

    Shape, IDs, connectivity, coordinates, DOFs, exact response selections and
    every signed nodal load are compared, not merely their global resultant.
    The returned checks are fresh; caller-supplied positive flags are not trusted.
    """
    if not isinstance(mesh, dict):
        raise ValueError("mesh must be a catalogue object")
    canonical, raw, definition, cells = _context(settings, mesh.get("cells"))
    expected = _catalogue(canonical, raw, definition, cells)
    if not _strict_equal(mesh, expected):
        raise ValueError("mesh differs from the deterministic frozen catalogue")
    return expected["checks"]


def _strict_equal(actual, expected):
    # Python's True == 1 and 0 == 0.0 must not permit type aliases in IDs,
    # coordinates, support DOFs or machine-readable check flags.
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            _strict_equal(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _strict_equal(a, b) for a, b in zip(actual, expected))
    return actual == expected


def _export_rows(mesh):
    """Refuse malformed export data even when called without Domain settings."""
    if not isinstance(mesh, dict) or mesh.get("schema_version") != "1" or mesh.get("element_type") != "HEXA20":
        raise ValueError("unsupported mesh catalogue")
    nodes, elements, groups = mesh.get("nodes"), mesh.get("elements"), mesh.get("groups")
    if not isinstance(nodes, list) or not nodes or not isinstance(elements, list) or not elements or not isinstance(groups, dict):
        raise ValueError("incomplete mesh catalogue")
    for i, row in enumerate(nodes, 1):
        if not isinstance(row, dict) or set(row) != {"id", "coordinates_mm"} or type(row["id"]) is not int or row["id"] != i:
            raise ValueError("noncanonical node IDs")
        _finite_vector(row["coordinates_mm"], 3, "node coordinates")
    used = set()
    for i, row in enumerate(elements, 1):
        if not isinstance(row, dict) or set(row) != {"id", "node_ids"} or type(row["id"]) is not int or row["id"] != i:
            raise ValueError("noncanonical element IDs")
        ids = row["node_ids"]
        if not isinstance(ids, list) or len(ids) != 20 or any(type(v) is not int or not 1 <= v <= len(nodes) for v in ids) or len(set(ids)) != 20:
            raise ValueError("invalid HEXA20 connectivity")
        used.update(ids)
    if used != set(range(1, len(nodes) + 1)):
        raise ValueError("orphan/missing mesh nodes")
    for name, ids in groups.items():
        if not isinstance(name, str) or not name or not name.replace("_", "").isalnum() or name.startswith("CAE_") or name == "SOLID":
            raise ValueError("invalid/reserved physical group name")
        if not isinstance(ids, list) or not ids or any(type(v) is not int or not 1 <= v <= len(nodes) for v in ids) or ids != sorted(set(ids)):
            raise ValueError("invalid physical group node IDs")
    return nodes, elements, groups


def write_gmsh(mesh, path):
    """Write a new ASCII MSH2.2: HEXA20 SOLID and exact POI1 node groups.

    Type17 is HEXA20; type15 is POI1. Physical/geometrical tags are identical
    for each group so an importer retaining both tags cannot merge two groups.
    A global node shared by groups has a distinct POI1 element for each group.
    https://gmsh.info/doc/texinfo/#MSH-file-format-version-2
    """
    from pathlib import Path

    nodes, elements, groups = _export_rows(mesh)
    physical = {"SOLID": {"dimension": 3, "tag": 1}}
    physical.update({name: {"dimension": 0, "tag": i}
                     for i, name in enumerate(sorted(groups), 2)})
    point_ids = {}
    lines = ["$MeshFormat", "2.2 0 8", "$EndMeshFormat", "$PhysicalNames", str(len(physical))]
    lines.extend(f'{row["dimension"]} {row["tag"]} "{name}"' for name, row in physical.items())
    lines.extend(["$EndPhysicalNames", "$Nodes", str(len(nodes))])
    lines.extend(f'{node["id"]} ' + " ".join(format(v, ".17g") for v in node["coordinates_mm"]) for node in nodes)
    lines.extend(["$EndNodes", "$Elements", str(len(elements) + sum(map(len, groups.values())))])
    for row in elements:
        ids = [row["node_ids"][i] for i in GMSH_HEXA20_FROM_CANONICAL]
        lines.append(f'{row["id"]} 17 2 1 1 ' + " ".join(map(str, ids)))
    next_id = len(elements) + 1
    for name in sorted(groups):
        tag, current = physical[name]["tag"], []
        for node_id in groups[name]:
            lines.append(f"{next_id} 15 2 {tag} {tag} {node_id}")
            current.append(next_id)
            next_id += 1
        point_ids[name] = current
    lines.append("$EndElements")
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")
    return {"format": "MSH2.2_ASCII", "physical_tags": physical,
            "volume_element_ids": [row["id"] for row in elements], "point_element_ids": point_ids}


def write_calculix_mesh(mesh, path):
    """Write a new C3D20 mesh include; supports/loads/material/step stay adapter-owned."""
    from pathlib import Path

    nodes, elements, groups = _export_rows(mesh)
    lines = ["** Frozen canonical HEXA20 catalogue; units mm, N", "*NODE"]
    # Official CalculiX2.21 nodes.f reads at most20 characters per coordinate.
    # Use14 significant figures and retain full precision in the JSON catalogue.
    for node in nodes:
        fields = [format(v, ".14g") for v in node["coordinates_mm"]]
        if any(len(field) > 20 for field in fields):
            raise ValueError("CalculiX coordinate exceeds official20-character field")
        lines.append(f'{node["id"]}, ' + ", ".join(fields))
    lines.append("*ELEMENT, TYPE=C3D20, ELSET=SOLID")
    for row in elements:
        # CalculiX permits continuation of C3D20 connectivity: 15 nodes on
        # the first line (16 entries including elementID), then five nodes.
        lines.append(", ".join(map(str, [row["id"], *row["node_ids"][:15]])) + ",")
        lines.append(", ".join(map(str, row["node_ids"][15:])))
    for name in sorted(groups):
        lines.append(f"*NSET, NSET={name}")
        ids = groups[name]
        lines.extend(", ".join(map(str, ids[i:i + 16])) for i in range(0, len(ids), 16))
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")
    return {"format": "CALCULIX_C3D20_INCLUDE", "element_ids": [row["id"] for row in elements],
            "node_groups": {name: list(ids) for name, ids in groups.items()}}
