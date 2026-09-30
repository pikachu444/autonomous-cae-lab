"""Predeclared five-generation fixture screen using the existing Core/engine.

Run only in the configured Linux/WSL Python environment on a clean checkout.
No numeric candidates, native solver syntax or new optimizer live here.
"""

from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "plugins/fixture_design/upstream"
MATERIAL = UPSTREAM / "examples/printed_material_ASSUMED.json"
MODEL_SOURCE = UPSTREAM / "models/roller_support.py"
STUDY = "S-fixture-refinement"
CAMPAIGN = "C-fixture-refinement"
LIMITS = {
    "seed": 13, "population_size": 5, "max_generations": 5,
    "width_bounds_mm": [28.0, 42.0], "initial_width_mm": 28.0,
    "baseline_width_mm": 38.0, "displacement_limit_mm": 0.0065,
    "mesh_sizes_mm": [2.0, 1.5], "mesh_trend_limit": 0.05,
    "reaction_balance_limit": 0.01, "force_per_support_N": 100.0,
    "campaign_cad_cap": 30, "total_cad_cap_with_baseline": 31,
    "campaign_solver_children_cap": 29, "total_solver_children_cap_with_baseline": 30,
    "total_mesh_solver_runs_cap_with_baseline": 60,
    "gmsh_timeout_seconds": 180, "calculix_timeout_seconds": 300,
    "wall_watchdog_seconds": 5400, "process_address_space_bytes": 8 * 1024**3,
    "store_bytes_at_boundary_cap": 8 * 1024**3, "cpu_affinity_count": 2,
    "interrupt_before_cad_evaluation": 8, "cad_volume_relative_error_limit": 1e-9,
}
REQUIRED = {"cad": [], "analysis": ["displacement_mesh_trend",
            "mesh_0_reaction_balance", "mesh_1_reaction_balance"]}
UNKNOWN = {"static_strength", "physical_load_test", "fatigue_durability"}


class AcceptanceBudgetExceeded(RuntimeError):
    """Stop infrastructure work; never treat resource exhaustion as infeasibility."""


class PlannedInterruption(KeyboardInterrupt):
    pass


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory(folder):
    """Include hidden files; reject links instead of escaping the evidence root."""
    root = Path(folder)
    require(root.is_dir() and not root.is_symlink(), "Inventory root must be a real directory")
    files, directories = {}, []
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), f"Unexpected evidence symlink: {path}")
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            directories.append(relative)
        elif path.is_file():
            files[relative] = {"sha256": sha(path), "size_bytes": path.stat().st_size}
        else:
            raise AssertionError(f"Unsupported evidence entry: {path}")
    return {"files": files, "directories": directories,
            "file_count": len(files), "size_bytes": sum(row["size_bytes"] for row in files.values())}


def verify_preserved(root, saved):
    for relative, record in saved.items():
        path = Path(root) / relative
        require(path.is_file() and not path.is_symlink(), f"Missing preserved file: {relative}")
        require(path.stat().st_size == record["size_bytes"] and sha(path) == record["sha256"],
                f"Preserved file changed: {relative}")


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, timeout=30).decode().strip()


def tracked_files(root):
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=root, timeout=30).decode().split("\0")
    return [name for name in sorted(set(names)) if name and (Path(root) / name).is_file()]


def file_records():
    records = {}
    for prefix, folder in (("repository", ROOT), ("upstream", UPSTREAM)):
        for name in tracked_files(folder):
            path = folder / name
            require(not path.is_symlink(), f"Unexpected source symlink: {path}")
            records[f"{prefix}/{name}"] = {"sha256": sha(path), "size_bytes": path.stat().st_size}
    return records


def runtime_identity():
    result = {}
    for name, option in (("gmsh", "-version"), ("ccx", "-v")):
        found = shutil.which(name)
        require(found is not None, f"Missing configured executable: {name}")
        path = Path(found).resolve(strict=True)
        version = subprocess.run([str(path), option], capture_output=True, text=True, timeout=10)
        if name == "gmsh":
            require(version.returncode == 0 and re.fullmatch(r"\d+\.\d+(?:\.\d+)?", (version.stdout + version.stderr).strip()),
                    "Cannot read Gmsh version")
        else:
            # The installed CalculiX 2.21 version-only query returns 201. Keep
            # that observation; this is not a native solve success convention.
            require(version.returncode in (0, 201) and not version.stderr.strip() and
                    re.fullmatch(r"This is Version \d+\.\d+(?:\.\d+)?", version.stdout.strip()),
                    "Cannot read CalculiX version")
        result[name] = {"command_path": found, "resolved_path": str(path), "sha256": sha(path),
                        "size_bytes": path.stat().st_size,
                        "version_query_returncode": version.returncode,
                        "version_stdout": version.stdout.strip(), "version_stderr": version.stderr.strip()}
    return result


def geometric_reference():
    values = {}
    for node in ast.parse(MODEL_SOURCE.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and type(node.value.value) in (int, float):
                    values[target.id] = node.value.value
    wanted = {"support_depth_mm": 40.0, "support_height_mm": 26.0,
              "roller_diameter_mm": 8.3, "bolt_pitch_x_mm": 20.0,
              "hole_diameter_mm": 4.5, "edge_land_mm": 2.0}
    require(all(values.get(k) == v for k, v in wanted.items()), "Pinned analytical CAD assumptions changed")
    lower = values["bolt_pitch_x_mm"] + values["hole_diameter_mm"] + 2 * values["edge_land_mm"]
    require(lower == 28.5, "The source-derived open geometric lower bound changed")
    return {"source_sha256": sha(MODEL_SOURCE), "open_width_lower_bound_mm": lower,
            "comparison": "width > lower bound (equality is CAD rejection)", "defaults": wanted,
            "volume_expression": "40*26*width - pi*(8.3/2)^2*40/2 - 4*pi*(4.5/2)^2*26",
            "volume_slope_mm2": 40 * 26,
            "scope": "Geometric objective bound only; no feasibility/optimum certificate at the open boundary"}


def analytical_volume(width):
    return 40 * 26 * width - math.pi * 4.15**2 * 40 / 2 - 4 * math.pi * 2.25**2 * 26


def refinement_history(rows, population_size=5, geometric_lower=28.5, displacement_limit=0.0065):
    history, incumbent = [], None
    for row in rows:
        if row["usable"] and row["numerically_feasible"]:
            if incumbent is None or (row["feedback"]["objective"], row["index"]) < (
                    incumbent["feedback"]["objective"], incumbent["index"]):
                incumbent = row
        response = row["constraints"][0]
        history.append({"index": row["index"], "width_mm": row["values"]["support_width"],
                        "width_minus_open_bound_mm": row["values"]["support_width"] - geometric_lower,
                        "displacement_slack_mm": displacement_limit - response["value"] if response["valid"] else None,
                        "usable": row["usable"], "numerically_feasible": row["numerically_feasible"],
                        "incumbent_index": incumbent["index"] if incumbent else None,
                        "incumbent_volume_mm3": incumbent["objective"]["value"] if incumbent else None})
    initial = [row for row in rows if row["index"] <= population_size and row["usable"] and row["numerically_feasible"]]
    initial_best = min(initial, key=lambda row: (row["feedback"]["objective"], row["index"])) if initial else None
    improved = bool(initial_best and incumbent and incumbent["index"] > population_size and
                    incumbent["objective"]["value"] < initial_best["objective"]["value"])
    return {"history": history, "initial_population_best": deepcopy(initial_best),
            "final_incumbent": deepcopy(incumbent), "adaptive_refinement": "OBSERVED" if improved else "NOT_OBSERVED",
            "later_volume_improvement_mm3": (initial_best["objective"]["value"] - incumbent["objective"]["value"]
                                             if initial_best and incumbent else None)}


def apply_process_limits():
    import resource
    require(os.name == "posix" and hasattr(os, "sched_setaffinity"), "Run in the existing Linux/WSL runtime")
    available = sorted(os.sched_getaffinity(0))
    require(len(available) >= LIMITS["cpu_affinity_count"], "Two available CPUs are required")
    affinity = available[:LIMITS["cpu_affinity_count"]]
    os.sched_setaffinity(0, affinity)
    cap = LIMITS["process_address_space_bytes"]
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    effective = min(cap, hard) if hard != resource.RLIM_INFINITY else cap
    resource.setrlimit(resource.RLIMIT_AS, (effective, effective))
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[name] = "2"
    return {"cpu_affinity": sorted(os.sched_getaffinity(0)),
            "address_space_soft_hard_bytes": list(resource.getrlimit(resource.RLIMIT_AS)),
            "thread_limits": {name: os.environ[name] for name in
                              ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")},
            "scope": "Inherited process address-space/CPU bounds; not a total-machine RAM quota"}


def process_record(pid):
    """Linux identity is PID + kernel start tick + isolated session/group."""
    folder = Path("/proc") / str(pid)
    try:
        stat = (folder / "stat").read_text()
        fields = stat[stat.rfind(")") + 2:].split()
        argv = (folder / "cmdline").read_bytes().split(b"\0")
        return {"pid": pid, "state": fields[0], "parent_pid": int(fields[1]),
                "process_group": int(fields[2]), "session": int(fields[3]),
                "start_ticks": int(fields[19]),
                "argv": [part.decode(errors="replace") for part in argv if part]}
    except (FileNotFoundError, ProcessLookupError):
        return None


def owned_group_members(owner):
    members = []
    for folder in Path("/proc").iterdir():
        if not folder.name.isdigit():
            continue
        row = process_record(int(folder.name))
        if row is None or row["process_group"] != owner["process_group"]:
            continue
        require(row["session"] == owner["session"] and row["start_ticks"] >= owner["start_ticks"],
                "Process-group ownership could not be confirmed; do not kill an unowned process")
        if row["pid"] == owner["pid"]:
            require(row["start_ticks"] == owner["start_ticks"], "Worker PID was reused")
        members.append(row)
    return sorted(members, key=lambda row: row["pid"])


def control_json(path, data):
    path = Path(path)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def subreaper(value=None):
    """Task-process-only Linux adoption permits reaping killed descendants."""
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    existing = ctypes.c_int()
    require(libc.prctl(37, ctypes.byref(existing), 0, 0, 0) == 0, "Cannot inspect task subreaper state")
    if value is not None:
        require(libc.prctl(36, int(value), 0, 0, 0) == 0, "Cannot set task subreaper state")
    return existing.value


def reap_owned_group(group):
    while True:
        try:
            pid, status = os.waitpid(-group, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def stop_owned_group(process, owner):
    members = owned_group_members(owner)
    if process.poll() is None:
        leader = process_record(process.pid)
        require(leader is not None and leader["start_ticks"] == owner["start_ticks"] and
                leader["session"] == leader["process_group"] == process.pid,
                "Exact live worker ownership is unavailable; refuse process termination")
    if members:
        # A native CAD call cannot defer SIGKILL. Only this verified isolated
        # group receives the signal; no global process-name matching is used.
        try:
            os.killpg(owner["process_group"], signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=5)
    cleanup_deadline = time.monotonic() + 5
    while True:
        reap_owned_group(owner["process_group"])
        remaining = owned_group_members(owner)
        if not remaining or time.monotonic() >= cleanup_deadline:
            return {"members_before_termination": members, "remaining_owned_members": remaining,
                    "signal": "SIGKILL" if members else "NOT_NEEDED"}
        time.sleep(0.02)


def supervise_process(argv, control, *, timeout_seconds, start_monotonic=None):
    """Fixed production worker; explicit lower-level argv/budget only for tests.

    Production supplies no command or deadline option through the public CLI.
    A POSIX session contains the existing in-process CAD and its ordinary native
    subprocesses. All retained logs remain outside the worker store until exit.
    """
    require(os.name == "posix" and Path("/proc").is_dir(), "POSIX/Linux supervision is required")
    started = time.monotonic() if start_monotonic is None else start_monotonic
    deadline = started + timeout_seconds
    control = Path(control)
    control.mkdir(parents=True, exist_ok=False)
    control_json(control / "request.json", {"argv": argv, "timeout_seconds": timeout_seconds,
                                           "supervisor_pid": os.getpid(), "supervisor_process_group": os.getpgrp(),
                                           "started_monotonic": started, "deadline_monotonic": deadline,
                                           "deadline_clock": "time.monotonic", "script_sha256": sha(Path(__file__))})
    previous_subreaper = subreaper(1)
    process, owner, cleanup, exception = None, None, None, None
    status = "FAILED_SUPERVISION"
    try:
        with (control / "worker.stdout.log").open("xb") as stdout, (control / "worker.stderr.log").open("xb") as stderr:
            process = subprocess.Popen(argv, cwd=ROOT, stdout=stdout, stderr=stderr,
                                       start_new_session=True, shell=False)
            owner = process_record(process.pid)
            require(owner is not None and owner["parent_pid"] == os.getpid() and
                    owner["process_group"] == owner["session"] == process.pid and
                    owner["process_group"] != os.getpgrp(), "Dedicated worker ownership was not established")
            # /proc/cmdline can briefly be empty while exec loads the process
            # (observed state D). Freeze its kernel identity first; only that
            # identity may later supply the exact expected argv.
            identity_deadline = min(deadline, time.monotonic() + 5)
            while owner["argv"] != argv:
                require(not owner["argv"], "Dedicated worker argv differs from its fixed launch")
                require(time.monotonic() < identity_deadline and process.poll() is None,
                        "Exact worker argv was not available within the bounded startup window")
                time.sleep(0.002)
                observed = process_record(process.pid)
                require(observed is not None and all(observed[key] == owner[key] for key in
                        ("pid", "parent_pid", "process_group", "session", "start_ticks")), "Worker identity changed during argv startup")
                owner = observed
            control_json(control / "ownership.json", owner)
            try:
                remaining_seconds = deadline - time.monotonic()
                if remaining_seconds <= 0:
                    raise subprocess.TimeoutExpired(argv, timeout_seconds)
                process.wait(timeout=remaining_seconds)
                descendants = owned_group_members(owner)
                if descendants:
                    cleanup = stop_owned_group(process, owner)
                    status = "FAILED_ORPHANED_DESCENDANTS"
                else:
                    cleanup = {"members_before_termination": [], "remaining_owned_members": [], "signal": "NOT_NEEDED"}
                    status = "COMPLETED" if process.returncode == 0 else "FAILED_WORKER"
            except subprocess.TimeoutExpired:
                cleanup = stop_owned_group(process, owner)
                status = "WALL_TIMEOUT"
            require(not cleanup["remaining_owned_members"], "Owned descendants remain after bounded cleanup")
    except BaseException as error:
        exception = {"type": type(error).__name__, "reason": str(error)}
        status = "FAILED_SUPERVISION"
        if process is not None and owner is not None:
            try:
                cleanup = stop_owned_group(process, owner)
            except BaseException as cleanup_error:
                cleanup = {"status": "UNCONFIRMED", "exception_type": type(cleanup_error).__name__,
                           "reason": str(cleanup_error)}
        elif process is not None:
            cleanup = {"status": "UNCONFIRMED", "reason": "Exact kernel worker identity was unavailable; no unverified group kill",
                       "worker_pid": process.pid}
    finally:
        subreaper(previous_subreaper)
    result = {"status": status, "elapsed_seconds": time.monotonic() - started,
              "started_monotonic": started, "deadline_monotonic": deadline,
              "timeout_seconds": timeout_seconds, "worker_returncode": process.returncode if process else None,
              "ownership": owner, "cleanup": cleanup, "exception": exception,
              "stdout_sha256": sha(control / "worker.stdout.log") if (control / "worker.stdout.log").is_file() else None,
              "stderr_sha256": sha(control / "worker.stderr.log") if (control / "worker.stderr.log").is_file() else None,
              "deadline_scope": "External worker/session deadline; at most ten seconds of bounded exit/reaping afterward",
              "decision": "NOT_RELEASED"}
    control_json(control / "result.json", result)
    return result


def supervise(store):
    """Normal acceptance entry point with the fixed whole-process watchdog."""
    started = time.monotonic()
    store = Path(store).resolve()
    require(not store.exists(), "Use a new store; historical evidence cannot be overwritten")
    apply_process_limits()
    control = store.parent / (store.name + "-supervisor")
    argv = [sys.executable, "-m", "scripts.verify_fixture_refinement", "--_worker", "--store", str(store)]
    supervision = supervise_process(argv, control, timeout_seconds=LIMITS["wall_watchdog_seconds"], start_monotonic=started)
    store.mkdir(parents=True, exist_ok=True)
    retained = store / "acceptance/supervisor"
    retained.mkdir(parents=True, exist_ok=False)
    for original in sorted(control.iterdir()):
        require(original.is_file() and not original.is_symlink(), "Unexpected supervisor control entry")
        with (retained / original.name).open("xb") as destination, original.open("rb") as source:
            shutil.copyfileobj(source, destination)
        require(sha(retained / original.name) == sha(original), "Supervisor log copy mismatch")
    native_report = store / "fixture_refinement_acceptance.json"
    native_passed = native_report.is_file() and json.loads(native_report.read_text())["status"] == "PASS"
    if supervision["status"] != "COMPLETED" or not native_passed:
        failure = {"status": "FAILED_SUPERVISED_ACCEPTANCE", "supervision_status": supervision["status"],
                   "worker_returncode": supervision["worker_returncode"], "supervision_result_sha256": sha(retained / "result.json"),
                   "decision": "NOT_RELEASED", "policy": "Preserve partial records; timeout/failure is not infeasibility/convergence"}
        control_json(store / "fixture_refinement_supervisor_failure.json", failure)
        print(json.dumps(failure), flush=True)
        return failure
    final = inventory(store)
    require(final["size_bytes"] <= LIMITS["store_bytes_at_boundary_cap"], "Final supervised store exceeds boundary byte budget")
    elapsed = time.monotonic() - started
    require(elapsed < LIMITS["wall_watchdog_seconds"], "Supervision/retention finalization exceeded the whole acceptance wall budget")
    control_json(retained / "final_store_manifest.json", final)
    report = {"status": "PASS", "native_acceptance_sha256": sha(native_report),
              "whole_acceptance_elapsed_seconds": elapsed,
              "supervision_result_sha256": sha(retained / "result.json"),
              "final_store_manifest_sha256": sha(retained / "final_store_manifest.json"),
              "supervision": supervision, "decision": "NOT_RELEASED",
              "retained_before_final_supervisor_manifest_and_report": {"file_count": final["file_count"], "size_bytes": final["size_bytes"]}}
    control_json(store / "fixture_refinement_supervision_acceptance.json", report)
    print(json.dumps(report), flush=True)
    return report


class Guard:
    def __init__(self, store, frozen, save_json):
        self.store, self.frozen, self.save_json = store, frozen, save_json
        self.started = time.monotonic()
        self.cad_ids, self.solver_ids, self.events = [], [], []

    def check_identity(self):
        from caelab.storage import source_identity
        from caelab.adapters.fixture_cadquery import FixtureCadQueryAdapter
        require(source_identity(ROOT) == self.frozen["core"], "Clean Core/source identity drift")
        require(git(UPSTREAM, "status", "--porcelain", "--untracked-files=normal") == "", "Upstream changed")
        require(FixtureCadQueryAdapter.source_fingerprint() == self.frozen["plugin"], "Pinned plugin drift")
        require(file_records() == self.frozen["source_files"], "Working source/script/material bytes drift")
        require(runtime_identity() == self.frozen["native_runtime"], "Gmsh/CalculiX executable identity drift")

    def boundary(self, stage, identifier):
        elapsed = time.monotonic() - self.started
        if elapsed >= LIMITS["wall_watchdog_seconds"]:
            raise AcceptanceBudgetExceeded("Whole acceptance wall-clock budget exhausted")
        self.check_identity()
        size = 0
        for path in self.store.rglob("*"):
            require(not path.is_symlink(), "Evidence store contains an unexpected symlink")
            if path.is_file():
                size += path.stat().st_size
        if size > LIMITS["store_bytes_at_boundary_cap"]:
            raise AcceptanceBudgetExceeded("Evidence store exceeded the boundary-checked byte budget")
        event = {"sequence": len(self.events) + 1, "stage": stage, "experiment_id": identifier,
                 "elapsed_seconds": elapsed, "store_size_bytes": size,
                 "cad_calls_started": len(self.cad_ids), "solver_children_started": len(self.solver_ids)}
        self.events.append(event)
        self.save_json(self.store / "acceptance/boundaries" / f"{event['sequence']:04d}.json", event)
        print(json.dumps({"progress": event}), flush=True)

    def bind(self, lab, *, pause=False):
        original_cad, original_solve = lab.run_experiment, lab.run_analysis

        def cad(*args, **kwargs):
            identifier = kwargs["experiment_id"]
            if pause and identifier == f"E-{CAMPAIGN}-0008":
                self.boundary("PLANNED_INTERRUPTION_BEFORE_EIGHTH_CAD", identifier)
                raise PlannedInterruption("Interrupt before the eighth actual CAD experiment")
            self.boundary("BEFORE_CAD", identifier)
            if len(self.cad_ids) >= LIMITS["total_cad_cap_with_baseline"]:
                raise AcceptanceBudgetExceeded("Unique CAD experiment budget exhausted")
            require(identifier not in self.cad_ids, "An actual CAD experiment was rerun")
            self.cad_ids.append(identifier)
            result = original_cad(*args, **kwargs)
            self.boundary("AFTER_CAD", identifier)
            return result

        def solve(*args, **kwargs):
            identifier = kwargs["experiment_id"]
            self.boundary("BEFORE_SOLVER_CHILD", identifier)
            if len(self.solver_ids) >= LIMITS["total_solver_children_cap_with_baseline"]:
                raise AcceptanceBudgetExceeded("Solver-child budget exhausted")
            require(identifier not in self.solver_ids, "An actual solver child was rerun")
            self.solver_ids.append(identifier)
            result = original_solve(*args, **kwargs)
            self.boundary("AFTER_SOLVER_CHILD", identifier)
            return result

        lab.run_experiment, lab.run_analysis = cad, solve


def retained_prefix(store, partial):
    campaign = store / "optimizations" / CAMPAIGN
    saved = {}
    trees = {}
    for folder in sorted((store / "experiments").iterdir()):
        if folder.is_dir():
            tree = inventory(folder)
            trees[folder.relative_to(store).as_posix()] = tree
            saved.update({f"{folder.relative_to(store).as_posix()}/{name}": row for name, row in tree["files"].items()})
    for path in sorted((store / "ledger").glob("*.json")):
        if path.name != f"optimization-{CAMPAIGN}.json":
            saved[path.relative_to(store).as_posix()] = {"sha256": sha(path), "size_bytes": path.stat().st_size}
    for name in ("plan.json", "registry_snapshot.json"):
        path = campaign / name
        saved[path.relative_to(store).as_posix()] = {"sha256": sha(path), "size_bytes": path.stat().st_size}
    for name in ("candidates", "journal", "checkpoints"):
        for path in sorted((campaign / name).glob("*.json")):
            saved[path.relative_to(store).as_posix()] = {"sha256": sha(path), "size_bytes": path.stat().st_size}
    return {"completed_evaluations": partial["completed_evaluations"], "files": saved,
            "experiment_trees": trees, "partial_evaluations": deepcopy(partial["evaluations"]),
            "state_sha256": sha(campaign / "state.json"),
            "optimization_ledger_sha256": sha(store / "ledger" / f"optimization-{CAMPAIGN}.json"),
            "mutable_after_resume": ["optimizations/C-fixture-refinement/state.json",
                                     "ledger/optimization-C-fixture-refinement.json"],
            "pending_candidate_eight_sha256": sha(campaign / "candidates/0008.json")}


def check_solve(lab, identifier, parent, frozen):
    from caelab.storage import load_json
    result = lab.inspect_experiment(identifier)
    raw = load_json(lab.store / "experiments" / identifier / "simulation/result.json")
    require(result["provenance"]["core_commit"] == frozen["core"]["core_commit"] and
            result["provenance"]["core_dirty"] is False and
            result["provenance"]["core_source_sha256"] == frozen["core"]["core_source_sha256"] and
            result["provenance"]["source_commit"] == frozen["plugin"]["commit"], "Solver clean source closure mismatch")
    require(result["solver_status"] == "COMPLETED" and result["converged"] is True,
            "A failed solver cannot be accepted as an infeasible numerical candidate")
    require(result["decision"] == "NOT_RELEASED" and result["metrics"]["peak_stress"]["valid"] is False,
            "Diagnostic stress or solver completion was promoted to engineering release")
    require(result["parent_experiment_id"] == parent["experiment_id"] and result["cad_revision"] == parent["cad_revision"],
            "Child no longer refers to its actual CAD parent")
    parent_step = lab.store / "experiments" / parent["experiment_id"] / "cad/assembly.step"
    child_step = lab.store / "experiments" / identifier / "simulation/input.step"
    step_hash = sha(parent_step)
    require(sha(child_step) == step_hash and raw["provenance"]["parent_step_sha256"] == step_hash,
            "Solver did not consume the exact parent STEP")
    require(raw["provenance"]["material"] == frozen["material"] and raw["provenance"]["force_per_support_N"] == 100.0,
            "Declared material/load changed")
    require([row["mesh_size_max_mm"] for row in raw["mesh_studies"]] == LIMITS["mesh_sizes_mm"], "Mesh policy changed")
    checks = {row["code"]: row for row in raw["checks"]}
    require(checks["displacement_mesh_trend"]["limit"] == 0.05, "Mesh trend limit changed")
    for i in range(2):
        require(checks[f"mesh_{i}_reaction_balance"]["limit"] == 0.01, "Reaction limit changed")
    common = {row["type"]: row for row in result["validations"]}
    require(UNKNOWN <= {row["type"] for row in result["validations"] if row["status"] == "UNKNOWN"}, "Qualification UNKNOWN lost")
    return {"result": result, "raw": raw, "parent_step_sha256": step_hash,
            "required_checks": {name: common[name]["status"] for name in REQUIRED["analysis"]}}


def audit_rows(lab, result, frozen):
    proof, errors, children = [], [], 0
    for row in result["evaluations"]:
        cad = lab.inspect_experiment(row["cad_experiment_id"])
        require(cad["provenance"]["core_commit"] == frozen["core"]["core_commit"] and
                cad["provenance"]["core_dirty"] is False and
                cad["provenance"]["core_source_sha256"] == frozen["core"]["core_source_sha256"], "CAD source closure mismatch")
        require(row["decision"] == cad["decision"] == "NOT_RELEASED" and UNKNOWN <= set(row["unknown"]), "Unknown/release semantics lost")
        detail = {"index": row["index"], "cad_experiment_id": cad["experiment_id"],
                  "cad_status": cad["status"], "analysis_status": row["analysis_status"],
                  "width_mm": row["values"]["support_width"], "feedback": row["feedback"],
                  "constraints": row["constraints"], "unknown": row["unknown"]}
        if cad["status"] == "COMPLETED_REVIEW_REQUIRED":
            exact = analytical_volume(row["values"]["support_width"])
            error = abs(cad["metrics"]["cad_volume"]["value"] / exact - 1)
            require(error < LIMITS["cad_volume_relative_error_limit"], "Analytical CAD volume failed")
            require(row["values"]["support_width"] > frozen["geometry_reference"]["open_width_lower_bound_mm"], "Invalid open-bound CAD accepted")
            errors.append(error)
            detail.update({"analytical_volume_mm3": exact, "cad_volume_relative_error": error})
        else:
            require(cad["status"] == "REJECTED" and row["analysis_experiment_id"] is None,
                    "A rejected CAD generated a solver child or infrastructure failure was hidden")
            require(not (lab.store / "experiments" / (cad["experiment_id"] + "-solve")).exists(), "Rejected CAD has downstream files")
        if row["analysis_experiment_id"]:
            child = check_solve(lab, row["analysis_experiment_id"], cad, frozen)
            require(child["result"]["provenance"]["core_commit"] == frozen["core"]["core_commit"] and
                    child["result"]["provenance"]["core_dirty"] is False, "Solver source mismatch")
            children += 1
            detail.update({"analysis_experiment_id": row["analysis_experiment_id"], "parent_step_sha256": child["parent_step_sha256"],
                           "required_checks": child["required_checks"], "raw_mesh_studies": child["raw"]["mesh_studies"]})
        if row["usable"]:
            require(detail["required_checks"] == {name: "PASS" for name in REQUIRED["analysis"]}, "Usable feedback bypassed a required gate")
            response = row["constraints"][0]
            residual = (response["value"] - 0.0065) / 0.0065
            require(math.isclose(response["residual"], residual, rel_tol=1e-12, abs_tol=1e-14), "Constraint residual mismatch")
            require(row["numerically_feasible"] == (residual <= 0), "Constraint feasibility mismatch")
        else:
            require(row["feedback"] == {"objective": None, "constraint_residuals": [None]}, "Unusable feedback became a numeric penalty")
        proof.append(detail)
    rejected = result["evaluations"][0]
    require(rejected["values"] == {"support_width": 28.0} and rejected["cad_status"] == "REJECTED" and
            rejected["analysis_experiment_id"] is None, "Initial 28 mm CAD gate was not exercised")
    return {"evaluations": proof, "campaign_solver_children": children,
            "maximum_cad_volume_reference_error": max(errors)}


def run(store):
    store = Path(store).resolve()
    require(not store.exists(), "Use a new store; historical evidence cannot be overwritten")
    limits = apply_process_limits()
    from caelab import Lab
    from caelab.adapters.fixture_cadquery import FixtureCadQueryAdapter
    from caelab.storage import load_json, save_json, source_identity, utc_now
    store.mkdir(parents=True, exist_ok=False)
    started = utc_now()
    old_alarm = signal.getsignal(signal.SIGALRM)

    def watchdog(signum, frame):
        raise AcceptanceBudgetExceeded("Whole acceptance 90-minute wall-clock watchdog expired")

    signal.signal(signal.SIGALRM, watchdog)
    signal.setitimer(signal.ITIMER_REAL, LIMITS["wall_watchdog_seconds"])
    try:
        core = source_identity(ROOT)
        require(core["core_dirty"] is False and core["core_commit"] != "unavailable", "Commit a clean source before native acceptance")
        require(git(UPSTREAM, "status", "--porcelain", "--untracked-files=normal") == "", "Pinned upstream is dirty")
        frozen = {"started_utc": started, "core": core, "script_sha256": sha(Path(__file__)),
                  "plugin": FixtureCadQueryAdapter.source_fingerprint(), "source_files": file_records(),
                  "native_runtime": runtime_identity(), "material_sha256": sha(MATERIAL), "material": load_json(MATERIAL),
                  "geometry_reference": geometric_reference(), "limits": deepcopy(LIMITS), "process_limits": limits,
                  "qualification": "UNKNOWN", "decision": "NOT_RELEASED"}
        save_json(store / "acceptance/frozen.json", frozen)
        # Retain exact working source bytes, including Windows checkout line endings.
        for relative, record in frozen["source_files"].items():
            prefix, name = relative.split("/", 1)
            original = (ROOT if prefix == "repository" else UPSTREAM) / name
            destination = store / "acceptance/source" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, destination)
            require(sha(destination) == record["sha256"], "Source snapshot copy mismatch")
        lab = Lab(store)
        guard = Guard(store, frozen, save_json)
        guard.check_identity()
        lab.create_study(STUDY, "Predeclared multi-generation fixture refinement",
                         "Does a bounded five-generation numerical search improve its initial population?",
                         "Later feasible observations may reduce support volume under unchanged assumed physics.",
                         "Measure adaptive refinement, boundary margin, response slack and exact restart; never qualify strength.")
        lab.register_parameter(STUDY, "fixture.cadquery", "roller_support", "support_width_mm",
                               "support_width", "Support width", 28, 42)
        settings = {"load": {"force_per_support_N": 100.0,
                             "source": "Illustrative 100 N screen per support; unqualified, not measured"},
                    "material": frozen["material"], "mesh": {"max_sizes_mm": [2.0, 1.5]}}
        plan = lab.plan_optimization(study_id=STUDY, campaign_id=CAMPAIGN, backend="fixture.cadquery",
                                     model="roller_support", parameter_ids=["support_width"],
                                     objective={"source": "cad", "metric": "cad_volume", "unit": "mm^3", "direction": "minimize"},
                                     constraints=[{"source": "analysis", "metric": "max_displacement", "unit": "mm",
                                                   "operator": "<=", "limit": 0.0065, "scale": 0.0065}],
                                     seed=13, max_generations=5, population_size=5, initial_values={"support_width": 28.0},
                                     analysis_backend="fixture.calculix", analysis_settings=settings, required_validations=REQUIRED)
        campaign = store / "optimizations" / CAMPAIGN
        save_json(store / "acceptance/pre_native_plan.json", {"plan": plan, "plan_sha256": sha(campaign / "plan.json"),
                                                              "frozen_sha256": sha(store / "acceptance/frozen.json"),
                                                              "limits": LIMITS, "recorded_utc": utc_now()})
        guard.bind(lab, pause=True)
        baseline = lab.run_experiment(study_id=STUDY, experiment_id="E-refinement-baseline-cad",
                                      backend="fixture.cadquery", model="roller_support", values={"support_width": 38.0})
        baseline_solve = lab.run_analysis(parent_experiment_id=baseline["experiment_id"],
                                          experiment_id="E-refinement-baseline-solve", backend="fixture.calculix", settings=settings)
        require(baseline_solve["status"] == "COMPLETED_REVIEW_REQUIRED", "Baseline numerical screen failed")
        baseline_proof = check_solve(lab, baseline_solve["experiment_id"], baseline, frozen)
        require(abs(baseline["metrics"]["cad_volume"]["value"] / analytical_volume(38) - 1) < 1e-9,
                "Baseline analytical CAD volume failed")
        try:
            lab.run_optimization(CAMPAIGN)
        except PlannedInterruption:
            pass
        else:
            raise AssertionError("Planned seventh-evaluation interruption was not reached")
        partial = lab.inspect_optimization(CAMPAIGN)
        require(partial["status"] == "RUNNING" and partial["completed_evaluations"] == 7, "Interrupted prefix is not seven completed evaluations")
        require(not (store / "experiments" / f"E-{CAMPAIGN}-0008").exists(), "Eighth CAD began before interruption")
        prefix = retained_prefix(store, partial)
        save_json(store / "acceptance/interruption/prefix_manifest.json", prefix)
        shutil.copyfile(campaign / "state.json", store / "acceptance/interruption/state.json")
        shutil.copyfile(store / "ledger" / f"optimization-{CAMPAIGN}.json", store / "acceptance/interruption/optimization-ledger.json")
        old_call_counts = [len(guard.cad_ids), len(guard.solver_ids)]
        resumed = Lab(store)
        guard.bind(resumed)
        result = resumed.run_optimization(CAMPAIGN)
        require(result["evaluations"][:7] == prefix["partial_evaluations"], "Deterministic restart changed earlier observations")
        verify_preserved(store, prefix["files"])
        verify_preserved(store / "acceptance/source", frozen["source_files"])
        for relative, saved in prefix["experiment_trees"].items():
            require(inventory(store / relative) == saved, "A completed prefix experiment tree changed")
        require(result["algorithm"] == plan["algorithm"], "Frozen numerical engine options changed")
        require(len(result["evaluations"]) <= 30 and result["termination"]["evaluation_count"] == len(result["evaluations"]), "Campaign CAD count exceeded declaration")
        proof = audit_rows(resumed, result, frozen)
        require(proof["campaign_solver_children"] <= 29 and 2 * (proof["campaign_solver_children"] + 1) <= 60,
                "Campaign solver/mesh budget exceeded declaration")
        require(len(guard.cad_ids) == 1 + len(result["evaluations"]) and
                len(guard.solver_ids) == 1 + proof["campaign_solver_children"], "Replayed experiments were rerun")
        require(result["decision"] == "NOT_RELEASED" and result["incumbent"] is not None, "No feasible incumbent or release promoted")
        history = refinement_history(result["evaluations"])
        require(history["final_incumbent"] == result["incumbent"], "Independent incumbent reconstruction mismatch")
        # Completed reuse must need no installed backend, optimizer or adapter.
        before_reuse = inventory(store)
        offline = Lab(store, adapters={}, analysis_adapters={}, doe_adapters={}, optimization_adapters={},
                      pde_adapters={}, model_analysis_adapters={})
        require(offline.run_optimization(CAMPAIGN) == result and offline.inspect_optimization(CAMPAIGN) == result,
                "Empty-adapter completed reuse differs")
        require(inventory(store) == before_reuse, "Completed reuse changed retained bytes")
        guard.boundary("FINAL_IDENTITY_AND_RESOURCE_CHECK", CAMPAIGN)
        save_json(store / "acceptance/evaluation_proof.json", proof)
        save_json(store / "acceptance/refinement_history.json", history)
        save_json(store / "acceptance/completed_reuse_manifest.json", before_reuse)
        manifest = inventory(store)
        save_json(store / "acceptance/full_store_manifest.json", manifest)
        best = result["incumbent"]
        report = {"status": "PASS", "campaign_id": CAMPAIGN, "started_utc": started, "completed_utc": utc_now(),
                  "decision": "NOT_RELEASED", "source": frozen["core"], "script_sha256": frozen["script_sha256"],
                  "plugin": frozen["plugin"], "native_runtime": frozen["native_runtime"], "limits": LIMITS,
                  "algorithm": result["algorithm"], "termination": result["termination"],
                  "multigeneration": "OBSERVED" if result["termination"]["generations"] >= 2 else "NOT_OBSERVED",
                  "adaptive_refinement": history["adaptive_refinement"],
                  "initial_population_best": history["initial_population_best"],
                  "later_volume_improvement_mm3": history["later_volume_improvement_mm3"],
                  "evaluations": len(result["evaluations"]), "solver_children": proof["campaign_solver_children"],
                  "mesh_solver_runs_including_baseline": 2 * (proof["campaign_solver_children"] + 1),
                  "replayed_evaluations_without_rerun": 7, "calls_at_interruption": old_call_counts,
                  "total_cad_calls": len(guard.cad_ids), "total_solver_child_calls": len(guard.solver_ids),
                  "prefix_files_unchanged": len(prefix["files"]), "completed_empty_adapter_reuse": "PASS",
                  "baseline": {"width_mm": 38.0, "volume_mm3": baseline["metrics"]["cad_volume"]["value"],
                               "displacement_mm": baseline_solve["metrics"]["max_displacement"]["value"],
                               "parent_step_sha256": baseline_proof["parent_step_sha256"]},
                  "best": {"index": best["index"], "values": best["values"], "volume_mm3": best["objective"]["value"],
                           "displacement_mm": best["constraints"][0]["value"],
                           "displacement_slack_mm": 0.0065 - best["constraints"][0]["value"],
                           "width_minus_open_bound_mm": best["values"]["support_width"] - 28.5,
                           "cad_experiment_id": best["cad_experiment_id"], "analysis_experiment_id": best["analysis_experiment_id"]},
                  "maximum_cad_volume_reference_error": proof["maximum_cad_volume_reference_error"],
                  "geometry_reference": frozen["geometry_reference"],
                  "result_sha256": sha(campaign / "result.json"),
                  "frozen_sha256": sha(store / "acceptance/frozen.json"),
                  "plan_sha256": sha(campaign / "plan.json"),
                  "prefix_manifest_sha256": sha(store / "acceptance/interruption/prefix_manifest.json"),
                  "evaluation_proof_sha256": sha(store / "acceptance/evaluation_proof.json"),
                  "history_sha256": sha(store / "acceptance/refinement_history.json"),
                  "full_store_manifest_sha256": sha(store / "acceptance/full_store_manifest.json"),
                  "retained_before_final_manifest_and_report": {"file_count": manifest["file_count"], "size_bytes": manifest["size_bytes"]},
                  "limitations": ["Finite observations and five-generation budget are not a global/converged optimum certificate.",
                                  "28.5 mm is an open geometric bound; no design at equality is admitted.",
                                  "Measured response slack is reported without assuming an active displacement constraint.",
                                  "ASSUMED orthotropic material, idealized fixed base and 100 N saddle traction are unqualified.",
                                  "Source/mesh/deck/raw fields are retained locally; no remote durable raw archive is claimed.",
                                  "The 8 GiB store check runs at boundaries and is not an instantaneous disk quota.",
                                  "The address-space cap is inherited per process, not a combined RAM/cgroup quota.",
                                  "Native executable hashes do not close every host shared-library identity.",
                                  "Static strength, contact/fasteners, material, machine, physical and fatigue gates remain UNKNOWN."]}
        save_json(store / "fixture_refinement_acceptance.json", report)
        print(json.dumps(report), flush=True)
        return report
    except BaseException as error:
        signal.setitimer(signal.ITIMER_REAL, 0)
        failure = {"status": "FAILED_ACCEPTANCE", "started_utc": started, "failed_utc": utc_now(),
                   "exception_type": type(error).__name__, "reason": str(error), "decision": "NOT_RELEASED",
                   "policy": "Retain all files; infrastructure failure is not numerical infeasibility/convergence"}
        save_json(store / "fixture_refinement_failure.json", failure)
        print(json.dumps(failure), flush=True)
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_alarm)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    options = parser.parse_args()
    outcome = run(options.store) if options._worker else supervise(options.store)
    if outcome["status"] != "PASS":
        raise SystemExit(1)
