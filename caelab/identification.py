"""Local first-order identifiability of an already computed fit Jacobian.

This module never evaluates a model. Scales are declared parameter search ranges
and observation residual normalization, not inferred measurement uncertainty.
"""
from copy import deepcopy
import math
import numpy as np


def diagnose(jacobian, variables, experiments, parameter_values, *, loss='linear',
             jacobian_method='2-point', active_mask=None, rtol=1e-6):
    base = {'status': 'UNKNOWN', 'method': 'scaled_residual_jacobian_svd',
        'scope': 'local_first_order_at_final_fit', 'parameter_values': deepcopy(parameter_values),
        'uncertainty': 'UNKNOWN', 'global_uniqueness': 'UNKNOWN', 'engineering_release': 'NOT_RELEASED',
        'relative_rank_tolerance': rtol, 'jacobian_method': str(jacobian_method),
        'residual_definition': 'sqrt(weight/retained_count)*(prediction-observation)/scale'}
    if loss != 'linear':
        return {**base, 'reason': 'Robust-loss Jacobian is modified by the optimizer; ordinary response diagnosis unavailable.'}
    if not variables or len(variables) > 256:
        return {**base, 'reason': 'Supported diagnosis requires 1–256 fitted parameters.'}
    J = np.asarray(jacobian, dtype=float)
    if J.ndim != 2 or J.shape[1] != len(variables) or not J.shape[0] or not np.isfinite(J).all():
        return {**base, 'reason': 'A complete finite residual Jacobian was not retained.'}
    scales = []
    for v in variables:
        lo, hi = v['lower'], v['upper']
        scales.append(math.log(hi)-math.log(lo) if v['transform'] == 'log' else hi-lo)
    A = J * np.asarray(scales)
    if not np.isfinite(A).all():
        return {**base, 'reason': 'Declared range scaling overflowed.'}
    try:
        _, singular, Vh = np.linalg.svd(A, full_matrices=A.shape[0] < A.shape[1])
    except np.linalg.LinAlgError:
        return {**base, 'reason': 'SVD did not converge; fit values are retained without an identifiability claim.'}
    tolerance = float(singular[0] * rtol) if len(singular) else 0.
    rank = int(np.sum(singular > tolerance))
    null = Vh[rank:]
    participation = np.sum(null**2, axis=0) if len(null) else np.zeros(len(variables))
    norms = np.linalg.norm(A, axis=0)
    alignment = np.divide(A.T @ A, np.outer(norms, norms),
        out=np.full((len(variables), len(variables)), np.nan), where=np.outer(norms, norms) != 0)
    rows = []
    for index, v in enumerate(variables):
        rows.append({**deepcopy(v), 'encoded_range': scales[index],
            'status': 'UNRESOLVED_LOCAL' if participation[index] > rtol**2 else 'DISTINGUISHABLE_LOCAL',
            'null_participation': float(participation[index]),
            'active_bound': int(active_mask[index]) if active_mask is not None else None})
    responses = []
    for e in experiments:
        obs = e['observations']
        if '_mask' in e:
            retained_mask = e['_mask']
        elif 'mask' in e:
            retained_mask = e['mask']
        else:
            value = obs.get('value')
            retained_mask = [obs.get('valid') is not False] * (len(value) if isinstance(value, (list, tuple, np.ndarray)) else 1)
        mask = np.atleast_1d(np.asarray(retained_mask, dtype=bool))
        responses.append({'experiment_id': e['id'], 'response': e['response'],
            'unit': obs.get('unit'), 'component': obs.get('component'), 'measure': obs.get('measure'),
            'frame': obs.get('frame'), 'location': obs.get('location'),
            'count': int(mask.sum()), 'mask': mask.tolist(), 'weight': e['weight'], 'scale': e['scale'],
            'source': deepcopy(e.get('observation_source')), 'axes': deepcopy(obs.get('axes', []))})
    def finite_list(value):
        return [[float(x) if math.isfinite(x) else None for x in row] for row in value]
    return {**base, 'status': 'LOCAL_RANK_COMPLETE' if rank == len(variables) else 'LOCAL_RANK_DEFICIENT',
        'jacobian_rank': rank, 'coefficient_count': len(variables), 'residual_count': J.shape[0],
        'condition_number': float(singular[0]/singular[-1]) if rank == len(variables) else None,
        'absolute_rank_tolerance': tolerance, 'singular_values': singular.tolist() + [0.]*(len(variables)-len(singular)),
        'parameters': rows, 'null_directions': null.tolist(), 'sensitivity_alignment': finite_list(alignment),
        'responses': responses, 'parameter_scope': 'fitted_only; fixed parameters are in the frozen run input'}


def require_independent_rows(experiments):
    """Same raw column/row cannot become holdout by renaming or recalibration."""
    owners = {}
    for e in experiments:
        source = e.get('observation_source') or {}
        obs = e.get('observations') or {}
        digest = source.get('source_sha256')
        mapping = obs.get('mapping') or {}
        column = obs.get('source_column_identity', mapping.get('column'))
        rows = obs.get('source_rows')
        if not digest or column is None or rows is None:
            continue  # Inline observations have no claimed raw provenance.
        retained_mask=e['_mask'] if '_mask' in e else e.get('mask')
        if retained_mask is None:
            retained_mask=np.ones(len(rows),dtype=bool)
        retained_mask=np.asarray(retained_mask,dtype=bool)
        if retained_mask.ndim!=1 or len(retained_mask)!=len(rows):
            raise ValueError('관측의 원본 행과 피팅/검증 선택 길이가 다릅니다.')
        for row, included in zip(rows,retained_mask):
            if not included:
                continue
            key = (digest, str(column), int(row))
            if key in owners and owners[key] != e['role']:
                raise ValueError('피팅과 검증에 같은 원본 열/행이 포함되었습니다.')
            owners[key] = e['role']
