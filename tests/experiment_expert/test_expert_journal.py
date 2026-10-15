"""Actual FN30 core with explicit provider/prompt/search doubles; no account calls."""
from copy import deepcopy
import threading
import pytest
from caelab.storage import canonical_hash
from caelab.expert_journal_inspection import read_journal,inspect_journal
from .support import ServiceHost
from .costorm_support import scripted,selected_search,configuration,discussion,execute


def test_partial_save_cold_read_current_budget_retry_and_unsent_intervention(tmp_path,scripted,selected_search):
    config=configuration()
    with ServiceHost(tmp_path/'wb',configuration=config) as h:
        d,source=discussion(h,2);doc=d['id']
        job,r=execute(h,doc,'expert.ask')
        assert r['status']=='STOPPED',r
        assert len(scripted)==2 and len(r['costorm']['retry']['journal'])==2
        assert not r['costorm']['view']['turns']
        partial=read_journal(h.expert,doc,job,limit=1)
        assert partial['next_offset']==1 and partial['rows'][0]['adopted_utterance'] is False
        assert partial['stop_state']=='ACTION_STOPPED'
        h.save(doc);digest=canonical_hash(h.expert.result(doc,job));before=len(scripted)
    with ServiceHost(tmp_path/'wb',configuration=config) as cold:
        # Same ORIGINAL job remains readable through the real owner after restart.
        for _ in range(3):
            view=read_journal(cold.expert,doc,job)
            assert view['total']==2 and not view['committed_turns']
            cold.save(doc)
        assert len(scripted)==before
        d=cold.expert.read(doc);draft=deepcopy(d['draft'])
        draft['budget']['model_calls']=1
        draft['composer']['text']='UNSENT new area opinion'
        cold.command(doc,'expert.update',{'draft':draft})
        job2,r2=execute(cold,doc,'expert.retry')
        assert r2['status']=='STOPPED' and r2['costorm']['usage']['model_calls']==1
        assert r2['costorm']['usage']['replayed_completions']>=2
        assert all('UNSENT new area opinion' not in p for p in scripted)
        assert cold.expert.read(doc)['draft']['composer']['text']=='UNSENT new area opinion'
        draft=deepcopy(cold.expert.read(doc)['draft']);draft['budget']['model_calls']=100
        cold.command(doc,'expert.update',{'draft':draft})
        _,completed=execute(cold,doc,'expert.retry')
        assert completed['status']=='ANSWERED',completed
        assert completed['costorm']['usage']['replayed_completions']>=3
        assert canonical_hash(cold.expert.result(doc,job))==digest
        assert read_journal(cold.expert,doc,job)['total']==2
        # Only explicit intervene sends the preserved composer. Then advance consumes it.
        intervention=cold.command(doc,'expert.intervene')['document']
        n=len(scripted)
        _,following=execute(cold,doc,'expert.advance')
        assert following['status']=='ANSWERED',following
        assert any('UNSENT new area opinion' in p for p in scripted[n:])
        assert following['costorm']['consumed_user_ids']


def test_revoked_source_blocks_retry_without_calls_or_losing_partial(tmp_path,scripted,selected_search):
    with ServiceHost(tmp_path,configuration=configuration()) as h:
        d,source=discussion(h);doc=d['id'];job,r=execute(h,doc,'expert.ask')
        h.save(doc);before=len(scripted)
        h.core.assistance().knowledge.revoke(source['document_id'])
        with pytest.raises(PermissionError):h.command(doc,'expert.retry')
        assert len(scripted)==before
        assert read_journal(h.expert,doc,job)['total']==2


def test_changed_selected_revision_blocks_replay(tmp_path,scripted,selected_search):
    with ServiceHost(tmp_path,configuration=configuration()) as h:
        d,source=discussion(h);doc=d['id'];job,r=execute(h,doc,'expert.ask')
        p=h.root/'alpha.md';p.write_text('Changed source revision',encoding='utf-8')
        new=h.core.assistance().knowledge.ingest(str(p),collection='research',document_id=source['document_id'])
        draft=deepcopy(h.expert.read(doc)['draft']);draft['context']['selected_sources'][0]['revision']=new['revision']
        h.command(doc,'expert.update',{'draft':draft});before=len(scripted)
        with pytest.raises(ValueError,match='자료'):h.command(doc,'expert.retry')
        assert len(scripted)==before and read_journal(h.expert,doc,job)['total']==2


def test_malformed_completion_is_retained_but_excluded_on_retry(tmp_path,scripted,selected_search,monkeypatch):
    import caelab.assist.openscience_host as host
    original=host.run_openscience;broken={'once':True}
    def malformed(*a,**k):
        text=original(*a,**k)
        if broken['once']:
            broken['once']=False
            return 'malformed JSON completion'
        return text
    monkeypatch.setattr(host,'run_openscience',malformed)
    with ServiceHost(tmp_path,configuration=configuration()) as h:
        d,_=discussion(h,100);doc=d['id'];job,r=execute(h,doc,'expert.ask')
        assert r['status']=='STOPPED',r
        assert r['costorm']['retry']['invalid_completion_key']
        view=read_journal(h.expert,doc,job)
        assert view['rows'][0]['state']=='INVALID_COMPLETION_EXCLUDED'
        _,r2=execute(h,doc,'expert.retry')
        assert r2['status']=='ANSWERED',r2
        bad_prompt=r['costorm']['retry']['journal'][0]['prompt']
        assert scripted.count(bad_prompt)==2  # rejected completion actually requested again
        # Repeated equal valid prompts WITHIN this action can also hit the cache.
        assert read_journal(h.expert,doc,job)['rows'][0]['text']=='malformed JSON completion'


def test_cancel_request_not_confirmation_and_returned_text_not_adopted(tmp_path,scripted,selected_search,monkeypatch):
    import caelab.assist.openscience_host as host
    original=host.run_openscience;entered=threading.Event();release=threading.Event()
    def blocked(*a,**k):
        text=original(*a,**k);entered.set();assert release.wait(5);return text
    monkeypatch.setattr(host,'run_openscience',blocked)
    with ServiceHost(tmp_path,configuration=configuration()) as h:
        d,_=discussion(h,100);doc=d['id'];receipt=h.command(doc,'expert.ask');job=receipt['job']['id']
        assert entered.wait(5)
        try:
            h.manager.cancel(job)
            assert h.manager.status(job)['state'] not in {'SUCCEEDED','CANCELLED'}
        finally:release.set()
        h.wait(job);h.expert.read(doc);r=h.expert.result(doc,job)
        assert r['status']=='STOPPED' and r['execution_status']=='CANCELLED',r
        view=read_journal(h.expert,doc,job)
        assert view['total']==1 and not view['committed_turns']
        assert view['stop_state']=='CANCEL_CONFIRMED'
        assert not view['rows'][0]['adopted_utterance']
        assert inspect_journal({**r,'execution_status':'PARTIAL_FAILURE'},document_id=doc,job_id=job,
            cancel_requested=True)['stop_state']=='CANCEL_REQUESTED'


def test_resumed_discussion_explicit_calculation_return_report_and_cold_reopen(tmp_path,scripted,selected_search):
    from .test_file_workflow import import_source
    from .test_uncertainty import spec
    from caelab.experiment_analysis_service import source_problem,uncertainty_request
    with ServiceHost(tmp_path/'wb',configuration=configuration()) as h:
        d,_=discussion(h,2);doc=d['id'];first,partial=execute(h,doc,'expert.ask')
        draft=deepcopy(h.expert.read(doc)['draft']);draft['budget']['model_calls']=100
        h.command(doc,'expert.update',{'draft':draft});_,resumed=execute(h,doc,'expert.retry')
        assert resumed['status']=='ANSWERED'
        # A real explicit analytic calculation is attached by the user; neither
        # partial reading nor this attachment starts another calculation/model.
        _,_,source=import_source(h);p=source_problem(h.core,{'source':source})
        plan,job,calculated=h.run_plan(uncertainty_request(source,spec(p)));h.save(plan)
        ref=h.core.document_result_reference(plan,job)
        evidence={k:ref[k] for k in ('document_id','job_id','input_revision','input_sha256')}
        evidence['selection']=[]
        draft=deepcopy(h.expert.read(doc)['draft']);draft['composer'].update(text='검토한 전파 결과를 반영하세요.',evidence=[evidence])
        before=len(scripted);h.command(doc,'expert.update',{'draft':draft});h.command(doc,'expert.intervene')
        assert len(scripted)==before
        _,advanced=execute(h,doc,'expert.advance');assert advanced['status']=='ANSWERED',advanced
        # A moderator's next question need not retrieve evidence. Further steps
        # are explicit owner commands, never polling-driven model calls.
        for _ in range(3):
            if any('experiment_uncertainty' in p and 'SUPPLIED_INPUTS_ONLY' in p for p in scripted[before:]):break
            _,advanced=execute(h,doc,'expert.advance');assert advanced['status']=='ANSWERED',advanced
        assert any('experiment_uncertainty' in p and 'SUPPLIED_INPUTS_ONLY' in p for p in scripted[before:])
        _,report=execute(h,doc,'expert.report');assert report['status']=='ANSWERED',report
        h.save(doc);frozen=deepcopy(h.expert.read(doc)['discussion']['costorm']['report'])
        assert frozen['references'];count=len(scripted)
        assert canonical_hash(h.expert.result(doc,first))==canonical_hash(partial)
    with ServiceHost(tmp_path/'wb',configuration=configuration()) as cold:
        assert cold.expert.read(doc)['discussion']['costorm']['report']==frozen
        assert read_journal(cold.expert,doc,first)['total']==2
        cold.save(doc);assert len(scripted)==count


def test_role_permission_revoked_after_partial_blocks_all_journal_replay(tmp_path,scripted,selected_search):
    with ServiceHost(tmp_path,configuration=configuration()) as h:
        d,_=discussion(h);doc=d['id'];job,raw=execute(h,doc,'expert.ask');before=len(scripted)
        h.core.assistance().experts.definitions['mechanics']['tools']=[]
        receipt=h.command(doc,'expert.retry');h.wait(receipt['job']['id'])
        assert h.manager.status(receipt['job']['id'])['state']=='FAILED'
        assert len(scripted)==before
        assert read_journal(h.expert,doc,job)['total']==2
