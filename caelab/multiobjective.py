"""Append-only coordination of native epsilon-constraint campaigns.

Existing frozen Core plans, DE execution, native ownership and numerical verdicts
remain authoritative. The numerical helper only coordinates bounded child plans
and compares original eligible responses; it never supplies a new solver path.
"""
from copy import deepcopy
from filelock import FileLock

from . import optimization as opt
from .execution_control import check_cancelled
from .optimizers import epsilon_campaign as numerical
from .response_comparison import _guard_source_paths, _path, _sha
from .storage import check_id, load_json, save_json


def _folder(lab, parent_id):
    return _path(lab, f'multiobjective/{check_id(parent_id)}')


def _plan(lab, identifier):
    check_id(identifier)
    for name in ('plan.json', 'registry_snapshot.json', 'analysis_conditions_template.json'):
        _path(lab, f'optimizations/{identifier}/{name}')
    _path(lab, f'ledger/optimization-{identifier}.json')
    return opt._plan(lab, identifier)


def create(lab, *, parent_id, template_campaign_id, objectives, primary_index,
           threshold_grid, child_budget, seed, total_evaluation_budget):
    folder = _folder(lab, parent_id)
    if any(_path(lab, f'{namespace}/{parent_id}').exists()
           for namespace in ('campaigns', 'optimizations', 'multiobjective')):
        raise FileExistsError('This campaign ID is already retained')
    template, template_folder, _, _, snapshot = _plan(lab, template_campaign_id)
    opt._verify_sources(lab, template, snapshot)
    template_sha = _sha(template_folder/'plan.json')
    parent = numerical.build_parent(parent_id=parent_id, template_plan=template,
             template_plan_sha256=template_sha,
             source_pins=numerical.source_pins_for(template, template_sha),
             objectives=objectives, primary_index=primary_index,
             threshold_grid=threshold_grid, child_budget=child_budget,
             seed=seed, total_evaluation_budget=total_evaluation_budget)
    # Check every request through the existing scalar response selector before
    # creating the parent. Real plans still pass the full Core planner below.
    backend = (template['backend'] if template['route'] == 'model_analysis'
               else template['analysis']['backend'])
    adapter = (lab.model_analysis_adapters if template['route'] == 'model_analysis'
               else lab.analysis_adapters).get(backend)
    if adapter is None or any(item['metric'] not in adapter.default_metrics for item in objectives):
        raise ValueError('Every objective must be advertised by the frozen native backend')
    for child in parent['children']:
        if any(_path(lab, f'{namespace}/{child["campaign_id"]}').exists()
               for namespace in ('campaigns', 'optimizations')):
            raise FileExistsError('A child campaign ID is already retained')
    opt._verify_sources(lab, template, snapshot)
    folder.mkdir(parents=True, exist_ok=False)
    save_json(folder/'plan.json', parent)
    save_json(folder/'receipt.json', {'parent_id': parent_id, 'plan_sha256': _sha(folder/'plan.json'),
                                    'parent_digest': parent['digest']})
    return deepcopy(parent)


def _load(lab, parent_id, *, live=False):
    folder = _folder(lab, parent_id)
    for name in ('plan.json', 'receipt.json'):
        _path(lab, f'multiobjective/{parent_id}/{name}')
    parent, receipt = load_json(folder/'plan.json'), load_json(folder/'receipt.json')
    if (receipt != {'parent_id': parent_id, 'plan_sha256': _sha(folder/'plan.json'),
                    'parent_digest': parent.get('digest')} or parent.get('parent_id') != parent_id):
        raise ValueError('Multiobjective parent identity or original receipt differs')
    identifier = parent['template_plan']['campaign_id']
    template, template_folder, _, _, snapshot = _plan(lab, identifier)
    if live:
        opt._verify_sources(lab, template, snapshot)
    bindings, plans = [], {}
    binding_folder = _path(lab, f'multiobjective/{parent_id}/bindings')
    if binding_folder.exists():
        paths = sorted(binding_folder.iterdir())
        for index, path in enumerate(paths, 1):
            if path.name != f'{index:04d}.json':
                raise ValueError('Multiobjective child binding sequence differs')
            binding = load_json(_path(lab, f'multiobjective/{parent_id}/bindings/{path.name}'))
            child_plan, child_folder, _, _, _ = _plan(lab, binding['campaign_id'])
            intent = load_json(_path(lab, f'multiobjective/{parent_id}/intents/{index:04d}.json'))
            spec = parent['children'][index - 1]
            if intent != {'parent_digest': parent['digest'], 'child_digest': spec['digest'],
                          'campaign_id': spec['campaign_id'], 'index': index}:
                raise ValueError('Child binding lost its original owned submission intent')
            bindings.append(binding)
            plans[binding['campaign_id']] = (child_plan, _sha(child_folder/'plan.json'))
    numerical.verify_resume(parent, parent_digest=receipt['parent_digest'], template_plan=template,
             template_plan_sha256=_sha(template_folder/'plan.json'),
             source_pins=numerical.source_pins_for(template, _sha(template_folder/'plan.json')),
             child_receipts=bindings, child_plans=plans)
    return folder, parent, bindings, plans


def _collect(lab, parent, bindings, plans):
    child_records, native = [], {}
    for binding in bindings:
        identifier = binding['campaign_id']
        plan = plans[identifier][0]
        folder = _path(lab, f'optimizations/{identifier}')
        record = lab.inspect_optimization(identifier)
        for row in record['evaluations']:
            keys = ('model_experiment_id',) if plan['route'] == 'model_analysis' else ('cad_experiment_id', 'analysis_experiment_id')
            for key in keys:
                experiment_id = row.get(key)
                if experiment_id and experiment_id not in native:
                    _guard_source_paths(lab, experiment_id)
                    native[experiment_id] = (lab.inspect_experiment(experiment_id),
                        _sha(_path(lab, f'experiments/{experiment_id}/result.json')))
        child_records.append({'receipt': binding, 'plan': plan, 'record': record,
                             'result_sha256': _sha(folder/'result.json') if (folder/'result.json').exists() else None})
        if record['status'] not in ('COMPLETED_REVIEW_REQUIRED', 'NO_FEASIBLE_DESIGN'):
            break
    return numerical.collect(parent, parent_digest=parent['digest'],
                             child_records=child_records, experiment_results=native)


def inspect(lab, parent_id):
    folder, parent, bindings, plans = _load(lab, parent_id)
    calculated = _collect(lab, parent, bindings, plans)
    result_path = _path(lab, f'multiobjective/{parent_id}/result.json')
    if result_path.exists():
        seal = load_json(_path(lab, f'multiobjective/{parent_id}/result-receipt.json'))
        if (seal != {'parent_id': parent_id, 'result_sha256': _sha(result_path)}
                or load_json(result_path) != calculated):
            raise ValueError('Multiobjective result differs from the original child records')
    return {'integrity': 'VERIFIED', 'plan': parent, 'record': calculated,
            'plan_sha256': _sha(folder/'plan.json'),
            'result_sha256': _sha(result_path) if result_path.exists() else None}


def run(lab, parent_id):
    lock = _path(lab, f'ledger/multiobjective-{check_id(parent_id)}.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(lock), timeout=0):
        return _run(lab, parent_id)


def _run(lab, parent_id):
    folder, parent, bindings, plans = _load(lab, parent_id, live=True)
    if (folder/'result.json').exists():
        return inspect(lab, parent_id)
    for child in parent['children']:
        check_cancelled()
        index, identifier = child['index'], child['campaign_id']
        if index > len(bindings):
            # A published intent is ownership evidence. A child lacking its
            # final binding is ambiguous; never adopt or overwrite it on retry.
            intent = _path(lab, f'multiobjective/{parent_id}/intents/{index:04d}.json')
            if intent.exists() or _path(lab, f'optimizations/{identifier}').exists():
                raise ValueError('UNKNOWN child binding: retained intent/child needs recovery')
            save_json(intent, {'parent_digest': parent['digest'], 'child_digest': child['digest'],
                               'campaign_id': identifier, 'index': index})
            method = (lab.plan_model_optimization if parent['template_plan']['route'] == 'model_analysis'
                      else lab.plan_condition_optimization)
            plan = method(**deepcopy(child['request']))
            child_folder = _path(lab, f'optimizations/{identifier}')
            binding = numerical.bind_child_plan(parent, parent_digest=parent['digest'], index=index,
                                child_plan=plan, plan_sha256=_sha(child_folder/'plan.json'))
            save_json(folder/'bindings'/f'{index:04d}.json', binding)
            bindings.append(binding); plans[identifier] = (plan, binding['plan_sha256'])
        lab.run_optimization(identifier)
        current = _collect(lab, parent, bindings, plans)
        if current['children'][index - 1]['status'] not in ('COMPLETED_REVIEW_REQUIRED', 'NO_FEASIBLE_DESIGN'):
            return inspect(lab, parent_id)
    check_cancelled()
    result = _collect(lab, parent, bindings, plans)
    if result['status'] != 'COMPLETED_REVIEW_REQUIRED':
        raise ValueError('Multiobjective children did not close their frozen budgets')
    save_json(folder/'result.json', result)
    save_json(folder/'result-receipt.json', {'parent_id': parent_id, 'result_sha256': _sha(folder/'result.json')})
    return inspect(lab, parent_id)
