"""Author one declared TR-U receiver in FreeCAD, without a solver call.

Invoked only by the bounded Windows check after its declaration is accepted.
The real owner captures its mesh/selection/material through existing collect;
this helper does not write a snapshot manifest or an input deck.
"""
from pathlib import Path
import json
import os
import traceback


def author(declaration_path, output):
    import FreeCAD as App
    import FreeCADGui as Gui
    import Part, Fem, ObjectsFem
    from PySide import QtCore
    from apps.desktop_pre.bridge import Owner
    from apps.desktop_pre.assembly_pose_candidate import _hold, _release
    from apps.desktop_pre.freeze_contact import collect
    from caelab.storage import canonical_hash

    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    declaration=json.loads(Path(declaration_path).read_text(encoding='utf-8'))
    recorded=declaration.pop('declaration_sha256')
    if canonical_hash(declaration)!=recorded:
        raise ValueError('The bounded receiver declaration changed before native authoring.')
    receiver=declaration['receiver'];owner=None;doc=None
    receipt={'pid':os.getpid(),'declaration_sha256':recorded,'solver_executions':0}
    try:
        doc=App.newDocument('StructuralTransferReceiver');doc.Label='변위 전달 수신 시험편';_hold(doc)
        points=dict(zip(receiver['node_ids'],receiver['coordinates']))
        vector=lambda n:App.Vector(*points[n])
        faces=[Part.Face(Part.makePolygon([vector(n) for n in (*ids,ids[0])]))
               for ids in ((1,3,2),(1,2,4),(2,3,4),(3,1,4))]
        solid=Part.makeSolid(Part.makeShell(faces))
        if not solid.isValid() or len(solid.Solids)!=1:
            raise ValueError('The declared receiver must remain one valid native solid.')
        body=doc.addObject('PartDesign::Feature','Solid');body.Label='다른 C3D10 경계';body.Shape=solid
        analysis=ObjectsFem.makeAnalysis(doc,'Analysis')
        solver=ObjectsFem.makeSolverCalculiXCcxTools(doc,'Solver');analysis.addObject(solver)
        solver.AnalysisType='static';solver.ModelSpace='3D';solver.SplitInputWriter=False
        solver.GeometricalNonlinearity='linear';solver.MaterialNonlinearity='linear'
        # Native property uses seconds; the existing STATIC writer explicitly
        # records/consumes this as a dimensionless load parameter.
        solver.TimePeriod='1 s'
        material=ObjectsFem.makeMaterialSolid(doc,'Steel')
        material.Material={'Name':'등방 탄성재료','YoungsModulus':'210000 MPa','PoissonRatio':'0.3'}
        material.References=[(body,('Solid1',))];analysis.addObject(material)
        mesh=ObjectsFem.makeMeshGmsh(doc,'Mesh');mesh.Shape=body;native=Fem.FemMesh()
        for n,point in points.items():native.addNode(*point,n)
        for row in receiver['elements']:native.addVolume(row['native_node_ids'],row['element_id'])
        mesh.FemMesh=native;mesh.ElementOrder='2nd';mesh.ElementDimension='3D';analysis.addObject(mesh)
        boundary=ObjectsFem.makeConstraintFixed(doc,'TransferBoundary')
        boundary.Label='전달할 외곽 경계'
        boundary.References=[(body,tuple('Face'+str(i+1) for i in range(len(solid.Faces))))]
        analysis.addObject(boundary);doc.recompute()
        owner=Owner(doc,output/'exchange',App=App,Gui=Gui);owner.QtCore=QtCore
        owner.fem._record_condition(boundary,'explicit-native-selection')
        saved=owner.project.save(output/'receiver.caepre')
        doc.recompute()
        model,identity=collect(analysis,solver,owner.fem,capture_only=True)
        if (len(model['nodes'])!=35 or len(model['elements'])!=8
                or len(model['boundary_dofs'])!=102
                or {r['node_id'] for r in model['boundary_dofs']}!=set(range(1,35))
                or model['loads'] or model['contacts']):
            raise ValueError('Native receiver capture differs from the declared free-internal-node fixture.')
        # These are captured records, never an executable hand-written input.
        (output/'captured-model.json').write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8')
        (output/'captured-identity.json').write_text(json.dumps(identity,ensure_ascii=False,indent=2),encoding='utf-8')
        doc.saveAs(str(output/'receiver.FCStd'))
        body.Visibility=True;mesh.Visibility=False
        Gui.activeDocument().activeView().viewAxonometric();Gui.activeDocument().activeView().fitAll()
        Gui.Selection.clearSelection();Gui.Selection.addSelection(doc.Name,body.Name)
        Gui.updateGui();Gui.activeDocument().activeView().saveImage(str(output/'receiver-reference.png'),1000,760,'Current')
        receipt.update(status='PREPARED',native_version=list(App.Version()),saved=saved,
            captured_model_sha256=canonical_hash(model),boundary_object=boundary.Name,
            analysis_id=analysis.Name,solver_id=solver.Name,nodes=35,elements=8,
            boundary_dofs=102,free_internal_node_ids=[35],source_fields_copied=False)
    except Exception as error:
        receipt.update(status='FAILED',error=str(error),traceback=traceback.format_exc())
    finally:
        cleanup_errors=[]
        if owner is not None:
            try:owner.close()
            except Exception as error:cleanup_errors.append('owner: '+str(error))
        if doc is not None:
            try:_release(doc);App.closeDocument(doc.Name)
            except Exception as error:cleanup_errors.append('document: '+str(error))
        if cleanup_errors:receipt.update(status='FAILED',cleanup_errors=cleanup_errors)
        (output/'prepare-result.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        QtCore.QTimer.singleShot(0,Gui.getMainWindow().close)
    return receipt
