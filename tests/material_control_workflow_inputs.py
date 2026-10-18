"""Declared synthetic B4.3 cases, never installed as user material defaults."""
from copy import deepcopy
from plugins.material_point import law_native as law


def cases():
    def history(model, axial, times):
        s = law.default_settings(model)
        s['time'] = times
        s['deformation_gradient'] = [[[x, 0., 0.], [0., 1., 0.], [0., 0., 1.]] for x in axial]
        s['boundary_control'] = {'stress_components': {c: [0.] * len(times) for c in ('yy', 'zz')},
                                 'solver': deepcopy(law.BOUNDARY_OPTIONS)}
        return s
    neo = history('neo_hooke', [1., 1.1, 1.2], [0., 1., 2.])
    constrained = deepcopy(neo); constrained.pop('boundary_control')
    dp = history('drucker_prager_linear', [1., 1.001, 1.006, 1.002], [0., 1., 2., 3.])
    sls = history('single_branch_maxwell', [1., 1.001, 1.003, 1.002], [0., .37, 1.11, 2.5])
    failed = law.default_settings('drucker_prager_linear')
    failed['parameters']['beta'] = 0.
    failed['time'] = [0., 1., 2.]
    identity = [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]
    failed['deformation_gradient'] = [deepcopy(identity), [[1.01, 0., 0.], [0., 1.01, 0.], [0., 0., 1.01]], deepcopy(identity)]
    retry = deepcopy(failed); retry['deformation_gradient'][1] = [[1.0001, 0., 0.], [0., 1., 0.], [0., 0., 1.]]
    return [dict(name=name, expected_status=status, settings=s) for name, status, s in (
        ('neo_free', 'SUCCEEDED', neo), ('neo_constrained', 'SUCCEEDED', constrained),
        ('dp_free', 'SUCCEEDED', dp), ('maxwell_free_physical_time', 'SUCCEEDED', sls),
        ('dp_local_failure_preserved', 'FAILED', failed), ('dp_same_initial_retry', 'SUCCEEDED', retry))]
