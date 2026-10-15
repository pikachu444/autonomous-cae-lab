"""Regional native properties through ShellEditor and its existing transaction.

Actual ElementGeometry2D / ConstraintPressure objects are the property owners.
Their extra element list records explicit FE selection where CAD References
cannot express a subset.  It is compared on every freeze, never auto-rebound.
"""
from copy import deepcopy
import math

from caelab.shell_model import ShellError, issue, number, prepare_mesh, digest
from caelab.shell_regions import REGION_FIELDS, check_shape, reverse_region


def _extra(obj, kind, name):
    if name not in obj.PropertiesList:
        obj.addProperty(kind, name, 'CAE Lab 셸 영역')


def _ids(obj):
    values = list(getattr(obj, 'CAEElementIds', []))
    if any(type(e) is not int or e <= 0 for e in values) or len(values) != len(set(values)):
        raise ValueError(f'{obj.Label}: native 영역 요소 번호가 잘못됐습니다.')
    return sorted(values)


def state(editor, draft):
    from .shell_edit import SETTINGS, _refs
    _, by = editor._members(draft, complete=True)
    material = editor._object(draft['material_id'])
    if material.Category != 'Solid':
        raise ValueError('균질 등방 탄성 Solid 재료를 선택하세요.')
    rows = []
    for row in draft['regions']:
        section = editor._object(row['geometry_id'])
        pressure = editor._object(row['pressure_id'])
        axis = getattr(section, 'CAEAxisReference', None)
        if axis is None:
            raise ValueError(f'{row["label"]}: 국부축을 명시적으로 적용하세요.')
        rows.append({'id': row['id'], 'geometry_id': section.Name,
                     'pressure_id': pressure.Name,
                     'thickness_mm': float(section.Thickness.getValueAs('mm').Value),
                     'offset': float(section.Offset), 'section_refs': _refs(section),
                     'section_elements': _ids(section),
                     'axis': [float(axis.x), float(axis.y), float(axis.z)],
                     'orientation': section.CAENormalOrientation,
                     'pressure_MPa': float(pressure.Pressure.getValueAs('MPa').Value),
                     'pressure_reversed': bool(pressure.Reversed),
                     'pressure_amplitude': bool(pressure.EnableAmplitude),
                     'pressure_refs': _refs(pressure), 'pressure_elements': _ids(pressure)})
    return {'members': sorted([k, o.Name] for k, items in by.items() for o in items),
            'solver': {k: getattr(editor._object(draft['solver_id']), k) for k in SETTINGS},
            'material': dict(material.Material), 'material_refs': _refs(material),
            'regions': rows, 'pressure_amplitude': any(r['pressure_amplitude'] for r in rows),
            'binding': editor._stamp(draft)}


def verify_assigned_state(draft, observed):
    """Validate exactly declared targets, including native edits between Apply calls."""
    if len(draft['regions']) != len(observed['regions']):
        raise ValueError('native 영역 개수가 편집 초안과 다릅니다.')
    for row, actual in zip(draft['regions'], observed['regions']):
        if row['id'] != actual['id'] or row['geometry_id'] != actual['geometry_id'] or row['pressure_id'] != actual['pressure_id']:
            raise ValueError('native 영역 순서/소유자가 편집 초안과 다릅니다.')
        path = 'regions/'+row['id']
        ids = sorted(row['elements'])
        if actual['section_elements'] != ids or actual['pressure_elements'] != ids:
            raise ShellError([issue(path+'/elements', 'native 요소 할당이 편집 초안과 다릅니다.')])
        if actual['section_refs'] != row['face_refs'] or actual['pressure_refs'] != row['face_refs']:
            raise ShellError([issue(path+'/face_refs', 'native 면 참조가 편집 초안과 다릅니다.')])
        expected = {'thickness_mm': number(row['thickness_mm']), 'offset': number(row['offset']),
                    'pressure_MPa': abs(number(row['pressure_MPa']))}
        for key, value in expected.items():
            if abs(actual[key]-value) > 8*math.ulp(value):
                raise ShellError([issue(path+'/'+key, 'native 속성이 입력값을 그대로 받지 않았습니다.')])
        if (actual['orientation'] != row['orientation'] or
                actual['pressure_reversed'] != (number(row['pressure_MPa']) < 0) or
                actual['pressure_amplitude'] or
                actual['axis'] != [number(row['axis_'+c]) for c in 'xyz']):
            raise ShellError([issue(path, 'native 법선/축/압력 조건이 입력과 다릅니다.')])


def apply(editor, analysis_id):
    import ObjectsFem
    from .shell_edit import SETTINGS
    record = editor._record(analysis_id)
    draft = record['draft']
    editor._binding(draft)
    analysis, _ = editor._members(draft)
    _, nodes, elements = editor._mesh(draft)
    prepared = prepare_mesh(nodes, elements, draft)
    editor._fixed(draft, prepared)

    def change():
        if not draft.get('material_id'):
            obj = ObjectsFem.makeMaterialSolid(editor.owner.doc)
            obj.Label = '판재 공통 재료'; analysis.addObject(obj)
            draft['material_id'] = obj.Name
        material = editor._object(draft['material_id'])
        values = dict(material.Material)
        values.setdefault('Name', material.Label)
        values.update(YoungsModulus=format(number(draft['young_MPa']), '.17g')+' MPa',
                      PoissonRatio=format(number(draft['poisson']), '.17g'))
        material.Material = values; material.References = []
        for row in draft['regions']:
            for key, constructor, suffix in (
                    ('geometry_id', ObjectsFem.makeElementGeometry2D, ' 단면'),
                    ('pressure_id', ObjectsFem.makeConstraintPressure, ' 압력')):
                if not row[key]:
                    obj = constructor(editor.owner.doc)
                    obj.Label = row['label']+suffix
                    analysis.addObject(obj); row[key] = obj.Name
            section = editor._object(row['geometry_id'])
            pressure = editor._object(row['pressure_id'])
            references = [(editor._object(r['object_id']), tuple(r['subelements'])) for r in row['face_refs']]
            section.Thickness = format(number(row['thickness_mm']), '.17g')+' mm'
            section.Offset = number(row['offset'])
            pressure.Pressure = format(abs(number(row['pressure_MPa'])), '.17g')+' MPa'
            pressure.Reversed = number(row['pressure_MPa']) < 0
            pressure.EnableAmplitude = False
            for obj in (section, pressure):
                obj.References = references
                _extra(obj, 'App::PropertyIntegerList', 'CAEElementIds')
                obj.CAEElementIds = sorted(row['elements'])
            _extra(section, 'App::PropertyString', 'CAENormalOrientation')
            _extra(section, 'App::PropertyVector', 'CAEAxisReference')
            section.CAENormalOrientation = row['orientation']
            section.CAEAxisReference = editor.owner.App.Vector(*[number(row['axis_'+c]) for c in 'xyz'])
        for key, value in SETTINGS.items():
            setattr(editor._object(draft['solver_id']), key, value)
        observed = state(editor, draft)
        verify_assigned_state(draft, observed)
        record['draft'] = deepcopy(draft)
        record['applied'] = {'draft': deepcopy(draft), 'native': observed}
        data = editor._all(); data['shells'][analysis_id] = record
        editor.owner.write_metadata(data)
    editor.owner._transaction('CAE Lab 셸 영역 속성 적용', change)
    return editor.inspect(analysis_id)


def import_properties(editor, analysis_id):
    """Explicit native-to-draft import; never silently updates the applied stamp."""
    record = editor._record(analysis_id); draft = record['draft']
    from .shell_edit import native_type
    analysis = editor._object(analysis_id)
    active = [o for o in analysis.Group if not getattr(o, 'Suppressed', False)]
    sections = {o.Name for o in active if native_type(o) == 'Fem::ElementGeometry2D'}
    pressures = {o.Name for o in active if native_type(o) == 'Fem::ConstraintPressure'}
    if ('regions' not in draft or
            sections != {r['geometry_id'] for r in draft['regions'] if r['geometry_id']} or
            pressures != {r['pressure_id'] for r in draft['regions'] if r['pressure_id']}):
        # This is an explicit import, not an automatic repair. Discover the
        # actual assignments, but never refresh an existing geometry binding.
        return begin_regions(editor, draft, analysis, retain_binding=True)
    actual = state(editor, draft)
    for row, current in zip(draft['regions'], actual['regions']):
        if current['section_elements'] != current['pressure_elements'] or current['section_refs'] != current['pressure_refs']:
            raise ShellError([issue('regions/'+row['id'], '단면과 압력의 실제 할당이 다릅니다. native 참조를 먼저 복구하세요.')])
        if current['pressure_amplitude']:
            raise ValueError('시간 진폭 압력은 이 선형 정적 영역 경로에 불러올 수 없습니다.')
        row.update(elements=current['section_elements'], face_refs=current['section_refs'],
                   thickness_mm=str(current['thickness_mm']), offset=str(current['offset']),
                   pressure_MPa=str(current['pressure_MPa']*(-1 if current['pressure_reversed'] else 1)),
                   orientation=current['orientation'])
        row.update({'axis_'+c: str(v) for c, v in zip('xyz', current['axis'])})
    material = editor._object(draft['material_id'])
    # Material conversion follows the existing FreeCAD Units parser.
    draft['young_MPa'] = str(editor.owner.App.Units.Quantity(material.Material['YoungsModulus']).getValueAs('MPa').Value)
    draft['poisson'] = str(number(material.Material['PoissonRatio']))
    record.pop('applied', None)
    editor._store(analysis_id, record, 'native 셸 영역 불러오기')
    return editor.inspect(analysis_id)


def selection(editor, analysis_id):
    """Read current native faces, without changing a draft, mesh, or document."""
    from .shell_edit import _global_shape
    draft = editor._record(analysis_id)['draft']
    mesh, _, elements = editor._mesh(draft)
    refs, selected = [], set()
    for picked in editor.owner.Gui.Selection.getSelectionEx():
        if picked.Object.Document is not editor.owner.doc:
            raise ValueError('현재 문서에서 영역의 면을 선택하세요.')
        if picked.Object is mesh and not picked.SubElementNames:
            selected.update(draft['elements']); continue
        names = list(picked.SubElementNames)
        if not names:
            raise ValueError('전체 CAD 물체가 아니라 실제 면을 선택하세요.')
        for name in names:
            if not name.startswith('Face'):
                raise ValueError('영역에는 실제 면만 선택하세요.')
            nodes = set(map(int, mesh.FemMesh.getNodesByFace(_global_shape(picked.Object, name))))
            found = {e for e, conn in elements.items() if set(conn) <= nodes}
            if not found:
                raise ValueError(f'{picked.Object.Label}/{name}: 대응 S8 요소가 없습니다.')
            selected.update(found)
        refs.append({'object_id': picked.Object.Name, 'subelements': names})
    if not selected or not selected <= set(draft['elements']):
        raise ValueError('현재 참여 셸 집합 안의 면/메시를 선택하세요.')
    return {'elements': sorted(selected), 'face_refs': refs}


def check_reversal_edit(before, after):
    """A text save cannot turn a normal without the reference-plane contract."""
    originals = {row['id']: row for row in before}
    for row in after:
        old = originals.get(row['id'])
        if not old or row['orientation'] == old['orientation'] or not old['orientation']:
            continue
        if {old['orientation'], row['orientation']} != {'native', 'reversed'}:
            raise ValueError('영역의 법선 반전 명령을 사용하세요.')
        if (number(row['offset']) != -number(old['offset']) or
                number(row['pressure_MPa']) not in (number(old['pressure_MPa']), -number(old['pressure_MPa']))):
            raise ValueError('offset/압력 수정은 먼저 초안에 저장하고 법선 반전 명령을 사용하세요.')


def begin_regions(editor, draft, analysis, *, retain_binding=False):
    """Explicit import of native sections. Overlaps remain visible draft errors.

    Each existing pressure must correspond to exactly one section selection.
    Unresolved or overlapping native owners are never chosen by list order.
    No native object, property, mesh or applied stamp is changed during import.
    """
    from .shell_edit import native_type, _refs, _global_shape
    from caelab.shell_model import DEFAULTS
    from caelab.shell_regions import uniform_region
    active = [o for o in analysis.Group if not getattr(o, 'Suppressed', False)]
    sections = [o for o in active if native_type(o) == 'Fem::ElementGeometry2D']
    if not sections:
        raise ValueError('불러올 native 셸 단면 객체가 없습니다. 초안을 유지합니다.')
    previous = draft.get('regions', [uniform_region(draft)])
    previous_by_object = {}
    for row in previous:
        if row['geometry_id']:
            previous_by_object.setdefault(row['geometry_id'], []).append(row)
    materials = [o for o in active if native_type(o) == 'Fem::MaterialCommon']
    pressures = [o for o in active if native_type(o) == 'Fem::ConstraintPressure']
    if len(materials) > 1:
        raise ShellError([issue('material_id', '다중 native 재료 할당은 이 균질 영역 경로에 지원하지 않습니다. 명시적으로 분리하세요.')])
    mesh, _, elements = editor._mesh(draft)
    def targets(obj):
        refs = _refs(obj)
        if 'CAEElementIds' in obj.PropertiesList:
            chosen = _ids(obj)
        elif refs:
            chosen = set()
            for ref in refs:
                for name in ref['subelements']:
                    if not name.startswith('Face'):
                        raise ValueError(obj.Label+': 실제 면 참조가 필요합니다.')
                    ns = set(map(int, mesh.FemMesh.getNodesByFace(_global_shape(editor._object(ref['object_id']), name))))
                    es = {e for e, conn in elements.items() if set(conn) <= ns}
                    if not es:
                        raise ValueError(obj.Label+': 면에 대응하는 완전한 S8 요소가 없습니다.')
                    chosen.update(es)
            chosen = sorted(chosen)
        else:
            chosen = sorted(elements)
        if not chosen or not set(chosen) <= set(elements):
            raise ValueError(obj.Label+': native 요소 할당이 현재 메시와 다릅니다.')
        return chosen, refs
    section_targets = [(obj, *targets(obj)) for obj in sections]
    pressure_targets = [(obj, *targets(obj)) for obj in pressures]
    matched = {}
    for p, pe, pr in pressure_targets:
        matches = [g.Name for g, ge, gr in section_targets if ge == pe and gr == pr]
        if len(matches) != 1 or matches[0] in matched:
            raise ShellError([issue(p.Label, '압력과 단면의 native 할당이 일대일이 아닙니다. 압력 집합을 명시적으로 분리/복구하세요.')])
        matched[matches[0]] = p
    draft.update(elements=sorted(elements), face_refs=[], geometry_id=None, pressure_id=None,
                 material_id=materials[0].Name if materials else None)
    regions = []
    for i, (g, ge, gr) in enumerate(section_targets):
        previous_rows = previous_by_object.get(g.Name, [])
        old = previous_rows[0] if len(previous_rows) == 1 else None
        row = uniform_region(draft, region_id='R'+str(i+1), label=old['label'] if old else g.Label)
        p = matched.get(g.Name)
        row.update(elements=ge, face_refs=gr, geometry_id=g.Name,
                   pressure_id=p.Name if p else '', thickness_mm=str(g.Thickness.getValueAs('mm').Value),
                   offset=str(g.Offset), orientation=getattr(g, 'CAENormalOrientation', old['orientation'] if old else 'native'),
                   pressure_MPa=str(p.Pressure.getValueAs('MPa').Value*(-1 if p.Reversed else 1)) if p else '0')
        if p and p.EnableAmplitude:
            raise ValueError(p.Label+': 시간 진폭 압력은 이 정적 경로에 불러올 수 없습니다.')
        axis = getattr(g, 'CAEAxisReference', None)
        if axis is not None:
            row.update({'axis_'+c: str(getattr(axis, c)) for c in 'xyz'})
        regions.append(row)
    draft['regions'] = regions
    if materials:
        m = materials[0]
        try:
            draft['young_MPa'] = str(editor.owner.App.Units.Quantity(m.Material['YoungsModulus']).getValueAs('MPa').Value)
            draft['poisson'] = str(m.Material['PoissonRatio'])
        except (KeyError, ValueError, TypeError):
            draft['young_MPa'] = draft['poisson'] = ''
    editor._members(draft)
    if not retain_binding:
        draft['binding'] = editor._stamp(draft)
    # An existing binding (including a missing/stale one) is never refreshed
    # by a property import. Changed geometry still needs explicit rebind.
    # This explicit native import is a draft, not Apply or a READY admission.
    editor._store(analysis.Name, {'draft': draft, 'applied': None}, 'native 셸 영역 초안 불러오기')
    return editor.inspect(analysis.Name)
