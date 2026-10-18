"""Remote attempts inside the existing JobManager and immutable batch exchange.

Only explicit run/reconnect/cancel/collect dispatch network commands.
Catalog, status, result reading and draft inspection never connect to a host.
"""
import argparse
import base64
from copy import deepcopy
import json
from pathlib import Path, PurePosixPath
import re
import time

from filelock import FileLock
from . import numerical
from .evaluation import file_hash, save_evaluation
from .execution_control import (CancellationToken, ExecutionCancelled,
    ExecutionCleanupFailed, cancellation_scope, check_cancelled)
from .remote_schedulers import digest, fingerprint, relative_path, job_id as scheduler_job_id
from .storage import canonical_hash, check_id, load_json, save_json, utc_now

OPERATIONS = {'remote.run', 'remote.reconnect', 'remote.cancel', 'remote.collect'}
DEFAULT_OUTPUTS = ['results.json', 'solver.stdout.log', 'solver.stderr.log',
                   'scheduler.stdout.log', 'scheduler.stderr.log']


def host_configuration(workbench, host_id):
    check_id(host_id)
    host = deepcopy(workbench.config.get('remote_hosts', {}).get(host_id))
    if not isinstance(host, dict) or host.get('enabled') is not True:
        raise ValueError('선택한 원격 실행 위치가 등록되지 않았습니다. 초안과 로컬 작업은 유지됩니다.')
    allowed = {'enabled','label','target','port','scheduler','root','queue','account','python',
               'command','runtime','responses','files','outputs','max_threads','max_memory_mb',
               'max_wall_seconds','transfer_limit','command_timeout','poll_seconds',
               'monitor_seconds','cancel_seconds','ssh_executable','post_outputs'}
    if set(host) - allowed:
        raise ValueError('Remote registrations must not contain credentials, environment values or arbitrary SSH options')
    if host.get('scheduler') not in {'ssh', 'slurm', 'pbs'}:
        raise ValueError('Select SSH, Slurm or OpenPBS')
    if not re.fullmatch(r'(?:[A-Za-z0-9_.-]+@)?[A-Za-z0-9][A-Za-z0-9_.-]*', str(host.get('target',''))):
        raise ValueError('Register one explicit SSH host or existing alias')
    root = host.get('root')
    if not isinstance(root, str) or not root.startswith('/') or '..' in PurePosixPath(root).parts or any(c in root for c in '\x00\n\r'):
        raise ValueError('Register the existing absolute POSIX working root')
    if type(host.get('port',22)) is not int or not 1 <= host.get('port',22) <= 65535:
        raise ValueError('Invalid registered SSH port')
    for key in ('queue','account'):
        if not isinstance(host.get(key,''), str) or (host.get(key) and not re.fullmatch(r'[A-Za-z0-9_.@-]+',host[key])):
            raise ValueError('Queue/account must be explicit scheduler names')
    command = host.get('command')
    if not isinstance(command,list) or not command or any(not isinstance(x,str) or not x or any(c in x for c in '\x00\n\r') for x in command):
        raise ValueError('Register a foreground runtime argv, not a shell expression')
    runtime = host.get('runtime')
    if not isinstance(runtime,dict) or set(runtime) != {'id','version'} or any(not isinstance(v,str) or not v.strip() for v in runtime.values()):
        raise ValueError('Declare the selected runtime identity and build/version; never infer a local runtime')
    for key, default in [('max_threads',1),('max_memory_mb',1024),('max_wall_seconds',3600),
                         ('transfer_limit',16*1024**2),('command_timeout',45),('monitor_seconds',300),('cancel_seconds',30)]:
        value = host.get(key,default)
        if type(value) is not int or value <= 0:
            raise ValueError(key + ' requires a positive integer budget')
        host[key] = value
    if host['transfer_limit'] > 16*1024**2:
        raise ValueError('Remote transfer keeps the existing 16 MiB exchange limit')
    poll = host.get('poll_seconds',1.)
    if type(poll) not in (int,float) or not 0.05 <= poll <= 60:
        raise ValueError('Remote poll interval must be between .05 and 60 seconds')
    host['poll_seconds'] = poll
    if not isinstance(host.get('responses'),dict) or not host['responses']:
        raise ValueError('Register expected response names with exact kind and unit')
    for name, response in host['responses'].items():
        if not isinstance(name,str) or not isinstance(response,dict) or set(response) != {'kind','unit'} or response['kind'] not in {'scalar','series','field','event'} or not isinstance(response['unit'],str) or not response['unit']:
            raise ValueError('Each remote response needs its exact kind and unit')
    files = host.get('files',{})
    if not isinstance(files,dict): raise ValueError('Remote input files must be registered explicitly')
    for name, source in files.items():
        relative_path(name)
        if name in DEFAULT_OUTPUTS or name == 'batch.json': raise ValueError('Input/output names conflict')
        if not isinstance(source,str): raise ValueError('Register local input paths in operator configuration')
    outputs = host.get('outputs',[])
    if not isinstance(outputs,list): raise ValueError('Register explicit output files')
    for name in outputs:
        relative_path(name)
        if name in files or name == 'batch.json': raise ValueError('An output cannot replace an input')
    names = [*files, *DEFAULT_OUTPUTS, *outputs, 'batch.json']
    folded = {}
    for name in names:
        previous = folded.setdefault(name.casefold(), name)
        if previous != name: raise ValueError('Remote files differ only by case on Windows')
    post = host.get('post_outputs', [])
    if not isinstance(post, list): raise ValueError('Declare explicit spatial output files')
    for item in post:
        if not isinstance(item, dict) or set(item) != {'relative','native_metadata'}:
            raise ValueError('Spatial outputs require a file and physical metadata')
        relative_path(item['relative'])
        if item['relative'] not in outputs or Path(item['relative']).suffix.lower() not in {'.vtu','.pvd'}:
            raise ValueError('Spatial outputs must be declared VTU/PVD output files')
        if not isinstance(item['native_metadata'], dict): raise ValueError('Declare spatial units, location and time')
    host.setdefault('python','python3')
    if not isinstance(host['python'],str) or not host['python'] or any(c in host['python'] for c in '\x00\n\r'):
        raise ValueError('Register the existing remote Python executable')
    if Path(host.get('ssh_executable','ssh')).name.lower() not in {'ssh','ssh.exe'}:
        raise ValueError('Use an existing OpenSSH executable, not an arbitrary local command')
    return host


def _source(workbench, identifier):
    folder = workbench.root / 'results' / check_id(identifier)
    path = folder / 'remote.json'
    record = load_json(path)
    if record.get('schema') != 'caelab.remote-attempt.v1': raise ValueError('Not a retained remote attempt')
    origin = check_id(record['origin_job'])
    intent_folder = workbench.root / 'results' / origin
    intent = load_json(intent_folder / 'remote-intent.json')
    if fingerprint(intent) != record['intent_sha256']:
        raise ValueError('Retained remote input/target checksum differs')
    for name,sha in intent['files'].items():
        relative_path(name)
        if file_hash(intent_folder/'inputs'/name) != sha:
            raise ValueError('Retained remote input file changed')
    host = host_configuration(workbench, record['host_id'])
    if _binding(host) != record['host_binding']:
        raise ValueError('The registered host/runtime/path changed; the retained job cannot be retargeted')
    job = workbench.manager.status(origin)
    args = job['arguments']
    if job['operation'] != 'remote.run' or args.get('host_id') != record['host_id'] or args.get('batch_job') != record['batch_job']:
        raise ValueError('Retained attempt differs from the original JobManager submission')
    review = inspect(workbench, args['host_id'], args['batch_job'], args.get('remote_resources'))
    batch = (intent_folder/'inputs'/'batch.json').read_bytes()
    if (record['token'] != 'R'+origin[1:] or record['exchange_id'] != review['manifest']['exchange_id'] or
        digest(batch) != intent['batch_sha256'] or json.loads(batch) != review['manifest'] or
        intent['resources'] != review['resources'] or any(intent.get(k) != host.get(k, '') for k in ('command','runtime','python','scheduler','queue','account')) or
        intent['responses'] != host['responses'] or intent.get('post_outputs', []) != host.get('post_outputs', []) or
        intent['outputs'] != list(dict.fromkeys(DEFAULT_OUTPUTS+host.get('outputs',[]))) or
        intent['transfer_limit'] != host['transfer_limit'] or set(intent['files']) != {'batch.json',*host.get('files',{})} or
        record['remote_directory'] != str(PurePosixPath(host['root'])/record['token'])):
        raise ValueError('Retained token, source values, resources or runtime differs')
    return record, intent, intent_folder, host


def _binding(host):
    return fingerprint({key:host.get(key) for key in ('target','port','scheduler','root','queue','account','python','command','runtime','responses','files','outputs','post_outputs','transfer_limit')})


def inspect(workbench, host_id, batch_job, resources=None):
    host = host_configuration(workbench, host_id)
    result = workbench.result(check_id(batch_job))
    manifest = deepcopy(result.get('manifest'))
    if not isinstance(manifest,dict) or manifest.get('kind') != 'file_batch' or not manifest.get('exchange_id'):
        raise ValueError('Select a retained export_batch job with an exact exchange ID')
    # Reuse typed-domain/candidate validation, including missing NOT_EVALUATED rows.
    numerical.import_batch(manifest, [])
    selected = {'threads':1, 'memory_mb':min(1024,host['max_memory_mb']), 'wall_seconds':min(3600,host['max_wall_seconds'])}
    if resources is not None:
        if not isinstance(resources,dict) or set(resources)-set(selected): raise ValueError('Unknown remote resource request')
        selected.update(resources)
    for key in selected:
        if type(selected[key]) is not int or not 0 < selected[key] <= host['max_' + key]:
            raise ValueError('Remote resource request exceeds the registered host budget: ' + key)
    return {'host_id':host_id, 'scheduler':host['scheduler'], 'runtime':host['runtime'],
            'queue':host.get('queue',''), 'account':host.get('account',''), 'resources':selected,
            'batch_job':batch_job, 'manifest':manifest, 'manifest_sha256':canonical_hash(manifest),
            'host_binding':_binding(host), 'network_calls':0, 'live_acceptance':'NOT_RUN',
            'resource_enforcement':{'threads':'OMP_NUM_THREADS', 'memory':'HINT_ONLY' if host['scheduler']=='ssh' else 'SCHEDULER_REQUEST',
                                    'wall_time':'OWNED_SUPERVISOR_AND_SCHEDULER' if host['scheduler']!='ssh' else 'OWNED_SUPERVISOR'}}


def validate_arguments(workbench, operation, arguments):
    allowed = {'host_id','batch_job','remote_resources','label'} if operation == 'remote.run' else {'source_job','label'}
    if operation not in OPERATIONS or not isinstance(arguments,dict) or set(arguments)-allowed:
        raise ValueError('Use the registered remote operation and exact source job')
    if operation == 'remote.run': return inspect(workbench, arguments['host_id'], arguments['batch_job'], arguments.get('remote_resources'))
    record, _, _, _ = _source(workbench, arguments['source_job'])
    return record


def catalog(workbench):
    jobs = workbench.manager.list()
    by_id = {job['id']: job for job in jobs}
    hosts = []
    for identifier in workbench.config.get('remote_hosts',{}):
        try:
            host = host_configuration(workbench,identifier)
            hosts.append({'id':identifier,'label':host.get('label',identifier),'scheduler':host['scheduler'],
                          'runtime':host['runtime'],'queue':host.get('queue',''),'account':host.get('account',''),
                          'limits':{k:host[k] for k in ('max_threads','max_memory_mb','max_wall_seconds')}})
        except (ValueError,TypeError,KeyError):
            hosts.append({'id':identifier,'label':identifier,'error':'등록한 실행 위치 설정을 확인하세요.'})
    batches = []
    for job in jobs:
        if job['operation'] == 'batch_export' and job.get('result_refs'):
            batches.append({'id':job['id'],'label':job['arguments'].get('label',job['arguments'].get('case_id','실행 묶음'))})
    attempts = []
    for path in sorted((workbench.root/'results').glob('*/remote.json')):
        record = load_json(path)
        job = by_id.get(path.parent.name, {})
        attempts.append({'id':path.parent.name,'label':record.get('label','원격 계산'),
                         'state':record['state'],'scheduler_id':record.get('scheduler_id'),
                         'host_id':record['host_id'],'updated_utc':record['updated_utc'],
                         'job_state':job.get('state'),
                         **{key:deepcopy(record.get(key)) for key in ('terminated',
                             'termination_confirmation','cancel_requested','imported_count','missing_count')},
                         'error':deepcopy(job.get('error') or record.get('error'))})
    retained = {row['id'] for row in attempts}
    for job in jobs:
        if job['operation'] in OPERATIONS and job['id'] not in retained:
            attempts.append({'id':job['id'],'label':job['arguments'].get('label','원격 계산'),
                'state':job['state'],'scheduler_id':None,'host_id':job['arguments'].get('host_id'),
                'updated_utc':job.get('updated_utc',job['created_utc']),
                'job_state':job['state'],'error':deepcopy(job.get('error')),
                **{key:None for key in ('terminated','termination_confirmation',
                    'cancel_requested','imported_count','missing_count')}})
    return {'hosts':hosts,'batches':batches,'attempts':attempts,'live_acceptance':'NOT_RUN','network_calls':0,
            'store_key':canonical_hash(str(workbench.root)),
            'requests':[{key:deepcopy(job.get(key)) for key in ('id','operation','arguments','request_id','state','result_refs')}
                        for job in jobs if job['operation'] in OPERATIONS]}


def status(workbench, identifier):
    path = workbench.root/'results'/check_id(identifier)/'remote.json'
    return deepcopy(load_json(path))


def _reject_remote_refs(value):
    if isinstance(value, dict):
        if 'data_ref' in value:
            raise ValueError('Remote arrays must be explicit finite values, never external data_ref paths')
        for item in value.values(): _reject_remote_refs(item)
    elif isinstance(value, list):
        for item in value: _reject_remote_refs(item)


def _publish_post(workbench, output, identifier, intent):
    """Publish retained spatial bytes through the existing bounded native reader."""
    from .native_inputs import register_native_input
    from uuid import uuid4
    published = {'post_inputs': []}
    try:
        for item in intent.get('post_outputs', []):
            source = output/'recovered'/item['relative']
            receipt = register_native_input(workbench.root, output/'recovered', source, 'D'+uuid4().hex,
                root_id='job:'+identifier, relative=item['relative'],
                limit=min(intent['transfer_limit'], workbench.config.get('local_input_max_bytes', 2*1024**3)),
                native_metadata=item['native_metadata'])
            published['post_inputs'].append({k:receipt[k] for k in ('id','format','sha256')})
        if published['post_inputs']: published['post_input'] = deepcopy(published['post_inputs'][0])
    except (OSError, ValueError, KeyError, TypeError) as error:
        # Already registered files remain available; failure must not imply every output is ready.
        published['post_registration'] = {'status':'FAILED', 'message':str(error)}
    return published


def _prepare(workbench, arguments, identifier, output):
    review = inspect(workbench, arguments['host_id'],arguments['batch_job'],arguments.get('remote_resources'))
    host = host_configuration(workbench,arguments['host_id'])
    manifest_bytes = (json.dumps(review['manifest'],ensure_ascii=False,allow_nan=False,sort_keys=True)+'\n').encode()
    files = {'batch.json':manifest_bytes}
    for name, source in host.get('files',{}).items():
        path = Path(source)
        if any(part.lower() in {'.ssh','.aws','.azure','.kube'} for part in path.parts):
            raise ValueError('Authentication/configuration directories are not remote inputs')
        if path.is_symlink() or not path.is_file(): raise ValueError('Registered remote input is missing or redirected')
        before = file_hash(path)
        files[name] = path.read_bytes()
        if b'PRIVATE KEY-----' in files[name]: raise ValueError('Authentication keys are not transferable input files')
        if digest(files[name]) != before or file_hash(path) != before: raise ValueError('Registered input changed during staging')
    if sum(map(len,files.values())) > host['transfer_limit']: raise ValueError('Input exceeds the registered transfer budget')
    intent = {'scheduler':host['scheduler'],'queue':host.get('queue',''),'account':host.get('account',''),
              'runtime':host['runtime'],'python':host['python'],'command':host['command'],
              'resources':review['resources'],'files':{name:digest(data) for name,data in files.items()},
              'batch_sha256':digest(manifest_bytes),'responses':host['responses'],
              'outputs':list(dict.fromkeys(DEFAULT_OUTPUTS + host.get('outputs',[]))),
              'post_outputs':deepcopy(host.get('post_outputs', [])),
              'transfer_limit':host['transfer_limit']}
    for name, data in files.items():
        path = output/'inputs'/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
    save_json(output/'remote-intent.json',intent)
    record = {'schema':'caelab.remote-attempt.v1','origin_job':identifier,'host_id':arguments['host_id'],
              'host_binding':review['host_binding'],'token':'R'+identifier[1:], 'intent_sha256':fingerprint(intent),
              'batch_job':arguments['batch_job'],'exchange_id':review['manifest']['exchange_id'],
              'queue':intent['queue'],'account':intent['account'],'runtime':intent['runtime'],
              'remote_directory':str(PurePosixPath(host['root'])/('R'+identifier[1:])),
              'state':'PREPARING','scheduler_id':None,'terminated':False,
              'label':arguments.get('label','원격 계산'),'live_acceptance':'NOT_RUN'}
    return record, intent, output, host


def execute(workbench, operation, arguments, identifier, *, transport=None):
    """JobManager callback. Reconnection never calls submit, even after lost replies."""
    validate_arguments(workbench,operation,arguments)
    output = workbench.root/'results'/check_id(identifier)
    output.mkdir(parents=True,exist_ok=False)
    if operation == 'remote.run':
        record,intent,origin_folder,host = _prepare(workbench,arguments,identifier,output)
    else:
        original,intent,origin_folder,host = _source(workbench,arguments['source_job'])
        record = deepcopy(original)
        record['source_job'] = arguments['source_job']
    from .remote_transport import SSHTransport
    transport = transport or SSHTransport(host)
    manifest_bytes = (origin_folder/'inputs'/'batch.json').read_bytes()
    if digest(manifest_bytes) != intent['batch_sha256']: raise ValueError('Retained batch bytes changed')
    manifest = json.loads(manifest_bytes)
    sequence = 0
    def persist(**changes):
        record.update(changes,updated_utc=utc_now())
        save_json(output/'remote.json',record)
    def call(action, **extra):
        nonlocal sequence
        sequence += 1
        payload = dict(token=record['token'],base=host['root'],intent=intent,intent_sha256=record['intent_sha256'],**extra)
        # Serialize one SSH command, not the whole monitor: a separate cancel can intervene.
        with FileLock(origin_folder/'remote-control.lock', timeout=host['command_timeout']+1):
            value = transport.request(action,payload,output/'commands'/f'{sequence:04d}-{action}')
        if not isinstance(value,dict): raise ValueError('Remote response must be a receipt')
        if value.get('terminated') is True and (value.get('state') not in {'COMPLETED','FAILED','CANCELLED','TIMEOUT'} or
            value.get('termination_confirmation') not in {'SCHEDULER_ACCOUNTING','OWNED_CHILD_REAPED','SUBMISSION_ATOMICALLY_BLOCKED'}):
            raise ValueError('Actual remote termination has no recognized confirmation')
        known = record.get('scheduler_id')
        incoming = value.get('scheduler_id')
        if incoming is not None:
            scheduler_job_id(host['scheduler'],incoming)
            if known is not None and incoming != known: raise ValueError('Remote scheduler ID changed')
        persist(**{key:deepcopy(value[key]) for key in ('state','scheduler_state','scheduler_id','terminated','exit_code','termination_confirmation','cancel_requested') if key in value})
        return value
    def seal(execution_status, **extra):
        artifacts = [{'path':p.relative_to(output).as_posix(),'sha256':file_hash(p)}
                     for p in sorted((output/'recovered').rglob('*')) if p.is_file()]
        result = {'kind':'remote_batch','execution_status':execution_status,'responses':{},
                  'remote':deepcopy(record),'artifacts':artifacts,'diagnostics':{'decision':'NOT_RELEASED'},**extra}
        save_evaluation(result,output,existing=True)
        return result
    def recover():
        fetched = call('fetch')
        if fetched.get('terminated') is not True or fetched.get('input_sha256') != intent['files']:
            raise ValueError('Recovered input/termination receipt differs')
        entries = fetched.get('files')
        if not isinstance(entries,dict) or set(entries)-set(intent['outputs']): raise ValueError('Unexpected remote output file')
        retained = {}; total = 0
        for name, entry in entries.items():
            relative_path(name)
            data = base64.b64decode(entry['base64'],validate=True); total += len(data)
            if total > intent['transfer_limit'] or digest(data) != entry['sha256']: raise ValueError('Remote output transfer checksum differs')
            retained[name] = data
        # Keep exact failed output before semantic admission; no existing result is overwritten.
        for name,data in retained.items():
            path = output/'recovered'/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
        rows = []
        if 'results.json' in retained:
            returned = json.loads(retained['results.json'])
            if not isinstance(returned,dict) or returned.get('input_manifest_sha256') != intent['batch_sha256'] or returned.get('runtime') != intent['runtime']:
                raise ValueError('Remote result belongs to a different input/runtime')
            rows = returned['results']
            if not isinstance(rows,list): raise ValueError('Remote result rows must be a list')
            for row in rows:
                responses = row.get('responses',{})
                _reject_remote_refs(row)
                if row.get('execution_status') == 'SUCCEEDED' and set(responses) != set(intent['responses']):
                    raise ValueError('Successful remote result is missing a declared response')
                for name,response in responses.items():
                    if name not in intent['responses'] or any(response.get(key) != value for key,value in intent['responses'][name].items()):
                        raise ValueError('Remote response unit/kind differs from the declared observation')
        table = numerical.import_batch(manifest,rows)
        persist(state='RECOVERED',output_sha256={name:digest(data) for name,data in retained.items()},
                imported_count=table['imported_count'],missing_count=table['missing_count'])
        state = ('CANCELLED' if record.get('cancel_requested') and fetched.get('state') != 'COMPLETED' else
                 'FAILED' if fetched.get('state') != 'COMPLETED' or table['missing_count'] or any(row['execution_status']!='SUCCEEDED' for row in table['candidates']) else 'SUCCEEDED')
        # Existing reader/Runner handles these ordinary evaluation responses and candidate rows.
        responses = {f"후보 {index+1} / {name}":deepcopy(response)
                     for index,row in enumerate(table['candidates'])
                     for name,response in row.get('responses',{}).items()}
        result = {'table':table, 'candidates':table['candidates'], 'responses':responses}
        try:
            result.update(_publish_post(workbench, output, identifier, intent))
            if result.get('post_registration', {}).get('status') == 'FAILED': state = 'FAILED'
        except (ValueError, OSError, KeyError, TypeError) as error:
            result.update(post_registration={'status':'FAILED','message':str(error)})
            state = 'FAILED'
        return seal(state,**result)
    persist()
    try:
        check_cancelled()
        if operation == 'remote.run':
            payload_files = {}
            for name,sha in intent['files'].items():
                data = (origin_folder/'inputs'/name).read_bytes()
                if digest(data) != sha: raise ValueError('Staged input checksum differs')
                payload_files[name] = {'base64':base64.b64encode(data).decode(),'sha256':sha}
            prepared = call('prepare',files=payload_files)
            if prepared.get('input_sha256') != intent['files']: raise ValueError('Remote input transfer is incomplete')
            persist(state='SUBMITTING')  # Durable intent precedes the only submit call.
            call('submit')
        elif operation == 'remote.cancel':
            persist(cancel_requested=True)
            call('cancel')
        elif operation == 'remote.collect':
            state = call('query')
            if state.get('terminated') is not True:
                return seal('FAILED', failure_reason='실제 종료가 확인되지 않았습니다. 같은 작업의 상태를 다시 확인하세요.')
            return recover()
        elif operation == 'remote.reconnect':
            call('query')
            return seal('SUCCEEDED', mode='STATUS_ONLY', solver_execution='NOT_PERFORMED')
        deadline = time.monotonic() + host['monitor_seconds']
        while True:
            check_cancelled()
            state = call('query')
            if state.get('terminated') is True:
                return seal('CANCELLED' if state['state']=='CANCELLED' else 'SUCCEEDED' if state['state']=='COMPLETED' else 'FAILED',
                            mode='AWAITING_EXPLICIT_COLLECTION', solver_execution='REMOTE_TERMINATION_CONFIRMED')
            if time.monotonic() >= deadline:
                persist(state='MONITORING_PAUSED',terminated=False)
                return seal('FAILED',failure_reason='Monitoring budget ended; the same remote job may still be active. Explicit reconnect never resubmits.')
            time.sleep(host['poll_seconds'])
    except ExecutionCancelled:
        if operation in {'remote.reconnect','remote.collect'}:
            # Cancelling a local observation/transfer never cancels the remote computation.
            persist(local_request_status='CANCELLED')
            return seal('CANCELLED', mode='LOCAL_OBSERVATION_CANCELLED', solver_execution='NOT_PERFORMED')
        if record['state'] in {'PREPARING','PREPARED'}:
            persist(state='CANCELLED_BEFORE_SUBMIT',cancel_requested=True,terminated=True,
                    termination_confirmation='NO_SUBMIT_CALL')
            return seal('CANCELLED')
        persist(state='CANCEL_REQUESTED',cancel_requested=True,terminated=False)
        # Local SSH cancellation is not remote termination. Confirm separately.
        with cancellation_scope(CancellationToken()):
            try:
                call('cancel')
                deadline = time.monotonic() + host['cancel_seconds']
                while True:
                    state = call('query')
                    if state.get('terminated') is True: return seal('CANCELLED', mode='AWAITING_EXPLICIT_COLLECTION')
                    if time.monotonic() >= deadline: break
                    time.sleep(host['poll_seconds'])
            except (ValueError,OSError,RuntimeError):
                pass
        persist(state='TERMINATION_UNCONFIRMED',terminated=False)
        raise ExecutionCleanupFailed('Remote cancellation was requested but actual termination is unconfirmed; reconnect/cancel the same job')
    except ExecutionCleanupFailed:
        raise
    except Exception as error:
        persist(state='CONNECTION_OR_RESULT_ERROR',error_type=type(error).__name__,error=str(error))
        return seal('FAILED',failure_reason=str(error))


def dispatch(workbench, operation, arguments):
    if operation == 'catalog': return catalog(workbench)
    if operation == 'preview': return inspect(workbench,**arguments)
    if operation == 'status': return status(workbench,arguments['job_id'])
    raise ValueError('Use catalog, preview or status; execution uses the existing submit API')


def _worker(batch, configuration, runtime, *, output='results.json', threads=None):
    """Existing remote installation's CLI: reuse ExternalFilesAdapter per candidate.

    configuration is an operator-owned file already available on that host. It is
    never supplied as a client command, and this function does not install software.
    """
    from .adapters.external_files import ExternalFilesAdapter
    from .evaluation import run
    import numpy as np
    batch = Path(batch).resolve()
    target = Path(output).resolve()
    if target.exists(): raise ValueError('Refusing a stale remote results file')
    raw = batch.read_bytes(); manifest = json.loads(raw)
    numerical.import_batch(manifest, [])
    config = load_json(Path(configuration))
    if threads is not None: config['threads'] = threads
    adapter = ExternalFilesAdapter(runtime['id'], config)
    rows = []
    def serializable(value):
        if isinstance(value, np.ndarray): return value.tolist()
        if isinstance(value, np.generic): return value.item()
        raise TypeError('Unsupported remote result value')
    for candidate in manifest['candidates']:
        check_cancelled()
        folder = target.parent/'candidates'/check_id(candidate['candidate_id'])
        result = run(adapter, {**deepcopy(manifest.get('settings', {})),
            'case_id':manifest['case_id'], 'values':deepcopy(candidate['values'])}, output=folder)
        rows.append({**result, **{k:deepcopy(candidate[k]) for k in ('candidate_id','values','case_id','exchange_id')}})
        envelope = {'input_manifest_sha256':digest(raw), 'runtime':deepcopy(runtime), 'results':rows}
        # Publish completed/failed candidates incrementally; cancellation leaves missing rows unknown.
        temporary = target.with_name(target.name+'.tmp')
        temporary.write_text(json.dumps(envelope, ensure_ascii=False, allow_nan=False,
            default=serializable), encoding='utf-8')
        temporary.replace(target)
    return envelope if rows else {'input_manifest_sha256':digest(raw),'runtime':deepcopy(runtime),'results':[]}


def worker(batch, configuration, runtime, *, output='results.json'):
    """Cooperative native cleanup uses the existing CancellationToken/owned commands."""
    import os
    import signal
    import threading
    folder = Path(output).resolve().parent
    control = folder/'.cae-intent.json'
    intent = load_json(control) if control.is_file() else None
    if intent and (intent['runtime'] != runtime or intent['batch_sha256'] != file_hash(batch)):
        raise ValueError('Worker runtime/input differs from the supervisor intent')
    token = CancellationToken(); handlers = {}; cleanup = True
    if os.name == 'posix' and threading.current_thread() is threading.main_thread():
        for number in (signal.SIGTERM, signal.SIGINT):
            handlers[number] = signal.signal(number, lambda *_:token.request())
    try:
        with cancellation_scope(token):
            return _worker(batch, configuration, runtime, output=output,
                threads=intent['resources']['threads'] if intent else None)
    except ExecutionCleanupFailed:
        cleanup = False
        raise
    finally:
        for number, handler in handlers.items(): signal.signal(number, handler)
        if intent:
            save_json(folder/'.cae-runtime-exit.json', {'intent_sha256':fingerprint(intent),
                'token':scheduler_job_id('ssh', folder.name),
                'runtime':runtime,'cleanup_confirmed':cleanup and not token.cleanup_pending,
                'cancel_observed':token.observed})


def main(argv=None):
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'worker':
        parser = argparse.ArgumentParser(description='Run a retained batch with an existing registered external program')
        parser.add_argument('worker'); parser.add_argument('--batch',default='batch.json')
        parser.add_argument('--configuration',required=True); parser.add_argument('--runtime-id',required=True)
        parser.add_argument('--runtime-version',required=True)
        args = parser.parse_args(argv)
        worker(args.batch,args.configuration,{'id':args.runtime_id,'version':args.runtime_version})
        return
    from .workbench_client import Client
    parser = argparse.ArgumentParser(description='Explicit remote batch actions through the existing local service')
    parser.add_argument('--service',required=True)
    parser.add_argument('action',choices=['catalog','preview','status','run','reconnect','cancel','collect'])
    parser.add_argument('--host'); parser.add_argument('--batch-job'); parser.add_argument('--job')
    parser.add_argument('--request-id')
    args = parser.parse_args(argv); client = Client(args.service)
    if args.action in {'run','reconnect','cancel','collect'}:
        if not args.request_id: parser.error('An explicit stable --request-id is required; retry the same value after a lost reply')
        payload = {'host_id':args.host,'batch_job':args.batch_job} if args.action == 'run' else {'source_job':args.job}
        result = client.submit('remote.'+args.action,payload,request_id=args.request_id)
    else:
        payload = {'host_id':args.host,'batch_job':args.batch_job} if args.action == 'preview' else {'job_id':args.job} if args.action == 'status' else {}
        result = client.request('/api/workbench/remote',{'operation':args.action,'arguments':payload})
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))


if __name__ == '__main__': main()
