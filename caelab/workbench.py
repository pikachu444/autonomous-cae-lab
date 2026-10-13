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
from .storage import save_json, load_json, check_id, utc_now, canonical_hash
from .native_inputs import NATIVE_EXTENSIONS, register_native_input, register_frozen_input

INPUT_EXTENSIONS = {'.csv','.txt','.dat','.asc','.npz','.json','.md','.pdf'}

OPERATIONS = {'evaluate','run','import_table','fit','doe','optimize','uq','analyze','compare','event',
              'batch_export','batch_import','surrogate','epsilon','sensitivity',
              'sample_sensitivity',
              'knowledge.ingest','knowledge.rebuild','knowledge.revoke','literature.search','literature.read',
              'literature.import','experts.ask','calculations.plan','pde.evaluate','simulation.run','evaluation.coupled'}


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
        self.workspace=Path(workspace).resolve()
        self.root=self.workspace/'workbench'
        self.root.mkdir(parents=True,exist_ok=True)
        self.config=deepcopy(configuration or {})
        self.workspace_id=self.config.get('workspace_id','local')
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
        self.native_commands=NativeCommands(self.root,self.session_id)
        self.numerical_documents=NumericalDocuments(self.root,self.session_id,self.submit,self.manager,
            resolve_document=self.document_read, resolve_result=self.document_result,
            prepare_request=self._request_plan_arguments,
            resolve_source_revision=lambda identifier,revision:self._document_owner(identifier)._verify_revision(identifier,revision),
            resolve_pde_revision=lambda identifier,revision:self.pde_documents._verify_revision(identifier,revision))
        self.pde_documents=PDEDocuments(self.root,self.session_id,self.submit,self.manager)
        self.discussion_documents=DiscussionDocuments(self.root,self.session_id,self.submit,self.manager,
            list_experts=lambda:self.assistance_call('experts.list',{}),
            resolve_document=self.document_read,resolve_result=self.document_result,
            resolve_knowledge=lambda reference:self.assistance_call('knowledge.source',reference))
        self.simulation_documents=SimulationDocuments(self.root,self.session_id,self.submit,self.manager)
        self.evaluation_documents=EvaluationDocuments(self.root,self.session_id,self.submit,self.manager,
            resolve_revision=lambda identifier,revision:self._document_owner(identifier)._verify_revision(identifier,revision))
        from .research_workflows import reference_metadata
        self.study_documents=StudyDocuments(self.root,self.session_id,self.submit,self.manager,
            resolve_reference=lambda reference:reference_metadata(self,reference))
        self.desktop=DesktopLinks(self)

    def research_owners(self):
        return (self.material_documents,self.data_documents,self.numerical_documents,
                self.pde_documents,self.discussion_documents,self.simulation_documents,
                self.evaluation_documents,self.study_documents)

    def documents(self):
        return {'service_session_id':self.session_id,
                'documents':[doc for owner in self.research_owners() for doc in owner.list()]+self.native_commands.documents()}

    def document_open(self, *, kind='material', title=None, draft=None, document_id=None):
        owners={owner.kind:owner for owner in self.research_owners()}
        if kind not in owners:
            raise ValueError('Choose a research document kind; native documents open in their host')
        if title is None:
            title={'material':'Material research','data':'Data research','pde':'PDE research',
                   'numerical':'Numerical Plan','expert':'Expert discussion','simulation':'Simulation research',
                   'evaluation':'Evaluation definition','study':'Study'}[kind]
        return owners[kind].open(title=title,draft=draft,document_id=document_id)

    def _document_owner(self, identifier):
        check_id(identifier)
        return next((owner for owner in self.research_owners() if identifier.startswith(owner.prefix)),self.native_commands)

    def document_read(self, identifier):
        return self._document_owner(identifier).read(identifier)

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
            if arguments['receipt'].get('format') not in {'vtu','pvd'}:
                raise ValueError('Post readers currently admit registered VTU/PVD result sets')
        method=owner.submit if owner is self.native_commands else owner.command
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
        return result_metadata(self.document_result(identifier,job_id,selection={'metadata_only': True}))

    def document_response_locations(self, identifier, job_id, channel, *, start=0, count=128, search=''):
        from .research_operations import response_locations
        result = self.document_result(identifier, job_id, selection={'metadata_only': True})
        return response_locations(result, channel, start=start, count=count, search=search) | {
            'document_id': identifier, 'job_id': job_id}

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

    def domain_candidate_preview(self, plan_id, job_id, candidate_id):
        from .domain_candidate import preview
        return preview(self,plan_id,job_id,candidate_id)

    def domain_candidate_adopt(self, plan_id, job_id, candidate_id, *, target_document_id,
                               session_id, expected_generation, command_id):
        from .domain_candidate import adopt
        return adopt(self,plan_id,job_id,candidate_id,target_document_id=target_document_id,
            session_id=session_id,expected_generation=expected_generation,command_id=command_id)

    def study_references(self, identifier):
        return self.study_documents.resolve_references(identifier)

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
        path=contained(self.root,receipt['file'])
        if file_hash(path)!=receipt['sha256']:
            raise ValueError('Uploaded source changed')
        if receipt.get('kind') in {'native_result', 'native_design', 'frozen_fem', 'frozen_contact'}:
            folder=(self.root/'inputs'/identifier).resolve()
            files=receipt.get('files',[])
            if not files or not any(item.get('file')==receipt['file'] and item.get('sha256')==receipt['sha256'] for item in files):
                raise ValueError('Native input set has no pinned entry file')
            for item in files:
                dependency=contained(self.root,item['file'])
                if not dependency.is_relative_to(folder) or dependency.stat().st_size!=item['bytes'] or file_hash(dependency)!=item['sha256']:
                    raise ValueError('Registered native input or dependency changed')
        return path

    def native_input(self, identifier):
        """Resolve a registered native set for a local reader after verification."""
        path = self.input_path(identifier)
        receipt = load_json(self.root/'inputs'/identifier/'input.json')
        if receipt.get('kind') not in {'native_result', 'native_design', 'frozen_fem', 'frozen_contact'}:
            raise ValueError('Select a registered native result or FEM snapshot')
        result = {'id': identifier, 'path': str(path), 'format': receipt['format'], 'kind': receipt['kind'], 'sha256': receipt['sha256'],
                'source_pins': [{'path': str(contained(self.root, item['file'])),
                                 'bytes': item['bytes'], 'sha256': item['sha256']}
                                for item in receipt['files']]}
        result['registration_origin'] = deepcopy(receipt.get('origin'))
        if receipt.get('candidate_branch'):
            result['candidate_branch'] = deepcopy(receipt['candidate_branch'])
        if receipt['kind'] in {'frozen_fem', 'frozen_contact'}:
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

    def input_preview(self,identifier):
        path=self.input_path(identifier)
        receipt=load_json(self.root/'inputs'/identifier/'input.json')
        if receipt.get('kind') in {'frozen_fem', 'frozen_contact'}:
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
            return {'backend':backend, 'inputs':compiled['inputs'], 'responses':compiled['definition']['responses'],
                    'readiness':'NOT_PROBED', 'execution':'serial existing stage adapters'}
        if backend=='material.felupe':
            return {'backend':backend,'models':['linear_elastic','neo_hooke'],
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
            return {'backend':backend,'inputs':adapter.describe_inputs(request['settings']),**extras}
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
            from .assist import Assistance
            from .assist.experts import RuntimeConfig
            runtime=RuntimeConfig(**self.config['runtime']) if self.config.get('runtime') else None
            callbacks={'calculations.inputs':self.describe_inputs,
                       'calculations.resources':lambda request:self.resource_request(request.get('inputs',request),request.get('resources')),
                       'calculations.submit':self._proposed_submit,
                       'calculations.status':lambda request:self.manager.status(request['job_id']),
                       'results.read':lambda request:self.result(request.get('result_id',request.get('job_id',request.get('run_id'))),selection=request.get('selection',{'metadata_only':True})),
                       'numerical.doe':lambda request:self._numerical_submit('doe',request),
                       'numerical.analyze':lambda request:self._execute('analyze',request,'read'),
                       'numerical.fit':lambda request:self._numerical_submit('fit',request),
                       'numerical.optimize':lambda request:self._numerical_submit('optimize',request)}
            self._assistance=Assistance(self.root/'assistance',experts=self.config.get('experts'),runtime=runtime,
                                       callbacks=callbacks,source_roots=[self.root])
        return self._assistance

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
                if operation=='fit':
                    options['max_nfev']=min(options.get('max_nfev',maximum),maximum)
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
        args=deepcopy(validated['inputs'])
        from .research_operations import validate_result_refs
        validate_result_refs(operation,args)
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
        if backend in {'structure.calculix.frozen', 'structure.calculix.contact'}:
            if set(settings) != {'data_id'}:
                raise ValueError('Frozen FEM execution requires only a registered data_id')
            identifier=settings['data_id']
            path=self.input_path(identifier)
            receipt=load_json(self.root/'inputs'/identifier/'input.json')
            if receipt.get('kind') != ('frozen_contact' if backend == 'structure.calculix.contact' else 'frozen_fem'):
                raise ValueError('Select a registered frozen FEM snapshot')
            return {'data_id':identifier,'snapshot_path':str(path)}
        if backend=='files.table':
            identifier=settings.pop('data_id',None)
            if not identifier or 'path' in settings:
                raise ValueError('Remote table reads require an uploaded data_id')
            settings['path']=str(self.input_path(identifier))
        # No remotely supplied solver paths or arbitrary code. Native adapters
        # retain their own typed numeric/domain validation.
        def reject_paths(value):
            if isinstance(value,dict):
                for key,item in value.items():
                    if key in {'command','argv','module','factory','script','executable','output','output_root','runtime','snapshot_path'}:
                        raise ValueError('Remote execution configuration is not a model input')
                    if key=='path' and backend!='files.table':
                        raise ValueError('Use an uploaded input reference, not a server path')
                    reject_paths(item)
            elif isinstance(value,list):
                for item in value:
                    reject_paths(item)
        reject_paths(settings)
        return settings

    def _execute(self, operation, arguments, identifier):
        args=deepcopy(arguments)
        args.pop('label',None)  # Retained job metadata, never a solver parameter.
        if 'result_refs' in args:
            from .research_operations import resolve_request_inputs
            args=resolve_request_inputs(operation,args,resolve_document=self.document_read,
                                        resolve_result=self.document_result)
        backend=args.get('backend')
        if backend is not None:
            args['settings']=self._settings(backend,args.get('settings',{}))
        if operation=='evaluation.coupled':
            from .research_workflows import execute_definition
            return execute_definition(self,args,identifier)
        if operation=='simulation.run':
            if set(args)!={'backend','settings'}:
                raise ValueError('Simulation requires only its declared backend and frozen settings')
            from .research_execution import run_domain
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
            adapter = get_backend(backend)
            if not callable(adapter) and not callable(getattr(adapter, 'prepare', None)):
                from .model_parameters import bind
                from .research_execution import run_domain
                settings = args.get('settings', {})
                if args.get('values'):
                    settings = bind(adapter, settings, args['values'])
                return run_domain(self, {'backend': backend, 'settings': settings}, self.root/'results'/identifier)
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
            if backend in {'structure.calculix.frozen', 'structure.calculix.contact'} and result.get('execution_status')=='SUCCEEDED':
                result['origin_input']={'id':arguments['settings']['data_id'],
                    'kind':'frozen_contact' if backend=='structure.calculix.contact' else 'frozen_fem'}
                try:
                    artifact=result['post_artifact']
                    source=contained(output,artifact['relative'])
                    if source.stat().st_size!=artifact['bytes'] or file_hash(source)!=artifact['sha256']:
                        raise ValueError('Native Post artifact changed before registration')
                    receipt=register_native_input(self.root,output,source,'D'+uuid.uuid4().hex,
                        root_id='job:'+identifier,relative=artifact['relative'],limit=self.config.get('local_input_max_bytes',2*1024**3),
                        native_metadata=artifact.get('native_metadata'))
                    result['post_input']={'id':receipt['id'],'format':receipt['format'],'sha256':receipt['sha256']}
                except (OSError, ValueError, KeyError, TypeError) as error:
                    # Preserve the already-computed responses and owned files if
                    # downstream publication fails. Never claim Post is ready or
                    # silently resubmit a costly native calculation to recover it.
                    result.update(execution_status='FAILED', native_execution_status='SUCCEEDED',
                                  post_registration={'status':'FAILED','type':type(error).__name__,'message':str(error)})
                    result.setdefault('diagnostics', {})['post_registration'] = str(error)
            return result
        if operation=='import_table':
            mapping=args.get('mapping',{})
            reference=args.get('source_ref')
            if reference is None:
                # Existing result-only API calls retain their registered-input contract.
                return evaluate('files.table',{**mapping,'path':str(self.input_path(args['data_id']))})
            source, _ = self.data_documents.resolve_job_source(args['data_id'], reference)
            result=evaluate('files.table',{**mapping,'path':str(source)})
            # A queued import may start after the editor/source has changed.
            # Verify the same pinned bytes and receipt after the actual reader,
            # without consulting the current draft or repairing the registry.
            self.data_documents.resolve_job_source(args['data_id'], reference)
            result.setdefault('diagnostics',{})['source_ref']=deepcopy(reference)
            return result
        if operation.startswith(('knowledge.','literature.','experts.')) or operation=='calculations.plan':
            if operation=='knowledge.ingest':
                data_id=args.pop('data_id')
                args['source']=str(self.input_path(data_id))
                receipt=load_json(self.root/'inputs'/data_id/'input.json')
                args.setdefault('metadata',{}).setdefault('title',receipt['name'])
            result=self.assistance_call(operation,args)
            if operation=='experts.ask' and result.get('status') in {'FAILED','NOT_CONFIGURED'}:
                result['execution_status']='FAILED'
            return result
        from . import numerical
        if operation=='sample_sensitivity':
            plan=numerical.sample_sensitivity(**args)
            return {**plan,'kind':'sensitivity_plan','execution_status':'SUCCEEDED',
                    'solver_execution':'NOT_PERFORMED','next_step':'Evaluate the exact retained candidate rows; then select this plan and its matched result for sensitivity.'}
        if operation in {'fit','doe','optimize','uq','epsilon'}:
            backend=args.pop('backend')
            if operation=='fit':
                args.pop('settings',None)
                for experiment in args.get('experiments',[]):
                    experiment['settings']=self._settings(backend,experiment.get('settings',{}))
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
                        experiment['observation_source'] = deepcopy(reference)
                        _resolve(source, self.document_read, self.document_result)
                    elif 'observation_job' in experiment:
                        observation_response=experiment.pop('observation_response',experiment['response'])
                        observation=self.result(experiment.pop('observation_job'),selection=[observation_response])
                        experiment['observations']=observation['responses'][observation_response]
            methods={'fit':numerical.fit_model,'doe':numerical.run_doe,'optimize':numerical.optimize,
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
                settings=(args.get('experiments',[{}])[0].get('settings',{}) if operation=='fit' else args.get('settings',{}))
                if set(settings)!={'definition_ref'}:
                    raise ValueError('Select an exact saved EvaluationDefinition')
                if operation=='fit' and any(item.get('settings')!=settings for item in args.get('experiments',[])):
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
                        if operation=='fit':
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
            plan=numerical.export_batch(args['variables'],args['candidates'],path,case_id=args['case_id'],settings=args.get('settings'))
            return {'batch_id':identifier,'manifest':plan,'mode':'FILE_EXCHANGE','solver_execution':'NOT_PERFORMED'}
        if operation=='batch_import':
            plan=args.get('manifest')
            if plan is None:
                plan=self.result(args['batch_job'])['manifest']
            return numerical.import_batch(plan,args['results'])
        if operation=='surrogate':
            from .research_operations import surrogate_result
            training=args.get('training')
            holdout=args.get('holdout')
            if training is None: training=self.result(args['training_job'])
            if holdout is None: holdout=self.result(args['holdout_job'])
            return surrogate_result(training,holdout,args['response'],args['points'],
                                    variables=args.get('variables'),options=args.get('options'))
        if operation=='sensitivity':
            table=args.get('table')
            if table is None: table=self.result(args['job_id'])
            return numerical.analyze_sensitivity(args['plan'],table,args['response'])
        raise ValueError('Unknown operation')

    def shutdown(self, timeout=5):
        self.native_commands.shutdown()
        return self.manager.shutdown(timeout)
