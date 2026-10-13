"""Create public editable contact input; no product feature or physics claim."""
import json
from pathlib import Path

import FreeCAD as App


folder = Path(__file__).parent
folder.mkdir(exist_ok=True)
output = folder / 'two-feet.FCStd'
assert not output.exists(), 'Preserve previously created source models'
doc = App.newDocument('TwoFeet')


def horizontal_faces(obj, z, normal_z):
    selected = []
    for index, face in enumerate(obj.Shape.Faces, 1):
        u0, u1, v0, v1 = face.ParameterRange
        normal = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
        if abs(face.CenterOfMass.z - z) < 1e-8 and abs(normal.z - normal_z) < 1e-8:
            selected.append('Face' + str(index))
    return selected


try:
    base = doc.addObject('Part::Box', 'Base')
    base.Label = 'Base'
    base.Length, base.Width, base.Height = 30, 20, 5
    stock = doc.addObject('Part::Box', 'Stock')
    stock.Length, stock.Width, stock.Height = 20, 10, 10
    stock.Placement.Base = App.Vector(5, 5, 5.2)
    notch = doc.addObject('Part::Box', 'Notch')
    notch.Length, notch.Width, notch.Height = 10, 12, 6
    notch.Placement.Base = App.Vector(10, 4, 4.2)
    bridge = doc.addObject('Part::Cut', 'Bridge')
    bridge.Label = 'Bridge'
    bridge.Base, bridge.Tool = stock, notch
    bridge.Refine = True
    doc.recompute()
    assert base.Shape.isValid() and bridge.Shape.isValid()
    assert len(bridge.Shape.Solids) == 1
    assert abs(bridge.Shape.Volume - 1500) < 1e-7
    faces_a = horizontal_faces(bridge, 5.2, -1)
    faces_b = horizontal_faces(base, 5, 1)
    assert len(faces_a) == 2 and len(faces_b) == 1
    assert abs(sum(bridge.Shape.getElement(name).Area for name in faces_a) - 100) < 1e-7
    expected = {'A': ['Bridge', faces_a], 'B': ['Base', faces_b]}
    doc.saveAs(str(output))
finally:
    App.closeDocument(doc.Name)

doc = App.openDocument(str(output))
try:
    assert doc.Bridge.TypeId == 'Part::Cut'
    assert doc.Bridge.Base.Name == 'Stock' and doc.Bridge.Tool.Name == 'Notch'
    restored = {'A': ['Bridge', horizontal_faces(doc.Bridge, 5.2, -1)],
                'B': ['Base', horizontal_faces(doc.Base, 5, 1)]}
    assert restored == expected
    assert doc.Base.Shape.distToShape(doc.Bridge.Shape)[0] > 0.199999
    report = {'file': str(output), 'units': 'mm', 'initial_clearance': 0.2,
              'suggested_contact_selection': restored,
              'contact_area_A': 100, 'support_face': horizontal_faces(doc.Base, 0, -1),
              'load_face': horizontal_faces(doc.Bridge, 15.2, 1),
              'freecad_version': list(App.Version()),
              'scope': 'editable CAD fixture with two contact faces; save/reopen checked',
              'contact_declaration': 'not created; author with product editor when available',
              'mesh': 'not generated', 'solver': 'not run', 'gui': 'not run'}
    (folder / 'model.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
finally:
    App.closeDocument(doc.Name)
