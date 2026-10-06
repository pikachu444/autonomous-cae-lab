"""Independent result-axis and shared native completeness source controls."""
from copy import deepcopy
import pytest

from test_fixture_assembly_affine_field import synthetic
from caelab.adapters.fixture_assembly_mechanics_fields import parse_fields, numerical_summary
from plugins.fixture_design.assembly_field_reference import canonical_settings


def fake_observation():
    # Artificial tables explicitly retain synthetic labels. No native success.
    values = synthetic()
    mapping, catalog, quality, raw = values.mapping, values.catalog, values.quality, values.raw
    raw = deepcopy(raw)
    raw['available_orders'] = [0,1]
    raw['access_parameters'] = {'NUME_ORDRE':[0,1], 'INST':[0.,1.]}
    raw['load_parameter'] = 1.
    packet = {'components': canonical_settings()['components'], 'solver_policy': {'load_parameters':[0.,1.]}}
    return mapping, catalog, quality, raw, packet


def test_mechanics_joins_complete_actual_final_order_without_affine_boundary_assumption():
    mapping,catalog,quality,raw,packet = fake_observation()
    raw.pop('boundary')
    fields = parse_fields(raw,mapping,catalog,quality,packet)
    assert fields['load_parameter'] == 1.
    assert fields['scope'] == 'COMPLETE_NATIVE_ASSEMBLY_MECHANICS_FIELDS'
    assert fields['axis_semantics'] == 'DIMENSIONLESS_STATIC_LOAD_PARAMETER_NOT_PHYSICAL_TIME'
    assert sum(len(body['nodes']) for body in fields['bodies'].values()) == catalog['node_count']


def test_native_initial_zero_may_be_absent_without_constructing_an_initial_field():
    mapping,catalog,quality,raw,packet = fake_observation()
    raw['available_orders'] = [1]
    raw['access_parameters'] = {'NUME_ORDRE':[1], 'INST':[1.]}
    fields = parse_fields(raw,mapping,catalog,quality,packet)
    assert fields['actual_load_parameters'] == [1.]
    assert fields['initial_state'] == 'NOT_STORED'


def test_omitting_a_requested_nonzero_increment_is_rejected():
    mapping,catalog,quality,raw,packet = fake_observation()
    packet['solver_policy']['load_parameters'] = [0.,.5,1.]
    raw['available_orders'] = [1]
    raw['access_parameters'] = {'NUME_ORDRE':[1], 'INST':[1.]}
    with pytest.raises(ValueError): parse_fields(raw,mapping,catalog,quality,packet)


@pytest.mark.parametrize('change', ['wrong_order','missing_axis','time_alias','unrequested_axis','missing_node'])
def test_actual_axis_or_full_field_mismatch_is_rejected(change):
    mapping,catalog,quality,raw,packet = fake_observation()
    if change == 'wrong_order': raw['order'] = 3
    if change == 'missing_axis': raw['access_parameters']['INST'] = [1.]
    if change == 'time_alias': raw['load_parameter'] = 0.
    if change == 'unrequested_axis': packet['solver_policy']['load_parameters'] = [0.,.5,1.]
    if change == 'missing_node':
        for column in raw['tables']['DEPL'].values(): column.pop()
    with pytest.raises(ValueError): parse_fields(raw,mapping,catalog,quality,packet)


def test_balance_observes_signed_force_and_whole_vector_not_loaded_component():
    fields = {'bodies': {'a': {'nodes': [
        {'reaction_n':[0,0,16.], 'displacement_mm':[3.,4.,0.]},
        {'reaction_n':[0,0,0.], 'displacement_mm':[0.,0.,1.]}]}}}
    packet = {'loads':[{'components_N':{'FX':0.,'FY':0.,'FZ':-16.}}]}
    verdict = numerical_summary(fields,packet)
    assert verdict['metrics']['max_displacement']['value'] == 5.
    assert verdict['checks'][0]['status'] == 'PASS'
    assert verdict['metrics']['peak_stress']['valid'] is False
    fields['bodies']['a']['nodes'][0]['reaction_n'][2] = 0.
    assert numerical_summary(fields,packet)['checks'][0]['status'] == 'FAIL'
