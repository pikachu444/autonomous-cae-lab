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
                        "experiment_run", "experiment_summary"} <= names

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
                print(json.dumps({"mcp_tools": sorted(names), "result": content}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
