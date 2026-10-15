"""Native command, save and execution hooks; reuse Connection's single queue."""
from copy import deepcopy
from pathlib import Path
import uuid
from caelab.dynamic_model import NAMESPACE
from caelab.storage import canonical_hash, load_json


def panel(connection, owner):
    dock = getattr(connection,'panels',{}).get(owner.doc.Name,{}).get('dynamic')
    try:return dock.widget() if dock is not None else None
    except RuntimeError:return None


def editor_token(connection, owner):
    widget=panel(connection,owner)
    return widget.editor_token() if widget is not None else None


def pending_changes(connection, owner):return editor_token(connection,owner) is not None


def flush_before_save(connection,owner,arguments,target,on_done,*,capture_motion=True,capture_shell=True,capture_beam=True):
    widget=panel(connection,owner);snapshot=deepcopy(widget.pending_snapshot()) if widget is not None else None
    if snapshot is None:return None
    args,selected=deepcopy(arguments),deepcopy(target)
    def saved(value):
        if value.get('status')=='FAILED':
            if on_done:on_done(value)
            return
        try:
            widget.accept_saved_snapshot(snapshot,value)
            connection.submit_native('document.save',args,selected,on_done,owner=owner,_capture_dynamic=False,
                _capture_motion_view=capture_motion,_capture_shell=capture_shell,_capture_beam=capture_beam)
        except (ValueError,RuntimeError) as exc:
            if on_done:on_done({'status':'FAILED','error':{'message':str(exc)}})
    return connection.submit_native('pre.dynamic.draft',{'analysis_id':snapshot['analysis_id'],'draft':snapshot},owner=owner,on_done=saved)


def _ready(connection,owner,analysis_id):
    if connection.pending or any(r['document_id']==owner.document_id for r in connection.native_requests.values()):
        raise ValueError('이 문서의 이전 작업을 먼저 완료하거나 취소하세요.')
    if pending_changes(connection,owner):raise ValueError('동해석 편집을 적용하거나 취소한 뒤 입력을 생성하세요.')
    fem=getattr(connection,'panels',{}).get(owner.doc.Name,{}).get('fem')
    page=fem.widget() if fem is not None else None
    if page is not None:
        steps=getattr(page,'steps_page',None);materials=getattr(page,'material_page',None);conv=getattr(page,'convergence_page',None)
        if steps is not None and steps.modified:raise ValueError('기존 FEM 단계 편집을 먼저 적용하거나 취소하세요.')
        if materials is not None and materials.pending_changes():raise ValueError('기존 재료/기하 편집을 먼저 저장·적용하거나 취소하세요.')
        solver_id=owner.dynamic._get(analysis_id)['draft']['solver_id']
        if conv is not None and conv.pending_changes(analysis_id,solver_id):raise ValueError('기존 수렴 편집을 먼저 저장·적용하거나 취소하세요.')
    owner.refresh();info=owner.dynamic.inspect(analysis_id)
    if not info['can_freeze']:
        errors=info.get('errors',[]);raise ValueError(errors[0]['message'] if errors else '동해석 설정을 명시적으로 적용하세요.')
    return info


def _queue(connection,owner,operation,arguments,export_only):
    connection.pending={'command_id':'C'+uuid.uuid4().hex,'stage':'command','retry':False,
        'document_id':owner.document_id,'session_id':owner.session_id,'generation':owner.generation,
        'operation':operation,'arguments':deepcopy(arguments),'export_only':bool(export_only)}
    connection.send_command()


def start_run(connection,owner,analysis_id,*,export_only=False):
    _ready(connection,owner,analysis_id)
    _queue(connection,owner,'pre.dynamic.freeze',{'analysis_id':analysis_id},export_only)


def restart_dialog(connection,owner,analysis_id,attempt):
    """Explicit READ, never a hidden substitute for the normal 'new run' action."""
    from caelab.dynamic_restart import inspect_attempt
    W=connection.QtWidgets
    info=_ready(connection,owner,analysis_id)
    inventory=inspect_attempt(Path(attempt).absolute())['inventory']
    dialog=W.QDialog(connection.Gui.getMainWindow());dialog.setWindowTitle('실제 native 저장점 — READ 이어가기')
    layout=W.QVBoxLayout(dialog)
    note=W.QLabel('부모 실행의 실제 .rout만 사용합니다. 원 형상·재료·밀도·초기조건·감쇠는 바꾸지 않습니다.\n'
        '현재 적용된 전체 단계표에서 선택한 완료 단계 이후를 실행합니다. 새 시도이며 원 결과는 보존합니다.')
    note.setWordWrap(True);layout.addWidget(note)
    choice=W.QComboBox()
    for r in inventory['checkpoints']:
        choice.addItem(f"{r['step']} / {r['step_id']} / native 전역 좌표 {r['native_global_coordinate']}",r['step'])
    layout.addWidget(choice)
    export=W.QCheckBox('입력만 생성하고 계산하지 않음');export.setChecked(True);layout.addWidget(export)
    buttons=W.QDialogButtonBox(W.QDialogButtonBox.Ok|W.QDialogButtonBox.Cancel);layout.addWidget(buttons)
    buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject)
    execute=getattr(dialog,'exec',None) or dialog.exec_
    if execute()!=W.QDialog.Accepted:return
    current=_ready(connection,owner,analysis_id)
    if canonical_hash(current['record'])!=canonical_hash(info['record']):raise ValueError('선택 중 설정이 변경됐습니다. 다시 검토하세요.')
    step=choice.currentData();rows=current['record']['draft']['program']['steps']
    if step is None or not rows[step:]:raise ValueError('저장점 이후에 실행할 단계를 단계표에 추가·적용하세요.')
    _queue(connection,owner,'pre.dynamic.restart',{'analysis_id':analysis_id,'parent_attempt':str(Path(attempt).absolute()),
        'checkpoint_step':step,'steps':deepcopy(rows[step:])},export.isChecked())


def make_panel(connection,owner):
    from .dynamic_panel import make_panel as factory
    from .dynamic_result_window import open_result
    submit=lambda op,args,target=None,on_done=None:connection.submit_native(op,args,target,on_done,owner=owner)
    def results():
        widget=panel(connection,owner);analysis_id=widget.analysis_key if widget is not None else None
        open_result(connection.QtWidgets,connection.QtCore,parent=connection.Gui.getMainWindow(),
            on_restart=(lambda attempt:restart_dialog(connection,owner,analysis_id,attempt)) if analysis_id else None,
            on_post=lambda attempt:open_post(connection,attempt))
    return factory(connection.QtWidgets,connection.QtCore,owner.dynamic,submit,Gui=connection.Gui,
        on_run=lambda analysis_id,export_only=False:start_run(connection,owner,analysis_id,export_only=export_only),
        on_results=results,on_runner=connection.open_runner,on_save=lambda:connection.guards.save(owner=owner))


def open_post(connection,attempt):
    """Use the existing Post launcher, not another renderer or application."""
    # Existing Runner owns registered Post requests/origin. Opening its list keeps
    # the shared Post lifetime and response guards in one place.
    record=load_json(Path(attempt)/'contact_execution.json')
    identifier=record.get('job_id')
    if not identifier:raise ValueError('JobManager에 등록된 실행이 아닙니다. 기존 Post에서 dynamic.pvd를 직접 여세요.')
    connection.open_runner(identifier)
    connection.message.setText('계산 목록에서 이 실행의 Post 열기를 선택하세요: '+str(attempt))


def show_input(path,W,C,*,parent=None):
    from caelab.adapters.contact_fem import validate_snapshot
    _,model,_,_=validate_snapshot(Path(path).absolute())
    dialog=W.QDialog(parent);dialog.setWindowTitle('동해석 native 입력');dialog.resize(860,680)
    layout=W.QVBoxLayout(dialog);label=W.QLabel('READ 재시작 입력 — 원 상태는 contact.rin에서 읽습니다.' if model.get('restart') else
        '새 동해석 입력 — 초기조건과 native 단계 상태 전달. mm · N · s · tonne.')
    label.setWordWrap(True);layout.addWidget(label)
    text=W.QPlainTextEdit();text.setReadOnly(True);text.setLineWrapMode(W.QPlainTextEdit.NoWrap)
    text.setPlainText((Path(path).parent/'contact.inp').read_text(encoding='ascii'));layout.addWidget(text)
    close=W.QPushButton('닫기');close.clicked.connect(dialog.close);layout.addWidget(close)
    dialog.setAttribute(C.Qt.WA_DeleteOnClose);dialog.show()
    _INPUT_WINDOWS.add(dialog);dialog.destroyed.connect(lambda *_:_INPUT_WINDOWS.discard(dialog));return dialog


_INPUT_WINDOWS=set()


def install(connection):
    W,Gui=connection.QtWidgets,connection.Gui;main=Gui.getMainWindow()
    existing=main.findChild(W.QMenu,'CAELabDynamicMenu')
    if existing:return existing
    menu=main.menuBar().addMenu('동해석');menu.setObjectName('CAELabDynamicMenu')
    def invoke(fn):
        try:fn()
        except Exception as exc:connection.message.setText(str(exc))
    def result():
        from .dynamic_result_window import open_result
        open_result(W,connection.QtCore,parent=main,on_post=lambda attempt:open_post(connection,attempt))
    for label,fn in [('동해석 설정…',lambda:connection.show_panel('dynamic')),
                     ('입력 생성…',lambda:connection.run(export_only=True)),('계산',connection.run),('저장 결과 열기…',result)]:
        action=menu.addAction(label);action.triggered.connect(lambda checked=False,cb=fn:invoke(cb))
    return menu
