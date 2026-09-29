"""Seeded numerical proposals, immutable lineage and invalid-CAD solver gate."""

import json
from pathlib import Path

import pytest

from caelab import Lab
from caelab.storage import save_json


class CountingAnalysis:
    backend = "test.analysis"
    version = "1"
    analysis_type = "linear_static"
    default_metrics = ["test_displacement"]

    def __init__(self):
        self.calls = 0

    def solve(self, parent_result, parent_root, output, settings):
        self.calls += 1
        output.mkdir(parents=True)
        answer = {"status": "COMPLETED", "checks": [{"code": "numerical_test", "status": "PASS"}],
                  "metrics": {"test_displacement": {"value": 0.01, "unit": "mm", "valid": True}},
                  "solver_status": "COMPLETED", "converged": True,
                  "pending_validations": ["static_strength"], "provenance": {},
                  "raw_result": "simulation/result.json"}
        save_json(output / "result.json", answer)
        return answer


def _lab(tmp_path: Path, analysis=None):
    lab = Lab(tmp_path, analysis_adapters={CountingAnalysis.backend: analysis or CountingAnalysis()})
    lab.create_study("S-doe", "Fixture exploration", "Which pitch values obey CAD rules?",
                     "Some sampled values are invalid", "Keep CAD and numerical evidence")
    lab.register_parameter("S-doe", "fixture.cadquery", "roller_support",
                           "bolt_pitch_x_mm", "bolt_pitch", "Bolt pitch", 18, 40)
    return lab


def _plan(lab):
    return lab.plan_doe(study_id="S-doe", campaign_id="C-pitch", backend="fixture.cadquery",
                        model="roller_support", parameter_ids=["bolt_pitch"],
                        sample_count=2, seed=13, analysis_backend="test.analysis",
                        analysis_settings={"load": {"force_N": 100}})


def test_seeded_plan_invalid_cad_skips_solver_and_replay_is_verified(tmp_path):
    adapter = CountingAnalysis()
    lab = _lab(tmp_path, adapter)
    plan = _plan(lab)
    second = _plan(_lab(tmp_path / "independent"))
    assert [v["values"] for v in plan["samples"]] == [v["values"] for v in second["samples"]]
    assert plan["algorithm"]["seed"] == 13
    assert lab.inspect_doe("C-pitch")["status"] == "PLANNED"
    result = lab.run_doe("C-pitch")
    assert adapter.calls == 1
    assert [(v["cad_status"], v["analysis_status"]) for v in result["samples"]] == [
        ("COMPLETED_REVIEW_REQUIRED", "COMPLETED_REVIEW_REQUIRED"),
        ("REJECTED", "SKIPPED_CAD_REJECTED")]
    assert result["decision"] == "NOT_RELEASED"
    assert result["samples"][0]["analysis_experiment_id"] == "E-C-pitch-001-solve"
    assert result["samples"][1]["analysis_experiment_id"] is None
    assert not (tmp_path / "experiments/E-C-pitch-002-solve").exists()
    assert lab.inspect_experiment("E-C-pitch-001-solve")["campaign_id"] == "C-pitch"
    assert lab.inspect_doe("C-pitch") == result
    assert lab.run_doe("C-pitch") == result and adapter.calls == 1
    journal = tmp_path / "campaigns/C-pitch/journal/001.json"
    journal.write_text(journal.read_text().replace("0.01", "0.02"))
    with pytest.raises(ValueError, match="journal hash"):
        lab.inspect_doe("C-pitch")


def test_campaign_resumes_only_verified_previous_samples(tmp_path):
    lab = _lab(tmp_path)
    _plan(lab)
    original_run = lab.run_experiment

    def interrupt(*args, **kwargs):
        if kwargs["experiment_id"] == "E-C-pitch-002":
            raise RuntimeError("Interrupted after first sample")
        return original_run(*args, **kwargs)

    lab.run_experiment = interrupt
    with pytest.raises(RuntimeError, match="Interrupted"):
        lab.run_doe("C-pitch")
    prior = (tmp_path / "experiments/E-C-pitch-001/result.json").read_bytes()
    assert lab.inspect_doe("C-pitch")["completed_samples"] == 1
    journal = tmp_path / "campaigns/C-pitch/journal/001.json"
    original_journal = journal.read_bytes()
    journal.write_text('{"index": 1, "fake": true}')
    with pytest.raises(ValueError, match="journal"):
        lab.inspect_doe("C-pitch")
    journal.write_bytes(original_journal)
    lab.run_experiment = original_run
    resumed = lab.run_doe("C-pitch")
    assert (tmp_path / "experiments/E-C-pitch-001/result.json").read_bytes() == prior
    assert len(resumed["samples"]) == 2


def test_registry_change_blocks_campaign_before_new_runs(tmp_path):
    lab = _lab(tmp_path)
    _plan(lab)
    lab.register_parameter("S-doe", "fixture.cadquery", "roller_support",
                           "support_width_mm", "support_width", "Support width", 28, 60)
    with pytest.raises(ValueError, match="registry changed"):
        lab.run_doe("C-pitch")
    assert not (tmp_path / "experiments/E-C-pitch-001").exists()


def test_tampered_plan_is_detected(tmp_path):
    lab = _lab(tmp_path)
    _plan(lab)
    path = tmp_path / "campaigns/C-pitch/plan.json"
    plan = json.loads(path.read_text())
    plan["samples"][0]["values"]["bolt_pitch"] = 31
    save_json(path, plan)
    with pytest.raises(ValueError, match="plan or registry snapshot hash"):
        lab.run_doe("C-pitch")


def test_resume_rejects_unplanned_settings_even_with_matching_values(tmp_path):
    lab = _lab(tmp_path)
    plan = _plan(lab)
    item = plan["samples"][0]
    lab.run_experiment(study_id="S-doe", experiment_id=item["cad_experiment_id"],
                       backend="fixture.cadquery", model="roller_support",
                       values=item["values"], campaign_id="C-pitch",
                       settings={"random_seed": 999, "unplanned": True})
    with pytest.raises(ValueError, match="execution settings differ"):
        lab.run_doe("C-pitch")
    assert not (tmp_path / "experiments/E-C-pitch-001-solve").exists()


def test_cad_execution_failure_is_not_labeled_invalid_design(tmp_path, monkeypatch):
    lab = _lab(tmp_path)
    _plan(lab)

    def fail(*args, **kwargs):
        raise RuntimeError("CAD process crashed")

    monkeypatch.setattr(lab.adapters["fixture.cadquery"], "regenerate", fail)
    result = lab.run_doe("C-pitch")
    assert [s["cad_status"] for s in result["samples"]] == ["FAILED_EXECUTION"] * 2
    assert [s["analysis_status"] for s in result["samples"]] == [
        "SKIPPED_CAD_FAILED_EXECUTION"] * 2
    assert not (tmp_path / "experiments/E-C-pitch-001-solve").exists()
