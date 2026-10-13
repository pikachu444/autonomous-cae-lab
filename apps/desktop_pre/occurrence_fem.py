"""Exact native Assembly occurrence -> synchronized FEM geometry.

One native SubShapeBinder per occurrence; no fuse, custom geometry proxy or
source-part substitution. FreeCAD 1.1.4 ShapeBinder.cpp is the implementation.
"""
from copy import deepcopy
import re

from .fem_edit import _native_type, _target
from .motion import _pose

OPTIONS = {'Relative': True, 'BindMode': 'Synchronized', 'Fuse': False,
           'Refine': False, 'MakeFace': False, 'BindCopyOnChange': 'Disabled'}
KEY = 'assembly_analyses'


def source_of(occurrence):
    if not occurrence.isDerivedFrom('App::Link'):
        raise ValueError('Use a direct native Link occurrence for this Assembly study')
    if int(getattr(occurrence, 'ElementCount', 0)) != 0:
        raise ValueError('Link arrays need a separate occurrence study')
    if float(getattr(occurrence, 'Scale', 1.)) != 1.:
        raise ValueError('Scaled occurrences are not supported by the rigid pose study')
    scale = getattr(occurrence, 'ScaleVector', None)
    if scale is not None and any(float(v) != 1. for v in (scale.x, scale.y, scale.z)):
        raise ValueError('Non-unit occurrence scale is not a rigid pose')
    source = occurrence.LinkedObject
    if (source is None or isinstance(source, tuple) or source.Document is not occurrence.Document
            or source.isDerivedFrom('App::Link') or source.isDerivedFrom('Assembly::AssemblyObject')
            or not source.isDerivedFrom('Part::Feature')):
        raise ValueError('Use a direct solid part in this document; nested/external links need a separate study')
    shape = source.Shape.copy(True, False)
    if shape.isNull() or not shape.isValid() or len(shape.Solids) != 1:
        raise ValueError('Each occurrence must refer to one valid native solid')
    return source


def binding(owner, analysis_id):
    item = owner.read_metadata().get(KEY, {}).get(analysis_id)
    if not item:
        raise ValueError('조립 형상 연결…에서 이 해석의 두 인스턴스를 연결하세요.')
    return deepcopy(item)


def _number(value):
    return float(value.Value if hasattr(value, 'Value') else value)


def validate_body(owner, assembly, row):
    occurrence, body = owner._object(row['occurrence_id']), owner._object(row['body_id'])
    source = source_of(occurrence)
    if source.Name != row['source_id'] or occurrence not in owner.motion._parts(assembly):
        raise ValueError('The analysis occurrence or linked part changed')
    if (body.TypeId != 'PartDesign::SubShapeBinder'
            or [(obj, tuple(names)) for obj, names in body.Support] != [(assembly, (occurrence.Name + '.',))]
            or _pose(body.Placement) != [0., 0., 0., 0., 0., 0., 1.]
            or body.getParentGeoFeatureGroup() is not None
            or any(getattr(body, key) != value for key, value in OPTIONS.items())
            or _number(body.Offset) != 0.):
        raise ValueError('Analysis geometry binding changed; restore its exact occurrence support')
    if getattr(body, 'ExpressionEngine', []):
        raise ValueError('Expression-controlled analysis geometry needs an explicit supported binding')
    return occurrence, body, source


def element_pairs(owner, assembly, row, family='Face'):
    """Resolve native feature history to the exact linked source, across saves.

    A binder's restored TShape is distinct from its source TShape. Pointer
    identity (isSame/isPartner) is therefore not a persisted correspondence.
    """
    occurrence, body, source = validate_body(owner, assembly, row)
    if family == 'Solid':
        # Whole support of one admitted solid, not an invented Solid element map.
        # FreeCAD's mapped element histories cover faces/edges/vertices.
        if len(body.Shape.Solids) != 1 or len(source.Shape.Solids) != 1:
            raise ValueError('Whole occurrence region requires exactly one native solid')
        return {'Solid1': 'Solid1'}
    plural = {'Face': 'Faces', 'Edge': 'Edges'}[family]
    originals = getattr(source.Shape, plural)
    result = {}
    for index, actual in enumerate(getattr(body.Shape, plural), 1):
        name = family + str(index)
        history = body.getElementHistory(name, recursive=True, sameType=True, showName=False)
        candidates = set()
        for origin, mapped, intermediates in history:
            if isinstance(origin, int):
                raise ValueError('Occurrence element history has an unresolved native owner')
            if origin is not source:
                continue
            local = str(source.Shape.getElementIndexedName(mapped))
            if not re.fullmatch(re.escape(family) + r'[1-9][0-9]*', local):
                raise ValueError('Occurrence history does not resolve to a native source element')
            if int(local[len(family):]) > len(originals):
                raise ValueError('Occurrence source element no longer exists')
            candidates.add(local)
        if len(candidates) != 1:
            raise ValueError('Occurrence element has no unique native source history')
        result[name] = next(iter(candidates))
    if len(result) != len(originals) or len(set(result.values())) != len(originals):
        raise ValueError('Occurrence geometry is missing, split or duplicates source topology')
    return result


def refresh_bindings(owner, analysis, expected=None, *, require_unchanged):
    """Execute only the native binders, with an exact saved-geometry guard.

    This checks native Support evaluation, not a hand-built transformed copy.
    No preference change, mesh admission, fingerprint replacement or file save.
    """
    record = binding(owner, analysis.Name)
    if expected is not None and record != expected:
        raise ValueError('Saved Assembly-to-Analysis association changed')
    assembly = owner._object(record['assembly_id'])
    before = {}
    for row in record['bodies']:
        _, body, _ = validate_body(owner, assembly, row)
        before[body.Name] = _target(body, [])
        if body.recompute() is not True:
            raise ValueError('Native occurrence analysis geometry failed to recompute')
        if require_unchanged and _target(body, []) != before[body.Name]:
            raise ValueError('Retained occurrence geometry differs from native Support evaluation; recompute and remesh')
    owner.doc.recompute()
    if require_unchanged:
        for row in record['bodies']:
            body = owner._object(row['body_id'])
            if _target(body, []) != before[body.Name]:
                raise ValueError('Occurrence geometry changed during native recompute')
    return inspect_bindings(owner, analysis, expected)


def inspect_bindings(owner, analysis, expected=None):
    record = binding(owner, analysis.Name)
    if expected is not None and record != expected:
        raise ValueError('Saved Assembly-to-Analysis association changed')
    assembly = owner._object(record['assembly_id'])
    parts = owner.motion._parts(assembly)
    if {row['occurrence_id'] for row in record['bodies']} != {part.Name for part in parts}:
        raise ValueError('Analysis must contain both distinct Assembly occurrences')
    meshes = [obj for obj in analysis.Group if hasattr(obj, 'FemMesh') and not getattr(obj, 'Suppressed', False)]
    if {mesh.Name for mesh in meshes} != {row['mesh_id'] for row in record['bodies']}:
        raise ValueError('Analysis has missing or extra active meshes for its occurrences')
    for row in record['bodies']:
        _, body, _ = validate_body(owner, assembly, row)
        mesh = owner._object(row['mesh_id'])
        if _native_type(mesh) != 'Fem::FemMeshGmsh' or mesh.Shape is not body:
            raise ValueError('Mesh must use the selected occurrence analysis shape')
        element_pairs(owner, assembly, row, 'Face')
        # Any geometric FEM reference must belong to an admitted occurrence.
    allowed = {row['body_id'] for row in record['bodies']}
    for obj in analysis.Group:
        for ref in getattr(obj, 'References', []):
            if ref[0].Name not in allowed:
                raise ValueError(obj.Label + ': select the occurrence analysis shape, not the original part')
        direction = getattr(obj, 'Direction', None)
        if direction and direction[0].Name not in allowed:
            raise ValueError(obj.Label + ': direction reference is outside the occurrence analysis')
    return record


def connect(owner, analysis, assembly):
    """Explicit user operation; fresh Analysis or exact existing binding only."""
    owner.before_design_action('connect Assembly analysis geometry')
    existing = owner.read_metadata().get(KEY, {}).get(analysis.Name)
    if existing:
        if existing['assembly_id'] != assembly.Name:
            raise ValueError('This Analysis already belongs to another Assembly')
        return inspect_bindings(owner, analysis)
    if _native_type(analysis) != 'Fem::FemAnalysis':
        raise ValueError('Select a native FEM Analysis')
    # Never reinterpret original-part constraints as occurrence constraints.
    if any(hasattr(obj, 'FemMesh') or getattr(obj, 'References', []) for obj in analysis.Group):
        raise ValueError('Use an Analysis without meshes or face conditions; existing targets are preserved')
    from .assembly_candidates import structure
    _, parts, _, _ = structure(owner, assembly)
    import ObjectsFem
    result = {'assembly_id': assembly.Name, 'bodies': []}
    def change():
        for occurrence in parts:
            source = source_of(occurrence)
            body = owner.doc.addObject('PartDesign::SubShapeBinder', 'AnalysisOccurrence')
            body.Label = occurrence.Label + ' 해석 형상'
            for key, value in OPTIONS.items():
                setattr(body, key, value)
            body.Offset = 0.
            body.Placement = owner.App.Placement()
            body.Support = [(assembly, [occurrence.Name + '.'])]
            mesh = ObjectsFem.makeMeshGmsh(owner.doc, 'OccurrenceMesh')
            mesh.Label = occurrence.Label + ' 메시'
            mesh.Shape = body
            mesh.ElementOrder = '2nd'
            mesh.ElementDimension = '3D'
            analysis.addObject(mesh)
            if body.ViewObject:
                body.ViewObject.Visibility = False
            result['bodies'].append({'occurrence_id': occurrence.Name, 'source_id': source.Name,
                                    'body_id': body.Name, 'mesh_id': mesh.Name})
        data = owner.read_metadata()
        data.setdefault(KEY, {})[analysis.Name] = result
        owner.write_metadata(data)
    owner._transaction('Connect Assembly analysis geometry', change)
    return inspect_bindings(owner, analysis)


def capture_element(owner, body, names):
    """Optional exact occurrence anchor for the existing correspondence owner."""
    for record in owner.read_metadata().get(KEY, {}).values():
        row = next((item for item in record['bodies'] if item['body_id'] == body.Name), None)
        if row is None:
            continue
        assembly = owner._object(record['assembly_id'])
        _, _, source = validate_body(owner, assembly, row)
        from .candidate_correspondence import anchor
        elements = []
        for name in names:
            family = re.match(r'(Face|Edge|Solid)', name)[0]
            local_name = element_pairs(owner, assembly, row, family)[name]
            try:
                mapped, reason = anchor(source, local_name), None
            except (ValueError, RuntimeError, AttributeError, TypeError) as error:
                mapped, reason = None, str(error)
            elements.append({'name': local_name, 'mapped': mapped, 'unavailable': reason})
        return {'binding': deepcopy(row), 'assembly_id': assembly.Name,
                'source_target': _target(source, [item['name'] for item in elements]),
                'elements': elements}
    return None


def resolve_element(owner, saved):
    """Rigid unchanged source or the existing source mapped-history resolver."""
    row = saved['binding']
    assembly = owner._object(saved['assembly_id'])
    _, body, source = validate_body(owner, assembly, row)
    old = saved['source_target']
    names = [item['name'] for item in saved['elements']]
    if names == ['Solid1']:
        if len(source.Shape.Solids) != 1:
            raise ValueError('Whole occurrence source is no longer one solid')
        local_names, method = names, 'native_occurrence_whole_support'
    elif _target(source, names) == old:
        local_names, method = names, 'native_occurrence_rigid'
    else:
        from .candidate_correspondence import resolve
        if any(item['mapped'] is None for item in saved['elements']):
            raise ValueError('Changed occurrence source needs unambiguous native element history')
        _, local_names, _ = resolve(owner, {'target': old,
            'elements': [item['mapped'] for item in saved['elements']], 'history_unavailable': None})
        method = 'native_occurrence_mapped_element'
    mapped_names = []
    for name in local_names:
        family = re.match(r'(Face|Edge|Solid)', name)[0]
        mapping = element_pairs(owner, assembly, row, family)
        matches = [key for key, value in mapping.items() if value == name]
        if len(matches) != 1:
            raise ValueError('Occurrence reference is deleted or ambiguous')
        mapped_names.append(matches[0])
    return body, mapped_names, method
