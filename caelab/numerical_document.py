"""Independent numerical plans over frozen domain and observation inputs.

The document owner supplies editing, Undo, revision storage and run retention;
SciPy/FELUPE remain the calculation authorities. Adoption is a separate command
against the Material owner, never a side effect of running a plan.
"""
from copy import deepcopy
import math

from .material_document import MaterialDocuments, diagnostics as material_diagnostics
from .adapters.felupe_material import validate_settings, validate_parameters
from .storage import canonical_hash, check_id


def default_draft():
    return {'mode': 'fit', 'material': None, 'variables': [], 'experiments': [],
            'method': 'least_squares', 'budget': 200, 'count': 16, 'seed': 0,
            'failure_penalty': None}


def material_reference(document):
    return {'document_id': document['id'], 'generation': document['generation'],
            'input_revision': document['input_revision'], 'draft': deepcopy(document['draft'])}


def from_material_document(document):
    draft = default_draft()
    draft['material'] = material_reference(document)
    settings = document['draft'].get('settings', {})
    if not isinstance(settings, dict):
        return draft
    parameters = settings.get('parameters', {})
    if not isinstance(parameters, dict):
        return draft
    for name, value in parameters.items():
        # Bounds are user-editable suggestions, never converted material data.
        numeric = type(value) in (int, float) and math.isfinite(value)
        low, high = ((-.99, .49) if name == 'nu' else
                     (value * .1, value * 10) if numeric and value > 0 else ('', ''))
        draft['variables'].append({'id': name, 'unit': '1' if name == 'nu' else settings.get('stress_unit', ''),
                                  'value': value, 'lower': low, 'upper': high,
                                  'free': name != 'nu', 'transform': 'linear'})
    return draft


def _number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(label + ' must be a finite number')
    return value


def diagnostics(draft):
    try:
        keys = set(default_draft())
        if not isinstance(draft, dict) or set(draft) != keys:
            raise ValueError('Numerical plan requires only its visible model, variables, experiments, method and budget fields')
        if draft['mode'] not in ('fit', 'doe'):
            raise ValueError('Choose fit or doe; other numerical services remain available through the API')
        material = draft['material']
        if not isinstance(material, dict) or set(material) != {'document_id', 'generation', 'input_revision', 'draft'}:
            raise ValueError('Select a Material document and retain its exact input revision')
        check_id(material['document_id'])
        check_id(material['input_revision'])
        if not material['document_id'].startswith('M') or type(material['generation']) is not int or material['generation'] < 0:
            raise ValueError('Material reference requires a Material identity and exact generation')
        errors = material_diagnostics(material['draft'])
        if errors:
            raise ValueError('Referenced Material input is invalid: ' + errors[0]['message'])
        settings = material['draft']['settings']
        variables = draft['variables']
        if not isinstance(variables, list) or len(variables) != len(settings['parameters']):
            raise ValueError('Declare every Material coefficient once; fixed coefficients stay visible')
        names = set()
        for variable in variables:
            required = {'id', 'unit', 'value', 'lower', 'upper', 'free', 'transform'}
            if not isinstance(variable, dict) or set(variable) != required:
                raise ValueError('Each coefficient requires name, unit, current value, bounds, free and transform')
            name = variable['id']
            if name not in settings['parameters'] or name in names:
                raise ValueError('Coefficient names must match the selected Material model exactly')
            names.add(name)
            if type(variable['free']) is not bool:
                raise ValueError('Free must be a boolean')
            if variable['unit'] != ('1' if name == 'nu' else settings['stress_unit']):
                raise ValueError('Coefficient unit differs from Material settings; no conversion is inferred')
            value = _number(variable['value'], name)
            if variable['transform'] not in ('linear', 'log'):
                raise ValueError('Coefficient transform must be linear or log')
            if variable['free']:
                low, high = _number(variable['lower'], name + ' lower'), _number(variable['upper'], name + ' upper')
                if not low < high or not math.isfinite(high-low) or not low <= value <= high:
                    raise ValueError('Free coefficients require increasing finite bounds containing the current value')
                if variable['transform'] == 'log' and low <= 0:
                    raise ValueError('Log coordinates require positive bounds')
        validate_parameters(settings['model'], {v['id']: v['value'] for v in variables})
        if not any(v['free'] for v in variables):
            raise ValueError('Declare at least one free coefficient; direct evaluation belongs to Material')
        for key in ('budget', 'count'):
            if type(draft[key]) is not int or draft[key] < 1:
                raise ValueError(key + ' must be a positive integer')
        if type(draft['seed']) is not int or not 0 <= draft['seed'] <= 2**32-1:
            raise ValueError('Seed must be an unsigned 32-bit integer')
        if draft['method'] not in ('least_squares', 'differential_evolution'):
            raise ValueError('Fit method must be least_squares or differential_evolution')
        if draft['failure_penalty'] is not None and _number(draft['failure_penalty'], 'Failure penalty') <= 0:
            raise ValueError('Failure penalty must be positive or null (stop least-squares on failures)')
        if not isinstance(draft['experiments'], list):
            raise ValueError('Experiments must be a list')
        seen = set()
        for experiment in draft['experiments']:
            required = {'id', 'role', 'source', 'response', 'settings', 'weight', 'scale'}
            if not isinstance(experiment, dict) or set(experiment) != required:
                raise ValueError('Experiments require observation source, explicit model protocol, role, weight and scale')
            identifier = check_id(experiment['id'])
            if identifier in seen:
                raise ValueError('Experiment identities must be distinct')
            seen.add(identifier)
            if experiment['role'] not in ('fit', 'holdout'):
                raise ValueError('Experiment role must be fit or holdout')
            source = experiment['source']
            if not isinstance(source, dict) or set(source) != {'document_id', 'job_id', 'response', 'input_revision', 'input_sha256'}:
                raise ValueError('Observation source requires exact Data document, import job, response and submitted input identity')
            for key in ('document_id', 'job_id', 'input_revision'):
                check_id(source[key])
            if not source['document_id'].startswith('T') or not isinstance(source['response'], str) or not source['response']:
                raise ValueError('Select a retained Data response')
            if not isinstance(source['input_sha256'], str) or len(source['input_sha256']) != 64:
                raise ValueError('Observation source requires its submitted input hash')
            protocol = experiment['settings']
            if not isinstance(protocol, dict) or set(protocol) != set(settings):
                raise ValueError('Experiment protocol requires exactly the visible Material settings')
            validate_settings(protocol)
            if (protocol['model'], protocol['stress_unit'], protocol.get('time_unit', 's')) != (settings['model'], settings['stress_unit'], settings['time_unit']):
                raise ValueError('Experiment model and units must match Material; enter measured protocol explicitly')
            if experiment['response'] not in ('stress_xx', 'stress_yy', 'stress_zz', 'stress_xy', 'stress_xz', 'stress_yz'):
                raise ValueError('Select an explicit model stress component')
            for key in ('weight', 'scale'):
                if _number(experiment[key], key) <= 0:
                    raise ValueError(key + ' must be positive')
        if draft['mode'] == 'fit' and not any(e['role'] == 'fit' for e in draft['experiments']):
            raise ValueError('Add at least one fit experiment; holdout is evaluated separately')
    except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
        return [{'severity': 'error', 'path': 'plan', 'message': str(error), 'blocks_evaluation': True}]
    return []


class NumericalDocuments(MaterialDocuments):
    kind = 'numerical'
    prefix = 'N'
    update_operation = 'numerical.update'
    evaluate_operation = 'numerical.run'
    default_draft = staticmethod(default_draft)
    diagnostics = staticmethod(diagnostics)

    @staticmethod
    def evaluation_for(draft):
        return draft['mode']

    def __init__(self, root, session_id, submit, manager, *, resolve_document, resolve_result):
        super().__init__(root, session_id, submit, manager)
        self.resolve_document, self.resolve_result = resolve_document, resolve_result

    def job_arguments(self, draft):
        reference = draft['material']
        current = self.resolve_document(reference['document_id'])
        if (current.get('kind') != 'material' or current['input_revision'] != reference['input_revision']
                or canonical_hash(current['draft']) != canonical_hash(reference['draft'])):
            raise ValueError('Referenced Material input changed; reselect its explicit revision before running')
        settings = deepcopy(reference['draft']['settings'])
        settings['parameters'] = {v['id']: v['value'] for v in draft['variables']}
        variables = [{k: deepcopy(v[k]) for k in ('id', 'unit', 'value', 'lower', 'upper', 'transform')}
                     for v in draft['variables'] if v['free']]
        args = {'backend': draft['material']['draft']['backend'], 'variables': variables,
                'execution': {'mode': 'serial', 'workers': 1, 'on_failure': 'continue', 'max_evaluations': draft['budget']}}
        if draft['mode'] == 'doe':
            args.update(settings=settings, count=draft['count'], seed=draft['seed'])
        else:
            experiments = []
            for item in draft['experiments']:
                source = item['source']
                document = self.resolve_document(source['document_id'])
                run = next((run for run in document.get('runs', []) if run['job_id'] == source['job_id']), None)
                if (document.get('kind') != 'data' or run is None or run.get('input_revision') != source['input_revision']
                        or run.get('input_sha256') != source['input_sha256']):
                    raise ValueError('Observation source differs from the retained Data import')
                result = self.resolve_result(source['document_id'], source['job_id'], selection=[source['response']])
                if result.get('execution_status') != 'SUCCEEDED':
                    raise ValueError('Observation import did not succeed')
                observation = deepcopy(result['responses'][source['response']])
                self._validate_observation(observation, item, settings)
                experiment = {k: deepcopy(v) for k, v in item.items() if k != 'source'}
                experiment['observations'] = observation
                experiment['settings']['parameters'] = deepcopy(settings['parameters'])
                experiments.append(experiment)
            options = {'failure_penalty': draft['failure_penalty']} if draft['failure_penalty'] is not None else {}
            if draft['method'] == 'differential_evolution':
                options['seed'] = draft['seed']
            args.update(experiments=experiments, method=draft['method'], options=options)
        return args

    @staticmethod
    def _validate_observation(obs, experiment, settings):
        expected_measure = 'infinitesimal_Cauchy' if settings['model'] == 'linear_elastic' else 'first_Piola'
        if obs.get('kind') != 'series' or obs.get('measure') != expected_measure or obs.get('frame') != 'material_cartesian':
            raise ValueError('Observation must explicitly match the model stress measure and material_cartesian frame')
        if obs.get('coordinate_system', 'UNSPECIFIED') != 'UNSPECIFIED' or 'coordinate_frame' in obs:
            raise ValueError('This adapter exposes no coordinate-system conversion; use the declared material frame')
        if experiment['response'] != 'stress_' + str(obs.get('component')):
            raise ValueError('Observation and model stress component differ')
        if obs.get('unit') != settings['stress_unit'] or obs.get('location') != 'material_point' or obs.get('reduction') != 'none':
            raise ValueError('Observation unit, location and reduction must match the Material response')
        axes = obs.get('axes', [])
        if len(axes) != 1 or axes[0].get('name') != 'time' or axes[0].get('unit') != settings['time_unit']:
            raise ValueError('Supply an explicit time history; strain axes are not converted to time')
        from .numerical import _experiment
        _experiment({**deepcopy(experiment), 'observations': deepcopy(obs)})
        axis = axes[0]['values']
        protocol = experiment['settings']
        if axis[0] < protocol['time'][0] or axis[-1] > protocol['time'][-1]:
            raise ValueError('Observed time lies outside the explicit Material protocol')


def adopted_draft(run, result, candidate_id):
    """Return validated coefficients; the caller owns atomic target generation checks."""
    plan = run['draft']
    errors = diagnostics(plan)
    if errors:
        raise ValueError('Submitted plan is invalid: ' + errors[0]['message'])
    if result.get('kind') != plan['mode']:
        raise ValueError('Result kind differs from the submitted Numerical plan')
    candidate = next((row for row in result.get('candidates', []) if row.get('candidate_id') == candidate_id), None)
    if candidate is None or candidate.get('execution_status') != 'SUCCEEDED' or candidate.get('prediction_status'):
        raise ValueError('Only an actually evaluated successful candidate can be adopted')
    if plan['mode'] == 'fit' and (type(candidate.get('objective')) not in (int, float) or not math.isfinite(candidate['objective'])):
        raise ValueError('Fit candidate requires an actual finite objective')
    free = {v['id']: v for v in plan['variables'] if v['free']}
    if not isinstance(candidate.get('values'), dict) or set(candidate['values']) != set(free):
        raise ValueError('Candidate coefficients differ from the submitted free variables')
    material = deepcopy(plan['material']['draft'])
    material['settings']['parameters'] = {v['id']: v['value'] for v in plan['variables']}
    for name, value in candidate['values'].items():
        value = _number(value, name)
        if not free[name]['lower'] <= value <= free[name]['upper']:
            raise ValueError('Candidate value lies outside submitted bounds')
        material['settings']['parameters'][name] = value
    errors = material_diagnostics(material)
    if errors:
        raise ValueError('Candidate produces invalid Material parameters: ' + errors[0]['message'])
    return material
