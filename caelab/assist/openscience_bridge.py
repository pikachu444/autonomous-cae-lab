"""Authenticated, short-lived Streamable HTTP MCP view of one expert turn.

The owning workbench process keeps the approved callbacks and budget. The MCP
SDK handles the wire protocol; this module only exposes the scoped catalog.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import secrets


def make_http_app(catalog, invoke, token):
    from mcp.server.lowlevel import Server
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from mcp.types import Tool, TextContent, CallToolResult
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    server = Server('caelab-scoped-expert')

    @server.list_tools()
    async def list_tools():
        return [Tool(name=row['name'], description=row['description'],
                     inputSchema=row['parameters']) for row in catalog]

    @server.call_tool(validate_input=False)
    async def call_tool(name, arguments):
        try:
            result = await asyncio.to_thread(invoke, name, arguments)
            is_error = False
        except Exception as exc:
            result = {'status': 'TOOL_REJECTED', 'error': type(exc).__name__,
                      'reason': str(exc)}
            is_error = True
        return CallToolResult(content=[TextContent(type='text', text=json.dumps(result, ensure_ascii=False))],
                              isError=is_error)

    manager = StreamableHTTPSessionManager(server, stateless=True, json_response=True,
                                           max_request_body_size=100_000)

    class AuthorizedMCP:
        async def __call__(self, scope, receive, send):
            headers = dict(scope.get('headers', []))
            supplied = headers.get(b'authorization', b'').decode('latin-1')
            if not secrets.compare_digest(supplied, 'Bearer ' + token):
                await JSONResponse({'error': 'Access denied'}, status_code=403)(scope, receive, send)
                return
            await manager.handle_request(scope, receive, send)

    @asynccontextmanager
    async def lifespan(_app):
        async with manager.run():
            yield

    return Starlette(routes=[Route('/mcp', endpoint=AuthorizedMCP(),
                                  methods=['GET', 'POST', 'DELETE'])], lifespan=lifespan)
