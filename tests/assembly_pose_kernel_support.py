"""TEST ONLY: FreeCAD-shaped access to installed OpenCASCADE/CadQuery.

No FreeCAD process, mesh, solver, healing, refinement or tessellation. This is
not a product dependency. Pure protocol tests do not import it; kernel tests
explicitly skip when CadQuery/OCP is absent. Geometry methods are real OCC ops.
"""
import io
import struct
import zipfile
import json
from types import SimpleNamespace as NS

import cadquery as cq
from OCP.BinTools import BinTools_ShapeSet
from OCP.TopAbs import TopAbs_Orientation
from OCP.gp import gp_Trsf, gp_Quaternion, gp_Vec
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Common

class KernelPlacement:
 def __init__(self,loc): self.loc=loc
 def multiply(self,other): return KernelPlacement(self.loc*other.loc)
 def inverse(self): return KernelPlacement(self.loc.inverse)


class KernelShape:
 def __init__(self,s):self.s=s
 def copy(self):return KernelShape(self.s.copy())
 @property
 def Placement(self):return KernelPlacement(self.s.location())
 @Placement.setter
 def Placement(self,value):self.s=self.s.located(value.loc)
 def isNull(self):return self.s.isNull()
 def isValid(self):return self.s.isValid()
 @property
 def Solids(self):return [KernelShape(x) for x in self.s.Solids()]
 @property
 def Faces(self):return [KernelShape(x) for x in self.s.Faces()]
 @property
 def Edges(self):return [KernelShape(x) for x in self.s.Edges()]
 @property
 def Vertexes(self):return [KernelShape(x) for x in self.s.Vertices()]
 @property
 def Volume(self):return self.s.Volume()
 @property
 def Area(self):return self.s.Area()
 @property
 def CenterOfMass(self):return self.s.Center()
 @property
 def Surface(self):return self.s.geomType()
 @property
 def BoundBox(self):
  from types import SimpleNamespace
  b=self.s.BoundingBox();return SimpleNamespace(XMin=b.xmin,YMin=b.ymin,ZMin=b.zmin,XMax=b.xmax,YMax=b.ymax,ZMax=b.zmax)
 def cut(self,b):
  op=BRepAlgoAPI_Cut(self.s.wrapped,b.s.wrapped)
  if not op.IsDone(): raise RuntimeError('OCC cut failed')
  return KernelShape(cq.Shape.cast(op.Shape()))
 def common(self,b):
  op=BRepAlgoAPI_Common(self.s.wrapped,b.s.wrapped)
  if not op.IsDone(): raise RuntimeError('OCC common failed')
  return KernelShape(cq.Shape.cast(op.Shape()))

def location(values):
    transform = gp_Trsf()
    transform.SetRotation(gp_Quaternion(*values[3:]))
    transform.SetTranslationPart(gp_Vec(*values[:3]))
    return cq.Location(transform)


def read_freecad_binary(raw):
    """Read the exact retained FreeCAD 1.1.4 binary shape, not a box recreation.

    FreeCAD TopoShape.cpp importBinary/exportBinary use BinTools_ShapeSet
    followed by three int32 values (shape id, location id, orientation).
    https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Part/App/TopoShape.cpp#L809-L826
    This differs from BinTools.Read's standalone shape trailer. OCP stream
    conversion buffers the Python stream, so separate the documented trailer
    before reading the shape set. Fixture byte order is Windows little-endian.
    """
    if not raw.startswith(b'\nOpen CASCADE Topology V3 (c)\n') or len(raw) < 12:
        raise ValueError('Not the retained FreeCAD binary shape format')
    shapes = BinTools_ShapeSet()
    shapes.Read(io.BytesIO(raw[:-12]))
    shape_id, location_id, orientation = struct.unpack('<iii', raw[-12:])
    if not 1 <= shape_id <= shapes.NbShapes() or location_id < 0 or orientation not in range(4):
        raise ValueError('Invalid FreeCAD binary shape reference')
    shape = shapes.Shape(shape_id)
    shape.Location(shapes.Locations().Location(location_id))
    shape.Orientation(TopAbs_Orientation(orientation))
    return KernelShape(cq.Shape.cast(shape))


def retained_shape(project, name):
    with zipfile.ZipFile(project) as archive:
        manifest = json.loads(archive.read('project.json'))
        with zipfile.ZipFile(io.BytesIO(archive.read(manifest['entry']))) as document:
            return read_freecad_binary(document.read(name+'.Shape.bin'))


def brep(shape):
    stream = io.BytesIO()
    shape.s.exportBrep(stream)
    return stream.getvalue()
