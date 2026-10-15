"""User-supplied Codex counterexample; original Pro files remain immutable."""
from copy import deepcopy
import pytest
from _numerical_candidate_detail_support import DetailHost, synthetic_inputs, intermediate
from test_numerical_candidate_evidence_c1 import complete
from caelab.numerical_candidate_evidence import CAPTURE, SUCCESS


def test_preserving_retry_must_not_save_a_newer_unreviewed_plan(tmp_path,monkeypatch):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0));cid=intermediate(host,doc,job)
        view=complete(host,doc,job,cid)
        document=host.owner.read(doc)
        args=dict(source=view['source'],candidate_id=cid,attempt_job_id=view['attempt_job_id'],purpose=SUCCESS)
        identity=dict(session_id=document['session_id'],expected_generation=document['generation'],command_id='CstalePreserving')
        original_save=host.owner._save
        monkeypatch.setattr(host.owner,'_save',lambda value:(_ for _ in ()).throw(OSError('injected disk failure')))
        with pytest.raises(OSError):host.owner.command(doc,CAPTURE,args,**identity)
        monkeypatch.setattr(host.owner,'_save',original_save)
        current=host.owner.read(doc);changed=deepcopy(current['draft'])
        changed['request']['purpose']='다른 창에서 바꾼 아직 저장하지 않은 계획'
        host.command(doc,'numerical.update',{'draft':changed})
        before=host.owner.read(doc)
        assert before['generation']>identity['expected_generation']+1 and before['dirty']
        try:
            result=host.owner.command(doc,CAPTURE,args,**identity)
        except ValueError:
            return
        after=host.owner.read(doc)
        raise AssertionError('Stale PRESERVING retry unexpectedly saved newer draft: '+repr({
            'old_generation':identity['expected_generation'],'peer_generation':before['generation'],
            'saved_revision':after['saved_revision'],'dirty_before':before['dirty'],'dirty_after':after['dirty'],
            'purpose':after['draft']['request']['purpose'],'returned_ref':result['reference']}))
