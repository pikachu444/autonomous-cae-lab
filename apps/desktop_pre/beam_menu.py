"""Small common-wiring hooks for native beam commands, save and execution.

All dispatches use the document's existing Owner and the Connection's existing
completion/retry queue. This module owns neither a broker nor a job manager.
"""
from copy import deepcopy
from pathlib import Path
import json
import uuid
from caelab.beam_model import NAMESPACE


def panel(connection, owner):
    dock=getattr(connection,'panels',{}).get(owner.doc.Name,{}).get('beam')
    try:return dock.widget() if dock is not None else None
    except RuntimeError:return None


def editor_token(connection, owner):
    widget=panel(connection,owner)
    return widget.editor_token() if widget is not None else None


def pending_changes(connection, owner):
    return editor_token(connection,owner) is not None


def flush_before_save(connection,owner,arguments,target,on_done,*,capture_motion=True,capture_shell=True):
    widget=panel(connection,owner)
    snapshot=deepcopy(widget.pending_snapshot()) if widget is not None else None
    if snapshot is None:return None
    saved_args,saved_target=deepcopy(arguments),deepcopy(target)
    def applied(value):
        if value.get('status')=='FAILED':
            if on_done:on_done(value)
            return
        widget.accept_saved_snapshot(snapshot,value)
        try:
            connection.submit_native('document.save',saved_args,saved_target,on_done,owner=owner,
                _capture_motion_view=capture_motion,_capture_beam=False,_capture_shell=capture_shell)
        except Exception as error:
            if on_done:on_done({'status':'FAILED','error':{'message':str(error)}})
    return connection.submit_native('pre.beam.draft',
        {'analysis_id':snapshot['analysis_id'],'draft':snapshot},on_done=applied,owner=owner)


def uses_beam(analysis, metadata):
    if analysis.Name in metadata.get(NAMESPACE,{}):return True
    for obj in analysis.Group:
        if hasattr(obj,'FemMesh') and obj.FemMesh.Edges and not obj.FemMesh.Faces and not obj.FemMesh.Volumes:
            return True
    return False


def start_run(connection,owner,analysis_id,*,export_only=False):
    """Queue the exact same native completion -> DesktopLinks -> JobManager flow."""
    if connection.pending or any(r['document_id']==owner.document_id for r in connection.native_requests.values()):
        raise ValueError('이 문서의 이전 작업을 먼저 완료하거나 취소하세요.')
    if pending_changes(connection,owner):
        raise ValueError('빔 편집을 적용하거나 취소한 뒤 입력을 생성하세요.')
    owner.refresh()
    info=owner.beam.inspect(analysis_id)
    if not info['can_freeze']:
        errors=info.get('errors',[])
        raise ValueError(errors[0]['message'] if errors else '빔 설정을 명시적으로 적용하세요.')
    connection.pending={'command_id':'C'+uuid.uuid4().hex,'stage':'command','retry':False,
        'document_id':owner.document_id,'session_id':owner.session_id,'generation':owner.generation,
        'operation':'pre.beam.freeze','arguments':{'analysis_id':analysis_id},'export_only':bool(export_only)}
    connection.send_command()


def make_panel(connection,owner):
    from .beam_panel import make_panel as factory
    from .beam_result_window import open_result
    submit=lambda operation,args,target=None,on_done=None: connection.submit_native(operation,args,target,on_done,owner=owner)
    def run(analysis_id,export_only=False):
        start_run(connection,owner,analysis_id,export_only=export_only)
    return factory(connection.QtWidgets,connection.QtCore,owner.beam,submit,Gui=connection.Gui,
        on_run=run,on_results=lambda:open_result(connection.QtWidgets,connection.QtCore,
            parent=connection.Gui.getMainWindow()),on_runner=connection.open_runner,
        on_save=lambda:connection.guards.save(owner=owner))


def show_input(path,W,C,*,parent=None):
    from caelab.adapters.beam_fem import validate_snapshot
    manifest,model,_=validate_snapshot(Path(path).absolute())
    dialog=W.QDialog(parent);dialog.setWindowTitle('빔 입력');dialog.resize(850,680)
    layout=W.QVBoxLayout(dialog)
    label=W.QLabel('B32R · RECT  |  mm · N · Nmm · MPa · rad');label.setWordWrap(True);layout.addWidget(label)
    text=W.QPlainTextEdit();text.setReadOnly(True);text.setLineWrapMode(W.QPlainTextEdit.NoWrap)
    text.setPlainText((Path(path).parent/'beam.inp').read_text(encoding='ascii'));layout.addWidget(text)
    note=W.QLabel('원 모델과 분리된 입력입니다. 계산은 아직 실행하지 않았습니다.');note.setWordWrap(True);layout.addWidget(note)
    buttons=W.QDialogButtonBox(W.QDialogButtonBox.Close);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
    dialog.setAttribute(C.Qt.WA_DeleteOnClose);dialog.show()
    return dialog


def install(connection):
    """Native menu survives without an AI/MCP account; uses Qt, never a web view."""
    W,C,Gui=connection.QtWidgets,connection.QtCore,connection.Gui
    main=Gui.getMainWindow()
    existing=main.findChild(W.QMenu,'CAELabBeamMenu')
    if existing:return existing
    menu=main.menuBar().addMenu('빔');menu.setObjectName('CAELabBeamMenu')
    def invoke(callback):
        try:callback()
        except Exception as exc:connection.message.setText(str(exc))
    def result():
        from .beam_result_window import open_result
        open_result(W,C,parent=main)
    for title,callback in [('빔 설정…',lambda:connection.show_panel('beam')),
                           ('입력 생성…',lambda:connection.run(export_only=True)),
                           ('계산',connection.run),('저장된 결과 열기…',result)]:
        action=menu.addAction(title);action.triggered.connect(lambda checked=False,cb=callback:invoke(cb))
    return menu
