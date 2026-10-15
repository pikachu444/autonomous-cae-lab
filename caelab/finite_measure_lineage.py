"""Typed nonlinear nodes inside Data's existing sample DAG.

NONLINEAR_EXACT means an exactly replayable formula and raw dependency set,
NOT a linear coefficient or an uncertainty derivative. No affine weight is
fabricated for ln(lambda), F/A or P*lambda/J.
"""
from __future__ import annotations
from copy import deepcopy
import math
from .storage import canonical_hash
from .finite_measure import (SCHEMA, OPERATION, FRAME, STRAIN_MEASURES,
                            active_roles, evaluate_row, validate_definition)

EXACT = 'NONLINEAR_EXACT'


def output_metadata(spec):
    return {'unit': spec['unit'], 'measure': spec['output'], 'component': spec['axis'] * 2,
        'frame': FRAME, 'location': 'material_point', 'reduction': 'none',
        'extensions': {'finite_measure': {'schema': SCHEMA, 'payload': deepcopy(spec)}}}


def apply(channels, op, recipe_hash):
    from . import data_processing_lineage as lineage
    spec = validate_definition(op['settings'])
    roles = active_roles(spec)
    role_channels = {}
    for role in roles:
        name = spec['channels'].get(role)
        if name not in channels:
            raise ValueError(role + ': 동일한 보존 import의 보조 채널을 선택하세요.')
        candidate = channels[name]
        lineage.verify_channel(candidate)
        if candidate.get('status') != 'READY':
            raise ValueError(role + ': 선행 처리 실패를 먼저 수정하세요.')
        role_channels[role] = candidate
    primary = 'load' if spec['output'] not in STRAIN_MEASURES else 'deformation' if 'deformation' in role_channels else 'Fxx'
    parent = role_channels[primary]
    if spec['channels'][primary] != op['input']:
        raise ValueError('연산의 주 입력과 선택한 물리 채널이 다릅니다.')
    for role, channel in role_channels.items():
        if (channel['source'] != parent['source'] or channel['target_grid'] != parent['target_grid']
                or channel['axis'] != parent['axis']
                or [s['coordinate_sample_id'] for s in channel['samples']] !=
                   [s['coordinate_sample_id'] for s in parent['samples']]):
            raise ValueError(role + ': 원 source/sample/time/grid가 다릅니다. 시간값만으로 join하지 않습니다.')
    output = deepcopy(parent)
    output.update(name=op['output'], metadata=output_metadata(spec), status='READY')
    output['recipe_refs'] = list(dict.fromkeys([r for c in role_channels.values() for r in c['recipe_refs']] + [recipe_hash]))
    channel_id = 'H' + canonical_hash([[(r, c['response_channel_id']) for r, c in role_channels.items()], recipe_hash, op])[:40]
    output['response_channel_id'] = channel_id
    nodes = {}
    for channel in role_channels.values():
        for sid, node in channel['lineage']['nodes'].items():
            if sid in nodes and nodes[sid] != node:
                raise ValueError('동일 sample ID의 원 DAG 내용이 다릅니다.')
            nodes[sid] = deepcopy(node)
    for i, sample in enumerate(output['samples']):
        operands, references, edges, footprint = {}, {}, [], []
        for role, channel in role_channels.items():
            sid = channel['samples'][i]['sample_id']
            operands[role] = {'value': channel['values'][i], 'metadata': deepcopy(channel['metadata'])}
            references[role] = {'sample_id': sid, 'metadata': deepcopy(channel['metadata']),
                                'response_channel_id': channel['response_channel_id']}
            if sid not in footprint:
                footprint.append(sid)
                edges.append({'sample_id': sid, 'coefficient': None, 'coefficient_status': EXACT,
                              'input_value': channel['values'][i]})
        value, audit, reason = None, None, ''
        valid = all(c['operation_valid'][i] for c in role_channels.values())
        if not valid:
            reason = '; '.join(r + ': ' + (c['operation_reasons'][i] or '선행 연산 무효')
                               for r, c in role_channels.items() if not c['operation_valid'][i])
        else:
            try:
                value, audit = evaluate_row(spec, operands)
            except (ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError) as error:
                reason, valid = str(error), False
        output['values'][i] = value
        output['operation_valid'][i] = valid
        output['operation_reasons'][i] = reason
        for flag, why in (('quality_valid', 'quality_reasons'), ('calculation_valid', 'calculation_reasons')):
            output[flag][i] = all(c[flag][i] for c in role_channels.values())
            output[why][i] = '; '.join(r+': '+c[why][i] for r, c in role_channels.items() if not c[flag][i])
        # Display choices never determine validity; retain the primary display mask.
        output['break_before'][i] = any(c.get('break_before', [False]*len(output['samples']))[i] for c in role_channels.values())
        rows = sorted({r for c in role_channels.values() for r in c['samples'][i]['source_rows']})
        validity_rows = sorted({r for c in role_channels.values() for r in c['samples'][i].get('validity_source_rows', c['samples'][i]['source_rows'])})
        node = {'kind': 'operation', 'stage': {'id': op['id'], 'operation': OPERATION,
                    'settings': deepcopy(spec), 'recipe_sha256': recipe_hash,
                    'input_channel_id': parent['response_channel_id']},
            'physical_metadata': deepcopy(output['metadata']), 'response_channel_id': channel_id,
            'coordinate_sample_id': sample['coordinate_sample_id'], 'inputs': edges,
            'bias': None, 'coefficient_status': EXACT, 'coefficient_basis': 'EXACT_NONLINEAR_RELATION_NOT_AFFINE_OR_DERIVATIVE',
            'value': value, 'operation_valid': valid, 'validity_inputs': footprint,
            'nonlinear_relation': {'schema': SCHEMA, 'operands': references, 'audit': audit},
            'not_computed_reason': reason,
            'validity_policy': 'ALL_EXACT_SOURCE_SAMPLE_TIME_OPERANDS_NO_GAP_BRIDGING'}
        sid = 'P' + canonical_hash([channel_id, i, node])[:40]
        nodes[sid] = node
        sample.update(sample_id=sid, contributors=deepcopy(edges), source_rows=rows,
                      validity_source_rows=validity_rows, import_index=None)
    output['lineage'] = {'format': lineage.FORMAT, 'nodes': nodes}
    output['lineage_sha256'] = canonical_hash(output['lineage'])
    lineage.verify_channel(output)
    return output


def verify_node(node, nodes, support):
    """Called by the original DAG verifier, including on cold retained reads."""
    spec = validate_definition(node['stage']['settings'])
    relation = node.get('nonlinear_relation', {})
    if (relation.get('schema') != SCHEMA or set(relation) != {'schema', 'operands', 'audit'}
            or node.get('coefficient_status') != EXACT or node.get('bias') is not None
            or node.get('physical_metadata') != output_metadata(spec)):
        raise ValueError('유한변환의 typed nonlinear 관계/측도 선언이 바뀌었습니다.')
    refs = relation['operands']
    if set(refs) != set(active_roles(spec)):
        raise ValueError('비선형 식의 원 입력이 누락되거나 바뀌었습니다.')
    footprints = node['validity_inputs']
    ids = list(dict.fromkeys(refs[role]['sample_id'] for role in active_roles(spec)))
    if ids != footprints or len(node['inputs']) != len(ids):
        raise ValueError('비선형 값 기여와 품질/계산 footprint가 다릅니다.')
    operands = {}
    for role, ref in refs.items():
        parent = nodes[ref['sample_id']]
        if (set(ref) != {'sample_id', 'metadata', 'response_channel_id'}
                or parent.get('coordinate_sample_id') != node['coordinate_sample_id']
                or parent.get('response_channel_id') != ref['response_channel_id']
                or parent.get('physical_metadata') != ref['metadata']):
            raise ValueError('보조 원행/좌표/물리 메타데이터가 실제 입력 DAG와 다릅니다. 원 import에서 다시 처리하세요.')
        operands[role] = {'value': parent['value'], 'metadata': ref['metadata']}
    for edge, sid in zip(node['inputs'], ids):
        if edge != {'sample_id': sid, 'coefficient': None, 'coefficient_status': EXACT, 'input_value': nodes[sid]['value']}:
            raise ValueError('비선형 기여를 선형 계수로 바꾸거나 원값을 변경할 수 없습니다.')
    all_valid = all(s[2] for s in support)
    try:
        expected, audit = evaluate_row(spec, operands)
    except (ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError):
        expected, audit, all_valid = None, None, False
    if node.get('operation_valid') is not all_valid:
        raise ValueError('유한변환 operation validity가 실제 domain/선행 결과와 다릅니다.')
    if all_valid:
        if node['value'] != expected or relation['audit'] != audit:
            raise ValueError('보존된 유한변환 값/근거가 실제 비선형 식과 다릅니다.')
    elif node.get('value') is not None or not node.get('not_computed_reason'):
        raise ValueError('무효 원행의 값과 실패 이유를 보존해야 합니다.')


def dependency_trace(node, parents):
    """Compose raw dependency identity, never numerical covariance coefficients."""
    terms = {}
    statuses = {node.get('coefficient_status'), *(p['coefficient_status'] for p in parents)}
    status = EXACT if statuses <= {'KNOWN', EXACT} else 'UNKNOWN'
    for parent in parents:
        for key, term in parent['terms'].items():
            terms[key] = {**deepcopy(term), 'coefficient': None, 'coefficient_status': status}
    return {'terms': terms, 'bias': None, 'coefficient_status': status}
