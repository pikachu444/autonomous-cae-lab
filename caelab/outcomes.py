"""Shared numerical outcome checks at the adapter-to-Core boundary."""

import math

from .storage import canonical_hash


def _numeric_value(value):
    if type(value) in (int, float):
        try:
            return math.isfinite(value)
        except OverflowError:
            return False
    return isinstance(value, list) and bool(value) and all(_numeric_value(item) for item in value)


def validate_outcome(outcome: dict) -> None:
    if (not isinstance(outcome, dict) or outcome.get("status") not in ("COMPLETED", "REJECTED") or
            not isinstance(outcome.get("checks"), list) or
            not isinstance(outcome.get("metrics"), dict) or
            not isinstance(outcome.get("provenance"), dict) or
            not isinstance(outcome.get("solver_status"), str) or
            not isinstance(outcome.get("pending_validations"), list) or
            any(not isinstance(k, str) or not k for k in outcome["pending_validations"]) or
            type(outcome.get("converged")) not in (bool, type(None))):
        raise ValueError("Numerical adapter returned an invalid common outcome")
    if any(not isinstance(check, dict) or
           check.get("status") not in ("PASS", "FAIL", "UNKNOWN", "WARNING") or
           not isinstance(check.get("code"), str) or not check["code"] for check in outcome["checks"]):
        raise ValueError("Numerical adapter returned an invalid validation check")
    if any(not isinstance(name, str) or not name or
           not isinstance(metric, dict) or not {"value", "unit", "valid"} <= metric.keys() or
           not isinstance(metric["unit"], str) or not metric["unit"] or type(metric["valid"]) is not bool or
           (metric["valid"] and not _numeric_value(metric["value"])) or
           (not metric["valid"] and (not isinstance(metric.get("reason"), str) or not metric["reason"]))
           for name, metric in outcome["metrics"].items()):
        raise ValueError("Numerical adapter returned an invalid metric")
    if outcome["status"] == "COMPLETED" and (outcome["solver_status"] not in ("COMPLETED", "CONVERGED") or
                                              outcome["converged"] is not True or not outcome["metrics"]):
        raise ValueError("Completed numerical execution requires convergence and metrics")
    canonical_hash(outcome)
