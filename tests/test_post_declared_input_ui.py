"""Declared file selection/registration and exact native display commands; no solver."""
from copy import deepcopy
import json
import time
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from PySide6.QtWidgets import QInputDialog
from apps.research import desktop, post_source_dialogs
from caelab.workbench import Workbench
from test_research_post_ui import app, window, wait
from test_desktop_navigation import client, processes, post_install
from test_beam_post_bundle import produced as beam_produced
from test_shell_post_admission import produced as shell_produced


@pytest.mark.parametrize('kind',['beam','shell'])
def test_qt_picker_registers_declared_bundle_in_existing_source_add(app,window,tmp_path,monkeypatch,kind,beam_produced,shell_produced):
    entry=beam_produced[1] if kind=='beam' else shell_produced[0]
    filename=kind+'_inspection.json'
    wb=Workbench.__new__(Workbench);wb.root=tmp_path/'registered';wb.config={'input_roots':{'approved':str(entry.parent)}}
    registered=[]
    window.client.local_inputs=lambda *a,**k:{'entries':[
        {'name':filename,'relative':filename,'directory':False},
        {'name':'unrelated.json','relative':'unrelated.json','directory':False}]}
    def register(root,relative):
        receipt=wb.register_local_input(root,relative);registered.append(receipt);return receipt
    window.client.register_local_input=register
    def choose(*args,**kwargs):
        assert filename in args[3] and 'unrelated.json' not in args[3]
        return filename,True
    monkeypatch.setattr(QInputDialog,'getItem',choose)
    window._choose_directory('approved')
    deadline=time.monotonic()+45
    while time.monotonic()<deadline and not (window.client.calls and window._pending is None and not window._busy):
        app.processEvents();time.sleep(.005)
    assert window.client.calls and window._pending is None and not window._busy,window.message.text()
    receipt=registered[0]
    assert receipt['native_metadata'][kind+'_inspection']['relative']==filename
    assert window.client.calls[-1][1:] == ('post.source_add',{'input_id':receipt['id']})
    resolved=wb.native_input(receipt['id'])
    assert resolved['native_metadata']==receipt['native_metadata'] and resolved['source_pins']


@pytest.mark.parametrize('filename',['beam_inspection.json','shell_inspection.json','contact-inspection.json'])
def test_changed_source_picker_can_choose_each_declared_manifest(app,window,tmp_path,monkeypatch,filename):
    from test_post_source_update import original_source
    source=original_source();window._sources()[0].update(source);window._source_ref=source['source_ref']
    window.client.local_roots=lambda:{'roots':[{'id':'approved'}]}
    window.client.desktop_context=lambda:{'export_root':str(tmp_path)}
    window.client.local_inputs=lambda *a,**k:{'entries':[{'name':filename,'relative':filename,'directory':False}]}
    monkeypatch.setattr(QInputDialog,'getItem',lambda *a,**k:(filename,True))
    dialog=post_source_dialogs.SourceUpdateDialog(window,source);dialog.show()
    wait(app,lambda:not dialog._busy and dialog.roots.count()==1)
    dialog.file_button.click();wait(app,lambda:dialog.file.text()==filename)
    assert dialog.preview is None and not window.client.calls
    dialog.reject()


def test_standalone_post_inspection_uses_existing_registered_native_prepare(client,processes,tmp_path,monkeypatch,beam_produced):
    post_install(client,tmp_path)
    manifest=beam_produced[1].parent/'beam_inspection.json'
    wb=Workbench.__new__(Workbench);wb.root=tmp_path/'registered';wb.workspace_id='Wfixture'
    wb.config={'input_roots':{'approved':str(manifest.parent)}}
    client.local_roots=wb.local_roots;client.local_inputs=wb.local_inputs;client.register_local_input=wb.register_local_input
    monkeypatch.setattr(desktop,'_choose_file',lambda *a:manifest)
    monkeypatch.setattr(QInputDialog,'getItem',lambda *a,**k:('beam_inspection.json' if 'beam_inspection.json' in a[3] else a[3][0],True))
    prepared=[]
    def prepare(command,**kwargs):
        prepared.append(command);assert '--registered-input' in command and '--service-url' in command
        identifier=command[command.index('--registered-input')+1]
        receipt=wb.native_input(identifier);assert 'beam_inspection' in receipt['native_metadata'] and receipt['source_pins']
        folder=Path(command[3]);folder.mkdir();(folder/'state.pvsm').write_text('Explicit native state double')
        (folder/'project.json').write_text(json.dumps({'kind':'external-result','workspace_file':'state.pvsm'}))
        return NS(returncode=0)
    monkeypatch.setattr(desktop.subprocess,'run',prepare)
    original=manifest.read_bytes();result=desktop._post(client,desktop._arguments(['--service',client.url,'post']))
    assert result['status']=='LAUNCHED' and len(prepared)==len(processes)==1 and manifest.read_bytes()==original


@pytest.mark.parametrize('component',[None,'UX'])
def test_field_selection_display_uses_exact_native_source_view_and_component(app,window,component):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    doc=window.client.document;doc['capabilities']=['post.select_array']
    doc['state'].update(views=[{'view_id':'Vexact','type':'RenderView'}],active_view_id='Vexact')
    item={'name':'M1' if component is None else 'U_mm','association':'POINTS','components':1 if component is None else 3,
          'component_names':['M1'] if component is None else ['UX','UY','UZ'],'units':'Nmm' if component is None else 'mm'}
    if component is None:item.update(measure='section_moment',quantity='1축 굽힘 모멘트')
    doc['state']['analysis']['sources'][0]['native_metadata']['arrays']=[item]
    window._show_document(deepcopy(doc),preserve_buffer=True)
    window._source_ref='Sfirst';window._tree_selection=('source','Sfirst');window._show_arrays();window._update_actions()
    window.array_table.setFocus();window.array_table.setCurrentCell(0,0);QTest.keyClick(window.array_table,Qt.Key.Key_Space)
    window.array_table.selectRow(0)
    if component:window.array_component.setCurrentIndex(window.array_component.findData(component))
    assert window.select_array_button.isEnabled()
    if component is None:assert '1축 굽힘 모멘트' in window.array_description.text()
    window._show_arrays() # Same-source polling must preserve the chosen component.
    if component:assert window.array_component.currentData()==component
    window.select_array_button.click();wait(app,lambda:window.client.calls and not window._busy and window._pending is None)
    args={'association':'POINTS','array':item['name'],'target':{'source_id':'101','view_id':'Vexact'}}
    if component:args['component']=component
    assert window.client.calls[-1][1:] == ('post.select_array',args) and 'time' not in args


def test_unknown_vector_names_require_native_field_inspection(app,window):
    window._fill_arrays([{'name':'external','association':'POINTS','components':3}]);window.array_table.selectRow(0)
    assert not window.array_component.count() and not window.select_array_button.isEnabled()
    assert '필드 정보 읽기' in window.array_description.text() and not window.client.calls


@pytest.mark.parametrize('as_mapping',[False,True])
def test_inspected_component_names_survive_polling_only_for_same_owner_generation(app,window,as_mapping):
    doc=window.client.document
    declared={'name':'U_mm','association':'POINTS','components':3,'units':'mm'}
    source=doc['state']['analysis']['sources'][0]
    source['native_metadata']['arrays']={'U_mm':declared} if as_mapping else [declared]
    source['metadata']['arrays']=[{**declared,'component_names':['UX','UY','UZ']}]
    window._show_document(deepcopy(doc),preserve_buffer=True);window._source_ref='Sfirst';window._show_arrays()
    assert window.inspect_source();wait(app,lambda:not window._busy and window._pending is None)
    window.array_table.selectRow(0);window.array_component.setCurrentIndex(window.array_component.findData('UY'))
    window._show_arrays();assert window.array_component.currentData()=='UY'
    window.document['generation']+=1;window._show_arrays()
    assert not window.array_component.count()


@pytest.mark.parametrize('cancel',[False,True])
def test_standalone_declared_mismatch_or_cancel_preserves_source_and_never_prepares(client,processes,tmp_path,monkeypatch,cancel):
    post_install(client,tmp_path)
    selected=tmp_path/'beam_inspection.json';selected.write_text('{}');original=selected.read_bytes()
    client.local_roots=lambda:{'roots':[{'id':'approved'}]}
    client.local_inputs=lambda *a,**k:{'entries':[{'name':selected.name,'relative':selected.name,'directory':False}]}
    registered=[]
    def register(*args):
        registered.append(args)
        return {'id':'Dwrong','native_metadata':{'beam_inspection':{'relative':selected.name,'bytes':2,'sha256':'0'*64}}}
    client.register_local_input=register
    monkeypatch.setattr(desktop,'_choose_file',lambda *a:selected)
    monkeypatch.setattr(QInputDialog,'getItem',lambda *a,**k:(a[3][0],not cancel))
    with pytest.raises(ValueError,match='취소' if cancel else '다릅니다'):
        desktop._post(client,desktop._arguments(['--service',client.url,'post']))
    assert selected.read_bytes()==original and not processes and not Path(client.context['export_root']).exists()
    assert bool(registered)==(not cancel)
