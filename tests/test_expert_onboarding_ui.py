"""Actual Qt/current HTTP/Knowledge ingest. No model/provider/native run.

Uses only a temporary operator config/store and explicitly fake installation
files. It does not establish readiness of the user's real default settings.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import time

from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QApplication,QDialog,QDialogButtonBox,QListWidget,QMessageBox
from PySide6.QtTest import QTest

from caelab import expert_connection as setup
from caelab.storage import save_json
from test_expert_connection import transport,public_installation
from apps.research.appearance import apply_appearance
from apps.research.expert_connection_dialog import ConnectionDialog
from apps.research.expert_sources import SourceDialog
from apps.research.expert_library_pack import OfficialDocumentsDialog

COLLECTIONS=['pre-freecad-fem','mesh-gmsh','post-paraview']
CUSTOM={'id':'custom','label':'사용자 시험 검토','instructions':'사용자가 보관한 기존 지시입니다.',
    'collections':['project-current'],'tools':['knowledge.source']}


def app():
    value=QApplication.instance() or QApplication([])
    apply_appearance(value)
    return value


def wait(application,predicate,detail=lambda:''):
    deadline=time.monotonic()+20
    while not predicate() and time.monotonic()<deadline:
        application.processEvents();time.sleep(.01)
    assert predicate(),detail()


def cleanup(application,*dialogs):
    from shiboken6 import isValid
    for dialog in dialogs:
        if dialog is not None:
            if isValid(dialog):
                if hasattr(dialog,'_allow_close'):
                    # Cleanup only this owned temporary Expert window. The
                    # close/save decision itself is outside this onboarding test.
                    dialog._allow_close=True
                def discard_test_buffer():
                    modal=application.activeModalWidget()
                    if isinstance(modal,QMessageBox):
                        button=modal.button(QMessageBox.StandardButton.Discard)
                        if button:button.click()
                QTimer.singleShot(0,discard_test_buffer)
                dialog.close()
            wait(application,lambda:all(worker.completed.is_set() for worker in dialog._workers))
            if isValid(dialog):dialog.deleteLater()
    application.processEvents()


def capture(widget,name):
    folder=os.environ.get('EXPERT_ONBOARDING_RENDER_DIR')
    if folder:
        path=Path(folder);path.mkdir(parents=True,exist_ok=True)
        assert widget.grab().save(str(path/(name+'.png')))


def initialize(tmp_path,monkeypatch):
    config=tmp_path/'operator.json'
    save_json(config,{'experts':[deepcopy(CUSTOM)],'runtime':None,'unrelated':{'keep':True}})
    profile,runtime=public_installation(tmp_path)
    monkeypatch.setattr(setup,'default_config_path',lambda:config)
    monkeypatch.setattr(setup,'discover',lambda:{'profiles':[str(profile)],'runtimes':[str(runtime)]})
    return config,profile,runtime


def test_preset_and_role_scope_cancel_preserve_user_roles_connection_and_permissions(tmp_path,monkeypatch):
    application=app();config,_,_=initialize(tmp_path,monkeypatch)
    original=config.read_bytes()
    with transport(tmp_path,config) as (client,wb):
        dialog=ConnectionDialog(client,config_path=config)
        try:
            dialog.show();wait(application,lambda:dialog.loaded and not dialog._busy)
            dialog.tabs.setCurrentIndex(1)
            QTest.mouseClick(dialog.load_preset_button,Qt.MouseButton.LeftButton)
            assert [row['id'] for row in dialog.definitions]==['custom','r0','r1','r2']
            assert dialog.definitions[0]==CUSTOM
            assert all(row['collections']==['public'] for row in dialog.definitions[1:])
            dialog.roles.setCurrentCell(1,0)
            def cancel_scope():
                modal=application.activeModalWidget();choices=modal.findChild(QListWidget)
                for i in range(choices.count()):
                    if choices.item(i).data(Qt.ItemDataRole.UserRole) in COLLECTIONS:
                        choices.item(i).setCheckState(Qt.CheckState.Checked)
                modal.reject()
            QTimer.singleShot(0,cancel_scope);dialog.edit_role_collections()
            assert dialog.definitions[1]['collections']==['public'] and dialog._selected_collections()==[]
            dialog.preset.setCurrentIndex(1);dialog.load_preset()
            assert {row['id'] for row in dialog.definitions}>={'custom','r0','r1','r2','materials','testing'}
            dialog.preset.setCurrentIndex(2);dialog.load_preset()
            assert dialog.definitions==[CUSTOM]
            dialog.reject()
            assert config.read_bytes()==original and wb.config['experts']==[CUSTOM]
            assert wb.config['runtime'] is None and wb.manager.list()==[]
        finally:cleanup(application,dialog)


def test_source_settings_refresh_and_original_text_preserved(tmp_path,monkeypatch):
    application=app();config,profile,runtime=initialize(tmp_path,monkeypatch)
    with transport(tmp_path,config) as (client,wb):
        dialog=SourceDialog(client,{},collections=['project-current'],role_id='custom')
        settings=[];errors=[]
        original_exec=ConnectionDialog.exec
        def configure(value):
            settings.append(value)
            def accept():
                try:
                    if not value.loaded or value._busy:
                        QTimer.singleShot(10,accept);return
                    value.enabled.setChecked(True);value.profile.setEditText(str(profile))
                    value.runtime.setEditText(str(runtime));value.model.setEditText('openai-codex/test-model')
                    value.question.setChecked(False);value.apply()
                    def finish():
                        if value._busy:QTimer.singleShot(10,finish)
                        else:value.reject()
                    QTimer.singleShot(10,finish)
                except Exception as error:errors.append(str(error));value.reject()
            QTimer.singleShot(0,accept)
            return original_exec(value)
        monkeypatch.setattr(ConnectionDialog,'exec',configure)
        try:
            dialog.show();wait(application,lambda:not dialog._busy and dialog._connection_status=='NOT_CONFIGURED')
            dialog.open_settings()
            wait(application,lambda:not dialog._busy and dialog._connection_status=='CONFIGURED')
            assert not errors and dialog._role_collections=={'project-current'}
            assert wb.config['runtime']['transmission'].get('collections',[])==[]
            payload={'title':'보관된 공식 원문','segments':[{'locator':{'section':'<img alt="FEM">','line_start':1,'line_end':12},
                'text':'<img alt="FEM">\n# Official original text','limitations':[]}]}
            original=deepcopy(payload);dialog.preview.set_payload(payload)
            assert dialog.preview.segment.currentText()=='줄 1–12'
            assert dialog.preview.text.toPlainText()==payload['segments'][0]['text']
            assert dialog.preview.payload==original and payload==original
            assert wb.manager.list()==[]
        finally:cleanup(application,*settings,dialog)


def test_qt_three_roles_official_import_team_selection_and_saved_draft(tmp_path,monkeypatch):
    from apps.research.expert_window import ExpertWindow
    from apps.research.research_team_panel import TeamReviewDialog
    application=app();config,profile,runtime=initialize(tmp_path,monkeypatch)
    with transport(tmp_path,config) as (client,wb):
        connection=ConnectionDialog(client,config_path=config);window=None
        errors=[];source_visits=[];official_visits=[]
        try:
            connection.show();wait(application,lambda:connection.loaded and not connection._busy)
            connection.tabs.setCurrentIndex(1);connection.load_preset()
            for index in (1,2,3):
                connection.roles.setCurrentCell(index,0)
                def accept_scope():
                    modal=application.activeModalWidget();choices=modal.findChild(QListWidget)
                    for i in range(choices.count()):
                        if choices.item(i).data(Qt.ItemDataRole.UserRole) in COLLECTIONS:
                            choices.item(i).setCheckState(Qt.CheckState.Checked)
                    modal.accept()
                QTimer.singleShot(0,accept_scope);connection.edit_role_collections()
            assert connection._selected_collections()==[]
            connection.enabled.setChecked(True);connection.profile.setEditText(str(profile))
            connection.runtime.setEditText(str(runtime));connection.model.setEditText('openai-codex/test-model')
            connection.question.setChecked(False)
            for width in (1040,760):
                connection.resize(width,720);application.processEvents();capture(connection,'roles-'+str(width))
            connection.apply();wait(application,lambda:not connection._busy and connection._pending_sha is None)
            assert len(wb.config['experts'])==4 and wb.config['unrelated']=={'keep':True}
            policy=wb.config['runtime']['transmission']
            assert not policy['allow_question'] and policy.get('collections',[])==[]
            assert not policy.get('allow_results') and not policy.get('allow_public_search')
            connection.reject()
            official_exec=OfficialDocumentsDialog.exec
            def import_and_select(dialog):
                official_visits.append(dialog)
                deadline=time.monotonic()+20;phase=[0]
                def step():
                    if dialog._closed:return
                    if time.monotonic()>deadline:
                        errors.append('official: '+dialog.message.text());dialog.reject();return
                    if dialog.pack and not dialog._busy and phase[0]==0:
                        phase[0]=1;QTest.mouseClick(dialog.import_button,Qt.MouseButton.LeftButton)
                    elif phase[0]==1 and len(dialog.selected_imported())==3 and not dialog._busy and not dialog._active and not dialog._queue:
                        for width in (1000,740):
                            dialog.resize(width,700);application.processEvents();capture(dialog,'official-'+str(width))
                        assert all(not(item.flags()&Qt.ItemFlag.ItemIsUserCheckable) for entry,item in dialog.rows.values() if entry['availability']=='URL_ONLY')
                        assert dialog.return_button.isEnabled()
                        dialog.return_button.click()
                        assert dialog._closed and len(dialog.references)==3
                        return
                    QTimer.singleShot(20,guarded)
                def guarded():
                    try:step()
                    except Exception as error:errors.append('official: '+repr(error));dialog.reject()
                QTimer.singleShot(0,guarded)
                return official_exec(dialog)
            monkeypatch.setattr(OfficialDocumentsDialog,'exec',import_and_select)
            source_exec=SourceDialog.exec
            def choose_sources(dialog):
                source_visits.append(dialog);deadline=time.monotonic()+20;phase=[0]
                def step():
                    if dialog._closed:return
                    if time.monotonic()>deadline:
                        errors.append('source: '+dialog.message.text());dialog.reject();return
                    if not dialog._busy and phase[0]==0:
                        phase[0]=1
                        if len(source_visits)==1:dialog.choose_official()
                        else:
                            for i in range(dialog.library.topLevelItemCount()):dialog.library.topLevelItem(i).setCheckState(0,Qt.CheckState.Checked)
                    elif phase[0]==1 and not dialog._busy and len(dialog.selected())==3:
                        assert '전송' in dialog.readiness.text()
                        if len(source_visits)==1:
                            for width in (1080,760):
                                dialog.resize(width,740);application.processEvents();capture(dialog,'sources-'+str(width))
                        QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok),Qt.MouseButton.LeftButton);return
                    QTimer.singleShot(20,guarded)
                def guarded():
                    try:step()
                    except Exception as error:errors.append('source: '+repr(error));dialog.reject()
                QTimer.singleShot(0,guarded);return source_exec(dialog)
            monkeypatch.setattr(SourceDialog,'exec',choose_sources)
            team_exec=TeamReviewDialog.exec
            def configure_team(dialog):
                def edit():
                    try:
                        for i in range(dialog.roles.topLevelItemCount()):
                            item=dialog.roles.topLevelItem(i);role=item.data(0,Qt.ItemDataRole.UserRole)
                            item.setCheckState(0,Qt.CheckState.Checked if role in {'r0','r1','r2'} else Qt.CheckState.Unchecked)
                            if role not in {'r0','r1','r2'}:continue
                            dialog.roles.setCurrentItem(item)
                            dialog.question.setPlainText('공식 원문의 적용 조건을 확인하세요.')
                            for n in range(dialog.tools.count()):
                                tool=dialog.tools.item(n)
                                if tool.data(Qt.ItemDataRole.UserRole)=='knowledge.source':tool.setCheckState(Qt.CheckState.Checked)
                            dialog.select_sources()
                        dialog.deliverable.setText('설정 차이와 확인할 조건')
                        for width in (1060,800):
                            dialog.resize(width,740);application.processEvents();capture(dialog,'team-'+str(width))
                        dialog.apply()
                    except Exception as error:errors.append(str(error));dialog.reject()
                QTimer.singleShot(0,edit);return team_exec(dialog)
            monkeypatch.setattr(TeamReviewDialog,'exec',configure_team)
            window=ExpertWindow(client,poll_interval=30);window.show()
            wait(application,lambda:window.document is not None and not window._busy and len(window._registry)==4)
            window.question.setPlainText('공식 문서에서 FEM 설정과 결과 선택의 적용 조건을 검토하세요.')
            window.protocol_mode.setCurrentIndex(window.research_team.mode_index)
            window.research_team.panel.review_team()
            assert not errors,errors
            draft=window.edited_draft();team=draft['context']['research_team']
            assert team['version']==2 and {row['expert_id'] for row in team['assignments']}=={'r0','r1','r2'}
            assert all(len(row['source_refs'])==3 and row['tools']==['knowledge.source'] for row in team['assignments'])
            assert not draft['context'].get('transmission_scope',{}).get('source_refs')
            assert window.save_document()
            wait(application,lambda:not window._busy and window.document.get('saved_revision'))
            saved=client.document_read(window.document['id'])
            assert saved['draft']['context']['research_team']['assignments']==team['assignments']
            assert len(wb.manager.list())==3 and {job['operation'] for job in wb.manager.list()}=={'knowledge.ingest'}
            for job in wb.manager.list():
                entry=job['arguments']['metadata']['official_document']
                assert entry['license']['redistribution_permitted'] and entry['original_url']
            assert len(official_visits)==1 and len(source_visits)==3
        finally:
            cleanup(application,connection,*official_visits,*source_visits,window)


def test_official_lost_reply_and_partial_failure_keep_existing_jobs_and_no_blind_reimport(tmp_path,monkeypatch):
    application=app();config,_,_=initialize(tmp_path,monkeypatch)
    with transport(tmp_path,config) as (client,wb):
        original_execute=wb.manager._execute
        def execute(operation,arguments,job_id):
            if arguments.get('metadata',{}).get('official_document',{}).get('id')=='freecad-gmsh-mesh':
                raise OSError('CONTROLLED source ingestion failure')
            return original_execute(operation,arguments,job_id)
        monkeypatch.setattr(wb.manager,'_execute',execute)
        original_submit=client.submit;sent=[]
        def lost(*args,**kwargs):
            value=original_submit(*args,**kwargs);sent.append(value['id'])
            if len(sent)==1:raise OSError('CONTROLLED reply loss after admission')
            return value
        monkeypatch.setattr(client,'submit',lost)
        dialog=OfficialDocumentsDialog(client);reopened=None
        try:
            dialog.show();wait(application,lambda:dialog.pack is not None and not dialog._busy)
            dialog.start_import();wait(application,lambda:not dialog._busy and '기존 작업 확인' in dialog.message.text())
            dialog.refresh_jobs();wait(application,lambda:not dialog._busy and not dialog._active and len(dialog.selected_imported())==1)
            assert len(wb.manager.list())==1 and len(sent)==1
            dialog.start_import();wait(application,lambda:not dialog._busy and not dialog._active and not dialog._queue)
            assert len(wb.manager.list())==2 and {job['state'] for job in wb.manager.list()}=={'FAILED','SUCCEEDED'}
            records=deepcopy(wb.manager.list());dialog.reject()
            reopened=OfficialDocumentsDialog(client);reopened.show()
            wait(application,lambda:reopened.pack is not None and not reopened._busy)
            reopened.start_import();wait(application,lambda:not reopened._busy and not reopened._active and not reopened._queue)
            assert wb.manager.list()==records and len(sent)==2
            assert len(reopened.selected_imported())==1
        finally:cleanup(application,dialog,reopened)


def test_correction_saved_roles_track_applied_and_deferred_disk_save(tmp_path,monkeypatch):
    application=app();config,_,_=initialize(tmp_path,monkeypatch)
    with transport(tmp_path,config) as (client,wb):
        dialog=ConnectionDialog(client,config_path=config)
        try:
            dialog.show();wait(application,lambda:dialog.loaded and not dialog._busy)
            dialog.load_preset();dialog.apply()
            wait(application,lambda:not dialog._busy and dialog._pending_sha is None)
            saved=deepcopy(dialog.definitions)
            assert len(saved)==4 and wb.config['experts']==saved
            dialog.preset.setCurrentIndex(1);dialog.load_preset()
            assert len(dialog.definitions)==6
            dialog.preset.setCurrentIndex(2);dialog.load_preset()
            assert dialog.definitions==saved
            monkeypatch.setattr(client,'reload_expert_connection',lambda _: {'status':'DEFERRED'})
            dialog.preset.setCurrentIndex(1);dialog.load_preset();dialog.apply()
            wait(application,lambda:not dialog._busy and dialog._pending_sha is not None)
            disk=json.loads(config.read_text(encoding='utf-8'))
            assert len(disk['experts'])==6 and dialog._saved_definitions==disk['experts']
            assert wb.config['experts']==saved and wb.manager.list()==[]
        finally:cleanup(application,dialog)


def test_correction_official_checked_selection_updates_without_import():
    from examples.research_knowledge_public import load_pack,PACK
    from hashlib import sha256
    application=app();pack=load_pack();digest=sha256(PACK.read_bytes()).hexdigest()
    entries=[row for row in pack['documents'] if row['availability']=='BUNDLED']
    class CatalogClient:
        def request(self,path):
            assert path=='/api/workbench'
            return {'jobs':[{'id':str(i),'operation':'knowledge.ingest','state':'SUCCEEDED',
                'request_id':'official-pack-'+row['id']+'-'+digest[:16]} for i,row in enumerate(entries)]}
        def result(self,identifier):
            row=entries[int(identifier)];asset=next(a for a in pack['assets'] if a['path']==row['file'])
            return {'sha256':asset['sha256'],'segments_read':1,'failed_segments':[],
                    'document_id':'D'+identifier,'revision':1}
    dialog=OfficialDocumentsDialog(CatalogClient())
    try:
        dialog.show();wait(application,lambda:dialog.pack is not None and not dialog._busy)
        assert dialog.return_button.isEnabled()
        for entry,item in dialog.rows.values():
            if entry['availability']=='BUNDLED':item.setCheckState(0,Qt.CheckState.Unchecked)
        assert not dialog.return_button.isEnabled()
        dialog.refresh_jobs();wait(application,lambda:not dialog._busy)
        dialog.rows[entries[0]['id']][1].setCheckState(0,Qt.CheckState.Checked)
        assert dialog.return_button.isEnabled() and len(dialog.selected_imported())==1
        dialog.choose_imported();assert len(dialog.references)==1
    finally:cleanup(application,dialog)


def test_correction_markdown_reading_raw_and_plain_formats_preserve_original():
    from apps.research.expert_sources import SourcePreview,_reading_markdown
    from examples.research_knowledge_public import load_pack,PACK
    from caelab.assist.knowledge import read_segments
    application=app();pack=load_pack();preview=SourcePreview()
    try:
        preview.show()
        for entry in (row for row in pack['documents'] if row['availability']=='BUNDLED'):
            segments,failed=read_segments(PACK.parent/entry['file'])
            asset=next(row for row in pack['assets'] if row['path']==entry['file'])
            payload={'title':entry['title'],'sha256':asset['sha256'],'segments':segments,'failed_segments':failed}
            original=deepcopy(payload);preview.set_payload(payload)
            markdown=Path(entry['file']).suffix=='.md'
            assert preview._markdown==markdown
            if markdown:
                assert preview.pages.currentWidget() is preview.reading
                assert '<img' not in preview.reading.toPlainText()
                preview.raw.click();assert preview.text.toPlainText()==segments[0]['text']
                preview.segment.setCurrentIndex(1);assert preview.text.toPlainText()==segments[1]['text']
                preview.raw.click();assert preview.pages.currentWidget() is preview.reading
                preview.raw.click();assert preview.text.toPlainText()==segments[1]['text']
                assert not preview.reading.openLinks() and not preview.reading.openExternalLinks()
                from PySide6.QtCore import QUrl
                from PySide6.QtGui import QTextDocument
                for url in ('https://example.invalid/a.png','file:///C:/private.png'):
                    assert preview.reading.document().loadResource(QTextDocument.ResourceType.ImageResource,QUrl(url)).isEmpty()
            else:assert preview.pages.currentWidget() is preview.text
            assert preview.payload==original and payload==original
        # Format and code interpretation are not inferred from text or content_kind.
        for kind in ('source_text','extracted_text'):
            payload={'title':'보관된 텍스트','sha256':'0'*64,'segments':[{'content_kind':kind,
                'locator':{'page':1},'text':'# literal [link](file:///private) <img src="x">'}]}
            preview.set_payload(payload)
            assert preview.pages.currentWidget() is preview.text
            assert preview.text.toPlainText()==payload['segments'][0]['text']
        code='```html\n<img src="a">\n```\n`<img src="b">`\n'
        assert _reading_markdown(code)==code
        assert '보존 그림' in _reading_markdown('<img alt="보존 그림" src="file:///private">')
    finally:preview.close();preview.deleteLater();application.processEvents()


def test_correction_team_role_one_or_no_sources_reopen_without_global_selection(monkeypatch):
    from PySide6.QtWidgets import QWidget
    from apps.research.research_team_panel import TeamReviewDialog
    application=app();refs=[{'document_id':'D'+str(i),'revision':1} for i in range(3)]
    draft={'context':{'selected_sources':deepcopy(refs),'selected_document_ids':[r['document_id'] for r in refs],
        'transmission_scope':{'source_refs':deepcopy(refs)},'research_team':{'version':2,
        'assignments':[{'expert_id':'r0','source_refs':[refs[1]]},{'expert_id':'r1','source_refs':[]}]}},'composer':{}}
    original=deepcopy(draft)
    class EditingWindow(QWidget):
        client=object();document={'turns':[]};_source_titles={}
        _registry=[{'id':name,'label':name,'collections':['public'],'tools':['knowledge.source']} for name in ('r0','r1')]
        def edited_draft(self):return deepcopy(draft)
    window=EditingWindow();dialog=TeamReviewDialog(window,draft);observed=[]
    def inspect(source):
        expected=[refs[1]] if dialog._selected=='r0' else []
        assert source.initial==expected and source._selection_error is None
        assert source._context['selected_document_ids']==[r['document_id'] for r in expected]
        assert source._context['transmission_scope']==original['context']['transmission_scope']
        observed.append(deepcopy(source.initial));source.reject();return QDialog.DialogCode.Rejected
    monkeypatch.setattr(SourceDialog,'exec',inspect)
    try:
        for index in (0,0,1,1):
            dialog.roles.setCurrentItem(dialog.roles.topLevelItem(index));dialog.select_sources()
        assert observed==[[refs[1]],[refs[1]],[],[]] and draft==original
        assert dialog.assignments['r0']['source_refs']==[refs[1]]
        assert dialog.assignments['r1']['source_refs']==[]
    finally:dialog.close();window.close();dialog.deleteLater();window.deleteLater();application.processEvents()
