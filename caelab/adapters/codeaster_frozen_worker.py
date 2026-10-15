"""Code_Aster17.4 consumer of the existing, checked FreeCAD TET10 snapshot.

Only solve imports Code_Aster. Mesh identity and result parsing can be checked
without a solver; no shape, mesh, load or response is generated here.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

try:
    from .codeaster_worker import (coordinate_bijection, _finite, _identifier,
        _table, _table_identifier, _field_order, _runtime_versions, _save,
        VECTOR_COMPONENTS, STRESS_COMPONENTS, COORDINATE_COMPONENTS)
    from .fixture_assembly_field_geometry import tetra10_gauss
except ImportError:  # copied beside codeaster_worker inside the existing SIF
    from codeaster_worker import (coordinate_bijection, _finite, _identifier,
        _table, _table_identifier, _field_order, _runtime_versions, _save,
        VECTOR_COMPONENTS, STRESS_COMPONENTS, COORDINATE_COMPONENTS)
    from fixture_assembly_field_geometry import tetra10_gauss


def mesh_text(mesh):
    """ASTER and frozen C3D10 share edge order; retain explicit external IDs."""
    nodes, cells = mesh['nodes'], mesh['elements']
    if len(nodes) > 200000 or len(cells) > 500000:
        raise ValueError('Frozen Aster mesh exceeds the existing native mesh budget')
    labels = {row['node_id']: 'N'+str(i+1) for i, row in enumerate(nodes)}
    elements = {row['element_id']: 'M'+str(i+1) for i, row in enumerate(cells)}
    lines = ['TITRE', 'Retained FreeCAD FEM mesh, mm N MPa', 'FINSF', 'COOR_3D']
    for row in nodes:
        xyz = [format(v, '.17g') for v in row['position_mm']]
        lines += [labels[row['node_id']]+' '+' '.join(xyz[:2]),xyz[2]]
    lines += ['FINSF', 'TETRA10']
    for row in cells:
        names = [labels[n] for n in row['node_ids']]
        lines += [elements[row['element_id']]+' '+' '.join(names[:5]),' '.join(names[5:])]
    lines += ['FINSF', 'GROUP_MA', 'BODY', *elements.values(), 'FINSF',
              'GROUP_NO', 'FIXED', *[labels[n] for n in sorted({r['node_id'] for r in mesh['fixed_dofs']})], 'FINSF', 'FIN', '']
    return '\n'.join(lines), labels, elements


def check_import(mesh, expected):
    """Prove actual native node/topology/support identity before MECA."""
    coords = mesh.getCoordinates().toNumpy().tolist()
    nodes, cells = expected['nodes'], expected['elements']
    wanted = [row['position_mm'] for row in nodes]
    mapping = coordinate_bijection(coords, wanted)
    if (mapping is None or list(mesh.getNodes()) != list(range(len(nodes)))
            or mesh.getNumberOfNodes() != len(nodes)
            or mesh.getNumberOfCells() != len(cells)
            or set(mesh.getCells('BODY')) != set(range(len(cells)))):
        raise ValueError('Native Aster node/cell catalogue differs from the frozen mesh')
    node_ids = [nodes[index]['node_id'] for index in mapping]
    by_connectivity = {tuple(row['node_ids']): row['element_id'] for row in cells}
    native_elements = []
    for index, connectivity in enumerate(mesh.getConnectivity()):
        key = tuple(node_ids[n] for n in connectivity)
        if mesh.getCellTypeName(index) != 'TETRA10' or key not in by_connectivity:
            raise ValueError('Native Aster TETRA10 connectivity/order differs from the frozen mesh')
        native_elements.append(by_connectivity[key])
    fixed = {row['node_id'] for row in expected['fixed_dofs']}
    if len(native_elements) != len(cells) or len(set(native_elements)) != len(cells) or {node_ids[n] for n in mesh.getNodes('FIXED')} != fixed:
        raise ValueError('Native Aster body or Fixed selection differs from the frozen mesh')
    return {'status':'PASS', 'node_ids_in_native_order':node_ids,
        'element_ids_in_native_order':native_elements, 'coordinates_in_native_order':coords,
        'fixed_node_ids':sorted(fixed), 'solver_gate':'CHECKED_BEFORE_MECA_STATIQUE'}


def _gauss_positions(points):
    return [row['xyz_mm'] for row in tetra10_gauss(points)]


def parse_result(raw, expected):
    """Full native DEPL/REAC and FPG5 coverage; missing rows never become zero."""
    if raw.get('solver_status') != 'COMPLETED' or raw.get('converged') is not True:
        raise ValueError('Native Aster result did not complete')
    if raw.get('versions',{}).get('code_aster') != '17.4.0':
        raise ValueError('Frozen Aster path requires the existing pinned17.4 runtime')
    guard, tables = raw['native_mesh_checks'], raw['tables']
    if guard.get('status') != 'PASS':
        raise ValueError('Native Aster mesh admission did not pass')
    order = _identifier(raw['order'], 'order')
    if raw.get('available_orders') != [order]:
        raise ValueError('Single linear static result requires exactly one native order')
    access = raw.get('access_parameters',{})
    if access.get('NUME_ORDRE') != [order]:
        raise ValueError('Native result access order differs from its field tables')
    # Aster static INST is a load parameter, never physical time in seconds.
    instants = access.get('INST')
    if not isinstance(instants,list) or len(instants) != 1:
        raise ValueError('Missing actual native static load parameter')
    parameter = _finite(instants[0], 'static load parameter')
    node_order = guard['node_ids_in_native_order']
    element_order = guard['element_ids_in_native_order']
    source_nodes = {row['node_id']: row['position_mm'] for row in expected['nodes']}
    source_elements = {row['element_id']: row['node_ids'] for row in expected['elements']}
    if (len(node_order) != len(source_nodes) or set(node_order) != set(source_nodes)
            or len(element_order) != len(source_elements) or set(element_order) != set(source_elements)
            or guard.get('fixed_node_ids') != sorted({r['node_id'] for r in expected['fixed_dofs']})):
        raise ValueError('Native/source mesh map is incomplete')
    def nodal(field):
        table,count = _table(tables.get(field), ('NOEUD','NUME_ORDRE',*COORDINATE_COMPONENTS,*VECTOR_COMPONENTS),field)
        values = {}
        for row in range(count):
            index = _table_identifier(table['NOEUD'][row],'NOEUD')-1
            if not 0 <= index < len(node_order) or node_order[index] in values:
                raise ValueError('Unknown or duplicate native nodal row')
            _field_order(table,row,order,field)
            n = node_order[index]
            xyz = [_finite(table[key][row],'node coordinate') for key in COORDINATE_COMPONENTS]
            if any(not math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12) for a,b in zip(xyz,source_nodes[n])):
                raise ValueError('Native nodal row coordinates differ from the frozen source')
            values[n] = [_finite(table[key][row],field) for key in VECTOR_COMPONENTS]
        if set(values) != set(source_nodes):
            raise ValueError('Missing native nodal rows')
        return values
    displacements, reactions = nodal('DEPL'), nodal('REAC_NODA')
    stress,count = _table(tables.get('SIEF_ELGA'), ('MAILLE','POINT','SOUS_POINT','NUME_ORDRE',*COORDINATE_COMPONENTS,*STRESS_COMPONENTS),'SIEF_ELGA')
    rows, seen = [], set()
    positions = {element:[] for element in source_elements}
    for row in range(count):
        index = _table_identifier(stress['MAILLE'][row],'MAILLE')-1
        point = _identifier(stress['POINT'][row],'POINT')
        subpoint = _identifier(stress['SOUS_POINT'][row],'SOUS_POINT')
        _field_order(stress,row,order,'SIEF_ELGA')
        if not 0 <= index < len(element_order) or point not in range(1,6) or subpoint != 1 or (index,point) in seen:
            raise ValueError('Unknown or duplicate native stress point')
        seen.add((index,point))
        rows.append({'element_id':element_order[index], 'point':point,'subpoint':subpoint,'order':order,
            'position_mm':[_finite(stress[key][row],'stress coordinate') for key in COORDINATE_COMPONENTS],
            'stress_MPa':[_finite(stress[key][row],'stress') for key in STRESS_COMPONENTS]})
        positions[element_order[index]].append(rows[-1]['position_mm'])
    if len(seen) != 5*len(source_elements):
        raise ValueError('Missing native TETRA10 FPG5 stress points')
    for element,connectivity in source_elements.items():
        if coordinate_bijection(positions[element],_gauss_positions([source_nodes[n] for n in connectivity])) is None:
            raise ValueError('Actual native Gauss coordinates differ from the frozen quadratic element')
    fixed = guard['fixed_node_ids']
    return {'order':order, 'static':{'step':1,'increment':order,'load_parameter':parameter},
        'displacements':displacements, 'reactions':reactions, 'stress_points':rows,
        'support_reaction_N':[math.fsum(reactions[n][axis] for n in fixed) for axis in range(3)]}


def solve(input_path):
    from code_aster.Commands import (DEBUT, FIN, LIRE_MAILLAGE, AFFE_MODELE,
        DEFI_MATERIAU, AFFE_MATERIAU, AFFE_CHAR_MECA, MECA_STATIQUE,
        CALC_CHAMP, CREA_TABLE, IMPR_RESU)
    from code_aster.Cata.Syntax import _F
    path = Path(input_path)
    config = json.loads(path.read_text(encoding='utf-8'))
    root = path.parent
    expected_path = root/'mesh.json'
    expected = json.loads(expected_path.read_text(encoding='utf-8'))
    if hashlib.sha256(expected_path.read_bytes()).hexdigest() != config['mesh_record_sha256']:
        raise ValueError('Frozen worker mesh record changed')
    DEBUT()
    if hashlib.sha256(Path('fort.20').read_bytes()).hexdigest() != config['mail_sha256']:
        raise ValueError('Native linked mesh differs from retained input')
    versions,runtime = _runtime_versions()
    if versions.get('code_aster') != '17.4.0':
        raise ValueError('Existing Code_Aster17.4 runtime required')
    mesh = LIRE_MAILLAGE(FORMAT='ASTER',UNITE=20)
    guard = check_import(mesh,expected)
    _save(root/'native_mesh_checks.json',guard)
    model = AFFE_MODELE(MAILLAGE=mesh,AFFE=_F(GROUP_MA='BODY',PHENOMENE='MECANIQUE',MODELISATION='3D'))
    material = DEFI_MATERIAU(ELAS=_F(E=config['material']['young_modulus_MPa'],NU=config['material']['poisson_ratio']))
    assigned = AFFE_MATERIAU(MAILLAGE=mesh,AFFE=_F(GROUP_MA='BODY',MATER=material))
    labels = {int(key):value for key,value in config['node_labels'].items()}
    forces = {}
    for row in expected['loads']:
        forces.setdefault(row['node_id'],{})[('FX','FY','FZ')[row['component']-1]] = row['force_N']
    load = AFFE_CHAR_MECA(MODELE=model,DDL_IMPO=_F(GROUP_NO='FIXED',DX=0.,DY=0.,DZ=0.),
        FORCE_NODALE=tuple(_F(NOEUD=labels[n],**components) for n,components in forces.items()))
    result = MECA_STATIQUE(MODELE=model,CHAM_MATER=assigned,EXCIT=_F(CHARGE=load),SOLVEUR=_F(METHODE='MUMPS'))
    result = CALC_CHAMP(reuse=result,RESULTAT=result,FORCE='REAC_NODA')
    indexes = list(result.getIndexes())
    if len(indexes) != 1:
        raise ValueError('Expected one native static order')
    order = indexes[0]
    tables = {}
    for field,components in (('DEPL',VECTOR_COMPONENTS),('REAC_NODA',VECTOR_COMPONENTS),('SIEF_ELGA',STRESS_COMPONENTS)):
        table = CREA_TABLE(RESU=_F(RESULTAT=result,NOM_CHAM=field,NUME_ORDRE=order,NOM_CMP=components,TOUT='OUI'))
        tables[field] = table.EXTR_TABLE().values()
        _save(root/(field.lower()+'.table.json'),tables[field])
    IMPR_RESU(FORMAT='MED',UNITE=80,RESU=_F(RESULTAT=result,NOM_CHAM=('DEPL','REAC_NODA','SIEF_ELGA'),NUME_ORDRE=order))
    _save(root/'worker_result.json',{'solver_status':'COMPLETED','converged':True,
        'versions':versions,'code_aster_runtime':runtime,'order':order,'available_orders':indexes,
        'access_parameters':result.getAccessParameters(),'native_mesh_checks':guard,'tables':tables,
        'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(), 'mail_sha256':config['mail_sha256']})
    FIN()
