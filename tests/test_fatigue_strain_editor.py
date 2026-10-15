"""Qt checks for the dedicated views. Skip is NOT Windows acceptance."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import pytest
pytest.importorskip('PySide6',reason='Qt NOT_RUN: PySide6 unavailable; do not install a new dependency for this delivery')
from PySide6.QtWidgets import QApplication,QDialog
from apps.research.fatigue_strain_dialog import StrainLifeEditor
from apps.research.fatigue_strain_results import StrainFatigueResults
from caelab.fatigue_strain import default_settings,analyze
from caelab.storage import canonical_hash
from test_fatigue_strain_math import cases
from test_connected_evaluation_study import service


def test_known_method_is_a_label_instead_of_an_invalid_tuple():
    app=QApplication.instance() or QApplication([]);window=StrainLifeEditor(None,default_settings())
    try:
        assert window.method.count()==3
        assert '미완성' not in window.method.currentText()
        assert tuple(window.method.currentData())==('CP_SWT','SWT')
        assert not window.axis.isVisible()
    finally:window.close();app.processEvents()


def test_simulation_has_one_fatigue_task_and_no_empty_geometry_page(service):
    from apps.research.simulation_window import SimulationWindow
    app=QApplication.instance() or QApplication([]);wb,client=service
    doc=client.document_open(kind='simulation',draft={'backend':'damage.rainflow','settings':default_settings()})
    window=SimulationWindow(client,auto_open=False,poll_interval=0)
    try:
        window._opened(doc);window.show();app.processEvents()
        visible=[node.text(0) for node in window._nodes.values() if not node.isHidden()]
        assert visible==['피로 조건']
        assert not window.graph_tabs.isTabVisible(window.graph_tabs.indexOf(window.domain_canvas))
        assert window.edited_draft()==doc['draft']
    finally:window._allow_close=True;window.close();app.processEvents()


def test_incomplete_draft_cancel_keeps_original_and_permits_local_apply():
    app=QApplication.instance() or QApplication([]);original=default_settings()
    window=StrainLifeEditor(None,original)
    try:
        window.resize(760,600);window.show();app.processEvents()
        window.cal_fields['E'].setText('1e');window.cal_fields['reference'].setText('내 시험 자료')
        edited=window.edited()
        assert edited['calibration']['E']=='1e' and original['calibration']['E'] is None
        assert '미완성' in window.message.text()
        window.reject();app.processEvents();assert window.result()==QDialog.DialogCode.Rejected
    finally:window.close();app.processEvents()


def test_late_preview_and_cancel_cannot_replace_a_newer_draft():
    app=QApplication.instance() or QApplication([]);window=StrainLifeEditor(None,default_settings());calls=[]
    try:
        window._after=lambda value:calls.append(value);window._request_serial=window._serial
        window._edited();window._done('late',None)
        assert calls==[] and '늦은' in window.message.text()
        window.reject();window._after=lambda value:calls.append(value);window._request_serial=window._serial
        window._done('after_cancel',None);assert calls==[]
    finally:window.close();app.processEvents()


def test_retained_result_select_membership_restore_no_execution_or_mutation():
    app=QApplication.instance() or QApplication([]);result=analyze(*cases());before=canonical_hash(result)
    window=StrainFatigueResults(result,'Jview')
    try:
        window.resize(760,680);window.show();app.processEvents();assert window.plane is not None
        assert window.width()<=760 and window.height()<=700
        window._cycle_selected(0);window._row_selected(0);selected=window.selected()
        assert selected['result_sha256']==before
        assert selected['source_row'] in window.cycle['member_source_rows']
        assert window.raw_table.rowCount()==12
        assert len(window.figure.axes)==2 and len(window.figure.axes[0].lines)>=2
        restored=StrainFatigueResults(result,'Jview',selected)
        try:assert restored.selected()==selected
        finally:restored.close()
        assert canonical_hash(result)==before
    finally:window.close();app.processEvents()
