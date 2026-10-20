"""Read captured S1 mapping receipts and both meshes; zero mapping/solver calls."""
from copy import deepcopy
import math

from .evaluation import file_hash
from .storage import canonical_hash, load_json
from .research_workflows import result_folder, evaluation_stage_result
from .p1_temperature_transfer import original


def inspect_mapped(wb, document_id, job_id, result, declaration, record, frozen, progress, *, start, count, folder=None, read_stage=None):
    from .workbench import contained
    if folder is None:
        folder, _ = result_folder(wb, document_id, job_id)
    if read_stage is None:
        read_stage = lambda attempt, selection: evaluation_stage_result(wb, document_id, job_id, attempt, selection)
    targets = [r for r in progress['stages'] if r['stage_id'] == record['to_stage'] and r['iteration'] == record['iteration']]
    if len(targets) != 1:
        raise ValueError('수신 단계 기록이 모호합니다.')
    target = targets[0]
    receipt = {}
    if record.get('receipt_recorded'):
        path = contained(folder, record['receipt_path'])
        if path.is_symlink() or file_hash(path) != record['receipt_sha256']:
            raise ValueError('전달 원기록이 누락되거나 변경됐습니다.')
        receipt = load_json(path)
        if (receipt.get('capture_sha256') != original.digest({k: v for k, v in receipt.items() if k != 'capture_sha256'})
                or receipt.get('mapping') != declaration['mapping'] or receipt.get('policy') != declaration['options']
                or receipt.get('status') != record['status']):
            raise ValueError('전달 원기록의 hash/정의/상태가 다릅니다.')
    source_rows, source_attempts = [], []
    refs = receipt.get('source_refs', [])
    sources = []
    for index, snapshot in enumerate(declaration['options']['time']['sources']):
        matches = [r for r in progress['stages'] if r['stage_id'] == snapshot['stage'] and r['iteration'] == record['source_iteration']]
        if len(matches) > 1:
            raise ValueError('공급 snapshot의 실제 attempt가 모호합니다.')
        attempt = matches[0] if matches else None
        source_attempts.append(attempt)
        response, unavailable = None, None
        if attempt is None:
            unavailable = '공급 snapshot 실행 기록 없음'
        elif attempt['state'] != 'SUCCEEDED':
            unavailable = '공급 snapshot이 성공하지 않았습니다. 원 단계의 부분 결과/실패를 확인하세요.'
        else:
            # The exact stage reader verifies payloads. Never replace corrupt
            # bytes with cached receipt values or recalculate a missing field.
            catalog = read_stage(attempt['attempt_id'], {'metadata_only': True})
            if snapshot['output'] not in catalog.get('responses', {}):
                unavailable = '필수 snapshot 출력 없음'
            else:
                response = read_stage(attempt['attempt_id'],
                                                   {'responses': [snapshot['output']]})['responses'][snapshot['output']]
                if index < len(refs):
                    ref = refs[index]
                    expected_source = next(s['source'] for s in frozen['stages'] if s['id'] == snapshot['stage'])
                    if (ref['stage'] != snapshot['stage'] or ref['output'] != snapshot['output']
                            or ref['attempt_id'] != attempt['attempt_id'] or ref['source'] != expected_source
                            or ref['result_sha256'] != attempt['result_sha256']
                            or canonical_hash(response) != ref['source_response_sha256']):
                        raise ValueError('공급 장과 동결된 snapshot/source ref가 다릅니다.')
                stored = receipt.get('sources', [])
                if index < len(stored) and canonical_hash(stored[index]) != canonical_hash(response):
                    raise ValueError('전달에 사용한 공급값과 실제 보존 원결과가 다릅니다.')
        sources.append(response)
        rows = []
        if isinstance(response, dict):
            ids, xyz, values = (response.get(k) for k in ('node_ids', 'coordinates', 'value'))
            if not all(isinstance(v, list) for v in (ids, xyz, values)) or len(ids) != len(xyz) or len(ids) != len(values):
                unavailable = '공급 장의 절점/좌표/값 배열 불일치; 원 결과를 확인하세요.'
            else:
                mask = response.get('valid_mask')
                for j in range(start, min(start + count, len(ids))):
                    val = values[j]
                    valid = type(val) in (float, int) and math.isfinite(val)
                    rows.append({'node': ids[j], 'coordinates': deepcopy(xyz[j]), 'value': deepcopy(val),
                                 'mask': mask[j] if isinstance(mask, list) and j < len(mask) else None,
                                 'finite': valid})
        source_rows.append({'snapshot_index': index, 'stage': snapshot['stage'], 'output': snapshot['output'],
                            'name': next(s['name'] for s in frozen['stages'] if s['id'] == snapshot['stage']),
                            'reference': deepcopy(refs[index]) if index < len(refs) else None,
                            'metadata': _metadata(response), 'rows': rows,
                            'total': len(response.get('node_ids', [])) if isinstance(response, dict) else 0,
                            'unavailable': unavailable})
    mapped = receipt.get('mapped_field')
    received, settings = None, {}
    unavailable = receipt.get('error') or target.get('error')
    if target.get('dispatched') and target.get('state') in ('SUCCEEDED', 'REJECTED', 'FAILED', 'CANCELLED'):
        try:
            downstream = read_stage(target['attempt_id'],
                                                {'responses': [], 'include_settings': True})
            settings = downstream.get('settings', {})
            received = settings.get(declaration['input'])
            hex8 = mapped is not None and mapped.get('basis') == 'Hex8_nodal_samples'
            if hex8:
                history = settings.get('thermal_regions', {})
                slots = history.get('temperature', {})
                names = ['temperature_' + str(i) for i in range(len(history.get('time_s', [])))]
                if declaration['input'] not in names:
                    raise ValueError('보존된 3D 온도 이력의 수신 슬롯이 다릅니다.')
                slot = names.index(declaration['input'])
                if (history['time_s'][slot] != mapped['time'] or history.get('time_origin') != mapped['time_origin']
                        or canonical_hash(settings.get('mesh')) != mapped.get('receiver_mesh_sha256')):
                    raise ValueError('보존된 3D 수신 메시·이력·적용 입력이 전달 기록과 다릅니다.')
                matching = [source for source in slots.get('source', [])
                            if source.get('time_s') == mapped['time'] and
                            source.get('capture_sha256') == mapped['capture_sha256'] and
                            source.get('receiver_mesh_sha256') == mapped['receiver_mesh_sha256'] and
                            source.get('source_refs') == mapped.get('source_refs')]
                values = slots.get('values')
                if not isinstance(values,list) or slot >= len(values):
                    raise ValueError('보존된 3D 온도 슬롯의 절점 값이 없습니다.')
                value = values[slot]
                if len(matching) != 1 or canonical_hash(value) != canonical_hash(mapped['value']):
                    raise ValueError('보존된 3D 슬롯의 실제 절점 온도·원본 참조가 다릅니다.')
                received = {**deepcopy(mapped), 'value':deepcopy(value)}
            if mapped is not None and (canonical_hash(received) != canonical_hash(mapped)
                    or (not hex8 and canonical_hash(settings) != receipt['receiver_bound_settings_sha256'])):
                raise ValueError('보존된 수신 입력과 실제 전달 계산값이 다릅니다.')
        except ValueError as error:
            if str(error) != 'This stage has no completed retained result; inspect progress/failure':
                raise
            unavailable = unavailable or '수신 단계의 완료 결과가 없습니다. 부분 기록을 확인하세요.'
    elif mapped is not None:
        unavailable = unavailable or '전달은 검증됐지만 수신 계산은 제출되지 않았습니다.'
    geometry = receipt.get('receiver_mesh', {})
    ids, coordinates = geometry.get('node_ids', []), geometry.get('coordinates', [])
    if len(ids) != len(coordinates):
        raise ValueError('보존 수신 메시의 절점/좌표 배열이 다릅니다.')
    rows = []
    for i in range(start, min(start + count, len(ids))):
        a = mapped['value'][i] if mapped is not None else None
        b = received['value'][i] if received is not None else None
        spatial = [deepcopy(s['rows'][i]) for s in receipt.get('spatial', [])]
        rows.append({'row': i, 'node': ids[i], 'coordinates': deepcopy(coordinates[i]), 'mapped': a,
                     # Compatibility alias; the S1 view explicitly labels this
                     # mapped value, never a node-aligned original source value.
                     'supplied': a, 'received': b, 'difference': b - a if a is not None and b is not None else None,
                     'required': True, 'available': a is not None and b is not None,
                     'valid_mask': mapped['valid_mask'][i] if mapped is not None else None,
                     'spatial_sources': spatial})
    metadata = _metadata(mapped)
    if mapped is None:
        metadata.update(unit=declaration['options']['target_unit'], quantity=declaration['options']['target_quantity'],
                        coordinate_units='m', mesh_sha256=geometry.get('mesh_sha256'))
    reference = receipt.get('temperature', {}).get('receiver_reference')
    total = max([len(ids)] + [s['total'] for s in source_rows])
    result.update(mapping_kind='p1_temperature', transfer=deepcopy(record) if receipt else None,
                  transfer_confirmation=record['status'], declaration=deepcopy(declaration),
                  source_attempt=source_attempts[0] if source_attempts else None, source_attempts=source_attempts,
                  target_attempt=target, source_snapshots=source_rows, metadata=metadata,
                  receiver_mesh=deepcopy(geometry), clock=deepcopy(receipt.get('clock')),
                  temperature=deepcopy(receipt.get('temperature')), rows=rows, receiver_rows=deepcopy(rows),
                  start=start, count=min(count, max(0, total - start)), total=total, receiver_total=len(ids),
                  metadata_differences=[], coverage_policy=('ALL_RECEIVER_HEX8_NODES_REQUIRED'
                      if mapped and mapped.get('basis') == 'Hex8_nodal_samples' else 'ALL_RECEIVER_P1_NODES_REQUIRED'),
                  coverage=deepcopy(receipt.get('coverage')), invalid_receiver_ids=receipt.get('invalid_receiver_ids', []),
                  native_mask=mapped.get('valid_mask') if mapped else None,
                  unavailable=unavailable, reference_temperature=reference['value'] if reference else None,
                  reference_temperature_unit='K' if reference else None,
                  exact_values_match=mapped is not None and received is not None and canonical_hash(mapped) == canonical_hash(received),
                  conservative=False, original_source_and_receiver_are_different_meshes=True)
    result['extrusion'] = deepcopy(receipt.get('extrusion'))
    # Do not call equal meshes different just because this policy was selected.
    result['original_source_and_receiver_are_different_meshes'] = bool(mapped and sources and all(
        isinstance(s, dict) and s.get('mesh_sha256') != mapped['mesh_sha256'] for s in sources))
    return result


def _metadata(response):
    keys = ('unit', 'quantity', 'component', 'association', 'basis', 'frame', 'measure',
            'coordinate_units', 'coordinate_frame', 'mesh_sha256', 'time', 'time_units', 'time_origin',
            'capture_sha256', 'snapshot_kind', 'temperature_reference')
    return {k: deepcopy(response.get(k)) for k in keys} if isinstance(response, dict) else {}
