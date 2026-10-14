"""Frozen native beam execution through the existing execution owner.

No CAD imports, remeshing, guessed rotations or model edits occur in this
adapter. Source models, failed native outputs and older result directories are
never reused as writable solver working directories.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from ..beam_model import BACKEND, validate_model
from ..beam_deck import render, matches_saved_input
from ..beam_results import (read_frd, write_post, final_responses, sha,
                            _read_bytes, _printed_close, UNAVAILABLE)
from ..execution_control import (run_owned_command, check_cancelled,
                                  ExecutionCancelled, ExecutionCleanupFailed)
from ..storage import check_id, save_json

KIND = 'freecad-beam-frozen'


def validate_snapshot(path):
    """Reuse the frozen native file-set contract, with beam-owned contents."""
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('snapshot_path must be an absolute native manifest path')
    payload = _read_bytes(path)
    if len(payload)>8*1024**2:
        raise ValueError('Native manifest exceeds 8 MiB')
    manifest = json.loads(payload)
    if manifest.get('kind')!=KIND or manifest.get('schema_version')!='1':
        raise ValueError('Expected a completed native beam snapshot')
    check_id(manifest['id'])
    if manifest.get('native_version',[])[:3]!=['1','1','4']:
        raise ValueError('Beam native export requires FreeCAD 1.1.4')
    if manifest.get('input_file')!='beam.inp' or manifest.get('editable_project')!='editable.caepre':
        raise ValueError('Beam snapshot must retain editable native model/project and beam.inp')
    expected={'editable.FCStd','editable.caepre','mesh.json','beam.inp'}
    entries=manifest.get('files',[])
    if len(entries)!=len(expected) or {r.get('relative') for r in entries}!=expected:
        raise ValueError('Unexpected or incomplete frozen native beam file set')
    pins={path.name:{'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}}
    if path.name!='snapshot.json':
        raise ValueError('Expected the completed native snapshot.json manifest')
    for entry in entries:
        name=entry['relative']
        data=_read_bytes(path.parent/name)
        digest=hashlib.sha256(data).hexdigest()
        if type(entry.get('bytes')) is not int or len(data)!=entry['bytes'] or digest!=entry.get('sha256'):
            raise ValueError('Frozen native beam source changed: '+name)
        pins[name]={'bytes':len(data),'sha256':digest}
    model=json.loads(_read_bytes(path.parent/'mesh.json'))
    validate_model(model)
    if not matches_saved_input(_read_bytes(path.parent/'beam.inp').decode('ascii'), model):
        raise ValueError('Frozen beam deck does not match its native settings/connectivity')
    writers=manifest.get('writers',{})
    if writers.get('output')!='OUTPUT=2D / SECTION FORCES':
        raise ValueError('Beam native output contract is not explicit')
    return manifest,model,pins


def check_pins(folder,pins):
    for name,pin in pins.items():
        path=Path(folder)/name
        if path.stat().st_size!=pin['bytes'] or sha(path)!=pin['sha256']:
            raise ValueError('Frozen source association changed: '+name)


def log_diagnostics(stdout,stderr):
    """CCX can return zero with *ERROR; never substitute exit-code-only success."""
    lines=(stdout+'\n'+stderr).splitlines()
    errors=[s.strip() for s in lines if re.search(r'\*\s*ERROR\b',s,re.I)]
    warnings=[s.strip() for s in lines if re.search(r'\*\s*WARNING\b',s,re.I)]
    return {'errors':errors,'warnings':warnings,
        'has_unreviewed_native_diagnostic':bool(errors or warnings)}


def read_saved_run(folder):
    """Open the same sealed native files, including failures, without a process."""
    folder=Path(folder).absolute()
    receipt=json.loads(_read_bytes(folder/'beam_execution.json'))
    if receipt.get('backend')!=BACKEND or receipt.get('schema_version')!='1':
        raise ValueError('This is not a saved beam execution')
    artifacts=receipt.get('artifacts',[])
    names=[item.get('relative') for item in artifacts]
    if len(set(names))!=len(names):raise ValueError('Duplicate saved beam artifact')
    required={p.relative_to(folder).as_posix() for p in (folder/'solver'/'beam.frd',folder/'frozen_input'/'snapshot.json') if p.exists()}
    if not required.issubset(names):raise ValueError('Unsealed beam input/result file')
    for item in artifacts:
        name=item.get('relative')
        if (not isinstance(name,str) or not name or '\\' in name or ':' in name or
                Path(name).is_absolute() or any(p in ('','..','.') for p in name.split('/'))):
            raise ValueError('Unsafe saved beam artifact path')
        path=folder/name
        if path.stat().st_size!=item['bytes'] or sha(path)!=item['sha256']:
            raise ValueError('Saved beam result changed: '+name)
    model=None;observed=None
    frozen=folder/'frozen_input'/'snapshot.json'
    if frozen.exists():
        _,model,pins=validate_snapshot(frozen)
        if receipt.get('input_pins')!=pins:
            raise ValueError('Saved beam input association differs')
    frd=folder/'solver'/'beam.frd'
    if model is not None and frd.exists():
        # Reader diagnosis is part of a failed attempt, not a reason to lose
        # its editable input/logs. Corrupt fields remain unavailable.
        try:
            executed=folder/'solver'/'beam.inp'
            if not executed.is_file() or sha(executed)!=pins['beam.inp']['sha256']:
                raise ValueError('Saved executed beam deck differs from the frozen conditions; fields are unavailable')
            observed=read_frd(frd,model,allow_partial=receipt['execution_status']!='SUCCEEDED')
        except (ValueError,UnicodeError) as exc:
            receipt={**receipt,'saved_reader_error':str(exc)}
    metadata = receipt.get('post_artifact', {}).get('native_metadata', {})
    if 'beam_inspection' in metadata:
        from ..beam_inspection import validate_metadata
        checked = validate_metadata(folder/'post'/'beam.pvd', metadata)
        context = checked['execution']
        if any(context.get(key) != receipt.get(key) for key in
               ('execution_status', 'snapshot_id', 'input_pins', 'runtime', 'native_return_code')):
            raise ValueError('Saved beam execution and Post bundle identity differ')
    return {'folder':str(folder),'execution':receipt,'model':model,'observed':observed}


def publish_post(output, observed, model, execution):
    """Seal the retained raw companion before the shared native registrar sees it."""
    from ..beam_inspection import retain
    artifact = write_post(Path(output)/'post', observed, model,
                          source_status=execution['execution_status'])
    return retain(output, artifact, execution)


class BeamFemCalculixAdapter:
    backend=BACKEND
    version='1'

    def run(self,settings,*,output,runtime=None):
        if not isinstance(settings,dict) or set(settings)-{'snapshot_path','data_id'} or not isinstance(settings.get('snapshot_path'),str):
            raise ValueError('Beam run requires snapshot_path and optional registered data_id only')
        if runtime:
            raise ValueError('Beam CalculiX uses configured PATH; runtime overrides are not admitted')
        if 'data_id' in settings:check_id(settings['data_id'])
        output=Path(output).absolute()
        if any(p.is_symlink() for p in (output,*output.parents)):
            raise ValueError('Output must be a regular new directory')
        output.mkdir(parents=True,exist_ok=True)
        if any(output.iterdir()):
            raise ValueError('Beam run refuses to overwrite an existing result or attempt')
        result={'schema_version':'1','backend':BACKEND,'execution_status':'REJECTED',
                'responses':{},'checks':[],'qualification':'UNKNOWN','decision':'NOT_RELEASED',
                'engineering_valid':False,'diagnostics':{},'artifacts':[],
                'unavailable':UNAVAILABLE.copy()}
        model=None;retained=None;pins=None;executable=None;binary_hash=None;native=None;launched=False
        try:
            source=Path(settings['snapshot_path'])
            manifest,model,pins=validate_snapshot(source)
            retained=output/'frozen_input';retained.mkdir()
            for name in pins:
                shutil.copyfile(source.parent/name,retained/name)
            validate_snapshot(retained/'snapshot.json')
            check_pins(retained,pins)
            result.update(snapshot_id=manifest['id'],data_id=settings.get('data_id'),input_pins=pins,
                checks=[{'name':'native_beam_snapshot','status':'PASS'}],execution_status='FAILED')
            check_cancelled()
            command=shutil.which('ccx')
            if command is None:
                raise RuntimeError('CalculiX 2.22 실행 파일 ccx를 PATH에서 찾지 못했습니다. 설정 후 새 계산을 실행하세요.')
            executable=Path(command).resolve(strict=True);binary_hash=sha(executable)
            result['runtime']={'executable':str(executable),'sha256':binary_hash,'configuration':'configured PATH','version':'2.22'}
            native=output/'solver';native.mkdir()
            # The Windows build returns 201 for -v despite printing 2.22.
            # Verify the exact version from the actual FRD below, as for shells.
            # A physical run must still return zero and retain the same binary.
            if sha(executable)!=binary_hash:
                raise ValueError('Native executable changed before calculation')
            deck=native/'beam.inp';shutil.copyfile(retained/'beam.inp',deck)
            check_cancelled();launched=True
            solved=run_owned_command([str(executable),'-i','beam'],native,'ccx_beam',owned_tree=True)
            result['diagnostics']=log_diagnostics(solved.stdout,solved.stderr)
            result['native_return_code']=solved.returncode
            check_cancelled()
            check_pins(source.parent,pins);check_pins(retained,pins)
            if sha(deck)!=pins['beam.inp']['sha256'] or sha(executable)!=binary_hash:
                raise ValueError('Native deck/executable changed during calculation')
            observed=read_frd(native/'beam.frd',model)
            if not _printed_close(observed['frames'][-1]['load_parameter_token'],1.):
                raise ValueError('Native result has not reached the requested final static load parameter')
            if solved.returncode or result['diagnostics']['has_unreviewed_native_diagnostic']:
                raise RuntimeError('계산 로그의 오류·경고를 확인하세요. 종료 코드 0만으로 성공 처리하지 않습니다.')
            # Explicitly diagnostic oblique models never become ordinary success.
            if model['draft']['diagnostic_oblique']:
                result.update(execution_status='FAILED',native_output_status='PARTIAL_FAILURE',diagnostic_only=True,
                              diagnostics={**result['diagnostics'],'reason':'비축정렬 경로의 독립 검증 전 진단 계산입니다.'})
            else:
                result.update(execution_status='SUCCEEDED',responses=final_responses(observed,model))
            result['post_artifact']=publish_post(output,observed,model,result)
            result['complete_native_frames']=len(observed['frames'])
            result['native_version']=observed['native_version']
        except ExecutionCleanupFailed:
            # The existing owner must finish process-tree cleanup before sealing
            # any output. Never race a still-running process with result reads.
            raise
        except ExecutionCancelled as exc:
            result.update(execution_status='CANCELLED',responses={},diagnostics={'reason':str(exc)})
        except (ValueError,KeyError,TypeError,AttributeError,IndexError,OverflowError,OSError,
                RuntimeError,UnicodeError,subprocess.TimeoutExpired) as exc:
            if result['execution_status']=='SUCCEEDED':
                result.update(execution_status='FAILED',native_execution_status='SUCCEEDED')
            result.update(responses={},diagnostics={**result['diagnostics'],'type':type(exc).__name__,'reason':str(exc)})
        # Retain complete frames after a stopped/failed calculation only after
        # independently checking the *retained* input and exact executed deck.
        if result['execution_status'] not in ('SUCCEEDED','REJECTED') and 'post_artifact' not in result and launched and model is not None:
            try:
                check_pins(retained,pins)
                if sha(native/'beam.inp')!=pins['beam.inp']['sha256'] or sha(executable)!=binary_hash:
                    raise ValueError('Cannot associate partial output with the frozen executed input')
                observed=read_frd(native/'beam.frd',model,allow_partial=True)
                result['complete_native_frames']=len(observed['frames'])
                result['partial_output']={'complete_file':observed['complete_file'],'truncation':observed['truncation'],
                    'load_parameter':observed['frames'][-1]['static']['load_parameter']}
                if result['execution_status']=='FAILED':result['native_output_status']='PARTIAL_FAILURE'
                result['post_artifact']=publish_post(output,observed,model,result)
            except (ValueError,KeyError,TypeError,OSError,UnicodeError) as exc:
                result['diagnostics']['partial_reader_error']=str(exc)
        result['limitations']=[
            'Straight uniform B32R/RECT; linear static isotropic elasticity; no branch/joint/offset/curved beam.',
            'Results use original beam nodes, not expanded topology. No synthetic rotation or support reaction moment.',
            'Section force slots have separate N and Nmm channels, never MPa or von Mises.',
            'Non-axis-aligned models are diagnostic only until independent CalculiX 2.22 verification.',
            'Native computation success is not an engineering acceptance.']
        # A failed/rejected/cancelled attempt also gets a stable reader receipt.
        result['artifacts']=[{'relative':p.relative_to(output).as_posix(),'path':p.relative_to(output).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}
            for p in sorted(output.rglob('*')) if p.is_file() and not p.is_symlink()]
        save_json(output/'beam_execution.json',result)
        return result
