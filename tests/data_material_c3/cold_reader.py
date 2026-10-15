"""Separate-process capsule-only reader used by the narrow C3 acceptance test."""
from pathlib import Path
import json
import sys

from caelab.storage import load_json, canonical_hash
from caelab.evaluation import read_result, file_hash
from caelab.data_recovery_inputs import inspect_capsule, resolve_source, read_table_source
from caelab.material_test import deformation_plot_axis
from .support import plain


def main():
    capsule, expected_path=map(Path,sys.argv[1:3]);expected=load_json(expected_path)
    # Construction/mutation guards are deliberately active in the cold process.
    # No original owner, store, backend registration or solver is required.
    from caelab.material_document import MaterialDocuments
    from caelab.jobs import JobManager
    import caelab.storage
    import caelab.workbench
    def forbidden(*a,**k):raise AssertionError('Cold source reading must not construct an owner, write, or submit')
    MaterialDocuments.__init__=forbidden
    JobManager.submit=forbidden
    caelab.workbench.Workbench.__init__=forbidden
    caelab.storage.save_json=forbidden
    inspected=inspect_capsule(capsule,expected_capsule_sha256=expected['capsule_sha256'])
    c=inspected['capsule'];ack=c['acknowledged'];assets=capsule.with_suffix('.assets')
    assert c['identity']==expected['identity'] and ack['document_sha256']==expected['base_sha256']
    assert c['raw']['cells'][0]['raw_text']=='1e' and ack['document']['saved_revision'] is None
    for key,digest in expected['source_sha256'].items():
        source,receipt=resolve_source(capsule,key,expected_capsule_sha256=expected['capsule_sha256'])
        assert file_hash(source)==digest and canonical_hash(receipt)==expected['receipt_sha256'][key]
    # Each historical mapping reads its own original bytes, not the current C
    # source or the A source used by the retained processing result.
    checked=[]
    for draft_path, factor in [(['draft'],3), (['_undo',0],1), (['_undo',1],2), (['_redo',0],4), (['runs',0,'draft'],1)]:
        view=read_table_source(capsule,draft_path=draft_path,expected_capsule_sha256=expected['capsule_sha256'])
        assert view['table']['responses']['force']['value'].tolist()==[0.,20.*factor,40.*factor,60.*factor]
        checked.append(draft_path)
    table=read_table_source(capsule,draft_path=['runs',0,'draft'],expected_capsule_sha256=expected['capsule_sha256'])
    assert canonical_hash(plain(table['table']['responses']))==expected['imported_responses_sha256']
    job=next(j for j in ack['jobs'] if j['job_id']==expected['job_id'])
    imported=read_result(assets/job['result_path'],verify='all')
    assert canonical_hash(imported['responses'])==expected['imported_responses_sha256']
    processed=read_result(assets/'documents'/c['identity']['document_id']/'processing'/expected['processing_id'],verify='all')
    obs=processed['responses']['P11']
    assert canonical_hash(obs)==expected['processed_response_sha256']
    assert obs['source_rows']==expected['plan_observation_rows'] and obs['value']==expected['plan_observation_values']
    assert obs['unit']=='MPa' and obs['measure']=='first_Piola'
    assert processed['responses']['e']['value']==[0.,.01,.02,.03]
    assert processed['responses']['T_K']['value']==[293.15]*4
    assert obs['processing_channel']['lineage']
    assert deformation_plot_axis(obs,processed,expected['kinematics'])==expected['plot_axis']
    print(json.dumps({'verification':inspected['source_retention'],'inputs_verified':len(expected['source_sha256']),
        'historical_draft_paths_read':checked,
        'identity':c['identity'],'source_rows':obs['source_rows'],'nominal_stress_MPa':obs['value'],
        'engineering_strain':processed['responses']['e']['value'],
        'absolute_temperature_K':processed['responses']['T_K']['value'],
        'processed_response_sha256':canonical_hash(obs),'base_sha256':ack['document_sha256'],
        'owner_constructions':0,'jobs_submitted':0,'solver_execution':'NOT_PERFORMED',
        'resume_permission':inspected['resume_permission']},ensure_ascii=False))

if __name__=='__main__':main()
