"""M4 identity, edit, failure and archive protocol regressions; native is doubled.

Representation doubles embed transforms in a Compound, unlike the original
M4 tests. Full actual OpenCASCADE comparisons are in test_assembly_pose_kernel.
"""
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest

from assembly_pose_doubles import source_fixture, Owner, pose, _pose, compound, Shape, Vector
from test_assembly_pose_candidate import run_preparation
from apps.desktop_pre.assembly_pose_geometry import assert_same_shape, same_pose, IDENTITY
from apps.desktop_pre.assembly_pose_candidate import validate_model, prepare_fem_object
from apps.desktop_pre.projects import remember_open
from apps.desktop_pre.mesh_binding import MeshBindingObserver, PROPERTY_NAME
from apps.desktop_pre.fem_edit import FEMEditor, _target
from caelab import native_cad


@pytest.fixture
def model(tmp_path,monkeypatch):
    original,root,_=source_fixture(tmp_path,monkeypatch)
    job=run_preparation(original,root)
    assert job.current['state']=='READY',job.current
    owner=Owner(job._document, original.export_root, App=original.App,Gui=original.Gui)
    return original,owner


def first(owner):
    row=owner.read_metadata()['assembly_pose_candidate']['bodies'][0]
    return row,owner._object(row['body_id']),owner._object(row['link_id']),owner._object(row['copied_source_id'])


def test_prepared_binder_has_embedded_world_transform_not_link_shape_double(model):
    _,owner=model;row,body,link,source=first(owner)
    import Part
    native=Part.getShape(link,transform=True)
    assert body.Shape.ShapeType=='Compound' and same_pose(_pose(body.Shape.Placement),IDENTITY)
    assert not same_pose(_pose(body.Shape.Placement),_pose(native.Placement))
    assert body.Shape.exportBrepToString()!=native.exportBrepToString()
    assert owner.motion._replay_geometry(body.Shape)!=owner.motion._replay_geometry(native)
    assert not validate_model(owner,exact=True)['errors']


@pytest.mark.parametrize('mutation',['source_document','source_document_id','source_id','path',
                                   'swapped_link','swapped_source','source_type','missing_identity'])
def test_colocated_repeats_never_prove_source_or_occurrence_identity(model,mutation):
    _,owner=model;data=owner.read_metadata();record=data['assembly_pose_candidate']
    a,b=record['bodies'];body=owner._object(a['body_id']);link=owner._object(a['link_id'])
    other=owner._object(b['link_id']);other.Placement=link.Placement.copy()
    owner.doc.recompute()
    assert not validate_model(owner)['errors']  # intentional coincident edit is allowed
    if mutation=='source_document':a['source_document']='DifferentSourceDocument'
    elif mutation=='source_document_id':record['source_document_id']='Pother'
    elif mutation=='source_id':a['source_id']='AnotherDefinition'
    elif mutation=='source_type':a['source_type']='PartDesign::Feature'
    elif mutation=='path':
        a['path']=['Assembly','OtherParent',a['occurrence_id']];body.SourceOccurrencePath=a['path']
    elif mutation=='swapped_link':
        body.Support=[(other,('',))];body.PoseOccurrence=other
    elif mutation=='swapped_source':
        source=owner._object(a['copied_source_id'])
        twin=owner.doc.copyObject([source],True)[0]
        link.setLink(twin);body.SourcePart=twin;a['copied_source_id']=twin.Name
    elif mutation=='missing_identity':body.SourceIdentity=''
    owner.write_metadata(data);before=owner.read_metadata();count=owner.doc.recomputes
    assert validate_model(owner)['errors']
    assert owner.read_metadata()==before and owner.doc.recomputes==count


@pytest.mark.parametrize('mutation',['array','scale','vector_scale','link_transform','parent','binder_offset','option'])
def test_private_options_and_parent_are_independent_gates(model,mutation):
    _,owner=model;_,body,link,source=first(owner)
    if mutation=='array':link.ElementCount=1
    elif mutation=='scale':link.Scale=2.
    elif mutation=='vector_scale':link.ScaleVector=Vector(1.,1.,1.1)
    elif mutation=='link_transform':link.LinkTransform=True
    elif mutation=='parent':link.getParentGeoFeatureGroup=lambda: NS(Placement=pose(IDENTITY))
    elif mutation=='binder_offset':body.Offset=.1
    elif mutation=='option':body.Refine=True
    assert validate_model(owner)['errors']


def test_source_edit_stale_link_and_binder_cannot_validate_each_other(model,monkeypatch):
    _,owner=model;row,body,link,source=first(owner)
    import Part
    get=Part.getShape;previous=get(link,transform=True)
    monkeypatch.setattr(Part,'getShape',lambda obj,**kw:previous.copy() if obj is link else get(obj,**kw))
    source.Shape.size=(13.,8.,6.)
    before=owner.read_metadata();count=owner.doc.recomputes
    assert validate_model(owner)['errors']
    assert owner.read_metadata()==before and owner.doc.recomputes==count


def test_post_edit_allows_current_geometry_but_never_updates_fem_fingerprints(model,tmp_path):
    original,owner=model;row,body,link,source=first(owner)
    result=prepare_fem_object(owner,body.Name,'mesh');mesh=owner._object(result['object_id'])
    # A nonempty mesh protocol specimen, NOT a generated FEM result.
    mesh.FemMesh=NS(Nodes={1:Vector(),2:Vector(1,0,0),3:Vector(0,1,0),4:Vector(0,0,1)},
                    Volumes=[1],Faces=[],Edges=[],getElementNodes=lambda _: [1,2,3,4])
    observer=MeshBindingObserver(owner.doc);observer.track(mesh)
    old_stamp=getattr(mesh,PROPERTY_NAME)
    condition=owner.doc.addObject('Fem::ConstraintFixed','Fixed')
    condition.References=[(body,['Face1'])]
    target=_target(body,['Face1'])
    condition_data={'conditions':[{'object_id':condition.Name,'targets':[target],'direction_target':None}]}
    inspector=FEMEditor(owner)
    assert not FEMEditor._condition_errors(inspector,condition,condition_data)
    source.Shape.size=(14.,8.,6.)
    assert validate_model(owner)['errors']  # stale binder, not yet recomputed by user
    owner.doc.recompute()  # EXPLICIT editor action, never inside validation
    count=owner.doc.recomputes;before=owner.read_metadata()
    assert not validate_model(owner)['errors']  # not permanently frozen to frame geometry
    assert validate_model(owner,exact=True)['errors']
    assert owner.doc.recomputes==count and owner.read_metadata()==before
    assert getattr(mesh,PROPERTY_NAME)==old_stamp
    with pytest.raises(ValueError,match='Source geometry changed'):observer.validate(mesh)
    assert FEMEditor._condition_errors(inspector,condition,condition_data)
    saved=owner.project.save(tmp_path/'edited.caepre')
    manifest,entry=native_cad.unpack_project(saved['path'],tmp_path/'reopened')
    reopened=owner.App.openDocument(str(entry));remember_open(reopened,manifest,saved['path'])
    fresh=Owner(reopened,owner.export_root,App=owner.App,Gui=owner.Gui)
    count=reopened.recomputes
    assert not validate_model(fresh)['errors']
    assert getattr(fresh._object(mesh.Name),PROPERTY_NAME)==old_stamp
    with pytest.raises(ValueError):MeshBindingObserver(reopened).validate(fresh._object(mesh.Name))
    assert reopened.recomputes==count and not original.doc.recomputes


def test_empty_mesh_settings_creation_never_stamps_a_generated_mesh(model):
    _,owner=model;row,body,_,_=first(owner)
    owner.mesh_bindings=MeshBindingObserver(owner.doc)
    # Real observer rejects an empty mesh; old M4 called track unconditionally.
    result=prepare_fem_object(owner,body.Name,'mesh')
    assert result['created'] and not result['executed']
    assert PROPERTY_NAME not in owner._object(result['object_id']).PropertiesList


def test_initial_pose_check_remains_separate_even_when_geometry_is_symmetric(model):
    _,owner=model;row,body,link,source=first(owner)
    # Intentional later movement remains editable; initial frame check cannot use
    # full solid equivalence as a reason to discard the independent pose check.
    link.Placement=pose([0.,0.,0.,0.,0.,1.,0.]);owner.doc.recompute()
    assert validate_model(owner,exact=True)['errors']
    assert not validate_model(owner)['errors']


def test_kernel_failure_copy_only_and_unmodified_tolerance_contract(monkeypatch):
    from caelab.adapters import freecad_face_catalog_worker as worker
    from caelab.adapters.native_face_catalog import GEOMETRY_TOLERANCES
    a,b=Shape(),Shape();snapshots=[s.exportBrepToString() for s in (a,b)]
    limits=deepcopy(GEOMETRY_TOLERANCES)
    class NativeFailure(Exception):pass
    def fail(actual,expected,tolerances):
        assert actual is not a and expected is not b
        assert tolerances==limits and tolerances is not GEOMETRY_TOLERANCES
        actual.text='modified-copy';tolerances['relative']=1.
        raise NativeFailure('OCC failure')
    monkeypatch.setattr(worker,'_verify_geometry',fail)
    with pytest.raises(ValueError) as error:assert_same_shape(None,a,b,'부품')
    assert isinstance(error.value.__cause__,NativeFailure)
    assert [s.exportBrepToString() for s in (a,b)]==snapshots and GEOMETRY_TOLERANCES==limits


def test_zero_volume_difference_still_requires_complete_face_common(monkeypatch):
    from assembly_pose_doubles import Face,BooleanResult
    monkeypatch.setattr(Face,'common',lambda *_:BooleanResult(area=0.))
    with pytest.raises(ValueError):assert_same_shape(None,Shape(),Shape(),'면 없음')


def test_ambiguous_face_correspondence_never_chooses_first_match(monkeypatch):
    from assembly_pose_doubles import Face,BooleanResult
    from caelab.adapters import freecad_face_catalog_worker as worker
    monkeypatch.setattr(worker,'_candidate',lambda *_:True)
    monkeypatch.setattr(Face,'common',lambda self,_:BooleanResult(area=self.Area))
    with pytest.raises(ValueError):assert_same_shape(None,Shape(),Shape(),'중복 면')


def test_solid_difference_must_be_checked_in_both_directions(monkeypatch):
    from assembly_pose_doubles import BooleanResult
    calls=[]
    a,b=Shape(),Shape();a.side='first';b.side='second'
    def difference(self,other):
        calls.append((self.side,other.side))
        return BooleanResult(volume=0. if self.side=='first' else .01)
    monkeypatch.setattr(Shape,'cut',difference)
    with pytest.raises(ValueError):assert_same_shape(None,a,b,'양방향 차이')
    assert calls==[('first','second'),('second','first')]


def test_original_pose_limits_are_not_replaced_by_geometry_tolerance():
    import math
    from apps.desktop_pre.assembly_pose_geometry import TRANSLATION_TOL_MM,ROTATION_TOL_RAD
    assert (TRANSLATION_TOL_MM,ROTATION_TOL_RAD)==(1.e-7,1.e-9)
    assert same_pose([.9e-7,0.,0.,0.,0.,0.,1.],IDENTITY)
    assert not same_pose([1.1e-7,0.,0.,0.,0.,0.,1.],IDENTITY)
    assert same_pose([0.,0.,0.,0.,0.,math.sin(.45e-9),math.cos(.45e-9)],IDENTITY)
    assert not same_pose([0.,0.,0.,0.,0.,math.sin(.55e-9),math.cos(.55e-9)],IDENTITY)


def test_windows_macro_refuses_unowned_or_wrong_pid_before_touching_native(tmp_path,monkeypatch):
    import importlib.util,json,os
    from pathlib import Path
    path=Path(__file__).parents[1]/'examples/assembly-candidate/run_native_correction.py'
    spec=importlib.util.spec_from_file_location('m4_owned_launcher_test',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    request=tmp_path/'request.json';request.write_text(json.dumps({'token':'test-token'}))
    monkeypatch.delenv('CAELAB_M4_OWNED_TOKEN',raising=False)
    with pytest.raises(RuntimeError,match='Not an owned'):mod.owned_native_entry(request)
    monkeypatch.setenv('CAELAB_M4_OWNED_TOKEN','test-token')
    monkeypatch.setenv('CAELAB_M4_OWNED_REQUEST',str(request.resolve()))
    monkeypatch.setenv('CAELAB_M4_OWNED_PARENT_PID',str(os.getppid()+1))
    with pytest.raises(RuntimeError,match='different process'):mod.owned_native_entry(request)
