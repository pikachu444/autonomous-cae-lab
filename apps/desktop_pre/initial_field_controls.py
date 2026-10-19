"""Capture the existing initial-condition editor through native owner saves."""
from copy import deepcopy


def panel(connection, owner):
    dock = getattr(connection, 'panels', {}).get(owner.doc.Name, {}).get('fem')
    try:return getattr(dock.widget(), 'initial_field_page', None) if dock is not None else None
    except RuntimeError:return None


def editor_token(connection, owner):
    p = panel(connection, owner)
    return p.token() if p is not None else None


def pending_changes(connection, owner):
    p = panel(connection, owner)
    return p is not None and p.pending_changes()


def flush_before_save(connection, owner, arguments, target, on_done):
    p = panel(connection, owner)
    if p is None or not p.pending_changes():return None
    if p.pending:raise ValueError('처리 중인 초기조건 요청을 먼저 확인하세요. 현재 편집은 유지합니다.')
    args, saved_target = deepcopy(arguments), deepcopy(target); session = owner.session_id
    def stored(result):
        if owner.closed or owner.session_id != session or panel(connection, owner) is not p:
            if on_done:on_done({'status':'FAILED', 'error':{'message':'원 모델이 바뀌었습니다. 현재 편집은 유지합니다.'}})
            return
        connection.submit_native('document.save', args, saved_target, on_done, owner=owner,
            _capture_initial=False, _capture_pretension=False, _capture_connector=False,
            _capture_motion_view=False, _capture_shell=False, _capture_beam=False,
            _capture_dynamic=False, _capture_composite=False)
    def failed(error):
        if on_done:on_done({'status':'FAILED', 'error':{'message':str(error)}})
    p.store(stored, on_error=failed)
    return {'queued':True, 'stage':'initial_editor'}


def store_native_pending(owner, *, connection=None):
    p = panel(connection, owner) if connection is not None else None
    if p is None:
        ref = getattr(owner.fem, '_initial_field_page', None); p = ref() if ref else None
    if p is None or not p.pending_changes():return False
    if p.pending:raise ValueError('처리 중인 초기조건 요청을 먼저 확인하세요.')
    import uuid
    snapshot = deepcopy(p.snapshot()); owner.refresh()
    value = owner.dispatch({'command_id':'C' + uuid.uuid4().hex, 'document_id':owner.document_id,
        'session_id':owner.session_id, 'expected_generation':owner.generation, 'operation':'pre.initial.save_draft',
        'arguments':{**snapshot, 'expected_revision':(p.current or {}).get('revision')}, 'target':{'object_id':p.loaded_analysis}})
    if value.get('status') == 'FAILED':raise ValueError(value.get('error', {}).get('message', '초기조건 초안을 저장하지 못했습니다.'))
    p.accept(snapshot, value.get('result', value)); return True


def route(connection, owner, solver):
    from .fem_edit import _native_type
    p = panel(connection, owner); wanted = set(owner.read_metadata().get('initial_fields', {}))
    if p is not None and (p.modified or p.pending):wanted.add(p.loaded_analysis)
    analyses = [a for a in owner.doc.Objects if _native_type(a) == 'Fem::FemAnalysis' and solver in a.Group and a.Name in wanted]
    if not analyses:return False
    if len(analyses) != 1:raise ValueError('초기조건을 편집할 해석 하나를 활성화하세요.')
    host = connection.show_panel('fem', owner=owner); p = host.initial_field_page; aid = analyses[0].Name
    if p.loaded_analysis != aid:
        if p.modified or p.pending:raise ValueError('현재 초안을 저장하거나 취소한 뒤 해석을 바꾸세요.')
        host.analysis.setCurrentIndex(host.analysis.findData(aid)); p.refresh()
    host.tabs.setCurrentWidget(p)
    connection.message.setText('초기조건과 해석 단계를 확인한 뒤 입력 파일 생성 또는 계산을 선택하세요.')
    return True
