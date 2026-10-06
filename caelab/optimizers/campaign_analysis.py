"""Deterministic postprocessing of declared, saved numerical DOE samples.

This module never samples, executes a model, converts units, or grants an
engineering verdict. All methods use one complete eligible cohort. A failed
row or any invalid requested response excludes the entire row, with its ID
retained in ``exclusions``; missing responses are never replaced with zero.

The conditioning ceiling and polynomial recognition tolerance below govern
numerical regression support only. They are neither response acceptance
criteria nor physical accuracy/qualification thresholds.
"""

from __future__ import annotations

from copy import deepcopy
import math
import re

import numpy as np


_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
_PARAMETER_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_METRIC = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_UNSAFE_KEYS = {"__proto__", "prototype", "constructor"}
_VARIABLE_REQUIRED = {"parameter_id", "lower_bound", "upper_bound", "unit"}
_VARIABLE_OPTIONAL = {
    "display_name", "native", "current_value", "default_value", "mode", "kind",
    "dependencies", "geometry_effect", "input_effect", "source", "source_sha256",
    "target", "conditions_id", "conditions_template_revision",
    "condition_input_descriptors_sha256",
}
_MAX_CONDITION = 1e12
_POLYNOMIAL_TOLERANCE = 1e-10
_LIMITATIONS = [
    "Statistics describe the eligible empirical DOE samples only; no population "
    "probability, confidence interval, failure probability or input origin is inferred.",
    "Normalized multivariate least-squares coefficients describe conditional "
    "sample associations, not causal effects or Sobol sensitivity indices.",
    "Surrogate validity means a supported finite fit with separate held-out error "
    "only; it is not an accuracy verdict or an extrapolation qualification.",
    "Pareto membership compares only eligible saved sample responses with their "
    "declared directions and exact units; it is not global optimality or physical feasibility.",
    "Failed or invalid rows are excluded as a common cohort without zero substitution. "
    "Material, model and physical qualification remain outside this analysis.",
]


def _number(value, description):
    if type(value) not in (int, float):
        raise ValueError(f"{description} must be a finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{description} must be a finite number")
    return float(value)


def _text(value, description, maximum=128):
    if (type(value) is not str or not value.strip() or len(value) > maximum
            or any(ord(char) < 32 for char in value)):
        raise ValueError(f"{description} must be a nonempty bounded string")
    return value


def _identifier(value, description, pattern=_ID):
    if type(value) is not str or not pattern.fullmatch(value) or value in _UNSAFE_KEYS:
        raise ValueError(f"{description} is not a supported identifier")
    return value


def _shape(value, required, optional, description):
    if (type(value) is not dict or not required <= value.keys()
            or value.keys() - required - optional):
        raise ValueError(f"{description} has missing or unknown fields")


def _json_value(value, depth=0):
    """Check optional registry metadata without interpreting binding eligibility."""
    if depth > 32:
        raise ValueError("Registry metadata exceeds the supported JSON nesting")
    if value is None or type(value) in (str, bool):
        return
    if type(value) in (int, float):
        _number(value, "Registry metadata number")
        return
    if type(value) is list:
        for item in value:
            _json_value(item, depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str or key in _UNSAFE_KEYS:
                raise ValueError("Registry metadata requires safe string keys")
            _json_value(item, depth + 1)
        return
    raise ValueError("Registry metadata must be JSON data")


def _validate(samples, variable_definitions, response_definitions, seed):
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("Analysis seed must be an unsigned 32-bit integer")
    for value, lower, upper, name in (
            (samples, 2, 512, "Samples"),
            (variable_definitions, 1, 16, "Variable definitions"),
            (response_definitions, 1, 16, "Response definitions")):
        if type(value) is not list or not lower <= len(value) <= upper:
            raise ValueError(f"{name} must contain {lower}..{upper} rows")
    names = set()
    for variable in variable_definitions:
        _shape(variable, _VARIABLE_REQUIRED, _VARIABLE_OPTIONAL, "Variable definition")
        name = _identifier(variable["parameter_id"], "Parameter ID", _PARAMETER_ID)
        if name in names:
            raise ValueError("Variable IDs must be distinct")
        names.add(name)
        _text(variable["unit"], "Variable unit")
        low = _number(variable["lower_bound"], "Lower bound")
        high = _number(variable["upper_bound"], "Upper bound")
        if not low < high or not math.isfinite(high - low):
            raise ValueError("Variable bounds require a positive finite interval")
        _json_value(variable)
        for key in ("current_value", "default_value"):
            if key in variable:
                _number(variable[key], f"Variable {key}")
    metrics = set()
    for response in response_definitions:
        _shape(response, {"metric", "unit", "direction"}, set(), "Response definition")
        metric = _identifier(response["metric"], "Metric", _METRIC)
        if metric in metrics:
            raise ValueError("Response metrics must be distinct")
        metrics.add(metric)
        _text(response["unit"], "Response unit")
        if response["direction"] not in ("minimize", "maximize"):
            raise ValueError("Response direction must explicitly be minimize or maximize")
    seen = set()
    eligible, exclusions = [], []
    for row in samples:
        _shape(row, {"id", "values", "responses", "usable"}, set(), "Sample")
        identifier = _identifier(row["id"], "Sample ID")
        if identifier in seen:
            raise ValueError("Sample IDs must be distinct")
        seen.add(identifier)
        if type(row["usable"]) is not bool:
            raise ValueError("Sample usable must be a boolean")
        if type(row["values"]) is not dict or row["values"].keys() != names:
            raise ValueError("Sample values must match all declared variable IDs exactly")
        for variable in variable_definitions:
            value = _number(row["values"][variable["parameter_id"]], "Sample variable")
            if not variable["lower_bound"] <= value <= variable["upper_bound"]:
                raise ValueError("Sample variable lies outside its declared bounds")
        if type(row["responses"]) is not dict or row["responses"].keys() != metrics:
            raise ValueError("Sample responses must match all requested metrics exactly")
        invalid = []
        for response in response_definitions:
            metric = response["metric"]
            item = row["responses"][metric]
            _shape(item, {"value", "unit", "valid"}, {"reason"}, "Sample response")
            if type(item["valid"]) is not bool:
                raise ValueError("Response valid must be a boolean")
            _text(item["unit"], "Sample response unit")
            if item["unit"] != response["unit"]:
                raise ValueError("Response units must exactly match; no implicit conversion")
            if item["value"] is not None or item["valid"]:
                _number(item["value"], "Sample response value")
            if "reason" in item:
                _text(item["reason"], "Invalid response reason", 2000)
            if not item["valid"]:
                invalid.append(metric)
        if not row["usable"]:
            exclusions.append({"id": identifier, "reason": "ROW_UNUSABLE"})
        elif invalid:
            exclusions.append({"id": identifier,
                               "reason": "INVALID_RESPONSE:" + ",".join(invalid)})
        else:
            eligible.append(row)
    # Canonical ID order makes the seeded split independent of input row order.
    return (sorted(eligible, key=lambda row: row["id"]),
            sorted(exclusions, key=lambda row: row["id"]))


def _finite(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Derived statistic cannot be represented as finite JSON")
    return value


def _scaled_moments(values):
    scale = float(np.max(np.abs(values))) if len(values) else 0.0
    scaled = values / scale if scale else np.zeros_like(values)
    mean = float(np.mean(scaled)) if len(values) else 0.0
    std = float(np.std(scaled, ddof=1)) if len(values) > 1 else None
    return scale, scaled, mean, std


def _statistics(values, definition):
    row = {"metric": definition["metric"], "unit": definition["unit"],
           "count": len(values), "mean": None, "std": None, "min": None,
           "max": None, "quantiles": {"q05": None, "q50": None, "q95": None}}
    if not len(values):
        return row
    scale, scaled, mean, std = _scaled_moments(values)
    row.update(mean=_finite(scale * mean),
               std=_finite(scale * std) if std is not None else None,
               min=float(np.min(values)), max=float(np.max(values)))
    quantiles = np.quantile(scaled, [.05, .5, .95], method="linear")
    row["quantiles"] = {key: _finite(scale * value)
                        for key, value in zip(("q05", "q50", "q95"), quantiles)}
    return row


def _regression(design, values):
    """Full-column-rank least squares with a reported numerical support fence."""
    try:
        coefficients, _, rank, singular = np.linalg.lstsq(design, values, rcond=None)
    except np.linalg.LinAlgError:
        return None, 0, None, "LINALG_FAILURE"
    rank = int(rank)
    if design.shape[0] < design.shape[1]:
        return None, rank, None, "INSUFFICIENT_SAMPLES"
    if rank != design.shape[1]:
        return None, rank, None, "RANK_DEFICIENT"
    condition = float(singular[0] / singular[-1])
    if not math.isfinite(condition):
        return None, rank, None, "NUMERIC_UNREPRESENTABLE"
    if condition > _MAX_CONDITION:
        return None, rank, condition, "ILL_CONDITIONED"
    if not np.all(np.isfinite(coefficients)):
        return None, rank, condition, "NUMERIC_UNREPRESENTABLE"
    return coefficients, rank, condition, None


def _sensitivity(x, y, variables, definition, ids):
    row = {"metric": definition["metric"], "unit": definition["unit"],
           "method": "NORMALIZED_MULTIVARIATE_LEAST_SQUARES", "valid": False,
           "reason": "INSUFFICIENT_SAMPLES", "rank": 0, "condition_number": None,
           "coefficients": [], "sample_ids": ids[:], "intercept": None,
           "response_mean": None, "response_std": None}
    if not len(y):
        return row
    yscale, ys, ymean, ystd = _scaled_moments(y)
    row["response_mean"] = _finite(yscale * ymean)
    row["response_std"] = _finite(yscale * ystd) if ystd is not None else None
    if len(y) < 2:
        return row
    columns = []
    for column in x.T:
        _, scaled, mean, std = _scaled_moments(column)
        if std == 0:
            row["reason"] = "CONSTANT_INPUT"
            return row
        columns.append((scaled - mean) / std)
    if ystd == 0:
        row["reason"] = "CONSTANT_RESPONSE"
        return row
    design = np.column_stack([np.ones(len(y)), *columns])
    coefficients, rank, condition, reason = _regression(design, (ys - ymean) / ystd)
    row.update(rank=rank, condition_number=condition, reason=reason)
    if coefficients is None:
        return row
    row.update(valid=True, intercept=float(coefficients[0]), coefficients=[
        {"parameter_id": variable["parameter_id"], "unit": "1",
         "parameter_unit": variable["unit"], "coefficient": float(value)}
        for variable, value in zip(variables, coefficients[1:])])
    return row


def _features(variables, quadratic=False):
    powers = [{}] + [{variable["parameter_id"]: 1} for variable in variables]
    if quadratic:
        powers += [{variable["parameter_id"]: 2} for variable in variables]
        powers += [{variables[i]["parameter_id"]: 1, variables[j]["parameter_id"]: 1}
                   for i in range(len(variables)) for j in range(i + 1, len(variables))]
    return [{"id": f"F{index}", "powers": item} for index, item in enumerate(powers)]


def _design(z, variables, features):
    positions = {variable["parameter_id"]: index for index, variable in enumerate(variables)}
    columns = []
    for feature in features:
        column = np.ones(len(z))
        for name, power in feature["powers"].items():
            column = column * z[:, positions[name]] ** power
        columns.append(column)
    return np.column_stack(columns)


def _surrogate(x, y, variables, definition, ids, seed, train, test):
    features = _features(variables)
    row = {"metric": definition["metric"], "unit": definition["unit"],
           "method": "SEEDED_HOLDOUT_LEAST_SQUARES", "model": "affine",
           "train_ids": [ids[i] for i in train], "test_ids": [ids[i] for i in test],
           "rank": 0, "condition_number": None, "features": features,
           "coefficients": [], "normalization": [
               {key: deepcopy(variable[key]) for key in
                ("parameter_id", "unit", "lower_bound", "upper_bound")}
               for variable in variables],
           "test_mae": None, "test_rmse": None, "test_max_error": None,
           "valid": False, "reason": "INSUFFICIENT_SAMPLES", "seed": seed,
           "limitations": [
               "The seed splits canonical original sample IDs into 75% training and "
               "25% test (rounded up). Held-out responses never select the polynomial degree.",
               "Feature coordinates use the declared bounds, z=2*(x-lower)/(upper-lower)-1; "
               "coefficients retain the response unit. Degree selection uses training residual only.",
               "Held-out error is descriptive, with no accuracy acceptance threshold. "
               "No extrapolation or physical qualification is granted.",
           ]}
    if not train or not test:
        return row
    z = np.column_stack([
        2 * ((x[:, index] - variable["lower_bound"]) /
             (variable["upper_bound"] - variable["lower_bound"])) - 1
        for index, variable in enumerate(variables)])
    train_y = y[train]
    scale = float(np.max(np.abs(train_y)))
    target = train_y / scale if scale else np.zeros_like(train_y)
    design = _design(z, variables, features)
    coefficients, rank, condition, reason = _regression(design[train], target)
    row.update(rank=rank, condition_number=condition, reason=reason)
    if coefficients is None:
        return row
    # This tolerance recognizes an exactly affine numerical sample relation;
    # it is never applied to the held-out errors or an engineering response.
    residual = design[train] @ coefficients - target
    if float(np.sqrt(np.mean(residual ** 2))) > _POLYNOMIAL_TOLERANCE:
        quadratic_features = _features(variables, quadratic=True)
        quadratic_design = _design(z, variables, quadratic_features)
        candidate, candidate_rank, candidate_condition, candidate_reason = _regression(
            quadratic_design[train], target)
        if candidate is not None:
            features, design, coefficients = quadratic_features, quadratic_design, candidate
            row.update(model="quadratic", features=features, rank=candidate_rank,
                       condition_number=candidate_condition)
        else:
            row["limitations"].append("Quadratic training fit is unsupported: " + candidate_reason
                                      + "; the supported affine fit is retained.")
    with np.errstate(over="ignore", invalid="ignore"):
        original_coefficients = coefficients * scale
        prediction = (design[test] @ coefficients) * scale
    if not np.all(np.isfinite(original_coefficients)) or not np.all(np.isfinite(prediction)):
        row["reason"] = "NUMERIC_UNREPRESENTABLE"
        return row
    # Scaling the errors avoids an artificial overflow in squaring a finite
    # dimensional error. An actually unrepresentable error remains a refusal.
    error_scale = max(float(np.max(np.abs(y[test]))), float(np.max(np.abs(prediction))))
    error = ((prediction / error_scale) - (y[test] / error_scale)
             if error_scale else np.zeros(len(test)))
    errors = [error_scale * float(np.mean(np.abs(error))),
              error_scale * float(np.sqrt(np.mean(error ** 2))),
              error_scale * float(np.max(np.abs(error)))]
    if not all(math.isfinite(value) for value in errors):
        row["reason"] = "NUMERIC_UNREPRESENTABLE"
        return row
    row.update(valid=True, reason=None, coefficients=[
        {"feature_id": feature["id"], "value": float(value), "unit": definition["unit"]}
        for feature, value in zip(features, original_coefficients)],
        test_mae=errors[0], test_rmse=errors[1], test_max_error=errors[2])
    return row


def _pareto(y, definitions, ids):
    row = {"response_definitions": deepcopy(definitions), "nondominated_ids": [],
           "method": "EXACT_COMPONENTWISE_NONDOMINANCE", "valid": False,
           "reason": "REQUIRES_TWO_RESPONSES"}
    if len(definitions) < 2:
        return row
    if not ids:
        row["reason"] = "NO_ELIGIBLE_SAMPLES"
        return row
    oriented = y * np.array([1 if definition["direction"] == "minimize" else -1
                             for definition in definitions])
    row["nondominated_ids"] = [identifier for index, identifier in enumerate(ids)
        if not np.any(np.all(oriented <= oriented[index], axis=1)
                      & np.any(oriented < oriented[index], axis=1))]
    row.update(valid=True, reason=None)
    return row


def summarize(samples, variable_definitions, response_definitions, *, seed=13):
    """Return finite JSON statistics, associations, holdout fits and Pareto IDs.

    Inputs are bounded JSON data; requested variable/response keys and units
    must match exactly. IDs are retained, while ID ordering is canonicalized
    before the seeded split. No input object or registry binding is modified.
    The common eligible cohort is used by every output, without interpolation
    or replacement of failed responses. ``std`` is sample standard deviation
    (ddof=1); empirical quantiles use linear interpolation.
    """
    eligible, exclusions = _validate(samples, variable_definitions, response_definitions, seed)
    ids = [row["id"] for row in eligible]
    x = np.array([[row["values"][variable["parameter_id"]] for variable in variable_definitions]
                  for row in eligible], dtype=float).reshape(len(eligible), len(variable_definitions))
    y = np.array([[row["responses"][response["metric"]]["value"] for response in response_definitions]
                  for row in eligible], dtype=float).reshape(len(eligible), len(response_definitions))
    train, test = [], []
    if ids:
        shuffled = np.random.default_rng(seed).permutation(len(ids))
        count = max(1, math.ceil(len(ids) / 4))
        test, train = sorted(shuffled[:count].tolist()), sorted(shuffled[count:].tolist())
    return {
        "statistics": [_statistics(y[:, index], response)
                       for index, response in enumerate(response_definitions)],
        "sensitivity": [_sensitivity(x, y[:, index], variable_definitions, response, ids)
                        for index, response in enumerate(response_definitions)],
        "surrogate": [_surrogate(x, y[:, index], variable_definitions, response,
                                 ids, seed, train, test)
                      for index, response in enumerate(response_definitions)],
        "pareto": _pareto(y, response_definitions, ids),
        "exclusions": exclusions,
        "qualification": "NUMERICAL_SAMPLE_ANALYSIS_ONLY",
        "decision": "NOT_RELEASED",
        "limitations": _LIMITATIONS[:],
    }
