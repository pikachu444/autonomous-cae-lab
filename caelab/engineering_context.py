"""Read the selected job's actual model, diagnostics and result; never execute."""
from copy import deepcopy
import json


def read_context(workbench, identifier):
    from .storage import check_id
    identifier = check_id(identifier)
    job = workbench.desktop.job_record(identifier)
    arguments = job.get('arguments', {})
    context = {'job_id': identifier, 'state': job['state'], 'operation': job.get('operation'),
               'backend': arguments.get('backend'), 'error': deepcopy(job.get('error')),
               'origin': deepcopy(arguments.get('origin')),
               'model': {}, 'logs': [], 'result': None, 'limitations': []}
    settings = arguments.get('settings', {})
    context['settings'] = deepcopy(settings)
    data_id = settings.get('data_id') if isinstance(settings, dict) else None
    if data_id:
        try:
            source = workbench.input_path(data_id)
            if source.suffix.lower() == '.json' and source.stat().st_size <= 2 * 1024 * 1024:
                snapshot = json.loads(source.read_text(encoding='utf-8-sig'))
                if not isinstance(snapshot, dict):
                    raise ValueError('The model summary must be an object')
                context['model'] = {key: deepcopy(snapshot[key]) for key in (
                    'kind', 'export_profile', 'native_version', 'analysis', 'solver', 'mesh',
                    'mesh_summary', 'mesh_quality', 'shape', 'material', 'materials', 'conditions', 'contacts',
                    'sections', 'steps', 'units', 'limits') if key in snapshot}
            else:
                context['limitations'].append('The selected input has no bounded model summary.')
        except (OSError, ValueError, KeyError) as error:
            context['limitations'].append('Model input unavailable: ' + str(error))
    else:
        context['model'] = {'settings': deepcopy(settings), 'values': deepcopy(arguments.get('values', {}))}
    monitor = workbench.job_monitor(identifier)
    for log in monitor['logs'][:6]:
        selected = workbench.job_monitor(identifier, log=log['id'],
            offset=max(0, log['bytes'] - 6144), limit=6144)['selected_log']
        context['logs'].append({'label': log['label'], **selected})
    if len(monitor['logs']) > 6 or monitor.get('catalog_truncated'):
        context['limitations'].append('Only the first six log tails are included; use the job monitor for more.')
    try:
        from .research_operations import result_metadata
        result = workbench.result(identifier, selection={'metadata_only': True})
        context['result'] = {'execution_status': result.get('execution_status'), 'summary': result_metadata(result),
            'fields': deepcopy(result.get('native_field_summary')),
            'diagnostics': {key: deepcopy(result.get('diagnostics', {})[key]) for key in
                ('reason', 'error_type', 'failure_reason', 'field_delivery_error') if key in result.get('diagnostics', {})}}
    except (OSError, ValueError, KeyError) as error:
        context['limitations'].append('Result unavailable: ' + str(error))
    context['validation_status'] = '검증 사례 없음'
    context['engineering_release'] = 'NOT_ASSESSED'
    return context
