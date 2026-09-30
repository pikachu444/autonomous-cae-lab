"""Independent numerical/domain checks; these synthetic states are not native proof."""

from copy import deepcopy
from types import SimpleNamespace
import json
import math

import numpy as np
import pytest

from plugins.material_point import reference as ref
from caelab.adapters import mfront_material_worker as worker


def settings():
    return {"case": "isotropic_small_strain", "material": {"youngs_modulus_mpa": 200., "poisson_ratio": .25},
            "temperature_k": 293.15, "limits": deepcopy(ref.FIXED_LIMITS),
            "history": [{"time_s": 0., "strain": [0.] * 6},
                        {"time_s": 1., "strain": [.001, -.002, .003, .004, -.005, .006]},
                        {"time_s": 2., "strain": [-.001, .002, -.003, -.004, .005, -.006]},
                        {"time_s": 3., "strain": [0.] * 6}]}


def independent_stress(strain):
    # E=200,nu=.25 => lambda=80,mu=80; deliberately independent known constants.
    return [80. * sum(strain[:3]) + 160. * value for value in strain[:3]] + [160. * value for value in strain[3:]]


class FakeState:
    def __init__(self):
        self.gradients = np.zeros((1, 6))
        self.thermodynamic_forces = np.zeros((1, 6))
        self.internal_state_variables = np.zeros((1, 2))
        self.stored_energies = np.zeros(1)
        self.dissipated_energies = np.zeros(1)
        self.properties = {}
        self.external = {}


class FakeManager:
    def __init__(self, behaviour, count):
        self.s0, self.s1 = FakeState(), FakeState()
        self.K = np.zeros((1, 6, 6))


class FakeBinding:
    MaterialDataManager = FakeManager
    class BehaviourIntegrationOptions:
        integration_type = property(lambda self: "TEST_ONLY")
        compute_speed_of_sound = property(lambda self: False)
    IntegrationType = SimpleNamespace(IntegrationWithConsistentTangentOperator="TEST_ONLY")

    @staticmethod
    def setMaterialProperty(state, name, value):
        state.properties[name] = value

    @staticmethod
    def setExternalStateVariable(state, name, value):
        state.external[name] = value

    @staticmethod
    def integrate(manager, options, dt, begin, end):
        assert dt > 0 and begin == 0 and end == 1
        assert manager.s0.properties == manager.s1.properties == {"YoungModulus": 200., "PoissonRatio": .25}
        assert manager.s0.external == manager.s1.external == {"Temperature": 293.15}
        c = np.diag([160.] * 6)
        c[:3, :3] += 80.
        manager.s1.thermodynamic_forces[:] = c @ manager.s1.gradients[0]
        manager.K[0] = c
        # State-dependent counters prove clone/restore includes all exposed buffers.
        manager.s1.internal_state_variables[:] = manager.s0.internal_state_variables + 1
        manager.s1.stored_energies[:] = manager.s0.stored_energies + 2
        manager.s1.dissipated_energies[:] = manager.s0.dissipated_energies + 3
        return SimpleNamespace(exit_status=1, time_step_increase_factor=1., error_message="", n=1)

    @staticmethod
    def update(manager):
        for name in ("gradients", "thermodynamic_forces", "internal_state_variables", "stored_energies", "dissipated_energies"):
            getattr(manager.s0, name)[:] = getattr(manager.s1, name)


def observations(tmp_path):
    spec = settings()
    mgis = worker.integrate_history(FakeBinding, None, spec, "b" * 64, tmp_path)
    mstates = []
    for entry in spec["history"]:
        strain, stress = entry["strain"], independent_stress(entry["strain"])
        mstates.append({"time_s": entry["time_s"], "gradients_kelvin": ref.to_kelvin(strain),
            "strain_physical": list(strain), "stress_kelvin_mpa": ref.to_kelvin(stress),
            "stress_physical_mpa": stress, "properties_native": [0., 0.] if entry["time_s"] == 0 else [200., .25],
            "state_phase": "INITIAL_UNPREPARED" if entry["time_s"] == 0 else "INTEGRATED",
            "external_state_variables_native": [0.] if entry["time_s"] == 0 else [293.15],
            "iterations": 0 if entry["time_s"] == 0 else 1, "substeps": 0})
    return spec, {"library_sha256": "b" * 64, "mgis": mgis, "mtest": {"library_sha256": "b" * 64,
        "material_properties": {"YoungModulus": 200., "PoissonRatio": .25},
        "external_state_variables": {"Temperature": 293.15}, "substep_limit": 1, "states": mstates}}


def test_independent_hooke_normal_shear_energy_and_kelvin_tangent():
    result = ref.analytical_reference(settings())
    assert result["lambda_mpa"] == 80. and result["mu_mpa"] == 80.
    assert result["states"][1]["stress_physical_mpa"] == pytest.approx([.32, -.16, .64, .64, -.8, .96])
    assert result["states"][1]["stress_kelvin_mpa"] == pytest.approx([.32, -.16, .64,
        .64 * math.sqrt(2), -.8 * math.sqrt(2), .96 * math.sqrt(2)])
    assert result["states"][1]["energy_density_mpa"] == pytest.approx(.0136)
    assert result["tangent_kelvin_mpa"] == [[240., 80., 80., 0., 0., 0.], [80., 240., 80., 0., 0., 0.],
        [80., 80., 240., 0., 0., 0.], [0., 0., 0., 160., 0., 0.],
        [0., 0., 0., 0., 160., 0.], [0., 0., 0., 0., 0., 160.]]
    assert result["states"][-1]["stress_physical_mpa"] == [0.] * 6
    assert result["states"][-1]["energy_density_mpa"] == 0.


def test_kelvin_round_trip_preserves_tensor_product_and_unequal_order():
    value = [.001, -.002, .003, .004, -.005, .006]
    native = ref.to_kelvin(value)
    assert ref.from_kelvin(native) == pytest.approx(value, abs=1e-18)
    assert sum(x * x for x in native) == pytest.approx(sum(x * x * (1 if i < 3 else 2) for i, x in enumerate(value)))


def test_worker_independent_clones_all_state_buffers_without_advancing_nominal(tmp_path):
    spec, raw = observations(tmp_path)
    initial = raw["mgis"]["steps"][1]["initial_state"]
    assert initial["internal_state_variables"] == [1., 1.]
    assert initial["stored_energies"] == [2.]
    assert initial["dissipated_energies"] == [3.]
    for step in raw["mgis"]["steps"]:
        assert step["nominal_before_probes"] == step["nominal_after_probes"]
        assert step["initial_state"] == step["nominal_initial_after_probes"]
        assert all(p["initial_state"] == step["initial_state"] for fd in step["finite_differences"] for p in fd["probes"])
    a = worker.fresh_manager(FakeBinding, None, initial)
    b = worker.fresh_manager(FakeBinding, None, initial)
    a.s0.internal_state_variables[:] = 999
    assert b.s0.internal_state_variables.tolist() == [[1., 1.]]
    assert initial["internal_state_variables"] == [1., 1.]
    assessed = ref.assess(spec, raw)
    assert all(c["status"] == "PASS" for c in assessed["checks"])
    assert all(m["valid"] for m in assessed["metrics"].values())
    assert assessed["metrics"]["max_energy_density_error"]["value"] < 1e-17
    assert set(ref.PENDING) <= set(assessed["pending_validations"])
    json.dumps(assessed, allow_nan=False)


@pytest.mark.parametrize("mutation", [
    lambda s: s.update(case="finite_strain"), lambda s: s.update(extra="unsupported"),
    lambda s: s.pop("history"), lambda s: s["material"].update(youngs_modulus_mpa=True),
    lambda s: s["material"].update(youngs_modulus_mpa=0), lambda s: s["material"].update(youngs_modulus_mpa=float("inf")),
    lambda s: s["material"].update(poisson_ratio=.5), lambda s: s["material"].update(poisson_ratio=-1),
    lambda s: s["material"].update(poisson_ratio=float("nan")), lambda s: s.update(temperature_k=0),
    lambda s: s["history"][1].update(time_s=0), lambda s: s["history"][0]["strain"].__setitem__(0, .001),
    lambda s: s["history"][1]["strain"].__setitem__(3, .010001), lambda s: s["history"][1].update(strain=[0.] * 5),
    lambda s: s["history"][1].update(time_s=True), lambda s: s["limits"].update(stress_relative=1e-7),
    lambda s: s["limits"].update(finite_difference_steps=[1e-7, 1e-8]),
    lambda s: s["limits"].update(finite_difference_steps=[1e-7, 1e-8, True]),
])
def test_strict_invalid_settings_rejected(mutation):
    spec = settings()
    mutation(spec)
    with pytest.raises(ValueError):
        ref.validate_settings(spec)


def test_validation_reference_declaration_assessment_do_not_mutate_inputs(tmp_path):
    spec, raw = observations(tmp_path)
    original, native = deepcopy(spec), deepcopy(raw)
    ref.validate_settings(spec)["material"]["youngs_modulus_mpa"] = 1.
    ref.analytical_reference(spec)
    declaration = ref.model_declaration(spec)
    assert declaration["model"]["geometry"] is None and declaration["model"]["mesh"] is None
    assert declaration["loads"][0]["convention"] == "physical_tensor"
    declaration["loads"][0]["history"][1]["strain"][0] = 99.
    ref.assess(spec, raw)
    assert spec == original and raw == native


@pytest.mark.parametrize("kind", ["scaling", "order", "stress", "tangent", "fd", "state", "dt", "properties", "nominal_changed", "driver_binary", "unreliable", "failed", "mtest"])
def test_measured_failures_preserve_invalid_numeric_metrics(tmp_path, kind):
    spec, raw = observations(tmp_path)
    step = raw["mgis"]["steps"][0]
    if kind == "scaling":
        step["gradients_kelvin"][3:] = step["strain_physical"][3:]
    elif kind == "order":
        step["gradients_kelvin"][3], step["gradients_kelvin"][5] = step["gradients_kelvin"][5], step["gradients_kelvin"][3]
    elif kind == "stress":
        step["stress_physical_mpa"][0] += .1
    elif kind == "tangent":
        step["tangent_kelvin_mpa"][4][4] *= .5
    elif kind == "fd":
        # Only the smallest h fails: every h, not the best h, must be qualified.
        step["finite_differences"][2]["probes"][1]["stress_kelvin_mpa"][5] += .01
    elif kind == "state":
        step["finite_differences"][0]["probes"][0]["initial_state"]["internal_state_variables"][0] += 1
    elif kind == "dt":
        step["finite_differences"][0]["probes"][0]["initial_state"]["dt_s"] += 1
    elif kind == "properties":
        step["finite_differences"][0]["probes"][0]["initial_state"]["material_properties"]["YoungModulus"] += 1
    elif kind == "nominal_changed":
        step["nominal_after_probes"]["stress_kelvin_mpa"][0] += 1
    elif kind == "driver_binary":
        raw["mtest"]["library_sha256"] = "c" * 64
    elif kind in ("unreliable", "failed"):
        step["integration_return"] = 0 if kind == "unreliable" else -1
    elif kind == "mtest":
        raw["mtest"]["states"][2]["stress_kelvin_mpa"][5] += .01
    result = ref.assess(spec, raw)
    assert any(c["status"] == "FAIL" for c in result["checks"])
    assert all(not m["valid"] and m["reason"] for m in result["metrics"].values())
    assert all(m["value"] is not None for m in result["metrics"].values())
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("mutation", [
    lambda r: r.pop("mtest"), lambda r: r["mgis"]["steps"].pop(),
    lambda r: r["mgis"]["steps"][0].pop("stress_kelvin_mpa"),
    lambda r: r["mgis"]["steps"][0]["tangent_kelvin_mpa"].pop(),
    lambda r: r["mgis"]["steps"][0]["stress_kelvin_mpa"].__setitem__(0, float("nan")),
    lambda r: r["mgis"]["steps"][0]["finite_differences"].pop(),
    lambda r: r["mgis"]["steps"][0]["finite_differences"][0]["probes"].pop(),
    lambda r: r["mgis"]["steps"][0].update(integration_return=True),
    lambda r: r["mtest"]["states"][1].pop("properties_native"),
])
def test_malformed_native_data_raises_without_fabricating_arrays(tmp_path, mutation):
    spec, raw = observations(tmp_path)
    mutation(raw)
    with pytest.raises(ValueError):
        ref.assess(spec, raw)


def test_native_unreliable_stops_without_advancing_history(tmp_path):
    class Unreliable(FakeBinding):
        @staticmethod
        def integrate(*args):
            result = FakeBinding.integrate(*args)
            result.exit_status = 0
            return result
        @staticmethod
        def update(manager):
            pytest.fail("An unreliable nominal state must never advance")
    result = worker.integrate_history(Unreliable, None, settings(), "b" * 64, tmp_path)
    assert result["native_rejection"]["integration_return"] == 0
    assert len(result["steps"]) == 1


def test_declared_zero_isvs_and_unsupported_energy_getters_are_never_called():
    class NoOptionalBuffers:
        gradients = np.zeros((1, 6))
        thermodynamic_forces = np.zeros((1, 6))
        @property
        def internal_state_variables(self):
            pytest.fail("MGIS3 zero-column getter would divide by zero")
        @property
        def stored_energies(self):
            pytest.fail("Behavior does not compute stored energy")
        @property
        def dissipated_energies(self):
            pytest.fail("Behavior does not compute dissipated energy")
    behaviour = SimpleNamespace(internal_state_variables=[], computesStoredEnergy=False, computesDissipatedEnergy=False)
    captured = worker.snapshot(NoOptionalBuffers(), {"YoungModulus": 200., "PoissonRatio": .25}, {"Temperature": 293.15}, 1., behaviour)
    assert captured["internal_state_variables"] == captured["stored_energies"] == captured["dissipated_energies"] == []
    class NoOptionalManager:
        def __init__(self, b, count):
            self.s0, self.s1 = NoOptionalBuffers(), NoOptionalBuffers()
    binding = SimpleNamespace(MaterialDataManager=NoOptionalManager,
                              setMaterialProperty=lambda *args: None, setExternalStateVariable=lambda *args: None)
    restored = worker.fresh_manager(binding, behaviour, captured)
    assert worker.snapshot(restored.s0, captured["material_properties"], captured["external_state_variables"], 1., behaviour) == captured


def test_installed_package_identity_uses_actual_spec_and_resolved_binding(tmp_path):
    package = tmp_path / "package"
    (package / ".spack").mkdir(parents=True)
    binding = package / "TEST_ONLY.so"
    binding.write_bytes(b"TEST ONLY binding")
    spec = package / ".spack/spec.json"
    spec.write_text(json.dumps({"spec": {"nodes": [{"name": "mgis", "version": "3.0", "hash": "TEST_ONLY"}]}}))
    output = tmp_path / "output"
    output.mkdir()
    identity = worker.installed_package_identity(package, "mgis", "3.0", binding, output)
    assert identity["version"] == "3.0" and identity["spack_hash"] == "TEST_ONLY"
    assert identity["spec_sha256"] == worker.sha256(spec)
    assert identity["binding_sha256"] == worker.sha256(binding)
    assert (output / "mgis_installed_spec.json").read_bytes() == spec.read_bytes()
    spec.write_text(json.dumps({"spec": {"nodes": [{"name": "mgis", "version": "4.0", "hash": "TEST_ONLY"}]}}))
    with pytest.raises(ValueError, match="version drifted"):
        worker.installed_package_identity(package, "mgis", "3.0", binding, output)
    outside = tmp_path / "OUTSIDE.so"
    outside.write_bytes(b"TEST ONLY")
    with pytest.raises(ValueError, match="outside"):
        worker.installed_package_identity(package, "mgis", "3.0", outside, output)


def test_fixed_portable_compiler_policy_keeps_O2_and_no_fast_math():
    flags = worker.portable_compiler_flags("-fno-fast-math -O2 -DNDEBUG", "-DTFEL_ARCH64 -std=c++20", worker.TFEL_PREFIX + "/include")
    assert "-O2" in flags and "-fno-fast-math" in flags and "-std=c++20" in flags
    for extra in ("-march=native", "-ftree-vectorize", "-ffast-math", "-mtune=native"):
        with pytest.raises(ValueError, match="portable"):
            worker.portable_compiler_flags("-fno-fast-math -O2 " + extra, "-std=c++20", worker.TFEL_PREFIX + "/include")


def test_mtest_records_full_actual_tensors_and_initial_unprepared_phase(tmp_path):
    class FakeMTest:
        def __init__(self):
            self.history, self.properties, self.calls = {}, {}, []
        def setModellingHypothesis(self, h):
            assert h == "Tridimensional"
        def setBehaviour(self, interface, library, name):
            assert interface == "generic" and name == "Elasticity"
        def setMaximumNumberOfSubSteps(self, count):
            assert count == 1
        def setMaximumNumberOfIterations(self, count):
            assert count == 10
        def setStrainEpsilon(self, epsilon):
            assert epsilon == 1e-14
        def setStressEpsilon(self, epsilon):
            assert epsilon == 1e-10
        def setMaterialProperty(self, key, value):
            self.properties[key] = value
        def setExternalStateVariable(self, key, value):
            assert key == "Temperature"
            self.temperature = value
        def setImposedStrain(self, name, values):
            self.history[name] = values
        def setStrain(self, values):
            assert values == [0.] * 6
        def setStress(self, values):
            assert values == [0.] * 6
        def setOutputFileName(self, name):
            self.output = name
        def setOutputFilePrecision(self, precision):
            assert precision == 17
        def completeInitialisation(self):
            assert len(self.history) == 6
        def initializeCurrentState(self, state):
            state.e1, state.s1, state.iv1 = [0.] * 6, [0.] * 6, []
            state.mprops1, state.evs0, state.iterations, state.subSteps = [0., 0.], [0.], 0, 0
        def initializeWorkSpace(self, wk):
            pass
        def printOutput(self, time, state):
            pass
        def execute(self, state, wk, before, after):
            assert after > before
            self.calls.append((before, after))
            state.e1 = [self.history[name][after] for name in ("EXX", "EYY", "EZZ", "EXY", "EXZ", "EYZ")]
            state.s1 = ref.to_kelvin(independent_stress(ref.from_kelvin(state.e1)))
            state.mprops1, state.evs0, state.iterations = [200., .25], [self.temperature], 1
    fake = FakeMTest()
    module = SimpleNamespace(MTest=lambda: fake, MTestCurrentState=SimpleNamespace, MTestWorkSpace=SimpleNamespace)
    library = tmp_path / "TEST_ONLY.so"
    library.write_bytes(b"TEST ONLY, no native integration")
    result = worker.mtest_history(module, library, settings(), tmp_path)
    assert result["library_sha256"] == worker.sha256(library)
    assert result["states"][0]["state_phase"] == "INITIAL_UNPREPARED"
    assert result["states"][0]["properties_native"] == [0., 0.]
    assert result["states"][0]["external_state_variables_native"] == [0.]
    assert fake.calls == [(0., 1.), (1., 2.), (2., 3.)]
    assert result["states"][1]["stress_physical_mpa"] == pytest.approx([.32, -.16, .64, .64, -.8, .96])
    assert all(row["state_phase"] == "INTEGRATED" and row["properties_native"] == [200., .25]
               and row["external_state_variables_native"] == [293.15] for row in result["states"][1:])
