"""Offline selector regressions using the real pinned worker and simulated CAD.

No FreeCAD process is started. Mock document/shape responses test routing and
identity handling, not actual FCStd regeneration or engineering acceptance.
"""

from copy import deepcopy
import hashlib
import io
import json
import math
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from caelab.adapters import freecad_parameter_worker as owned_worker
from caelab.adapters import freecad_parameters as selectors
from caelab.adapters import native_bridge
from caelab.adapters.fixture_freecad import FixtureFreeCADAdapter


LEGACY = "LocatorProfile|constraint|0"


class Sketch:
    Name = "LocatorProfile"
    Label = "User locator profile"
    TypeId = "Sketcher::SketchObject"
    PropertiesList = []

    def __init__(self):
        self.Constraints = [SimpleNamespace(Name="center_x", Type="DistanceX", Value=2.0),
                            SimpleNamespace(Name="locator_radius", Type="Radius", Value=6.0)]
        self.driving = [True, True]

    def getDriving(self, index):
        return self.driving[index]

    def renameConstraint(self, index, name):
        self.Constraints[index].Name = name

    def setDatum(self, index, quantity):
        self.Constraints[index].Value = quantity.Value


class Document:
    Name = "MockNative"
    Label = "Offline imported locator"

    def __init__(self, path):
        self.path = path
        self.saved = 0
        self.effect = True
        self.sketch = Sketch()
        self.block = SimpleNamespace(Name="Block", Label="User block", TypeId="Part::Box",
            PropertiesList=["Length"], Length=SimpleNamespace(Value=32.0),
            getTypeIdOfProperty=lambda _: "App::PropertyLength")
        self.config = SimpleNamespace(Name="FixtureConfiguration", Label="Fixture definitions", TypeId="App::DocumentObjectGroup", PropertiesList=[],
            Definition=json.dumps({"final": "LocatorSolid", "parameters": [{
                "key": LEGACY, "name": "radius", "label": "User radius", "unit": "mm",
                "object": self.sketch.Name, "kind": "constraint", "constraint": "locator_radius",
                "min": 2.0, "max": 10.0}]}))
        self.final = SimpleNamespace(Name="LocatorSolid", Label="Final user locator", TypeId="Part::Extrusion", PropertiesList=[])
        self.Objects = [self.sketch, self.block, self.config, self.final]
        self.recompute()

    def getObject(self, name):
        return next((obj for obj in self.Objects if obj.Name == name), None)

    def recompute(self):
        if not self.effect and hasattr(self.final, "Shape"):
            return
        radius = next((c.Value for c in self.sketch.Constraints if c.Type == "Radius"), 6.0)
        x = -next((c.Value for c in self.sketch.Constraints if c.Type == "DistanceX"), 0.0)
        bounds = SimpleNamespace(XMin=x-radius, XMax=x+radius, YMin=-radius, YMax=radius, ZMin=0, ZMax=8)
        self.final.Shape = SimpleNamespace(Volume=8*math.pi*radius**2, Area=16*math.pi*radius+2*math.pi*radius**2,
            BoundBox=bounds, Solids=[SimpleNamespace(CenterOfMass=SimpleNamespace(x=x, y=0, z=4))])

    def save(self):
        self.saved += 1
        self.path.write_bytes(f"SIMULATED FCSTD SAVE {self.saved}\n".encode())


@pytest.fixture
def native(tmp_path, monkeypatch):
    source = tmp_path / "editable.FCStd"
    source.write_bytes(b"SIMULATED IMPORTED FCSTD BYTES\n")
    doc = Document(source)
    calls = {"open": 0, "close": 0}

    def open_document(path):
        assert Path(path) == source
        calls["open"] += 1
        return doc

    def close_document(name):
        assert name == doc.Name
        calls["close"] += 1

    app = SimpleNamespace(openDocument=open_document, closeDocument=close_document,
        Units=SimpleNamespace(Quantity=lambda text: SimpleNamespace(Value=float(text.split()[0]))))
    monkeypatch.setitem(sys.modules, "FreeCAD", app)
    monkeypatch.setitem(sys.modules, "Part", SimpleNamespace())
    worker = owned_worker._upstream_worker()  # Exact local 3e48 file, no copied worker algorithms.
    return SimpleNamespace(doc=doc, worker=worker, source=source, calls=calls,
        sha=lambda: hashlib.sha256(source.read_bytes()).hexdigest())


def inspect(native):
    return owned_worker.dispatch({"action": "inspect", "document": str(native.source)}, native.worker)


def write_registry(native, patch):
    registry = json.loads(native.doc.config.Definition)
    patch(registry)
    native.doc.config.Definition = json.dumps(registry)


def selection(native, key, expected=None):
    worker, doc = native.worker, native.doc
    targets = worker._targets(doc)
    resolved = selectors.registered_targets(doc, worker._registry(doc), targets, worker._datum)
    return selectors.resolve_selection(key, native.sha(), native.sha() if expected is None else expected, targets, resolved)


def register_request(native, target, **patch):
    return {"action": "register", "document": str(native.source), "target": target,
            "source_sha256": native.sha(), "name": "center_offset", "label": "User center offset", "min": 0.0, "max": 8.0, **patch}


def test_inserted_old_index_is_discovered_without_borrowing_radius_bounds(native, tmp_path, monkeypatch):
    info = inspect(native)
    constraint_candidates = [c for c in info["candidates"] if c["kind"] == "constraint"]
    new_key = f"LocatorProfile|caelab-constraint-v1|{native.sha()}|0"
    assert [(c["key"], c["dimension"], c["value"]) for c in constraint_candidates] == [(new_key, "center_x", 2.0)]
    assert info["parameters"][0]["key"] == LEGACY
    assert info["parameters"][0]["value"] == 6.0
    assert native.calls == {"open": 1, "close": 1}
    adapter = FixtureFreeCADAdapter(tmp_path)
    monkeypatch.setattr(adapter, "_call", lambda *_args, **_kwargs: info)
    candidates = adapter.discover("imported")
    assert len({c.native["path"] for c in candidates}) == len(candidates)
    new = next(c for c in candidates if c.native["path"] == new_key)
    old = next(c for c in candidates if c.native["path"] == LEGACY)
    assert (new.label, new.value, new.unit, new.lower, new.upper) == ("center_x", 2.0, "mm", None, None)
    assert (old.label, old.value, old.lower, old.upper) == ("User radius", 6.0, 2.0, 10.0)
    assert next(c.native["path"] for c in candidates if c.native["object"] == "Block") == "Block|property|Length"


@pytest.mark.parametrize("case", ["key", "constraint_identity", "property_identity", "raw_path"])
def test_duplicate_definitions_and_raw_paths_fail_before_pinned_inspection(native, monkeypatch, case):
    if case == "raw_path":
        native.doc.block.PropertiesList.append("Length")
        expected = "NATIVE_DUPLICATE_PATH"
    else:
        def patch(registry):
            if case == "property_identity":
                first = {"key": "Block|property|Length", "name": "width", "object": "Block", "kind": "property", "property": "Length"}
                registry["parameters"] = [first, {**first, "key": "historical-property-key", "name": "width_again"}]
            else:
                first = registry["parameters"][0]
                registry["parameters"].append({**first, "name": "second_radius",
                    "key": first["key"] if case == "key" else "registered-opaque-key"})
        write_registry(native, patch)
        expected = "NATIVE_DUPLICATE_KEY" if case == "key" else "NATIVE_DUPLICATE_IDENTITY"
    monkeypatch.setattr(native.worker, "inspect", lambda *_: pytest.fail("Ambiguous definitions reached pinned inspection"))
    with pytest.raises(ValueError, match=expected):
        inspect(native)


@pytest.mark.parametrize("case,code", [
    ("rename", "NATIVE_REGISTERED_DIMENSION_MISSING"), ("delete", "NATIVE_REGISTERED_DIMENSION_MISSING"),
    ("delete_object", "NATIVE_REGISTERED_DIMENSION_MISSING"), ("not_driving", "NATIVE_REGISTERED_NOT_DRIVING"),
    ("unsupported", "NATIVE_REGISTERED_UNSUPPORTED"), ("duplicate_name", "NATIVE_DUPLICATE_IDENTITY"),
    ("duplicate_nondriving_name", "NATIVE_DUPLICATE_IDENTITY"), ("positional_definition", "NATIVE_REGISTERED_UNSUPPORTED"),
])
def test_registered_named_dimension_is_strict_and_never_uses_first_match(native, monkeypatch, case, code):
    sketch = native.doc.sketch
    if case == "rename": sketch.Constraints[1].Name = "renamed_radius"
    elif case == "delete": sketch.Constraints.pop(); sketch.driving.pop()
    elif case == "delete_object": native.doc.Objects.remove(sketch)
    elif case == "not_driving": sketch.driving[1] = False
    elif case == "unsupported": sketch.Constraints[1].Type = "Angle"
    elif case.startswith("duplicate"):
        sketch.Constraints.append(SimpleNamespace(Name="locator_radius", Type="Radius", Value=8.0))
        sketch.driving.append(case == "duplicate_name")
    else: write_registry(native, lambda registry: registry["parameters"][0].update(constraint_index=1))
    monkeypatch.setattr(native.worker, "inspect", lambda *_: pytest.fail("Invalid named identity reached pinned inspection"))
    with pytest.raises(ValueError, match=code):
        inspect(native)


@pytest.mark.parametrize("case,code", [("deleted", "NATIVE_REGISTERED_DIMENSION_MISSING"),
                                      ("unit", "NATIVE_REGISTERED_UNSUPPORTED")])
def test_registered_property_requires_current_supported_property(native, case, code):
    write_registry(native, lambda registry: registry["parameters"].append({"key": "Block|property|Length",
        "name": "width", "object": "Block", "kind": "property", "property": "Length"}))
    if case == "deleted": native.doc.block.PropertiesList.clear()
    else: native.doc.block.getTypeIdOfProperty = lambda _: "App::PropertyAngle"
    with pytest.raises(ValueError, match=code): inspect(native)


@pytest.mark.parametrize("raw", ["LocatorProfile|constraint|1", "LocatorProfile|constraint|2", "LocatorProfile|constraint|99"])
def test_unregistered_legacy_indices_have_no_positional_fallback(native, raw):
    with pytest.raises(ValueError, match="NATIVE_SELECTOR_REDISCOVERY_REQUIRED"):
        selection(native, raw)
    actual, registered = selection(native, LEGACY)
    assert actual["key"] == "LocatorProfile|constraint|1" and registered["constraint"] == "locator_radius"


@pytest.mark.parametrize("expected_revision", ["old", "current"])
def test_stale_opaque_selector_refuses_before_pinned_registration(native, monkeypatch, expected_revision):
    candidate = next(c for c in inspect(native)["candidates"] if c["kind"] == "constraint")
    old_sha = native.sha()
    native.doc.save()
    monkeypatch.setattr(native.worker, "dispatch", lambda *_: pytest.fail("A stale selector reached pinned registration"))
    request = register_request(native, candidate["key"], source_sha256=old_sha if expected_revision == "old" else native.sha())
    with pytest.raises(ValueError, match="NATIVE_SELECTOR_STALE"):
        owned_worker.dispatch(request, native.worker)


def test_unregistered_property_requires_its_current_discovery_revision(native):
    with pytest.raises(ValueError, match="NATIVE_SELECTOR_STALE"):
        selection(native, "Block|property|Length", "f" * 64)
    actual, registered = selection(native, "Block|property|Length")
    assert actual["key"] == "Block|property|Length" and registered is None


def test_bind_preserves_opaque_key_and_pinned_named_identity_across_save_and_reorder(native, monkeypatch):
    candidate = next(c for c in inspect(native)["candidates"] if c["kind"] == "constraint")
    original_key, original_sha = candidate["key"], native.sha()
    calls, pinned_dispatch = [], native.worker.dispatch

    def dispatch(request):
        calls.append(deepcopy(request))
        return pinned_dispatch(request)

    monkeypatch.setattr(native.worker, "dispatch", dispatch)
    info = owned_worker.dispatch(register_request(native, original_key), native.worker)
    assert [request["target"] for request in calls] == ["LocatorProfile|constraint|0"]
    registry = native.worker._registry(native.doc)
    assert [(entry["key"], entry["constraint"]) for entry in registry["parameters"]] == [
        (LEGACY, "locator_radius"), (original_key, "center_offset")]
    assert info["source_sha256"] == native.sha() != original_sha
    native.doc.sketch.Constraints.reverse(); native.doc.sketch.driving.reverse()
    native.doc.save()
    refreshed = inspect(native)
    assert [entry["key"] for entry in refreshed["parameters"]] == [LEGACY, original_key]
    assert not [candidate for candidate in refreshed["candidates"] if candidate["kind"] == "constraint"]
    actual, registered = selection(native, original_key, original_sha)
    assert actual["key"] == "LocatorProfile|constraint|1" and registered["constraint"] == "center_offset"
    assert registered["label"] == "User center offset" and (registered["min"], registered["max"]) == (0.0, 8.0)


def test_pinned_geometry_effect_refusal_is_preserved(native):
    candidate = next(c for c in inspect(native)["candidates"] if c["kind"] == "constraint")
    native.doc.effect = False
    original = native.source.read_bytes()
    with pytest.raises(ValueError, match="no measurable effect"):
        owned_worker.dispatch(register_request(native, candidate["key"]), native.worker)
    assert native.source.read_bytes() == original and native.doc.saved == 0


@pytest.mark.parametrize("driving", [True, False])
def test_registration_rejects_a_name_collision_before_pinned_mutation(native, monkeypatch, driving):
    candidate = next(c for c in inspect(native)["candidates"] if c["kind"] == "constraint")
    native.doc.sketch.Constraints.append(SimpleNamespace(Name="new_offset", Type="DistanceY", Value=3.0))
    native.doc.sketch.driving.append(driving)
    monkeypatch.setattr(native.worker, "dispatch", lambda *_: pytest.fail("A name collision reached pinned registration"))
    before = native.source.read_bytes()
    with pytest.raises(ValueError, match="NATIVE_DUPLICATE_IDENTITY"):
        owned_worker.dispatch(register_request(native, candidate["key"], name="new_offset"), native.worker)
    assert native.source.read_bytes() == before and native.doc.sketch.Constraints[0].Name == "center_x"


@pytest.mark.parametrize("case", ["registered", "cross_namespace"])
def test_adapter_rejects_duplicate_paths_before_bounds_lookup(tmp_path, monkeypatch, case):
    parameter = {"key": LEGACY, "object": "LocatorProfile", "value": 6, "kind": "constraint", "min": 2, "max": 10}
    info = {"parameters": [parameter], "candidates": [], "source_sha256": "a" * 64}
    if case == "registered": info["parameters"].append({**parameter, "min": -999, "max": 999})
    else: info["candidates"].append({**parameter, "value": 2})
    adapter = FixtureFreeCADAdapter(tmp_path)
    monkeypatch.setattr(adapter, "_call", lambda *_args, **_kwargs: info)
    with pytest.raises(ValueError, match="NATIVE_DUPLICATE_PATH"): adapter.discover("model")


def test_adapter_probe_and_bind_forward_current_candidate_revision(native, tmp_path, monkeypatch):
    info = inspect(native)
    adapter, calls = FixtureFreeCADAdapter(tmp_path), []
    monkeypatch.setattr(adapter, "_call", lambda *_args, **_kwargs: info)
    candidate = next(c for c in adapter.discover("model") if "caelab-constraint-v1" in c.native["path"])

    def call(action, **kwargs):
        calls.append((action, kwargs))
        return {"source_sha256": "b" * 64, "status": "PASS"}

    monkeypatch.setattr(adapter, "_call", call)
    adapter.probe_effect("model", candidate, 0, 8)
    assert adapter.bind("model", candidate, "offset", "Offset", 0, 8) == "b" * 64
    assert [action for action, _ in calls] == ["probe", "bind"]
    assert all(kwargs["source_sha256"] == candidate.source_sha256 and kwargs["target"] == candidate.native["path"] for _, kwargs in calls)


def test_owned_launch_keeps_trusted_worker_protocol_and_existing_inner_bound(tmp_path, monkeypatch):
    monkeypatch.setenv("FREECAD_CMD", "TRUSTED TEST EXECUTABLE")
    monkeypatch.setenv("CAELAB_FREECAD_PARAMETER_WORKER", "UNTRUSTED INHERITED PATH")
    request = {"action": "inspect", "document": "SIMULATED.FCStd", "worker": "UNTRUSTED WORKER OVERRIDE"}
    seen = []

    def run(command, **kwargs):
        seen.append((command, kwargs))
        assert command == ["TRUSTED TEST EXECUTABLE", str(Path(native_bridge.__file__).with_name("freecad_parameter_worker.py").resolve())]
        assert kwargs["cwd"] == native_bridge.UPSTREAM and kwargs["timeout"] == 150
        assert kwargs["env"]["CAELAB_FREECAD_PARAMETER_WORKER"] == command[1]
        assert kwargs["stdout"] == native_bridge.subprocess.PIPE and kwargs["stderr"] == native_bridge.subprocess.PIPE
        assert json.loads(Path(kwargs["env"]["FIXTURE_FREECAD_REQUEST"]).read_text()) == request
        Path(kwargs["env"]["FIXTURE_FREECAD_RESULT"]).write_text(json.dumps({"ok": True, "result": {"native": True}}))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(native_bridge.subprocess, "run", run)
    assert native_bridge._parameter_run(request) == {"native": True}
    assert len(seen) == 1


def test_exact_appimage_console_exec_resolves_fixed_worker_without_dunder_file(native, tmp_path, monkeypatch):
    worker_path = Path(owned_worker.__file__).resolve()
    request, result = tmp_path / "request.json", tmp_path / "result.json"
    request.write_text(json.dumps({"action": "inspect", "document": str(native.source)}))
    for key, value in {"CAELAB_FREECAD_PARAMETER_WORKER": worker_path, "FIXTURE_FREECAD_SCRIPT": worker_path,
                       "FIXTURE_FREECAD_REQUEST": request, "FIXTURE_FREECAD_RESULT": result}.items():
        monkeypatch.setenv(key, str(value))
    console = {"__name__": "__main__"}
    # Same code string as the installed/pinned wrapper's console, with no
    # __file__ injected by importlib or a conventional Python script runner.
    exec('exec(compile(open(__import__("os").environ["FIXTURE_FREECAD_SCRIPT"]).read(), "<fixture-worker>", "exec"))', console)
    assert "__file__" not in console
    answer = json.loads(result.read_text())
    assert answer["ok"] is True
    assert answer["result"]["parameters"][0]["key"] == LEGACY
    assert any(candidate["dimension"] == "center_x" for candidate in answer["result"]["candidates"])
    assert native.calls == {"open": 1, "close": 1}


@pytest.mark.parametrize("case", ["missing", "foreign", "relative"])
def test_console_exec_refuses_missing_foreign_or_relative_worker_seam(native, monkeypatch, case):
    worker_path = Path(owned_worker.__file__).resolve()
    monkeypatch.setenv("FIXTURE_FREECAD_SCRIPT", str(worker_path))
    if case == "missing": monkeypatch.delenv("CAELAB_FREECAD_PARAMETER_WORKER", raising=False)
    elif case == "foreign": monkeypatch.setenv("CAELAB_FREECAD_PARAMETER_WORKER", str(native.source))
    else: monkeypatch.setenv("CAELAB_FREECAD_PARAMETER_WORKER", "freecad_parameter_worker.py")
    with pytest.raises(RuntimeError, match="NATIVE_WORKER_ENTRY_INVALID"):
        exec(compile(worker_path.read_text(), "<fixture-worker>", "exec"), {"__name__": "__main__"})
    assert native.calls == {"open": 0, "close": 0}


@pytest.mark.parametrize("answer,exit_code,code", [
    (None, 0, "produced no result"), ({"ok": False, "error": "NATIVE_DUPLICATE_KEY"}, 1, "NATIVE_DUPLICATE_KEY"),
    ({"ok": True, "result": {}}, 7, "returned an error"), ({"ok": "yes", "result": {}}, 0, "invalid worker result"),
    ({"ok": True, "result": []}, 0, "invalid native CAD result"),
])
def test_owned_launch_refuses_missing_failed_or_malformed_native_result(monkeypatch, answer, exit_code, code):
    monkeypatch.setenv("FREECAD_CMD", "TRUSTED TEST EXECUTABLE")

    def run(_command, **kwargs):
        if answer is not None:
            Path(kwargs["env"]["FIXTURE_FREECAD_RESULT"]).write_text(json.dumps(answer))
        return SimpleNamespace(returncode=exit_code, stdout="", stderr="")

    monkeypatch.setattr(native_bridge.subprocess, "run", run)
    with pytest.raises((ValueError, RuntimeError), match=code): native_bridge._parameter_run({"action": "inspect"})


def test_adapter_retains_existing_outer_process_bound(tmp_path, monkeypatch):
    monkeypatch.setenv("FREECAD_CMD", "TRUSTED TEST EXECUTABLE")

    def run(command, **kwargs):
        assert command[-2:] == ["-m", "caelab.adapters.native_bridge"]
        assert kwargs["timeout"] == 180 and kwargs["capture_output"] and kwargs["text"]
        assert json.loads(kwargs["input"])["store"] == str(tmp_path)
        return SimpleNamespace(returncode=0, stdout='{"result": "simulated"}', stderr="")

    monkeypatch.setattr(native_bridge.subprocess, "run", run)
    assert FixtureFreeCADAdapter(tmp_path)._call("discover", model="model") == {"result": "simulated"}


@pytest.mark.parametrize("action", ["preflight", "regenerate", "bind", "probe", "select_final"])
def test_bridge_blocks_native_algorithms_when_current_registered_identity_is_invalid(native, monkeypatch, action):
    request = {"store": str(native.source.parent), "action": action, "model": "model", "target": LEGACY,
               "values": {LEGACY: 7}, "lower": 2, "upper": 10, "final": "LocatorSolid", "output": "unused"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request)))
    monkeypatch.setattr(native_bridge.native_cad, "_path", lambda _: native.source)
    monkeypatch.setattr(native_bridge, "_inspect", lambda *_: (_ for _ in ()).throw(ValueError("NATIVE_REGISTERED_DIMENSION_MISSING")))
    monkeypatch.setattr(native_bridge.native_cad, "execute", lambda *_: pytest.fail("Invalid identity reached native execution"))
    monkeypatch.setattr(native_bridge.native_cad, "_run", lambda *_: pytest.fail("Invalid identity reached native geometry"))
    with pytest.raises(ValueError, match="NATIVE_REGISTERED_DIMENSION_MISSING"): native_bridge.main()


@pytest.mark.parametrize("drift", [False, True])
def test_importer_receives_only_the_once_read_inspected_payload(tmp_path, monkeypatch, capsys, drift):
    source, destination = tmp_path / "input.FCStd", tmp_path / "imported.FCStd"
    original = b"SIMULATED INSPECTED NATIVE INPUT\n"
    source.write_bytes(original)
    inspected_sha = hashlib.sha256(original).hexdigest()
    calls = {"read": 0, "import": []}
    request = {"store": str(tmp_path), "action": "import", "path": str(source)}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request)))

    def inspect_input(request):
        assert request == {"action": "inspect", "document": str(source)}
        if drift:
            source.write_bytes(b"SIMULATED UNINSPECTED CHANGED INPUT\n")
        return {"source_sha256": inspected_sha}

    read_bytes = Path.read_bytes

    def read(path):
        if path == source:
            calls["read"] += 1
        return read_bytes(path)

    def import_document(payload):
        calls["import"].append(payload)
        assert payload == original
        destination.write_bytes(payload)
        return {"design": "imported-model"}

    monkeypatch.setattr(native_bridge, "_parameter_run", inspect_input)
    monkeypatch.setattr(Path, "read_bytes", read)
    monkeypatch.setattr(native_bridge.native_cad, "import_document", import_document)
    monkeypatch.setattr(native_bridge.native_cad, "_path", lambda _: destination)
    monkeypatch.setattr(native_bridge, "_inspect", lambda model: {"design": model, "source_sha256": inspected_sha})
    if drift:
        with pytest.raises(ValueError, match="NATIVE_SOURCE_CHANGED"):
            native_bridge.main()
        assert calls["import"] == [] and not destination.exists()
        assert capsys.readouterr().out == ""
    else:
        native_bridge.main()
        assert calls["import"] == [original]
        assert json.loads(capsys.readouterr().out)["source_sha256"] == inspected_sha
    assert calls["read"] == 1
