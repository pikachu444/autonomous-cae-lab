"""Create tiny editable public CAD models in an existing FreeCAD Python console.

No company geometry, mesher, solver or provider is used.
"""


def sketch_solid(App, Part, Sketcher):
    doc = App.newDocument('PublicSketchVariable')
    body = doc.addObject('PartDesign::Body', 'Body')
    body.Label = '원형 몸체'
    sketch = doc.addObject('Sketcher::SketchObject', 'Sketch')
    body.addObject(sketch); sketch.Label = '원형 스케치'
    line = sketch.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(2, 0, 0)), True)
    sketch.addConstraint(Sketcher.Constraint('Horizontal', line))
    circle = sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10), False)
    index = sketch.addConstraint(Sketcher.Constraint('Radius', circle, 10.))
    sketch.renameConstraint(index, 'original_radius')
    pad = body.newObject('PartDesign::Pad', 'Pad')
    pad.Label = '원형 돌출'; pad.Profile = sketch; pad.Length = 5.
    doc.recompute(); sketch.Visibility = False
    return doc, sketch, pad


def property_solid(App):
    doc = App.newDocument('PublicPropertyVariable')
    box = doc.addObject('Part::Box', 'Box')
    box.Label = '직육면체'; box.Length = 10.; box.Width = 4.; box.Height = 3.
    doc.recompute()
    return doc, box
