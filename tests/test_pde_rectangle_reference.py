"""Independent scalar checks and synthetic raw-field admission; no native solver."""

from copy import deepcopy
import math

import pytest

from caelab.adapters.fenicsx_worker import PDEInputError, error_rate
from plugins.pde_elliptic import reference as domain


def synthetic_observations(settings=None):
    """Complete contract fixture; its declared norm errors are not solved observations."""
    settings = settings or domain.manufactured_settings()
    lx, ly = settings["problem"]["domain"]["lengths"]
    fields, studies = [], []
    for index, n in enumerate(settings["mesh"]["cell_counts"]):
        coordinates = [[lx * i / n, ly * j / n] for i in range(n + 1) for j in range(n + 1)]
        ids = list(range(len(coordinates)))
        values = [x*x*y*y+x+2*y+1 for x, y in coordinates]
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
        fields.append({"schema_version": "1", "coordinates_unit": "1", "field_unit": "1", "node_ids": ids,
                       "coordinates": coordinates, "values": values, "cell_node_ids": cells,
                       "dirichlet_node_ids": sorted(union), "boundaries": boundary})
        l2, h1 = .024 / 4**index, .4 / 2**index
        studies.append({"cells_per_axis": n, "nominal_h": math.hypot(lx, ly) / n, "degree": 1, "cell_type": "triangle",
                        "global_cells": 2*n*n, "global_dofs": (n+1)**2, "dirichlet_dofs": len(union), "boundary_value_error": 0.,
                        "l2_error": l2, "h1_seminorm_error": h1, "l2_convergence_rate": 2. if index else None,
                        "h1_seminorm_convergence_rate": 1. if index else None,
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
