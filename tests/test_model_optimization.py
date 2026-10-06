"""Real SciPy numerical feedback/replay with TEST ONLY model observations.

The synthetic adapter executes no native solver and makes no physics claim.
All stores are per-test temporary stores; no historical experiment is reused.
"""

from collections import Counter
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from caelab import optimization
from caelab.model_parameters import ModelInputRejected, bind
from caelab.schema import validate as validate_schema
from caelab.storage import artifact_manifest, canonical_hash, load_json, save_json
from test_model_parameters import (STUDY, InteriorMalformedModel, SyntheticParameterizedModel, register_x,
                                   synthetic_lab, template_settings)


CAMPAIGN = "C-model-search"
ENGINE = "scipy.differential_evolution"


def _lab(path, adapter=None):
    lab, adapter = synthetic_lab(path, adapter)
    register_x(lab)
    lab.register_model_parameter(STUDY, adapter.backend, template_settings(), "input_y",
                                 "research_y", "Research Y", 0.0, 4.0)
    return lab, adapter


def _plan(lab, **changes):
    options = {"study_id": STUDY, "campaign_id": CAMPAIGN,
               "backend": SyntheticParameterizedModel.backend, "settings": template_settings(),
               "parameter_ids": ["research_x", "research_y"],
               "objective": {"source": "model", "metric": "synthetic_objective", "unit": "1",
                             "direction": "minimize"},
               "constraints": [{"source": "model", "metric": "synthetic_constraint", "unit": "1",
                                "operator": "<=", "limit": 3.5, "scale": 2.0}],
               "seed": 13, "max_generations": 1, "population_size": 5,
               "initial_values": {"research_x": 1.0, "research_y": 1.0},
               "required_validations": {"model": ["synthetic_check"]}, "engine": ENGINE}
    options.update(changes)
    return lab.plan_model_optimization(**options)


def test_declared_model_target_and_constraints_share_existing_engine_and_immutable_results(tmp_path):
    lab, adapter = _lab(tmp_path)
    objective = {"source": "model", "metric": "synthetic_objective", "unit": "1", "direction": "match",
                 "target": 0.625, "scale": 2.0, "origin": "SYNTHETIC", "reference": "TEST ONLY (x,y)=(1,1) response"}
    plan = _plan(lab, objective=objective)
    result = lab.run_optimization(CAMPAIGN)
    for row in result["evaluations"]:
        if row["usable"]:
            match = row["objective"]["target_comparison"]
            assert match["difference"] == pytest.approx(row["objective"]["value"] - plan["objective"]["target"])
            assert row["feedback"]["objective"] == pytest.approx((match["difference"] / 2.0) ** 2)
            assert row["feedback"]["constraint_residuals"] == pytest.approx([(row["values"]["research_x"] + row["values"]["research_y"] - 3.5) / 2.0])
    assert result["incumbent"]["feedback"]["objective"] == pytest.approx(0)
    assert result["decision"] == "NOT_RELEASED"
    calls = adapter.calls
    assert lab.inspect_optimization(CAMPAIGN) == result
    assert lab.run_optimization(CAMPAIGN) == result and adapter.calls == calls


@pytest.mark.parametrize("change", [{"target": True}, {"target": float("inf")}, {"scale": 0}, {"scale": -1},
    {"origin": "VERIFIED_MEASUREMENT"}, {"reference": " "}, {"reference": "x" * 2049}, {"direction": "minimize"}])
def test_invalid_matching_declaration_stops_before_campaign_or_adapter(tmp_path, change):
    lab, adapter = _lab(tmp_path)
    objective = {"source": "model", "metric": "synthetic_objective", "unit": "1", "direction": "match",
                 "target": 1.0, "scale": 1.0, "origin": "DESIGN_TARGET", "reference": "Test target"}
    with pytest.raises(ValueError):
        _plan(lab, objective={**objective, **change})
    assert not (lab.store / "optimizations" / CAMPAIGN).exists() and adapter.calls == 0


def _files(folder):
    return {path.relative_to(folder).as_posix(): path.read_bytes()
            for path in folder.rglob("*") if path.is_file() and path.name != "execution.lock"}


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class InterruptedEvaluation(RuntimeError):
    pass


def _interrupt_after_first(lab, monkeypatch):
    original = lab.run_model_analysis

    def interrupt(**options):
        if options["experiment_id"] == f"E-{CAMPAIGN}-0002":
            raise InterruptedEvaluation("TEST ONLY: interrupted after first committed evaluation")
        return original(**options)

    monkeypatch.setattr(lab, "run_model_analysis", interrupt)
    with pytest.raises(InterruptedEvaluation, match="first committed"):
        lab.run_optimization(CAMPAIGN)
    monkeypatch.setattr(lab, "run_model_analysis", original)
    partial = lab.inspect_optimization(CAMPAIGN)
    assert partial["status"] == "RUNNING" and partial["completed_evaluations"] == 1
    assert not (lab.store / "experiments" / f"E-{CAMPAIGN}-0002").exists()
    return partial


def _assert_model_row(lab, plan, row):
    assert not {"cad_experiment_id", "cad_revision", "cad_status", "cad_result_sha256",
                "analysis_experiment_id", "analysis_status", "analysis_result_sha256",
                "parent_experiment_id"}.intersection(row)
    assert row["model_experiment_id"] == f"E-{CAMPAIGN}-{row['index']:04d}"
    expected = deepcopy(plan["model_template"])
    expected["inputs"].update(x=row["values"]["research_x"], y=row["values"]["research_y"])
    assert canonical_hash(row["model_settings"]) == canonical_hash(expected)
    assert type(row["model_settings"]["mesh"]["cell_count"]) is int
    assert type(row["model_settings"]["flags"]["audit"]) is bool
    assert row["model_revision"] == canonical_hash({"settings": row["model_settings"],
                                                   "declaration": row["model_declaration"]})
    experiment = lab.inspect_experiment(row["model_experiment_id"])
    folder = lab.store / "experiments" / row["model_experiment_id"]
    proposal, thread = load_json(folder / "proposal.json"), load_json(folder / "thread.json")
    assert "parent_experiment_id" not in experiment and "parent_experiment_id" not in proposal
    assert experiment["cad_revision"] is None and thread["cad_revision"] is None
    assert experiment["campaign_id"] == proposal["campaign_id"] == thread["campaign"] == CAMPAIGN
    assert experiment["input_parameters"] == proposal["parameters"] == row["values"]
    assert experiment["model_revision"] == proposal["model_revision"] == thread["model_revision"] == row["model_revision"]
    assert proposal["execution"] == row["model_settings"]
    assert experiment["extensions"]["model_analysis"].get("declaration", {}) == row["model_declaration"]
    assert row["model_result_sha256"] == _sha(folder / "result.json")
    assert experiment["provenance"]["registry_sha256"] == plan["registry_sha256"]
    assert experiment["decision"] == row["decision"] == "NOT_RELEASED"
    assert {"model_qualification", "physical_validation"} <= set(row["unknown"])
    return experiment


def test_real_scipy_feedback_adapts_and_completed_model_campaign_reuses_exact_records(tmp_path, monkeypatch):
    lab, adapter = _lab(tmp_path)
    template = template_settings()
    plan = _plan(lab, settings=template)
    template["load"]["force"] = 999.0
    assert plan["route"] == "model_analysis"
    assert not {"model", "cad_adapter_version", "cad_source_fingerprint", "analysis"}.intersection(plan)
    assert plan["model_source_fingerprint"]["runtime"] == {"test_only": True, "version": "1"}
    validate_schema("optimization-plan", plan)
    result = lab.run_optimization(CAMPAIGN)
    validate_schema("optimization-result", result)
    rows = result["evaluations"]
    assert result["route"] == "model_analysis" and result["decision"] == "NOT_RELEASED"
    assert result["algorithm"]["engine"] == ENGINE
    assert 5 < len(rows) <= 10 and result["termination"]["evaluation_count"] == len(rows)
    assert any(row["values"] not in plan["algorithm"]["initial_population"] for row in rows[5:])
    assert len({tuple(row["key"]) for row in rows}) == len(rows)
    for row in rows:
        experiment = _assert_model_row(lab, plan, row)
        if row["usable"]:
            x, y = row["values"]["research_x"], row["values"]["research_y"]
            score = (x - 1.25) ** 2 + (y - 1.75) ** 2
            assert row["feedback"]["objective"] == pytest.approx(score)
            assert row["feedback"]["constraint_residuals"] == pytest.approx([(x + y - 3.5) / 2.0])
            assert experiment["metrics"]["synthetic_objective"]["value"] == pytest.approx(score)
    best = min((row for row in rows if row["numerically_feasible"]),
               key=lambda row: (row["feedback"]["objective"], row["index"]))
    assert result["incumbent"] == best
    assert best["feedback"]["objective"] <= rows[0]["feedback"]["objective"]
    assert adapter.calls == sum(row["model_settings"]["inputs"]["x"] + row["model_settings"]["inputs"]["y"]
                                <= row["model_settings"]["domain_budget"] for row in rows)
    preserved = _files(lab.store)
    calls = adapter.calls
    # Completed evidence remains inspectable after the installed backend changes.
    monkeypatch.setattr(adapter, "runtime_version", "changed-after-completion")
    monkeypatch.setattr(adapter, "crash", True)
    inspected = []
    original = lab.inspect_experiment

    def tracked(identifier, **options):
        inspected.append(identifier)
        return original(identifier, **options)

    monkeypatch.setattr(lab, "inspect_experiment", tracked)
    assert lab.inspect_optimization(CAMPAIGN) == result
    assert Counter(inspected) == Counter(row["model_experiment_id"] for row in rows)
    assert lab.run_optimization(CAMPAIGN) == result
    assert adapter.calls == calls and _files(lab.store) == preserved


def test_individually_admitted_inputs_with_invalid_combination_retain_rejected_experiment(tmp_path):
    lab, adapter = _lab(tmp_path)
    assert all(entry["input_effect"]["status"] == "PASS" for entry in lab.registry(STUDY)["entries"])
    plan = _plan(lab, initial_values={"research_x": 4.0, "research_y": 4.0})
    result = lab.run_optimization(CAMPAIGN)
    rejected = result["evaluations"][0]
    experiment = _assert_model_row(lab, plan, rejected)
    assert rejected["values"] == {"research_x": 4.0, "research_y": 4.0}
    assert rejected["model_status"] == experiment["status"] == "REJECTED"
    assert experiment["solver_status"] == "NOT_RUN" and experiment["converged"] is None
    assert experiment["metrics"] == {} and rejected["model_declaration"] == {}
    assert rejected["feedback"] == {"objective": None, "constraint_residuals": [None]}
    assert not rejected["usable"] and not rejected["numerically_feasible"]
    assert any("domain budget" in evidence["observation"]["observed"] for evidence in experiment["evidence"])
    assert not (lab.store / "experiments" / rejected["model_experiment_id"] / "simulation").exists()
    assert all(item["inputs"]["x"] + item["inputs"]["y"] <= item["domain_budget"]
               for item in adapter.solved_settings)
    assert adapter.calls == sum(row["model_status"] == "COMPLETED_REVIEW_REQUIRED"
                                for row in result["evaluations"])
    assert any(row["numerically_feasible"] for row in result["evaluations"])


def test_interruption_replays_real_engine_without_repeating_completed_model_experiments(tmp_path, monkeypatch):
    lab, adapter = _lab(tmp_path / "interrupted")
    plan = _plan(lab)
    partial = _interrupt_after_first(lab, monkeypatch)
    first = partial["evaluations"][0]
    assert first["numerically_feasible"] and adapter.calls == 1
    folder = lab.store / "experiments" / first["model_experiment_id"]
    preserved = _files(folder)
    journal = lab.store / "optimizations" / CAMPAIGN / "journal/0001.json"
    journal_bytes = journal.read_bytes()
    resumed = lab.run_optimization(CAMPAIGN)
    assert resumed["evaluations"][0] == first
    assert journal.read_bytes() == journal_bytes and _files(folder) == preserved
    assert adapter.calls == sum(row["model_status"] == "COMPLETED_REVIEW_REQUIRED" for row in resumed["evaluations"])
    independent, second_adapter = _lab(tmp_path / "independent")
    second_plan = _plan(independent)
    assert second_plan["algorithm"] == plan["algorithm"]
    direct = independent.run_optimization(CAMPAIGN)
    fields = ("values", "key", "feedback", "numerically_feasible", "model_status", "model_settings", "model_revision")
    assert [{key: row[key] for key in fields} for row in resumed["evaluations"]] == [
        {key: row[key] for key in fields} for row in direct["evaluations"]]
    assert adapter.calls == second_adapter.calls


@pytest.mark.parametrize("boundary", ["before_journal", "before_checkpoint"])
def test_model_completion_and_journal_crash_boundaries_recover_without_new_native_call(tmp_path, monkeypatch, boundary):
    lab, adapter = _lab(tmp_path)
    _plan(lab)
    campaign = lab.store / "optimizations" / CAMPAIGN
    if boundary == "before_journal":
        original = optimization.save_json

        def interrupt(path, value):
            if path == campaign / "journal/0001.json":
                raise InterruptedEvaluation("TEST ONLY: before journal")
            return original(path, value)

        monkeypatch.setattr(optimization, "save_json", interrupt)
    else:
        original = optimization._checkpoint

        def interrupt(*args, **kwargs):
            raise InterruptedEvaluation("TEST ONLY: before checkpoint")

        monkeypatch.setattr(optimization, "_checkpoint", interrupt)
    with pytest.raises(InterruptedEvaluation, match=boundary.replace("_", " ")):
        lab.run_optimization(CAMPAIGN)
    assert adapter.calls == 1
    experiment = lab.store / "experiments" / f"E-{CAMPAIGN}-0001"
    preserved = _files(experiment)
    partial = lab.inspect_optimization(CAMPAIGN)
    assert partial["completed_evaluations"] == (0 if boundary == "before_journal" else 1)
    if boundary == "before_checkpoint":
        assert partial["checkpoint_pending"] == [1]
        journal_bytes = (campaign / "journal/0001.json").read_bytes()
        monkeypatch.setattr(optimization, "_checkpoint", original)
    else:
        assert partial["status"] == "PLANNED"
        monkeypatch.setattr(optimization, "save_json", original)
    result = lab.run_optimization(CAMPAIGN)
    assert _files(experiment) == preserved and (campaign / "checkpoints/0001.json").is_file()
    if boundary == "before_checkpoint":
        assert (campaign / "journal/0001.json").read_bytes() == journal_bytes
    assert adapter.calls == sum(row["model_status"] == "COMPLETED_REVIEW_REQUIRED" for row in result["evaluations"])


@pytest.mark.parametrize("selected", ["objective", "constraint"])
@pytest.mark.parametrize("metric", [
    pytest.param({"value": 0.5, "unit": "m", "valid": True}, id="wrong-unit"),
    pytest.param({"value": [0.5, 0.6], "unit": "1", "valid": True}, id="vector"),
    pytest.param({"value": None, "unit": "1", "valid": False, "reason": "TEST ONLY: unavailable"}, id="null-invalid"),
    pytest.param({"value": 0.5, "unit": "1", "valid": False, "reason": "TEST ONLY: failed response"}, id="invalid-finite"),
])
def test_unusable_model_metrics_preserve_raw_observation_and_have_null_feedback(tmp_path, monkeypatch, selected, metric):
    metric_name = "synthetic_objective" if selected == "objective" else "synthetic_constraint"
    lab, adapter = _lab(tmp_path, SyntheticParameterizedModel(metric_overrides={metric_name: metric}))
    plan = _plan(lab)
    partial = _interrupt_after_first(lab, monkeypatch)
    row = partial["evaluations"][0]
    result = _assert_model_row(lab, plan, row)
    raw = load_json(lab.store / "experiments" / row["model_experiment_id"] / "simulation/result.json")
    assert raw["metrics"][metric_name] == result["metrics"][metric_name] == metric
    observation = row["objective"] if selected == "objective" else row["constraints"][0]
    assert observation["value"] is None and observation["valid"] is False and observation["reason"]
    assert not row["usable"] and not row["numerically_feasible"] and partial["incumbent"] is None
    assert row["feedback"] == {"objective": None, "constraint_residuals": [None]}
    text = (lab.store / "optimizations" / CAMPAIGN / "journal/0001.json").read_text()
    assert "NaN" not in text and "Infinity" not in text and adapter.calls == 1


@pytest.mark.parametrize("check_status", ["FAIL", "UNKNOWN", "MISSING"])
def test_model_required_check_cannot_be_replaced_by_valid_objective(tmp_path, monkeypatch, check_status):
    lab, adapter = _lab(tmp_path, SyntheticParameterizedModel(check_status=check_status))
    _plan(lab)
    row = _interrupt_after_first(lab, monkeypatch)["evaluations"][0]
    assert row["objective"]["valid"] is True
    assert not row["usable"] and not row["numerically_feasible"]
    assert row["feedback"] == {"objective": None, "constraint_residuals": [None]}
    assert adapter.calls == 1
    if check_status == "FAIL":
        completed = lab.run_optimization(CAMPAIGN)
        assert completed["status"] == "NO_FEASIBLE_DESIGN" and completed["incumbent"] is None
        assert completed["decision"] == "NOT_RELEASED" and completed["termination"]["converged"] is False


@pytest.mark.parametrize("metric", [
    {"value": None, "unit": "1", "valid": True},
    {"value": True, "unit": "1", "valid": True},
    {"value": "0.1", "unit": "1", "valid": True},
])
def test_malformed_model_response_is_retained_as_failed_execution(tmp_path, metric):
    lab, adapter = _lab(tmp_path, SyntheticParameterizedModel(metric_overrides={"synthetic_objective": metric}))
    _plan(lab)
    with pytest.raises(RuntimeError, match="execution failed.*evidence retained"):
        lab.run_optimization(CAMPAIGN)
    partial = lab.inspect_optimization(CAMPAIGN)
    row = partial["evaluations"][0]
    result = lab.inspect_experiment(row["model_experiment_id"])
    raw = load_json(lab.store / "experiments" / row["model_experiment_id"] / "simulation/result.json")
    assert raw["metrics"]["synthetic_objective"] == metric
    assert result["status"] == row["model_status"] == partial["status"] == "FAILED_EXECUTION"
    assert result["metrics"] == {} and row["failed_execution"]
    assert row["feedback"] == {"objective": None, "constraint_residuals": [None]}
    assert partial["incumbent"] is None and adapter.calls == 1
    retained = _files(lab.store / "experiments")
    with pytest.raises(RuntimeError, match="retains a failed execution"):
        lab.run_optimization(CAMPAIGN)
    assert _files(lab.store / "experiments") == retained and adapter.calls == 1


@pytest.mark.parametrize("change", ["core_source", "binding_source", "runtime", "adapter_version",
                                  "declaration", "descriptor", "algorithm"])
def test_frozen_source_template_runtime_registry_and_algorithm_block_new_evaluations(tmp_path, monkeypatch, change):
    from caelab import model_parameters

    lab, adapter = _lab(tmp_path)
    _plan(lab)
    if change == "core_source":
        original = model_parameters.source_identity
        monkeypatch.setattr(model_parameters, "source_identity", lambda root: {
            **original(root), "core_source_sha256": "0" * 64})
    elif change == "binding_source":
        monkeypatch.setattr(adapter, "input_source_files", [Path(__file__).resolve()])
    elif change == "runtime":
        adapter.runtime_version = "2"
    elif change == "adapter_version":
        monkeypatch.setattr(adapter, "version", "test-only-2")
    elif change == "declaration":
        original = adapter.describe_model

        def changed(settings):
            model = original(settings)
            model["loads"][0]["value"] = 3.0
            return model

        monkeypatch.setattr(adapter, "describe_model", changed)
    elif change == "descriptor":
        original = adapter.describe_inputs

        def changed(settings):
            descriptors = original(settings)
            descriptors[0]["label"] = "Changed descriptor"
            return descriptors

        monkeypatch.setattr(adapter, "describe_inputs", changed)
    else:
        engine = lab.optimization_adapters[ENGINE]
        original = engine.describe
        monkeypatch.setattr(engine, "describe", lambda *args, **kwargs: {
            **original(*args, **kwargs), "tol": 0.001})
    with pytest.raises(ValueError, match="(?i)(changed|runtime)"):
        lab.run_optimization(CAMPAIGN)
    assert adapter.calls == 0 and not (lab.store / "experiments").exists()
    assert lab.inspect_optimization(CAMPAIGN)["status"] == "PLANNED"


def test_real_registry_bounds_change_is_detected_before_execution(tmp_path):
    lab, adapter = _lab(tmp_path)
    _plan(lab)
    path = lab.store / "studies" / STUDY / "parameters.json"
    registry = load_json(path)
    registry["entries"][0]["upper_bound"] = 3.0
    save_json(path, registry)
    with pytest.raises(ValueError, match="registry changed"):
        lab.run_optimization(CAMPAIGN)
    assert adapter.calls == 0 and not (lab.store / "experiments").exists()


def test_runtime_drift_after_interruption_preserves_completed_model_and_blocks_next(tmp_path, monkeypatch):
    lab, adapter = _lab(tmp_path)
    _plan(lab)
    partial = _interrupt_after_first(lab, monkeypatch)
    preserved = _files(lab.store / "experiments")
    adapter.runtime_version = "2"
    with pytest.raises(ValueError, match="runtime.*changed"):
        lab.run_optimization(CAMPAIGN)
    assert adapter.calls == 1 and _files(lab.store / "experiments") == preserved
    assert lab.inspect_optimization(CAMPAIGN)["evaluations"] == partial["evaluations"]


def test_changed_setter_cannot_execute_a_hidden_load_mutation_after_planning(tmp_path, monkeypatch):
    lab, adapter = _lab(tmp_path)
    _plan(lab, initial_values={"research_x": 2.0, "research_y": 1.0})
    original = adapter.bind_inputs

    def hidden_load(settings, values):
        bound = original(settings, values)
        bound["load"]["force"] = 3.0
        return bound

    monkeypatch.setattr(adapter, "bind_inputs", hidden_load)
    with pytest.raises(ValueError, match="outside its declared locations"):
        lab.run_optimization(CAMPAIGN)
    assert adapter.calls == 0 and not (lab.store / "experiments").exists()
    assert (lab.store / "optimizations" / CAMPAIGN / "candidates/0001.json").is_file()


def test_model_journal_candidate_checkpoint_proposal_and_artifact_tamper_are_refused(tmp_path, monkeypatch):
    lab, adapter = _lab(tmp_path)
    _plan(lab)
    partial = _interrupt_after_first(lab, monkeypatch)
    first = partial["evaluations"][0]
    campaign = lab.store / "optimizations" / CAMPAIGN
    experiment = lab.store / "experiments" / first["model_experiment_id"]
    cases = [
        (campaign / "journal/0001.json", lambda item: item["feedback"].update(objective=999.0)),
        (campaign / "candidates/0001.json", lambda item: item["model_settings"]["load"].update(force=999.0)),
        (campaign / "checkpoints/0001.json", lambda item: item.update(incumbent_index=None)),
        (campaign / "plan.json", lambda item: item["algorithm"].update(seed=14)),
        (experiment / "proposal.json", lambda item: item["execution"]["load"].update(force=999.0)),
        (experiment / "thread.json", lambda item: item.update(model_revision="0" * 64)),
    ]
    for path, mutate in cases:
        retained = path.read_bytes()
        changed = load_json(path)
        mutate(changed)
        save_json(path, changed)
        try:
            with pytest.raises(ValueError, match="(?i)(hash|journal|candidate|checkpoint|plan)"):
                lab.inspect_optimization(CAMPAIGN)
        finally:
            path.write_bytes(retained)
        assert lab.inspect_optimization(CAMPAIGN) == partial
    artifact = experiment / "simulation/raw.log"
    retained = artifact.read_bytes()
    artifact.write_bytes(retained + b"TEST ONLY: tampered raw evidence\n")
    try:
        with pytest.raises(ValueError, match="Artifact hash mismatch"):
            lab.run_optimization(CAMPAIGN)
    finally:
        artifact.write_bytes(retained)
    assert lab.inspect_optimization(CAMPAIGN) == partial and adapter.calls == 1


@pytest.mark.parametrize("change", [
    {"parameter_ids": ["input_x"]}, {"parameter_ids": ["research_x", "research_x"]},
    {"objective": {"source": "cad", "metric": "synthetic_objective", "unit": "1", "direction": "minimize"}},
    {"objective": {"source": "model", "metric": "unadvertised_metric", "unit": "1", "direction": "minimize"}},
    {"required_validations": {"cad": [], "analysis": []}},
    {"initial_values": {"research_x": 4.1, "research_y": 1.0}},
])
def test_model_planning_rejects_unregistered_inputs_wrong_selectors_and_bounds_without_store(tmp_path, change):
    lab, adapter = _lab(tmp_path)
    with pytest.raises(ValueError):
        _plan(lab, **change)
    assert not (lab.store / "optimizations" / CAMPAIGN).exists() and adapter.calls == 0


@pytest.mark.parametrize("fault", ["missing_unit", "duplicate_id", "invalid_typed_path", "missing_model"])
def test_interior_malformed_model_metadata_stops_search_without_rejected_journal(tmp_path, fault):
    lab, adapter = _lab(tmp_path, InteriorMalformedModel(fault))
    assert all(entry["input_effect"]["status"] == "PASS" for entry in lab.registry(STUDY)["entries"])
    _plan(lab, initial_values={"research_x": 2.0, "research_y": 1.0})
    with pytest.raises(ValueError) as raised:
        lab.run_optimization(CAMPAIGN)
    assert not isinstance(raised.value, ModelInputRejected)
    campaign = lab.store / "optimizations" / CAMPAIGN
    # A malformed declaration can stop candidate construction itself; a
    # malformed descriptor can stop the later binding gate. Neither is data.
    candidate_path = campaign / "candidates/0001.json"
    if candidate_path.exists():
        assert load_json(candidate_path)["values"] == {"research_x": 2.0, "research_y": 1.0}
    assert not (campaign / "journal/0001.json").exists()
    assert not (campaign / "checkpoints/0001.json").exists() and not (campaign / "result.json").exists()
    assert adapter.calls == 0 and not (lab.store / "experiments").exists()
    partial = lab.inspect_optimization(CAMPAIGN)
    assert partial["status"] == "PLANNED" and partial["completed_evaluations"] == 0
    assert partial["evaluations"] == [] and partial["incumbent"] is None


@pytest.mark.parametrize("context", ["load", "mesh"])
def test_new_candidate_declaration_is_compared_to_frozen_plan_after_valid_binding(tmp_path, monkeypatch, context):
    lab, adapter = _lab(tmp_path)
    plan = _plan(lab)
    values = {"research_x": 2.0, "research_y": 1.0}
    bound = bind(adapter, plan["model_template"], {"input_x": 2.0, "input_y": 1.0})
    assert bound["inputs"] == {"x": 2.0, "y": 1.0}
    original = adapter.describe_model

    def changed_after_binding(settings):
        model = original(settings)
        if settings["inputs"]["x"] == 2.0:
            if context == "load":
                model["loads"][0]["value"] = 3.0
            else:
                model["model"]["mesh"]["degree"] = 2
        return model

    monkeypatch.setattr(adapter, "describe_model", changed_after_binding)
    with pytest.raises(ValueError, match="Candidate model declaration changed frozen context"):
        optimization._new_item(lab, plan, 1, values)
    assert adapter.calls == 0 and not (lab.store / "experiments").exists()
    assert lab.inspect_optimization(CAMPAIGN)["completed_evaluations"] == 0


@pytest.mark.parametrize("context", ["load", "mesh", "empty_completed"])
def test_self_consistent_stored_model_declaration_is_checked_against_plan_without_live_adapter(tmp_path, monkeypatch,
                                                                                           context):
    lab, adapter = _lab(tmp_path)
    plan = _plan(lab)
    first = _interrupt_after_first(lab, monkeypatch)["evaluations"][0]
    assert first["model_status"] == "COMPLETED_REVIEW_REQUIRED" and adapter.calls == 1
    campaign = lab.store / "optimizations" / CAMPAIGN
    folder = lab.store / "experiments" / first["model_experiment_id"]
    forged = deepcopy(first)
    if context == "load":
        forged["model_declaration"]["loads"][0]["value"] = 3.0
    elif context == "mesh":
        forged["model_declaration"]["model"]["mesh"]["degree"] = 2
    else:
        forged["model_declaration"] = {}
    forged["model_revision"] = canonical_hash({"settings": forged["model_settings"],
                                               "declaration": forged["model_declaration"]})

    # Reanchor the modified metadata throughout the TEST ONLY store. This
    # deliberately removes byte-hash and internal-consistency shortcuts so
    # inspection must compare against the unchanged frozen plan declaration.
    proposal = load_json(folder / "proposal.json")
    proposal["model_revision"] = forged["model_revision"]
    proposal["extensions"]["model_analysis"]["declaration"] = deepcopy(forged["model_declaration"])
    if context == "load":
        proposal["loads"] = deepcopy(forged["model_declaration"]["loads"])
    elif context == "mesh":
        proposal["model"]["mesh"] = deepcopy(forged["model_declaration"]["model"]["mesh"])
    save_json(folder / "proposal.json", proposal)
    proposal_revision = canonical_hash(proposal)
    experiment = load_json(folder / "result.json")
    experiment["model_revision"] = forged["model_revision"]
    experiment["proposal_revision"] = proposal_revision
    experiment["extensions"]["model_analysis"]["declaration"] = deepcopy(forged["model_declaration"])
    experiment["provenance"]["proposal_sha256"] = proposal_revision
    experiment["artifacts"] = artifact_manifest(folder, revision=proposal_revision)
    save_json(folder / "result.json", experiment)
    thread = load_json(folder / "thread.json")
    thread["model_revision"] = forged["model_revision"]
    save_json(folder / "thread.json", thread)
    ledger_path = lab.store / "ledger" / f"{first['model_experiment_id']}.json"
    ledger = load_json(ledger_path)
    ledger.update(result_sha256=_sha(folder / "result.json"), thread_sha256=_sha(folder / "thread.json"))
    save_json(ledger_path, ledger)
    forged["model_result_sha256"] = _sha(folder / "result.json")
    save_json(campaign / "candidates/0001.json", {key: forged[key] for key in optimization._item_fields(plan)})
    save_json(campaign / "journal/0001.json", forged)
    checkpoint = load_json(campaign / "checkpoints/0001.json")
    checkpoint["journal_sha256"]["0001.json"] = _sha(campaign / "journal/0001.json")
    save_json(campaign / "checkpoints/0001.json", checkpoint)
    save_json(campaign / "state.json", checkpoint)

    # The lower byte-integrity checks pass. Even installing no live model
    # adapter must still allow the campaign's pure semantic comparison.
    assert lab.inspect_experiment(first["model_experiment_id"]) == experiment
    lab.model_analysis_adapters = {}
    message = ("Only retained declaration rejection may omit model metadata" if context == "empty_completed"
               else "frozen model declaration context")
    with pytest.raises(ValueError, match=message):
        lab.inspect_optimization(CAMPAIGN)
    assert adapter.calls == 1
