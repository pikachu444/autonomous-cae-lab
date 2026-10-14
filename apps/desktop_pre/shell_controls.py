"""Narrow glue to the existing native Connection and JobManager, not a scheduler."""
from pathlib import Path
import uuid

from caelab.shell_model import digest


class ShellActions:
    def __init__(self, connection, panel, editor):
        self.connection=connection; self.panel=panel; self.editor=editor
        self.preparing=None

    def prepare(self):
        panel=self.panel; owner=self.editor.owner
        if panel.pending_changes(): raise ValueError('속성을 적용하거나 미적용 편집을 취소하세요.')
        if self.preparing: raise ValueError('이미 입력을 준비하고 있습니다.')
        aid=panel.buffer.analysis_id
        record,_,_=self.editor.effective(aid)
        expected=digest(record['applied'])
        pending={'command_id':None}; self.preparing=pending
        def prepared(value):
            self.preparing=None
            if value.get('applied_sha256')!=expected:
                raise ValueError('입력 준비 도중 적용 상태가 달라졌습니다. 새 입력을 준비하세요.')
            folder=Path(owner.export_root).resolve()
            path=(folder/value['snapshot_relative']).resolve(strict=True)
            if not path.is_relative_to(folder) or path.parent.parent.name!=owner.document_id:
                raise ValueError('다른 문서의 입력을 실행할 수 없습니다.')
            panel.prepared={'command_id':pending['command_id'],'applied_sha256':expected,
                            'analysis_id':aid,'snapshot_relative':value['snapshot_relative']}
            panel.set_status('입력을 준비했습니다. 계산은 아직 실행하지 않았습니다.')
            panel.update_enabled()
            from .shell_input_dialog import show_input
            show_input(path,self.connection.QtWidgets,self.connection.QtCore,parent=self.connection.Gui.getMainWindow())
        def done(value):
            if value.get('status')=='FAILED':
                self.preparing=None
            prepared(value) if value.get('status')!='FAILED' else None
            panel.update_enabled()
        try:
            # Connection owns this command's ID, retry, response and generation.
            def failed(_):
                self.preparing=None; panel.update_enabled()
            result=panel._send('pre.shell.freeze',{'analysis_id':aid},done,failed)
            pending['command_id']=result['command_id']
            if panel.prepared and panel.prepared.get('command_id') is None:
                panel.prepared['command_id']=pending['command_id']
            panel.update_enabled()
        except Exception:
            self.preparing=None; panel.update_enabled(); raise

    def cancel_prepare(self):
        row=self.preparing
        if row is None or not row['command_id']:return
        # Native freeze is cancellable while queued, as with existing Pre freeze.
        # Once native writing begins the owner completes/retains that attempt.
        connection=self.connection
        connection.request('shell-cancel:'+row['command_id'],
            lambda:connection.client.command_cancel(row['command_id']),connection._native_status)

    def run_prepared(self):
        panel=self.panel; owner=self.editor.owner; prepared=panel.prepared
        if not prepared or not prepared.get('command_id'): raise ValueError('입력을 먼저 준비하세요.')
        if panel.pending_changes(): raise ValueError('검토한 입력 이후 편집이 있습니다. 적용 후 새 입력을 준비하세요.')
        record,_,_=self.editor.effective(prepared['analysis_id'])
        if digest(record['applied'])!=prepared['applied_sha256']:
            raise ValueError('검토한 입력과 현재 적용 상태가 다릅니다. 새 입력을 준비하세요.')
        if prepared.get('job_id'):
            self.connection.open_runner(prepared['job_id']); return
        identifier=prepared['command_id']; panel.busy=True; panel.update_enabled()
        def submitted(value):
            panel.busy=False
            if value['origin']['document_id']!=owner.document_id:
                raise ValueError('계산의 원 문서가 일치하지 않습니다.')
            prepared['job_id']=value['job']['id']; panel.prepared=prepared
            self.connection.submit_native('pre.links.record',{'job_id':prepared['job_id']},owner=owner)
            panel.set_status('검토한 입력으로 계산을 등록했습니다. 중단은 계산 목록에서 실행하세요.')
            panel.update_enabled(); self.connection.open_runner(prepared['job_id'])
        def execute():
            try: return {'ok':self.connection.client.native_submit(identifier)}
            except Exception as error: return {'error':str(error)}
        def result(value):
            panel.busy=False
            if 'error' in value:
                panel.set_status(value['error']+' 같은 준비 입력으로 다시 확인할 수 있습니다.')
                panel.update_enabled(); return
            panel.safe(lambda:submitted(value['ok']))
            panel.update_enabled()
        self.connection.request('shell-submit:'+identifier,execute,result)

    def open_result(self):
        prepared=self.panel.prepared
        if not prepared or not prepared.get('job_id'): raise ValueError('계산 목록에서 저장된 결과를 선택하세요.')
        self.connection.open_post(prepared['job_id'])


def install(connection):
    """Add a contextual native menu entry without modifying FEM/solid panels."""
    main=connection.Gui.getMainWindow(); W=connection.QtWidgets
    menu=None
    for action in main.menuBar().actions():
        if action.menu() and action.text().replace('&','') in ('해석','Analysis','FEM'):
            menu=action.menu(); break
    if menu is None: menu=main.menuBar().addMenu('판재')
    action=menu.addAction('판재 셸…')
    action.setToolTip('선택한 해석의 판재 셸, 두께, 방향과 압력을 편집합니다.')
    def show():
        try: connection.show_panel('shell')
        except Exception as error: connection.message.setText(str(error))
    action.triggered.connect(show)
    connection.shell_menu_action=action


def pending_panel(connection, owner):
    dock=getattr(connection,'panels',{}).get(owner.doc.Name,{}).get('shell')
    try:return getattr(dock.widget(),'shell_controller',None) if dock is not None else None
    except RuntimeError:return None


def route(connection, owner, analysis):
    """Invalid saved shell drafts must block rather than fall through to solids."""
    record=owner.read_metadata().get('shells',{}).get(analysis.Name)
    if record is None:return False
    panel=pending_panel(connection,owner)
    if panel is not None and panel.pending_changes():
        raise ValueError('셸 속성에 미적용 편집이 있습니다. 적용하거나 저장본을 다시 읽으세요.')
    owner.shell.effective(analysis.Name)
    return True


def editor_token(connection, owner):
    panel=pending_panel(connection,owner)
    return digest(panel.buffer.snapshot()) if panel is not None else None


def has_unsaved_editor(connection, owner):
    panel=pending_panel(connection,owner)
    return panel is not None and panel.pending_changes()


def flush_before_save(connection, owner, arguments, target, on_done, *, capture_motion=True):
    """Save raw shell fields before the existing document save, including offline.

    This is a Save action, not a numerical Apply. Invalid raw values are kept.
    The native owner's transaction and normal project-save guard remain owners.
    Return None when no shell buffer needs capture.
    """
    from copy import deepcopy
    panel=pending_panel(connection,owner)
    if panel is None or not panel.pending_changes():return None
    if panel.busy:raise ValueError('셸 작업 응답을 확인한 뒤 저장하세요.')
    snapshot=deepcopy(panel.buffer.snapshot()); panel.busy=True; panel.update_enabled()
    def finished(value):
        panel.busy=False
        if value.get('status')!='FAILED':panel.buffer.acknowledge(snapshot)
        panel.show_errors(); panel.update_enabled()
        if on_done:on_done(value)
    def captured(value):
        if value.get('status')=='FAILED':finished(value);return
        try:
            connection.submit_native('document.save',deepcopy(arguments),deepcopy(target),finished,
                owner=owner,_capture_motion_view=capture_motion,_capture_shell=False)
        except Exception as error:
            finished({'status':'FAILED','error':{'message':str(error)}})
    try:
        broker=connection.owners[owner.doc.Name][2]
        if broker.stop.is_set() or not broker.registered.is_set():
            owner.refresh()
            reply=owner.dispatch({'command_id':'C'+uuid.uuid4().hex,'document_id':owner.document_id,
                'session_id':owner.session_id,'expected_generation':owner.generation,
                'operation':'pre.shell.save_draft','arguments':snapshot,'target':{}})
            captured(reply if reply.get('status')=='FAILED' else reply['result'])
            return {'queued':True,'completed':True,'command_id':reply['command_id']}
        return connection.submit_native('pre.shell.save_draft',snapshot,on_done=captured,owner=owner)
    except Exception:
        panel.busy=False;panel.update_enabled();raise
