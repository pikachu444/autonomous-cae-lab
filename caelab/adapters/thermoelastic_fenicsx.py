"""Recorded SI thermal and thermoelastic stages using the existing native runner."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path

from plugins.thermoelastic import reference as domain
from . import fenicsx_rectangle as rectangle
from . import fenicsx_rectangle_worker as helpers
from .. import execution_control
from ..storage import save_json

WORKER = Path(__file__).with_name('thermoelastic_fenicsx_worker.py')
SOURCE_PATHS = {'adapter': ('caelab/adapters/thermoelastic_fenicsx.py', 'sources/thermoelastic_fenicsx.py'),
                'worker': ('caelab/adapters/thermoelastic_fenicsx_worker.py', 'worker.py'),
                'domain': ('plugins/thermoelastic/reference.py', 'thermoelastic_reference.py'),
                'helpers': ('caelab/adapters/fenicsx_rectangle_worker.py', 'rectangle_worker.py'),
                'runner': ('caelab/adapters/fenicsx_rectangle.py', 'sources/fenicsx_rectangle.py'),
                'execution_control': ('caelab/execution_control.py', 'sources/execution_control.py')}
_FILES = {'adapter': Path(__file__), 'worker': WORKER, 'domain': Path(domain.__file__),
          'helpers': Path(helpers.__file__), 'runner': Path(rectangle.__file__),
          'execution_control': Path(execution_control.__file__)}
_LOADED = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in _FILES.items()}


class _Stage:
    version = '1'
    restart_safe = True
    domain = 'thermoelastic'

    def default_settings(self):
        return domain.default_settings(self.stage)

    def validate_settings(self, settings):
        return domain.validate_settings(settings, self.stage)

    def describe_ports(self, settings):
        return domain.describe_ports(settings, self.stage)

    def bind_port(self, settings, port, response):
        return domain.bind_port(settings, self.stage, port, response)

    def _input_fields(self):
        if self.stage == 'thermal':
            return {'conductivity': ('conductivity', 'value', 'W/(m*K)'),
                    'conductivity_temperature_slope': ('conductivity', 'beta', '1/K'),
                    'conductivity_reference_temperature': ('conductivity', 'reference_temperature', 'K'),
                    'heat_source': ('heat_source', 'value', 'W/m^3'),
                    'boundary_temperature': ('boundary_temperature', 'value', 'K')}
        return {'young_modulus': ('material', 'young_modulus', 'Pa'),
                'poisson_ratio': ('material', 'poisson_ratio', '1'),
                'thermal_expansion': ('material', 'thermal_expansion', '1/K'),
                'reference_temperature': ('material', 'reference_temperature', 'K')}

    def describe_inputs(self, settings):
        settings = self.validate_settings(settings)
        return [{'id': identifier, 'label': identifier.replace('_', ' '), 'unit': unit,
                 'value': settings[section][key], 'type': 'continuous'}
                for identifier, (section, key, unit) in self._input_fields().items()]

    def bind_inputs(self, settings, values):
        fields = self._input_fields()
        if not isinstance(values, dict) or set(values) - set(fields):
            raise ValueError('Choose only the advertised thermal/structural numerical inputs')
        result = deepcopy(settings)
        for identifier, value in values.items():
            section, key, _ = fields[identifier]
            result[section][key] = value
        # The original physical validation remains authoritative for candidates;
        # neither bounds nor positivity are silently clipped by this binding.
        return self.validate_settings(result)

    def run(self, settings, *, output, runtime=None):
        if runtime:
            raise ValueError('FEniCSx stages use the existing documented operator runtime configuration')
        settings = self.validate_settings(settings)
        if self.stage == 'structural' and settings['temperature'] is None:
            return {'execution_status': 'REJECTED', 'responses': {}, 'checks': [],
                    'diagnostics': {'reason': 'Required captured temperature input is unbound', 'solver_status': 'NOT_RUN'}}
        output = Path(output)
        native = output / 'native'
        if any(path.is_symlink() for path in (output, *output.parents)) or native.exists():
            raise ValueError('Stage native output must be fresh and contain no symbolic links')
        native.mkdir(parents=True)
        if any(helpers._sha(path) != _LOADED[key] for key, path in _FILES.items()):
            raise RuntimeError('Loaded stage implementation changed; start a new service before execution')
        captured = {key: path.read_bytes() for key, path in _FILES.items()}
        manifest = {'schema_version': '1', 'domain_plugin_version': domain.VERSION, 'files': {}}
        for key, source in _FILES.items():
            repository, relative = SOURCE_PATHS[key]
            if source.relative_to(Path(__file__).parents[2]).as_posix() != repository:
                raise RuntimeError('Stage captured source location differs from its declared identity')
            path = native / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(captured[key])
            manifest['files'][key] = {'repository_path': repository, 'copied_path': relative,
                                      'sha256': hashlib.sha256(captured[key]).hexdigest()}
        save_json(native / 'source_manifest.json', manifest)
        save_json(native / 'input.json', {'stage': self.stage, 'settings': settings})
        spec_sha, manifest_sha = helpers._sha(native / 'input.json'), helpers._sha(native / 'source_manifest.json')
        interpreter = os.environ.get('CAELAB_FENICSX_PYTHON', '/usr/bin/python3')
        if not interpreter.strip(): raise ValueError('CAELAB_FENICSX_PYTHON must identify a system Python interpreter')
        timeout = rectangle._wall_timeout()
        command = [interpreter, '-I', str((native / 'worker.py').resolve()), str((native / 'input.json').resolve())]
        excluded = ['PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'PETSC_DIR', 'PETSC_OPTIONS', 'PETSC_OPTIONS_YAML']
        environment = os.environ.copy()
        for name in excluded: environment.pop(name, None)
        save_json(native / 'command.json', {'argv': command, 'timeout_seconds': timeout,
            'python_isolated_mode': True, 'fixed_solver_policy': helpers.NATIVE_OPTIONS,
            'excluded_environment_variables': excluded})
        def verify():
            for key, source in _FILES.items():
                if source.read_bytes() != captured[key] or helpers._regular_file(native, SOURCE_PATHS[key][1]).read_bytes() != captured[key]:
                    raise RuntimeError('Original or captured stage source drift; artifacts retained')
            if helpers._sha(native / 'input.json') != spec_sha or helpers._sha(native / 'source_manifest.json') != manifest_sha:
                raise RuntimeError('Frozen stage input/source identity changed')
        verify()
        try:
            rectangle._run_process(command, native, environment, timeout)
        except execution_control.ExecutionCleanupFailed:
            raise
        except execution_control.ExecutionCancelled as error:
            save_json(native / 'cancellation.json', {'reason': str(error), 'numerical_verdict': 'UNKNOWN'})
            return {'execution_status': 'CANCELLED', 'responses': {}, 'checks': [],
                    'diagnostics': {'reason': str(error), 'native_artifacts': 'native', 'numerical_verdict': 'UNKNOWN'}}
        except RuntimeError as error:
            verify()
            return {'execution_status': 'FAILED', 'responses': {}, 'checks': [],
                    'diagnostics': {'reason': str(error), 'solver_status': 'FAILED_EXECUTION',
                                    'native_artifacts': 'native', 'stderr': 'native/stderr.log',
                                    'engineering_release': 'NOT_RELEASED'}}
        verify()
        raw = rectangle._finite_json(native, 'worker_result.json')
        if (raw.get('spec_sha256') != spec_sha or raw.get('source_manifest_sha256') != manifest_sha
                or raw.get('stage') != self.stage or raw.get('mpi_size') != 1 or raw.get('scalar_type') != 'float64'
                or raw.get('solver_policy') != {'ksp_type': 'preonly', 'pc_type': 'lu'}
                or not isinstance(raw.get('versions'), dict) or not rectangle._VERSION_KEYS <= set(raw['versions'])
                or any(not isinstance(raw['versions'][key], str) or not raw['versions'][key].strip() for key in rectangle._VERSION_KEYS)
                or raw.get('execution_status') not in ('SUCCEEDED', 'REJECTED')
                or type(raw.get('ksp_convergence_reason')) is not int):
            raise RuntimeError('Native stage input/source/runtime receipt mismatch; raw artifacts retained')
        expected_artifacts = {'fields.json', 'field.xdmf', 'field.h5', 'forms.ufl.txt', 'petsc_initialization.json'}
        if self.stage == 'thermal': expected_artifacts.add('thermal_field.json')
        if not isinstance(raw.get('artifacts'), dict) or set(raw['artifacts']) != expected_artifacts:
            raise RuntimeError('Native stage omitted the required captured field/source artifacts')
        for relative, digest in raw['artifacts'].items():
            if helpers._sha(helpers._regular_file(native, relative)) != digest:
                raise RuntimeError('Captured native stage artifact changed: ' + relative)
        if domain.digest(rectangle._finite_json(native, 'fields.json')) != domain.digest(raw.get('responses')):
            raise RuntimeError('Native response record differs from its preserved field data')
        initialization = rectangle._finite_json(native, 'petsc_initialization.json')
        if (initialization != raw.get('petsc_initialization')
                or initialization != {'argv': ['caelab_thermoelastic_worker', '-skip_petscrc'],
                    'options': {'skip_petscrc': None}, 'petsc_rc_disabled': True,
                    'ambient_options_removed': ['PETSC_OPTIONS', 'PETSC_OPTIONS_YAML']}):
            raise RuntimeError('Native stage PETSc bootstrap receipt mismatch')
        checks = raw.get('checks')
        if (not isinstance(checks, list) or not checks or any(not isinstance(check, dict)
                or check.get('status') not in ('PASS', 'FAIL') for check in checks)
                or (raw['execution_status'] == 'SUCCEEDED') != all(check['status'] == 'PASS' for check in checks)
                or raw['execution_status'] == 'SUCCEEDED' and raw['ksp_convergence_reason'] <= 0):
            raise RuntimeError('Native stage execution status and numerical checks disagree')
        if self.stage == 'thermal': domain.validate_temperature(raw['responses']['temperature'], settings)
        return {'execution_status': raw['execution_status'], 'responses': deepcopy(raw['responses']),
                'checks': deepcopy(raw['checks']), 'diagnostics': {'native_artifacts': 'native',
                    'spec_sha256': spec_sha, 'source_manifest_sha256': manifest_sha,
                    'versions': raw['versions'], 'solver_policy': raw['solver_policy'],
                    'source_manifest': 'native/source_manifest.json', 'limitations': list(domain.LIMITATIONS),
                    'engineering_release': 'NOT_RELEASED', 'nonlinear_iteration': 'EXPLICIT_LAGGED_PICARD_ONLY'}}


class ThermalFenicsxAdapter(_Stage):
    backend = 'thermal.fenicsx.rectangle'
    stage = 'thermal'


class ThermoelasticFenicsxAdapter(_Stage):
    backend = 'structural.fenicsx.thermoelastic_rectangle'
    stage = 'structural'
