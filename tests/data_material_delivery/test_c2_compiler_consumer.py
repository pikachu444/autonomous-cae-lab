"""Canonical admission adversaries; no solvers or fabricated adoption receipts.

The frozen Windows demo is an immutable compiler-output fixture only. Actual
owner adoption/managed execution is covered by test_c2_workbench_chain.py.
"""
from copy import deepcopy
from pathlib import Path
import json
import math
import numpy as np
import pytest
from caelab.storage import canonical_hash
from caelab.data_processing_selection import (
    consume_frozen_fit_inclusion, freeze_fit_inclusion, require_independent_samples, _trial)
from caelab.data_processing_lineage import verify_channel, verify_response, aligned_driver_indexes
from caelab.data_processing_consumer import retained_assessment, admit_snapshot
from caelab.numerical_candidate_detail import consume_frozen_fit_inclusion as numerical_consume, plain
from caelab.numerical_fit_lineage import lineage_assessment


@pytest.fixture(scope='module')
def demo():
    folder=Path(__file__).parent/'fixtures'/'c2_canonical_demo'
    exps=json.loads((folder/'frozen-experiments.json').read_text(encoding='utf-8'))
    packet=json.loads((folder/'frozen-fit-inclusion.v1.json').read_text(encoding='utf-8'))
    assert packet['packet_sha256']=='cf45a6acd3f7e396c89c1bc8f5cb57ee9b81fbe7eee2b76c0a0db87ac9f072d3'
    return exps,packet



@pytest.fixture(scope='module')
def bound(tmp_path_factory):
    from .c2_fixtures import make_workbench, make_processed_plan
    w=make_workbench(tmp_path_factory.mktemp('bound_canonical'))
    try:
        b=make_processed_plan(w)
        yield b['args']['experiments'], b['args']['frozen_inclusion']
    finally: assert w.shutdown()['joined']


def reseal(experiments, packet):
    """Adversarially rebuild local hashes, NOT a call to Data's producer."""
    value=deepcopy(packet);value['trials']=[_trial(e) for e in experiments]
    value['packet_sha256']=canonical_hash({k:v for k,v in value.items() if k!='packet_sha256'})
    return value


def test_original_windows_output_enters_numerical_only_via_actual_data_consumer(demo):
    experiments,packet=demo
    before=canonical_hash(experiments)
    accepted=numerical_consume(experiments,packet)
    assert len(accepted)==2 and all(len(e['observations']['sample_ids'])==138 for e in accepted)
    assert all('source_rows' not in e['observations'] for e in accepted)
    assessment=lineage_assessment(accepted)
    assert assessment['status']=='CANONICAL_DATA_CONSUMER_VERIFIED'
    assert assessment['adoption_receipt_authentication'].startswith('NOT_INFERRED')
    assert canonical_hash(experiments)==before
    # Object hash and raw file hash are distinct and cannot be interchanged.
    t=packet['trials'][0]
    assert t['source_sha256']==canonical_hash(experiments[0]['observation_source'])
    assert t['source_sha256']!=t['extra_provenance']['source']['source_sha256']
    assert retained_assessment(accepted)['packet_sha256']==packet['packet_sha256']


@pytest.mark.parametrize('mutation',['mask','sample_weights','settings','source_hash_name','axis_unit','driver_grid','missing_dag','fake_source_rows'])
def test_resealed_packet_cannot_bypass_actual_sample_contract(demo,bound,mutation):
    experiments,packet=deepcopy(bound if mutation in {'settings','driver_grid'} else demo);e=experiments[0];obs=e['observations']
    if mutation=='mask':e['mask'][0]=not e['mask'][0]
    elif mutation=='sample_weights':e['sample_weights'][0]+=1.
    elif mutation=='settings':e['settings']['deformation_gradient'][0][0][0]+=0.125
    elif mutation=='source_hash_name':e['observation_source']['source_sha256']=packet['trials'][0]['source_sha256']
    elif mutation=='axis_unit':obs['axes'][0]['unit']='ms'
    elif mutation=='driver_grid':
        e['observation_source']['driver_binding']['driver_response']['target_grid']['values'][1]+=.001
    elif mutation=='missing_dag':
        ch=obs['processing_channel'];node=ch['lineage']['nodes'][obs['sample_ids'][1]]
        del ch['lineage']['nodes'][node['inputs'][0]['sample_id']]
        ch['lineage_sha256']=canonical_hash(ch['lineage']);obs['lineage_sha256']=ch['lineage_sha256']
    else:obs['source_rows']=obs['sample_ids'][:]
    malformed=reseal(experiments,packet)
    with pytest.raises((ValueError,KeyError)):numerical_consume(experiments,malformed)


def test_different_derived_ids_do_not_make_shared_raw_contributors_independent(demo):
    experiments,packet=deepcopy(demo)
    a,b=experiments
    a['mask']=[i==1 for i in range(138)] # 4.05s: raw40+41
    b['mask']=[i==2 for i in range(138)] # 4.10s: raw41
    assert a['observations']['sample_ids'][1]!=b['observations']['sample_ids'][2]
    with pytest.raises(ValueError,match='RAW_CONTRIBUTOR_OVERLAP'):require_independent_samples(experiments)
    from caelab.identification import require_independent_rows
    with pytest.raises(ValueError,match='RAW_CONTRIBUTOR_OVERLAP'):require_independent_rows(experiments)
    with pytest.raises(ValueError,match='RAW_CONTRIBUTOR_OVERLAP'):freeze_fit_inclusion(experiments)


def test_excluded_raw82_cannot_be_reintroduced_by_resealed_output_validity(demo):
    ch=deepcopy(demo[0][0]['observations']['processing_channel'])
    indexes=[i for i,t in enumerate(ch['axis']['values']) if 8.15-1e-12<=t<=8.25+1e-12]
    assert len(indexes)==3 and all(not ch['operation_valid'][i] for i in indexes)
    i=indexes[0];sample=ch['samples'][i];node=ch['lineage']['nodes'][sample['sample_id']]
    node['operation_valid']=True
    for key in ('quality_valid','calculation_valid','operation_valid'):ch[key][i]=True
    ch['lineage_sha256']=canonical_hash(ch['lineage'])
    with pytest.raises(ValueError,match='excluded raw|validity|Derived sample ID'):verify_channel(ch)


def test_value_contributor_cannot_be_hidden_from_quality_footprint(demo):
    ch=deepcopy(demo[0][0]['observations']['processing_channel'])
    sample=ch['samples'][1];node=ch['lineage']['nodes'][sample['sample_id']]
    node['validity_inputs']=node['validity_inputs'][:1]
    assert len(node['inputs'])==2
    ch['lineage_sha256']=canonical_hash(ch['lineage'])
    with pytest.raises(ValueError,match='validity footprint'):verify_channel(ch)


def test_driver_time_unit_is_checked_even_when_grid_object_was_not_changed(bound):
    e=deepcopy(bound[0][0]);o=e['observations'];d=e['observation_source']['driver_binding']['driver_response']
    d['axes'][0]['unit']='ms'
    with pytest.raises(ValueError,match='unit|metadata'):aligned_driver_indexes(o,d)


def test_canonical_header_loss_is_not_downgraded_to_verified_legacy(demo):
    exps=consume_frozen_fit_inclusion(*demo)
    del exps[0]['frozen_fit_packet']
    with pytest.raises(ValueError,match='packet header'):retained_assessment(exps)
    legacy=[{'id':'Eleg','observations':{'sample_ids':['A','B']}}]
    assert lineage_assessment(legacy)['derived_sample_independence']=='NOT_VERIFIED'


def test_missing_canonical_packet_is_not_admitted_by_a_legacy_alias(demo):
    exps,p=deepcopy(demo)
    with pytest.raises(ValueError,match='original frozen_inclusion'):
        admit_snapshot({'experiments':exps},{'experiments':exps})
    with pytest.raises(ValueError,match='not both'):
        admit_snapshot({'experiments':exps,'frozen_inclusion':p},{'experiments':exps,'frozen_inclusion':p},legacy_packet=p)
    changed=deepcopy(p);changed['format']='caelab.frozen-fit-inclusion.v1'
    with pytest.raises(ValueError):numerical_consume(exps,changed)


def test_future_extra_provenance_is_losslessly_detached(demo):
    exps,p=deepcopy(demo)
    p['trials'][0]['extra_provenance']['lab_note']={'note':['원문'], 'format':'private-note-v1'}
    p['packet_sha256']=canonical_hash({k:v for k,v in p.items() if k!='packet_sha256'})
    accepted=numerical_consume(exps,p)
    assert retained_assessment(accepted)['packet_sha256']==p['packet_sha256']
    p['trials'][0]['extra_provenance']['lab_note']['note'].append('not frozen')
    assert accepted[0]['frozen_fit_inclusion']['extra_provenance']['lab_note']['note']==['원문']


def test_one_pass_plain_preserves_original_nullable_transport_semantics():
    from caelab.numerical import _nullable
    value={'a':[np.int64(3),np.float64(2.),np.float64(float('nan')),float('inf')],
           'b':(np.array([1.,float('-inf')]),{'s':'1e','truth':np.bool_(True)})}
    def old(v):
        v=_nullable(v)
        if isinstance(v,dict):return {k:old(x) for k,x in v.items()}
        if isinstance(v,(list,tuple)):return [old(x) for x in v]
        if isinstance(v,np.generic):return old(v.item())
        return v
    assert plain(value)==old(value)
