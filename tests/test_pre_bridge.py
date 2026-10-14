"""FreeCAD-shaped owner/GUI protocol doubles; no native app/process is started.

Observer names/signatures mirror FreeCAD's App/DocumentObserverPython.h and
App/DocumentObserverPython.cpp (slotChangedObject, created/deleted object,
Undo/RedoDocument, FinishSaveDocument(document, filename), DeletedDocument).
These checks establish routing and ownership, not native geometry acceptance.
"""
from copy import deepcopy
from pathlib import Path
import queue
import sys
import threading
from types import SimpleNamespace as NS

import pytest

from apps.desktop_pre.bridge import Owner, GuiDispatch


class Quantity:
    dimensions={'mm':'length','cm':'length','m':'length','N':'force','kN':'force','deg':'angle','rad':'angle','s':'time'}
    def __init__(self, text):
        self.Value, self.symbol=str(text).split()
        self.Value=float(self.Value)
        if self.symbol not in self.dimensions:
            raise ValueError('unsupported test quantity')
        self.Unit=self.dimensions[self.symbol]
    def __str__(self):
        return f'{self.Value:g} {self.symbol}'


class Object:
    def __init__(self, doc, name, kind='Part::Feature', **quantities):
        self.Document,self.Name,self.Label,self.TypeId=doc,name,name,kind
        self.State=[]
        self.PropertiesList=list(quantities)
        self.ExpressionEngine=[]
        self.editor_modes={}
        self.property_types={name:('App::PropertyForce' if value.Unit=='force' else 'App::PropertyLength') for name,value in quantities.items()}
        for key,value in quantities.items():
            object.__setattr__(self,key,value)
    def __setattr__(self,name,value):
        object.__setattr__(self,name,value)
        if name in self.__dict__.get('PropertiesList',[]):
            self.Document.app.changed(self,name)
    def getEditorMode(self,name):
        return self.editor_modes.get(name,[])
    def getTypeIdOfProperty(self,name):
        return self.property_types[name]


@pytest.fixture
def native(tmp_path):
    app=NS(observers=[],active=None,Units=NS(Quantity=Quantity))
    app.addDocumentObserver=lambda observer:app.observers.append(observer)
    app.removeDocumentObserver=lambda observer:app.observers.remove(observer)
    app.setActiveDocument=lambda name:setattr(app,'active',name)
    def changed(obj,prop):
        for observer in list(app.observers):
            observer.slotChangedObject(obj,prop)
    app.changed=changed
    doc=NS(Name='UserDoc',Label='User design',FileName=str(tmp_path/'user.FCStd'),Objects=[],transactions=[],UndoCount=1,RedoCount=1)
    doc.app=app
    doc.openTransaction=lambda title:doc.transactions.append(('open',title))
    doc.recompute=lambda:doc.transactions.append(('recompute',))
    doc.commitTransaction=lambda:doc.transactions.append(('commit',))
    doc.abortTransaction=lambda:doc.transactions.append(('abort',))
    doc.getObject=lambda name:next((obj for obj in doc.Objects if obj.Name==name),None)
    def save():
        for observer in app.observers:
            observer.slotFinishSaveDocument(doc,doc.FileName)
    def undo():
        for observer in app.observers:
            observer.slotUndoDocument(doc)
    def redo():
        for observer in app.observers:
            observer.slotRedoDocument(doc)
    doc.save,doc.undo,doc.redo=save,undo,redo
    dimension=Object(doc,'Pad',Length=Quantity('10 mm'))
    force=Object(doc,'Load','Fem::ConstraintForce',Force=Quantity('20 N'))
    sketch=Object(doc,'Sketch','Sketcher::SketchObject')
    sketch.Constraints=[NS(Type='Distance',Value=5,Name=''),NS(Type='Coincident',Value=0,Name=''),NS(Type='Angle',Value=.2,Name='')]
    sketch.getDriving=lambda index:True
    sketch.datums={0:Quantity('5 mm'),2:Quantity('10 deg')}
    def set_datum(index,value):
        sketch.datums[index]=value
        app.changed(sketch,'Constraints')
    sketch.setDatum=set_datum
    sketch.getDatum=lambda index:sketch.datums[index]
    analysis=Object(doc,'Analysis','Fem::FemAnalysis')
    solver=Object(doc,'Solver','Fem::SolverCcxTools')
    # Mirror the actual native Analysis membership used by freeze routing.
    analysis.Group=[solver, force]
    solver.MaterialNonlinearity='linear'
    solver.GeometricalNonlinearity='linear'
    doc.Objects=[dimension,force,sketch,analysis,solver]
    selection=NS(rows=[])
    selection.getSelectionEx=lambda name:list(selection.rows)
    selection.clearSelection=lambda:selection.rows.clear()
    selection.addSelection=lambda obj,sub='':selection.rows.append(NS(Object=obj,SubElementNames=[sub] if sub else []))
    gui=NS(Selection=selection,Control=NS(activeDialog=lambda:False),activeDocument=lambda:NS(getInEdit=lambda:False))
    gui.window=NS(calls=[],isMinimized=lambda:True)
    for name in ('showNormal','raise_','activateWindow'):
        setattr(gui.window,name,lambda name=name:gui.window.calls.append(name))
    gui.getMainWindow=lambda:gui.window
    owner=Owner(doc,tmp_path/'exchange',App=app,Gui=gui,document_id='Pdesign')
    yield NS(app=app,gui=gui,doc=doc,owner=owner,pad=dimension,force=force,sketch=sketch,analysis=analysis,solver=solver)
    if owner in app.observers:
        owner.close()


def request(native,operation='pre.set_property',arguments=None,target=None,**overrides):
    return {'command_id':'Cedit','document_id':native.owner.document_id,'session_id':native.owner.session_id,
        'expected_generation':native.owner.generation,'operation':operation,
        'arguments':arguments if arguments is not None else {'property':'Length','value':25,'unit':'mm'},
        'target':target if target is not None else {'object_id':'Pad'},**overrides}


def test_mesh_comparison_routes_without_design_change(native, monkeypatch):
    from apps.desktop_pre import mesh_quality_compare
    from caelab.native_commands import CAPABILITIES
    mesh = Object(native.doc, 'MeshGmsh', 'Fem::FemMeshGmsh')
    native.doc.Objects.append(mesh)
    calls = []
    def compare(editor, selected, history_id, expected_hash):
        calls.append((editor, selected, history_id, expected_hash))
        return {'history_id': history_id, 'mesh_id': selected.Name}
    monkeypatch.setattr(mesh_quality_compare, 'compare_mesh_quality', compare)
    def reject_design_change(operation):
        raise AssertionError('A quality comparison must not change the design')
    native.owner.before_design_action = reject_design_change
    generation = native.owner.generation
    response = native.owner.dispatch(request(native, 'pre.fem.mesh_compare',
        {'history_id': 'Gprevious', 'mesh_sha256': 'a' * 64}, {'object_id': mesh.Name}))
    assert 'pre.fem.mesh_compare' in CAPABILITIES['pre']
    assert response['status'] == 'COMPLETED', response
    assert calls == [(native.owner.fem, mesh, 'Gprevious', 'a' * 64)]
    assert native.owner.generation == generation and native.doc.transactions == []
    invalid = native.owner.dispatch(request(native, 'pre.fem.mesh_compare',
        {'history_id': 'Gprevious'}, {'object_id': mesh.Name}, command_id='Cinvalid'))
    assert invalid['status'] == 'FAILED' and len(calls) == 1


def test_mesh_view_routes_without_design_edit_and_closes_with_owner(native, monkeypatch):
    from caelab.native_commands import CAPABILITIES
    calls = []
    def dispatch(owner, arguments, target):
        calls.append((owner, arguments, target))
        return {'mesh_id': target['object_id'], 'element_ids': arguments['element_ids']}
    monkeypatch.setitem(sys.modules, 'apps.desktop_pre.mesh_element_view', NS(dispatch=dispatch))
    native.owner.before_design_action = lambda _: pytest.fail('Element view changed the design')
    generation = native.owner.generation
    args = {'mode': 'isolate', 'element_ids': [3, 17], 'mesh_sha256': 'a' * 64}
    target = {'object_id': 'MeshGmsh'}
    response = native.owner.dispatch(request(native, 'pre.fem.mesh_view', args, target))
    assert 'pre.fem.mesh_view' in CAPABILITIES['pre']
    assert response['status'] == 'COMPLETED', response
    assert calls == [(native.owner, args, target)]
    assert native.owner.generation == generation and native.doc.transactions == []
    stale = native.owner.dispatch(request(native, 'pre.fem.mesh_view', args, target,
        command_id='Cstale', expected_generation=generation + 1))
    assert stale['status'] == 'FAILED' and len(calls) == 1
    closed = []
    native.owner._mesh_element_view = NS(close=lambda: closed.append(True))
    native.owner.close()
    assert closed == [True] and native.owner not in native.app.observers


def test_design_action_restores_transient_element_view_before_native_edit(native):
    calls = []
    native.owner._mesh_element_view = NS(restore=lambda: calls.append('restore'), close=lambda: None)
    native.owner.before_design_action('pre.fem.mesh_generate')
    assert calls == ['restore'] and native.doc.transactions == []


def test_human_changes_observer_lifecycle_and_saved_state(native):
    owner=native.owner
    assert owner in native.app.observers
    old=owner.generation
    native.pad.Length=Quantity('12 mm')  # Native human property edit callback.
    inspected=owner.dispatch(request(native,'pre.inspect',{},{}))
    assert inspected['status']=='COMPLETED' and inspected['result']['generation']==old+1
    assert inspected['result']['dirty']
    owner.slotCreatedObject(native.force)
    owner.slotDeletedObject(native.force)
    owner.slotUndoDocument(native.doc)
    owner.slotRedoDocument(native.doc)
    assert owner.generation==old+5
    owner.slotFinishSaveDocument(native.doc,native.doc.FileName)
    assert owner.descriptor()['dirty']  # Native saveCopy/FinishSave is not Lab publication.
    foreign=NS(Document=NS(Name='Unrelated', Objects=[]))
    owner.slotChangedObject(foreign,'Length')
    assert owner.generation==old+5
    owner.slotDeletedDocument(native.doc)
    assert owner.descriptor()['capabilities']==[]


def test_open_pre_document_registers_all_native_operations(native,tmp_path):
    from caelab.native_commands import NativeCommands
    owner = native.owner
    broker = NativeCommands(tmp_path/'service', 'Sservice')
    registered = broker.register(host_id='Hpre',session_id=owner.session_id,
        application='freecad',version='1.1.4',execution_mode='gui',
        documents=[owner.descriptor()],registration_nonce='n'*32)
    identity = {key:registered[key] for key in ('session_id','host_token')}
    broker.submit(document_id=owner.document_id,operation='pre.inspect',arguments={},
        session_id=owner.session_id,expected_generation=owner.generation,command_id='Cinspect')
    dispatched = broker.next('Hpre',**identity)['command']
    outcome = owner.dispatch(dispatched)
    assert outcome['status'] == 'COMPLETED'
    assert 'pre.impact.capture' in outcome['result']['capabilities']
    owner.close()
    assert owner not in native.app.observers


@pytest.mark.parametrize('object_id,property_name,value,unit',[('Pad','Length',25,'mm'),('Load','Force',50,'N')])
def test_real_owner_transaction_and_idempotent_same_request(native,object_id,property_name,value,unit):
    command=request(native,arguments={'property':property_name,'value':value,'unit':unit},target={'object_id':object_id})
    first=native.owner.dispatch(command)
    assert first['status']=='COMPLETED'
    assert native.doc.transactions==[('open','CAE Lab '+property_name),('recompute',),('commit',)]
    assert first['generation']==1
    assert native.owner.dispatch(deepcopy(command))==first
    assert len(native.doc.transactions)==3
    conflicting={**command,'arguments':{**command['arguments'],'value':value+1}}
    with pytest.raises(ValueError,match='conflicts'):
        native.owner.dispatch(conflicting)
    assert len(native.doc.transactions)==3


@pytest.mark.parametrize('variation,message',[('stale','STALE_GENERATION'),('wrong_unit','dimension'),('unknown_target','STALE_TARGET'),('unknown_property','unsupported'),('bool_value','finite'),('read_only','read-only'),('hidden','read-only'),('expression','expression-driven'),('pending_edit','BUSY_EDIT')])
def test_invalid_edits_are_rejected_before_native_mutation(native,variation,message):
    command=request(native)
    if variation=='stale':
        native.pad.Length=Quantity('15 mm')
    elif variation=='wrong_unit':
        command['arguments']['unit']='N'
    elif variation=='unknown_target':
        command['target']['object_id']='Gone'
    elif variation=='unknown_property':
        command['arguments']['property']='Placement'
    elif variation=='bool_value':
        command['arguments']['value']=True
    elif variation=='read_only':
        native.pad.editor_modes['Length']=['ReadOnly']
    elif variation=='hidden':
        native.pad.editor_modes['Length']=['Hidden']
    elif variation=='expression':
        native.pad.ExpressionEngine=[('Length','Other.Length')]
    elif variation=='pending_edit':
        native.gui.Control.activeDialog=lambda:True
    before=str(native.pad.Length)
    result=native.owner.dispatch(command)
    assert result['status']=='FAILED' and message in result['error']['message']
    assert native.doc.transactions==[] and str(native.pad.Length)==before


def test_sketch_datum_uses_native_quantity_and_transaction(native):
    command=request(native,'pre.set_datum',{'constraint_index':0,'value':8,'unit':'mm'},{'object_id':'Sketch'})
    result=native.owner.dispatch(command)
    assert result['status']=='COMPLETED' and str(native.sketch.getDatum(0))=='8 mm'
    assert native.doc.transactions==[('open','CAE Lab sketch datum'),('recompute',),('commit',)]
    command=request(native,'pre.set_datum',{'constraint_index':2,'value':2,'unit':'mm'},{'object_id':'Sketch'},command_id='Cwrong')
    assert 'unit' in native.owner.dispatch(command)['error']['message']
    assert len(native.doc.transactions)==3


def test_transaction_aborts_on_native_exception(native):
    def failed_recompute():
        raise RuntimeError('native recompute failed')
    native.doc.recompute=failed_recompute
    result=native.owner.dispatch(request(native))
    assert result['status']=='FAILED'
    assert native.doc.transactions==[('open','CAE Lab Length'),('abort',)]


def test_freeze_receipt_keeps_export_path_and_does_not_resubmit(native,monkeypatch):
    saved = native.owner.export_root / 'retained.caepre'
    saved.parent.mkdir(parents=True)
    saved.write_bytes(b'native-project-double')
    monkeypatch.setattr(native.owner.project, 'save', lambda: {'retained_project': str(saved)})
    monkeypatch.setattr(native.owner.fem, 'validate_for_run', lambda analysis: [])
    calls=[]
    def freeze(analysis,solver,root,*,binding_validator=None):
        assert binding_validator == native.owner.mesh_bindings.validate
        assert analysis is native.analysis and solver is native.solver
        path=root/'Fretained'/'snapshot.json'
        from caelab.storage import save_json
        save_json(path, {'files': []})
        calls.append((analysis,solver,root))
        return path
    monkeypatch.setattr('apps.desktop_pre.freeze_analysis.freeze_analysis',freeze)
    command=request(native,'pre.freeze',{'analysis_id':'Analysis','solver_id':'Solver'},{})
    result=native.owner.dispatch(command)
    assert result['status']=='COMPLETED'
    assert result['result']['snapshot_relative']=='Pdesign/Fretained/snapshot.json'
    assert native.owner.dispatch(command)==result and len(calls)==1
    assert not native.doc.transactions


def test_owner_rejects_off_thread_native_access(native):
    errors=[]
    def other_thread():
        for action in (native.owner.descriptor,lambda:native.owner.dispatch(request(native)),native.owner.close):
            try:
                action()
            except Exception as error:
                errors.append(error)
    thread=threading.Thread(target=other_thread)
    thread.start();thread.join()
    assert len(errors)==3 and all('main thread' in str(error) for error in errors)
    assert native.doc.transactions==[] and native.owner in native.app.observers


def test_return_to_current_design_preserves_native_task_and_window_size(native):
    native.app.ActiveDocument = native.doc
    native.gui.Control.activeDialog = lambda: True
    native.gui.window.isMinimized = lambda: False
    result = native.owner.dispatch(request(native, 'document.activate', {}, {}))
    assert result['status'] == 'COMPLETED'
    assert native.gui.window.calls == ['raise_', 'activateWindow']
    assert native.doc.transactions == [] and native.app.active is None
    native.app.ActiveDocument = NS(Name='OtherEditingDocument')
    rejected = native.owner.dispatch(request(native, 'document.activate', {}, {}, command_id='Cother'))
    assert rejected['status'] == 'FAILED' and 'BUSY_EDIT' in rejected['error']['message']


class Timer:
    def __init__(self):
        self.timeout=NS(connect=lambda callback:setattr(self,'callback',callback))
        self.running=False
    def setInterval(self,value):
        self.interval=value
    def start(self):
        self.running=True
    def stop(self):
        self.running=False


def drain(dispatch):
    events=[]
    while not dispatch.outgoing.empty():
        events.append(dispatch.outgoing.get_nowait())
    return events


def test_gui_dispatch_publishes_human_changes_and_finished_protocol(native):
    dispatch=GuiDispatch(native.owner,NS(QTimer=Timer))
    dispatch._tick()
    ready=drain(dispatch)
    assert ready[0]['event']=='ready' and dispatch.last_tick is not None
    assert ready[0]['documents'][0]['generation']==0
    native.pad.Length=Quantity('13 mm')
    dispatch._tick()
    assert drain(dispatch)[0]['documents'][0]['generation']==1
    dispatch.incoming.put(request(native))
    dispatch._tick()
    events=drain(dispatch)
    assert [event['event'] for event in events]==['started']
    assert native.doc.transactions == []
    dispatch.command_gate.acknowledge_started('Cedit')
    dispatch._tick()
    events += drain(dispatch)
    assert [event['event'] for event in events]==['started','finished']
    assert events[-1]['outcome']['state']=='SUCCEEDED'
    assert events[-1]['documents'][0]['generation']==2
    dispatch.broker_stop=threading.Event()
    dispatch.broker_stop.set()
    dispatch.incoming.put(request(native,command_id='Cstopped'))
    dispatch._tick()
    assert len(native.doc.transactions)==3 and dispatch.incoming.qsize()==1
    dispatch.close()
    assert not dispatch.timer.running and native.owner not in native.app.observers


def test_gui_dispatch_reports_rejection_and_document_close(native):
    dispatch=GuiDispatch(native.owner,NS(QTimer=Timer))
    dispatch._tick();drain(dispatch)
    dispatch.incoming.put(request(native,expected_generation=99))
    dispatch._tick()
    dispatch.command_gate.acknowledge_started('Cedit')
    dispatch._tick()
    events=drain(dispatch)
    finished=events[-1]
    assert finished['outcome']['state']=='FAILED'
    assert 'STALE_GENERATION' in finished['outcome']['error']['message']
    native.owner.slotDeletedDocument(native.doc)
    dispatch._tick()
    assert drain(dispatch)==[{'event':'closed'}]
    assert not dispatch.timer.running
    dispatch.close()
    assert native.owner not in native.app.observers


def test_stopped_broker_does_not_accumulate_undeliverable_heartbeats(native,monkeypatch):
    dispatch=GuiDispatch(native.owner,NS(QTimer=Timer))
    dispatch._tick();drain(dispatch)
    dispatch.broker_stop=threading.Event()
    dispatch.broker_stop.set()
    times=iter([100,102,104,106,108])
    monkeypatch.setattr('apps.desktop_pre.bridge.time.monotonic',lambda:next(times))
    dispatch._last_heartbeat=0
    for _ in range(5):
        dispatch._tick()
    assert dispatch.outgoing.qsize()==0
    assert native.doc.transactions==[]
    dispatch.close()


def test_connection_does_not_reuse_identity_for_a_different_unsaved_document(tmp_path,monkeypatch):
    from apps.desktop_pre.connection import Connection
    document=NS(Name='Unnamed',Label='New unsaved model',FileName='',getObject=lambda name:None)
    captured=[]
    def start(doc,config,QtCore,**options):
        captured.append(options.get('document_id'))
        owner=NS(document_id=options.get('document_id') or 'Pnew',doc=doc,generation=0,closed=False)
        return owner,NS(close=lambda:None),NS(stop=threading.Event(),registered=threading.Event())
    monkeypatch.setattr('apps.desktop_pre.connection.bridge.start',start)
    connection=Connection.__new__(Connection)
    connection.closed=False
    connection.replies=queue.Queue()
    connection.working=set()
    connection.pending=None
    connection.records={'Unnamed':{'id':'Pold','working_file':''}}
    connection.owners={}
    connection.native_requests={}
    connection.panels={}
    connection.project_path=tmp_path/'native_documents.json'
    connection.App=NS(listDocuments=lambda:{'Unnamed':document},ActiveDocument=document)
    connection.config={}
    connection.QtCore=None
    connection.log=lambda *args,**kwargs:None
    connection.identity=NS(setText=lambda text:None)
    for name in ('run_button','export_button','cancel_button','retry_button'):
        setattr(connection,name,NS(setEnabled=lambda value:None))
    connection.tick()
    assert captured==[None]
    assert connection.records['Unnamed']['id']=='Pnew'


def test_long_freeze_waits_for_start_receipt_then_reports_once(native, tmp_path, monkeypatch):
    """Real broker thread/service state + native-shaped writer; no native run."""
    from caelab.native_commands import NativeCommands
    from caelab.native_transport import BrokerIO
    from caelab.workbench_client import Client
    from caelab.storage import save_json
    saved = tmp_path / 'retained.caepre'
    saved.write_bytes(b'native-project-double')
    monkeypatch.setattr(native.owner.project, 'save', lambda: {'retained_project': str(saved)})
    monkeypatch.setattr(native.owner.fem, 'validate_for_run', lambda analysis: [])
    clock = [100.0]
    monkeypatch.setattr('caelab.native_commands.time.monotonic', lambda: clock[0])
    service = NativeCommands(tmp_path / 'service', 'Sservice')
    dispatch = GuiDispatch(native.owner, NS(QTimer=Timer))
    transport = BrokerIO(dispatch, 'http://127.0.0.1:8766', application='freecad', version='TEST_ONLY')
    contacted, finished = threading.Event(), threading.Event()
    events, calls = [], []
    def http(client, path, body=None):
        if path.endswith('/register'):
            return service.register(**body)
        if path.endswith('/commands/next'):
            response = service.next(transport.host_id, **body)
            if clock[0] == 129:
                contacted.set()
            return response
        if path.endswith('/events'):
            events.append((clock[0], body['event']))
            response = service.event(transport.host_id, **body)
            if body['event'] == 'finished':
                finished.set()
            return response
        raise AssertionError(path)
    monkeypatch.setattr(Client, 'request', http)
    def writer(analysis, solver, root, **kwargs):
        calls.append((analysis, solver))
        assert service.status('Clong')['phase'] == 'APPLYING'
        assert transport.active_command_id == 'Clong'
        clock[0] = 129
        assert contacted.wait(2)  # Worker remains alive; native GUI cannot tick.
        clock[0] = 131
        waiting = service.status('Clong')
        assert waiting['owner_status']['dispatcher_status'] == 'APPLYING_UNCONFIRMED'
        assert service._hosts[transport.host_id]['_seen'] == 100
        transport.require_tick()
        dispatch._tick()  # A native nested loop must not publish fake progress/reenter.
        assert dispatch.last_tick == 100 and not any(kind == 'heartbeat' for _, kind in events)
        manifest = root / 'Flong' / 'snapshot.json'
        save_json(manifest, {'files': []})
        return manifest
    monkeypatch.setattr('apps.desktop_pre.freeze_analysis.freeze_analysis', writer)
    try:
        dispatch._tick()
        transport.start()
        assert transport.registered.wait(2)
        service.submit('Pdesign', 'pre.freeze', {'analysis_id': 'Analysis', 'solver_id': 'Solver'},
                       session_id=native.owner.session_id, expected_generation=0, command_id='Clong')
        queued = dispatch.incoming.get(timeout=2)
        dispatch.incoming.put(queued)
        dispatch._tick()
        assert calls == []  # A published start is not yet permission to apply.
        assert dispatch.command_gate.started.wait(2)
        dispatch._tick()
        assert finished.wait(2)
        result = service.status('Clong')
        assert result['state'] == 'SUCCEEDED', result
        assert result['final_generation'] == native.owner.generation
        assert len(calls) == 1 and [kind for _, kind in events] == ['started', 'finished']
        assert service.submit('Pdesign', 'pre.freeze', {'analysis_id': 'Analysis', 'solver_id': 'Solver'},
                              session_id=native.owner.session_id, expected_generation=0, command_id='Clong') == result
    finally:
        dispatch.close()
        transport.worker.join(timeout=2)
        if transport.worker.is_alive():
            transport.stop.set()
            transport.worker.join(timeout=2)
