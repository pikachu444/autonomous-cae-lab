"""Use the existing Data/Material and each actual bound Plan raw transport.

An immutable archive is never installed in raw-recovery/. This adapter only
renders a checked current-owner BUFFER_READY packet. Existing Keep/close/save
and Plan patch-review actions remain the owners of later user operations.
"""
from copy import deepcopy
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QAbstractItemView, QInputDialog
from caelab.related_save import input_identity
from .data_material_recovery_host import _Review, _views, _available


def _view(window,identifier):
    found=next((v for v in _views(window) if v[0]['id']==identifier),None)
    if found is None: raise ValueError('선택한 실제 편집 창이 닫혔거나 다른 문서로 바뀌었습니다.')
    return found


def _ready(window,identifier):
    if not _available(window):
        raise ValueError('현재 문서 요청이 끝난 뒤 원문을 여세요. 입력은 유지됩니다.')
    if window.document['id']==identifier:
        if window.local_dirty or window.conflict or any(t.state()==QAbstractItemView.State.EditingState
                for t in window.findChildren(QAbstractItemView) if
                t in ([window.mapping] if window.document['kind']=='data' else [window.history,window.coefficients])):
            raise ValueError('현재 편집 원문을 먼저 보관한 뒤 새로 연 편집기에서 이어가세요. 미확정 입력을 버리지 않습니다.')
    else:
        panel=window._plan_panel; widget=panel._widgets.get(identifier)
        if widget is None or widget.has_unapplied_buffer() or not widget.recovery_ready():
            raise ValueError('이 계획의 현재 편집 원문을 먼저 보관한 뒤 깨끗한 계획 편집기에서 이어가세요.')


def inspect_portable_recovery(window):
    if getattr(window,'_recovery_review',None) is not None or not _available(window): return
    session=_Review(window)
    try:
        views=_views(window)
        if not views: session.finish(); return
        index=0
        if len(views)>1:
            labels=[str(i+1)+'. '+d['title']+' / '+('재료' if d['kind']=='material' else '계획')
                    for i,(d,_,_) in enumerate(views)]
            selected,ok=QInputDialog.getItem(window,'이동 사본의 원 편집 자료','현재 편집할 문서',labels,0,False)
            if not ok: session.finish(); return
            index=labels.index(selected)
        document=deepcopy(views[index][0]); identifier=document['id']
        # Reading is always allowed even with a dirty buffer. The clean-view
        # precondition is checked only by the explicit resume callback below.
        def bound():
            identity=deepcopy(session.identities[identifier]); base=input_identity(document)
            def current():
                _ready(window,identifier)
                now,snapshot,_=_view(window,identifier)
                if input_identity(now)!=base:
                    raise ValueError('검토 중 기준 문서가 바뀌었습니다. 현재 입력을 유지합니다.')
                return deepcopy(identity),snapshot()
            def restore(packet):
                _ready(window,identifier)
                now,_,restore_raw=_view(window,identifier)
                if input_identity(now)!=base:
                    raise ValueError('늦게 도착한 원문을 다른 문서에 복구하지 않습니다.')
                target=packet['document']; returned=packet['target_identity']
                if (target['id']!=identifier or target['kind']!=document['kind'] or
                        input_identity(target)!={k:v for k,v in returned.items() if k!='store_id'}
                        or returned['store_id']!=identity['store_id'] or returned['session_id']!=identity['session_id']):
                    raise ValueError('현재 소유자의 정확한 응답이 아닙니다.')
                if identifier==window.document['id']:
                    window._show_document(target)
                else:
                    panel=window._plan_panel; widget=panel._widgets[identifier]
                    widget.bind_owner(panel._adapters[identifier],target)
                    panel._documents[identifier]=deepcopy(target)
                    selected=panel.plans.findData(identifier)
                    if selected<0: raise ValueError('현재 계획 선택이 바뀌었습니다.')
                    panel.plans.setCurrentIndex(selected); panel.stack.setCurrentWidget(widget)
                restore_raw(deepcopy(packet['raw']))
                session.guard.protect_current([window],restore_focus=True)
                window.message.setText('원문을 현재 편집기에 복구했습니다. 계산·저장하지 않았습니다. 닫을 때 현재 사본에 원문을 보관하세요.')
            def loaded(payload):
                try:
                    from .portable_recovery_dialog import PortableRecoveryReadDialog
                    records=[r for r in payload['archives'] if r['source']=='CARRIED_ORIGINAL']
                    if not records:
                        window.message.setText('이 사본에 명시 포함된 원 편집 자료가 없습니다. 원 편집기의 보관본을 선택하여 사본을 만드세요.'); return
                    dialog=PortableRecoveryReadDialog(window.client,document,records,current=current,restore=restore,parent=window)
                    window._portable_archive_dialog=dialog
                    dialog.exec()
                finally:
                    window._portable_archive_dialog=None; session.finish()
            session.request(lambda:window.client.portable_recovery_catalog([identifier]),loaded)
        session.bind([document],bound)
    except (ValueError,KeyError,TypeError,RuntimeError) as error:
        window.message.setText(str(error)); session.finish()


def install_portable_recovery_action(window,menu):
    action=QAction('이동 사본의 원 편집 자료…',window)
    action.triggered.connect(lambda:inspect_portable_recovery(window))
    menu.addAction(action)
    return action
