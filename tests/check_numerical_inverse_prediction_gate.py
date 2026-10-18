"""Recheck the original retained-output fault injection; no model evaluation."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main(store,negative_path,folder):
    from examples.s1_windows_transfer import local_service
    from caelab.numerical import compare_curves,EvaluationFailed
    from caelab.storage import canonical_hash
    store=Path(store).resolve();folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=False)
    negative=json.loads(Path(negative_path).read_text(encoding='utf-8'))
    doc='Nfddaddc8b86b4d17b447f1af66ddc58a';job='Ja05c8a958ad94c31a0619ff1dcb0e0c9'
    def stamps():
        return {str(p.relative_to(store)):dict(bytes=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns,
            sha256=hashlib.sha256(p.read_bytes()).hexdigest())
            for name in ('documents','inputs','results') for p in (store/'workbench'/name).rglob('*')
            if p.is_file() and p.name!='working.json'}
    prior=stamps();calls=[]
    (folder/'before-stamps.json').write_text(json.dumps(prior,indent=2),encoding='utf-8')
    def forbidden(*args,**kwargs):calls.append('submit');raise AssertionError('Read-only gate check attempted calculation')
    with local_service(store) as (wb,client),ExitStack() as stack:
        for target in (wb,wb.manager):stack.enter_context(patch.object(target,'submit',forbidden))
        jobs_before={row['id'] for row in wb.manager.list()}
        owner_hash=canonical_hash(client.document_read(doc))
        result=client.document_result(doc,job);result_hash=canonical_hash(result)
        view=client.numerical_candidate_detail(doc,job,'C000015')
        prediction=deepcopy(view['trials'][0]['raw_evaluation']['responses']['stress_xx'])
        assert prediction=={key:value for key,value in negative['prediction'].items() if key!='mask'}
        valid=compare_curves(prediction,negative['observations'],weight=1,scale=1,mask=negative['fit_mask'])
        assert valid['objective']==negative['comparison']['objective']
        try:compare_curves(negative['prediction'],negative['observations'],weight=1,scale=1,mask=negative['fit_mask'])
        except EvaluationFailed as error:rejection=str(error)
        else:raise AssertionError('Required invalid prediction was scored')
        assert canonical_hash(client.document_result(doc,job))==result_hash
        assert canonical_hash(client.document_read(doc))==owner_hash
        assert {row['id'] for row in wb.manager.list()}==jobs_before and not calls
    after=stamps()
    (folder/'after-stamps.json').write_text(json.dumps(after,indent=2),encoding='utf-8')
    assert after==prior
    record=dict(document_id=doc,job_id=job,candidate_id='C000015',result_sha256=result_hash,
        prior_fault_outcome=negative['outcome'],current_fault_outcome='EvaluationFailed',reason=rejection,
        valid_unmodified_objective=valid['objective'],fixed_fit_mask=negative['fit_mask'],
        weight=valid['weight'],scale=valid['scale'],required_count=valid['count'],
        raw_input_result_document_bytes_and_mtimes_unchanged=True,files=prior,new_jobs=0,solve_fit_predict_submissions=0,
        owner_unchanged_during_reads=True,working_session_rebind='Existing owner session rebinding may persist working.json; immutable revisions/inputs/results are checked separately.',
        numerical_source_sha256=hashlib.sha256(Path('caelab/numerical.py').read_bytes()).hexdigest())
    (folder/'prediction-gate.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in record.items() if key!='files'},ensure_ascii=False),flush=True)


if __name__=='__main__':main(*sys.argv[1:])
