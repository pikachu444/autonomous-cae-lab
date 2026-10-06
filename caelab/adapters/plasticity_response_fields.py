"""Pure exact-point and bounded history readers for retained native J2 fields.

Core supplies manifest-verified JSON and rechecks the immutable source. This
module performs no file, process, solver or API operations. Historical producer
v1/five-source records and current v1.2/seven-source records stay distinct.
"""

from copy import deepcopy
import hashlib
import json
import math

from plugins.elasticity import plasticity_reference as domain
from . import codeaster_plasticity_worker as worker
from . import codeaster_worker as mesh_worker
from .structural_response_fields import _need, _finite, _integer, _sha, _keys, _same, _path


BACKEND = "structural.code_aster.plasticity"
FRAME = "global Cartesian model; sensor/world alignment UNKNOWN"
JSON_LIMIT = 64 * 1024 * 1024
INPUT_LIMIT = 1024 * 1024
NODE_LIMIT, ELEMENT_LIMIT = 200000, 500000
_BASE = {"input": "simulation/input.json", "outcome": "simulation/analysis_raw.json"}
_SOURCE5 = {"domain_reference.py", "mesh_runtime_adapter.py", "codeaster_worker.py",
            "codeaster_plasticity_worker.py", "plasticity_adapter.py"}
_SOURCES = {"1": _SOURCE5, "1.2": _SOURCE5 | {"codeaster_execution.py", "execution_control.py"}}
_UNITS = {"time": "s", "strain": "1", "displacement": "mm", "stress": "MPa", "reaction": "N"}
_OCI = "d8d19ea91989eac0d38195bc5795c54c69f530f7196f53d67697ffa57c9106d5"
NODAL_COMPONENTS = tuple(f"{field}.{component}" for field in ("DEPL", "REAC_NODA")
                         for component in worker.VECTOR_COMPONENTS)
GAUSS_COMPONENTS = tuple("SIEF_ELGA." + component for component in worker.STRESS_COMPONENTS) + ("VARI_ELGA.V1",)
_COMMON_SELECTOR = {"kind", "artifact", "sha256", "model_revision", "mesh_index", "time_index", "component"}
_RECORD_KEYS = {"mesh_size_mm", "node_ids", "coordinates_mm", "element_count", "states",
                "group_node_ids", "reaction_method", "stress_component_order", "nonlinear_convergence"}
_STATE_KEYS = {"time_s", "actual_result_order", "displacements_mm", "stresses_mpa", "eq_plastic_strain",
               "plastic_indicator", "reaction_n", "drive_reaction_x_n", "nodal_reactions_n",
               "stress_point_coordinates_mm", "stress_identifiers", "native_boundary_resultants_n"}
_RAW_KEYS = {"schema_version", "solver_status", "converged", "available_orders", "access_parameters", "states", "mesh",
             "versions", "code_aster_runtime", "numerical_libraries", "input_sha256", "mesh_input_sha256", "native_mesh_checks",
             "native_material", "nonlinear_policy", "convergence_evidence", "measured_linear_residual"}
LIMITATIONS = [
    "Exact native node or BODY TETRA10 five-point Gauss sample on one recorded mesh; no interpolation, extrapolation or Gauss-to-node stress.",
    "Seconds label the declared quasi-static loading history; inertia, rate dependence and world/sensor alignment are not inferred.",
    "History uses only the finest declared mesh. Gauss means are UNWEIGHTED arithmetic means, never volume averages or native point values.",
    "The initial state has no new Newton increment. Original Domain verdicts and invalid metrics remain unchanged; physical UNKNOWN/NOT_RELEASED.",
    "The display catalog uses retained assessment metadata; exact selections and histories reparse the selected mesh's native tables.",
    "Original source TETRA10 topology and the recorded pre-model native import guard are bound; native connectivity is not re-exported or reconstructed.",
    "Seven bounded JSON resources maximum; large retained analysis/raw histories are read again on selection, without a persistent reader cache.",
]


def _call(function, *args):
    try:
        return function(*args)
    except (KeyError, IndexError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
        raise ValueError("Incomplete retained Code_Aster J2 field/history contract") from exc


def _json_tree(value, depth=0, active=None):
    _need(depth <= 64, "J2 JSON nesting exceeds the reader bound")
    if type(value) in (int, float):
        _need(_finite(value), "Nonfinite J2 JSON number")
    elif type(value) in (dict, list):
        active = set() if active is None else active
        _need(id(value) not in active, "Cyclic J2 resource")
        active.add(id(value))
        if type(value) is dict:
            _need(all(type(key) is str for key in value), "J2 JSON keys must be strings")
        for item in value.values() if type(value) is dict else value:
            _json_tree(item, depth + 1, active)
        active.remove(id(value))
    else:
        _need(value is None or type(value) in (str, bool), "Non-JSON J2 resource")


def _manifest(result):
    _need(type(result) is dict and type(result.get("provenance")) is dict, "J2 provenance is required")
    p = result["provenance"]
    _need(p.get("adapter") == BACKEND and p.get("adapter_version") in _SOURCES,
          "Unsupported retained J2 field producer")
    _need(_sha(result.get("model_revision")) and _sha(result.get("proposal_revision")) and
          p.get("proposal_sha256") == result["proposal_revision"], "J2 model/proposal revisions differ")
    _need(type(result.get("artifacts")) is list, "J2 artifact manifest is required")
    manifest, folded = {}, set()
    for entry in result["artifacts"]:
        _need(type(entry) is dict and _path(entry.get("path")) and _sha(entry.get("sha256")) and
              _integer(entry.get("size_bytes"), positive=False) and entry.get("revision") == result["proposal_revision"],
              "J2 artifact identity/size/proposal revision differs")
        path = entry["path"]
        _need(path.casefold() not in folded, "Duplicate/aliased J2 artifact path")
        folded.add(path.casefold())
        manifest[path] = entry
    return manifest


def _entry(manifest, path, bound=None):
    _need(path in manifest and manifest[path]["size_bytes"] > 0 and
          (bound is None or manifest[path]["size_bytes"] <= bound), "Missing/oversized retained J2 artifact: " + path)
    return manifest[path]


def _resource(resources, role, manifest, path, bound=JSON_LIMIT):
    item = resources.get(role)
    _need(type(item) is tuple and len(item) == 2, "J2 resources require (JSON, manifest entry) tuples")
    raw, entry = item
    _need(type(raw) is dict and _same(entry, _entry(manifest, path, bound)),
          "J2 resource differs from its bounded manifest entry")
    _json_tree(raw)
    return raw, entry


def _vector(values, count, label):
    _need(type(values) is list and len(values) == count and all(_finite(value) for value in values),
          "J2 finite exact vector required: " + label)
    return values


def _table(values, rows, columns, label):
    _need(type(values) is list and len(values) == rows, "J2 complete table required: " + label)
    for row in values:
        _vector(row, columns, label)


def _ids(values, *, positive=True, label="identifiers"):
    _need(type(values) is list and values and all(_integer(v, positive=positive) for v in values) and
          len(set(values)) == len(values), "J2 exact unique integer " + label + " required")
    return set(values)


def _level_policy(index):
    prefix = f"simulation/level_{index}/"
    return {role: {"path": prefix + name, "maximum_bytes": bound} for role, name, bound in (
        ("level_input", "input.json", INPUT_LIMIT), ("native", "worker_result.json", JSON_LIMIT),
        ("parsed", "parsed_history.json", JSON_LIMIT), ("expected_mesh", "expected_mesh.json", JSON_LIMIT),
        ("mesh_catalog", "mesh_catalog.json", JSON_LIMIT))}


def _headers(result, proposal, resources):
    manifest = _manifest(result)
    _need(type(resources) is dict and set(_BASE) <= set(resources) and len(resources) <= 7,
          "J2 reader needs two headers and at most five selected-mesh resources")
    settings, input_entry = _resource(resources, "input", manifest, _BASE["input"], INPUT_LIMIT)
    outcome, _ = _resource(resources, "outcome", manifest, _BASE["outcome"])
    p, detail = result["provenance"], result["provenance"].get("adapter_details")
    _need(result.get("status") in ("COMPLETED_REVIEW_REQUIRED", "REJECTED") and result.get("decision") == "NOT_RELEASED" and
          result.get("solver_status") == "COMPLETED" and result.get("converged") is True and result.get("cad_revision") is None,
          "J2 result has no completed retained native history")
    _need(_same(settings, p.get("execution_settings")) and _same(domain.validate_settings(settings), settings),
          "J2 input differs from the normalized immutable execution settings")
    if proposal is not None:
        _need(type(proposal) is dict and proposal.get("id") == result.get("experiment_id") and
              type(result.get("experiment_id")) is str and result["experiment_id"] and
              proposal.get("study_id") == result.get("study", {}).get("id") and
              proposal.get("model_revision") == result["model_revision"] and proposal.get("cad_revision") is None and
              proposal.get("physics", {}).get("backend") == BACKEND and _same(proposal.get("execution"), settings),
              "J2 proposal/result/study/model identity differs")
        model = proposal.get("model", {})
        expected_mesh = {"sizes_mm": settings["mesh_sizes_mm"], "order": 2, "element_type": "TETRA10"}
        if settings.get("mode") == "selected_mesh":
            expected_mesh["mode"] = "selected_mesh"
        _need(_same(model.get("geometry"), {"type": "block", "dimensions_mm": settings["dimensions_mm"],
              "unit": "mm", "origin": [0., 0., 0.]}) and _same(model.get("mesh"), expected_mesh) and
              _same(model.get("materials"), domain.model_declaration(settings)["materials"]),
              "J2 model geometry/material/unit/mesh differs from the saved request")
    _need(type(detail) is dict and detail.get("adapter") == BACKEND and detail.get("adapter_version") == p["adapter_version"] and
          detail.get("input_sha256") == input_entry["sha256"] and _same(detail.get("nonlinear_policy"), worker.NONLINEAR_POLICY) and
          detail.get("oci_manifest_sha256") == _OCI and detail.get("measured_linear_residual") is None and
          detail.get("reused_native_guard") == "caelab.adapters.codeaster_worker.validate_native_mesh",
          "J2 source input/producer/native policy differs")
    sources = detail.get("captured_source_sha256")
    _need(_keys(sources, _SOURCES[p["adapter_version"]]), "J2 captured source membership differs for the original producer version")
    for name, digest in sources.items():
        _need(_sha(digest) and _entry(manifest, "simulation/" + name)["sha256"] == digest,
              "J2 copied source is not exactly manifested")
    plugin = detail.get("domain_plugin")
    _need(type(plugin) is dict and plugin.get("module") == "plugins.elasticity.plasticity_reference" and
          plugin.get("version") == "1" and plugin.get("source_artifact") == "simulation/domain_reference.py" and
          plugin.get("source_sha256") == sources["domain_reference.py"], "J2 Domain source identity differs")
    selected = settings.get("mode") == "selected_mesh"
    if selected:
        _need(p["adapter_version"] == "1.2" and outcome.get("mode") == detail.get("mode") == "selected_mesh" and
              outcome.get("scope") == detail.get("scope") == domain.SELECTED_SCOPE and
              _same(outcome.get("input_provenance"), settings["input_provenance"]) and
              _same(detail.get("input_provenance"), settings["input_provenance"]) and
              _same(detail.get("units"), _UNITS) and _same(detail.get("declared_limits"), settings["limits"]),
              "Selected J2 scope/source/units/limits differ")
    else:
        _need("mode" not in outcome and "mode" not in detail and "input_provenance" not in detail,
              "Historical benchmark must not be relabeled as selected J2 execution")
    _need(outcome.get("status") == ("REJECTED" if result["status"] == "REJECTED" else "COMPLETED") and
          outcome.get("solver_status") == "COMPLETED" and outcome.get("converged") is True and
          _same(outcome.get("provenance"), detail) and _same(outcome.get("metrics"), result.get("metrics")) and
          outcome.get("raw_result") == _BASE["outcome"] and type(outcome.get("checks")) is list and outcome["checks"] and
          all(type(check) is dict and check.get("status") in ("PASS", "FAIL") for check in outcome["checks"]),
          "J2 retained assessment/status/metrics do not match the original result")
    _need(any(check["status"] == "FAIL" for check in outcome["checks"]) == (outcome["status"] == "REJECTED"),
          "J2 original numerical classification disagrees with its recorded checks")
    records = outcome.get("mesh_records")
    _need(type(records) is list and len(records) == len(settings["mesh_sizes_mm"]), "J2 declared meshes must be completely retained")
    expected_meshes = [f"simulation/level_{i}/mesh.msh" for i in range(len(records))]
    _need(detail.get("mesh") == expected_meshes and detail.get("native_fields") ==
          [f"simulation/level_{i}/results.med" for i in range(len(records))], "J2 retained mesh/MED level paths differ")
    for i, record in enumerate(records):
        _record(record, settings["mesh_sizes_mm"][i], settings["history"]["times_s"], settings["dimensions_mm"])
        for spec in _level_policy(i).values():
            _entry(manifest, spec["path"], spec["maximum_bytes"])
        _entry(manifest, expected_meshes[i])
        _entry(manifest, f"simulation/level_{i}/results.med")
    return {"manifest": manifest, "settings": settings, "outcome": outcome, "detail": detail, "records": records}


def _record(record, size, times, dimensions):
    _need(_keys(record, _RECORD_KEYS) and _finite(record["mesh_size_mm"]) and record["mesh_size_mm"] == size and
          _integer(record["element_count"]) and record["element_count"] <= ELEMENT_LIMIT and
          record["stress_component_order"] == ["xx", "yy", "zz", "xy", "xz", "yz"], "J2 retained mesh/component metadata differs")
    ids = record["node_ids"]
    nodes = _ids(ids, label="node IDs")
    _need(4 <= len(ids) <= NODE_LIMIT and ids == sorted(ids) and nodes == set(range(1, len(ids) + 1)),
          "J2 node IDs must be the complete actual decimal native indices")
    _table(record["coordinates_mm"], len(ids), 3, "native coordinates")
    tolerance = 1e-12 * max(1., *dimensions)
    for position in record["coordinates_mm"]:
        _need(all(-tolerance <= value <= span + tolerance for value, span in zip(position, dimensions)),
              "J2 native node position lies outside the original declared block")
    groups = record["group_node_ids"]
    _need(_keys(groups, {"X0", "XL", "Y0", "Z0"}), "J2 boundary group coverage differs")
    for values in groups.values():
        _need(_ids(values, label="boundary nodes") <= nodes, "Foreign J2 boundary node")
    states = record["states"]
    _need(type(states) is list and len(states) == len(times) and type(record["reaction_method"]) is str and
          record["reaction_method"] == "Component-specific constrained DOFs: X0.DX/Y0.DY/Z0.DZ; drive XL.DX recorded separately",
          "J2 time/reaction semantics differ")
    points, orders, previous_ids, previous_coordinates = 5 * record["element_count"], [], None, None
    for i, (state, time) in enumerate(zip(states, times)):
        _need(_keys(state, _STATE_KEYS) and _finite(state["time_s"]) and state["time_s"] == time and
              _integer(state["actual_result_order"], positive=False), "J2 actual time/order differs")
        order = state["actual_result_order"]
        orders.append(order)
        for name in ("displacements_mm", "nodal_reactions_n"):
            _table(state[name], len(ids), 3, name)
        _table(state["stresses_mpa"], points, 6, "SIEF_ELGA")
        _table(state["stress_point_coordinates_mm"], points, 3, "Gauss coordinates")
        for name in ("eq_plastic_strain", "plastic_indicator"):
            _vector(state[name], points, name)
        _vector(state["reaction_n"], 3, "support reactions")
        _need(_finite(state["drive_reaction_x_n"]) and _keys(state["native_boundary_resultants_n"], groups),
              "J2 native boundary resultant coverage differs")
        for values in state["native_boundary_resultants_n"].values():
            _vector(values, 3, "native boundary resultant")
        identifiers = state["stress_identifiers"]
        _need(type(identifiers) is list and len(identifiers) == points, "J2 complete Gauss identity required")
        keys = []
        for point in identifiers:
            _need(_keys(point, {"element_id", "point", "subpoint", "order"}) and
                  _integer(point["element_id"]) and type(point["point"]) is int and point["point"] in (1, 2, 3, 4, 5) and
                  type(point["subpoint"]) is int and point["subpoint"] == 1 and
                  type(point["order"]) is int and point["order"] == order, "J2 element/point/subpoint/order identity differs")
            keys.append((point["element_id"], point["point"], point["subpoint"]))
        bodies = {key[0] for key in keys}
        _need(keys == sorted(keys) and len(set(keys)) == points and len(bodies) == record["element_count"] and
              set(keys) == {(body, point, 1) for body in bodies for point in (1, 2, 3, 4, 5)} and
              (previous_ids is None or keys == previous_ids) and
              (previous_coordinates is None or _same(state["stress_point_coordinates_mm"], previous_coordinates)),
              "J2 all-five-point/body coverage or geometry changed across times")
        previous_ids, previous_coordinates = keys, state["stress_point_coordinates_mm"]
        for position in state["stress_point_coordinates_mm"] if i == 0 else []:
            _need(all(-tolerance <= value <= span + tolerance for value, span in zip(position, dimensions)),
                  "J2 Gauss position lies outside the original declared block")
    _need(len(set(orders)) == len(orders), "Duplicate J2 native stored result order")
    convergence = record["nonlinear_convergence"]
    _need(type(convergence) is dict and convergence.get("status") in ("PASS", "FAIL") and
          _same(convergence.get("native_limits"), worker.NONLINEAR_POLICY) and
          _same(convergence.get("initial_state"), {"time_s": times[0], "status": "INITIAL_STATE_NO_NEWTON_INCREMENT"}) and
          type(convergence.get("increments")) is list and len(convergence["increments"]) == len(times) - 1 and
          all(_finite(row.get("time_s")) and row["time_s"] == time for row, time in zip(convergence["increments"], times[1:])),
          "J2 original nonlinear history/initial qualification differs")
    return record


def _selector(ctx, selection):
    _need(type(selection) is dict and selection.get("kind") in ("fe_nodal", "fe_gauss"), "Select a native J2 node or Gauss point")
    nodal = selection["kind"] == "fe_nodal"
    _need(_keys(selection, _COMMON_SELECTOR | ({"node_id"} if nodal else {"element_id", "point", "subpoint"})) and
          _integer(selection["mesh_index"], positive=False) and selection["mesh_index"] < len(ctx["records"]) and
          _integer(selection["time_index"], positive=False) and selection["time_index"] < len(ctx["settings"]["history"]["times_s"]) and
          selection["component"] in (NODAL_COMPONENTS if nodal else GAUSS_COMPONENTS), "J2 exact selector keys/index/component differ")
    index = selection["mesh_index"]
    path = f"simulation/level_{index}/parsed_history.json"
    entry = _entry(ctx["manifest"], path, JSON_LIMIT)
    _need(selection["artifact"] == path and _sha(selection["sha256"]) and selection["sha256"] == entry["sha256"] and
          selection["model_revision"] == ctx["result"]["model_revision"], "J2 selected artifact/hash/model revision differs")
    if nodal:
        _need(_integer(selection["node_id"]) and selection["node_id"] in ctx["records"][index]["node_ids"], "Unknown J2 native node")
    else:
        _need(_integer(selection["element_id"]) and type(selection["point"]) is int and selection["point"] in (1, 2, 3, 4, 5) and
              type(selection["subpoint"]) is int and selection["subpoint"] == 1, "Unknown J2 Gauss identity")
        _need(any(point["element_id"] == selection["element_id"] for point in ctx["records"][index]["states"][0]["stress_identifiers"]),
              "J2 selected element is not an actual recorded BODY cell")
    return index


def _native_tables(ctx, raw, index):
    # The pinned worker's _save contract is sorted indent-2 JSON plus LF. Bind
    # embedded raw tables to all their separately retained native table files
    # without adding one resource per table or opening those files here.
    names = {"DEPL", "REAC_NODA", "SIEF_ELGA", "VARI_ELGA", "BOUNDARY_RESULTANTS"}
    for state in raw["states"]:
        _need(_keys(state["tables"], names), "J2 native table set differs")
        for name, table in state["tables"].items():
            payload = (json.dumps(table, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
            path = f"simulation/level_{index}/order_{state['order']}_{name.lower()}.table.json"
            entry = _entry(ctx["manifest"], path)
            _need(entry["size_bytes"] == len(payload) and entry["sha256"] == hashlib.sha256(payload).hexdigest(),
                  "J2 raw table differs from the separately manifested native table bytes")


def _mesh_binding(expected, catalog, guard, dimensions):
    _need(_keys(expected, {"schema_version", "source_format", "node_ids", "coordinates_mm", "tetrahedra",
          "group_node_ids", "total_cell_count", "physical_groups", "importer_policy"}) and expected["schema_version"] == "1" and
          expected["source_format"] == "GMSH2.2" and _integer(expected["total_cell_count"]) and
          _same(expected["physical_groups"], {"BODY": {"dimension": 3, "tag": 1001}, "X0": {"dimension": 2, "tag": 1002},
          "XL": {"dimension": 2, "tag": 1003}, "Y0": {"dimension": 2, "tag": 1004}, "Z0": {"dimension": 2, "tag": 1005}}),
          "J2 expected original mesh format/physical groups differ")
    source_ids = expected["node_ids"]
    source_set = _ids(source_ids, label="original source nodes")
    _need(4 <= len(source_ids) <= NODE_LIMIT and source_ids == sorted(source_ids), "J2 source node order/count differs")
    _table(expected["coordinates_mm"], len(source_ids), 3, "original mesh coordinates")
    _need(_same(guard.get("coordinate_tolerances"), {"relative": 1e-12, "absolute": 1e-12}) and
          guard.get("status") == "PASS" and guard.get("support_union_verified") is True and
          _finite(guard.get("minimum_native_jacobian_mm3")) and guard["minimum_native_jacobian_mm3"] > 0 and
          type(guard.get("node_count")) is int and guard["node_count"] == len(source_ids) and
          type(guard.get("total_cell_count")) is int and guard["total_cell_count"] == expected["total_cell_count"],
          "J2 recorded pre-model native mesh guard is incomplete")
    coordinates, body, groups = worker._catalog(catalog)
    _need(set(coordinates) == set(range(1, len(source_ids) + 1)), "J2 native decimal node IDs are incomplete")
    source_by_native = guard.get("source_node_ids_by_native_index")
    _need(_ids(source_by_native, label="native/source map") == source_set and len(source_by_native) == len(source_ids),
          "J2 native/source node bijection differs")
    actual_coordinates = [coordinates[node] for node in range(1, len(source_ids) + 1)]
    mapping = mesh_worker.coordinate_bijection(actual_coordinates, expected["coordinates_mm"])
    _need(mapping is not None and [source_ids[row] for row in mapping] == source_by_native,
          "J2 original/native geometry differs from the retained import mapping")
    tets = expected["tetrahedra"]
    _need(type(tets) is list and 0 < len(tets) <= ELEMENT_LIMIT and len(tets) == len(body) and
          type(guard.get("volume_element_count")) is int and guard["volume_element_count"] == len(body),
          "J2 original/native BODY count differs")
    tet_ids, corner_sets, used_nodes = set(), set(), set()
    for tet in tets:
        _need(_keys(tet, {"element_id", "node_ids"}) and _integer(tet["element_id"]) and tet["element_id"] not in tet_ids and
              len(tet["node_ids"]) == 10 and _ids(tet["node_ids"], label="TETRA10 connectivity") <= source_set,
              "J2 original TETRA10 connectivity differs")
        corners = tuple(sorted(tet["node_ids"][:4]))
        _need(corners not in corner_sets, "Duplicate original J2 BODY corners")
        tet_ids.add(tet["element_id"])
        corner_sets.add(corners)
        used_nodes.update(tet["node_ids"])
    _need(used_nodes == source_set, "J2 original mesh has unreferenced nodes")
    element_mapping = guard.get("source_element_mapping")
    _need(type(element_mapping) is list and len(element_mapping) == len(tets), "J2 retained BODY/source map is incomplete")
    native_cells, mapped_sources = [], []
    for item in element_mapping:
        _need(_keys(item, {"native_cell_index", "source_element_id"}) and
              _integer(item["native_cell_index"], positive=False) and item["native_cell_index"] < expected["total_cell_count"] and
              _integer(item["source_element_id"]), "J2 native BODY/source mapping row differs")
        native_cells.append(item["native_cell_index"] + 1)
        mapped_sources.append(item["source_element_id"])
    _need(len(set(native_cells)) == len(body) and set(native_cells) == body and
          len(set(mapped_sources)) == len(tets) and set(mapped_sources) == tet_ids,
          "J2 actual BODY identifiers differ from original source element mapping")
    source_groups, native_groups = expected["group_node_ids"], guard.get("native_group_node_indices")
    _need(_keys(source_groups, groups) and _keys(native_groups, groups), "J2 native/source boundary membership differs")
    for name in groups:
        source_nodes = _ids(source_groups[name], label="original boundary nodes")
        indexes = native_groups[name]
        native = _ids(indexes, positive=False, label="original native group indices")
        _need(source_nodes <= source_set and all(index < len(source_ids) for index in indexes) and
              {index + 1 for index in native} == set(groups[name]) and
              {source_by_native[index] for index in native} == source_nodes,
              "J2 original/native boundary group differs: " + name)
    return {"expected_mesh_binding": "RECORDED_PRE_MODEL_NATIVE_IMPORT_GUARD",
            "native_connectivity": "NOT_REEXPORTED", "native_body_ids": sorted(body)}


def _level(ctx, resources, index):
    policy = _level_policy(index)
    _need(set(resources) == set(_BASE) | set(policy), "J2 selected mesh resource roles differ")
    read = {role: _resource(resources, role, ctx["manifest"], spec["path"], spec["maximum_bytes"])
            for role, spec in policy.items()}
    config, config_entry = read["level_input"]
    raw, raw_entry = read["native"]
    parsed, parsed_entry = read["parsed"]
    expected, expected_entry = read["expected_mesh"]
    catalog, _ = read["mesh_catalog"]
    _need(_keys(raw, _RAW_KEYS | ({"mode", "input_provenance"} if ctx["settings"].get("mode") == "selected_mesh" else set())),
          "J2 native worker envelope contains unsupported metadata/unit/frame declarations")
    size = ctx["settings"]["mesh_sizes_mm"][index]
    mesh_entry = _entry(ctx["manifest"], f"simulation/level_{index}/mesh.msh")
    _need(_keys(config, {"settings", "mesh_size_mm", "mesh_sha256", "expected_mesh_sha256"}) and
          _same(config["settings"], ctx["settings"]) and _finite(config["mesh_size_mm"]) and config["mesh_size_mm"] == size and
          config["mesh_sha256"] == mesh_entry["sha256"] and config["expected_mesh_sha256"] == expected_entry["sha256"] and
          raw.get("input_sha256") == config_entry["sha256"] and raw.get("mesh_input_sha256") == mesh_entry["sha256"] and
          _same(raw.get("mesh"), catalog) and _same(raw.get("nonlinear_policy"), worker.NONLINEAR_POLICY),
          "J2 level request/native/mesh artifact identity differs")
    if ctx["settings"].get("mode") == "selected_mesh":
        _need(raw.get("mode") == "selected_mesh" and _same(raw.get("input_provenance"), ctx["settings"]["input_provenance"]),
              "J2 native selected mode/input source differs")
    else:
        _need("mode" not in raw and "input_provenance" not in raw, "Historical native J2 result must retain its original mode")
    versions, runtime = raw.get("versions"), raw.get("code_aster_runtime")
    _need(type(versions) is dict and versions.get("code_aster") == "17.4.0" and
          all(type(versions.get(name)) is str and versions[name].strip() for name in ("python", "numpy")) and
          type(runtime) is dict and runtime.get("version") == "17.4.0" and _same(runtime, ctx["detail"].get("code_aster_runtime")) and
          all(_same(value, ctx["detail"].get("versions", {}).get(key)) for key, value in versions.items()) and
          raw.get("measured_linear_residual") is None,
          "J2 recorded native runtime/version or residual semantics differ")
    material = ctx["settings"]["material"]
    young, hardening = material["youngs_modulus_mpa"], material["plastic_modulus_mpa"]
    native_material = raw.get("native_material")
    _need(type(native_material) is dict and set(native_material) in ({"ELAS", "ECRO_LINE"}, {"ELAS", "ECRO_LINE", "translation"}) and
          _same(native_material["ELAS"], {"E": young, "NU": material["poisson_ratio"]}) and
          _same(native_material["ECRO_LINE"], {"SY": material["yield_stress_mpa"], "D_SIGM_EPSI": young * (hardening / (young + hardening))}),
          "J2 native material differs from the saved E/nu/yield/plastic modulus")
    guard = raw.get("native_mesh_checks")
    _need(type(guard) is dict and guard.get("expected_mesh_sha256") == expected_entry["sha256"] and
          guard.get("checked_msh_sha256") == mesh_entry["sha256"], "J2 native import guard hashes differ")
    topology = _mesh_binding(expected, catalog, guard, ctx["settings"]["dimensions_mm"])
    computed = worker.parse_history_tables(raw, size, ctx["settings"]["history"]["times_s"])
    _need(_same({key: value for key, value in parsed.items() if key != "nonlinear_convergence"}, computed) and
          _same(parsed, ctx["records"][index]), "J2 parsed history differs from complete native table reparse or retained assessment")
    _native_tables(ctx, raw, index)
    return {"record": parsed, "entry": parsed_entry, "raw_entry": raw_entry, "topology": topology,
            "expected_sha256": expected_entry["sha256"], "mesh_sha256": mesh_entry["sha256"]}


def _initial(record):
    return {"index": 0, "kind": "INITIAL_STATE_NO_NEWTON_INCREMENT", "time_s": record["states"][0]["time_s"],
            "actual_result_order": record["states"][0]["actual_result_order"]}


def _display(result, proposal, resources):
    ctx = _headers(result, proposal, resources)
    _need(set(resources) == set(_BASE), "J2 display requires only the two verified headers")
    meshes = []
    for index, record in enumerate(ctx["records"]):
        path = f"simulation/level_{index}/parsed_history.json"
        meshes.append({"mesh_index": index, "mesh_size_mm": record["mesh_size_mm"], "artifact": path,
            "sha256": ctx["manifest"][path]["sha256"], "times_s": [state["time_s"] for state in record["states"]],
            "actual_result_orders": [state["actual_result_order"] for state in record["states"]],
            "node_ids": deepcopy(record["node_ids"]), "coordinates_mm": deepcopy(record["coordinates_mm"]),
            "element_count": record["element_count"], "gauss_ids": [
                {key: point[key] for key in ("element_id", "point", "subpoint")}
                for point in record["states"][0]["stress_identifiers"]], "group_node_ids": deepcopy(record["group_node_ids"]),
            "components": list(NODAL_COMPONENTS + GAUSS_COMPONENTS), "initial_state": _initial(record),
            "coordinate_frame": FRAME, "coordinates_unit": "mm", "limitations": list(LIMITATIONS)})
    return {"kind": "j2_fe_fields", "model_revision": result["model_revision"], "meshes": meshes,
            "limitations": list(LIMITATIONS), "original_status": result["status"], "decision": "NOT_RELEASED"}


def _selected(result, proposal, resources, selection):
    ctx = _headers(result, proposal, resources)
    ctx["result"] = result
    index = _selector(ctx, selection)
    verified = _level(ctx, resources, index)
    record, entry, raw_entry = verified["record"], verified["entry"], verified["raw_entry"]
    state = record["states"][selection["time_index"]]
    field, component = selection["component"].split(".")
    if selection["kind"] == "fe_nodal":
        row = record["node_ids"].index(selection["node_id"])
        position = record["coordinates_mm"][row]
        if field == "DEPL":
            value, unit, quantity, measure = state["displacements_mm"][row][worker.VECTOR_COMPONENTS.index(component)], "mm", "DISPLACEMENT", "native nodal displacement"
        else:
            value, unit, quantity, measure = state["nodal_reactions_n"][row][worker.VECTOR_COMPONENTS.index(component)], "N", "NODAL_REACTION", "signed native nodal reaction"
        location = f"native node {selection['node_id']} on recorded mesh {index}"
        coverage = "ALL_NATIVE_MESH_NODES"
    else:
        rows = [i for i, point in enumerate(state["stress_identifiers"]) if all(point[key] == selection[key] for key in ("element_id", "point", "subpoint"))]
        _need(len(rows) == 1, "Selected J2 Gauss point is not unique")
        row = rows[0]
        position = state["stress_point_coordinates_mm"][row]
        if field == "SIEF_ELGA":
            value, unit, quantity, measure = state["stresses_mpa"][row][worker.STRESS_COMPONENTS.index(component)], "MPa", "STRESS", "small-strain Cauchy stress at native Gauss point"
        else:
            value, unit, quantity, measure = state["eq_plastic_strain"][row], "1", "EQUIVALENT_PLASTIC_STRAIN", "native VMIS_ISOT_LINE VARI_ELGA.V1 cumulative equivalent plastic strain"
        location = f"native BODY TETRA10 {selection['element_id']} point {selection['point']} subpoint {selection['subpoint']} on recorded mesh {index}"
        coverage = "ALL_BODY_TETRA10_FIVE_RIGI_POINTS"
    initial = selection["time_index"] == 0
    source = {**deepcopy(selection), "quantity": quantity, "measure": measure, "coordinate_frame": FRAME,
        "location": location, "coordinates_mm": deepcopy(position), "coordinates_unit": "mm",
        "actual_result_order": state["actual_result_order"], "time_s": state["time_s"], "value_origin": "NATIVE_COMPONENT",
        "raw_artifact": raw_entry["path"], "raw_sha256": raw_entry["sha256"], "coverage": coverage,
        "mesh_sha256": verified["mesh_sha256"], "expected_mesh_sha256": verified["expected_sha256"],
        "topology": verified["topology"], "axis_semantics": "NATIVE_INST_DECLARED_QUASI_STATIC_HISTORY_SECONDS",
        **({"initial_state": _initial(record)} if initial else {})}
    return {"value": value, "unit": unit, "source_field": source, "qualification": {
        "numeric": "INITIAL_STATE_NO_NEWTON_INCREMENT" if initial else "RECORDED_NATIVE_VALUE",
        "reference": "RECORDED_DOMAIN_VERDICT_UNCHANGED", "physical": "UNKNOWN", "decision": "NOT_RELEASED"},
        "alignment": "USER_DECLARED_UNVERIFIED", "response_axis": {"quantity": "time", "value": state["time_s"], "unit": "s"}}


def _channels(result, proposal, resources):
    ctx = _headers(result, proposal, resources)
    index = len(ctx["records"]) - 1
    verified = _level(ctx, resources, index)
    record, entry, raw_entry = verified["record"], verified["entry"], verified["raw_entry"]
    states, channels = record["states"], []
    times, orders = [state["time_s"] for state in states], [state["actual_result_order"] for state in states]
    count = 5 * record["element_count"]

    def add(identifier, label, values, quantity, component, measure, unit, location, native_field, *, derived=False):
        _vector(values, len(times), "history channel")
        channels.append({"id": identifier, "label": label, "metric": None, "quantity": quantity,
            "component": component, "measure": measure, "coordinate_frame": FRAME, "location": location, "unit": unit,
            "axis": {"quantity": "time", "unit": "s", "values": list(times),
                     "semantics": "NATIVE_INST_DECLARED_QUASI_STATIC_HISTORY_SECONDS"}, "values": list(values),
            "initial_state": _initial(record), "origin": {"kind": "DERIVED" if derived else "NATIVE",
                "driver": "code_aster", "artifact": entry["path"], "sha256": entry["sha256"],
                "native_artifact": raw_entry["path"], "native_sha256": raw_entry["sha256"], "native_field": native_field,
                "mapping": "ALL_GAUSS_UNWEIGHTED_ARITHMETIC_MEAN" if derived else "EXACT_NATIVE_POST_RELEVE_T_BOUNDARY_RESULTANT",
                "mesh_index": index, "mesh_size_mm": record["mesh_size_mm"], "actual_result_orders": list(orders),
                "mesh_sha256": verified["mesh_sha256"], "expected_mesh_sha256": verified["expected_sha256"],
                **({"aggregation": {"operation": "arithmetic_mean", "weighting": "UNWEIGHTED", "point_count": count,
                    "coverage": "ALL_BODY_TETRA10_FIVE_RIGI_POINTS", "volume_average": False}} if derived else {})}})

    for group, axis, component in (("X0", 0, "FX"), ("Y0", 1, "FY"), ("Z0", 2, "FZ"), ("XL", 0, "FX")):
        add(f"j2-{group.lower()}-{component.lower()}", f"{group} 부호 반력 {component}",
            [state["native_boundary_resultants_n"][group][axis] for state in states], "force", component,
            "signed native POST_RELEVE_T boundary resultant", "N", f"group {group}.{worker.VECTOR_COMPONENTS[axis]} on finest declared mesh {index}",
            f"BOUNDARY_RESULTANTS.{group}.{worker.VECTOR_COMPONENTS[axis]}")
    for axis, component in enumerate(worker.STRESS_COMPONENTS):
        add("j2-gauss-mean-" + component.lower(), f"Gauss {component} 산술평균 (가중 없음)",
            [math.fsum(row[axis] / count for row in state["stresses_mpa"]) for state in states], "stress", component,
            "UNWEIGHTED arithmetic mean of small-strain Cauchy Gauss stress; not volume average", "MPa",
            f"all BODY TETRA10 five-point Gauss samples on finest declared mesh {index}", "SIEF_ELGA." + component, derived=True)
    add("j2-gauss-mean-v1", "Gauss 등가 소성변형률 V1 산술평균 (가중 없음)",
        [math.fsum(value / count for value in state["eq_plastic_strain"]) for state in states], "equivalent_plastic_strain", "V1",
        "UNWEIGHTED arithmetic mean of native VARI_ELGA.V1; not volume average", "1",
        f"all BODY TETRA10 five-point Gauss samples on finest declared mesh {index}", "VARI_ELGA.V1", derived=True)
    return deepcopy(channels)


class PlasticityResponseFieldsAdapter:
    backend = BACKEND
    history_limitations = LIMITATIONS

    @staticmethod
    def field_response_resources(result):
        manifest = _manifest(result)
        for role, path in _BASE.items():
            _entry(manifest, path, INPUT_LIMIT if role == "input" else JSON_LIMIT)
        return {role: {"path": path, "maximum_bytes": INPUT_LIMIT if role == "input" else JSON_LIMIT}
                for role, path in _BASE.items()}

    @staticmethod
    def field_selection_resources(result, selection, verified_resources):
        def policy():
            ctx = _headers(result, None, verified_resources)
            _need(set(verified_resources) == set(_BASE), "J2 selection requires exactly the two verified headers")
            ctx["result"] = result
            return _level_policy(_selector(ctx, selection))
        return _call(policy)

    @staticmethod
    def display_response_fields(result, proposal, resources):
        return _call(_display, result, proposal, resources)

    @staticmethod
    def select_response_fields(result, proposal, resources, selection):
        return _call(_selected, result, proposal, resources, selection)

    @staticmethod
    def history_response_resources(result):
        manifest = _manifest(result)
        settings = result["provenance"].get("execution_settings")
        _need(_same(domain.validate_settings(settings), settings), "J2 finest history must use the original normalized settings")
        policy = {**PlasticityResponseFieldsAdapter.field_response_resources(result),
                  **_level_policy(len(settings["mesh_sizes_mm"]) - 1)}
        for spec in policy.values():
            _entry(manifest, spec["path"], spec["maximum_bytes"])
        return policy

    @staticmethod
    def response_history_channels(result, proposal, resources):
        return _call(_channels, result, proposal, resources)
