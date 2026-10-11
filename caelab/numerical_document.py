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


def request_draft(request=None, *, source=None):
    """An actual existing-engine request; opening it never submits a job."""
    return {'mode': 'request', 'request': deepcopy(request if request is not None else {
        'purpose': '', 'operation': 'evaluate', 'inputs': {'backend': '', 'settings': {}},
        'budget': {'evaluations': 1}}), 'source': deepcopy(source)}


def request_diagnostics(draft):
    try:
        if set(draft) != {'mode', 'request', 'source'}:
            raise ValueError('Request Plan requires mode, editable request and source reference')
        from .assist.experts import validate_plan_request
        request = draft['request']
        if not isinstance(request, dict) or set(request) != {'purpose', 'operation', 'inputs', 'budget'}:
            raise ValueError('Request requires purpose, operation, inputs and evaluation budget')
        if not isinstance(request['purpose'], str) or not request['purpose'].strip():
            raise ValueError('Enter the research purpose before running')
        if set(request.get('budget', {})) != {'evaluations'}:
            raise ValueError('Use the existing evaluation budget; provider permissions are separate')
        validate_plan_request(request)
        from .research_operations import validate_result_refs
        validate_result_refs(request['operation'], request['inputs'])
        source = draft['source']
        if source is not None:
            if isinstance(source, dict) and 'document_id' in source:
                if set(source) != {'document_id', 'kind', 'saved_revision', 'input_revision', 'input_sha256'}:
                    raise ValueError('Frozen Plan source requires exact document kind, saved/input revisions and input hash')
                for key in ('document_id', 'saved_revision', 'input_revision'):
                    check_id(source[key])
                kinds = {'data':'T', 'material':'M', 'pde':'Q', 'simulation':'V', 'evaluation':'E', 'study':'S'}
                if source['kind'] not in kinds or not source['document_id'].startswith(kinds[source['kind']]):
                    raise ValueError('Select an exact saved research source')
                from .research_operations import _hash
                _hash(source['input_sha256'], 'source input')
                return []
            if isinstance(source,dict) and 'pde_document_id' in source:
                if set(source) != {'pde_document_id','saved_revision','input_revision','input_sha256'}:
                    raise ValueError('PDE Plan source requires its exact saved revision and input hash')
                for key in ('pde_document_id','saved_revision','input_revision'):
                    check_id(source[key])
                digest = source['input_sha256']
                if (not source['pde_document_id'].startswith('Q') or not isinstance(digest,str)
                        or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest)):
                    raise ValueError('Select an exact saved PDE input')
                return []
            required = {'discussion_id', 'turn_id', 'proposal_index', 'job_id',
                        'input_revision', 'input_sha256', 'proposal_sha256'}
            if not isinstance(source, dict) or set(source) != required:
                raise ValueError('A proposed Plan retains its exact discussion, turn, job and proposal hash')
            for key in ('discussion_id', 'turn_id', 'job_id', 'input_revision'):
                check_id(source[key])
            if not source['discussion_id'].startswith('X') or type(source['proposal_index']) is not int or source['proposal_index'] < 0:
                raise ValueError('Select an actual discussion proposal')
            for key in ('input_sha256', 'proposal_sha256'):
                if not isinstance(source[key], str) or len(source[key]) != 64 or any(c not in '0123456789abcdef' for c in source[key]):
                    raise ValueError('Source requires exact retained hashes')
    except (ValueError, TypeError, KeyError) as error:
        return [{'severity': 'error', 'path': 'request', 'message': str(error), 'blocks_evaluation': True}]
    return []


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
    if isinstance(draft, dict) and draft.get('mode') == 'request':
        return request_diagnostics(draft)
    try:
        keys = set(default_draft())
        extra = {'operation_options'} if isinstance(draft, dict) and draft.get('mode') in ('optimize', 'uq', 'epsilon') else set()
        if not isinstance(draft, dict) or not keys <= set(draft) or set(draft) - keys - extra:
            raise ValueError('Numerical plan requires only its visible model, variables, experiments, method and budget fields')
        if draft['mode'] not in ('fit', 'doe', 'optimize', 'uq', 'epsilon'):
            raise ValueError('Choose fit, doe, optimize, uq or epsilon; retained-result operations use Request Plans')
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
        if draft['mode'] == 'fit' and draft['method'] not in ('least_squares', 'differential_evolution'):
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
        if draft['mode'] in ('doe', 'uq') and draft['count'] > draft['budget']:
            raise ValueError('Sample count exceeds the Plan evaluation budget')
        if draft['mode'] in ('optimize', 'uq', 'epsilon'):
            from .assist.experts import validate_plan_request
            validate_plan_request(material_request(draft))
            _material_operation_diagnostics(draft)
    except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
        return [{'severity': 'error', 'path': 'plan', 'message': str(error), 'blocks_evaluation': True}]
    return []


def material_request(draft):
    """Compile bound Material search/UQ inputs using only visible coefficients."""
    mode = draft['mode']
    options = deepcopy(draft.get('operation_options'))
    if not isinstance(options, dict):
        raise ValueError(mode + ' requires visible operation_options')
    accepted = {'optimize': {'objective', 'constraints', 'options'},
                'uq': {'distributions', 'source', 'independence', 'thresholds'},
                'epsilon': {'objectives', 'constraints', 'options', 'threshold_grid', 'primary_index'}}
    if mode not in accepted or set(options) - accepted[mode]:
        raise ValueError('Unknown visible ' + str(mode) + ' operation option')
    settings = deepcopy(draft['material']['draft']['settings'])
    settings['parameters'] = {v['id']: v['value'] for v in draft['variables']}
    variables = [{key: deepcopy(v[key]) for key in ('id', 'unit', 'value', 'lower', 'upper', 'transform')}
                 for v in draft['variables'] if v['free']]
    inputs = {'backend': draft['material']['draft']['backend'], 'settings': settings,
              'variables': variables, 'seed': draft['seed'], **options,
              'execution': {'mode': 'serial', 'workers': 1, 'on_failure': 'continue', 'max_evaluations': draft['budget']}}
    if mode == 'uq':
        inputs['count'] = draft['count']
    elif mode == 'epsilon':
        inputs['total_evaluation_budget'] = draft['budget']
    return {'purpose': 'Material ' + mode + ' over the explicitly bound coefficient revision',
            'operation': mode, 'inputs': inputs, 'budget': {'evaluations': draft['budget']}}


def _material_operation_diagnostics(draft):
    """Validate semantics and hard budgets without running a Material model."""
    mode, options = draft['mode'], draft['operation_options']
    settings = draft['material']['draft']['settings']
    if mode == 'uq':
        if draft['count'] < 2:
            raise ValueError('UQ requires at least two declared samples')
        names = {v['id'] for v in draft['variables'] if v['free']}
        if set(options.get('distributions', {})) != names:
            raise ValueError('Declare one distribution for every free Material coefficient')
        if options.get('independence') != 'INDEPENDENT_USER_DECLARED':
            raise ValueError('Declare independent input marginals explicitly')
        source = options.get('source', {})
        if (not isinstance(source, dict) or source.get('origin') not in ('ASSUMED', 'MEASURED_REPORTED', 'PUBLISHED_REFERENCE', 'SYNTHETIC')
                or not isinstance(source.get('reference'), str) or not source['reference'].strip()):
            raise ValueError('Declare the input distribution source and reference')
        for variable in draft['variables']:
            if not variable['free']:
                continue
            law = options['distributions'][variable['id']]
            if not isinstance(law, dict) or law.get('unit', variable['unit']) != variable['unit']:
                raise ValueError('Distribution units must match the Material coefficient')
            distribution = law.get('distribution')
            if distribution == 'uniform':
                low, high = _number(law.get('lower', variable['lower']), 'uniform lower'), _number(law.get('upper', variable['upper']), 'uniform upper')
                if not variable['lower'] <= low < high <= variable['upper']:
                    raise ValueError('Uniform support must lie within declared coefficient bounds')
            elif distribution in ('normal', 'truncnorm', 'lognormal'):
                mean, std = _number(law.get('mean'), 'distribution mean'), _number(law.get('std'), 'distribution std')
                if std <= 0 or (distribution == 'lognormal' and mean <= 0):
                    raise ValueError('Distribution requires positive deviation and a valid mean')
            else:
                raise ValueError('Choose uniform, normal, truncnorm or lognormal')
        definitions = options.get('thresholds', [])
    else:
        de = options.get('options', {})
        if not isinstance(de, dict) or set(de) - {'max_generations', 'population_size', 'initial_values', 'retain_responses'}:
            raise ValueError('Use the existing differential evolution options')
        population, generations = de.get('population_size', 12), de.get('max_generations', 40)
        if type(population) is not int or population < 5 or type(generations) is not int or generations < 1:
            raise ValueError('Differential evolution requires population >=5 and generations >=1')
        initial = de.get('initial_values')
        if initial is not None:
            free = {v['id']: v for v in draft['variables'] if v['free']}
            if not isinstance(initial, dict) or set(initial) != set(free):
                raise ValueError('Initial search values require every free Material coefficient exactly once')
            for name, value in initial.items():
                value = _number(value, 'initial ' + name)
                if not free[name]['lower'] <= value <= free[name]['upper']:
                    raise ValueError('Initial search value lies outside declared coefficient bounds')
        if de.get('retain_responses', 'summary') not in ('summary', 'all'):
            raise ValueError('Response retention must be summary or all')
        required = population * (generations + 1)
        if mode == 'epsilon':
            objectives = options.get('objectives', [])
            primary = options.get('primary_index', 0)
            grid = options.get('threshold_grid')
            if (not isinstance(objectives, list) or len(objectives) < 2 or type(primary) is not int
                    or not 0 <= primary < len(objectives) or not isinstance(grid, list)
                    or len(grid) != len(objectives)-1):
                raise ValueError('Epsilon requires a primary objective and explicit thresholds for every secondary objective')
            combinations = 1
            for points in grid:
                if not isinstance(points, list) or not points:
                    raise ValueError('Each epsilon threshold dimension needs finite values')
                for value in points:
                    _number(value, 'epsilon threshold')
                combinations *= len(points)
            required *= combinations
            if draft['seed'] + combinations - 1 > 2**32-1:
                raise ValueError('Epsilon child seeds must stay within the unsigned 32-bit seed range')
            definitions = objectives + options.get('constraints', [])
        else:
            definitions = [options.get('objective')] + options.get('constraints', [])
        if required > draft['budget']:
            raise ValueError('Search population/generations exceed the declared total evaluation budget')
    for definition in definitions:
        if not isinstance(definition, dict):
            raise ValueError('Declare each physical response objective or threshold')
        response = definition.get('response')
        if response not in {'stress_xx', 'stress_yy', 'stress_zz', 'stress_xy', 'stress_xz', 'stress_yz', 'energy'}:
            raise ValueError('Select an existing Material stress or energy history')
        if response == 'energy' and settings['model'] == 'linear_elastic':
            raise ValueError('The selected linear Material model does not expose energy')
        if definition.get('unit') != settings['stress_unit']:
            raise ValueError('Material response unit must match the bound Material settings')
        if definition.get('reduction') not in ('max', 'min', 'final', 'mean', 'abs_max'):
            raise ValueError('Material history objectives require an explicit scalar reduction')
        if 'component' in definition and definition['component'] != (response[7:] if response.startswith('stress_') else 'energy_per_reference_volume'):
            raise ValueError('Material response component differs from the declared channel')
        if 'location' in definition and definition['location'] != 'material_point':
            raise ValueError('Material response location must be material_point')
        if 'scale' in definition and _number(definition['scale'], 'response scale') <= 0:
            raise ValueError('Response scale must be positive')
        if 'limit' in definition:
            _number(definition['limit'], 'response limit')
        if 'direction' in definition and definition['direction'] not in ('minimize', 'maximize'):
            raise ValueError('Objective direction must be minimize or maximize')
        permitted = ('<', '<=', '>', '>=') if mode == 'uq' else ('<=', '>=')
        if 'operator' in definition and definition['operator'] not in permitted:
            raise ValueError('Declare a supported physical response threshold operator')


class NumericalDocuments(MaterialDocuments):
    kind = 'numerical'
    prefix = 'N'
    update_operation = 'numerical.update'
    evaluate_operation = 'numerical.run'
    default_draft = staticmethod(default_draft)
    diagnostics = staticmethod(diagnostics)

    @staticmethod
    def evaluation_for(draft):
        if draft['mode'] == 'request':
            operation, inputs = draft['request']['operation'], draft['request']['inputs']
            # PDE declarations use their existing native adapter and retained field delivery.
            if operation == 'evaluate' and str(inputs.get('backend', '')).startswith('pde.'):
                return 'pde.evaluate'
            if operation == 'evaluate':
                from .simulation_document import CATALOG
                if inputs.get('backend') in CATALOG:
                    return 'simulation.run'
            return operation
        return draft['mode']

    def __init__(self, root, session_id, submit, manager, *, resolve_document, resolve_result,
                 prepare_request=None, resolve_pde_revision=None, resolve_source_revision=None):
        super().__init__(root, session_id, submit, manager)
        self.resolve_document, self.resolve_result = resolve_document, resolve_result
        self.prepare_request = prepare_request
        self.resolve_pde_revision = resolve_pde_revision
        self.resolve_source_revision = resolve_source_revision

    @staticmethod
    def _draft(value):
        if isinstance(value,dict) and value.get('mode') == 'request':
            # Imported PDE mesh declarations are already bounded to 8 MiB.
            from .pde_document import PDEDocuments
            return PDEDocuments._draft(value)
        return MaterialDocuments._draft(value)

    def job_arguments(self, draft):
        if draft.get('mode') == 'request':
            if self.prepare_request is None:
                raise ValueError('The shared numerical request service is unavailable; the Plan remains editable')
            source = draft.get('source')
            if source is not None and 'document_id' in source:
                if self.resolve_source_revision is None:
                    raise ValueError('The saved research source resolver is unavailable')
                original = self.resolve_source_revision(source['document_id'], source['saved_revision'])
                if (original.get('kind') != source['kind'] or original['input_revision'] != source['input_revision']
                        or canonical_hash(original['draft']) != source['input_sha256']):
                    raise ValueError('The saved source research input changed')
            elif source is not None and 'pde_document_id' in source:
                if self.resolve_pde_revision is None:
                    raise ValueError('The saved PDE source resolver is unavailable')
                original = self.resolve_pde_revision(source['pde_document_id'],source['saved_revision'])
                if original['input_revision'] != source['input_revision'] or canonical_hash(original['draft']) != source['input_sha256']:
                    raise ValueError('The saved source PDE input changed')
            elif source is not None:
                discussion = self.resolve_document(source['discussion_id'])
                turn = next((row for row in discussion.get('turns', []) if row['id'] == source['turn_id']), None)
                if turn is None or any(turn.get(key) != source[key] for key in ('job_id','input_revision','input_sha256')):
                    raise ValueError('The selected source turn or its submitted input changed')
                original = self.resolve_result(source['discussion_id'],source['job_id'])
                actions = original.get('proposed_actions', [])
                index = source['proposal_index']
                if index >= len(actions) or canonical_hash(actions[index].get('plan')) != source['proposal_sha256']:
                    raise ValueError('The retained source proposal changed or is missing')
            from .research_operations import validate_result_refs
            validate_result_refs(draft['request']['operation'], draft['request']['inputs'])
            return self.prepare_request(deepcopy(draft['request']))
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
        elif draft['mode'] in ('optimize', 'uq', 'epsilon'):
            _material_operation_diagnostics(draft)
            request = material_request(draft)
            if self.prepare_request is not None:
                return self.prepare_request(request)
            # Direct owner tests/callers retain the same explicit hard evaluation limit.
            args = request['inputs']
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
    if plan.get('mode') == 'request':
        raise ValueError('A general request has no implied Material target; use an explicitly bound Material Plan for adoption')
    errors = diagnostics(plan)
    if errors:
        raise ValueError('Submitted plan is invalid: ' + errors[0]['message'])
    expected_kind = {'optimize': 'optimization', 'epsilon': 'epsilon_optimization'}.get(plan['mode'], plan['mode'])
    if result.get('kind') != expected_kind:
        raise ValueError('Result kind differs from the submitted Numerical plan')
    candidate = next((row for row in result.get('candidates', []) if row.get('candidate_id') == candidate_id), None)
    if candidate is None or candidate.get('execution_status') != 'SUCCEEDED' or candidate.get('prediction_status'):
        raise ValueError('Only an actually evaluated successful candidate can be adopted')
    if plan['mode'] in ('fit', 'optimize', 'epsilon') and (type(candidate.get('objective')) not in (int, float) or not math.isfinite(candidate['objective'])):
        raise ValueError('Search candidate requires an actual finite objective')
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
