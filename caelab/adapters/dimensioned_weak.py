"""Owned native execution of a distinct dimensioned linear weak-form capability."""
from pathlib import Path
import hashlib
import json
import os
from .. import dimensioned_models as domain
from ..storage import save_json
from .fenicsx_rectangle import _run_process, _wall_timeout
from ..execution_control import ExecutionCancelled,ExecutionCleanupFailed

SOURCES={'worker.py':Path(__file__).with_name('dimensioned_weak_worker.py'),
         'dimensioned_expression.py':Path(__file__).parents[1]/'dimensioned_expression.py',
         'dimensioned_models.py':Path(__file__).parents[1]/'dimensioned_models.py'}
LOADED={name:path.read_bytes() for name,path in SOURCES.items()}


class DimensionedWeakAdapter:
    backend=domain.WEAK
    version='1'
    def default_settings(self): return domain.default_settings(self.backend)
    def validate_settings(self,settings): return domain.validate_settings(self.backend,settings)
    def describe_model(self,settings): return domain.model_declaration(self.backend,settings)
    def describe_inputs(self,settings): return domain.describe_inputs(self.backend,settings)
    def bind_inputs(self,settings,values): return domain.bind_inputs(self.backend,settings,values)

    def run(self,settings,*,output,runtime=None):
        if runtime and set(runtime)-{'threads','memory_mb'}: raise ValueError('지원하지 않는 실행 설정입니다.')
        settings=self.validate_settings(settings)
        folder=Path(output)/'pde';folder.mkdir(exist_ok=False)
        for name,path in SOURCES.items():
            if path.read_bytes()!=LOADED[name]: raise RuntimeError('서비스 시작 후 약형식 코드가 변경됐습니다.')
            data=LOADED[name]
            if name=='dimensioned_models.py':
                data=data.replace(b'from .dimensioned_expression import',b'from dimensioned_expression import')
            (folder/name).write_bytes(data)
        pins={name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in SOURCES}
        save_json(folder/'sources.json',pins);save_json(folder/'input.json',settings)
        input_hash=hashlib.sha256((folder/'input.json').read_bytes()).hexdigest()
        manifest_hash=hashlib.sha256((folder/'sources.json').read_bytes()).hexdigest()
        interpreter=os.environ.get('CAELAB_FENICSX_PYTHON','/usr/bin/python3')
        if not interpreter.strip(): raise ValueError('FEniCSx Python 실행 경로가 비어 있습니다.')
        env=os.environ.copy()
        for name in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','PETSC_DIR','PETSC_OPTIONS','PETSC_OPTIONS_YAML'): env.pop(name,None)
        command=[interpreter,'-I',str((folder/'worker.py').resolve()),str((folder/'input.json').resolve())]
        save_json(folder/'command.json',{'argv':command,'timeout_seconds':_wall_timeout()})
        try: _run_process(command,folder,env,_wall_timeout())
        except ExecutionCleanupFailed: raise
        except (RuntimeError,ExecutionCancelled) as error:
            partial={}
            if (folder/'progress.json').exists(): partial=json.loads((folder/'progress.json').read_text(encoding='utf-8'))
            return {'execution_status':'CANCELLED' if isinstance(error,ExecutionCancelled) else 'FAILED',
                    'responses':{},'checks':[],'diagnostics':{'reason':str(error),'partial_levels':partial,'native_fields':partial.get('fields',[]),
                        'mesh_studies':partial.get('completed_levels',[]),'decision':'NOT_RELEASED'}}
        if any(hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest for name,digest in pins.items()):
            raise RuntimeError('계산 중 보존 코드가 변경됐습니다.')
        raw=json.loads((folder/'worker_result.json').read_text(encoding='utf-8'),
                       parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite native JSON')))
        if (raw.pop('input_sha256')!=input_hash or raw.pop('sources_sha256')!=manifest_hash
                or hashlib.sha256((folder/'input.json').read_bytes()).hexdigest()!=input_hash
                or hashlib.sha256((folder/'sources.json').read_bytes()).hexdigest()!=manifest_hash):
            raise RuntimeError('계산 입력/코드 참조가 일치하지 않습니다.')
        return raw
