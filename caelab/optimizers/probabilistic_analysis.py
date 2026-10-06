"""Candidate pure probability propagation for declared independent uniforms.

The caller declares both the marginal laws and their independence/source. A
seeded scrambled LHS supplies the finite numerical design, not measured input
distributions. Actual rows must join every declared original experiment ID and
input point exactly. Failed/invalid responses remain retained and are excluded
without zero replacement. The valid-row threshold ratio has no iid binomial
confidence interval: LHS points are stratified, dependent observations.

This module writes nothing and executes no model, provider or native backend.
"""

from copy import deepcopy
import math
import operator
import re

import numpy as np
import scipy
from scipy.stats import qmc


_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
_PARAMETER_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_METRIC = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_UNSAFE = {"__proto__", "prototype", "constructor"}
_OPERATORS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}
_REQUEST_KEYS = {"marginals", "independence", "source", "sample_ids", "seed"}
_DESIGN_KEYS = _REQUEST_KEYS | {"schema_version", "sample_count", "sampling", "samples"}
_LIMITATIONS = [
    "Uniform marginal laws, bounds and independence are explicit user declarations; "
    "their physical validity or source adequacy is not identified by numerical sampling.",
    "Scrambled Latin-hypercube points are stratified dependent samples. No iid binomial "
    "confidence interval, population confidence or identified physical failure probability is supplied.",
    "Thresholds use the original signed scalar response and exact unit without magnitude, "
    "absolute value, interpolation or unit conversion.",
    "Excluded outcomes are unknown, not zero or non-exceedances. The ratio describes "
    "only valid numerical rows; response-dependent exclusions can bias propagation estimates.",
    "Unknown-outcome fraction bounds concern only this finite declared design; they are "
    "not population probability bounds or confidence intervals.",
    "Empirical moments and linearly interpolated quantiles describe finite numerical "
    "responses. No causal effect, Sobol index, model qualification or engineering release is inferred.",
]


def _shape(value, keys, description, optional=frozenset()):
    if type(value) is not dict or not keys <= value.keys() or value.keys() - keys - optional:
        raise ValueError(f"{description} has missing or unknown fields")


def _number(value, description):
    if type(value) not in (int, float):
        raise ValueError(f"{description} must be a finite nonboolean number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{description} must be a finite nonboolean number")
    return float(value)


def _text(value, description, maximum=128):
    if (type(value) is not str or not value.strip() or len(value) > maximum
            or any(ord(char) < 32 for char in value)):
        raise ValueError(f"{description} must be a nonempty bounded string")
    return value


def _id(value, description, pattern=_ID):
    if type(value) is not str or not pattern.fullmatch(value) or value in _UNSAFE:
        raise ValueError(f"{description} is not a supported identifier")
    return value


def _request(request):
    _shape(request, _REQUEST_KEYS, "Sampling request")
    if request["independence"] != "INDEPENDENT_USER_DECLARED":
        raise ValueError("Independent uniform marginals must be explicitly declared")
    if type(request["seed"]) is not int or not 0 <= request["seed"] <= 2**32 - 1:
        raise ValueError("Sampling seed must be an unsigned 32-bit integer")
    _shape(request["source"], {"origin", "reference"}, "Distribution source")
    if request["source"]["origin"] not in (
            "ASSUMED", "MEASURED_REPORTED", "PUBLISHED_REFERENCE", "SYNTHETIC"):
        raise ValueError("Distribution source origin must be explicitly declared")
    _text(request["source"]["reference"], "Distribution source reference", 2000)
    marginals, sample_ids = request["marginals"], request["sample_ids"]
    if type(marginals) is not list or not 1 <= len(marginals) <= 16:
        raise ValueError("Declare 1..16 continuous uniform marginals")
    if type(sample_ids) is not list or not 2 <= len(sample_ids) <= 512:
        raise ValueError("Declare 2..512 original experiment IDs")
    seen = set()
    for marginal in marginals:
        _shape(marginal, {"parameter_id", "unit", "distribution", "lower_bound", "upper_bound"},
               "Marginal")
        name = _id(marginal["parameter_id"], "Parameter ID", _PARAMETER_ID)
        if name in seen:
            raise ValueError("Marginal parameter IDs must be distinct")
        seen.add(name)
        _text(marginal["unit"], "Marginal unit")
        if marginal["distribution"] != "uniform":
            raise ValueError("Only explicit continuous uniform marginals are supported")
        low = _number(marginal["lower_bound"], "Marginal lower bound")
        high = _number(marginal["upper_bound"], "Marginal upper bound")
        if not low < high or not math.isfinite(high - low):
            raise ValueError("Uniform bounds require a positive finite interval")
    seen = set()
    for identifier in sample_ids:
        _id(identifier, "Experiment ID")
        if identifier in seen:
            raise ValueError("Experiment IDs must be distinct")
        seen.add(identifier)


def declare_samples(request):
    """Declare scrambled, seeded LHS points for caller-supplied experiment IDs.

    ``request`` is exact JSON {marginals, independence, source, sample_ids,
    seed}. Marginals have exact {parameter_id, unit, distribution:'uniform',
    lower_bound, upper_bound}. Independence is 'INDEPENDENT_USER_DECLARED';
    source is exact {origin, reference}. The original ID and marginal order
    controls point binding and is preserved. Nothing is executed or persisted.
    """
    _request(request)
    marginals = request["marginals"]
    unit_cube = qmc.LatinHypercube(d=len(marginals), scramble=True, strength=1,
                                  optimization=None, rng=np.random.default_rng(request["seed"])).random(
                                      len(request["sample_ids"]))
    samples = []
    for index, (identifier, row) in enumerate(zip(request["sample_ids"], unit_cube), 1):
        values = {}
        for marginal, ordinate in zip(marginals, row):
            low, high = marginal["lower_bound"], marginal["upper_bound"]
            value = float(low + (high - low) * ordinate)
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError("LHS point cannot be represented within its declared finite bounds")
            values[marginal["parameter_id"]] = value
        samples.append({"id": identifier, "index": index, "values": values})
    return {**deepcopy(request), "schema_version": "1.0", "sample_count": len(samples),
            "sampling": {"engine": "scipy.latin_hypercube", "version": scipy.__version__,
                         "numpy_version": np.__version__, "strength": 1, "optimization": None,
                         "randomization": "SCRAMBLED_STRATIFIED"},
            "samples": samples}


def _declaration(declaration):
    _shape(declaration, _DESIGN_KEYS, "Sampling declaration")
    request = {key: declaration[key] for key in _REQUEST_KEYS}
    _request(request)
    if (declaration["schema_version"] != "1.0" or type(declaration["sample_count"]) is not int
            or declaration["sample_count"] != len(declaration["sample_ids"])):
        raise ValueError("Sampling declaration version or count differs")
    _shape(declaration["sampling"], {"engine", "version", "numpy_version", "strength",
                                    "optimization", "randomization"}, "Sampling metadata")
    if type(declaration["sampling"]["strength"]) is not int:
        raise ValueError("Sampling strength must be an integer")
    samples = declaration["samples"]
    if type(samples) is not list or len(samples) != declaration["sample_count"]:
        raise ValueError("Sampling declaration must retain every point")
    names = {item["parameter_id"] for item in declaration["marginals"]}
    for index, sample in enumerate(samples, 1):
        _shape(sample, {"id", "index", "values"}, "Declared point")
        if (type(sample["index"]) is not int or sample["index"] != index
                or sample["id"] != declaration["sample_ids"][index - 1]):
            raise ValueError("Declared point index or original experiment ID differs")
        if type(sample["values"]) is not dict or sample["values"].keys() != names:
            raise ValueError("Declared point variable keys differ")
        for marginal in declaration["marginals"]:
            value = _number(sample["values"][marginal["parameter_id"]], "Declared ordinate")
            if not marginal["lower_bound"] <= value <= marginal["upper_bound"]:
                raise ValueError("Declared point lies outside its marginal bounds")
    # The frozen points must be the declared LHS, not relabeled generic DOE or
    # an arbitrary sample subset. Different sampler versions require explicit
    # integration support, rather than claiming unverified replay compatibility.
    expected = declare_samples(request)
    if declaration != expected:
        raise ValueError("Sampling declaration differs from its exact seeded LHS/version")


def _thresholds(thresholds):
    if type(thresholds) is not list or not 1 <= len(thresholds) <= 16:
        raise ValueError("Declare 1..16 signed scalar response thresholds")
    ids, units = set(), {}
    for threshold in thresholds:
        _shape(threshold, {"id", "metric", "unit", "operator", "value"}, "Threshold")
        identifier = _id(threshold["id"], "Threshold ID")
        metric = _id(threshold["metric"], "Response metric", _METRIC)
        if identifier in ids:
            raise ValueError("Threshold IDs must be distinct")
        ids.add(identifier)
        unit = _text(threshold["unit"], "Threshold unit")
        if metric in units and units[metric] != unit:
            raise ValueError("Thresholds on one metric require the same original unit")
        units[metric] = unit
        if type(threshold["operator"]) is not str or threshold["operator"] not in _OPERATORS:
            raise ValueError("Threshold operator must explicitly be >, >=, < or <=")
        _number(threshold["value"], "Threshold value")
    return units


def _rows(declaration, rows, units):
    if type(rows) is not list or len(rows) != declaration["sample_count"]:
        raise ValueError("Every declared experiment row is required, including failures")
    expected = {point["id"]: point for point in declaration["samples"]}
    seen, by_id = set(), {}
    valid, exclusions = [], []
    names = {item["parameter_id"] for item in declaration["marginals"]}
    for row in rows:
        _shape(row, {"id", "values", "responses", "usable"}, "Result row")
        identifier = _id(row["id"], "Result experiment ID")
        if identifier not in expected or identifier in seen:
            raise ValueError("Result experiment ID is duplicate or not in the declared design")
        seen.add(identifier)
        if type(row["usable"]) is not bool:
            raise ValueError("Result usable must be a boolean")
        if type(row["values"]) is not dict or row["values"].keys() != names:
            raise ValueError("Result inputs must match every declared marginal exactly")
        for marginal in declaration["marginals"]:
            name = marginal["parameter_id"]
            value = _number(row["values"][name], "Result input value")
            if not marginal["lower_bound"] <= value <= marginal["upper_bound"]:
                raise ValueError("Result input lies outside its declared bounds")
            if value != expected[identifier]["values"][name]:
                raise ValueError("Result input differs from its original declared ID/point")
        if type(row["responses"]) is not dict or row["responses"].keys() != units.keys():
            raise ValueError("Result responses must exactly match threshold metrics")
        invalid = []
        for metric, unit in units.items():
            response = row["responses"][metric]
            _shape(response, {"value", "unit", "valid"}, "Result response", optional={"reason"})
            if type(response["valid"]) is not bool:
                raise ValueError("Response valid must be a boolean")
            _text(response["unit"], "Response unit")
            if response["unit"] != unit:
                raise ValueError("Threshold and original response units must exactly match")
            if response["value"] is not None or response["valid"]:
                _number(response["value"], "Response value")
            if "reason" in response and response["reason"] is not None:
                _text(response["reason"], "Response reason", 2000)
            if not response["valid"]:
                invalid.append(metric)
        by_id[identifier] = row
        if not row["usable"]:
            exclusions.append({"id": identifier, "reason": "ROW_UNUSABLE"})
        elif invalid:
            exclusions.append({"id": identifier, "reason": "INVALID_RESPONSE:" + ",".join(invalid)})
        else:
            valid.append(identifier)
    if seen != expected.keys():
        raise ValueError("Declared experiment rows are missing")
    positions = {identifier: index for index, identifier in enumerate(declaration["sample_ids"])}
    return ([by_id[identifier] for identifier in declaration["sample_ids"]],
            sorted(valid, key=positions.__getitem__),
            sorted(exclusions, key=lambda item: positions[item["id"]]))


def _finite(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Derived statistic cannot be represented as finite JSON")
    return value


def _statistics(values, metric, unit):
    row = {"metric": metric, "unit": unit, "count": len(values), "mean": None, "std": None,
           "min": None, "max": None, "quantiles": {"q05": None, "q50": None, "q95": None}}
    if not values:
        return row
    data = np.asarray(values, dtype=float)
    scale = float(np.max(np.abs(data)))
    normalized = data / scale if scale else np.zeros_like(data)
    row.update(mean=_finite(scale * float(np.mean(normalized))),
               std=_finite(scale * float(np.std(normalized, ddof=1))) if len(values) > 1 else None,
               min=float(np.min(data)), max=float(np.max(data)))
    row["quantiles"] = {key: _finite(scale * float(value)) for key, value in zip(
        ("q05", "q50", "q95"), np.quantile(normalized, [.05, .5, .95], method="linear"))}
    return row


def analyze(declaration, rows, thresholds):
    """Join retained scalar outcomes to a declared LHS and estimate predicates.

    Rows use exact {id, values, responses, usable}; metric payloads use
    {value, unit, valid} plus optional reason. All threshold metrics must be
    present even when invalid (value:null allowed only with valid:false).
    Thresholds are exact {id, metric, unit, operator, value}. Original IDs,
    signed values, units, invalid outcomes and declaration are copied intact.
    No missing experiment row, zero substitute or implicit unit conversion is
    accepted. The common cohort is complete for every requested metric.
    """
    _declaration(declaration)
    units = _thresholds(thresholds)
    ordered, valid_ids, exclusions = _rows(declaration, rows, units)
    valid_set = set(valid_ids)
    eligible = [row for row in ordered if row["id"] in valid_set]
    total, count, excluded = len(ordered), len(eligible), len(exclusions)
    estimates = []
    for threshold in thresholds:
        metric, operation = threshold["metric"], threshold["operator"]
        observed = sum(_OPERATORS[operation](row["responses"][metric]["value"], threshold["value"])
                       for row in eligible)
        estimates.append({**deepcopy(threshold),
            "predicate": f"{metric} {operation} {threshold['value']} {threshold['unit']}",
            "signed_scalar": True, "exceedance_count": observed, "n_valid": count,
            "n_excluded": excluded, "probability_estimate": observed / count if count else None,
            "conditioning": "VALID_NUMERICAL_ROWS_ONLY", "valid": bool(count),
            "reason": None if count else "NO_VALID_NUMERICAL_RESPONSES",
            "confidence_interval": None,
            "confidence_interval_reason": "LHS_STRATIFIED_DEPENDENT_NOT_IID_BINOMIAL",
            "unknown_outcome_fraction_bounds": {"lower": observed / total,
                                                  "upper": (observed + excluded) / total},
        })
    return {
        "schema_version": "1.0", "declaration": deepcopy(declaration), "samples": deepcopy(ordered),
        "sample_ids": declaration["sample_ids"][:], "valid_sample_ids": valid_ids,
        "counts": {"declared": total, "valid": count, "excluded": excluded},
        "statistics": [_statistics([row["responses"][metric]["value"] for row in eligible], metric, unit)
                       for metric, unit in units.items()],
        "thresholds": estimates, "exclusions": exclusions,
        "qualification": "DECLARED_UNIFORM_NUMERICAL_PROBABILITY_PROPAGATION_ONLY",
        "physical": "UNKNOWN", "engineering": "UNKNOWN", "decision": "NOT_RELEASED",
        "limitations": _LIMITATIONS[:],
    }
