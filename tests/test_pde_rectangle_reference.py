"""Independent scalar checks and synthetic raw-field admission; no native solver."""

from copy import deepcopy
import math

import pytest

from caelab.adapters.fenicsx_worker import PDEInputError, error_rate
from plugins.pde_elliptic import reference as domain


def synthetic_observations(settings=None):
    """Complete contract fixture; its declared norm errors are not solved observations."""
    settings = settings or domain.manufactured_settings()
    selected = settings.get("mode") == "selected_mesh"
    lx, ly = settings["problem"]["domain"]["lengths"]
    fields, studies = [], []
    for index, n in enumerate(settings["mesh"]["cell_counts"]):
        coordinates = [[lx * i / n, ly * j / n] for i in range(n + 1) for j in range(n + 1)]
        ids = list(range(len(coordinates)))
        values = [x - 2*y if selected else x*x*y*y+x+2*y+1 for x, y in coordinates]
        cells = []
        for i in range(n):
            for j in range(n):
                a = i * (n + 1) + j
                cells.extend([[a, a + n + 1, a + 1], [a + n + 1, a + n + 2, a + 1]])
        side_nodes = {"xmin": list(range(n + 1)), "xmax": list(range(n * (n + 1), (n + 1)**2)),
                      "ymin": [i * (n + 1) for i in range(n + 1)], "ymax": [i * (n + 1) + n for i in range(n + 1)]}
        boundary, union = {}, set()
        for offset, side in enumerate(domain.SIDES):
            nodes = side_nodes[side]
            length = ly if side[0] == "x" else lx
            boundary[side] = {"facet_ids": list(range(offset * n, (offset + 1) * n)),
                              "facet_node_ids": [[nodes[k], nodes[k + 1]] for k in range(n)], "dof_ids": nodes,
                              "measure": length, "normal_integral": [-ly, 0.] if side == "xmin" else [ly, 0.] if side == "xmax"
                              else [0., -lx] if side == "ymin" else [0., lx],
                              "prescribed_values": [domain.expression_value(settings["problem"]["boundaries"][side]["value"], *coordinates[node]) for node in nodes],
                              "prescribed_integral": 0.}  # Synthetic finite metadata, not a native quadrature claim.
            if settings["problem"]["boundaries"][side]["type"] == "dirichlet":
                union.update(nodes)
                if selected:
                    for node, value in zip(nodes, boundary[side]["prescribed_values"]):
                        values[node] = value
        fields.append({"schema_version": "1", "coordinates_unit": "1", "field_unit": "1", "node_ids": ids,
                       "coordinates": coordinates, "values": values, "cell_node_ids": cells,
                       "dirichlet_node_ids": sorted(union), "boundaries": boundary})
        l2, h1 = .024 / 4**index, .4 / 2**index
        studies.append({"cells_per_axis": n, "nominal_h": math.hypot(lx, ly) / n, "degree": 1, "cell_type": "triangle",
                        "global_cells": 2*n*n, "global_dofs": (n+1)**2, "dirichlet_dofs": len(union), "boundary_value_error": 0.,
                        "l2_error": None if selected else l2, "h1_seminorm_error": None if selected else h1,
                        "l2_convergence_rate": None if selected else 2. if index else None,
                        "h1_seminorm_convergence_rate": None if selected else 1. if index else None,
                        "linear_residual": {"absolute": 1e-13, "rhs_norm": 2., "relative": 5e-14, "normalization": "rhs_l2_norm"},
                        "ksp_convergence_reason": 4, "ksp_iterations": 1})
    return studies, fields


def test_manufactured_sources_and_unequal_outward_fluxes_match_direct_derivatives():
    for k, c, lengths in ((1., 0., (2., 1.)), (2., 3., (1.5, .75))):
        settings = domain.manufactured_settings(c, lengths, k)
        for x, y in ((0., 0.), (.37, .29), lengths):
            # Direct u_xx/u_yy independent of the expression parser and factory.
            u = x*x*y*y+x+2*y+1
            expected = -k*(2*y*y+2*x*x)+c*u
            assert domain.source_value(k, c, x, y) == pytest.approx(expected)
            assert domain.expression_value(settings["problem"]["weak_form"]["rhs"], x, y) == pytest.approx(expected)
        for side, point, expected in (("xmin", (0., .2), 1.4), ("ymin", (.3, 0.), 1.3),
                                      ("xmax", (lengths[0], .2), k*(2*lengths[0]*.2**2+1)),
                                      ("ymax", (.3, lengths[1]), k*(2*lengths[1]*.3**2+2))):
            assert domain.boundary_value(k, side, *point) == pytest.approx(expected)
            assert domain.expression_value(settings["problem"]["boundaries"][side]["value"], *point) == pytest.approx(expected)
    # Only the two prescribed Neumann integrals; these are not full flux balance.
    assert 2*2*1**3/3+1 == pytest.approx(7/3)
    assert 2*1*2**3/3+2*2 == pytest.approx(28/3)


def test_normalization_and_common_declaration_are_independent_deep_copies():
    settings = domain.manufactured_settings()
    original = deepcopy(settings)
    normalized = domain.validate_settings(settings)
    declaration = domain.model_declaration(settings)
    normalized["mesh"]["cell_counts"][0] = 99
    declaration["model"]["geometry"]["dimensions"][0] = 999
    assert settings == original
    assert domain.manufactured_settings() == original
    assert declaration["boundary_conditions"][1]["neumann_semantics"] == "diffusion*grad(u).outward_normal"
    assert declaration["outputs"]["fields"] == [{"field": "u", "type": "scalar", "unit": "1"}]


@pytest.mark.parametrize("path,value", [
    (("problem", "domain", "lengths"), [True, 1.]),
    (("problem", "domain", "lengths"), [.0009, 1.]),
    (("problem", "domain", "lengths"), [1001., 1.]),
    (("problem", "domain", "lengths"), [float("nan"), 1.]),
    (("problem", "weak_form", "diffusion"), 0.),
    (("problem", "weak_form", "reaction"), -1.),
    (("problem", "weak_form", "rhs"), "__import__('os').system('x')"),
    (("problem", "reference", "solution"), "x.__class__"),
    (("mesh", "cell_counts"), [8, 24, 32]),
    (("mesh", "degree"), 2),
    (("validation", "min_h1_rate"), True),
    (("validation", "max_l2_error"), float("inf")),
])
def test_unsafe_or_unsupported_declarations_are_refused(path, value):
    request = domain.manufactured_settings()
    target = request
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(PDEInputError):
        domain.validate_settings(request)


def test_whole_side_schema_corner_consistency_and_dirichlet_anchor_are_required():
    request = domain.manufactured_settings()
    for change in (lambda b: b.pop("xmax"), lambda b: b.update(zmin={"type": "neumann", "value": "0"}),
                   lambda b: b["xmin"].update(type="robin"), lambda b: b["xmin"].update(value="2*x[1]+2"),
                   lambda b: b["xmin"].update(value="exp(1000+x[1])"),
                   lambda b: [entry.update(type="neumann") for entry in b.values()]):
        broken = deepcopy(request)
        change(broken["problem"]["boundaries"])
        with pytest.raises(PDEInputError):
            domain.validate_settings(broken)
    for extra in ("time", "python", "petsc_options", "mpi"):
        with pytest.raises(PDEInputError):
            domain.validate_settings({**request, extra: "unsupported"})


def test_complete_synthetic_fields_and_all_pair_numerics_pass_without_qualification():
    settings = domain.manufactured_settings()
    studies, fields = synthetic_observations(settings)
    before = deepcopy((studies, fields, settings))
    assessment = domain.assess(settings, studies, fields)
    assert all(check["status"] == "PASS" for check in assessment["checks"])
    assert assessment["metrics"]["l2_error"] == {"value": .0015, "unit": "1", "valid": True}
    assert assessment["pending_validations"] == ["physical_validation", "model_qualification"]
    assert (studies, fields, settings) == before
    assert assessment["mesh_studies"][-1]["recomputed_boundary_value_error"] == 0.


@pytest.mark.parametrize("kind", ["duplicate_node", "duplicate_coordinate", "outside", "missing_value", "nonfinite", "duplicate_cell",
                                 "degenerate", "overlap", "facet_duplicate", "facet_wrong_nodes", "missing_side", "normal", "measure",
                                 "prescribed", "union", "study_count", "summary_error", "residual", "rate", "first_rate"])
def test_malformed_field_identity_or_inconsistent_observations_fail_closed(kind):
    settings = domain.manufactured_settings()
    studies, fields = synthetic_observations(settings)
    study, field = studies[-1], fields[-1]
    side = field["boundaries"]["xmin"]
    if kind == "duplicate_node": field["node_ids"][1] = field["node_ids"][0]
    elif kind == "duplicate_coordinate": field["coordinates"][1] = field["coordinates"][0]
    elif kind == "outside": field["coordinates"][1][0] = -.1
    elif kind == "missing_value": field["values"].pop()
    elif kind == "nonfinite": field["values"][1] = float("inf")
    elif kind == "duplicate_cell": field["cell_node_ids"][1] = field["cell_node_ids"][0]
    elif kind == "degenerate": field["cell_node_ids"][0][0] = field["cell_node_ids"][0][1]
    elif kind == "overlap": field["cell_node_ids"][1] = [0, 33, 34]
    elif kind == "facet_duplicate": side["facet_ids"][1] = side["facet_ids"][0]
    elif kind == "facet_wrong_nodes": side["facet_node_ids"][0] = [33, 34]
    elif kind == "missing_side": field["boundaries"].pop("ymax")
    elif kind == "normal": side["normal_integral"][0] *= -1
    elif kind == "measure": side["measure"] += .1
    elif kind == "prescribed": side["prescribed_values"][0] += .1
    elif kind == "union": field["dirichlet_node_ids"].pop()
    elif kind == "study_count": study["global_dofs"] = True
    elif kind == "summary_error": study["boundary_value_error"] = .01
    elif kind == "residual": study["linear_residual"]["relative"] = 0.
    elif kind == "rate": study["h1_seminorm_convergence_rate"] = 99.
    elif kind == "first_rate": studies[0]["l2_convergence_rate"] = 2.
    with pytest.raises(PDEInputError):
        domain.assess(settings, studies, fields)


@pytest.mark.parametrize("failure", ["l2", "h1", "coarse_pair", "residual", "ksp", "boundary"])
def test_finite_numerical_failure_keeps_observed_values_and_invalidates_metrics(failure):
    settings = domain.manufactured_settings()
    studies, fields = synthetic_observations(settings)
    study = studies[-1]
    if failure == "l2":
        study["l2_error"] = .05
        study["l2_convergence_rate"] = error_rate(studies[-2]["l2_error"], .05)
    elif failure == "h1":
        study["h1_seminorm_error"] = .6
        study["h1_seminorm_convergence_rate"] = error_rate(studies[-2]["h1_seminorm_error"], .6)
    elif failure == "coarse_pair":
        studies[0]["l2_error"] = .01
        studies[1]["l2_convergence_rate"] = error_rate(.01, studies[1]["l2_error"])
    elif failure == "residual":
        study["linear_residual"].update(absolute=1e-8, relative=5e-9)
    elif failure == "ksp": study["ksp_convergence_reason"] = -5
    elif failure == "boundary":
        fields[-1]["values"][0] += .01
        study["boundary_value_error"] = abs(fields[-1]["values"][0]-1.)
    assessment = domain.assess(settings, studies, fields)
    assert any(check["status"] == "FAIL" for check in assessment["checks"])
    assert all(not metric["valid"] and metric["reason"] for metric in assessment["metrics"].values())
    assert assessment["mesh_studies"][-1]["l2_error"] == study["l2_error"]
    assert settings["validation"] == domain.manufactured_settings()["validation"]


def test_zero_reference_errors_do_not_invent_rates_and_zero_rhs_normalization_is_explicit():
    settings = domain.manufactured_settings()
    studies, fields = synthetic_observations(settings)
    for study in studies:
        study.update(l2_error=0., l2_convergence_rate=None)
        study["linear_residual"] = {"absolute": 1e-14, "rhs_norm": 0., "relative": 1e-14, "normalization": "absolute_for_zero_rhs"}
    assessment = domain.assess(settings, studies, fields)
    assert next(check for check in assessment["checks"] if check["code"] == "pde_l2_convergence_rate")["status"] == "FAIL"
    assert next(check for check in assessment["checks"] if check["code"] == "pde_linear_residual")["status"] == "PASS"


def test_selected_factory_has_independent_editable_defaults_without_benchmark_validation(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Selected input must not construct a reference or benchmark sweep")
    monkeypatch.setattr(domain, "_linear_settings", forbidden)
    monkeypatch.setattr(domain, "manufactured_settings", forbidden)
    settings = domain.selected_settings()
    assert settings == {
        "mode": "selected_mesh",
        "problem": {"domain": {"type": "rectangle", "lengths": [2., 1.]},
                    "weak_form": {"diffusion": 1., "reaction": 0., "rhs": "1"},
                    "boundaries": {"xmin": {"type": "dirichlet", "value": "0"},
                                   "xmax": {"type": "dirichlet", "value": "0"},
                                   "ymin": {"type": "neumann", "value": "0"},
                                   "ymax": {"type": "neumann", "value": "0"}}, "reference": None},
        "mesh": {"cell_counts": [16], "degree": 1}, "validation": {"max_residual_relative": 1e-10}}
    original = deepcopy(settings)
    declaration = domain.model_declaration(settings)
    normalized = domain.validate_settings(settings)
    normalized["mesh"]["cell_counts"][0] = 3
    declaration["model"]["geometry"]["dimensions"][0] = 3.
    declaration["outputs"]["metrics"].clear()
    assert settings == original == domain.selected_settings()
    assert declaration["reference"] is None and declaration["mode"] == "selected_mesh"


@pytest.mark.parametrize("count", [1, 16, 128])
def test_selected_accepts_one_bounded_mesh_and_arbitrary_safe_rhs_mixed_boundary_data(count):
    settings = domain.selected_settings()
    settings["mesh"]["cell_counts"] = [count]
    settings["problem"]["weak_form"].update(diffusion=2., reaction=3., rhs="exp(x[0])-2*sin(x[1])")
    settings["problem"]["boundaries"]["xmin"]["value"] = "-2*x[1]"
    settings["problem"]["boundaries"]["xmax"]["value"] = "1-2*x[1]"
    settings["problem"]["boundaries"]["ymin"]["value"] = "-3*x[0]"
    before = deepcopy(settings)
    assert domain.validate_settings(settings) == before
    declaration = domain.model_declaration(settings)
    assert settings == before and declaration["reference"] is None
    assert declaration["model"]["mesh"]["cell_counts"] == [count]
    assert declaration["loads"][0]["expression"] == "exp(x[0])-2*sin(x[1])"
    assert declaration["boundary_conditions"][2]["expression"] == "-3*x[0]"
    assert declaration["outputs"]["metrics"][-2:] == ["field_min", "field_max"]


@pytest.mark.parametrize("path,value", [
    (("mode",), "benchmark"), (("mode",), True),
    (("mesh", "cell_counts"), []), (("mesh", "cell_counts"), [2, 4, 8]),
    (("mesh", "cell_counts"), [0]), (("mesh", "cell_counts"), [129]),
    (("mesh", "cell_counts"), [True]), (("mesh", "cell_counts"), [16.]),
    (("mesh", "degree"), True), (("mesh", "degree"), 2),
    (("validation",), {"max_residual_relative": 1e-10, "min_l2_rate": 1.8}),
    (("validation", "max_residual_relative"), 0.), (("validation", "max_residual_relative"), True),
    (("validation", "max_residual_relative"), float("nan")),
    (("problem", "reference"), {"solution": "0", "source": "fake reference"}),
    (("problem", "weak_form", "diffusion"), False), (("problem", "weak_form", "diffusion"), float("inf")),
    (("problem", "weak_form", "reaction"), -1.),
    (("problem", "weak_form", "rhs"), "__import__('os').system('x')"),
    (("problem", "weak_form", "rhs"), "x[2]"),
    (("problem", "boundaries", "xmin", "type"), "robin"),
    (("problem", "domain", "lengths"), [True, 1.]),
])
def test_selected_rejects_unsupported_modes_references_meshes_and_unsafe_values(path, value):
    settings = domain.selected_settings()
    target = settings
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(PDEInputError):
        domain.validate_settings(settings)


@pytest.mark.parametrize("kind", ["missing_mode", "extra_top", "missing_reference", "extra_weak", "extra_mesh", "pure_neumann", "corner"])
def test_selected_requires_exact_keys_and_consistent_anchored_whole_sides(kind):
    settings = domain.selected_settings()
    if kind == "missing_mode": settings.pop("mode")
    elif kind == "extra_top": settings["python"] = "forbidden"
    elif kind == "missing_reference": settings["problem"].pop("reference")
    elif kind == "extra_weak": settings["problem"]["weak_form"]["ufl"] = "forbidden"
    elif kind == "extra_mesh": settings["mesh"]["path"] = "/untrusted"
    elif kind == "pure_neumann":
        for boundary in settings["problem"]["boundaries"].values(): boundary["type"] = "neumann"
    else: settings["problem"]["boundaries"]["ymin"] = {"type": "dirichlet", "value": "1"}
    with pytest.raises(PDEInputError):
        domain.validate_settings(settings)


def test_selected_complete_fields_keep_signed_extrema_without_reference_or_accuracy_claim(monkeypatch):
    settings = domain.selected_settings()
    settings["mesh"]["cell_counts"] = [2]
    studies, fields = synthetic_observations(settings)
    before = deepcopy((settings, studies, fields))
    monkeypatch.setattr(domain, "error_rate", lambda *args: pytest.fail("Selected mode must not evaluate mesh rates"))
    assessment = domain.assess(settings, studies, fields)
    assert (settings, studies, fields) == before
    assert {check["code"] for check in assessment["checks"]} == {"pde_solver_convergence", "pde_boundary_and_mesh", "pde_linear_residual"}
    assert all(check["status"] == "PASS" for check in assessment["checks"])
    assert assessment["metrics"]["field_min"] == {"value": -1., "unit": "1", "valid": True}
    assert assessment["metrics"]["field_max"] == {"value": 1., "unit": "1", "valid": True}
    for name in ("l2_error", "h1_seminorm_error", "l2_convergence_rate", "h1_seminorm_convergence_rate"):
        assert assessment["metrics"][name]["value"] is None and not assessment["metrics"][name]["valid"]
        assert "Not evaluated" in assessment["metrics"][name]["reason"]
    assert assessment["reference"]["status"] == "UNKNOWN"
    assert assessment["reference"]["solution"] is assessment["reference"]["source"] is assessment["reference"]["error_quadrature_degree"] is None
    assert assessment["pending_validations"] == ["reference_agreement", "mesh_convergence", "physical_validation", "model_qualification"]


@pytest.mark.parametrize("kind", ["reference_error", "reference_rate", "missing_reference_metadata", "nonfinite_field", "missing_node", "boundary", "residual", "ksp"])
def test_selected_field_and_reference_metadata_refusal_preserves_finite_numerical_failures(kind):
    settings = domain.selected_settings()
    settings["mesh"]["cell_counts"] = [2]
    studies, fields = synthetic_observations(settings)
    study, field = studies[0], fields[0]
    if kind == "reference_error": study["l2_error"] = 0.
    elif kind == "reference_rate": study["h1_seminorm_convergence_rate"] = False
    elif kind == "missing_reference_metadata": study.pop("l2_error")
    elif kind == "nonfinite_field": field["values"][1] = float("inf")
    elif kind == "missing_node": field["node_ids"].pop()
    elif kind == "boundary": field["values"][0] = .1; study["boundary_value_error"] = .1
    elif kind == "residual": study["linear_residual"].update(absolute=1e-8, relative=5e-9)
    else: study["ksp_convergence_reason"] = -5
    if kind not in {"boundary", "residual", "ksp"}:
        with pytest.raises(PDEInputError): domain.assess(settings, studies, fields)
    else:
        assessment = domain.assess(settings, studies, fields)
        assert any(check["status"] == "FAIL" for check in assessment["checks"])
        assert all(not metric["valid"] for metric in assessment["metrics"].values())
        assert assessment["metrics"]["field_min"]["value"] == min(field["values"])
        assert assessment["metrics"]["field_max"]["value"] == max(field["values"])


def test_benchmark_three_key_contract_still_requires_reference_and_sweep():
    settings = domain.manufactured_settings()
    assert set(settings) == {"problem", "mesh", "validation"}
    assert settings["mesh"] == {"cell_counts": [8, 16, 32], "degree": 1}
    assert settings["validation"] == {"max_l2_error": .03, "min_l2_rate": 1.8, "max_h1_seminorm_error": .5,
                                      "min_h1_rate": .9, "max_residual_relative": 1e-10}
    assert "metrics" not in domain.model_declaration(settings)["outputs"]
    for change in (lambda request: request["mesh"].update(cell_counts=[16]),
                   lambda request: request["problem"].update(reference=None),
                   lambda request: request.update(mode="selected_mesh")):
        broken = deepcopy(settings)
        change(broken)
        with pytest.raises(PDEInputError): domain.validate_settings(broken)
