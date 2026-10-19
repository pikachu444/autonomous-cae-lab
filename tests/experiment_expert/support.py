"""Public fixture: real owner/revisions/JobManager/Workbench dispatch.

Only full Workbench construction (native Pre files absent from request ZIP) and
original fit-data production are composed here. Use the current Numerical owner
with its existing CandidateDetailMixin and evidence publication hooks unchanged.
"""
from copy import deepcopy
from pathlib import Path
import threading
import uuid

from caelab.workbench import Workbench
from caelab.jobs import JobManager, TERMINAL
from caelab.storage import canonical_hash, load_json
from caelab.material_document import MaterialDocuments
from caelab.numerical_document import NumericalDocuments, request_draft
from caelab.data_document import DataDocuments
from caelab.study_document import StudyDocuments
from caelab.report_document import ReportDocuments
from caelab.discussion_document import DiscussionDocuments
from caelab.numerical_candidate_detail import freeze_fit_input, trial_detail, SCHEMA, read_candidate_detail
from caelab.numerical_candidate_evidence import CAPTURE
from caelab.research_workflows import reference_metadata
from caelab.experiment_uncertainty import plain
from caelab.experiment_analysis_service import OPERATIONS

class ServiceHost:
    def __init__(self,root,*,configuration=None,data_owner_type=DataDocuments):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        w=self.core=Workbench.__new__(Workbench)
        w.workspace=self.root.parent;w.root=self.root;w.config=deepcopy(configuration or {});w.workspace_id='local'
        w._portable_manifest=None
        w.session_id='S'+uuid.uuid4().hex
        w._assist_config_lock=threading.RLock();w._assistance=None;w._assistance_active=0;w._assistance_cleanup_pending=False
        self.original_fixture=None
        self.manager=w.manager=JobManager(self.root,self._execute,workers=1,cpu_budget=2)
        w.native_commands=object() # never called; no simulated native implementation
        self.owner=w.numerical_documents=NumericalDocuments(self.root,w.session_id,w.submit,self.manager,
            resolve_document=w.document_read,resolve_result=w.document_result,prepare_request=w._request_plan_arguments)
        self.data=w.data_documents=data_owner_type(self.root,w.session_id,w.submit,self.manager,
            resolve_input=lambda i:(w.input_path(i),load_json(w.root/'inputs'/i/'input.json')))
        w.material_documents=MaterialDocuments(self.root,w.session_id,w.submit,self.manager)
        self.study=w.study_documents=StudyDocuments(self.root,w.session_id,w.submit,self.manager,
            resolve_reference=lambda ref:reference_metadata(w,ref))
        self.reports=w.report_documents=ReportDocuments(self.root,w.session_id,w.submit,self.manager,resolve_reference=w.research_reference)
        self.expert=w.discussion_documents=DiscussionDocuments(self.root,w.session_id,w.submit,self.manager,
            list_experts=lambda:w.assistance_call('experts.list',{}),resolve_document=w.document_read,
            resolve_result=w.document_result,resolve_knowledge=lambda ref:w.assistance_call('knowledge.source',ref))
        w.research_owners=lambda:(w.material_documents,self.data,self.owner,self.study,self.reports,self.expert)
        from caelab.desktop_links import DesktopLinks
        w.desktop=DesktopLinks(w)

    def _execute(self,op,args,job):
        if op=='fit' and self.original_fixture:
            return deepcopy(self.original_fixture)
        return self.core._execute(op,args,job)

    def command(self,doc,op,args=None,**kwargs):
        d=self.core.document_read(doc)
        return self.core.document_command(doc,op,args or {},session_id=d['session_id'],expected_generation=d['generation'],**kwargs)

    def wait(self,job):
        # Wait for the existing exact future rather than repeatedly deepcopying
        # a canonical multi-MiB input while its worker needs the GIL. This is a
        # test wait, not a changed product timeout or numerical tolerance.
        self.manager._futures[job].result(timeout=180)
        result=self.manager.status(job)
        assert result['state'] in TERMINAL, (result['state'],result.get('error'))
        return result

    def save(self,doc):
        return self.command(doc,'document.save')['document']

    def run_plan(self,request):
        d=self.owner.open(title='명시 시험 분석',draft=request_draft(request))
        assert not d['diagnostics'],d['diagnostics']
        receipt=self.command(d['id'],'numerical.run')
        job=receipt['job']['id'];status=self.wait(job)
        assert status['result_refs'],status
        return d['id'],job,self.owner.result(d['id'],job)

    def original(self,problem,*,backend='public.algebra',binding=True,raws=None,failed=False):
        """Seed a labeled PUBLIC fixture using REAL C1 format/owner save/capture.
        This is not an original GUI optimization or a CAS correction test.
        """
        from caelab.numerical_candidate_detail import backend_binding
        variables=problem['variables'];experiments=problem['experiments'];candidate=deepcopy(problem['candidate'])
        inputs={'backend':backend,'variables':deepcopy(variables),'experiments':deepcopy(experiments),
            'method':problem['optimizer_method'],'options':{'loss':problem['optimizer_loss']}}
        if failed:candidate['execution_status']='FAILED'
        trials=deepcopy(problem['selected_trials'])
        if raws is not None:
            trials=[trial_detail(e,raw,origin={'kind':'fit_final','candidate_id':candidate['candidate_id']}) for e,raw in zip(experiments,raws)]
        candidate['candidate_detail']={'schema':SCHEMA,'candidate_id':candidate['candidate_id'],
            'values_sha256':canonical_hash(candidate['values']), 'trials':trials, 'retention':'RETAINED'}
        submitted=deepcopy(inputs)
        frozen=freeze_fit_input(backend,{k:v for k,v in inputs.items() if k!='backend'},submitted,
                              evaluator_binding=backend_binding(self.core,backend) if binding else None)
        output={'kind':'fit','execution_status':'FAILED' if failed else 'SUCCEEDED','responses':{},'checks':[],
            'variables':deepcopy(variables),'candidates':[candidate],'parameters':deepcopy(candidate['values']),
            'curves':[],'fit_input_snapshot':frozen,'diagnostics':{'fixture':'seeded C1 record; not original optimizer execution'}}
        self.original_fixture=plain(output)
        d=self.owner.open(title='보존된 공개 후보',draft=request_draft({'purpose':'공개 원 후보 fixture','operation':'fit',
            'inputs':inputs,'budget':{'evaluations':100}}))
        job=self.manager.submit('fit',submitted)
        self.wait(job['id'])
        working=self.owner._documents[d['id']]
        working['runs'].append(self.owner._run_record(job,working['draft'],working['generation'],working['input_revision'],self.owner.session_id))
        self.owner._persist_draft(working)
        self.original_fixture=None
        self.save(d['id'])
        view=read_candidate_detail(self.owner,d['id'],job['id'],candidate['candidate_id'])
        receipt=self.command(d['id'],CAPTURE,{'source':view['source'],'candidate_id':candidate['candidate_id'],
            'attempt_job_id':None,'purpose':'failure_diagnostic' if failed else 'success_judgment'})
        return d['id'],job['id'],receipt['reference']

    def close(self):
        result=self.manager.shutdown()
        assert result['joined'],result
    def __enter__(self):return self
    def __exit__(self,*a):self.close()
