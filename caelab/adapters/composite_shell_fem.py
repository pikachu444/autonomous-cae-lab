"""Frozen S8R laminate evaluation using existing execution ownership and readers."""
from pathlib import Path
import shutil
import subprocess

from caelab.composite_shell import BACKEND
from caelab.execution_control import (run_owned_command,check_cancelled,ExecutionCancelled,ExecutionCleanupFailed)
from caelab.storage import check_id,save_json
from caelab.composite_shell_results import read_native,retain,load
from .composite_shell_deck import validate_snapshot
from .shell_deck import read_bytes,sha,json_read
from .shell_fem import _same
from .beam_fem import log_diagnostics


def collect(output,model,*,execution_status):
    output=Path(output);native=output/'solver'
    observed=read_native(native,model)
    frames=observed['dat']['frames']
    complete=(observed['frd']['status']=='COMPLETE' and observed['dat']['status']=='COMPLETE' and
              frames and frames[-1]['load_parameter']==1. and observed['frd']['frames'][-1]['load_parameter']==1.)
    status=execution_status if execution_status!='SUCCEEDED' or complete else 'FAILED'
    post=output/'post';post.mkdir();(post/'source').mkdir()
    for path in native.iterdir():
        if path.is_file() and path.stat().st_size:
            data=read_bytes(path);(post/'source'/path.name).write_bytes(data)
            if sha(path)!=sha(post/'source'/path.name):raise ValueError('Native laminate output changed during retention')
    primary,metadata=retain(post,model,observed,execution_status=status)
    load(post/primary,metadata['composite_inspection'])
    responses={}
    if frames:
        last=frames[-1];rows=last['rows']
        for field,name,unit in (('S','ply_stress_native','MPa'),('E','ply_strain_native','1')):
            if field not in last['fields']:continue
            responses[name]={'kind':'field','unit':unit,'component':'TENSOR6','location':'layer_integration_point',
                'reduction':'none','value':[r[field]['values'] for r in rows],
                'metadata':{'association':'CELLS','component_names':['XX','YY','ZZ','XY','YZ','ZX'],
                    'coordinate_frame':'FREECAD_DOCUMENT_GLOBAL','recovery':'none_native_DAT',
                    'locations':[{k:r[k] for k in ('element_id','native_solid_id','integration_point','native_layer',
                                                 'ply_id','ui_position','inplane_ip','thickness_ip')} for r in rows],
                    'static':{k:last[k] for k in ('step','increment','load_parameter')},
                    'source':'solver/composite.dat','engineering_valid':False}}
    return {'execution_status':status,'responses':responses,'native_version':'2.22',
            'observation_status':'COMPLETE' if complete else 'PARTIAL',
            'post_artifact':{'relative':'post/'+primary,'bytes':(post/primary).stat().st_size,
                             'sha256':sha(post/primary),'native_metadata':metadata}}


class CompositeShellCalculixAdapter:
    backend=BACKEND
    version='1'

    def default_settings(self):
        return {'data_id':''}

    def validate_settings(self,settings):
        # Public diagnostics never resolve caller-supplied server paths.
        if not isinstance(settings,dict) or set(settings)!={'data_id'}:
            raise ValueError('등록한 적층 입력을 선택하세요.')
        check_id(settings['data_id'])
        return dict(settings)

    def describe_model(self,settings):
        self.validate_settings(settings)
        return {'backend':BACKEND,'profile':'S8R COMPOSITE','qualification':'UNKNOWN'}

    def describe_ports(self,settings):
        self.validate_settings(settings)
        return {'inputs':[],'outputs':[]}

    def run(self,settings,*,output,runtime=None):
        if not isinstance(settings,dict) or set(settings)-{'snapshot_path','data_id'} or not isinstance(settings.get('snapshot_path'),str):
            raise ValueError('Select the exact registered composite snapshot')
        if runtime:raise ValueError('Use the existing configured CalculiX PATH runtime')
        if 'data_id' in settings:check_id(settings['data_id'])
        output=Path(output).absolute()
        if any(p.is_symlink() for p in (output,*output.parents)):raise ValueError('Use a regular new laminate result folder')
        output.mkdir(parents=True,exist_ok=True)
        if any(output.iterdir()):raise ValueError('A laminate attempt must not overwrite an earlier result')
        result={'backend':BACKEND,'adapter_version':self.version,'execution_status':'FAILED',
                'qualification':'UNKNOWN','engineering_valid':False,'responses':{},
                'limitations':['S8R explicit isotropic/orthotropic linear elastic laminate, static Fixed/pressure',
                    'DAT GLOBAL S/E are original layer IP tuples; FRD S/E are extrapolated/averaged',
                    'COORD/RF are not requested; no failure law or physical qualification claimed']}
        source=model=pins=executable=binary_sha=None;native=None
        try:
            check_cancelled();source=Path(settings['snapshot_path'])
            manifest,model,mesh,pins=validate_snapshot(source)
            retained=output/'retained_inputs';retained.mkdir()
            for name,pin in pins.items():
                _same(source.parent/name,pin);(retained/name).write_bytes(read_bytes(source.parent/name));_same(retained/name,pin)
            native=output/'solver';native.mkdir();(native/'composite.inp').write_bytes(read_bytes(retained/'composite.inp'))
            command=shutil.which('ccx')
            if not command:raise RuntimeError('Configured CalculiX 2.22 ccx is unavailable')
            executable=Path(command).resolve(strict=True);binary_sha=sha(executable)
            result['runtime']={'executable':str(executable),'sha256':binary_sha}
            completed=run_owned_command([str(executable),'-i','composite'],native,'ccx_composite',owned_tree=True)
            result.update(return_code=completed.returncode,execution_status='SUCCEEDED' if completed.returncode==0 else 'FAILED')
            logs=log_diagnostics(completed.stdout or '',completed.stderr or '')
            result['native_diagnostics']=logs
            if logs['errors']:result['execution_status']='FAILED'
            check_cancelled()
        except ExecutionCleanupFailed:raise
        except ExecutionCancelled as error:result.update(execution_status='CANCELLED',diagnostics={'reason':str(error)})
        except (ValueError,KeyError,TypeError,AttributeError,IndexError,OverflowError,OSError,RuntimeError,subprocess.TimeoutExpired) as error:
            result.update(execution_status='FAILED',diagnostics={'type':type(error).__name__,'reason':str(error)})
        try:
            if pins is not None:
                for name,pin in pins.items():_same(source.parent/name,pin);_same(output/'retained_inputs'/name,pin)
            if executable is not None and sha(executable)!=binary_sha:raise ValueError('Configured solver changed while executing')
            if native is not None and all((native/('composite'+ext)).is_file() for ext in ('.12d','.frd','.dat')):
                result.update(collect(output,model,execution_status=result['execution_status']))
            elif result['execution_status']=='SUCCEEDED':raise ValueError('Native layer results were not produced')
        except (ValueError,KeyError,TypeError,IndexError,OverflowError,OSError) as error:
            if result['execution_status']!='CANCELLED':result['execution_status']='FAILED'
            result['responses']={};result.pop('post_artifact',None)
            result.setdefault('diagnostics',{})['collection_error']=str(error)
        result['artifacts']=[{'relative':p.relative_to(output).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}
                             for p in sorted(output.rglob('*')) if p.is_file()]
        save_json(output/'composite_execution.json',result)
        return result


def read_saved_run(folder):
    folder=Path(folder).absolute();result=json_read(folder/'composite_execution.json')
    if result.get('backend')!=BACKEND:raise ValueError('Not a saved laminate evaluation')
    from caelab.shell_inspection import _member
    seen=set()
    for row in result['artifacts']:
        name=row['relative'];path=_member(folder,name)
        if name in seen or path.stat().st_size!=row['bytes'] or sha(path)!=row['sha256']:
            raise ValueError('Saved laminate artifact changed: '+name)
        seen.add(name)
    artifact=result.get('post_artifact')
    if artifact:
        load(_member(folder,artifact['relative']),artifact['native_metadata']['composite_inspection'])
    return result
