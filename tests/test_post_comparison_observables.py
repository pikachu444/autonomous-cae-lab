"""Saved observable identities; pure calculations, no native runtime required."""
from copy import deepcopy
import numpy as np
import pytest
from caelab import post_comparison as c
from test_post_comparison_physics import recipe


def projected(kind, selection, *, difference='selected_difference', role='A_original'):
    r = recipe()
    layout = {'kind': kind, 'components': ['x', 'y', 'z']} if kind == 'vector' else {
        'kind': 'tensor', 'components': ['xx','yy','zz','xy','yz','xz'],
        'shear': 'tensor', 'indices': 'same_cartesian_basis'}
    for side in ('a', 'b'):
        r[side]['layout'] = deepcopy(layout)
    r.update(selection=selection, difference=difference)
    metadata = c.output_declarations(r)
    row = next(row for row in metadata['arrays'] if row['name'] == role)
    return dict(recipe()['a'], **{key: deepcopy(value) for key, value in row.items() if key != 'name'},
                array=role)


def again(a, b):
    r = recipe()
    r.update(a=deepcopy(a), b=deepcopy(b))
    return r


@pytest.mark.parametrize('kind,left,right', [
    ('vector','x','y'), ('tensor','xx','yy'), ('vector','x','magnitude'),
    ('tensor','xy','yx')])
def test_equal_numbers_from_different_saved_components_are_not_zero_difference(kind, left, right):
    r = again(projected(kind,left), projected(kind,right))
    with pytest.raises(ValueError, match='서로 다른 관측량'):
        c.validate(r, [], [])
    with pytest.raises(ValueError, match='서로 다른 관측량'):
        c.compare(np.array([[1.]]), np.array([[1.]]), r, [True])


def test_same_saved_component_converts_units_and_keeps_identity_through_recomparison():
    a = projected('vector','x'); b = deepcopy(a); b['units'] = 'Pa'
    r = again(a,b); c.validate(r, [], [])
    av = c.transform_values([[2.]],a,r['target'],c.IDENTITY)
    bv = c.transform_values([[2e6]],b,r['target'],c.IDENTITY)
    assert c.compare(av,bv,r,[True])['delta'].tolist() == [0.]
    rows = c.output_declarations(r)['arrays']
    assert rows[0]['observable'] == a['observable']
    assert rows[1]['observable'] == a['observable']
    assert rows[2]['observable'] == {'version':1,'operation':'difference','operand':a['observable']}
    r['b']['frame']='local'; r['alignment']['response_declared']=True
    r['b']['layout']['scalar_semantics']='invariant'  # Cannot override the retained component meaning.
    with pytest.raises(ValueError, match='원 벡터'):
        c.validate(r, [], [])


def test_norm_difference_is_not_difference_of_norms_and_ignores_display_component():
    magnitude = projected('vector','magnitude')
    delta_norms = projected('vector','magnitude',role='B_minus_A')
    norm_delta_x = projected('vector','x',difference='norm_of_difference',role='B_minus_A')
    norm_delta_y = projected('vector','y',difference='norm_of_difference',role='B_minus_A')
    assert norm_delta_x['observable'] == norm_delta_y['observable']
    c.validate(again(norm_delta_x,norm_delta_y), [], [])
    for other in (magnitude, delta_norms):
        with pytest.raises(ValueError, match='서로 다른 관측량'):
            c.validate(again(norm_delta_x,other), [], [])
    nested = c.output_declarations(again(norm_delta_x,norm_delta_y))['arrays'][2]['observable']
    assert nested['operand'] == norm_delta_x['observable']


def test_unknown_legacy_is_not_inferred_from_array_name_or_matching_unknown():
    a = projected('vector','x')
    legacy = {'derivation':'comparison_v2','arrays':[dict(a,name='A_original')]}
    for row in legacy['arrays']:
        row.pop('observable')
    original = deepcopy(legacy)
    read_copy = c.retained_declarations(legacy)
    assert legacy == original
    unknown = dict(a, observable=read_copy['arrays'][0]['observable'])
    for other in (a,unknown):
        with pytest.raises(ValueError, match='미확인'):
            c.validate(again(unknown,other), [], [])
    # Explicit user declaration is separate from legacy retained bytes.
    unknown['observable'] = c.observable_value('vector','x')
    c.validate(again(a,unknown), [], [])


def test_tensor_norm_is_frobenius_and_not_vector_magnitude():
    a = projected('tensor','magnitude'); b = projected('vector','magnitude')
    assert a['observable']['norm']=='frobenius' and b['observable']['norm']=='euclidean'
    with pytest.raises(ValueError, match='서로 다른 관측량'):
        c.validate(again(a,b), [], [])


def test_legacy_path_mask_is_not_invented_from_original_comparison_array_name():
    row=projected('vector','y',role='B_at_A')
    row.pop('observable')
    row.pop('spatial_mask')
    row.pop('validity_policy')
    row['name']=row.pop('array')
    row['validity_masks']=['vtkValidPointMask']
    legacy={'derivation':'comparison_v2','arrays':[row]}
    original=deepcopy(legacy)
    restored=c.retained_declarations(legacy)
    assert restored['arrays'][0]['spatial_mask']=='vtkValidPointMask'
    assert restored['arrays'][0]['observable']==c.UNKNOWN_OBSERVABLE
    assert legacy==original
