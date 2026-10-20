"""Desktop binding for the existing recovery API; no owner apply/save logic."""
from copy import deepcopy
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QAbstractItemView, QInputDialog, QMessageBox
from shiboken6 import isValid
from caelab.related_save import input_identity
from .recovery_focus import RawEditorFocusGuard


def _views(window):
    if not window.document:
        return []
    provider = getattr(window, 'recovery_views', None)
    if callable(provider):
        return provider()
    from .material_recovery import material_raw_snapshot, restore_material_raw
    from .data_recovery import data_raw_snapshot, restore_data_raw
    data=window.document.get('kind')=='data'
    snapshot=data_raw_snapshot if data else material_raw_snapshot
    restore=restore_data_raw if data else restore_material_raw
    views=[(deepcopy(window.document),lambda:snapshot(window),lambda raw:restore(window,raw))]
    panel=getattr(window,'_plan_panel',None)
    if panel is not None:
        views.extend(panel.recovery_views())
    return views


def _available(window):
    panel=getattr(window,'_plan_panel',None)
    ready=getattr(window,'recovery_ready',None)
    return (not window._busy and (not callable(ready) or ready())
            and (panel is None or panel.recovery_ready()))


class _Review:
    """Keep one modal/review lifecycle and its live delegates together."""
    def __init__(self,window):
        self.window=window
        self.guard=RawEditorFocusGuard([window]); self.guard.__enter__()
        self.timer_running=window.timer.isActive(); window.timer.stop()
        self.worker=None; self.identities={}; self.bases={}
        window._recovery_review=self

    def finish(self):
        window=self.window
        if getattr(window,'_recovery_review',None) is not self:
            return
        window._recovery_review=None
        self.guard.__exit__(None,None,None)
        if self.timer_running and isValid(window) and window.isVisible() and not window._allow_close:
            window.timer.start()

    def request(self,function,received):
        from .data_window import _Read
        worker=self.worker=_Read(function)
        def done(value,error):
            if not isValid(self.window) or getattr(self.window,'_recovery_review',None) is not self:
                return
            self.worker=None
            if error:
                self.window.message.setText('보관 정보를 확인하지 못했습니다. 창과 편집 원문을 유지합니다.')
                self.window.message.setToolTip(str(error)); self.finish(); return
            try: received(value)
            except (ValueError,KeyError,TypeError,RuntimeError) as error:
                self.window.message.setText(str(error)); self.finish()
        worker.signals.finished.connect(done,Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    def bind(self,documents,after):
        self.bases={d['id']:input_identity(d) for d in documents}
        client=self.window.client; identifiers=list(self.bases)
        def read():
            return [client.data_material('recovery.identity',{'document_id':identifier}) for identifier in identifiers]
        def received(identities):
            if (len(identities)!=len(self.bases) or any(
                    {k:v for k,v in identity.items() if k!='store_id'}!=self.bases.get(identity.get('document_id'))
                    for identity in identities)):
                raise ValueError('문서가 검토 중 바뀌었습니다. 현재 창과 편집 원문을 유지합니다.')
            self.identities={identity['document_id']:deepcopy(identity) for identity in identities}
            after()
        self.request(read,received)

    def capture(self):
        views=_views(self.window)
        if not _available(self.window) or {d['id'] for d,_,_ in views}!=set(self.bases):
            raise ValueError('연결된 편집 창이 바뀌었습니다. 현재 입력을 유지합니다.')
        requests=[]
        for document,snapshot,_ in views:
            if input_identity(document)!=self.bases[document['id']]:
                raise ValueError('기준 문서가 바뀌었습니다. 현재 입력을 유지합니다.')
            requests.append({'identity':deepcopy(self.identities[document['id']]),'raw':snapshot()})
        return requests


def leave_with_recovery(window,continuation):
    """Capture before any editor commit, and continue only after a fresh gate."""
    if getattr(window,'_recovery_review',None) is not None:
        return
    if not _available(window):
        window.message.setText('현재 문서 요청이 끝난 뒤 닫거나 바꾸세요. 편집 원문은 유지됩니다.'); return
    session=_Review(window)
    try:
        views=_views(window)
        pending=any(table.state()==QAbstractItemView.State.EditingState for table in window.findChildren(QAbstractItemView))
        dirty=window.local_dirty or any(d.get('dirty') for d,_,_ in views)
        panel=getattr(window,'_plan_panel',None)
        dirty=dirty or bool(panel and panel.has_pending_inputs())
        if not views or not (pending or dirty):
            continuation(); session.finish(); return
        # Snapshot before the question changes focus or starts any transport.
        original={d['id']:snapshot() for d,snapshot,_ in views}
        question=QMessageBox(window); question.setWindowTitle('편집한 입력')
        question.setText('편집한 입력을 보관하고 닫을까요?')
        save=question.addButton('저장',QMessageBox.ButtonRole.AcceptRole)
        keep=question.addButton('편집 원문 보관',QMessageBox.ButtonRole.ActionRole)
        question.addButton('취소',QMessageBox.ButtonRole.RejectRole)
        question.exec()
        session.guard.restore_focus()
        if question.clickedButton() is save:
            session.finish()
            if panel and panel.has_unconfirmed_save():
                window.message.setText('저장 결과를 먼저 확인하세요. 창과 편집 원문은 유지됩니다.')
            elif panel and panel.has_pending_inputs():
                window.message.setText('계획 편집을 먼저 적용하고 저장하세요. 미확정 입력은 원문으로 보관할 수 있습니다.')
            else: window.save_document(after=continuation)
            return
        if question.clickedButton() is not keep:
            session.finish(); return
        def bound():
            try:
                # Focus events can settle while identities are read; restore only unchanged editors.
                session.guard.restore_focus()
                current=session.capture()
                if {r['identity']['document_id']:r['raw'] for r in current}!=original:
                    raise ValueError('검토 중 편집이 바뀌었습니다. 창과 원문을 유지합니다.')
                from .data_material_recovery_dialog import RecoveryKeepDialog
                dialog=RecoveryKeepDialog(window.client,[d for d,_,_ in views],session.capture,window)
                dialog.exec()
                if dialog.is_still_current() and _available(window):
                    continuation()
            finally: session.finish()
        session.bind([d for d,_,_ in views],bound)
    except (ValueError,KeyError,TypeError,RuntimeError) as error:
        window.message.setText(str(error)); session.finish()


def inspect_recovery(window):
    if getattr(window,'_recovery_review',None) is not None or not _available(window):
        return
    session=_Review(window)
    try:
        views=_views(window)
        if not views: session.finish(); return
        index=0
        if len(views)>1:
            labels=[d.get('title','문서')+' ('+('재료' if i==0 else '계획 '+str(i))+')' for i,(d,_,_) in enumerate(views)]
            selected,accepted=QInputDialog.getItem(window,'보관한 편집 원문','문서',labels,0,False)
            if not accepted: session.finish(); return
            index=labels.index(selected)
        document,_,restore=views[index]
        def bound():
            from .data_material_recovery_read import RecoveryReadDialog
            identity=session.identities[document['id']]
            def current_identity():
                current=next((d for d,_,_ in _views(window) if d['id']==document['id']),None)
                if current is None or input_identity(current)!=session.bases[document['id']]:
                    raise ValueError('기준 문서가 바뀌었습니다.')
                return deepcopy(identity)
            try:
                def restore_guarded(raw):
                    restore(raw)
                    session.guard.protect_current([window],restore_focus=True)
                dialog=RecoveryReadDialog(window.client,document,identity,restore_guarded,current_identity=current_identity,parent=window)
                dialog.exec()
            finally: session.finish()
        session.bind([document],bound)
    except (ValueError,KeyError,TypeError,RuntimeError) as error:
        window.message.setText(str(error)); session.finish()


def install_recovery_action(window,menu):
    action=QAction('보관한 편집 원문…',window)
    action.triggered.connect(lambda:inspect_recovery(window))
    menu.addSeparator(); menu.addAction(action)
    return action
