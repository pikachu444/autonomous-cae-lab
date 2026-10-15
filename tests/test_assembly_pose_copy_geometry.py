"""M4 private-copy fingerprint/legacy gate; native objects are explicit doubles.

Actual editable Boolean copy/full-geometry evidence is the native curved jig.
These checks preserve source identity and fail closed after a recorded copy edit.
"""
from copy import deepcopy
import pytest
from test_assembly_pose_admission import ready
from apps.desktop_pre.assembly_pose_candidate import KEY,validate_model


def test_private_recompute_representation_change_keeps_full_geometry_and_source(tmp_path,monkeypatch):
    """A representation-only double exercises the previously rejecting branch.

    Native Boolean equivalence is checked separately; this does not substitute
    a synthetic box for the native curved/Boolean acceptance specimen.
    """
    from assembly_pose_doubles import source_fixture,Document,Shape,Owner
    from test_assembly_pose_candidate import run_preparation
    from apps.desktop_pre.assembly_pose_geometry import _local_digest
    original,root,_=source_fixture(tmp_path,monkeypatch)
    before=deepcopy(original.read_metadata())
    recompute,brep,read_brep=Document.recompute,Shape.exportBrepToString,Shape.importBrepFromString
    marker=' private-recomputed-representation'
    def private_recompute(doc):
        recompute(doc)
        if doc.Name.startswith('PoseAnalysis'):
            for obj in doc.Objects:
                if obj.TypeId=='Part::Box':obj.Shape.private_representation=True
    def represented(shape):
        return brep(shape)+(marker if getattr(shape,'private_representation',False) else '')
    def restore_representation(shape,text):
        changed=text.endswith(marker)
        read_brep(shape,text[:-len(marker)] if changed else text)
        shape.private_representation=changed
    monkeypatch.setattr(Document,'recompute',private_recompute)
    monkeypatch.setattr(Shape,'exportBrepToString',represented)
    monkeypatch.setattr(Shape,'importBrepFromString',restore_representation)
    job=run_preparation(original,root)
    assert job.current['state']=='READY',job.current
    copied=Owner(job._document,original.export_root,App=original.App,Gui=original.Gui)
    rows=copied.read_metadata()[KEY]['bodies']
    assert rows and all(row['geometry']!=row['copied_geometry'] for row in rows)
    assert all(_local_digest(copied,copied._object(row['copied_source_id']).Shape)==row['copied_geometry'] for row in rows)
    count=copied.doc.recomputes;metadata=deepcopy(copied.read_metadata())
    assert not validate_model(copied,exact=True)['errors']
    assert copied.doc.recomputes==count and copied.read_metadata()==metadata
    assert original.read_metadata()==before and original.doc.recomputes==0
    # An old row without the new witness must still satisfy its ORIGINAL exact
    # fingerprint. Geometric equivalence alone cannot silently upgrade legacy.
    legacy=deepcopy(metadata)
    for row in legacy[KEY]['bodies']:row.pop('copied_geometry')
    copied.write_metadata(legacy)
    assert validate_model(copied,exact=True)['errors']
    assert copied.read_metadata()==legacy and copied.doc.recomputes==count
    assert original.read_metadata()==before and original.doc.recomputes==0


@pytest.mark.parametrize('change',['legacy','copy_fingerprint','private_CAD'])
def test_private_copy_exact_gate_preserves_source_and_legacy(ready,change):
    original,owner=ready
    source_before=deepcopy(original.read_metadata())
    data=owner.read_metadata();row=data[KEY]['bodies'][0]
    original_geometry=row['geometry'];original_identity=deepcopy(row['path'])
    assert isinstance(row['copied_geometry'],str) and len(row['copied_geometry'])==64
    if change=='legacy':
        for body in data[KEY]['bodies']:body.pop('copied_geometry')
        owner.write_metadata(data)
    elif change=='copy_fingerprint':
        row['copied_geometry']='0'*64;owner.write_metadata(data)
    else:
        owner._object(row['copied_source_id']).Shape.size=(13.,8.,6.)
    before=deepcopy(owner.read_metadata());recomputes=owner.doc.recomputes
    result=validate_model(owner,exact=True)
    assert bool(result['errors']) is (change!='legacy')
    assert owner.read_metadata()==before and owner.doc.recomputes==recomputes
    assert original.read_metadata()==source_before
    assert before[KEY]['bodies'][0]['geometry']==original_geometry
    assert before[KEY]['bodies'][0]['path']==original_identity
