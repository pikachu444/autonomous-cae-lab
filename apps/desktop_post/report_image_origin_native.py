"""Exact-source review in an existing native Post owner; never a screenshot.

Read/verify commands do not change pipeline, time, field, camera or input files.
Cold startup selects an already restored source BEFORE creating the native owner.
"""
import json
import os
from pathlib import Path

from caelab.post_observation import check_pin
from caelab.report_image import verify_origin
from caelab.storage import canonical_hash


def startup_request(path, project_path):
    if not path:
        return None
    # This is an existing launcher folder request, not another Report asset store.
    file = Path(path)
    if file.stat().st_size > 256 * 1024:
        raise ValueError('보고서 원자료 열기 요청이 너무 큽니다.')
    origin = json.loads(file.read_text(encoding='utf-8'))
    verify_origin(origin)
    if Path(project_path).resolve() != check_pin(origin['project']):
        raise ValueError('보고서가 가리키는 정확한 저장 Post project가 아닙니다.')
    return origin


def select_restored_source(origin):
    """Cold startup only. Reuse loaded proxies; never create a reader/view."""
    from paraview import simple as p
    _, _, record = verify_origin(origin)
    names = [record.get('retained_source_name'), record.get('source_name')]
    source = next((found for name in names if name for found in [p.FindSource(name)] if found is not None), None)
    if source is None:
        raise ValueError('정확한 저장 pipeline을 찾지 못했습니다. 원프로젝트 복구가 필요합니다.')
    # ParaView GetViews() commonly returns a list; registration names live in PM.
    from paraview import servermanager
    manager = servermanager.ProxyManager()
    registered = manager.GetProxiesInGroup('views')
    matches = [view for (name, _), view in registered.items() if name == record['view_name']]
    if len(matches) != 1:
        raise ValueError('저장 결과의 retained view가 없거나 중복됩니다.')
    p.SetActiveSource(source)
    p.SetActiveView(matches[0])
    # Render the loaded retained view; no Show/ColorBy, clock/camera reconstruction.
    p.Render(matches[0])
    verify_origin(origin)


def verify_live(workspace, *, origin, expected_view_generation):
    from paraview import simple as p, servermanager
    try:
        from .report_image_data import verify_displayed
    except ImportError:
        from report_image_data import verify_displayed
    owner = workspace.owner
    owner.assert_thread(); owner.refresh()
    expected_generation = owner.generation
    if type(expected_view_generation) is not int or owner.view_generation != expected_view_generation:
        raise ValueError('원 Post 표시 상태가 바뀌었습니다. 현재 창과 보고서는 변경하지 않았습니다.')
    _, _, saved = verify_origin(origin)
    if owner.document_id != origin['document_id'] or owner.project_path.resolve() != check_pin(origin['project']):
        raise ValueError('살아 있는 원창이 다른 저장본에 있습니다. 현재 원창을 저장·종료한 후 정확 저장본 열기를 다시 요청하세요.')
    obj = workspace.object(origin['object_ref']); record, bundle = workspace._bundle(obj)
    if any(record.get(k) != saved.get(k) for k in ('id', 'recipe', 'graph', 'bindings', 'view_name')):
        raise ValueError('살아 있는 원창의 결과/recipe가 다릅니다. 현재 상태를 덮지 않았습니다.')
    source = bundle['source']; selected = p.GetActiveSource()
    for proxy in [*bundle.get('proxies', [source]), p.GetActiveView()]:
        if proxy is not None and owner.native_properties(proxy)[1]:
            raise ValueError('원창에 미적용 native 편집이 있습니다. 편집을 적용/취소한 뒤 다시 확인하세요.')
    if selected is None or owner.proxy_id(selected) != owner.proxy_id(source):
        raise ValueError('원창이 다른 pipeline을 선택하고 있습니다. 현재 선택을 덮지 않았습니다. 원창의 정확 저장 결과를 선택하거나 창을 종료한 후 다시 여세요.')
    info = source.GetDataInformation().DataInformation
    value = float(info.GetTime()) if info.GetHasTime() else None
    verify_displayed(servermanager.Fetch(source), saved, actual_time=value)
    verify_origin(origin)
    owner.refresh()
    if owner.view_generation != expected_view_generation or owner.generation != expected_generation:
        raise ValueError('원자료 검증 중 표시 조건이 바뀌었습니다. 과거 결과 열기 완료로 처리하지 않습니다.')
    return {'status': 'SOURCE_VERIFIED', 'origin_sha256': canonical_hash(origin),
            'object_ref': origin['object_ref'], 'revision': origin['revision'],
            'result_sha256': origin['result_sha256'], 'native_pid': os.getpid(),
            'generation': owner.generation, 'view_generation': owner.view_generation,
            'historical_view_restored': False}
