"""Pinned, seeded continuous design-of-experiments sampler."""

from __future__ import annotations

import math

import numpy
import scipy
from scipy.stats import qmc


ENGINE = "scipy.latin_hypercube"


def sample(variables: list[dict], *, count: int, seed: int) -> tuple[list[dict[str, float]], dict]:
    if not variables or type(count) is not int or not 2 <= count <= 32:
        raise ValueError("DOE requires 1+ variables and 2–32 samples")
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("DOE seed must be an unsigned 32-bit integer")
    names = [v["parameter_id"] for v in variables]
    if len(set(names)) != len(names):
        raise ValueError("DOE variables must be distinct")
    for variable in variables:
        lower, upper = variable["lower_bound"], variable["upper_bound"]
        if (variable["kind"] != "continuous" or variable["mode"] != "free" or
                variable["geometry_effect"]["status"] != "PASS" or
                not all(type(x) in (int, float) and math.isfinite(x) for x in (lower, upper)) or
                lower >= upper):
            raise ValueError("DOE variable requires finite continuous free bounds and CAD effect")
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
