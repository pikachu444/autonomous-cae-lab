"""Impact A source editing, real Qt and existing document owner; no solver."""
from copy import deepcopy
from pathlib import Path
import json,os,subprocess,sys,time,uuid
import shutil,re
import pytest
from PySide6 import QtCore,QtGui,QtWidgets
from apps.research.impact_editor import ImpactEditor
from apps.research.impact_project import ImportDialog
from apps.research.impact_source_editor import SourceChangeDialog,ReferenceReviewDialog
from caelab import impact_input_workflow as workflow,impact_reference_bindings as bindings
from caelab.impact_source import capture
from caelab.impact_model import default_settings
from caelab.storage import canonical_hash

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def app():
    application=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from apps.research.appearance import apply_appearance
    apply_appearance(application)
    return application

@pytest.fixture
def settings():
    folder=ROOT/'examples/impact/input_a/native'
    return workflow.open_definition(folder/'impact_0000.rad',folder,engine=folder/'impact_0001.rad',units='Mg/mm/s')['settings']

def choose_file(page,name):
    for i in range(page.files.topLevelItemCount()):
        if page.files.topLevelItem(i).text(0)==name:
            page.files.setCurrentItem(page.files.topLevelItem(i));return
    raise AssertionError(name)

def field_dialog(editor,key='end_s'):
    field=next(f for f in workflow.inspect(editor.edited())['fields'] if f['field']==key)
    choose_file(editor.source_page,field['file'])
    return SourceChangeDialog(editor.source_page,field=field)

def release(app,*widgets):
    for widget in widgets:widget.close();widget.deleteLater()
    app.processEvents()

def test_native_import_engine_units_cancel_and_source_projection(app,settings):
    folder=ROOT/'examples/impact/input_a/native';dialog=ImportDialog()
    try:
        dialog.entry.setText(str(folder/'impact_0000.rad'));dialog.engine.setText(str(folder/'impact_0001.rad'))
        dialog.root.setText(str(folder));dialog.units.setChecked(True);dialog.show();dialog.check_input()
        assert not dialog.units.isEnabled() and not dialog.engine.isEnabled()
        deadline=time.monotonic()+8
        while dialog.worker is not None and time.monotonic()<deadline:
            app.processEvents();QtCore.QThread.msleep(5)
        assert dialog.worker is None and dialog.source is not None and dialog.ok.isEnabled()
        assert dialog.source['format']=='RAD' and dialog.files.count()>=3
        dialog.units.setChecked(False)
        assert dialog.source is None and not dialog.ok.isEnabled()
        editor=ImpactEditor(settings)
        try:
            assert editor.tabs.currentWidget() is editor.project
            for i in range(editor.tabs.count()):
                if editor.tabs.tabText(i)=='시간과 중력':assert not editor.tabs.isTabEnabled(i)
            editor.times['end_s'].setText('999')
            assert editor.edited()['time']==settings['time']
        finally:release(app,editor)
    finally:
        if dialog.worker is not None:dialog.worker.cancelled.set();dialog.worker.wait(8000)
        release(app,dialog)

def test_native_preview_cancel_apply_preserves_original_and_invalid_draft(app,settings,tmp_path):
    original=deepcopy(settings);editor=ImpactEditor(settings);dialog=None
    try:
        dialog=field_dialog(editor);dialog.replacement.setPlainText('0.0012');dialog.show_preview()
        assert dialog.apply_button.isEnabled() and editor.edited()==original
        dialog.reject();assert editor.edited()==original
        release(app,dialog);dialog=field_dialog(editor);dialog.replacement.setPlainText('0.0012');dialog.show_preview();dialog.apply()
        editor.replace_settings(dialog.applied)
        assert editor.edited()['time']['end_s']==.0012 and settings==original
        assert editor.edited()['source']['bundle']==settings['source']['bundle']
        changed=deepcopy(editor.edited());stale=field_dialog(editor);editor.value['qualification']='edited elsewhere'
        stale.replacement.setPlainText('0.002');stale.show_preview();assert not stale.apply_button.isEnabled()
        release(app,stale);editor.replace_settings(changed)
        page=editor.source_page;file=next(f['file'] for f in workflow.inspect(editor.edited())['fields'] if f['field']=='end_s');choose_file(page,file)
        content=page.original.toPlainText();start=content.index('/ANIM/VECT/DISP')
        cursor=page.original.textCursor();cursor.setPosition(start);cursor.setPosition(start+len('/ANIM/VECT/DISP'),QtGui.QTextCursor.MoveMode.KeepAnchor);page.original.setTextCursor(cursor)
        bad=SourceChangeDialog(page);bad.replacement.setPlainText('/UNSUPPORTED_GUI_CARD\n');bad.show_preview();bad.apply()
        assert bad.applied is not None and workflow.inspect(bad.applied)['blockers'],bad.status.text()
        editor.replace_settings(bad.applied);assert editor.source_page.diagnostics.topLevelItemCount()>0
        diagnostic=editor.source_page.diagnostics.topLevelItem(0)
        editor.source_page.locate_diagnostic(diagnostic)
        assert 'UNSUPPORTED_GUI_CARD' in editor.source_page.original.textCursor().selectedText()
        from caelab.workbench import Workbench
        owner=Workbench(tmp_path/'invalid-draft',configuration={'workers':1})
        try:
            doc=owner.document_open(kind='simulation',title='미지원 카드 초안',draft={'backend':'explicit.opencourant.model','settings':bad.applied})
            saved=owner.document_command(doc['id'],'document.save',{},session_id=doc['session_id'],
                expected_generation=doc['generation'],command_id='C'+uuid.uuid4().hex)
            assert saved['document']['draft']['settings']==bad.applied
            doc=saved['document']
            with pytest.raises(ValueError):
                owner.document_command(doc['id'],'simulation.evaluate',{},session_id=doc['session_id'],
                    expected_generation=doc['generation'],command_id='C'+uuid.uuid4().hex)
        finally:owner.shutdown(10)
        release(app,bad)
    finally:release(app,*([dialog] if dialog else []),editor)

@pytest.mark.parametrize('change',['renamed','removed_old_id'])
def test_crlf_range_and_explicit_reference_review_preserve_logical_entity(app,tmp_path,change):
    folder=tmp_path/'input';shutil.copytree(ROOT/'examples/impact/input_a',folder)
    path=folder/'assembly.inp';raw=path.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n');path.write_bytes(raw)
    value=workflow.open_definition(folder/'assembly.inp',folder)['settings']
    local=20 if change=='renamed' else 40
    value['responses']=[workflow.response_for_source(value,quantity='displacement',component='Z',association='POINTS',instance='BODY-2',local_id=local)]
    editor=ImpactEditor(value);dialog=None
    try:
        source=deepcopy(editor.edited());file=next(row['path'] for row in source['source']['bundle']['files'] if 'Body-2' in row['text']);page=editor.source_page;choose_file(page,file)
        # Display selection uses normalized Qt characters; adapter owns byte/EOL mapping.
        text=page.original.toPlainText();start=0;end=len(text)
        cursor=page.original.textCursor();cursor.setPosition(start);cursor.setPosition(end,QtGui.QTextCursor.MoveMode.KeepAnchor);page.original.setTextCursor(cursor)
        changed_text=text.replace('Body-2','Body-3')
        if change=='removed_old_id':
            changed_text=re.sub(r'\*INSTANCE,NAME=Body-1.*?\*END INSTANCE\n','',text,flags=re.S)
            changed_text=changed_text.replace('*NSET,NSET=Fixed,INSTANCE=Body-1\n10\n','')
            changed_text=changed_text.replace('Body-1.40,Body-2.Tip','Body-2.Tip').replace('Body-1.Solid,Body-2.Solid','Body-2.Solid')
            changed_text=changed_text.replace('*BOUNDARY\nDrop.Fixed,1,3,0\n','')
        dialog=SourceChangeDialog(page);dialog.replacement.setPlainText(changed_text);dialog.show_preview();dialog.apply()
        assert dialog.applied is not None,dialog.status.text()
        from caelab.impact_input_edits import edited_files
        changed=edited_files(dialog.applied['source'])[file]
        assert b'\r\n' in changed and changed.replace(b'\r\n',b'').find(b'\n')<0
        assert path.read_bytes()==raw
        editor.replace_settings(dialog.applied)
        review=ReferenceReviewDialog(editor.edited());review.show_review()
        assert review.choices and review.table.item(0,1).text().find('BODY-2')>=0
        before=deepcopy(editor.edited());review.reject();assert editor.edited()==before
        # Select the current source entity explicitly; never recycle an effective ID.
        selection,combo=review.choices[0]
        assert combo.currentIndex()==-1
        wanted='BODY-3 / 원 번호 20' if change=='renamed' else 'BODY-2 / 원 번호 40'
        target=next(i for i in range(combo.count()) if wanted in combo.itemText(i))
        combo.setCurrentIndex(target);review.show_review();assert review.confirm.isEnabled();review.apply()
        assert review.applied is not None
        editor.replace_settings(review.applied)
        report=bindings.review(editor.edited());assert not report['changed']
        assert report['after'][0]['source']['instance']==('BODY-3' if change=='renamed' else 'BODY-2')
        release(app,review)
    finally:release(app,*([dialog] if dialog else []),editor)

def test_same_simulation_save_and_separate_process_reopen_continues_edit(app,settings,tmp_path):
    from caelab.workbench import Workbench
    root=tmp_path/'workspace';owner=Workbench(root,configuration={'workers':1});editor=ImpactEditor(settings)
    def command(document,operation,args):
        return owner.document_command(document['id'],operation,args,session_id=document['session_id'],
            expected_generation=document['generation'],command_id='C'+uuid.uuid4().hex)
    try:
        doc=owner.document_open(kind='simulation',title='원 입력 편집',draft={'backend':'explicit.opencourant.model','settings':settings})
        dialog=field_dialog(editor);dialog.replacement.setPlainText('0.0012');dialog.show_preview();dialog.apply();editor.replace_settings(dialog.applied)
        doc=command(doc,'simulation.update',{'draft':{'backend':'explicit.opencourant.model','settings':editor.edited()}})['document']
        doc=command(doc,'document.save',{})['document'];expected=canonical_hash(doc['draft']);identifier=doc['id']
        release(app,dialog)
    finally:owner.shutdown(10);release(app,editor)
    code='from caelab.workbench import Workbench;import sys,json;w=Workbench(sys.argv[1]);\ntry:\n d=w.document_open(kind="simulation",document_id=sys.argv[2]);print(json.dumps(d))\nfinally:w.shutdown(10)'
    cold=subprocess.run([sys.executable,'-c',code,str(root),identifier],cwd=ROOT,capture_output=True,text=True,check=True)
    document=json.loads(cold.stdout);assert canonical_hash(document['draft'])==expected
    continued=ImpactEditor(document['draft']['settings'])
    try:
        edit=field_dialog(continued);assert float(edit.original)==.0012;edit.replacement.setPlainText('0.0013');edit.show_preview();assert edit.apply_button.isEnabled();release(app,edit)
    finally:release(app,continued)


def test_import_cancel_waits_for_owned_reader_and_ignores_late_result(app):
    folder=ROOT/'examples/impact/input_a/native';dialog=ImportDialog()
    try:
        dialog.entry.setText(str(folder/'impact_0000.rad'));dialog.engine.setText(str(folder/'impact_0001.rad'))
        dialog.root.setText(str(folder));dialog.units.setChecked(True);dialog.check_input();dialog.reject()
        assert dialog._cancel and dialog.source is None
        deadline=time.monotonic()+8
        while dialog.worker is not None and time.monotonic()<deadline:
            app.processEvents();QtCore.QThread.msleep(5)
        assert dialog.worker is None and dialog.source is None and not dialog.ok.isEnabled()
    finally:
        if dialog.worker is not None:dialog.worker.cancelled.set();dialog.worker.wait(8000)
        release(app,dialog)


def test_stale_generated_sets_remain_visible_and_reselect_one_by_one(app):
    from examples.impact.include_project import settings as included_settings
    from apps.research.impact_project import TargetDialog
    value=included_settings();original=deepcopy(value)
    file=next(row['path'] for row in value['source']['bundle']['files'] if '1000,0.3' in row['text'])
    buffer=workflow.editor_buffer(value,file);start=buffer['effective_text'].index('1000,0.3')
    changed=workflow.apply_display_range(value,file=file,start=start,end=start+4,replacement='900',
        reason='공개 GUI 원문 수정',expected_definition_sha256=canonical_hash(value))['settings']
    editor=ImpactEditor(changed)
    try:
        page=editor.project;assert page.reselect_generated and page.tree.topLevelItemCount()==1
        before=deepcopy(editor.edited());page.tree.setCurrentItem(page.tree.topLevelItem(0).child(0));page.remove()
        assert '사용 중' in page.message.text() and editor.edited()==before
        for definition in list(changed['generated_sets']):
            page.refresh((definition['kind'],definition['name']));failures=[]
            def operate():
                dialog=app.activeModalWidget()
                try:
                    assert isinstance(dialog,TargetDialog)
                    assert dialog.chosen()==[]
                    if definition['kind']=='surface':
                        for face in definition['faces']:dialog.select_face(tuple(face))
                    dialog.apply()
                except BaseException as error:failures.append(error);dialog.reject()
            QtCore.QTimer.singleShot(0,operate);page.edit();assert not failures
            current=next(row for row in editor.edited()['generated_sets'] if row['name']==definition['name'])
            assert current['source_sha256']!=definition['source_sha256']
        assert not page.reselect_generated
        assert editor.edited()['motions']==original['motions'] and editor.edited()['contacts']==original['contacts']
        assert value==original
    finally:release(app,editor)


def test_reference_details_expose_difference_after_fifth_member(app):
    from examples.impact.include_project import settings as included_settings
    settings=included_settings();settings[bindings.KEY]=bindings.snapshot(settings)
    members=settings[bindings.KEY]['rows'][0]['source']['members'];assert len(members)>5
    current_sixth=members[5]['native_id'];members[5]['native_id']=999999
    dialog=ReferenceReviewDialog(settings)
    try:
        for selection,combo in dialog.choices:
            if combo.currentIndex()<0:combo.setCurrentIndex(combo.findData(settings[selection[0]][selection[1]][selection[2]]))
        dialog.show_review();assert dialog.confirm.isEnabled()
        detail=dialog.details.toPlainText()
        assert '999999' in detail and '원 번호 '+str(current_sixth) in detail
        assert '기존 원 대상 전체 구성원' in detail and '현재 원 대상 전체 구성원' in detail
    finally:release(app,dialog)


def test_hierarchical_new_response_uses_instance_local_display_and_saved_identity(app,monkeypatch):
    from caelab.impact_responses import QUANTITIES
    from caelab.impact_assembly import exact_entity
    from caelab.impact_model import model_from_settings
    folder=ROOT/'examples/impact/input_a';settings=workflow.open_definition(folder/'assembly.inp',folder)['settings']
    editor=ImpactEditor(settings);seen=[]
    def pick(*args,**kwargs):
        choices=args[3];seen.append(choices)
        return (QUANTITIES['displacement'][0] if len(seen)==1 else 'BODY-2 / 원 번호 20'),True
    monkeypatch.setattr(QtWidgets.QInputDialog,'getItem',pick)
    try:
        editor.add_response();assert editor.responses.rowCount()==1
        assert 'BODY-1 / 원 번호 20' in seen[1] and 'BODY-2 / 원 번호 20' in seen[1]
        combo=editor.responses.cellWidget(0,2);assert combo.currentText()=='BODY-2 / 원 번호 20'
        expected=exact_entity(model_from_settings(settings),'POINTS','BODY-2',20)
        assert combo.currentData()==expected and editor.edited()['responses'][0]['identity']==expected
        reopened=ImpactEditor(editor.edited())
        try:assert reopened.responses.cellWidget(0,2).currentText()=='BODY-2 / 원 번호 20'
        finally:release(app,reopened)
        combo.setCurrentIndex(-1);assert editor.edited()['responses'][0]['identity'] is None
    finally:release(app,editor)
