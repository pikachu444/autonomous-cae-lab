"""Native authoring for the fixed Case A cube; no solver is started here."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback


def run():
    config=json.loads(Path(os.environ['CAELAB_CASE_A_CONFIG']).read_text(encoding='utf-8'))
    if config['token']!=os.environ.get('CAELAB_CASE_A_TOKEN'):
        raise RuntimeError('Wrong owned Case A process')
    sys.path.insert(0,config['repo'])
    import FreeCAD as App
    import FreeCADGui as Gui
    if App.listDocuments():raise RuntimeError('Case A requires an empty owned FreeCAD process')
    import Fem,ObjectsFem,Part
    from apps.desktop_pre.bridge import Owner
    from apps.desktop_pre import nonlinear_material
    from apps.desktop_pre.freeze_contact import freeze_contact
    from apps.desktop_pre.freeze_analysis import CCX_FROM_NATIVE_TET10
    from caelab.storage import canonical_hash,save_json
    from caelab.calculix_material import default_plasticity,J2
    from case_a_fixture import cube_c3d10
    packet=json.loads(Path(config['packet']).read_text(encoding='utf-8'))
    assert canonical_hash(packet)==config['packet_sha256']
    root=Path(config['repo'])
    for relative,pin in packet['source_sha256'].items():
        assert hashlib.sha256((root/relative).read_bytes()).hexdigest()==pin,relative+' changed after declaration'
    output=Path(config['output']);output.mkdir(parents=True,exist_ok=False)
    report=dict(status='RUNNING',pid=os.getpid(),version=list(App.Version()),cases=[],solver_calls=0)
    owner=None
    try:
        fixture=cube_c3d10()
        for index,case in enumerate(packet['cases']):
            doc=App.newDocument('CaseA'+str(index+1));doc.Label=case['name']
            box=doc.addObject('Part::Feature','Specimen');box.Shape=Part.makeBox(1.,1.,1.)
            analysis=ObjectsFem.makeAnalysis(doc,'Analysis')
            mesh=ObjectsFem.makeMeshGmsh(doc,'Mesh');mesh.Shape=box
            native=Fem.FemMesh()
            for n,xyz in enumerate(fixture['points_mm'],1):native.addNode(*xyz,n)
            for n,cell in enumerate(fixture['cells_C3D10_1_based'],1):
                native_ids=[None]*10
                for deck_slot,native_slot in enumerate(CCX_FROM_NATIVE_TET10):native_ids[native_slot]=cell[deck_slot]
                native.addVolume(native_ids,n)
            mesh.FemMesh=native;analysis.addObject(mesh)
            material=ObjectsFem.makeMaterialSolid(doc,'Material');material.References=[(box,['Solid1'])]
            material.Material={'Name':'Synthetic J2 Case A','YoungsModulus':'210000 MPa','PoissonRatio':'0.3'}
            analysis.addObject(material)
            solver=ObjectsFem.makeSolverCalculiXCcxTools(doc,'Solver')
            for key,value in dict(AnalysisType='static',ModelSpace='3D',SplitInputWriter=False,
                GeometricalNonlinearity='linear',MaterialNonlinearity='nonlinear',
                AutomaticIncrementation=True,IncrementsMaximum=100,MatrixSolverType='default').items():
                setattr(solver,key,value)
            for key,value in dict(TimeInitialIncrement=.1,TimeMinimumIncrement=1e-6,
                TimeMaximumIncrement=.1,TimePeriod=1.).items():setattr(solver,key,value)
            analysis.addObject(solver);doc.recompute()
            owner=Owner(doc,output/case['name']/'exports',App=App,Gui=Gui)
            curve=default_plasticity();curve['yield_points']=[[250.,0.],[300.,.05]]
            nonlinear_material.apply(owner.fem,material,analysis.Name,dict(law=J2,plasticity=curve,definitions_confirmed=True))
            faces={}
            for face_index,face in enumerate(box.Shape.Faces,1):
                center=face.CenterOfMass
                for axis,letter in enumerate('xyz'):
                    value=(center.x,center.y,center.z)[axis]
                    for side in (0,1):
                        if value==side:faces[letter+str(side)]='Face'+str(face_index)
            assert len(faces)==6
            confined=case['name']=='transverse_strain_confinement'
            specs=[('x0',0),('x1',0),('y0',1),('z0',2)]
            if confined:specs += [('y1',1),('z1',2)]
            conditions=[]
            for face,axis in specs:
                region=owner.fem._region_set(box,dict(label=face,subelements=[faces[face]]))
                obj=ObjectsFem.makeConstraintDisplacement(doc,'BC'+face)
                obj.References=[(box,[faces[face]])];obj.EnableAmplitude=False
                for letter in 'xyz':setattr(obj,letter+'Free',True)
                letter='xyz'[axis];setattr(obj,letter+'Free',False)
                values=[0. if face.endswith('0') else float(F[axis][axis]-1.)
                        for F in case['CCX_condition']['requested_F']]
                setattr(obj,letter+'Displacement',values[-1]);analysis.addObject(obj)
                owner.fem._record_condition(obj,region['id']);conditions.append((obj,axis+1,values))
            stages=[]
            for i in (1,2,3):
                stages.append(dict(id='Stage'+str(i),label='지정 변위 단계 '+str(i),
                    duration=1.,initial=.1,minimum=1e-6,maximum=.1,increments=100,output_frequency=1,
                    curves=[dict(condition_id=obj.Name,component=component,unit='mm',
                        points=[[0.,values[i-1]],[1.,values[i]]]) for obj,component,values in conditions]))
            metadata=owner.read_metadata();metadata['contact_programs']=[dict(analysis_id=analysis.Name,
                draft=dict(schema_version='1',procedure='static',steps=stages))]
            owner.write_metadata(metadata);doc.recompute()
            editable=output/case['name']/'authored.FCStd';editable.parent.mkdir(parents=True,exist_ok=True)
            doc.saveAs(str(editable));doc.recompute()
            quality=owner.fem.quality(mesh,limit=128);save_json(output/case['name']/'native-quality.json',quality)
            assert quality['bad_element_count']==0,quality
            for e,expected in enumerate(fixture['cells_C3D10_1_based'],1):
                assert [native.getElementNodes(e)[slot] for slot in CCX_FROM_NATIVE_TET10]==expected
            frozen=freeze_contact(analysis,solver,output/case['name']/'frozen',fem=owner.fem)
            report['cases'].append(dict(name=case['name'],editable=str(editable),frozen=str(frozen),
                declared_case_sha256=canonical_hash(case),nodes=len(native.Nodes),cells=len(native.Volumes)))
            save_json(output/'author.json',report)
            owner.close();owner=None;App.closeDocument(doc.Name)
        report['status']='PASS'
    except BaseException as error:
        report.update(status='FAIL',error_type=type(error).__name__,error=str(error),traceback=traceback.format_exc())
        traceback.print_exc()
    finally:
        if owner is not None:owner.close()
        for name in list(App.listDocuments()):App.closeDocument(name)
        save_json(output/'author.json',report)
        Gui.getMainWindow().close()
