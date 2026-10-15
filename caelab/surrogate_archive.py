"""Numeric-only archives for the pinned SciPy RBF implementation.

The archive carries solved coefficients, not executable pickle or a refit recipe.
SciPy's existing __setstate__/evaluation path is used only after version/shape
checks. Local archives retain training ordinates and a declared neighborhood rule;
only an explicit new-point prediction solves local coefficients. Reading retained
predictions and restoring an archive never fit or predict.
"""
from copy import deepcopy
import numpy as np
import scipy
from scipy.interpolate import RBFInterpolator


def archive(model):
    rbf = model.model
    first, solved = rbf.__getstate__()
    y, d, d_shape, d_dtype, neighbors, smoothing, kernel, epsilon, powers = first
    if tuple(d_shape) or np.dtype(d_dtype) != np.dtype('float64'):
        raise ValueError('Stored research RBF requires a real scalar response')
    result = {'status': 'AVAILABLE', 'format': 'scipy-global-rbf-v1', 'scipy_version': scipy.__version__,
        'variables': deepcopy(model.variables), 'response': deepcopy(model.response),
        'validation': deepcopy(model.validation), 'support': [a.tolist() for a in model.support],
        'state': {'y': y.tolist(), 'd': d.tolist(), 'smoothing': smoothing.tolist(),
            'kernel': kernel, 'epsilon': float(epsilon), 'powers': powers.tolist()}}
    if neighbors is None:
        shift, scale, coefficients = solved
        result['state'].update(shift=shift.tolist(), scale=scale.tolist(), coefficients=coefficients.tolist())
    else:
        result.update(format='scipy-local-rbf-v1', neighborhood={
            'neighbors': int(neighbors), 'metric': 'euclidean',
            'coordinates': 'linear_normalized_variable_bounds',
            'new_point_operation': 'SOLVE_LOCAL_COEFFICIENTS',
            'retained_predictions': 'parent_result.predictions'})
    return result


def restore(value):
    from .numerical import Surrogate, _variables
    if (not isinstance(value, dict) or value.get('status') != 'AVAILABLE'
            or value.get('format') not in {'scipy-global-rbf-v1', 'scipy-local-rbf-v1'}
            or value.get('scipy_version') != scipy.__version__):
        raise ValueError('Stored RBF format/version unavailable; explicitly train a new model, never refit on reopen')
    variables = _variables(value['variables'])
    state = value['state']
    local = value['format'] == 'scipy-local-rbf-v1'
    keys = {'y','d','smoothing','kernel','epsilon','powers'}
    if set(state) != (keys if local else keys | {'shift','scale','coefficients'}):
        raise ValueError('Invalid numeric RBF archive fields')
    arrays = {name: np.asarray(state[name], dtype=float) for name in
        (('y','d','smoothing','powers') if local else ('y','d','smoothing','powers','shift','scale','coefficients'))}
    if any(not np.all(np.isfinite(a)) for a in arrays.values()):
        raise ValueError('RBF archive contains nonfinite values')
    y, d, powers = arrays['y'], arrays['d'], arrays['powers']
    dimensions = len(variables)
    if powers.size == 0:
        powers = powers.reshape(0, dimensions)
    if (y.ndim != 2 or y.shape[1] != dimensions or not len(y)
            or d.shape != (len(y),1) or powers.ndim != 2 or powers.shape[1] != dimensions
            or np.any(powers < 0) or not np.array_equal(powers, np.floor(powers))
            or arrays['smoothing'].shape != (len(y),)):
        raise ValueError('Invalid RBF archive dimensions')
    if not local and (arrays['shift'].shape != (dimensions,) or arrays['scale'].shape != (dimensions,)
            or np.any(arrays['scale'] <= 0) or arrays['coefficients'].shape != (len(y)+len(powers),1)):
        raise ValueError('Invalid RBF archive dimensions')
    if state['kernel'] not in {'linear','thin_plate_spline','cubic','quintic','multiquadric',
                               'inverse_multiquadric','inverse_quadratic','gaussian'}:
        raise ValueError('Unknown stored RBF kernel')
    epsilon = float(state['epsilon'])
    support = np.asarray(value['support'], dtype=float)
    if (not np.isfinite(epsilon) or support.shape != (2,dimensions)
            or not np.all(np.isfinite(support)) or np.any(support[0] > support[1])):
        raise ValueError('Invalid RBF support or shape parameter')
    # Explicit numeric conversion above prevents deserializing code or objects.
    neighbors = None
    if local:
        from scipy.spatial import KDTree
        neighborhood = value.get('neighborhood', {})
        neighbors = neighborhood.get('neighbors')
        if (neighborhood != {'neighbors': neighbors, 'metric': 'euclidean',
                'coordinates': 'linear_normalized_variable_bounds',
                'new_point_operation': 'SOLVE_LOCAL_COEFFICIENTS',
                'retained_predictions': 'parent_result.predictions'}
                or type(neighbors) is not int or not max(1,len(powers)) <= neighbors <= len(y)
                or len(np.unique(y, axis=0)) != len(y) or np.any(arrays['smoothing'] < 0)):
            raise ValueError('Invalid local RBF neighborhood/training state')
        solved = (KDTree(y),)  # Spatial index only: no coefficient fit or prediction.
    else:
        solved = (arrays['shift'],arrays['scale'],arrays['coefficients'])
    rbf = RBFInterpolator.__new__(RBFInterpolator)
    rbf.__setstate__(((y,d,(),np.dtype('float64'),neighbors,arrays['smoothing'],
        state['kernel'],epsilon,powers.astype(int)),
        solved))
    return Surrogate(rbf,variables,deepcopy(value['response']),deepcopy(value['validation']),support)


def predict(retained, points):
    model = restore(retained.get('model_artifact', {}))
    local = model.model.neighbors is not None
    return {'kind': 'surrogate', 'execution_status': 'SUCCEEDED',
        'predictions': model.predict(points), 'variables': deepcopy(model.variables),
        'response': deepcopy(model.response), 'validation': deepcopy(retained.get('validation', model.validation)),
        'model_artifact': deepcopy(retained['model_artifact']),
        'training_performed': False, 'solver_execution': 'NOT_PERFORMED',
        'prediction_operation': 'SOLVE_LOCAL_COEFFICIENTS' if local and points else 'STORED_GLOBAL_COEFFICIENTS' if not local else 'NO_QUERY',
        'local_coefficients_computed': bool(local and points),
        'limitations': [('Explicit new-point prediction solves local coefficients from archived training data.' if local
                        else 'Predictions use stored coefficients.') + ' Predictions are not actual evaluator results.']}


def validate_search(retained, variables, objective, constraints=None):
    """Admit meanings, not an arbitrary reinterpretation of a saved predictor."""
    from .numerical import _variables
    artifact = retained.get('model_artifact', {})
    saved = _variables(artifact.get('variables', []))
    selected = _variables(variables)
    if ([(v['id'],v['unit'],v['transform']) for v in selected] !=
            [(v['id'],v['unit'],v['transform']) for v in saved]):
        raise ValueError('Saved surrogate variable order, units and transforms must match the selected search')
    if any(a['lower'] < b['lower'] or a['upper'] > b['upper'] for a,b in zip(selected,saved)):
        raise ValueError('Search bounds must lie within the saved normalization bounds; training-support extrapolation remains marked')
    definition = artifact.get('response', {})
    fields = ('response','unit','reduction','component','location','measure','frame','coordinate_system','coordinate_frame')
    for declaration in [objective] + list(constraints or []):
        if any(declaration.get(k) != definition.get(k) for k in fields):
            raise ValueError('Search response/unit/reduction/physical meaning differs from the saved surrogate')
    return selected


def search(retained, variables, objective, *, constraints=None, seed=0, options=None, execution=None, source_ref=None):
    """Explicit prediction-only search through the existing differential evolution.

    The private objective callback supplies numeric predictions to that existing
    optimizer. Every externally retained candidate is marked PREDICTED before
    returning, and cannot pass Numerical's actual-response/adoption gates.
    """
    from . import numerical
    from .storage import canonical_hash
    variables = validate_search(retained,variables,objective,constraints)
    model = restore(retained.get('model_artifact', {}))
    declaration = model.response
    def predicted_objective(values, settings):
        row = model.predict([values])[0]
        response = deepcopy(row['responses'][declaration['response']])
        # The optimizer computes only a mathematical recommendation. Its normal
        # actual-response gate remains unchanged outside this private callback.
        response.update({k:deepcopy(v) for k,v in declaration.items() if k != 'response'})
        return {'execution_status':'SUCCEEDED','responses':{declaration['response']:response},
                'out_of_range':row['out_of_range']}
    result = numerical.optimize(predicted_objective,variables,objective,constraints=constraints,
                                seed=seed,options=options,execution=execution)
    for row in result['candidates'] + ([result['best']] if result.get('best') else []):
        if row.get('execution_status') == 'SUCCEEDED':
            row.update(execution_status='PREDICTED',prediction_status='PREDICTED',
                       predicted_feasible=row.pop('feasible',False),actual_evaluation_performed=False)
            row['prediction_source']={'model_sha256':canonical_hash(retained['model_artifact']),
                                      'result_ref':deepcopy(source_ref)}
            point=np.asarray([row['values'][v['id']] for v in model.variables])
            row['out_of_range']=bool(np.any(point<model.support[0]) or np.any(point>model.support[1]))
    # Existing optimizer timing counts mathematical callback calls. They are
    # retained separately and never advertised as native/physical dispatches.
    result.update(kind='surrogate',surrogate_operation='search',response=deepcopy(declaration),
        predictions=deepcopy(result['candidates']),model_artifact=deepcopy(retained['model_artifact']),
        validation=deepcopy(retained.get('validation',model.validation)),training_performed=False,
        solver_execution='NOT_PERFORMED',actual_evaluation_count=0,
        prediction_count=sum(r.get('execution_status')=='PREDICTED' for r in result['candidates']),
        local_coefficients_computed=bool(model.model.neighbors is not None and result['candidates']),
        prediction_operation='SOLVE_LOCAL_COEFFICIENTS' if model.model.neighbors is not None else 'STORED_GLOBAL_COEFFICIENTS')
    result['timing']['prediction_calls']=result['timing'].get('dispatched_evaluations_total',0)
    result['timing']['dispatched_evaluations_total']=0
    result['limitations'] += ['Recommended candidates and constraint satisfaction are predictions only. Explicit actual evaluation is required before adoption.']
    return result


def confirmation_values(prediction, actual, point):
    """Compare already retained records, never predict or execute in a reader."""
    from .numerical import _scalar, EvaluationFailed
    matches=[row for row in prediction.get('predictions',[]) if row.get('values')==point]
    if (not matches or any(row.get('execution_status')!='PREDICTED' for row in matches)
            or any(row.get('responses')!=matches[0].get('responses') for row in matches[1:])):
        raise ValueError('Select one exact retained prediction at the confirmation point')
    if actual.get('values')!=point:
        raise ValueError('Actual evaluation coordinates differ from the predicted point')
    definition=deepcopy(prediction.get('response',{}))
    if not definition:
        raise ValueError('The stored prediction lacks its physical response definition')
    response=matches[0].get('responses',{}).get(definition['response'],{})
    predicted=response.get('value')
    if (response.get('unit')!=definition['unit'] or type(predicted) not in (int,float)
            or not np.isfinite(predicted)):
        raise ValueError('The retained prediction value or unit is unavailable')
    reason=''
    try:
        value=_scalar(actual,definition)
    except (EvaluationFailed,ValueError,KeyError,TypeError) as error:
        value=None;reason=str(error)
    return {'definition':definition,'values':deepcopy(point),'predicted':predicted,
            'actual':value,'difference':value-predicted if value is not None else None,
            'actual_status':actual.get('execution_status','UNKNOWN'),'reason':reason}



def validate_confirmation_request(training_draft,actual_draft):
    """Same-model confirmation is narrower than comparing arbitrary experiments."""
    from .numerical import _variables
    from .storage import canonical_hash
    original=training_draft.get('request',{}).get('inputs',{})
    actual_request=actual_draft.get('request',{})
    actual=actual_request.get('inputs',{})
    def changed(part):
        raise ValueError('평가 조건 변경: '+part+'. 같은 모델의 예측 확인으로 비교할 수 없습니다. 원래 결과는 유지됩니다.')
    if actual_request.get('operation')!='doe':
        changed('확인 방법')
    if original.get('backend')!=actual.get('backend'):
        changed('평가기')
    if not isinstance(original.get('settings'),dict) or canonical_hash(original['settings'])!=canonical_hash(actual.get('settings')):
        changed('고정 설정')
    def declarations(value):
        return [(row['id'],row['unit'],row['transform']) for row in _variables(value.get('variables'))]
    if declarations(original)!=declarations(actual):
        changed('변수 순서·단위·변환')
    def model(draft):
        ref=draft.get('model_source')
        if ref is not None:return ref
        source=draft.get('source')
        if not isinstance(source,dict):return None
        if 'pde_document_id' in source:
            return {**{key:value for key,value in source.items() if key!='pde_document_id'},
                    'kind':'pde','document_id':source['pde_document_id']}
        return source if source.get('kind') in {'material','pde','simulation','evaluation'} else None
    if model(training_draft)!=model(actual_draft):
        changed('저장 모델')
