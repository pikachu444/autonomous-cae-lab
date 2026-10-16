"""First-order uncertainty of a saved comparison's physical difference B−A.

Use the existing comparison alignment and joint-covariance engine. Inputs are
the original scalar samples, never interpolated standard deviations. There is
no calibration replay, guessed independence, weighted-residual propagation or
uncertainty interpolation across calculation gaps.
"""
from copy import deepcopy
import numpy as np

from .data_comparison import compare_data_curves
from .experiment_uncertainty import MAX_SAMPLES, MAX_VARIABLES, METADATA, PropagationUnavailable, plain
from .storage import canonical_hash


def read_problem(reader, reference, *, plan_mask=None):
    """Same exact public owner/retained-result reads in server and GUI preview."""
    payload = reader.research_reference(reference)
    if payload.get('status') != 'AVAILABLE' or payload.get('kind') != 'comparison':
        raise ValueError('현재 읽을 수 있는 저장된 비교를 선택하세요.')
    record = payload['comparison']
    a,b = record['binding']['source'],record['binding']['prediction_source']
    if all(a[k] == b[k] for k in ('document_id','job_id','response')):
        raise PropagationUnavailable('같은 원 응답의 자기 비교는 별도 불확실 입력으로 전파하지 않습니다. 원 비교는 그대로 읽을 수 있습니다.')
    operands, references = {}, {}
    for side, key in (('A','source'),('B','prediction_source')):
        binding = record['binding'][key]
        exact = reader.document_result_reference(binding['document_id'], binding['job_id'])
        if any(exact[k] != binding[k] for k in ('document_id','job_id','input_revision','input_sha256')):
            raise ValueError('저장된 비교의 원 입력 개정이 달라졌습니다.')
        result = reader.document_result(binding['document_id'], binding['job_id'], selection=[binding['response']])
        response = result['responses'][binding['response']]
        if result.get('execution_status') != 'SUCCEEDED' or canonical_hash(response) != binding['response_sha256']:
            raise ValueError('저장된 비교의 원 응답 값 또는 물리 정의가 달라졌습니다.')
        operands[side], references[side] = response, exact
    problem = comparison_problem(record, operands['A'], operands['B'])
    if plan_mask is not None:
        from .experiment_uncertainty import _mask
        problem['included'] = [a and b for a,b in zip(problem['included'],_mask(plan_mask,len(problem['included']),'Plan mask'))]
    problem['operand_references'] = references
    problem['source'] = {'kind':'retained_comparison','reference':deepcopy(reference)}
    return plain(problem)


def comparison_problem(record, observation, prediction):
    """Jacobian of existing linear alignment at the declared fixed coordinates."""
    observation, prediction, record = map(plain, (observation, prediction, record))
    saved = record['comparison']
    page = record['page']
    start, count = page['start'], page['count']
    original = deepcopy(observation)
    if original['kind'] not in ('scalar','series'):
        raise PropagationUnavailable('차이 전파는 저장된 스칼라 또는 한 축 곡선 비교를 지원합니다.')
    values = original['value'] if isinstance(original['value'],list) else [original['value']]
    n = len(values)
    stop = min(n, start+count)
    if not 0 <= start < stop or stop-start > MAX_SAMPLES:
        raise PropagationUnavailable('비교의 원 표본 구간을 명시 한도 안에서 선택하세요.')
    chosen = list(range(start,stop))
    observation['value'] = values[start:stop]
    for axis in observation.get('axes',[]):
        axis['values'] = axis['values'][start:stop]
    for key in ('source_rows',):
        if key in observation:
            if len(observation[key]) != n:
                raise ValueError('관측 원행과 표본 길이가 다릅니다.')
            observation[key] = observation[key][start:stop]
    # Check the SAME physical contract and interpolation/gap rules as the saved comparison.
    actual = compare_data_curves(prediction, observation, weight=saved['weight'], scale=saved['scale'], mask=saved['mask'])
    if (actual['prediction'] != saved['prediction'] or actual['observation']['value'] != saved['observation']['value']
            or actual['mask'] != saved['mask']):
        raise ValueError('저장된 비교의 시각 정렬·선택·관측 값과 원자료가 다릅니다.')
    included = saved['mask']
    if not any(included):
        raise PropagationUnavailable('전파에 사용할 유효 비교 표본을 선택하세요.')
    a = np.asarray(observation['value'],dtype=float)
    b = np.asarray(prediction['value'],dtype=float).reshape(-1)
    if original['kind']=='series':
        target = np.asarray(observation['axes'][0]['values'],dtype=float)
        axis = np.asarray(prediction['axes'][0]['values'],dtype=float)
    else:
        target, axis = np.array([0.]), np.array([0.])
    weights = []
    for index, good in enumerate(included):
        if not good:
            weights.append({});continue
        x = target[index]
        j = int(np.searchsorted(axis,x))
        if j < len(axis) and axis[j] == x:
            weights.append({j:1.})
        else:
            if j == 0 or j == len(axis):
                raise PropagationUnavailable('원 비교 범위 밖의 시각으로 전파하지 않습니다.')
            t = float((x-axis[j-1])/(axis[j]-axis[j-1]))
            weights.append({j-1:1-t,j:t})
    used_b = sorted({j for row in weights for j in row})
    variables = []
    columns = {}
    for side, indexes, response, vals in (('A',[chosen[i] for i,ok in enumerate(included) if ok],original,values),
                                          ('B',used_b,prediction,b)):
        rows = response.get('source_rows')
        if rows is not None and len(rows) != len(vals):
            raise ValueError(side+'의 원행과 값 길이가 다릅니다.')
        for index in indexes:
            identifier = side+':'+str(index)
            columns[identifier] = len(variables)
            variable = {'id':identifier,'unit':response['unit'],'value':float(vals[index]),
                        'operand':side,'sample_index':index,'label':('관측 A' if side=='A' else '예측 B')}
            if rows is not None:variable['source_row']=rows[index]
            variables.append(variable)
    if len(variables)>MAX_VARIABLES:
        raise PropagationUnavailable('전파 입력 한도를 넘습니다. 더 짧은 저장 비교 구간을 선택하세요.')
    G = np.zeros((len(chosen),len(variables)))
    differences = []
    for i, good in enumerate(included):
        if not good:
            differences.append(None);continue
        G[i,columns['A:'+str(chosen[i])]] = -1.
        for j,w in weights[i].items():G[i,columns['B:'+str(j)]] = w
        differences.append(saved['prediction'][i]-float(a[i]))
    supplied = [{'operand':side,'provided_output_uncertainty':deepcopy((response.get('calibration') or {}).get('uncertainty'))}
                for side,response in (('A',original),('B',prediction))]
    return {'kind':'comparison_difference','variables':variables,'sensitivities':G.tolist(),
        'included':included,'sample_ids':['comparison:'+str(i) for i in chosen],'values':differences,
        'unit':observation['unit'],'metadata':{k:observation.get(k,'UNKNOWN') for k in METADATA},
        'original':{**({'raw_samples':{'source_rows':observation['source_rows']}} if 'source_rows' in observation else {}),
                    'axis':({'values':target.tolist(),'name':observation['axes'][0]['name'],'unit':observation['axes'][0]['unit']}
                            if original['kind']=='series' else {'values':chosen,'name':'표본 순서','unit':'1'}),
                    'observation':observation,'prediction':prediction,'comparison':saved},
        'alignment':{'policy':actual['alignment_policy'],'prediction_weights':weights,'observation_indexes':chosen,
                     'weight':saved['weight'],'scale':saved['scale'],'weighted_residual_propagated':False},
        'coefficient_basis':'exact linear value alignment of retained comparison; difference B-A, not normalized residual',
        'supplied_output_uncertainty':supplied,'calibration_reapplied':False}
