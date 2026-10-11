"""Pure declarations for the thermal/elastic worker; no native imports or solve.

The geometry is a metre rectangle with serial triangular P1 elements. Material
numbers are explicit assumed SI inputs, not qualified material data. Transfer is
an exact captured nodal field on the same declared mesh, with no interpolation.
"""
from copy import deepcopy
import hashlib
import json
import math

VERSION = '1'
LIMITATIONS = ['Steady isotropic conduction; uniform all-boundary Dirichlet temperature.',
               'Uniform through-thickness temperature, no out-of-plane gradient; constant thickness cancels from the 2D weak forms.',
               'Small-strain 2D isotropic plane stress; constant E, nu and thermal expansion.',
               'Traction-free mechanical exterior; origin ux/uy and lower-right uy remove rigid modes.',
               'Same rectangle/P1 triangular mesh only; no projection or coordinate/unit conversion.',
               'Temperature-dependent conductivity is an explicit lagged Picard linearization.',
               'No contact, plasticity, transient heat, physical qualification or engineering release.']


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(label + ' requires exactly ' + ', '.join(sorted(expected)))


def number(value, label, *, low=None, high=None):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid or low is not None and value < low or high is not None and value > high:
        raise ValueError(label + ' requires a finite number within its declared bounds')
    return value


def default_settings(stage='thermal'):
    settings = {'domain': {'type': 'rectangle', 'lengths': [1., .25], 'unit': 'm', 'frame': 'global_cartesian'},
                'mesh': {'cells': [8, 4], 'degree': 1, 'cell': 'triangle'},
                'time': {'value': 0., 'unit': 's', 'origin': 'steady_reference'},
                'validation': {'max_residual_relative': 1e-10}}
    if stage == 'thermal':
        settings.update(conductivity={'value': 200., 'unit': 'W/(m*K)', 'beta': 0., 'beta_unit': '1/K',
                                      'reference_temperature': 293.15, 'reference_unit': 'K'},
                        heat_source={'value': 0., 'unit': 'W/m^3'},
                        boundary_temperature={'value': 323.15, 'unit': 'K'}, linearization_temperature=None)
    elif stage == 'structural':
        settings.update(material={'young_modulus': 70e9, 'young_modulus_unit': 'Pa', 'poisson_ratio': .3,
                                  'poisson_ratio_unit': '1', 'thermal_expansion': 23e-6,
                                  'thermal_expansion_unit': '1/K', 'reference_temperature': 293.15,
                                  'reference_temperature_unit': 'K', 'assumption': 'plane_stress'},
                        temperature=None)
        settings['validation'].update(free_expansion_max_error=1e-10, temperature_uniformity_tolerance=1e-8)
    else:
        raise ValueError('Choose thermal or structural stage')
    return validate_settings(settings, stage)


def mesh_declaration(settings):
    return {key: deepcopy(settings[key]) for key in ('domain', 'mesh')}


def mesh_digest(coordinates, cells):
    return digest({'coordinates': coordinates, 'cell_node_ids': cells})


def seal_field(field):
    value = deepcopy(field)
    value.pop('capture_sha256', None)
    value['capture_sha256'] = digest(value)
    return value


def validate_temperature(field, settings):
    required = {'kind', 'value', 'unit', 'quantity', 'component', 'location', 'reduction', 'association',
                'measure', 'frame', 'coordinate_units', 'coordinate_frame', 'coordinates', 'node_ids',
                'cell_node_ids', 'mesh_declaration', 'mesh_sha256', 'time', 'time_units', 'time_origin', 'capture_sha256'}
    _keys(field, required, 'Captured temperature')
    metadata = {'kind': 'field', 'unit': 'K', 'quantity': 'absolute_temperature', 'component': 'scalar',
                'location': 'node', 'reduction': 'none', 'association': 'POINTS', 'measure': 'thermodynamic_temperature',
                'frame': 'global_cartesian', 'coordinate_units': 'm', 'coordinate_frame': 'global_cartesian'}
    if any(field[key] != value for key, value in metadata.items()):
        raise ValueError('Temperature port requires explicit absolute Kelvin nodal metadata in metre/global coordinates')
    if field['mesh_declaration'] != mesh_declaration(settings):
        raise ValueError('Temperature transfer requires the exact same declared mesh')
    time = settings['time']
    if (field['time'], field['time_units'], field['time_origin']) != (time['value'], time['unit'], time['origin']):
        raise ValueError('Temperature field time, unit and origin differ from the stage')
    nx, ny = settings['mesh']['cells']
    count = (nx + 1) * (ny + 1)
    ids, xyz, values, cells = (field[key] for key in ('node_ids', 'coordinates', 'value', 'cell_node_ids'))
    if not isinstance(ids, list) or ids != list(range(count)):
        raise ValueError('Captured field requires complete ordered serial node identities')
    if not isinstance(xyz, list) or len(xyz) != count or not isinstance(values, list) or len(values) != count:
        raise ValueError('Captured temperature coordinates and values must cover every P1 node')
    lx, ly = settings['domain']['lengths']
    positions, grid = set(), []
    for point, temperature in zip(xyz, values):
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError('Temperature field coordinates must be two-dimensional')
        x, y = (number(v, 'coordinate') for v in point)
        i, j = round(x / lx * nx), round(y / ly * ny)
        if not (0 <= i <= nx and 0 <= j <= ny and math.isclose(x, i * lx / nx, rel_tol=1e-12, abs_tol=1e-14)
                and math.isclose(y, j * ly / ny, rel_tol=1e-12, abs_tol=1e-14)) or (i, j) in positions:
            raise ValueError('Temperature coordinates must cover the exact declared rectangle grid')
        positions.add((i, j))
        grid.append((i, j))
        number(temperature, 'Absolute temperature', low=0., high=5000.)
    if (not isinstance(cells, list) or len(cells) != 2 * nx * ny
            or any(not isinstance(cell, list) or len(cell) != 3 or len(set(cell)) != 3
                   or any(type(node) is not int or not 0 <= node < count for node in cell) for cell in cells)
            or len({tuple(sorted(cell)) for cell in cells}) != len(cells)):
        raise ValueError('Captured field requires every distinct triangular cell')
    tiles = {}
    for cell in cells:
        points = {grid[node] for node in cell}
        i, j = min(p[0] for p in points), min(p[1] for p in points)
        corners = {(i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)}
        if not (0 <= i < nx and 0 <= j < ny and points <= corners):
            raise ValueError('Captured triangle must lie in one declared grid cell')
        tiles.setdefault((i, j), []).append(points)
    for i in range(nx):
        for j in range(ny):
            triangles = tiles.get((i, j), [])
            if len(triangles) != 2:
                raise ValueError('Captured triangular cells do not cover the declared mesh')
            shared = list(triangles[0] & triangles[1])
            if (len(shared) != 2 or abs(shared[0][0] - shared[1][0]) != 1
                    or abs(shared[0][1] - shared[1][1]) != 1):
                raise ValueError('Captured triangles overlap or leave a gap in a grid cell')
    if field['mesh_sha256'] != mesh_digest(xyz, cells) or seal_field(field)['capture_sha256'] != field['capture_sha256']:
        raise ValueError('Captured temperature or mesh content hash changed')
    return deepcopy(field)


def conductivity_values(settings):
    data = settings['conductivity']
    old = settings['linearization_temperature']
    temperatures = old['value'] if old is not None else [data['reference_temperature']]
    values = [data['value'] * (1. + data['beta'] * (temperature - data['reference_temperature'])) for temperature in temperatures]
    if any(not math.isfinite(value) or value <= 0. for value in values):
        raise ValueError('Lagged temperature-dependent conductivity must remain strictly positive at every node')
    return values


def validate_settings(settings, stage):
    common = {'domain', 'mesh', 'time', 'validation'}
    extra = {'conductivity', 'heat_source', 'boundary_temperature', 'linearization_temperature'} if stage == 'thermal' else {'material', 'temperature'}
    if stage not in ('thermal', 'structural'):
        raise ValueError('Unknown thermoelastic stage')
    _keys(settings, common | extra, 'Stage settings')
    domain, mesh, time, validation = (settings[key] for key in ('domain', 'mesh', 'time', 'validation'))
    _keys(domain, {'type', 'lengths', 'unit', 'frame'}, 'Domain')
    if domain['type'] != 'rectangle' or domain['unit'] != 'm' or domain['frame'] != 'global_cartesian':
        raise ValueError('Only a metre/global-cartesian rectangle is supported')
    if not isinstance(domain['lengths'], list) or len(domain['lengths']) != 2:
        raise ValueError('Declare both rectangle lengths')
    for value in domain['lengths']: number(value, 'Rectangle length [m]', low=1e-5, high=1000.)
    _keys(mesh, {'cells', 'degree', 'cell'}, 'Mesh')
    if (mesh['degree'] != 1 or type(mesh['degree']) is not int or mesh['cell'] != 'triangle'
            or not isinstance(mesh['cells'], list) or len(mesh['cells']) != 2
            or any(type(n) is not int or not 1 <= n <= 128 for n in mesh['cells'])
            or math.prod(mesh['cells']) > 4096):
        raise ValueError('Mesh requires bounded serial triangular P1 cells (at most 8192 triangles)')
    _keys(time, {'value', 'unit', 'origin'}, 'Time')
    number(time['value'], 'Steady time')
    if time['unit'] != 's' or not isinstance(time['origin'], str) or not time['origin'].strip() or len(time['origin']) > 256:
        raise ValueError('Declare a steady snapshot time in seconds with an explicit origin')
    validation_keys = {'max_residual_relative'} | ({'free_expansion_max_error', 'temperature_uniformity_tolerance'} if stage == 'structural' else set())
    _keys(validation, validation_keys, 'Validation')
    number(validation['max_residual_relative'], 'Residual threshold', low=1e-14, high=1e-4)
    if stage == 'thermal':
        data = settings['conductivity']
        _keys(data, {'value', 'unit', 'beta', 'beta_unit', 'reference_temperature', 'reference_unit'}, 'Conductivity')
        if (data['unit'], data['beta_unit'], data['reference_unit']) != ('W/(m*K)', '1/K', 'K'):
            raise ValueError('Declare conductivity W/(m*K), beta 1/K and reference K explicitly')
        number(data['value'], 'Conductivity', low=1e-8, high=1e6)
        number(data['beta'], 'Conductivity beta', low=-.1, high=.1)
        number(data['reference_temperature'], 'Conductivity reference temperature', low=0., high=5000.)
        for key, unit, low, high in (('heat_source', 'W/m^3', -1e8, 1e8), ('boundary_temperature', 'K', 0., 5000.)):
            _keys(settings[key], {'value', 'unit'}, key)
            if settings[key]['unit'] != unit: raise ValueError(key + ' requires unit ' + unit)
            number(settings[key]['value'], key, low=low, high=high)
        if settings['linearization_temperature'] is not None:
            validate_temperature(settings['linearization_temperature'], settings)
        conductivity_values(settings)
    else:
        material = settings['material']
        _keys(material, {'young_modulus', 'young_modulus_unit', 'poisson_ratio', 'poisson_ratio_unit',
                         'thermal_expansion', 'thermal_expansion_unit', 'reference_temperature',
                         'reference_temperature_unit', 'assumption'}, 'Elastic material')
        if (material['young_modulus_unit'], material['poisson_ratio_unit'], material['thermal_expansion_unit'],
            material['reference_temperature_unit'], material['assumption']) != ('Pa', '1', '1/K', 'K', 'plane_stress'):
            raise ValueError('Material requires SI E/CTE/reference temperature and explicit plane_stress')
        number(material['young_modulus'], 'Young modulus', low=1., high=1e13)
        number(material['poisson_ratio'], 'Poisson ratio', low=-.99, high=.49)
        number(material['thermal_expansion'], 'Thermal expansion', low=-.01, high=.01)
        number(material['reference_temperature'], 'Reference temperature', low=0., high=5000.)
        if validation['free_expansion_max_error'] is not None:
            number(validation['free_expansion_max_error'], 'Free expansion displacement threshold [m]', low=1e-14, high=.01)
        number(validation['temperature_uniformity_tolerance'], 'Benchmark uniformity tolerance [K]', low=1e-14, high=.01)
        if settings['temperature'] is not None: validate_temperature(settings['temperature'], settings)
    return json.loads(json.dumps(settings, allow_nan=False))


def temperature_port(required):
    return {'kind': 'field', 'unit': 'K', 'quantity': 'absolute_temperature', 'association': 'POINTS',
            'component': 'scalar', 'location': 'node', 'measure': 'thermodynamic_temperature', 'frame': 'global_cartesian',
            'coordinate_units': 'm', 'coordinate_frame': 'global_cartesian', 'transfer': 'exact_same_mesh', 'required': required}


def describe_ports(settings, stage):
    validate_settings(settings, stage)
    if stage == 'thermal':
        return {'inputs': {'linearization_temperature': temperature_port(False)},
                'outputs': {'temperature': temperature_port(False)}}
    return {'inputs': {'temperature': temperature_port(True)},
            'outputs': {'displacement': {'kind': 'field', 'unit': 'm', 'quantity': 'displacement',
                'association': 'POINTS', 'components': ['x', 'y'], 'frame': 'global_cartesian'},
                        'stress': {'kind': 'field', 'unit': 'Pa', 'quantity': 'stress', 'association': 'CELLS',
                                   'components': ['xx', 'yy', 'xy'], 'measure': 'infinitesimal_Cauchy', 'frame': 'global_cartesian',
                                   'reduction': 'cell_average'}}}


def bind_port(settings, stage, port, response):
    result = validate_settings(settings, stage)
    expected = 'linearization_temperature' if stage == 'thermal' else 'temperature'
    if port != expected: raise ValueError('Unsupported declared stage input port: ' + str(port))
    result[port] = validate_temperature(response, result)
    return validate_settings(result, stage)
