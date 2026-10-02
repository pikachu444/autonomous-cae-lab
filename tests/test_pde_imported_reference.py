"""Scientific source controls and explicitly UNSOLVED P1 interpolant fixtures."""

from copy import deepcopy
import hashlib
import math

import pytest

from caelab.adapters import fenicsx_gmsh as syntax
from plugins.pde_imported import reference as domain


def small_settings(case="mixed", shape="l_shape", counts=(1, 2, 8)):
    return {"problem": domain.manufactured_problem(case, shape), "mesh": {"degree": 1, "levels": [syntax.manufactured_mesh(shape, n) for n in counts]},
            "validation": {"max_l2_error": .02, "max_h1_seminorm_error": .3, "min_l2_rate": 1.8, "min_h1_rate": .9, "max_residual_relative": 1e-10}}


def refresh_rates(studies):
    for i, row in enumerate(studies):
        for metric, rate in (("l2_error", "l2_convergence_rate"), ("h1_seminorm_error", "h1_seminorm_convergence_rate")):
            row[rate] = domain.convergence_rate(studies[i-1][metric], row[metric], studies[i-1]["max_edge_h"], row["max_edge_h"]) if i else None


def synthetic_imported(settings):
    """No solver: saved fields are nodal polynomial interpolants; maps are synthetic.

    Errors use the packet's closed uniform-grid interpolant formula. KSP/residual
    and synchronization records are labelled transport fixtures, not native proof.
    Every independent index space is deliberately permuted.
    """
    meshes = syntax.prepare(settings)
    studies, fields, bindings, mappings = [], [], [], []
    for i, mesh in enumerate(meshes):
        info = domain.mesh_geometry(mesh)
        original = [row["id"] for row in mesh["nodes"]]
        size, count = len(original), len(mesh["cells"])
        source_ids = list(reversed(original))
        source_to_dof = {source: node for node, source in enumerate(source_ids)}
        coordinates = [info["xyz"][source] for source in source_ids]
        problem = settings["problem"]
        values = [domain.expression_value(problem["reference"]["solution"], *point) for point in coordinates]
        all_edges = sorted({tuple(sorted((a, b))) for row in mesh["cells"] for a, b in zip(row["node_ids"], row["node_ids"][1:]+row["node_ids"][:1])})
        edge_to_facet = {edge: len(all_edges)-1-j for j, edge in enumerate(all_edges)}
        boundaries, selected = {}, set()
        for name, group in mesh["boundaries"].items():
            ordered = sorted(group["elements"], key=lambda row: edge_to_facet[tuple(sorted(row["node_ids"]))])
            nodes = sorted(source_to_dof[node] for node in info["groups"][name]["node_ids"])
            supplied = problem["boundaries"][name]
            if supplied["type"] == "dirichlet": selected.update(nodes)
            integral = 0.
            for element in ordered:
                p, q = [info["xyz"][node] for node in element["node_ids"]]
                midpoint = [(a+b)/2 for a, b in zip(p, q)]
                integral += math.dist(p, q)/6*(domain.expression_value(supplied["value"], *p)+4*domain.expression_value(supplied["value"], *midpoint)+domain.expression_value(supplied["value"], *q))
            boundaries[name] = {"facet_ids": [edge_to_facet[tuple(sorted(row["node_ids"]))] for row in ordered],
                "facet_node_ids": [[source_to_dof[node] for node in row["node_ids"]] for row in ordered], "source_element_ids": [row["id"] for row in ordered],
                "dof_ids": nodes, "measure": info["groups"][name]["measure"], "normal_integral": info["groups"][name]["normal_integral"],
                "prescribed_values": [domain.expression_value(supplied["value"], *coordinates[node]) for node in nodes], "prescribed_integral": integral}
        cell_sources = list(reversed([row["id"] for row in mesh["cells"]]))
        field = {"schema_version": "1", "coordinates_unit": "1", "field_unit": "1", "node_ids": list(range(size)), "source_node_ids": source_ids,
                 "coordinates": coordinates, "values": values, "cell_ids": list(range(count)), "source_cell_ids": cell_sources,
                 "cell_node_ids": [[source_to_dof[node] for node in info["cells"][source]["node_ids"]] for source in cell_sources], "dirichlet_node_ids": sorted(selected), "boundaries": boundaries}
        _, table = syntax.dense_import(mesh)
        geometry_indices = list(range(1, size))+[0]
        geometry_sources = [original[index] for index in geometry_indices]
        vertex_geometry = list(reversed(range(size)))
        importer_cells = [row["id"] for row in mesh["cells"]][1:]+[mesh["cells"][0]["id"]]
        physical_groups = {"body": {"dim": 2, "tag": 1}, **{name: {"dim": 1, "tag": group["tag"]} for name, group in mesh["boundaries"].items()}}
        mapping = {"schema_version": "1", **table, "geometry_input_indices": geometry_indices, "geometry_source_node_ids": geometry_sources,
                   "vertex_ids": list(range(size)), "vertex_geometry_indices": vertex_geometry, "vertex_dof_ids": [source_to_dof[geometry_sources[index]] for index in vertex_geometry],
                   "cell_ids": field["cell_ids"], "original_cell_index": [importer_cells.index(source) for source in cell_sources], "importer_cell_source_ids": importer_cells, "source_cell_ids": cell_sources,
                   "physical_groups": physical_groups, "boundary_source_elements": {name: row["source_element_ids"] for name, row in boundaries.items()},
                   "gmsh_initialization": {"argv": [], "read_config_files": False, "finalized": True}}
        weak = problem["weak_form"]
        binding = {"schema_version": "1", "source_sha256": mesh["source_sha256"], "dense_sha256": table["dense_sha256"], "node_ids": field["node_ids"], "source_node_ids": source_ids,
                   "diffusion": weak["diffusion"], "reaction": weak["reaction"], "rhs_values": [domain.expression_value(weak["rhs"], *point) for point in coordinates], "reference_values": values.copy()}
        n = math.sqrt(2)/info["max_edge_h"]
        harmonic = "**2-x[1]**2" in problem["reference"]["solution"]
        l2 = math.sqrt(info["area"]*(1 if harmonic else 11)/90)/n**2
        h1 = math.sqrt(2*info["area"]/3)/n
        study = {"level": i, "degree": 1, "cell_type": "triangle", "max_edge_h": info["max_edge_h"], "global_nodes": size, "global_dofs": size, "global_cells": count,
                 "dirichlet_nodes": len(selected), "dirichlet_dofs": len(selected), "boundary_value_error": 0., "l2_error": l2, "h1_seminorm_error": h1,
                 "linear_residual": {"absolute": 0., "rhs_norm": 0., "relative": 0., "normalization": "absolute_for_zero_rhs"}, "ksp_convergence_reason": 1, "ksp_iterations": 1,
                 "solver_policy": {"ksp_type": "preonly", "pc_type": "lu"}, "solution_synchronization": {"max_abs_difference": 0., "passed": True},
                 "coefficients": {"diffusion": weak["diffusion"], "reaction": weak["reaction"]}, "physical_groups": physical_groups,
                 "source_sha256": mesh["source_sha256"], "dense_sha256": table["dense_sha256"]}
        studies.append(study)
        fields.append(field)
        bindings.append(binding)
        mappings.append(mapping)
    refresh_rates(studies)
    return meshes, studies, fields, bindings, mappings


def test_l_polygon_embedding_boundary_normals_and_irregular_refinement_orders():
    settings = small_settings()
    meshes, studies, fields, bindings, mappings = synthetic_imported(settings)
    before = deepcopy((settings, meshes, studies, fields, bindings, mappings))
    for info in domain.mesh_series(meshes):
        assert info["area"] == 3 and sum(row["measure"] for row in info["groups"].values()) == 8
        assert info["groups"]["notch_horizontal"]["normal_integral"] == [0., 1.]
        assert info["groups"]["notch_vertical"]["normal_integral"] == [1., 0.]
    outcome = domain.assess(settings, meshes, studies, fields, bindings, mappings)
    assert all(row["status"] == "PASS" for row in outcome["checks"])
    assert outcome["pending_validations"] == ["physical_validation", "model_qualification"]
    assert [row["l2_convergence_rate"] for row in studies[1:]] == pytest.approx([2., 2.])
    assert [row["h1_seminorm_convergence_rate"] for row in studies[1:]] == pytest.approx([1., 1.])
    assert (settings, meshes, studies, fields, bindings, mappings) == before
    assert mappings[0]["geometry_input_indices"] != mappings[0]["vertex_dof_ids"]


@pytest.mark.parametrize("kind", ["duplicate_coordinate", "duplicate_cell", "missing_line", "crossing", "disconnected", "hanging", "hole"])
def test_normalized_scientific_topology_and_embedding_fail_closed(kind):
    mesh = syntax.parse_msh(**{key: value for key, value in {"data": syntax.manufactured_mesh("l_shape", 2)["data"], "sha256": syntax.manufactured_mesh("l_shape", 2)["sha256"]}.items()})
    if kind == "duplicate_coordinate": mesh["nodes"][1]["coordinates"] = mesh["nodes"][0]["coordinates"].copy()
    elif kind == "duplicate_cell": mesh["cells"][1]["node_ids"] = mesh["cells"][0]["node_ids"].copy()
    elif kind == "missing_line": mesh["boundaries"]["west"]["elements"].pop()
    elif kind == "crossing": mesh["nodes"][7]["coordinates"] = [1.75, .25]
    elif kind == "disconnected": mesh["cells"] = [mesh["cells"][0], mesh["cells"][-1]]
    elif kind == "hanging":
        # Collapse one nonadjacent vertex onto another edge, without retopologizing.
        next(row for row in mesh["nodes"] if row["coordinates"] == [1., 1.])["coordinates"] = [.25, 0.]
    else:
        # Remove a two-triangle interior square and expose an untagged hole.
        mesh = syntax.parse_msh(syntax.manufactured_mesh("rectangle", 3)["data"], syntax.manufactured_mesh("rectangle", 3)["sha256"])
        mesh["cells"] = [row for row in mesh["cells"] if row["id"] not in {29, 31}]
    with pytest.raises(domain.PDEInputError): domain.mesh_geometry(mesh)


@pytest.mark.parametrize("kind", ["polygon", "group_geometry", "nonrefining", "conflicting_D", "pure_N", "undefined_rhs", "missing_boundary"])
def test_problem_series_and_actual_boundary_input_preflight(kind):
    settings = small_settings()
    meshes = syntax.prepare(settings)
    if kind == "polygon":
        for row in meshes[-1]["nodes"]: row["coordinates"][0] *= 1.1
    elif kind == "group_geometry":
        a, b = meshes[-1]["boundaries"]["north"]["elements"], meshes[-1]["boundaries"]["notch_horizontal"]["elements"]
        a[0], b[0] = b[0], a[0]
        a.sort(key=lambda row: row["id"]); b.sort(key=lambda row: row["id"])
    elif kind == "nonrefining": meshes[-1] = deepcopy(meshes[-2]); settings["mesh"]["levels"][-1] = deepcopy(settings["mesh"]["levels"][-2])
    elif kind == "conflicting_D": settings["problem"]["boundaries"]["west"]["value"] += "+1"
    elif kind == "pure_N":
        for row in settings["problem"]["boundaries"].values(): row["type"] = "neumann"
    elif kind == "undefined_rhs": settings["problem"]["weak_form"]["rhs"] = "1/x[0]"
    else: settings["problem"]["boundaries"].pop("north")
    with pytest.raises(domain.PDEInputError): domain.validate_settings(settings, meshes)


@pytest.mark.parametrize("kind", ["geometry_map", "vertex_dof", "cell_row", "source_cell_tuple", "source_facet", "normal", "source_id", "rhs", "reference", "coefficient", "sync", "residual_normalization", "order"])
def test_complete_field_input_and_mapping_corruption_is_malformed_execution_data(kind):
    settings = small_settings()
    meshes, studies, fields, bindings, mappings = synthetic_imported(settings)
    if kind == "geometry_map": mappings[1]["geometry_source_node_ids"][0] = mappings[1]["geometry_source_node_ids"][1]
    elif kind == "vertex_dof": mappings[1]["vertex_dof_ids"] = list(reversed(mappings[1]["vertex_dof_ids"]))
    elif kind == "cell_row": mappings[1]["original_cell_index"] = list(reversed(mappings[1]["original_cell_index"]))
    elif kind == "source_cell_tuple": fields[1]["cell_node_ids"][0] = fields[1]["cell_node_ids"][1].copy()
    elif kind == "source_facet": fields[1]["boundaries"]["north"]["source_element_ids"].reverse()
    elif kind == "normal": fields[1]["boundaries"]["notch_horizontal"]["normal_integral"][1] *= -1
    elif kind == "source_id": fields[1]["source_node_ids"].reverse()
    elif kind == "rhs": bindings[1]["rhs_values"][0] += 1
    elif kind == "reference": bindings[1]["reference_values"][0] += 1
    elif kind == "coefficient": bindings[1]["diffusion"] *= 2
    elif kind == "sync": studies[1]["solution_synchronization"]["passed"] = False
    elif kind == "residual_normalization": studies[1]["linear_residual"]["rhs_norm"] = 1.
    else: studies[1]["l2_convergence_rate"] += .1
    with pytest.raises(domain.PDEInputError): domain.assess(settings, meshes, studies, fields, bindings, mappings)


def test_finite_numerical_failures_keep_invalid_values_and_zero_errors_do_not_prove_orders():
    settings = small_settings()
    meshes, studies, fields, bindings, mappings = synthetic_imported(settings)
    studies[1]["linear_residual"].update(absolute=.01, rhs_norm=1., relative=.01, normalization="rhs_l2_norm")
    studies[-1]["l2_error"] = .7
    refresh_rates(studies)
    result = domain.assess(settings, meshes, studies, fields, bindings, mappings)
    assert result["metrics"]["l2_error"]["value"] == .7 and result["metrics"]["linear_residual_relative"]["value"] == .01
    assert all(not row["valid"] and row["reason"] for row in result["metrics"].values())
    for study in studies: study["l2_error"] = 0.
    refresh_rates(studies)
    result = domain.assess(settings, meshes, studies, fields, bindings, mappings)
    assert result["metrics"]["l2_convergence_rate"]["value"] is None and not result["metrics"]["l2_convergence_rate"]["valid"]


def test_harmonic_zero_source_and_closed_neumann_inputs_are_independent_polynomials():
    for case, expected in (("mixed", {"east_lower": 5., "notch_horizontal": 4., "notch_vertical": 3., "north": 6.}),
                           ("harmonic", {"east_lower": 5., "notch_horizontal": 0., "notch_vertical": 3., "north": -2.})):
        settings = small_settings(case)
        meshes, studies, fields, bindings, mappings = synthetic_imported(settings)
        if case == "harmonic": assert settings["problem"]["weak_form"]["rhs"] == "0.0" and set(bindings[0]["rhs_values"]) == {0.}
        for name, integral in expected.items(): assert fields[0]["boundaries"][name]["prescribed_integral"] == pytest.approx(integral)
        assert studies[-1]["l2_error"]**2 == pytest.approx((1 if case == "harmonic" else 11)/30/8**4)
        assert studies[-1]["h1_seminorm_error"]**2 == pytest.approx(2/8**2)
        assert all(row["status"] == "PASS" for row in domain.assess(settings, meshes, studies, fields, bindings, mappings)["checks"])


def test_general_planar_named_groups_use_polygon_normals_and_preserve_geometry_on_refinement():
    settings = small_settings("all_dirichlet")
    for level in settings["mesh"]["levels"]:
        mesh = syntax.parse_msh(level["data"], level["sha256"])
        for row in mesh["nodes"]: row["coordinates"][0] += .25*row["coordinates"][1]
        level["data"] = syntax._format(mesh)
        level["sha256"] = hashlib.sha256(level["data"].encode("ascii")).hexdigest()
    meshes = syntax.prepare(settings)
    assert domain.validate_settings(settings, meshes) == settings
    for info in domain.mesh_series(meshes):
        assert info["area"] == pytest.approx(3.)
        assert info["groups"]["west"]["measure"] == pytest.approx(2*math.sqrt(1+.25**2))
        assert info["groups"]["west"]["normal_integral"] == pytest.approx([-2., .5])
        assert info["groups"]["notch_vertical"]["normal_integral"] == pytest.approx([1., -.25])


@pytest.mark.parametrize("kind", ["dense_ID", "geometry_source_ID", "mapping_cell_ID", "binding_DOF", "binding_source_ID", "physical_tag"])
def test_boolean_identity_aliases_are_malformed_not_integer_ids(kind):
    settings = small_settings()
    meshes, studies, fields, bindings, mappings = synthetic_imported(settings)
    if kind == "dense_ID": mappings[0]["dense_node_ids"][0] = True
    elif kind == "geometry_source_ID":
        index = mappings[0]["geometry_source_node_ids"].index(1)
        mappings[0]["geometry_source_node_ids"][index] = True
    elif kind == "mapping_cell_ID": mappings[0]["cell_ids"] = [False, *mappings[0]["cell_ids"][1:]]
    elif kind == "binding_DOF": bindings[0]["node_ids"] = [False, *bindings[0]["node_ids"][1:]]
    elif kind == "binding_source_ID":
        index = bindings[0]["source_node_ids"].index(1)
        bindings[0]["source_node_ids"] = bindings[0]["source_node_ids"].copy()
        bindings[0]["source_node_ids"][index] = True
    else: meshes[0]["cells"][0]["physical_tag"] = True
    with pytest.raises(domain.PDEInputError): domain.assess(settings, meshes, studies, fields, bindings, mappings)
