"""Retained Data comparison through the established numerical residual contract."""
from copy import deepcopy

from .numerical import compare_curves


def compare_data_curves(prediction, observation, **options):
    """Use ordinary alignment for continuous curves; gaps require exact samples.

    Calculation exclusions never imply interpolated measurements. Predictions
    with gap boundaries also require exact retained observation coordinates.
    The common comparator checks unit, measure, frame and axis declarations.
    """
    result = compare_curves(prediction, observation, **options)
    result['alignment_policy'] = 'exact_samples_preserving_calculation_gaps' if observation.get('has_calculation_gaps') or prediction.get('has_calculation_gaps') else result['method']
    result['observation_source_rows'] = deepcopy(observation.get('source_rows', []))
    result['observation_segments'] = deepcopy(observation.get('segments', []))
    return result
