"""Independent St. Venant--Kirchhoff energy, PK1 Hessian and cold verdicts.

F/P are general physical tensors in the declared nine-component order. Only
MTest's symmetric Cauchy tensor uses Kelvin six. No solver, native path, NumPy,
binding or generated material code is used to construct a reference value.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import sys


__version__ = "1"
F_COMPONENTS = ("xx", "yy", "zz", "xy", "yx", "xz", "zx", "yz", "zy")
SYMMETRIC_COMPONENTS = ("xx", "yy", "zz", "xy", "xz", "yz")
_PAIRS = ((0, 0), (1, 1), (2, 2), (0, 1), (1, 0), (0, 2), (2, 0), (1, 2), (2, 1))
IDENTITY_F = (1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
_FIXED_LIMITS = {"stress_absolute_mpa": 1e-10, "stress_relative": 1e-8,
    "tangent_relative": 1e-8, "energy_absolute_mpa": 1e-10, "energy_relative": 1e-8,
    "finite_difference_relative": 1e-6, "finite_difference_steps": [1e-7, 1e-8, 1e-9]}
FIXED_LIMITS = deepcopy(_FIXED_LIMITS)
PENDING = ("model_qualification", "material_qualification", "physical_validation",
    "static_strength", "fatigue_durability", "solver_coupling", "corporate_license_approval",
    "corporate_security_approval", "native_dissipated_energy", "mtest_energy")


def _keys(value: object, names: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != names:
        raise ValueError(f"{label} requires exactly {sorted(names)}")
    return value


def _required(value: object, names: set[str], label: str) -> dict:
    if not isinstance(value, dict) or not names <= set(value):
        raise ValueError(f"{label} is missing required fields: {sorted(names)}")
    return value


def _number(value: object, label: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite real number, never bool")
    try:
        result = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError(f"{label} must be representable") from error
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _vector(value: object, size: int, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != size:
        raise ValueError(f"{label} requires {size} complete components")
    return [_number(item, label) for item in value]


def _matrix(value: object, size: int, label: str) -> list[list[float]]:
    if not isinstance(value, list) or len(value) != size:
        raise ValueError(f"{label} requires {size} complete rows")
    return [_vector(row, size, label) for row in value]


def _sum(values, label: str) -> float:
    try:
        return _number(math.fsum(values), label)
    except OverflowError as error:
        raise ValueError(f"{label} must be representable") from error


def to_matrix(components: list[float]) -> list[list[float]]:
    values = _vector(components, 9, "General physical tensor")
    result = [[0.0] * 3 for _ in range(3)]
    for (i, j), value in zip(_PAIRS, values):
        result[i][j] = value
    return result


def from_matrix(matrix: list[list[float]]) -> list[float]:
    rows = _matrix(matrix, 3, "General physical matrix")
    return [rows[i][j] for i, j in _PAIRS]


def to_kelvin(physical: list[float]) -> list[float]:
    values = _vector(physical, 6, "Symmetric physical Cauchy tensor")
    return values[:3] + [math.sqrt(2.0) * value for value in values[3:]]


def from_kelvin(kelvin: list[float]) -> list[float]:
    values = _vector(kelvin, 6, "Symmetric Kelvin Cauchy tensor")
    return values[:3] + [value / math.sqrt(2.0) for value in values[3:]]


def transpose(matrix: list[list[float]]) -> list[list[float]]:
    rows = _matrix(matrix, 3, "Matrix")
    return [[rows[j][i] for j in range(3)] for i in range(3)]


def multiply(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    a, b = _matrix(left, 3, "Left matrix"), _matrix(right, 3, "Right matrix")
    return [[_sum((a[i][k] * b[k][j] for k in range(3)), "Matrix product") for j in range(3)] for i in range(3)]


def determinant(matrix: list[list[float]]) -> float:
    a = _matrix(matrix, 3, "Matrix")
    return _sum((a[0][0] * a[1][1] * a[2][2], a[0][1] * a[1][2] * a[2][0],
        a[0][2] * a[1][0] * a[2][1], -a[0][2] * a[1][1] * a[2][0],
        -a[0][1] * a[1][0] * a[2][2], -a[0][0] * a[1][2] * a[2][1]), "Determinant")


def _inverse(a: list[list[float]]) -> list[list[float]]:
    det = determinant(a)
    if det <= 0.0:
        raise ValueError("An orientation-preserving invertible matrix is required")
    return [[_number((a[(j + 1) % 3][(i + 1) % 3] * a[(j + 2) % 3][(i + 2) % 3] -
                      a[(j + 1) % 3][(i + 2) % 3] * a[(j + 2) % 3][(i + 1) % 3]) / det,
                     "Inverse matrix") for j in range(3)] for i in range(3)]


def _kinematics(components: list[float]) -> tuple:
    values = _vector(components, 9, "Deformation gradient")
    if any(abs(value) > 2.0 for value in values):
        raise ValueError("Deformation gradient components must have absolute value <=2")
    f = to_matrix(values)
    jacobian = determinant(f)
    if jacobian <= 0.0:
        raise ValueError("Every deformation and signed probe requires J>0")
    c = multiply(transpose(f), f)
    green = [[0.5 * (c[i][j] - (1.0 if i == j else 0.0)) for j in range(3)] for i in range(3)]
    norm = _number(math.hypot(*(value for row in green for value in row)), "Green strain norm")
    if norm > 0.02:
        raise ValueError("Green strain Frobenius norm must be <=0.02")
    return f, jacobian, green, norm


def _material(material: dict) -> tuple[float, float, float]:
    _keys(material, {"youngs_modulus_mpa", "poisson_ratio"}, "Material")
    young = _number(material["youngs_modulus_mpa"], "Young modulus")
    poisson = _number(material["poisson_ratio"], "Poisson ratio")
    if not 0.0 < young <= 1e9 or not -1.0 < poisson < 0.5:
        raise ValueError("Require 0<E<=1e9 MPa and -1<nu<0.5")
    lam = _number(young * poisson / ((1.0 + poisson) * (1.0 - 2.0 * poisson)), "Lambda")
    mu = _number(young / (2.0 * (1.0 + poisson)), "Mu")
    bulk = _number(young / (3.0 * (1.0 - 2.0 * poisson)), "Bulk modulus")
    if mu <= 0.0 or bulk <= 0.0:
        raise ValueError("Elastic quadratic energy must be positively representable")
    return lam, mu, bulk


def response(deformation_gradient: list[float], material: dict) -> dict:
    """Independent W/P/sigma and full physical-order energy Hessian at one F."""
    f, jacobian, green, norm = _kinematics(deformation_gradient)
    lam, mu, bulk = _material(material)
    trace = _sum((green[i][i] for i in range(3)), "Green strain trace")
    dev = [[green[i][j] - (trace / 3.0 if i == j else 0.0) for j in range(3)] for i in range(3)]
    # Algebraically identical positive bulk/deviator form avoids cancellation
    # of lambda terms for an admitted negative Poisson ratio near -1.
    energy = _sum((0.5 * bulk * trace * trace,
                   *[mu * value * value for row in dev for value in row]), "Reference-volume energy")
    second = [[_sum((2.0 * mu * dev[i][j], bulk * trace if i == j else 0.0), "PK2 stress")
               for j in range(3)] for i in range(3)]
    first = multiply(f, second)
    cauchy = [[_number(value / jacobian, "Cauchy stress") for value in row]
              for row in multiply(first, transpose(f))]
    spatial = multiply(f, transpose(f))
    hessian = [[_sum((second[l][j] if i == k else 0.0, lam * f[i][j] * f[k][l],
                      mu * f[i][l] * f[k][j], mu * spatial[i][k] if j == l else 0.0), "PK1 energy Hessian")
                for k, l in _PAIRS] for i, j in _PAIRS]
    return {"deformation_gradient": list(deformation_gradient), "jacobian": jacobian,
        "green_strain": [green[i][j] for i, j in ((0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2))],
        "green_strain_norm": norm, "pk2_stress_mpa": [second[i][j] for i, j in
            ((0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2))],
        "pk1_stress_mpa": from_matrix(first), "cauchy_stress_mpa": [cauchy[i][j] for i, j in
            ((0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2))],
        "pk1_tangent_mpa": hessian, "stored_energy_density_mpa": energy}


def _rotation(axis: str, angle: float) -> list[list[float]]:
    c, s = math.cos(angle), math.sin(angle)
    return ([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]] if axis == "z" else
            [[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def canonical_settings() -> dict:
    """Exact twelve-state strain/rotation/recovery request, deep independent."""
    identity = to_matrix(list(IDENTITY_F))
    h = [[1.001, .0004, -.0002], [.00015, .9995, .0003], [.00025, -.00035, 1.0007]]
    gradients = [identity, identity, [[1.001, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        [[.999, 0.0, 0.0], [0.0, 1.0007, 0.0], [0.0, 0.0, 1.0003]],
        [[1.0, .0006, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        [[1.0, 0.0, 0.0], [-.0004, 1.0, 0.0], [0.0, 0.0, 1.0]],
        h, multiply(_rotation("z", math.pi / 4.0), h),
        multiply(multiply(_rotation("x", math.pi / 6.0), _rotation("z", math.pi / 3.0)), h),
        h, _rotation("z", math.pi / 3.0), identity]
    return {"case": "saint_venant_kirchhoff", "material": {"youngs_modulus_mpa": 210000.0, "poisson_ratio": .3},
        "temperature_k": 293.15, "history": [{"time_s": float(i), "deformation_gradient": from_matrix(f)}
                                            for i, f in enumerate(gradients)], "limits": deepcopy(_FIXED_LIMITS)}


def validate_settings(settings: dict) -> dict:
    """Deep admission including every fixed signed central probe before export."""
    _keys(settings, {"case", "material", "temperature_k", "history", "limits"}, "Settings")
    if settings["case"] != "saint_venant_kirchhoff":
        raise ValueError("Only the bounded saint_venant_kirchhoff law is supported")
    _material(settings["material"])
    material = {name: _number(value, name) for name, value in settings["material"].items()}
    temperature = _number(settings["temperature_k"], "Temperature")
    if not 0.0 < temperature <= 5000.0:
        raise ValueError("Require 0<T<=5000 K; no temperature dependence is qualified")
    _keys(settings["limits"], set(_FIXED_LIMITS), "Limits")
    for name, expected in _FIXED_LIMITS.items():
        observed = (_vector(settings["limits"][name], 3, name) if isinstance(expected, list)
                    else _number(settings["limits"][name], name))
        if observed != expected:
            raise ValueError(f"{name} is frozen before native execution")
    history = settings["history"]
    if not isinstance(history, list) or not 3 <= len(history) <= 32:
        raise ValueError("History requires 3 through 32 complete ordered states")
    normalized = []
    meaningful = False
    for index, entry in enumerate(history):
        _keys(entry, {"time_s", "deformation_gradient"}, "History entry")
        time = _number(entry["time_s"], "Time")
        f = _vector(entry["deformation_gradient"], 9, "Deformation gradient")
        if not 0.0 <= time <= 1e6 or (index and time <= normalized[-1]["time_s"]):
            raise ValueError("Times must strictly increase within [0,1e6]")
        _, _, _, norm = _kinematics(f)
        meaningful |= norm >= 1e-6
        if index:
            for step in _FIXED_LIMITS["finite_difference_steps"]:
                for column in range(9):
                    for sign in (-1, 1):
                        probe = list(f)
                        probe[column] += sign * step
                        _kinematics(probe)
        # Refuse unrepresentable response fields/scales as part of preflight.
        response(f, material)
        normalized.append({"time_s": time, "deformation_gradient": f})
    if normalized[0]["time_s"] != 0.0 or normalized[0]["deformation_gradient"] != list(IDENTITY_F):
        raise ValueError("The first unprepared record must be t0 with identity F")
    if normalized[1]["deformation_gradient"] != list(IDENTITY_F):
        raise ValueError("The second endpoint must be actual native identity F at positive dt")
    if not meaningful:
        raise ValueError("At least one meaningful Green strain norm >=1e-6 is required")
    result = {"case": settings["case"], "material": material, "temperature_k": temperature,
              "history": normalized, "limits": deepcopy(_FIXED_LIMITS)}
    _reference(result)
    return result


def _flat(matrix: list[list[float]]) -> list[float]:
    return [value for row in matrix for value in row]


def _reference(settings: dict) -> dict:
    states = [{"time_s": entry["time_s"], "phase": "REFERENCE_ONLY_UNPREPARED" if index == 0 else "REFERENCE_ONLY",
               **response(entry["deformation_gradient"], settings["material"])}
              for index, entry in enumerate(settings["history"])]
    endpoints = states[1:]
    scales = {"stress_mpa": max(abs(x) for row in endpoints for key in
                              ("pk1_stress_mpa", "cauchy_stress_mpa") for x in row[key]),
              "tangent_mpa": max(abs(x) for row in endpoints for x in _flat(row["pk1_tangent_mpa"])),
              "energy_mpa": max(row["stored_energy_density_mpa"] for row in endpoints)}
    if any(not math.isfinite(value) or value <= 0.0 for value in scales.values()):
        raise ValueError("Declared history reference scales must be positively representable")
    lam, mu, bulk = _material(settings["material"])
    return {"case": settings["case"], "lambda_mpa": lam, "mu_mpa": mu, "bulk_modulus_mpa": bulk,
        "general_component_order": list(F_COMPONENTS), "symmetric_component_order": list(SYMMETRIC_COMPONENTS),
        "tangent_axes": "rows_P_columns_F_in_general_component_order", "states": states, "scales": scales,
        "energy_measure": "per_reference_volume", "energy_unit": "MPa = N mm/mm^3",
        "native_dissipated_energy": "UNKNOWN", "mtest_energy": "UNKNOWN"}


def analytical_reference(settings: dict) -> dict:
    return _reference(validate_settings(settings))


def model_declaration(settings: dict) -> dict:
    settings = validate_settings(settings)
    return {"model": {"geometry": None, "mesh": None, "materials": [{"law": "saint_venant_kirchhoff",
        "youngs_modulus_mpa": settings["material"]["youngs_modulus_mpa"], "poisson_ratio": settings["material"]["poisson_ratio"],
        "source_kind": "SYNTHETIC_REFERENCE", "qualified": False, "kinematics": "finite_rotation_small_green_strain"}]},
        "initial_conditions": [{"type": "deformation_gradient", "value": list(IDENTITY_F), "components": list(F_COMPONENTS)},
            {"type": "temperature", "value": settings["temperature_k"], "unit": "K"}],
        "boundary_conditions": [], "loads": [{"type": "prescribed_deformation_gradient_history", "components": list(F_COMPONENTS),
            "convention": "physical_general_tensor", "unit": "1", "time_unit": "s", "history": deepcopy(settings["history"])}],
        "outputs": {"fields": [{"name": "pk1_stress", "components": list(F_COMPONENTS), "unit": "MPa", "measure": "PK1"},
            {"name": "cauchy_stress", "components": list(SYMMETRIC_COMPONENTS), "unit": "MPa", "measure": "Cauchy"},
            {"name": "pk1_tangent", "shape": [9, 9], "unit": "MPa", "axes": "P/F"}],
            "history": [{"name": "native_stored_energy_density", "unit": "MPa", "measure": "per_reference_volume"}]},
        "scope": "Bounded SVK finite-kinematics material point; no general rubber, physical or spatial solver qualification"}


def state_hash(state: dict) -> str:
    try:
        text = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError("Complete state must be finite JSON data") from error
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_STATE_KEYS = {"deformation_gradient", "pk1_stress_mpa", "stored_energies",
    "internal_state_variables", "dissipated_energies", "material_properties",
    "external_state_variables", "manager_tangent_cache_mpa", "dt_s"}


def _snapshot(state: object, label: str) -> dict:
    _keys(state, _STATE_KEYS, label)
    _vector(state["deformation_gradient"], 9, label + ".F")
    _vector(state["pk1_stress_mpa"], 9, label + ".P")
    _vector(state["stored_energies"], 1, label + ".stored_energies")
    _vector(state["internal_state_variables"], 0, label + ".ISV_absent")
    _vector(state["dissipated_energies"], 0, label + ".dissipation_absent")
    _matrix(state["manager_tangent_cache_mpa"], 9, label + ".manager_K")
    _keys(state["material_properties"], {"YoungModulus", "PoissonRatio"}, label + ".properties")
    _keys(state["external_state_variables"], {"Temperature"}, label + ".ESV")
    for value in (*state["material_properties"].values(), *state["external_state_variables"].values()):
        _number(value, label + ".property_or_ESV")
    _number(state["dt_s"], label + ".dt")
    return state


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{label} requires a measured lowercase SHA256")
    return value


def _return(value: object, label: str) -> int:
    if type(value) is not int or value not in (-1, 0, 1):
        raise ValueError(f"{label} requires the native integer -1,0,1 return")
    return value


def _containers(value: object) -> list[int]:
    """Mutable containers, including nested caches/properties, must be copied."""
    if isinstance(value, dict):
        return [id(value), *(item for child in value.values() for item in _containers(child))]
    if isinstance(value, list):
        return [id(value), *(item for child in value for item in _containers(child))]
    return []


def _max_error(observed: list[float], expected: list[float]) -> float:
    return max(_number(abs(a - b), "Observed error") for a, b in zip(observed, expected))


def _norm_error(observed: list[float], expected: list[float]) -> float:
    return _number(math.hypot(*(a - b for a, b in zip(observed, expected))), "Observed error norm")


def _symmetric_matrix(components: list[float]) -> list[list[float]]:
    v = _vector(components, 6, "Physical symmetric tensor")
    return [[v[0], v[3], v[4]], [v[3], v[1], v[5]], [v[4], v[5], v[2]]]


def _sym_components(matrix: list[list[float]]) -> list[float]:
    return [matrix[i][j] for i, j in ((0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2))]


def _rotated_tangent(matrix: list[list[float]], q: list[list[float]]) -> list[list[float]]:
    lookup = {pair: n for n, pair in enumerate(_PAIRS)}
    return [[_sum((q[i][a] * q[k][b] * matrix[lookup[a, j]][lookup[b, l]]
                   for a in range(3) for b in range(3)), "Spatially rotated PK1 Hessian")
             for k, l in _PAIRS] for i, j in _PAIRS]


def _pair_checks(history: list[dict], observations: list[dict], scales: dict, limits: dict) -> dict:
    """All observed matching-C pairs; references never substitute observations."""
    rotated, recovered = [], []
    eps = 64.0 * sys.float_info.epsilon
    for i, first in enumerate(observations):
        fa = to_matrix(history[i + 1]["deformation_gradient"])
        ca = multiply(transpose(fa), fa)
        for j in range(i + 1, len(observations)):
            second = observations[j]
            fb = to_matrix(history[j + 1]["deformation_gradient"])
            cb = multiply(transpose(fb), fb)
            if _max_error(_flat(ca), _flat(cb)) > eps * max(1.0, *(abs(v) for v in _flat(ca))):
                continue
            same_f = history[i + 1]["deformation_gradient"] == history[j + 1]["deformation_gradient"]
            q = multiply(fb, _inverse(fa))
            qqt = multiply(q, transpose(q))
            if (abs(determinant(q) - 1.0) > eps or
                    _max_error(_flat(qqt), _flat(to_matrix(list(IDENTITY_F)))) > eps):
                continue
            expected_p = (first["pk1_stress_mpa"] if same_f else
                          from_matrix(multiply(q, to_matrix(first["pk1_stress_mpa"]))))
            expected_sigma = (first["cauchy_stress_mpa"] if same_f else _sym_components(
                multiply(multiply(q, _symmetric_matrix(first["cauchy_stress_mpa"])), transpose(q))))
            expected_a = (first["pk1_tangent_mpa"] if same_f else _rotated_tangent(first["pk1_tangent_mpa"], q))
            errors = {"pk1_error_mpa": _max_error(second["pk1_stress_mpa"], expected_p),
                "cauchy_error_mpa": _max_error(second["cauchy_stress_mpa"], expected_sigma),
                "tangent_error_mpa": _max_error(_flat(second["pk1_tangent_mpa"]), _flat(expected_a)),
                "energy_error_mpa": abs(second["stored_energy_density_mpa"] - first["stored_energy_density_mpa"])}
            entry = {"first_history_index": i + 1, "second_history_index": j + 1,
                     "spatial_rotation": q, **errors,
                     "tangent_relative_error": errors["tangent_error_mpa"] / scales["tangent_mpa"]}
            (recovered if same_f else rotated).append(entry)
    stress_bound = limits["stress_absolute_mpa"] + limits["stress_relative"] * scales["stress_mpa"]
    energy_bound = limits["energy_absolute_mpa"] + limits["energy_relative"] * scales["energy_mpa"]
    result = {}
    for code, rows in (("spatial_objectivity", rotated), ("path_recovery", recovered)):
        passed = all(row["pk1_error_mpa"] <= stress_bound and row["cauchy_error_mpa"] <= stress_bound and
                     row["energy_error_mpa"] <= energy_bound and
                     row["tangent_relative_error"] <= limits["tangent_relative"] for row in rows)
        result[code] = {"code": code, "status": ("PASS" if passed else "FAIL") if rows else "UNKNOWN",
            "pairs": rows, "reason": "All observed eligible pairs" if rows else "Required observed matching-C pair absent",
            "stress_limit_mpa": stress_bound, "energy_limit_mpa": energy_bound,
            "tangent_relative_limit": limits["tangent_relative"]}
    return result


def assess(settings: dict, raw: dict) -> dict:
    """Check complete observed records; retain finite failures and UNKNOWN gates.

    Malformed/partial/nonfinite observations raise ValueError. Numerical/state/
    reliable-return failures stay in metrics with valid=False. Native t0 buffers
    are only continuity metadata; every numerical check starts at actual t1.
    Actual binding/runtime/source/build identity remains the adapter's gate.
    """
    settings = validate_settings(settings)
    reference = _reference(settings)
    _required(raw, {"library_sha256", "initial", "steps", "mtest"}, "Native raw")
    library = _sha(raw["library_sha256"], "Native library")
    mtest = _required(raw["mtest"], {"library_sha256", "steps", "deformation_gradient_epsilon"}, "MTest raw")
    other_library = _sha(mtest["library_sha256"], "MTest library")
    mtest_gradient_epsilon = _number(mtest["deformation_gradient_epsilon"], "MTest deformation gradient epsilon")
    if mtest_gradient_epsilon != 1e-14:
        raise ValueError("MTest deformation gradient epsilon must retain the original fixed 1e-14 criterion")
    steps, other_steps = raw["steps"], mtest["steps"]
    expected_steps = len(settings["history"]) - 1
    if (not isinstance(steps, list) or len(steps) != expected_steps or
            not isinstance(other_steps, list) or len(other_steps) != expected_steps):
        raise ValueError("Every actual endpoint is required in both driver histories")
    flags = {code: True for code in ("reliable_integrations", "native_history", "same_library",
        "immutable_probe_state", "snapshot_content", "probe_admission", "fd_summary_integrity", "native_tensor_measure")}
    flags["same_library"] = library == other_library
    initial = _required(raw["initial"], {"phase", "time_s", "deformation_gradient", "state", "state_sha256"}, "Initial metadata")
    initial_f = _vector(initial["deformation_gradient"], 9, "Initial F")
    previous = _snapshot(initial["state"], "Unprepared initial buffers")
    initial_time = _number(initial["time_s"], "Initial time")
    properties = {"YoungModulus": settings["material"]["youngs_modulus_mpa"], "PoissonRatio": settings["material"]["poisson_ratio"]}
    external = {"Temperature": settings["temperature_k"]}
    flags["native_history"] &= (initial["phase"] == "INITIAL_UNPREPARED" and initial_time == 0.0 and
        initial_f == list(IDENTITY_F) and previous["deformation_gradient"] == initial_f and previous["dt_s"] == 0.0)
    flags["snapshot_content"] &= (_sha(initial["state_sha256"], "Initial hash") == state_hash(previous) and
        previous["material_properties"] == properties and previous["external_state_variables"] == external)
    scales, limits = reference["scales"], settings["limits"]
    errors, fd_reports = [], {h: [] for h in limits["finite_difference_steps"]}
    mtest_gradient_reports = []
    stress_bound = limits["stress_absolute_mpa"] + limits["stress_relative"] * scales["stress_mpa"]
    energy_bound = limits["energy_absolute_mpa"] + limits["energy_relative"] * scales["energy_mpa"]
    fd_stress_bound = limits["stress_absolute_mpa"] + limits["finite_difference_relative"] * scales["stress_mpa"]
    probe_errors = []
    # Identity of serialized snapshots is checked as well as their contents.
    # JSON alone cannot establish the native memory-copy mechanism; the adapter
    # must retain that execution evidence separately.
    initial_containers = _containers(previous)
    seen_snapshots: set[int] = set(initial_containers)
    flags["immutable_probe_state"] &= len(initial_containers) == len(seen_snapshots)

    def checked_state(value: object, label: str) -> dict:
        state = _snapshot(value, label)
        flags["snapshot_content"] &= state["material_properties"] == properties and state["external_state_variables"] == external
        containers = _containers(state)
        flags["immutable_probe_state"] &= (len(containers) == len(set(containers)) and
                                          not seen_snapshots.intersection(containers))
        seen_snapshots.update(containers)
        return state

    def matches_snapshot(state: dict, observation: dict, dt: float, *, tangent: bool) -> bool:
        return (state["deformation_gradient"] == observation["deformation_gradient"] and
                state["pk1_stress_mpa"] == observation["pk1_stress_mpa"] and
                state["stored_energies"] == [observation["stored_energy_density_mpa"]] and state["dt_s"] == dt and
                (not tangent or state["manager_tangent_cache_mpa"] == observation["pk1_tangent_mpa"]))

    for index, (step, other, expected) in enumerate(zip(steps, other_steps, reference["states"][1:]), 1):
        _required(step, {"time_s", "dt_s", "deformation_gradient", "pk1_stress_mpa", "cauchy_stress_mpa",
            "pk1_tangent_mpa", "stored_energy_density_mpa", "integration_return", "initial_state", "initial_state_sha256",
            "nominal_before_probes", "nominal_after_probes", "nominal_after_update", "nominal_after_update_sha256",
            "finite_differences"}, "Actual MGIS endpoint")
        f = _vector(step["deformation_gradient"], 9, "Actual F")
        p = _vector(step["pk1_stress_mpa"], 9, "Actual PK1")
        sigma = _vector(step["cauchy_stress_mpa"], 6, "Actual Cauchy")
        tangent = _matrix(step["pk1_tangent_mpa"], 9, "Actual PK1 tangent")
        energy = _number(step["stored_energy_density_mpa"], "Actual native W")
        time = _number(step["time_s"], "Actual endpoint time")
        dt = settings["history"][index]["time_s"] - settings["history"][index - 1]["time_s"]
        flags["native_history"] &= (time == expected["time_s"] and f == expected["deformation_gradient"] and
            _number(step["dt_s"], "Actual dt") == dt and step.get("phase", "INTEGRATED") == "INTEGRATED")
        flags["reliable_integrations"] &= _return(step["integration_return"], "Nominal integration") == 1
        baseline = checked_state(step["initial_state"], "Nominal initial snapshot")
        before = checked_state(step["nominal_before_probes"], "Nominal before probes")
        after = checked_state(step["nominal_after_probes"], "Nominal after probes")
        committed = checked_state(step["nominal_after_update"], "Nominal committed snapshot")
        flags["immutable_probe_state"] &= (all(baseline[key] == previous[key] for key in previous if key != "dt_s") and
            baseline["dt_s"] == dt and before == after)
        # MGIS update commits s1 to s0 and resets the manager's nonphysical K
        # cache. Preserve its actual pre-update tangent and require the captured
        # committed state, including dt and every physical field, independently.
        flags["immutable_probe_state"] &= (all(committed[key] == after[key] for key in after
            if key != "manager_tangent_cache_mpa") and
            all(value == 0.0 for value in _flat(committed["manager_tangent_cache_mpa"])))
        flags["snapshot_content"] &= (_sha(step["initial_state_sha256"], "Nominal baseline hash") == state_hash(baseline) and
            matches_snapshot(before, step, dt, tangent=True) and matches_snapshot(after, step, dt, tangent=True) and
            _sha(step["nominal_after_update_sha256"], "Nominal committed hash") == state_hash(committed))
        fm = to_matrix(f)
        jacobian = determinant(fm)
        if jacobian > 0.0:
            transformed = [[_number(v / jacobian, "Observed PK1 to Cauchy") for v in row]
                           for row in multiply(to_matrix(p), transpose(fm))]
            measure_error = _max_error(sigma, _sym_components(transformed))
            skew_error = max(abs(transformed[i][j] - transformed[j][i]) for i in range(3) for j in range(3))
            flags["native_tensor_measure"] &= max(measure_error, skew_error) <= stress_bound
        else:
            measure_error, skew_error = scales["stress_mpa"], scales["stress_mpa"]
            flags["native_tensor_measure"] = False
        _required(other, {"phase", "time_s", "dt_s", "imposed_deformation_gradient", "deformation_gradient",
            "cauchy_stress_kelvin_mpa", "integration_return"}, "MTest endpoint")
        imposed_f = _vector(other["imposed_deformation_gradient"], 9, "MTest imposed F")
        other_f = _vector(other["deformation_gradient"], 9, "MTest F")
        _kinematics(other_f)
        other_time = _number(other["time_s"], "MTest time")
        other_dt = _number(other["dt_s"], "MTest dt")
        gradient_residuals = [_number(actual - imposed, "MTest F residual") for actual, imposed in zip(other_f, imposed_f)]
        gradient_errors = [abs(value) for value in gradient_residuals]
        gradient_passed = all(value < mtest_gradient_epsilon for value in gradient_errors)
        mtest_gradient_reports.append({"history_index": index, "time_s": other_time, "dt_s": other_dt,
            "imposed_deformation_gradient": imposed_f, "deformation_gradient": other_f,
            "signed_residuals": gradient_residuals, "absolute_residuals": gradient_errors,
            "maximum_absolute_residual": max(gradient_errors), "passed": gradient_passed})
        other_sigma = from_kelvin(other["cauchy_stress_kelvin_mpa"])
        flags["native_history"] &= (other["phase"] == "INTEGRATED" and other_time == time == expected["time_s"] and
            other_dt == dt and imposed_f == expected["deformation_gradient"] and gradient_passed)
        flags["reliable_integrations"] &= _return(other["integration_return"], "MTest integration") == 1
        errors.append({"history_index": index, "time_s": time,
            "pk1_error_mpa": _max_error(p, expected["pk1_stress_mpa"]), "pk1_error_norm_mpa": _norm_error(p, expected["pk1_stress_mpa"]),
            "cauchy_error_mpa": _max_error(sigma, expected["cauchy_stress_mpa"]), "cauchy_error_norm_mpa": _norm_error(sigma, expected["cauchy_stress_mpa"]),
            "tangent_error_mpa": _max_error(_flat(tangent), _flat(expected["pk1_tangent_mpa"])),
            "tangent_error_norm_mpa": _norm_error(_flat(tangent), _flat(expected["pk1_tangent_mpa"])),
            "tangent_major_symmetry_error_mpa": max(abs(tangent[i][j] - tangent[j][i]) for i in range(9) for j in range(9)),
            "energy_error_mpa": abs(energy - expected["stored_energy_density_mpa"]),
            "mtest_reference_error_mpa": _max_error(other_sigma, expected["cauchy_stress_mpa"]),
            "cross_driver_error_mpa": _max_error(other_sigma, sigma),
            "pk1_cauchy_measure_error_mpa": measure_error, "cauchy_skew_error_mpa": skew_error})
        fds = step["finite_differences"]
        if not isinstance(fds, list) or len(fds) != 3:
            raise ValueError("All three configured FD h values are required at every endpoint")
        seen_h = set()
        for fd in fds:
            _required(fd, {"h", "probes", "pk1_tangent_mpa", "energy_gradient_mpa"}, "FD observations")
            h = _number(fd["h"], "FD h")
            if h not in fd_reports or h in seen_h:
                raise ValueError("Missing, duplicate or unsupported FD h")
            seen_h.add(h)
            reported_a = _matrix(fd["pk1_tangent_mpa"], 9, "Reported FD PK1 tangent")
            reported_p = _vector(fd["energy_gradient_mpa"], 9, "Reported FD energy gradient")
            probes = fd["probes"]
            if not isinstance(probes, list) or len(probes) != 18:
                raise ValueError("Each h requires plus/minus observations for all nine F columns")
            signed = {}
            for probe in probes:
                _required(probe, {"column", "sign", "deformation_gradient", "pk1_stress_mpa", "stored_energy_density_mpa", "integration_return",
                    "initial_state", "initial_state_sha256", "final_state", "final_state_sha256"}, "Signed native probe")
                column, sign = probe["column"], probe["sign"]
                if type(column) is not int or column not in range(9) or type(sign) is not int or sign not in (-1, 1) or (column, sign) in signed:
                    raise ValueError("Every FD column/sign must be a unique exact integer pair")
                probe_f = _vector(probe["deformation_gradient"], 9, "Probe F")
                _kinematics(probe_f)
                _vector(probe["pk1_stress_mpa"], 9, "Probe actual P")
                _number(probe["stored_energy_density_mpa"], "Probe actual W")
                probe_before = checked_state(probe["initial_state"], "Probe initial snapshot")
                probe_after = checked_state(probe["final_state"], "Probe final snapshot")
                flags["immutable_probe_state"] &= probe_before == baseline
                flags["snapshot_content"] &= (_sha(probe["initial_state_sha256"], "Probe baseline hash") == state_hash(probe_before) and
                    _sha(probe["final_state_sha256"], "Probe final hash") == state_hash(probe_after) and matches_snapshot(probe_after, probe, dt, tangent=False))
                flags["reliable_integrations"] &= _return(probe["integration_return"], "Probe integration") == 1
                target_f = list(expected["deformation_gradient"])
                target_f[column] += sign * h
                flags["probe_admission"] &= probe_f == target_f
                expected_probe = response(target_f, settings["material"])
                probe_errors.append({"history_index": index, "h": h, "column": column, "sign": sign,
                    "pk1_error_mpa": _max_error(probe["pk1_stress_mpa"], expected_probe["pk1_stress_mpa"]),
                    "energy_error_mpa": abs(probe["stored_energy_density_mpa"] - expected_probe["stored_energy_density_mpa"])})
                signed[column, sign] = probe
            recomputed_a = [[_number((signed[j, 1]["pk1_stress_mpa"][i] - signed[j, -1]["pk1_stress_mpa"][i]) / (2.0 * h), "Recomputed FD tangent")
                             for j in range(9)] for i in range(9)]
            recomputed_p = [_number((signed[j, 1]["stored_energy_density_mpa"] - signed[j, -1]["stored_energy_density_mpa"]) / (2.0 * h), "Recomputed energy gradient")
                            for j in range(9)]
            flags["fd_summary_integrity"] &= reported_a == recomputed_a and reported_p == recomputed_p
            fd_reports[h].append({"history_index": index, "time_s": time, "pk1_tangent_mpa": recomputed_a,
                "energy_gradient_mpa": recomputed_p, "reported_tangent_error_mpa": _max_error(_flat(reported_a), _flat(recomputed_a)),
                "reported_gradient_error_mpa": _max_error(reported_p, recomputed_p),
                "tangent_vs_native_mpa": _max_error(_flat(recomputed_a), _flat(tangent)),
                "tangent_vs_reference_mpa": _max_error(_flat(recomputed_a), _flat(expected["pk1_tangent_mpa"])),
                "gradient_vs_native_mpa": _max_error(recomputed_p, p),
                "gradient_vs_reference_mpa": _max_error(recomputed_p, expected["pk1_stress_mpa"])})
        previous = committed
    checks = [{"code": code, "status": "PASS" if flag else "FAIL", "observed": flag, "expected": True} for code, flag in flags.items()]
    checks.append({"code": "mtest_deformation_gradient_residual",
        "status": "PASS" if all(row["passed"] for row in mtest_gradient_reports) else "FAIL",
        "observed": max(row["maximum_absolute_residual"] for row in mtest_gradient_reports),
        "limit": mtest_gradient_epsilon, "comparison": "strictly_less_than",
        "component_order": list(F_COMPONENTS), "every_component_error": [deepcopy(row["absolute_residuals"]) for row in mtest_gradient_reports]})
    metrics = {}

    def numeric(code: str, values: list[float], unit: str, bound: float) -> None:
        maximum = max(values)
        metrics[code] = {"value": maximum, "unit": unit}
        checks.append({"code": code, "status": "PASS" if maximum <= bound else "FAIL", "observed": maximum,
                       "limit": bound, "every_error": values})

    for code, key in (("pk1_stress_error", "pk1_error_mpa"), ("cauchy_stress_error", "cauchy_error_mpa"),
            ("mtest_stress_error", "mtest_reference_error_mpa"), ("cross_driver_stress_error", "cross_driver_error_mpa")):
        numeric(code, [row[key] for row in errors], "MPa", stress_bound)
    numeric("analytical_tangent_relative_error", [row["tangent_error_mpa"] / scales["tangent_mpa"] for row in errors], "1", limits["tangent_relative"])
    numeric("tangent_major_symmetry_relative_error", [row["tangent_major_symmetry_error_mpa"] / scales["tangent_mpa"] for row in errors], "1", limits["tangent_relative"])
    numeric("native_energy_density_error", [row["energy_error_mpa"] for row in errors], "MPa", energy_bound)
    numeric("probe_pk1_stress_error", [row["pk1_error_mpa"] for row in probe_errors], "MPa", stress_bound)
    numeric("probe_native_energy_density_error", [row["energy_error_mpa"] for row in probe_errors], "MPa", energy_bound)
    for h, rows in fd_reports.items():
        suffix = format(h, ".0e")
        for name, key, scale, bound, unit in (
            ("fd_tangent_vs_native_", "tangent_vs_native_mpa", scales["tangent_mpa"], limits["finite_difference_relative"], "1"),
            ("fd_tangent_vs_reference_", "tangent_vs_reference_mpa", scales["tangent_mpa"], limits["finite_difference_relative"], "1"),
            ("fd_energy_gradient_vs_native_", "gradient_vs_native_mpa", 1.0, fd_stress_bound, "MPa"),
            ("fd_energy_gradient_vs_reference_", "gradient_vs_reference_mpa", 1.0, fd_stress_bound, "MPa")):
            numeric(name + suffix, [row[key] / scale for row in rows], unit, bound)
    pair_report = _pair_checks(settings["history"], steps, scales, limits)
    checks.extend(pair_report.values())
    scientific_passed = all(check["status"] != "FAIL" for check in checks)
    complete = all(check["status"] == "PASS" for check in checks)
    for metric in metrics.values():
        metric["valid"] = scientific_passed
        if not scientific_passed:
            metric["reason"] = "One or more numerical, native-state, history or reliable-return checks failed"
    return {"reference": reference, "checks": checks, "metrics": metrics, "passed": complete,
        "numerical_status": "FAIL" if not scientific_passed else "PASS" if complete else "UNKNOWN",
        "release_status": "NOT_RELEASED", "pending": [{"code": code, "status": "UNKNOWN", "blocking": True} for code in PENDING],
        "endpoint_errors": errors, "probe_errors": probe_errors, "mtest_gradient_residuals": mtest_gradient_reports,
        "finite_difference_errors": [{"h": h, "steps": rows} for h, rows in fd_reports.items()],
        "pair_observations": pair_report, "native_observations": {
            "time_s": [row["time_s"] for row in steps], "pk1_stress_mpa": [deepcopy(row["pk1_stress_mpa"]) for row in steps],
            "cauchy_stress_mpa": [deepcopy(row["cauchy_stress_mpa"]) for row in steps],
            "stored_energy_density_mpa": [row["stored_energy_density_mpa"] for row in steps],
            "actual_endpoint_count": expected_steps, "unprepared_initial_excluded": True,
            "native_dissipated_energy": "UNKNOWN", "mtest_energy": "UNKNOWN"},
        "limitations": ["One synthetic constitutive law and library; driver agreement is not cross-solver physical validation",
            "Large proper rotations with admitted small Green strain, not general rubber or large-stretch stability",
            "Native copy/runtime/build/source/descriptor evidence is separately required from the adapter",
            "No inferred FD rate or replacement of absent native energy", "No strength, durability or RELEASED verdict"]}
