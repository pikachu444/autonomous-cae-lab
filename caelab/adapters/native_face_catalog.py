"""Revision-owned FreeCAD face artifacts; stored reading needs no native runtime.

Only a successful upstream CAD output can acquire this optional catalog.  The
worker reads the retained editable document and STEP, never the mutable model.
Native face identity, geometry observation and engineering admission are separate.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys

CATALOG_PATH = "cad/native_faces/catalog.json"
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
MAX_FACES = 4096
FRAME_ID = "cad_document_global"
FRAME_LABEL = "FreeCAD document global Cartesian basis; sensor/world alignment UNKNOWN"
GEOMETRY_TOLERANCES = {"length_mm": 1e-7, "area_mm2": 1e-7,
                       "volume_mm3": 1e-7, "relative": 1e-8}
SHA256 = re.compile(r"^[a-f0-9]{64}$")


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _json_bytes(raw, *, maximum=MAX_JSON_BYTES):
    if not raw or len(raw) > maximum:
        raise ValueError("Native face JSON exceeds its byte limit")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate native face JSON key")
            result[key] = value
        return result

    def refuse_constant(value):
        raise ValueError("Nonfinite native face JSON number")

    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=refuse_constant)
        queue = [(result, 0)]
        while queue:
            value, depth = queue.pop()
            if depth > 40:
                raise ValueError("Native face JSON is too deeply nested")
            if isinstance(value, dict):
                queue.extend((child, depth + 1) for child in value.values())
            elif isinstance(value, list):
                queue.extend((child, depth + 1) for child in value)
            elif isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Nonfinite native face JSON number")
        return result
    except (RecursionError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid native face JSON") from error


def _hash_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _file(root, name):
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("Invalid native face artifact path")
    relative = PurePosixPath(name)
    if relative.is_absolute() or relative.as_posix() != name or any(part in (".", "..") for part in relative.parts):
        raise ValueError("Invalid native face artifact path")
    path = Path(root)
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Native face artifacts must not be symbolic links")
    if not path.resolve().is_relative_to(Path(root).resolve()) or not path.is_file():
        raise ValueError("Native face artifact is missing or outside its experiment")
    return path


def _capture(root, name, *, maximum=MAX_ARTIFACT_BYTES):
    path = _file(root, name)
    if path.stat().st_size > maximum:
        raise ValueError("Native face artifact exceeds its byte limit")
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if size > maximum:
                raise ValueError("Native face artifact exceeds its byte limit")
            digest.update(chunk)
    return {"path": name, "sha256": digest.hexdigest(), "size_bytes": size}


def _vector(value, size=3):
    return isinstance(value, list) and len(value) == size and all(_finite(item) for item in value)


def _bounds(value):
    return (isinstance(value, dict) and set(value) == {"min", "max"}
            and _vector(value["min"]) and _vector(value["max"])
            and all(low <= high for low, high in zip(value["min"], value["max"])))


def _artifact(value, expected=None):
    if (not isinstance(value, dict) or set(value) != {"path", "sha256", "size_bytes"}
            or not isinstance(value["path"], str)
            or not isinstance(value["sha256"], str) or not SHA256.fullmatch(value["sha256"])
            or type(value["size_bytes"]) is not int or not 0 < value["size_bytes"] <= MAX_ARTIFACT_BYTES
            or (expected is not None and value["path"] != expected)):
        raise ValueError("Invalid native face source/artifact identity")


def revision_identity(catalog):
    """The namespace binds exact retained bytes and actual native geometry."""
    return _hash_json({"schema_version": catalog["schema_version"], "sources": catalog["sources"],
                       "native_object": catalog["native_object"],
                       "body_geometry_sha256": catalog["body"]["geometry_sha256"],
                       "face_geometry_sha256": [face["geometry_sha256"] for face in catalog["faces"]]})


def validate_catalog(catalog):
    """Validate the portable shape only.  This is not a native/physical verdict."""
    if (not isinstance(catalog, dict) or catalog.get("schema_version") != "1.0"
            or catalog.get("kind") != "native_face_catalog"
            or catalog.get("coordinate_systems") != [{"id": FRAME_ID, "type": "cartesian", "unit": "mm",
                "basis": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "origin": [0, 0, 0], "label": FRAME_LABEL,
                "alignment": "UNKNOWN"}]
            or catalog.get("physical_qualification") != "UNKNOWN"):
        raise ValueError("Invalid native face catalog envelope/frame")
    frame = catalog["coordinate_systems"][0]
    if not _vector(frame["origin"]) or any(not _vector(row) for row in frame["basis"]):
        raise ValueError("Native face basis/origin must contain finite numeric components")
    runtime = catalog.get("native_runtime")
    if (not isinstance(runtime, dict) or set(runtime) != {"freecad_version"}
            or not isinstance(runtime["freecad_version"], list) or not 1 <= len(runtime["freecad_version"]) <= 32
            or any(not isinstance(item, str) or not 1 <= len(item) <= 512 for item in runtime["freecad_version"])):
        raise ValueError("The native face producer version is missing")
    sources = catalog.get("sources")
    if not isinstance(sources, dict) or set(sources) != {"editable", "step", "cad_result"}:
        raise ValueError("Native face catalog requires its original CAD artifacts")
    for key, name in (("editable", "cad/editable.FCStd"), ("step", "cad/native.step"),
                      ("cad_result", "cad/result.json")):
        _artifact(sources[key], name)
    native = catalog.get("native_object")
    if (not isinstance(native, dict) or not isinstance(native.get("name"), str)
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", native["name"])
            or not isinstance(native.get("label"), str) or not isinstance(native.get("type_id"), str)
            or not all(_vector(native.get(key), 16) for key in
                       ("placement_matrix", "global_placement_matrix", "ancestor_transform_matrix"))):
        raise ValueError("Invalid selected native final object/placement")
    body = catalog.get("body")
    if (not isinstance(body, dict) or body.get("id") != "B-final"
            or type(body.get("solid_count")) is not int or body["solid_count"] != 1
            or not _finite(body.get("volume_mm3")) or body["volume_mm3"] <= 0
            or not _finite(body.get("area_mm2")) or body["area_mm2"] <= 0
            or not _vector(body.get("center_mm")) or not _bounds(body.get("bounds_mm"))):
        raise ValueError("Invalid single native solid observation")
    _artifact(body.get("brep"), "cad/native_faces/body.brep")
    if body.get("geometry_sha256") != body["brep"]["sha256"]:
        raise ValueError("Native body geometry fingerprint differs from its BREP")
    verification = catalog.get("geometry_verification")
    if (not isinstance(verification, dict) or verification.get("status") != "PASS"
            or verification.get("tolerances") != GEOMETRY_TOLERANCES
            or verification.get("method") != "OpenCASCADE solid symmetric difference and unique face common-area correspondence"
            or not _finite(verification.get("symmetric_difference_mm3"))
            or verification["symmetric_difference_mm3"] < 0
            or verification["symmetric_difference_mm3"] > max(GEOMETRY_TOLERANCES["volume_mm3"],
                GEOMETRY_TOLERANCES["relative"] * body["volume_mm3"])):
        raise ValueError("Native/STEP geometry correspondence is not verified")
    for key in ("native_volume_mm3", "step_volume_mm3"):
        value = verification.get(key)
        if (not _finite(value) or value <= 0
                or abs(value - body["volume_mm3"]) > max(GEOMETRY_TOLERANCES["volume_mm3"],
                    GEOMETRY_TOLERANCES["relative"] * body["volume_mm3"])):
            raise ValueError("Native/STEP observed volume differs from the catalog body")
    faces = catalog.get("faces")
    if not isinstance(faces, list) or not 1 <= len(faces) <= MAX_FACES:
        raise ValueError("Invalid native face count")
    if (type(verification.get("native_face_count")) is not int
            or verification["native_face_count"] != len(faces)
            or type(verification.get("step_face_count")) is not int
            or verification["step_face_count"] != len(faces)):
        raise ValueError("Native and STEP face counts differ")
    for index, face in enumerate(faces, 1):
        name = f"Face{index}"
        if (not isinstance(face, dict) or face.get("native_name") != name
                or face.get("native_object") != native["name"] or face.get("body_id") != "B-final"
                or face.get("kind") != "native_face" or face.get("roles") != ["boundary", "load"]
                or face.get("unit") != "mm" or face.get("coordinate_system") != FRAME_ID
                or not _finite(face.get("area_mm2")) or face["area_mm2"] <= 0
                or not _vector(face.get("center_mm")) or not _bounds(face.get("bounds_mm"))
                or not isinstance(face.get("surface_type"), str) or not face["surface_type"]
                or face.get("step_correspondence") != "UNIQUE_GEOMETRY_MATCH"):
            raise ValueError("Invalid native FaceN observation")
        _artifact(face.get("brep"), f"cad/native_faces/faces/{name}.brep")
        if face.get("geometry_sha256") != face["brep"]["sha256"]:
            raise ValueError("Native face geometry fingerprint differs from its BREP")
        if "planar_normal_global" in face:
            normal = face["planar_normal_global"]
            if (face["surface_type"] != "Plane" or not _vector(normal)
                    or abs(sum(component * component for component in normal) - 1) > 1e-10):
                raise ValueError("Invalid native planar normal")
    revision = revision_identity(catalog)
    if catalog.get("native_catalog_revision") != revision:
        raise ValueError("Native face catalog revision changed")
    if any(face.get("id") != f"F-{revision}-{face['native_name']}" for face in faces):
        raise ValueError("Native FaceN identity is not bound to this revision")
    return catalog


def _all_files(catalog):
    return [*catalog["sources"].values(), catalog["body"]["brep"],
            *(face["brep"] for face in catalog["faces"])]


def _verify_files(root, catalog, manifest=None, revision=None):
    for expected in _all_files(catalog):
        if _capture(root, expected["path"]) != expected:
            raise ValueError("Native face source or BREP bytes changed")
        if manifest is not None:
            entries = [entry for entry in manifest if entry.get("path") == expected["path"]]
            if (len(entries) != 1 or any(entries[0].get(key) != expected[key] for key in expected)
                    or entries[0].get("revision") != revision):
                raise ValueError("Native face artifact differs from its original manifest/revision")


def _verified_metadata(cad):
    bom = cad.get("bom") if isinstance(cad, dict) else None
    if (not isinstance(cad, dict) or cad.get("cad_generated") is not True
            or cad.get("decision") != "REVIEW_REQUIRED" or not isinstance(bom, list) or len(bom) != 1
            or not isinstance(bom[0], dict) or not _finite(bom[0].get("volume_mm3"))
            or bom[0]["volume_mm3"] <= 0):
        raise ValueError("Only a successful single-solid CAD output supports native face capture")


def build_face_catalog(cad_output: Path) -> dict:
    """Append a new catalog to a newly generated output; never overwrite one.

    Uses the existing configured FreeCADCmd and a fixed trusted worker, with an
    owned POSIX process group and the existing 150-second native worker budget.
    The fresh native_faces directory also retains request, logs and worker result
    on failure.  Failure does not advertise a usable catalog.
    """
    from ..contracts import CapabilityUnavailable
    from ..execution_control import run_owned_command
    cad_output = Path(cad_output)
    if cad_output.is_symlink() or not cad_output.is_dir():
        raise ValueError("Native face capture needs a new CAD output directory")
    cad_output = cad_output.resolve()
    # All paths in this artifact are experiment-relative under the standard cad/.
    root = cad_output.parent
    if cad_output.name != "cad":
        raise ValueError("Native face capture requires the existing cad output namespace")
    _verified_metadata(_json_bytes(_file(root, "cad/result.json").read_bytes()))
    sources = {key: _capture(root, name) for key, name in (("editable", "cad/editable.FCStd"),
               ("step", "cad/native.step"), ("cad_result", "cad/result.json"))}
    command = os.environ.get("FREECAD_CMD") or shutil.which("freecadcmd") or shutil.which("FreeCADCmd")
    if not command:
        raise CapabilityUnavailable("FreeCADCmd is required for new native face capture")
    if os.name != "posix":
        raise CapabilityUnavailable("New native face capture uses the existing owned POSIX FreeCAD runtime")
    stage = cad_output / "native_faces"
    stage.mkdir(exist_ok=False)
    request = {"schema_version": "1.0", "experiment_root": str(root), "sources": sources,
               "output": str(stage)}
    request_path = stage / "request.json"
    request_bytes = json.dumps(request, allow_nan=False).encode()
    with request_path.open("xb") as stream:
        stream.write(request_bytes)
    run = run_owned_command([sys.executable, str(Path(__file__).resolve()),
                             "--launch", str(request_path)], stage, "freecad_faces", timeout=150)
    result = _json_bytes(_file(stage, "worker-result.json").read_bytes())
    if run.returncode or not isinstance(result, dict) or result.get("ok") is not True:
        reason = result.get("error", "Native face worker failed") if isinstance(result, dict) else "Native face worker failed"
        raise ValueError(str(reason))
    catalog = validate_catalog(_json_bytes(_file(root, CATALOG_PATH).read_bytes()))
    if catalog["sources"] != sources:
        raise ValueError("Native face worker changed its captured CAD identity")
    if _file(stage, "request.json").read_bytes() != request_bytes:
        raise ValueError("Native face capture request changed during execution")
    _verify_files(root, catalog)
    return catalog


def read_face_catalog(parent_root: Path, parent: dict) -> dict | None:
    """Read hash-bound retained native faces; historical absence stays absent."""
    root = Path(parent_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Invalid native face experiment directory")
    root = root.resolve()
    manifest = parent.get("artifacts")
    if not isinstance(manifest, list) or any(not isinstance(item, dict) for item in manifest):
        raise ValueError("Native faces require the original artifact manifest")
    entries = [item for item in manifest if item.get("path") == CATALOG_PATH]
    exists = (root / CATALOG_PATH).exists() or (root / CATALOG_PATH).is_symlink()
    if not entries and not exists:
        return None
    if len(entries) != 1:
        raise ValueError("Native face catalog is not uniquely manifested")
    if not isinstance(parent.get("cad_revision"), str) or not SHA256.fullmatch(parent["cad_revision"]):
        raise ValueError("Native face catalog requires its original CAD revision")
    entry = entries[0]
    path = _file(root, CATALOG_PATH)
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("Native face catalog exceeds its byte limit")
    raw = path.read_bytes()
    captured = {"path": CATALOG_PATH, "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
    if any(entry.get(key) != captured[key] for key in captured) or entry.get("revision") != parent.get("cad_revision"):
        raise ValueError("Native face catalog differs from its original manifest/revision")
    catalog = validate_catalog(_json_bytes(raw))
    _verify_files(root, catalog, manifest, parent.get("cad_revision"))
    cad = _json_bytes(_file(root, "cad/result.json").read_bytes())
    _verified_metadata(cad)
    declared_volume, volume = cad["bom"][0]["volume_mm3"], catalog["body"]["volume_mm3"]
    if abs(declared_volume - volume) > max(GEOMETRY_TOLERANCES["volume_mm3"], GEOMETRY_TOLERANCES["relative"] * volume):
        raise ValueError("Native face body differs from the preserved CAD result")
    # Recheck the whole collected set, including the catalog, after the last read.
    _verify_files(root, catalog, manifest, parent.get("cad_revision"))
    if _capture(root, CATALOG_PATH, maximum=MAX_JSON_BYTES) != captured:
        raise ValueError("Native face catalog changed during reading")
    return catalog


def _launch(request_path):
    """Child-only environment; exec retains the owned group and live process."""
    if os.name != "posix":
        raise RuntimeError("Owned native face worker launch requires POSIX")
    worker = Path(__file__).resolve().with_name("freecad_face_catalog_worker.py")
    request_path = Path(request_path)
    if request_path.is_symlink() or request_path.parent.resolve() != Path.cwd().resolve():
        raise ValueError("The native face request must remain in its owned working directory")
    request_path = request_path.resolve()
    _json_bytes(request_path.read_bytes(), maximum=1024 * 1024)
    command = os.environ.get("FREECAD_CMD") or shutil.which("freecadcmd") or shutil.which("FreeCADCmd")
    if not command or not worker.is_file():
        raise RuntimeError("The existing FreeCAD runtime or trusted face worker is unavailable")
    environment = {**os.environ, "CAELAB_FREECAD_FACE_CATALOG_WORKER": str(worker),
                   "CAELAB_FREECAD_FACE_REQUEST": str(request_path),
                   "CAELAB_FREECAD_FACE_RESULT": str(request_path.with_name("worker-result.json"))}
    os.execvpe(command, [command, str(worker)], environment)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--launch":
        raise SystemExit("Only the fixed native face worker launch is supported")
    _launch(sys.argv[2])
