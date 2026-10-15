"""S1 mapping hooks for the existing Evaluation compiler and sequential runner.

This module owns no queue, iteration loop, owner or result store. Its receipts
are immutable files of the existing evaluation attempt, including failed binds.
"""
from copy import deepcopy
from pathlib import Path

from . import p1_temperature_transfer as transfer
from .storage import canonical_hash, save_json
from .evaluation import file_hash

ROW_KEYS = {'id', 'from_stage', 'output', 'to_stage', 'input', 'mapping', 'lag'}


def validate_row(row, stage_ids):
    if not isinstance(row, dict):
        raise ValueError('Transfer must be an explicit object')
    if row.get('mapping') == 'exact_same_mesh':
        if set(row) != ROW_KEYS:
            raise ValueError('Exact transfer requires its original seven keys, without inferred options')
        return
    if row.get('mapping') != transfer.MAPPING or set(row) != ROW_KEYS | {'options'}:
        raise ValueError('Choose exact_same_mesh or an explicitly configured p1_temperature transfer')
    options = transfer.validate_options(row['options'])
    sources = options['time']['sources']
    if sources[0] != {'stage': row['from_stage'], 'output': row['output']}:
        raise ValueError('The first snapshot must be the transfer source/output, not an implicit replacement')
    for source in sources:
        if source['stage'] not in stage_ids:
            raise ValueError('A required snapshot refers to a missing stage')
        if row['lag'] == 0 and stage_ids.index(source['stage']) >= stage_ids.index(row['to_stage']):
            raise ValueError('Every required immediate snapshot must precede the receiving stage')


def compile_transfer(row, compiled):
    """Pure metadata compatibility; no numeric mapping, probe, solve or repair."""
    options = transfer.validate_options(row['options'])
    target = compiled[row['to_stage']]['ports']['inputs'].get(row['input'])
    if not target or transfer.MAPPING not in target.get('mappings', []):
        raise ValueError(row['id'] + ': receiving port does not advertise scalar P1 temperature mapping')
    if target.get('quantity') != options['target_quantity'] or target.get('unit') != options['target_unit']:
        raise ValueError(row['id'] + ': mapping quantity/unit must equal the explicit receiver port')
    for snapshot in options['time']['sources']:
        source = compiled[snapshot['stage']]['ports']['outputs'].get(snapshot['output'])
        if not source or source.get('quantity') != transfer.ABSOLUTE or source.get('unit') not in transfer.ABS_UNITS:
            raise ValueError(row['id'] + ': each source must advertise an absolute-temperature field')
        for key, value in {'kind': 'field', 'association': 'POINTS', 'component': 'scalar', 'location': 'node',
                           'measure': 'thermodynamic_temperature', 'frame': 'global_cartesian',
                           'coordinate_units': 'm', 'coordinate_frame': 'global_cartesian', 'basis': 'P1'}.items():
            if source.get(key) != value:
                raise ValueError(row['id'] + ': incompatible source ' + key)
        for key in ('kind', 'association', 'component', 'location', 'frame', 'coordinate_units', 'coordinate_frame', 'basis'):
            if target.get(key) != source.get(key):
                raise ValueError(row['id'] + ': incompatible receiver ' + key)
    if row['lag'] and target.get('required'):
        raise ValueError('The initial iteration needs an explicitly optional/seeded feedback port')


def bind_transfer(row, model, source_set, run_result, iteration, output, stages):
    """Called only from execute() before its existing receiver dispatch point."""
    from .backends import get_backend
    source_iteration = iteration - row['lag']
    record = {key: deepcopy(row[key]) for key in ('id', 'from_stage', 'to_stage', 'input', 'mapping')}
    record.update(iteration=iteration, source_iteration=source_iteration, status='VALIDATING',
                  options=deepcopy(row['options']), receiver_dispatched_at_mapping=False)
    fields, references, receipt = [], [], {}
    run_result['transfers'].append(record)
    try:
        for snapshot in row['options']['time']['sources']:
            upstream = source_set.get(snapshot['stage'])
            if upstream is None or upstream.get('execution_status') != 'SUCCEEDED':
                raise ValueError('A required saved snapshot is absent or its producer did not succeed')
            response = deepcopy(upstream.get('responses', {}).get(snapshot['output']))
            attempts = [s for s in run_result['stages'] if s['stage_id'] == snapshot['stage'] and s['iteration'] == source_iteration]
            if len(attempts) != 1 or attempts[0]['state'] != 'SUCCEEDED':
                raise ValueError('A required source snapshot has no unique successful retained attempt')
            source = next(s['source'] for s in stages if s['id'] == snapshot['stage'])
            references.append({'stage': snapshot['stage'], 'output': snapshot['output'],
                'iteration': source_iteration, 'attempt_id': attempts[0]['attempt_id'],
                'source': deepcopy(source), 'result_sha256': attempts[0]['result_sha256'],
                'source_response_sha256': canonical_hash(response),
                'capture_sha256': response.get('capture_sha256') if isinstance(response, dict) else None})
            fields.append(response)
        mapped, receipt = transfer.map_temperature(fields, model['settings'], row['options'], source_refs=references)
        # The receiver's own capability/clock/material binding remains final.
        settings = get_backend(model['backend']).bind_port(model['settings'], row['input'], mapped)
        receipt['receiver_bound_settings_sha256'] = canonical_hash(settings)
        receipt['receiver_model_before_binding_sha256'] = canonical_hash(model)
        receipt.pop('capture_sha256', None)
        receipt['capture_sha256'] = transfer.original.digest(receipt)
        record.update(status='VALIDATED', source_response_sha256=canonical_hash(fields[0]),
                      source_refs=references, unit=mapped['unit'], time=mapped['time'],
                      mesh_sha256=mapped['mesh_sha256'], association=mapped['association'])
        return settings
    except (ValueError, KeyError, TypeError, IndexError, ArithmeticError) as error:
        receipt = deepcopy(error.receipt) if isinstance(error, transfer.TransferError) else receipt
        receipt.pop('capture_sha256', None)
        receipt.update(schema='p1-temperature-receipt-v1', mapping=transfer.MAPPING, status='FAILED',
                       error=str(error), policy=deepcopy(row['options']), source_refs=deepcopy(references), conservative=False)
        receipt['capture_sha256'] = transfer.original.digest(receipt)
        record.update(status='FAILED', error=str(error), source_refs=deepcopy(references))
        raise
    finally:
        # Failure receipts use this same artifact boundary; no separate store.
        path = Path(output) / 'transfers' / (f'i{iteration:04d}-' + row['id'] + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        save_json(path, receipt)
        record.update(receipt_path=path.relative_to(output).as_posix(), receipt_sha256=file_hash(path))
