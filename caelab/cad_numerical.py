"""Saved Pre/Simulation/Numerical connections using the existing owners."""
from copy import deepcopy
from pathlib import Path
import uuid

from .storage import check_id, canonical_hash, load_json, save_json
from .native_cad import inspect_project
from .native_inputs import register_native_input
from .evaluation import file_hash, read_result
from .adapters.cad_analysis import BACKEND, validate_settings


def resolve_settings(wb, settings):
    """Resolve only a registered immutable input and operator native runtime.

    Idempotent for the existing run_domain second resolution. Even a supplied
    internal context must exactly match the independently resolved context.
    """
    settings = deepcopy(settings)
    validate_settings(settings)
    path = wb.input_path(settings['data_id'])
    receipt = wb.native_input(settings['data_id'])
    if receipt.get('kind') != 'native_design' or path.suffix.lower() != '.caepre':
        raise ValueError('Native studies require a registered saved CAEPRE dependency graph')
    if receipt['sha256'] != settings['source_sha256'] or file_hash(path) != settings['source_sha256']:
        raise ValueError('Registered saved Analysis input differs')
    manifest = inspect_project(path)
    if manifest.get('unavailable_dependencies'):
        raise ValueError('Saved native dependency is unavailable')
    if canonical_hash(manifest['metadata'].get('candidate_recipe')) != canonical_hash(settings['recipe']):
        raise ValueError('Plan recipe differs from the registered saved Analysis')
    runtime = wb.desktop.context()
    executable = runtime.get('freecad_executable')
    if executable:
        configured = Path(executable).expanduser()
        # Official portable root FreeCAD.exe is a short-lived launcher. The
        # same installation's bin executable owns the GUI/macros we must await.
        native = configured.parent / 'bin' / 'FreeCAD.exe'
        if configured.name.lower() == 'freecad.exe' and native.is_file():
            executable = str(native.resolve())
        else:
            executable = str(configured.resolve())
    gmsh = None
    if executable:
        exe = Path(executable)
        for candidate in (exe.parent / 'gmsh.exe', exe.parent / 'bin/gmsh.exe',
                          exe.parent.parent / 'bin/gmsh.exe', exe.parent / 'gmsh'):
            if candidate.is_file():
                gmsh = str(candidate.resolve())
                break
    context = {'source': str(path.resolve()), 'freecad_executable': executable, 'gmsh': gmsh}
    if '_native_context' in settings and settings['_native_context'] != context:
        raise ValueError('Caller cannot replace native execution paths')
    settings['_native_context'] = context
    return settings


def prepare_plan(wb, command_id, *, operation='doe'):
    """A completed native capture opens one explicit unexecuted research Plan."""
    from .workbench import contained
    from .numerical_document import request_draft
    command_id = check_id(command_id)
    if operation not in ('doe', 'optimize'):
        raise ValueError('Start a DOE or optimization Plan')
    with wb.desktop._lock:
        command = wb.native_commands.status(command_id)
        if command['operation'] != 'pre.research.prepare' or command['state'] != 'SUCCEEDED':
            raise ValueError('Complete the native Analysis research capture first')
        envelope = command.get('outcome', {}).get('result', {})
        result = envelope.get('result', {})
        if envelope.get('status') != 'COMPLETED':
            raise ValueError('Native Analysis capture has no completed result')
        project = contained(wb.desktop.root, result['project_relative'])
        if not project.is_relative_to(wb.desktop.root / command['document_id']) or project.suffix.lower() != '.caepre':
            raise ValueError('Saved Analysis must belong to the exact native owner command')
        if file_hash(project) != result['project_sha256']:
            raise ValueError('Saved native research input changed')
        record = wb.desktop.root / 'cad_plans' / (command_id + '.json')
        signature = canonical_hash({'command': command['request_hash'], 'operation': operation})
        if record.exists():
            prepared = load_json(record)
            if prepared['signature'] != signature:
                raise ValueError('This capture was already used with a different operation')
            if prepared.get('plan_id'):
                return {'document': wb.numerical_documents.read(prepared['plan_id']),
                        'source': prepared['source'], 'executed': False}
        else:
            native = register_native_input(wb.root, wb.desktop.root, project, 'D' + uuid.uuid4().hex,
                root_id='native-owner:' + command['document_id'], relative=result['project_relative'],
                limit=wb.config.get('local_input_max_bytes', 2 * 1024**3))
            recipe = deepcopy(result['recipe'])
            settings = {'data_id': native['id'], 'source_sha256': native['sha256'], 'recipe': recipe,
                        'values': {row['id']: row['value'] for row in recipe['variables']}}
            validate_settings(settings)
            prepared = {'signature': signature, 'settings': settings,
                        'simulation_id': 'V' + canonical_hash({'capture': command_id})[:32],
                        'title': result['label'][:160]}
            save_json(record, prepared)
        recipe = prepared['settings']['recipe']
        scalar = next((r for r in recipe['responses'] if r['reduction'] not in ('field', 'series')), None)
        if operation == 'optimize' and scalar is None:
            raise ValueError('Choose at least one scalar response for an objective')
        simulation = wb.simulation_documents
        identifier = prepared['simulation_id']
        if 'handoff' not in prepared:
            with simulation._lock(identifier):
                if (simulation._folder(identifier) / 'working.json').exists() or simulation._manifest(identifier):
                    source = simulation.read(identifier)
                else:
                    source = simulation.open(_new_id=identifier, title=prepared['title'],
                                             draft={'backend': BACKEND, 'settings': prepared['settings']})
                expected_draft = {'backend': BACKEND, 'settings': prepared['settings']}
                if canonical_hash(source['draft']) != canonical_hash(expected_draft) or source['runs']:
                    raise ValueError('Prepared Analysis recipe was edited; keep its edits and make a new capture')
                prepared['handoff'] = {'document_id': identifier, 'session_id': wb.session_id,
                    'expected_generation': source['generation'],
                    'command_id': 'C' + canonical_hash({'capture': command_id, 'step': 'plan'})[:32]}
                save_json(record, prepared)
        handoff = wb.desktop.domain_plan(**prepared['handoff'])
        plan = handoff['document']
        # Retain exact initialization arguments BEFORE applying. The existing
        # owner command receipt handles replay; a retry never uses a newer generation.
        recipe = prepared['settings']['recipe']
        inputs = {'backend': BACKEND, 'settings': deepcopy(prepared['settings']),
                  'variables': [{'id': row['id'], 'value': row['value'], 'lower': row['lower'],
                                 'upper': row['upper'], 'unit': row['unit']} for row in recipe['variables']],
                  'execution': {'mode': 'serial', 'workers': 1, 'on_failure': 'continue'}}
        if operation == 'doe':
            inputs.update(count=4, seed=0, responses=[row['id'] for row in recipe['responses']])
            budget = 4
        else:
            scalar = next((r for r in recipe['responses'] if r['reduction'] not in ('field', 'series')), None)
            if not scalar:
                raise ValueError('Choose at least one scalar response for an objective')
            inputs.update(objective={'response': scalar['id'], 'unit': scalar['unit'], 'reduction': ('none' if scalar['reduction'] == 'value' else scalar['reduction']), 'direction': 'minimize'},
                          constraints=[], options={'population_size': 4, 'max_generations': 1})
            budget = 8
        draft = request_draft({'purpose': prepared['title'], 'operation': operation,
                               'inputs': inputs, 'budget': {'evaluations': budget}}, source=handoff['source'])
        if 'initialization' not in prepared:
            initial = request_draft({'purpose': prepared['title'], 'operation': 'evaluate',
                'inputs': {'backend': BACKEND, 'settings': prepared['settings']},
                'budget': {'evaluations': 1}}, source=handoff['source'])
            if canonical_hash(plan['draft']) != canonical_hash(initial) or plan['runs']:
                raise ValueError('New Plan was edited before initialization; its edits are retained')
            prepared['initialization'] = {'identifier': plan['id'], 'operation': 'numerical.update',
                'arguments': {'draft': draft}, 'session_id': wb.session_id,
                'expected_generation': plan['generation'],
                'command_id': 'C' + canonical_hash({'capture': command_id, 'step': 'initialize'})[:32]}
            prepared['source'] = handoff['source']
            save_json(record, prepared)
        wb.numerical_documents.command(**prepared['initialization'])
        # Read the current owner after replay: an earlier result may predate edits.
        updated = wb.numerical_documents.read(prepared['initialization']['identifier'])
        save_json(record, {**prepared, 'plan_id': updated['id']})
        return {'document': updated, 'source': prepared['source'], 'executed': False}


def open_candidate(wb, plan_id, job_id, candidate_id, evaluation_index):
    """Register the exact calculated project; never replay values on the base."""
    from .research_workflows import result_folder, numerical_evaluation_result
    from .workbench import contained
    for value in (plan_id, job_id, candidate_id):
        check_id(value)
    verified = numerical_evaluation_result(wb, plan_id, job_id, candidate_id,
        evaluation_index=evaluation_index, selection={'responses': [], 'include_settings': True})
    if verified.get('backend') != BACKEND:
        raise ValueError('This candidate has no native saved-design evaluator')
    editable = verified.get('editable_design')
    if verified.get('execution_status') != 'SUCCEEDED' or not editable or not editable.get('calculated'):
        raise ValueError('No successfully calculated editable candidate; inspect retained failure files')
    parent, run = result_folder(wb, plan_id, job_id)
    result = read_result(parent, selection={'metadata_only': True})
    candidate = next(row for row in result['candidates'] if row['candidate_id'] == candidate_id)
    if candidate.get('execution_status') != 'SUCCEEDED':
        raise ValueError('Select a successful candidate; failed artifacts remain available for inspection')
    ref = candidate['evaluation_refs'][evaluation_index]
    folder = contained(parent, ref['relative'])
    project = contained(folder, editable['relative'])
    if project.suffix.lower() != '.caepre' or file_hash(project) != editable['sha256']:
        raise ValueError('Retained calculated native project differs')
    with wb.desktop._lock:
        identity = {'plan_id': plan_id, 'job_id': job_id, 'candidate_id': candidate_id,
                    'evaluation_index': evaluation_index, 'result_sha256': ref['result_sha256'],
                    'base_data_id': editable['base_data_id'], 'base_sha256': editable['base_sha256']}
        receipt = register_native_input(wb.root, folder, project, 'D' + uuid.uuid4().hex,
            root_id='native-candidate', relative=project.relative_to(folder).as_posix(),
            limit=wb.config.get('local_input_max_bytes', 2 * 1024**3))
        # Same registry record; no second result store. Only this verified
        # service path can add branch lineage, never a caller-supplied path.
        record_path = wb.root / 'inputs' / receipt['id'] / 'input.json'
        record = load_json(record_path)
        record['candidate_branch'] = identity
        save_json(record_path, record)
        return {'input_id': receipt['id'], 'source': identity, 'calculation_performed': False}


def candidate_post(wb, plan_id, job_id, candidate_id, evaluation_index):
    from .research_workflows import result_folder, numerical_evaluation_result
    from .workbench import contained
    verified = numerical_evaluation_result(wb, plan_id, job_id, candidate_id,
        evaluation_index=evaluation_index, selection={'responses': []})
    artifact = verified.get('post_artifact')
    if verified.get('backend') != BACKEND or not artifact:
        raise ValueError('This candidate has no retained native field')
    parent, _ = result_folder(wb, plan_id, job_id)
    table = read_result(parent, selection={'metadata_only': True})
    row = next(r for r in table['candidates'] if r['candidate_id'] == candidate_id)
    reference = row['evaluation_refs'][evaluation_index]
    folder = contained(parent, reference['relative'])
    source = contained(folder, artifact['relative'])
    if file_hash(source) != artifact['sha256'] or source.stat().st_size != artifact['bytes']:
        raise ValueError('Candidate native field differs from its retained result')
    key = canonical_hash({'plan': plan_id, 'job': job_id, 'candidate': candidate_id,
                          'evaluation': evaluation_index, 'sha256': reference['result_sha256']})
    with wb.desktop._lock:
        record = wb.desktop.root / 'cad_post' / (key + '.json')
        if record.exists():
            field = load_json(record)
            if wb.native_input(field['id'])['sha256'] != field['sha256']:
                raise ValueError('Registered candidate field changed')
            return field
        receipt = register_native_input(wb.root, folder, source, 'D' + uuid.uuid4().hex,
            root_id='candidate-result:' + job_id, relative=artifact['relative'],
            limit=wb.config.get('local_input_max_bytes', 2 * 1024**3),
            native_metadata=artifact.get('native_metadata'))
        field = {'id': receipt['id'], 'format': receipt['format'], 'sha256': receipt['sha256']}
        save_json(record, field)
        return field
