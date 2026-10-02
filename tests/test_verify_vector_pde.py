"""Source-only frozen-plan, independent calculus and provenance controls."""

from copy import deepcopy
import math

import pytest

from caelab.storage import save_json
from plugins.pde_vector.reference import validate_settings
from scripts import verify_vector_pde as runner


def field(count=1, experiment="E-vector-mixed", settings=None):
    settings = settings or runner.specification()
    coordinates = [[i/count, j/count] for j in range(count+1) for i in range(count+1)]
    ids = list(range(len(coordinates)))
    cells = []
    for j in range(count):
        for i in range(count):
            a = j*(count+1)+i
            b, c, d = a+1, a+count+1, a+count+2
            cells.extend([[a, b, d], [a, d, c]])
    return {"node_ids": ids, "coordinates": coordinates, "cell_node_ids": cells,
            "values": [runner._math(experiment, settings, x, y)["solution"] for x, y in coordinates]}


def test_frozen_controls_preserve_component_directions_and_fixed_criteria():
    accepted, rejected, refused = runner.cases()
    assert len(accepted) == 6 and len(rejected) == 3 and len(refused) == 5
    assert len(set(accepted) | set(rejected) | set(refused)) == 14
    assert sum(len(case["mesh"]["cell_counts"]) for case in [*accepted.values(), *rejected.values()]) == 27
    for settings in [*accepted.values(), *rejected.values()]:
        assert validate_settings(settings) == settings
        assert settings["validation"] == {"max_l2_error": .04, "max_h1_seminorm_error": .8,
            "min_l2_rate": 1.8, "min_h1_rate": .9, "max_residual_relative": 1e-10}
    base = accepted["E-vector-mixed"]
    assert rejected["E-vector-reference-reject"]["problem"]["reference"]["solution"] == [base["problem"]["reference"]["solution"][0], "0.0"]
    assert rejected["E-vector-source-swap-reject"]["problem"]["weak_form"]["rhs"] == base["problem"]["weak_form"]["rhs"][::-1]
    assert refused["E-vector-invalid-corner"]["problem"]["boundaries"]["xmin"]["value"][0] == base["problem"]["boundaries"]["xmin"]["value"][0]
    assert base["problem"]["weak_form"]["lame_lambda"] > 0
    assert accepted["E-vector-lambda-zero"]["problem"]["weak_form"]["lame_lambda"] == 0
    assert accepted["E-vector-harmonic-zero-source"]["problem"]["weak_form"]["rhs"] == ["0.0", "0.0"]


def test_direct_lame_source_shear_and_outward_signs():
    settings = runner.specification()
    observed = runner._math("E-vector-mixed", settings, .7, .3)
    x, y = .7, .3
    assert observed["rhs"] == pytest.approx([-2*x*x-6*y*y-16*x*y, -12*x*x-4*y*y-8*x*y])
    assert observed["stress"][0][1] == pytest.approx(2*x*x*y+4*x*y*y-1)
    assert observed["stress"][0][1] == observed["stress"][1][0]
    # Lower sides become N for this pure calculus check, without a native run.
    for side in ("xmin", "ymin"):
        settings["problem"]["boundaries"][side]["type"] = "neumann"
    assert runner._side_value("E-vector-mixed", settings, "xmin", 0., y) == pytest.approx([-4., 1.])
    assert runner._side_value("E-vector-mixed", settings, "ymin", x, 0.) == pytest.approx([1., -4.])
    flipped = runner._side_value("E-vector-traction-reject", settings, "xmax", 2., y)
    original = runner._side_value("E-vector-mixed", settings, "xmax", 2., y)
    assert flipped == pytest.approx([original[0], -original[1]])


def test_harmonic_divergence_and_zero_source_do_not_fake_lambda_coverage():
    settings = runner.cases()[0]["E-vector-harmonic-zero-source"]
    data = runner._math("E-vector-harmonic-zero-source", settings, .7, .3)
    assert data["rhs"] == [0., 0.]
    assert data["gradient"][0][0]+data["gradient"][1][1] == 0
    assert data["stress"] == [[2.8, -1.2], [-1.2, -2.8]]
    settings["problem"]["weak_form"]["lame_lambda"] = 9
    assert runner._math("E-vector-harmonic-zero-source", settings, .7, .3)["stress"] == data["stress"]
    settings["problem"]["weak_form"]["reaction"] = 3
    assert runner._math("E-vector-harmonic-zero-source", settings, .7, .3)["rhs"] == [3*value for value in data["solution"]]


def test_independent_duffy_matches_closed_unit_square_errors():
    # On these two triangles q_h=min(x,y) for q=x²y²; affine parts cancel.
    # Direct integrals: ||q_h-q||²=67/1050 and ||grad(q_h-q)||²=11/15.
    result = runner._integrate_field("E-vector-mixed", runner.specification(), field())
    assert result["component_l2"] == pytest.approx([math.sqrt(67/1050), 2*math.sqrt(67/1050)], rel=1e-12)
    assert result["component_h1"] == pytest.approx([math.sqrt(11/15), 2*math.sqrt(11/15)], rel=1e-12)
    assert result["l2"] == pytest.approx(math.sqrt(67/210), rel=1e-12)
    assert result["h1"] == pytest.approx(math.sqrt(11/3), rel=1e-12)


def test_duffy_handles_orientation_and_global_node_permutation():
    original = field()
    expected = runner._integrate_field("E-vector-mixed", runner.specification(), original)
    permutation = [2, 0, 3, 1]
    changed = {"node_ids": permutation,
        "coordinates": [original["coordinates"][node] for node in permutation],
        "values": [original["values"][node] for node in permutation],
        "cell_node_ids": [cell[::-1] for cell in original["cell_node_ids"]]}
    actual = runner._integrate_field("E-vector-mixed", runner.specification(), changed)
    for name in actual:
        assert actual[name] == pytest.approx(expected[name], rel=1e-12)


def test_swapped_directed_values_are_not_magnitude_equivalent():
    original, changed = field(2), field(2)
    changed["values"] = [values[::-1] for values in changed["values"]]
    a = runner._integrate_field("E-vector-mixed", runner.specification(), original)
    b = runner._integrate_field("E-vector-mixed", runner.specification(), changed)
    assert b["l2"] > 3*a["l2"]
    assert all(sum(value*value for value in first) == sum(value*value for value in second)
               for first, second in zip(original["values"], changed["values"]))


def test_raw_observation_preservation_allows_only_additive_diagnostics():
    raw = {"components": [{"index": 0, "value": 1.0}, {"index": 1, "value": 2.0}], "rate": None}
    assessed = deepcopy(raw)
    assessed["components"][0]["diagnostic"] = "recomputed"
    assert runner._original_observations(raw, assessed)
    assessed["components"][1]["value"] = -2.0
    assert not runner._original_observations(raw, assessed)
    assessed = deepcopy(raw)
    assessed["components"][0]["index"] = False
    assert not runner._original_observations(raw, assessed)


def test_old_store_refused_before_any_source_or_native_call(tmp_path, monkeypatch):
    retained = tmp_path / "retained"
    retained.mkdir()
    artifact = retained / "old.json"
    artifact.write_text('{"retain":true}\n')
    before = artifact.read_bytes()
    monkeypatch.setattr(runner, "_source_pin", lambda: pytest.fail("Old store must refuse before source/native setup"))
    with pytest.raises(AssertionError, match="must be new"):
        runner.run(retained)
    assert artifact.read_bytes() == before


@pytest.mark.parametrize("commit,dirty", [("unavailable", False), ("candidate", True)])
def test_clean_source_guard_blocks_native_and_store_creation(tmp_path, monkeypatch, commit, dirty):
    monkeypatch.setattr(runner, "_source_pin", lambda: {"core": {"core_commit": commit, "core_dirty": dirty}, "files": {}})
    monkeypatch.setattr(runner, "Lab", lambda *a, **k: pytest.fail("Uncommitted source must block Core/native"))
    with pytest.raises(AssertionError, match="committed clean"):
        runner.run(tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_source_and_retained_provenance_drift_are_detected(monkeypatch):
    frozen = {"core": {"core_commit": "candidate", "core_dirty": False}, "files": {"worker": "sealed"}}
    monkeypatch.setattr(runner, "_source_pin", lambda: frozen)
    runner._verify_source(frozen, {"provenance": frozen["core"]})
    with pytest.raises(AssertionError, match="provenance"):
        runner._verify_source(frozen, {"provenance": {"core_commit": "other", "core_dirty": False}})
    changed = deepcopy(frozen)
    changed["files"]["worker"] = "changed"
    monkeypatch.setattr(runner, "_source_pin", lambda: changed)
    with pytest.raises(AssertionError, match="source drift"):
        runner._verify_source(frozen)


def test_native_copy_hash_drift_is_detected_without_execution(tmp_path, monkeypatch):
    native = tmp_path / "pde"
    native.mkdir()
    save_json(native / "command.json", {"source_only_fixture": True})
    copied = native / "worker.py"
    copied.write_text("synthetic source-only copy\n")
    digest = runner._sha(copied)
    pin = {"core": {"core_commit": "candidate", "core_dirty": False}, "files": {"worker.py": digest}}
    monkeypatch.setattr(runner, "SOURCE_PATHS", {"worker": ("worker.py", "worker.py")})
    monkeypatch.setattr(runner, "_source_pin", lambda: pin)
    save_json(native / "source_manifest.json", {"files": {"worker": {"repository_path": "worker.py", "copied_path": "worker.py", "sha256": digest}}})
    runner._verify_source(pin, {"provenance": pin["core"]}, tmp_path)
    copied.write_text("tampered source-only copy\n")
    with pytest.raises(AssertionError, match="copied bytes"):
        runner._verify_source(pin, {"provenance": pin["core"]}, tmp_path)
