"""Registered scalar scenarios on one immutable CAD and condition template.

Core stores/verifies identities; the analysis adapter advertises and binds
Domain inputs. Numerical algorithms do not regenerate or rebind native faces.
"""
from copy import deepcopy
import hashlib
import math
from pathlib import Path

from filelock import FileLock

from . import registration_transaction as registration
from .analysis_conditions import execution, _path
from .contracts import Candidate, CapabilityUnavailable
from .registry import register_parameter
from .storage import canonical_hash, check_id, load_json, save_json, source_identity


class ConditionInputRejected(ValueError):
    """A retained Domain rejection, distinct from a Core identity failure."""


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _leaf(value, path):
    if not isinstance(path, list) or not path or any(type(key) not in (str, int) for key in path):
        raise ValueError('Condition input requires an advertised leaf path')
    current = value
    for key in path[:-1]:
        current = current[key]
    return current, path[-1], current[path[-1]]


def describe(lab, conditions_id):
    record = lab.inspect_analysis_conditions(conditions_id)
    backend = record['request']['backend']
    record, settings, reference, raw = execution(lab, record['source']['experiment_id'], backend, conditions_id)
    adapter = lab.analysis_adapters[backend]
    hooks = [getattr(adapter, name, None) for name in
             ('condition_input_descriptors', 'bind_condition_inputs', 'condition_input_policy_identity')]
    if not all(callable(hook) for hook in hooks):
        raise CapabilityUnavailable('This solver has no advertised saved-condition research inputs')
    descriptors = hooks[0](deepcopy(record['catalog']), deepcopy(record['request']['declaration']))
    if not isinstance(descriptors, list) or not 1 <= len(descriptors) <= 32:
        raise ValueError('Condition input advertisement must contain 1..32 descriptors')
    ids, paths = set(), set()
    for item in descriptors:
        if set(item) != {'id', 'label', 'unit', 'value', 'lower', 'upper', 'declaration_path'}:
            raise ValueError('Incomplete condition input descriptor')
        check_id(item['id'])
        if (item['id'] in ids or not all(isinstance(item[key], str) and item[key].strip() for key in ('label', 'unit'))
                or not all(_finite(item[key]) for key in ('value', 'lower', 'upper'))
                or not item['lower'] <= item['value'] <= item['upper'] or item['lower'] >= item['upper']):
            raise ValueError('Ambiguous/nonfinite condition input descriptor')
        path_key = canonical_hash(item['declaration_path'])
        if path_key in paths or _leaf(record['request']['declaration'], item['declaration_path'])[2] != item['value']:
            raise ValueError('Condition descriptor differs from its declared scalar location')
        ids.add(item['id']); paths.add(path_key)
    policy = hooks[2]()
    if (not isinstance(policy, dict) or not policy or
            any(not isinstance(name, str) or not isinstance(sha, str) or len(sha) != 64
                or any(c not in '0123456789abcdef' for c in sha) for name, sha in policy.items())):
        raise ValueError('Condition input policy source identity is incomplete')
    fingerprint = {'backend': backend, 'version': adapter.version, 'input_policy': policy,
                   'projection_policy_sha256': record['adapter_binding']['policy_sha256']}
    revision = canonical_hash({'record_sha256': hashlib.sha256(raw).hexdigest(),
                               'descriptors': descriptors, 'fingerprint': fingerprint})
    candidates = [Candidate(native={'backend': backend, 'document': revision, 'object': 'analysis_conditions',
        'path': item['id'], 'alias': ''}, label=item['label'], unit=item['unit'], value=item['value'],
        lower=item['lower'], upper=item['upper'], source_sha256=revision).__dict__ for item in descriptors]
    return {'source': deepcopy(record['source']), 'backend': backend, 'conditions_id': conditions_id,
            'catalog_revision': record['catalog_revision'], 'conditions_revision': record['conditions_revision'],
            'template_revision': revision, 'descriptors': descriptors,
            'condition_input_descriptors_sha256': canonical_hash(descriptors), 'candidates': candidates,
            'fingerprint': fingerprint, 'record': record, 'reference': reference,
            'rebind_policy': 'FIXED_CAD_NO_REBIND'}


def bind(lab, template, assignments):
    descriptors = {item['id']: item for item in template['descriptors']}
    if (not isinstance(assignments, dict) or not assignments or
            any(name not in descriptors or not _finite(value) or
                not descriptors[name]['lower'] <= value <= descriptors[name]['upper']
                for name, value in assignments.items())):
        raise ValueError('Condition candidates require advertised in-bound finite scalar values')
    record = template['record']; original = record['request']['declaration']
    adapter = lab.analysis_adapters[template['backend']]
    try:
        bound = adapter.bind_condition_inputs(deepcopy(record['catalog']), deepcopy(original), deepcopy(assignments))
    except ValueError as error:
        raise ConditionInputRejected(str(error)) from error
    verify_bound(template, assignments, bound)
    return bound


def verify_bound(template, assignments, bound):
    """Check a retained declaration without executing a newer Domain policy."""
    descriptors = {item['id']: item for item in template['descriptors']}
    original = template['record']['request']['declaration']
    if (not isinstance(assignments, dict) or not assignments or
            any(name not in descriptors or not _finite(value) or
                not descriptors[name]['lower'] <= value <= descriptors[name]['upper']
                for name, value in assignments.items())):
        raise ValueError('Condition candidates require advertised in-bound finite scalar values')
    canonical_hash(bound)
    expected = deepcopy(original); changed_items = set()
    for name, value in assignments.items():
        path = descriptors[name]['declaration_path']; target, key, old = _leaf(expected, path)
        target[key] = value
        if old != value:
            changed_items.add((path[0], path[1]))
    for group, index in changed_items:
        # Only the source of a changed item may receive Domain scenario text.
        # Fixed engineering context, selections and every other value are exact.
        source = bound[group][index]['source']
        if group == 'materials' and (source.get('category') != 'ASSUMED' or
                'qualification UNKNOWN' not in source.get('description', '')):
            raise ValueError('Numerical material candidates cannot inherit measured qualification')
        if group == 'loads' and (not isinstance(source, str) or 'ASSUMED numerical scenario' not in source):
            raise ValueError('Numerical load candidates require explicit assumed provenance')
        expected[group][index]['source'] = deepcopy(source)
    if canonical_hash(expected) != canonical_hash(bound):
        raise ValueError('Condition binding changed undeclared fixed context')


def register(lab, *, study_id, conditions_id, input_id, parameter_id, display_name, lower, upper, mode='free'):
    lab.inspect_study(study_id)
    template = describe(lab, conditions_id)
    if template['source']['study_id'] != study_id:
        raise ValueError('Condition inputs belong to another study')
    found = [item for item in template['candidates'] if item['native']['path'] == input_id]
    if len(found) != 1:
        raise ValueError('Condition input was not advertised by this solver/template')
    # Probe declared input effects only, never a fabricated physics validation.
    before = canonical_hash(template['record']['request']['declaration'])
    probes = [bind(lab, template, {input_id: value}) for value in (lower, upper)]
    effect = {'status': 'PASS', 'scope': 'DECLARED_SCALAR_BINDING_ONLY', 'before_sha256': before,
              'after_sha256': [canonical_hash(value) for value in probes], 'physical': 'UNKNOWN'}
    if effect['after_sha256'][0] == effect['after_sha256'][1]:
        raise ValueError('Selected condition variable has no declared scalar effect')
    path = lab.store / 'studies' / check_id(study_id) / 'parameters.json'
    with FileLock(str(path)+'.lock', timeout=30), lab._registration_file_lock:
        registration.assert_no_pending(lab.store)
        registry = load_json(path)
        entry = register_parameter(registry['entries'], Candidate(**found[0]), parameter_id=parameter_id,
            display_name=display_name, lower=lower, upper=upper, mode=mode, effect=effect, effect_kind='model_input')
        entry.update(target='analysis_conditions', conditions_id=conditions_id,
            conditions_template_revision=template['template_revision'],
            condition_input_descriptors_sha256=template['condition_input_descriptors_sha256'])
        if describe(lab, conditions_id) != template:
            raise ValueError('Condition input source changed during registration')
        registry['entries'].append(entry); registry['revision'] += 1
        save_json(path, registry)
        save_json(path.parent/'registry_history'/f"{registry['revision']:04d}.json", registry)
        return entry


def verify_current(lab, plan, snapshot):
    template = describe(lab, plan['fixed_cad']['conditions_id'])
    if template != plan['fixed_cad']:
        raise ValueError('Fixed CAD/conditions/input policy changed after planning')
    if (canonical_hash(lab.registry(plan['study_id'])) != plan['registry_sha256'] or
            canonical_hash(snapshot) != plan['registry_sha256'] or
            source_identity(Path(__file__).resolve().parents[1])['core_source_sha256'] != plan['core_source_sha256']):
        raise ValueError('Fixed CAD campaign registry/Core source changed')
    return template
