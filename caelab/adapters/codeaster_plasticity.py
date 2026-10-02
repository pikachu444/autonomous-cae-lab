"""Real small-strain Code_Aster J2 loading/unloading through declared-model Core.

The pure domain plugin supplies an independent return map. All mesh admission,
Gmsh geometry and native import checks reuse the exercised elasticity adapter.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import re

from plugins.elasticity import plasticity_reference as domain
from . import codeaster_elasticity as elastic
from . import codeaster_worker as mesh_worker
from . import codeaster_plasticity_worker as worker
from ..storage import save_json


_SOURCES = {
    "domain_reference.py": Path(domain.__file__).resolve(),
    "mesh_runtime_adapter.py": Path(elastic.__file__).resolve(),
    "codeaster_worker.py": Path(mesh_worker.__file__).resolve(),
    "codeaster_plasticity_worker.py": Path(worker.__file__).resolve(),
    "plasticity_adapter.py": Path(__file__).resolve(),
    "codeaster_execution.py": Path(__file__).with_name("codeaster_execution.py"),
}
_SOURCE_BYTES = {name: path.read_bytes() for name, path in _SOURCES.items()}
_SOURCE_SHA = {name: hashlib.sha256(data).hexdigest() for name, data in _SOURCE_BYTES.items()}
_PENDING = ["static_strength", "material_qualification", "physical_validation", "fatigue_durability", "model_qualification"]
_LIMITATIONS = [
    "Small-strain homogeneous J2 isotropic-hardening material benchmark, not a full Phase 5 qualification.",
    "Contact, geometric nonlinearity, reverse plasticity, finite strain, fatigue and physical material calibration remain unverified.",
    "Two meshes are an affine patch agreement check; no mesh convergence order is inferred.",
    "Plastic work/dissipation are derived from native stress and equivalent-plastic history, not a native global energy-balance field.",
    "No assembled linear matrix/vector residual is exported; nonlinear native convergence and independent reference errors are distinct.",
    "The pinned solver-only vendor image includes an MPI rank compatibility patch.",
]


def _assert_sources(output: Path) -> None:
    for name, source in _SOURCES.items():
        if (not source.is_file() or elastic._sha256(source) != _SOURCE_SHA[name] or
                elastic._sha256(output / name) != _SOURCE_SHA[name]):
            raise RuntimeError(f"Captured plasticity/backend source drifted: {name}; old evidence remains preserved")


def parse_convergence_log(text: str, times_s: list[float]) -> dict:
    """Require the actual pinned .mess increment/iteration residual histories.

    MESURE/STAT is timing/count statistics, not a residual field. Native printed
    nonlinear residuals are kept under their own names; they are not A*u-b.
    """
    increments, current, columns = [], None, None
    number = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?"
    for line_number, line in enumerate(text.splitlines(), 1):
        instant = re.search(r"Instant de calcul\s*:\s*(" + number + r")", line)
        if instant:
            current = {"time_s": float(instant[1].replace("D", "E").replace("d", "e")),
                       "iterations": [], "final_residuals": {}}
            increments.append(current)
            columns = None
        final = re.search(r"Le résidu de type <(RESI_GLOB_RELA|RESI_GLOB_MAXI)> vaut\s*(" + number + r")", line)
        if final and current is not None:
            value = float(final[2].replace("D", "E").replace("d", "e"))
            if not math.isfinite(value) or value < 0 or final[1] in current["final_residuals"]:
                raise ValueError("Missing/duplicate/nonfinite native final residual summary")
            current["final_residuals"][final[1]] = {"value": value, "source_line": line_number, "raw_line": line}
        if "|" not in line or current is None:
            continue
        fields = [field.strip() for field in line.strip().strip("|").split("|")]
        if "RESI_GLOB_RELA" in fields and "RESI_GLOB_MAXI" in fields:
            columns = (fields.index("RESI_GLOB_RELA"), fields.index("RESI_GLOB_MAXI"))
            continue
        iteration = re.fullmatch(r"(\d+)\s*(X?)", fields[0]) if fields else None
        if iteration is None:
            continue
        if columns is None or max(columns) >= len(fields):
            raise ValueError("Native iteration row has no verified relative/absolute residual header")
        residuals, flags = [], {"iteration": bool(iteration[2])}
        for column in columns:
            token = re.fullmatch(r"(" + number + r")\s*(X?)", fields[column])
            if token is None:
                raise ValueError("Missing/nonfinite native nonlinear residual observation")
            value = float(token[1].replace("D", "E").replace("d", "e"))
            if not math.isfinite(value) or value < 0:
                raise ValueError("Invalid native nonlinear residual observation")
            residuals.append(value)
            flags["RESI_GLOB_RELA" if column == columns[0] else "RESI_GLOB_MAXI"] = bool(token[2])
        current["iterations"].append({"iteration": int(iteration[1]), "RESI_GLOB_RELA": residuals[0],
            "RESI_GLOB_MAXI": residuals[1], "failed_criterion_flags": flags,
            "source_line": line_number, "raw_row": line})
    if [item["time_s"] for item in increments] != times_s[1:]:
        raise ValueError("Native nonlinear residual increments do not cover the exact declared nonzero-time history")
    checks = []
    for index, increment in enumerate(increments, 1):
        rows = increment["iterations"]
        if (not rows or [row["iteration"] for row in rows] != list(range(len(rows))) or
                len(rows) > worker.NONLINEAR_POLICY["maximum_iterations"]):
            raise ValueError("Incomplete/nonsequential native Newton iteration history")
        last = rows[-1]
        final = increment["final_residuals"]
        if set(final) != {"RESI_GLOB_RELA", "RESI_GLOB_MAXI"}:
            raise ValueError("Native final residual observations are missing")
        for criterion in final:
            if float(f'{final[criterion]["value"]:.5E}') != last[criterion]:
                raise ValueError("Native full precision final residual disagrees with the printed iteration row")
        for criterion, limit_key in (("RESI_GLOB_RELA", "relative_residual_limit"),
                                     ("RESI_GLOB_MAXI", "absolute_residual_limit")):
            value = final[criterion]["value"]
            limit = worker.NONLINEAR_POLICY[limit_key]
            flagged = last["failed_criterion_flags"][criterion] or last["failed_criterion_flags"]["iteration"]
            checks.append({"code": f"{criterion}_instant_{index}", "time_s": increment["time_s"],
                "status": "PASS" if value <= limit and not flagged else "FAIL",
                "observed": {"value": value, "native_unconverged_flag": flagged}, "limit": limit})
    return {"initial_state": {"time_s": times_s[0], "status": "INITIAL_STATE_NO_NEWTON_INCREMENT"},
            "increments": increments, "native_limits": worker.NONLINEAR_POLICY,
            "checks": checks, "status": "PASS" if all(check["status"] == "PASS" for check in checks) else "FAIL",
            "method": "Pinned native .mess RESI_GLOB_RELA/MAXI; both frozen limits required, no assembled A/u/b claim"}


def parse_measure_statistics(text: str, convergence: dict, times_s: list[float]) -> dict:
    """Cross-check actual STAT timing/count rows; these are not residuals."""
    rows = [[item.strip() for item in row] for row in csv.reader(text.splitlines()) if row]
    if len(rows) != len(times_s) + 1 or any(not row or row[0] or row[-1] for row in rows):
        raise ValueError("Native MESURE table must contain two headers and every nonzero-time row")
    rows = [row[1:-1] for row in rows]
    groups, names = rows[:2]
    if (not groups or len(names) != len(groups) or any(not name for name in names) or
            len(set(zip(groups, names))) != len(names) or
            any(group not in ("", "Time", "Count", "Memory") for group in groups)):
        raise ValueError("Malformed pinned MESURE/STAT two-level column headers")
    required = (("", "INST"), ("Count", "Newt_Iter"), ("", "State"))
    indexes = []
    for label in required:
        if label not in list(zip(groups, names)):
            raise ValueError("Native MESURE/STAT time/count/state columns are missing")
        indexes.append(list(zip(groups, names)).index(label))
    parsed = []
    for source_row, (row, instant, increment) in enumerate(zip(rows[2:], times_s[1:], convergence["increments"]), 3):
        if len(row) != len(names):
            raise ValueError("Incomplete native MESURE/STAT row")
        values = []
        for group, name, value in zip(groups, names, row):
            if (group, name) == ("", "State"):
                values.append(value)
            elif group in ("Count", "Memory"):
                if not re.fullmatch(r"\d+", value):
                    raise ValueError("Invalid native MESURE count/memory observation")
                values.append(int(value))
            else:
                try:
                    observed = float(value.replace("D", "E").replace("d", "e"))
                except ValueError as exc:
                    raise ValueError("Invalid native MESURE time observation") from exc
                if not math.isfinite(observed) or observed < 0:
                    raise ValueError("Nonfinite/negative native MESURE time observation")
                values.append(observed)
        printed_time, iterations, state = [values[index] for index in indexes]
        # STAT writes INST with E12.5 precision. Full-precision result access
        # parameters are checked separately; this is a transcription check.
        if (printed_time != float(f"{instant:.5e}") or iterations != len(increment["iterations"]) or state != "CONV"):
            raise ValueError("Native MESURE time/count/state differs from the verified increment history")
        parsed.append({"time_s": instant, "printed_time_s": printed_time, "newton_iteration_count": iterations,
                       "state": state, "values": values, "source_row": source_row, "raw_row": row})
    return {"column_groups": groups, "column_names": names, "rows": parsed, "status": "PASS",
            "method": "Pinned MESURE/STAT operation statistics cross-checked against .mess increments; not residuals"}


def _checked_worker(level: Path, mesh: dict, size: float, input_sha: str, settings: dict) -> tuple[dict, dict]:
    try:
        raw = json.loads((level / "worker_result.json").read_text(encoding="utf-8"))
        json.dumps(raw, allow_nan=False)
        versions, runtime = raw["versions"], raw["code_aster_runtime"]
        guard = raw["native_mesh_checks"]
        if (raw["input_sha256"] != input_sha or elastic._sha256(level / "input.json") != input_sha or
                raw["mesh_input_sha256"] != elastic._sha256(level / "mesh.msh") or
                versions["code_aster"] != "17.4.0" or runtime["version"] != "17.4.0" or
                any(not isinstance(versions.get(name), str) or not versions[name].strip() for name in ("python", "numpy"))):
            raise ValueError("Native nonlinear input/version identity is missing or drifted")
        if (guard.get("status") != "PASS" or guard.get("support_union_verified") is not True or
                guard.get("node_count") != mesh["node_count"] or
                guard.get("volume_element_count") != mesh["element_count"] or
                guard.get("expected_mesh_sha256") != elastic._sha256(level / "expected_mesh.json") or
                guard.get("checked_msh_sha256") != elastic._sha256(level / "mesh.msh") or
                json.loads((level / "native_mesh_checks.json").read_text(encoding="utf-8")) != guard):
            raise ValueError("Reused native pre-MECA geometry/topology/group gate evidence is missing or drifted")
        if raw.get("nonlinear_policy") != worker.NONLINEAR_POLICY:
            raise ValueError("Native nonlinear convergence policy differs from frozen policy")
        material = settings["material"]
        young, hardening = material["youngs_modulus_mpa"], material["plastic_modulus_mpa"]
        actual_material = raw.get("native_material", {})
        if (actual_material.get("ELAS") != {"E": young, "NU": material["poisson_ratio"]} or
                actual_material.get("ECRO_LINE") != {"SY": material["yield_stress_mpa"],
                                                     "D_SIGM_EPSI": young * (hardening / (young + hardening))} or
                json.loads((level / "native_material.json").read_text(encoding="utf-8")) != actual_material):
            raise ValueError("Native material/tangent declaration differs from frozen E/yield/H")
        record = worker.parse_history_tables(raw, size, settings["history"]["times_s"])
        if (record["element_count"] != mesh["element_count"] or
                mesh_worker.coordinate_bijection(record["coordinates_mm"], list(mesh["nodes"].values())) is None):
            raise ValueError("Native nonlinear mesh differs from the checked source")
        tolerance = 1e-12 * max(1., *settings["dimensions_mm"])
        for state in record["states"]:
            if any(any(value < -tolerance or value > span + tolerance for value, span in
                       zip(point, settings["dimensions_mm"])) for point in state["stress_point_coordinates_mm"]):
                raise ValueError("Native nonlinear integration point is outside the checked block")
        coordinates = dict(zip(record["node_ids"], record["coordinates_mm"]))
        for name, identifiers in record["group_node_ids"].items():
            if mesh_worker.coordinate_bijection([coordinates[node] for node in identifiers],
                [mesh["nodes"][node] for node in mesh["group_node_ids"][name]]) is None:
                raise ValueError(f"Native nonlinear boundary group differs from checked source: {name}")
        for name in ("results.med", "aster.mess", "convergence.measure"):
            if not (level / name).is_file() or (level / name).stat().st_size == 0:
                raise ValueError(f"Required native nonlinear evidence is missing: {name}")
        convergence = parse_convergence_log((level / "aster.mess").read_text(encoding="utf-8", errors="replace"),
                                             settings["history"]["times_s"])
        convergence["measure_statistics"] = parse_measure_statistics(
            (level / "convergence.measure").read_text(encoding="utf-8"), convergence, settings["history"]["times_s"])
        save_json(level / "nonlinear_convergence.json", convergence)
        record["nonlinear_convergence"] = convergence
        return raw, record
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise RuntimeError(f"Incomplete/malformed nonlinear fields at {level.name}: {exc}") from exc


class CodeAsterPlasticityAdapter:
    backend = "structural.code_aster.plasticity"
    domain = "elasticity"
    physics_domain = "structural"
    analysis_type = "nonlinear_static"
    version = "1.1"
    default_metrics = ["peak_stress", "final_stress", "peak_eq_plastic_strain", "unload_residual_strain",
                       "plastic_work_density", "hardening_energy_density", "plastic_dissipation_density",
                       "max_component_displacement_error", "max_component_stress_error",
                       "max_eq_plastic_strain_error", "reaction_relative_error", "mesh_agreement_relative"]

    def describe_model(self, settings: dict) -> dict:
        declaration = domain.model_declaration(settings)
        model = {field: declaration.pop(field) for field in ("geometry", "materials", "mesh")}
        return {"model": model, **declaration}

    def solve(self, output: Path, settings: dict) -> dict:
        output = Path(output)
        if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
            raise ValueError("Analysis output must be new or empty; preserved evidence cannot be overwritten")
        output.mkdir(parents=True, exist_ok=True)
        budgets = elastic.process_budgets()
        for name, data in _SOURCE_BYTES.items():
            (output / name).write_bytes(data)
        _assert_sources(output)
        provenance = {"adapter": self.backend, "adapter_version": self.version,
            "captured_source_sha256": dict(_SOURCE_SHA),
            "domain_plugin": {"module": domain.__name__, "version": domain.__version__,
                              "source_sha256": _SOURCE_SHA["domain_reference.py"],
                              "source_artifact": "simulation/domain_reference.py"},
            "reused_native_guard": "caelab.adapters.codeaster_worker.validate_native_mesh",
            "oci_manifest_sha256": elastic.OCI_MANIFEST_SHA256,
            "nonlinear_policy": worker.NONLINEAR_POLICY, "assumptions": _LIMITATIONS}
        checks = []

        def reject(code, observation, limit="Declared bounded uniaxial J2 load/unload history"):
            checks.append({"code": code, "status": "FAIL", "observed": observation, "limit": limit})
            outcome = {"status": "REJECTED", "solver_status": "NOT_RUN", "converged": None,
                "checks": checks, "metrics": {}, "pending_validations": _PENDING,
                "provenance": provenance, "raw_result": "simulation/analysis_raw.json"}
            save_json(output / "analysis_raw.json", outcome)
            return outcome

        try:
            settings = domain.validate_settings(settings)
        except ValueError as exc:
            return reject("plasticity_preflight", str(exc))
        save_json(output / "input.json", settings)
        save_json(output / "analytical_reference.json", domain.analytical_reference(settings))
        save_json(output / "model_declaration.json", self.describe_model(settings))
        try:
            workload = elastic._mesh_workload(settings)
        except elastic.MeshRejected as exc:
            return reject("mesh_workload_preflight", str(exc))
        save_json(output / "mesh_workload.json", workload)
        if not workload["admitted"]:
            return reject("mesh_workload_preflight", workload)
        checks.append({"code": "mesh_workload_preflight", "status": "PASS", "observed": workload,
                       "limit": {"maximum_nodes": workload["maximum_nodes"], "maximum_elements": workload["maximum_elements"]}})
        _assert_sources(output)
        try:
            image, image_sha, runtime, gmsh, prlimit = elastic._image_identity(output)
        except RuntimeError as exc:
            (output / "runtime_preflight.stderr.log").write_text(str(exc) + "\n", encoding="utf-8")
            raise
        save_json(output / "process_budgets.json", budgets)
        gmsh_version = elastic._process([gmsh, "-version"], output, "gmsh_version", timeout=10)
        singularity_version = elastic._process([runtime, "--version"], output, "container_version", timeout=10)
        if not gmsh_version or not singularity_version:
            raise RuntimeError("Native mesher/container version observations are missing")
        provenance.update({"image_path": str(image), "image_sha256": image_sha,
                           "versions": {"gmsh": gmsh_version, "singularity": singularity_version},
                           "input_sha256": elastic._sha256(output / "input.json")})
        meshes = []
        for index, size in enumerate(settings["mesh_sizes_mm"]):
            _assert_sources(output)
            level = output / f"level_{index}"
            level.mkdir(exist_ok=False)
            (level / "model.geo").write_text(elastic.gmsh_source(settings, size), encoding="utf-8")
            elastic._process([prlimit, f"--as={elastic._GMSH_MEMORY_BYTES}", f"--cpu={elastic._GMSH_CPU_SECONDS}", "--",
                gmsh, "model.geo", "-3", "-order", "2", "-format", "msh2", "-o", "mesh.msh", "-nopopup", "-v", "3"], level, "gmsh")
            try:
                mesh = elastic.parse_gmsh_mesh(level / "mesh.msh", settings["dimensions_mm"])
            except elastic.MeshRejected as exc:
                return reject(f"mesh_preflight_{index}", str(exc))
            except (ValueError, OSError, OverflowError) as exc:
                raise RuntimeError(f"Malformed Gmsh output at {level.name}: {exc}") from exc
            summary = {name: value for name, value in mesh.items() if name not in ("nodes", "tetrahedra", "surfaces")}
            save_json(level / "mesh_checks.json", summary)
            save_json(level / "expected_mesh.json", elastic._expected_mesh(mesh))
            checks.append({"code": f"mesh_preflight_{index}", "status": "PASS", "observed": summary,
                           "limit": {"minimum_jacobian": ">0", "volume_and_area_relative_error": 1e-10}})
            meshes.append((level, size, mesh))
        preferences, scratch_root = output / "preferences", output / "scratch"
        preferences.mkdir(exist_ok=False)
        scratch_root.mkdir(exist_ok=False)
        records, native = [], []
        for level, size, mesh in meshes:
            _assert_sources(output)
            if elastic._sha256(image) != image_sha:
                raise RuntimeError("Pinned image drifted before nonlinear execution")
            save_json(level / "input.json", {"settings": settings, "mesh_size_mm": size,
                "mesh_sha256": elastic._sha256(level / "mesh.msh"),
                "expected_mesh_sha256": elastic._sha256(level / "expected_mesh.json")})
            input_sha = elastic._sha256(level / "input.json")
            (level / "model.comm").write_text("import sys\nsys.path.insert(0, '/work')\n"
                "from codeaster_plasticity_worker import solve_level\n"
                f"solve_level('/work/{level.name}/input.json')\n", encoding="utf-8")
            (level / "model.export").write_text(
                f"P actions make_etude\nP memory_limit {budgets['solver_memory_mb']}\nP time_limit {budgets['solver_time_seconds']}\nP mpi_nbcpu 1\nP ncpus 2\n"
                f"F comm /work/{level.name}/model.comm D 1\nF mmed /work/{level.name}/mesh.msh D 20\n"
                f"F rmed /work/{level.name}/results.med R 80\nF mess /work/{level.name}/aster.mess R 6\n"
                f"F resu /work/{level.name}/aster.resu R 8\nF resu /work/{level.name}/convergence.measure R 81\n", encoding="utf-8")
            scratch = scratch_root / level.name
            scratch.mkdir(exist_ok=False)
            scratch_record = {"container_mount": "/tmp", "path": f"simulation/scratch/{level.name}",
                              "retention_status": "PRESERVED_UNTIL_VALID_EXTRACTION"}
            save_json(level / "scratch.json", scratch_record)
            command = [runtime, "exec", "--cleanenv", "--containall", "--no-home", "--env", "OMP_NUM_THREADS=2",
                "--bind", str(output.resolve()) + ":/work:rw", "--bind", str(preferences.resolve()) + ":" + str(Path.home()) + ":rw",
                "--bind", str(scratch.resolve()) + ":/tmp:rw", "--pwd", "/work", str(image),
                "/bin/bash", "--noprofile", "--norc", "-c", elastic.CONTAINER_SCRIPT,
                "caelab-codeaster-plasticity", f"/work/{level.name}/model.export"]
            elastic._process(command, level, "solver", timeout=budgets["subprocess_timeout_seconds"])
            raw, record = _checked_worker(level, mesh, size, input_sha, settings)
            save_json(level / "parsed_history.json", record)
            checks.append({"code": f"native_nonlinear_convergence_{len(records)}",
                "status": record["nonlinear_convergence"]["status"],
                "observed": record["nonlinear_convergence"]["checks"], "limit": worker.NONLINEAR_POLICY})
            _assert_sources(output)
            if elastic._sha256(image) != image_sha:
                raise RuntimeError("Pinned image drifted during nonlinear execution")
            elastic._cleanup_scratch(output, scratch)
            scratch_record["retention_status"] = "REMOVED_AFTER_VALID_EXTRACTION"
            save_json(level / "scratch.json", scratch_record)
            records.append(record)
            native.append(raw)
        if any(raw["versions"] != native[0]["versions"] or raw["code_aster_runtime"] != native[0]["code_aster_runtime"] for raw in native[1:]):
            raise RuntimeError("Native runtime identity changed across plasticity meshes")
        assessment = domain.assess(settings, records)
        _assert_sources(output)
        checks.extend(assessment["checks"])
        for index, record in enumerate(records):
            scale = max(1.0, *(abs(state["reaction_n"][0]) for state in record["states"]))
            error = max(abs(state["reaction_n"][0] + state["drive_reaction_x_n"]) for state in record["states"])
            checks.append({"code": f"drive_support_equilibrium_{index}", "status": "PASS" if error <=
                settings["limits"]["reaction_absolute_n"] + settings["limits"]["reaction_relative"] * scale else "FAIL",
                "observed": error, "limit": {"absolute_n": settings["limits"]["reaction_absolute_n"],
                    "relative": settings["limits"]["reaction_relative"], "scale_n": scale}})
        completed = all(check["status"] == "PASS" for check in checks)
        if not completed:
            failures = ", ".join(check["code"] for check in checks if check["status"] == "FAIL")
            for metric in assessment["metrics"].values():
                metric.update(valid=False, reason="Plasticity numerical validation failed: " + failures)
        provenance["versions"].update(native[0]["versions"])
        provenance.update({"code_aster_runtime": native[0]["code_aster_runtime"],
            "numerical_libraries": native[0].get("numerical_libraries"),
            "mesh": [f"simulation/{level.name}/mesh.msh" for level, _, _ in meshes],
            "native_fields": [f"simulation/{level.name}/results.med" for level, _, _ in meshes],
            "container_isolation": {"cleanenv": True, "containall": True, "no_home": True,
                "preferences": "Fresh experiment-only home content", "tmp": "Fresh per-level disk scratch",
                "omp_threads": 2, "mpi_ranks": 1},
            "process_budgets": {**budgets, "gmsh_address_space_bytes": elastic._GMSH_MEMORY_BYTES},
            "reaction_method": records[0]["reaction_method"], "measured_linear_residual": None})
        outcome = {"status": "COMPLETED" if completed else "REJECTED", "solver_status": "COMPLETED", "converged": True,
            "checks": checks, "metrics": assessment["metrics"], "pending_validations": assessment["pending_validations"],
            "provenance": provenance, "raw_result": "simulation/analysis_raw.json", "reference": assessment["reference"],
            "mesh_studies": assessment["mesh_studies"], "mesh_records": records,
            "mesh_response": assessment["mesh_response"], "derived_energy": assessment["derived_energy"],
            "limitations": [*assessment["limitations"], *_LIMITATIONS]}
        save_json(output / "analysis_raw.json", outcome)
        return outcome
