"""Seeded DOE on declared models or one immutable CAD/condition revision.

The sampler owns points; existing model/condition bindings own engineering
admission and native syntax. This module retains observations, not optimization
feedback, probability distributions, engineering approval or a best design.
"""

from copy import deepcopy
from pathlib import Path

from filelock import FileLock

from . import optimization as opt
from .contracts import CapabilityUnavailable
from .execution_control import check_cancelled
from .schema import validate as validate_schema
from .storage import canonical_hash, check_id, load_json, save_json, source_identity, utc_now


ENGINE = 'scipy.latin_hypercube'
ROOT = Path(__file__).resolve().parents[1]


def _paths(lab, identifier):
    if len(check_id(identifier)) > 58:
        raise ValueError('DOE campaign ID exceeds 58 characters')
    return lab.store / 'campaigns' / identifier, lab.store / 'ledger' / f'campaign-{identifier}.json'


def _requirements(value, route):
    expected = {'model'} if route == 'model_analysis' else {'cad', 'analysis'}
    requirements = deepcopy(value if value is not None else {key: [] for key in expected})
    if (type(requirements) is not dict or set(requirements) != expected or any(
            type(names) is not list or len(names) > 32 or
            any(type(name) is not str or not name.strip() for name in names) or
            len(set(names)) != len(names) for names in requirements.values())):
        raise ValueError('DOE required validations must name distinct route-specific checks')
    return requirements


def _request(lab, campaign_id, parameter_ids, sample_count, seed, engine):
    folder, ledger = _paths(lab, campaign_id)
    if (folder.exists() or ledger.exists() or (lab.store / 'optimizations' / campaign_id).exists()
            or (lab.store / 'ledger' / f'optimization-{campaign_id}.json').exists()):
        raise ValueError('Campaign ID is already used; preserve the existing records')
    if (type(parameter_ids) is not list or not parameter_ids or len(parameter_ids) > 32
            or any(type(name) is not str or not name for name in parameter_ids)
            or len(set(parameter_ids)) != len(parameter_ids)):
        raise ValueError('Select distinct registered research parameter IDs')
    if type(sample_count) is not int or not 2 <= sample_count <= 32:
        raise ValueError('DOE requires 2..32 samples')
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError('DOE seed must be an unsigned 32-bit integer')
    if engine != ENGINE or engine not in lab.doe_adapters:
        raise CapabilityUnavailable('Declared-model DOE requires the available seeded uniform LHS sampler')


def _variables(parameter_ids, available, advertised):
    if any(name not in available for name in parameter_ids):
        raise ValueError('DOE variable does not map to this registered model/condition template')
    variables = [deepcopy(available[name]) for name in parameter_ids]
    for item in variables:
        candidate = advertised.get(item['native']['path'])
        if (candidate is None or item['native'] != candidate['native']
                or item['unit'] != candidate['unit'] or item['source_sha256'] != candidate['source_sha256']
                or not all(opt._number(item[key]) for key in ('lower_bound', 'upper_bound'))
                or not candidate['lower'] <= item['lower_bound'] < item['upper_bound'] <= candidate['upper']):
            raise ValueError('DOE registry unit/bounds/binding differs from its advertised scalar input')
    return variables


def _sample(lab, plan):
    engine = plan['algorithm']['engine'] if 'algorithm' in plan else plan['engine']
    if engine != ENGINE or engine not in lab.doe_adapters:
        raise CapabilityUnavailable('DOE sampler is unavailable')
    sampler = lab.doe_adapters[engine]
    points, algorithm = sampler.sample(plan['variables'], count=plan['sample_count'], seed=plan['seed'])
    if (type(points) is not list or len(points) != plan['sample_count'] or type(algorithm) is not dict
            or algorithm.get('engine') != engine or algorithm.get('version') != sampler.version
            or algorithm.get('seed') != plan['seed']):
        raise ValueError('DOE sampler returned inconsistent points/provenance')
    for values in points:
        opt._key(plan, values)  # Exact names, bounds and finite nonboolean values.
    canonical_hash(algorithm)
    return points, algorithm


def _persist(lab, plan, registry):
    points, algorithm = _sample(lab, plan)
    plan['algorithm'] = algorithm
    plan.pop('engine')
    plan['samples'] = []
    for index, values in enumerate(points, 1):
        opt._verify_sources(lab, plan, registry)
        plan['samples'].append(opt._new_item(lab, plan, index, values))
        opt._verify_sources(lab, plan, registry)
    validate_schema('model-doe-plan', plan)
    canonical_hash(plan)
    folder, ledger_path = _paths(lab, plan['campaign_id'])
    # Recheck immediately before the first write; a concurrent plan cannot be
    # used as an overwrite destination after an earlier request check.
    _request(lab, plan['campaign_id'], [v['parameter_id'] for v in plan['variables']],
             plan['sample_count'], plan['seed'], algorithm['engine'])
    folder.mkdir(parents=True, exist_ok=False)
    save_json(folder / 'plan.json', plan)
    save_json(folder / 'registry_snapshot.json', registry)
    save_json(ledger_path, {'campaign_id': plan['campaign_id'], 'plan_sha256': opt._sha(folder / 'plan.json'),
                           'registry_sha256': opt._sha(folder / 'registry_snapshot.json'), 'created_utc': utc_now()})
    return deepcopy(plan)


def _base(lab, study_id, campaign_id, route, variables, registry, requirements, sample_count, seed, engine):
    return {'schema_version': '1.0', 'type': 'doe', 'route': route, 'campaign_id': campaign_id,
            'study_id': study_id, 'status': 'PLANNED', 'variables': variables,
            'registry_revision': registry['revision'], 'registry_sha256': canonical_hash(registry),
            'core_source_sha256': source_identity(ROOT)['core_source_sha256'],
            'objective': None, 'constraints': [], 'required_validations': requirements,
            'sample_count': sample_count, 'seed': seed, 'engine': engine,
            'failure_policy': {'domain_rejected': 'UNUSABLE_NO_NATIVE_EXECUTION', 'numerical_rejected': 'UNUSABLE',
                               'failed_execution': 'STOP', 'restart': 'EXACT_PLANNED_SAMPLE_REUSE'},
            'created_utc': utc_now()}


def plan_model_doe(lab, *, study_id, campaign_id, backend, settings, parameter_ids, sample_count, seed,
                   required_validations=None, engine=ENGINE):
    from .model_parameters import describe
    _request(lab, campaign_id, parameter_ids, sample_count, seed, engine)
    lab.inspect_study(study_id)
    requirements = _requirements(required_validations, 'model_analysis')
    description = describe(lab, backend, settings)
    registry = lab.registry(study_id)
    available = {item['parameter_id']: item for item in registry['entries'] if
                 item.get('target') == 'model_analysis' and item['native']['backend'] == backend
                 and item['native']['document'] == description['revision']}
    advertised = {item.native['path']: item.__dict__ for item in description['candidates']}
    variables = _variables(parameter_ids, available, advertised)
    plan = _base(lab, study_id, campaign_id, 'model_analysis', variables, registry, requirements,
                 sample_count, seed, engine)
    plan.update(backend=backend, model_template=deepcopy(settings), model_template_revision=description['revision'],
                model_input_descriptors=description['descriptors'], model_declaration=description['declaration'],
                model_source_fingerprint=description['fingerprint'], model_adapter_version=description['adapter'].version)
    return _persist(lab, plan, registry)


def plan_condition_doe(lab, *, study_id, campaign_id, conditions_id, parameter_ids, sample_count, seed,
                       required_validations=None, engine=ENGINE):
    from .condition_parameters import describe
    _request(lab, campaign_id, parameter_ids, sample_count, seed, engine)
    lab.inspect_study(study_id)
    requirements = _requirements(required_validations, 'fixed_cad_analysis')
    template = describe(lab, conditions_id)
    if template['source']['study_id'] != study_id:
        raise ValueError('Fixed CAD conditions belong to a different study')
    backend, analysis_backend = template['source']['backend'], template['backend']
    registry = lab.registry(study_id)
    available = {item['parameter_id']: item for item in registry['entries'] if
                 item.get('target') == 'analysis_conditions' and item.get('conditions_id') == conditions_id
                 and item.get('conditions_template_revision') == template['template_revision']
                 and item.get('condition_input_descriptors_sha256') == template['condition_input_descriptors_sha256']
                 and item['native']['backend'] == analysis_backend
                 and item['native']['document'] == template['template_revision']}
    advertised = {item['native']['path']: item for item in template['candidates']}
    variables = _variables(parameter_ids, available, advertised)
    proposal = load_json(lab.store / 'experiments' / template['source']['experiment_id'] / 'proposal.json')
    plan = _base(lab, study_id, campaign_id, 'fixed_cad_analysis', variables, registry, requirements,
                 sample_count, seed, engine)
    plan.update(backend=backend, model=proposal['model']['geometry']['source'], fixed_cad=template,
                cad_adapter_version=lab._adapter(backend).version, cad_source_fingerprint=opt._fingerprint(lab._adapter(backend)),
                analysis_adapter_version=lab.analysis_adapters[analysis_backend].version,
                analysis={'backend': analysis_backend,
                          'settings': deepcopy(template['record']['adapter_binding']['settings'])})
    return _persist(lab, plan, registry)


def _candidate(plan, item, index):
    if (type(item) is not dict or set(item) != set(opt._item_fields(plan)) or type(item['index']) is not int
            or item['index'] != index or item['key'] != opt._key(plan, item['values'])):
        raise ValueError('DOE frozen candidate index/values/key differs')
    if plan['route'] == 'fixed_cad_analysis':
        from .fixed_cad_optimization import validate_candidate
        validate_candidate(plan, item)
    else:
        from .model_parameters import expected_settings, expected_declaration
        assignments = {v['native']['path']: item['values'][v['parameter_id']] for v in plan['variables']}
        expected = expected_settings(plan['model_template'], plan['model_input_descriptors'], assignments)
        if (item['model_experiment_id'] != f"E-{plan['campaign_id']}-{index:04d}"
                or canonical_hash(expected) != canonical_hash(item['model_settings'])
                or item['model_revision'] != canonical_hash({'settings': item['model_settings'],
                                                            'declaration': item['model_declaration']})
                or (item['model_declaration'] and canonical_hash(item['model_declaration']) != canonical_hash(
                    expected_declaration(plan['model_declaration'], plan['model_input_descriptors'], assignments)))):
            raise ValueError('DOE candidate changed frozen model context/identity')


def _plan(lab, identifier):
    folder, ledger_path = _paths(lab, identifier)
    ledger = load_json(ledger_path)
    if (ledger.get('campaign_id') != identifier or opt._sha(folder / 'plan.json') != ledger.get('plan_sha256')
            or opt._sha(folder / 'registry_snapshot.json') != ledger.get('registry_sha256')):
        raise ValueError('DOE plan or registry snapshot hash mismatch')
    plan, snapshot = load_json(folder / 'plan.json'), load_json(folder / 'registry_snapshot.json')
    validate_schema('model-doe-plan', plan)
    canonical_hash(plan)
    if (plan['campaign_id'] != identifier or canonical_hash(snapshot) != plan['registry_sha256']
            or snapshot['revision'] != plan['registry_revision'] or len(plan['samples']) != plan['sample_count']
            or plan['algorithm']['seed'] != plan['seed']
            or len({v['parameter_id'] for v in plan['variables']}) != len(plan['variables'])
            or any(item not in snapshot['entries'] for item in plan['variables'])):
        raise ValueError('DOE plan differs from its frozen registry/sample count')
    if plan['route'] == 'model_analysis':
        from .model_parameters import _validated_inputs
        descriptors = _validated_inputs(plan['model_input_descriptors'])
        revision = canonical_hash({'settings': plan['model_template'], 'declaration': plan['model_declaration']})
        if (revision != plan['model_template_revision']
                or plan['model_source_fingerprint']['adapter'] != plan['backend']
                or plan['model_source_fingerprint']['version'] != plan['model_adapter_version']):
            raise ValueError('DOE model template revision/source differs from its frozen context')
        source_sha = canonical_hash({'fingerprint': plan['model_source_fingerprint'], 'inputs': descriptors,
                                     'model_revision': revision})
        advertised = {d['id']: {'native': {'backend': plan['backend'], 'document': revision,
                         'object': 'declared_inputs', 'path': d['id'], 'alias': ''},
                         'unit': d['unit'], 'source_sha256': source_sha, 'lower': d['lower'], 'upper': d['upper']}
                      for d in descriptors}
        if any(v.get('target') != 'model_analysis' or v.get('model_template_revision') != revision
               or v.get('input_descriptor_sha256') != canonical_hash(descriptors) for v in plan['variables']):
            raise ValueError('DOE model registry differs from its frozen descriptors')
    else:
        template = plan['fixed_cad']
        revision = canonical_hash({'record_sha256': template['reference']['record_sha256'],
                                   'descriptors': template['descriptors'], 'fingerprint': template['fingerprint']})
        if (revision != template['template_revision'] or template['source']['study_id'] != plan['study_id']
                or template['source']['backend'] != plan['backend'] or template['backend'] != plan['analysis']['backend']
                or template['record']['adapter_binding']['version'] != plan['analysis_adapter_version']
                or canonical_hash(template['record']['adapter_binding']['settings']) != canonical_hash(plan['analysis']['settings'])
                or canonical_hash(template['descriptors']) != template['condition_input_descriptors_sha256']):
            raise ValueError('DOE fixed-CAD template differs from its frozen context')
        advertised = {item['native']['path']: item for item in template['candidates']}
        if any(v.get('target') != 'analysis_conditions' or v.get('conditions_id') != template['conditions_id']
               or v.get('conditions_template_revision') != revision
               or v.get('condition_input_descriptors_sha256') != template['condition_input_descriptors_sha256']
               for v in plan['variables']):
            raise ValueError('DOE condition registry differs from its frozen descriptors')
    _variables([v['parameter_id'] for v in plan['variables']],
               {v['parameter_id']: v for v in plan['variables']}, advertised)
    for index, item in enumerate(plan['samples'], 1):
        _candidate(plan, item, index)
    return plan, folder, ledger_path, ledger, snapshot


def _experiments(lab, plan, item, allow_run, verified):
    if plan['route'] == 'fixed_cad_analysis':
        from .fixed_cad_optimization import experiments
        return experiments(lab, plan, item, allow_run, verified)
    return None, opt._model_experiment(lab, plan, item, allow_run, verified)


def _record(lab, plan, item, cad, analysis):
    model = plan['route'] == 'model_analysis'
    results = [analysis] if model else [cad, analysis]
    usable = (opt._usable(analysis, plan['required_validations']['model'], analysis=True) if model else
              opt._usable(cad, plan['required_validations']['cad']) and
              opt._usable(analysis, plan['required_validations']['analysis'], analysis=True))
    status = analysis['status'] if analysis is not None else 'SKIPPED_DOMAIN_CONDITION_REJECTED'
    identity = ({'model_status': status,
                 'model_result_sha256': opt._sha(lab.store / 'experiments' / analysis['experiment_id'] / 'result.json')}
                if model else {'cad_status': cad['status'],
                               'cad_result_sha256': opt._sha(lab.store / 'experiments' / cad['experiment_id'] / 'result.json'),
                               'analysis_status': status,
                               'analysis_result_sha256': opt._sha(lab.store / 'experiments' / analysis['experiment_id'] / 'result.json')
                               if analysis is not None else None})
    if model and not item['model_declaration'] and (status != 'REJECTED' or analysis['solver_status'] != 'NOT_RUN'):
        raise ValueError('Only recorded model declaration rejection may omit metadata')
    return {**deepcopy(item), **identity, 'status': status,
            'metrics': {'model': deepcopy(analysis['metrics'])} if model else
                       {'cad': deepcopy(cad['metrics']), 'analysis': deepcopy(analysis['metrics']) if analysis is not None else None},
            'usable': bool(usable), 'failed_execution': any(r is not None and r['status'] == 'FAILED_EXECUTION' for r in results),
            'unknown': sorted({v['type'] for r in results if r is not None for v in r['validations'] if v['status'] == 'UNKNOWN'}),
            'failures': [{'experiment_id': r['experiment_id'], 'type': v['type'], 'evidence_ids': v['evidence_ids']}
                         for r in results if r is not None for v in r['validations'] if v['status'] == 'FAIL'],
            'decision': 'NOT_RELEASED'}


def _rows(lab, plan, folder, verified):
    for path in sorted((folder / 'candidates').glob('*.json')):
        if path.name not in {f'{i:04d}.json' for i in range(1, plan['sample_count'] + 1)}:
            raise ValueError('DOE candidate file is outside its frozen sample sequence')
        index = int(path.stem)
        if canonical_hash(load_json(path)) != canonical_hash(plan['samples'][index - 1]):
            raise ValueError('DOE candidate file differs from its frozen sample')
    rows = []
    for index, path in enumerate(sorted((folder / 'journal').glob('*.json')), 1):
        if path.name != f'{index:04d}.json' or index > plan['sample_count']:
            raise ValueError('DOE journal sequence has a gap/extra sample')
        row, item = load_json(path), plan['samples'][index - 1]
        if canonical_hash(load_json(folder / 'candidates' / path.name)) != canonical_hash(item):
            raise ValueError('DOE journal candidate differs from its frozen sample')
        cad, analysis = _experiments(lab, plan, item, False, verified)
        if canonical_hash(row) != canonical_hash(_record(lab, plan, item, cad, analysis)):
            raise ValueError('DOE journal differs from its verified experiment')
        rows.append(row)
    return rows


def _checkpoint_state(folder, plan_sha, rows):
    return {'plan_sha256': plan_sha, 'completed_samples': len(rows), 'sample_order': [r['key'] for r in rows],
            'failed_execution': any(r['failed_execution'] for r in rows),
            'journal_sha256': {f"{r['index']:04d}.json": opt._sha(folder / 'journal' / f"{r['index']:04d}.json") for r in rows}}


def _checkpoint(folder, plan_sha, rows):
    state = _checkpoint_state(folder, plan_sha, rows)
    path = folder / 'checkpoints' / f'{len(rows):04d}.json'
    if path.exists():
        if canonical_hash(load_json(path)) != canonical_hash(state):
            raise ValueError('DOE checkpoint differs from its verified journal')
    else:
        save_json(path, state)
    save_json(folder / 'state.json', state)


def _checkpoints(folder, plan_sha, rows, completed):
    pending = []
    names = {f'{i:04d}.json' for i in range(1, len(rows) + 1)}
    if any(path.name not in names for path in (folder / 'checkpoints').glob('*.json')):
        raise ValueError('DOE checkpoint is outside its journal sequence')
    for row in rows:
        path = folder / 'checkpoints' / f"{row['index']:04d}.json"
        if not path.exists():
            if completed or row['index'] != len(rows):
                raise ValueError('DOE checkpoint is missing')
            pending.append(row['index'])
        elif canonical_hash(load_json(path)) != canonical_hash(_checkpoint_state(folder, plan_sha, rows[:row['index']])):
            raise ValueError('DOE checkpoint hash/state mismatch')
    state_path = folder / 'state.json'
    if state_path.exists():
        # An atomic state write can be interrupted after a newer immutable
        # journal/checkpoint. A verified older prefix can be completed on resume.
        count = load_json(state_path).get('completed_samples')
        if (type(count) is not int or not 1 <= count <= len(rows)
                or completed and count != len(rows)
                or canonical_hash(load_json(state_path)) != canonical_hash(_checkpoint_state(folder, plan_sha, rows[:count]))):
            raise ValueError('DOE state differs from its verified journal prefix')
    elif completed:
        raise ValueError('Completed DOE state is missing')
    return pending


def _versions(lab, rows, verified):
    versions = None
    for row in rows:
        versions = opt._versions(lab, row, versions, verified=verified)
    return versions


def run_doe(lab, campaign_id):
    folder, _ = _paths(lab, campaign_id)
    if not folder.is_dir():
        raise ValueError('DOE plan is missing')
    with FileLock(str(folder / 'execution.lock'), timeout=30):
        plan, folder, ledger_path, ledger, snapshot = _plan(lab, campaign_id)
        if (folder / 'result.json').exists():
            return inspect_doe(lab, campaign_id)
        with FileLock(str(lab.store / 'studies' / plan['study_id'] / 'parameters.json') + '.lock', timeout=30):
            opt._verify_sources(lab, plan, snapshot)
            points, algorithm = _sample(lab, plan)
            if (canonical_hash(algorithm) != canonical_hash(plan['algorithm']) or
                    canonical_hash(points) != canonical_hash([item['values'] for item in plan['samples']])):
                raise ValueError('DOE sampler/runtime or exact seeded points changed since planning')
            verified = {}
            rows = _rows(lab, plan, folder, verified)
            _checkpoints(folder, ledger['plan_sha256'], rows, False)
            versions = _versions(lab, rows, verified)
            if any(row['failed_execution'] for row in rows):
                raise RuntimeError('DOE retains a failed execution; preserve it and plan a new campaign after repair')
            for row in rows:
                _checkpoint(folder, ledger['plan_sha256'], rows[:row['index']])
            for index, item in enumerate(plan['samples'], 1):
                if index <= len(rows):
                    continue
                check_cancelled()
                opt._verify_sources(lab, plan, snapshot)
                actual = opt._new_item(lab, plan, index, item['values'])
                if canonical_hash(actual) != canonical_hash(item):
                    raise ValueError('DOE candidate binding changed since planning')
                candidate = folder / 'candidates' / f'{index:04d}.json'
                if candidate.exists():
                    if canonical_hash(load_json(candidate)) != canonical_hash(item):
                        raise ValueError('Pending DOE candidate differs from the frozen sample')
                else:
                    save_json(candidate, item)
                cad, analysis = _experiments(lab, plan, item, True, verified)
                opt._verify_sources(lab, plan, snapshot)
                row = _record(lab, plan, item, cad, analysis)
                save_json(folder / 'journal' / f'{index:04d}.json', row)
                rows.append(row)
                _checkpoint(folder, ledger['plan_sha256'], rows)
                versions = opt._versions(lab, row, versions, verified=verified)
                if row['failed_execution']:
                    raise RuntimeError(f'DOE backend execution failed at sample {index}; evidence retained')
            check_cancelled()
            opt._verify_sources(lab, plan, snapshot)
            result = {'schema_version': '1.0', 'type': 'doe', 'route': plan['route'], 'campaign_id': campaign_id,
                      'study_id': plan['study_id'], 'status': 'COMPLETED_REVIEW_REQUIRED', 'decision': 'NOT_RELEASED',
                      'plan_sha256': ledger['plan_sha256'], 'registry_sha256': plan['registry_sha256'],
                      'algorithm': deepcopy(plan['algorithm']), 'samples': rows,
                      'provenance': {**source_identity(ROOT), 'solver_versions': versions,
                                     'journal_sha256': _checkpoint_state(folder, ledger['plan_sha256'], rows)['journal_sha256'],
                                     'checkpoint_sha256': {p.name: opt._sha(p) for p in sorted((folder / 'checkpoints').glob('*.json'))}},
                      'completed_utc': utc_now()}
            validate_schema('model-doe-result', result)
            save_json(folder / 'result.json', result)
            save_json(ledger_path, {**ledger, 'result_sha256': opt._sha(folder / 'result.json')})
            return deepcopy(result)


def inspect_doe(lab, campaign_id):
    plan, folder, _, ledger, _ = _plan(lab, campaign_id)
    verified = {}
    rows = _rows(lab, plan, folder, verified)
    versions = _versions(lab, rows, verified)
    completed = (folder / 'result.json').exists()
    pending = _checkpoints(folder, ledger['plan_sha256'], rows, completed)
    if not completed:
        return {'type': 'doe', 'route': plan['route'], 'status': 'FAILED_EXECUTION' if any(r['failed_execution'] for r in rows)
                else 'RUNNING' if rows else 'PLANNED', 'decision': 'NOT_RELEASED', 'plan': plan,
                'completed_samples': len(rows), 'samples': rows, 'checkpoint_pending': pending}
    if opt._sha(folder / 'result.json') != ledger.get('result_sha256'):
        raise ValueError('DOE result hash mismatch')
    result = load_json(folder / 'result.json')
    validate_schema('model-doe-result', result)
    expected = {'campaign_id': campaign_id, 'study_id': plan['study_id'], 'route': plan['route'],
                'plan_sha256': ledger['plan_sha256'], 'registry_sha256': plan['registry_sha256'],
                'algorithm': plan['algorithm'], 'samples': rows}
    if (len(rows) != plan['sample_count'] or any(r['failed_execution'] for r in rows)
            or any(canonical_hash(result[key]) != canonical_hash(value) for key, value in expected.items())
            or result['provenance']['solver_versions'] != versions
            or result['provenance']['journal_sha256'] != _checkpoint_state(folder, ledger['plan_sha256'], rows)['journal_sha256']
            or result['provenance']['checkpoint_sha256'] != {p.name: opt._sha(p) for p in sorted((folder / 'checkpoints').glob('*.json'))}):
        raise ValueError('DOE result differs from its verified plan/journal/checkpoints')
    return result
