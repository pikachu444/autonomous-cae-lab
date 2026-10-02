"""Pure rectangle/input/field checks, independent of native FEniCSx syntax."""

from __future__ import annotations

from collections import Counter, defaultdict
import copy
import json
import math

if __name__ == "domain_reference":
    from fenicsx_expression import (FUNCTION_NAMES, PDEInputError, error_rate, finite_number,
                                    interpret_expression, parse_expression, validate_settings as _linear_settings)
else:
    from caelab.adapters.fenicsx_worker import (FUNCTION_NAMES, PDEInputError, error_rate, finite_number,
                                               interpret_expression, parse_expression, validate_settings as _linear_settings)


VERSION = "1"
SIDES = ("xmin", "xmax", "ymin", "ymax")
ATOL = 1e-12
_VALIDATIONS = {"max_l2_error", "min_l2_rate", "max_h1_seminorm_error", "min_h1_rate", "max_residual_relative"}
_FIELD_KEYS = {"schema_version", "coordinates_unit", "field_unit", "node_ids", "coordinates", "values",
               "cell_node_ids", "dirichlet_node_ids", "boundaries"}
_SIDE_KEYS = {"facet_ids", "facet_node_ids", "dof_ids", "measure", "normal_integral", "prescribed_values", "prescribed_integral"}
_STUDY_KEYS = {"cells_per_axis", "nominal_h", "degree", "cell_type", "global_cells", "global_dofs", "dirichlet_dofs",
               "boundary_value_error", "l2_error", "h1_seminorm_error", "l2_convergence_rate",
               "h1_seminorm_convergence_rate", "linear_residual", "ksp_convergence_reason", "ksp_iterations"}
LIMITATIONS = [
    "Dimensionless rectangle, scalar real P1 triangles, constant positive diffusion and nonnegative reaction.",
    "Four whole named sides admit Dirichlet or outward diffusive Neumann data; at least one side is Dirichlet.",
    "Pure Neumann, Robin, imported geometry, vector/coupled/time-dependent models and MPI execution are unsupported.",
    "Native symbolic degree-8 quadrature measures L2 and gradient-H1 errors; the reference is never interpolated.",
    "Domain independently checks native grid/topology/boundaries, Dirichlet field error, residual normalization and every mesh-pair rate.",
    "Prescribed Neumann-side integrals are not the complete boundary-flux balance; Dirichlet-side physical flux is not measured here.",
    "Mathematical reference agreement is not NAFEMS, physical validation or engineering model qualification.",
]


def _keys(value, names, label):
    if not isinstance(value, dict) or set(value) != set(names):
        raise PDEInputError(f"{label} requires exactly {', '.join(sorted(names))}")
    return value


def _number(value, label, **sign):
    if not finite_number(value, **sign):
        raise PDEInputError(f"{label} requires a finite number with the stated sign")
    return float(value)


def _same(actual, expected, label):
    if not finite_number(actual) or not math.isclose(actual, expected, rel_tol=ATOL, abs_tol=ATOL):
        raise PDEInputError(f"Inconsistent {label}")


def expression_value(source, x, y):
    """Recompute a finite scalar using the saved existing AST interpreter."""
    try:
        value = interpret_expression(parse_expression(source), (x, y),
                                     {name: getattr(math, name) for name in FUNCTION_NAMES})
    except (ArithmeticError, ValueError) as exc:
        raise PDEInputError("Scalar expression is undefined at a required boundary point") from exc
    return _number(value, "scalar boundary value")


def validate_settings(settings):
    _keys(settings, {"problem", "mesh", "validation"}, "rectangle settings")
    problem = _keys(settings["problem"], {"domain", "weak_form", "boundaries", "reference"}, "problem")
    rectangle = _keys(problem["domain"], {"type", "lengths"}, "domain")
    lengths = rectangle["lengths"]
    if (rectangle["type"] != "rectangle" or not isinstance(lengths, list) or len(lengths) != 2 or
            any(not finite_number(value) or not .001 <= value <= 1000 for value in lengths)):
        raise PDEInputError("Rectangle lengths must be finite numbers between 0.001 and 1000")
    thresholds = _keys(settings["validation"], _VALIDATIONS, "validation")
    if any(not finite_number(value, positive=True) for value in thresholds.values()):
        raise PDEInputError("All numerical thresholds must be finite and strictly positive")
    # Reuse the existing complete expression/material/mesh/reference validator.
    _linear_settings({"problem": {"domain": "unit_square", "weak_form": problem["weak_form"],
                                  "dirichlet": "0.0", "reference": problem["reference"]},
                      "mesh": settings["mesh"], "validation": {key: thresholds[key] for key in
                      ("max_l2_error", "min_l2_rate", "max_residual_relative")}})
    boundaries = _keys(problem["boundaries"], SIDES, "boundaries")
    for side, boundary in boundaries.items():
        _keys(boundary, {"type", "value"}, f"boundary {side}")
        if boundary["type"] not in ("dirichlet", "neumann"):
            raise PDEInputError("Only whole-side Dirichlet and outward diffusive Neumann data are supported")
        parse_expression(boundary["value"])
    if not any(boundary["type"] == "dirichlet" for boundary in boundaries.values()):
        raise PDEInputError("Pure Neumann is unsupported; at least one whole Dirichlet side is required")
    for x, xs in ((0., "xmin"), (lengths[0], "xmax")):
        for y, ys in ((0., "ymin"), (lengths[1], "ymax")):
            values = [expression_value(boundaries[side]["value"], x, y) for side in (xs, ys)
                      if boundaries[side]["type"] == "dirichlet"]
            if len(values) == 2 and not math.isclose(values[0], values[1], rel_tol=ATOL, abs_tol=ATOL):
                raise PDEInputError(f"Conflicting adjacent Dirichlet data at {xs}/{ys}")
    return json.loads(json.dumps(settings, allow_nan=False))


def manufactured_settings(reaction=0.0, lengths=(2.0, 1.0), diffusion=1.0):
    k, c = _number(diffusion, "diffusion", positive=True), _number(reaction, "reaction", nonnegative=True)
    if not isinstance(lengths, (tuple, list)) or len(lengths) != 2:
        raise PDEInputError("Manufactured rectangle requires two lengths")
    lx, ly = lengths
    return validate_settings({
        "problem": {"domain": {"type": "rectangle", "lengths": list(lengths)},
                    "weak_form": {"diffusion": k, "reaction": c,
                                  "rhs": f"-2*{k!r}*(x[0]**2+x[1]**2)+{c!r}*(x[0]**2*x[1]**2+x[0]+2*x[1]+1)"},
                    "boundaries": {"xmin": {"type": "dirichlet", "value": "2*x[1]+1"},
                                   "xmax": {"type": "neumann", "value": f"{k!r}*(2*{lx!r}*x[1]**2+1)"},
                                   "ymin": {"type": "dirichlet", "value": "x[0]+1"},
                                   "ymax": {"type": "neumann", "value": f"{k!r}*(2*{ly!r}*x[0]**2+2)"}},
                    "reference": {"solution": "x[0]**2*x[1]**2+x[0]+2*x[1]+1",
                                  "source": "Direct manufactured mathematical derivative of u=x^2*y^2+x+2*y+1; not NAFEMS or physical qualification"}},
        "mesh": {"cell_counts": [8, 16, 32], "degree": 1},
        "validation": {"max_l2_error": .03, "min_l2_rate": 1.8, "max_h1_seminorm_error": .5,
                       "min_h1_rate": .9, "max_residual_relative": 1e-10}})


def source_value(k, c, x, y):
    """Direct independent derivatives: u_xx=2*y² and u_yy=2*x²."""
    k, c = _number(k, "diffusion", positive=True), _number(c, "reaction", nonnegative=True)
    x, y = _number(x, "x"), _number(y, "y")
    u = x * x * y * y + x + 2 * y + 1
    return _number(-k * (2 * y * y + 2 * x * x) + c * u, "manufactured source")


def boundary_value(k, side, x, y):
    k, x, y = _number(k, "diffusion", positive=True), _number(x, "x"), _number(y, "y")
    if side == "xmin":
        value = 2 * y + 1
    elif side == "ymin":
        value = x + 1
    elif side == "xmax":
        value = k * (2 * x * y * y + 1)
    elif side == "ymax":
        value = k * (2 * y * x * x + 2)
    else:
        raise PDEInputError("Unknown manufactured rectangle side")
    return _number(value, "manufactured boundary value")


def model_declaration(settings):
    normalized = validate_settings(settings)
    problem, weak = normalized["problem"], normalized["problem"]["weak_form"]
    return {"case": "rectangle_scalar_elliptic", "version": VERSION,
            "model": {"geometry": {"type": "rectangle", "dimensions": problem["domain"]["lengths"],
                                   "origin": [0., 0.], "unit": "1"},
                      "mesh": {**normalized["mesh"], "cell_type": "triangle", "space": "scalar_lagrange"}},
            "constitutive_law": {"type": "constant_scalar_diffusion_reaction", "diffusion": {"value": weak["diffusion"], "unit": "1"},
                                 "reaction": {"value": weak["reaction"], "unit": "1"}},
            "boundary_conditions": [{"type": problem["boundaries"][side]["type"], "selection": {"type": "named_side", "name": side},
                                     "expression": problem["boundaries"][side]["value"], "unit": "1",
                                     "neumann_semantics": "diffusion*grad(u).outward_normal"}
                                    for side in SIDES],
            "loads": [{"type": "source", "expression": weak["rhs"], "unit": "1"}],
            "outputs": {"fields": [{"field": "u", "type": "scalar", "unit": "1"}]},
            "reference": copy.deepcopy(problem["reference"])}


def _ids(value, label, *, size=None):
    if (not isinstance(value, list) or any(type(node) is not int or node < 0 or (size is not None and node >= size) for node in value) or
            len(value) != len(set(value))):
        raise PDEInputError(f"Invalid/duplicate {label}")
    return set(value)


def _mesh_topology(settings, study, field):
    """Check retained grid/triangles only; no response, boundary or norm verdict."""
    count, lengths = study["cells_per_axis"], settings["problem"]["domain"]["lengths"]
    size = (count + 1)**2
    ids = field["node_ids"]
    if _ids(ids, "native node IDs", size=size) != set(range(size)):
        raise PDEInputError("Native node coverage differs from the complete rectangle grid")
    coordinates = field["coordinates"]
    if not isinstance(coordinates, list) or len(coordinates) != size:
        raise PDEInputError("Incomplete native coordinates")
    grid, xyz = {}, dict(zip(ids, coordinates))
    for node, point in zip(ids, coordinates):
        if not isinstance(point, list) or len(point) != 2 or any(not finite_number(value) for value in point):
            raise PDEInputError("Malformed native rectangle coordinates")
        index = tuple(round(value * count / length) for value, length in zip(point, lengths))
        if any(not 0 <= slot <= count for slot in index):
            raise PDEInputError("Native coordinates lie outside the declared rectangle")
        for value, slot, length in zip(point, index, lengths):
            _same(value, slot * length / count, "native rectangular grid coordinate")
        grid[node] = index
    if set(grid.values()) != {(i, j) for i in range(count + 1) for j in range(count + 1)}:
        raise PDEInputError("Duplicate or missing native grid positions")
    cells = field["cell_node_ids"]
    if not isinstance(cells, list) or len(cells) != 2 * count**2:
        raise PDEInputError("Incomplete native triangle coverage")
    identities, squares, edges = set(), defaultdict(list), Counter()
    for cell in cells:
        if not isinstance(cell, list) or len(cell) != 3 or len(_ids(cell, "triangle nodes", size=size)) != 3:
            raise PDEInputError("Malformed native triangle connectivity")
        identity = tuple(sorted(cell))
        if identity in identities:
            raise PDEInputError("Duplicate native triangle")
        identities.add(identity)
        points = [grid[node] for node in cell]
        ix, iy = min(p[0] for p in points), min(p[1] for p in points)
        determinant = ((points[1][0] - points[0][0]) * (points[2][1] - points[0][1]) -
                       (points[2][0] - points[0][0]) * (points[1][1] - points[0][1]))
        if abs(determinant) != 1 or max(p[0] for p in points) != ix + 1 or max(p[1] for p in points) != iy + 1:
            raise PDEInputError("Degenerate or undeclared native triangle")
        squares[ix, iy].append(set(points))
        edges.update(tuple(sorted((cell[a], cell[b]))) for a, b in ((0, 1), (1, 2), (2, 0)))
    if set(squares) != {(i, j) for i in range(count) for j in range(count)}:
        raise PDEInputError("Native triangles do not cover every rectangular grid cell")
    for (i, j), triangles in squares.items():
        shared = triangles[0] & triangles[1] if len(triangles) == 2 else set()
        if (len(triangles) != 2 or triangles[0] | triangles[1] != {(i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)} or
                len(shared) != 2 or len({p[0] for p in shared}) != 2 or len({p[1] for p in shared}) != 2):
            raise PDEInputError("Overlapping native triangle coverage")
    if any(multiplicity not in (1, 2) for multiplicity in edges.values()):
        raise PDEInputError("Nonmanifold native triangle edges")
    exterior = {edge for edge, multiplicity in edges.items() if multiplicity == 1}
    return count, lengths, size, grid, xyz, exterior


def _field_check(settings, study, field):
    _keys(field, _FIELD_KEYS, "native DOF field")
    if (field["schema_version"] != "1" or field["coordinates_unit"] != "1" or field["field_unit"] != "1"):
        raise PDEInputError("Native DOF field units/schema differ from the declaration")
    values = field["values"]
    expected_size = (study["cells_per_axis"] + 1)**2
    if (not isinstance(values, list) or len(values) != expected_size or
            any(not finite_number(value) for value in values)):
        raise PDEInputError("Incomplete/nonfinite native coordinates/values")
    count, lengths, size, grid, xyz, exterior = _mesh_topology(settings, study, field)
    by_id, cells = dict(zip(field["node_ids"], values)), field["cell_node_ids"]
    boundaries = _keys(field["boundaries"], SIDES, "native named boundaries")
    prescribed, selected, facets_seen, boundary_edges = {}, set(), set(), set()
    error, pointwise_passed = 0., True
    for side in SIDES:
        boundary = _keys(boundaries[side], _SIDE_KEYS, f"native boundary {side}")
        axis, slot = (0, 0) if side == "xmin" else (0, count) if side == "xmax" else (1, 0) if side == "ymin" else (1, count)
        expected_nodes = {node for node, index in grid.items() if index[axis] == slot}
        dof_ids = boundary["dof_ids"]
        if _ids(dof_ids, "side DOF IDs", size=size) != expected_nodes or dof_ids != sorted(dof_ids):
            raise PDEInputError("Native side DOF membership differs from its named rectangle side")
        facet_ids = _ids(boundary["facet_ids"], "native facet IDs", size=3 * count**2 + 2 * count)
        if len(facet_ids) != count or facet_ids & facets_seen or boundary["facet_ids"] != sorted(boundary["facet_ids"]):
            raise PDEInputError("Native side facets overlap or have incomplete coverage")
        facets_seen.update(facet_ids)
        endpoints = boundary["facet_node_ids"]
        if not isinstance(endpoints, list) or len(endpoints) != count:
            raise PDEInputError("Incomplete native side-facet endpoints")
        side_edges = set()
        for pair in endpoints:
            if not isinstance(pair, list) or len(pair) != 2 or len(_ids(pair, "facet endpoints", size=size)) != 2:
                raise PDEInputError("Malformed native facet endpoints")
            edge = tuple(sorted(pair))
            if edge not in exterior or not set(pair) <= expected_nodes or edge in side_edges or edge in boundary_edges:
                raise PDEInputError("Native named facet endpoints differ from the complete disjoint exterior edges")
            side_edges.add(edge)
        boundary_edges.update(side_edges)
        length = lengths[1 - axis]
        _same(boundary["measure"], length, "native side measure")
        normal = boundary["normal_integral"]
        if not isinstance(normal, list) or len(normal) != 2:
            raise PDEInputError("Incomplete native side-normal integral")
        for component in range(2):
            _same(normal[component], length * (-1 if slot == 0 else 1) if component == axis else 0., "outward side-normal integral")
        observed = boundary["prescribed_values"]
        if not isinstance(observed, list) or len(observed) != len(dof_ids):
            raise PDEInputError("Incomplete prescribed side values")
        specification = settings["problem"]["boundaries"][side]
        for node, value in zip(dof_ids, observed):
            expected = expression_value(specification["value"], *xyz[node])
            _same(value, expected, "prescribed native boundary value")
            if specification["type"] == "dirichlet":
                prescribed.setdefault(node, []).append(expected)
                error = max(error, abs(by_id[node] - expected))
                pointwise_passed = pointwise_passed and math.isclose(by_id[node], expected, rel_tol=ATOL, abs_tol=ATOL)
        _number(boundary["prescribed_integral"], "prescribed native side integral")
        if specification["type"] == "dirichlet":
            selected.update(expected_nodes)
    if boundary_edges != exterior or len(exterior) != 4 * count:
        raise PDEInputError("Native named facets do not cover the entire exterior exactly once")
    if _ids(field["dirichlet_node_ids"], "Dirichlet union", size=size) != selected or field["dirichlet_node_ids"] != sorted(selected):
        raise PDEInputError("Native Dirichlet DOFs differ from the exact union of declared sides")
    if (study["global_cells"] != len(cells) or study["global_dofs"] != size or study["dirichlet_dofs"] != len(selected)):
        raise PDEInputError("Native mesh/DOF summaries differ from retained fields")
    _same(study["boundary_value_error"], error, "native and independently recomputed Dirichlet field error")
    limit = max(ATOL, max(abs(value) for values_at_node in prescribed.values() for value in values_at_node) * ATOL)
    return error, limit, pointwise_passed


def assess(settings, studies, native_fields):
    normalized = validate_settings(settings)
    counts = normalized["mesh"]["cell_counts"]
    if (not isinstance(studies, list) or not isinstance(native_fields, list) or
            len(studies) != len(counts) or len(native_fields) != len(counts)):
        raise PDEInputError("Complete observations/fields are required for every frozen mesh")
    observed = copy.deepcopy(studies)
    boundaries, residuals = [], []
    for index, (count, study, field) in enumerate(zip(counts, observed, native_fields)):
        if not isinstance(study, dict) or not _STUDY_KEYS <= set(study):
            raise PDEInputError("Missing native rectangle observations")
        for key in ("cells_per_axis", "degree", "global_cells", "global_dofs", "dirichlet_dofs", "ksp_convergence_reason", "ksp_iterations"):
            if type(study[key]) is not int or (key != "ksp_convergence_reason" and study[key] < 0):
                raise PDEInputError(f"Malformed integer native observation {key}")
        if study["cells_per_axis"] != count or study["degree"] != 1 or study["cell_type"] != "triangle":
            raise PDEInputError("Native mesh identity differs from the frozen request")
        _same(study["nominal_h"], math.hypot(*normalized["problem"]["domain"]["lengths"]) / count, "nominal rectangular mesh h")
        for key in ("boundary_value_error", "l2_error", "h1_seminorm_error"):
            _number(study[key], key, nonnegative=True)
        error, limit, pointwise_passed = _field_check(normalized, study, field)
        study["recomputed_boundary_value_error"] = error
        boundaries.append({"n": count, "observed": study["boundary_value_error"], "recomputed": error,
                           "limit": limit, "pointwise_passed": pointwise_passed})
        residual = _keys(study["linear_residual"], {"absolute", "rhs_norm", "relative", "normalization"}, "linear residual")
        for key in ("absolute", "rhs_norm", "relative"):
            _number(residual[key], f"residual {key}", nonnegative=True)
        expected = residual["absolute"] / residual["rhs_norm"] if residual["rhs_norm"] > 0 else residual["absolute"]
        if (residual["normalization"] != ("rhs_l2_norm" if residual["rhs_norm"] > 0 else "absolute_for_zero_rhs") or
                not finite_number(expected) or not math.isclose(residual["relative"], expected, rel_tol=ATOL, abs_tol=0.0)):
            raise PDEInputError("Inconsistent constrained linear residual normalization")
        residuals.append(max(residual["relative"], expected))
        for metric, rate in (("l2_error", "l2_convergence_rate"), ("h1_seminorm_error", "h1_seminorm_convergence_rate")):
            expected_rate = error_rate(observed[index - 1][metric], study[metric]) if index else None
            if ((expected_rate is None and study[rate] is not None) or
                    (expected_rate is not None and (not finite_number(study[rate]) or
                     not math.isclose(study[rate], expected_rate, rel_tol=ATOL, abs_tol=ATOL)))):
                raise PDEInputError(f"Inconsistent native/recomputed {rate}")
    limits, fine = normalized["validation"], observed[-1]
    l2_rates, h1_rates = [row["l2_convergence_rate"] for row in observed[1:]], [row["h1_seminorm_convergence_rate"] for row in observed[1:]]
    numerical = [("pde_solver_convergence", all(row["ksp_convergence_reason"] > 0 for row in observed),
                  [row["ksp_convergence_reason"] for row in observed], "Positive native PETSc KSP reason"),
                 ("pde_boundary_and_mesh", all(row["pointwise_passed"] for row in boundaries), boundaries,
                  "Complete rectangle/side topology and pointwise Dirichlet absolute/relative tolerance 1e-12"),
                 ("pde_analytical_l2_error", fine["l2_error"] <= limits["max_l2_error"], fine["l2_error"], limits["max_l2_error"]),
                 ("pde_analytical_h1_seminorm_error", fine["h1_seminorm_error"] <= limits["max_h1_seminorm_error"], fine["h1_seminorm_error"], limits["max_h1_seminorm_error"]),
                 ("pde_l2_convergence_rate", all(rate is not None and rate >= limits["min_l2_rate"] for rate in l2_rates), l2_rates, limits["min_l2_rate"]),
                 ("pde_h1_seminorm_convergence_rate", all(rate is not None and rate >= limits["min_h1_rate"] for rate in h1_rates), h1_rates, limits["min_h1_rate"]),
                 ("pde_linear_residual", max(residuals) <= limits["max_residual_relative"], residuals, limits["max_residual_relative"])]
    checks = [{"code": code, "status": "PASS" if passed else "FAIL", "observed": value, "limit": limit} for code, passed, value, limit in numerical]
    passed = all(check["status"] == "PASS" for check in checks)
    failed = ", ".join(check["code"] for check in checks if check["status"] == "FAIL")
    metric_values = {"l2_error": fine["l2_error"], "h1_seminorm_error": fine["h1_seminorm_error"],
                     "l2_convergence_rate": fine["l2_convergence_rate"], "h1_seminorm_convergence_rate": fine["h1_seminorm_convergence_rate"],
                     "linear_residual_relative": max(residuals)}
    return {"checks": checks, "metrics": {name: {"value": value, "unit": "1", "valid": passed,
            **({"reason": f"Declared rectangle numerical validation failed: {failed}"} if not passed else {})} for name, value in metric_values.items()},
            "reference": {**copy.deepcopy(normalized["problem"]["reference"]), "domain": copy.deepcopy(normalized["problem"]["domain"]),
                          "diffusion": normalized["problem"]["weak_form"]["diffusion"], "reaction": normalized["problem"]["weak_form"]["reaction"],
                          "neumann_semantics": "diffusion*grad(u).outward_normal", "units": "dimensionless", "error_quadrature_degree": 8,
                          "h1_semantics": "gradient seminorm", "rate_semantics": "Every declared mesh pair must pass"},
            "mesh_studies": observed, "pending_validations": ["physical_validation", "model_qualification"], "limitations": list(LIMITATIONS)}
