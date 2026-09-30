"""Material adapter/Core contracts with synthetic processes, no native proof."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from caelab import Lab
from caelab.adapters import mfront_material as adapter
from caelab.storage import canonical_hash, load_json, save_json
from plugins.material_point import reference as ref
from test_material_point_reference import observations, settings


def lab_at(path, instance=None):
    instance = instance or adapter.MFrontMaterialAdapter()
    lab = Lab(path, adapters={}, analysis_adapters={}, doe_adapters={}, optimization_adapters={}, pde_adapters={},
              model_analysis_adapters={instance.backend: instance})
    lab.create_study("S-material", "Material point", "Does the declared constitutive point match the independent law?",
                     "The bounded infinitesimal isotropic case is numerically consistent", "Synthetic contract test only")
    return lab


def run(lab, spec=None, identifier="E-material"):
    return lab.run_model_analysis(study_id="S-material", experiment_id=identifier,
        backend=adapter.MFrontMaterialAdapter.backend, settings=settings() if spec is None else spec)


def mock_native(monkeypatch, tmp_path, mutation=None):
    image = tmp_path / "fake-image.sif"
    image.write_bytes(b"TEST ONLY: not an actual native SIF")
    digest = adapter.sha256(image)
    monkeypatch.setattr(adapter, "_runtime_identity", lambda: (image, digest, "TEST_ONLY_singularity"))
    monkeypatch.setattr(adapter, "_process", lambda *args, **kwargs: "TEST ONLY process")

    def checked(output, input_sha):
        spec, raw = observations(output)
        if mutation:
            mutation(raw)
        save_json(output / "native_raw.json", raw)
        return raw | {"runtime": {"tfel": "TEST_ONLY", "mgis": "TEST_ONLY"},
                      "behaviour_description": {"behaviour": "TEST_ONLY"}}, {"library_sha256": "b" * 64}
    monkeypatch.setattr(adapter, "checked_native", checked)


def test_common_declared_run_is_cadless_immutable_and_unknown(tmp_path, monkeypatch):
    mock_native(monkeypatch, tmp_path)
    lab = lab_at(tmp_path / "store")
    spec = settings()
    original = deepcopy(spec)
    result = run(lab, spec)
    assert result["status"] == "COMPLETED_REVIEW_REQUIRED", result
    assert result["solver_status"] == "COMPLETED" and result["converged"] is True
    assert result["decision"] == "NOT_RELEASED" and result["cad_revision"] is None
    assert "parent_experiment_id" not in result
    folder = lab.store / "experiments/E-material"
    proposal = load_json(folder / "proposal.json")
    declaration = ref.model_declaration(spec)
    assert proposal["model"] == declaration["model"]
    assert proposal["loads"] == declaration["loads"] and proposal["initial_conditions"] == declaration["initial_conditions"]
    assert result["model_revision"] == canonical_hash({"settings": spec, "declaration": declaration})
    assert load_json(folder / "thread.json")["model_revision"] == result["model_revision"]
    assert lab.inspect_experiment("E-material") == result
    assert set(ref.PENDING) <= set(lab.research_summary("E-material")["unknown"])
    assert spec == original
    record_bytes = (folder / "result.json").read_bytes()
    second = run(lab, identifier="E-new")
    assert second["experiment_id"] == "E-new"
    assert (folder / "result.json").read_bytes() == record_bytes
    with pytest.raises(FileExistsError):
        run(lab)
    (folder / "simulation/native_raw.json").write_text("tampered")
    with pytest.raises(Exception, match="(?i)(hash|changed|tamper|integrity)"):
        lab.inspect_experiment("E-material")


def test_invalid_input_prevents_worker_and_compiler_in_common_core(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, "_runtime_identity", lambda: pytest.fail("Invalid inputs must reject before native preflight"))
    monkeypatch.setattr(adapter, "_process", lambda *args, **kwargs: pytest.fail("Invalid inputs must not launch any process"))
    lab = lab_at(tmp_path / "store")
    spec = settings()
    spec["material"]["poisson_ratio"] = .5
    result = run(lab, spec)
    assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN"
    assert result["metrics"] == {}
    assert not (lab.store / "experiments/E-material/simulation").exists()


def test_direct_adapter_invalid_input_preflight_no_native_process(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, "_runtime_identity", lambda: pytest.fail("No native preflight permitted"))
    spec = settings()
    spec["history"][1]["strain"][0] = .1
    result = adapter.MFrontMaterialAdapter().solve(tmp_path / "simulation", spec)
    assert result["solver_status"] == "NOT_RUN" and result["status"] == "REJECTED"


def test_native_numeric_rejection_retains_finite_invalid_fields(tmp_path, monkeypatch):
    mock_native(monkeypatch, tmp_path, lambda raw: raw["mgis"]["steps"][0]["stress_physical_mpa"].__setitem__(0, 100.))
    lab = lab_at(tmp_path / "store")
    result = run(lab)
    assert result["status"] == "REJECTED" and result["solver_status"] == "COMPLETED"
    assert result["metrics"]["max_physical_stress_error"]["value"] > 99.
    assert all(not metric["valid"] and metric["reason"] for metric in result["metrics"].values())
    assert lab.inspect_experiment("E-material") == result


@pytest.mark.parametrize("mode", ["missing", "corrupt", "crash"])
def test_absent_corrupt_or_crashed_native_outputs_preserve_failed_store(tmp_path, monkeypatch, mode):
    image = tmp_path / "fake.sif"
    image.write_bytes(b"TEST_ONLY")
    monkeypatch.setattr(adapter, "_runtime_identity", lambda: (image, adapter.sha256(image), "TEST_ONLY"))
    def process(command, output, label, **kwargs):
        (output / (label + ".stdout.log")).write_text("TEST ONLY partial native output")
        if label == "material_worker":
            if mode == "corrupt":
                (output / "native_raw.json").write_text('{"schema_version":"1","stress":NaN}')
            if mode == "crash":
                raise RuntimeError("TEST ONLY native process crash")
        return "TEST_ONLY"
    monkeypatch.setattr(adapter, "_process", process)
    lab = lab_at(tmp_path / "store")
    result = run(lab)
    assert result["status"] == "FAILED_EXECUTION" and result["solver_status"] == "FAILED_EXECUTION"
    assert result["metrics"] == {} and result["decision"] == "NOT_RELEASED"
    assert result["provenance"]["adapter_details"]["image_sha256"] == adapter.sha256(image)
    assert set(ref.PENDING) <= set(lab.research_summary("E-material")["unknown"])
    paths = {a["path"] for a in result["artifacts"]}
    assert "simulation/input.json" in paths and "simulation/material_worker.stdout.log" in paths
    assert lab.inspect_experiment("E-material") == result


def test_output_reuse_and_domain_source_drift_refused(tmp_path, monkeypatch):
    output = tmp_path / "simulation"
    output.mkdir()
    (output / "old.log").write_text("Old evidence")
    with pytest.raises(ValueError, match="old evidence"):
        adapter.MFrontMaterialAdapter().solve(output, settings())
    assert (output / "old.log").read_text() == "Old evidence"
    monkeypatch.setattr(adapter, "_DOMAIN_SHA", "0" * 64)
    result = adapter.MFrontMaterialAdapter().solve(tmp_path / "new", settings())
    assert result["solver_status"] == "FAILED_EXECUTION"
    assert "source changed" in result["checks"][0]["observed"]


def test_process_timeout_keeps_partial_logs(tmp_path, monkeypatch):
    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(["TEST_ONLY"], 1, output=b"partial", stderr=b"error")
    monkeypatch.setattr(adapter.subprocess, "run", timed_out)
    with pytest.raises(RuntimeError, match="partial evidence"):
        adapter._process(["TEST_ONLY"], tmp_path, "native", timeout=1)
    assert (tmp_path / "native.stdout.log").read_text() == "partial"
    assert "TimeoutExpired" in (tmp_path / "native.stderr.log").read_text()


def test_missing_and_hash_drifted_sif_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("CAELAB_MFRONT_IMAGE", raising=False)
    monkeypatch.delenv("CAELAB_MFRONT_IMAGE_SHA256", raising=False)
    monkeypatch.delenv("CAELAB_CODEASTER_IMAGE", raising=False)
    monkeypatch.delenv("CAELAB_CODEASTER_IMAGE_SHA256", raising=False)
    with pytest.raises(RuntimeError, match="Configure"):
        adapter._runtime_identity()
    image = tmp_path / "image.sif"
    image.write_bytes(b"TEST_ONLY")
    monkeypatch.setenv("CAELAB_MFRONT_IMAGE", str(image))
    monkeypatch.setenv("CAELAB_MFRONT_IMAGE_SHA256", "0" * 64)
    with pytest.raises(RuntimeError, match="SIF hash drifted"):
        adapter._runtime_identity()


def native_identity_fixture(output, monkeypatch):
    build = output / "build/src"
    build.mkdir(parents=True)
    (output / "input.json").write_text('{"TEST_ONLY":true}')
    (output / "build/Elasticity.mfront").write_bytes(b"TEST ONLY source, never compiled")
    (build / "libBehaviour.so").write_bytes(b"TEST ONLY library, never loaded")
    (build / "Makefile.mfront").write_text("CXXFLAGS = TEST_ONLY\n")
    source_sha = adapter.sha256(output / "build/Elasticity.mfront")
    monkeypatch.setattr(adapter, "SOURCE_SHA256", source_sha)
    runtime = {"mgis": "3.0", "tfel": "tfel-config 5.0.0 (TEST_ONLY)", "python": "TEST_ONLY", "numpy": "TEST_ONLY",
               "compiler": "TEST_ONLY", "mfront": "TEST_ONLY", "make": "TEST_ONLY",
               "mgis_binding_sha256": "a" * 64, "mtest_binding_sha256": "a" * 64}
    for name, prefix, version in (("mgis", adapter.MGIS_PREFIX, "3.0"), ("tfel", adapter.TFEL_PREFIX, "5.0.0")):
        (output / (name + "_installed_spec.json")).write_text('{"TEST_ONLY":true}')
        runtime[name + "_package"] = {"name": name, "version": version, "package_prefix": prefix,
            "binding_path": prefix + "/TEST_ONLY.so", "spec_sha256": adapter.sha256(output / (name + "_installed_spec.json")),
            "binding_sha256": "a" * 64}
    raw = {"schema_version": "1", "input_sha256": adapter.sha256(output / "input.json"),
           "source_sha256": source_sha, "worker_sha256": adapter._WORKER_SHA,
           "library_sha256": adapter.sha256(build / "libBehaviour.so"), "runtime": runtime,
           "behaviour_description": {"behaviour": "Elasticity", "hypothesis": "TRIDIMENSIONAL",
               "material_properties": ["YoungModulus", "PoissonRatio"], "external_state_variables": ["Temperature"]}}
    save_json(output / "native_raw.json", raw)
    save_json(output / "runtime.json", runtime)
    save_json(output / "build_identity.json", {"library_sha256": raw["library_sha256"], "source_sha256": source_sha,
        "generation_arguments": adapter.BUILD_ARGUMENTS, "makefile_sha256": adapter.sha256(build / "Makefile.mfront"),
        "compiler_flags_makefile": ["TEST_ONLY"], "actual_compiler_commands": ["TEST_ONLY"],
        "compiler_flags_policy": adapter.COMPILER_POLICY, "compiler_flags_override": ["-O2", "-fno-fast-math", "-std=c++20"],
        "dependency_sha256": {"TEST_ONLY": "a" * 64}})
    return raw


@pytest.mark.parametrize("drift", ["input", "source", "library", "makefile", "worker", "runtime", "hypothesis"])
def test_native_source_build_library_and_runtime_drift_refused(tmp_path, monkeypatch, drift):
    raw = native_identity_fixture(tmp_path, monkeypatch)
    assert adapter.checked_native(tmp_path, raw["input_sha256"])[0] == raw
    if drift in ("input", "source", "library", "makefile"):
        path = {"input": "input.json", "source": "build/Elasticity.mfront", "library": "build/src/libBehaviour.so",
                "makefile": "build/src/Makefile.mfront"}[drift]
        (tmp_path / path).write_bytes(b"TEST ONLY tamper")
    else:
        if drift == "worker":
            raw["worker_sha256"] = "0" * 64
        elif drift == "runtime":
            raw["runtime"]["mgis"] = "unexpected-version"
        else:
            raw["behaviour_description"]["hypothesis"] = "PlaneStrain"
        save_json(tmp_path / "native_raw.json", raw)
    with pytest.raises(RuntimeError, match="Malformed native"):
        adapter.checked_native(tmp_path, raw["input_sha256"])
