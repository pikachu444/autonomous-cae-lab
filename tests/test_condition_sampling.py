"""Actual seeded SciPy engines with TEST_ONLY declared condition bindings.

The analytic callbacks below test numerical admission/replay only. They do not
run CAD/native solvers or supply measured material/load/engineering evidence.
"""

from copy import deepcopy
import json
import math

import pytest

from caelab.optimizers.scipy_de import ScipyDifferentialEvolution
from caelab.optimizers.scipy_lhs import sample


def _conditions():
    return [
        {"parameter_id": "force_z", "target": "analysis_conditions", "unit": "N",
         "kind": "continuous", "mode": "free", "lower_bound": -240.0, "upper_bound": -80.0,
         "current_value": -150.0, "input_effect": {"status": "PASS", "detail": "TEST_ONLY declared round-trip"}},
        {"parameter_id": "elastic_E", "target": "analysis_conditions", "unit": "MPa",
         "kind": "continuous", "mode": "free", "lower_bound": 70000.0, "upper_bound": 210000.0,
         "current_value": 210000.0, "input_effect": {"status": "PASS", "detail": "TEST_ONLY declared round-trip"}}]


def _admit(engine, variables):
    if engine == "lhs":
        return sample(variables, count=7, seed=13)
    return ScipyDifferentialEvolution().describe(
        variables, seed=13, max_generations=2, population_size=7, constraint_count=1)


def test_actual_lhs_preserves_signed_units_strata_and_identical_seeded_geometry_sequence():
    variables = _conditions()
    variables.append({"parameter_id": "width", "unit": "mm", "kind": "continuous", "mode": "free",
                      "lower_bound": 28.0, "upper_bound": 42.0, "geometry_effect": {"status": "PASS"}})
    before = deepcopy(variables)
    points, metadata = sample(variables, count=7, seed=13)
    assert (points, metadata) == sample(variables, count=7, seed=13)
    assert points != sample(variables, count=7, seed=14)[0]
    geometry = deepcopy(variables)
    for item in geometry:
        item.pop("target", None)
        item["geometry_effect"] = {"status": "PASS"}
    # Admission changes cannot change the RNG, dimensional order or scaling.
    assert (points, metadata) == sample(geometry, count=7, seed=13)
    for variable in variables:
        name, lower, upper = variable["parameter_id"], variable["lower_bound"], variable["upper_bound"]
        assert all(math.isfinite(point[name]) and lower <= point[name] <= upper for point in points)
        strata = [int((point[name] - lower) / (upper - lower) * 7) for point in points]
        assert sorted(strata) == list(range(7))
    assert all(point["force_z"] < 0 for point in points)
    assert [item["unit"] for item in variables] == ["N", "MPa", "mm"]
    assert metadata["seed"] == 13 and metadata["strength"] == 1 and metadata["optimization"] is None
    assert variables == before
    json.dumps((points, metadata), allow_nan=False)


def test_actual_de_condition_callbacks_replay_exactly_and_keep_native_input_signs():
    variables = _conditions()
    before = deepcopy(variables)
    engine = ScipyDifferentialEvolution()
    options = {"seed": 13, "max_generations": 2, "population_size": 7, "constraint_count": 1,
               "initial_values": {"force_z": -160.0, "elastic_E": 140000.0}}
    observed = []

    def evaluate(values):
        assert set(values) == {"force_z", "elastic_E"}
        for entry in variables:
            value = values[entry["parameter_id"]]
            assert type(value) is float and math.isfinite(value)
            assert entry["lower_bound"] <= value <= entry["upper_bound"]
        assert values["force_z"] < 0
        feedback = {"objective": ((values["force_z"] + 160.0) / 80.0)**2
                                 + ((values["elastic_E"] - 140000.0) / 70000.0)**2,
                    "constraint_residuals": [(values["force_z"] + 120.0) / 80.0]}
        observed.append((deepcopy(values), deepcopy(feedback)))
        return feedback

    result = engine.run(variables, evaluate, **options)
    index = 0

    def replay(values):
        nonlocal index
        previous, feedback = observed[index]
        assert [value.hex() for value in values.values()] == [value.hex() for value in previous.values()]
        index += 1
        return deepcopy(feedback)

    assert engine.run(variables, replay, **options) == result
    assert index == len(observed) == result["evaluation_count"]
    assert len({tuple(value.hex() for value in row.values()) for row, _ in observed}) == len(observed)
    assert len(observed) > options["population_size"]
    # Known TEST_ONLY quadratic optimum; this is not a structural response.
    assert result["candidate_values"] == options["initial_values"]
    assert result["objective"] == 0.0 and result["constraint_residuals"] == [-.5]
    assert result["algorithm"] == engine.describe(variables, **options)
    assert variables == before
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("target", [None, "cad"])
@pytest.mark.parametrize("engine", ["lhs", "de"])
def test_existing_cad_effect_admission_and_seeded_population_are_preserved(engine, target):
    variables = _conditions()
    for entry in variables:
        entry.pop("target")
        entry.pop("input_effect")
        entry["geometry_effect"] = {"status": "PASS"}
    original = _admit(engine, variables)
    if target is not None:
        for entry in variables:
            entry["target"] = target
    assert _admit(engine, variables) == original


def test_de_existing_model_inputs_keep_the_same_seeded_population():
    conditions = _conditions()
    model = deepcopy(conditions)
    for entry in model:
        entry["target"] = "model_analysis"
    assert _admit("de", model) == _admit("de", conditions)
    # Model-input DOE now uses the same admitted binding effect and the same
    # seeded sampler. The Domain target cannot alter points or their order.
    assert _admit("lhs", model) == _admit("lhs", conditions)


@pytest.mark.parametrize("engine", ["lhs", "de"])
@pytest.mark.parametrize("change", [
    {"target": "arbitrary"}, {"target": None}, {"target": True},
    {"input_effect": None}, {"input_effect": {}}, {"input_effect": "PASS"},
    {"input_effect": {"status": "UNKNOWN"}}, {"input_effect": {"status": "FAIL"}},
    {"kind": "integer"}, {"mode": "fixed"},
    {"lower_bound": True}, {"upper_bound": False},
    {"lower_bound": float("nan")}, {"upper_bound": float("inf")},
    {"lower_bound": -80.0}, {"lower_bound": 0.0},
    {"lower_bound": -1e308, "upper_bound": 1e308},
    pytest.param({"upper_bound": 10**1000}, id="unrepresentable-integer-bound"),
    {"current_value": True}, {"current_value": None}, {"current_value": "-150"},
    {"current_value": float("nan")}, {"current_value": float("inf")},
    {"current_value": -241.0}, {"current_value": -79.0},
    pytest.param({"current_value": 10**1000}, id="unrepresentable-integer-current"),
    pytest.param({"lower_bound": 10**16, "upper_bound": 10**16 + 4, "current_value": 10**16 + 5},
                 id="out-of-bounds-before-float-rounding")])
def test_invalid_conditions_refuse_even_with_a_pass_geometry_effect(engine, change):
    variables = _conditions()
    variables[0]["geometry_effect"] = {"status": "PASS"}
    variables[0].update(change)
    before = deepcopy(variables)
    with pytest.raises(ValueError):
        _admit(engine, variables)
    # NaN is retained as the exact original object, without coercion or clipping.
    assert variables == before


@pytest.mark.parametrize("engine", ["lhs", "de"])
def test_missing_input_effect_cannot_fall_back_to_cad_or_mutate_the_entry(engine):
    variables = _conditions()
    variables[0].pop("input_effect")
    variables[0]["geometry_effect"] = {"status": "PASS"}
    before = deepcopy(variables)
    with pytest.raises(ValueError):
        _admit(engine, variables)
    assert variables == before


@pytest.mark.parametrize("initial", [
    {"force_z": -241.0, "elastic_E": 140000.0}, {"force_z": -79.0, "elastic_E": 140000.0},
    {"force_z": True, "elastic_E": 140000.0}, {"force_z": -150.0, "elastic_E": float("nan")}])
def test_invalid_initial_conditions_never_invoke_a_numeric_callback(initial):
    def forbidden(values):
        raise AssertionError("Invalid initial conditions must refuse before numerical feedback")

    with pytest.raises(ValueError):
        ScipyDifferentialEvolution().run(_conditions(), forbidden, seed=13, max_generations=2,
            population_size=7, constraint_count=0, initial_values=initial)


@pytest.mark.parametrize("engine", ["lhs", "de"])
@pytest.mark.parametrize("variables", [[], [None], [{}], [_conditions()[0], _conditions()[0]]])
def test_malformed_or_duplicate_registry_variables_are_refused(engine, variables):
    with pytest.raises(ValueError):
        _admit(engine, variables)
