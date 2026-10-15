"""Create the editable single clamp with existing native FreeCAD/FEM tools."""
from pathlib import Path
import json,math,sys,time,uuid
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))


def create(output):
    import FreeCAD as App
    import FreeCADGui as Gui
    import ObjectsFem,FemGui
    from PySide import QtCore
    from apps.desktop_pre.bridge import Owner
    from apps.desktop_pre.assembly_pose_candidate import _hold,_release
    from caelab.storage import save_json
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('새 빈 저장 폴더를 선택하세요. 기존 모델과 결과는 덮어쓰지 않습니다.')
    doc=App.newDocument('CurvedClampFEM');doc.Label='곡면 클램프 정적 해석';_hold(doc)
    owner=None
    try:
        outer=doc.addObject('Part::Cylinder','ClampStock');outer.Label='클램프 외경'
        outer.Radius=8;outer.Height=14
        bore=doc.addObject('Part::Cylinder','ClampBore');bore.Label='관통 구멍'
        bore.Radius=2.5;bore.Height=14
        body=doc.addObject('Part::Cut','Clamp');body.Label='구멍 있는 곡면 클램프'
        body.Base=outer;body.Tool=bore;doc.recompute()
        analysis=ObjectsFem.makeAnalysis(doc,'Analysis')
        solver=ObjectsFem.makeSolverCalculiXCcxTools(doc,'SolverCcx');analysis.addObject(solver)
        solver.AnalysisType='static';solver.GeometricalNonlinearity='linear';solver.MaterialNonlinearity='linear'
        mesh=ObjectsFem.makeMeshGmsh(doc,'ClampMesh');mesh.Shape=body;analysis.addObject(mesh)
        material=ObjectsFem.makeMaterialSolid(doc,'ClampMaterial');material.Material={'Name':'ClampIsotropicExample'};analysis.addObject(material)
        doc.recompute();owner=Owner(doc,output/'exchange',App=App,Gui=Gui);owner.QtCore=QtCore
        fem=owner.fem
        fem.dispatch('pre.fem.material_set',{'young_modulus':210000.,'poisson_ratio':.3,'unit':'MPa'},{'object_id':material.Name})
        fem.dispatch('pre.fem.mesh_settings',{'min_size':1.5,'max_size':2.5,'unit':'mm','element_type':'C3D10'},{'object_id':mesh.Name})
        planes=[(i,face) for i,face in enumerate(body.Shape.Faces,1) if face.Surface.__class__.__name__=='Plane']
        bottom=min(planes,key=lambda row:row[1].CenterOfMass.z)[0]
        top=max(planes,key=lambda row:row[1].CenterOfMass.z)[0]
        assert bottom!=top
        for name,index,kind in [('아랫면 고정',bottom,'Fixed'),('윗면 축력',top,'Force')]:
            region=fem.dispatch('pre.fem.region_set',{'label':name,'subelements':['Face'+str(index)]},{'object_id':body.Name})
            args={'region_id':region['id'],'kind':kind}
            if kind=='Force':args.update(force=100.,unit='N',direction_region_id=None,reversed=True)
            fem.dispatch('pre.fem.condition_set',args,{'object_id':analysis.Name})
        FemGui.setActiveAnalysis(analysis)
        pending=fem.dispatch('pre.fem.mesh_generate',{}, {'object_id':mesh.Name})
        deadline=time.monotonic()+90
        while fem._pending and time.monotonic()<deadline:
            QtCore.QCoreApplication.processEvents();time.sleep(.02)
        if fem._pending:
            fem.dispatch('pre.fem.mesh_cancel',{'history_id':pending['history_id']},{'object_id':mesh.Name})
            raise RuntimeError('메시 생성 완료를 확인하지 못했습니다. 원자료와 취소 기록을 확인하세요.')
        history=next(r for r in fem._metadata()['mesh_history'] if r['id']==pending['history_id'])
        if history['state']!='SUCCEEDED':raise RuntimeError(str(history))
        owner.mesh_bindings.validate(mesh)
        assert mesh.FemMesh.VolumeCount>0
        saved=owner.project.save(output/'curved-clamp.caepre')
        owner.refresh()
        reply=owner.dispatch({'command_id':'C'+uuid.uuid4().hex,'document_id':owner.document_id,
            'session_id':owner.session_id,'expected_generation':owner.generation,'operation':'pre.freeze',
            'arguments':{'analysis_id':analysis.Name,'solver_id':solver.Name},'target':{}})
        if reply.get('status')!='COMPLETED':raise RuntimeError(str(reply))
        snapshot=owner.export_root/reply['result']['snapshot_relative']
        native_loads=json.loads((snapshot.parent/'mesh.json').read_text(encoding='utf-8'))['loads']
        load_sum=[math.fsum(row['force_N'] for row in native_loads if row['component']==axis) for axis in (1,2,3)]
        result={'state':'FROZEN','project':saved,'reply':reply,'export_root':str(owner.export_root),
            'body':body.Name,'bottom_face':'Face'+str(bottom),'top_face':'Face'+str(top),
            'force_N':100.,'nominal_force_N':100.,'native_nodal_load_sum_N':load_sum,
            'direction':'native top-face normal reversed',
            'mesh_nodes':len(mesh.FemMesh.Nodes),'mesh_volumes':mesh.FemMesh.VolumeCount,
            'solver_execution':'NOT_PERFORMED','motion_required':False}
        save_json(output/'fem-result.json',result)
        App.setActiveDocument(doc.Name);Gui.activeDocument().activeView().viewAxonometric();Gui.activeDocument().activeView().fitAll()
        return result
    except Exception as error:
        if owner is not None:
            try:owner.project.save(output/'fem-failed.caepre')
            except Exception:pass
        save_json(output/'fem-result.json',{'state':'FAILED','error':str(error),'solver_execution':'NOT_PERFORMED'})
        raise
    finally:
        if owner is not None:owner.close()
        _release(doc)


def main():
    import FreeCADGui as Gui
    from PySide import QtGui
    try:from PySide import QtWidgets
    except ImportError:QtWidgets=QtGui
    folder=QtWidgets.QFileDialog.getExistingDirectory(Gui.getMainWindow(),'곡면 클램프 해석 저장 폴더')
    if folder:create(folder)


if __name__=='__main__':main()
