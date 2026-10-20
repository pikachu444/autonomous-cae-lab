"""Qt panel construction before the native connection is attached."""
import os
from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def test_shell_panel_opens_before_connection_without_shadowing_qwidget_actions():
    from PySide6 import QtCore, QtWidgets
    from apps.desktop_pre.shell_panel import make_panel

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    editor = SimpleNamespace(inspect=lambda: {
        'analyses': [], 'meshes': [], 'solvers': [], 'records': [],
    })
    panel = make_panel(QtWidgets, QtCore, editor, lambda *args, **kwargs: None)
    try:
        assert panel.shell_actions is None
        assert callable(panel.actions)
        assert not panel.cancel_prepare_button.isEnabled()
        panel.show()
        app.processEvents()
        assert panel.isVisible()
    finally:
        panel.close()
        panel.deleteLater()


@pytest.fixture
def saved_panel():
    """Product widgets with explicit source/command doubles; no native calculation."""
    from PySide6 import QtCore as C,QtWidgets as W,QtGui as G
    from apps.desktop_pre.shell_panel import make_panel
    from test_shell_support import model
    app=W.QApplication.instance() or W.QApplication([])
    path=Path('C:/Windows/Fonts/malgun.ttf')
    font=G.QFontDatabase.addApplicationFont(str(path)) if app.platformName()=='offscreen' and path.is_file() else -1
    data=model()
    descriptor={'analyses':[{'id':'ShellAnalysis','label':'검사 판재'}],
        'meshes':[{'id':'ShellMesh','label':'검사 S8 메시'}],'solvers':[{'id':'Solver','label':'CalculiX'}],
        'records':[{'analysis_id':'ShellAnalysis','draft':deepcopy(data['draft']),'ready':True,'applied':True,'errors':[]}]}
    editor=SimpleNamespace(inspect=lambda:deepcopy(descriptor),
        _mesh=lambda draft:(None,{int(n):p for n,p in data['source_nodes'].items()},
                           {int(e):c for e,c in data['source_elements'].items()}))
    calls=[]
    def submit(op,args,on_done=None):
        calls.append((op,deepcopy(args)))
        if op=='pre.shell.save_draft':
            descriptor['records'][0]['draft'].update(deepcopy(args['fields']))
            if on_done:on_done(deepcopy(descriptor))
        elif op=='pre.shell.preview_rebind':
            if on_done:on_done({'token':'Selection','mesh_label':'검사 S8 메시','selected_count':len(args['elements'])})
        elif op=='document.save':
            if on_done:on_done({'saved':True})
    p=make_panel(W,C,editor,submit);p.show();app.processEvents()
    yield p,app,data,calls
    p.close();p.deleteLater();app.processEvents()
    if font>=0:G.QFontDatabase.removeApplicationFont(font)


@pytest.mark.parametrize('width',[480,900])
def test_property_errors_do_not_enlarge_panel_and_restore_physical_tooltips(saved_panel,width):
    from PySide6 import QtCore as C,QtWidgets as W,QtTest as T
    p,app,_,calls=saved_panel
    p.resize(width,850);app.processEvents()
    assert p.width()==width and p.properties.isColumnHidden(2)
    assert '(0.5 - Offset)' in p.edits['offset'].toolTip()
    assert '+법선과 반대' in p.edits['pressure_MPa'].toolTip()
    field=p.edits['thickness_mm'];field.setFocus()
    value_x=p.properties.columnViewportPosition(1)
    T.QTest.keyClick(field,C.Qt.Key_A,C.Qt.ControlModifier);T.QTest.keyClicks(field,'1e');app.processEvents()
    assert p.width()==width and not p.properties.isColumnHidden(2)
    assert p.properties.columnViewportPosition(1)==value_x
    assert field.text()=='1e' and p.buffer.fields['thickness_mm']=='1e'
    assert '오류:' in p.properties.item(0,2).text() and field.property('invalid')
    assert p.save_button.isEnabled() and not p.prepare_button.isEnabled()
    p.save_button.click();assert calls[0][0]=='pre.shell.save_draft' and calls[0][1]['fields']['thickness_mm']=='1e'
    assert calls[1][0]=='document.save' and not p.busy
    assert field.text()=='1e'
    T.QTest.keyClick(field,C.Qt.Key_A,C.Qt.ControlModifier);T.QTest.keyClicks(field,'3');app.processEvents()
    assert p.properties.isColumnHidden(2) and not field.property('invalid')
    assert '(0.5 - Offset)' in p.edits['offset'].toolTip()


def test_fixed_nodes_and_same_mesh_elements_restore_selection_on_confirm(saved_panel):
    from PySide6 import QtCore as C,QtWidgets as W
    p,app,data,calls=saved_panel
    p.buffer.fields['fixed_nodes']=list(data['fixed_nodes']);p.show_errors()
    original=deepcopy(p.buffer.fields['fixed_nodes'])
    assert str(len(original)) in p.support_count.text()

    def confirm_dialogs(steps,open_dialog):
        pending=list(steps);errors=[]
        unrelated=W.QDialog();unrelated.setWindowTitle('다른 작업의 대화상자');unrelated.show()
        elapsed=C.QElapsedTimer();elapsed.start()
        timer=C.QTimer(p);timer.setInterval(10)
        def confirm():
            owned=[d for d in p.findChildren(W.QDialog) if d.parentWidget() is p and d.isVisible()]
            try:
                if elapsed.elapsed()>5000:
                    raise AssertionError('Shell selection dialog did not reach '+pending[0][0])
                matching=[d for d in owned if d.windowTitle()==pending[0][0]]
                if not matching:return
                dialog=matching[0];_,inspect=pending.pop(0)
                inspect(dialog)
                buttons=dialog.findChild(W.QDialogButtonBox)
                assert buttons is not None
                buttons.button(W.QDialogButtonBox.Ok).click()
                if not pending:timer.stop()
            except Exception as error:
                errors.append(error);timer.stop()
                for dialog in owned:dialog.reject()
        timer.timeout.connect(confirm);timer.start()
        try:
            open_dialog()
            if errors:raise errors[0]
            assert not pending,'Shell selection did not open the expected dialogs'
            assert unrelated.isVisible()
        finally:
            timer.stop();timer.deleteLater()
            unrelated.close();unrelated.deleteLater()

    def inspect_nodes(d):
        table=d.findChild(W.QTableWidget)
        ids=[int(table.item(i.row(),0).text()) for i in table.selectionModel().selectedRows()]
        assert sorted(ids)==original
    confirm_dialogs([('고정 절점',inspect_nodes)],lambda:p.choose_mesh_ids(True))
    assert p.buffer.fields['fixed_nodes']==original and not calls
    def inspect_mesh(d):
        assert d.findChild(W.QComboBox).currentData()=='ShellMesh'
    def inspect_elements(d):
        table=d.findChild(W.QTableWidget)
        ids=[int(table.item(i.row(),0).text()) for i in table.selectionModel().selectedRows()]
        assert sorted(ids)==data['draft']['elements']
    confirm_dialogs([('셸 메시',inspect_mesh),('셸 참여 요소',inspect_elements)],lambda:p.choose_mesh_ids(False))
    assert calls[-1]==('pre.shell.preview_rebind',{'analysis_id':'ShellAnalysis','mesh_id':'ShellMesh','elements':data['draft']['elements']})
