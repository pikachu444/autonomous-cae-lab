"""Portable contract tests with an UNSOLVED, TEST_ONLY ten-node tetrahedron.

These fixtures do not establish native execution, an admissible restraint rank,
material qualification or a physical observation. Core must separately bind
the supplied JSON to immutable artifact bytes; this adapter tests parsed data.
"""

import builtins
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import pytest

from caelab.adapters.structural_response_fields import select_field_response


_REVISION = "a" * 64
_CATALOG_REVISION = "e" * 64
_IDS = [7, 11, 21, 43, 54, 67, 81, 102, 145, 209]
_XYZ = [[0., 0., 0.], [2., 0., 0.], [0., 2., 0.], [0., 0., 2.],
        [1., 0., 0.], [1., 1., 0.], [0., 1., 0.], [0., 0., 1.],
        [1., 0., 1.], [0., 1., 1.]]
_FACES = [[7, 11, 21, 54, 67, 81], [7, 43, 11, 102, 145, 54],
          [11, 43, 21, 145, 209, 67], [21, 43, 7, 209, 102, 81]]


def _pin(path):
    payload = ("UNSOLVED_TEST_ONLY_SOURCE:" + path).encode("ascii")
    return {"path": path, "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload), "revision": _REVISION, "mime_type": "text/plain"}


def _field_entry(path, raw):
    payload = json.dumps(raw, sort_keys=True, allow_nan=False).encode("ascii")
    return {"path": path, "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload), "revision": _REVISION, "mime_type": "application/json"}


def _case(native=False, *, selected=True, index=0):
    """Build a complete parsed contract, never read a retained run or solve it."""
    backend = "structure.calculix.native" if native else "fixture.calculix"
    version = "1" if native else "6" if selected else "5"
    prefix = "simulation/" if native else f"simulation/support_{index}/"
    filenames = ({"mesh": "mesh.json", "deck": "native.inp", "boundary": "boundary.json",
                  "frd": "native.frd", "dat": "native.dat"} if native else
                 {"mesh": "gmsh.inp", "deck": f"support_{index}.inp", "saddle": "saddle_load.json",
                  "frd": f"support_{index}.frd", "dat": f"support_{index}.dat"})
    sources = [_pin(prefix + name) for name in filenames.values()]
    source_map = {name: {"path": filename, "sha256": row["sha256"], "bytes": row["size_bytes"]}
                  for (name, filename), row in zip(filenames.items(), sources)}
    values = {43: [-.01, .02, -.03], 102: [.002, .003, -.004],
              145: [.001, -.002, -.05], 209: [.001, .01, -.09]}
    nodes = [{"node_id": node, "position_mm": deepcopy(xyz),
              "displacement_mm": deepcopy(values.get(node, [0., 0., 0.])),
              "displacement_tokens": [format(v, ".6E" if native else ".5E")
                                      for v in values.get(node, [0., 0., 0.])]}
             for node, xyz in zip(_IDS, _XYZ)]
    face_ids = [f"F-{_CATALOG_REVISION}-Face{i}" for i in range(1, 5)]
    boundary = [{"element_id": number, "type": "CPS6", "node_ids": deepcopy(ids),
                 ("selection_id" if native else "group"):
                 face_ids[i] if native else ["BOTTOM", "SADDLE_SIDE", "WALL_A", "WALL_B"][i]}
                for i, (number, ids) in enumerate(zip((2, 3, 5, 17), _FACES))]
    raw = {"schema_version": "1.0", "kind": ("native_structural_nodal_displacement" if native else
                                              "fixture_calculix_nodal_displacement"),
           "backend": backend, "adapter_version": version, "parent_experiment_id": "E_CAD",
           "cad_revision": _REVISION, "mesh_size_max_mm": 4. if selected else [4., 3.][index],
           "coordinate_frame": "CAD_DOCUMENT_GLOBAL" if native else "SOLVER_GLOBAL_CARTESIAN",
           "position_unit": "mm", "displacement_unit": "mm", "force_unit": "N",
           "static": {"step": 1, "increment": 1, "load_parameter": 1.},
           "coverage": "ALL_MESH_NODES", "qualification": "UNKNOWN", "engineering_valid": False,
           "nodes": nodes, "elements": [{"element_id": 31, "type": "C3D10", "node_ids": list(_IDS)}],
           "boundary_faces": boundary, "node_count": len(nodes), "element_count": 1,
           "boundary_face_count": 4, "sources": source_map}
    if native:
        declaration = {"analysis_type": "linear_static", "units": {"length": "mm", "force": "N", "stress": "MPa"},
                       "coordinate_system": "global", "mesh": {"mode": "selected", "max_size_mm": 4.},
                       "materials": [{"id": "M1", "selection_id": "B-final", "law": "isotropic_linear_elastic",
                                      "young_modulus_MPa": 210000., "poisson_ratio": .3,
                                      "source": {"category": "ASSUMED", "description": "UNSOLVED TEST_ONLY"}}],
                       "boundary_conditions": [{"id": "BC1", "selection_id": face_ids[0], "type": "displacement",
                                                "components": {"UX": 0.}, "unit": "mm", "coordinate_system": "global",
                                                "source": "UNSOLVED TEST_ONLY partial DOF"}],
                       "loads": [{"id": "L1", "selection_id": face_ids[1], "type": "resultant_force",
                                  "components": {"FX": 0., "FY": 0., "FZ": 4.}, "unit": "N",
                                  "coordinate_system": "global", "source": "UNSOLVED TEST_ONLY signed force"}],
                       "contact": {"mode": "none", "source": "UNSOLVED TEST_ONLY no-contact"}}
        execution = {"analysis_type": "linear_static", "declaration": declaration,
                     "mesh": deepcopy(declaration["mesh"]),
                     "native_catalog": {"native_catalog_revision": _CATALOG_REVISION,
                                        "selections": [{"id": face, "kind": "native_face"} for face in face_ids]}}
        loads = [{"node_id": node, "component": 3, "force_N": force, "integration_force_N": force, "force_token": f"{force:.12e}"}
                 for node, force in ((43, -1.), (102, 2.), (145, 3.))]
        regions = [{"id": "L1", "selection_id": face_ids[1], "resultant_N": [0., 0., 4.],
                    "native_area_mm2": 2., "mesh_area_mm2": 2.,
                    "distribution": "consistent_quadratic_surface_shape_function_integration"}]
        raw.update({"native_catalog_revision": _CATALOG_REVISION, "parent_step_sha256": "f" * 64,
                    "deck_sha256": source_map["deck"]["sha256"], "peak_node_id": 209,
                    "prescribed_dofs": [{"node_id": node, "component": 1, "value_mm": 0.,
                                         "declared_value_mm": 0., "value_token": "0.000000000000e+00"}
                                        for node in sorted(_FACES[0])],
                    "loads": loads, "load_regions": regions})
        path = prefix + "field.json"
        details = {"parent_step_sha256": raw["parent_step_sha256"], "field_artifact": path,
                   "boundary": {"load_regions": deepcopy(regions)}}
        maximum = math.hypot(*values[209])
    else:
        mesh = {"max_sizes_mm": [4.]} if selected else {"max_sizes_mm": [4., 3.]}
        if selected:
            mesh["mode"] = "selected"
        execution = {"mesh": mesh, "load": {"force_N": 6., "source": "UNSOLVED TEST_ONLY"}}
        raw.update({"mesh_index": index, "fixed_node_ids": sorted(_FACES[0]), "fixed_dofs": [1, 2, 3],
                    "loads": [{"node_id": node, "dof": 3, "force_N": [0., 0., -force], "force_token": f"{-force:g}"}
                              for node, force in ((43, 1.), (102, 2.), (145, 3.))]})
        path = prefix + "fea_field.json"
        studies = [{"index": i, "mesh_size_max_mm": size, "loaded_node_count": 3,
                    "displacement_table": f"simulation/support_{i}/support_{i}.dat",
                    "displacement_table_sha256": _pin(f"simulation/support_{i}/support_{i}.dat")["sha256"]}
                   for i, size in enumerate(mesh["max_sizes_mm"])]
        details = {"adapter": backend, "adapter_version": version, "parent_experiment_id": "E_CAD",
                   "cad_revision": _REVISION, "mesh_max_sizes_mm": deepcopy(mesh["max_sizes_mm"]),
                   "force_per_support_N": 6., "per_mesh_displacement": {"studies": studies}}
        if selected:
            details.update({"mesh_policy": {"mode": "selected"}, "mesh_sensitivity": {"status": "NOT_ASSESSED"}})
        # Existing fixture metric is loaded-saddle |UZ|, not the whole-field norm.
        maximum = .05
    artifact = _field_entry(path, raw)
    proposal = {"id": "E_TEST", "parent_experiment_id": "E_CAD", "study_id": "S_TEST",
                "physics": {"backend": backend}, "model": {"geometry": {
                    "source_experiment_id": "E_CAD", "cad_revision": _REVISION}}, "execution": execution}
    if native:
        proposal.update({"boundary_conditions": deepcopy(declaration["boundary_conditions"]),
                         "loads": deepcopy(declaration["loads"])})
        proposal["model"]["materials"] = deepcopy(declaration["materials"])
    result = {"experiment_id": "E_TEST", "parent_experiment_id": "E_CAD", "cad_revision": _REVISION,
              "study": {"id": "S_TEST"}, "status": "COMPLETED_REVIEW_REQUIRED", "solver_status": "COMPLETED",
              "converged": True, "decision": "NOT_RELEASED", "artifacts": sources + [deepcopy(artifact)],
              "metrics": {"max_displacement": {"value": maximum, "unit": "mm", "valid": True},
                          "displacement_mesh_change_ratio": {"value": None, "valid": False}},
              "provenance": {"adapter": backend, "adapter_version": version, "parent_experiment_id": "E_CAD",
                             "execution_settings": deepcopy(execution), "adapter_details": details}}
    selection = {"artifact": path, "sha256": artifact["sha256"], "cad_revision": _REVISION,
                 "node_id": 43, "component": "UX"}
    return {"result": result, "proposal": proposal, "raw": raw, "artifact": artifact, "selection": selection}


def _sync_native_proposal(case):
    declaration = case["proposal"]["execution"]["declaration"]
    case["proposal"]["model"]["materials"] = deepcopy(declaration["materials"])
    case["proposal"]["loads"] = deepcopy(declaration["loads"])
    case["proposal"]["boundary_conditions"] = deepcopy(declaration["boundary_conditions"])
    case["result"]["provenance"]["execution_settings"] = deepcopy(case["proposal"]["execution"])


def test_native_integrated_force_and_serialized_deck_token_are_distinct_retained_values():
    # Existing producer saves both the integration value and its 13-digit deck
    # token; accepting only a four-key synthetic load misses actual native data.
    case = _case(True)
    case['raw']['loads'][0]['integration_force_N'] = -1.00000000000002
    selected = select_field_response(**case)
    assert selected['value'] == -.01 and selected['qualification'] == 'UNKNOWN'
    case['raw']['loads'][0]['integration_force_N'] = -1.1
    with pytest.raises(ValueError, match='load DOF/source token differs'):
        select_field_response(**case)


def test_native_missing_or_zero_original_integration_load_is_not_a_producer_contract():
    case = _case(True)
    del case['raw']['loads'][0]['integration_force_N']
    with pytest.raises(ValueError, match='load DOF/source token differs'):
        select_field_response(**case)
    case = _case(True)
    case['raw']['loads'][0].update(integration_force_N=0., force_N=0., force_token='0.000000000000e+00')
    with pytest.raises(ValueError, match='load DOF/source token differs'):
        select_field_response(**case)


@pytest.mark.parametrize("native", [False, True], ids=["fixture", "native"])
@pytest.mark.parametrize("component,expected", [("UX", -.01), ("UY", .02), ("UZ", -.03),
                                               ("MAGNITUDE", math.hypot(-.01, .02, -.03))])
def test_signed_components_and_explicit_norm_keep_exact_original_scope(native, component, expected):
    case = _case(native)
    case["selection"]["component"] = component
    before = deepcopy(case)
    selected = select_field_response(**case)
    assert selected == {"value": expected, "unit": "mm", "qualification": "UNKNOWN",
                        "alignment": "USER_DECLARED_UNVERIFIED", "source_field": {
                            **case["selection"], "quantity": "DISPLACEMENT", "position_mm": [0., 0., 2.],
                            "position_unit": "mm", "coordinate_frame": case["raw"]["coordinate_frame"],
                            "value_origin": "DERIVED_MAGNITUDE" if component == "MAGNITUDE" else "NATIVE_COMPONENT",
                            "static": {"step": 1, "increment": 1, "load_parameter": 1.}, "coverage": "ALL_MESH_NODES"}}
    assert case == before
    selected["source_field"]["position_mm"][2] = 999
    selected["source_field"]["static"]["step"] = 999
    assert case == before
    assert "time" not in selected["source_field"] and "axis" not in selected["source_field"]


def test_fixture_refinement_selects_actual_artifact_mesh_without_cross_mesh_node_identity():
    coarse, fine = _case(selected=False), _case(selected=False, index=1)
    fine["raw"]["nodes"][3]["position_mm"] = [0., 0., 3.]
    fine["raw"]["nodes"][3]["displacement_mm"][0] = -.02
    fine["raw"]["nodes"][3]["displacement_tokens"][0] = "-2.00000E-02"
    fine["artifact"] = _field_entry(fine["artifact"]["path"], fine["raw"])
    fine["selection"]["sha256"] = fine["artifact"]["sha256"]
    fine["result"]["artifacts"][-1] = deepcopy(fine["artifact"])
    manifest = coarse["result"]["artifacts"] + fine["result"]["artifacts"]
    coarse["result"]["artifacts"] = deepcopy(manifest)
    fine["result"]["artifacts"] = deepcopy(manifest)
    c, f = select_field_response(**coarse), select_field_response(**fine)
    assert (c["value"], f["value"]) == (-.01, -.02)
    assert c["source_field"]["node_id"] == f["source_field"]["node_id"] == 43
    assert c["source_field"]["artifact"] != f["source_field"]["artifact"]
    assert c["source_field"]["sha256"] != f["source_field"]["sha256"]
    assert c["source_field"]["position_mm"] != f["source_field"]["position_mm"]
    fine["raw"]["mesh_index"] = 0
    with pytest.raises(ValueError, match="mesh level"):
        select_field_response(**fine)


@pytest.mark.parametrize("key,value", [
    ("node_id", 0), ("node_id", -1), ("node_id", True), ("node_id", 43.),
    ("node_id", "43"), ("node_id", 2**53), ("node_id", 44),
    ("component", "U"), ("component", "norm"), ("component", "-UZ"),
    ("component", 1), ("component", ["UX"]), ("sha256", "b" * 64),
    ("sha256", "A" * 64), ("cad_revision", "b" * 64),
    ("artifact", "../simulation/field.json"), ("artifact", "simulation\\field.json"),
    ("artifact", "/simulation/field.json"), ("artifact", "simulation/unknown.json")])
def test_selection_requires_exact_supported_positive_identity(key, value):
    case = _case(True)
    case["selection"][key] = value
    with pytest.raises(ValueError):
        select_field_response(**case)


@pytest.mark.parametrize("change", ["extra", "missing"])
def test_selection_cannot_smuggle_scope_or_a_nearest_point(change):
    case = _case()
    if change == "extra":
        case["selection"]["nearest_position_mm"] = [0., 0., 2.]
    else:
        del case["selection"]["cad_revision"]
    with pytest.raises(ValueError):
        select_field_response(**case)


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("path,value", [
    (("position_unit",), "m"), (("displacement_unit",), "m"), (("force_unit",), "kN"),
    (("coordinate_frame",), "WORLD"), (("schema_version",), "2.0"),
    (("adapter_version",), "999"), (("coverage",), "LOADED_NODES"),
    (("qualification",), "QUALIFIED"), (("engineering_valid",), True),
    (("cad_revision",), "b" * 64), (("parent_experiment_id",), "E_OTHER_CAD"),
    (("static", "step"), True), (("static", "increment"), 1.),
    (("static", "load_parameter"), True), (("static", "load_parameter"), float("inf")),
    (("static", "load_parameter"), 2.), (("static", "time_s"), 1.),
    (("nodes", 3, "displacement_mm", 0), float("nan")),
    (("nodes", 9, "displacement_mm", 2), float("inf")),
    (("nodes", 9, "position_mm", 1), True), (("nodes", 9, "position_mm", 2), float("inf")),
    (("nodes", 3, "displacement_mm", 0), False),
    (("nodes", 3, "displacement_tokens", 0), "-0.02"),
    (("nodes", 3, "node_id"), 43.), (("nodes", 3, "node_id"), True),
    (("nodes", 4, "node_id"), 43), (("node_count",), True),
    (("element_count",), 0), (("elements", 0, "type"), "C3D4"),
    (("elements", 0, "node_ids", 9), 999), (("elements", 0, "node_ids", 9), 7),
    (("elements", 0, "element_id"), True), (("boundary_faces", 0, "element_id"), 31),
    (("boundary_faces", 0, "node_ids", 3), 67),
    (("sources", "dat", "sha256"), "b" * 64), (("sources", "dat", "bytes"), 1),
    (("sources", "dat", "bytes"), True), (("sources", "deck", "path"), "foreign.inp")])
def test_invalid_retained_contract_is_refused_even_off_selected_node(native, path, value):
    case = _case(native)
    target = case["raw"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        select_field_response(**case)


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("part", ["missing_node", "orphan_node", "missing_boundary", "duplicate_boundary",
                                   "extra_source", "missing_source", "duplicate_manifest", "manifest_size",
                                   "manifest_revision", "manifest_mime", "detached_artifact"])
def test_complete_coverage_and_original_manifest_are_required(native, part):
    case = _case(native)
    raw, manifest = case["raw"], case["result"]["artifacts"]
    if part == "missing_node":
        raw["nodes"].pop()
        raw["node_count"] -= 1
    elif part == "orphan_node":
        raw["nodes"].append({**deepcopy(raw["nodes"][-1]), "node_id": 999})
        raw["node_count"] += 1
    elif part == "missing_boundary":
        raw["boundary_faces"].pop()
        raw["boundary_face_count"] -= 1
    elif part == "duplicate_boundary":
        row = deepcopy(raw["boundary_faces"][-1])
        row["element_id"] = 18
        raw["boundary_faces"].append(row)
        raw["boundary_face_count"] += 1
    elif part == "extra_source":
        raw["sources"]["foreign"] = deepcopy(raw["sources"]["dat"])
    elif part == "missing_source":
        del raw["sources"]["dat"]
    elif part == "duplicate_manifest":
        manifest.append(deepcopy(manifest[0]))
    elif part == "manifest_size":
        manifest[0]["size_bytes"] += 1
    elif part == "manifest_revision":
        manifest[0]["revision"] = "b" * 64
    elif part == "manifest_mime":
        manifest[-1]["mime_type"] = case["artifact"]["mime_type"] = "text/plain"
    else:
        case["artifact"]["role"] = "UNRECORDED"
    with pytest.raises(ValueError):
        select_field_response(**case)


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("part", ["proposal_parent", "proposal_revision", "proposal_study", "proposal_backend",
                                   "provenance_parent", "proposal_execution", "unsupported", "incomplete",
                                   "unconverged", "released"])
def test_envelopes_cannot_pair_another_result_cad_or_execution(native, part):
    case = _case(native)
    proposal, result = case["proposal"], case["result"]
    if part == "proposal_parent":
        proposal["parent_experiment_id"] = "E_OTHER_CAD"
    elif part == "proposal_revision":
        proposal["model"]["geometry"]["cad_revision"] = "b" * 64
    elif part == "proposal_study":
        proposal["study_id"] = "S_OTHER"
    elif part == "proposal_backend":
        proposal["physics"]["backend"] = "fixture.gmsh"
    elif part == "provenance_parent":
        result["provenance"]["parent_experiment_id"] = "E_OTHER_CAD"
    elif part == "proposal_execution":
        proposal["execution"]["mesh"]["extra"] = True
    elif part == "unsupported":
        result["provenance"]["adapter"] = "pde.fenicsx"
    elif part == "incomplete":
        result["status"] = "REJECTED"
    elif part == "unconverged":
        result["converged"] = False
    else:
        result["decision"] = "RELEASED"
    with pytest.raises(ValueError):
        select_field_response(**case)


@pytest.mark.parametrize("part", ["catalog", "step", "deck", "peak", "metric", "partial_dof_missing",
                                   "dof_token", "load_token", "load_total", "face", "load_region", "mesh_mode",
                                   "mesh_bool", "material_nonfinite", "material_bool", "material_zero",
                                   "poisson_limit", "material_law", "contact", "bc_type", "load_type"])
def test_native_preserves_own_catalog_partial_dofs_signed_loads_and_whole_field_peak(part):
    case = _case(True)
    raw = case["raw"]
    declaration = case["proposal"]["execution"]["declaration"]
    if part == "catalog":
        raw["native_catalog_revision"] = "b" * 64
    elif part == "step":
        raw["parent_step_sha256"] = "b" * 64
    elif part == "deck":
        raw["deck_sha256"] = "b" * 64
    elif part == "peak":
        raw["peak_node_id"] = 43
    elif part == "metric":
        case["result"]["metrics"]["max_displacement"]["value"] = .05
    elif part == "partial_dof_missing":
        raw["prescribed_dofs"].pop()
    elif part == "dof_token":
        raw["prescribed_dofs"][0]["value_token"] = "1"
    elif part == "load_token":
        raw["loads"][0]["force_token"] = "1"
    elif part == "load_total":
        raw["loads"][0].update(force_N=-2., force_token="-2.000000000000e+00")
    elif part == "face":
        raw["boundary_faces"][0]["selection_id"] = f"F-{'b' * 64}-Face1"
    elif part == "load_region":
        raw["load_regions"][0]["selection_id"] = f"F-{'b' * 64}-Face2"
    elif part == "mesh_mode":
        declaration["mesh"]["mode"] = "sweep"
        case["proposal"]["execution"]["mesh"]["mode"] = "sweep"
    elif part == "mesh_bool":
        declaration["mesh"]["max_size_mm"] = True
        case["proposal"]["execution"]["mesh"]["max_size_mm"] = True
        raw["mesh_size_max_mm"] = 1.
    elif part == "material_nonfinite":
        declaration["materials"][0]["young_modulus_MPa"] = float("inf")
    elif part == "material_bool":
        declaration["materials"][0]["poisson_ratio"] = True
    elif part == "material_zero":
        declaration["materials"][0]["young_modulus_MPa"] = 0.
    elif part == "poisson_limit":
        declaration["materials"][0]["poisson_ratio"] = .5
    elif part == "material_law":
        declaration["materials"][0]["law"] = "plasticity"
    elif part == "contact":
        declaration["contact"]["mode"] = "bonded"
    elif part == "bc_type":
        declaration["boundary_conditions"][0]["type"] = "fixed"
    else:
        declaration["loads"][0]["type"] = "pressure"
    _sync_native_proposal(case)
    with pytest.raises(ValueError):
        select_field_response(**case)


def test_native_signed_force_weights_and_partial_dofs_are_not_rewritten():
    case = _case(True)
    before = deepcopy(case)
    assert any(row["force_N"] < 0 for row in case["raw"]["loads"])
    assert {row["component"] for row in case["raw"]["prescribed_dofs"]} == {1}
    select_field_response(**case)
    assert case == before


@pytest.mark.parametrize("part", ["level", "size", "fixed", "fixed_bool", "force", "force_bool", "force_token",
                                   "dat", "loaded_count", "sensitivity", "metric"])
def test_fixture_retains_recorded_base_saddle_level_and_unassessed_mesh(part):
    case = _case()
    raw, details = case["raw"], case["result"]["provenance"]["adapter_details"]
    if part == "level":
        raw["mesh_index"] = 1
    elif part == "size":
        raw["mesh_size_max_mm"] = 3.
    elif part == "fixed":
        raw["fixed_node_ids"].remove(7)
    elif part == "fixed_bool":
        raw["fixed_dofs"][0] = True
    elif part == "force":
        raw["loads"][0]["force_N"][2] = 1.
    elif part == "force_bool":
        raw["loads"][0]["dof"] = True
    elif part == "force_token":
        raw["loads"][0]["force_token"] = "-2"
    elif part == "dat":
        details["per_mesh_displacement"]["studies"][0]["displacement_table_sha256"] = "b" * 64
    elif part == "loaded_count":
        details["per_mesh_displacement"]["studies"][0]["loaded_node_count"] = 2
    elif part == "sensitivity":
        details["mesh_sensitivity"]["status"] = "PASS"
    else:
        case["result"]["metrics"]["displacement_mesh_change_ratio"].update(valid=True, value=0.)
    with pytest.raises(ValueError):
        select_field_response(**case)


def test_no_file_read_write_or_native_call_is_needed(monkeypatch):
    cases = [_case(), _case(True)]

    def forbidden(*args, **kwargs):
        raise AssertionError("Pure adapter must not access files")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(Path, "read_bytes", forbidden)
        patch.setattr(Path, "read_text", forbidden)
        patch.setattr(Path, "write_bytes", forbidden)
        patch.setattr(Path, "write_text", forbidden)
        for case in cases:
            assert select_field_response(**case)["value"] == -.01
