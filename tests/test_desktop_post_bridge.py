"""Owner identity, native edits and queue/thread separation without GUI claims."""
import importlib
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest


class Property:
    def __init__(self, data):
        self.data = data
        self.unchecked = []
        self.SMProperty = self

    def GetInformationOnly(self):
        return False

    def GetData(self):
        return self.data

    def GetNumberOfUncheckedElements(self):
        return len(self.unchecked)

    def GetNumberOfElements(self):
        return len(self.data) if isinstance(self.data, list) else 1

    def GetElement(self, index):
        return self.data[index] if isinstance(self.data, list) else self.data

    def GetUncheckedElement(self, index):
        return self.unchecked[index]


class Proxy:
    def __init__(self, identifier, kind="PVDReader", **properties):
        self.identifier = identifier
        self.kind = kind
        self.props = {name: Property(data) for name, data in properties.items()}
        self.SMProxy = self
        self.observers = {}

    def GetGlobalIDAsString(self):
        return self.identifier

    def GetXMLName(self):
        return self.kind

    def ListProperties(self):
        return list(self.props)

    def GetProperty(self, name):
        return self.props[name]

    def AddObserver(self, event, callback):
        self.observers[len(self.observers)] = callback
        return len(self.observers) - 1

    def RemoveObserver(self, identifier):
        self.observers.pop(identifier)

    def edit(self, name, data):
        self.props[name].data = data
        for observer in self.observers.values():
            observer(self, "PropertyModifiedEvent")

    def GetInteractor(self):
        return self.interactor


class Interactor:
    def __init__(self, gui):
        self.gui = gui
        self.callbacks = {}

    def IsA(self, kind):
        return self.gui and kind == "QVTKInteractor"

    def AddObserver(self, event, callback):
        self.callbacks[1] = callback
        return 1

    def RemoveObserver(self, identifier):
        self.callbacks.pop(identifier)

    def CreateRepeatingTimer(self, interval):
        return 17

    def DestroyTimer(self, identifier):
        self.destroyed = identifier


@pytest.fixture
def bridge(monkeypatch, tmp_path):
    source = Proxy("source-17", FileName="original.pvd", PointArrays=["response"])
    view = Proxy("view-29", "RenderView", CameraPosition=[1, 2, 3], ViewTime=0)
    view.interactor = Interactor(gui=True)
    representation = Proxy("display-31", "GeometryRepresentation", ColorArrayName=["POINTS", "response"])
    scene = SimpleNamespace(AnimationTime=0)
    current = {"view": view, "source": source}
    sources = {("human label", "17"): source}
    renders = []
    native = SimpleNamespace(GetSources=lambda: sources, GetViews=lambda: [view],
                             GetRepresentations=lambda: {("display", 31): representation},
                             GetAnimationScene=lambda: scene, GetActiveSource=lambda: current["source"],
                             GetActiveView=lambda: current["view"],
                             SetActiveView=lambda selected: current.update(view=selected),
                             Render=lambda selected: renders.append(selected), GetParaViewVersion=lambda: (6, 2))
    doc = {"kind": "external-result", "document_id": "Dpersistent", "project_root": str(tmp_path), "workspace_sha256": "original"}
    saved = []

    def save_project(path, record):
        saved.append(record)
        output = tmp_path / "saved.json"
        output.write_text(json.dumps(dict(record, workspace_sha256="saved")), encoding="utf-8")
        return output

    def select_array(target, view=None, **arguments):
        scene.AnimationTime = arguments.get("time", scene.AnimationTime)
        representation.edit("ColorArrayName", [arguments["association"], arguments["array"]])
        current["view"] = view or current["view"]
        return arguments

    commands = SimpleNamespace(project=lambda: (tmp_path / "project.json", doc),
                               verify_sources=lambda: (tmp_path / "project.json", doc),
                               set_save_owner=lambda owner: None, clear_save_owner=lambda owner: None)
    external = SimpleNamespace(KIND="external-result", save_project=save_project,
                               select_array=select_array, times=lambda selected: [0, 1],
                               inspect_result=lambda selected: {"time": scene.AnimationTime, "points": 4})
    monkeypatch.setitem(sys.modules, "paraview", SimpleNamespace(simple=native))
    monkeypatch.setitem(sys.modules, "apps.desktop_post.commands", commands)
    monkeypatch.setitem(sys.modules, "apps.desktop_post.external", external)
    import apps.desktop_post as package
    monkeypatch.setattr(package, "commands", commands, raising=False)
    monkeypatch.setattr(package, "external", external, raising=False)
    monkeypatch.delitem(sys.modules, "apps.desktop_post.bridge", raising=False)
    module = importlib.import_module("apps.desktop_post.bridge")
    yield SimpleNamespace(module=module, source=source, view=view, representation=representation,
                          scene=scene, sources=sources, saved=saved, renders=renders, doc=doc,
                          external=external)
    sys.modules.pop("apps.desktop_post.bridge", None)


def command(owner, operation="post.inspect", **overrides):
    return dict({"command_id": "Cone", "document_id": owner.document_id, "session_id": owner.session_id,
                 "expected_generation": owner.generation, "operation": operation, "target": {}, "arguments": {}}, **overrides)


@pytest.fixture
def save_commands(bridge, monkeypatch):
    # Exercise the real macro entry, with only native I/O replaced by the fixture.
    monkeypatch.setattr(sys.modules["paraview"], "servermanager", SimpleNamespace(), raising=False)
    spec = importlib.util.spec_from_file_location("post_save_commands", Path(bridge.module.__file__).with_name("commands.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.project = bridge.module.commands.project
    module.verify_sources = bridge.module.commands.verify_sources
    module.external_module = lambda: bridge.external
    monkeypatch.setattr(bridge.module, "commands", module)
    return module


def test_macro_and_mcp_share_owner_save_completion(bridge, save_commands, monkeypatch):
    monkeypatch.setattr(bridge.module, "BrokerIO", lambda *_args, **_kwargs: SimpleNamespace(start=lambda: None))
    owner, dispatcher, _ = bridge.module.start("http://127.0.0.1:8000")
    bridge.source.edit("PointArrays", ["response", "other"])
    bridge.view.edit("CameraPosition", [3, 2, 1])
    owner.refresh()
    assert owner.descriptor()["dirty"]
    path = save_commands.save_project()
    assert path.is_file() and owner.descriptor()["dirty"] is False
    assert owner.saved_revision == "saved"
    assert bridge.saved[-1]["generation"] == owner.generation == 1
    assert bridge.saved[-1]["view_generation"] == owner.view_generation == 1
    assert bridge.saved[-1]["document_id"] == owner.document_id
    dispatcher._tick()
    report = dispatcher.outgoing.get_nowait()["documents"][0]
    assert report["dirty"] is False and report["saved_revision"] == "saved"
    bridge.source.edit("PointArrays", ["response"])
    result = owner.dispatch(command(owner, "document.save"))
    assert result["status"] == "COMPLETED" and owner.generation == 2
    assert owner.descriptor()["dirty"] is False and len(bridge.saved) == 2
    assert bridge.doc["workspace_sha256"] == "original"
    dispatcher.close()
    assert save_commands._save_owner is None


@pytest.mark.parametrize("failure", ["native", "manifest"])
def test_macro_and_mcp_failed_save_leave_owner_dirty(bridge, save_commands, monkeypatch, tmp_path, failure):
    owner = bridge.module.Owner()
    save_commands.set_save_owner(owner)
    bridge.source.edit("PointArrays", ["other"])

    def fail_save(*_args):
        if failure == "native":
            raise RuntimeError("native SaveState failed")
        path = tmp_path / "broken-manifest.json"
        path.write_text("{}", encoding="utf-8")
        return path

    monkeypatch.setattr(bridge.external, "save_project", fail_save)
    with pytest.raises((RuntimeError, KeyError)):
        save_commands.save_project()
    assert owner.descriptor()["dirty"] and owner.saved_revision == "original"
    assert owner.saved_generation == 0 and owner.generation == 1
    result = owner.dispatch(command(owner, "document.save"))
    assert result["status"] == "FAILED"
    assert owner.descriptor()["dirty"] and owner.saved_revision == "original"


def test_macro_save_rejects_pending_edit_or_different_document(bridge, save_commands):
    owner = bridge.module.Owner()
    save_commands.set_save_owner(owner)
    bridge.source.edit("PointArrays", ["other"])
    bridge.source.props["FileName"].unchecked = ["pending.pvd"]
    with pytest.raises(ValueError, match="BUSY_EDIT"):
        save_commands.save_project()
    bridge.source.props["FileName"].unchecked = []
    bridge.doc["document_id"] = "Dother"
    with pytest.raises(ValueError, match="STALE_DOCUMENT"):
        save_commands.save_project()
    assert bridge.saved == [] and owner.descriptor()["dirty"]


def test_fresh_native_human_edit_and_stale_generation(bridge):
    owner = bridge.module.Owner()
    assert owner.document_id == "Dpersistent"
    request = command(owner, target={"source_id": "source-17"})
    bridge.source.edit("FileName", "new.pvd")
    rejected = owner.dispatch(request)
    assert rejected["status"] == "FAILED" and "generation changed" in rejected["error"]["message"]
    assert owner.generation == 1 and owner.modified_events == 1
    response = owner.dispatch(command(owner, command_id="Cfresh"))
    assert response["result"]["sources"][0]["properties"]["FileName"] == "new.pvd"
    bridge.source.edit("FileName", "original.pvd")
    owner.refresh()
    assert owner.generation == 2  # Native Undo does not rewind generation.


def test_view_changes_do_not_stale_source_generation(bridge):
    owner = bridge.module.Owner()
    bridge.view.edit("CameraPosition", [3, 2, 1])
    bridge.representation.edit("ColorArrayName", ["CELLS", "response"])
    bridge.scene.AnimationTime = 1
    owner.refresh()
    assert owner.generation == 0 and owner.view_generation == 1


def test_apply_then_undo_between_timer_ticks_still_advances_generation(bridge):
    owner = bridge.module.Owner()
    bridge.source.edit("FileName", "new.pvd")
    bridge.source.edit("FileName", "original.pvd")
    assert owner.refresh()["generation"] == 2


def test_exact_target_session_pending_edits_and_no_arbitrary_exec(bridge):
    owner = bridge.module.Owner()
    for request in (command(owner, session_id="Sprevious"),
                    command(owner, command_id="Ctarget", target={"source_id": "human label"}),
                    command(owner, command_id="Cexec", operation="python.exec", arguments={"code": "bad"})):
        assert owner.dispatch(request)["status"] == "FAILED"
    bridge.source.props["FileName"].unchecked = ["pending.pvd"]
    response = owner.dispatch(command(owner, "document.save", command_id="Cpending"))
    assert "BUSY_EDIT" in response["error"]["message"] and bridge.saved == []
    assert owner.refresh()["sources"][0]["pending_properties"] == ["FileName"]


def test_typed_selection_idempotence_and_append_save_identity(bridge):
    owner = bridge.module.Owner()
    request = command(owner, "post.select_array", target={"source_id": "source-17", "view_id": "view-29"},
                      arguments={"association": "CELLS", "array": "response", "time": 1})
    response = owner.dispatch(request)
    assert response["status"] == "COMPLETED" and response["view_generation"] == 1
    assert owner.dispatch(request) == response and len(bridge.renders) == 1
    with pytest.raises(ValueError, match="different content"):
        owner.dispatch(dict(request, arguments={"association": "POINTS", "array": "response"}))
    saved = owner.dispatch(command(owner, "document.save", command_id="Csave"))
    assert saved["status"] == "COMPLETED" and bridge.saved[0]["document_id"] == "Dpersistent"
    assert owner.descriptor()["dirty"] is False
    assert bridge.doc["workspace_sha256"] == "original"


def test_proxy_operations_reject_other_threads(bridge):
    owner = bridge.module.Owner()
    errors = []
    def other_thread():
        try:
            owner.refresh()
        except RuntimeError as error:
            errors.append(str(error))
    worker = threading.Thread(target=other_thread)
    worker.start()
    worker.join()
    assert errors and "owner thread" in errors[0]


def test_native_timer_drains_on_owner_thread_and_refuses_headless(bridge):
    owner = bridge.module.Owner()
    dispatcher = bridge.module.GuiDispatch(owner).install()
    dispatcher.incoming.put(command(owner))
    assert dispatcher.ready is False
    bridge.view.interactor.callbacks[1](None, "TimerEvent")
    events = [dispatcher.outgoing.get_nowait() for _ in range(3)]
    assert [event["event"] for event in events] == ["ready", "started", "finished"]
    assert events[-1]["outcome"]["state"] == "SUCCEEDED"
    dispatcher.close()
    assert bridge.view.interactor.destroyed == 17
    bridge.view.interactor = Interactor(gui=False)
    with pytest.raises(RuntimeError, match="headless execution cannot control a GUI"):
        bridge.module.GuiDispatch(owner).install()


def test_broker_io_moves_only_json_while_timer_owns_proxy_dispatch(bridge, monkeypatch):
    from caelab.workbench_client import Client
    owner = bridge.module.Owner()
    dispatcher = bridge.module.GuiDispatch(owner).install()
    broker = bridge.module.BrokerIO(dispatcher, "http://127.0.0.1:8000")
    packets, sent = [], False
    completed = threading.Event()
    main_thread = threading.get_ident()

    def request(client, path, body=None):
        nonlocal sent
        assert threading.get_ident() != main_thread
        packets.append((path, body))
        if path.endswith("/register"):
            return {"host_token": "private-host-token"}
        if path.endswith("/commands/next"):
            if not sent:
                sent = True
                return {"command": command(owner, host_id=broker.host_id)}
            return {"command": None}
        if body.get("event") == "finished":
            completed.set()
        return {"accepted": True}

    monkeypatch.setattr(Client, "request", request)
    # No host registration before the first actual native timer callback.
    dispatcher._tick()
    broker.start()
    queued = dispatcher.incoming.get(timeout=2)
    dispatcher.incoming.put(queued)
    dispatcher._tick()
    assert completed.wait(2)
    broker.close()
    broker.worker.join(timeout=2)
    assert not broker.worker.is_alive()
    registration = packets[0][1]
    assert registration["execution_mode"] == "gui" and registration["documents"][0]["id"] == owner.document_id
    assert registration["registration_nonce"] == broker.registration_nonce and len(broker.registration_nonce) >= 32
    outcomes = [body for path, body in packets if body.get("event") == "finished"]
    assert outcomes[0]["outcome"]["state"] == "SUCCEEDED"
    assert "host_token" not in outcomes[0]["outcome"]["result"]
    assert "registration_nonce" not in outcomes[0]["outcome"]["result"]


def test_unchanged_owner_heartbeat_requires_actual_timer_ticks(bridge, monkeypatch):
    owner = bridge.module.Owner()
    dispatcher = bridge.module.GuiDispatch(owner).install()
    clock = [10.0]
    monkeypatch.setattr(bridge.module.time, "monotonic", lambda: clock[0])
    dispatcher._tick()
    assert dispatcher.outgoing.get_nowait()["event"] == "ready"
    clock[0] = 10.5
    dispatcher._tick()
    assert dispatcher.outgoing.empty()
    clock[0] = 11.1
    dispatcher._tick()
    assert dispatcher.outgoing.get_nowait()["event"] == "heartbeat"
    broker = bridge.module.BrokerIO(dispatcher, "http://127.0.0.1:8000", tick_timeout=5)
    broker.require_tick()
    clock[0] = 17
    with pytest.raises(RuntimeError, match="I/O polling is not an owner heartbeat"):
        broker.require_tick()
    assert dispatcher.outgoing.empty()  # I/O checks never synthesize a heartbeat.


def test_io_stops_polling_after_native_timer_loss_and_blocks_late_apply(bridge, monkeypatch):
    from caelab.workbench_client import Client
    owner = bridge.module.Owner()
    dispatcher = bridge.module.GuiDispatch(owner).install()
    dispatcher._tick()
    broker = bridge.module.BrokerIO(dispatcher, "http://127.0.0.1:8000")
    packets, logs = [], []
    broker.log = lambda event, **data: logs.append((event, data))

    def request(client, path, body=None):
        packets.append(path)
        if path.endswith("/register"):
            return {"host_token": "private-token"}
        if path.endswith("/commands/next"):
            dispatcher.last_tick = bridge.module.time.monotonic() - 31
            return {"command": None}
        return {"accepted": True}

    monkeypatch.setattr(Client, "request", request)
    broker.start()
    broker.worker.join(timeout=2)
    assert broker.stop.is_set() and not broker.worker.is_alive()
    assert len([path for path in packets if path.endswith("/commands/next")]) == 1
    assert logs[-1][0] == "bridge_io_stopped"
    assert all(broker.registration_nonce not in str(data) for _, data in logs)
    dispatcher.incoming.put(command(owner, "document.save"))
    dispatcher._tick()
    assert bridge.saved == [] and dispatcher.incoming.qsize() == 1
