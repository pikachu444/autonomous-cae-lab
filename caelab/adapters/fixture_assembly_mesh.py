"""Internal, bounded assembly meshing boundary; no AnalysisAdapter admission.

The Lab controller reuses the CAD producer's verifier. Its isolated system-
Python worker receives only captured, hash-bound inputs and standalone sources.
Importing this module never imports a CAD kernel or the native Gmsh SDK.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

SDK_FILE = Path("/usr/lib/python3/dist-packages/gmsh.py")
SDK_SHA256 = "275cd3fa7141a723e22c717ebd70a8760683e3a2692598f780874ce3386b9cb6"
SDK_LIBRARY = Path("/usr/lib/x86_64-linux-gnu/libgmsh.so.4.12.1")
SDK_LIBRARY_SHA256 = "13d7aa9e48ca2333a8be79453ac6e7503cc9d803d98004b8aef5796bed1ae0f9"
SYSTEM_PYTHON = "/usr/bin/python3"
POLICY = {"cpu_limit_seconds": 86400, "wall_timeout_seconds": None,
          "threads": 2, "read_config_files": False, "native_retry_count": 0,
          "writer": "adapter_msh2_ascii_17g", "producer": "Gmsh4.12.1",
          "coordinate_roundtrip": "binary64_bits_including_negative_zero"}
HELPER = Path(__file__).resolve()
WORKER = HELPER.with_name("fixture_assembly_mesh_worker.py")
DOMAIN_FILE = (HELPER.with_name("assembly_mesh.py") if HELPER.parent.name == "capsule"
               else HELPER.parents[2] / "plugins/fixture_design/assembly_mesh.py")
_DOMAIN_CONTEXT = None


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def core_digest(value) -> str:
    # Core storage uses literal UTF-8. Native CAD/mesh revision encodings are
    # independently declared; do not substitute their ASCII encoding for Core.
    data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def file_entry(file: Path) -> dict:
    data = file.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def no_symlinks(file: Path) -> None:
    if any(p.is_symlink() for p in (file, *file.parents)):
        raise ValueError("Symlinked input/output/source is forbidden")


def safe(root: Path, name: str, *, exists: bool = True) -> Path:
    if not isinstance(name, str) or any(c in name for c in "\\:\0\r\n"):
        raise ValueError("Unsafe mesh artifact path")
    parts = name.split("/")
    if not all(parts) or any(p in (".", "..") for p in parts):
        raise ValueError("Unsafe mesh artifact path")
    file = Path(root).joinpath(*parts)
    no_symlinks(file)
    if not file.resolve().is_relative_to(Path(root).resolve()) or (exists and not file.is_file()):
        raise ValueError("Missing or escaping mesh artifact path")
    return file


def read_json(file: Path):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError("Duplicate JSON key: " + k)
            result[k] = v
        return result
    def invalid(value):
        raise ValueError("Nonfinite JSON number: " + value)
    no_symlinks(file)
    return json.loads(file.read_bytes().decode("utf-8", errors="strict"),
                      object_pairs_hook=pairs, parse_constant=invalid)


def save(file: Path, value) -> None:
    no_symlinks(file)
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def fresh(output: Path) -> None:
    no_symlinks(output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Fresh empty mesh output required; historical evidence remains intact")
    output.mkdir(parents=True, exist_ok=True)


def check_files(root: Path, entries: dict) -> None:
    if not isinstance(entries, dict) or not entries:
        raise ValueError("A nonempty byte manifest is required")
    for name, expected in entries.items():
        if set(expected) != {"sha256", "size_bytes"} or type(expected["size_bytes"]) is not int or expected["size_bytes"] < 0:
            raise ValueError("Malformed mesh byte manifest entry")
        if file_entry(safe(root, name)) != expected:
            raise ValueError("Mesh input/output/source byte drift: " + name)


def standalone(file: Path, name: str):
    no_symlinks(file)
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def domain():
    global _DOMAIN_CONTEXT
    observed = file_entry(DOMAIN_FILE)
    if _DOMAIN_CONTEXT is None:
        module = standalone(DOMAIN_FILE, "_assembly_mesh_domain")
        if file_entry(DOMAIN_FILE) != observed:
            raise ValueError("Mesh Domain changed during its explicit source load")
        _DOMAIN_CONTEXT = (observed, module)
    if observed != _DOMAIN_CONTEXT[0]:
        raise ValueError("Loaded mesh Domain source changed; stale declarations refused")
    return _DOMAIN_CONTEXT[1]


def _cad_adapter():
    from . import fixture_assembly
    return fixture_assembly


def positive_id(value):
    if type(value) is not int or not 0 < value < 2**64:
        raise ValueError("Positive actual native integer identity required")
    return value


def mesh_options(mesh_size_mm: float) -> dict:
    size = domain().profile(mesh_size_mm)["mesh_size_mm"]
    return {"General.NumThreads": 2, "Mesh.MaxNumThreads2D": 2, "Mesh.MaxNumThreads3D": 2,
            "Mesh.ElementOrder": 2, "Mesh.SecondOrderLinear": 0, "Mesh.HighOrderOptimize": 0,
            "Mesh.MeshSizeMin": size, "Mesh.MeshSizeMax": size,
            "Mesh.MeshSizeFromCurvature": 0, "Mesh.MeshSizeFromPoints": 1,
            "Mesh.MeshSizeExtendFromBoundary": 1, "Mesh.Algorithm3D": 1,
            "Mesh.RecombineAll": 0, "Mesh.MshFileVersion": 2.2}


def numbers(value, length):
    if not isinstance(value, list) or len(value) != length or any(
            type(v) not in (int, float) or not math.isfinite(v) for v in value):
        raise ValueError("Complete finite actual numeric array required")
    return value


def validate_parent(parent_result: dict, parent_root: Path) -> dict:
    """Validate existing experiment bytes and deliberately reuse CAD verification."""
    root = Path(parent_root)
    result = read_json(safe(root, "result.json"))
    if result != parent_result or result.get("status") != "COMPLETED_REVIEW_REQUIRED" or result.get("decision") != "NOT_RELEASED":
        raise ValueError("A verified completed CAD parent is required")
    if result.get("solver_status") != "NOT_RUN" or result.get("converged") is not None:
        raise ValueError("Assembly CAD parent must not be a solver result")
    if any(v.get("status") == "FAIL" for v in result.get("validations", [])):
        raise ValueError("Invalid CAD parent validations block mesh export")
    provenance = result["provenance"]
    if provenance.get("adapter") != "fixture.assembly":
        raise ValueError("Parent backend must be fixture.assembly")
    proposal = read_json(safe(root, "proposal.json"))
    registry = read_json(safe(root, "registry_snapshot.json"))
    if not isinstance(proposal, dict) or not isinstance(proposal.get("model"), dict) or not isinstance(proposal["model"].get("geometry"), dict) or not isinstance(proposal.get("physics"), dict) or not isinstance(proposal.get("parameters"), dict) or not isinstance(registry, dict) or "revision" not in registry:
        raise ValueError("Malformed assembly parent proposal/registry envelope")
    if proposal["model"]["geometry"] != {"backend": "fixture.assembly", "source": "bending_assembly"} or proposal["physics"]["analysis_type"] != "cad_preflight":
        raise ValueError("Unsupported assembly parent model/analysis")
    if core_digest(proposal) != provenance["proposal_sha256"] or core_digest(registry) != provenance["registry_sha256"]:
        raise ValueError("Parent proposal/registry hash differs")
    if result["input_parameters"] != proposal["parameters"] or result["registry_revision"] != registry["revision"] or proposal["registry_revision"] != registry["revision"]:
        raise ValueError("Parent parameter/registry identity differs")
    pr = core_digest({"model": proposal["model"]["geometry"]["source"], "values": result["input_parameters"], "registry": registry})
    if result["proposal_revision"] != pr:
        raise ValueError("Parent proposal revision differs")
    entries = {}
    for artifact in result["artifacts"]:
        name = artifact["path"]
        if name in entries or artifact.get("revision") != result["cad_revision"]:
            raise ValueError("Duplicate artifact or foreign parent revision")
        entries[name] = {"sha256": artifact["sha256"], "size_bytes": artifact["size_bytes"]}
    check_files(root, entries)
    catalogs = [name for name in entries if name.endswith("/assembly_catalog.json")]
    if len(catalogs) != 1:
        raise ValueError("One manifested assembly catalog required")
    prefix = catalogs[0].rsplit("/", 1)[0]
    raw_name = prefix + "/result.json"
    if raw_name not in entries:
        raise ValueError("Native CAD result is not manifested")
    raw = read_json(safe(root, raw_name))
    if raw.get("cad_generated") is not True or raw.get("decision") != "REVIEW_REQUIRED":
        raise ValueError("Unadmitted native CAD parent")
    cad = _cad_adapter()
    cad.verify_result(root / prefix, raw, raw["source_fingerprint_before"])
    if provenance["cad_source_sha256"] != raw["source_sha256"] or result["cad_revision"] != core_digest({"source": raw["native_revision"], "proposal": pr}):
        raise ValueError("Parent Core/native/source revision differs")
    catalog = read_json(safe(root, catalogs[0]))
    d = domain()
    intent = d.intent(catalog["components"])
    if catalog.get("face_count") != 117 or sum(len(c["faces"]) for c in catalog["components"]) != 117 or len(catalog["interfaces"]) != 15:
        raise ValueError("Original full fifteen-body/117-face/15-interface parent required")
    for c in catalog["components"]:
        for item in [c, *c["faces"]]:
            name = prefix + "/" + item["native_brep_path"]
            if name not in entries or entries[name]["sha256"] != item["native_geometry_sha256"]:
                raise ValueError("Native BREP is not bound to the parent manifest")
    # Capture all manifested CAD bytes and every input actually used by Core joins.
    for name in ("result.json", "proposal.json", "registry_snapshot.json"):
        entries[name] = file_entry(safe(root, name))
    return {"identity": {"experiment_id": result["experiment_id"], "cad_revision": result["cad_revision"],
            "native_revision": raw["native_revision"], "source_sha256": raw["source_sha256"],
            "input_sha256": raw["input_sha256"], "catalog_sha256": raw["catalog_sha256"],
            "result_sha256": entries["result.json"]["sha256"], "cad_prefix": prefix,
            "cad_provenance": deepcopy(provenance)}, "files": entries, "intent": intent,
            "catalog": catalog, "native_result": raw}


def source_files() -> dict[str, Path]:
    files = {"fixture_assembly_mesh.py": HELPER, "fixture_assembly_mesh_worker.py": WORKER,
             "assembly_mesh.py": DOMAIN_FILE, "gmsh.py": SDK_FILE}
    for name, path in _cad_adapter().source_files().items():
        files["parent_verifier/" + name] = path
    return files


def source_fingerprint() -> dict:
    result = {}
    for name, file in source_files().items():
        no_symlinks(file)
        result[name] = file_entry(file)
    if result["gmsh.py"]["sha256"] != SDK_SHA256:
        raise ValueError("The reviewed Gmsh4.12.1 SDK source pin differs")
    return result


def prepare_request(parent_result: dict, parent_root: Path, output: Path, mesh_size_mm: float) -> dict:
    parent_root, output = Path(parent_root).absolute(), Path(output).absolute()
    if output.resolve().is_relative_to(parent_root.resolve()):
        raise ValueError("Mesh output may not mutate the historical parent experiment")
    d = domain()
    profile = d.profile(mesh_size_mm)
    parent = validate_parent(parent_result, parent_root)
    source = source_fingerprint()
    if file_entry(SDK_LIBRARY)["sha256"] != SDK_LIBRARY_SHA256:
        raise ValueError("Observed reviewed system Gmsh library differs")
    fresh(output)
    for base, files, source_root in (("parent", parent["files"], Path(parent_root)),
                                     ("capsule", source, None)):
        for name, entry in files.items():
            src = safe(source_root, name) if source_root is not None else source_files()[name]
            dest = safe(output, base + "/" + name, exists=False)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("xb") as stream:
                stream.write(src.read_bytes())
            if file_entry(dest) != entry:
                raise ValueError("Captured mesh input/source differs")
    request = {"schema_version": 1, "profile": profile, "intent": parent["intent"],
               "parent": parent["identity"], "parent_files": parent["files"], "source_files": source,
               "policy": deepcopy(POLICY), "sdk_library_sha256": SDK_LIBRARY_SHA256,
               "controller": {"python": sys.version.split()[0], "source_commit": "UNKNOWN",
                              "source_identity": "Exact captured bytes; Git was not queried"}}
    save(output / "request.json", request)
    check_request(output, request)
    check_files(Path(parent_root), parent["files"])
    if source_fingerprint() != source:
        raise ValueError("Mesh source changed during capture")
    return request


def check_request(root: Path, request: dict) -> dict:
    if read_json(safe(root, "request.json")) != request:
        raise ValueError("Frozen mesh request changed")
    if request.get("schema_version") != 1 or request.get("policy") != POLICY or request.get("sdk_library_sha256") != SDK_LIBRARY_SHA256:
        raise ValueError("Unsupported or changed native mesh request/policy")
    check_files(root / "capsule", request["source_files"])
    check_files(root / "parent", request["parent_files"])
    d = standalone(safe(root / "capsule", "assembly_mesh.py"), "_captured_mesh_domain")
    if request["profile"] != d.profile(request["profile"]["mesh_size_mm"]):
        raise ValueError("Mesh profile/rule/limits drift")
    if request["source_files"]["gmsh.py"]["sha256"] != SDK_SHA256:
        raise ValueError("Reviewed SDK source identity differs")
    catalog = read_json(safe(root / "parent", request["parent"]["cad_prefix"] + "/assembly_catalog.json"))
    if file_entry(safe(root / "parent", request["parent"]["cad_prefix"] + "/assembly_catalog.json"))["sha256"] != request["parent"]["catalog_sha256"] or request["intent"] != d.intent(catalog["components"]):
        raise ValueError("Captured parent catalog/intent differs")
    raw = read_json(safe(root / "parent", request["parent"]["cad_prefix"] + "/result.json"))
    for key in ("native_revision", "source_sha256", "input_sha256", "catalog_sha256"):
        if raw[key] != request["parent"][key]:
            raise ValueError("Captured parent native identity differs")
    return catalog


def _norm(v):
    return math.sqrt(math.fsum(x*x for x in v))


def _dot(a, b):
    return math.fsum(x*y for x, y in zip(a, b))


def _unit(v):
    numbers(v, 3)
    length = _norm(v)
    if length <= 0:
        raise ValueError("Native surface direction is absent")
    return [x / length for x in v]


def matches_geometry(expected: dict, actual: dict, dim: int) -> bool:
    """No ordinal/tag selection: bounded signatures and available surface data."""
    limits = domain().LIMITS
    measure = "volume_mm3" if dim == 3 else "area_mm2"
    a, b = expected[measure], actual[measure]
    if type(a) not in (int, float) or type(b) not in (int, float) or not math.isfinite(a) or not math.isfinite(b) or min(a, b) <= 0:
        raise ValueError("Invalid actual native geometry measure")
    ec, ac = numbers(expected["center_of_mass_mm"], 3), numbers(actual["center_of_mass_mm"], 3)
    eb = numbers(expected["bounds"]["min_mm"], 3) + numbers(expected["bounds"]["max_mm"], 3)
    ab = numbers(actual["bounds"]["min_mm"], 3) + numbers(actual["bounds"]["max_mm"], 3)
    if max(abs(x-y) for x, y in zip(ec, ac)) > limits["center_absolute_mm"] or max(abs(x-y) for x, y in zip(eb, ab)) > limits["bounds_absolute_mm"] or abs(a-b)/a > limits["measure_relative"]:
        return False
    if dim == 3:
        return True
    kind = expected["geom_type"]
    if kind not in ("PLANE", "CYLINDER") or actual["geom_type"] != kind:
        return False
    point, normal = numbers(actual["surface_point_mm"], 3), _unit(actual["surface_normal"])
    curvature = numbers(actual["principal_curvatures_per_mm"], 2)
    surface = expected["surface"]
    scale = max(_norm([hi-lo for hi, lo in zip(eb[3:], eb[:3])]), limits["center_absolute_mm"])
    # Every surface check uses the declared linear displacement allowance.
    # Curvature/direction comparisons are converted to displacement at face scale.
    if kind == "PLANE":
        n = _unit(surface["normal"])
        offset = [x-y for x, y in zip(point, numbers(surface["origin_mm"], 3))]
        misalignment = _norm([normal[i] - _dot(normal, n)*n[i] for i in range(3)]) * scale
        return abs(_dot(offset, n)) <= limits["center_absolute_mm"] and misalignment <= limits["center_absolute_mm"] and max(abs(k) for k in curvature)*scale*scale <= limits["center_absolute_mm"]
    axis = _unit(surface["axis_direction"])
    radius = surface["radius_mm"]
    if type(radius) not in (int, float) or not math.isfinite(radius) or radius <= 0:
        raise ValueError("Invalid captured cylinder radius")
    offset = [x-y for x, y in zip(point, numbers(surface["axis_origin_mm"], 3))]
    radial = [offset[i]-_dot(offset, axis)*axis[i] for i in range(3)]
    r = _norm(radial)
    if r == 0:
        return False
    tangent_error = _norm([normal[i]-_dot(normal, _unit(radial))*_unit(radial)[i] for i in range(3)])*radius
    low, high = sorted(abs(k) for k in curvature)
    return abs(r-radius) <= limits["center_absolute_mm"] and tangent_error <= limits["center_absolute_mm"] and low*scale*scale <= limits["center_absolute_mm"] and abs(high*radius-1)*radius <= limits["center_absolute_mm"]


def join_geometry(catalog: dict, observations: dict) -> dict:
    d = domain()
    components = {c["id"]: c for c in catalog["components"]}
    wanted = {(3, name): components[name] for name in d.ACTIVE}
    wanted.update({(2, f["id"]): f for name in d.ACTIVE for f in components[name]["faces"]})
    joined, used = [], set()
    for (dim, identity), expected in wanted.items():
        candidates = [a for a in observations["volumes" if dim == 3 else "faces"]
                      if a["component_id"] == (identity if dim == 3 else expected["component_id"])
                      and matches_geometry(expected, a["signature"], dim)]
        if len(candidates) != 1:
            raise ValueError("Missing/ambiguous native geometry signature: " + identity)
        a = candidates[0]
        key = (dim, positive_id(a["entity_tag"]))
        if key in used:
            raise ValueError("Native geometry entity belongs to more than one catalog identity")
        used.add(key)
        joined.append({"dim": dim, "entity_tag": a["entity_tag"], "component_id": a["component_id"],
                       "catalog_face_id": identity if dim == 2 else None, "signature": a["signature"]})
    actual_keys = {(dim, positive_id(a["entity_tag"])) for dim, key in ((3, "volumes"), (2, "faces")) for a in observations[key]}
    if len(actual_keys) != sum(len(observations[key]) for key in ("volumes", "faces")) or actual_keys != used:
        raise ValueError("Extra/duplicate native geometry entity")
    return {"entities": joined, "limits": dict(d.LIMITS), "association": "unique_actual_geometry_signature_not_tag_or_array_order"}


def check_mapping(mapping: dict, catalog: dict) -> dict:
    if mapping.get("units") != "mm" or mapping.get("frame") != "global_assembly_cartesian_mm" or mapping.get("writer") != POLICY["writer"]:
        raise ValueError("Mesh frame/units/writer differs")
    options = mesh_options(mapping["mesh_size_mm"])
    if mapping["options"] != {"requested": options, "observed": options}:
        raise ValueError("Native mesh size/options observation differs")
    geometry = join_geometry(catalog, mapping["geometry_observations"])
    if mapping["geometry_join"] != geometry:
        raise ValueError("Native geometry join differs")
    entities = {(e["dim"], e["entity_tag"]): e for e in geometry["entities"]}
    groups, names = {}, set()
    for group in mapping["physical_groups"]:
        key = (group["dim"], positive_id(group["tag"]))
        if key in groups or group["name"] in names or not re.fullmatch(r"[VF][0-9]{4}", group["name"]):
            raise ValueError("Duplicate or unsafe physical group identity")
        names.add(group["name"])
        if len(group["entity_tags"]) != 1 or (key[0], group["entity_tags"][0]) not in entities:
            raise ValueError("Physical/entity mapping differs")
        entity = entities[(key[0], group["entity_tags"][0])]
        if group["component_id"] != entity["component_id"] or group["catalog_face_id"] != entity["catalog_face_id"]:
            raise ValueError("Physical/body/face mapping differs")
        ids = group["node_ids"]
        if len(ids) != len(set(ids)) or any(positive_id(n) != n for n in ids):
            raise ValueError("Invalid physical group node observations")
        groups[key] = group
    if len(groups) != len(entities) or {(dim, g["entity_tags"][0]) for (dim, _), g in groups.items()} != set(entities):
        raise ValueError("Complete unique physical geometry coverage required")
    nodes = {}
    for node in mapping["nodes"]:
        identity = positive_id(node["id"])
        if identity in nodes:
            raise ValueError("Duplicate actual node ID")
        nodes[identity] = numbers(node["xyz_mm"], 3)
    elements, referenced, owners = {}, set(), {}
    group_nodes = {key: set() for key in groups}
    for e in mapping["elements"]:
        eid = positive_id(e["id"])
        if eid in elements or e["type"] not in (9, 11) or type(e["type"]) is not int:
            raise ValueError("Duplicate or unsupported actual mesh element")
        dim, n = (3, 10) if e["type"] == 11 else (2, 6)
        if e["dim"] != dim:
            raise ValueError("Native element dimension differs")
        entity = entities.get((dim, e["entity_tag"]))
        group = groups.get((dim, e["physical_tag"]))
        if entity is None or group is None or group["entity_tags"] != [e["entity_tag"]] or e["component_id"] != entity["component_id"] or e["catalog_face_id"] != entity["catalog_face_id"]:
            raise ValueError("Element physical/entity/body/face join differs")
        conn = e["node_ids"]
        if not isinstance(conn, list) or len(conn) != n or len(set(conn)) != n or any(positive_id(i) not in nodes for i in conn):
            raise ValueError("Incomplete/foreign/duplicate actual element connectivity")
        for i in conn:
            if i in owners and owners[i] != e["component_id"]:
                raise ValueError("A native node ID is shared between distinct bodies")
            owners[i] = e["component_id"]
        referenced.update(conn)
        group_nodes[(dim, e["physical_tag"])].update(conn)
        elements[eid] = e
    if not elements or referenced != set(nodes):
        raise ValueError("Full selected node coverage differs")
    all_nodes = {}
    for node in mapping["api_all_nodes"]:
        nid = positive_id(node["id"])
        if nid in all_nodes:
            raise ValueError("Duplicate global SDK node ID")
        all_nodes[nid] = numbers(node["xyz_mm"], 3)
    bits = lambda row: b"".join(struct.pack("!d", v) for v in row)
    if any(n not in all_nodes or bits(xyz) != bits(all_nodes[n]) for n, xyz in nodes.items()):
        raise ValueError("Selected node/global SDK coordinate join differs")
    selected_api = {}
    for block in mapping["api_global_elements"]:
        kind, n = block["type"], block["node_count"]
        ids, conn = block["element_ids"], block["node_ids"]
        if len(conn) != len(ids)*n or len(set(ids)) != len(ids):
            raise ValueError("Malformed global SDK element block")
        if kind in (9, 11):
            for k, eid in enumerate(ids):
                if positive_id(eid) in selected_api:
                    raise ValueError("Duplicate global SDK element ID")
                selected_api[eid] = (kind, conn[k*n:(k+1)*n])
        elif block["dimension"] not in (0, 1):
            raise ValueError("Foreign unsupported global SDK element type")
    if selected_api != {eid: (e["type"], e["node_ids"]) for eid, e in elements.items()}:
        raise ValueError("Partial/foreign global SDK selected-element coverage")
    for key, group in groups.items():
        if not group_nodes[key] or set(group["node_ids"]) != group_nodes[key]:
            raise ValueError("Physical SDK node coverage differs from actual elements")
        if len(group["node_coordinates_mm"]) != len(group["node_ids"]) or any(
                bits(numbers(xyz, 3)) != bits(nodes[nid]) for nid, xyz in zip(group["node_ids"], group["node_coordinates_mm"])):
            raise ValueError("Physical SDK node/global coordinate join differs")
    properties = mapping["element_properties"]
    for kind, dim, n, primary in (("11", 3, 10, 4), ("9", 2, 6, 3)):
        p = properties[kind]
        if p["dimension"] != dim or p["order"] != 2 or p["node_count"] != n or p["primary_node_count"] != primary:
            raise ValueError("Actual quadratic SDK element property differs")
        numbers(p["reference_node_coordinates"], n*dim)
    for omitted in mapping["omitted_entities"]:
        if omitted["dim"] not in (0, 1) or omitted["reason"] != "Outside selected 3D/2D solver-input scope":
            raise ValueError("Unsupported omitted mesh entity")
    return {"nodes": nodes, "elements": elements, "groups": groups}


def write_msh(file: Path, mapping: dict) -> None:
    """Serialize actual selected SDK quantities; this is not Gmsh's writer."""
    no_symlinks(file)
    groups = mapping["physical_groups"]
    with file.open("x", encoding="ascii", newline="\n") as stream:
        stream.write("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$PhysicalNames\n" + str(len(groups)) + "\n")
        for g in groups:
            if not re.fullmatch(r"[VF][0-9]{4}", g["name"]):
                raise ValueError("Unsafe native physical group name")
            stream.write(f'{g["dim"]} {g["tag"]} "{g["name"]}"\n')
        stream.write("$EndPhysicalNames\n$Nodes\n" + str(len(mapping["nodes"])) + "\n")
        for node in mapping["nodes"]:
            stream.write(str(node["id"]) + " " + " ".join(format(x, ".17g") for x in numbers(node["xyz_mm"], 3)) + "\n")
        stream.write("$EndNodes\n$Elements\n" + str(len(mapping["elements"])) + "\n")
        for e in mapping["elements"]:
            stream.write(" ".join(str(x) for x in [e["id"], e["type"], 2, e["physical_tag"], e["entity_tag"], *e["node_ids"]]) + "\n")
        stream.write("$EndElements\n")


def verify_msh(file: Path, mapping: dict) -> None:
    """Independent strict ASCII parser, exact IDs and binary64 coordinate bits."""
    lines = iter(file.read_bytes().decode("ascii", errors="strict").splitlines())
    def take(expected=None):
        try:
            value = next(lines)
        except StopIteration as error:
            raise ValueError("Truncated MSH2 data") from error
        if expected is not None and value != expected:
            raise ValueError("Malformed MSH2 section")
        return value
    def integer(value):
        if not re.fullmatch(r"[0-9]+", value):
            raise ValueError("Malformed MSH2 integer")
        return int(value)
    take("$MeshFormat"); take("2.2 0 8"); take("$EndMeshFormat"); take("$PhysicalNames")
    groups = {}
    for _ in range(integer(take())):
        match = re.fullmatch(r'([23]) ([0-9]+) "([VF][0-9]{4})"', take())
        if not match:
            raise ValueError("Malformed MSH2 physical group")
        key = (int(match[1]), positive_id(int(match[2])))
        if key in groups:
            raise ValueError("Duplicate MSH2 group")
        groups[key] = match[3]
    if groups != {(g["dim"], g["tag"]): g["name"] for g in mapping["physical_groups"]}:
        raise ValueError("MSH2 physical names differ")
    take("$EndPhysicalNames"); take("$Nodes")
    nodes = {}
    for _ in range(integer(take())):
        row = take().split()
        if len(row) != 4:
            raise ValueError("Malformed MSH2 node")
        nid = positive_id(integer(row[0]))
        xyz = numbers([float(v) for v in row[1:]], 3)
        if nid in nodes:
            raise ValueError("Duplicate MSH2 node")
        nodes[nid] = b"".join(struct.pack("!d", v) for v in xyz)
    expected_nodes = {n["id"]: b"".join(struct.pack("!d", v) for v in n["xyz_mm"]) for n in mapping["nodes"]}
    if nodes != expected_nodes:
        raise ValueError("MSH2 coordinate/ID binary64 bits differ")
    take("$EndNodes"); take("$Elements")
    elements = {}
    for _ in range(integer(take())):
        row = [integer(v) for v in take().split()]
        if len(row) < 5 or row[1] not in (9, 11) or row[2] != 2 or len(row) != (11 if row[1] == 9 else 15):
            raise ValueError("Malformed MSH2 element")
        eid = positive_id(row[0])
        if eid in elements:
            raise ValueError("Duplicate MSH2 element")
        elements[eid] = row[1:]
    expected_elements = {e["id"]: [e["type"], 2, e["physical_tag"], e["entity_tag"], *e["node_ids"]] for e in mapping["elements"]}
    if elements != expected_elements:
        raise ValueError("MSH2 element/connectivity/physical/entity join differs")
    take("$EndElements")
    if list(lines):
        raise ValueError("Foreign trailing MSH2 data")


def determinant_check(jacobian: list, actual: float) -> dict:
    values = numbers(jacobian, 9)
    numbers([actual], 1)
    a,b,c,d,e,f,g,h,i = values  # Native column-major; determinant is unchanged by transpose.
    terms = (a*e*i, d*h*c, g*b*f, -g*e*c, -d*b*i, -a*h*f)
    if not all(math.isfinite(v) for v in terms):
        raise ValueError("Jacobian determinant arithmetic overflow")
    reconstructed = math.fsum(terms)
    # Two ordinary six-product determinant evaluations: max seven rounding steps
    # per dependency path each; gamma16 bounds both, plus 16 subnormal roundings.
    unit = 2**-53
    bound = (16*unit/(1-16*unit))*math.fsum(abs(t) for t in terms) + 16*math.ulp(0.0)
    error = abs(reconstructed-actual)
    if error > bound:
        raise ValueError("Actual SDK determinant/matrix consistency exceeds IEEE754 forward bound")
    return {"reconstructed_mm3": reconstructed, "absolute_difference_mm3": error,
            "forward_arithmetic_bound_mm3": bound, "bound": "gamma16_sum_abs_six_products_plus_16_subnormal_roundings"}


def verify_jacobians(file: Path, mapping: dict, metadata: dict, catalog: dict) -> dict:
    import numpy as np  # Existing controller/system dependency; never imported by module discovery.
    keys = {"element_ids", "entity_tags", "jacobians", "determinants", "coordinates"}
    with np.load(file, allow_pickle=False) as arrays:
        if set(arrays.files) != keys:
            raise ValueError("Unexpected Jacobian NPZ arrays")
        data = {k: arrays[k] for k in keys}
    elements = {e["id"]: e for e in mapping["elements"] if e["type"] == 11}
    n = len(elements)
    shapes = {"element_ids": [n], "entity_tags": [n], "jacobians": [n,5,9],
              "determinants": [n,5], "coordinates": [n,5,3]}
    if metadata.get("rule") != domain().profile(3.0)["rule"] or metadata.get("points") != [list(p) for p in domain().POINTS] or metadata.get("weights") != list(domain().WEIGHTS) or metadata.get("jacobian_order") != "column_major_Jxu_Jyu_Jzu_Jxv_Jyv_Jzv_Jxw_Jyw_Jzw" or metadata.get("units") != {"jacobians": "mm", "determinants": "mm^3", "coordinates": "mm"}:
        raise ValueError("Jacobian rule/order/units differ")
    for key, shape in shapes.items():
        dtype = "uint64" if key in ("element_ids", "entity_tags") else "float64"
        arr = data[key]
        if arr.dtype.name != dtype or list(arr.shape) != shape or metadata["arrays"][key] != {"dtype": dtype, "shape": shape} or not np.isfinite(arr).all():
            raise ValueError("Incomplete, wrong dtype/shape or nonfinite actual Jacobian array")
    ids = [int(v) for v in data["element_ids"]]
    if len(set(ids)) != n or set(ids) != set(elements) or metadata.get("element_order") != ids:
        raise ValueError("Jacobian actual element order/coverage differs")
    rows, consistency = [], []
    for r, eid in enumerate(ids):
        e = elements[eid]
        if int(data["entity_tags"][r]) != e["entity_tag"]:
            raise ValueError("Jacobian entity/element join differs")
        dets = data["determinants"][r].tolist()
        for p in range(5):
            consistency.append(determinant_check(data["jacobians"][r,p].tolist(), dets[p]))
        rows.append({"element_id": eid, "component_id": e["component_id"], "determinants_mm3": dets})
    volumes = {c["id"]: c["volume_mm3"] for c in catalog["components"] if c["id"] in domain().ACTIVE}
    quality = domain().quality(volumes, rows)
    quality["determinant_consistency"] = {"sample_count": len(consistency),
        "maximum_absolute_difference_mm3": max(c["absolute_difference_mm3"] for c in consistency),
        "maximum_forward_bound_mm3": max(c["forward_arithmetic_bound_mm3"] for c in consistency),
        "bound": "gamma16_sum_abs_six_products_plus_16_subnormal_roundings"}
    return quality


def revision_material(result: dict) -> dict:
    return {key: result[key] for key in ("schema_version", "parent", "request_sha256", "source_files", "runtime_before", "runtime_after",
            "profile", "policy", "output_files", "quality", "jacobian_metadata", "status", "decision")}


def verify_output(root: Path, result: dict, request: dict) -> dict:
    catalog = check_request(root, request)
    if result.get("schema_version") != 1 or result.get("request_sha256") != file_entry(safe(root, "request.json"))["sha256"] or result.get("parent") != request["parent"] or result.get("source_files") != request["source_files"] or result.get("profile") != request["profile"] or result.get("policy") != POLICY or result.get("decision") != "NOT_RELEASED":
        raise ValueError("Mesh result input/source/profile/parent identity differs")
    before, after = result["runtime_before"], result["runtime_after"]
    if before != after or before["python"] != "3.12.3" or before["gmsh_version"] != "4.12.1" or before["sdk_sha256"] != SDK_SHA256 or before["library_sha256"] != SDK_LIBRARY_SHA256 or before["cpu_limit_seconds"] != 86400:
        raise ValueError("Native runtime/source/library/policy drift")
    check_files(root, result["output_files"])
    wanted = {"mesh.msh", "mapping.json", "jacobians.npz", "jacobian_metadata.json", "mesher.log", "imported_geometry.json", "quality.json", "lifecycle.json"}
    if set(result["output_files"]) != wanted:
        raise ValueError("Complete native output manifest required")
    mapping = read_json(safe(root, "mapping.json"))
    if mapping["mesh_size_mm"] != request["profile"]["mesh_size_mm"]:
        raise ValueError("Returned native mesh size differs from frozen profile")
    check_mapping(mapping, catalog)
    if read_json(safe(root, "imported_geometry.json")) != {"observations": mapping["geometry_observations"], "join": mapping["geometry_join"]}:
        raise ValueError("Native geometry raw/readback mapping differs")
    lifecycle = read_json(safe(root, "lifecycle.json"))
    if lifecycle.get("initialize_succeeded") is not True or lifecycle.get("finalize_succeeded") is not True or lifecycle.get("initialize_attempts") != 1 or lifecycle.get("read_config_files") is not False or lifecycle.get("logger_started") is not True or lifecycle.get("solver_calls") != 0 or lifecycle.get("provider_calls") != 0:
        raise ValueError("Native owned initialize/finalize lifecycle is incomplete")
    verify_msh(safe(root, "mesh.msh"), mapping)
    quality = verify_jacobians(safe(root, "jacobians.npz"), mapping, result["jacobian_metadata"], catalog)
    if read_json(safe(root, "jacobian_metadata.json")) != result["jacobian_metadata"]:
        raise ValueError("Retained full Jacobian metadata differs")
    if read_json(safe(root, "quality.json")) != quality or result["quality"] != quality or quality["status"] != "PASS" or result.get("status") != "VALID_PREPROCESSING":
        raise ValueError("Mesh quality is invalid or returned quality differs")
    if result.get("mesh_revision") != digest(revision_material(result)):
        raise ValueError("Mesh revision does not bind actual bytes/observations")
    return result


def _invoke(output: Path) -> int:
    from ..execution_control import check_cancelled, wait_for_process, stop_owned_process
    check_request(output, read_json(safe(output, "request.json")))
    command = [SYSTEM_PYTHON, "-I", "-B", str(output / "capsule/fixture_assembly_mesh_worker.py"), str(output / "request.json")]
    check_cancelled()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", MKL_NUM_THREADS="2")
    started = time.monotonic()
    with (output / "worker.stdout.txt").open("x", encoding="utf-8") as stdout, (output / "worker.stderr.txt").open("x", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, cwd=output, env=env, stdout=stdout, stderr=stderr, start_new_session=os.name == "posix")
        try:
            code = wait_for_process(process, timeout=None)
        except BaseException:
            try:
                stop_owned_process(process, isolated_group=os.name == "posix")
            finally:
                save(output / "process.json", {"command": command, "exit_code": process.poll(), "policy": POLICY,
                    "interrupted": True, "owned_leader_reaped": process.poll() is not None,
                    "elapsed_seconds": time.monotonic()-started, "solver_calls": 0, "provider_calls": 0})
            raise
    save(output / "process.json", {"command": command, "exit_code": code, "policy": POLICY,
        "interrupted": False, "owned_leader_reaped": process.poll() is not None,
        "elapsed_seconds": time.monotonic()-started, "solver_calls": 0, "provider_calls": 0})
    if code != 0:
        raise RuntimeError(f"Assembly mesh worker exited with code {code}; no mesh admitted; evidence retained at {output}")
    return code


def mesh_parent(parent_result: dict, parent_root: Path, output: Path, mesh_size_mm: float) -> dict:
    """Private preprocessing helper: no material/analysis/research/Core outcome."""
    parent_root, output = Path(parent_root).absolute(), Path(output).absolute()
    if os.name != "posix" or sys.version.split()[0] != "3.12.3":
        raise ValueError("Existing WSL Lab Python3.12.3 controller is required")
    request = prepare_request(parent_result, parent_root, output, mesh_size_mm)
    request_bytes = file_entry(output / "request.json")
    _invoke(output)
    if file_entry(output / "request.json") != request_bytes:
        raise ValueError("Mesh request bytes changed during native execution")
    # Reuse the producer verifier again; old bytes and current source both matter.
    validate_parent(parent_result, parent_root)
    check_files(parent_root, request["parent_files"])
    if source_fingerprint() != request["source_files"]:
        raise ValueError("Assembly mesh source changed during native execution")
    result = read_json(safe(output, "result.json"))
    verify_output(output, result, request)
    return {"preflight_status": result["status"], "decision": "NOT_RELEASED", "mesh_revision": result["mesh_revision"],
            "parent": result["parent"], "profile": result["profile"], "policy": result["policy"],
            "artifacts": deepcopy(result["output_files"]), "mapping": "mapping.json", "quality": result["quality"],
            "runtime": result["runtime_after"], "source_files": result["source_files"],
            "solver_status": "NOT_RUN", "converged": None, "limitations": list(domain().LIMITATIONS)}
