"""Acceptance witness integrity and claim semantics; no native solver claims."""

from copy import deepcopy
from types import SimpleNamespace
import json
import os
import sys
import time

import pytest

from scripts.verify_fixture_refinement import (LIMITS, analytical_volume, geometric_reference,
                                                inventory, process_record, refinement_history, runtime_identity,
                                                supervise_process, verify_preserved)


def row(index, width, volume, *, usable=True, feasible=True, displacement=0.006):
    return {"index": index, "values": {"support_width": width}, "usable": usable,
            "numerically_feasible": feasible, "objective": {"value": volume},
            "feedback": {"objective": volume if usable else None},
            "constraints": [{"valid": displacement is not None, "value": displacement}]}


def test_retention_witness_includes_hidden_files_and_refuses_changed_bytes(tmp_path):
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden/raw.dat").write_bytes(b"native bytes")
    saved = inventory(tmp_path)
    assert ".hidden/raw.dat" in saved["files"]
    verify_preserved(tmp_path, saved["files"])
    (tmp_path / ".hidden/raw.dat").write_bytes(b"other bytes!")
    with pytest.raises(AssertionError, match="changed"):
        verify_preserved(tmp_path, saved["files"])


def test_retention_witness_refuses_missing_file(tmp_path):
    (tmp_path / "raw").write_bytes(b"native")
    saved = inventory(tmp_path)
    (tmp_path / "raw").unlink()
    with pytest.raises(AssertionError, match="Missing"):
        verify_preserved(tmp_path, saved["files"])


def test_hidden_symlink_cannot_escape_inventory(tmp_path):
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.write_bytes(b"outside")
    (tmp_path / ".alias").symlink_to(outside)
    with pytest.raises(AssertionError, match="symlink"):
        inventory(tmp_path)


def test_later_best_must_improve_initial_population_to_claim_refinement():
    rows = [row(1, 28, None, usable=False, feasible=False, displacement=None),
            row(2, 31, 300), row(3, 30, 290), row(4, 35, 340), row(5, 38, 380), row(6, 29, 280)]
    report = refinement_history(rows)
    assert report["initial_population_best"]["index"] == 3
    assert report["adaptive_refinement"] == "OBSERVED"
    assert report["later_volume_improvement_mm3"] == 10
    assert report["history"][-1]["width_minus_open_bound_mm"] == 0.5
    assert report["history"][-1]["displacement_slack_mm"] == pytest.approx(0.0005)
    assert report["history"][0]["displacement_slack_mm"] is None


@pytest.mark.parametrize("later", [row(6, 29, 280, usable=False), row(6, 29, 280, feasible=False),
                                  row(6, 30, 290), row(6, 31, 300)])
def test_unusable_infeasible_equal_or_worse_later_member_is_not_refinement(later):
    initial = [row(1, 30, 290), row(2, 31, 300), row(3, 32, 310), row(4, 35, 350), row(5, 38, 380)]
    report = refinement_history([*initial, deepcopy(later)])
    assert report["adaptive_refinement"] == "NOT_OBSERVED"
    assert report["final_incumbent"]["index"] == 1


def test_reference_preserves_the_source_open_bound_and_positive_volume_slope():
    reference = geometric_reference()
    assert reference["open_width_lower_bound_mm"] == 28.5
    assert "equality is CAD rejection" in reference["comparison"]
    assert analytical_volume(28.6) - analytical_volume(28.5) == pytest.approx(104)
    assert LIMITS["campaign_cad_cap"] == 5 * (5 + 1)
    assert LIMITS["total_mesh_solver_runs_cap_with_baseline"] == 2 * (29 + 1)
    assert LIMITS["gmsh_timeout_seconds"] == 180 and LIMITS["calculix_timeout_seconds"] == 300


def test_version_only_returncode_201_is_recorded_without_accepting_a_bad_query(tmp_path, monkeypatch):
    for name in ("gmsh", "ccx"):
        (tmp_path / name).write_bytes(b"test executable identity only")
    monkeypatch.setattr("scripts.verify_fixture_refinement.shutil.which", lambda name: str(tmp_path / name))
    def version(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout="4.12.1\n", stderr="") if command[1] == "-version" else SimpleNamespace(
            returncode=201, stdout="\nThis is Version 2.21\n", stderr="")
    monkeypatch.setattr("scripts.verify_fixture_refinement.subprocess.run", version)
    assert runtime_identity()["ccx"]["version_query_returncode"] == 201
    monkeypatch.setattr("scripts.verify_fixture_refinement.subprocess.run", lambda command, **kw:
        SimpleNamespace(returncode=0, stdout="4.12.1\n", stderr="") if command[1] == "-version" else
        SimpleNamespace(returncode=201, stdout="unrelated output", stderr=""))
    with pytest.raises(AssertionError, match="CalculiX version"):
        runtime_identity()


def test_supervisor_retains_clean_worker_ownership_logs_and_zero_return(tmp_path):
    argv = [sys.executable, "-c", "import time; print('pure supervision test', flush=True); time.sleep(.2)"]
    result = supervise_process(argv, tmp_path / "control", timeout_seconds=3)
    assert result["status"] == "COMPLETED" and result["worker_returncode"] == 0
    assert result["ownership"]["argv"] == argv
    assert result["ownership"]["process_group"] == result["ownership"]["session"] == result["ownership"]["pid"]
    assert result["ownership"]["process_group"] != os.getpgrp()
    assert result["cleanup"]["remaining_owned_members"] == []
    assert (tmp_path / "control/worker.stdout.log").read_text().strip() == "pure supervision test"
    assert (tmp_path / "control/result.json").is_file()


def test_transient_empty_proc_argv_requires_the_same_kernel_identity_then_exact_launch(tmp_path, monkeypatch):
    real_record = process_record
    calls = 0
    def transient(pid):
        nonlocal calls
        observed = real_record(pid)
        calls += 1
        if calls <= 2 and observed:
            return {**observed, "argv": []}
        return observed
    monkeypatch.setattr("scripts.verify_fixture_refinement.process_record", transient)
    argv = [sys.executable, "-c", "import time; time.sleep(.2)"]
    result = supervise_process(argv, tmp_path / "delayed-argv", timeout_seconds=3)
    assert result["status"] == "COMPLETED" and result["ownership"]["argv"] == argv
    assert result["cleanup"]["remaining_owned_members"] == []


def test_external_deadline_kills_native_like_blocked_worker_and_child_descendants(tmp_path):
    # libc.sleep blocks inside native code; no Python signal watchdog is used.
    grandchild = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"
    child = ("import ctypes,json,signal,subprocess,sys; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
             f"p=subprocess.Popen([sys.executable,'-c',{grandchild!r}]); "
             "print(json.dumps({'grandchild_pid':p.pid}),flush=True); ctypes.CDLL(None).sleep(60)")
    worker = ("import ctypes,json,os,signal,subprocess,sys; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
              f"p=subprocess.Popen([sys.executable,'-c',{child!r}]); "
              "print(json.dumps({'worker_pid':os.getpid(),'child_pid':p.pid}),flush=True); ctypes.CDLL(None).sleep(60)")
    started = time.monotonic()
    result = supervise_process([sys.executable, "-c", worker], tmp_path / "blocked", timeout_seconds=.7)
    assert time.monotonic() - started < 5
    assert result["status"] == "WALL_TIMEOUT" and result["worker_returncode"] == -9
    observations = [json.loads(line) for line in (tmp_path / "blocked/worker.stdout.log").read_text().splitlines()]
    pids = {pid for row in observations for pid in row.values()}
    assert len(pids) == 3
    assert pids <= {row["pid"] for row in result["cleanup"]["members_before_termination"]}
    assert result["cleanup"]["remaining_owned_members"] == []
    assert all(process_record(pid) is None for pid in pids)


def test_zero_exit_with_orphaned_descendant_is_failure_and_owned_group_is_cleaned(tmp_path):
    worker = ("import json,subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
              "print(json.dumps({'child_pid':p.pid}),flush=True); time.sleep(.2)")
    result = supervise_process([sys.executable, "-c", worker], tmp_path / "orphaned", timeout_seconds=3)
    assert result["worker_returncode"] == 0 and result["status"] == "FAILED_ORPHANED_DESCENDANTS"
    child = json.loads((tmp_path / "orphaned/worker.stdout.log").read_text())["child_pid"]
    assert result["cleanup"]["remaining_owned_members"] == [] and process_record(child) is None
