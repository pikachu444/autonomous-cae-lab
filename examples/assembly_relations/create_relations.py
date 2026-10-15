"""Editable FreeCAD 1.1.4 five-chain rig. Creation/configuration does NOT calculate.

One ground, five different Link occurrences of one rod definition. Every moving
body has exactly one joint to ground: no contradictory multi-joint fake rig.
Native pose/path computation remains the existing FreeCAD Motion implementation.
"""
from copy import deepcopy
from pathlib import Path
import runpy
import tempfile

# Reuse only the existing preference guard; importing it does not build/run M3.
_guard = runpy.run_path(str(Path(__file__).resolve().parents[1]/'assembly_closed_loop'/'create_four_bar.py'))
no_automatic_solve = _guard['no_automatic_solve']
COORDINATES = (('A', 'Revolute', '입력 회전 A'), ('B', 'Revolute', '입력 회전 B'),
               ('C', 'Revolute', '출력 회전 C'), ('L', 'Slider', '입력 이동 L'), ('X', 'Slider', '출력 이동 X'))


def build_document():
    import FreeCAD as App
    import FreeCADGui as Gui
    import Part
    if tuple(App.Version()[:3]) != ('1', '1', '4'):
        raise RuntimeError('공개 rig의 native 수용 대상은 FreeCAD 1.1.4입니다.')
    Gui.activateWorkbench('AssemblyWorkbench')
    import JointObject as NativeJoint
    doc = App.newDocument('GeneralRelations'); doc.Label = '여러 구동 관계'; doc.UndoMode = 1
    context = {'doc': doc, 'joints': {}, 'moving': {}, 'origins': {}}
    with no_automatic_solve(App):
        assembly = doc.addObject('Assembly::AssemblyObject', 'RelationRig')
        assembly.Type = 'Assembly'; assembly.Label = '독립 회전과 이동'
        group = assembly.newObject('Assembly::JointGroup', 'Joints')
        definitions = doc.addObject('App::DocumentObjectGroup', 'Definitions'); definitions.Label = '부품 원형'
        rod = doc.addObject('Part::Feature', 'RodSource'); rod.Label = '반복 부품 원형'
        rod.Shape = Part.makeBox(25, 6, 4, App.Vector(0, -3, -2)); definitions.addObject(rod)
        support = doc.addObject('Part::Feature', 'GroundSource'); support.Label = '지지대 원형'
        support.Shape = Part.makeBox(6, 155, 6, App.Vector(-6, -15, -3)); definitions.addObject(support)
        ground = assembly.newObject('App::Link', 'GroundLink'); ground.setLink(support); ground.Label = '고정 지지대'
        fixed = group.newObject('App::FeaturePython', 'Ground')
        NativeJoint.GroundedJoint(fixed, ground); fixed.Label = '지지대 고정'
        if App.GuiUp: NativeJoint.ViewProviderGroundedJoint(fixed.ViewObject)
        for index, (name, kind, label) in enumerate(COORDINATES):
            origin = App.Vector(0, index*30, 0)
            moving = assembly.newObject('App::Link', 'Link'+name)
            moving.setLink(rod); moving.Label = '반복 부품'  # hierarchy supplies occurrence ordinals
            moving.Placement = App.Placement(origin, App.Rotation())
            joint = group.newObject('App::FeaturePython', 'Joint'+name)
            NativeJoint.Joint(joint, NativeJoint.JointTypes.index(kind)); joint.Label = label
            if App.GuiUp: NativeJoint.ViewProviderJoint(joint.ViewObject)
            joint.Detach1 = joint.Detach2 = True
            joint.Reference1 = (ground, ['', '']); joint.Reference2 = (moving, ['', ''])
            joint.Placement1 = App.Placement(origin, App.Rotation())
            joint.Placement2 = App.Placement()
            for key in ('Offset1', 'Offset2'):
                if hasattr(joint, key): setattr(joint, key, App.Placement())
            joint.Proxy.updateJCSPlacements(joint)
            context['joints'][name] = joint; context['moving'][name] = moving
            context['origins'][name] = [0., float(index*30), 0.]
        # Non-identity root makes document-global trace validation meaningful.
        assembly.Placement = App.Placement(App.Vector(200, -80, 15), App.Rotation(App.Vector(0, 0, 1), 20))
        rod.ViewObject.Visibility = support.ViewObject.Visibility = False
        doc.recompute()
    context.update(assembly=assembly, ground=ground, root_design=assembly.Placement.copy(), target={'assembly_id': assembly.Name})
    if App.GuiUp:
        Gui.activeDocument().activeView().viewAxonometric(); Gui.activeDocument().activeView().fitAll()
    return context


def definition_for(context, case='nonlinear'):
    """Return the declaration, not expanded strings. Changing A does not edit C/X."""
    from apps.desktop_pre.motion_occurrence import unique_path
    if case not in ('linear', 'changed', 'nonlinear'): raise ValueError('linear / changed / nonlinear')
    joints, assembly = context['joints'], context['assembly']
    drives = [{'joint_id': joints[name].Name, 'type': kind, 'formula': formula, 'unit': unit, 'name': label}
        for name, kind, formula, unit, label in (
            ('A', 'Angular', '60*time' if case=='changed' else '30*time', 'deg', '입력 A'),
            ('B', 'Angular', '10*time', 'deg', '입력 B'), ('L', 'Linear', '5*time', 'mm', '입력 L'))]
    def source(name):
        drive = next(d for d in drives if d['joint_id'] == joints[name].Name)
        return {'alias': name, 'joint_id': drive['joint_id'], 'type': drive['type'],
            'path': deepcopy(unique_path(assembly, joints[name])['path']), 'unit': drive['unit']}
    c = {'expression': 'amplitude*sin(A)+B' if case=='nonlinear' else '0.5*A+B',
        'sources': [source('A'), source('B')],
        'constants': [{'name': 'amplitude', 'value': 30., 'unit': 'deg'}] if case=='nonlinear' else []}
    x = {'expression': 'gain*A+L', 'sources': [source('A'), source('L')],
        'constants': [{'name': 'gain', 'value': 2., 'unit': 'mm/deg'}]}
    drives += [{'joint_id': joints[name].Name, 'type': kind, 'formula': '', 'unit': u, 'name': '출력 '+name, 'relation': relation}
        for name, kind, u, relation in (('C', 'Angular', 'deg', c), ('X', 'Linear', 'mm', x))]
    return {'time': {'start': 0., 'end': 1., 'step': .25, 'unit': 's'}, 'fps': 20,
        'native_error_tolerance': 1e-6, 'drives': drives,
        'traces': [{'id': name+' 끝점', 'occurrence_id': context['moving'][name].Name, 'point': [20., 0., 0.],
            'frame': 'occurrence_local', 'coordinate_unit': 'mm', 'output_frame': 'document_global'} for name in ('C', 'X')]}


def configure(owner, context, case='nonlinear'):
    if owner.doc is not context['doc']: raise ValueError('현재 rig 문서의 owner를 사용하세요.')
    import FreeCAD as App
    definition = definition_for(context, case)
    with no_automatic_solve(App):
        result = owner.motion.dispatch('pre.motion.configure', {'definition': definition}, context['target'])
    return definition, result


def editor_for(definition, *, invalid=False):
    """Same snapshot schema used by the selected-drive Qt editor."""
    from apps.desktop_pre.motion_relation import relation_values
    drives = deepcopy(definition['drives'])
    for drive in drives:
        if drive.get('relation') is not None: drive['relation'] = relation_values(drive['relation'], raw=True)
    if invalid:
        drives[3]['relation']['expression'] = 'amplitude*sin('
        if not drives[3]['relation']['constants']:
            drives[3]['relation']['constants'].append({'name': 'amplitude', 'value': '', 'unit': 'deg'})
        drives[3]['relation']['constants'][0]['value'] = '1e'
    return {'view': {'joint_id': drives[3]['joint_id'], 'drive_row': 3, 'trace_row': 0},
        'joint_draft': None, 'definition_draft': None if not invalid else {
            'time': {k: str(definition['time'][k]) for k in ('start', 'end', 'step')},
            'fps': definition['fps'], 'tolerance': str(definition['native_error_tolerance']), 'drives': drives,
            'traces': [{'id': t['id'], 'occurrence_id': t['occurrence_id'], 'point': [str(x) for x in t['point']]} for t in definition['traces']]},
        'relation_view': {'source_row': 1, 'constant_row': 0}}


def open_example():
    """For the existing native panel: release temporary owner, never calculate."""
    import FreeCAD as App
    from apps.desktop_pre.bridge import Owner
    context = build_document()
    owner = Owner(context['doc'], Path(tempfile.gettempdir())/'caelab-m1-relations')
    try:
        definition, _ = configure(owner, context)
        owner.motion.dispatch('pre.motion.save_editor', {'editor': editor_for(definition)}, context['target'])
        owner.motion.close()
    finally:
        App.removeDocumentObserver(owner); owner.closed = True
    return context
