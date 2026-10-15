"""Exact research document/result navigation and reusable stage execution.

Transport wrappers call these functions; they never own a second document,
queue or optimizer. Source revisions are read through their existing owners.
"""
from copy import deepcopy
from pathlib import Path

from .storage import canonical_hash, check_id, load_json, revision_read_scope
from .evaluation import read_result, file_hash


def result_folder(wb, document_id, job_id):
    owner = wb._document_owner(check_id(document_id))
    if owner is wb.native_commands:
        raise ValueError('Choose an exact research document result')
    document = owner.read(document_id)
    row = next((row for row in document.get('runs', []) if row['job_id'] == check_id(job_id)), None)
    if row is None:
        raise ValueError('The selected job does not belong to this document')
    retained = row.get('retained_result')
    if retained:
        owner._verify_revision(document_id, retained['revision'])
        folder = owner._folder(document_id) / 'revisions' / retained['revision'] / 'results' / job_id
    else:
        folder = wb.root / 'results' / job_id
    return folder, row


@revision_read_scope()
def evaluation_progress(wb, document_id, job_id):
    if wb._document_owner(document_id) is not wb.evaluation_documents:
        raise ValueError('Stage progress belongs to an EvaluationDefinition document')
    folder, row = result_folder(wb, document_id, job_id)
    if (folder / 'result.json').exists():
        result = wb.document_result(document_id, job_id, selection={'responses': []})
        result['phase'] = 'FINISHED'
    elif (folder / 'progress.json').exists():
        result = load_json(folder / 'progress.json')
    else:
        result = {'phase': wb.desktop.job_record(job_id).get('phase', 'QUEUED'), 'stages': [], 'iterations': [], 'transfers': []}
    # progress.json records the last worker observation. After a controller
    # restart it is evidence of that attempt, not a claim that it is still live.
    # Overlay controller state only in the response; never rewrite old evidence.
    result = deepcopy(result)
    job = wb.desktop.job_record(job_id)
    state = job['state']
    result.update(job_state=state, controller_phase=job.get('phase'),
                  cancel_requested=job.get('cancel_requested', False))
    if state in {'INTERRUPTED', 'CLEANUP_PENDING', 'CANCEL_REQUESTED'}:
        result['recorded_phase'] = result.get('phase')
        result['phase'] = state
    elif state in {'FAILED', 'CANCELLED'} and result.get('phase') != 'FINISHED':
        result['recorded_phase'] = result.get('phase')
        result['phase'] = state
    if state in {'INTERRUPTED', 'FAILED', 'CANCELLED', 'CLEANUP_PENDING'}:
        for stage in result.get('stages', []):
            if stage.get('state') == 'RUNNING':
                stage.update(recorded_state='RUNNING', state=state,
                             completion_confirmed=False)
    return {key: deepcopy(value) for key, value in result.items() if key not in {'responses', 'artifacts'}} | {
        'document_id': document_id, 'job_id': job_id, 'input_revision': row['input_revision'],
        'input_sha256': row['input_sha256']}


@revision_read_scope()
def evaluation_stage_result(wb, document_id, job_id, attempt_id, selection=None):
    check_id(attempt_id)
    if wb._document_owner(document_id) is not wb.evaluation_documents:
        raise ValueError('Stage results belong to an EvaluationDefinition document')
    folder, _ = result_folder(wb, document_id, job_id)
    if (folder / 'result.json').exists():
        progress = read_result(folder, verify='all', selection={'metadata_only': True})
    elif (folder / 'progress.json').exists():
        progress = load_json(folder / 'progress.json')
    else:
        raise ValueError('This evaluation has no recorded stage attempt yet')
    stage = next((row for row in progress['stages'] if row['attempt_id'] == attempt_id), None)
    if stage is None:
        raise ValueError('Choose an actual attempt from this exact evaluation')
    from .workbench import contained
    stage_folder = contained(folder, stage['result_directory'])
    if not (stage_folder / 'result.json').exists():
        raise ValueError('This stage has no completed retained result; inspect progress/failure')
    result = read_result(stage_folder, verify='all', selection=selection)
    # A failed parent does not erase independently completed stage results.
    return {**result, 'stage_attempt': deepcopy(stage), 'parent_job_id': job_id}


@revision_read_scope()
def numerical_evaluation_result(wb, document_id, job_id, candidate_id, *,
                                evaluation_index=None, attempt_id=None, selection=None):
    """Follow a selected row to its actual saved stage receipts, never a path supplied by a caller."""
    from .workbench import contained
    if wb._document_owner(document_id) is not wb.numerical_documents:
        raise ValueError('Select a Numerical Plan and its actual candidate')
    check_id(candidate_id)
    folder, _ = result_folder(wb, document_id, job_id)
    parent = read_result(folder, selection={'metadata_only': True})
    candidate = next((row for row in parent.get('candidates', []) if row['candidate_id'] == candidate_id), None)
    if candidate is None or candidate.get('prediction_status') == 'PREDICTED' or candidate.get('execution_status') == 'PREDICTED':
        raise ValueError('Choose an actual candidate evaluation, not a predicted or absent row')
    references = candidate.get('evaluation_refs', [])
    identity = dict(document_id=document_id, job_id=job_id, candidate_id=candidate_id)
    identity.update(parent_execution_status=deepcopy(parent.get('execution_status')),
                    candidate_purpose=deepcopy(candidate.get('purpose')),
                    candidate_gradient_admission=deepcopy(candidate.get('gradient_admission')),
                    candidate_execution_status=deepcopy(candidate.get('execution_status')))
    if 'gradient_verification' in parent:
        identity['gradient_verification'] = deepcopy(parent['gradient_verification'])
    if evaluation_index is None:
        if attempt_id is not None or selection is not None:
            raise ValueError('Select an evaluation index before its stage or response')
        return {**identity, 'evaluations': [{**{k: deepcopy(v) for k, v in ref.items()
            if k not in {'relative', 'result_sha256'}}, 'evaluation_index': i} for i, ref in enumerate(references)]}
    if type(evaluation_index) is not int or not 0 <= evaluation_index < len(references):
        raise ValueError('Select an actual retained evaluation index from this candidate')
    reference = references[evaluation_index]
    directory = contained(folder, reference['relative'])
    if file_hash(directory / 'result.json') != reference['result_sha256']:
        raise ValueError('Candidate evaluation metadata differs from its retained row')
    if isinstance(selection,dict) and 'transfer' in selection:
        if set(selection)!={'transfer'} or attempt_id is not None:
            raise ValueError('전달값은 단계/응답 선택과 별도로 선택하세요.')
        query=selection['transfer']
        if not isinstance(query,dict) or set(query)-{'id','iteration','start','count'}:
            raise ValueError('전달 이름·반복과 제한된 행 범위만 지정하세요.')
        progress=read_result(directory,verify='all')
        frozen=load_json(directory/'input.json')['definition']
        from .evaluation_definition import definition_hash
        if definition_hash(frozen)!=progress.get('definition_sha256') or progress['definition_sha256']!=reference['definition_sha256']:
            raise ValueError('후보의 실제 저장 정의와 원 결과 참조가 다릅니다.')
        def read_stage(attempt,chosen):
            stages=[r for r in progress.get('stages',[]) if r['attempt_id']==attempt]
            if len(stages)!=1:
                raise ValueError('이 후보의 정확한 단계만 선택하세요.')
            row=stages[0];stage_folder=contained(directory,row['result_directory'])
            if not (stage_folder/'result.json').is_file():
                raise ValueError('This stage has no completed retained result; inspect progress/failure')
            result=read_result(stage_folder,verify='all',selection=chosen)
            return {**result,'stage_attempt':deepcopy(row),'parent_job_id':job_id}
        from .transfer_inspection import inspect_retained
        viewed=inspect_retained(wb,document_id,job_id,directory,frozen,progress,read_stage,
            query.get('id'),query.get('iteration'),start=query.get('start',0),count=query.get('count',256))
        return {**viewed,**identity,'evaluation_index':evaluation_index}
    result = read_result(directory, verify='all',
                         selection={'metadata_only': True} if attempt_id is not None else selection)
    identity['evaluation_index'] = evaluation_index
    if attempt_id is not None:
        check_id(attempt_id)
        stage = next((row for row in result.get('stages', []) + result.get('derivative_attempts', [])
                      if row['attempt_id'] == attempt_id), None)
        if stage is None:
            raise ValueError('Choose an attempt from this exact candidate evaluation')
        stage_directory = contained(directory, stage['result_directory'])
        result = read_result(stage_directory, verify='all', selection=selection)
        result['stage_attempt'] = deepcopy(stage)
        result['attempt_kind'] = 'adjoint' if 'primal_reference' in stage else 'primal'
    return {**result, **identity}


def execute_definition(wb, arguments, job_id):
    from .evaluation_definition import compile_definition, execute
    from .research_operations import _resolve
    from .research_execution import run_domain
    if set(arguments) != {'definition', 'snapshots', 'definition_source'}:
        raise ValueError('Evaluation execution requires its prepared definition and exact stage snapshots')
    compiled = compile_definition(arguments['definition'], arguments['snapshots'])
    # Workbench.submit verified these snapshots against this definition owner
    # before admission. The queue executes those frozen bytes; editing or losing
    # the original domain document cannot substitute another stage after submit.
    reuse = compiled['definition'].get('reuse')
    retained, folder = None, None
    if reuse and reuse['stages']:
        retained = _resolve(reuse['source'], wb.document_read, wb.document_result)
        folder, _ = result_folder(wb, reuse['source']['document_id'], reuse['source']['job_id'])
    return execute(compiled, wb.root / 'results' / check_id(job_id),
        lambda model, output: run_domain(wb, model, output), reuse_result=retained, reuse_folder=folder)


def _candidate_reference_view(result, selection):
    """Select actual nested candidate responses after full exact-result verification.

    This is a read view of existing candidate records, not a new result schema
    or evaluation. Advanced native location/time selection stays with the
    existing candidate evaluation/stage reader and original result tool.
    """
    if isinstance(selection, list):
        selection = {'responses': selection}
    if not isinstance(selection, dict) or set(selection) - {'responses', 'rows', 'candidate_ids', 'metadata_only', 'reduction_index'}:
        raise ValueError('Candidate evidence preview accepts response names and rows; open the original result for advanced selection')
    names = selection.get('responses')
    if names is not None and (not isinstance(names, list) or any(not isinstance(name, str) for name in names)):
        raise ValueError('Response selection must be a list of names')
    bounds = selection.get('rows')
    if bounds is not None and (not isinstance(bounds, (list, tuple)) or len(bounds) != 2
            or any(type(value) is not int for value in bounds)):
        raise ValueError('Candidate response rows require an integer start and stop')
    key = 'candidates' if isinstance(result.get('candidates'), list) else 'predictions'
    rows = result[key]
    selected_ids = selection.get('candidate_ids')
    if selected_ids is not None:
        if (not isinstance(selected_ids, list) or not selected_ids or
                any(not isinstance(v, str) for v in selected_ids) or len(set(selected_ids)) != len(selected_ids)):
            raise ValueError('Choose distinct exact retained candidates')
        if set(selected_ids) - {row.get('candidate_id') for row in rows}:
            raise ValueError('Selected candidate is absent from this exact result')
        rows = [row for row in rows if row.get('candidate_id') in selected_ids]
    reduction_index=selection.get('reduction_index')
    if reduction_index is not None:
        if (type(reduction_index) is not int or selected_ids is None or len(rows)!=1
                or not 0<=reduction_index<len(rows[0].get('response_reductions',[]))
                or set(selection)-{'candidate_ids','responses','reduction_index'}):
            raise ValueError('Select one exact saved candidate reduction, without curve rows or times')
        reduced=rows[0]['response_reductions'][reduction_index]
        if names != [reduced['response']]:
            raise ValueError('Saved reduction and requested response differ')
        actual=deepcopy(result);actual[key]=deepcopy(rows)
        actual[key][0]['responses']={}
        actual[key][0]['response_reductions']=[deepcopy(reduced)]
        actual[key][0]['selected_reduction_index']=reduction_index
        return actual
    available = {name for row in rows for name in (row.get('responses') or {})}
    if names is not None and any(name not in available for name in names):
        raise ValueError('Unknown candidate response selection')
    actual = deepcopy(result)
    actual[key] = deepcopy(rows)
    for row in actual[key]:
        responses = row.get('responses') or {}
        row['responses'] = ({} if selection.get('metadata_only') else
            {name: response for name, response in responses.items() if names is None or name in names})
        if not selection.get('metadata_only'):
            row.pop('response_reductions',None)
        for response in row['responses'].values():
            if bounds is None or response.get('kind') != 'series':
                continue
            values = response.get('value')
            axes = response.get('axes') or []
            if (not isinstance(values, list) or len(axes) != 1
                    or not isinstance(axes[0].get('values'), list) or len(axes[0]['values']) != len(values)):
                raise ValueError('Candidate series does not have one matching saved axis')
            selected = slice(*bounds)
            response['value'] = values[selected]
            axes[0]['values'] = axes[0]['values'][selected]
            for field in ('mask', 'source_rows'):
                if response.get(field) is not None:
                    if not isinstance(response[field], list) or len(response[field]) != len(values):
                        raise ValueError('Candidate series ' + field + ' does not match its values')
                    response[field] = response[field][selected]
    return actual


def resolve_reference(wb, reference):
    """Read the requested immutable evidence, never the current draft instead."""
    from .study_document import reference_error
    from .research_operations import _resolve, RESULT_REF_KEYS, result_metadata
    error = reference_error(reference)
    if error:
        raise ValueError(error)
    kind = reference['kind']
    if kind == 'numerical_candidate_evidence':
        from .numerical_candidate_evidence import candidate_report_payload
        return candidate_report_payload(wb.numerical_documents, reference)
    if kind == 'comparison':
        owner=wb._document_owner(reference['document_id'])
        if owner is wb.native_commands:raise ValueError('비교를 소유한 연구 문서를 선택하세요.')
        saved=owner._verify_revision(reference['document_id'],reference['saved_revision'])
        row=next((r for r in saved.get('comparisons',[]) if r['id']==reference['comparison_id']),None)
        if saved['kind']!=reference['document_kind'] or row is None or row['result_sha256']!=reference['result_sha256']:
            raise ValueError('저장된 비교의 정확한 참조가 다릅니다.')
        current=owner.read(reference['document_id'])
        current_row=next((r for r in current.get('comparisons',[]) if r['id']==reference['comparison_id']),None)
        if current_row is None or current_row['result_sha256']!=row['result_sha256']:
            raise ValueError('요청한 비교가 현재 소유자에서 읽히지 않습니다.')
        comparison=owner.comparison(reference['document_id'],reference['comparison_id'],
            start=reference['start'],count=reference['count'])
        return {'status':'AVAILABLE','kind':kind,'reference':deepcopy(reference),'comparison':comparison}
    if kind == 'knowledge':
        source = wb.assistance_call('knowledge.source', {key: deepcopy(reference[key])
            for key in ('document_id', 'revision', 'locator')})
        if (source.get('status') != 'AVAILABLE' or source.get('sha256') != reference['source_sha256']
                or canonical_hash(source) != reference['content_sha256']):
            raise ValueError('선택한 문헌 개정/원문이 없거나 변경되었습니다.')
        result = {'status': 'AVAILABLE', 'kind': kind, 'reference': deepcopy(reference), 'source': source}
        if hasattr(wb, 'assistance'):
            result['source_metadata'] = wb.assistance().knowledge.revision_details(
                reference['document_id'], reference['revision'], workspace_id=wb.workspace_id)
        return result
    if kind == 'document':
        owner = wb._document_owner(reference['document_id'])
        if owner is wb.native_commands:
            raise ValueError('Select a saved research document reference; native source references remain in their projects')
        saved = owner._verify_revision(reference['document_id'], reference['saved_revision'])
        if (saved['kind'] != reference['document_kind'] or saved['input_revision'] != reference['input_revision']
                or canonical_hash(saved['draft']) != reference['input_sha256']):
            raise ValueError('Saved document input identity differs')
        if saved['kind'] == 'expert':
            from .portable_research_knowledge import require_owner_sources, document_refs
            require_owner_sources(owner, document_refs(saved))
        return {'status': 'AVAILABLE', 'kind': kind, 'reference': deepcopy(reference),
                'document': {key: deepcopy(saved[key]) for key in ('id', 'kind', 'title', 'input_revision', 'draft')}}
    if kind == 'result':
        exact = {key: reference[key] for key in RESULT_REF_KEYS}
        result = _resolve(exact, wb.document_read, wb.document_result)
        selection = reference.get('selection', [reference['response']] if reference.get('response') else {'metadata_only': True})
        nested = isinstance(result.get('candidates'), list) or isinstance(result.get('predictions'), list)
        metadata_only = isinstance(selection, dict) and selection.get('metadata_only')
        if result.get('kind') in {'experiment_uncertainty', 'experiment_identification'}:
            from .experiment_analysis_reporting import retained_report_view
            actual = retained_report_view(result, selection)
        else:
            actual = (_candidate_reference_view(result, selection) if nested else
                      wb.document_result(exact['document_id'], exact['job_id'], selection=selection))
        return {'status': 'AVAILABLE', 'kind': kind, 'reference': deepcopy(reference),
                'metadata': result_metadata(result), 'result': actual}
    owner = wb.discussion_documents
    saved = owner._verify_revision(reference['discussion_id'], reference['saved_revision'])
    from .portable_research_knowledge import require_owner_sources, document_refs
    require_owner_sources(owner, [*document_refs(saved), *saved.get('portable_knowledge_refs', [])])
    turn = next((row for row in saved.get('discussion', {}).get('turns', []) if row['id'] == reference['turn_id']), None)
    if turn is None or canonical_hash(turn) != reference['turn_sha256']:
        raise ValueError('Saved discussion turn differs from its exact reference')
    return {'status': 'AVAILABLE', 'kind': kind, 'reference': deepcopy(reference), 'turn': deepcopy(turn)}


def reference_metadata(wb, reference):
    result = resolve_reference(wb, reference)
    result.pop('document', None); result.pop('result', None); result.pop('turn', None)
    result.pop('source', None); result.pop('comparison', None)
    result.pop('candidate_evidence', None)
    return result
