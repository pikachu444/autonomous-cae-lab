"""Bounded real desktop owner-opening acceptance with an existing saved case.

Run under scripts/native_check.py on Windows. The JSON input names an existing
portable workspace, document kind/id, optional --pyside flag and expected saved
revision. No document, provider answer or calculation fixture is manufactured.
The startup observer uses Qt signals in the product's original CLI process;
it is not a physical OS-input acceptance.
"""
import json
import os
from pathlib import Path
import sys
import time


def write_json(path, value):
    """Publish complete observer/driver messages across the two processes."""
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    # Windows readers may briefly hold a destination handle without delete
    # sharing. Keep atomic publication and retry only that short sharing race.
    deadline=time.monotonic()+.5
    while True:
        try:
            os.replace(temporary,path);return
        except PermissionError:
            if time.monotonic()>=deadline:raise
            time.sleep(.005)


def observe_owner():
    folder=Path(os.environ['CAELAB_OWNER_CAPTURE'])
    expected=json.loads((folder/'expected.json').read_text(encoding='utf-8'))
    attached=False
    def profile(frame,event,arg):
        nonlocal attached
        if attached or event!='return' or frame.f_code.co_name!='__init__':return
        if '/apps/research/' not in frame.f_code.co_filename.replace('\\','/'):return
        window=frame.f_locals.get('self')
        if type(window).__name__ not in {
            'DataWindow','MaterialWindow','NativeMaterialWindow','LawNativeMaterialWindow',
            'NumericalWindow','RequestPlanWindow','ExperimentAnalysisWindow','PDEWindow',
            'SimulationWindow','EvaluationWindow','ExpertWindow','StudyWindow','ReportWindow'}:return
        if not hasattr(window,'document'):return
        attached=True;sys.setprofile(None)
        from PySide6.QtCore import QTimer,QObject,QEvent
        from PySide6.QtWidgets import QApplication,QLineEdit,QPlainTextEdit,QMessageBox,QTabWidget
        from PySide6.QtTest import QTest
        from caelab.storage import canonical_hash
        app=QApplication.instance();timer=QTimer(window);timer.setInterval(80)
        state={'ready':False,'last_command':None,'settled_since':None};deadline=time.monotonic()+100
        selected=None;original_field_text=None
        def snapshot():
            doc=window.document or {}
            field={}
            if isinstance(selected,QLineEdit):
                field={'text':selected.text(),'selection':selected.selectedText(),'focus':selected.hasFocus()}
            elif isinstance(selected,QPlainTextEdit):
                field={'text':selected.toPlainText(),'selection':selected.textCursor().selectedText(),'focus':selected.hasFocus()}
            dirty=bool(getattr(window,'local_dirty',False))
            if hasattr(window,'draft') and isinstance(window.draft,dict):dirty=dirty or window.draft!=doc.get('draft',{})
            if type(window).__name__=='ReportWindow':dirty=dirty or bool(window._edit_buffers) or window.title.text()!=window.draft['title']
            return {'pid':os.getpid(),'parent_pid':os.getppid(),'window_token':id(window),
                'window_class':type(window).__name__,'window_title':window.windowTitle(),
                'document_id':doc.get('id'),'kind':doc.get('kind'),'session_id':doc.get('session_id'),
                'saved_revision':doc.get('saved_revision'),'draft_sha256':canonical_hash(doc.get('draft',{})),
                'local_dirty':dirty,
                'document_dirty':bool(doc.get('dirty')),'allow_close':bool(getattr(window,'_allow_close',False)),
                'busy':bool(getattr(window,'_busy',False)),
                'recovery_review_active':getattr(window,'_recovery_review',None) is not None,
                'message':window.message.text() if hasattr(window,'message') and hasattr(window.message,'text') else None,
                'visible':window.isVisible(),'active_window':window.isActiveWindow(),
                'remembered_focus_is_selected':window.focusWidget() is selected,
                'selected_field':field,'qt_platform':app.platformName()}
        def save(name,value):
            write_json(folder/name,value)
        class FocusTrace(QObject):
            def __init__(self):super().__init__(window);self.events=[]
            def eventFilter(self,watched,event):
                if event.type() in (QEvent.Type.FocusIn,QEvent.Type.FocusOut,
                                    QEvent.Type.WindowActivate,QEvent.Type.WindowDeactivate):
                    self.events.append({'monotonic_ns':time.monotonic_ns(),'event':event.type().name,
                        'reason':str(event.reason()) if hasattr(event,'reason') else None,
                        'watched':'selected_field' if watched is selected else 'owner_window',
                        'state':snapshot()})
                    save('focus-events.json',self.events)
                return False
        def tick():
            nonlocal selected,original_field_text
            try:
                if not state['ready']:
                    if time.monotonic()>deadline:raise TimeoutError('Exact owner did not finish reading')
                    doc=window.document
                    if (not doc or getattr(window,'_busy',False) or getattr(window,'_callbacks',0)
                            or getattr(window,'_worker',None) is not None):
                        state['settled_since']=None;return
                    # Include queued startup inspections, not only the gap
                    # between document_read and its next QTimer callback.
                    if state['settled_since'] is None:
                        state['settled_since']=time.monotonic();return
                    if time.monotonic()-state['settled_since']<.2:return
                    if expected['kind']=='report' and not getattr(window,'assets',{}):return
                    assert doc['id']==expected['document_id'] and doc['kind']==expected['kind']
                    assert doc['saved_revision']==expected['saved_revision']
                    if expected.get('dirty_question'):
                        selected=window.question;selected.show()
                        selected.setPlainText(selected.toPlainText()+'\n소유 창 재사용 확인')
                    elif expected.get('dirty_field'):
                        spec=expected['dirty_field']
                        if isinstance(spec,dict):
                            path=tuple(spec['path'])
                            node=max((p for p in window._nodes if path[:len(p)]==p),key=len)
                            window.tree.setCurrentItem(window._nodes[node]);app.processEvents()
                        selected=(window.fields[tuple(spec['path'])][0] if isinstance(spec,dict)
                                  else getattr(window,spec))
                        assert isinstance(selected,(QLineEdit,QPlainTextEdit))
                        original_field_text=selected.text() if isinstance(selected,QLineEdit) else selected.toPlainText()
                        for tabs in window.findChildren(QTabWidget):
                            for index in range(tabs.count()):
                                if tabs.widget(index).isAncestorOf(selected):tabs.setCurrentIndex(index)
                        selected.show();selected.setFocus()
                        assert selected.isEnabled() and not selected.isReadOnly()
                        if isinstance(selected,QLineEdit):
                            selected.setCursorPosition(len(selected.text()));QTest.keyClicks(selected,' _owner_buffer')
                            selected.clearFocus();app.processEvents()
                        else:selected.insertPlainText(' _owner_buffer')
                        assert snapshot()['local_dirty'],'The real editable field did not create a protected buffer'
                    else:
                        selected=next((w for w in window.findChildren(QLineEdit)
                            if w.isVisible() and w.isEnabled() and not w.isReadOnly()),None)
                    if selected:
                        trace=window._owner_probe_focus_trace=FocusTrace()
                        window.installEventFilter(trace);selected.installEventFilter(trace)
                        selected.setFocus();selected.selectAll()
                    window.resize(1280,820);app.processEvents()
                    if expected.get('capture'):
                        assert window.grab().save(str(folder/'owner-normal.png'))
                        window.resize(960,720);app.processEvents()
                        assert window.grab().save(str(folder/'owner-narrow.png'))
                    state['ready']=True;save('ready.json',snapshot())
                save('state.json',snapshot())
                request=folder/'command.json'
                if not request.exists():return
                command=json.loads(request.read_text(encoding='utf-8'))
                if command['sequence']==state['last_command']:return
                # A readiness snapshot does not reserve the asynchronous owner.
                # Wait before consuming a command rather than type into a field
                # temporarily disabled by a subsequent product read.
                if (getattr(window,'_busy',False) or getattr(window,'_callbacks',0)
                        or getattr(window,'_worker',None) is not None):return
                if command['action']=='close_restore' and selected is not None and not selected.isEnabled():return
                state['last_command']=command['sequence']
                assert command['action'] in {'close_cancel','close_discard','close_restore','close_reload'}
                if command['action']=='close_reload':
                    # Explicit existing Reload restores the Expert's sticky local
                    # edit flag without applying or saving the controlled buffer.
                    window.reload_remote();restore=QTimer(window);restore.setInterval(50)
                    window._owner_probe_restore_timer=restore;end=time.monotonic()+20
                    def close_reloaded():
                        if time.monotonic()>end:
                            restore.stop();save('child-error.json',{'error':'Explicit Reload did not finish',**snapshot()});return
                        if getattr(window,'_busy',False) or snapshot()['local_dirty']:return
                        restore.stop();accepted=window.close()
                        save('command-'+str(command['sequence'])+'.json',{'accepted':accepted,'explicit_restore':'reload_existing_owner',**snapshot()})
                    restore.timeout.connect(close_reloaded);restore.start();return
                if command['action']=='close_restore':
                    assert original_field_text is not None
                    selected.setFocus();selected.selectAll()
                    if isinstance(selected,QLineEdit):
                        QTest.keyClicks(selected,original_field_text);selected.clearFocus();app.processEvents()
                    else:selected.insertPlainText(original_field_text)
                    assert not snapshot()['local_dirty'],'Restoring the actual field must clear its protected buffer'
                old=QMessageBox.question
                QMessageBox.question=lambda *a,**k:(QMessageBox.StandardButton.Cancel
                    if command['action']=='close_cancel' else QMessageBox.StandardButton.Discard)
                modal=QTimer(window);modal.setInterval(30)
                def cancel_owned_question():
                    if command['action']!='close_cancel':return
                    for dialog in window.findChildren(QMessageBox):
                        if not dialog.isVisible():continue
                        button=next((b for b in dialog.buttons() if dialog.buttonRole(b)==QMessageBox.ButtonRole.RejectRole),None)
                        if button is not None:
                            dialog.grab().save(str(folder/'close-cancel-dialog.png'));button.click();modal.stop();return
                modal.timeout.connect(cancel_owned_question);modal.start()
                try:accepted=window.close()
                finally:modal.stop();modal.deleteLater();QMessageBox.question=old
                save('command-'+str(command['sequence'])+'.json',{'accepted':accepted,**snapshot()})
            except BaseException as error:
                timer.stop();save('child-error.json',{'error':repr(error),**snapshot()})
                window._allow_close=True;window.close();app.exit(1)
        app.aboutToQuit.connect(lambda:save('exited.json',snapshot()))
        timer.timeout.connect(tick);timer.start()
    sys.setprofile(profile)


def main(case_path,out_path):
    import shutil
    import subprocess
    import threading
    from contextlib import ExitStack
    from unittest.mock import patch
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from apps.research import desktop
    from PySide6.QtWidgets import QApplication
    from caelab.storage import canonical_hash
    from caelab.workbench_client import Client
    case=json.loads(Path(case_path).read_text(encoding='utf-8'))
    assert case['kind'] in {'data','material','numerical','pde','simulation','evaluation','expert','study','report'}
    if case['kind']=='data' and not case.get('pyside'):
        raise ValueError('Use the dedicated native Data driver for the default installed Data owner')
    out=Path(out_path).resolve();out.mkdir(parents=True,exist_ok=False)
    store=out/'한글 공백 원 보관소';other=out/'다른 보관소 같은 이름'
    if case.get('prepared_stores'):
        store,other=map(lambda value:Path(value).resolve(),case['prepared_stores'])
        assert store!=other and store.is_dir() and other.is_dir()
        for selected_store in (store,other):
            saved=selected_store/'workbench/documents'/case['document_id']/'revisions'/case['saved_revision']/'revision.json'
            import hashlib
            assert hashlib.sha256(saved.read_bytes()).hexdigest()==case['source_revision_sha256']
    else:
        shutil.copytree(Path(case['workspace']).resolve(),store);shutil.copytree(store,other)
    app=QApplication.instance() or QApplication([])
    services=[];processes=[];record={}
    def service(path):
        server=LabHTTPServer(LabService(path),0);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
        services.append((server,thread));client=Client(f'http://127.0.0.1:{server.server_port}')
        def forbidden(*a,**k):raise AssertionError('Opening an owner cannot submit a calculation/provider')
        server.workbench.submit=server.workbench.manager.submit=forbidden
        for owner in server.workbench.research_owners():owner.submit=forbidden
        return server.workbench,client
    def load(path):return json.loads(path.read_text(encoding='utf-8'))
    def wait(path,process=None):
        end=time.monotonic()+110
        while time.monotonic()<end:
            app.processEvents()
            error=path.parent/'child-error.json'
            if error.exists():raise AssertionError(error.read_text(encoding='utf-8'))
            if path.exists():return load(path)
            if process is not None and process.poll() is not None:raise AssertionError('Owner exited before readiness')
            time.sleep(.03)
        raise TimeoutError(str(path))
    try:
        wb,client=service(store);wb2,client2=service(other)
        before=client.document_read(case['document_id']);before2=client2.document_read(case['document_id'])
        assert before['title']==before2['title'] and before['id']==before2['id']
        jobs=[{j['id'] for j in service.manager.list()} for service in (wb,wb2)]
        original_popen=desktop.subprocess.Popen
        def tracked(*args,**kwargs):
            if case.get('pyside'):
                arguments=list(args[0])
                if 'apps.research.desktop' in arguments and 'data' in arguments and '--pyside' not in arguments:
                    args=(arguments+['--pyside'],*args[1:])
            process=original_popen(*args,**kwargs);processes.append(process);return process
        bootstrap=out/'startup';bootstrap.mkdir()
        (bootstrap/'sitecustomize.py').write_text("import os,runpy\nrunpy.run_path(os.environ['CAELAB_OWNER_OBSERVER'],run_name='_caelab_owner_observer')\n",encoding='utf-8')
        def configure(folder, *, clean_reopen=False):
            observed={**case,'saved_revision':before['saved_revision']}
            if clean_reopen:
                observed['dirty_field']=None;observed['dirty_question']=False
            folder.mkdir();write_json(folder/'expected.json',observed)
            os.environ['CAELAB_OWNER_CAPTURE']=str(folder)
        with ExitStack() as stack:
            stack.enter_context(patch.object(desktop.subprocess,'Popen',tracked))
            stack.enter_context(patch.dict(os.environ,{'PYTHONPATH':str(bootstrap)+os.pathsep+str(Path.cwd())+os.pathsep+os.environ.get('PYTHONPATH',''),
                'CAELAB_OWNER_OBSERVER':str(Path(__file__).resolve()),'QT_QPA_PLATFORM':'windows'}))
            folder=out/'first';configure(folder)
            first=desktop.launch_tool(client,case['kind'],document_id=case['document_id'])
            ready=wait(folder/'ready.json');assert ready['qt_platform']=='windows'
            count=len(processes);second=desktop.launch_tool(client,case['kind'],document_id=case['document_id'])
            assert second['status']=='ACTIVATED',second
            assert len(processes)==count,'Same owner launch created another process'
            time.sleep(.2);state=wait(folder/'state.json')
            for key in ('pid','window_token','document_id','session_id','draft_sha256','local_dirty','selected_field'):
                assert state[key]==ready[key],(key,state[key],ready[key])
            write_json(out/'activation.json',{'first':first,'activation':second,'first_owner':ready,'after_activation':state})
            direct=None
            if case.get('direct_cli'):
                arguments=[sys.executable,'-m','apps.research.desktop','--service',client.url,
                           case['kind'],'--document-id',case['document_id']]
                if case.get('pyside'):arguments.append('--pyside')
                direct_process=original_popen(arguments,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                    text=True,encoding='utf-8',env=os.environ.copy());processes.append(direct_process)
                stdout,stderr=direct_process.communicate(timeout=45)
                direct={'arguments':arguments,'pid':direct_process.pid,'exit_code':direct_process.returncode,
                        'stdout':stdout,'stderr':stderr}
                assert direct_process.returncode==0,direct
                time.sleep(.2);state=wait(folder/'state.json')
                direct['same_owner_after']=state
                write_json(out/'direct-cli.json',direct)
                for key in ('pid','window_token','document_id','session_id','draft_sha256','local_dirty','selected_field'):
                    assert state[key]==ready[key],('direct_cli',key,state[key],ready[key])
            cancelled=None
            if case.get('dirty_question') or case.get('dirty_field'):
                write_json(folder/'command.json',{'sequence':1,'action':'close_cancel'})
                cancelled=wait(folder/'command-1.json')
                assert cancelled['accepted'] is False and cancelled['visible']
                assert cancelled['local_dirty'] and cancelled['selected_field']['text']==ready['selected_field']['text']
                count=len(processes)
                assert desktop.launch_tool(client,case['kind'],document_id=case['document_id'])['status']=='ACTIVATED'
                assert len(processes)==count and not (folder/'exited.json').exists()
            folder2=out/'other-store';configure(folder2)
            different=desktop.launch_tool(client2,case['kind'],document_id=case['document_id']);ready2=wait(folder2/'ready.json')
            assert ready2['pid']!=ready['pid'] and ready2['session_id']!=ready['session_id']
            for current,f in [(first,folder),(different,folder2)]:
                close_action=('close_reload' if case.get('reload_before_accepted_close') else
                              'close_restore' if case.get('restore_before_accepted_close') else 'close_discard')
                write_json(f/'command.json',{'sequence':2,'action':close_action})
                wait(f/'exited.json')
            # Closed-owner re-open must use the same selected saved document.
            clean_reopen=bool(case.get('clean_reopen'))
            folder3=out/'reopened';configure(folder3,clean_reopen=clean_reopen)
            reopened=desktop.launch_tool(client,case['kind'],document_id=case['document_id']);ready3=wait(folder3/'ready.json')
            assert ready3['pid']!=ready['pid'] and ready3['document_id']==ready['document_id']
            assert ready3['draft_sha256']==ready['draft_sha256']
            reopen_close='close_discard' if clean_reopen else close_action
            write_json(folder3/'command.json',{'sequence':1,'action':reopen_close});wait(folder3/'exited.json')
            assert client.document_read(before['id'])['draft']==before['draft']
            assert client2.document_read(before2['id'])['draft']==before2['draft']
            for current,expected in zip((wb,wb2),jobs):assert {j['id'] for j in current.manager.list()}==expected
            record={'status':'PASS_EXACT_OWNER_REUSE_SEPARATE_STORE_REOPEN','kind':case['kind'],'document_id':before['id'],
                'first':first,'activation':second,'other_store':different,'closed_reopen':reopened,
                'first_owner':ready,'other_owner':ready2,'reopened_owner':ready3,'new_jobs':0,
                'provider_calls':0,'cancelled_close':cancelled,'direct_cli':direct,'pyside_compatibility':bool(case.get('pyside')),
                'qt_signal_observation_only':True,'clean_reopen':clean_reopen}
            write_json(out/'result.json',record)
            print('EXACT_OWNER_OPEN_PASS',case['kind'],flush=True)
    finally:
        for child in processes:
            if child.poll() is None:
                try:child.wait(timeout=3)
                except subprocess.TimeoutExpired:child.terminate();child.wait(timeout=5)
        for server,thread in reversed(services):server.shutdown();server.server_close();thread.join(3);server.workbench.shutdown()


if __name__=='_caelab_owner_observer':observe_owner()
elif __name__=='__main__':main(*sys.argv[1:])
