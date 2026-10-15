"""Canonical sample policy/compiler evidence consumed by Numerical, not re-inferred.

Old integer source-row policies remain a separate legacy contract. A new frozen
resampling domain is never assigned its old rows' roles or weights implicitly.
Policy proposals are pure, unadopted previews; adoption is an explicit caller
operation, persisted by the existing Numerical owner update/CAS boundary.
"""
from __future__ import annotations
from collections import Counter
from copy import deepcopy
import math
from .storage import canonical_hash, check_id
from .data_processing_lineage import verify_channel, trace_sample, raw_key, plain

POLICY = 'caelab.observation-sample-policy/1'
PROPOSAL = 'caelab.observation-sample-policy-proposal/1'
PACKET = 'frozen-fit-inclusion.v1'
MASK_ORDER = ['RAW_SOURCE_QUALITY', 'DATA_CALCULATION', 'OPERATION_VALIDITY',
              'EXPLICIT_OBSERVATION_SAMPLE_POLICY']
INDEPENDENCE = 'DISJOINT_RAW_VALUE_CONTRIBUTORS_BETWEEN_FIT_AND_HOLDOUT'


def _policy(value):
    if not isinstance(value, dict) or set(value) != {'included', 'role', 'weight'}:
        raise ValueError('A sample policy explicitly declares inclusion, role and weight')
    if type(value['included']) is not bool or value['role'] not in {'fit', 'holdout'}:
        raise ValueError('Sample inclusion must be boolean and role fit/holdout')
    w = value['weight']
    if type(w) not in (int, float) or not math.isfinite(w) or w < 0:
        raise ValueError('Sample weight must be finite and nonnegative')
    return deepcopy(value)


def sample_domain(channel):
    verify_channel(channel)
    return {'source': deepcopy(channel['source']), 'response_channel_id': channel['response_channel_id'],
        'target_grid_id': channel['target_grid']['grid_id'],
        'sample_ids_sha256': canonical_hash([s['sample_id'] for s in channel['samples']]),
        'sample_count': len(channel['samples']), 'lineage_sha256': channel['lineage_sha256'],
        'values_sha256': canonical_hash(channel['values']),
        'recipe_refs': deepcopy(channel['recipe_refs']), 'unit': channel['metadata']['unit']}


def propose_sample_policy(channel, *, role='fit', weight=1., raw_selection=None):
    """Preview a policy, including optional explicit projection of old row choices."""
    default = _policy({'included': True, 'role': 'fit' if role == 'train' else role, 'weight': weight})
    domain = sample_domain(channel)
    entries, notes = {}, {}
    if raw_selection is not None:
        from .data_processing import compile_selection
        legacy = deepcopy(channel)
        legacy['sample_domain'] = 'raw-row-v1'
        old = compile_selection(legacy, raw_selection, default_role=role)
        projected = {r['sample_id']: r for r in old['records']}
    else:
        projected = {}
    for s in channel['samples']:
        sid = s['sample_id']
        entry = deepcopy(default)
        if sid in projected:
            row = projected[sid]
            ambiguous = row['role'] is None or row['weight'] is None
            entry.update(included=False if ambiguous else row['included'],
                         role=row['role'] or default['role'], weight=row['weight'] if row['weight'] is not None else 0.)
            if row['reasons']: notes[sid] = list(row['reasons'])
        entries[sid] = entry
    proposal = {'format': PROPOSAL, 'domain': domain, 'entries': entries,
        'notes': notes, 'projection_source': deepcopy(raw_selection), 'state': 'UNADOPTED',
        'mask_order': list(MASK_ORDER), 'independence_policy': INDEPENDENCE}
    proposal['proposal_sha256'] = canonical_hash(proposal)
    return proposal


def accept_sample_policy(proposal, *, adoption, entries=None):
    """Seal the user's explicit choice; service persists it with numerical.update.

    default + overrides is lossless compression of the reviewed per-sample map,
    not a rule for applying a policy to any future grid. The domain hash must
    still exactly match all frozen sample IDs, response, source and lineage.
    """
    body = {k: deepcopy(v) for k, v in proposal.items() if k != 'proposal_sha256'}
    if (body.get('format') != PROPOSAL or body.get('state') != 'UNADOPTED'
            or canonical_hash(body) != proposal.get('proposal_sha256')):
        raise ValueError('Policy proposal changed before explicit adoption')
    if not isinstance(adoption, dict) or set(adoption) != {'plan_document_id', 'command_id', 'session_id', 'generation'}:
        raise ValueError('Policy adoption needs its Plan owner/CAS command identity')
    for key in ('plan_document_id', 'command_id', 'session_id'): check_id(adoption[key])
    if not adoption['plan_document_id'].startswith('N') or type(adoption['generation']) is not int or adoption['generation'] < 0:
        raise ValueError('Explicit adoption belongs to a Numerical Plan generation')
    chosen = deepcopy(body['entries'] if entries is None else entries)
    if not isinstance(chosen, dict) or not chosen or set(chosen) != set(body['entries']):
        raise ValueError('Review exactly the frozen observation sample IDs')
    normalized = {sid: _policy(p) for sid, p in chosen.items()}
    counts = Counter(canonical_hash(p) for p in normalized.values())
    frequent = counts.most_common(1)[0][0]
    default = next(p for p in normalized.values() if canonical_hash(p) == frequent)
    policy = {'format': POLICY, 'domain': deepcopy(body['domain']), 'default': default,
        'overrides': {sid: p for sid, p in normalized.items() if p != default},
        'adoption': deepcopy(adoption), 'proposal_sha256': proposal['proposal_sha256'],
        'independence_policy': INDEPENDENCE}
    policy['policy_sha256'] = canonical_hash(policy)
    return policy


def validate_sample_policy(policy):
    keys = {'format', 'domain', 'default', 'overrides', 'adoption', 'proposal_sha256', 'independence_policy', 'policy_sha256'}
    if not isinstance(policy, dict) or set(policy) != keys or policy['format'] != POLICY:
        raise ValueError('Use an explicitly adopted frozen observation sample policy')
    if canonical_hash({k: v for k, v in policy.items() if k != 'policy_sha256'}) != policy['policy_sha256']:
        raise ValueError('Sample policy content/hash mismatch')
    adoption = policy['adoption']
    if not isinstance(adoption, dict) or set(adoption) != {'plan_document_id', 'command_id', 'session_id', 'generation'}:
        raise ValueError('Sample policy is missing the explicit Plan adoption identity')
    for key in ('plan_document_id', 'command_id', 'session_id'): check_id(adoption[key])
    if not adoption['plan_document_id'].startswith('N') or type(adoption['generation']) is not int or adoption['generation'] < 0:
        raise ValueError('Policy adoption belongs to a Numerical Plan generation')
    domain = policy['domain']
    if not isinstance(domain, dict) or set(domain) != {'source', 'response_channel_id', 'target_grid_id',
            'sample_ids_sha256', 'sample_count', 'lineage_sha256', 'values_sha256', 'recipe_refs', 'unit'}:
        raise ValueError('Invalid frozen sample domain')
    if type(domain['sample_count']) is not int or domain['sample_count'] < 1:
        raise ValueError('A frozen sample policy needs a nonempty observation domain')
    _policy(policy['default'])
    if not isinstance(policy['overrides'], dict): raise ValueError('Invalid sample policy overrides')
    for sid, value in policy['overrides'].items():
        check_id(sid); _policy(value)
    if policy['independence_policy'] != INDEPENDENCE:
        raise ValueError('Unrecognized train/holdout independence policy')
    return policy


def compile_samples(channel, selection, *, base_weight=1.):
    domain = sample_domain(channel)
    if type(base_weight) not in (int, float) or not math.isfinite(base_weight) or base_weight <= 0:
        raise ValueError('Experiment weight must be finite and positive')
    policy = selection.get('sample_policy') if isinstance(selection, dict) else None
    error = None
    if policy is None:
        error = 'EXPLICIT_SAMPLE_POLICY_REQUIRED'
    else:
        validate_sample_policy(policy)
        if policy['domain'] != domain:
            error = 'SAMPLE_POLICY_FROZEN_DOMAIN_MISMATCH'
        elif set(policy['overrides']) - {s['sample_id'] for s in channel['samples']}:
            error = 'SAMPLE_POLICY_UNKNOWN_SAMPLE_ID'
    records, groups, used = [], {}, {}
    conflicts, cache = [], {}
    for i, sample in enumerate(channel['samples']):
        reasons = []
        flags = {'raw_quality': bool(channel['quality_valid'][i]),
                 'data_calculation': bool(channel['calculation_valid'][i]),
                 'operation_valid': bool(channel['operation_valid'][i])}
        if not flags['raw_quality']: reasons.append('RAW_QUALITY: ' + channel['quality_reasons'][i])
        if not flags['data_calculation']: reasons.append('DATA_CALCULATION: ' + channel['calculation_reasons'][i])
        if not flags['operation_valid']: reasons.append('OPERATION_INVALID: ' + channel['operation_reasons'][i])
        if sample['import_index'] is None: reasons.append('NO_RETAINED_IMPORT_SAMPLE')
        chosen = None if error else deepcopy(policy['overrides'].get(sample['sample_id'], policy['default']))
        flags['plan_included'] = chosen['included'] if chosen else None
        if error: reasons.append(error)
        elif not chosen['included']: reasons.append('PLAN_EXCLUDED')
        elif chosen['weight'] == 0: reasons.append('ZERO_PLAN_WEIGHT')
        record = {**deepcopy(sample), 'time': channel['axis']['values'][i], 'included': not reasons,
            'role': chosen['role'] if chosen else None, 'weight': chosen['weight'] if chosen else None,
            'reasons': reasons, 'masks': flags, 'mask_order': list(MASK_ORDER),
            'display_visible': channel['display_visible'][i],
            'recipe_refs': deepcopy(channel['recipe_refs']),
            'stage_ref': deepcopy(channel['lineage']['nodes'][sample['sample_id']]['stage'])}
        # Store exact signed source lineage once in the frozen observation DAG.
        # Per-row evidence references that graph; do not duplicate covariance or
        # N complete curves when weights differ.
        if not reasons:
            trace = trace_sample(channel, sample['sample_id'], cache=cache)
            if trace['coefficient_status'] != 'KNOWN':
                record['reasons'].append('VALUE_LINEAGE_UNKNOWN')
                record['included'] = False
            else:
                role = chosen['role']
                for term in trace['terms']:
                    key = raw_key(term['raw_ref'])
                    previous = used.get(key)
                    if previous and previous['role'] != role:
                        conflicts.append({'raw_key': list(key), 'left': previous,
                            'right': {'role': role, 'sample_id': sample['sample_id']}})
                    used[key] = {'role': role, 'sample_id': sample['sample_id']}
                groups.setdefault(role, []).append((sample['import_index'], chosen['weight']))
        records.append(record)
    blocked = error is not None or bool(conflicts)
    compiled = [] if blocked else [{'role': role, 'indexes': [i for i, _ in rows],
        'sample_weights': [w for _, w in rows], 'experiment_weight': float(base_weight)} for role, rows in sorted(groups.items())]
    return {'format': 'caelab.sample_compilation/2', 'state': 'BLOCKED' if blocked else 'READY',
        'blocking_reasons': ([error] if error else []) + (['RAW_CONTRIBUTOR_OVERLAP'] if conflicts else []),
        'records': records, 'groups': compiled, 'counts': {role: sum(len(g['indexes']) for g in compiled if g['role'] == role) for role in ('fit', 'holdout')},
        'selection': deepcopy(selection), 'domain': domain, 'source': deepcopy(channel['source']),
        'recipe_refs': deepcopy(channel['recipe_refs']), 'mask_order': list(MASK_ORDER),
        'display_affects_fit': False, 'independence_policy': INDEPENDENCE,
        'independence_conflicts': conflicts}


def require_independent_samples(experiments):
    """Canonical cross-trial raw contributor check, shared by fit and consumers."""
    used = {}
    for e in experiments:
        obs = e.get('observations') or {}
        n = len(obs.get('value', [])) if obs.get('kind') == 'series' else 0
        mask = e['_mask'] if '_mask' in e else e.get('mask', [True] * n)
        if len(mask) != n and n: raise ValueError('Observation mask length differs from sample count')
        channel = obs.get('processing_channel')
        if channel and channel.get('lineage'):
            verify_channel(channel)
            samples = obs.get('sample_ids', [])
            if len(samples) != n or len(set(samples)) != n:
                raise ValueError('Exact processing sample IDs are missing or duplicated')
            cache = {}
            keys = []
            for sid, included in zip(samples, mask):
                if not included: continue
                trace = trace_sample(channel, sid, cache=cache)
                if trace['coefficient_status'] != 'KNOWN':
                    raise ValueError('Cannot claim independence with unknown value lineage')
                keys.extend((raw_key(t['raw_ref']), sid) for t in trace['terms'])
        else:
            if obs.get('sample_domain') == 'derived-grid-v2':
                raise ValueError('Derived observations have no verifiable processing lineage')
            source = e.get('observation_source') or {}
            digest = source.get('source_sha256')
            column = obs.get('source_column_identity', obs.get('mapping', {}).get('column'))
            rows = plain(obs.get('source_rows'))
            if not digest or column is None or rows is None: continue
            if len(rows) != n or any(type(r) is not int or r < 0 for r in rows):
                raise ValueError('Legacy source_rows must remain exact integer raw rows')
            keys = [((digest, str(column), row), row) for row, yes in zip(rows, mask) if yes]
        driver = (e.get('observation_source') or {}).get('driver_binding', {}).get('driver_response')
        if driver and driver.get('processing_channel'):
            from .data_processing_lineage import aligned_driver_indexes
            indexes = aligned_driver_indexes(obs, driver)
            dc = driver['processing_channel']; cache = {}
            for k, included in enumerate(mask):
                if not included: continue
                sid = driver['sample_ids'][indexes[k]]
                trace = trace_sample(dc, sid, cache=cache)
                if trace['coefficient_status'] != 'KNOWN':
                    raise ValueError('Cannot claim independence with unknown measured driver lineage')
                keys.extend((raw_key(t['raw_ref']), sid) for t in trace['terms'])
        for key, sample in keys:
            if key in used and used[key][0] != e['role']:
                raise ValueError('RAW_CONTRIBUTOR_OVERLAP: fit and holdout share measured source cells: ' + repr(key))
            used[key] = (e['role'], e['id'], sample)
    return {'policy': INDEPENDENCE, 'status': 'DISJOINT', 'raw_cell_count': len(used)}


def _trial(e):
    obs = plain(e['observations'])
    source = plain(e.get('observation_source') or {})
    n = len(obs['value']) if obs.get('kind') == 'series' else 1
    trial = {'trial_id': e['id'], 'observation_sha256': canonical_hash(obs),
        'settings_sha256': canonical_hash(plain(e.get('settings', {}))),
        'source_sha256': canonical_hash(source), 'unit': obs['unit'], 'role': e['role'],
        'response': e['response'], 'mask': plain(e.get('mask', e.get('_mask', [True] * n))),
        'weight': e['weight'], 'scale': e.get('scale', 1.),
        'sample_weights': plain(e.get('sample_weights', [1.] * n)),
        'extra_provenance': {'compilation': deepcopy(source.get('compilation')),
            'source': source, 'mask_order': deepcopy(source.get('compilation', {}).get('mask_order', ['LEGACY_RAW_ROW_CONTRACT'])),
            'recipe_refs': deepcopy(obs.get('recipe_refs', [])),
            'processing_channel': deepcopy(obs.get('processing_channel'))}}
    if 'source_rows' in obs: trial['source_rows'] = deepcopy(obs['source_rows'])
    for key in ('sample_ids', 'coordinate_sample_ids', 'target_grid', 'response_channel_id', 'sample_domain', 'lineage_sha256'):
        if key in obs: trial[key] = deepcopy(obs[key])
    return trial


def freeze_fit_inclusion(experiments):
    """Canonical Data-produced packet; Numerical verifies rather than remasks it."""
    independence = require_independent_samples(experiments)
    trials = [_trial(e) for e in experiments]
    if len({t['trial_id'] for t in trials}) != len(trials):
        raise ValueError('Frozen trial IDs must be distinct')
    packet = {'format': PACKET, 'producer': 'caelab.data_processing', 'trials': trials,
              'independence': independence}
    packet['packet_sha256'] = canonical_hash(packet)
    consume_frozen_fit_inclusion(experiments, packet)
    return packet


def consume_frozen_fit_inclusion(experiments, packet):
    """Minimal consumer boundary for the Numerical lane's proposed v1 packet.

    This does not implement a candidate engine. It checks exact inputs/settings,
    role/weight/mask/scale/unit and preserves all extra provenance by deepcopy.
    Caller-supplied hashes alone are insufficient: the canonical compiler is
    rechecked against each retained channel and explicitly adopted sample policy.
    """
    if not isinstance(packet, dict) or packet.get('format') != PACKET:
        raise ValueError('Unsupported frozen fit inclusion packet')
    if canonical_hash({k: v for k, v in packet.items() if k != 'packet_sha256'}) != packet.get('packet_sha256'):
        raise ValueError('Frozen inclusion packet hash mismatch')
    expected = [_trial(e) for e in experiments]
    trials = packet.get('trials', [])
    if len(trials) != len(expected): raise ValueError('Frozen trial count differs')
    if len({t.get('trial_id') for t in trials}) != len(trials): raise ValueError('Duplicate frozen trial')
    by_id = {t['trial_id']: t for t in trials}
    result = deepcopy(experiments)
    for e, wanted in zip(result, expected):
        row = by_id.get(e['id'])
        if row is None: raise ValueError('A frozen trial is missing')
        for key, value in wanted.items():
            if key == 'extra_provenance': continue
            if row.get(key) != value: raise ValueError('Frozen trial ' + key + ' mismatch')
        extra = row.get('extra_provenance')
        if not isinstance(extra, dict) or any(extra.get(k) != v for k, v in wanted['extra_provenance'].items()):
            raise ValueError('Frozen canonical provenance differs from the consumed observation')
        if ('source_rows' in row) != ('source_rows' in wanted):
            raise ValueError('A derived sample cannot be assigned a fabricated legacy raw-row field')
        # In particular strings must never replace the historical integer field.
        if 'source_rows' in row and any(type(r) is not int for r in row['source_rows']):
            raise ValueError('source_rows accepts only integer raw source identities')
        obs = e['observations']; channel = obs.get('processing_channel')
        source = e.get('observation_source') or {}
        if channel:
            from .data_processing_lineage import verify_response, SOURCE_KEYS
            verify_response(obs, complete=True)
            if source.get('source_sha256') != channel['source']['source_sha256']:
                raise ValueError('Raw file hash differs from canonical observation source hash field')
            if any(source.get('data_source', {}).get(k) != channel['source'][k]
                    for k in SOURCE_KEYS if k != 'source_sha256'):
                raise ValueError('Frozen Data document/import identity differs from observation source')
        binding = source.get('driver_binding')
        if binding:
            from .data_processing_lineage import aligned_driver_indexes
            driver = binding['driver_response']
            indexes = aligned_driver_indexes(obs, driver)
            if (binding.get('driver_indexes') != indexes
                    or binding.get('observation_sample_ids') != obs.get('sample_ids')
                    or binding.get('coordinate_sample_ids') != obs.get('coordinate_sample_ids')):
                raise ValueError('Frozen driver binding indexes/sample identities changed')
            from .material_test import measured_protocol
            recipe = binding['recipe']
            expected_settings = measured_protocol(plain(e['settings']),
                {'execution_status': 'SUCCEEDED', 'responses': {recipe['channel']: driver}}, recipe)
            if canonical_hash(expected_settings) != canonical_hash(plain(e['settings'])):
                raise ValueError('Frozen measured driver and evaluator time/deformation settings differ')
        if channel and channel.get('sample_domain') == 'derived-grid-v2':
            compilation = (e.get('observation_source') or {}).get('compilation') or {}
            fresh = compile_samples(channel, compilation.get('selection'), base_weight=e['weight'])
            if fresh['state'] != 'READY' or fresh != compilation:
                raise ValueError('Canonical sample compilation differs from frozen evidence')
            group = next((g for g in fresh['groups'] if g['role'] == e['role']), None)
            indexes = set(group['indexes']) if group else set()
            weights = dict(zip(group['indexes'], group['sample_weights'])) if group else {}
            if (e['mask'] != [i in indexes for i in range(len(obs['value']))]
                    or e['sample_weights'] != [weights.get(i, 0.) for i in range(len(obs['value']))]):
                raise ValueError('Experiment mask/weights differ from canonical compiler')
        e['frozen_fit_inclusion'] = deepcopy(row)  # Do not strip future provenance extensions.
        # Small original packet header + its original per-trial row permit the
        # existing Numerical evidence collector to verify canonical admission
        # without N duplicated complete packets or a second compiler/schema.
        e['frozen_fit_packet'] = {k: deepcopy(packet[k]) for k in
            ('format', 'producer', 'packet_sha256', 'independence')}
    independence = require_independent_samples(result)
    if packet.get('independence') != independence or packet.get('producer') != 'caelab.data_processing':
        raise ValueError('Frozen canonical independence evidence differs')
    return result
