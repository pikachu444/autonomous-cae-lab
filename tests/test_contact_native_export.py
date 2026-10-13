"""Native API contract doubles; no FreeCAD application, mesher or solver is run."""
import sys
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from test_contact_execution import model
from apps.desktop_pre import freeze_contact as exporter
from apps.desktop_pre.fem_edit import FEMEditor


def test_current_condition_faces_override_stale_mesh_groups_and_force_values_are_native(model, monkeypatch):
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
                   Material={'YoungsModulus': '1000 MPa', 'PoissonRatio': '.3'})
    fixed = obj('Fixed', 'Fem::ConstraintFixed', References=[(bodies['Base'], ['Face3'])])
    displacement = obj('Displacement', 'Fem::ConstraintDisplacement',
        References=[(bodies['Pad'], ['Face2'])], EnableAmplitude=False,
        xFree=False, yFree=True, zFree=True, xDisplacement=Quantity(-.02, 'mm'))
    force = obj('Force', 'Fem::ConstraintForce', References=[(bodies['Pad'], ['Face4', 'Face9'])],
        EnableAmplitude=False, Force=Quantity(10., 'N'), DirectionVector=NS(x=0., y=0., z=-1.))
    contact = obj('Contact', 'Fem::ConstraintContact')
    analysis = obj('Analysis', 'Fem::FemAnalysis',
                   Group=[solver, *meshes.values(), material, fixed, displacement, force, contact])
    record = {'analysis_id': analysis.Name, 'object_id': contact.Name,
              'draft': deepcopy(model['contacts'][0]['draft']), 'definition_sha256': 'TEST_ONLY'}
    for side, name in [('a', 'Pad'), ('b', 'Base')]:
        record[side] = {'target': {'object_id': name, 'subelements': [{'name': 'Face1'}]}}
    reads = []
    def members(a):
        assert a is analysis
        return NS(mats_linear=[{'Object': material}], cons_fixed=[{'Object': fixed}],
                  cons_displacement=[{'Object': displacement}], cons_force=[{'Object': force}])

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

    modules = {
        'FreeCAD': NS(Units=NS(Quantity=lambda value: Quantity(value, 'MPa'))),
        'femtools': NS(membertools=NS(AnalysisMember=members)),
        'femmesh': NS(meshtools=NS(get_ccx_elements=elements,
            get_femnodes_by_references=reference_nodes,
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
    actual, identity = exporter.collect(analysis, solver, fem)
    nmap = actual['body_maps']
    fixed_nodes = {row['node_id'] for row in actual['boundary_dofs'] if row['value_mm'] == 0.}
    assert fixed_nodes == {nmap['Base']['nodes'][n] for n in (1, 2, 3)}
    assert {'node_id': nmap['Pad']['nodes'][4], 'component': 1, 'value_mm': -.02} in actual['boundary_dofs']
    assert not any(row['node_id'] == nmap['Pad']['nodes'][1] for row in actual['boundary_dofs'])
    assert sum(row['force_N'] for row in actual['loads']) == -10.
    assert {row['node_id'] for row in actual['loads']} == {nmap['Pad']['nodes'][n] for n in (5, 6)}
    assert len(reads) == 2 and len(identity) == 2
    assert meshes['Base'].FemMesh.groups == {'Fixed': [4], 'Displacement': [1]}
    assert meshes['Pad'].FemMesh.groups == {'Fixed': [4], 'Displacement': [1]}


    # Check and export share the same real collector; Check does not publish files.
    assert FEMEditor.validate_for_run(fem, analysis) == []
    displacement.xDisplacement = Quantity('nan', 'mm')
    diagnostics = FEMEditor.validate_for_run(fem, analysis)
    assert diagnostics and diagnostics[0]['path'] == 'contact'
    assert diagnostics[0]['blocks_evaluation']
