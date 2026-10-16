"""Public two-material laminate using the maintained eight-node plate mesh."""
from copy import deepcopy
from pathlib import Path

from examples.shell.generate_plate import grid
from caelab.composite_shell import PROFILE, default_draft
from caelab.adapters.composite_shell_deck import MESH_KIND


def model(nx=4,ny=2):
    nodes,elements,fixed=grid(80.,30.,nx,ny)
    draft=default_draft('LaminateAnalysis','ShellMesh','Solver')
    draft.update(elements=list(elements),fixed_nodes=fixed)
    draft['materials']={
        'Orthotropic':{'label':'직교이방성 층','law':'orthotropic_linear','constants':dict(zip(
            ('E1_MPa','E2_MPa','E3_MPa','nu12','nu13','nu23','G12_MPa','G13_MPa','G23_MPa'),
            ('130000','9000','9000','.28','.28','.35','5000','5000','3300')))},
        'Isotropic':{'label':'등방 탄성 층','law':'isotropic_linear','constants':{'E_MPa':'70000','nu':'.3'}}}
    draft['regions']=[{'id':'PlateRegion','label':'평판','elements':list(elements),'face_refs':[],
        'orientation':'native','axis':['1','0','0'],'offset':'.15','pressure_MPa':'.001',
        'plies':[{'id':'UpperPly','material_id':'Orthotropic','thickness_mm':'.7','angle_deg':'90'},
                 {'id':'LowerPly','material_id':'Isotropic','thickness_mm':'1.3','angle_deg':'0'}]}]
    text='*NODE\n'+''.join(str(n)+', '+', '.join(map(str,p))+'\n' for n,p in nodes.items())
    text+='*ELEMENT, TYPE=S8, ELSET=Eall\n'+''.join(str(e)+', '+', '.join(map(str,c))+'\n' for e,c in elements.items())
    return {'schema_version':'1','kind':MESH_KIND,'profile':PROFILE,'units':{'position':'mm','stress':'MPa','force':'N'},
        'source_nodes':{str(n):p for n,p in nodes.items()},'source_elements':{str(e):c for e,c in elements.items()},
        'native_mesh':text,'draft':draft,'applied':{'draft':deepcopy(draft),'native':{}},'fixed_nodes':fixed}


def create(destination):
    """Create a native FEM document, leaving explicit Apply and Run to the user."""
    import FreeCAD as App
    import FreeCADGui as Gui
    import Fem,ObjectsFem
    from apps.desktop_pre.composite_edit import MATERIAL_KEYS
    from apps.desktop_pre.shell_edit import SETTINGS
    if list(App.Version())[:3]!=['1','1','4'] or not App.GuiUp:raise ValueError('Use FreeCAD 1.1.4 GUI')
    path=Path(destination).absolute()
    if path.exists() or path.suffix.lower()!='.fcstd':raise ValueError('Choose a new FCStd file')
    path.parent.mkdir(parents=True,exist_ok=True)
    values=model();nodes,elements,fixed=grid(80.,30.,4,2)
    doc=App.newDocument('LaminatePlate');doc.Label='두 재료 적층 평판'
    plate=doc.addObject('Part::Plane','Plate');plate.Length=80.;plate.Width=30.;doc.recompute()
    mesh=doc.addObject('Fem::FemMeshObject','ShellMesh');mesh.addProperty('App::PropertyLink','Shape','FEM');mesh.Shape=plate
    fem=Fem.FemMesh()
    for n,xyz in nodes.items():fem.addNode(*xyz,n)
    for e,conn in elements.items():fem.addFace(conn,e)
    mesh.FemMesh=fem
    analysis=ObjectsFem.makeAnalysis(doc,'LaminateAnalysis');analysis.Label='적층 평판 굽힘';analysis.addObject(mesh)
    solver=ObjectsFem.makeSolverCalculiXCcxTools(doc);analysis.addObject(solver)
    for key,value in SETTINGS.items():setattr(solver,key,value)
    materials={}
    for name,record in values['draft']['materials'].items():
        obj=ObjectsFem.makeMaterialSolid(doc,name);obj.Label=record['label']
        obj.Material={'Name':record['label'],'CAELabLinearLaw':record['law'],
            **{MATERIAL_KEYS[k]:v+(' MPa' if k.endswith('_MPa') else '') for k,v in record['constants'].items()}}
        obj.References=[];analysis.addObject(obj);materials[name]=obj.Name
    support=ObjectsFem.makeConstraintFixed(doc);support.Label='왼쪽 모서리 고정'
    edges=['Edge'+str(i) for i,e in enumerate(plate.Shape.Edges,1) if all(abs(v.Point.x)<1e-9 for v in e.Vertexes)]
    if len(edges)!=1:raise ValueError('Actual left support edge is ambiguous')
    support.References=[(plate,tuple(edges))];analysis.addObject(support)
    doc.recompute();doc.saveAs(str(path));Gui.activeDocument().activeView().viewAxonometric();Gui.activeDocument().activeView().fitAll()
    Gui.Selection.clearSelection();Gui.Selection.addSelection(plate,'Face1')
    return doc,{'analysis_id':analysis.Name,'mesh_id':mesh.Name,'solver_id':solver.Name},materials
