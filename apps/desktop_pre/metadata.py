"""Small native document metadata; FreeCAD owns persistence and Undo.

This is not a parallel CAD document. Native features, constraints, joints and
FEM objects remain their original editable FreeCAD objects.
"""
from copy import deepcopy
import json

NAME = 'CAELabProject'
PROPERTY = 'Definition'
SCHEMA = 'caelab-pre-project/1'


def read(doc):
    obj = doc.getObject(NAME)
    if obj is None:
        return {'schema': SCHEMA}
    if PROPERTY not in obj.PropertiesList:
        raise ValueError('CAELabProject name is occupied by a different native object')
    value = json.loads(getattr(obj, PROPERTY))
    if not isinstance(value, dict) or value.get('schema') != SCHEMA:
        raise ValueError('Unsupported or invalid saved CAE Lab native metadata; preserve the draft')
    return deepcopy(value)


def write(doc, value):
    value = deepcopy(value)
    value['schema'] = SCHEMA
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    if len(text.encode('utf-8')) > 8 * 1024 * 1024:
        raise ValueError('Native research metadata exceeds 8 MiB; use retained result files')
    obj = doc.getObject(NAME)
    if obj is None:
        obj = doc.addObject('App::DocumentObjectGroup', NAME)
        obj.Label = 'CAE Lab research and connections'
        obj.addProperty('App::PropertyString', PROPERTY, 'CAE Lab',
                        'Research definitions and exact retained job references')
        obj.setEditorMode(PROPERTY, 1)
    elif PROPERTY not in obj.PropertiesList:
        raise ValueError('CAELabProject name is occupied by a different native object')
    if getattr(obj, PROPERTY) != text:
        setattr(obj, PROPERTY, text)
