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
    def __init__(self, document_id=None, session_id=None):
        self.thread = threading.get_ident()
        self.session_id = session_id or "S" + uuid.uuid4().hex
        path, doc = commands.project()
        if doc.get("kind") != external.KIND:
            raise ValueError("The current Post bridge supports independent external-result documents")
        self.document_id = document_id or doc.get("document_id") or "D" + uuid.uuid4().hex
        self.project_root = Path(doc.get("project_root", path.parent)).resolve()
        self.title = path.parent.name
        self.saved_revision = doc.get("workspace_sha256")
        self.saved_generation = 0
        self.saved_view_generation = 0
        self.generation = doc.get("generation", 0)
        self.view_generation = doc.get("view_generation", 0)
        self.saved_generation = self.generation
        self.saved_view_generation = self.view_generation
        self._content = None
        self._view = None
        self._observers = {}
        self.completed = {}
        self.modified_events = 0
        self.refresh()

    def assert_thread(self):
        if threading.get_ident() != self.thread:
            raise RuntimeError("Native ParaView proxies must be accessed on their owner thread")

    def refresh(self):
        self.assert_thread()
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
                         "fresh": True, "supports": list(OPERATIONS), "supports_cancel": "queued_only"}
        return self.snapshot

    def _modified(self, source):
        self.assert_thread()
        self.modified_events += 1
        if self._content is not None:
            identifier = proxy_id(source)
            applied, _ = properties(source)
            if self._content.get(identifier) != applied:
                # Observe each checked edit/Undo even if two edits happen between ticks.
                self._content[identifier] = applied
                self.generation += 1

    def descriptor(self):
        self.assert_thread()
        return {"id": self.document_id, "kind": "post", "title": self.title,
                "generation": self.generation, "view_generation": self.view_generation,
                "dirty": (self.generation != self.saved_generation or self.view_generation != self.saved_view_generation),
                "saved_revision": self.saved_revision, "capabilities": list(OPERATIONS), "state": self.snapshot}

    def save_project(self):
        """Complete the same managed save for human macros and typed commands."""
        self.refresh()
        if any(item["pending_properties"] for item in self.snapshot["sources"] + self.snapshot["views"] + list(self.snapshot["representations"].values())):
            raise ValueError("BUSY_EDIT: native properties contain unapplied changes")
        path, doc = commands.verify_sources()
        if (doc.get("kind") != external.KIND or doc.get("document_id", self.document_id) != self.document_id
                or Path(doc.get("project_root", path.parent)).resolve() != self.project_root):
            raise ValueError("STALE_DOCUMENT: managed save belongs to a different document")
        generation, view_generation = self.generation, self.view_generation
        saved = external.save_project(path, dict(doc, document_id=self.document_id,
                                                generation=generation, view_generation=view_generation))
        revision = json.loads(saved.read_text(encoding="utf-8"))["workspace_sha256"]
        self.refresh()
        # Publish save completion only after the native save and manifest succeed.
        self.saved_revision = revision
        self.saved_generation, self.saved_view_generation = generation, view_generation
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
        try:
            if request.get("document_id") != self.document_id or request.get("session_id") != self.session_id:
                raise ValueError("STALE_DOCUMENT: wrong document or owner session")
            expected = request.get("expected_generation")
            if type(expected) is not int or expected != self.generation:
                raise ValueError("STALE_DOCUMENT: generation changed")
            operation = request.get("operation")
            if operation not in OPERATIONS:
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
            else:
                if any(item["pending_properties"] for item in self.snapshot["sources"] + self.snapshot["views"] + list(self.snapshot["representations"].values())):
                    raise ValueError("BUSY_EDIT: native properties contain unapplied changes")
                if operation == "document.save":
                    if arguments or target:
                        raise ValueError("document.save uses the managed document save location")
                    saved = self.save_project()
                    payload = {"project": str(saved), "document_id": self.document_id}
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
            raise RuntimeError("GUI_DISPATCH_UNAVAILABLE: native Qt interactor timer creation failed")
        return self

    def _tick(self, *_):
        self.owner.assert_thread()
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
        commands.clear_save_owner(self.owner)
        if self.interactor is not None:
            self.interactor.DestroyTimer(self.timer)
            self.interactor.RemoveObserver(self.observer)


from caelab.native_transport import BrokerIO as _NativeBrokerIO


class BrokerIO(_NativeBrokerIO):
    def __init__(self, dispatcher, service_url, *, log=None, tick_timeout=30):
        super().__init__(dispatcher, service_url, application="paraview",
                         version=str(p.GetParaViewVersion()), log=log, tick_timeout=tick_timeout)


def start(service_url, *, log=None):
    owner = Owner()
    dispatcher = GuiDispatch(owner).install()
    broker = BrokerIO(dispatcher, service_url, log=log).start()
    commands.set_save_owner(owner)
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
