"""Cold source contracts only: every native-shaped value is MOCK_UNSOLVED.

No TFEL/MGIS/MTest behaviour is compiled, loaded or integrated in these tests.
The fake integration below uses the frozen pure reference as a test double;
its numerical agreement proves a serialization contract, never native accuracy.
"""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from caelab.adapters import mfront_hyperelastic as adapter
from caelab.adapters import mfront_hyperelastic_worker as worker
domain = adapter.domain
SVK_SOURCE = Path(__file__).parent / "fixtures/mfront/SaintVenantKirchhoffElasticity.mfront"


@pytest.fixture(scope="session")
def contract(tmp_path_factory):
    """Explicit test double generates the complete shape; no private raw data."""
    output = tmp_path_factory.mktemp("MOCK_UNSOLVED_contract")
    library = output / "MOCK_UNSOLVED.so"
    library.write_bytes(b"MOCK_UNSOLVED_NOT_A_LIBRARY")
    raw = worker.integrate_history(FakeBinding(), fake_behaviour(), spec(), worker.sha256(library), output)
    raw["mtest"] = worker.mtest_history(fake_mtest_module(FakeMTest()), library, spec(), output)
    raw["test_evidence_kind"] = "SYNTHETIC_NOT_NATIVE"
    assert domain.assess(spec(), raw)["passed"]
    return raw


def spec():
    return domain.canonical_settings()


def dump(folder, name, value):
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    worker.save(path, value)


def write_synthetic_native(output, settings, contract):
    """Retained raw source/build envelope, expressly NOT a compiled behaviour."""
    native = deepcopy(contract)
    build = output / "build/src"
    build.mkdir(parents=True)
    (build / "libBehaviour.so").write_bytes(b"MOCK_UNSOLVED_NOT_A_SHARED_LIBRARY")
    (output / "build" / (worker.BEHAVIOUR + ".mfront")).write_bytes(SVK_SOURCE.read_bytes())
    flags = adapter.transport.portable_compiler_flags("-fno-fast-math -O2", "-DTFEL_ARCH64 -std=c++20", worker.TFEL_PREFIX + "/include")
    compiler = "/MOCK_UNSOLVED/g++"
    command = compiler + " " + " ".join(flags) + " -c synthetic.cxx"
    makefile = "CXXFLAGS = " + " ".join(flags) + "\n"
    (build / "Makefile.mfront").write_text(makefile)
    (output / "build/compile.stdout.log").write_text(command + "\n")
    digest = worker.sha256(build / "libBehaviour.so")
    native["library_sha256"] = native["mtest"]["library_sha256"] = digest
    runtime = {"python": "MOCK_UNSOLVED", "numpy": "MOCK_UNSOLVED", "tfel": "tfel-config 5.0.0 (MOCK_UNSOLVED)",
        "mfront": "MOCK_UNSOLVED", "compiler": "MOCK_UNSOLVED", "make": "MOCK_UNSOLVED", "mgis": "3.0",
        "tfel_recommended_oflags0": "-fno-fast-math -O2", "tfel_cpp_compiler_flags": "-DTFEL_ARCH64 -std=c++20",
        "tfel_include_path": worker.TFEL_PREFIX + "/include", "executables": {"g++": {"path": compiler}}}
    for name, prefix, version, binding_name in (("mgis", worker.MGIS_PREFIX, "3.0", "mgis"), ("tfel", worker.TFEL_PREFIX, "5.0.0", "mtest")):
        dump(output, name + "_installed_spec.json", {"spec": {"nodes": [{"name": name, "version": version, "hash": "MOCK_UNSOLVED_spack"}]}})
        binding_path, binding_sha = prefix + "/lib/MOCK_UNSOLVED.so", "c" * 64
        runtime[binding_name + "_binding_path"] = binding_path
        runtime[binding_name + "_binding_sha256"] = binding_sha
        runtime[name + "_package"] = {"name": name, "version": version, "spack_hash": "MOCK_UNSOLVED_spack", "package_prefix": prefix,
            "spec_sha256": worker.sha256(output / (name + "_installed_spec.json")), "binding_path": binding_path,
            "binding_sha256": binding_sha, "upstream_binary_source_commit": "UNKNOWN"}
    desc = worker.descriptor(FakeBinding(), fake_behaviour())
    identity = {"library_path": "build/src/libBehaviour.so", "library_sha256": digest, "source_sha256": worker.SOURCE_SHA256,
        "generation_arguments": list(worker.BUILD_ARGUMENTS), "makefile_sha256": worker.sha256(build / "Makefile.mfront"),
        "actual_compiler_commands": [command], "compiler_commands_artifact": "build/compile.stdout.log",
        "compiler_flags_policy": worker.COMPILER_POLICY, "compiler_flags_override": flags,
        "compiler_flags_makefile": [makefile.strip()], "dependency_sha256": {"/MOCK_UNSOLVED/lib.so": "d" * 64}}
    native.update(schema_version="1", input_sha256=worker.sha256(output / "input.json"), source_sha256=worker.SOURCE_SHA256,
        worker_sha256=adapter._SOURCE_SHA["mfront_hyperelastic_worker.py"], captured_source_sha256=deepcopy(adapter._SOURCE_SHA),
        runtime=runtime, behaviour_description=desc, finite_strain_options={"stress_measure": "PK1", "tangent_operator": "DPK1_DF"},
        process_policy=json.loads((output / "input.json").read_text())["process_policy"])
    licenses = []
    for name in ("LICENCE-GNU-GPL", "LICENCE-CECILL-A-EN", "LICENCE-CECILL-A-FR"):
        path = output / "licenses" / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("MOCK_UNSOLVED license identity fixture, not legal approval")
        licenses.append({"name": name, "sha256": worker.sha256(path)})
    dump(output, "source_attribution.json", {"source_sha256": worker.SOURCE_SHA256, "reference_commit": worker.TFEL_COMMIT, "licenses": licenses})
    for name, value in (("native_raw.json", native), ("runtime.json", runtime), ("build_identity.json", identity), ("behaviour_description.json", desc)):
        dump(output, name, value)
    return native


def fake_native(monkeypatch, tmp_path, contract, mutation=None):
    image = tmp_path / "MOCK_UNSOLVED.sif"
    image.write_bytes(b"MOCK_UNSOLVED_NOT_A_CONTAINER")
    calls = []
    monkeypatch.setattr(adapter.material, "_runtime_identity", lambda: (image, worker.sha256(image), "MOCK_UNSOLVED_singularity"))
    def process(command, output, label, **kwargs):
        calls.append((command, label, kwargs))
        (output / (label + ".stdout.log")).write_text("MOCK_UNSOLVED no native process executed\n")
        (output / (label + ".stderr.log")).write_text("")
        if label == "hyperelastic_worker":
            raw = write_synthetic_native(output, spec(), contract)
            if mutation:
                mutation(output, raw)
            dump(output, "native_raw.json", raw)
        return "MOCK_UNSOLVED metadata"
    monkeypatch.setattr(adapter.execution, "_process", process)
    return calls, image


class Variable:
    def __init__(self, name, size=9, kind="Tensor"):
        self.name, self.size, self.kind = name, size, kind
    def getType(self):
        return self.kind


def fake_behaviour():
    gradient, force = Variable("DeformationGradient"), Variable("FirstPiolaKirchhoffStress")
    return SimpleNamespace(hypothesis="Tridimensional", btype="FINITE", kinematic="F_CAUCHY", behaviour=worker.BEHAVIOUR,
        tfel_version="5.0.0 MOCK_UNSOLVED", build_id="MOCK_UNSOLVED", source="MOCK_UNSOLVED",
        computesStoredEnergy=True, computesDissipatedEnergy=False, internal_state_variables=[],
        gradients=[gradient], thermodynamic_forces=[force], tangent_operator_blocks=[(force, gradient)],
        material_properties=[Variable("YoungModulus"), Variable("PoissonRatio")], external_state_variables=[Variable("Temperature")])


class FakeState:
    def __init__(self):
        self.gradients = np.zeros((1, 9))
        self.thermodynamic_forces = np.zeros((1, 9))
        self.stored_energies = np.zeros(1)
        self.properties, self.external = {}, {}
    @property
    def internal_state_variables(self):
        pytest.fail("MGIS3 absent-ISV getter must never be called")
    @property
    def dissipated_energies(self):
        pytest.fail("Unsupported dissipated-energy getter must never be called")


class FakeManager:
    def __init__(self, behaviour, count):
        assert count == 1
        self.s0, self.s1, self.K = FakeState(), FakeState(), None
    def allocateArrayOfTangentOperatorBlocks(self):
        self.K = np.zeros((1, 9, 9))


class FakeBinding:
    Hypothesis = SimpleNamespace(Tridimensional="Tridimensional")
    BehaviourType = SimpleNamespace(STANDARDFINITESTRAINBEHAVIOUR="FINITE")
    BehaviourKinematic = SimpleNamespace(FINITESTRAINKINEMATIC_F_CAUCHY="F_CAUCHY")
    FiniteStrainBehaviourOptionsStressMeasure = SimpleNamespace(PK1="PK1", CAUCHY="CAUCHY")
    FiniteStrainBehaviourOptionsTangentOperator = SimpleNamespace(DPK1_DF="DPK1_DF", DSIG_DF="DSIG_DF")
    IntegrationType = SimpleNamespace(IntegrationWithConsistentTangentOperator="CONSISTENT")
    MaterialDataManager = FakeManager
    def __init__(self, fail_at=None, code=0, raises_at=None):
        self.calls, self.updates = [], []
        self.fail_at, self.code, self.raises_at = fail_at, code, raises_at
    def FiniteStrainBehaviourOptions(self):
        return SimpleNamespace(stress_measure="CAUCHY", tangent_operator="DSIG_DF")
    def BehaviourIntegrationOptions(self):
        return SimpleNamespace(integration_type="CONSISTENT", compute_speed_of_sound=False)
    def getArraySize(self, variables, hypothesis):
        return sum(v.size for v in variables)
    def getVariableSize(self, variable, hypothesis):
        return variable.size
    def setMaterialProperty(self, state, name, value):
        state.properties[name] = value
    def setExternalStateVariable(self, state, name, value):
        state.external[name] = value
    def integrate(self, manager, options, dt, begin, end):
        assert begin == 0 and end == 1 and dt > 0
        self.calls.append(manager)
        if self.raises_at == len(self.calls):
            raise RuntimeError("MOCK_UNSOLVED interrupted integration")
        values = [float(value) for value in manager.s1.gradients.reshape(-1)]
        response = domain.response(values, spec()["material"])
        manager.s1.thermodynamic_forces[:] = response["pk1_stress_mpa"]
        manager.s1.stored_energies[:] = response["stored_energy_density_mpa"]
        manager.K[:] = response["pk1_tangent_mpa"]
        return SimpleNamespace(exit_status=self.code if self.fail_at == len(self.calls) else 1,
            time_step_increase_factor=1., error_message="MOCK_UNSOLVED", n=0)
    def update(self, manager):
        self.updates.append(manager)
        for name in ("gradients", "thermodynamic_forces", "stored_energies"):
            getattr(manager.s0, name)[:] = getattr(manager.s1, name)


def test_frozen_domain_bytes_and_default_metric_contract():
    assert worker.sha256(domain.__file__) == "fe90482f7b4114b0a7a3fcf3d9d6c98d7b3b305c571ff6b3d7879b1581002bc9"
    assert worker.sha256(Path(domain.__file__).with_name("__init__.py")) == "c1b942901836390150aa3963dc3fb131691ec43602d47cded60a2e45679ca7ca"
    assert len(set(adapter.MFrontHyperelasticAdapter.default_metrics)) == 21
    assert set(worker.F_COMPONENTS) == {"xx", "yy", "zz", "xy", "yx", "xz", "zx", "yz", "zy"}
    source_pin = json.loads(SVK_SOURCE.with_suffix(".source.json").read_text())
    assert SVK_SOURCE.stat().st_size == source_pin["bytes"] == 3002
    assert worker.sha256(SVK_SOURCE) == source_pin["sha256"] == worker.SOURCE_SHA256
    assert source_pin["commit"] == worker.TFEL_COMMIT and source_pin["source_url"] == worker.SOURCE_URL


def test_declaration_is_pure_immutable_and_has_no_cad(monkeypatch):
    monkeypatch.setattr(adapter.material, "_runtime_identity", lambda: pytest.fail("Pure declaration reached runtime"))
    original = spec()
    assert adapter.MFrontHyperelasticAdapter().describe_model(original) == domain.model_declaration(original)
    assert original == spec()
    assert domain.model_declaration(original)["model"]["geometry"] is None


@pytest.mark.parametrize("mutate", [
    lambda s: s["material"].update(poisson_ratio=.5), lambda s: s["material"].update(youngs_modulus_mpa=True),
    lambda s: s.update(temperature_k=0), lambda s: s["history"][1].update(time_s=0),
    lambda s: s["history"][2]["deformation_gradient"].__setitem__(0, -1),
    lambda s: s["history"][2]["deformation_gradient"].__setitem__(3, float("nan")),
    lambda s: s["history"][2].update(deformation_gradient=[1.] * 6),
    lambda s: s["limits"].update(stress_relative=1e-7),
    lambda s: s["limits"].update(finite_difference_steps=[1e-7, 1e-8]),
    lambda s: s.update(source="untrusted.mfront")])
def test_invalid_admission_precedes_all_runtime(monkeypatch, tmp_path, mutate):
    monkeypatch.setattr(adapter.material, "_runtime_identity", lambda: pytest.fail("Invalid input reached native preflight"))
    monkeypatch.setattr(adapter.execution, "_process", lambda *args, **kwargs: pytest.fail("Invalid input launched a command"))
    monkeypatch.setattr(adapter, "save_json", lambda *args, **kwargs: pytest.fail("Invalid input wrote a native artifact"))
    s = spec()
    mutate(s)
    output = tmp_path / "new-parent/invalid"
    result = adapter.MFrontHyperelasticAdapter().solve(output, s)
    assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN" and result["metrics"] == {}
    assert result["converged"] is None and result["raw_result"] is None
    assert result["provenance"]["source_capture_status"] == "NOT_RUN"
    assert result["provenance"]["domain_plugin"]["source_artifact"] is None
    assert "captured_source_sha256" not in result["provenance"]
    assert not output.exists() and not output.parent.exists()


def test_native_envelope_pass_is_only_synthetic_and_retains_policy(monkeypatch, tmp_path, contract):
    monkeypatch.delenv("CAELAB_CODEASTER_TIME_LIMIT_SECONDS", raising=False)
    monkeypatch.delenv("CAELAB_CODEASTER_WALL_TIMEOUT_SECONDS", raising=False)
    calls, image = fake_native(monkeypatch, tmp_path, contract)
    result = adapter.MFrontHyperelasticAdapter().solve(tmp_path / "out", spec())
    assert result["status"] == "COMPLETED" and result["solver_status"] == "COMPLETED"
    assert result["assessment"]["release_status"] == "NOT_RELEASED"
    assert len(result["assessment"]["native_observations"]["time_s"]) == 11
    assert result["provenance"]["compiled_source_equivalence"] == "UNKNOWN"
    assert set(adapter._SOURCES) == worker.SOURCE_NAMES
    command, _, args = calls[-1]
    assert args["timeout"] is None and result["provenance"]["process_policy"]["solver_time_seconds"] == 86400
    assert "--cleanenv" in command and "--containall" in command and "--no-home" in command
    assert command[-1] == adapter._SCRIPT and "-I -B" in adapter._SCRIPT
    assert adapter.material.PROCESS_TIMEOUT_SECONDS == 240
    assert image.read_bytes() == b"MOCK_UNSOLVED_NOT_A_CONTAINER"


@pytest.mark.parametrize("change", [
    lambda o, r: r.update(input_sha256="0" * 64), lambda o, r: r.update(worker_sha256="0" * 64),
    lambda o, r: r.update(source_sha256="0" * 64), lambda o, r: r.update(captured_source_sha256={}),
    lambda o, r: r.update(library_sha256="0" * 64), lambda o, r: r.update(process_policy={}),
    lambda o, r: r.update(finite_strain_options={"stress_measure": "CAUCHY", "tangent_operator": "DSIG_DF"}),
    lambda o, r: (o / "build/src/libBehaviour.so").write_bytes(b"foreign"),
    lambda o, r: (o / "build/compile.stdout.log").write_text("fake command"),
    lambda o, r: (o / "mgis_installed_spec.json").write_text("{}"),
    lambda o, r: (o / "behaviour_description.json").write_text("{}"),
    lambda o, r: (o / "licenses/LICENCE-GNU-GPL").write_text("foreign"),
    lambda o, r: r["mtest"].update(library_sha256="0" * 64),
    lambda o, r: r["steps"][0].pop("stored_energy_density_mpa"),
    lambda o, r: r["steps"][0]["finite_differences"].pop(),
    lambda o, r: r["steps"][0]["finite_differences"][0]["probes"].pop(),
    lambda o, r: r["steps"].pop(),
    lambda o, r: r.update(extra_overflow=float("inf"))])
def test_malformed_or_foreign_raw_cannot_publish_result(monkeypatch, tmp_path, contract, change):
    fake_native(monkeypatch, tmp_path, contract, change)
    with pytest.raises((RuntimeError, ValueError, TypeError)):
        adapter.MFrontHyperelasticAdapter().solve(tmp_path / "out", spec())
    assert not (tmp_path / "out/analysis_raw.json").exists()
    assert (tmp_path / "out/execution_failure.json").is_file()
    assert (tmp_path / "out/hyperelastic_worker.stdout.log").is_file()


def test_finite_wrong_native_fields_retain_invalid_metrics(monkeypatch, tmp_path, contract):
    def mutate(output, raw):
        raw["steps"][2]["pk1_stress_mpa"][3] += 1.
    fake_native(monkeypatch, tmp_path, contract, mutate)
    result = adapter.MFrontHyperelasticAdapter().solve(tmp_path / "out", spec())
    assert result["status"] == "REJECTED" and result["solver_status"] == "COMPLETED"
    assert all(not m["valid"] and m["reason"] for m in result["metrics"].values())
    assert result["assessment"]["release_status"] == "NOT_RELEASED"
    assert (tmp_path / "out/native_raw.json").is_file()


@pytest.mark.parametrize("field,value", [("gradient_sizes", [6]), ("force_sizes", [6]), ("computes_stored_energy", False),
    ("internal_state_variables", ["unexpected"]), ("computes_dissipated_energy", True), ("stored_energy_measure", "per_mass"),
    ("component_order", list(reversed(worker.F_COMPONENTS))), ("kinematic", "SMALL_STRAIN")])
def test_descriptor_mismatch_even_when_raw_and_descriptor_artifact_agree(monkeypatch, tmp_path, contract, field, value):
    def mutate(output, raw):
        raw["behaviour_description"][field] = value
        dump(output, "behaviour_description.json", raw["behaviour_description"])
    fake_native(monkeypatch, tmp_path, contract, mutate)
    with pytest.raises(RuntimeError, match="descriptor"):
        adapter.MFrontHyperelasticAdapter().solve(tmp_path / "out", spec())


@pytest.mark.parametrize("kind", ["source", "image", "copied_source"])
def test_late_identity_drift_retains_original_partial_no_result(monkeypatch, tmp_path, contract, kind):
    if kind == "source":
        source = tmp_path / "guarded-domain.py"
        source.write_bytes(adapter._SOURCE_BYTES["domain_reference.py"])
        monkeypatch.setitem(adapter._SOURCES, "domain_reference.py", source)
    calls, image = fake_native(monkeypatch, tmp_path, contract)
    previous = adapter.execution._process
    def changed(*args, **kwargs):
        value = previous(*args, **kwargs)
        if args[2] == "hyperelastic_worker":
            target = source if kind == "source" else image if kind == "image" else args[1] / "execution_control.py"
            target.write_bytes(b"late foreign bytes")
        return value
    monkeypatch.setattr(adapter.execution, "_process", changed)
    with pytest.raises(RuntimeError, match="drift"):
        adapter.MFrontHyperelasticAdapter().solve(tmp_path / "out", spec())
    assert not (tmp_path / "out/analysis_raw.json").exists()
    assert (tmp_path / "out/native_raw.json").is_file()


@pytest.mark.parametrize("error,status", [(RuntimeError("MOCK process failure"), "FAILED_EXECUTION"),
    (adapter.execution_control.ExecutionCancelled("MOCK observed cancellation"), "CANCELLED"),
    (adapter.execution_control.ExecutionCleanupFailed("MOCK owned PID unreaped"), "CLEANUP_PENDING")])
def test_owned_failure_control_truth_and_partial_retention(monkeypatch, tmp_path, error, status):
    image = tmp_path / "image"
    image.write_bytes(b"MOCK_UNSOLVED")
    monkeypatch.setattr(adapter.material, "_runtime_identity", lambda: (image, worker.sha256(image), "MOCK_UNSOLVED"))
    def failed(command, output, label, **kwargs):
        if label == "hyperelastic_worker":
            (output / "mgis.partial.json").write_text('{"test_evidence_kind":"MOCK_UNSOLVED","steps":[]}')
            raise error
        return "MOCK_UNSOLVED"
    monkeypatch.setattr(adapter.execution, "_process", failed)
    with pytest.raises(type(error)) as observed:
        adapter.MFrontHyperelasticAdapter().solve(tmp_path / "out", spec())
    assert observed.value is error
    receipt = json.loads((tmp_path / "out/execution_failure.json").read_text())
    assert receipt["status"] == status and receipt["numerical_verdict"] == "UNKNOWN"
    assert receipt["decision"] == "NOT_RELEASED" and (tmp_path / "out/mgis.partial.json").exists()
    assert not (tmp_path / "out/analysis_raw.json").exists()


def test_cleanup_exception_survives_failure_receipt_io_error(monkeypatch, tmp_path):
    error = adapter.execution_control.ExecutionCleanupFailed("MOCK still owned")
    monkeypatch.setattr(adapter.MFrontHyperelasticAdapter, "_execute", lambda *args: (_ for _ in ()).throw(error))
    monkeypatch.setattr(adapter, "save_json", lambda *args: (_ for _ in ()).throw(OSError("MOCK failed receipt write")))
    with pytest.raises(adapter.execution_control.ExecutionCleanupFailed) as observed:
        adapter.MFrontHyperelasticAdapter().solve(tmp_path / "out", spec())
    assert observed.value is error


@pytest.mark.parametrize("kind", ["existing", "symlink"])
def test_old_output_never_overwritten(tmp_path, kind):
    output = tmp_path / "out"
    if kind == "existing":
        output.mkdir()
        (output / "old").write_bytes(b"preserved")
    else:
        original = tmp_path / "original"
        original.mkdir()
        (original / "old").write_bytes(b"preserved")
        output.symlink_to(original, target_is_directory=True)
    with pytest.raises(ValueError, match="overwritten"):
        adapter.MFrontHyperelasticAdapter().solve(output, spec())
    assert (output / "old").read_bytes() == b"preserved"
    invalid = spec()
    invalid["material"]["poisson_ratio"] = .5
    rejected = adapter.MFrontHyperelasticAdapter().solve(output, invalid)
    assert rejected["status"] == "REJECTED" and rejected["raw_result"] is None
    assert set(output.iterdir()) == {output / "old"}
    assert (output / "old").read_bytes() == b"preserved"


def test_physical9_pk1_conversion_keeps_xy_yx_directions():
    f = [1.1, .9, 1., .2, -.1, .05, .03, -.04, .06]
    p = [2., 3., 4., 5., 6., 7., 8., 9., 10.]
    fm = np.array([[f[0], f[3], f[5]], [f[4], f[1], f[7]], [f[6], f[8], f[2]]])
    pm = np.array([[p[0], p[3], p[5]], [p[4], p[1], p[7]], [p[6], p[8], p[2]]])
    matrix = pm @ fm.T / np.linalg.det(fm)
    expected = [matrix[i, j] for i, j in ((0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2))]
    assert worker.cauchy_from_pk1(f, p) == pytest.approx(expected, abs=1e-14)


def test_complete_initial_and_independent_cache_state_clone():
    binding, behaviour = FakeBinding(), fake_behaviour()
    props = {"YoungModulus": 210000., "PoissonRatio": .3}
    external = {"Temperature": 293.15}
    original = worker.initial_manager(binding, behaviour, props, external)
    baseline = worker.snapshot(original, original.s0, props, external, 1.)
    before_hash = worker.state_hash(baseline)
    first, second = worker.fresh_manager(binding, behaviour, baseline), worker.fresh_manager(binding, behaviour, baseline)
    assert not np.shares_memory(first.s0.gradients, first.s1.gradients)
    assert not np.shares_memory(first.K, second.K)
    first.s1.gradients[0, 3] += 1e-7
    first.K[0, 3, 4] = 123.
    assert worker.state_hash(baseline) == before_hash
    assert worker.snapshot(second, second.s0, props, external, 1.) == baseline
    assert baseline["stored_energies"] == [0.] and baseline["internal_state_variables"] == []


@pytest.mark.parametrize("change", [lambda b: b.pop("stored_energies"), lambda b: b.update(stored_energies=[]),
    lambda b: b.update(internal_state_variables=[0.]), lambda b: b.update(dissipated_energies=[0.]),
    lambda b: b.update(manager_tangent_cache_mpa=[[0.] * 6 for _ in range(6)]), lambda b: b.update(dt_s=True)])
def test_incomplete_baseline_rejected_before_integration(change):
    binding, behaviour = FakeBinding(), fake_behaviour()
    props, external = {"YoungModulus": 210000., "PoissonRatio": .3}, {"Temperature": 293.15}
    initial = worker.initial_manager(binding, behaviour, props, external)
    baseline = worker.snapshot(initial, initial.s0, props, external, 1.)
    change(baseline)
    with pytest.raises((ValueError, KeyError)):
        worker.fresh_manager(binding, behaviour, baseline)
    assert binding.calls == []


def test_all_594_synthetic_probes_and_11_nominals_have_independent_complete_states(tmp_path):
    binding = FakeBinding()
    raw = worker.integrate_history(binding, fake_behaviour(), spec(), "a" * 64, tmp_path)
    assert len(binding.calls) == 605 and len(binding.updates) == 11
    assert len({id(manager) for manager in binding.calls}) == 605
    assert raw["initial"]["phase"] == "INITIAL_UNPREPARED" and raw["steps"][0]["time_s"] == 1.
    assert len(list((tmp_path / "probes").rglob("column_*.json"))) == 594
    baseline = raw["initial"]["state"]
    for step in raw["steps"]:
        assert step["nominal_before_probes"] == step["nominal_after_probes"]
        assert step["initial_state"]["manager_tangent_cache_mpa"] == baseline["manager_tangent_cache_mpa"]
        assert step["native_dt_s"] == step["dt_s"]
        assert len(step["finite_differences"]) == 3
        for fd in step["finite_differences"]:
            assert {(p["column"], p["sign"]) for p in fd["probes"]} == {(j, s) for j in range(9) for s in (-1, 1)}
            assert all(p["initial_state"] == step["initial_state"] for p in fd["probes"])
            assert all(p["initial_state_sha256"] == worker.state_hash(p["initial_state"]) and
                p["final_state_sha256"] == worker.state_hash(p["final_state"]) for p in fd["probes"])
        baseline = step["nominal_after_probes"]
    library = tmp_path / "MOCK_UNSOLVED.so"
    library.write_bytes(b"MOCK_UNSOLVED_NOT_A_LIBRARY")
    raw["library_sha256"] = worker.sha256(library)
    raw["mtest"] = worker.mtest_history(fake_mtest_module(FakeMTest()), library, spec(), tmp_path)
    raw["test_evidence_kind"] = "MOCK_UNSOLVED_SYNTHETIC_NOT_NATIVE"
    assessed = domain.assess(spec(), raw)
    assert assessed["passed"] and assessed["release_status"] == "NOT_RELEASED"
    assert set(assessed["metrics"]) == set(adapter.MFrontHyperelasticAdapter.default_metrics)


@pytest.mark.parametrize("at,code", [(1, -1), (2, 0), (56, 0)])
def test_unreliable_nominal_or_probe_stops_history_and_preserves_real_partial(tmp_path, at, code):
    binding = FakeBinding(fail_at=at, code=code)
    raw = worker.integrate_history(binding, fake_behaviour(), spec(), "a" * 64, tmp_path)
    assert len(binding.calls) == at and len(binding.updates) == (1 if at == 56 else 0)
    assert raw["native_rejection"]["integration_return"] == code
    assert json.loads((tmp_path / "mgis.partial.json").read_text())["native_rejection"]["integration_return"] == code
    assert adapter._native_rejection(raw, spec())["integration_return"] == code


def test_interrupted_probe_keeps_previous_complete_signed_record(tmp_path):
    binding = FakeBinding(raises_at=3)
    with pytest.raises(RuntimeError, match="interrupted"):
        worker.integrate_history(binding, fake_behaviour(), spec(), "a" * 64, tmp_path)
    partial = json.loads((tmp_path / "mgis.partial.json").read_text())
    assert len(binding.updates) == 0 and len(partial["steps"][0]["finite_differences"][0]["probes"]) == 1
    assert len(list((tmp_path / "probes").rglob("column_*.json"))) == 1


@pytest.mark.parametrize("change", [lambda b: setattr(b, "computesStoredEnergy", False), lambda b: setattr(b, "computesDissipatedEnergy", True),
    lambda b: setattr(b, "internal_state_variables", [Variable("hidden")]), lambda b: setattr(b, "gradients", [Variable("Strain", 6)]),
    lambda b: setattr(b, "thermodynamic_forces", [Variable("Stress", 6)]), lambda b: setattr(b, "tangent_operator_blocks", []),
    lambda b: setattr(b, "kinematic", "SMALL_STRAIN"), lambda b: setattr(b, "tfel_version", "unknown"),
    lambda b: setattr(b, "material_properties", [Variable("Density")])])
def test_wrong_live_descriptor_refuses_before_any_manager_or_state(change):
    binding, behaviour = FakeBinding(), fake_behaviour()
    change(behaviour)
    with pytest.raises(ValueError):
        worker.descriptor(binding, behaviour)
    assert binding.calls == []


def test_explicit_options_and_single_block_descriptor():
    binding = FakeBinding()
    options = worker.finite_options(binding)
    assert options.stress_measure == "PK1" and options.tangent_operator == "DPK1_DF"
    assert worker.descriptor(binding, fake_behaviour())["tangent_operator_blocks"][0]["shape"] == [9, 9]


@pytest.mark.parametrize("cpu,wall", [(0, None), (True, None), (-1, None), (86400, 0), (86400, True)])
def test_zero_or_invalid_budget_never_means_unlimited(cpu, wall):
    p = adapter.policy.process_budgets()
    p.update(solver_time_seconds=cpu, subprocess_timeout_seconds=wall)
    with pytest.raises(ValueError):
        worker.validated_policy(p)


def test_user_budgets_are_explicit_while_default_wall_is_none(monkeypatch):
    monkeypatch.delenv("CAELAB_CODEASTER_TIME_LIMIT_SECONDS", raising=False)
    monkeypatch.delenv("CAELAB_CODEASTER_WALL_TIMEOUT_SECONDS", raising=False)
    assert worker.validated_policy(adapter.policy.process_budgets())["subprocess_timeout_seconds"] is None
    monkeypatch.setenv("CAELAB_CODEASTER_TIME_LIMIT_SECONDS", "999")
    monkeypatch.setenv("CAELAB_CODEASTER_WALL_TIMEOUT_SECONDS", "888")
    p = worker.validated_policy(adapter.policy.process_budgets())
    assert p["solver_time_seconds"] == 999 and p["subprocess_timeout_seconds"] == 888
    assert p["solver_time_source"] == p["wall_time_source"] == "USER_ENVIRONMENT"


class FakeMTest:
    def __init__(self, fail_at=None):
        self.recorded, self.maps, self.calls = {}, {}, []
        self.fail_at = fail_at
    def __getattr__(self, name):
        return lambda *args: self.recorded.__setitem__(name, args)
    def setImposedDeformationGradient(self, name, values):
        self.maps[name] = values
    def initializeCurrentState(self, state):
        state.e1, state.s1, state.iterations, state.subSteps = list(worker.IDENTITY), [0.] * 6, 0, 0
    def execute(self, state, workspace, t0, t1):
        self.calls.append((t0, t1))
        if self.fail_at == len(self.calls):
            raise RuntimeError("MOCK_UNSOLVED MTest failure")
        state.e1 = [self.maps[name][t1] for name in worker.F_NAMES]
        sigma = domain.response(state.e1, spec()["material"])["cauchy_stress_mpa"]
        state.s1 = list(sigma[:3]) + [math_sqrt2() * value for value in sigma[3:]]
        state.iterations, state.subSteps = 1, 1


def math_sqrt2():
    return 2. ** .5


def fake_mtest_module(instance):
    return SimpleNamespace(MTest=lambda: instance, MTestCurrentState=SimpleNamespace, MTestWorkSpace=SimpleNamespace)


def test_mtest_names_physical9_and_public_kelvin6_endpoints_same_library(tmp_path):
    library = tmp_path / "library"
    library.write_bytes(b"MOCK_UNSOLVED")
    instance = FakeMTest()
    raw = worker.mtest_history(fake_mtest_module(instance), library, spec(), tmp_path)
    assert len(raw["steps"]) == 11 and len(instance.calls) == 11 and instance.calls[0] == (0., 1.)
    assert list(instance.maps) == list(worker.F_NAMES)
    assert raw["library_sha256"] == worker.sha256(library)
    assert instance.recorded["setMaximumNumberOfSubSteps"] == (1,)
    assert instance.recorded["setDeformationGradient"] == (worker.IDENTITY,)
    assert raw["stored_energy"] == "UNKNOWN" and all(len(s["cauchy_stress_kelvin_mpa"]) == 6 for s in raw["steps"])
    assert all(s["deformation_gradient"] == entry["deformation_gradient"] for s, entry in zip(raw["steps"], spec()["history"][1:]))


def test_mtest_failure_keeps_prior_endpoints_without_synthesized_success(tmp_path):
    library = tmp_path / "library"
    library.write_bytes(b"MOCK_UNSOLVED")
    instance = FakeMTest(fail_at=3)
    with pytest.raises(RuntimeError, match="MTest failure"):
        worker.mtest_history(fake_mtest_module(instance), library, spec(), tmp_path)
    raw = json.loads((tmp_path / "mtest.partial.json").read_text())
    assert len(raw["steps"]) == 2 and "execution_failure" in raw


def test_capture_hash_or_membership_refusal_precedes_dynamic_import(tmp_path):
    for name, data in adapter._SOURCE_BYTES.items():
        (tmp_path / name).write_bytes(data)
    envelope = {"captured_source_sha256": deepcopy(adapter._SOURCE_SHA)}
    worker.assert_captures(tmp_path, envelope)
    (tmp_path / "execution_control.py").write_bytes(b"foreign")
    with pytest.raises(ValueError, match="drifted"):
        worker.assert_captures(tmp_path, envelope)
    envelope["captured_source_sha256"].pop("execution_control.py")
    with pytest.raises(ValueError, match="Complete"):
        worker.assert_captures(tmp_path, envelope)


def test_wrong_installed_svk_bytes_refuse_before_generation(monkeypatch, tmp_path):
    source = tmp_path / "gallery.mfront"
    source.write_bytes(b"gallery variant")
    monkeypatch.setattr(worker, "SOURCE_PATH", source)
    transport = SimpleNamespace(_executable=lambda *args: pytest.fail("Wrong source reached executable discovery"))
    with pytest.raises(ValueError, match="gallery fallback forbidden"):
        worker.build_native(tmp_path, transport)
    assert not (tmp_path / "build").exists()


def test_finite_json_exponent_overflow_is_not_hidden_by_extra_metadata(tmp_path):
    (tmp_path / "overflow.json").write_text('{"extra_observation":1e999}')
    with pytest.raises(ValueError):
        adapter._json(tmp_path, "overflow.json")


def test_build_uses_exact_source_generic3d_portable_flags_and_no_scientific_wall_timer(monkeypatch, tmp_path):
    # A compiler-command construction test; these are inert local fixture files.
    prefix = tmp_path / "MOCK_UNSOLVED_tfel"
    include = prefix / "include"
    include.mkdir(parents=True)
    source = prefix / "share/doc/mfront/tests/behaviours" / (worker.BEHAVIOUR + ".mfront")
    source.parent.mkdir(parents=True)
    source.write_bytes(SVK_SOURCE.read_bytes())
    licenses = prefix / "share/doc/tfel"
    licenses.mkdir(parents=True)
    for name in ("LICENCE-GNU-GPL", "LICENCE-CECILL-A-EN", "LICENCE-CECILL-A-FR"):
        (licenses / name).write_text("MOCK_UNSOLVED license fixture")
    tools = {}
    for name in ("mfront", "mtest", "g++", "make", "tfel-config", "ldd"):
        path = prefix / "bin" / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"MOCK_UNSOLVED_NOT_AN_EXECUTABLE")
        tools[name] = str(path)
    dependency = tmp_path / "dependency.so"
    dependency.write_bytes(b"MOCK_UNSOLVED_NOT_A_SHARED_LIBRARY")
    monkeypatch.setattr(worker, "TFEL_PREFIX", str(prefix))
    monkeypatch.setattr(worker, "SOURCE_PATH", source)
    monkeypatch.setattr(adapter.transport, "TFEL_PREFIX", str(prefix))
    flags = adapter.transport.portable_compiler_flags("-fno-fast-math -O2", "-std=c++20", str(include))
    calls = []
    def command(argv, output, label, timeout):
        calls.append((argv, label, timeout))
        if label == "generate":
            (output / "src").mkdir()
            return "MOCK_UNSOLVED generation not executed"
        if label == "compile":
            (output / "src/libBehaviour.so").write_bytes(b"MOCK_UNSOLVED_NOT_COMPILED")
            (output / "src/Makefile.mfront").write_text("CXXFLAGS = " + " ".join(flags) + "\n")
            line = tools["g++"] + " " + " ".join(flags) + " -c MOCK_UNSOLVED.cxx"
            (output / "compile.stdout.log").write_text(line + "\n")
            return line
        return {"tfel": "tfel-config 5.0.0 MOCK_UNSOLVED", "tfel_recommended_oflags0": "-fno-fast-math -O2",
            "tfel_cpp_compiler_flags": "-std=c++20", "tfel_include_path": str(include),
            "library_dependencies": "lib.so => " + str(dependency) + " (0x0000)"}.get(label, "MOCK_UNSOLVED")
    transport = SimpleNamespace(shutil=adapter.transport.shutil, _executable=lambda name: tools[name],
        _command=command, portable_compiler_flags=adapter.transport.portable_compiler_flags)
    output = tmp_path / "build-output"
    output.mkdir()
    library, runtime, build = worker.build_native(output, transport)
    generate = next(row for row in calls if row[1] == "generate")
    compile_row = next(row for row in calls if row[1] == "compile")
    assert generate[0][1:] == worker.BUILD_ARGUMENTS and generate[2] is None and compile_row[2] is None
    assert compile_row[0][-1].startswith("CXXFLAGS=") and "-O2" in compile_row[0][-1]
    assert build["source_sha256"] == worker.SOURCE_SHA256 and build["library_sha256"] == worker.sha256(library)
    assert build["compiler_flags_override"] == flags and build["dependency_sha256"] == {str(dependency): worker.sha256(dependency)}
    assert all(row[2] == 10 for row in calls if row[1] not in ("generate", "compile"))


@pytest.mark.parametrize("kind", ["outside", "version", "duplicate", "missing"])
def test_reused_installed_package_guard_checks_real_readonly_metadata(tmp_path, kind):
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    binding = prefix / "binding.so"
    binding.write_bytes(b"MOCK_UNSOLVED_NOT_LOADED")
    spec_path = prefix / ".spack/spec.json"
    spec_path.parent.mkdir()
    nodes = [{"name": "mgis", "version": "3.0", "hash": "MOCK_UNSOLVED"}]
    if kind == "outside":
        binding = tmp_path / "foreign.so"
        binding.write_bytes(b"MOCK_UNSOLVED_NOT_LOADED")
    elif kind == "version":
        nodes[0]["version"] = "other"
    elif kind == "duplicate":
        nodes += deepcopy(nodes)
    else:
        nodes = []
    worker.save(spec_path, {"spec": {"nodes": nodes}})
    with pytest.raises(ValueError):
        adapter.transport.installed_package_identity(prefix, "mgis", "3.0", binding, tmp_path)
