"""Pure selection from retained, revision-bound CalculiX displacement fields.

Core must verify contained paths, exact artifact bytes/hashes, JSON and source
records before and after this call. This reader checks their supplied metadata
and physical layout; it never opens files, regenerates native data or executes
solvers. A mesh node is local to its field artifact, not a cross-run/sensor ID.
"""

from copy import deepcopy
import math
import re
import sys

from .fixture_field import _exterior, _FRD_NUMBER, _NUMBER


_COMPONENTS = ("UX", "UY", "UZ", "MAGNITUDE")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,79}\Z")
_SAFE_INTEGER = 2 ** 53 - 1
_COMMON = {"schema_version", "kind", "backend", "adapter_version", "parent_experiment_id",
           "cad_revision", "mesh_size_max_mm", "coordinate_frame", "position_unit",
           "displacement_unit", "force_unit", "static", "coverage", "qualification",
           "engineering_valid", "nodes", "elements", "boundary_faces", "loads",
           "node_count", "element_count", "boundary_face_count", "sources"}


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _integer(value, positive=True):
    return type(value) is int and (0 < value if positive else 0 <= value) and value <= _SAFE_INTEGER


def _sha(value):
    return type(value) is str and _SHA.fullmatch(value) is not None


def _id(value):
    return type(value) is str and _ID.fullmatch(value) is not None


def _keys(value, expected):
    return type(value) is dict and set(value) == set(expected)


def _vector(value):
    return type(value) is list and len(value) == 3 and all(_finite(item) for item in value)


def _same(left, right):
    if _finite(left) and _finite(right):
        return left == right
    if type(left) in (int, float) or type(right) in (int, float):
        return False
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(_same(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    return left == right


def _token(token, value, *, frd=False, maximum=None):
    if (type(token) is not str or (maximum is not None and len(token) > maximum) or
            not (_FRD_NUMBER if frd else _NUMBER).fullmatch(token)):
        return False
    return float(token.replace("D", "E").replace("d", "e")) == value


def _path(value):
    return (type(value) is str and 0 < len(value) <= 240 and
            re.search(r"[\\\x00-\x20:#?%]", value) is None and
            all(part not in ("", ".", "..") for part in value.split("/")))


def _context(result, proposal, artifact, selection):
    _need(_keys(selection, {"artifact", "sha256", "cad_revision", "node_id", "component"}) and
          _path(selection["artifact"]) and _sha(selection["sha256"]) and _sha(selection["cad_revision"]) and
          _integer(selection["node_id"]) and selection["component"] in _COMPONENTS,
          "Select an exact field artifact/hash/revision, positive node ID and supported displacement component")
    _need(type(result) is dict and type(proposal) is dict, "Field source envelopes must be mappings")
    backend = result["provenance"]["adapter"]
    _need(backend in ("structure.calculix.native", "fixture.calculix"), "Unsupported structural field family")
    parent, revision = result["parent_experiment_id"], result["cad_revision"]
    _need(_id(result["experiment_id"]) and _id(parent) and parent != result["experiment_id"] and _sha(revision) and
          result["status"] == "COMPLETED_REVIEW_REQUIRED" and result["converged"] is True and
          result["solver_status"] in ("COMPLETED", "CONVERGED") and result["decision"] == "NOT_RELEASED",
          "An unreleased, completed CAD-parent result is required")
    _need(proposal["id"] == result["experiment_id"] and proposal["parent_experiment_id"] == parent and
          proposal["study_id"] == result["study"]["id"] and proposal["physics"]["backend"] == backend and
          proposal["model"]["geometry"]["source_experiment_id"] == parent and
          proposal["model"]["geometry"]["cad_revision"] == revision and
          result["provenance"]["parent_experiment_id"] == parent and
          _same(proposal["execution"], result["provenance"]["execution_settings"]),
          "Proposal/result parent, CAD revision, study, backend or saved execution differs")
    manifest = {}
    _need(type(result["artifacts"]) is list, "A unique artifact manifest is required")
    for row in result["artifacts"]:
        _need(type(row) is dict and _path(row["path"]) and row["path"] not in manifest and
              _sha(row["sha256"]) and _integer(row["size_bytes"], False) and row["revision"] == revision,
              "Artifact path/hash/size/revision is invalid or duplicated")
        manifest[row["path"]] = row
    _need(type(artifact) is dict and _same(manifest.get(selection["artifact"]), artifact) and
          artifact["path"] == selection["artifact"] and artifact["sha256"] == selection["sha256"] and
          artifact["revision"] == selection["cad_revision"] == revision and
          _integer(artifact["size_bytes"]) and artifact["mime_type"] == "application/json",
          "Selected field entry must equal its original manifest/hash/CAD revision")
    return backend, manifest


def _sources(raw, manifest, prefix, names):
    _need(_keys(raw["sources"], names), "The original five structural source pins are required")
    for name, filename in names.items():
        source = raw["sources"][name]
        entry = manifest.get(prefix + filename)
        _need(_keys(source, {"path", "sha256", "bytes"}) and source["path"] == filename and
              _sha(source["sha256"]) and _integer(source["bytes"]) and entry is not None and
              source["sha256"] == entry["sha256"] and source["bytes"] == entry["size_bytes"],
              "Structural field source path/hash/size does not match its manifest")


def _geometry(raw, native):
    for key, count in (("nodes", "node_count"), ("elements", "element_count"), ("boundary_faces", "boundary_face_count")):
        _need(type(raw[key]) is list and _integer(raw[count]) and raw[count] == len(raw[key]),
              "Complete node/element/exterior coverage counts are required")
    nodes, previous = {}, 0
    for row in raw["nodes"]:
        _need(_keys(row, {"node_id", "position_mm", "displacement_mm", "displacement_tokens"}) and
              _integer(row["node_id"]) and row["node_id"] > previous and _vector(row["position_mm"]) and
              _vector(row["displacement_mm"]) and math.isfinite(math.hypot(*row["displacement_mm"])) and
              type(row["displacement_tokens"]) is list and len(row["displacement_tokens"]) == 3 and
              all(_token(token, value, frd=not native) for token, value in
                  zip(row["displacement_tokens"], row["displacement_mm"])),
              "Every actual node requires a unique positive ID, finite XYZ/U and matching native tokens")
        nodes[row["node_id"]] = row
        previous = row["node_id"]
    elements, used, previous = {}, set(), 0
    for row in raw["elements"]:
        ids = row["node_ids"]
        _need(_keys(row, {"element_id", "type", "node_ids"}) and _integer(row["element_id"]) and
              row["element_id"] > previous and row["type"] == "C3D10" and type(ids) is list and
              len(ids) == 10 and all(_integer(node) and node in nodes for node in ids) and len(set(ids)) == 10,
              "Complete original C3D10 connectivity is required")
        elements[row["element_id"]] = ids
        used.update(ids)
        previous = row["element_id"]
    _need(used == nodes.keys(), "Field nodes must exactly cover the complete element node set")
    groups, previous = {}, 0
    group_key = "selection_id" if native else "group"
    for row in raw["boundary_faces"]:
        ids = row["node_ids"]
        group = row[group_key]
        _need(_keys(row, {"element_id", "type", "node_ids", group_key}) and _integer(row["element_id"]) and
              row["element_id"] > previous and row["element_id"] not in elements and row["type"] == "CPS6" and
              type(ids) is list and len(ids) == 6 and all(_integer(node) and node in nodes for node in ids) and
              len(set(ids)) == 6 and (_id(group) if native else type(group) is str and
                                   re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", group) is not None),
              "Original CPS6 boundary IDs, groups and midside connectivity are required")
        groups.setdefault(group, set()).update(ids)
        previous = row["element_id"]
    # Existing pure parser invariant, including complete exterior, midside
    # association and nonmanifold refusal. No native syntax or files are read.
    boundary_nodes = _exterior(elements, raw["boundary_faces"])
    return nodes, groups, boundary_nodes


def _native(raw, result, proposal, artifact, manifest, nodes, groups, boundary_nodes):
    execution, details = proposal["execution"], result["provenance"]["adapter_details"]
    _need(artifact["path"] == "simulation/field.json" and result["provenance"]["adapter_version"] == "1" and
          raw["adapter_version"] == "1" and raw["kind"] == "native_structural_nodal_displacement" and
          raw["coordinate_frame"] == "CAD_DOCUMENT_GLOBAL" and result["solver_status"] == "COMPLETED",
          "Unsupported native structural producer/path/frame")
    declaration, catalog = execution["declaration"], execution["native_catalog"]
    _need(execution["analysis_type"] == declaration["analysis_type"] == "linear_static" and
          declaration["units"] == {"length": "mm", "force": "N", "stress": "MPa"} and
          declaration["coordinate_system"] == "global" and _same(execution["mesh"], declaration["mesh"]) and
          declaration["mesh"]["mode"] == "selected" and
          _finite(declaration["mesh"]["max_size_mm"]) and declaration["mesh"]["max_size_mm"] > 0 and
          _finite(raw["mesh_size_max_mm"]) and raw["mesh_size_max_mm"] > 0 and
          raw["mesh_size_max_mm"] == declaration["mesh"]["max_size_mm"] and
          _sha(raw["native_catalog_revision"]) and raw["native_catalog_revision"] == catalog["native_catalog_revision"] and
          _same(proposal["boundary_conditions"], declaration["boundary_conditions"]) and
          _same(proposal["loads"], declaration["loads"]) and _same(proposal["model"]["materials"], declaration["materials"]),
          "Native catalog, selected mesh or declared conditions differ from the original proposal")
    materials = declaration["materials"]
    _need(type(materials) is list and len(materials) == 1 and materials[0]["selection_id"] == "B-final" and
          materials[0]["law"] == "isotropic_linear_elastic" and
          _finite(materials[0]["young_modulus_MPa"]) and materials[0]["young_modulus_MPa"] > 0 and
          _finite(materials[0]["poisson_ratio"]) and -1 < materials[0]["poisson_ratio"] < .5 and
          declaration["contact"]["mode"] == "none" and not declaration["contact"].get("pairs"),
          "Only the retained single-solid isotropic elastic, no-contact producer is supported")
    _sources(raw, manifest, "simulation/", {"mesh": "mesh.json", "deck": "native.inp", "boundary": "boundary.json",
                                           "frd": "native.frd", "dat": "native.dat"})
    _need(raw["deck_sha256"] == raw["sources"]["deck"]["sha256"] and _sha(raw["parent_step_sha256"]) and
          raw["parent_step_sha256"] == details["parent_step_sha256"] and details["field_artifact"] == artifact["path"],
          "Native deck/parent STEP/field source metadata differs")
    faces = {}
    for face in catalog["selections"]:
        if face.get("kind") == "native_face":
            _need(_id(face["id"]) and face["id"] not in faces, "Ambiguous native face catalog identity")
            faces[face["id"]] = face
    _need(groups and set(groups) <= faces.keys(), "Boundary groups must retain this catalog's native face identities")
    expected, prescribed = {}, {}
    for bc in declaration["boundary_conditions"]:
        _need(bc["type"] == "displacement" and bc["selection_id"] in groups and bc["unit"] == "mm" and bc["coordinate_system"] == "global" and
              type(bc["components"]) is dict and bc["components"] and set(bc["components"]) <= {"UX", "UY", "UZ"},
              "Native displacement declarations require the actual face and explicit global DOFs")
        for node in groups[bc["selection_id"]]:
            for component, value in bc["components"].items():
                key = (node, _COMPONENTS.index(component) + 1)
                _need(_finite(value) and (key not in expected or expected[key] == value), "Conflicting/nonfinite native DOF")
                expected[key] = value
    _need(type(raw["prescribed_dofs"]) is list and raw["prescribed_dofs"], "Native prescribed DOFs are missing")
    for row in raw["prescribed_dofs"]:
        key = (row["node_id"], row["component"])
        _need(_keys(row, {"node_id", "component", "value_mm", "declared_value_mm", "value_token"}) and
              _integer(row["node_id"]) and row["node_id"] in boundary_nodes and type(row["component"]) is int and
              row["component"] in (1, 2, 3) and key not in prescribed and key in expected and
              _finite(row["value_mm"]) and _finite(row["declared_value_mm"]) and
              row["declared_value_mm"] == expected[key] and
              abs(row["value_mm"] - expected[key]) <= 1e-12 * max(1, abs(expected[key])) and
              _token(row["value_token"], row["value_mm"], maximum=20), "Native prescribed DOF/source token differs")
        prescribed[key] = row["value_mm"]
    _need(prescribed.keys() == expected.keys(), "Native declared displacement DOFs are incomplete")
    permitted, target = set(), [0.0, 0.0, 0.0]
    for load in declaration["loads"]:
        _need(load["type"] == "resultant_force" and load["selection_id"] in groups and load["unit"] == "N" and load["coordinate_system"] == "global" and
              _keys(load["components"], {"FX", "FY", "FZ"}), "Native force declarations require an actual global face/vector")
        for axis, component in enumerate(("FX", "FY", "FZ")):
            value = load["components"][component]
            _need(_finite(value), "Native declared force is nonfinite")
            target[axis] += value
            if value != 0:
                permitted.update((node, axis + 1) for node in groups[load["selection_id"]])
    weights, assigned = [[], [], []], set()
    _need(type(raw["loads"]) is list and raw["loads"], "Native signed nodal loads are missing")
    for row in raw["loads"]:
        key = (row["node_id"], row["component"])
        _need(_keys(row, {"node_id", "component", "force_N", "integration_force_N", "force_token"}) and _integer(row["node_id"]) and
              type(row["component"]) is int and row["component"] in (1, 2, 3) and key in permitted and
              key not in prescribed and key not in assigned and _finite(row["force_N"]) and
              _finite(row["integration_force_N"]) and row["integration_force_N"] != 0 and
              row["force_token"] == format(row["integration_force_N"], ".12e") and
              _token(row["force_token"], row["force_N"], maximum=20), "Native signed load DOF/source token differs")
        assigned.add(key)
        weights[row["component"] - 1].append(row["force_N"])
    _need(all(_finite(total) and _finite(expected_value) and abs(total - expected_value) <= 1e-10 * max(1, abs(expected_value))
              for total, expected_value in zip((math.fsum(values) for values in weights), target)),
          "Native nodal resultants differ from the declared signed force vector")
    _need(_same(raw["load_regions"], details["boundary"]["load_regions"]), "Native load-region association differs")
    peak = max(math.hypot(*node["displacement_mm"]) for node in nodes.values())
    metric = result["metrics"]["max_displacement"]
    _need(_integer(raw["peak_node_id"]) and raw["peak_node_id"] in nodes and
          abs(math.hypot(*nodes[raw["peak_node_id"]]["displacement_mm"]) - peak) <= 8 * sys.float_info.epsilon * max(peak, math.ulp(0.0)) and
          metric["valid"] is True and metric["unit"] == "mm" and _finite(metric["value"]) and
          abs(metric["value"] - peak) <= 8 * sys.float_info.epsilon * max(peak, metric["value"], math.ulp(0.0)),
          "Native whole-field peak differs from its same-record vector-magnitude metric")


def _fixture(raw, result, proposal, artifact, manifest, nodes, groups, boundary_nodes):
    match = re.fullmatch(r"simulation/support_([0-7])/fea_field\.json", artifact["path"])
    version, details, mesh = result["provenance"]["adapter_version"], result["provenance"]["adapter_details"], proposal["execution"]["mesh"]
    _need(match is not None and version in ("5", "6") and raw["adapter_version"] in ("5", "6") and
          int(raw["adapter_version"]) <= int(version) and raw["kind"] == "fixture_calculix_nodal_displacement" and
          raw["coordinate_frame"] == "SOLVER_GLOBAL_CARTESIAN" and details["adapter"] == "fixture.calculix" and
          details["adapter_version"] == version and details["parent_experiment_id"] == result["parent_experiment_id"] and
          details["cad_revision"] == result["cad_revision"], "Unsupported fixture producer/path/frame or parent metadata")
    index, sizes = int(match[1]), details["mesh_max_sizes_mm"]
    _need(type(sizes) is list and 1 <= len(sizes) <= 8 and _same(sizes, mesh["max_sizes_mm"]) and
          all(_finite(size) and size > 0 and (i == 0 or sizes[i - 1] > size) for i, size in enumerate(sizes)) and
          index < len(sizes) and type(raw["mesh_index"]) is int and raw["mesh_index"] == index and
          _finite(raw["mesh_size_max_mm"]) and raw["mesh_size_max_mm"] == sizes[index],
          "Fixture field must retain its actual recorded mesh level/size")
    if mesh.get("mode") == "selected":
        metric = result["metrics"]["displacement_mesh_change_ratio"]
        _need(version == "6" and len(sizes) == 1 and details["mesh_policy"]["mode"] == "selected" and
              details["mesh_sensitivity"]["status"] == "NOT_ASSESSED" and metric["valid"] is False and metric["value"] is None,
              "Selected fixture mesh cannot acquire a mesh-sensitivity verdict")
    else:
        _need("mode" not in mesh and len(sizes) >= 2, "Unsupported fixture refinement policy")
    prefix = f"simulation/support_{index}/"
    names = {"mesh": "gmsh.inp", "deck": f"support_{index}.inp", "saddle": "saddle_load.json",
             "frd": f"support_{index}.frd", "dat": f"support_{index}.dat"}
    _sources(raw, manifest, prefix, names)
    _need(type(raw["fixed_node_ids"]) is list and raw["fixed_node_ids"] and
          _same(raw["fixed_dofs"], [1, 2, 3]), "Original fixture XYZ fixed-node declarations are required")
    previous, fixed = 0, set()
    for node in raw["fixed_node_ids"]:
        _need(_integer(node) and node > previous and node in boundary_nodes, "Invalid fixture fixed-node identity")
        fixed.add(node)
        previous = node
    minimum = min(node["position_mm"][2] for node in nodes.values())
    _need(all((node_id in fixed) == (abs(node["position_mm"][2] - minimum) < 1e-4) for node_id, node in nodes.items()),
          "Fixture fixed nodes differ from the recorded whole minimum-Z base")
    _need(type(raw["loads"]) is list and 0 < len(raw["loads"]) <= len(nodes), "Fixture signed saddle loads are missing")
    previous, loaded, forces = 0, set(), []
    for row in raw["loads"]:
        _need(_keys(row, {"node_id", "force_N", "dof", "force_token"}) and _integer(row["node_id"]) and
              row["node_id"] > previous and row["node_id"] in boundary_nodes and row["node_id"] not in fixed and
              type(row["dof"]) is int and row["dof"] == 3 and _vector(row["force_N"]) and
              row["force_N"][0] == row["force_N"][1] == 0 and row["force_N"][2] < 0 and
              _token(row["force_token"], row["force_N"][2]), "Fixture load node/vector/native token differs")
        loaded.add(row["node_id"])
        forces.append(-row["force_N"][2])
        previous = row["node_id"]
    _need(sum(loaded <= members for members in groups.values()) == 1, "Fixture loaded nodes lack one original saddle group")
    expected, total = details["force_per_support_N"], math.fsum(forces)
    _need(_finite(expected) and expected > 0 and _finite(total) and abs(total - expected) <= 1e-8 * expected,
          "Fixture nodal resultant differs from the original support force")
    study = details["per_mesh_displacement"]["studies"][index]
    _need(type(study["index"]) is int and study["index"] == index and study["mesh_size_max_mm"] == sizes[index] and
          type(study["loaded_node_count"]) is int and study["loaded_node_count"] == len(loaded) and
          study["displacement_table"] == prefix + names["dat"] and
          study["displacement_table_sha256"] == raw["sources"]["dat"]["sha256"],
          "Fixture loaded-saddle statistics do not refer to this same mesh/DAT artifact")


def select_field_response(result, proposal, raw, artifact, selection):
    """Select an exact retained node/component, never a nearest point or history.

    The supplied JSON must come from Core-verified artifact bytes. Mathematical
    magnitude is explicitly derived; coordinates are undeformed native positions.
    Physical alignment and qualification remain unverified/UNKNOWN.
    """
    try:
        backend, manifest = _context(result, proposal, artifact, selection)
        native = backend == "structure.calculix.native"
        extra = ({"native_catalog_revision", "parent_step_sha256", "deck_sha256", "peak_node_id", "prescribed_dofs", "load_regions"}
                 if native else {"mesh_index", "fixed_node_ids", "fixed_dofs"})
        _need(_keys(raw, _COMMON | extra) and raw["schema_version"] == "1.0" and raw["backend"] == backend and
              raw["parent_experiment_id"] == result["parent_experiment_id"] and raw["cad_revision"] == result["cad_revision"] and
              raw["position_unit"] == raw["displacement_unit"] == "mm" and raw["force_unit"] == "N" and
              raw["coverage"] == "ALL_MESH_NODES" and raw["qualification"] == "UNKNOWN" and raw["engineering_valid"] is False and
              _keys(raw["static"], {"step", "increment", "load_parameter"}) and
              type(raw["static"]["step"]) is int and raw["static"]["step"] == 1 and
              type(raw["static"]["increment"]) is int and raw["static"]["increment"] == 1 and
              _finite(raw["static"]["load_parameter"]) and raw["static"]["load_parameter"] == 1,
              "Original displacement field schema/units/coverage/qualification/static declaration is unsupported")
        nodes, groups, boundary_nodes = _geometry(raw, native)
        (_native if native else _fixture)(raw, result, proposal, artifact, manifest, nodes, groups, boundary_nodes)
        _need(selection["node_id"] in nodes, "The selected original node does not exist in this field/mesh")
        node, component = nodes[selection["node_id"]], selection["component"]
        value = math.hypot(*node["displacement_mm"]) if component == "MAGNITUDE" else node["displacement_mm"][_COMPONENTS.index(component)]
        return {"value": value, "unit": "mm", "source_field": {
            "artifact": artifact["path"], "sha256": artifact["sha256"], "cad_revision": raw["cad_revision"],
            "node_id": node["node_id"], "component": component, "quantity": "DISPLACEMENT",
            "position_mm": deepcopy(node["position_mm"]), "position_unit": "mm", "coordinate_frame": raw["coordinate_frame"],
            "value_origin": "DERIVED_MAGNITUDE" if component == "MAGNITUDE" else "NATIVE_COMPONENT",
            "static": deepcopy(raw["static"]), "coverage": raw["coverage"]},
            "qualification": "UNKNOWN", "alignment": "USER_DECLARED_UNVERIFIED"}
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as exc:
        raise ValueError("Malformed or incomplete retained structural field contract") from exc
