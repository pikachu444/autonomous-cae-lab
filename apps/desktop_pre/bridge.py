"""Typed commands for the actual open FreeCAD document, on its native GUI thread.

Uses FreeCAD's installed Qt binding. No second/headless CAD is edited behind it.
The observer callback names follow FreeCAD 1.1.4 DocumentObserverPython.cpp.
"""
from copy import deepcopy
import math
from pathlib import Path
import queue
import threading
import time
import uuid

from caelab.storage import canonical_hash, save_json
from caelab.native_transport import BrokerIO, DispatchGate
from apps.desktop_pre.mesh_binding import MeshBindingObserver


OPERATIONS = ('pre.inspect', 'pre.set_property', 'pre.set_datum', 'pre.select', 'pre.freeze',
              'document.save', 'document.undo', 'document.redo', 'document.activate')
EDITABLE = {'Length', 'Length2', 'Width', 'Height', 'Radius', 'Radius1', 'Radius2',
            'Angle', 'Angle2', 'Force', 'CharacteristicLengthMax', 'CharacteristicLengthMin'}
QUANTITIES = {'App::PropertyLength', 'App::PropertyDistance', 'App::PropertyAngle', 'App::PropertyForce'}


class Owner:
    def __init__(self, doc, export_root, *, App=None, Gui=None, document_id=None):
        if App is None:
            import FreeCAD as App
        if Gui is None:
            import FreeCADGui as Gui
        self.App, self.Gui, self.doc = App, Gui, doc
        self.document_id = document_id or 'P' + uuid.uuid4().hex
        self.session_id = 'S' + uuid.uuid4().hex
        self.export_root = Path(export_root).resolve()
        self.generation = self.view_generation = 0
        self.saved_generation = None
        self.completed = {}
        self.closed = False
        self._selection = None
        self.thread_id = threading.get_ident()
        self.mesh_bindings = MeshBindingObserver(doc)
        self.binding_diagnostics = {}
        App.addDocumentObserver(self)
        for obj in doc.Objects:
            if hasattr(obj, 'FemMesh') and getattr(obj, 'Shape', None) is not None:
                try:
                    self.mesh_bindings.track(obj)
                except Exception as error:
                    # Preserve loaded native drafts, including a stale mesh.
                    # Export validates the selected mesh again and blocks it.
                    self.binding_diagnostics[obj.Name] = str(error)
        self.refresh()

    def assert_thread(self):
        if threading.get_ident() != self.thread_id:
            raise RuntimeError('Native document access requires its main thread')

    def slotChangedObject(self, obj, prop):
        if obj.Document is self.doc:
            self.generation += 1
            self.mesh_bindings.slotChangedObject(obj, prop)

    def slotCreatedObject(self, obj):
        if obj.Document is self.doc:
            self.generation += 1

    slotDeletedObject = slotCreatedObject

    def slotUndoDocument(self, doc):
        if doc is self.doc:
            self.generation += 1

    slotRedoDocument = slotUndoDocument

    def slotFinishSaveDocument(self, doc, *unused):
        if doc is self.doc:
            self.saved_generation = self.generation

    def slotDeletedDocument(self, doc):
        if doc is self.doc:
            self.closed = True

    def refresh(self):
        self.assert_thread()
        if self.closed:
            return
        selection = [(row.Object.Name, tuple(row.SubElementNames))
                     for row in self.Gui.Selection.getSelectionEx(self.doc.Name)]
        if selection != self._selection:
            self._selection = selection
            self.view_generation += 1

    def descriptor(self):
        self.assert_thread()
        if self.closed:
            return {'id': self.document_id, 'kind': 'pre', 'title': 'Closed design',
                'generation': self.generation, 'view_generation': self.view_generation, 'capabilities': []}
        objects = [{'id': obj.Name, 'label': obj.Label, 'type': obj.TypeId,
                    'state': list(obj.State)} for obj in self.doc.Objects[:200]]
        return {'id': self.document_id, 'kind': 'pre', 'title': self.doc.Label,
                'native_document': self.doc.Name, 'working_file': self.doc.FileName,
                'generation': self.generation, 'view_generation': self.view_generation,
                'saved_generation': self.saved_generation, 'dirty': self.saved_generation != self.generation,
                'capabilities': list(OPERATIONS), 'objects': objects,
                'object_count': len(self.doc.Objects), 'selection': self._selection,
                'mesh_binding_diagnostics': dict(self.binding_diagnostics),
                'pending_edit': bool(self.Gui.Control.activeDialog() or
                    (self.Gui.activeDocument() and self.Gui.activeDocument().getInEdit()))}

    def _object(self, name):
        if not isinstance(name, str):
            raise ValueError('Select an exact native object ID')
        obj = self.doc.getObject(name)
        if obj is None:
            raise ValueError('STALE_TARGET: native object no longer exists')
        return obj

    def _idle(self):
        if self.descriptor()['pending_edit']:
            raise ValueError('BUSY_EDIT: finish or cancel the native task before this command')

    def _transaction(self, title, change):
        self.doc.openTransaction(title)
        try:
            change()
            self.doc.recompute()
            self.doc.commitTransaction()
        except Exception:
            self.doc.abortTransaction()
            raise

    def dispatch(self, request):
        self.assert_thread()
        identifier = request['command_id']
        stamp = canonical_hash(request)
        if identifier in self.completed:
            old, result = self.completed[identifier]
            if old != stamp:
                raise ValueError('command_id conflicts with an earlier native request')
            return deepcopy(result)
        result = {'command_id': identifier, 'document_id': self.document_id}
        try:
            self.refresh()
            if self.closed or request['document_id'] != self.document_id or request['session_id'] != self.session_id:
                raise ValueError('STALE_SESSION: native document was closed or reopened')
            if type(request['expected_generation']) is not int or request['expected_generation'] != self.generation:
                raise ValueError('STALE_GENERATION: read the human-edited document before applying')
            operation, args, target = request['operation'], request['arguments'], request.get('target', {})
            if operation not in OPERATIONS or not isinstance(args, dict) or not isinstance(target, dict):
                raise ValueError('Unsupported native command')
            payload = None
            if operation == 'pre.inspect':
                if args or set(target) - {'object_id'}:
                    raise ValueError('Inspect accepts only an optional target.object_id')
                payload = self.descriptor()
                if target:
                    obj = self._object(target['object_id'])
                    payload['properties'] = {name: str(getattr(obj, name)) for name in obj.PropertiesList if name in EDITABLE}
                    if obj.TypeId == 'Sketcher::SketchObject':
                        payload['constraints'] = [{'index': i, 'type': value.Type, 'value': value.Value}
                                                  for i, value in enumerate(obj.Constraints)]
            else:
                if operation != 'document.activate':
                    self._idle()
                if operation in {'document.save', 'document.undo', 'document.redo', 'document.activate'}:
                    if args or target:
                        raise ValueError('This document command takes no arguments or target')
                    if operation == 'document.save':
                        if not self.doc.FileName:
                            raise ValueError('Use native Save As once to choose the editable file location')
                        self.doc.save()
                        self.saved_generation = self.generation
                    elif operation in {'document.undo', 'document.redo'}:
                        count = self.doc.UndoCount if operation.endswith('undo') else self.doc.RedoCount
                        if not count:
                            raise ValueError('No native edit is available to undo/redo')
                        getattr(self.doc, operation.split('.')[1])()
                    else:
                        if self.descriptor()['pending_edit'] and getattr(self.App, 'ActiveDocument', None) is not self.doc:
                            raise ValueError('BUSY_EDIT: cannot switch away from another document’s native task')
                        if getattr(self.App, 'ActiveDocument', None) is not self.doc:
                            self.App.setActiveDocument(self.doc.Name)
                        window = self.Gui.getMainWindow()
                        if window.isMinimized():
                            window.showNormal()
                        window.raise_()
                        window.activateWindow()
                    payload = self.descriptor()
                elif operation == 'pre.freeze':
                    if set(args) != {'analysis_id', 'solver_id'} or target:
                        raise ValueError('Freeze requires exact analysis_id and solver_id')
                    from apps.desktop_pre.freeze_analysis import freeze_analysis
                    manifest = freeze_analysis(self._object(args['analysis_id']), self._object(args['solver_id']),
                                               self.export_root / self.document_id,
                                               binding_validator=self.mesh_bindings.validate)
                    payload = {'snapshot_relative': manifest.relative_to(self.export_root).as_posix(),
                               'label': self.doc.Label + ' — ' + args['analysis_id']}
                elif operation == 'pre.select':
                    if set(args) != {'objects'} or target or not isinstance(args['objects'], list) or len(args['objects']) > 200:
                        raise ValueError('Select needs a bounded list of exact object/subelement pairs')
                    selected = []
                    for item in args['objects']:
                        if not isinstance(item, dict) or set(item) - {'object_id', 'subelement'}:
                            raise ValueError('Unknown native selection field')
                        obj, sub = self._object(item['object_id']), item.get('subelement', '')
                        if not isinstance(sub, str):
                            raise ValueError('Subelement must be an exact native name')
                        if sub:
                            obj.Shape.getElement(sub)  # Validate every target before clearing selection.
                        selected.append((obj, sub))
                    self.Gui.Selection.clearSelection()
                    for obj, sub in selected:
                        self.Gui.Selection.addSelection(obj, sub) if sub else self.Gui.Selection.addSelection(obj)
                    payload = {'selected': len(selected)}
                elif operation == 'pre.set_property':
                    if set(target) != {'object_id'} or set(args) != {'property', 'value', 'unit'}:
                        raise ValueError('Set property requires object_id, property, finite value and explicit unit')
                    obj, name = self._object(target['object_id']), args['property']
                    if (name not in EDITABLE or name not in obj.PropertiesList
                            or {'ReadOnly', 'Hidden'}.intersection(obj.getEditorMode(name))):
                        raise ValueError('Property is unsupported or read-only; use the native editor')
                    if type(args['value']) not in (int, float) or not math.isfinite(args['value']):
                        raise ValueError('A finite numeric value is required')
                    if not isinstance(args['unit'], str) or not args['unit'].strip():
                        raise ValueError('A physical unit is required')
                    if obj.getTypeIdOfProperty(name) not in QUANTITIES:
                        raise ValueError('Only declared native dimension/load quantities are supported')
                    if any(path == name for path, _ in getattr(obj, 'ExpressionEngine', [])):
                        raise ValueError('Property is expression-driven; edit the native expression explicitly')
                    value = self.App.Units.Quantity(str(args['value']) + ' ' + args['unit'])
                    if value.Unit != getattr(obj, name).Unit:
                        raise ValueError('Quantity dimension differs from the native property')
                    self._transaction('CAE Lab ' + name, lambda: setattr(obj, name, value))
                    payload = {'object_id': obj.Name, 'property': name, 'value': str(getattr(obj, name))}
                elif operation == 'pre.set_datum':
                    if set(target) != {'object_id'} or set(args) != {'constraint_index', 'value', 'unit'}:
                        raise ValueError('Sketch datum requires exact constraint_index, value and unit')
                    obj, index = self._object(target['object_id']), args['constraint_index']
                    if obj.TypeId != 'Sketcher::SketchObject' or type(index) is not int or not 0 <= index < len(obj.Constraints):
                        raise ValueError('Choose an existing sketch dimensional constraint')
                    if type(args['value']) not in (int, float) or not math.isfinite(args['value']):
                        raise ValueError('A finite numeric datum is required')
                    kinds = {'Distance','DistanceX','DistanceY','Radius','Diameter','Angle','AngleViaPoint'}
                    kind = obj.Constraints[index].Type
                    if kind not in kinds or not isinstance(args['unit'], str):
                        raise ValueError('Only native dimensional constraints can be assigned')
                    value = self.App.Units.Quantity(str(args['value']) + ' ' + args['unit'])
                    expected = self.App.Units.Quantity('1 deg' if kind.startswith('Angle') else '1 mm')
                    if value.Unit != expected.Unit:
                        raise ValueError('Datum unit does not match the native constraint')
                    self._transaction('CAE Lab sketch datum', lambda: obj.setDatum(index, value))
                    payload = {'object_id': obj.Name, 'constraint_index': index, 'value': str(obj.getDatum(index))}
                self.refresh()
            result.update(status='COMPLETED', result=payload, generation=self.generation, view_generation=self.view_generation)
        except Exception as error:
            result.update(status='FAILED', error={'type': type(error).__name__, 'message': str(error)},
                          generation=self.generation, view_generation=self.view_generation)
        self.completed[identifier] = (stamp, deepcopy(result))
        return result

    def close(self):
        self.assert_thread()
        self.App.removeDocumentObserver(self)
        self.closed = True


class GuiDispatch:
    def __init__(self, owner, QtCore):
        self.owner = owner
        self.incoming, self.outgoing = queue.Queue(maxsize=64), queue.Queue()
        self.last_tick = None
        self._last_heartbeat = 0
        self._published = None
        self.ready = False
        self.broker_stop = None
        self.command_gate = DispatchGate()
        self.timer = QtCore.QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def _tick(self):
        self.owner.assert_thread()
        if self.command_gate.executing:
            return
        if self.owner.closed:
            self.outgoing.put({'event': 'closed'})
            self.timer.stop()
            return
        if self.broker_stop is not None and self.broker_stop.is_set():
            return
        self.owner.refresh()
        self.last_tick = time.monotonic()
        descriptor = self.owner.descriptor()
        if not self.ready or descriptor != self._published or self.last_tick - self._last_heartbeat >= 1:
            self.outgoing.put({'event': 'heartbeat' if self.ready else 'ready', 'documents': [descriptor]})
            self.ready = True
            self._last_heartbeat, self._published = self.last_tick, descriptor
        if self.command_gate.request is None:
            try:
                request = self.incoming.get_nowait()
            except queue.Empty:
                return
            self.command_gate.stage(request, self.outgoing)
            return
        request = self.command_gate.take()
        if request is None:
            return
        try:
            response = self.owner.dispatch(request)
        except Exception as error:
            response = {'status': 'FAILED', 'error': {'type': type(error).__name__, 'message': str(error)}}
        outcome = {'state': 'SUCCEEDED' if response['status'] == 'COMPLETED' else 'FAILED', 'result': response}
        if response.get('error'):
            outcome['error'] = {'code': response['error']['type'], 'message': response['error']['message']}
        self.outgoing.put({'event': 'finished', 'command_id': request['command_id'], 'outcome': outcome,
                           'documents': [self.owner.descriptor()]})
        self.last_tick = time.monotonic()  # The native call really returned to its GUI.
        self.command_gate.complete()

    def close(self):
        self.outgoing.put({'event': 'closed'})
        self.timer.stop()
        self.owner.close()


def start(doc, config, QtCore, *, log=None, document_id=None):
    owner = Owner(doc, config['export_root'], document_id=document_id)
    dispatcher = GuiDispatch(owner, QtCore)
    broker = BrokerIO(dispatcher, config['service_url'], application='freecad',
                      version='.'.join(owner.App.Version()[:3]), log=log).start()
    return owner, dispatcher, broker
