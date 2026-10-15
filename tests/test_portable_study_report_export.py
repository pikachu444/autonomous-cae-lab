"""Actual Report owner/scope and headless export publication gate, NOT Qt/PDF."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from caelab.report_image import merge_read_assets
from examples.portable_study_expert_public import rows
from test_portable_study_expert import workspace, make_copy, policy
from apps.research.portable_research_report import (apply_read_assets, export_selection,
    read_export_sources, publish_checked)


def window(wb, document):
    messages=[]; visibility=[]
    w=SimpleNamespace(document=document,draft=deepcopy(document['draft']),assets={},_page=object(),_page_stale=False,
        _closed=False,message=SimpleNamespace(setText=messages.append),
        preview=SimpleNamespace(setVisible=visibility.append),messages=messages,visibility=visibility)
    def render():w._page=object();w._page_stale=False
    w.render=render
    return w


def test_scope_denial_never_merges_a_sensitive_preview_but_R1_image_damage_still_does():
    old={'Aold':{'id':'Aold','source_status':'AVAILABLE','content':{'kind':'knowledge','text':'SECRET'}}}
    deny={'id':'Aold','snapshot_status':'SCOPE_REQUIRED','source_status':'SOURCE_UNAVAILABLE'}
    assert merge_read_assets(old,[deny])['Aold']==deny
    assert 'SECRET' not in str(merge_read_assets(old,[deny]))
    missing={'id':'Aold','source_status':'SNAPSHOT_UNAVAILABLE','message':'pixels missing'}
    assert merge_read_assets(old,[missing])['Aold']['retained_preview_only'] is True
    assert old['Aold']['content']['text']=='SECRET'


def test_invalid_draft_on_denial_cannot_leave_old_print_preview_visible():
    w=window(None,{'id':'Bone','draft':{}})
    w.assets={'Aold':{'id':'Aold','content':{'text':'SECRET'}}}
    def failed_render():w._page_stale=True
    w.render=failed_render
    apply_read_assets(w,[{'id':'Aold','snapshot_status':'SCOPE_REQUIRED','source_status':'SOURCE_UNAVAILABLE'}])
    assert w._page is None and w.visibility==[False] and 'SECRET' not in str(w.assets)


@pytest.mark.parametrize('change',['none','revoke','scope','late_edit','stale_owner'])
def test_existing_report_owner_is_rechecked_before_output_and_old_file_preserved(tmp_path,change):
    case,receipt,target=make_copy(tmp_path)
    with workspace(target) as wb:
        doc=wb.document_read(rows(receipt)['report']);w=window(wb,doc)
        selection=export_selection(doc,w.draft)
        reviewed=read_export_sources(wb,selection)
        apply_read_assets(w,reviewed['assets'])
        destination=tmp_path/'기존 출력.txt';destination.write_text('KEEP OLD OUTPUT')
        if change=='revoke':policy(wb,case['source']['document_id'],revoked=True)
        elif change=='scope':policy(wb,case['source']['document_id'],access_scope=['other'])
        elif change=='late_edit':w.draft['title']='새 편집'
        elif change=='stale_owner':
            from examples.portable_study_expert_public import update
            draft=deepcopy(doc['draft']);draft['title']='다른 창의 편집';update(wb,doc,draft)
        if change=='stale_owner':
            with pytest.raises(ValueError,match='다른 창'):read_export_sources(wb,selection)
            assert destination.read_text()=='KEEP OLD OUTPUT'
            return
        current=read_export_sources(wb,selection)
        result=publish_checked(w,selection,reviewed,current,lambda:destination.write_text('CONTROLLED PUBLICATION, NOT PDF RENDERING'))
        assert result==(change=='none')
        if change!='none':assert destination.read_text()=='KEEP OLD OUTPUT'
        if change in {'revoke','scope'}:
            assert all('content' not in a for a in w.assets.values())
            assert w.draft==doc['draft']
        if change=='late_edit':assert w.draft['title']=='새 편집'


def test_same_id_current_content_collision_is_not_permission_to_export_archived_text(tmp_path):
    case,receipt,target=make_copy(tmp_path)
    with workspace(target) as wb:
        doc=wb.document_read(rows(receipt)['report']); w=window(wb,doc)
        selected=export_selection(doc,w.draft)
        reviewed=read_export_sources(wb,selected)
        apply_read_assets(w,reviewed['assets'])
        policy(wb,case['source']['document_id'],portable_revisions={})
        current=read_export_sources(wb,selected)
        writes=[]
        assert not publish_checked(w,selected,reviewed,current,lambda:writes.append('not allowed'))
        assert not writes and all('content' not in a for a in w.assets.values())
        assert current['assets'][0]['snapshot_status']=='SCOPE_REQUIRED'
