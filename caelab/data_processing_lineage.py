"""Sparse, signed processing lineage and channel-independent frozen grid IDs.

The DAG records value contributors separately from validity footprints. It is
not an uncertainty/covariance engine. Coefficients are conditional on the frozen
axis: selecting a nearest neighbor is not differentiated w.r.t. the coordinates.
"""
from __future__ import annotations
from copy import deepcopy
import math
import numpy as np
from .storage import canonical_hash

FORMAT = 'caelab.sample-lineage/2'
SOURCE_KEYS = ('document_id', 'job_id', 'input_revision', 'input_sha256', 'source_sha256')


def plain(value):
    if isinstance(value, np.ndarray): return plain(value.tolist())
    if isinstance(value, np.generic): return plain(value.item())
    if isinstance(value, dict): return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [plain(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value): return None
    return value


def grid_identity(source, axis, *, domain, raw_rows=None):
    """Same input + coordinate grid, independent of response/recipe/operation ID."""
    descriptor = {'format': 'caelab.target-grid/1', 'domain': domain,
        'source': {k: source[k] for k in SOURCE_KEYS},
        'axis_name': axis['name'], 'axis_unit': axis['unit'], 'values': plain(axis['values'])}
    if raw_rows is not None: descriptor['raw_rows'] = list(raw_rows)
    descriptor['grid_id'] = 'G' + canonical_hash(descriptor)[:40]
    descriptor['coordinate_sample_ids'] = ['X' + canonical_hash([descriptor['grid_id'], i, v])[:40]
                                           for i, v in enumerate(descriptor['values'])]
    return descriptor


def initialize(channel, response):
    source = channel['source']; column = channel['source_column']
    mapping = deepcopy(response.get('mapping', {}))
    channel_id = 'H' + canonical_hash([source, column, mapping, channel['metadata']])[:40]
    channel['response_channel_id'] = channel_id
    channel['sample_domain'] = 'raw-row-v1'
    grid = grid_identity(source, channel['axis'], domain='raw',
                         raw_rows=[s['anchor_row'] for s in channel['samples']])
    channel['target_grid'] = grid
    nodes = {}
    raw = response.get('raw_samples') or {}
    raw_values = raw.get('value')
    scale, bias = float(mapping.get('scale', 1.)), float(mapping.get('offset', 0.))
    if 'calibration' in mapping:
        from .experiment_calibration import factor
        c = mapping['calibration']
        scale = c['a'] * factor(c['input_unit'], c['coefficient_input_unit'])
        bias = c['b'] - c['a'] * c['x0'] * factor(c['x0_unit'], c['coefficient_input_unit'])
    for i, sample in enumerate(channel['samples']):
        raw_ref = {**deepcopy(source), 'column': column,
            'column_identity': response.get('source_column_identity', column),
            'source_row': sample['anchor_row']}
        raw_id = 'R' + canonical_hash(raw_ref)[:40]
        sample['sample_id'] = 'I' + canonical_hash([channel_id, sample['anchor_row']])[:40]
        raw_value = plain(raw_values[i]) if raw_values is not None else None
        nodes[raw_id] = {'kind': 'raw', 'raw_ref': raw_ref, 'value': raw_value,
            'value_known': raw_values is not None and raw_value is not None,
            'quality_valid': channel['quality_valid'][i],
            'quality_reason': channel['quality_reasons'][i]}
        edge = {'sample_id': raw_id, 'coefficient': scale, 'coefficient_status': 'KNOWN',
                'input_value': raw_value}
        nodes[sample['sample_id']] = {'kind': 'operation',
            'stage': {'operation': 'import_mapping', 'mapping': mapping, 'source': deepcopy(source)},
            'response_channel_id': channel_id, 'coordinate_sample_id': grid['coordinate_sample_ids'][i],
            'inputs': [edge] if scale != 0 else [], 'bias': bias,
            'coefficient_status': 'KNOWN', 'value': channel['values'][i],
            'validity_inputs': [raw_id], 'operation_valid': channel['operation_valid'][i],
            'coefficient_basis': 'affine_import_of_original_raw_value'}
        sample.update(coordinate_sample_id=grid['coordinate_sample_ids'][i],
            contributors=deepcopy(nodes[sample['sample_id']]['inputs']),
            validity_source_rows=list(sample['source_rows']))
    channel['lineage'] = {'format': FORMAT, 'nodes': nodes}
    channel['lineage_sha256'] = canonical_hash(channel['lineage'])
    return channel


def stamp(output, parent, op, recipe_hash, stencils, biases, footprints):
    count = len(output['samples'])
    blocked = output.get('status') == 'BLOCKED'
    if blocked:
        # The stage was not executed. Its declared input channel is retained,
        # but no fabricated identity/equal-weight value contribution is emitted.
        stencils, footprints = [[] for _ in range(count)], [[i] for i in range(count)]
    if stencils is None: stencils = [[(i, 1.)] for i in range(count)]
    if biases is None: biases = [0.] * count
    if footprints is None: footprints = [[j for j, _ in row] for row in stencils]
    if len(stencils) != count or len(biases) != count or len(footprints) != count:
        raise ValueError('Processing stencil length differs from output grid')
    resampled = op['operation'] == 'resample' and not blocked
    if resampled:
        domain = 'derived-grid-v2'
        grid = grid_identity(parent['source'], output['axis'], domain='resampled')
    else:
        domain = parent.get('sample_domain', 'raw-row-v1')
        grid = deepcopy(parent['target_grid'])
        if output['axis'] != parent['axis']:
            grid = grid_identity(parent['source'], output['axis'],
                domain='resampled' if domain == 'derived-grid-v2' else 'raw',
                raw_rows=None if domain == 'derived-grid-v2' else [s['anchor_row'] for s in output['samples']])
    output.update(sample_domain=domain, target_grid=grid)
    channel_id = 'H' + canonical_hash([parent['response_channel_id'], recipe_hash, op])[:40]
    output['response_channel_id'] = channel_id
    nodes = deepcopy(parent['lineage']['nodes'])
    stage = {'id': op['id'], 'operation': op['operation'], 'settings': deepcopy(op['settings']),
        'recipe_sha256': recipe_hash, 'input_channel_id': parent['response_channel_id']}
    for i, sample in enumerate(output['samples']):
        combined = {}
        for j, coefficient in stencils[i]:
            if type(j) is not int or not 0 <= j < len(parent['samples']):
                raise ValueError('Lineage references a missing input sample')
            combined[j] = combined.get(j, 0.) + float(coefficient)
        edges = [{'sample_id': parent['samples'][j]['sample_id'], 'coefficient': weight,
                  'coefficient_status': 'KNOWN', 'input_value': parent['values'][j]}
                 for j, weight in sorted(combined.items()) if weight != 0.]
        footprint_ids = [parent['samples'][int(j)]['sample_id'] for j in sorted(set(footprints[i]))]
        value_rows = sorted({r for j, w in combined.items() if w != 0 for r in parent['samples'][j]['source_rows']})
        validity_rows = sorted({r for j in footprints[i] for r in parent['samples'][int(j)].get('validity_source_rows', parent['samples'][int(j)]['source_rows'])})
        if max(len(value_rows), len(validity_rows)) > 4096:
            raise ValueError('Operation dependency footprint exceeds the explicit 4096-row limit')
        # No extrapolated/blocked output is represented as a computed value.
        known = bool(output['operation_valid'][i])
        node = {'kind': 'operation', 'stage': stage, 'response_channel_id': channel_id,
            'coordinate_sample_id': grid['coordinate_sample_ids'][i], 'inputs': edges,
            'bias': None if blocked else float(biases[i]), 'coefficient_status': 'KNOWN' if known else 'NOT_APPLICABLE',
            'value': output['values'][i], 'operation_valid': known,
            'validity_inputs': footprint_ids,
            'coefficient_basis': 'NOT_EXECUTED' if blocked else 'linear_in_values_conditional_on_frozen_axis',
            'coordinate_derivative': 'NOT_APPLICABLE',
            'validity_policy': 'ALL_FOOTPRINT_INPUTS_VALID_NO_GAP_BRIDGING'}
        if not known:
            node['not_computed_reason'] = output['operation_reasons'][i]
        sid = 'P' + canonical_hash([channel_id, i, node])[:40]
        nodes[sid] = node
        sample.update(sample_id=sid, coordinate_sample_id=grid['coordinate_sample_ids'][i],
                      contributors=deepcopy(edges), source_rows=value_rows,
                      validity_source_rows=validity_rows, import_index=None)
    output['lineage'] = {'format': FORMAT, 'nodes': nodes}
    output['lineage_sha256'] = canonical_hash(output['lineage'])
    return output


def trace_sample(channel, sample_id, *, cache=None):
    """Compose the sparse DAG to raw-cell signed coefficients, not equal weights."""
    nodes = channel['lineage']['nodes']
    cache = {} if cache is None else cache
    visiting = set()
    def visit(sid):
        if sid in cache: return cache[sid]
        if sid in visiting or sid not in nodes:
            raise ValueError('Processing lineage is cyclic or has an unresolved input sample')
        visiting.add(sid)
        node = nodes[sid]
        if node['kind'] == 'raw':
            key = canonical_hash(node['raw_ref'])
            result = {'terms': {key: {'raw_ref': deepcopy(node['raw_ref']), 'coefficient': 1.,
                                      'raw_value': node['value'], 'coefficient_status': 'KNOWN'}},
                      'bias': 0., 'coefficient_status': 'KNOWN'}
        else:
            terms, bias = {}, node['bias']
            status = node['coefficient_status']
            for edge in node['inputs']:
                parent = visit(edge['sample_id']); w = edge['coefficient']
                if edge['coefficient_status'] != 'KNOWN' or parent['coefficient_status'] != 'KNOWN':
                    status = 'UNKNOWN'
                bias += w * parent['bias']
                for key, term in parent['terms'].items():
                    if key not in terms: terms[key] = {**deepcopy(term), 'coefficient': 0.}
                    terms[key]['coefficient'] += w * term['coefficient']
            result = {'terms': {k: v for k, v in terms.items() if v['coefficient'] != 0.},
                      'bias': bias, 'coefficient_status': status}
        visiting.remove(sid)
        cache[sid] = result
        return result
    r = visit(sample_id)
    return {**{k: deepcopy(v) for k, v in r.items() if k != 'terms'},
            'terms': [deepcopy(v) for _, v in sorted(r['terms'].items())],
            'sample_id': sample_id}


def raw_key(reference):
    # Different import IDs or recipes cannot make the same measured cell independent.
    return (reference['source_sha256'], str(reference.get('column_identity', reference['column'])),
            reference['source_row'])


def verify_channel(channel):
    if channel.get('lineage', {}).get('format') != FORMAT:
        raise ValueError('Explicit derived samples require retained v2 lineage')
    if canonical_hash(channel['lineage']) != channel.get('lineage_sha256'):
        raise ValueError('Processing lineage hash differs from its frozen channel')
    grid = channel['target_grid']
    rebuilt = grid_identity(grid['source'], {'name': grid['axis_name'], 'unit': grid['axis_unit'], 'values': grid['values']},
                            domain=grid['domain'], raw_rows=grid.get('raw_rows'))
    if rebuilt != grid or len(channel['samples']) != len(grid['coordinate_sample_ids']):
        raise ValueError('Target-grid identity differs from frozen coordinates')
    nodes = channel['lineage']['nodes']
    ids = [s['sample_id'] for s in channel['samples']]
    if len(set(ids)) != len(ids): raise ValueError('Duplicate derived sample ID')
    for i, s in enumerate(channel['samples']):
        node = nodes.get(s['sample_id'], {})
        if (s['coordinate_sample_id'] != grid['coordinate_sample_ids'][i]
                or node.get('coordinate_sample_id') != s['coordinate_sample_id']
                or node.get('response_channel_id') != channel['response_channel_id']
                or node.get('value') != channel['values'][i]):
            raise ValueError('Derived sample, response channel or coordinate identity differs')
    return channel


def aligned_driver_indexes(observation, driver):
    """Join values on frozen coordinate IDs; NEVER fabricate integer raw rows."""
    if 'target_grid' not in observation and 'target_grid' not in driver:
        rows, drows = observation.get('source_rows', []), driver.get('source_rows', [])
        if not rows or len(set(rows)) != len(rows) or len(set(drows)) != len(drows):
            raise ValueError('측정 변형축의 원본 행 연결이 없거나 중복됩니다.')
    else:
        if ('target_grid' not in observation or 'target_grid' not in driver
                or observation['target_grid'] != driver['target_grid']):
            raise ValueError('Observation and driver must use the same frozen target grid')
        for response in (observation, driver):
            channel = verify_channel(response['processing_channel'])
            if any(response.get(k) != channel.get(k) for k in
                    ('target_grid', 'response_channel_id', 'sample_domain', 'lineage_sha256')):
                raise ValueError('Response identity differs from its frozen processing channel')
            ids = response.get('sample_ids', []); coordinates = response.get('coordinate_sample_ids', [])
            if (len(ids) != len(set(ids)) or len(coordinates) != len(ids)
                    or len(coordinates) != len(set(coordinates))):
                raise ValueError('Missing or duplicate response sample/coordinate IDs')
            if len(response.get('axes', [])) != 1 or len(response['axes'][0].get('values', [])) != len(ids):
                raise ValueError('Response axis length differs from its sample identities')
            by_id = {s['sample_id']: (i, s) for i, s in enumerate(channel['samples'])}
            if len(response.get('sample_ids', [])) != len(response['value']):
                raise ValueError('Response sample identities are missing')
            for k, sid in enumerate(response['sample_ids']):
                if sid not in by_id: raise ValueError('Response sample absent from its lineage')
                i, s = by_id[sid]
                if (s['coordinate_sample_id'] != response['coordinate_sample_ids'][k]
                        or channel['values'][i] != response['value'][k]
                        or channel['axis']['values'][i] != response['axes'][0]['values'][k]):
                    raise ValueError('Response values/coordinates differ from retained sample')
        rows, drows = observation['coordinate_sample_ids'], driver['coordinate_sample_ids']
    times, dtimes = observation['axes'][0]['values'], driver['axes'][0]['values']
    if len(rows) != len(observation['value']) or len(rows) != len(times) or len(drows) != len(dtimes) or len(drows) != len(driver['value']):
        raise ValueError('Observation/driver sample identity lengths differ')
    lookup = {r: (i, t) for i, (r, t) in enumerate(zip(drows, dtimes))}
    if any(r not in lookup or lookup[r][1] != t for r, t in zip(rows, times)):
        raise ValueError('관측과 측정 변형의 표본/시간이 다릅니다.')
    return [lookup[r][0] for r in rows]
