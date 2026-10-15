"""Presenter + real HTTP/Core/broker checks; native publication alone is controlled.

Synthetic FCStd/CAEPRE bytes are not an actual FreeCAD or solver acceptance.
"""
from copy import deepcopy
from pathlib import Path
import threading
import os
import sys

import pytest

from apps.research.native_project_actions import NativeProjectActions, copy_from_native, retry_native_copy
from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from caelab.workbench_client import Client
from caelab.native_project_inputs import context_from_workbench, resume_target_save, _save_witness_receipt
from caelab.portable_project_native import verify_opened, _native_open_readback
from caelab.native_project_contract import _completed_save_witness
from caelab.native_cad import publish_project, KIND
from caelab.portable_project_io import fingerprint_file
from test_native_project_inputs import saved_source


class ControlledNativePublisher:
    """Only native process/materialization/Save is a double, auth broker is real."""
    def __init__(self, server, *, retained_selection=None):
        self.wb = server.workbench
        self.context = context_from_workbench(self.wb)
        self.launches, self.saves = [], []
        self.hosts = {}
        self.retained_selection=deepcopy(retained_selection)

    def launch(self, ticket):
        self.launches.append(ticket.binding.open_id)
        owner_id = ticket.binding.owner_document_id
        descriptor = {'id':owner_id, 'kind':'pre', 'title':'공개 합성 모델 (native 대역)',
            'generation':1, 'view_generation':0, 'saved_revision':None, 'graph_version':'controlled-graph',
            'dirty':True, 'capabilities':['document.save','pre.project.save','document.activate'],
            'native_open_id':ticket.binding.open_id,'native_target_id':ticket.binding.target_id,
            'native_working_root':str(ticket.binding.materialization_root)}
        host_id = 'H'+ticket.binding.open_id[1:]
        registration = self.wb.native_commands.register(host_id=host_id, session_id='S'+ticket.binding.open_id[1:],
            application='freecad', version='CONTROLLED_NOT_NATIVE', execution_mode='headless',
            documents=[descriptor], registration_nonce='n'*40)
        self.hosts[owner_id] = [registration, descriptor, ticket]
        payload = dict(open_id=ticket.binding.open_id, reference=deepcopy(ticket.binding.reference),
            target_id=ticket.binding.target_id, working_document_id=owner_id, context_session=self.wb.session_id,
            native_owner_session=registration['session_id'], native_kind='pre', status='OPENED')
        if self.retained_selection is not None:
            payload.update(selection_status='SELECTED',selection=deepcopy(self.retained_selection))
        verify_opened(self.context, ticket.binding.open_id, _native_open_readback(payload))
        return {'status':'LAUNCHED','native_boundary':'CONTROLLED_NOT_EXECUTED'}

    def stamp(self, owner_id):
        registration, descriptor, _ = self.hosts[owner_id]
        return {key: descriptor.get('id' if key=='document_id' else key) for key in
            ('document_id','kind','generation','view_generation','saved_revision','graph_version')} | {'session_id':registration['session_id']}

    def pump(self, owner_id, *, fail=False, embed_owner=False):
        auth, descriptor, ticket = self.hosts[owner_id]
        args = {key:auth[key] for key in ('session_id','host_token')}
        command = self.wb.native_commands.next(auth['host_id'], **args)['command']
        assert command and command['operation']=='document.save' and command['arguments']=={}
        self.wb.native_commands.event(auth['host_id'], event='started', command_id=command['command_id'], **args)
        if fail:
            outcome = {'state':'FAILED','error':{'message':'CONTROLLED disk full'}}
        else:
            wire = command['_target_save']
            assert set(wire)=={'prepare_command_id','save_command_id','open_id'}
            reservation = resume_target_save(self.context, wire['prepare_command_id'])
            assert reservation.save_command_id == command['command_id']
            saved = reservation.native_save_root / 'synthetic.caepre'
            original = ticket.verified_input.entry_path
            if embed_owner:
                # Keep the real saved-owner reader in the reopening path. Only
                # this synthetic native Save payload is a controlled boundary.
                import zipfile,json
                from xml.etree import ElementTree as ET
                embedded=reservation.native_save_root/'controlled-saved.FCStd'
                embedded.parent.mkdir(parents=True,exist_ok=True)
                with zipfile.ZipFile(original) as source,zipfile.ZipFile(embedded,'w') as destination:
                    for name in source.namelist():
                        data=source.read(name)
                        if name=='Document.xml':
                            tree=ET.fromstring(data)
                            obj=ET.SubElement(tree,'Object',name='CAELabProject')
                            prop=ET.SubElement(ET.SubElement(obj,'Properties'),'Property',name='Definition')
                            ET.SubElement(prop,'String',value=json.dumps({'schema':'caelab-pre-project/1','document_id':owner_id}))
                            data=ET.tostring(tree,encoding='utf-8')
                        destination.writestr(name,data)
                original=embedded
            row = {'file':'documents/part.FCStd','native_name':'part',**fingerprint_file(original)}
            manifest = {'kind':KIND,'schema_version':1,'document_id':owner_id,'revision':'RControlledNativeSave',
                'entry':row['file'],'metadata':{'document_id':owner_id},'documents':[row],'unavailable_dependencies':[]}
            publish_project(saved, manifest, {row['file']:original})
            descriptor.update(saved_revision=manifest['revision'],dirty=False,native_target_id=reservation.target_id)
            stamp = self.stamp(owner_id)
            witness = _completed_save_witness('pre', saved, owner_stamp=stamp, command_id=command['command_id'],
                publication_complete=True,source={'native_boundary':'CONTROLLED_NOT_EXECUTED'})
            receipt = _save_witness_receipt(witness, ticket.binding, _target_save=reservation)
            self.saves.append(command['command_id'])
            envelope = {'status':'COMPLETED','command_id':command['command_id'],'document_id':owner_id,
                'session_id':auth['session_id'],'result':{'native_save_receipt':receipt}}
            outcome = {'state':'SUCCEEDED','result':envelope}
        self.wb.native_commands.event(auth['host_id'], event='finished', command_id=command['command_id'],
            outcome=outcome, documents=[descriptor], **args)


@pytest.fixture
def connected(tmp_path):
    source = saved_source(tmp_path)
    server = LabHTTPServer(LabService(tmp_path/'store'),0,
        workbench_config={'workers':1,'input_roots':{'cad':str(source)}})
    thread = threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True)
    thread.start()
    client = Client('http://127.0.0.1:'+str(server.server_port))
    try:
        registration = client.native_project_register({'mode':'selected_file','native_kind':'pre',
            'root_id':'cad','relative':'part.FCStd'},command_id='CRegisterPublic')
        yield server,client,registration['reference'],source
    finally:
        server.shutdown();server.server_close();thread.join(5)
        assert not thread.is_alive()


def saved_request(ref):
    return dict(reference=deepcopy(ref),intent='saved',target_id=None,expected_head=None,selection=None,allow_partial=False)


def test_actual_http_open_readback_cancel_and_lost_save_then_head_recovery(connected,monkeypatch):
    server,client,reference,source = connected
    native = ControlledNativePublisher(server)
    actions = NativeProjectActions(client,launcher=native.launch,confirm_first_save=lambda:False)
    source_bytes = (source/'part.FCStd').read_bytes()
    opened = actions.open(saved_request(reference),command_id='COpenPublic')
    assert opened['status']=='OPENED' and opened['owner_document_id']!=reference['document_id']
    assert actions.open(saved_request(reference),command_id='COpenPublic')['open_id']==opened['open_id']
    assert len(native.launches)==1
    stamp=native.stamp(opened['owner_document_id'])
    assert actions.save(opened['open_id'],expected_stamp=stamp,expected_head=None,command_id='CCancel')['status']=='CANCELLED'
    assert not actions._saves and not native.saves and not native.context.target_saves
    actions.confirm_first_save=lambda:True
    original=client.document_command
    sent=[]
    def lost_reply(*a,**kw):
        sent.append(kw['command_id']);original(*a,**kw)
        native.pump(opened['owner_document_id'])
        raise OSError('CONTROLLED transport loss after native completion')
    monkeypatch.setattr(client,'document_command',lost_reply)
    pending=actions.save(opened['open_id'],expected_stamp=stamp,expected_head=None,command_id='CSavePublic')
    assert pending['status']=='SAVE_UNCONFIRMED' and len(sent)==len(native.saves)==1
    publish=client.native_project_save_head;publications=[]
    def lost_head(*a,**kw):
        result=publish(*a,**kw);publications.append(result)
        if len(publications)==1:raise OSError('CONTROLLED head response loss')
        return result
    monkeypatch.setattr(client,'native_project_save_head',lost_head)
    assert actions.check_save('CSavePublic')['status']=='SAVE_PUBLISHED_HEAD_PENDING'
    done=actions.check_save('CSavePublic')
    assert done['status']=='PUBLISHED' and done['head']['head_generation']==1
    assert publications[0]==done and len(sent)==len(native.saves)==1
    assert done['reference']['document_id']==opened['owner_document_id']
    assert done['head']['parent_reference']==reference
    assert (source/'part.FCStd').read_bytes()==source_bytes
    assert server.workbench.manager.list()==[]


def test_http_open_pending_never_completes_or_relaunches_and_public_authority_rejected(connected):
    from urllib.error import HTTPError
    server,client,reference,_=connected
    launches=[]
    actions=NativeProjectActions(client,launcher=lambda ticket:launches.append(ticket) or {'status':'LAUNCHED'})
    first=actions.open(saved_request(reference),command_id='CPending')
    assert first['status']=='OPEN_PENDING'
    assert actions.open(saved_request(reference),command_id='CPending')['status']=='OPEN_PENDING'
    assert len(launches)==1
    for endpoint,body in [('prepare-open',{'request':saved_request(reference),'command_id':'CExtra','ticket':{}}),
                           ('register',{'source':{'mode':'completed_native_save','command_id':'CFake'},'command_id':'CForged','receipt':{}})]:
        with pytest.raises(HTTPError):client.request('/api/workbench/native-project/'+endpoint,body)
    assert len(launches)==1 and server.workbench.manager.list()==[]


def test_actual_broker_failure_preserves_source_and_rejects_public_private_save(connected):
    from urllib.error import HTTPError
    server,client,reference,source=connected
    native=ControlledNativePublisher(server);actions=NativeProjectActions(client,launcher=native.launch,confirm_first_save=lambda:True)
    opened=actions.open(saved_request(reference),command_id='CFailOpen');stamp=native.stamp(opened['owner_document_id'])
    queued=actions.save(opened['open_id'],expected_stamp=stamp,expected_head=None,command_id='CFailSave')
    assert queued['status']=='SAVE_PENDING'
    native.pump(opened['owner_document_id'],fail=True)
    assert actions.check_save('CFailSave')['status']=='FAILED'
    assert not native.saves and not list((server.workbench.workspace/'native').glob('*/head.json'))
    with pytest.raises(HTTPError):client.document_command(opened['owner_document_id'],'document.save',
        {'_target_save':{'open_id':opened['open_id']}},session_id=stamp['session_id'],expected_generation=stamp['generation'],command_id='CForgedPrivate')
    assert (source/'part.FCStd').is_file() and server.workbench.manager.list()==[]


def test_current_working_reuses_exact_dirty_owner_and_rejects_stale_head_or_unclear_owner(connected):
    from urllib.error import HTTPError
    server,client,reference,_=connected
    old_selection={'version':1,'native_kind':'pre','snapshot_sha256':reference['snapshot_sha256'],
        'selection':{'document_member':'document0','occurrence_chain':[],'object_name':'Part','subelements':[]}}
    native=ControlledNativePublisher(server,retained_selection=old_selection)
    actions=NativeProjectActions(client,launcher=native.launch,confirm_first_save=lambda:True)
    opened=actions.open(saved_request(reference),command_id='CWorkingOrigin')
    owner_id=opened['owner_document_id'];stamp=native.stamp(owner_id)
    assert actions.save(opened['open_id'],expected_stamp=stamp,expected_head=None,command_id='CWorkingSave')['status']=='SAVE_PENDING'
    native.pump(owner_id)
    published=actions.check_save('CWorkingSave')
    assert published['status']=='PUBLISHED'
    auth,descriptor,ticket=native.hosts[owner_id]
    descriptor['dirty']=True
    def heartbeat():
        server.workbench.native_commands.event(auth['host_id'],session_id=auth['session_id'],
            host_token=auth['host_token'],event='heartbeat',documents=[descriptor])
    heartbeat()
    request=dict(reference=published['reference'],intent='working',target_id=published['target_id'],
        expected_head={'generation':1,'reference':published['reference']},selection=None,allow_partial=False)
    before_tickets=set(native.context.tickets)
    reused=actions.open(request,command_id='CWorkingActivate')
    assert reused['reuse_existing'] and reused['open_id']==opened['open_id']
    assert reused['reference']==reference and reused['request_reference']==published['reference']
    assert actions.open(request,command_id='CWorkingActivate')['owner_document_id']==owner_id
    activation=server.workbench.native_commands.next(auth['host_id'],session_id=auth['session_id'],host_token=auth['host_token'])['command']
    assert activation['operation']=='document.activate' and activation['document_id']==owner_id
    assert len(native.launches)==len(native.saves)==1 and set(native.context.tickets)==before_tickets
    assert client.document_read(owner_id)['dirty'] is True and ticket.binding.reference==reference
    stale=deepcopy(request);stale['expected_head']['generation']=0
    with pytest.raises(HTTPError):actions.open(stale,command_id='CWorkingStale')
    selected=deepcopy(request);selected['selection']=old_selection
    # Even equal retained readback does not prove the selection in a dirty
    # current owner. Do not reactivate/select/relaunch based on that old value.
    unclear=actions.open(selected,command_id='CWorkingSelection')
    assert unclear['status']=='OPEN_UNCONFIRMED' and '저장본을 별도 창' in unclear['message']
    descriptor['native_working_root']=str(ticket.binding.materialization_root.parent/'different')
    heartbeat()
    assert actions.open(request,command_id='CWorkingUnclear')['status']=='OPEN_UNCONFIRMED'
    assert set(native.context.tickets)==before_tickets and len(native.launches)==1
    assert server.workbench.manager.list()==[]


def test_copy_review_cancel_destination_cancel_and_same_publication_request(connected,tmp_path,monkeypatch):
    server,client,reference,_=connected
    inspected=[]
    actions=NativeProjectActions(client,review_copy=lambda plan:inspected.append(plan) or False,
        choose_destination=lambda:pytest.fail('Destination chooser follows approval only'))
    assert copy_from_native(actions,reference)['status']=='CANCELLED'
    assert inspected[0]['native_inspections'] and actions._copy is None
    actions.review_copy=lambda plan:True;actions.choose_destination=lambda:''
    assert copy_from_native(actions,reference)['status']=='CANCELLED' and actions._copy is None
    actions.choose_destination=lambda:tmp_path/'actual portable copy'
    original=client.portable_create;calls=[]
    def lost_once(**request):
        calls.append(deepcopy(request));result=original(**request)
        if len(calls)==1:raise OSError('CONTROLLED response loss after existing portable publication')
        return result
    monkeypatch.setattr(client,'portable_create',lost_once)
    with pytest.raises(OSError):copy_from_native(actions,reference)
    result=retry_native_copy(actions)
    assert calls[0]==calls[1] and result['status']=='ALREADY_CREATED'
    assert server.workbench.manager.list()==[]


def test_native_only_context_requires_its_existing_native_dialog_and_launcher_before_effects(connected):
    from apps.research.native_project_actions import open_native_project
    server,_,reference,_=connected
    context=context_from_workbench(server.workbench)
    with pytest.raises(ValueError,match='포함 목록과 폴더 선택'):
        copy_from_native(context,reference)
    with pytest.raises(ValueError,match='기존 열기 동작'):
        open_native_project(context,saved_request(reference),command_id='CNoNativeAdapter')
    assert not context.tickets and not context.target_saves and server.workbench.manager.list()==[]


def test_authenticated_close_allows_fresh_working_open_but_queries_and_shutdown_do_not_launch(connected):
    server,client,reference,_=connected
    native=ControlledNativePublisher(server)
    actions=NativeProjectActions(client,launcher=native.launch,confirm_first_save=lambda:True)
    opened=actions.open(saved_request(reference),command_id='CCloseSource')
    owner_id=opened['owner_document_id']
    assert actions.save(opened['open_id'],expected_stamp=native.stamp(owner_id),expected_head=None,
        command_id='CCloseSave')['status']=='SAVE_PENDING'
    native.pump(owner_id,embed_owner=True)
    published=actions.check_save('CCloseSave')
    assert published['status']=='PUBLISHED'
    auth,_,old_ticket=native.hosts[owner_id]
    server.workbench.native_commands.event(auth['host_id'],session_id=auth['session_id'],
        host_token=auth['host_token'],event='closed')
    assert client.document_read(owner_id)['owner_closed'] is True
    assert client.native_project_open_ticket(opened['open_id'])['status']=='CLOSED'
    assert actions.open(saved_request(reference),command_id='CCloseSource')['status']=='CLOSED'
    assert len(native.launches)==1
    request=dict(reference=published['reference'],intent='working',target_id=published['target_id'],
        expected_head={'generation':1,'reference':published['reference']},selection=None,allow_partial=False)
    fresh=actions.open(request,command_id='CExplicitReopenWorking')
    assert fresh['status']=='OPENED' and fresh['open_id']!=opened['open_id']
    assert fresh['owner_document_id']==owner_id and len(native.launches)==2
    assert old_ticket.binding.reference==reference
    assert client.native_project_open_ticket(opened['open_id'])['status']=='CLOSED'
    assert actions.open(saved_request(reference),command_id='CCloseSource')['status']=='CLOSED'
    assert actions.open(request,command_id='CExplicitReopenWorking')['open_id']==fresh['open_id']
    assert len(native.launches)==2
    server.workbench.native_commands.shutdown()
    assert client.document_read(owner_id)['owner_closed'] is False
    assert client.native_project_open_ticket(fresh['open_id'])['status']=='OPEN_UNCONFIRMED'
    assert actions.open(request,command_id='CAfterServiceShutdown')['status']=='OPEN_UNCONFIRMED'
    assert len(native.launches)==2 and len(native.saves)==1 and server.workbench.manager.list()==[]


def test_qwindows_closed_saved_window_needs_next_click_and_heartbeat_loss_never_relaunches(connected):
    import time
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from apps.research.reference_window import ReferenceWindow
    server,client,reference,_=connected
    app=QApplication.instance() or QApplication([])
    assert app.platformName()=='windows'
    native=ControlledNativePublisher(server)
    client._native_project_actions=NativeProjectActions(client,launcher=native.launch)
    window=ReferenceWindow(client,reference)
    def until(predicate):
        deadline=time.monotonic()+8
        while not predicate() and time.monotonic()<deadline:
            app.processEvents();time.sleep(.01)
        assert predicate()
    def click():
        QTest.mouseClick(window.open_button,Qt.MouseButton.LeftButton)
        until(lambda:not window._busy)
    try:
        window.show();until(lambda:not window._busy)
        click();assert len(native.launches)==1
        first_owner=next(iter(native.hosts));auth=native.hosts[first_owner][0]
        server.workbench.native_commands.event(auth['host_id'],session_id=auth['session_id'],
            host_token=auth['host_token'],event='closed')
        click()
        assert len(native.launches)==1 and '한 번 더' in window.message.text()
        assert not window._native_project_open_commands
        click()
        assert len(native.launches)==2 and '별도 창에서 열었습니다' in window.message.text()
        second_owner=next(item for item in native.hosts if item!=first_owner)
        second_auth=native.hosts[second_owner][0]
        host=server.workbench.native_commands._hosts[second_auth['host_id']]
        host['_seen']-=server.workbench.native_commands.timeout+1
        second_open=native.launches[-1]
        assert client.native_project_open_ticket(second_open)['status']=='OPEN_UNCONFIRMED'
        assert client.document_read(second_owner)['owner_closed'] is False
        click();click()
        assert len(native.launches)==2 and window._native_project_open_commands
        assert not native.saves and server.workbench.manager.list()==[]
    finally:
        window.close();until(lambda:not window._workers)
        window.deleteLater();app.processEvents()


def test_actual_stdio_mcp_uses_same_service_and_no_native_execution(connected):
    import asyncio
    import json
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    server,client,reference,_=connected
    async def exercise():
        params=StdioServerParameters(command=sys.executable,
            args=['-m','openscience.workbench_mcp'],
            env={**os.environ,'CAELAB_SERVICE_URL':client.url})
        async with stdio_client(params) as (reader,writer):
            async with ClientSession(reader,writer) as session:
                await session.initialize()
                names={tool.name for tool in (await session.list_tools()).tools}
                assert {'native_project_'+verb for verb in ('register','read','prepare_open','open_ticket','prepare_save','save_head')} <= names
                async def call(name,args):
                    result=await session.call_tool('native_project_'+name,args)
                    assert not result.isError,result.content
                    return result.structuredContent or json.loads(result.content[0].text)
                reread=await call('register',{'source':{'mode':'selected_file','native_kind':'pre',
                    'root_id':'cad','relative':'part.FCStd'},'command_id':'CRegisterPublic'})
                assert reread['reference']==reference
                summary=await call('read',{'reference':reference})
                assert summary['verification']=='METADATA_ONLY'
                opened=await call('prepare_open',{'request':saved_request(reference),'command_id':'CMcpOpen'})
                view=await call('open_ticket',{'open_id':opened['open_id']})
                assert view['status']=='PREPARED' and view['effects']['native_launch'] is False
                for name,args in [('prepare_save',{'open_id':view['open_id'],'expected_stamp':{},'expected_head':None,'command_id':'CMcpNoOwner'}),
                                  ('save_head',{'target_id':'KUnknown','save_command_id':'CUnknown','expected_head':None,'command_id':'CMcpNoSave'})]:
                    assert (await session.call_tool('native_project_'+name,args)).isError
    asyncio.run(exercise())
    assert server.workbench.manager.list()==[]


def test_cli_current_ticket_launches_once_without_native_and_rejects_mixed_input(connected,monkeypatch,capsys):
    import json
    from apps.research import desktop
    server,client,reference,_=connected
    prepared=client.native_project_prepare_open(saved_request(reference),command_id='CCliOpen')
    launches=[]
    def launch(command,**options):
        launches.append((command,options))
        return type('ControlledProcess',(),{'pid':12345})()
    monkeypatch.setattr(desktop.subprocess,'Popen',launch)
    args=['--service',client.url,'pre','--native-project-open-id',prepared['open_id'],'--executable',sys.executable]
    assert desktop.main(args)==0
    first=json.loads(capsys.readouterr().out)
    assert first['status']=='OPEN_PENDING' and len(launches)==1
    macro=Path(launches[0][0][-1]);config=json.loads((macro.parent/'config.json').read_text(encoding='utf-8'))
    view=client.native_project_open_ticket(prepared['open_id'])
    assert config['native_project_open']==view['launch_config'] and config['service_url']==client.url
    assert desktop.main(args)==0
    assert json.loads(capsys.readouterr().out)['status']=='OPEN_PENDING' and len(launches)==1
    with pytest.raises(ValueError,match='다른 입력'):
        desktop.main(args+['--source','do-not-read.FCStd'])
    assert server.workbench.manager.list()==[]


def test_reference_window_exact_saved_button_and_first_save_cancel_qwindows(connected):
    import time
    from PySide6.QtCore import Qt,QTimer
    from PySide6.QtWidgets import QApplication,QMessageBox
    from PySide6.QtTest import QTest
    from apps.research.appearance import apply_appearance
    from apps.research.reference_window import ReferenceWindow
    from apps.research.native_project_actions import _confirm_first_save
    server,client,reference,_=connected
    app=QApplication.instance() or QApplication([])
    apply_appearance(app)
    assert app.platformName()=='windows'
    native=ControlledNativePublisher(server)
    client._native_project_actions=NativeProjectActions(client,launcher=native.launch)
    window=ReferenceWindow(client,reference)
    def until(predicate):
        deadline=time.monotonic()+8
        while not predicate() and time.monotonic()<deadline:
            app.processEvents()
            # Release the Python GIL while the real HTTP server and Qt worker
            # run. QTest.qWait alone can starve those Python threads on Windows.
            time.sleep(.01)
        assert predicate()
    try:
        window.show();until(lambda:not window._busy)
        assert window.value['status']=='AVAILABLE' and window.open_button.isEnabled()
        QTest.mouseClick(window.open_button,Qt.MouseButton.LeftButton)
        until(lambda:not window._busy)
        assert len(native.launches)==1 and window.message.text()=='저장본을 별도 창에서 열었습니다.'
        QTest.mouseClick(window.open_button,Qt.MouseButton.LeftButton)
        until(lambda:not window._busy)
        assert len(native.launches)==1 and window.reference==reference
        output=os.environ.get('NATIVE_ACTIONS_RENDER_DIR')
        if output:
            folder=Path(output);folder.mkdir(parents=True,exist_ok=True)
            for width in (1180,800):
                window.resize(width,740);app.processEvents()
                assert window.grab().save(str(folder/('reference-'+str(width)+'.png')))
        def cancel():
            active=app.activeModalWidget()
            assert isinstance(active,QMessageBox)
            assert {'새 작업 사본으로 저장','취소'}=={button.text() for button in active.buttons()}
            if output:active.grab().save(str(Path(output)/'first-save-cancel.png'))
            QTest.keyClick(active,Qt.Key.Key_Escape)
        QTimer.singleShot(30,cancel)
        assert _confirm_first_save() is False
        assert not native.saves and not native.context.target_saves and server.workbench.manager.list()==[]
    finally:
        window.close()
        until(lambda:not window._workers)
        window.deleteLater();app.processEvents()


def test_pre_submit_generation_refusal_is_persisted_failure_and_new_explicit_save_uses_same_target(connected,monkeypatch):
    """Real HTTP/Core/broker; synthetic native publication only, no native process."""
    from caelab.storage import load_json
    server,client,reference,source=connected
    native=ControlledNativePublisher(server)
    actions=NativeProjectActions(client,launcher=native.launch,confirm_first_save=lambda:True)
    opened=actions.open(saved_request(reference),command_id='CF3Open')
    owner_id=opened['owner_document_id'];stamp=native.stamp(owner_id)
    original_bytes=(source/'part.FCStd').read_bytes()
    prepare=client.native_project_prepare_save
    def change_after_prepare(*args,**kwargs):
        value=prepare(*args,**kwargs)
        auth,descriptor,_=native.hosts[owner_id]
        descriptor['generation']+=1
        server.workbench.native_commands.event(auth['host_id'],session_id=auth['session_id'],
            host_token=auth['host_token'],event='heartbeat',documents=[descriptor])
        return value
    monkeypatch.setattr(client,'native_project_prepare_save',change_after_prepare)
    rejected=actions.save(opened['open_id'],expected_stamp=stamp,expected_head=None,command_id='CF3OldSave')
    assert rejected['status']=='FAILED' and not native.saves
    prepared=actions._saves['CF3OldSave']['prepared'];actual_id=prepared['save_command_id']
    receipt=client.command_status(actual_id)
    assert receipt['state']=='FAILED' and receipt['phase']=='NOT_DISPATCHED'
    assert receipt['native_save_invoked'] is False and receipt['expected_generation']==stamp['generation']
    journal=native.context.root/'native_project'/'target_saves'/'CF3OldSave.json'
    failed=load_json(journal)
    assert failed['state']=='FAILED_CONFIRMED' and failed['failure_stage']=='before_save'
    assert failed['native_save_invoked'] is False
    assert actions.save(opened['open_id'],expected_stamp=stamp,expected_head=None,command_id='CF3OldSave')['status']=='FAILED'
    monkeypatch.setattr(client,'native_project_prepare_save',prepare)
    next_save=actions.save(opened['open_id'],expected_stamp=native.stamp(owner_id),expected_head=None,command_id='CF3NewSave')
    assert next_save['status']=='SAVE_PENDING'
    fresh=actions._saves['CF3NewSave']['prepared']
    assert fresh['target_id']==prepared['target_id'] and fresh['save_command_id']!=actual_id
    native.pump(owner_id)
    assert actions.check_save('CF3NewSave')['status']=='PUBLISHED' and len(native.saves)==1
    assert client.command_status(actual_id)==receipt and load_json(journal)==failed
    assert (source/'part.FCStd').read_bytes()==original_bytes and server.workbench.manager.list()==[]


def test_pre_submit_wrong_request_and_existing_or_retained_command_never_release_reservation(connected):
    from urllib.error import HTTPError
    from caelab.storage import load_json
    server,client,reference,_=connected
    native=ControlledNativePublisher(server)
    actions=NativeProjectActions(client,launcher=native.launch)
    opened=actions.open(saved_request(reference),command_id='CF3ProtectOpen')
    owner_id=opened['owner_document_id'];stamp=native.stamp(owner_id)
    prepared=client.native_project_prepare_save(opened['open_id'],expected_stamp=stamp,
        expected_head=None,command_id='CF3ProtectSave')
    actual_id=prepared['save_command_id']
    journal=native.context.root/'native_project'/'target_saves'/'CF3ProtectSave.json'
    reserved=load_json(journal)
    assert reserved['state']=='RESERVED'
    for session,args,generation in [('SWrongSession',{},stamp['generation']),
                                    (stamp['session_id'],{'unexpected':True},stamp['generation']),
                                    (stamp['session_id'],{},True)]:
        with pytest.raises(HTTPError):
            client.document_command(owner_id,'pre.project.save',args,session_id=session,
                expected_generation=generation,command_id=actual_id)
        assert load_json(journal)==reserved
        with pytest.raises(HTTPError):client.command_status(actual_id)
    queued=client.document_command(owner_id,'pre.project.save',{},session_id=stamp['session_id'],
        expected_generation=stamp['generation'],command_id=actual_id)
    record=server.workbench.native_commands.root/(actual_id+'.json')
    retained_bytes=record.read_bytes()
    auth,descriptor,_=native.hosts[owner_id]
    descriptor['generation']+=1
    server.workbench.native_commands.event(auth['host_id'],session_id=auth['session_id'],
        host_token=auth['host_token'],event='heartbeat',documents=[descriptor])
    # An already admitted exact retry remains the same queued command even if
    # the current generation changed. Conflicting retries have no release power.
    assert client.document_command(owner_id,'pre.project.save',{},session_id=stamp['session_id'],
        expected_generation=stamp['generation'],command_id=actual_id)==queued
    with pytest.raises(HTTPError):client.document_command(owner_id,'pre.project.save',{},
        session_id='SWrongSession',expected_generation=stamp['generation'],command_id=actual_id)
    assert load_json(journal)==reserved and record.read_bytes()==retained_bytes
    # Simulate persistence preceding in-memory admission. A retained original
    # record is sufficient to forbid overwrite or reservation release.
    server.workbench.native_commands._commands.pop(actual_id)
    with pytest.raises(HTTPError):client.document_command(owner_id,'pre.project.save',{},
        session_id=stamp['session_id'],expected_generation=stamp['generation'],command_id=actual_id)
    assert record.read_bytes()==retained_bytes and load_json(journal)==reserved
    assert not native.saves and server.workbench.manager.list()==[]


def test_pre_submit_failure_reply_loss_uses_existing_failed_id_without_repeating_save(connected,monkeypatch):
    from urllib.error import HTTPError
    server,client,reference,_=connected
    native=ControlledNativePublisher(server)
    actions=NativeProjectActions(client,launcher=native.launch,confirm_first_save=lambda:True)
    opened=actions.open(saved_request(reference),command_id='CF3LostOpen')
    owner_id=opened['owner_document_id'];stamp=native.stamp(owner_id)
    original=client.document_command;sent=[]
    def refuse_then_lose(*args,**kwargs):
        sent.append(kwargs['command_id'])
        auth,descriptor,_=native.hosts[owner_id]
        descriptor['generation']+=1
        server.workbench.native_commands.event(auth['host_id'],session_id=auth['session_id'],
            host_token=auth['host_token'],event='heartbeat',documents=[descriptor])
        result=original(*args,**kwargs)
        assert result['state']=='FAILED' and result['native_save_invoked'] is False
        raise OSError('CONTROLLED loss after persisted NOT_DISPATCHED failure')
    monkeypatch.setattr(client,'document_command',refuse_then_lose)
    unknown=actions.save(opened['open_id'],expected_stamp=stamp,expected_head=None,command_id='CF3LostSave')
    assert unknown['status']=='SAVE_UNCONFIRMED' and len(sent)==1
    assert actions.check_save('CF3LostSave')['status']=='FAILED' and len(sent)==1 and not native.saves
    # A missing status before any server admission is UNKNOWN, never a failure
    # witness and never permission to submit this same Save a second time.
    actions2=NativeProjectActions(client,confirm_first_save=lambda:True)
    never_sent=[]
    def missing(*args,**kwargs):
        never_sent.append(kwargs['command_id'])
        raise OSError('CONTROLLED request did not reach server')
    monkeypatch.setattr(client,'document_command',missing)
    # This explicit new operation is separately reserved after proven failure.
    pending=actions2.save(opened['open_id'],expected_stamp=native.stamp(owner_id),
        expected_head=None,command_id='CF3NeverAdmitted')
    assert pending['status']=='SAVE_UNCONFIRMED'
    assert actions2.check_save('CF3NeverAdmitted')['status']=='SAVE_UNCONFIRMED'
    assert len(never_sent)==1 and not native.saves and server.workbench.manager.list()==[]
