"""Native adapter contract checks that can run without FreeCAD installed."""

from pathlib import Path

import cadquery as cq

from caelab.adapters.fixture_freecad import FixtureFreeCADAdapter
from caelab.adapters import native_bridge


def test_registered_sketch_dimension_is_not_rediscovered_after_index_shift(tmp_path, monkeypatch):
    adapter = FixtureFreeCADAdapter(tmp_path)
    info = {
        "source_sha256": "native-revision", "parameters": [
            {"key": "Sketch|constraint|0", "object": "Sketch", "dimension": "locator_radius",
             "constraint": "locator_radius", "kind": "constraint", "value": 4.0,
             "min": 2.0, "max": 10.0}],
        "candidates": [
            {"key": "Sketch|constraint|1", "object": "Sketch", "dimension": "locator_radius",
             "kind": "constraint", "value": 4.0},
            {"key": "Sketch|constraint|2", "object": "Sketch", "dimension": "new_dimension",
             "kind": "constraint", "value": 7.0}],
    }
    monkeypatch.setattr(adapter, "_call", lambda action, **kwargs: info)
    candidates = adapter.discover("design")
    assert [c.native["path"] for c in candidates] == [
        "Sketch|constraint|2", "Sketch|constraint|0"]
    assert candidates[-1].value == 4.0  # The registered name still resolves its value.


def test_native_preflight_isolates_each_changed_value(tmp_path, monkeypatch):
    source = tmp_path / "source.FCStd"
    source.write_bytes(b"stand-in for a real native document")
    width_key, noop_key = "Block|property|Length", "Cutter|property|Height"
    monkeypatch.setattr(native_bridge.native_cad, "_path", lambda model: source)
    monkeypatch.setattr(native_bridge.native_cad, "inspect", lambda model: {
        "parameters": [
            {"key": width_key, "name": "support_width", "value": 32.0},
            {"key": noop_key, "name": "ineffective_height", "value": 4.0},
        ]})

    def generate(request):
        assert request["action"] == "generate"
        target = Path(request["output"])
        target.mkdir()
        width = request["values"].get("support_width", 32.0)
        cq.exporters.export(cq.Workplane("XY").box(width, 20, 10), str(target / "native.step"))
        return {"decision": "REVIEW_REQUIRED"}

    monkeypatch.setattr(native_bridge.native_cad, "_run", generate)
    checks = native_bridge._preflight("design", {width_key: 38.0, noop_key: 6.0})
    assert [(c["code"], c["status"]) for c in checks] == [
        ("geometry_effect_" + width_key, "PASS"),
        ("geometry_effect_" + noop_key, "FAIL")]
