"""Independent isotropic Hooke reference and material-point numerical gates.

Physical tensor components are xx, yy, zz, xy, xz, yz, never engineering shear.
This module has no MFront, MGIS, MTest, NumPy or native-path dependency.
"""

from copy import deepcopy
import hashlib
import json
import math

__version__ = "1"
COMPONENTS = ["xx", "yy", "zz", "xy", "xz", "yz"]
SQRT2 = math.sqrt(2.0)
FIXED_LIMITS = {"stress_absolute_mpa": 1e-10, "stress_relative": 1e-8,
                "tangent_relative": 1e-8, "finite_difference_steps": [1e-7, 1e-8, 1e-9]}
PENDING = ["model_qualification", "material_qualification", "physical_validation",
           "static_strength", "fatigue_durability", "solver_coupling",
           "corporate_license_approval", "corporate_security_approval"]


def _number(value, label):
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite number, not a boolean")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _keys(value, required, label):
    if not isinstance(value, dict) or set(value) != set(required):
        raise ValueError(f"{label} requires exactly {sorted(required)}")


def _vector(value, size, label):
    if not isinstance(value, list) or len(value) != size:
        raise ValueError(f"{label} must contain exactly {size} components")
    return [_number(item, label) for item in value]


def _matrix(value, size, label):
    if not isinstance(value, list) or len(value) != size:
        raise ValueError(f"{label} requires {size} complete rows")
    return [_vector(row, size, label) for row in value]


def state_hash(state):
    return hashlib.sha256(json.dumps(state, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def to_kelvin(physical):
    vector = _vector(physical, 6, "Physical tensor")
    return vector[:3] + [SQRT2 * item for item in vector[3:]]


def from_kelvin(kelvin):
    vector = _vector(kelvin, 6, "Kelvin tensor")
    return vector[:3] + [item / SQRT2 for item in vector[3:]]


def validate_settings(settings):
    _keys(settings, {"case", "material", "temperature_k", "history", "limits"}, "Settings")
    if settings["case"] != "isotropic_small_strain":
        raise ValueError("Only the isotropic_small_strain material-point case is supported")
    _keys(settings["material"], {"youngs_modulus_mpa", "poisson_ratio"}, "Material")
    modulus = _number(settings["material"]["youngs_modulus_mpa"], "Young modulus")
    poisson = _number(settings["material"]["poisson_ratio"], "Poisson ratio")
    if not 0 < modulus <= 1e9 or not -1 < poisson < .5:
        raise ValueError("Require 0 < E <= 1e9 MPa and -1 < nu < 0.5")
    temperature = _number(settings["temperature_k"], "Temperature")
    if not 0 < temperature <= 5000:
        raise ValueError("Require 0 < temperature <= 5000 K; no temperature dependence is qualified")
    _keys(settings["limits"], FIXED_LIMITS, "Limits")
    limits = settings["limits"]
    for name in ("stress_absolute_mpa", "stress_relative", "tangent_relative"):
        if _number(limits[name], name) != FIXED_LIMITS[name]:
            raise ValueError(f"{name} is fixed at {FIXED_LIMITS[name]} before native execution")
    if _vector(limits["finite_difference_steps"], 3, "FD steps") != FIXED_LIMITS["finite_difference_steps"]:
        raise ValueError("All central FD steps are fixed at 1e-7, 1e-8, 1e-9")
    history = settings["history"]
    if not isinstance(history, list) or not 2 <= len(history) <= 32:
        raise ValueError("History requires 2 through 32 states")
    normalized = []
    for index, entry in enumerate(history):
        _keys(entry, {"time_s", "strain"}, f"History state {index}")
        time = _number(entry["time_s"], "Time")
        strain = _vector(entry["strain"], 6, "Physical tensor strain")
        if not 0 <= time <= 1e6 or any(abs(item) > .01 for item in strain):
            raise ValueError("Require times in [0,1e6] s and physical strain components in [-0.01,0.01]")
        if index and time <= normalized[-1]["time_s"]:
            raise ValueError("History times must increase strictly")
        normalized.append({"time_s": time, "strain": strain})
    if normalized[0] != {"time_s": 0.0, "strain": [0.0] * 6}:
        raise ValueError("History must start at t=0 with zero strain and zero initial stress")
    result = {"case": settings["case"], "material": {"youngs_modulus_mpa": modulus,
              "poisson_ratio": poisson}, "temperature_k": temperature, "history": normalized,
              "limits": deepcopy(FIXED_LIMITS)}
    # Finite inputs can still overflow near a singular Poisson ratio.
    lam, mu = _lame(result)
    if not all(math.isfinite(value) and value > 0 for value in (mu, lam + 2 * mu, 3 * lam + 2 * mu)):
        raise ValueError("The elastic coefficients must be representable and positive definite")
    return result


def canonical_settings():
    mixed = [.0008, -.0003, .0002, .00015, -.00025, .00035]
    strains = [[0.] * 6, [.001, 0., 0., 0., 0., 0.], [0., -.0007, 0., 0., 0., 0.],
               [0., 0., .0004, 0., 0., 0.], [0., 0., 0., .0003, 0., 0.],
               [0., 0., 0., 0., -.0002, 0.], [0., 0., 0., 0., 0., .0005],
               mixed, [-item for item in mixed], [0.] * 6, mixed, [0.] * 6]
    return {"case": "isotropic_small_strain", "material": {"youngs_modulus_mpa": 210000.,
            "poisson_ratio": .3}, "temperature_k": 293.15,
            "history": [{"time_s": float(i), "strain": list(strain)} for i, strain in enumerate(strains)],
            "limits": deepcopy(FIXED_LIMITS)}


def _lame(settings):
    modulus, poisson = (settings["material"][key] for key in ("youngs_modulus_mpa", "poisson_ratio"))
    return modulus * poisson / ((1 + poisson) * (1 - 2 * poisson)), modulus / (2 * (1 + poisson))


def analytical_reference(settings):
    settings = validate_settings(settings)
    lam, mu = _lame(settings)
    tangent = [[(lam if i < 3 and j < 3 else 0.) + (2 * mu if i == j else 0.)
                for j in range(6)] for i in range(6)]
    states = []
    for entry in settings["history"]:
        strain = entry["strain"]
        trace = math.fsum(strain[:3])
        stress = [lam * trace + 2 * mu * item for item in strain[:3]] + [2 * mu * item for item in strain[3:]]
        energy = .5 * math.fsum(a * b * (1 if i < 3 else 2) for i, (a, b) in enumerate(zip(stress, strain)))
        states.append({"time_s": entry["time_s"], "strain_physical": list(strain),
                       "gradients_kelvin": to_kelvin(strain), "stress_physical_mpa": stress,
                       "stress_kelvin_mpa": to_kelvin(stress), "energy_density_mpa": energy})
    return {"lambda_mpa": lam, "mu_mpa": mu, "tangent_kelvin_mpa": tangent,
            "component_order": list(COMPONENTS), "states": states,
            "source": "Independent Python Hooke law, not generated/native observations"}


def model_declaration(settings):
    settings = validate_settings(settings)
    return {"model": {"geometry": None, "mesh": None,
                      "materials": [{"id": "isotropic-elastic", "law": "isotropic_linear_elasticity",
                                     **settings["material"], "stress_unit": "MPa", "qualified": False}]},
            "boundary_conditions": [],
            "initial_conditions": [{"type": "strain", "value": [0.] * 6, "unit": "1"},
                                   {"type": "stress", "value": [0.] * 6, "unit": "MPa"},
                                   {"type": "temperature", "value": settings["temperature_k"], "unit": "K"}],
            "loads": [{"type": "prescribed_strain_history", "strain_measure": "infinitesimal",
                       "convention": "physical_tensor", "components": list(COMPONENTS),
                       "unit": "1", "time_unit": "s", "history": deepcopy(settings["history"])}],
            "outputs": {"fields": [{"name": "stress", "unit": "MPa", "components": list(COMPONENTS)},
                                   {"name": "tangent_kelvin", "unit": "MPa", "shape": [6, 6]}],
                        "history": [{"name": "stress_physical", "unit": "MPa"},
                                    {"name": "elastic_energy_density", "unit": "MPa"}]},
            "scope": "Constitutive material-point benchmark only; physical and solver coupling qualification UNKNOWN"}


def _max_error(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


def _flat(matrix):
    return [item for row in matrix for item in row]


def _state(state, settings, label):
    required = {"gradients_kelvin", "stress_kelvin_mpa", "internal_state_variables", "stored_energies",
                "dissipated_energies", "material_properties", "external_state_variables", "dt_s"}
    _keys(state, required, label)
    _vector(state["gradients_kelvin"], 6, label)
    _vector(state["stress_kelvin_mpa"], 6, label)
    for key in ("internal_state_variables", "stored_energies", "dissipated_energies"):
        if not isinstance(state[key], list):
            raise ValueError(f"{label}.{key} must be a complete list")
        for item in state[key]:
            _number(item, label)
    _keys(state["material_properties"], {"YoungModulus", "PoissonRatio"}, label)
    _keys(state["external_state_variables"], {"Temperature"}, label)
    for item in (*state["material_properties"].values(), *state["external_state_variables"].values()):
        _number(item, label)
    _number(state["dt_s"], label)
    return state


def _observation(observation, label, *, tangent=False):
    if not isinstance(observation, dict):
        raise ValueError(f"{label} must be a complete observation")
    for key in ("gradients_kelvin", "strain_physical", "stress_kelvin_mpa", "stress_physical_mpa"):
        _vector(observation.get(key), 6, label + "." + key)
    if tangent:
        _matrix(observation.get("tangent_kelvin_mpa"), 6, label + ".tangent")


def assess(settings, raw):
    """Malformed native observations raise; measured numerical failures stay numeric.

    State identity, driver continuity and every FD h/column are admission gates.
    Native energy buffers are retained but this example does not compute energy;
    observed energy below is explicitly postprocessed from measured stress.
    """
    settings = validate_settings(settings)
    reference = analytical_reference(settings)
    if not isinstance(raw, dict) or not isinstance(raw.get("mgis"), dict) or not isinstance(raw.get("mtest"), dict):
        raise ValueError("Complete MGIS and MTest outputs are required")
    mgis, mtest = raw["mgis"], raw["mtest"]
    steps = mgis.get("steps")
    mstates = mtest.get("states")
    if (not isinstance(steps, list) or len(steps) != len(settings["history"]) - 1 or
            not isinstance(mstates, list) or len(mstates) != len(settings["history"])):
        raise ValueError("Incomplete nominal or MTest history")
    initial = mgis.get("initial")
    _observation(initial, "MGIS initial")
    expected_properties = {"YoungModulus": settings["material"]["youngs_modulus_mpa"],
                           "PoissonRatio": settings["material"]["poisson_ratio"]}
    expected_external = {"Temperature": settings["temperature_k"]}
    flags = {name: True for name in ("reliable_integrations", "native_tensor_mapping", "immutable_probe_state",
                                    "driver_continuity", "nominal_history")}
    if not isinstance(mtest.get("library_sha256"), str) or not isinstance(mgis.get("library_sha256"), str):
        raise ValueError("Both drivers require their measured library hashes")
    flags["driver_continuity"] = (len(mgis["library_sha256"]) == 64 and
                                   mgis["library_sha256"] == mtest["library_sha256"] == raw.get("library_sha256"))
    flags["driver_continuity"] &= mtest.get("substep_limit") == 1
    for driver in (mgis, mtest):
        flags["driver_continuity"] &= (driver.get("material_properties") == expected_properties and
                                       driver.get("external_state_variables") == expected_external)
    previous = mgis.get("initial_state")
    _state(previous, settings, "Initial state")
    flags["nominal_history"] &= (previous["gradients_kelvin"] == [0.] * 6 and
                                  previous["stress_kelvin_mpa"] == [0.] * 6)
    observations, fd_errors, analytic_errors = [initial], {h: [] for h in FIXED_LIMITS["finite_difference_steps"]}, []
    fd_reported_errors = {h: [] for h in fd_errors}
    fd_reference_errors = {h: [] for h in fd_errors}
    for index, step in enumerate(steps, 1):
        _observation(step, f"MGIS step {index}", tangent=True)
        time = _number(step.get("time_s"), "Step time")
        flags["nominal_history"] &= time == settings["history"][index]["time_s"]
        baseline = _state(step.get("initial_state"), settings, "Step initial state")
        nominal_before = step.get("nominal_before_probes")
        nominal_after = step.get("nominal_after_probes")
        _state(nominal_before, settings, "Nominal before probes")
        _state(nominal_after, settings, "Nominal after probes")
        initial_after = _state(step.get("nominal_initial_after_probes"), settings, "Nominal initial after probes")
        dt = time - settings["history"][index - 1]["time_s"]
        flags["immutable_probe_state"] &= (all(baseline[key] == previous[key] for key in previous if key != "dt_s") and
            baseline["material_properties"] == expected_properties and baseline["external_state_variables"] == expected_external and
            baseline["dt_s"] == dt and nominal_before == nominal_after and
            baseline == initial_after and step.get("initial_state_unchanged") is True and
            step.get("initial_state_sha256") == state_hash(baseline) and
            nominal_after["gradients_kelvin"] == step["gradients_kelvin"] and
            nominal_after["stress_kelvin_mpa"] == step["stress_kelvin_mpa"])
        if type(step.get("integration_return")) is not int:
            raise ValueError("Every nominal integration requires an integer return code")
        flags["reliable_integrations"] &= step["integration_return"] == 1
        _number(step.get("time_step_increase_factor"), "Time-step factor")
        if not isinstance(step.get("error_message"), str):
            raise ValueError("Every integration must preserve its error message")
        analytic_errors.append(_max_error(_flat(step["tangent_kelvin_mpa"]), _flat(reference["tangent_kelvin_mpa"])))
        fds = step.get("finite_differences")
        if not isinstance(fds, list) or len(fds) != 3:
            raise ValueError("All three FD step sizes are required")
        seen_h = set()
        for fd in fds:
            if not isinstance(fd, dict):
                raise ValueError("Each FD step requires a complete observation mapping")
            h = _number(fd.get("h"), "FD h")
            if h not in fd_errors or h in seen_h:
                raise ValueError("Missing/duplicate/unconfigured FD step size")
            seen_h.add(h)
            matrix = _matrix(fd.get("tangent_kelvin_mpa"), 6, "FD tangent")
            probes = fd.get("probes")
            if not isinstance(probes, list) or len(probes) != 12:
                raise ValueError("Each h needs both signs of every one of six FD columns")
            by_column = {}
            for probe in probes:
                if not isinstance(probe, dict):
                    raise ValueError("Each signed FD probe must be a complete mapping")
                column, sign = probe.get("column"), probe.get("sign")
                if type(column) is not int or column not in range(6) or type(sign) is not int or sign not in (-1, 1):
                    raise ValueError("Invalid FD column/sign")
                if (column, sign) in by_column:
                    raise ValueError("Duplicate FD column/sign")
                _observation(probe, "FD probe")
                probe_initial = _state(probe.get("initial_state"), settings, "FD initial state")
                flags["immutable_probe_state"] &= (probe_initial == baseline and
                    probe.get("initial_state_sha256") == state_hash(baseline))
                if type(probe.get("integration_return")) is not int:
                    raise ValueError("Every FD integration requires its integer return code")
                flags["reliable_integrations"] &= probe["integration_return"] == 1
                _number(probe.get("time_step_increase_factor"), "FD time-step factor")
                if not isinstance(probe.get("error_message"), str):
                    raise ValueError("Every FD integration requires its error message")
                perturbed = list(step["gradients_kelvin"])
                perturbed[column] += sign * h
                flags["immutable_probe_state"] &= probe["gradients_kelvin"] == perturbed
                flags["native_tensor_mapping"] &= (_max_error(probe["strain_physical"], from_kelvin(probe["gradients_kelvin"])) <= 1e-15 and
                    _max_error(probe["stress_physical_mpa"], from_kelvin(probe["stress_kelvin_mpa"])) <= 1e-12)
                by_column[column, sign] = probe
            recomputed = [[(by_column[j, 1]["stress_kelvin_mpa"][i] - by_column[j, -1]["stress_kelvin_mpa"][i]) / (2 * h)
                           for j in range(6)] for i in range(6)]
            flags["immutable_probe_state"] &= matrix == recomputed
            fd_reported_errors[h].append(_max_error(_flat(matrix), _flat(step["tangent_kelvin_mpa"])))
            fd_reference_errors[h].append(_max_error(_flat(matrix), _flat(reference["tangent_kelvin_mpa"])))
            fd_errors[h].append(max(fd_reported_errors[h][-1], fd_reference_errors[h][-1]))
        observations.append(step)
        previous = nominal_after
    physical_errors, kelvin_errors, driver_errors, energy_errors, energies = [], [], [], [], []
    for index, (observation, other, expected) in enumerate(zip(observations, mstates, reference["states"])):
        _observation(other, "MTest state")
        _vector(other.get("properties_native"), 2, "MTest native material properties")
        _vector(other.get("external_state_variables_native"), 1, "MTest native external state")
        if type(other.get("substeps")) is not int or type(other.get("iterations")) is not int:
            raise ValueError("MTest must preserve actual substep and iteration counts")
        # MTest's public initializer allocates zero property/ESV buffers and
        # initializes strain/stress; prepare fills E/nu/T for each real step.
        # Retain those t=0 values with their exact phase, never replace them or
        # manufacture a zero-dt integration. Every actual increment is strict.
        if index == 0:
            flags["driver_continuity"] &= (other.get("state_phase") == "INITIAL_UNPREPARED" and
                other["properties_native"] == [0., 0.] and other["external_state_variables_native"] == [0.] and
                other["substeps"] == 0 and other["iterations"] == 0)
        else:
            flags["driver_continuity"] &= (other.get("state_phase") == "INTEGRATED" and
                other["properties_native"] == list(expected_properties.values()) and
                other["external_state_variables_native"] == [settings["temperature_k"]] and other["substeps"] == 0)
        flags["nominal_history"] &= (_number(observation.get("time_s"), "MGIS time") == expected["time_s"] and
                                      _number(other.get("time_s"), "MTest time") == expected["time_s"])
        for row in (observation, other):
            flags["native_tensor_mapping"] &= (_max_error(row["gradients_kelvin"], expected["gradients_kelvin"]) <= 1e-15 and
                _max_error(row["strain_physical"], expected["strain_physical"]) <= 1e-15 and
                _max_error(row["stress_physical_mpa"], from_kelvin(row["stress_kelvin_mpa"])) <= 1e-12)
            physical_errors.append(_max_error(row["stress_physical_mpa"], expected["stress_physical_mpa"]))
            kelvin_errors.append(_max_error(row["stress_kelvin_mpa"], expected["stress_kelvin_mpa"]))
        driver_errors.append(_max_error(observation["stress_kelvin_mpa"], other["stress_kelvin_mpa"]))
        energy = .5 * math.fsum(s * e * (1 if i < 3 else 2) for i, (s, e) in enumerate(
                               zip(observation["stress_physical_mpa"], observation["strain_physical"])))
        energies.append(energy)
        energy_errors.append(abs(energy - expected["energy_density_mpa"]))
    stress_scale = max(1., *(abs(item) for row in reference["states"] for item in row["stress_physical_mpa"]))
    stress_limit = FIXED_LIMITS["stress_absolute_mpa"] + FIXED_LIMITS["stress_relative"] * stress_scale
    tangent_scale = max(abs(item) for item in _flat(reference["tangent_kelvin_mpa"]))
    checks = [{"code": key, "status": "PASS" if value else "FAIL", "observed": value,
               "expected": True} for key, value in flags.items()]
    metrics = {"max_physical_stress_error": {"value": max(physical_errors), "unit": "MPa"},
               "max_kelvin_stress_error": {"value": max(kelvin_errors), "unit": "MPa"},
               "analytical_tangent_relative_error": {"value": max(analytic_errors) / tangent_scale, "unit": "1"},
               "cross_driver_stress_error": {"value": max(driver_errors), "unit": "MPa"},
               "max_energy_density_error": {"value": max(energy_errors), "unit": "MPa"},
               "stress_history": {"value": [row["stress_physical_mpa"] for row in observations], "unit": "MPa"},
               "energy_density_history": {"value": energies, "unit": "MPa"}}
    for name in ("max_physical_stress_error", "max_kelvin_stress_error", "cross_driver_stress_error",
                 "analytical_tangent_relative_error"):
        limit = FIXED_LIMITS["tangent_relative"] if "tangent" in name else stress_limit
        checks.append({"code": name, "status": "PASS" if metrics[name]["value"] <= limit else "FAIL",
                       "observed": metrics[name]["value"], "limit": limit})
    for h, errors in fd_errors.items():
        name = "fd_tangent_relative_error_" + format(h, ".0e")
        value = max(errors) / tangent_scale
        metrics[name] = {"value": value, "unit": "1"}
        checks.append({"code": name, "status": "PASS" if value <= FIXED_LIMITS["tangent_relative"] else "FAIL",
                       "observed": value, "limit": FIXED_LIMITS["tangent_relative"],
                       "every_step_relative_error": [item / tangent_scale for item in errors],
                       "maximum_vs_reported": max(fd_reported_errors[h]) / tangent_scale,
                       "maximum_vs_reference": max(fd_reference_errors[h]) / tangent_scale,
                       "every_step_vs_reported": [item / tangent_scale for item in fd_reported_errors[h]],
                       "every_step_vs_reference": [item / tangent_scale for item in fd_reference_errors[h]]})
    energy_limit = .5 * stress_limit * max(math.fsum(abs(e) * (1 if i < 3 else 2)
                       for i, e in enumerate(row["strain_physical"])) for row in reference["states"])
    checks.append({"code": "elastic_energy_density", "status": "PASS" if max(energy_errors) <= energy_limit else "FAIL",
                   "observed": max(energy_errors), "limit": energy_limit,
                   "method": "Stress-error bound times the prescribed physical strain contraction"})
    passed = all(check["status"] == "PASS" for check in checks)
    for metric in metrics.values():
        metric["valid"] = passed
        if not passed:
            metric["reason"] = "Constitutive qualification failed: " + ", ".join(c["code"] for c in checks if c["status"] == "FAIL")
    return {"checks": checks, "metrics": metrics, "pending_validations": list(PENDING),
            "reference": reference, "stress_scale_mpa": stress_scale, "stress_limit_mpa": stress_limit,
            "energy_method": "Postprocessed 0.5*sigma:epsilon from observed physical tensor fields; not a native stored-energy claim"}
