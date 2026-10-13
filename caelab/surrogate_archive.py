"""Numeric-only archive for the pinned SciPy global RBF implementation.

The archive carries solved coefficients, not executable pickle or a refit recipe.
SciPy's existing __setstate__/evaluation path is used only after version/shape
checks. Nearest-neighbor RBF fits a local model during prediction and is therefore
explicitly excluded from the no-refit archive.
"""
from copy import deepcopy
import numpy as np
import scipy
from scipy.interpolate import RBFInterpolator


def archive(model):
    if model.model.neighbors is not None:
        return {'status': 'UNAVAILABLE', 'reason': 'Local-neighbor RBF requires fitting on each new query; select global RBF for stored-model prediction.'}
    rbf = model.model
    first, solved = rbf.__getstate__()
    y, d, d_shape, d_dtype, neighbors, smoothing, kernel, epsilon, powers = first
    if tuple(d_shape) or np.dtype(d_dtype) != np.dtype('float64'):
        raise ValueError('Stored research RBF requires a real scalar response')
    shift, scale, coefficients = solved
    return {'status': 'AVAILABLE', 'format': 'scipy-global-rbf-v1', 'scipy_version': scipy.__version__,
        'variables': deepcopy(model.variables), 'response': deepcopy(model.response),
        'validation': deepcopy(model.validation), 'support': [a.tolist() for a in model.support],
        'state': {'y': y.tolist(), 'd': d.tolist(), 'smoothing': smoothing.tolist(),
            'kernel': kernel, 'epsilon': float(epsilon), 'powers': powers.tolist(),
            'shift': shift.tolist(), 'scale': scale.tolist(), 'coefficients': coefficients.tolist()}}


def restore(value):
    from .numerical import Surrogate, _variables
    if (not isinstance(value, dict) or value.get('status') != 'AVAILABLE'
            or value.get('format') != 'scipy-global-rbf-v1'
            or value.get('scipy_version') != scipy.__version__):
        raise ValueError('Stored RBF format/version unavailable; explicitly train a new model, never refit on reopen')
    variables = _variables(value['variables'])
    state = value['state']
    if set(state) != {'y','d','smoothing','kernel','epsilon','powers','shift','scale','coefficients'}:
        raise ValueError('Invalid numeric RBF archive fields')
    arrays = {name: np.asarray(state[name], dtype=float) for name in
        ('y','d','smoothing','powers','shift','scale','coefficients')}
    if any(not np.all(np.isfinite(a)) for a in arrays.values()):
        raise ValueError('RBF archive contains nonfinite values')
    y, d, powers = arrays['y'], arrays['d'], arrays['powers']
    dimensions = len(variables)
    if powers.size == 0:
        powers = powers.reshape(0, dimensions)
    if (y.ndim != 2 or y.shape[1] != dimensions or not len(y)
            or d.shape != (len(y),1) or powers.ndim != 2 or powers.shape[1] != dimensions
            or np.any(powers < 0) or not np.array_equal(powers, np.floor(powers))
            or arrays['smoothing'].shape != (len(y),)
            or arrays['shift'].shape != (dimensions,) or arrays['scale'].shape != (dimensions,)
            or np.any(arrays['scale'] <= 0)
            or arrays['coefficients'].shape != (len(y)+len(powers),1)):
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
    rbf = RBFInterpolator.__new__(RBFInterpolator)
    rbf.__setstate__(((y,d,(),np.dtype('float64'),None,arrays['smoothing'],
        state['kernel'],epsilon,powers.astype(int)),
        (arrays['shift'],arrays['scale'],arrays['coefficients'])))
    return Surrogate(rbf,variables,deepcopy(value['response']),deepcopy(value['validation']),support)


def predict(retained, points):
    model = restore(retained.get('model_artifact', {}))
    return {'kind': 'surrogate', 'execution_status': 'SUCCEEDED',
        'predictions': model.predict(points), 'variables': deepcopy(model.variables),
        'response': deepcopy(model.response), 'validation': deepcopy(retained.get('validation', model.validation)),
        'model_artifact': deepcopy(retained['model_artifact']),
        'training_performed': False, 'solver_execution': 'NOT_PERFORMED',
        'limitations': ['Predictions use stored coefficients; they are not actual evaluator results.']}


def confirmation_values(prediction, actual, point):
    """Compare already retained records, never predict or execute in a reader."""
    from .numerical import _scalar, EvaluationFailed
    matches=[row for row in prediction.get('predictions',[]) if row.get('values')==point]
    if len(matches)!=1 or matches[0].get('execution_status')!='PREDICTED':
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
