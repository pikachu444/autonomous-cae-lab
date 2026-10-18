"""An inspection reuses only its verified immutable result, with detached reads."""
from copy import deepcopy

import pytest

from caelab.numerical_candidate_detail import _source,DetailIdentityError
from caelab.numerical_candidate_evidence import _saved_owner
from caelab.storage import revision_read_scope
from .support import ServiceHost
from .test_final_diagnosis import direct_problem
from .test_service import algebra_registered


def test_same_retained_source_is_detached_and_checks_each_request(tmp_path,algebra_registered):
    with ServiceHost(tmp_path) as host:
        doc,job,reference=host.original(direct_problem())
        _,facet=_saved_owner(host.owner,doc,reference['saved_revision'])
        expected=reference['source'];calls=[];read_result=facet.result
        def counted(*args,**kwargs):
            calls.append(args)
            return read_result(*args,**kwargs)
        facet.result=counted
        with revision_read_scope():
            first=_source(facet,doc,job,expected)
            first[2]['candidates'][0]['values']['x']=-123.
            second=_source(facet,doc,job,expected)
            assert second[2]['candidates'][0]['values']['x']!=-123.
            assert len(calls)==1
            bad=deepcopy(expected);bad['result_sha256']='a'*64
            with pytest.raises(DetailIdentityError,match='Stale result'):_source(facet,doc,job,bad)
            original_read=facet.read
            changed=original_read(doc);changed['runs'][0]['input_sha256']='b'*64
            facet.read=lambda identifier:deepcopy(changed)
            with pytest.raises(DetailIdentityError,match='submitted Plan'):_source(facet,doc,job,expected)
            facet.read=original_read
        with revision_read_scope():_source(facet,doc,job,expected)
        assert len(calls)==2
