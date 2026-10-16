"""E6 uses the existing native save queue and contextual FEM page."""
from copy import deepcopy
from caelab.storage import canonical_hash


def panel(connection,owner):
    dock=getattr(connection,'panels',{}).get(owner.doc.Name,{}).get('fem')
    try:return getattr(dock.widget(),'pretension_page',None) if dock is not None else None
    except RuntimeError:return None


def editor_token(connection,owner):
    page=panel(connection,owner)
    if page is None or not (page.modified or page.pending):return None
    return canonical_hash({'analysis_id':page.loaded_analysis,'editor':page.editor_snapshot(),
        'pending':page.pending[:3] if page.pending else None})


def pending_changes(connection,owner):
    page=panel(connection,owner)
    return page is not None and page.pending_changes()


def flush_before_save(connection,owner,arguments,target,on_done):
    page=panel(connection,owner);snapshot=deepcopy(page.pending_snapshot()) if page is not None else None
    if snapshot is None:return None
    aid=page.current_analysis();session=owner.session_id
    expected=canonical_hash(page._saved_snapshot) if page._saved_snapshot is not None else None
    def captured(value):
        if value.get('status')=='FAILED':
            if on_done:on_done(value)
            return
        try:
            if owner.closed or owner.session_id!=session or panel(connection,owner) is not page:
                raise ValueError('체결 초안을 저장한 원 문서를 확인하세요. 현재 편집은 유지합니다.')
            page.accept_saved_snapshot(snapshot,value)
            # This hook runs AFTER the existing captures. A late edit remains
            # dirty; restarting those captures would silently save a newer D1.
            connection.submit_native('document.save',deepcopy(arguments),deepcopy(target),on_done,owner=owner,
                _capture_pretension=False,_capture_motion_view=False,_capture_shell=False,
                _capture_beam=False,_capture_dynamic=False,_capture_composite=False,_capture_connector=False)
        except (ValueError,RuntimeError) as error:
            if on_done:on_done({'status':'FAILED','error':{'message':str(error)}})
    return connection.submit_native('pre.fem.pretension_save_editor',
        {'editor':snapshot,'expected_editor_sha256':expected},{'object_id':aid},captured,owner=owner)


def route_native_solver(connection,owner,solver):
    from .fem_edit import _native_type
    data=owner.read_metadata();page=panel(connection,owner)
    wanted={row['analysis_id'] for row in data.get('pretension_sections',[])}|set(data.get('pretension_editors',{}))
    if page is not None and (page.modified or page.pending):wanted.add(page.loaded_analysis)
    targets=[a for a in owner.doc.Objects if _native_type(a)=='Fem::FemAnalysis' and solver in a.Group and a.Name in wanted]
    if not targets:return False
    if len(targets)!=1:raise ValueError('체결 조건이 속한 해석 하나를 활성화하세요.')
    widget=connection.show_panel('fem',owner=owner);current=widget.pretension_page;aid=targets[0].Name
    if current.loaded_analysis!=aid:
        if current.modified or current.pending:raise ValueError('현재 체결 초안을 보관하거나 취소한 뒤 다른 해석을 선택하세요.')
        widget.analysis.setCurrentIndex(widget.analysis.findData(aid));current.refresh()
    widget.tabs.setCurrentWidget(current)
    connection.message.setText('볼트 체결 조건과 해석 단계를 확인한 뒤 입력 파일 생성 또는 계산을 선택하세요.')
    return True


def store_native_pending(owner, *, connection=None):
    """The existing synchronous File Save stores raw text, never applies it."""
    page=panel(connection,owner) if connection is not None else None
    if page is None:
        ref=getattr(getattr(owner,'fem',None),'_pretension_page',None)
        page=ref() if ref is not None else None
    if page is None:return False
    snapshot=deepcopy(page.pending_snapshot())
    if snapshot is None:return False
    import uuid
    owner.refresh()
    result=owner.dispatch({'command_id':'C'+uuid.uuid4().hex,'document_id':owner.document_id,
        'session_id':owner.session_id,'expected_generation':owner.generation,
        'operation':'pre.fem.pretension_save_editor','arguments':{'editor':snapshot,
            'expected_editor_sha256':canonical_hash(page._saved_snapshot) if page._saved_snapshot is not None else None},
        'target':{'object_id':page.current_analysis()}})
    if result.get('status')=='FAILED':raise ValueError(result.get('error',{}).get('message','체결 초안을 보관하지 못했습니다.'))
    page.accept_saved_snapshot(snapshot,result.get('result',result))
    return True
