"""Small GUI/CLI client helpers using existing owner commands and receipts.

No new owner/store; retry freezes the originally submitted payload and IDs.
Opening/reloading a result never constructs this write action or evaluates it.
"""
from copy import deepcopy
import uuid
from .numerical_document import request_draft


class ExplicitAnalysisAction:
    def __init__(self, request, action, *, source_reference, session_id, document=None):
        if action not in ('save', 'run'):
            raise ValueError('저장 또는 명시 실행을 선택하세요.')
        self.request=deepcopy(request);self.action=action
        self.source_reference=deepcopy(source_reference);self.session_id=session_id
        self.document=deepcopy(document)
        self.ids={stage:'C'+uuid.uuid4().hex for stage in ('create','update','finish')}
        self._updated=False;self._update_document=None;self._finish_document=None

    def perform(self,client):
        if self.document is None:
            self.document=client.result_followup(self.source_reference,'numerical',
                session_id=self.session_id,command_id=self.ids['create'],request=self.request)['document']
        if not self._updated:
            if self.document['draft'].get('request') != self.request:
                if self._update_document is None:self._update_document=deepcopy(self.document)
                d=self._update_document
                self.document=client.document_command(d['id'],'numerical.update',
                    {'draft':request_draft(self.request)},session_id=d['session_id'],
                    expected_generation=d['generation'],command_id=self.ids['update'])['document']
            self._updated=True
        # Freeze before finish. A lost reply must NOT acquire a later generation.
        if self._finish_document is None:self._finish_document=deepcopy(self.document)
        d=self._finish_document
        operation='document.save' if self.action=='save' else 'numerical.run'
        return client.document_command(d['id'],operation,{},session_id=d['session_id'],
            expected_generation=d['generation'],command_id=self.ids['finish'])


def save_analysis_study(client,pending):
    """Append the chosen question using the same exact result and retry receipts."""
    if 'document' not in pending:
        ref=client.document_result_reference(pending['source_document'],pending['source_job'])
        pending['reference']=deepcopy(ref)
        pending['document']=client.result_followup(ref,'study',session_id=pending['source_session'],command_id=pending['create'])['document']
    if 'update_snapshot' not in pending:
        d=client.document_read(pending['document']['id']);draft=deepcopy(d['draft'])
        if isinstance(draft.get('question'),str) and not draft['question'].strip():draft['question']=pending['question']
        evidence=next((row for row in draft['evidence'] if all(
            row.get('reference',{}).get(key)==value for key,value in pending['reference'].items())),None)
        if evidence is None:
            evidence={'id':'E'+uuid.uuid4().hex,'kind':'result','label':'보존한 시험 분석',
                'reference':{'kind':'result',**deepcopy(pending['reference'])},'note':''}
            draft['evidence'].append(evidence)
        draft['next_observations'].append({'id':pending['observation_id'],'question':pending['question'],
            'hypothesis_ids':[],'evidence_ids':[evidence['id']],'status':'PLANNED',
            'note':'사용자가 선택한 다음 시험 질문; 새 계산 없음'+('\n'+pending['note'] if pending.get('note') else '')})
        pending['update_snapshot']=(d,draft)
    if 'updated' not in pending:
        d,draft=pending['update_snapshot']
        receipt=client.document_command(d['id'],'study.update',{'draft':draft},session_id=d['session_id'],expected_generation=d['generation'],command_id=pending['update'])
        pending['updated']=receipt['document']
    updated=pending['updated']
    return client.document_command(updated['id'],'document.save',{},session_id=updated['session_id'],expected_generation=updated['generation'],command_id=pending['save'])


def read_analysis_source(client, *, source=None, evidence_reference=None, plan_mask=None,
                         relative_step=1e-4, reuse_result=None):
    """Preview original values/cost without creating a Plan or executing models."""
    from .storage import canonical_hash
    from .experiment_uncertainty import calibration_problem,plain
    from .experiment_final_diagnosis import problem_from_evidence,evaluation_plan,_admission,read_jacobian
    if (source is None)==(evidence_reference is None):
        raise ValueError('보존한 시험 응답 또는 최종 후보 근거 하나를 선택하세요.')
    if source is not None:
        if source.get('kind')=='processing_channel':
            # Reuse the exact public Data C1 read endpoint; do not add an HTTP
            # route or reimplement its owner publication/retained assets.
            from .experiment_uncertainty import processing_problem
            d=client.document_read(source['document_id'])
            r=client.request('/api/workbench/data-material',{'operation':'data.processing.result',
                'arguments':{'document_id':source['document_id'],'processing_revision':source['revision']}})
            channel=plain(r['channels'][source['channel']])
            if canonical_hash(channel)!=source['channel_sha256']:
                raise ValueError('선택한 보존 처리 채널이 달라졌습니다.')
            origin=r['diagnostics']['processing_record']['source']
            ref=client.document_result_reference(origin['document_id'],origin['job_id'])
            if any(ref[k]!=origin[k] for k in ('document_id','job_id','input_revision','input_sha256')):
                raise ValueError('처리 개정의 원 시험 입력과 명시 Plan 출처가 다릅니다.')
            problem=processing_problem(channel,plan_mask=plan_mask)
            problem['processing_record']=deepcopy(r['diagnostics']['processing_record'])
        elif source.get('kind')=='observation_chain':
            from .experiment_observation_uncertainty import read_problem
            problem=read_problem(client,source,plan_mask=plan_mask)
            ref=problem['operand_references'].get('A')
            if ref is None:ref=read_analysis_source(client,source=source['base'],plan_mask=plan_mask)['source_reference']
            d=client.document_read(ref['document_id'])
        elif source.get('kind')=='retained_comparison':
            from .experiment_comparison_uncertainty import read_problem
            problem=read_problem(client,source['reference'],plan_mask=plan_mask)
            ref=problem['operand_references']['A'];d=client.document_read(ref['document_id'])
        elif source.get('kind')=='result_response':
            ref=source['reference'];d=client.document_read(ref['document_id'])
            r=client.document_result(ref['document_id'],ref['job_id'])
            actual=client.document_result_reference(ref['document_id'],ref['job_id'])
            if actual!=ref or canonical_hash(r)!=ref['result_sha256']:
                raise ValueError('선택한 원 시험 입력/결과가 달라졌습니다.')
            problem=calibration_problem(r['responses'][source['response']],plan_mask=plan_mask)
        else:
            raise ValueError('원 시험 응답 또는 Data owner가 보존한 처리 개정을 선택하세요.')
        problem['source']=deepcopy(source);cost=0
    else:
        ref=evidence_reference['source'];d=client.document_read(evidence_reference['document_id'])
        from .numerical_candidate_evidence import READ
        receipt=client.document_command(d['id'],READ,{'reference':evidence_reference,'consumer':'read'},
            session_id=d['session_id'],expected_generation=d['generation'])
        supplied={}
        if receipt['evidence']['snapshot']['fit_input']['inputs'].get('frozen_inclusion') is not None:
            from types import SimpleNamespace
            from .portable_project_execution import execution_read
            from .numerical_candidate_detail import _source
            owner=SimpleNamespace(read=client.document_read,result=client.document_result,_portable_client_read=True)
            bridge=execution_read(owner,d['id'],ref['job_id'])
            expected=receipt['evidence']['snapshot']['source']
            if bridge is not None:
                if bridge.source!=ref or bridge.execution_source!=expected:
                    raise ValueError('선택한 후보와 이동 사본의 원 실행이 다릅니다. 원 결과를 다시 확인하세요.')
                owner=bridge.reader;identifier=bridge.execution_source['document_id']
            else:identifier=d['id']
            _,run,_,_=_source(owner,identifier,ref['job_id'],expected)
            supplied['submitted_arguments']=run['arguments']
        problem=problem_from_evidence(receipt['evidence'],**supplied)
        reason=_admission(problem)
        if reason:
            cost=0
        elif reuse_result:
            from .research_operations import _resolve
            retained=_resolve(reuse_result,client.document_read,client.document_result)
            read_jacobian(retained,problem)
            cost=0
        else:
            cost=evaluation_plan(problem,relative_step)['model_evaluations']
        keys=('document_id','job_id','input_revision','input_sha256','result_sha256')
        ref={k:ref[k] for k in keys}
    from .linear_adjoint_contract import describe_methods
    diagnostic=({'available':not reason,'reasons':[reason] if reason else [],'cost':cost}
                if evidence_reference is not None else None)
    return {'problem':problem,'source_reference':deepcopy(ref),'session_id':d['session_id'],
            'model_evaluations':cost,'performed_model_calls':0,'derivative_methods':describe_methods(diagnostic=diagnostic)}


def source_request_identity(request):
    """Identity of the measurement/candidate underlying the input editor.

    Editing uncertainty values or a budget does not change the underlying data,
    but switching a source, Plan mask or selected candidate does. An old saved
    result must not supply input rows for a different current draft.
    """
    inputs=request.get('inputs',{})
    if request.get('operation')=='experiment_uncertainty':
        return deepcopy({'operation':request['operation'],'source':inputs.get('source'),
                         'plan_mask':inputs.get('plan_mask')})
    if request.get('operation')=='identification_final':
        return deepcopy({'operation':request['operation'],'evidence_reference':inputs.get('evidence_reference')})
    raise ValueError('시험 분석 Plan이 아닙니다.')
