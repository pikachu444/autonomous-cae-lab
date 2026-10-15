"""Explicit readback jobs on the EXISTING Workbench/JobManager.

The new job is a derivation, never a replacement native execution. All native
identity in its retained result remains the original job; the readback job and
source execution receipt are separately pinned. No executable lookup exists.
"""
from copy import deepcopy
import json
from pathlib import Path

from .adapters.frozen_fem import _read
from .dynamic_result_store import file_pin, verify_pin, read_attempt
from .storage import check_id, save_json

OPERATION = 'dynamic.reprocess'


def request(workbench, source_job_id):
    """Prepare the exact currently selected source receipt; does not submit."""
    source_job_id = check_id(source_job_id)
    folder = workbench.root/'native'/source_job_id
    return prepare(workbench, {'source_job_id': source_job_id,
                              'source_record': file_pin(folder,folder/'contact_execution.json')})


def prepare(workbench, arguments):
    if not isinstance(arguments, dict) or set(arguments) != {'source_job_id','source_record'}:
        raise ValueError('Readback requires one original job and its exact execution record pin')
    source_id = check_id(arguments['source_job_id'])
    original = workbench.manager.status(source_id)
    if (original['state'] not in {'SUCCEEDED','FAILED','CANCELLED','INTERRUPTED','PARTIAL_FAILURE'}
            or original.get('cleanup_unconfirmed')):
        raise ValueError('Original native job is active or cleanup is unconfirmed')
    if original['operation'] != 'run' or original['arguments'].get('backend') != 'structure.calculix.contact':
        raise ValueError('Select an original managed structural run, not another derived attempt')
    folder = workbench.root/'native'/source_id
    pin = arguments['source_record']
    if set(pin) != {'relative','bytes','sha256'} or pin['relative'] != 'contact_execution.json':
        raise ValueError('Pin the original contact_execution.json, not a substitute result')
    record = json.loads(_read(verify_pin(folder,pin)))
    identity = record.get('job_identity') or {}
    if (record.get('job_id') != source_id or identity.get('id') != source_id or
            identity.get('request_hash') != original['request_hash'] or
            record.get('data_id') != original['arguments']['settings'].get('data_id') or
            record.get('input_origin') != original['arguments'].get('origin')):
        raise ValueError('Readback source is from a different job/input/request')
    return deepcopy(arguments)


def execute(workbench, arguments, identifier):
    from .dynamic_recovery import reprocess
    from .dynamic_locations import publish_job_inputs
    arguments = prepare(workbench, arguments)
    identifier = check_id(identifier)
    job = workbench.manager.status(identifier)
    if job['operation'] != OPERATION or job['arguments'] != arguments:
        raise ValueError('Readback execution differs from its owned JobManager request')
    original = workbench.manager.status(arguments['source_job_id'])
    source = workbench.root/'native'/arguments['source_job_id']
    output = workbench.root/'native'/identifier
    receipt = reprocess(source,output, expected_record=arguments['source_record'],
        readback_job={k: deepcopy(job.get(k)) for k in ('id','workspace_id','operation','request_hash')},
        original_job_state=original['state'])
    if receipt.get('dynamic_post_artifacts') and receipt.get('readback_status') == 'SUCCEEDED':
        try:
            publish_job_inputs(workbench,receipt,output,identifier,original['arguments'],
                               native_job_id=arguments['source_job_id'])
            receipt['post_registration'] = {'status': 'SUCCEEDED'}
        except (ValueError,OSError,KeyError,TypeError) as error:
            receipt['post_registration'] = {'status':'FAILED','message':str(error)}
            receipt['readback_status'] = 'FAILED'
        save_json(output/'contact_execution.json',receipt)
    verify_pin(source,arguments['source_record'])
    # JobManager's state describes THIS read operation. Native failure remains
    # explicit in source_execution_status and in the immutable retained result.
    state = receipt['readback_status']
    result = {'execution_status': state if state in ('SUCCEEDED','FAILED','CANCELLED') else 'FAILED',
        'operation': OPERATION, 'operation_kind':'READBACK_ONLY', 'responses':{},
        'solver_execution':'NOT_PERFORMED', 'source_execution_status':receipt['execution_status'],
        'source_job_id':arguments['source_job_id'], 'source_job_state':original['state'],
        'qualification':'UNKNOWN','decision':'NOT_RELEASED','engineering_valid':False,
        'retained_attempt': {'relative':'native/'+identifier,
            'record':file_pin(output,output/'contact_execution.json'),
            'dynamic_result':deepcopy(receipt.get('dynamic_result')),
            'snapshot_id':receipt['snapshot_id'], 'native_job_id':receipt.get('job_id')},
        'post_inputs':deepcopy(receipt.get('post_inputs',[])),
        'post_input':deepcopy(receipt.get('post_input')),
        'diagnostics': {'readback':deepcopy(receipt.get('diagnostics',{})),
                        'post_registration':deepcopy(receipt.get('post_registration'))}}
    return result


def open_result(workbench, identifier, *, metadata_only=False, verification='selected'):
    """Exact saved readback selection after a new owner starts; never reruns."""
    identifier = check_id(identifier)
    job = workbench.manager.status(identifier)
    if job['operation'] != OPERATION:
        raise ValueError('Select a retained readback job')
    result = workbench.manager.result(identifier, selection={'metadata_only':True})
    ref = result['retained_attempt']
    if ref['relative'] != 'native/'+identifier:
        raise ValueError('Readback result refers to a different artifact directory')
    folder = workbench.root/ref['relative']
    return read_attempt(folder,expected_record=ref['record'],expected_result=ref['dynamic_result'],
                        expected_job_id=ref['native_job_id'],expected_snapshot_id=ref['snapshot_id'],
                        metadata_only=metadata_only,verification=verification)


def verify_registration_job(workbench_root, job_id, bundle):
    """Permit ONLY an exact readback job to register its ORIGINAL native origin.

    Called by existing native registrar after copying/validating dependencies.
    The source execution receipt and JobManager request must agree; no replacement
    native job ID is written into the result to satisfy registration.
    """
    job_id = check_id(job_id)
    root = Path(workbench_root)
    job = json.loads(_read(root/'jobs'/(job_id+'.json')))
    if job.get('id') != job_id or job.get('operation') != OPERATION:
        raise ValueError('Dynamic input belongs to a different JobManager run')
    origin = bundle['origin']
    # Load bounded immutable index, not any native/frame payload.
    from .dynamic_result_store import load_result
    entry = bundle['paths'][0]
    data = load_result(Path(entry).parent/'source/dynamic_result.json',metadata_only=True)
    derivation = data.get('derivation') or {}
    expected = {k:job.get(k) for k in ('id','workspace_id','operation','request_hash')}
    args=job.get('arguments',{})
    source_pin=derivation.get('original_execution_record',{})
    if (derivation.get('kind')!='explicit_native_output_readback' or
            derivation.get('readback_job')!=expected or
            origin.get('job_id')!=args.get('source_job_id') or
            source_pin.get('relative')!='source_execution.json' or
            {k:source_pin.get(k) for k in ('bytes','sha256')} !=
            {k:args.get('source_record',{}).get(k) for k in ('bytes','sha256')}):
        raise ValueError('Readback registration differs from its original execution/request')
    original= json.loads(_read(verify_pin(Path(entry).parent/'source',source_pin)))
    if (original.get('job_id')!=origin.get('job_id') or
            original.get('snapshot_id')!=origin.get('snapshot_id') or
            original.get('input_origin')!=origin.get('input_origin')):
        raise ValueError('Copied original execution differs from retained result origin')
