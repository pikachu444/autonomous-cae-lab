"""Lost save acknowledgement plus pending cells must reach the original Keep gate."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import threading
import time
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QLineEdit,QMessageBox


def test_lost_save_reply_inspection_keeps_both_pending_owners_for_cold_read(tmp_path,monkeypatch):
    from apps.lab.service import LabService
    from apps.lab.server import LabHTTPServer
    from apps.research.material_window import MaterialWindow
    from apps.research.material_related_save import RelatedSaveDialog
    from apps.research.data_material_recovery_dialog import RecoveryKeepDialog
    from apps.research.material_recovery import material_raw_snapshot
    from apps.research.appearance import apply_appearance
    from caelab.workbench_client import Client
    from caelab.numerical_document import from_material_document
    app=QApplication.instance() or QApplication([]);apply_appearance(app)
    servers=[];windows=[];errors=[]
    def start():
        service=LabService(tmp_path);server=LabHTTPServer(service,0)
        thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
        servers.append((service,server,thread))
        return server,Client(f'http://127.0.0.1:{server.server_port}')
    def stop():
        service,server,thread=servers.pop();server.shutdown();server.server_close();service.shutdown();thread.join(2)
    def wait(ready):
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            app.processEvents()
            if errors:raise errors[0]
            if ready():return
            time.sleep(.01)
        raise AssertionError('Pending-cell saved-metadata recovery did not settle')
    def later(kind,action):
        def find():
            dialog=next((d for d in app.topLevelWidgets() if isinstance(d,kind) and d.isVisible()),None)
            if dialog is None:QTimer.singleShot(10,find);return
            try:action(dialog)
            except BaseException as error:errors.append(error);dialog.reject()
        QTimer.singleShot(10,find)
    server,client=start()
    try:
        material=client.document_open(kind='material',title='탄성 재료')
        plan=client.document_open(kind='numerical',title='인장 계획',draft=from_material_document(material))
        drafts={d['id']:deepcopy(d['draft']) for d in (material,plan)}
        window=MaterialWindow(client,auto_open=False,poll_interval=0);windows.append(window)
        window._show_document(material);window.show();panel=window.open_plan_variables()
        wait(lambda:not panel._busy and bool(panel._widgets))
        widget=panel._widgets[plan['id']]
        assert callable(getattr(widget,'refresh_saved_metadata',None))
        original=client.data_material;calls=[]
        def lost(operation,args):
            calls.append(operation);result=original(operation,args)
            if operation=='related_save.execute':raise OSError('Injected committed save reply loss')
            return result
        monkeypatch.setattr(client,'data_material',lost)
        def save(dialog):
            wait(lambda:not dialog._busy and dialog.preview is not None)
            dialog.save();wait(lambda:not dialog._busy);assert dialog.receipt is None;dialog.reject()
        later(RelatedSaveDialog,save);assert panel.save_related()
        receipt_id=panel._related_save_receipts[plan['id']]
        widget.table.item(0,2).setText('2e')
        item=window.coefficients.item(0,1);window.coefficients.setCurrentItem(item);window.coefficients.editItem(item);app.processEvents()
        line=next(e for e in window.coefficients.findChildren(QLineEdit) if e.isVisible())
        line.setText('1e3');line.setSelection(2,-2)
        plan_raw=widget.recovery_snapshot();material_raw=material_raw_snapshot(window)
        later(QMessageBox,lambda dialog:next(b for b in dialog.buttons() if b.text()=='저장').click())
        window.close();app.processEvents()
        assert window.isVisible() and '저장 결과를 먼저 확인' in window.message.text()
        assert line.text()=='1e3' and line.selectedText()=='1e'
        def capture(prefix):
            directory=os.environ.get('CAELAB_SAVED_METADATA_RENDERS')
            if directory:
                from pathlib import Path
                folder=Path(directory);folder.mkdir(parents=True,exist_ok=True)
                for name,size in [('normal',(1440,980)),('narrow',(900,820))]:
                    window.resize(*size);app.processEvents()
                    assert window.grab().save(str(folder/(prefix+'-'+name+'.png')))
        capture('pending-before')
        def read(dialog):
            wait(lambda:not dialog._busy and dialog.receipt is not None)
            assert not dialog.allow_writes;dialog.reject()
        later(RelatedSaveDialog,read);assert panel.save_related(receipt_id=receipt_id)
        assert line.text()=='1e3' and line.selectedText()=='1e' and line.cursorPosition()==0
        assert widget.recovery_snapshot()==plan_raw
        assert material_raw_snapshot(window)['cells']==material_raw['cells']
        assert window.document['saved_revision'] and widget.document_snapshot()['saved_revision']
        assert '저장 결과를 읽었습니다' in window.message.text()
        capture('pending-saved')
        assert calls==['related_save.preview','related_save.execute','related_save.receipt']
        later(QMessageBox,lambda dialog:next(b for b in dialog.buttons() if b.text()=='편집 원문 보관').click())
        def keep(dialog):
            wait(lambda:dialog.keep_button.isEnabled() or dialog.preview is not None and any(t.get('problems') for t in dialog.preview['targets']))
            assert dialog.keep_button.isEnabled(),dialog.message.text()
            dialog.keep()
        later(RecoveryKeepDialog,keep);window.close();wait(lambda:not window.isVisible())
        capsules={d['id']:original('recovery.read',{'document_id':d['id']})['capsules'][-1]['capsule'] for d in (material,plan)}
        assert any(c['raw_text']=='1e3' and c['editor_kind']=='unfinished' for c in capsules[material['id']]['raw']['cells'])
        assert capsules[material['id']]['raw']['focus']==material_raw['focus']
        assert any(c['raw_text']=='2e' for c in capsules[plan['id']]['raw']['cells'])
        assert all(client.document_read(d['id'])['draft']==drafts[d['id']] for d in (material,plan))
        stop();server,client=start()
        for d in (material,plan):
            retained=client.data_material('recovery.read',{'document_id':d['id']})['capsules'][-1]['capsule']
            assert retained['capsule_sha256']==capsules[d['id']]['capsule_sha256']
            assert retained['raw']==capsules[d['id']]['raw']
        receipt=client.data_material('related_save.receipt',{'receipt_id':receipt_id})
        assert receipt['all_saved'] and all(len(t['attempts'])==1 for t in receipt['targets'])
        assert not server.workbench.manager.list()
    finally:
        for window in windows:window._allow_close=True;window.close()
        app.processEvents()
        while servers:stop()
