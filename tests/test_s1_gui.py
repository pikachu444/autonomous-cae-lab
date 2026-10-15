"""Actual Qt rendering when installed; controlled numerical fields, not FE proof."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import time
import pytest
pytest.importorskip('PySide6',reason='NOT_RUN: PySide6 unavailable; no fabricated UI screenshots')
pytest.importorskip('matplotlib')
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog
from apps.research.evaluation_window import EvaluationWindow
from apps.research.temperature_mapping_dialog import TemperatureMappingDialog, configure
from apps.research.transfer_inspection_window import TransferInspectionWindow
from apps.research.appearance import apply_appearance
from test_s1_owner_transfer import service,controlled,sources,run


def settled(app,predicate,seconds=8):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise AssertionError('Owned Qt request did not settle')


def test_real_mapping_dialog_and_receiver_source_render(service,controlled,tmp_path):
    wb,client=service;_,draft=sources(client);doc,job,result=run(client,draft)
    app=QApplication.instance() or QApplication([])
    apply_appearance(app)
    catalog=client.evaluation_inspect(doc['id'])
    editor=TemperatureMappingDialog(draft['transfers'][0],draft['stages'],{s['id']:s for s in catalog['stages']})
    viewer=TransferInspectionWindow(client,doc['id'],job,'TtoU',0)
    before=list(controlled['calls'])
    try:
        editor.show();viewer.show()
        settled(app,lambda:getattr(viewer,'_data',{}).get('mapping_kind')=='p1_temperature')
        assert editor.options()==draft['transfers'][0]['options']
        for name,w,h in [('normal',1100,780),('narrow',680,640)]:
            viewer.resize(w,h);editor.resize(max(560,w-240),max(440,h-100));app.processEvents()
            assert viewer.grab().save(str(tmp_path/('s1-transfer-'+name+'.png')))
            assert editor.grab().save(str(tmp_path/('s1-editor-'+name+'.png')))
        view=viewer.mapped_view
        assert view.table.rowCount()==12
        origin=draft['transfers'][0]['options']['time']['receiver']['origin']
        assert origin not in view.details.text() and origin in view.details.toolTip()
        assert all(origin not in view.selector.itemText(i) for i in range(view.selector.count()))
        assert view.table.item(1,1).text()=='0.33333333, 0'
        assert view.table.item(0,6).text()=='2개 시점'
        assert '가중치' in view.table.item(0,6).toolTip()
        view.selector.setCurrentIndex(1);app.processEvents();assert view.table.rowCount()==6
        view.selector.setCurrentIndex(2);app.processEvents();assert view.table.rowCount()==15
        viewer._retry()
        assert view.data is None and view.table.rowCount()==0
        settled(app,lambda:view.data is not None)
        assert view.selector.currentData()==('source',1) and view.table.rowCount()==15
        retained=deepcopy(view.data)
        view.clear(keep_selection=True)
        assert view.data is None and view.table.rowCount()==0
        assert view.selector.currentData()==('source',1)
        view.set_data(retained);app.processEvents()
        assert view.selector.currentData()==('source',1) and view.table.rowCount()==15
        view.clear()
        assert view.selector.currentIndex()==-1 and view.table.rowCount()==0
        view.set_data(retained);app.processEvents()
        assert view.selector.currentData()==('receiver',None)
        assert controlled['calls']==before
        editor.instant.setText('1e');editor._accept();assert editor.error.text()
        assert editor.isVisible()  # Invalid draft stays in the editor for repair.
        editor.instant.setText('1');assert editor.options()==draft['transfers'][0]['options']
    finally:
        editor.close();viewer.close();app.processEvents()


def test_modal_cancel_preserves_pending_text_and_solver_calls_zero(service,controlled):
    wb,client=service;_,draft=sources(client)
    doc=client.document_open(kind='evaluation',draft=draft)
    app=QApplication.instance() or QApplication([])
    apply_appearance(app)
    window=EvaluationWindow(client,auto_open=False,poll_interval=0)
    window._show_document(doc)
    window._inspection=client.evaluation_inspect(doc['id'])
    from caelab.storage import canonical_hash
    window._catalog_sources={s['id']:canonical_hash(s['source']) for s in draft['stages']}
    edited=deepcopy(draft);edited['stages'][0]['name']='미적용 공급 이름'
    window._replace_draft(edited);before=window.edited_draft()
    def cancel():
        dialog=window.findChild(TemperatureMappingDialog)
        assert dialog is not None and window.local_dirty
        dialog.reject()
    try:
        QTimer.singleShot(20,cancel)
        assert configure(window,edited['transfers'][0]) is None
        assert window.edited_draft()==before and window.local_dirty
        assert not controlled['calls'] and not wb.manager.list()
    finally:
        window._allow_close=True;window.close();app.processEvents()


def test_method_captions_preserve_exact_backend_and_invalid_draft_without_run(service,controlled):
    from apps.research.pde_window import PDEWindow,setting_label
    from apps.research.simulation_window import SimulationWindow, MODELS
    from caelab import scikit_fem_models as domain
    wb,client=service
    app=QApplication.instance() or QApplication([])
    apply_appearance(app)
    for kind,cls,backend,alternative in [
        ('pde',PDEWindow,domain.WEAK,'pde.scipy.ode'),
        ('simulation',SimulationWindow,domain.THERMAL,domain.STRUCTURAL),
    ]:
        doc=client.document_open(kind=kind,draft={'backend':backend,'settings':domain.default_settings(backend)})
        window=cls(client,auto_open=False,poll_interval=0)
        try:
            window._show_document(doc)
            original=deepcopy(window.edited_draft())
            assert window.backend.currentData()==backend
            caption=window.backend.lineEdit().text()
            assert backend not in caption
            assert caption==(MODELS[backend][0] if kind=='simulation' else '선형 약형식 (scikit-fem)')
            if kind=='pde':
                assert setting_label(('settings','space','family'))=='함수 공간 계열'
                assert setting_label(('settings','mesh','levels'))=='메시 수준'
                assert window.domain_axes.get_title()=='모델 영역'
            window.backend.setCurrentIndex(window.backend.findData(alternative))
            assert window.edited_draft()==dict(original,backend=alternative)
            window.backend.setEditText('unsupported.future.method')
            assert window.edited_draft()==dict(original,backend='unsupported.future.method')
            assert not window.evaluate_button.isEnabled()
            window.save_document()
            settled(app,lambda:not window._busy)
            saved=client.document_read(doc['id'])
            assert saved['draft']==dict(original,backend='unsupported.future.method')
            window._show_document(saved)
            assert window.edited_draft()==saved['draft']
            assert 'unsupported.future.method' not in window.backend.lineEdit().text()
            malformed=deepcopy(saved);malformed['draft']['backend']=[]
            window._show_document(malformed)
            assert window.edited_draft()['backend']==[]
            window._show_document(doc)
            assert window.edited_draft()==original and window.backend.currentData()==backend
            assert window.backend.lineEdit().text()==caption
            assert not controlled['calls'] and not wb.manager.list()
        finally:
            window._allow_close=True;window.close();app.processEvents()


def test_initial_transfer_iteration_tuple_selects_second_catalog_entry(service,controlled,monkeypatch):
    wb,client=service;_,draft=sources(client);doc,job,result=run(client,draft)
    app=QApplication.instance() or QApplication([])
    apply_appearance(app)
    original=client.evaluation_transfer
    selected=[]
    def read(*args,**kwargs):
        payload=original(*args,**kwargs)
        if len(args)==2:
            payload=deepcopy(payload)
            earlier=deepcopy(payload['transfers'][0]);earlier['iteration']=1
            payload['transfers'].insert(0,earlier)
        else:
            selected.append(args[2:])
        return payload
    monkeypatch.setattr(client,'evaluation_transfer',read)
    before=list(controlled['calls'])
    viewer=TransferInspectionWindow(client,doc['id'],job,'TtoU',0)
    try:
        viewer.show()
        settled(app,lambda:getattr(viewer,'_data',{}).get('mapping_kind')=='p1_temperature')
        assert viewer.selector.currentIndex()==1
        assert viewer.selector.currentData()==('TtoU',0)
        assert selected==[('TtoU',0)] and controlled['calls']==before
    finally:
        viewer.close();app.processEvents()
