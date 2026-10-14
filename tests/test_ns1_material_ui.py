"""Actual offscreen Qt rendering/events with explicit native-object doubles."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from copy import deepcopy
import pytest
W=pytest.importorskip('PySide6.QtWidgets')
C=pytest.importorskip('PySide6.QtCore')
G=pytest.importorskip('PySide6.QtGui')
T=pytest.importorskip('PySide6.QtTest')
from test_pre_fem_panel_ui import panel, native, app
from test_ns1_native_edit import nonlinear_factory, draft
from apps.desktop_pre import nonlinear_material as nm
from caelab.calculix_material import J2


def edit(page, app, points='250\t0\n270\t1.234567891234567e-5\n300\t.02'):
    page.law.setCurrentIndex(page.law.findData(J2)); page.confirm.setChecked(True)
    app.clipboard().setText(points)
    page.table.setFocus()
    T.QTest.keyClick(page.table,C.Qt.Key.Key_V,C.Qt.KeyboardModifier.ControlModifier)
    app.processEvents()


def test_literal_paste_late_receipt_error_row_and_native_apply(panel,native,nonlinear_factory,app):
    page=panel.material_page
    panel.tabs.setCurrentWidget(page); panel.resize(900,850); panel.show(); app.processEvents()
    edit(page,app)
    assert page.current_draft()['plasticity']['yield_points'][1][1]=='1.234567891234567e-5'
    assert page.apply_button.isEnabled() and page.modified
    page.send(True)
    page.table.item(2,0).setText('310')
    panel.test_complete()
    assert page.modified and page.table.item(2,0).text()=='310'
    assert nm.read(native.editor,native.material,native.analysis.Name)['draft']['plasticity']['yield_points'][2][0]=='300'
    page.send(True); panel.test_complete()
    assert not page.modified
    page.table.item(1,1).setText('1e')
    assert not page.apply_button.isEnabled()
    panel.poll(); assert not page.apply_button.isEnabled()  # Poll must not re-enable invalid Apply.
    page.error_button.click()
    assert (page.table.currentRow(),page.table.currentColumn())==(1,1)
    assert page.table.verticalHeaderItem(1).text()=='2 !'
    page.send(False); panel.test_complete()
    assert not page.modified and not page.apply_button.isEnabled()
    page.discard(); assert page.table.item(1,1).text()=='1e'


def test_201_point_draft_roundtrip_stays_editable_and_cannot_apply(panel,native,app):
    page=panel.material_page; panel.tabs.setCurrentWidget(page)
    value=draft(201)
    nm.save(native.editor,native.material,native.analysis.Name,value)
    page.discard()
    assert page.table.rowCount()==201 and not page.apply_button.isEnabled()
    assert page.table.verticalHeaderItem(200).text()=='201 !'
    page.error_button.click(); assert page.table.currentRow()==200
    page.send(False); panel.test_complete(); page.discard()
    assert page.table.rowCount()==201 and page.current_draft()['plasticity']['yield_points']==value['plasticity']['yield_points']
    page.table.clearSelection(); page.table.selectRow(200); page.remove_rows()
    assert page.table.rowCount()==200 and page.apply_button.isEnabled()
    page.sync_actions(True); page.update_state(); assert not page.apply_button.isEnabled()
    page.sync_actions(False); assert page.apply_button.isEnabled()


def test_geometry_late_edit_and_elastic_edit_are_pending_until_explicit_apply(panel,native,app):
    page=panel.material_page
    page.nlgeom.setChecked(True)
    assert page.geometry_pending() and '미적용' in page.strain_meaning.text()
    page.apply_geometry(); page.nlgeom.setChecked(False); panel.test_complete()
    assert native.solver.GeometricalNonlinearity=='nonlinear' and page.geometry_pending()
    page.apply_geometry(); panel.test_complete(); assert not page.geometry_pending()
    panel.modulus.setValue(1234.5); assert page.elastic_pending() and page.pending_changes()
    panel.refresh(); assert panel.modulus.value()==1234.5
    panel.apply_material(); panel.test_complete(); assert not page.elastic_pending()


def test_extra_native_column_is_not_discarded_by_open_and_save(panel,native,app):
    value=draft(); value['plasticity']['yield_points'][1].append('293.15')
    nm.save(native.editor,native.material,native.analysis.Name,value)
    page=panel.material_page; page.discard()
    assert not page.apply_button.isEnabled()
    page.send(False); panel.test_complete()
    assert nm.read(native.editor,native.material,native.analysis.Name)['draft']==value
    page.table.item(1,0).setText('275')  # Explicitly editing this row replaces its unsupported shape.
    assert len(page.current_draft()['plasticity']['yield_points'][1])==2


@pytest.mark.parametrize('width',[480,1100])
def test_real_render_korean_narrow_width_and_keyboard_focus(panel,native,app,width):
    page=panel.material_page; panel.tabs.setCurrentWidget(page)
    panel.resize(width,900); panel.show(); app.processEvents(); edit(page,app)
    assert panel.width()==width and page.plot.width()>=190
    assert page.table.width()>=175 and page.apply_button.isVisible()
    assert page.apply_button.geometry().right()<=page.width()
    page.table.setCurrentCell(1,1); page.table.setFocus()
    T.QTest.keyClick(page.table,C.Qt.Key.Key_Tab)
    app.processEvents()
    assert page.table.currentRow()==2
    target=os.environ.get('NS1_RENDER_DIR')
    if target:
        folder=Path(target); folder.mkdir(parents=True,exist_ok=True)
        assert panel.grab().save(str(folder/f'ns1-material-{width}.png'))


def test_narrow_numeric_display_keeps_exponent_and_does_not_round_source(panel,app):
    page=panel.material_page; edit(page,app)
    index=page.table.model().index(1,1)
    option=W.QStyleOptionViewItem()
    option.rect=C.QRect(0,0,92,26)
    page.table.itemDelegate().initStyleOption(option,index)
    assert 'e-05' in option.text
    assert float(option.text)==pytest.approx(1.234567891234567e-5,rel=.001)
    assert page.table.item(1,1).text()=='1.234567891234567e-5'
