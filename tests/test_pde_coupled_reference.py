"""Independent component/region mathematics and labelled synthetic admission."""

from collections import defaultdict
from copy import deepcopy
from functools import lru_cache
import math

import pytest

from plugins.pde_coupled import reference as domain
from test_pde_rectangle_reference import synthetic_observations


@lru_cache(maxsize=1)
def _baseline(): return domain.manufactured_settings()


def small_settings():
    settings = deepcopy(_baseline())
    settings["mesh"]["cell_counts"] = [2, 4, 8]
    return settings


def synthetic_coupled(settings=None):
    """Existing rectangle topology only; fields/norms are unsolved test fixtures."""
    settings = settings or small_settings()
    geometry = domain.rectangle.manufactured_settings(lengths=settings["problem"]["domain"]["lengths"])
    geometry["mesh"] = deepcopy(settings["mesh"])
    studies, fields = synthetic_observations(geometry)
    trees, bindings = domain._trees(settings["problem"]), []
    for index, (study, field) in enumerate(zip(studies, fields)):
        n, lx = study["cells_per_axis"], settings["problem"]["domain"]["lengths"][0]
        field.update(field_type="vector", components=["u0", "u1"], block_size=2, cell_ids=list(range(2*n*n)))
        field["values"] = [[domain._value(tree, point) for tree in trees["reference"]["left" if point[0] <= lx/2 else "right"]] for point in field["coordinates"]]
        field["cell_regions"] = ["left" if max(field["coordinates"][node][0] for node in cell) <= lx/2 else "right" for cell in field["cell_node_ids"]]
        adjacent, region_nodes, region_cells = defaultdict(list), {r: set() for r in domain.REGIONS}, {r: [] for r in domain.REGIONS}
        for cell_id, cell, region in zip(field["cell_ids"], field["cell_node_ids"], field["cell_regions"]):
            region_nodes[region].update(cell)
            region_cells[region].append(cell_id)
            for a, b in ((0, 1), (1, 2), (2, 0)): adjacent[tuple(sorted((cell[a], cell[b])))].append((cell_id, region))
        interface_nodes = [node for node, point in zip(field["node_ids"], field["coordinates"]) if point[0] == lx/2]
        interface_edges = sorted(edge for edge in adjacent if set(edge) <= set(interface_nodes))
        neighbours = [{region: cell for cell, region in adjacent[edge]} for edge in interface_edges]
        field["interface"] = {"facet_ids": list(range(4*n, 5*n)), "facet_node_ids": [list(edge) for edge in interface_edges],
            "node_ids": interface_nodes, "adjacent_cell_ids": [[row["left"], row["right"]] for row in neighbours],
            "measure": settings["problem"]["domain"]["lengths"][1], "plus_x_normal": [1., 0.]}
        old_boundaries, boundaries = field["boundaries"], {}
        for side in domain.SIDES:
            boundaries[side] = {}
            for region in domain.touching(side):
                old = old_boundaries[side]
                selected = list(range(n)) if side[0] == "x" else list(range(n//2)) if region == "left" else list(range(n//2, n))
                pair_rows = [old["facet_node_ids"][row] for row in selected]
                nodes = sorted({node for pair in pair_rows for node in pair})
                fraction = 1. if side[0] == "x" else .5
                boundaries[side][region] = {"facet_ids": [old["facet_ids"][row] for row in selected], "facet_node_ids": pair_rows,
                    "dof_ids": nodes, "measure": fraction*old["measure"], "normal_integral": [fraction*value for value in old["normal_integral"]],
                    "prescribed_values": [[domain._value(tree, field["coordinates"][node]) for tree in trees["boundaries"][side][region]] for node in nodes],
                    "prescribed_integral": [0., 0.]}  # No native quadrature assertion.
        field["boundaries"] = boundaries
        rows = [{"index": component, "field": f"u{component}", "l2_error": (.024, .036)[component]/4**index,
                 "h1_seminorm_error": (.4, .6)[component]/2**index, "l2_convergence_rate": 2. if index else None,
                 "h1_seminorm_convergence_rate": 1. if index else None, "boundary_value_error": 0.} for component in range(2)]
        weak = settings["problem"]["weak_form"]
        study.update(global_nodes=(n+1)**2, global_dofs=2*(n+1)**2, dirichlet_nodes=len(field["dirichlet_node_ids"]),
            dirichlet_dofs=2*len(field["dirichlet_node_ids"]), block_size=2, solution_sync_error=0., components=rows,
            region_coefficients=deepcopy(weak["diffusion"]), reaction_matrix=deepcopy(weak["reaction"]),
            region_cell_counts={region: n*n for region in domain.REGIONS}, interface_facets=n,
            l2_error=math.hypot(*(row["l2_error"] for row in rows)), h1_seminorm_error=math.hypot(*(row["h1_seminorm_error"] for row in rows)))
        bindings.append({"schema_version": "1", "components": ["u0", "u1"], "regions": {
            region: {"cell_ids": region_cells[region], "node_ids": sorted(region_nodes[region]),
                     "diffusion": deepcopy(weak["diffusion"][region]), "reaction": deepcopy(weak["reaction"]),
                     **{key: [[domain._value(tree, field["coordinates"][node]) for tree in trees[name][region]] for node in sorted(region_nodes[region])]
                        for key, name in (("rhs_values", "rhs"), ("reference_values", "reference"))}}
            for region in domain.REGIONS}})
    return studies, fields, bindings


def refresh_errors(studies):
    for index, study in enumerate(studies):
        for name, rate in (("l2_error", "l2_convergence_rate"), ("h1_seminorm_error", "h1_seminorm_convergence_rate")):
            study[name] = math.hypot(*(row[name] for row in study["components"]))
            study[rate] = domain.expression.error_rate(studies[index-1][name], study[name]) if index else None
            for component, row in enumerate(study["components"]): row[rate] = domain.expression.error_rate(studies[index-1]["components"][component][name], row[name]) if index else None


@pytest.mark.parametrize("reaction", [None, [[2., .25], [.25, 1.]]])
def test_manufactured_operator_and_interface_flux_use_independent_component_derivatives(reaction):
    settings = domain.manufactured_settings(reaction=reaction)
    trees, weak = domain._trees(settings["problem"]), settings["problem"]["weak_form"]
    slopes = {"left": (1., -2.), "right": (5/31, -22/31)}
    for region in domain.REGIONS:
        matrix, a = weak["diffusion"][region], slopes[region]
        for x, y in ((.37, .29), (1., .3), (1.6, .7)):
            s, beta = x-1., (1., 2.)
            u = (1+y+a[0]*s+s*s*y*y, 2-3*y+a[1]*s+2*s*s*y*y)
            laplace = [2*b*(s*s+y*y) for b in beta]
            expected = [sum(weak["reaction"][i][j]*u[j]-matrix[i][j]*laplace[j] for j in range(2)) for i in range(2)]
            assert [domain._value(tree, (x, y)) for tree in trees["rhs"][region]] == pytest.approx(expected)
            derivative_y = (1+2*s*s*y, -3+4*s*s*y)
            assert [domain._value(tree, (x, y)) for tree in trees["boundaries"]["ymax"][region]] == pytest.approx([sum(matrix[i][j]*derivative_y[j] for j in range(2)) for i in range(2)])
        interface_flux = [sum(matrix[i][j]*a[j] for j in range(2)) for i in range(2)]
        assert interface_flux == pytest.approx([1., -1.5])
    y = .7
    rhs = {region: [domain._value(tree, (1., y)) for tree in trees["rhs"][region]] for region in domain.REGIONS}
    assert [rhs["right"][i]-rhs["left"][i] for i in range(2)] == pytest.approx([0., -2*y*y])
    assert [domain._value(tree, (1., y)) for tree in trees["reference"]["left"]] == pytest.approx([domain._value(tree, (1., y)) for tree in trees["reference"]["right"]])


def test_default_neumann_segment_integrals_and_harmonic_zero_source():
    trees = domain._trees(_baseline()["problem"])
    expected = {("xmax", "right"): (3., 5/6), ("ymax", "left"): (5/2, -5/6), ("ymax", "right"): (15/2, -25/6)}
    for (side, region), integral in expected.items():
        points = ((2., 0.), (2., .5), (2., 1.)) if side == "xmax" else ((0., 1.), (.5, 1.), (1., 1.)) if region == "left" else ((1., 1.), (1.5, 1.), (2., 1.))
        assert [sum(weight*domain._value(tree, point)/6 for weight, point in zip((1, 4, 1), points)) for tree in trees["boundaries"][side][region]] == pytest.approx(integral)
    harmonic = domain.manufactured_settings(case="harmonic")
    assert harmonic["problem"]["weak_form"]["rhs"] == {"left": ["0.0", "0.0"], "right": ["0.0", "0.0"]}
    harmonic_trees = domain._trees(harmonic["problem"])
    assert [domain._value(tree, (1., .5)) for tree in harmonic_trees["reference"]["left"]] == pytest.approx([1+.5-.5**2, 2-3*.5-2*.5**2])


@pytest.mark.parametrize("matrix,positive", [([[1., 2.], [2., 1.]], True), ([[1., .5], [.500000000000001, 1.]], True),
    ([[True, 0.], [0., 1.]], True), ([[1., 0.], [0., float("inf")]], True), ([[0., 0.], [0., 1.]], True),
    ([[0., 1e-200], [1e-200, 1.]], False), ([[1., 2.], [2., 1.]], False), ([[5e-324, 0.], [0., 1e308]], True)])
def test_matrix_shape_exact_symmetry_and_scaled_principal_minors_refuse(matrix, positive):
    with pytest.raises(domain.PDEInputError): domain._matrix(matrix, "test matrix", positive=positive)


def test_extreme_scaled_spd_and_semidefinite_reaction_are_not_clipped_or_mutated():
    for value in (1e-308, 1e308):
        matrix = [[value, 0.], [0., value]]
        assert domain._matrix(matrix, "scaled SPD", positive=True) == matrix
    for matrix in ([[0., 0.], [0., 0.]], [[1., 1.], [1., 1.]], [[0., 0.], [0., 1.]]):
        assert domain._matrix(matrix, "PSD") == matrix
    settings, original = small_settings(), small_settings()
    declaration, normalized = domain.model_declaration(settings), domain.validate_settings(settings)
    assert declaration["case"] == "rectangle_coupled_diffusion"
    assert declaration["constitutive_law"]["diffusion_axis"] == "component_rows_of_grad_u"
    assert declaration["model"]["geometry"]["interface"] == {"axis": 0, "fraction": .5}
    declaration["constitutive_law"]["diffusion"]["left"]["value"][0][0] = 99.
    normalized["problem"]["weak_form"]["rhs"]["left"][0] = "changed"
    assert settings == original


@pytest.mark.parametrize("kind", ["unsafe", "rhs_shape", "interface_u1", "odd", "pure_neumann", "touching", "time", "finite_grid"])
def test_invalid_interface_and_region_inputs_refuse_without_repair(kind):
    settings = small_settings()
    if kind == "unsafe": settings["problem"]["weak_form"]["rhs"]["right"][1] = "__import__('os').getcwd()"
    elif kind == "rhs_shape": settings["problem"]["weak_form"]["rhs"]["right"].pop()
    elif kind == "interface_u1": settings["problem"]["boundaries"]["ymin"]["value"]["right"][1] += "+1"
    elif kind == "odd": settings["mesh"]["cell_counts"] = [3, 6, 12]
    elif kind == "pure_neumann":
        for side in settings["problem"]["boundaries"].values(): side["type"] = "neumann"
    elif kind == "touching": settings["problem"]["boundaries"]["xmin"]["value"]["right"] = ["0.0", "0.0"]
    elif kind == "time": settings["problem"]["reference"]["solution"]["left"][1] = "t"
    else: settings["problem"]["weak_form"]["rhs"]["right"][0] = "1/(x[0]-1.5)"
    with pytest.raises(domain.PDEInputError): domain.validate_settings(settings)


def test_complete_original_fields_shared_interface_and_both_source_traces_are_admitted():
    settings = small_settings()
    studies, fields, bindings = synthetic_coupled(settings)
    before = deepcopy((settings, studies, fields, bindings))
    result = domain.assess(settings, studies, fields, bindings)
    assert all(row["status"] == "PASS" for row in result["checks"])
    assert len(result["metrics"]) == 9 and all(row["valid"] for row in result["metrics"].values())
    interface_nodes = fields[-1]["interface"]["node_ids"]
    left, right = bindings[-1]["regions"]["left"], bindings[-1]["regions"]["right"]
    assert set(left["node_ids"]) & set(right["node_ids"]) == set(interface_nodes)
    assert left["rhs_values"][left["node_ids"].index(interface_nodes[-1])][1] != right["rhs_values"][right["node_ids"].index(interface_nodes[-1])][1]
    assert (settings, studies, fields, bindings) == before
    result["reference"]["components"].pop()
    assert domain.COMPONENTS == ["u0", "u1"]


@pytest.mark.parametrize("kind", ["tag_reversal", "missing_cell", "duplicate_interface", "adjacency_order", "shared_node", "interface_normal",
    "segment_duplicate", "segment_trace", "RHS_trace_average", "matrix", "component_order", "truncated", "aggregate", "rate", "residual"])
def test_malformed_original_region_interface_and_directed_evidence_fails_closed(kind):
    studies, fields, bindings = synthetic_coupled()
    study, field, binding = studies[-1], fields[-1], bindings[-1]
    if kind == "tag_reversal": field["cell_regions"][0] = "right"
    elif kind == "missing_cell": field["cell_ids"].pop()
    elif kind == "duplicate_interface": field["interface"]["facet_node_ids"][0] = list(field["interface"]["facet_node_ids"][1])
    elif kind == "adjacency_order": field["interface"]["adjacent_cell_ids"][0].reverse()
    elif kind == "shared_node": binding["regions"]["right"]["node_ids"].remove(field["interface"]["node_ids"][0])
    elif kind == "interface_normal": field["interface"]["plus_x_normal"] = [-1., 0.]
    elif kind == "segment_duplicate": field["boundaries"]["ymax"]["right"]["facet_ids"][0] = field["boundaries"]["ymax"]["left"]["facet_ids"][0]
    elif kind == "segment_trace": field["boundaries"]["ymax"]["right"]["prescribed_values"][0] = list(field["boundaries"]["ymax"]["left"]["prescribed_values"][-1])
    elif kind == "RHS_trace_average":
        node = field["interface"]["node_ids"][-1]
        left, right = binding["regions"]["left"], binding["regions"]["right"]
        right["rhs_values"][right["node_ids"].index(node)][1] = (right["rhs_values"][right["node_ids"].index(node)][1]+left["rhs_values"][left["node_ids"].index(node)][1])/2
    elif kind == "matrix": study["region_coefficients"]["right"][0][1] = study["region_coefficients"]["right"][1][0] = .5
    elif kind == "component_order": study["components"].reverse()
    elif kind == "truncated": field["values"][0].pop()
    elif kind == "aggregate": study["l2_error"] = study["components"][0]["l2_error"]
    elif kind == "rate": study["components"][1]["l2_convergence_rate"] = 3.
    else: study["linear_residual"]["relative"] = 0.
    with pytest.raises(domain.PDEInputError): domain.assess(small_settings(), studies, fields, bindings)


def test_finite_criteria_and_dirichlet_failures_reject_all_metrics_without_changing_limits():
    studies, fields, bindings = synthetic_coupled()
    studies[-1]["components"][1]["l2_error"] = .0027
    refresh_errors(studies)
    assert studies[-1]["l2_convergence_rate"] > 1.8 and studies[-1]["components"][1]["l2_convergence_rate"] < 1.8
    fields[-1]["values"][0][1] += .25
    studies[-1]["components"][1]["boundary_value_error"] = studies[-1]["boundary_value_error"] = .25
    studies[0]["linear_residual"].update(absolute=1e-6, relative=5e-7)
    result = domain.assess(small_settings(), studies, fields, bindings)
    assert {"pde_boundary_and_mesh", "pde_l2_convergence_rate", "pde_linear_residual"} <= {row["code"] for row in result["checks"] if row["status"] == "FAIL"}
    assert all(not row["valid"] and row["reason"] for row in result["metrics"].values())
