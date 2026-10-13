"""Explicit build / build-and-evaluate using the existing owned MFront runtime."""
from pathlib import Path
import hashlib
import json
import os
from .. import user_material as domain
from ..storage import save_json
from ..execution_control import ExecutionCancelled,ExecutionCleanupFailed,check_cancelled
from .mfront_material import _runtime_identity,sha256
from .codeaster_elasticity import _process

SOURCES={'worker.py':Path(__file__).with_name('user_mfront_worker.py'),
 'native_helpers.py':Path(__file__).with_name('mfront_material_worker.py'),
 'user_material.py':Path(__file__).parents[1]/'user_material.py',
 'dimensioned_expression.py':Path(__file__).parents[1]/'dimensioned_expression.py'}
LOADED={name:path.read_bytes() for name,path in SOURCES.items()}
BOOTSTRAP='source /opt/activate.sh; export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1; exec python3 -I /work/worker.py'


class UserMFrontAdapter:
    backend=domain.BACKEND
    version='1'
    def default_settings(self):return domain.default_settings()
    def validate_settings(self,settings):return domain.validate_settings(settings)
    def describe_model(self,settings):return domain.model_declaration(settings)
    def describe_ports(self,settings):
        self.validate_settings(settings);return {'inputs':{},'outputs':{}}
    def describe_inputs(self,settings):
        s=self.validate_settings(settings)
        return [{'id':r['name'],'label':r['name'],'unit':r['unit'],'value':r['value'],
            'lower':-1e100,'upper':1e100,'settings_path':['properties',i,'value'],
            'declaration_paths':[['model','properties',i,'value']]} for i,r in enumerate(s['properties'])]
    def bind_inputs(self,settings,values):
        s=self.validate_settings(settings);rows={r['name']:r for r in s['properties']}
        if not isinstance(values,dict) or set(values)-set(rows):raise ValueError('등록된 물성만 변경할 수 있습니다.')
        for key,value in values.items():rows[key]['value']=value
        return self.validate_settings(s)

    def run(self,settings,*,output,runtime=None):
        if runtime and set(runtime)-{'threads','memory_mb'}:raise ValueError('법칙 입력은 실행 경로를 변경하지 못합니다.')
        s=self.validate_settings(settings);folder=Path(output)/'user_law';folder.mkdir(exist_ok=False)
        save_json(folder/'input.json',s)
        # Exact source permission is resolved only in the executing operator
        # process. No HTTP field or source text can grant compilation authority.
        digest=domain.require_admission(s);check_cancelled()
        save_json(folder/'admission.json',{'source_sha256':digest,'authority':'LOCAL_OPERATOR_EXACT_SOURCE_APPROVAL'})
        for name,path in SOURCES.items():
            if path.read_bytes()!=LOADED[name]:raise RuntimeError('서비스 시작 후 구성식 worker가 변경됐습니다.')
            data=LOADED[name]
            if name=='user_material.py':data=data.replace(b'from .dimensioned_expression import',b'from dimensioned_expression import')
            (folder/name).write_bytes(data)
        pins={name:sha256(folder/name) for name in SOURCES};save_json(folder/'sources.json',pins)
        input_sha=sha256(folder/'input.json');manifest_sha=sha256(folder/'sources.json')
        image,image_sha,launcher=_runtime_identity()
        scratch=folder/'scratch';scratch.mkdir()
        command=[launcher,'exec','--cleanenv','--containall','--no-home','--bind',str(folder.resolve())+':/work:rw',
            '--bind',str(scratch.resolve())+':/tmp:rw','--pwd','/work',str(image),
            '/bin/bash','--noprofile','--norc','-c',BOOTSTRAP]
        save_json(folder/'runtime_selection.json',{'image_sha256':image_sha,'image':str(image),
                    'source_sha256':digest,'action':s['action'],'scope':'owned process; admitted native source, not a C++ security sandbox'})
        try:
            _process(command,folder,'user_law',timeout=300)
        except ExecutionCleanupFailed:raise
        except (RuntimeError,ExecutionCancelled) as error:
            partial={}
            path=folder/'history.partial.json'
            if path.is_file():partial=json.loads(path.read_text(encoding='utf-8'))
            return {'execution_status':'CANCELLED' if isinstance(error,ExecutionCancelled) else 'FAILED','responses':{},
                    'checks':[],'diagnostics':{'reason':str(error),'constitutive':partial,'decision':'NOT_RELEASED'}}
        if (sha256(image)!=image_sha or sha256(folder/'input.json')!=input_sha or sha256(folder/'sources.json')!=manifest_sha
            or any(sha256(folder/name)!=value or SOURCES[name].read_bytes()!=LOADED[name] for name,value in pins.items())):
            raise RuntimeError('빌드 입력/실행 코드/선택 runtime이 변경됐습니다.')
        raw=json.loads((folder/'user_result.json').read_text(encoding='utf-8'),
            parse_constant=lambda value:(_ for _ in ()).throw(ValueError('Native nonfinite JSON')))
        if (raw['input_sha256']!=input_sha or raw['sources_sha256']!=manifest_sha or raw['source_sha256']!=digest
            or sha256(folder/'build'/(s['behaviour']+'.mfront'))!=digest
            or raw['library_sha256']!=sha256(folder/'build/src/libBehaviour.so')):
            raise RuntimeError('법칙 원문/컴파일 라이브러리의 보존 참조가 다릅니다.')
        history=raw['constitutive'];complete=[r for r in history['steps'] if 'committed_state' in r]
        responses={}
        for i,name in enumerate(domain.COMPONENTS):
            if complete:
                responses['stress_'+name]={'kind':'series','unit':'Pa','value':[r['stress_kelvin'][i] for r in complete],
                    'axes':[{'name':'time','unit':'s','values':[r['time_s'] for r in complete]}],
                    'component':name,'frame':'material_cartesian','measure':'kelvin_cauchy_stress',
                    'location':'material_point','reduction':'none'}
        return {'execution_status':'SUCCEEDED' if history['status'] in ('SUCCEEDED','BUILT_ONLY') else 'FAILED',
            'responses':responses,'checks':[{'name':'engineering_qualification','status':'NOT_ASSESSED'}],
            'diagnostics':{'build':raw['build'],'constitutive':history,'action':s['action'],
                'source_sha256':digest,'interface':'generic MGIS; FE export not implemented','decision':'NOT_RELEASED',
                'residual':'NOT_REPORTED_BY_MGIS','substeps':'NOT_REPORTED_BY_MGIS'}}
