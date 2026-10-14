"""Qt interaction with scene and quality doubles; no native mesh calculation."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
from PySide6 import QtCore as C, QtWidgets as W, QtTest as T

from test_pre_mesh_element_view import native
from apps.desktop_pre.mesh_element_panel import make_dialog


@pytest.fixture
def app(): return W.QApplication.instance() or W.QApplication([])


@pytest.fixture
def dialog(native,app):
    n=native; n.owner.refresh=lambda:None
    n.owner.mesh_bindings=type('Binding',(),{'validate':lambda _,mesh:{'binding_validation':'CURRENT_SOURCE_AND_MESH_MATCH'}})()
    quality={'mesh_id':'Mesh','mesh_sha256':'a'*64,'total_elements':2,'bad_element_count':1,
             'rows':[{'element_id':477,'element_type':'C3D10','minimum_sampled_jacobian_mm3':8.,
                      'minimum_scaled_sampled_jacobian':.1,'errors':[]},
                     {'element_id':479,'element_type':'C3D10','minimum_sampled_jacobian_mm3':-1.,
                      'minimum_scaled_sampled_jacobian':-.05,'errors':['JACOBIAN_AT_OR_BELOW_1E_10_MM3']}]}
    calls=[]
    def dispatch(request):
        assert request['operation']=='pre.fem.mesh_quality'
        assert request['target']=={'object_id':'Mesh'}
        assert request['expected_generation']==n.owner.generation
        calls.append(deepcopy(request)); return {'status':'COMPLETED','result':deepcopy(quality)}
    n.owner.dispatch=dispatch
    d=make_dialog(W,C,n.owner,n.mesh)
    d.show(); app.processEvents()
    yield d,n,calls
    d.close(); app.processEvents()


def test_normal_bad_keyboard_model_link_isolate_fit_and_reset(dialog,app):
    d,n,calls=dialog
    assert 'Jacobian 기준 미달' in d.table.item(1,4).text()
    assert not any(button.isEnabled() for button in d.view_buttons)
    d.table.selectRow(0); d.table.setFocus()
    T.QTest.keyClick(d.table,C.Qt.Key_Down)
    assert d._selected==[479]
    assert n.selection.rows[0].SubElementNames==['Elem479F1']
    d.poll(); assert d._selected==[479]  # Background polling must not clear the row selection.
    d.display('fit')
    assert d.view.element_ids==[479] and n.view.fit_calls
    assert n.mode.whichChild.getValue()==-1
    d.restore()
    assert n.mode.whichChild.getValue()==3 and not d.view.active
    assert [(r.Object.Name,r.SubElementNames) for r in n.selection.rows]==[('Base',['Face1'])]
    # A native raw pick updates the table through the same source element ID.
    n.selection.rows=[]; n.selection.addSelection(n.mesh,'Elem477F3')
    d.poll()
    assert d._selected==[477] and d.table.selectionModel().selectedRows()[0].row()==0
    assert n.owner.metadata=={'original':True} and n.owner.generation==0
    assert len(calls)==1


def test_empty_selection_stale_mesh_and_close_remove_view(dialog,app):
    d,n,_=dialog
    d.table.selectRow(1); d.display('isolate')
    d.table.clearSelection()
    assert not d.view.active and not any(button.isEnabled() for button in d.view_buttons)
    d.table.selectRow(0); d.display('isolate')
    n.mesh.FemMesh.sha='b'*64
    d.poll()
    assert not d.view.active and d._quality is None and d.table.rowCount()==0
    assert '바뀌어' in d.status.text()
    assert not any(button.isEnabled() for button in d.view_buttons)
    d.close(); app.processEvents()
    assert not n.owner.App.observers and len(n.scene.children)==1


def test_reopen_same_window_and_row_change_never_leave_old_geometry(dialog,app):
    d,n,_=dialog
    assert make_dialog(W,C,n.owner,n.mesh) is d
    d.table.selectRow(0);d.display('isolate')
    d.table.selectRow(1)
    assert not d.view.active and d._selected==[479]
    assert n.mode.whichChild.getValue()==3 and len(n.scene.children)==1
    d.display('isolate');assert d.view.element_ids==[479]
    d.close();assert n.owner._mesh_element_dialog is None


def test_typed_other_mesh_view_does_not_leave_panel_with_unmanaged_geometry(dialog,app):
    from types import SimpleNamespace as NS
    from apps.desktop_pre.mesh_element_view import get_view
    d,n,_=dialog
    d.table.selectRow(0);d.display('isolate')
    other=NS(**n.mesh.__dict__);other.Name='OtherMesh';other.Label='다른 메시'
    n.owner.doc.Objects.append(other)
    other_view=get_view(n.owner,other)
    other_view.show([479],other.FemMesh.sha,isolate=True)
    d.poll();assert d.view._closed and not d.reset.isEnabled()
    d.display('fit')
    assert d.view is n.owner._mesh_element_view and not d.view._closed and other_view._closed
    d.close();assert len(n.scene.children)==1 and not n.owner.App.observers


def test_stale_selection_error_is_not_overwritten_by_selected_number(dialog,app):
    d,n,_=dialog;n.mesh.FemMesh.sha='b'*64
    d.table.selectRow(1)
    assert '바뀌었습니다' in d.status.text()
    assert not d.view.active
