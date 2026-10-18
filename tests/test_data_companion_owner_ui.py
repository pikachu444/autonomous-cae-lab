"""Explicit Data companions retain their buffer without claiming the primary owner."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QDialog,QMessageBox

from apps.research.data_window import DataWindow
from caelab.data_document import default_draft
from caelab.storage import canonical_hash


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def document():
    draft=default_draft()
    return dict(id='Tselected',kind='data',session_id='Sowner',generation=0,input_revision='Iselected',
        title='선택한 시험 자료',draft=draft,diagnostics=[],dirty=False,saved_revision=None,
        can_undo=False,can_redo=False,runs=[dict(job_id='Joriginal',input_generation=0,
            input_revision='Iselected',input_sha256=canonical_hash(draft))])


@pytest.fixture
def quiet_reads(monkeypatch):
    for name in ('refresh_preview','refresh_source_table','refresh_result','_restore_view'):
        monkeypatch.setattr(DataWindow,name,lambda *a,**k:None)


def close(window,app):
    window._allow_close=True;window.close();app.processEvents()


@pytest.mark.parametrize('task,identifier', [('other','Tselected'),('processing',None),('acquisition','Mwrong')])
def test_companion_constructor_requires_named_task_and_exact_data_id(app,task,identifier):
    with pytest.raises(ValueError):DataWindow(None,document_id=identifier,companion_task=task,auto_open=False)


def test_primary_still_binds_and_companion_is_same_document_auxiliary(app,quiet_reads,monkeypatch):
    import apps.research.result_return as returns
    bound=[];closed=[]
    monkeypatch.setattr(returns,'bind_receiver',lambda w,d:bound.append((w,d['id'])) or True)
    monkeypatch.setattr(returns,'close_receiver',lambda w:closed.append(w))
    primary=DataWindow(None,auto_open=False,poll_interval=0)
    companion=DataWindow(None,document_id='Tselected',companion_task='processing',auto_open=False,poll_interval=0)
    try:
        primary._opened(document());companion._opened(document());app.processEvents()
        assert bound==[(primary,'Tselected')]
        assert primary.windowTitle().startswith('Data — ')
        assert companion.windowTitle().startswith('자료 처리 도구 — 선택한 시험 자료')
        assert primary.new_action.isEnabled() and not companion.new_action.isEnabled()
        assert not companion.open_action.isEnabled() and not companion.open_tests_action.isEnabled()
        with pytest.raises(ValueError):companion.open_document(document_id='Tother')
        with pytest.raises(ValueError):companion.open_document(document_id='Tselected',draft=default_draft())
        with pytest.raises(ValueError):companion.open_companion_task('acquisition')
        with pytest.raises(ValueError):companion._opened({**document(),'kind':'material'})
    finally:close(companion,app);close(primary,app)
    assert closed==[companion,primary]


def test_recipe_accept_keeps_visible_auxiliary_buffer_and_close_cancel(app,quiet_reads,monkeypatch):
    from apps.research import data_processing_dialog
    class Client:
        def data_material(self,*a,**k):raise AssertionError('Recipe and cancel must not issue Core commands')
    window=DataWindow(Client(),document_id='Tselected',companion_task='processing',auto_open=False,poll_interval=0)
    before=document();window._opened(before);window.show();app.processEvents()
    source=dict(document_id='Tselected',job_id='Joriginal',input_revision='Iselected',input_sha256=canonical_hash(before['draft']))
    monkeypatch.setattr(window,'selected_source',lambda:source)
    recipe={'version':1,'operations':[]}
    class Accepted:
        def __init__(self,*a,**k):self.recipe=deepcopy(recipe)
        def exec(self):return QDialog.DialogCode.Accepted
    monkeypatch.setattr(data_processing_dialog,'DataProcessingRecipeDialog',Accepted)
    try:
        window.edit_processing_recipe();app.processEvents()
        edited=deepcopy(window.edited_draft())
        assert window.local_dirty and edited['processing']['recipe']==recipe
        assert window.document==before and window.document['draft']==before['draft']
        assert window.isVisible() and window.apply_action.isEnabled()
        # Existing leave/recovery path owns this decision; no hidden host may
        # disappear while its accepted recipe is still only a local edit.
        def cancel():
            dialog=QApplication.activeModalWidget();assert isinstance(dialog,QMessageBox);dialog.reject()
        QTimer.singleShot(0,cancel);window.close();app.processEvents()
        assert window.isVisible() and window.local_dirty and window.edited_draft()==edited
    finally:close(window,app)


@pytest.mark.parametrize('task',['processing','acquisition'])
def test_cli_explicit_companion_preserves_task_even_when_primary_is_active(monkeypatch,task):
    import apps.research.data_window as module
    import apps.research.result_return as returns
    calls=[]
    client=SimpleNamespace(document_read=lambda identifier:dict(id=identifier,kind='data'))
    monkeypatch.setattr(module,'Client',lambda url:client)
    monkeypatch.setattr(module,'QApplication',SimpleNamespace(instance=lambda:SimpleNamespace(exec=lambda:0)))
    def activation(*a,**k):raise AssertionError('Explicit companion intent must not be reduced to primary activation')
    monkeypatch.setattr(returns,'activate_existing',activation)
    class Window:
        def __init__(self,*a,**k):calls.append(('create',k))
        def show(self):calls.append(('show',))
        def open_document(self,**k):calls.append(('open',k['document_id']));k['after']()
        def open_companion_task(self,t):calls.append(('task',t))
    monkeypatch.setattr(module,'DataWindow',Window)
    assert module.main(['--service','http://local','--document-id','Tselected','--data-task',task])==0
    assert calls[0][1]['companion_task']==task and calls[0][1]['auto_open'] is False
    assert ('open','Tselected') in calls and ('task',task) in calls


def test_cli_normal_open_still_activates_without_constructing_duplicate(monkeypatch):
    import apps.research.data_window as module
    import apps.research.result_return as returns
    monkeypatch.setattr(module,'Client',lambda url:object())
    monkeypatch.setattr(module,'QApplication',SimpleNamespace(instance=lambda:object()))
    calls=[];monkeypatch.setattr(returns,'activate_existing',lambda *a,**k:calls.append(k) or {'status':'ACTIVATED'})
    monkeypatch.setattr(module,'DataWindow',lambda *a,**k:pytest.fail('Primary activation must not construct another DataWindow'))
    assert module.main(['--service','http://local','--document-id','Tselected'])==0
    assert calls==[{'kind':'data'}]


@pytest.mark.parametrize('identifier,kind',[('Mwrong','material'),('Tselected','material')])
def test_cli_companion_wrong_owner_is_rejected_before_window(monkeypatch,identifier,kind):
    import apps.research.data_window as module
    monkeypatch.setattr(module,'Client',lambda url:SimpleNamespace(document_read=lambda i:{'id':i,'kind':kind}))
    monkeypatch.setattr(module,'QApplication',SimpleNamespace(instance=lambda:object()))
    monkeypatch.setattr(module,'DataWindow',lambda *a,**k:pytest.fail('Wrong kind must not open a companion'))
    with pytest.raises(ValueError):module.main(['--service','http://local','--document-id',identifier,'--data-task','processing'])
