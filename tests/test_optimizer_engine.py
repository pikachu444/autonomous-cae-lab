"""Numerical reference, reproducibility and invalid-feedback DE acceptance."""

import copy
import json

import numpy
import pytest

from caelab.optimizers.scipy_de import ScipyDifferentialEvolution


def _variables(names=("x", "y"), lower=0.0, upper=3.0):
    return [{"parameter_id": name, "lower_bound": lower, "upper_bound": upper,
             "kind": "continuous", "mode": "free", "geometry_effect": {"status": "PASS"}}
            for name in names]


def _quadratic(values):
    # The constrained analytical minimizer is (1, 1), f=2. The unconstrained
    # minimizer (2, 2) violates x+y <= 2, exercising actual constraint handling.
    x, y = values["x"], values["y"]
    return {"objective": (x - 2.0)**2 + (y - 2.0)**2,
            "constraint_residuals": [(x + y - 2.0) / 2.0]}


def test_real_constrained_quadratic_matches_analytical_reference():
    result = ScipyDifferentialEvolution().run(
        _variables(), _quadratic, seed=42, max_generations=160,
        population_size=16, initial_values={"x": 0.25, "y": 0.25}, constraint_count=1)
    assert result["converged"] and result["termination_reason"] == "CONVERGED"
    assert result["candidate_values"] == pytest.approx({"x": 1.0, "y": 1.0}, abs=3e-4)
    assert result["objective"] == pytest.approx(2.0, abs=1e-7)
    assert result["constraint_residuals"][0] <= 0.0
    assert 1 <= result["generations"] < 160
    assert result["evaluation_count"] > 16
    json.dumps(result, allow_nan=False)


def test_exact_evaluation_sequence_can_replay_and_callbacks_are_memoized():
    engine = ScipyDifferentialEvolution()
    options = {"seed": 13, "max_generations": 6, "population_size": 7,
               "initial_values": {"x": 0.5, "y": 0.5}, "constraint_count": 1}
    recorded = []

    def first(values):
        recorded.append((tuple(value.hex() for value in values.values()), _quadratic(values)))
        return recorded[-1][1]

    result = engine.run(_variables(), first, **options)
    index = 0

    def replay(values):
        nonlocal index
        exact, feedback = recorded[index]
        assert tuple(value.hex() for value in values.values()) == exact
        index += 1
        return copy.deepcopy(feedback)

    assert engine.run(_variables(), replay, **options) == result
    assert index == len(recorded) == result["evaluation_count"]
    assert len({values for values, _ in recorded}) == len(recorded)
    assert result["algorithm"] == engine.describe(_variables(), **options)
    assert len(recorded) > options["population_size"]  # At least one evolved generation.


def test_describe_freezes_absolute_lhs_population_and_x0_without_solving(monkeypatch):
    def no_solver(*args, **kwargs):
        raise AssertionError("describe must not execute the optimizer")

    monkeypatch.setattr("caelab.optimizers.scipy_de.differential_evolution", no_solver)
    engine = ScipyDifferentialEvolution()
    options = {"seed": 4, "max_generations": 1, "population_size": 5,
               "initial_values": None, "constraint_count": 0}
    description = engine.describe(_variables(), **options)
    assert len(description["initial_population"]) == 5  # Not 5 * dimension.
    assert description == engine.describe(_variables(), **options)
    for name in ("x", "y"):
        strata = [int(point[name] / 3.0 * 5) for point in description["initial_population"]]
        assert sorted(strata) == list(range(5))
    options["initial_values"] = {"x": 0.0, "y": 3.0}
    with_initial = engine.describe(_variables(), **options)
    assert with_initial["initial_population"][0] == options["initial_values"]
    assert with_initial["initial_population"][1:] == description["initial_population"][1:]
    json.dumps(with_initial, allow_nan=False)


@pytest.mark.parametrize("constraint_count", [0, 1])
def test_invalid_objective_cannot_displace_valid_feasible_candidate(constraint_count):
    invalid_seen = []

    def evaluate(values):
        x = values["x"]
        if x > 0.5:
            invalid_seen.append(x)
            return {"objective": None, "constraint_residuals": [-1.0] * constraint_count}
        return {"objective": (x - 0.4)**2 + 1.0,
                "constraint_residuals": [-1.0] * constraint_count}

    result = ScipyDifferentialEvolution().run(
        _variables(("x",), upper=1.0), evaluate, seed=7, max_generations=12,
        population_size=8, initial_values={"x": 0.4}, constraint_count=constraint_count)
    assert invalid_seen
    assert result["objective"] == pytest.approx(1.0, abs=1e-8)
    assert result["candidate_values"]["x"] <= 0.5
    json.dumps(result, allow_nan=False)


def test_invalid_constraint_cannot_be_selected_with_a_better_objective():
    def evaluate(values):
        x = values["x"]
        if x > 0.5:
            return {"objective": -100.0, "constraint_residuals": [None]}
        return {"objective": (x - 0.4)**2 + 1.0, "constraint_residuals": [-1.0]}

    result = ScipyDifferentialEvolution().run(
        _variables(("x",), upper=1.0), evaluate, seed=7, max_generations=12,
        population_size=8, initial_values={"x": 0.4}, constraint_count=1)
    assert result["candidate_values"]["x"] <= 0.5
    assert result["objective"] == pytest.approx(1.0, abs=1e-8)
    assert result["constraint_residuals"] == [-1.0]


def test_all_invalid_feedback_stays_null_and_never_converges():
    result = ScipyDifferentialEvolution().run(
        _variables(("x",), upper=1.0),
        lambda values: {"objective": None, "constraint_residuals": [None]},
        seed=7, max_generations=2, population_size=5, constraint_count=1)
    assert not result["converged"]
    assert result["termination_reason"] == "MAX_GENERATIONS"
    assert result["generations"] == 2
    assert result["objective"] is None and result["constraint_residuals"] == [None]
    json.dumps(result, allow_nan=False)


def test_generation_budget_is_not_reported_as_convergence():
    result = ScipyDifferentialEvolution().run(
        _variables(), _quadratic, seed=42, max_generations=1,
        population_size=5, constraint_count=1)
    assert not result["converged"] and result["termination_reason"] == "MAX_GENERATIONS"
    assert result["generations"] == 1
    assert result["evaluation_count"] > 5


@pytest.mark.parametrize("exception_type", [RuntimeError, ValueError, TypeError, StopIteration])
def test_callback_failures_propagate_unchanged(exception_type):
    failure = exception_type("interrupted evaluation")
    count = 0

    def evaluate(values):
        nonlocal count
        count += 1
        if count == 7:
            raise failure
        return _quadratic(values)

    with pytest.raises(exception_type) as raised:
        ScipyDifferentialEvolution().run(
            _variables(), evaluate, seed=42, max_generations=3,
            population_size=5, constraint_count=1)
    assert raised.value is failure
    assert count == 7


@pytest.mark.parametrize("feedback", [
    {}, {"objective": 1.0}, {"objective": 1.0, "constraint_residuals": []},
    {"objective": numpy.inf, "constraint_residuals": [0.0]},
    {"objective": numpy.nan, "constraint_residuals": [0.0]},
    {"objective": 1.0, "constraint_residuals": [numpy.inf]},
    {"objective": 1.0, "constraint_residuals": [numpy.nan]},
    {"objective": True, "constraint_residuals": [0.0]},
    {"objective": 1.0, "constraint_residuals": [False]},
])
def test_invalid_feedback_shape_or_nonfinite_numbers_are_rejected(feedback):
    with pytest.raises(ValueError):
        ScipyDifferentialEvolution().run(
            _variables(), lambda values: feedback, seed=4,
            max_generations=1, population_size=5, constraint_count=1)


@pytest.mark.parametrize("change", [
    {"parameter_id": ""}, {"kind": "integer"}, {"mode": "fixed"},
    {"geometry_effect": {"status": "UNKNOWN"}}, {"geometry_effect": None},
    {"lower_bound": 3.0}, {"lower_bound": 4.0}, {"upper_bound": numpy.inf},
    {"lower_bound": numpy.nan}, {"lower_bound": True},
    {"lower_bound": -1e308, "upper_bound": 1e308},
])
def test_registry_variable_validation(change):
    variables = _variables()
    variables[0].update(change)
    with pytest.raises(ValueError):
        ScipyDifferentialEvolution().describe(
            variables, seed=4, max_generations=1, population_size=5, constraint_count=0)


@pytest.mark.parametrize("variables", [[], _variables(("x", "x")), [None], [{}]])
def test_empty_duplicate_or_missing_variable_entries_are_rejected(variables):
    with pytest.raises(ValueError):
        ScipyDifferentialEvolution().describe(
            variables, seed=4, max_generations=1, population_size=5, constraint_count=0)


@pytest.mark.parametrize("change", [
    {"seed": True}, {"seed": -1}, {"seed": 2**32}, {"seed": 1.0},
    {"max_generations": 0}, {"max_generations": True}, {"max_generations": 1.5},
    {"population_size": 4}, {"population_size": True}, {"population_size": 5.0},
    {"constraint_count": -1}, {"constraint_count": True}, {"constraint_count": 1.0},
    {"initial_values": {"x": 1.0}}, {"initial_values": {"x": 1.0, "y": 1.0, "z": 1.0}},
    {"initial_values": {"x": -0.1, "y": 1.0}},
    {"initial_values": {"x": numpy.nan, "y": 1.0}},
    {"initial_values": {"x": True, "y": 1.0}},
])
def test_configuration_validation(change):
    options = {"seed": 4, "max_generations": 1, "population_size": 5,
               "constraint_count": 0, "initial_values": None}
    options.update(change)
    with pytest.raises(ValueError):
        ScipyDifferentialEvolution().describe(_variables(), **options)
