"""Cold SVK math/record checks; all native-looking records here are SYNTHETIC.

The oracle differentiates a scalar Green-strain energy with a small, independent
second-order dual-number evaluator. It does not call the Domain stress/Hessian
formula to populate observations, tangents or either sign of a probe.
"""

from copy import deepcopy
import hashlib
import json
import math

import pytest

from plugins.hyperelastic import reference as domain


PAIRS = ((0, 0), (1, 1), (2, 2), (0, 1), (1, 0), (0, 2), (2, 0), (1, 2), (2, 1))
SYM = ((0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2))
I9 = [1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


class Jet:
    """Second derivatives via product rule, independently of constitutive A."""

    def __init__(self, value, gradient=None, hessian=None):
        self.value = float(value)
        self.gradient = gradient if gradient is not None else [0.0] * 9
        self.hessian = hessian if hessian is not None else [[0.0] * 9 for _ in range(9)]

    @staticmethod
    def variable(value, index):
        gradient = [0.0] * 9
        gradient[index] = 1.0
        return Jet(value, gradient)

    def __add__(self, other):
        other = other if isinstance(other, Jet) else Jet(other)
        return Jet(self.value + other.value,
            [a + b for a, b in zip(self.gradient, other.gradient)],
            [[self.hessian[i][j] + other.hessian[i][j] for j in range(9)] for i in range(9)])

    __radd__ = __add__

    def __mul__(self, other):
        other = other if isinstance(other, Jet) else Jet(other)
        return Jet(self.value * other.value,
            [a * other.value + self.value * b for a, b in zip(self.gradient, other.gradient)],
            [[self.hessian[i][j] * other.value + self.value * other.hessian[i][j] +
                self.gradient[i] * other.gradient[j] + other.gradient[i] * self.gradient[j]
                for j in range(9)] for i in range(9)])

    __rmul__ = __mul__


def energy_oracle(f9, material):
    f = [[None] * 3 for _ in range(3)]
    for index, (i, j) in enumerate(PAIRS):
        f[i][j] = Jet.variable(f9[index], index)
    green = [[0.5 * (sum((f[k][i] * f[k][j] for k in range(3)), Jet(0.0)) +
                      (-1.0 if i == j else 0.0)) for j in range(3)] for i in range(3)]
    trace = sum((green[i][i] for i in range(3)), Jet(0.0))
    e, nu = material["youngs_modulus_mpa"], material["poisson_ratio"]
    lam, mu = e * nu / ((1 + nu) * (1 - 2 * nu)), e / (2 * (1 + nu))
    return 0.5 * lam * trace * trace + mu * sum((g * g for row in green for g in row), Jet(0.0))


def oracle(f9, material):
    jet = energy_oracle(f9, material)
    f, p = [[0.0] * 3 for _ in range(3)], [[0.0] * 3 for _ in range(3)]
    for index, (i, j) in enumerate(PAIRS):
        f[i][j], p[i][j] = f9[index], jet.gradient[index]
    det = (f[0][0] * (f[1][1] * f[2][2] - f[1][2] * f[2][1]) -
           f[0][1] * (f[1][0] * f[2][2] - f[1][2] * f[2][0]) +
           f[0][2] * (f[1][0] * f[2][1] - f[1][1] * f[2][0]))
    cauchy = [[sum(p[i][k] * f[j][k] for k in range(3)) / det for j in range(3)] for i in range(3)]
    return {"deformation_gradient": list(f9), "pk1_stress_mpa": jet.gradient,
        "cauchy_stress_mpa": [cauchy[i][j] for i, j in SYM],
        "pk1_tangent_mpa": jet.hessian, "stored_energy_density_mpa": jet.value}


def digest(state):
    return hashlib.sha256(json.dumps(state, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def snapshot(observation, settings, dt):
    return {"deformation_gradient": deepcopy(observation["deformation_gradient"]),
        "pk1_stress_mpa": deepcopy(observation["pk1_stress_mpa"]),
        "stored_energies": [observation["stored_energy_density_mpa"]],
        "internal_state_variables": [], "dissipated_energies": [],
        "material_properties": {"YoungModulus": settings["material"]["youngs_modulus_mpa"],
                                "PoissonRatio": settings["material"]["poisson_ratio"]},
        "external_state_variables": {"Temperature": settings["temperature_k"]},
        "manager_tangent_cache_mpa": deepcopy(observation["pk1_tangent_mpa"]), "dt_s": dt}


def synthetic_raw(settings):
    """A test double, never native acceptance: full separately copied snapshots."""
    initial_values = {"deformation_gradient": I9, "pk1_stress_mpa": [0.0] * 9,
        "stored_energy_density_mpa": 0.0, "pk1_tangent_mpa": [[0.0] * 9 for _ in range(9)]}
    previous = snapshot(initial_values, settings, 0.0)
    raw = {"test_evidence_kind": "SYNTHETIC_NOT_NATIVE", "library_sha256": "a" * 64,
        "initial": {"phase": "INITIAL_UNPREPARED", "time_s": 0.0, "deformation_gradient": list(I9),
                    "state": deepcopy(previous), "state_sha256": digest(previous)},
        "steps": [], "mtest": {"library_sha256": "a" * 64, "deformation_gradient_epsilon": 1e-14, "steps": []}}
    for index, entry in enumerate(settings["history"][1:], 1):
        dt = entry["time_s"] - settings["history"][index - 1]["time_s"]
        before = {**deepcopy(previous), "dt_s": dt}
        observation = oracle(entry["deformation_gradient"], settings["material"])
        nominal = snapshot(observation, settings, dt)
        # SYNTHETIC_NOT_NATIVE: model MGIS's documented post-update K reset.
        committed = deepcopy(nominal)
        committed["manager_tangent_cache_mpa"] = [[0.0] * 9 for _ in range(9)]
        step = {**deepcopy(observation), "phase": "INTEGRATED", "time_s": entry["time_s"], "dt_s": dt,
            "integration_return": 1, "initial_state": deepcopy(before), "initial_state_sha256": digest(before),
            "nominal_before_probes": deepcopy(nominal), "nominal_after_probes": deepcopy(nominal),
            "nominal_after_update": deepcopy(committed), "nominal_after_update_sha256": digest(committed), "finite_differences": []}
        for h in (1e-7, 1e-8, 1e-9):
            probes = []
            by_column = {}
            for column in range(9):
                for sign in (-1, 1):
                    f = list(entry["deformation_gradient"])
                    f[column] += sign * h
                    actual = oracle(f, settings["material"])
                    final_state = snapshot(actual, settings, dt)
                    probe = {"column": column, "sign": sign, "deformation_gradient": f,
                        "pk1_stress_mpa": deepcopy(actual["pk1_stress_mpa"]),
                        "stored_energy_density_mpa": actual["stored_energy_density_mpa"], "integration_return": 1,
                        "initial_state": deepcopy(before), "initial_state_sha256": digest(before),
                        "final_state": final_state, "final_state_sha256": digest(final_state)}
                    probes.append(probe)
                    by_column[column, sign] = probe
            step["finite_differences"].append({"h": h, "probes": probes,
                "pk1_tangent_mpa": [[(by_column[j, 1]["pk1_stress_mpa"][i] - by_column[j, -1]["pk1_stress_mpa"][i]) / (2 * h)
                    for j in range(9)] for i in range(9)],
                "energy_gradient_mpa": [(by_column[j, 1]["stored_energy_density_mpa"] - by_column[j, -1]["stored_energy_density_mpa"]) / (2 * h)
                    for j in range(9)]})
        raw["steps"].append(step)
        # SYNTHETIC_NOT_NATIVE: an iterative MTest solve may retain nonzero F
        # roundoff below its original fixed criterion. Actual stresses come from
        # this independent double's observed F; the Domain reference stays at
        # the exact prescribed history.
        observed_f = [value + (5e-16 if column % 2 == 0 else -5e-16)
                      for column, value in enumerate(entry["deformation_gradient"])]
        cauchy = oracle(observed_f, settings["material"])["cauchy_stress_mpa"]
        raw["mtest"]["steps"].append({"phase": "INTEGRATED", "time_s": entry["time_s"], "dt_s": dt,
            "imposed_deformation_gradient": deepcopy(entry["deformation_gradient"]), "deformation_gradient": observed_f,
            "cauchy_stress_kelvin_mpa": cauchy[:3] + [math.sqrt(2) * x for x in cauchy[3:]], "integration_return": 1})
        previous = deepcopy(committed)
    return raw


@pytest.fixture(scope="module")
def cold_observations():
    settings = domain.canonical_settings()
    return settings, synthetic_raw(settings)


def test_declared_nine_component_order_and_no_kelvin_coercion():
    assert domain.F_COMPONENTS == ("xx", "yy", "zz", "xy", "yx", "xz", "zx", "yz", "zy")
    original = [1.001, .999, 1.0005, .0002, -.0004, .0003, -.0006, .0007, -.0008]
    assert domain.to_matrix(original) == [[1.001, .0002, .0003], [-.0004, .999, .0007], [-.0006, -.0008, 1.0005]]
    assert domain.from_matrix(domain.to_matrix(original)) == original
    with pytest.raises(ValueError):
        domain.to_matrix([0.0] * 6)
    with pytest.raises(ValueError):
        domain.to_kelvin(original)


def test_kelvin_conversion_only_for_symmetric_cauchy():
    physical = [10.0, 20.0, 30.0, -2.0, 3.0, -4.0]
    converted = domain.to_kelvin(physical)
    assert converted[:3] == physical[:3]
    assert converted[3:] == pytest.approx([-2 * math.sqrt(2), 3 * math.sqrt(2), -4 * math.sqrt(2)])
    assert domain.from_kelvin(converted) == pytest.approx(physical)


def test_default_history_exact_values_and_deep_independent_copies():
    first, second = domain.canonical_settings(), domain.canonical_settings()
    assert len(first["history"]) == 12
    assert [entry["time_s"] for entry in first["history"]] == list(range(12))
    assert first["history"][0]["deformation_gradient"] == first["history"][1]["deformation_gradient"] == I9
    assert first["history"][4]["deformation_gradient"][3] == .0006
    assert first["history"][5]["deformation_gradient"][4] == -.0004
    assert first["history"][6]["deformation_gradient"] == [1.001, .9995, 1.0007, .0004, .00015, -.0002, .00025, .0003, -.00035]
    assert first["history"][9]["deformation_gradient"] == first["history"][6]["deformation_gradient"]
    first["history"][0]["deformation_gradient"][0] = 5.0
    first["limits"]["finite_difference_steps"][0] = 5.0
    assert second == domain.canonical_settings()


def test_exact_identity_has_actual_nonzero_hessian_but_zero_energy_stress():
    result = domain.response(I9, {"youngs_modulus_mpa": 200.0, "poisson_ratio": .25})
    assert result["pk1_stress_mpa"] == [0.0] * 9
    assert result["stored_energy_density_mpa"] == 0.0
    a = result["pk1_tangent_mpa"]
    assert a[0][0] == 240.0 and a[0][1] == 80.0
    assert a[3][3] == a[3][4] == a[4][3] == a[4][4] == 80.0
    assert a[5][5] == a[5][6] == a[7][8] == 80.0


def test_uniaxial_closed_form_p_energy_tangent_and_cauchy_measure():
    a, e, nu = 1.001, 200.0, .25
    green = (a * a - 1) / 2
    result = domain.response([a, 1, 1, 0, 0, 0, 0, 0, 0], {"youngs_modulus_mpa": e, "poisson_ratio": nu})
    assert result["stored_energy_density_mpa"] == pytest.approx(120 * green * green, rel=1e-14)
    assert result["pk1_stress_mpa"][:3] == pytest.approx([a * 240 * green, 80 * green, 80 * green])
    assert result["cauchy_stress_mpa"][:3] == pytest.approx([a * 240 * green, 80 * green / a, 80 * green / a])
    assert result["pk1_tangent_mpa"][0][0] == pytest.approx(240 * green + 240 * a * a)
    # Current-volume or mass energy would fail the declared reference measure.
    assert result["stored_energy_density_mpa"] != pytest.approx(120 * green * green / a, rel=1e-6)


@pytest.mark.parametrize("history_index", list(range(1, 12)))
def test_full_hessian_and_pk1_are_independent_scalar_energy_derivatives(history_index):
    settings = domain.canonical_settings()
    f = settings["history"][history_index]["deformation_gradient"]
    actual = domain.response(f, settings["material"])
    independent = energy_oracle(f, settings["material"])
    # Independent ordinary additions and compensated positive-energy sums have
    # distinct IEEE rounding (~4e-14 MPa here). This cold oracle bound is still
    # 100x tighter than the frozen 1e-10 MPa numerical absolute-energy gate.
    assert actual["stored_energy_density_mpa"] == pytest.approx(independent.value, abs=1e-12, rel=1e-12)
    assert actual["pk1_stress_mpa"] == pytest.approx(independent.gradient, abs=8e-11, rel=2e-12)
    for row, expected in zip(actual["pk1_tangent_mpa"], independent.hessian):
        assert row == pytest.approx(expected, abs=2e-9, rel=2e-13)
    for i in range(9):
        for j in range(9):
            assert actual["pk1_tangent_mpa"][i][j] == pytest.approx(actual["pk1_tangent_mpa"][j][i], abs=1e-9)


@pytest.mark.parametrize("h", [1e-7, 1e-8, 1e-9])
def test_all_nine_energy_gradient_and_hessian_fd_columns_with_independent_oracle(h):
    settings = domain.canonical_settings()
    f = settings["history"][8]["deformation_gradient"]
    actual = domain.response(f, settings["material"])
    reference = domain.analytical_reference(settings)
    for column in range(9):
        plus, minus = list(f), list(f)
        plus[column] += h
        minus[column] -= h
        a, b = energy_oracle(plus, settings["material"]), energy_oracle(minus, settings["material"])
        gradient = (a.value - b.value) / (2 * h)
        assert abs(gradient - actual["pk1_stress_mpa"][column]) <= 1e-6 * reference["scales"]["stress_mpa"]
        for row in range(9):
            fd = (a.gradient[row] - b.gradient[row]) / (2 * h)
            assert abs(fd - actual["pk1_tangent_mpa"][row][column]) <= 1e-6 * reference["scales"]["tangent_mpa"]


@pytest.mark.parametrize("material", [
    {"youngs_modulus_mpa": 100.0, "poisson_ratio": 0.0},
    {"youngs_modulus_mpa": 70000.0, "poisson_ratio": .2},
    {"youngs_modulus_mpa": 120000.0, "poisson_ratio": -.5},
])
def test_reference_tracks_changed_material_and_matches_hessian(material):
    settings = domain.canonical_settings()
    settings["material"] = material
    ref = domain.analytical_reference(settings)
    expected = oracle(settings["history"][6]["deformation_gradient"], material)
    assert ref["states"][6]["pk1_stress_mpa"] == pytest.approx(expected["pk1_stress_mpa"], abs=1e-10)
    assert ref["states"][6]["stored_energy_density_mpa"] == pytest.approx(expected["stored_energy_density_mpa"])
    for row, other in zip(ref["states"][6]["pk1_tangent_mpa"], expected["pk1_tangent_mpa"]):
        assert row == pytest.approx(other, abs=1e-9)


def test_negative_poisson_energy_positive_and_stable_near_minus_one():
    material = {"youngs_modulus_mpa": 100.0, "poisson_ratio": -.999999}
    dilation = [1.001, 1.001, 1.001, 0, 0, 0, 0, 0, 0]
    observed = domain.response(dilation, material)
    green = (.001 * 2 + .001 ** 2) / 2
    bulk = 100 / (3 * (1 - 2 * material["poisson_ratio"]))
    assert observed["stored_energy_density_mpa"] == pytest.approx(.5 * bulk * (3 * green) ** 2, rel=1e-12)
    assert observed["stored_energy_density_mpa"] > 0


def test_changed_prescribed_f_and_time_reference_no_rate_temperature_law():
    settings = domain.canonical_settings()
    settings["history"][2]["deformation_gradient"][0] = 1.002
    settings["temperature_k"] = 350.0
    settings["history"] = [{**entry, "time_s": 2 * entry["time_s"]} for entry in settings["history"]]
    ref = domain.analytical_reference(settings)
    assert ref["states"][2]["time_s"] == 4
    assert ref["states"][2]["stored_energy_density_mpa"] > domain.analytical_reference(domain.canonical_settings())["states"][2]["stored_energy_density_mpa"]
    same_f = deepcopy(settings)
    same_f["temperature_k"] = 280.0
    assert domain.analytical_reference(same_f)["states"][2]["pk1_stress_mpa"] == ref["states"][2]["pk1_stress_mpa"]


def test_proper_rotation_nonzero_hessian_and_zero_stress_energy():
    angle = .7
    c, s = math.cos(angle), math.sin(angle)
    f = [c, c, 1, -s, s, 0, 0, 0, 0]
    result = domain.response(f, domain.canonical_settings()["material"])
    assert max(abs(x) for x in result["pk1_stress_mpa"]) < 1e-10
    assert result["stored_energy_density_mpa"] < 1e-20
    assert max(abs(x) for row in result["pk1_tangent_mpa"] for x in row) > 1e5


def test_model_declaration_is_solver_independent_and_editing_it_does_not_edit_settings():
    settings = domain.canonical_settings()
    before = deepcopy(settings)
    declared = domain.model_declaration(settings)
    assert declared["model"]["geometry"] is None and declared["model"]["mesh"] is None
    assert declared["model"]["materials"][0]["qualified"] is False
    assert declared["outputs"]["fields"][0]["components"] == list(domain.F_COMPONENTS)
    assert declared["outputs"]["history"][0]["measure"] == "per_reference_volume"
    assert not any(word in json.dumps(declared) for word in ("mfront", "MGIS", "MTest", "docker", "native_path"))
    declared["loads"][0]["history"][0]["deformation_gradient"][0] = -100
    assert settings == before


BAD_SETTINGS = [
    ("unknown_setting", lambda s: s.update(backend="bad")),
    ("wrong_case", lambda s: s.update(case="neo_hookean")),
    ("missing_material", lambda s: s.pop("material")),
    ("material_extra", lambda s: s["material"].update(density=1)),
    ("E_zero", lambda s: s["material"].update(youngs_modulus_mpa=0)),
    ("E_negative", lambda s: s["material"].update(youngs_modulus_mpa=-1)),
    ("E_limit", lambda s: s["material"].update(youngs_modulus_mpa=1e9 + 1)),
    ("E_bool", lambda s: s["material"].update(youngs_modulus_mpa=True)),
    ("E_underflow", lambda s: s["material"].update(youngs_modulus_mpa=5e-324)),
    ("E_inf", lambda s: s["material"].update(youngs_modulus_mpa=math.inf)),
    ("nu_half", lambda s: s["material"].update(poisson_ratio=.5)),
    ("nu_minus_one", lambda s: s["material"].update(poisson_ratio=-1)),
    ("nu_nan", lambda s: s["material"].update(poisson_ratio=math.nan)),
    ("temperature_zero", lambda s: s.update(temperature_k=0)),
    ("temperature_limit", lambda s: s.update(temperature_k=5000.1)),
    ("temperature_bool", lambda s: s.update(temperature_k=True)),
    ("history_tuple", lambda s: s.update(history=tuple(s["history"]))),
    ("history_short", lambda s: s.update(history=s["history"][:2])),
    ("history_many", lambda s: s.update(history=s["history"] * 3)),
    ("history_extra_key", lambda s: s["history"][2].update(load=1)),
    ("time_duplicate", lambda s: s["history"][2].update(time_s=1)),
    ("time_backwards", lambda s: s["history"][2].update(time_s=-1)),
    ("time_limit", lambda s: s["history"][-1].update(time_s=1e6 + 1)),
    ("time_bool", lambda s: s["history"][2].update(time_s=True)),
    ("initial_not_t0", lambda s: s["history"][0].update(time_s=.5)),
    ("initial_not_I", lambda s: s["history"][0]["deformation_gradient"].__setitem__(0, 1.001)),
    ("t1_not_identity", lambda s: s["history"][1]["deformation_gradient"].__setitem__(3, .0001)),
    ("F_six", lambda s: s["history"][2].update(deformation_gradient=[0] * 6)),
    ("F_bool", lambda s: s["history"][2]["deformation_gradient"].__setitem__(3, True)),
    ("F_nonfinite", lambda s: s["history"][2]["deformation_gradient"].__setitem__(3, math.inf)),
    ("F_component_bound", lambda s: s["history"][2]["deformation_gradient"].__setitem__(0, 2.1)),
    ("J_negative", lambda s: s["history"][2].update(deformation_gradient=[-1, 1, 1, 0, 0, 0, 0, 0, 0])),
    ("J_zero", lambda s: s["history"][2].update(deformation_gradient=[0, 1, 1, 0, 0, 0, 0, 0, 0])),
    ("Green_limit", lambda s: s["history"][2].update(deformation_gradient=[1.03, 1, 1, 0, 0, 0, 0, 0, 0])),
    ("all_strain_zero", lambda s: s.update(history=[{"time_s": float(i), "deformation_gradient": list(I9)} for i in range(3)])),
    ("weaken_stress", lambda s: s["limits"].update(stress_relative=1e-7)),
    ("weaken_energy", lambda s: s["limits"].update(energy_relative=1e-7)),
    ("weaken_tangent", lambda s: s["limits"].update(tangent_relative=1e-7)),
    ("weaken_fd", lambda s: s["limits"].update(finite_difference_relative=1e-5)),
    ("fd_fewer", lambda s: s["limits"].update(finite_difference_steps=[1e-7, 1e-8])),
    ("fd_bool", lambda s: s["limits"].update(finite_difference_steps=[1e-7, 1e-8, True])),
    ("fd_changed", lambda s: s["limits"].update(finite_difference_steps=[1e-7, 1e-8, 1e-10])),
    ("limits_extra", lambda s: s["limits"].update(energy_scale=1)),
]


@pytest.mark.parametrize("label,mutate", BAD_SETTINGS, ids=[name for name, _ in BAD_SETTINGS])
def test_settings_refuse_invalid_before_model_export(label, mutate):
    settings = domain.canonical_settings()
    mutate(settings)
    with pytest.raises(ValueError):
        domain.validate_settings(settings)
    with pytest.raises(ValueError):
        domain.model_declaration(settings)


def test_admitted_endpoint_but_fixed_plus_probe_outside_green_bound_is_refused():
    settings = domain.canonical_settings()
    settings["history"][2]["deformation_gradient"][0] = math.sqrt(1.04 - 1e-8)
    # Nominal itself has G<.02; h=1e-7 plus perturbation crosses .02.
    domain.response(settings["history"][2]["deformation_gradient"], settings["material"])
    with pytest.raises(ValueError, match="Green strain"):
        domain.validate_settings(settings)


def test_admission_copy_and_exposed_limits_cannot_change_frozen_internal_limits():
    settings = domain.canonical_settings()
    checked = domain.validate_settings(settings)
    checked["material"]["youngs_modulus_mpa"] = 1.0
    checked["history"][6]["deformation_gradient"][0] = 1.0
    checked["limits"]["finite_difference_steps"][0] = 1.0
    assert settings == domain.canonical_settings()
    old = domain.FIXED_LIMITS["finite_difference_steps"][0]
    try:
        domain.FIXED_LIMITS["finite_difference_steps"][0] = 1.0
        assert domain.validate_settings(settings)["limits"]["finite_difference_steps"][0] == old
    finally:
        domain.FIXED_LIMITS["finite_difference_steps"][0] = old


def check_map(outcome):
    return {item["code"]: item for item in outcome["checks"]}


def test_full_synthetic_history_all_fd_sizes_objectivity_recovery_unknown_release(cold_observations):
    settings, raw = cold_observations
    outcome = domain.assess(settings, raw)
    assert outcome["numerical_status"] == "PASS" and outcome["passed"] is True
    assert outcome["release_status"] == "NOT_RELEASED"
    assert all(row["status"] == "UNKNOWN" and row["blocking"] for row in outcome["pending"])
    assert len(outcome["endpoint_errors"]) == 11
    assert len(outcome["probe_errors"]) == 11 * 3 * 18
    assert [entry["h"] for entry in outcome["finite_difference_errors"]] == [1e-7, 1e-8, 1e-9]
    for h in ("1e-07", "1e-08", "1e-09"):
        assert check_map(outcome)["fd_tangent_vs_native_" + h]["status"] == "PASS"
        assert check_map(outcome)["fd_tangent_vs_reference_" + h]["status"] == "PASS"
        assert check_map(outcome)["fd_energy_gradient_vs_native_" + h]["status"] == "PASS"
        assert check_map(outcome)["fd_energy_gradient_vs_reference_" + h]["status"] == "PASS"
    assert check_map(outcome)["spatial_objectivity"]["status"] == "PASS"
    assert check_map(outcome)["path_recovery"]["status"] == "PASS"
    assert any(pair["first_history_index"] == 6 and pair["second_history_index"] == 8 for pair in outcome["pair_observations"]["spatial_objectivity"]["pairs"])
    assert outcome["native_observations"]["unprepared_initial_excluded"] is True
    assert outcome["native_observations"]["actual_endpoint_count"] == 11
    assert outcome["native_observations"]["native_dissipated_energy"] == outcome["native_observations"]["mtest_energy"] == "UNKNOWN"


def test_noncanonical_history_does_not_invent_missing_objectivity_or_recovery(cold_observations):
    full_settings, full_raw = cold_observations
    settings = deepcopy(full_settings)
    settings["history"] = settings["history"][:3]
    raw = deepcopy(full_raw)
    raw["steps"] = raw["steps"][:2]
    raw["mtest"]["steps"] = raw["mtest"]["steps"][:2]
    outcome = domain.assess(settings, raw)
    assert outcome["numerical_status"] == "UNKNOWN" and outcome["passed"] is False
    assert check_map(outcome)["spatial_objectivity"]["status"] == "UNKNOWN"
    assert check_map(outcome)["path_recovery"]["status"] == "UNKNOWN"
    assert outcome["release_status"] == "NOT_RELEASED"


def rehash_initial(raw):
    raw["initial"]["state_sha256"] = digest(raw["initial"]["state"])


def rehash_step(step):
    step["initial_state_sha256"] = digest(step["initial_state"])
    for fd in step["finite_differences"]:
        for probe in fd["probes"]:
            probe["initial_state_sha256"] = digest(probe["initial_state"])
            probe["final_state_sha256"] = digest(probe["final_state"])


TAMPERS = [
    ("wrong_library", "same_library", lambda r: r["mtest"].update(library_sha256="b" * 64)),
    ("initial_native_phase", "native_history", lambda r: r["initial"].update(phase="INTEGRATED")),
    ("initial_time", "native_history", lambda r: r["initial"].update(time_s=.1)),
    ("initial_hash", "snapshot_content", lambda r: r["initial"].update(state_sha256="b" * 64)),
    ("nominal_unreliable", "reliable_integrations", lambda r: r["steps"][3].update(integration_return=0)),
    ("nominal_refused", "reliable_integrations", lambda r: r["steps"][3].update(integration_return=-1)),
    ("mtest_unreliable", "reliable_integrations", lambda r: r["mtest"]["steps"][0].update(integration_return=0)),
    ("probe_refused", "reliable_integrations", lambda r: r["steps"][0]["finite_differences"][0]["probes"][0].update(integration_return=-1)),
    ("wrong_endpoint_time", "native_history", lambda r: r["steps"][1].update(time_s=99)),
    ("wrong_dt", "native_history", lambda r: r["steps"][1].update(dt_s=.5)),
    ("wrong_endpoint_F", "native_history", lambda r: r["steps"][1]["deformation_gradient"].__setitem__(0, 1.002)),
    ("mtest_wrong_phase", "native_history", lambda r: r["mtest"]["steps"][0].update(phase="INITIAL_UNPREPARED")),
    ("mtest_wrong_time", "native_history", lambda r: r["mtest"]["steps"][1].update(time_s=9)),
    ("mtest_wrong_dt", "native_history", lambda r: r["mtest"]["steps"][1].update(dt_s=0)),
    ("mtest_wrong_F", "native_history", lambda r: r["mtest"]["steps"][1]["deformation_gradient"].__setitem__(3, .0006)),
    ("baseline_hash", "snapshot_content", lambda r: r["steps"][1].update(initial_state_sha256="c" * 64)),
    ("baseline_energy", "immutable_probe_state", lambda r: r["steps"][1]["initial_state"]["stored_energies"].__setitem__(0, 1)),
    ("baseline_manager_cache", "immutable_probe_state", lambda r: r["steps"][1]["initial_state"]["manager_tangent_cache_mpa"][0].__setitem__(0, 1.0)),
    ("nominal_after_mutation", "immutable_probe_state", lambda r: r["steps"][2]["nominal_after_probes"]["pk1_stress_mpa"].__setitem__(0, 0)),
    ("probe_baseline_energy", "immutable_probe_state", lambda r: r["steps"][1]["finite_differences"][0]["probes"][0]["initial_state"]["stored_energies"].__setitem__(0, 2)),
    ("probe_baseline_dt", "immutable_probe_state", lambda r: r["steps"][1]["finite_differences"][0]["probes"][0]["initial_state"].update(dt_s=2)),
    ("probe_baseline_property", "snapshot_content", lambda r: r["steps"][1]["finite_differences"][0]["probes"][0]["initial_state"]["material_properties"].update(YoungModulus=1)),
    ("probe_baseline_temperature", "snapshot_content", lambda r: r["steps"][1]["finite_differences"][0]["probes"][0]["initial_state"]["external_state_variables"].update(Temperature=1)),
    ("probe_F", "probe_admission", lambda r: r["steps"][1]["finite_differences"][0]["probes"][0]["deformation_gradient"].__setitem__(0, 1.001)),
    ("probe_final_hash", "snapshot_content", lambda r: r["steps"][1]["finite_differences"][0]["probes"][0].update(final_state_sha256="b" * 64)),
    ("probe_final_energy", "snapshot_content", lambda r: r["steps"][1]["finite_differences"][0]["probes"][0]["final_state"]["stored_energies"].__setitem__(0, 3)),
    ("FD_summary_tangent", "fd_summary_integrity", lambda r: r["steps"][1]["finite_differences"][0]["pk1_tangent_mpa"][0].__setitem__(0, 0)),
    ("FD_summary_gradient", "fd_summary_integrity", lambda r: r["steps"][1]["finite_differences"][2]["energy_gradient_mpa"].__setitem__(0, 0)),
    ("zero_native_identity_tangent", "analytical_tangent_relative_error", lambda r: r["steps"][0].update(pk1_tangent_mpa=[[0.0] * 9 for _ in range(9)])),
    ("zero_offdiagonal_tangent_entry", "analytical_tangent_relative_error", lambda r: r["steps"][0]["pk1_tangent_mpa"][3].__setitem__(4, 0.0)),
    ("false_tangent_major_symmetry", "tangent_major_symmetry_relative_error", lambda r: r["steps"][1]["pk1_tangent_mpa"][0].__setitem__(3, 10)),
    ("PK1_wrong_sign", "pk1_stress_error", lambda r: r["steps"][1]["pk1_stress_mpa"].__setitem__(0, -r["steps"][1]["pk1_stress_mpa"][0])),
    ("Cauchy_wrong_sign", "cauchy_stress_error", lambda r: r["steps"][1]["cauchy_stress_mpa"].__setitem__(0, -r["steps"][1]["cauchy_stress_mpa"][0])),
    ("MTest_wrong_shear_Kelvin", "mtest_stress_error", lambda r: r["mtest"]["steps"][3]["cauchy_stress_kelvin_mpa"].__setitem__(3, r["mtest"]["steps"][3]["cauchy_stress_kelvin_mpa"][3] / math.sqrt(2))),
    ("MTest_native_agree_but_wrong", "mtest_stress_error", lambda r: r["mtest"]["steps"][2]["cauchy_stress_kelvin_mpa"].__setitem__(1, 1.0)),
    ("native_W_zero", "native_energy_density_error", lambda r: r["steps"][1].update(stored_energy_density_mpa=0)),
    ("native_W_current_volume", "native_energy_density_error", lambda r: r["steps"][1].update(stored_energy_density_mpa=r["steps"][1]["stored_energy_density_mpa"] / 1.001)),
    ("probe_W_bias", "probe_native_energy_density_error", lambda r: r["steps"][1]["finite_differences"][2]["probes"][0].update(stored_energy_density_mpa=0)),
    ("probe_P_bias", "probe_pk1_stress_error", lambda r: r["steps"][1]["finite_differences"][2]["probes"][0]["pk1_stress_mpa"].__setitem__(0, 0)),
]


@pytest.mark.parametrize("label,code,mutate", TAMPERS, ids=[name for name, _, _ in TAMPERS])
def test_retained_finite_tampering_is_failed_and_metrics_are_kept_invalid(cold_observations, label, code, mutate):
    settings, original = cold_observations
    raw = deepcopy(original)
    mutate(raw)
    outcome = domain.assess(settings, raw)
    assert check_map(outcome)[code]["status"] == "FAIL"
    assert outcome["numerical_status"] == "FAIL" and outcome["passed"] is False
    assert outcome["release_status"] == "NOT_RELEASED"
    assert outcome["metrics"] and all(metric["valid"] is False for metric in outcome["metrics"].values())
    assert all(math.isfinite(metric["value"]) for metric in outcome["metrics"].values())
    assert len(outcome["probe_errors"]) == 594


MALFORMED = [
    ("missing_native_W", lambda r: r["steps"][0].pop("stored_energy_density_mpa")),
    ("native_W_nonfinite", lambda r: r["steps"][0].update(stored_energy_density_mpa=math.nan)),
    ("native_P_short", lambda r: r["steps"][0].update(pk1_stress_mpa=[0] * 6)),
    ("native_P_nonfinite", lambda r: r["steps"][0]["pk1_stress_mpa"].__setitem__(0, math.inf)),
    ("native_F_six", lambda r: r["steps"][0].update(deformation_gradient=[0] * 6)),
    ("native_A_6x9", lambda r: r["steps"][0].update(pk1_tangent_mpa=[[0] * 9 for _ in range(6)])),
    ("native_A_badcolumn", lambda r: r["steps"][0]["pk1_tangent_mpa"][0].pop()),
    ("native_A_nonfinite", lambda r: r["steps"][0]["pk1_tangent_mpa"][0].__setitem__(0, math.nan)),
    ("missing_endpoint", lambda r: r["steps"].pop()),
    ("missing_mtest_endpoint", lambda r: r["mtest"]["steps"].pop()),
    ("MTest_Cauchy9", lambda r: r["mtest"]["steps"][0].update(cauchy_stress_kelvin_mpa=[0] * 9)),
    ("MTest_missing_return", lambda r: r["mtest"]["steps"][0].pop("integration_return")),
    ("return_bool", lambda r: r["steps"][0].update(integration_return=True)),
    ("return_float", lambda r: r["steps"][0].update(integration_return=1.0)),
    ("missing_h", lambda r: r["steps"][0]["finite_differences"].pop()),
    ("duplicate_h", lambda r: r["steps"][0]["finite_differences"][1].update(h=1e-7)),
    ("other_h", lambda r: r["steps"][0]["finite_differences"][1].update(h=1e-6)),
    ("missing_probe", lambda r: r["steps"][0]["finite_differences"][0]["probes"].pop()),
    ("duplicate_probe", lambda r: r["steps"][0]["finite_differences"][0]["probes"][1].update(sign=-1)),
    ("probe_col_limit", lambda r: r["steps"][0]["finite_differences"][0]["probes"][0].update(column=9)),
    ("probe_sign_bool", lambda r: r["steps"][0]["finite_differences"][0]["probes"][0].update(sign=True)),
    ("probe_column_bool", lambda r: r["steps"][0]["finite_differences"][0]["probes"][0].update(column=True)),
    ("probe_W_missing", lambda r: r["steps"][0]["finite_differences"][0]["probes"][0].pop("stored_energy_density_mpa")),
    ("probe_final_incomplete", lambda r: r["steps"][0]["finite_differences"][0]["probes"][0]["final_state"].pop("manager_tangent_cache_mpa")),
    ("snapshot_stored_absent", lambda r: r["initial"]["state"].update(stored_energies=[])),
    ("snapshot_ISV_invented", lambda r: r["initial"]["state"].update(internal_state_variables=[0])),
    ("snapshot_dissipation_invented", lambda r: r["initial"]["state"].update(dissipated_energies=[0])),
    ("snapshot_cache_6x6", lambda r: r["initial"]["state"].update(manager_tangent_cache_mpa=[[0] * 6 for _ in range(6)])),
    ("snapshot_property_missing", lambda r: r["initial"]["state"]["material_properties"].pop("YoungModulus")),
    ("snapshot_ESV_nonfinite", lambda r: r["initial"]["state"]["external_state_variables"].update(Temperature=math.inf)),
    ("bad_library_hash", lambda r: r.update(library_sha256="unknown")),
    ("bad_state_hash", lambda r: r["initial"].update(state_sha256="unknown")),
]


@pytest.mark.parametrize("label,mutate", MALFORMED, ids=[name for name, _ in MALFORMED])
def test_malformed_or_missing_actual_observation_is_not_replaced(cold_observations, label, mutate):
    settings, original = cold_observations
    raw = deepcopy(original)
    mutate(raw)
    with pytest.raises(ValueError):
        domain.assess(settings, raw)


def test_unprepared_nonzero_buffers_are_only_metadata_not_native_observations(cold_observations):
    settings, original = cold_observations
    raw = deepcopy(original)
    raw["initial"]["state"]["pk1_stress_mpa"] = [123.0] * 9
    raw["initial"]["state"]["stored_energies"] = [999.0]
    raw["initial"]["state"]["manager_tangent_cache_mpa"] = [[456.0] * 9 for _ in range(9)]
    rehash_initial(raw)
    # First independent baseline preserves these unprepared buffers. First t1
    # stress/W/K itself still comes from an independent actual-integration double.
    for key in ("pk1_stress_mpa", "stored_energies", "manager_tangent_cache_mpa"):
        raw["steps"][0]["initial_state"][key] = deepcopy(raw["initial"]["state"][key])
        for fd in raw["steps"][0]["finite_differences"]:
            for probe in fd["probes"]:
                probe["initial_state"][key] = deepcopy(raw["initial"]["state"][key])
    rehash_step(raw["steps"][0])
    outcome = domain.assess(settings, raw)
    assert outcome["numerical_status"] == "PASS"
    assert outcome["native_observations"]["stored_energy_density_mpa"][0] == 0
    assert outcome["native_observations"]["pk1_stress_mpa"][0] == [0] * 9


def test_nominal_and_probe_state_aliases_are_rejected_even_if_values_equal(cold_observations):
    settings, original = cold_observations
    for mode in ("nominal", "probe"):
        raw = deepcopy(original)
        step = raw["steps"][0]
        if mode == "nominal":
            step["nominal_after_probes"] = step["nominal_before_probes"]
        else:
            step["finite_differences"][0]["probes"][0]["initial_state"] = step["initial_state"]
        outcome = domain.assess(settings, raw)
        assert check_map(outcome)["immutable_probe_state"]["status"] == "FAIL"


@pytest.mark.parametrize("field", ["pk1_stress_mpa", "manager_tangent_cache_mpa", "material_properties", "external_state_variables"])
def test_shallow_copied_nested_state_buffers_fail_deep_clone_contract(cold_observations, field):
    settings, original = cold_observations
    raw = deepcopy(original)
    step = raw["steps"][0]
    probe = step["finite_differences"][0]["probes"][0]
    probe["initial_state"][field] = step["initial_state"][field]
    outcome = domain.assess(settings, raw)
    assert check_map(outcome)["immutable_probe_state"]["status"] == "FAIL"


def test_rehashing_a_changed_baseline_does_not_hide_path_or_probe_advance(cold_observations):
    settings, original = cold_observations
    raw = deepcopy(original)
    step = raw["steps"][4]
    step["initial_state"]["deformation_gradient"] = deepcopy(step["deformation_gradient"])
    for fd in step["finite_differences"]:
        for probe in fd["probes"]:
            probe["initial_state"] = deepcopy(step["initial_state"])
    rehash_step(step)
    outcome = domain.assess(settings, raw)
    assert check_map(outcome)["immutable_probe_state"]["status"] == "FAIL"


def test_every_fd_h_and_every_offdiagonal_column_contributes(cold_observations):
    settings, original = cold_observations
    for index, suffix in enumerate(("1e-07", "1e-08", "1e-09")):
        raw = deepcopy(original)
        fd = raw["steps"][7]["finite_differences"][index]
        probe = next(p for p in fd["probes"] if p["column"] == 8 and p["sign"] == 1)
        probe["pk1_stress_mpa"][4] += 1.0
        outcome = domain.assess(settings, raw)
        assert check_map(outcome)["fd_tangent_vs_native_" + suffix]["status"] == "FAIL"
        assert check_map(outcome)["fd_tangent_vs_reference_" + suffix]["status"] == "FAIL"
        assert outcome["finite_difference_errors"][index]["steps"][7]["tangent_vs_native_mpa"] > 0


def test_wrong_pk1_transpose_cannot_be_hidden_by_symmetric_cauchy(cold_observations):
    settings, original = cold_observations
    raw = deepcopy(original)
    p = raw["steps"][6]["pk1_stress_mpa"]
    p[3], p[4] = p[4], p[3]
    p[5], p[6] = p[6], p[5]
    p[7], p[8] = p[8], p[7]
    outcome = domain.assess(settings, raw)
    assert check_map(outcome)["pk1_stress_error"]["status"] == "FAIL"
    assert check_map(outcome)["native_tensor_measure"]["status"] == "FAIL"


def test_objectivity_full_spatial_hessian_rotation_and_recovery_are_native_checks(cold_observations):
    settings, original = cold_observations
    for index, code in ((7, "spatial_objectivity"), (8, "path_recovery")):
        raw = deepcopy(original)
        raw["steps"][index]["pk1_tangent_mpa"][8][4] += 10
        outcome = domain.assess(settings, raw)
        assert check_map(outcome)[code]["status"] == "FAIL"


def test_assess_does_not_mutate_inputs_and_output_native_arrays_are_independent(cold_observations):
    settings, original = cold_observations
    raw = deepcopy(original)
    before = digest(raw)
    settings_before = deepcopy(settings)
    outcome = domain.assess(settings, raw)
    assert digest(raw) == before and settings == settings_before
    outcome["native_observations"]["pk1_stress_mpa"][0][0] = 100
    assert raw["steps"][0]["pk1_stress_mpa"][0] == 0


def test_state_hash_is_canonical_and_refuses_nonfinite_and_non_json():
    assert domain.state_hash({"b": 1.0, "a": [2]}) == digest({"a": [2], "b": 1.0})
    for bad in ({"x": math.nan}, {"x": object()}, {"x": math.inf}):
        with pytest.raises(ValueError):
            domain.state_hash(bad)


def assert_retained_failure(outcome, code):
    assert check_map(outcome)[code]["status"] == "FAIL"
    assert outcome["numerical_status"] == "FAIL" and outcome["passed"] is False
    assert outcome["release_status"] == "NOT_RELEASED"
    assert len(outcome["metrics"]) == 21
    assert all(metric["valid"] is False and math.isfinite(metric["value"]) for metric in outcome["metrics"].values())
    assert all(row["status"] == "UNKNOWN" and row["blocking"] for row in outcome["pending"])


def test_committed_zero_cache_and_iterative_mtest_gradient_are_separate_evidence(cold_observations):
    settings, raw = cold_observations
    assert raw["test_evidence_kind"] == "SYNTHETIC_NOT_NATIVE"
    assert raw["mtest"]["deformation_gradient_epsilon"] == 1e-14
    assert any(actual != imposed for row in raw["mtest"]["steps"]
               for actual, imposed in zip(row["deformation_gradient"], row["imposed_deformation_gradient"]))
    for index, step in enumerate(raw["steps"]):
        committed = step["nominal_after_update"]
        after = step["nominal_after_probes"]
        assert step["nominal_after_update_sha256"] == digest(committed)
        assert any(value != 0.0 for row in after["manager_tangent_cache_mpa"] for value in row)
        assert all(value == 0.0 for row in committed["manager_tangent_cache_mpa"] for value in row)
        assert all(committed[key] == after[key] for key in after if key != "manager_tangent_cache_mpa")
        if index + 1 < len(raw["steps"]):
            baseline = raw["steps"][index + 1]["initial_state"]
            assert all(baseline[key] == committed[key] for key in committed if key != "dt_s")
    before = digest(raw)
    outcome = domain.assess(settings, raw)
    assert outcome["passed"] is True and outcome["numerical_status"] == "PASS"
    assert len(outcome["metrics"]) == 21
    assert outcome["reference"] == domain.analytical_reference(settings)
    assert digest(raw) == before
    check = check_map(outcome)["mtest_deformation_gradient_residual"]
    assert check["status"] == "PASS" and check["limit"] == 1e-14 and check["comparison"] == "strictly_less_than"
    assert check["component_order"] == list(domain.F_COMPONENTS)
    assert len(check["every_component_error"]) == 11
    assert 0 < check["observed"] < 1e-14
    assert len(outcome["mtest_gradient_residuals"]) == 11
    for index, row in enumerate(outcome["mtest_gradient_residuals"]):
        source = raw["mtest"]["steps"][index]
        assert row["history_index"] == index + 1 and row["time_s"] == source["time_s"]
        assert row["deformation_gradient"] == source["deformation_gradient"]
        assert row["imposed_deformation_gradient"] == settings["history"][index + 1]["deformation_gradient"]
        assert row["signed_residuals"] == [actual - imposed for actual, imposed in
                                         zip(source["deformation_gradient"], source["imposed_deformation_gradient"])]
        assert row["absolute_residuals"] == check["every_component_error"][index]
        assert len(row["absolute_residuals"]) == 9 and all(value < 1e-14 for value in row["absolute_residuals"])
    outcome["mtest_gradient_residuals"][0]["deformation_gradient"][0] = 99.0
    assert digest(raw) == before


def test_next_committed_baseline_allows_only_the_declared_nonuniform_dt_adjustment():
    settings = domain.canonical_settings()
    for index, entry in enumerate(settings["history"]):
        entry["time_s"] = float(index * index)
    raw = synthetic_raw(settings)
    assert raw["test_evidence_kind"] == "SYNTHETIC_NOT_NATIVE"
    assert [step["dt_s"] for step in raw["steps"]] == list(range(1, 22, 2))
    assert domain.assess(settings, raw)["passed"] is True


@pytest.mark.parametrize("missing", ["nominal_after_update", "nominal_after_update_sha256"])
def test_missing_actual_committed_evidence_is_never_reconstructed(cold_observations, missing):
    settings, original = cold_observations
    raw = deepcopy(original)
    raw["steps"][0].pop(missing)
    with pytest.raises(ValueError, match="missing required fields"):
        domain.assess(settings, raw)


@pytest.mark.parametrize("field", ["deformation_gradient", "pk1_stress_mpa", "stored_energies",
    "internal_state_variables", "dissipated_energies", "material_properties",
    "external_state_variables", "manager_tangent_cache_mpa", "dt_s"])
def test_committed_snapshot_requires_every_complete_field(cold_observations, field):
    settings, original = cold_observations
    raw = deepcopy(original)
    raw["steps"][0]["nominal_after_update"].pop(field)
    with pytest.raises(ValueError, match="Nominal committed snapshot"):
        domain.assess(settings, raw)


@pytest.mark.parametrize("bad_hash", ["b" * 64, "unknown"])
def test_committed_hash_is_bound_to_the_actual_full_snapshot(cold_observations, bad_hash):
    settings, original = cold_observations
    raw = deepcopy(original)
    raw["steps"][0]["nominal_after_update_sha256"] = bad_hash
    if len(bad_hash) != 64:
        with pytest.raises(ValueError, match="Nominal committed hash"):
            domain.assess(settings, raw)
    else:
        assert_retained_failure(domain.assess(settings, raw), "snapshot_content")


PHYSICAL_COMMITTED_FIELDS = ("deformation_gradient", "pk1_stress_mpa", "stored_energies",
                             "material_properties", "external_state_variables", "dt_s")


def change_physical_field(state, field):
    if isinstance(state[field], list):
        state[field][0] += .1
    elif isinstance(state[field], dict):
        key = next(iter(state[field]))
        state[field][key] += .1
    else:
        state[field] += .1


@pytest.mark.parametrize("field", PHYSICAL_COMMITTED_FIELDS)
def test_rehash_cannot_hide_a_changed_committed_physical_field_or_dt(cold_observations, field):
    settings, original = cold_observations
    raw = deepcopy(original)
    step = raw["steps"][4]
    change_physical_field(step["nominal_after_update"], field)
    step["nominal_after_update_sha256"] = digest(step["nominal_after_update"])
    assert_retained_failure(domain.assess(settings, raw), "immutable_probe_state")


@pytest.mark.parametrize("field", ["internal_state_variables", "dissipated_energies"])
def test_update_cannot_invent_absent_native_capabilities(cold_observations, field):
    settings, original = cold_observations
    raw = deepcopy(original)
    raw["steps"][0]["nominal_after_update"][field] = [0.0]
    with pytest.raises(ValueError):
        domain.assess(settings, raw)


@pytest.mark.parametrize("row,column", [(0, 0), (0, 8), (3, 4), (8, 0), (8, 8)])
def test_committed_cache_requires_exact_zero_even_for_the_smallest_nonzero_float(cold_observations, row, column):
    settings, original = cold_observations
    raw = deepcopy(original)
    step = raw["steps"][0]
    step["nominal_after_update"]["manager_tangent_cache_mpa"][row][column] = math.nextafter(0.0, 1.0)
    step["nominal_after_update_sha256"] = digest(step["nominal_after_update"])
    outcome = domain.assess(settings, raw)
    assert_retained_failure(outcome, "immutable_probe_state")
    assert check_map(outcome)["snapshot_content"]["status"] == "PASS"


@pytest.mark.parametrize("field", ["deformation_gradient", "pk1_stress_mpa", "stored_energies",
    "internal_state_variables", "dissipated_energies", "material_properties", "external_state_variables"])
def test_equal_committed_physical_buffers_must_still_be_independent(cold_observations, field):
    settings, original = cold_observations
    raw = deepcopy(original)
    step = raw["steps"][0]
    step["nominal_after_update"][field] = step["nominal_after_probes"][field]
    assert step["nominal_after_update_sha256"] == digest(step["nominal_after_update"])
    outcome = domain.assess(settings, raw)
    assert_retained_failure(outcome, "immutable_probe_state")
    assert check_map(outcome)["snapshot_content"]["status"] == "PASS"


def test_zero_committed_cache_rows_cannot_alias_each_other(cold_observations):
    settings, original = cold_observations
    raw = deepcopy(original)
    cache = raw["steps"][0]["nominal_after_update"]["manager_tangent_cache_mpa"]
    cache[8] = cache[0]
    assert_retained_failure(domain.assess(settings, raw), "immutable_probe_state")


def test_next_nominal_baseline_cannot_alias_equal_committed_snapshot(cold_observations):
    settings, original = cold_observations
    raw = deepcopy(original)
    raw["steps"][1]["initial_state"] = raw["steps"][0]["nominal_after_update"]
    assert_retained_failure(domain.assess(settings, raw), "immutable_probe_state")


@pytest.mark.parametrize("field", PHYSICAL_COMMITTED_FIELDS[:-1])
def test_next_nominal_and_probe_baselines_cannot_advance_a_rehashed_committed_physical_field(cold_observations, field):
    settings, original = cold_observations
    raw = deepcopy(original)
    step = raw["steps"][1]
    change_physical_field(step["initial_state"], field)
    for fd in step["finite_differences"]:
        for probe in fd["probes"]:
            probe["initial_state"] = deepcopy(step["initial_state"])
    rehash_step(step)
    assert_retained_failure(domain.assess(settings, raw), "immutable_probe_state")


def test_next_baseline_cannot_restore_the_preupdate_nominal_tangent(cold_observations):
    settings, original = cold_observations
    raw = deepcopy(original)
    step = raw["steps"][1]
    step["initial_state"]["manager_tangent_cache_mpa"] = deepcopy(raw["steps"][0]["nominal_after_probes"]["manager_tangent_cache_mpa"])
    for fd in step["finite_differences"]:
        for probe in fd["probes"]:
            probe["initial_state"] = deepcopy(step["initial_state"])
    rehash_step(step)
    outcome = domain.assess(settings, raw)
    assert_retained_failure(outcome, "immutable_probe_state")
    assert check_map(outcome)["snapshot_content"]["status"] == "PASS"
    assert check_map(outcome)["analytical_tangent_relative_error"]["status"] == "PASS"


@pytest.mark.parametrize("epsilon", [0.0, 1e-15, 1e-13, 1e-12, math.inf, math.nan, True, "1e-14"])
def test_mtest_metadata_cannot_change_the_original_driver_criterion(cold_observations, epsilon):
    settings, original = cold_observations
    raw = deepcopy(original)
    raw["mtest"]["deformation_gradient_epsilon"] = epsilon
    with pytest.raises(ValueError, match="MTest deformation gradient epsilon"):
        domain.assess(settings, raw)


def test_missing_mtest_original_criterion_is_not_inferred(cold_observations):
    settings, original = cold_observations
    raw = deepcopy(original)
    raw["mtest"].pop("deformation_gradient_epsilon")
    with pytest.raises(ValueError, match="MTest raw"):
        domain.assess(settings, raw)


@pytest.mark.parametrize("mutate", [
    lambda row: row.pop("imposed_deformation_gradient"),
    lambda row: row.update(imposed_deformation_gradient=[0.0] * 8),
    lambda row: row["imposed_deformation_gradient"].__setitem__(0, math.nan),
    lambda row: row["imposed_deformation_gradient"].__setitem__(0, True),
])
def test_missing_or_malformed_mtest_imposed_map_evidence_is_not_replaced(cold_observations, mutate):
    settings, original = cold_observations
    raw = deepcopy(original)
    mutate(raw["mtest"]["steps"][0])
    with pytest.raises(ValueError):
        domain.assess(settings, raw)


@pytest.mark.parametrize("component", range(9), ids=domain.F_COMPONENTS)
def test_mtest_imposed_components_must_match_history_exactly_even_with_subcriterion_drift(cold_observations, component):
    settings, original = cold_observations
    raw = deepcopy(original)
    imposed = raw["mtest"]["steps"][5]["imposed_deformation_gradient"]
    imposed[component] = math.nextafter(imposed[component], math.inf)
    outcome = domain.assess(settings, raw)
    assert_retained_failure(outcome, "native_history")
    assert check_map(outcome)["mtest_deformation_gradient_residual"]["status"] == "PASS"


def test_mtest_cannot_report_observed_gradient_as_the_exact_prescribed_map(cold_observations):
    settings, original = cold_observations
    raw = deepcopy(original)
    for row in raw["mtest"]["steps"]:
        row["imposed_deformation_gradient"] = deepcopy(row["deformation_gradient"])
    outcome = domain.assess(settings, raw)
    assert_retained_failure(outcome, "native_history")
    assert check_map(outcome)["mtest_deformation_gradient_residual"]["observed"] == 0.0


@pytest.mark.parametrize("mode", ["component_order", "endpoint_order", "time", "dt"])
def test_mtest_prescribed_order_and_time_cannot_drift_together_with_observed_state(cold_observations, mode):
    settings, original = cold_observations
    raw = deepcopy(original)
    rows = raw["mtest"]["steps"]
    if mode == "component_order":
        for field in ("imposed_deformation_gradient", "deformation_gradient"):
            values = rows[5][field]
            values[3], values[4] = values[4], values[3]
    elif mode == "endpoint_order":
        rows[1], rows[2] = rows[2], rows[1]
    elif mode == "time":
        rows[5]["time_s"] = math.nextafter(rows[5]["time_s"], math.inf)
    else:
        rows[5]["dt_s"] = math.nextafter(rows[5]["dt_s"], math.inf)
    assert_retained_failure(domain.assess(settings, raw), "native_history")


@pytest.fixture(scope="module")
def zero_diagonal_observations():
    """SYNTHETIC_NOT_NATIVE proper permutation rotation permits exact 0-F bounds."""
    settings = domain.canonical_settings()
    settings["history"][2]["deformation_gradient"] = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0]
    return settings, synthetic_raw(settings)


@pytest.mark.parametrize("component", range(9), ids=domain.F_COMPONENTS)
@pytest.mark.parametrize("sign", [-1, 1])
@pytest.mark.parametrize("bound", ["equal", "above"])
def test_every_observed_mtest_component_strictly_rejects_at_and_above_original_criterion(zero_diagonal_observations, component, sign, bound):
    settings, original = zero_diagonal_observations
    raw = deepcopy(original)
    endpoint = 1 if component < 3 else 0
    row = raw["mtest"]["steps"][endpoint]
    assert row["imposed_deformation_gradient"][component] == 0.0
    magnitude = 1e-14 if bound == "equal" else math.nextafter(1e-14, math.inf)
    row["deformation_gradient"][component] = sign * magnitude
    outcome = domain.assess(settings, raw)
    assert_retained_failure(outcome, "mtest_deformation_gradient_residual")
    assert check_map(outcome)["native_history"]["status"] == "FAIL"
    retained = outcome["mtest_gradient_residuals"][endpoint]
    assert retained["signed_residuals"][component] == sign * magnitude
    assert retained["absolute_residuals"][component] == magnitude
    assert retained["passed"] is False


@pytest.mark.parametrize("component", range(9), ids=domain.F_COMPONENTS)
def test_every_observed_mtest_component_preserves_below_criterion_residual(zero_diagonal_observations, component):
    settings, original = zero_diagonal_observations
    raw = deepcopy(original)
    endpoint = 1 if component < 3 else 0
    row = raw["mtest"]["steps"][endpoint]
    magnitude = math.nextafter(1e-14, 0.0)
    row["deformation_gradient"][component] = magnitude
    before = digest(raw)
    outcome = domain.assess(settings, raw)
    assert outcome["passed"] is True and outcome["numerical_status"] == "PASS"
    assert check_map(outcome)["mtest_deformation_gradient_residual"]["status"] == "PASS"
    assert outcome["mtest_gradient_residuals"][endpoint]["absolute_residuals"][component] == magnitude
    assert outcome["reference"] == domain.analytical_reference(settings) and digest(raw) == before


@pytest.mark.parametrize("component", range(9), ids=domain.F_COMPONENTS)
@pytest.mark.parametrize("invalid", [math.nan, math.inf, True])
def test_every_observed_mtest_component_refuses_nonfinite_or_boolean_values(cold_observations, component, invalid):
    settings, original = cold_observations
    raw = deepcopy(original)
    raw["mtest"]["steps"][0]["deformation_gradient"][component] = invalid
    with pytest.raises(ValueError):
        domain.assess(settings, raw)


@pytest.mark.parametrize("observed", [
    [-1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    [0.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    [2.1, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    [1.03, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
])
def test_actual_mtest_gradient_keeps_original_orientation_component_and_green_admission(cold_observations, observed):
    settings, original = cold_observations
    raw = deepcopy(original)
    raw["mtest"]["steps"][1]["deformation_gradient"] = observed
    with pytest.raises(ValueError):
        domain.assess(settings, raw)


def test_legal_near_boundary_history_does_not_admit_actual_mtest_green_strain_outside_original_bound():
    settings = domain.canonical_settings()
    # Configured endpoint plus every signed h=1e-7 probe must remain inside
    # G<=.02, so sub-1e-14 roundoff cannot bridge that admitted probe margin.
    settings["history"][2]["deformation_gradient"][0] = math.sqrt(1.04 - 4e-7)
    domain.validate_settings(settings)
    raw = synthetic_raw(settings)
    assert raw["test_evidence_kind"] == "SYNTHETIC_NOT_NATIVE"
    assert domain.assess(settings, raw)["numerical_status"] != "FAIL"
    raw["mtest"]["steps"][1]["deformation_gradient"][0] = math.sqrt(1.04) + 1e-12
    with pytest.raises(ValueError, match="Green strain Frobenius norm"):
        domain.assess(settings, raw)
