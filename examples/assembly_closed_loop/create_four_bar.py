"""Public planar 4R CAD fixture for installed FreeCAD 1.1.4.

Four revolute joints + one grounded occurrence, never a cylindrical substitute.
The geometry calculation below is ONLY initial CAD placement; there is no time
integration or replacement kinematics solver. All motion uses existing Motion.
"""
from contextlib import contextmanager
from copy import deepcopy
import math
from pathlib import Path
import tempfile


LENGTHS = {'ground': 100., 'crank': 60., 'coupler': 70., 'rocker': 50.}
BAR_ORDER = ('ground', 'crank', 'coupler', 'rocker')
LABELS = {'ground': '고정 링크', 'crank': '입력 링크', 'coupler': '연결봉', 'rocker': '출력 링크'}
# name, first bar/local anchor, second bar/local anchor
JOINTS = (('A', 'ground', 0., 'crank', 0.), ('B', 'crank', 60., 'coupler', 0.),
          ('C', 'coupler', 70., 'rocker', 50.), ('D', 'rocker', 0., 'ground', 100.))


def design_geometry(singular=False):
    """Construct one initial placement, not motion samples or reference results."""
    d, a, b, c = (LENGTHS[name] for name in BAR_ORDER)
    angle = math.acos((d*d+a*a-(b+c)*(b+c))/(2*d*a)) if singular else math.pi/3
    A, D = (0., 0.), (d, 0.)
    B = (a*math.cos(angle), a*math.sin(angle))
    dx, dy = D[0]-B[0], D[1]-B[1]
    distance = math.hypot(dx, dy)
    if singular:
        C = (B[0]+b*dx/(b+c), B[1]+b*dy/(b+c))
    else:
        along = (b*b-c*c+distance*distance)/(2*distance)
        height = math.sqrt(b*b-along*along)
        C = (B[0]+along*dx/distance-height*dy/distance,
             B[1]+along*dy/distance+height*dx/distance)
    angles = {'ground': 0., 'crank': angle,
              'coupler': math.atan2(C[1]-B[1], C[0]-B[0]),
              'rocker': math.atan2(C[1]-D[1], C[0]-D[0])}
    return {'points': {'A': A, 'B': B, 'C': C, 'D': D}, 'angles': angles,
            'origins': {'ground': A, 'crank': A, 'coupler': B, 'rocker': D},
            'singular': bool(singular)}


@contextmanager
def no_automatic_solve(App):
    """Build CAD without silently invoking the native solver; restore preferences."""
    preferences = App.ParamGet('User parameter:BaseApp/Preferences/Mod/Assembly')
    saved = {key: (key in preferences.GetBools(), preferences.GetBool(key, True))
             for key in ('SolveOnRecompute', 'SolveOnMove')}
    try:
        for key in saved: preferences.SetBool(key, False)
        yield
    finally:
        for key, (present, value) in saved.items():
            if present: preferences.SetBool(key, value)
            else: preferences.RemBool(key)


def _set_design(context, singular=False):
    import FreeCAD as App
    geometry = design_geometry(singular)
    for name, obj in context['bars'].items():
        x, y = geometry['origins'][name]
        obj.Placement = App.Placement(App.Vector(x, y, 0),
                                      App.Rotation(App.Vector(0, 0, 1), math.degrees(geometry['angles'][name])))
    for name, left, lp, right, rp in JOINTS:
        joint = context['joints'][name]
        # All JCS axes coincide in the initial WORLD frame. The relative input
        # angle is therefore zero at the constructed design, independent of the
        # bars' initial absolute angles. Do not call the presolve connector setter.
        joint.Detach1 = joint.Detach2 = True
        for index, bar, x in ((1, left, lp), (2, right, rp)):
            setattr(joint, 'Placement'+str(index), App.Placement(App.Vector(x, 0, 0),
                App.Rotation(App.Vector(0, 0, 1), -math.degrees(geometry['angles'][bar]))))
            setattr(joint, 'Reference'+str(index), (context['bars'][bar], ['', '']))
        for key in ('Offset1', 'Offset2'):
            if hasattr(joint, key): setattr(joint, key, App.Placement())
        joint.Proxy.updateJCSPlacements(joint)
    context['geometry'] = geometry


def build_document():
    """Return editable native CAD; no owner, simulation calculation or new UI."""
    import FreeCAD as App
    import FreeCADGui as Gui
    import Part
    Gui.activateWorkbench('AssemblyWorkbench')
    import JointObject as NativeJoint
    if tuple(App.Version()[:3]) != ('1', '1', '4'):
        raise RuntimeError('이 예제는 설치된 FreeCAD 1.1.4에서 확인하도록 작성했습니다.')
    doc = App.newDocument('ClosedFourBar')
    doc.Label = '4절 회전 기구'
    doc.UndoMode = 1
    context = {'doc': doc, 'bars': {}, 'joints': {}}
    with no_automatic_solve(App):
        assembly = doc.addObject('Assembly::AssemblyObject', 'FourBar')
        assembly.Type = 'Assembly'; assembly.Label = '4절 링크'
        group = assembly.newObject('Assembly::JointGroup', 'Joints')
        context['assembly'] = assembly
        sources = doc.addObject('App::DocumentObjectGroup', 'BarDefinitions'); sources.Label = '링크 원형'
        for name in BAR_ORDER:
            source = doc.addObject('Part::Feature', 'Shape_'+name)
            source.Label = LABELS[name]+' 원형'
            source.Shape = Part.makeBox(LENGTHS[name], 8., 4., App.Vector(0, -4, -2))
            sources.addObject(source)
            link = assembly.newObject('App::Link', 'Link_'+name)
            link.setLink(source); link.Label = LABELS[name]
            link.ViewObject.Visibility = True
            source.ViewObject.Visibility = False
            context['bars'][name] = link
        ground = group.newObject('App::FeaturePython', 'Ground')
        NativeJoint.GroundedJoint(ground, context['bars']['ground'])
        ground.Label = '고정 링크 지지'
        if App.GuiUp: NativeJoint.ViewProviderGroundedJoint(ground.ViewObject)
        for name, *_ in JOINTS:
            joint = group.newObject('App::FeaturePython', 'Joint'+name)
            NativeJoint.Joint(joint, NativeJoint.JointTypes.index('Revolute'))
            joint.Label = {'A': '입력 회전 A', 'B': '회전 B', 'C': '회전 C', 'D': '출력 회전 D'}[name]
            if App.GuiUp: NativeJoint.ViewProviderJoint(joint.ViewObject)
            context['joints'][name] = joint
        _set_design(context)
        doc.recompute()
    context['target'] = {'assembly_id': assembly.Name}
    context['definition'] = {'time': {'start': 0., 'end': 1., 'step': .05, 'unit': 's'},
        'fps': 20, 'native_error_tolerance': 1e-6,
        'drives': [{'joint_id': context['joints']['A'].Name, 'type': 'Angular',
                    'formula': '10*pi/180*time', 'unit': 'rad', 'name': '입력 회전'}],
        'traces': [{'id': '연결봉 중앙', 'occurrence_id': context['bars']['coupler'].Name,
                    'point': [35., 0., 0.], 'frame': 'occurrence_local',
                    'coordinate_unit': 'mm', 'output_frame': 'document_global'}]}
    if App.GuiUp:
        Gui.activeDocument().activeView().viewTop()
        Gui.activeDocument().activeView().fitAll()
    return context


def configure(owner, context):
    if owner.doc is not context['doc']: raise ValueError('예제를 소유한 문서를 선택하세요.')
    import FreeCAD as App
    with no_automatic_solve(App):
        return owner.motion.dispatch('pre.motion.configure', {'definition': deepcopy(context['definition'])}, context['target'])


def set_case(owner, context, case):
    """Explicit EXAMPLE action only. Keeps prior successes/attempts in this owner."""
    if case not in ('normal', 'overconstrained', 'unreachable', 'singular'):
        raise ValueError('normal / overconstrained / unreachable / singular 중에서 선택하세요.')
    import FreeCAD as App
    owner.before_design_action('change four-bar example')
    with no_automatic_solve(App):
        owner._transaction('4절 기구 설계 자세', lambda: _set_design(context, case == 'singular'))
    definition = deepcopy(context['definition'])
    if case == 'unreachable':
        # A half-turn from the initial 60-degree crank position gives a pin
        # distance sqrt(19600)=140 mm, exceeding coupler+rocker = 120 mm.
        # This is infeasible for either angular sign. Native decides the result.
        definition['drives'][0]['formula'] = 'pi'
    elif case == 'overconstrained':
        definition['drives'].append({'joint_id': context['joints']['D'].Name,
            'type': 'Angular', 'formula': '0', 'unit': 'rad', 'name': '출력 고정 구동'})
    elif case == 'singular':
        # B-C-D are collinear at the input reach limit. Never fabricate a
        # singularity return code: Ondsel may reject or traverse this geometry.
        definition['drives'][0]['formula'] = '10*pi/180*time'
    with no_automatic_solve(App):
        return owner.motion.dispatch('pre.motion.configure', {'definition': definition}, context['target'])


def open_example():
    """Create/configure for the existing CAE panel, then release the temporary owner.

    The macro is synchronous and never processes events. Connection's ordinary
    discovery attaches the document afterwards; no second lasting owner or panel.
    """
    import FreeCAD as App
    from apps.desktop_pre.bridge import Owner
    context = build_document()
    owner = Owner(context['doc'], Path(tempfile.gettempdir())/'caelab-m3-example')
    try:
        configure(owner, context)
        owner.motion.close()
    finally:
        App.removeDocumentObserver(owner)
        owner.closed = True
    return context
