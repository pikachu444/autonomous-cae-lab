"""Editable native FreeCAD 1.1.4 beam generator; no solver approximation.

Run from the product FreeCAD Python console or CreateBeam.FCMacro. Geometry is
an editable Sketcher line; the explicit Seg3 mesh is real Fem.FemMesh. Editing
the sketch does not silently regenerate this mesh: explicitly rebuild/rebind.
"""
from copy import deepcopy
from pathlib import Path
import math
import uuid

CASES={
    'end_force':'끝 힘 -1 N (전체 Z)',
    'moment_1':'순수 굽힘 1000 Nmm (전체 Y / 단면 1축)',
    'moment_2':'순수 굽힘 1000 Nmm (전체 Z / 단면 2축)',
    'section_90':'단면 90° · 전체 Y 모멘트 유지',
    'rotation':'고정 끝 Y 회전 0.01° 지정',
    'zero_draft':'폭 0인 초안 저장 · 계산 차단',
    'oblique_torsion':'비축정렬 비틀림 · 진단 전용',
}


def create(case='moment_1',*,output_root=None,segments=10,attach=True):
    import FreeCAD as App
    import FreeCADGui as Gui
    import Part,Sketcher,Fem,ObjectsFem
    from apps.desktop_pre.bridge import Owner
    from apps.desktop_pre import cae_prep
    if list(map(str,App.Version()[:3]))!=['1','1','4']:
        raise RuntimeError('This example is pinned to FreeCAD 1.1.4; no native version substitution')
    if case not in CASES or type(segments) is not int or not 2<=segments<=1000:
        raise ValueError('Select a named beam case and 2..1000 Seg3 elements')
    direction=[.7,1.4,-2.] if case=='oblique_torsion' else [1.,0.,0.]
    size=math.hypot(*direction);direction=[v/size for v in direction];length=1000.
    doc=App.newDocument('Beam_'+case+'_'+uuid.uuid4().hex[:6]);doc.Label=CASES[case]
    doc.UndoMode=1
    sketch=doc.addObject('Sketcher::SketchObject','BeamLine');sketch.Label='빔 중심선 · 1000 mm'
    i=sketch.addGeometry(Part.LineSegment(App.Vector(0,0,0),App.Vector(length,0,0)),False)
    sketch.addConstraint(Sketcher.Constraint('Coincident',i,1,-1,1))
    sketch.addConstraint(Sketcher.Constraint('Distance',i,length))
    sketch.addConstraint(Sketcher.Constraint('Horizontal',i))
    # Sketch geometry stays in its native plane. Its actual Placement defines
    # the global oblique edge; the real Seg3 mesh uses those global coordinates.
    if case=='oblique_torsion':
        sketch.Placement=App.Placement(App.Vector(0,0,0),App.Rotation(App.Vector(1,0,0),App.Vector(*direction)))
    analysis=ObjectsFem.makeAnalysis(doc,'BeamAnalysis')
    solver=ObjectsFem.makeSolverCalculiXCcxTools(doc,'BeamSolver');analysis.addObject(solver)
    for key,value in {'AnalysisType':'static','GeometricalNonlinearity':'linear','MaterialNonlinearity':'linear',
                      'ModelSpace':'3D','ExcludeBendingStiffness':False,'BeamReducedIntegration':True}.items():
        setattr(solver,key,value)
    native=Fem.FemMesh()
    # Non-consecutive labels make accidental ID arithmetic observable.
    ids=[101+7*j for j in range(2*segments+1)]
    for j,n in enumerate(ids):native.addNode(*[length*j/(2*segments)*v for v in direction],n)
    for j in range(segments):native.addEdge([ids[2*j],ids[2*j+2],ids[2*j+1]],1001+11*j)
    mesh=doc.addObject('Fem::FemMeshObject','BeamMesh');mesh.Label='선 메시 · Seg3 / B32R'
    mesh.FemMesh=native
    if 'Shape' not in mesh.PropertiesList:mesh.addProperty('App::PropertyLink','Shape','Mesh')
    mesh.Shape=sketch;analysis.addObject(mesh);doc.recompute()
    connection=getattr(cae_prep,'CONNECTION',None) if attach else None
    if connection is not None:
        connection.tick();owner=connection.active_owner()
        if owner.doc is not doc:raise RuntimeError('Existing native owner does not point to this document')
    else:
        output_root=Path(output_root or (Path.home()/'CAEBeamExamples')).absolute()
        owner=Owner(doc,output_root,App=App,Gui=Gui)
    info=owner.beam.create({'analysis_id':analysis.Name,'mesh_id':mesh.Name,
                           'edge':{'object':sketch.Name,'subelement':'Edge1'}})
    d=deepcopy(info['record']['draft'])
    d['ends'][0].update(reference={'object':sketch.Name,'subelement':'Vertex1'},
                         translation_mm=['0']*3,rotation_deg=['0']*3)
    d['ends'][1]['reference']={'object':sketch.Name,'subelement':'Vertex2'}
    if case=='end_force':d['ends'][1]['force_N']=['0','0','-1']
    if case in ('moment_1','section_90','zero_draft'):d['ends'][1]['moment_Nmm']=['0','1000','0']
    if case=='moment_2':d['ends'][1]['moment_Nmm']=['0','0','1000']
    if case=='section_90':d['section']['rotation_deg']='90'
    if case=='rotation':d['ends'][0]['rotation_deg']=['0','0.01','0']
    if case=='oblique_torsion':
        d['diagnostic_oblique']=True;d['ends'][1]['system']='local';d['ends'][1]['moment_Nmm']=['0','0','1000']
    owner.beam.apply(analysis.Name,d)
    if case=='zero_draft':
        d=deepcopy(owner.beam.inspect(analysis.Name)['record']['draft']);d['section']['width_mm']='0'
        owner.beam.save_draft(analysis.Name,d)
    owner.project.save()
    mesh.ViewObject.Visibility=False;sketch.ViewObject.Visibility=True
    Gui.activeDocument().activeView().viewAxonometric();Gui.activeDocument().activeView().fitAll()
    if connection is not None:connection.show_panel('beam',owner=owner)
    return owner,analysis.Name


def run_macro():
    from PySide import QtGui
    try:from PySide import QtWidgets as W
    except ImportError:W=QtGui
    import FreeCADGui as Gui
    names=list(CASES)
    chosen,ok=W.QInputDialog.getItem(Gui.getMainWindow(),'빔 예제','조건',list(CASES.values()),0,False)
    if not ok:return
    return create(names[list(CASES.values()).index(chosen)])
