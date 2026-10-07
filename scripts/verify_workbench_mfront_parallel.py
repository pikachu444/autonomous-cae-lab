"""Actual managed two-process MGIS fit, candidate reset and cancellation probe.

Operator native-environment.json supplies a separately built Elasticity library.
Synthetic stresses are calculated independently from isotropic Hooke law; no
physical qualification is inferred. Each invocation requires a new store.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import resource
import time

from caelab.storage import save_json
from caelab.workbench import Workbench


TRUTH = {"youngs_modulus_mpa": 275., "poisson_ratio": .28}
INITIAL = {"youngs_modulus_mpa": 180., "poisson_ratio": .2}
VARIABLES = [
    {"id": "youngs_modulus_mpa", "unit": "MPa", "lower": 100., "upper": 500., "value": 180.},
    {"id": "poisson_ratio", "unit": "1", "lower": .05, "upper": .45, "value": .2},
]


def _history(component, *, length=5):
    rows = [{"time_s": 0., "strain": [0.] * 6}]
    for index in range(1, length):
        strain = [0.] * 6
        strain[component] = (.0003 + .0002 * index) * (-1 if index % 2 else 1)
        rows.append({"time_s": float(index) / 4, "strain": strain})
    return rows


def _settings(history):
    return {"material": dict(INITIAL), "temperature_k": 293.15, "history": history}


def _stress(material, strain):
    young, nu = material["youngs_modulus_mpa"], material["poisson_ratio"]
    lam = young * nu / ((1 + nu) * (1 - 2 * nu))
    mu = young / (2 * (1 + nu))
    return [2 * mu * strain[i] + (lam * sum(strain[:3]) if i < 3 else 0.) for i in range(6)]


def _observation(history, component):
    name = ("xx", "yy", "zz", "xy", "xz", "yz")[component]
    return {"kind": "series", "value": [_stress(TRUTH, row["strain"])[component] for row in history],
            "unit": "MPa", "component": name, "location": "material point", "reduction": "none",
            "axes": [{"name": "time", "unit": "s", "values": [row["time_s"] for row in history]}]}


def _descendants():
    """Return only descendants of this verifier from Linux procfs."""
    processes = {}
    for path in Path("/proc").glob("[0-9]*"):
        try:
            status = (path / "status").read_text(encoding="utf-8")
            fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
            processes[int(path.name)] = {"ppid": int(fields["PPid"].strip()),
                "rss_kib": int(fields.get("VmRSS", "0 kB").strip().split()[0]),
                "name": fields["Name"].strip()}
        except (OSError, KeyError, ValueError, IndexError):
            pass
    owned = {os.getpid()}
    changed = True
    while changed:
        before = len(owned)
        owned.update(pid for pid, entry in processes.items() if entry["ppid"] in owned)
        changed = len(owned) > before
    return {pid: entry for pid, entry in processes.items() if pid in owned and pid != os.getpid()}


def _wait(bench, job, *, monitor, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        children = _descendants()
        monitor["peak_descendant_rss_kib"] = max(monitor["peak_descendant_rss_kib"],
                                                  sum(row["rss_kib"] for row in children.values()))
        monitor["seen_processes"].update({str(pid): row["name"] for pid, row in children.items()})
        state = bench.manager.status(job["id"])
        if state["state"] in {"SUCCEEDED", "FAILED", "CANCELLED", "PARTIAL_FAILURE", "INTERRUPTED"}:
            return state
        time.sleep(.02)
    raise TimeoutError(job["id"])


def _candidate_audit(root):
    folders = sorted((root / "native").glob("*/prepared-*"))
    if not folders:
        raise AssertionError("No prepared worker resource was retained")
    seen_ids, max_error, records = set(), 0., []
    for folder in folders:
        library = (folder / "prepared_execution.json")
        if not library.is_file():
            raise AssertionError(f"Missing library identity: {folder}")
        identity = json.loads(library.read_text(encoding="utf-8"))
        candidates = []
        for result_file in sorted((folder / "candidates").glob("*/result.json")):
            result = json.loads(result_file.read_text(encoding="utf-8"))
            request = json.loads((result_file.parent / "input.json").read_text(encoding="utf-8"))
            if result["candidate_id"] in seen_ids or result["candidate_id"] != request["candidate_id"]:
                raise AssertionError("Candidate identity collision")
            seen_ids.add(result["candidate_id"])
            if result["execution_status"] == "SUCCEEDED":
                for native, prescribed in zip(result["rows"], request["history"]):
                    expected = _stress(request["material"], prescribed["strain"])
                    max_error = max(max_error, *(abs(a - b) for a, b in zip(native["stress_physical_mpa"], expected)))
            candidates.append({"candidate_id": result["candidate_id"], "material": request["material"],
                               "execution_status": result["execution_status"]})
        records.append({"folder": str(folder), "library_sha256": identity["library_sha256"],
                        "worker_sha256": identity["worker_sha256"], "candidates": candidates})
    if max_error > 1e-10:
        raise AssertionError(f"Independent Hooke stress error {max_error}")
    return records, max_error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True)
    args = parser.parse_args()
    root = Path(args.store).resolve()
    root.mkdir(parents=True, exist_ok=False)
    bench = Workbench(root, configuration={"workers": 2, "cpu_budget": 4, "workspace_id": "mfront-parallel"})
    monitor = {"peak_descendant_rss_kib": 0, "seen_processes": {}}
    started = time.perf_counter()
    try:
        experiments = []
        for index, component in enumerate((0, 3, 0)):
            history = _history(component)
            experiments.append({"id": f"history-{index}", "role": "holdout" if index == 2 else "fit",
                                "settings": _settings(history), "response": "stress_xy" if component == 3 else "stress_xx",
                                "observations": _observation(history, component), "weight": 1., "scale": .1})
        fit = bench.submit("fit", {"backend": "material.mfront.prepared", "variables": VARIABLES,
            "experiments": experiments, "options": {"max_nfev": 25},
            "execution": {"mode": "process", "workers": 2, "threads": 1, "max_evaluations": 160}})
        fit_status = _wait(bench, fit, monitor=monitor)
        if fit_status["state"] != "SUCCEEDED":
            raise AssertionError(f"Two-process fit failed: {fit_status['state']} {fit_status.get('error')}")
        fit_result = bench.result(fit["id"])
        if (abs(fit_result["parameters"]["youngs_modulus_mpa"] - TRUTH["youngs_modulus_mpa"]) > 1e-4 or
            abs(fit_result["parameters"]["poisson_ratio"] - TRUTH["poisson_ratio"]) > 1e-6 or
            max(curve["rmse"] for curve in fit_result["curves"]) > 1e-8):
            raise AssertionError("Parallel fit did not identify both synthetic parameters")

        # A,B,A is enough to expose stale native state while 512 longer
        # histories give cancellation a real active process batch to stop.
        long_history = _history(3, length=32)
        a, b = dict(TRUTH), {"youngs_modulus_mpa": 320., "poisson_ratio": .31}
        candidates = [{"id": f"C{i:05d}", "values": material} for i, material in
                      enumerate([a, b, a] + [a if i % 2 else b for i in range(509)])]
        doe = bench.submit("doe", {"backend": "material.mfront.prepared", "variables": VARIABLES,
            "settings": _settings(long_history), "candidates": candidates,
            "execution": {"mode": "process", "workers": 2, "threads": 1, "max_evaluations": 512}})
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            prepared = list((bench.root / "native" / doe["id"]).glob("prepared-*/candidates/*/result.json"))
            if len(prepared) >= 2:
                break
            if bench.manager.status(doe["id"])["state"] in {"SUCCEEDED", "FAILED", "CANCELLED", "PARTIAL_FAILURE"}:
                break
            time.sleep(.01)
        before_cancel = len(list((bench.root / "native" / doe["id"]).glob("prepared-*/candidates/*/result.json")))
        cancel_receipt = bench.manager.cancel(doe["id"])
        doe_status = _wait(bench, doe, monitor=monitor)
        if doe_status["state"] != "CANCELLED":
            raise AssertionError(f"Active DOE cancellation did not finish CANCELLED: {doe_status['state']} {doe_status.get('error')}")
        doe_result = bench.result(doe["id"])
        counts = {status: sum(row["execution_status"] == status for row in doe_result["candidates"])
                  for status in ("SUCCEEDED", "CANCELLED", "FAILED", "REJECTED")}
        if len(doe_result["candidates"]) != 512 or counts["CANCELLED"] == 0 or counts["SUCCEEDED"] == 0:
            raise AssertionError(f"Cancellation did not preserve partial candidate journal: {counts}")
        records, max_error = _candidate_audit(bench.root)
        fit_resources = [entry for entry in records if f"/{fit['id']}/" in entry["folder"]]
        if len(fit_resources) < 4 or len({entry["folder"] for entry in fit_resources}) < 4:
            raise AssertionError("Two fit process workers did not own distinct fit-history resources")
        # Model child processes must have ended after both jobs join.
        live = _descendants()
        if any("singularity" in row["name"].lower() or "python3" in row["name"].lower()
               for row in live.values()):
            raise AssertionError(f"Owned MGIS/process worker remains live: {live}")
        receipt = {"fit_job": fit["id"], "fit_state": fit_status["state"],
            "parameters": fit_result["parameters"], "fit_timing": fit_result["timing"],
            "fit_curve_rmse_mpa": [row["rmse"] for row in fit_result["curves"]],
            "doe_job": doe["id"], "doe_state": doe_status["state"],
            "cancel_requested_state": cancel_receipt["state"], "native_before_cancel": before_cancel,
            "candidate_status_counts": counts, "native_stress_max_error_mpa": max_error,
            "prepared_resources": records, "peak_descendant_rss_kib": monitor["peak_descendant_rss_kib"],
            "seen_processes": monitor["seen_processes"],
            "rusage_children_maxrss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
            "elapsed_seconds": time.perf_counter() - started,
            "qualification": "UNKNOWN; synthetic same-law observations only"}
        save_json(root / "parallel_receipt.json", receipt)
        print(json.dumps({key: value for key, value in receipt.items() if key != "prepared_resources"},
                         allow_nan=False), flush=True)
    finally:
        bench.shutdown(timeout=30)


if __name__ == "__main__":
    main()
