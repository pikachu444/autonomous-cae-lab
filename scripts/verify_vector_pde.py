"""Fresh committed-source vector acceptance with independent directed fields.

An explicit run invokes native solves. Source tests never substitute for these
mathematical/reference observations; previous stores and failures are retained.
"""

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from caelab import Lab
from caelab.adapters.fenicsx_vector_worker import SOURCE_PATHS
from caelab.storage import canonical_hash, load_json, save_json, source_identity, utc_now
from plugins.pde_vector.reference import manufactured_settings


REPOSITORY = Path(__file__).resolve().parents[1]
BACKEND = "pde.fenicsx.vector"
SOURCE_FILES = ("scripts/verify_vector_pde.py", *[item[0] for item in SOURCE_PATHS.values()])
COMPONENTS = ["u0", "u1"]
# Shifted5-point Gauss-Legendre: Duffy integrates squared quartics exactly.
_NODES = (-.906179845938664, -.5384693101056831, 0., .5384693101056831, .906179845938664)
_WEIGHTS = (.2369268850561891, .4786286704993665, .5688888888888889, .4786286704993665, .2369268850561891)
_QUADRATURE = tuple(((node+1)/2, weight/2) for node, weight in zip(_NODES, _WEIGHTS))


def specification():
    return manufactured_settings()


def cases():
    """All fixed controls exist before the first native call or output."""
    accepted = {
        "E-vector-mixed": specification(),
        "E-vector-reaction": manufactured_settings(reaction=3.0),
        "E-vector-domain": manufactured_settings(lengths=(1.5, .75), lame_lambda=3.0, lame_mu=.5, reaction=2.0),
        "E-vector-lambda-zero": manufactured_settings(lame_lambda=0.0),
        "E-vector-all-dirichlet": specification(),
        "E-vector-harmonic-zero-source": manufactured_settings(case="harmonic"),
    }
    request = accepted["E-vector-all-dirichlet"]
    request["problem"]["boundaries"] = {
        side: {"type": "dirichlet", "value": deepcopy(request["problem"]["reference"]["solution"])}
        for side in ("xmin", "xmax", "ymin", "ymax")}
    rejected = {name: deepcopy(accepted["E-vector-mixed"]) for name in (
        "E-vector-reference-reject", "E-vector-traction-reject", "E-vector-source-swap-reject")}
    rejected["E-vector-reference-reject"]["problem"]["reference"]["solution"][1] = "0.0"
    for side in ("xmax", "ymax"):
        values = rejected["E-vector-traction-reject"]["problem"]["boundaries"][side]["value"]
        values[1] = f"-({values[1]})"
    rejected["E-vector-source-swap-reject"]["problem"]["weak_form"]["rhs"].reverse()
    refused = {name: deepcopy(accepted["E-vector-mixed"]) for name in (
        "E-vector-invalid-expression", "E-vector-invalid-components", "E-vector-invalid-corner",
        "E-vector-invalid-mu", "E-vector-invalid-pure-traction")}
    refused["E-vector-invalid-expression"]["problem"]["weak_form"]["rhs"][0] = "x.__class__"
    refused["E-vector-invalid-components"]["problem"]["weak_form"]["rhs"].pop()
    values = refused["E-vector-invalid-corner"]["problem"]["boundaries"]["xmin"]["value"]
    values[1] = f"({values[1]})+1"
    refused["E-vector-invalid-mu"]["problem"]["weak_form"]["lame_mu"] = 0.0
    refused["E-vector-invalid-pure-traction"]["problem"]["boundaries"] = {
        side: {"type": "neumann", "value": ["0.0", "0.0"]} for side in ("xmin", "xmax", "ymin", "ymax")}
    return accepted, rejected, refused


def _require(condition, message):
    if not condition:
        raise AssertionError(message)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _close(actual, expected, message):
    _require(type(actual) in (int, float) and math.isfinite(actual) and
             math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-12), message)


def _source_pin():
    return {"core": source_identity(REPOSITORY),
            "files": {relative: _sha(REPOSITORY / relative) for relative in SOURCE_FILES}}


def _original_observations(raw, assessed):
    """Assessment may append diagnostics; it must preserve every native datum."""
    if isinstance(raw, dict):
        return isinstance(assessed, dict) and all(key in assessed and _original_observations(value, assessed[key])
                                                for key, value in raw.items())
    if isinstance(raw, list):
        return isinstance(assessed, list) and len(raw) == len(assessed) and all(
            _original_observations(value, candidate) for value, candidate in zip(raw, assessed))
    return type(raw) is type(assessed) and raw == assessed


def _verify_source(pin, result=None, folder=None):
    _require(_source_pin() == pin, "Vector acceptance source drift; original results retained")
    if result is None:
        return
    _require({key: result["provenance"].get(key) for key in pin["core"]} == pin["core"],
             "Retained vector provenance differs from frozen source")
    if folder is not None and (folder / "pde/command.json").exists():
        manifest = load_json(folder / "pde/source_manifest.json")
        _require(set(manifest["files"]) == set(SOURCE_PATHS), "Incomplete vector native source copies")
        for key, (repository_path, copied_path) in SOURCE_PATHS.items():
            item = manifest["files"][key]
            _require(item == {"repository_path": repository_path, "copied_path": copied_path,
                              "sha256": pin["files"][repository_path]}, "Vector native manifest identity drift")
            _require(_sha(folder / "pde" / copied_path) == item["sha256"], "Vector native copied bytes drift")


def _math(experiment, settings, x, y):
    """Direct derivatives, independent of native/Domain expression interpreters."""
    weak = settings["problem"]["weak_form"]
    lam, mu, c = weak["lame_lambda"], weak["lame_mu"], weak["reaction"]
    if experiment == "E-vector-harmonic-zero-source":
        u = [x*x-y*y+1, -2*x*y+2]
        gradient = [[2*x, -2*y], [-2*y, -2*x]]
        source = [c*value for value in u]
        stress = [[4*mu*x, -4*mu*y], [-4*mu*y, -4*mu*x]]
    else:
        u = [x*x*y*y+x+2*y+1, 2*x*x*y*y-3*x+y+2]
        gradient = [[2*x*y*y+1, 2*x*x*y+2], [4*x*y*y-3, 4*x*x*y+1]]
        source = [c*u[0]-2*mu*x*x-(4*mu+2*lam)*y*y-8*(mu+lam)*x*y,
                  c*u[1]-(8*mu+4*lam)*x*x-4*mu*y*y-4*(mu+lam)*x*y]
        divergence = gradient[0][0]+gradient[1][1]
        shear = mu*(gradient[0][1]+gradient[1][0])
        stress = [[2*mu*gradient[0][0]+lam*divergence, shear],
                  [shear, 2*mu*gradient[1][1]+lam*divergence]]
    reference, reference_gradient = deepcopy(u), deepcopy(gradient)
    if experiment == "E-vector-reference-reject":
        reference[1], reference_gradient[1] = 0.0, [0., 0.]
    if experiment == "E-vector-source-swap-reject":
        source.reverse()
    return {"solution": u, "gradient": gradient, "rhs": source, "stress": stress,
            "reference": reference, "reference_gradient": reference_gradient}


def _side_value(experiment, settings, side, x, y):
    data = _math(experiment, settings, x, y)
    if settings["problem"]["boundaries"][side]["type"] == "dirichlet":
        return data["solution"]
    axis, sign = (0, -1) if side == "xmin" else (0, 1) if side == "xmax" else (1, -1) if side == "ymin" else (1, 1)
    traction = [sign*data["stress"][component][axis] for component in range(2)]
    if experiment == "E-vector-traction-reject" and side in ("xmax", "ymax"):
        traction[1] = -traction[1]
    return traction


def _integrate_field(experiment, settings, field):
    """Directed component L2 and all four gradient errors on saved P1 cells."""
    coordinates = dict(zip(field["node_ids"], field["coordinates"]))
    values = dict(zip(field["node_ids"], field["values"]))
    l2, h1 = [0., 0.], [0., 0.]
    for ids in field["cell_node_ids"]:
        points, nodal = [coordinates[node] for node in ids], [values[node] for node in ids]
        (x0, y0), (x1, y1), (x2, y2) = points
        det = (x1-x0)*(y2-y0)-(x2-x0)*(y1-y0)
        _require(det != 0., "Degenerate saved vector triangle")
        basis = [[(y1-y2)/det, (x2-x1)/det], [(y2-y0)/det, (x0-x2)/det], [(y0-y1)/det, (x1-x0)/det]]
        gradients = [[sum(nodal[node][component]*basis[node][axis] for node in range(3))
                      for axis in range(2)] for component in range(2)]
        for r, wr in _QUADRATURE:
            for s, ws in _QUADRATURE:
                barycentric = [1-r-(1-r)*s, r, (1-r)*s]
                x, y = [sum(barycentric[node]*points[node][axis] for node in range(3)) for axis in range(2)]
                data, weight = _math(experiment, settings, x, y), abs(det)*(1-r)*wr*ws
                for component in range(2):
                    interpolated = sum(barycentric[node]*nodal[node][component] for node in range(3))
                    l2[component] += weight*(interpolated-data["reference"][component])**2
                    h1[component] += weight*sum((gradients[component][axis]-data["reference_gradient"][component][axis])**2
                                                for axis in range(2))
    return {"component_l2": [math.sqrt(value) for value in l2],
            "component_h1": [math.sqrt(value) for value in h1],
            "l2": math.sqrt(sum(l2)), "h1": math.sqrt(sum(h1))}


def _assessed_studies(result, folder):
    """Read the retained adapter outcome; Core extensions hold model metadata."""
    detail = load_json(folder / "pde/result.json")
    _require(isinstance(detail, dict) and isinstance(detail.get("mesh_studies"), list),
             "Missing assessed studies in the retained PDE adapter artifact")
    _require(detail.get("raw_result") == "pde/result.json" and
             detail.get("solver_status") == result["solver_status"] and
             detail.get("converged") is result["converged"],
             "PDE adapter execution identity differs from Core")
    _require(_original_observations(detail.get("metrics"), result["metrics"]) and
             _original_observations(result["metrics"], detail.get("metrics")),
             "PDE adapter metrics differ from Core")
    return detail["mesh_studies"]


def _fields(experiment, settings, result, folder):
    assessed_studies = _assessed_studies(result, folder)
    root = folder / "pde"
    studies = load_json(root / "worker_result.json")["mesh_studies"]
    _require(len(studies) == len(settings["mesh"]["cell_counts"]), "Incomplete vector mesh studies")
    _require(len(assessed_studies) == len(studies), "Adapter lost vector studies")
    for raw, assessed in zip(studies, assessed_studies):
        _require(_original_observations(raw, assessed), "Adapter changed original vector observations")
    previous, closure = None, []
    progress = load_json(root / "progress.json")
    _require(progress == {"schema_version": "1", "status": "COMPLETED", "completed": [
        {"cells_per_axis": count} for count in settings["mesh"]["cell_counts"]]}, "Vector progress is incomplete")
    for count, study in zip(settings["mesh"]["cell_counts"], studies):
        _require(study["cells_per_axis"] == count and study["block_size"] == 2 and
                 study["global_nodes"] == (count+1)**2 and study["global_dofs"] == 2*study["global_nodes"] and
                 study["dirichlet_dofs"] == 2*study["dirichlet_nodes"], "Wrong vector node/scalar-DOF counts")
        files = study["files"]
        expected = {key: f"level_n{count}/{name}" for key, name in {"field": "field.xdmf", "field_data": "field.h5",
            "form_source": "forms.ufl.txt", "dofs": "dofs.json", "binding": "binding.json"}.items()}
        _require(files == expected, "Wrong vector retained filenames")
        for key, relative in files.items():
            _require(_sha(root / relative) == study["artifact_sha256"][key], "Vector retained artifact hash mismatch")
        _require(load_json(root / f"level_n{count}/observation.json") == study, "Vector observation differs from retained study")
        field, binding = load_json(root / files["dofs"]), load_json(root / files["binding"])
        _require(field["components"] == binding["components"] == COMPONENTS and field["block_size"] == 2 and
                 field["field_type"] == "vector" and binding["node_ids"] == field["node_ids"], "Vector component/binding layout mismatch")
        _require(len(binding["rhs_values"]) == len(binding["reference_values"]) == len(field["node_ids"]), "Incomplete vector input binding")
        by_id = dict(zip(field["node_ids"], field["coordinates"]))
        for index, (x, y) in enumerate(field["coordinates"]):
            data = _math(experiment, settings, x, y)
            for key, expected_values in (("rhs_values", data["rhs"]), ("reference_values", data["reference"])):
                _require(len(binding[key][index]) == 2, "Dropped vector input component")
                for actual, expected_value in zip(binding[key][index], expected_values):
                    _close(actual, expected_value, "Independent vector source/reference binding differs")
        lx, ly = settings["problem"]["domain"]["lengths"]
        for side, boundary in field["boundaries"].items():
            for node, actual_values in zip(boundary["dof_ids"], boundary["prescribed_values"]):
                expected_values = _side_value(experiment, settings, side, *by_id[node])
                for actual, expected_value in zip(actual_values, expected_values):
                    _close(actual, expected_value, "Independent directed side value differs")
            axis, constant = (0, 0.) if side == "xmin" else (0, lx) if side == "xmax" else (1, 0.) if side == "ymin" else (1, ly)
            length, integrals = (ly if axis == 0 else lx), [0., 0.]
            for coordinate, weight in _QUADRATURE:
                x, y = (constant, length*coordinate) if axis == 0 else (length*coordinate, constant)
                for component, value in enumerate(_side_value(experiment, settings, side, x, y)):
                    integrals[component] += length*weight*value
            for actual, expected_value in zip(boundary["prescribed_integral"], integrals):
                _close(actual, expected_value, "Independent vector side integral differs")
        integrated = _integrate_field(experiment, settings, field)
        for metric, key in (("l2_error", "l2"), ("h1_seminorm_error", "h1")):
            _close(study[metric], integrated[key], "Independent directed vector norm differs")
            for component in range(2):
                _close(study["components"][component][metric], integrated["component_"+key][component], "Independent component norm differs")
        for metric, key in (("l2_convergence_rate", "l2"), ("h1_seminorm_convergence_rate", "h1")):
            expected_rate = math.log(previous[key]/integrated[key], 2) if previous and previous[key]>0 and integrated[key]>0 else None
            _require(study[metric] is None if expected_rate is None else math.isclose(study[metric], expected_rate, rel_tol=1e-10, abs_tol=1e-12), "Independent vector rate differs")
            for component in range(2):
                before = previous["component_"+key][component] if previous else None
                current = integrated["component_"+key][component]
                expected_rate = math.log(before/current, 2) if before is not None and before>0 and current>0 else None
                observed = study["components"][component][metric]
                _require(observed is None if expected_rate is None else math.isclose(observed, expected_rate, rel_tol=1e-10, abs_tol=1e-12), "Independent component rate differs")
        _require(study["ksp_convergence_reason"] > 0 and study["linear_residual"]["relative"] <= settings["validation"]["max_residual_relative"], "Vector constrained residual/KSP failed")
        closure.append({"count": count, **integrated})
        previous = integrated
    return closure


def _case_diagnostics(experiment, category, result, result_sha):
    """Keep actual Core evidence separate from the frozen expected category."""
    failed = [deepcopy(row["observation"]) for row in result.get("evidence", [])
              if isinstance(row.get("observation"), dict) and row["observation"].get("status") == "FAIL"]
    recorded = {row.get("code") for row in failed}
    failed.extend({"code": row["type"], "status": "FAIL", "observed": None, "limit": row.get("threshold")}
                  for row in result["validations"] if row["status"] == "FAIL" and row["type"] not in recorded)
    return {"experiment_id": experiment, "expected_category": category,
            "expected_status": "COMPLETED_REVIEW_REQUIRED" if category == "ACCEPTED" else "REJECTED",
            "actual_status": result["status"],
            "expected_solver_status": "NOT_RUN" if category == "PREFLIGHT_REJECTED" else "COMPLETED",
            "actual_solver_status": result["solver_status"], "failed_checks": failed,
            "result_sha256": result_sha}


def _classification_failure(kind, diagnostics):
    return f"Wrong vector {kind} classification: {json.dumps(diagnostics, sort_keys=True, allow_nan=False)}"


def run(store):
    store = Path(store).resolve()
    _require(not store.exists(), "Vector acceptance store must be new; historical bytes retained")
    pin = _source_pin()
    _require(pin["core"]["core_commit"] != "unavailable" and pin["core"]["core_dirty"] is False,
             "Vector native acceptance requires committed clean source")
    accepted, rejected, refused = cases()
    store.mkdir(parents=True, exist_ok=False)
    plan = {"schema_version": "1", "created_utc": utc_now(), "source": pin,
            "accepted": accepted, "numerical_rejections": rejected, "preflight_rejections": refused,
            "qualification": "BOUNDED_MATHEMATICAL_ONLY", "release": "NOT_RELEASED"}
    save_json(store / "acceptance_plan.json", plan)
    plan_sha, reports = _sha(store / "acceptance_plan.json"), []
    lab = Lab(store)
    lab.create_study("S-vector", "Directed vector weak form and fixed reference controls",
        "Do both coupled components match independent references on every frozen mesh?",
        "P1 vector L2 and full-gradient H1 converge at orders2 and1 with correctly directed traction.",
        "Retain complete vector fields, numerical refusals and UNKNOWN qualification.")
    preserved = {}
    try:
        for category, requests in (("ACCEPTED", accepted), ("NUMERICAL_REJECTED", rejected), ("PREFLIGHT_REJECTED", refused)):
            for experiment, settings in requests.items():
                _verify_source(pin)
                _require(_sha(store / "acceptance_plan.json") == plan_sha, "Frozen vector plan drift")
                result = lab.run_pde(study_id="S-vector", experiment_id=experiment, settings=settings, backend=BACKEND)
                folder = store / "experiments" / experiment
                _verify_source(pin, result, folder)
                _require(_sha(store / "acceptance_plan.json") == plan_sha, "Frozen vector plan drift during call")
                _require(result["decision"] == "NOT_RELEASED" and result["cad_revision"] is None and
                         "parent_experiment_id" not in result, "Vector result acquired false engineering approval/CAD parent")
                unknown = {row["type"]:row["status"] for row in result["validations"]}
                _require(unknown.get("physical_validation") == unknown.get("model_qualification") == "UNKNOWN", "Vector qualification changed")
                result_sha = _sha(folder / "result.json")
                ledger = load_json(store / "ledger" / f"{experiment}.json")
                _require(ledger["experiment_id"] == experiment and ledger["result_sha256"] == result_sha
                         and ledger["thread_sha256"] == _sha(folder / "thread.json")
                         and lab.inspect_experiment(experiment) == result, "Vector immutable ledger/result/thread mismatch")
                diagnostics = _case_diagnostics(experiment, category, result, result_sha)
                native_matches = result["solver_status"] == diagnostics["expected_solver_status"]
                closure, field_verification = [], "NOT_CHECKED_NATIVE_EXECUTION"
                if native_matches and result["solver_status"] == "COMPLETED":
                    closure = _fields(experiment, settings, result, folder)
                    # Validity follows the actual Domain checks, never the plan's expected label.
                    numerical_passed = not any(row["status"] == "FAIL" for row in result["validations"])
                    actual_status = "COMPLETED_REVIEW_REQUIRED" if numerical_passed else "REJECTED"
                    _require(result["status"] == actual_status,
                             f"Vector Core status differs from Domain checks: {json.dumps(diagnostics, sort_keys=True)}")
                    _require(bool(result["metrics"]) and all(metric["valid"] is numerical_passed for metric in result["metrics"].values()),
                             "Wrong vector metric validity for actual Domain verdict")
                    if not numerical_passed:
                        _require(all(metric.get("reason") for metric in result["metrics"].values()), "Lost vector invalid-metric reasons")
                    from plugins.pde_vector.reference import model_declaration
                    declaration = model_declaration(settings)
                    _require(result["model_revision"] == canonical_hash({"settings": settings, "declaration": declaration}), "Vector declaration revision drift")
                    field_verification = "VERIFIED_COMPLETE"
                elif native_matches and category == "PREFLIGHT_REJECTED":
                    _require(not (folder / "pde/command.json").exists(), "Invalid vector input launched native execution")
                    _require(result["metrics"] == {}, "Preflight refusal acquired numerical metrics")
                    field_verification = "NOT_RUN_PREFLIGHT"
                _require(_sha(folder / "result.json") == result_sha, "Vector result drift during verification")
                reports.append({"experiment_id": experiment, "category": category, "status": result["status"],
                    "solver_status": result["solver_status"], "metrics": result["metrics"], "field_norm_closure": closure,
                    "model_revision": result["model_revision"], "artifact_manifest_sha256": canonical_hash(result["artifacts"]),
                    "result_sha256": result_sha, "field_verification": field_verification, "diagnostics": diagnostics})
                preserved.update({str(path.relative_to(store)).replace("\\", "/"): _sha(path)
                                  for path in folder.rglob("*") if path.is_file()})
                save_json(store / "acceptance_progress.json", {"status": "RUNNING", "source": pin, "cases": reports})
                _require(native_matches, _classification_failure("native execution", diagnostics))
                _require(result["status"] == diagnostics["expected_status"],
                         _classification_failure("numerical", diagnostics))
        _verify_source(pin)
        _require(_sha(store / "acceptance_plan.json") == plan_sha, "Frozen vector plan drift at completion")
        for relative, digest in preserved.items():
            _require(_sha(store / relative) == digest, "A later vector experiment overwrote previous bytes")
        report = {"schema_version": "1", "created_utc": utc_now(), "status": "PASS_BOUNDED_MATHEMATICAL",
                  "source": pin, "plan_sha256": plan_sha, "accepted": len(accepted), "numerical_rejections": len(rejected),
                  "preflight_rejections": len(refused), "native_processes": len(accepted)+len(rejected),
                  "native_meshes": sum(len(case["field_norm_closure"]) for case in reports), "cases": reports,
                  "preserved_artifact_hashes": preserved,
                  "decision": "NOT_RELEASED", "qualification": "UNKNOWN", "official_research_admission": "NOT_ADMITTED"}
        save_json(store / "acceptance.json", report)
        save_json(store / "acceptance_progress.json", {"status": "COMPLETED", "source": pin, "cases": reports})
        return report
    except BaseException as exc:
        save_json(store / "acceptance_progress.json", {"status": "FAILED_OR_PARTIAL", "source": pin, "cases": reports,
                 "error": f"{type(exc).__name__}: {exc}", "decision": "NOT_RELEASED"})
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    report = run(parser.parse_args().store)
    print(json.dumps({key: report[key] for key in ("status", "accepted", "numerical_rejections", "preflight_rejections",
                      "native_processes", "native_meshes", "decision")}, indent=2))


if __name__ == "__main__":
    main()
