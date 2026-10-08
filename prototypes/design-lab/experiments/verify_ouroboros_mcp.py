"""Bounded read-only probe of the local Ouroboros HTTP MCP host."""
import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main():
    async with streamable_http_client("http://127.0.0.1:8765/mcp") as streams:
        async with ClientSession(streams[0], streams[1]) as client:
            handshake = await client.initialize()
            listing = await client.list_tools()
            names = [tool.name for tool in listing.tools]
            safe = {}
            for tool in listing.tools:
                if tool.name in {"ouroboros_session_status", "ouroboros_project_status", "ouroboros_job_status", "ouroboros_query_events"}:
                    safe[tool.name] = tool.input_schema
            event_probe = await client.call_tool("ouroboros_query_events", {"limit": 1, "offset": 0})
            print(json.dumps({
                "server_name": handshake.server_info.name,
                "server_version": handshake.server_info.version,
                "tool_count": len(names),
                "read_only_schemas": safe,
                "event_query_is_error": event_probe.is_error,
                "event_query_content_blocks": len(event_probe.content),
            }, ensure_ascii=False))


asyncio.run(main())
