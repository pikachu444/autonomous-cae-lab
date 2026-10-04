"""Standalone Gmsh4.12.1 producer; import-safe until its explicit entry point.

No ambient CAD/Core code or native parent path is imported. Geometry and fields
below are exclusively actual SDK observations, not a finite-element solution.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import time


def _load(file: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _helper():
    return _load(Path(__file__).with_name("fixture_assembly_mesh.py"), "_owned_mesh_helper")


def bootstrap(input_file: Path):
    """Check executed/captured source before importing any capsule Python code."""
    root = input_file.parent
    if input_file.name != "request.json" or any(p.is_symlink() for p in (input_file, *input_file.parents)):
        raise ValueError("One nonsymlinked owned request.json path required")
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("Duplicate bootstrap request JSON key")
            out[key] = value
        return out
    request = json.loads(input_file.read_bytes().decode("utf-8", errors="strict"), object_pairs_hook=pairs)
    if not isinstance(request, dict) or not isinstance(request.get("source_files"), dict):
        raise ValueError("Malformed owned source capsule envelope")
    for name in ("fixture_assembly_mesh.py", "fixture_assembly_mesh_worker.py", "assembly_mesh.py", "gmsh.py"):
        file = root / "capsule" / name
        if any(p.is_symlink() for p in (file, *file.parents)) or not file.is_file():
            raise ValueError("Missing/symlinked standalone source capsule")
        data = file.read_bytes()
        actual = {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
        if actual != request["source_files"].get(name):
            raise ValueError("Standalone source capsule drift before import: " + name)
        if name == "fixture_assembly_mesh_worker.py" and Path(__file__).read_bytes() != data:
            raise ValueError("Executed native worker differs from captured source")
    if request["source_files"]["gmsh.py"]["sha256"] != "275cd3fa7141a723e22c717ebd70a8760683e3a2692598f780874ce3386b9cb6":
        raise ValueError("Reviewed official SDK source pin differs before import")
    return _load(root / "capsule/fixture_assembly_mesh.py", "_owned_mesh_helper"), request


def _list(values):
    return values.tolist() if hasattr(values, "tolist") else list(values)


def signature(g, dim: int, tag: int) -> dict:
    box = _list(g.model.occ.getBoundingBox(dim, tag))
    result = {"center_of_mass_mm": _list(g.model.occ.getCenterOfMass(dim, tag)),
              "bounds": {"min_mm": box[:3], "max_mm": box[3:]},
              "volume_mm3" if dim == 3 else "area_mm2": float(g.model.occ.getMass(dim, tag))}
    if dim == 2:
        result["geom_type"] = g.model.getType(dim, tag).upper()
        lo, hi = g.model.getParametrizationBounds(dim, tag)
        uv = [math.fsum((float(a), float(b)))/2 for a, b in zip(lo, hi)]
        if len(uv) != 2 or not all(math.isfinite(v) for v in uv):
            raise ValueError("Finite actual surface parametrization required")
        km, kn, dm, dn = g.model.getPrincipalCurvatures(tag, uv)
        result.update({"parametric_bounds": [_list(lo), _list(hi)], "sample_uv": uv,
            "surface_point_mm": _list(g.model.getValue(2, tag, uv)),
            "surface_normal": _list(g.model.getNormal(tag, uv)),
            "principal_curvatures_per_mm": [float(km[0]), float(kn[0])],
            "principal_directions": [_list(dm), _list(dn)],
            "surface_observation": "Actual SDK point/normal/curvatures at captured UV; no invented native plane/cylinder origin"})
    return result


def import_geometry(g, h, root: Path, request: dict, catalog: dict) -> dict:
    observations = {"volumes": [], "faces": []}
    wanted = {c["id"]: c for c in catalog["components"]}
    for name in request["intent"]["active"]:
        component = wanted[name]
        file = h.safe(root / "parent", request["parent"]["cad_prefix"] + "/" + component["native_brep_path"])
        imported = g.model.occ.importShapes(str(file), highestDimOnly=True, format="brep")
        g.model.occ.synchronize()
        if len(imported) != 1 or imported[0][0] != 3:
            raise ValueError("Each original component BREP must import exactly one volume")
        tag = h.positive_id(int(imported[0][1]))
        observations["volumes"].append({"component_id": name, "entity_tag": tag, "signature": signature(g, 3, tag)})
        boundaries = g.model.getBoundary([(3, tag)], combined=False, oriented=False, recursive=False)
        if not boundaries or any(dim != 2 for dim, _ in boundaries):
            raise ValueError("Actual full volume surface boundary required")
        for _, face_tag in boundaries:
            observations["faces"].append({"component_id": name, "entity_tag": h.positive_id(int(face_tag)),
                                         "signature": signature(g, 2, face_tag)})
        h.save(root / "import-evidence" / (name + ".json"),
               {"volumes": [a for a in observations["volumes"] if a["component_id"] == name],
                "faces": [a for a in observations["faces"] if a["component_id"] == name]})
    join = h.join_geometry(catalog, observations)
    for dim, key in ((3, "volumes"), (2, "faces")):
        expected = {a["entity_tag"] for a in observations[key]}
        actual = {int(tag) for actual_dim, tag in g.model.getEntities(dim) if actual_dim == dim}
        if actual != expected:
            raise ValueError("Extra/shared imported volume or face entity")
    return {"observations": observations, "join": join}


def physical_groups(g, geometry: dict) -> list[dict]:
    groups = []
    counters = {2: 0, 3: 0}
    for e in geometry["join"]["entities"]:
        dim, tag = e["dim"], e["entity_tag"]
        counters[dim] += 1
        name = ("V" if dim == 3 else "F") + f"{counters[dim]:04d}"
        physical_tag = int(g.model.addPhysicalGroup(dim, [tag], name=name))
        groups.append({"dim": dim, "tag": physical_tag, "name": name, "entity_tags": [tag],
                       "component_id": e["component_id"], "catalog_face_id": e["catalog_face_id"]})
    return groups


def _properties(g, kind: int) -> dict:
    name, dim, order, count, coords, primary = g.model.mesh.getElementProperties(kind)
    return {"name": name, "dimension": int(dim), "order": int(order), "node_count": int(count),
            "reference_node_coordinates": _list(coords), "primary_node_count": int(primary)}


def _blocks(g, dim=-1, tag=-1) -> list[dict]:
    types, ids, nodes = g.model.mesh.getElements(dim, tag)
    if len(types) != len(ids) or len(types) != len(nodes):
        raise ValueError("Malformed actual SDK element block arrays")
    output = []
    for kind, element_ids, conn in zip(types, ids, nodes):
        p = _properties(g, int(kind))
        output.append({"type": int(kind), "dimension": p["dimension"], "node_count": p["node_count"],
                       "element_ids": [int(n) for n in element_ids], "node_ids": [int(n) for n in conn]})
    return output


def collect_mesh(g, h, geometry: dict, groups: list[dict]) -> tuple[dict, dict, dict]:
    import numpy as np
    nodes, coordinates, parametric = g.model.mesh.getNodes()
    all_nodes = [{"id": int(n), "xyz_mm": _list(coordinates[3*i:3*i+3])} for i, n in enumerate(nodes)]
    if len(coordinates) != len(nodes)*3:
        raise ValueError("Incomplete actual SDK node coordinate coverage")
    elements, omitted, ids, entity_tags, jac, det, physical_coords = [], [], [], [], [], [], []
    points = [v for p in h.domain().POINTS for v in p]
    for group in groups:
        dim, entity_tag = group["dim"], group["entity_tags"][0]
        native_physical = [int(v) for v in g.model.getPhysicalGroupsForEntity(dim, entity_tag)]
        if native_physical != [group["tag"]] or g.model.getPhysicalName(dim, group["tag"]) != group["name"] or [int(v) for v in g.model.getEntitiesForPhysicalGroup(dim, group["tag"])] != [entity_tag]:
            raise ValueError("Actual SDK physical/entity/name coverage differs")
        ns, xyz = g.model.mesh.getNodesForPhysicalGroup(dim, group["tag"])
        if len(xyz) != len(ns)*3:
            raise ValueError("Incomplete actual physical-group node coordinates")
        group["node_ids"] = [int(n) for n in ns]
        group["node_coordinates_mm"] = [_list(xyz[3*i:3*i+3]) for i in range(len(ns))]
        blocks = _blocks(g, dim, entity_tag)
        expected_kind = 11 if dim == 3 else 9
        if not blocks or any(b["type"] != expected_kind for b in blocks):
            raise ValueError("Every active body/face must have only actual TETRA10/TRIA6 elements")
        for b in blocks:
            n = b["node_count"]
            if len(b["node_ids"]) != n*len(b["element_ids"]):
                raise ValueError("Incomplete actual native connectivity")
            for i, eid in enumerate(b["element_ids"]):
                elements.append({"id": eid, "type": b["type"], "dim": dim, "entity_tag": entity_tag,
                    "physical_tag": group["tag"], "component_id": group["component_id"],
                    "catalog_face_id": group["catalog_face_id"], "node_ids": b["node_ids"][i*n:(i+1)*n]})
            if dim == 3:
                js, ds, cs = g.model.mesh.getJacobians(11, points, entity_tag)
                count = len(b["element_ids"])
                if len(js) != count*5*9 or len(ds) != count*5 or len(cs) != count*5*3:
                    raise ValueError("Complete actual five-point SDK Jacobian arrays required")
                ids.extend(b["element_ids"]); entity_tags.extend([entity_tag]*count)
                jac.extend(_list(js)); det.extend(_list(ds)); physical_coords.extend(_list(cs))
    for dim in (0, 1):
        for _, tag in g.model.getEntities(dim):
            omitted.append({"dim": dim, "entity_tag": int(tag), "blocks": _blocks(g, dim, int(tag)),
                            "reason": "Outside selected 3D/2D solver-input scope"})
    referenced = {i for e in elements for i in e["node_ids"]}
    mapping = {"schema_version": 1, "units": "mm", "frame": "global_assembly_cartesian_mm",
        "writer": h.POLICY["writer"], "data_producer": "Gmsh4.12.1", "geometry_observations": geometry["observations"],
        "geometry_join": geometry["join"], "physical_groups": groups, "elements": elements,
        "nodes": [n for n in all_nodes if n["id"] in referenced], "api_all_nodes": all_nodes,
        "api_node_parametric_coordinates": _list(parametric), "api_global_elements": _blocks(g),
        "omitted_entities": omitted, "omitted_node_ids": [n["id"] for n in all_nodes if n["id"] not in referenced],
        "element_properties": {str(k): _properties(g, k) for k in (11, 9)}}
    n = len(ids)
    arrays = {"element_ids": np.asarray(ids, dtype="uint64"), "entity_tags": np.asarray(entity_tags, dtype="uint64"),
              "jacobians": np.asarray(jac, dtype="float64").reshape(n,5,9),
              "determinants": np.asarray(det, dtype="float64").reshape(n,5),
              "coordinates": np.asarray(physical_coords, dtype="float64").reshape(n,5,3)}
    metadata = {"rule": h.domain().profile(3.0)["rule"], "points": [list(p) for p in h.domain().POINTS],
        "weights": list(h.domain().WEIGHTS), "element_order": ids,
        "jacobian_order": "column_major_Jxu_Jyu_Jzu_Jxv_Jyv_Jzv_Jxw_Jyw_Jzw",
        "units": {"jacobians": "mm", "determinants": "mm^3", "coordinates": "mm"},
        "arrays": {k: {"dtype": a.dtype.name, "shape": list(a.shape)} for k, a in arrays.items()},
        "basis": "Actual SDK getJacobians; entity getElements order, all actual TETRA10 and all five samples"}
    return mapping, arrays, metadata


def runtime(g, h) -> dict:
    import resource
    # The official copied Python SDK can resolve only a SONAME. Its actual
    # loaded mapping, not that relative string or a guessed cwd path, is evidence.
    loaded = set()
    for line in Path("/proc/self/maps").read_text().splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) == 6 and fields[5].startswith("/") and Path(fields[5]).name.startswith("libgmsh"):
            loaded.add(Path(fields[5]).resolve())
    if len(loaded) != 1:
        raise ValueError("Actual loaded Gmsh shared-library identity UNKNOWN or ambiguous")
    lib = loaded.pop()
    if lib != h.SDK_LIBRARY or h.file_entry(lib)["sha256"] != h.SDK_LIBRARY_SHA256:
        raise ValueError("Actual loaded SDK library differs from reviewed system identity")
    return {"python": sys.version.split()[0], "gmsh_version": g.__version__,
            "sdk_sha256": h.file_entry(Path(g.__file__))["sha256"], "sdk_path": str(Path(g.__file__).resolve()),
            "library_path": str(lib), "library_sha256": h.file_entry(lib)["sha256"],
            "sdk_requested_library": str(g.libpath), "library_evidence": "actual_/proc/self/maps",
            "cpu_limit_seconds": resource.getrlimit(resource.RLIMIT_CPU)[0]}


def runtime_snapshot(g, h, root: Path, phase: str) -> dict:
    """Append diagnostic observations without adding trusted mesh artifacts.

    These snapshots remain available on rejected jobs. They never replace the
    success result's bound runtime fields or independently admit mesh quality.
    """
    if phase not in ("before", "after"):
        raise ValueError("Only fixed before/after runtime diagnostic phases are supported")
    snapshot = {"schema_version": 1, "phase": phase, "diagnostic_only": True,
                "request_sha256": h.file_entry(root / "request.json")["sha256"]}
    try:
        observed = runtime(g, h)
    except BaseException as exc:
        h.save(root / ("runtime-" + phase + ".json"), {**snapshot,
               "observation_status": "UNKNOWN", "runtime": None,
               "exception_type": type(exc).__name__, "reason": str(exc)})
        raise
    h.save(root / ("runtime-" + phase + ".json"), {**snapshot,
           "observation_status": "OBSERVED", "runtime": observed})
    return observed


def produce(g, h, root: Path, request: dict, catalog: dict) -> dict:
    """SDK-dependent operations are injectable solely as controlled cold fixtures."""
    import numpy as np
    g.model.add("owned_fixture_assembly_mesh")
    options = h.mesh_options(request["profile"]["mesh_size_mm"])
    for name, value in options.items():
        g.option.setNumber(name, value)
    observed = {name: float(g.option.getNumber(name)) for name in options}
    if observed != options:
        raise ValueError("Actual Gmsh options differ from explicit mesh recipe")
    geometry = import_geometry(g, h, root, request, catalog)
    h.save(root / "imported_geometry.json", geometry)
    groups = physical_groups(g, geometry)
    g.model.mesh.generate(3)
    mapping, arrays, metadata = collect_mesh(g, h, geometry, groups)
    mapping["mesh_size_mm"] = request["profile"]["mesh_size_mm"]
    mapping["options"] = {"requested": options, "observed": observed}
    h.save(root / "mapping.json", mapping)
    h.save(root / "jacobian_metadata.json", metadata)
    with (root / "jacobians.npz").open("xb") as file:
        np.savez(file, **arrays)
    h.check_mapping(mapping, catalog)
    quality = h.verify_jacobians(root / "jacobians.npz", mapping, metadata, catalog)
    h.save(root / "quality.json", quality)
    if quality["status"] != "PASS":
        raise ValueError("Actual five-point Jacobian/one-percent body-volume quality FAILED; no mesh exported")
    h.write_msh(root / "mesh.msh", mapping)
    h.verify_msh(root / "mesh.msh", mapping)
    return {"quality": quality, "jacobian_metadata": metadata}


def main(input_file: Path) -> int:
    import resource
    input_file = input_file.absolute()
    h, request = bootstrap(input_file)
    root = input_file.parent
    request_bytes = h.file_entry(input_file)
    catalog = h.check_request(root, request)
    if sys.version.split()[0] != "3.12.3" or Path(sys.executable).resolve() != Path(h.SYSTEM_PYTHON).resolve():
        raise ValueError("Exact reviewed system Python3.12.3 runtime required")
    source_before = {"helper": h.file_entry(Path(h.__file__)), "worker": h.file_entry(Path(__file__))}
    if source_before != {"helper": request["source_files"]["fixture_assembly_mesh.py"], "worker": request["source_files"]["fixture_assembly_mesh_worker.py"]}:
        raise ValueError("Executed standalone worker/helper source differs")
    _, hard = resource.getrlimit(resource.RLIMIT_CPU)
    if hard != resource.RLIM_INFINITY and hard < 86400:
        raise ValueError("Existing hard CPU policy cannot support the declared 86400 seconds")
    resource.setrlimit(resource.RLIMIT_CPU, (86400, hard))
    g = _load(h.safe(root / "capsule", "gmsh.py"), "_captured_official_gmsh")
    before = runtime_snapshot(g, h, root, "before")
    initialized = logger_started = finalized = False
    error, result = None, None
    started = time.monotonic()
    try:
        g.initialize([], readConfigFiles=False, run=False)
        initialized = True
        g.logger.start(); logger_started = True
        produced = produce(g, h, root, request, catalog)
        result = {"schema_version": 1, "status": "VALID_PREPROCESSING", "decision": "NOT_RELEASED",
            "parent": request["parent"], "request_sha256": request_bytes["sha256"], "source_files": request["source_files"],
            "profile": request["profile"], "policy": request["policy"], "runtime_before": before, **produced}
    except BaseException as exc:
        error = exc
    finally:
        if logger_started:
            try:
                with (root / "mesher.log").open("x", encoding="utf-8", newline="\n") as stream:
                    stream.write("\n".join(g.logger.get()) + "\n")
                g.logger.stop()
            except BaseException as exc:
                error = error or exc
        if initialized:
            try:
                g.finalize(); finalized = True
            except BaseException as exc:
                error = error or exc
        h.save(root / "lifecycle.json", {"initialize_succeeded": initialized, "read_config_files": False,
            "logger_started": logger_started, "finalize_succeeded": finalized, "initialize_attempts": 1,
            "elapsed_seconds": time.monotonic()-started, "solver_calls": 0, "provider_calls": 0})
    try:
        after = runtime_snapshot(g, h, root, "after")
        h.check_request(root, request)
        if h.file_entry(input_file) != request_bytes or h.file_entry(Path(h.__file__)) != source_before["helper"] or h.file_entry(Path(__file__)) != source_before["worker"] or before != after:
            raise ValueError("Executed mesh source/input/runtime drift")
    except BaseException as exc:
        error = error or exc
    if error is not None:
        h.save(root / "failure.json", {"status": "REJECTED_PREPROCESSING", "decision": "NOT_RELEASED",
               "exception_type": type(error).__name__, "reason": str(error), "native_quality": "UNKNOWN",
               "partial_files_retained": True, "native_retry_count": 0})
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1
    result["runtime_after"] = after
    result["output_files"] = {name: h.file_entry(h.safe(root, name)) for name in ("mesh.msh", "mapping.json", "jacobians.npz", "jacobian_metadata.json", "mesher.log", "imported_geometry.json", "quality.json", "lifecycle.json")}
    result["mesh_revision"] = h.digest(h.revision_material(result))
    h.verify_output(root, result, request)
    h.save(root / "result.json", result)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Expected one captured request.json path")
    raise SystemExit(main(Path(sys.argv[1])))
