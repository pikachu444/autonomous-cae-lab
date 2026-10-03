"""Independent standard-linear-solid reference and strict numerical verdicts.

Physical tensors use xx, yy, zz, xy, xz, yz with shear weight two.
No native library or generated-law code is used to construct the reference.
"""

from copy import deepcopy
import hashlib
import json
import math

__version__ = "1"
COMPONENTS = ["xx", "yy", "zz", "xy", "xz", "yz"]
SQRT2 = math.sqrt(2.)
MATERIAL_KEYS = ["equilibrium_bulk_modulus_mpa", "equilibrium_shear_modulus_mpa",
                 "branch_bulk_modulus_mpa", "branch_shear_modulus_mpa", "relaxation_time_s"]
NATIVE_PROPERTIES = ["EquilibriumBulkModulus", "EquilibriumShearModulus",
                     "BranchBulkModulus", "BranchShearModulus", "RelaxationTime"]
FIXED_LIMITS = {"stress_absolute_mpa": 1e-10, "stress_relative": 1e-8,
                "tangent_relative": 1e-8, "energy_absolute_mpa": 1e-12,
                "energy_relative": 1e-8, "finite_difference_steps": [1e-7, 1e-8, 1e-9]}
PENDING = ["model_qualification", "material_qualification", "physical_validation",
           "static_strength", "fatigue_durability", "solver_coupling",
           "corporate_license_approval", "corporate_security_approval"]


def number(value, label):
    if type(value) not in (int, float):
        raise ValueError(f"{label} requires a finite number, never a boolean")
    try:
        value = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{label} must be representable") from exc
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def keys(value, names, label):
    if not isinstance(value, dict) or set(value) != set(names):
        raise ValueError(f"{label} requires exactly {sorted(names)}")


def vector(value, size=6, label="Tensor"):
    if not isinstance(value, list) or len(value) != size:
        raise ValueError(f"{label} requires {size} complete components")
    return [number(item, label) for item in value]


def matrix(value, label="Tangent"):
    if not isinstance(value, list) or len(value) != 6:
        raise ValueError(f"{label} requires six complete rows")
    return [vector(row, label=label) for row in value]


def state_hash(state):
    return hashlib.sha256(json.dumps(state, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def to_kelvin(value):
    v = vector(value)
    return v[:3] + [SQRT2 * item for item in v[3:]]


def from_kelvin(value):
    v = vector(value)
    return v[:3] + [item / SQRT2 for item in v[3:]]


def contraction(left, right):
    a, b = vector(left), vector(right)
    return _sum(x * y * (1 if i < 3 else 2) for i, (x, y) in enumerate(zip(a, b)))


def _sum(values):
    try:
        return number(math.fsum(values), "Tensor sum")
    except (OverflowError, ValueError) as exc:
        raise ValueError("Tensor result must be finite and representable") from exc


def _trace_deviator(value):
    v = vector(value)
    trace = _sum(v[:3])
    # Pairwise differences retain exactly zero for bit-identical hydrostatics.
    dev = [_sum((v[i] - v[(i + 1) % 3], v[i] - v[(i + 2) % 3])) / 3 for i in range(3)] + v[3:]
    return trace, vector(dev)


def stiffness(strain, bulk, shear):
    trace, dev = _trace_deviator(strain)
    return vector([_sum((bulk * trace, 2 * shear * x)) for x in dev[:3]] + [2 * shear * x for x in dev[3:]])


def compliance(stress, bulk, shear):
    trace, dev = _trace_deviator(stress)
    return vector([_sum((trace / (9 * bulk), x / (2 * shear))) for x in dev[:3]] + [x / (2 * shear) for x in dev[3:]])


def tangent(bulk, shear):
    return matrix([[(bulk - 2 * shear / 3 if i < 3 and j < 3 else 0.) + (2 * shear if i == j else 0.)
                    for j in range(6)] for i in range(6)])


def _quadratic(value, bulk, shear, *, inverse=False):
    trace, dev = _trace_deviator(value)
    squares = _sum(x * x * (1 if i < 3 else 2) for i, x in enumerate(dev))
    return _sum((trace * trace / (9 * bulk), squares / (2 * shear))) if inverse else _sum((bulk * trace * trace, 2 * shear * squares))


def _horner(coefficients, argument):
    value = coefficients[-1]
    for coefficient in reversed(coefficients[:-1]):
        value = coefficient + argument * value
    return value


def _coefficients(x):
    """Equivalent kernels; 1/8 is an evaluation switch, not a time cutoff."""
    if x == 0.:
        return 1., 1., .5, 0., .5, 0.
    a, A = math.exp(-x), -math.expm1(-2 * x) / 2
    if x <= 1 / 8:
        f = _horner([(-1) ** n / math.factorial(n + 1) for n in range(18)], x)
        g = _horner([(-1) ** n / math.factorial(n + 2) for n in range(18)], x)
        beta = _horner([1/2, -1/24, 1/240, -17/40320, 31/725760,
                       -691/159667200, 5461/12454041600, -929569/20922789888000], x * x)
        delta = x * _horner([1/12, -1/120, 17/20160, -31/362880,
                            691/79833600, -5461/6227020800, 929569/10461394944000,
                            -3202291/355687428096000], x * x)
    else:
        f = -math.expm1(-x) / x
        g = (1 - f) / x
        half = math.tanh(x / 2)
        beta = half / x
        delta = (x - 2 * half) / x / x
    return tuple(number(v, "Constitutive coefficient") for v in (a, f, g, A, beta, delta))


def validate_settings(settings):
    keys(settings, {"case", "material", "temperature_k", "history", "limits"}, "Settings")
    if settings["case"] != "single_branch_maxwell":
        raise ValueError("Only the trusted single_branch_maxwell infinitesimal 3D law is supported")
    keys(settings["material"], MATERIAL_KEYS, "Material")
    material = {key: number(settings["material"][key], key) for key in MATERIAL_KEYS}
    for key, value in material.items():
        upper = 1e6 if key == "relaxation_time_s" else 1e9
        if not 1e-6 <= value <= upper:
            raise ValueError(f"{key} must be in [1e-6,{upper}] in its declared unit")
    temperature = number(settings["temperature_k"], "Temperature")
    if not 0 < temperature <= 5000:
        raise ValueError("Temperature must be in (0,5000] K")
    keys(settings["limits"], FIXED_LIMITS, "Limits")
    for key, fixed in FIXED_LIMITS.items():
        actual = vector(settings["limits"][key], 3, key) if isinstance(fixed, list) else number(settings["limits"][key], key)
        if actual != fixed:
            raise ValueError(f"{key} is frozen before native execution")
    history = settings["history"]
    if not isinstance(history, list) or not 2 <= len(history) <= 32:
        raise ValueError("History must contain 2 through 32 ordered states")
    normalized = []
    for index, entry in enumerate(history):
        keys(entry, {"time_s", "strain"}, f"History {index}")
        time, strain = number(entry["time_s"], "Time"), vector(entry["strain"])
        if not 0 <= time <= 1e6 or any(abs(x) > .01 for x in strain):
            raise ValueError("History requires [0,1e6] s and physical strain components in [-0.01,0.01]")
        if index and time <= normalized[-1]["time_s"]:
            raise ValueError("Times must increase strictly; zero dt is forbidden")
        normalized.append({"time_s": time, "strain": strain})
    if normalized[0] != {"time_s": 0., "strain": [0.] * 6}:
        raise ValueError("Initial time/strain/stress/branch stress/energies must all be zero")
    return {"case": settings["case"], "material": material, "temperature_k": temperature,
            "history": normalized, "limits": deepcopy(FIXED_LIMITS)}


def canonical_settings(*, refined=False, relaxation_time_s=1.):
    times = [0., .2, 1., 1.2, 2., 2.2, 3., 3.2, 4.]
    amplitudes = [0., 1., 1., 0., 0., -.5, -.5, 0., 0.]
    direction = [.001, -.0002, .0003, .0004, -.0003, .0002]
    if refined:
        times = [x for i, t in enumerate(times[:-1]) for x in (t, (t + times[i + 1]) / 2)] + [times[-1]]
        amplitudes = [x for i, a in enumerate(amplitudes[:-1]) for x in (a, (a + amplitudes[i + 1]) / 2)] + [amplitudes[-1]]
    return validate_settings({"case": "single_branch_maxwell", "material": dict(zip(MATERIAL_KEYS,
        [1000., 500., 2000., 1000., relaxation_time_s])), "temperature_k": 293.15,
        "history": [{"time_s": t, "strain": [a * e for e in direction]} for t, a in zip(times, amplitudes)],
        "limits": deepcopy(FIXED_LIMITS)})


def increment(material, strain_old, strain_next, q_old, dt, *, _validated_history=False):
    """Exact exponential ramp step; all arguments are independent physical tensors."""
    e0, e1, q0 = vector(strain_old), vector(strain_next), vector(q_old)
    dt = number(dt, "Delta t")
    if dt <= 0:
        raise ValueError("Delta t must be positive")
    k0, g0, k1, g1, tau = (number(material[key], key) for key in MATERIAL_KEYS)
    if min(k0, g0, k1, g1, tau) <= 0:
        raise ValueError("Every modulus and relaxation time must be positive")
    x = number(dt / tau, "Dimensionless increment")
    if x == 0. and (not _validated_history or dt > 1e6 or
            not all(1e-6 <= m <= 1e9 for m in (k0, g0, k1, g1)) or not 1e-6 <= tau <= 1e6 or
            any(abs(v) > .01 for v in (*e0, *e1)) or math.hypot(*to_kelvin(q0)) > 5.58e9):
        raise ValueError("Underflowed ratio requires the bounded validated causal-history limit")
    a, f, g, A, beta, delta = _coefficients(x)
    de = vector([y - z for y, z in zip(e1, e0)])
    z = stiffness(de, k1, g1)
    q1 = vector([_sum((a * old, f * change)) for old, change in zip(q0, z)])
    c0e0, c0e1 = stiffness(e0, k0, g0), stiffness(e1, k0, g0)
    square = vector([_sum((old, beta * change)) for old, change in zip(q0, z)])
    dD = _sum((A * _quadratic(square, k1, g1, inverse=True), delta * _quadratic(z, k1, g1, inverse=True)))
    dW = _sum((.5 * contraction(vector([_sum((v0, v1)) for v0, v1 in zip(c0e0, c0e1)]), de),
               f * contraction(q0, de), g * contraction(z, de)))
    psi = .5 * _sum((_quadratic(e1, k0, g0), _quadratic(q1, k1, g1, inverse=True)))
    sigma = vector([_sum((v, q)) for v, q in zip(c0e1, q1)])
    return {"branch_stress_physical_mpa": q1, "stress_physical_mpa": sigma,
            "stored_energy_mpa": psi, "dissipation_increment_mpa": dD,
            "work_increment_mpa": dW, "tangent_kelvin_mpa": tangent(k0 + f * k1, g0 + f * g1),
            "decay": a, "ramp_factor": f}


def analytical_reference(settings):
    settings = validate_settings(settings)
    states = [{"time_s": 0., "strain_physical": [0.] * 6, "gradients_kelvin": [0.] * 6,
               "stress_physical_mpa": [0.] * 6, "stress_kelvin_mpa": [0.] * 6,
               "branch_stress_physical_mpa": [0.] * 6, "branch_stress_kelvin_mpa": [0.] * 6,
               "stored_energy_mpa": 0., "dissipated_energy_mpa": 0., "work_mpa": 0.}]
    dissipations, works = [], []
    for previous, entry in zip(settings["history"], settings["history"][1:]):
        last = states[-1]
        step = increment(settings["material"], previous["strain"], entry["strain"],
                         last["branch_stress_physical_mpa"], entry["time_s"] - previous["time_s"],
                         _validated_history=True)
        dissipations.append(step["dissipation_increment_mpa"])
        works.append(step["work_increment_mpa"])
        states.append({"time_s": entry["time_s"], "strain_physical": list(entry["strain"]),
            "gradients_kelvin": to_kelvin(entry["strain"]), "stress_physical_mpa": step["stress_physical_mpa"],
            "stress_kelvin_mpa": to_kelvin(step["stress_physical_mpa"]),
            "branch_stress_physical_mpa": step["branch_stress_physical_mpa"],
            "branch_stress_kelvin_mpa": to_kelvin(step["branch_stress_physical_mpa"]),
            "stored_energy_mpa": step["stored_energy_mpa"],
            "dissipated_energy_mpa": _sum(dissipations),
            "work_mpa": _sum(works),
            "tangent_kelvin_mpa": step["tangent_kelvin_mpa"],
            "dt_s": entry["time_s"] - previous["time_s"]})
    return {"states": states, "energy_unit": "MPa = MJ/m^3 per reference volume",
            "reference_kind": "Independent exact-exponential standard-linear-solid Python law",
            "scope": "Synthetic constitutive benchmark; no measured-material or solver coupling qualification"}


def model_declaration(settings):
    settings = validate_settings(settings)
    return {"model": {"geometry": None, "mesh": None, "materials": [{"id": "synthetic-single-branch-maxwell",
        "law": "standard_linear_solid", **deepcopy(settings["material"]), "modulus_unit": "MPa",
        "time_unit": "s", "source_kind": "SYNTHETIC_REFERENCE", "qualified": False}]},
        "boundary_conditions": [],
        "initial_conditions": [{"type": "strain", "value": [0.] * 6, "unit": "1"},
                               {"type": "stress", "value": [0.] * 6, "unit": "MPa"},
                               {"type": "branch_stress", "value": [0.] * 6, "unit": "MPa"},
                               {"type": "stored_energy", "value": 0., "unit": "MPa"},
                               {"type": "dissipated_energy", "value": 0., "unit": "MPa"},
                               {"type": "temperature", "value": settings["temperature_k"], "unit": "K"}],
        "loads": [{"type": "prescribed_strain_history", "strain_measure": "infinitesimal",
                   "convention": "physical_tensor", "components": list(COMPONENTS), "unit": "1", "time_unit": "s",
                   "history": deepcopy(settings["history"]), "interpolation": "piecewise_linear"}],
        "outputs": {"fields": [{"name": name, "unit": unit, "components": list(COMPONENTS)}
                               for name, unit in (("stress", "MPa"), ("branch_stress", "MPa"))] +
                              [{"name": "tangent_kelvin", "unit": "MPa", "shape": [6, 6]}],
                    "history": [{"name": name, "unit": "MPa"} for name in
                                ("stress_physical", "branch_stress_physical", "native_stored_energy", "native_dissipated_energy")]},
        "scope": "Synthetic single-branch infinitesimal viscoelastic point, no spatial solver/physical qualification"}


def _error(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


def _flat(a):
    return [x for row in a for x in row]


def _observation(row, label, *, has_tangent=False):
    if not isinstance(row, dict):
        raise ValueError(f"{label} requires complete observations")
    for name in ("gradients_kelvin", "strain_physical", "stress_kelvin_mpa", "stress_physical_mpa",
                 "branch_stress_kelvin_mpa", "branch_stress_physical_mpa"):
        vector(row.get(name), label=label + "." + name)
    for name in ("stored_energy_mpa", "dissipated_energy_mpa"):
        number(row.get(name), label + "." + name)
    number(row.get("time_s"), label + ".time")
    if has_tangent:
        matrix(row.get("tangent_kelvin_mpa"), label + ".tangent")


def _buffers(state, properties, temperature, label):
    keys(state, {"gradients_kelvin", "stress_kelvin_mpa", "internal_state_variables", "stored_energies",
                 "dissipated_energies", "material_properties", "external_state_variables", "shapes"}, label)
    for name in ("gradients_kelvin", "stress_kelvin_mpa", "internal_state_variables"):
        vector(state[name], label=label + "." + name)
    for name in ("stored_energies", "dissipated_energies"):
        vector(state[name], 1, label + "." + name)
    keys(state["material_properties"], NATIVE_PROPERTIES, label + ".properties")
    for name in NATIVE_PROPERTIES:
        vector(state["material_properties"][name], 1, label + "." + name)
    keys(state["external_state_variables"], {"Temperature"}, label + ".external")
    vector(state["external_state_variables"]["Temperature"], 1, label + ".Temperature")
    expected_shapes = {"gradients_kelvin": [1, 6], "stress_kelvin_mpa": [1, 6],
                       "internal_state_variables": [1, 6], "stored_energies": [1], "dissipated_energies": [1]}
    if state["shapes"] != expected_shapes:
        raise ValueError(f"{label} native buffer shape/stride is incomplete")
    return (state["material_properties"] == {key: [value] for key, value in properties.items()} and
            state["external_state_variables"] == {"Temperature": [temperature]})


def _manager(value, properties, temperature, label):
    keys(value, {"s0", "s1", "tangent_cache_kelvin_mpa", "dt_s", "metadata"}, label)
    ok = all([_buffers(value[name], properties, temperature, label + "." + name) for name in ("s0", "s1")])
    matrix(value["tangent_cache_kelvin_mpa"], label + ".cache")
    number(value["dt_s"], label + ".dt")
    expected = {"tangent_cache_shape": [1, 6, 6], "native_dtype": "float64", "integration_points": 1, "gradient_stride": 6, "force_stride": 6, "isv_stride": 6,
                "property_storage": "EXTERNAL_STORAGE_owned_arrays", "temperature_storage": "EXTERNAL_STORAGE_owned_array",
                "computes_stored_energy": True, "computes_dissipated_energy": True,
                "speed_of_sound": "NOT_REQUESTED", "native_copy_policy": "fresh_independent_full_buffers"}
    if value["metadata"] != expected:
        raise ValueError(f"{label} native state metadata/capability is incomplete")
    return ok


def _containers(value):
    """Mutable snapshot identities, separate from canonical content hashes."""
    if isinstance(value, dict):
        return [id(value), *(item for child in value.values() for item in _containers(child))]
    if isinstance(value, list):
        return [id(value), *(item for child in value for item in _containers(child))]
    return []


MTEST_LIMITS = {"substep_limit": 1, "iteration_limit": 10,
                "strain_epsilon": 1e-14, "stress_epsilon_mpa": 1e-10}
MTEST_COMPONENTS = ["EXX", "EYY", "EZZ", "EXY", "EXZ", "EYZ"]


def _mtest_imposed_history(settings, mtest):
    """Check what was imposed separately from the driver's actual solution."""
    for name, fixed in MTEST_LIMITS.items():
        value = mtest.get(name)
        if type(value) is not type(fixed) or value != fixed:
            raise ValueError("Exact predeclared MTest epsilon/iteration/substep limits are required")
    expected = [{"time_s": entry["time_s"], "gradients_kelvin": to_kelvin(entry["strain"])}
                for entry in settings["history"]]
    imposed = mtest.get("imposed_history")
    if not isinstance(imposed, list) or len(imposed) != len(expected):
        raise ValueError("Complete actual imposed MTest history is required")
    for entry in imposed:
        keys(entry, {"time_s", "gradients_kelvin"}, "MTest imposed entry")
        number(entry["time_s"], "MTest imposed time")
        vector(entry["gradients_kelvin"], label="MTest imposed Kelvin gradient")
    if (mtest.get("imposed_components") != MTEST_COMPONENTS or
            mtest.get("imposed_interpolation") != "piecewise_linear" or
            mtest.get("imposed_history") != expected):
        raise ValueError("Exact actual imposed MTest Kelvin history/ordering is required")
    return expected


def assess(settings, raw):
    settings = validate_settings(settings)
    reference = analytical_reference(settings)
    if not isinstance(raw, dict) or not isinstance(raw.get("mgis"), dict) or not isinstance(raw.get("mtest"), dict):
        raise ValueError("Complete actual MGIS and MTest drivers are mandatory")
    descriptor = raw.get("behaviour_description")
    if (not isinstance(descriptor, dict) or descriptor.get("computes_stored_energy") is not True or
            descriptor.get("computes_dissipated_energy") is not True or
            descriptor.get("internal_state_variables") != ["BranchStress"] or
            descriptor.get("internal_state_variable_sizes") != [6] or
            descriptor.get("material_properties") != NATIVE_PROPERTIES or
            descriptor.get("external_state_variables") != ["Temperature"]):
        raise ValueError("Native six-component branch stress and both native energy descriptors are required")
    mgis, mtest = raw["mgis"], raw["mtest"]
    steps, states = mgis.get("steps"), mtest.get("states")
    if (not isinstance(steps, list) or len(steps) != len(settings["history"]) - 1 or
            not isinstance(states, list) or len(states) != len(settings["history"])):
        raise ValueError("Exact ordered complete MGIS/MTest history counts are mandatory")
    props = dict(zip(NATIVE_PROPERTIES, (settings["material"][key] for key in MATERIAL_KEYS)))
    flags = dict.fromkeys(("reliable_integrations", "native_tensor_mapping", "immutable_full_probe_state",
                          "native_driver_continuity", "exact_ordered_history", "native_energy_table"), True)
    seen_snapshots = set()

    def checked_manager(value, label):
        flags["immutable_full_probe_state"] &= _manager(value, props, settings["temperature_k"], label)
        containers = _containers(value)
        flags["immutable_full_probe_state"] &= (len(containers) == len(set(containers)) and
                                                not seen_snapshots.intersection(containers))
        seen_snapshots.update(containers)
        return value

    library = raw.get("library_sha256")
    if not isinstance(library, str) or len(library) != 64:
        raise ValueError("Actual generated binary hash is missing")
    flags["native_driver_continuity"] &= mgis.get("library_sha256") == mtest.get("library_sha256") == library
    for driver in (mgis, mtest):
        flags["native_driver_continuity"] &= driver.get("material_properties") == props and driver.get("external_state_variables") == {"Temperature": settings["temperature_k"]}
    imposed_history = _mtest_imposed_history(settings, mtest)
    table = mtest.get("native_output_table")
    if (not isinstance(table, dict) or table.get("column_count") != 21 or table.get("stored_energy_column") != 20 or
            table.get("dissipated_energy_column") != 21 or not isinstance(table.get("sha256"), str) or
            len(table["sha256"]) != 64 or table.get("rows") != len(states)):
        raise ValueError("Strict actual MTest energy output table identity is required")
    initial = mgis.get("initial")
    _observation(initial, "MGIS initial")
    baseline = checked_manager(mgis.get("initial_manager"), "Initial manager")
    flags["immutable_full_probe_state"] &= baseline["s0"] == baseline["s1"]
    for name in ("gradients_kelvin", "stress_kelvin_mpa", "internal_state_variables", "stored_energies", "dissipated_energies"):
        flags["immutable_full_probe_state"] &= all(x == 0. for x in baseline["s0"][name])
    flags["immutable_full_probe_state"] &= _flat(baseline["tangent_cache_kelvin_mpa"]) == [0.] * 36 and baseline["dt_s"] == 0.
    observations = [initial]
    fd_errors = {h: {"reported": [], "reference": []} for h in FIXED_LIMITS["finite_difference_steps"]}
    tangent_errors = []
    probe_errors = dict.fromkeys(("probe_stress", "probe_branch", "probe_stored_energy", "probe_dissipated_energy"), 0.)
    previous = baseline
    for index, step in enumerate(steps, 1):
        _observation(step, f"MGIS step {index}", has_tangent=True)
        expected = reference["states"][index]
        current = checked_manager(step.get("initial_manager"), "Nominal baseline")
        flags["immutable_full_probe_state"] &= (all(current[key] == previous[key] for key in previous if key != "dt_s") and
            current["dt_s"] == expected["dt_s"] and step.get("initial_state_sha256") == state_hash(current))
        before, after = step.get("nominal_before_probes"), step.get("nominal_after_probes")
        for value, label in ((before, "Before probes"), (after, "After probes")):
            checked_manager(value, label)
        committed = checked_manager(step.get("nominal_after_update"), "Nominal committed snapshot")
        committed_hash = step.get("nominal_after_update_sha256")
        if (not isinstance(committed_hash, str) or len(committed_hash) != 64 or
                any(c not in "0123456789abcdef" for c in committed_hash)):
            raise ValueError("Nominal committed hash requires a canonical SHA256")
        # The actual MGIS update clears K before copying every s1 buffer to s0.
        # Preserve the original tangent observation; never invent or restore K.
        flags["immutable_full_probe_state"] &= (committed["s0"] == committed["s1"] == after["s1"] and
            all(committed[key] == after[key] for key in ("dt_s", "metadata")) and
            _flat(committed["tangent_cache_kelvin_mpa"]) == [0.] * 36 and
            committed_hash == state_hash(committed))
        end = after["s1"]
        flags["immutable_full_probe_state"] &= (before == after and after["s0"] == current["s0"] and
            after["dt_s"] == expected["dt_s"] and after["tangent_cache_kelvin_mpa"] == step["tangent_kelvin_mpa"] and
            end["gradients_kelvin"] == step["gradients_kelvin"] and end["stress_kelvin_mpa"] == step["stress_kelvin_mpa"] and
            end["internal_state_variables"] == step["branch_stress_kelvin_mpa"] and
            end["stored_energies"] == [step["stored_energy_mpa"]] and end["dissipated_energies"] == [step["dissipated_energy_mpa"]])
        flags["exact_ordered_history"] &= step["time_s"] == expected["time_s"]
        if type(step.get("integration_return")) is not int:
            raise ValueError("Actual nominal reliable return must be an integer")
        flags["reliable_integrations"] &= step["integration_return"] == 1
        number(step.get("time_step_increase_factor"), "Nominal dt factor")
        if not isinstance(step.get("error_message"), str):
            raise ValueError("Actual integration diagnostic is missing")
        scale = max(abs(x) for x in _flat(expected["tangent_kelvin_mpa"]))
        tangent_errors.append(_error(_flat(step["tangent_kelvin_mpa"]), _flat(expected["tangent_kelvin_mpa"])) / scale)
        fds = step.get("finite_differences")
        if not isinstance(fds, list) or len(fds) != 3:
            raise ValueError("Every increment requires every configured FD h")
        if [fd.get("h") for fd in fds] != FIXED_LIMITS["finite_difference_steps"]:
            raise ValueError("FD h order/count differs from the frozen contract")
        for fd in fds:
            h = number(fd.get("h"), "FD h")
            observed_matrix = matrix(fd.get("tangent_kelvin_mpa"), "FD tangent")
            probes = fd.get("probes")
            if not isinstance(probes, list) or len(probes) != 12:
                raise ValueError("Every h requires all six central-FD column pairs")
            if [(probe.get("column"), probe.get("sign")) for probe in probes] != [(c, s) for c in range(6) for s in (-1, 1)]:
                raise ValueError("All ordered unique FD columns/signs are required")
            by_column = {}
            for probe in probes:
                if type(probe.get("column")) is not int or type(probe.get("sign")) is not int:
                    raise ValueError("FD column and sign must be integers, never booleans")
                _observation(probe, "FD probe")
                restored = checked_manager(probe.get("initial_manager"), "FD baseline")
                flags["immutable_full_probe_state"] &= restored == current and probe.get("initial_state_sha256") == state_hash(current)
                if type(probe.get("integration_return")) is not int:
                    raise ValueError("Every signed probe needs its actual integer return")
                flags["reliable_integrations"] &= probe["integration_return"] == 1
                number(probe.get("time_step_increase_factor"), "Probe dt factor")
                if not isinstance(probe.get("error_message"), str):
                    raise ValueError("Probe diagnostics are missing")
                perturbed = list(step["gradients_kelvin"])
                perturbed[probe["column"]] += probe["sign"] * h
                flags["immutable_full_probe_state"] &= probe["gradients_kelvin"] == perturbed
                flags["native_tensor_mapping"] &= (_error(probe["strain_physical"], from_kelvin(probe["gradients_kelvin"])) <= 1e-15 and
                    _error(probe["stress_physical_mpa"], from_kelvin(probe["stress_kelvin_mpa"])) <= 1e-12 and
                    _error(probe["branch_stress_physical_mpa"], from_kelvin(probe["branch_stress_kelvin_mpa"])) <= 1e-12)
                final = checked_manager(probe.get("final_manager"), "FD final")
                flags["immutable_full_probe_state"] &= (final["s0"] == current["s0"] and final["dt_s"] == expected["dt_s"] and
                    probe.get("final_state_sha256") == state_hash(final) and
                    final["s1"]["gradients_kelvin"] == probe["gradients_kelvin"] and
                    final["s1"]["stress_kelvin_mpa"] == probe["stress_kelvin_mpa"] and
                    final["s1"]["internal_state_variables"] == probe["branch_stress_kelvin_mpa"] and
                    final["s1"]["stored_energies"] == [probe["stored_energy_mpa"]] and
                    final["s1"]["dissipated_energies"] == [probe["dissipated_energy_mpa"]] and
                    final["tangent_cache_kelvin_mpa"] == step["tangent_kelvin_mpa"])
                flags["exact_ordered_history"] &= probe["time_s"] == expected["time_s"]
                prior_reference = reference["states"][index - 1]
                probe_reference = increment(settings["material"], prior_reference["strain_physical"],
                    from_kelvin(perturbed), prior_reference["branch_stress_physical_mpa"], expected["dt_s"])
                probe_errors["probe_stress"] = max(probe_errors["probe_stress"],
                    _error(probe["stress_kelvin_mpa"], to_kelvin(probe_reference["stress_physical_mpa"])))
                probe_errors["probe_branch"] = max(probe_errors["probe_branch"],
                    _error(probe["branch_stress_kelvin_mpa"], to_kelvin(probe_reference["branch_stress_physical_mpa"])))
                probe_errors["probe_stored_energy"] = max(probe_errors["probe_stored_energy"],
                    abs(probe["stored_energy_mpa"] - probe_reference["stored_energy_mpa"]))
                probe_errors["probe_dissipated_energy"] = max(probe_errors["probe_dissipated_energy"],
                    abs(probe["dissipated_energy_mpa"] - prior_reference["dissipated_energy_mpa"] -
                        probe_reference["dissipation_increment_mpa"]))
                by_column[probe["column"], probe["sign"]] = probe
            recomputed = [[(by_column[j, 1]["stress_kelvin_mpa"][i] - by_column[j, -1]["stress_kelvin_mpa"][i]) / (2 * h)
                           for j in range(6)] for i in range(6)]
            flags["immutable_full_probe_state"] &= observed_matrix == recomputed
            fd_errors[h]["reported"].append(_error(_flat(recomputed), _flat(step["tangent_kelvin_mpa"])) / scale)
            fd_errors[h]["reference"].append(_error(_flat(recomputed), _flat(expected["tangent_kelvin_mpa"])) / scale)
        observations.append(step)
        previous = committed
    errors = dict.fromkeys(("stress_physical", "stress_kelvin", "branch_physical", "branch_kelvin",
                            "cross_driver_stress", "cross_driver_branch", "stored_energy", "dissipated_energy",
                            "prefix_work_closure"), 0.)
    errors.update(probe_errors)
    observed_energies = {"mgis": [], "mtest": []}
    positive, monotonic = True, True
    for index, (observed, other, expected) in enumerate(zip(observations, states, reference["states"])):
        _observation(other, "MTest state")
        if index == 0:
            for row in (observed, other):
                flags["exact_ordered_history"] &= all(row[key] == [0.] * 6 for key in ("gradients_kelvin", "strain_physical", "stress_kelvin_mpa", "stress_physical_mpa", "branch_stress_kelvin_mpa", "branch_stress_physical_mpa")) and row["stored_energy_mpa"] == row["dissipated_energy_mpa"] == 0.
        properties = vector(other.get("properties_native"), 5, "MTest native material array")
        external = vector(other.get("external_state_variables_native"), 1, "MTest native temperature")
        isv = vector(other.get("internal_state_variables"), label="MTest native q")
        if type(other.get("substeps")) is not int or type(other.get("iterations")) is not int:
            raise ValueError("MTest actual step/iteration counts are required")
        flags["native_driver_continuity"] &= (other["substeps"] == 0 and
            0 <= other["iterations"] <= MTEST_LIMITS["iteration_limit"] and isv == other["branch_stress_kelvin_mpa"])
        if index == 0:
            flags["native_driver_continuity"] &= other.get("state_phase") == "INITIAL_UNPREPARED" and properties == [0.] * 5 and external == [0.] and other["iterations"] == 0
        else:
            flags["native_driver_continuity"] &= other.get("state_phase") == "INTEGRATED" and properties == list(props.values()) and external == [settings["temperature_k"]]
        flags["exact_ordered_history"] &= observed["time_s"] == other["time_s"] == expected["time_s"]
        for driver_name, row in (("mgis", observed), ("mtest", other)):
            if driver_name == "mtest":
                # ImposedGradient solves actual e1 with strict residual < the
                # already declared strain epsilon. Never project that e1 onto
                # the input, or use it to replace the independent reference.
                mapping = (_error(row["gradients_kelvin"], imposed_history[index]["gradients_kelvin"]) <
                           MTEST_LIMITS["strain_epsilon"] and
                           _error(row["strain_physical"], from_kelvin(row["gradients_kelvin"])) <= 1e-15)
            else:
                mapping = (_error(row["gradients_kelvin"], expected["gradients_kelvin"]) <= 1e-15 and
                           _error(row["strain_physical"], expected["strain_physical"]) <= 1e-15)
            flags["native_tensor_mapping"] &= (mapping and
                _error(row["stress_physical_mpa"], from_kelvin(row["stress_kelvin_mpa"])) <= 1e-12 and
                _error(row["branch_stress_physical_mpa"], from_kelvin(row["branch_stress_kelvin_mpa"])) <= 1e-12)
            for metric, key in (("stress_physical", "stress_physical_mpa"), ("stress_kelvin", "stress_kelvin_mpa"),
                                ("branch_physical", "branch_stress_physical_mpa"), ("branch_kelvin", "branch_stress_kelvin_mpa")):
                errors[metric] = max(errors[metric], _error(row[key], expected[key]))
            for metric, key in (("stored_energy", "stored_energy_mpa"), ("dissipated_energy", "dissipated_energy_mpa")):
                errors[metric] = max(errors[metric], abs(row[key] - expected[key]))
            errors["prefix_work_closure"] = max(errors["prefix_work_closure"],
                abs(row["stored_energy_mpa"] + row["dissipated_energy_mpa"] - expected["work_mpa"]))
            observed_energies[driver_name].append([row["stored_energy_mpa"], row["dissipated_energy_mpa"]])
        errors["cross_driver_stress"] = max(errors["cross_driver_stress"], _error(observed["stress_kelvin_mpa"], other["stress_kelvin_mpa"]))
        errors["cross_driver_branch"] = max(errors["cross_driver_branch"], _error(observed["branch_stress_kelvin_mpa"], other["branch_stress_kelvin_mpa"]))
    stress_scale = max(1., *(abs(x) for row in reference["states"] for key in
        ("stress_physical_mpa", "stress_kelvin_mpa", "branch_stress_physical_mpa", "branch_stress_kelvin_mpa") for x in row[key]))
    energy_scale = max(1e-3, *(abs(row[key]) for row in reference["states"] for key in
        ("stored_energy_mpa", "dissipated_energy_mpa", "work_mpa")))
    stress_limit = FIXED_LIMITS["stress_absolute_mpa"] + FIXED_LIMITS["stress_relative"] * stress_scale
    energy_limit = FIXED_LIMITS["energy_absolute_mpa"] + FIXED_LIMITS["energy_relative"] * energy_scale
    for energies in observed_energies.values():
        positive &= all(psi >= -energy_limit for psi, _ in energies)
        monotonic &= energies[0][1] >= -energy_limit and all(b[1] >= a[1] - energy_limit for a, b in zip(energies, energies[1:]))
    checks = [{"code": name, "status": "PASS" if flag else "FAIL", "observed": flag, "expected": True}
              for name, flag in flags.items()]
    metrics = {}
    for name, error in errors.items():
        code = "max_" + name + "_error"
        limit = energy_limit if name in ("stored_energy", "dissipated_energy", "prefix_work_closure", "probe_stored_energy", "probe_dissipated_energy") else stress_limit
        metrics[code] = {"value": error, "unit": "MPa"}
        checks.append({"code": code, "status": "PASS" if error <= limit else "FAIL", "observed": error, "limit": limit})
    metrics["analytical_tangent_relative_error"] = {"value": max(tangent_errors), "unit": "1"}
    checks.append({"code": "analytical_tangent_relative_error", "status": "PASS" if max(tangent_errors) <= FIXED_LIMITS["tangent_relative"] else "FAIL",
                   "observed": max(tangent_errors), "limit": FIXED_LIMITS["tangent_relative"], "every_step_relative_error": tangent_errors})
    for h, values in fd_errors.items():
        error = max(*values["reported"], *values["reference"])
        name = "fd_tangent_relative_error_" + format(h, ".0e")
        metrics[name] = {"value": error, "unit": "1"}
        checks.append({"code": name, "status": "PASS" if error <= FIXED_LIMITS["tangent_relative"] else "FAIL",
            "observed": error, "limit": FIXED_LIMITS["tangent_relative"], "every_step_vs_reported": values["reported"],
            "every_step_vs_reference": values["reference"]})
    checks.extend({"code": name, "status": "PASS" if flag else "FAIL", "observed": flag, "limit": energy_limit}
                  for name, flag in (("native_stored_energy_nonnegative", positive), ("native_dissipation_nondecreasing", monotonic)))
    metrics.update({"stress_history": {"value": [r["stress_physical_mpa"] for r in observations], "unit": "MPa"},
                    "branch_stress_history": {"value": [r["branch_stress_physical_mpa"] for r in observations], "unit": "MPa"},
                    "native_energy_history": {"value": [observed_energies["mgis"], observed_energies["mtest"]], "unit": "MPa", "drivers": ["mgis", "mtest"], "components": ["stored", "dissipated"]},
                    "reference_work_history": {"value": [r["work_mpa"] for r in reference["states"]], "unit": "MPa"}})
    failed = [check["code"] for check in checks if check["status"] == "FAIL"]
    for metric in metrics.values():
        metric["valid"] = not failed
        if failed:
            metric["reason"] = "Viscoelastic numerical gates failed: " + ", ".join(failed)
    return {"checks": checks, "metrics": metrics, "pending_validations": list(PENDING), "reference": reference,
            "stress_scale_mpa": stress_scale, "stress_limit_mpa": stress_limit,
            "energy_scale_mpa": energy_scale, "energy_limit_mpa": energy_limit,
            "energy_method": "Actual native MGIS buffers and pinned MTest output table; reference-volume MPa=MJ/m^3"}


def compare_refinement(coarse_settings, coarse_raw, fine_settings, fine_raw):
    """Shared-time semigroup verdict; no step-size tangent/order claim."""
    coarse, fine = validate_settings(coarse_settings), validate_settings(fine_settings)
    for key in ("case", "material", "temperature_k", "limits"):
        if coarse[key] != fine[key]:
            raise ValueError("Refinement must preserve the declared material/temperature/limits")
    if len(fine["history"]) != 2 * len(coarse["history"]) - 1:
        raise ValueError("The declared midpoint refinement must retain every coarse state")
    for i, (a, b) in enumerate(zip(coarse["history"], coarse["history"][1:])):
        if fine["history"][2 * i] != a or fine["history"][2 * i + 1] != {
                "time_s": (a["time_s"] + b["time_s"]) / 2,
                "strain": [(x + y) / 2 for x, y in zip(a["strain"], b["strain"])]}:
            raise ValueError("Refinement changed the exact piecewise-linear strain history")
    if fine["history"][-1] != coarse["history"][-1]:
        raise ValueError("Refinement changed the endpoint")
    assessments = [assess(coarse, coarse_raw), assess(fine, fine_raw)]
    stress_limit = max(a["stress_limit_mpa"] for a in assessments)
    energy_limit = max(a["energy_limit_mpa"] for a in assessments)
    errors = dict.fromkeys(("stress", "branch_stress", "stored_energy", "dissipated_energy"), 0.)
    for driver in ("mgis", "mtest"):
        def rows(raw):
            return [raw["mgis"]["initial"], *raw["mgis"]["steps"]] if driver == "mgis" else raw["mtest"]["states"]
        small = {row["time_s"]: row for row in rows(fine_raw)}
        for observed in rows(coarse_raw):
            other = small[observed["time_s"]]
            for name, key in (("stress", "stress_kelvin_mpa"), ("branch_stress", "branch_stress_kelvin_mpa")):
                errors[name] = max(errors[name], _error(observed[key], other[key]))
            for name in ("stored_energy", "dissipated_energy"):
                errors[name] = max(errors[name], abs(observed[name + "_mpa"] - other[name + "_mpa"]))
    base_pass = all(c["status"] == "PASS" for a in assessments for c in a["checks"])
    checks = [{"code": "refinement_base_gates", "status": "PASS" if base_pass else "FAIL", "observed": base_pass}]
    for name, error in errors.items():
        limit = energy_limit if name.endswith("energy") else stress_limit
        checks.append({"code": "shared_time_" + name, "status": "PASS" if error <= limit else "FAIL",
                       "observed": error, "limit": limit, "unit": "MPa"})
    return {"status": "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL",
            "checks": checks, "shared_times_s": [row["time_s"] for row in coarse["history"]],
            "method": "Exact-exponential composition at declared shared times, both actual native drivers",
            "limitations": "Tangent uses each driver's own dt; no convergence order or physical qualification claim"}
