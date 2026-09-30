"""Runtime-profile admission contracts; TEST ONLY process/binary substitutes.

These tests establish no native numerical or alternate-SIF qualification.
"""

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from caelab import Lab
from caelab.adapters import mfront_inverse as adapter
from caelab.storage import load_json
from plugins.material_point import inverse_reference as domain


@pytest.fixture(autouse=True)
def clean_deployment(monkeypatch):
    for name in adapter.CONFIG_KEYS:
        monkeypatch.delenv(name, raising=False)
    for name in list(adapter.os.environ):
        if name.startswith(adapter.NATIVE_OVERRIDE_PREFIXES):
            monkeypatch.delenv(name, raising=False)


def probe_data():
    return {"schema_version": "1", "probe_sha256": adapter.SOURCE_HASHES[
            adapter.RUNTIME_PROBE.relative_to(adapter.ROOT).as_posix()],
        "python": {"version": "3.11.14", "executable": "/usr/bin/python3.11"},
        "bindings": {name: {"loaded_path": prefix + "/lib/TEST_ONLY.so",
            "resolved_path": prefix + "/lib/TEST_ONLY.so", "sha256": adapter.SEALED_NATIVE_BINARIES[name]["sha256"]}
            for name, prefix in (("mgis_binding", adapter.base.MGIS_PREFIX),
                                 ("mtest_binding", adapter.base.TFEL_PREFIX))},
        "executables": {name: {"path": "/usr/bin/TEST_ONLY_" + name,
            "sha256": adapter.SEALED_NATIVE_BINARIES[name]["sha256"]}
            for name in ("compiler", "mfront", "mtest", "tfel_config")}}


def definition_data(value=None):
    return {"data": {"attributes": {"deffile": adapter.OCI_DEFINITION if value is None else value}},
            "type": "container"}


def fake_admission(monkeypatch, tmp_path, *, profile=adapter.SEALED_OCI, mutate=None):
    if profile is not None:
        monkeypatch.setenv(adapter.PROFILE_ENV, profile)
    image, wrapper, prlimit = (tmp_path / name for name in ("TEST_ONLY.sif", "TEST_ONLY_runtime", "TEST_ONLY_prlimit"))
    for path in (image, wrapper, prlimit):
        path.write_bytes(("TEST ONLY " + path.name).encode())
    monkeypatch.setattr(adapter.base, "_runtime_identity", lambda: (image, adapter.base.sha256(image), str(wrapper)))
    monkeypatch.setattr(adapter.shutil, "which", lambda name: str(prlimit) if name == "prlimit" else None)
    calls = []
    def command(argv):
        calls.append(list(argv))
        if "inspect" in argv:
            data = definition_data()
        else:
            probe = Path(next(value[:-len(":/probe:ro")] for value in argv if value.endswith(":/probe:ro")))
            assert (probe / adapter.RUNTIME_PROBE.name).read_bytes() == adapter.SOURCE_BYTES[str(adapter.RUNTIME_PROBE)]
            data = probe_data()
        if mutate:
            mutate(data, len(calls))
        return {"returncode": 0, "stdout": json.dumps(data, sort_keys=True), "stderr": "", "error": None}
    monkeypatch.setattr(adapter, "_bounded_command", command)
    return image, wrapper, prlimit, calls


def test_constructor_reads_configuration_only_and_default_stays_exact(monkeypatch):
    monkeypatch.setattr(adapter.base, "_runtime_identity", lambda: pytest.fail("Constructor cannot read runtime"))
    monkeypatch.setattr(adapter, "_bounded_command", lambda *_: pytest.fail("Constructor cannot start processes"))
    instance = adapter.MFrontInverseAdapter()
    assert instance.runtime_profile_declaration()["profile"] == adapter.LOCAL_EXACT
    assert instance.runtime_profile_declaration()["local_exact_sif_sha256"] == (
        "f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64")
    assert instance.describe_model(domain.canonical_settings())["model"]["inverse_problem"][
        "observation_dataset"]["source"]["kind"] == "SYNTHETIC_REFERENCE"
    assert instance.runtime_admission_evidence() == {}


@pytest.mark.parametrize("value", ["", "sealed_oci", "AUTO", "LOCAL_EXACT", " SEALED_OCI"])
def test_invalid_profile_rejected_without_native_calls(monkeypatch, value):
    monkeypatch.setenv(adapter.PROFILE_ENV, value)
    monkeypatch.setattr(adapter, "_bounded_command", lambda *_: pytest.fail("Invalid profile starts no process"))
    with pytest.raises(ValueError, match="deployment configuration"):
        adapter.MFrontInverseAdapter()


def test_default_rejects_other_sif_without_attempting_oci_fallback(monkeypatch, tmp_path):
    _, _, _, calls = fake_admission(monkeypatch, tmp_path, profile=None)
    with pytest.raises(RuntimeError, match="exact already-verified SIF"):
        adapter.MFrontInverseAdapter().input_runtime_identity()
    assert calls == []


def test_opt_in_oci_admission_remeasures_and_freezes_actual_identity(monkeypatch, tmp_path):
    image, wrapper, prlimit, calls = fake_admission(monkeypatch, tmp_path)
    monkeypatch.setenv("TEST_ONLY_SECRET", "must not enter runtime evidence")
    instance = adapter.MFrontInverseAdapter()
    first = instance.input_runtime_identity()
    second = instance.input_runtime_identity()
    assert first == second and len(calls) == 4
    assert first["profile"] == adapter.SEALED_OCI and first["kind"] == "sealed_mfront_oci"
    assert first["image_sha256"] == adapter.base.sha256(image) != adapter.PINNED_SIF_SHA256
    assert first["singularity"]["sha256"] == adapter.base.sha256(wrapper)
    assert first["prlimit"]["sha256"] == adapter.base.sha256(prlimit)
    assert first["oci_definition"]["oci_manifest_sha256"] == adapter.base.OCI_MANIFEST_SHA256
    assert first["preflight_probe"]["measurements"] == probe_data()
    assert "must not enter" not in json.dumps(first)
    for command in calls:
        assert command[:4] == [str(prlimit), "--as=4294967296", "--cpu=30", "--fsize=65536"]
    assert calls[0][4:] == [str(wrapper), "inspect", "--json", "--deffile", str(image)]
    for command in (calls[1], calls[3]):
        assert "--cleanenv" in command and "--containall" in command and "--no-home" in command
        assert any(value.endswith(":/probe:ro") for value in command)
        assert any(value.endswith(":/tmp:rw") for value in command)
        assert command[-5:] == ["/bin/bash", "--noprofile", "--norc", "-c", adapter.PROBE_BOOTSTRAP]
    assert calls[1] != calls[3]  # Fresh isolated mounts, not an admission cache.
    first["source_files"].clear()
    assert instance.input_runtime_identity() == second  # Returned mappings cannot mutate the seal.


@pytest.mark.parametrize("name", adapter.CONFIG_KEYS)
def test_any_config_drift_blocks_before_commands(monkeypatch, tmp_path, name):
    _, _, _, calls = fake_admission(monkeypatch, tmp_path)
    instance = adapter.MFrontInverseAdapter()
    instance.input_runtime_identity()
    count = len(calls)
    monkeypatch.setenv(name, "changed deployment")
    with pytest.raises(RuntimeError, match="environment changed"):
        instance.input_runtime_identity()
    assert len(calls) == count


@pytest.mark.parametrize("name", ["SINGULARITYENV_LD_PRELOAD", "APPTAINERENV_PYTHONPATH", "SINGULARITY_BINDPATH",
    "SINGULARITY_MOUNT", "APPTAINER_MOUNT", "SINGULARITY_OVERLAY", "APPTAINER_OVERLAY",
    "SINGULARITY_OVERLAYIMAGE", "APPTAINER_OVERLAYIMAGE", "SINGULARITY_CONTAINLIBS",
    "APPTAINER_WRITABLE_TMPFS", "SINGULARITY_HOME", "SINGULARITY_FUTURE_UNDECLARED_CONTROL"])
def test_unapproved_native_environment_override_blocks_without_retaining_secret(monkeypatch, tmp_path, name):
    _, _, _, calls = fake_admission(monkeypatch, tmp_path)
    instance = adapter.MFrontInverseAdapter()
    monkeypatch.setenv(name, "TEST_ONLY_secret")
    with pytest.raises(RuntimeError, match="overrides are not admitted"):
        instance.input_runtime_identity()
    assert calls == [] and "TEST_ONLY_secret" not in json.dumps(instance.runtime_admission_evidence())


@pytest.mark.parametrize("name", ["SINGULARITY_MOUNT", "APPTAINER_OVERLAY"])
def test_container_control_drift_after_admission_blocks_before_native_solve(monkeypatch, tmp_path, name):
    _, _, _, calls = fake_admission(monkeypatch, tmp_path)
    instance = adapter.MFrontInverseAdapter()
    instance.input_runtime_identity()
    monkeypatch.setenv(name, "TEST_ONLY_secret_modified_native_view")
    monkeypatch.setattr(instance._base, "solve", lambda *_: pytest.fail("Drift must block before inherited native process"))
    result = instance.solve(tmp_path / "simulation", domain.canonical_settings())
    assert len(calls) == 2
    assert result["solver_status"] == "FAILED_EXECUTION" and result["metrics"] == {}
    assert "TEST_ONLY_secret" not in json.dumps(result)


@pytest.mark.parametrize("which", [0, 1, 2])
def test_sif_wrapper_or_limit_tool_drift_blocks_before_new_command(monkeypatch, tmp_path, which):
    *paths, calls = fake_admission(monkeypatch, tmp_path)
    instance = adapter.MFrontInverseAdapter()
    instance.input_runtime_identity()
    paths[which].write_bytes(b"Changed TEST ONLY runtime")
    with pytest.raises(RuntimeError, match="identity changed"):
        instance.input_runtime_identity()
    assert len(calls) == 2


def test_sif_change_during_probe_rejected(monkeypatch, tmp_path):
    image, _, _, _ = fake_admission(monkeypatch, tmp_path)
    original = adapter._bounded_command
    def changed(argv):
        result = original(argv)
        if "exec" in argv:
            image.write_bytes(b"Changed during TEST ONLY probe")
        return result
    monkeypatch.setattr(adapter, "_bounded_command", changed)
    with pytest.raises(RuntimeError, match="during native runtime admission"):
        adapter.MFrontInverseAdapter().input_runtime_identity()


def test_probe_source_drift_blocks_declaration_and_admission(monkeypatch, tmp_path):
    _, _, _, calls = fake_admission(monkeypatch, tmp_path)
    instance = adapter.MFrontInverseAdapter()
    original = adapter.base.sha256
    monkeypatch.setattr(adapter.base, "sha256", lambda path: "0" * 64 if Path(path) == adapter.RUNTIME_PROBE else original(path))
    with pytest.raises(RuntimeError, match="source changed"):
        instance.describe_inputs(domain.canonical_settings())
    with pytest.raises(RuntimeError, match="source changed"):
        instance.input_runtime_identity()
    assert calls == []


@pytest.mark.parametrize("value", ["bootstrap: docker\nfrom: simvia/code_aster:17.4.0",
    "bootstrap: docker\nfrom: simvia/code_aster@sha256:" + "0" * 64,
    adapter.OCI_DEFINITION + "\n%post\ntrue", "", None, 1, {}])
def test_missing_wrong_or_augmented_oci_definition_has_no_fallback(value):
    data = definition_data()
    data["data"]["attributes"]["deffile"] = value
    with pytest.raises(ValueError):
        adapter._definition(json.dumps(data))


def test_strict_metadata_structure_duplicate_and_nonfinite_rejection():
    for text in ('{"data":{},"type":"container","type":"container"}',
                 '{"data":{},"type":NaN}', '{"data":{},"type":"container"}',
                 json.dumps({**definition_data(), "labels": {}})):
        with pytest.raises(ValueError):adapter._definition(text)


@pytest.mark.parametrize("name", adapter.SEALED_NATIVE_BINARIES)
def test_every_native_hash_is_required_before_discovery_and_native(monkeypatch, tmp_path, name):
    def mutate(data, _):
        if "bindings" in data:
            group = "bindings" if name.endswith("binding") else "executables"
            data[group][name]["sha256"] = "0" * 64
    fake_admission(monkeypatch, tmp_path, mutate=mutate)
    instance = adapter.MFrontInverseAdapter()
    monkeypatch.setattr(instance._base, "solve", lambda *_: pytest.fail("No native solve after failed admission"))
    lab = Lab(tmp_path / "store", model_analysis_adapters={instance.backend: instance})
    with pytest.raises(ValueError, match="sealed inventory"):
        lab.discover_model_parameters(instance.backend, domain.canonical_settings())
    result = instance.solve(tmp_path / "simulation", domain.canonical_settings())
    assert result["status"] == "REJECTED" and result["solver_status"] == "FAILED_EXECUTION"
    assert result["metrics"] == {} and result["pending_validations"] == domain.PENDING
    assert not (tmp_path / "simulation/native_raw.json").exists()
    assert load_json(tmp_path / "simulation/runtime_admission_failure.json")["commands"]["probe"]["returncode"] == 0


@pytest.mark.parametrize("mode", ["source", "prefix", "traversal", "relative", "missing", "extra", "schema"])
def test_malformed_probe_or_source_inventory_rejected(mode):
    data = probe_data()
    if mode == "source":data["probe_sha256"] = "0" * 64
    elif mode == "prefix":data["bindings"]["mgis_binding"]["resolved_path"] = "/tmp/lib.so"
    elif mode == "traversal":data["bindings"]["mgis_binding"]["resolved_path"] = adapter.base.MGIS_PREFIX + "/../lib.so"
    elif mode == "relative":data["executables"]["compiler"]["path"] = "g++"
    elif mode == "missing":data["executables"].pop("mtest")
    elif mode == "extra":data["bindings"]["unsealed"] = {}
    elif mode == "schema":data["schema_version"] = True
    with pytest.raises(ValueError):adapter._checked_probe(json.dumps(data))


@pytest.mark.parametrize("name", adapter.SEALED_NATIVE_BINARIES)
def test_existing_post_native_seal_is_not_replaced_by_preflight(name):
    raw = {"runtime": {"mgis_binding_sha256": adapter.SEALED_NATIVE_BINARIES["mgis_binding"]["sha256"],
                      "mtest_binding_sha256": adapter.SEALED_NATIVE_BINARIES["mtest_binding"]["sha256"],
                      "executables": {key: deepcopy(adapter.SEALED_NATIVE_BINARIES[key]) for key in
                                      ("compiler", "mfront", "mtest", "tfel_config")}}}
    adapter._sealed_runtime(raw)
    if name.endswith("binding"):
        raw["runtime"][name + "_sha256"] = "0" * 64
    else:
        raw["runtime"]["executables"][name]["sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="pinned SIF inventory"):
        adapter._sealed_runtime(raw)


def test_profile_cannot_be_chosen_in_model_settings(monkeypatch, tmp_path):
    _, _, _, calls = fake_admission(monkeypatch, tmp_path)
    instance = adapter.MFrontInverseAdapter()
    settings = domain.canonical_settings()
    settings["runtime_profile"] = adapter.SEALED_OCI
    result = instance.solve(tmp_path / "simulation", settings)
    assert result["solver_status"] == "NOT_RUN" and result["status"] == "REJECTED"
    assert calls == []


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_process_output_is_bounded_and_rejected(stream):
    result = adapter._bounded_command([sys.executable, "-c",
        "import sys; sys." + stream + ".write('x' * 1000000); sys." + stream + ".flush()"])
    assert "byte bound" in result["error"]
    assert len(result[stream].encode()) == adapter.ADMISSION_LIMITS[stream + "_bytes"]


def test_process_timeout_invalid_encoding_missing_and_nonzero_rejected(monkeypatch):
    monkeypatch.setitem(adapter.ADMISSION_LIMITS, "timeout_seconds", .1)
    result = adapter._bounded_command([sys.executable, "-c", "import time; time.sleep(10)"])
    assert "timed out" in result["error"]
    result = adapter._bounded_command([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff')"])
    assert "invalid UTF-8" in result["error"]
    result = adapter._bounded_command(["/TEST_ONLY/no-such-command"])
    assert "could not start" in result["error"]
    result = adapter._bounded_command([sys.executable, "-c", "raise SystemExit(7)"])
    assert result["returncode"] == 7 and "exited 7" in result["error"]


def test_admission_failure_preserves_predeclared_profile_and_bounded_logs(monkeypatch, tmp_path):
    from scripts import verify_material_inverse as verifier
    fake_admission(monkeypatch, tmp_path, mutate=lambda data, _: data.update(type="wrong") if "type" in data else None)
    monkeypatch.setattr(verifier, "source_identity", lambda _: {"core_commit": "TEST_ONLY", "core_dirty": False})
    store = tmp_path / "failed-preflight"
    with pytest.raises(ValueError, match="structure"):
        verifier.freeze(store, require_clean=True)
    declaration = load_json(store / "runtime_profile_predeclaration.json")
    assert declaration["runtime_profile"]["profile"] == adapter.SEALED_OCI
    assert declaration["settings"] == domain.canonical_settings()
    assert load_json(store / "runtime_admission_failure.json")["status"] == "FAIL"
    assert load_json(store / "runtime_admission.json")["commands"]["definition"]["stdout"]
    assert not (store / "experiments").exists()
