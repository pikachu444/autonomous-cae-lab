"""Pure admission/metadata for the first discrete adjoint, never a solver import."""
from copy import deepcopy

BACKEND = 'thermal.scikit_fem.rectangle'
METHOD = 'slsqp_adjoint'
SUPPORTED_INPUTS = {'conductivity', 'heat_source', 'boundary_temperature', 'conductivity_reference_temperature'}
RESPONSE = 'mean_temperature'
RESIDUAL_LIMIT = 1e-10
CENTRAL_H = 1e-5
CENTRAL_ATOL = 2e-7
CENTRAL_RTOL = 3e-5
TAYLOR_H = (0.04, 0.02, 0.01, 0.005)
TAYLOR_ORDER = (1.7, 2.3)
FIRST_ORDER = (0.8, 1.2)
ROUNDOFF_FACTOR = 1e-10


def describe(backend, settings):
    reasons = []
    if backend != BACKEND:
        reasons.append('첫 adjoint는 정상 선형 열전도만 지원합니다. 다른 분야·연성은 차분 진화를 사용하세요.')
    elif settings['conductivity']['beta'] != 0. or settings['linearization_temperature'] is not None:
        reasons.append('온도의존 Picard/고정 선형화장은 total adjoint 지원 밖입니다. 차분 진화를 사용하세요.')
    elif min(settings['mesh']['cells']) < 2:
        reasons.append('자유 내부 DOF가 있는 메시가 필요합니다.')
    return {'method': METHOD, 'available': not reasons, 'reasons': reasons,
            'algorithm': 'discrete_linear_adjoint', 'state': 'steady_linear_fixed_mesh',
            'response': RESPONSE, 'unit': 'K', 'reduction': 'native_integral',
            'supported_inputs': sorted(SUPPORTED_INPUTS),
            'boundary': 'all-boundary affine Dirichlet; T0 design dependence included',
            'excluded': ['nonlinear_total', 'coupled', 'geometry', 'transient', 'nonsmooth_reduction', 'dependent_or_discrete_variables'],
            'primal_cost': 1, 'adjoint_cost_per_response': 1, 'runtime': 'NOT_PROBED'}


def admit_settings(backend, settings, request):
    info = describe(backend, settings)
    if not info['available']:
        raise ValueError('; '.join(info['reasons']))
    if (not isinstance(request, dict) or set(request) != {'response', 'inputs'}
            or request['response'] != RESPONSE or not isinstance(request['inputs'], list)
            or not request['inputs'] or len(set(request['inputs'])) != len(request['inputs'])
            or set(request['inputs']) - SUPPORTED_INPUTS):
        raise ValueError('선언된 평균 온도와 지원 입력을 선택하세요. 유한차분 대체는 하지 않습니다.')
    return deepcopy(request)


def describe_definition(compiled):
    d = compiled['definition']; stages = compiled['stages']
    if len(stages) != 1 or d['transfers'] or d['iteration']['enabled'] or d.get('reuse'):
        return {'method': METHOD, 'available': False,
                'reasons': ['선형 단일 단계/고정 메시만 adjoint 지원합니다. 반복·전달·연성에는 차분 진화를 사용하세요.']}
    stage = next(iter(stages)); model = stages[stage]['model']
    info = describe(model['backend'], model['settings'])
    info.update(stage=stage, responses=[r['id'] for r in d['responses']
                if r['stage'] == stage and r['response'] == RESPONSE and r['unit'] == 'K'])
    if not info['responses']:
        info['available'] = False; info['reasons'].append('평균 온도 응답을 K로 내보내야 합니다.')
    return info


def configure(compiled, variables, responses):
    from .evaluation_shared_inputs import targets
    from . import variable_domains as domains
    info = describe_definition(compiled)
    if not info['available']:
        raise ValueError('; '.join(info['reasons']))
    for response in responses:
        if response.get('response') not in info['responses'] or response.get('unit') != 'K':
            raise ValueError('Adjoint 응답은 선언된 mean_temperature [K]만 지원합니다.')
        if response.get('reduction', 'native_integral') != 'native_integral':
            raise ValueError('평균 온도는 실제 적분 reduction만 지원하며 max/min으로 바꿀 수 없습니다.')
        for key, expected in [('component', 'mean_temperature'), ('location', 'domain')]:
            if key in response and response[key] != expected:
                raise ValueError('Adjoint 응답의 실제 성분/위치를 선택하세요.')
    domain = domains.VariableDomains(variables)
    if not domain.free:
        raise ValueError('Adjoint 최적화에는 자유 연속 변수가 필요합니다.')
    bindings = {b['id']: b for b in compiled['definition']['bindings']}
    selected, logical = [], []
    for v in domain.variables:
        if domains.mode(v) == 'dependent' or domains.kind(v) != 'continuous':
            raise ValueError('Adjoint는 연속 free/fixed 변수만 지원합니다. 혼합·종속 변수는 차분 진화를 사용하세요.')
        binding = bindings.get(v['id'])
        if not binding or binding['unit'] != v['unit']:
            raise ValueError('변수는 저장된 Evaluation의 실제 입력과 단위가 일치해야 합니다.')
        if 'bounds' in binding and domains.mode(v)=='free' and (v['lower']<binding['bounds'][0] or v['upper']>binding['bounds'][1]):
            raise ValueError('Plan 변수 범위가 저장된 공유 입력 범위를 벗어났습니다.')
        if domains.mode(v) == 'fixed':
            continue
        if any(t['input_id'] not in SUPPORTED_INPUTS for t in targets(binding)):
            raise ValueError('이 입력의 미분은 지원하지 않습니다. 차분 진화를 사용하세요: ' + v['id'])
        selected.extend(t['input_id'] for t in targets(binding))
        logical.append(v['id'])
    # A fixed assignment is still an actual input. In particular a fixed beta
    # must not turn the admitted baseline into a frozen nonlinear problem.
    from .evaluation_shared_inputs import assign
    from .evaluation_definition import input_descriptors, bind_values
    initial=domain.decode(domain.encode())
    models,_=assign(compiled['definition']['bindings'],
        {key:item['model'] for key,item in compiled['stages'].items()},initial,input_descriptors,bind_values)
    actual=models[info['stage']]
    request={'response':RESPONSE,'inputs':sorted(set(selected))}
    admit_settings(actual['backend'],actual['settings'],request)
    return {'stage': info['stage'], 'request': request,
            'logical_inputs': logical, 'responses': sorted({r['response'] for r in responses})}
