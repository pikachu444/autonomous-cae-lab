"""One additional tool on the existing MCP server, using its Client factory.

No MCP server, owner, solver, provider or scheduler is constructed here.
"""

def register_transfer_tool(mcp, client):
    @mcp.tool()
    def evaluation_transfer_read(document_id: str, job_id: str, transfer_id: str | None = None,
                                 iteration: int | None = None, start: int = 0, count: int = 256) -> dict:
        """Read exact retained source snapshots, receiver values, masks, clocks and failures; never map or solve."""
        return client().evaluation_transfer(document_id, job_id, transfer_id, iteration, start=start, count=count)
