"""Portable catalog protection tests. Synthetic BREP text is not native proof."""

from copy import deepcopy
import json
import importlib.util
import os
from types import SimpleNamespace
from pathlib import Path

import pytest

from caelab.adapters import native_face_catalog as catalog_api
from caelab.storage import artifact_manifest


IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def synthetic_catalog(root):
    cad = root / "cad"
    faces = cad / "native_faces/faces"
    faces.mkdir(parents=True)
    (cad / "editable.FCStd").write_bytes(b"TEST_ONLY native source")
    (cad / "native.step").write_bytes(b"TEST_ONLY STEP source")
    (cad / "result.json").write_text(json.dumps({"cad_generated": True, "decision": "REVIEW_REQUIRED",
                                                "bom": [{"volume_mm3": 480}]}))
    (cad / "native_faces/body.brep").write_bytes(b"TEST_ONLY body BREP")
    (faces / "Face1.brep").write_bytes(b"TEST_ONLY face BREP")
    sources = {key: catalog_api._capture(root, name) for key, name in (
        ("editable", "cad/editable.FCStd"), ("step", "cad/native.step"), ("cad_result", "cad/result.json"))}
    body_brep = catalog_api._capture(root, "cad/native_faces/body.brep")
    face_brep = catalog_api._capture(root, "cad/native_faces/faces/Face1.brep")
    result = {"schema_version": "1.0", "kind": "native_face_catalog", "sources": sources,
              "native_object": {"name": "Box", "label": "Synthetic box", "type_id": "Part::Box",
                  "placement_matrix": IDENTITY[:], "global_placement_matrix": IDENTITY[:],
                  "ancestor_transform_matrix": IDENTITY[:]},
              "coordinate_systems": [{"id": catalog_api.FRAME_ID, "type": "cartesian", "unit": "mm",
                  "basis": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "origin": [0, 0, 0],
                  "label": catalog_api.FRAME_LABEL, "alignment": "UNKNOWN"}],
              "body": {"id": "B-final", "solid_count": 1, "volume_mm3": 480, "area_mm2": 392,
                  "center_mm": [6, 4, 2.5], "bounds_mm": {"min": [0, 0, 0], "max": [12, 8, 5]},
                  "brep": body_brep, "geometry_sha256": body_brep["sha256"]},
              "faces": [{"native_name": "Face1", "native_object": "Box", "body_id": "B-final",
                  "kind": "native_face", "roles": ["boundary", "load"], "unit": "mm",
                  "coordinate_system": catalog_api.FRAME_ID, "area_mm2": 40,
                  "center_mm": [0, 4, 2.5], "bounds_mm": {"min": [0, 0, 0], "max": [0, 8, 5]},
                  "surface_type": "Plane", "planar_normal_global": [-1, 0, 0],
                  "step_correspondence": "UNIQUE_GEOMETRY_MATCH", "brep": face_brep,
                  "geometry_sha256": face_brep["sha256"]}],
              "geometry_verification": {"status": "PASS", "tolerances": catalog_api.GEOMETRY_TOLERANCES.copy(),
                  "method": "OpenCASCADE solid symmetric difference and unique face common-area correspondence",
                  "symmetric_difference_mm3": 0, "native_face_count": 1, "step_face_count": 1,
                  "native_volume_mm3": 480, "step_volume_mm3": 480},
              "native_runtime": {"freecad_version": ["TEST_ONLY"]},
              "physical_qualification": "UNKNOWN"}
    reseal(result)
    publish(root, result)
    return result


def reseal(catalog):
    revision = catalog_api.revision_identity(catalog)
    catalog["native_catalog_revision"] = revision
    for face in catalog["faces"]:
        face["id"] = f"F-{revision}-{face['native_name']}"


def publish(root, catalog):
    (root / catalog_api.CATALOG_PATH).write_text(json.dumps(catalog, allow_nan=False), encoding="utf-8")
    return {"cad_revision": "a" * 64, "artifacts": artifact_manifest(root, revision="a" * 64)}


@pytest.fixture
def recorded(tmp_path):
    catalog = synthetic_catalog(tmp_path)
    return tmp_path, catalog, publish(tmp_path, catalog)


def test_stored_native_faces_require_no_freecad_or_worker(recorded, monkeypatch):
    root, catalog, parent = recorded
    monkeypatch.delenv("FREECAD_CMD", raising=False)
    monkeypatch.setattr(catalog_api, "build_face_catalog", lambda *args: pytest.fail("Native work during read"))
    before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    assert catalog_api.read_face_catalog(root, parent) == catalog
    assert before == {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_historical_absence_stays_absent_and_unmanifested_catalog_is_refused(tmp_path):
    assert catalog_api.read_face_catalog(tmp_path, {"artifacts": []}) is None
    synthetic_catalog(tmp_path)
    with pytest.raises(ValueError, match="manifested"):
        catalog_api.read_face_catalog(tmp_path, {"artifacts": []})


@pytest.mark.parametrize("name", ["cad/editable.FCStd", "cad/native.step", "cad/result.json",
                                   "cad/native_faces/body.brep", "cad/native_faces/faces/Face1.brep",
                                   catalog_api.CATALOG_PATH])
def test_original_source_and_brep_tampering_is_refused(recorded, name):
    root, _, parent = recorded
    (root / name).write_bytes(b"changed")
    with pytest.raises(ValueError, match="bytes changed|manifest/revision"):
        catalog_api.read_face_catalog(root, parent)


@pytest.mark.parametrize("change", ["duplicate", "missing", "revision", "size"])
def test_original_manifest_identity_is_required(recorded, change):
    root, _, parent = recorded
    row = next(item for item in parent["artifacts"] if item["path"] == "cad/native_faces/faces/Face1.brep")
    if change == "duplicate":
        parent["artifacts"].append(deepcopy(row))
    elif change == "missing":
        parent["artifacts"].remove(row)
    elif change == "revision":
        row["revision"] = "b" * 64
    else:
        row["size_bytes"] += 1
    with pytest.raises(ValueError, match="manifest/revision"):
        catalog_api.read_face_catalog(root, parent)


@pytest.mark.parametrize("change", [
    lambda c: c["faces"][0].update(native_name="Face2"),
    lambda c: c["faces"][0].update(native_object="Other"),
    lambda c: c["faces"][0].update(id="Face1"),
    lambda c: c["faces"][0].update(kind="triangle"),
    lambda c: c["faces"][0].update(area_mm2=True),
    lambda c: c["faces"][0].update(planar_normal_global=[0, 0, 2]),
    lambda c: c["faces"][0].update(geometry_sha256="f" * 64),
    lambda c: c["body"].update(solid_count=2),
    lambda c: c["body"].update(solid_count=True),
    lambda c: c["body"].update(volume_mm3=10 ** 400),
    lambda c: c["geometry_verification"].update(symmetric_difference_mm3=1),
    lambda c: c["geometry_verification"].update(step_face_count=2),
    lambda c: c["geometry_verification"].update(step_volume_mm3=True),
    lambda c: c["coordinate_systems"][0].update(alignment="VERIFIED"),
    lambda c: c["coordinate_systems"][0]["basis"][0].__setitem__(0, True),
    lambda c: c.pop("native_runtime"),
    lambda c: c["sources"]["editable"].update(path="../original.FCStd"),
])
def test_misleading_or_malformed_face_contract_is_refused(recorded, change):
    root, catalog, _ = recorded
    change(catalog)
    parent = publish(root, catalog)
    with pytest.raises(ValueError):
        catalog_api.read_face_catalog(root, parent)


def test_new_source_bytes_get_new_face_ids_without_rebinding_old_ids(recorded):
    root, original, _ = recorded
    changed = deepcopy(original)
    (root / "cad/editable.FCStd").write_bytes(b"TEST_ONLY different revision")
    changed["sources"]["editable"] = catalog_api._capture(root, "cad/editable.FCStd")
    reseal(changed)
    assert changed["faces"][0]["id"] != original["faces"][0]["id"]
    assert catalog_api.read_face_catalog(root, publish(root, changed)) == changed


def test_symlinked_face_is_refused_even_with_matching_target_bytes(recorded, tmp_path):
    root, _, parent = recorded
    path = root / "cad/native_faces/faces/Face1.brep"
    external = tmp_path / "outside.brep"
    external.write_bytes(path.read_bytes())
    path.unlink()
    try:
        path.symlink_to(external)
    except OSError:
        pytest.skip("The test environment cannot create symbolic links")
    with pytest.raises(ValueError, match="symbolic links|outside"):
        catalog_api.read_face_catalog(root, parent)


def test_second_pass_refuses_a_source_changed_during_read(recorded, monkeypatch):
    root, _, parent = recorded
    capture = catalog_api._capture
    calls = 0

    def changing_capture(current_root, name, **kwargs):
        nonlocal calls
        result = capture(current_root, name, **kwargs)
        calls += 1
        if calls == 5:
            (root / "cad/native.step").write_bytes(b"late source drift")
        return result

    monkeypatch.setattr(catalog_api, "_capture", changing_capture)
    with pytest.raises(ValueError, match="bytes changed"):
        catalog_api.read_face_catalog(root, parent)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e309}',
                               b"[" * 42 + b"0" + b"]" * 42])
def test_duplicate_nonfinite_and_deep_json_are_refused(raw):
    with pytest.raises(ValueError):
        catalog_api._json_bytes(raw)


def test_byte_limit_is_checked_before_parsing():
    with pytest.raises(ValueError, match="byte limit"):
        catalog_api._json_bytes(b"[] ", maximum=2)


def test_rehashed_cad_result_that_disagrees_with_native_body_is_refused(recorded):
    root, catalog, _ = recorded
    path = root / "cad/result.json"
    raw = json.loads(path.read_text())
    raw["bom"][0]["volume_mm3"] = 481
    path.write_text(json.dumps(raw))
    catalog["sources"]["cad_result"] = catalog_api._capture(root, "cad/result.json")
    reseal(catalog)
    with pytest.raises(ValueError, match="preserved CAD result"):
        catalog_api.read_face_catalog(root, publish(root, catalog))


def test_native_condition_hook_preserves_faces_and_explicit_same_document_frame(recorded):
    from caelab.adapters.cad_condition_catalog import native_final_solid_catalog

    root, original, parent = recorded
    parent["provenance"] = {"cad_model": "native:TEST_ONLY"}
    catalog = native_final_solid_catalog(root, parent, backend="fixture.freecad")
    assert catalog["selections"][0]["id"] == "B-final"
    assert catalog["selections"][0]["roles"] == ["material"]
    face = catalog["selections"][1]
    assert face["id"] == original["faces"][0]["id"]
    assert face["brep"] == original["faces"][0]["brep"]
    assert face["coordinate_system"] == "global"
    assert face["native_coordinate_system"] == "cad_document_global"
    assert catalog["coordinate_systems"][0]["alignment"] == "UNKNOWN"
    assert catalog["native_frame_mapping"]["sensor_world_alignment"] == "UNKNOWN"
    assert catalog["native_face_context"]["coordinate_systems"] == original["coordinate_systems"]
    assert catalog["native_face_context"]["native_object"] == original["native_object"]
    assert len(catalog["native_face_policy_sha256"]) == 64
    assert original["faces"][0]["coordinate_system"] == "cad_document_global"


def test_native_catalog_requires_actual_parent_revision(recorded):
    root, _, parent = recorded
    parent.pop("cad_revision")
    with pytest.raises(ValueError, match="original CAD revision"):
        catalog_api.read_face_catalog(root, parent)


def test_native_condition_hook_without_catalog_keeps_historical_whole_solid(recorded):
    from caelab.adapters.cad_condition_catalog import final_solid_catalog, native_final_solid_catalog

    root, _, parent = recorded
    (root / catalog_api.CATALOG_PATH).unlink()
    parent["artifacts"] = [item for item in parent["artifacts"] if item["path"] != catalog_api.CATALOG_PATH]
    parent["provenance"] = {"cad_model": "native:TEST_ONLY"}
    assert native_final_solid_catalog(root, parent, backend="fixture.freecad") == final_solid_catalog(root, parent, backend="fixture.freecad")


def test_new_successful_freecad_generation_calls_catalog_before_outcome(tmp_path, monkeypatch):
    from caelab.adapters.fixture_freecad import FixtureFreeCADAdapter

    adapter = FixtureFreeCADAdapter(tmp_path)
    native = {"cad_generated": True, "decision": "REVIEW_REQUIRED", "bounds_mm": [12, 8, 5],
              "bom": [{"volume_mm3": 480}], "checks": [], "cad_checks": [], "source_sha256": "a" * 64}
    monkeypatch.setattr(adapter, "_call", lambda *args, **kwargs: native)
    calls = []
    monkeypatch.setattr(catalog_api, "build_face_catalog", lambda output: calls.append(output))
    output = tmp_path / "cad"
    result = adapter.regenerate("native:TEST_ONLY", {}, output)
    assert calls == [output]
    assert result.generated is True
    assert result.metrics["cad_volume"] == {"value": 480, "unit": "mm^3", "valid": True}
    assert result.source_sha256 == native["source_sha256"]


def test_rejected_generation_skips_capture_and_catalog_failure_blocks_success(tmp_path, monkeypatch):
    from caelab.adapters.fixture_freecad import FixtureFreeCADAdapter

    adapter = FixtureFreeCADAdapter(tmp_path)
    native = {"cad_generated": False, "decision": "REJECTED", "checks": [], "cad_checks": [], "source_sha256": "a" * 64}
    monkeypatch.setattr(adapter, "_call", lambda *args, **kwargs: native)
    monkeypatch.setattr(catalog_api, "build_face_catalog", lambda output: pytest.fail("Rejected CAD reached native face work"))
    assert adapter.regenerate("native:TEST_ONLY", {}, tmp_path / "cad").generated is False
    native["cad_generated"] = True

    def fail(output):
        raise ValueError("Native/STEP mismatch")

    monkeypatch.setattr(catalog_api, "build_face_catalog", fail)
    with pytest.raises(ValueError, match="mismatch"):
        adapter.regenerate("native:TEST_ONLY", {}, tmp_path / "cad")


@pytest.mark.parametrize("common_area", [0, 1e-10])
def test_zero_or_partial_common_area_never_matches_a_small_native_face(common_area):
    # Proxy geometry isolates the tolerance regression. It is not native proof;
    # the real retained box test separately checks full OCC face correspondence.
    worker_path = Path(catalog_api.__file__).with_name("freecad_face_catalog_worker.py")
    spec = importlib.util.spec_from_file_location("native_face_tolerance_control", worker_path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)

    class Intersection:
        Area = common_area
        Volume = 1e-12

        def isNull(self):
            return self.Area == 0

        def isValid(self):
            return True

    class Shape:
        Volume = 1e-12
        Area = 1e-9
        CenterOfMass = SimpleNamespace(x=0, y=0, z=0)
        BoundBox = SimpleNamespace(XMin=0, XMax=1e-5, YMin=0, YMax=1e-5, ZMin=0, ZMax=1e-5)
        Surface = SimpleNamespace()
        Edges = []
        Vertexes = []

        def __init__(self):
            self.Solids, self.Faces = [self], [self]

        def isNull(self):
            return False

        def isValid(self):
            return True

        def cut(self, other):
            return Intersection()

        def common(self, other):
            return Intersection()

    with pytest.raises(ValueError, match="unique geometric STEP correspondence"):
        worker._verify_geometry(Shape(), Shape(), catalog_api.GEOMETRY_TOLERANCES)


@pytest.mark.skipif(os.name != "posix", reason="New native capture requires its existing POSIX runtime")
def test_existing_catalog_cannot_be_overwritten(recorded, monkeypatch):
    root, _, _ = recorded
    monkeypatch.setenv("FREECAD_CMD", "/not-launched")
    with pytest.raises(FileExistsError):
        catalog_api.build_face_catalog(root / "cad")
