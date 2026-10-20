"""Regression gates for native acceptance provenance and changed-load evidence."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts import verify_structural_families as acceptance


def test_preservation_detects_ledger_changes_even_when_all_experiment_bytes_match(tmp_path):
    folder = tmp_path / "experiments/E-one"
    folder.mkdir(parents=True)
    (folder / "result.json").write_text('{"decision":"NOT_RELEASED"}')
    ledger = tmp_path / "ledger/E-one.json"
    ledger.parent.mkdir()
    ledger.write_text('{"result_sha256":"old","created_utc":"original"}')
    original = acceptance._freeze_experiment(tmp_path, "E-one")
    ledger.write_text('{"result_sha256":"old","created_utc":"changed"}')
    later = acceptance._freeze_experiment(tmp_path, "E-one")
    assert original["files"] == later["files"] and original != later


@pytest.fixture
def source(monkeypatch):
    value = {"core": {"core_commit": "a" * 40, "core_dirty": False, "core_source_sha256": "b" * 64},
             "fixture_pin": "c" * 40, "fixture": {"commit": "c" * 40, "files_sha256": "d" * 64},
             "fixture_dirty": False, "tracked_files_sha256": {"definition.json": "e" * 64}}
    monkeypatch.setattr(acceptance, "_source_snapshot", lambda: deepcopy(value))
    return value


@pytest.mark.parametrize("changed", ["head", "core_bytes", "core_dirty", "fixture_pin", "fixture_bytes", "fixture_dirty", "tracked_bytes"])
def test_source_changes_between_native_runs_refuse_acceptance(monkeypatch, source, changed):
    later = deepcopy(source)
    if changed == "head": later["core"]["core_commit"] = "f" * 40
    if changed == "core_bytes": later["core"]["core_source_sha256"] = "f" * 64
    if changed == "core_dirty": later["core"]["core_dirty"] = True
    if changed == "fixture_pin": later["fixture_pin"] = "f" * 40
    if changed == "fixture_bytes": later["fixture"]["files_sha256"] = "f" * 64
    if changed == "fixture_dirty": later["fixture_dirty"] = True
    if changed == "tracked_bytes": later["tracked_files_sha256"]["definition.json"] = "f" * 64
    monkeypatch.setattr(acceptance, "_source_snapshot", lambda: later)
    with pytest.raises(AssertionError, match="Source/HEAD/fixture"):
        acceptance._check_source(source)


@pytest.mark.parametrize("key,value", [("source_commit", "f" * 40), ("core_commit", "f" * 40),
    ("core_dirty", True), ("core_source_sha256", "f" * 64)])
def test_each_result_must_identify_the_frozen_clean_source(source, key, value):
    result = {"provenance": {"source_commit": source["core"]["core_commit"], **source["core"]}}
    result["provenance"][key] = value
    with pytest.raises(AssertionError, match="Core result source"):
        acceptance._check_source(source, result)


@pytest.fixture
def completed(monkeypatch, source, tmp_path):
    identifier = "E-roof-gravity-half-ccx"
    metrics = {"primary_response": {"value": .5, "unit": "mm", "valid": True}}
    result = {"status": "COMPLETED_REVIEW_REQUIRED", "solver_status": "COMPLETED", "converged": True,
              "decision": "NOT_RELEASED", "cad_revision": None, "model_revision": "revision-half",
              "metrics": metrics, "provenance": {"source_commit": source["core"]["core_commit"], **source["core"]}}
    summary = {"experiment_id": identifier, "metrics": deepcopy(metrics), "status": result["status"],
               "decision": result["decision"], "model_revision": result["model_revision"],
               "unknown": ["physical_validation", "model_qualification", "original_midas_replication"]}
    lab = SimpleNamespace(inspect_experiment=lambda _: result, research_summary=lambda _: summary)
    raw = [{"actual_native_fields": "retained"}]
    path = tmp_path / "experiments" / identifier / "simulation/mesh_records.json"
    path.parent.mkdir(parents=True)
    path.write_text("[]")
    monkeypatch.setattr(acceptance, "load_json", lambda _: raw)
    monkeypatch.setattr(acceptance, "assess", lambda *_: {"metrics": deepcopy(metrics)})
    return identifier, lab, result, summary, raw


def test_changed_load_uses_checked_raw_observations_and_unknown_qualification(tmp_path, source, completed):
    identifier, lab, result, summary, raw = completed
    assert acceptance._checked_completed(lab, tmp_path, identifier, {}, result, source) == (summary, raw)


@pytest.mark.parametrize("failure", ["invalid_response", "raw_mismatch", "solver_not_completed",
    "not_converged", "lost_unknown", "summary_mismatch"])
def test_changed_load_cannot_pass_with_half_sized_but_unverified_feedback(monkeypatch, tmp_path, source, completed, failure):
    identifier, lab, result, summary, _ = completed
    if failure == "invalid_response":
        result["metrics"]["primary_response"]["valid"] = False
        summary["metrics"] = deepcopy(result["metrics"])
    if failure == "raw_mismatch": monkeypatch.setattr(acceptance, "assess", lambda *_: {"metrics": {}})
    if failure == "solver_not_completed": result["solver_status"] = "NOT_RUN"
    if failure == "not_converged": result["converged"] = False
    if failure == "lost_unknown": summary["unknown"].remove("original_midas_replication")
    if failure == "summary_mismatch": summary["model_revision"] = "wrong-revision"
    with pytest.raises(AssertionError):
        acceptance._checked_completed(lab, tmp_path, identifier, {}, result, source)


@pytest.mark.parametrize("status,solver_status,converged", [
    ("FAILED_EXECUTION", "FAILED", False),
    ("FAILED_EXECUTION", "COMPLETED", None),
    ("REJECTED", "COMPLETED", True),
])
def test_native_failure_identifies_actual_states_observations_and_result_path(
        tmp_path, source, completed, status, solver_status, converged):
    identifier, lab, result, _, _ = completed
    failed = {"code": "native_check", "status": "FAIL", "observed": 0.125,
              "limit": 0.01, "expected": "complete native fields"}
    result.update(status=status, solver_status=solver_status, converged=converged,
                  evidence=[{"observation": failed},
                            {"observation": {"code": "passing_check", "status": "PASS"}}])
    original = deepcopy(result)
    with pytest.raises(AssertionError) as error:
        acceptance._checked_completed(lab, tmp_path, identifier, {}, result, source)
    message = str(error.value)
    assert identifier in message
    for key in ("status", "solver_status", "converged"):
        assert f"{key}={result[key]!r}" in message
    assert repr(failed) in message
    assert "passing_check" not in message
    assert str(tmp_path / "experiments" / identifier / "result.json") in message
    assert result == original


def test_failed_numerical_checks_keep_comparison_values_and_failures(
        monkeypatch, tmp_path, source, completed, capsys):
    identifier, lab, result, summary, raw = completed
    settings = acceptance.specification("ansys_vmd1_regular", "Fz")
    result["status"] = summary["status"] = "REJECTED"
    result["metrics"]["primary_response"]["valid"] = False
    summary["metrics"] = deepcopy(result["metrics"])
    failed = {"code": "signed_moment_balance", "status": "FAIL", "observed": 0.0002, "limit": 1e-7}
    result["evidence"] = [{"observation": failed}]
    assessment = {"metrics": deepcopy(result["metrics"]), "checks": [failed],
                  "reference": acceptance.model_declaration(settings)["reference"],
                  "mesh_studies": [{"primary_response_mm": .5, "reference_relative_error": .01,
                                    "reaction_relative_error": .0002, "moment_relative_error": .0002}]}
    monkeypatch.setattr(acceptance, "assess", lambda *_: deepcopy(assessment))
    comparison = {}
    original = deepcopy(result)
    with pytest.raises(acceptance._NumericalFailure) as error:
        acceptance._checked_completed(lab, tmp_path, identifier, settings, result, source, comparison)
    assert error.value.raw == raw
    assert comparison["assessment"] == assessment
    assert comparison["reference"]["units"]["response"] == "mm"
    assert comparison["failed_observations"] == [failed]
    assert comparison["status"] == "REJECTED" and comparison["missing_fields"] == []
    assert comparison["assessment"]["metrics"]["primary_response"]["valid"] is False
    assert '"signed_moment_balance"' in capsys.readouterr().out
    assert result == original


def test_execution_failure_explicitly_reports_missing_comparison_fields(tmp_path, source, completed, capsys):
    identifier, lab, result, summary, _ = completed
    result.update(status="FAILED_EXECUTION", solver_status="FAILED_EXECUTION", converged=None)
    summary["status"] = result["status"]
    summary["unknown"] = ["model_qualification", "physical_validation"]
    result["metrics"] = summary["metrics"] = {}
    result["evidence"] = [{"observation": {"code": "model_analysis_execution", "status": "FAIL",
        "observed": "RuntimeError: Native input/source mesh identity drifted"}}]
    comparison = {}
    with pytest.raises(acceptance._NumericalFailure) as error:
        acceptance._checked_completed(lab, tmp_path, identifier,
            acceptance.specification("ansys_vmd1_regular", "Fx"), result, source, comparison)
    assert error.value.raw is None
    assert "Native input/source mesh identity drifted" in str(error.value)
    assert comparison["assessment"] is None
    assert comparison["missing_fields"] == ["complete_native_fields", "mesh_studies"]
    assert comparison["status"] == "FAILED_EXECUTION" and comparison["solver_status"] == "FAILED_EXECUTION"
    assert '"assessment": null' in capsys.readouterr().out


@pytest.mark.parametrize("failed_status", ["REJECTED", "FAILED_EXECUTION", "CANCELLED"])
def test_independent_cases_continue_and_original_failure_still_fails_run(
        monkeypatch, tmp_path, source, failed_status):
    """Synthetic orchestration only; no native solver or physical result is produced."""
    from caelab.storage import load_json, save_json
    records, calls = {}, []
    first_failure = "E-ansys_vmd1_regular-Fx-ccx"

    def metrics(factor, failed):
        return {"primary_response": {"value": factor, "unit": "mm", "valid": not failed}}

    def summary(identifier):
        result = records[identifier]
        return {"experiment_id": identifier, **{key: deepcopy(result[key]) for key in
            ("metrics", "status", "decision", "model_revision")},
            "unknown": ["model_qualification", "physical_validation"]
                if result["solver_status"] in {"FAILED_EXECUTION", "CANCELLED"}
                else ["physical_validation", "model_qualification", "original_midas_replication"]}

    def run_model_analysis(**arguments):
        identifier, settings = arguments["experiment_id"], arguments["settings"]
        calls.append(identifier)
        refused, failed = identifier.startswith("E-refused"), identifier == first_failure
        unreadable = failed and failed_status in {"FAILED_EXECUTION", "CANCELLED"}
        result = {"status": failed_status if failed else "REJECTED" if refused else "COMPLETED_REVIEW_REQUIRED",
            "solver_status": failed_status if unreadable else "NOT_RUN" if refused else "COMPLETED",
            "converged": None if refused or unreadable else True,
            "decision": "NOT_RELEASED", "cad_revision": None,
            "model_revision": str((settings["case"], settings["load_case"], settings["load_factor"])),
            "metrics": {} if refused or unreadable else metrics(settings["load_factor"], failed),
            "evidence": [{"observation": {"code": "model_analysis_execution", "status": "FAIL",
                "observed": "RuntimeError: Native input/source mesh identity drifted"}}] if failed else [],
            "provenance": {"source_commit": source["core"]["core_commit"], **source["core"]}}
        records[identifier] = result
        folder = store / "experiments" / identifier
        save_json(folder / "result.json", result)
        save_json(store / "ledger" / (identifier + ".json"), {"synthetic_not_solved": True})
        if not refused and not unreadable:
            save_json(folder / "simulation/mesh_records.json",
                      [{"synthetic_not_solved": True, "factor": settings["load_factor"], "failed": failed}])
        return result

    lab = SimpleNamespace(create_study=lambda *_: None, run_model_analysis=run_model_analysis,
                          research_summary=summary, inspect_experiment=lambda identifier: records[identifier])
    monkeypatch.setattr(acceptance, "Lab", lambda _: lab)
    monkeypatch.setattr(acceptance.subprocess, "check_output",
        lambda arguments, **_: source["core"]["core_commit"] + "\n" if arguments[-1] == "HEAD" else "")
    monkeypatch.setattr(acceptance, "assess", lambda settings, raw: {
        "metrics": metrics(raw[0]["factor"], raw[0]["failed"]), "checks": [],
        "reference": acceptance.model_declaration(settings)["reference"], "mesh_studies": []})
    monkeypatch.setattr(acceptance, "_cross_fields", lambda *_: {
        "status": "PASS", "levels": [{"displacement_field_relative_error": 0.0}]})
    store = tmp_path / "synthetic-run"
    with pytest.raises(AssertionError, match="Native comparisons retained failures"):
        acceptance.run(store, source["core"]["core_commit"])
    report = load_json(store / "acceptance.json")
    assert first_failure in calls and "E-scordelis_lo_solid-gravity-aster" in calls
    assert len(report["cross_solver"]) == len(acceptance.CASES)
    failed_entry = next(row for row in report["experiments"] if row["experiment_id"] == first_failure)
    assert failed_entry["status"] == failed_status
    if failed_status == "REJECTED":
        assert failed_entry["numerical_comparison"]["assessment"]["metrics"]["primary_response"]["valid"] is False
    else:
        assert failed_entry["numerical_comparison"]["assessment"] is None
        assert failed_entry["numerical_comparison"]["missing_fields"]
        assert report["cross_solver"][0]["status"] == "NOT_COMPARED"
    assert report["failures"][0]["experiment_id"] == first_failure
    assert "Native input/source mesh identity drifted" in report["failures"][0]["message"]
    assert report["status"] == "FAILED_OR_PARTIAL"


@pytest.mark.parametrize("failed_status", ["FAILED_EXECUTION", "CANCELLED"])
def test_actual_lab_failure_summary_remains_collectable_without_completed_qualification(
        monkeypatch, tmp_path, source, failed_status):
    from caelab import Lab
    from caelab.execution_control import ExecutionCancelled

    def fail(output, settings):
        if failed_status == "CANCELLED":
            raise ExecutionCancelled("test-only cancellation; no native solve")
        raise RuntimeError("test-only execution failure; no native solve")

    adapter = SimpleNamespace(backend="test.structural.failure", version="test-only",
        domain="structure", physics_domain="solid_mechanics", analysis_type="linear_static",
        default_metrics=["primary_response"], describe_model=acceptance.model_declaration, solve=fail)
    monkeypatch.setattr("caelab.declared_model.source_identity", lambda *_: deepcopy(source["core"]))
    lab = Lab(tmp_path / "actual-lab", model_analysis_adapters={adapter.backend: adapter})
    lab.create_study("S-failure", "Test-only failure record", "Does failure retain its actual summary?",
                     "A failed solve has no completed numerical qualification", "No native solver is used")
    settings = acceptance.specification("ansys_vmd1_regular", "Fz")
    identifier = "E-test-failure"
    result = lab.run_model_analysis(study_id="S-failure", experiment_id=identifier,
                                   backend=adapter.backend, settings=settings)
    summary = lab.research_summary(identifier)
    assert result["status"] == summary["status"] == failed_status
    assert summary["metrics"] == {}
    assert set(summary["unknown"]) == {"model_qualification", "physical_validation"}
    comparison = {}
    with pytest.raises(acceptance._NumericalFailure, match=failed_status) as error:
        acceptance._checked_completed(lab, lab.store, identifier, settings, result, source, comparison)
    assert error.value.raw is None
    assert comparison["status"] == comparison["solver_status"] == failed_status
    assert comparison["assessment"] is None and comparison["missing_fields"]
    assert lab.inspect_experiment(identifier) == result
