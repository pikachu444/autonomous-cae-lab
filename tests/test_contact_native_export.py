"""Native API contract doubles; no FreeCAD application, mesher or solver is run."""
import sys
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from test_contact_execution import model
from apps.desktop_pre import freeze_contact as exporter
from apps.desktop_pre.fem_edit import FEMEditor


@pytest.mark.parametrize('zero_force_program,dynamic',[(False,False),(True,False),(True,True)])
def test_current_condition_faces_override_stale_mesh_groups_and_force_values_are_native(model, monkeypatch,zero_force_program,dynamic):
    class Quantity:
        def __init__(self, value, unit=None):
            self.Value = float(str(value).split()[0])
            self.unit = unit
        def getValueAs(self, unit):
            if self.unit is None:
                raise AssertionError('Dimensionless native force table cannot convert to N twice')
            assert unit == self.unit
            return Quantity(self.Value)

    doc = NS(Objects=[], isTouched=lambda: False)
    objects = {}
    def obj(name, kind, **values):
        value = NS(Name=name, Label=name, TypeId=kind, Document=doc, State=[], Suppressed=False, **values)
        doc.Objects.append(value)
        objects[name] = value
        return value

    bodies, meshes = {}, {}
    for name in ('Pad', 'Base'):
        shape = NS(Solids=[1])
        shape.copy = lambda *a: NS(isValid=lambda: True)
        bodies[name] = obj(name, 'Part::Feature', Shape=shape)
        nodes = {row['native_node_id']: NS(**dict(zip('xyz', row['position_mm'])))
                 for row in model['nodes'] if row['body_id'] == name}
        # Old condition groups deliberately point to the wrong face.
        mesh = NS(Nodes=nodes, Volumes=[73], getElementNodes=lambda e: list(range(1, 11)),
                  GroupCount=2, groups={'Fixed': [4], 'Displacement': [1]})
        meshes[name] = obj(name+'Mesh', 'Fem::FemMeshObjectPython', Shape=bodies[name], FemMesh=mesh)
    solver = obj('Solver', 'Fem::SolverCcxTools', AnalysisType='static', ModelSpace='3D',
        MaterialNonlinearity='linear', SplitInputWriter=False, GeometricalNonlinearity='nonlinear',
        TimeInitialIncrement=Quantity(.5, 's'), TimePeriod=Quantity(1., 's'),
        TimeMinimumIncrement=Quantity(1e-6, 's'), TimeMaximumIncrement=Quantity(.5, 's'),
        IncrementsMaximum=100, AutomaticIncrementation=True, MatrixSolverType='default',
        IterationsControlParameterTimeUse=False)
    material = obj('Material', 'Fem::MaterialCommon', Category='Solid', References=[],
                   Material={'YoungsModulus': '1000 MPa', 'PoissonRatio': '.3', 'Density':'7800 kg/m^3'})
    fixed = obj('Fixed', 'Fem::ConstraintFixed', References=[(bodies['Base'], ['Face3'])])
    displacement = obj('Displacement', 'Fem::ConstraintDisplacement',
        References=[(bodies['Pad'], ['Face2'])], EnableAmplitude=False,
        xFree=False, yFree=True, zFree=True, xDisplacement=Quantity(-.02, 'mm'))
    force = obj('Force', 'Fem::ConstraintForce', References=[(bodies['Pad'], ['Face4', 'Face9'])],
        EnableAmplitude=False, Force=Quantity(0. if zero_force_program else 10., 'N'), DirectionVector=NS(x=0., y=0., z=-1.))
    contact = obj('Contact', 'Fem::ConstraintContact')
    analysis = obj('Analysis', 'Fem::FemAnalysis',
                   Group=[solver, *meshes.values(), material, fixed, displacement, force, contact])
    record = {'analysis_id': analysis.Name, 'object_id': contact.Name,
              'draft': deepcopy(model['contacts'][0]['draft']), 'definition_sha256': 'TEST_ONLY'}
    for side, name in [('a', 'Pad'), ('b', 'Base')]:
        record[side] = {'target': {'object_id': name, 'subelements': [{'name': 'Face1'}]}}
    reads = []
    extra_displacements = []
    def members(a):
        assert a is analysis
        return NS(mats_linear=[{'Object': material}], cons_fixed=[{'Object': fixed}],
                  cons_displacement=[{'Object': displacement}, *[{'Object':o} for o in extra_displacements]], cons_force=[{'Object': force}])

    class Getter:
        def __init__(self, a, s, mesh, member):
            assert a is analysis and s is solver
            self.mesh, self.member = mesh, member
        def get_constraints_force_nodeloads(self):
            assert self.mesh is meshes['Pad']
            self.member.cons_force[0]['NodeLoadTable'] = [
                ('Face4', {5: Quantity(2.), 6: Quantity(3.)}),
                ('Face9', {5: Quantity(1.), 6: Quantity(4.)})]

    def elements(getter, reference):
        source, face = reference
        assert getter.mesh.Shape is source
        return reference, [73] if face == 'Solid1' else [(73, 1)], face != 'Solid1'

    def reference_nodes(mesh, references):
        reads.append((mesh, references))
        if references == fixed.References:
            assert mesh is meshes['Base'].FemMesh
            return [1, 2, 3]
        assert references == displacement.References and mesh is meshes['Pad'].FemMesh
        return [4]

    def probe_table(mesh,elements,nodes,probe):
        assert zero_force_program and force.Force.Value==0
        assert probe is not force and probe.References==force.References
        assert probe.Force.getValueAs('N').Value==1.
        return [('Face4',{5:Quantity(.3)}),('Face9',{6:Quantity(.7)})]

    modules = {
        'FreeCAD': NS(Units=NS(Quantity=lambda value: Quantity(value, str(value).split()[-1]))),
        'femtools': NS(membertools=NS(AnalysisMember=members)),
        'femmesh': NS(meshtools=NS(get_ccx_elements=elements,
            get_femnodes_by_references=reference_nodes,
            get_femelement_table=lambda mesh: 'EXPLICIT_ELEMENT_TABLE_DOUBLE',
            get_force_obj_face_nodeload_table=lambda mesh,elements,nodes,probe: probe_table(mesh,elements,nodes,probe),
            get_femnodes_by_femobj_with_references=lambda *a: pytest.fail('Stale name group must not be used'))),
        'femmesh.meshsetsgetter': NS(MeshSetsGetter=Getter),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(exporter, '_target', lambda source, names: {
        'object_id': source.Name, 'subelements': [{'name': name} for name in names]})
    owner = NS(doc=doc, assert_thread=lambda: None, _object=objects.__getitem__,
               mesh_bindings=NS(validate=lambda mesh: {'state': 'CURRENT_TEST_DOUBLE'}))
    fem = NS(owner=owner, _pending={}, _assert_idle=lambda: None, _metadata=lambda: {},
             _condition_errors=lambda *a: [], quality=lambda *a, **kw: {'bad_element_count': 0},
             contact=NS(_data=lambda: {'contacts': [record]}, errors=lambda record: []))
    if zero_force_program:
        from caelab.contact_steps import default_program
        inputs=[{'object_id':force.Name,'type':force.TypeId,'total_force_N':0.},
                {'object_id':fixed.Name,'type':fixed.TypeId},
                {'object_id':displacement.Name,'type':displacement.TypeId,'components_mm':{1:-.02}}]
        program=default_program(model['step'],inputs)
        program['procedure']='dynamic' if dynamic else 'static'
        program['steps'][0]['curves'][0]['points']=[[0,0],[.5,100],[1.,0]]
        fem._metadata=lambda:{'contact_programs':[{'analysis_id':analysis.Name,'draft':program}]}
    actual, identity = exporter.collect(analysis, solver, fem)
    assert solver.AnalysisType=='static'  # Pinned CcxTools has no dynamic enum.
    if dynamic:
        assert actual['analysis_steps']['procedure']=='dynamic'
        assert all(row['density_tonne_per_mm3']==pytest.approx(7.8e-9) for row in actual['materials'])
    nmap = actual['body_maps']
    fixed_nodes = {row['node_id'] for row in actual['boundary_dofs'] if row['value_mm'] == 0.}
    assert fixed_nodes == {nmap['Base']['nodes'][n] for n in (1, 2, 3)}
    assert {'node_id': nmap['Pad']['nodes'][4], 'component': 1, 'value_mm': -.02} in actual['boundary_dofs']
    assert not any(row['node_id'] == nmap['Pad']['nodes'][1] for row in actual['boundary_dofs'])
    assert sum(row['force_N'] for row in actual['loads']) == (0. if zero_force_program else -10.)
    if zero_force_program:
        from caelab.contact_steps import compile_program
        mapped=compile_program(actual['analysis_steps'],actual['conditions'])[0]['loads']
        assert sum(points[1][1] for points in mapped.values())==pytest.approx(-100.)
        assert force.Force.Value==0.
    assert {row['node_id'] for row in actual['loads']} == {nmap['Pad']['nodes'][n] for n in (5, 6)}
    assert len(reads) == 2 and len(identity) == 2
    assert meshes['Base'].FemMesh.groups == {'Fixed': [4], 'Displacement': [1]}
    assert meshes['Pad'].FemMesh.groups == {'Fixed': [4], 'Displacement': [1]}


    # Check and export share the same real collector; Check does not publish files.
    assert FEMEditor.validate_for_run(fem, analysis) == []
    if zero_force_program and not dynamic:
        from caelab.contact_steps import default_program
        second=obj('SecondTravel','Fem::ConstraintDisplacement',
            References=displacement.References,EnableAmplitude=False,
            xFree=False,yFree=True,zFree=True,xDisplacement=Quantity(-.04,'mm'))
        analysis.Group.append(second); extra_displacements.append(second)
        declarations=deepcopy(actual['conditions'])
        added=deepcopy(next(c for c in declarations if c['object_id']==displacement.Name))
        added.update(object_id=second.Name,components_mm={1:-.04})
        for row in added['boundary_dofs']: row['value_mm']=-.04
        declarations.append(added)
        program=default_program(model['step'],declarations)
        first=program['steps'][0]; last=deepcopy(first); last.update(id='Step2',label='다음 변위')
        next(c for c in first['curves'] if c['condition_id']==second.Name)['mode']='release'
        next(c for c in last['curves'] if c['condition_id']==displacement.Name)['mode']='release'
        program['steps'].append(last)
        fem._metadata=lambda:{'contact_programs':[{'analysis_id':analysis.Name,'draft':program}]}
        changed,_=exporter.collect(analysis,solver,fem)
        assert len(changed['analysis_steps']['steps'])==2
        # Same values simultaneously are still rejected by the actual compiler.
        next(c for c in first['curves'] if c['condition_id']==second.Name).pop('mode')
        with pytest.raises(ValueError,match='충돌'):
            exporter.collect(analysis,solver,fem)
    displacement.xDisplacement = Quantity('nan', 'mm')
    diagnostics = FEMEditor.validate_for_run(fem, analysis)
    assert diagnostics and diagnostics[0]['path'] == 'contact'
    assert diagnostics[0]['blocks_evaluation']
