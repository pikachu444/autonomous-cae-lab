"""Actual Core envelope controls with labelled source-only adapter fixtures."""

from copy import deepcopy

import pytest

from caelab import Lab
from caelab.storage import save_json, load_json
from scripts import verify_vector_pde, verify_coupled_pde


class SourceOnlyAdapter:
    backend = "test.source_only_pde"
    version = "1"
    domain = "mathematics"
    physics_domain = "mathematics"
    analysis_type = "source_fixture"
    default_metrics = ["source_marker"]

    def solve(self, output, settings):
        output.mkdir()
        raw = {"source_only_fixture": True, "marker": "not native numerical evidence"}
        outcome = {"status": "COMPLETED", "solver_status": "COMPLETED", "converged": True,
            "checks": [{"code": "source_only", "status": "PASS", "observed": "synthetic adapter"}],
            "metrics": {"source_marker": {"value": 1., "unit": "1", "valid": True}},
            "pending_validations": ["physical_validation", "model_qualification"],
            "provenance": {"source_only_fixture": True}, "raw_result": "pde/result.json",
            "mesh_studies": [deepcopy(raw)]}
        save_json(output / "worker_result.json", {"mesh_studies": [raw]})
        save_json(output / "result.json", outcome)
        return outcome


@pytest.fixture
def source_result(tmp_path):
    adapter = SourceOnlyAdapter()
    lab = Lab(tmp_path, adapters={}, analysis_adapters={}, doe_adapters={},
        optimization_adapters={}, pde_adapters={adapter.backend: adapter}, model_analysis_adapters={})
    lab.create_study("S-source", "Envelope regression", "Where are assessed observations stored?",
                     "The adapter artifact retains them", "No native qualification")
    result = lab.run_pde(study_id="S-source", experiment_id="E-source",
                         backend=adapter.backend, settings={"source_only_fixture": True})
    assert lab.inspect_experiment("E-source") == result
    assert result["decision"] == "NOT_RELEASED"
    assert "mesh_studies" not in result["extensions"]["pde"]
    return result, tmp_path / "experiments/E-source"


@pytest.mark.parametrize("runner", [verify_vector_pde, verify_coupled_pde])
def test_readers_use_actual_core_artifact_boundary_without_solver(runner, source_result):
    result, folder = source_result
    assert runner._assessed_studies(result, folder) == [{"source_only_fixture": True,
                                                        "marker": "not native numerical evidence"}]
    # The intentionally incomplete fixture stops at missing native progress,
    # rather than assuming scientific observations exist in Core extensions.
    with pytest.raises(FileNotFoundError, match="progress.json"):
        runner._fields("E-source", {"mesh": {"cell_counts": [8]}}, result, folder)


@pytest.mark.parametrize("change", ["metrics", "solver_status", "converged", "raw_result", "mesh_studies"])
def test_adapter_artifact_mismatch_refuses_without_numerical_execution(source_result, change):
    result, folder = source_result
    path = folder / "pde/result.json"
    detail = load_json(path)
    if change == "metrics": detail[change]["source_marker"]["valid"] = 1
    elif change == "solver_status": detail[change] = "NOT_RUN"
    elif change == "converged": detail[change] = 1
    elif change == "raw_result": detail[change] = "pde/other.json"
    else: detail[change] = None
    save_json(path, detail)
    with pytest.raises(AssertionError):
        verify_vector_pde._assessed_studies(result, folder)
