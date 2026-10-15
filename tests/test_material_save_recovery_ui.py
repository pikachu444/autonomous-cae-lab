"""Cold GUI receipt recovery over the existing HTTP/Core owner APIs."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import json
import threading
import time
import uuid
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from apps.research.material_save_recovery import checked_context


@pytest.mark.parametrize('change', ['material', 'plan', 'receipt', 'kind', 'identity_shape'])
def test_foreign_pending_save_is_rejected_without_changing_context(change):
    context = dict(material_id='Mone', selected_plan='None', plans={'None': dict(receipt_id='Rone',
        unconfirmed=True, pending_preview={'receipt_id':'Rone', 'targets':[
            {'identity':{'document_id':'Mone','kind':'material'}},
            {'identity':{'document_id':'None','kind':'numerical'}}]})})
    original = deepcopy(context)
    if change == 'material': context['material_id'] = 'Mtwo'
    elif change == 'plan': context['plans']['None']['pending_preview']['targets'][1]['identity']['document_id'] = 'Ntwo'
    elif change == 'receipt': context['plans']['None']['pending_preview']['receipt_id'] = 'Rtwo'
    elif change == 'kind': context['plans']['None']['pending_preview']['targets'][0]['identity']['kind'] = 'data'
    else: context['plans']['None']['pending_preview']['targets'][0]['identity']['document_id'] = {}
    before = deepcopy(context)
    with pytest.raises(ValueError): checked_context(context, 'Mone')
    assert context == before and original['plans']['None']['receipt_id'] == 'Rone'


def wait(app, ready):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        app.processEvents()
        if ready(): return
        time.sleep(.01)
    raise AssertionError('Related-save recovery GUI did not settle')


@pytest.mark.parametrize('panel_already_open', [False, True])
def test_related_save_context_follows_its_material_when_switching_documents(panel_already_open):
    from apps.research.material_window import MaterialWindow
    from apps.research.material_recovery import material_raw_snapshot
    from apps.research.material_save_recovery import restore_context, context_for
    from caelab.material_document import default_draft
    from caelab.numerical_document import from_material_document
    app=QApplication.instance() or QApplication([])
    def document(identifier):
        return dict(id=identifier,kind='material',title='탄성 재료',session_id='Sfixture',generation=0,
            input_revision='I'+identifier,draft=default_draft(),runs=[],diagnostics=[],dirty=False,
            can_undo=False,can_redo=False,saved_revision=None)
    a,b=document('MfixtureA'),document('MfixtureB')
    plan=dict(a,id='NfixtureA',kind='numerical',title='인장 계획',draft=from_material_document(a))
    second=dict(plan,id='NfixtureSecond',title='별도 계획')
    context=dict(material_id=a['id'],selected_plan=plan['id'],plans={plan['id']:dict(
        receipt_id='Soriginal',pending_preview=None,unconfirmed=True)})
    original=deepcopy(context);calls=[]
    class Client:
        def documents(self):calls.append('read');return {'documents':deepcopy([plan,second])}
        def data_material(self,*args):raise AssertionError('Document switching issued a save request')
    window=MaterialWindow(Client(),auto_open=False,poll_interval=0)
    try:
        window._show_document(a);window.show();restore_context(window,context)
        if panel_already_open:
            panel=window.open_plan_variables();wait(app,lambda:not panel._busy)
            assert panel._related_save_receipts=={plan['id']:'Soriginal'}
        # The existing open lifecycle performs the panel's owner rebinding.
        window._opened(b)
        if window._plan_panel is None:panel=window.open_plan_variables()
        else:panel=window._plan_panel
        wait(app,lambda:not panel._busy)
        assert not panel._related_save_receipts and not panel._widgets
        assert 'related_save' not in material_raw_snapshot(window)['selection']
        assert context_for(window,a['id'])==original and context==original
        window._opened(a);wait(app,lambda:not panel._busy)
        assert panel._related_save_receipts=={plan['id']:'Soriginal'}
        assert panel.save_receipt_button.isEnabled() and panel.plans.currentData()==plan['id']
        assert material_raw_snapshot(window)['selection']['related_save']==original
        panel.plans.setCurrentIndex(panel.plans.findData(second['id']))
        panel.refresh_plans();wait(app,lambda:not panel._busy)
        assert panel.plans.currentData()==second['id']
        assert not panel.save_receipt_button.isEnabled()
        assert window.document['draft']==a['draft'] and set(calls)=={'read'}
    finally:
        window._allow_close=True;window.close();app.processEvents()


@pytest.mark.parametrize('lost_reply', [False, True])
def test_cold_capsule_reopens_original_receipt_without_saving_again(tmp_path, monkeypatch, lost_reply):
    from apps.lab.service import LabService
    from apps.lab.server import LabHTTPServer
    from apps.research.appearance import apply_appearance
    from apps.research.material_window import MaterialWindow
    from apps.research.material_related_save import RelatedSaveDialog
    from apps.research.material_recovery import material_raw_snapshot, restore_material_raw
    from caelab.workbench_client import Client
    from caelab.numerical_document import from_material_document
    from caelab.storage import canonical_hash
    app = QApplication.instance() or QApplication([]); apply_appearance(app)
    windows=[]; dialogs=[]; failures=[]; servers=[]
    def start():
        service=LabService(tmp_path); server=LabHTTPServer(service,0)
        thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True); thread.start()
        servers.append((service,server,thread))
        return server,Client(f'http://127.0.0.1:{server.server_port}')
    def stop():
        service,server,thread=servers.pop();server.shutdown();server.server_close();service.shutdown();thread.join(2)
    def command(document,operation,args=None):
        return client.document_command(document['id'],operation,args or {},session_id=document['session_id'],
            expected_generation=document['generation'],command_id='C'+uuid.uuid4().hex)['document']
    server,client=start()
    try:
        material=command(client.document_open(kind='material',title='탄성 재료'),'document.save')
        plan=command(client.document_open(kind='numerical',title='인장 계획',draft=from_material_document(material)),'document.save')
        old_reference=deepcopy(plan['draft']['material'])
        draft=deepcopy(material['draft']);draft['settings']['parameters']['E']=1250.
        material=command(material,'material.update',{'draft':draft})
        draft=deepcopy(plan['draft']);draft['variables'][0]['value']=1200.
        plan=command(plan,'numerical.update',{'draft':draft})
        window=MaterialWindow(client,auto_open=False,poll_interval=0);windows.append(window)
        window._show_document(material);window.show();panel=window.open_plan_variables()
        wait(app,lambda:not panel._busy and bool(panel._widgets))
        original_save=server.workbench.numerical_documents._save
        failed=[]
        def fail_once(document):
            if not lost_reply and not failed:
                failed.append(True);raise PermissionError('Injected Plan storage failure')
            return original_save(document)
        monkeypatch.setattr(server.workbench.numerical_documents,'_save',fail_once)
        transport=client.data_material;operations=[]
        def send(operation,args):
            operations.append(operation);result=transport(operation,args)
            if operation=='related_save.execute' and lost_reply: raise OSError('Injected committed reply loss')
            return result
        monkeypatch.setattr(client,'data_material',send)
        def act():
            dialog=next((d for d in app.topLevelWidgets() if isinstance(d,RelatedSaveDialog) and d.isVisible()),None)
            if dialog is None:QTimer.singleShot(10,act);return
            def ready():
                if dialog._busy or dialog.preview is None:QTimer.singleShot(10,ready);return
                try:
                    dialog.save()
                    def close():
                        if dialog._busy:QTimer.singleShot(10,close);return
                        dialog.reject()
                    close()
                except BaseException as error:failures.append(error);dialog.reject()
            ready()
        QTimer.singleShot(10,act);assert panel.save_related();assert not failures
        identifier=plan['id'];receipt_id=panel._related_save_receipts[identifier]
        assert operations.count('related_save.preview')==1 and operations.count('related_save.execute')==1
        # Refresh saved metadata through the existing read path before Keep. An
        # old saved_revision is never silently assigned to a newer owner gate.
        window._show_document(client.document_read(material['id']),preserve_history=True)
        wait(app,lambda:not panel._busy)
        raw=material_raw_snapshot(window)
        assert raw['selection']['related_save']['plans'][identifier]['receipt_id']==receipt_id
        if lost_reply:assert raw['selection']['related_save']['plans'][identifier]['unconfirmed']
        identity=transport('recovery.identity',{'document_id':material['id']})
        request={'identity':identity,'raw':raw}
        prepared=transport('recovery.prepare',{'requests':[request]})
        outcome=transport('recovery.execute',{'preview':prepared})
        assert outcome['all_kept'] and outcome['close_permitted']
        capsule_id=outcome['targets'][0]['capsule_id']
        window._allow_close=True;window.close();stop()
        server,client=start();transport=client.data_material
        current=client.document_read(material['id']);identity=transport('recovery.identity',{'document_id':material['id']})
        recovered=transport('recovery.recover',{'document_id':material['id'],'capsule_id':capsule_id,
            'identity':identity,'acknowledge_session_change':True})
        assert recovered['state']=='RESUME_READY'
        fresh=MaterialWindow(client,auto_open=False,poll_interval=0);windows.append(fresh)
        fresh._show_document(current);fresh.show();restore_material_raw(fresh,recovered['raw'])
        assert fresh._plan_panel is None  # Recovery makes no Plan read or save.
        panel=fresh.open_plan_variables();wait(app,lambda:not panel._busy and bool(panel._widgets))
        assert panel.plans.currentData()==identifier and panel.save_receipt_button.isEnabled()
        assert panel._related_save_receipts[identifier]==receipt_id
        before=client.document_read(identifier);calls=[]
        unread=[]
        def recorded(operation,args):
            calls.append(operation);result=transport(operation,args)
            if lost_reply and operation=='related_save.receipt' and not unread:
                unread.append(True);raise OSError('Injected original receipt read reply loss')
            return result
        monkeypatch.setattr(client,'data_material',recorded)
        dialog=RelatedSaveDialog(client,current,before,receipt_id=receipt_id,
            pending_preview=panel._related_save_pending.get(identifier));dialogs.append(dialog);dialog.show()
        wait(app,lambda:not dialog._busy and (bool(unread) if lost_reply else dialog.receipt is not None))
        assert calls==['related_save.receipt']
        if lost_reply:
            assert dialog.receipt is None and dialog.resume_button.isVisible() and dialog.resume_button.isEnabled()
            assert dialog.resume_original()
            wait(app,lambda:dialog.receipt is not None and not dialog._busy)
            assert calls==['related_save.receipt','related_save.execute']
        assert dialog.receipt['receipt_id']==receipt_id
        assert not dialog.save_button.isEnabled() and not dialog.resume_button.isVisible()
        assert len(dialog.receipt['targets'][0]['attempts'])==1
        directory = os.environ.get('CAELAB_SAVE_RECOVERY_RENDERS')
        if directory:
            from pathlib import Path
            folder=Path(directory);folder.mkdir(parents=True,exist_ok=True)
            for label,size in [('normal',(820,390)),('narrow',(640,390))]:
                dialog.resize(*size);app.processEvents()
                name=('lost-reply' if lost_reply else 'partial')+'-'+label+'.png'
                assert dialog.grab().save(str(folder/name))
        if not lost_reply:
            assert dialog.receipt['targets'][1]['state']=='FAILED'
            assert before['draft']['material']==old_reference
            dialog.table.selectRow(1);assert dialog.retry_button.isEnabled()
            dialog.retry_selected();wait(app,lambda:dialog.receipt['all_saved'] and not dialog._busy)
            assert len(dialog.receipt['targets'][0]['attempts'])==1
            assert len(dialog.receipt['targets'][1]['attempts'])==2
        else:assert dialog.receipt['all_saved'] and len(dialog.receipt['targets'][1]['attempts'])==1
        assert client.document_read(identifier)['draft']['material']==old_reference
        # Existing fresh-CAS publication remains an explicit separate action.
        if lost_reply:
            assert dialog.publish()
            wait(app,lambda:not dialog._busy)
            assert dialog.receipt['publication']['state']=='PUBLISHED',dialog.message.text()
        assert not server.workbench.manager.list()
        assert canonical_hash(json.loads(json.dumps(raw)))==canonical_hash(raw)
    finally:
        for dialog in dialogs:dialog.close()
        for window in windows:window._allow_close=True;window.close()
        app.processEvents()
        while servers:stop()
