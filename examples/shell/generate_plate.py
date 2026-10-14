"""Deterministic native example, not a special case in the shell solver path.

Run create() in the installed FreeCAD GUI Python console. grid() is pure Python
so topology can be regression-tested without pretending FreeCAD was executed.
"""
import math
from pathlib import Path


def grid(length=100., width=40., nx=8, ny=4):
    if (type(nx) is not int or type(ny) is not int or nx<1 or ny<1 or nx*ny>100000
            or not math.isfinite(length) or not math.isfinite(width) or min(length,width)<=0):
        raise ValueError('Use finite positive dimensions and positive integer element counts')
    locations=set(); patches=[]
    for j in range(ny):
        for i in range(nx):
            x,y=2*i,2*j
            nodes=((x,y),(x+2,y),(x+2,y+2),(x,y+2),
                   (x+1,y),(x+2,y+1),(x+1,y+2),(x,y+1))
            locations.update(nodes); patches.append(nodes)
    numbering={p:i+1 for i,p in enumerate(sorted(locations,key=lambda p:(p[1],p[0])))}
    nodes={numbering[(x,y)]:[length*x/(2*nx),width*y/(2*ny),0.] for x,y in numbering}
    elements={i+1:[numbering[p] for p in conn] for i,conn in enumerate(patches)}
    fixed=sorted(numbering[p] for p in numbering if p[0]==0)
    return nodes,elements,fixed


def create(destination, *, length=100., width=40., nx=8, ny=4, thickness=2., offset=0., pressure=.001):
    import FreeCAD as App
    import FreeCADGui as Gui
    import Fem, FemGui, ObjectsFem
    from apps.desktop_pre.shell_edit import SETTINGS
    from caelab.shell_model import number
    if list(App.Version())[:3]!=['1','1','4'] or not App.GuiUp:
        raise ValueError('Use the installed FreeCAD 1.1.4 GUI, not a separate headless document')
    path=Path(destination).absolute()
    if path.suffix.lower()!='.fcstd' or path.exists(): raise ValueError('Choose a new .FCStd path')
    path.parent.mkdir(parents=True,exist_ok=True)
    if number(thickness)<=0 or not math.isfinite(offset) or not math.isfinite(pressure) or pressure==0:
        raise ValueError('Use positive thickness, finite offset and nonzero pressure')
    nodes,elements,fixed=grid(length,width,nx,ny)
    doc=App.newDocument('ShellPlate')
    plate=doc.addObject('Part::Plane','Plate'); plate.Label='편집 가능한 평판'
    plate.Length=length; plate.Width=width
    doc.recompute()
    fem=Fem.FemMesh()
    for n,xyz in nodes.items(): fem.addNode(*xyz,n)
    for e,conn in elements.items(): fem.addFace(conn,e)
    mesh=doc.addObject('Fem::FemMeshObject','ShellMesh'); mesh.Label='S8 판재 메시'
    if 'Shape' not in mesh.PropertiesList: mesh.addProperty('App::PropertyLink','Shape','FEM')
    mesh.Shape=plate; mesh.FemMesh=fem
    analysis=ObjectsFem.makeAnalysis(doc,'ShellAnalysis'); analysis.Label='판재 굽힘'
    analysis.addObject(mesh)
    solver=ObjectsFem.makeSolverCalculiXCcxTools(doc); analysis.addObject(solver)
    for key,value in SETTINGS.items(): setattr(solver,key,value)
    material=ObjectsFem.makeMaterialSolid(doc); material.Label='등방 탄성 강재'
    material.Material={'Name':'Example isotropic steel','YoungsModulus':'210000 MPa','PoissonRatio':'0.3'}
    material.References=[]; analysis.addObject(material)
    section=ObjectsFem.makeElementGeometry2D(doc,thickness); section.Label='판재 단면'
    section.Offset=offset; section.References=[(plate,('Face1',))]; analysis.addObject(section)
    load=ObjectsFem.makeConstraintPressure(doc); load.Label='판재 압력'
    load.Pressure=str(abs(pressure))+' MPa'; load.Reversed=pressure<0; load.EnableAmplitude=False
    load.References=[(plate,('Face1',))]; analysis.addObject(load)
    left=[]
    for i,edge in enumerate(plate.Shape.Edges,1):
        if all(abs(v.Point.x)<=1e-10*length for v in edge.Vertexes): left.append('Edge'+str(i))
    if len(left)!=1: raise ValueError('Could not identify the example support edge; no fallback face is guessed')
    support=ObjectsFem.makeConstraintFixed(doc); support.Label='한쪽 모서리 고정'
    support.References=[(plate,tuple(left))]; analysis.addObject(support)
    doc.recompute(); doc.saveAs(str(path))
    Gui.activeDocument().activeView().viewAxonometric(); Gui.activeDocument().activeView().fitAll()
    FemGui.setActiveAnalysis(analysis); Gui.Selection.clearSelection(); Gui.Selection.addSelection(plate,'Face1')
    return doc
