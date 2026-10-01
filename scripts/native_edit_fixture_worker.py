"""Acceptance-only native edits, using the same FreeCAD objects as its editor.

This trusted worker creates synthetic inputs and representative editor revisions.
It is not a production CAD editing operation. Domain validation stays upstream.
"""
import importlib.util
import json
import os
from pathlib import Path
import traceback

import FreeCAD as App
import Part
import Sketcher


def upstream_worker():
    root = Path(os.environ['CAELAB_NATIVE_EDIT_REPO'])
    source = root / 'plugins/fixture_design/upstream/fixturelab/freecad_worker.py'
    spec = importlib.util.spec_from_file_location('caelab_fixture_acceptance_upstream', source)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    return worker


def describe(doc, worker):
    registry = worker._registry(doc)
    final = worker._final(doc, registry)
    shape = final.Shape
    if shape.isNull() or not shape.isValid() or len(shape.Solids) != 1:
        raise ValueError('Synthetic fixture must have one valid solid')
    sketches = {o.Name: [
        {'index': i, 'name': c.Name, 'type': c.Type, 'value': float(c.Value),
         'driving': o.getDriving(i)} for i, c in enumerate(o.Constraints)]
        for o in doc.Objects if o.TypeId == 'Sketcher::SketchObject'}
    return {'freecad_version': App.Version(), 'registry': registry, 'sketches': sketches,
            'bounds_mm': [shape.BoundBox.XLength, shape.BoundBox.YLength, shape.BoundBox.ZLength],
            'volume_mm3': shape.Volume,
            'center_mm': [shape.Solids[0].CenterOfMass.x, shape.Solids[0].CenterOfMass.y,
                          shape.Solids[0].CenterOfMass.z]}


def layout(sketch, descriptors):
    for i in range(len(sketch.Constraints) - 1, -1, -1):
        sketch.delConstraint(i)
    for item in descriptors:
        # Distance from circle center to the origin: origin minus center.
        if item['type'] in ('DistanceX', 'DistanceY'):
            constraint = Sketcher.Constraint(item['type'], 0, 3, -1, 1, item['value'])
        elif item['type'] == 'Radius':
            constraint = Sketcher.Constraint('Radius', 0, item['value'])
        else:
            raise ValueError('Unsupported synthetic constraint')
        index = sketch.addConstraint(constraint)
        sketch.renameConstraint(index, item['name'])


def dispatch(request, worker):
    action, source = request['action'], Path(request['document'])
    if action == 'legacy_register':
        return worker.dispatch({'action': 'register', 'document': str(source),
                                'target': 'LocatorProfile|constraint|0', 'name': 'locator_radius',
                                'min': 2, 'max': 10, 'label': 'Locator radius'})
    if action == 'box_new':
        doc = App.newDocument('ImportedPart')
        try:
            box = doc.addObject('Part::Box', 'ImportedBox')
            box.Length, box.Width, box.Height = 12, 10, 8
            worker._save_registry(doc, {'parameters': [], 'final': box.Name})
            doc.recompute()
            doc.saveAs(str(source))
            return describe(doc, worker)
        finally:
            App.closeDocument(doc.Name)
    doc = App.openDocument(str(source))
    try:
        if action == 'part_length':
            doc.getObject('ImportedBox').Length = 14
        elif action == 'sketch_layout':
            layout(doc.getObject('LocatorProfile'), request['constraints'])
        elif action in ('rename_registered', 'delete_registered', 'reference_registered'):
            sketch = doc.getObject('LocatorProfile')
            matches = [i for i, c in enumerate(sketch.Constraints) if c.Name == 'locator_radius']
            if len(matches) != 1:
                raise ValueError('Expected one legacy named radius')
            index = matches[0]
            if action == 'rename_registered':
                sketch.renameConstraint(index, 'renamed_radius')
            elif action == 'delete_registered':
                sketch.delConstraint(index)
            else:
                sketch.setDriving(index, False)
        elif action in ('duplicate_key', 'duplicate_identity'):
            registry = worker._registry(doc)
            duplicate = dict(registry['parameters'][0])
            duplicate['name'] = 'duplicate_parameter'
            if action == 'duplicate_identity':
                duplicate['key'] = 'LocatorProfile|invalid-distinct-alias'
            registry['parameters'].append(duplicate)
            worker._save_registry(doc, registry)
        elif action == 'touch_label':
            doc.Label += ' revised'
        elif action != 'describe':
            raise ValueError('Unsupported synthetic native edit')
        if action != 'describe':
            doc.recompute()
            doc.save()
        return describe(doc, worker)
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    target = Path(os.environ['FIXTURE_FREECAD_RESULT'])
    try:
        result = dispatch(json.loads(Path(os.environ['FIXTURE_FREECAD_REQUEST']).read_text()), upstream_worker())
        target.write_text(json.dumps({'ok': True, 'result': result}, indent=2))
    except Exception as exc:
        target.write_text(json.dumps({'ok': False, 'error': str(exc), 'traceback': traceback.format_exc()}))
        raise
