"""Typed Numerical carrier only. Data compiler independence is NOT certified."""
from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator

from caelab.assist.experts import _OBSERVATIONS, _EXPERIMENT
from caelab.numerical_candidate_detail import freeze_fit_input, table_rows
from caelab.numerical_fit_lineage import validate_lineage_fields, consume_data_extensions, lineage_assessment
from caelab.storage import canonical_hash
from _numerical_candidate_detail_support import DetailHost, synthetic_inputs, intermediate
from test_numerical_candidate_evidence_c1 import capture, complete
from caelab.numerical_candidate_evidence import resolve_candidate_evidence


def enriched_inputs():
    inputs=synthetic_inputs(retain=0)
    for exp in inputs['experiments']:
        obs=exp['observations']
        obs['sample_ids']=[exp['id']+'-sample-'+str(i) for i in range(4)]
        op={'operation_id':'ResampleObservedAndDriver','sha256':'b'*64}
        obs['operation_refs']=[op]
        obs['contributors']=[dict(sample_id=sample,
            # The same raw contributor deliberately occurs in fit AND holdout.
            # Legacy different integer source_rows cannot detect this leakage.
            raw_contributors=[dict(source_sha256='c'*64,source_column_identity=2,source_row=i,weight=.25),
                              dict(source_sha256='c'*64,source_column_identity=2,source_row=i+1,weight=.75)],
            operation_refs=[op]) for i,sample in enumerate(obs['sample_ids'])]
        obs['operation_metadata']={'schema':'test.c1.data-not-agreed.v0','payload':{
            'target_grid':[0.,1.,2.,3.], 'quality':[True,True,False,True],
            'gap':['measured','interpolated','excluded','measured'],
            'driver_sample_ids':obs['sample_ids'], 'plan_inclusion':exp['mask'],
            'role':exp['role'],'weight':exp['weight']}}
        obs['extensions']={'data.pending':{'schema':'test.future-packet.v0','payload':{
            'arbitrary_final_names':{'contributors':obs['contributors']},
            'stage_records':[{'operation_id':'ResampleObservedAndDriver','quality':'partial'}]}}}
        exp['extensions']={'data.protocol':{'schema':'test.protocol.v0','payload':{'hash':'d'*64}}}
    return inputs


def test_shared_strict_schema_accepts_lossless_typed_extensions():
    inputs=enriched_inputs()
    for experiment in inputs['experiments']:
        assert list(Draft202012Validator(_OBSERVATIONS).iter_errors(experiment['observations']))==[]
        assert list(Draft202012Validator(_EXPERIMENT).iter_errors(experiment))==[]
        validate_lineage_fields(experiment['observations'],count=4)
    before=canonical_hash(inputs)
    args=deepcopy(inputs);backend=args.pop('backend')
    packet=freeze_fit_input(backend,args,inputs)
    assert canonical_hash(inputs)==before
    for original,frozen in zip(inputs['experiments'],packet['inputs']['experiments']):
        for field in ('sample_ids','contributors','operation_refs','operation_metadata','extensions','source_rows'):
            assert frozen['observations'][field]==original['observations'][field]
        assert frozen['settings']==original['settings'] and frozen['extensions']==original['extensions']
        assert frozen['role']==original['role'] and frozen['weight']==original['weight']
    assessment=lineage_assessment(packet['inputs']['experiments'])
    assert assessment['status']=='PENDING_DATA_COMPILER_CONTRACT'
    assert assessment['derived_sample_independence']=='NOT_VERIFIED'
    assert not assessment['compiler_or_resampling_performed']


def test_enriched_actual_owner_fit_detail_save_preserves_carrier(tmp_path):
    inputs=enriched_inputs();before=canonical_hash(inputs)
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(inputs);cid=intermediate(host,doc,job)
        view=complete(host,doc,job,cid)
        ref=capture(host,view)['reference']
        saved=resolve_candidate_evidence(host.owner,ref,consumer='success_report')
        assert saved['readiness']['lineage']['derived_sample_independence']=='NOT_VERIFIED'
        for experiment in inputs['experiments']:
            rows=table_rows(view,experiment['id'])
            obs=experiment['observations']
            assert [r['sample_id'] for r in rows]==obs['sample_ids']
            assert [r['source_row'] for r in rows]==obs['source_rows']
            assert [r['contributors'] for r in rows]==obs['contributors']
            assert all(r['operation_metadata']==obs['operation_metadata'] for r in rows)
        assert canonical_hash(inputs)==before and len(host.manager.list())==2


@pytest.mark.parametrize('change', ['string_rows','id_count','id_order','nonfinite_weight','unknown_flat_field','malformed_packet'])
def test_reject_bad_carrier_without_rewriting_integer_rows(change):
    obs=enriched_inputs()['experiments'][0]['observations']
    if change=='string_rows': obs['source_rows']=obs['sample_ids']
    elif change=='id_count': obs['sample_ids']=obs['sample_ids'][:-1]
    elif change=='id_order': obs['contributors'].reverse()
    elif change=='nonfinite_weight': obs['contributors'][0]['raw_contributors'][0]['weight']=float('inf')
    elif change=='unknown_flat_field': obs['untyped_future_blob']={'x':1}
    elif change=='malformed_packet': obs['extensions']['data.pending']={'payload':{}}
    before=deepcopy(obs)
    if change=='unknown_flat_field':
        assert list(Draft202012Validator(_OBSERVATIONS).iter_errors(obs))
    else:
        with pytest.raises(ValueError): validate_lineage_fields(obs,count=4)
    assert obs==before


def test_data_root_injection_is_validate_only_no_invented_compiler_contract():
    experiments=enriched_inputs()['experiments'];before=canonical_hash(experiments)
    calls=[]
    retained=consume_data_extensions(experiments,lambda packet:calls.append(deepcopy(packet)))
    assert retained==experiments and calls==[experiments] and retained is not experiments
    with pytest.raises(TypeError): consume_data_extensions(experiments,None)
    def forbidden_rewrite(packet): packet[0]['observations']['source_rows'][0]=9999
    with pytest.raises(ValueError,match='not rewrite'): consume_data_extensions(experiments,forbidden_rewrite)
    with pytest.raises(ValueError): consume_data_extensions(experiments,lambda packet:{'status':'SUCCEEDED'})
    assert canonical_hash(experiments)==before
