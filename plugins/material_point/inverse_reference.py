"""A frozen synthetic inverse prerequisite, with no numerical search engine.

The known Hooke response creates the target and the post-run oracle only.
Feedback receives a selected actual native observation from the adapter.
"""

from copy import deepcopy
import hashlib
import json
import math

from . import reference as material


__version__ = "1"
METRIC = "inverse_residual"
INPUT_ID = "youngs_modulus_mpa"
LOWER_MPA, UPPER_MPA = 100000., 300000.
KNOWN_MODULUS_MPA = 200000.
SCALE_MPA = 300.
OBJECTIVE_AGREEMENT_ABSOLUTE = 1e-12
BASE_KEYS = {"case", "material", "temperature_k", "history", "limits"}
PENDING = [*material.PENDING, "identification_qualification"]
REQUIRED_BASE_CHECKS = ["reliable_integrations", "native_tensor_mapping", "immutable_probe_state",
                        "driver_continuity", "nominal_history", "max_physical_stress_error",
                        "max_kelvin_stress_error", "cross_driver_stress_error",
                        "analytical_tangent_relative_error", "fd_tangent_relative_error_1e-07",
                        "fd_tangent_relative_error_1e-08", "fd_tangent_relative_error_1e-09",
                        "elastic_energy_density"]


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode("utf-8")).hexdigest()


def _keys(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f"{label} must have exactly the declared keys")


def _finite(value, label):
    try:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"{label} must be a finite number, not a boolean")
        return float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} must be a finite representable number") from exc


def canonical_dataset():
    """Known synthetic target; it is never labeled a physical measurement."""
    settings = material.canonical_settings()
    settings["material"][INPUT_ID] = KNOWN_MODULUS_MPA
    target = material.analytical_reference(settings)["states"][1]["stress_physical_mpa"][0]
    body = {"schema_version": "1",
            "source": {"kind": "SYNTHETIC_REFERENCE", "generator": "independent_python_hooke_v1",
                       "known_material": deepcopy(settings["material"]),
                       "temperature_k": settings["temperature_k"], "physical_measurement": False},
            "observations": [{"quantity": "stress", "component": "xx", "time_s": 1.,
                              "unit": "MPa", "value": target, "scale_mpa": SCALE_MPA}]}
    return {**body, "sha256": _hash(body)}


def validate_dataset(dataset):
    _keys(dataset, {"schema_version", "source", "observations", "sha256"}, "Observation dataset")
    out = deepcopy(dataset)
    _keys(out["source"], {"kind", "generator", "known_material", "temperature_k", "physical_measurement"},
          "Observation source")
    _keys(out["source"]["known_material"], {INPUT_ID, "poisson_ratio"}, "Known synthetic material")
    for key in (INPUT_ID, "poisson_ratio"):
        out["source"]["known_material"][key] = _finite(out["source"]["known_material"][key], key)
    out["source"]["temperature_k"] = _finite(out["source"]["temperature_k"], "Source temperature")
    if (not isinstance(out["observations"], list) or len(out["observations"]) != 1 or
            type(out["source"]["physical_measurement"]) is not bool):
        raise ValueError("Exactly one synthetic observation and explicit physical-measurement flag are required")
    item = out["observations"][0]
    _keys(item, {"quantity", "component", "time_s", "unit", "value", "scale_mpa"}, "Observation")
    for key in ("time_s", "value", "scale_mpa"):
        item[key] = _finite(item[key], key)
    if item["scale_mpa"] <= 0:
        raise ValueError("Observation normalization scale must be positive MPa")
    body = {key: value for key, value in out.items() if key != "sha256"}
    if not isinstance(out["sha256"], str) or out["sha256"] != _hash(body):
        raise ValueError("Observation dataset SHA256 drifted")
    if _hash(out) != _hash(canonical_dataset()):
        raise ValueError("This prerequisite supports only the declared synthetic xx/time-1/MPa/scale-300 dataset")
    return out


def canonical_settings():
    return {**material.canonical_settings(), "observation_dataset": canonical_dataset()}


def validate_settings(settings):
    _keys(settings, BASE_KEYS | {"observation_dataset"}, "Inverse settings")
    base = material.validate_settings({key: settings[key] for key in BASE_KEYS})
    modulus = base["material"][INPUT_ID]
    if not LOWER_MPA <= modulus <= UPPER_MPA:
        raise ValueError("Young modulus must remain in the declared 100000..300000 MPa domain")
    fixed = deepcopy(base)
    fixed["material"][INPUT_ID] = 210000.
    if _hash(fixed) != _hash(material.canonical_settings()):
        raise ValueError("History, nu, temperature, case and all numerical limits are frozen")
    return {**base, "observation_dataset": validate_dataset(settings["observation_dataset"])}


def base_settings(settings):
    normalized = validate_settings(settings)
    return {key: normalized[key] for key in BASE_KEYS}


def model_declaration(settings):
    normalized = validate_settings(settings)
    declaration = material.model_declaration(base_settings(normalized))
    declaration["model"]["inverse_problem"] = {
        "kind": "bounded_synthetic_reference_prerequisite",
        "observation_dataset": deepcopy(normalized["observation_dataset"]),
        "objective": {"metric": METRIC, "unit": "1", "direction": "minimize",
                      "definition": "((actual physical stress xx at time 1 s - target MPa) / 300 MPa)^2"},
        "qualification": "UNKNOWN: no measured material, statistical fit, global optimum or engineering release"}
    declaration["scope"] = "Synthetic-reference inverse prerequisite; native constitutive gates mandatory; qualification UNKNOWN"
    return declaration


def describe_inputs(settings):
    settings = validate_settings(settings)
    return [{"id": INPUT_ID, "label": "Young modulus", "unit": "MPa",
             "value": settings["material"][INPUT_ID], "lower": LOWER_MPA, "upper": UPPER_MPA,
             "settings_path": ["material", INPUT_ID],
             "declaration_paths": [["model", "materials", 0, INPUT_ID]]}]


def bind_inputs(settings, values):
    settings = validate_settings(settings)
    _keys(values, {INPUT_ID}, "Inverse assignments")
    settings["material"][INPUT_ID] = _finite(values[INPUT_ID], "Bound modulus")
    return validate_settings(settings)


def objective_from_observation(settings, observation):
    """Assess the physical observation selected by the native adapter.

    No candidate modulus or analytical candidate response enters this formula.
    """
    settings = validate_settings(settings)
    _keys(observation, {"quantity", "component", "time_s", "unit", "value"}, "Native physical observation")
    observation = deepcopy(observation)
    observation["time_s"] = _finite(observation["time_s"], "Native observation time")
    observation["value"] = _finite(observation["value"], "Native observed stress")
    target = settings["observation_dataset"]["observations"][0]
    if any(observation[key] != target[key] for key in ("quantity", "component", "time_s", "unit")):
        raise ValueError("Actual observation quantity/component/time/unit does not match the frozen dataset")
    residual = (observation["value"] - target["value"]) / target["scale_mpa"]
    squared = residual * residual
    if not math.isfinite(residual) or not math.isfinite(squared):
        raise ValueError("Native inverse residual is not a finite scalar")
    return {"metrics": {METRIC: {"value": squared, "unit": "1", "valid": True},
                        "normalized_stress_residual": {"value": residual, "unit": "1", "valid": True},
                        "observed_axial_stress": {"value": observation["value"], "unit": "MPa", "valid": True},
                        "target_axial_stress": {"value": target["value"], "unit": "MPa", "valid": True}},
            "checks": [{"code": "inverse_observation_contract", "status": "PASS",
                        "observed": deepcopy(observation), "dataset_sha256": settings["observation_dataset"]["sha256"],
                        "scope": "Observation and objective semantics only; residual zero is not required for valid feedback"}],
            "observation": observation, "source_kind": "SYNTHETIC_REFERENCE",
            "dataset_sha256": settings["observation_dataset"]["sha256"]}


def synthetic_oracle(modulus_mpa):
    """Post-run comparator only, never numerical-engine feedback."""
    modulus = _finite(modulus_mpa, "Oracle modulus")
    if not LOWER_MPA <= modulus <= UPPER_MPA:
        raise ValueError("Oracle modulus is outside the predeclared bounds")
    nu, strain = .3, .001
    stress = modulus * (1 - nu) / ((1 + nu) * (1 - 2 * nu)) * strain
    target = canonical_dataset()["observations"][0]["value"]
    return {"stress_xx_mpa": stress, METRIC: ((stress - target) / SCALE_MPA) ** 2,
            "known_modulus_mpa": KNOWN_MODULUS_MPA,
            "source": "SYNTHETIC_REFERENCE post-run oracle only; not native feedback"}


def frozen_packet():
    return {"settings": canonical_settings(), "input": describe_inputs(canonical_settings())[0],
            "objective": {"source": "model", "metric": METRIC, "unit": "1", "direction": "minimize"},
            "engine": {"name": "scipy.differential_evolution", "seed": 13, "population_size": 5,
                       "max_generations": 1, "initial_modulus_mpa": 210000., "maximum_evaluations": 10},
            "oracle": {"known_modulus_mpa": KNOWN_MODULUS_MPA,
                       "pointwise_objective_agreement_absolute": OBJECTIVE_AGREEMENT_ABSOLUTE,
                       "acceptance": "Best observed residual must improve over the initial candidate; no final-fit tolerance"},
            "required_validations": {"model": [*REQUIRED_BASE_CHECKS, "inverse_observation_contract"]},
            "pending_validations": list(PENDING), "decision": "NOT_RELEASED"}
