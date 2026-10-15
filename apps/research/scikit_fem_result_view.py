"""Feed exact SI captures into the existing PDE/Simulation result selector."""
from copy import deepcopy


def fields(result):
    backend = result.get('backend', '')
    if backend not in ('pde.scikit_fem.dimensioned', 'thermal.scikit_fem.rectangle',
                       'structural.scikit_fem.thermoelastic_rectangle'):
        return []
    entries = []
    for name, value in result.get('responses', {}).items():
        if value.get('kind') != 'field' or value.get('association') not in ('POINTS', 'CELLS'):
            continue
        field = {'node_ids': deepcopy(value['node_ids'] if value['association'] == 'POINTS' else value['cell_ids']),
            'coordinates': deepcopy(value['coordinates']), 'values': deepcopy(value['value']),
            'components': deepcopy(value.get('components', ['scalar'])), 'field_unit': value['unit'],
            'coordinates_unit': value['coordinate_units'], 'association': value['association']}
        post = next((p for p in result.get('post_inputs', []) if p.get('response') == name), {})
        entries.append({'name': name, 'study_index': post.get('study_index'), 'field': field, 'time': value['time'], 'time_unit': value['time_units'],
            'time_origin': value['time_origin'], 'source': {k:deepcopy(value.get(k)) for k in
            ('capture_sha256','mesh_sha256','quantity','measure','frame','basis','snapshot_kind')}, 'physical_capture': True})
    return entries
