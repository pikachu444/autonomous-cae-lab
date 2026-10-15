"""Small independent input example, NOT a native CAD capture or a solver result.

python -m examples.contact.recover1_periodic_cube /absolute/new/output
Creates a C3D10 cube through the existing contact compiler. Does not create a
fake FCStd/snapshot, start a solver, qualify Windows, or replace user face input.
"""
from copy import deepcopy
from itertools import combinations
import json
from pathlib import Path
import sys
from caelab.contact import separate_meshes, surface_union
from caelab.contact_deck import FACES, UNITS, render
from apps.desktop_pre.freeze_analysis import CCX_FROM_NATIVE_TET10


def model():
    corners = [(0,0,0), (1,0,0), (1,1,0), (0,1,0), (0,0,1), (1,0,1), (1,1,1), (0,1,1)]
    tets = [(0,1,2,6), (0,2,3,6), (0,3,7,6), (0,7,4,6), (0,4,5,6), (0,5,1,6)]
    xyz = {i+1: list(v) for i, v in enumerate(corners)}
    mids, elements = {}, []
    for eid, tet in enumerate(tets, 1):
        ids = [n+1 for n in tet]
        for i,j in ((0,1),(1,2),(2,0),(0,3),(1,3),(2,3)):
            edge = tuple(sorted((ids[i], ids[j])))
            if edge not in mids:
                mids[edge] = len(xyz)+1
                xyz[mids[edge]] = [(xyz[edge[0]][k]+xyz[edge[1]][k])/2 for k in range(3)]
            ids.append(mids[edge])
        native = [None]*10
        for ccx_slot, native_slot in enumerate(CCX_FROM_NATIVE_TET10):
            native[native_slot] = ids[ccx_slot]
        elements.append({'element_id': eid, 'type': 'C3D10', 'native_node_ids': native})
    value = separate_meshes([{'body_id': 'Cube',
        'nodes': [{'node_id': n, 'position_mm': point} for n, point in xyz.items()], 'elements': elements}], minimum_bodies=1)
    for row in value['nodes']:
        row['native_position_mm'] = list(row['position_mm'])
    for row in value['elements']:
        row['type'] = 'C3D10'
    mapping = value['body_maps']['Cube']['nodes']
    boundaries = [{'node_id': mapping[n], 'component': d, 'value_mm': 0.}
        for n, ds in ((1,(1,2,3)), (4,(1,3)), (5,(1,))) for d in ds]
    center = next(n for n, position in xyz.items() if position == [.5,.5,.5])
    load = {'node_id': mapping[center], 'component': 3, 'force_N': 1.}
    value.update(kind='freecad-contact-mesh', schema_version='1', units=dict(UNITS),
        analysis_scope='single_solid_static', contacts=[],
        materials=[{'body_id': 'Cube', 'object_id': 'Material', 'law': 'isotropic_linear_elastic',
                    'young_modulus_MPa': 1000., 'poisson_ratio': .3}],
        boundary_dofs=boundaries, loads=[load], conditions=[],
        step={'initial': 1., 'period': 1., 'minimum': 1e-6, 'maximum': 1., 'increments': 20,
              'geometry': 'linear', 'automatic': True, 'matrix_solver': 'default', 'controls': None})
    # Resolve the example planes by their full six-node element faces, including
    # midsides. The product native path resolves selected CAD faces via MeshSetsGetter.
    nodes = {r['node_id']: r['position_mm'] for r in value['nodes']}
    surfaces = []
    for plane in (0,1):
        rows = [[e['native_element_id'], f] for e in value['elements'] for f, slots in FACES.items()
                if all(nodes[e['node_ids'][slot]][0] == plane for slot in slots)]
        surfaces.append(surface_union('Cube', [{'face': 'Face'+str(plane+1), 'element_faces': rows}], value['body_maps']))
    value['periodic_constraints'] = [{'id': 'Pexample',
        'draft': {'label': 'X 방향 주기 경계', 'a_region_id': 'Rleft', 'b_region_id': 'Rright',
                  'transform': {'kind': 'translation', 'translation_mm': [1,0,0]},
                  'tolerance_mm': 1e-8, 'dofs': [1,2,3]}, 'a': surfaces[0], 'b': surfaces[1]}]
    return value


def main(folder):
    folder = Path(folder).absolute()
    folder.mkdir(parents=True, exist_ok=False)
    value = model()
    deck = render(value)
    (folder/'periodic-cube.inp').write_text(deck, encoding='ascii')
    (folder/'periodic-cube.json').write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    (folder/'STATUS.txt').write_text('INPUT_ONLY; synthetic independent mesh; native solver NOT_RUN; no FCStd or owner receipt fabricated.\n', encoding='utf-8')
    print(folder)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python -m examples.contact.recover1_periodic_cube NEW_OUTPUT_DIRECTORY')
    main(sys.argv[1])
