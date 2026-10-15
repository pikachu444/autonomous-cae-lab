"""Fresh interpreter acceptance of saved canonical evidence/results; no submit.
Invoked by the owner-chain test, not an evaluator or a new service.
"""
import json
import sys
from pathlib import Path
from caelab.storage import canonical_hash
from caelab.experiment_analysis_service import selected_problem
from caelab.experiment_final_diagnosis import read_jacobian
from .support import ServiceHost


def main(path):
    case=json.loads(Path(path).read_text(encoding='utf-8'))
    with ServiceHost(case['root']) as h:
        def forbidden(*args,**kwargs):
            raise AssertionError('read/save/reopen submitted a new model/job')
        h.manager.submit=forbidden
        h.core.submit=forbidden
        for owner in h.core.research_owners():owner.submit=forbidden
        # The synthetic backend is deliberately NOT registered in this process.
        # Every value must come from the retained original input/result/evidence.
        before=len(h.manager.list())
        p=selected_problem(h.core,case['reference'])
        assert canonical_hash(p)==case['problem_hash']
        from caelab.experiment_analysis_actions import read_analysis_source
        from .test_actions import Client
        preview=read_analysis_source(Client(h),evidence_reference=case['reference'])
        assert preview['problem']==p and preview['performed_model_calls']==0
        r=h.owner.result(case['plan'],case['job'])
        J=read_jacobian(r,p)
        assert J['sha256']==case['jacobian_hash']
        contents=h.core.report_content(case['report'],[case['asset']])['assets'][0]['content']['result']
        assert canonical_hash(contents)==case['report_hash']
        assert h.study.read(case['study'])['draft']==case['study_draft']
        assert canonical_hash(h.owner.result(case['source_plan'],case['fit_job']))==case['original_hash']
        h.save(case['plan']);h.save(case['report']);h.save(case['study'])
        assert canonical_hash(h.owner.result(case['plan'],case['job']))==canonical_hash(r)
        assert len(h.manager.list())==before
    print(json.dumps({'cold_process':True,'model_calls':0,'submissions':0,
        'canonical_read':True,'ordinary_J_read':True,'report_read':True,'study_read':True,'save_without_evaluation':True}))


if __name__=='__main__':main(sys.argv[1])
