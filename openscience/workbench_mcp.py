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
def local_roots_list() -> dict:
    """List existing approved read/snapshot roots; this grants no new file access."""
    return client().local_roots()

@mcp.tool()
def local_files_list(root_id: str, relative: str='', cursor: int=0) -> dict:
    """List a bounded page in an approved root; next_cursor continues the listing."""
    return client().local_inputs(root_id,relative,cursor=cursor)

@mcp.tool()
def local_input_register(root_id: str, relative: str) -> dict:
    """Snapshot a selected file; VTU/PVD registration includes supported dependencies."""
    return client().register_local_input(root_id,relative)

@mcp.tool()
def input_preview(input_id: str) -> dict:
    """Inspect registered data or native-set metadata after checking retained files."""
    return client().input_preview(input_id)

@mcp.tool()
def native_input_resolve(input_id: str) -> dict:
    """Resolve a registered native result's verified local path and dependency pins."""
    return client().native_input(input_id)

@mcp.tool()
def documents_list() -> dict:
    """List service-owned Material drafts and actual registered native documents."""
    return client().documents()

@mcp.tool()
def document_open(kind: str='material', title: str='Material research', draft: dict | None=None, document_id: str | None=None) -> dict:
    """Create or reopen a Material draft without evaluation; Post opens in its native host."""
    return client().document_open(kind=kind,title=title,draft=draft,document_id=document_id)

@mcp.tool()
def document_read(document_id: str) -> dict:
    """Read the owner draft; native state is the last report, use post.inspect for a fresh command."""
    return client().document_read(document_id)

@mcp.tool()
def document_command(document_id: str, operation: str, arguments: dict, session_id: str,
                     expected_generation: int, command_id: str | None=None) -> dict:
    """Apply a typed owner command to the exact session/generation; reuse its ID only for identical retries."""
    return client().document_command(document_id,operation,arguments,session_id=session_id,
                                    expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def document_result_read(document_id: str, job_id: str, selection: dict | None=None) -> dict:
    """Read the Material document's original retained curve and diagnostics, without recomputation."""
    return client().document_result(document_id,job_id,selection=selection)

@mcp.tool()
def hosts_list() -> dict:
    """Inspect native host identity, GUI/headless mode and live connection; never exposes owner tokens."""
    return client().hosts()

@mcp.tool()
def command_status(command_id: str) -> dict:
    """Read a native command outcome; this is separate from calculation job status."""
    return client().command_status(command_id)

@mcp.tool()
def command_cancel(command_id: str) -> dict:
    """Cancel a queued native command; dispatched commands explicitly refuse unsupported cancellation."""
    return client().command_cancel(command_id)

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
