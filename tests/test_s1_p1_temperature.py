"""S1 transfer/temperature contracts; synthetic fields are NOT solver evidence."""
from copy import deepcopy
import builtins
import json
import math

import numpy as np
import pytest

from caelab import p1_temperature_transfer as t
from caelab import scikit_fem_models as domain
from caelab.backends import get_backend
from plugins.thermoelastic import reference as old


def settings(backend=domain.THERMAL, cells=(2, 1), instant=0., origin='test_origin', unit='s'):
    result = domain.default_settings(backend)
    result['mesh']['cells'] = list(cells)
    result['time'] = {'value': instant, 'unit': unit, 'origin': origin}
    return result


def analytic_field(s, f=lambda x, y: 300. + 4.*x - 2.*y, *, unit='K'):
    coords = t.rectangle_geometry(s)['coordinates']
    return t.temperature_field(s, [f(x, y) for x, y in coords], unit=unit)


def options(receiver, sources=('Heat',), mode='exact'):
    result = t.default_options(sources[0], receiver_time=receiver['time'])
    result['time']['mode'] = mode
    result['time']['sources'] = [{'stage': name, 'output': 'temperature'} for name in sources]
    return result


def reseal(field):
    field['mesh_sha256'] = old.mesh_digest(field['coordinates'], field['cell_node_ids'])
    return old.seal_field(field)


def test_three_pure_capabilities_and_windows_are_separate(monkeypatch):
    original_import = builtins.__import__
    def guard(name, *args, **kwargs):
        if name.split('.')[0] in {'skfem', 'scipy', 'dolfinx', 'petsc4py', 'ufl'}:
            raise AssertionError('Check must not import a solver')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guard)
    from caelab.adapters.native_doctor import execution_environment
    from caelab.pde_document import default_draft, diagnostics
    for name in (domain.THERMAL, domain.STRUCTURAL, domain.WEAK):
        adapter = get_backend(name)
        s = adapter.default_settings()
        assert adapter.validate_settings(s) == s
        assert adapter.describe_inputs(s)
        assert adapter.describe_ports(s)
        assert not execution_environment(name, host='win32')['blocked']
    assert execution_environment('pde.fenicsx.rectangle', host='win32')['blocked']
    assert execution_environment('thermal.fenicsx.rectangle', host='win32')['blocked']
    draft = default_draft(domain.WEAK)
    draft['settings']['forms']['linear'] = '__import__("os")'
    assert diagnostics(draft)
    assert draft['settings']['forms']['linear'] == '__import__("os")'
    draft['settings']['forms']['linear'] = 'k*v'  # Wrong dimensions.
    assert diagnostics(draft)


def test_constant_really_different_meshes_A03():
    source = settings(cells=(2, 1))
    receiver = settings(domain.STRUCTURAL, (3, 2))
    field = analytic_field(source, lambda x, y: 323.15)
    mapped, receipt = t.map_temperature([field], receiver, options(receiver), source_refs=[{'test': 'CONTROLLED'}])
    assert len(field['node_ids']) == 6 and len(mapped['node_ids']) == 12
    assert field['mesh_sha256'] != mapped['mesh_sha256']
    assert field['cell_node_ids'] != mapped['cell_node_ids']
    assert field['node_ids'] != mapped['node_ids']
    assert max(abs(v - 323.15) for v in mapped['value']) <= 1e-10
    assert receipt['conservative'] is False
    assert receipt['coverage'] == {'required': 12, 'covered': 12, 'policy': 'all_receiver_nodes'}
    assert receipt['sources'][0] == field
    assert all(row['valid'] for row in receipt['spatial'][0]['rows'])
    assert old.seal_field(receipt)['capture_sha256'] == receipt['capture_sha256']


@pytest.mark.parametrize('reorder', [False, True])
def test_affine_reordered_sparse_ids_actual_connectivity_A04(reorder):
    source = settings(cells=(2, 2)); receiver = settings(domain.STRUCTURAL, (3, 3))
    f = analytic_field(source)
    if reorder:
        oldids = f['node_ids'][:]
        sparse = {n: 101 + 11*n for n in oldids}
        order = list(reversed(range(len(oldids))))
        f['node_ids'] = [sparse[oldids[i]] for i in order]
        f['coordinates'] = [f['coordinates'][i] for i in order]
        f['value'] = [f['value'][i] for i in order]
        f['cell_node_ids'] = [[sparse[n] for n in reversed(c)] for c in reversed(f['cell_node_ids'])]
        f = reseal(f)
    before = deepcopy(f)
    out, rec = t.map_temperature([f], receiver, options(receiver))
    assert f == before  # No read-side normalization or source mutation.
    assert max(abs(v - (300 + 4*x - 2*y)) for v, (x, y) in zip(out['value'], out['coordinates'])) <= 1e-10
    assert rec['sources'][0]['node_ids'] == f['node_ids']
    assert rec['sources'][0]['cell_node_ids'] == f['cell_node_ids']


@pytest.mark.parametrize('failure', ['hole', 'duplicate_cell', 'degenerate', 'wrong_topology', 'duplicate_position',
    'missing_mask', 'false_mask', 'short_mask', 'wrong_mask_type', 'nan', 'hash', 'quantity', 'unit',
    'frame', 'coordinate_frame', 'coordinate_unit', 'association', 'basis', 'measure', 'component', 'duplicate_id'])
def test_reject_bad_sources_without_reconstructing_or_clamping_A05(failure):
    s = settings(cells=(2, 2)); r = settings(domain.STRUCTURAL, (3, 2)); f = analytic_field(s)
    if failure == 'hole': f['cell_node_ids'].pop()
    elif failure == 'duplicate_cell': f['cell_node_ids'][-1] = f['cell_node_ids'][0][:]
    elif failure == 'degenerate': f['cell_node_ids'][0] = [0, 1, 2]
    elif failure == 'wrong_topology': f['cell_node_ids'][0] = [0, 2, 8]
    elif failure == 'duplicate_position': f['coordinates'][1] = f['coordinates'][0][:]
    elif failure == 'missing_mask': f.pop('valid_mask')
    elif failure == 'false_mask': f['valid_mask'][1] = False
    elif failure == 'short_mask': f['valid_mask'].pop()
    elif failure == 'wrong_mask_type': f['valid_mask'][1] = 1
    elif failure == 'nan': f['value'][1] = math.nan
    elif failure == 'hash': f['value'][1] += .1
    elif failure == 'quantity': f['quantity'] = 'dimensionless'
    elif failure == 'unit': f['unit'] = 'delta_K'
    elif failure == 'frame': f['frame'] = 'local'
    elif failure == 'coordinate_frame': f['coordinate_frame'] = 'local'
    elif failure == 'coordinate_unit': f['coordinate_units'] = 'mm'
    elif failure == 'association': f['association'] = 'CELLS'
    elif failure == 'basis': f['basis'] = 'P2'
    elif failure == 'measure': f['measure'] = 'temperature_difference'
    elif failure == 'component': f['component'] = 'vector'
    elif failure == 'duplicate_id': f['node_ids'][1] = f['node_ids'][0]
    if failure not in ('nan', 'hash'): f = reseal(f)
    with pytest.raises(t.TransferError) as error:
        t.map_temperature([f], r, options(r))
    assert error.value.receipt['status'] == 'FAILED'
    json.dumps(error.value.receipt, allow_nan=False)  # Retainable even for NaN input.


def test_outside_receiver_has_failed_coverage_not_zero_substitution():
    s = settings(); r = settings(domain.STRUCTURAL, (3, 2)); r['domain']['lengths'][0] = 1.1
    with pytest.raises(t.TransferError) as error:
        t.map_temperature([analytic_field(s)], r, options(r))
    rec = error.value.receipt
    assert rec['mapped_field'] is None and rec['invalid_receiver_ids']
    assert rec['coverage']['covered'] < rec['coverage']['required']
    assert all(row['value_K'] is None for row in rec['spatial'][0]['rows'] if not row['valid'])


def test_linear_time_two_real_mesh_declarations_and_saved_weights_A06():
    a = settings(cells=(2, 1), instant=0.)
    b = settings(cells=(4, 2), instant=2.)
    r = settings(domain.STRUCTURAL, (3, 2), instant=1.)
    fields = [analytic_field(s, lambda x, y, t0=s['time']['value']: 300+4*x-2*y+5*t0) for s in (a, b)]
    policy = options(r, ('Start', 'End'), 'linear')
    refs = [{'stage': 'Start', 'capture': fields[0]['capture_sha256']}, {'stage': 'End', 'capture': fields[1]['capture_sha256']}]
    out, rec = t.map_temperature(fields, r, policy, source_refs=refs)
    assert rec['clock']['weights'] == [.5, .5] and rec['source_refs'] == refs
    assert len(rec['spatial']) == 2 and rec['spatial'][0]['source_mesh_sha256'] != rec['spatial'][1]['source_mesh_sha256']
    assert max(abs(v - (305+4*x-2*y)) for v, (x, y) in zip(out['value'], out['coordinates'])) <= 1e-10
    assert out['snapshot_kind'] == 'physical_snapshot'
    assert 'NOT_A_TRANSIENT_SOLVER' in rec['clock']['physics']


@pytest.mark.parametrize('fault', ['unbracketed', 'duplicate', 'nonmonotone', 'origin', 'missing', 'receiver_clock', 'receiver_origin'])
def test_required_clock_gates(fault):
    a, b = settings(instant=0.), settings(instant=2.)
    r = settings(domain.STRUCTURAL, (3, 2), instant=1.)
    fields = [analytic_field(a), analytic_field(b)]; policy = options(r, ('A', 'B'), 'linear')
    if fault == 'unbracketed': r['time']['value'] = 3.; policy['time']['receiver'] = deepcopy(r['time'])
    elif fault == 'duplicate': fields[1]['time'] = 0.; fields[1] = reseal(fields[1])
    elif fault == 'nonmonotone': fields.reverse()
    elif fault == 'origin': fields[1]['time_origin'] = 'another'; fields[1] = reseal(fields[1])
    elif fault == 'missing': fields.pop()
    elif fault == 'receiver_clock': policy['time']['receiver']['value'] = 8.
    elif fault == 'receiver_origin': r['time']['origin'] = 'other'
    with pytest.raises(t.TransferError): t.map_temperature(fields, r, policy)


def test_exact_clock_physical_units_and_no_nearest_time():
    s = settings(instant=1000., unit='ms'); r = settings(domain.STRUCTURAL, (3, 2), instant=1.)
    out, rec = t.map_temperature([analytic_field(s)], r, options(r))
    assert out['time'] == 1. and out['time_units'] == 's'
    assert rec['clock']['source_seconds'] == ['1.0000']
    r['time']['value'] += 1e-12
    with pytest.raises(t.TransferError): t.map_temperature([analytic_field(s)], r, options(r))


def test_explicit_steady_relabel_is_a_user_declaration_not_interpolation():
    s = settings(instant=0., origin='initial_state')
    r = settings(domain.STRUCTURAL, (3, 2), instant=100., origin='assembly_clock')
    policy = options(r, mode='steady_relabel')
    with pytest.raises(t.TransferError): t.map_temperature([analytic_field(s)], r, policy)
    policy['time']['same_steady_state'] = {'declared': True, 'statement': '열평형 상태가 동일하다고 사용자가 선언함'}
    out, rec = t.map_temperature([analytic_field(s)], r, policy)
    assert rec['clock']['mode'] == 'steady_relabel' and rec['clock']['weights'] == [1.]
    assert out['snapshot_kind'] == 'steady'
    assert rec['clock']['same_steady_state'] == policy['time']['same_steady_state']
    f = analytic_field(s); f['snapshot_kind'] = 'physical_snapshot'; f = reseal(f)
    with pytest.raises(t.TransferError): t.map_temperature([f], r, policy)


def test_kelvin_celsius_delta_and_receiver_Tref_ownership_A07():
    s = settings(); r = settings(domain.STRUCTURAL, (3, 2))
    kelvin = analytic_field(s, lambda x, y: 323.15)
    celsius = analytic_field(s, lambda x, y: 50., unit='degC')
    out_k, rec_k = t.map_temperature([kelvin], r, options(r))
    out_c, rec_c = t.map_temperature([celsius], r, options(r))
    assert out_k['value'] == pytest.approx(out_c['value'], abs=1e-12)
    assert rec_c['temperature']['source_offsets_K'] == [273.15]
    assert rec_k['temperature']['reference_subtractions_in_mapping'] == 0
    r['temperature_mode'] = 'difference'
    policy = options(r); policy.update(target_quantity=t.DIFFERENCE, target_unit='delta_K')
    delta, rec = t.map_temperature([celsius], r, policy)
    assert delta['value'] == pytest.approx([30.] * len(delta['value']), abs=1e-12)
    assert rec['temperature']['reference_subtractions_in_mapping'] == 1
    assert delta['temperature_reference'] == t.receiver_reference(r)
    get_backend(domain.STRUCTURAL).bind_port(r, 'temperature', delta)
    delta_c = deepcopy(delta); delta_c['unit'] = 'delta_degC'; delta_c = reseal(delta_c)
    assert t._absolute_values(delta_c) == pytest.approx(out_c['value'])  # Zero offset for differences.
    changed = deepcopy(r); changed['material']['reference_temperature'] += 1.
    with pytest.raises(ValueError): get_backend(domain.STRUCTURAL).bind_port(changed, 'temperature', delta)
    # Independent constitutive datum, not claimed to be a solved displacement.
    assert r['material']['thermal_expansion'] * 30. * r['domain']['lengths'][0] == pytest.approx(.00069)


def test_original_exact_path_remains_strict_and_picard_is_reused():
    s = old.default_settings('thermal'); s['mesh']['cells'] = [2, 1]
    capture = analytic_field(s)
    legacy = {k: v for k, v in capture.items() if k not in t.EXT_KEYS}; legacy = old.seal_field(legacy)
    assert old.validate_temperature(legacy, s) == legacy
    with pytest.raises(ValueError): old.validate_temperature(capture, s)
    target = settings(cells=(2, 1), origin=s['time']['origin'])
    target['conductivity']['beta'] = .001
    bound = get_backend(domain.THERMAL).bind_port(target, 'linearization_temperature', capture)
    assert old.conductivity_values(bound) == pytest.approx([200*(1+.001*(v-293.15)) for v in capture['value']])
    assert target['linearization_temperature'] is None


def test_post_writer_uses_exact_values_units_clock(tmp_path):
    from caelab.physical_fields import write_field
    import xml.etree.ElementTree as ET
    s = settings(instant=2., origin='measured_clock')
    f = analytic_field(s)
    result = write_field('temperature', f, tmp_path/'공간 온도')
    clock = ET.parse(result['path'])
    assert float(clock.find('.//DataSet').get('timestep')) == 2.
    assert result['native_metadata']['time'] == {'unit':'s', 'semantics':'measured_clock', 'values':[2.]}
    vtu = ET.parse(result['path'].with_name('field.vtu'))
    array = next(x for x in vtu.findall('.//PointData/DataArray') if x.get('Name') == 'temperature')
    assert [float(v) for v in array.text.split()] == f['value']


def test_worker_imports_captured_plugin_not_installed_shadow_before_any_solve(tmp_path):
    """Real owned Python process; forced stop before OSS import, not a FE test."""
    import json
    import subprocess
    import sys
    from pathlib import Path
    from caelab.adapters.scikit_fem_spatial import _LOADED
    from caelab import scikit_fem_models as domain
    import hashlib
    native = tmp_path / 'native'; frozen = native / 'sources'
    manifest = {'files': {}}
    for name, data in _LOADED.items():
        dest = frozen / name; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data)
        manifest['files'][name] = {'sha256': hashlib.sha256(data).hexdigest()}
    (native / 'source_manifest.json').write_text(json.dumps(manifest))
    (native / 'input.json').write_text(json.dumps({'backend': domain.THERMAL, 'settings': domain.default_settings(domain.THERMAL)}))
    live = tmp_path / 'installed'; (live / 'plugins').mkdir(parents=True)
    (live / 'plugins/__init__.py').write_text("raise RuntimeError('POISON_PLUGIN_IMPORTED')\n")
    wrapper = tmp_path / 'bootstrap.py'
    wrapper.write_text("import sys,runpy,importlib.metadata\n"
        + "sys.path.insert(0," + repr(str(live)) + ")\n"
        + "def stop(name): raise RuntimeError('STOP_BEFORE_OSS_IMPORT')\n"
        + "importlib.metadata.version=stop\n"
        + "sys.argv=[" + repr(str(frozen / 'caelab/adapters/scikit_fem_worker.py')) + "," + repr(str(native/'input.json')) + "]\n"
        + "runpy.run_path(sys.argv[0],run_name='__main__')\n")
    child = None
    try:
        child = subprocess.Popen([sys.executable, '-I', str(wrapper)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = child.communicate(timeout=30)
        assert child.returncode == 1 and 'STOP_BEFORE_OSS_IMPORT' in stderr, stderr
        assert 'POISON_PLUGIN_IMPORTED' not in stderr
        identities = json.loads((native/'import_identity.json').read_text())
        original = identities['plugins.thermoelastic.reference']
        assert Path(original['file']) == frozen/'plugins/thermoelastic/reference.py'
        assert original['sha256'] == manifest['files']['plugins/thermoelastic/reference.py']['sha256']
    finally:
        if child is not None:
            if child.poll() is None: child.kill()
            child.wait(timeout=5)
            if child.stdout: child.stdout.close()
            if child.stderr: child.stderr.close()
