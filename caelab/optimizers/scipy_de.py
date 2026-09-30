"""Deterministic, bounded differential evolution behind the numerical boundary.

Core supplies a minimization score and dimensionless constraint residuals
(``<= 0`` is feasible). Missing feedback remains ``None`` outside SciPy;
only the solver's callbacks see infinite infeasibility. This module neither
chooses engineering metrics nor executes CAD/analysis or persists a journal.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy
import scipy
from scipy.optimize import NonlinearConstraint, differential_evolution
from scipy.stats import qmc


ENGINE = "scipy.differential_evolution"


def _finite_number(value: object, label: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite number")
    try:
        number = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError(f"{label} must be a finite number") from error
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def _validated_variables(variables: list[dict]) -> tuple[list[str], list[list[float]]]:
    if not isinstance(variables, list) or not variables:
        raise ValueError("Optimization requires at least one registered variable")
    names, bounds = [], []
    for variable in variables:
        if not isinstance(variable, dict):
            raise ValueError("Optimization variables must be registry entries")
        name = variable.get("parameter_id")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("Optimization variable IDs must be nonempty and distinct")
        effect = variable.get("geometry_effect")
        if (variable.get("kind") != "continuous" or variable.get("mode") != "free" or
                not isinstance(effect, dict) or effect.get("status") != "PASS"):
            raise ValueError("Optimization requires continuous free variables with PASS CAD effect")
        lower = _finite_number(variable.get("lower_bound"), f"{name} lower bound")
        upper = _finite_number(variable.get("upper_bound"), f"{name} upper bound")
        if lower >= upper:
            raise ValueError("Optimization variable bounds must be strictly increasing")
        # SciPy scales through the sum and difference of these limits. Refuse
        # finite endpoints whose range would overflow that representation.
        if not math.isfinite(upper - lower) or not math.isfinite(upper + lower):
            raise ValueError("Optimization bounds must have a finite scaling range")
        names.append(name)
        bounds.append([lower, upper])
    return names, bounds


def _validated_feedback(feedback: dict, constraint_count: int) -> dict:
    if not isinstance(feedback, dict) or "objective" not in feedback:
        raise ValueError("Evaluation must return objective and constraint_residuals")
    objective = feedback["objective"]
    if objective is not None:
        objective = _finite_number(objective, "Evaluation objective")
    residuals = feedback.get("constraint_residuals")
    if not isinstance(residuals, list) or len(residuals) != constraint_count:
        raise ValueError("Evaluation constraint_residuals must match constraint_count")
    return {"objective": objective,
            "constraint_residuals": [None if value is None else
                                     _finite_number(value, "Evaluation constraint residual")
                                     for value in residuals]}


class ScipyDifferentialEvolution:
    engine = ENGINE
    version = scipy.__version__

    def describe(self, variables: list[dict], *, seed: int, max_generations: int,
                 population_size: int, initial_values: dict[str, float] | None = None,
                 constraint_count: int) -> dict:
        """Validate and freeze the complete initial population without evaluations.

        ``population_size`` is an absolute count, unlike SciPy's ``popsize``
        multiplier. If supplied, ``initial_values`` must contain every variable
        and replaces the first LHS member, matching SciPy's public ``x0`` rule.
        """
        names, bounds = _validated_variables(variables)
        if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
            raise ValueError("Optimization seed must be an unsigned 32-bit integer")
        if type(max_generations) is not int or max_generations < 1:
            raise ValueError("Optimization max_generations must be a positive integer")
        if type(population_size) is not int or population_size < 5:
            raise ValueError("Optimization population_size must be an integer of at least 5")
        if type(constraint_count) is not int or constraint_count < 0:
            raise ValueError("Optimization constraint_count must be a nonnegative integer")
        x0 = None
        if initial_values is not None:
            if not isinstance(initial_values, dict) or set(initial_values) != set(names):
                raise ValueError("Optimization initial_values must contain exactly the variable IDs")
            x0 = {name: _finite_number(initial_values[name], f"{name} initial value")
                  for name in names}
            if any(not lower <= x0[name] <= upper
                   for name, (lower, upper) in zip(names, bounds)):
                raise ValueError("Optimization initial_values must lie within the variable bounds")

        unit_cube = qmc.LatinHypercube(
            d=len(names), scramble=True, strength=1, optimization=None,
            rng=numpy.random.default_rng(seed)).random(population_size)
        points = [{name: float(lower + (upper - lower) * row[index])
                   for index, (name, (lower, upper)) in enumerate(zip(names, bounds))}
                  for row in unit_cube]
        if x0 is not None:
            points[0] = x0.copy()
        return {"engine": self.engine, "version": self.version,
                "numpy_version": numpy.__version__, "seed": seed,
                "max_generations": max_generations, "population_size": population_size,
                "parameter_order": names, "bounds": bounds,
                "initial_population": points, "initial_values": x0,
                "initialization": {"engine": "scipy.stats.qmc.LatinHypercube",
                                   "scramble": True, "strength": 1, "optimization": None,
                                   "rng": "numpy.random.default_rng", "seed": seed},
                "rng": "numpy.random.default_rng", "strategy": "best1bin",
                "mutation": [0.5, 1.0], "recombination": 0.7,
                "tol": 1e-8, "atol": 1e-12, "polish": False,
                "workers": 1, "updating": "deferred", "vectorized": False,
                "constraint_count": constraint_count,
                "constraint_convention": "dimensionless_residual_le_zero",
                "internal_availability_constraint": True,
                "memoization": "exact_float_hex"}

    def run(self, variables: list[dict], evaluate: Callable, *, seed: int,
            max_generations: int, population_size: int,
            initial_values: dict[str, float] | None = None, constraint_count: int) -> dict:
        """Search using feedback; convergence is not proof of a global optimum.

        Repeat calls with the same frozen configuration and feedback regenerate
        the same exact-float evaluation sequence. Core can replay its persisted
        journal through ``evaluate``; no private solver state is serialized.
        """
        algorithm = self.describe(variables, seed=seed, max_generations=max_generations,
                                  population_size=population_size, initial_values=initial_values,
                                  constraint_count=constraint_count)
        if not callable(evaluate):
            raise ValueError("Optimization evaluate must be callable")
        names = algorithm["parameter_order"]
        cache: dict[tuple[str, ...], dict] = {}
        callback_error: BaseException | None = None

        def feedback_for(x) -> dict:
            nonlocal callback_error
            values = {name: _finite_number(float(value), f"{name} candidate value")
                      for name, value in zip(names, x)}
            key = tuple(values[name].hex() for name in names)
            if key not in cache:
                try:
                    cache[key] = _validated_feedback(evaluate(values), constraint_count)
                except BaseException as error:
                    # Some SciPy objective wrappers turn TypeError/ValueError
                    # into a generic map error. Preserve the original failure.
                    callback_error = error
                    raise
            return cache[key]

        def objective(x) -> float:
            value = feedback_for(x)["objective"]
            return numpy.inf if value is None else value

        def constraints(x):
            feedback = feedback_for(x)
            residuals = feedback["constraint_residuals"]
            available = feedback["objective"] is not None and all(
                value is not None for value in residuals)
            # The extra internal gate stops a missing objective with otherwise
            # valid residuals from being ranked as a feasible design. It is not
            # an engineering constraint and is not returned as public evidence.
            return numpy.asarray([numpy.inf if value is None else value for value in residuals]
                                 + [0.0 if available else numpy.inf], dtype=float)

        population = numpy.asarray([[point[name] for name in names]
                                    for point in algorithm["initial_population"]], dtype=float)
        x0 = (None if algorithm["initial_values"] is None else
              numpy.asarray([algorithm["initial_values"][name] for name in names], dtype=float))
        try:
            result = differential_evolution(
                objective, algorithm["bounds"], strategy=algorithm["strategy"],
                maxiter=max_generations, tol=algorithm["tol"], atol=algorithm["atol"],
                mutation=tuple(algorithm["mutation"]), recombination=algorithm["recombination"],
                rng=numpy.random.default_rng(seed), polish=False, init=population, x0=x0,
                updating="deferred", workers=1, vectorized=False,
                constraints=NonlinearConstraint(constraints, -numpy.inf, 0.0))
        except BaseException:
            if callback_error is not None:
                raise callback_error
            raise
        # SciPy also treats StopIteration during a generation as an internal
        # stop signal. Evaluation interruptions belong to Core's journal and
        # must propagate even when the public solver returns instead of raises.
        if callback_error is not None:
            raise callback_error
        feedback = feedback_for(result.x)
        feasible = (feedback["objective"] is not None and all(
            value is not None and value <= 0 for value in feedback["constraint_residuals"]))
        converged = bool(result.success) and feasible
        if converged:
            reason = "CONVERGED"
        elif int(result.nit) >= max_generations:
            reason = "MAX_GENERATIONS"
        elif not feasible:
            reason = "NO_FEASIBLE_VALID_CANDIDATE"
        else:
            reason = "NOT_CONVERGED"
        return {"algorithm": algorithm, "converged": converged,
                "termination_reason": reason, "generations": int(result.nit),
                "candidate_values": {name: float(value) for name, value in zip(names, result.x)},
                "objective": feedback["objective"],
                "constraint_residuals": feedback["constraint_residuals"],
                "evaluation_count": len(cache)}
