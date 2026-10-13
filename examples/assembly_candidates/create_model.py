"""Public two-occurrence examples, using installed FreeCAD 1.1.4 only.

Call create('Revolute' or 'Slider', an_empty_short_folder) in FreeCAD GUI Python.
Creates and saves an editable Analysis/recipe. Does not mesh or run CalculiX.
"""
from pathlib import Path
import json


def create(kind, directory):
    import FreeCAD as App
    import FreeCADGui as Gui
    import ObjectsFem
    import JointObject
    from apps.desktop_pre.bridge import Owner
    from apps.desktop_pre.occurrence_fem import connect, element_pairs
    from apps.desktop_pre.candidate_recipe import prepare_recipe
    from apps.desktop_pre.assembly_candidates import measure
    from caelab.native_cad import sha

    if kind not in ('Revolute', 'Slider') or not App.GuiUp:
        raise ValueError('Use FreeCAD GUI with Revolute or Slider')
    folder = Path(directory).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    if any(folder.iterdir()):
        raise ValueError('Use a new output directory; prior source is preserved')
    doc = App.newDocument('Assembly' + kind)
    doc.Label = '회전 접촉' if kind == 'Revolute' else '이동 접촉'
    doc.UndoMode = 1
    fixed = doc.addObject('Part::Box', 'FixedPart')
    fixed.Label = '받침'
    fixed.Length, fixed.Width, fixed.Height = 20, 20, 3
    moving_part = doc.addObject('Part::Box', 'MovingPart')
    moving_part.Label = '이동 부품'
    moving_part.Length, moving_part.Width, moving_part.Height = 10, 6, 3
    assembly = doc.addObject('Assembly::AssemblyObject', 'Assembly')
    assembly.Type = 'Assembly'
    group = assembly.newObject('Assembly::JointGroup', 'Joints')
    ground = assembly.newObject('App::Link', 'GroundOccurrence')
    ground.setLink(fixed)
    ground.Label = '받침 인스턴스'
    moving = assembly.newObject('App::Link', 'MovingOccurrence')
    moving.setLink(moving_part)
    moving.Label = '이동 인스턴스'
    moving.Placement = App.Placement(App.Vector(5, 5, 3.2), App.Rotation())
    anchored = group.newObject('App::FeaturePython', 'Grounded')
    JointObject.GroundedJoint(anchored, ground)
    JointObject.ViewProviderGroundedJoint(anchored.ViewObject)
    joint = group.newObject('App::FeaturePython', 'Joint')
    JointObject.Joint(joint, JointObject.JointTypes.index(kind))
    joint.Label = '회전' if kind == 'Revolute' else '직선 이동'
    # Explicit connector origins; no FaceN proxy for a joint coordinate.
    joint.Detach1 = joint.Detach2 = True
    joint.Reference1, joint.Reference2 = (ground, ['']), (moving, [''])
    joint.Placement1 = App.Placement(App.Vector(5, 5, 3.2), App.Rotation())
    joint.Placement2 = App.Placement()
    JointObject.ViewProviderJoint(joint.ViewObject)
    if kind == 'Revolute':
        joint.EnableAngleMin = joint.EnableAngleMax = True
        joint.AngleMin, joint.AngleMax = -30., 30.
        unit, lower, upper = 'deg', -10., 10.
    else:
        joint.EnableLengthMin = joint.EnableLengthMax = True
        joint.LengthMin, joint.LengthMax = -.1, .1
        unit, lower, upper = 'mm', -.08, .08
    fixed.ViewObject.Visibility = moving_part.ViewObject.Visibility = False
    doc.recompute()
    if assembly.solve(False) != 0:
        raise ValueError('Native initial Assembly solve failed')
    owner = Owner(doc, folder / 'exchange', App=App, Gui=Gui)
    analysis = ObjectsFem.makeAnalysis(doc)
    solver = ObjectsFem.makeSolverCalculixCcxTools(doc)
    analysis.addObject(solver)
    solver.AnalysisType, solver.ModelSpace = 'static', '3D'
    solver.MaterialNonlinearity, solver.GeometricalNonlinearity = 'linear', 'nonlinear'
    solver.SplitInputWriter = False
    solver.TimeInitialIncrement, solver.TimeMaximumIncrement = .1, .1
    solver.TimePeriod, solver.TimeMinimumIncrement = 1., 1e-5
    solver.IncrementsMaximum = 100
    solver.AutomaticIncrementation = True
    connected = connect(owner, analysis, assembly)
    by_occurrence = {row['occurrence_id']: row for row in connected['bodies']}
    rows = [by_occurrence[ground.Name], by_occurrence[moving.Name]]
    for row in rows:
        mesh = doc.getObject(row['mesh_id'])
        mesh.CharacteristicLengthMax = 2.
        mesh.CharacteristicLengthMin = 1.
    material = ObjectsFem.makeMaterialSolid(doc)
    material.Material = {'Name': 'Public elastic example', 'YoungsModulus': '1000 MPa',
                         'PoissonRatio': '0.3', 'Density': '1000 kg/m^3'}
    analysis.addObject(material)

    def region(row, source_face, label):
        # Fixture-created Box faces, connected by actual native feature history.
        mapping = element_pairs(owner, assembly, row)
        names = [name for name, source in mapping.items() if source == source_face]
        if len(names) != 1:
            raise ValueError('Public fixture source face has no exact occurrence counterpart')
        return owner.fem._region_set(doc.getObject(row['body_id']),
                                     {'label': label, 'subelements': names})

    support = region(rows[0], 'Face5', '받침 아래')
    upper = region(rows[1], 'Face6', '이동 부품 위')
    slave = region(rows[1], 'Face5', '이동 접촉면')
    master = region(rows[0], 'Face6', '받침 접촉면')
    owner.fem._condition(analysis, {'region_id': support['id'], 'kind': 'Fixed'}, repair=False)
    displacement = owner.fem._condition(analysis, {'region_id': upper['id'], 'kind': 'Displacement'}, repair=False)
    condition = doc.getObject(displacement['object_id'])
    def prescribe():
        condition.xFree = condition.yFree = condition.zFree = False
        condition.xDisplacement = condition.yDisplacement = 0.
        condition.zDisplacement = -.35
        condition.EnableAmplitude = False
        owner.fem._record_condition(condition, upper['id'])
    owner._transaction('Public prescribed displacement', prescribe)
    contact = owner.fem.contact.set(analysis, {'draft': {
        'label': '부품과 받침', 'a_region_id': slave['id'], 'b_region_id': master['id'],
        'normal_law': 'linear', 'normal_stiffness_MPa_per_mm': 10000.,
        'tangential_law': 'frictionless'}})
    doc.recompute()
    errors = owner.fem.contact.errors(contact)
    if errors:
        raise ValueError(errors)
    state = owner.research.descriptor(analysis.Name)
    selected = next(row for row in state['candidates'] if row['target']['family'] == 'joint_coordinate')
    owner.research.dispatch('pre.research.register', {
        'analysis_id': analysis.Name, 'source_stamp': state['source_stamp'], 'key': selected['key'],
        'id': 'pose', 'label': '회전 각도' if kind == 'Revolute' else '이동량',
        'unit': unit, 'lower': lower, 'upper': upper}, {})
    prepared = prepare_recipe(owner, {'analysis_id': analysis.Name, 'solver_id': solver.Name,
        'variable_ids': ['pose'], 'responses': [{'id': 'normal_force', 'kind': 'pair',
        'pair_id': contact['object_id'], 'quantity': 'CFN', 'component': 'Z',
        'increment': 'final', 'reduction': 'value', 'unit': 'N'}]})
    project = owner.export_root / prepared['project_relative']
    receipt = {'kind': kind, 'project': str(project), 'sha256': sha(project),
               'recipe': prepared['recipe'], 'initial_coordinate': measure(owner, joint),
               'proposed_values': [-5., 5.] if kind == 'Revolute' else [-.05, .05],
               'unit': unit, 'freecad_version': list(App.Version()),
               'mesh_execution': 'NOT_PERFORMED', 'solver_execution': 'NOT_PERFORMED',
               'engineering_release': 'NOT_RELEASED'}
    (folder / 'fixture.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding='utf-8')
    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    return owner, receipt
