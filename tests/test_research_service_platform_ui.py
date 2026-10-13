"""Real HTTP/Qt host metadata; no native solver or build approval."""
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QThreadPool
from test_research003_ui import app
from test_connected_evaluation_study import service,change,wait
from caelab.adapters import native_doctor as doctor


@pytest.mark.parametrize('kind,backend',[('pde','pde.fenicsx.dimensioned'),('material','material.mfront.user')])
def test_native_edit_save_and_results_controls_remain_available_on_windows_service(service,app,monkeypatch,kind,backend):
    from apps.research.pde_window import PDEWindow
    from apps.research.native_material_window import NativeMaterialWindow
    from caelab.pde_document import default_draft as pde_draft
    from caelab.simulation_document import default_draft as material_draft
    monkeypatch.setattr(doctor,'service_platform',lambda:'win32')
    wb,client=service;draft=(pde_draft if kind=='pde' else material_draft)(backend)
    doc=client.document_open(kind=kind,draft=draft)
    window=(PDEWindow if kind=='pde' else NativeMaterialWindow)(client,document_id=doc['id'],poll_interval=0)
    window.resize(1100,780);window.show()
    try:
        wait(lambda:window.document and not window._busy,app)
        original=deepcopy(window.edited_draft())
        assert not window.evaluate_button.isEnabled()
        assert window.save_action.isEnabled() and window.plan_action.isEnabled()
        assert 'Linux' in window.execution_hint.text() and window.evaluate() is False
        assert len(wb.manager.list())==0 and window.edited_draft()==original
        window.save_document();wait(lambda:not window._busy,app)
        reopened=client.document_open(kind=kind,document_id=doc['id'])
        assert reopened['draft']==original and len(wb.manager.list())==0
        # Same client, same document/store, explicit service-host metadata:
        # Linux means only platform support, never tested native installation.
        monkeypatch.setattr(doctor,'service_platform',lambda:'linux')
        window.refresh_document();wait(lambda:not window._busy,app)
        assert window.document['service_platform']=='linux' and window.evaluate_button.isEnabled()
        assert window.edited_draft()==original and len(wb.manager.list())==0
        legacy=deepcopy(window.document);legacy.pop('service_platform')
        window._show_document(legacy);window._update_actions()
        assert window.evaluate_button.isEnabled() and '확인 필요' in window.execution_hint.text()
        assert window.size().width()==1100 and window.size().height()==780
    finally:
        window._allow_close=True;window.close()
        QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
