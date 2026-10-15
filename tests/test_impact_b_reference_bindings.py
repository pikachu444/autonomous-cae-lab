"""B selections reuse logical receipt/review/accept, not current integer existence."""
from copy import deepcopy

import pytest

from impact_b_fixtures import settings
from caelab.impact_model import model_from_settings,validate_settings
from caelab.impact_input_workflow import apply_text
from caelab.impact_input_edits import original_files
from caelab.impact_source import capture
from caelab.impact_reference_bindings import KEY,snapshot,validate,review,accept_review
from caelab.storage import canonical_hash


def test_material_assignment_source_edit_blocks_until_explicit_review(tmp_path):
    s=settings();validate_settings(s)
    # Both materials remain supported. Only the upper bulk assignment changes;
    # the selected lower bulk ID and its integer remain present and unchanged.
    raw=s['source']['text']
    extra='*MATERIAL,NAME=OTHER\n*DENSITY\n1e-9\n*ELASTIC\n1000,.3\n*PLASTIC\n100,0\n150,1\n'
    s['source']['text']=raw.replace('*MATERIAL,NAME=BOND',extra+'*MATERIAL,NAME=BOND')
    entry=tmp_path/'coupon.inp';entry.write_text(s['source']['text'],encoding='ascii')
    s['source']=capture(entry,tmp_path)
    file=next(iter(original_files(s['source'])))
    before=original_files(s['source'])[file]
    token=b'*SOLID SECTION,ELSET=UPPER,MATERIAL=BULK';offset=before.index(token)
    changed=apply_text(s,file=file,start=offset,end=offset+len(token),
        replacement='*SOLID SECTION,ELSET=UPPER,MATERIAL=OTHER',reason='UNIT change assigned members',
        expected_definition_sha256=canonical_hash(s))['settings']
    assert changed['b_responses']==s['b_responses']
    with pytest.raises(ValueError,match='대응이 바뀌'):validate_settings(changed)
    report=review(changed)
    bulk_before=next(r for r in report['before'] if r['selection']==['bulk_damage',0,'material'])
    bulk_after=next(r for r in report['after'] if r['selection']==['bulk_damage',0,'material'])
    assert len(bulk_before['source']['members'])==2 and len(bulk_after['source']['members'])==1
    with pytest.raises(ValueError):accept_review(changed,expected_definition_sha256=canonical_hash(changed),
        expected_review_sha256=report['review_sha256'],acknowledged=False)
    accepted=accept_review(changed,expected_definition_sha256=canonical_hash(changed),
        expected_review_sha256=report['review_sha256'],acknowledged=True)
    validate_settings(accepted)


@pytest.mark.parametrize('selection',[['b_responses',0,'identity'],['b_responses',3,'identity'],
                                    ['bulk_damage',0,'material'],['interface_controls',0,'material']])
def test_logical_instance_reuse_is_not_accepted_by_effective_number(selection):
    # Logical-entity unit boundary only: this does not claim native support for
    # B's bulk law on the current C3D4-only hierarchical input compiler.
    s=settings();model=model_from_settings(s)
    lineage=model.setdefault('lineage',{}).setdefault('elements',{})
    for eid in model['elements']:
        lineage[str(eid)]={'part':'COUPON','instance':'BODY-1','local_id':eid}
    s[KEY]=snapshot(s,model)
    current=deepcopy(model)
    eid=2 if selection in (['b_responses',3,'identity'],['interface_controls',0,'material']) else 1
    current['lineage']['elements'][str(eid)]['instance']='BODY-2'
    before=next(r for r in s[KEY]['rows'] if r['selection']==selection)
    after=next(r for r in snapshot(s,current)['rows'] if r['selection']==selection)
    assert before['value']==after['value'] and before['source']!=after['source']
    with pytest.raises(ValueError,match='대응이 바뀌'):validate(s,current)


def test_pair_identity_and_delayed_gate_bind_to_original_faces_not_list_index():
    s=settings();model=model_from_settings(s)
    s['contacts']=[{'a':'LOWER_TOP','b':'UPPER_BOTTOM'}]
    s['b_responses']=[{'name':'PAIR','scope':'pair','identity':0,'quantity':'force','component':'FNZ'}]
    s['interface_controls'][0]['contact_index']=0
    s[KEY]=snapshot(s,model)
    current=deepcopy(model);current['surfaces']['UPPER_BOTTOM']=[('1','S1')]
    for path in (['b_responses',0,'identity'],['interface_controls',0,'contact_index']):
        old=next(r for r in s[KEY]['rows'] if r['selection']==path)
        new=next(r for r in snapshot(s,current)['rows'] if r['selection']==path)
        assert old['value']==new['value']==0 and old['source']!=new['source']
    with pytest.raises(ValueError,match='대응이 바뀌'):validate(s,current)


def test_a_only_receipt_is_unchanged_and_incomplete_b_draft_stays_editable():
    s=settings()
    for key in ('b_responses','bulk_damage','interface_controls'):s.pop(key)
    original=snapshot(s);s[KEY]=deepcopy(original)
    assert snapshot(s)==original;validate(s,model_from_settings(s))
    draft=settings();draft['bulk_damage'][0]['evolution']['gf_n_mm']='1e'
    draft[KEY]=snapshot(draft)
    validate(draft,model_from_settings(draft))
    with pytest.raises(ValueError):validate_settings(draft)
