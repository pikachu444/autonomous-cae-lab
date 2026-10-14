"""Dedicated cold-edit verifier: real FEMEditor commands on native doubles.

Archives are actual .caepre containers carrying the existing in-memory native
serialization double, NOT FreeCAD FCStd or a new-process Windows acceptance.
"""
from copy import deepcopy
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
from types import SimpleNamespace as NS
import sys
import pytest

from assembly_pose_doubles import source_fixture,Owner,Object,Vector
from test_assembly_pose_candidate import run_preparation
from apps.desktop_pre.assembly_pose_candidate import KEY,require_valid,prepare_fem_object
from apps.desktop_pre.fem_edit import FEMEditor,_mesh_hash
from apps.desktop_pre.mesh_binding import MeshBindingObserver,PROPERTY_NAME
from apps.desktop_pre.projects import remember_open
from caelab import native_cad

spec=spec_from_file_location('m4_cold_edit_test',Path(__file__).parents[1]/'examples/assembly-candidate/native_check.py')
verifier=module_from_spec(spec);spec.loader.exec_module(verifier)


class Quantity:
    """Only the already-declared mm / MPa values needed by these protocol tests."""
    def __init__(self,value):
        parts=str(value).split();self.Value=float(parts[0]);self.unit=parts[1] if len(parts)>1 else ''
    def getValueAs(self,unit):
        assert unit==self.unit,(unit,self.unit)
        return self
    def __str__(self):return str(self.Value)+' '+self.unit


def attach_fem(owner):
    owner.App.Units=NS(Quantity=Quantity)
    owner.Gui=NS(Control=NS(activeDialog=lambda:False),activeDocument=lambda:NS(getInEdit=lambda:False))
    owner.fem=FEMEditor(owner);owner.mesh_bindings=MeshBindingObserver(owner.doc)


@pytest.fixture
def edited(tmp_path,monkeypatch):
    original,root,_=source_fixture(tmp_path,monkeypatch);job=run_preparation(original,root)
    assert job.current['state']=='READY',job.current
    owner=Owner(job._document,original.export_root,App=original.App,Gui=original.Gui)
    attach_fem(owner)
    native=sys.modules['ObjectsFem']
    def mesh(doc,name):
        obj=doc.addObject('Fem::FemMeshObjectPython',name);obj.Proxy=NS(Type='Fem::FemMeshGmsh')
        obj.FemMesh=NS();obj.MeshRegionList=[];obj.MeshBoundaryLayerList=[];obj.MeshGroupList=[]
        obj.CharacteristicLengthMin=Quantity('0 mm');obj.CharacteristicLengthMax=Quantity('0 mm')
        obj.ElementOrder='2nd';obj.ElementDimension='3D'
        return obj
    def material(doc,name):
        obj=doc.addObject('App::MaterialObjectPython',name);obj.References=[]
        obj.Proxy=NS(Type='Fem::MaterialCommon');obj.Category='Solid';return obj
    def local(doc,mesh,value,name):
        obj=doc.addObject('Fem::MeshRegion',name);obj.References=[]
        mesh.MeshRegionList.append(obj);return obj
    monkeypatch.setattr(native,'makeMeshGmsh',mesh)
    monkeypatch.setattr(native,'makeMaterialSolid',material)
    monkeypatch.setattr(native,'makeMeshRegion',local,raising=False)
    monkeypatch.setattr(native,'makeConstraintFixed',lambda doc:doc.addObject('Fem::ConstraintFixed','Fixed'),raising=False)
    monkeypatch.setattr(native,'makeConstraintForce',lambda doc:doc.addObject('Fem::ConstraintForce','Force'),raising=False)
    report=require_valid(owner);saved=owner.read_metadata()[KEY]
    assignments=[]
    for i,row in enumerate(saved['bodies'],1):
        body=owner._object(row['body_id'])
        m=prepare_fem_object(owner,body.Name,'mesh');mesh=owner._object(m['object_id'])
        material_id=prepare_fem_object(owner,body.Name,'material')['object_id']
        owner.fem.dispatch('pre.fem.material_set',{'young_modulus':200000.+1000*i,'unit':'MPa','poisson_ratio':.3},
                           {'object_id':material_id})
        owner.fem.dispatch('pre.fem.mesh_settings',{'min_size':2.+.1*i,'max_size':4.+.1*i,'unit':'mm','element_type':'C3D10'},
                           {'object_id':mesh.Name})
        region=owner.fem.dispatch('pre.fem.region_set',{'label':'시험 면','subelements':['Face'+str(i)]},{'object_id':body.Name})
        condition=owner.fem.dispatch('pre.fem.condition_set',{'region_id':region['id'],'kind':'Fixed'},
                                    {'object_id':report['analysis_id']})
        refinement=owner.fem.dispatch('pre.fem.mesh_local_size',{'region_id':region['id'],'size':1.5+.1*i,'unit':'mm'},
                                     {'object_id':mesh.Name})
        # Mesh protocol specimen only: no test-generated Gmsh result is claimed.
        mesh.FemMesh=NS(Nodes={1:Vector(),2:Vector(1,0,0),3:Vector(0,1,0),4:Vector(0,0,1)},
            Volumes=[1],Faces=[],Edges=[],VolumeCount=1,getElementNodes=lambda _: [1,2,3,4])
        owner.mesh_bindings.track(mesh)
        assignments.append({'body_id':body.Name,'mesh_id':mesh.Name,'material_id':material_id,
            'material':dict(owner._object(material_id).Material),'condition_id':condition['object_id'],
            'region_id':region['id'],'face':'Face'+str(i),'target':region['target'],
            'mesh_settings':owner.fem._mesh_settings(mesh),'local_id':refinement['object_id'],
            'local_size_mm':refinement['size_mm'],'mesh_binding':getattr(mesh,PROPERTY_NAME),
            'mesh_volume_count':1,'mesh_node_count':4,'mesh_content_sha256':_mesh_hash(mesh.FemMesh)})
    expected={'bodies':saved['bodies'],'assignments':assignments,'frame':report['frame'],'time':report['time'],
              'meshes':[r['mesh_id'] for r in assignments],'materials':[r['material_id'] for r in assignments]}
    # Exercise the verifier's full-content branch, with all objects explicitly doubled.
    verifier.check_assignments(owner,expected,'NATIVE_GMSH')
    return original,owner,expected


def reopen(owner,saved,path):
    manifest,entry=native_cad.unpack_project(saved['path'],path)
    doc=owner.App.openDocument(str(entry));remember_open(doc,manifest,saved['path'])
    fresh=Owner(doc,owner.export_root,App=owner.App,Gui=owner.Gui);attach_fem(fresh)
    return fresh


def test_real_typed_apply_after_archive_reopen_changes_each_target_and_resaves(edited,tmp_path):
    original,owner,expected=edited
    before_source=original.read_metadata();saved=owner.project.save(tmp_path/'first.caepre')
    source_bytes=Path(saved['path']).read_bytes()
    owner.App.closeDocument(owner.doc.Name)
    fresh=reopen(owner,saved,tmp_path/'한글 첫 재열기')
    count=fresh.doc.recomputes;before=fresh.read_metadata()
    verifier.check_assignments(fresh,expected,'NATIVE_GMSH')
    assert fresh.doc.recomputes==count and fresh.read_metadata()==before
    updated,edits=verifier.edit_reopened_inputs(fresh,expected,'NATIVE_GMSH')
    assert len(edits)==2 and fresh.doc.recomputes>count  # explicit apply, not a read
    for old,new,edit in zip(expected['assignments'],updated['assignments'],edits):
        assert all(old[k]==new[k] for k in ('body_id','mesh_id','material_id','condition_id','local_id'))
        assert all(old[k]!=new[k] for k in ('material','mesh_settings','face','target','local_size_mm'))
        assert old['mesh_binding']==new['mesh_binding']
        assert old['mesh_content_sha256']==new['mesh_content_sha256']
        assert edit['old_face']!=edit['new_face']
    saved_again=fresh.project.save(tmp_path/'수정 후 재저장.caepre')
    fresh.App.closeDocument(fresh.doc.Name)
    second=reopen(fresh,saved_again,tmp_path/'재저장 파일 다시 열기')
    count=second.doc.recomputes;before=second.read_metadata()
    verifier.check_assignments(second,updated,'NATIVE_GMSH')
    assert second.doc.recomputes==count and second.read_metadata()==before
    assert Path(saved['path']).read_bytes()==source_bytes
    assert original.read_metadata()==before_source and not original.doc.recomputes


@pytest.mark.parametrize('op',['pre.fem.material_set','pre.fem.mesh_settings','pre.fem.condition_set','pre.fem.mesh_local_size'])
def test_noop_apply_cannot_be_mistaken_for_success(edited,monkeypatch,op):
    _,owner,expected=edited
    real=owner.fem.dispatch
    def noop(operation,args,target):
        if operation!=op:return real(operation,args,target)
        if op=='pre.fem.mesh_settings':return {'mesh_id':target['object_id'],'mesh_generated':False}
        if op=='pre.fem.mesh_local_size':return {'object_id':args['refinement_id'],'size_mm':args['size']}
        return {'object_id':target['object_id']}
    monkeypatch.setattr(owner.fem,'dispatch',noop)
    with pytest.raises((AssertionError,ValueError)):
        verifier.edit_reopened_inputs(owner,expected,'NATIVE_GMSH')


def test_verifier_rejects_same_count_mesh_with_modified_nodes(edited):
    _,owner,expected=edited
    mesh=owner._object(expected['assignments'][0]['mesh_id']);mesh.FemMesh.Nodes[1]=Vector(.1,0,0)
    with pytest.raises((AssertionError,ValueError)):
        verifier.check_assignments(owner,expected,'NATIVE_GMSH')


def test_cold_edit_refuses_failed_state_before_first_apply(edited,monkeypatch):
    _,owner,expected=edited;data=owner.read_metadata();data[KEY]['state']='FAILED';owner.write_metadata(data)
    calls=[];monkeypatch.setattr(owner.fem,'dispatch',lambda *args:calls.append(args))
    with pytest.raises(ValueError):verifier.edit_reopened_inputs(owner,expected,'NATIVE_GMSH')
    assert not calls
