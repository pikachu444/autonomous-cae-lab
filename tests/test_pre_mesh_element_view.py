"""Scene/owner doubles for preservation; real native rendering is separate."""
from copy import deepcopy
from types import SimpleNamespace as NS
import sys
import pytest

from apps.desktop_pre import mesh_element_view as module
NATIVE_GEOMETRY = module._native_geometry


class Node:
    def __init__(self): self.children = []
    def addChild(self, node): self.children.append(node)
    def removeChild(self, node): self.children.remove(node)
    def findChild(self, node): return self.children.index(node) if node in self.children else -1
    def getNumChildren(self): return len(self.children)
    def getChild(self, i): return self.children[i]


class Switch(Node):
    def __init__(self, value=3): super().__init__(); self._value = value
    @property
    def whichChild(self): return NS(getValue=lambda: self._value)
    @whichChild.setter
    def whichChild(self, value): self._value = value


@pytest.fixture
def native(monkeypatch):
    coin = NS(SoSeparator=Node, SoSwitch=Switch, SoPickStyle=type('Pick', (), {'UNPICKABLE':1}),
              SoTransform=type('Transform', (), {}), SO_SWITCH_NONE=-1, SbViewportRegion=lambda *size:size)
    monkeypatch.setitem(sys.modules, 'pivy', NS(coin=coin))
    scene, mode = Node(), Switch()
    root = Node(); root.addChild(mode); scene.addChild(root)
    doc = NS(Name='Original', Objects=[])
    pose = NS(Base=NS(x=10., y=20., z=30.), Rotation=NS(Q=(0.,0.,0.,1.)))
    mesh = NS(Name='Mesh', Label='원 메시', Document=doc, FemMesh=NS(Volumes=[477,479], sha='a'*64),
              ViewObject=NS(RootNode=root, Visibility=True, ShowInner=False), getGlobalPlacement=lambda:pose)
    base = NS(Name='Base', Document=doc)
    doc.Objects=[mesh,base]; doc.getObject=lambda name: next((o for o in doc.Objects if o.Name==name),None)
    selection = NS(rows=[NS(Object=base, SubElementNames=['Face1'])], modes=[])
    def get_selection(name, resolve):
        assert name==doc.Name; selection.modes.append(resolve); return [r for r in selection.rows if r.Object.Document is doc]
    selection.getSelectionEx=get_selection
    def clear_selection(name):
        selection.rows[:]=[r for r in selection.rows if r.Object.Document.Name != name]
    selection.clearSelection=clear_selection
    selection.addSelection=lambda obj, name: selection.rows.append(NS(Object=obj,SubElementNames=[name]))
    view = NS(camera='original camera', fit_calls=[])
    view.getSceneGraph=lambda:scene; view.getCamera=lambda:view.camera
    view.setCamera=lambda value:setattr(view,'camera',value)
    view.getSize=lambda:(900,650)
    view.getCameraNode=lambda:NS(viewAll=lambda *args:view.fit_calls.append(args))
    app = NS(ActiveDocument=doc, observers=[])
    app.addDocumentObserver=lambda obj:app.observers.append(obj)
    app.removeDocumentObserver=lambda obj:app.observers.remove(obj)
    owner = NS(doc=doc,App=app,Gui=NS(Selection=selection,activeDocument=lambda:NS(activeView=lambda:view)),
               generation=0,session_id='session',document_id='document',closed=False,metadata={'original':True},assert_thread=lambda:None)
    owner.fem=NS(_mesh=lambda target:mesh if target=={'object_id':'Mesh'} else None)
    monkeypatch.setattr(module,'_mesh_hash',lambda fem:fem.sha)
    calls=[]
    monkeypatch.setattr(module,'_native_geometry',lambda owner,mesh,ids:(calls.append(list(ids)) or Node()))
    return NS(owner=owner,mesh=mesh,base=base,scene=scene,mode=mode,view=view,selection=selection,calls=calls,pose=pose)


def test_exact_ids_isolate_and_selected_geometry_fit_restore_original_state(native):
    n=native; before=deepcopy(n.owner.metadata),n.mesh.ViewObject.Visibility,n.mesh.ViewObject.ShowInner,n.mesh.FemMesh.sha
    view=module.get_view(n.owner,n.mesh)
    result=view.show([479,479],n.mesh.FemMesh.sha,isolate=True,fit=True)
    assert result['element_ids']==[479] and n.calls==[[479]]
    assert n.mode.whichChild.getValue()==-1 and len(n.scene.children)==2
    assert n.view.fit_calls[0][0] is view._overlay
    assert n.view.fit_calls[0][1]==(900,650)
    assert module.selected_element_ids(n.owner,n.mesh)==[479]
    assert view._overlay.getChild(1).translation==(10.,20.,30.)
    view.restore()
    assert not view.active and len(n.scene.children)==1 and n.mode.whichChild.getValue()==3
    assert n.view.camera=='original camera'
    assert [(r.Object.Name,r.SubElementNames) for r in n.selection.rows]==[('Base',['Face1'])]
    assert before==(n.owner.metadata,n.mesh.ViewObject.Visibility,n.mesh.ViewObject.ShowInner,n.mesh.FemMesh.sha)
    assert n.owner.generation==0 and set(n.selection.modes)=={0}
    view.close(); assert not n.owner.App.observers


def test_empty_stale_foreign_and_replaced_mesh_never_show_old_geometry(native):
    n=native; view=module.get_view(n.owner,n.mesh)
    for ids in ([],[999]):
        with pytest.raises(ValueError):view.show(ids,n.mesh.FemMesh.sha)
    assert n.calls==[]
    view.show([477],n.mesh.FemMesh.sha,isolate=True)
    n.mesh.FemMesh.sha='b'*64
    with pytest.raises(ValueError,match='바뀌었습니다'): view.show([477],'a'*64)
    assert not view.active and len(n.scene.children)==1 and n.mode.whichChild.getValue()==3
    n.mesh.FemMesh.sha='a'*64
    view.show([477],n.mesh.FemMesh.sha,isolate=True)
    n.owner.doc.Objects.remove(n.mesh)
    assert not view.check_current() and not view.active
    view.close()


def test_save_change_close_and_active_document_callbacks_remove_transient_scene(native):
    n=native; view=module.get_view(n.owner,n.mesh)
    for callback in (lambda:view.slotStartSaveDocument(n.owner.doc),lambda:view.slotChangedObject(n.mesh,'FemMesh'),
                     lambda:view.slotActivateDocument(NS(Name='other'))):
        view.show([479],n.mesh.FemMesh.sha,isolate=True)
        callback(); assert not view.active and len(n.scene.children)==1
    view.show([479],n.mesh.FemMesh.sha,isolate=True)
    n.owner.closed=True
    view.slotDeletedDocument(n.owner.doc)
    assert not view.active and len(n.scene.children)==1
    view.close(); view.close(); assert not n.owner.App.observers


def test_raw_model_selection_rejects_whole_mesh_and_other_objects(native):
    n=native
    n.selection.rows=[NS(Object=n.mesh,SubElementNames=['','Node760','Elem477F1','Elem477F2','Elem999F1']),
                      NS(Object=n.base,SubElementNames=['Elem479F1'])]
    assert module.selected_element_ids(n.owner,n.mesh)==[477]
    n.selection.rows=[NS(Object=n.mesh,SubElementNames=[])]
    assert module.selected_element_ids(n.owner,n.mesh)==[]


def test_geometry_creation_failure_preserves_prior_view_without_model_edits(native,monkeypatch):
    n=native; view=module.get_view(n.owner,n.mesh)
    view.show([477],n.mesh.FemMesh.sha,isolate=True)
    old=view._overlay
    def fail(*args):raise ValueError('native builder failed')
    monkeypatch.setattr(module,'_native_geometry',fail)
    with pytest.raises(ValueError):view.show([479],n.mesh.FemMesh.sha,isolate=True)
    assert view._overlay is old and view.element_ids==[477] and n.owner.generation==0
    view.close()


def test_pending_generation_restores_view_and_rejects_new_scene(native):
    n=native; view=module.get_view(n.owner,n.mesh)
    view.show([477],n.mesh.FemMesh.sha,isolate=True)
    n.owner.fem._pending={'Mesh':{'id':'running'}}
    assert not view.check_current() and not view.active
    with pytest.raises(ValueError,match='메시 생성 중'):view.select([479],n.mesh.FemMesh.sha)
    assert len(n.calls)==1 and n.mode.whichChild.getValue()==3
    view.close()


def test_other_document_selection_and_new_active_document_are_not_erased(native):
    n=native; otherdoc=NS(Name='Other');other=NS(Name='OtherPart',Document=otherdoc)
    n.selection.rows.append(NS(Object=other,SubElementNames=['Face2']))
    view=module.get_view(n.owner,n.mesh)
    view.show([477],n.mesh.FemMesh.sha,isolate=True)
    assert any(r.Object is other for r in n.selection.rows)
    n.owner.App.ActiveDocument=otherdoc
    view.slotActivateDocument(otherdoc)
    assert any(r.Object is other and r.SubElementNames==['Face2'] for r in n.selection.rows)
    assert any(r.Object is n.base and r.SubElementNames==['Face1'] for r in n.selection.rows)
    assert n.owner.App.ActiveDocument is otherdoc and not view.active
    view.close()


def test_native_builder_removes_own_pose_before_outer_global_pose(native,monkeypatch):
    n=native; bodies=[];closed=[]
    class FemMesh:
        def __init__(self):self.nodes={};self.volumes={};bodies.append(self)
        def addNode(self,x,y,z,i):self.nodes[i]=(x,y,z)
        def addVolume(self,ids,i):self.volumes[i]=ids
    monkeypatch.setitem(sys.modules,'Fem',NS(FemMesh=FemMesh))
    points={i:NS(x=i+10.,y=20.,z=30.) for i in range(1,5)}
    n.mesh.FemMesh.Nodes=points;n.mesh.FemMesh.getElementNodes=lambda i:(1,2,3,4)
    n.mesh.Placement=NS(inverse=lambda:NS(multVec=lambda p:NS(x=p.x-10,y=p.y-20,z=p.z-30)))
    geometry=Node();geometry.copy=lambda:geometry
    switch=Switch(0);switch.addChild(geometry);root=Node();root.addChild(switch)
    obj=NS(ViewObject=NS(RootNode=root))
    temp=NS(Name='Temporary',addObject=lambda *args:obj,recompute=lambda:None)
    def new_document(name,**options):
        assert options=={'hidden':True,'temp':True};return temp
    n.owner.App.newDocument=new_document;n.owner.App.closeDocument=lambda name:closed.append(name)
    assert NATIVE_GEOMETRY(n.owner,n.mesh,[477]) is geometry
    assert bodies[0].nodes=={i:(float(i),0.,0.) for i in range(1,5)}
    assert bodies[0].volumes=={477:[1,2,3,4]} and closed==['Temporary']
