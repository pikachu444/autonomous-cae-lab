"""Official MCP SDK transport to an existing, single-owner workbench service.

Set CAELAB_SERVICE_URL; this process never constructs Lab or a job controller.
The same tools can be used by OpenScience or any compatible MCP client.
"""
import os
from typing import Literal
from mcp.server.fastmcp import FastMCP
from caelab.workbench_client import Client

mcp=FastMCP('CAE research workbench')

def client():
    url=os.environ.get('CAELAB_SERVICE_URL')
    if not url:
        raise ValueError('CAELAB_SERVICE_URL must select an existing workbench; start caelab serve first')
    return Client(url)

from caelab.temperature_transfer_mcp import register_transfer_tool
register_transfer_tool(mcp, client)

@mcp.tool()
def backends_list() -> dict:
    """Read registered capabilities without starting a solver."""
    data=client().request('/api/workbench')
    return {'backends':data['backends'],'operations':data['operations'],'workspace_id':data['workspace_id']}

@mcp.tool()
def model_inputs_describe(request: dict) -> dict:
    """Read the chosen adapter's actual input IDs/units/bounds; this is declaration lookup, not an installation probe."""
    return client().describe_inputs(request)

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
def native_project_register(source: dict, command_id: str, replacements: list | None = None) -> dict:
    """Register selected saved native files or a completed native Save; never saves or launches."""
    return client().native_project_register(source, replacements=replacements or (), command_id=command_id)

@mcp.tool()
def native_project_read(reference: dict, facet: str = 'summary') -> dict:
    """Read the exact registered native snapshot; metadata summary is not native open evidence."""
    return client().native_project_read(reference, facet=facet)

@mcp.tool()
def native_project_prepare_open(request: dict, command_id: str) -> dict:
    """Prepare an exact saved import or selected working head; does not launch native software."""
    return client().native_project_prepare_open(request, command_id=command_id)

@mcp.tool()
def native_project_open_ticket(open_id: str) -> dict:
    """Check the current native open request/readback; never launches or adopts caller authority."""
    return client().native_project_open_ticket(open_id)

@mcp.tool()
def native_project_prepare_save(open_id: str, expected_stamp: dict, expected_head: dict | None, command_id: str) -> dict:
    """Reserve a target after human first-Save approval; the existing document.save remains explicit."""
    return client().native_project_prepare_save(open_id, expected_stamp=expected_stamp, expected_head=expected_head, command_id=command_id)

@mcp.tool()
def native_project_save_head(target_id: str, save_command_id: str, expected_head: dict | None,
                             command_id: str, open_id: str | None = None) -> dict:
    """Publish only a verified completed native Save; no native Save or ID allocation retry."""
    return client().native_project_save_head(target_id, save_command_id, expected_head=expected_head, command_id=command_id, open_id=open_id)

@mcp.tool()
def native_input_resolve(input_id: str) -> dict:
    """Resolve a registered native result's verified local path and dependency pins."""
    return client().native_input(input_id)

@mcp.tool()
def documents_list() -> dict:
    """List independent Data/Material/PDE/Numerical/Expert drafts and native Pre/Post documents."""
    return client().documents()

@mcp.tool()
def document_open(kind: str='material', title: str | None=None, draft: dict | None=None, document_id: str | None=None) -> dict:
    """Create/reopen material, data, pde, numerical or expert without execution; native docs open in their host."""
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
    """Read this document's retained import/evaluation/search result without recomputation."""
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
def backend_readiness(backend: str) -> dict:
    """Inspect one registered runtime's existing dependency discovery; no solve, credentials or configuration changes."""
    return client().backend_readiness(backend)

@mcp.tool()
def pre_project(document_id: str, action: str, session_id: str, expected_generation: int,
                command_id: str, input_id: str | None = None, job_id: str | None = None) -> dict:
    """Read/save an editable CAD+Link bundle, open a registered design, or retain an exact design job. Same native GUI owner."""
    operations = {'inspect': 'pre.project.inspect', 'save': 'pre.project.save',
                  'open': 'pre.project.open', 'retain_job': 'pre.links.record'}
    if action not in operations:
        raise ValueError('Choose inspect/save/open/retain_job')
    arguments = {'input_id': input_id} if action == 'open' else {'job_id': job_id} if action == 'retain_job' else {}
    if (action != 'open' and input_id is not None) or (action != 'retain_job' and job_id is not None):
        raise ValueError('Only the selected action accepts its exact registered input/job ID')
    return client().document_command(document_id, operations[action], arguments,
        session_id=session_id, expected_generation=expected_generation, command_id=command_id)

@mcp.tool()
def pre_edit(document_id: str, operation: str, arguments: dict, target: dict,
             session_id: str, expected_generation: int, command_id: str) -> dict:
    """Apply advertised live pre.parameters.*, pre.motion.*, pre.joint.*, pre.assembly.*, pre.fem.* commands. Read the owner's capabilities/selection first; operation receipts are not solver jobs."""
    if not operation.startswith(('pre.parameters.', 'pre.motion.', 'pre.joint.', 'pre.assembly.', 'pre.fem.')):
        raise ValueError('Use an advertised Pre research/Assembly/FEM operation')
    if 'target' in arguments:
        raise ValueError('Target is supplied separately')
    return client().document_command(document_id, operation, {**arguments, 'target': target},
        session_id=session_id, expected_generation=expected_generation, command_id=command_id)

@mcp.tool()
def native_analysis_submit(command_id: str) -> dict:
    """Submit the exact completed pre.freeze command's retained FEM input; identical retries reuse its job."""
    return client().native_submit(command_id)

@mcp.tool()
def native_analysis_open(command_id: str, solver: str | None = None) -> dict:
    """Open the exact completed native export in Simulation; no calculation starts. Retry returns the same document with its edits."""
    return client().native_open_simulation(command_id, solver=solver)

@mcp.tool()
def job_navigation(job_id: str) -> dict:
    """Get this job's original document, retained editable design and verified Post input references."""
    return client().job_navigation(job_id)

@mcp.tool()
def data_source_preview(document_id: str) -> dict:
    """Read a bounded source preview through the Data owner, including its retained source copy."""
    return client().document_source_preview(document_id)

@mcp.tool()
def data_compare(source: dict, prediction_source: dict) -> dict:
    """Compare and retain exact Data/Material/PDE/Simulation curves with explicit units/frame/measure; never rerun a solver."""
    return client().document_compare(source,prediction_source)

@mcp.tool()
def research_compare_curves(source: dict, prediction_source: dict) -> dict:
    """Use the same owner comparison command as the research GUI. Both inputs name exact document/job/response; raw curves and alignment are saved in source's owner."""
    return client().document_compare(source,prediction_source)

@mcp.tool()
def data_comparison_read(document_id: str, comparison_id: str, start: int=0, count: int=4096) -> dict:
    """Read a bounded page of an actual saved comparison including its frozen input identities."""
    return client().document_comparison(document_id,comparison_id,start=start,count=count)

@mcp.tool()
def data_followup(source: dict, kind: str, session_id: str, command_id: str,
                  material_document_id: str | None=None) -> dict:
    """Open an unexecuted Plan for an explicit Material protocol, or an Expert discussion from Data."""
    return client().data_followup(source,kind,session_id=session_id,command_id=command_id,
                                  material_document_id=material_document_id)

@mcp.tool()
def document_result_reference(document_id: str, job_id: str) -> dict:
    """Read a bounded exact retained result reference for later Plan inputs without sending its large table."""
    return client().document_result_reference(document_id,job_id)

@mcp.tool()
def document_result_metadata(document_id: str, job_id: str) -> dict:
    """Read actual scalar/series physical definitions, available reductions and failure counts, without curves."""
    return client().document_result_metadata(document_id,job_id)

@mcp.tool()
def document_response_locations(document_id: str, job_id: str, channel: str,
                                start: int = 0, count: int = 128, search: str = '') -> dict:
    """Page/search every advertised node or Gauss location of one exact retained channel, without sending field arrays."""
    return client().document_response_locations(document_id,job_id,channel,start=start,count=count,search=search)

@mcp.tool()
def result_followup(source_ref: dict, kind: str, session_id: str, command_id: str,
                    request: dict | None=None) -> dict:
    """Create a saved-result discussion or explicit editable request; creation performs no inference/evaluation."""
    return client().result_followup(source_ref,kind,session_id=session_id,command_id=command_id,request=request)

@mcp.tool()
def post_add_result(document_id: str, input_id: str, session_id: str, expected_generation: int,
                    command_id: str, label_text: str | None=None) -> dict:
    """Add a registered VTU/PVD reader to the same native document without replacing its layout/selection."""
    args={'input_id':input_id}
    if label_text is not None: args['label_text']=label_text
    return client().document_command(document_id,'post.source_add',args,session_id=session_id,
                                    expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def post_analysis_edit(document_id: str, kind: str, draft: dict, session_id: str,
                       expected_generation: int, command_id: str, object_ref: str | None=None) -> dict:
    """Edit comparison/filter/measurement in the live owner; invalid drafts remain visible and cannot Apply."""
    if kind not in ('comparison','filter','measurement'):
        raise ValueError('Choose comparison, filter or measurement')
    return client().document_command(document_id,'post.'+kind+'_edit',{'draft':draft,'object_ref':object_ref},
        session_id=session_id,expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def post_analysis_action(document_id: str, action: str, object_ref: str, session_id: str,
                         expected_generation: int, command_id: str, view_id: str | None=None) -> dict:
    """Preview/Apply/Show/Reset/Undo/Redo one owned analysis; an exact native view may overlay actual curves."""
    operations={'preview':'post.mapping_validate','apply':'post.apply','show':'post.show_analysis',
                'reset':'post.reset','undo':'post.undo','redo':'post.redo'}
    if action not in operations: raise ValueError('Choose preview/apply/show/reset/undo/redo')
    args={'object_ref':object_ref}
    if view_id is not None:
        if action not in ('apply','show'): raise ValueError('A target view is used only when applying or showing a result')
        args['view_id']=view_id
    return client().document_command(document_id,operations[action],args,
        session_id=session_id,expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def post_samples(document_id: str, object_ref: str, session_id: str, expected_generation: int,
                 command_id: str, preview: bool=True, offset: int=0, limit: int=100,
                 point_index: int | None=None) -> dict:
    """Read bounded native values/masks; selecting a point retains its exact A/B values and native highlight."""
    return client().document_command(document_id,'post.sample',dict(object_ref=object_ref,preview=preview,
        offset=offset,limit=limit,point_index=point_index),session_id=session_id,
        expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def post_repair_source(document_id: str, source_ref: str, input_id: str, session_id: str,
                        expected_generation: int, command_id: str) -> dict:
    """Repair only an identical registered result/dependency content set at its new location; never relabel changed data."""
    return client().document_command(document_id,'post.source_repair',dict(source_ref=source_ref,input_id=input_id),
        session_id=session_id,expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def simulation_edit(document_id: str, draft: dict, session_id: str, expected_generation: int, command_id: str) -> dict:
    """Edit the actual supported simulation declaration; invalid drafts remain saveable."""
    return client().document_command(document_id,'simulation.update',{'draft':draft},session_id=session_id,
        expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def simulation_run(document_id: str, session_id: str, expected_generation: int, command_id: str) -> dict:
    """Submit exactly the visible simulation input to the existing Runner."""
    return client().document_command(document_id,'simulation.evaluate',{},session_id=session_id,
        expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def evaluation_definition_edit(document_id: str, draft: dict, session_id: str, expected_generation: int, command_id: str) -> dict:
    """Edit ordered stages, declared transfers, bindings, iteration and explicit reuse."""
    return client().document_command(document_id,'evaluation.update',{'draft':draft},session_id=session_id,
        expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def evaluation_definition_inspect(document_id: str) -> dict:
    """Read actual source ports and inputs, including diagnostics for disconnected drafts."""
    return client().evaluation_inspect(document_id)

@mcp.tool()
def evaluation_definition_run(document_id: str, session_id: str, expected_generation: int, command_id: str) -> dict:
    """Run the frozen stages under one existing job; job_cancel stops subsequent stages."""
    return client().document_command(document_id,'evaluation.run',{},session_id=session_id,
        expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def evaluation_progress(document_id: str, job_id: str) -> dict:
    """Read actual attempts/transfers/convergence for the selected evaluation job."""
    return client().evaluation_progress(document_id,job_id)

@mcp.tool()
def evaluation_stage_result(document_id: str, job_id: str, attempt_id: str, selection: dict | None=None) -> dict:
    """Read a bounded selection from this exact retained stage; never rerun it."""
    return client().evaluation_stage_result(document_id,job_id,attempt_id,selection=selection or {'metadata_only':True})

@mcp.tool()
def numerical_evaluation_result(document_id: str, job_id: str, candidate_id: str,
        evaluation_index: int | None=None, attempt_id: str | None=None, selection: dict | None=None) -> dict:
    """Select an actual candidate's retained stage evaluation; omitted index lists existing evaluations."""
    return client().numerical_evaluation_result(document_id,job_id,candidate_id,evaluation_index=evaluation_index,
        attempt_id=attempt_id,selection=(selection or {'metadata_only':True}) if evaluation_index is not None else selection)

@mcp.tool()
def domain_plan_open(document_id: str, session_id: str, expected_generation: int, command_id: str) -> dict:
    """Create the same unexecuted Numerical Plan used by Simulation/Evaluation GUI."""
    return client().domain_plan(document_id,session_id=session_id,expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def study_edit(document_id: str, draft: dict, session_id: str, expected_generation: int, command_id: str) -> dict:
    """Edit question, competing hypotheses, evidence and explicit provisional decisions."""
    return client().document_command(document_id,'study.update',{'draft':draft},session_id=session_id,
        expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def study_references(document_id: str) -> dict:
    """Check the original saved evidence identities without executing research."""
    return client().study_references(document_id)

@mcp.tool()
def research_reference_read(reference: dict) -> dict:
    """Read the selected saved document/result/Expert turn, not its replacement draft."""
    return client().research_reference(reference)

@mcp.tool()
def study_followup(context: dict, kind: str, session_id: str, command_id: str) -> dict:
    """Open the selected saved Study issue in Expert/Numerical without inference or calculation."""
    return client().study_followup(context,kind,session_id=session_id,command_id=command_id)

@mcp.tool()
def pde_edit(document_id: str, draft: dict, session_id: str, expected_generation: int,
             command_id: str | None=None) -> dict:
    """Edit the same opened PDE declaration as the GUI; invalid drafts remain saveable."""
    return client().document_command(document_id,'pde.update',{'draft':draft},session_id=session_id,
        expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def pde_evaluate(document_id: str, session_id: str, expected_generation: int,
                 command_id: str | None=None) -> dict:
    """Freeze the valid PDE input and return its existing managed job; no CAD is required."""
    return client().document_command(document_id,'pde.evaluate',{},session_id=session_id,
        expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def pde_plan_open(document_id: str, session_id: str, expected_generation: int, command_id: str) -> dict:
    """Copy this exact saved PDE input into an editable Numerical request, with no calculation."""
    return client().pde_plan(document_id,session_id=session_id,
        expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def expert_discussion_edit(document_id: str, draft: dict, session_id: str, expected_generation: int,
                           command_id: str | None=None) -> dict:
    """Edit topics, selected registered roles and the exact question/scope on the same owner."""
    return client().document_command(document_id,'expert.update',{'draft':draft},session_id=session_id,
        expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def expert_discussion_control(document_id: str, action: str, session_id: str, expected_generation: int,
                              command_id: str | None=None) -> dict:
    """ask/intervene/pause/resume/advance through the GUI's discussion owner; pause does not cancel calculations."""
    if action not in {'ask','intervene','pause','resume','advance'}:
        raise ValueError('Choose ask, intervene, pause, resume or advance')
    return client().document_command(document_id,'expert.'+action,{},session_id=session_id,
        expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def expert_plan_open(discussion_id: str, turn_id: str, proposal_index: int, session_id: str,
                     command_id: str) -> dict:
    """Open the selected actual proposal as an editable Numerical document; it submits no calculation."""
    return client().discussion_plan(discussion_id,turn_id,proposal_index,
        session_id=session_id,command_id=command_id)

@mcp.tool()
def expert_research_transfer(document_id: str, kind: Literal['study', 'result_review', 'report'],
                             selection: dict, session_id: str, expected_generation: int,
                             command_id: str) -> dict:
    """Open selected claims in Study, an actual result review draft, or a retained Report.

    Use stored selection IDs and the exact current owner session/generation.
    Identical retries keep command_id; this never asks a model or runs a calculation.
    """
    return client().research_team_transfer(document_id,kind,selection,session_id=session_id,
        expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def numerical_plan_edit(document_id: str, draft: dict, session_id: str, expected_generation: int,
                        command_id: str | None=None) -> dict:
    """Edit a Material-bound Plan or actual calculation request; source references are preserved."""
    return client().document_command(document_id,'numerical.update',{'draft':draft},session_id=session_id,
        expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def numerical_plan_run(document_id: str, session_id: str, expected_generation: int,
                       command_id: str | None=None) -> dict:
    """Explicitly submit the frozen current Plan through the existing numerical engine and JobManager."""
    return client().document_command(document_id,'numerical.run',{},session_id=session_id,
        expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def numerical_candidate_adopt(document_id: str, job_id: str, candidate_id: str, material_document_id: str,
                              session_id: str, expected_generation: int, command_id: str) -> dict:
    """Adopt one actual candidate through the original Material owner; reject changed input or stale generation."""
    return client().numerical_adopt(document_id,job_id,candidate_id,material_document_id=material_document_id,
        session_id=session_id,expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def pde_candidate_preview(plan_id: str, job_id: str, candidate_id: str) -> dict:
    """Prepare a reviewable PDE edit from the actual retained candidate and supported native binding; no evaluation."""
    return client().pde_candidate_preview(plan_id,job_id,candidate_id)

@mcp.tool()
def domain_candidate_preview(plan_id: str, job_id: str, candidate_id: str) -> dict:
    """Review actual candidate changes to Simulation or saved Evaluation stage branches."""
    return client().domain_candidate_preview(plan_id,job_id,candidate_id)

@mcp.tool()
def domain_candidate_adopt(plan_id: str, job_id: str, candidate_id: str, target_document_id: str,
        session_id: str, expected_generation: int, command_id: str) -> dict:
    """Explicitly adopt reviewed inputs on their owner. Stage branches preserve the original source documents."""
    return client().domain_candidate_adopt(plan_id,job_id,candidate_id,target_document_id=target_document_id,
        session_id=session_id,expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def pde_candidate_adopt(plan_id: str, job_id: str, candidate_id: str, pde_document_id: str,
                        session_id: str, expected_generation: int, command_id: str) -> dict:
    """Explicitly adopt into the originally bound PDE owner; retain past inputs/results and reject changed target drafts."""
    return client().pde_adopt(plan_id,job_id,candidate_id,pde_document_id=pde_document_id,
        session_id=session_id,expected_generation=expected_generation,command_id=command_id)

@mcp.tool()
def calculation_submit(operation: str, arguments: dict, request_id: str | None=None, resources: dict | None=None) -> dict:
    """Submit a registered calculation/DOE/fit/import/analysis to the shared controller."""
    return client().submit(operation,arguments,request_id=request_id,resources=resources)

@mcp.tool()
def dynamic_reprocess_prepare(source_job_id: str) -> dict:
    """Prepare exact retained terminal native outputs without submission or solver execution.

    After explicit user intent, pass the returned arguments unchanged to
    calculation_submit('dynamic.reprocess', ...), then use the ordinary job tools.
    The new readback job never changes the original execution or its qualification.
    """
    return client().dynamic_reprocess_request(source_job_id)

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
