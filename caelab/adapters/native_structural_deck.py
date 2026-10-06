"""CalculiX syntax for verified native-face loads and explicit displacement DOFs."""
from collections import defaultdict
import math
import numpy as np


def native_number(value):
    """CalculiX free-format numeric fields have a 20-character limit."""
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('A native numeric field must be finite')
    token = f'{value:.12e}'
    if len(token) > 20 or not math.isfinite(float(token)):
        raise ValueError('A native numeric field exceeds CalculiX serialization limits')
    return token


def prepare(mesh, declaration):
    nodes = {int(n): tuple(xyz) for n, xyz in mesh['nodes'].items()}
    elements = {int(e): tuple(row) for e, row in mesh['elements'].items()}
    boundary = {}
    for item in declaration['boundary_conditions']:
        for node in mesh['face_nodes'][item['selection_id']]:
            for name, value in item['components'].items():
                key = (node, {'UX': 1, 'UY': 2, 'UZ': 3}[name])
                if key in boundary and boundary[key] != value:
                    raise ValueError('Conflicting prescribed displacement at a shared native face node')
                boundary[key] = value
    forces = defaultdict(float)
    load_observations = []
    for item in declaration['loads']:
        face = mesh['face_weights'][item['selection_id']]
        area = face['mesh_area_mm2']
        target = [item['components'][name] for name in ('FX', 'FY', 'FZ')]
        for native, weight in face['nodal_area_weights_mm2'].items():
            node = int(native)
            for component, total in enumerate(target, 1):
                forces[node, component] += weight / area * total
        load_observations.append({'id': item['id'], 'selection_id': item['selection_id'],
                                  'resultant_N': target, 'native_area_mm2': face['native_area_mm2'],
                                  'mesh_area_mm2': area, 'distribution': mesh['load_distribution']})
    forces = {key: value for key, value in forces.items() if value != 0}
    if any(key in boundary for key in forces):
        raise ValueError('A nonzero applied nodal force shares its constrained DOF; reaction interpretation is ambiguous')
    if not boundary or not forces:
        raise ValueError('Explicit active displacement constraints and forces are required')
    origin = np.mean(np.asarray(list(nodes.values())), axis=0)
    length = max(float(np.ptp(np.asarray(list(nodes.values())), axis=0).max()), 1.)
    rigid = []
    for node, component in boundary:
        x, y, z = (np.asarray(nodes[node]) - origin) / length
        rigid.append(([1, 0, 0, 0, z, -y], [0, 1, 0, -z, 0, x], [0, 0, 1, y, -x, 0])[component-1])
    if np.linalg.matrix_rank(np.asarray(rigid)) != 6:
        raise ValueError('The declared displacement DOFs leave unrestrained rigid-body modes')
    applied = [math.fsum(value for (_, component), value in forces.items() if component == axis) for axis in (1, 2, 3)]
    expected = [math.fsum(item['components'][axis] for item in declaration['loads']) for axis in ('FX', 'FY', 'FZ')]
    if any(abs(a-b) > 64 * math.ulp(max(1., abs(a), abs(b))) for a, b in zip(applied, expected)):
        raise ValueError('Consistent surface integration does not preserve the declared force resultant')
    return nodes, elements, boundary, forces, load_observations, applied


def write(path, mesh, declaration):
    nodes, elements, boundary, forces, observations, applied = prepare(mesh, declaration)
    material = declaration['materials'][0]
    lines = ['*HEADING', 'Revision-bound native single-solid linear static analysis', '*NODE']
    serialized_nodes = {n: [float(native_number(v)) for v in xyz] for n, xyz in nodes.items()}
    lines += [f'{node}, ' + ', '.join(native_number(v) for v in xyz) for node, xyz in sorted(nodes.items())]
    lines += ['*ELEMENT, TYPE=C3D10, ELSET=BODY']
    lines += [str(element) + ', ' + ', '.join(map(str, row)) for element, row in sorted(elements.items())]
    lines += ['*NSET, NSET=ALL_NODES']
    ids = sorted(nodes)
    lines += [', '.join(map(str, ids[i:i+12])) for i in range(0, len(ids), 12)]
    lines += ['*MATERIAL, NAME=DECLARED_MATERIAL', '*ELASTIC',
              f"{native_number(material['young_modulus_MPa'])}, {native_number(material['poisson_ratio'])}",
              '*SOLID SECTION, ELSET=BODY, MATERIAL=DECLARED_MATERIAL',
              '*STEP', '*STATIC', '*BOUNDARY']
    lines += [f'{node}, {component}, {component}, {native_number(value)}'
              for (node, component), value in sorted(boundary.items())]
    lines += ['*CLOAD']
    lines += [f'{node}, {component}, {native_number(value)}' for (node, component), value in sorted(forces.items())]
    lines += ['*NODE PRINT, NSET=ALL_NODES', 'U, RF', '*NODE FILE, NSET=ALL_NODES', 'U',
              '*EL FILE', 'S', '*END STEP']
    path.write_text('\n'.join(lines) + '\n', encoding='ascii')
    return {'node_count': len(nodes), 'element_count': len(elements), 'fixed_dofs':
            [{'node_id': n, 'component': d, 'value_mm': float(native_number(value)),
              'declared_value_mm': value, 'value_token': native_number(value)} for (n, d), value in sorted(boundary.items())],
            'loads': [{'node_id': n, 'component': d, 'force_N': float(native_number(value)),
                       'integration_force_N': value, 'force_token': native_number(value)} for (n, d), value in sorted(forces.items())],
            'serialized_node_coordinates_mm': serialized_nodes,
            'load_regions': observations, 'total_applied_force_N': [math.fsum(float(native_number(v))
                for (_,d),v in forces.items() if d == axis) for axis in (1,2,3)],
            'integration_resultant_N': applied, 'rigid_body_constraint_rank': 6,
            'native_serialization': '20-character CalculiX fields; 13 significant digits; signed weights retained'}


def read_tables(path, nodes, *, data=None):
    tables, current = {}, None
    tokens = {'U': {}, 'RF': {}}
    raw = path.read_bytes() if data is None else data
    for line in raw.decode('ascii').splitlines():
        lower = line.strip().lower()
        if lower.startswith(('displacements (vx,vy,vz)', 'forces (fx,fy,fz)')):
            if ' for set all_nodes and time ' not in lower or float(lower.rsplit(' ', 1)[-1]) != 1.:
                raise ValueError('Unexpected native displacement/force set or static load parameter')
            current = 'U' if lower.startswith('displacements') else 'RF'
            if current in tables:
                raise ValueError('Duplicate native static response table')
            tables[current] = {}
            continue
        fields = line.split()
        if current and len(fields) == 4 and fields[0].isdigit():
            node = int(fields[0])
            values = [float(value.replace('D', 'E')) for value in fields[1:]]
            if node not in nodes or node in tables[current] or not all(math.isfinite(v) for v in values):
                raise ValueError('Foreign, duplicate or nonfinite native response')
            tables[current][node] = values
            tokens[current][node] = fields[1:]
    if set(tables) != {'U', 'RF'} or any(set(table) != set(nodes) for table in tables.values()):
        raise ValueError('Incomplete native displacement/force output for the actual complete mesh')
    tables['tokens'] = tokens
    return tables
