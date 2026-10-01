"""Three fixed structural families on the shared HEXA20 catalogue, Code_Aster17.4.

Domain definitions/references and the admitted runtime are reused. This module
owns native compilation, containment, complete extraction and source identity.
It does not resume the deferred LE10 implementation or qualify physical strength.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
from typing import Any

from .codeaster_elasticity import (CodeAsterElasticityAdapter, CONTAINER_SCRIPT,
    OCI_MANIFEST_SHA256, PROCESS_TIMEOUT, _cleanup_scratch, _image_identity, _process, _sha256)
from .structural_family_codeaster_worker import gmsh_import_contract, parse_field_tables
from ..storage import save_json

_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("structural_family_codeaster_worker.py")
_DOMAIN = _ROOT / "plugins/structural_families/reference.py"
_SPEC = _ROOT / "benchmarks/specifications/structural-families-v1.json"
_MESH = Path(__file__).with_name("structural_family_mesh.py")
_HELPER = Path(__file__).with_name("codeaster_worker.py")
_RUNTIME = Path(__file__).with_name("codeaster_elasticity.py")
_SOURCE_PATHS = {"adapter_source.py": Path(__file__).resolve(), "structural_family_codeaster_worker.py": WORKER,
                 "domain_reference.py": _DOMAIN, "structural-families-v1.json": _SPEC,
                 "structural_family_mesh.py": _MESH, "codeaster_worker.py": _HELPER,
                 "runtime_helper.py": _RUNTIME}
_PENDING = ["static_strength", "material_qualification", "physical_validation", "fatigue_durability", "model_qualification", "original_midas_replication"]
_LIMITATIONS = [
    "The three fixed solid derivatives do not establish original MIDAS reproduction, torsion or independent shell rotations.",
    "HEXA20 RIGI=FPG27: actual native integration-point stress remains distinct from surface/averaged nodal stress.",
    "Actual Gauss coordinates and complete shared node/cell/load identities are required; POINT number alone is insufficient.",
    "Native REAC_NODA resultants include only each restrained DOF once; all raw reaction components are retained.",
    "Sampled isoparametric Jacobian checks are bounded and do not prove continuum positivity everywhere.",
    "The pinned solver-only vendor image includes an MPI compatibility patch; assembled residual and energy remain UNKNOWN.",
]


def _domain():
    return importlib.import_module("plugins.structural_families.reference")


def _mesh_module():
    return importlib.import_module("caelab.adapters.structural_family_mesh")


def _no_links(path: Path) -> None:
    """Reject existing link ancestors before any creation/read of owned evidence."""
    for ancestor in [*reversed(path.absolute().parents), path.absolute()]:
        if ancestor.is_symlink():
            raise ValueError("Linked native output/source paths are not admitted")


def _snapshot(output: Path) -> dict:
    manifest = {}
    for name, source in _SOURCE_PATHS.items():
        _no_links(source)
        data = source.read_bytes()
        (output / name).write_bytes(data)
        manifest[name] = {"path": str(source.resolve()), "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
    save_json(output / "source_identity.json", manifest)
    _assert_sources(output, manifest)
    return manifest


def _assert_sources(output: Path, manifest: dict) -> None:
    for name, entry in manifest.items():
        source = Path(entry["path"])
        _no_links(source)
        _no_links(output / name)
        if not source.is_file() or _sha256(source) != entry["sha256"] or _sha256(output / name) != entry["sha256"]:
            raise RuntimeError("Structural-family source changed; native evidence is preserved")


def _admitted_runtime(output: Path) -> tuple[tuple, dict]:
    # cleanenv controls the child environment, but Singularity's own inherited
    # option namespaces can still add mounts/options. Refuse them before launch.
    if any(name.upper().startswith(("SINGULARITY_", "SINGULARITYENV_", "APPTAINER_", "APPTAINERENV_")) for name in os.environ):
        raise RuntimeError("Inherited container overrides are not admitted for the fixed native runtime")
    locations = _image_identity(output)
    identity = CodeAsterElasticityAdapter().input_runtime_identity()
    return locations, identity


def _assert_runtime(identity: dict) -> None:
    if CodeAsterElasticityAdapter().input_runtime_identity() != identity:
        raise RuntimeError("Code_Aster native image/executable/runtime identity changed; evidence preserved")


def _material(declaration: dict) -> dict:
    materials = declaration["model"]["materials"]
    if not isinstance(materials, list) or len(materials) != 1:
        raise ValueError("Exactly one trusted linear material declaration is required")
    young = materials[0]["youngs_modulus"]
    poisson = materials[0]["poisson_ratio"]
    if young.get("unit") != "MPa" or poisson.get("unit") != "1":
        raise ValueError("Trusted family material units must be MPa and dimensionless")
    return {"youngs_modulus_mpa": young["value"], "poisson_ratio": poisson["value"]}


def _checked_worker(level: Path, expected: dict, input_sha: str, sources: dict) -> tuple[dict, dict]:
    try:
        raw = json.loads((level / "worker_result.json").read_text(encoding="utf-8"))
        json.dumps(raw, allow_nan=False)
        versions, runtime, guard = raw.get("versions"), raw.get("code_aster_runtime"), raw.get("native_mesh_checks")
        if not isinstance(versions, dict) or versions.get("code_aster") != "17.4.0" or any(not isinstance(versions.get(name), str) or not versions[name] for name in ("python", "numpy")) or not isinstance(runtime, dict) or runtime.get("version") != "17.4.0":
            raise ValueError("Actual native runtime version is missing or drifted")
        if raw.get("input_sha256") != input_sha or _sha256(level / "input.json") != input_sha or raw.get("mesh_input_sha256") != _sha256(level / "mesh.msh"):
            raise ValueError("Native input/source mesh identity drifted")
        config = json.loads((level / "input.json").read_text(encoding="utf-8"))
        declared_sources = {name: sources[name]["sha256"] for name in (WORKER.name, _HELPER.name, _MESH.name)}
        if config.get("expected_mesh_sha256") != _sha256(level / "expected_mesh.json") or config.get("mesh_sha256") != _sha256(level / "mesh.msh") or config.get("source_hashes") != declared_sources:
            raise ValueError("Current catalogue/source manifest differs from original worker input")
        if json.loads((level / "expected_mesh.json").read_text(encoding="utf-8")) != expected:
            raise ValueError("Current expected mesh differs from the host checked catalogue")
        if not isinstance(guard, dict) or guard.get("status") != "PASS" or guard.get("support_and_load_groups_verified") is not True or guard.get("expected_mesh_sha256") != _sha256(level / "expected_mesh.json") or guard.get("checked_msh_sha256") != _sha256(level / "mesh.msh") or guard.get("input_sha256") != input_sha or guard.get("node_count") != len(expected["nodes"]) or guard.get("volume_element_count") != len(expected["elements"]):
            raise ValueError("Native pre-MECA identity/completeness gate is missing or drifted")
        if json.loads((level / "native_mesh_checks.json").read_text(encoding="utf-8")) != guard:
            raise ValueError("Native guard artifact differs from actual raw guard")
        # Recompute import identity from the current source before normalizing
        # any field. Recorded PASS alone does not replace exact source checks.
        contract = gmsh_import_contract(expected, level / "mesh.msh")
        if contract != expected["native_import"]:
            raise ValueError("Current native import contract differs from checked source")
        for name, entry in sources.items():
            if _sha256(level.parent / name) != entry["sha256"]:
                raise ValueError("Copied native source changed during execution")
        if not (level / "results.med").is_file() or (level / "results.med").stat().st_size == 0:
            raise ValueError("Native MED displacement/stress/reaction fields are missing")
        record = parse_field_tables(raw, expected)
        record["native_fields_artifact"] = f"simulation/{level.name}/results.med"
        return raw, record
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise RuntimeError(f"Incomplete/malformed native family fields at {level.name}: {exc}") from exc


class StructuralFamilyCodeAsterAdapter:
    backend = "structural.families.code_aster"
    domain = "structural_families"
    physics_domain = "structural"
    analysis_type = "linear_static"
    version = "1"
    default_metrics = ["primary_response"]
    input_source_files = tuple(_SOURCE_PATHS.values())

    def describe_model(self, settings: dict) -> dict:
        return _domain().model_declaration(deepcopy(settings))

    def solve(self, output: Path, settings: dict) -> dict:
        output = Path(output)
        _no_links(output)
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise ValueError("Analysis output must be new/empty; old evidence cannot be overwritten")
        output.mkdir(parents=True, exist_ok=True)
        sources = _snapshot(output)
        provenance = {"adapter": self.backend, "adapter_version": self.version,
                      "source_identity": sources, "oci_manifest_sha256": OCI_MANIFEST_SHA256,
                      "domain_plugin": {"module": "plugins.structural_families.reference", "source_sha256": sources["domain_reference.py"]["sha256"], "source_artifact": "simulation/domain_reference.py"},
                      "definition_sha256": sources["structural-families-v1.json"]["sha256"],
                      "distribution": "Pinned solver-only vendor OCI with MPI rank compatibility patch",
                      "assumptions": list(_LIMITATIONS)}
        checks = []

        def reject(code: str, observed: Any) -> dict:
            result = {"status": "REJECTED", "solver_status": "NOT_RUN", "converged": None,
                      "checks": [*checks, {"code": code, "status": "FAIL", "observed": observed}],
                      "metrics": {}, "provenance": provenance, "pending_validations": list(_PENDING),
                      "raw_result": "simulation/analysis_raw.json", "limitations": list(_LIMITATIONS)}
            _assert_sources(output, sources)
            save_json(output / "analysis_raw.json", result)
            return result

        try:
            normalized = _domain().validate_settings(deepcopy(settings))
            declaration = self.describe_model(normalized)
            material = _material(declaration)
        except (ValueError, TypeError, KeyError) as exc:
            return reject("structural_family_preflight", str(exc))
        save_json(output / "input.json", normalized)
        save_json(output / "model_declaration.json", declaration)
        meshes = []
        # Compile and preflight every requested catalogue before any external
        # runtime/version command or solver process can be invoked.
        for index, cells in enumerate(normalized["mesh_cells"]):
            _assert_sources(output, sources)
            level = output / f"level_{index}"
            level.mkdir(exist_ok=False)
            try:
                catalogue = _mesh_module().build_mesh(normalized, cells)
                checks_result = _mesh_module().check_mesh(catalogue, normalized)
                save_json(level / "mesh_catalogue.json", catalogue)
                save_json(level / "mesh_checks.json", checks_result)
                save_json(level / "nodal_loads.json", catalogue["nodal_loads_n"])
                native_metadata = _mesh_module().write_gmsh(catalogue, level / "mesh.msh")
                save_json(level / "gmsh_metadata.json", native_metadata)
                expected = deepcopy(catalogue)
                expected["native_import"] = gmsh_import_contract(catalogue, level / "mesh.msh")
                save_json(level / "expected_mesh.json", expected)
            except (ValueError, TypeError, KeyError) as exc:
                return reject(f"mesh_preflight_{index}", str(exc))
            checks.append({"code": f"mesh_preflight_{index}", "status": "PASS", "observed": checks_result,
                           "evidence_artifact": f"simulation/{level.name}/mesh_checks.json"})
            meshes.append((level, expected))
        _assert_sources(output, sources)
        try:
            (image, image_sha, runtime, gmsh, _prlimit), runtime_identity = _admitted_runtime(output)
        except (RuntimeError, ValueError) as exc:
            (output / "runtime_preflight.stderr.log").write_text(str(exc) + "\n", encoding="utf-8")
            raise
        provenance["runtime_identity"] = runtime_identity
        provenance["image_sha256"] = image_sha
        provenance["versions"] = {"gmsh": _process([gmsh, "-version"], output, "gmsh_version", timeout=10),
                                  "singularity": _process([runtime, "--version"], output, "container_version", timeout=10)}
        if not all(provenance["versions"].values()):
            raise RuntimeError("The admitted runtime did not return actual versions")
        preferences, scratch_root = output / "preferences", output / "scratch"
        preferences.mkdir(exist_ok=False)
        scratch_root.mkdir(exist_ok=False)
        records, raw_results = [], []
        for level, expected in meshes:
            _assert_sources(output, sources)
            _assert_runtime(runtime_identity)
            native_sources = {name: sources[name]["sha256"] for name in (WORKER.name, _HELPER.name, _MESH.name)}
            save_json(level / "input.json", {"settings": normalized, "material": material,
                    "mesh_sha256": _sha256(level / "mesh.msh"), "expected_mesh_sha256": _sha256(level / "expected_mesh.json"),
                    "source_hashes": native_sources})
            input_sha = _sha256(level / "input.json")
            (level / "model.comm").write_text("import sys\nsys.path.insert(0, '/work')\nfrom structural_family_codeaster_worker import solve_level\n"
                                            f"solve_level('/work/{level.name}/input.json')\n", encoding="utf-8")
            (level / "model.export").write_text("P actions make_etude\nP memory_limit 1024\nP time_limit 120\nP mpi_nbcpu 1\nP ncpus 1\n"
                f"F comm /work/{level.name}/model.comm D 1\nF mmed /work/{level.name}/mesh.msh D 20\n"
                f"F rmed /work/{level.name}/results.med R 80\nF mess /work/{level.name}/aster.mess R 6\n"
                f"F resu /work/{level.name}/aster.resu R 8\n", encoding="utf-8")
            scratch = scratch_root / level.name
            scratch.mkdir(exist_ok=False)
            scratch_record = {"path": f"simulation/scratch/{level.name}", "retention_status": "PRESERVED_UNTIL_VALID_EXTRACTION"}
            save_json(level / "scratch.json", scratch_record)
            command = [runtime, "exec", "--cleanenv", "--containall", "--no-home", "--env", "OMP_NUM_THREADS=2",
                       "--bind", str(output.resolve()) + ":/work:rw", "--bind", str(preferences.resolve()) + ":" + str(Path.home()) + ":rw",
                       "--bind", str(scratch.resolve()) + ":/tmp:rw", "--pwd", "/work", str(image),
                       "/bin/bash", "--noprofile", "--norc", "-c", CONTAINER_SCRIPT, "caelab-codeaster", f"/work/{level.name}/model.export"]
            _process(command, level, "solver")
            raw, record = _checked_worker(level, expected, input_sha, sources)
            save_json(level / "parsed_fields.json", record)
            _assert_sources(output, sources)
            _assert_runtime(runtime_identity)
            _cleanup_scratch(output, scratch)
            scratch_record["retention_status"] = "REMOVED_AFTER_VALID_EXTRACTION"
            save_json(level / "scratch.json", scratch_record)
            records.append(record)
            raw_results.append(raw)
        save_json(output / "mesh_records.json", records)
        if any(raw["versions"] != raw_results[0]["versions"] or raw["code_aster_runtime"] != raw_results[0]["code_aster_runtime"] for raw in raw_results[1:]):
            raise RuntimeError("Actual Code_Aster runtime drifted between mesh levels")
        assessment = _domain().assess(normalized, records)
        _assert_sources(output, sources)
        _assert_runtime(runtime_identity)
        checks.extend({**row, "evidence_artifact": "simulation/analysis_raw.json"} for row in assessment["checks"])
        provenance["versions"].update(raw_results[0]["versions"])
        provenance.update({"code_aster_runtime": raw_results[0]["code_aster_runtime"], "stress_quadrature": "HEXA20 RIGI=FPG27",
            "stress_coordinates": "Actual native CREA_TABLE/COOR_ELGA columns verified against every physical shared quadrature point",
            "point_order": "Aster xi outer/eta middle/zeta inner; normalized to canonical xi-fast via physical coordinate checks",
            "reaction_method": "Actual REAC_NODA; per-restrained-DOF deduplicated sum and global-origin moment, never applied FORCE_NODALE",
            "native_fields": [f"simulation/{level.name}/results.med" for level, _ in meshes],
            "mesh_response": assessment["mesh_response"], "container_isolation": {"cleanenv": True, "containall": True, "no_home": True,
            "home_content": "Fresh experiment-local preferences", "tmp_content": "Fresh per-level disk scratch", "scratch_retention": "Preserve on failure; remove only after valid extraction"},
            "process_budgets": {"solver_memory_mb": 1024, "solver_time_seconds": 120, "subprocess_timeout_seconds": PROCESS_TIMEOUT},
            "solver": {"linear_method": "MUMPS", "measured_linear_residual": None, "residual_status": "UNKNOWN: assembled A/u/b not exported"}})
        result = {"status": "COMPLETED" if all(row["status"] == "PASS" for row in checks) else "REJECTED",
                  "solver_status": "COMPLETED", "converged": True, "checks": checks, "metrics": assessment["metrics"],
                  "provenance": provenance, "pending_validations": assessment["pending_validations"],
                  "raw_result": "simulation/analysis_raw.json", "reference": assessment["reference"], "mesh_studies": assessment["mesh_studies"],
                  "mesh_records": records, "limitations": [*assessment["limitations"], *_LIMITATIONS]}
        save_json(output / "analysis_raw.json", result)
        return result
