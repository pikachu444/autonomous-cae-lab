"""Bind the existing PNG export to the saved 3D scene, on its owner thread.

No renderer, store, timers, observers, exit hooks or broker are introduced.
"""
from copy import deepcopy
import os

from caelab.post_observation import file_pin
from caelab.report_image import (FORMAT, MAX_PNG_BYTES, make_origin, png_dimensions,
                                 read_pinned, source_records, retained_analyses, validate_snapshot, verify_origin, warp_conditions)
from caelab.storage import canonical_hash, utc_now


def _properties(workspace, proxy):
    values, pending = workspace.owner.native_properties(proxy)
    if pending:
        raise ValueError('미적용 native 속성이 있습니다. 적용 또는 취소한 뒤 캡처하세요: ' + ', '.join(pending))
    return deepcopy(values)


def _input(rep):
    value = rep.Input
    value = value.GetData() if hasattr(value, 'GetData') else value
    if isinstance(value, (tuple, list)):
        if len(value) != 1:
            raise ValueError('다중 입력 표시를 하나의 결과로 캡처하지 않습니다.')
        value = value[0]
    return value


def scene_state(workspace, obj, record, bundle, lineage=None, axis_context=None):
    """Inspect the actual retained view, colored array and DATA_TIME_STEP."""
    from paraview import simple as p
    owner = workspace.owner
    owner.assert_thread()
    views = [view for name, view in workspace._views() if name == record.get('view_name')]
    if len(views) != 1 or views[0].GetXMLName() != 'RenderView':
        raise ValueError('이 결과의 정확한 3D RenderView를 먼저 표시하세요.')
    view, source = views[0], bundle['source']
    selected, legends = [], []
    for rep in view.Representations:
        if not bool(getattr(rep, 'Visibility', False)):
            continue
        if rep.GetXMLName() == 'ScalarBarWidgetRepresentation':
            legends.append(rep)
            continue
        if not hasattr(rep, 'Input'):
            raise ValueError('결과 외 표시 객체가 있습니다. 선택 결과만 별도 view에 표시하세요.')
        native_input = _input(rep)
        if (native_input is None or owner.proxy_id(native_input) != owner.proxy_id(source)
                or int(getattr(native_input, 'Port', 0)) != int(getattr(source, 'Port', 0))):
            raise ValueError('다른 결과/주석이 함께 보입니다. 선택 결과만 별도 view에 표시하세요.')
        selected.append(rep)
    if len(selected) != 1:
        raise ValueError('선택 결과의 보이는 representation이 없거나 중복됩니다.')
    rep = selected[0]
    view_props, rep_props = _properties(workspace, view), _properties(workspace, rep)
    color = rep.ColorArrayName
    color = color.GetData() if hasattr(color, 'GetData') else color
    if not isinstance(color, (list, tuple)) or len(color) != 2 or color[0] not in ('POINTS', 'CELLS') or not color[1]:
        raise ValueError('단색 이미지는 물리 결과가 아닙니다. 실제 필드를 선택하세요.')
    if rep_props.get('MapScalars') in (0, False) or rep_props.get('Texture'):
        raise ValueError('직접 RGB/텍스처 색상은 물리 필드 범례로 해석하지 않습니다.')
    association, field_name = color
    information = source.GetDataInformation().DataInformation
    attributes = (information.GetPointDataInformation() if association == 'POINTS'
                  else information.GetCellDataInformation())
    array = attributes.GetArrayInformation(field_name)
    if array is None:
        raise ValueError('선택한 배열이 실제 결과에 없습니다.')
    components = int(array.GetNumberOfComponents())
    lookup = getattr(rep, 'LookupTable', None)
    lookup_props = _properties(workspace, lookup) if lookup is not None else {}
    if components == 1:
        component = {'mode': 'SCALAR', 'index': None, 'name': None}
    elif lookup_props.get('VectorMode') == 'Magnitude':
        component = {'mode': 'MAGNITUDE', 'index': None, 'name': None}
    elif lookup_props.get('VectorMode') == 'Component':
        index = int(lookup_props['VectorComponent'])
        if not 0 <= index < components:
            raise ValueError('색상 성분이 실제 배열 범위를 벗어났습니다.')
        component = {'mode': 'COMPONENT', 'index': index, 'name': array.GetComponentName(index)}
    else:
        raise ValueError('벡터의 실제 표시 성분을 확인하지 못했습니다.')
    for legend in legends:
        linked = getattr(legend, 'LookupTable', None)
        if linked is None or lookup is None or owner.proxy_id(linked) != owner.proxy_id(lookup):
            raise ValueError('다른 필드의 범례가 표시되어 있습니다.')
    from caelab.report_image_axis import output_declaration, native_clock
    if axis_context is None:
        raise ValueError('저장 결과의 정확한 축 선언이 없습니다.')
    declaration = output_declaration(axis_context) or {}
    try:
        from .report_image_blocks import inspect as inspect_blocks
    except ImportError:
        from report_image_blocks import inspect as inspect_blocks
    block_coloring = inspect_blocks(rep, lookup, association=association,
        field_name=field_name, representation_properties=rep_props)
    declared = [row for row in declaration.get('arrays', [])
                if row.get('name') == field_name and row.get('association') == association]
    if len(declared) > 1:
        raise ValueError('이 필드의 물리 선언이 중복됩니다.')
    declared = declared[0] if declared else {}
    unit = declared.get('units')
    if unit in ('', 'UNKNOWN'):
        unit = None
    has_time = bool(information.GetHasTime())
    graph = deepcopy(record['graph'])
    for proxy in bundle.get('proxies', []):
        _properties(workspace, proxy)
    lineage = lineage or [{'object_ref': obj['id'], 'revision': record['id'], 'graph': graph}]
    warps = warp_conditions(lineage)
    state = {'view_name': record['view_name'], 'view_type': view.GetXMLName(),
             'view': view_props, 'camera': {k: v for k, v in view_props.items() if k.startswith('Camera')},
             'representation': rep_props, 'lookup_table': lookup_props,
             'legend': [_properties(workspace, legend) for legend in legends],
             'field': {'name': field_name, 'association': association, 'component': component,
                       'components': components, 'unit': unit,
                       'unit_status': 'DECLARED' if unit is not None else 'UNKNOWN',
                       'declaration': deepcopy(declared)},
             'clock': native_clock(has_time, float(information.GetTime()) if has_time else None,
                                   float(view.ViewTime), float(p.GetAnimationScene().AnimationTime), declaration),
             'axis_context': deepcopy(axis_context), 'block_coloring': block_coloring,
             'warp': warps, 'graph': graph,
             'data': {'bounds': list(information.GetBounds()),
                      'points': int(information.GetNumberOfPoints()),
                      'cells': int(information.GetNumberOfCells())},
             'generations': {'content': owner.generation, 'view': owner.view_generation}}
    canonical_hash(state)
    return state


def capture(workspace, object_ref):
    """One guarded call to Workspace.export; the default export path is unchanged."""
    from paraview import simple as p, servermanager
    try:
        from .report_image_data import verify_displayed
    except ImportError:
        from report_image_data import verify_displayed
    owner = workspace.owner
    owner.assert_thread()
    obj = workspace.object(object_ref)
    record, bundle = workspace._bundle(obj)
    origin, project, saved_obj, saved = make_origin(file_pin(owner.project_path),
        owner.document_id, owner.session_id, os.getpid(), object_ref, record['id'])
    if any(record.get(key) != saved.get(key) for key in ('id', 'recipe', 'graph', 'bindings', 'view_name')):
        raise ValueError('선택한 적용 결과와 view를 먼저 저장하세요. 현재 편집은 유지됩니다.')
    view = next((v for name, v in workspace._views() if name == record['view_name']), None)
    if view is None or view.GetXMLName() != 'RenderView':
        raise ValueError('저장된 결과의 3D view를 찾지 못했습니다.')
    # Render existing data, never submit physics or switch the active view/source.
    p.Render(view)
    owner.refresh()
    lineage = retained_analyses(project, saved_obj, saved)
    from caelab.report_image_axis import saved_axis_context
    axis_context = saved_axis_context(project, saved_obj, saved)
    before = scene_state(workspace, obj, record, bundle, lineage, axis_context)
    exact_data = verify_displayed(servermanager.Fetch(bundle['source']), saved, actual_time=before['clock']['value'])
    snapshot = {'format': FORMAT, 'capture_status': 'SUCCEEDED', 'origin': origin,
                'scene': before, 'lineage': lineage, 'recipe': deepcopy(saved['recipe']),
                'sources': source_records(project, saved_obj, saved),
                'result_files': deepcopy(saved['result_files']),
                'result_status': {'execution_status': saved.get('summary', {}).get('execution_status', 'UNKNOWN'),
                                  'qualification': saved.get('summary', {}).get('qualification', 'UNKNOWN'),
                                  'checks': deepcopy(saved.get('summary', {}).get('checks', [])),
                                  'failure_reason': saved.get('summary', {}).get('failure_reason')},
                'data_match': {'status': 'EXACT', 'sha256': canonical_hash(exact_data)},
                'captured_utc': utc_now(), 'engineering_release': 'NOT_RELEASED'}
    validate_snapshot(snapshot)
    receipt = workspace.export(object_ref=object_ref, format='png')
    pin = file_pin(receipt['file'])
    data = read_pinned(pin, MAX_PNG_BYTES)
    if pin['sha256'] != receipt['sha256'] or receipt['revision'] != saved['id']:
        raise ValueError('내보낸 이미지와 선택 결과가 다릅니다.')
    workspace._bundle(obj)
    owner.refresh()
    if scene_state(workspace, obj, record, bundle, lineage, axis_context) != before:
        raise ValueError('캡처 중 표시 조건/시각/입력이 변경되었습니다. 이전 보고서는 유지됩니다.')
    verify_displayed(servermanager.Fetch(bundle['source']), saved, expected=exact_data, actual_time=before['clock']['value'])
    verify_origin(origin)
    snapshot.update(png=pin, pixel_size=list(png_dimensions(data)))
    validate_snapshot(snapshot)
    return {**receipt, 'report_snapshot': snapshot}
