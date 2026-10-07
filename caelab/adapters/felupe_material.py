"""Material-point histories evaluated by optional FELUPE, not a new material solver."""
from copy import deepcopy
import numpy as np
from ..evaluation import PreparedEvaluation


class FelupeMaterialAdapter:
    backend = 'material.felupe'
    version = '1'

    def prepare(self, settings, *, runtime=None):
        import felupe
        if runtime and set(runtime)-{'threads','memory_mb'}:
            raise ValueError('Unsupported FELUPE runtime options')
        model = settings.get('model', 'linear_elastic')
        if model not in {'linear_elastic', 'neo_hooke'}:
            raise ValueError('Choose FELUPE linear_elastic or neo_hooke; other laws require a registered adapter')
        time = np.asarray(settings['time'], dtype=float)
        gradients = np.asarray(settings['deformation_gradient'], dtype=float)
        if time.ndim != 1 or not len(time) or not np.isfinite(time).all() or np.any(np.diff(time) <= 0):
            raise ValueError('History time must be finite and strictly increasing')
        if gradients.shape != (len(time), 3, 3) or not np.isfinite(gradients).all() or np.any(np.linalg.det(gradients) <= 0):
            raise ValueError('A positive-determinant 3x3 deformation gradient is required at each time')
        unit = settings.get('stress_unit')
        if not isinstance(unit, str) or not unit:
            raise ValueError('An explicit stress_unit is required; all moduli use that unit')
        parameters = deepcopy(settings.get('parameters', {}))
        names = {'E', 'nu'} if model == 'linear_elastic' else {'mu', 'lmbda'}
        if set(parameters) != names:
            raise ValueError(f'{model} requires parameters {sorted(names)}')
        fixed_gradients = gradients.copy()
        fixed_time = time.copy()

        def calculate(values):
            if not set(values) <= names:
                raise ValueError('Unknown material parameter')
            p = {**parameters, **values}
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(v) for v in p.values()):
                raise ValueError('Material parameters must be finite numbers')
            if model == 'linear_elastic':
                if p['E'] <= 0 or not -1 < p['nu'] < .5:
                    raise ValueError('Linear elasticity requires E > 0 and -1 < nu < 0.5')
                material = felupe.LinearElastic(**p)
            else:
                if p['mu'] <= 0 or p['lmbda'] + 2 * p['mu'] / 3 <= 0:
                    raise ValueError('Neo-Hooke shear and bulk moduli must be positive')
                material = felupe.NeoHookeCompressible(**p)
            # Every candidate starts from its own zero state. Elastic laws have no
            # internal history; the library remains the stress/tangent authority.
            F = np.moveaxis(fixed_gradients.copy(), 0, -1)[:, :, None, :]
            state = np.zeros((0, 1, len(time)))
            stress = material.gradient([F, state])[0][:, :, 0, :]
            tangent = material.hessian([F, state])[0][..., 0, :]
            tangent = np.broadcast_to(tangent, (*tangent.shape[:-1], len(time))).copy()
            axes = [{'name': 'time', 'unit': settings.get('time_unit', 's'), 'values': fixed_time.copy()}]
            responses = {}
            for component, i, j in [('xx', 0, 0), ('yy', 1, 1), ('zz', 2, 2),
                                    ('xy', 0, 1), ('xz', 0, 2), ('yz', 1, 2)]:
                responses['stress_' + component] = {
                    'kind': 'series', 'value': stress[i, j].copy(), 'unit': unit,
                    'component': component, 'location': 'material_point', 'reduction': 'none',
                    'axes': deepcopy(axes), 'frame': 'material_cartesian',
                    'measure': 'infinitesimal_Cauchy' if model == 'linear_elastic' else 'first_Piola'}
            responses['tangent'] = {'kind': 'field', 'value': np.moveaxis(tangent, -1, 0), 'unit': unit,
                                    'component': 'ijkl', 'location': 'material_point', 'reduction': 'none', 'axes': deepcopy(axes)}
            if model == 'neo_hooke':
                responses['energy'] = {'kind': 'series', 'value': np.asarray(material.function([F, state])[0]).reshape(-1),
                                       'unit': unit, 'component': 'energy_per_reference_volume',
                                       'location': 'material_point', 'reduction': 'none', 'axes': deepcopy(axes)}
            return {'execution_status': 'SUCCEEDED', 'responses': responses,
                    'checks': [{'name': 'physical_calibration', 'status': 'NOT_ASSESSED'}],
                    'diagnostics': {'library': 'felupe', 'version': felupe.__version__, 'model': model,
                                    'parameters': p, 'initial_state': 'ZERO_ELASTIC_STATE',
                                    'limitations': ['Prescribed material-point kinematics, no FE boundary solve',
                                                   'Fitted synthetic data is not physical validation']}}
        return PreparedEvaluation(calculate, settings)
