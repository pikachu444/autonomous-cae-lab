"""Read native FEM objects without creating an Owner or changing the document."""
from copy import deepcopy

from . import metadata


def _value(value):
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if hasattr(value, 'Name') and hasattr(value, 'Document'):
        return {'object': value.Name}
    if isinstance(value, dict):
        return {str(key): _value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_value(item) for item in value]
    if hasattr(value, 'Value') and hasattr(value, 'Unit'):
        return {'value': value.Value, 'unit': str(value.Unit)}
    if all(hasattr(value, key) for key in ('x', 'y', 'z')):
        return [value.x, value.y, value.z]
    return str(value)


def model_snapshot(doc, selection=()):
    """Call on FreeCAD's main thread; saved-file readers set model_state themselves."""
    result = {'kind': 'freecad-model', 'model_state': 'current_editing_model',
              'document': {'name': doc.Name, 'label': doc.Label,
                           'path': getattr(doc, 'FileName', '')},
              'materials': [], 'steps': [], 'conditions': [], 'contacts': [],
              'sections': [], 'solver': [], 'mesh': [], 'selection': _value(selection)}
    for obj in doc.Objects:
        proxy = getattr(getattr(obj, 'Proxy', None), 'Type', '')
        kind = str(proxy or obj.TypeId)
        if obj.Name == metadata.NAME:
            continue
        if hasattr(obj, 'FemMesh'):
            category = 'mesh'
        elif 'Material' in kind:
            category = 'materials'
        elif 'Solver' in kind:
            category = 'solver'
        elif 'Analysis' in kind:
            category = 'steps'
        elif any(term in kind for term in ('Contact', 'Tie')):
            category = 'contacts'
        elif any(term in kind for term in ('Section', 'Beam', 'ShellThickness')):
            category = 'sections'
        elif any(term in kind for term in ('Constraint', 'Initial', 'Load')):
            category = 'conditions'
        else:
            continue
        row = {'name': obj.Name, 'label': obj.Label, 'type': kind, 'properties': {}}
        for name in getattr(obj, 'PropertiesList', []):
            if name in {'Shape', 'FemMesh', 'ExpressionEngine', 'Placement', 'Proxy'}:
                continue
            try:
                row['properties'][name] = _value(getattr(obj, name))
            except Exception as error:
                row.setdefault('unavailable', {})[name] = str(error)
        if category == 'mesh':
            mesh = obj.FemMesh
            row['counts'] = {key: getattr(mesh, key) for key in
                             ('NodeCount', 'EdgeCount', 'FaceCount', 'VolumeCount')
                             if hasattr(mesh, key)}
            # Native APIs expose existing topology. Reading it generates no mesh.
            row['elements'] = {}
            for name in ('Edges', 'Faces', 'Volumes'):
                identifiers = getattr(mesh, name, ())
                if identifiers:
                    counts = {}
                    for identifier in identifiers:
                        size = len(mesh.getElementNodes(identifier))
                        counts[size] = counts.get(size, 0) + 1
                    row['elements'][name.lower()] = [
                        {'nodes_per_element': size, 'count': count} for size, count in sorted(counts.items())]
        result[category].append(row)
    stored = metadata.read(doc)
    result['saved_extensions'] = deepcopy({key: value for key, value in stored.items()
                                           if key not in {'schema', 'document_id'}})
    if 'mesh_quality' in stored:
        result['mesh_quality'] = deepcopy(stored['mesh_quality'])
    return result
