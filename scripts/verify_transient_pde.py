"""Fresh, committed-source transient rectangle acceptance; not a source test.

Native execution happens only on explicit invocation. Failed and rejected
histories remain in their original experiments; a later receipt is no rerun.
"""

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from caelab import Lab
from caelab.adapters.fenicsx_transient_worker import SOURCE_PATHS
from caelab.storage import canonical_hash, load_json, save_json, source_identity, utc_now
from plugins.pde_transient.reference import manufactured_settings


REPOSITORY = Path(__file__).resolve().parents[1]
BACKEND = "pde.fenicsx.transient"
SOURCE_FILES = ("scripts/verify_transient_pde.py", *[item[0] for item in SOURCE_PATHS.values()])


def specification(axis="mesh"):
    return manufactured_settings(axis=axis, case="temporal" if axis == "time" else "polynomial")


def cases():
    """Freeze every condition and unchanged numerical limit before the first call."""
    accepted = {
        "E-transient-mesh": specification(),
        "E-transient-time": specification("time"),
        "E-transient-reaction": manufactured_settings(axis="time", case="temporal", reaction=3.0),
        "E-transient-domain": manufactured_settings(lengths=(1.5, .75), diffusion=.5, reaction=3.0),
        "E-transient-zero-source": manufactured_settings(case="zero_source"),
    }
    rejected = {name: deepcopy(accepted["E-transient-time"]) for name in
                ("E-transient-reference-reject", "E-transient-flux-reject", "E-transient-time-rhs-reject")}
    rejected["E-transient-reference-reject"]["problem"]["reference"]["solution"] = "0.0"
    for side in ("xmax", "ymax"):
        boundary = rejected["E-transient-flux-reject"]["problem"]["boundaries"][side]
        boundary["value"] = f"-({boundary['value']})"
    rejected["E-transient-time-rhs-reject"]["problem"]["weak_form"]["rhs"] = "-(x[0]+2*x[1]+1)"
    refused = {name: deepcopy(accepted["E-transient-mesh"]) for name in
               ("E-transient-invalid-expression", "E-transient-invalid-corner", "E-transient-invalid-initial",
                "E-transient-invalid-pure-neumann", "E-transient-invalid-work")}
    refused["E-transient-invalid-expression"]["problem"]["weak_form"]["rhs"] = "x.__class__"
    corner = refused["E-transient-invalid-corner"]["problem"]["boundaries"]["xmin"]
    corner["value"] = f"({corner['value']})+1"
    initial = refused["E-transient-invalid-initial"]["problem"]["initial"]
    initial["value"] = f"({initial['value']})+1"
    refused["E-transient-invalid-pure-neumann"]["problem"]["boundaries"] = {
        side: {"type": "neumann", "value": "0.0"} for side in ("xmin", "xmax", "ymin", "ymax")}
    refused["E-transient-invalid-work"]["mesh"]["cell_counts"] = [32, 64, 128]
    refused["E-transient-invalid-work"]["time"]["step_counts"] = [128]
    return accepted, rejected, refused


def _require(condition, description):
    if not condition:
        raise AssertionError(description)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_pin():
    return {"core": source_identity(REPOSITORY),
            "files": {relative: _sha(REPOSITORY / relative) for relative in SOURCE_FILES}}


def _verify_source(pin, result=None, root=None):
    _require(_source_pin() == pin, "Transient acceptance source drift; original results remain retained")
    if result is None:
        return
    _require({key: result["provenance"].get(key) for key in pin["core"]} == pin["core"],
             "Retained provenance differs from the frozen clean source")
    if root is not None and (root / "pde/command.json").exists():
        manifest = load_json(root / "pde/source_manifest.json")
        _require(set(manifest["files"]) == set(SOURCE_PATHS), "Missing/extra copied native source identity")
        for key, (repository_path, copied_path) in SOURCE_PATHS.items():
            identity = manifest["files"][key]
            _require(identity == {"repository_path": repository_path, "copied_path": copied_path,
                                 "sha256": pin["files"][repository_path]}, "Native source manifest binding differs")
            _require(_sha(root / "pde" / copied_path) == identity["sha256"], "Saved native source bytes drifted")


def _run_fixed(lab, store, pin, study, experiment, request):
    _verify_source(pin)
    try:
        result = lab.run_pde(study_id=study, experiment_id=experiment, backend=BACKEND, settings=request)
    except BaseException:
        _verify_source(pin)
        raise
    _verify_source(pin, result, store / "experiments" / experiment)
    return result


def _pairs(settings):
    ns, steps = settings["mesh"]["cell_counts"], settings["time"]["step_counts"]
    return list(zip(ns, steps * len(ns))) if settings["refinement_axis"] == "mesh" else list(zip(ns * len(steps), steps))


def _values_identity(field):
    return canonical_hash({"node_ids": field["node_ids"], "values": field["values"]})


def _geometry_identity(field):
    return canonical_hash({key: field[key] for key in ("node_ids", "coordinates", "cell_node_ids", "dirichlet_node_ids")} | {
        "boundaries": {side: {key: value for key, value in boundary.items()
                              if key not in ("prescribed_values", "prescribed_integral")}
                       for side, boundary in field["boundaries"].items()}})


def _polynomial(x, y):
    return x*x*y*y+x+2*y+1


def _reference_value(experiment, x, y, time):
    if experiment == "E-transient-reference-reject":
        return 0.
    if experiment == "E-transient-zero-source":
        return x*x+y*y+4*time+x+2*y+1
    if experiment in ("E-transient-mesh", "E-transient-domain"):
        return (1+time)*_polynomial(x, y)
    return math.exp(-time)*(x+2*y+1)


def _initial_value(experiment, x, y):
    if experiment == "E-transient-zero-source":
        return x*x+y*y+x+2*y+1
    if experiment in ("E-transient-mesh", "E-transient-domain"):
        return _polynomial(x, y)
    return x+2*y+1


def _rhs_value(experiment, settings, x, y, time):
    if experiment == "E-transient-zero-source":
        return 0.
    if experiment == "E-transient-time-rhs-reject":
        return -(x+2*y+1)
    weak = settings["problem"]["weak_form"]
    if experiment in ("E-transient-mesh", "E-transient-domain"):
        return _polynomial(x, y)+(1+time)*(-2*weak["diffusion"]*(x*x+y*y)+weak["reaction"]*_polynomial(x, y))
    return (weak["reaction"]-1)*math.exp(-time)*(x+2*y+1)


def _history(store, experiment, settings):
    """Inspect raw saved steps with independent polynomials, not the new parser."""
    output = store / "experiments" / experiment / "pde"
    raw = load_json(output / "worker_result.json")
    _require(raw["status"] == "COMPLETED" and raw["mpi_size"] == 1 and raw["scalar_type"] == "float64",
             "A complete real serial native history is required")
    pairs = _pairs(settings)
    _require(len(raw["studies"]) == len(pairs), "Native refinement study omitted or duplicated")
    snapshots = solves = 0
    for index, (row, (count, step_count)) in enumerate(zip(raw["studies"], pairs)):
        _require(row["study_index"] == index and row["cells_per_axis"] == count and row["step_count"] == step_count,
                 "Native study identity differs from the frozen mesh/time axis")
        _require(len(row["steps"]) == step_count+1, "Every initial/intermediate/final field must be retained")
        previous = geometry = None
        dt = settings["time"]["end"]/step_count
        for j, step in enumerate(row["steps"]):
            time = j*dt
            _require(step["index"] == j and math.isclose(step["time"], time, rel_tol=1e-12, abs_tol=1e-12)
                     and math.isclose(step["native_time_value"], time, rel_tol=1e-12, abs_tol=1e-12),
                     "A saved step uses a wrong/duplicate/stale native time")
            _require(step["dt"] == (dt if j else 0.) and step["distinct_state"] is True
                     and step["previous_values_sha256"] == previous, "Previous/current native state binding differs")
            for key, relative in step["files"].items():
                _require(_sha(output / relative) == step["artifact_sha256"][key], "Retained transient step bytes drifted")
            field = load_json(output / step["files"]["dofs"])
            binding = load_json(output / step["files"]["time_binding"])
            _require(load_json((output / step["files"]["dofs"]).parent / "observation.json") == step,
                     "The retained step observation differs from the completed history")
            _require(field["node_ids"] == sorted(field["node_ids"]) and len(field["node_ids"]) == (count+1)**2,
                     "Complete ordered native IDs are required for state identity")
            current = _values_identity(field)
            _require(current == step["current_values_sha256"], "Saved field does not match the native state identity")
            current_geometry = _geometry_identity(field)
            _require(geometry is None or geometry == current_geometry, "Native geometry/topology changed within a time history")
            geometry, previous = current_geometry, current
            _require(binding["time"] == step["time"] and binding["node_ids"] == field["node_ids"], "Time binding identity differs")
            _require(len(binding["rhs_values"]) == len(field["node_ids"]) == len(binding["reference_values"]),
                     "Complete source and reference samples are required")
            for slot, (x, y) in enumerate(field["coordinates"]):
                _require(math.isclose(binding["rhs_values"][slot], _rhs_value(experiment, settings, x, y, time),
                                     rel_tol=1e-12, abs_tol=1e-12), "Native source coefficient does not bind declared time")
                _require(math.isclose(binding["reference_values"][slot], _reference_value(experiment, x, y, time),
                                     rel_tol=1e-12, abs_tol=1e-12), "Native reference does not bind declared time")
                if not j:
                    _require(math.isclose(field["values"][slot], _initial_value(experiment, x, y),
                                         rel_tol=1e-12, abs_tol=1e-12), "Initial nodal interpolation differs")
            if not j:
                _require(step["solver_status"] == "NOT_RUN" and step["linear_residual"] is None
                         and step["ksp_convergence_reason"] is None and step["ksp_iterations"] is None,
                         "Initial interpolation must not claim a solver execution")
            else:
                _require(step["solver_status"] == "COMPLETED" and step["ksp_convergence_reason"] > 0,
                         "Every native time step must actually converge")
                residual = step["linear_residual"]
                value = residual["absolute"]/residual["rhs_norm"] if residual["rhs_norm"] else residual["absolute"]
                _require(math.isclose(residual["relative"], value, rel_tol=1e-12, abs_tol=0.)
                         and value <= settings["validation"]["max_residual_relative"], "Every constrained step residual must pass")
                solves += 1
            snapshots += 1
    return raw, snapshots, solves


def _checked(lab, experiment):
    result = lab.inspect_experiment(experiment)
    _require(result["decision"] == "NOT_RELEASED" and result["cad_revision"] is None
             and "parent_experiment_id" not in result, "PDE mathematical evidence is not CAD/engineering release")
    _require({"model_qualification", "physical_validation"} <= set(lab.research_summary(experiment)["unknown"]),
             "Qualification must stay UNKNOWN")
    return result


def _manifest(root):
    return {str(path.relative_to(root)).replace("\\", "/"): _sha(path)
            for path in root.rglob("*") if path.is_file()}


def run(store):
    store = Path(store).resolve()
    if store.exists():
        raise ValueError("Transient acceptance requires a fresh store; keep every prior attempt")
    started, pin = utc_now(), _source_pin()
    _require(pin["core"]["core_dirty"] is False and pin["core"]["core_commit"] != "unavailable",
             "Native acceptance requires clean committed source; source tests are separate")
    accepted, rejected, refused = cases()
    plan = {"schema_version": "1", "status": "FROZEN_BEFORE_FIRST_NATIVE_CALL", "source_pin": pin,
            "accepted": deepcopy(accepted), "numerical_rejections": deepcopy(rejected), "preflight_rejections": deepcopy(refused),
            "expected_solver_processes": len(accepted)+len(rejected), "fixed_wall_timeout": None}
    lab = Lab(store)
    study = "S-transient-pde"
    lab.create_study(study, "Transient scalar rectangles and immutable time histories",
                     "Do independent time/mesh refinements reproduce declared evolving reference fields?",
                     "Backward Euler and P1 converge at orders1 in time and2/1 in space with full step binding.",
                     "Retain initial/intermediate/final fields, rejections and UNKNOWN qualification.")
    save_json(store / "transient_pde_plan.json", plan)
    plan_sha256 = _sha(store / "transient_pde_plan.json")
    progress = {"schema_version": "1", "status": "RUNNING", "source_pin": pin, "completed": {}}
    save_json(store / "transient_pde_progress.json", progress)
    preserved, observations, results = {}, {}, {}
    snapshots = solves = 0
    try:
        for expected, group in (("accepted", accepted), ("numerical_rejections", rejected), ("preflight_rejections", refused)):
            for experiment, request in group.items():
                _require(_sha(store / "transient_pde_plan.json") == plan_sha256,
                         "A changed frozen plan must block every subsequent native call")
                result = _run_fixed(lab, store, pin, study, experiment, request)
                _require(_sha(store / "transient_pde_plan.json") == plan_sha256,
                         "Frozen plan changed during the native call; keep its result")
                _require(_checked(lab, experiment) == result, "Stored result and immutable ledger must agree")
                root = store / "experiments" / experiment
                if expected == "preflight_rejections":
                    _require(result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN"
                             and not (root / "pde/command.json").exists(), "Invalid input must block native execution")
                else:
                    _require(result["status"] == ("COMPLETED_REVIEW_REQUIRED" if expected == "accepted" else "REJECTED")
                             and result["solver_status"] == "COMPLETED", "Frozen numerical acceptance/rejection differs")
                    _require(bool(result["metrics"]) and all(metric["valid"] is (expected == "accepted")
                             for metric in result["metrics"].values()), "Finite rejected observations must remain invalid")
                    declaration = lab.pde_adapters[BACKEND].describe_model(deepcopy(request))
                    _require(result["model_revision"] == canonical_hash({"settings": request, "declaration": declaration}),
                             "Time/initial/source/boundary declarations must enter the common model revision")
                    raw, count, solved = _history(store, experiment, request)
                    snapshots, solves = snapshots+count, solves+solved
                    observations[experiment] = raw
                results[experiment] = result
                preserved.update({f"experiments/{experiment}/{name}": value for name, value in _manifest(root).items()})
                progress["completed"][experiment] = {"status": result["status"], "solver_status": result["solver_status"],
                                                     "model_revision": result["model_revision"]}
                save_json(store / "transient_pde_progress.json", progress)
        _verify_source(pin)
        _require(_sha(store / "transient_pde_plan.json") == plan_sha256,
                 "The plan must remain frozen after every native call")
        for name, value in preserved.items():
            _require(_sha(store / name) == value, "A later experiment overwrote an original retained history")
    except BaseException as exc:
        progress.update(status="FAILED_OR_PARTIAL", failure_type=type(exc).__name__, reason=str(exc))
        save_json(store / "transient_pde_progress.json", progress)
        raise
    progress["status"] = "COMPLETED_BOUNDED_MATHEMATICAL"
    save_json(store / "transient_pde_progress.json", progress)
    report = {"schema_version": "1", "status": "PASS_BOUNDED_MATHEMATICAL", "started_utc": started,
              "finished_utc": utc_now(), "source_pin": pin, "frozen_plan_sha256": plan_sha256,
              "accepted": list(accepted), "numerical_rejections": list(rejected), "preflight_rejections": list(refused),
              "solver_processes": len(accepted)+len(rejected), "native_studies": sum(len(raw["studies"]) for raw in observations.values()),
              "retained_snapshots": snapshots, "native_solves": solves,
              "cases": {name: {"metrics": results[name]["metrics"], "versions": raw["versions"], "studies": raw["studies"]}
                        for name, raw in observations.items()}, "preserved_artifact_hashes": preserved,
              "provider_calls": 0, "official_openscience_runs": 0, "decision": "NOT_RELEASED",
              "limitations": ["Manufactured scalar real P1 rectangle/backward-Euler mathematical checks only.",
                              "No physical/model release, arbitrary PDE/coupling/MPI or new official Research admission.",
                              "Raw symbolic quadrature/residuals require separate independent field review.",
                              "Snapshot/source/time binding is not physical solution flux-balance proof."]}
    save_json(store / "transient_pde_acceptance.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=Path("artifacts/transient-pde-lab"))
    options = parser.parse_args()
    receipt = run(options.store)
    print(json.dumps({key: receipt[key] for key in ("status", "accepted", "numerical_rejections", "preflight_rejections",
                     "solver_processes", "native_studies", "retained_snapshots", "native_solves")}, indent=2))
