"""Operator-registered input templates, owned execution and explicit table extraction."""
from copy import deepcopy
from pathlib import Path
import json
import os
import string
from ..backends import register_backend
from ..evaluation import file_hash
from ..execution_control import run_owned_command
from .file_table import read_table


def register_external_backend(identifier, configuration):
    config=deepcopy(configuration)
    if not isinstance(config.get('command'),list) or not config['command'] or not all(isinstance(x,str) for x in config['command']):
        raise ValueError('Trusted external command must be an argv list, not shell text')
    register_backend(identifier,lambda: ExternalFilesAdapter(identifier,config),roles=('model','external'),
                     native_runtime=config.get('label','Operator-registered external program'),threads=config.get('threads',1))


class ExternalFilesAdapter:
    version='1'
    def __init__(self,identifier,configuration):
        self.backend=identifier
        self.config=deepcopy(configuration)

    def run(self,settings,*,output,runtime=None):
        if runtime:
            raise ValueError('External execution is configured by the operator, not the request')
        if set(settings)-{'values','case_id','conditions'}:
            raise ValueError('External request accepts declared values, case_id and conditions only')
        values=settings.get('values',{})
        declarations=self.config.get('variables',{})
        if set(values)!=set(declarations):
            raise ValueError('External candidate values must match registered variables')
        import math
        for name,value in values.items():
            spec=declarations[name]
            if type(value) not in (int,float) or not math.isfinite(value) or not spec['lower']<=value<=spec['upper']:
                raise ValueError(f'{name}: candidate is outside registered numeric bounds')
        root=Path(output).resolve()
        def target(relative):
            path=(root/relative).resolve()
            if not path.is_relative_to(root) or path==root:
                raise ValueError('Registered file path escapes the candidate output')
            return path
        inputs=[]
        for template in self.config.get('templates',[]):
            source=Path(template['source']).resolve()
            destination=target(template['destination'])
            destination.parent.mkdir(parents=True,exist_ok=True)
            text=string.Template(source.read_text(encoding='utf-8')).substitute({key:repr(float(v)) for key,v in values.items()})
            with destination.open('x',encoding='utf-8') as stream:
                stream.write(text)
            inputs.append({'name':template['destination'],'original_sha256':file_hash(source),'input_sha256':file_hash(destination)})
        with target('candidate.json').open('x',encoding='utf-8') as stream:
            json.dump(settings,stream,allow_nan=False)
        result_path=target(self.config['result']['path'])
        if result_path.exists():
            raise ValueError('Output already exists before execution; refusing stale response')
        environment=dict(os.environ)
        environment['OMP_NUM_THREADS']=str(self.config.get('threads',1))
        run_owned_command(self.config['command'],root,'external',timeout=self.config.get('timeout',300),env=environment).check_returncode()
        extractor=self.config.get('extractor')
        if extractor:
            run_owned_command(extractor,root,'extract',timeout=self.config.get('timeout',300),env=environment).check_returncode()
        result=read_table(result_path,self.config['result'])
        result['diagnostics'].update(mode='REGISTERED_EXTERNAL_EXECUTION',solver_execution='COMPLETED',
                                     backend=self.backend,inputs=inputs,values=values,case_id=settings.get('case_id'))
        return result


class FileEvaluationFactory:
    """Explicit file evaluation for numerical studies; never advertised as in-memory.

    Factories contain trusted operator configuration, so spawned workers register
    their own adapter. Every real candidate/case has a new retained directory.
    """
    def __init__(self, identifier, configuration, output):
        self.identifier=identifier
        self.configuration=deepcopy(configuration)
        self.output=str(Path(output).resolve())

    def prepare(self, settings, *, runtime=None):
        import uuid
        from ..evaluation import PreparedEvaluation, run
        adapter=ExternalFilesAdapter(self.identifier,self.configuration)
        if runtime and set(runtime)-{'threads','memory_mb'}:
            raise ValueError('Unsupported file evaluation runtime option')
        def candidate(values):
            result=run(adapter,{**deepcopy(settings),'values':values},
                       output=Path(self.output)/('candidate-'+uuid.uuid4().hex))
            result['diagnostics']['evaluation_mode']='FILE_BASED'
            return result
        return PreparedEvaluation(candidate,settings)
