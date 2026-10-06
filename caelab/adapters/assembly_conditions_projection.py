"""Join declared CAD selections to exact retained native physical groups.

This is adapter syntax, with no topology search, coordinate merge or input repair.
Source node IDs stay source IDs until the checked Code_Aster import binds them.
"""
from copy import deepcopy

from .fixture_assembly_native_import_worker import source_catalog


SOLVER_POLICY = {'load_parameters': [0.0, 0.25, 0.5, 0.75, 1.0],
                 'residual_relative': 1e-6, 'maximum_iterations': 50,
                 'contact_coefficient': 1000.0}


def compile_packet(catalog, declaration, mapping, *, solver_policy=None):
    from plugins.fixture_design.assembly_conditions import validate_declaration
    scope = validate_declaration(catalog, declaration)
    source = source_catalog(mapping)
    components = scope['active_components']
    if set(source['bodies']) != set(components):
        raise ValueError('Declared body scope differs from retained mesh')
    selected = {row['id']: row for row in catalog['selections']}
    faces = {}
    for group, row in source['groups'].items():
        if row['dim'] == 2:
            key = row['component_id'], row['catalog_face_id']
            if key in faces:
                raise ValueError('Ambiguous genuine native face-to-group mapping')
            faces[key] = group
    # Complete active catalog coverage is checked, not only chosen load faces.
    expected = {(row['component_id'], row['catalog_face_id']) for row in selected.values()
                if row['kind'] == 'native_assembly_face' and row['component_id'] in components}
    if set(faces) != expected:
        raise ValueError('Retained physical groups do not cover the exact active CAD faces')

    def face(selection):
        row = selected[selection]
        group = faces[row['component_id'], row['catalog_face_id']]
        return group, source['groups'][group]

    materials = []
    for material in declaration['materials']:
        component = selected[material['selection_id']]['component_id']
        materials.append({'component_id': component, 'volume_group': source['bodies'][component],
            'young_modulus_MPa': material['young_modulus_MPa'], 'poisson_ratio': material['poisson_ratio']})
    boundaries, loads = [], []
    for items, destination, label in ((declaration['boundary_conditions'], boundaries, 'BC'),
                                      (declaration['loads'], loads, 'LD')):
        for number, item in enumerate(items, 1):
            group, row = face(item['selection_id'])
            projected = {'id': item['id'], 'node_group': f'{label}{number:03d}',
                'face_group': group, 'source_node_ids': sorted(row['node_ids'])}
            if selected[item['selection_id']]['kind'] == 'assembly_face_interior_nodes':
                others = {nid for name, other in source['groups'].items() if name != group and other['dim'] == 2
                          and other['component_id'] == row['component_id'] for nid in other['node_ids']}
                projected['source_node_ids'] = sorted(set(row['node_ids']) - others)
                projected['node_scope'] = 'FACE_INTERIOR_EXCLUDING_OTHER_FACE_BOUNDARIES'
                if not projected['source_node_ids']:
                    raise ValueError('Selected retained face has no native interior nodes')
            if label == 'BC':
                projected['components'] = {key.replace('U', 'D', 1): value for key, value in item['components'].items()}
            else:
                projected['components_N'] = deepcopy(item['components'])
            destination.append(projected)
    ties, contacts, pairs = [], [], []
    for number, pair in enumerate(declaration['contact'].get('pairs', []), 1):
        master_side = pair['master']
        slave_side = 'b' if master_side == 'a' else 'a'
        master, master_data = face(pair['selection_' + master_side])
        slave, slave_data = face(pair['selection_' + slave_side])
        record = {'id': f'CP{number:03d}', 'master_face_group': master, 'slave_face_group': slave}
        law = pair.get('law', declaration['contact']['mode'])
        if law == 'bonded':
            record['master_volume_group'] = source['bodies'][master_data['component_id']]
            record['distance_max_mm'] = pair['distance_max_mm']
            ties.append(record)
        elif law == 'frictionless':
            if 'initial_state' in declaration['contact']:
                record['initial_state'] = declaration['contact']['initial_state']
            contacts.append(record)
        else:
            raise ValueError('Unsupported native interface law')
        pairs.append({'id': record['id'], 'declaration': deepcopy(pair), 'native_projection': deepcopy(record),
                      'master_component': master_data['component_id'], 'slave_component': slave_data['component_id']})
    if declaration['contact'].get('master_union_same_slave') is True:
        grouped = {}
        for contact in contacts:
            grouped.setdefault(contact['slave_face_group'], []).append(contact)
        merged = []
        for members in grouped.values():
            if len(members) == 1:
                merged.append(members[0])
            else:
                merged.append({'id': members[0]['id'],
                    'master_face_groups': [item['master_face_group'] for item in members],
                    'slave_face_group': members[0]['slave_face_group'],
                    **({'initial_state': members[0]['initial_state']} if 'initial_state' in members[0] else {}),
                    'source_pair_ids': [item['id'] for item in members]})
        contacts = merged
    packet = {'schema_version': '1.0', 'components': components, 'materials': materials,
              'boundary_conditions': boundaries, 'loads': loads, 'ties': ties, 'contacts': contacts,
              'solver_policy': deepcopy(solver_policy or SOLVER_POLICY)}
    receipt = {'scope': 'EXACT_RETAINED_CAD_FACE_TO_NATIVE_PHYSICAL_GROUP',
               'cad_revision': catalog['cad_revision'], 'mesh_revision': catalog['retained_mesh']['mesh_revision'],
               'pair_projections': pairs, 'force_distribution': 'EQUAL_FORCE_PER_DECLARED_NATIVE_SURFACE_NODE',
               'master_union_same_slave': declaration['contact'].get('master_union_same_slave', False),
               'axis': 'DIMENSIONLESS_STATIC_LOAD_PARAMETER_NOT_PHYSICAL_TIME',
               'excitation_kind': 'PRESCRIBED_DISPLACEMENT' if not loads else 'FORCE_OR_MIXED',
               'engineering': 'UNKNOWN', 'decision': 'NOT_RELEASED'}
    return packet, receipt
