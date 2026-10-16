"""Native entry and completed-input handoff to the existing Simulation owner."""
import os
from copy import deepcopy
from caelab.storage import canonical_hash
from pathlib import Path
import subprocess


def _native_panel(Gui,owner):
    state=getattr(Gui.getMainWindow(),'_caelab_connector_actions',{})
    entry=state.get('panels',{}).get(owner.doc.Name)
    try:
        value=entry.panel if entry is not None and entry.owner is owner else None
        return value if value is not None and value.isVisible() else None
    except RuntimeError:return None


def panel(connection,owner):return _native_panel(connection.Gui,owner)


def store_native_pending(Gui,owner):
    value=_native_panel(Gui,owner)
    snapshot=value.pending_snapshot() if value is not None else None
    if snapshot is None:return False
    if not value._store(False):raise ValueError('연결요소 초안을 보관하지 못했습니다. 현재 입력을 유지하고 오류를 수정하세요.')
    return True


def editor_token(connection,owner):
    value=panel(connection,owner)
    return canonical_hash({'connector_id':value.connector_id,'draft':value.draft()}) if value is not None else None


def pending_changes(connection,owner):
    value=panel(connection,owner)
    return value is not None and value.pending_changes()


def flush_before_save(connection,owner,arguments,target,on_done,**captures):
    value=panel(connection,owner);snapshot=value.pending_snapshot() if value is not None else None
    if snapshot is None:return None
    saved_args,saved_target=deepcopy(arguments),deepcopy(target)
    def captured(result):
        if result.get('status')=='FAILED':
            if on_done:on_done(result)
            return
        try:
            value.accept_saved_snapshot(snapshot,result)
            connection.submit_native('document.save',saved_args,saved_target,on_done,owner=owner,
                _capture_connector=False,**captures)
        except (ValueError,RuntimeError) as exc:
            if on_done:on_done({'status':'FAILED','error':{'message':str(exc)}})
    return connection.submit_native('pre.connector.draft',deepcopy(snapshot),owner=owner,on_done=captured)


def rebind(connection,previous,current):
    state=getattr(connection.Gui.getMainWindow(),'_caelab_connector_actions',{})
    entry=state.get('panels',{}).get(previous.doc.Name)
    if entry is None or entry.owner is not previous:return
    entry.owner=current;entry.native=current.connector
    value=entry.panel
    if value is not None and value.isVisible() and value.connector_id:
        value._load(current.connector.inspect(value.connector_id))


def install(config,*,connection=None,file_actions):
    import FreeCADGui as Gui
    from PySide import QtCore,QtGui
    try:from PySide import QtWidgets as W
    except ImportError:W=QtGui
    from .connector_panel import show
    main=Gui.getMainWindow()
    state=getattr(main,'_caelab_connector_actions',None)
    if state is not None:
        state.update(config=dict(config),connection=connection,file_actions=file_actions)
        return state
    state={'config':dict(config),'connection':connection,'file_actions':file_actions,'panels':{}}
    main._caelab_connector_actions=state
    menu=main.menuBar().addMenu('연결요소');menu.setObjectName('CAELabConnectorMenu')
    def report(message):W.QMessageBox.warning(main,'연결요소',str(message))
    def open_simulation(value):
        if value.get('status')!='DRAFT_OPENED' or value.get('executed') is not False:
            raise ValueError('보존한 입력의 계산 문서를 열지 못했습니다. 같은 요청으로 다시 확인하세요.')
        env=os.environ.copy()
        for key in ('PYTHONHOME','PYTHONPATH','QT_PLUGIN_PATH','QML2_IMPORT_PATH','LD_LIBRARY_PATH'):env.pop(key,None)
        subprocess.Popen([state['config']['python'],'-m','apps.research.desktop','--service',
            state['config']['service_url'],'simulation','--document-id',value['document']['id']],
            cwd=str(Path(__file__).resolve().parents[2]),env=env)
    class PanelEditor:
        """Reuse the native Editor; only connected Freeze uses the existing queue."""
        def __init__(self,owner):self.owner=owner;self.native=owner.connector;self.panel=None
        def __getattr__(self,name):return getattr(self.native,name)
        def save_document(self):
            conn=state['connection']
            if conn is not None:return conn.guards.save(owner=self.owner)
            # Reuse the installed native file action (including portable Save),
            # after synchronously storing the raw editor in the same Owner.
            if state['file_actions']['current_owner']() is not self.owner:
                raise ValueError('이 연결요소의 원 모델을 활성화한 뒤 저장하세요.')
            if self.panel is not None and self.panel.pending_changes() and not self.panel._store(False):return False
            actions=main.findChildren(getattr(W,'QAction',None) or QtGui.QAction)
            action=next((a for a in actions if a.objectName()=='CAELabPortablePreSave'),None)
            if action is None:raise ValueError('파일 메뉴의 프로젝트 저장 명령을 확인하세요.')
            action.trigger();return True
        def freeze(self,key):
            conn=state['connection']
            if conn is None:return self.native.freeze(key)
            broker=conn.owners.get(self.owner.doc.Name)
            if broker is None or broker[2].stop.is_set() or not broker[2].registered.is_set():
                return self.native.freeze(key)
            wire={}
            def opened(value):
                p=self.panel
                if p is not None:
                    p.prepared={**wire,'document_id':value['document']['id']}
                    p.notice.setText('보존한 입력의 계산 문서를 열었습니다. 실행은 그 문서에서 명시하세요.')
                open_simulation(value)
            def completed(value):
                if value.get('status')=='FAILED':
                    if self.panel is not None:self.panel.notice.setText(value.get('error',{}).get('message','입력 준비를 완료하지 못했습니다.'))
                    return
                command=wire.get('command_id')
                if not command:raise ValueError('완료한 입력의 원 명령을 다시 확인하세요.')
                conn.request('connector-document:'+command,
                    lambda:conn.client.native_open_simulation(command),opened)
            queued=conn.submit_native('pre.connector.freeze',{'connector_id':key},owner=self.owner,on_done=completed)
            wire.update(queued)
            if self.panel is not None:
                QtCore.QTimer.singleShot(0,lambda:self.panel.notice.setText('입력을 준비하는 중입니다. 계산은 아직 실행하지 않습니다.'))
            return dict(queued)
    def edit():
        try:
            owner=state['file_actions']['current_owner']()
            if owner.closed:raise ValueError('열린 모델을 선택하세요.')
            entry=state['panels'].get(owner.doc.Name)
            if entry is None or entry.owner is not owner:
                entry=PanelEditor(owner);state['panels'][owner.doc.Name]=entry
            entry.panel=show(W,QtCore,entry)
        except Exception as exc:report(exc)
    action=menu.addAction('스프링과 댐퍼…');action.triggered.connect(lambda checked=False:edit())
    state['menu']=menu
    return state
