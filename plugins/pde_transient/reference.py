"""Pure transient rectangle declarations, time binding and complete-history checks."""

from __future__ import annotations

import copy
import hashlib
import json
import math

if __name__ == "transient_reference":
    import domain_reference as rectangle
    import fenicsx_time_expression as expression
else:
    from plugins.pde_elliptic import reference as rectangle
    from caelab.adapters import fenicsx_time_expression as expression

VERSION = "1"
PDEInputError = expression.PDEInputError
SIDES = rectangle.SIDES
finite_number = expression.finite_number
_keys, _number, _same = rectangle._keys, rectangle._number, rectangle._same
MAX_SNAPSHOTS = 2_000_000
LIMITATIONS = ["Dimensionless scalar unit-capacity backward Euler on real64 serial P1 rectangles; fixed uniform time steps.",
               "One refinement axis changes while the other stays fixed; all adjacent final-time rates are measured.",
               "Native symbolic degree8 L2/gradient-H1 errors are observations; Domain independently checks field/time/source/history bindings.",
               "Prescribed Neumann integrals are input binding, not full physical solution flux equilibrium.",
               "Adaptive time, CN/BDF2, nonlinear/vector/coupled/imported domains and MPI are unsupported.",
               "Mathematical histories do not qualify physical or engineering models; qualification remains UNKNOWN."]


def study_pairs(settings):
    meshes, steps = settings["mesh"]["cell_counts"], settings["time"]["step_counts"]
    return list(zip(meshes, steps * len(meshes))) if settings["refinement_axis"] == "mesh" else list(zip(meshes * len(steps), steps))


def value_sha256(node_ids, values):
    return hashlib.sha256(json.dumps({"node_ids": node_ids, "values": values}, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _counts(values, refining):
    if (not isinstance(values, list) or not (3 <= len(values) <= 8 if refining else len(values) == 1) or
            any(type(value) is not int or not 1 <= value <= 128 for value in values) or
            (refining and any(b != 2*a for a, b in zip(values, values[1:])))):
        raise PDEInputError("Refining counts require 3..8 doubling integers1..128; fixed counts require one integer1..128")


def _trees(problem):
    return {"rhs": expression.parse_expression(problem["weak_form"]["rhs"]),
            "reference": expression.parse_expression(problem["reference"]["solution"]),
            "initial": expression.parse_expression(problem["initial"]["value"]),
            **{side: expression.parse_expression(problem["boundaries"][side]["value"]) for side in SIDES}}


def validate_settings(settings):
    _keys(settings, {"problem", "mesh", "time", "refinement_axis", "validation"}, "transient settings")
    problem = _keys(settings["problem"], {"domain", "weak_form", "boundaries", "initial", "reference"}, "transient problem")
    axis = settings["refinement_axis"]
    if axis not in ("mesh", "time"):
        raise PDEInputError("Refinement axis must be mesh or time")
    mesh = _keys(settings["mesh"], {"cell_counts", "degree"}, "mesh")
    if type(mesh["degree"]) is not int or mesh["degree"] != 1:
        raise PDEInputError("Only scalar P1 triangles are supported")
    time = _keys(settings["time"], {"start", "end", "step_counts", "scheme", "unit"}, "time")
    if (not finite_number(time["start"]) or time["start"] != 0 or not finite_number(time["end"]) or
            not .001 <= time["end"] <= 1000 or time["scheme"] != "backward_euler" or time["unit"] != "1"):
        raise PDEInputError("Time must start0 with finite end0.001..1000, backward_euler and unit1")
    _counts(mesh["cell_counts"], axis == "mesh")
    _counts(time["step_counts"], axis == "time")
    _keys(problem["initial"], {"value"}, "initial")
    _keys(problem["weak_form"], {"diffusion", "reaction", "rhs"}, "weak form")
    _keys(problem["reference"], {"solution", "source"}, "reference")
    _keys(problem["boundaries"], SIDES, "boundaries")
    for boundary in problem["boundaries"].values():
        _keys(boundary, {"type", "value"}, "boundary")
    trees = _trees(problem)
    # Reuse the old full rectangle declaration validator on a t0-bound projection.
    bound = bound_rectangle(settings, 0.)
    bound["mesh"] = {"cell_counts": [1, 2, 4], "degree": 1}
    rectangle.validate_settings(bound)
    pairs = study_pairs(settings)
    if sum((steps+1)*(count+1)**2 for count, steps in pairs) > MAX_SNAPSHOTS:
        raise PDEInputError("Declared retained snapshot work exceeds2,000,000 node values")
    lx, ly = problem["domain"]["lengths"]
    for count, steps in pairs:
        for step in range(steps+1):
            instant = step*time["end"]/steps
            for i in range(count+1):
                for j in range(count+1):
                    x, y = i*lx/count, j*ly/count
                    expression.scalar_value(trees["rhs"], x, y, instant)
                    expression.scalar_value(trees["reference"], x, y, instant)
                    selected = []
                    for side, on_side in (("xmin", i == 0), ("xmax", i == count), ("ymin", j == 0), ("ymax", j == count)):
                        if on_side:
                            prescribed = expression.scalar_value(trees[side], x, y, instant)
                            if problem["boundaries"][side]["type"] == "dirichlet":
                                selected.append(prescribed)
                    if len(selected) == 2 and not math.isclose(*selected, rel_tol=1e-12, abs_tol=1e-12):
                        raise PDEInputError("Adjacent time-dependent Dirichlet corners conflict")
                    if step == 0:
                        initial = expression.scalar_value(trees["initial"], x, y, 0.)
                        if any(not math.isclose(initial, value, rel_tol=1e-12, abs_tol=1e-12) for value in selected):
                            raise PDEInputError("Initial interpolation conflicts with declared t0 Dirichlet values")
    return json.loads(json.dumps(settings, allow_nan=False))


def bound_rectangle(settings, time):
    problem = settings["problem"]
    return {"problem": {"domain": copy.deepcopy(problem["domain"]),
                        "weak_form": {**problem["weak_form"], "rhs": expression.bind_expression(problem["weak_form"]["rhs"], time)},
                        "boundaries": {side: {**boundary, "value": expression.bind_expression(boundary["value"], time)} for side, boundary in problem["boundaries"].items()},
                        "reference": {**problem["reference"], "solution": expression.bind_expression(problem["reference"]["solution"], time)}},
            "mesh": copy.deepcopy(settings["mesh"]), "validation": copy.deepcopy(settings["validation"])}


def manufactured_settings(axis="mesh", case="polynomial", reaction=0.0, lengths=(2.0, 1.0), diffusion=1.0):
    k, c = _number(diffusion, "diffusion", positive=True), _number(reaction, "reaction", nonnegative=True)
    if not isinstance(lengths, (list, tuple)) or len(lengths) != 2:
        raise PDEInputError("Manufactured rectangle requires two lengths")
    lx, ly = lengths
    phi = "(x[0]**2*x[1]**2+x[0]+2*x[1]+1)"
    if case == "polynomial" and axis == "mesh":
        initial, solution = phi, "(1+t)*"+phi
        rhs = f"{phi}-2*{k!r}*(1+t)*(x[0]**2+x[1]**2)+{c!r}*({solution})"
        boundaries = {"xmin": "(1+t)*(2*x[1]+1)", "ymin": "(1+t)*(x[0]+1)",
                      "xmax": f"{k!r}*(1+t)*(2*{lx!r}*x[1]**2+1)", "ymax": f"{k!r}*(1+t)*(2*{ly!r}*x[0]**2+2)"}
    elif case == "temporal" and axis == "time":
        initial, solution = "x[0]+2*x[1]+1", "exp(-t)*(x[0]+2*x[1]+1)"
        rhs = f"({c!r}-1)*({solution})"
        boundaries = {"xmin": "exp(-t)*(2*x[1]+1)", "ymin": "exp(-t)*(x[0]+1)", "xmax": f"{k!r}*exp(-t)", "ymax": f"2*{k!r}*exp(-t)"}
    elif case == "zero_source" and axis == "mesh" and k == 1 and c == 0:
        initial, solution = "x[0]**2+x[1]**2+x[0]+2*x[1]+1", "x[0]**2+x[1]**2+4*t+x[0]+2*x[1]+1"
        rhs = "0.0"
        boundaries = {"xmin": "x[1]**2+4*t+2*x[1]+1", "ymin": "x[0]**2+4*t+x[0]+1",
                      "xmax": f"2*{lx!r}+1", "ymax": f"2*{ly!r}+2"}
    else:
        raise PDEInputError("Manufactured case requires its frozen refinement axis; zero_source requires k1/c0")
    return validate_settings({"problem": {"domain": {"type": "rectangle", "lengths": list(lengths)},
            "weak_form": {"diffusion": k, "reaction": c, "rhs": rhs}, "boundaries": {side: {"type": "dirichlet" if side in ("xmin", "ymin") else "neumann", "value": boundaries[side]} for side in SIDES},
            "initial": {"value": initial}, "reference": {"solution": solution, "source": f"Direct manufactured {case} scalar time derivative and Laplacian; not physical qualification"}},
            "mesh": {"cell_counts": [8, 16, 32] if axis == "mesh" else [8], "degree": 1},
            "time": {"start": 0., "end": 1., "step_counts": [32] if axis == "mesh" else [16, 32, 64], "scheme": "backward_euler", "unit": "1"}, "refinement_axis": axis,
            "validation": {"max_l2_error": .06 if axis == "mesh" else .04, "min_l2_rate": 1.8 if axis == "mesh" else .8,
                           "max_h1_seminorm_error": 1. if axis == "mesh" else .2, "min_h1_rate": .9 if axis == "mesh" else .8, "max_residual_relative": 1e-10}})


def model_declaration(settings):
    settings = validate_settings(settings)
    declaration = rectangle.model_declaration({**bound_rectangle(settings, 0.), "mesh": {"cell_counts": [1, 2, 4], "degree": 1}})
    problem = settings["problem"]
    declaration.update(case="rectangle_scalar_transient", version=VERSION, time=copy.deepcopy(settings["time"]),
                       refinement_axis=settings["refinement_axis"], initial_conditions=[{"field": "u", "expression": problem["initial"]["value"], "unit": "1"}], reference=copy.deepcopy(problem["reference"]))
    declaration["model"]["mesh"] = {**settings["mesh"], "cell_type": "triangle", "space": "scalar_lagrange"}
    declaration["constitutive_law"]["capacity"] = {"value": 1., "unit": "1"}
    for row in declaration["boundary_conditions"]:
        row["expression"] = problem["boundaries"][row["selection"]["name"]]["value"]
    declaration["loads"][0]["expression"] = problem["weak_form"]["rhs"]
    declaration["outputs"]["history"] = [{"field": "u", "unit": "1", "sampling": "all_frozen_times_including_initial", "time": copy.deepcopy(settings["time"])}]
    return declaration


def assess(settings, studies, native_fields, bindings):
    settings = validate_settings(settings)
    pairs, trees = study_pairs(settings), _trees(settings["problem"])
    if not all(isinstance(rows, list) and len(rows) == len(pairs) for rows in (studies, native_fields, bindings)):
        raise PDEInputError("Complete studies/fields/time bindings are required")
    observed = copy.deepcopy(studies)
    residuals, reasons, boundary_passes, initial_passes = [], [], [], []
    for index, ((n, count), study, fields, history_bindings) in enumerate(zip(pairs, observed, native_fields, bindings)):
        if not isinstance(study, dict) or any(study.get(key) != value or type(study.get(key)) is not type(value) for key, value in
                {"study_index": index, "cells_per_axis": n, "step_count": count, "refinement_axis": settings["refinement_axis"]}.items()):
            raise PDEInputError("Transient study identity differs from declared pair")
        dt = settings["time"]["end"]/count
        _same(study.get("dt"), dt, "study dt")
        _same(study.get("nominal_h"), math.hypot(*settings["problem"]["domain"]["lengths"])/n, "study h")
        steps = study.get("steps")
        if not all(isinstance(rows, list) and len(rows) == count+1 for rows in (steps, fields, history_bindings)):
            raise PDEInputError("Missing/extra time snapshots")
        prior_hash, fixed_mesh = None, None
        for j, (step, field, binding) in enumerate(zip(steps, fields, history_bindings)):
            instant = j*settings["time"]["end"]/count
            if not isinstance(step, dict) or type(step.get("index")) is not int or step["index"] != j or step.get("distinct_state") is not True:
                raise PDEInputError("Invalid time-step identity or aliased previous/current state")
            for key, expected in (("time", instant), ("dt", dt if j else 0.), ("native_time_value", instant)):
                _same(step.get(key), expected, key)
            for key in ("global_cells", "global_dofs", "dirichlet_dofs"):
                if type(step.get(key)) is not int:
                    raise PDEInputError("Malformed native step counts")
            for key in ("boundary_value_error", "l2_error", "h1_seminorm_error"):
                _number(step.get(key), key, nonnegative=True)
            time_settings = bound_rectangle(settings, instant)
            identity = {**step, "cells_per_axis": n}
            _, _, passed = rectangle._field_check(time_settings, identity, field)
            boundary_passes.append(passed)
            if field["node_ids"] != sorted(field["node_ids"]):
                raise PDEInputError("Native history node IDs must be sorted for canonical identity")
            mesh_identity = {key: field[key] for key in ("node_ids", "coordinates", "cell_node_ids", "dirichlet_node_ids")}
            mesh_identity["boundaries"] = {side: {key: field["boundaries"][side][key] for key in
                                       ("facet_ids", "facet_node_ids", "dof_ids", "measure", "normal_integral")} for side in SIDES}
            if fixed_mesh is not None and mesh_identity != fixed_mesh:
                raise PDEInputError("Native mesh/DOF identity changed within a fixed study")
            fixed_mesh = copy.deepcopy(mesh_identity)
            actual_hash = value_sha256(field["node_ids"], field["values"])
            if step.get("current_values_sha256") != actual_hash or step.get("previous_values_sha256") != prior_hash:
                raise PDEInputError("Broken previous/current canonical value identity")
            prior_hash = actual_hash
            _keys(binding, {"schema_version", "time", "node_ids", "rhs_values", "reference_values"}, "time binding")
            if binding["schema_version"] != "1" or binding["node_ids"] != field["node_ids"]:
                raise PDEInputError("Time-binding node IDs differ from raw field")
            _same(binding["time"], instant, "binding time")
            for key, tree in (("rhs_values", trees["rhs"]), ("reference_values", trees["reference"])):
                values = binding[key]
                if not isinstance(values, list) or len(values) != len(field["node_ids"]):
                    raise PDEInputError("Incomplete declared RHS/reference time binding")
                for value, point in zip(values, field["coordinates"]):
                    _same(value, expression.scalar_value(tree, *point, instant), "declared RHS/reference sample")
            if j == 0:
                if step.get("solver_status") != "NOT_RUN" or any(step.get(key) is not None for key in ("linear_residual", "ksp_convergence_reason", "ksp_iterations")):
                    raise PDEInputError("Initial state must not claim a solve/residual/KSP")
                initial_passes.extend(math.isclose(value, expression.scalar_value(trees["initial"], *point, 0.), rel_tol=1e-12, abs_tol=1e-12)
                                      for value, point in zip(field["values"], field["coordinates"]))
            else:
                if step.get("solver_status") != "COMPLETED" or type(step.get("ksp_convergence_reason")) is not int or type(step.get("ksp_iterations")) is not int or step["ksp_iterations"] < 0:
                    raise PDEInputError("Solved history omits actual solver state")
                reasons.append(step["ksp_convergence_reason"])
                residual = _keys(step.get("linear_residual"), {"absolute", "rhs_norm", "relative", "normalization"}, "residual")
                for key in ("absolute", "rhs_norm", "relative"):
                    _number(residual[key], key, nonnegative=True)
                expected = residual["absolute"]/residual["rhs_norm"] if residual["rhs_norm"] > 0 else residual["absolute"]
                if residual["normalization"] != ("rhs_l2_norm" if residual["rhs_norm"] > 0 else "absolute_for_zero_rhs") or not finite_number(expected) or not math.isclose(residual["relative"], expected, rel_tol=1e-12, abs_tol=0.):
                    raise PDEInputError("Inconsistent all-step constrained residual normalization")
                residuals.append(expected)
        for metric, rate in (("l2_error", "final_l2_convergence_rate"), ("h1_seminorm_error", "final_h1_seminorm_convergence_rate")):
            expected = rectangle.error_rate(observed[index-1]["steps"][-1][metric], steps[-1][metric]) if index else None
            if expected is None:
                if study.get(rate) is not None:
                    raise PDEInputError("Zero/first final error cannot establish rate")
            else:
                _same(study.get(rate), expected, "all-pair final rate")
    limits, fine = settings["validation"], observed[-1]["steps"][-1]
    l2_rates = [row["final_l2_convergence_rate"] for row in observed[1:]]
    h1_rates = [row["final_h1_seminorm_convergence_rate"] for row in observed[1:]]
    conditions = [("pde_history_completeness", True, [len(row["steps"]) for row in observed], "Exact N+1 ordered snapshots with immutable links"),
                  ("pde_initial_interpolation", all(initial_passes), None, "Complete initial nodal interpolation"),
                  ("pde_boundary_and_mesh", all(boundary_passes), None, "Reused rectangle field/topology/side and time data checks"),
                  ("pde_solver_convergence", all(reason > 0 for reason in reasons), reasons, "Positive reasons at every solved step"),
                  ("pde_analytical_l2_error", fine["l2_error"] <= limits["max_l2_error"], fine["l2_error"], limits["max_l2_error"]),
                  ("pde_analytical_h1_seminorm_error", fine["h1_seminorm_error"] <= limits["max_h1_seminorm_error"], fine["h1_seminorm_error"], limits["max_h1_seminorm_error"]),
                  ("pde_l2_convergence_rate", all(rate is not None and rate >= limits["min_l2_rate"] for rate in l2_rates), l2_rates, limits["min_l2_rate"]),
                  ("pde_h1_seminorm_convergence_rate", all(rate is not None and rate >= limits["min_h1_rate"] for rate in h1_rates), h1_rates, limits["min_h1_rate"]),
                  ("pde_linear_residual", max(residuals) <= limits["max_residual_relative"], max(residuals), limits["max_residual_relative"])]
    checks = [{"code": code, "status": "PASS" if passed else "FAIL", "observed": value, "limit": limit} for code, passed, value, limit in conditions]
    passed = all(row["status"] == "PASS" for row in checks)
    failures = ", ".join(row["code"] for row in checks if row["status"] == "FAIL")
    values = {"l2_error": fine["l2_error"], "h1_seminorm_error": fine["h1_seminorm_error"], "l2_convergence_rate": l2_rates[-1],
              "h1_seminorm_convergence_rate": h1_rates[-1], "linear_residual_relative": max(residuals)}
    return {"checks": checks, "metrics": {key: {"value": value, "unit": "1", "valid": passed,
                    **({"reason": f"Transient numerical validation failed: {failures}"} if not passed else {})} for key, value in values.items()},
            "time_studies": observed, "reference": {**copy.deepcopy(settings["problem"]["reference"]), "time": copy.deepcopy(settings["time"]),
            "refinement_axis": settings["refinement_axis"], "rate_semantics": "Every adjacent refinement pair at identical final time", "h1_semantics": "gradient seminorm", "error_quadrature_degree": 8},
            "pending_validations": ["physical_validation", "model_qualification"], "limitations": list(LIMITATIONS)}
