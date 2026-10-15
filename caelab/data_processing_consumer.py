"""Thin transport/consumer adapters for the single canonical Data compiler.

No candidate engine, compiler, sample policy or schema is defined here. The
existing frozen-fit-inclusion.v1 packet is validated by data_processing_selection
at every admission; legacy Numerical carriers remain explicitly unverified.
"""
from __future__ import annotations
from copy import deepcopy

from .storage import canonical_hash
from .data_processing_selection import PACKET, consume_frozen_fit_inclusion
from .data_processing_lineage import trace_sample


def is_canonical_observation(observation):
    return bool(set(observation) & {'processing_channel', 'target_grid', 'sample_domain', 'coordinate_sample_ids'})


def admit_snapshot(inputs, submitted_arguments, *, legacy_packet=None):
    """Validate retained inputs, not merely their self hashes or a field alias."""
    experiments = inputs['experiments']
    packet = inputs.get('frozen_inclusion')
    submitted = submitted_arguments.get('frozen_inclusion')
    if packet is not None:
        if legacy_packet is not None or inputs.get('fit_inclusion') is not None:
            raise ValueError('Choose canonical frozen_inclusion or the explicit legacy carrier, not both')
        if submitted is None or canonical_hash(packet) != canonical_hash(submitted):
            raise ValueError('Frozen Data packet differs from the original submitted arguments')
        # Bind the exact source/settings/mask/policy to both original submission
        # and retained snapshot. Renaming a raw hash to a source-object hash, or
        # resealing only the snapshot, cannot create new admitted inputs.
        consume_frozen_fit_inclusion(submitted_arguments['experiments'], submitted)
        accepted = consume_frozen_fit_inclusion(experiments, packet)
        return accepted, {'format': PACKET, 'producer': packet['producer'],
            'packet_sha256': packet['packet_sha256'], 'status': 'CANONICAL_CHECK_PASSED',
            'independence': deepcopy(packet['independence'])}
    if submitted is not None or any(is_canonical_observation(e.get('observations', {})) for e in experiments):
        raise ValueError('Canonical processing observations require their original frozen_inclusion packet')
    return deepcopy(experiments), None


def retained_assessment(experiments):
    """Reassemble ORIGINAL transported rows/header, then call Data's consumer.

    This does not generate a packet or infer VERIFIED from a label. Its original
    packet_sha256 must match every exact retained trial and canonical admission.
    No header means no canonical verification claim, including old C1 results.
    """
    headers = [e.get('frozen_fit_packet') for e in experiments]
    if not headers or not all(isinstance(h, dict) for h in headers):
        if any(is_canonical_observation(e.get('observations', {})) for e in experiments):
            raise ValueError('Canonical Data detail lost its original verified packet header')
        return None
    if any(h != headers[0] for h in headers):
        raise ValueError('Retained trials belong to different canonical Data packets')
    header = headers[0]
    if set(header) != {'format', 'producer', 'packet_sha256', 'independence'}:
        raise ValueError('Retained Data packet header changed')
    packet = {**deepcopy(header), 'trials': [deepcopy(e['frozen_fit_inclusion']) for e in experiments]}
    consume_frozen_fit_inclusion(experiments, packet)
    return {'status': 'CANONICAL_DATA_CONSUMER_VERIFIED',
        'derived_sample_independence': 'VERIFIED_DISJOINT_RAW_VALUE_CONTRIBUTORS',
        'packet_sha256': packet['packet_sha256'], 'producer': packet['producer'],
        'independence': deepcopy(packet['independence']),
        'compiler_or_resampling_performed': False,
        'adoption_receipt_authentication': 'NOT_INFERRED_FROM_PACKET; actual owner command receipts are separate'}


def candidate_sample_metadata(experiment, index):
    """Read existing DAG metadata; no interpolation, new ID, or model evaluation."""
    obs = experiment['observations']
    if not obs.get('processing_channel'):
        return {}
    sid = obs['sample_ids'][index]
    weights = experiment.get('sample_weights')
    return {'coordinate_sample_id': obs['coordinate_sample_ids'][index],
        'sample_weight': weights[index] if weights is not None else 1.,
        'response_channel_id': obs['response_channel_id'],
        'lineage_ref': {'sample_id': sid, 'lineage_sha256': obs['lineage_sha256'],
                        'target_grid_id': obs['target_grid']['grid_id']},
        'value_lineage': trace_sample(obs['processing_channel'], sid),
        'mask_order': deepcopy((experiment.get('observation_source') or {}).get('compilation', {}).get('mask_order')),
        'recipe_refs': deepcopy(obs.get('recipe_refs', []))}


def extend_fit_transport(observation, experiment, fit):
    """Extend existing typed tool properties; canonical semantics stay in Data."""
    string = {'type': 'string', 'minLength': 1}
    ids = {'type': 'array', 'items': string}
    obj = {'type': 'object'}
    array = {'type': 'array'}
    observation['properties'].update(deepcopy({
        'coordinate_sample_ids': ids, 'source_row_dependencies': {'type': 'array', 'items': {
            'type': 'array', 'items': {'type': 'integer', 'minimum': 0}}},
        'response_channel_id': string, 'sample_domain': string, 'lineage_sha256': string,
        'target_grid': obj, 'processing_channel': obj, 'recipe_refs': array,
        'raw_samples': obj, 'segments': array, 'operation_status': string}))
    experiment['properties'].update(deepcopy({
        'sample_weights': {'type': 'array', 'items': {'type': 'number', 'minimum': 0}},
        'frozen_fit_inclusion': obj, 'frozen_fit_packet': obj}))
    fit['properties']['frozen_inclusion'] = deepcopy(obj)
