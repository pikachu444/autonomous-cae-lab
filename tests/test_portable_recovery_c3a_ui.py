"""Qt contract tests. NOT_RUN when PySide6 is absent; no synthetic GUI PASS."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
from copy import deepcopy
import pytest
pytest.importorskip('PySide6',reason='C3A Qt rendering NOT_RUN: PySide6 is not installed')
pytest.importorskip('matplotlib')
from PySide6.QtWidgets import QApplication,QLineEdit,QMessageBox,QDialog
from PySide6.QtCore import QThreadPool,Qt
from PySide6.QtTest import QTest
from apps.research.data_window import DataWindow
from apps.research.material_window import MaterialWindow
from apps.research.data_recovery import data_raw_snapshot,restore_data_raw
from apps.research.material_recovery import material_raw_snapshot,restore_material_raw
from apps.research.portable_recovery_dialog import PortableRecoveryReadDialog
from apps.research.connection_window_recovery import RecoverySelectionDialog
from caelab.portable_recovery_resume import buffer_token
from caelab.storage import load_json
from examples.portable_connection_c3a_public import create_case,make_copy
from test_portable_recovery_c3a_http import serving


def wait(app,predicate,seconds=8):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        app.processEvents()
        if predicate():return
        time.sleep(.005)  # Let Python owner/HTTP worker run; no QTest busy loop.
    raise AssertionError('C3A Qt transport did not settle')


@pytest.fixture
def app():
    app=QApplication.instance() or QApplication([]);owned=[]
    try:yield app,owned
    finally:
        for window in reversed(owned):
            if isinstance(window,(DataWindow,MaterialWindow)):window._allow_close=True
            window.close();window.deleteLater()
        wait(app,lambda:QThreadPool.globalInstance().activeThreadCount()==0)
        app.processEvents()


@pytest.fixture
def backend(tmp_path):
    wb,case=create_case(tmp_path/'original')
    try:make_copy(wb,case,tmp_path/'copy')
    finally:wb.shutdown()
    import shutil
    shutil.rmtree(tmp_path/'original')
    with serving(tmp_path/'copy') as pair:
        yield (*pair,load_json(tmp_path/'copy/portable-project.json'))


@pytest.mark.parametrize('kind',['data','material'])
def test_original_archive_dialog_to_actual_unfinished_editor(app,backend,kind,monkeypatch):
    application,owned=app;server,client,manifest=backend
    row=next(r for r in manifest['recovery_archives'] if r['original_identity']['kind']==kind)
    document=client.document_read(row['document_id'])
    window=(DataWindow if kind=='data' else MaterialWindow)(client,auto_open=False,poll_interval=0)
    owned.append(window);window._show_document(document);window.show();application.processEvents()
    snapshot=data_raw_snapshot if kind=='data' else material_raw_snapshot
    restore=restore_data_raw if kind=='data' else restore_material_raw
    identity=client.data_material('recovery.identity',{'document_id':document['id']})
    records=[r for r in client.portable_recovery_catalog([document['id']])['archives'] if r['source']=='CARRIED_ORIGINAL']
    original=deepcopy(window.document['draft']);packets=[]
    def received(packet):
        packets.append(packet);window._show_document(packet['document']);restore(window,packet['raw'])
    dialog=PortableRecoveryReadDialog(client,document,records,current=lambda:(identity,snapshot(window)),restore=received,parent=window)
    owned.append(dialog);dialog.show();wait(application,lambda:dialog.layers is not None and not dialog._busy)
    assert dialog.cells.item(0,3).text()=='1e'
    assert dialog.context.rowCount()>0
    if kind=='data':assert dialog.source_choice.count()==2
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    dialog.resume();wait(application,lambda:bool(packets) and not dialog.isVisible())
    actual=snapshot(window)
    assert any(c['raw_text']=='1e' and c['editor_kind']=='unfinished' for c in actual['cells'])
    assert client.document_read(document['id'])['draft']==original
    assert server.workbench.manager.list()==[] and server.workbench._assistance is None


def test_two_actual_plan_widgets_restore_separate_blank_invalid(app,backend):
    application,owned=app;server,client,manifest=backend
    material=next(r for r in manifest['recovery_archives'] if r['original_identity']['kind']=='material')
    document=client.document_read(material['document_id'])
    window=MaterialWindow(client,auto_open=False,poll_interval=0);owned.append(window)
    window._show_document(document);window.show();panel=window.open_plan_variables()
    wait(application,lambda:not panel._busy and panel.plans.count()==2)
    expected={}
    for row in [r for r in manifest['recovery_archives'] if r['original_identity']['kind']=='numerical']:
        identifier=row['document_id'];panel.plans.setCurrentIndex(panel.plans.findData(identifier));application.processEvents()
        widget=panel._widgets[identifier];doc=widget.document_snapshot()
        token=buffer_token(widget.recovery_snapshot())
        identity=client.data_material('recovery.identity',{'document_id':identifier})
        preview=client.portable_recovery_preview(row['archive_id'],target_identity=identity,buffer=token)
        packet=client.portable_recovery_resume(preview,approved=True,overwrite_approved=True,live_buffer=token,command_id=preview['command_id'])
        widget.bind_owner(panel._adapters[identifier],packet['document']);widget.restore_recovery(packet['raw'])
        expected[identifier]=packet['raw']['cells'][0]['raw_text']
    recovered={doc['id']:snapshot() for doc,snapshot,_ in panel.recovery_views()}
    assert sorted(expected.values())==['','invalid']
    for identifier,text in expected.items():
        assert any(c['raw_text']==text for c in recovered[identifier]['cells'])
    assert server.workbench.manager.list()==[]


def test_copy_picker_requires_explicit_kept_selection(app,backend):
    application,owned=app;server,client,manifest=backend
    ids=[r['document_id'] for r in manifest['documents']]
    dialog=RecoverySelectionDialog(client.portable_recovery_catalog(ids));owned.append(dialog)
    assert dialog.selections()==[]
    dialog.table.item(0,0).setCheckState(Qt.CheckState.Checked)
    assert len(dialog.selections())==1 and 'archive_id' in dialog.selections()[0]


def test_copy_picker_keeps_valid_rows_available_when_a_kept_archive_is_broken(app):
    application,owned=app
    blocked=dict(selection={'document_id':'Mbroken','capsule_id':'Qbroken'},
        document_id='Mbroken',title='누락된 원문',kind='material',state='BLOCKED',
        selectable=False,message='Declared recovery asset is missing: input.json')
    valid=dict(selection={'document_id':'Mvalid','capsule_id':'Qvalid'},
        document_id='Mvalid',title='읽을 수 있는 원문',kind='material',state='STORED',
        source='KEPT_IN_CURRENT_STORE',selectable=True)
    dialog=RecoverySelectionDialog({'archives':[blocked,valid]});owned.append(dialog)
    dialog.show();application.processEvents()
    assert 'input.json' in dialog.message.text()
    assert not dialog.table.item(0,0).flags() & Qt.ItemFlag.ItemIsEnabled
    dialog.table.item(1,0).setCheckState(Qt.CheckState.Checked)
    assert dialog.selections()==[valid['selection']]


def test_actual_menu_read_keeps_dirty_delegate_and_backward_selection(app,backend,monkeypatch):
    application,owned=app;server,client,manifest=backend
    row=next(r for r in manifest['recovery_archives'] if r['original_identity']['kind']=='material')
    document=client.document_read(row['document_id'])
    window=MaterialWindow(client,auto_open=False,poll_interval=0);owned.append(window)
    window._show_document(document);window.show();window.activateWindow();application.processEvents()
    table=window.coefficients;table.setCurrentCell(0,1);table.editItem(table.item(0,1))
    application.processEvents()
    editor=next(e for e in table.findChildren(QLineEdit) if e.isVisible())
    wait(application,editor.hasFocus)
    editor.selectAll();QTest.keyClicks(editor,'1e');editor.setSelection(2,-1)
    assert editor.text()=='1e' and editor.selectedText()=='e' and editor.cursorPosition()==1
    before=material_raw_snapshot(window);seen=[]
    def inspect(dialog):
        owned.append(dialog);dialog.show()
        wait(application,lambda:dialog.layers is not None and not dialog._busy)
        assert dialog.resume() is False
        assert '현재 편집 원문' in dialog.message.text()
        dialog.reject();seen.append(True)
        return dialog.result()
    monkeypatch.setattr(PortableRecoveryReadDialog,'exec',inspect)
    window.portable_recovery_action.trigger()
    # activateWindow/setFocus on modal exit completes on the next Qt event turn.
    wait(application,lambda:seen and window._recovery_review is None and editor.hasFocus())
    after=material_raw_snapshot(window)
    assert after['cells']==before['cells'] and after['focus']==before['focus']
    assert editor.hasFocus() and editor.selectedText()=='e' and editor.cursorPosition()==1
    assert client.document_read(document['id'])==document
    assert server.workbench.manager.list()==[] and server.workbench._assistance is None
