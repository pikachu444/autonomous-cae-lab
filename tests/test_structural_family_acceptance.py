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
def completed(monkeypatch, source):
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
