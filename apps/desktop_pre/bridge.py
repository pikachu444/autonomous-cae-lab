"""Typed commands for the actual open FreeCAD document, on its native GUI thread.

Uses FreeCAD's installed Qt binding. No second/headless CAD is edited behind it.
The observer callback names follow FreeCAD 1.1.4 DocumentObserverPython.cpp.
"""
from copy import deepcopy
from contextlib import contextmanager
import math
from pathlib import Path
import queue
import threading
import time
import uuid

from caelab.storage import canonical_hash, save_json
from caelab.native_transport import BrokerIO, DispatchGate
from apps.desktop_pre.mesh_binding import MeshBindingObserver
from apps.desktop_pre import metadata
from apps.desktop_pre.parameters import Parameters, OPERATIONS as PARAMETER_OPERATIONS
from apps.desktop_pre.projects import Project, OPERATIONS as PROJECT_OPERATIONS
from apps.desktop_pre.motion import Motion, OPERATIONS as MOTION_OPERATIONS
from apps.desktop_pre.fem_edit import FEMEditor, OPERATIONS as FEM_OPERATIONS
from apps.desktop_pre.research_inputs import ResearchInputs, OPERATIONS as RESEARCH_OPERATIONS


OPERATIONS = ('pre.inspect', 'pre.set_property', 'pre.set_datum', 'pre.select', 'pre.freeze', 'pre.contact.freeze', 'pre.impact.capture',
              'document.save', 'document.undo', 'document.redo', 'document.activate',
              'pre.workbench', 'pre.export_native_copy', 'pre.validate', 'pre.fem.mesh_compare') + PARAMETER_OPERATIONS + PROJECT_OPERATIONS + MOTION_OPERATIONS + FEM_OPERATIONS + RESEARCH_OPERATIONS
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
        stored = metadata.read(doc)
        self.document_id = document_id or stored.get('document_id') or 'P' + uuid.uuid4().hex
        self.session_id = 'S' + uuid.uuid4().hex
        self.export_root = Path(export_root).resolve()
        self.generation = self.view_generation = 0
        self.saved_generation = None
        self.completed = {}
        self.closed = False
        self._selection = None
        self._preview_depth = 0
        self.recovery_error = None
        self._fem_cache = None
        self.thread_id = threading.get_ident()
        self.mesh_bindings = MeshBindingObserver(doc)
        self.binding_diagnostics = {}
        self.parameters = Parameters(self)
        self.project = Project(self)
        self.motion = Motion(self)
        self.fem = FEMEditor(self)
        self.research = ResearchInputs(self)
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
        self.project.attach_opened()

    def assert_thread(self):
        if threading.get_ident() != self.thread_id:
            raise RuntimeError('Native document access requires its main thread')

    def slotChangedObject(self, obj, prop):
        if obj.Document is self.doc and not self._preview_depth:
            self.generation += 1
            if not hasattr(obj, 'FemMesh') or getattr(obj, 'Shape', None) is not None:
                self.mesh_bindings.slotChangedObject(obj, prop)
        elif obj.Document is not self.doc:
            self.project.note_dependency_change(obj.Document)

    def slotCreatedObject(self, obj):
        if obj.Document is self.doc and not self._preview_depth:
            self.generation += 1
        elif obj.Document is not self.doc:
            self.project.note_dependency_change(obj.Document)

    slotDeletedObject = slotCreatedObject

    def slotUndoDocument(self, doc):
        if doc is self.doc and not self._preview_depth:
            self.generation += 1
        elif doc is not self.doc:
            self.project.note_dependency_change(doc)

    slotRedoDocument = slotUndoDocument

    def slotFinishSaveDocument(self, doc, *unused):
        # Native saveCopy is only a prepared member. A project is saved only
        # after all dependencies and the committed .caepre file are published.
        pass

    def slotStartSaveDocument(self, doc, *unused):
        if doc is self.doc and not self.project.in_save:
            # Backup for native auto-recovery/save paths. UI Save/SaveAs/close
            # use the checked project guard, since observer exceptions alone
            # cannot veto FreeCAD's C++ save operation.
            try:
                self.motion.before_design_action('native save')
            except Exception as error:
                self.recovery_error = str(error)

    @contextmanager
    def preview_changes(self):
        self.assert_thread()
        self._preview_depth += 1
        try:
            yield
        finally:
            self._preview_depth -= 1
            self.view_generation += 1

    def read_metadata(self):
        self.assert_thread()
        return metadata.read(self.doc)

    def write_metadata(self, value):
        self.assert_thread()
        metadata.write(self.doc, dict(value, document_id=self.document_id))

    def before_design_action(self, reason):
        self.assert_thread()
        if self.fem._pending:
            raise ValueError('MESH_BUSY: finish/cancel the native mesh generation before ' + reason)
        if self.recovery_error:
            raise ValueError(self.recovery_error)
        self.motion.before_design_action(reason)
        self._idle()

    def fem_descriptor(self):
        key = (self.generation, tuple((name, value.get('cancelled')) for name, value in self.fem._pending.items()))
        if self._fem_cache is None or self._fem_cache[0] != key:
            try:
                state = self.fem.descriptor()
                state = {name: state.get(name) for name in ('regions', 'conditions', 'meshes', 'mesh_history',
                         'mesh_local_sizes', 'mesh_busy', 'active_mesh_generations', 'execution_scope', 'contact')}
            except Exception as error:
                state = {'inspection_error': str(error), 'mesh_busy': bool(self.fem._pending)}
            self._fem_cache = key, state
        return deepcopy(self._fem_cache[1])

    def slotDeletedDocument(self, doc):
        if doc is self.doc:
            self.closed = True
        else:
            self.project.note_dependency_change(doc, removed=True)

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
        try:
            motion = self.motion.descriptor()
        except Exception as error:
            motion = {'inspection_error': str(error)}
        return {'id': self.document_id, 'kind': 'pre', 'title': self.doc.Label,
                'native_document': self.doc.Name, 'working_file': self.doc.FileName,
                'generation': self.generation, 'view_generation': self.view_generation,
                'saved_generation': self.saved_generation, 'dirty': not self.project.is_saved(),
                'capabilities': list(OPERATIONS), 'objects': objects,
                'object_count': len(self.doc.Objects), 'selection': self._selection,
                'mesh_binding_diagnostics': dict(self.binding_diagnostics),
                'motion': motion, 'fem': self.fem_descriptor(), 'project': self.project.descriptor(),
                'recovery_error': self.recovery_error,
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
                if operation not in {'document.activate', 'pre.contact.cancel_rebind'}:
                    self._idle()
                readonly = {'pre.research.discover', 'pre.project.inspect', 'pre.parameters.discover', 'pre.parameters.preflight',
                            'pre.motion.inspect', 'pre.motion.path', 'pre.contact.inspect', 'pre.contact.highlight',
                            'pre.contact.preview_rebind', 'pre.contact.cancel_rebind', 'pre.contact.geometry', 'pre.contact.steps_read', 'pre.fem.mesh_quality', 'pre.fem.mesh_highlight', 'pre.fem.mesh_compare', 'pre.select'}
                if self.fem._pending and operation not in readonly | {'pre.fem.mesh_cancel', 'document.activate'}:
                    raise ValueError('MESH_BUSY: finish/cancel this native mesh generation before another design command')
                if (operation not in readonly and operation not in MOTION_OPERATIONS
                        and operation not in {'document.activate', 'pre.fem.mesh_cancel', 'pre.links.record'}):
                    self.before_design_action(operation)
                if operation in {'document.save', 'document.undo', 'document.redo', 'document.activate'}:
                    if args or target:
                        raise ValueError('This document command takes no arguments or target')
                    if operation == 'document.save':
                        payload = self.project.save()
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
                    payload = {**self.descriptor(), **({'save': payload} if operation == 'document.save' else {})}
                elif operation == 'pre.impact.capture':
                    if set(args) != {'analysis_id', 'solver_id'} or target:
                        raise ValueError('Choose an exact Analysis and mesh-reference solver')
                    from .impact_capture import capture
                    payload = capture(self, args['analysis_id'], args['solver_id'])
                elif operation in RESEARCH_OPERATIONS:
                    payload = self.research.dispatch(operation, args, target)
                elif operation in PARAMETER_OPERATIONS:
                    payload = self.parameters.dispatch(operation, args, target)
                elif operation in PROJECT_OPERATIONS:
                    payload = self.project.dispatch(operation, args, target)
                elif operation in MOTION_OPERATIONS:
                    payload = self.motion.dispatch(operation, args, target)
                elif operation == 'pre.fem.mesh_compare':
                    if set(target) != {'object_id'} or set(args) != {'history_id', 'mesh_sha256'}:
                        raise ValueError('비교할 현재 메시와 이전 메시를 선택하고 품질을 다시 조회하세요.')
                    from .mesh_quality_compare import compare_mesh_quality
                    payload = compare_mesh_quality(self.fem, self._object(target['object_id']),
                                                   args['history_id'], args['mesh_sha256'])
                elif operation in FEM_OPERATIONS:
                    payload = self.fem.dispatch(operation, args, target)
                elif operation == 'pre.workbench':
                    if set(args) != {'name'} or target or args['name'] not in {'PartWorkbench', 'PartDesignWorkbench', 'SketcherWorkbench', 'AssemblyWorkbench', 'FemWorkbench'}:
                        raise ValueError('Select a supported installed native CAD/Assembly/FEM workbench')
                    if args['name'] not in self.Gui.listWorkbenches():
                        raise ValueError('The requested native workbench is not installed')
                    self.Gui.activateWorkbench(args['name'])
                    payload = {'workbench': args['name']}
                elif operation == 'pre.export_native_copy':
                    if args or target:
                        raise ValueError('Native copy export takes no path; it creates a new private retained FCStd copy')
                    path = self.export_root / self.document_id / 'native_copies' / ('N' + uuid.uuid4().hex + '.FCStd')
                    path.parent.mkdir(parents=True, exist_ok=True)
                    self.doc.saveCopy(str(path))
                    payload = {'file': str(path), 'lab_project_saved': False,
                               'external_links_packaged': False}
                elif operation == 'pre.validate':
                    if set(args) != {'analysis_id'} or target:
                        raise ValueError('Choose an exact native Analysis')
                    diagnostics = self.fem.validate_for_run(self._object(args['analysis_id']))
                    payload = {'diagnostics': diagnostics, 'can_freeze': not diagnostics, 'engineering_release': 'UNKNOWN'}
                elif operation in {'pre.freeze', 'pre.contact.freeze'}:
                    if set(args) != {'analysis_id', 'solver_id'} or target:
                        raise ValueError('Freeze requires exact analysis_id and solver_id')
                    from apps.desktop_pre.freeze_analysis import freeze_analysis
                    diagnostics = (self.fem.validate_for_run(self._object(args['analysis_id']))
                                   if operation == 'pre.freeze' else [])
                    if diagnostics:
                        raise ValueError('FEM_INPUT_INVALID: ' + '; '.join(item['path'] + ': ' + item['message'] for item in diagnostics))
                    saved = self.project.save()
                    frozen_generation = self.generation
                    from apps.desktop_pre.nonlinear_material import uses_solid_route
                    if operation == 'pre.contact.freeze' or uses_solid_route(self._object(args['analysis_id']), self.fem._metadata()):
                        from apps.desktop_pre.freeze_contact import freeze_contact
                        manifest = freeze_contact(self._object(args['analysis_id']), self._object(args['solver_id']),
                                                  self.export_root / self.document_id, fem=self.fem)
                    else:
                        manifest = freeze_analysis(self._object(args['analysis_id']), self._object(args['solver_id']),
                                                   self.export_root / self.document_id,
                                                   binding_validator=self.mesh_bindings.validate)
                    if self.generation != frozen_generation:
                        raise ValueError('INPUT_CHANGED: design changed during native export; the prepared files remain and no run was submitted')
                    from caelab.storage import load_json
                    from caelab.native_cad import sha
                    import shutil
                    editable = manifest.parent / 'editable.caepre'
                    shutil.copyfile(saved['retained_project'], editable)
                    data = load_json(manifest)
                    data['editable_project'] = editable.name
                    data['files'].append({'relative': editable.name, 'sha256': sha(editable), 'bytes': editable.stat().st_size})
                    save_json(manifest, data)
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
                    if not obj.getDriving(index):
                        raise ValueError('Reference-only sketch constraints cannot be assigned as driving dimensions')
                    paths = {'Constraints[' + str(index) + ']', 'Constraints.' + obj.Constraints[index].Name}
                    if any(path in paths for path, _ in getattr(obj, 'ExpressionEngine', [])):
                        raise ValueError('This datum is expression-driven; edit the native expression explicitly')
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
        self.fem.close()
        if not self.closed:
            self.motion.close()
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
    owner.QtCore = QtCore
    dispatcher = GuiDispatch(owner, QtCore)
    broker = BrokerIO(dispatcher, config['service_url'], application='freecad',
                      version='.'.join(owner.App.Version()[:3]), log=log).start()
    return owner, dispatcher, broker
