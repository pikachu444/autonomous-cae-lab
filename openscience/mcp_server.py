"""Stdio MCP transport for a locally authorized OpenScience project.

Install requirements-mcp.txt in the selected Python environment. The SDK owns
the protocol; this file only forwards typed research operations to CAE-Lab.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server.fastmcp import FastMCP

from caelab import Lab
from caelab.adapters import fixture_cadquery


mcp = FastMCP("Autonomous CAE Lab")


_GIT_TIMEOUT_SECONDS = 3
_SOURCE_IDENTITY_URI = "caelab://runtime/source-identity"


def _diagnostic_error(error: OSError) -> str:
    if isinstance(error, FileNotFoundError):
        return "NOT_FOUND"
    if isinstance(error, PermissionError):
        return "ACCESS_DENIED"
    return "IO_ERROR"


def _diagnostic_git(root: Path, args: list[str]) -> tuple[str | None, dict]:
    """Fixed read-only Git probes; never return stderr, argv or environment."""
    try:
        # Git status may otherwise write/lock its index even for a diagnostic.
        # Disable optional index writes and configured fsmonitor execution.
        result = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", *args], cwd=root, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=_GIT_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        return None, {"status": "UNKNOWN", "error": "TIMEOUT"}
    except OSError as error:
        return None, {"status": "UNKNOWN", "error": _diagnostic_error(error)}
    except UnicodeError:
        return None, {"status": "UNKNOWN", "error": "INVALID_OUTPUT"}
    if result.returncode != 0:
        return None, {"status": "UNKNOWN", "error": "NONZERO_EXIT",
                      "return_code": result.returncode}
    return result.stdout, {"status": "KNOWN", "error": None, "return_code": 0}


def _diagnostic_git_identity(root: Path) -> dict:
    commit, commit_probe = _diagnostic_git(root, ["rev-parse", "HEAD"])
    if commit is not None:
        commit = commit.strip()
        if not re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", commit):
            commit, commit_probe = None, {"status": "UNKNOWN", "error": "INVALID_OUTPUT"}
    dirty, dirty_probe = _diagnostic_git(
        root, ["status", "--porcelain", "--untracked-files=normal"])
    return {"commit": commit or "UNKNOWN", "dirty": None if dirty is None else bool(dirty.strip()),
            "probes": {"commit": commit_probe, "dirty": dirty_probe}}


def _diagnostic_source_hash(root: Path, names: list[str], *, missing_marker: bool = False) -> dict:
    """Existing Core/fixture path+file-digest semantics, without unbounded Git."""
    digest = hashlib.sha256()
    try:
        if not root.is_dir() or not names:
            return {"status": "UNKNOWN", "error": "NOT_FOUND", "sha256": None}
        for name in names:
            source = root / name
            if not source.resolve().is_relative_to(root.resolve()):
                return {"status": "UNKNOWN", "error": "OUTSIDE_SOURCE_ROOT", "sha256": None}
            digest.update(name.encode())
            digest.update(hashlib.sha256(source.read_bytes()).digest()
                          if not missing_marker or source.is_file() else b"MISSING")
    except OSError as error:
        return {"status": "UNKNOWN", "error": _diagnostic_error(error), "sha256": None}
    except (UnicodeError, RuntimeError):
        return {"status": "UNKNOWN", "error": "INVALID_SOURCE_PATH", "sha256": None}
    return {"status": "KNOWN", "error": None, "sha256": digest.hexdigest()}


@mcp.resource(_SOURCE_IDENTITY_URI, name="resident_mcp_source_identity",
              mime_type="application/json")
def runtime_source_identity() -> str:
    """Read resident MCP import paths and bounded Git/disk source diagnostics.

    This creates no Lab/store, imports no CAD model and supplies no provenance
    verdict. On-disk fingerprints are not a hash of cached Python bytecode.
    """
    core_module = sys.modules[Lab.__module__]
    core_path = Path(core_module.__file__).resolve()
    core_root = core_path.parents[1]
    fixture_root = fixture_cadquery.UPSTREAM.resolve()
    try:
        core_files = [*sorted((core_root / "caelab").rglob("*.py")),
                      *sorted((core_root / "schemas").glob("*.json"))]
        core_hash = _diagnostic_source_hash(
            core_root, [path.relative_to(core_root).as_posix() for path in core_files])
    except OSError as error:
        core_hash = {"status": "UNKNOWN", "error": _diagnostic_error(error), "sha256": None}
    fixture_names, fixture_files_probe = _diagnostic_git(
        fixture_root, ["ls-files", "--cached", "--others", "--exclude-standard", "-z"])
    fixture_hash = (_diagnostic_source_hash(
        fixture_root, sorted(set(name for name in fixture_names.split("\0") if name)),
        missing_marker=True) if fixture_names is not None else
        {"status": "UNKNOWN", "error": fixture_files_probe["error"], "sha256": None})
    imported_fixture = {
        name: str(Path(module.__file__).resolve())
        for name, module in list(sys.modules.items())
        if (name == "fixturelab" or name.startswith("fixturelab."))
        and getattr(module, "__file__", None)
    }
    return json.dumps({
        "schema_version": 1, "resource": _SOURCE_IDENTITY_URI, "diagnostic_only": True,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "fingerprint_observation": "on-disk source; not cached imported Python bytecode",
        "process": {"pid": os.getpid(), "python_executable": sys.executable,
                    "mcp_server_path": str(Path(__file__).resolve())},
        "core": {"module_path": str(core_path), "repo_path": str(core_root),
                 "git": _diagnostic_git_identity(core_root),
                 "fingerprint": {**core_hash, "semantics": "caelab.storage.source_identity"}},
        "fixture": {"adapter_module_path": str(Path(fixture_cadquery.__file__).resolve()),
                    "repo_path": str(fixture_root), "imported_module_paths": imported_fixture,
                    "git": _diagnostic_git_identity(fixture_root),
                    "files_probe": fixture_files_probe,
                    "fingerprint": {**fixture_hash,
                                    "semantics": "FixtureCadQueryAdapter.source_fingerprint"}},
    }, sort_keys=True, allow_nan=False)


def _lab() -> Lab:
    return Lab(Path(os.environ.get("CAELAB_STORE", str(Path(__file__).resolve().parents[1] / "runs"))))


@mcp.tool()
def study_create(study_id: str, name: str, research_question: str,
                 hypothesis: str, objective: str) -> dict:
    """Create a persistent research study with a question, hypothesis and objective."""
    return _lab().create_study(study_id, name, research_question, hypothesis, objective)


@mcp.tool()
def study_inspect(study_id: str) -> dict:
    """Read a persisted study's research question and hypothesis."""
    return _lab().inspect_study(study_id)


@mcp.tool()
def parameters_discover(backend: str, model: str) -> list[dict]:
    """Inspect a trusted CAD model for native parameter candidates; read only."""
    return _lab().discover_parameters(backend, model)


@mcp.tool()
def parameters_list(study_id: str) -> dict:
    """Read the versioned registry and existing native-to-research variable mappings."""
    return _lab().registry(study_id)


@mcp.tool()
def parameters_refresh(study_id: str, backend: str, model: str) -> dict:
    """Reverify mapped CAD dimensions after an engineer changes native source; retain registry history."""
    return _lab().refresh_registry(study_id, backend, model)


@mcp.tool()
def model_native_inspect(model: str) -> dict:
    """Inspect editable FreeCAD feature tree, driving dimensions and final-solid candidates."""
    return _lab().inspect_native_model(model)


@mcp.tool()
def model_native_select_final(model: str, final: str) -> dict:
    """Select an existing FreeCAD final solid after importing a document."""
    return _lab().select_native_final(model, final)


@mcp.tool()
def model_native_new(template: str = "roller_support") -> dict:
    """Create a trusted editable fixture template when FreeCADCmd is installed."""
    return _lab().create_native_model(template=template)


@mcp.tool()
def model_native_import(file_name: str) -> dict:
    """Import an existing FCStd from the configured CAELAB_IMPORT_ROOT folder."""
    root = os.environ.get("CAELAB_IMPORT_ROOT")
    if not root or not file_name or Path(file_name).name != file_name or not file_name.endswith(".FCStd"):
        raise ValueError("Select an FCStd filename under CAELAB_IMPORT_ROOT")
    source = (Path(root) / file_name).resolve()
    if not source.is_relative_to(Path(root).resolve()):
        raise ValueError("FCStd path escapes CAELAB_IMPORT_ROOT")
    return _lab().import_native_model(source)


@mcp.tool()
def parameters_register(study_id: str, backend: str, model: str, native_path: str,
                        parameter_id: str, display_name: str, lower: float, upper: float,
                        mode: str = "free", kind: str = "continuous") -> dict:
    """Map one discovered CAD dimension to a named research variable and probe its geometry effect."""
    return _lab().register_parameter(study_id, backend, model, native_path,
                                     parameter_id, display_name, lower, upper, mode, kind)


@mcp.tool()
def experiment_run(study_id: str, experiment_id: str, backend: str, model: str,
                   values: dict[str, float], hypothesis_id: str | None = None,
                   settings: dict | None = None) -> dict:
    """Run an immutable CAD experiment; invalid proposals are recorded and blocked before export."""
    return _lab().run_experiment(study_id=study_id, experiment_id=experiment_id,
                                 backend=backend, model=model, values=values,
                                 hypothesis_id=hypothesis_id, settings=settings)


@mcp.tool()
def experiment_inspect(experiment_id: str) -> dict:
    """Read full metrics, evidence, validation, provenance and checked artifact hashes."""
    return _lab().inspect_experiment(experiment_id)


@mcp.tool()
def experiment_summary(experiment_id: str) -> dict:
    """Read concise solver-independent research outcome; UNKNOWN remains explicit."""
    return _lab().research_summary(experiment_id)


@mcp.tool()
def experiment_compare(experiment_ids: list[str]) -> list[dict]:
    """Compare summarized experiments by registered research variable and validation."""
    return _lab().compare(experiment_ids)


@mcp.tool()
def analysis_run(parent_experiment_id: str, experiment_id: str, backend: str,
                 settings: dict) -> dict:
    """Analyze a verified CAD revision as a new child experiment with explicit load/material/mesh."""
    return _lab().run_analysis(parent_experiment_id=parent_experiment_id,
                               experiment_id=experiment_id, backend=backend,
                               settings=settings)


@mcp.tool()
def doe_plan(study_id: str, campaign_id: str, backend: str, model: str,
             parameter_ids: list[str], sample_count: int, seed: int,
             analysis_backend: str | None = None,
             analysis_settings: dict | None = None,
             engine: str = "scipy.latin_hypercube") -> dict:
    """Persist seeded numerical samples of registered research variables before execution."""
    return _lab().plan_doe(study_id=study_id, campaign_id=campaign_id,
                           backend=backend, model=model, parameter_ids=parameter_ids,
                           sample_count=sample_count, seed=seed,
                           analysis_backend=analysis_backend,
                           analysis_settings=analysis_settings, engine=engine)


@mcp.tool()
def doe_run(campaign_id: str) -> dict:
    """Execute a persisted DOE; invalid CAD points never reach the solver."""
    return _lab().run_doe(campaign_id)


@mcp.tool()
def doe_inspect(campaign_id: str) -> dict:
    """Read the checked campaign plan, sample journal and result references."""
    return _lab().inspect_doe(campaign_id)


@mcp.tool()
def optimization_plan(study_id: str, campaign_id: str, backend: str, model: str,
                      parameter_ids: list[str], objective: dict, constraints: list[dict],
                      seed: int, max_generations: int = 1, population_size: int = 5,
                      initial_values: dict | None = None, analysis_backend: str | None = None,
                      analysis_settings: dict | None = None, required_validations: dict | None = None,
                      engine: str = "scipy.differential_evolution") -> dict:
    """Freeze research metric semantics and a deterministic bounded numerical search; no engineering release."""
    return _lab().plan_optimization(study_id=study_id, campaign_id=campaign_id, backend=backend,
                                    model=model, parameter_ids=parameter_ids, objective=objective,
                                    constraints=constraints, seed=seed, max_generations=max_generations,
                                    population_size=population_size, initial_values=initial_values,
                                    analysis_backend=analysis_backend, analysis_settings=analysis_settings,
                                    required_validations=required_validations, engine=engine)


@mcp.tool()
def optimization_run(campaign_id: str) -> dict:
    """Run or exactly replay adaptive numerical evaluations; preserve invalid evidence and stop backend failures."""
    return _lab().run_optimization(campaign_id)


@mcp.tool()
def optimization_inspect(campaign_id: str) -> dict:
    """Read checked optimizer state, valid incumbent, metric semantics and every immutable evaluation."""
    return _lab().inspect_optimization(campaign_id)


@mcp.tool()
def pde_run(study_id: str, experiment_id: str, backend: str, settings: dict,
            hypothesis_id: str | None = None) -> dict:
    """Run a declared weak-form PDE and record analytical error/field evidence through the common Core."""
    return _lab().run_pde(study_id=study_id, experiment_id=experiment_id, backend=backend,
                           settings=settings, hypothesis_id=hypothesis_id)


@mcp.tool()
def model_analysis_run(study_id: str, experiment_id: str, backend: str, settings: dict,
                       hypothesis_id: str | None = None) -> dict:
    """Analyze a declared research model without a CAD parent and retain checked numerical evidence."""
    return _lab().run_model_analysis(study_id=study_id, experiment_id=experiment_id,
                                    backend=backend, settings=settings, hypothesis_id=hypothesis_id)


@mcp.tool()
def model_parameters_discover(backend: str, settings: dict) -> list[dict]:
    """Discover advertised scalar model inputs; preserve fixed loads/mesh/numerical limits."""
    return _lab().discover_model_parameters(backend, settings)


@mcp.tool()
def model_parameters_register(study_id: str, backend: str, settings: dict, input_id: str,
                              parameter_id: str, display_name: str, lower: float, upper: float,
                              mode: str = "free") -> dict:
    """Map one named declared-model input; declaration effect is not physical qualification."""
    return _lab().register_model_parameter(study_id, backend, settings, input_id,
                                          parameter_id, display_name, lower, upper, mode)


@mcp.tool()
def model_optimization_plan(study_id: str, campaign_id: str, backend: str, settings: dict,
                            parameter_ids: list[str], objective: dict, constraints: list[dict],
                            seed: int, max_generations: int = 1, population_size: int = 5,
                            initial_values: dict | None = None, required_validations: dict | None = None,
                            engine: str = "scipy.differential_evolution") -> dict:
    """Freeze declared-model input bindings and runtime for the existing numerical search engine."""
    return _lab().plan_model_optimization(study_id=study_id, campaign_id=campaign_id, backend=backend,
             settings=settings, parameter_ids=parameter_ids, objective=objective, constraints=constraints,
             seed=seed, max_generations=max_generations, population_size=population_size,
             initial_values=initial_values, required_validations=required_validations, engine=engine)


if __name__ == "__main__":
    mcp.run(transport="stdio")
