"""Shared read-only field routing; no new executable adapter admission."""
from types import SimpleNamespace

import pytest

from caelab.engine import Lab
from caelab import response_field, response_comparison
from caelab.adapters.assembly_response_fields import AssemblyResponseFieldsAdapter


def test_default_reader_is_separate_from_solver_admission(tmp_path):
    lab = Lab(tmp_path / 'store', doe_adapters={}, optimization_adapters={},
              pde_adapters={}, model_analysis_adapters={})
    backend = AssemblyResponseFieldsAdapter.backend
    assert backend not in lab.analysis_adapters
    reader = lab.response_field_adapters[backend]
    assert type(reader) is AssemblyResponseFieldsAdapter
    assert not hasattr(reader, 'solve') and not hasattr(reader, 'conditions_preflight')
    assert reader.field_response_resources({'provenance': {'adapter': backend, 'adapter_version': '1'}}) == {
        'field': {'path': 'simulation/admitted-fields.json', 'maximum_bytes': 536870912},
        'mapping': {'path': 'simulation/mesh-reuse/mapping.json', 'maximum_bytes': 134217728}}


def test_default_pde_readers_do_not_admit_a_solver_or_change_native_node_ids(tmp_path):
    from caelab.adapters.pde_response_fields import PDEResponseFieldsAdapter, SUPPORTED_BACKENDS
    lab = Lab(tmp_path / 'store', adapters={}, analysis_adapters={}, pde_adapters={},
              model_analysis_adapters={}, doe_adapters={}, optimization_adapters={})
    assert len(SUPPORTED_BACKENDS) == 5
    for backend in SUPPORTED_BACKENDS:
        reader = lab.response_field_adapters[backend]
        assert type(reader) is PDEResponseFieldsAdapter
        assert not hasattr(reader, 'solve')
        assert backend not in lab.pde_adapters and backend not in lab.analysis_adapters


def test_selected_field_reader_gets_verified_headers_before_additional_native_bytes(monkeypatch):
    calls = []
    selection = {'kind': 'pde_nodal', 'node_id': 0}
    result = {'provenance': {'adapter': 'TEST_ONLY'}}

    def additional(r, s, resources):
        assert r is result and s is selection
        assert resources == {'header': ({'TEST_ONLY': 'header.json'}, {'TEST_ONLY': 'manifest'})}
        calls.append(('selection', 0))
        return {'field': {'path': 'field.json', 'maximum_bytes': 32}}

    reader = SimpleNamespace(field_response_resources=lambda r: {
        'header': {'path': 'header.json', 'maximum_bytes': 16}}, field_selection_resources=additional)
    lab = SimpleNamespace(analysis_adapters={}, response_field_adapters={'TEST_ONLY': reader})

    def read(l, r, path, *, maximum_bytes):
        assert l is lab and r is result
        calls.append((path, maximum_bytes))
        return {'TEST_ONLY': path}, {'TEST_ONLY': 'manifest'}

    monkeypatch.setattr(response_field, '_read_native', read)
    actual, resources = response_field._adapter_resources(lab, result, selection)
    assert actual is reader and set(resources) == {'header', 'field'}
    assert calls == [('header.json', 16), ('selection', 0), ('field.json', 32)]


@pytest.mark.parametrize('additional', [{}, {'header': {'path': 'overwrite.json', 'maximum_bytes': 1}},
    {'field': {'path': 'field.json', 'maximum_bytes': 1, 'extra': True}}])
def test_selected_resource_contract_refuses_header_replacement_before_field_read(monkeypatch, additional):
    reader = SimpleNamespace(field_response_resources=lambda r: {
        'header': {'path': 'header.json', 'maximum_bytes': 16}},
        field_selection_resources=lambda r, s, resources: additional)
    lab = SimpleNamespace(analysis_adapters={}, response_field_adapters={'TEST_ONLY': reader})
    calls = []
    def read(l, r, path, *, maximum_bytes):
        calls.append(path)
        return {}, {}
    monkeypatch.setattr(response_field, '_read_native', read)
    with pytest.raises(ValueError):
        response_field._adapter_resources(lab, {'provenance': {'adapter': 'TEST_ONLY'}}, {'TEST_ONLY': True})
    assert calls == ['header.json']


def test_readonly_research_metric_semantics_do_not_require_solver_admission(tmp_path, monkeypatch):
    lab = Lab(tmp_path / 'store', doe_adapters={}, optimization_adapters={},
              pde_adapters={}, model_analysis_adapters={})
    backend = AssemblyResponseFieldsAdapter.backend
    assert backend not in lab.analysis_adapters
    result = {'provenance': {'adapter': backend, 'adapter_version': '1'},
        'metrics': {'max_displacement': {'value': .125, 'unit': 'mm', 'valid': True}}}
    import caelab.research_context as context
    monkeypatch.setattr(context, 'comparison_context', lambda *args: None)
    monkeypatch.setattr(context, 'analysis_conditions_context', lambda *args: None)
    semantics = lab._research_result_context(result)['metric_semantics']['max_displacement']
    assert semantics['component'] == 'VECTOR_MAGNITUDE'
    assert semantics['coverage'] == 'ALL_ORIGINAL_MESH_NODES'
    assert semantics['selection_id'] == 'ALL_ORIGINAL_ACTIVE_BODY_NODES'
    assert semantics['unit'] == 'mm'
    assert result['metrics']['max_displacement']['value'] == .125
    assert backend not in lab.analysis_adapters


@pytest.mark.parametrize('changed', [
    {'provenance': {'adapter': 'fixture.calculix', 'adapter_version': '1'}},
    {'provenance': {'adapter': AssemblyResponseFieldsAdapter.backend, 'adapter_version': 'UNKNOWN'}},
    {'metrics': {}}, {'metrics': {'max_displacement': {'unit': 'mm', 'valid': False}}},
    {'metrics': {'max_displacement': {'unit': 'm', 'valid': True}}},
])
def test_unavailable_or_different_family_has_no_inferred_assembly_metric_semantics(changed):
    result = {'provenance': {'adapter': AssemblyResponseFieldsAdapter.backend, 'adapter_version': '1'},
        'metrics': {'max_displacement': {'value': .125, 'unit': 'mm', 'valid': True}}}
    assert AssemblyResponseFieldsAdapter.research_metric_semantics(result | changed) is None


def test_resources_choose_bounded_reader_without_executable_hook(monkeypatch):
    backend = AssemblyResponseFieldsAdapter.backend
    reader = AssemblyResponseFieldsAdapter()
    lab = SimpleNamespace(analysis_adapters={backend: object()}, response_field_adapters={backend: reader})
    result, calls = {'provenance': {'adapter': backend, 'adapter_version': '1'}}, []

    def read(_lab, _result, path, *, maximum_bytes):
        assert _lab is lab and _result is result
        calls.append((path, maximum_bytes))
        return {'TEST_ONLY': path}, {'TEST_ONLY': 'manifest'}

    monkeypatch.setattr(response_field, '_read_native', read)
    actual, resources = response_field._adapter_resources(lab, result)
    assert actual is reader
    assert set(resources) == {'field', 'mapping'}
    assert calls == [('simulation/admitted-fields.json', 536870912),
                     ('simulation/mesh-reuse/mapping.json', 134217728)]


@pytest.mark.parametrize('changed', [False, True])
def test_display_rechecks_exact_result_identity_after_reader(monkeypatch, changed):
    result = {'study': {'id': 'S-TEST_ONLY'}}
    proposal, calls = {}, []
    before = {'result_sha256': 'a' * 64}

    def source(lab, identifier):
        calls.append(identifier)
        return result, proposal, {'result_sha256': ('b' if changed and len(calls) == 2 else 'a') * 64}

    display = {'TEST_ONLY': 'bounded source projection'}
    reader = SimpleNamespace(display_response_fields=lambda r, p, resources: display)
    monkeypatch.setattr(response_comparison, '_source', source)
    monkeypatch.setattr(response_field, '_adapter_resources', lambda lab, r: (reader, {}))
    if changed:
        with pytest.raises(ValueError, match='changed during inspection'):
            response_field.display_catalog(object(), 'E-TEST_ONLY')
    else:
        assert response_field.display_catalog(object(), 'E-TEST_ONLY') == {
            'schema_version': '1.0', 'integrity': 'VERIFIED', 'experiment_id': 'E-TEST_ONLY',
            'study_id': 'S-TEST_ONLY', **before, 'display': display,
            'engineering': 'UNKNOWN', 'decision': 'NOT_RELEASED'}
    assert calls == ['E-TEST_ONLY', 'E-TEST_ONLY']


@pytest.mark.parametrize('policy', [None, {}, {'field': {'path': 'simulation/test.json'}},
    {'field': {'path': 'simulation/test.json', 'maximum_bytes': 1, 'caller_override': True}}])
def test_no_unbounded_or_caller_supplied_resource_contract(monkeypatch, policy):
    adapter = SimpleNamespace(field_response_resources=lambda result: policy)
    lab = SimpleNamespace(analysis_adapters={'TEST_ONLY': adapter}, response_field_adapters={})
    monkeypatch.setattr(response_field, '_read_native', lambda *args, **kwargs: pytest.fail('Invalid contract read a file'))
    with pytest.raises(ValueError):
        response_field._adapter_resources(lab, {'provenance': {'adapter': 'TEST_ONLY'}})
