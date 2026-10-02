"""Real SciPy/CAD search gates; counting analysis is explicitly test-only."""

from copy import deepcopy
from collections import Counter
from dataclasses import replace
import hashlib
from pathlib import Path

import pytest

from caelab import Lab
from caelab.storage import load_json, save_json


CAD = "fixture.cadquery"
MODEL = "roller_support"
STUDY = "S-optimization"
CAMPAIGN = "C-search"
ENGINE = "scipy.differential_evolution"


class CountingAnalysis:
    """Exercise Core's analysis contract without claiming a structural solve."""

    backend = "test.optimization.analysis"
    version = "test-only-1"
    analysis_type = "linear_static"
    default_metrics = ["test_response", "test_constraint"]

    def __init__(self, *, metric_overrides=None, check_status="PASS", crash=False,
                 solver_status="COMPLETED"):
        self.calls = 0
        self.parents = []
        self.metric_overrides = metric_overrides or {}
        self.check_status = check_status
        self.crash = crash
        self.solver_status = solver_status
        self.solver_version = "TEST-ONLY-1"

    def solve(self, parent_result, parent_root, output, settings):
        self.calls += 1
        self.parents.append(parent_result["experiment_id"])
        source = parent_root / "cad/assembly.step"
        step = next(a for a in parent_result["artifacts"] if a["path"] == "cad/assembly.step")
        assert source.is_file() and parent_result["cad_revision"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == step["sha256"]
        output.mkdir()
        (output / "solver.log").write_text("TEST ONLY: counting adapter, no structural solver\n")
        if self.crash:
            raise RuntimeError("test-only analysis process crashed")
        pitch = parent_result["input_parameters"]["bolt_pitch"]
        metrics = {
            "test_response": {"value": (pitch - 20.0) ** 2 + 1.0, "unit": "mm", "valid": True},
            "test_constraint": {"value": pitch, "unit": "mm", "valid": True},
        }
        metrics.update(deepcopy(self.metric_overrides))
        checks = ([] if self.check_status == "MISSING" else [
            {"code": "reaction_test", "status": self.check_status,
             "observed": 0.0, "limit": 0.01}])
        outcome = {"status": "COMPLETED", "solver_status": self.solver_status, "converged": True,
                   "checks": checks, "metrics": metrics,
                   "pending_validations": ["static_strength", "physical_load_test"],
                   "provenance": {"versions": {"solver": self.solver_version},
                                  "source_step_sha256": step["sha256"], "test_only": True},
                   "raw_result": "simulation/result.json"}
        save_json(output / "result.json", outcome)
        return outcome


def _lab(path: Path, analysis=None):
    adapter = analysis if analysis is not None else CountingAnalysis()
    lab = Lab(path, analysis_adapters={adapter.backend: adapter})
    lab.create_study(STUDY, "Bounded numerical search", "Which registered pitches remain usable?",
                     "CAD rejection and numerical usability are distinct",
                     "Preserve deterministic evaluation evidence")
    registered = lab.register_parameter(STUDY, CAD, MODEL, "bolt_pitch_x_mm",
                                        "bolt_pitch", "Bolt pitch", 18, 40)
    assert registered["geometry_effect"]["status"] == "PASS"
    return lab, adapter


def _plan(lab, *, initial_pitch=20.0, **changes):
    options = {"study_id": STUDY, "campaign_id": CAMPAIGN, "backend": CAD,
               "model": MODEL, "parameter_ids": ["bolt_pitch"],
               "objective": {"source": "analysis", "metric": "test_response",
                             "unit": "mm", "direction": "minimize"},
               "constraints": [{"source": "analysis", "metric": "test_constraint",
                                "unit": "mm", "operator": "<=", "limit": 24.0, "scale": 1.0}],
               "seed": 13, "max_generations": 1, "population_size": 5,
               "initial_values": {"bolt_pitch": initial_pitch},
               "analysis_backend": CountingAnalysis.backend,
               "analysis_settings": {"load": {"force_N": 100, "source": "TEST ONLY"}},
               "required_validations": {"cad": [], "analysis": ["reaction_test"]}}
    options.update(changes)
    return lab.plan_optimization(**options)


class InterruptedEvaluation(RuntimeError):
    pass


def test_user_cancel_preserves_first_evaluation_and_stops_numerical_candidates(tmp_path):
    from caelab.execution_control import CancellationToken, ExecutionCancelled, cancellation_scope
    token = CancellationToken()

    class RequestAfterAnalysis(CountingAnalysis):
        def solve(self, *args, **kwargs):
            result = super().solve(*args, **kwargs)
            token.request()
            return result

    adapter = RequestAfterAnalysis()
    lab, _ = _lab(tmp_path, adapter)
    _plan(lab)
    with cancellation_scope(token), pytest.raises(ExecutionCancelled):
        lab.run_optimization(CAMPAIGN)
    partial = lab.inspect_optimization(CAMPAIGN)
    assert partial["status"] == "RUNNING" and partial["completed_evaluations"] == 1
    assert adapter.calls == 1 and token.observed
    assert (tmp_path / "optimizations" / CAMPAIGN / "journal/0001.json").is_file()
    assert not (tmp_path / "experiments" / f"E-{CAMPAIGN}-0002").exists()
    assert not (tmp_path / "optimizations" / CAMPAIGN / "result.json").exists()


def _interrupt_after_first(lab, monkeypatch):
    """Interrupt before reserving the second CAD ID, after a committed row."""
    original = lab.run_experiment

    def interrupt(*args, **kwargs):
        if kwargs["experiment_id"] == f"E-{CAMPAIGN}-0002":
            raise InterruptedEvaluation("Interrupted after completed first evaluation")
        return original(*args, **kwargs)

    monkeypatch.setattr(lab, "run_experiment", interrupt)
    with pytest.raises(InterruptedEvaluation, match="completed first"):
        lab.run_optimization(CAMPAIGN)
    monkeypatch.setattr(lab, "run_experiment", original)
    partial = lab.inspect_optimization(CAMPAIGN)
    assert partial["status"] == "RUNNING" and partial["completed_evaluations"] == 1
    assert not (lab.store / "experiments" / f"E-{CAMPAIGN}-0002").exists()
    return partial


def _files(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes()
            for p in folder.rglob("*") if p.is_file()}


def test_real_de_invalid_cad_skips_analysis_and_completed_replay_is_immutable(tmp_path, monkeypatch):
    lab, analysis = _lab(tmp_path)
    plan = _plan(lab, initial_pitch=40.0)
    assert plan["algorithm"]["engine"] == ENGINE
    assert plan["algorithm"]["population_size"] == 5
    assert plan["algorithm"]["max_generations"] == 1
    assert plan["algorithm"]["initial_population"][0] == {"bolt_pitch": 40.0}
    assert plan["variables"][0]["native"]["path"] == "bolt_pitch_x_mm"
    assert plan["cad_source_fingerprint"]["commit"] == "3e48bf6138f495299f45b1af254bfb4aaff307b8"
    assert len(plan["cad_source_fingerprint"]["files_sha256"]) == 64
    assert plan["failure_policy"]["failed_execution"] == "STOP"
    assert lab.inspect_optimization(CAMPAIGN)["status"] == "PLANNED"

    result = lab.run_optimization(CAMPAIGN)
    rows = result["evaluations"]
    assert 5 <= len(rows) <= 10
    assert rows[0]["cad_status"] == "REJECTED"
    rejected = [row for row in rows if row["cad_status"] == "REJECTED"]
    accepted = [row for row in rows if row["cad_status"] == "COMPLETED_REVIEW_REQUIRED"]
    assert rejected and accepted
    assert analysis.calls == len(accepted)
    assert len(set(analysis.parents)) == analysis.calls
    for row in rejected:
        assert row["analysis_status"] == "SKIPPED_CAD_REJECTED"
        assert row["analysis_experiment_id"] is None
        assert row["objective"]["value"] is None and not row["usable"]
        assert not (lab.store / "experiments" / (row["cad_experiment_id"] + "-solve")).exists()
        assert row["failures"] and row["decision"] == "NOT_RELEASED"
    for row in rows:
        assert row["key"] == [float(row["values"][name]).hex()
                              for name in plan["algorithm"]["parameter_order"]]
        assert row["unknown"] or row["cad_status"] == "REJECTED"
        if row["constraints"][0]["valid"]:
            assert row["constraints"][0]["residual"] == pytest.approx(
                row["values"]["bolt_pitch"] - 24.0)
    assert result["incumbent"] is not None and result["incumbent"]["numerically_feasible"]
    assert result["decision"] == "NOT_RELEASED"
    assert result["provenance"]["solver_versions"] == {"solver": "TEST-ONLY-1"}
    assert result["termination"]["evaluation_count"] == len(rows)

    jsonschema = pytest.importorskip("jsonschema")
    schemas = Path(__file__).resolve().parents[1] / "schemas"
    jsonschema.validate(plan, load_json(schemas / "optimization-plan.schema.json"))
    jsonschema.validate(result, load_json(schemas / "optimization-result.schema.json"))
    retained = _files(lab.store / "optimizations" / CAMPAIGN)
    retained.pop("execution.lock", None)
    old_calls = analysis.calls
    # A completed record can still be inspected/replayed after this installation changes.
    monkeypatch.setattr(lab.adapters[CAD], "version", "changed-after-completion")
    monkeypatch.setattr(analysis, "crash", True)
    inspected = []
    inspect_experiment = lab.inspect_experiment

    def count_inspections(identifier, **options):
        inspected.append(identifier)
        return inspect_experiment(identifier, **options)

    monkeypatch.setattr(lab, "inspect_experiment", count_inspections)
    assert lab.inspect_optimization(CAMPAIGN) == result
    expected_ids = {row["cad_experiment_id"] for row in rows} | {
        row["analysis_experiment_id"] for row in rows if row["analysis_experiment_id"]}
    assert set(inspected) == expected_ids
    expected_counts = Counter({identifier: 1 for identifier in expected_ids})
    # Core's child inspection also verifies its CAD parent; that check is kept.
    expected_counts.update(row["cad_experiment_id"] for row in rows if row["analysis_experiment_id"])
    assert Counter(inspected) == expected_counts
    inspected.clear()
    assert lab.inspect_optimization(CAMPAIGN) == result
    assert Counter(inspected) == expected_counts
    assert lab.run_optimization(CAMPAIGN) == result
    assert analysis.calls == old_calls
    replay_files = _files(lab.store / "optimizations" / CAMPAIGN)
    replay_files.pop("execution.lock", None)
    assert replay_files == retained
    result_file = lab.store / "optimizations" / CAMPAIGN / "result.json"
    changed = deepcopy(result)
    changed["decision"] = "RELEASED"
    save_json(result_file, changed)
    with pytest.raises(ValueError, match="result hash"):
        lab.inspect_optimization(CAMPAIGN)


def test_resume_preserves_completed_results_and_never_repeats_the_solver(tmp_path, monkeypatch):
    lab, analysis = _lab(tmp_path)
    plan = _plan(lab)
    partial = _interrupt_after_first(lab, monkeypatch)
    first = partial["evaluations"][0]
    assert first["numerically_feasible"] and analysis.calls == 1
    paths = [lab.store / "experiments" / first["cad_experiment_id"],
             lab.store / "experiments" / first["analysis_experiment_id"]]
    preserved = [_files(path) for path in paths]
    journal = lab.store / "optimizations" / CAMPAIGN / "journal/0001.json"
    previous_journal = journal.read_bytes()
    resumed = lab.run_optimization(CAMPAIGN)
    assert resumed["evaluations"][0] == first
    assert journal.read_bytes() == previous_journal
    assert [_files(path) for path in paths] == preserved
    assert analysis.calls == sum(row["analysis_experiment_id"] is not None
                                 for row in resumed["evaluations"])
    assert len(set(analysis.parents)) == analysis.calls
    checkpoint = load_json(lab.store / "optimizations" / CAMPAIGN /
                           f"checkpoints/{len(resumed['evaluations']):04d}.json")
    assert checkpoint["evaluation_order"] == [row["key"] for row in resumed["evaluations"]]
    independent, other_analysis = _lab(tmp_path / "independent")
    other_plan = _plan(independent)
    assert other_plan["algorithm"] == plan["algorithm"]
    replay = independent.run_optimization(CAMPAIGN)
    selectors = ("values", "key", "feedback", "numerically_feasible", "cad_status", "analysis_status")
    assert [{name: row[name] for name in selectors} for row in replay["evaluations"]] == [
        {name: row[name] for name in selectors} for row in resumed["evaluations"]]
    assert other_analysis.calls == analysis.calls


def test_journal_committed_before_checkpoint_interruption_remains_inspectable_and_resumable(tmp_path, monkeypatch):
    from caelab import optimization

    lab, analysis = _lab(tmp_path)
    _plan(lab)
    original = optimization._checkpoint

    def interrupt_checkpoint(*args, **kwargs):
        raise InterruptedEvaluation("Interrupted after journal write before checkpoint")

    monkeypatch.setattr(optimization, "_checkpoint", interrupt_checkpoint)
    with pytest.raises(InterruptedEvaluation, match="before checkpoint"):
        lab.run_optimization(CAMPAIGN)
    monkeypatch.setattr(optimization, "_checkpoint", original)
    campaign = lab.store / "optimizations" / CAMPAIGN
    journal = campaign / "journal/0001.json"
    preserved_journal = journal.read_bytes()
    assert not (campaign / "checkpoints/0001.json").exists()
    partial = lab.inspect_optimization(CAMPAIGN)
    assert partial["status"] == "RUNNING" and partial["completed_evaluations"] == 1
    assert partial["checkpoint_pending"] == [1]
    assert analysis.calls == 1
    first = partial["evaluations"][0]
    retained = _files(lab.store / "experiments" / first["analysis_experiment_id"])
    resumed = lab.run_optimization(CAMPAIGN)
    assert resumed["evaluations"][0] == first
    assert journal.read_bytes() == preserved_journal
    assert _files(lab.store / "experiments" / first["analysis_experiment_id"]) == retained
    assert (campaign / "checkpoints/0001.json").is_file()
    assert analysis.calls == sum(row["analysis_experiment_id"] is not None
                                 for row in resumed["evaluations"])
    assert len(set(analysis.parents)) == analysis.calls


def test_tampered_partial_journal_proposal_artifact_candidate_and_checkpoint_are_detected(tmp_path, monkeypatch):
    lab, analysis = _lab(tmp_path)
    _plan(lab)
    partial = _interrupt_after_first(lab, monkeypatch)
    row = partial["evaluations"][0]
    campaign = lab.store / "optimizations" / CAMPAIGN
    cases = [
        (campaign / "journal/0001.json", lambda item: item["feedback"].update(objective=999.0)),
        (campaign / "candidates/0001.json", lambda item: item["values"].update(bolt_pitch=21.0)),
        (campaign / "checkpoints/0001.json", lambda item: item.update(incumbent_index=None)),
        (campaign / "plan.json", lambda item: item["algorithm"].update(seed=14)),
        (lab.store / "experiments" / row["cad_experiment_id"] / "proposal.json",
         lambda item: item["execution"].update(random_seed=14)),
    ]
    for path, mutate in cases:
        original = path.read_bytes()
        item = load_json(path)
        mutate(item)
        save_json(path, item)
        try:
            with pytest.raises(ValueError, match="(?i)(hash|journal|candidate|checkpoint|plan)"):
                lab.inspect_optimization(CAMPAIGN)
        finally:
            path.write_bytes(original)
        assert lab.inspect_optimization(CAMPAIGN) == partial
    artifact = lab.store / "experiments" / row["analysis_experiment_id"] / "simulation/solver.log"
    original = artifact.read_bytes()
    artifact.write_bytes(original + b"tampered raw observation\n")
    with pytest.raises(ValueError, match="Artifact hash mismatch"):
        lab.run_optimization(CAMPAIGN)
    artifact.write_bytes(original)
    assert lab.inspect_optimization(CAMPAIGN) == partial and analysis.calls == 1


@pytest.mark.parametrize("change", ["core_source", "cad_source", "plugin_fingerprint", "cad_version", "analysis_version", "algorithm"])
def test_changed_source_or_algorithm_blocks_new_evaluations(tmp_path, monkeypatch, change):
    lab, analysis = _lab(tmp_path)
    _plan(lab)
    partial = _interrupt_after_first(lab, monkeypatch)
    if change == "core_source":
        from caelab import campaign
        original = campaign.source_identity

        def changed_identity(root):
            return {**original(root), "core_source_sha256": "0" * 64}

        monkeypatch.setattr(campaign, "source_identity", changed_identity)
    elif change == "cad_source":
        original = lab.adapters[CAD].discover
        monkeypatch.setattr(lab.adapters[CAD], "discover", lambda model: [
            replace(candidate, source_sha256="0" * 64) for candidate in original(model)])
    elif change == "plugin_fingerprint":
        original = lab.adapters[CAD].source_fingerprint
        monkeypatch.setattr(lab.adapters[CAD], "source_fingerprint", lambda: {
            **original(), "files_sha256": "0" * 64})
    elif change == "cad_version":
        monkeypatch.setattr(lab.adapters[CAD], "version", "different-cad-version")
    elif change == "analysis_version":
        monkeypatch.setattr(analysis, "version", "different-analysis-version")
    else:
        engine = lab.optimization_adapters[ENGINE]
        original = engine.describe

        def changed_algorithm(*args, **kwargs):
            return {**original(*args, **kwargs), "tol": 0.001}

        monkeypatch.setattr(engine, "describe", changed_algorithm)
    with pytest.raises(ValueError, match="(?i)(changed|runtime)"):
        lab.run_optimization(CAMPAIGN)
    assert analysis.calls == 1
    assert not (lab.store / "experiments" / f"E-{CAMPAIGN}-0002").exists()
    assert lab.inspect_optimization(CAMPAIGN)["evaluations"] == partial["evaluations"]


def test_real_registry_change_blocks_execution_before_any_experiment(tmp_path):
    lab, analysis = _lab(tmp_path)
    _plan(lab)
    lab.register_parameter(STUDY, CAD, MODEL, "support_width_mm",
                           "support_width", "Support width", 28, 60)
    with pytest.raises(ValueError, match="registry changed"):
        lab.run_optimization(CAMPAIGN)
    assert analysis.calls == 0
    assert not (lab.store / "experiments" / f"E-{CAMPAIGN}-0001").exists()


@pytest.mark.parametrize("check_status", ["FAIL", "UNKNOWN", "MISSING"])
def test_required_reaction_check_cannot_be_replaced_by_valid_metric(tmp_path, monkeypatch, check_status):
    lab, analysis = _lab(tmp_path, CountingAnalysis(check_status=check_status))
    _plan(lab)
    partial = _interrupt_after_first(lab, monkeypatch)
    row = partial["evaluations"][0]
    child = lab.inspect_experiment(row["analysis_experiment_id"])
    assert child["metrics"]["test_response"]["valid"] is True
    assert row["objective"]["valid"] is True
    assert not row["usable"] and not row["numerically_feasible"]
    assert row["feedback"]["objective"] is None and partial["incumbent"] is None
    if check_status == "FAIL":
        assert child["status"] == "REJECTED"
        assert row["failures"]
    else:
        assert child["status"] == "COMPLETED_REVIEW_REQUIRED"
    assert analysis.calls == 1 and child["decision"] == "NOT_RELEASED"
    if check_status == "FAIL":
        completed = lab.run_optimization(CAMPAIGN)
        assert completed["status"] == "NO_FEASIBLE_DESIGN" and completed["incumbent"] is None
        assert completed["termination"]["converged"] is False
        assert all(not item["numerically_feasible"] for item in completed["evaluations"])
        assert completed["decision"] == "NOT_RELEASED"


@pytest.mark.parametrize("pitch,feasible", [(22.0, True), (18.0, False)])
def test_maximize_and_lower_bound_constraint_use_explicit_scaled_feedback(tmp_path, monkeypatch, pitch, feasible):
    lab, _ = _lab(tmp_path)
    _plan(lab, initial_pitch=pitch,
          objective={"source": "analysis", "metric": "test_response", "unit": "mm", "direction": "maximize"},
          constraints=[{"source": "analysis", "metric": "test_constraint", "unit": "mm",
                        "operator": ">=", "limit": 20.0, "scale": 2.0}])
    partial = _interrupt_after_first(lab, monkeypatch)
    row = partial["evaluations"][0]
    assert row["usable"]
    assert row["objective"]["value"] == pytest.approx((pitch - 20.0) ** 2 + 1.0)
    assert row["feedback"]["objective"] == pytest.approx(-row["objective"]["value"])
    assert row["constraints"][0]["residual"] == pytest.approx((20.0 - pitch) / 2.0)
    assert row["constraints"][0]["satisfied"] is feasible
    assert row["numerically_feasible"] is feasible
    assert (partial["incumbent"] is not None) is feasible


BAD_METRICS = [
    pytest.param({"value": 0.01, "unit": "m", "valid": True}, id="wrong-unit"),
    pytest.param({"value": [0.01, 0.02], "unit": "mm", "valid": True}, id="vector"),
    pytest.param({"value": True, "unit": "mm", "valid": True}, id="boolean"),
    pytest.param({"value": 0.01, "unit": "mm", "valid": False,
                  "reason": "TEST ONLY: unusable numerical observation"}, id="invalid"),
]


@pytest.mark.parametrize("selected", ["objective", "constraint"])
@pytest.mark.parametrize("metric", BAD_METRICS)
def test_unusable_metric_is_retained_but_never_used_for_objective_or_constraint(tmp_path, monkeypatch, selected, metric):
    name = "test_response" if selected == "objective" else "test_constraint"
    lab, _ = _lab(tmp_path, CountingAnalysis(metric_overrides={name: metric}))
    _plan(lab)
    if type(metric["value"]) is bool:
        with pytest.raises(RuntimeError, match="execution failed.*evidence retained"):
            lab.run_optimization(CAMPAIGN)
        partial = lab.inspect_optimization(CAMPAIGN)
        assert partial["status"] == "FAILED_EXECUTION"
    else:
        partial = _interrupt_after_first(lab, monkeypatch)
    row = partial["evaluations"][0]
    child = lab.inspect_experiment(row["analysis_experiment_id"])
    raw = load_json(lab.store / "experiments" / row["analysis_experiment_id"] / "simulation/result.json")
    assert raw["metrics"][name] == metric
    if type(metric["value"]) is bool:
        assert child["status"] == "FAILED_EXECUTION" and child["metrics"] == {}
    else:
        assert child["metrics"][name] == metric
        assert child["status"] == "COMPLETED_REVIEW_REQUIRED"
    observation = row["objective"] if selected == "objective" else row["constraints"][0]
    assert observation["valid"] is False and observation["value"] is None
    assert observation["reason"]
    assert not row["usable"] and not row["numerically_feasible"]
    assert row["feedback"] == {"objective": None, "constraint_residuals": [None]}
    assert partial["incumbent"] is None
    journal = (lab.store / "optimizations" / CAMPAIGN / "journal/0001.json").read_text()
    assert "Infinity" not in journal and "NaN" not in journal


@pytest.mark.parametrize("failed_backend", ["cad", "analysis"])
def test_backend_crash_stops_search_and_remains_a_failed_execution(tmp_path, monkeypatch, failed_backend):
    analysis = CountingAnalysis(crash=failed_backend == "analysis")
    lab, _ = _lab(tmp_path, analysis)
    _plan(lab)
    if failed_backend == "cad":
        def crash(*args, **kwargs):
            raise RuntimeError("test-only CAD process crashed")

        monkeypatch.setattr(lab.adapters[CAD], "regenerate", crash)
    with pytest.raises(RuntimeError, match="execution failed.*evidence retained"):
        lab.run_optimization(CAMPAIGN)
    inspected = lab.inspect_optimization(CAMPAIGN)
    assert inspected["status"] == "FAILED_EXECUTION"
    assert inspected["decision"] == "NOT_RELEASED"
    assert inspected["completed_evaluations"] == 1 and inspected["incumbent"] is None
    row = inspected["evaluations"][0]
    assert row["failed_execution"] and not row["numerically_feasible"]
    assert row["failures"] and row["feedback"]["objective"] is None
    if failed_backend == "analysis":
        assert row["cad_status"] == "COMPLETED_REVIEW_REQUIRED"
        assert row["analysis_status"] == "FAILED_EXECUTION" and analysis.calls == 1
        child = lab.inspect_experiment(row["analysis_experiment_id"])
        assert "simulation/solver.log" in {a["path"] for a in child["artifacts"]}
    else:
        assert row["cad_status"] == "FAILED_EXECUTION"
        assert row["analysis_status"] == "SKIPPED_CAD_FAILED_EXECUTION"
        assert row["analysis_experiment_id"] is None and analysis.calls == 0
    assert not (lab.store / "experiments" / f"E-{CAMPAIGN}-0002").exists()
    retained = _files(lab.store / "experiments")
    with pytest.raises(RuntimeError, match="retains a failed execution"):
        lab.run_optimization(CAMPAIGN)
    assert lab.inspect_optimization(CAMPAIGN) == inspected
    assert _files(lab.store / "experiments") == retained


@pytest.mark.parametrize("invalid", ["null-metric", "string-metric", "not-run-solver", "failed-solver"])
def test_malformed_completed_analysis_cannot_feed_the_search(tmp_path, invalid):
    overrides = {}
    status = "COMPLETED"
    if invalid == "null-metric":
        overrides = {"test_response": {"value": None, "unit": "mm", "valid": True}}
    elif invalid == "string-metric":
        overrides = {"test_response": {"value": "0.001", "unit": "mm", "valid": True}}
    else:
        status = "NOT_RUN" if invalid == "not-run-solver" else "FAILED_EXECUTION"
    lab, analysis = _lab(tmp_path, CountingAnalysis(metric_overrides=overrides, solver_status=status))
    _plan(lab)
    with pytest.raises(RuntimeError, match="execution failed.*evidence retained"):
        lab.run_optimization(CAMPAIGN)
    result = lab.inspect_optimization(CAMPAIGN)
    assert result["status"] == "FAILED_EXECUTION" and result["incumbent"] is None
    row = result["evaluations"][0]
    child = lab.inspect_experiment(row["analysis_experiment_id"])
    assert child["status"] == "FAILED_EXECUTION"
    assert child["metrics"] == {} and child["decision"] == "NOT_RELEASED"
    assert row["feedback"] == {"objective": None, "constraint_residuals": [None]}
    assert analysis.calls == 1
    assert not (lab.store / "experiments" / f"E-{CAMPAIGN}-0002").exists()


@pytest.mark.parametrize("solver_status", ["COMPLETED", "CONVERGED"])
def test_successful_solver_version_drift_is_checked_for_both_statuses(solver_status):
    """Pure Core version gate: synthetic records do not claim solver execution."""
    from caelab.optimization import _versions

    current = {"solver": "TEST-ONLY-2"}

    class FakeLab:
        def inspect_experiment(self, experiment_id):
            assert experiment_id == "E-test-only-solve"
            return {"solver_status": solver_status, "provenance": {"solver": {"versions": current}}}

    row = {"analysis_experiment_id": "E-test-only-solve"}
    assert _versions(FakeLab(), row, None) == current
    assert _versions(FakeLab(), row, current.copy()) == current
    with pytest.raises(ValueError, match="solver versions changed"):
        _versions(FakeLab(), row, {"solver": "TEST-ONLY-1"})
