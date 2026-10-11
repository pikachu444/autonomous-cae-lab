"""Retained Data comparison through the established numerical residual contract."""
from copy import deepcopy

import numpy as np

from .numerical import compare_curves


def compare_data_curves(prediction, observation, **options):
    """Use ordinary alignment for continuous curves; gaps require exact samples.

    Calculation exclusions never imply interpolated measurements. Predictions
    with gap boundaries also require exact retained observation coordinates.
    The common comparator checks unit, measure, frame and axis declarations.
    """
    if observation.get('has_calculation_gaps') or prediction.get('has_calculation_gaps'):
        axes = prediction.get('axes', [])
        targets = observation.get('axes', [])
        if len(axes) != 1 or len(targets) != 1:
            raise ValueError('Gap-aware comparison requires one explicit axis')
        x = np.asarray(axes[0]['values'], dtype=float)
        target = np.asarray(targets[0]['values'], dtype=float)
        if x.ndim != 1 or target.ndim != 1 or not len(x) or not np.isfinite(x).all() or np.any(np.diff(x) <= 0):
            raise ValueError('Prediction axis must be finite and strictly increasing before gap-aware selection')
        indexes = np.searchsorted(x, target)
        if np.any(indexes >= len(x)) or not np.array_equal(x[indexes], target):
            raise ValueError('Calculation gaps require exact matching prediction samples; gap interpolation is unsupported')
        prediction = deepcopy(prediction)
        prediction['value'] = np.asarray(prediction['value'])[indexes].tolist()
        prediction['axes'][0]['values'] = target.tolist()
        prediction.pop('raw_samples', None)
        prediction.pop('segments', None)
    result = compare_curves(prediction, observation, **options)
    result['alignment_policy'] = 'exact_samples_preserving_calculation_gaps' if observation.get('has_calculation_gaps') or prediction.get('has_calculation_gaps') else result['method']
    result['observation_source_rows'] = deepcopy(observation.get('source_rows', []))
    result['observation_segments'] = deepcopy(observation.get('segments', []))
    return result
