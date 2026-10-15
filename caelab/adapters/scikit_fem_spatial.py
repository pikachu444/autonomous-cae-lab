"""Pinned scikit-fem capabilities; all solves use the existing owned runner.

Declaration/port/Check methods are pure Python.  Reading retained results does
not import skfem, probe an executable, or call this adapter's run method.
"""
from copy import deepcopy
from importlib.metadata import PackageNotFoundError, version
import hashlib
import json
import os
from pathlib import Path
import sys

from .. import scikit_fem_models as domain
from ..execution_control import ExecutionCancelled, ExecutionCleanupFailed
from ..storage import save_json
from .fenicsx_rectangle import _run_process

_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_NAMES = (
    'caelab/__init__.py', 'caelab/adapters/__init__.py',
    'caelab/adapters/scikit_fem_spatial.py',
    'caelab/adapters/scikit_fem_worker.py', 'caelab/adapters/scikit_fem_forms.py',
    'caelab/scikit_fem_models.py', 'caelab/p1_temperature_transfer.py',
    'caelab/dimensioned_models.py', 'caelab/dimensioned_expression.py',
    'plugins/thermoelastic/__init__.py', 'plugins/thermoelastic/reference.py',
    # These files establish the parent-owned supervisor identity. They are not
    # re-imported by the isolated worker, which cannot submit other jobs.
    'caelab/adapters/fenicsx_rectangle.py', 'caelab/execution_control.py',
)
_LOADED = {name: (_ROOT / name).read_bytes() for name in _SOURCE_NAMES}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'),
                      parse_constant=lambda token: (_ for _ in ()).throw(ValueError('Nonfinite spatial JSON: ' + token)))


def _wall_timeout():
    value = os.environ.get('CAELAB_SCIKIT_FEM_WALL_TIMEOUT_SECONDS')
    if value is None:
        return None  # No hidden solver wall budget.
    if not value or not value.isascii() or not value.isdecimal() or int(value) <= 0:
        raise ValueError('CAELAB_SCIKIT_FEM_WALL_TIMEOUT_SECONDS requires a positive integer')
    return int(value)


def discover_runtime():
    """Metadata only, never imports FE code or reports an executed calculation."""
    installed = {}
    for package, required in domain.VERSIONS.items():
        try:
            installed[package] = version(package)
        except PackageNotFoundError as error:
            raise RuntimeError(package + '==' + required + ' 설치가 필요합니다.') from error
    if installed != domain.VERSIONS:
        raise RuntimeError('공간 계산의 고정 의존성 버전이 다릅니다: ' + repr(installed))
    return {'python': sys.executable, 'versions': installed, 'kind': 'service_python',
            'calculation': 'NOT_EXECUTED', 'platform': sys.platform, 'requires_wsl': False}


class _Spatial:
    version = '1'
    restart_safe = True
    domain = 'scikit_fem_spatial'

    def default_settings(self): return domain.default_settings(self.backend)
    def validate_settings(self, settings): return domain.validate_settings(self.backend, settings)
    def describe_model(self, settings): return domain.model_declaration(self.backend, settings)
    def describe_inputs(self, settings): return domain.describe_inputs(self.backend, settings)
    def bind_inputs(self, settings, values): return domain.bind_inputs(self.backend, settings, values)
    def describe_ports(self, settings): return domain.describe_ports(self.backend, settings)
    def bind_port(self, settings, port, response): return domain.bind_port(self.backend, settings, port, response)

    def run(self, settings, *, output, runtime=None):
        if runtime and set(runtime) - {'threads', 'memory_mb'}:
            raise ValueError('공간 계산은 기존 JobManager의 threads/memory_mb 예약만 사용합니다.')
        settings = self.validate_settings(settings)
        if self.backend == domain.STRUCTURAL and settings['temperature'] is None:
            return {'execution_status': 'REJECTED', 'responses': {}, 'checks': [],
                    'diagnostics': {'reason': 'Required captured temperature input is unbound',
                                    'solver_status': 'NOT_RUN', 'decision': 'NOT_RELEASED'}}
        output = Path(output)
        native = output / 'native'
        if any(p.is_symlink() for p in (output, *output.parents)) or native.exists():
            raise ValueError('Spatial stage output must be fresh and contain no symbolic links')
        for name, data in _LOADED.items():
            if (_ROOT / name).read_bytes() != data:
                raise RuntimeError('서비스 시작 후 공간 계산 코드가 변경됐습니다. 새 owner/service에서 실행하세요.')
        native.mkdir(parents=True)
        manifest = {'schema_version': '1', 'backend': self.backend, 'implementation_version': self.version, 'files': {}}
        for name, data in _LOADED.items():
            copied = native / 'sources' / name
            copied.parent.mkdir(parents=True, exist_ok=True)
            copied.write_bytes(data)
            manifest['files'][name] = {'repository_path': name, 'sha256': hashlib.sha256(data).hexdigest()}
        save_json(native / 'source_manifest.json', manifest)
        save_json(native / 'input.json', {'backend': self.backend, 'settings': settings})
        input_sha, manifest_sha = _sha(native / 'input.json'), _sha(native / 'source_manifest.json')
        environment = os.environ.copy()
        for name in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV'):
            environment.pop(name, None)
        # Same installed service interpreter on Windows and Linux. No WSL,
        # subprocess package installation, paid service, CAD or provider call.
        command = [sys.executable, '-I', str((native / 'sources/caelab/adapters/scikit_fem_worker.py').resolve()),
                   str((native / 'input.json').resolve())]
        timeout = _wall_timeout()
        save_json(native / 'command.json', {'argv': command, 'timeout_seconds': timeout,
                  'backend': self.backend, 'required_versions': domain.VERSIONS})
        try:
            _run_process(command, native, environment, timeout)
        except ExecutionCleanupFailed:
            # Do not report CANCELLED or cleaned up when the existing owner
            # could not establish a cleanup terminal state.
            raise
        except (RuntimeError, ExecutionCancelled) as error:
            partial = _read(native / 'progress.json') if (native / 'progress.json').is_file() else {}
            return {'execution_status': 'CANCELLED' if isinstance(error, ExecutionCancelled) else 'FAILED',
                    'responses': {}, 'checks': [], 'diagnostics': {
                        'reason': str(error), 'worker_execution': _read(native / 'execution.json'),
                        'partial_levels': partial, 'physical_fields': partial.get('physical_fields', []),
                        'mesh_studies': partial.get('completed_levels', []), 'decision': 'NOT_RELEASED',
                        'physical_qualification': 'UNKNOWN', 'backend_identity': self.backend}}
        # The reused supervisor waits/reaps on success and stops the exact
        # owned process/group on cancellation, timeout and exceptions. No PID
        # search, unrelated process kill, or detached background work occurs.
        for name, data in _LOADED.items():
            if (native / 'sources' / name).read_bytes() != data:
                raise RuntimeError('보존한 공간 계산 코드가 실행 중 변경됐습니다.')
        raw = _read(native / 'worker_result.json')
        if (raw.pop('input_sha256') != input_sha or raw.pop('sources_sha256') != manifest_sha
                or _sha(native / 'input.json') != input_sha or _sha(native / 'source_manifest.json') != manifest_sha
                or raw.get('backend') != self.backend):
            raise RuntimeError('공간 계산 결과의 원입력/코드/백엔드 identity가 다릅니다.')
        artifacts = raw.pop('worker_artifacts')
        if not isinstance(artifacts, dict) or 'fields.json' not in artifacts:
            raise ValueError('Spatial worker did not retain its exact field artifacts')
        for relative, expected in artifacts.items():
            path = native / relative
            if (not path.resolve().is_relative_to(native.resolve()) or path.is_symlink()
                    or not path.is_file() or _sha(path) != expected):
                raise ValueError('보존된 공간 계산 artifact가 누락되거나 손상됐습니다: ' + relative)
        if _read(native / 'fields.json') != raw['responses']:
            raise ValueError('Space field artifact differs from the actual worker response')
        raw.setdefault('diagnostics', {})['retained_worker_artifacts'] = deepcopy(artifacts)
        return raw


class ScikitFemWeakAdapter(_Spatial):
    backend = domain.WEAK


class ScikitFemThermalAdapter(_Spatial):
    backend = domain.THERMAL


class ScikitFemThermoelasticAdapter(_Spatial):
    backend = domain.STRUCTURAL
