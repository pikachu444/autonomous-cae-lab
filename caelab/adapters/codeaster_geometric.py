"""Finite-rotation beam through the existing declared-model Core boundary.

The Domain owns the independent circle and numerical verdicts. This adapter
owns deterministic ASTER syntax, actual native six-DOF histories and evidence.
It reuses the pinned image, execution policy and owned process supervisor.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
import json
import math
from pathlib import Path
import re

from plugins.geometric_nonlinearity import reference as domain
from . import codeaster_elasticity as elastic
from . import codeaster_geometric_worker as worker
from .codeaster_plasticity import parse_measure_statistics
from ..storage import save_json


_SOURCES = {
    "domain_reference.py": Path(domain.__file__).resolve(),
    "domain_init.py": Path(domain.__file__).with_name("__init__.py"),
    "geometric_adapter.py": Path(__file__).resolve(),
    "codeaster_geometric_worker.py": Path(worker.__file__).resolve(),
    "mesh_runtime_adapter.py": Path(elastic.__file__).resolve(),
    "codeaster_worker.py": Path(__file__).with_name("codeaster_worker.py"),
    "codeaster_plasticity_worker.py": Path(__file__).with_name("codeaster_plasticity_worker.py"),
    "statistics_parser.py": Path(__file__).with_name("codeaster_plasticity.py"),
    "codeaster_execution.py": Path(__file__).with_name("codeaster_execution.py"),
    "execution_control.py": Path(__file__).resolve().parents[1] / "execution_control.py",
}
_SOURCE_BYTES = {name: path.read_bytes() for name, path in _SOURCES.items()}
_SOURCE_SHA = {name: hashlib.sha256(data).hexdigest() for name, data in _SOURCE_BYTES.items()}
_PENDING = ["native_global_energy", "static_strength", "material_qualification", "physical_validation",
            "fatigue_durability", "model_qualification"]
_LIMITATIONS = [
    "Bounded elastic pure end-moment finite-rotation SEG2 beam; not a full Phase5 qualification.",
    "Time is a quasi-static load parameter, not physical dynamics.",
    "Native rectangular section inputs are retained; native computed section properties are UNKNOWN.",
    "SIEF is a local generalized section wrench, not a native Cauchy stress tensor.",
    "Derived bending energy and section fiber stress are independent derived quantities, not native global energy or strength qualification.",
    "Initial local Y is explicit; native current-orientation qualification remains UNKNOWN.",
    "The pinned vendor image includes an MPI compatibility patch; compiled source equality remains UNKNOWN.",
    "Native nonlinear convergence is distinct from assembled A*x-b and independent curve accuracy.",
]


def _assert_sources(output: Path) -> None:
    for name, source in _SOURCES.items():
        if (not source.is_file() or elastic._sha256(source) != _SOURCE_SHA[name] or
                not (output / name).is_file() or elastic._sha256(output / name) != _SOURCE_SHA[name]):
            raise RuntimeError(f"Captured geometric/backend source drifted: {name}; old evidence remains preserved")


def parse_convergence_log(text: str, times_s: list[float]) -> dict:
    """Require real full .mess residual histories under the explicit beam policy.

    Native rounded Newton cells are cross-checked against full precision final
    summaries. A residual FAIL is retained; malformed/missing histories fail
    extraction. Neither measure statistics nor curve errors replace residuals.
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
                raise ValueError("Duplicate/nonfinite native beam final residual summary")
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
            raise ValueError("Native beam iteration lacks verified residual headers")
        observations = {}
        flags = {"iteration": bool(iteration[2])}
        for criterion, column in zip(("RESI_GLOB_RELA", "RESI_GLOB_MAXI"), columns):
            token = re.fullmatch(r"(" + number + r")\s*(X?)", fields[column])
            if token is None:
                raise ValueError("Missing/nonfinite native beam nonlinear residual cell")
            value = float(token[1].replace("D", "E").replace("d", "e"))
            if not math.isfinite(value) or value < 0:
                raise ValueError("Invalid native beam nonlinear residual cell")
            observations[criterion] = value
            flags[criterion] = bool(token[2])
        current["iterations"].append({"iteration": int(iteration[1]), **observations,
            "failed_criterion_flags": flags, "source_line": line_number, "raw_row": line})
    if [item["time_s"] for item in increments] != times_s[1:]:
        raise ValueError("Native beam increments omit/duplicate the exact requested nonzero-time history")
    checks = []
    for index, increment in enumerate(increments, 1):
        rows = increment["iterations"]
        if (not rows or [row["iteration"] for row in rows] != list(range(len(rows))) or
                len(rows) > worker.NONLINEAR_POLICY["maximum_iterations"]):
            raise ValueError("Incomplete/nonsequential native beam Newton history")
        final, last = increment["final_residuals"], rows[-1]
        if set(final) != {"RESI_GLOB_RELA", "RESI_GLOB_MAXI"}:
            raise ValueError("Native beam full precision final residuals are missing")
        for criterion, limit_name in (("RESI_GLOB_RELA", "relative_residual_limit"),
                                      ("RESI_GLOB_MAXI", "absolute_residual_limit")):
            value = final[criterion]["value"]
            if float(f"{value:.5E}") != last[criterion]:
                raise ValueError("Native beam full precision final residual differs from rounded Newton cell")
            flagged = last["failed_criterion_flags"][criterion] or last["failed_criterion_flags"]["iteration"]
            limit = worker.NONLINEAR_POLICY[limit_name]
            checks.append({"code": f"{criterion}_instant_{index}", "time_s": increment["time_s"],
                "status": "PASS" if value <= limit and not flagged else "FAIL",
                "observed": {"value": value, "native_unconverged_flag": flagged}, "limit": limit})
    return {"initial_state": {"time_s": times_s[0], "status": "INITIAL_STATE_NO_NEWTON_INCREMENT"},
            "increments": increments, "native_limits": deepcopy(worker.NONLINEAR_POLICY), "checks": checks,
            "status": "PASS" if all(check["status"] == "PASS" for check in checks) else "FAIL",
            "method": "Actual native .mess full precision RESI_GLOB_RELA/MAXI with explicit beam policy; no assembled residual claim"}


def comm_source(level_name: str) -> str:
    if not re.fullmatch(r"level_[0-9]+", level_name):
        raise ValueError("Native beam command level must be an owned level_N directory")
    return ("import sys\nsys.path.insert(0, '/work')\n"
            "from codeaster_geometric_worker import solve_level\n"
            f"solve_level('/work/{level_name}/input.json')\n")


def export_source(level_name: str, budgets: dict) -> str:
    comm_source(level_name)
    memory, cpu = budgets["solver_memory_mb"], budgets["solver_time_seconds"]
    if type(memory) is not int or memory <= 0 or type(cpu) is not int or cpu <= 0:
        raise ValueError("Native export memory/CPU budgets must be positive integers")
    return (f"P actions make_etude\nP memory_limit {memory}\nP time_limit {cpu}\nP mpi_nbcpu 1\nP ncpus 2\n"
            f"F comm /work/{level_name}/model.comm D 1\nF mail /work/{level_name}/mesh.mail D 20\n"
            f"F rmed /work/{level_name}/results.med R 80\nF mess /work/{level_name}/aster.mess R 6\n"
            f"F resu /work/{level_name}/aster.resu R 8\nF resu /work/{level_name}/convergence.measure R 81\n")


def _checked_worker(level: Path, expected: dict, input_sha: str, settings: dict, budgets: dict) -> tuple[dict, dict]:
    try:
        raw = json.loads((level / "worker_result.json").read_text(encoding="utf-8"))
        json.dumps(raw, allow_nan=False)
        captured_input = json.loads((level / "input.json").read_text(encoding="utf-8"))
        if (captured_input["settings"] != settings or captured_input["element_count"] != expected["element_count"] or
                captured_input["captured_source_sha256"] != _SOURCE_SHA or
                (level / "mesh.mail").read_text(encoding="utf-8") != worker.mail_source(expected) or
                (level / "model.comm").read_text(encoding="utf-8") != comm_source(level.name) or
                (level / "model.export").read_text(encoding="utf-8") != export_source(level.name, budgets) or
                captured_input["comm_sha256"] != elastic._sha256(level / "model.comm") or
                captured_input["export_sha256"] != elastic._sha256(level / "model.export")):
            raise ValueError("Native beam captured settings/deck/source differ from exact generated input")
        versions, runtime, guard = raw["versions"], raw["code_aster_runtime"], raw["native_mesh_checks"]
        if (raw["input_sha256"] != input_sha or elastic._sha256(level / "input.json") != input_sha or
                raw["mesh_input_sha256"] != elastic._sha256(level / "mesh.mail") or
                versions["code_aster"] != "17.4.0" or runtime["version"] != "17.4.0" or
                any(not isinstance(versions.get(name), str) or not versions[name].strip() for name in ("python", "numpy")) or
                json.loads((level / "runtime.json").read_text(encoding="utf-8")) !=
                    {"versions": versions, "code_aster_runtime": runtime}):
            raise ValueError("Native beam input/runtime identity is missing or drifted")
        if (json.loads((level / "expected_mesh.json").read_text(encoding="utf-8")) != expected or
                guard.get("status") != "PASS" or guard.get("support_union_verified") is not True or
                guard.get("node_count") != len(expected["nodes"]) or guard.get("element_count") != expected["element_count"] or
                guard.get("expected_mesh_sha256") != elastic._sha256(level / "expected_mesh.json") or
                guard.get("checked_mail_sha256") != elastic._sha256(level / "mesh.mail") or
                json.loads((level / "native_mesh_checks.json").read_text(encoding="utf-8")) != guard or
                json.loads((level / "mesh_catalog.json").read_text(encoding="utf-8")) != raw["mesh"]):
            raise ValueError("Native beam pre-solve geometry/group gate is missing or drifted")
        material = {"ELAS": {"E": settings["material"]["youngs_modulus_mpa"], "NU": settings["material"]["poisson_ratio"]}}
        section = worker.native_section(settings)
        for name, actual, declared in (("native_material.json", raw.get("native_material"), material),
                                       ("native_section.json", raw.get("native_section"), section),
                                       ("nonlinear_policy.json", raw.get("nonlinear_policy"), worker.NONLINEAR_POLICY)):
            if actual != declared or json.loads((level / name).read_text(encoding="utf-8")) != declared:
                raise ValueError("Native beam material/section/frame/policy differs from frozen input")
        if raw.get("native_global_energy", {}).get("status") != "UNKNOWN" or raw.get("measured_linear_residual") is not None:
            raise ValueError("Unsupported native global energy/assembled residual cannot be declared observed")
        record = worker.parse_history_tables(raw, settings["history"]["times_s"])
        # Re-run the complete catalogue guard against the actual native catalogue
        # through its recorded mappings, independent of a PASS label.
        native_mesh = _RecordedMesh(raw["mesh"])
        verified, catalog = worker.validate_native_mesh(native_mesh, expected)
        if (catalog != raw["mesh"] or any(guard.get(key) != value for key, value in verified.items())):
            raise ValueError("Recorded beam native/source identity mapping differs from checked source")
        access = {"available_orders": raw["available_orders"], "access_parameters": raw["access_parameters"]}
        if json.loads((level / "native_access_parameters.json").read_text(encoding="utf-8")) != access:
            raise ValueError("Saved native beam order/time access identity differs")
        for state in raw["states"]:
            for name, table in state["tables"].items():
                if json.loads((level / f"order_{state['order']}_{name.lower()}.table.json").read_text(encoding="utf-8")) != table:
                    raise ValueError("Saved raw native beam table differs from returned field")
        for name in ("results.med", "aster.mess", "aster.resu", "convergence.measure"):
            if not (level / name).is_file() or (level / name).stat().st_size == 0:
                raise ValueError(f"Required native beam evidence is missing: {name}")
        convergence = parse_convergence_log((level / "aster.mess").read_text(encoding="utf-8", errors="replace"),
                                             settings["history"]["times_s"])
        convergence["measure_statistics"] = parse_measure_statistics(
            (level / "convergence.measure").read_text(encoding="utf-8"), convergence, settings["history"]["times_s"])
        save_json(level / "nonlinear_convergence.json", convergence)
        record["nonlinear_convergence"] = convergence
        return raw, record
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
        raise RuntimeError(f"Incomplete/malformed finite-rotation beam fields at {level.name}: {exc}") from exc


class _RecordedMesh:
    """Read-only native catalogue view for a second source/mapping check.

    This checks saved evidence, and never substitutes for the real worker's
    pre-solve Mesh API guard. Native table fields remain separately checked.
    """
    def __init__(self, catalog):
        self.catalog = catalog
        self.nodes = sorted(catalog["nodes"], key=lambda item: item["node_id"])
        self.cells = sorted(catalog["beam_elements"], key=lambda item: item["element_id"])
        if ([node["node_id"] for node in self.nodes] != list(range(1, len(self.nodes) + 1)) or
                [cell["element_id"] for cell in self.cells] != list(range(1, len(self.cells) + 1))):
            raise ValueError("Recorded native numeric node/cell indices are incomplete")

    def getCoordinates(self):
        return self

    def toNumpy(self):
        return self

    def tolist(self):
        return [node["coordinates_mm"] for node in self.nodes]

    def getNodes(self, group=None):
        return list(range(len(self.nodes))) if group is None else [node - 1 for node in self.catalog["group_node_ids"][group]]

    def getNumberOfNodes(self):
        return len(self.nodes)

    def getNumberOfCells(self):
        return len(self.cells)

    def getConnectivity(self):
        return [[node - 1 for node in cell["node_ids"]] for cell in self.cells]

    def getCellTypeName(self, index):
        return self.cells[index]["type"]

    def getCells(self, group):
        return list(range(len(self.cells))) if group == "BEAM" else []

    def getGroupsOfCells(self):
        return ["BEAM"]

    def getGroupsOfNodes(self):
        return list(self.catalog["group_node_ids"])


class CodeAsterGeometricAdapter:
    backend = "structural.code_aster.geometric_nonlinearity"
    domain = "geometric_nonlinearity"
    physics_domain = "structural"
    analysis_type = "nonlinear_static"
    version = "1.0"
    default_metrics = ["tip_x", "tip_y", "tip_rotation_z", "root_moment_z", "derived_section_fiber_stress",
        "derived_bending_energy", "max_position_error", "finest_position_error", "max_rotation_error", "max_force_error",
        "max_moment_error", "max_section_force_error", "max_section_moment_error", "max_curvature_error",
        "max_derived_energy_error", "minimum_mesh_rate"]

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
                              "source_sha256": _SOURCE_SHA["domain_reference.py"], "source_artifact": "simulation/domain_reference.py"},
            "oci_manifest_sha256": elastic.OCI_MANIFEST_SHA256, "nonlinear_policy": deepcopy(worker.NONLINEAR_POLICY),
            "field_semantics": deepcopy(worker.FIELD_SEMANTICS), "assumptions": list(_LIMITATIONS),
            "native_section_property_coverage": "UNKNOWN", "native_global_energy": "UNKNOWN",
            "compiled_source_equivalence": "UNKNOWN"}
        checks = []
        try:
            settings = domain.validate_settings(settings)
        except ValueError as exc:
            checks.append({"code": "geometric_preflight", "status": "FAIL", "observed": str(exc),
                           "limit": "Declared bounded elastic pure end-moment beam"})
            outcome = {"status": "REJECTED", "solver_status": "NOT_RUN", "converged": None,
                "checks": checks, "metrics": {}, "pending_validations": list(_PENDING),
                "provenance": provenance, "raw_result": "simulation/analysis_raw.json", "limitations": list(_LIMITATIONS)}
            save_json(output / "analysis_raw.json", outcome)
            return outcome
        save_json(output / "input.json", settings)
        save_json(output / "analytical_reference.json", domain.analytical_reference(settings))
        save_json(output / "model_declaration.json", self.describe_model(settings))
        _assert_sources(output)
        try:
            image, image_sha, runtime, _gmsh, _prlimit = elastic._image_identity(output)
        except RuntimeError as exc:
            (output / "runtime_preflight.stderr.log").write_text(str(exc) + "\n", encoding="utf-8")
            raise
        container_version = elastic._process([runtime, "--version"], output, "container_version", timeout=10)
        if not container_version:
            raise RuntimeError("Native container version observation is missing")
        provenance.update(image_path=str(image), image_sha256=image_sha,
                          versions={"singularity": container_version}, input_sha256=elastic._sha256(output / "input.json"))
        save_json(output / "process_budgets.json", budgets)
        preferences, scratch_root = output / "preferences", output / "scratch"
        preferences.mkdir(exist_ok=False)
        scratch_root.mkdir(exist_ok=False)
        records, native, meshes = [], [], []
        for index, count in enumerate(settings["mesh"]["element_counts"]):
            _assert_sources(output)
            if elastic._sha256(image) != image_sha:
                raise RuntimeError("Pinned image drifted before finite-rotation beam execution")
            level = output / f"level_{index}"
            level.mkdir(exist_ok=False)
            expected = worker.beam_mesh(settings["beam"]["length_mm"], count)
            (level / "mesh.mail").write_text(worker.mail_source(expected), encoding="utf-8")
            save_json(level / "expected_mesh.json", expected)
            (level / "model.comm").write_text(comm_source(level.name), encoding="utf-8")
            (level / "model.export").write_text(export_source(level.name, budgets), encoding="utf-8")
            save_json(level / "input.json", {"settings": settings, "element_count": count,
                "mesh_sha256": elastic._sha256(level / "mesh.mail"),
                "expected_mesh_sha256": elastic._sha256(level / "expected_mesh.json"),
                "comm_sha256": elastic._sha256(level / "model.comm"),
                "export_sha256": elastic._sha256(level / "model.export"),
                "captured_source_sha256": dict(_SOURCE_SHA)})
            input_sha = elastic._sha256(level / "input.json")
            scratch = scratch_root / level.name
            scratch.mkdir(exist_ok=False)
            scratch_record = {"container_mount": "/tmp", "path": f"simulation/scratch/{level.name}",
                              "retention_status": "PRESERVED_UNTIL_VALID_EXTRACTION"}
            save_json(level / "scratch.json", scratch_record)
            command = [runtime, "exec", "--cleanenv", "--containall", "--no-home", "--env", "OMP_NUM_THREADS=2",
                "--bind", str(output.resolve()) + ":/work:rw",
                "--bind", str(preferences.resolve()) + ":" + str(Path.home()) + ":rw",
                "--bind", str(scratch.resolve()) + ":/tmp:rw", "--pwd", "/work", str(image),
                "/bin/bash", "--noprofile", "--norc", "-c", elastic.CONTAINER_SCRIPT,
                "caelab-codeaster-geometric", f"/work/{level.name}/model.export"]
            _assert_sources(output)
            if elastic._sha256(image) != image_sha:
                raise RuntimeError("Pinned image drifted immediately before finite-rotation beam execution")
            elastic._process(command, level, "solver", timeout=budgets["subprocess_timeout_seconds"])
            raw, record = _checked_worker(level, expected, input_sha, settings, budgets)
            save_json(level / "parsed_history.json", record)
            checks.append({"code": f"native_nonlinear_convergence_{index}", "status": record["nonlinear_convergence"]["status"],
                           "observed": record["nonlinear_convergence"]["checks"], "limit": deepcopy(worker.NONLINEAR_POLICY)})
            _assert_sources(output)
            if elastic._sha256(image) != image_sha:
                raise RuntimeError("Pinned image drifted during finite-rotation beam execution")
            elastic._cleanup_scratch(output, scratch)
            scratch_record["retention_status"] = "REMOVED_AFTER_VALID_EXTRACTION"
            save_json(level / "scratch.json", scratch_record)
            records.append(record)
            native.append(raw)
            meshes.append(level)
        if any(raw["versions"] != native[0]["versions"] or raw["code_aster_runtime"] != native[0]["code_aster_runtime"]
               for raw in native[1:]):
            raise RuntimeError("Native runtime identity changed across finite-rotation beam meshes")
        _assert_sources(output)
        assessment = domain.assess(settings, records)
        _assert_sources(output)
        if elastic._sha256(image) != image_sha:
            raise RuntimeError("Pinned image drifted before finite-rotation beam result publication")
        checks.extend(assessment["checks"])
        completed = all(check["status"] == "PASS" for check in checks)
        if not completed:
            failures = ", ".join(check["code"] for check in checks if check["status"] != "PASS")
            for metric in assessment["metrics"].values():
                metric.update(valid=False, reason="Geometric numerical validation incomplete/failed: " + failures)
        provenance["versions"].update(native[0]["versions"])
        provenance.update(code_aster_runtime=native[0]["code_aster_runtime"],
            numerical_libraries=native[0].get("numerical_libraries"),
            mesh=[f"simulation/{level.name}/mesh.mail" for level in meshes],
            solver_deck=[f"simulation/{level.name}/model.comm" for level in meshes],
            native_fields=[f"simulation/{level.name}/results.med" for level in meshes],
            native_mesh_guard=[f"simulation/{level.name}/native_mesh_checks.json" for level in meshes],
            reaction_method=records[0]["reaction_method"], measured_linear_residual=None,
            process_budgets=budgets,
            container_isolation={"cleanenv": True, "containall": True, "no_home": True,
                                 "preferences": "Fresh experiment-only home content", "tmp": "Fresh per-level disk scratch",
                                 "omp_threads": 2, "mpi_ranks": 1})
        outcome = {"status": "COMPLETED" if completed else "REJECTED", "solver_status": "COMPLETED", "converged": True,
            "checks": checks, "metrics": assessment["metrics"],
            "pending_validations": list(dict.fromkeys([*assessment["pending_validations"], *_PENDING])),
            "provenance": provenance, "raw_result": "simulation/analysis_raw.json", "reference": assessment["reference"],
            "mesh_studies": assessment["mesh_studies"], "mesh_records": records,
            "mesh_response": assessment["mesh_response"], "derived_energy": assessment["derived_energy"],
            "derived_stress": assessment["derived_stress"],
            "limitations": [*assessment["limitations"], *_LIMITATIONS]}
        save_json(output / "analysis_raw.json", outcome)
        return outcome
