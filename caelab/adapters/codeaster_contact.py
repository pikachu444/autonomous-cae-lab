"""Bounded official SSNP121A contact behind the existing declared-model API.

The contact Domain owns reference/verdicts. This adapter owns the exact public
MED asset, pinned native syntax/execution, source identity and original tables.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re

from plugins.contact_patch import reference as domain
from . import codeaster_contact_worker as worker
from . import codeaster_elasticity as native
from ..storage import save_json


_ROOT = Path(__file__).resolve().parents[2]
_ASSET_ROOT = _ROOT / "benchmarks/input-data/codeaster"
_MESH = _ASSET_ROOT / "ssnp121a-17.4.0.mmed"
_CATALOG = _ASSET_ROOT / "ssnp121a-17.4.0.mesh.json"
_SPEC = _ROOT / "benchmarks/specifications/contact-patch-ssnp121a-v1.json"
_MESH_SHA = "825e79a01b983b14b136d4fc2490c2bc40e85ccc25ebd8ae6aa32e88dd544f91"
_CATALOG_SHA = "7398ce4349f076e225e76d1d840d60da1dfe24b57181c1ae1d7b5cfc069d8291"
_IMAGE_SHA = "f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64"
_SOURCES = {
    "domain_reference.py": Path(domain.__file__).resolve(),
    "codeaster_contact.py": Path(__file__).resolve(),
    "codeaster_contact_worker.py": Path(worker.__file__).resolve(),
    "codeaster_worker.py": Path(native.__file__).with_name("codeaster_worker.py"),
    "codeaster_runtime_adapter.py": Path(native.__file__).resolve(),
    "codeaster_execution.py": Path(native.__file__).with_name("codeaster_execution.py"),
    "execution_control.py": Path(native.__file__).resolve().parents[1] / "execution_control.py",
    "reference_specification.json": _SPEC,
    "frozen_mesh.json": _CATALOG,
    "codeaster_contact_mesh.py": Path(worker.mesh_contracts.__file__).resolve(),
    "source_parent.mmed": _MESH,
    "source_parent_mesh.json": _CATALOG,
}
_BYTES = {name: path.read_bytes() for name, path in _SOURCES.items()}
_SHA = {name: hashlib.sha256(data).hexdigest() for name, data in _BYTES.items()}
_LIMITATIONS = [
    "Official SSNP121A plane-strain frictionless two-block patch; not NAFEMS CGS1 or real fixture contact.",
    "Six original analytical sample criteria remain1%; full pressure/gap/contact/cross-solver qualification is separate.",
    "Exact native asset has313nodes/265QUAD4/92SEG2, different from the document's132SEG2.",
    "Actual body groups reverse the document figure's plate numbering; coordinate identity controls regions.",
    "SIMPSON/order4 is exact17.4 source policy; equivalence to old SIMPSON2 wording remains UNKNOWN.",
    "Projected gaps are derived from actual displaced interface coordinates, not a measured native gap channel.",
    "Native absolute Newton residual is a convergence observation, not assembled A*u-b or engineering approval.",
    "Geometry reaction uses the original controlled two iterations; pointwise contact-gap qualification remains UNKNOWN.",
    "Vendor SIF includes an MPI compatibility patch; binary/upstream-source equivalence remains UNKNOWN.",
]


def _source_bundle(mesh_variant: str | None = None) -> tuple[dict, dict, dict]:
    paths, data, hashes = dict(_SOURCES), dict(_BYTES), dict(_SHA)
    if mesh_variant is not None:
        profile = worker.selected_mesh_contract(mesh_variant)
        additions = {
            "frozen_mesh.json": (_ASSET_ROOT / "ssnp121a-17.4.0.uniform_quad4_2x.mesh.json", profile["catalog_sha256"]),
            "selected_source.mmed": (_ASSET_ROOT / "ssnp121a-17.4.0.uniform_quad4_2x.mmed", profile["mesh_sha256"]),
            "mesh_generation_recipe.json": (_ASSET_ROOT / "ssnp121a-17.4.0.uniform_quad4_2x.generation.json", profile["recipe_sha256"]),
            worker.mesh_contracts.PROFILE_NAME: (_ASSET_ROOT / worker.mesh_contracts.PROFILE_NAME, worker.REFINED_PROFILE_SHA256),
        }
        for name, (path, digest) in additions.items():
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != digest or path.is_symlink():
                raise RuntimeError(f"Sealed refined contact source changed: {name}")
            paths[name], data[name], hashes[name] = path, content, digest
        if hashes["codeaster_contact_mesh.py"] != profile["generator_sha256"]:
            raise RuntimeError("Captured mesh generator differs from the actual sealed preparation source")
    return paths, data, hashes


def _assert_sources(output: Path, mesh_variant: str | None = None) -> None:
    paths, _, hashes = _source_bundle(mesh_variant)
    for name, path in paths.items():
        if path.is_symlink() or native._sha256(path) != hashes[name] or native._sha256(output / name) != hashes[name]:
            raise RuntimeError(f"Contact source changed: {name}; captured evidence remains preserved")
    if native._sha256(_MESH) != _MESH_SHA or native._sha256(_CATALOG) != _CATALOG_SHA:
        raise RuntimeError("Original contact mesh/catalogue drifted; no substitute input is admitted")


def parse_convergence_log(text: str) -> dict:
    """Require original exact final absolute residual, retaining all native rows.

    The contact geometry iterations can repeat a single instant. They do not
    imply extra requested load steps or an invented relative-residual verdict.
    """
    number = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?"
    instants, final, rows = [], [], []
    for index, line in enumerate(text.splitlines(), 1):
        instant = re.search(r"Instant de calcul\s*:\s*(" + number + r")", line)
        if instant:
            value = float(instant[1].replace("D", "E").replace("d", "e"))
            if not math.isfinite(value) or value != 1.0:
                raise ValueError("Contact native instant differs from the single requested final1s")
            instants.append({"value": value, "source_line": index})
        residual = re.search(r"Le résidu de type <RESI_GLOB_MAXI> vaut\s*(" + number + r")", line)
        if residual:
            value = float(residual[1].replace("D", "E").replace("d", "e"))
            if not math.isfinite(value) or value < 0:
                raise ValueError("Invalid actual absolute contact residual")
            final.append({"value": value, "source_line": index, "raw_line": line})
        if "|" in line and ("RESI_GLOB" in line or re.match(r"\s*\|\s*\d+", line)):
            rows.append({"source_line": index, "raw_line": line})
    if not instants or not final or not rows:
        raise ValueError("Missing original native contact instant/residual/iteration observations")
    limit = 2e-8
    observed = final[-1]["value"]
    return {"status": "PASS" if observed <= limit else "FAIL", "final_absolute_residual": observed,
            "absolute_residual_limit": limit, "instants": instants, "final_observations": final,
            "iteration_rows": rows, "relative_or_assembled_residual": "NOT_MEASURED_OR_CLAIMED",
            "method": "Original17.4 RESI_GLOB_MAXI full-precision native summary"}


def _numerical_observation(observation: dict) -> dict:
    """Keep native identity/extraction metadata in the original artifact.

    The pure Domain receives only its explicit physical observations. Project
    fields, never change or reconstruct any returned numerical response.
    """
    return {
        "samples": {name: {key: observation["samples"][name][key]
                           for key in ("normal_traction_pa", "vertical_displacement_m")}
                    for name in ("A", "B", "N14")},
        "boundary_reactions_n_per_m": deepcopy(observation["boundary_reactions_n_per_m"]),
        "slave_contact": {key: deepcopy(observation["slave_contact"][key])
                          for key in ("node_ids", "normal_traction_pa")},
        "fields": deepcopy(observation["fields"]),
        "projected_gaps_m": deepcopy(observation.get("projected_gaps_m")),
    }


class CodeAsterContactPatchAdapter:
    backend = "structural.code_aster.contact_patch"
    version = "1.1"
    domain = "contact_patch"
    physics_domain = "structural"
    analysis_type = "nonlinear_static"
    default_metrics = [
        "A_normal_traction", "A_vertical_displacement", "B_normal_traction", "B_vertical_displacement",
        "N14_normal_traction", "N14_vertical_displacement", "max_sample_pressure_relative_error",
        "max_sample_displacement_relative_error", "top_reaction_y", "bottom_reaction_y",
        "boundary_force_balance_relative", "all_nodes_force_balance_relative",
        "slave_normal_traction_min", "slave_normal_traction_max",
        "derived_projected_gap_min", "derived_projected_gap_max", "derived_projected_gap_max_absolute",
    ]

    def describe_model(self, settings: dict) -> dict:
        declaration = deepcopy(domain.model_declaration(settings))
        selected = worker.mesh_contracts.variant(settings)
        if selected is not None:
            profile = worker.selected_mesh_contract(selected)
            declaration["mesh"].update(asset_sha256=profile["mesh_sha256"], catalog_sha256=profile["catalog_sha256"],
                parent_asset_sha256=profile["parent"]["mesh_sha256"], generation_recipe_sha256=profile["recipe_sha256"],
                generation_source_sha256=profile["generator_sha256"], mesh_profile_sha256=worker.REFINED_PROFILE_SHA256)
        model_keys = ("geometry", "materials", "mesh", "sections", "interfaces", "contact", "coordinate_systems")
        model = {name: declaration.pop(name) for name in model_keys if name in declaration}
        return {"model": model, **declaration}

    def solve(self, output: Path, settings: dict) -> dict:
        output = Path(output)
        if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
            raise ValueError("Contact output must be new or empty; original evidence cannot be overwritten")
        output.mkdir(parents=True, exist_ok=True)
        checked, admission_error = None, None
        try:
            checked = domain.validate_settings(settings)
        except ValueError as exc:
            admission_error = exc
        selected = worker.mesh_contracts.variant(checked) if checked is not None else None
        profile = worker.selected_mesh_contract(selected)
        _, captured_bytes, captured_hashes = _source_bundle(selected)
        for name, data in captured_bytes.items():
            (output / name).write_bytes(data)
        _assert_sources(output, selected)
        limitations = list(_LIMITATIONS)
        if selected is not None:
            limitations[2] = "Selected generated uniform2 asset has1154nodes/1060QUAD4/184SEG2; original313 prefix and all named groups are preserved."
            limitations.append("One uniform2 subdivision is a mesh-sensitivity comparison; mesh convergence and original vendor-mesh replication are not claimed.")
        provenance = {"adapter": self.backend, "adapter_version": self.version,
            "captured_source_sha256": captured_hashes, "domain_plugin": {"module": domain.__name__,
            "version": domain.__version__, "source_artifact": "simulation/domain_reference.py",
            "source_sha256": _SHA["domain_reference.py"]},
            "reference": "Code_Aster SSNP121A/17.4.0/50ebc13c70ee9df62faf93ddcb746a3757b3042a",
            "mesh_sha256": profile["mesh_sha256"], "mesh_catalog_sha256": profile["catalog_sha256"],
            "assumptions": limitations}
        if selected is not None:
            provenance.update(mesh_variant=selected, source_parent_mesh=profile["parent"],
                generation_recipe_sha256=profile["recipe_sha256"], generation_source_sha256=profile["generator_sha256"],
                mesh_profile_sha256=worker.REFINED_PROFILE_SHA256, mesh_metadata_byte_repeatability="NOT_CLAIMED")
        if admission_error is not None:
            outcome = {"status": "REJECTED", "solver_status": "NOT_RUN", "converged": None,
                "checks": [{"code": "contact_preflight", "status": "FAIL", "observed": str(admission_error)}],
                "metrics": {}, "pending_validations": list(domain._PENDING),
                "provenance": provenance, "raw_result": "simulation/analysis_raw.json"}
            save_json(output / "analysis_raw.json", outcome)
            return outcome
        save_json(output / "input.json", checked)
        save_json(output / "analytical_reference.json", domain.analytical_reference(checked))
        save_json(output / "model_declaration.json", self.describe_model(checked))
        budgets = native.process_budgets()
        image, image_sha, runtime, _, _ = native._image_identity(output)
        if image_sha != _IMAGE_SHA:
            raise RuntimeError("Initial contact qualification requires the already protected17.4 SIF")
        level = output / "level_0"
        level.mkdir(exist_ok=False)
        selected_mesh = (_MESH if selected is None else _ASSET_ROOT / "ssnp121a-17.4.0.uniform_quad4_2x.mmed")
        (level / "mesh.mmed").write_bytes(selected_mesh.read_bytes())
        save_json(level / "input.json", {"settings": checked, "mesh_sha256": profile["mesh_sha256"],
            "mesh_inspection_sha256": profile["catalog_sha256"]})
        input_sha = native._sha256(level / "input.json")
        (level / "model.comm").write_text("import sys\nsys.path.insert(0, '/work')\n"
            "from codeaster_contact_worker import solve_level\n"
            "solve_level('/work/level_0/input.json')\n", encoding="utf-8")
        (level / "model.export").write_text(
            f"P actions make_etude\nP memory_limit {budgets['solver_memory_mb']}\n"
            f"P time_limit {budgets['solver_time_seconds']}\nP mpi_nbcpu 1\nP ncpus 1\n"
            "F comm /work/level_0/model.comm D 1\nF mmed /work/level_0/mesh.mmed D 20\n"
            "F rmed /work/level_0/results.med R 80\nF mess /work/level_0/aster.mess R 6\n"
            "F resu /work/level_0/aster.resu R 8\n", encoding="utf-8")
        preferences = output / "preferences"
        scratch_root = output / "scratch"
        preferences.mkdir(exist_ok=False)
        scratch_root.mkdir(exist_ok=False)
        scratch = scratch_root / "level_0"
        scratch.mkdir(exist_ok=False)
        save_json(level / "scratch.json", {"path": "simulation/scratch/level_0",
            "retention_status": "PRESERVED_UNTIL_VALID_EXTRACTION"})
        _assert_sources(output, selected)
        if (native._sha256(image) != image_sha or native._sha256(level / "mesh.mmed") != profile["mesh_sha256"] or
                native._sha256(level / "input.json") != input_sha):
            raise RuntimeError("Contact runtime/input drift before native execution")
        command = [runtime, "exec", "--cleanenv", "--containall", "--no-home", "--env", "OMP_NUM_THREADS=1",
            "--bind", str(output.resolve()) + ":/work:rw", "--bind", str(preferences.resolve()) + ":" + str(Path.home()) + ":rw",
            "--bind", str(scratch.resolve()) + ":/tmp:rw", "--pwd", "/work", str(image),
            "/bin/bash", "--noprofile", "--norc", "-c", native.CONTAINER_SCRIPT,
            "caelab-codeaster-contact", "/work/level_0/model.export"]
        native._process(command, level, "solver", timeout=budgets["subprocess_timeout_seconds"])
        raw = json.loads((level / "worker_result.json").read_text(encoding="utf-8"))
        if (raw.get("input_sha256") != input_sha or raw.get("mesh_input_sha256") != profile["mesh_sha256"] or
                raw.get("mesh_variant") != selected or
                raw.get("solver_status") != "COMPLETED" or raw.get("converged") is not True or
                not isinstance(raw.get("versions"), dict) or not isinstance(raw.get("code_aster_runtime"), dict)):
            raise ValueError("Native contact result identity/status/runtime does not match the original request")
        if not (level / "results.med").is_file() or not (level / "results.med").stat().st_size:
            raise ValueError("Complete native contact MED field artifact is missing")
        observation = (worker.parse_contact_tables(raw) if selected is None else
                       worker.parse_contact_tables(raw, mesh_variant=selected))
        save_json(level / "parsed_contact.json", observation)
        convergence = parse_convergence_log((level / "aster.mess").read_text(encoding="utf-8", errors="replace"))
        save_json(level / "nonlinear_convergence.json", convergence)
        numerical_observation = _numerical_observation(observation)
        save_json(level / "domain_contact_observation.json", numerical_observation)
        assessed = domain.assess(checked, numerical_observation)
        checks = [{"code": "native_contact_mesh_identity", "status": "PASS",
                   "observed": raw["native_mesh_checks"], "limit": ("Exact public313node/265QUAD4/92SEG2 asset" if selected is None else
                       "Exact sealed uniform2 1154node/1060QUAD4/184SEG2 asset and original313 parent identity")},
                  {"code": "native_contact_absolute_convergence", "status": convergence["status"],
                   "observed": convergence["final_absolute_residual"], "limit": convergence["absolute_residual_limit"]},
                  *assessed["checks"]]
        metrics = deepcopy(assessed["metrics"])
        completed = all(item["status"] == "PASS" for item in checks)
        if not completed:
            for metric in metrics.values():
                metric.update(valid=False, reason="Contact native/reference gate failed; original observation retained")
        _assert_sources(output, selected)
        if (native._sha256(image) != image_sha or native._sha256(level / "mesh.mmed") != profile["mesh_sha256"] or
                native._sha256(level / "input.json") != input_sha):
            raise RuntimeError("Contact runtime/input drift after extraction; original artifacts remain")
        provenance.update(code_aster_runtime=raw["code_aster_runtime"], versions=raw["versions"],
            process_budgets=budgets, image_sha256=image_sha, oci_manifest_sha256=native.OCI_MANIFEST_SHA256,
            native_fields=["simulation/level_0/results.med"], native_input="simulation/level_0/mesh.mmed",
            container_isolation={"cleanenv": True, "containall": True, "no_home": True,
                "mpi_ranks": 1, "omp_threads": 1},
            nonlinear_policy=raw.get("native_policy"), measured_assembled_residual=None)
        native._cleanup_scratch(output, scratch)
        save_json(level / "scratch.json", {"path": "simulation/scratch/level_0",
            "retention_status": "REMOVED_AFTER_VALID_EXTRACTION", "native_evidence": "simulation/level_0"})
        outcome = {"status": "COMPLETED" if completed else "REJECTED", "solver_status": "COMPLETED",
            "converged": convergence["status"] == "PASS", "checks": checks, "metrics": metrics,
            "pending_validations": assessed["pending_validations"], "provenance": provenance,
            "raw_result": "simulation/analysis_raw.json", "reference": assessed["reference"],
            "contact_observation": observation, "nonlinear_convergence": convergence,
            "limitations": [*assessed["limitations"], *limitations]}
        save_json(output / "analysis_raw.json", outcome)
        return outcome
