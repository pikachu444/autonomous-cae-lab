"""Public editable XLink assembly. Run in FreeCAD; no mesh or solver.

The parts use ordinary native parametric primitives and Boolean features, as
in the existing assembly examples. This is a portability example, not a jig
qualification or a solution of the original M4 motion problem.
"""
from pathlib import Path


def create(folder):
    import FreeCAD as App
    import FreeCADGui as Gui
    import ObjectsFem
    from apps.desktop_pre.bridge import Owner
    from apps.desktop_pre.assembly_pose_candidate import _hold
    from apps.desktop_pre.portable_project import complete_save, saved_offer
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    def step(value):
        (folder/'creation-stage.txt').write_text(value, encoding='utf8')
    step('base')
    base = App.newDocument('PortableBase'); _hold(base)
    base.Label = '베이스 원부품'
    block = base.addObject('Part::Box', 'Base'); block.Label = '베이스'
    block.Length = 60; block.Width = 30; block.Height = 8
    base.recompute(); base.saveAs(str(folder/'base.FCStd'))
    child = App.newDocument('PortableClamp'); _hold(child)
    child.Label = '구멍이 있는 클램프 원부품'
    outer = child.addObject('Part::Cylinder', 'Outer'); outer.Radius = 10; outer.Height = 12
    bore = child.addObject('Part::Cylinder', 'Bore'); bore.Radius = 4; bore.Height = 12
    clamp = child.addObject('Part::Cut', 'Clamp'); clamp.Label = '클램프'
    clamp.Base = outer; clamp.Tool = bore
    child.recompute(); outer.Visibility = bore.Visibility = False
    child.saveAs(str(folder/'clamp.FCStd'))
    step('root')
    root = App.newDocument('PortableAssembly'); _hold(root)
    root.Label = '외부 부품 조립 예제'
    root.saveAs(str(folder/'assembly.FCStd'))  # Native external Links require a saved owning document.
    mount = root.addObject('App::Part', 'Mount'); mount.Label = '조립'
    step('base link')
    base_link = root.addObject('App::Link', 'BaseOccurrence'); base_link.setLink(block); mount.addObject(base_link)
    nested = root.addObject('App::Part', 'Clamps'); nested.Label = '클램프 배치'; mount.addObject(nested)
    for index, x in enumerate((15, 45), 1):
        step('clamp link '+str(index))
        link = root.addObject('App::Link', 'ClampOccurrence'+str(index))
        link.Label = '클램프 '+str(index); link.setLink(clamp); nested.addObject(link)
        link.Placement.Base = App.Vector(x, 15, 8)
    step('analysis')
    analysis = ObjectsFem.makeAnalysis(root)
    support = root.addObject('Part::Box', 'Support'); support.Label = '고정 지지대'
    support.Length = 60; support.Width = 30; support.Height = 3
    support.Placement.Base.z = -3
    root.recompute()
    fixed = ObjectsFem.makeConstraintFixed(root, 'FixedBase'); fixed.Label = '베이스 고정'
    fixed.References = [(support, ('Face1',))]; analysis.addObject(fixed)
    step('root recompute')
    root.recompute()
    step('owner')
    owner = Owner(root, folder/'local', App=App, Gui=Gui)
    App.setActiveDocument(root.Name)
    Gui.Selection.clearSelection(); Gui.Selection.addSelection(root.Name, 'ClampOccurrence2', 'Face1')
    Gui.activeDocument().activeView().viewAxonometric(); Gui.activeDocument().activeView().fitAll()
    step('managed save')
    witness = complete_save(owner, expected_stamp=saved_offer(owner)['stamp'], path=folder/'assembly.caepre')
    step('complete')
    return owner, witness
