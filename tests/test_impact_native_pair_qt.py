"""Native source/response Qt contracts; no solver, converter, or result rebinding."""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
import json,os,subprocess,sys,threading,time

import pytest
from PySide6 import QtCore,QtWidgets,QtTest

from apps.research.impact_editor import ImpactEditor
from apps.research.impact_bulk_editor import ResponseDialog
from apps.research.impact_project import ImportDialog
from caelab import impact_native,impact_reference_bindings as bindings
from caelab.impact_source import capture
from caelab.impact_input_edits import edited_files
from caelab.storage import canonical_hash

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def app():
    application=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from apps.research.appearance import apply_appearance
    apply_appearance(application);return application


def settings(name='native_pair'):
    folder=ROOT/'examples/impact/input_a'/name
    return impact_native.settings_from_source(capture(folder/'impact_0000.rad',folder,
        engine=folder/'impact_0001.rad',units='Mg/mm/s'))


def wait(app,predicate):
    deadline=time.monotonic()+15
    while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert predicate()


def close(app,*widgets):
    from shiboken6 import isValid
    for widget in widgets:
        if widget is not None and isValid(widget):
            if hasattr(widget,'_allow_close'):widget._allow_close=True
            widget.close();widget.deleteLater()
    app.processEvents()


def capture_window(app,widget,name):
    folder=os.environ.get('IMPACT_NATIVE_PAIR_RENDER_DIR')
    if folder:
        path=Path(folder);path.mkdir(parents=True,exist_ok=True);app.processEvents()
        assert widget.grab().save(str(path/(name+'.png')))


@contextmanager
def service(folder):
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.workbench_client import Client
    server=LabHTTPServer(LabService(folder),0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    try:yield Client('http://127.0.0.1:'+str(server.server_port)),server.workbench
    finally:server.shutdown();server.server_close();thread.join(3)


def test_native_pair_without_history_blocks_empty_picker_and_preserves_removable_draft(app,monkeypatch):
    original=settings('native');editor=ImpactEditor(original)
    try:
        page=editor.bulk_page
        editor.show();editor.tabs.setCurrentWidget(page);page.tabs.setCurrentIndex(2)
        assert all(not page.actions[key,verb].isEnabled() for key in ('bulk','interface','response') for verb in ('add','edit','remove'))
        assert '출력 카드가 없어' in page.note.text()
        editor.resize(820,700);capture_window(app,editor,'native-no-history-820')
        page.action('response','add');assert '출력 카드' in page.status.text()
        with pytest.raises(ValueError,match='출력 카드'):ResponseDialog(original)
        draft=deepcopy(original);draft['b_responses']=[{'name':'old_pair','scope':'pair','identity':0,'quantity':'force','component':'FNX'}]
        editor.replace_settings(draft);assert page.actions['response','remove'].isEnabled()
        page.tables['response'].selectRow(0)
        monkeypatch.setattr(QtWidgets.QMessageBox,'question',lambda *a,**kw:QtWidgets.QMessageBox.StandardButton.Cancel)
        page.action('response','remove');assert editor.edited()==draft
        monkeypatch.setattr(QtWidgets.QMessageBox,'question',lambda *a,**kw:QtWidgets.QMessageBox.StandardButton.Yes)
        page.action('response','remove');assert editor.edited()['b_responses']==[]
        assert editor.edited()['source']==original['source'] and original.get('b_responses') is None
    finally:close(app,editor)


def test_native_pair_selection_does_not_accept_unrelated_stale_bindings(app):
    value=settings();value[bindings.KEY]=bindings.snapshot(value)
    value[bindings.KEY]['rows'][0]['value']='CONTROLLED_STALE'
    editor=ImpactEditor(value);dialog=ResponseDialog(editor.edited())
    try:
        original=deepcopy(editor.edited());dialog.apply()
        assert dialog.applied is None and '대응이 바뀌었습니다' in dialog.status.text()
        assert editor.edited()==original
    finally:close(app,dialog,editor)


def test_native_pair_gui_import_edit_remove_same_document_save_and_cold(app,tmp_path,monkeypatch):
    from apps.research.simulation_window import SimulationWindow
    from apps.research.impact_editor import edit
    from caelab.adapters import impact
    from caelab.impact_model import BACKEND
    def forbidden(*args,**kwargs):raise AssertionError('No solver/converter/runtime execution')
    monkeypatch.setattr(impact,'selected_runtime',forbidden);monkeypatch.setattr(impact,'run_owned_command',forbidden)
    folder=ROOT/'examples/impact/input_a/native_pair';workspace=tmp_path/'workspace'
    errors=[];children=[];window=None;expected=None;document_id=None
    original_import_exec=ImportDialog.exec;original_response_exec=ResponseDialog.exec;original_editor_exec=ImpactEditor.exec
    plan=[]
    def import_source(dialog):
        children.append(dialog)
        def start():
            dialog.entry.setText(str(folder/'impact_0000.rad'));dialog.engine.setText(str(folder/'impact_0001.rad'))
            dialog.root.setText(str(folder));dialog.units.setChecked(True);dialog.check_input()
            def finish():
                try:
                    if dialog.worker is not None:QtCore.QTimer.singleShot(10,finish);return
                    assert dialog.source is not None and dialog.ok.isEnabled(),dialog.status.text()
                    dialog.ok.click()
                except Exception as error:errors.append(str(error));dialog.reject()
            QtCore.QTimer.singleShot(10,finish)
        QtCore.QTimer.singleShot(0,start);return original_import_exec(dialog)
    def response(dialog):
        children.append(dialog);quantity,component,accept=plan.pop(0)
        def choose():
            try:
                assert dialog.scope.count()==1 and dialog.scope.currentData()=='pair'
                assert dialog.identity.count()==1 and dialog.identity.currentData()==0
                assert 'LOWER_FACE' in dialog.identity.currentText() and 'UPPER_FACE' in dialog.identity.currentText()
                assert {dialog.component.itemData(i) for i in range(dialog.component.count())}=={'FNX','FNY','FNZ','FTX','FTY','FTZ'}
                dialog.quantity.setCurrentIndex(dialog.quantity.findData(quantity))
                dialog.component.setCurrentIndex(dialog.component.findData(component))
                if quantity=='native_impulse':
                    for width in (760,660):dialog.resize(width,410);capture_window(app,dialog,'pair-response-'+str(width))
                if accept:dialog.apply();assert dialog.applied is not None,dialog.status.text()
                else:dialog.reject()
            except Exception as error:errors.append(str(error));dialog.reject()
        QtCore.QTimer.singleShot(0,choose);return original_response_exec(dialog)
    def edit_model(editor):
        children.append(editor)
        def operate():
            try:
                editor.choose_file();page=editor.bulk_page
                assert editor.edited()['source']['format']=='RAD' and page.native_groups
                assert all(not page.actions[k,v].isEnabled() for k in ('bulk','interface') for v in ('add','edit','remove'))
                original_source=deepcopy(editor.edited()['source'])
                # Explicit source binding already exists after a prior input edit.
                editor.value[bindings.KEY]=bindings.snapshot(editor.edited())
                editor.tabs.setCurrentWidget(page);page.tabs.setCurrentIndex(2)
                for quantity,component in (('force','FNX'),('native_impulse','FTZ'),('sampled_impulse','FNZ')):
                    plan.append((quantity,component,True));page.actions['response','add'].click()
                assert len(editor.edited()['b_responses'])==3
                page.tables['response'].selectRow(0);before=deepcopy(editor.edited())
                plan.append(('force','FNZ',False));page.actions['response','edit'].click();assert editor.edited()==before
                plan.append(('force','FNZ',True));page.actions['response','edit'].click()
                page.tables['response'].selectRow(2);page.actions['response','remove'].click()
                assert len(editor.edited()['b_responses'])==2
                assert editor.edited()['source']==original_source
                impact_native.validate_settings(editor.edited())
                for width in (1080,820):editor.resize(width,700);capture_window(app,editor,'native-response-editor-'+str(width))
                editor.accept()
            except Exception as error:errors.append(str(error));editor.reject()
        QtCore.QTimer.singleShot(0,operate);return original_editor_exec(editor)
    monkeypatch.setattr(ImportDialog,'exec',import_source);monkeypatch.setattr(ResponseDialog,'exec',response);monkeypatch.setattr(ImpactEditor,'exec',edit_model)
    monkeypatch.setattr(QtWidgets.QMessageBox,'question',lambda *a,**kw:QtWidgets.QMessageBox.StandardButton.Yes)
    with service(workspace) as (client,wb):
        try:
            document=client.document_open(kind='simulation',title='원 접촉쌍 응답',draft={'backend':BACKEND,'settings':settings('native')})
            document_id=document['id'];window=SimulationWindow(client,document_id=document_id,poll_interval=0);window.show()
            wait(app,lambda:window.document is not None and not window._busy)
            edit(window);assert not errors,errors
            assert window.local_dirty and len(window.edited_draft()['settings']['b_responses'])==2
            assert window.save_document();wait(app,lambda:not window._busy and not window.local_dirty)
            saved=client.document_read(document_id);expected=deepcopy(saved['draft']['settings'])
            assert [(r['quantity'],r['component']) for r in expected['b_responses']]==[('force','FNZ'),('native_impulse','FTZ')]
            assert saved['runs']==[] and wb.manager.list()==[]
            (tmp_path/'saved.json').write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
        finally:close(app,*reversed(children),window)
    code='''
import sys,json
from pathlib import Path
from PySide6.QtWidgets import QApplication
from apps.research.impact_editor import ImpactEditor
from apps.research.impact_bulk_editor import ResponseDialog
from caelab.workbench import Workbench
from caelab.impact_native import validate_settings
from caelab.impact_input_edits import edited_files
from caelab.storage import canonical_hash
app=QApplication([]);wb=Workbench(sys.argv[1],configuration={'workers':1});editor=dialog=None
try:
 document=wb.document_open(kind='simulation',document_id=sys.argv[2]);settings=document['draft']['settings']
 assert canonical_hash(settings)==sys.argv[3];validate_settings(settings)
 editor=ImpactEditor(settings);rows=settings['b_responses'];assert editor.bulk_page.tables['response'].rowCount()==2
 for row in rows:
  dialog=ResponseDialog(settings,row);assert dialog.identity.currentData()==row['identity'];assert dialog.component.currentData()==row['component']
  dialog.reject();dialog.close();dialog.deleteLater();dialog=None
 assert editor.edited()==settings and not wb.manager.list() and document['runs']==[]
 source=edited_files(settings['source']);fixture=Path(sys.argv[4]);assert all((fixture/name).read_bytes()==raw for name,raw in source.items())
 print('COLD_QT_NATIVE_PAIR_SAME_SOURCE_SELECTION_NO_JOBS')
finally:
 if dialog:dialog.close()
 if editor:editor.close();editor.deleteLater()
 app.processEvents();assert wb.shutdown()['joined']
'''
    cold=subprocess.run([sys.executable,'-c',code,str(workspace),document_id,canonical_hash(expected),str(folder)],cwd=ROOT,capture_output=True,text=True,timeout=30)
    (tmp_path/'cold.stdout').write_text(cold.stdout,encoding='utf-8');(tmp_path/'cold.stderr').write_text(cold.stderr,encoding='utf-8')
    assert cold.returncode==0,cold.stdout+cold.stderr
