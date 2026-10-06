"""One immutable CAD parent, explicit scalar condition candidates and native children.

The existing optimization journal and SciPy engine own ordering/replay. CAD
parameters retain their original meaning; scenario variables live in the
campaign candidate and its copied typed conditions, never in CAD dimensions.
"""
from copy import deepcopy

from .condition_parameters import bind, verify_bound, ConditionInputRejected
from .storage import canonical_hash, load_json


ITEM_FIELDS = ('cad_experiment_id', 'analysis_experiment_id', 'conditions_id',
               'condition_declaration', 'condition_input_rejection', 'condition_binding_sha256')


def assignments(plan, values):
    return {item['native']['path']: values[item['parameter_id']] for item in plan['variables']}


def binding_hash(plan, item):
    return canonical_hash({'source': plan['fixed_cad']['source'],
        'template_revision': plan['fixed_cad']['template_revision'], 'values': item['values'],
        'declaration': item['condition_declaration'], 'rejection': item['condition_input_rejection']})


def candidate(lab, plan, index, values):
    identifier = f"E-{plan['campaign_id']}-{index:04d}"
    declaration, rejection = None, None
    try:
        declaration = bind(lab, plan['fixed_cad'], assignments(plan, values))
    except ConditionInputRejected as error:
        rejection = f'{type(error).__name__}: {error}'
    item = {'cad_experiment_id': plan['fixed_cad']['source']['experiment_id'],
            'analysis_experiment_id': identifier if declaration is not None else None,
            'conditions_id': f"C-{plan['campaign_id']}-{index:04d}" if declaration is not None else None,
            'condition_declaration': declaration, 'condition_input_rejection': rejection,
            'values': deepcopy(values)}
    item['condition_binding_sha256'] = binding_hash(plan, item)
    return item


def validate_candidate(plan, item):
    accepted = item['condition_declaration'] is not None
    identifier = f"E-{plan['campaign_id']}-{item['index']:04d}"
    if (item['cad_experiment_id'] != plan['fixed_cad']['source']['experiment_id']
            or item['analysis_experiment_id'] != (identifier if accepted else None)
            or item['conditions_id'] != (f"C-{plan['campaign_id']}-{item['index']:04d}" if accepted else None)
            or item['condition_binding_sha256'] != binding_hash(plan, item)
            or (accepted and item['condition_input_rejection'] is not None)
            or (not accepted and (not isinstance(item['condition_input_rejection'], str)
                                  or not item['condition_input_rejection'].startswith('ConditionInputRejected: ')))):
        raise ValueError('Fixed CAD candidate identity/binding mismatch')
    if accepted:
        verify_bound(plan['fixed_cad'], assignments(plan, item['values']), item['condition_declaration'])


def experiments(lab, plan, item, allow_run, verified):
    validate_candidate(plan, item)
    template = plan['fixed_cad']; source = template['source']
    parent_id = source['experiment_id']
    parent = verified.get(parent_id)
    if parent is None:
        parent = lab.inspect_experiment(parent_id)
        verified[parent_id] = parent
    from .analysis_conditions import _sha, _revision
    parent_root = lab.store / 'experiments' / parent_id
    proposal = load_json(parent_root / 'proposal.json')
    thread = load_json(parent_root / 'thread.json')
    if (parent['study']['id'] != plan['study_id'] or parent['cad_revision'] != source['cad_revision']
            or _sha(parent_root/'result.json') != source['result_sha256']
            or _sha(parent_root/'proposal.json') != source['proposal_sha256']
            or _sha(parent_root/'thread.json') != source['thread_sha256']
            or proposal['physics']['analysis_type'] != 'cad_preflight'
            or parent['provenance']['adapter'] != source['backend']):
        raise ValueError('Fixed CAD campaign parent source changed')
    if item['condition_declaration'] is None:
        # No model or solver is created for an inadmissible Domain candidate.
        if (lab.store/'experiments'/f"E-{plan['campaign_id']}-{item['index']:04d}").exists():
            raise ValueError('Rejected fixed CAD candidate invented a native child')
        return parent, None
    child_id, conditions_id = item['analysis_experiment_id'], item['conditions_id']
    folder = lab.store/'experiments'/child_id
    condition_path = lab.store/'analysis_conditions'/conditions_id/'record.json'
    request = {**deepcopy(template['record']['request']), 'conditions_id': conditions_id,
               'declaration': deepcopy(item['condition_declaration'])}
    if not folder.exists():
        if not allow_run:
            raise ValueError('Fixed CAD journal references a missing native child')
        if not condition_path.exists():
            lab.save_analysis_conditions(**request)
        record = lab.inspect_analysis_conditions(conditions_id)
        if (record['request'] != request or record['source'] != source
                or record['catalog'] != template['record']['catalog']):
            raise ValueError('Pending fixed CAD conditions differ from the frozen candidate')
        lab.run_analysis(parent_experiment_id=parent_id, experiment_id=child_id,
                         backend=template['backend'], conditions_id=conditions_id)
    child = verified.get(child_id)
    if child is None:
        child = lab.inspect_experiment(child_id)
        verified[child_id] = child
    child_proposal = load_json(folder/'proposal.json')
    record = load_json(folder/'analysis_conditions.json')
    reference = child['provenance'].get('analysis_conditions', {})
    if (record['request'] != request or record['source'] != source
            or record['catalog'] != template['record']['catalog']
            or record['catalog_revision'] != template['catalog_revision']
            or record['conditions_revision'] != _revision(source, request, template['catalog_revision'])
            or record['adapter_binding']['policy'] != template['record']['adapter_binding']['policy']
            or child.get('parent_experiment_id') != parent_id or child['cad_revision'] != source['cad_revision']
            or child['provenance'].get('adapter') != template['backend']
            or child['provenance'].get('adapter_version') != plan['analysis_adapter_version']
            or child['provenance'].get('core_source_sha256') != plan['core_source_sha256']
            or child_proposal['study_id'] != plan['study_id']
            or child['input_parameters'] != parent['input_parameters']
            or child_proposal['parameters'] != parent['input_parameters']
            or child['registry_revision'] != parent['registry_revision']
            or child['provenance']['registry_sha256'] != parent['provenance']['registry_sha256']
            or reference.get('id') != conditions_id):
        raise ValueError('Fixed CAD native child differs from its retained candidate/context')
    return parent, child
