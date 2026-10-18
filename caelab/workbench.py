"""Workspace application services shared by HTTP, CLI and optional MCP/experts."""
from copy import deepcopy
from pathlib import Path
import base64
import json
import re
import uuid
import threading
import io
import hashlib
import unicodedata
from .backends import list_backends, get_backend
from .evaluation import evaluate, run, read_result, file_hash
from .jobs import JobManager
from .storage import save_json, load_json, check_id, utc_now, canonical_hash, revision_read_scope
from .native_inputs import NATIVE_EXTENSIONS, register_native_input, register_frozen_input

INPUT_EXTENSIONS = {'.csv','.txt','.dat','.asc','.npz','.json','.md','.pdf'}

OPERATIONS = {'detail_eval','evaluate','run','import_table','fit','doe','optimize','uq','analyze','compare','event',
              'batch_export','batch_import','remote.run','remote.reconnect','remote.cancel','remote.collect','surrogate','epsilon','sensitivity',
              'sample_sensitivity', 'experiment_uncertainty', 'identification_final',
              'knowledge.ingest','knowledge.rebuild','knowledge.revoke','literature.search','literature.read',
              'literature.import','experts.ask','calculations.plan','pde.evaluate','simulation.run','evaluation.coupled','dynamic.reprocess','impact.reprocess'}


def contained(root, relative):
    if not isinstance(relative,str) or not relative or '\\' in relative or '\x00' in relative:
        raise ValueError('A relative workspace reference is required')
    raw=Path(relative)
    if raw.is_absolute() or '..' in raw.parts:
        raise ValueError('Absolute paths and traversal are not accepted')
    target=(Path(root)/raw).resolve()
    if not target.is_relative_to(Path(root).resolve()):
        raise ValueError('Reference escapes workspace')
    return target


class Workbench:
    def __init__(self, workspace, *, configuration=None, operator_config_path=None):
        candidate = Path(workspace).absolute()
        if (candidate/'portable-project.json').exists() or (candidate/'.incomplete.json').exists():
            from .portable_project import verify_project
            from .portable_project_io import PortableProjectError, Issue
            checked = verify_project(candidate)
            if checked['status'] != 'READY':
                raise PortableProjectError([Issue(**issue) for issue in checked['issues']])
        self._portable_manifest = load_json(candidate/'portable-project.json') if (candidate/'portable-project.json').is_file() else None
        self.workspace=candidate.resolve()
        self.root=self.workspace/'workbench'
        self.root.mkdir(parents=True,exist_ok=True)
        self.config=deepcopy(configuration or {})
        self.workspace_id=self.config.get('workspace_id', (self._portable_manifest or {}).get('knowledge_workspace_id', 'local'))
        if set(self.config.get('external_backends',{})) & {row['id'] for row in list_backends()}:
            raise ValueError('Workspace external backend IDs must not replace global registered backends')
        self.manager=JobManager(self.root,self._execute,workers=self.config.get('workers',2),cpu_budget=self.config.get('cpu_budget'))
        self._assistance=None
        self._assist_config_lock = threading.RLock()
        self._assistance_active = 0
        self._assistance_cleanup_pending = False
        from .expert_connection import bind_operator_config
        bind_operator_config(self, operator_config_path)
        from .material_document import MaterialDocuments
        from .data_document import DataDocuments
        from .numerical_document import NumericalDocuments
        from .pde_document import PDEDocuments
        from .discussion_document import DiscussionDocuments
        from .simulation_document import SimulationDocuments
        from .evaluation_definition import EvaluationDocuments
        from .study_document import StudyDocuments
        from .desktop_links import DesktopLinks
        from .native_commands import NativeCommands
        self.session_id='S'+uuid.uuid4().hex
        self.material_documents=MaterialDocuments(self.root,self.session_id,self.submit,self.manager)
        self.data_documents=DataDocuments(self.root,self.session_id,self.submit,self.manager,
            resolve_input=lambda identifier:(self.input_path(identifier),load_json(self.root/'inputs'/check_id(identifier)/'input.json')))
        self.native_commands=NativeCommands(self.root,self.session_id, private_target_save=self._native_project_target_save)
        self.numerical_documents=NumericalDocuments(self.root,self.session_id,self.submit,self.manager,
            resolve_document=self.document_read, resolve_result=self.document_result,
            resolve_processing=self.data_documents.processing_result,
            prepare_request=self._request_plan_arguments,
            resolve_source_revision=lambda identifier,revision:self._document_owner(identifier)._verify_revision(identifier,revision),
            resolve_pde_revision=lambda identifier,revision:self.pde_documents._verify_revision(identifier,revision))
        self.pde_documents=PDEDocuments(self.root,self.session_id,self.submit,self.manager)
        self.discussion_documents=DiscussionDocuments(self.root,self.session_id,self.submit,self.manager,
            list_experts=lambda:self.assistance_call('experts.list',{}),
            resolve_document=self.document_read,resolve_result=self.document_result,
            resolve_knowledge=lambda reference:self.assistance_call('knowledge.source',reference))
        from .research_team_results import capture_result_verification
        self.discussion_documents.capture_result_verification = lambda ref: capture_result_verification(self, ref)
        from . import research_team_followup
        self.discussion_documents.research_team_transfer_context = lambda doc: research_team_followup.build_transfer_context(self, doc)
        self.simulation_documents=SimulationDocuments(self.root,self.session_id,self.submit,self.manager)
        self.evaluation_documents=EvaluationDocuments(self.root,self.session_id,self.submit,self.manager,
            resolve_revision=lambda identifier,revision:self._document_owner(identifier)._verify_revision(identifier,revision))
        from .research_workflows import reference_metadata
        self.study_documents=StudyDocuments(self.root,self.session_id,self.submit,self.manager,
            resolve_reference=lambda reference:reference_metadata(self,reference))
        from .report_document import ReportDocuments
        self.report_documents = ReportDocuments(self.root, self.session_id, self.submit, self.manager,
            resolve_reference=lambda reference: self.research_reference(reference))
        for owner in (self.study_documents, self.discussion_documents, self.report_documents):
            owner.knowledge_access = lambda reference: self.assistance().knowledge.check_access(
                **reference, workspace_id=self.workspace_id)
            owner.literature_access = lambda reference: self.assistance().literature.read(
                reference['paper_id'], reference['locator'])
        self.desktop=DesktopLinks(self)

    def research_owners(self):
        return (self.material_documents,self.data_documents,self.numerical_documents,
                self.pde_documents,self.discussion_documents,self.simulation_documents,
                self.evaluation_documents,self.study_documents,self.report_documents)

    def documents(self):
        return {'service_session_id':self.session_id,
                'documents':[doc for owner in self.research_owners() for doc in owner.list()]+self.native_commands.documents()}

    def document_open(self, *, kind='material', title=None, draft=None, document_id=None):
        owners={owner.kind:owner for owner in self.research_owners()}
        if kind not in owners:
            raise ValueError('Choose a research document kind; native documents open in their host')
        if title is None:
            title={'material':'Material research','data':'Data research','pde':'PDE research',
                   'numerical':'Numerical Plan','expert':'전문가 토론','simulation':'Simulation research',
                   'evaluation':'Evaluation definition','study':'Study','report':'연구 보고서'}[kind]
        return owners[kind].open(title=title,draft=draft,document_id=document_id)

    def _document_owner(self, identifier):
        check_id(identifier)
        return next((owner for owner in self.research_owners() if identifier.startswith(owner.prefix)),self.native_commands)

    def document_read(self, identifier):
        return self._document_owner(identifier).read(identifier)

    @revision_read_scope()
    def connection_graph(self, document_ids=None, *, include_history=False):
        from .connection_graph import build_graph
        return build_graph(self, document_ids, include_history=include_history)

    @revision_read_scope()
    def connection_catalog(self, target_id):
        from .connection_graph_edit import catalog
        return catalog(self, target_id)

    @revision_read_scope()
    def connection_impact(self, target_id, port):
        from .connection_graph_edit import read_impact
        return read_impact(self, target_id, port)

    @revision_read_scope()
    def connection_preview(self, target, port, action, source=None):
        from .connection_graph_edit import preview_edit
        return preview_edit(self, target, port, action, source)

    def connection_apply(self, proposal, *, confirmed, command_id):
        from .connection_graph_edit import apply_edit
        return apply_edit(self, proposal, confirmed=confirmed, command_id=command_id)

    @revision_read_scope()
    def connection_view_read(self):
        from .connection_graph_view import read_view
        return read_view(self)

    def connection_view_save(self, state, *, scope, expected_revision, expected_sha256, command_id):
        from .connection_graph_view import save_view
        return save_view(self, state, scope=scope, expected_revision=expected_revision,
                         expected_sha256=expected_sha256, command_id=command_id)

    def portable_inspect(self, selections, *, draft_policy='acknowledged', recovery_archives=None):
        from .portable_project import inspect_copy
        return inspect_copy(self, selections, draft_policy=draft_policy, recovery_archives=recovery_archives)

    def portable_recovery_catalog(self, document_ids):
        from .portable_project_recovery import catalog
        return catalog(self, document_ids)

    def portable_recovery_read(self, archive_id, *, facet='layers', selection=None):
        from .portable_project_recovery import read_archive
        return read_archive(self.workspace, archive_id, facet=facet, selection=selection)

    def portable_recovery_preview(self, archive_id, *, target_identity, buffer):
        from .portable_recovery_resume import preview_resume
        return preview_resume(self, archive_id, target_identity=target_identity, buffer=buffer)

    def portable_recovery_resume(self, preview, *, approved, overwrite_approved, live_buffer, command_id):
        from .portable_recovery_resume import resume
        return resume(self, preview, approved=approved, overwrite_approved=overwrite_approved,
                      live_buffer=live_buffer, command_id=command_id)

    def portable_create(self, inspection, destination, *, approved, command_id, session_id):
        from .portable_project import create_copy
        return create_copy(self, inspection, destination, approved=approved,
                           command_id=command_id, session_id=session_id)

    def portable_verify(self, folder):
        from .portable_project import verify_project
        return verify_project(folder)

    def portable_repair(self, folder, relative, replacement, *, approved):
        from .portable_project import repair_asset
        return repair_asset(folder, relative, replacement, approved=approved)

    def backend_readiness(self, backend):
        """Explicit dependency discovery only; never a solver/inference call."""
        from .backends import list_backends
        if not isinstance(backend, str) or backend not in {row['id'] for row in list_backends()}:
            raise ValueError('Choose a registered backend to inspect')
        from .adapters.native_doctor import doctor_native_backend
        inspected = ('pde.fenicsx' if backend in {'thermal.fenicsx.rectangle', 'structural.fenicsx.thermoelastic_rectangle'} else backend)
        result = doctor_native_backend(inspected, execute=False)
        result.update(backend=backend, inspected_runtime=inspected, solver_executed=False,
                      engineering_release='NOT_RELEASED')
        return result

    def document_command(self, identifier, operation, arguments, *, session_id, expected_generation, command_id=None):
        check_id(identifier)
        owner=self._document_owner(identifier)
        from .material_fe_transfer import OPERATIONS as LAW_OPERATIONS, enrich_command
        if owner is self.native_commands and operation in LAW_OPERATIONS:
            previous, arguments = enrich_command(self, identifier, operation, arguments,
                session_id, expected_generation, command_id)
            if previous is not None:
                return previous
        if operation == 'numerical.experiment.preview':
            if owner is not self.numerical_documents:
                raise ValueError('Select a Numerical experiment Plan')
            from .experiment_analysis_service import preview_owner
            return preview_owner(owner, identifier, arguments, session_id=session_id, expected_generation=expected_generation)
        if operation == 'numerical.evidence.adopt':
            from .numerical_candidate_evidence import evidence_adopt_command
            return evidence_adopt_command(self, identifier, arguments, session_id=session_id,
                expected_generation=expected_generation, command_id=command_id)
        if owner is self.native_commands and operation == 'pre.project.open':
            if not isinstance(arguments, dict) or set(arguments) != {'input_id'}:
                raise ValueError('Open native CAD through a registered input ID, not a caller path or receipt')
            receipt = self.native_input(arguments['input_id'])
            if receipt.get('kind') != 'native_design':
                raise ValueError('Select a registered FCStd/CAEPRE editable design')
            arguments = {**arguments, 'receipt': receipt}
        if owner is self.native_commands and operation == 'pre.links.record':
            if not isinstance(arguments, dict) or set(arguments) != {'job_id'}:
                raise ValueError('Retain the exact job ID, not caller-supplied result metadata')
            if command_id:
                # A job may finish between POST and its exact retry. Reuse the
                # already admitted immutable link, not a newer mutable status.
                try:
                    previous = owner.status(command_id)
                except KeyError:
                    previous = None
                if previous is not None:
                    if ((previous['document_id'], previous['operation'], previous['session_id'], previous['expected_generation'])
                            != (identifier, operation, session_id, expected_generation)
                            or previous['arguments'].get('job_id') != arguments['job_id']):
                        raise ValueError('command_id conflicts with an earlier request')
                    return previous
            job = self.desktop.job_record(arguments['job_id'])
            origin = job['arguments'].get('origin', {})
            if origin.get('document_id') != identifier or origin.get('kind') != 'pre':
                raise ValueError('This job belongs to a different native design')
            arguments = {**arguments, 'link': {'job_id': job['id'], 'origin': deepcopy(origin),
                'operation': job['operation'], 'state_when_recorded': job['state'],
                'result_refs': deepcopy(job.get('result_refs', []))}}
        if owner is self.native_commands and operation in {'post.source_add','post.source_repair'}:
            allowed={'input_id','label_text'} if operation=='post.source_add' else {'input_id','source_ref'}
            if not isinstance(arguments,dict) or set(arguments)-allowed or 'input_id' not in arguments:
                raise ValueError('Post source commands require a registered input ID, never a caller-supplied path or receipt')
            arguments={**arguments,'receipt':self.native_input(arguments['input_id'])}
            if (arguments['receipt'].get('format') not in {'vtu','pvd'}
                    and not (arguments['receipt'].get('format') == 'vtt' and arguments['receipt'].get('kind') == 'native_curve')):
                raise ValueError('Post readers currently admit registered VTU/PVD result sets')
        method=owner.submit if owner is self.native_commands else owner.command
        if owner is self.native_commands and operation in {'document.save', 'pre.project.save'} and command_id:
            # Keep admission and its absence proof under the existing registry
            # RLock. A queued/persisted operation is never released or replayed.
            with owner._lock:
                try:
                    return method(identifier,operation,arguments,session_id=session_id,
                                  expected_generation=expected_generation,command_id=command_id)
                except ValueError as error:
                    record_path = owner.root / (check_id(command_id) + '.json')
                    if (arguments != {} or command_id in owner._commands
                            or record_path.exists() or record_path.is_symlink()):
                        raise
                    from .native_project_inputs import (context_from_workbench,
                        resolve_target_save_command, _record_target_save_failure)
                    context = context_from_workbench(self)
                    matches = [binding for binding, _ in context.target_saves.values()
                               if binding.save_command_id == command_id]
                    if len(matches) != 1:
                        raise
                    try:
                        reserved = resolve_target_save_command(context, command_id)
                        document = owner.read(identifier)
                        exact = (type(expected_generation) is int and reserved == matches[0]
                            and reserved.owner_document_id == identifier
                            and reserved.expected_stamp['session_id'] == session_id
                            and reserved.expected_stamp['generation'] == expected_generation
                            and document.get('connected')
                            and document.get('session_id') == session_id
                            and document.get('service_session_id') == self.session_id
                            and document.get('kind') == reserved.expected_stamp['kind'])
                        if not exact:
                            raise ValueError('The rejected request is not the exact current Save reservation')
                        _record_target_save_failure(context, reserved, error, stage='before_save')
                    except (KeyError, ValueError, FileNotFoundError):
                        # Missing/changed permission or reservation is UNKNOWN;
                        # preserve it and the original refusal without release.
                        raise error
                    return owner._record_not_dispatched_save_failure(identifier, operation, arguments,
                        session_id=session_id, expected_generation=expected_generation,
                        command_id=command_id, error=error)
        return method(identifier,operation,arguments,session_id=session_id,
                      expected_generation=expected_generation,command_id=command_id)

    def document_result(self, identifier, job_id, *, selection=None):
        owner=self._document_owner(identifier)
        if owner is self.native_commands:
            raise ValueError('Native documents expose their results in the native host')
        return owner.result(identifier,job_id,selection=selection)

    def document_result_reference(self, identifier, job_id):
        from .research_operations import result_reference
        return result_reference(self.document_read(identifier),job_id,self.document_result(identifier,job_id))

    def document_result_metadata(self, identifier, job_id):
        from .research_operations import result_metadata
        from .research_team_results import describe_result_selection
        metadata = result_metadata(self.document_result(identifier,job_id,selection={'metadata_only': True}))
        metadata['research_team_descriptor'] = describe_result_selection(self, identifier, job_id)
        return metadata

    def research_team_transfer(self, document_id, kind, selection, *, session_id, expected_generation, command_id):
        """Open selected research in an existing editor without starting inference."""
        from .research_team_followup import transfer
        return transfer(self, document_id, kind, selection, session_id=session_id,
                        expected_generation=expected_generation, command_id=command_id)

    def document_response_locations(self, identifier, job_id, channel, *, start=0, count=128, search=''):
        from .research_operations import response_locations
        result = self.document_result(identifier, job_id, selection={'metadata_only': True})
        return response_locations(result, channel, start=start, count=count, search=search) | {
            'document_id': identifier, 'job_id': job_id}

    def constitutive_inspect(self, document_id, job_id, increment=0):
        from .constitutive_inspection import inspect_constitutive
        return inspect_constitutive(self, document_id, job_id, increment)

    def evaluation_transfer(self, document_id, job_id, transfer_id=None, iteration=None, *, start=0, count=256):
        from .transfer_inspection import inspect_transfer
        return inspect_transfer(self, document_id, job_id, transfer_id, iteration, start=start, count=count)

    def evaluation_inspect(self, identifier):
        return self.evaluation_documents.inspect_definition(identifier)

    def evaluation_progress(self, identifier, job_id):
        from .research_workflows import evaluation_progress
        return evaluation_progress(self,identifier,job_id)

    def evaluation_stage_result(self, identifier, job_id, attempt_id, *, selection=None):
        from .research_workflows import evaluation_stage_result
        return evaluation_stage_result(self,identifier,job_id,attempt_id,selection)

    def numerical_evaluation_result(self, identifier, job_id, candidate_id, *, evaluation_index=None, attempt_id=None, selection=None):
        from .research_workflows import numerical_evaluation_result
        return numerical_evaluation_result(self,identifier,job_id,candidate_id,
            evaluation_index=evaluation_index,attempt_id=attempt_id,selection=selection)

    def numerical_candidate_detail(self, document_id, job_id, candidate_id, *, attempt_job_id=None, source=None):
        from .numerical_candidate_detail import read_candidate_detail
        return read_candidate_detail(self.numerical_documents, document_id, job_id, candidate_id,
                                     attempt_job_id=attempt_job_id, source=source)

    def domain_candidate_preview(self, plan_id, job_id, candidate_id):
        from .domain_candidate import preview
        return preview(self,plan_id,job_id,candidate_id)

    def domain_candidate_adopt(self, plan_id, job_id, candidate_id, *, target_document_id,
                               session_id, expected_generation, command_id, detail_evidence=None):
        from .domain_candidate import adopt
        return adopt(self,plan_id,job_id,candidate_id,target_document_id=target_document_id,
            session_id=session_id,expected_generation=expected_generation,command_id=command_id,
            detail_evidence=detail_evidence)

    def study_references(self, identifier):
        return self.study_documents.resolve_references(identifier)

    def report_capture(self, document_id, reference):
        if isinstance(reference, dict) and reference.get('kind') == 'post_image_command':
            if set(reference) != {'kind', 'command_id'}:
                raise ValueError('보고서 캡처는 완료된 Post 명령만 선택합니다.')
            command = self.native_commands.status(check_id(reference['command_id']))
            return self.report_documents.capture_image(check_id(document_id), command)
        from .experiment_analysis_service import validate_report_capture
        validate_report_capture(self, reference)
        return self.report_documents.capture(check_id(document_id), reference)

    def report_content(self, document_id, assets):
        return self.report_documents.content(check_id(document_id), assets)

    def research_reference(self, reference):
        from .research_workflows import resolve_reference
        return resolve_reference(self,reference)

    def post_measurement_preview(self, command_id):
        from .post_numerical import preview
        return preview(self, command_id)

    def post_measurement_plan(self, command_id, selection, *, session_id, handoff_id, target_plan_id=None):
        from .post_numerical import prepare
        return prepare(self, command_id, selection, session_id=session_id, handoff_id=handoff_id, target_plan_id=target_plan_id)

    def post_observation(self, reference):
        from .post_numerical import observation
        return observation(self, reference)

    def document_source_preview(self, identifier):
        if self._document_owner(identifier) is not self.data_documents:
            raise ValueError('Source preview belongs to a Data document')
        return self.data_documents.source_preview(identifier)

    def document_source_table(self, identifier, *, start=0, count=4096):
        if self._document_owner(identifier) is not self.data_documents:
            raise ValueError('Source table belongs to a Data document')
        return self.data_documents.source_table(identifier, start=start, count=count)

    def post_curve_snapshot(self, reference, response):
        """Freeze a retained Data channel for the existing native Post owner."""
        from .post_curves import snapshot
        return snapshot(self, reference, response)

    def _curve_reference(self, reference):
        if (not isinstance(reference,dict) or not {'document_id','job_id','response'} <= set(reference)
                or set(reference)-{'document_id','job_id','response','input_revision','input_sha256'}):
            raise ValueError('Choose an exact document, job and response channel')
        document=self.document_read(check_id(reference['document_id']))
        run=next((row for row in document.get('runs',[]) if row['job_id']==reference['job_id']),None)
        if run is None or any(key in reference and reference[key]!=run[key] for key in ('input_revision','input_sha256')):
            raise ValueError('Selected curve differs from its submitted document input')
        name=reference['response']
        if not isinstance(name,str) or not name:
            raise ValueError('Select an explicitly named response')
        result=self.document_result(document['id'],reference['job_id'],selection=[name])
        if result.get('execution_status')!='SUCCEEDED':
            raise ValueError('A failed or missing evaluation cannot supply a comparison curve')
        response=result['responses'][name]
        binding={**reference,'input_revision':run['input_revision'],'input_sha256':run['input_sha256'],
                 'response_sha256':canonical_hash(response)}
        return document,run,response,binding

    def document_compare(self, source, prediction_source):
        from .data_comparison import compare_data_curves
        document,_,observation,observed=self._curve_reference(source)
        if document.get('kind') not in {'data', 'material', 'pde', 'simulation'}:
            raise ValueError('Retained curve comparison belongs to a Data, Material, PDE or Simulation document')
        _,_,prediction,predicted=self._curve_reference(prediction_source)
        comparison=compare_data_curves(prediction,observation)
        return self._document_owner(document['id']).retain_comparison(document['id'],{
            'binding':{'source':observed,'prediction_source':predicted},
            'comparison':comparison,'input_curves':{'observation':observation,'prediction':prediction}})

    def upload(self, name, payload):
        if not isinstance(payload,bytes) or not payload or len(payload)>16*1024*1024:
            raise ValueError('Upload must contain 1 byte to 16 MiB')
        return self._store_input(name, io.BytesIO(payload), len(payload))

    def _store_input(self, name, stream, length, *, origin=None):
        if (not isinstance(name,str) or not 1 <= len(name) <= 240 or name in {'.','..'}
                or any(char in '/\\:\x00' or unicodedata.category(char).startswith('C') for char in name)):
            raise ValueError('A plain filename is required')
        suffix=Path(name).suffix.lower()
        if suffix not in INPUT_EXTENSIONS:
            raise ValueError('Unsupported data/document extension')
        identifier='D'+uuid.uuid4().hex
        folder=self.root/'inputs'/identifier
        folder.mkdir(parents=True)
        path=folder/('source'+suffix)
        digest=hashlib.sha256()
        total=0
        with path.open('xb') as destination:
            while chunk := stream.read(min(1024*1024, length-total+1)):
                total+=len(chunk)
                if total>length:
                    raise ValueError('Source length changed during registration')
                digest.update(chunk)
                destination.write(chunk)
        if total!=length:
            raise ValueError('Source length changed during registration')
        receipt={'id':identifier,'name':name,'file':path.relative_to(self.root).as_posix(),
                 'bytes':total,'sha256':digest.hexdigest(),'created_utc':utc_now()}
        if origin:
            receipt['origin']=origin
        save_json(folder/'input.json',receipt)
        return receipt

    def local_roots(self):
        return {'workspace_id': self.workspace_id, 'roots': [
            {'id': identifier, 'access': 'read_and_snapshot',
             'extensions': sorted(INPUT_EXTENSIONS | NATIVE_EXTENSIONS)}
            for identifier in self.config.get('input_roots', {})]}

    def local_inputs(self, root_id, relative='', *, cursor=0):
        if type(cursor) is not int or cursor < 0:
            raise ValueError('File cursor must be a nonnegative integer')
        roots=self.config.get('input_roots',{})
        if root_id not in roots:
            raise ValueError('Select an operator-approved input root')
        root=Path(roots[root_id]).resolve()
        directory=contained(root,relative) if relative else root
        if not directory.is_dir():
            raise ValueError('Input directory is unavailable')
        entries=[]
        skipped=0
        for item in sorted(directory.iterdir(),key=lambda p:(not p.is_dir(),p.name.casefold())):
            if not item.resolve().is_relative_to(root):
                continue
            if item.is_dir() or item.suffix.lower() in INPUT_EXTENSIONS | NATIVE_EXTENSIONS:
                if skipped < cursor:
                    skipped+=1
                    continue
                entries.append({'name':item.name,'relative':item.relative_to(root).as_posix(),
                                'directory':item.is_dir(),'bytes':None if item.is_dir() else item.stat().st_size,
                                'modified_ns':item.stat().st_mtime_ns})
            if len(entries)>200:
                break
        return {'root_id':root_id,'relative':relative,'entries':entries[:200],'limit':200,
                'next_cursor':cursor+200 if len(entries)>200 else None}

    def register_local_input(self, root_id, relative):
        roots=self.config.get('input_roots',{})
        if root_id not in roots:
            raise ValueError('Select an operator-approved input root')
        source=contained(Path(roots[root_id]),relative)
        limit=self.config.get('local_input_max_bytes',2*1024**3)
        if type(limit) is not int or limit<1:
            raise ValueError('local_input_max_bytes must be a positive integer')
        if source.name == 'beam_inspection.json':
            from .beam_inspection import explicit_manifest
            entry, metadata = explicit_manifest(source)
            return register_native_input(self.root, roots[root_id], entry, 'D'+uuid.uuid4().hex,
                root_id=root_id, relative=relative, limit=limit, native_metadata=metadata)
        if source.name == 'composite_inspection.json':
            from .composite_shell_results import explicit_manifest
            entry, metadata = explicit_manifest(source)
            return register_native_input(self.root, roots[root_id], entry, 'D'+uuid.uuid4().hex,
                root_id=root_id, relative=relative, limit=limit, native_metadata=metadata)
        if source.name == 'shell_inspection.json':
            from .shell_inspection import explicit_manifest
            entry, metadata = explicit_manifest(source)
            return register_native_input(self.root, roots[root_id], entry, 'D'+uuid.uuid4().hex,
                root_id=root_id, relative=relative, limit=limit, native_metadata=metadata)
        if source.name == 'contact-inspection.json':
            from .contact_inspection import explicit_manifest
            entry, metadata = explicit_manifest(source)
            return register_native_input(self.root, roots[root_id], entry, 'D'+uuid.uuid4().hex,
                root_id=root_id, relative=relative, limit=limit, native_metadata=metadata)
        if source.suffix.lower() in NATIVE_EXTENSIONS:
            return register_native_input(self.root, roots[root_id], source, 'D'+uuid.uuid4().hex,
                root_id=root_id, relative=relative, limit=limit)
        if source.name == 'snapshot.json':
            return register_frozen_input(self.root, roots[root_id], source, 'D'+uuid.uuid4().hex,
                root_id=root_id, relative=relative, limit=limit)
        with source.open('rb') as stream:
            import os
            before=os.fstat(stream.fileno())
            if not 0<before.st_size<=limit:
                raise ValueError(f'Local input must contain 1 byte to {limit} bytes')
            receipt=self._store_input(source.name,stream,before.st_size,
                origin={'mode':'LOCAL_SNAPSHOT','root_id':root_id,'relative':relative})
            after=os.fstat(stream.fileno())
            current=source.stat()
            identity=lambda stat:(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns)
            if identity(before)!=identity(after) or identity(after)!=identity(current):
                # Retain partial bytes for diagnosis, but do not advertise an
                # input whose source changed while it was being copied.
                (self.root/'inputs'/receipt['id']/'input.json').unlink()
                raise ValueError('Source changed during local registration; retry when writing has finished')
        return receipt

    def inputs(self):
        return [load_json(path) for path in sorted((self.root/'inputs').glob('*/input.json'))]

    def input_path(self, identifier):
        check_id(identifier)
        receipt=load_json(self.root/'inputs'/identifier/'input.json')
        if receipt.get('native_project') is not None:
            from .native_project_inputs import context_from_workbench, registered_input
            return registered_input(context_from_workbench(self), identifier, full=True).entry_path
        path=contained(self.root,receipt['file'])
        if file_hash(path)!=receipt['sha256']:
            raise ValueError('Uploaded source changed')
        if receipt.get('kind') in {'native_result', 'native_design', 'frozen_fem', 'frozen_contact', 'frozen_shell', 'frozen_composite_shell', 'frozen_beam', 'frozen_connector', 'native_curve'}:
            folder=(self.root/'inputs'/identifier).resolve()
            files=receipt.get('files',[])
            if not files or not any(item.get('file')==receipt['file'] and item.get('sha256')==receipt['sha256'] for item in files):
                raise ValueError('Native input set has no pinned entry file')
            if (receipt.get('native_metadata') or {}).get('dynamic_locations') is not None:
                metadata = receipt['native_metadata']
                if canonical_hash(metadata) != receipt.get('native_metadata_sha256'):
                    raise ValueError('Registered native field metadata changed')
                from .dynamic_locations import verify_saved_source
                verify_saved_source(path, metadata, receipt.get('origin'),
                    [{'path': str(contained(self.root,item['file'])), 'bytes': item['bytes'],
                      'sha256': item['sha256']} for item in files])
                return path  # selected-scope admission; no full frame-byte scan
            for item in files:
                dependency=contained(self.root,item['file'])
                if not dependency.is_relative_to(folder) or dependency.stat().st_size!=item['bytes'] or file_hash(dependency)!=item['sha256']:
                    raise ValueError('Registered native input or dependency changed')
        return path

    def native_input(self, identifier):
        """Resolve a registered native set for a local reader after verification."""
        path = self.input_path(identifier)
        receipt = load_json(self.root/'inputs'/identifier/'input.json')
        if receipt.get('native_project') is not None:
            from .native_project_inputs import context_from_workbench, registered_input
            verified = registered_input(context_from_workbench(self), identifier, full=True)
            return {'id': identifier, 'path': str(verified.entry_path), 'kind': receipt['kind'],
                'format': receipt['format'], 'sha256': receipt['sha256'],
                'source_pins': [{'path': str(verified.member_paths[m['id']]), 'bytes': m['bytes'], 'sha256': m['sha256']}
                                for m in verified.snapshot['members'] if m['storage'] == 'file'],
                'files': [{'path': str(verified.member_paths[m['id']]), 'relative': m['relative'],
                           'bytes': m['bytes'], 'sha256': m['sha256']}
                          for m in verified.snapshot['members'] if m['storage'] == 'file'],
                'registration_origin': deepcopy(receipt.get('origin')), 'native_reference': deepcopy(verified.reference)}
        if receipt.get('kind') not in {'native_result', 'native_design', 'frozen_fem', 'frozen_contact', 'frozen_shell', 'frozen_composite_shell', 'frozen_beam', 'frozen_connector', 'native_curve'}:
            raise ValueError('Select a registered native result or FEM snapshot')
        result = {'id': identifier, 'path': str(path), 'format': receipt['format'], 'kind': receipt['kind'], 'sha256': receipt['sha256'],
                'source_pins': [{'path': str(contained(self.root, item['file'])),
                                 'bytes': item['bytes'], 'sha256': item['sha256']}
                                for item in receipt['files']]}
        result['registration_origin'] = deepcopy(receipt.get('origin'))
        if receipt.get('candidate_branch'):
            result['candidate_branch'] = deepcopy(receipt['candidate_branch'])
        if receipt['kind'] in {'frozen_fem', 'frozen_contact', 'frozen_shell', 'frozen_composite_shell', 'frozen_beam', 'frozen_connector'}:
            manifest = load_json(path)
            result['editable_path'] = str(path.parent / manifest.get('editable_project', 'editable.FCStd'))
        if receipt['kind'] == 'native_design':
            result['files'] = [{'path': str(contained(self.root, item['file'])),
                               'relative': item['relative'], 'sha256': item['sha256'], 'bytes': item['bytes']}
                              for item in receipt['files']]
        if receipt.get('native_metadata') is not None:
            if canonical_hash(receipt['native_metadata']) != receipt.get('native_metadata_sha256'):
                raise ValueError('Registered native field metadata changed')
            result['native_metadata'] = deepcopy(receipt['native_metadata'])
        return result

    def native_project_register(self, source, *, replacements=(), command_id):
        from .native_project_inputs import context_from_workbench, register_saved, resolve_completed_command
        context = context_from_workbench(self, resolve_completed_save=lambda identifier: resolve_completed_command(self, identifier))
        return register_saved(context, source, replacements=replacements, command_id=command_id)

    def native_project_read(self, reference, *, facet='summary'):
        from .native_project_inputs import context_from_workbench, read_registered
        return read_registered(context_from_workbench(self), reference, facet=facet)

    def native_project_prepare_open(self, request, *, command_id):
        from .native_project_inputs import context_from_workbench
        from .portable_project_native import prepare_open, open_ticket_view
        context = context_from_workbench(self)
        if request.get('intent') == 'working':
            from .portable_project_native import _target
            if set(request) != {'reference', 'intent', 'target_id', 'expected_head', 'selection', 'allow_partial'}:
                raise ValueError('현재 작업 사본의 정확한 열기 요청을 선택하세요.')
            check_id(command_id)
            target, head, verified = _target(context, request['target_id'])
            if (request['reference'] != head['reference'] or request['expected_head'] !=
                    {'generation': head['head_generation'], 'reference': head['reference']}):
                raise ValueError('STALE_TARGET: 현재 저장본을 다시 선택하세요.')
            if type(request['allow_partial']) is not bool or (not request['allow_partial'] and
                    verified.snapshot['validation']['closure'] != 'COMPLETE'):
                raise ValueError('일부 자료가 없는 작업 사본의 열기를 명시적으로 확인하세요.')
            try:
                owner = self.native_commands.read(target['working_document_id'])
            except KeyError:
                owner = None
            if owner is not None and owner.get('owner_closed'):
                owner = None  # Authenticated native close permits a new explicit open.
            if owner is not None:
                # A live window owns its edits. Reuse only its current exact
                # ticket; missing evidence is not permission for a new launch.
                open_id = owner.get('native_open_id')
                if request['selection'] is not None:
                    return {'status': 'OPEN_UNCONFIRMED', 'open_id': open_id,
                        'reference': deepcopy(request['reference']), 'owner_document_id': target['working_document_id'],
                        'target_id': target['target_id'],
                        'message': '현재 창의 선택 대상을 확인할 수 없습니다. 저장본을 별도 창에서 여세요.'}
                try:
                    view = self.native_project_open_ticket(open_id)
                    ticket = context.tickets[open_id]
                    if (view['status'] not in {'OPENED', 'PARTIAL_OPEN'} or
                            view['target_id'] != target['target_id'] or
                            view['owner_document_id'] != target['working_document_id'] or
                            owner.get('native_target_id') != target['target_id'] or
                            Path(owner.get('native_working_root', '')).resolve() != ticket.binding.materialization_root.resolve()):
                        raise ValueError('현재 창과 선택한 작업 사본의 대응을 확인할 수 없습니다.')
                except (KeyError, TypeError, ValueError):
                    return {'status': 'OPEN_UNCONFIRMED', 'open_id': open_id,
                        'reference': deepcopy(request['reference']), 'owner_document_id': target['working_document_id'],
                        'target_id': target['target_id'], 'message': '이미 열린 작업 창의 연결을 먼저 확인하세요.'}
                return {**view, 'reuse_existing': True, 'request_reference': deepcopy(request['reference']),
                    'expected_stamp': {key: owner.get('id' if key == 'document_id' else key) for key in
                        ('document_id', 'kind', 'session_id', 'generation', 'view_generation', 'saved_revision', 'graph_version')}}
        ticket = prepare_open(context, request, command_id=command_id)
        view = open_ticket_view(context, ticket.binding.open_id)
        return {key: view[key] for key in ('status', 'open_id', 'reference', 'owner_document_id',
            'target_id', 'local_save_state', 'warnings', 'effects')}

    def native_project_open_ticket(self, open_id):
        from .native_project_inputs import context_from_workbench
        from .portable_project_native import open_ticket_view
        view = open_ticket_view(context_from_workbench(self), open_id)
        if view['status'] == 'OPENED':
            readback = view['readback']
            # Query the exact readback session, even after another explicit
            # open has created a new owner session for the same working ID.
            owner = next((item for item in self.native_commands.documents()
                if item['id'] == view['owner_document_id']
                and item.get('session_id') == readback.get('native_owner_session')
                and item.get('service_session_id') == self.session_id), {})
            if owner.get('owner_closed') and owner.get('kind') == view['native_kind']:
                view['status'] = 'CLOSED'
            elif not (owner.get('connected') and owner.get('kind') == view['native_kind']
                    and owner.get('session_id') == readback.get('native_owner_session')
                    and owner.get('service_session_id') == self.session_id
                    and owner.get('native_open_id') == open_id
                    and owner.get('native_target_id') == view['target_id']
                    and Path(owner.get('native_working_root', '')).resolve() ==
                        context_from_workbench(self).tickets[open_id].binding.materialization_root.resolve()):
                view['status'] = 'OPEN_UNCONFIRMED'
            elif readback.get('status') == 'PARTIAL_OPEN':
                view['status'] = 'PARTIAL_OPEN'
        return view

    def native_project_prepare_save(self, open_id, *, expected_stamp, expected_head, command_id):
        from .native_project_inputs import context_from_workbench, prepare_target_save
        owner = self.native_commands.read(expected_stamp['document_id'])
        current = {key: owner.get('id' if key == 'document_id' else key) for key in
            ('document_id', 'kind', 'session_id', 'generation', 'view_generation', 'saved_revision', 'graph_version')}
        if not owner.get('connected') or current != expected_stamp:
            raise ValueError('STALE_DOCUMENT: 현재 native 문서의 저장 기준을 다시 확인하세요.')
        reservation = prepare_target_save(context_from_workbench(self), open_id,
            expected_stamp=expected_stamp, expected_head=expected_head, command_id=command_id)
        return {'status': 'SAVE_PREPARED', **{key: deepcopy(getattr(reservation, key)) for key in
            ('save_id', 'save_command_id', 'open_id', 'owner_document_id', 'target_id', 'expected_head')},
            'effects': {'native_save': False, 'head_published': False}}

    def native_project_save_head(self, target_id, save_command_id, *, expected_head, command_id, open_id=None):
        from .native_project_inputs import (context_from_workbench, resolve_target_save_command,
            resolve_completed_command, publish_head)
        context = context_from_workbench(self)
        reservation = resolve_target_save_command(context, save_command_id)
        if (reservation.target_id != target_id or reservation.expected_head != expected_head
                or (open_id is not None and reservation.open_id != open_id)
                or (expected_head is None and open_id != reservation.open_id)):
            raise ValueError('STALE_TARGET: 완료한 저장과 원 작업 대상을 다시 확인하세요.')
        witness = resolve_completed_command(self, save_command_id)
        return publish_head(context, target_id, witness, expected_head=expected_head,
            command_id=command_id, _target_save=reservation)

    def _native_project_target_save(self, request, document):
        if request['operation'] not in {'document.save', 'pre.project.save'}:
            return None
        from .native_project_inputs import context_from_workbench, resolve_target_save_command
        context = context_from_workbench(self)
        if not any(binding.save_command_id == request['command_id'] for binding, _ in context.target_saves.values()):
            return None  # Ordinary native Save keeps the existing path.
        stamp = {key: document.get('id' if key == 'document_id' else key) for key in
            ('document_id', 'kind', 'session_id', 'generation', 'view_generation', 'saved_revision', 'graph_version')}
        reservation = resolve_target_save_command(context, request['command_id'], stamp)
        if (request['document_id'] != reservation.owner_document_id
                or request['session_id'] != reservation.expected_stamp['session_id']
                or request['expected_generation'] != reservation.expected_stamp['generation']
                or request['arguments']):
            raise ValueError('STALE_DOCUMENT: 예약한 native 저장 요청이 변경되었습니다.')
        return {'prepare_command_id': context.target_saves[reservation.save_id][1],
            'save_command_id': reservation.save_command_id, 'open_id': reservation.open_id}

    def input_preview(self,identifier):
        path=self.input_path(identifier)
        receipt=load_json(self.root/'inputs'/identifier/'input.json')
        if receipt.get('native_project') is not None:
            from .native_project_inputs import context_from_workbench, registered_input, read_registered
            context = context_from_workbench(self)
            verified = registered_input(context, identifier, full=True)
            return {'id': identifier, 'name': receipt['name'], 'kind': receipt['kind'], 'format': receipt['format'],
                    **read_registered(context, verified.reference)}
        if receipt.get('kind') in {'frozen_fem', 'frozen_contact', 'frozen_shell', 'frozen_composite_shell', 'frozen_beam', 'frozen_connector'}:
            return {'id':identifier,'kind':receipt['kind'],'format':receipt['format'],
                    'name':receipt['name'],'file_count':len(receipt['files']),
                    'bytes':receipt['total_bytes'],'sha256':receipt['sha256'],
                    'preview':'Frozen editable CAD, existing FEM mesh and native solver input'}
        if path.suffix.lower() in NATIVE_EXTENSIONS:
            receipt=load_json(self.root/'inputs'/identifier/'input.json')
            return {'id':identifier,'kind':receipt['kind'],'format':receipt['format'],
                    'name':receipt['name'],'file_count':len(receipt['files']),
                    'bytes':receipt['total_bytes'],'sha256':receipt['sha256'],
                    'preview':('Editable CAD snapshot with registered dependencies; open in Pre' if receipt['kind'] == 'native_design'
                               else 'Native result snapshot; open in Post to inspect fields and time steps')}
        if path.suffix in {'.pdf','.npz'}:
            return {'id':identifier,'kind':path.suffix,'preview':'Binary input; select a document or numeric reader'}
        with path.open(encoding='utf-8-sig') as stream:
            sample=stream.read(16385)
        truncated=len(sample)>16384
        text=sample[:16384]
        result={'id':identifier,'text':text,'truncated':truncated}
        if path.suffix in {'.csv','.txt','.dat','.asc'}:
            from .adapters.file_table import preview_table
            table=preview_table(text,truncated=truncated)
            if table is not None:
                result['table_preview']=table
        return result

    def backends(self):
        return list_backends()+[{'id':'evaluation.definition','roles':['prepared'], 'source':'service',
            'native_runtime':None,'threads':1,'readiness':'NOT_PROBED'}]+[{'id':identifier,'roles':['external'],'native_runtime':config.get('label','Operator-registered program'),
            'threads':config.get('threads',1),'source':'workspace','readiness':'EXECUTION_NOT_TESTED'}
            for identifier,config in self.config.get('external_backends',{}).items()]

    def overview(self):
        return {'workspace_id':self.workspace_id,'backends':self.backends(),
                'inputs':self.inputs(),'jobs':self.manager.list(),
                'input_roots':list(self.config.get('input_roots',{})),
                'assistance':{'configured':bool(self.config.get('runtime'))},
                'operations':sorted(OPERATIONS)}

    def result(self, identifier, *, selection=None):
        identifier=check_id(identifier)
        if not (self.root/'results'/identifier/'result.json').is_file():
            match=self.desktop.research_job(identifier)
            if match and match[2].get('retained_result'):
                return match[0].result(match[1]['id'],identifier,selection=selection)
        job = self.manager.status(identifier)
        if job.get('operation') == 'experts.ask':
            from .portable_research_knowledge import draft_refs, require_owner_sources
            require_owner_sources(self.discussion_documents, draft_refs('expert',
                {'context': job.get('arguments', {}).get('context', {})}))
        # The job owns its native path. A browser/LLM never supplies a solver
        # output directory or a replacement outcome to the native reader.
        summary=self.manager.result(identifier,selection={'responses':[]})
        if summary.get('native_result') and not (summary.get('pde_document_result') or summary.get('research_document_result')):
            path=self.root/'native'/check_id(identifier)
            if not path.is_dir():
                raise ValueError('Saved native result is unavailable')
            return read_result(path,selection=selection)
        return self.manager.result(identifier,selection=selection)

    def describe_inputs(self, request):
        backend=request.get('backend') or request.get('inputs',{}).get('backend')
        if not backend:
            return {'backends':self.backends()}
        if backend=='evaluation.definition':
            settings=request.get('settings',request.get('inputs',{}).get('settings',{}))
            if set(settings)!={'definition_ref'}:
                return {'backend':backend,'inputs':[], 'required':['definition_ref'], 'readiness':'NOT_PROBED'}
            compiled=self.evaluation_documents.from_reference(settings['definition_ref'])
            admission = None
            if request.get('method') == 'slsqp_adjoint':
                from .linear_adjoint_contract import configure
                admission = configure(compiled, request.get('variables', []),
                    [request.get('objective', {})] + request.get('constraints', []))
            return {'backend':backend, 'inputs':compiled['inputs'], 'responses':compiled['definition']['responses'],
                    'derivative_capability': compiled['derivative_capability'], 'derivative_admission': admission,
                    'budget_unit': 'stage_or_adjoint_dispatch' if admission is not None or any('targets' in b for b in compiled['definition']['bindings']) else 'model_evaluation',
                    'readiness':'NOT_PROBED', 'execution':'serial existing stage adapters'}
        if backend=='material.law_native':
            from plugins.material_point import law_native
            settings=request.get('settings',request.get('inputs',{}).get('settings',{}))
            return {'backend':backend,'models':list(law_native.MODELS),
                    'inputs':law_native.describe_inputs(settings) if settings else [],
                    'declaration':law_native.declaration(settings) if settings else None,
                    'readiness':'NOT_PROBED','execution':'explicit evaluation only'}
        if backend=='material.felupe':
            from .adapters.felupe_material import FelupeMaterialAdapter
            settings=request.get('settings',request.get('inputs',{}).get('settings',{}))
            descriptors=FelupeMaterialAdapter().describe_inputs(settings) if settings else []
            return {'inputs':descriptors, 'backend':backend,'models':['linear_elastic','neo_hooke'],
                    'parameters':{'linear_elastic':['E','nu'],'neo_hooke':['mu','lmbda']},
                    'required':['time','deformation_gradient','stress_unit','parameters'],
                    'axis':'time','outputs':['stress_xx','stress_yy','stress_zz','stress_xy','stress_xz','stress_yz','tangent']}
        if backend in self.config.get('external_backends',{}):
            configuration=self.config['external_backends'][backend]
            return {'backend':backend,'input_mode':'external_files','variables':configuration.get('variables',{}),
                    'settings_schema':{'type':'object','additionalProperties':False,'properties':{
                        'values':{'type':'object','description':'Exact registered variable values; numerical studies populate these from each candidate.'},
                        'case_id':{'type':'string'},'conditions':configuration.get('conditions_schema',{'type':'object'})}},
                    'responses':configuration.get('result',{}).get('columns',{}),
                    'settings_example':configuration.get('settings_example',{}),
                    'numerical_inputs':'Use count and seed directly in DOE inputs, not a design object; use settings.conditions for test conditions. Analyze the completed job separately.'}
        adapter=get_backend(backend)
        from .workbench_examples import native_example
        example=native_example(backend)
        extras={'example_settings':example,'example_notice':'Editable mathematical teaching case; not physical qualification.'} if example else {}
        if callable(getattr(adapter,'describe_inputs',None)) and request.get('settings'):
            derivative = ({'derivative_capability': adapter.describe_derivatives(request['settings'])}
                          if callable(getattr(adapter, 'describe_derivatives', None)) else {})
            return {'backend':backend,'inputs':adapter.describe_inputs(request['settings']),**extras,**derivative}
        return {'backend':backend,'input_mode':'native_settings','runtime':'Probe only the chosen backend',
                'description':'Use the backend documented settings or registered external input declaration',**extras}

    def _admit_job(self, *args, **kwargs):
        with self._assist_config_lock:
            return self.manager.submit(*args, **kwargs)

    def submit(self, operation, arguments, *, request_id=None, resources=None):
        if operation not in OPERATIONS or not isinstance(arguments,dict):
            raise ValueError('Select a registered operation with JSON arguments')
        if 'label' in arguments and (not isinstance(arguments['label'],str) or len(arguments['label'])>160):
            raise ValueError('Research name must be text of at most 160 characters')
        if set(arguments)&{'output','record','runtime','command','factory','module','source_roots'}:
            raise ValueError('Output, runtime and execution registrations are operator-owned')
        if isinstance(arguments.get('backend'),str) and arguments['backend'] not in {row['id'] for row in self.backends()}:
            raise ValueError('Backend is not registered')
        if operation.startswith('remote.'):
            from .remote_execution import validate_arguments
            if not isinstance(request_id, str) or not request_id.strip():
                raise ValueError('원격 요청은 응답 유실 후 같은 요청을 확인할 request_id가 필요합니다.')
            if resources:
                raise ValueError('원격 자원은 remote_resources에서 지정하세요.')
            validate_arguments(self, operation, arguments)
            return self._admit_job(operation, arguments, workspace_id=self.workspace_id,
                request_id=request_id, resources={'threads':1})
        if operation in {'doe','optimize','epsilon','fit','uq','sample_sensitivity'} and 'variables' in arguments:
            from .variable_domains import normalize, require_capability
            declared = normalize(arguments['variables'])
            require_capability(operation, declared)
            described = self.describe_inputs(arguments) if operation != 'fit' or arguments.get('settings') else {}
            if described.get('inputs'):
                from .variable_binding import admit_domains, request_descriptors
                admit_domains(declared, request_descriptors(arguments.get('backend'),
                    arguments.get('settings', {}), described['inputs']))
        if operation in {'experiment_uncertainty', 'identification_final'}:
            from .experiment_analysis_service import validate_prepared
            validate_prepared(self, operation, arguments)
        if operation=='detail_eval':
            from .numerical_candidate_detail import validate_detail_arguments, validate_backend_binding
            validate_detail_arguments(self.numerical_documents, arguments)
            validate_backend_binding(self, arguments)
        if operation=='evaluation.coupled':
            source=arguments.get('definition_source',{})
            owner=self.evaluation_documents
            identifier=check_id(source.get('document_id'))
            with owner._lock(identifier):
                document=owner.read(identifier)
                expected=owner.prepare_job_arguments(document['draft'],owner._documents[identifier])
                if canonical_hash(arguments)!=canonical_hash(expected):
                    raise ValueError('Evaluation arguments differ from the selected owner input/session/generation')
                requested=self.resource_request(arguments,resources)
                return self._admit_job(operation,arguments,workspace_id=self.workspace_id,request_id=request_id,resources=requested)
        if arguments.get('backend') == 'structure.calculix.design':
            execution = arguments.get('execution', {})
            if execution.get('mode', 'serial') != 'serial' or execution.get('workers', 1) != 1:
                raise ValueError('Native CAD candidates currently run serially with one worker')
            if '_native_context' in arguments.get('settings', {}):
                raise ValueError('Native execution context is service-owned')
        if operation == 'impact.reprocess':
            from .impact_recovery import prepare
            arguments = prepare(self, arguments)
        if operation == 'dynamic.reprocess':
            from .dynamic_recovery_job import prepare
            arguments = prepare(self, arguments)
        if operation == 'import_table':
            arguments = deepcopy(arguments)
            certificates = self.data_documents.calibration_sources(
                arguments.get('mapping', {}), arguments.get('calibration_sources'))
            if certificates or 'calibration_sources' in arguments:
                arguments['calibration_sources'] = certificates
        requested=self.resource_request(arguments,resources)
        return self._admit_job(operation,arguments,workspace_id=self.workspace_id,request_id=request_id,resources=requested)

    def resource_request(self,arguments,resources=None):
        requested=deepcopy(resources or {})
        execution=arguments.get('execution',{})
        actual_threads=execution.get('workers',1)*execution.get('threads',1)
        external=self.config.get('external_backends',{}).get(arguments.get('backend'),{})
        actual_threads=max(actual_threads,execution.get('workers',1)*external.get('threads',1))
        registered=next((row for row in self.backends() if row['id']==arguments.get('backend')), {})
        native_threads=registered.get('threads',1)
        if arguments.get('backend') in {'explicit.opencourant.model','explicit.opencourant.connector'}:
            # This adapter now honors the admitted thread count; keep its old
            # two-thread default when no operator reservation was supplied.
            native_threads=max(native_threads,requested.get('threads',2))
        if registered.get('native_runtime') and arguments.get('backend') not in self.config.get('external_backends',{}):
            import os
            # Preserved native adapters may inherit operator thread settings.
            for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
                try:
                    native_threads=max(native_threads,int(os.environ.get(key,'1')))
                except ValueError:
                    raise ValueError(f'{key} must declare a positive integer for managed native execution')
        actual_threads=max(actual_threads,execution.get('workers',1)*native_threads)
        models=[]
        if 'definition_source' in arguments:
            models=[row['draft'] for row in arguments.get('snapshots',{}).values()]
        elif arguments.get('backend')=='evaluation.definition':
            settings=arguments.get('settings') or (arguments.get('experiments') or [{}])[0].get('settings',{})
            if set(settings)!={'definition_ref'}:
                raise ValueError('Select a saved definition before execution')
            if execution.get('mode','serial')!='serial' or execution.get('workers',1)!=1:
                raise ValueError('Reusable stage evaluations require serial execution with one worker')
            compiled=self.evaluation_documents.from_reference(settings['definition_ref'])
            if arguments.get('method') == 'slsqp_adjoint':
                from .linear_adjoint_contract import configure
                configure(compiled, arguments.get('variables', []),
                    [arguments.get('objective', {})] + arguments.get('constraints', []))
            models=[row['model'] for row in compiled['stages'].values()]
        for model in models:
            actual_threads=max(actual_threads,self.resource_request(model)['threads'])
        requested['threads']=max(requested.get('threads',1),actual_threads)
        if execution.get('memory_mb') is not None:
            requested['memory_mb']=max(requested.get('memory_mb',0),execution['memory_mb']*execution.get('workers',1))
        return requested

    def assistance(self):
        with self._assist_config_lock:
            return self._get_assistance()

    def _get_assistance(self):
        if self._assistance is None:
            self._assistance = self._create_assistance(self.config)
        return self._assistance

    def _create_assistance(self, configuration):
        """Build from one approved configuration; publish only after validation."""
        from .assist import Assistance
        from .assist.experts import RuntimeConfig
        runtime=RuntimeConfig(**configuration['runtime']) if configuration.get('runtime') else None
        callbacks={'calculations.inputs':self.describe_inputs,
                   'calculations.resources':lambda request:self.resource_request(request.get('inputs',request),request.get('resources')),
                   'calculations.submit':self._proposed_submit,
                   'calculations.status':lambda request:self.manager.status(request['job_id']),
                   'results.read':lambda request:self.result(request.get('result_id',request.get('job_id',request.get('run_id'))),selection=request.get('selection',{'metadata_only':True})),
                   'numerical.doe':lambda request:self._numerical_submit('doe',request),
                   'numerical.analyze':lambda request:self._execute('analyze',request,'read'),
                   'numerical.fit':lambda request:self._numerical_submit('fit',request),
                   'numerical.optimize':lambda request:self._numerical_submit('optimize',request)}
        assistance = Assistance(self.root/'assistance',experts=configuration.get('experts'),runtime=runtime,
                                   callbacks=callbacks,source_roots=[self.root])
        if self._portable_manifest:
            from .portable_research_knowledge import bind_store
            bind_store(assistance.knowledge, self.workspace, self._portable_manifest)
        return assistance

    @staticmethod
    def _numerical_arguments(operation, request):
        """Apply the existing execution budget before a managed submission."""
        args=deepcopy(request)
        budget=args.pop('budget',{})
        maximum=budget.get('evaluations')
        if maximum is not None:
            if type(maximum) is not int or maximum < 1:
                raise ValueError('Evaluation budget must be a positive integer')
            execution=args.setdefault('execution',{})
            execution['max_evaluations']=min(execution.get('max_evaluations',maximum),maximum)
            if operation in {'doe','uq'}:
                if operation=='doe' and 'candidates' in args:
                    samples=len(args['candidates'])
                elif operation=='doe' and 'result_refs' in args:
                    samples=0  # Exact retained rows are checked again before execution below.
                else:
                    samples=args.get('count',128 if operation=='uq' else 16)
                if samples>maximum:
                    raise ValueError('Sampling exceeds the allowed evaluation budget')
            if operation in {'fit','optimize','epsilon'}:
                options=args.setdefault('options',{})
                if operation=='fit' and args.get('method','least_squares')!='de':
                    options['max_nfev']=min(options.get('max_nfev',maximum),maximum)
                elif operation=='optimize' and args.get('method') == 'slsqp_adjoint':
                    # Native stage/adjoint dispatches use the same hard budget.
                    if set(options) - {'maxiter','ftol','initial_values','verify_gradient','retain_responses'}:
                        raise ValueError('SLSQP 선택에는 SLSQP 방법 설정만 사용할 수 있습니다.')
                elif operation=='epsilon':
                    import math
                    grid=args.get('threshold_grid',[])
                    if not grid or any(not isinstance(row,list) or not row for row in grid):
                        raise ValueError('Each secondary objective requires an explicit nonempty threshold grid')
                    children=math.prod(len(row) for row in grid)
                    total=args.get('total_evaluation_budget',maximum)
                    if type(total) is not int or total < 1 or total > maximum:
                        raise ValueError('Epsilon total evaluation budget exceeds the Plan budget')
                    population=options.get('population_size',12)
                    generations=options.get('max_generations',min(40,max(1,total//children//population-1)))
                    if children*population*(generations+1)>total:
                        raise ValueError('Epsilon threshold searches exceed the total evaluation budget')
                    options['max_generations']=generations
                    args['total_evaluation_budget']=total
                    execution['max_evaluations']=min(execution['max_evaluations'],total)
                else:
                    options['max_generations']=min(options.get('max_generations',40),
                        max(1,maximum//options.get('population_size',12)-1))
                    if (options['max_generations']+1)*options.get('population_size',12)>maximum:
                        raise ValueError('Optimization population exceeds allowed evaluations')
        return args

    def _numerical_submit(self, operation, request):
        return self.submit(operation,self._numerical_arguments(operation,request))

    def _request_plan_arguments(self, request, *, submission=False):
        from .assist.experts import validate_plan_request
        validated=validate_plan_request(request,describe_inputs=self.describe_inputs,
                                        submission=submission)['plan']
        operation=validated['operation']
        if operation in {'experiment_uncertainty', 'identification_final'}:
            from .experiment_analysis_service import prepare_request
            return prepare_request(self, validated)
        args=deepcopy(validated['inputs'])
        from .research_operations import validate_result_refs
        validate_result_refs(operation,args)
        if operation == 'surrogate' and 'search' in args:
            args['search'] = self._numerical_arguments('optimize',
                {**args['search'], 'budget':validated['budget']})
            return args
        if operation in {'doe','fit','optimize','uq','epsilon'}:
            return self._numerical_arguments(operation,{**args,'budget':validated['budget']})
        if operation=='evaluate' and str(args.get('backend','')).startswith('pde.'):
            if args.get('values'):
                raise ValueError('Direct PDE requests edit declared coefficients in settings; use a Numerical search for mapped free variables')
            args.pop('values',None)
        elif operation == 'evaluate' and 'values' in args:
            from .simulation_document import CATALOG
            if args.get('backend') in CATALOG:
                # NumericalDocuments submits this as the existing simulation
                # operation. Freeze explicit scalar assignments before that
                # strict backend/settings-only boundary, leaving its owner
                # document untouched.
                from .model_parameters import bind
                values = args.pop('values')
                if values:
                    args['settings'] = bind(get_backend(args['backend']), args['settings'], values)
        return args

    def _proposed_submit(self, request):
        operation=request['operation']
        if operation not in {'evaluate','run','doe','fit','optimize','uq','epsilon','analyze',
                             'surrogate','sensitivity','sample_sensitivity','batch_export','batch_import'}:
            raise ValueError('Operation is not supported by expert calculation submission')
        inputs=self._request_plan_arguments(request,submission=True)
        return self.submit(operation,inputs,resources=request.get('resources'))

    def assistance_call(self, operation, arguments):
        args=deepcopy(arguments)
        scoped={'knowledge.ingest','knowledge.list','knowledge.search','knowledge.source','knowledge.revoke',
                'experts.ask','calculations.plan'}
        if operation in scoped:
            args['workspace_id']=self.workspace_id
        with self._assist_config_lock:
            assistance = self.assistance()
            self._assistance_active += 1
        try:
            return assistance.call(operation,args)
        except Exception as error:
            from .execution_control import ExecutionCleanupFailed
            if isinstance(error, ExecutionCleanupFailed):
                with self._assist_config_lock:
                    self._assistance_cleanup_pending = True
            raise
        finally:
            with self._assist_config_lock:
                self._assistance_active -= 1

    def _settings(self, backend, settings):
        settings=deepcopy(settings)
        if backend == 'structure.calculix.design':
            from .cad_numerical import resolve_settings
            return resolve_settings(self, settings)
        if backend == 'explicit.opencourant.connector' and set(settings) == {'data_id'}:
            identifier=settings['data_id'];path=self.input_path(identifier)
            receipt=load_json(self.root/'inputs'/identifier/'input.json')
            if receipt.get('kind')!='frozen_connector':raise ValueError('Select a registered connector input')
            return {'data_id':identifier,'snapshot_path':str(path)}
        if backend in {'structure.calculix.frozen', 'structure.calculix.contact', 'structure.calculix.pretension', 'structure.calculix.shell', 'structure.calculix.shell.composite', 'structure.calculix.beam', 'structure.codeaster.frozen'}:
            if set(settings) != {'data_id'}:
                raise ValueError('Frozen FEM execution requires only a registered data_id')
            identifier=settings['data_id']
            path=self.input_path(identifier)
            receipt=load_json(self.root/'inputs'/identifier/'input.json')
            if receipt.get('kind') != {'structure.calculix.contact':'frozen_contact', 'structure.calculix.pretension':'frozen_contact', 'structure.calculix.frozen':'frozen_fem', 'structure.codeaster.frozen':'frozen_fem',
                                      'structure.calculix.shell':'frozen_shell', 'structure.calculix.shell.composite':'frozen_composite_shell', 'structure.calculix.beam':'frozen_beam'}[backend]:
                raise ValueError('Select a registered frozen FEM snapshot')
            return {'data_id':identifier,'snapshot_path':str(path)}
        if backend=='files.table':
            identifier=settings.pop('data_id',None)
            if not identifier or 'path' in settings:
                raise ValueError('Remote table reads require an uploaded data_id')
            settings['path']=str(self.input_path(identifier))
        # No remotely supplied solver paths or arbitrary code. Native adapters
        # retain their own typed numeric/domain validation.
        provenance_paths=frozenset()
        if backend=='structure.felupe.law_native' and 'source_receipt' in settings:
            from .law_native_provenance import admitted_guard_paths
            provenance_paths=admitted_guard_paths(settings)
        elif backend=='explicit.opencourant.model' and 'source' in settings:
            from .impact_input_workflow import admitted_guard_paths
            provenance_paths=admitted_guard_paths(settings)
        def reject_paths(value,trail=()):
            if isinstance(value,dict):
                for key,item in value.items():
                    if key in {'command','argv','module','factory','script','executable','output','output_root','runtime','snapshot_path'}:
                        raise ValueError('Remote execution configuration is not a model input')
                    if key=='path' and backend!='files.table' and trail+(key,) not in provenance_paths:
                        raise ValueError('Use an uploaded input reference, not a server path')
                    reject_paths(item,trail+(key,))
            elif isinstance(value,list):
                for index,item in enumerate(value):
                    reject_paths(item,trail+(index,))
        reject_paths(settings)
        return settings

    def _execute(self, operation, arguments, identifier):
        if operation == 'acquisition.replay':
            from .acquisition_service import execute
            return execute(self, arguments, identifier)
        if operation.startswith('remote.'):
            from .remote_execution import execute
            return execute(self, operation, arguments, identifier)
        if operation == 'impact.reprocess':
            from .impact_recovery import execute
            return execute(self, arguments, identifier)
        if operation == 'dynamic.reprocess':
            from .dynamic_recovery_job import execute
            return execute(self, arguments, identifier)
        args=deepcopy(arguments)
        args.pop('label',None)  # Retained job metadata, never a solver parameter.
        if operation in {'experiment_uncertainty', 'identification_final'}:
            from .experiment_analysis_service import execute
            return execute(self, operation, args, identifier)
        if 'result_refs' in args:
            from .research_operations import resolve_request_inputs
            args=resolve_request_inputs(operation,args,resolve_document=self.document_read,
                                        resolve_result=self.document_result)
        backend=args.get('backend')
        if operation=='detail_eval':
            from .numerical_candidate_detail import validate_detail_arguments, validate_backend_binding
            validate_detail_arguments(self.numerical_documents, arguments, allow_active=True)
            validate_backend_binding(self, arguments)
        domain_adapter = None
        if operation == 'evaluate' and backend not in {'evaluation.definition', 'material.mfront.prepared'}:
            candidate = get_backend(backend)
            if not callable(candidate) and not callable(getattr(candidate, 'prepare', None)):
                domain_adapter = candidate
        if backend is not None and operation != 'simulation.run' and domain_adapter is None:
            args['settings']=self._settings(backend,args.get('settings',{}))
        if operation=='evaluation.coupled':
            from .research_workflows import execute_definition
            return execute_definition(self,args,identifier)
        if operation=='simulation.run':
            if set(args)!={'backend','settings'}:
                raise ValueError('Simulation requires only its declared backend and frozen settings')
            from .research_execution import run_domain
            if args['backend'] in {'explicit.opencourant.model','explicit.opencourant.connector'}:
                return run_domain(self,args,self.root/'results'/identifier,
                    runtime=self.manager.status(identifier)['resources'])
            return run_domain(self,args,self.root/'results'/identifier)
        if operation=='evaluate' and backend=='evaluation.definition':
            from .evaluation_definition import execute
            from .research_execution import run_domain
            if set(args.get('settings',{}))!={'definition_ref'} or set(args)-{'backend','settings','values'}:
                raise ValueError('Reusable evaluation requires its exact saved definition reference')
            compiled=self.evaluation_documents.from_reference(args['settings']['definition_ref'])
            if compiled['definition'].get('reuse'):
                raise ValueError('Numerical evaluations start independent stages; clear direct-run reuse in the definition')
            return execute(compiled,self.root/'results'/identifier,
                lambda model,output:run_domain(self,model,output),values=args.get('values'))
        if operation=='pde.evaluate':
            if set(args)!={'backend','settings'}:
                raise ValueError('PDE evaluation requires only its declared backend and frozen settings')
            from .pde import evaluate_document
            return evaluate_document(self,identifier,backend,args['settings'])
        if operation=='evaluate':
            if backend=='material.mfront.prepared':
                from .adapters.native_evaluation import NativeEvaluationFactory
                return evaluate(NativeEvaluationFactory(backend,self.root/'native'/identifier),
                                args.get('settings',{}),values=args.get('values'))
            adapter = domain_adapter if domain_adapter is not None else get_backend(backend)
            if not callable(adapter) and not callable(getattr(adapter, 'prepare', None)):
                from .model_parameters import bind
                from .research_execution import run_domain
                settings = args.get('settings', {})
                if args.get('values'):
                    settings = bind(adapter, settings, args['values'])
                runtime = (self.manager.status(identifier)['resources']
                           if backend in {'explicit.opencourant.model', 'explicit.opencourant.connector'} else None)
                return run_domain(self, {'backend': backend, 'settings': settings}, self.root/'results'/identifier,
                                  runtime=runtime)
            return evaluate(backend,args.get('settings',{}),values=args.get('values'))
        if operation=='run':
            if backend=='material.mfront.prepared':
                from .adapters.native_evaluation import NativeEvaluationFactory
                return evaluate(NativeEvaluationFactory(backend,self.root/'native'/identifier),
                                args.get('settings',{}),values=args.get('values'))
            if backend in self.config.get('external_backends',{}):
                from .adapters.external_files import ExternalFilesAdapter
                backend=ExternalFilesAdapter(backend,self.config['external_backends'][backend])
            output=self.root/'native'/identifier
            result=run(backend,args.get('settings',{}),output=output,selection=args.get('selection'))
            if backend in {'structure.calculix.frozen', 'structure.calculix.contact', 'structure.calculix.pretension', 'structure.calculix.shell', 'structure.calculix.shell.composite', 'structure.calculix.beam', 'structure.codeaster.frozen'}:
                result['origin_input']={'id':arguments['settings']['data_id'],
                    'kind':{'structure.calculix.contact':'frozen_contact', 'structure.calculix.pretension':'frozen_contact', 'structure.calculix.frozen':'frozen_fem', 'structure.codeaster.frozen':'frozen_fem',
                            'structure.calculix.shell':'frozen_shell', 'structure.calculix.shell.composite':'frozen_composite_shell', 'structure.calculix.beam':'frozen_beam'}[backend]}
            publish_contact_prefix = (backend in {'structure.calculix.contact', 'structure.calculix.pretension'} and
                result.get('partial_result',{}).get('status')=='CONVERGED_PREFIX' and
                result.get('partial_result',{}).get('complete_analysis') is False)
            publish_shell_prefix = (backend in {'structure.calculix.shell','structure.calculix.shell.composite'} and bool(result.get('post_artifact')))
            if backend in {'structure.calculix.frozen', 'structure.calculix.contact', 'structure.calculix.pretension', 'structure.calculix.shell', 'structure.calculix.shell.composite', 'structure.calculix.beam', 'structure.codeaster.frozen'} and (
                    result.get('execution_status')=='SUCCEEDED' or publish_contact_prefix or publish_shell_prefix or
                    (backend=='structure.calculix.beam' and result.get('post_artifact') and
                     result.get('execution_status') in {'FAILED','CANCELLED'})):
                native_status=result.get('execution_status')
                try:
                    if result.get('dynamic_post_artifacts'):
                        from .dynamic_locations import publish_job_inputs
                        publish_job_inputs(self,result,output,identifier,arguments)
                    else:
                        artifacts=[result['post_artifact'],*result.get('additional_post_artifacts',[])]
                        result['post_inputs']=[]
                        for artifact in artifacts:
                            source=contained(output,artifact['relative'])
                            if source.stat().st_size!=artifact['bytes'] or file_hash(source)!=artifact['sha256']:
                                raise ValueError('Native Post artifact changed before registration')
                            receipt=register_native_input(self.root,output,source,'D'+uuid.uuid4().hex,
                                root_id='job:'+identifier,relative=artifact['relative'],limit=self.config.get('local_input_max_bytes',2*1024**3),
                                native_metadata=artifact.get('native_metadata'))
                            result['post_inputs'].append({'id':receipt['id'],'format':receipt['format'],'sha256':receipt['sha256']})
                        result['post_input']=deepcopy(result['post_inputs'][0])
                except (OSError, ValueError, KeyError, TypeError) as error:
                    # Preserve the already-computed responses and owned files if
                    # downstream publication fails. Never claim Post is ready or
                    # silently resubmit a costly native calculation to recover it.
                    result.update(execution_status='FAILED', native_execution_status=native_status,
                                  post_registration={'status':'FAILED','type':type(error).__name__,'message':str(error)})
                    result.setdefault('diagnostics', {})['post_registration'] = str(error)
            return result
        if operation=='import_table':
            mapping=args.get('mapping',{})
            reference=args.get('source_ref')
            certificates=self.data_documents.calibration_sources(
                mapping,args.get('calibration_sources'),require_frozen=True)
            source=(self.input_path(args['data_id']) if reference is None else
                    self.data_documents.resolve_job_source(args['data_id'],reference)[0])
            result=evaluate('files.table',{**mapping,'path':str(source)})
            if reference is not None:
                self.data_documents.resolve_job_source(args['data_id'],reference)
                result.setdefault('diagnostics',{})['source_ref']=deepcopy(reference)
            self.data_documents.calibration_sources(mapping,certificates,require_frozen=True)
            result.setdefault('diagnostics',{})['test_metadata']=deepcopy(args.get('test_metadata',{}))
            result['diagnostics']['calibration_sources']=deepcopy(certificates)
            return result
        if operation.startswith(('knowledge.','literature.','experts.')) or operation=='calculations.plan':
            if operation=='knowledge.ingest':
                data_id=args.pop('data_id')
                args['source']=str(self.input_path(data_id))
                receipt=load_json(self.root/'inputs'/data_id/'input.json')
                args.setdefault('metadata',{}).setdefault('title',receipt['name'])
            if operation == 'experts.ask' and args.get('context', {}).get('discussion_mode') == 'costorm':
                from .discussion_costorm import authorize
                from .assist.costorm import owner_step
                trusted = authorize(self.discussion_documents, args, identifier)
                if trusted.get('team_action') is not None:
                    action = trusted['team_action']
                    def configure_tools(runtime, budget):
                        from types import SimpleNamespace
                        from .assist.research_evidence import ResultAccess
                        from .research_team_results import workbench_readers, analysis_input_factory, AnalysisAccess
                        from .execution_control import check_cancelled
                        readers = workbench_readers(self, verification_receipts=action.lookup_result_verification)
                        readers['transmission_check'] = runtime._transmission_check
                        result_access = ResultAccess(readers=readers, current_scope_probe=action.current_scope_probe)
                        analysis_access = AnalysisAccess(
                            describe_inputs=analysis_input_factory(self, readers=readers),
                            describe_resources=lambda resources: self.resource_request({}, resources),
                            existing_callback=lambda request: self._execute('analyze', request, 'read'),
                            execution_control=SimpleNamespace(check=check_cancelled))
                        return {'result_access': result_access, 'analysis_access': analysis_access}
                    action.configure_tools = configure_tools
                with owner_step(trusted):
                    result = self.assistance_call(operation, args)
            else:
                result=self.assistance_call(operation,args)
            if operation=='experts.ask' and result.get('status') in {'FAILED','NOT_CONFIGURED'}:
                result['execution_status']='FAILED'
            return result
        from . import numerical
        if operation=='sample_sensitivity':
            plan=numerical.sample_sensitivity(**args)
            return {**plan,'kind':'sensitivity_plan','execution_status':'SUCCEEDED',
                    'solver_execution':'NOT_PERFORMED','next_step':'Evaluate the exact retained candidate rows; then select this plan and its matched result for sensitivity.'}
        if operation in {'fit','doe','optimize','uq','epsilon','detail_eval'}:
            backend=args.pop('backend')
            if operation in {'fit','detail_eval'}:
                args.pop('settings',None)
                for experiment in args.get('experiments',[]):
                    resolved_settings=self._settings(backend,experiment.get('settings',{}))
                    if operation=='detail_eval' and canonical_hash(resolved_settings)!=canonical_hash(experiment.get('settings',{})):
                        raise ValueError('Detail execution cannot replace the original frozen evaluator settings')
                    experiment['settings']=resolved_settings
                    if isinstance(experiment.get('observations'),dict) and 'path' in experiment['observations']:
                        raise ValueError('Remote observations require an uploaded result ID or explicit numeric values')
                    sources = set(experiment) & {'observations', 'observation_job', 'observation_ref'}
                    if len(sources) != 1:
                        raise ValueError('Every fit/holdout experiment selects exactly one observation source')
                    if 'observation_ref' in experiment:
                        from .research_operations import _resolve
                        reference = experiment.pop('observation_ref')
                        if not isinstance(reference, dict) or set(reference) != {'result', 'response'}:
                            raise ValueError('Select an exact saved observation result and response')
                        retained = _resolve(reference['result'], self.document_read, self.document_result)
                        if retained.get('execution_status') != 'SUCCEEDED' or retained.get('prediction_status'):
                            raise ValueError('Fit observations require an actual successful retained result')
                        source = reference['result']
                        response = reference['response']
                        selected = self.document_result(source['document_id'], source['job_id'], selection=[response])
                        experiment['observations'] = selected['responses'][response]
                        experiment['observation_source'] = {**deepcopy(reference),
                            'source_sha256': selected.get('diagnostics', {}).get('source_sha256')}
                        _resolve(source, self.document_read, self.document_result)
                    elif 'observation_job' in experiment:
                        observation_response=experiment.pop('observation_response',experiment['response'])
                        observation_job=experiment.pop('observation_job')
                        observation=self.result(observation_job,selection=[observation_response])
                        experiment['observations']=observation['responses'][observation_response]
                        experiment['observation_source']={'job_id':observation_job,'response':observation_response,
                            'source_sha256':observation.get('diagnostics',{}).get('source_sha256')}
            from .numerical_candidate_detail import freeze_fit_input, evaluate_candidate_detail, backend_binding
            # The Data lane may supply its frozen compiler packet at this boundary.
            # This consumer verifies it; it never compiles or changes source rows.
            inclusion_packet=args.pop('fit_inclusion',None) if operation=='fit' else None
            if operation == 'fit' and inclusion_packet is not None and args.get('frozen_inclusion') is not None:
                raise ValueError('Canonical frozen_inclusion and legacy fit_inclusion cannot be combined')
            fit_snapshot=(freeze_fit_input(backend,args,arguments,
                inclusion_packet=inclusion_packet,evaluator_binding=backend_binding(self,backend)) if operation=='fit' else None)
            methods={'detail_eval':evaluate_candidate_detail,'fit':numerical.fit_model,'doe':numerical.run_doe,'optimize':numerical.optimize,
                     'uq':numerical.run_uq,'epsilon':numerical.epsilon_optimize}
            execution=args.get('execution',{})
            if set(execution)-{'mode','workers','threads','memory_mb','on_failure','max_evaluations'}:
                raise ValueError('Unknown execution option')
            if execution.get('workers',1)*execution.get('threads',1)>self.manager.cpu_budget:
                raise ValueError('Numerical worker/thread product exceeds CPU budget')
            if operation=='doe' and 'candidates' in args and len(args['candidates'])>execution.get('max_evaluations',float('inf')):
                raise ValueError('Exact retained candidate count exceeds this Plan evaluation budget')
            evaluator=backend
            owns_candidate_files = backend == 'evaluation.definition'
            if 'responses' in args:
                selections = args['responses']
                if not isinstance(selections, list) or any(not isinstance(name, str) or not name for name in selections):
                    raise ValueError('Response selection requires exact registered response names')
            if backend=='evaluation.definition':
                from .evaluation_definition import DefinitionFactory
                from .research_execution import run_domain
                if execution.get('mode','serial')!='serial' or execution.get('workers',1)!=1:
                    raise ValueError('Reusable evaluation currently runs serial stage sequences; select one worker')
                settings=(args.get('experiments',[{}])[0].get('settings',{}) if operation in {'fit','detail_eval'} else args.get('settings',{}))
                if set(settings)!={'definition_ref'}:
                    raise ValueError('Select an exact saved EvaluationDefinition')
                if operation in {'fit','detail_eval'} and any(item.get('settings')!=settings for item in args.get('experiments',[])):
                    raise ValueError('Fit experiments must reference the same evaluation definition')
                compiled=self.evaluation_documents.from_reference(settings['definition_ref'])
                if compiled['definition'].get('reuse'):
                    raise ValueError('Numerical candidates cannot reuse another candidate state; clear direct-run reuse')
                evaluator=DefinitionFactory(compiled,self.root/'results'/identifier/'evaluations',
                    lambda model,output:run_domain(self,model,output))
            elif backend in self.config.get('external_backends',{}):
                from .adapters.external_files import FileEvaluationFactory
                evaluator=FileEvaluationFactory(backend,self.config['external_backends'][backend],self.root/'native'/identifier)
            else:
                adapter=get_backend(backend)
                if backend=='material.mfront.prepared' or (not callable(adapter) and not callable(getattr(adapter,'prepare',None))):
                    from .adapters.native_evaluation import NativeEvaluationFactory
                    selectors=args.pop('responses',None)
                    if selectors is None:
                        if operation in {'fit','detail_eval'}:
                            selectors=[experiment['response'] for experiment in args.get('experiments',[])]
                        elif operation in {'optimize','epsilon'}:
                            definitions=([args['objective']] if operation=='optimize' else args.get('objectives',[]))+args.get('constraints',[])
                            selectors=[definition.get('response',definition.get('metric')) for definition in definitions]
                    owns_candidate_files = backend != 'material.mfront.prepared'
                    folder = self.root/'results'/identifier
                    evaluator=NativeEvaluationFactory(backend,
                        folder/'evaluations' if owns_candidate_files else self.root/'native'/identifier,
                        response_selection=selectors, retained_root=folder if owns_candidate_files else None)
            if 'responses' in args:
                raise ValueError('Explicit DOE/UQ response selection is available for file-based native evaluations; this evaluator returns its own named responses')
            try:
                result=methods[operation](evaluator,**args)
            except Exception as error:
                from .execution_control import ExecutionCleanupFailed, ExecutionCancelled
                if not owns_candidate_files or isinstance(error,ExecutionCleanupFailed):
                    raise
                # A later objective/response error must not orphan completed
                # native stages. Retain those actual attempts without claiming
                # that the numerical algorithm accepted or ranked them.
                result={'kind':operation,'execution_status':'CANCELLED' if isinstance(error,ExecutionCancelled) else 'FAILED',
                    'responses':{},'candidates':[],
                    'failure_reason':str(error),'diagnostics':{'error_type':type(error).__name__,
                        'decision':'NOT_RELEASED','candidate_association':'UNASSIGNED_AFTER_ENGINE_ERROR'},
                    'evaluation_attempts':(evaluator.retained_attempts() if callable(getattr(evaluator,'retained_attempts',None))
                                           else deepcopy(evaluator.completed))}
            if 'domain_input' in result:
                from .numerical_candidate_detail import backend_binding
                result['evaluator_binding'] = backend_binding(self, backend)
            if fit_snapshot is not None:
                result['fit_input_snapshot']=fit_snapshot
            if owns_candidate_files:
                from .evaluation import save_evaluation
                folder=self.root/'results'/identifier
                result['artifacts']=[{'path':path.relative_to(folder).as_posix(),'sha256':file_hash(path)}
                    for path in sorted(folder.rglob('*')) if path.is_file()]
                save_evaluation(result,folder,existing=folder.exists())
            return result
        if operation=='analyze':
            table=args.pop('table',None)
            if table is None:
                table=self.result(args.pop('job_id'))
            return numerical.analyze_candidates(table,**args)
        if operation=='compare':
            prediction=self.result(args['prediction_job'],selection=[args['prediction_response']])['responses'][args['prediction_response']]
            observation=self.result(args['observation_job'],selection=[args['observation_response']])['responses'][args['observation_response']]
            return numerical.compare_curves(prediction,observation,**args.get('options',{}))
        if operation=='event':
            response_name=args.pop('response')
            response=self.result(args.pop('job_id'),selection=[response_name])['responses'][response_name]
            return numerical.detect_event(response,**args)
        if operation=='batch_export':
            path=self.root/'batches'/identifier
            plan=numerical.export_batch(args['variables'],args['candidates'],path,case_id=args['case_id'],settings=args.get('settings'),domain_input=args.get('domain_input'))
            return {'batch_id':identifier,'manifest':plan,'mode':'FILE_EXCHANGE','solver_execution':'NOT_PERFORMED'}
        if operation=='batch_import':
            plan=args.get('manifest')
            if plan is None:
                plan=self.result(args['batch_job'])['manifest']
            return numerical.import_batch(plan,args['results'])
        if operation=='surrogate':
            if 'retained_model' in args and 'search' in args:
                from .surrogate_archive import search
                return search(args['retained_model'], source_ref=args.get('model_reference'), **args['search'])
            if 'retained_model' in args:
                from .surrogate_archive import predict
                return predict(args['retained_model'], args['points'])
            from .research_operations import surrogate_result
            training=args.get('training')
            holdout=args.get('holdout')
            if training is None: training=self.result(args['training_job'])
            if holdout is None: holdout=self.result(args['holdout_job'])
            return surrogate_result(training,holdout,args['response'],args['points'],
                                    variables=args.get('variables'),options=args.get('options'))
        if operation=='sensitivity':
            if 'baseline' in args and 'refined' in args:
                from .numerical_extensions import compare_sobol
                return compare_sobol(args['baseline'], args['refined'], source_refs=args.get('comparison_refs'))
            table=args.get('table')
            if table is None: table=self.result(args['job_id'])
            return numerical.analyze_sensitivity(args['plan'],table,args['response'],
                evaluation_context=args.get('evaluation_context'), evaluation_source_ref=args.get('evaluation_source_ref'))
        raise ValueError('Unknown operation')

    def shutdown(self, timeout=5):
        self.native_commands.shutdown()
        return self.manager.shutdown(timeout)
