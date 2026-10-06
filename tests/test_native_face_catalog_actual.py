"""Opt-in existing FreeCAD native geometry proof; no solver/provider/GUI proof."""

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys

import pytest

from caelab.adapters.native_face_catalog import build_face_catalog, read_face_catalog
from caelab.execution_control import run_owned_command
from caelab.storage import artifact_manifest


@pytest.mark.skipif(os.name != "posix" or not os.environ.get("FREECAD_CMD")
                    or os.environ.get("CAELAB_TEST_NATIVE_FACES") != "1",
                    reason="Requires explicit bounded native face test and the existing POSIX FreeCAD runtime")
def test_actual_rotated_box_faces_revision_repeatability_and_source_preservation(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    retained = {}
    catalogs = []
    for name, length in (("first", 12), ("revision", 14)):
        root = tmp_path / name
        root.mkdir()
        source = root / "original.FCStd"
        request = root / "fixture-request.json"
        request.write_text(json.dumps({"repo": str(repo), "source": str(source),
                                       "output": str(root / "cad"), "length_mm": length}))
        command = [sys.executable, str(repo / "tests/native_face_catalog_fixture_worker.py"), "--launch", str(request)]
        generated = run_owned_command(command, root, "public_box", timeout=150)
        assert generated.returncode == 0, generated.stderr
        metadata = json.loads((root / "cad/result.json").read_text())
        assert metadata["native_refusal_probes"] == {"isolated_vertex": True, "multiple_solids": True}
        retained.update({path: hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in (source, root / "cad/editable.FCStd", root / "cad/native.step", root / "cad/result.json")})
        catalog = build_face_catalog(root / "cad")
        assert len(catalog["faces"]) == 6
        assert [face["native_name"] for face in catalog["faces"]] == [f"Face{index}" for index in range(1, 7)]
        assert catalog["body"]["volume_mm3"] == pytest.approx(length * 8 * 5, abs=1e-7)
        cosine, sine = math.cos(math.pi / 6), math.sin(math.pi / 6)
        assert catalog["body"]["bounds_mm"]["min"] == pytest.approx([-11, 2, 3], abs=1e-7)
        assert catalog["body"]["bounds_mm"]["max"] == pytest.approx([-7 + length * cosine, 2 + length * sine + 8 * cosine, 8], abs=1e-7)
        assert catalog["body"]["center_mm"] == pytest.approx([-7 + length / 2 * cosine - 4 * sine,
                                                                 2 + length / 2 * sine + 4 * cosine, 5.5], abs=1e-7)
        assert all(face["surface_type"] == "Plane" and "planar_normal_global" in face for face in catalog["faces"])
        normals = [face["planar_normal_global"] for face in catalog["faces"]]
        for normal in ([cosine, sine, 0], [-cosine, -sine, 0], [-sine, cosine, 0],
                       [sine, -cosine, 0], [0, 0, 1], [0, 0, -1]):
            assert any(sum((a - b) ** 2 for a, b in zip(normal, actual)) < 1e-14 for actual in normals)
        revision = hashlib.sha256(name.encode()).hexdigest()
        parent = {"cad_revision": revision, "artifacts": artifact_manifest(root, revision=revision)}
        assert read_face_catalog(root, parent) == catalog
        catalogs.append(catalog)
    assert not set(face["id"] for face in catalogs[0]["faces"]) & set(face["id"] for face in catalogs[1]["faces"])
    repeated = tmp_path / "repeat"
    (repeated / "cad").mkdir(parents=True)
    for name in ("editable.FCStd", "native.step", "result.json"):
        shutil.copyfile(tmp_path / "first/cad" / name, repeated / "cad" / name)
    catalog = build_face_catalog(repeated / "cad")
    assert catalog["native_catalog_revision"] == catalogs[0]["native_catalog_revision"]
    assert [face["geometry_sha256"] for face in catalog["faces"]] == [face["geometry_sha256"] for face in catalogs[0]["faces"]]
    mismatch = tmp_path / "mismatch"
    (mismatch / "cad").mkdir(parents=True)
    for name in ("editable.FCStd", "native.step", "result.json"):
        shutil.copyfile(tmp_path / "first/cad" / name, mismatch / "cad" / name)
    shutil.copyfile(tmp_path / "revision/cad/native.step", mismatch / "cad/native.step")
    with pytest.raises(ValueError, match="Native and STEP volume differ"):
        build_face_catalog(mismatch / "cad")
    assert not (mismatch / "cad/native_faces/catalog.json").exists()
    assert retained == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in retained}
