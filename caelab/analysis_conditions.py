"""Append-only mechanical declarations bound to a verified CAD experiment.

Core owns identity, integrity and persistence. Catalogs/projected settings are
adapter-owned; engineering input semantics and support are Domain-owned. A
supported declaration is not native execution, material qualification or release.
"""

from copy import deepcopy
from pathlib import Path
import re

from jsonschema.exceptions import ValidationError

from .contracts import CapabilityUnavailable
from .response_comparison import _source, _path, _sha, _finite_json
from .schema import validate
from .storage import canonical_hash, check_id, load_json, save_json, source_identity, utc_now


def _parent(lab, experiment_id):
    parent, proposal, hashes = _source(lab, check_id(experiment_id))
    if (proposal['physics']['analysis_type'] != 'cad_preflight' or not parent['cad_revision']
            or not re.fullmatch(r'[0-9a-f]{64}', parent['cad_revision']) or parent['solver_status'] != 'NOT_RUN'):
        raise ValueError('Conditions require a completed, verified CAD preflight experiment')
    source = {'experiment_id': experiment_id, 'study_id': parent['study']['id'],
              'cad_revision': parent['cad_revision'], 'backend': parent['provenance']['adapter'], **hashes}
    adapter = lab.adapters.get(source['backend'])
    hook = getattr(adapter, 'conditions_catalog', None)
    if not callable(hook):
        raise CapabilityUnavailable('This CAD adapter does not yet supply a revision-bound condition catalog')
    catalog = hook(_path(lab, f'experiments/{experiment_id}'), deepcopy(parent), deepcopy(proposal))
    _finite_json(catalog)
    if (catalog.get('schema_version') != '1.0' or not isinstance(catalog.get('selections'), list)
            or not catalog['selections'] or not isinstance(catalog.get('coordinate_systems'), list)):
        raise ValueError('Adapter returned an incomplete condition catalog')
    return source, catalog


def describe(lab, experiment_id):
    source, catalog = _parent(lab, experiment_id)
    return {'source': source, 'catalog': catalog, 'catalog_revision': canonical_hash(catalog),
            'backends': [{'backend': key, 'label': key,
                          'scope': 'Declared-input admission only; native runtime and engineering qualification not checked'}
                         for key, adapter in lab.analysis_adapters.items()
                         if callable(getattr(adapter, 'conditions_preflight', None))]}


def _request(request):
    _finite_json(request)
    validate('analysis-conditions-request', request)
    for key in ('conditions_id', 'experiment_id'):
        check_id(request[key])
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,127}', request['backend']):
        raise ValueError('Conditions backend must be a registered name')
    for group in ('materials', 'loads', 'boundary_conditions'):
        for item in request['declaration'][group]:
            check_id(item['id'])
            check_id(item['selection_id'])
    for pair in request['declaration']['contact'].get('pairs', []):
        check_id(pair['selection_a'])
        check_id(pair['selection_b'])


def _support(lab, request, catalog):
    from plugins.elasticity.conditions import validate_declaration
    declaration = request['declaration']
    validate_declaration(catalog, declaration)
    adapter = lab.analysis_adapters.get(request['backend'])
    preflight = getattr(adapter, 'conditions_preflight', None)
    project = getattr(adapter, 'settings_from_conditions', None)
    if not callable(preflight) or not callable(project):
        return {'status': 'UNAVAILABLE', 'reasons': ['선택한 solver에 공통 조건 변환이 아직 연결되지 않았습니다.'],
                'native_runtime': 'NOT_CHECKED'}, None
    support = preflight(deepcopy(catalog), deepcopy(declaration))
    if (support.get('status') not in {'SUPPORTED_DECLARED_INPUTS', 'UNSUPPORTED_FOR_MODEL', 'UNSUPPORTED_FOR_CONDITIONS'}
            or not isinstance(support.get('reasons'), list) or support.get('native_runtime') != 'NOT_CHECKED'):
        raise ValueError('Adapter returned an invalid declared-input support verdict')
    binding = None
    if support['status'] == 'SUPPORTED_DECLARED_INPUTS':
        policy_hook = getattr(adapter, 'conditions_policy_identity', None)
        if not callable(policy_hook):
            raise ValueError('Condition projection must identify its adapter/Domain policy source')
        policy = policy_hook()
        if (not isinstance(policy, dict) or not policy
                or any(not isinstance(key, str) or not isinstance(value, str)
                       or not re.fullmatch(r'[0-9a-f]{64}', value) for key, value in policy.items())):
            raise ValueError('Condition projection policy hashes are incomplete')
        settings = project(deepcopy(catalog), deepcopy(declaration))
        _finite_json(settings)
        if not isinstance(settings, dict):
            raise ValueError('Adapter condition projection must be a settings mapping')
        binding = {'backend': request['backend'], 'version': adapter.version,
                   'conditions_version': getattr(adapter, 'conditions_version', None),
                   'policy': policy, 'policy_sha256': canonical_hash(policy),
                   'settings': settings, 'settings_sha256': canonical_hash(settings)}
    return support, binding


def _revision(source, request, catalog_revision):
    return canonical_hash({'source': source, 'backend': request['backend'],
                           'declaration': request['declaration'], 'catalog_revision': catalog_revision})


def save(lab, **arguments):
    request = deepcopy(arguments)
    _request(request)
    source, catalog = _parent(lab, request['experiment_id'])
    catalog_revision = canonical_hash(catalog)
    if request['cad_revision'] != source['cad_revision'] or request['catalog_revision'] != catalog_revision:
        raise ValueError('Selected CAD/catalog revision changed; reload it before saving conditions')
    support, binding = _support(lab, request, catalog)
    record = {'schema_version': '1.0', 'id': request['conditions_id'], 'created_utc': utc_now(),
              'source': source, 'request': request, 'catalog': catalog, 'catalog_revision': catalog_revision,
              'conditions_revision': _revision(source, request, catalog_revision),
              'support': support, 'adapter_binding': binding,
              'engineering': 'UNKNOWN', 'decision': 'NOT_RELEASED',
              'provenance': source_identity(Path(__file__).resolve().parents[1])}
    # A late edit of parent bytes or selection policy cannot become this record's
    # source merely because the first inspection succeeded.
    if (_parent(lab, request['experiment_id']) != (source, catalog)
            or _support(lab, request, catalog) != (support, binding)):
        raise ValueError('Conditions source changed before persistence')
    folder = _path(lab, f'analysis_conditions/{record["id"]}')
    folder.mkdir(parents=True, exist_ok=False)
    _path(lab, f'analysis_conditions/{record["id"]}/record.json')
    _path(lab, f'analysis_conditions/{record["id"]}/receipt.json')
    save_json(folder / 'record.json', record)
    save_json(folder / 'receipt.json', {'id': record['id'], 'record_sha256': _sha(folder / 'record.json')})
    return record


def inspect(lab, conditions_id):
    identifier = check_id(conditions_id)
    folder = _path(lab, f'analysis_conditions/{identifier}')
    path = _path(lab, f'analysis_conditions/{identifier}/record.json')
    receipt_path = _path(lab, f'analysis_conditions/{identifier}/receipt.json')
    receipt, record = load_json(receipt_path), load_json(path)
    if receipt.get('id') != identifier or receipt.get('record_sha256') != _sha(path):
        raise ValueError('Analysis conditions record hash/identity mismatch')
    _request(record['request'])
    if record.get('schema_version') != '1.0' or record.get('id') != identifier or record['request']['conditions_id'] != identifier:
        raise ValueError('Analysis conditions record identity mismatch')
    source, catalog = _parent(lab, record['request']['experiment_id'])
    support, binding = _support(lab, record['request'], catalog)
    expected_revision = _revision(source, record['request'], canonical_hash(catalog))
    if (record['source'] != source or record['catalog'] != catalog
            or record['request']['cad_revision'] != source['cad_revision']
            or record['catalog_revision'] != canonical_hash(catalog)
            or record['request']['catalog_revision'] != record['catalog_revision']
            or record['conditions_revision'] != expected_revision or record['support'] != support
            or record['adapter_binding'] != binding or record.get('engineering') != 'UNKNOWN'
            or record.get('decision') != 'NOT_RELEASED'):
        raise ValueError('Analysis conditions source/catalog/declaration/binding mismatch')
    return record


def list_records(lab, experiment_id):
    check_id(experiment_id)
    _parent(lab, experiment_id)
    namespace = _path(lab, 'analysis_conditions')
    if not namespace.is_dir():
        return []
    rows = []
    for folder in sorted(namespace.iterdir()):
        try:
            # The unverified header may filter unrelated records but cannot
            # supply payload or a trusted verdict to the requested model.
            path = _path(lab, f'analysis_conditions/{check_id(folder.name)}/record.json')
            raw = load_json(path)
            if raw.get('source', {}).get('experiment_id') != experiment_id:
                continue
            rows.append({'record': inspect(lab, folder.name), 'integrity': 'VERIFIED'})
        except (OSError, ValueError, KeyError, TypeError, ValidationError) as error:
            rows.append({'id': folder.name, 'integrity': 'UNKNOWN', 'error': str(error)})
    return rows


def execution(lab, parent_id, backend, conditions_id):
    record = inspect(lab, conditions_id)
    if record['source']['experiment_id'] != parent_id or record['request']['backend'] != backend:
        raise ValueError('Analysis conditions belong to a different CAD parent or solver')
    if record['support']['status'] != 'SUPPORTED_DECLARED_INPUTS' or record['adapter_binding'] is None:
        raise CapabilityUnavailable('Declared conditions cannot execute: ' + '; '.join(record['support']['reasons']))
    path = _path(lab, f'analysis_conditions/{record["id"]}/record.json')
    raw = path.read_bytes()
    import hashlib
    receipt = load_json(_path(lab, f'analysis_conditions/{record["id"]}/receipt.json'))
    if (load_json(path) != record or receipt.get('id') != record['id']
            or receipt.get('record_sha256') != hashlib.sha256(raw).hexdigest()):
        raise ValueError('Conditions changed while preparing their execution snapshot')
    reference = {'id': record['id'], 'revision': record['conditions_revision'],
                 'record_sha256': hashlib.sha256(raw).hexdigest(), 'catalog_revision': record['catalog_revision'],
                 'scope': 'USER_DECLARED_UNVERIFIED'}
    return record, deepcopy(record['adapter_binding']['settings']), reference, raw


def verify_child(folder, result):
    """Verify the copied declaration, preserving historical adapter behavior.

    No current-policy re-projection or mutable conditions namespace is needed
    to read a finished child. The original CAD-parent check remains in Core.
    """
    reference = result['provenance'].get('analysis_conditions')
    if reference is None:
        return
    path = Path(folder) / 'analysis_conditions.json'
    if path.is_symlink() or not path.resolve().is_relative_to(Path(folder).resolve()):
        raise ValueError('Child conditions snapshot must remain inside its experiment')
    if _sha(path) != reference['record_sha256']:
        raise ValueError('Child analysis conditions snapshot hash mismatch')
    record, proposal, thread = load_json(path), load_json(Path(folder) / 'proposal.json'), load_json(Path(folder) / 'thread.json')
    _request(record['request'])
    binding, declaration = record['adapter_binding'], record['request']['declaration']
    if (record['id'] != reference['id'] or record['conditions_revision'] != reference['revision']
            or record['schema_version'] != '1.0' or record['request']['conditions_id'] != record['id']
            or record['catalog_revision'] != reference['catalog_revision']
            or record['request']['catalog_revision'] != reference['catalog_revision']
            or canonical_hash(record['catalog']) != reference['catalog_revision']
            or _revision(record['source'], record['request'], reference['catalog_revision']) != reference['revision']
            or record['source']['experiment_id'] != result['parent_experiment_id']
            or record['request']['experiment_id'] != result['parent_experiment_id']
            or record['source']['result_sha256'] != result['provenance']['parent_result_sha256']
            or record['source']['cad_revision'] != result['cad_revision']
            or record['request']['cad_revision'] != result['cad_revision']
            or record['request']['backend'] != result['provenance']['adapter']
            or record['support']['status'] != 'SUPPORTED_DECLARED_INPUTS'
            or record['decision'] != 'NOT_RELEASED' or record['engineering'] != 'UNKNOWN'
            or binding is None or binding['backend'] != result['provenance']['adapter']
            or binding['version'] != result['provenance']['adapter_version']
            or binding['policy_sha256'] != canonical_hash(binding['policy'])
            or binding['settings_sha256'] != canonical_hash(binding['settings'])
            or binding['settings'] != proposal['execution']
            or binding['settings'] != result['provenance']['execution_settings']
            or proposal.get('provenance', {}).get('analysis_conditions') != reference
            or thread.get('analysis_conditions') != reference
            or proposal['model'].get('materials') != declaration['materials']
            or proposal['boundary_conditions'] != declaration['boundary_conditions']
            or proposal['loads'] != declaration['loads']
            or proposal['physics']['analysis_type'] != declaration['analysis_type']
            or proposal['model'].get('coordinate_systems') != record['catalog']['coordinate_systems']
            or proposal['model'].get('conditions_mesh') != declaration['mesh']
            or proposal['model'].get('contact_declaration') != declaration['contact']):
        raise ValueError('Child analysis conditions linkage or projected settings mismatch')
