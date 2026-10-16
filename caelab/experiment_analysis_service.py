"""FN05 bridges into the EXISTING Numerical Request Plan / JobManager owner.

These are two explicit operations, not backends. They use existing immutable
Data/Numerical readers. No call in this module opens a provider or creates a
store, scheduler, or independent document owner.
"""
from __future__ import annotations
from copy import deepcopy

from .storage import canonical_hash
from .experiment_uncertainty import plain

OPERATIONS = frozenset({'experiment_uncertainty', 'identification_final'})


def plan_input_schemas():
    from .research_operations import RESULT_REF_SCHEMA
    string = {'type': 'string', 'minLength': 1}
    obj = {'type': 'object'}
    def closed(properties, required):
        return {'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}
    imported = closed({'kind': {'const': 'result_response'}, 'reference': deepcopy(RESULT_REF_SCHEMA),
                       'response': string}, ['kind', 'reference', 'response'])
    processing = closed({'kind': {'const': 'processing_channel'}, 'document_id': string, 'revision': string,
        'channel': string, 'channel_sha256': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'}},
        ['kind', 'document_id', 'revision', 'channel', 'channel_sha256'])
    comparison = closed({'kind': {'const':'retained_comparison'},'reference':obj},['kind','reference'])
    observation = closed({'kind': {'const':'observation_chain'}, 'base':obj, 'operands':obj},['kind','base','operands'])
    return {
        'experiment_uncertainty': closed({'source': {'oneOf': [imported, processing, comparison, observation]},
            'specification': obj, 'plan_mask': {'type': 'array', 'items': {'type': 'boolean'}}}, ['source', 'specification']),
        'identification_final': closed({'evidence_reference': obj,
            'relative_step': {'type': 'number', 'minimum': 1e-8, 'maximum': 1e-2},
            'reuse_result': deepcopy(RESULT_REF_SCHEMA)}, ['evidence_reference'])}


def uncertainty_request(source, specification, *, purpose='제공 불확실성 전파', plan_mask=None):
    inputs = {'source': deepcopy(source), 'specification': deepcopy(specification)}
    if plan_mask is not None:
        inputs['plan_mask'] = deepcopy(plan_mask)
    # The existing Plan requires a positive budget slot. This analytic operation
    # explicitly reports ZERO model/solver evaluations; the slot is not a call.
    return {'purpose': purpose, 'operation': 'experiment_uncertainty', 'inputs': inputs, 'budget': {'evaluations': 1}}


def final_request(evidence_reference, *, evaluations, relative_step=1e-4,
                  purpose='최종 선택 계수의 국소 식별 진단', reuse_result=None):
    inputs = {'evidence_reference': deepcopy(evidence_reference), 'relative_step': relative_step}
    if reuse_result is not None:
        inputs['reuse_result'] = deepcopy(reuse_result)
    return {'purpose': purpose, 'operation': 'identification_final', 'inputs': inputs,
            'budget': {'evaluations': evaluations}}


def _retained(workbench, reference):
    from .research_operations import _resolve
    return _resolve(reference, workbench.document_read, workbench.document_result)


def source_problem(workbench, inputs):
    from .experiment_uncertainty import calibration_problem, processing_problem
    source = inputs['source']
    if source['kind'] == 'result_response':
        result = _retained(workbench, source['reference'])
        name = source['response']
        if name not in result.get('responses', {}):
            raise ValueError('선택한 원자료 응답이 보존 결과에 없습니다.')
        problem = calibration_problem(result['responses'][name], plan_mask=inputs.get('plan_mask'))
        problem['source_execution_status'] = result.get('execution_status', 'UNKNOWN')
        problem['source_diagnostics'] = plain(result.get('diagnostics', {}))
    elif source['kind'] == 'processing_channel':
        # Actual C1 owner-published processing result. NOT a new DAG or C2
        # canonical-fit adapter, and NOT a loose JSON channel supplied by UI.
        from .data_processing_document import result as read_processing
        result = read_processing(workbench.data_documents, source['document_id'], source['revision'])
        channels = result.get('channels', {})
        if source['channel'] not in channels:
            raise ValueError('보존된 처리 개정에 선택한 채널이 없습니다.')
        channel = plain(channels[source['channel']])
        if canonical_hash(channel) != source['channel_sha256']:
            raise ValueError('처리 채널의 원값/기여/선택이 달라졌습니다.')
        problem = processing_problem(channel, plan_mask=inputs.get('plan_mask'))
        problem['processing_record'] = plain(result['diagnostics']['processing_record'])
    elif source['kind'] == 'observation_chain':
        from .experiment_observation_uncertainty import read_problem
        problem = read_problem(workbench,source,plan_mask=inputs.get('plan_mask'))
    elif source['kind'] == 'retained_comparison':
        from .experiment_comparison_uncertainty import read_problem
        problem = read_problem(workbench,source['reference'],plan_mask=inputs.get('plan_mask'))
    else:
        raise ValueError('실제 저장한 원자료/처리 채널을 선택하세요.')
    problem['source'] = deepcopy(source)
    return plain(problem)


def selected_problem(workbench, reference, *, consumer='read'):
    from .numerical_candidate_evidence import resolve_candidate_evidence
    from .experiment_final_diagnosis import problem_from_evidence
    owner = workbench.numerical_documents
    resolved = resolve_candidate_evidence(owner, reference, consumer=consumer)
    submitted = None
    if resolved['snapshot']['fit_input']['inputs'].get('frozen_inclusion') is not None:
        # Reuse the same immutable historical owner/source readers as the
        # existing Numerical evidence gate. No live Plan, re-freeze or submit.
        from .numerical_candidate_evidence import _saved_owner
        from .numerical_candidate_detail import _source
        _, historical = _saved_owner(owner, reference['document_id'], reference['saved_revision'])
        exact = resolved['snapshot']['source']
        from .portable_project_execution import execution_read
        bridge = execution_read(historical, reference['document_id'], exact['job_id'])
        if bridge is not None:
            if bridge.source != reference['source'] or bridge.execution_source != exact:
                raise ValueError('Selected evidence and portable execution identities differ')
            historical = bridge.reader
            identifier = bridge.execution_source['document_id']
        else:
            identifier = reference['document_id']
        _, run, _, _ = _source(historical, identifier, exact['job_id'], exact)
        submitted = run['arguments']
    return problem_from_evidence(resolved, submitted_arguments=submitted)


def prepare_request(workbench, request):
    """Explicit Plan preview/submission: reads only; no evaluator is prepared."""
    from .assist.experts import validate_plan_request
    from .experiment_final_diagnosis import evaluation_plan, _admission, read_jacobian
    plan = validate_plan_request(request)['plan']
    operation, inputs = plan['operation'], plan['inputs']
    if operation not in OPERATIONS:
        raise ValueError('시험 분석 명시 작업을 선택하세요.')
    args = {'request': deepcopy(plan), 'execution': {'mode': 'serial', 'workers': 1,
            'threads': 1, 'max_evaluations': plan['budget']['evaluations']}}
    if operation == 'experiment_uncertainty':
        args['problem'] = source_problem(workbench, inputs)
        args['cost'] = {'model_evaluations': 0, 'provider_calls': 0, 'operation': 'analytic first-order propagation'}
    else:
        args['problem'] = selected_problem(workbench, inputs['evidence_reference'])
        issue = _admission(args['problem'])
        if issue:
            args['cost'] = {'model_evaluations': 0, 'reason': issue}
        elif inputs.get('reuse_result'):
            retained = _retained(workbench, inputs['reuse_result'])
            read_jacobian(retained, args['problem'])
            args['cost'] = {'model_evaluations': 0, 'reused_retained_jacobian': True}
        else:
            args['cost'] = evaluation_plan(args['problem'], inputs.get('relative_step', 1e-4))
        # Backend identity is required before new evaluation, not for reading
        # a historical result on a machine without that solver.
        if not issue and not inputs.get('reuse_result'):
            from .numerical_candidate_detail import backend_binding
            backend = args['problem']['fit_input']['inputs']['backend']
            actual = backend_binding(workbench, backend)
            expected = args['problem']['fit_input'].get('evaluator_binding')
            if expected is None:
                raise ValueError('원 피팅 evaluator 결합이 없습니다. 요약 읽기는 유지하지만 새 최종점 평가를 제출하지 않습니다.')
            if expected != actual:
                raise ValueError('원 피팅 evaluator 등록/설정/버전과 현재 실행기가 다릅니다.')
            args['evaluator_binding'] = actual
            # Existing Workbench resource_request must see the REAL solver and
            # settings. Do not reserve one CPU while a nested native solver
            # inherits a larger thread allocation. Reads/reuse reserve no solver.
            args['backend'] = backend
            args['experiments'] = deepcopy(args['problem']['experiments'])
    args['problem_sha256'] = canonical_hash(args['problem'])
    return args


def validate_prepared(workbench, operation, arguments):
    """Both admission and execution re-resolve exact refs; never downgrade CAS."""
    supplied = deepcopy(arguments)
    supplied.pop('label', None)
    if operation not in OPERATIONS or supplied.get('request', {}).get('operation') != operation:
        raise ValueError('시험 분석 명령과 원 Plan이 다릅니다.')
    actual = prepare_request(workbench, supplied['request'])
    if canonical_hash(actual) != canonical_hash(supplied):
        raise ValueError('시험 분석의 원자료/보존 후보/예산이 달라졌습니다. 원 요청을 보존하고 새로 검토하세요.')
    return actual


def _evaluator(workbench, problem, identifier):
    """Select existing registered factories, exactly as Workbench Numerical does."""
    from .backends import get_backend
    backend = problem['fit_input']['inputs']['backend']
    folder = workbench.root / 'results' / identifier
    if backend == 'evaluation.definition':
        from .evaluation_definition import DefinitionFactory
        from .research_execution import run_domain
        experiments = [e for e in problem['experiments'] if e['role'] == 'fit']
        settings = experiments[0]['settings']
        if set(settings) != {'definition_ref'} or any(e['settings'] != settings for e in experiments):
            raise ValueError('동일한 저장 EvaluationDefinition을 선택하세요.')
        compiled = workbench.evaluation_documents.from_reference(settings['definition_ref'])
        if compiled['definition'].get('reuse'):
            raise ValueError('차분점 사이에 상태를 재사용하지 않습니다.')
        return DefinitionFactory(compiled, folder/'evaluations', lambda model, output: run_domain(workbench, model, output)), True
    if backend in workbench.config.get('external_backends', {}):
        from .adapters.external_files import FileEvaluationFactory
        return FileEvaluationFactory(backend, workbench.config['external_backends'][backend], workbench.root/'native'/identifier), False
    adapter = get_backend(backend)
    if backend == 'material.mfront.prepared' or (not callable(adapter) and not callable(getattr(adapter, 'prepare', None))):
        from .adapters.native_evaluation import NativeEvaluationFactory
        owns_files = backend != 'material.mfront.prepared'
        return NativeEvaluationFactory(backend, folder/'evaluations' if owns_files else workbench.root/'native'/identifier,
            response_selection=list(dict.fromkeys(e['response'] for e in problem['experiments'] if e['role'] == 'fit')),
            retained_root=folder if owns_files else None), owns_files
    return backend, False


def execute(workbench, operation, arguments, identifier):
    from .experiment_uncertainty import propagate
    from .experiment_final_diagnosis import evaluate_final, read_jacobian, _admission
    from .execution_control import check_cancelled
    args = validate_prepared(workbench, operation, arguments)
    check_cancelled()
    plan, problem = args['request'], args['problem']
    owns_files = False
    if operation == 'experiment_uncertainty':
        try:
            result = propagate(problem, plan['inputs']['specification'])
        except (ValueError, TypeError, KeyError) as error:
            # An invalid explicit uncertainty request is a retained diagnostic,
            # never loss of the source measurements or the supplied recipe.
            result = {'kind': 'experiment_uncertainty', 'execution_status': 'REJECTED',
                'responses': {}, 'checks': [], 'failure_reason': str(error),
                'experiment_analysis': {'source_problem': problem,
                    'propagation': {'status': 'UNKNOWN', 'reason': str(error)},
                    'specification': deepcopy(plan['inputs']['specification']),
                    'engineering_release': 'NOT_RELEASED'},
                'timing': {'model_calls': 0, 'budget_used': 0}}
    else:
        # Admission failures produce an explicit saved UNKNOWN diagnostic with
        # zero evaluations. They never substitute a later successful attempt.
        if _admission(problem):
            result = evaluate_final(None, problem, budget_evaluations=plan['budget']['evaluations'])
        elif plan['inputs'].get('reuse_result'):
            selected_problem(workbench, plan['inputs']['evidence_reference'], consumer='success_report')
            retained = _retained(workbench, plan['inputs']['reuse_result'])
            record = read_jacobian(retained, problem)
            result = {'kind': 'experiment_identification', 'execution_status': 'SUCCEEDED', 'responses': {},
                'identification': deepcopy(retained['identification']), 'checks': [],
                'experiment_analysis': {'source_problem': problem, 'problem_sha256': args['problem_sha256'],
                    'ordinary_jacobian': record, 'reused_result': deepcopy(plan['inputs']['reuse_result']),
                    'attempts': [], 'optimization_performed': False, 'holdout_evaluations': 0,
                    'engineering_release': 'NOT_RELEASED'}, 'timing': {'model_calls': 0, 'budget_used': 0}}
        else:
            # Mandatory success consumer gate, not readiness-only permission.
            selected_problem(workbench, plan['inputs']['evidence_reference'], consumer='success_report')
            evaluator, owns_files = _evaluator(workbench, problem, identifier)
            result = evaluate_final(evaluator, problem, budget_evaluations=plan['budget']['evaluations'],
                relative_step=plan['inputs'].get('relative_step', 1e-4), execution=args['execution'])
    result['experiment_analysis']['request'] = deepcopy(plan)
    result['experiment_analysis']['source_problem_sha256'] = args['problem_sha256']
    # Recheck cancellation after analytic/replay work; keep computed data but
    # do not declare a successfully completed user action after observed stop.
    from .execution_control import ExecutionCancelled
    try:
        check_cancelled()
    except ExecutionCancelled as error:
        result['execution_status'] = 'CANCELLED'
        result['failure_reason'] = str(error)
    if owns_files:
        from .evaluation import save_evaluation, file_hash
        folder = workbench.root/'results'/identifier
        result['artifacts'] = [{'path': p.relative_to(folder).as_posix(), 'sha256': file_hash(p)}
                               for p in sorted(folder.rglob('*')) if p.is_file()]
        save_evaluation(result, folder, existing=folder.exists())
    return result


def preview_owner(owner, identifier, arguments, *, session_id, expected_generation):
    """Read-only command over the current Plan; no command receipt or mutation."""
    if arguments != {} or session_id != owner.session_id or type(expected_generation) is not int:
        raise ValueError('현재 Plan과 세션의 원자료/비용을 읽으세요.')
    with owner._lock(identifier):
        document = owner.read(identifier)
        if document['generation'] != expected_generation:
            raise ValueError('Plan이 변경되었습니다. 입력을 보존하고 현재 문서를 다시 읽으세요.')
        draft = document['draft']
        if draft.get('mode') != 'request' or draft['request'].get('operation') not in OPERATIONS:
            raise ValueError('시험 분석 Request Plan을 선택하세요.')
        prepared = owner.job_arguments(draft)
        return {'document': document, 'preview': {'problem': prepared['problem'], 'cost': prepared['cost'],
            'executed': False, 'provider_calls': 0, 'model_calls': 0}}


def validate_report_capture(workbench, reference):
    """A diagnostic result is not a shortcut around immutable detail gates."""
    if not isinstance(reference, dict) or reference.get('kind') != 'result':
        return
    exact = {k: reference[k] for k in ('document_id','job_id','input_revision','input_sha256','result_sha256')}
    result = _retained(workbench, exact)
    if result.get('kind') != 'experiment_identification':
        return
    from .experiment_final_diagnosis import read_jacobian
    data = result['experiment_analysis']
    problem = data['source_problem']
    success = result.get('execution_status') == 'SUCCEEDED'
    consumer = 'success_report' if success else ('failure_report' if problem['evidence_reference']['purpose'] == 'failure_diagnostic' else 'read')
    verified = selected_problem(workbench, problem['evidence_reference'], consumer=consumer)
    if canonical_hash(problem) != canonical_hash(verified):
        raise ValueError('최종점 진단과 원 후보/상세 근거가 다릅니다.')
    if success:
        read_jacobian(result, problem)


def matches_followup_source(request, source_reference, *, workbench=None):
    """Exact source binding for the EXISTING idempotent result→Plan handoff.

    Called after Workbench has validated/prepared the explicit request. No
    canonical Data alias and no new creation/receipt machinery are introduced.
    """
    keys = ('document_id','job_id','input_revision','input_sha256','result_sha256')
    operation = request.get('operation')
    inputs = request.get('inputs', {})
    if operation == 'experiment_uncertainty':
        source = inputs.get('source', {})
        if source.get('kind')=='observation_chain':
            original=deepcopy(request);original['inputs']['source']=deepcopy(source['base'])
            return matches_followup_source(original,source_reference,workbench=workbench)
        selected = source.get('reference') if source.get('kind') == 'result_response' else None
        if source.get('kind') == 'retained_comparison' and workbench is not None:
            # The original A result anchors the established handoff receipt.
            # The frozen problem separately binds the saved comparison and B.
            selected = source_problem(workbench, inputs)['operand_references']['A']
        if source.get('kind') == 'processing_channel' and workbench is not None:
            # The original Data result anchors the existing idempotent handoff;
            # the Plan ALSO retains the exact published processing/channel SHA.
            p = source_problem(workbench, inputs)
            origin = p['processing_record']['source']
            selected = workbench.document_result_reference(origin['document_id'], origin['job_id'])
            if any(selected[k] != origin[k] for k in keys[:-1]):
                return False
    elif operation == 'identification_final':
        selected = inputs.get('evidence_reference', {}).get('source')
    else:
        return False
    return (isinstance(selected,dict) and all(k in selected and k in source_reference for k in keys)
            and {k:selected[k] for k in keys} == {k:source_reference[k] for k in keys})
