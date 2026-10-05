"""Preflight tests use real CadQuery STEP, never synthetic solver success."""

import hashlib
import json
from pathlib import Path

import pytest

from caelab.adapters.fixture_cadquery import FixtureCadQueryAdapter
from caelab.adapters.fixture_calculix import (FixtureCalculiXAdapter, UPSTREAM,
                                              _base_reactions, _finite_displacement_table,
                                              _request_base_reactions, _apply_saddle_forces,
                                              _per_mesh_responses)
from caelab.outcomes import validate_outcome
from caelab.storage import artifact_manifest


def parent(tmp_path: Path, *, roller_diameter: float = 8.3):
    root = tmp_path / "parent"
    cad = root / "cad"
    fixture = FixtureCadQueryAdapter()
    result = fixture.regenerate("roller_support",
                                {"support_width_mm": 38,
                                 "roller_diameter_mm": roller_diameter}, cad)
    assert result.generated
    revision = "a" * 64
    return root, {"experiment_id": "E-parent", "status": "COMPLETED_REVIEW_REQUIRED",
                  "decision": "NOT_RELEASED", "cad_revision": revision,
                  "provenance": {"adapter": "fixture.cadquery"},
                  "artifacts": artifact_manifest(root, revision=revision)}


def settings():
    material = json.loads((UPSTREAM / "examples/printed_material_ASSUMED.json").read_text())
    return {"load": {"force_per_support_N": 100.0, "source": "test load: unqualified"},
            "material": material, "mesh": {"max_sizes_mm": [4, 3, 2]}}


def test_verified_step_preflight_reaches_executable_gate(tmp_path, monkeypatch):
    root, result = parent(tmp_path)
    monkeypatch.setattr("caelab.adapters.fixture_calculix.shutil.which", lambda _: None)
    out = tmp_path / "analysis"
    with pytest.raises(RuntimeError, match="Missing open-source executable: gmsh"):
        FixtureCalculiXAdapter().solve(result, root, out, settings())
    assert not (out / "input.step").exists()


def test_tampered_parent_step_rejected_before_meshing(tmp_path):
    root, result = parent(tmp_path)
    with (root / "cad/assembly.step").open("ab") as stream:
        stream.write(b"\nmodified")
    out = tmp_path / "analysis"
    response = FixtureCalculiXAdapter().solve(result, root, out, settings())
    assert response["status"] == "REJECTED"
    assert response["checks"][-1]["code"] == "cad_artifact_integrity"
    assert response["solver_status"] == "NOT_RUN"
    assert list(out.iterdir()) == [out / "result.json"]


def test_unsupported_saddle_and_load_are_rejected(tmp_path):
    root, result = parent(tmp_path, roller_diameter=9.0)
    out = tmp_path / "analysis"
    rejected = FixtureCalculiXAdapter().solve(result, root, out, settings())
    assert rejected["status"] == "REJECTED"
    assert rejected["checks"][-1]["code"] == "saddle_boundary_compatibility"
    assert not (out / "input.step").exists()

    root2, result2 = parent(tmp_path / "second")
    invalid = settings()
    invalid["load"]["force_per_support_N"] = 0
    rejected = FixtureCalculiXAdapter().solve(result2, root2, tmp_path / "invalid", invalid)
    assert rejected["checks"][-1]["code"] == "load_definition"


def test_displacement_table_rejects_nonfinite_nonextreme_node(tmp_path):
    dat = tmp_path / "solver.dat"
    dat.write_text("displacements (vx,vy,vz)\n"
                   "1 0.0 0.0 -1.0\n"
                   "2 0.0 NaN -0.5\n"
                   "3 0.0 0.0 -1.1\n")
    with pytest.raises(RuntimeError, match="Nonfinite loaded-node displacement: 2"):
        _finite_displacement_table(dat, {1, 2, 3})
    dat.write_text("displacements (vx,vy,vz)\n"
                   "1 0.0 0.0 -1.0\n"
                   "2 0.0 0.0 -0.5\n"
                   "3 0.0 0.0 -1.1\n")
    _finite_displacement_table(dat, {1, 2, 3})


def test_fixed_reaction_table_checks_signed_balance_and_completeness(tmp_path):
    dat = tmp_path / "solver.dat"
    dat.write_text("displacements (vx,vy,vz) for set ROLLER_NODES\n"
                   "3 0 0 -0.01\n\n"
                   "forces (fx,fy,fz) for set BASE_FIXED and time  0.1000000E+01\n\n"
                   "1 1.0 0.0 30.0\n"
                   "2 -1.0 0.0 70.0\n\n")
    reaction = _base_reactions(dat, {1, 2}, 100.0)
    assert reaction["reaction_force_N"] == [0.0, 0.0, 100.0]
    assert reaction["relative_imbalance"] == 0
    original = dat.read_text()
    dat.write_text(original.replace("70.0", "-70.0"))
    assert _base_reactions(dat, {1, 2}, 100.0)["relative_imbalance"] > 1
    dat.write_text(original.replace("2 -1.0 0.0 70.0", ""))
    with pytest.raises(RuntimeError, match="Incomplete fixed-node reactions"):
        _base_reactions(dat, {1, 2}, 100.0)
    dat.write_text(original.replace("2 -1.0 0.0 70.0", "2 -1.0 NaN 70.0"))
    with pytest.raises(RuntimeError, match="Nonfinite fixed-node reaction"):
        _base_reactions(dat, {1, 2}, 100.0)


def test_reaction_request_preserves_the_existing_step(tmp_path):
    deck = tmp_path / "support.inp"
    deck.write_text("*STEP\n*STATIC\n*NODE PRINT, NSET=ROLLER_NODES\nU\n*END STEP\n")
    _request_base_reactions(deck)
    assert deck.read_text().endswith("*NODE PRINT, NSET=ROLLER_NODES\nU\n"
                                     "*NODE PRINT, NSET=BASE_FIXED\nRF\n*END STEP\n")


def test_area_load_replaces_only_saddle_set_and_forces(tmp_path):
    deck = tmp_path / "support.inp"
    deck.write_text("*NSET, NSET=BASE_FIXED\n10\n"
                    "*NSET, NSET=ROLLER_NODES\n1, 2\n"
                    "*MATERIAL, NAME=PRINT_INPUT\n*ELASTIC\n100, 0.3\n"
                    "*STEP\n*STATIC\n*BOUNDARY\nBASE_FIXED, 1, 3\n"
                    "*CLOAD\n1, 3, -50\n2, 3, -50\n"
                    "*NODE PRINT, NSET=ROLLER_NODES\nU\n*END STEP\n")
    _apply_saddle_forces(deck, {1: -20.0, 2: -30.0, 3: -50.0}, 2)
    text = deck.read_text()
    assert "*NSET, NSET=BASE_FIXED\n10\n" in text
    assert "*NSET, NSET=ROLLER_NODES\n1, 2, 3\n" in text
    assert "*CLOAD\n1, 3, -20\n2, 3, -30\n3, 3, -50\n" in text
    assert "*MATERIAL, NAME=PRINT_INPUT\n*ELASTIC\n100, 0.3\n" in text
    deck.write_text(text.replace("*CLOAD\n", "*DLOAD\n"))
    with pytest.raises(RuntimeError, match="Unexpected solver deck structure"):
        _apply_saddle_forces(deck, {1: -100.0}, 2)


def test_area_load_keeps_small_forces_within_calculix_field_width(tmp_path):
    deck = tmp_path / "support.inp"
    deck.write_text("*NSET, NSET=ROLLER_NODES\n1\n"
                    "*MATERIAL, NAME=PRINT_INPUT\n*STEP\n*CLOAD\n1, 3, -100\n"
                    "*NODE PRINT, NSET=ROLLER_NODES\nU\n*END STEP\n")
    forces = {1: -99.99994951471318, 2: -5.048528681584956e-05}
    _apply_saddle_forces(deck, forces, 1)
    fields = [line.split(",")[-1].strip() for line in
              deck.read_text().split("*CLOAD\n")[1].split("*NODE PRINT")[0].splitlines()]
    assert max(map(len, fields)) <= 20
    assert sum(map(float, fields)) == pytest.approx(sum(forces.values()), abs=1e-8)


def _per_mesh_response_fixture(output):
    """Controlled DAT bytes only; no geometry, native solve or scientific approval."""
    observations = [(4, -0.00564208), (3, -0.005730928), (2, -0.005827884)]
    studies = []
    for index, (size, uz) in enumerate(observations):
        folder = output / f"support_{index}"
        folder.mkdir(parents=True)
        dat = folder / f"support_{index}.dat"
        dat.write_bytes(f"TEST ONLY: native-looking DAT fixture {index}\n".encode())
        studies.append({"mesh_size_max_mm": size,
                        "displacement": {"min_vertical_displacement_mm": uz},
                        "boundary": {"loaded_node_count": 2, "loaded_node_ids": [2, 7]},
                        "files": {"displacement_table": f"support_{index}/support_{index}.dat"}})
    return studies


def test_per_mesh_response_preserves_order_sign_scope_and_evidence(tmp_path):
    studies = _per_mesh_response_fixture(tmp_path)
    before = json.dumps(studies, sort_keys=True)
    metrics, evidence = _per_mesh_responses(studies, tmp_path, True)
    assert metrics == {
        "mesh_size_max_mm": {"value": [4, 3, 2], "unit": "mm", "valid": True},
        "loaded_saddle_min_global_uz": {"value": [-0.00564208, -0.005730928, -0.005827884], "unit": "mm", "valid": True},
    }
    assert (evidence["node_set"], evidence["coordinate_system"], evidence["component"], evidence["statistic"]) == (
        "ROLLER_NODES", "global Cartesian", "UZ", "minimum over loaded saddle nodes")
    assert evidence["source_result"] == "simulation/result.json"
    assert evidence["mesh_metric"] == "mesh_size_max_mm" and evidence["response_metric"] == "loaded_saddle_min_global_uz"
    manifest = {entry["path"]: entry for entry in artifact_manifest(tmp_path, revision="a" * 64)}
    for index, row in enumerate(evidence["studies"]):
        relative = f"support_{index}/support_{index}.dat"
        assert row == {"index": index, "mesh_size_max_mm": [4, 3, 2][index], "loaded_node_count": 2,
                       "displacement_table": "simulation/" + relative,
                       "displacement_table_sha256": hashlib.sha256((tmp_path / relative).read_bytes()).hexdigest()}
        assert row["displacement_table_sha256"] == manifest[relative]["sha256"]
    assert json.dumps(studies, sort_keys=True) == before
    assert FixtureCalculiXAdapter.version == "6"
    assert FixtureCalculiXAdapter.default_metrics == ["max_displacement", "peak_stress", "displacement_mesh_change_ratio",
        "applied_force_per_support", "reaction_force", "reaction_balance_ratio", "mesh_size_max_mm", "loaded_saddle_min_global_uz"]


def test_per_mesh_response_retains_finite_failed_trend_in_common_outcome(tmp_path):
    studies = _per_mesh_response_fixture(tmp_path)
    metrics, evidence = _per_mesh_responses(studies, tmp_path, False)
    assert metrics["mesh_size_max_mm"] == {"value": [4, 3, 2], "unit": "mm", "valid": True}
    assert metrics["loaded_saddle_min_global_uz"] == {"value": [-0.00564208, -0.005730928, -0.005827884],
        "unit": "mm", "valid": False, "reason": "Declared mesh trend threshold exceeded"}
    # A rejected controlled outcome verifies the existing numeric-list boundary,
    # without representing a completed native execution or engineering approval.
    outcome = {"status": "REJECTED", "checks": [{"code": "displacement_mesh_trend", "status": "FAIL"}],
               "metrics": metrics, "provenance": {"per_mesh_displacement": evidence},
               "solver_status": "NOT_RUN", "converged": None, "pending_validations": ["static_strength"]}
    before = json.dumps(outcome, sort_keys=True)
    validate_outcome(outcome)
    assert json.dumps(outcome, sort_keys=True) == before


@pytest.mark.parametrize("fault", ["missing", "nonfinite", "boolean", "order", "missing_dat", "foreign_dat", "count", "duplicate_ids", "trend"])
def test_per_mesh_response_rejects_unavailable_or_misassociated_observations(tmp_path, fault):
    studies = _per_mesh_response_fixture(tmp_path)
    passed = True
    if fault == "missing":
        studies[1]["displacement"] = {}
    elif fault == "nonfinite":
        studies[1]["displacement"]["min_vertical_displacement_mm"] = float("nan")
    elif fault == "boolean":
        studies[1]["displacement"]["min_vertical_displacement_mm"] = True
    elif fault == "order":
        studies[1]["mesh_size_max_mm"] = 4
    elif fault == "missing_dat":
        (tmp_path / "support_1/support_1.dat").unlink()
    elif fault == "foreign_dat":
        studies[1]["files"]["displacement_table"] = "../foreign.dat"
    elif fault == "count":
        studies[1]["boundary"]["loaded_node_count"] = True
    elif fault == "duplicate_ids":
        studies[1]["boundary"]["loaded_node_ids"] = [2, 2]
    elif fault == "trend":
        passed = 1
    with pytest.raises(ValueError, match="per-mesh"):
        _per_mesh_responses(studies, tmp_path, passed)


def test_explicit_selected_response_retains_signed_observation_and_dat_binding(tmp_path):
    study = _per_mesh_response_fixture(tmp_path)[:1]
    before = json.dumps(study, sort_keys=True)
    metrics, provenance = _per_mesh_responses(study, tmp_path, None, selected_mesh=True)
    assert metrics == {"mesh_size_max_mm": {"value": [4], "unit": "mm", "valid": True},
        "loaded_saddle_min_global_uz": {"value": [-.00564208], "unit": "mm", "valid": True,
            "reason": "Observed on selected mesh; mesh sensitivity unassessed"}}
    assert provenance["node_set"] == "ROLLER_NODES" and provenance["component"] == "UZ"
    assert provenance["statistic"] == "minimum over loaded saddle nodes"
    assert provenance["coordinate_system"] == "global Cartesian" and provenance["unit"] == "mm"
    assert provenance["studies"] == [{"index": 0, "mesh_size_max_mm": 4, "loaded_node_count": 2,
        "displacement_table": "simulation/support_0/support_0.dat",
        "displacement_table_sha256": hashlib.sha256((tmp_path / "support_0/support_0.dat").read_bytes()).hexdigest()}]
    assert json.dumps(study, sort_keys=True) == before


@pytest.mark.parametrize("count,verdict,selected", [(1, True, False), (1, False, False), (1, None, False),
    (1, True, True), (1, False, True), (0, None, True), (2, None, True), (3, None, True), (1, None, 1)])
def test_single_response_requires_opt_in_and_unassessed_verdict(tmp_path, count, verdict, selected):
    studies = _per_mesh_response_fixture(tmp_path)[:count]
    with pytest.raises(ValueError, match="per-mesh"):
        _per_mesh_responses(studies, tmp_path, verdict, selected_mesh=selected)


@pytest.mark.parametrize("fault", ["missing", "nonfinite", "boolean", "missing_dat", "foreign_dat", "count", "duplicate_ids"])
def test_selected_response_keeps_existing_numeric_node_and_source_guards(tmp_path, fault):
    study = _per_mesh_response_fixture(tmp_path)[:1]
    if fault == "missing":
        study[0]["displacement"] = {}
    elif fault in ("nonfinite", "boolean"):
        study[0]["displacement"]["min_vertical_displacement_mm"] = float("nan") if fault == "nonfinite" else True
    elif fault == "missing_dat":
        (tmp_path / "support_0/support_0.dat").unlink()
    elif fault == "foreign_dat":
        study[0]["files"]["displacement_table"] = "support_1/support_1.dat"
    elif fault == "count":
        study[0]["boundary"]["loaded_node_count"] = 1
    elif fault == "duplicate_ids":
        study[0]["boundary"]["loaded_node_ids"] = [2, 2]
    with pytest.raises(ValueError, match="per-mesh"):
        _per_mesh_responses(study, tmp_path, None, selected_mesh=True)


@pytest.fixture(scope="module")
def mesh_policy_parent(tmp_path_factory):
    return parent(tmp_path_factory.mktemp("TEST_ONLY-mesh-policy-parent"))


@pytest.mark.parametrize("mesh", [{"max_sizes_mm": [3]}, {"max_sizes_mm": []},
    {"max_sizes_mm": [3, 3]}, {"max_sizes_mm": [2, 3]}, {"max_sizes_mm": list(range(9, 0, -1))},
    {"mode": "selected", "max_sizes_mm": [3, 2]}, {"mode": "selected", "max_sizes_mm": []},
    {"mode": "selected", "max_sizes_mm": [0]}, {"mode": "selected", "max_sizes_mm": [-1]},
    {"mode": "selected", "max_sizes_mm": [True]}, {"mode": "selected", "max_sizes_mm": [float("nan")]},
    {"mode": "selected", "max_sizes_mm": [float("inf")]}, {"mode": "selected", "max_sizes_mm": [10 ** 400]},
    {"mode": "selected", "max_sizes_mm": [None]},
    {"mode": "selected", "max_sizes_mm": ["3"]}, {"mode": "selected", "max_sizes_mm": 3},
    {"mode": "selected"}, {"mode": "selected", "max_sizes_mm": [3], "extra": 1},
    {"mode": "refinement", "max_sizes_mm": [3, 2]}, {"mode": "unknown", "max_sizes_mm": [3]},
    {"mode": "", "max_sizes_mm": [3]}, {"mode": None, "max_sizes_mm": [3]},
    {"mode": True, "max_sizes_mm": [3]}, {"mode": 1, "max_sizes_mm": [3]},
    {"mode": float("nan"), "max_sizes_mm": [3]}, {"mode": ["selected"], "max_sizes_mm": [3]}, None])
def test_unsupported_mesh_requests_are_rejected_before_native_or_mesh(tmp_path, monkeypatch, mesh_policy_parent, mesh):
    root, result = mesh_policy_parent
    def prohibited(*_args, **_kwargs):
        pytest.fail("Rejected mesh request reached executable/native gate")
    monkeypatch.setattr("caelab.adapters.fixture_calculix.shutil.which", prohibited)
    monkeypatch.setattr("caelab.adapters.fixture_calculix.subprocess.run", prohibited)
    configuration = settings()
    configuration["mesh"] = mesh
    output = tmp_path / "rejected"
    response = FixtureCalculiXAdapter().solve(result, root, output, configuration)
    assert response["status"] == "REJECTED" and response["solver_status"] == "NOT_RUN"
    assert response["checks"][-1]["code"] == "mesh_settings"
    assert response["provenance"]["adapter_version"] == "6"
    assert list(output.iterdir()) == [output / "result.json"]


def test_selected_single_mesh_reaches_existing_executable_gate(tmp_path, monkeypatch, mesh_policy_parent):
    root, result = mesh_policy_parent
    monkeypatch.setattr("caelab.adapters.fixture_calculix.shutil.which", lambda _: None)
    configuration = settings()
    configuration["mesh"] = {"mode": "selected", "max_sizes_mm": [3]}
    output = tmp_path / "selected"
    with pytest.raises(RuntimeError, match="Missing open-source executable: gmsh"):
        FixtureCalculiXAdapter().solve(result, root, output, configuration)
    assert not (output / "input.step").exists()
