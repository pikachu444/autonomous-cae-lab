"""Owner-thread read/verify/select adapter for original comparison samples.

All native data come from existing Workspace bundles/readers. No snapshot export,
curve comparison, imported Data job, Report asset, or solver is created here.
"""
from copy import deepcopy
import json
import os
from pathlib import Path

from caelab import post_curves
from caelab.post_curve_origin import RAW_FIELDS, raw_record, targets, unique, verify_curve
from caelab.post_observation import (MAX_BYTES, MAX_ROWS, check_pin, file_pin,
    saved_record, verify_origin, project_samples)
from caelab.storage import canonical_hash


def _saved_project(ws):
    owner = ws.owner
    owner.assert_thread()
    path = owner.project_path.resolve(strict=True)
    if not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError('저장 Post 프로젝트가 없거나 읽기 한도를 초과합니다.')
    pin = file_pin(path)
    with path.open('rb') as stream:
        data = stream.read(MAX_BYTES+1)
    import hashlib
    if len(data) != pin['bytes'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
        raise ValueError('저장 프로젝트를 읽는 중 파일이 변경되었습니다.')
    project = json.loads(data.decode('utf-8-sig'))
    if project.get('document_id') != owner.document_id:
        raise ValueError('현재 owner와 실제 저장 프로젝트가 다릅니다.')
    workspace = file_pin(path.parent / project['workspace_file'])
    if workspace['sha256'] != project.get('workspace_sha256'):
        raise ValueError('저장 workspace가 변경되었습니다. 같은 원파일을 복원하세요.')
    check_pin(pin)
    return project, pin, workspace


def _saved_applied(project, obj, record):
    saved_obj = project.get('analysis', {}).get('objects', {}).get(obj['id'])
    if not isinstance(saved_obj, dict) or saved_obj.get('kind') != obj['kind']:
        raise ValueError('현재 분석이 저장 프로젝트에 없습니다. 먼저 적용하고 저장하세요.')
    history, position = saved_obj.get('history', []), saved_obj.get('position', -1)
    if type(position) is not int or not 0 <= position < len(history):
        raise ValueError('적용한 결과를 저장한 뒤 원자료를 여세요.')
    saved = history[position]
    keys = ('id', 'recipe', 'graph', 'bindings', 'summary', 'result_file', 'result_files', 'result_sha256')
    if (any(saved.get(k) != record.get(k) for k in keys)
            or not saved.get('result_files') or not saved.get('result_sha256')
            or obj.get('draft') != record.get('recipe')
            or saved_obj.get('draft') != saved.get('recipe')):
        raise ValueError('현재/저장 개정이나 미적용 편집이 다릅니다. 원 편집을 보존했습니다.')
    for pin in saved['result_files']:
        check_pin(pin)
    entry = next((pin for pin in saved['result_files']
                  if Path(pin['path']).resolve() == Path(saved['result_file']).resolve()), None)
    if entry is None or entry['sha256'] != saved['result_sha256']:
        raise ValueError('정확한 저장 결과 entry가 pin 목록에 없습니다.')
    return saved


def _original_dependencies(ws, obj, record, seen=None):
    """Retained-only fallback permits viewing, not silent origin verification.

    Walk the existing revision bindings so missing PVD frames/sidecars cannot be
    hidden by an intact derived table. Reading still uses _verify_inputs.
    """
    seen = set() if seen is None else seen
    if record['id'] in seen:
        raise ValueError('원자료 의존이 순환합니다.')
    seen.add(record['id'])
    try:
        refs = ws._refs(obj['kind'], record['recipe'])
        revisions = ws._retained_dependencies(record, refs)
        ws._verify_inputs(refs, revisions=revisions)
        for ref in refs:
            if ref in ws.document.get('sources', {}):
                continue
            upstream = ws.object(ref)
            matches = [r for r in upstream['history'] if r['id'] == revisions.get(ref)]
            if len(matches) != 1:
                raise ValueError('원자료의 정확한 의존 개정이 없습니다.')
            _original_dependencies(ws, upstream, matches[0], seen)
    finally:
        seen.remove(record['id'])


def saved_origin(ws, obj, record):
    """A REAL saved-owner receipt; minimal curve origin is not cast to fullpin."""
    project, project_pin, workspace_pin = _saved_project(ws)
    saved = _saved_applied(project, obj, record)
    if obj['kind'] != 'measurement':
        raise ValueError('원 측정 record가 필요합니다.')
    _original_dependencies(ws, obj, record)
    origin = {'kind': 'post_measurement', 'document_id': ws.owner.document_id,
        'session_id': ws.owner.session_id, 'pid': os.getpid(),
        'project': project_pin, 'workspace': workspace_pin, 'object_ref': obj['id'],
        'revision': saved['id'], 'recipe_sha256': canonical_hash(saved['recipe']),
        'result_files_sha256': canonical_hash(saved['result_files']),
        'result_sha256': saved['result_sha256']}
    verify_origin(origin)
    return origin


def _idle(ws, expected_view_generation):
    owner = ws.owner
    owner.assert_thread(); owner.refresh()
    if (type(expected_view_generation) is not int or expected_view_generation != owner.view_generation
            or getattr(owner, 'closed', False)):
        raise ValueError('원창의 선택/표시가 바뀌었습니다. 다시 확인하세요.')
    state = owner.snapshot
    items = [*state.get('sources', []), *state.get('views', []),
             *state.get('representations', {}).values()]
    if any(item.get('pending_properties') for item in items):
        raise ValueError('미적용 native 속성 편집이 있습니다. 편집을 덮지 않았습니다.')
    return owner.generation, owner.view_generation


def read(ws, *, object_ref, revision, table, row_index, expected_view_generation):
    """Read one saved comparison selection and its actual originals, no mutation."""
    start = _idle(ws, expected_view_generation)
    obj = ws.object(object_ref); record, bundle = ws._bundle(obj)
    if obj['kind'] != 'comparison' or record['recipe'].get('version') != 3 or record['id'] != revision:
        raise ValueError('현재 저장된 v3 비교를 선택하세요. 미리보기/다른 개정은 열지 않습니다.')
    project, project_pin, workspace_pin = _saved_project(ws)
    _saved_applied(project, obj, record)
    _original_dependencies(ws, obj, record)
    try:
        from . import curve_native
    except ImportError:
        import curve_native
    # B brackets can lie on a page other than the selected A row. Read all bounded
    # retained original pages, not a guessed B index or a newly interpolated row.
    payload = {'semantics': 'retained_curve_comparison', 'summary': deepcopy(record['summary']),
               'rows': [], 'originals': {'a': [], 'b': []}}
    total = max(record['summary']['count_a'], record['summary']['count_b'])
    if type(total) is not int or not 1 <= total <= MAX_ROWS:
        raise ValueError('비교 원행 수가 읽기 한도를 초과합니다.')
    for offset in range(0, total, 1000):
        page = curve_native.sample(bundle, offset=offset, limit=1000)
        payload['rows'].extend(page['rows'])
        for tag in ('a', 'b'):
            payload['originals'][tag].extend(page['originals'][tag])
    result = targets(payload, table, row_index)
    for target in result:
        source = curve_native.selected(ws, target['selector'])
        verify_curve(source, target)
        if 'reference' in target['origin']:
            target['kind'] = 'data_curve'
        else:
            source_obj = ws.object(target['selector']['source_ref'])
            source_record, _ = ws._bundle(source_obj)
            target['kind'] = 'native_curve'
            target['saved_origin'] = saved_origin(ws, source_obj, source_record)
    # Bound receipt; raw rows and lineage strings do not confer owner authority.
    if len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode()) > 128*1024:
        raise ValueError('선택 원행의 설명이 명령 영수증 한도를 초과합니다.')
    check_pin(project_pin); check_pin(workspace_pin)
    ws._verify_record(obj, record, bundle)
    _original_dependencies(ws, obj, record)
    ws.owner.refresh()
    if start != (ws.owner.generation, ws.owner.view_generation):
        raise ValueError('원행을 읽는 중 owner/표시가 바뀌었습니다.')
    return {'status': 'ORIGINALS_READ', 'object_ref': object_ref, 'revision': revision,
            'preview': False, 'table': table, 'row_index': row_index, 'targets': result,
            'generation': start[0], 'view_generation': start[1],
            'project': project_pin, 'workspace': workspace_pin}


def _native_rows(ws, record, bundle):
    try:
        from . import measurements, contact_views
    except ImportError:
        import measurements, contact_views
    rows, total = [], None
    while total is None or len(rows) < total:
        page = contact_views.annotate(measurements.sample_data(bundle['source'], offset=len(rows), limit=1000,
            declarations=record['summary'].get('declarations')), record['summary'])
        count = page.get('total', page.get('count'))
        if (type(count) is not int or not 1 <= count <= MAX_ROWS or (total is not None and total != count)
                or not page.get('rows') or len(rows)+len(page['rows']) > count):
            raise ValueError('원측정 표가 불완전하거나 읽는 동안 변경되었습니다.')
        total = count; rows.extend(page['rows'])
    return rows


def _resolve(ws, target):
    origin = target['saved_origin'] if target.get('kind') == 'native_curve' else target['origin']
    project, _, saved = verify_origin(origin)
    if (ws.owner.document_id != origin['document_id']
            or ws.owner.project_path.resolve() != check_pin(origin['project'])):
        raise ValueError('다른 owner/저장 프로젝트입니다. 현재 원창을 바꾸지 않았습니다.')
    obj = ws.object(origin['object_ref']); record, bundle = ws._bundle(obj)
    _saved_applied(project, obj, record)
    if record['id'] != origin['revision']:
        raise ValueError('과거 exact record가 현재 선택에 없습니다. 최신 개정으로 대신 열지 않습니다.')
    _original_dependencies(ws, obj, record)
    if target.get('kind') == 'native_curve':
        try:
            from .curve_native import selected
        except ImportError:
            from curve_native import selected
        curve = selected(ws, target['selector'])
        raw = verify_curve(curve, target)
        selection = {'block': deepcopy(target['selector']['block']),
            'value_array': target['selector']['column'], 'value_component': target['selector']['component'],
            'axis': {'kind': 'array', 'name': target['selector']['axis_column'], 'component': None}}
        native_identity = deepcopy(raw['identity'])
        rows = _native_rows(ws, record, bundle)
        matches = [r for r in rows if r.get('row') == native_identity['row'] and r.get('block') == native_identity['block']]
        if len(matches) != 1:
            raise ValueError('선택한 위치의 정확 원행이 없거나 중복됩니다.')
        native = matches[0]
    elif target.get('kind') == 'measurement_lineage':
        rows = _native_rows(ws, record, bundle)
        snapshot = {'recipe': saved['recipe'], 'summary': saved['summary'], 'rows': rows, 'origin': origin}
        if canonical_hash(saved['summary']) != target['summary_sha256']:
            raise ValueError('측정 계보의 단위·기저·축 선언이 변경되었습니다.')
        converted = project_samples(snapshot, target['selection'])
        mapping = unique(converted['origin']['row_identity'], 'source_row', target['mapping']['source_row'])
        if mapping != target['mapping'] or converted['origin']['native_column'] != target['native_column']:
            raise ValueError('시험 CSV 행과 native 원행/성분의 실제 계보가 다릅니다.')
        native_identity = mapping['native']; selection = deepcopy(target['selection'])
        matches = [r for r in rows if (all(r.get(k) == v for k, v in native_identity.items()))]
        if len(matches) != 1:
            raise ValueError('측정의 exact native 원행을 하나로 선택할 수 없습니다.')
        native = matches[0]
        projected = unique(converted['rows'], 'source_row', mapping['source_row'])
        raw = {'identity': deepcopy(native_identity), 'raw_x': projected['axis'], 'raw_y': projected['value'],
               'quality': projected['valid'], 'quality_reason': projected['reason']}
    else:
        raise ValueError('정확한 native 측정 origin만 열 수 있습니다. 일반 시험 자료는 Data에서 여세요.')
    verify_origin(origin); ws._verify_record(obj, record, bundle)
    _original_dependencies(ws, obj, record)
    return origin, obj, record, bundle, selection, native, raw


def verify(ws, *, target, expected_view_generation):
    start = _idle(ws, expected_view_generation)
    origin, obj, record, bundle, selection, native, raw = _resolve(ws, target)
    ws.owner.refresh()
    if start != (ws.owner.generation, ws.owner.view_generation):
        raise ValueError('검증 중 원창이 변경되었습니다. 선택은 하지 않았습니다.')
    return {'status': 'SOURCE_VERIFIED', 'target_sha256': canonical_hash(target),
        'origin_sha256': canonical_hash(origin), 'object_ref': obj['id'], 'revision': record['id'],
        'result_sha256': record['result_sha256'], 'native_pid': os.getpid(),
        'generation': start[0], 'view_generation': start[1], 'selection': selection,
        'row': deepcopy(native), 'raw': deepcopy(raw), 'clock_changed': False}


def _native_leaf(source, native):
    """Resolve the actual fetched leaf and its VTK flat index, never a solver ID."""
    from paraview import servermanager
    session = source.SMProxy.GetSession()
    if session.GetNumberOfProcesses(session.DATA_SERVER) != 1:
        raise ValueError('분산 결과의 행 번호를 단일 프로세스 번호로 추정하지 않습니다.')
    data = servermanager.Fetch(source)
    block = native.get('block', [])
    leaf = data
    for index in block:
        if type(index) is not int or index < 0 or not hasattr(leaf, 'GetNumberOfBlocks') or index >= leaf.GetNumberOfBlocks():
            raise ValueError('원행의 실제 native block 경로가 없습니다.')
        leaf = leaf.GetBlock(index)
    if leaf is None:
        raise ValueError('원행 block이 비어 있습니다.')
    field = 'ROW' if hasattr(leaf, 'GetNumberOfRows') else 'POINT'
    count = leaf.GetNumberOfRows() if field == 'ROW' else leaf.GetNumberOfPoints()
    row = native.get('row', native.get('point_index'))
    if type(row) is not int or not 0 <= row < count:
        raise ValueError('원행 번호가 native block 범위 밖에 있습니다.')
    if not block:
        return leaf, None, field, row
    iterator = data.NewIterator(); iterator.InitTraversal()
    matches = []
    while not iterator.IsDoneWithTraversal():
        if iterator.GetCurrentDataObject() == leaf:
            matches.append(iterator.GetCurrentFlatIndex())
        iterator.GoToNextItem()
    if len(matches) != 1:
        raise ValueError('native block의 평탄 인덱스가 모호합니다. 다른 위치를 선택하지 않았습니다.')
    return leaf, matches[0], field, row


def _highlight(source, native):
    """Use the existing ParaView index-selection API on the resolved exact leaf."""
    from paraview.selection import SelectIDs, SelectCompositeDataIDs
    _, flat_index, field, row = _native_leaf(source, native)
    source.SMProxy.SetSelectionInput(0, None, 0)  # rollback retains the previous exact selection
    if 'point_index' in native and 'block' not in native:
        try:
            from .measurements import highlight_point
        except ImportError:
            from measurements import highlight_point
        highlight_point(source, native['point_index'])
    elif flat_index is None:
        SelectIDs(IDs=[0, row], FieldType=field, Source=source)
    else:
        SelectCompositeDataIDs(IDs=[flat_index, 0, row], FieldType=field, Source=source)
    if source.SMProxy.GetSelectionInput(0) is None:
        raise ValueError('native 원행 선택이 적용되지 않았습니다. 완료로 처리하지 않습니다.')


class _DisplayRollback:
    """Preserve the existing native scene on a failed exact-row presentation.

    We restore only properties this adapter/Workspace.show can touch and delete
    only proxies created during this request. A failed rollback stays an error,
    never an atomic-success claim. Data, readers and inputs are never deleted.
    """
    def __init__(self, source, record):
        from paraview import simple as p
        self.p, self.source, self.record = p, source, record
        self.record_before = deepcopy(record)
        self.active = p.GetActiveSource(), p.GetActiveView()
        self.views = list(p.GetViews())
        self.layouts = list(p.GetLayouts().values())
        self.representations = list(p.GetRepresentations().values())
        self.selection = source.SMProxy.GetSelectionInput(0)
        self.properties = []
        for proxy in [*self.views, *self.representations]:
            values = {}
            # Domain changes reset series defaults as well as block selectors.
            # Restore controlling properties before dependent series/style values.
            for name in ('AttributeType', 'Assembly', 'ArraySelectionMode',
                         'CompositeDataSetIndex', 'BlockSelectors', 'Visibility',
                         'UseIndexForXAxis', 'XArrayName', 'SeriesVisibility',
                         'SeriesLabel', 'SeriesColor', 'SeriesOpacity', 'SeriesPlotCorner',
                         'SeriesLineStyle', 'SeriesLineThickness', 'SeriesMarkerStyle',
                         'SeriesMarkerSize', 'ChartTitle', 'LeftAxisTitle', 'BottomAxisTitle',
                         'SelectionOnly', 'ShowBlockName'):
                prop = proxy.GetProperty(name)
                if prop is not None and hasattr(prop, 'GetData'):
                    values[name] = deepcopy(prop.GetData())
            self.properties.append((proxy, values))

    def restore(self):
        p = self.p
        errors = []
        def attempt(fn):
            try: fn()
            except Exception as error: errors.append(str(error))
        attempt(lambda: self.source.SMProxy.SetSelectionInput(0, self.selection, 0))
        for proxy, values in self.properties:
            groups = (('AttributeType', 'Assembly', 'ArraySelectionMode'),
                      ('CompositeDataSetIndex', 'BlockSelectors'))
            controls = {name for group in groups for name in group}
            for group in (*groups, tuple(name for name in values if name not in controls)):
                changed = False
                for name in group:
                    if name in values:
                        def put(proxy=proxy, name=name, value=values[name]):
                            if _property_data(proxy, name) != value:
                                setattr(proxy, name, value)
                        attempt(put); changed = True
                if changed:
                    attempt(proxy.UpdateVTKObjects)
                    attempt(proxy.SMProxy.UpdatePropertyInformation)
            attempt(lambda proxy=proxy, values=values: _check_properties(proxy, values))
        for proxy in list(p.GetRepresentations().values()):
            if proxy not in self.representations: attempt(lambda proxy=proxy: p.Delete(proxy))
        for proxy in list(p.GetViews()):
            if proxy not in self.views: attempt(lambda proxy=proxy: p.Delete(proxy))
        for proxy in list(p.GetLayouts().values()):
            if proxy not in self.layouts: attempt(lambda proxy=proxy: p.RemoveLayout(proxy))
        self.record.clear(); self.record.update(self.record_before)
        attempt(lambda: p.SetActiveSource(self.active[0]))
        attempt(lambda: p.SetActiveView(self.active[1]))
        # Redraw retained views, never recreate/delete an existing reader or window.
        for view in self.views:
            attempt(lambda view=view: p.Render(view))
        for proxy, values in self.properties:
            attempt(lambda proxy=proxy, values=values: _check_properties(proxy, values))
        if (self.source.SMProxy.GetSelectionInput(0) != self.selection
                or (p.GetActiveSource(), p.GetActiveView()) != self.active):
            errors.append('이전 선택/활성 source/view의 복원을 확인하지 못했습니다.')
        if errors:
            raise RuntimeError('표시 복원 미확정; 원파일/비교는 보존됨: '+'; '.join(errors))


def _property_data(proxy, name):
    prop = proxy.GetProperty(name)
    if prop is None or not hasattr(prop, 'GetData'):
        raise ValueError('원자료 표시 속성을 확인할 수 없습니다: '+name)
    value = prop.GetData()
    return list(value) if isinstance(value, (tuple, list)) else value


def _check_properties(proxy, checks):
    for name, expected in checks.items():
        actual = _property_data(proxy, name)
        # ParaView exposes scalar and repeatable single-element vectors differently.
        if isinstance(expected, (tuple, list)):
            actual = actual if isinstance(actual, list) else [actual]
            expected = list(expected)
        elif isinstance(actual, list) and len(actual) == 1:
            actual = actual[0]
        if actual != expected:
            raise ValueError('원 성분·축·block 표시 적용을 확인하지 못했습니다: '+name)


def _chart_choice(display, name, value):
    prop = display.GetProperty(name)
    if prop is None or value not in list(getattr(prop, 'Available', ())):
        raise ValueError('원자료 표시의 native domain이 지원하지 않습니다: '+name+' / '+value)
    setattr(display, name, value)
    _check_properties(display, {name: value})


def _selector_leaf(display, flat_index):
    prop = display.GetProperty('BlockSelectors')
    domain = prop.FindDomain('vtkSMDataAssemblyDomain') if prop is not None else None
    if domain is None or domain.GetDataAssemblyName() != 'Hierarchy' or domain.GetMode() != 0:
        raise ValueError('정확한 원 block의 Hierarchy domain을 확인할 수 없습니다.')
    hierarchy = domain.GetDataAssembly()
    selector = "//*[@cid='%s']" % flat_index
    nodes = list(hierarchy.SelectNodes([selector])) if hierarchy is not None else []
    if (len(nodes) != 1 or hierarchy.GetNumberOfChildren(nodes[0]) != 0
            or hierarchy.GetAttributeOrDefault(nodes[0], 'cid', '') != str(flat_index)
            or list(hierarchy.GetDataSetIndices(nodes[0], False)) != [flat_index]):
        raise ValueError('원 block selector가 정확히 한 native leaf를 가리키지 않습니다.')
    return selector


def _chart_block(display, flat_index):
    if flat_index is None:
        return {}
    if display.GetProperty('BlockSelectors') is not None:
        # cid is the iterator's flat composite ID, not a named-assembly node ID.
        _chart_choice(display, 'Assembly', 'Hierarchy')
        # A PROVEN singleton has no cross-block aggregation. This also avoids
        # guessing block-name suffixes in Individual Blocks series domains.
        _chart_choice(display, 'ArraySelectionMode', 'Merged Blocks')
        display.UpdateVTKObjects(); display.SMProxy.UpdatePropertyInformation()
        selector = _selector_leaf(display, flat_index)
        display.BlockSelectors = [selector]
        checks = {'Assembly': 'Hierarchy', 'ArraySelectionMode': 'Merged Blocks',
                  'BlockSelectors': [selector]}
    else:
        # No version-number guess / compatibility alias: only a real old property.
        prop = display.GetProperty('CompositeDataSetIndex')
        if prop is None or prop.FindDomain('vtkSMCompositeTreeDomain') is None:
            raise ValueError('정확한 원 block을 선택할 native 표시 속성/domain이 없습니다.')
        display.CompositeDataSetIndex = [flat_index]
        checks = {'CompositeDataSetIndex': [flat_index]}
    display.UpdateVTKObjects(); display.SMProxy.UpdatePropertyInformation()
    _check_properties(display, checks)
    return checks


def _chart_array_name(leaf, field, name, component):
    # Reuse the very same ParaView mangling helper used by the chart domain.
    # 'F (1)', 'F_Y', custom component labels, and Magnitude are not interchangeable.
    from paraview import servermanager
    attributes = leaf.GetRowData() if field == 'ROW' else leaf.GetPointData()
    array = attributes.GetArray(name)
    if array is None:
        raise ValueError('선택 leaf에 원 응답/축 배열이 없습니다: '+name)
    count = array.GetNumberOfComponents()
    if count == 1 and component is None:
        component = 0
    if type(component) is not int or not 0 <= component < count:
        raise ValueError('원 응답/축 성분이 native 배열 범위 밖입니다.')
    def names(item):
        if item.GetNumberOfComponents() == 1:
            return [item.GetName()]
        info = servermanager.vtkPVArrayInformation(); info.CopyFromArray(item)
        return [servermanager.vtkSMArrayListDomain.CreateMangledName(info, index)
                for index in range(item.GetNumberOfComponents()+1)]
    result = names(array)[component]
    # Domain strings alone cannot disambiguate a scalar/flattened-vector collision.
    candidates = [label for index in range(attributes.GetNumberOfArrays())
                  if (item := attributes.GetArray(index)) is not None for label in names(item)]
    if candidates.count(result) != 1:
        raise ValueError('원 응답/축의 native 성분명이 중복되어 정확히 선택할 수 없습니다.')
    # The chart's vtkAttributeDataToTableFilter also adds these metadata arrays.
    # Check only the selected label: unrelated raw arrays remain usable/preserved.
    overwritten = {'vtkOriginalIndices'}
    generated = set(overwritten)
    if field == 'POINT' and leaf.IsA('vtkPointSet') and leaf.GetPoints() is not None:
        coordinates = leaf.GetPoints().GetData()
        overwritten.add(coordinates.GetName())
        generated.update([coordinates.GetName(), *names(coordinates)])
    if name in overwritten or result in generated:
        raise ValueError('원 응답/축의 native 성분명이 차트 자동 생성 열과 겹쳐 정확히 선택할 수 없습니다.')
    return result


def _show_selected(ws, obj, record, bundle, selection, native):
    from paraview import simple as p
    source = bundle['source']
    # Resolve before changing the view. A composite leaf index is not block[0].
    leaf, flat_index, field, row = _native_leaf(source, native)
    ws.show(obj, record, bundle)
    view = p.GetActiveView()
    checks = {}
    display = None
    if view.GetXMLName() == 'XYChartView':
        display = p.GetDisplayProperties(source, view)
        # Association, assembly and chart mode all control native series domains.
        association = 'Row Data' if field == 'ROW' else 'Point Data'
        _chart_choice(display, 'AttributeType', association)
        checks.update(AttributeType=association)
        checks.update(_chart_block(display, flat_index))
        display.UpdateVTKObjects(); display.SMProxy.UpdatePropertyInformation()
        _check_properties(display, checks)
        series = _chart_array_name(leaf, field, selection['value_array'], selection['value_component'])
        domain = list(getattr(display.GetProperty('SeriesVisibility'), 'Available', []))
        if series not in domain:
            raise ValueError('원 성분을 선택할 native 곡선 계열이 없습니다: '+series)
        axis = selection['axis']
        if axis['kind'] == 'array':
            xname = _chart_array_name(leaf, field, axis['name'], axis.get('component'))
            axes = list(getattr(display.GetProperty('XArrayName'), 'Available', []))
            if xname not in axes:
                raise ValueError('native 곡선에 선택한 원축이 없습니다.')
            display.UseIndexForXAxis = 0; display.XArrayName = xname
            checks.update(UseIndexForXAxis=0, XArrayName=xname)
        elif axis['kind'] == 'point_index':
            display.UseIndexForXAxis = 1
            checks['UseIndexForXAxis'] = 1
        else:
            raise ValueError('좌표 성분 축은 현재 native 차트에서 직접 선택할 수 없습니다. 원 시험 표에서 좌표와 원점을 확인하세요.')
        display.SeriesVisibility = [series]
        checks['SeriesVisibility'] = [series]
        display.UpdateVTKObjects()
    _highlight(source, native)
    p.Render(view)
    # Property assignment/render return is not an exact-selection receipt.
    if p.GetActiveSource() != source or p.GetActiveView() != view:
        raise ValueError('원자료 선택 중 활성 source/view가 변경되었습니다.')
    _check_properties(display, checks)
    if 'BlockSelectors' in checks:
        # Rendering/domain callbacks must not turn a singleton into a group.
        _selector_leaf(display, flat_index)


def select(ws, *, target, verified, expected_view_generation):
    """Separate explicit mutation after verification; verify again before apply."""
    from paraview import simple as p
    actual = verify(ws, target=target, expected_view_generation=expected_view_generation)
    if actual != verified:
        raise ValueError('원자료 검증 영수증 이후 값/owner/선택이 바뀌었습니다. 새 검증이 필요합니다.')
    origin, obj, record, bundle, selection, native, raw = _resolve(ws, target)
    rollback = _DisplayRollback(bundle['source'], record)
    before = deepcopy(obj), ws.state.get('active_object'), p.GetActiveSource(), p.GetActiveView()
    try:
        _show_selected(ws, obj, record, bundle, selection, native)
        # Persist ONLY owner-local, exact selection, never token/session/PID authority.
        local = deepcopy(target)
        local.pop('saved_origin', None)
        if local['kind'] == 'measurement_lineage':
            local.pop('origin', None)
        obj['selection_context'] = {'kind': 'post_curve_origin', 'target': local}
        obj['selection'] = [deepcopy(native)]
        obj['selection_revision'] = record['id']
        obj['selection_hash'] = canonical_hash(obj['selection'])
        ws.state['active_object'] = obj['id']; ws._touch(); ws.owner.refresh()
        verify_origin(origin); _original_dependencies(ws, obj, record)
    except BaseException as error:
        obj.clear(); obj.update(before[0]); ws.state['active_object'] = before[1]
        try:
            rollback.restore()
        except Exception as recovery:
            raise RuntimeError(str(error)+'; '+str(recovery)) from error
        raise
    return {**actual, 'status': 'SOURCE_SELECTED', 'generation': ws.owner.generation,
            'view_generation': ws.owner.view_generation, 'selection_sha256': obj['selection_hash']}


def restore(ws, obj):
    """Restore saved exact selection through the same verifier, not old tokens."""
    context = obj.get('selection_context', {})
    if context.get('kind') != 'post_curve_origin':
        return False
    record, bundle = ws._bundle(obj)
    if (obj.get('selection_revision') != record['id']
            or canonical_hash(obj.get('selection')) != obj.get('selection_hash')):
        raise ValueError('저장한 원행 선택과 적용 개정이 다릅니다.')
    target = deepcopy(context['target']); origin = saved_origin(ws, obj, record)
    if target['kind'] == 'native_curve':
        target['saved_origin'] = origin
    elif target['kind'] == 'measurement_lineage':
        target['origin'] = origin
    else:
        raise ValueError('지원하지 않는 원행 선택 종류입니다.')
    _, _, _, _, selection, native, _ = _resolve(ws, target)
    if [native] != obj['selection']:
        raise ValueError('저장 원행 값이 현재 native 원행과 다릅니다.')
    rollback = _DisplayRollback(bundle['source'], record)
    try:
        _show_selected(ws, obj, record, bundle, selection, native)
    except BaseException:
        rollback.restore()
        raise
    return True


def activate_window(owner, controls):
    """Only the already-installed current-process GUI handle; no HWND from users."""
    import ctypes
    from ctypes import wintypes as W
    owner.assert_thread()
    if os.name != 'nt' or controls is None or controls.closed or owner.closed or controls.in_action:
        raise ValueError('현재 native 원창의 활성화 경로가 없습니다.')
    controls.refresh()
    hwnd = controls.main
    if not hwnd or controls.platform.main_window() != hwnd:
        raise ValueError('현재 owner의 정확한 원창을 하나로 확인하지 못했습니다.')
    user = controls.platform.user
    for name, result, arguments in (
        ('GetWindowThreadProcessId', W.DWORD, [W.HWND, ctypes.POINTER(W.DWORD)]),
        ('IsIconic', W.BOOL, [W.HWND]), ('ShowWindow', W.BOOL, [W.HWND, ctypes.c_int]),
        ('SetForegroundWindow', W.BOOL, [W.HWND]), ('GetForegroundWindow', W.HWND, [])):
        fn = getattr(user, name); fn.restype, fn.argtypes = result, arguments
    pid = W.DWORD()
    thread = user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value != os.getpid() or thread != controls.platform.thread:
        raise ValueError('원창의 실제 PID/GUI thread가 owner와 다릅니다.')
    if user.IsIconic(hwnd):
        user.ShowWindow(hwnd, 9)  # SW_RESTORE; no input injection/foreground-policy bypass.
    accepted = bool(user.SetForegroundWindow(hwnd))
    active = user.GetForegroundWindow() == hwnd
    return {'status': 'ACTIVATED' if active else 'NOT_PERFORMED', 'native_pid': os.getpid(),
            'foreground_confirmed': bool(active), 'request_accepted': accepted,
            'message': '' if active else 'Windows가 전경 전환을 허용하지 않았습니다. 원행 선택은 별도 확인 결과입니다.'}
