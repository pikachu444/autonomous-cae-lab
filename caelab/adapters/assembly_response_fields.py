"""Pure retained assembly field selection and bounded browser projection.

Core supplies strictly decoded, manifest/hash/size/path-verified JSON, and
rechecks the same result/proposal/artifacts after reading. No files, HTTP,
native APIs or solver processes are opened here. The returned display is
derived presentation data, not a new immutable experiment artifact.
"""

from copy import deepcopy
import json
import math
import sys

from .structural_response_fields import _need, _finite, _integer, _sha, _id, _keys, _vector, _same, _path
from .fixture_assembly_native_import_worker import source_catalog, PERMUTATIONS, COORDINATE_ABSOLUTE_MM, SOURCE_COMMIT
from .fixture_assembly_field_geometry import exterior_nodes, _FACES
from ..storage import canonical_hash
from plugins.fixture_design.assembly_mesh import ACTIVE


BACKEND = "fixture.assembly_mechanics.code_aster"
FIELD_PATH = "simulation/admitted-fields.json"
MAPPING_PATH = "simulation/mesh-reuse/mapping.json"
AXIS = "DIMENSIONLESS_STATIC_LOAD_PARAMETER_NOT_PHYSICAL_TIME"
COMPONENTS = ("UX", "UY", "UZ", "MAGNITUDE")
# Presentation allocation limits, not engineering or native source-file limits.
# Retained coarse3: 76,214 nodes /44,226 TETRA10 /17,118 TRIA6. No fine1_5 claim.
DISPLAY_LIMITS = {"nodes": 100000, "elements": 60000, "faces": 25000,
                  "triangles": 100000, "bytes": 64 * 1024 * 1024}
SOURCE_LIMITS = {"field": 536870912, "mapping": 134217728}
_SUBTRIANGLES = ((0, 3, 5), (3, 1, 4), (5, 4, 2), (3, 4, 5))
_RAW_KEYS = {"scope", "bodies", "order", "native_import_comparison", "geometry_checks",
             "geometry_order_binding", "load_parameter", "available_orders", "actual_load_parameters", "initial_state",
             "axis_semantics", "coordinate_frame", "field_validity"}
_LIMITATIONS = (
    "Derived bounded display; source artifacts/result hashes are verified by Core before and after reading.",
    "Original positive source node IDs and distinct bodies are preserved; coincident XYZ is never merged.",
    "Four linear display triangles per original TRIA6 face are not quadratic geometry or an engineering reference.",
    "Outward display winding is derived from the adjacent tetrahedron's opposite corner, not a native field.",
    "The static load parameter is dimensionless, not physical time or an interpolated history sample.",
    "Signed native U/RF is retained; |U| is explicitly derived, without unit conversion or metric replacement.",
    "Complete native Gauss stresses remain in the source artifact; no nodal stress is constructed or colored.",
    "Mesh sensitivity, physical material/mount/contact/strength/durability qualification remain UNKNOWN; NOT_RELEASED.",
)


def _entry(manifest, supplied, path):
    _need(type(supplied) is dict and _same(manifest.get(path), supplied) and supplied["path"] == path
          and _integer(supplied["size_bytes"]) and supplied["mime_type"] == "application/json",
          "Assembly JSON entry must equal its recorded manifest path/hash/bytes/revision")


def _pin(manifest, path, pin):
    entry = manifest.get(path)
    _need(_path(path) and _keys(pin, {"sha256", "size_bytes"}) and _sha(pin["sha256"])
          and _integer(pin["size_bytes"]) and entry is not None
          and entry["sha256"] == pin["sha256"] and entry["size_bytes"] == pin["size_bytes"],
          "Retained assembly native source pin differs from its artifact manifest")
    return entry


def _context(result, proposal, artifact, mapping_artifact):
    _need(type(result) is dict and type(proposal) is dict, "Assembly source envelopes must be mappings")
    parent, revision, provenance = result["parent_experiment_id"], result["cad_revision"], result["provenance"]
    details, execution = provenance["adapter_details"], proposal["execution"]
    _need(_id(result["experiment_id"]) and _id(parent) and parent != result["experiment_id"] and _sha(revision)
          and _id(result["study"]["id"]) and result["status"] == "COMPLETED_REVIEW_REQUIRED"
          and result["solver_status"] == "COMPLETED" and result["converged"] is True
          and result["decision"] == "NOT_RELEASED" and provenance["adapter"] == BACKEND
          and provenance["adapter_version"] == details["adapter_version"] == "1" and details["adapter"] == BACKEND,
          "An unreleased completed version-1 retained assembly result is required")
    _need(proposal["id"] == result["experiment_id"] and proposal["parent_experiment_id"] == parent
          and proposal["study_id"] == result["study"]["id"] and proposal["physics"]["backend"] == BACKEND
          and proposal["model"]["geometry"] == {"source_experiment_id": parent, "cad_revision": revision}
          and provenance["parent_experiment_id"] == parent and _same(execution, provenance["execution_settings"])
          and _same(execution, details["execution_settings"])
          and provenance["proposal_sha256"] == result["proposal_revision"] == canonical_hash(proposal),
          "Assembly proposal/result/study/backend/parent/execution revision differs")
    declaration, catalog, mesh = execution["declaration"], execution["catalog"], execution["mesh"]
    retained, reuse, cad_parent = catalog["retained_mesh"], details["reuse"], details["cad_parent"]
    _need(execution["analysis_type"] == declaration["analysis_type"] == "nonlinear_static"
          and declaration["units"] == {"length": "mm", "force": "N", "stress": "MPa"}
          and declaration["coordinate_system"] == "global" and _same(mesh, declaration["mesh"])
          and _keys(mesh, {"mode", "mesh_revision"}) and mesh["mode"] == "retained" and _sha(mesh["mesh_revision"])
          and mesh["mesh_revision"] == retained["mesh_revision"] == details["mesh_revision"] == reuse["mesh_revision"]
          and catalog["cad_revision"] == retained["cad_revision"] == revision
          and catalog["cad_backend"] == "fixture.assembly" and catalog["model"] == "bending_assembly"
          and retained["profile"] == "coarse3" and retained["active_components"] == list(ACTIVE)
          and _keys(reuse["parent"], {"experiment_id", "cad_revision", "native_revision"})
          and all(cad_parent[key] == reuse["parent"][key] for key in reuse["parent"])
          and cad_parent["experiment_id"] == parent and cad_parent["cad_revision"] == revision and _sha(cad_parent["native_revision"])
          and reuse["status"] == "CAPTURED_BYTE_REUSE" and reuse["capture_only"] is True
          and _same(proposal["loads"], declaration["loads"])
          and _same(proposal["boundary_conditions"], declaration["boundary_conditions"])
          and _same(proposal["model"]["materials"], declaration["materials"]),
          "Assembly retained mesh/CAD revision, declared units or same-record conditions differ")
    _need(type(result["metrics"]) is dict and type(result["validations"]) is list
          and all(type(row) is dict and row["status"] in ("PASS", "FAIL", "UNKNOWN")
                  and type(row["blocking"]) is bool and row["experiment_id"] == result["experiment_id"]
                  and row["cad_revision"] == revision for row in result["validations"]),
          "Recorded metrics and same-record validation verdicts are required")
    manifest, folded = {}, set()
    _need(type(result["artifacts"]) is list and 0 < len(result["artifacts"]) <= 4096, "Bounded artifact manifest required")
    for row in result["artifacts"]:
        _need(type(row) is dict and _path(row["path"]) and row["path"].casefold() not in folded
              and _sha(row["sha256"]) and _integer(row["size_bytes"], False) and row["revision"] == revision,
              "Invalid/aliased assembly artifact path/hash/size/CAD revision")
        manifest[row["path"]] = row
        folded.add(row["path"].casefold())
    _entry(manifest, artifact, FIELD_PATH)
    _entry(manifest, mapping_artifact, MAPPING_PATH)
    _need(artifact["size_bytes"] <= SOURCE_LIMITS["field"] and mapping_artifact["size_bytes"] <= SOURCE_LIMITS["mapping"],
          "Retained assembly JSON exceeds its explicit source-read resource bound")
    sources = [artifact, mapping_artifact]
    for path, pin in (("simulation/native/worker-result.json", details["worker_result_entry"]),
                      ("simulation/native/native-catalog.json", details["native_catalog_entry"]),
                      ("simulation/mesh-reuse/mesh.msh", details["original_mesh_entry"])):
        sources.append(_pin(manifest, path, pin))
    receipt = reuse["receipt"]
    _need(receipt["path"] == "mesh-reuse-receipt.json", "Unsupported retained mesh receipt path")
    sources.append(_pin(manifest, "simulation/mesh-reuse/" + receipt["path"],
                        {key: receipt[key] for key in ("sha256", "size_bytes")}))
    native = details["retained_native_files"]
    for name in ("depl.table.json", "reac_noda.table.json", "sief_elga.table.json", "coor_elga.table.json"):
        sources.append(_pin(manifest, "simulation/native/" + name, native["native/" + name]))
    return details, deepcopy(sources)


def _geometry(raw, mapping):
    _need(_keys(raw, _RAW_KEYS) and raw["scope"] == "COMPLETE_NATIVE_ASSEMBLY_MECHANICS_FIELDS"
          and raw["axis_semantics"] == AXIS and raw["coordinate_frame"] == "global_assembly_cartesian_mm"
          and raw["field_validity"] == "COMPLETE_NATIVE_OBSERVATION_NOT_PHYSICAL_QUALIFICATION"
          and _integer(raw["order"]) and _finite(raw["load_parameter"]) and raw["load_parameter"] == 1
          and raw["geometry_order_binding"] == "DERIVED_COMMAND_CONTEXT_NOT_NATIVE_GEOMETRY_ORDER"
          and type(raw["bodies"]) is dict and set(raw["bodies"]) == set(ACTIVE),
          "Complete assembly field/frame/static-order/body scope differs")
    orders, parameters = raw["available_orders"], raw["actual_load_parameters"]
    _need(type(orders) is list and orders and all(_integer(i, False) for i in orders)
          and orders == sorted(set(orders)) and raw["order"] == orders[-1]
          and type(parameters) is list and len(parameters) == len(orders) and all(_finite(i) for i in parameters)
          and parameters in ([0., .25, .5, .75, 1.], [.25, .5, .75, 1.])
          and raw["load_parameter"] == parameters[-1]
          and raw["initial_state"] == ("NATIVE_STORED" if parameters[0] == 0 else "NOT_STORED"),
          "Actual native orders/static increments/initial-state observation differs; zero is never invented")
    _need(type(mapping) is dict and mapping["mesh_size_mm"] == 3 and type(mapping["mesh_size_mm"]) in (int, float)
          and type(mapping["nodes"]) is list and 0 < len(mapping["nodes"]) <= DISPLAY_LIMITS["nodes"]
          and type(mapping["elements"]) is list
          and 0 < len(mapping["elements"]) <= DISPLAY_LIMITS["elements"] + DISPLAY_LIMITS["faces"],
          "Retained coarse3 data exceeds the assembly display resource envelope")
    source = source_catalog(mapping)
    _need(set(source["bodies"]) == set(ACTIVE) and all(_integer(i) for i in source["nodes"])
          and all(_integer(i) for i in source["elements"]), "Original source IDs must be positive safe integers on seven distinct bodies")
    comparison = raw["native_import_comparison"]
    ids, cell_ids = comparison["source_node_ids_by_native_index"], comparison["source_element_ids_by_native_index"]
    _need(comparison["status"] == "PASS" and comparison["scope"] == "NATIVE_IMPORT_ONLY"
          and comparison["decision"] == "NOT_RELEASED" and comparison["solver_status"] == "NOT_RUN"
          and type(comparison["node_count"]) is int and comparison["node_count"] == len(source["nodes"])
          and type(comparison["cell_count"]) is int and comparison["cell_count"] == len(source["elements"])
          and type(comparison["group_count"]) is int and comparison["group_count"] == 84
          and type(ids) is list and len(ids) == len(source["nodes"]) and all(_integer(i) for i in ids)
          and len(set(ids)) == len(ids) and set(ids) == set(source["nodes"])
          and type(cell_ids) is list and len(cell_ids) == len(source["elements"]) and all(_integer(i) for i in cell_ids)
          and len(set(cell_ids)) == len(cell_ids) and set(cell_ids) == set(source["elements"])
          and _same(comparison["element_permutations"], {str(key): list(value) for key, value in PERMUTATIONS.items()})
          and comparison["ordering_source_commit"] == SOURCE_COMMIT
          and comparison["coordinate_absolute_limit_mm"] == COORDINATE_ABSOLUTE_MM
          and _finite(comparison["maximum_coordinate_error_mm"])
          and 0 <= comparison["maximum_coordinate_error_mm"] <= COORDINATE_ABSOLUTE_MM
          and comparison["compiled_image_source_equivalence"] == "UNKNOWN",
          "Original source/native node/cell/order/permutation bijections are incomplete or changed")
    observed_bodies = comparison["bodies"]
    _need(type(observed_bodies) is list and len(observed_bodies) == len(ACTIVE)
          and all(_keys(row, {"component_id", "volume_group", "node_count", "cell_count"})
                  and row["component_id"] in source["bodies"] and row["volume_group"] == source["bodies"][row["component_id"]]
                  and _integer(row["node_count"]) and row["node_count"] == len(source["group_nodes"][row["volume_group"]])
                  and _integer(row["cell_count"]) and row["cell_count"] == len(source["group_cells"][row["volume_group"]])
                  for row in observed_bodies)
          and len({row["component_id"] for row in observed_bodies}) == len(ACTIVE),
          "Native import per-body counts/volume-group identity differs")
    reverse_nodes = {node: index for index, node in enumerate(ids)}
    reverse_cells = {element: index for index, element in enumerate(cell_ids)}
    cells, body_cells, elements, faces = [], [], [], []
    for index, eid in enumerate(cell_ids):
        row = source["elements"][eid]
        kind = "TETRA10" if row["type"] == 11 else "TRIA6"
        conn = [reverse_nodes[row["node_ids"][i]] for i in PERMUTATIONS[row["type"]]]
        cells.append({"index": index, "type": kind, "node_indices": conn})
        output = {"element_id": eid, "node_ids": deepcopy(row["node_ids"]), "component_id": row["component_id"], "type": kind}
        if kind == "TETRA10":
            elements.append(output)
        else:
            output["physical_group"] = next(name for name, group in source["groups"].items()
                                           if group["dim"] == 2 and group["tag"] == row["physical_tag"])
            faces.append(output)
    _need(len(elements) <= DISPLAY_LIMITS["elements"] and len(faces) <= DISPLAY_LIMITS["faces"]
          and 4 * len(faces) <= DISPLAY_LIMITS["triangles"], "Complete connectivity exceeds the assembly display resource envelope")
    for component in ACTIVE:
        body_cells.append({"component_id": component,
            "volume_cell_indices": sorted(reverse_cells[i] for i in source["group_cells"][source["bodies"][component]]),
            "face_cell_indices": sorted(reverse_cells[i] for name, group in source["groups"].items()
                                        if group["dim"] == 2 and group["component_id"] == component for i in source["group_cells"][name])})
    exterior = {row["component_id"]: set(row["exterior_node_indices"]) for row in exterior_nodes(cells, body_cells)}
    nodes, seen, gauss_count, maximum_error, bodies = [], set(), 0, 0.0, []
    for component, topology in zip(ACTIVE, body_cells):
        body = raw["bodies"][component]
        _need(_keys(body, {"nodes", "gauss", "qualified_mesh_volume_mm3", "native_energy"})
              and _finite(body["qualified_mesh_volume_mm3"]) and body["qualified_mesh_volume_mm3"] > 0
              and type(body["native_energy"]) is dict and body["native_energy"]["status"] in ("OBSERVED", "UNKNOWN")
              and type(body["nodes"]) is list and type(body["gauss"]) is list,
              "Original complete body field/volume/energy metadata is required")
        energy = body["native_energy"]
        if energy["status"] == "UNKNOWN":
            _need(_keys(energy, {"status", "value_n_mm", "reason"}) and energy["value_n_mm"] is None
                  and type(energy["reason"]) is str, "Unavailable native body energy must remain UNKNOWN/null")
        else:
            _need(_keys(energy, {"status", "value_n_mm", "basis", "volume_group", "order", "raw_table_retained"})
                  and _finite(energy["value_n_mm"]) and energy["value_n_mm"] > 0
                  and energy["basis"] == "NATIVE_POST_ELEM_ENER_POT_TOTALE" and energy["volume_group"] == source["bodies"][component]
                  and type(energy["order"]) is int and energy["order"] == raw["order"] and energy["raw_table_retained"] is True,
                  "Native body energy observation/source order differs")
        group = source["bodies"][component]
        _need(len(body["nodes"]) == len(source["group_nodes"][group]), "Body node count is incomplete")
        for row in body["nodes"]:
            index, nid = row["native_index"], row["source_node_id"]
            _need(_keys(row, {"native_index", "source_node_id", "xyz_mm", "displacement_mm", "reaction_n", "exterior"})
                  and _integer(index, False) and index < len(ids) and _integer(nid) and nid == ids[index]
                  and nid in source["group_nodes"][group] and nid not in seen and _vector(row["xyz_mm"])
                  and _vector(row["displacement_mm"]) and math.isfinite(math.hypot(*row["displacement_mm"]))
                  and _vector(row["reaction_n"]) and type(row["exterior"]) is bool
                  and row["exterior"] == (index in exterior[component]),
                  "Every original body node requires exact ID/native index/exterior and finite native XYZ/U/RF")
            error = max(abs(a - b) for a, b in zip(row["xyz_mm"], source["nodes"][nid]))
            _need(error <= COORDINATE_ABSOLUTE_MM, "Native/source XYZ exceeds the retained import coordinate identity limit")
            maximum_error = max(maximum_error, error)
            seen.add(nid)
            nodes.append({"node_id": nid, "position_mm": deepcopy(row["xyz_mm"]),
                "displacement_mm": deepcopy(row["displacement_mm"]), "reaction_n": deepcopy(row["reaction_n"]),
                "component_id": component, "native_index": index, "exterior": row["exterior"]})
        wanted = {(index, point) for index in topology["volume_cell_indices"] for point in range(1, 6)}
        _need(len(body["gauss"]) == len(wanted), "Complete native Gauss coverage is required, never nodal stress")
        actual = set()
        for row in body["gauss"]:
            index, point = row["native_cell_index"], row["point"]
            reference = row["derived_geometry_reference"]
            _need(_keys(row, {"native_cell_index", "source_element_id", "point", "subpoint", "order", "xyz_mm",
                              "weight_mm3", "stress6_mpa", "derived_geometry_reference"})
                  and _integer(index, False) and type(point) is int and (index, point) in wanted and (index, point) not in actual
                  and _integer(row["source_element_id"]) and row["source_element_id"] == cell_ids[index]
                  and type(row["subpoint"]) is int and row["subpoint"] == 1 and type(row["order"]) is int and row["order"] == raw["order"]
                  and _vector(row["xyz_mm"]) and _finite(row["weight_mm3"]) and row["weight_mm3"] != 0
                  and type(row["stress6_mpa"]) is list and len(row["stress6_mpa"]) == 6 and all(_finite(v) for v in row["stress6_mpa"])
                  and _keys(reference, {"point", "reference_xyz", "reference_weight", "xyz_mm", "signed_jacobian_mm3", "native_expected_weight_mm3"})
                  and type(reference["point"]) is int and reference["point"] == point
                  and _vector(reference["reference_xyz"]) and _vector(reference["xyz_mm"])
                  and all(_finite(reference[key]) for key in ("reference_weight", "signed_jacobian_mm3", "native_expected_weight_mm3")),
                  "Native signed Gauss tensors must retain complete element/point/order identity")
            actual.add((index, point))
        gauss_count += len(actual)
        bodies.append({"component_id": component, "node_count": len(body["nodes"]), "element_count": len(topology["volume_cell_indices"]),
                       "boundary_face_count": len(topology["face_cell_indices"]), "gauss_count": len(actual),
                       "qualified_mesh_volume_mm3": body["qualified_mesh_volume_mm3"], "native_energy": deepcopy(body["native_energy"])})
    _need(seen == set(source["nodes"]) and maximum_error <= comparison["maximum_coordinate_error_mm"],
          "Complete node coverage/native import coordinate observation differs")
    checks = raw["geometry_checks"]
    _need(_keys(checks, {"maximum_coordinate_error_mm", "coordinate_absolute_limit_mm", "maximum_point_weight_relative_error", "point_weight_relative_limit"})
          and checks["coordinate_absolute_limit_mm"] == COORDINATE_ABSOLUTE_MM and checks["point_weight_relative_limit"] == 1e-8
          and _finite(checks["maximum_coordinate_error_mm"]) and 0 <= checks["maximum_coordinate_error_mm"] <= COORDINATE_ABSOLUTE_MM
          and _finite(checks["maximum_point_weight_relative_error"]) and 0 <= checks["maximum_point_weight_relative_error"] <= 1e-8,
          "Original native geometry checks/limits are missing or changed")
    return source, sorted(nodes, key=lambda row: row["node_id"]), elements, faces, cells, bodies, gauss_count


def _triangles(source, nodes, faces, cells, comparison):
    positions = {row["node_id"]: row["position_mm"] for row in nodes}
    node_ids = comparison["source_node_ids_by_native_index"]
    cell_ids = comparison["source_element_ids_by_native_index"]
    owners = {}
    for cell in cells:
        if cell["type"] == "TETRA10":
            conn = [node_ids[i] for i in cell["node_indices"]]
            for corners, _ in _FACES:
                key = tuple(sorted(conn[i] for i in corners))
                opposite = next(conn[i] for i in range(4) if i not in corners)
                owners.setdefault(key, []).append((cell_ids[cell["index"]], opposite))
    output = []
    for face in faces:
        conn = face["node_ids"]
        owner = owners[tuple(sorted(conn[:3]))]
        _need(len(owner) == 1, "Display face lacks one original adjacent tetrahedron")
        eid, opposite = owner[0]
        for slots in _SUBTRIANGLES:
            triangle = [conn[i] for i in slots]
            a, b, c, d = [positions[i] for i in (*triangle, opposite)]
            u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
            cross = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
            direction = math.fsum(cross[i] * (d[i] - a[i]) for i in range(3))
            _need(_finite(direction) and direction != 0, "Degenerate/nonrepresentable linear display triangle orientation")
            if direction > 0:
                triangle[1], triangle[2] = triangle[2], triangle[1]
            output.append({"node_ids": triangle, "face_id": face["element_id"], "component_id": face["component_id"], "owner_element_id": eid})
    return output


def _prepare(result, proposal, raw, artifact, mapping, mapping_artifact):
    details, pins = _context(result, proposal, artifact, mapping_artifact)
    source, nodes, elements, faces, cells, bodies, gauss_count = _geometry(raw, mapping)
    _need(_same(raw["geometry_checks"], details["geometry_checks"]) and details["axis_semantics"] == AXIS
          and _same(details["actual_load_parameters"], raw["actual_load_parameters"])
          and _same(proposal["execution"]["solver_policy"]["load_parameters"], [0., .25, .5, .75, 1.]),
          "Original observed static increments/geometry checks differ from the recorded producer")
    selected = proposal["execution"]["catalog"]["selections"]
    _need(type(selected) is list and all(type(row) is dict and _id(row["id"]) for row in selected)
          and len({row["id"] for row in selected}) == len(selected), "Unique retained CAD catalog aliases are required")
    body_ids = {row["component_id"] for row in selected if row["kind"] == "native_assembly_body" and row["component_id"] in ACTIVE}
    native_faces = [(row["component_id"], row["catalog_face_id"]) for row in selected
                    if row["kind"] == "native_assembly_face" and row["component_id"] in ACTIVE]
    mapped_faces = {(group["component_id"], group["catalog_face_id"]) for group in source["groups"].values() if group["dim"] == 2}
    _need(body_ids == set(ACTIVE) and len(native_faces) == len(set(native_faces)) and set(native_faces) == mapped_faces,
          "Complete original CAD body/face identities differ from retained mapping groups")
    peak = max(math.hypot(*node["displacement_mm"]) for node in nodes)
    metric = result["metrics"]["max_displacement"]
    _need(metric["valid"] is True and metric["unit"] == "mm" and _finite(metric["value"])
          and abs(metric["value"] - peak) <= 8 * sys.float_info.epsilon * max(peak, abs(metric["value"]), math.ulp(0.0)),
          "Assembly whole-field vector-magnitude metric differs from the retained native nodal vectors")
    stress = result["metrics"]["peak_stress"]
    _need(stress["valid"] is False and stress["value"] is None and stress["unit"] == "MPa",
          "Retained native Gauss tensors cannot acquire a valid nodal/strength metric")
    return source, nodes, elements, faces, cells, bodies, gauss_count, pins


def display_field(result, proposal, raw, artifact, mapping, mapping_artifact):
    """Build display arrays from verified original JSON; never create an artifact."""
    try:
        source, nodes, elements, faces, cells, bodies, gauss_count, pins = _prepare(result, proposal, raw, artifact, mapping, mapping_artifact)
        output = {"schema_version": "1.0", "kind": "assembly_mechanics_nodal_displacement_display",
            "scope": "BOUNDED_COMPLETE_NATIVE_ASSEMBLY_DISPLAY", "source_scope": raw["scope"], "backend": BACKEND,
            "adapter_version": "1", "experiment_id": result["experiment_id"], "parent_experiment_id": result["parent_experiment_id"],
            "cad_revision": result["cad_revision"], "mesh_revision": proposal["execution"]["mesh"]["mesh_revision"],
            "proposal_revision": result["proposal_revision"], "position_unit": "mm", "displacement_unit": "mm", "force_unit": "N",
            "coordinate_frame": raw["coordinate_frame"], "coverage": "ALL_ORIGINAL_MESH_NODES", "static": {
                "order": raw["order"], "load_parameter": raw["load_parameter"], "axis_semantics": AXIS},
            "available_orders": deepcopy(raw["available_orders"]), "actual_load_parameters": deepcopy(raw["actual_load_parameters"]),
            "initial_state": raw["initial_state"],
            "node_count": len(nodes), "element_count": len(elements), "boundary_face_count": len(faces),
            "nodes": nodes, "source_nodes": deepcopy(mapping["nodes"]), "elements": elements, "boundary_faces": faces,
            "display_triangles": _triangles(source, nodes, faces, cells, raw["native_import_comparison"]), "bodies": bodies,
            "source_artifacts": pins, "identity": deepcopy(raw["native_import_comparison"]), "geometry_checks": deepcopy(raw["geometry_checks"]),
            "connectivity_basis": "ORIGINAL_RETAINED_GMSH_ORDER_WITH_NATIVE_IMPORT_PERMUTATION_RECORDED_SEPARATELY",
            "display_geometry": "FOUR_LINEAR_TRIANGLES_PER_TRIA6_WITH_DERIVED_OUTWARD_WINDING",
            "native_gauss": {"artifact": FIELD_PATH, "sha256": artifact["sha256"], "point_count": gauss_count,
                             "location": "NATIVE_TETRA10_FPG5_GAUSS_POINTS", "nodal_stress": "NOT_CONSTRUCTED", "displayed": False},
            "metrics": deepcopy(result["metrics"]), "validations": deepcopy(result["validations"]),
            "qualification": "UNKNOWN", "engineering_valid": False, "decision": "NOT_RELEASED",
            "display_limits": dict(DISPLAY_LIMITS), "limitations": list(_LIMITATIONS)}
        _need(len(json.dumps(output, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")) <= DISPLAY_LIMITS["bytes"],
              "Complete assembly display JSON exceeds the 64 MiB presentation resource envelope; no data is truncated")
        return output
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as exc:
        raise ValueError("Malformed or incomplete retained assembly display contract") from exc


def select_field_response(result, proposal, raw, artifact, selection, *, mapping, mapping_artifact):
    """Select one exact original source ID, never a nearest/coincident coordinate."""
    try:
        _need(_keys(selection, {"artifact", "sha256", "cad_revision", "node_id", "component"})
              and selection["artifact"] == FIELD_PATH and _sha(selection["sha256"]) and _sha(selection["cad_revision"])
              and selection["sha256"] == artifact["sha256"] and selection["cad_revision"] == result["cad_revision"]
              and _integer(selection["node_id"]) and selection["component"] in COMPONENTS,
              "Select the exact admitted artifact/hash/CAD revision, positive source node ID and displacement component")
        _, nodes, *_ = _prepare(result, proposal, raw, artifact, mapping, mapping_artifact)
        selected = next((node for node in nodes if node["node_id"] == selection["node_id"]), None)
        _need(selected is not None, "The selected original source node does not exist in this retained mesh")
        component = selection["component"]
        value = math.hypot(*selected["displacement_mm"]) if component == "MAGNITUDE" else selected["displacement_mm"][COMPONENTS.index(component)]
        return {"value": value, "unit": "mm", "source_field": {
            **deepcopy(selection), "mesh_revision": proposal["execution"]["mesh"]["mesh_revision"],
            "mapping_artifact": MAPPING_PATH, "mapping_sha256": mapping_artifact["sha256"],
            "component_id": selected["component_id"], "native_index": selected["native_index"], "quantity": "DISPLACEMENT",
            "position_mm": deepcopy(selected["position_mm"]), "position_unit": "mm", "coordinate_frame": raw["coordinate_frame"],
            "value_origin": "DERIVED_MAGNITUDE" if component == "MAGNITUDE" else "NATIVE_COMPONENT",
            "static": {"order": raw["order"], "load_parameter": raw["load_parameter"], "axis_semantics": AXIS},
            "coverage": "ALL_ORIGINAL_MESH_NODES"}, "qualification": "UNKNOWN", "alignment": "USER_DECLARED_UNVERIFIED"}
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as exc:
        raise ValueError("Malformed or incomplete retained assembly selection contract") from exc


class AssemblyResponseFieldsAdapter:
    """Read-only adapter registry entry; it cannot admit or execute a solver."""

    backend = BACKEND

    @staticmethod
    def research_metric_semantics(result):
        provenance = result.get('provenance', {})
        maximum = result.get('metrics', {}).get('max_displacement', {})
        if (provenance.get('adapter') != BACKEND or provenance.get('adapter_version') != '1'
                or maximum.get('unit') != 'mm' or maximum.get('valid') is not True):
            return None
        return {'max_displacement': {'quantity': 'displacement', 'component': 'VECTOR_MAGNITUDE',
            'selection_id': 'ALL_ORIGINAL_ACTIVE_BODY_NODES', 'reduction': 'MAX_MAGNITUDE',
            'unit': 'mm', 'coordinate_frame': 'global_assembly_cartesian_mm',
            'coverage': 'ALL_ORIGINAL_MESH_NODES',
            'description': '원본 조립체 전체 메시 절점의 변위 벡터 크기 최대값; 하중부 |UZ|가 아님'}}

    @staticmethod
    def field_response_resources(result):
        _need(type(result) is dict and type(result.get("provenance")) is dict
              and result["provenance"].get("adapter") == BACKEND and result["provenance"].get("adapter_version") == "1",
              "Unsupported assembly result reader producer")
        return {"field": {"path": FIELD_PATH, "maximum_bytes": SOURCE_LIMITS["field"]},
                "mapping": {"path": MAPPING_PATH, "maximum_bytes": SOURCE_LIMITS["mapping"]}}

    @staticmethod
    def _resources(resources):
        _need(_keys(resources, {"field", "mapping"}) and all(type(value) is tuple and len(value) == 2 for value in resources.values()),
              "Assembly response resources require exact field/mapping (JSON, manifest entry) tuples")
        return (*resources["field"], *resources["mapping"])

    @staticmethod
    def display_response_fields(result, proposal, resources):
        raw, artifact, mapping, mapping_artifact = AssemblyResponseFieldsAdapter._resources(resources)
        return display_field(result, proposal, raw, artifact, mapping, mapping_artifact)

    @staticmethod
    def select_response_fields(result, proposal, resources, selection):
        raw, artifact, mapping, mapping_artifact = AssemblyResponseFieldsAdapter._resources(resources)
        return select_field_response(result, proposal, raw, artifact, selection, mapping=mapping, mapping_artifact=mapping_artifact)
