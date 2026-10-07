"""Operator-registered input templates, owned execution and explicit table extraction."""
from copy import deepcopy
from pathlib import Path
import json
import os
import string
import shutil
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
        if self.config.get('conditions_schema'):
            import jsonschema
            jsonschema.validate(settings.get('conditions',{}),self.config['conditions_schema'])
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
        for attachment in self.config.get('files',[]):
            source=Path(attachment['source']).resolve()
            destination=target(attachment['destination'])
            destination.parent.mkdir(parents=True,exist_ok=True)
            original_hash=file_hash(source)
            with source.open('rb') as reader, destination.open('xb') as writer:
                shutil.copyfileobj(reader,writer,length=1024*1024)
            if file_hash(destination)!=original_hash or file_hash(source)!=original_hash:
                raise ValueError('External attachment changed while copying')
            inputs.append({'name':attachment['destination'],'original_sha256':original_hash,
                           'input_sha256':original_hash,'mode':'UNCHANGED_ATTACHMENT'})
        for template in self.config.get('templates',[]):
            source=Path(template['source']).resolve()
            destination=target(template['destination'])
            destination.parent.mkdir(parents=True,exist_ok=True)
            original=source.read_bytes()
            import hashlib
            original_hash=hashlib.sha256(original).hexdigest()
            text=original.decode(template.get('encoding','utf-8'))
            mode=template.get('mode','template')
            if mode=='template':
                # Legacy explicitly registered dollar placeholders remain
                # supported. Native $ comments and unrelated $ names survive.
                text=string.Template(text).safe_substitute({key:repr(float(v)) for key,v in values.items()})
            elif mode=='tokens':
                for patch in template.get('replacements',[]):
                    token=patch['token']
                    if not isinstance(token,str) or not token or text.count(token)!=patch.get('count',1):
                        raise ValueError('Input token occurrence count differs from its registered selector')
                    text=text.replace(token,format(values[patch['variable']],patch.get('format','.17g')))
            elif mode=='fixed_columns':
                lines=text.splitlines(keepends=True)
                occupied=set()
                for patch in template.get('replacements',[]):
                    line,start,stop=patch['line']-1,patch['start'],patch['stop']
                    if not 0<=line<len(lines) or not 0<=start<stop<=len(lines[line].rstrip('\r\n')):
                        raise ValueError('Fixed-width input selector is outside the original line')
                    cells={(line,i) for i in range(start,stop)}
                    if occupied & cells:
                        raise ValueError('Fixed-width input selectors overlap')
                    occupied.update(cells)
                    if lines[line][start:stop]!=patch['expected']:
                        raise ValueError('Original fixed-width input differs from registered expected bytes')
                    replacement=format(values[patch['variable']],patch.get('format','.8g'))
                    if len(replacement)>stop-start:
                        raise ValueError('Candidate value does not fit its native fixed-width field')
                    lines[line]=lines[line][:start]+replacement.rjust(stop-start)+lines[line][stop:]
                text=''.join(lines)
            else:
                raise ValueError('Input update mode must be template, tokens or fixed_columns')
            with destination.open('xb') as stream:
                stream.write(text.encode(template.get('encoding','utf-8')))
            if file_hash(source)!=original_hash:
                raise ValueError('Original input changed while preparing the candidate')
            inputs.append({'name':template['destination'],'original_sha256':original_hash,
                           'input_sha256':file_hash(destination),'mode':mode})
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
        # Recheck after the program/extractor: a new symlink must not redirect
        # a registered result outside this candidate's directory.
        result_path=target(self.config['result']['path'])
        result=read_table(result_path,self.config['result'])
        result['diagnostics'].update(mode='REGISTERED_EXTERNAL_EXECUTION',solver_execution='COMPLETED',
                                     backend=self.backend,inputs=inputs,values=values,case_id=settings.get('case_id'),
                                     conditions=deepcopy(settings.get('conditions',{})),candidate_directory=str(root))
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
