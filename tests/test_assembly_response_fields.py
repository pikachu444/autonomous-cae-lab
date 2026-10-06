"""TEST_ONLY seven coincident bodies; no native solve or numerical qualification.

Reuse the retained parser's small synthetic complete tables. Artificial source
pins below exercise parsed/manifest joins; Core separately verifies file bytes.
"""

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import math

import pytest

from test_fixture_assembly_affine_field import synthetic
from caelab.adapters.fixture_assembly_mechanics_fields import parse_fields
from caelab.adapters.assembly_response_fields import (
    AssemblyResponseFieldsAdapter, BACKEND, FIELD_PATH, MAPPING_PATH, AXIS, SOURCE_LIMITS,
    display_field, select_field_response,
)
from caelab.storage import canonical_hash
from plugins.fixture_design.assembly_mesh import ACTIVE


CAD, MESH = "a" * 64, "b" * 64


def _entry(path, value=None):
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
               if value is not None else ("TEST_ONLY artificial source pin " + path).encode())
    return {"path": path, "sha256": hashlib.sha256(payload).hexdigest(), "size_bytes": len(payload),
            "mime_type": "application/json" if path.endswith(".json") else "application/octet-stream", "revision": CAD}


def _reseal(case):
    result, proposal = case["result"], case["proposal"]
    result["provenance"]["execution_settings"] = deepcopy(proposal["execution"])
    result["provenance"]["adapter_details"]["execution_settings"] = deepcopy(proposal["execution"])
    result["provenance"]["proposal_sha256"] = result["proposal_revision"] = canonical_hash(proposal)
    result["metrics"]["max_displacement"]["value"] = max(math.hypot(*row["displacement_mm"])
        for body in case["raw"]["bodies"].values() for row in body["nodes"])
    for key, path, value in (("artifact", FIELD_PATH, case["raw"]), ("mapping_artifact", MAPPING_PATH, case["mapping"])):
        case[key] = _entry(path, value)
        result["artifacts"] = [row for row in result["artifacts"] if row["path"] != path] + [deepcopy(case[key])]
    case["selection"] = {"artifact": FIELD_PATH, "sha256": case["artifact"]["sha256"], "cad_revision": CAD,
                         "node_id": case["raw"]["bodies"][ACTIVE[0]]["nodes"][0]["source_node_id"], "component": "UX"}


@lru_cache(maxsize=1)
def _base_case():
    original = synthetic()
    mapping, native = original.mapping, original.raw
    for group in mapping["physical_groups"]:
        if group["dim"] == 2:
            group["catalog_face_id"] = group["component_id"] + ":TEST_ONLY-face-" + group["name"]
    for row in mapping["elements"]:
        if row["dim"] == 2:
            group = next(group for group in mapping["physical_groups"] if group["dim"] == 2 and group["tag"] == row["physical_tag"])
            row["catalog_face_id"] = group["catalog_face_id"]
    policy = {"load_parameters": [0., .25, .5, .75, 1.], "residual_relative": 1e-6,
              "maximum_iterations": 50, "contact_coefficient": 1000.}
    native.update(order=4, available_orders=[0, 1, 2, 3, 4], load_parameter=1.,
                  access_parameters={"NUME_ORDRE": [0, 1, 2, 3, 4], "INST": policy["load_parameters"]})
    native["geometry_context"]["selected_result_order"] = 4
    for table in native["tables"].values():
        if "NUME_ORDRE" in table:
            table["NUME_ORDRE"] = [4] * len(table["NUME_ORDRE"])
    for energy in native["native_energy"].values():
        energy["selection"]["NUME_ORDRE"] = 4
        energy["table"]["NUME_ORDRE"] = [4]
    # Artifact JSONs are decoded independently in Core; no in-memory XYZ alias.
    raw = deepcopy(parse_fields(native, mapping, original.catalog, original.quality,
                                {"components": list(ACTIVE), "solver_policy": policy}))
    raw["bodies"][ACTIVE[0]]["nodes"][0]["displacement_mm"] = [-0.0, -.02, .03]
    raw["bodies"][ACTIVE[0]]["nodes"][0]["reaction_n"] = [-3., 4., -5.]
    selections = [{"id": "B-" + component, "kind": "native_assembly_body", "component_id": component} for component in ACTIVE]
    selections += [{"id": "S-" + group["name"], "kind": "native_assembly_face", "component_id": group["component_id"],
                    "catalog_face_id": group["catalog_face_id"]} for group in mapping["physical_groups"] if group["dim"] == 2]
    retained = {"mesh_revision": MESH, "cad_revision": CAD, "profile": "coarse3", "active_components": list(ACTIVE)}
    declaration = {"analysis_type": "nonlinear_static", "units": {"length": "mm", "force": "N", "stress": "MPa"},
        "coordinate_system": "global", "mesh": {"mode": "retained", "mesh_revision": MESH},
        "materials": [{"id": "M-" + component, "selection_id": "B-" + component, "law": "isotropic_linear_elastic",
                       "young_modulus_MPa": 210000., "poisson_ratio": .3,
                       "source": {"category": "ASSUMED", "description": "TEST_ONLY; not measured"}} for component in ACTIVE],
        "boundary_conditions": [{"id": "partial", "selection_id": "S-F0001", "components": {"UX": .02, "UZ": -.01},
                                 "type": "displacement", "unit": "mm", "coordinate_system": "global", "source": "TEST_ONLY partial DOFs"}],
        "loads": [{"id": "drive", "selection_id": "S-F0077", "components": {"FX": -2.5, "FY": 0., "FZ": -100.},
                   "type": "resultant_force", "unit": "N", "coordinate_system": "global", "source": "TEST_ONLY signed load"}],
        "contact": {"mode": "none", "pairs": [], "source": "TEST_ONLY contact assumption"}}
    execution = {"analysis_type": "nonlinear_static", "catalog": {"cad_revision": CAD, "cad_backend": "fixture.assembly",
        "model": "bending_assembly", "units": {"length": "mm", "area": "mm^2", "volume": "mm^3"},
        "retained_mesh": retained, "selections": selections}, "declaration": declaration,
        "mesh": deepcopy(declaration["mesh"]), "solver_policy": policy}
    proposal = {"id": "TEST-solve", "parent_experiment_id": "TEST-cad", "study_id": "TEST-study",
        "physics": {"backend": BACKEND}, "execution": execution,
        "model": {"geometry": {"source_experiment_id": "TEST-cad", "cad_revision": CAD}, "materials": deepcopy(declaration["materials"])},
        "loads": deepcopy(declaration["loads"]), "boundary_conditions": deepcopy(declaration["boundary_conditions"])}
    paths = ["simulation/native/worker-result.json", "simulation/native/native-catalog.json", "simulation/mesh-reuse/mesh.msh",
             "simulation/mesh-reuse/mesh-reuse-receipt.json", *["simulation/native/" + name for name in
             ("depl.table.json", "reac_noda.table.json", "sief_elga.table.json", "coor_elga.table.json")]]
    artifacts = [_entry(path) for path in paths]
    pins = {row["path"]: {key: row[key] for key in ("sha256", "size_bytes")} for row in artifacts}
    parent = {"experiment_id": "TEST-cad", "cad_revision": CAD, "native_revision": "c" * 64}
    details = {"adapter": BACKEND, "adapter_version": "1", "mesh_revision": MESH,
        "cad_parent": {**parent, "result_sha256": "d" * 64, "cad_prefix": "cad"},
        "reuse": {"mesh_revision": MESH, "parent": parent, "status": "CAPTURED_BYTE_REUSE", "capture_only": True,
                  "receipt": {"path": "mesh-reuse-receipt.json", **pins[paths[3]]}},
        "worker_result_entry": pins[paths[0]], "native_catalog_entry": pins[paths[1]], "original_mesh_entry": pins[paths[2]],
        "retained_native_files": {path[len("simulation/"):]: pins[path] for path in paths if ".table.json" in path},
        "geometry_checks": deepcopy(raw["geometry_checks"]), "axis_semantics": AXIS, "actual_load_parameters": policy["load_parameters"]}
    result = {"experiment_id": "TEST-solve", "parent_experiment_id": "TEST-cad", "cad_revision": CAD,
        "study": {"id": "TEST-study"}, "status": "COMPLETED_REVIEW_REQUIRED", "solver_status": "COMPLETED", "converged": True,
        "decision": "NOT_RELEASED", "provenance": {"adapter": BACKEND, "adapter_version": "1", "parent_experiment_id": "TEST-cad",
        "adapter_details": details}, "metrics": {"max_displacement": {"value": 0., "unit": "mm", "valid": True},
        "peak_stress": {"value": None, "unit": "MPa", "valid": False, "reason": "Native Gauss tensors are not nodal strength"}},
        "validations": [{"status": "UNKNOWN", "blocking": True, "experiment_id": "TEST-solve", "cad_revision": CAD,
                         "type": "TEST-physical-" + str(i)} for i in range(7)], "artifacts": artifacts}
    case = {"result": result, "proposal": proposal, "raw": raw, "mapping": mapping}
    _reseal(case)
    return case


def _case():
    return deepcopy(_base_case())


def _display(case):
    return display_field(**{key: value for key, value in case.items() if key != "selection"})


def _put(obj, path, value):
    for key in path[:-1]:
        obj = obj[key]
    obj[path[-1]] = value


def test_complete_display_preserves_sparse_ids_coincident_bodies_original_connectivity_and_signed_arrays():
    case = _case()
    before = deepcopy(case)
    field = _display(case)
    assert case == before and field["kind"] == "assembly_mechanics_nodal_displacement_display"
    assert field["node_count"] == 245 and field["element_count"] == 42 and field["boundary_face_count"] == 84
    assert len(field["display_triangles"]) == 336 and len(field["bodies"]) == 7
    assert field["source_nodes"] == case["mapping"]["nodes"]
    assert field["identity"] == case["raw"]["native_import_comparison"]
    assert field["static"] == {"order": 4, "load_parameter": 1., "axis_semantics": AXIS}
    assert field["metrics"] == case["result"]["metrics"] and field["validations"] == case["result"]["validations"]
    assert field["qualification"] == "UNKNOWN" and field["decision"] == "NOT_RELEASED" and field["engineering_valid"] is False
    assert field["native_gauss"]["point_count"] == 210 and field["native_gauss"]["nodal_stress"] == "NOT_CONSTRUCTED"
    assert "loads" not in field and "fixed_node_ids" not in field and "gauss" not in field
    original = {row["id"]: row for row in case["mapping"]["elements"]}
    for row in field["elements"] + field["boundary_faces"]:
        assert row["node_ids"] == original[row["element_id"]]["node_ids"]
    chosen = next(row for row in field["nodes"] if row["node_id"] == case["selection"]["node_id"])
    assert chosen["displacement_mm"] == [-0., -.02, .03] and chosen["reaction_n"] == [-3., 4., -5.]
    assert json.dumps(chosen["displacement_mm"]).startswith("[-0.0,")
    same_xyz = [row for row in field["nodes"] if row["position_mm"] == chosen["position_mm"]]
    assert len(same_xyz) == 7 and len({row["node_id"] for row in same_xyz}) == 7
    field["nodes"][0]["displacement_mm"][0] = 99
    field["identity"]["source_node_ids_by_native_index"].clear()
    field["metrics"]["peak_stress"]["valid"] = True
    assert case == before


def test_each_linear_display_triangle_is_outward_with_exact_original_face_and_owning_volume_ids():
    field = _display(_case())
    nodes = {row["node_id"]: row["position_mm"] for row in field["nodes"]}
    faces = {row["element_id"]: row for row in field["boundary_faces"]}
    elements = {row["element_id"]: row for row in field["elements"]}
    for triangle in field["display_triangles"]:
        face, element = faces[triangle["face_id"]], elements[triangle["owner_element_id"]]
        assert set(triangle["node_ids"]) <= set(face["node_ids"])
        assert face["component_id"] == element["component_id"] == triangle["component_id"]
        opposite = next(i for i in element["node_ids"][:4] if i not in face["node_ids"][:3])
        a, b, c, d = [nodes[i] for i in (*triangle["node_ids"], opposite)]
        u, v = [b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)]
        cross = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
        assert sum(cross[i]*(d[i]-a[i]) for i in range(3)) < 0


@pytest.mark.parametrize("component,value", [("UX", -0.), ("UY", -.02), ("UZ", .03), ("MAGNITUDE", math.hypot(-0., -.02, .03))])
def test_selected_component_is_exact_signed_node_value_and_magnitude_is_explicitly_derived(component, value):
    case = _case()
    case["selection"]["component"] = component
    before = deepcopy(case)
    selected = select_field_response(**case)
    assert selected["value"] == value and selected["unit"] == "mm"
    assert selected["source_field"]["component"] == component
    assert selected["source_field"]["value_origin"] == ("DERIVED_MAGNITUDE" if component == "MAGNITUDE" else "NATIVE_COMPONENT")
    assert selected["source_field"]["mesh_revision"] == MESH and selected["source_field"]["mapping_sha256"] == case["mapping_artifact"]["sha256"]
    assert selected["source_field"]["static"]["axis_semantics"] == AXIS and "axis" not in selected["source_field"]
    assert selected["qualification"] == "UNKNOWN" and selected["alignment"] == "USER_DECLARED_UNVERIFIED"
    if component == "UX":
        assert math.copysign(1, selected["value"]) == -1
    selected["source_field"]["position_mm"][0] = 99
    assert case == before


@pytest.mark.parametrize("key,value", [("node_id", 0), ("node_id", True), ("node_id", 1), ("node_id", 2**53),
    ("node_id", "100017"), ("component", "RFZ"), ("component", "norm"), ("component", ["UX"]),
    ("artifact", "simulation/native/depl.table.json"), ("sha256", "f"*64), ("cad_revision", "f"*64)])
def test_selection_never_falls_back_to_native_index_nearest_point_or_another_artifact(key, value):
    case = _case()
    case["selection"][key] = value
    with pytest.raises(ValueError):
        select_field_response(**case)


@pytest.mark.parametrize("path,value", [
    (("result", "status"), "REJECTED"), (("result", "decision"), "RELEASED"),
    (("result", "provenance", "adapter_version"), "2"), (("result", "study", "id"), "OTHER-study"),
    (("result", "parent_experiment_id"), "OTHER-cad"), (("result", "proposal_revision"), "f"*64),
    (("result", "provenance", "adapter_details", "mesh_revision"), "f"*64),
    (("mapping_artifact", "sha256"), "f"*64), (("artifact", "path"), "../simulation/admitted-fields.json"),
    (("result", "provenance", "adapter_details", "worker_result_entry", "sha256"), "f"*64),
    (("result", "metrics", "peak_stress", "valid"), True),
])
def test_wrong_record_revision_manifest_or_source_pin_is_refused_without_mutation(path, value):
    case = _case()
    _put(case, path, value)
    before = deepcopy(case)
    with pytest.raises(ValueError):
        _display(case)
    assert case == before


@pytest.mark.parametrize("fault", ["missing-node", "duplicate-node", "wrong-body", "native-index", "nonfinite-u", "bool-rf",
    "xyz", "false-exterior", "missing-gauss", "duplicate-gauss", "gauss-id", "gauss-order", "gauss-stress",
    "missing-face", "midside", "shared-id", "physical-group", "wrong-axis", "metric-substitution", "catalog-face",
    "body-count", "energy", "nonfinite-reference"])
def test_complete_native_arrays_topology_body_axis_and_metric_identity_are_required(fault):
    case = _case()
    body = case["raw"]["bodies"][ACTIVE[0]]
    if fault == "missing-node": body["nodes"].pop()
    elif fault == "duplicate-node": body["nodes"][1] = deepcopy(body["nodes"][0])
    elif fault == "wrong-body": body["nodes"][0] = deepcopy(case["raw"]["bodies"][ACTIVE[1]]["nodes"][0])
    elif fault == "native-index": body["nodes"][0]["native_index"] = 0
    elif fault == "nonfinite-u": body["nodes"][0]["displacement_mm"][1] = float("inf")
    elif fault == "bool-rf": body["nodes"][0]["reaction_n"][0] = True
    elif fault == "xyz": body["nodes"][0]["xyz_mm"][0] += 1e-6
    elif fault == "false-exterior": body["nodes"][0]["exterior"] = not body["nodes"][0]["exterior"]
    elif fault == "missing-gauss": body["gauss"].pop()
    elif fault == "duplicate-gauss": body["gauss"][1] = deepcopy(body["gauss"][0])
    elif fault == "gauss-id": body["gauss"][0]["source_element_id"] += 1
    elif fault == "gauss-order": body["gauss"][0]["order"] = 1
    elif fault == "gauss-stress": body["gauss"][0]["stress6_mpa"][0] = True
    elif fault == "missing-face": case["mapping"]["elements"].pop()
    elif fault == "midside": case["mapping"]["elements"][0]["node_ids"][4] = case["mapping"]["elements"][0]["node_ids"][5]
    elif fault == "shared-id": case["mapping"]["nodes"][35]["id"] = case["mapping"]["nodes"][0]["id"]
    elif fault == "physical-group": case["mapping"]["physical_groups"][0]["component_id"] = ACTIVE[1]
    elif fault == "wrong-axis": case["raw"]["axis_semantics"] = "PHYSICAL_TIME_SECONDS"
    elif fault == "metric-substitution": case["result"]["metrics"]["max_displacement"]["value"] = .03
    elif fault == "body-count": case["raw"]["native_import_comparison"]["bodies"][0]["node_count"] -= 1
    elif fault == "energy": body["native_energy"]["value_n_mm"] = float("inf")
    elif fault == "nonfinite-reference": body["gauss"][0]["derived_geometry_reference"]["xyz_mm"][0] = float("inf")
    else:
        case["proposal"]["execution"]["catalog"]["selections"][-1]["catalog_face_id"] = "OTHER-face"
        _reseal(case)
    before = deepcopy(case)
    with pytest.raises(ValueError):
        _display(case)
    assert case == before


def test_manifest_aliases_and_boolean_sizes_refuse():
    for alteration in ("alias", "bool"):
        case = _case()
        if alteration == "alias":
            duplicate = deepcopy(case["artifact"])
            duplicate["path"] = duplicate["path"].upper()
            case["result"]["artifacts"].append(duplicate)
        else:
            case["mapping_artifact"]["size_bytes"] = True
            for entry in case["result"]["artifacts"]:
                if entry["path"] == MAPPING_PATH: entry["size_bytes"] = True
        with pytest.raises(ValueError): _display(case)


@pytest.mark.parametrize("role", ["field", "mapping"])
def test_source_byte_bounds_are_independent_of_complete_display_budget(role):
    case = _case()
    key = "artifact" if role == "field" else "mapping_artifact"
    case[key]["size_bytes"] = SOURCE_LIMITS[role] + 1
    for entry in case["result"]["artifacts"]:
        if entry["path"] == case[key]["path"]: entry["size_bytes"] = case[key]["size_bytes"]
    with pytest.raises(ValueError, match="source-read"): _display(case)


def test_pure_reader_registry_never_adds_executable_admission_or_opens_a_file(monkeypatch):
    case = _case()
    def denied(*args, **kwargs):
        raise AssertionError("Pure adapter unexpectedly opened a file or executed a process")
    monkeypatch.setattr("builtins.open", denied)
    monkeypatch.setattr("subprocess.Popen", denied)
    adapter = AssemblyResponseFieldsAdapter()
    assert not any(hasattr(adapter, name) for name in ("solve", "settings_from_conditions", "conditions_preflight"))
    expected = {"field": {"path": FIELD_PATH, "maximum_bytes": 536870912},
                "mapping": {"path": MAPPING_PATH, "maximum_bytes": 134217728}}
    assert adapter.field_response_resources(case["result"]) == expected
    resources = {"field": (case["raw"], case["artifact"]), "mapping": (case["mapping"], case["mapping_artifact"])}
    assert adapter.display_response_fields(case["result"], case["proposal"], resources) == _display(case)
    assert adapter.select_response_fields(case["result"], case["proposal"], resources, case["selection"]) == select_field_response(**case)
    expected["field"]["maximum_bytes"] = 1
    assert adapter.field_response_resources(case["result"])["field"]["maximum_bytes"] == 536870912
    with pytest.raises(ValueError): adapter.display_response_fields(case["result"], case["proposal"], {**resources, "extra": (None, None)})


def test_display_allocation_refusal_does_not_truncate_original_measurements(monkeypatch):
    import caelab.adapters.assembly_response_fields as reader
    case = _case()
    before = deepcopy(case)
    monkeypatch.setitem(reader.DISPLAY_LIMITS, "bytes", 1000)
    with pytest.raises(ValueError, match="no data is truncated"): _display(case)
    assert case == before


@pytest.mark.parametrize("resource,limit", [("nodes", 244), ("elements", 41), ("faces", 83), ("triangles", 335)])
def test_display_item_limits_refuse_complete_data_instead_of_dropping_nodes_or_faces(monkeypatch, resource, limit):
    import caelab.adapters.assembly_response_fields as reader
    case = _case()
    before = deepcopy(case)
    monkeypatch.setitem(reader.DISPLAY_LIMITS, resource, limit)
    with pytest.raises(ValueError, match="resource envelope"): _display(case)
    assert case == before


def test_unstored_initial_zero_is_not_fabricated_and_final_node_response_is_not_history():
    case = _case()
    case["raw"].update(available_orders=[1, 2, 3, 4], actual_load_parameters=[.25, .5, .75, 1.], initial_state="NOT_STORED")
    case["result"]["provenance"]["adapter_details"]["actual_load_parameters"] = [.25, .5, .75, 1.]
    _reseal(case)
    field = _display(case)
    assert field["actual_load_parameters"] == [.25, .5, .75, 1.] and field["initial_state"] == "NOT_STORED"
    assert field["available_orders"] == [1, 2, 3, 4] and field["static"]["order"] == 4
    assert select_field_response(**case)["source_field"]["static"]["load_parameter"] == 1.
    case["raw"]["initial_state"] = "NATIVE_STORED"
    with pytest.raises(ValueError, match="zero is never invented"): _display(case)


@pytest.mark.parametrize("key,value", [("available_orders", [0, 1, 2, True, 4]), ("available_orders", [0, 1, 1, 3, 4]),
    ("actual_load_parameters", [0., .5, 1.]), ("actual_load_parameters", [0., .25, True, .75, 1.]),
    ("actual_load_parameters", [0., .25, .75, .5, 1.])])
def test_native_increment_arrays_refuse_missing_nonfinite_bool_or_nonmonotone_samples(key, value):
    case = _case()
    case["raw"][key] = value
    with pytest.raises(ValueError): _display(case)


def test_unavailable_native_energy_stays_unknown_without_inventing_a_replacement():
    case = _case()
    unknown = {"status": "UNKNOWN", "value_n_mm": None, "reason": "TEST_ONLY unavailable native table"}
    case["raw"]["bodies"][ACTIVE[0]]["native_energy"] = deepcopy(unknown)
    _reseal(case)
    field = _display(case)
    assert field["bodies"][0]["native_energy"] == unknown and field["qualification"] == "UNKNOWN"
    assert select_field_response(**case)["value"] == -0.
