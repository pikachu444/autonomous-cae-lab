"""TEST_ONLY numerical DOE functions; no solver or physical reference is run."""

from copy import deepcopy
from itertools import product
import json
import math

import numpy as np
import pytest

from caelab.optimizers.campaign_analysis import summarize


def _variables():
    return [
        {"parameter_id": "force_z", "lower_bound": -1.0, "upper_bound": 1.0,
         "unit": "N", "kind": "continuous", "mode": "free",
         "target": "analysis_conditions", "current_value": -0.25,
         "input_effect": {"status": "PASS", "detail": "TEST_ONLY declared binding"}},
        {"parameter_id": "width", "lower_bound": -1.0, "upper_bound": 1.0,
         "unit": "mm", "native": {"object": "TEST_ONLY", "property": "Width"},
         "geometry_effect": {"status": "PASS"}, "source": "TEST_ONLY DOE"},
    ]


def _responses():
    return [{"metric": "deflection", "unit": "mm", "direction": "minimize"}]


def _row(identifier, x, z, value, *, usable=True, valid=True):
    return {"id": identifier, "values": {"force_z": x, "width": z},
            "responses": {"deflection": {"value": value, "unit": "mm", "valid": valid}},
            "usable": usable}


def _grid(function=lambda x, z: 7 + 3 * x - 5 * z, size=7):
    return [_row(f"E{index:03d}", float(x), float(z), float(function(x, z)))
            for index, (x, z) in enumerate(product(np.linspace(-1, 1, size), repeat=2))]


def test_closed_linear_statistics_and_signed_multivariate_associations_keep_units():
    samples, variables, responses = _grid(), _variables(), _responses()
    before = deepcopy((samples, variables, responses))
    result = summarize(samples, variables, responses)
    assert set(result) == {"statistics", "sensitivity", "surrogate", "pareto", "exclusions",
                           "qualification", "decision", "limitations"}
    stats = result["statistics"][0]
    expected_std = math.sqrt(sum((row["responses"]["deflection"]["value"] - 7)**2
                                 for row in samples) / (len(samples) - 1))
    assert stats["mean"] == pytest.approx(7)
    assert stats["std"] == pytest.approx(expected_std)
    assert (stats["metric"], stats["unit"], stats["count"], stats["min"], stats["max"]) == (
        "deflection", "mm", 49, -1, 15)
    original = sorted(row["responses"]["deflection"]["value"] for row in samples)
    # Linear empirical interpolation at index (n-1)*q, not a population interval.
    assert stats["quantiles"]["q05"] == pytest.approx(original[2] * .6 + original[3] * .4)
    assert stats["quantiles"]["q50"] == pytest.approx(7)
    sensitivity = result["sensitivity"][0]
    x_std = math.sqrt(sum(row["values"]["force_z"]**2 for row in samples) / 48)
    assert sensitivity["valid"] and sensitivity["rank"] == 3
    assert sensitivity["response_mean"] == pytest.approx(7)
    assert sensitivity["response_std"] == pytest.approx(expected_std)
    assert sensitivity["coefficients"] == [
        {"parameter_id": "force_z", "unit": "1", "parameter_unit": "N",
         "coefficient": pytest.approx(3 * x_std / expected_std)},
        {"parameter_id": "width", "unit": "1", "parameter_unit": "mm",
         "coefficient": pytest.approx(-5 * x_std / expected_std)},
    ]
    fit = result["surrogate"][0]
    assert fit["valid"] and fit["model"] == "affine" and fit["rank"] == 3
    assert fit["test_max_error"] < 1e-12
    assert [item["value"] for item in fit["coefficients"]] == pytest.approx([7, 3, -5])
    assert all(item["unit"] == "mm" for item in fit["coefficients"])
    assert set(fit["train_ids"]).isdisjoint(fit["test_ids"])
    assert sorted(fit["train_ids"] + fit["test_ids"]) == sorted(row["id"] for row in samples)
    assert len(fit["test_ids"]) == 13 and len(fit["train_ids"]) == 36
    assert result["qualification"] == "NUMERICAL_SAMPLE_ANALYSIS_ONLY"
    assert result["decision"] == "NOT_RELEASED"
    assert not result["pareto"]["valid"]
    assert (samples, variables, responses) == before
    json.dumps(result, allow_nan=False)


def test_exact_quadratic_selects_full_rank_basis_and_validates_independent_holdout():
    samples = _grid(lambda x, z: 2 + 3*x - 4*z + 2*x*x + x*z + .5*z*z, size=9)
    result = summarize(samples, _variables(), _responses(), seed=31)
    fit = result["surrogate"][0]
    assert fit["valid"] and fit["model"] == "quadratic" and fit["rank"] == 6
    by_id = {row["feature_id"]: row["value"] for row in fit["coefficients"]}
    coefficients = {tuple(sorted(row["powers"].items())): by_id[row["id"]]
                    for row in fit["features"]}
    assert coefficients == {
        (): pytest.approx(2), (("force_z", 1),): pytest.approx(3),
        (("width", 1),): pytest.approx(-4), (("force_z", 2),): pytest.approx(2),
        (("width", 2),): pytest.approx(.5),
        (("force_z", 1), ("width", 1)): pytest.approx(1),
    }
    assert fit["test_rmse"] < 1e-12 and fit["test_mae"] < 1e-12
    assert fit["normalization"] == [
        {"parameter_id": "force_z", "unit": "N", "lower_bound": -1., "upper_bound": 1.},
        {"parameter_id": "width", "unit": "mm", "lower_bound": -1., "upper_bound": 1.},
    ]


@pytest.mark.parametrize("function", [lambda x, z: 7 + 3*x - 5*z,
                                      lambda x, z: 2 + x*x - 3*x*z])
def test_holdout_response_mutation_cannot_select_degree_or_change_training_fit(function):
    samples = _grid(function, size=9)
    original = summarize(samples, _variables(), _responses(), seed=13)["surrogate"][0]
    changed = deepcopy(samples)
    for row in changed:
        if row["id"] in original["test_ids"]:
            row["responses"]["deflection"]["value"] += 1000
    fit = summarize(changed, _variables(), _responses(), seed=13)["surrogate"][0]
    for key in ("coefficients", "features", "model", "rank", "condition_number", "normalization",
                "train_ids", "test_ids"):
        assert fit[key] == original[key]
    assert fit["test_mae"] == pytest.approx(1000)
    assert original["test_mae"] < 1e-12


def test_seeded_replay_is_canonical_to_sample_order_without_mutation():
    samples = _grid()
    original = deepcopy(samples)
    result = summarize(samples, _variables(), _responses(), seed=13)
    assert result == summarize(list(reversed(samples)), _variables(), _responses(), seed=13)
    assert result["surrogate"][0]["test_ids"] != summarize(
        samples, _variables(), _responses(), seed=14)["surrogate"][0]["test_ids"]
    assert samples == original


def test_nonlinear_holdout_reports_nonzero_error_without_accuracy_or_causal_claim():
    samples = _grid(lambda x, z: math.sin(4*math.pi*x) + math.cos(3*math.pi*z), size=11)
    result = summarize(samples, _variables(), _responses())
    fit = result["surrogate"][0]
    assert fit["valid"] and fit["model"] == "quadratic"
    assert fit["test_rmse"] > .2
    assert fit["reason"] is None
    assert "accuracy acceptance threshold" in " ".join(fit["limitations"])
    assert "not causal effects or Sobol" in " ".join(result["limitations"])
    assert result["decision"] == "NOT_RELEASED"


def test_affine_fit_is_kept_with_explicit_limitation_when_quadratic_is_underdetermined():
    samples = [_row(f"E{i}", x, z, x*x + 2*z*z)
               for i, (x, z) in enumerate([(-1, -1), (-.5, -.8), (.25, -.3),
                                           (.75, .5), (0, .7), (1, 1)])]
    result = summarize(samples, _variables(), _responses(), seed=3)
    fit = result["surrogate"][0]
    assert fit["valid"] and fit["model"] == "affine"
    assert any("Quadratic training fit is unsupported" in text for text in fit["limitations"])
    assert fit["test_max_error"] > .1


def test_failed_or_any_invalid_response_excludes_whole_row_without_zero_substitution():
    definitions = _responses() + [{"metric": "reaction", "unit": "N", "direction": "maximize"}]
    samples = _grid()
    for row in samples:
        row["responses"]["reaction"] = {"value": -2., "unit": "N", "valid": True}
    samples[0]["usable"] = False
    samples[1]["responses"]["reaction"] = {"value": None, "unit": "N", "valid": False,
                                             "reason": "TEST_ONLY unavailable native response"}
    samples[2]["responses"]["deflection"]["valid"] = False
    before = deepcopy(samples)
    result = summarize(samples, _variables(), definitions)
    assert result["exclusions"] == [
        {"id": "E000", "reason": "ROW_UNUSABLE"},
        {"id": "E001", "reason": "INVALID_RESPONSE:reaction"},
        {"id": "E002", "reason": "INVALID_RESPONSE:deflection"},
    ]
    assert all(row["count"] == 46 for row in result["statistics"])
    assert result["statistics"][0]["mean"] == pytest.approx(
        sum(row["responses"]["deflection"]["value"] for row in samples[3:]) / 46)
    assert all("E000" not in row["sample_ids"] for row in result["sensitivity"])
    assert all("E001" not in row["train_ids"] + row["test_ids"] for row in result["surrogate"])
    assert not set(["E000", "E001", "E002"]) & set(result["pareto"]["nondominated_ids"])
    assert samples == before
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("remaining", [0, 1])
def test_empty_or_single_eligible_cohort_is_truthful_and_finite(remaining):
    samples = _grid()
    for row in samples[remaining:]:
        row["usable"] = False
        row["responses"]["deflection"] = {"value": None, "unit": "mm", "valid": False}
    result = summarize(samples, _variables(), _responses())
    stats = result["statistics"][0]
    assert stats["count"] == remaining and stats["std"] is None
    if remaining == 0:
        assert stats["mean"] is None and stats["min"] is None and stats["max"] is None
        assert stats["quantiles"] == {"q05": None, "q50": None, "q95": None}
    else:
        assert stats["mean"] == samples[0]["responses"]["deflection"]["value"]
    for item in result["sensitivity"] + result["surrogate"]:
        assert item["valid"] is False and item["coefficients"] == [] and item["reason"]
    assert result["surrogate"][0]["test_mae"] is None
    assert result["surrogate"][0]["test_rmse"] is None
    json.dumps(result, allow_nan=False)


def test_collinear_design_refuses_fit_but_keeps_actual_statistics():
    samples = [_row(f"E{i}", float(x), float(x), float(2*x))
               for i, x in enumerate(np.linspace(-1, 1, 25))]
    result = summarize(samples, _variables(), _responses())
    assert result["statistics"][0]["count"] == 25
    for item in result["sensitivity"] + result["surrogate"]:
        assert not item["valid"] and item["reason"] == "RANK_DEFICIENT"
        assert item["rank"] == 2 and item["condition_number"] is None
        assert item["coefficients"] == []
    assert result["surrogate"][0]["test_max_error"] is None


def test_near_collinear_design_is_reported_as_unsupported_not_engineering_failure():
    samples = [_row(f"E{i}", float(x), float(x + (1e-13 if i % 2 else -1e-13)), float(2*x))
               for i, x in enumerate(np.linspace(-.9, .9, 25))]
    result = summarize(samples, _variables(), _responses())
    for item in result["sensitivity"] + result["surrogate"]:
        assert not item["valid"] and item["reason"] in ("RANK_DEFICIENT", "ILL_CONDITIONED")
        if item["reason"] == "ILL_CONDITIONED":
            assert math.isfinite(item["condition_number"]) and item["condition_number"] > 1e12
    assert result["qualification"] == "NUMERICAL_SAMPLE_ANALYSIS_ONLY"


@pytest.mark.parametrize("constant_input", [False, True])
def test_constant_variance_has_no_invented_zero_sensitivity(constant_input):
    samples = _grid(lambda x, z: 0.)
    if constant_input:
        for row in samples:
            row["values"]["force_z"] = 0.
            row["responses"]["deflection"]["value"] = row["values"]["width"]
    result = summarize(samples, _variables(), _responses())
    item = result["sensitivity"][0]
    assert item["reason"] == ("CONSTANT_INPUT" if constant_input else "CONSTANT_RESPONSE")
    assert not item["valid"] and item["coefficients"] == []
    json.dumps(result, allow_nan=False)


def test_pareto_mixed_directions_keeps_equal_original_ids_and_uses_common_cohort():
    definitions = [{"metric": "cost", "unit": "USD", "direction": "minimize"},
                   {"metric": "benefit", "unit": "N", "direction": "maximize"}]
    samples = []
    for identifier, a, b in [("Ea", 1, 2), ("Eb", 2, 3), ("Ec", 3, 1),
                             ("Ed", 1, 2), ("Ee", 4, 4), ("Ef", .5, 10)]:
        row = _row(identifier, 0., 0., 0.)
        row["responses"] = {"cost": {"value": a, "unit": "USD", "valid": True},
                            "benefit": {"value": b, "unit": "N", "valid": identifier != "Ef"}}
        samples.append(row)
    result = summarize(samples, _variables(), definitions)
    assert result["pareto"]["valid"]
    assert result["pareto"]["nondominated_ids"] == ["Ea", "Eb", "Ed", "Ee"]
    assert result["pareto"]["response_definitions"] == definitions
    reverse = deepcopy(definitions)
    reverse[1]["direction"] = "minimize"
    assert summarize(samples, _variables(), reverse)["pareto"]["nondominated_ids"] == ["Ea", "Ec", "Ed"]
    assert result["exclusions"] == [{"id": "Ef", "reason": "INVALID_RESPONSE:benefit"}]
    assert result["statistics"][1]["min"] == 1 and result["statistics"][1]["max"] == 4


def test_no_eligible_multiresponse_pareto_is_explicitly_unavailable():
    samples = _grid()
    definitions = _responses() + [{"metric": "force", "unit": "N", "direction": "maximize"}]
    for row in samples:
        row["responses"]["force"] = {"value": None, "unit": "N", "valid": False}
    archive = summarize(samples, _variables(), definitions)["pareto"]
    assert archive["valid"] is False and archive["reason"] == "NO_ELIGIBLE_SAMPLES"
    assert archive["nondominated_ids"] == []


@pytest.mark.parametrize("mutate", [
    lambda s, v, r: s[0].update(extra=True),
    lambda s, v, r: s[0].pop("usable"),
    lambda s, v, r: s[0].update(usable=1),
    lambda s, v, r: s[0].update(id="../escape"),
    lambda s, v, r: s[1].update(id=s[0]["id"]),
    lambda s, v, r: s[0]["values"].update(unregistered=0),
    lambda s, v, r: s[0]["values"].pop("width"),
    lambda s, v, r: s[0]["values"].update(force_z=True),
    lambda s, v, r: s[0]["values"].update(force_z=math.nan),
    lambda s, v, r: s[0]["values"].update(force_z=math.inf),
    lambda s, v, r: s[0]["values"].update(force_z=-1.01),
    lambda s, v, r: s[0]["responses"].update(other={"value": 1, "unit": "mm", "valid": True}),
    lambda s, v, r: s[0]["responses"].clear(),
    lambda s, v, r: s[0]["responses"]["deflection"].update(extra=0),
    lambda s, v, r: s[0]["responses"]["deflection"].update(valid=1),
    lambda s, v, r: s[0]["responses"]["deflection"].update(value=True),
    lambda s, v, r: s[0]["responses"]["deflection"].update(value=math.nan),
    lambda s, v, r: s[0]["responses"]["deflection"].update(value=math.inf),
    lambda s, v, r: s[0]["responses"]["deflection"].update(value=[1, 2]),
    lambda s, v, r: s[0]["responses"]["deflection"].update(value=None),
    lambda s, v, r: s[0]["responses"]["deflection"].update(unit=""),
    lambda s, v, r: s[0]["responses"]["deflection"].update(unit="m"),
    lambda s, v, r: v[0].update(extra=0),
    lambda s, v, r: v[1].update(parameter_id=v[0]["parameter_id"]),
    lambda s, v, r: v[0].update(lower_bound=True),
    lambda s, v, r: v[0].update(lower_bound=1.),
    lambda s, v, r: v[0].update(upper_bound=-2.),
    lambda s, v, r: v[0].update(upper_bound=math.inf),
    lambda s, v, r: v[0].update(unit=" "),
    lambda s, v, r: v[0]["input_effect"].update(observed=math.nan),
    lambda s, v, r: r[0].update(direction="auto"),
    lambda s, v, r: r[0].update(extra=True),
    lambda s, v, r: r[0].update(unit=""),
    lambda s, v, r: r.append(deepcopy(r[0])),
])
def test_malformed_input_is_refused_without_mutating_or_silently_filtering(mutate):
    samples, variables, responses = _grid(), _variables(), _responses()
    mutate(samples, variables, responses)
    before = deepcopy((samples, variables, responses))
    with pytest.raises(ValueError):
        summarize(samples, variables, responses)
    # NaN is intentionally not equal to itself; compare the retained JSON tokens.
    assert json.dumps((samples, variables, responses), sort_keys=True) == json.dumps(before, sort_keys=True)


@pytest.mark.parametrize("value", [math.nan, math.inf, True, [], "unknown"])
def test_invalid_or_unusable_response_cannot_hide_malformed_numeric_value(value):
    samples = _grid()
    samples[0]["usable"] = False
    samples[0]["responses"]["deflection"].update(value=value, valid=False)
    with pytest.raises(ValueError):
        summarize(samples, _variables(), _responses())


@pytest.mark.parametrize("seed", [True, -1, 2**32, 13.0, None])
def test_seed_requires_explicit_bounded_integer(seed):
    with pytest.raises(ValueError, match="seed"):
        summarize(_grid(), _variables(), _responses(), seed=seed)


@pytest.mark.parametrize("which,count", [("samples", 1), ("samples", 513),
                                         ("variables", 0), ("variables", 17),
                                         ("responses", 0), ("responses", 17)])
def test_declared_resource_envelope_refuses_outside_counts(which, count):
    samples, variables, responses = _grid(), _variables(), _responses()
    if which == "samples":
        samples = [_row(f"E{i}", 0, 0, i) for i in range(count)]
    elif which == "variables":
        variables = [{"parameter_id": f"V{i}", "unit": "1", "lower_bound": 0, "upper_bound": 1}
                     for i in range(count)]
    else:
        responses = [{"metric": f"M{i}", "unit": "1", "direction": "minimize"} for i in range(count)]
    with pytest.raises(ValueError, match="rows"):
        summarize(samples, variables, responses)


def test_512_rows_are_supported_and_remain_finite_json():
    variables = [{"parameter_id": "force", "unit": "N", "lower_bound": -1., "upper_bound": 1.}]
    samples = [{"id": f"E{i:03d}", "values": {"force": float(x)},
                "responses": {"deflection": {"value": float(2*x - 1), "unit": "mm", "valid": True}},
                "usable": True} for i, x in enumerate(np.linspace(-1, 1, 512))]
    result = summarize(samples, variables, _responses())
    assert result["statistics"][0]["count"] == 512
    assert result["surrogate"][0]["valid"] and result["surrogate"][0]["test_max_error"] < 1e-12
    json.dumps(result, allow_nan=False)


def test_finite_large_values_do_not_overflow_just_from_squaring_statistics():
    samples = _grid(lambda x, z: x * 1e308)
    result = summarize(samples, _variables(), _responses())
    assert result["statistics"][0]["std"] < 1e308
    assert result["statistics"][0]["min"] == -1e308
    assert result["statistics"][0]["max"] == 1e308
    assert result["surrogate"][0]["valid"]
    json.dumps(result, allow_nan=False)


def test_truly_unrepresentable_derived_statistic_refuses_infinite_json():
    samples = [_row("Ea", -1., -1., -1.79e308), _row("Eb", 1., 1., 1.79e308)]
    with pytest.raises(ValueError, match="finite JSON"):
        summarize(samples, _variables(), _responses())
