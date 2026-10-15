"""Pure declarations for the bounded Windows-capable scikit-fem adapters.

Reuses the original dimensioned AST and thermoelastic physical validation.
Importing this module, editing, Check and saved reads never import skfem/SciPy.
"""
from copy import deepcopy
import ast

from plugins.thermoelastic import reference as original
from . import dimensioned_models as dimensioned
from .dimensioned_expression import ExpressionError
from . import p1_temperature_transfer as transfer

WEAK = 'pde.scikit_fem.dimensioned'
THERMAL = 'thermal.scikit_fem.rectangle'
STRUCTURAL = 'structural.scikit_fem.thermoelastic_rectangle'
BACKENDS = (WEAK, THERMAL, STRUCTURAL)
VERSIONS = {'scikit-fem': '12.0.2', 'numpy': '2.3.5', 'scipy': '1.17.0'}
LIMITATIONS = [
    'Serial float64 scikit-fem P1 assembly and SciPy SuperLU; no WSL, CAD, AI or paid service.',
    'Metre/global-Cartesian rectangles, at most 8192 triangles; no imported arbitrary geometry.',
    'Steady conduction or explicitly declared linear scalar volume weak form with Dirichlet/natural boundaries.',
    'Small-strain isotropic plane stress, constant E/nu/CTE; traction-free exterior with three rigid-mode anchors.',
    'Scalar nodal temperature interpolation on actual source cells, NOT a conservative transfer.',
    'Recorded snapshot selection/interpolation is not a transient heat or structural integrator.',
    'Original residual, temperature and free-expansion thresholds are not relaxed.',
    'Physical qualification, material suitability and engineering release remain UNKNOWN/NOT_RELEASED.',
]


def default_settings(backend):
    if backend == WEAK:
        result = dimensioned.default_settings(dimensioned.WEAK)
        result.update(physical={'quantity': transfer.ABSOLUTE, 'measure': 'thermodynamic_temperature', 'frame': 'global_cartesian'},
                      time={'value': 0., 'unit': 's', 'origin': 'steady_reference'})
        return result
    stage = 'thermal' if backend == THERMAL else 'structural' if backend == STRUCTURAL else None
    if stage is None:
        raise ValueError('Unknown scikit-fem capability')
    result = original.default_settings(stage)
    if stage == 'thermal':
        result['boundary_gradient'] = {'values': [0., 0.], 'unit': 'K/m'}
    else:
        result['temperature_mode'] = 'absolute'
    return result


def _weak_core(settings):
    core = deepcopy(settings)
    core.pop('physical', None); core.pop('time', None)
    return core


def validate_settings(backend, settings):
    if backend == WEAK:
        if not isinstance(settings, dict) or set(settings) != set(default_settings(WEAK)):
            raise ExpressionError('선언된 약형식·물리량·실제 snapshot 시간을 모두 지정하세요.')
        dimensioned.validate_settings(dimensioned.WEAK, _weak_core(settings))
        transfer.clock(settings['time'])
        physical = settings['physical']
        original._keys(physical, {'quantity', 'measure', 'frame'}, 'Scalar physical declaration')
        if physical['frame'] != 'global_cartesian':
            raise ExpressionError('전역 직교 좌표계만 지원합니다.', path='settings.physical.frame')
        if physical['quantity'] == transfer.ABSOLUTE:
            if settings['field']['unit'] != 'K' or physical['measure'] != 'thermodynamic_temperature':
                raise ExpressionError('절대 온도 선언에는 K와 thermodynamic_temperature가 필요합니다.', path='settings.physical')
        elif (physical['quantity'], physical['measure']) != ('declared_scalar', 'user_declared_scalar'):
            raise ExpressionError('물리량을 자동으로 온도로 해석하지 않습니다.', path='settings.physical')
        # The existing thermoelastic rectangular topology limit is also the
        # transfer limit.  This is a capability bound, not a relaxed tolerance.
        for n in settings['mesh']['levels']:
            geom = original.default_settings('thermal')
            geom['domain']['lengths'] = [settings['domain']['width'], settings['domain']['height']]
            geom['mesh']['cells'] = [n, n]
            original.validate_settings(geom, 'thermal')
        for label, source in settings['forms'].items():
            tree = ast.parse(source, mode='eval')
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'grad':
                    if any(isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
                           and child.func.id in ('grad', 'inner') for child in ast.walk(node.args[0])):
                        raise ExpressionError('P1 체적 약형식의 중첩 공간 미분은 지원하지 않습니다.',
                                              path='settings.forms.' + label, node=node)
        return deepcopy(settings)
    if backend not in (THERMAL, STRUCTURAL):
        raise ValueError('Unknown scikit-fem capability')
    stage = 'thermal' if backend == THERMAL else 'structural'
    if not isinstance(settings, dict) or set(settings) != set(default_settings(backend)):
        raise ValueError('Use only the declared scikit-fem stage settings')
    s = deepcopy(settings)
    original_clock = s['time']
    instant_s = transfer.clock(original_clock)
    s['time'] = {'value': float(instant_s), 'unit': 's', 'origin': original_clock['origin']}
    port = 'linearization_temperature' if stage == 'thermal' else 'temperature'
    captured = s[port]; s[port] = None
    if stage == 'thermal':
        gradient = s.pop('boundary_gradient')
        original._keys(gradient, {'values', 'unit'}, 'Affine boundary gradient')
        if gradient['unit'] != 'K/m' or not isinstance(gradient['values'], list) or len(gradient['values']) != 2:
            raise ValueError('Boundary gradient requires two explicit K/m components')
        gx, gy = [original.number(v, 'Boundary temperature gradient') for v in gradient['values']]
        boundary = s['boundary_temperature']
        original._keys(boundary, {'value', 'unit'}, 'Boundary absolute temperature')
        if boundary['unit'] not in transfer.ABS_UNITS:
            raise ValueError('Boundary temperature is absolute K or degC/°C, never a temperature difference')
        kelvin = original.number(boundary['value'], 'Boundary temperature') + transfer.ABS_UNITS[boundary['unit']]
        s['boundary_temperature'] = {'value': kelvin, 'unit': 'K'}
        original.validate_settings(s, stage)
        lx, ly = s['domain']['lengths']
        for x, y in ((0., 0.), (lx, 0.), (0., ly), (lx, ly)):
            original.number(kelvin + gx*x + gy*y, 'Affine absolute boundary temperature', low=0., high=5000.)
        if captured is not None:
            validated = transfer.validate_bound(captured, settings)
            # Same lagged-Picard law as the original domain; no new iteration engine.
            s[port] = {'value': transfer._absolute_values(validated)}
            original.conductivity_values(s)
    else:
        mode = s.pop('temperature_mode')
        if mode not in ('absolute', 'difference'):
            raise ValueError('Structural temperature input must explicitly be absolute or difference')
        original.validate_settings(s, stage)
        if captured is not None:
            transfer.validate_bound(captured, settings, quantity=transfer.ABSOLUTE if mode == 'absolute' else transfer.DIFFERENCE)
    return deepcopy(settings)


def geometry_settings(backend, settings, level=None):
    if backend != WEAK:
        return deepcopy(settings)
    n = settings['mesh']['levels'][-1] if level is None else level
    result = original.default_settings('thermal')
    result['domain']['lengths'] = [settings['domain']['width'], settings['domain']['height']]
    result['mesh']['cells'] = [n, n]
    result['time'] = deepcopy(settings['time'])
    return result


def model_declaration(backend, settings):
    settings = validate_settings(backend, settings)
    return {'kind': 'scikit_fem_dimensioned_weak' if backend == WEAK else 'scikit_fem_' + ('conduction' if backend == THERMAL else 'plane_stress'),
            'backend': backend, 'backend_version': '1', 'model': deepcopy(settings),
            'coordinate_unit': 'm', 'time_unit': settings['time']['unit'],
            'snapshot_physics': 'steady', 'required_runtime': deepcopy(VERSIONS)}


def temperature_port(required, *, quantity=transfer.ABSOLUTE):
    port = original.temperature_port(required)
    port.update(basis='P1', mappings=['exact_same_mesh', transfer.MAPPING], required_region='all_receiver_nodes')
    if quantity == transfer.DIFFERENCE:
        port.update(quantity=quantity, unit='delta_K', measure=transfer.DIFFERENCE)
    return port


def describe_ports(backend, settings):
    settings = validate_settings(backend, settings)
    if backend == WEAK:
        return {'inputs': {}, 'outputs': {settings['field']['name']: temperature_port(False)}
                if settings['physical']['quantity'] == transfer.ABSOLUTE else {}}
    if backend == THERMAL:
        return {'inputs': {'linearization_temperature': temperature_port(False)},
                'outputs': {'temperature': temperature_port(False)}}
    result = original.describe_ports({k: v for k, v in settings.items() if k != 'temperature_mode'} | {'temperature': None,
        'time': {'value': float(transfer.clock(settings['time'])), 'unit': 's', 'origin': settings['time']['origin']}}, 'structural')
    result['inputs']['temperature'] = temperature_port(True, quantity=transfer.ABSOLUTE if settings['temperature_mode'] == 'absolute' else transfer.DIFFERENCE)
    return result


def bind_port(backend, settings, port, response):
    settings = validate_settings(backend, settings)
    expected = 'linearization_temperature' if backend == THERMAL else 'temperature' if backend == STRUCTURAL else None
    if port != expected:
        raise ValueError('Choose the advertised temperature input port')
    quantity = transfer.DIFFERENCE if backend == STRUCTURAL and settings['temperature_mode'] == 'difference' else transfer.ABSOLUTE
    settings[port] = transfer.validate_bound(response, settings, quantity=quantity)
    return validate_settings(backend, settings)


def describe_inputs(backend, settings):
    settings = validate_settings(backend, settings)
    if backend == WEAK:
        return dimensioned.describe_inputs(dimensioned.WEAK, _weak_core(settings))
    # Reuse the original stage coefficient ownership/IDs, without importing any
    # solver.  Extra geometry/gradient inputs are explicit, not hidden runtime.
    fields = ({'conductivity': ('conductivity', 'value', 'W/(m*K)'),
               'conductivity_temperature_slope': ('conductivity', 'beta', '1/K'),
               'conductivity_reference_temperature': ('conductivity', 'reference_temperature', 'K'),
               'heat_source': ('heat_source', 'value', 'W/m^3'),
               'boundary_temperature': ('boundary_temperature', 'value', settings['boundary_temperature']['unit'])}
              if backend == THERMAL else
              {'young_modulus': ('material', 'young_modulus', 'Pa'), 'poisson_ratio': ('material', 'poisson_ratio', '1'),
               'thermal_expansion': ('material', 'thermal_expansion', '1/K'), 'reference_temperature': ('material', 'reference_temperature', 'K')})
    return [{'id': name, 'label': name.replace('_', ' '), 'unit': unit, 'type': 'continuous',
             'value': settings[section][key], 'settings_path': [section, key],
             'declaration_paths': [['model', section, key]]} for name, (section, key, unit) in fields.items()]


def bind_inputs(backend, settings, values):
    settings = validate_settings(backend, settings)
    rows = {r['id']: r for r in describe_inputs(backend, settings)}
    if not isinstance(values, dict) or set(values) - set(rows):
        raise ValueError('Choose only advertised physical inputs')
    if backend == WEAK:
        updated = dimensioned.bind_inputs(dimensioned.WEAK, _weak_core(settings), values)
        return validate_settings(backend, dict(updated, physical=settings['physical'], time=settings['time']))
    for key, value in values.items():
        section, name = rows[key]['settings_path']
        settings[section][name] = value
    return validate_settings(backend, settings)
