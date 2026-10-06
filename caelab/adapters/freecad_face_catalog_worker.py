"""Read-only final FCStd FaceN capture in the configured FreeCAD process.

The upstream generator remains responsible for regeneration/export checks. This
worker adds native geometry observations to its successful retained output and
requires actual geometry correspondence with the retained STEP. Face enumeration
comes only from the selected native object, never from a tessellation or STEP.
"""

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re


def _worker_path():
    if "__file__" in globals():
        worker = Path(__file__).resolve()
    else:
        expected = os.environ.get("CAELAB_FREECAD_FACE_CATALOG_WORKER")
        actual = os.environ.get("FIXTURE_FREECAD_SCRIPT")
        if (not expected or not actual or not Path(expected).is_absolute()
                or not Path(actual).is_absolute() or Path(expected).resolve() != Path(actual).resolve()):
            raise RuntimeError("The fixed native face worker entry is missing or mismatched")
        worker = Path(expected).resolve()
    if (worker.name != "freecad_face_catalog_worker.py" or worker.parent.name != "adapters"
            or worker.parent.parent.name != "caelab" or not worker.is_file()):
        raise RuntimeError("The trusted native face worker path is invalid")
    return worker


def _helpers(worker):
    path = worker.with_name("native_face_catalog.py")
    spec = importlib.util.spec_from_file_location("caelab_native_faces_pure_helpers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _vector(value):
    return [float(value.x), float(value.y), float(value.z)]


def _matrix(placement):
    matrix = placement.toMatrix()
    return [float(getattr(matrix, f"A{row}{column}")) for row in range(1, 5) for column in range(1, 5)]


def _bounds(shape):
    box = shape.BoundBox
    return {"min": [float(box.XMin), float(box.YMin), float(box.ZMin)],
            "max": [float(box.XMax), float(box.YMax), float(box.ZMax)]}


def _solid(shape, name):
    if (shape.isNull() or not shape.isValid() or len(shape.Solids) != 1
            or not math.isfinite(shape.Volume) or shape.Volume <= 0
            or len(shape.Faces) != len(shape.Solids[0].Faces)
            or len(shape.Edges) != len(shape.Solids[0].Edges)
            or len(shape.Vertexes) != len(shape.Solids[0].Vertexes)):
        raise ValueError(name + " must consist of one valid positive-volume solid")
    return shape.Solids[0]


def _close(first, second, absolute, relative):
    return (math.isfinite(first) and math.isfinite(second)
            and abs(first - second) <= max(absolute, relative * max(abs(first), abs(second))))


def _face_metric(face):
    return {"area_mm2": float(face.Area), "center_mm": _vector(face.CenterOfMass),
            "bounds_mm": _bounds(face), "surface_type": type(face.Surface).__name__}


def _candidate(first, second, limits):
    # Numeric pruning is only a preliminary candidate test. Actual common-area
    # geometry is required below; equal area/centroid/bounds alone never suffice.
    return (_close(first["area_mm2"], second["area_mm2"], limits["area_mm2"], limits["relative"])
            and all(_close(a, b, limits["length_mm"], limits["relative"])
                    for a, b in zip(first["center_mm"], second["center_mm"]))
            and all(_close(a, b, limits["length_mm"], limits["relative"])
                    for key in ("min", "max")
                    for a, b in zip(first["bounds_mm"][key], second["bounds_mm"][key])))


def _verify_geometry(native, step, limits):
    source, exchange = _solid(native, "Selected native final shape"), _solid(step, "Native STEP")
    if len(native.Faces) != len(step.Faces):
        raise ValueError("Native and STEP face partitions differ; no face catalog is admitted")
    if not _close(source.Volume, exchange.Volume, limits["volume_mm3"], limits["relative"]):
        raise ValueError("Native and STEP volume differ")
    source_bounds, exchange_bounds = _bounds(source), _bounds(exchange)
    if any(not _close(a, b, limits["length_mm"], limits["relative"])
           for key in ("min", "max") for a, b in zip(source_bounds[key], exchange_bounds[key])):
        raise ValueError("Native and STEP document-global bounds differ")
    differences = [source.cut(exchange), exchange.cut(source)]
    if any(not shape.isNull() and not shape.isValid() for shape in differences):
        raise ValueError("Native/STEP Boolean geometry comparison is invalid")
    difference = sum(float(shape.Volume) for shape in differences)
    if (not math.isfinite(difference) or difference < 0
            or difference > max(limits["volume_mm3"], limits["relative"] * source.Volume)):
        raise ValueError("Native and STEP solid geometry differ")
    metrics = [_face_metric(face) for face in step.Faces]
    used = set()
    for native_face in native.Faces:
        metric = _face_metric(native_face)
        matches = []
        for index, (step_face, step_metric) in enumerate(zip(step.Faces, metrics)):
            if _candidate(metric, step_metric, limits):
                common = native_face.common(step_face)
                if not common.isNull() and not common.isValid():
                    raise ValueError("Native/STEP face comparison is invalid")
                # Absolute tolerances may prune tiny-face candidates, but an
                # empty or partial intersection can never establish identity.
                if (not common.isNull() and common.Area > 0
                        and abs(common.Area / native_face.Area - 1) <= limits["relative"]
                        and abs(common.Area / step_face.Area - 1) <= limits["relative"]):
                    matches.append(index)
        if len(matches) != 1 or matches[0] in used:
            raise ValueError("A native face has no unique geometric STEP correspondence")
        used.add(matches[0])
    return {"status": "PASS", "method": "OpenCASCADE solid symmetric difference and unique face common-area correspondence",
            "tolerances": limits, "symmetric_difference_mm3": difference,
            "native_volume_mm3": float(source.Volume), "step_volume_mm3": float(exchange.Volume),
            "native_face_count": len(native.Faces), "step_face_count": len(step.Faces)}


def capture(request, helpers):
    import FreeCAD as App
    import Part

    if not isinstance(request, dict) or set(request) != {"schema_version", "experiment_root", "sources", "output"}:
        raise ValueError("Invalid native face worker request")
    root = Path(request["experiment_root"])
    output = Path(request["output"])
    if (request["schema_version"] != "1.0" or not root.is_absolute() or root.is_symlink()
            or not output.is_absolute() or output.is_symlink()
            or output.resolve() != (root.resolve() / "cad/native_faces")
            or not output.is_dir() or not isinstance(request["sources"], dict)
            or set(request["sources"]) != {"editable", "step", "cad_result"}):
        raise ValueError("Native face worker needs its private output and captured source paths")
    root, output = root.resolve(), output.resolve()
    if any((output / name).exists() or (output / name).is_symlink() for name in
           ("body.brep", "faces", "catalog.json")):
        raise ValueError("Native face geometry output must be fresh")
    for key, expected in (("editable", "cad/editable.FCStd"), ("step", "cad/native.step"),
                          ("cad_result", "cad/result.json")):
        helpers._artifact(request["sources"][key], expected)
        if helpers._capture(root, expected) != request["sources"][key]:
            raise ValueError("Captured native CAD source changed before face inspection")
    helpers._verified_metadata(helpers._json_bytes(helpers._file(root, "cad/result.json").read_bytes()))
    document = App.openDocument(str(helpers._file(root, "cad/editable.FCStd")))
    try:
        configuration = document.getObject("FixtureConfiguration")
        if configuration is None or not hasattr(configuration, "Definition"):
            raise ValueError("The retained upstream document has no selected final object")
        registry = helpers._json_bytes(configuration.Definition.encode(), maximum=1024 * 1024)
        final_name = registry.get("final") if isinstance(registry, dict) else None
        if not isinstance(final_name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", final_name):
            raise ValueError("The selected native final object is missing")
        final = document.getObject(final_name)
        if final is None or not hasattr(final, "Shape"):
            raise ValueError("The selected native final object has no shape")
        # Shape already carries the object's local placement. Only the ancestor
        # transform is added. No recompute, save, mesh or source mutation occurs.
        global_placement = final.getGlobalPlacement()
        ancestor = global_placement.multiply(final.Placement.inverse())
        shape = final.Shape.copy()
        shape.Placement = ancestor.multiply(shape.Placement)
        solid = _solid(shape, "Selected native final shape")
        if not 1 <= len(shape.Faces) <= helpers.MAX_FACES:
            raise ValueError("The selected final shape exceeds the native face catalog limit")
        step = Part.read(str(helpers._file(root, "cad/native.step")))
        verification = _verify_geometry(shape, step, helpers.GEOMETRY_TOLERANCES.copy())
        faces_directory = output / "faces"
        faces_directory.mkdir(exist_ok=False)
        shape.exportBrep(str(output / "body.brep"))
        body_brep = helpers._capture(root, "cad/native_faces/body.brep")
        body = {"id": "B-final", "solid_count": 1, "volume_mm3": float(solid.Volume),
                "area_mm2": float(solid.Area), "center_mm": _vector(solid.CenterOfMass),
                "bounds_mm": _bounds(solid), "geometry_sha256": body_brep["sha256"], "brep": body_brep}
        faces = []
        for index, face in enumerate(shape.Faces, 1):
            name = f"Face{index}"
            face.exportBrep(str(faces_directory / f"{name}.brep"))
            brep = helpers._capture(root, f"cad/native_faces/faces/{name}.brep")
            row = {**_face_metric(face), "native_object": final_name, "native_name": name,
                   "body_id": "B-final", "kind": "native_face", "roles": ["boundary", "load"],
                   "label": f"{final.Label} / {name}", "unit": "mm", "coordinate_system": helpers.FRAME_ID,
                   "orientation": str(face.Orientation), "step_correspondence": "UNIQUE_GEOMETRY_MATCH",
                   "geometry_sha256": brep["sha256"], "brep": brep}
            if row["surface_type"] == "Plane":
                u_min, u_max, v_min, v_max = face.ParameterRange
                normal = face.normalAt((u_min + u_max) / 2, (v_min + v_max) / 2)
                if normal.Length <= 0:
                    raise ValueError("A native planar face has no finite unit normal")
                normal.normalize()
                row["planar_normal_global"] = _vector(normal)
            faces.append(row)
        catalog = {"schema_version": "1.0", "kind": "native_face_catalog", "sources": request["sources"],
                   "native_object": {"name": final.Name, "label": final.Label, "type_id": final.TypeId,
                       "placement_matrix": _matrix(final.Placement),
                       "global_placement_matrix": _matrix(global_placement),
                       "ancestor_transform_matrix": _matrix(ancestor)},
                   "native_runtime": {"freecad_version": list(App.Version())},
                   "coordinate_systems": [{"id": helpers.FRAME_ID, "type": "cartesian", "unit": "mm",
                       "basis": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "origin": [0, 0, 0],
                       "label": helpers.FRAME_LABEL, "alignment": "UNKNOWN"}],
                   "body": body, "faces": faces, "geometry_verification": verification,
                   "physical_qualification": "UNKNOWN",
                   "limitations": ["FaceN is local to this captured native revision; old IDs are never rebound automatically.",
                       "Geometry correspondence does not qualify meshing, conditions, solver, material or physical behavior.",
                       "Sensor/world alignment is UNKNOWN; native document-global coordinates only."]}
        revision = helpers.revision_identity(catalog)
        catalog["native_catalog_revision"] = revision
        for row in faces:
            row["id"] = f"F-{revision}-{row['native_name']}"
        helpers.validate_catalog(catalog)
        helpers._verify_files(root, catalog)
        with (output / "catalog.json").open("xb") as stream:
            stream.write((json.dumps(catalog, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())
        return {"catalog_path": "cad/native_faces/catalog.json", "native_catalog_revision": revision,
                "face_count": len(faces), "volume_mm3": body["volume_mm3"]}
    finally:
        App.closeDocument(document.Name)


def main():
    worker = _worker_path()
    helpers = _helpers(worker)
    request_path = Path(os.environ["CAELAB_FREECAD_FACE_REQUEST"])
    result_path = Path(os.environ["CAELAB_FREECAD_FACE_RESULT"])
    if (not request_path.is_absolute() or request_path.is_symlink()
            or request_path.name != "request.json" or result_path != request_path.with_name("worker-result.json")):
        raise ValueError("Native face worker request/result paths differ")
    try:
        request = helpers._json_bytes(request_path.read_bytes(), maximum=1024 * 1024)
        if (not isinstance(request, dict) or Path(request.get("output", "")).resolve() != request_path.parent.resolve()
                or Path(request.get("experiment_root", "")).resolve() != request_path.parent.parent.parent.resolve()):
            raise ValueError("Native face request cannot select another experiment or output directory")
        result = capture(request, helpers)
        answer = {"ok": True, "result": result}
    except Exception as error:
        answer = {"ok": False, "error": str(error), "error_type": type(error).__name__}
    with result_path.open("xb") as stream:
        stream.write(json.dumps(answer, ensure_ascii=False, allow_nan=False).encode())


if __name__ == "__main__":
    main()
