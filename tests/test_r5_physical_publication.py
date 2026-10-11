"""Controlled captured SI arrays through the real VTU/PVD publisher; no solve."""
from copy import deepcopy
import xml.etree.ElementTree as ET

import pytest

from caelab.physical_fields import write_field
from plugins.thermoelastic.reference import mesh_digest, seal_field


def captured(association):
    # Deliberately unsorted, noncontiguous native IDs expose accidental reordering.
    ids = [19, 7, 31, 2]
    xyz = [[0., 0.], [.02, 0.], [0., .01], [.02, .01]]
    cells = [[19, 7, 2], [19, 2, 31]]
    common = {'kind': 'field', 'association': association, 'reduction': 'none',
              'frame': 'global_cartesian', 'coordinate_units': 'm', 'coordinate_frame': 'global_cartesian',
              'node_ids': ids, 'cell_node_ids': cells, 'mesh_sha256': mesh_digest(xyz, cells),
              'time': .375, 'time_units': 's', 'time_origin': 'experiment_start'}
    if association == 'POINTS':
        response = {**common, 'component': 'vector', 'components': ['x', 'y'],
                    'coordinates': xyz, 'location': 'node', 'unit': 'm', 'quantity': 'displacement',
                    'measure': 'infinitesimal_displacement',
                    'value': [[.001, -.002], [.003, -.004], [.005, -.006], [.007, -.008]]}
    else:
        response = {**common, 'component': 'tensor_components', 'components': ['xx', 'yy', 'xy'],
                    'coordinates': [[.04 / 3, .01 / 3], [.02 / 3, .02 / 3]],
                    'mesh_coordinates': xyz, 'cell_ids': [44, 12], 'location': 'cell',
                    'unit': 'Pa', 'quantity': 'stress', 'measure': 'infinitesimal_Cauchy',
                    'value': [[120., -80., 3.], [-140., 65., -2.]]}
    return seal_field(response)


def arrays(parent):
    return {row.attrib['Name']: (row.attrib, [float(value) for value in row.text.split()])
            for row in parent.findall('DataArray')}


@pytest.mark.parametrize('association,name', [('POINTS', 'displacement'), ('CELLS', 'stress')])
def test_captured_components_publish_exact_association_ids_connectivity_and_physical_clock(tmp_path, association, name):
    response = captured(association)
    original = deepcopy(response)
    published = write_field(name, response, tmp_path / name)
    assert response == original
    assert published['response'] == name and published['path'].name == 'field.pvd'
    dataset = ET.parse(published['path']).find('./Collection/DataSet')
    assert float(dataset.attrib['timestep']) == .375
    piece = ET.parse(published['path'].parent / dataset.attrib['file']).find('./UnstructuredGrid/Piece')
    assert piece.attrib == {'NumberOfPoints': '4', 'NumberOfCells': '2'}
    point, cell = arrays(piece.find('PointData')), arrays(piece.find('CellData'))
    assert point['NativeNodeId'][1] == [19, 7, 31, 2]
    topology = arrays(piece.find('Cells'))
    assert topology['connectivity'][1] == [0, 1, 3, 0, 3, 2]
    assert topology['offsets'][1] == [3, 6] and topology['types'][1] == [5, 5]
    points = arrays(piece.find('Points'))['Points']
    assert points[0]['NumberOfComponents'] == '3'
    assert points[1] == [0., 0., 0., .02, 0., 0., 0., .01, 0., .02, .01, 0.]
    selected = point if association == 'POINTS' else cell
    other = cell if association == 'POINTS' else point
    for column, component in enumerate(response['components']):
        array_name = name + '_' + component
        assert selected[array_name][1] == [row[column] for row in response['value']]
        assert selected[array_name][0]['NumberOfComponents'] == '1'
        assert array_name not in other
    if association == 'CELLS':
        assert cell['NativeCellId'][1] == [44, 12]
    metadata = published['native_metadata']
    assert metadata['coordinate_units'] == 'm' and metadata['coordinate_frame'] == 'global_cartesian'
    assert metadata['time'] == {'unit': 's', 'semantics': 'experiment_start', 'values': [.375]}
    descriptors = {row['name']: row for row in metadata['arrays']}
    for component in response['components']:
        descriptor = descriptors[name + '_' + component]
        assert descriptor == {'name': name + '_' + component, 'association': association,
            'components': 1, 'units': response['unit'], 'frame': response['frame'],
            'measure': response['measure'], 'quantity': response['quantity']}


@pytest.mark.parametrize('association', ['POINTS', 'CELLS'])
def test_changed_capture_is_rejected_before_publication(tmp_path, association):
    response = captured(association)
    response['value'][0][0] += 1.
    output = tmp_path / 'changed'
    with pytest.raises(ValueError, match='differs from its captured native values'):
        write_field('changed', response, output)
    assert not output.exists()


@pytest.mark.parametrize('defect', ['components', 'cell_ids', 'values', 'connectivity'])
def test_explicit_cell_capture_structure_is_not_repaired(tmp_path, defect):
    response = captured('CELLS')
    if defect == 'components':
        response['components'] = ['xx', 'xx', 'xy']
    elif defect == 'cell_ids':
        response['cell_ids'] = [44, 44]
    elif defect == 'values':
        response['value'].pop()
    else:
        response['cell_node_ids'][0][0] = 999
    response = seal_field(response)
    output = tmp_path / defect
    with pytest.raises(ValueError):
        write_field('invalid', response, output)
    assert not output.exists()
