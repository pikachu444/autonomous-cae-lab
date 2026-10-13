"""Material-point histories evaluated by optional FELUPE, not a new material solver."""
from copy import deepcopy
from numbers import Real
import numpy as np
from ..evaluation import PreparedEvaluation


def validate_parameters(model, parameters):
    names = {'E', 'nu'} if model == 'linear_elastic' else {'mu', 'lmbda'}
    if not isinstance(parameters, dict) or set(parameters) != names:
        raise ValueError(f'{model} requires parameters {sorted(names)}')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(v) for v in parameters.values()):
        raise ValueError('Material parameters must be finite numbers')
    if model == 'linear_elastic':
        if parameters['E'] <= 0 or not -1 < parameters['nu'] < .5:
            raise ValueError('Linear elasticity requires E > 0 and -1 < nu < 0.5')
    elif parameters['mu'] <= 0 or parameters['lmbda'] + 2 * parameters['mu'] / 3 <= 0:
        raise ValueError('Neo-Hooke shear and bulk moduli must be positive')


def validate_settings(settings, *, parameters=True):
    """Validate editable inputs without importing or executing the optional solver."""
    model = settings.get('model', 'linear_elastic')
    if model not in {'linear_elastic', 'neo_hooke'}:
        raise ValueError('Choose FELUPE linear_elastic or neo_hooke; other laws require a registered adapter')
    for key in ('time', 'deformation_gradient'):
        raw = np.asarray(settings[key], dtype=object)
        if any(isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) for value in raw.flat):
            raise ValueError('History values must be finite numbers, not booleans or text')
    time = np.asarray(settings['time'], dtype=float)
    gradients = np.asarray(settings['deformation_gradient'], dtype=float)
    if time.ndim != 1 or not len(time) or not np.isfinite(time).all() or np.any(np.diff(time) <= 0):
        raise ValueError('History time must be finite and strictly increasing')
    if gradients.shape != (len(time), 3, 3) or not np.isfinite(gradients).all() or np.any(np.linalg.det(gradients) <= 0):
        raise ValueError('A positive-determinant 3x3 deformation gradient is required at each time')
    if not isinstance(settings.get('stress_unit'), str) or not settings['stress_unit'].strip():
        raise ValueError('An explicit stress_unit is required; all moduli use that unit')
    if not isinstance(settings.get('time_unit', 's'), str) or not settings.get('time_unit', 's').strip():
        raise ValueError('An explicit time_unit is required')
    names = {'E', 'nu'} if model == 'linear_elastic' else {'mu', 'lmbda'}
    if not isinstance(settings.get('parameters'), dict) or set(settings['parameters']) != names:
        raise ValueError(f'{model} requires parameters {sorted(names)}')
    if parameters:
        validate_parameters(model, settings['parameters'])
    return model, time, gradients


class FelupeMaterialAdapter:
    backend = 'material.felupe'
    version = '1'

    def describe_inputs(self, settings):
        """Declare current coefficients without importing/running FELUPE.

        Bounds are editable search suggestions, not proof that every combined
        coefficient set satisfies the material law.
        """
        validate_settings(settings)
        labels={'E':'탄성계수','nu':'푸아송비','mu':'전단계수','lmbda':'Lamé 계수'}
        rows=[]
        for name,value in settings['parameters'].items():
            low,high=((-0.99,0.49) if name=='nu' else
                      (value*.1,value*10.) if value>0 else (value-abs(value or 1.),value+abs(value or 1.)))
            rows.append({'id':name,'label':labels[name],'unit':'1' if name=='nu' else settings['stress_unit'],
                         'value':value,'lower':low,'upper':high,'path':['parameters',name]})
        return rows

    def bind_inputs(self, settings, values):
        """Pure coefficient binding through the existing Material domain contract.

        Units, deformation/time histories and unselected coefficients are copied
        unchanged. No FELUPE calculation, document edit or adoption occurs here.
        """
        if not isinstance(values,dict):
            raise ValueError('Material assignments require named coefficients')
        validate_settings(settings)
        from ..evaluation_definition import bind_values
        return bind_values({'backend':self.backend,'settings':deepcopy(settings)},
                           deepcopy(values))['settings']

    def prepare(self, settings, *, runtime=None):
        import felupe
        if runtime and set(runtime)-{'threads','memory_mb'}:
            raise ValueError('Unsupported FELUPE runtime options')
        model, time, gradients = validate_settings(settings, parameters=False)
        unit = settings['stress_unit']
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
            validate_parameters(model, p)
            if model == 'linear_elastic':
                material = felupe.LinearElastic(**p)
            else:
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
