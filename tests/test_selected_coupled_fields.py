"""Read-only joins over TEST_ONLY full nine-source coupled capsules.

The existing transport fixture copies the actual producer source but replaces
its process with unsolved synthetic fields. No native execution or accuracy
claim is made. Core owns reading/hash containment; the reader gets parsed tuples.
"""

import builtins
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from caelab.adapters import pde_response_fields as reader
from test_pde_response_fields import fixture as legacy_fixture
from test_selected_coupled_adapter import candidate, _mock_process
from test_selected_coupled_reference import selected


def digest(value):
    raw = value if type(value) is bytes else json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def record_factory(candidate, tmp_path, monkeypatch):
    adapter, _ = candidate
    _mock_process(candidate, monkeypatch)
    created = []

    def make(settings=None):
        settings = deepcopy(selected() if settings is None else settings)
        folder = tmp_path / ("TEST_ONLY-child-" + str(len(created)))
        output = folder / "pde"
        outcome = adapter.FenicsxCoupledPDEAdapter().solve(output, settings)
        raw, manifest = {}, []
        revision = "a" * 64
        model = digest(adapter.domain.model_declaration(settings))
        for path in sorted(output.rglob("*")):
            if not path.is_file():
                continue
            data = path.read_bytes()
            relative = "pde/" + path.relative_to(output).as_posix()
            raw[relative] = json.loads(data) if path.suffix == ".json" else data
            manifest.append({"path": relative, "sha256": digest(data), "size_bytes": len(data),
                             "revision": revision, "mime_type": "application/octet-stream"})
        raw["pde/input.json"] = settings  # Identical parsed bytes; shared test mutation is explicit.
        proposal = {"id": "E-TEST_ONLY-" + str(len(created)), "study_id": "S-TEST_ONLY",
                    "model_revision": model, "cad_revision": None,
                    "physics": {"backend": adapter.FenicsxCoupledPDEAdapter.backend}, "execution": settings}
        result = {"experiment_id": proposal["id"], "study": {"id": proposal["study_id"]},
                  "proposal_revision": revision, "model_revision": model, "cad_revision": None,
                  "status": "REJECTED" if outcome["status"] == "REJECTED" else "COMPLETED_REVIEW_REQUIRED",
                  "solver_status": outcome["solver_status"], "decision": "NOT_RELEASED",
                  "metrics": deepcopy(outcome["metrics"]), "artifacts": manifest,
                  "validations": [{"type": name, "status": "UNKNOWN"} for name in outcome["pending_validations"]],
                  "provenance": {"adapter": adapter.FenicsxCoupledPDEAdapter.backend,
                                 "adapter_version": adapter.FenicsxCoupledPDEAdapter.version,
                                 "proposal_sha256": revision, "execution_settings": settings,
                                 "adapter_details": deepcopy(outcome["provenance"])}}
        field_adapter = reader.PDEResponseFieldsAdapter(result["provenance"]["adapter"])

        def resources(policy):
            entries = {item["path"]: item for item in result["artifacts"]}
            return {role: (raw[spec["path"]], entries[spec["path"]]) for role, spec in policy.items()}

        def headers():
            return resources(field_adapter.field_response_resources(result))

        def selection(index=0, component="u0", node=4):
            row = raw["pde/worker_result.json"]["mesh_studies"][index]
            path = "pde/" + row["files"]["dofs"]
            entry = next(item for item in result["artifacts"] if item["path"] == path)
            return {"kind": "pde_nodal", "artifact": path, "sha256": entry["sha256"],
                    "model_revision": result["model_revision"], "study_index": index,
                    "step_index": None, "node_id": node, "component": component}

        def select(selection_=None):
            selection_ = selection() if selection_ is None else selection_
            h = headers()
            policy = field_adapter.field_selection_resources(result, selection_, h)
            return field_adapter.select_response_fields(result, proposal, {**h, **resources(policy)}, selection_)

        def reseal():
            # TEST_ONLY rehashed malformed capsules let semantic fences run after
            # a simulated Core byte-verification success, not instead of it.
            detail = result["provenance"]["adapter_details"]
            worker = raw["pde/worker_result.json"]
            for row in worker["mesh_studies"]:
                row["artifact_sha256"] = {role: digest(raw["pde/" + path]) for role, path in row["files"].items()}
            detail["spec_sha256"] = worker["spec_sha256"] = digest(raw["pde/input.json"])
            detail["source_manifest_sha256"] = worker["source_manifest_sha256"] = digest(raw["pde/source_manifest.json"])
            result["artifacts"] = [{"path": path, "sha256": digest(value),
                "size_bytes": len(value) if type(value) is bytes else len(json.dumps(
                    value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()),
                "revision": revision, "mime_type": "application/octet-stream"} for path, value in raw.items()]

        f = {"result": result, "proposal": proposal, "raw": raw, "settings": settings,
             "worker": raw["pde/worker_result.json"], "source": raw["pde/source_manifest.json"],
             "detail": result["provenance"]["adapter_details"], "adapter": field_adapter,
             "headers": headers, "resources": resources, "selection": selection, "select": select,
             "reseal": reseal, "domain": adapter.domain, "folder": folder}
        f["row"] = f["worker"]["mesh_studies"][0]
        f["field"] = raw["pde/" + f["row"]["files"]["dofs"]]
        f["binding"] = raw["pde/" + f["row"]["files"]["binding"]]
        created.append(f)
        return f
    return make


def test_selected_original_signed_components_and_stationary_dimensionless_identity(record_factory):
    f = record_factory()
    before = deepcopy((f["result"], f["proposal"], f["raw"]))
    catalog = f["adapter"].display_response_fields(f["result"], f["proposal"], f["headers"]())
    assert len(catalog["entries"]) == 1 and catalog["coordinate_frame"] == "PDE_MODEL_CARTESIAN"
    entry = catalog["entries"][0]
    assert entry["cells_per_axis"] == 2 and entry["time"] is None and entry["step_index"] is None
    assert entry["artifact"] == "pde/level_n2/dofs.json" and entry["unit"] == "1"
    assert entry["components"] == ["u0", "u1"]
    node = next(node for node, values in zip(f["field"]["node_ids"], f["field"]["values"]) if values == [-2., 3.])
    for component, expected in (("u0", -2.), ("u1", 3.)):
        selected_value = f["select"](f["selection"](node=node, component=component))
        assert selected_value["value"] == expected and selected_value["unit"] == "1"
        assert selected_value["source_field"]["node_id"] == node
        assert selected_value["source_field"]["axis_semantics"] == "STATIONARY_PDE; NO_TIME_AXIS"
        assert "response_axis" not in selected_value
        assert selected_value["qualification"] == {"numeric": "RECORDED_NATIVE_VALUE",
            "reference": "RECORDED_DOMAIN_VERDICT_UNCHANGED", "physical": "UNKNOWN", "decision": "NOT_RELEASED"}
        assert selected_value["alignment"] == "USER_DECLARED_UNVERIFIED"
        selected_value["source_field"]["coordinates"][0] = -999.
    assert (f["result"], f["proposal"], f["raw"]) == before
    for name in f["domain"]._REFERENCE_METRICS:
        assert f["result"]["metrics"][name]["value"] is None and f["result"]["metrics"][name]["valid"] is False
    assert f["proposal"]["cad_revision"] is None


def test_policy_reuses_complete_nine_source_capsule_and_two_selected_native_resources(record_factory):
    f = record_factory()
    assert f["source"]["domain_plugin_version"] == "1.1" and len(f["source"]["files"]) == 9
    entries = {entry["path"]: entry for entry in f["result"]["artifacts"]}
    for role, pin in f["source"]["files"].items():
        path = "pde/" + pin["copied_path"]
        assert digest(f["raw"][path]) == pin["sha256"] == entries[path]["sha256"] == f["detail"]["source_sha256"][role]
    h = f["headers"]()
    assert set(h) == {"input", "source", "worker"}
    policy = f["adapter"].field_selection_resources(f["result"], f["selection"](), h)
    assert policy == {role: {"path": "pde/level_n2/" + name, "maximum_bytes": reader.JSON_LIMIT}
                     for role, name in (("dofs", "dofs.json"), ("binding", "binding.json"))}
    assert all(row["reference_values"] is None for row in f["binding"]["regions"].values())


def test_current_canonical_producer_keeps_three_reference_levels_and_numerical_criteria(record_factory):
    from plugins.pde_coupled import reference as domain
    settings = domain.manufactured_settings()
    settings["mesh"]["cell_counts"] = [2, 4, 8]
    f = record_factory(settings)
    original = deepcopy((f["result"]["metrics"], f["result"]["validations"]))
    catalog = f["adapter"].display_response_fields(f["result"], f["proposal"], f["headers"]())
    assert [entry["cells_per_axis"] for entry in catalog["entries"]] == [2, 4, 8]
    assert f["settings"]["validation"] == {"max_l2_error": .04, "min_l2_rate": 1.8,
        "max_h1_seminorm_error": .8, "min_h1_rate": .9, "max_residual_relative": 1e-10}
    for index, row in enumerate(f["worker"]["mesh_studies"]):
        field = f["raw"]["pde/" + row["files"]["dofs"]]
        binding = f["raw"]["pde/" + row["files"]["binding"]]
        assert all(type(region["reference_values"]) is list for region in binding["regions"].values())
        sel = f["selection"](index=index, node=field["node_ids"][-1], component="u1")
        assert f["select"](sel)["value"] == field["values"][-1][1]
    assert (f["result"]["metrics"], f["result"]["validations"]) == original


def test_historical_producer_uses_original_capsule_not_current_domain_validator(monkeypatch):
    f = legacy_fixture("coupled", rejected=True)
    from plugins.pde_coupled import reference as domain
    monkeypatch.setattr(domain, "validate_settings", lambda *args: pytest.fail("Historical producer must not use current input admission"))
    before = deepcopy((f["result"], f["raw"]))
    assert f["select"](f["selection"](node=31, component="u0"))["value"] == -11.
    assert (f["result"], f["raw"]) == before
    f["bindings"][0]["regions"]["left"]["reference_values"] = None
    f["seal"]()
    with pytest.raises(ValueError, match="reference traces"):
        f["select"]()


@pytest.mark.parametrize("mutation", [
    lambda f: f["result"]["provenance"].update(adapter_version="1"),
    lambda f: f["detail"].update(domain_plugin_version="1"),
    lambda f: f["source"].update(domain_plugin_version="1"),
    lambda f: f["settings"].pop("mode"),
    lambda f: f["settings"].pop("input_provenance"),
    lambda f: f["settings"].update(mode="selected_history"),
    lambda f: f["settings"]["problem"].update(reference={"solution": {}, "source": "Invented"}),
    lambda f: f["worker"].pop("mode"),
    lambda f: f["worker"].update(scope="SELECTED_DIMENSIONLESS_SCALAR_RECTANGLE"),
    lambda f: f["detail"].update(input_provenance={"origin": "SYNTHETIC", "reference": "Another source"}),
    lambda f: f["worker"].update(input_provenance={"origin": "ASSUMED", "reference": "Another source"}),
    lambda f: f["settings"]["input_provenance"].update(origin="UNKNOWN"),
    lambda f: f["settings"]["input_provenance"].update(reference=" "),
    lambda f: f["settings"]["mesh"]["cell_counts"].append(4),
    lambda f: f["settings"]["mesh"]["cell_counts"].__setitem__(0, 3),
    lambda f: f["settings"]["validation"].update(max_l2_error=.04),
    lambda f: f["settings"]["validation"].update(max_residual_relative=True),
    lambda f: f["detail"].update(error_quadrature_degree=8),
    lambda f: f["row"].update(global_nodes=6),
    lambda f: f["row"].update(interface_facets=1),
    lambda f: f["row"].update(l2_error=0.),
    lambda f: f["row"]["components"][1].update(h1_seminorm_error=0.),
])
def test_rehashed_unadvertised_mode_source_reference_or_level_refuses(record_factory, mutation):
    f = record_factory()
    mutation(f)
    f["reseal"]()
    with pytest.raises(ValueError):
        f["adapter"].display_response_fields(f["result"], f["proposal"], f["headers"]())


@pytest.mark.parametrize("mutation", [
    lambda f: f["binding"]["regions"]["left"].update(reference_values=[]),
    lambda f: f["binding"]["regions"]["left"].pop("reference_values"),
    lambda f: f["binding"]["regions"]["right"]["rhs_values"][0].__setitem__(1, 999.),
    lambda f: f["field"].pop("cell_regions"),
    lambda f: f["field"].update(coordinate_frame="WORLD_CARTESIAN_MM"),
    lambda f: f["field"].update(field_unit="mm"),
    lambda f: f["field"].update(time=1., time_unit="s"),
    lambda f: f["field"]["cell_regions"].__setitem__(0, "right"),
    lambda f: f["field"]["interface"]["adjacent_cell_ids"][0].reverse(),
    lambda f: f["field"]["interface"]["node_ids"].pop(),
    lambda f: f["field"]["boundaries"]["ymin"]["left"]["prescribed_values"][0].__setitem__(0, 5.),
    lambda f: f["field"]["coordinates"][0].__setitem__(0, .01),
    lambda f: f["field"]["values"][4].__setitem__(1, True),
])
def test_rehashed_native_component_frame_tag_interface_and_trace_refusals(record_factory, mutation):
    f = record_factory()
    mutation(f)
    f["reseal"]()
    with pytest.raises(ValueError):
        f["select"]()


def test_mirrored_coefficient_and_changed_model_field_hashes_are_exact(record_factory):
    f = record_factory()
    old = f["selection"]()
    original_value = f["select"](old)["value"]
    changed = f["domain"].bind_inputs(f["settings"], {"diffusion_left_01": .25})
    assert changed["problem"]["weak_form"]["diffusion"]["left"][0][1] == changed["problem"]["weak_form"]["diffusion"]["left"][1][0] == .25
    replacement = record_factory(changed)
    assert replacement["result"]["model_revision"] != f["result"]["model_revision"]
    assert replacement["select"]()["value"] == original_value
    with pytest.raises(ValueError, match="selector/revision"):
        replacement["select"](old)
    # A changed declared coefficient cannot relabel a retained old native field.
    f["settings"]["problem"]["weak_form"]["diffusion"]["left"] = deepcopy(changed["problem"]["weak_form"]["diffusion"]["left"])
    f["reseal"]()
    with pytest.raises(ValueError, match="coefficient binding"):
        f["select"]()
    # Even a semantically finite replacement field requires its new manifest SHA.
    f = record_factory()
    old = f["selection"]()
    f["field"]["values"][4][0] = -1.
    f["reseal"]()
    with pytest.raises(ValueError, match="artifact"):
        f["select"](old)


@pytest.mark.parametrize("matrix", [[[2., .5], [.25, 1.]], [[1., 2.], [2., 1.]]])
def test_no_symmetric_mirror_or_spd_repair_is_inferred(record_factory, matrix):
    f = record_factory()
    f["settings"]["problem"]["weak_form"]["diffusion"]["left"] = matrix
    f["reseal"]()
    with pytest.raises(ValueError):
        f["select"]()


@pytest.mark.parametrize("role", ["domain_reference", "vector_worker_helper", "execution_control"])
def test_original_source_capsule_membership_and_hashes_cannot_be_substituted(record_factory, role):
    f = record_factory()
    f["detail"]["source_sha256"][role] = "e" * 64
    with pytest.raises(ValueError, match="source path/hash"):
        f["select"]()


def test_only_coupled_version_11_is_opted_in(record_factory):
    f = record_factory()
    f["result"]["provenance"]["adapter"] = "pde.fenicsx.vector"
    with pytest.raises(ValueError, match="producer"):
        f["adapter"].field_response_resources(f["result"])


def test_pure_reader_does_not_open_capsule_files_or_execute_native(record_factory, monkeypatch):
    f = record_factory()
    monkeypatch.setattr(builtins, "open", lambda *a, **k: pytest.fail("Reader opened a file"))
    monkeypatch.setattr(Path, "read_bytes", lambda *a, **k: pytest.fail("Reader reloaded current source"))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("Reader ran a process"))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("Reader started a process"))
    assert f["select"]()["value"] == -2.
    assert f["result"]["decision"] == "NOT_RELEASED"
