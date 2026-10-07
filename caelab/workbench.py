"""Workspace application services shared by HTTP, CLI and optional MCP/experts."""
from copy import deepcopy
from pathlib import Path
import base64
import json
import re
import uuid
import io
import hashlib
import unicodedata
from .backends import list_backends, get_backend
from .evaluation import evaluate, run, read_result, file_hash
from .jobs import JobManager
from .storage import save_json, load_json, check_id, utc_now

OPERATIONS = {'evaluate','run','import_table','fit','doe','optimize','uq','analyze','compare','event',
              'batch_export','batch_import','surrogate','epsilon','sensitivity',
              'knowledge.ingest','knowledge.rebuild','knowledge.revoke','literature.search','literature.read',
              'literature.import','experts.ask','calculations.plan'}


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
    def __init__(self, workspace, *, configuration=None):
        self.workspace=Path(workspace).resolve()
        self.root=self.workspace/'workbench'
        self.root.mkdir(parents=True,exist_ok=True)
        self.config=deepcopy(configuration or {})
        self.workspace_id=self.config.get('workspace_id','local')
        if set(self.config.get('external_backends',{})) & {row['id'] for row in list_backends()}:
            raise ValueError('Workspace external backend IDs must not replace global registered backends')
        self.manager=JobManager(self.root,self._execute,workers=self.config.get('workers',2),cpu_budget=self.config.get('cpu_budget'))
        self._assistance=None

    def upload(self, name, payload):
        if not isinstance(payload,bytes) or not payload or len(payload)>16*1024*1024:
            raise ValueError('Upload must contain 1 byte to 16 MiB')
        return self._store_input(name, io.BytesIO(payload), len(payload))

    def _store_input(self, name, stream, length, *, origin=None):
        if (not isinstance(name,str) or not 1 <= len(name) <= 240 or name in {'.','..'}
                or any(char in '/\\:\x00' or unicodedata.category(char).startswith('C') for char in name)):
            raise ValueError('A plain filename is required')
        suffix=Path(name).suffix.lower()
        if suffix not in {'.csv','.txt','.dat','.asc','.npz','.json','.md','.pdf'}:
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

    def local_inputs(self, root_id, relative=''):
        roots=self.config.get('input_roots',{})
        if root_id not in roots:
            raise ValueError('Select an operator-approved input root')
        root=Path(roots[root_id]).resolve()
        directory=contained(root,relative) if relative else root
        if not directory.is_dir():
            raise ValueError('Input directory is unavailable')
        entries=[]
        for item in sorted(directory.iterdir(),key=lambda p:(not p.is_dir(),p.name.casefold())):
            if not item.resolve().is_relative_to(root):
                continue
            if item.is_dir() or item.suffix.lower() in {'.csv','.txt','.dat','.asc','.npz','.json','.md','.pdf'}:
                entries.append({'name':item.name,'relative':item.relative_to(root).as_posix(),
                                'directory':item.is_dir(),'bytes':None if item.is_dir() else item.stat().st_size})
            if len(entries)>=200:
                break
        return {'root_id':root_id,'relative':relative,'entries':entries,'limit':200}

    def register_local_input(self, root_id, relative):
        roots=self.config.get('input_roots',{})
        if root_id not in roots:
            raise ValueError('Select an operator-approved input root')
        source=contained(Path(roots[root_id]),relative)
        limit=self.config.get('local_input_max_bytes',2*1024**3)
        if type(limit) is not int or limit<1:
            raise ValueError('local_input_max_bytes must be a positive integer')
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
        return path

    def input_preview(self,identifier):
        path=self.input_path(identifier)
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
        return list_backends()+[{'id':identifier,'roles':['external'],'native_runtime':config.get('label','Operator-registered program'),
            'threads':config.get('threads',1),'source':'workspace','readiness':'EXECUTION_NOT_TESTED'}
            for identifier,config in self.config.get('external_backends',{}).items()]

    def overview(self):
        return {'workspace_id':self.workspace_id,'backends':self.backends(),
                'inputs':self.inputs(),'jobs':self.manager.list(),
                'input_roots':list(self.config.get('input_roots',{})),
                'assistance':{'configured':bool(self.config.get('runtime'))},
                'operations':sorted(OPERATIONS)}

    def result(self, identifier, *, selection=None):
        # The job owns its native path. A browser/LLM never supplies a solver
        # output directory or a replacement outcome to the native reader.
        summary=self.manager.result(identifier,selection={'responses':[]})
        if summary.get('native_result'):
            path=self.root/'native'/check_id(identifier)
            if not path.is_dir():
                raise ValueError('Saved native result is unavailable')
            return read_result(path,selection=selection)
        return self.manager.result(identifier,selection=selection)

    def describe_inputs(self, request):
        backend=request.get('backend') or request.get('inputs',{}).get('backend')
        if not backend:
            return {'backends':self.backends()}
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

    def submit(self, operation, arguments, *, request_id=None, resources=None):
        if operation not in OPERATIONS or not isinstance(arguments,dict):
            raise ValueError('Select a registered operation with JSON arguments')
        if 'label' in arguments and (not isinstance(arguments['label'],str) or len(arguments['label'])>160):
            raise ValueError('Research name must be text of at most 160 characters')
        if set(arguments)&{'output','record','runtime','command','factory','module','source_roots'}:
            raise ValueError('Output, runtime and execution registrations are operator-owned')
        if isinstance(arguments.get('backend'),str) and arguments['backend'] not in {row['id'] for row in self.backends()}:
            raise ValueError('Backend is not registered')
        requested=self.resource_request(arguments,resources)
        return self.manager.submit(operation,arguments,workspace_id=self.workspace_id,request_id=request_id,resources=requested)

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
        requested['threads']=max(requested.get('threads',1),actual_threads)
        if execution.get('memory_mb') is not None:
            requested['memory_mb']=max(requested.get('memory_mb',0),execution['memory_mb']*execution.get('workers',1))
        return requested

    def assistance(self):
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

    def _numerical_submit(self, operation, request):
        args=deepcopy(request)
        budget=args.pop('budget',{})
        maximum=budget.get('evaluations')
        if maximum is not None:
            if type(maximum) is not int or maximum < 1:
                raise ValueError('Evaluation budget must be a positive integer')
            execution=args.setdefault('execution',{})
            execution['max_evaluations']=min(execution.get('max_evaluations',maximum),maximum)
            if operation in {'doe','uq'} and (args.get('count',128 if operation=='uq' else 16)>maximum or len(args.get('candidates',[]))>maximum):
                raise ValueError('Sampling exceeds the allowed evaluation budget')
            if operation in {'fit','optimize'}:
                options=args.setdefault('options',{})
                if operation=='fit':
                    options['max_nfev']=min(options.get('max_nfev',maximum),maximum)
                else:
                    options['max_generations']=min(options.get('max_generations',40),
                        max(1,maximum//options.get('population_size',12)-1))
                    if (options['max_generations']+1)*options.get('population_size',12)>maximum:
                        raise ValueError('Optimization population exceeds allowed evaluations')
        return self.submit(operation,args)

    def _proposed_submit(self, request):
        operation=request['operation']
        if operation not in {'evaluate','run','doe','fit','optimize','uq','analyze'}:
            raise ValueError('Operation is not supported by expert calculation submission')
        inputs=deepcopy(request['inputs'])
        if operation in {'doe','fit','optimize','uq'}:
            inputs['budget']=request.get('budget',{})
            return self._numerical_submit(operation,inputs)
        return self.submit(operation,inputs,resources=request.get('resources'))

    def assistance_call(self, operation, arguments):
        args=deepcopy(arguments)
        scoped={'knowledge.ingest','knowledge.list','knowledge.search','knowledge.source','knowledge.revoke',
                'experts.ask','calculations.plan'}
        if operation in scoped:
            args['workspace_id']=self.workspace_id
        return self.assistance().call(operation,args)

    def _settings(self, backend, settings):
        settings=deepcopy(settings)
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
                    if key in {'command','argv','module','factory','script','executable','output','output_root','runtime'}:
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
        backend=args.get('backend')
        if backend is not None:
            args['settings']=self._settings(backend,args.get('settings',{}))
        if operation=='evaluate':
            if backend=='material.mfront.prepared':
                from .adapters.native_evaluation import NativeEvaluationFactory
                return evaluate(NativeEvaluationFactory(backend,self.root/'native'/identifier),
                                args.get('settings',{}),values=args.get('values'))
            return evaluate(backend,args.get('settings',{}),values=args.get('values'))
        if operation=='run':
            if backend=='material.mfront.prepared':
                from .adapters.native_evaluation import NativeEvaluationFactory
                return evaluate(NativeEvaluationFactory(backend,self.root/'native'/identifier),
                                args.get('settings',{}),values=args.get('values'))
            if backend in self.config.get('external_backends',{}):
                from .adapters.external_files import ExternalFilesAdapter
                backend=ExternalFilesAdapter(backend,self.config['external_backends'][backend])
            return run(backend,args.get('settings',{}),output=self.root/'native'/identifier,selection=args.get('selection'))
        if operation=='import_table':
            mapping=args.get('mapping',{})
            return evaluate('files.table',{**mapping,'path':str(self.input_path(args['data_id']))})
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
        if operation in {'fit','doe','optimize','uq','epsilon'}:
            backend=args.pop('backend')
            if operation=='fit':
                args.pop('settings',None)
                for experiment in args.get('experiments',[]):
                    experiment['settings']=self._settings(backend,experiment.get('settings',{}))
                    if isinstance(experiment.get('observations'),dict) and 'path' in experiment['observations']:
                        raise ValueError('Remote observations require an uploaded result ID or explicit numeric values')
                    if 'observation_job' in experiment:
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
            evaluator=backend
            if backend in self.config.get('external_backends',{}):
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
                    evaluator=NativeEvaluationFactory(backend,self.root/'native'/identifier,response_selection=selectors)
            return methods[operation](evaluator,**args)
        if operation=='analyze':
            table=args.pop('table',None)
            if table is None:
                table=self.manager.result(args.pop('job_id'))
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
            plan=self.manager.result(args['batch_job'])['manifest']
            return numerical.import_batch(plan,args['results'])
        if operation=='surrogate':
            model=numerical.fit_surrogate(self.manager.result(args['training_job']),self.manager.result(args['holdout_job']),args['response'])
            return {'predictions':model.predict(args['points']), 'validation':model.validation}
        if operation=='sensitivity':
            return numerical.analyze_sensitivity(args['plan'],self.manager.result(args['job_id']),args['response'])
        raise ValueError('Unknown operation')

    def shutdown(self, timeout=5):
        return self.manager.shutdown(timeout)
