"""Directed Lamé declarations and vector norms; no native numerical imports."""

import copy
import json
import math

if __name__ == "vector_reference":
    import domain_reference as rectangle
    import fenicsx_expression as expression
else:
    from plugins.pde_elliptic import reference as rectangle
    from caelab.adapters import fenicsx_worker as expression

VERSION = "1"
COMPONENTS = ["u0", "u1"]
SIDES = rectangle.SIDES
PDEInputError = expression.PDEInputError
finite_number = expression.finite_number
_keys, _number, _same = rectangle._keys, rectangle._number, rectangle._same
LIMITATIONS = ["Dimensionless stationary two-component Lamé operator on real64 serial blocked P1 rectangles.",
               "Constant lambda>=0/mu>0/reaction>=0; whole-side vector Dirichlet or outward sigma(u)*normal traction.",
               "Native symbolic degree8 component/vector L2 and full-gradient H1 are observations; Domain checks directed inputs, fields, norm identities and every rate.",
               "Partial component constraints, pure traction, Robin, variable/time/nonlinear/imported/MPI models are unsupported.",
               "Prescribed traction integrals are input binding, not physical equilibrium or material/plane-stress/strength qualification.",
               "Model and physical qualification remain UNKNOWN; mathematical agreement is not engineering approval."]


def _vector(value, label):
    if not isinstance(value, list) or len(value) != 2:
        raise PDEInputError(f"{label} requires exactly two ordered scalar expressions")
    return [expression.parse_expression(source) for source in value]


def _value(tree, point):
    try:
        value = expression.interpret_expression(tree, point, {name: getattr(math, name) for name in expression.FUNCTION_NAMES})
    except (ArithmeticError, ValueError) as exc:
        raise PDEInputError("Declared vector component is undefined at required coordinates") from exc
    return _number(value, "directed vector sample")


def _trees(problem):
    return {"rhs": _vector(problem["weak_form"]["rhs"], "RHS"), "reference": _vector(problem["reference"]["solution"], "reference"),
            **{side: _vector(problem["boundaries"][side]["value"], side) for side in SIDES}}


def scalar_settings(settings, component):
    problem, weak = settings["problem"], settings["problem"]["weak_form"]
    return {"problem": {"domain": copy.deepcopy(problem["domain"]),
            "weak_form": {"diffusion": weak["lame_mu"], "reaction": weak["reaction"], "rhs": weak["rhs"][component]},
            "boundaries": {side: {"type": boundary["type"], "value": boundary["value"][component]} for side, boundary in problem["boundaries"].items()},
            "reference": {"solution": problem["reference"]["solution"][component], "source": problem["reference"]["source"]}},
            "mesh": copy.deepcopy(settings["mesh"]), "validation": copy.deepcopy(settings["validation"])}


def validate_settings(settings):
    _keys(settings, {"problem", "mesh", "validation"}, "vector settings")
    problem = _keys(settings["problem"], {"domain", "weak_form", "boundaries", "reference"}, "vector problem")
    weak = _keys(problem["weak_form"], {"family", "lame_lambda", "lame_mu", "reaction", "rhs"}, "Lamé weak form")
    if weak["family"] != "lame":
        raise PDEInputError("Only the fixed Lamé operator is supported")
    _number(weak["lame_lambda"], "lambda", nonnegative=True)
    _number(weak["lame_mu"], "mu", positive=True)
    _number(weak["reaction"], "reaction", nonnegative=True)
    _keys(problem["reference"], {"solution", "source"}, "reference")
    _keys(problem["boundaries"], SIDES, "vector boundaries")
    for boundary in problem["boundaries"].values():
        _keys(boundary, {"type", "value"}, "whole-side vector boundary")
    trees = _trees(problem)
    # Syntax, rectangle, mesh, threshold and corner checks reuse the complete old validator.
    # These component projections validate inputs; they do not represent scalar solves.
    for component in range(2):
        rectangle.validate_settings(scalar_settings(settings, component))
    lx, ly = problem["domain"]["lengths"]
    for count in settings["mesh"]["cell_counts"]:
        for i in range(count+1):
            for j in range(count+1):
                point = (lx*i/count, ly*j/count)
                for tree in trees["rhs"] + trees["reference"]:
                    _value(tree, point)
                for side, selected in (("xmin", i == 0), ("xmax", i == count), ("ymin", j == 0), ("ymax", j == count)):
                    if selected:
                        for tree in trees[side]: _value(tree, point)
    return json.loads(json.dumps(settings, allow_nan=False))


def manufactured_settings(case="polynomial", lame_lambda=1., lame_mu=1., reaction=0., lengths=(2., 1.)):
    lam, mu, c = _number(lame_lambda, "lambda", nonnegative=True), _number(lame_mu, "mu", positive=True), _number(reaction, "reaction", nonnegative=True)
    if not isinstance(lengths, (list, tuple)) or len(lengths) != 2:
        raise PDEInputError("Manufactured vector rectangle requires two lengths")
    if case == "polynomial":
        u = ["x[0]**2*x[1]**2+x[0]+2*x[1]+1", "2*x[0]**2*x[1]**2-3*x[0]+x[1]+2"]
        d = "(2*x[0]*x[1]**2+4*x[0]**2*x[1]+2)"
        s00 = f"4*{mu!r}*x[0]*x[1]**2+2*{mu!r}+{lam!r}*{d}"
        s01 = f"{mu!r}*(2*x[0]**2*x[1]+4*x[0]*x[1]**2-1)"
        s11 = f"8*{mu!r}*x[0]**2*x[1]+2*{mu!r}+{lam!r}*{d}"
        rhs = [f"{c!r}*({u[0]})-2*{mu!r}*x[0]**2-(4*{mu!r}+2*{lam!r})*x[1]**2-8*({mu!r}+{lam!r})*x[0]*x[1]",
               f"{c!r}*({u[1]})-(8*{mu!r}+4*{lam!r})*x[0]**2-4*{mu!r}*x[1]**2-4*({mu!r}+{lam!r})*x[0]*x[1]"]
    elif case == "harmonic":
        u = ["x[0]**2-x[1]**2+1", "-2*x[0]*x[1]+2"]
        rhs = [f"{c!r}*({source})" for source in u] if c else ["0.0", "0.0"]
        s00, s01, s11 = f"4*{mu!r}*x[0]", f"-4*{mu!r}*x[1]", f"-4*{mu!r}*x[0]"
    else:
        raise PDEInputError("Manufactured vector case must be polynomial or harmonic")
    return validate_settings({"problem": {"domain": {"type": "rectangle", "lengths": list(lengths)},
            "weak_form": {"family": "lame", "lame_lambda": lam, "lame_mu": mu, "reaction": c, "rhs": rhs},
            "boundaries": {"xmin": {"type": "dirichlet", "value": list(u)}, "ymin": {"type": "dirichlet", "value": list(u)},
                           "xmax": {"type": "neumann", "value": [s00, s01]}, "ymax": {"type": "neumann", "value": [s01, s11]}},
            "reference": {"solution": u, "source": f"Direct manufactured {case} vector derivatives and sigma(u)*outward_normal; dimensionless mathematical reference"}},
            "mesh": {"cell_counts": [8, 16, 32], "degree": 1},
            "validation": {"max_l2_error": .04, "min_l2_rate": 1.8, "max_h1_seminorm_error": .8, "min_h1_rate": .9, "max_residual_relative": 1e-10}})


def model_declaration(settings):
    settings = validate_settings(settings)
    problem, weak = settings["problem"], settings["problem"]["weak_form"]
    declaration = rectangle.model_declaration(scalar_settings(settings, 0))
    declaration.update(case="rectangle_vector_lame", version=VERSION, reference=copy.deepcopy(problem["reference"]))
    declaration["model"]["mesh"].update(space="vector_lagrange", components=list(COMPONENTS), block_size=2)
    declaration["constitutive_law"] = {"type": "dimensionless_lame_operator", "lame_lambda": {"value": weak["lame_lambda"], "unit": "1"},
            "lame_mu": {"value": weak["lame_mu"], "unit": "1"}, "reaction": {"value": weak["reaction"], "unit": "1"},
            "stress_semantics": "2*mu*sym(grad(u))+lambda*div(u)*I"}
    for row in declaration["boundary_conditions"]:
        row.pop("neumann_semantics")
        row["expression"] = copy.deepcopy(problem["boundaries"][row["selection"]["name"]]["value"])
        row["components"] = list(COMPONENTS)
        row["traction_semantics"] = "sigma(u)*outward_normal"
    declaration["loads"][0]["expression"] = copy.deepcopy(weak["rhs"])
    declaration["loads"][0]["components"] = list(COMPONENTS)
    declaration["outputs"]["fields"] = [{"field": "u", "type": "vector", "components": list(COMPONENTS), "unit": "1"}]
    return declaration


def _scalar_view(field, component):
    _keys(field, rectangle._FIELD_KEYS | {"field_type", "components", "block_size"}, "native vector field")
    if field["field_type"] != "vector" or field["components"] != COMPONENTS or type(field["block_size"]) is not int or field["block_size"] != 2:
        raise PDEInputError("Native field component order/block identity mismatch")
    for key in ("values",):
        if not isinstance(field[key], list) or any(not isinstance(row, list) or len(row) != 2 or any(not finite_number(value) for value in row) for row in field[key]):
            raise PDEInputError("Incomplete/nonfinite directed vector field")
    view = {key: copy.deepcopy(field[key]) for key in rectangle._FIELD_KEYS}
    view["values"] = [row[component] for row in field["values"]]
    if not isinstance(view["boundaries"], dict):
        raise PDEInputError("Missing vector boundaries")
    for side in SIDES:
        boundary = view["boundaries"].get(side)
        _keys(boundary, rectangle._SIDE_KEYS, "native vector boundary")
        rows, integral = boundary["prescribed_values"], boundary["prescribed_integral"]
        if (not isinstance(rows, list) or any(not isinstance(row, list) or len(row) != 2 or any(not finite_number(value) for value in row) for row in rows) or
                not isinstance(integral, list) or len(integral) != 2 or any(not finite_number(value) for value in integral)):
            raise PDEInputError("Incomplete native directed traction/Dirichlet data")
        boundary["prescribed_values"] = [row[component] for row in rows]
        boundary["prescribed_integral"] = integral[component]
    return view


def assess(settings, studies, native_fields, bindings):
    settings = validate_settings(settings)
    counts, trees = settings["mesh"]["cell_counts"], _trees(settings["problem"])
    if not all(isinstance(rows, list) and len(rows) == len(counts) for rows in (studies, native_fields, bindings)):
        raise PDEInputError("Complete vector studies/fields/bindings required")
    observed, boundaries, sync, residuals, reasons = copy.deepcopy(studies), [], [], [], []
    for index, (n, study, field, binding) in enumerate(zip(counts, observed, native_fields, bindings)):
        if not isinstance(study, dict) or not rectangle._STUDY_KEYS <= set(study):
            raise PDEInputError("Missing vector study observations")
        for key, expected in (("cells_per_axis", n), ("degree", 1), ("block_size", 2), ("global_nodes", (n+1)**2),
                              ("global_dofs", 2*(n+1)**2), ("global_cells", 2*n*n)):
            if type(study.get(key)) is not int or study[key] != expected:
                raise PDEInputError("Vector block/node/scalar count mismatch")
        if study["cell_type"] != "triangle" or type(study.get("dirichlet_nodes")) is not int or type(study["dirichlet_dofs"]) is not int or study["dirichlet_dofs"] != 2*study["dirichlet_nodes"]:
            raise PDEInputError("Vector Dirichlet block/scalar count mismatch")
        _same(study["nominal_h"], math.hypot(*settings["problem"]["domain"]["lengths"])/n, "vector h")
        components = study.get("components")
        if not isinstance(components, list) or len(components) != 2:
            raise PDEInputError("Missing vector component diagnostics")
        for component, row in enumerate(components):
            _keys(row, {"index", "field", "l2_error", "h1_seminorm_error", "l2_convergence_rate", "h1_seminorm_convergence_rate", "boundary_value_error"}, "component diagnostic")
            if type(row["index"]) is not int or row["index"] != component or row["field"] != COMPONENTS[component]:
                raise PDEInputError("Component diagnostic order mismatch")
            for key in ("l2_error", "h1_seminorm_error", "boundary_value_error"):
                _number(row[key], key, nonnegative=True)
            scalar = _scalar_view(field, component)
            scalar_study = {**study, "global_dofs": study["global_nodes"], "dirichlet_dofs": study["dirichlet_nodes"], "boundary_value_error": row["boundary_value_error"]}
            _, _, passed = rectangle._field_check(scalar_settings(settings, component), scalar_study, scalar)
            boundaries.append(passed)
            for metric, rate in (("l2_error", "l2_convergence_rate"), ("h1_seminorm_error", "h1_seminorm_convergence_rate")):
                expected = expression.error_rate(observed[index-1]["components"][component][metric], row[metric]) if index else None
                if expected is None:
                    if row[rate] is not None: raise PDEInputError("First/zero component error cannot prove rate")
                else: _same(row[rate], expected, "component rate")
        _same(study["boundary_value_error"], max(row["boundary_value_error"] for row in components), "vector boundary error identity")
        for metric, rate in (("l2_error", "l2_convergence_rate"), ("h1_seminorm_error", "h1_seminorm_convergence_rate")):
            _number(study[metric], metric, nonnegative=True)
            _same(study[metric], math.hypot(*(row[metric] for row in components)), "component/aggregate norm identity")
            expected = expression.error_rate(observed[index-1][metric], study[metric]) if index else None
            if expected is None:
                if study[rate] is not None: raise PDEInputError("First/zero vector error cannot prove rate")
            else: _same(study[rate], expected, "vector rate")
        _keys(binding, {"schema_version", "node_ids", "components", "rhs_values", "reference_values"}, "directed binding")
        if binding["schema_version"] != "1" or binding["node_ids"] != field["node_ids"] or binding["components"] != COMPONENTS:
            raise PDEInputError("Directed binding ID/component identity mismatch")
        for key, parsed in (("rhs_values", trees["rhs"]), ("reference_values", trees["reference"])):
            rows = binding[key]
            if not isinstance(rows, list) or len(rows) != len(field["node_ids"]): raise PDEInputError("Truncated directed input binding")
            for row, point in zip(rows, field["coordinates"]):
                if not isinstance(row, list) or len(row) != 2: raise PDEInputError("Truncated binding component")
                for component in range(2): _same(row[component], _value(parsed[component], point), "directed source/reference sample")
        synchronization = _number(study.get("solution_sync_error"), "actual x/field sync error", nonnegative=True)
        limit = max(1e-12, max(abs(value) for row in field["values"] for value in row)*1e-12)
        sync.append(synchronization <= limit)
        if type(study["ksp_convergence_reason"]) is not int or type(study["ksp_iterations"]) is not int or study["ksp_iterations"] < 0:
            raise PDEInputError("Missing actual vector KSP observations")
        reasons.append(study["ksp_convergence_reason"])
        residual = _keys(study["linear_residual"], {"absolute", "rhs_norm", "relative", "normalization"}, "vector residual")
        for key in ("absolute", "rhs_norm", "relative"): _number(residual[key], key, nonnegative=True)
        expected = residual["absolute"]/residual["rhs_norm"] if residual["rhs_norm"] else residual["absolute"]
        if residual["normalization"] != ("rhs_l2_norm" if residual["rhs_norm"] else "absolute_for_zero_rhs") or not finite_number(expected) or not math.isclose(residual["relative"], expected, rel_tol=1e-12, abs_tol=0.):
            raise PDEInputError("Inconsistent actual vector residual normalization")
        residuals.append(expected)
    fine, limits = observed[-1], settings["validation"]
    l2_rates = [row["l2_convergence_rate"] for row in observed[1:]]
    h1_rates = [row["h1_seminorm_convergence_rate"] for row in observed[1:]]
    component_rates = {name: [[row["components"][component][name] for row in observed[1:]] for component in range(2)] for name in ("l2_convergence_rate", "h1_seminorm_convergence_rate")}
    conditions = [("pde_boundary_and_mesh", all(boundaries), None, "Complete directed field and reused rectangle geometry/side checks"),
        ("pde_solution_sync", all(sync), [row["solution_sync_error"] for row in observed], "Actual algebraic x/field abs/rel1e-12"),
        ("pde_solver_convergence", all(reason > 0 for reason in reasons), reasons, "Positive vector KSP reason"),
        ("pde_analytical_l2_error", fine["l2_error"] <= limits["max_l2_error"], fine["l2_error"], limits["max_l2_error"]),
        ("pde_analytical_h1_seminorm_error", fine["h1_seminorm_error"] <= limits["max_h1_seminorm_error"], fine["h1_seminorm_error"], limits["max_h1_seminorm_error"]),
        ("pde_l2_convergence_rate", all(rate is not None and rate >= limits["min_l2_rate"] for rate in l2_rates + sum(component_rates["l2_convergence_rate"], [])), {"vector": l2_rates, "components": component_rates["l2_convergence_rate"]}, limits["min_l2_rate"]),
        ("pde_h1_seminorm_convergence_rate", all(rate is not None and rate >= limits["min_h1_rate"] for rate in h1_rates + sum(component_rates["h1_seminorm_convergence_rate"], [])), {"vector": h1_rates, "components": component_rates["h1_seminorm_convergence_rate"]}, limits["min_h1_rate"]),
        ("pde_linear_residual", max(residuals) <= limits["max_residual_relative"], residuals, limits["max_residual_relative"])]
    checks = [{"code": code, "status": "PASS" if passed else "FAIL", "observed": value, "limit": limit} for code, passed, value, limit in conditions]
    passed = all(row["status"] == "PASS" for row in checks)
    failures = ", ".join(row["code"] for row in checks if row["status"] == "FAIL")
    metric_values = {"l2_error": fine["l2_error"], "h1_seminorm_error": fine["h1_seminorm_error"], "l2_convergence_rate": fine["l2_convergence_rate"],
                     "h1_seminorm_convergence_rate": fine["h1_seminorm_convergence_rate"], "linear_residual_relative": max(residuals)}
    for component in range(2):
        for name in ("l2_error", "h1_seminorm_error"): metric_values[f"component_{component}_{name}"] = fine["components"][component][name]
    return {"checks": checks, "metrics": {name: {"value": value, "unit": "1", "valid": passed,
            **({"reason": f"Vector numerical validation failed: {failures}"} if not passed else {})} for name, value in metric_values.items()},
            "mesh_studies": observed, "reference": {**copy.deepcopy(settings["problem"]["reference"]), "family": "lame", "components": list(COMPONENTS),
            "error_quadrature_degree": 8, "h1_semantics": "full Frobenius gradient seminorm", "traction_semantics": "sigma(u)*outward_normal",
            "rate_semantics": "Every vector and individual component adjacent mesh pair"},
            "pending_validations": ["physical_validation", "model_qualification"], "limitations": list(LIMITATIONS)}
