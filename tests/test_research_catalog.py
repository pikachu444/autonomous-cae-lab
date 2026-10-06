"""Research summary stays bounded without dropping declared model selections."""
from copy import deepcopy

import pytest

from caelab.research_catalog import condition_catalog_summary, FULL_SELECTION_LIMIT


def catalog(size=209):
    return {'cad_revision': 'a' * 64, 'coordinate_system': 'global',
        'retained_mesh': {'mesh_revision': 'b' * 64},
        'selections': [{'id': f'S-{i}', 'label': f'Native selection {i}', 'bounds': [i, i+1]}
                       for i in range(size)]}


def declaration():
    return {'materials': [{'selection_id': 'S-1'}],
        'boundary_conditions': [{'selection_id': 'S-2'}],
        'loads': [{'selection_id': 'S-2'}],
        'contact': {'pairs': [{'surface_a': 'S-3', 'surface_b': 'S-4', 'master': 'surface_a'}]}}


def project(original, declared):
    return condition_catalog_summary(original, declared, 'c' * 64,
        'experiments/E-TEST_ONLY/analysis_conditions.json')


def test_all_material_boundary_load_and_contact_regions_retained_exactly():
    original, declared = catalog(), declaration()
    before = deepcopy((original, declared))
    shown, scope = project(original, declared)
    assert shown['selections'] == original['selections'][1:5]
    assert shown['retained_mesh'] == original['retained_mesh']
    assert scope == {'scope': 'DECLARATION_REFERENCED_SELECTIONS_ONLY',
        'source_catalog_revision': 'c' * 64,
        'source_record_ref': 'experiments/E-TEST_ONLY/analysis_conditions.json',
        'source_selection_count': 209, 'returned_selection_count': 4, 'omitted_selection_count': 205,
        'complete_catalog_available_in': 'CANONICAL_EXPERIMENT_INSPECTION_AND_CHILD_RECORD',
        'execution_catalog': False}
    shown['selections'][0]['bounds'][0] = 999
    assert (original, declared) == before


@pytest.mark.parametrize('size', [0, 1, FULL_SELECTION_LIMIT])
def test_existing_small_context_is_unchanged(size):
    original = catalog(size)
    shown, scope = project(original, declaration())
    assert shown == original and shown is not original and scope is None


@pytest.mark.parametrize('declared', [{}, {'metadata': {'label': 'S-1'}}])
def test_no_recognized_selection_contract_cannot_silently_omit_whole_catalog(declared):
    original = catalog()
    shown, scope = project(original, declared)
    assert shown == original and scope is None


@pytest.mark.parametrize('key', ['selection_id', 'surface_a', 'surface_b'])
@pytest.mark.parametrize('value', ['S-missing', None, ['S-1']])
def test_missing_or_malformed_frozen_reference_is_refused(key, value):
    with pytest.raises(ValueError, match='missing catalog selection'):
        project(catalog(), {'TEST_ONLY': [{key: value}]})


def test_duplicate_catalog_ids_are_not_silently_collapsed():
    original = catalog()
    original['selections'][-1]['id'] = original['selections'][0]['id']
    with pytest.raises(ValueError, match='duplicate selections'):
        project(original, declaration())
