"""Actual existing owner/HTTP saves; inject only an explicit storage failure."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import threading
import time
import uuid
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('caelab.related_save')
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from apps.research.material_related_save import RelatedSaveDialog


def test_receipt_rows_keep_owner_selection_and_enter_escape_do_not_save():
    """Display/keyboard fixture only; real HTTP saves are checked separately."""
    app=QApplication.instance() or QApplication([])
    material=dict(id='Mdisplay',kind='material',title='보존할 인장 재료',session_id='Sdisplay',
        generation=0,input_revision='Idisplay',draft={},saved_revision=None)
    plan=dict(material,id='Ndisplay',kind='numerical',title='별도 DOE 계획')
    calls=[]
    class PreviewOnly:
        def data_material(self,operation,arguments):
            calls.append(operation);assert operation=='related_save.preview'
            return dict(receipt_id='Sdisplay',saveable_count=2,
                targets=[dict(target,preview_problems=[]) for target in arguments['requests']])
    dialog=RelatedSaveDialog(PreviewOnly(),material,plan)
    try:
        dialog.show();wait(app,lambda:dialog.preview is not None and not dialog._busy)
        rows=[dict(target,state=state,attempts=[]) for target,state in zip(dialog.requests,('SAVED','FAILED'))]
        dialog._show(rows)
        assert dialog.table.currentRow()==1
        dialog._show(list(reversed(rows)))
        assert dialog.table.item(dialog.table.currentRow(),0).data(Qt.ItemDataRole.UserRole)=='Ndisplay'
        dialog.table.setFocus();QTest.keyClick(dialog.table,Qt.Key.Key_Return);app.processEvents()
        assert not dialog.isVisible() and calls==['related_save.preview']
        dialog.show();QTest.keyClick(dialog.table,Qt.Key.Key_Escape);app.processEvents()
        assert not dialog.isVisible() and calls==['related_save.preview']
    finally:dialog.close();app.processEvents()


def wait(app, ready):
    end = time.monotonic() + 15
    while time.monotonic() < end:
        app.processEvents()
        if ready(): return
        QTest.qWait(10)
    raise AssertionError('Related save GUI reply timeout')


def test_preview_cancel_does_not_emit_or_retain_a_save_attempt():
    app = QApplication.instance() or QApplication([])
    material = dict(id='Mfixture', kind='material', title='인장 재료', session_id='Sfixture',
        generation=0, input_revision='Ifixture', draft={}, saved_revision=None)
    plan = dict(material, id='Nfixture', kind='numerical', title='인장 피팅')
    calls = []
    class PreviewTransport:
        def data_material(self, operation, arguments):
            calls.append(operation)
            assert operation == 'related_save.preview'
            return dict(receipt_id='Spreview', saveable_count=2,
                targets=[dict(target, preview_problems=[]) for target in arguments['requests']])
    dialog = RelatedSaveDialog(PreviewTransport(), material, plan)
    attempted = []; dialog.saveAttempted.connect(attempted.append)
    try:
        wait(app, lambda: dialog.preview is not None and not dialog._busy)
        dialog.reject()
        assert not attempted and dialog.pending_preview is None
        assert calls == ['related_save.preview']
    finally: dialog.close(); app.processEvents()


def test_actual_partial_save_only_retries_failed_plan_then_explicitly_links(tmp_path, monkeypatch):
    from apps.lab.service import LabService
    from apps.lab.server import LabHTTPServer
    from caelab.workbench_client import Client
    from caelab.numerical_document import from_material_document
    app = QApplication.instance() or QApplication([])
    service = LabService(tmp_path); server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True); thread.start()
    client = Client(f'http://127.0.0.1:{server.server_port}')
    def command(document, operation, arguments=None):
        return client.document_command(document['id'], operation, arguments or {},
            session_id=document['session_id'], expected_generation=document['generation'],
            command_id='C' + uuid.uuid4().hex)['document']
    dialog = None
    try:
        material = command(client.document_open(kind='material', title='인장 재료'), 'document.save')
        plan = command(client.document_open(kind='numerical', title='인장 피팅', draft=from_material_document(material)), 'document.save')
        old_reference = deepcopy(plan['draft']['material'])
        old_plan_revision = plan['saved_revision']
        draft = deepcopy(material['draft']); draft['settings']['parameters']['E'] = 1250.
        material = command(material, 'material.update', {'draft': draft})
        draft = deepcopy(plan['draft']); draft['variables'][0]['value'] = 1200.
        plan = command(plan, 'numerical.update', {'draft': draft})
        owner = server.workbench.numerical_documents
        original_save = owner._save
        refused = []
        def fail_once(document):
            if not refused:
                refused.append(document['id']); raise PermissionError('Injected Plan save permission failure')
            return original_save(document)
        monkeypatch.setattr(owner, '_save', fail_once)
        dialog = RelatedSaveDialog(client, material, plan)
        wait(app, lambda: dialog.preview is not None and not dialog._busy)
        assert dialog.save_button.isEnabled()
        dialog.save(); wait(app, lambda: dialog.receipt is not None and not dialog._busy)
        assert [target['state'] for target in dialog.receipt['targets']] == ['SAVED', 'FAILED']
        saved_material = deepcopy(dialog.receipt['targets'][0]['saved_reference'])
        assert client.document_read(plan['id'])['draft']['material'] == old_reference
        assert client.document_read(plan['id'])['saved_revision'] == old_plan_revision
        assert not dialog.link_button.isEnabled()
        dialog.table.selectRow(1); assert dialog.retry_button.isEnabled()
        dialog.retry_selected(); wait(app, lambda: dialog.receipt['all_saved'] and not dialog._busy)
        assert len(dialog.receipt['targets'][0]['attempts']) == 1
        assert len(dialog.receipt['targets'][1]['attempts']) == 2
        assert dialog.receipt['targets'][0]['saved_reference'] == saved_material
        assert client.document_read(plan['id'])['draft']['material'] == old_reference
        assert dialog.link_button.isEnabled()
        dialog.publish(); wait(app, lambda: dialog.receipt['publication']['state'] == 'PUBLISHED' and not dialog._busy)
        final_plan = client.document_read(plan['id'])
        assert final_plan['draft']['material']['saved_revision'] == saved_material['saved_revision']
        assert final_plan['draft']['material']['input_revision'] == material['input_revision']
        assert not final_plan['runs'] and not client.document_read(material['id'])['runs']
        receipt_id = dialog.receipt['receipt_id']
        assert client.data_material('related_save.receipt', {'receipt_id': receipt_id})['publication']['state'] == 'PUBLISHED'
        dialog.close()
        server.shutdown(); server.server_close(); service.shutdown(); thread.join(2)
        service = LabService(tmp_path); server = LabHTTPServer(service, 0)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True); thread.start()
        client = Client(f'http://127.0.0.1:{server.server_port}')
        cold_material = client.document_read(material['id'])
        cold_plan = client.document_read(plan['id'])
        assert cold_plan['saved_revision'] == final_plan['saved_revision']
        assert cold_plan['draft'] == final_plan['draft']
        dialog = RelatedSaveDialog(client, cold_material, cold_plan, receipt_id=receipt_id)
        wait(app, lambda: dialog.receipt is not None and not dialog._busy)
        assert dialog.receipt['publication']['state'] == 'PUBLISHED'
        assert dialog.receipt['targets'][0]['saved_reference'] == saved_material
        assert not dialog.save_button.isEnabled() and not dialog.retry_button.isEnabled()
    finally:
        if dialog: dialog.close()
        app.processEvents(); server.shutdown(); server.server_close(); service.shutdown(); thread.join(2)


def _retained_host(workspace):
    """A real local HTTP owner, with every calculation submission prohibited."""
    from contextlib import contextmanager
    from apps.lab.service import LabService
    from apps.lab.server import LabHTTPServer
    from caelab.workbench_client import Client
    @contextmanager
    def host():
        service=LabService(workspace);server=LabHTTPServer(service,0)
        def prohibited(*args,**kwargs):raise AssertionError('Related-save must not submit a calculation')
        server.workbench.submit=server.workbench.manager.submit=prohibited
        thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
        try:yield server,Client(f'http://127.0.0.1:{server.server_port}')
        finally:server.shutdown();server.server_close();service.shutdown();thread.join(2)
    return host()


def _retained_window(app,client,material_id,plan_id):
    from apps.research.material_window import MaterialWindow
    window=MaterialWindow(client,auto_open=False,poll_interval=0)
    window._show_document(client.document_read(material_id));window.show()
    panel=window.open_plan_variables()
    wait(app,lambda:not panel._busy and panel.plans.findData(plan_id)>=0)
    panel.plans.setCurrentIndex(panel.plans.findData(plan_id))
    wait(app,lambda:plan_id in panel._widgets)
    return window,panel,panel._widgets[plan_id]


def _capture_related(app,widget,folder,name):
    for label,size in [('normal',(850,410)),('narrow',(640,410))]:
        widget.resize(*size);app.processEvents();QTest.qWait(40)
        assert widget.grab().save(str(folder/(name+'-'+label+'.png')))


def test_retained_c1_material_plan_partial_save_and_cold_raw_recovery(tmp_path,monkeypatch):
    """Opt-in: existing C1 owners, one small copy, real HTTP/Qt and a new Python."""
    source_setting=os.environ.get('CAELAB_RELATED_SAVE_SOURCE')
    if not source_setting:pytest.skip('Explicit retained C1 source was not supplied')
    import hashlib,json,shutil,subprocess,sys
    from pathlib import Path
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialogButtonBox,QLineEdit
    from apps.research.appearance import apply_appearance
    from apps.research.material_plan_panel import PlanPatchDialog
    from apps.research.material_recovery import material_raw_snapshot
    from apps.research.data_material_recovery_dialog import RecoveryKeepDialog
    from apps.research.data_material_recovery_host import _views
    from apps.research.recovery_focus import RawEditorFocusGuard
    source=Path(source_setting)
    if source.is_file():source=Path(json.loads(source.read_text(encoding='utf-8'))['second_receipt']['workspace'])
    def pins():return {str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    original=pins();files=list(source.rglob('*'))
    assert len(original)==93 and sum(p.stat().st_size for p in files if p.is_file())==925618
    workspace=Path(os.environ.get('CAELAB_RELATED_SAVE_COPY',str(tmp_path/'C1 작업 사본')))
    if not workspace.exists():shutil.copytree(source,workspace)
    folder=Path(os.environ.get('CAELAB_RELATED_SAVE_RENDERS',str(tmp_path/'renders')));folder.mkdir(parents=True,exist_ok=True)
    mid='M46a5c0963d134b9a86dd01a4652c85a7';nid='N7ff9690b2efc4164a27c45fb08496ef3'
    app=QApplication.instance() or QApplication([]);apply_appearance(app)
    windows=[];dialogs=[];errors=[];record={'source_files':93,'source_bytes':925618,'controlled_failures':[]}
    try:
        with _retained_host(workspace) as (server,client):
            window,panel,widget=_retained_window(app,client,mid,nid);windows.append(window)
            m0=deepcopy(window.document);p0=client.document_read(nid)
            assert p0['draft']['mode']=='doe' and not m0['runs'] and not p0['runs']
            assert m0['saved_revision']=='Rf3ee524ce28b4be58a9c746a47e9e26a'
            assert p0['saved_revision']=='Rda3e985dd89148999aac6221e806f51e'
            before_m=deepcopy(m0['draft']);before_p=deepcopy(p0['draft']);old_ref=deepcopy(before_p['material'])
            # Actual live editor: opening Save must neither commit nor discard it.
            table=window.coefficients;table.setCurrentCell(0,1);table.editItem(table.item(0,1));app.processEvents()
            line=next(e for e in table.findChildren(QLineEdit) if e.isVisible());line.setText('1e')
            assert panel.save_related() is False and line.text()=='1e'
            assert client.document_read(mid)['draft']==before_m
            QTest.keyClick(line,Qt.Key.Key_Escape);app.processEvents()
            assert table.item(0,1).text()!='1e'
            # Multi-cell paste and focused local Undo do not change either owner.
            window.raise_();window.activateWindow();QTest.qWait(100)
            widget.table.setFocus();widget.table.setCurrentCell(0,2);app.processEvents()
            app.clipboard().setText('1300\t120');QTest.qWait(50)
            if app.clipboard().text()=='1300\t120':
                assert widget.table.paste_cells();record['clipboard_paste']='OBSERVED'
            else:
                record['clipboard_paste']='NOT_OBSERVED_WINDOWS_CLIPBOARD_EMPTY'
                widget.table.item(0,2).setText('1300');widget.table.item(0,3).setText('120')
            app.processEvents();widget.undo()
            assert widget.buffer_snapshot()==before_p
            window.coefficients.item(0,1).setText('1250')
            widget.table.item(0,2).setText('1200');app.processEvents()
            assert panel.save_related() is False
            assert client.document_read(nid)['draft']==before_p
            window.apply_inputs();wait(app,lambda:not window._busy)
            assert window.document['draft']['settings']['parameters']['E']==1250
            # Keep the real Apply review modal and its normal Qt event loop.
            def apply_review():
                d=next((d for d in app.topLevelWidgets() if isinstance(d,PlanPatchDialog) and d.isVisible()),None)
                if d is None:QTimer.singleShot(10,apply_review);return
                d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Apply).click()
            QTimer.singleShot(10,apply_review);widget.preview_changes()
            wait(app,lambda:not panel._busy and not widget._busy and not widget.has_unapplied_buffer())
            assert client.document_read(nid)['draft']['variables'][0]['value']==1200
            # Inject only the Plan's filesystem boundary, after real HTTP review.
            original_save=server.workbench.numerical_documents._save;refused=[]
            def fail_once(document):
                if not refused:
                    refused.append(document['id']);raise PermissionError('Controlled C1 Plan storage failure')
                return original_save(document)
            monkeypatch.setattr(server.workbench.numerical_documents,'_save',fail_once)
            captured=[]
            def save_modal():
                d=next((d for d in app.topLevelWidgets() if isinstance(d,RelatedSaveDialog) and d.isVisible()),None)
                if d is None:QTimer.singleShot(10,save_modal);return
                def ready():
                    if d._busy or d.preview is None:QTimer.singleShot(10,ready);return
                    d.save_button.click()
                    def finish():
                        if d._busy:QTimer.singleShot(10,finish);return
                        try:
                            assert d.receipt and [t['state'] for t in d.receipt['targets']]==['SAVED','FAILED'],d.message.text()
                            assert d.table.currentRow()==1 and d.retry_button.isEnabled()
                            _capture_related(app,d,folder,'partial-save');captured.append(deepcopy(d.receipt))
                        except BaseException as error:errors.append(error)
                        d.close_button.click()
                    finish()
                ready()
            QTimer.singleShot(10,save_modal);assert panel.save_related();assert not errors,errors
            receipt=captured[0];rid=receipt['receipt_id'];record['partial_receipt']=receipt
            assert refused==[nid] and len(receipt['targets'][0]['attempts'])==1
            assert client.document_read(nid)['saved_revision']==p0['saved_revision']
            assert client.document_read(nid)['draft']['material']==old_ref
            # Prepare two raw capsules from the existing host view list, not a new schema.
            window.coefficients.item(0,1).setText('1e')
            widget.table.setCurrentCell(0,2);widget.table.editItem(widget.table.item(0,2));app.processEvents()
            widget._live_editor().setText('2e')
            with RawEditorFocusGuard([window]):
                identities={d['id']:client.data_material('recovery.identity',{'document_id':d['id']}) for d,_,_ in _views(window)}
                def capture():return [{'identity':deepcopy(identities[d['id']]),'raw':snapshot()}
                                      for d,snapshot,_ in _views(window)]
                raw_requests=capture();assert {r['identity']['document_id'] for r in raw_requests}=={mid,nid}
                d=RecoveryKeepDialog(client,[item[0] for item in _views(window)],capture,window);dialogs.append(d);d.show()
                wait(app,lambda:d.preview is not None and not d._busy)
                # This controlled capsule transport failure must not permit close.
                transport=client.data_material
                def fail_capsule(operation,args):
                    if operation=='recovery.execute':raise OSError('Controlled capsule acknowledgement failure')
                    return transport(operation,args)
                monkeypatch.setattr(client,'data_material',fail_capsule)
                d.keep_button.click();wait(app,lambda:not d._busy)
                assert not d.close_ready and d.isVisible() and d.outcome is None
                assert capture()==raw_requests
                record['controlled_failures']=['Plan _save permission failure','capsule transport before execute']
                monkeypatch.setattr(client,'data_material',transport)
                d.keep_button.click();wait(app,lambda:d.close_ready and not d._busy)
                assert d.outcome['all_kept'] and d.gate['close_permitted']
                assert capture()==raw_requests
                record['capsules']=d.outcome['targets']
            assert not server.workbench.manager.list()
            ipc=folder/'cold-input.json';ipc.write_text(json.dumps(dict(workspace=str(workspace),mid=mid,nid=nid,
                receipt_id=rid,raw_requests=raw_requests,capsules=record['capsules'],old_reference=old_ref,
                saved_material=receipt['targets'][0]['saved_reference']),ensure_ascii=False),encoding='utf-8')
            for d in dialogs:d.close()
            window._allow_close=True;window.close();app.processEvents()
        # A distinct Python, HTTP service, session and actual Qt window.
        env=dict(os.environ,CAELAB_RELATED_SAVE_COLD=str(ipc));env.pop('CAELAB_RELATED_SAVE_SOURCE',None)
        result=subprocess.run([sys.executable,'-m','pytest',__file__+'::test_retained_related_save_cold_process',
            '-q','--basetemp='+str(tmp_path/'cold-process')],env=env,text=True,capture_output=True,timeout=120)
        (folder/'cold-stdout.log').write_text(result.stdout,encoding='utf-8');(folder/'cold-stderr.log').write_text(result.stderr,encoding='utf-8')
        assert result.returncode==0,result.stdout+result.stderr
        record['cold']=json.loads((folder/'cold-result.json').read_text(encoding='utf-8'))
        assert record['cold']['pid']!=os.getpid() and record['cold']['receipt_id']==rid
        record['source_unchanged']=pins()==original;assert record['source_unchanged']
        record['new_jobs']=0;record['solver_calls']=0
        (folder/'flow.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        for d in dialogs:d.close()
        for w in windows:w._allow_close=True;w.close()
        app.processEvents()
        assert pins()==original


def test_retained_related_save_cold_process():
    """Invoked explicitly by the retained-owner test in a separate interpreter."""
    ipc=os.environ.get('CAELAB_RELATED_SAVE_COLD')
    if not ipc:pytest.skip('Separate-process recovery input was not supplied')
    import json
    from pathlib import Path
    from apps.research.appearance import apply_appearance
    from apps.research.material_recovery import restore_material_raw,material_raw_snapshot
    from apps.research.recovery_focus import RawEditorFocusGuard
    from PySide6.QtWidgets import QLineEdit
    data=json.loads(Path(ipc).read_text(encoding='utf-8'));folder=Path(ipc).parent
    app=QApplication.instance() or QApplication([]);apply_appearance(app);window=dialog=guard=None
    try:
        with _retained_host(Path(data['workspace'])) as (server,client):
            window,panel,widget=_retained_window(app,client,data['mid'],data['nid'])
            before={i:client.document_read(i) for i in (data['mid'],data['nid'])}
            originals={r['identity']['document_id']:r['raw'] for r in data['raw_requests']}
            if os.environ.get('CAELAB_RELATED_SAVE_HOST_RECEIPT')=='1':
                # Continue from an already-retried receipt; never restore an old
                # Plan capsule over its newer saved metadata or repeat a save.
                target=next(t for t in data['capsules'] if t['identity']['document_id']==data['mid'])
                recovered=client.data_material('recovery.recover',dict(document_id=data['mid'],capsule_id=target['capsule_id'],
                    identity=client.data_material('recovery.identity',{'document_id':data['mid']}),acknowledge_session_change=True))
                assert recovered['state']=='RESUME_READY'
                restore_material_raw(window,recovered['raw'])
                receipt_before=client.data_material('related_save.receipt',{'receipt_id':data['receipt_id']})
                def receipt_body(value):
                    value=deepcopy(value);value.pop('updated_utc',None);return value
                assert receipt_before['all_saved'] and panel.save_receipt_button.isEnabled()
                errors=[];observed=[]
                from PySide6.QtCore import QTimer
                def read_modal():
                    d=next((d for d in app.topLevelWidgets() if isinstance(d,RelatedSaveDialog) and d.isVisible()),None)
                    if d is None:QTimer.singleShot(10,read_modal);return
                    def ready():
                        if d._busy or d.receipt is None:QTimer.singleShot(10,ready);return
                        try:
                            assert receipt_body(d.receipt)==receipt_body(receipt_before) and not d.allow_writes
                            assert not any(b.isEnabled() for b in (d.save_button,d.retry_button,d.link_button,d.resume_button))
                            _capture_related(app,d,folder,'host-receipt');observed.append(True)
                        except BaseException as error:errors.append(error)
                        d.close_button.click()
                    ready()
                QTimer.singleShot(10,read_modal)
                assert panel.save_related(receipt_id=data['receipt_id']) and observed and not errors,errors
                assert window.coefficients.item(0,1).text()=='1e'
                assert receipt_body(client.data_material('related_save.receipt',{'receipt_id':data['receipt_id']}))==receipt_body(receipt_before)
                assert all(client.document_read(i)['draft']==d['draft'] for i,d in before.items())
                assert not server.workbench.manager.list()
                (folder/'host-result.json').write_text(json.dumps(dict(pid=os.getpid(),production_host_entry=True,
                    receipt_id=data['receipt_id'],receipt_targets_and_attempts_unchanged=True,raw_preserved=True,new_jobs=0),indent=2),encoding='utf-8')
                return
            for target in data['capsules']:
                identifier=target['identity']['document_id'] if 'identity' in target else target['document_id']
                recovered=client.data_material('recovery.recover',dict(document_id=identifier,capsule_id=target['capsule_id'],
                    identity=client.data_material('recovery.identity',{'document_id':identifier}),acknowledge_session_change=True))
                assert recovered['state']=='RESUME_READY' and recovered['raw']==originals[identifier]
                if identifier==data['mid']:restore_material_raw(window,recovered['raw'])
                else:widget.restore_recovery(recovered['raw'])
            assert window.coefficients.item(0,1).text()=='1e'
            assert widget._live_editor().text()=='2e'
            assert panel._related_save_receipts[data['nid']]==data['receipt_id']
            assert material_raw_snapshot(window)['local_draft']==originals[data['mid']]['local_draft']
            guard=RawEditorFocusGuard([window]);guard.__enter__()
            for size,label in [((1440,950),'normal'),((1000,760),'narrow')]:
                window.resize(*size);app.processEvents();assert window.grab().save(str(folder/('cold-raw-'+label+'.png')))
            # Receipt inspection with raw buffers is read-only and leaves both owners untouched.
            dialog=RelatedSaveDialog(client,before[data['mid']],before[data['nid']],receipt_id=data['receipt_id'],allow_writes=False)
            dialog.show();wait(app,lambda:dialog.receipt is not None and not dialog._busy)
            assert not dialog.retry_button.isEnabled() and not dialog.save_button.isEnabled()
            _capture_related(app,dialog,folder,'cold-raw-receipt');dialog.close()
            # User cancels the pending delegate and undoes the local raw cell; no owner Undo.
            editor=widget._live_editor();assert isinstance(editor,QLineEdit)
            QTest.keyClick(editor,Qt.Key.Key_Escape);app.processEvents()
            guard.__exit__();guard=None
            if widget.has_unapplied_buffer():widget.undo()
            window.undo_inputs();app.processEvents()
            assert not widget.has_unapplied_buffer() and not window.local_dirty
            dialog=RelatedSaveDialog(client,client.document_read(data['mid']),client.document_read(data['nid']),receipt_id=data['receipt_id'])
            dialog.show();wait(app,lambda:dialog.receipt is not None and not dialog._busy)
            assert dialog.table.currentRow()==1 and dialog.retry_button.isEnabled()
            dialog.retry_button.click();wait(app,lambda:dialog.receipt['all_saved'] and not dialog._busy)
            assert dialog.receipt['targets'][0]['saved_reference']==data['saved_material']
            assert [len(t['attempts']) for t in dialog.receipt['targets']]==[1,2]
            assert client.document_read(data['nid'])['draft']['material']==data['old_reference']
            for identifier,old in before.items():
                assert client.document_read(identifier)['draft']==old['draft']
                assert not client.document_read(identifier)['runs']
            assert not server.workbench.manager.list()
            _capture_related(app,dialog,folder,'cold-retry')
            (folder/'cold-result.json').write_text(json.dumps(dict(pid=os.getpid(),receipt_id=data['receipt_id'],
                receipt=dialog.receipt,raw_restored=True,read_only_inspection=True,local_undo=True,new_jobs=0),ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        if guard:guard.__exit__()
        if dialog:dialog.close()
        if window:window._allow_close=True;window.close()
        app.processEvents()
