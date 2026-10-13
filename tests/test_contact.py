"""Pure contact contracts; native/solver execution is not simulated as acceptance."""
from copy import deepcopy
import pytest
from caelab.contact import default_contact, law_errors, separate_meshes, surface_union


def body(name):
    return {'body_id': name,
        'nodes': [{'node_id': i, 'position_mm': [i, 0, 0]} for i in range(1, 11)],
        'elements': [{'element_id': 73, 'type': 'C3D10', 'native_node_ids': list(range(1, 11))}]}


def test_coincident_bodies_and_local_id_collisions_keep_independent_dofs_and_inverse_map():
    data = separate_meshes([body('Pad'), body('Base')])
    assert len(data['nodes']) == 20 and len(data['elements']) == 2
    assert data['nodes'][0]['position_mm'] == data['nodes'][10]['position_mm']
    assert data['body_maps']['Pad']['nodes'][1] != data['body_maps']['Base']['nodes'][1]
    assert {(row['body_id'], row['native_element_id']) for row in data['elements']} == {('Pad', 73), ('Base', 73)}
    assert set(data['elements'][0]['node_ids']).isdisjoint(data['elements'][1]['node_ids'])
    faces = [{'face': 'Face1', 'element_faces': [(73, 1)]},
             {'face': 'Face2', 'element_faces': [(73, 2), (73, 1)]}]
    a = surface_union('Pad', faces, data['body_maps'])
    b = surface_union('Base', faces, data['body_maps'])
    assert a['element_faces'] == [[1, 1], [1, 2]]
    assert b['element_faces'] == [[2, 1], [2, 2]]
    with pytest.raises(ValueError, match='no mapped'):
        surface_union('Pad', faces + [{'face': 'Face3', 'element_faces': []}], data['body_maps'])
    with pytest.raises(ValueError, match='outside'):
        surface_union('Pad', [{'face': 'Face1', 'element_faces': [(1, 1)]}], data['body_maps'])


def test_laws_preserve_partial_drafts_and_never_translate_gap_or_flip_into_metadata_success():
    draft = default_contact()
    draft.update(normal_law='linear', tangential_law='frictionless',
                 normal_stiffness_MPa_per_mm='1e')
    before = deepcopy(draft)
    assert any(row['path'] == 'normal_stiffness_MPa_per_mm' for row in law_errors(draft))
    assert draft == before
    draft['normal_stiffness_MPa_per_mm'] = '2e5'
    assert not law_errors(draft)
    draft.update(tangential_law='coulomb', friction_coefficient='0', stick_stiffness_MPa_per_mm='1.2e4')
    assert not law_errors(draft)
    for patch, field in [({'nominal_gap_mm': '0.1'}, 'nominal_gap_mm'),
                         ({'normal': 'reversed'}, 'normal'),
                         ({'adjustment_mm': '0.1'}, 'adjustment_mm'),
                         ({'activation': 'interval'}, 'step')]:
        assert any(row['path'] == field for row in law_errors(dict(draft, **patch)))
