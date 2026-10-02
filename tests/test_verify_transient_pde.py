"""Source-only acceptance-plan/provenance checks; no native solver proof."""

from copy import deepcopy

import pytest

from caelab.adapters.fenicsx_worker import PDEInputError
from plugins.pde_transient.reference import validate_settings
from scripts import verify_transient_pde as runner


def test_frozen_controls_separate_time_space_and_keep_actual_work_counts():
    accepted, rejected, refused = runner.cases()
    assert len(accepted) == 5 and len(rejected) == 3 and len(refused) == 5
    assert set(accepted).isdisjoint(rejected) and set(accepted).isdisjoint(refused)
    for settings in [*accepted.values(), *rejected.values()]:
        assert validate_settings(settings) == settings
    temporal = accepted["E-transient-time"]
    spatial = accepted["E-transient-mesh"]
    assert runner._pairs(temporal) == [(8, 16), (8, 32), (8, 64)]
    assert runner._pairs(spatial) == [(8, 32), (16, 32), (32, 32)]
    assert temporal["validation"] == {"max_l2_error": .04, "min_l2_rate": .8,
                                     "max_h1_seminorm_error": .2, "min_h1_rate": .8,
                                     "max_residual_relative": 1e-10}
    assert spatial["validation"] == {"max_l2_error": .06, "min_l2_rate": 1.8,
                                    "max_h1_seminorm_error": 1., "min_h1_rate": .9,
                                    "max_residual_relative": 1e-10}
    pairs = [pair for settings in [*accepted.values(), *rejected.values()] for pair in runner._pairs(settings)]
    assert len(pairs) == 24
    assert sum(count+1 for _, count in pairs) == 872
    assert sum(count for _, count in pairs) == 848
    assert all(settings["time"]["end"] == 1 for settings in [*accepted.values(), *rejected.values()])


@pytest.mark.parametrize("name", sorted(runner.cases()[2]))
def test_each_refusal_is_actually_invalid_before_native(name):
    with pytest.raises(PDEInputError):
        validate_settings(runner.cases()[2][name])


def test_controls_are_independent_deep_copies_and_finite_wrong_conditions_remain_declared():
    accepted, rejected, refused = runner.cases()
    accepted["E-transient-time"]["time"]["step_counts"].append(128)
    assert rejected["E-transient-flux-reject"]["time"]["step_counts"] == [16, 32, 64]
    assert runner.cases()[0]["E-transient-time"]["time"]["step_counts"] == [16, 32, 64]
    assert rejected["E-transient-reference-reject"]["problem"]["reference"]["solution"] == "0.0"
    assert rejected["E-transient-time-rhs-reject"]["problem"]["weak_form"]["rhs"] == "-(x[0]+2*x[1]+1)"
    assert refused["E-transient-invalid-work"]["time"]["step_counts"] == [128]


def test_existing_store_is_preserved_without_source_or_runtime_calls(tmp_path, monkeypatch):
    store = tmp_path / "old"
    store.mkdir()
    marker = store / "original.txt"
    marker.write_bytes(b"original experiment")
    def forbidden(*args, **kwargs):
        raise AssertionError("Existing stores must refuse before inspecting source/runtime")
    monkeypatch.setattr(runner, "_source_pin", forbidden)
    monkeypatch.setattr(runner, "Lab", forbidden)
    with pytest.raises(ValueError, match="fresh store"):
        runner.run(store)
    assert marker.read_bytes() == b"original experiment"


def test_dirty_source_blocks_before_creating_store_or_constructing_lab(tmp_path, monkeypatch):
    store = tmp_path / "new"
    monkeypatch.setattr(runner, "_source_pin", lambda: {"core": {"core_dirty": True, "core_commit": "candidate"}})
    def forbidden(*args, **kwargs):
        raise AssertionError("Dirty native acceptance must refuse before Lab construction")
    monkeypatch.setattr(runner, "Lab", forbidden)
    with pytest.raises(AssertionError, match="clean committed source"):
        runner.run(store)
    assert not store.exists()


def test_source_drift_before_call_blocks_solver_and_after_call_is_retained_as_failure(tmp_path, monkeypatch):
    pin = {"core": {"core_commit": "original", "core_dirty": False}, "files": {"worker.py": "first"}}
    drifted = deepcopy(pin)
    drifted["files"]["worker.py"] = "changed"
    calls = []
    class FakeLab:
        def run_pde(self, **kwargs):
            calls.append(kwargs)
            return {"provenance": deepcopy(pin["core"])}
    monkeypatch.setattr(runner, "_source_pin", lambda: drifted)
    with pytest.raises(AssertionError, match="source drift"):
        runner._run_fixed(FakeLab(), tmp_path, pin, "S-test", "E-test", {})
    assert calls == []
    observations = iter((pin, drifted))
    monkeypatch.setattr(runner, "_source_pin", lambda: next(observations))
    with pytest.raises(AssertionError, match="source drift"):
        runner._run_fixed(FakeLab(), tmp_path, pin, "S-test", "E-test", {})
    assert len(calls) == 1


def test_execution_failure_is_not_replaced_by_a_pass_when_source_stays_frozen(tmp_path, monkeypatch):
    pin = {"core": {"core_commit": "original", "core_dirty": False}, "files": {}}
    monkeypatch.setattr(runner, "_source_pin", lambda: pin)
    class FailedLab:
        def run_pde(self, **kwargs):
            raise RuntimeError("partial native failure")
    with pytest.raises(RuntimeError, match="partial native failure"):
        runner._run_fixed(FailedLab(), tmp_path, pin, "S-test", "E-test", {})


def test_identity_preserves_node_binding_and_saved_number_types():
    field = {"node_ids": [0, 1], "values": [1., 2.]}
    first = runner._values_identity(field)
    assert first != runner._values_identity({"node_ids": [1, 0], "values": [1., 2.]})
    assert first != runner._values_identity({"node_ids": [0, 1], "values": [1, 2]})


def test_independent_reference_and_source_formulas_cover_real_zero_and_time_load_controls():
    settings = runner.specification("time")
    x, y, time = 1., .25, .5
    assert runner._rhs_value("E-transient-time", settings, x, y, time) == -runner._reference_value("E-transient-time", x, y, time)
    assert runner._rhs_value("E-transient-time-rhs-reject", settings, x, y, time) == -(x+2*y+1)
    assert runner._reference_value("E-transient-reference-reject", x, y, time) == 0.
    assert runner._rhs_value("E-transient-zero-source", runner.specification(), x, y, time) == 0.
    assert runner._reference_value("E-transient-zero-source", x, y, time)-runner._initial_value("E-transient-zero-source", x, y) == 4*time
