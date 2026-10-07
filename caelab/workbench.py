"""Workspace application services shared by HTTP, CLI and optional MCP/experts."""
from copy import deepcopy
from pathlib import Path
import base64
import json
import re
import uuid
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
        if not isinstance(name,str) or Path(name).name!=name or not re.fullmatch(r'[A-Za-z0-9_. -]{1,120}',name):
            raise ValueError('A plain filename is required')
        suffix=Path(name).suffix.lower()
        if suffix not in {'.csv','.txt','.dat','.asc','.npz','.json','.md','.pdf'}:
            raise ValueError('Unsupported data/document extension')
        identifier='D'+uuid.uuid4().hex
        folder=self.root/'inputs'/identifier
        folder.mkdir(parents=True)
        path=folder/('source'+suffix)
        path.write_bytes(payload)
        receipt={'id':identifier,'name':name,'file':path.relative_to(self.root).as_posix(),
                 'bytes':len(payload),'sha256':file_hash(path),'created_utc':utc_now()}
        save_json(folder/'input.json',receipt)
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
        return {'id':identifier,'text':path.read_text(encoding='utf-8')[:16384]}

    def backends(self):
        return list_backends()+[{'id':identifier,'roles':['external'],'native_runtime':config.get('label','Operator-registered program'),
            'threads':config.get('threads',1),'source':'workspace','readiness':'EXECUTION_NOT_TESTED'}
            for identifier,config in self.config.get('external_backends',{}).items()]

    def overview(self):
        return {'workspace_id':self.workspace_id,'backends':self.backends(),
                'inputs':self.inputs(),'jobs':self.manager.list(),
                'assistance':{'configured':bool(self.config.get('runtime'))},
                'operations':sorted(OPERATIONS)}

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
            return {'backend':backend,'input_mode':'external_files','variables':self.config['external_backends'][backend].get('variables',{})}
        adapter=get_backend(backend)
        if callable(getattr(adapter,'describe_inputs',None)) and request.get('settings'):
            return {'backend':backend,'inputs':adapter.describe_inputs(request['settings'])}
        return {'backend':backend,'input_mode':'native_settings','runtime':'Probe only the chosen backend',
                'description':'Use the backend documented settings or registered external input declaration'}

    def submit(self, operation, arguments, *, request_id=None, resources=None):
        if operation not in OPERATIONS or not isinstance(arguments,dict):
            raise ValueError('Select a registered operation with JSON arguments')
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
                       'results.read':lambda request:self.manager.result(request.get('result_id',request.get('job_id',request.get('run_id')))),
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
            if operation=='doe' and (args.get('count',16)>maximum or len(args.get('candidates',[]))>maximum):
                raise ValueError('DOE exceeds the allowed evaluation budget')
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
        inputs=deepcopy(request['inputs'])
        if operation in {'doe','fit','optimize'}:
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
                    if key in {'command','argv','module','factory','script','executable','output','runtime'}:
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
        backend=args.get('backend')
        if backend is not None:
            args['settings']=self._settings(backend,args.get('settings',{}))
        if operation=='evaluate':
            return evaluate(backend,args.get('settings',{}),values=args.get('values'))
        if operation=='run':
            if backend in self.config.get('external_backends',{}):
                from .adapters.external_files import ExternalFilesAdapter
                backend=ExternalFilesAdapter(backend,self.config['external_backends'][backend])
            return run(backend,args.get('settings',{}),output=self.root/'native'/identifier)
        if operation=='import_table':
            mapping=args.get('mapping',{})
            return evaluate('files.table',{**mapping,'path':str(self.input_path(args['data_id']))})
        if operation.startswith(('knowledge.','literature.','experts.')) or operation=='calculations.plan':
            if operation=='knowledge.ingest':
                args['source']=str(self.input_path(args.pop('data_id')))
            return self.assistance_call(operation,args)
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
                        observation=self.manager.result(experiment.pop('observation_job'))
                        observation_response=experiment.pop('observation_response',experiment['response'])
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
                if not callable(adapter) and not callable(getattr(adapter,'prepare',None)):
                    from .adapters.native_evaluation import NativeEvaluationFactory
                    evaluator=NativeEvaluationFactory(backend,self.root/'native'/identifier)
            return methods[operation](evaluator,**args)
        if operation=='analyze':
            table=args.pop('table',None)
            if table is None:
                table=self.manager.result(args.pop('job_id'))
            return numerical.analyze_candidates(table,**args)
        if operation=='compare':
            prediction=self.manager.result(args['prediction_job'])['responses'][args['prediction_response']]
            observation=self.manager.result(args['observation_job'])['responses'][args['observation_response']]
            return numerical.compare_curves(prediction,observation,**args.get('options',{}))
        if operation=='event':
            response=self.manager.result(args.pop('job_id'))['responses'][args.pop('response')]
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
