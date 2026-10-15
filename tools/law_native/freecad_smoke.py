"""Run only inside a newly owned FreeCAD GUI process (invoked by the .FCMacro).

Real FreeCAD mesh/property/transaction/save/cold read acceptance. Never claims an
FE solve. Source was saved by the existing Material owner in the service Python.
"""
from pathlib import Path
from copy import deepcopy
import json,os,sys,traceback

def run():
    config_path=os.environ.get('CAELAB_LAW_SMOKE_CONFIG')
    token=os.environ.get('CAELAB_LAW_SMOKE_TOKEN')
    if not config_path or not token:raise RuntimeError('Owned smoke configuration/token required; no changes made')
    cfg=json.loads(Path(config_path).read_text(encoding='utf-8'))
    if token!=cfg['token']:raise RuntimeError('Wrong smoke process; no changes or quit allowed')
    import FreeCAD as App
    import FreeCADGui as Gui
    if App.listDocuments():raise RuntimeError('Refusing a process that already has native documents open')
    output=Path(cfg['output']);output.mkdir(parents=True,exist_ok=False)
    owner=doc=None
    report={'status':'STARTING','native':'ACTUAL_FREECAD_PROCESS','FE_execution':'NOT_RUN',
        'pid':os.getpid(),'FreeCAD_version':list(App.Version()),'python':sys.version,'mode':cfg['mode']}
    try:
        import ObjectsFem,Part,Fem
        from apps.desktop_pre.bridge import Owner
        from apps.desktop_pre import law_native_material as native
        from caelab import material_fe_transfer as transfer,law_native_fe as fe
        from caelab.storage import canonical_hash,save_json,load_json
        if cfg['mode']=='apply':
            doc=App.newDocument('LawNativeSpecimen');doc.UndoMode=1
            shape=doc.addObject('Part::Feature','Specimen');shape.Label='재료 법칙 공개 시편';shape.Shape=Part.makeBox(1.,1.,1.)
            analysis=ObjectsFem.makeAnalysis(doc,'Analysis')
            base=ObjectsFem.makeMaterialSolid(doc,'Material')
            base.Material={'Name':'Preserved original elastic placeholder','YoungsModulus':'210000 MPa','PoissonRatio':'0.3'}
            base.References=[(shape,('Solid1',))]
            solver=ObjectsFem.makeSolverCalculiXCcxTools(doc,'SolverContext')
            mesh=doc.addObject('Fem::FemMeshObject','SpecimenMesh')
            if 'Shape' not in mesh.PropertiesList:mesh.addProperty('App::PropertyLink','Shape')
            mesh.Shape=shape;frozen=fe.cube_mesh();fm=Fem.FemMesh()
            for i,p in enumerate(frozen['points'],1):fm.addNode(*p,i)
            for i,cell in enumerate(frozen['cells'],1):
                smesh=[0]*8
                for vtk,local in enumerate(native.SMESH_TO_VTK):smesh[local]=cell[vtk]+1
                fm.addVolume(smesh,i)
            mesh.FemMesh=fm
            for obj in (base,solver,mesh):analysis.addObject(obj)
            doc.recompute();owner=Owner(doc,output/'exports',App=App,Gui=Gui)
            region=owner.fem._region_set(shape,{'label':'전체 Solid1','subelements':['Solid1']})
            selection={'analysis_id':analysis.Name,'material_id':base.Name,'region_id':region['id'],
                       'mesh_id':mesh.Name,'solver_id':solver.Name}
            source=load_json(cfg['source']);options=fe.default_settings()
            options={'solver':options['solver'],'boundary':options['boundary'],'purpose':'CONSTITUTIVE_SPECIMEN'}
            original=deepcopy(base.Material)
            native.save(owner.fem,selection,{'unfinished_coefficient':'1e','options':options})
            before=canonical_hash(owner.read_metadata());generation=owner.generation
            review=transfer.make_review(source,native.capture(owner.fem,selection),options)
            assert canonical_hash(owner.read_metadata())==before and owner.generation==generation
            assert review['status']=='READY_FOR_EXPLICIT_APPLY',review['errors']
            receipt=native.apply(owner.fem,selection,review)
            assert base.Material==original and receipt['applied']
            frozen=native.freeze(owner.fem,selection);save_json(output/'frozen-simulation.json',frozen)
            # Actual native Undo/Redo, not a controlled transaction fixture.
            doc.undo();doc.recompute();assert native.read(owner.fem,selection)['assignment'] is None
            doc.redo();doc.recompute()
            restored=native.read(owner.fem,selection)['assignment']
            assert restored['assignment_sha256']==receipt['assignment']['assignment_sha256']
            target=output/'specimen.FCStd';doc.recompute();doc.saveAs(str(target))
            save_json(output/'selection.json',selection)
            report.update(status='PASS',assignment_sha256=restored['assignment_sha256'],
                preview_bytes_unchanged=True,original_native_material_unchanged=True,undo_redo='PASS',
                source_sha256=source['snapshot_sha256'],native_file=str(target))
        else:
            previous=Path(cfg['previous']);selection=load_json(previous/'selection.json')
            expected=load_json(previous/'receipt.json')
            doc=App.openDocument(str(previous/'specimen.FCStd'));owner=Owner(doc,output/'exports',App=App,Gui=Gui)
            assignment=native.read(owner.fem,selection)['assignment']
            assert assignment['assignment_sha256']==expected['assignment_sha256']
            assert assignment['review']['source']['snapshot_sha256']==expected['source_sha256']
            # Cold read deliberately does NOT require the old Material workspace paths.
            report.update(status='PASS',assignment_sha256=assignment['assignment_sha256'],
                          cold_read='ACTUAL_FRESH_NATIVE_PROCESS',solver_or_compiler_calls=0)
    except BaseException as error:
        report.update(status='FAIL',error_type=type(error).__name__,error=str(error),traceback=traceback.format_exc())
        traceback.print_exc()
    finally:
        cleanup=[]
        if owner is not None:
            try:owner.close();cleanup.append('OWNER_CLOSED')
            except BaseException as error:cleanup.append('OWNER_CLOSE_ERROR: '+str(error))
        if doc is not None:
            try:App.closeDocument(doc.Name);cleanup.append('OWN_DOCUMENT_CLOSED')
            except BaseException as error:cleanup.append('DOCUMENT_CLOSE_ERROR: '+str(error))
        report['cleanup']=cleanup
        (output/'receipt.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        # This is only reached in the token-authorized empty *new process* above.
        # The parent owns the actual process tree and confirms exit even on timeout.
        Gui.getMainWindow().close()
