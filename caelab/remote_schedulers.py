"""Thin OpenSSH/Slurm/OpenPBS commands; also the per-command remote helper.

The helper runs as ``python -`` over existing SSH. It creates no service,
installs nothing, and never forwards or reports an authentication environment.
"""
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import sys
import time


TERMINAL = {'COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT'}
SLURM_TERMINAL = {'COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT', 'NODE_FAIL',
                  'OUT_OF_MEMORY', 'PREEMPTED', 'BOOT_FAIL', 'DEADLINE', 'REVOKED'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode())


def relative_path(name):
    if not isinstance(name, str) or not name or name in {'.','..'} or any(c in name for c in ('\\', ':', '\x00', '\n', '\r')):
        raise ValueError('A contained POSIX file name is required')
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '.' in p.parts or name != p.as_posix():
        raise ValueError('Remote file traversal is not allowed')
    if any(part.startswith('.cae-') for part in p.parts):
        raise ValueError('Remote control files are reserved')
    reserved = {'con','prn','aux','nul',*[f'com{i}' for i in range(1,10)],*[f'lpt{i}' for i in range(1,10)]}
    if any(part.endswith((' ','.')) or part.split('.')[0].casefold() in reserved for part in p.parts):
        raise ValueError('Remote output names must also be portable Windows file names')
    return name


def job_id(scheduler, value):
    pattern = r'[0-9]+' if scheduler == 'slurm' else r'[0-9]+(?:\.[A-Za-z0-9_.-]+)?' if scheduler == 'pbs' else r'R[0-9a-f]{32}'
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError('Unexpected scheduler job identity')
    return value


def parse_submit(scheduler, stdout):
    text = stdout.strip()
    if scheduler == 'slurm':
        # --parsable may append ;cluster, which must not become shell syntax.
        if not re.fullmatch(r'[0-9]+(?:;[A-Za-z0-9_.-]+)?', text):
            raise ValueError('Slurm did not return one parsable job ID')
        text = text.split(';')[0]
    return job_id(scheduler, text)


def _slurm_state(state, exit_code=None):
    state = state.split()[0].rstrip('+')
    terminal = state in SLURM_TERMINAL and exit_code is not None
    mapped = ('COMPLETED' if state == 'COMPLETED' and exit_code == '0:0' else
              'CANCELLED' if state == 'CANCELLED' else 'TIMEOUT' if state == 'TIMEOUT' else
              'FAILED' if terminal else 'RUNNING' if state in {'RUNNING', 'COMPLETING'} else 'QUEUED')
    return {'state': mapped, 'scheduler_state': state, 'terminated': terminal,
            'exit_code': exit_code, 'termination_confirmation': 'SCHEDULER_ACCOUNTING' if terminal else None}


def parse_slurm(text, token, *, accounting=False, expected_id=None):
    matches = []
    for line in text.splitlines():
        fields = line.strip().split('|')
        if not fields or len(fields) != (5 if accounting else 4):
            continue
        identifier, name, comment, state = fields[:4]
        if name != 'cae_' + token[1:11] or comment != token:
            continue
        if expected_id is not None and identifier != expected_id:
            continue
        if not re.fullmatch(r'[0-9]+', identifier):  # Ignore .batch/.extern steps.
            continue
        code = fields[4] if accounting and re.fullmatch(r'[0-9]+:[0-9]+', fields[4]) else None
        matches.append(dict(_slurm_state(state, code), scheduler_id=identifier))
    if len(matches) > 1:
        raise ValueError('Multiple Slurm jobs match the retained submission token')
    return matches[0] if matches else {'state': 'UNKNOWN', 'terminated': False, 'scheduler_id': expected_id}


def parse_pbs(text, token, *, expected_id=None):
    jobs = json.loads(text).get('Jobs', {})
    if not isinstance(jobs, dict):
        raise ValueError('OpenPBS JSON Jobs must be a mapping')
    matches = []
    for identifier, row in jobs.items():
        variables = row.get('Variable_List', {})
        if isinstance(variables, str):
            variables = dict(item.split('=', 1) for item in variables.split(',') if '=' in item)
        if row.get('Job_Name') != 'cae_' + token[1:11] or variables.get('CAELAB_SUBMISSION') != token:
            continue
        if expected_id is not None and identifier != expected_id:
            continue
        job_id('pbs', identifier)
        state, code = row.get('job_state'), row.get('Exit_status')
        terminal = state == 'F' and type(code) is int
        mapped = ('COMPLETED' if terminal and code == 0 else 'FAILED' if terminal else
                  'RUNNING' if state in {'R', 'E', 'S'} else 'QUEUED')
        matches.append({'scheduler_id': identifier, 'state': mapped, 'scheduler_state': state,
                        'terminated': terminal, 'exit_code': code if type(code) is int else None,
                        'termination_confirmation': 'SCHEDULER_ACCOUNTING' if terminal else None})
    if len(matches) > 1:
        raise ValueError('Multiple PBS jobs match the retained submission token')
    return matches[0] if matches else {'state': 'UNKNOWN', 'terminated': False, 'scheduler_id': expected_id}


def submit_command(intent, folder, token):
    resources = intent['resources']
    seconds = resources['wall_seconds']
    wall = f'{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}'
    name = 'cae_' + token[1:11]
    if intent['scheduler'] == 'slurm':
        argv = ['sbatch', '--parsable', '--export=NONE', '--job-name=' + name, '--comment=' + token,
                '--chdir=' + str(folder), '--cpus-per-task=' + str(resources['threads']),
                '--mem=' + str(resources['memory_mb']) + 'M', '--time=' + wall,
                '--output=' + str(folder / 'scheduler.stdout.log'), '--error=' + str(folder / 'scheduler.stderr.log')]
        if intent['queue']: argv.append('--partition=' + intent['queue'])
        if intent['account']: argv.append('--account=' + intent['account'])
    elif intent['scheduler'] == 'pbs':
        argv = ['qsub', '-N', name, '-v', 'CAELAB_SUBMISSION=' + token,
                '-l', f"select=1:ncpus={resources['threads']}:mem={resources['memory_mb']}mb",
                '-l', 'walltime=' + wall, '-o', str(folder / 'scheduler.stdout.log'),
                '-e', str(folder / 'scheduler.stderr.log')]
        if intent['queue']: argv += ['-q', intent['queue']]
        if intent['account']: argv += ['-A', intent['account']]
    else:
        raise ValueError('Select Slurm or OpenPBS for scheduler submission')
    return argv + [str(folder / '.cae-job.sh')]


# One owned supervisor per SSH/batch job. No PID from disk is ever signalled.
SUPERVISOR = '''import json,os,signal,subprocess,time
from pathlib import Path
p=Path(__file__).resolve().parent
def put(name,value):
 t=p/(name+'.tmp');t.write_text(json.dumps(value),encoding='utf-8');os.replace(t,p/name)
s=json.loads((p/'.cae-intent.json').read_text(encoding='utf-8'))
def identity(pid):
 try:
  stat=Path('/proc/'+str(pid)+'/stat').read_text();ticks=stat[stat.rfind(')')+2:].split()[19]
  return [Path('/proc/sys/kernel/random/boot_id').read_text().strip(),ticks]
 except OSError:return None
put('.cae-process.json',{'pid':os.getpid(),'identity':identity(os.getpid())})
cancelled=False;timed_out=False;child=None
def ask(signum,frame):
 global cancelled
 cancelled=True
signal.signal(signal.SIGTERM,ask);signal.signal(signal.SIGINT,ask)
try:
 with (p/'solver.stdout.log').open('xb') as out,(p/'solver.stderr.log').open('xb') as err:
  env=dict(os.environ);env['OMP_NUM_THREADS']=str(s['resources']['threads'])
  child=subprocess.Popen(s['command'],cwd=p,stdout=out,stderr=err,stdin=subprocess.DEVNULL,start_new_session=True,env=env)
  start=time.monotonic()
  while child.poll() is None:
   cancelled=cancelled or (p/'.cae-cancel.request').exists()
   timed_out=time.monotonic()-start>=s['resources']['wall_seconds']
   if cancelled or timed_out:
    os.killpg(child.pid,signal.SIGTERM)
    try:child.wait(timeout=5)
    except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
    break
   time.sleep(.1)
  code=child.wait()
  try:os.killpg(child.pid,0)
  except ProcessLookupError:pass
  else:raise RuntimeError('Descendant termination is unconfirmed')
 if s['scheduler']=='ssh':
  receipt=json.loads((p/'.cae-runtime-exit.json').read_text())
  expected=__import__('hashlib').sha256(json.dumps(s,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
  if receipt.get('token')!=p.name or receipt.get('intent_sha256')!=expected or receipt.get('runtime')!=s['runtime'] or receipt.get('cleanup_confirmed') is not True:raise RuntimeError('Runtime cleanup is unconfirmed')
 put('.cae-exit.json',{'token':p.name,'intent_sha256':__import__('hashlib').sha256(json.dumps(s,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest(),'state':'CANCELLED' if cancelled else 'TIMEOUT' if timed_out else 'COMPLETED' if code==0 else 'FAILED','exit_code':code,'child_reaped':True,'runtime_python':__import__('sys').version.split()[0]})
except BaseException as error:
 # A failed cleanup must not become a terminal receipt.
 put('.cae-supervisor-error.json',{'error_type':type(error).__name__,'child_reaped':child is None or child.poll() is not None})
 raise
'''


def _put(path, value):
    temporary = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    temporary.write_text(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    os.replace(temporary, path)


def _file(folder, name):
    p = folder / relative_path(name)
    if any(part.is_symlink() for part in [p, *list(p.parents)[:len(PurePosixPath(name).parts)]]):
        raise ValueError('Symbolic links are not transferred')
    if not p.resolve().is_relative_to(folder):
        raise ValueError('Remote file escapes the owned job directory')
    return p


def _call(argv):
    completed = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
    # qstat includes environment values. Keep raw output in memory only.
    return completed.returncode, completed.stdout.decode('utf-8', errors='strict')


def _query(folder, intent, token):
    if (folder / '.cae-cancelled-before-submit').exists():
        return {'scheduler_id':None,'state':'CANCELLED','terminated':True,
                'termination_confirmation':'SUBMISSION_ATOMICALLY_BLOCKED'}
    receipt_path = folder / '.cae-submission.json'
    identifier = json.loads(receipt_path.read_text())['scheduler_id'] if receipt_path.exists() else None
    scheduler = intent['scheduler']
    if scheduler == 'ssh':
        exit_path = folder / '.cae-exit.json'
        if exit_path.exists():
            receipt = json.loads(exit_path.read_text())
            if (receipt.get('child_reaped') is True and receipt.get('state') in TERMINAL and
                receipt.get('token') == token and receipt.get('intent_sha256') == fingerprint(intent)):
                return dict(receipt, scheduler_id=token, terminated=True, termination_confirmation='OWNED_CHILD_REAPED')
        process_path = folder / '.cae-process.json'
        alive = False
        if process_path.exists():
            process = json.loads(process_path.read_text())
            try:
                pid = process['pid']
                stat = Path(f'/proc/{pid}/stat').read_text()
                identity = [Path('/proc/sys/kernel/random/boot_id').read_text().strip(), stat[stat.rfind(')')+2:].split()[19]]
                alive = process['identity'] is not None and identity == process['identity']
            except (OSError, IndexError):
                pass
        return {'scheduler_id': identifier, 'state': 'RUNNING' if alive else 'UNKNOWN', 'terminated': False}
    if scheduler == 'slurm':
        rc, text = _call(['squeue', '--noheader', '--name=cae_' + token[1:11], '--format=%i|%j|%k|%T'])
        if rc != 0: raise RuntimeError('Slurm queue query failed; termination is unconfirmed')
        state = parse_slurm(text, token, expected_id=identifier)
        if state['state'] == 'UNKNOWN' or state.get('scheduler_state') in SLURM_TERMINAL:
            rc, text = _call(['sacct', '--noheader', '--parsable2', '--name=cae_' + token[1:11],
                              '--starttime=1970-01-01', '--format=JobIDRaw,JobName%32,Comment%64,State,ExitCode'])
            if rc != 0: raise RuntimeError('Slurm accounting unavailable; termination is unconfirmed')
            state = parse_slurm(text, token, accounting=True, expected_id=identifier)
    else:
        argv = ['qstat', '-x', '-f', '-F', 'json'] + ([identifier] if identifier else [])
        rc, text = _call(argv)
        if rc != 0: raise RuntimeError('PBS history query failed; termination is unconfirmed')
        state = parse_pbs(text, token, expected_id=identifier)
    if state.get('scheduler_id') and identifier is None:
        _put(receipt_path, {'scheduler_id': state['scheduler_id'], 'recovered_by_token': True})
    return state


def remote_request(request):
    """Execute one explicit command on the selected host, never an implicit submit."""
    if os.name != 'posix':
        raise ValueError('The registered remote execution host must be POSIX')
    token = job_id('ssh', request['token'])
    base = Path(request['base'])
    if not base.is_absolute() or '..' in base.parts or base.resolve(strict=True) != base or not base.is_dir():
        raise ValueError('Use the existing canonical remote working root')
    folder = base / token
    action = request['action']
    if action == 'prepare':
        folder.mkdir(mode=0o700, exist_ok=True)
    if folder.is_symlink() or not folder.is_dir() or folder.resolve() != folder:
        raise ValueError('The remote job directory is missing or redirected')
    intent = request['intent']
    if fingerprint(intent) != request['intent_sha256']:
        raise ValueError('Remote intent checksum differs')
    intent_path = folder / '.cae-intent.json'
    if intent_path.exists():
        if json.loads(intent_path.read_text()) != intent:
            raise ValueError('The remote job already has a different immutable input')
    elif action == 'prepare':
        # O_EXCL prevents concurrent prepare from replacing the first intent.
        with intent_path.open('x', encoding='utf-8') as stream:
            json.dump(intent, stream, ensure_ascii=False, allow_nan=False)
    else:
        raise ValueError('The remote job has no prepared input')
    if action == 'prepare':
        for name, item in request['files'].items():
            path = _file(folder, name)
            data = base64.b64decode(item['base64'], validate=True)
            if len(data) > intent['transfer_limit'] or digest(data) != intent['files'].get(name):
                raise ValueError('Input transfer checksum differs')
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                if digest(path.read_bytes()) != digest(data): raise ValueError('Existing remote input bytes differ')
            else:
                with path.open('xb') as stream: stream.write(data)
        if set(request['files']) != set(intent['files']):
            raise ValueError('Input transfer is incomplete')
        return {'state': 'PREPARED', 'input_sha256': intent['files'], 'terminated': False}
    for name, sha in intent['files'].items():
        if digest(_file(folder, name).read_bytes()) != sha:
            raise ValueError('Prepared remote input was changed')
    if action == 'submit':
        try: (folder / '.cae-submit-claim').mkdir()
        except FileExistsError: return _query(folder, intent, token)
        (folder / '.cae-runner.py').write_text(SUPERVISOR, encoding='utf-8')
        script = '#!/bin/sh\ncd ' + shlex.quote(str(folder)) + '\nexec ' + shlex.join([intent['python'], str(folder / '.cae-runner.py')]) + '\n'
        (folder / '.cae-job.sh').write_text(script, encoding='utf-8')
        if intent['scheduler'] == 'ssh':
            _put(folder / '.cae-submission.json', {'scheduler_id': token})
            subprocess.Popen([intent['python'], str(folder / '.cae-runner.py')], cwd=folder,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return {'scheduler_id': token, 'state': 'SUBMITTED', 'terminated': False}
        rc, text = _call(submit_command(intent, folder, token))
        if rc != 0:
            raise RuntimeError('Scheduler submission response failed; query the same token, never resubmit')
        identifier = parse_submit(intent['scheduler'], text)
        _put(folder / '.cae-submission.json', {'scheduler_id': identifier})
        return {'scheduler_id': identifier, 'state': 'SUBMITTED', 'terminated': False}
    if action == 'query': return _query(folder, intent, token)
    if action == 'cancel':
        (folder / '.cae-cancel.request').touch(exist_ok=True)
        try:
            (folder / '.cae-submit-claim').mkdir()
        except FileExistsError:
            pass
        else:
            (folder / '.cae-cancelled-before-submit').touch(exist_ok=False)
            return _query(folder,intent,token)
        state = _query(folder, intent, token)
        if state.get('terminated'): return state
        identifier = state.get('scheduler_id')
        if not identifier: return dict(state, cancel_requested=False)
        if intent['scheduler'] == 'ssh':
            (folder / '.cae-cancel.request').touch(exist_ok=True)
        else:
            rc, _ = _call(['scancel' if intent['scheduler'] == 'slurm' else 'qdel', job_id(intent['scheduler'], identifier)])
            if rc != 0: raise RuntimeError('Cancellation command failed; termination is unconfirmed')
        return dict(state, cancel_requested=True, terminated=False)
    if action == 'fetch':
        state = _query(folder, intent, token)
        if not state.get('terminated'): raise ValueError('Files cannot be recovered before confirmed termination')
        files, size = {}, 0
        for name in intent['outputs']:
            path = _file(folder, name)
            if not path.exists(): continue
            if not path.is_file(): raise ValueError('Recovered output is not a regular file')
            data = path.read_bytes(); size += len(data)
            if size > intent['transfer_limit']: raise ValueError('Recovered files exceed the registered transfer budget')
            files[name] = {'base64': base64.b64encode(data).decode('ascii'), 'sha256': digest(data)}
        return dict(state, files=files, input_sha256=intent['files'])
    raise ValueError('Unknown explicit remote command')


def _entry(encoded):
    try:
        value = remote_request(json.loads(base64.b64decode(encoded, validate=True)))
        print(json.dumps({'ok': True, 'value': value}, ensure_ascii=False, allow_nan=False))
    except Exception as error:
        # Never print scheduler attributes, remote environment or authentication data.
        print(json.dumps({'ok': False, 'error_type': type(error).__name__, 'message': str(error)}))
