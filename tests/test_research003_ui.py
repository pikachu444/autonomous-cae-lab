"""Qt command/read paths; no native solver. Actual SciPy/FELUPE only where selected."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThreadPool
from test_connected_evaluation_study import service,controlled,sources,change,wait
from caelab.jobs import TERMINAL


@pytest.fixture
def app():
    app=QApplication.instance() or QApplication([])
    yield app
    # Queued receivers run before service fixture releases its HTTP server.
    QThreadPool.globalInstance().waitForDone(5000);app.processEvents()


def test_ode_expression_draft_actual_result_and_small_window(service,app):
    from apps.research.pde_window import PDEWindow
    from caelab.pde_document import default_draft
    client=service[1]
    doc=client.document_open(kind='pde',draft=default_draft('pde.scipy.ode'))
    window=PDEWindow(client,document_id=doc['id'],poll_interval=0);window.resize(1100,780);window.show()
    try:
        wait(lambda:window.document and not window._busy,app)
        window.tree.setCurrentItem(window._nodes[('settings','states')]);app.processEvents()
        field=window.fields[('settings','states',0,'rhs')][0]
        field.setPlainText('temperature + rate');window.validate_inputs()
        wait(lambda:not window._busy,app)
        assert window.local_dirty and window._input_checks
        assert window.edited_draft()['settings']['states'][0]['rhs']=='temperature + rate'
        assert len(service[0].manager.list())==0
        window.fields[('settings','states',0,'rhs')][0].setPlainText('-rate*(temperature-ambient)')
        window.apply_inputs();wait(lambda:not window._busy,app)
        window.evaluate();wait(lambda:not window._busy and window.document['runs'],app)
        job=window.document['runs'][-1]['job_id'];wait(lambda:client.status(job)['state'] in TERMINAL,app)
        window._selected_job=job;window._result_key=None;window.refresh_result()
        wait(lambda:window._result and not window._busy,app)
        assert window._result['responses']['temperature']['unit']=='K'
        assert window.size().width()==1100 and window.size().height()==780
        assert window.result_canvas.width()>350 and window.result_canvas.height()>230
    finally:
        window._allow_close=True;window.close();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()


def test_transfer_actual_bound_rows_and_plot_selection(service,controlled,app):
    from apps.research.transfer_inspection_window import TransferInspectionWindow
    wb,client=service;controlled['fail_structure']=False
    _,draft=sources(client);doc=client.document_open(kind='evaluation',draft=draft)
    job=change(client,doc,'evaluation.run')['job']['id'];wait(lambda:client.status(job)['state'] in TERMINAL,app)
    window=TransferInspectionWindow(client,doc['id'],job);window.show()
    try:
        wait(lambda:len(window._rows)==4,app)
        window.table.selectRow(2);app.processEvents()
        assert window._rows[2]['supplied']==window._rows[2]['received']==320.
        assert window.canvas.height()>240 and window.table.rowCount()==4
        assert '완료' in window.status.text()
        count=len(wb.manager.list());window._page(0)
        wait(lambda:len(window._rows)==4,app);assert len(wb.manager.list())==count
    finally:
        window.close();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()


def test_native_material_source_editor_contract_without_simulation_changes(service,app):
    from apps.research.native_material_window import NativeMaterialWindow
    from caelab.user_material import default_settings
    client=service[1];draft={'backend':'material.mfront.user','settings':default_settings()}
    doc=client.document_open(kind='material',draft=draft)
    window=NativeMaterialWindow(client,document_id=doc['id'],poll_interval=0);window.show()
    try:
        wait(lambda:window.document and not window._busy,app)
        assert window.new_action.text()=='새 구성식…'
        assert window.evaluate_button.text()=='빌드만 실행'
        window.tree.setCurrentItem(window._nodes[('settings','source')]);app.processEvents()
        assert ('settings','source') not in window.fields # source editor is separate, not a giant inline field
        assert window.edited_draft()==draft and not service[0].manager.list()
    finally:
        window._allow_close=True;window.close();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()



def test_user_source_review_cancel_then_local_permission_no_build(service,app,tmp_path,monkeypatch):
    from apps.research.material_build_dialog import MaterialBuildDialog
    from caelab import material_build_permission as permission,user_material as domain
    monkeypatch.setattr(permission,'directory',lambda:tmp_path/'operator')
    wb,client=service;settings=domain.default_settings()
    context=client.request('/api/workbench/material-build-context')
    dialog=MaterialBuildDialog(client,context,settings)
    dialog.show();app.processEvents()
    assert dialog.source.toPlainText()==settings['source']
    assert dialog.confirm.isEnabled()
    dialog.reject()
    assert not permission.is_admitted(settings['source'],settings['behaviour'])
    reopened=MaterialBuildDialog(client,context,settings)
    reopened.approve()
    assert reopened.approved and permission.is_admitted(settings['source'],settings['behaviour'])
    assert not wb.manager.list() # permission is not a hidden build/evaluation
    changed=dict(settings,source=settings['source']+'\n')
    assert not permission.is_admitted(changed['source'],changed['behaviour'])



@pytest.mark.parametrize('accept',[False,True])
def test_source_modal_preserves_other_window_property_and_exact_generation(service,app,monkeypatch,accept):
    from PySide6.QtWidgets import QDialog,QPlainTextEdit
    from apps.research.native_material_window import NativeMaterialWindow
    from caelab.user_material import default_settings
    from copy import deepcopy
    client=service[1];draft={'backend':'material.mfront.user','settings':default_settings()}
    doc=client.document_open(kind='material',draft=draft)
    window=NativeMaterialWindow(client,document_id=doc['id'],poll_interval=0);window.show()
    try:
        wait(lambda:window.document and not window._busy,app)
        def edit(dialog):
            fresh=client.document_read(doc['id']);changed=deepcopy(fresh['draft'])
            changed['settings']['properties'][0]['value']=2e9
            updated=change(client,fresh,'material.update',{'draft':changed})['document']
            # A queued document read may finish inside the nested modal loop.
            window._show_document(updated)
            dialog.findChild(QPlainTextEdit).setPlainText(draft['settings']['source']+'\n// reviewed version\n')
            return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected
        monkeypatch.setattr(QDialog,'exec',edit)
        window.edit_law_source()
        assert window.edited_draft()['settings']['properties'][0]['value']==2e9
        if accept:
            assert window.local_dirty and window.edited_draft()['settings']['source'].endswith('// reviewed version\n')
            window.apply_inputs();wait(lambda:not window._busy,app)
        else:
            assert window.edited_draft()['settings']['source']==draft['settings']['source']
            assert not window.local_dirty
        current=client.document_read(doc['id'])
        assert current['draft']['settings']['properties'][0]['value']==2e9
        assert not service[0].manager.list()
    finally:
        window._allow_close=True;window.close();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
