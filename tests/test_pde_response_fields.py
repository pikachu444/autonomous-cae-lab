"""TEST_ONLY unsolved field layouts; no native execution or qualification.

Synthetic source/field hashes exercise immutable joins. Core independently owns
byte containment/hash verification; these tests supply its parsed resource tuples.
"""

import builtins
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess

import pytest

from caelab.adapters import pde_response_fields as reader
from caelab.adapters.fenicsx_gmsh import parse_msh, dense_import


def sha(value):
    return hashlib.sha256(value if type(value) is bytes else
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def native_field(vector=False):
    def side(facet, nodes, measure, normal):
        return {"facet_ids": [facet], "facet_node_ids": [nodes], "dof_ids": sorted(nodes),
                "measure": measure, "normal_integral": normal,
                "prescribed_values": [[1., -2.], [3., -4.]] if vector else [1., 2.],
                "prescribed_integral": [4., -6.] if vector else 3.}
    field = {"schema_version": "1", "coordinates_unit": "1", "field_unit": "1",
             "node_ids": [0, 5, 9, 12], "coordinates": [[0., 0.], [2., 0.], [0., 1.], [2., 1.]],
             "values": [[1., -3.], [2., 4.], [-5., 6.], [7., -8.]] if vector else [1., -2., 3., -4.],
             "cell_node_ids": [[0, 5, 12], [0, 12, 9]], "dirichlet_node_ids": [0, 5, 9],
             "boundaries": {"xmin": side(0, [0, 9], 1., [-1., 0.]), "xmax": side(3, [5, 12], 1., [1., 0.]),
                            "ymin": side(6, [0, 5], 2., [0., -2.]), "ymax": side(8, [9, 12], 2., [0., 2.])}}
    if vector:
        field.update(field_type="vector", components=["u0", "u1"], block_size=2)
    return field


def coupled_field():
    field = native_field(True)
    old = field["boundaries"]
    def side(facet, nodes, normal):
        return {"facet_ids": [facet], "facet_node_ids": [nodes], "dof_ids": sorted(nodes), "measure": 1.,
                "normal_integral": normal, "prescribed_values": [[1., -2.], [3., -4.]], "prescribed_integral": [4., -6.]}
    field.update(node_ids=[0, 5, 9, 12, 20, 31],
                 coordinates=[[0., 0.], [2., 0.], [0., 1.], [2., 1.], [1., 0.], [1., 1.]],
                 values=[[1., -3.], [2., 4.], [-5., 6.], [7., -8.], [9., -10.], [-11., 12.]],
                 cell_ids=[0, 6, 15, 21], cell_node_ids=[[0, 20, 31], [0, 31, 9], [20, 5, 12], [20, 12, 31]],
                 cell_regions=["left", "left", "right", "right"], dirichlet_node_ids=[0, 5, 9, 20],
                 interface={"facet_ids": [40], "facet_node_ids": [[20, 31]], "node_ids": [20, 31],
                            "adjacent_cell_ids": [[0, 21]], "measure": 1., "plus_x_normal": [1., 0.]},
                 boundaries={"xmin": {"left": old["xmin"]}, "xmax": {"right": old["xmax"]},
                             "ymin": {"left": side(6, [0, 20], [0., -1.]), "right": side(7, [20, 5], [0., -1.])},
                             "ymax": {"left": side(8, [9, 31], [0., 1.]), "right": side(9, [31, 12], [0., 1.])}})
    return field


def original_mesh():
    # Sparse ORIGINAL IDs and permuted original rows, not native DOF indices.
    return ("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$PhysicalNames\n5\n2 1 \"body\"\n"
            "1 2 \"xmin\"\n1 3 \"xmax\"\n1 4 \"ymin\"\n1 5 \"ymax\"\n$EndPhysicalNames\n"
            "$Nodes\n4\n505 2 1 0\n101 0 0 0\n201 0 1 0\n107 2 0 0\n$EndNodes\n"
            "$Elements\n6\n901 2 2 1 1 101 505 201\n601 2 2 1 1 101 107 505\n"
            "1001 1 2 2 2 101 201\n1002 1 2 3 3 107 505\n1003 1 2 4 4 101 107\n"
            "1004 1 2 5 5 201 505\n$EndElements\n")


def fixture(kind="rectangle", selected=False, rejected=False):
    backend = "pde.fenicsx." + kind
    vector, coupled, imported, transient = kind in ("vector", "coupled"), kind == "coupled", kind == "imported", kind == "transient"
    domain = {"type": "imported_mesh", "body": "body"} if imported else {"type": "rectangle", "lengths": [2., 1.]}
    weak = ({"diffusion": {"left": [[2., .5], [.5, 1.]], "right": [[4., -.5], [-.5, 2.]]}, "reaction": [[0., 0.], [0., 0.]]}
            if coupled else {"diffusion": 1., "reaction": 0., "rhs": "0"})
    boundaries = {side: {"type": "dirichlet" if side in ("xmin", "ymin") else "neumann",
                  "value": {region: ["1", "2"] for region in (["left"] if side == "xmin" else ["right"] if side == "xmax" else ["left", "right"])}
                  if coupled else ["1", "2"] if vector else "1"} for side in ("xmin", "xmax", "ymin", "ymax")}
    data = original_mesh()
    data_sha = sha(data.encode())
    settings = {"problem": {"domain": domain, "weak_form": weak, "boundaries": boundaries,
                           "reference": None if selected else {"source": "TEST_ONLY UNSOLVED", "solution": ["1", "2"] if vector else "1"}},
                "mesh": {"degree": 1, "levels": [{"format": "gmsh_msh2_ascii", "source": "UNSOLVED.msh", "data": data, "sha256": data_sha}]}
                if imported else {"degree": 1, "cell_counts": [2 if coupled else 1]},
                "validation": {"max_residual_relative": 1e-10}}
    if selected:
        settings["mode"] = "selected_mesh"
    if transient:
        settings.update(refinement_axis="time", time={"start": 0., "end": 1., "step_counts": [2], "unit": "1", "scheme": "backward_euler"})
    raw = {}
    source = {"schema_version": "1", "domain_plugin_version": "1", "files": {}}
    for key, (repo, copied) in reader._sources(kind).items():
        raw["pde/" + copied] = ("TEST_ONLY UNSOLVED source " + repo).encode()
        source["files"][key] = {"repository_path": repo, "copied_path": copied, "sha256": sha(raw["pde/" + copied])}
    versions = {key: "UNSOLVED" for key in reader._VERSIONS | ({"gmsh"} if imported else set())}
    worker = {"schema_version": "1", "status": "COMPLETED", "mpi_size": 1, "scalar_type": "float64", "versions": versions}
    if selected:
        worker.update(mode="selected_mesh", scope="SELECTED_DIMENSIONLESS_SCALAR_RECTANGLE")
    rows, fields, bindings, mappings = [], [], [], []
    for j in range(3 if transient else 1):
        field = coupled_field() if coupled else native_field(vector)
        prefix = f"study_0_n1_N2/step_{j}" if transient else "level_0" if imported else "level_n2" if coupled else "level_n1"
        files = {name: prefix + "/" + filename for name, filename in
                 {"field": "field.xdmf", "field_data": "field.h5", "form_source": "forms.ufl.txt", "dofs": "dofs.json"}.items()}
        binding, mapping = None, None
        if transient:
            field["values"] = [1. + j, -0.0, 1e-5 * (j + 1), 4.5 + j]
            files["time_binding"] = prefix + "/time_binding.json"
            binding = {"schema_version": "1", "time": j / 2, "node_ids": field["node_ids"], "rhs_values": [0.] * 4, "reference_values": field["values"]}
        elif coupled:
            files["binding"] = prefix + "/binding.json"
            binding = {"schema_version": "1", "components": ["u0", "u1"], "regions": {}}
            for region in ("left", "right"):
                cells = [id_ for id_, name in zip(field["cell_ids"], field["cell_regions"]) if name == region]
                nodes = [0, 9, 20, 31] if region == "left" else [5, 12, 20, 31]
                binding["regions"][region] = {"cell_ids": cells, "node_ids": nodes, "diffusion": weak["diffusion"][region], "reaction": weak["reaction"],
                                             "rhs_values": [[3., -4.] for _ in nodes], "reference_values": [[1., -2.] for _ in nodes]}
        elif vector:
            files["binding"] = prefix + "/binding.json"
            binding = {"schema_version": "1", "node_ids": field["node_ids"], "components": ["u0", "u1"],
                       "rhs_values": field["values"], "reference_values": field["values"]}
        elif imported:
            files.update({key: prefix + "/" + filename for key, filename in
                          {"binding": "binding.json", "mapping": "import_mapping.json", "original": "original.msh", "dense": "dense-import.msh"}.items()})
            dense, table = dense_import(parse_msh(data, data_sha))
            raw["pde/" + files["original"]] = data.encode()
            raw["pde/" + files["dense"]] = dense.encode()
            field.update(cell_ids=[0, 11], source_node_ids=[101, 107, 201, 505], source_cell_ids=[601, 901])
            for i, side in enumerate(field["boundaries"].values()):
                side["source_element_ids"] = [1001 + i]
            mapping = {"schema_version": "1", **table, "geometry_input_indices": [2, 0, 3, 1], "geometry_source_node_ids": [201, 101, 505, 107],
                       "vertex_ids": [0, 3, 7, 9], "vertex_geometry_indices": [1, 3, 0, 2], "vertex_dof_ids": [0, 5, 9, 12],
                       "cell_ids": [0, 11], "original_cell_index": [1, 0], "importer_cell_source_ids": [901, 601], "source_cell_ids": [601, 901],
                       "physical_groups": {"body": {"dim": 2, "tag": 1}, **{side: {"dim": 1, "tag": i + 2} for i, side in enumerate(boundaries)}},
                       "boundary_source_elements": {side: b["source_element_ids"] for side, b in field["boundaries"].items()},
                       "gmsh_initialization": {"argv": [], "read_config_files": False, "finalized": True}}
            binding = {"schema_version": "1", "node_ids": field["node_ids"], "source_node_ids": field["source_node_ids"],
                       "source_sha256": data_sha, "dense_sha256": table["dense_sha256"], "diffusion": 1., "reaction": 0.,
                       "rhs_values": [0.] * 4, "reference_values": field["values"]}
        for name in ("field", "field_data", "form_source"):
            raw["pde/" + files[name]] = ("TEST_ONLY UNSOLVED " + name).encode()
        raw["pde/" + files["dofs"]] = field
        if binding is not None:
            raw["pde/" + files.get("binding", files.get("time_binding"))] = binding
        if mapping is not None:
            raw["pde/" + files["mapping"]] = mapping
        count = len(field["node_ids"])
        constrained = len(field["dirichlet_node_ids"])
        row = {"degree": 1, "cell_type": "triangle", "global_cells": len(field["cell_node_ids"]), "global_dofs": count * (2 if vector else 1),
               "dirichlet_dofs": constrained * (2 if vector else 1), "files": files, "artifact_sha256": {}}
        if not imported:
            row["cells_per_axis"] = 2 if coupled else 1
        if vector or imported:
            row.update(global_nodes=count, dirichlet_nodes=constrained)
        if vector:
            row["block_size"] = 2
        if coupled:
            row.update(region_cell_counts={"left": 2, "right": 2}, region_coefficients=weak["diffusion"], reaction_matrix=weak["reaction"])
        if imported:
            row.update(level=0, source_sha256=data_sha, dense_sha256=mapping["dense_sha256"], physical_groups=mapping["physical_groups"],
                       coefficients={"diffusion": 1., "reaction": 0.})
        if transient:
            row.update(index=j, time=j / 2, native_time_value=j / 2, dt=.5 if j else 0., solver_status="COMPLETED" if j else "NOT_RUN",
                       previous_values_sha256=rows[-1]["current_values_sha256"] if j else None, current_values_sha256=reader._value_hash(field),
                       distinct_state=True, linear_residual={"absolute": 1e-12, "rhs_norm": 1., "relative": 1e-12, "normalization": "rhs_l2_norm"} if j else None,
                       ksp_convergence_reason=1 if j else None, ksp_iterations=1 if j else None)
        rows.append(row)
        fields.append(field)
        bindings.append(binding)
        mappings.append(mapping)
    if transient:
        worker["studies"] = [{"study_index": 0, "cells_per_axis": 1, "step_count": 2, "dt": .5, "refinement_axis": "time", "steps": rows}]
    else:
        worker["mesh_studies"] = rows
    raw.update({"pde/input.json": settings, "pde/source_manifest.json": source, "pde/worker_result.json": worker})
    revision, model = "a" * 64, "b" * 64
    proposal = {"id": "E-UNSOLVED", "study_id": "S-UNSOLVED", "model_revision": model, "cad_revision": None,
                "physics": {"backend": backend}, "execution": settings}
    detail = {"adapter": backend, "adapter_version": "1", "domain_plugin_version": "1", "units": "dimensionless",
              "source_manifest": "pde/source_manifest.json", "source_sha256": {key: row["sha256"] for key, row in source["files"].items()},
              "mpi_size": 1, "scalar_type": "float64", "versions": versions}
    if selected:
        detail.update(mode="selected_mesh", scope="SELECTED_DIMENSIONLESS_SCALAR_RECTANGLE")
    result = {"experiment_id": proposal["id"], "study": {"id": proposal["study_id"]}, "model_revision": model, "cad_revision": None,
              "proposal_revision": revision, "status": "REJECTED" if rejected else "COMPLETED_REVIEW_REQUIRED", "solver_status": "COMPLETED",
              "converged": True, "decision": "NOT_RELEASED", "artifacts": [],
              "metrics": {"l2_error": {"value": None if selected else .25, "unit": "1", "valid": not (selected or rejected),
                                       "reason": "Reference not provided" if selected else "Retained coarse-pair rejection" if rejected else "TEST_ONLY UNSOLVED"}},
              "validations": [{"type": "physical_validation", "status": "UNKNOWN"}],
              "provenance": {"adapter": backend, "adapter_version": "1", "proposal_sha256": revision, "execution_settings": settings, "adapter_details": detail}}

    def seal():
        for row in rows:
            row["artifact_sha256"] = {key: sha(raw["pde/" + path]) for key, path in row["files"].items()}
        worker["spec_sha256"] = detail["spec_sha256"] = sha(settings)
        worker["source_manifest_sha256"] = detail["source_manifest_sha256"] = sha(source)
        result["artifacts"] = [{"path": path, "sha256": sha(value), "size_bytes": len(value) if type(value) is bytes else
                                len(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()),
                                "revision": revision, "mime_type": "application/octet-stream"} for path, value in raw.items()]

    def resources(policy):
        manifest = {entry["path"]: entry for entry in result["artifacts"]}
        return {role: (raw[spec["path"]], manifest[spec["path"]]) for role, spec in policy.items()}

    adapter = reader.PDEResponseFieldsAdapter(backend)
    def headers():
        return resources(adapter.field_response_resources(result))
    def selection(step=1 if transient else None, node=0, component="u0" if vector else "u"):
        index = step if transient else 0
        path = "pde/" + rows[index]["files"]["dofs"]
        manifest = {entry["path"]: entry for entry in result["artifacts"]}
        return {"kind": "pde_nodal", "artifact": path, "sha256": manifest[path]["sha256"], "model_revision": model,
                "study_index": 0, "step_index": step, "node_id": node, "component": component}
    def select(sel=None):
        sel = selection() if sel is None else sel
        h = headers()
        policy = adapter.field_selection_resources(result, sel, h)
        return adapter.select_response_fields(result, proposal, {**h, **resources(policy)}, sel)
    seal()
    return {"kind": kind, "result": result, "proposal": proposal, "settings": settings, "detail": detail, "source": source,
            "worker": worker, "rows": rows, "fields": fields, "bindings": bindings, "mappings": mappings, "raw": raw,
            "adapter": adapter, "seal": seal, "headers": headers, "resources": resources, "selection": selection, "select": select}


@pytest.mark.parametrize("kind", ["rectangle", "transient", "vector", "coupled", "imported"])
def test_same_contract_catalog_and_original_signed_selection(kind):
    f = fixture(kind, rejected=True)
    before = deepcopy((f["result"], f["proposal"], f["raw"]))
    catalog = f["adapter"].display_response_fields(f["result"], f["proposal"], f["headers"]())
    assert catalog["kind"] == "pde" and catalog["model_revision"] == f["result"]["model_revision"]
    assert "nodes" not in catalog and "values" not in catalog
    assert catalog["recorded_status"] == "REJECTED"
    sel = f["selection"](node=0, component="u1" if kind in ("vector", "coupled") else "u")
    value = f["select"](sel)
    assert value["value"] == (-3. if kind in ("vector", "coupled") else 2. if kind == "transient" else 1.)
    assert value["source_field"]["node_id"] == 0 and value["source_field"]["coordinates"] == [0., 0.]
    assert value["source_field"]["coordinate_frame"] == "PDE_MODEL_CARTESIAN"
    assert value["qualification"]["physical"] == "UNKNOWN" and value["qualification"]["decision"] == "NOT_RELEASED"
    assert value["alignment"] == "USER_DECLARED_UNVERIFIED"
    assert (f["result"], f["proposal"], f["raw"]) == before
    if kind == "imported":
        assert value["source_field"]["source_node_id"] == 101
    if kind != "transient":
        assert "response_axis" not in value


def test_selected_no_reference_is_not_promoted_to_benchmark_or_valid_metric():
    f = fixture(selected=True)
    original = deepcopy(f["result"]["metrics"])
    assert f["select"](f["selection"](node=12))["value"] == -4.
    assert f["result"]["metrics"] == original
    assert original["l2_error"]["value"] is None and original["l2_error"]["valid"] is False


def test_initial_native_state_and_exact_axis_negative_zero_are_preserved():
    f = fixture("transient")
    initial = f["select"](f["selection"](step=0, node=5))
    assert math.copysign(1., initial["value"]) == -1.
    assert initial["response_axis"] == {"quantity": "time", "unit": "1", "value": 0.}
    assert initial["source_field"]["solver_status"] == "NOT_RUN"
    assert initial["source_field"]["initial_state"]["kind"] == "UNINTEGRATED_INITIAL_CONDITION"
    final = f["select"](f["selection"](step=2))
    assert final["response_axis"]["value"] == 1.
    assert "initial_state" not in final["source_field"]
    assert final["source_field"]["axis_semantics"] == "DIMENSIONLESS_MODEL_TIME"


def test_policy_reads_three_headers_then_only_exact_selected_and_previous_data():
    for kind in ("rectangle", "transient", "vector", "coupled", "imported"):
        f = fixture(kind)
        base = f["adapter"].field_response_resources(f["result"])
        additional = f["adapter"].field_selection_resources(f["result"], f["selection"](), f["headers"]())
        assert set(base) == {"input", "source", "worker"}
        assert not set(base) & set(additional) and len(base) + len(additional) <= 8
        assert all(spec["maximum_bytes"] == 32 * 1024 * 1024 for spec in additional.values())
        if kind == "transient":
            assert set(additional) == {"dofs", "time_binding", "previous_dofs", "previous_time_binding"}


@pytest.mark.parametrize("key,value", [("kind", "structural"), ("artifact", "pde/other/dofs.json"), ("sha256", "c" * 64),
    ("model_revision", "d" * 64), ("study_index", 1), ("study_index", True), ("step_index", 0),
    ("node_id", True), ("node_id", -1), ("component", "MAGNITUDE"), ("component", "u1")])
def test_exact_selector_metadata_refuses_foreign_or_unadvertised_identity(key, value):
    f = fixture()
    sel = f["selection"]()
    sel[key] = value
    with pytest.raises(ValueError):
        f["select"](sel)


def test_absent_node_extra_selector_and_resource_roles_refuse():
    f = fixture()
    with pytest.raises(ValueError, match="absent"):
        f["select"](f["selection"](node=8))
    sel = f["selection"]()
    sel["value"] = 100.
    with pytest.raises(ValueError):
        f["select"](sel)
    sel = f["selection"]()
    resources = f["headers"]()
    policy = f["adapter"].field_selection_resources(f["result"], sel, resources)
    resources.update(f["resources"](policy))
    resources["unselected"] = resources["dofs"]
    with pytest.raises(ValueError):
        f["adapter"].select_response_fields(f["result"], f["proposal"], resources, sel)


@pytest.mark.parametrize("mutation", [
    lambda f: f["fields"][0].update(coordinates_unit="mm"),
    lambda f: f["fields"][0].update(field_unit="Pa"),
    lambda f: f["fields"][0].update(coordinate_frame="WORLD"),
    lambda f: f["fields"][0].update(schema_version="2"),
    lambda f: f["fields"][0]["node_ids"].__setitem__(1, 0),
    lambda f: f["fields"][0]["node_ids"].__setitem__(1, True),
    lambda f: f["fields"][0]["values"].__setitem__(1, True),
    lambda f: f["fields"][0]["coordinates"][0].__setitem__(0, True),
    lambda f: f["fields"][0]["cell_node_ids"][0].__setitem__(1, 99),
    lambda f: f["fields"][0]["cell_node_ids"].__setitem__(1, [0, 5, 12]),
    lambda f: f["fields"][0]["boundaries"]["xmin"]["dof_ids"].__setitem__(1, 12),
    lambda f: f["fields"][0]["dirichlet_node_ids"].pop(),
    lambda f: f["rows"][0].update(cells_per_axis=2),
    lambda f: f["rows"][0].update(global_dofs=True),
])
def test_rehashed_malformed_field_and_mesh_level_still_refuse(mutation):
    f = fixture()
    mutation(f)
    f["seal"]()
    with pytest.raises(ValueError):
        f["select"]()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_native_parsed_values_refuse_without_coercion(value):
    f = fixture()
    # Core rejects these bytes too; adapter independently rejects supplied raw data.
    f["fields"][0]["values"][0] = value
    with pytest.raises(ValueError):
        f["select"]()


@pytest.mark.parametrize("mutation", [
    lambda f: f["worker"].update(spec_sha256="e" * 64),
    lambda f: f["worker"].update(source_manifest_sha256="e" * 64),
    lambda f: f["worker"].update(mpi_size=True),
    lambda f: f["worker"].update(scalar_type="float32"),
    lambda f: f["worker"]["versions"].update(dolfinx=""),
    lambda f: f["source"]["files"]["worker"].update(copied_path="../worker.py"),
    lambda f: f["detail"]["source_sha256"].update(worker="e" * 64),
    lambda f: f["source"]["files"].pop("domain_reference"),
])
def test_native_source_spec_versions_and_membership_mismatch_refuse(mutation):
    f = fixture()
    mutation(f)
    with pytest.raises(ValueError):
        f["select"]()


@pytest.mark.parametrize("kind", ["vector", "coupled"])
def test_directed_component_order_or_binding_nodes_are_not_guessed(kind):
    f = fixture(kind)
    f["fields"][0]["components"] = ["u1", "u0"]
    f["seal"]()
    with pytest.raises(ValueError):
        f["select"]()
    f = fixture(kind)
    if kind == "vector":
        f["bindings"][0]["node_ids"] = [5, 0, 9, 12]
    else:
        f["bindings"][0]["regions"]["left"]["node_ids"] = [0, 5, 9, 20]
    f["seal"]()
    with pytest.raises(ValueError):
        f["select"]()


@pytest.mark.parametrize("mutation", [
    lambda f: f["rows"][1].update(time=True),
    lambda f: f["rows"][1].update(native_time_value=.75),
    lambda f: f["rows"][1].update(previous_values_sha256="e" * 64),
    lambda f: f["bindings"][1].update(time=.75),
    lambda f: f["bindings"][0].update(time=.1),
    lambda f: f["fields"][1]["values"].__setitem__(0, 91.),
    lambda f: f["fields"][0]["coordinates"][0].__setitem__(0, .01),
    lambda f: f["rows"][0].update(solver_status="COMPLETED"),
])
def test_transient_actual_axis_initial_and_previous_current_binding_refusal(mutation):
    f = fixture("transient")
    mutation(f)
    f["seal"]()
    with pytest.raises(ValueError):
        f["select"]()


@pytest.mark.parametrize("mutation", [
    lambda f: f["mappings"][0]["geometry_source_node_ids"].__setitem__(0, 505),
    lambda f: f["mappings"][0]["vertex_dof_ids"].__setitem__(0, 5),
    lambda f: f["mappings"][0]["original_cell_index"].__setitem__(0, 0),
    lambda f: f["mappings"][0]["physical_groups"]["body"].update(tag=7),
    lambda f: f["mappings"][0].update(dense_sha256="e" * 64),
    lambda f: f["fields"][0]["source_node_ids"].__setitem__(0, 505),
    lambda f: f["fields"][0]["coordinates"][0].__setitem__(0, .01),
    lambda f: f["fields"][0]["source_cell_ids"].reverse(),
    lambda f: f["fields"][0]["boundaries"]["xmin"]["source_element_ids"].__setitem__(0, 1002),
])
def test_original_msh_geometry_physical_names_and_native_bijections_are_exact(mutation):
    f = fixture("imported")
    mutation(f)
    f["seal"]()
    with pytest.raises(ValueError):
        f["select"]()


def test_same_length_rehashed_original_msh_is_not_accepted_as_old_geometry():
    f = fixture("imported")
    f["settings"]["mesh"]["levels"][0]["data"] = original_mesh().replace("101 0 0 0", "101 1 0 0")
    f["seal"]()
    with pytest.raises(ValueError):
        f["select"]()


@pytest.mark.parametrize("mutation", [
    lambda f: f["fields"][0]["interface"].update(adjacent_cell_ids=[[0, 15]]),
    lambda f: f["fields"][0]["interface"].update(plus_x_normal=[-1., 0.]),
    lambda f: f["rows"][0].update(region_cell_counts={"left": 1, "right": 3}),
    lambda f: f["bindings"][0]["regions"]["left"]["diffusion"][0].__setitem__(0, 5.),
])
def test_coupled_interface_and_region_input_binding_refuse(mutation):
    f = fixture("coupled")
    # Detach fixture values before mutation to test mismatch, not aliased inputs.
    f["bindings"][0]["regions"]["left"]["diffusion"] = deepcopy(f["bindings"][0]["regions"]["left"]["diffusion"])
    mutation(f)
    f["seal"]()
    with pytest.raises(ValueError):
        f["select"]()


def test_manifest_copy_revision_alias_and_json_bound_refuse():
    f = fixture()
    f["result"]["artifacts"].append(deepcopy(f["result"]["artifacts"][0]))
    with pytest.raises(ValueError):
        f["select"]()
    f = fixture()
    entry = next(e for e in f["result"]["artifacts"] if e["path"] == "pde/input.json")
    entry["revision"] = "e" * 64
    with pytest.raises(ValueError):
        f["select"]()
    f = fixture()
    entry = next(e for e in f["result"]["artifacts"] if e["path"] == "pde/input.json")
    entry["size_bytes"] = reader.JSON_LIMIT + 1
    with pytest.raises(ValueError):
        f["headers"]()
    f = fixture()
    h = f["headers"]()
    raw, entry = h["input"]
    h["input"] = (raw, {**entry, "sha256": "e" * 64})
    with pytest.raises(ValueError):
        f["adapter"].display_response_fields(f["result"], f["proposal"], h)


@pytest.mark.parametrize("status,solver", [("FAILED_EXECUTION", "FAILED"), ("CANCELLED", "CANCELLED"), ("REJECTED", "NOT_RUN")])
def test_native_failure_or_preflight_rejection_is_not_a_numerical_field(status, solver):
    f = fixture()
    f["result"].update(status=status, solver_status=solver)
    with pytest.raises(ValueError):
        f["select"]()


def test_unsupported_family_and_boolean_cross_record_identity_refuse():
    for backend in ("pde.fenicsx", "pde.fenicsx.nonlinear", "structure.calculix.native"):
        with pytest.raises(ValueError):
            reader.PDEResponseFieldsAdapter(backend)
    f = fixture()
    f["proposal"] = deepcopy(f["proposal"])
    f["proposal"]["execution"]["mesh"]["degree"] = True
    h = f["headers"]()
    with pytest.raises(ValueError):
        f["adapter"].display_response_fields(f["result"], f["proposal"], h)


def test_pure_reader_does_not_open_files_or_start_processes(monkeypatch):
    f = fixture("imported")
    def forbidden(*args, **kwargs):
        raise AssertionError("Pure selector attempted native/file I/O")
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert f["select"]()["source_field"]["source_node_id"] == 101
