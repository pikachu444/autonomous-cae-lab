"""Execution controls use tiny local processes, never a native solver."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import time

import pytest

from caelab.adapters.codeaster_execution import process_budgets
from caelab.adapters.codeaster_elasticity import _process


@pytest.fixture
def clean_policy(monkeypatch):
    for name in ("CAELAB_CODEASTER_TIME_LIMIT_SECONDS", "CAELAB_CODEASTER_WALL_TIMEOUT_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_native_default_and_explicit_long_user_budget_remain_separate_from_wall_limit(clean_policy):
    assert process_budgets()["solver_time_seconds"] == 86400
    assert process_budgets()["subprocess_timeout_seconds"] is None
    clean_policy.setenv("CAELAB_CODEASTER_TIME_LIMIT_SECONDS", "172800")
    clean_policy.setenv("CAELAB_CODEASTER_WALL_TIMEOUT_SECONDS", "259200")
    budget = process_budgets()
    assert budget["solver_time_seconds"] == 172800
    assert budget["subprocess_timeout_seconds"] == 259200
    assert budget["solver_time_source"] == budget["wall_time_source"] == "USER_ENVIRONMENT"
    assert budget["qualification"] == "UNKNOWN"


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "", "unlimited", " 60", "2147483648"])
@pytest.mark.parametrize("name", ["CAELAB_CODEASTER_TIME_LIMIT_SECONDS", "CAELAB_CODEASTER_WALL_TIMEOUT_SECONDS"])
def test_invalid_budget_is_refused_without_a_process(clean_policy, name, value):
    clean_policy.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        process_budgets()


def wait_for(path: Path):
    deadline = time.monotonic() + 5
    while not path.exists():
        if time.monotonic() >= deadline:
            pytest.fail(f"Local test process did not create {path.name}")
        time.sleep(.01)


def test_no_wall_budget_keeps_running_and_exposes_owned_pid_and_live_logs(tmp_path):
    source = (
        "from pathlib import Path; import sys,time; "
        "print('local process started',flush=True); Path('entered').touch(); "
        "exec(\"while not Path('release').exists(): time.sleep(.01)\"); "
        "print('local process complete',flush=True)"
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        job = pool.submit(_process, [sys.executable, "-u", "-c", source], tmp_path, "solver", timeout=None)
        try:
            wait_for(tmp_path / "entered")
            state = json.loads((tmp_path / "solver.execution.json").read_text())
            assert state["status"] == "RUNNING" and state["pid"] > 0
            assert state["timeout_seconds"] is None and not job.done()
            assert "local process started" in (tmp_path / "solver.stdout.log").read_text()
        finally:
            (tmp_path / "release").touch()
        assert "local process complete" in job.result(timeout=5)
    final = json.loads((tmp_path / "solver.execution.json").read_text())
    assert final["status"] == "COMPLETED" and final["return_code"] == 0
    assert "finished_utc" in final


def test_user_wall_budget_retains_partial_output_and_distinct_execution_state(tmp_path):
    with pytest.raises(RuntimeError, match="budget exhausted.*UNKNOWN"):
        _process([sys.executable, "-u", "-c", "import time; print('partial output',flush=True); time.sleep(30)"],
                 tmp_path, "solver", timeout=1)
    state = json.loads((tmp_path / "solver.execution.json").read_text())
    assert state["status"] == "BUDGET_EXHAUSTED" and state["reason"] == "WALL_TIME_BUDGET"
    assert state["return_code"] != 0
    assert "partial output" in (tmp_path / "solver.stdout.log").read_text()
    assert not (tmp_path / "analysis_raw.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="Native Code_Aster process groups run in Linux/WSL")
def test_wall_budget_stops_owned_runner_and_child_group(tmp_path):
    source = (
        "import subprocess,sys,time; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
        "print(child.pid,flush=True); time.sleep(30)"
    )
    with pytest.raises(RuntimeError, match="budget exhausted"):
        _process([sys.executable, "-u", "-c", source], tmp_path, "solver", timeout=1)
    child = int((tmp_path / "solver.stdout.log").read_text().strip())
    native_state = Path(f"/proc/{child}/stat")
    # A killed child may await init reaping as a zombie; it cannot keep solving.
    assert not native_state.exists() or native_state.read_text().split()[2] == "Z"


@pytest.mark.parametrize("marker,expected", [("<S>_CPU_LIMIT", "BUDGET_EXHAUSTED"), ("numerical failure", "FAILED_EXECUTION")])
def test_native_error_marker_does_not_become_numerical_acceptance(tmp_path, marker, expected):
    with pytest.raises(RuntimeError, match="failed"):
        _process([sys.executable, "-c", "import sys; print(sys.argv[1],file=sys.stderr); sys.exit(4)", marker],
                 tmp_path, "solver", timeout=None)
    assert json.loads((tmp_path / "solver.execution.json").read_text())["status"] == expected
    assert not (tmp_path / "analysis_raw.json").exists()
