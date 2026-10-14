"""Actual collector with native API doubles; no FreeCAD/mesh generator/solver."""
from copy import deepcopy
import sys
from types import SimpleNamespace as NS
import pytest

from test_contact_execution import model
from test_ns1_pipeline import nonlinear_model
from test_ns1_native_edit import draft
from apps.desktop_pre import freeze_contact as exporter
from apps.desktop_pre import nonlinear_material as nm
from caelab.contact_deck import render
from caelab.calculix_material import J2, LINEAR


def native_fixture(model, monkeypatch, single):
    model=nonlinear_model(model,single=single)
    doc=NS(Objects=[],isTouched=lambda:False)
    objects={}; metadata={}; bodies={}; meshes={}; materials=[]
    class Quantity:
        def __init__(self,value): self.Value=float(str(value).split()[0]); self.unit=str(value).split()[-1]
        def getValueAs(self,unit):
            assert unit==self.unit
            return NS(Value=self.Value)
    def make(name,kind,**values):
        obj=NS(Name=name,Label=name,TypeId=kind,State=[],Document=doc,Suppressed=False,**values)
        objects[name]=obj; doc.Objects.append(obj); return obj
    for name in model['body_maps']:
        body=make(name,'Part::Feature',Shape=NS(Solids=[1],copy=lambda *a:NS(isValid=lambda:True)))
        nodes={r['native_node_id']:NS(**dict(zip('xyz',r['position_mm']))) for r in model['nodes'] if r['body_id']==name}
        mesh=make(name+'Mesh','Fem::FemMeshObjectPython',Shape=body,
                  FemMesh=NS(Nodes=nodes,Volumes=[73],getElementNodes=lambda e:list(range(1,11))))
        base=make(name+'Material','Fem::MaterialCommon',Category='Solid',References=[(body,['Solid1'])],
                  Material={'Name':name,'YoungsModulus':'1000 MPa','PoissonRatio':'.3'})
        materials.append(base); bodies[name]=body; meshes[name]=mesh
    solver=make('Solver','Fem::SolverCcxTools',AnalysisType='static',ModelSpace='3D',SplitInputWriter=False,
        MaterialNonlinearity='nonlinear',GeometricalNonlinearity='nonlinear',IncrementsMaximum=100,
        AutomaticIncrementation=True,MatrixSolverType='default',IterationsControlParameterTimeUse=False,
        **{k:Quantity(str(v)+' s') for k,v in [('TimeInitialIncrement',.5),('TimePeriod',1),('TimeMinimumIncrement',1e-6),('TimeMaximumIncrement',.5)]})
    fixed=make('Fixed','Fem::ConstraintFixed',References=[(bodies['Pad' if single else 'Base'],['Face1'])])
    force=make('Force','Fem::ConstraintForce',References=[(bodies['Pad'],['Face2'])],EnableAmplitude=False,
               Force=Quantity('10 N'),DirectionVector=NS(x=0.,y=0.,z=-1.))
    plastic=make('PlasticPad',nm.KIND,LinearBaseMaterial=objects['PadMaterial'],
                 MaterialModelNonlinearity='isotropic hardening',YieldPoints=['250, 0','270, 0.001','300, .02'])
    records=[]
    if not single:
        contact=make('Contact','Fem::ConstraintContact')
        record={'analysis_id':'Analysis','object_id':'Contact','draft':deepcopy(model['contacts'][0]['draft']),'definition_sha256':'EXPLICIT_TEST_DOUBLE'}
        for side,name in [('a','Pad'),('b','Base')]: record[side]={'target':{'object_id':name,'subelements':[{'name':'Face1'}]}}
        records=[record]
    analysis=make('Analysis','Fem::FemAnalysis',Group=[solver,*meshes.values(),*materials,fixed,force,plastic]+([contact] if records else []))
    def members(analysis):
        return NS(mats_linear=[{'Object':obj} for obj in materials],cons_fixed=[{'Object':fixed}],
                  cons_force=[{'Object':force}],cons_displacement=[])
    class Getter:
        def __init__(self,analysis,solver,mesh,member): self.mesh,self.member=mesh,member
        def get_constraints_force_nodeloads(self): self.member.cons_force[0]['NodeLoadTable']=[('Face2',{4:NS(Value=10.)})]
    def elements(getter,reference):
        assert getter.mesh.Shape is reference[0]
        return reference,[73] if reference[1]=='Solid1' else [(73,1)],reference[1]!='Solid1'
    modules={'FreeCAD':NS(Units=NS(Quantity=Quantity)),
             'femtools':NS(membertools=NS(AnalysisMember=members)),
             'femmesh':NS(meshtools=NS(get_ccx_elements=elements,get_femnodes_by_references=lambda mesh,refs:[1,2,3])),
             'femmesh.meshsetsgetter':NS(MeshSetsGetter=Getter),
             'femsolver.calculix':NS(write_constraint_contact=NS())}
    for key,module in modules.items(): monkeypatch.setitem(sys.modules,key,module)
    monkeypatch.setattr(exporter,'_target',lambda obj,names:{'object_id':obj.Name,'subelements':[{'name':name} for name in names]})
    owner=NS(doc=doc,_object=objects.__getitem__,mesh_bindings=NS(validate=lambda mesh:{'state':'EXPLICIT_TEST_DOUBLE'}))
    fem=NS(owner=owner,_assert_idle=lambda:None,_metadata=lambda:deepcopy(metadata),
           quality=lambda *a,**k:{'bad_element_count':0},_condition_errors=lambda *a:[],
           contact=NS(_data=lambda:{'contacts':records},errors=lambda record:[]))
    return NS(doc=doc,objects=objects,analysis=analysis,solver=solver,fem=fem,plastic=plastic,metadata=metadata)


@pytest.mark.parametrize('single',[False,True])
def test_native_user_sets_link_mixed_materials_and_201_draft_blocks_before_export(model,monkeypatch,single,tmp_path):
    n=native_fixture(model,monkeypatch,single)
    before=list(n.plastic.YieldPoints)
    actual,identity=exporter.collect(n.analysis,n.solver,n.fem)
    assert actual['materials'][0]['object_id']=='PadMaterial'
    assert next(r for r in actual['materials'] if r['body_id']=='Pad')['law']==J2
    if not single: assert next(r for r in actual['materials'] if r['body_id']=='Base')['law']==LINEAR
    assert len(identity)==(1 if single else 2) and render(actual).count('*PLASTIC')==1
    assert n.plastic.YieldPoints==before
    n.metadata['plasticity_drafts']=[{'analysis_id':'Analysis','material_id':'PadMaterial','draft':draft(201)}]
    with pytest.raises(ValueError,match='200'): exporter.collect(n.analysis,n.solver,n.fem)
    with pytest.raises(ValueError,match='200'): exporter.freeze_contact(n.analysis,n.solver,tmp_path/'output',fem=n.fem)
    assert not (tmp_path/'output').exists() and n.plastic.YieldPoints==before
    n.metadata.clear(); n.plastic.YieldPoints=['250,0']*201
    with pytest.raises(ValueError,match='200'): exporter.collect(n.analysis,n.solver,n.fem)


def test_foreign_material_link_and_missing_nonlinear_solver_flag_are_not_ignored(model,monkeypatch):
    n=native_fixture(model,monkeypatch,True)
    n.solver.MaterialNonlinearity='linear'
    with pytest.raises(ValueError,match='일치'): exporter.collect(n.analysis,n.solver,n.fem)
    n.solver.MaterialNonlinearity='nonlinear'
    n.plastic.LinearBaseMaterial=NS(Name='Foreign',TypeId='Fem::MaterialCommon')
    with pytest.raises(ValueError,match='기본 재료'): exporter.collect(n.analysis,n.solver,n.fem)
