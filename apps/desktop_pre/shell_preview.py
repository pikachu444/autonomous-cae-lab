"""Transient Coin overlays inside the existing FreeCAD view, not a new viewer."""
import math
from caelab.shell_model import normal8, unit, shape8


def show(owner, mesh, *, previous=None):
    if owner.App.ActiveDocument is not owner.doc:
        raise ValueError('셸을 편집 중인 문서를 활성화한 뒤 미리보기를 여세요.')
    from pivy import coin
    view=owner.Gui.getDocument(owner.doc.Name).activeView()
    root=coin.SoSeparator()
    draw=coin.SoDrawStyle(); draw.lineWidth=2; root.addChild(draw)
    # All geometry remains in the native FemMesh display. At most 2000 elements
    # receive direction/offset overlays, avoiding an unbounded GUI allocation.
    stride=max(1,math.ceil(len(mesh['elements'])/2000))
    from caelab.shell_regions import element_values
    def polyline(points, color):
        sep=coin.SoSeparator(); material=coin.SoBaseColor()
        material.rgb=color; sep.addChild(material)
        coordinates=coin.SoCoordinate3(); coordinates.point.setValues(0,len(points),points)
        sep.addChild(coordinates)
        line=coin.SoLineSet(); line.numVertices=[len(points)]; sep.addChild(line)
        root.addChild(sep)
    for e in list(mesh['elements'])[::stride]:
        values=element_values(mesh,e)
        points=[mesh['nodes'][n] for n in mesh['elements'][e]]
        center=[sum(w*p[k] for w,p in zip(shape8(0,0),points)) for k in range(3)]
        n=mesh['normals'][e]; x=mesh['axes'][e][0]
        size=max(values['thickness_mm'], math.sqrt(mesh['areas_mm2'][e])*.25)
        polyline([center,[center[k]+size*n[k] for k in range(3)]],(.1,.45,.95))
        polyline([center,[center[k]+size*x[k] for k in range(3)]],(.15,.65,.2))
        for side,color in ((-.5,(.2,.65,.8)),(.5,(.95,.55,.15))):
            loop=[]
            natural=[]
            for a in range(9): natural.append((-1+2*a/8,-1))
            for a in range(1,9): natural.append((1,-1+2*a/8))
            for a in range(1,9): natural.append((1-2*a/8,1))
            for a in range(1,9): natural.append((-1,1-2*a/8))
            for r,s in natural:
                q=shape8(r,s); nn=unit(normal8(points,r,s))
                loop.append([sum(w*p[k] for w,p in zip(q,points))+
                             (side-values['offset'])*values['thickness_mm']*nn[k] for k in range(3)])
            polyline(loop,color)
    # Build before replacing so a failed preview does not destroy the last one.
    view.getSceneGraph().addChild(root)
    if previous is not None:
        old_view,old_root=previous
        old_view.getSceneGraph().removeChild(old_root)
    view.redraw()
    return view,root
