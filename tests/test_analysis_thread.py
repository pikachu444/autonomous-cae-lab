"""The solver contract must preserve an immutable, verified CAD parent."""

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from caelab import Lab


class EvidenceAdapter:
    backend = "test.structural"
    version = "test-1"
    analysis_type = "linear_static"
    default_metrics = ["max_displacement"]

    def solve(self, parent_result, parent_root, output, settings):
        source = parent_root / "cad/assembly.step"
        assert parent_result["cad_revision"]
        output.mkdir()
        shutil.copy2(source, output / "input.step")
        (output / "solver.log").write_text("Test adapter: no physical solver\n")
        return {"status": "COMPLETED", "solver_status": "CONVERGED", "converged": True,
                "checks": [{"code": "input_geometry", "status": "PASS",
                            "observed": hashlib.sha256(source.read_bytes()).hexdigest()}],
                "metrics": {"max_displacement": {"value": 0.25, "unit": "mm", "valid": True}},
                "pending_validations": ["static_strength", "physical_load_test"],
                "provenance": {"mesh": "simulation/input.step", "solver": "test-adapter",
                               "solver_deck": None},
                "raw_result": "simulation/solver.log"}


def cad_parent(tmp_path):
    lab = Lab(tmp_path, analysis_adapters={EvidenceAdapter.backend: EvidenceAdapter()})
    lab.create_study("S-solver", "Fixture analysis", "Does a wider support pass CAD?",
                     "38 mm remains CAD-valid", "Preserve the CAD model for analysis")
    lab.register_parameter("S-solver", "fixture.cadquery", "roller_support",
                           "support_width_mm", "support_width", "Support width", 28, 60)
    valid = lab.run_experiment(study_id="S-solver", experiment_id="E-cad",
                               backend="fixture.cadquery", model="roller_support",
                               values={"support_width": 38})
    return lab, valid


def test_solver_child_preserves_parent_revision_and_evidence(tmp_path):
    lab, parent = cad_parent(tmp_path)
    original = (tmp_path / "experiments/E-cad/result.json").read_bytes()
    child = lab.run_analysis(parent_experiment_id="E-cad", experiment_id="E-solver",
                             backend="test.structural", settings={"load": {"force_N": 100}})
    assert child["status"] == "COMPLETED_REVIEW_REQUIRED"
    assert child["decision"] == "NOT_RELEASED"
    assert child["parent_experiment_id"] == "E-cad"
    assert child["cad_revision"] == parent["cad_revision"]
    assert child["provenance"]["parent_result_sha256"] == hashlib.sha256(original).hexdigest()
    assert (tmp_path / "experiments/E-cad/result.json").read_bytes() == original
    assert {"simulation/input.step", "simulation/solver.log"} <= {
        a["path"] for a in child["artifacts"]}
    assert lab.research_summary("E-solver")["parent_experiment_id"] == "E-cad"
    assert "physical_load_test" in lab.research_summary("E-solver")["unknown"]
    assert "machine_interface" in lab.research_summary("E-solver")["unknown"]
    assert lab.inspect_experiment("E-solver") == child
    with pytest.raises(FileExistsError):
        lab.run_analysis(parent_experiment_id="E-cad", experiment_id="E-solver",
                         backend="test.structural", settings={})

    schema = json.loads((Path(__file__).resolve().parents[1] /
                         "schemas/result.schema.json").read_text())
    pytest.importorskip("jsonschema").validate(child, schema)
    (tmp_path / "experiments/E-cad/cad/report.html").write_text("tampered")
    with pytest.raises(ValueError, match="Artifact hash mismatch"):
        lab.inspect_experiment("E-solver")


def test_analysis_refuses_invalid_cad_parent(tmp_path):
    lab, _ = cad_parent(tmp_path)
    lab.register_parameter("S-solver", "fixture.cadquery", "roller_support",
                           "bolt_pitch_x_mm", "bolt_pitch", "Bolt pitch", 18, 40)
    invalid = lab.run_experiment(study_id="S-solver", experiment_id="E-invalid",
                                 backend="fixture.cadquery", model="roller_support",
                                 values={"bolt_pitch": 30})
    assert invalid["status"] == "REJECTED"
    with pytest.raises(ValueError, match="completed, verified CAD"):
        lab.run_analysis(parent_experiment_id="E-invalid", experiment_id="E-solver",
                         backend="test.structural", settings={"load": {"force_N": 100}})
    assert not (tmp_path / "experiments/E-solver").exists()


def test_solver_crash_records_failure_separately(tmp_path):
    lab, parent = cad_parent(tmp_path)

    class CrashingAdapter(EvidenceAdapter):
        def solve(self, parent_result, parent_root, output, settings):
            raise RuntimeError("mesh executable absent")

    lab.analysis_adapters[EvidenceAdapter.backend] = CrashingAdapter()
    failed = lab.run_analysis(parent_experiment_id="E-cad", experiment_id="E-crash",
                              backend="test.structural", settings={})
    assert failed["status"] == "FAILED_EXECUTION" and failed["decision"] == "NOT_RELEASED"
    assert failed["solver_status"] == "FAILED_EXECUTION"
    assert failed["cad_revision"] == parent["cad_revision"]
    assert lab.inspect_experiment("E-cad")["status"] == "COMPLETED_REVIEW_REQUIRED"


def test_malformed_solver_response_is_a_persisted_failure(tmp_path):
    lab, _ = cad_parent(tmp_path)

    class MalformedAdapter(EvidenceAdapter):
        def solve(self, parent_result, parent_root, output, settings):
            return {"status": "COMPLETED", "checks": [], "metrics": {"broken": {"value": float("nan")}},
                    "solver_status": "COMPLETED", "converged": True,
                    "pending_validations": ["static_strength"], "provenance": {},
                    "raw_result": None}

    lab.analysis_adapters[EvidenceAdapter.backend] = MalformedAdapter()
    failed = lab.run_analysis(parent_experiment_id="E-cad", experiment_id="E-malformed",
                              backend="test.structural", settings={})
    assert failed["status"] == "FAILED_EXECUTION"
    assert lab.inspect_experiment("E-malformed")["status"] == "FAILED_EXECUTION"


def test_backend_cannot_replace_parent_identity_or_reference_external_evidence(tmp_path):
    lab, parent = cad_parent(tmp_path)

    class SpoofingAdapter(EvidenceAdapter):
        def solve(self, parent_result, parent_root, output, settings):
            outcome = super().solve(parent_result, parent_root, output, settings)
            outcome["provenance"].update({"parent_experiment_id": "other",
                                          "cad_revision": "spoofed"})
            outcome["raw_result"] = "../../outside.json"
            return outcome

    lab.analysis_adapters[EvidenceAdapter.backend] = SpoofingAdapter()
    child = lab.run_analysis(parent_experiment_id="E-cad", experiment_id="E-spoof",
                             backend="test.structural", settings={})
    assert child["provenance"]["parent_experiment_id"] == "E-cad"
    assert child["cad_revision"] == parent["cad_revision"]
    assert child["evidence"][0]["artifact"] == "proposal.json"
    assert lab.inspect_experiment("E-spoof") == child
