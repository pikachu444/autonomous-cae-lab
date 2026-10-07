"""Official MCP SDK transport to an existing, single-owner workbench service.

Set CAELAB_SERVICE_URL; this process never constructs Lab or a job controller.
The same tools can be used by OpenScience or any compatible MCP client.
"""
import os
from mcp.server.fastmcp import FastMCP
from caelab.workbench_client import Client

mcp=FastMCP('CAE research workbench')

def client():
    url=os.environ.get('CAELAB_SERVICE_URL')
    if not url:
        raise ValueError('CAELAB_SERVICE_URL must select an existing workbench; start caelab serve first')
    return Client(url)

@mcp.tool()
def backends_list() -> dict:
    """Read registered capabilities without starting a solver."""
    data=client().request('/api/workbench')
    return {'backends':data['backends'],'operations':data['operations'],'workspace_id':data['workspace_id']}

@mcp.tool()
def calculation_submit(operation: str, arguments: dict, request_id: str | None=None, resources: dict | None=None) -> dict:
    """Submit a registered calculation/DOE/fit/import/analysis to the shared controller."""
    return client().submit(operation,arguments,request_id=request_id,resources=resources)

@mcp.tool()
def job_status(job_id: str) -> dict:
    """Read the same job ID shown by HTTP/GUI, without resubmission."""
    return client().status(job_id)

@mcp.tool()
def job_cancel(job_id: str) -> dict:
    """Request safe cancellation; cancellation requested does not establish process exit."""
    return client().cancel(job_id)

@mcp.tool()
def result_read(job_id: str, responses: list[str] | None=None, selection: dict | None=None) -> dict:
    """Read retained results without solver/AI execution, optionally select responses."""
    if responses is not None and selection is not None:
        raise ValueError('Choose responses or a detailed selection')
    return client().result(job_id,selection=selection if selection is not None else responses)

@mcp.tool()
def knowledge_search(query: str, collections: list[str] | None=None, top_k: int=10) -> dict:
    """Search permitted local original documents with source locators."""
    return client().request('/api/workbench/assist',{'operation':'knowledge.search','arguments':{
        'query':query,'collections':collections,'top_k':top_k}})

@mcp.tool()
def knowledge_source(document_id: str, revision: str | None=None, locator: str | None=None) -> dict:
    """Open an authorized original source; revoked access remains revoked."""
    return client().request('/api/workbench/assist',{'operation':'knowledge.source','arguments':{
        'document_id':document_id,'revision':revision,'locator':locator}})

@mcp.tool()
def literature_search(query: str, providers: list[str] | None=None) -> dict:
    """Explicitly request public literature; return a managed job and actual access status."""
    return client().submit('literature.search',{'query':query,'providers':providers})

@mcp.tool()
def experts_list() -> dict:
    """List configured roles without changing the selected model or authentication."""
    return client().request('/api/workbench/assist',{'operation':'experts.list','arguments':{}})

@mcp.tool()
def expert_ask(expert_id: str, question: str, context: dict | None=None, session_id: str | None=None) -> dict:
    """Ask the selected configured expert as a managed job; no fixed-answer fallback."""
    return client().submit('experts.ask',{'expert_id':expert_id,'question':question,'context':context or {},'session_id':session_id})

@mcp.tool()
def calculations_plan(request: dict) -> dict:
    """Validate an editable numerical plan; planning does not execute it."""
    return client().request('/api/workbench/assist',{'operation':'calculations.plan','arguments':{'request':request}})

if __name__=='__main__':
    mcp.run(transport='stdio')
