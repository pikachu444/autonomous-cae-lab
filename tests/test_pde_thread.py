"""Core PDE record tests only: dummy observations are not FEniCSx acceptance."""

from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from caelab import Lab
from caelab.contracts import CapabilityUnavailable
from caelab.storage import canonical_hash, load_json, save_json


STUDY = "S-pde-thread"
EXPERIMENT = "E-pde-thread"


class DummyPDE:
    """Produce test-only raw artifacts and the common numerical outcome."""

    backend = "test.pde"
    version = "test-only-1"
    domain = "pde"
    physics_domain = "scalar_elliptic"
    analysis_type = "weak_form_benchmark"
    default_metrics = ["test_l2_error"]

    def __init__(self, mutate=None, *, crash=False, change_settings=False):
        self.calls = 0
        self.mutate = mutate
        self.crash = crash
        self.change_settings = change_settings

    def solve(self, output, settings):
        self.calls += 1
        output.mkdir()
        save_json(output / "input.json", settings)
        (output / "weak_form.txt").write_text("TEST ONLY: protocol fixture, no assembled weak form\n")
        (output / "raw.txt").write_text("TEST ONLY: synthetic observation, no PDE solution\n")
        if self.crash:
            raise RuntimeError("test-only PDE worker crashed")
        if self.change_settings:
            settings["mesh"]["cell_counts"][0] = 999
        outcome = {"status": "COMPLETED", "solver_status": "COMPLETED", "converged": True,
                   "checks": [{"code": "test_reference_error", "status": "PASS",
                               "observed": 0.001, "limit": 0.003}],
                   "metrics": {"test_l2_error": {"value": 0.001, "unit": "1", "valid": True}},
                   "pending_validations": ["test_domain_qualification"],
                   "provenance": {"versions": {"solver": "TEST-ONLY"}, "test_only": True},
                   "raw_result": "pde/raw.txt"}
        if self.mutate:
            self.mutate(outcome)
        return outcome


def _settings():
    return {"mesh": {"cell_counts": [8, 16, 32]},
            "problem": {"label": "TEST ONLY: Core protocol fixture"},
            "reference": {"source": "Synthetic observation, not analytical solver evidence"}}


def _lab(path, adapter=None):
    adapter = adapter if adapter is not None else DummyPDE()
    lab = Lab(path, adapters={}, analysis_adapters={}, doe_adapters={},
              optimization_adapters={}, pde_adapters={adapter.backend: adapter})
    lab.create_study(STUDY, "PDE contract", "Can a mathematical model retain its own evidence?",
                     "A PDE record does not require a CAD parent", "Check common provenance gates")
    return lab, adapter


def _run(lab, **changes):
    options = {"study_id": STUDY, "experiment_id": EXPERIMENT,
               "backend": DummyPDE.backend, "settings": _settings(), "hypothesis_id": "H-test-pde"}
    options.update(changes)
    return lab.run_pde(**options)


def test_pde_uses_common_schema_evidence_and_hashed_thread_without_a_cad_parent(tmp_path):
    lab, adapter = _lab(tmp_path)
    settings = _settings()
    result = _run(lab, settings=settings)
    folder = lab.store / "experiments" / EXPERIMENT
    proposal = load_json(folder / "proposal.json")
    thread = load_json(folder / "thread.json")
    ledger = load_json(lab.store / "ledger" / f"{EXPERIMENT}.json")
    assert adapter.calls == 1
    assert result["status"] == "COMPLETED_REVIEW_REQUIRED"
    assert result["solver_status"] == "COMPLETED" and result["converged"] is True
    assert result["decision"] == "NOT_RELEASED" and result["cad_revision"] is None
    assert "parent_experiment_id" not in result and "parent_experiment_id" not in proposal
    assert result["input_parameters"] == {} and proposal["parameters"] == {}
    assert proposal["registry_revision"] == 0
    assert proposal["model"]["geometry"] is None
    assert proposal["physics"]["backend"] == DummyPDE.backend
    assert proposal["execution"] == settings
    assert result["proposal_revision"] == canonical_hash(proposal)
    assert result["extensions"]["pde"]["model_revision"] == canonical_hash(settings)
    assert result["provenance"]["execution_settings"] == settings
    assert result["provenance"]["adapter_version"] == DummyPDE.version
    assert result["provenance"]["solver"]["versions"] == {"solver": "TEST-ONLY"}
    assert thread["study"] == STUDY and thread["hypothesis"] == "H-test-pde"
    assert thread["cad_revision"] is None and "parent_experiment" not in thread
    assert thread["model_revision"] == canonical_hash(settings)
    assert thread["experiment"] == EXPERIMENT and thread["run"] == EXPERIMENT
    assert ledger["result_sha256"] == hashlib.sha256((folder / "result.json").read_bytes()).hexdigest()
    assert ledger["thread_sha256"] == hashlib.sha256((folder / "thread.json").read_bytes()).hexdigest()
    artifacts = {item["path"]: item for item in result["artifacts"]}
    assert {"proposal.json", "registry_snapshot.json", "pde/input.json", "pde/weak_form.txt",
            "pde/raw.txt"} <= artifacts.keys()
    for name, artifact in artifacts.items():
        assert artifact["sha256"] == hashlib.sha256((folder / name).read_bytes()).hexdigest()
        assert artifact["size_bytes"] == (folder / name).stat().st_size
        assert artifact["revision"] == result["proposal_revision"]
    evidence = {item["id"]: item for item in result["evidence"]}
    assert thread["evidence"] == list(evidence)
    assert all(item["artifact"] == "pde/raw.txt" for item in evidence.values())
    for validation in result["validations"]:
        assert set(validation["evidence_ids"]) <= evidence.keys()
        assert validation["cad_revision"] is None and validation["solver_run_id"] == EXPERIMENT
    unknown = {v["type"] for v in result["validations"] if v["status"] == "UNKNOWN"}
    assert {"model_qualification", "physical_validation", "test_domain_qualification"} <= unknown
    assert set(lab.research_summary(EXPERIMENT)["unknown"]) == unknown
    assert lab.inspect_experiment(EXPERIMENT) == result
    schemas = Path(__file__).resolve().parents[1] / "schemas"
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(proposal, load_json(schemas / "experiment.schema.json"))
    jsonschema.validate(result, load_json(schemas / "result.schema.json"))


@pytest.mark.parametrize("plugin", ["pde_nonlinear", "pde_elliptic", "pde_transient", "pde_vector"])
def test_optional_pde_declaration_enters_the_common_revision_and_proposal(tmp_path, plugin):
    from importlib import import_module
    reference = import_module("plugins." + plugin + ".reference")
    manufactured_settings, model_declaration = reference.manufactured_settings, reference.model_declaration

    lab, adapter = _lab(tmp_path)
    adapter.describe_model = model_declaration
    adapter.pde_model_declaration = True
    settings = manufactured_settings()
    declaration = model_declaration(settings)
    result = _run(lab, settings=settings)
    proposal = load_json(tmp_path / "experiments" / EXPERIMENT / "proposal.json")
    thread = load_json(tmp_path / "experiments" / EXPERIMENT / "thread.json")
    revision = canonical_hash({"settings": settings, "declaration": declaration})
    assert proposal["model"] == declaration["model"]
    assert proposal["boundary_conditions"] == declaration["boundary_conditions"]
    assert proposal["loads"] == declaration["loads"]
    assert proposal["outputs"]["fields"] == declaration["outputs"]["fields"]
    if plugin == "pde_transient":
        assert proposal["initial_conditions"] == declaration["initial_conditions"]
        assert proposal["outputs"]["history"] == declaration["outputs"]["history"]
    assert result["extensions"]["pde"]["declaration"] == declaration
    assert proposal["model_revision"] == result["model_revision"] == thread["model_revision"] == revision
    assert result["cad_revision"] is None and "parent_experiment_id" not in result
    assert result["decision"] == "NOT_RELEASED" and adapter.calls == 1
    assert result["provenance"]["adapter_details"]["test_only"] is True
    assert lab.inspect_experiment(EXPERIMENT) == result


@pytest.mark.parametrize("mutate", [
    pytest.param(lambda outcome: outcome.update(status="UNKNOWN_STATUS"), id="malformed-status"),
    pytest.param(lambda outcome: outcome["checks"][0].update(status="FINISHED"), id="malformed-check"),
    pytest.param(lambda outcome: outcome["metrics"]["test_l2_error"].pop("unit"), id="malformed-metric"),
    pytest.param(lambda outcome: outcome["metrics"]["test_l2_error"].update(value=None), id="null-valid-metric"),
    pytest.param(lambda outcome: outcome["metrics"]["test_l2_error"].update(value="0.001"), id="string-valid-metric"),
    pytest.param(lambda outcome: outcome.update(solver_status="NOT_RUN"), id="not-run-solver"),
    pytest.param(lambda outcome: outcome.update(solver_status="FAILED_EXECUTION"), id="failed-solver"),
    pytest.param(lambda outcome: outcome.update(converged=False), id="nonconverged-completion"),
    pytest.param(lambda outcome: outcome["metrics"]["test_l2_error"].update(value=float("nan")), id="nan-metric"),
    pytest.param(lambda outcome: outcome["metrics"]["test_l2_error"].update(value=float("inf")), id="infinite-metric"),
    pytest.param(lambda outcome: outcome["checks"][0].update(observed=float("nan")), id="nan-evidence"),
    pytest.param(lambda outcome: outcome["provenance"].update(raw_nonfinite=float("inf")), id="infinite-provenance"),
])
def test_malformed_or_nonfinite_pde_outcome_is_a_retained_failed_execution(tmp_path, mutate):
    lab, adapter = _lab(tmp_path, DummyPDE(mutate))
    result = _run(lab)
    assert result["status"] == "FAILED_EXECUTION" and result["solver_status"] == "FAILED_EXECUTION"
    assert result["converged"] is None and result["decision"] == "NOT_RELEASED"
    assert result["metrics"] == {}
    assert any(v["type"] == "pde_execution" and v["status"] == "FAIL" for v in result["validations"])
    assert "pde/raw.txt" in {a["path"] for a in result["artifacts"]}
    assert {"model_qualification", "physical_validation"} <= set(lab.research_summary(EXPERIMENT)["unknown"])
    assert lab.inspect_experiment(EXPERIMENT) == result and adapter.calls == 1


def test_pde_worker_crash_retains_partial_artifacts_and_failed_status(tmp_path):
    lab, adapter = _lab(tmp_path, DummyPDE(crash=True))
    result = _run(lab)
    assert result["status"] == "FAILED_EXECUTION" and result["decision"] == "NOT_RELEASED"
    assert result["evidence"][0]["artifact"] == "proposal.json"
    assert "test-only PDE worker crashed" in result["evidence"][0]["observation"]["observed"]
    assert "pde/raw.txt" in {a["path"] for a in result["artifacts"]}
    assert lab.inspect_experiment(EXPERIMENT) == result and adapter.calls == 1


def test_completed_pde_numerical_rejection_preserves_invalid_observations(tmp_path):
    def reject(outcome):
        outcome["status"] = "REJECTED"
        outcome["checks"][0].update(status="FAIL", observed=0.02)
        outcome["metrics"]["test_l2_error"].update(
            value=0.02, valid=False, reason="TEST ONLY: reference-error screen failed")

    lab, _ = _lab(tmp_path, DummyPDE(reject))
    result = _run(lab)
    assert result["status"] == "REJECTED"
    assert result["solver_status"] == "COMPLETED" and result["converged"] is True
    assert result["metrics"]["test_l2_error"] == {
        "value": 0.02, "unit": "1", "valid": False,
        "reason": "TEST ONLY: reference-error screen failed"}
    assert result["decision"] == "NOT_RELEASED"
    summary = lab.research_summary(EXPERIMENT)
    assert summary["failures"][0]["type"] == "test_reference_error"
    assert summary["failures"][0]["evidence_ids"]
    assert summary["metrics"]["test_l2_error"]["value"] == 0.02
    assert "pde/raw.txt" in {a["path"] for a in result["artifacts"]}
    assert lab.inspect_experiment(EXPERIMENT) == result


def test_missing_pde_capability_and_invalid_settings_do_not_reserve_an_id(tmp_path):
    lab, adapter = _lab(tmp_path)
    with pytest.raises(CapabilityUnavailable, match="No executable PDE adapter"):
        _run(lab, backend="test.absent")
    for settings in ([], {"nonfinite": float("nan")}):
        with pytest.raises(ValueError):
            _run(lab, settings=settings)
    assert adapter.calls == 0
    assert not (lab.store / "experiments" / EXPERIMENT).exists()
    assert not (lab.store / "ledger" / f"{EXPERIMENT}.json").exists()


def test_pde_duplicate_id_cannot_overwrite_native_or_result_evidence(tmp_path):
    lab, adapter = _lab(tmp_path)
    result = _run(lab)
    folder = lab.store / "experiments" / EXPERIMENT
    before = {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()}
    with pytest.raises(FileExistsError):
        _run(lab, settings={"mesh": {"cell_counts": [4, 8, 16]}})
    assert adapter.calls == 1 and lab.inspect_experiment(EXPERIMENT) == result
    assert {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("relative", ["result.json", "thread.json", "proposal.json", "registry_snapshot.json", "pde/raw.txt"])
def test_pde_hash_tampering_is_detected_for_result_thread_and_raw_artifacts(tmp_path, relative):
    lab, _ = _lab(tmp_path)
    _run(lab)
    path = lab.store / "experiments" / EXPERIMENT / relative
    if path.suffix == ".json":
        document = load_json(path)
        document["tampered"] = True
        save_json(path, document)
    else:
        path.write_bytes(path.read_bytes() + b"tampered\n")
    with pytest.raises(ValueError, match="(?i)hash mismatch"):
        lab.inspect_experiment(EXPERIMENT)


def test_backend_mutation_cannot_change_request_revision_or_external_evidence_ref(tmp_path):
    def external_reference(outcome):
        outcome["raw_result"] = "../../outside.txt"
        outcome["provenance"]["cad_revision"] = "test-only-spoof"

    lab, _ = _lab(tmp_path, DummyPDE(external_reference, change_settings=True))
    settings = _settings()
    expected = deepcopy(settings)
    result = _run(lab, settings=settings)
    assert settings == expected
    assert result["provenance"]["execution_settings"] == expected
    assert result["extensions"]["pde"]["model_revision"] == canonical_hash(expected)
    assert result["cad_revision"] is None
    assert all(e["artifact"] == "proposal.json" for e in result["evidence"])
    assert lab.inspect_experiment(EXPERIMENT) == result
