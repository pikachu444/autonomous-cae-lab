"""Explicit JobManager/evaluation FE adapter with the existing owned-process runner."""
from copy import deepcopy
from pathlib import Path
import os
import subprocess
import sys
from .. import law_native_fe as domain
from ..storage import save_json
from ..evaluation import read_result,file_hash
from ..execution_control import run_owned_command,ExecutionCancelled,ExecutionCleanupFailed


class LawNativeFEAdapter:
    backend='structure.felupe.law_native'
    version='1'
    default_settings=staticmethod(domain.default_settings)
    validate_settings=staticmethod(domain.validate_settings)
    describe_model=staticmethod(domain.describe_model)

    def describe_ports(self,settings):
        domain.validate_settings(settings)
        return {'inputs':{},'outputs':{}}

    def describe_inputs(self,settings):
        # FE fitting is deliberately not a new optimizer route: point fitting is
        # bound by the saved Material owner, followed by explicit FE application.
        domain.validate_settings(settings)
        return []

    def run(self,settings,*,output,runtime=None):
        if runtime and set(runtime)-{'threads','memory_mb'}:
            raise ValueError('No caller executable/library/source/build override')
        s=domain.validate_settings(settings);folder=Path(output).resolve()
        save_json(folder/'fe-input.json',s)
        package_root=Path(__file__).resolve().parents[2]
        env=dict(os.environ)
        env.update(PYTHONPATH=str(package_root),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
        command=[sys.executable,'-m','caelab.adapters.law_native_fe_worker',
                 '--input',str(folder/'fe-input.json'),'--output',str(folder/'fe')]
        save_json(folder/'fe-command.json',{'argv':command,'cwd':str(folder),'timeout_s':180,
            'owner':'existing JobManager/execution_control; no solver by name or imported PID',
            'compile':'NOT_REQUIRED','windows':'WSL_NOT_REQUIRED'})
        try:
            completed=run_owned_command(command,folder,'law-fe',timeout=180,env=env,owned_tree=True)
            if (folder/'fe/result.json').exists():
                result=read_result(folder/'fe',verify='all')
            else:
                result={'execution_status':'FAILED','responses':{},'checks':[],
                    'diagnostics':{'reason':'Worker returned no retained evaluation','return_code':completed.returncode,
                                   'FE_execution':'FAILED','build_execution':'NOT_REQUIRED'}}
        except ExecutionCleanupFailed:raise
        except (ExecutionCancelled,subprocess.TimeoutExpired) as error:
            result={'execution_status':'CANCELLED' if isinstance(error,ExecutionCancelled) else 'FAILED',
                'responses':{},'checks':[],'diagnostics':{'reason':str(error),'FE_execution':'INTERRUPTED',
                    'partial_evidence':'fe/fe-progress.json if produced; no failed trial commit',
                    'build_execution':'NOT_REQUIRED'}}
        result['artifacts']=[{'path':p.relative_to(folder).as_posix(),'sha256':file_hash(p)}
                            for p in sorted(folder.rglob('*')) if p.is_file()]
        return result
