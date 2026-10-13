"""Local operator setup and fixed-file Expert reload; never model tool arguments."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

MODEL = re.compile(r'openai-codex/[A-Za-z0-9._-]+\Z')
VERSION = '2.0.146'
FIELDS = {'runtime', 'experts'}


def default_config_path():
    local = os.environ.get('LOCALAPPDATA')
    return Path(local) / 'AutonomousCAELab' / 'workbench-config.json' if local else None


def digest(path):
    path = Path(path)
    if not path.exists():
        return None
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def read_config(path):
    path = Path(path)
    if not path.exists():
        return {}, None
    raw = path.read_bytes()
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError('Operator configuration exceeds 2 MiB')
    value = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('Operator configuration must be an object')
    return value, hashlib.sha256(raw).hexdigest()


def roles(value):
    rows = value.get('experts', []) if isinstance(value, dict) else value
    if not isinstance(rows, list) or len(rows) > 64:
        raise ValueError('Choose an editable role definitions file with at most 64 roles')
    seen = set()
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get('id'), str)
                or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,79}', row['id'])
                or row['id'] in seen or not isinstance(row.get('instructions', ''), str)):
            raise ValueError('Role definitions need distinct IDs and text instructions')
        for key in ('collections', 'tools', 'answer_sections'):
            if not isinstance(row.get(key, []), list) or any(not isinstance(x, str) for x in row.get(key, [])):
                raise ValueError('Role collections/tools/answer sections must be text lists')
        seen.add(row['id'])
    return deepcopy(rows)


def installation(profile, runtime_prefix):
    """Read only public ownership/policy records; no auth store or provider call."""
    result = {'status': 'UNAVAILABLE', 'authentication': 'UNVERIFIED',
              'model_entitlement': 'UNVERIFIED', 'inference': 'NOT_RUN',
              'models': [], 'network_access_performed': False}
    try:
        profile, runtime = Path(profile).resolve(strict=True), Path(runtime_prefix).resolve(strict=True)
        marker, _ = read_config(profile / 'caelab-profile-owner.json')
        binary = runtime / 'node_modules' / '@synsci' / 'openscience-windows-x64' / 'bin' / 'openscience.exe'
        config_file = profile / 'config' / 'openscience.json'
        if (marker.get('kind') != 'autonomous-cae-lab.chatgpt-auth-profile'
                or marker.get('provider') != 'openai-codex'
                or Path(marker.get('profile_root', '')).resolve() != profile
                or marker.get('runtime_version') != VERSION or not config_file.is_file()):
            raise ValueError('Existing profile ownership/version is unavailable or changed')
        pins = [x for x in marker.get('runtime_pin', {}).get('NativeBinaries', [])
                if Path(x.get('Path', '')).resolve() == binary]
        if len(pins) != 1 or not binary.is_file() or digest(binary).lower() != str(pins[0].get('Sha256')).lower():
            raise ValueError('Pinned OpenScience executable is missing or changed')
        config, _ = read_config(config_file)
        if config.get('permission', {}).get('*') != 'deny' or config.get('enabled_providers') != ['openai-codex']:
            raise ValueError('Existing profile provider/tool policy differs from the supported route')
        # Only a configured model hint is read. Catalog presence is not entitlement.
        hint = config.get('model')
        if isinstance(hint, str) and MODEL.fullmatch(hint):
            result['models'] = [hint]
        result.update(status='PINNED_FILES_VERIFIED', reason='Local files and deny-by-default policy match',
                      runtime_version=VERSION)
    except (OSError, ValueError, TypeError, KeyError):
        result['reason'] = 'Select the existing owned profile and matching pinned runtime'
    return result


def discover():
    local = os.environ.get('LOCALAPPDATA')
    if not local:
        return {'profiles': [], 'runtimes': []}
    base = Path(local) / 'AutonomousCAELab'
    return {
        'profiles': [str(p) for p in sorted((base / 'profiles').glob('*'))
                     if (p / 'caelab-profile-owner.json').is_file()],
        'runtimes': [str(p) for p in sorted((base / 'runtimes').glob('openscience-*'))
                     if (p / 'node_modules/@synsci/openscience-windows-x64/bin/openscience.exe').is_file()]}


def powershell_command(script, *, platform=None):
    """Native Windows never invokes wslpath; retain the existing WSL route."""
    platform = os.name if platform is None else platform
    if platform == 'nt':
        shell = shutil.which('pwsh.exe')
        if not shell:
            candidate = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'PowerShell/7/pwsh.exe'
            shell = str(candidate) if candidate.is_file() else None
        if not shell:
            raise ValueError('Existing PowerShell 7 is unavailable; no host or provider was invoked')
        return [shell, '-NoProfile', '-NonInteractive', '-File', str(Path(script).resolve())]
    import subprocess
    if not shutil.which('wslpath') or not shutil.which('pwsh.exe'):
        raise ValueError('The configured Windows OpenScience host is unavailable on this platform')
    windows_script = subprocess.check_output(['wslpath', '-w', str(script)], text=True).strip()
    return ['pwsh.exe', '-NoProfile', '-NonInteractive', '-File', windows_script]


def validate_runtime(value):
    from .assist.experts import RuntimeConfig
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError('Invalid Expert runtime configuration')
    runtime = RuntimeConfig(**value)
    if (runtime.provider != 'openscience' or not isinstance(runtime.model, str)
            or not MODEL.fullmatch(runtime.model) or runtime.generator is not None
            or runtime.api_base_url or runtime.credential_env or not runtime.external_model):
        raise ValueError('Connection supports only the explicit existing OpenScience subscription route')
    for override in (runtime.expert_models or {}).values():
        if (not isinstance(override, dict) or set(override) - {'model', 'provider'}
                or override.get('provider', 'openscience') != 'openscience'
                or not MODEL.fullmatch(override.get('model', ''))):
            raise ValueError('Role models must stay on the selected OpenScience route')
    if not isinstance(runtime.transmission, (dict, type(None))):
        raise ValueError('Invalid operator transmission policy')
    return runtime


def proposal(original, *, enabled, profile, runtime_prefix, model, definitions, role_models, allow_question):
    value = deepcopy(original)
    definitions = roles(definitions)
    value['experts'] = definitions
    if enabled:
        if installation(profile, runtime_prefix)['status'] != 'PINNED_FILES_VERIFIED':
            raise ValueError('Select matching existing profile/runtime files before connecting')
        runtime = deepcopy(value.get('runtime') or {})
        runtime.update(provider='openscience', model=model, credential_env='', api_base_url=None,
                       generator=None, external_model=True, openscience_profile=profile,
                       openscience_runtime_prefix=runtime_prefix)
        ids = {row['id'] for row in definitions}
        if set(role_models) - ids:
            raise ValueError('A role model targets an unavailable definition')
        runtime['expert_models'] = {key: {'provider': 'openscience', 'model': name}
                                    for key, name in role_models.items() if name}
        policy = deepcopy(runtime.get('transmission') or {})
        policy.update(allow_external_model=bool(allow_question), allow_question=bool(allow_question))
        # Existing result/source/public-search grants are preserved, never auto-added.
        runtime['transmission'] = policy
        validate_runtime(runtime)
        value['runtime'] = runtime
    else:
        # Disable connection explicitly; retain unrelated operator keys.
        value['runtime'] = None
    return value


def save_local(path, expected_sha256, value):
    """GUI/local Python only; no route accepts these bytes or a destination path."""
    from filelock import FileLock
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + '.lock', timeout=0):
        if digest(path) != expected_sha256:
            raise ValueError('Operator settings changed; reopen Connection before applying')
        raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
        descriptor, temporary = tempfile.mkstemp(prefix='.expert-', suffix='.json', dir=path.parent)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            if digest(path) != expected_sha256:
                raise ValueError('Operator settings changed during save')
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return hashlib.sha256(raw).hexdigest()


def bind_operator_config(workbench, path):
    """Called only from trusted server construction, never HTTP arguments."""
    workbench._operator_config_path = Path(path).resolve() if path is not None else None
    workbench._operator_config_sha = None
    if path is not None:
        value, sha = read_config(path)
        if value != workbench.config:
            raise ValueError('Operator file changed during service startup')
        workbench._operator_config_sha = sha


def status(workbench):
    with workbench._assist_config_lock:
        runtime = workbench.config.get('runtime') or {}
        model_roles = runtime.get('expert_models') or {}
        definitions = (list(workbench._assistance.experts.definitions.values()) if workbench._assistance
                       else workbench.config.get('experts', []))
        if isinstance(definitions, dict):
            definitions = definitions.get('experts', [])
        if not isinstance(definitions, list):
            definitions = []  # Legacy external role file is not reread by status.
        return {'service_session_id': workbench.session_id,
                'operator_config_path': str(workbench._operator_config_path) if workbench._operator_config_path else None,
                'config_sha256': workbench._operator_config_sha,
                'provider': runtime.get('provider'), 'model': runtime.get('model'),
                'roles': [{'id': row['id'], 'label': row.get('label', row['id']),
                           'model': model_roles.get(row['id'], {}).get('model', runtime.get('model'))}
                          for row in definitions],
                'authentication': 'UNVERIFIED', 'model_entitlement': 'UNVERIFIED',
                'inference': 'NOT_RUN', 'configuration': 'CONFIGURED' if runtime else 'NOT_CONFIGURED'}


def reload_local(workbench, expected_sha256):
    """Activate only the CLI-bound local file; caller cannot supply config/paths."""
    from .jobs import TERMINAL
    from .assist.experts import ExpertRuntime
    if workbench._operator_config_path is None:
        raise ValueError('This service has no local operator configuration path')
    with workbench._assist_config_lock, workbench.manager._lock:
        value, sha = read_config(workbench._operator_config_path)
        if not sha or sha != expected_sha256:
            raise ValueError('The local operator file differs from the selected saved settings')
        if {k: v for k, v in value.items() if k not in FIELDS} != {
                k: v for k, v in workbench.config.items() if k not in FIELDS}:
            raise ValueError('Unrelated operator settings changed; restart explicitly after saving work')
        if sha == workbench._operator_config_sha and value == workbench.config:
            return {**status(workbench), 'status': 'APPLIED', 'inference_performed': False}
        if workbench._assistance_cleanup_pending:
            return {**status(workbench), 'status': 'CLEANUP_PENDING', 'reason': 'Prior native cleanup is unconfirmed; settings remain inactive'}
        if workbench._assistance_active or any(row['state'] not in TERMINAL
                                              for row in workbench.manager.list()):
            return {**status(workbench), 'status': 'DEFERRED', 'reason': 'Wait for current jobs/requests to finish'}
        definitions = roles(value.get('experts', []))
        runtime = validate_runtime(value.get('runtime'))
        assistance = workbench.assistance()
        replacement = ExpertRuntime(assistance.knowledge, assistance.literature,
            experts=definitions, runtime=runtime, callbacks=assistance.experts.callbacks,
            session_root=assistance.experts.session_root)
        if digest(workbench._operator_config_path) != sha:
            raise ValueError('Operator file changed during activation')
        assistance.experts = replacement
        for key in FIELDS:
            if key in value:
                workbench.config[key] = deepcopy(value[key])
            else:
                workbench.config.pop(key, None)
        workbench._operator_config_sha = sha
        return {**status(workbench), 'status': 'APPLIED', 'inference_performed': False}
