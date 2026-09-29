"""Stdio MCP transport for a locally authorized OpenScience project.

Install requirements-mcp.txt in the selected Python environment. The SDK owns
the protocol; this file only forwards typed research operations to CAE-Lab.
"""

import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server.fastmcp import FastMCP

from caelab import Lab


mcp = FastMCP("Autonomous CAE Lab")


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


if __name__ == "__main__":
    mcp.run(transport="stdio")
