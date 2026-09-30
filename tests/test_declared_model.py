"""Declared-model Core contract tests; no adapter here executes real physics."""

from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from caelab import Lab
from caelab.contracts import CapabilityUnavailable
from caelab.schema import validate as validate_schema
from caelab.storage import canonical_hash, load_json, save_json


STUDY = "S-declared-model"


def _settings():
    return {"mesh": {"cell_count": 4},
            "research": {"source": "TEST ONLY: common model fixture"}}


def _declaration():
    return {
        "model": {
            "geometry": {"kind": "declared_block",
                         "dimensions": {"length": {"value": 10.0, "unit": "mm"}}},
            "mesh": {"method": "test_only", "cell_count": 4},
            "materials": [{"id": "test-material", "source": "TEST ONLY", "qualified": False}],
            "sections": [{"id": "test-section", "type": "solid"}],
            "interfaces": [], "contact": [], "coordinate_systems": [{"id": "global", "unit": "mm"}],
        },
        "boundary_conditions": [{"type": "prescribed_displacement", "region": "fixed",
                                 "value": [0.0, 0.0, 0.0], "unit": "mm"}],
        "loads": [{"type": "force", "region": "loaded", "value": [0.0, 0.0, -1.0],
                   "unit": "N", "source": "TEST ONLY"}],
        "initial_conditions": [{"type": "displacement", "value": [0.0, 0.0, 0.0], "unit": "mm"}],
        "outputs": {"fields": [{"name": "displacement", "unit": "mm"}],
                    "history": [{"name": "strain_energy", "unit": "mJ"}], "metrics": ["test_response"]},
        "reference": {"source": "TEST ONLY: not an analytical physics acceptance"},
    }


class CountingModel:
    """A second, scalar-model case has no optional describe_model method."""

    backend = "test.model.scalar"
    version = "test-only-1"
    domain = "material"
    physics_domain = "scalar_material"
    analysis_type = "material_point_test"
    default_metrics = ["test_response"]
    metric_unit = "1"

    def __init__(self, *, mode="complete", mutate_inputs=False, raw_reference=None):
        self.calls = 0
        self.mode = mode
        self.mutate_inputs = mutate_inputs
        self.raw_reference = raw_reference

    def solve(self, output, settings):
        self.calls += 1
        output.mkdir()
        save_json(output / "input.json", settings)
        (output / "raw.log").write_text("TEST ONLY: synthetic model observation, no solver executed\n")
        if self.mode == "crash":
            raise RuntimeError("test-only infrastructure failed after partial files")
        if self.mutate_inputs:
            settings["mesh"]["cell_count"] = 999
            if hasattr(self, "declaration"):
                self.declaration["model"]["geometry"]["dimensions"]["length"]["value"] = 999.0
                self.declaration["loads"][0]["value"][-1] = -999.0
        outcome = {"status": "COMPLETED", "solver_status": "COMPLETED", "converged": True,
                   "checks": [{"code": "test_model_screen", "status": "PASS", "observed": 0.01, "limit": 0.02}],
                   "metrics": {"test_response": {"value": 0.01, "unit": self.metric_unit, "valid": True}},
                   "pending_validations": ["test_domain_qualification"],
                   "provenance": {"versions": {"solver": "TEST-ONLY"}, "test_only": True},
                   "raw_result": self.raw_reference or f"{output.name}/raw.log"}
        if self.mode == "numerical_rejection":
            outcome["status"] = "REJECTED"
            outcome["checks"][0].update(status="FAIL", observed=0.05)
            outcome["metrics"]["test_response"].update(
                value=0.05, valid=False, reason="TEST ONLY: numerical screen rejected this observation")
        elif self.mode == "contradictory_completion":
            outcome["solver_status"] = "NOT_RUN"
        elif self.mode == "spoof_identity":
            outcome.update(cad_revision="test-only-fake-cad", model_revision="0" * 64,
                           parent_experiment_id="E-test-only-fake-parent",
                           artifacts=[{"path": "../../outside.log", "sha256": "0" * 64}])
            outcome["provenance"].update(cad_revision="test-only-fake-cad", model_revision="0" * 64)
        return outcome


class DeclaredModel(CountingModel):
    """Complete common metadata, still an explicitly test-only observation."""

    backend = "test.model.elasticity"
    domain = "structure"
    physics_domain = "solid_mechanics"
    analysis_type = "linear_static"
    metric_unit = "mm"

    def __init__(self, *, declaration_error=None, declaration_mutator=None, **kwargs):
        super().__init__(**kwargs)
        self.describe_calls = 0
        self.declaration = _declaration()
        self.declaration_error = declaration_error
        self.declaration_mutator = declaration_mutator

    def describe_model(self, settings):
        self.describe_calls += 1
        if self.declaration_error:
            raise self.declaration_error
        if self.mutate_inputs:
            settings["mesh"]["cell_count"] = 998
        if self.declaration_mutator:
            return self.declaration_mutator(self.declaration)
        return self.declaration


class ForbiddenParentAnalysis:
    backend = "test.parent-gate"
    version = "test-only-1"
    analysis_type = "linear_static"
    default_metrics = ["test_response"]

    def solve(self, *args, **kwargs):
        pytest.fail("CAD-parent analysis must reject a non-CAD model before invoking an adapter")


def _lab(path, model=None, scalar=None, pde=None):
    model = model if model is not None else DeclaredModel()
    scalar = scalar if scalar is not None else CountingModel()
    lab = Lab(path, adapters={}, analysis_adapters={ForbiddenParentAnalysis.backend: ForbiddenParentAnalysis()},
              doe_adapters={}, optimization_adapters={}, pde_adapters=pde or {},
              model_analysis_adapters={model.backend: model, scalar.backend: scalar})
    lab.create_study(STUDY, "Declared models", "Do distinct model families share the same evidence contract?",
                     "Numerical model identity is independent of a CAD parent",
                     "Preserve common declarations and immutable records")
    return lab, model, scalar


def _run(lab, *, experiment_id="E-declared", backend=DeclaredModel.backend, settings=None, **changes):
    return lab.run_model_analysis(study_id=STUDY, experiment_id=experiment_id, backend=backend,
                                  settings=_settings() if settings is None else settings, **changes)


def _files(folder):
    return {path.relative_to(folder).as_posix(): path.read_bytes()
            for path in folder.rglob("*") if path.is_file()}


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_two_non_cad_models_share_typed_records_evidence_and_revision_contract(tmp_path):
    lab, model, scalar = _lab(tmp_path)
    declared = _run(lab, hypothesis_id="H-declared")
    simple = _run(lab, experiment_id="E-scalar", backend=scalar.backend)
    assert model.calls == scalar.calls == model.describe_calls == 1
    assert declared["model_revision"] != simple["model_revision"]
    for result, adapter, declaration in ((declared, model, _declaration()), (simple, scalar, {})):
        identifier = result["experiment_id"]
        folder = lab.store / "experiments" / identifier
        proposal = load_json(folder / "proposal.json")
        thread = load_json(folder / "thread.json")
        ledger = load_json(lab.store / "ledger" / f"{identifier}.json")
        model_revision = canonical_hash({"settings": _settings(), "declaration": declaration})
        assert result["status"] == "COMPLETED_REVIEW_REQUIRED" and result["decision"] == "NOT_RELEASED"
        assert result["cad_revision"] is None and "parent_experiment_id" not in result
        assert "parent_experiment_id" not in proposal and "parent_experiment" not in thread
        assert proposal["domain"] == adapter.domain
        assert proposal["physics"] == {"domain": adapter.physics_domain,
                                       "analysis_type": adapter.analysis_type, "backend": adapter.backend}
        assert proposal["parameters"] == result["input_parameters"] == {}
        assert proposal["registry_revision"] == result["registry_revision"] == 0
        assert proposal["model_revision"] == result["model_revision"] == thread["model_revision"] == model_revision
        assert result["proposal_revision"] == canonical_hash(proposal)
        assert result["provenance"]["proposal_sha256"] == canonical_hash(proposal)
        assert result["provenance"]["execution_settings"] == _settings()
        assert result["provenance"]["solver"]["versions"] == {"solver": "TEST-ONLY"}
        assert result["extensions"]["model_analysis"]["model_revision"] == model_revision
        assert proposal["extensions"] == result["extensions"]
        assert ledger["result_sha256"] == _sha(folder / "result.json")
        assert ledger["thread_sha256"] == _sha(folder / "thread.json")
        assert thread["cad_revision"] is None and thread["run"] == identifier
        assert thread["evidence"] == [evidence["id"] for evidence in result["evidence"]]
        artifacts = {artifact["path"]: artifact for artifact in result["artifacts"]}
        assert {"proposal.json", "registry_snapshot.json", "simulation/input.json", "simulation/raw.log"} <= artifacts.keys()
        for name, artifact in artifacts.items():
            assert artifact["sha256"] == _sha(folder / name)
            assert artifact["size_bytes"] == (folder / name).stat().st_size
            assert artifact["revision"] == result["proposal_revision"]
        evidence_ids = {evidence["id"] for evidence in result["evidence"]}
        assert all(evidence["source"] == adapter.backend and evidence["artifact"] == "simulation/raw.log"
                   for evidence in result["evidence"])
        assert all(set(validation["evidence_ids"]) <= evidence_ids for validation in result["validations"])
        assert {"model_qualification", "physical_validation", "test_domain_qualification"} <= {
            validation["type"] for validation in result["validations"] if validation["status"] == "UNKNOWN"}
        assert lab.inspect_experiment(identifier) == result
        assert lab.research_summary(identifier)["model_revision"] == model_revision
        validate_schema("experiment", proposal)
        validate_schema("result", result)
    declared_proposal = load_json(lab.store / "experiments/E-declared/proposal.json")
    assert declared_proposal["model"] == _declaration()["model"]
    assert declared_proposal["outputs"] == _declaration()["outputs"]
    for field in ("boundary_conditions", "loads", "initial_conditions"):
        assert declared_proposal[field] == _declaration()[field]
    assert declared["extensions"]["model_analysis"]["declaration"] == _declaration()
    assert simple["extensions"]["model_analysis"] == {"model_revision": simple["model_revision"]}
    comparison = lab.compare(["E-declared", "E-scalar"])
    assert [summary["model_revision"] for summary in comparison] == [declared["model_revision"], simple["model_revision"]]
    assert [summary["metrics"]["test_response"]["unit"] for summary in comparison] == ["mm", "1"]
    with pytest.raises(ValueError, match="completed, verified CAD"):
        lab.run_analysis(parent_experiment_id="E-declared", experiment_id="E-forbidden-child",
                         backend=ForbiddenParentAnalysis.backend, settings={})
    assert not (lab.store / "experiments/E-forbidden-child").exists()


def test_settings_and_returned_declaration_mutations_cannot_change_frozen_inputs(tmp_path):
    adapter = DeclaredModel(mutate_inputs=True)
    original_settings = _settings()
    expected_settings = deepcopy(original_settings)
    expected_declaration = deepcopy(adapter.declaration)
    lab, _, _ = _lab(tmp_path, model=adapter)
    result = _run(lab, settings=original_settings)
    proposal = load_json(lab.store / "experiments/E-declared/proposal.json")
    assert original_settings == expected_settings
    assert adapter.declaration != expected_declaration
    assert proposal["model"] == expected_declaration["model"]
    assert proposal["loads"] == expected_declaration["loads"]
    assert proposal["execution"] == result["provenance"]["execution_settings"] == expected_settings
    assert result["extensions"]["model_analysis"]["declaration"] == expected_declaration
    assert result["model_revision"] == canonical_hash({"settings": expected_settings, "declaration": expected_declaration})
    assert lab.inspect_experiment("E-declared") == result


def test_pre_reservation_capability_settings_and_ids_and_duplicate_preservation(tmp_path):
    lab, model, scalar = _lab(tmp_path)
    with pytest.raises(CapabilityUnavailable, match="No executable model analysis adapter"):
        _run(lab, backend="test.missing")
    for invalid_settings in ([], {"nonfinite": float("nan")}):
        with pytest.raises(ValueError):
            _run(lab, settings=invalid_settings)
    with pytest.raises(ValueError, match="Invalid"):
        _run(lab, experiment_id="../outside")
    assert model.calls == scalar.calls == model.describe_calls == 0
    assert not (lab.store / "experiments/E-declared").exists()
    assert not (lab.store / "ledger/E-declared.json").exists()
    result = _run(lab)
    retained = _files(lab.store / "experiments/E-declared")
    with pytest.raises(FileExistsError):
        _run(lab, settings={"mesh": {"cell_count": 8}})
    assert model.calls == 1
    assert _files(lab.store / "experiments/E-declared") == retained
    assert lab.inspect_experiment("E-declared") == result


@pytest.mark.parametrize("error,expected_status", [
    pytest.param(ValueError("test-only invalid model input"), "REJECTED", id="invalid-declaration"),
    pytest.param(RuntimeError("test-only declaration dependency unavailable"), "FAILED_EXECUTION", id="declaration-infrastructure"),
])
def test_declaration_failure_is_retained_and_never_invokes_solve(tmp_path, error, expected_status):
    lab, adapter, _ = _lab(tmp_path, model=DeclaredModel(declaration_error=error))
    result = _run(lab)
    assert result["status"] == expected_status and result["decision"] == "NOT_RELEASED"
    assert result["solver_status"] == ("NOT_RUN" if expected_status == "REJECTED" else "FAILED_EXECUTION")
    assert result["metrics"] == {} and result["converged"] is None
    assert adapter.describe_calls == 1 and adapter.calls == 0
    assert not (lab.store / "experiments/E-declared/simulation").exists()
    expected_check = "model_declaration" if expected_status == "REJECTED" else "model_analysis_execution"
    assert any(validation["type"] == expected_check and validation["status"] == "FAIL"
               for validation in result["validations"])
    assert all(evidence["artifact"] == "proposal.json" for evidence in result["evidence"])
    assert lab.inspect_experiment("E-declared") == result


@pytest.mark.parametrize("mutation", [
    pytest.param(lambda declaration: ["not", "a", "mapping"], id="nonmapping-declaration"),
    pytest.param(lambda declaration: {**declaration, "outputs": None}, id="malformed-outputs"),
    pytest.param(lambda declaration: {**declaration, "boundary_conditions": {}}, id="malformed-boundary"),
])
def test_malformed_adapter_declaration_is_a_retained_contract_failure(tmp_path, mutation):
    lab, adapter, _ = _lab(tmp_path, model=DeclaredModel(declaration_mutator=mutation))
    result = _run(lab)
    assert result["status"] == "FAILED_EXECUTION" and result["solver_status"] == "FAILED_EXECUTION"
    assert result["decision"] == "NOT_RELEASED" and adapter.calls == 0
    assert not (lab.store / "experiments/E-declared/simulation").exists()
    assert lab.inspect_experiment("E-declared") == result


@pytest.mark.parametrize("mode,expected_status", [("crash", "FAILED_EXECUTION"), ("numerical_rejection", "REJECTED"),
                                                  ("contradictory_completion", "FAILED_EXECUTION")])
def test_partial_infrastructure_failure_is_distinct_from_completed_numerical_rejection(tmp_path, mode, expected_status):
    lab, adapter, _ = _lab(tmp_path, model=DeclaredModel(mode=mode))
    result = _run(lab)
    assert result["status"] == expected_status and result["decision"] == "NOT_RELEASED"
    assert adapter.calls == 1
    assert {"simulation/input.json", "simulation/raw.log"} <= {artifact["path"] for artifact in result["artifacts"]}
    if mode == "numerical_rejection":
        assert result["solver_status"] == "COMPLETED" and result["converged"] is True
        assert result["metrics"]["test_response"] == {
            "value": 0.05, "unit": "mm", "valid": False,
            "reason": "TEST ONLY: numerical screen rejected this observation"}
        assert lab.research_summary("E-declared")["failures"][0]["type"] == "test_model_screen"
    else:
        assert result["solver_status"] == "FAILED_EXECUTION" and result["converged"] is None
        assert result["metrics"] == {}
        assert lab.research_summary("E-declared")["failures"][0]["type"] == "model_analysis_execution"
    assert lab.inspect_experiment("E-declared") == result


@pytest.mark.parametrize("raw_reference", ["../../outside.log", "ABSOLUTE"])
def test_external_evidence_and_spoofed_identity_cannot_replace_core_records(tmp_path, raw_reference):
    outside = tmp_path / "outside.log"
    outside.write_text("TEST ONLY: must not be registered as experiment evidence\n")
    if raw_reference == "ABSOLUTE":
        raw_reference = str(outside.resolve())
    lab, _, _ = _lab(tmp_path / "store", model=DeclaredModel(mode="spoof_identity", raw_reference=raw_reference))
    result = _run(lab)
    assert result["cad_revision"] is None and "parent_experiment_id" not in result
    assert result["model_revision"] == canonical_hash({"settings": _settings(), "declaration": _declaration()})
    assert all(evidence["artifact"] == "proposal.json" for evidence in result["evidence"])
    assert all(not Path(artifact["path"]).is_absolute() and ".." not in Path(artifact["path"]).parts
               for artifact in result["artifacts"])
    assert "simulation/raw.log" in {artifact["path"] for artifact in result["artifacts"]}
    assert lab.inspect_experiment("E-declared") == result


def test_result_proposal_thread_and_raw_tampering_are_hash_checked(tmp_path):
    lab, _, _ = _lab(tmp_path)
    result = _run(lab)
    folder = lab.store / "experiments/E-declared"
    for relative in ("result.json", "proposal.json", "thread.json", "simulation/raw.log"):
        path = folder / relative
        original = path.read_bytes()
        if path.suffix == ".json":
            document = load_json(path)
            document["tampered"] = True
            save_json(path, document)
        else:
            path.write_bytes(original + b"tampered\n")
        try:
            with pytest.raises(ValueError, match="(?i)hash mismatch"):
                lab.inspect_experiment("E-declared")
        finally:
            path.write_bytes(original)
        assert lab.inspect_experiment("E-declared") == result


@pytest.mark.parametrize("document", ["result", "proposal", "thread"])
def test_model_revision_consistency_is_checked_even_after_synthetic_hash_reanchoring(tmp_path, document):
    """Reanchor only test fixtures to exercise the semantic check beyond hashes."""
    lab, _, _ = _lab(tmp_path)
    _run(lab)
    folder = lab.store / "experiments/E-declared"
    path = folder / f"{document}.json"
    mutated = load_json(path)
    mutated["model_revision"] = "0" * 64
    save_json(path, mutated)
    if document == "proposal":
        result = load_json(folder / "result.json")
        artifact = next(artifact for artifact in result["artifacts"] if artifact["path"] == "proposal.json")
        artifact.update(sha256=_sha(path), size_bytes=path.stat().st_size)
        save_json(folder / "result.json", result)
    ledger_path = lab.store / "ledger/E-declared.json"
    ledger = load_json(ledger_path)
    ledger.update(result_sha256=_sha(folder / "result.json"), thread_sha256=_sha(folder / "thread.json"))
    save_json(ledger_path, ledger)
    with pytest.raises(ValueError, match="(?i)model revision mismatch"):
        lab.inspect_experiment("E-declared")


def test_pde_namespace_and_legacy_records_without_top_level_model_revision_remain_compatible(tmp_path):
    class LegacyPDE(CountingModel):
        backend = "test.pde.compatibility"
        domain = "pde"
        physics_domain = "scalar_elliptic"
        analysis_type = "weak_form_benchmark"

        def describe_model(self, settings):
            pytest.fail("Compatible PDE calls must preserve their settings-only revision")

    adapter = LegacyPDE()
    lab, _, _ = _lab(tmp_path, pde={adapter.backend: adapter})
    result = lab.run_pde(study_id=STUDY, experiment_id="E-legacy-pde",
                         backend=adapter.backend, settings=_settings())
    folder = lab.store / "experiments/E-legacy-pde"
    proposal = load_json(folder / "proposal.json")
    assert adapter.calls == 1 and result["model_revision"] == canonical_hash(_settings())
    assert result["extensions"] == {"pde": {"model_revision": canonical_hash(_settings())}}
    assert proposal["extensions"] == result["extensions"]
    assert {"pde/input.json", "pde/raw.log"} <= {artifact["path"] for artifact in result["artifacts"]}
    assert all(evidence["artifact"] == "pde/raw.log" for evidence in result["evidence"])
    # A self-contained legacy envelope reproduces the pre-optional-field schema.
    proposal.pop("model_revision")
    result.pop("model_revision")
    save_json(folder / "proposal.json", proposal)
    result["proposal_revision"] = result["provenance"]["proposal_sha256"] = canonical_hash(proposal)
    for artifact in result["artifacts"]:
        artifact["revision"] = result["proposal_revision"]
        if artifact["path"] == "proposal.json":
            artifact.update(sha256=_sha(folder / "proposal.json"), size_bytes=(folder / "proposal.json").stat().st_size)
    save_json(folder / "result.json", result)
    ledger_path = lab.store / "ledger/E-legacy-pde.json"
    ledger = load_json(ledger_path)
    ledger.update(result_sha256=_sha(folder / "result.json"), thread_sha256=_sha(folder / "thread.json"))
    save_json(ledger_path, ledger)
    validate_schema("experiment", proposal)
    validate_schema("result", result)
    assert lab.inspect_experiment("E-legacy-pde") == result
    assert lab.research_summary("E-legacy-pde")["model_revision"] is None
    assert lab.research_summary("E-legacy-pde")["decision"] == "NOT_RELEASED"
