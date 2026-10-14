"""M4 protocol/geometry/real archive tests; all native objects are doubles."""
from copy import deepcopy
from types import SimpleNamespace as NS
import math
from pathlib import Path
import pytest
import numpy as np

from assembly_pose_doubles import source_fixture,pose,_pose,Owner,get_shape
from apps.desktop_pre import metadata
from apps.desktop_pre.assembly_pose_geometry import (frame_world_poses,select_frame,same_pose,IDENTITY)
from apps.desktop_pre.assembly_pose_candidate import PoseCandidates,validate_model,in_preparation,prepare_fem_object
from apps.desktop_pre.motion_history import pack_poses
from apps.desktop_pre.projects import remember_open
from caelab import native_cad

@pytest.fixture
def sample(tmp_path,monkeypatch):return source_fixture(tmp_path,monkeypatch)

def matrix(value):
    # Independent Rodrigues matrix oracle, not production pose_product.
    x,y,z,w=value[3:]; q=np.array([x,y,z]); skew=np.array([[0,-z,y],[z,0,-x],[-y,x,0.]])
    result=np.eye(4);result[:3,:3]=np.eye(3)+2*w*skew+2*skew@skew
    result[:3,3]=value[:3];return result

def test_multiple_parent_rotations_saved_world_root_repeats_not_collapsed(sample):
    owner,root,payload=sample
    result=select_frame(owner,root.Name,'Kfixture',2)
    assert len(result['leaves'])==2 and result['leaves'][0]['source_id']==result['leaves'][1]['source_id']
    actual={row['id']:value for row,value in zip(payload['bindings'],payload['frames'][2])}
    for row in result['leaves']:
        expected=matrix(payload['world_roots'][2])
        for name in row['path'][1:]:expected=expected@matrix(actual[name])
        np.testing.assert_allclose(matrix(row['world_pose']),expected,atol=1e-12)
        assert len(row['path'])==4 and '(배치 ' in row['label']
    assert not same_pose(result['leaves'][0]['world_pose'],result['leaves'][1]['world_pose'])
    assert result['ground_to_support'] is False and result['physics']=='STARTING_GEOMETRY_ONLY'
    assert not owner.doc.recomputes

@pytest.mark.parametrize('mutation', ['shape','placement','reference','missing_pose','rejected','frame'])
def test_stale_or_missing_selected_result_never_recomputes_or_changes_source(sample,mutation):
    owner,root,payload=sample;data=owner.read_metadata()
    if mutation=='shape':owner._object('Box').Shape.text='changed'
    if mutation=='placement':owner._object('RepeatB').Placement=pose([2.,0.,0.,0.,0.,0.,1.])
    if mutation=='reference':owner._object('Slide2').Reference2=(owner._object('RepeatA'),['',''])
    if mutation=='missing_pose':data['motion_paths']['Kfixture'].pop('poses');owner.write_metadata(data)
    if mutation=='rejected':data['motion_paths']['Kfixture']['accepted']=False;owner.write_metadata(data)
    before=owner.read_metadata();placements=[_pose(obj.Placement) for obj in owner.doc.Objects]
    with pytest.raises(ValueError):select_frame(owner,root.Name,'Kfixture',-1 if mutation=='frame' else 2)
    assert owner.read_metadata()==before and placements==[_pose(obj.Placement) for obj in owner.doc.Objects]
    assert not owner.doc.recomputes


def test_missing_moving_ancestor_never_assumed_identity(sample):
    _,_,payload=sample;broken=deepcopy(payload)
    index=next(i for i,row in enumerate(broken['bindings']) if row['id']=='Outer')
    broken['bindings'].pop(index)
    for row in broken['frames']:row.pop(index)
    with pytest.raises(ValueError,match='상위 배치'):frame_world_poses(broken,2)
    # Only explicitly inspected non-geometric groups may lack a placement.
    assert frame_world_poses(broken,2,nonmoving_groups=[['Assembly','Outer']])


def run_preparation(owner,root,stop=None):
    job=PoseCandidates(owner);owner.pose_candidates=job
    job.start({'calculation_id':'Kfixture','frame':2},{'assembly_id':root.Name},automatic=False)
    for _ in range(40):
        if not job.busy:break
        if stop is not None:stop(job)
        job.advance()
    assert not job.busy
    return job


def test_end_to_end_independent_occurrences_actual_bundle_roundtrip_and_edit_save(sample,tmp_path):
    owner,root,_=sample;before=owner.read_metadata();objects=list(owner.doc.Objects)
    poses=[_pose(obj.Placement) for obj in objects];generation=owner.generation
    job=run_preparation(owner,root)
    assert job.current['state']=='READY',job.current
    target=job._document
    assert target is not owner.doc and not in_preparation(target)
    restored=Owner(target,tmp_path/'edit',App=owner.App,Gui=owner.Gui)
    report=validate_model(restored,exact=True)
    assert report['state']=='READY' and not report['errors'],report
    assert len(report['bodies'])==2
    assert len({row['body_id'] for row in report['bodies']})==2
    assert len({row['source_id'] for row in report['bodies']})==1
    analysis=target.getObject(report['analysis_id'])
    assert len(analysis.Group)==1 and not any(hasattr(obj,'References') for obj in analysis.Group)
    assert not any(obj.TypeId.startswith('Assembly::') for obj in target.Objects)
    first,second=[row['body_id'] for row in report['bodies']]
    mesh=prepare_fem_object(restored,first,'mesh');material=prepare_fem_object(restored,second,'material')
    assert target.getObject(mesh['object_id']).Shape.Name==first
    assert target.getObject(material['object_id']).References[0][0].Name==second
    assert target.getObject(material['object_id']).Material=={}  # editable invalid material is retained
    saved=restored.project.save(tmp_path/'edited.caepre')
    owner.App.closeDocument(target.Name)
    manifest,entry=native_cad.unpack_project(saved['path'],tmp_path/'edited-open')
    reopened=owner.App.openDocument(str(entry));remember_open(reopened,manifest,saved['path'])
    fresh=Owner(reopened,tmp_path/'fresh',App=owner.App,Gui=owner.Gui)
    assert not validate_model(fresh)['errors'] and not reopened.recomputes==0 # editor did recompute before save
    assert reopened.getObject(mesh['object_id']).Shape.Name==first
    assert reopened.getObject(material['object_id']).References[0][0].Name==second
    assert not owner.doc.recomputes and owner.read_metadata()==before and owner.doc.Objects==objects
    assert [_pose(obj.Placement) for obj in objects]==poses and owner.generation==generation
    assert owner.App.preferences.data=={} and not owner.closed

@pytest.mark.parametrize('stage',['before','source','parts'])
def test_cancel_preserves_source_and_created_files_without_a_solver(sample,stage):
    owner,root,_=sample;before=owner.read_metadata()
    def cancel(job):
        if stage=='before' or stage=='source' and job.current.get('completed') or stage=='parts' and job._document is not None:
            job.cancel()
    job=run_preparation(owner,root,cancel)
    assert job.current['state']=='CANCELLED',job.current
    assert owner.read_metadata()==before and not owner.doc.recomputes and not owner.closed
    assert owner.App.ActiveDocument is owner.doc
    if stage=='parts':
        assert Path(job.current['draft_project']).is_file() and not in_preparation(job._document)
    assert job.current['solver_execution']=='NOT_PERFORMED'


def test_failure_after_native_copy_keeps_draft_and_previous_ready(sample,monkeypatch):
    owner,root,_=sample;old=run_preparation(owner,root);retained=Path(old.current['project']).read_bytes()
    # Controlled native binder failure, not a simulated successful geometry operation.
    from assembly_pose_doubles import Object
    original=Object.recompute
    def fail(self):
        if self.TypeId=='PartDesign::SubShapeBinder':raise RuntimeError('controlled native binder failure')
        return original(self)
    monkeypatch.setattr(Object,'recompute',fail)
    newer=run_preparation(owner,root)
    assert newer.current['state']=='FAILED' and 'binder failure' in newer.current['message']
    assert Path(newer.current['source_project']).is_file()
    assert Path(newer.current['draft_project']).is_file()
    assert Path(old.current['project']).read_bytes()==retained and not owner.closed


def test_deleted_or_rebound_occurrence_is_invalid_not_silently_repaired(sample,tmp_path):
    owner,root,_=sample;job=run_preparation(owner,root);assert job.current['state']=='READY',job.current
    new=Owner(job._document,tmp_path/'edit',App=owner.App,Gui=owner.Gui)
    rows=new.read_metadata()['assembly_pose_candidate']['bodies']
    first,second=[new._object(row['body_id']) for row in rows]
    first.Support=list(second.Support)
    before=new.doc.recomputes
    assert validate_model(new)['state']=='INVALID' and new.doc.recomputes==before


def test_preview_is_not_restored_in_original_but_recovery_copy_restores_design(sample,tmp_path):
    owner,root,payload=sample;motion=owner.motion
    motion._base=[(owner._object(row['id']),'Placement',owner._object(row['id']).Placement.copy()) for row in payload['bindings']]
    for row,value in zip(payload['bindings'],payload['frames'][2]):owner._object(row['id']).Placement=pose(value)
    motion._last={(obj.Name,prop):_pose(getattr(obj,prop)) for obj,prop,_ in motion._base}
    motion._preview=True;motion._expected_generation=owner.generation
    before=[_pose(obj.Placement) for obj in owner.doc.Objects]
    job=run_preparation(owner,root);assert job.current['state']=='READY',job.current
    assert motion._preview and [_pose(obj.Placement) for obj in owner.doc.Objects]==before
    path=job.current['source_project'];raw=Path(path).read_bytes()
    manifest,entry=native_cad.unpack_project(path,tmp_path/'recover')
    recovered=owner.App.openDocument(str(entry));remember_open(recovered,manifest,path)
    for binding in payload['bindings']:assert same_pose(_pose(recovered.getObject(binding['id']).Placement),IDENTITY)
    assert manifest['new_design_branch'] and Path(path).read_bytes()==raw
    assert [_pose(obj.Placement) for obj in owner.doc.Objects]==before


def test_corrupt_source_archive_and_missing_open_are_explicit(sample):
    owner,root,_=sample;job=run_preparation(owner,root);assert job.current['state']=='READY',job.current
    source=Path(job.current['source_project']);source.write_bytes(source.read_bytes()+b'changed')
    with pytest.raises(ValueError,match='바뀌었습니다'):job.open_attempt(job.current['id'],'source')
    with pytest.raises(ValueError):job.open_attempt('../bad','source')
    assert not owner.doc.recomputes


def test_native_selection_not_previous_table_row_resolves_each_repeat(sample,tmp_path):
    from apps.desktop_pre.assembly_pose_candidate import selected_body
    owner,root,_=sample;job=run_preparation(owner,root)
    fresh=Owner(job._document,tmp_path/'target',App=owner.App,Gui=owner.Gui)
    rows=fresh.read_metadata()['assembly_pose_candidate']['bodies']
    selections=[]
    fresh.Gui=NS(Selection=NS(getSelectionEx=lambda name:selections))
    assert selected_body(fresh) is None
    for row in rows:
        selections[:]=[NS(Object=fresh._object(row['body_id']),SubElementNames=['Face1'])]
        assert selected_body(fresh)==row['body_id']
    selections.append(NS(Object=fresh._object(rows[0]['body_id']),SubElementNames=['Face2']))
    assert selected_body(fresh) is None
    selections[:]=[NS(Object=owner._object('Box'),SubElementNames=[])]
    assert selected_body(fresh) is None


def test_edit_during_preparation_is_not_overwritten_or_replayed(sample):
    owner,root,_=sample
    def edit(job):
        if job._document is not None:
            owner._object('RepeatB').Placement=pose([999.,0.,0.,0.,0.,0.,1.]);owner.generation+=1
    job=run_preparation(owner,root,edit)
    assert job.current['state']=='FAILED' and '편집' in job.current['message']
    assert owner._object('RepeatB').Placement.Base.x==999.
    assert Path(job.current['draft_project']).is_file()


def test_common_commands_registered_without_old_numerical_dependency():
    from apps.desktop_pre.assembly_pose_candidate import OPERATIONS
    from caelab.native_commands import CAPABILITIES
    from apps.desktop_pre.bridge import OPERATIONS as ALL_OPERATIONS
    assert set(OPERATIONS)<=set(ALL_OPERATIONS) and set(OPERATIONS)<=CAPABILITIES['pre']


def test_savecopy_guard_restores_flags_even_on_native_exception(sample):
    from apps.desktop_pre.assembly_pose_candidate import _snapshot_guard
    owner,_,_=sample
    assert not owner.project.in_save
    with pytest.raises(RuntimeError):
        with _snapshot_guard(owner,[owner.doc]):
            assert owner.project.in_save
            raise RuntimeError('native save failed')
    assert not owner.project.in_save


def test_preview_movement_without_generation_change_is_detected(sample):
    owner,root,_=sample
    def move(job):
        if job._document is not None:
            owner._object('RepeatA').Placement=pose([123.,0.,0.,0.,0.,0.,1.])
    job=run_preparation(owner,root,move)
    assert job.current['state']=='FAILED' and '표시 자세' in job.current['message']
    assert owner._object('RepeatA').Placement.Base.x==123.


def test_failed_reopen_retains_prepared_copy_and_opens_only_explicit_recovery(sample,monkeypatch):
    owner,root,_=sample
    original=owner.App.openDocument
    def fail(path):raise RuntimeError('controlled readback failure')
    monkeypatch.setattr(owner.App,'openDocument',fail)
    job=run_preparation(owner,root)
    assert job.current['state']=='FAILED' and Path(job.current['prepared_project']).is_file()
    assert not job.current.get('draft_project') and not job.current.get('project')
    receipts=[]
    monkeypatch.setattr(owner.project,'open',lambda receipt:receipts.append(receipt) or receipt)
    job.open_attempt(job.current['id'],'draft')
    assert receipts[-1]['path']==job.current['prepared_project']
    assert receipts[-1]['sha256']==job.current['prepared_sha256']
    with pytest.raises(ValueError,match='저장 파일'):job.open_attempt(job.current['id'],'model')
    assert not owner.closed and owner.App.ActiveDocument is owner.doc


def test_legacy_flat_numerical_boundary_remains_separate(sample):
    from apps.desktop_pre.assembly_candidates import structure,POLICY
    owner,root,_=sample;root.Type='Assembly'
    # The old single-joint Numerical route is still explicitly flat. M4's
    # exact nested selection succeeds without widening or replacing that route.
    with pytest.raises(ValueError,match='two direct occurrences'):structure(owner,root)
    assert POLICY=='native-flat-joint-v1'
    assert len(select_frame(owner,root.Name,'Kfixture',2)['leaves'])==2
