"""Native API protocol doubles. NO CAD kernel, real FCStd reader or solver.

ZIP handling uses the real .caepre packager, but the FCStd member's object reader
is explicitly replaced by an in-memory snapshot double. Do not call this a
FreeCAD execution, a native mesh test, or a cold-process geometry test.
"""
from copy import deepcopy
from contextlib import contextmanager
import hashlib
import itertools
import json
import math
from pathlib import Path
from types import SimpleNamespace as NS
import uuid
import zipfile

from apps.desktop_pre import metadata
from apps.desktop_pre.motion import Motion, _pose
from apps.desktop_pre.motion_history import pose_product, rotate_vector, pack_poses, POSE_SCHEMA
from apps.desktop_pre.motion_occurrence import unique_path
from apps.desktop_pre.projects import Project
from apps.desktop_pre.assembly_pose_geometry import IDENTITY

class Vector:
    def __init__(self, x=0., y=0., z=0.): self.x, self.y, self.z = x,y,z

class Rotation:
    def __init__(self, *q): self.Q = q or (0.,0.,0.,1.)

class Placement:
    def __init__(self, base=None, rotation=None): self.Base,self.Rotation=base or Vector(),rotation or Rotation()
    def copy(self): return deepcopy(self)
    def multiply(self,other): return pose(pose_product(_pose(self),_pose(other)))
    def inverse(self):
        q=self.Rotation.Q; qi=[-q[0],-q[1],-q[2],q[3]]
        xyz=rotate_vector(qi,[-self.Base.x,-self.Base.y,-self.Base.z])
        return pose(xyz+qi)


def pose(value): return Placement(Vector(*value[:3]),Rotation(*value[3:]))

def _points_equal(first, second):
    return len(first) == len(second) and all(any(
        max(abs(a-b) for a,b in zip(p,q)) < 1.e-9 for q in second) for p in first)


def _bounds(points):
    return NS(**{axis+end: fn(p[i] for p in points)
                 for i,axis in enumerate(('X','Y','Z'))
                 for end,fn in (('Min',min),('Max',max))})


class BooleanResult:
    """Controlled protocol result only. The optional OCC tests use real Booleans."""
    def __init__(self, volume=0., area=0.): self.Volume,self.Area=volume,area
    def isNull(self): return self.Volume == 0. and self.Area == 0.
    def isValid(self): return True


class Face:
    def __init__(self, shape, axis, side): self.shape,self.axis,self.side=shape,axis,side
    @property
    def points(self):
        local = list(itertools.product(*[(self.side*self.shape.size[i],) if i == self.axis
                                        else (0.,self.shape.size[i]) for i in range(3)]))
        return [self.shape.transform(p) for p in local]
    @property
    def Area(self): return math.prod(v for i,v in enumerate(self.shape.size) if i != self.axis)
    @property
    def CenterOfMass(self): return Vector(*(sum(p[i] for p in self.points)/4 for i in range(3)))
    @property
    def BoundBox(self): return _bounds(self.points)
    @property
    def Surface(self): return NS(kind='Plane')
    def exportBrepToString(self):
        return json.dumps([self.shape.text,self.axis,self.side,self.points])
    def common(self, other):
        return BooleanResult(area=self.Area if self.shape.text == other.shape.text
                             and _points_equal(self.points, other.points) else 0.)


class Shape:
    """Representation-aware cuboid DOUBLE, not an OpenCASCADE geometry oracle.

    Outer and embedded transformations serialize differently. Binder is an
    identity-outer Compound retaining its child's world transform. cut/common
    implement a deliberately limited exact-box protocol. Actual kernel coverage
    is separate in test_assembly_pose_kernel.py, never simulated by this class.
    """
    def __init__(self, text='editable-box'):
        self.text,self.Placement=text,Placement()
        self.embedded=Placement();self.size=(12.,8.,6.);self.ShapeType='Solid'
    def copy(self,*args): return deepcopy(self)
    def isNull(self): return False
    def isValid(self): return True
    def transform(self,point):
        p=self.Placement.multiply(self.embedded)
        v=rotate_vector(p.Rotation.Q,list(point))
        return [v[0]+p.Base.x,v[1]+p.Base.y,v[2]+p.Base.z]
    @property
    def points(self): return [self.transform(p) for p in itertools.product(*[(0.,v) for v in self.size])]
    @property
    def Solids(self):
        result=self.copy();result.ShapeType='Solid';return [result]
    @property
    def Faces(self): return [Face(self,axis,side) for axis in range(3) for side in (0,1)]
    @property
    def Edges(self): return [NS() for _ in range(12)]
    @property
    def Vertexes(self): return [NS(Point=Vector(*p)) for p in self.points]
    @property
    def BoundBox(self): return _bounds(self.points)
    @property
    def Volume(self): return math.prod(self.size)
    def cut(self, other):
        return BooleanResult(volume=0. if self.text == other.text and _points_equal(self.points,other.points)
                             else self.Volume)
    def exportBrepToString(self):
        return json.dumps([self.text,_pose(self.Placement),_pose(self.embedded),self.size,self.ShapeType])
    def importBrepFromString(self,text):
        self.text,outer,inner,self.size,self.ShapeType=json.loads(text)
        self.Placement=pose(outer);self.embedded=pose(inner)


def compound(shape):
    result=shape.copy();result.embedded=result.Placement.multiply(result.embedded)
    result.Placement=Placement();result.ShapeType='Compound'
    return result

class Object:
    def __init__(self,doc,kind,name):
        self.Document,self.TypeId,self.Name,self.Label=doc,kind,name,name
        self.PropertiesList=[];self._types={};self.Group=[];self.Placement=Placement()
        self.ViewObject=NS(Visibility=True);self.ExpressionEngine=[];self.Offset=0.
    @property
    def OutList(self): return self.Group
    def addProperty(self,kind,name,*args,**kw):
        self.PropertiesList.append(name);self._types[name]=kind;setattr(self,name,'')
    def setEditorMode(self,*args): pass
    def getTypeIdOfProperty(self,name): return self._types[name]
    def isDerivedFrom(self,kind):
        return kind==self.TypeId or kind=='Part::Feature' and self.TypeId in ('Part::Box','PartDesign::SubShapeBinder')
    def addObject(self,obj):
        if obj not in self.Group: self.Group.append(obj)
    def setLink(self,obj): self.LinkedObject=obj;self.LinkTransform=False
    def getLinkedObject(self): return self.LinkedObject
    def getTypeOfProperty(self,name):
        return ['ReadOnly','Output','NoRecompute'] if name=='CAELabMeshSourceBinding' else []
    def getGlobalPlacement(self): return self.Placement.copy()
    def getParentGeoFeatureGroup(self): return None
    def recompute(self):
        if self.TypeId=='PartDesign::SubShapeBinder': self.Shape=compound(get_shape(self.Support[0][0]))
        return True
    def getPlacementOf(self,path,obj):
        value=self.Placement.copy(); current=self
        for name in path.rstrip('.').split('.') if path else []:
            current=next(item for item in current.Group if item.Name==name)
            value=value.multiply(current.Placement)
        assert current is obj
        return value

class Document:
    def __init__(self,App,name):
        self._app=App;self.Name=self.Label=name;self.FileName='';self.Objects=[];self.OutList=[]
        self.Restoring=self.Importing=False;self.UndoMode=1;self.recomputes=0
    def __deepcopy__(self,memo):
        result=type(self)(self._app,self.Name);memo[id(self)]=result
        for key,value in vars(self).items():
            if key!='_app': setattr(result,key,deepcopy(value,memo))
        return result
    def addObject(self,kind,name):
        stem=name;i=1
        while self.getObject(name): name=stem+str(i);i+=1
        obj=Object(self,kind,name);self.Objects.append(obj);return obj
    def getObject(self,name): return next((obj for obj in self.Objects if obj.Name==name),None)
    def copyObject(self,objects,recursive=False):
        assert recursive is True
        result=[]
        for source in objects:
            clone=self.addObject(source.TypeId,source.Name);clone.Label=source.Label
            clone.Shape=source.Shape.copy();result.append(clone)
        return tuple(result)
    def recompute(self):
        self.recomputes+=1
        for obj in self.Objects: obj.recompute()
    def saveCopy(self,path):
        token=uuid.uuid4().hex
        self._app.snapshots[token]=deepcopy(self)
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('Document.xml','<Document><Objects/></Document>')
            z.writestr('DOUBLE-NOT-NATIVE.txt',token)

class Preferences:
    def __init__(self): self.data={}
    def GetContents(self): return [('Boolean',key,value) for key,value in self.data.items()]
    def SetBool(self,key,value): self.data[key]=value
    def RemBool(self,key): self.data.pop(key,None)

class App:
    Vector,Rotation,Placement=Vector,Rotation,Placement
    def __init__(self): self.documents={};self.snapshots={};self.preferences=Preferences();self.ActiveDocument=None
    def newDocument(self,name):
        stem=name;i=1
        while name in self.documents: name=stem+str(i);i+=1
        doc=Document(self,name);self.documents[name]=doc;self.ActiveDocument=doc;return doc
    def listDocuments(self): return dict(self.documents)
    def closeDocument(self,name):
        old=self.documents.pop(name)
        if old is self.ActiveDocument:self.ActiveDocument=None
    def openDocument(self,path):
        with zipfile.ZipFile(path) as z: token=z.read('DOUBLE-NOT-NATIVE.txt').decode()
        doc=deepcopy(self.snapshots[token]);stem=doc.Name;i=1
        while doc.Name in self.documents:doc.Name=stem+str(i);i+=1
        doc.FileName=str(path);self.documents[doc.Name]=doc;self.ActiveDocument=doc;return doc
    def setActiveDocument(self,name): self.ActiveDocument=self.documents[name]
    def ParamGet(self,path):return self.preferences


def get_shape(obj,subname=None,transform=True):
    current=obj
    if subname:
        for name in subname.rstrip('.').split('.'):
            current=next(item for item in current.Group if item.Name==name)
        world=obj.getPlacementOf(subname,current)
    else: world=obj.Placement
    source=current.LinkedObject if current.TypeId=='App::Link' else current
    shape=source.Shape.copy()
    shape.Placement=world.multiply(source.Placement.inverse()).multiply(shape.Placement)
    return shape

class MotionDouble:
    _assert_editor_applied=Motion._assert_editor_applied
    _replay_geometry=Motion._replay_geometry
    _replay_identity=Motion._replay_identity
    _joint_records=Motion._joint_records
    def __init__(self,owner):
        self.owner=owner;self._base=[];self._last={};self._preview=False;self._timer=None
        self._expected_generation=owner.generation;self._state='CALCULATED'
    def _parts(self,root):
        result=[]
        def walk(obj):
            for child in obj.Group:
                if child.TypeId in ('App::Link','Assembly::AssemblyLink'):
                    result.append(child);walk(child)
        walk(root);return result
    def _joints(self,root):
        return [obj for obj in self.owner.doc.Objects if obj.TypeId=='TestJoint']
    def _assembly(self,target):return self.owner._object(target['assembly_id'])
    def _saved_result(self,root,key):return self.owner.read_metadata()['motion_paths'][key]
    def _scene(self,root):
        return repr((self._replay_identity(root),self._joint_records(root)))
    def _metadata(self,root):return {},None
    def _native_definition(self,sim):return {'fixture':'recorded-native-output-double'}

class Owner:
    def __init__(self,doc,export_root,*,App=None,Gui=None):
        self.App,self.Gui,self.doc=App,Gui,doc;self.export_root=Path(export_root)
        self.document_id=metadata.read(doc).get('document_id','Psource')
        self.generation=0;self.saved_generation=None;self.closed=False;self.recovery_error=None
        self.motion=MotionDouble(self);self.fem=NS(_pending={})
        self.mesh_bindings=NS(track=lambda obj:None);self.project=Project(self)
        self.project.attach_opened()
    def assert_thread(self):pass
    def _object(self,name):
        obj=self.doc.getObject(name)
        if obj is None:raise ValueError('missing object')
        return obj
    def read_metadata(self):return metadata.read(self.doc)
    def write_metadata(self,value):metadata.write(self.doc,value)
    def before_design_action(self,reason):
        if self.motion._preview: raise AssertionError('source preview must never be restored')
    def _transaction(self,title,fn):fn();self.doc.recompute();self.generation+=1
    def close(self):self.closed=True


def source_fixture(tmp_path,monkeypatch):
    import sys
    from apps.desktop_pre import bridge
    App_=App();Gui=NS(getDocument=lambda name:NS(getInEdit=lambda:False))
    monkeypatch.setitem(sys.modules,'Part',NS(getShape=get_shape))
    monkeypatch.setitem(sys.modules,'FreeCAD',App_)
    def analysis(doc,name):return doc.addObject('Fem::FemAnalysis',name)
    def mesh(doc,name):
        obj=doc.addObject('Fem::FemMeshObjectPython',name);obj.FemMesh=NS();return obj
    def material(doc,name):
        obj=doc.addObject('App::MaterialObjectPython',name);obj.References=[];return obj
    monkeypatch.setitem(sys.modules,'ObjectsFem',NS(makeAnalysis=analysis,
        makeSolverCalculiXCcxTools=lambda doc,name:doc.addObject('Fem::FemSolverObjectPython',name),
        makeMeshGmsh=mesh,makeMaterialSolid=material))
    monkeypatch.setattr(bridge,'Owner',Owner)
    doc=App_.newDocument('Source');owner=Owner(doc,tmp_path/'exchange',App=App_,Gui=Gui)
    root=doc.addObject('Assembly::AssemblyObject','Assembly');root.Label='조립';root.Parents=[]
    outer=doc.addObject('Assembly::AssemblyLink','Outer');outer.Label='가동 모듈';outer.Rigid=False
    inner=doc.addObject('Assembly::AssemblyLink','Inner');inner.Label='가동 모듈';inner.Rigid=False
    root.addObject(outer);outer.addObject(inner)
    part=doc.addObject('Part::Box','Box');part.Shape=Shape()
    a=doc.addObject('App::Link','RepeatA');a.Label='반복';a.setLink(part);inner.addObject(a)
    b=doc.addObject('App::Link','RepeatB');b.Label='반복';b.setLink(part);inner.addObject(b)
    for name,kind in [('Ground','ground'),('Slide1','slide'),('Slide2','slide')]:
        joint=doc.addObject('TestJoint',name);root.addObject(joint)
        if kind=='ground':joint.ObjectToGround=a
        else:
            joint.JointType='Slider';joint.Reference1=(a,['','']);joint.Reference2=(b,['',''])
    identity=owner.motion._replay_identity(root)
    values={'Assembly':IDENTITY,'Outer':[10.,2.,3.,0.,0.,.7071067811865475,.7071067811865476],
            'Inner':[4.,0.,0.,.7071067811865475,0.,0.,.7071067811865476],
            'RepeatA':[1.,0.,0.,0.,0.,0.,1.],'RepeatB':[0.,2.,0.,0.,0.,0.,1.]}
    payload={'schema':POSE_SCHEMA,'calculation_id':'Kfixture','assembly_id':root.Name,**identity,
        'frame_times':[None,0.,.5],'clock':'fixture-output','design':[IDENTITY[:] for _ in identity['bindings']],
        'frames':[[IDENTITY[:] for _ in identity['bindings']]]+[
            [values[row['id']][:] for row in identity['bindings']] for _ in range(2)],
        'world_roots':[IDENTITY[:],[100.,20.,-3.,0.,0.,0.,1.],[100.,20.,-3.,0.,0.,0.,1.]]}
    result={'id':'Kfixture','assembly_id':root.Name,'accepted':True,'frame_count':3,
        'frame_times':payload['frame_times'],'clock':payload['clock'],'poses':pack_poses(payload,3),
        'attempt_id':'Afixture','definition_snapshot':{},'native_definition':owner.motion._native_definition(None)}
    metadata.write(doc,{'motion_paths':{'Kfixture':result},'motion_attempts':[{
        'id':'Afixture','result_id':'Kfixture','model':{'joints':owner.motion._joint_records(root)}}]})
    return owner,root,payload
