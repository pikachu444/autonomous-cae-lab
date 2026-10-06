"""Source-only frozen-plan, independent calculus and provenance controls."""

from copy import deepcopy
import math

import pytest

from caelab.storage import canonical_hash, load_json, save_json
from plugins.pde_vector import reference as domain
from plugins.pde_vector.reference import validate_settings
from scripts import verify_vector_pde as runner
from test_pde_vector_reference import refresh_errors, small_settings, synthetic_vector


def field(count=1, experiment="E-vector-mixed", settings=None):
    settings = settings or runner.specification()
    coordinates = [[i/count, j/count] for j in range(count+1) for i in range(count+1)]
    ids = list(range(len(coordinates)))
    cells = []
    for j in range(count):
        for i in range(count):
            a = j*(count+1)+i
            b, c, d = a+1, a+count+1, a+count+2
            cells.extend([[a, b, d], [a, d, c]])
    return {"node_ids": ids, "coordinates": coordinates, "cell_node_ids": cells,
            "values": [runner._math(experiment, settings, x, y)["solution"] for x, y in coordinates]}


def test_frozen_controls_preserve_component_directions_and_fixed_criteria():
    accepted, rejected, refused = runner.cases()
    assert len(accepted) == 6 and len(rejected) == 3 and len(refused) == 5
    assert len(set(accepted) | set(rejected) | set(refused)) == 14
    assert sum(len(case["mesh"]["cell_counts"]) for case in [*accepted.values(), *rejected.values()]) == 27
    for settings in [*accepted.values(), *rejected.values()]:
        assert validate_settings(settings) == settings
        assert settings["validation"] == {"max_l2_error": .04, "max_h1_seminorm_error": .8,
            "min_l2_rate": 1.8, "min_h1_rate": .9, "max_residual_relative": 1e-10}
    base = accepted["E-vector-mixed"]
    assert rejected["E-vector-reference-reject"]["problem"]["reference"]["solution"] == [base["problem"]["reference"]["solution"][0], "0.0"]
    assert rejected["E-vector-source-swap-reject"]["problem"]["weak_form"]["rhs"] == base["problem"]["weak_form"]["rhs"][::-1]
    assert refused["E-vector-invalid-corner"]["problem"]["boundaries"]["xmin"]["value"][0] == base["problem"]["boundaries"]["xmin"]["value"][0]
    assert base["problem"]["weak_form"]["lame_lambda"] > 0
    assert accepted["E-vector-lambda-zero"]["problem"]["weak_form"]["lame_lambda"] == 0
    assert accepted["E-vector-harmonic-zero-source"]["problem"]["weak_form"]["rhs"] == ["0.0", "0.0"]


def test_direct_lame_source_shear_and_outward_signs():
    settings = runner.specification()
    observed = runner._math("E-vector-mixed", settings, .7, .3)
    x, y = .7, .3
    assert observed["rhs"] == pytest.approx([-2*x*x-6*y*y-16*x*y, -12*x*x-4*y*y-8*x*y])
    assert observed["stress"][0][1] == pytest.approx(2*x*x*y+4*x*y*y-1)
    assert observed["stress"][0][1] == observed["stress"][1][0]
    # Lower sides become N for this pure calculus check, without a native run.
    for side in ("xmin", "ymin"):
        settings["problem"]["boundaries"][side]["type"] = "neumann"
    assert runner._side_value("E-vector-mixed", settings, "xmin", 0., y) == pytest.approx([-4., 1.])
    assert runner._side_value("E-vector-mixed", settings, "ymin", x, 0.) == pytest.approx([1., -4.])
    flipped = runner._side_value("E-vector-traction-reject", settings, "xmax", 2., y)
    original = runner._side_value("E-vector-mixed", settings, "xmax", 2., y)
    assert flipped == pytest.approx([original[0], -original[1]])


def test_harmonic_divergence_and_zero_source_do_not_fake_lambda_coverage():
    settings = runner.cases()[0]["E-vector-harmonic-zero-source"]
    data = runner._math("E-vector-harmonic-zero-source", settings, .7, .3)
    assert data["rhs"] == [0., 0.]
    assert data["gradient"][0][0]+data["gradient"][1][1] == 0
    assert data["stress"] == [[2.8, -1.2], [-1.2, -2.8]]
    settings["problem"]["weak_form"]["lame_lambda"] = 9
    assert runner._math("E-vector-harmonic-zero-source", settings, .7, .3)["stress"] == data["stress"]
    settings["problem"]["weak_form"]["reaction"] = 3
    assert runner._math("E-vector-harmonic-zero-source", settings, .7, .3)["rhs"] == [3*value for value in data["solution"]]


def test_independent_duffy_matches_closed_unit_square_errors():
    # On these two triangles q_h=min(x,y) for q=x²y²; affine parts cancel.
    # Direct integrals: ||q_h-q||²=67/1050 and ||grad(q_h-q)||²=11/15.
    result = runner._integrate_field("E-vector-mixed", runner.specification(), field())
    assert result["component_l2"] == pytest.approx([math.sqrt(67/1050), 2*math.sqrt(67/1050)], rel=1e-12)
    assert result["component_h1"] == pytest.approx([math.sqrt(11/15), 2*math.sqrt(11/15)], rel=1e-12)
    assert result["l2"] == pytest.approx(math.sqrt(67/210), rel=1e-12)
    assert result["h1"] == pytest.approx(math.sqrt(11/3), rel=1e-12)


def test_duffy_handles_orientation_and_global_node_permutation():
    original = field()
    expected = runner._integrate_field("E-vector-mixed", runner.specification(), original)
    permutation = [2, 0, 3, 1]
    changed = {"node_ids": permutation,
        "coordinates": [original["coordinates"][node] for node in permutation],
        "values": [original["values"][node] for node in permutation],
        "cell_node_ids": [cell[::-1] for cell in original["cell_node_ids"]]}
    actual = runner._integrate_field("E-vector-mixed", runner.specification(), changed)
    for name in actual:
        assert actual[name] == pytest.approx(expected[name], rel=1e-12)


def test_swapped_directed_values_are_not_magnitude_equivalent():
    original, changed = field(2), field(2)
    changed["values"] = [values[::-1] for values in changed["values"]]
    a = runner._integrate_field("E-vector-mixed", runner.specification(), original)
    b = runner._integrate_field("E-vector-mixed", runner.specification(), changed)
    assert b["l2"] > 3*a["l2"]
    assert all(sum(value*value for value in first) == sum(value*value for value in second)
               for first, second in zip(original["values"], changed["values"]))


def test_raw_observation_preservation_allows_only_additive_diagnostics():
    raw = {"components": [{"index": 0, "value": 1.0}, {"index": 1, "value": 2.0}], "rate": None}
    assessed = deepcopy(raw)
    assessed["components"][0]["diagnostic"] = "recomputed"
    assert runner._original_observations(raw, assessed)
    assessed["components"][1]["value"] = -2.0
    assert not runner._original_observations(raw, assessed)
    assessed = deepcopy(raw)
    assessed["components"][0]["index"] = False
    assert not runner._original_observations(raw, assessed)


def test_old_store_refused_before_any_source_or_native_call(tmp_path, monkeypatch):
    retained = tmp_path / "retained"
    retained.mkdir()
    artifact = retained / "old.json"
    artifact.write_text('{"retain":true}\n')
    before = artifact.read_bytes()
    monkeypatch.setattr(runner, "_source_pin", lambda: pytest.fail("Old store must refuse before source/native setup"))
    with pytest.raises(AssertionError, match="must be new"):
        runner.run(retained)
    assert artifact.read_bytes() == before


@pytest.mark.parametrize("commit,dirty", [("unavailable", False), ("candidate", True)])
def test_clean_source_guard_blocks_native_and_store_creation(tmp_path, monkeypatch, commit, dirty):
    monkeypatch.setattr(runner, "_source_pin", lambda: {"core": {"core_commit": commit, "core_dirty": dirty}, "files": {}})
    monkeypatch.setattr(runner, "Lab", lambda *a, **k: pytest.fail("Uncommitted source must block Core/native"))
    with pytest.raises(AssertionError, match="committed clean"):
        runner.run(tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_source_and_retained_provenance_drift_are_detected(monkeypatch):
    frozen = {"core": {"core_commit": "candidate", "core_dirty": False}, "files": {"worker": "sealed"}}
    monkeypatch.setattr(runner, "_source_pin", lambda: frozen)
    runner._verify_source(frozen, {"provenance": frozen["core"]})
    with pytest.raises(AssertionError, match="provenance"):
        runner._verify_source(frozen, {"provenance": {"core_commit": "other", "core_dirty": False}})
    changed = deepcopy(frozen)
    changed["files"]["worker"] = "changed"
    monkeypatch.setattr(runner, "_source_pin", lambda: changed)
    with pytest.raises(AssertionError, match="source drift"):
        runner._verify_source(frozen)


def test_native_copy_hash_drift_is_detected_without_execution(tmp_path, monkeypatch):
    native = tmp_path / "pde"
    native.mkdir()
    save_json(native / "command.json", {"source_only_fixture": True})
    copied = native / "worker.py"
    copied.write_text("synthetic source-only copy\n")
    digest = runner._sha(copied)
    pin = {"core": {"core_commit": "candidate", "core_dirty": False}, "files": {"worker.py": digest}}
    monkeypatch.setattr(runner, "SOURCE_PATHS", {"worker": ("worker.py", "worker.py")})
    monkeypatch.setattr(runner, "_source_pin", lambda: pin)
    save_json(native / "source_manifest.json", {"files": {"worker": {"repository_path": "worker.py", "copied_path": "worker.py", "sha256": digest}}})
    runner._verify_source(pin, {"provenance": pin["core"]}, tmp_path)
    copied.write_text("tampered source-only copy\n")
    with pytest.raises(AssertionError, match="copied bytes"):
        runner._verify_source(pin, {"provenance": pin["core"]}, tmp_path)


def protocol_run(monkeypatch, groups, modes, *, missing_reason=False, bad_ledger=False):
    """Synthetic transport/norm observations exercise the real retained-field checker.

    Domain assessment is real; the native solve and quadrature observations are
    labelled fixtures. The independent integrator has separate calculus controls.
    """
    pin = {"core": {"core_commit": "TEST_ONLY_NOT_NATIVE", "core_dirty": False}, "files": {}}
    monkeypatch.setattr(runner, "_source_pin", lambda: deepcopy(pin))
    monkeypatch.setattr(runner, "cases", lambda: deepcopy(groups))
    events, norms = [], {}
    original_fields = runner._fields

    def check_fields(experiment, settings, result, folder):
        events.append(("fields", experiment))
        return original_fields(experiment, settings, result, folder)

    def observed_norms(experiment, settings, retained_field):
        count = int(math.isqrt(len(retained_field["node_ids"]))) - 1
        events.append(("norm", experiment, count))
        return deepcopy(norms[experiment, count])

    monkeypatch.setattr(runner, "_fields", check_fields)
    monkeypatch.setattr(runner, "_integrate_field", observed_norms)

    class ProtocolLab:
        def __init__(self, store):
            self.store = store

        def create_study(self, *args):
            pass

        def inspect_experiment(self, experiment):
            events.append(("inspect", experiment))
            return load_json(self.store / "experiments" / experiment / "result.json")

        def run_pde(self, *, experiment_id, settings, **kwargs):
            experiment, mode = experiment_id, modes[experiment_id]
            folder = self.store / "experiments" / experiment
            output = folder / "pde"
            output.mkdir(parents=True)
            model_revision = None
            if mode in ("PASS", "COARSE_FAIL"):
                studies, fields, bindings = synthetic_vector(settings)
                if mode == "COARSE_FAIL":
                    # First rate log2(3)<1.8; final rate log2(16/3)>1.8.
                    for component, value in enumerate((.008, .012)):
                        studies[1]["components"][component]["l2_error"] = value
                    refresh_errors(studies)
                for study, retained_field, binding in zip(studies, fields, bindings):
                    count = study["cells_per_axis"]
                    # Whole-side prescribed integrals are known polynomial fixtures.
                    lx, ly = settings["problem"]["domain"]["lengths"]
                    for side, boundary in retained_field["boundaries"].items():
                        axis, constant = (0, 0.) if side == "xmin" else (0, lx) if side == "xmax" else (1, 0.) if side == "ymin" else (1, ly)
                        length = ly if axis == 0 else lx
                        integral = [0., 0.]
                        for coordinate, weight in runner._QUADRATURE:
                            x, y = (constant, length * coordinate) if axis == 0 else (length * coordinate, constant)
                            for component, value in enumerate(runner._side_value(experiment, settings, side, x, y)):
                                integral[component] += length * weight * value
                        boundary["prescribed_integral"] = integral
                    study["files"] = {key: f"level_n{count}/{name}" for key, name in {
                        "field": "field.xdmf", "field_data": "field.h5", "form_source": "forms.ufl.txt",
                        "dofs": "dofs.json", "binding": "binding.json"}.items()}
                    for relative in study["files"].values():
                        path = output / relative
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(b"TEST_ONLY synthetic transport; no native solve\n")
                    save_json(output / study["files"]["dofs"], retained_field)
                    save_json(output / study["files"]["binding"], binding)
                    study["artifact_sha256"] = {key: runner._sha(output / relative) for key, relative in study["files"].items()}
                    save_json(output / f"level_n{count}/observation.json", study)
                    norms[experiment, count] = {"l2": study["l2_error"], "h1": study["h1_seminorm_error"],
                        "component_l2": [row["l2_error"] for row in study["components"]],
                        "component_h1": [row["h1_seminorm_error"] for row in study["components"]]}
                assessment = domain.assess(settings, studies, fields, bindings)
                checks, metrics = assessment["checks"], assessment["metrics"]
                if missing_reason:
                    for metric in metrics.values():
                        metric.pop("reason", None)
                save_json(output / "worker_result.json", {"mesh_studies": studies})
                save_json(output / "progress.json", {"schema_version": "1", "status": "COMPLETED",
                    "completed": [{"cells_per_axis": count} for count in settings["mesh"]["cell_counts"]]})
                passed = all(row["status"] == "PASS" for row in checks)
                status, solver, converged = "COMPLETED_REVIEW_REQUIRED" if passed else "REJECTED", "COMPLETED", True
                save_json(output / "result.json", {"raw_result": "pde/result.json", "solver_status": solver,
                    "converged": converged, "metrics": metrics, "mesh_studies": assessment["mesh_studies"]})
                model_revision = canonical_hash({"settings": settings, "declaration": domain.model_declaration(settings)})
            else:
                checks = [{"code": "pde_preflight" if mode == "NOT_RUN" else "pde_execution", "status": "FAIL",
                           "observed": "TEST_ONLY refusal or native execution failure", "limit": None}]
                metrics, converged = {}, None
                solver = "NOT_RUN" if mode == "NOT_RUN" else mode
                status = "REJECTED" if mode == "NOT_RUN" else "FAILED_EXECUTION"
            result = {"experiment_id": experiment, "status": status, "solver_status": solver, "converged": converged,
                "decision": "NOT_RELEASED", "cad_revision": None, "model_revision": model_revision, "metrics": metrics,
                "validations": [{"type": row["code"], "status": row["status"], "threshold": row.get("limit")} for row in checks]
                    + [{"type": kind, "status": "UNKNOWN"} for kind in ("physical_validation", "model_qualification")],
                "evidence": [{"observation": deepcopy(row)} for row in checks], "provenance": deepcopy(pin["core"]),
                "artifacts": [{"path": str(path.relative_to(folder)), "sha256": runner._sha(path)}
                              for path in output.rglob("*") if path.is_file()]}
            save_json(folder / "result.json", result)
            save_json(folder / "thread.json", {"experiment": experiment, "test_only": True})
            save_json(self.store / "ledger" / f"{experiment}.json", {"experiment_id": experiment,
                "result_sha256": "tampered" if bad_ledger else runner._sha(folder / "result.json"),
                "thread_sha256": runner._sha(folder / "thread.json")})
            return result

    monkeypatch.setattr(runner, "Lab", ProtocolLab)
    return events


def test_coarse_failure_keeps_actual_verdict_all_fields_and_case_before_detailed_failure(tmp_path, monkeypatch):
    events = protocol_run(monkeypatch, ({"E-vector-mixed": small_settings()}, {}, {}), {"E-vector-mixed": "COARSE_FAIL"})
    store = tmp_path / "new"
    with pytest.raises(AssertionError, match="Wrong vector numerical classification") as failure:
        runner.run(store)
    result_path = store / "experiments/E-vector-mixed/result.json"
    result = load_json(result_path)
    progress = load_json(store / "acceptance_progress.json")
    case, = progress["cases"]
    assert progress["status"] == "FAILED_OR_PARTIAL" and not (store / "acceptance.json").exists()
    assert result["status"] == case["status"] == "REJECTED" and case["solver_status"] == "COMPLETED"
    assert all(not row["valid"] and "pde_l2_convergence_rate" in row["reason"] for row in result["metrics"].values())
    assert case["metrics"] == result["metrics"] and case["result_sha256"] == runner._sha(result_path)
    assert case["field_verification"] == "VERIFIED_COMPLETE" and len(case["field_norm_closure"]) == 3
    assert events == [("inspect", "E-vector-mixed"), ("fields", "E-vector-mixed"),
                      *(('norm', 'E-vector-mixed', count) for count in (1, 2, 4))]
    diagnostic = case["diagnostics"]
    check, = diagnostic["failed_checks"]
    assert check["code"] == "pde_l2_convergence_rate" and check["limit"] == 1.8
    assert check["observed"]["vector"][0] < 1.8 < check["observed"]["vector"][1]
    assert diagnostic["expected_status"] == "COMPLETED_REVIEW_REQUIRED" and diagnostic["actual_status"] == "REJECTED"
    for text in ("E-vector-mixed", "COMPLETED_REVIEW_REQUIRED", "REJECTED", "pde_l2_convergence_rate", "1.8", runner._sha(result_path)):
        assert text in str(failure.value) and text in progress["error"]


def test_normal_numerical_and_preflight_categories_keep_their_actual_metrics(tmp_path, monkeypatch):
    settings = small_settings()
    refused = deepcopy(settings)
    refused["problem"]["weak_form"]["lame_mu"] = 0.
    events = protocol_run(monkeypatch, ({"E-vector-mixed": settings}, {"E-vector-protocol-reject": settings}, {"E-refused": refused}),
        {"E-vector-mixed": "PASS", "E-vector-protocol-reject": "COARSE_FAIL", "E-refused": "NOT_RUN"})
    report = runner.run(tmp_path / "new")
    assert report["status"] == "PASS_BOUNDED_MATHEMATICAL"
    first, second, third = report["cases"]
    assert first["status"] == "COMPLETED_REVIEW_REQUIRED" and all(row["valid"] for row in first["metrics"].values())
    assert second["status"] == "REJECTED" and all(not row["valid"] and row["reason"] for row in second["metrics"].values())
    assert third["solver_status"] == "NOT_RUN" and third["metrics"] == {} and third["field_verification"] == "NOT_RUN_PREFLIGHT"
    assert not any(event[0] in ("fields", "norm") and event[1] == "E-refused" for event in events)


@pytest.mark.parametrize("mode", ["NOT_RUN", "FAILED_EXECUTION", "FAILED"])
def test_incomplete_native_execution_keeps_diagnostic_without_field_or_numerical_claim(tmp_path, monkeypatch, mode):
    events = protocol_run(monkeypatch, ({"E-vector-mixed": small_settings()}, {}, {}), {"E-vector-mixed": mode})
    store = tmp_path / "new"
    with pytest.raises(AssertionError, match="Wrong vector native execution classification") as failure:
        runner.run(store)
    progress = load_json(store / "acceptance_progress.json")
    case, = progress["cases"]
    assert progress["status"] == "FAILED_OR_PARTIAL" and events == [("inspect", "E-vector-mixed")]
    assert case["solver_status"] == mode and case["field_verification"] == "NOT_CHECKED_NATIVE_EXECUTION"
    assert case["field_norm_closure"] == [] and case["metrics"] == {}
    assert case["diagnostics"]["failed_checks"][0]["observed"] == "TEST_ONLY refusal or native execution failure"
    assert case["result_sha256"] in str(failure.value) and mode in progress["error"]
    assert not (store / "acceptance.json").exists()


@pytest.mark.parametrize("fault,message", [("reason", "invalid-metric reasons"), ("ledger", "ledger/result/thread mismatch")])
def test_corrupt_evidence_cannot_be_saved_as_verified_numerical_case(tmp_path, monkeypatch, fault, message):
    events = protocol_run(monkeypatch, ({"E-vector-mixed": small_settings()}, {}, {}), {"E-vector-mixed": "COARSE_FAIL"},
                          missing_reason=fault == "reason", bad_ledger=fault == "ledger")
    store = tmp_path / "new"
    with pytest.raises(AssertionError, match=message):
        runner.run(store)
    progress = load_json(store / "acceptance_progress.json")
    assert progress["status"] == "FAILED_OR_PARTIAL" and progress["cases"] == []
    assert not (store / "acceptance.json").exists()
    assert any(event[0] == "fields" for event in events) is (fault == "reason")
