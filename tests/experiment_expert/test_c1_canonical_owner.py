"""Actual C2 policy/compiled trial/evidence -> FN05; synthetic P=mu*t only.

ServiceHost composes the existing Workbench methods and actual owners because
this public source allowlist omits native Pre constructor dependencies. The
policy, compiler, transport, optimizer, detail/evidence and persistence are not
mocked. No FELUPE, GUI, provider or native solver is executed.
"""
from copy import deepcopy
import numpy as np
import pytest

from caelab.backends import register_backend
from caelab.storage import canonical_hash
from caelab.numerical_candidate_evidence import CAPTURE, resolve_candidate_evidence
from caelab.experiment_analysis_service import selected_problem, final_request
from caelab.experiment_final_diagnosis import problem_from_evidence, read_jacobian
from .support import ServiceHost
from .test_file_workflow import capture
from ._c1_canonical_support import (
    BACKEND, SyntheticPoint, make_processed_plan, fit_and_detail)


def canonical_candidate(host, monkeypatch):
    from caelab import backends
    monkeypatch.setattr(backends, '_registry', dict(backends._registry))
    register_backend(BACKEND, SyntheticPoint, roles=('model',), replace=True)
    SyntheticPoint.calls=[]; SyntheticPoint.outcome='SUCCEEDED'
    bundle=make_processed_plan(host.core)
    receipt=host.owner._folder(bundle['plan']['id'])/'commands'/'Cactual_sample_policy.json'
    from caelab.storage import load_json
    frozen=load_json(receipt)['response']['document']['draft']
    assert frozen['experiments'][0]['selection']['sample_policy']['domain']==bundle['proposal']['domain']
    bundle=fit_and_detail(host.core,bundle)
    n=bundle['plan']['id']
    host.save(bundle['data']['id']);host.save(bundle['material']['id']);host.save(n)
    receipt=host.command(n,CAPTURE,{'source':bundle['view']['source'],
        'candidate_id':bundle['candidate_id'],'attempt_job_id':bundle['attempt']['id'],
        'purpose':'success_judgment'})
    return {**bundle,'reference':receipt['reference']}


def test_canonical_policy_owner_final_and_report(tmp_path,monkeypatch):
    with ServiceHost(tmp_path/'현재 한글 폴더') as h:
        b=canonical_candidate(h,monkeypatch)
        reference=b['reference']
        problem=selected_problem(h.core,reference)
        from caelab.experiment_analysis_actions import read_analysis_source
        from .test_actions import Client
        jobs=len(h.manager.list());calls=len(SyntheticPoint.calls)
        preview=read_analysis_source(Client(h),evidence_reference=reference)
        assert preview['problem']==problem and preview['performed_model_calls']==0
        assert len(h.manager.list())==jobs and len(SyntheticPoint.calls)==calls
        assert problem['lineage_status']=='CANONICAL_DATA_CONSUMER_CHECKED'
        assert problem['fit_input']['data_inclusion']['packet_sha256']==b['args']['frozen_inclusion']['packet_sha256']
        assert problem['fit_input']['inputs']['frozen_inclusion']==b['args']['frozen_inclusion']
        original=canonical_hash(h.owner.result(b['plan']['id'],b['fit_job']['id']))
        before=len(SyntheticPoint.calls)
        doc,job,result=h.run_plan(final_request(reference,evaluations=5))
        assert result['execution_status']=='SUCCEEDED',result.get('failure_reason')
        assert len(SyntheticPoint.calls)-before==5
        record=read_jacobian(result,problem)
        fit=next(e for e in problem['experiments'] if e['role']=='fit')
        mask=np.array(fit['mask'],dtype=bool)
        axis=np.array(fit['observations']['axes'][0]['values'])[mask]
        weights=np.array(fit['sample_weights'])[mask]
        expected=axis*np.sqrt(weights)*np.sqrt(fit['weight']/mask.sum())/fit['scale']
        assert np.allclose(np.array(record['matrix'])[:,0],expected,rtol=1e-8,atol=1e-9)
        assert [r['sample_weight'] for r in record['residual_rows']]==weights.tolist()
        assert canonical_hash(h.owner.result(b['plan']['id'],b['fit_job']['id']))==original
        assert record['evaluation_plan']['holdout_evaluations']==0
        h.save(doc);report,asset=capture(h,doc,job)
        content=h.core.report_content(report,[asset])['assets'][0]['content']['result']
        assert content['experiment_analysis']['source_problem']['fit_input']['data_inclusion']['packet_sha256']==b['args']['frozen_inclusion']['packet_sha256']
        # Canonical verification uses the original saved arguments and original
        # producer/retained consumers. No producer freeze is permitted on reads.
        import caelab.data_processing_selection as data_selection
        def no_freeze(*a,**k):pytest.fail('consumer tried to freeze a new packet')
        with monkeypatch.context() as m:
            m.setattr(data_selection,'freeze_fit_inclusion',no_freeze)
            resolved=resolve_candidate_evidence(h.owner,reference,consumer='read')
            submitted=next(run['arguments'] for run in h.owner.read(b['plan']['id'])['runs']
                if run['job_id']==b['fit_job']['id'])
            assert problem_from_evidence(resolved,submitted_arguments=submitted)==problem
            with pytest.raises(ValueError,match='실제 제출'):problem_from_evidence(resolved)
            changed=deepcopy(submitted);changed['experiments'][0]['weight']=19.
            with pytest.raises(ValueError):problem_from_evidence(resolved,submitted_arguments=changed)
            def corrupt(kind):
                bad=deepcopy(resolved);s=bad['snapshot'];f=s['fit_input'];i=f['inputs'];e=i['experiments'][0]
                if kind=='missing':i.pop('frozen_inclusion')
                elif kind=='alias':f['inclusion_packet']=i.pop('frozen_inclusion')
                elif kind=='assessment':f['data_inclusion']['packet_sha256']='a'*64
                elif kind=='mask':e['mask'][0]=False
                elif kind=='weight':e['sample_weights'][0]=3.
                elif kind=='settings':e['settings']['time'][0]=-.1
                elif kind=='sample':e['observations']['sample_ids'][0]='Pwrong'
                elif kind=='source':e['observation_source']['source_sha256']='b'*64
                elif kind=='header':e['frozen_fit_packet']['packet_sha256']='c'*64
                elif kind=='trial':e['frozen_fit_inclusion']['observation_sha256']='d'*64
                f['inputs_sha256']=canonical_hash(i)
                bad['reference']['snapshot_sha256']=canonical_hash(s)
                return bad
            # Direct-consumer fault injection keeps the fixture sealed only to
            # reach its semantic gate; no stored evidence/revision is changed.
            calls=len(SyntheticPoint.calls)
            for kind in ('missing','alias','assessment','mask','weight','settings','sample','source','header','trial'):
                with pytest.raises(ValueError):
                    problem_from_evidence(corrupt(kind),submitted_arguments=submitted)
            assert len(SyntheticPoint.calls)==calls
        from caelab.numerical_candidate_detail import read_candidate_detail
        original_view=read_candidate_detail(h.owner,b['plan']['id'],b['fit_job']['id'],b['candidate_id'])
        assert len(original_view['missing_experiments'])==2  # later attempt is not backfilled
        from caelab.experiment_analysis_reporting import study_draft
        draft=study_draft(result,h.core.document_result_reference(doc,job),
            question='다음 시험의 계수 민감도를 어떻게 구분할까?',
            selected_questions=['다른 하중 경로를 독립 검증용으로 유지할 수 있는가?'])
        study=h.study.open(draft=draft);h.save(study['id'])
        case={'reference':reference,'problem_hash':canonical_hash(problem),'plan':doc,'job':job,
            'jacobian_hash':record['sha256'],'report':report,'asset':asset,'report_hash':canonical_hash(content),
            'study':study['id'],'study_draft':draft,'source_plan':b['plan']['id'],
            'fit_job':b['fit_job']['id'],'original_hash':original}
        root=h.root
    import shutil,subprocess,sys,os,json
    from pathlib import Path
    shutil.rmtree(root/'inputs');shutil.rmtree(root/'results')
    # No assumption of C01 closure: the actual required source owners have been
    # saved explicitly above, as in the supplied public tiny chain.
    shutil.rmtree(root/'documents'/b['data']['id']/'processing')
    moved=root.parent/'이동한 시험 자료'
    root.rename(moved);case['root']=str(moved)
    case_file=tmp_path/'cold-case.json';case_file.write_text(json.dumps(case,ensure_ascii=False),encoding='utf-8')
    proc=subprocess.run([sys.executable,'-m','experiment_expert._c1_cold_read',str(case_file)],
        capture_output=True,text=True,timeout=180,env={**os.environ,'PYTHONHASHSEED':'19','OPENBLAS_NUM_THREADS':'1',
            'PYTHONPATH':os.pathsep.join([str(Path(__file__).resolve().parents[1]),
                str(Path(__file__).resolve().parents[2]),os.environ.get('PYTHONPATH','')])})
    assert proc.returncode==0,proc.stderr[-6000:]
    check=json.loads(proc.stdout.strip().splitlines()[-1])
    assert check['submissions']==check['model_calls']==0 and check['save_without_evaluation']
    print('FN05_C1_COLD='+proc.stdout.strip())
