"""Read the selected job's actual model, diagnostics and result; never execute."""
from copy import deepcopy
import json
from pathlib import Path


def expert_projection(context):
    """Keep engineering observations in the prompt; archived raw text stays readable."""
    context = deepcopy(context)
    def convergence(value):
        if isinstance(value, list):
            return [convergence(row) for row in value]
        if not isinstance(value, dict):
            return value
        rows = value.get('rows', [])
        if rows and all(isinstance(row, dict) and 'native_tokens' in row for row in rows):
            value['columns'] = ['step', 'increment', 'attempt', 'iteration', 'contact_elements',
                'residual_force_pct', 'correction_disp_pct', 'residual_flux_pct', 'correction_temp_pct']
            value['line_numbers'] = [row.get('line') for row in rows]
            value['sentinel_channels'] = [row.get('sentinel_channels', []) for row in rows]
            value['rows'] = [row['native_tokens'] for row in rows]
        return value
    def observation(value):
        if not isinstance(value, dict):
            return value
        for log in value.get('logs', []):
            text = log.get('text')
            if not isinstance(text, str) or len(text.encode('utf-8')) <= 512:
                continue
            lines = text.splitlines()
            log.pop('text')
            log['diagnostic_lines'] = [line for line in lines if any(word in line.lower() for word in
                ('error', 'warning', 'fatal', 'no convergence', 'not converg', 'diverg', 'failed', 'cutback'))]
            log['last_line'] = next((line for line in reversed(lines) if line.strip()), '')
            log['raw_text'] = 'Retained locally; read the selected archive with knowledge.search/knowledge.source.'
        if 'convergence' in value:
            value['convergence'] = convergence(value['convergence'])
        for source in value.get('sources', []):
            observation(source)
        return value
    if 'engineering_context' in context:
        context['engineering_context'] = observation(context['engineering_context'])
    context['engineering_context_history'] = [observation(row)
        for row in context.get('engineering_context_history', [])]
    return context


def read_context(workbench, identifier=None, *, selection=None):
    if selection is not None:
        if identifier is not None:
            raise ValueError('Choose a job or independent selection, not both')
        configured = getattr(workbench, 'config', {}).get('desktop', {}).get('freecad_executable')
        return read_selection(selection, freecad_executable=configured)
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
    # Native writer/converter logs can sort before the actual solver histories.
    # Keep the bounded payload while always including the convergence files.
    logs = sorted(monitor['logs'], key=lambda row:
        (not row['label'].lower().endswith(('.sta', '.cvg', '.dat')), row['bytes'] == 0, row['label']))
    for log in logs[:6]:
        selected = workbench.job_monitor(identifier, log=log['id'],
            offset=max(0, log['bytes'] - 6144), limit=6144)['selected_log']
        context['logs'].append({'label': log['label'], **selected})
    if len(monitor['logs']) > 6 or monitor.get('catalog_truncated'):
        context['limitations'].append('Only six log tails are included, prioritizing .sta/.cvg/.dat; use the job monitor for more.')
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


def _model_summary(snapshot):
    return {key: deepcopy(snapshot[key]) for key in (
        'kind', 'export_profile', 'native_version', 'analysis', 'solver', 'mesh',
        'mesh_summary', 'mesh_quality', 'shape', 'material', 'materials', 'conditions',
        'loads', 'constraints', 'contacts', 'sections', 'steps', 'units', 'limits',
        'selection', 'document', 'model_state', 'saved_extensions') if key in snapshot}


def _input_summary(path):
    from apps.desktop_pre.native_calculix import read_sections
    sections, files = read_sections(path)
    groups = {'materials': [], 'steps': [], 'loads': [], 'constraints': [], 'contacts': [], 'sections': []}
    mesh = {'node_records': 0, 'element_types': {}}
    for card, options, rows in sections:
        if card == '*NODE':
            mesh['node_records'] += len(rows)
        if card == '*ELEMENT':
            kind = options.get('TYPE', '')
            # Continuation records are not elements; count original element headers.
            mesh['element_types'].setdefault(kind, {'connectivity_records': 0})['connectivity_records'] += len(rows)
        target = ('materials' if card in {'*MATERIAL', '*ELASTIC', '*PLASTIC', '*DENSITY', '*EXPANSION', '*CONDUCTIVITY', '*SPECIFIC HEAT'} else
                  'steps' if card in {'*STEP', '*END STEP', '*STATIC', '*DYNAMIC', '*FREQUENCY', '*BUCKLE', '*HEAT TRANSFER', '*COUPLED TEMPERATURE-DISPLACEMENT'} else
                  'loads' if card in {'*CLOAD', '*DLOAD', '*DFLUX', '*CFLUX', '*FILM', '*RADIATE'} else
                  'constraints' if card in {'*BOUNDARY', '*EQUATION', '*MPC', '*RIGID BODY'} else
                  'contacts' if card in {'*CONTACT PAIR', '*SURFACE INTERACTION', '*SURFACE BEHAVIOR', '*FRICTION', '*TIE', '*CONTACT', '*SURFACE'} else
                  'sections' if card.endswith(' SECTION') else None)
        if target and len(groups[target]) < 40:
            groups[target].append({'keyword': card, 'options': options, 'rows': rows[:40], 'row_count': len(rows)})
    return {'kind': 'calculix-input', 'model_state': 'calculation_input', 'mesh': mesh,
            'cards': list(dict.fromkeys(card for card, _, _ in sections)), 'files': list(map(str, files)),
            'units': None, 'mesh_quality': {'status': 'NOT_PROVIDED'}, **groups}


def _freecad_summary(path, *, freecad_executable=None):
    import os
    import tempfile
    from .adapters.native_calculix_results import _freecad_command
    from .execution_control import run_owned_command
    from .storage import save_json, load_json
    with tempfile.TemporaryDirectory(prefix='caelab-model-read-') as folder:
        root = Path(folder)
        request = root / 'request.json'
        save_json(request, {'source': str(path), 'output': str(root), 'mode': 'model_context'})
        env = os.environ.copy()
        for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH'):
            env.pop(key, None)
        env['CAELAB_FRD_CONVERSION'] = str(request)
        worker = Path(__file__).parent / 'adapters' / 'freecad_frd_worker.py'
        finished = run_owned_command([_freecad_command(freecad_executable), str(worker)], root, 'freecad_context',
            env=env, owned_tree=True, timeout=120)
        if finished.returncode:
            raise ValueError('FreeCAD could not read the saved model')
        result = load_json(root / 'converted.json')
        if result.get('error'):
            raise ValueError(result['error'])
        return result['model']


def _post_summary(path):
    import xml.etree.ElementTree as ET
    from .native_post_dependencies import inspect_dataset
    dependency = inspect_dataset(path, baseline_pins=None, approved_roots=[path.parent], limits={})
    result = {'execution_status': None, 'units': None, 'time_semantics': None, 'frames': [],
              'limitations': 'File headers only; open the result in ParaView to include native numerical ranges.'}
    if path.suffix.lower() == '.pvd':
        root = ET.parse(path).getroot()
        result['output_values'] = [float(node.attrib['timestep']) for node in root.findall('./Collection/DataSet')]
    for row in dependency['files'][:32]:
        file = Path(row['path'])
        if file.suffix.lower() != '.vtu':
            continue
        # Read only XML headers, including serial raw-appended VTK files.
        with file.open('rb') as stream:
            header = stream.read(2 * 1024 * 1024).split(b'<AppendedData', 1)[0]
        piece_end = header.find(b'</UnstructuredGrid>')
        if piece_end < 0:
            result['frames'].append({'path': str(file), 'status': 'HEADER_EXCEEDS_LIMIT'})
            continue
        root = ET.fromstring(header[:piece_end] + b'</UnstructuredGrid></VTKFile>')
        pieces = []
        for piece in root.findall('.//Piece'):
            arrays = []
            for tag, association in (('PointData', 'POINTS'), ('CellData', 'CELLS')):
                for array in piece.findall(tag + '/DataArray'):
                    width = int(array.get('NumberOfComponents', '1'))
                    arrays.append({'name': array.get('Name'), 'association': association, 'components': width,
                        'component_names': [array.get('ComponentName' + str(i)) for i in range(width)],
                        'units': None, 'frame': None})
            pieces.append({'points': int(piece.get('NumberOfPoints', '0')),
                           'cells': int(piece.get('NumberOfCells', '0')), 'arrays': arrays})
        result['frames'].append({'path': str(file), 'pieces': pieces})
    result['file_count'] = len(dependency['files'])
    result['summary_file_limit'] = 32
    return result


def read_selection(selection, *, freecad_executable=None):
    """Observe independent saved inputs and supplied live selection, without a job."""
    if not isinstance(selection, dict):
        raise ValueError('An independent selection must be an object')
    if len(json.dumps(selection, ensure_ascii=False, allow_nan=False)) > 2 * 1024 * 1024:
        raise ValueError('The selected engineering summary exceeds the bounded reader size')
    if 'sources' in selection:
        sources = selection['sources']
        if not isinstance(sources, list) or not 1 <= len(sources) <= 32:
            raise ValueError('Select from one to 32 independent engineering files')
        observed = [read_selection(source, freecad_executable=freecad_executable) for source in sources]
        logs, convergence = {}, {}
        for source in observed:
            companions = source.pop('logs', [])
            source['log_paths'] = [row['path'] for row in companions]
            for row in companions:
                logs.setdefault(row['path'], row)
            history = source.pop('convergence', None)
            if isinstance(history, list):
                source['convergence_paths'] = [row['path'] for row in history]
                for row in history:
                    convergence.setdefault(row['path'], {key: value for key, value in row.items() if key != 'path'})
            elif history is not None:
                path = next(row['path'] for row in companions if Path(row['path']).suffix.lower() == '.cvg')
                source['convergence_path'] = path
                convergence.setdefault(path, history)
        # Selected inputs/results share companion observations, not copies of their text.
        return {'sources': observed, 'logs': list(logs.values()),
                'convergence': [{'path': path, **history} for path, history in convergence.items()],
                'scope': deepcopy(selection.get('scope', {})), 'state': None,
                'validation_status': '검증 사례 없음', 'engineering_release': 'NOT_ASSESSED'}
    raw = selection.get('path') or selection.get('file_path')
    if not raw and selection.get('model_snapshot') is not None:
        model = _model_summary(selection['model_snapshot'])
        model['model_state'] = 'current_editing_model'
        return {'source': {'path': None, 'scope': deepcopy(selection.get('scope', {}))},
                'model': model, 'logs': [], 'result': deepcopy(selection.get('result_metadata')),
                'state': None, 'limitations': ['Unsaved current editing model; no calculation input is established.'],
                'validation_status': '검증 사례 없음', 'engineering_release': 'NOT_ASSESSED'}
    if not isinstance(raw, str) or not Path(raw).is_absolute():
        raise ValueError('Select an absolute local model, input, log or result path')
    path = Path(raw).resolve(strict=True)
    if not path.is_file() or path.stat().st_size > 256 * 1024 ** 2:
        raise ValueError('The selected engineering file is missing or exceeds the bounded reader size')
    context = {'source': {'path': str(path), 'scope': deepcopy(selection.get('scope', {}))},
        'model': {}, 'logs': [], 'result': None, 'state': None, 'limitations': [],
        'validation_status': '검증 사례 없음', 'engineering_release': 'NOT_ASSESSED'}
    suffix = path.suffix.lower()
    try:
        if selection.get('model_snapshot') is not None:
            context['model'] = _model_summary(selection['model_snapshot'])
            context['model']['model_state'] = 'current_editing_model'
        elif suffix == '.fcstd':
            context['model'] = _model_summary(_freecad_summary(path, freecad_executable=freecad_executable))
            context['model']['model_state'] = 'saved_model'
        elif suffix == '.inp':
            context['model'] = _input_summary(path)
        elif suffix == '.frd':
            from .adapters.native_calculix_results import inspect_frd
            nodes, frames = inspect_frd(path, require_displacement=False)
            context['result'] = {'execution_status': None, 'units': None, 'time_semantics': None,
                'node_count': len(nodes), 'frames': [{
                    **{key: frame.get(key) for key in ('value', 'step', 'analysis_type')},
                    'fields': [{'name': name, 'arrays': sorted(field['arrays']),
                        'components': deepcopy(field['components']), 'node_count': len(field['ids']),
                        'missing_node_count': len(set(nodes) - field['ids'])}
                        for name, field in frame['fields'].items()]} for frame in frames]}
        elif suffix in {'.vtu', '.pvd'}:
            context['result'] = _post_summary(path)
        elif suffix == '.json':
            if path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError('The model summary exceeds the bounded reader size')
            snapshot = json.loads(path.read_text(encoding='utf-8-sig'))
            if not isinstance(snapshot, dict):
                raise ValueError('The selected model summary must be an object')
            if snapshot.get('kind') == 'external-result':
                context['result'] = {'sources': {ref: {key: deepcopy(record[key]) for key in (
                    'entry_path', 'metadata', 'conversion', 'label') if key in record}
                    for ref, record in list(snapshot.get('sources', {}).items())[:16]},
                    'selection': deepcopy(snapshot.get('active_selection'))}
            else:
                context['model'] = _model_summary(snapshot)
                context['model'].setdefault('model_state', 'calculation_input' if snapshot.get('export_profile') else 'saved_model')
        if selection.get('result_metadata') is not None:
            context['result'] = deepcopy(selection['result_metadata'])
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, SyntaxError) as error:
        context['limitations'].append('Selected model/result unavailable: ' + str(error))
    # These companions are observed files with the same stem, not an inferred run.
    for ext in ('.sta', '.cvg', '.dat', '.log', '.out'):
        log = path.with_suffix(ext)
        if not log.is_file():
            continue
        size = log.stat().st_size
        with log.open('rb') as stream:
            stream.seek(max(0, size - 6144))
            text = stream.read(6144).decode('utf-8', errors='replace')
        context['logs'].append({'label': log.name, 'path': str(log), 'bytes': size,
            'offset': max(0, size - 6144), 'text': text, 'truncated': size > 6144})
        if ext == '.cvg':
            from .calculix_convergence import read_cvg
            try:
                parsed = read_cvg(log)
                parsed['record_count'] = len(parsed['rows'])
                parsed['rows'] = parsed['rows'][-40:]
                context['convergence'] = parsed
            except (ValueError, OSError) as error:
                context['limitations'].append('Convergence unavailable: ' + str(error))
    context['limitations'].append('Saved input and current editing model may differ; associated files alone do not establish solver completion or units.')
    return context
