"""Research variable mapping and early, solver-independent input checks."""

import math
import re
from typing import Any

from .contracts import Candidate


ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


def register_parameter(
    entries: list[dict[str, Any]], candidate: Candidate, *, parameter_id: str,
    display_name: str, lower: float, upper: float, mode: str = "free",
    kind: str = "continuous", dependencies: list[str] | None = None,
    effect: dict[str, Any],
) -> dict[str, Any]:
    if not ID.fullmatch(parameter_id) or not display_name.strip():
        raise ValueError("A unique parameter ID and display name are required")
    if any(p["parameter_id"] == parameter_id or p["native"] == candidate.native for p in entries):
        raise ValueError("Parameter ID or native CAD mapping already registered")
    if kind not in ("continuous", "integer", "discrete", "categorical"):
        raise ValueError("Unsupported parameter type")
    if mode not in ("fixed", "free"):
        raise ValueError("Parameter mode must be fixed or free")
    if kind in ("discrete", "categorical"):
        raise ValueError("This CAD adapter exposes numeric continuous/integer dimensions only")
    if (any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x)
            for x in (lower, upper)) or
        (candidate.lower is not None and lower < candidate.lower) or
        (candidate.upper is not None and upper > candidate.upper) or
        not lower <= candidate.value <= upper or lower >= upper):
        raise ValueError("Bounds must contain the current CAD value and lie inside native model bounds")
    if kind == "integer" and any(int(x) != x for x in (lower, upper, candidate.value)):
        raise ValueError("Integer parameter must have integral bounds and current value")
    dependencies = dependencies or []
    if parameter_id in dependencies or any(d not in {p["parameter_id"] for p in entries} for d in dependencies):
        raise ValueError("Dependencies must reference previously registered parameters")
    if effect.get("status") != "PASS":
        raise ValueError("CAD dimension has no verified measurable effect on final geometry")
    return {
        "parameter_id": parameter_id, "display_name": display_name.strip(),
        "native": candidate.native, "unit": candidate.unit,
        "current_value": candidate.value, "default_value": candidate.value,
        "lower_bound": lower, "upper_bound": upper,
        "mode": mode, "kind": kind, "dependencies": dependencies,
        "geometry_effect": effect, "source": "CAD discovery",
        "source_sha256": candidate.source_sha256,
    }


def validate_assignments(entries: list[dict[str, Any]], values: dict[str, Any]) -> list[dict[str, Any]]:
    checks = []
    known = {p["parameter_id"]: p for p in entries}
    for name in values:
        if name not in known:
            checks.append({"code": "unknown_parameter", "status": "FAIL", "observed": name})
    for name, value in values.items():
        if name not in known:
            continue
        p = known[name]
        valid_number = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        ok = valid_number and p["lower_bound"] <= value <= p["upper_bound"]
        if p["kind"] == "integer":
            ok = ok and int(value) == value
        if p["mode"] == "fixed":
            ok = ok and value == p["current_value"]
        checks.append({"code": "parameter_" + name, "status": "PASS" if ok else "FAIL",
                       "observed": value, "expected": [p["lower_bound"], p["upper_bound"]],
                       "mode": p["mode"], "unit": p["unit"]})
    return checks
