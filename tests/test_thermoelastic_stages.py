"""Portable stage contracts and an opt-in native acceptance; no default solve."""
from copy import deepcopy
import importlib.util
import os

import pytest

from plugins.thermoelastic import reference as domain
from caelab.adapters.thermoelastic_fenicsx import ThermalFenicsxAdapter, ThermoelasticFenicsxAdapter, SOURCE_PATHS
from caelab.adapters import thermoelastic_fenicsx_worker as worker
from caelab.execution_control import ExecutionCancelled, ExecutionCleanupFailed
from caelab.storage import load_json


def small_settings(stage='thermal'):
    value = domain.default_settings(stage)
    value['mesh']['cells'] = [1, 1]
    return domain.validate_settings(value, stage)


def captured_temperature(settings, values=None):
    """Explicit controlled capture for contract checks; not a native solution."""
    lx, ly = settings['domain']['lengths']
    coordinates = [[0., 0.], [lx, 0.], [0., ly], [lx, ly]]
    cells = [[0, 1, 3], [0, 3, 2]]
    return domain.seal_field({'kind': 'field', 'value': [323.15] * 4 if values is None else values,
        'unit': 'K', 'quantity': 'absolute_temperature', 'component': 'scalar', 'location': 'node',
        'reduction': 'none', 'association': 'POINTS', 'measure': 'thermodynamic_temperature',
        'frame': 'global_cartesian', 'coordinate_units': 'm', 'coordinate_frame': 'global_cartesian',
        'coordinates': coordinates, 'node_ids': [0, 1, 2, 3], 'cell_node_ids': cells,
        'mesh_declaration': domain.mesh_declaration(settings), 'mesh_sha256': domain.mesh_digest(coordinates, cells),
        'time': settings['time']['value'], 'time_units': settings['time']['unit'], 'time_origin': settings['time']['origin']})


def test_defaults_ports_and_unbound_structural_draft_are_pure(monkeypatch, tmp_path):
    import builtins
    original = builtins.__import__
    def guard(name, *args, **kwargs):
        if name.split('.')[0] in {'dolfinx', 'petsc4py', 'ufl', 'basix', 'mpi4py'}:
            raise AssertionError('Portable declaration imported a native runtime')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guard)
    thermal, structural = ThermalFenicsxAdapter(), ThermoelasticFenicsxAdapter()
    for adapter in (thermal, structural):
        settings = adapter.default_settings()
        assert adapter.validate_settings(settings) == settings and adapter.restart_safe is True
        assert settings['domain']['unit'] == 'm'
    assert thermal.describe_ports(thermal.default_settings())['inputs']['linearization_temperature']['required'] is False
    assert structural.describe_ports(structural.default_settings())['inputs']['temperature']['required'] is True
    outcome = structural.run(structural.default_settings(), output=tmp_path / 'unbound')
    assert outcome['execution_status'] == 'REJECTED' and outcome['diagnostics']['solver_status'] == 'NOT_RUN'
    assert not (tmp_path / 'unbound').exists()


def test_exact_capture_binding_and_explicit_picard_conductivity():
    thermal_settings = small_settings()
    field = captured_temperature(thermal_settings, [300., 310., 320., 330.])
    structural = ThermoelasticFenicsxAdapter()
    structure = small_settings('structural')
    structure['validation']['free_expansion_max_error'] = None  # Explicitly disable constant-T benchmark for this nonuniform field.
    bound = structural.bind_port(structure, 'temperature', field)
    assert bound['temperature'] == field and structure['temperature'] is None
    assert bound['material'] == structure['material'] and bound['validation'] == structure['validation']
    thermal_settings['conductivity']['beta'] = .001
    lagged = ThermalFenicsxAdapter().bind_port(thermal_settings, 'linearization_temperature', field)
    expected = [200. * (1. + .001 * (temperature - 293.15)) for temperature in field['value']]
    assert domain.conductivity_values(lagged) == pytest.approx(expected)
    assert lagged['linearization_temperature']['capture_sha256'] == field['capture_sha256']
    assert domain.conductivity_values(thermal_settings) == [200.]  # Declared reference-temperature initialization, not a temperature output.


@pytest.mark.parametrize('change', ['unit', 'coordinate_unit', 'frame', 'association', 'time', 'origin',
    'mesh', 'value', 'hash', 'coordinates', 'connectivity', 'node_ids', 'native_path'])
def test_temperature_transfer_rejects_ambiguous_changed_or_different_mesh_data(change):
    settings = small_settings('structural')
    field = captured_temperature(settings)
    if change == 'unit': field['unit'] = 'degC'
    elif change == 'coordinate_unit': field['coordinate_units'] = 'mm'
    elif change == 'frame': field['coordinate_frame'] = 'local'
    elif change == 'association': field['association'] = 'CELLS'
    elif change == 'time': field['time'] = 1.
    elif change == 'origin': field['time_origin'] = 'other_reference'
    elif change == 'mesh': field['mesh_declaration']['mesh']['cells'] = [2, 1]
    elif change == 'value': field['value'][0] = float('nan')
    elif change == 'hash': field['value'][0] += 1.
    elif change == 'coordinates': field['coordinates'][0][0] = .01
    elif change == 'connectivity':
        field['cell_node_ids'] = [[0, 1, 2], [0, 1, 3]]  # Overlap/gap despite correct number of triangles.
        field['mesh_sha256'] = domain.mesh_digest(field['coordinates'], field['cell_node_ids'])
        field = domain.seal_field(field)
    elif change == 'node_ids': field['node_ids'][0] = 9
    elif change == 'native_path': field['path'] = '/arbitrary/temperature.xdmf'
    with pytest.raises(ValueError):
        ThermoelasticFenicsxAdapter().bind_port(settings, 'temperature', field)


@pytest.mark.parametrize('change', ['dimensionless', 'degree', 'large_mesh', 'poisson', 'reference_unit', 'heat_unit', 'hidden_command'])
def test_bounded_physical_settings_are_not_repaired_or_relabelled(change):
    stage = 'structural' if change in ('poisson', 'reference_unit') else 'thermal'
    settings = domain.default_settings(stage)
    if change == 'dimensionless': settings['domain']['unit'] = '1'
    elif change == 'degree': settings['mesh']['degree'] = 2
    elif change == 'large_mesh': settings['mesh']['cells'] = [128, 128]
    elif change == 'poisson': settings['material']['poisson_ratio'] = .5
    elif change == 'reference_unit': settings['material']['reference_temperature_unit'] = 'degC'
    elif change == 'heat_unit': settings['heat_source']['unit'] = 'W'
    elif change == 'hidden_command': settings['command'] = ['arbitrary', 'solver']
    with pytest.raises(ValueError): domain.validate_settings(settings, stage)


def test_nonpositive_lagged_conductivity_is_rejected_without_clamping():
    settings = small_settings()
    settings['conductivity']['beta'] = -.1
    field = captured_temperature(settings)
    with pytest.raises(ValueError, match='strictly positive'):
        ThermalFenicsxAdapter().bind_port(settings, 'linearization_temperature', field)


@pytest.mark.parametrize('failure', ['unavailable', 'cancelled', 'cleanup_pending'])
def test_worker_boundary_failures_retain_sources_and_do_not_fabricate_fields(tmp_path, monkeypatch, failure):
    from caelab.adapters import thermoelastic_fenicsx as adapter_module
    calls = []
    def no_native(command, output, environment, timeout):
        calls.append(command)
        assert command[1] == '-I'
        assert not {'PYTHONPATH', 'PETSC_OPTIONS', 'PETSC_OPTIONS_YAML'} & set(environment)
        if failure == 'cancelled': raise ExecutionCancelled('Controlled cancellation before native launch')
        if failure == 'cleanup_pending': raise ExecutionCleanupFailed('Controlled unconfirmed cleanup')
        raise RuntimeError('Controlled missing native dependency; no worker process launched')
    monkeypatch.setattr(adapter_module.rectangle, '_run_process', no_native)
    adapter = ThermalFenicsxAdapter()
    if failure == 'cleanup_pending':
        with pytest.raises(ExecutionCleanupFailed): adapter.run(small_settings(), output=tmp_path)
    else:
        result = adapter.run(small_settings(), output=tmp_path)
        assert result['execution_status'] == ('CANCELLED' if failure == 'cancelled' else 'FAILED')
        assert not result['responses']
    native = tmp_path / 'native'
    assert len(calls) == 1 and not (native / 'field.xdmf').exists()
    manifest = load_json(native / 'source_manifest.json')
    assert set(manifest['files']) == set(SOURCE_PATHS)
    helpers, reference, manifest_sha = worker._bootstrap(native)
    assert reference.VERSION == '1' and manifest_sha == helpers._sha(native / 'source_manifest.json')
    (native / 'thermoelastic_reference.py').write_text('changed source', encoding='utf-8')
    with pytest.raises(RuntimeError, match='captured source bytes changed'): worker._bootstrap(native)


def test_native_dependency_presence_is_separate_from_portable_contract():
    if importlib.util.find_spec('dolfinx') is None:
        pytest.skip('FEniCSx unavailable in this Python; portable checks do not claim native execution')
    assert ThermalFenicsxAdapter().restart_safe  # Discovery does not solve or qualify physics.


@pytest.mark.skipif(os.environ.get('CAELAB_RUN_THERMOELASTIC_NATIVE') != '1',
                    reason='Native FEniCSx acceptance requires explicit installed-operator opt-in; no default solver launch')
def test_installed_native_conduction_then_free_expansion(tmp_path):
    """Operator-only acceptance: actual worker outputs, not controlled fixtures."""
    from caelab.evaluation import run
    thermal, structural = ThermalFenicsxAdapter(), ThermoelasticFenicsxAdapter()
    first = run(thermal, thermal.default_settings(), output=tmp_path / 'thermal')
    assert first['execution_status'] == 'SUCCEEDED', first['diagnostics']
    assert first['responses']['mean_temperature']['value'] == pytest.approx(323.15, abs=1e-8)
    bound = structural.bind_port(structural.default_settings(), 'temperature', first['responses']['temperature'])
    second = run(structural, bound, output=tmp_path / 'structural')
    assert second['execution_status'] == 'SUCCEEDED', second['checks']
    assert second['responses']['free_expansion_error']['value'] <= bound['validation']['free_expansion_max_error']
    assert second['responses']['displacement_linf']['value'] > 0.
    assert second['responses']['stress']['unit'] == 'Pa'
