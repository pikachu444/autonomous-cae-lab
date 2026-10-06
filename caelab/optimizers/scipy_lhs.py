"""Pinned, seeded continuous design-of-experiments sampler."""

from __future__ import annotations

import math

import numpy
import scipy
from scipy.stats import qmc


ENGINE = "scipy.latin_hypercube"


def sample(variables: list[dict], *, count: int, seed: int) -> tuple[list[dict[str, float]], dict]:
    if not isinstance(variables, list) or not variables or type(count) is not int or not 2 <= count <= 32:
        raise ValueError("DOE requires 1+ variables and 2–32 samples")
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("DOE seed must be an unsigned 32-bit integer")
    names = []
    for variable in variables:
        if not isinstance(variable, dict):
            raise ValueError("DOE variables must be registry entries")
        name = variable.get("parameter_id")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("DOE variable IDs must be nonempty and distinct")
        target = variable.get("target", "cad")
        if target == "cad":
            effect = variable.get("geometry_effect")
        elif target in ("analysis_conditions", "model_analysis"):
            effect = variable.get("input_effect")
        else:
            raise ValueError("DOE variable target must be CAD, model_analysis or analysis_conditions")
        lower, upper = variable.get("lower_bound"), variable.get("upper_bound")
        try:
            finite_bounds = (all(type(x) in (int, float) and math.isfinite(x) for x in (lower, upper))
                             and lower < upper and math.isfinite(upper - lower))
        except (TypeError, OverflowError):
            finite_bounds = False
        if (variable.get("kind") != "continuous" or variable.get("mode") != "free" or
                not isinstance(effect, dict) or effect.get("status") != "PASS" or not finite_bounds):
            raise ValueError("DOE variable requires finite continuous free bounds and PASS registered binding effect")
        if target in ("analysis_conditions", "model_analysis") and "current_value" in variable:
            current = variable["current_value"]
            try:
                valid_current = (type(current) in (int, float) and math.isfinite(current)
                                 and lower <= current <= upper)
            except (TypeError, OverflowError):
                valid_current = False
            if not valid_current:
                raise ValueError("DOE condition current value must be finite and within its bounds")
        names.append(name)
    unit_cube = qmc.LatinHypercube(d=len(variables), strength=1, optimization=None,
                                   rng=numpy.random.default_rng(seed)).random(count)
    points = [{v["parameter_id"]: float(v["lower_bound"] +
              (v["upper_bound"] - v["lower_bound"]) * row[i])
              for i, v in enumerate(variables)} for row in unit_cube]
    return points, {"engine": ENGINE, "version": scipy.__version__,
                    "numpy_version": numpy.__version__, "seed": seed,
                    "strength": 1, "optimization": None}


class ScipyLatinHypercube:
    engine = ENGINE
    version = scipy.__version__

    def sample(self, variables: list[dict], *, count: int, seed: int
               ) -> tuple[list[dict[str, float]], dict]:
        return sample(variables, count=count, seed=seed)
