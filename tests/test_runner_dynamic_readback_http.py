"""Real HTTP preparation over a retained controlled process failure; no native solve."""
import asyncio
from copy import deepcopy
import json
import os
import shutil
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from apps.lab.service import LabService
from caelab.workbench_client import Client, WorkbenchHTTPError
from test_dynamic_r2_recovery import managed
from test_lab_server import running


def test_http_prepares_exact_source_without_submitting_and_rejects_extra_fields(monkeypatch, tmp_path):
    real_which = shutil.which
    wb, source, calls = managed(monkeypatch, tmp_path, failed=True)
    workspace = wb.workspace
    original = deepcopy(wb.manager.status(source["id"]))
    wb.shutdown()
    # The native double patches the shared shutil module; MCP must find real Python.
    monkeypatch.setattr(shutil, 'which', real_which)
    with running(LabService(workspace)) as transport:
        client = Client(f"http://127.0.0.1:{transport.server.server_port}")
        manager = transport.server.workbench.manager
        before = manager.list()
        arguments = client.dynamic_reprocess_request(source["id"])
        assert set(arguments) == {"source_job_id", "source_record"}
        assert arguments["source_job_id"] == source["id"]
        assert arguments["source_record"]["relative"] == "contact_execution.json"
        assert client.dynamic_reprocess_request(source["id"]) == arguments
        assert manager.list() == before
        assert manager.status(source["id"]) == original

        async def same_mcp_preparation():
            params = StdioServerParameters(command=sys.executable,
                args=['-m', 'openscience.workbench_mcp'],
                env={**os.environ, 'CAELAB_SERVICE_URL': client.url})
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    names = {tool.name for tool in (await session.list_tools()).tools}
                    assert {'dynamic_reprocess_prepare', 'calculation_submit', 'job_status', 'result_read'} <= names
                    for _ in range(2):
                        response = await session.call_tool('dynamic_reprocess_prepare', {'source_job_id': source['id']})
                        assert not response.isError, response.content
                        actual = response.structuredContent or json.loads(response.content[0].text)
                        assert actual == arguments
                    refused = await session.call_tool('dynamic_reprocess_prepare', {'source_job_id': 'Jmissing'})
                    assert refused.isError

        asyncio.run(asyncio.wait_for(same_mcp_preparation(), timeout=35))
        assert manager.list() == before
        assert manager.status(source["id"]) == original
        with pytest.raises(WorkbenchHTTPError) as error:
            client.request("/api/workbench/dynamic-reprocess-request", {
                "source_job_id": source["id"], "output": "UNTRUSTED_OUTPUT"})
        assert error.value.code == 400
        assert manager.list() == before
        assert len(calls) == 1  # Only the controlled initial process, never a readback solve.
