"""Fresh-store declared rectangle/mixed-boundary mathematical acceptance.

This executes native FEniCSx only when explicitly invoked. Source tests and
the existence of this runner are not native/physical acceptance evidence.
"""

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from caelab import Lab
from caelab.storage import canonical_hash, load_json, save_json, source_identity, utc_now
from plugins.pde_elliptic.reference import manufactured_settings


REPOSITORY = Path(__file__).resolve().parents[1]
SOURCE_FILES = ("scripts/verify_rectangle_pde.py", "plugins/pde_elliptic/reference.py",
                "caelab/adapters/fenicsx_rectangle.py", "caelab/adapters/fenicsx_rectangle_worker.py",
                "caelab/adapters/fenicsx_worker.py", "caelab/execution_control.py")


def _source_pin():
    return {"core": source_identity(REPOSITORY),
            "files": {relative: hashlib.sha256((REPOSITORY / relative).read_bytes()).hexdigest()
                      for relative in SOURCE_FILES}}


def _verify_source(pin, result=None, root=None):
    _require(_source_pin() == pin, "Rectangle acceptance source changed; previous results remain retained")
    if result is None:
        return
    _require({key: result["provenance"].get(key) for key in pin["core"]} == pin["core"],
             "Retained result provenance differs from the pre-execution source pin")
    if root is not None and (root / "pde/command.json").exists():
        manifest = load_json(root / "pde/source_manifest.json")
        copied_sources = set()
        for item in manifest["files"].values():
            relative = item["repository_path"]
            _require(relative in pin["files"] and item["sha256"] == pin["files"][relative],
                     "Native source manifest differs from the pre-execution source pin")
            copied_sources.add(relative)
        _require(copied_sources == set(SOURCE_FILES) - {"scripts/verify_rectangle_pde.py"},
                 "Native source manifest does not contain exactly the frozen adapter/worker/domain/parser/execution helper")


def _run_fixed(lab, store, pin, study, backend, experiment, request):
    _verify_source(pin)
    try:
        result = lab.run_pde(study_id=study, experiment_id=experiment, backend=backend, settings=request)
    except BaseException:
        _verify_source(pin)
        raise
    _verify_source(pin, result, store / "experiments" / experiment)
    return result


def _require(condition, description):
    if not condition:
        raise AssertionError(description)


def _checked(lab, experiment):
    result = lab.inspect_experiment(experiment)
    _require(result["decision"] == "NOT_RELEASED" and result["cad_revision"] is None and
             "parent_experiment_id" not in result, "PDE evidence must have no CAD parent or release")
    _require({"model_qualification", "physical_validation"} <=
             set(lab.research_summary(experiment)["unknown"]), "Qualification must remain UNKNOWN")
    return result


def _manifest(root):
    return {str(path.relative_to(root)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def specification():
    return manufactured_settings()


def run(store: Path) -> dict:
    store = Path(store).resolve()
    if store.exists():
        raise ValueError("Rectangle acceptance requires a fresh store; prior attempts must be preserved")
    started = utc_now()
    pin = _source_pin()
    _require(pin["core"]["core_dirty"] is False and pin["core"]["core_commit"] != "unavailable",
             "Native acceptance requires clean committed source; development checks are separate")
    lab = Lab(store)
    study = "S-rectangle-pde"
    backend = "pde.fenicsx.rectangle"
    lab.create_study(study, "Declared rectangle and mixed scalar boundary conditions",
                     "Do changed domains and mixed outward fluxes reproduce an independently differentiated field?",
                     "P1 symbolic L2/H1 errors converge at orders2/1 with correct named boundaries and residuals.",
                     "Preserve mathematical evidence and numerical rejections without model or physical release.")
    settings = {"E-rectangle-mixed": specification(),
                "E-rectangle-reaction": manufactured_settings(reaction=3.0),
                "E-rectangle-domain": manufactured_settings(lengths=(1.5, .75), diffusion=2.0)}
    all_dirichlet = specification()
    for boundary in all_dirichlet["problem"]["boundaries"].values():
        boundary.update(type="dirichlet", value=all_dirichlet["problem"]["reference"]["solution"])
    settings["E-rectangle-all-dirichlet"] = all_dirichlet
    # Quadratic harmonic fields exercise zero-source forms without demanding
    # convergence rates from an exactly representable affine field's roundoff.
    harmonic_dirichlet = deepcopy(all_dirichlet)
    harmonic_solution = "x[0]**2-x[1]**2+x[0]+2*x[1]+1"
    harmonic_dirichlet["problem"]["weak_form"]["rhs"] = "0.0"
    harmonic_dirichlet["problem"]["reference"] = {"solution": harmonic_solution,
        "source": "Direct harmonic derivative: Laplacian(x^2-y^2+x+2*y+1)=2-2=0"}
    for boundary in harmonic_dirichlet["problem"]["boundaries"].values():
        boundary["value"] = harmonic_solution
    settings["E-rectangle-zero-source-all-dirichlet"] = harmonic_dirichlet
    harmonic_mixed = specification()
    harmonic_solution = "(x[0]-2.0)**2-(x[1]-1.0)**2+1.0"
    harmonic_mixed["problem"]["weak_form"]["rhs"] = "0.0"
    harmonic_mixed["problem"]["reference"] = {"solution": harmonic_solution,
        "source": "Direct harmonic derivative: Laplacian((x-2)^2-(y-1)^2+1)=0; xmax/ymax outward flux=0"}
    for boundary in harmonic_mixed["problem"]["boundaries"].values():
        boundary["value"] = harmonic_solution if boundary["type"] == "dirichlet" else "0.0"
    settings["E-rectangle-zero-source-zero-flux"] = harmonic_mixed
    wrong_reference = specification()
    wrong_reference["problem"]["reference"] = {"solution": "0.0",
        "source": "Intentionally wrong finite analytical field for numerical rejection"}
    wrong_flux = specification()
    for side in ("xmax", "ymax"):
        entry = wrong_flux["problem"]["boundaries"][side]
        entry["value"] = "-(" + entry["value"] + ")"
    rejected_settings = {"E-rectangle-reference-reject": wrong_reference,
                         "E-rectangle-flux-reject": wrong_flux}
    blocked_settings = {}
    for label in ("expression", "corner", "pure-neumann"):
        request = specification()
        if label == "expression":
            request["problem"]["boundaries"]["xmax"]["value"] = "__import__('os').getcwd()"
        elif label == "corner":
            request["problem"]["boundaries"]["xmin"]["value"] = "2*x[1]+2"
        else:
            for boundary in request["problem"]["boundaries"].values():
                boundary.update(type="neumann", value="0.0")
        blocked_settings["E-rectangle-invalid-" + label] = request
    # Freeze every proposed case, including negative controls, before execution.
    save_json(store / "frozen_plan.json", {"schema_version": "1", "recorded_utc": started,
        "backend": backend, "source_pin": pin, "cases": settings, "numerical_rejections": rejected_settings,
        "preflight_rejections": blocked_settings,
        "independent_reference": {"solution": "x^2*y^2+x+2*y+1",
            "laplacian": "2*(x^2+y^2)", "flux_definition": "k*grad(u).outward_normal",
            "default_domain": [2.0, 1.0],
            "default_neumann_integrals": {"xmax": 7.0 / 3.0, "ymax": 28.0 / 3.0},
            "max_boundary_integral_error": 1e-10,
            "mesh_dirichlet_union": "xmin/ymin:2*n+1; all sides:4*n"},
        "zero_source_references": {"E-rectangle-zero-source-all-dirichlet":
            "Laplacian(x^2-y^2+x+2*y+1)=0",
            "E-rectangle-zero-source-zero-flux":
            "Laplacian((x-2)^2-(y-1)^2+1)=0; outward xmax/ymax flux=0",
            "criteria": "The original rectangle L2/H1/rate/residual limits are unchanged"},
        "qualification": "UNKNOWN", "decision": "NOT_RELEASED"})
    accepted = {}
    observations = {}
    preserved = {}
    for experiment, request in settings.items():
        result = _run_fixed(lab, store, pin, study, backend, experiment, request)
        _require(result["status"] == "COMPLETED_REVIEW_REQUIRED", result["validations"])
        _require(all(item["valid"] for item in result["metrics"].values()), "All admitted responses must be valid")
        accepted[experiment] = _checked(lab, experiment)
        root = store / "experiments" / experiment
        raw = load_json(root / "pde/worker_result.json")
        observations[experiment] = raw
        declaration = lab.pde_adapters[backend].describe_model(deepcopy(request))
        _require(result["model_revision"] == canonical_hash({"settings": request, "declaration": declaration}),
                 "Geometry/boundaries must enter the common model revision")
        for row in raw["mesh_studies"]:
            count = row["cells_per_axis"]
            expected_dofs = 4 * count if experiment.endswith("all-dirichlet") else 2 * count + 1
            _require(row["dirichlet_dofs"] == expected_dofs, "Dirichlet corner union must be counted once")
            _require(row["ksp_convergence_reason"] > 0, "Actual linear solver must converge")
            if experiment in ("E-rectangle-mixed", "E-rectangle-reaction"):
                field = load_json(root / "pde" / row["files"]["dofs"])
                for side, expected in (("xmax", 7.0 / 3.0), ("ymax", 28.0 / 3.0)):
                    _require(math.isclose(field["boundaries"][side]["prescribed_integral"], expected,
                                         rel_tol=0.0, abs_tol=1e-10),
                             "Actual named outward flux quadrature differs from direct integral")
            if experiment == "E-rectangle-zero-source-zero-flux":
                field = load_json(root / "pde" / row["files"]["dofs"])
                _require(all(field["boundaries"][side]["prescribed_integral"] == 0.0
                             for side in ("xmax", "ymax")), "Zero prescribed flux must be retained as zero")
        preserved[experiment] = _manifest(root)
        save_json(store / "verification_progress.json", {"status": "RUNNING", "accepted": list(accepted),
            "recorded_utc": utc_now(), "decision": "NOT_RELEASED"})
    _require(len({result["model_revision"] for result in accepted.values()}) == len(accepted),
             "Changed reaction/domain/boundaries must produce distinct model revisions")
    # Reaction affects the discrete field even with the same exact analytical solution.
    fields = [load_json(store / "experiments" / experiment / "pde/level_n8/dofs.json")
              for experiment in ("E-rectangle-mixed", "E-rectangle-reaction")]
    _require(fields[0]["node_ids"] == fields[1]["node_ids"] and
             fields[0]["coordinates"] == fields[1]["coordinates"], "Field identities differ before comparison")
    effect = max(abs(a - b) for a, b in zip(fields[0]["values"], fields[1]["values"]))
    _require(effect > 1e-12, "Reaction change did not affect the actual discrete field")
    for experiment, request in rejected_settings.items():
        result = _run_fixed(lab, store, pin, study, backend, experiment, request)
        _require(result["status"] == "REJECTED" and result["solver_status"] == "COMPLETED" and
                 result["converged"] is True and result["metrics"] and
                 all(item["valid"] is False for item in result["metrics"].values()),
                 "Finite wrong reference/flux must retain converged fields and invalid numerical responses")
        _checked(lab, experiment)
    for experiment, request in blocked_settings.items():
        result = _run_fixed(lab, store, pin, study, backend, experiment, request)
        _require(result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN" and
                 not (store / "experiments" / experiment / "pde/command.json").exists(),
                 "Unsafe, conflicting or unsupported boundary conditions must prevent native execution")
        _checked(lab, experiment)
    for experiment, manifest in preserved.items():
        _require(_manifest(store / "experiments" / experiment) == manifest,
                 "Later experiments must preserve every earlier evidence byte")
    first = accepted["E-rectangle-mixed"]
    _verify_source(pin)
    report = {"schema_version": "1", "status": "PASS_BOUNDED_MATHEMATICAL", "decision": "NOT_RELEASED",
        "started_utc": started, "finished_utc": utc_now(), "backend": backend,
        "accepted_experiments": list(accepted), "numerical_rejections": list(rejected_settings),
        "preflight_rejections": list(blocked_settings), "reaction_coarse_field_max_difference": effect,
        "cases": {experiment: {"metrics": result["metrics"], "versions": observations[experiment]["versions"],
                                "mesh_studies": observations[experiment]["mesh_studies"]}
                  for experiment, result in accepted.items()},
        "preserved_artifact_hashes": preserved, "source_pin": pin,
        "source": {key: first["provenance"][key] for key in ("core_commit", "core_dirty", "core_source_sha256")},
        "limitations": ["Dimensionless scalar linear rectangle, P1/doubling meshes, at least one full Dirichlet side.",
            "No pure Neumann/nullspace, Robin, imported mesh, time/vector/coupled or MPI proof.",
            "No new official OpenScience/provider or same-record GUI acceptance; physical/model qualification UNKNOWN."]}
    save_json(store / "rectangle_pde_acceptance.json", report)
    save_json(store / "verification_progress.json", {"status": report["status"], "recorded_utc": utc_now(),
                                                   "decision": "NOT_RELEASED"})
    print(json.dumps({"status": report["status"], "accepted": len(accepted),
        "numerical_rejections": len(rejected_settings), "preflight_rejections": len(blocked_settings),
        "decision": "NOT_RELEASED"}))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    run(parser.parse_args().store)
