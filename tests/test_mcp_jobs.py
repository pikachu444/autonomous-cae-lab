"""Actual stdio job transport, using only Core metadata and preflight refusal."""

import asyncio
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_actual_stdio_submits_inspects_and_lists_without_native_execution(tmp_path):
    root = Path(__file__).resolve().parents[1]
    store = tmp_path / "new-mcp-job-store"

    async def exercise():
        params = StdioServerParameters(command=sys.executable,
            args=[str(root / "openscience/mcp_server.py")],
            env={**os.environ, "CAELAB_STORE": str(store)})
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                names = {tool.name for tool in (await session.list_tools()).tools}
                assert {"research_job_start", "research_job_inspect", "research_jobs_list", "research_job_cancel"} <= names

                async def call(name, arguments):
                    response = await session.call_tool(name, arguments)
                    assert not response.isError, response.content
                    return response.structuredContent or json.loads(response.content[0].text)

                created = await call("research_job_start", {"operation": "study_create", "arguments": {
                    "study_id": "S-stdio-job", "name": "Local job",
                    "research_question": "Are the same Core records retained?", "hypothesis": "Yes",
                    "objective": "Verify metadata transport without a solver"}})
                assert created["status"] == "RUNNING"
                for _ in range(100):
                    job = await call("research_job_inspect", {"job_id": created["id"]})
                    if job["status"] != "RUNNING":
                        break
                    await asyncio.sleep(.02)
                assert job["status"] == "COMPLETED" and job["result"]["id"] == "S-stdio-job"
                assert job["job_control"]["cancel_supported"] is True
                assert job["job_control"]["immediate_stop_guaranteed"] is False
                assert job["job_control"]["completion_is_numerical_pass"] is False
                study = await call("study_inspect", {"study_id": "S-stdio-job"})
                assert study == job["result"]
                listed = await call("research_jobs_list", {})
                assert listed["jobs"][0]["id"] == created["id"]
                late = await call("research_job_cancel", {"job_id": created["id"]})
                assert late["status"] == "COMPLETED" and late["result"] == job["result"]
                unknown = await session.call_tool("research_job_cancel", {"job_id": "J-foreign"})
                assert unknown.isError
                denied = await session.call_tool("research_job_start", {
                    "operation": "shell", "arguments": {"command": "arbitrary command"}})
                assert denied.isError

    asyncio.run(asyncio.wait_for(exercise(), timeout=30))
    assert (store / "studies/S-stdio-job/study.json").is_file()
    assert not (store / "experiments").exists()
