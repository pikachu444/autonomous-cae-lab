"""Editable C3D10 examples using installed FreeCAD/Gmsh and existing Owner.

Run inside the installed FreeCAD Python console, not system Python. No solve is
performed here. This generator has NOT been run on the delivery host.
"""
from copy import deepcopy
from pathlib import Path
import json
import sys
import uuid


CASES = ('initial-velocity', 'preload-release', 'preload-hold')


def configure_draft(source, *, case, initial_target=None):
    """The exact draft used by generate(), testable with the real step compiler.

    Does not import FreeCAD, modify the supplied draft, apply it or run a solver.
    The target in the initial-velocity case must come from native capture.
    """
    from caelab.dynamic_model import continuation_step
    if case not in CASES:
        raise ValueError('Unknown explicit example case')
    draft = deepcopy(source)
    if case == 'initial-velocity':
        if not isinstance(initial_target, dict) or not initial_target.get('native_node_ids'):
            raise ValueError('Capture the actual tip-face nodes for initial velocity')
        draft['initial_conditions'] = [{'id': 'InitialV', 'label': '자유 끝 초기 속도',
            'kind': 'V', 'component': 3, 'value': '100', 'target': deepcopy(initial_target)}]
        first = draft['program']['steps'][0]
        first.update(id='Dynamic1', label='자유 진동 1', procedure='dynamic', duration='0.002')
        second = continuation_step(first, identifier='Dynamic2', label='자유 진동 2')
        draft['program'].update(procedure='dynamic', steps=[first, second])
    else:
        preload = draft['program']['steps'][0]
        preload.update(id='Preload', label='정적 선행하중', procedure='static',
            duration='1', initial='0.1', minimum='0.000001', maximum='0.1')
        for row in preload['curves']:
            row.update(mode='curve', points=[['0', '0'], ['1', '5']])
        dynamic = continuation_step(preload, identifier='Dynamic1',
            label='하중 해제' if case == 'preload-release' else '하중 유지')
        dynamic.update(duration='0.002', initial='0.00001',
            minimum='0.00000001', maximum='0.00001')
        for row in dynamic['curves']:
            row['mode'] = 'release' if case == 'preload-release' else 'hold'
        second = continuation_step(dynamic, identifier='Dynamic2')
        draft['program'].update(procedure='mixed', steps=[preload, dynamic, second])
    return draft


def generate(output, *, case='initial-velocity', gmsh=None):
    """Create a new folder and editable solid; preserve any prior example intact.

    case: initial-velocity | preload-release | preload-hold
    The beam-shaped geometry is a 3D SOLID, not a beam element or shell model.
    Mesh generation uses the installed FreeCAD 1.1.4 GmshTools implementation.
    """
    if case not in CASES:
        raise ValueError('Unknown explicit example case')
    for name in ('apps.desktop_pre.cae_prep','cae_prep'):
        module=sys.modules.get(name)
        if module is not None and getattr(module,'CONNECTION',None) is not None:
            raise ValueError('제품 Connection을 시작하지 않은 FreeCAD에서 예제를 만든 뒤 example.caepre를 여세요.')
    import FreeCAD as App
    import FreeCADGui as Gui
    import ObjectsFem
    import FemGui
    from femmesh.gmshtools import GmshTools
    from apps.desktop_pre.bridge import Owner
    root=Path(output).expanduser().absolute();root.mkdir(parents=True,exist_ok=False)
    doc=App.newDocument('DynamicSolid'+uuid.uuid4().hex[:8]);doc.Label='동해석 고체 — '+case
    owner=None
    try:
        body=doc.addObject('Part::Box','Solid');body.Label='편집 가능한 고체'
        body.Length='100 mm';body.Width='10 mm';body.Height='10 mm'
        analysis=ObjectsFem.makeAnalysis(doc,'Analysis')
        solver=ObjectsFem.makeSolverCalculiXCcxTools(doc,'Solver')
        solver.AnalysisType='static'  # Existing dedicated compiler owns procedure.
        solver.ModelSpace='3D';solver.SplitInputWriter=False;solver.GeometricalNonlinearity='linear'
        solver.AutomaticIncrementation=True;solver.MatrixSolverType='default'
        solver.IterationsControlParameterTimeUse=False
        solver.TimePeriod='0.004 s';solver.TimeInitialIncrement='0.00001 s'
        solver.TimeMinimumIncrement='0.00000001 s';solver.TimeMaximumIncrement='0.00001 s'
        solver.IncrementsMaximum=5000;analysis.addObject(solver)
        material=ObjectsFem.makeMaterialSolid(doc,'Material')
        material.Material=dict(material.Material,Name='Example steel (illustrative)',YoungsModulus='210000 MPa',
                               PoissonRatio='0.3',Density='7850 kg/m^3')
        material.References=[(body,['Solid1'])];analysis.addObject(material)
        doc.recompute()
        def plane(axis,value):
            found=[]
            for i,face in enumerate(body.Shape.Faces,1):
                bb=face.BoundBox
                if abs(getattr(bb,axis+'Min')-value)<1e-9 and abs(getattr(bb,axis+'Max')-value)<1e-9:found.append('Face'+str(i))
            if len(found)!=1:raise ValueError('Generated box has no unique expected face')
            return found[0]
        root_face,tip_face=plane('X',0.),plane('X',100.)
        fixed=ObjectsFem.makeConstraintFixed(doc,'Support');fixed.References=[(body,[root_face])];analysis.addObject(fixed)
        force=None
        if case!='initial-velocity':
            force=ObjectsFem.makeConstraintForce(doc,'Preload');force.References=[(body,[tip_face])]
            edges=[]
            for i,edge in enumerate(body.Shape.Edges,1):
                bb=edge.BoundBox
                if abs(bb.XMin-100.)<1e-9 and abs(bb.XMax-100.)<1e-9 and abs(bb.YMin)<1e-9 and abs(bb.YMax)<1e-9 and abs(bb.ZLength-10.)<1e-9:
                    edges.append('Edge'+str(i))
            if len(edges)!=1:raise ValueError('Generated box has no unique transverse force direction edge')
            force.Direction=(body,[edges[0]]);force.Reversed=True;force.Force='5 N';force.EnableAmplitude=False
            analysis.addObject(force)
        mesh=ObjectsFem.makeMeshGmsh(doc,'Mesh');mesh.Shape=body;mesh.ElementOrder='2nd';mesh.ElementDimension='3D'
        mesh.SecondOrderLinear=False;mesh.CharacteristicLengthMin='3 mm';mesh.CharacteristicLengthMax='5 mm'
        analysis.addObject(mesh);doc.recompute()
        preferences=App.ParamGet('User parameter:BaseApp/Preferences/Mod/Fem/Gmsh')
        previous=preferences.GetString('gmshBinaryPath')
        if gmsh is not None:
            executable=Path(gmsh).absolute()
            if not executable.is_file():raise ValueError('Choose the installed Gmsh executable')
            preferences.SetString('gmshBinaryPath',str(executable))
        try:
            tool=GmshTools(mesh);tool.obj.WorkingDirectory=str(root/'mesh');(root/'mesh').mkdir()
            tool.run(blocking=True)
            if tool.process.exitCode()!=0 or not mesh.FemMesh.NodeCount or not mesh.FemMesh.VolumeCount:
                raise ValueError('Native Gmsh did not produce an actual solid mesh')
        finally:
            if gmsh is not None:preferences.SetString('gmshBinaryPath',previous)
        doc.recompute();doc.saveAs(str(root/'editable.FCStd'))
        owner=Owner(doc,root/'exports',App=App,Gui=Gui)
        def bind():
            owner.fem._record_condition(fixed,None)
            if force is not None:owner.fem._record_condition(force,None)
        owner._transaction('예제의 정확한 native 조건 확인',bind);doc.recompute()
        if owner.fem.quality(mesh,limit=1)['bad_element_count']:raise ValueError('Generated mesh fails existing quality gates')
        owner.dynamic.create(analysis.Name,solver.Name)
        draft=owner.dynamic._get(analysis.Name)['draft']
        target=None
        if case=='initial-velocity':
            target=owner.dynamic.dispatch('pre.dynamic.capture',{'analysis_id':analysis.Name,'body_id':body.Name,
                'native_node_ids':None,'faces':[tip_face]}, {})['target']
        draft=configure_draft(draft,case=case,initial_target=target)
        info=owner.dynamic.apply(analysis.Name,draft)
        if not info['can_freeze']:raise ValueError(str(info['errors']))
        doc.recompute();saved=owner.project.save(str(root/'example.caepre'))
        info=owner.dynamic.dispatch('pre.dynamic.freeze',{'analysis_id':analysis.Name},{})
        manifest=owner.export_root/info['snapshot_relative']
        receipt={'case':case,'freecad_version':list(App.Version()),'project':str(root/'example.caepre'),
            'snapshot_path':str(manifest),'editable_file':str(root/'editable.FCStd'),
            'solver_execution':'NOT_PERFORMED','qualification':'UNKNOWN','decision':'NOT_RELEASED'}
        (root/'generator-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        FemGui.setActiveAnalysis(analysis);Gui.activeDocument().activeView().viewAxonometric();Gui.activeDocument().activeView().fitAll()
        return receipt
    except Exception as exc:
        (root/'generator-failure.txt').write_text(str(exc),encoding='utf-8')
        raise
    finally:
        # The document remains editable. The normal application may attach its
        # own existing Owner; do not retain a second live document observer.
        if owner is not None:owner.close()
