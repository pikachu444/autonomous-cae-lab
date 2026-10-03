"""TEST ONLY contracts; all native execution is intercepted by bounded doubles."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import shutil

import numpy as np
import pytest

from caelab import Lab
from caelab.adapters import mfront_viscoelastic as adapter_module
from caelab.adapters import mfront_viscoelastic_worker as worker
from caelab.storage import canonical_hash, load_json, save_json
from caelab.outcomes import validate_outcome
from plugins.material_point import viscoelastic_reference as ref
from test_viscoelastic_reference import FakeBinding, FakeTransport, make_raw


def clean_environment(monkeypatch):
    for key in list(adapter_module.os.environ):
        if key.startswith(adapter_module.runtime_helpers.NATIVE_OVERRIDE_PREFIXES):
            monkeypatch.delenv(key)
    for key in adapter_module.CONFIG_KEYS:
        monkeypatch.delenv(key, raising=False)


def no_native(*args, **kwargs):
    pytest.fail("TEST ONLY preflight/description reached a native process or runtime hash")


def properties(settings):
    return dict(zip(worker.PROPERTY_NAMES, settings["material"].values()))


def test_nonzero_full_state_clone_has_no_aliases(tmp_path):
    settings = ref.canonical_settings()
    behaviour = SimpleNamespace(computesStoredEnergy=True, computesDissipatedEnergy=True)
    initial = worker.clone_manager(FakeBinding, behaviour, np, properties(settings), 293.15)
    for state in (initial.manager.s0, initial.manager.s1):
        state.gradients[:] = np.arange(6) * .001
        state.thermodynamic_forces[:] = np.arange(6) + .2
        state.internal_state_variables[:] = np.arange(6) - 3.
        state.stored_energies[:] = .0017
        state.dissipated_energies[:] = .0023
    initial.manager.K[:] = np.arange(36).reshape(1, 6, 6)
    baseline = worker.snapshot_manager(initial, .2)
    left = worker.clone_manager(FakeBinding, behaviour, np, properties(settings), 293.15, baseline)
    right = worker.clone_manager(FakeBinding, behaviour, np, properties(settings), 293.15, baseline)
    assert worker.snapshot_manager(left, .2) == baseline == worker.snapshot_manager(right, .2)
    for name in worker.ARRAYS:
        assert not np.shares_memory(getattr(left.manager.s0, name), getattr(right.manager.s0, name))
        assert not np.shares_memory(getattr(left.manager.s1, name), getattr(initial.manager.s1, name))
    assert not np.shares_memory(left.manager.K, right.manager.K)
    for state in ("s0", "s1"):
        for name in worker.PROPERTY_NAMES:
            assert not np.shares_memory(left.property_buffers[state][name], right.property_buffers[state][name])
        assert not np.shares_memory(left.external_buffers[state]["Temperature"], right.external_buffers[state]["Temperature"])
    left.manager.s1.internal_state_variables[0, 4] = 999.
    left.manager.s1.stored_energies[0] = 17.
    left.property_buffers["s1"]["RelaxationTime"][0] = 2.
    left.external_buffers["s0"]["Temperature"][0] = 800.
    left.manager.K[0, 0, 3] = 88.
    assert worker.snapshot_manager(right, .2) == baseline
    assert worker.snapshot_manager(initial, .2) == baseline


@pytest.mark.parametrize("return_code", [0, -1])
def test_unreliable_nominal_never_advances_or_runs_fd(tmp_path, return_code):
    settings = ref.canonical_settings()
    behaviour = SimpleNamespace(computesStoredEnergy=True, computesDissipatedEnergy=True)
    transport = FakeTransport(return_code)
    raw = worker.integrate_history(FakeBinding, behaviour, settings, "a" * 64, tmp_path, np, transport)
    assert transport.calls == 1
    assert raw["native_rejection"]["integration_return"] == return_code
    assert len(raw["steps"]) == 1 and raw["steps"][0]["finite_differences"] == []
    assert raw["steps"][0]["initial_manager"]["s0"]["internal_state_variables"] == [0.] * 6
    assert (tmp_path / "mgis.partial.json").exists()


def test_unreliable_signed_fd_does_not_advance_nominal(tmp_path):
    settings = ref.canonical_settings()
    behaviour = SimpleNamespace(computesStoredEnergy=True, computesDissipatedEnergy=True)
    class FailProbe(FakeTransport):
        def _integrate(self, binding, manager, dt):
            self.return_code = 0 if self.calls == 2 else 1
            return super()._integrate(binding, manager, dt)
    transport = FailProbe()
    raw = worker.integrate_history(FakeBinding, behaviour, settings, "a" * 64, tmp_path, np, transport)
    assert transport.calls == 3
    assert raw["native_rejection"]["phase"] == "finite_difference"
    assert len(raw["steps"]) == 1


def test_energy_getters_are_never_touched_without_native_flags(monkeypatch):
    monkeypatch.setattr(FakeBinding, "MaterialDataManager", no_native)
    with pytest.raises(ValueError):
        worker.clone_manager(FakeBinding, SimpleNamespace(computesStoredEnergy=False, computesDissipatedEnergy=True),
                             np, properties(ref.canonical_settings()), 293.15)


def table_text(states):
    lines = ["# first column: time"]
    for i in range(6):
        lines.append(f"# {i + 2} column: strain component {i}")
    for i in range(6):
        lines.append(f"# {i + 8} column: stress component {i}")
    for i in range(6):
        lines.append(f"# {i + 14} column: internal state variable BranchStress component {i}")
    lines += ["# 20 column: stored energy", "# 21 column: disspated energy"]
    for state in states:
        values = [state["time_s"], *state["global_u0"][:6], *state["committed_s0_kelvin_mpa"],
                  *state["committed_iv0"], state["stored_energy_mpa"], state["dissipated_energy_mpa"]]
        lines.append(" ".join(format(x, ".17g") for x in values))
    return "\n".join(lines) + "\n"


@pytest.fixture(scope="module")
def raw_template(tmp_path_factory):
    return make_raw(tmp_path_factory.mktemp("visco-test-only"))


def test_native_table_projection_is_actual_and_input_buffers_match(tmp_path, raw_template):
    states = deepcopy(raw_template["mtest"]["states"])
    path = tmp_path / "mtest.res"
    path.write_text(table_text(states))
    # A wrong in-memory energy is replaced only by its actual retained native table.
    states[3]["stored_energy_mpa"] = 123.
    metadata = worker.parse_mtest_table(path, states)
    assert metadata["stored_energy_column"] == 20 and metadata["dissipated_energy_column"] == 21
    assert states[3]["stored_energy_mpa"] == raw_template["mtest"]["states"][3]["stored_energy_mpa"]


@pytest.mark.parametrize("corrupt", [
    lambda text: text.replace("# 21 column: disspated energy", "# 21 column: energy"),
    lambda text: text.replace("# 20 column: stored energy", "# 20 column: stored energy\n# 20 column: stored energy"),
    lambda text: text.rsplit("\n", 2)[0] + "\n",
    lambda text: text.replace("# 14 column: internal state variable BranchStress component 0", "# 14 column: arbitrary field"),
    lambda text: text + "0 " * 20 + "nan\n",
])
def test_native_energy_table_absence_truncation_nonfinite_columns_reject(tmp_path, raw_template, corrupt):
    path = tmp_path / "mtest.res"
    path.write_text(corrupt(table_text(raw_template["mtest"]["states"])))
    with pytest.raises(ValueError):
        worker.parse_mtest_table(path, deepcopy(raw_template["mtest"]["states"]))


def test_table_state_buffer_mismatch_reject(tmp_path, raw_template):
    path = tmp_path / "mtest.res"
    path.write_text(table_text(raw_template["mtest"]["states"]))
    states = deepcopy(raw_template["mtest"]["states"])
    states[4]["internal_state_variables"][3] += .1
    with pytest.raises(ValueError):
        worker.parse_mtest_table(path, states)


@pytest.mark.parametrize("key", [
    "SINGULARITY_MOUNT", "SINGULARITY_OVERLAY", "SINGULARITYENV_LD_PRELOAD",
    "APPTAINER_BINDPATH", "APPTAINER_MOUNT", "APPTAINER_OVERLAY", "APPTAINERENV_FUTURE_CONTROL"])
def test_hidden_container_controls_reject_without_values(monkeypatch, key):
    clean_environment(monkeypatch)
    monkeypatch.setenv(key, "TEST_ONLY_SECRET")
    with pytest.raises(RuntimeError) as exc:
        adapter_module.MFrontViscoelasticAdapter()
    assert "TEST_ONLY_SECRET" not in str(exc.value)


def test_constructor_and_description_have_no_native_calls(monkeypatch):
    clean_environment(monkeypatch)
    monkeypatch.setattr(adapter_module.transport, "_runtime_identity", no_native)
    monkeypatch.setattr(adapter_module.execution.subprocess, "Popen", no_native)
    adapter = adapter_module.MFrontViscoelasticAdapter()
    declaration = adapter.describe_model(ref.canonical_settings())
    assert declaration["model"]["geometry"] is None
    assert declaration["model"]["materials"][0]["source_kind"] == "SYNTHETIC_REFERENCE"


@pytest.mark.parametrize("mutate", [
    lambda s: s["material"].update(relaxation_time_s=0.),
    lambda s: s["material"].update(branch_bulk_modulus_mpa=float("inf")),
    lambda s: s["limits"].update(tangent_relative=1e-7),
    lambda s: s.update(source="/tmp/model.mfront"),
    lambda s: s.update(library="/tmp/library.so"),
    lambda s: s.update(runtime_profile="SEALED_OCI"),
])
def test_invalid_inputs_block_before_runtime_compiler_or_worker(tmp_path, monkeypatch, mutate):
    clean_environment(monkeypatch)
    monkeypatch.setattr(adapter_module.transport, "_runtime_identity", no_native)
    monkeypatch.setattr(adapter_module, "_process", no_native)
    adapter = adapter_module.MFrontViscoelasticAdapter()
    settings = ref.canonical_settings()
    mutate(settings)
    outcome = adapter.solve(tmp_path / "invalid", settings)
    validate_outcome(outcome)
    assert outcome["status"] == "REJECTED" and outcome["solver_status"] == "NOT_RUN"
    assert outcome["pending_validations"] == ref.PENDING
    assert not (tmp_path / "invalid/input.json").exists()


def fake_runtime(monkeypatch, tmp_path):
    clean_environment(monkeypatch)
    image, singularity, limit = (tmp_path / name for name in ("image.sif", "singularity", "prlimit"))
    for path in (image, singularity, limit):
        path.write_text("TEST ONLY runtime placeholder")
    original_hash = adapter_module.transport.sha256
    def hashing(path):
        if Path(path) == singularity:
            return adapter_module.PINNED_SINGULARITY_SHA256
        return original_hash(path)
    monkeypatch.setattr(adapter_module.transport, "sha256", hashing)
    monkeypatch.setattr(adapter_module.transport, "_runtime_identity",
        lambda: (image, adapter_module.PINNED_SIF_SHA256, str(singularity)))
    monkeypatch.setattr(adapter_module.shutil, "which", lambda name: str(limit) if name == "prlimit" else None)
    return image, singularity, limit


def write_testonly_native(output, settings, raw_template, monkeypatch):
    output = Path(output)
    raw = deepcopy(raw_template)
    build = output / "build/src"
    build.mkdir(parents=True)
    shutil.copyfile(adapter_module.LAW, output / "build" / worker.SOURCE_NAME)
    (build / "libBehaviour.so").write_bytes(b"TEST ONLY generated binary placeholder")
    (build / "Makefile.mfront").write_text("CXXFLAGS=-O2 -fno-fast-math -std=c++20\n")
    library_sha = adapter_module.transport.sha256(build / "libBehaviour.so")
    raw["library_sha256"] = raw["mgis"]["library_sha256"] = raw["mtest"]["library_sha256"] = library_sha
    sealed = adapter_module.SEALED_NATIVE_BINARIES
    runtime = {"python": "3.11.TEST_ONLY", "numpy": np.__version__, "mgis": "3.0", "tfel": "tfel-config 5.0.0",
        "compiler": "TEST ONLY GCC", "mfront": "TEST ONLY MFront", "make": "TEST ONLY Make",
        "tfel_recommended_oflags0": "-O2 -fno-fast-math", "tfel_cpp_compiler_flags": "-std=c++20",
        "tfel_include_path": worker.TFEL_PREFIX + "/include",
        "process_policy": load_json(output / "frozen_execution_policy.json")["process_policy"],
        "resource_limits": load_json(output / "frozen_execution_policy.json")["resource_limits"],
        "mgis_binding_sha256": sealed["mgis_binding"]["sha256"],
        "mtest_binding_sha256": sealed["mtest_binding"]["sha256"],
        "extra_native_bindings": {"tfel_math": deepcopy(worker.SEALED_MTEST_MATH_BINDING)},
        "executables": {key: {"path": "/TEST_ONLY/" + key, **sealed[key]} for key in ("compiler", "mfront", "mtest", "tfel_config")}}
    for name, prefix, version, key in (("mgis", worker.MGIS_PREFIX, "3.0", "mgis_binding"),
                                     ("tfel", worker.TFEL_PREFIX, "5.0.0", "mtest_binding")):
        spec = output / (name + "_installed_spec.json")
        save_json(spec, {"TEST_ONLY": True, "version": version})
        runtime[key + "_path"] = prefix + "/TEST_ONLY_binding.so"
        runtime[name + "_package"] = {"name": name, "version": version, "package_prefix": prefix,
            "binding_path": runtime[key + "_path"], "binding_sha256": runtime[key + "_sha256"],
            "spec_sha256": adapter_module.transport.sha256(spec)}
    upstream = output / "upstream_GeneralizedMaxwell.mfront"
    upstream.write_text("TEST ONLY attributed reference source placeholder")
    monkeypatch.setattr(worker, "REFERENCE_SOURCE_SHA256", adapter_module.transport.sha256(upstream))
    licenses = output / "licenses"
    licenses.mkdir()
    records = []
    for name in ("LICENCE-GNU-GPL", "LICENCE-CECILL-A-EN", "LICENCE-CECILL-A-FR"):
        (licenses / name).write_text("TEST ONLY license placeholder")
        records.append({"name": name, "artifact": "licenses/" + name, "sha256": adapter_module.transport.sha256(licenses / name)})
    save_json(output / "source_attribution.json", {"source_sha256": worker.SOURCE_SHA256,
        "reference_sha256": worker.REFERENCE_SOURCE_SHA256, "reference_commit": worker.TFEL_COMMIT,
        "installed_tfel_license_files": records})
    flags = worker._transport().portable_compiler_flags(runtime["tfel_recommended_oflags0"],
        runtime["tfel_cpp_compiler_flags"], runtime["tfel_include_path"])
    compiler = runtime["executables"]["compiler"]["path"]
    commands = []
    import shlex
    for source in (worker.BEHAVIOUR + ".cxx", worker.BEHAVIOUR + "-generic.cxx"):
        commands.append(shlex.join([compiler, "-M", *flags, source]) + " > " + source[:-4] + ".d.$$;")
        commands.append(shlex.join([compiler, *flags, source, "-o", source[:-4] + ".o", "-c"]))
    commands.append(shlex.join([compiler, "-shared", worker.BEHAVIOUR + "-generic.o", worker.BEHAVIOUR + ".o",
        "-o", "libBehaviour.so", "-L" + worker.TFEL_PREFIX + "/lib",
        *["-l" + name for name in ("MFrontProfiling", "TFELMaterial", "TFELMath", "TFELUtilities", "TFELException", "TFELNUMODIS")]]))
    compile_log = output / "build/compile.stdout.log"
    compile_log.write_text("\n".join(commands) + "\n")
    command_records = adapter_module.compiler_helper.compiler_command_evidence(
        compile_log.read_text(), compiler, flags, behaviour=worker.BEHAVIOUR)
    dependency_log = output / "library_dependencies.stdout.log"
    dependency_log.write_text("libTEST_ONLY.so => /TEST_ONLY/dependency.so (0x1)\n")
    save_json(output / "build_identity.json", {"library_path": "build/src/libBehaviour.so", "library_sha256": library_sha,
        "source_sha256": worker.SOURCE_SHA256, "generation_arguments": worker.BUILD_ARGUMENTS,
        "makefile_sha256": adapter_module.transport.sha256(build / "Makefile.mfront"),
        "compiler_flags_policy": adapter_module.transport.COMPILER_POLICY, "compiler_flags_override": flags,
        "compiler_flags_makefile": ["CXXFLAGS=-O2 -fno-fast-math -std=c++20"],
        "actual_compiler_commands": [record["command"] for record in command_records],
        "compiler_commands_artifact": "build/compile.stdout.log", "compiler_commands_sha256": worker.sha256(compile_log),
        "compiler_command_policy": adapter_module.compiler_helper.COMPILER_COMMAND_POLICY,
        "compiler_command_evidence": command_records,
        "compiler_helper_sha256": adapter_module.SOURCE_HASHES[worker.COMPILER_HELPER_KEY],
        "dependency_artifact": "library_dependencies.stdout.log", "dependency_artifact_sha256": worker.sha256(dependency_log),
        "dependency_sha256": {"/TEST_ONLY/dependency.so": "c" * 64}})
    raw.update(input_sha256=adapter_module.transport.sha256(output / "input.json"),
        worker_sha256=adapter_module.SOURCE_HASHES[adapter_module.WORKER.relative_to(adapter_module.ROOT).as_posix()],
        source_sha256=worker.SOURCE_SHA256, transport_sha256=adapter_module.SOURCE_HASHES[worker.TRANSPORT_KEY], runtime=runtime,
        compiler_helper_sha256=adapter_module.SOURCE_HASHES[worker.COMPILER_HELPER_KEY],
        source_files=deepcopy(adapter_module.SOURCE_HASHES), process_policy=deepcopy(runtime["process_policy"]),
        resource_limits=deepcopy(runtime["resource_limits"]),
        extra_native_bindings=deepcopy(runtime["extra_native_bindings"]),
        conventions={"physical": "xx,yy,zz,xy,xz,yz", "native": "xx,yy,zz,sqrt2*xy,sqrt2*xz,sqrt2*yz",
                     "strain": "infinitesimal_tensor_not_engineering_shear", "stress_unit": "MPa",
                     "energy_unit": "MPa = MJ/m^3 per reference volume"})
    path = output / "mtest.res"
    path.write_text(table_text(raw["mtest"]["states"]))
    raw["mtest"]["native_output_table"] = worker.parse_mtest_table(path, raw["mtest"]["states"])
    save_json(output / "runtime.json", runtime)
    save_json(output / "native_raw.json", raw)
    return raw


def install_testonly_executor(monkeypatch, tmp_path, raw_template, corrupt=None):
    fake_runtime(monkeypatch, tmp_path)
    calls = []
    def execute(command, output, label, timeout):
        calls.append(command)
        raw = write_testonly_native(output, ref.canonical_settings(), raw_template, monkeypatch)
        if corrupt is not None:
            corrupt(Path(output), raw)
            save_json(Path(output) / "native_raw.json", raw)
    monkeypatch.setattr(adapter_module, "_process", execute)
    return calls


def test_injected_declared_model_preserves_common_evidence_and_no_cad(tmp_path, monkeypatch, raw_template):
    calls = install_testonly_executor(monkeypatch, tmp_path, raw_template)
    adapter = adapter_module.MFrontViscoelasticAdapter()
    lab = Lab(tmp_path / "store", model_analysis_adapters={adapter.backend: adapter})
    lab.create_study("S-visco", "TEST ONLY viscoelastic adapter", "TEST ONLY numerical contract",
                     "Full state and energy contract", "Synthetic numerical scope")
    settings = ref.canonical_settings()
    result = lab.run_model_analysis(study_id="S-visco", experiment_id="E-visco-test", backend=adapter.backend, settings=settings)
    assert result["status"] == "COMPLETED_REVIEW_REQUIRED", result["validations"]
    assert result["decision"] == "NOT_RELEASED" and result["cad_revision"] is None
    assert result["solver_status"] == "COMPLETED" and result["converged"] is True
    assert set(ref.PENDING) == {v["type"] for v in result["validations"] if v["status"] == "UNKNOWN"}
    folder = lab.store / "experiments/E-visco-test"
    proposal = load_json(folder / "proposal.json")
    assert result["model_revision"] == canonical_hash({"settings": settings,
        "declaration": proposal["extensions"]["model_analysis"]["declaration"]})
    assert all(v["evidence_ids"] for v in result["validations"] if v["status"] == "PASS")
    assert load_json(folder / "thread.json")["model_revision"] == result["model_revision"]
    assert lab.inspect_experiment("E-visco-test") == result
    assert calls and "exec" in calls[0] and "--containall" in calls[0] and "--cleanenv" in calls[0]
    assert not result["input_parameters"]
    with pytest.raises(FileExistsError):
        lab.run_model_analysis(study_id="S-visco", experiment_id="E-visco-test", backend=adapter.backend, settings=settings)


@pytest.mark.parametrize("corrupt", [
    lambda p, r: r.update(input_sha256="f" * 64),
    lambda p, r: r["runtime"].update(mgis_binding_sha256="f" * 64),
    lambda p, r: r["behaviour_description"].update(computes_dissipated_energy=False),
    lambda p, r: (p / "build/src/libBehaviour.so").write_bytes(b"corrupt"),
    lambda p, r: (p / "mtest.res").unlink(),
    lambda p, r: r["mtest"]["states"][3].update(stored_energy_mpa=100.),
    lambda p, r: (p / "mfront_viscoelastic_worker.py").write_text("changed captured source"),
])
def test_corrupt_or_missing_native_fields_are_failed_execution_with_unknowns(tmp_path, monkeypatch, raw_template, corrupt):
    install_testonly_executor(monkeypatch, tmp_path, raw_template, corrupt)
    adapter = adapter_module.MFrontViscoelasticAdapter()
    outcome = adapter.solve(tmp_path / "failed", ref.canonical_settings())
    validate_outcome(outcome)
    assert outcome["status"] == "REJECTED" and outcome["solver_status"] == "FAILED_EXECUTION"
    assert outcome["pending_validations"] == ref.PENDING
    assert outcome["provenance"]["input_runtime_identity"]["profile"] == "LOCAL_EXACT_SIF"
    assert (tmp_path / "failed/analysis_raw.json").exists()
    assert (tmp_path / "failed/native_raw.json").exists()


def test_numeric_native_failure_remains_rejected_invalid_metrics(tmp_path, monkeypatch, raw_template):
    def corrupt(p, raw):
        raw["mgis"]["steps"][2]["stress_physical_mpa"][3] += .1
    install_testonly_executor(monkeypatch, tmp_path, raw_template, corrupt)
    outcome = adapter_module.MFrontViscoelasticAdapter().solve(tmp_path / "numeric-fail", ref.canonical_settings())
    validate_outcome(outcome)
    assert outcome["solver_status"] == "COMPLETED" and outcome["status"] == "REJECTED"
    assert all(m["valid"] is False for m in outcome["metrics"].values())


def test_deployment_drift_blocks_before_process(tmp_path, monkeypatch):
    fake_runtime(monkeypatch, tmp_path)
    adapter = adapter_module.MFrontViscoelasticAdapter()
    monkeypatch.setenv("CAELAB_MFRONT_IMAGE_SHA256", "f" * 64)
    monkeypatch.setattr(adapter_module, "_process", no_native)
    outcome = adapter.solve(tmp_path / "drift", ref.canonical_settings())
    assert outcome["solver_status"] == "FAILED_EXECUTION"
    assert "environment changed" in outcome["checks"][0]["observed"]


def test_other_sif_is_not_admitted(tmp_path, monkeypatch):
    fake_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(adapter_module.transport, "_runtime_identity",
                        lambda: (tmp_path / "image.sif", "7" * 64, str(tmp_path / "singularity")))
    adapter = adapter_module.MFrontViscoelasticAdapter()
    with pytest.raises(RuntimeError, match="exact local SIF"):
        adapter.input_runtime_identity()


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":1e9999}'])
def test_duplicate_or_nonfinite_metadata_rejected(tmp_path, text):
    path = tmp_path / "bad.json"
    path.write_text(text)
    with pytest.raises(ValueError):
        adapter_module._strict_json(path)
