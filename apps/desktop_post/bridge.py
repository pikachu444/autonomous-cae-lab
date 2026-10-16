"""Typed in-process ParaView commands; native proxies stay on their owner thread.

The GUI dispatch uses its existing QVTKInteractor's native Qt timer, never a
foreign Qt binding or a second/headless ParaView process.
"""
import json
import math
import os
from pathlib import Path
import queue
import secrets
import threading
import time
import uuid
from copy import deepcopy

from caelab.native_transport import DispatchGate

from paraview import simple as p

try:
    from . import commands, external
except ImportError:
    import commands
    import external


OPERATIONS = ("post.inspect", "post.select_array", "document.save")


def proxy_id(proxy):
    return proxy.SMProxy.GetGlobalIDAsString()


def value(data):
    if hasattr(data, "SMProxy"):
        return {"proxy_id": proxy_id(data)}
    if isinstance(data, (list, tuple)):
        return [value(item) for item in data]
    if isinstance(data, float) and not math.isfinite(data):
        return None
    if data is None or isinstance(data, (bool, int, float, str)):
        return data
    return str(data)


def properties(proxy):
    applied, pending = {}, []
    for name in proxy.ListProperties():
        prop = proxy.GetProperty(name)
        native = prop.SMProperty
        if native.GetInformationOnly():
            continue
        if hasattr(prop, "GetData"):
            applied[name] = value(prop.GetData())
        # Native Properties stores un-applied vector edits as unchecked elements.
        if hasattr(native, "GetNumberOfUncheckedElements") and hasattr(native, "GetNumberOfElements"):
            count = native.GetNumberOfUncheckedElements()
            if count and (count != native.GetNumberOfElements() or
                          any(native.GetUncheckedElement(i) != native.GetElement(i) for i in range(count))):
                pending.append(name)
        if hasattr(native, "GetNumberOfUncheckedProxies") and hasattr(native, "GetNumberOfProxies"):
            count = native.GetNumberOfUncheckedProxies()
            if count and (count != native.GetNumberOfProxies() or
                          any(native.GetUncheckedProxy(i) != native.GetProxy(i) for i in range(count))):
                pending.append(name)
    return applied, pending


class Owner:
    def __init__(self, document_id=None, session_id=None, *, _portable_binding=None):
        if _portable_binding is not None:
            try:
                from .portable_project import validate_binding
            except ImportError:
                from portable_project import validate_binding
            validate_binding(_portable_binding)
        self.portable_binding = _portable_binding
        self.native_target_id = _portable_binding.target_id if _portable_binding is not None else None
        self.thread = threading.get_ident()
        self.session_id = session_id or "S" + uuid.uuid4().hex
        path, doc = commands.project()
        if doc.get("kind") != external.KIND:
            raise ValueError("The current Post bridge supports independent external-result documents")
        self.document_id = document_id or doc.get("document_id") or "D" + uuid.uuid4().hex
        self.project_root = Path(doc.get("project_root", path.parent)).resolve()
        self.project_path = Path(path)
        self.project_document = deepcopy(doc)
        if hasattr(external, 'recovery_records') and external.recovery_records():
            self.project_document['repair'] = external.recovery_records()
            self.project_document['partial_workspace'] = True
        try:
            from .naming import document_title
        except ImportError:
            from naming import document_title
        self.title = document_title(doc, path.parent.name)
        self.generation = doc.get("generation", 0)
        self.view_generation = doc.get("view_generation", 0)
        self.source_reference = deepcopy(_portable_binding.reference) if _portable_binding is not None else None
        self.source_native_revision = (_portable_binding.verified_input.snapshot.get('native_revision')
                                       if _portable_binding is not None else None)
        local_saved = _portable_binding is None
        if _portable_binding is not None and _portable_binding.intent == 'working':
            # N0 validates DERIVED_BASE at generation 0 and NATIVE_SAVED above 0.
            local_saved = _portable_binding.expected_head['generation'] > 0
            if local_saved and _portable_binding.verified_input.snapshot['source_document_id'] != self.document_id:
                raise ValueError('STALE_TARGET: saved native head belongs to another document')
        self.saved_revision = ((self.source_native_revision if _portable_binding is not None else doc.get('workspace_sha256'))
                               if local_saved else None)
        self.saved_generation = self.generation if local_saved else None
        self.saved_view_generation = self.view_generation if local_saved else None
        self._content = None
        self._view = None
        self._observers = {}
        self.closed = False
        self.completed = {}
        self.native_completed_saves = {}
        self.modified_events = 0
        self.workspace = None
        if 'sources' in doc:
            try:
                from .workspace import Workspace
            except ImportError:
                from workspace import Workspace
            self.workspace = Workspace(self, self.project_document)
            self.workspace.restore_selection()
        self.refresh()

    native_properties = staticmethod(properties)
    proxy_id = staticmethod(proxy_id)

    def current_project(self):
        self.assert_thread()
        return self.project_path, deepcopy(self.project_document)

    def operations(self):
        activation = ('document.activate',) if callable(getattr(self, '_activate_origin_window', None)) else ()
        if self.workspace is None:
            return OPERATIONS + activation
        try:
            from .workspace import OPERATIONS as extra
        except ImportError:
            from workspace import OPERATIONS as extra
        return OPERATIONS + extra + activation

    def assert_thread(self):
        if threading.get_ident() != self.thread:
            raise RuntimeError("Native ParaView proxies must be accessed on their owner thread")

    def refresh(self):
        self.assert_thread()
        if self.closed:
            raise RuntimeError('STALE_DOCUMENT: the native Post session is closed')
        sources = {}
        content = {}
        for (label, _), source in p.GetSources().items():
            identifier = proxy_id(source)
            props, pending = properties(source)
            sources[identifier] = {"source_id": identifier, "label": label, "reader": source.GetXMLName(), "properties": props, "pending_properties": pending}
            content[identifier] = props
            if identifier not in self._observers:
                # This observer notices native human Apply/Undo; snapshots always re-read.
                tag = source.SMProxy.AddObserver("PropertyModifiedEvent", lambda *_args, item=source: self._modified(item))
                self._observers[identifier] = (source.SMProxy, tag)
        for identifier in set(self._observers) - set(sources):
            native, tag = self._observers.pop(identifier)
            native.RemoveObserver(tag)
        views = {}
        for view in p.GetViews():
            identifier = proxy_id(view)
            props, pending = properties(view)
            views[identifier] = {"view_id": identifier, "type": view.GetXMLName(), "properties": props, "pending_properties": pending}
        representations = {}
        for representation in p.GetRepresentations().values():
            props, pending = properties(representation)
            representations[proxy_id(representation)] = {"properties": props, "pending_properties": pending}
            lookup = getattr(representation, "LookupTable", None)
            if lookup is not None:
                props, pending = properties(lookup)
                representations[proxy_id(lookup)] = {"properties": props, "pending_properties": pending}
        view_state = {"views": views, "representations": representations,
                      "time": float(p.GetAnimationScene().AnimationTime),
                      "active_source_id": None if p.GetActiveSource() is None else proxy_id(p.GetActiveSource()),
                      "active_view_id": None if p.GetActiveView() is None else proxy_id(p.GetActiveView())}
        if self._content is not None and content != self._content:
            self.generation += 1
        if self._view is not None and view_state != self._view:
            self.view_generation += 1
        self._content, self._view = content, view_state
        self.snapshot = {"document_id": self.document_id, "session_id": self.session_id,
                         "generation": self.generation, "view_generation": self.view_generation,
                         "pid": os.getpid(), "sources": list(sources.values()), "views": list(views.values()),
                         "representations": representations, "time": view_state["time"],
                         "active_source_id": view_state["active_source_id"], "active_view_id": view_state["active_view_id"],
                         "fresh": True, "supports": list(self.operations()), "supports_cancel": "queued_only"}
        if self.workspace is not None:
            self.snapshot['analysis'] = self.workspace.describe()
        return self.snapshot

    def _modified(self, source):
        self.assert_thread()
        if self.closed:
            return
        self.modified_events += 1
        if self._content is not None:
            identifier = proxy_id(source)
            try:
                applied, _ = properties(source)
            except (ValueError, RuntimeError):
                # Native vector properties emit events while their domain is
                # being rebuilt (e.g. array-name/status pairs are half written).
                # Retain the checked edit in CAS; the next normal refresh still
                # strictly reads the completed native properties or fails.
                self.generation += 1
                return
            if self._content.get(identifier) != applied:
                # Observe each checked edit/Undo even if two edits happen between ticks.
                self._content[identifier] = applied
                self.generation += 1

    def close(self):
        self.assert_thread()
        self.closed = True
        self._activate_origin_window = None
        self._confirm_partial_history_save = None
        for identifier, (native, tag) in list(self._observers.items()):
            native.RemoveObserver(tag)
            self._observers.pop(identifier)

    def descriptor(self):
        self.assert_thread()
        from caelab.native_post_dependencies import digest
        return {"id": self.document_id, "kind": "post", "title": self.title,
                "generation": self.generation, "view_generation": self.view_generation,
                "dirty": (self.generation != self.saved_generation or self.view_generation != self.saved_view_generation),
                "saved_revision": self.saved_revision, "graph_version": digest([
                    {key: row[key] for key in ('label', 'reader', 'properties')} for row in self.snapshot['sources']]),
                "native_open_id": self.portable_binding.open_id if self.portable_binding else None,
                "native_target_id": self.native_target_id,
                "native_source_reference": deepcopy(self.source_reference),
                "native_source_revision": self.source_native_revision,
                "native_working_root": str(self.portable_binding.materialization_root) if self.portable_binding else None,
                "capabilities": list(self.operations()), "state": self.snapshot}

    def save_project(self, *, _target_save=None, _history_plan=None):
        """Complete the same managed save for human macros and typed commands."""
        try:
            self.refresh()
            save_root = self.project_root
            if _target_save is not None:
                from caelab.native_project_contract import require_target_save
                from apps.desktop_post.portable_project import _stamp
                require_target_save(_target_save)
                if (self.portable_binding is None or _target_save.open_id != self.portable_binding.open_id
                        or _target_save.owner_document_id != self.document_id or _target_save.expected_stamp != _stamp(self)
                        or _target_save.source_reference != self.portable_binding.reference):
                    raise ValueError('STALE_DOCUMENT: native Save reservation belongs to another current owner')
                save_root = _target_save.native_save_root.parent
            elif (self.portable_binding is not None and self.portable_binding.intent == 'saved'
                  and self.native_target_id is None):
                raise ValueError('FIRST_SAVE_TARGET_REQUIRED: choose a new working project before saving this imported snapshot')
            if any(item["pending_properties"] for item in self.snapshot["sources"] + self.snapshot["views"] + list(self.snapshot["representations"].values())):
                raise ValueError("BUSY_EDIT: native properties contain unapplied changes")
            # External save verifies the healthy sources and retained analysis, and
            # preserves unavailable branches with explicit repair records. A global
            # source check here would make a partially recovered document unsavable.
            path, doc = commands.project()
            if (doc.get("kind") != external.KIND or doc.get("document_id", self.document_id) != self.document_id
                    or Path(doc.get("project_root", path.parent)).resolve() != self.project_root):
                raise ValueError("STALE_DOCUMENT: managed save belongs to a different document")
            if self.workspace is not None:
                self.workspace.prepare_for_save()
                self.refresh()
            generation, view_generation = self.generation, self.view_generation
            source_doc = self.project_document if self.workspace is not None else doc
            options = {'prepare': lambda document, folder: self.workspace.prepare_save(document, folder,
                _history_plan=_history_plan)} if self.workspace is not None else {}
            if self.workspace is not None or self.portable_binding is not None:
                options['_history_owner'] = self
        except Exception as error:
            from apps.desktop_post.portable_project import _record_definite_save_failure
            _record_definite_save_failure(self, _target_save, error, stage='before_save')
            raise
        attempt = {'phase': 'INVOKED', 'command_id': _target_save.save_command_id if _target_save is not None else None}
        self._native_save_attempt = attempt
        try:
            saved = external.save_project(path, dict(source_doc, document_id=self.document_id, title=self.title, project_root=str(save_root),
                                                    generation=generation, view_generation=view_generation), **options)
        except Exception as error:
            if attempt['phase'] == 'INVOKED':
                from apps.desktop_post.portable_project import _record_definite_save_failure
                _record_definite_save_failure(self, _target_save, error, stage='native_save')
            # PUBLISHED means native Save completed before this error. Preserve
            # its path/reservation as unknown; never turn it into a retryable Save.
            raise
        attempt.update(phase='RETURNED', saved_file=str(saved))
        saved_doc = json.loads(saved.read_text(encoding="utf-8"))
        revision = saved_doc["workspace_sha256"]
        self.project_path = Path(saved)
        self.project_root = Path(save_root)
        if _target_save is not None:
            self.native_target_id = _target_save.target_id
        self.project_document.clear()
        self.project_document.update(saved_doc)
        self.refresh()
        # Publish save completion only after the native save and manifest succeed.
        self.saved_revision = revision
        self.saved_generation, self.saved_view_generation = generation, view_generation
        if self.workspace is not None:
            finalized = {tuple(row['history'][key] for key in ('object_ref', 'revision_id', 'revision_sha256'))
                         for row in saved_doc.get('native_relocation_basis', {}).get('histories', [])}
            self.workspace._new_history_keys.difference_update(finalized)
        attempt['phase'] = 'COMPLETED'
        return saved

    def dispatch(self, request):
        self.assert_thread()
        stamp = json.dumps(request, sort_keys=True, allow_nan=False)
        identifier = request.get("command_id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("A command_id is required")
        if identifier in self.completed:
            previous, result = self.completed[identifier]
            if stamp != previous:
                raise ValueError("A command_id cannot be reused with different content")
            return result
        self.refresh()
        result = {"command_id": identifier, "document_id": self.document_id, "session_id": self.session_id,
                  "generation": self.generation, "view_generation": self.view_generation, "supports_cancel": "queued_only"}
        save_entered = False
        try:
            if request.get("document_id") != self.document_id or request.get("session_id") != self.session_id:
                raise ValueError("STALE_DOCUMENT: wrong document or owner session")
            expected = request.get("expected_generation")
            if type(expected) is not int or expected != self.generation:
                raise ValueError("STALE_DOCUMENT: generation changed")
            operation = request.get("operation")
            if operation not in self.operations():
                raise ValueError("UNSUPPORTED_COMMAND: " + str(operation))
            arguments = request.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be an object")
            target = request.get("target", {})
            if not isinstance(target, dict):
                raise ValueError("target must be an object")
            source = None
            if operation in ("post.inspect", "post.select_array") and target.get("source_id") is not None:
                source = next((item for item in p.GetSources().values() if proxy_id(item) == target["source_id"]), None)
                if source is None:
                    raise ValueError("STALE_TARGET: source no longer exists")
            if operation == "post.inspect":
                if arguments:
                    raise ValueError("post.inspect takes no arguments; use explicit selection to change time")
                payload = self.refresh().copy()
                if source is not None:
                    available = external.times(source)
                    if available and float(p.GetAnimationScene().AnimationTime) not in available:
                        raise ValueError("TIME_SELECTION_UNSUPPORTED: select an exact native frame before inspecting its values")
                    payload["data"] = external.inspect_result(source)
            elif operation == 'document.activate':
                if arguments or target:
                    raise ValueError('document.activate uses only the authenticated current owner window')
                payload = self._activate_origin_window()
                self.refresh()
            elif operation not in OPERATIONS:
                if target:
                    raise ValueError('Analysis commands use stable source_ref/object_ref arguments')
                payload = self.workspace.dispatch(operation, arguments)
                self.refresh()
            else:
                if any(item["pending_properties"] for item in self.snapshot["sources"] + self.snapshot["views"] + list(self.snapshot["representations"].values())):
                    raise ValueError("BUSY_EDIT: native properties contain unapplied changes")
                if operation == "document.save":
                    if arguments or target:
                        raise ValueError("document.save uses the managed document save location")
                    target_save = None
                    wire = request.get('_target_save')
                    if wire is not None:
                        if (not isinstance(wire, dict) or set(wire) != {'prepare_command_id', 'save_command_id', 'open_id'}
                                or wire['save_command_id'] != identifier or self.portable_binding is None
                                or wire['open_id'] != self.portable_binding.open_id):
                            raise ValueError('STALE_DOCUMENT: invalid current native Save reservation')
                        from caelab.native_project_inputs import resume_target_save
                        context = getattr(self, 'native_project_context', None)
                        if context is None:
                            raise ValueError('Current native open context is required for Save')
                        target_save = resume_target_save(context, wire['prepare_command_id'])
                        if target_save.save_command_id != identifier or target_save.open_id != wire['open_id']:
                            raise ValueError('STALE_DOCUMENT: native Save reservation differs')
                    history_plan = None
                    unavailable = [row for row in self.project_document.get('native_history_availability', {}).get('histories', [])
                                   if row['state'] == 'UNAVAILABLE_DECLARED']
                    if unavailable and self.portable_binding is not None:
                        from apps.desktop_post.portable_project import prepare_history_save, _stamp, _expect
                        history_plan = prepare_history_save(self, expected_stamp=_stamp(self), preserve_unavailable=True)
                        confirm = getattr(self, '_confirm_partial_history_save', None)
                        if confirm is None or confirm(deepcopy(unavailable)) is not True:
                            message = ('USER_CANCELLED: 누락 분석의 과거 기록 보관을 취소했습니다.' if confirm is not None else
                                'HISTORY_CONFIRMATION_REQUIRED: 현재 ParaView 창에서 누락 분석의 과거 기록 보관을 확인한 뒤 다시 저장하세요.')
                            raise ValueError(message)
                        _expect(self, history_plan.owner_stamp)
                    save_entered = True
                    if target_save is not None or history_plan is not None:
                        saved = self.save_project(_target_save=target_save, _history_plan=history_plan)
                    else:
                        saved = self.save_project()
                    save_receipt = None
                    if self.portable_binding is not None:
                        try:
                            from .portable_project import record_completed_save
                        except ImportError:
                            from portable_project import record_completed_save
                        witness = record_completed_save(self, saved, identifier)
                        from caelab.native_project_inputs import _save_witness_receipt
                        save_receipt = _save_witness_receipt(witness, self.portable_binding, _target_save=target_save)
                    payload = {"project": str(saved), "document_id": self.document_id}
                    if save_receipt is not None:
                        payload['native_save_receipt'] = save_receipt
                else:
                    if source is None:
                        raise ValueError("post.select_array requires an exact source_id")
                    view = next((item for item in p.GetViews() if proxy_id(item) == target.get("view_id") and item.GetXMLName() == "RenderView"), None)
                    if view is None:
                        raise ValueError("STALE_TARGET: select an exact native RenderView ID")
                    if set(arguments) - {"association", "array", "component", "time"} or not {"association", "array"} <= set(arguments):
                        raise ValueError("post.select_array requires association/array and optional component/time")
                    payload = external.select_array(source, view=view, **arguments)
                    p.Render(view)
                self.refresh()
            result.update(status="COMPLETED", result=payload, generation=self.generation, view_generation=self.view_generation)
        except Exception as error:
            if not save_entered:
                from apps.desktop_post.portable_project import _reject_reserved_save_before_effect
                _reject_reserved_save_before_effect(self, request, error)
            self.refresh()
            result.update(status="FAILED", error={"type": type(error).__name__, "message": str(error)}, generation=self.generation, view_generation=self.view_generation)
        self.completed[identifier] = (stamp, result)
        return result


class GuiDispatch:
    """I/O queues carry plain messages; only the native timer accesses proxies."""
    def __init__(self, owner):
        self.owner = owner
        self.incoming = queue.Queue(maxsize=64)
        self.outgoing = queue.Queue()
        self.interactor = None
        self.timer = None
        self.observer = None
        self.ticks = 0
        self.ready = False
        self._published = None
        self.last_tick = None
        self._last_heartbeat = None
        self.broker_stop = None
        self.command_gate = DispatchGate()
        self.native_controls = None
        self.native_exit = None
        self.closed = False
        self.broker_close = None

    def install(self, interval=100):
        self.owner.assert_thread()
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("GUI_DISPATCH_UNAVAILABLE: installation must run on the native main thread")
        view = next((view for view in p.GetViews() if view.GetXMLName() == "RenderView"), None)
        interactor = None if view is None else view.SMProxy.GetInteractor()
        if interactor is None or not interactor.IsA("QVTKInteractor"):
            raise RuntimeError("GUI_DISPATCH_UNAVAILABLE: a native GUI QVTKInteractor is required; headless execution cannot control a GUI")
        self.interactor = interactor
        self.observer = interactor.AddObserver("TimerEvent", self._tick)
        self.timer = interactor.CreateRepeatingTimer(interval)
        if not self.timer:
            interactor.RemoveObserver(self.observer)
            self.observer = None
            raise RuntimeError("GUI_DISPATCH_UNAVAILABLE: native Qt interactor timer creation failed")
        try:
            if __package__:
                from .native_controls import install
            else:
                from native_controls import install
            self.native_controls = install(self.owner, busy=lambda: self.command_gate.executing,
                                           on_closed=self.close)
            if self.native_controls is not None:
                if __package__:
                    from .curve_origin_native import activate_window
                else:
                    from curve_origin_native import activate_window
                self.owner._activate_origin_window = lambda: activate_window(self.owner, self.native_controls)
                self.owner._confirm_partial_history_save = self._confirm_partial_history_save
        except Exception as error:
            print('프로젝트 저장 단축키 연결을 준비하지 못했습니다. 저장 매크로를 사용하세요. '+str(error))
        try:
            if __package__:
                from .native_exit import install as install_exit
            else:
                from native_exit import install as install_exit
            self.native_exit = install_exit(self)
        except Exception as error:
            print('native 전체 종료 보호 설치 실패: File > Exit/Ctrl+Q는 보호되지 않습니다. '
                  '기존 X/Alt+F4/저장 매크로를 사용하세요. '+str(error))
        return self

    def _confirm_partial_history_save(self, rows):
        self.owner.assert_thread()
        controls = self.native_controls
        if controls is None or controls.closed or controls.in_action or not controls.main:
            return False
        lines = []
        for row in rows:
            title = self.owner.workspace.object(row['history']['object_ref']).get('title', '분석')
            names = [Path(item['expected_child']['relative']).name for item in row['missing'] if item.get('expected_child')]
            lines.append(title + ': ' + ', '.join(names))
        controls.in_action = True
        try:
            return controls.platform.confirm_save(controls.main,
                '다음 파일이 없는 분석을 과거 기록으로 함께 저장할까요?\n\n' + '\n'.join(lines)
                + '\n\n원 기록과 누락 목록을 보존합니다. 원값을 복구하기 전에는 검증된 결과로 사용할 수 없습니다.')
        finally:
            controls.in_action = False

    def _tick(self, *_):
        self.owner.assert_thread()
        if self.closed:
            return
        if self.native_controls is not None:
            try:
                self.native_controls.refresh()
            except Exception as error:
                self.owner._activate_origin_window = None
                self.owner._confirm_partial_history_save = None
                self.native_controls.close()
                self.native_controls = None
                print('프로젝트 저장 단축키 연결을 준비하지 못했습니다. 저장 매크로를 사용하세요. '+str(error))
        if self.native_controls is not None or self.native_exit is not None:
            if ((self.native_controls is not None and self.native_controls.in_action) or
                    (self.native_exit is not None and self.native_exit.in_action)):
                # Modal close/save choices keep transport alive but cannot run queued edits.
                self.last_tick = time.monotonic()
                if self.ready and self.last_tick - self._last_heartbeat >= 1:
                    self.outgoing.put({'event':'heartbeat','documents':[self.owner.descriptor()]})
                    self._last_heartbeat = self.last_tick
                return
        if self.command_gate.executing:
            return
        if self.broker_stop is not None and self.broker_stop.is_set():
            return
        self.ticks += 1
        self.last_tick = time.monotonic()
        self.owner.refresh()
        descriptor = self.owner.descriptor()
        if not self.ready:
            self.ready = True
            self.outgoing.put({"event": "ready", "documents": [descriptor]})
            self._last_heartbeat = self.last_tick
        elif descriptor != self._published or self.last_tick - self._last_heartbeat >= 1:
            self.outgoing.put({"event": "heartbeat", "documents": [descriptor]})
            self._last_heartbeat = self.last_tick
        self._published = descriptor
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
            result = self.owner.dispatch(request)
        except Exception as error:
            result = {"status": "FAILED", "error": {"type": type(error).__name__, "message": str(error)}}
        outcome = {"state": "SUCCEEDED" if result["status"] == "COMPLETED" else "FAILED", "result": result}
        if result.get("error"):
            message = result["error"]["message"]
            outcome["error"] = {"code": message.split(":", 1)[0], "message": message}
        self.outgoing.put({"event": "finished", "command_id": request["command_id"], "outcome": outcome,
                           "documents": [self.owner.descriptor()]})
        self.last_tick = time.monotonic()
        self.command_gate.complete()

    def close(self):
        self.owner.assert_thread()
        if self.closed:
            return
        if self.command_gate.executing:
            raise RuntimeError('BUSY_EDIT: native work is still running')
        # Detach must succeed before publishing closure or retiring the owner.
        # A live callback needs its unchanged owner and pending work for retry.
        if self.native_exit is not None:
            self.native_exit.close()
        self.closed = True
        self.owner._activate_origin_window = None
        self.owner._confirm_partial_history_save = None
        # Keep the closed receipt on the existing broker; it reconciles queued
        # commands without pretending a native calculation was cancelled.
        if self.broker_close is not None:
            self.broker_close()
        elif self.broker_stop is not None:
            self.broker_stop.set()
        self.command_gate.complete()
        while not self.incoming.empty():
            try:
                self.incoming.get_nowait()
            except queue.Empty:
                break
        try:
            if self.native_controls is not None:
                self.native_controls.close()
        finally:
            commands.clear_save_owner(self.owner)
            try:
                if self.interactor is not None:
                    try:
                        if self.timer:
                            self.interactor.DestroyTimer(self.timer)
                    finally:
                        if self.observer is not None:
                            self.interactor.RemoveObserver(self.observer)
            finally:
                self.owner.close()


from caelab.native_transport import BrokerIO as _NativeBrokerIO


class BrokerIO(_NativeBrokerIO):
    def __init__(self, dispatcher, service_url, *, log=None, tick_timeout=30):
        super().__init__(dispatcher, service_url, application="paraview",
                         version=str(p.GetParaViewVersion()), log=log, tick_timeout=tick_timeout)
        dispatcher.broker_close = self.close


def start(service_url=None, *, log=None, owner=None, _portable_binding=None):
    owner = owner or Owner(_portable_binding=_portable_binding)
    if _portable_binding is not None and owner.portable_binding is not _portable_binding:
        raise ValueError('STALE_TARGET: existing Post owner belongs to another open ticket')
    dispatcher = GuiDispatch(owner)
    try:
        dispatcher.install()
        broker = BrokerIO(dispatcher, service_url, log=log).start() if service_url else None
        commands.set_save_owner(owner)
    except Exception:
        dispatcher.close()
        raise
    return owner, dispatcher, broker


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Read-only native API probe; not GUI acceptance")
    parser.add_argument("--project")
    args = parser.parse_args()
    if args.project:
        os.environ["CAE_POST_PROJECT"] = args.project
        commands.restore_workspace()
        owner = Owner()
        print(json.dumps(owner.snapshot, allow_nan=False))
        view = p.GetActiveView()
    else:
        view = p.CreateView("RenderView")
    interactor = view.SMProxy.GetInteractor()
    print(json.dumps({"version": str(p.GetParaViewVersion()), "view_id": proxy_id(view),
                      "interactor": None if interactor is None else interactor.GetClassName(),
                      "is_qvtk": False if interactor is None else bool(interactor.IsA("QVTKInteractor")),
                      "gui_dispatch_verified": False}))
