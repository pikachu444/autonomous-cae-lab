"""Real broker/Owner/Workspace routing with scripted native row I/O only.

No ParaView, VTK, SDK, GUI, solver, provider or desktop process is executed.
The existing bridge proxy fixture supplies the physical native boundary; the
actual full Owner descriptor and durable broker protocol are not filtered.
"""
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from apps.research.post_curve_origin import NativeReturn, _command
from caelab.native_commands import NativeCommands
from test_desktop_post_bridge import bridge
from test_post_curve_origin_return import flow


@pytest.fixture(autouse=True)
def restore_native_import_bindings():
    import apps.desktop_post as package
    prefix = "apps.desktop_post."
    modules = {key: value for key, value in sys.modules.items() if key.startswith(prefix)}
    missing = object()
    names = ("bridge", "workspace", "commands", "external", "analysis", "measurements", "contact_views", "curve_origin_native")
    attributes = {name: getattr(package, name, missing) for name in names}
    yield
    for key in list(sys.modules):
        if key.startswith(prefix) and key not in modules:
            sys.modules.pop(key, None)
    sys.modules.update(modules)
    for name, value in attributes.items():
        if value is missing:
            if hasattr(package, name):
                delattr(package, name)
        else:
            setattr(package, name, value)


class BrokerClient:
    """Synchronous transport through the existing queue and completion APIs."""
    def __init__(self, broker, owner, credentials):
        self.broker, self.owner, self.credentials = broker, owner, credentials
        self.submits, self.dispatched, self.polls = [], [], []
        self.lost = set()

    def documents(self):
        return {"documents": self.broker.documents()}

    def document_read(self, identifier):
        return self.broker.read(identifier)

    def document_command(self, identifier, operation, arguments, **kwargs):
        self.submits.append(deepcopy(dict(document_id=identifier, operation=operation,
            arguments=arguments, **kwargs)))
        admitted = self.broker.submit(identifier, operation, arguments, **kwargs)
        dispatched = self.broker.next("Hpostbroker", **self.credentials)["command"]
        assert dispatched["command_id"] == admitted["command_id"]
        self.dispatched.append(deepcopy(dispatched))
        self.broker.event("Hpostbroker", **self.credentials, event="started",
            command_id=dispatched["command_id"], documents=[self.owner.descriptor()])
        envelope = self.owner.dispatch(dispatched)
        outcome = {"state": "SUCCEEDED" if envelope["status"] == "COMPLETED" else "FAILED", "result": envelope}
        self.broker.event("Hpostbroker", **self.credentials, event="finished",
            command_id=dispatched["command_id"], outcome=outcome, documents=[self.owner.descriptor()])
        completed = self.broker.status(admitted["command_id"])
        if operation in self.lost:
            self.lost.remove(operation)
            raise OSError("TEST_ONLY reply lost after native completion")
        return completed

    def command_status(self, identifier):
        self.polls.append(identifier)
        return self.broker.status(identifier)


@pytest.fixture
def broker_flow(bridge, flow, monkeypatch, tmp_path):
    import apps.desktop_post as package
    # Load a fresh real router; all temporary native modules/attributes are
    # restored by monkeypatch rather than leaking fixture imports to later tests.
    for name in ("analysis", "measurements", "contact_views"):
        module = ModuleType("apps.desktop_post." + name)
        if name == "contact_views":
            module.restore = lambda workspace: False
        monkeypatch.setitem(sys.modules, module.__name__, module)
        monkeypatch.setattr(package, name, module, raising=False)
    native = ModuleType("apps.desktop_post.curve_origin_native")
    monkeypatch.setitem(sys.modules, native.__name__, native)
    monkeypatch.setattr(package, "curve_origin_native", native, raising=False)
    path = Path(__file__).parents[1] / "apps/desktop_post/workspace.py"
    spec = importlib.util.spec_from_file_location("apps.desktop_post.workspace", path)
    workspace_module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, workspace_module)
    monkeypatch.setattr(package, "workspace", workspace_module, raising=False)
    spec.loader.exec_module(workspace_module)
    bridge.doc.update(document_id="Dpost", generation=3, view_generation=4, sources={})
    owner = bridge.module.Owner(session_id="Scurrent")
    broker = NativeCommands(tmp_path / "broker", "Sservice")
    helper_calls = []

    def receipt(operation, workspace, *, target, expected_view_generation, verified=None):
        assert type(workspace) is workspace_module.Workspace and workspace is owner.workspace
        assert target == flow.target and expected_view_generation == owner.view_generation
        helper_calls.append((operation, deepcopy(target), expected_view_generation))
        # Reuse the established row receipt fixture only at the native I/O seam.
        scripted = flow.client.document_command(owner.document_id, operation, {"target": target},
            session_id=owner.session_id, expected_generation=owner.generation,
            command_id="Cscripted" + str(len(helper_calls)))
        result = deepcopy(scripted["outcome"]["result"]["result"])
        result["native_pid"] = os.getpid()
        if operation == "post.curve_origin_select":
            assert verified["row"] == result["row"] and verified["target_sha256"] == result["target_sha256"]
            workspace._touch()
            bridge.scene.AnimationTime = .02
            owner.refresh()
        assert (result["generation"], result["view_generation"]) == (owner.generation, owner.view_generation)
        return result

    native.read = lambda *args, **kwargs: pytest.fail("Read was not requested in this bounded verify/select check")
    native.verify = lambda workspace, **kwargs: receipt("post.curve_origin_verify", workspace, **kwargs)
    native.select = lambda workspace, **kwargs: receipt("post.curve_origin_select", workspace, **kwargs)
    try:
        registration = broker.register(host_id="Hpostbroker", session_id=owner.session_id,
            application="paraview", version="6.2 scripted native boundary", execution_mode="gui",
            documents=[owner.descriptor()], registration_nonce="owned-test-registration-" * 2)
        credentials = {"session_id": owner.session_id, "host_token": registration["host_token"]}
        client = BrokerClient(broker, owner, credentials)
        yield SimpleNamespace(client=client, owner=owner, broker=broker,
            operation=NativeReturn(client, flow.target), target=flow.target,
            helper_calls=helper_calls, launches=flow.calls)
    finally:
        owner.close()
        broker.shutdown()


@pytest.mark.parametrize("lost_phase", [None, "verify", "select"])
def test_real_broker_roundtrip_preserves_origin_target_and_lost_reply_only_polls(broker_flow, lost_phase):
    f = broker_flow
    for phase in ("verify", "select"):
        operation = "post.curve_origin_" + phase
        if phase == lost_phase:
            f.client.lost.add(operation)
            with pytest.raises(OSError, match="reply lost"):
                getattr(f.operation, phase)()
            before = len(f.client.submits), len(f.helper_calls), len(f.owner.completed)
            command_id = f.client.submits[-1]["command_id"]
            retained = f.broker.root / (command_id + ".json")
            saved = retained.read_bytes()
            result = getattr(f.operation, phase)()
            assert f.client.polls == [command_id]
            assert (len(f.client.submits), len(f.helper_calls), len(f.owner.completed)) == before
            assert retained.read_bytes() == saved
        else:
            result = getattr(f.operation, phase)()
        assert result["status"] == ("SOURCE_VERIFIED" if phase == "verify" else "SOURCE_SELECTED")
        requested = f.client.submits[-1]
        dispatched = f.client.dispatched[-1]
        completed = f.broker.status(requested["command_id"])
        assert dispatched["target"] == completed["target"] == {}
        assert dispatched["arguments"] == completed["arguments"] == requested["arguments"]
        assert completed["arguments"]["origin_target"] == f.target
        assert "target" not in completed["arguments"] and completed["state"] == "SUCCEEDED"
        assert completed["outcome"]["result"]["status"] == "COMPLETED"
    assert [call[0] for call in f.helper_calls] == ["post.curve_origin_verify", "post.curve_origin_select"]
    assert len(f.client.submits) == len(f.owner.completed) == 2
    assert not f.launches and f.operation.verified_ok and f.operation.selected_ok


@pytest.mark.parametrize("phase", ["verify", "select"])
def test_old_reserved_target_wire_is_rejected_by_real_owner_and_exact_receipt_guard(broker_flow, phase):
    f = broker_flow
    if phase == "select":
        verified = f.operation.verify()
    else:
        verified = None
    native = f.client.document_read(f.owner.document_id)
    arguments = {"target": deepcopy(f.target), "expected_view_generation": native["view_generation"]}
    if verified:
        arguments["verified"] = verified
    original = deepcopy(arguments)
    calls_before = len(f.helper_calls)
    track = {}
    with pytest.raises(ValueError, match="다른 원행 요청"):
        _command(f.client, native, "post.curve_origin_" + phase, arguments, track, timeout=0)
    completed = f.broker.status(track["request"]["command_id"])
    assert completed["target"] == f.target and "target" not in completed["arguments"]
    assert completed["state"] == "FAILED"
    envelope = completed["outcome"]["result"]
    assert envelope["status"] == "FAILED"
    assert "stable source_ref/object_ref" in envelope["error"]["message"]
    assert arguments == original and len(f.helper_calls) == calls_before
    assert not f.launches
