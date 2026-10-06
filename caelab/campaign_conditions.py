"""Frozen human conditions reused through the existing numerical campaigns.

Each candidate owns a fresh CAD revision and a fresh condition record. A
selection ID is rebound only with unchanged catalog policy, selection semantics
and coordinate systems; the Domain/adapter must then admit the complete input.
Completed campaign inspection reads frozen snapshots, not today's policy.
"""

from copy import deepcopy
import hashlib
import json

from .storage import canonical_hash, check_id, load_json


REBIND_POLICY = 'REVISION_REBIND_EXACT_SELECTIONS'


def freeze(lab, conditions_id, *, study_id, backend, model, analysis_backend):
    from .analysis_conditions import execution
    record, settings, reference, raw = execution(
        lab, lab.inspect_analysis_conditions(conditions_id)['source']['experiment_id'],
        analysis_backend, conditions_id)
    parent = lab.inspect_experiment(record['source']['experiment_id'])
    proposal = load_json(lab.store / 'experiments' / parent['experiment_id'] / 'proposal.json')
    if (record['source']['study_id'] != study_id or record['source']['backend'] != backend
            or proposal['model']['geometry'] != {'backend': backend, 'source': model}):
        raise ValueError('Campaign conditions belong to another study or registered CAD model')
    template = {'rebind_policy': REBIND_POLICY, 'reference': reference,
                'record': record, 'record_canonical_sha256': canonical_hash(record)}
    return template, settings, raw


def verify(plan, folder):
    analysis = plan.get('analysis')
    template = analysis.get('conditions_template') if analysis else None
    if template is None:
        return
    from .analysis_conditions import _request, _revision
    path = folder / 'analysis_conditions_template.json'
    if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
        raise ValueError('Campaign condition snapshot must remain in its own folder')
    raw = path.read_bytes()
    record, reference = template['record'], template['reference']
    _request(record['request'])
    binding = record['adapter_binding']
    if (set(template) != {'rebind_policy', 'reference', 'record', 'record_canonical_sha256'}
            or template['rebind_policy'] != REBIND_POLICY
            or hashlib.sha256(raw).hexdigest() != reference['record_sha256']
            or json.loads(raw) != record or canonical_hash(record) != template['record_canonical_sha256']
            or record['id'] != reference['id'] or record['request']['conditions_id'] != record['id']
            or record['conditions_revision'] != reference['revision']
            or record['catalog_revision'] != reference['catalog_revision']
            or record['request']['catalog_revision'] != record['catalog_revision']
            or canonical_hash(record['catalog']) != record['catalog_revision']
            or _revision(record['source'], record['request'], record['catalog_revision']) != reference['revision']
            or record['source']['study_id'] != plan['study_id']
            or record['source']['backend'] != plan['backend']
            or record['source']['experiment_id'] != record['request']['experiment_id']
            or record['source']['cad_revision'] != record['request']['cad_revision']
            or record['request']['backend'] != analysis['backend']
            or record['support']['status'] != 'SUPPORTED_DECLARED_INPUTS'
            or record['engineering'] != 'UNKNOWN' or record['decision'] != 'NOT_RELEASED'
            or reference['scope'] != 'USER_DECLARED_UNVERIFIED' or binding is None
            or binding['backend'] != analysis['backend']
            or binding['version'] != plan['analysis_adapter_version']
            or binding['policy_sha256'] != canonical_hash(binding['policy'])
            or binding['settings_sha256'] != canonical_hash(binding['settings'])
            or binding['settings'] != analysis['settings']):
        raise ValueError('Campaign frozen conditions differ from the original declaration or settings')


def current(lab, plan):
    analysis = plan.get('analysis')
    template = analysis.get('conditions_template') if analysis else None
    if template is None:
        return
    actual, settings, _raw = freeze(lab, template['reference']['id'], study_id=plan['study_id'],
                                   backend=plan['backend'], model=plan['model'],
                                   analysis_backend=analysis['backend'])
    if actual != template or settings != analysis['settings']:
        raise ValueError('Saved campaign conditions or admission policy changed before execution')


def _selection_semantics(catalog, declaration):
    selected = {item['selection_id'] for group in ('materials', 'boundary_conditions', 'loads')
                for item in declaration[group]}
    for pair in declaration['contact'].get('pairs', []):
        selected.update((pair['selection_a'], pair['selection_b']))
    entries = {item['id']: item for item in catalog['selections']}
    if not selected <= entries.keys():
        raise ValueError('Candidate CAD lacks an explicitly selected condition region')
    # Whole-solid volume changes with numerical CAD variables. Every other
    # declared selection property must remain identical, including native IDs,
    # derivation definitions, roles, owners and any future geometry predicates.
    return {key: {name: value for name, value in entries[key].items()
                  if name not in ('volume_mm3', 'label')} for key in sorted(selected)}


def _candidate_catalog(lab, plan, parent_id):
    template = plan['analysis']['conditions_template']['record']
    described = lab.describe_analysis_conditions(parent_id)
    original, catalog = template['catalog'], described['catalog']
    declaration = template['request']['declaration']
    if (described['source']['study_id'] != plan['study_id']
            or catalog['cad_backend'] != plan['backend'] or catalog['model'] != plan['model']
            or catalog['coordinate_systems'] != original['coordinate_systems']
            or catalog['catalog_policy_sha256'] != original['catalog_policy_sha256']
            or catalog['input_semantics_sha256'] != original['input_semantics_sha256']
            or catalog.get('region_source_sha256') != original.get('region_source_sha256')
            or _selection_semantics(catalog, declaration) != _selection_semantics(original, declaration)):
        raise ValueError('Candidate selection semantics or coordinate/catalog policy changed; no automatic rebind')
    return described


def condition_id(plan, item):
    return check_id(f"C-{plan['campaign_id']}-{item['index']:04d}")


def bind(lab, plan, item):
    parent_id = item['cad_experiment_id']
    described = _candidate_catalog(lab, plan, parent_id)
    original = plan['analysis']['conditions_template']['record']
    request = {'conditions_id': condition_id(plan, item), 'experiment_id': parent_id,
               'cad_revision': described['source']['cad_revision'],
               'catalog_revision': described['catalog_revision'], 'backend': plan['analysis']['backend'],
               'declaration': deepcopy(original['request']['declaration'])}
    namespace = lab.store / 'analysis_conditions' / request['conditions_id']
    record = (lab.inspect_analysis_conditions(request['conditions_id']) if namespace.exists()
              else lab.save_analysis_conditions(**request))
    if (record['request'] != request or record['adapter_binding'] != original['adapter_binding']
            or record['support']['status'] != 'SUPPORTED_DECLARED_INPUTS'):
        raise ValueError('Candidate conditions projection does not match the frozen campaign declaration')
    return request['conditions_id']


def verify_child(plan, item, folder, result):
    template = plan['analysis'].get('conditions_template')
    if template is None:
        return
    # Core inspection has already verified the manifested child snapshot. This
    # extra check binds its unchanged declaration/projection to this campaign.
    record = load_json(folder / 'analysis_conditions.json')
    original = template['record']
    if (record['id'] != condition_id(plan, item)
            or result['provenance']['analysis_conditions']['id'] != record['id']
            or record['source']['experiment_id'] != item['cad_experiment_id']
            or record['source']['study_id'] != plan['study_id']
            or record['request']['declaration'] != original['request']['declaration']
            or record['adapter_binding'] != original['adapter_binding']
            or record['catalog']['coordinate_systems'] != original['catalog']['coordinate_systems']
            or _selection_semantics(record['catalog'], record['request']['declaration']) !=
                _selection_semantics(original['catalog'], original['request']['declaration'])):
        raise ValueError('Existing child conditions do not belong to this frozen campaign')
