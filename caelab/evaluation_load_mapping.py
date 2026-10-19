"""Conservative nodal load hooks for the existing sequential Evaluation owner."""
from copy import deepcopy
from pathlib import Path
import numpy as np

from . import conservative_load_transfer as transfer
from .storage import canonical_hash,save_json
from .evaluation import file_hash

ROW_KEYS={'id','from_stage','output','to_stage','input','mapping','lag','options'}


def validate_options(options):
    if not isinstance(options,dict) or set(options)!={'moment_origin_mm','target'}:
        raise ValueError('Choose a global moment origin and explicit receiver boundary')
    origin=np.asarray(options['moment_origin_mm'],dtype=float)
    if origin.shape!=(3,) or not np.isfinite(origin).all():
        raise ValueError('Moment origin requires finite XYZ coordinates in mm')
    # Declarations/compile never construct H. Only explicit preview/binding does.
    transfer.validate_target(options['target'])
    return deepcopy(options)


def validate_row(row,stage_ids):
    if not isinstance(row,dict) or set(row)!=ROW_KEYS or row.get('mapping')!=transfer.MAPPING:
        raise ValueError('Conservative load transfer requires an explicit complete declaration')
    if row['lag']!=0:raise ValueError('TR-F is a one-way current source transfer; feedback is not supported')
    validate_options(row['options'])


def compile_transfer(row,compiled):
    from .adapters.conservative_load import RECEIVER
    validate_options(row['options'])
    source=compiled[row['from_stage']]['ports']['outputs'].get(row['output'])
    target=compiled[row['to_stage']]['ports']['inputs'].get(row['input'])
    if not source or source.get('measure')!='support_reaction_on_source' or source.get('unit')!='N':
        raise ValueError('Select a verified source SPC reaction port, not contact stress or pair resultant')
    if (compiled[row['to_stage']]['model']['backend']!=RECEIVER or not target or
            transfer.MAPPING not in target.get('mappings',[]) or target.get('measure')!='applied_nodal_force'):
        raise ValueError('Select the C3D10 conservative nodal load receiver')
    for key,value in {'association':'POINTS','component':'VECTOR','frame':'global_cartesian',
                      'coordinate_units':'mm'}.items():
        if source.get(key)!=value or target.get(key)!=value:raise ValueError('Incompatible load port '+key)


def bind_transfer(row,model,source_set,run_result,iteration,output,stages):
    from .backends import get_backend
    options=validate_options(row['options']);receipt={}
    record={k:deepcopy(row[k]) for k in ('id','from_stage','to_stage','input','mapping')}
    record.update(iteration=iteration,source_iteration=iteration,status='VALIDATING',
                  receiver_dispatched_at_mapping=False,options=deepcopy(options))
    run_result['transfers'].append(record)
    try:
        upstream=source_set.get(row['from_stage'])
        if not upstream or upstream.get('execution_status')!='SUCCEEDED':
            raise ValueError('An unsuccessful source cannot supply a support reaction')
        attempts=[r for r in run_result['stages'] if r['stage_id']==row['from_stage'] and r['iteration']==iteration]
        if len(attempts)!=1 or attempts[0]['state']!='SUCCEEDED':
            raise ValueError('The source has no unique retained successful attempt')
        field=deepcopy(upstream['responses'][row['output']])
        reference={'stage':row['from_stage'],'output':row['output'],'attempt_id':attempts[0]['attempt_id'],
            'result_sha256':attempts[0]['result_sha256'],
            'source':deepcopy(next(s['source'] for s in stages if s['id']==row['from_stage']))}
        mapped,receipt=transfer.map_load(field,options['target'],moment_origin_mm=options['moment_origin_mm'])
        # Preserve the numerical receipt identity used by the actual receiver.
        # Owner/attempt provenance extends it without changing its core pointer.
        receipt.update(numerical_receipt_sha256=mapped['receipt_sha256'],source_refs=[reference],policy=deepcopy(options))
        settings=get_backend(model['backend']).bind_port(model['settings'],row['input'],mapped)
        receipt.update(receiver_bound_settings_sha256=canonical_hash(settings),
                       receiver_model_before_binding_sha256=canonical_hash(model))
        record.update(status='VALIDATED',source_response_sha256=canonical_hash(field),source_refs=[reference],
                      unit='N',association='POINTS',time=deepcopy(field['static']))
        return settings
    except (ValueError,KeyError,TypeError,IndexError) as error:
        if isinstance(error,transfer.TransferError):receipt=deepcopy(error.receipt)
        receipt.update(status='FAILED',mapping=transfer.MAPPING,error=str(error),policy=deepcopy(options))
        record.update(status='FAILED',error=str(error))
        raise
    finally:
        receipt['capture_sha256']=canonical_hash(receipt)
        path=Path(output)/'transfers'/(f'i{iteration:04d}-'+row['id']+'.json')
        path.parent.mkdir(parents=True,exist_ok=True);save_json(path,receipt)
        record.update(receipt_path=path.relative_to(output).as_posix(),receipt_sha256=file_hash(path))
