"""Pure independent science gates and TEST ONLY buffer-driver observations."""

from copy import deepcopy
import json
import math
from types import SimpleNamespace

import numpy as np
import pytest

from plugins.material_point import viscoelastic_reference as ref
from caelab.adapters import mfront_viscoelastic_worker as worker

LIBRARY_SHA = "a" * 64


def independent_matrix(k, g):
    c = np.zeros((6, 6), dtype=float)
    c[:3, :3] = k - 2 * g / 3
    c += np.eye(6) * (2 * g)
    return c


class FakeState:
    def __init__(self):
        self.gradients = np.zeros((1, 6))
        self.thermodynamic_forces = np.zeros((1, 6))
        self.internal_state_variables = np.zeros((1, 6))
        self.stored_energies = np.zeros(1)
        self.dissipated_energies = np.zeros(1)
        self.gradients_stride = self.thermodynamic_forces_stride = 6
        self.properties, self.external = {}, {}


class FakeManager:
    def __init__(self, behaviour, count):
        self.n, self.s0, self.s1 = count, FakeState(), FakeState()
        self.K = np.zeros((1, 6, 6))

    def allocateArrayOfTangentOperatorBlocks(self):
        pass


class FakeBinding:
    MaterialDataManager = FakeManager
    MaterialStateManagerStorageMode = SimpleNamespace(EXTERNAL_STORAGE=object())

    @staticmethod
    def setMaterialProperty(state, name, array, mode):
        assert mode is FakeBinding.MaterialStateManagerStorageMode.EXTERNAL_STORAGE
        state.properties[name] = array

    @staticmethod
    def setExternalStateVariable(state, name, array, mode):
        assert mode is FakeBinding.MaterialStateManagerStorageMode.EXTERNAL_STORAGE
        state.external[name] = array

    @staticmethod
    def update(manager):
        # Pinned MGIS update zeroes K, then commits every s1 buffer to s0.
        manager.K[:] = 0.
        for name in worker.ARRAYS:
            getattr(manager.s0, name)[:] = getattr(manager.s1, name)
        for name in manager.s1.properties:
            manager.s0.properties[name][:] = manager.s1.properties[name]
        for name in manager.s1.external:
            manager.s0.external[name][:] = manager.s1.external[name]


class FakeTransport:
    """TEST ONLY native-array surrogate with independent Kelvin matrix algebra."""
    def __init__(self, return_code=1):
        self.return_code = return_code
        self.calls = 0

    def _integrate(self, binding, manager, dt):
        self.calls += 1
        k0, g0, k1, g1, tau = [manager.s0.properties[key][0] for key in worker.PROPERTY_NAMES]
        c0, c1 = independent_matrix(k0, g0), independent_matrix(k1, g1)
        e0, e1, q0 = manager.s0.gradients[0], manager.s1.gradients[0], manager.s0.internal_state_variables[0]
        a, one, one2 = math.exp(-dt / tau), -math.expm1(-dt / tau), -math.expm1(-2 * dt / tau)
        rate = (e1 - e0) / dt
        qinf = tau * (c1 @ rate)
        b = q0 - qinf
        q1 = a * q0 + one * qinf
        manager.s1.internal_state_variables[0] = q1
        manager.s1.thermodynamic_forces[0] = c0 @ e1 + q1
        manager.K[0] = c0 + tau * one / dt * c1
        manager.s1.stored_energies[0] = .5 * (e1 @ c0 @ e1 + q1 @ np.linalg.solve(c1, q1))
        dD = dt / tau * (qinf @ np.linalg.solve(c1, qinf)) + 2 * one * (
            qinf @ np.linalg.solve(c1, b)) + .5 * one2 * (b @ np.linalg.solve(c1, b))
        manager.s1.dissipated_energies[0] = manager.s0.dissipated_energies[0] + dD
        return {"integration_return": self.return_code, "time_step_increase_factor": 1.,
                "error_message": "", "failure_or_unreliable_point_index": 0}


def make_raw(tmp_path, settings=None):
    """Manufactured TEST ONLY observations, never retained as native acceptance."""
    settings = settings or ref.canonical_settings()
    behaviour = SimpleNamespace(computesStoredEnergy=True, computesDissipatedEnergy=True)
    transport = FakeTransport()
    mgis = worker.integrate_history(FakeBinding, behaviour, settings, LIBRARY_SHA, tmp_path, np, transport)
    props = dict(zip(worker.PROPERTY_NAMES, settings["material"].values()))
    rows = [mgis["initial"], *mgis["steps"]]
    states = [{**{key: deepcopy(row[key]) for key in (
        "time_s", "gradients_kelvin", "strain_physical", "stress_kelvin_mpa", "stress_physical_mpa",
        "branch_stress_kelvin_mpa", "branch_stress_physical_mpa", "stored_energy_mpa", "dissipated_energy_mpa")},
        "internal_state_variables": list(row["branch_stress_kelvin_mpa"]),
        "properties_native": [0.] * 5 if i == 0 else list(props.values()),
        "external_state_variables_native": [0.] if i == 0 else [settings["temperature_k"]],
        "iterations": 0 if i == 0 else 1, "substeps": 0,
        "state_phase": "INITIAL_UNPREPARED" if i == 0 else "INTEGRATED"} for i, row in enumerate(rows)]
    descriptor = {"behaviour": worker.BEHAVIOUR, "hypothesis": "TRIDIMENSIONAL",
        "gradients": ["Strain"], "thermodynamic_forces": ["Stress"], "gradient_size": 6, "force_size": 6,
        "material_properties": list(worker.PROPERTY_NAMES), "internal_state_variables": ["BranchStress"],
        "internal_state_variable_sizes": [6], "external_state_variables": ["Temperature"],
        "computes_stored_energy": True, "computes_dissipated_energy": True}
    raw = {"schema_version": "1", "library_sha256": LIBRARY_SHA,
        "test_evidence_kind": "SYNTHETIC_NOT_NATIVE",
        "behaviour_description": descriptor, "mgis": mgis,
        "mtest": {"library_sha256": LIBRARY_SHA, "states": states, "material_properties": props,
                  "external_state_variables": {"Temperature": settings["temperature_k"]},
                  "substep_limit": 1, "iteration_limit": 10, "strain_epsilon": 1e-14, "stress_epsilon_mpa": 1e-10,
                  "imposed_components": ["EXX", "EYY", "EZZ", "EXY", "EXZ", "EYZ"],
                  "imposed_interpolation": "piecewise_linear",
                  "imposed_history": [{"time_s": row["time_s"], "gradients_kelvin": ref.to_kelvin(row["strain"])}
                                      for row in settings["history"]],
                  "native_output_table": {"column_count": 21, "stored_energy_column": 20,
                      "dissipated_energy_column": 21, "sha256": "b" * 64, "rows": len(states)}}}
    assert transport.calls == (len(settings["history"]) - 1) * 37
    return raw


def test_hold_relaxation_and_zero_strain_has_branch_energy():
    material = ref.canonical_settings()["material"]
    qold = [1., -2., 3., .4, -.5, .6]
    step = ref.increment(material, [0.] * 6, [0.] * 6, qold, 1.)
    assert step["branch_stress_physical_mpa"] == pytest.approx([x / math.e for x in qold])
    assert step["stress_physical_mpa"] == pytest.approx(step["branch_stress_physical_mpa"])
    # Independently contract hydrostatic/deviatoric stresses including weight 2.
    trace = sum(qold[:3])
    dev = [x - trace / 3 for x in qold[:3]]
    initial_energy = .5 * (trace ** 2 / (9 * 2000) +
        (sum(x * x for x in dev) + 2 * sum(x * x for x in qold[3:])) / (2 * 1000))
    assert step["stored_energy_mpa"] == pytest.approx(initial_energy * math.exp(-2))
    assert step["dissipation_increment_mpa"] == pytest.approx(initial_energy * (1 - math.exp(-2)))
    assert step["stored_energy_mpa"] > 0
    assert .5 * ref.contraction(step["stress_physical_mpa"], [0.] * 6) == 0.


def test_shear_factor_kelvin_and_known_ramp_energy():
    material = ref.canonical_settings()["material"]
    strain = [0., 0., 0., .001, 0., 0.]
    step = ref.increment(material, [0.] * 6, strain, [0.] * 6, 1.)
    qxy = 2 * 1000 * .001 * (1 - math.exp(-1))
    sigma_xy = 2 * 500 * .001 + qxy
    assert step["stress_physical_mpa"] == pytest.approx([0., 0., 0., sigma_xy, 0., 0.])
    assert ref.to_kelvin(step["stress_physical_mpa"])[3] == pytest.approx(math.sqrt(2) * sigma_xy)
    assert step["stored_energy_mpa"] == pytest.approx(500 * 2 * .001 ** 2 + qxy ** 2 / (2 * 1000))
    assert ref.contraction(strain, step["stress_physical_mpa"]) == pytest.approx(
        sum(a * b for a, b in zip(ref.to_kelvin(strain), ref.to_kelvin(step["stress_physical_mpa"]))))


def test_tangent_limits_and_dt_dependence():
    m = ref.canonical_settings()["material"]
    cshort = ref.increment(m, [0.] * 6, [0.] * 6, [0.] * 6, 1e-12)["tangent_kelvin_mpa"]
    clong = ref.increment(m, [0.] * 6, [0.] * 6, [0.] * 6, 1e12)["tangent_kelvin_mpa"]
    assert np.array(cshort) == pytest.approx(independent_matrix(3000, 1500), rel=1e-12, abs=1e-9)
    assert np.array(clong) == pytest.approx(independent_matrix(1000, 500), rel=1e-10, abs=1e-8)
    assert ref.increment(m, [0.] * 6, [0.] * 6, [0.] * 6, .2)["tangent_kelvin_mpa"] != \
           ref.increment(m, [0.] * 6, [0.] * 6, [0.] * 6, .1)["tangent_kelvin_mpa"]


def test_reference_semigroup_prefix_work_and_tau_change():
    coarse = ref.analytical_reference(ref.canonical_settings())["states"]
    refined = ref.analytical_reference(ref.canonical_settings(refined=True))["states"]
    tau2 = ref.analytical_reference(ref.canonical_settings(relaxation_time_s=2.))["states"]
    assert len(coarse) == 9 and len(refined) == 17
    for a, b in zip(coarse, refined[::2]):
        assert a["time_s"] == b["time_s"]
        for key in ("stress_physical_mpa", "branch_stress_physical_mpa", "stored_energy_mpa", "dissipated_energy_mpa"):
            assert a[key] == pytest.approx(b[key], rel=1e-12, abs=1e-14)
        assert a["stored_energy_mpa"] + a["dissipated_energy_mpa"] == pytest.approx(a["work_mpa"], abs=1e-14)
        assert a["stored_energy_mpa"] >= 0
    assert all(b["dissipated_energy_mpa"] >= a["dissipated_energy_mpa"] for a, b in zip(coarse, coarse[1:]))
    assert tau2[1]["stress_physical_mpa"] != coarse[1]["stress_physical_mpa"]
    # The unloading endpoint retains nonzero branch stress and actual stored energy.
    assert coarse[3]["strain_physical"] == [0.] * 6
    assert max(map(abs, coarse[3]["branch_stress_physical_mpa"])) > 0
    assert coarse[3]["stored_energy_mpa"] > 0


@pytest.mark.parametrize("mutate", [
    lambda s: s["material"].update(relaxation_time_s=0.),
    lambda s: s["material"].update(branch_shear_modulus_mpa=-1.),
    lambda s: s["material"].update(equilibrium_bulk_modulus_mpa=True),
    lambda s: s["material"].update(relaxation_time_s=float("nan")),
    lambda s: s.update(temperature_k=float("inf")),
    lambda s: s["limits"].update(energy_relative=1e-7),
    lambda s: s["limits"].update(finite_difference_steps=[1e-7, 1e-8, 1e-6]),
    lambda s: s["history"][1].update(time_s=0.),
    lambda s: s["history"][0].update(strain=[.001] + [0.] * 5),
    lambda s: s["history"][1].update(strain=[0.] * 5),
    lambda s: s.update(source="/tmp/user.mfront"),
    lambda s: s.update(library="/tmp/user.so"),
    lambda s: s["material"].update(extra=1),
    lambda s: s["history"].extend(s["history"] * 4),
])
def test_strict_preflight_rejection(mutate):
    s = ref.canonical_settings()
    mutate(s)
    with pytest.raises(ValueError):
        ref.validate_settings(s)


def test_input_and_declaration_are_immutable():
    s = ref.canonical_settings()
    before = deepcopy(s)
    normalized, declaration = ref.validate_settings(s), ref.model_declaration(s)
    normalized["history"][1]["strain"][0] = .009
    declaration["model"]["materials"][0]["branch_shear_modulus_mpa"] = 3.
    assert s == before


def test_complete_testonly_native_observations_and_refinement(tmp_path):
    coarse_settings, fine_settings = ref.canonical_settings(), ref.canonical_settings(refined=True)
    a, b = tmp_path / "coarse", tmp_path / "fine"
    a.mkdir(); b.mkdir()
    coarse, fine = make_raw(a, coarse_settings), make_raw(b, fine_settings)
    verdict = ref.assess(coarse_settings, coarse)
    assert all(c["status"] == "PASS" for c in verdict["checks"]), verdict["checks"]
    assert all(m["valid"] for m in verdict["metrics"].values())
    assert ref.compare_refinement(coarse_settings, coarse, fine_settings, fine)["status"] == "PASS"


@pytest.fixture(scope="module")
def raw_template(tmp_path_factory):
    return make_raw(tmp_path_factory.mktemp("visco-reference-test-only"))

@pytest.fixture
def raw(raw_template):
    return deepcopy(raw_template)


@pytest.mark.parametrize("mutation,code", [
    (lambda r: r["mgis"]["steps"][2]["stress_physical_mpa"].__setitem__(3, 123.), "max_stress_physical_error"),
    (lambda r: r["mtest"]["states"][3].update(stored_energy_mpa=.1), "max_stored_energy_error"),
    (lambda r: r["mtest"]["states"][3].update(dissipated_energy_mpa=-.1), "native_dissipation_nondecreasing"),
    (lambda r: r["mgis"]["steps"][1]["initial_manager"]["s0"]["internal_state_variables"].__setitem__(4, 4.), "immutable_full_probe_state"),
    (lambda r: r["mgis"]["steps"][2]["finite_differences"][2]["probes"][5]["initial_manager"]["s1"]["stored_energies"].__setitem__(0, .3), "immutable_full_probe_state"),
    (lambda r: r["mgis"]["steps"][2]["finite_differences"][0]["probes"][1]["final_manager"]["s1"]["dissipated_energies"].__setitem__(0, .5), "immutable_full_probe_state"),
    (lambda r: r["mgis"]["steps"][4].update(integration_return=0), "reliable_integrations"),
    (lambda r: r["mgis"]["steps"][4]["finite_differences"][1]["probes"][8].update(integration_return=-1), "reliable_integrations"),
    (lambda r: r["mgis"]["steps"][1]["tangent_kelvin_mpa"][0].__setitem__(3, 1.), "analytical_tangent_relative_error"),
    (lambda r: r["mtest"]["states"][2].update(substeps=1), "native_driver_continuity"),
    (lambda r: r["mtest"]["states"][2].update(time_s=1.01), "exact_ordered_history"),
    (lambda r: r["mtest"]["states"][0].update(stored_energy_mpa=1e-15), "exact_ordered_history"),
])
def test_numeric_corruption_rejects_and_retains_finite_invalid_metrics(raw, mutation, code):
    mutation(raw)
    verdict = ref.assess(ref.canonical_settings(), raw)
    assert next(c for c in verdict["checks"] if c["code"] == code)["status"] == "FAIL"
    assert all(m["valid"] is False and m["reason"] for m in verdict["metrics"].values())
    import json
    json.dumps(verdict, allow_nan=False)


@pytest.mark.parametrize("mutation", [
    lambda r: r["behaviour_description"].update(computes_stored_energy=False),
    lambda r: r["behaviour_description"].update(internal_state_variable_sizes=[5]),
    lambda r: r["mtest"].pop("native_output_table"),
    lambda r: r["mtest"]["states"].pop(),
    lambda r: r["mgis"]["steps"][0]["finite_differences"].pop(),
    lambda r: r["mgis"]["steps"][0].update(stored_energy_mpa=float("nan")),
    lambda r: r["mgis"]["steps"][0]["finite_differences"][0]["probes"][0].update(column=False),
    lambda r: r["mgis"]["steps"][0]["initial_manager"]["metadata"].update(tangent_cache_shape=[6, 6]),
    lambda r: r["mgis"]["steps"][1]["nominal_after_probes"]["s1"].update(internal_state_variables=[0.] * 5),
])
def test_missing_or_malformed_native_data_is_execution_failure(raw, mutation):
    mutation(raw)
    with pytest.raises(ValueError):
        ref.assess(ref.canonical_settings(), raw)


def failed_state_verdict(raw):
    before = ref.state_hash(raw)
    verdict = ref.assess(ref.canonical_settings(), raw)
    assert ref.state_hash(raw) == before
    assert next(c for c in verdict["checks"] if c["code"] == "immutable_full_probe_state")["status"] == "FAIL"
    assert all(m["valid"] is False and m["reason"] for m in verdict["metrics"].values())
    json.dumps(verdict, allow_nan=False)
    return verdict


def rehash_step(step):
    step["initial_state_sha256"] = ref.state_hash(step["initial_manager"])
    step["nominal_after_update_sha256"] = ref.state_hash(step["nominal_after_update"])
    for fd in step["finite_differences"]:
        for probe in fd["probes"]:
            probe["initial_state_sha256"] = ref.state_hash(probe["initial_manager"])
            probe["final_state_sha256"] = ref.state_hash(probe["final_manager"])


PHYSICAL_BUFFERS = ("gradients_kelvin", "stress_kelvin_mpa", "internal_state_variables",
                    "stored_energies", "dissipated_energies", "material_properties", "external_state_variables")


def alter_buffer(state, field, amount=.1):
    value = state[field]
    if isinstance(value, dict):
        value[next(iter(value))][0] += amount
    else:
        value[-1] += amount


def test_committed_zero_cache_full_nonzero_state_and_final_saved_evidence(tmp_path):
    raw = make_raw(tmp_path)
    assert raw["test_evidence_kind"] == "SYNTHETIC_NOT_NATIVE"
    previous = raw["mgis"]["initial_manager"]
    for index, step in enumerate(raw["mgis"]["steps"]):
        before, after, committed = (step[name] for name in (
            "nominal_before_probes", "nominal_after_probes", "nominal_after_update"))
        assert before == after
        assert step["tangent_kelvin_mpa"] == after["tangent_cache_kelvin_mpa"]
        assert any(x != 0. for row in step["tangent_kelvin_mpa"] for x in row)
        assert committed["s0"] == committed["s1"] == after["s1"]
        assert all(committed[key] == after[key] for key in ("dt_s", "metadata"))
        assert committed["tangent_cache_kelvin_mpa"] == [[0.] * 6 for _ in range(6)]
        assert worker.state_hash(committed) == ref.state_hash(committed) == step["nominal_after_update_sha256"]
        current = step["initial_manager"]
        assert all(current[key] == previous[key] for key in previous if key != "dt_s")
        assert current["dt_s"] == ref.canonical_settings()["history"][index + 1]["time_s"] - \
                                   ref.canonical_settings()["history"][index]["time_s"]
        for fd in step["finite_differences"]:
            assert [(p["column"], p["sign"]) for p in fd["probes"]] == [(c, s) for c in range(6) for s in (-1, 1)]
            for probe in fd["probes"]:
                assert probe["initial_manager"] == current
                assert probe["initial_state_sha256"] == ref.state_hash(current)
        previous = committed
    # Mixed signed loading/unloading has actual nonzero memory in all six ISVs.
    assert all(x != 0. for x in raw["mgis"]["steps"][2]["nominal_after_update"]["s0"]["internal_state_variables"])
    saved = json.loads((tmp_path / "mgis.partial.json").read_text(encoding="utf-8"))
    assert saved == raw["mgis"]
    assert saved["steps"][-1]["nominal_after_update_sha256"] == ref.state_hash(saved["steps"][-1]["nominal_after_update"])
    assert all(c["status"] == "PASS" for c in ref.assess(ref.canonical_settings(), raw)["checks"])


def test_next_committed_baseline_changes_only_the_declared_nonuniform_dt(tmp_path):
    settings = ref.canonical_settings()
    for i, entry in enumerate(settings["history"]):
        entry["time_s"] = float(i * i)
    raw = make_raw(tmp_path, settings)
    assert [s["initial_manager"]["dt_s"] for s in raw["mgis"]["steps"]] == list(range(1, 16, 2))
    assert all(c["status"] == "PASS" for c in ref.assess(settings, raw)["checks"])


@pytest.mark.parametrize("index", [0, -1])
@pytest.mark.parametrize("missing", ["nominal_after_update", "nominal_after_update_sha256"])
def test_missing_actual_commit_including_final_increment_is_never_reconstructed(raw, index, missing):
    raw["mgis"]["steps"][index].pop(missing)
    with pytest.raises(ValueError, match="Nominal committed"):
        ref.assess(ref.canonical_settings(), raw)


@pytest.mark.parametrize("path", [
    (key,) for key in ("s0", "s1", "tangent_cache_kelvin_mpa", "dt_s", "metadata")
] + [(side, key) for side in ("s0", "s1") for key in (*PHYSICAL_BUFFERS, "shapes")])
def test_commit_requires_every_full_state_buffer_and_metadata(raw, path):
    value = raw["mgis"]["steps"][-1]["nominal_after_update"]
    for key in path[:-1]:
        value = value[key]
    value.pop(path[-1])
    with pytest.raises(ValueError, match="Nominal committed snapshot"):
        ref.assess(ref.canonical_settings(), raw)


@pytest.mark.parametrize("bad_hash", [None, True, 3, "unknown", "G" * 64, "a" * 63])
def test_commit_hash_must_be_complete_canonical_sha256(raw, bad_hash):
    raw["mgis"]["steps"][0]["nominal_after_update_sha256"] = bad_hash
    with pytest.raises(ValueError, match="Nominal committed hash"):
        ref.assess(ref.canonical_settings(), raw)


def test_validly_formatted_commit_hash_mismatch_keeps_metrics_invalid(raw):
    raw["mgis"]["steps"][-1]["nominal_after_update_sha256"] = "b" * 64
    failed_state_verdict(raw)


@pytest.mark.parametrize("field", PHYSICAL_BUFFERS)
@pytest.mark.parametrize("side", ["s0", "s1", "both"])
def test_rehashed_commit_cannot_change_physical_energy_isv_property_or_temperature(raw, field, side):
    step = raw["mgis"]["steps"][2]
    for name in ("s0", "s1") if side == "both" else (side,):
        alter_buffer(step["nominal_after_update"][name], field)
    step["nominal_after_update_sha256"] = ref.state_hash(step["nominal_after_update"])
    verdict = failed_state_verdict(raw)
    assert next(c for c in verdict["checks"] if c["code"] == "analytical_tangent_relative_error")["status"] == "PASS"


def test_rehashed_commit_cannot_change_dt(raw):
    step = raw["mgis"]["steps"][-1]
    step["nominal_after_update"]["dt_s"] += .1
    step["nominal_after_update_sha256"] = ref.state_hash(step["nominal_after_update"])
    failed_state_verdict(raw)


@pytest.mark.parametrize("row,column", [(0, 0), (0, 5), (3, 4), (5, 0), (5, 5)])
def test_committed_cache_requires_exact_zero_despite_rehash_or_negligible_float(raw, row, column):
    step = raw["mgis"]["steps"][-1]
    step["nominal_after_update"]["tangent_cache_kelvin_mpa"][row][column] = math.nextafter(0., 1.)
    step["nominal_after_update_sha256"] = ref.state_hash(step["nominal_after_update"])
    failed_state_verdict(raw)


@pytest.mark.parametrize("mutation", [
    lambda s: s["metadata"].update(isv_stride=5),
    lambda s: s["metadata"].update(computes_dissipated_energy=False),
    lambda s: s["s1"]["shapes"].update(internal_state_variables=[6]),
    lambda s: s["s0"].update(internal_state_variables=[1.] * 5),
    lambda s: s["s1"].update(dissipated_energies=[]),
    lambda s: s["s1"]["material_properties"].pop("RelaxationTime"),
    lambda s: s["s0"]["external_state_variables"].update(Temperature=[True]),
    lambda s: s["tangent_cache_kelvin_mpa"][1].__setitem__(3, math.nan),
])
def test_malformed_commit_metadata_buffer_or_nonfinite_cache_rejects(raw, mutation):
    mutation(raw["mgis"]["steps"][0]["nominal_after_update"])
    with pytest.raises(ValueError):
        ref.assess(ref.canonical_settings(), raw)


@pytest.mark.parametrize("field", (*PHYSICAL_BUFFERS, "shapes"))
def test_equal_committed_buffers_must_be_independent_snapshots(raw, field):
    step = raw["mgis"]["steps"][0]
    step["nominal_after_update"]["s0"][field] = step["nominal_after_probes"]["s1"][field]
    assert step["nominal_after_update_sha256"] == ref.state_hash(step["nominal_after_update"])
    failed_state_verdict(raw)


@pytest.mark.parametrize("alias", ["states", "rows", "metadata", "next", "probe"])
def test_equal_rehashed_snapshots_and_cache_rows_cannot_alias(raw, alias):
    step, following = raw["mgis"]["steps"][:2]
    committed = step["nominal_after_update"]
    if alias == "states":
        committed["s0"] = committed["s1"]
    elif alias == "rows":
        committed["tangent_cache_kelvin_mpa"][5] = committed["tangent_cache_kelvin_mpa"][0]
    elif alias == "metadata":
        committed["metadata"] = step["nominal_after_probes"]["metadata"]
    elif alias == "next":
        # Preserve the declared second dt while aliasing a committed s1 buffer.
        following["initial_manager"]["s0"] = committed["s1"]
        following["initial_state_sha256"] = ref.state_hash(following["initial_manager"])
    else:
        probe = following["finite_differences"][1]["probes"][11]
        probe["initial_manager"] = following["initial_manager"]
    assert step["nominal_after_update_sha256"] == ref.state_hash(committed)
    failed_state_verdict(raw)


@pytest.mark.parametrize("field", PHYSICAL_BUFFERS)
def test_next_nominal_and_all_probe_baselines_cannot_advance_rehashed_changed_state(raw, field):
    step = raw["mgis"]["steps"][1]
    for side in ("s0", "s1"):
        alter_buffer(step["initial_manager"][side], field)
    for fd in step["finite_differences"]:
        for probe in fd["probes"]:
            probe["initial_manager"] = deepcopy(step["initial_manager"])
    rehash_step(step)
    failed_state_verdict(raw)


def test_next_nominal_and_all_probe_baselines_cannot_restore_prior_preupdate_tangent(raw):
    first, step = raw["mgis"]["steps"][:2]
    step["initial_manager"]["tangent_cache_kelvin_mpa"] = deepcopy(first["nominal_after_probes"]["tangent_cache_kelvin_mpa"])
    for fd in step["finite_differences"]:
        for probe in fd["probes"]:
            probe["initial_manager"] = deepcopy(step["initial_manager"])
    rehash_step(step)
    verdict = failed_state_verdict(raw)
    assert next(c for c in verdict["checks"] if c["code"] == "analytical_tangent_relative_error")["status"] == "PASS"


def test_equal_nonzero_owned_native_buffers_and_saved_snapshots_are_independent(raw):
    baseline = raw["mgis"]["steps"][2]["nominal_after_update"]
    baseline_hash = ref.state_hash(baseline)
    assert all(x != 0. for x in baseline["s0"]["internal_state_variables"])
    behaviour = SimpleNamespace(computesStoredEnergy=True, computesDissipatedEnergy=True)
    settings = ref.canonical_settings()
    props = dict(zip(worker.PROPERTY_NAMES, settings["material"].values()))
    handles = [worker.clone_manager(FakeBinding, behaviour, np, props, settings["temperature_k"], baseline) for _ in range(2)]
    buffers = []
    for handle in handles:
        assert worker.snapshot_manager(handle, baseline["dt_s"]) == baseline
        buffers.append(handle.manager.K)
        for side in ("s0", "s1"):
            state = getattr(handle.manager, side)
            buffers.extend(getattr(state, name) for name in worker.ARRAYS)
            buffers.extend(handle.property_buffers[side].values())
            buffers.extend(handle.external_buffers[side].values())
            assert all(state.properties[k] is handle.property_buffers[side][k] for k in props)
            assert state.external["Temperature"] is handle.external_buffers[side]["Temperature"]
    assert len(buffers) == 46
    assert not any(np.shares_memory(a, b) for i, a in enumerate(buffers) for b in buffers[i + 1:])
    saved = worker.snapshot_manager(handles[1], baseline["dt_s"])
    for array in buffers[:23]:
        array.reshape(-1)[0] += .25
    assert worker.snapshot_manager(handles[1], baseline["dt_s"]) == saved == baseline
    assert ref.state_hash(baseline) == baseline_hash
    handles[1].manager.s1.internal_state_variables[0, 0] += 3.
    assert saved == baseline and ref.state_hash(baseline) == baseline_hash


def test_worker_rejects_native_s0_s1_buffer_aliases_before_integration():
    class AliasedManager(FakeManager):
        def __init__(self, behaviour, count):
            super().__init__(behaviour, count)
            self.s1.internal_state_variables = self.s0.internal_state_variables
    class AliasedBinding(FakeBinding):
        MaterialDataManager = AliasedManager
    behaviour = SimpleNamespace(computesStoredEnergy=True, computesDissipatedEnergy=True)
    props = dict(zip(worker.PROPERTY_NAMES, ref.canonical_settings()["material"].values()))
    with pytest.raises(ValueError, match="Independent owned native"):
        worker.clone_manager(AliasedBinding, behaviour, np, props, 293.15)


def test_fake_update_zeroes_cache_before_full_buffer_copy():
    manager = FakeManager(None, 1)
    manager.K[:] = 2.
    for i, name in enumerate(worker.ARRAYS, 1):
        getattr(manager.s1, name)[:] = i
    manager.s0.properties = {k: np.array([0.]) for k in worker.PROPERTY_NAMES}
    manager.s1.properties = {k: np.array([float(i)]) for i, k in enumerate(worker.PROPERTY_NAMES, 1)}
    manager.s0.external, manager.s1.external = {"Temperature": np.array([0.])}, {"Temperature": np.array([293.15])}
    original = manager.s0.gradients
    class CopyOrderCheck:
        def __setitem__(self, key, value):
            assert np.array_equal(manager.K, np.zeros((1, 6, 6)))
            original[key] = value
    manager.s0.gradients = CopyOrderCheck()
    FakeBinding.update(manager)
    manager.s0.gradients = original
    for name in worker.ARRAYS:
        assert np.array_equal(getattr(manager.s0, name), getattr(manager.s1, name))
        assert not np.shares_memory(getattr(manager.s0, name), getattr(manager.s1, name))
    assert all(np.array_equal(manager.s0.properties[k], manager.s1.properties[k]) for k in worker.PROPERTY_NAMES)
    assert np.array_equal(manager.s0.external["Temperature"], manager.s1.external["Temperature"])


def test_old_masking_fake_without_cache_reset_is_refused_and_actual_bad_commit_saved(tmp_path):
    class OldMaskingBinding(FakeBinding):
        @staticmethod
        def update(manager):
            for name in worker.ARRAYS:
                getattr(manager.s0, name)[:] = getattr(manager.s1, name)
    settings = ref.canonical_settings()
    behaviour = SimpleNamespace(computesStoredEnergy=True, computesDissipatedEnergy=True)
    transport = FakeTransport()
    with pytest.raises(ValueError, match="Native commit did not advance"):
        worker.integrate_history(OldMaskingBinding, behaviour, settings, LIBRARY_SHA, tmp_path, np, transport)
    assert transport.calls == 37
    saved = json.loads((tmp_path / "mgis.partial.json").read_text(encoding="utf-8"))
    step = saved["steps"][0]
    assert step["nominal_after_update_sha256"] == ref.state_hash(step["nominal_after_update"])
    assert step["nominal_after_update"]["tangent_cache_kelvin_mpa"] == step["tangent_kelvin_mpa"]
    assert any(x != 0. for row in step["nominal_after_update"]["tangent_cache_kelvin_mpa"] for x in row)


@pytest.mark.parametrize("field", PHYSICAL_BUFFERS)
def test_worker_saves_actual_rehashed_corrupt_full_commit_and_refuses_it(tmp_path, field):
    class CorruptBinding(FakeBinding):
        @staticmethod
        def update(manager):
            FakeBinding.update(manager)
            for side in ("s0", "s1"):
                state = getattr(manager, side)
                if field == "material_properties":
                    state.properties["RelaxationTime"][0] += .1
                elif field == "external_state_variables":
                    state.external["Temperature"][0] += .1
                else:
                    native = next(name for name, saved in worker.ARRAYS.items() if saved == field)
                    getattr(state, native).reshape(-1)[-1] += .1
    settings = ref.canonical_settings()
    behaviour = SimpleNamespace(computesStoredEnergy=True, computesDissipatedEnergy=True)
    with pytest.raises(ValueError, match="Native commit did not advance"):
        worker.integrate_history(CorruptBinding, behaviour, settings, LIBRARY_SHA, tmp_path, np, FakeTransport())
    saved = json.loads((tmp_path / "mgis.partial.json").read_text(encoding="utf-8"))
    step = saved["steps"][0]
    assert step["nominal_after_update_sha256"] == ref.state_hash(step["nominal_after_update"])
    assert step["nominal_after_update"]["s0"] == step["nominal_after_update"]["s1"]
    assert step["nominal_after_update"]["s1"] != step["nominal_after_probes"]["s1"]


@pytest.mark.parametrize("phase", ["nominal", "finite_difference"])
def test_unreliable_integrations_never_invent_a_successful_commit(tmp_path, phase):
    class UnreliableTransport(FakeTransport):
        def _integrate(self, binding, manager, dt):
            result = super()._integrate(binding, manager, dt)
            if self.calls == (1 if phase == "nominal" else 2):
                result["integration_return"] = 0
            return result
    settings = ref.canonical_settings()
    behaviour = SimpleNamespace(computesStoredEnergy=True, computesDissipatedEnergy=True)
    transport = UnreliableTransport()
    mgis = worker.integrate_history(FakeBinding, behaviour, settings, LIBRARY_SHA, tmp_path, np, transport)
    assert mgis["native_rejection"]["phase"] == phase
    assert transport.calls == (1 if phase == "nominal" else 2)
    assert "nominal_after_update" not in mgis["steps"][0]
    assert "nominal_after_update_sha256" not in mgis["steps"][0]
    assert json.loads((tmp_path / "mgis.partial.json").read_text(encoding="utf-8")) == mgis
