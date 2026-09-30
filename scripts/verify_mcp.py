"""Real local stdio MCP round trip; does not claim a live OpenScience session."""

import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    with tempfile.TemporaryDirectory() as directory:
        server = StdioServerParameters(
            command=sys.executable, args=[str(root / "openscience/mcp_server.py")],
            env={**os.environ, "CAELAB_STORE": directory},
        )
        async with stdio_client(server) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                names = {tool.name for tool in (await session.list_tools()).tools}
                assert {"study_create", "parameters_discover", "parameters_register",
                        "experiment_run", "experiment_summary", "model_native_new",
                        "model_native_import", "model_native_inspect", "model_native_select_final",
                        "analysis_run", "doe_plan", "doe_run", "doe_inspect",
                        "optimization_plan", "optimization_run", "optimization_inspect", "pde_run",
                        "model_analysis_run"} <= names

                async def call(name, arguments):
                    response = await session.call_tool(name, arguments)
                    assert not response.isError, response.content
                    return response

                discovered = await call("parameters_discover",
                                        {"backend": "fixture.cadquery", "model": "roller_support"})
                assert discovered.content
                await call("study_create", {"study_id": "S-MCP", "name": "MCP fixture study",
                            "research_question": "Does width change preserve the CAD rules?",
                            "hypothesis": "38 mm support width is valid", "objective": "Record evidence"})
                await call("parameters_register", {"study_id": "S-MCP", "backend": "fixture.cadquery",
                            "model": "roller_support", "native_path": "support_width_mm",
                            "parameter_id": "support_width", "display_name": "Support width",
                            "lower": 28, "upper": 60})
                await call("experiment_run", {"study_id": "S-MCP", "experiment_id": "E-MCP-valid",
                            "backend": "fixture.cadquery", "model": "roller_support",
                            "values": {"support_width": 38}})
                summary = await call("experiment_summary", {"experiment_id": "E-MCP-valid"})
                content = summary.structuredContent or json.loads(summary.content[0].text)
                assert content["status"] == "COMPLETED_REVIEW_REQUIRED", content
                assert content["decision"] == "NOT_RELEASED"
                assert content["metrics"]["cad_bounds"]["value"][0] == 38
                await call("doe_plan", {"study_id": "S-MCP", "campaign_id": "C-MCP",
                           "backend": "fixture.cadquery", "model": "roller_support",
                           "parameter_ids": ["support_width"], "sample_count": 2, "seed": 13})
                campaign = await call("doe_run", {"campaign_id": "C-MCP"})
                progress = campaign.structuredContent or json.loads(campaign.content[0].text)
                assert len(progress["samples"]) == 2 and progress["decision"] == "NOT_RELEASED"
                checked = await call("doe_inspect", {"campaign_id": "C-MCP"})
                assert (checked.structuredContent or json.loads(checked.content[0].text)) == progress
                await call("optimization_plan", {"study_id": "S-MCP", "campaign_id": "C-MCP-opt",
                           "backend": "fixture.cadquery", "model": "roller_support",
                           "parameter_ids": ["support_width"],
                           "objective": {"source": "cad", "metric": "cad_volume", "unit": "mm^3",
                                         "direction": "minimize"}, "constraints": [], "seed": 13,
                           "max_generations": 1, "population_size": 5,
                           "initial_values": {"support_width": 28}})
                optimized = await call("optimization_run", {"campaign_id": "C-MCP-opt"})
                search = optimized.structuredContent or json.loads(optimized.content[0].text)
                assert search["decision"] == "NOT_RELEASED" and search["incumbent"] is not None
                assert search["evaluations"][0]["cad_status"] == "REJECTED"
                assert search["evaluations"][0]["feedback"]["objective"] is None
                optimized_inspect = await call("optimization_inspect", {"campaign_id": "C-MCP-opt"})
                assert (optimized_inspect.structuredContent or json.loads(optimized_inspect.content[0].text)) == search
                # A real preflight rejection is portable without a FEniCSx installation.
                rejected = await call("pde_run", {"study_id": "S-MCP", "experiment_id": "E-MCP-pde-reject",
                                      "backend": "pde.fenicsx", "settings": {}})
                pde = rejected.structuredContent or json.loads(rejected.content[0].text)
                assert pde["status"] == "REJECTED" and pde["solver_status"] == "NOT_RUN"
                assert pde["decision"] == "NOT_RELEASED" and pde["cad_revision"] is None
                # A declared material/input rejection must also use common records
                # without invoking Code_Aster or inventing a CAD parent.
                from scripts.verify_codeaster import specification
                invalid_model = specification()
                invalid_model["material"]["poisson_ratio"] = .5
                rejected_model = await call("model_analysis_run", {
                    "study_id": "S-MCP", "experiment_id": "E-MCP-model-reject",
                    "backend": "structural.code_aster", "settings": invalid_model})
                independent = rejected_model.structuredContent or json.loads(rejected_model.content[0].text)
                assert independent["status"] == "REJECTED" and independent["solver_status"] == "NOT_RUN"
                assert independent["decision"] == "NOT_RELEASED" and independent["cad_revision"] is None
                print(json.dumps({"mcp_tools": sorted(names), "result": content,
                                  "doe_samples": len(progress["samples"]),
                                  "optimization_evaluations": len(search["evaluations"]),
                                  "pde_preflight": pde["status"],
                                  "model_preflight": independent["status"]}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
