"""Portable projections of already retained Maxwell and J2 native evidence.

No native library is loaded. Original bytes, inputs, table identities and domain
verdicts are retained; exact field selection uses the existing J2 reader.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from ..storage import canonical_hash

MAXWELL = 'material.mfront.viscoelastic'
J2 = 'structural.code_aster.plasticity'
ELASTIC = 'material.mfront'
SVK = 'material.mfront.hyperelastic'
MATERIALS = (ELASTIC, SVK, MAXWELL)


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _path(output, relative):
    _need(isinstance(relative, str), 'Invalid retained native artifact path')
    parts = PurePosixPath(relative)
    _need(isinstance(relative, str) and not parts.is_absolute() and '\\' not in relative and
          parts.parts and all(part not in ('.', '..') for part in parts.parts), 'Invalid retained native artifact path')
    root = Path(output)
    _need(not root.is_symlink() and root.is_dir(), 'Retained native output must be a directory, not a link')
    root = root.resolve(strict=True)
    path = root
    for part in parts.parts:
        path = path / part
        _need(not path.is_symlink(), 'Retained native artifact contains a symbolic link')
    _need(path.is_file() and path.resolve(strict=True).is_relative_to(root), 'Retained native artifact is missing')
    return path


def _file_pin(output, relative):
    path = _path(output, relative)
    size = path.stat().st_size
    _need(0 < size <= 8 * 1024**3, 'Retained native artifact exceeds its bounded reader limit')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'path': 'simulation/' + relative, 'sha256': digest.hexdigest(), 'size_bytes': size}


def _load(output, relative, maximum=64 * 1024 * 1024):
    path = _path(output, relative)
    _need(0 < path.stat().st_size <= maximum, 'Retained native JSON exceeds its declared reader limit')
    payload = path.read_bytes()
    def pairs(items):
        value = {}
        for key, item in items:
            _need(key not in value, 'Duplicate retained native JSON key')
            value[key] = item
        return value
    def constant(value):
        raise ValueError('Nonfinite retained native JSON constant')
    value = json.loads(payload, object_pairs_hook=pairs, parse_constant=constant)
    canonical_hash(value)  # Also rejects exponent overflow and nonfinite arrays.
    return value


def _manifest(output, names):
    _need(0 < len(names) <= 1024, 'Retained native artifact inventory exceeds its bounded reader limit')
    result = [_file_pin(output, name) for name in sorted(set(names))]
    _need(len({item['path'].casefold() for item in result}) == len(result), 'Retained native artifact path alias')
    return result


def _channel_descriptor(channel, backend, digest):
    origin = deepcopy(channel['origin'])
    return {'kind': 'series', 'unit': channel['unit'], 'label': channel['label'],
            'quantity': channel['quantity'], 'component': channel['component'],
            'measure': channel['measure'], 'location': channel['location'],
            'coordinate_frame': channel['coordinate_frame'], 'reduction':
            'unweighted_arithmetic_mean' if origin.get('aggregation', {}).get('operation') == 'arithmetic_mean' else 'none',
            'axes': [{'name': 'time', 'unit': channel['axis']['unit'],
                      'semantics': channel['axis'].get('semantics', 'NATIVE_MATERIAL_HISTORY_TIME')}],
            'initial_state': deepcopy(channel['initial_state']),
            'source': {'backend': backend, 'artifact': 'native_raw.json' if backend in MATERIALS else 'analysis_raw.json',
                       'sha256': digest, 'selector': channel['id'], 'value_origin': origin['kind'],
                       'native_origin': origin},
            'qualification': {'physical': 'UNKNOWN', 'decision': 'NOT_RELEASED'}}


def _maxwell_context(outcome, output):
    from plugins.material_point import viscoelastic_reference as domain
    from . import mfront_history, mfront_viscoelastic_worker as worker
    from .mfront_viscoelastic import CAPTURE_NAMES
    _need(_load(output, 'analysis_raw.json') == outcome and outcome.get('solver_status') == 'COMPLETED' and
          outcome.get('status') in ('COMPLETED', 'REJECTED'), 'Maxwell retained solve/outcome is incomplete')
    settings = _load(output, 'input.json', 1024 * 1024)
    _need(domain.validate_settings(settings) == settings, 'Maxwell retained settings are not normalized')
    raw = _load(output, 'native_raw.json')
    p = outcome.get('provenance', {})
    build = _load(output, 'build_identity.json', 4 * 1024 * 1024)
    inventory = _load(output, 'source_inventory.json', 1024 * 1024)
    policy = _load(output, 'frozen_execution_policy.json', 1024 * 1024)
    _need(p.get('adapter') == MAXWELL and p.get('adapter_version') == '1' and raw.get('schema_version') == '1' and
          raw.get('input_sha256') == _file_pin(output, 'input.json')['sha256'] and
          raw.get('source_files') == inventory == p.get('source_files') == policy.get('source_files') and
          isinstance(inventory, dict) and set(inventory) == set(CAPTURE_NAMES) and
          policy.get('settings_sha256') == canonical_hash(settings) and policy.get('limits') == settings['limits'],
          'Maxwell saved input/source/threshold identity differs')
    names = {'analysis_raw.json', 'input.json', 'native_raw.json', 'build_identity.json', 'source_inventory.json',
             'frozen_execution_policy.json', 'runtime.json', 'build/src/libBehaviour.so', 'mtest.res'}
    capture_names = []
    for original, digest in inventory.items():
        _need(isinstance(original, str) and isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest),
              'Maxwell source pin is malformed')
        name = 'elastic_reference.py' if original == 'plugins/material_point/reference.py' else PurePosixPath(original).name
        _need(name not in capture_names, 'Maxwell source capture aliases another source')
        capture_names.append(name)
        _need(_file_pin(output, name)['sha256'] == digest, 'Maxwell captured original source changed')
        names.add(name)
    _need(inventory.get('caelab/adapters/mfront_viscoelastic_worker.py') == raw.get('worker_sha256') and
          inventory.get('plugins/material_point/viscoelastic_reference.py') == policy.get('domain_sha256') and
          raw.get('transport_sha256') == policy.get('transport_sha256') == inventory.get(worker.TRANSPORT_KEY) and
          raw.get('compiler_helper_sha256') == policy.get('compiler_helper_sha256') == inventory.get(worker.COMPILER_HELPER_KEY),
          'Maxwell saved worker/domain/transport identity differs')
    _need(raw.get('library_sha256') == build.get('library_sha256') == _file_pin(output, 'build/src/libBehaviour.so')['sha256'] and
          build == p.get('build') and raw.get('runtime') == p.get('versions') == _load(output, 'runtime.json') and
          raw.get('behaviour_description') == p.get('behaviour_description') and 'native_rejection' not in raw,
          'Maxwell original native build/runtime/field record differs')
    _need(domain.assess(settings, raw) == outcome.get('assessment') and
          outcome['assessment'].get('metrics') == outcome.get('metrics') and
          outcome['assessment'].get('checks') == outcome.get('checks'), 'Maxwell retained domain verdict differs')
    mtest = raw.get('mtest', {})
    states = deepcopy(mtest.get('states'))
    _need(isinstance(states, list) and worker.parse_mtest_table(_path(output, 'mtest.res'), states) ==
          mtest.get('native_output_table') and states == mtest.get('states'), 'Maxwell energy table differs from original native bytes')
    pins = _manifest(output, names)
    digest = canonical_hash(pins)
    artifact = next(item for item in pins if item['path'] == 'simulation/native_raw.json')
    channels = mfront_history.channels(outcome, settings, raw, artifact)
    return channels, digest


def _elastic_context(backend, outcome, output):
    if backend == ELASTIC:
        from plugins.material_point import reference as domain
    else:
        from plugins.hyperelastic import reference as domain
    _need(_load(output, 'analysis_raw.json') == outcome and outcome.get('solver_status') == 'COMPLETED' and
          outcome.get('status') in ('COMPLETED', 'REJECTED'), 'Material retained solve/outcome is incomplete')
    settings = _load(output, 'input.json', 1024 * 1024)
    _need(domain.validate_settings(settings) == settings, 'Material retained settings are not normalized')
    raw = _load(output, 'native_raw.json')
    p = outcome.get('provenance', {})
    build = _load(output, 'build_identity.json', 4 * 1024 * 1024)
    runtime = _load(output, 'runtime.json', 4 * 1024 * 1024)
    _need(p.get('adapter') == backend and p.get('adapter_version') == '1' and raw.get('schema_version') == '1' and
          p.get('input_sha256') == raw.get('input_sha256') == _file_pin(output, 'input.json')['sha256'] and
          raw.get('library_sha256') == build.get('library_sha256') == _file_pin(output, 'build/src/libBehaviour.so')['sha256'] and
          build == p.get('build') and raw.get('runtime') == runtime and
          all(p.get('versions', {}).get(key) == value for key, value in runtime.items()) and
          raw.get('behaviour_description') == p.get('behaviour_description') and 'native_rejection' not in raw,
          'Material retained input/build/runtime identity differs')
    names = {'analysis_raw.json', 'input.json', 'native_raw.json', 'build_identity.json', 'runtime.json',
             'domain_reference.py', 'build/src/libBehaviour.so'}
    if backend == ELASTIC:
        _need(raw.get('worker_sha256') == p.get('worker_sha256') == _file_pin(output, 'mfront_material_worker.py')['sha256'] and
              p.get('domain_plugin', {}).get('source_sha256') == _file_pin(output, 'domain_reference.py')['sha256'] and
              raw.get('source_sha256') == p.get('behaviour_source_sha256') and
              raw.get('conventions') == {'physical': 'xx,yy,zz,xy,xz,yz', 'native': 'xx,yy,zz,sqrt2*xy,sqrt2*xz,sqrt2*yz',
                                        'strain': 'infinitesimal, not engineering shear', 'stress_unit': 'MPa'},
              'Material retained tensor/source contract differs')
        names.add('mfront_material_worker.py')
    else:
        sources = p.get('captured_source_sha256')
        # Hyperelastic captures use source_snapshot_sha256 in the producer.
        if sources is None:
            sources = p.get('source_snapshot_sha256')
        _need(isinstance(sources, dict) and sources == raw.get('captured_source_sha256') and 1 <= len(sources) <= 32,
              'SVK retained source inventory is incomplete')
        for name, digest in sources.items():
            _need(_file_pin(output, name)['sha256'] == digest, 'SVK captured original source changed')
            names.add(name)
        from .mfront_hyperelastic import _SOURCES
        _need(set(sources) == set(_SOURCES) and
              raw.get('worker_sha256') == sources.get('mfront_hyperelastic_worker.py') and
              raw.get('source_sha256') == p.get('behaviour_source_sha256') and
              raw.get('finite_strain_options') == p.get('finite_strain_options') == {'stress_measure': 'PK1', 'tangent_operator': 'DPK1_DF'} and
              raw.get('conventions') == {'general_order': list(domain.F_COMPONENTS), 'stress_measure': 'PK1',
                  'tangent': 'rows_P_columns_F', 'stored_energy': 'native_per_reference_volume_MPa', 'MTest': 'Cauchy_Kelvin6'},
              'SVK retained measure/source contract differs')
    assessment = domain.assess(settings, raw)
    _need(assessment == outcome.get('assessment') and assessment.get('metrics') == outcome.get('metrics') and
          assessment.get('checks') == outcome.get('checks'), 'Material retained domain verdict differs')
    pins = _manifest(output, names)
    digest = canonical_hash(pins)
    raw_hash = next(item['sha256'] for item in pins if item['path'] == 'simulation/native_raw.json')
    channels = []
    frame = 'Tridimensional model component basis; sensor/world alignment UNKNOWN'
    initial = {'index': 0, 'kind': 'UNPREPARED_INITIAL_CONDITION'} if backend == ELASTIC else {
        'index': None, 'kind': 'UNPREPARED_INITIAL_CONDITION_EXCLUDED', 'time_s': raw['initial']['time_s']}
    def add(identifier, label, quantity, component, measure, values, times, driver, field, *, derived=False):
        channels.append({'id': identifier, 'label': label, 'quantity': quantity, 'component': component,
                         'measure': measure, 'location': 'single homogeneous material point', 'unit': 'MPa',
                         'coordinate_frame': frame, 'axis': {'quantity': 'time', 'unit': 's', 'values': list(times)},
                         'values': list(values), 'initial_state': deepcopy(initial),
                         'origin': {'kind': 'DERIVED' if derived else 'NATIVE', 'driver': driver,
                                    'artifact': 'simulation/native_raw.json', 'sha256': raw_hash,
                                    'native_field': field, 'mapping': measure}})
    if backend == ELASTIC:
        rows = [raw['mgis']['initial'], *raw['mgis']['steps']]
        times = [row['time_s'] for row in rows]
        _need(times == [row['time_s'] for row in settings['history']], 'Material actual native time differs')
        valid = assessment['metrics']['stress_history'].get('valid') is True
        if valid:
            _need(assessment['metrics']['stress_history']['value'] == [row['stress_physical_mpa'] for row in rows],
                  'Elastic saved scalar tensor histories differ from native observations')
            for driver, states in (('mgis', rows), ('mtest', raw['mtest']['states'])):
                for axis, component in enumerate(domain.COMPONENTS):
                    add(f'{driver}-stress-{component}', f'{driver.upper()} Cauchy stress {component}', 'stress', component,
                        'infinitesimal Cauchy stress; physical tensor components',
                        [row['stress_physical_mpa'][axis] for row in states], times, driver, 'stress_physical_mpa')
        energy = assessment['metrics']['energy_density_history']
        if energy.get('valid') is True:
            add('derived-elastic-energy', 'Elastic energy density derived from recorded stress and strain',
                'stored_energy_density', 'scalar', 'DERIVED 1/2 stress:strain; physical shear multiplicity 2; per reference volume',
                energy['value'], times, 'mgis', 'stress_physical_mpa,strain_physical', derived=True)
    else:
        # No native integrated stress or energy is asserted for unprepared t0.
        rows, times = raw['steps'], [row['time_s'] for row in raw['steps']]
        _need(times == [row['time_s'] for row in settings['history'][1:]], 'SVK native endpoint time differs')
        if assessment['numerical_status'] != 'FAIL':
            for axis, component in enumerate(domain.F_COMPONENTS):
                add(f'mgis-pk1-{component}', f'MGIS PK1 stress {component}', 'stress', component,
                    'PK1; physical general tensor components', [row['pk1_stress_mpa'][axis] for row in rows], times,
                    'mgis', 'pk1_stress_mpa')
            for axis, component in enumerate(('xx', 'yy', 'zz', 'xy', 'xz', 'yz')):
                add(f'mgis-cauchy-{component}', f'Cauchy stress {component} derived from native PK1/F', 'stress', component,
                    'DERIVED Cauchy = PK1 F^T / det(F)', [row['cauchy_stress_mpa'][axis] for row in rows], times,
                    'mgis', 'pk1_stress_mpa,deformation_gradient', derived=True)
                # MTest stores symmetric Cauchy Kelvin6; undo only its recorded sqrt(2) shear convention.
                import math
                scale = 1. if axis < 3 else math.sqrt(2.)
                add(f'mtest-cauchy-{component}', f'MTest native Cauchy stress {component}', 'stress', component,
                    'Cauchy; recorded Kelvin6 converted to physical symmetric tensor',
                    [row['cauchy_stress_kelvin_mpa'][axis] / scale for row in raw['mtest']['steps']], times,
                    'mtest', 'cauchy_stress_kelvin_mpa')
            add('mgis-stored', 'MGIS native stored energy per reference volume', 'stored_energy_density', 'scalar',
                'native stored energy per reference volume', [row['stored_energy_density_mpa'] for row in rows], times,
                'mgis', 'stored_energy_density_mpa')
    return channels, digest


def _j2_context(outcome, output):
    from .plasticity_response_fields import PlasticityResponseFieldsAdapter
    from . import plasticity_response_fields as reader
    from plugins.elasticity import plasticity_reference as domain
    _need(_load(output, 'analysis_raw.json') == outcome, 'J2 supplied outcome differs from its retained bytes')
    settings = _load(output, 'input.json', 1024 * 1024)
    p = outcome.get('provenance', {})
    version = p.get('adapter_version')
    _need(p.get('adapter') == J2 and version in reader._SOURCES, 'Unsupported J2 native producer')
    records = outcome.get('mesh_records')
    _need(isinstance(records, list) and 1 <= len(records) <= 3, 'J2 retained mesh count is not bounded')
    names = {'input.json', 'analysis_raw.json', *reader._SOURCES[version]}
    for index, record in enumerate(records):
        names.update(spec['path'].removeprefix('simulation/') for spec in reader._level_policy(index).values())
        names.update({f'level_{index}/mesh.msh', f'level_{index}/results.med'})
        for state in record['states']:
            order = state['actual_result_order']
            _need(type(order) is int and order >= 0, 'J2 native result order must be exact')
            names.update(f'level_{index}/order_{order}_{field}.table.json'
                         for field in ('depl', 'reac_noda', 'sief_elga', 'vari_elga', 'boundary_resultants'))
    pins = _manifest(output, names)
    digest = canonical_hash(pins)
    model_revision = canonical_hash(domain.model_declaration(settings))
    revision = canonical_hash({'backend': J2, 'settings': settings, 'native_artifacts': pins})
    # A read-only envelope adapts the existing strict Study reader to this native
    # output folder. These revisions identify bytes, not a new saved owner/run.
    result = {'status': 'REJECTED' if outcome.get('status') == 'REJECTED' else 'COMPLETED_REVIEW_REQUIRED',
              'solver_status': outcome.get('solver_status'), 'converged': outcome.get('converged'),
              'decision': 'NOT_RELEASED', 'cad_revision': None, 'model_revision': model_revision,
              'proposal_revision': revision, 'metrics': deepcopy(outcome.get('metrics')),
              'provenance': {'adapter': J2, 'adapter_version': version, 'proposal_sha256': revision,
                             'execution_settings': settings, 'adapter_details': deepcopy(p)},
              'artifacts': [{**item, 'revision': revision} for item in pins]}
    entries = {item['path']: item for item in result['artifacts']}
    adapter = PlasticityResponseFieldsAdapter()
    def resources(policy):
        return {role: (_load(output, spec['path'].removeprefix('simulation/'), spec['maximum_bytes']),
                       entries[spec['path']]) for role, spec in policy.items()}
    headers = resources(adapter.field_response_resources(result))
    fields = adapter.display_response_fields(result, None, headers)
    return adapter, result, fields, resources, headers, digest


def catalog(backend, outcome, output):
    if (backend in MATERIALS and outcome.get('solver_status') == 'COMPLETED' and
            outcome.get('status') == 'REJECTED' and outcome.get('converged') is False):
        _need(_load(output, 'analysis_raw.json') == outcome, 'Material rejected outcome differs from retained bytes')
        raw = _load(output, 'native_raw.json')
        if 'native_rejection' in raw:
            _need(outcome.get('provenance', {}).get('adapter') == backend and
                  any(check.get('code') == 'reliable_integrations' and check.get('status') == 'FAIL'
                      for check in outcome.get('checks', [])), 'Material partial rejection receipt differs')
            # A failed/unreliable increment intentionally has no completed
            # response history. Keep its outcome and original partial artifacts.
            return {}
    if backend in MATERIALS:
        channels, digest = _maxwell_context(outcome, output) if backend == MAXWELL else _elastic_context(backend, outcome, output)
        return {channel['id']: _channel_descriptor(channel, backend, digest) for channel in channels}
    adapter, result, fields, resources, headers, digest = _j2_context(outcome, output)
    channels = adapter.response_history_channels(result, None, resources(adapter.history_response_resources(result)))
    catalog = {channel['id']: _channel_descriptor(channel, J2, digest) for channel in channels}
    for mesh in fields['meshes']:
        for component in mesh['components']:
            key = f"j2.mesh{mesh['mesh_index']}.{component}"
            nodal = component.startswith(('DEPL.', 'REAC_NODA.'))
            unit = 'mm' if component.startswith('DEPL.') else 'N' if nodal else '1' if component == 'VARI_ELGA.V1' else 'MPa'
            catalog[key] = {'kind': 'series', 'unit': unit, 'component': component, 'reduction': 'none',
                            'quantity': 'displacement' if unit == 'mm' else 'nodal_reaction' if unit == 'N' else
                            'equivalent_plastic_strain' if unit == '1' else 'stress',
                            'location': 'exact native node' if nodal else 'exact native Gauss point',
                            'coordinate_frame': mesh['coordinate_frame'], 'coordinate_unit': 'mm',
                            'axes': [{'name': 'time', 'unit': 's', 'semantics': 'NATIVE_INST_DECLARED_QUASI_STATIC_HISTORY_SECONDS'}],
                            'initial_state': mesh['initial_state'], 'mesh_index': mesh['mesh_index'],
                            'selector_template': key + ('@<node_id>' if nodal else '@<element_id>:<point>:<subpoint>'),
                            'node_ids': mesh['node_ids'] if nodal else [], 'gauss_ids': [] if nodal else mesh['gauss_ids'],
                            'source': {'backend': J2, 'artifact': mesh['artifact'], 'sha256': digest,
                                       'parsed_sha256': mesh['sha256'], 'model_revision': fields['model_revision'],
                                       'value_origin': 'NATIVE_COMPONENT'},
                            'limitations': fields['limitations'],
                            'qualification': {'physical': 'UNKNOWN', 'decision': 'NOT_RELEASED'}}
            if not nodal:
                catalog[key]['selectors'] = [
                    {'label': f"Element {point['element_id']} / point {point['point']} / subpoint {point['subpoint']}",
                     'selector': f"{key}@{point['element_id']}:{point['point']}:{point['subpoint']}"}
                    for point in mesh['gauss_ids'][:256]]
                catalog[key]['selector_count'] = len(mesh['gauss_ids'])
                catalog[key]['selectors_truncated'] = len(mesh['gauss_ids']) > 256
    return catalog


def read(backend, outcome, output, selector, descriptors):
    """Return (descriptor, values, times) for the shared bounded-slice reader."""
    _need(isinstance(selector, str), 'Native response selector must be a declared channel string')
    if backend in MATERIALS:
        _need(selector in descriptors, 'Unknown retained material channel')
        channels, digest = _maxwell_context(outcome, output) if backend == MAXWELL else _elastic_context(backend, outcome, output)
        _need(digest == descriptors[selector]['source']['sha256'], 'Retained material artifacts changed during selection')
        channel = next(channel for channel in channels if channel['id'] == selector)
        return deepcopy(descriptors[selector]), channel['values'], channel['axis']['values']
    adapter, result, fields, resources, headers, digest = _j2_context(outcome, output)
    name, separator, identity = selector.partition('@')
    _need(name in descriptors, 'Unknown retained J2 channel')
    _need(digest == descriptors[name]['source']['sha256'], 'Retained J2 artifacts changed during selection')
    if not separator:
        channels = adapter.response_history_channels(result, None, resources(adapter.history_response_resources(result)))
        _need(any(channel['id'] == name for channel in channels), 'J2 field channel requires exact native identity')
        channel = next(channel for channel in channels if channel['id'] == name)
        return deepcopy(descriptors[name]), channel['values'], channel['axis']['values']
    descriptor = deepcopy(descriptors[name])
    _need('mesh_index' in descriptor, 'J2 history channel does not accept field IDs')
    mesh = fields['meshes'][descriptor['mesh_index']]
    nodal = descriptor['component'].startswith(('DEPL.', 'REAC_NODA.'))
    parts = identity.split(':')
    _need(len(parts) == (1 if nodal else 3) and all(re.fullmatch('[1-9][0-9]*', part) for part in parts),
          'J2 selector requires exact positive native node or element:point:subpoint IDs')
    ids = [int(part) for part in parts]
    selection = {'kind': 'fe_nodal' if nodal else 'fe_gauss', 'artifact': mesh['artifact'], 'sha256': mesh['sha256'],
                 'model_revision': fields['model_revision'], 'mesh_index': mesh['mesh_index'], 'time_index': 0,
                 'component': descriptor['component']}
    selection.update({'node_id': ids[0]} if nodal else dict(zip(('element_id', 'point', 'subpoint'), ids)))
    selected_resources = {**headers, **resources(adapter.field_selection_resources(result, selection, headers))}
    values, sources = [], []
    for index in range(len(mesh['times_s'])):
        item = adapter.select_response_fields(result, None, selected_resources, {**selection, 'time_index': index})
        values.append(item['value'])
        sources.append(item['source_field'])
    descriptor['source'].update(selector=selector, exact_selection=selection, sample_sources=sources)
    descriptor['location'] = sources[0]['location']
    descriptor['measure'] = sources[0]['measure']
    descriptor['coordinates'] = sources[0]['coordinates_mm']
    descriptor['coordinate_system'] = sources[0]['coordinate_frame']
    descriptor.pop('node_ids', None)
    descriptor.pop('gauss_ids', None)
    descriptor.pop('selector_template', None)
    return descriptor, values, mesh['times_s']
