"""Laminate actions reuse the native queue, registered freeze and research windows."""
from copy import deepcopy
from pathlib import Path
import os
import subprocess
import uuid

from caelab.shell_model import digest


def install(connection):
    menu=connection.Gui.getMainWindow().menuBar().addMenu('적층')
    action=menu.addAction('적층 셸…')
    def show():
        try:connection.show_panel('composite')
        except Exception as error:connection.message.setText(str(error))
    action.triggered.connect(show);connection.composite_menu_action=action


def pending_panel(connection,owner):
    dock=getattr(connection,'panels',{}).get(owner.doc.Name,{}).get('composite')
    try:return dock.widget() if dock is not None else None
    except RuntimeError:return None


def has_unsaved_editor(connection,owner):
    panel=pending_panel(connection,owner)
    return bool(panel is not None and panel.pending_changes())


def editor_token(connection,owner):
    panel=pending_panel(connection,owner)
    return digest(panel.current_draft()) if panel is not None else None


def route(connection,owner,analysis_id,*,export_only=False,open_only=False):
    """An existing laminate draft must never fall through to the solid writer."""
    if analysis_id not in owner.read_metadata().get('composite_shells',{}):return False
    panel=connection.show_panel('composite',owner=owner);panel.open_analysis(analysis_id)
    if not open_only:
        (panel.prepare_input if export_only else panel.run_prepared)()
    return True


def flush_before_save(connection,owner,arguments,target,on_done,**captures):
    panel=pending_panel(connection,owner)
    if panel is None or not panel.pending_changes():return None
    if panel.composite_state['busy']:raise ValueError('적층 작업의 응답을 확인한 뒤 저장하세요.')
    draft=panel.current_draft();state=panel.composite_state;state['busy']=True;panel.update_enabled()
    def captured(value):
        state['busy']=False
        if value.get('status')=='FAILED':
            panel.set_status(value.get('error',{}).get('message','초안을 저장하지 못했습니다.'))
            if on_done:on_done(value)
        else:
            # Save acknowledges only this raw snapshot; later edits stay dirty.
            panel.inspect_result(value,draft)
            connection.submit_native('document.save',deepcopy(arguments),deepcopy(target),on_done,
                owner=owner,_capture_composite=False,**captures)
        panel.update_enabled()
    try:return connection.submit_native('pre.composite.draft',{'analysis_id':draft['analysis_id'],'draft':draft},on_done=captured,owner=owner)
    except Exception:state['busy']=False;panel.update_enabled();raise


def make_panel(connection,owner):
    from .composite_panel import make_panel as factory
    W,C=connection.QtWidgets,connection.QtCore
    panel=None
    def submit(operation,args,on_done=None):return connection.submit_native(operation,args,on_done=on_done,owner=owner)
    def prepare():
        if panel.pending_changes():raise ValueError('현재 편집을 적용한 뒤 입력을 준비하세요.')
        draft=panel.current_draft();record,_,_=owner.composite.effective(draft['analysis_id']);expected=digest(record['applied'])
        wire={};epoch=panel.composite_state['epoch']
        def done(value):
            panel.composite_state['busy']=False
            if value.get('status')=='FAILED':raise ValueError(value.get('error',{}).get('message','입력을 준비하지 못했습니다.'))
            if epoch!=panel.composite_state['epoch'] or panel.pending_changes():return
            if value.get('applied_sha256')!=expected:raise ValueError('입력 준비 도중 적용 상태가 바뀌었습니다.')
            folder=Path(owner.export_root).resolve();path=(folder/value['snapshot_relative']).resolve(strict=True)
            if not path.is_relative_to(folder) or path.parent.parent.name!=owner.document_id:raise ValueError('다른 모델의 입력입니다.')
            panel.prepared={**wire,'analysis_id':draft['analysis_id'],'applied_sha256':expected,'snapshot_relative':value['snapshot_relative']}
            panel.set_status('입력을 준비했습니다. 해석 창에서 검토하거나 계산을 실행하세요.');panel.update_enabled()
        panel.composite_state['busy']=True;panel.update_enabled()
        try:
            wire.update(submit('pre.composite.freeze',{'analysis_id':draft['analysis_id']},done))
            if panel.prepared:panel.prepared.update(wire)
        except Exception:panel.composite_state['busy']=False;panel.update_enabled();raise
    def check_prepared():
        prepared=panel.prepared
        if not prepared or not prepared.get('command_id'):raise ValueError('입력을 먼저 준비하세요.')
        record,_,_=owner.composite.effective(prepared['analysis_id'])
        if panel.pending_changes() or digest(record['applied'])!=prepared['applied_sha256']:raise ValueError('현재 편집을 적용한 뒤 새 입력을 준비하세요.')
        return prepared
    def simulation():
        prepared=check_prepared()
        def opened(value):
            if value.get('status')!='DRAFT_OPENED' or value.get('executed') is not False:raise ValueError('계산 문서를 열지 못했습니다. 같은 요청으로 다시 확인하세요.')
            environment=os.environ.copy()
            for key in ('PYTHONHOME','PYTHONPATH','QT_PLUGIN_PATH','QML2_IMPORT_PATH','LD_LIBRARY_PATH'):environment.pop(key,None)
            subprocess.Popen([connection.config['python'],'-m','apps.research.desktop','--service',connection.config['service_url'],
                'simulation','--document-id',value['document']['id']],cwd=str(Path(__file__).resolve().parents[2]),env=environment)
            panel.set_status('해석 창을 열었습니다. 새 계산은 그 창에서 명시하세요.')
        connection.request('composite-document:'+prepared['command_id'],lambda:connection.client.native_open_simulation(prepared['command_id']),opened)
    def run():
        prepared=check_prepared()
        if prepared.get('job_id'):connection.open_runner(prepared['job_id']);return
        def submitted(value):
            if value['origin']['document_id']!=owner.document_id:raise ValueError('다른 원 모델의 계산입니다.')
            prepared['job_id']=value['job']['id'];connection.submit_native('pre.links.record',{'job_id':prepared['job_id']},owner=owner)
            connection.open_runner(prepared['job_id'])
        connection.request('composite-submit:'+prepared['command_id'],lambda:connection.client.native_submit(prepared['command_id']),submitted)
    def post():
        if not panel.prepared or not panel.prepared.get('job_id'):raise ValueError('계산 목록에서 완료된 결과를 선택하세요.')
        connection.open_post(panel.prepared['job_id'])
    def results():
        from .composite_result_window import open_result
        open_result(W,C,parent=connection.Gui.getMainWindow())
    panel=factory(W,C,owner.composite,submit,
        on_save=lambda:connection.submit_native('document.save',{},owner=owner),on_freeze=prepare,
        on_run=run,on_simulation=simulation,on_post=post,on_results=results)
    def open_analysis(aid):
        current=panel.current_draft()
        if current is not None and current['analysis_id']==aid:return
        if panel.pending_changes():raise ValueError('현재 적층 편집을 저장하거나 취소한 뒤 다른 해석을 여세요.')
        panel.composite_state['epoch']+=1;panel.prepared=None
        panel.composite_state['undo'].clear();panel.composite_state['redo'].clear()
        panel.inspect_result(owner.composite.inspect(aid))
    panel.open_analysis=open_analysis;panel.prepare_input=prepare;panel.run_prepared=run
    return panel
