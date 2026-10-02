"""Source controls with closed integrals; these fixtures are not native evidence."""

from copy import deepcopy
import math

import pytest

from caelab.storage import save_json
from plugins.pde_coupled.reference import validate_settings
from scripts import verify_coupled_pde as runner


def source_field():
    # Two unit squares, with the left triangulation reflected about x=1.
    # The affine solution parts interpolate exactly; q_h=min(|x-1|,y).
    return {"source_only_fixture": True, "node_ids": list(range(6)),
        "coordinates": [[0., 0.], [0., 1.], [1., 0.], [1., 1.], [2., 0.], [2., 1.]],
        "cell_node_ids": [[2, 0, 1], [2, 1, 3], [2, 4, 5], [2, 5, 3]],
        "values": [[0., 4.], [2., 3.], [1., 2.], [2., -1.], [36/31, 40/31], [98/31, 9/31]]}


def test_frozen_controls_and_fixed_criteria_cover_regions_and_components():
    accepted, rejected, refused = runner.cases()
    assert (len(accepted), len(rejected), len(refused)) == (6, 3, 8)
    assert len(set(accepted) | set(rejected) | set(refused)) == 17
    assert sum(len(case["mesh"]["cell_counts"]) for case in [*accepted.values(), *rejected.values()]) == 27
    for settings in [*accepted.values(), *rejected.values()]:
        assert validate_settings(settings) == settings
        assert settings["mesh"]["cell_counts"] == [8, 16, 32]
        assert settings["validation"] == {"max_l2_error": .04, "max_h1_seminorm_error": .8,
            "min_l2_rate": 1.8, "min_h1_rate": .9, "max_residual_relative": 1e-10}
    base = accepted["E-coupled-mixed"]
    for region in runner.REGIONS:
        assert rejected["E-coupled-reference-reject"]["problem"]["reference"]["solution"][region] == [
            base["problem"]["reference"]["solution"][region][0], "0.0"]
        assert rejected["E-coupled-source-swap-reject"]["problem"]["weak_form"]["rhs"][region] == base["problem"]["weak_form"]["rhs"][region][::-1]
        assert accepted["E-coupled-harmonic-mixed"]["problem"]["weak_form"]["rhs"][region] == ["0.0", "0.0"]
    homogeneous = accepted["E-coupled-homogeneous"]["problem"]["weak_form"]["diffusion"]
    assert homogeneous["left"] == homogeneous["right"] == [[2., .5], [.5, 1.]]
    assert accepted["E-coupled-reaction"]["problem"]["weak_form"]["reaction"] == [[2., .25], [.25, 1.]]
    assert all(row["type"] == "dirichlet" for row in accepted["E-coupled-all-dirichlet"]["problem"]["boundaries"].values())


@pytest.mark.parametrize("case", [
    "E-coupled-invalid-expression", "E-coupled-invalid-components", "E-coupled-invalid-interface-D",
    "E-coupled-invalid-SPD", "E-coupled-invalid-PSD", "E-coupled-invalid-symmetry",
    "E-coupled-invalid-odd-mesh", "E-coupled-invalid-pure-neumann"])
def test_all_preflight_controls_refuse_without_native_work(case):
    with pytest.raises(ValueError):
        validate_settings(runner.cases()[2][case])


def test_direct_piecewise_derivatives_keep_interface_value_flux_and_two_source_traces():
    settings = runner.specification()
    left = runner._math("E-coupled-mixed", settings, "left", 1., .5)
    right = runner._math("E-coupled-mixed", settings, "right", 1., .5)
    assert left["solution"] == right["solution"] == [1.5, .5]
    assert [row[0] for row in left["gradient"]] == [1., -2.]
    assert [row[0] for row in right["gradient"]] == pytest.approx([5/31, -22/31])
    assert [row[0] for row in left["flux"]] == pytest.approx([1., -1.5])
    assert [row[0] for row in right["flux"]] == pytest.approx([1., -1.5])
    assert left["rhs"] == [-1.5, -1.25]
    assert right["rhs"] == [-1.5, -1.75]
    settings["problem"]["weak_form"]["reaction"] = [[2., .25], [.25, 1.]]
    reacted = runner._math("E-coupled-reaction", settings, "right", 1., .5)
    assert reacted["rhs"] == [1.625, -.875]


@pytest.mark.parametrize("side,region,integral", [
    ("xmax", "right", [3., 5/6]),
    ("ymax", "left", [5/2, -5/6]),
    ("ymax", "right", [15/2, -25/6])])
def test_directed_segment_flux_has_independent_closed_integral(side, region, integral):
    settings = runner.specification()
    observed = [0., 0.]
    for coordinate, weight in runner._QUADRATURE:
        point = (2., coordinate) if side == "xmax" else (coordinate + (region == "right"), 1.)
        for component, value in enumerate(runner._side_value("E-coupled-mixed", settings, side, region, *point)):
            observed[component] += weight*value
    assert observed == pytest.approx(integral, rel=1e-12, abs=1e-12)
    flipped = runner._side_value("E-coupled-traction-reject", settings, side, region, *point)
    original = runner._side_value("E-coupled-mixed", settings, side, region, *point)
    assert flipped == pytest.approx([original[0], -original[1]])


def test_harmonic_controls_and_outward_signs():
    settings = runner.cases()[0]["E-coupled-harmonic-mixed"]
    for region in runner.REGIONS:
        data = runner._math("E-coupled-harmonic-mixed", settings, region, 1., .5)
        assert data["rhs"] == [0., 0.]
        assert data["solution"] == [1.25, 0.]
        assert [row[0] for row in data["flux"]] == pytest.approx([1., -1.5])
    settings["problem"]["boundaries"]["xmin"]["type"] = "neumann"
    assert runner._side_value("E-coupled-harmonic-mixed", settings, "xmin", "left", 0., .5) == pytest.approx([5., 6.5])
    settings["problem"]["boundaries"]["ymin"]["type"] = "neumann"
    assert runner._side_value("E-coupled-harmonic-mixed", settings, "ymin", "left", .25, 0.) == pytest.approx([-.5, 2.5])


def test_duffy_matches_closed_two_region_component_and_full_gradient_errors():
    # Direct square integrals: ||min(s,y)-s²y²||²=67/1050,
    # ||grad(min(s,y)-s²y²)||²=11/15. Two regions, beta=(1,2).
    result = runner._integrate_field("E-coupled-mixed", runner.specification(), source_field())
    assert result["component_l2"] == pytest.approx([math.sqrt(67/525), math.sqrt(268/525)], rel=1e-12)
    assert result["component_h1"] == pytest.approx([math.sqrt(22/15), math.sqrt(88/15)], rel=1e-12)
    assert result["l2"] == pytest.approx(math.sqrt(67/105), rel=1e-12)
    assert result["h1"] == pytest.approx(math.sqrt(22/3), rel=1e-12)


def test_duffy_uses_original_global_ids_and_triangle_orientation():
    original = source_field()
    expected = runner._integrate_field("E-coupled-mixed", runner.specification(), original)
    permutation, ids = [4, 1, 5, 0, 3, 2], [101, 83, 271, 16, 99, 7]
    changed = {"node_ids": [ids[node] for node in permutation],
        "coordinates": [original["coordinates"][node] for node in permutation],
        "values": [original["values"][node] for node in permutation],
        "cell_node_ids": [[ids[node] for node in cell[::-1]] for cell in original["cell_node_ids"]]}
    actual = runner._integrate_field("E-coupled-mixed", runner.specification(), changed)
    for name in actual:
        assert actual[name] == pytest.approx(expected[name], rel=1e-12)


@pytest.mark.parametrize("coordinate", [math.nextafter(1., 0.), math.nextafter(1., math.inf)])
def test_native_interface_ulp_representation_preserves_original_field_and_closed_integrals(coordinate):
    field = source_field()
    for point in field["coordinates"]:
        if point[0] == 1.:
            point[0] = coordinate
    original = deepcopy(field)
    result = runner._integrate_field("E-coupled-mixed", runner.specification(), field)
    assert result["component_l2"] == pytest.approx([math.sqrt(67/525), math.sqrt(268/525)], rel=1e-12)
    assert result["component_h1"] == pytest.approx([math.sqrt(22/15), math.sqrt(88/15)], rel=1e-12)
    assert field == original


def test_crossing_cell_is_refused_and_component_errors_cannot_be_replaced_by_magnitude():
    original, swapped = source_field(), source_field()
    swapped["values"] = [row[::-1] for row in swapped["values"]]
    a = runner._integrate_field("E-coupled-mixed", runner.specification(), original)
    b = runner._integrate_field("E-coupled-mixed", runner.specification(), swapped)
    assert b["l2"] > a["l2"]
    assert all(sum(v*v for v in first) == sum(v*v for v in second)
               for first, second in zip(original["values"], swapped["values"]))
    wrong_reference = runner._integrate_field("E-coupled-reference-reject", runner.specification(), original)
    assert wrong_reference["component_l2"][0] == a["component_l2"][0]
    assert wrong_reference["component_l2"][1] != a["component_l2"][1]
    original["cell_node_ids"][0] = [0, 4, 3]
    with pytest.raises(AssertionError, match="crosses coupled interface"):
        runner._integrate_field("E-coupled-mixed", runner.specification(), original)


def test_source_closure_includes_all_nine_native_dependencies_and_independent_quadrature():
    assert len(runner.SOURCE_PATHS) == 9
    assert len(set(runner.SOURCE_FILES)) == 11
    assert {row[0] for row in runner.SOURCE_PATHS.values()} <= set(runner.SOURCE_FILES)
    assert "scripts/verify_vector_pde.py" in runner.SOURCE_FILES
    assert "caelab/adapters/fenicsx_vector_worker.py" in runner.SOURCE_FILES


def test_old_store_refuses_before_source_or_native_creation(tmp_path, monkeypatch):
    retained = tmp_path / "retained"
    retained.mkdir()
    artifact = retained / "old.json"
    artifact.write_bytes(b'{"retain":true}\n')
    before = artifact.read_bytes()
    monkeypatch.setattr(runner, "_source_pin", lambda: pytest.fail("Old store must block source/native setup"))
    with pytest.raises(AssertionError, match="must be new"):
        runner.run(retained)
    assert artifact.read_bytes() == before


@pytest.mark.parametrize("commit,dirty", [("unavailable", False), ("candidate", True)])
def test_clean_source_guard_blocks_core_native_and_store_creation(tmp_path, monkeypatch, commit, dirty):
    monkeypatch.setattr(runner, "_source_pin", lambda: {"core": {"core_commit": commit, "core_dirty": dirty}, "files": {}})
    monkeypatch.setattr(runner, "Lab", lambda *a, **k: pytest.fail("Uncommitted source must block Core/native"))
    with pytest.raises(AssertionError, match="committed clean"):
        runner.run(tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_source_and_provenance_drift_detected_without_execution(monkeypatch):
    pin = {"core": {"core_commit": "candidate", "core_dirty": False}, "files": {"worker": "sealed"}}
    monkeypatch.setattr(runner, "_source_pin", lambda: pin)
    runner._verify_source(pin, {"provenance": pin["core"]})
    with pytest.raises(AssertionError, match="provenance"):
        runner._verify_source(pin, {"provenance": {"core_commit": "other", "core_dirty": False}})
    changed = deepcopy(pin)
    changed["files"]["worker"] = "changed"
    monkeypatch.setattr(runner, "_source_pin", lambda: changed)
    with pytest.raises(AssertionError, match="source drift"):
        runner._verify_source(pin)


def test_complete_native_manifest_missing_copy_and_tamper_gates_without_execution(tmp_path, monkeypatch):
    native = tmp_path / "pde"
    native.mkdir()
    save_json(native / "command.json", {"source_only_fixture": True})
    pin = {"core": {"core_commit": "candidate", "core_dirty": False}, "files": {}}
    manifest = {"files": {}}
    for key, (repository_path, copied_path) in runner.SOURCE_PATHS.items():
        path = native / copied_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"source-only placeholder {key}\n", encoding="utf-8")
        digest = runner._sha(path)
        pin["files"][repository_path] = digest
        manifest["files"][key] = {"repository_path": repository_path, "copied_path": copied_path, "sha256": digest}
    monkeypatch.setattr(runner, "_source_pin", lambda: pin)
    save_json(native / "source_manifest.json", manifest)
    runner._verify_source(pin, {"provenance": pin["core"]}, tmp_path)
    missing = deepcopy(manifest)
    missing["files"].pop(next(iter(missing["files"])))
    save_json(native / "source_manifest.json", missing)
    with pytest.raises(AssertionError, match="Incomplete nine"):
        runner._verify_source(pin, {"provenance": pin["core"]}, tmp_path)
    save_json(native / "source_manifest.json", manifest)
    (native / "worker.py").write_text("tampered source-only placeholder\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="copy bytes drift"):
        runner._verify_source(pin, {"provenance": pin["core"]}, tmp_path)
