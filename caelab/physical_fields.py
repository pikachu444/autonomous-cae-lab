"""Write captured SI P1 stage fields using the existing native PDE VTU writer."""
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET


def write_field(name, response, output):
    from .pde_results import _write_vtu, _field_arrays
    from plugins.thermoelastic.reference import digest
    required = ('unit', 'quantity', 'frame', 'measure', 'coordinate_units', 'coordinate_frame', 'time_units', 'time_origin')
    if any(not isinstance(response.get(key), str) or not response[key] for key in required):
        raise ValueError('Physical field requires exact units, quantity, frame, measure and actual clock')
    if response.get('capture_sha256') != digest({k: v for k, v in response.items() if k != 'capture_sha256'}):
        raise ValueError('Physical field differs from its captured native values')
    component = response['component']
    if component in ('vector', 'tensor_components'):
        component = response.get('components')
        if (not isinstance(component, list) or not component or len(component) != len(set(component))
                or any(not isinstance(c, str) or not c for c in component)):
            raise ValueError('Captured vector/tensor field needs its exact ordered component names')
    components = [name] if component == 'scalar' else [name + '_' + c for c in component] if isinstance(component, list) else None
    if not components:
        raise ValueError('Captured physical field has no explicit scalar/component list')
    association = response.get('association')
    if association not in ('POINTS', 'CELLS'):
        raise ValueError('Captured physical field supports native P1 POINTS or DG0 CELLS')
    spatial_metadata = {key: response[key] for key in ('basis', 'mesh_sha256', 'snapshot_kind') if key in response}
    if 'basis' in spatial_metadata and spatial_metadata['basis'] != {'POINTS': 'P1', 'CELLS': 'DG0'}[association]:
        raise ValueError('Captured field basis differs from its native association')
    if 'mesh_sha256' in spatial_metadata and (not isinstance(spatial_metadata['mesh_sha256'], str)
            or len(spatial_metadata['mesh_sha256']) != 64
            or any(c not in '0123456789abcdef' for c in spatial_metadata['mesh_sha256'])):
        raise ValueError('Captured mesh identity requires a SHA256 digest')
    if 'snapshot_kind' in spatial_metadata and spatial_metadata['snapshot_kind'] not in ('steady', 'physical_snapshot'):
        raise ValueError('Captured field requires its declared snapshot kind')
    field = {'node_ids': deepcopy(response['node_ids']),
             'coordinates': deepcopy(response['coordinates'] if association == 'POINTS' else response['mesh_coordinates']),
             'values': deepcopy(response['value']), 'components': components,
             'association': association,
             'cell_node_ids': deepcopy(response['cell_node_ids']),
             'coordinates_unit': response['coordinate_units'], 'field_unit': response['unit']}
    if association == 'CELLS':
        field['cell_ids'] = deepcopy(response['cell_ids'])
        if len(field['cell_ids']) != len(set(field['cell_ids'])):
            raise ValueError('Captured cell identities must be distinct')
    _field_arrays(field)
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=False)
    path = folder / 'field.vtu'
    metadata = _write_vtu({'field': field}, path)
    metadata.update(spatial_metadata)
    metadata.update(coordinate_frame=response['coordinate_frame'],
        time={'unit': response['time_units'], 'semantics': response['time_origin'], 'values': [response['time']]})
    for row in metadata['arrays']:
        if row['name'] in components:
            row.update(frame=response['frame'], measure=response['measure'], quantity=response['quantity'])
    # A single recorded physical instant is still a real time selection. PVD
    # carries that instant; it is not relabelled as a static or dimensionless run.
    tree = ET.Element('VTKFile', type='Collection', version='0.1', byte_order='LittleEndian')
    ET.SubElement(ET.SubElement(tree, 'Collection'), 'DataSet', timestep=format(response['time'], '.17g'), part='0', file=path.name)
    clock = folder / 'field.pvd'
    ET.ElementTree(tree).write(clock, encoding='utf-8', xml_declaration=True)
    return {'path': clock, 'native_metadata': metadata, 'response': name}
