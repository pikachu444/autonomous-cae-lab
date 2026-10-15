"""Mixed stress/kinematic boundary conditions over the existing FELUPE laws.

This module solves boundary equations, not constitutive equations. FELUPE owns
stress and d(stress)/dF. No observation, Plan, document, or job is created here.
All successful response arrays end at the last accepted increment on failure.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from numbers import Real
from typing import Callable

import numpy as np

COMPONENTS = {a + b: (i, j) for i, a in enumerate('xyz') for j, b in enumerate('xyz')}
MEASURES = {'linear_elastic': 'infinitesimal_Cauchy', 'neo_hooke': 'first_Piola'}
DEFAULT_SOLVER = {'atol': 1e-10, 'rtol': 1e-10, 'max_iterations': 40, 'max_backtracks': 24}


def capabilities(model: str) -> dict:
    """Law support is separate from runtime availability and engineering release."""
    supported = model in MEASURES
    available = importlib.util.find_spec('felupe') is not None
    return {
        'backend': 'material.felupe', 'model': model,
        'boundary_controller': 'caelab.material_control/1' if supported else None,
        'supported': supported, 'runtime_available': available,
        'runtime_status': 'AVAILABLE' if available else 'ADAPTER_UNAVAILABLE',
        'kinematics': ['prescribed_F', 'axial_stretch', 'axial_engineering_strain'] if supported else [],
        'stress_control': list(COMPONENTS) if supported else [],
        'stress_measure': MEASURES.get(model), 'frame': 'material_cartesian',
        'lateral': ['fixed', 'prescribed_F', 'free'] if supported else [],
        'time': 'strictly_increasing_quasistatic_path_parameter',
        'rate_dependence': False, 'temperature': False,
        'initial_state': 'elastic_deformation_gradient_only; no internal variables',
        'integration': 'elastic_constitutive_evaluation_and_damped_boundary_Newton',
        'platforms': {'Windows': 'PYTHON_PATH_NOT_RUNTIME_VERIFIED',
                      'WSL': 'OPTIONAL_NOT_REQUIRED_NOT_RUNTIME_VERIFIED'},
        'engineering_release': 'NOT_ASSESSED',
    }


def _number(value, label, *, positive=False, nonnegative=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not np.isfinite(value):
        raise ValueError(label + ' must be a finite number, not text or a boolean')
    value = float(value)
    if positive and value <= 0 or nonnegative and value < 0:
        raise ValueError(label + (' must be positive' if positive else ' must be nonnegative'))
    return value


def _array(value, shape, label):
    raw = np.asarray(value, dtype=object)
    if raw.shape != shape:
        raise ValueError(label + f' must have shape {shape}')
    for item in raw.flat:
        _number(item, label)
    return np.asarray(value, dtype=float)


def validate_control_settings(settings: dict, *, parameters=True):
    """Invalid drafts can be stored by the owner; this is execution admission."""
    from .adapters.felupe_material import validate_parameters
    required = {'model', 'parameters', 'stress_unit', 'time_unit', 'time',
                'deformation_gradient', 'boundary_control'}
    if not isinstance(settings, dict) or set(settings) != required:
        raise ValueError('Controlled Material settings require exactly ' + ', '.join(sorted(required)))
    model = settings['model']
    if model not in MEASURES:
        raise ValueError('This law has no registered mixed-control capability')
    for key in ('stress_unit', 'time_unit'):
        if not isinstance(settings[key], str) or not settings[key].strip():
            raise ValueError('Declare ' + key)
    time = settings['time']
    if not isinstance(time, list) or not 1 <= len(time) <= 100000:
        raise ValueError('time must contain 1 to 100000 ordered samples')
    time = _array(time, (len(time),), 'time')
    if np.any(np.diff(time) <= 0):
        raise ValueError('History time must be strictly increasing')
    F = _array(settings['deformation_gradient'], (len(time), 3, 3), 'deformation_gradient')
    with np.errstate(over='ignore', invalid='ignore'):
        determinants = np.linalg.det(F)
    if not np.isfinite(determinants).all() or np.any(determinants <= 0):
        raise ValueError('Prescribed F/initial guesses require positive det(F) at every sample')
    names = {'E', 'nu'} if model == 'linear_elastic' else {'mu', 'lmbda'}
    if not isinstance(settings['parameters'], dict) or set(settings['parameters']) != names:
        raise ValueError('The exact law parameter names are required')
    if parameters:
        validate_parameters(model, settings['parameters'])
    bc = settings['boundary_control']
    if not isinstance(bc, dict) or set(bc) != {'version', 'stress_measure', 'frame',
                                             'stress_components', 'initial_state', 'solver'}:
        raise ValueError('boundary_control needs version, measure, frame, stress_components, initial_state and solver')
    if type(bc['version']) is not int or bc['version'] != 1:
        raise ValueError('Unsupported boundary-control version')
    if bc['stress_measure'] != MEASURES[model] or bc['frame'] != 'material_cartesian':
        raise ValueError('Control targets must use the law stress measure and material_cartesian frame')
    targets = bc['stress_components']
    if not isinstance(targets, dict) or not targets or set(targets) - set(COMPONENTS):
        raise ValueError('Declare at least one unique stress-controlled tensor component')
    for name, values in targets.items():
        _array(values, (len(time),), 'stress target ' + name)
    initial = bc['initial_state']
    if not isinstance(initial, dict) or set(initial) != {'deformation_gradient', 'internal_variables'}:
        raise ValueError('Declare the elastic initial F and empty internal_variables')
    if initial['internal_variables'] != []:
        raise ValueError('These elastic laws do not accept internal state variables or an imposed initial stress')
    initial_F = _array(initial['deformation_gradient'], (3, 3), 'initial F')
    with np.errstate(over='ignore', invalid='ignore'):
        initial_det = np.linalg.det(initial_F)
    if not np.isfinite(initial_det) or initial_det <= 0:
        raise ValueError('Initial state requires positive det(F)')
    solver = bc['solver']
    if not isinstance(solver, dict) or set(solver) != set(DEFAULT_SOLVER):
        raise ValueError('Declare atol, rtol, max_iterations and max_backtracks explicitly')
    _number(solver['atol'], 'stress absolute tolerance', positive=True)
    _number(solver['rtol'], 'stress relative tolerance', nonnegative=True)
    with np.errstate(over='ignore', invalid='ignore'):
        tolerances = solver['atol'] + solver['rtol'] * np.max(np.abs(np.asarray(list(targets.values()), dtype=float)), axis=0)
    if not np.isfinite(tolerances).all():
        raise ValueError('Stress tolerance overflow is not an admissible convergence criterion')
    for key in ('max_iterations', 'max_backtracks'):
        if type(solver[key]) is not int or not 1 <= solver[key] <= 1000:
            raise ValueError(key + ' must be an integer from 1 to 1000')
    return model, time, F


def uniaxial_settings(base: dict, values: list, *, control='stretch', lateral='free',
                       lateral_22=None, lateral_33=None, solver=None) -> dict:
    """Explicit UI helper; fixed/prescribed lateral remains the legacy F path.

    Stress-control targets use the base law's measure, never an implicit Cauchy
    conversion. A stress-control history still needs an axial initial F guess.
    """
    result = deepcopy(base)
    result.pop('boundary_control', None)
    if control not in {'stretch', 'engineering_strain', 'stress'}:
        raise ValueError('Choose stretch, engineering_strain or stress')
    if lateral not in {'free', 'fixed', 'prescribed'}:
        raise ValueError('Choose free, fixed or prescribed lateral control')
    n = len(result['time'])
    array = _array(values, (n,), control)
    F = np.repeat(np.eye(3)[None, :, :], n, axis=0)
    if control != 'stress':
        F[:, 0, 0] = array + (1 if control == 'engineering_strain' else 0)
    if lateral == 'prescribed':
        F[:, 1, 1] = _array(lateral_22, (n,), 'lateral F22')
        F[:, 2, 2] = _array(lateral_33, (n,), 'lateral F33')
    elif lateral_22 is not None or lateral_33 is not None:
        raise ValueError('Lateral histories only apply to prescribed lateral control')
    result['deformation_gradient'] = F.tolist()
    stress = {'xx': array.tolist()} if control == 'stress' else {}
    if lateral == 'free':
        stress.update(yy=[0.] * n, zz=[0.] * n)
    if stress:
        result['boundary_control'] = {
            'version': 1, 'stress_measure': MEASURES.get(result['model']),
            'frame': 'material_cartesian', 'stress_components': stress,
            'initial_state': {'deformation_gradient': np.eye(3).tolist(), 'internal_variables': []},
            'solver': deepcopy(DEFAULT_SOLVER if solver is None else solver),
        }
        validate_control_settings(result)
    else:
        from .adapters.felupe_material import validate_settings
        validate_settings(result)
    return result


def solve_history(settings: dict, point_response: Callable, *, check_cancelled=None,
                  _validated_context=None) -> dict:
    """Damped Newton on the exact controlled stress components.

    point_response(F) returns (stress[3,3], dStress_dF[3,3,3,3]). It must be
    stateless for the two admitted elastic laws. Test reference oracles are
    injected here; production uses FELUPE only. Tolerances never change on failure.
    """
    from .execution_control import ExecutionCancelled, ExecutionCleanupFailed
    # Trusted domain-only reuse: the stateful caller validates its own declaration,
    # invokes one increment, and closes over an immutable accepted state. This is
    # not a JSON input field and does not relax the public elastic admission.
    model, times, prescribed = (validate_control_settings(settings) if _validated_context is None
                                else _validated_context)
    bc, unit = settings['boundary_control'], settings['stress_unit']
    names = sorted(bc['stress_components'])
    ij = [COMPONENTS[name] for name in names]
    targets = np.asarray([bc['stress_components'][name] for name in names], dtype=float).T
    options = bc['solver']
    last_F = np.array(bc['initial_state']['deformation_gradient'], dtype=float)
    last_state = {'increment': None, 'time': None, 'deformation_gradient': last_F.tolist(),
                  'internal_variables': [], 'stress': None}
    accepted, failed = [], None
    diagnostics = {'controller': 'caelab.material_control/1', 'model': model,
                   'parameters': deepcopy(settings['parameters']),
                   'initial_state': deepcopy(bc['initial_state']),
                   'boundary_control': deepcopy(bc), 'constitutive_increments': accepted,
                   'stress_measure': bc['stress_measure'], 'frame': bc['frame'],
                   'engineering_release': 'NOT_ASSESSED',
                   'limitations': ['Material-point boundary solve, not FE boundary verification',
                                   'Time is an ordered elastic path, not rate dependence',
                                   'No temperature dependence or stateful constitutive integration']}

    def point(F):
        if check_cancelled:
            check_cancelled()
        stress, tangent = point_response(F.copy())
        stress = _array(stress, (3, 3), 'library stress')
        tangent = _array(tangent, (3, 3, 3, 3), 'library tangent')
        return stress, tangent

    for index, time in enumerate(times):
        F = prescribed[index].copy()
        for i, j in ij:
            F[i, j] = last_F[i, j]
        residual, tolerance, iterations, trace = None, None, 0, []
        try:
            with np.errstate(over='ignore', invalid='ignore'):
                determinant = np.linalg.det(F)
            if not np.isfinite(determinant) or determinant <= 0:
                raise ValueError('Continuation initial guess has nonpositive det(F)')
            # A fixed absolute + target-relative stress tolerance, not a mutable
            # iteration residual scale or a silently relaxed convergence test.
            tolerance = float(options['atol'] + options['rtol'] * np.max(np.abs(targets[index])))
            stress, tangent = point(F)
            for iterations in range(options['max_iterations'] + 1):
                with np.errstate(over='ignore', invalid='ignore'):
                    r = np.asarray([stress[i, j] for i, j in ij]) - targets[index]
                if not np.isfinite(r).all():
                    residual = None
                    raise RuntimeError('Nonfinite boundary stress residual')
                residual = float(np.max(np.abs(r)))
                trace.append({'iteration': iterations, 'residual': residual})
                if residual <= tolerance:
                    break
                if iterations == options['max_iterations']:
                    raise RuntimeError('Boundary Newton iteration limit reached')
                jac = np.asarray([[tangent[i, j, k, l] for k, l in ij] for i, j in ij])
                delta = np.linalg.solve(jac, -r)
                if not np.isfinite(delta).all():
                    raise RuntimeError('Nonfinite boundary Newton correction')
                accepted_trial = False
                for backtrack in range(options['max_backtracks']):
                    alpha = 2. ** -backtrack
                    trial = F.copy()
                    for (i, j), step in zip(ij, delta):
                        trial[i, j] += alpha * step
                    with np.errstate(over='ignore', invalid='ignore'):
                        trial_det = np.linalg.det(trial)
                    if not np.isfinite(trial).all() or not np.isfinite(trial_det) or trial_det <= 0:
                        continue
                    # A constitutive library failure is not an admissibility
                    # rejection: it fails this increment, preserving its reason.
                    trial_stress, trial_tangent = point(trial)
                    with np.errstate(over='ignore', invalid='ignore'):
                        trial_r = np.asarray([trial_stress[i, j] for i, j in ij]) - targets[index]
                    if not np.isfinite(trial_r).all():
                        continue
                    norm = float(np.max(np.abs(trial_r)))
                    if norm <= tolerance or norm <= (1. - 1e-4 * alpha) * residual:
                        F, stress, tangent = trial, trial_stress, trial_tangent
                        trace[-1]['accepted_step_length'] = alpha
                        accepted_trial = True
                        break
                if not accepted_trial:
                    raise RuntimeError('No admissible residual-decreasing boundary step')
            entry = {'increment': index, 'time': float(time), 'time_unit': settings['time_unit'],
                     'deformation_gradient': F.tolist(), 'gradient_unit': '1',
                     'stress': stress.tolist(), 'stress_unit': unit,
                     'stress_measure': bc['stress_measure'], 'frame': bc['frame'],
                     'tangent': tangent.tolist(), 'residual': residual, 'tolerance': tolerance,
                     'iterations': iterations, 'iteration_trace': trace,
                     'internal_variables': [], 'status': 'SUCCEEDED'}
            accepted.append(entry)
            last_F = F.copy()
            last_state = {key: deepcopy(entry[key]) for key in
                          ('increment', 'time', 'deformation_gradient', 'stress', 'internal_variables')}
        except (ExecutionCancelled, ExecutionCleanupFailed):
            raise
        except Exception as error:
            # Cooperative job cancellation must retain JobManager's semantics.
            if error.__class__.__name__ in {'ExecutionCancelled', 'StudyCancelled', 'ExecutionCleanupFailed'}:
                raise
            failed = {'increment': index, 'time': float(time), 'error_type': type(error).__name__,
                      'message': str(error), 'trial_deformation_gradient': F.tolist(),
                      'residual': residual, 'tolerance': tolerance, 'iterations': iterations,
                      'iteration_trace': trace, 'stress_unit': unit}
            break
    diagnostics.update(failed_increment=failed, last_valid_state=deepcopy(last_state),
                       accepted_count=len(accepted), requested_count=len(times),
                       unattempted_increments=list(range((failed['increment'] + 1) if failed else len(times), len(times))))
    responses = {}
    axis = [{'name': 'time', 'unit': settings['time_unit'], 'values': [r['time'] for r in accepted]}]
    for name, (i, j) in COMPONENTS.items():
        responses['stress_' + name] = {'kind': 'series', 'value': [r['stress'][i][j] for r in accepted],
            'unit': unit, 'component': name, 'location': 'material_point', 'reduction': 'none',
            'axes': deepcopy(axis), 'frame': bc['frame'], 'measure': bc['stress_measure'],
            'partial': bool(failed), 'valid': not bool(failed)}
        responses['F_' + name] = {'kind': 'series', 'value': [r['deformation_gradient'][i][j] for r in accepted],
            'unit': '1', 'component': name, 'location': 'material_point', 'reduction': 'none',
            'axes': deepcopy(axis), 'frame': bc['frame'], 'measure': 'deformation_gradient',
            'partial': bool(failed), 'valid': not bool(failed)}
    if accepted:
        responses['tangent'] = {'kind': 'field', 'value': [r['tangent'] for r in accepted], 'unit': unit,
            'component': 'ijkl', 'location': 'material_point', 'reduction': 'none', 'axes': deepcopy(axis),
            'partial': bool(failed), 'valid': not bool(failed)}
    return {'execution_status': 'FAILED' if failed else 'SUCCEEDED', 'responses': responses,
            'checks': [{'name': 'mixed_boundary_residual', 'status': 'FAIL' if failed else 'PASS'},
                       {'name': 'physical_calibration', 'status': 'NOT_ASSESSED'}], 'diagnostics': diagnostics}


def prepare_controlled(settings: dict, *, runtime=None):
    """Existing adapter.prepare dispatches here without registering a new backend."""
    from .evaluation import PreparedEvaluation
    from .adapters.felupe_material import validate_parameters
    from .storage import canonical_hash
    from .execution_control import check_cancelled
    validate_control_settings(settings, parameters=False)
    if runtime and set(runtime) - {'threads', 'memory_mb'}:
        raise ValueError('Unsupported FELUPE runtime options')
    try:
        import felupe
    except ImportError as error:
        from .contracts import CapabilityUnavailable
        raise CapabilityUnavailable('FELUPE runtime unavailable; no alternate law is substituted') from error
    snapshot = deepcopy(settings)

    def calculate(values):
        if not isinstance(values, dict) or set(values) - set(snapshot['parameters']):
            raise ValueError('Unknown material parameter')
        current = deepcopy(snapshot)
        current['parameters'].update(values)
        validate_parameters(current['model'], current['parameters'])
        material = (felupe.LinearElastic(**current['parameters']) if current['model'] == 'linear_elastic'
                    else felupe.NeoHookeCompressible(**current['parameters']))
        def point(F):
            # Same gradient/hessian boundary as FelupeMaterialAdapter; no stress
            # formula is duplicated or fitted inside the production controller.
            x = [F[:, :, None, None], np.zeros((0, 1, 1))]
            return (material.gradient(x)[0][:, :, 0, 0],
                    material.hessian(x)[0][..., 0, 0])
        result = solve_history(current, point, check_cancelled=check_cancelled)
        result['diagnostics'].update(library='felupe', version=felupe.__version__,
            execution_signature=canonical_hash({'adapter': 'material.felupe',
                'library_version': felupe.__version__, 'controller': 'caelab.material_control/1',
                'protocol': current}))
        return result
    return PreparedEvaluation(calculate, snapshot)
