"""Pure selectors for the five retained serial P1 PDE field contracts.

Core supplies parsed, manifest-verified bytes and rechecks the immutable source
before/after these hooks. Nothing here opens files, executes a solver or runs
supplied code. Coupled producer 1.1 declarations/traces reuse the bounded Domain
AST checks; historical producer 1 is not reinterpreted through that validator.
No Domain verdict changes. Native DOF IDs belong to one exact field artifact;
coordinates and time are dimensionless model quantities.
"""

from copy import deepcopy
import hashlib
import json

from .fenicsx_gmsh import parse_msh, dense_import
from .structural_response_fields import _need, _finite, _integer, _sha, _keys, _same, _path


SUPPORTED_BACKENDS = tuple("pde.fenicsx." + kind for kind in
                           ("rectangle", "transient", "vector", "coupled", "imported"))
JSON_LIMIT = 32 * 1024 * 1024
NODE_LIMIT, CELL_LIMIT, ENTRY_LIMIT = 200000, 400000, 2048
FRAME = "PDE_MODEL_CARTESIAN"
_HEADERS = {"input": "pde/input.json", "source": "pde/source_manifest.json",
            "worker": "pde/worker_result.json"}
_SIDES = {"xmin", "xmax", "ymin", "ymax"}
_VERSIONS = {"python", "dolfinx", "ufl", "basix", "ffcx", "petsc4py", "petsc", "mpi4py", "numpy"}
_SELECTION = {"kind", "artifact", "sha256", "model_revision", "study_index",
              "step_index", "node_id", "component"}
_SOURCE_COMMON = {
    "expression_parser": ("caelab/adapters/fenicsx_worker.py", "fenicsx_expression.py"),
    "execution_control": ("caelab/execution_control.py", "sources/execution_control.py"),
}
_SOURCE_RECTANGLE = {
    "rectangle_domain_reference": ("plugins/pde_elliptic/reference.py", "domain_reference.py"),
    "rectangle_adapter": ("caelab/adapters/fenicsx_rectangle.py", "sources/fenicsx_rectangle.py"),
    "rectangle_worker": ("caelab/adapters/fenicsx_rectangle_worker.py", "rectangle_worker.py"),
}
_LIMITATIONS = [
    "Exact retained native P1 DOF/component only; no interpolation, nearest node or unit conversion.",
    "Coordinates and transient time have unit 1 in the declared PDE model; no physical/world/sensor alignment is inferred.",
    "Original Domain numerical/reference verdicts and invalid metrics are unchanged; physical qualification UNKNOWN/NOT_RELEASED.",
]


def _sources(kind):
    domains = {"rectangle": "elliptic", "transient": "transient", "vector": "vector",
               "coupled": "coupled", "imported": "imported"}
    result = {**_SOURCE_COMMON,
              "adapter": (f"caelab/adapters/fenicsx_{kind}.py", f"sources/fenicsx_{kind}.py"),
              "worker": (f"caelab/adapters/fenicsx_{kind}_worker.py", "worker.py"),
              "domain_reference": (f"plugins/pde_{domains[kind]}/reference.py",
                                   "domain_reference.py" if kind == "rectangle" else f"{kind}_reference.py")}
    if kind != "rectangle":
        result.update(_SOURCE_RECTANGLE)
    if kind == "transient":
        result["time_expression"] = ("caelab/adapters/fenicsx_time_expression.py", "fenicsx_time_expression.py")
    if kind in ("coupled", "imported"):
        result["vector_worker_helper"] = ("caelab/adapters/fenicsx_vector_worker.py", "vector_worker.py")
    if kind == "imported":
        result["mesh_syntax"] = ("caelab/adapters/fenicsx_gmsh.py", "mesh_syntax.py")
    return result


def _json_tree(value, depth=0, active=None):
    """Also reject JSON exponent overflow and cycles in supplied Python objects."""
    _need(depth <= 64, "PDE JSON nesting exceeds the reader contract")
    if type(value) in (int, float):
        _need(_finite(value), "Nonfinite PDE JSON number")
    elif type(value) in (dict, list):
        active = set() if active is None else active
        _need(id(value) not in active, "Cyclic PDE resource")
        active.add(id(value))
        if type(value) is dict:
            _need(all(type(key) is str for key in value), "PDE JSON object keys must be strings")
        for item in value.values() if type(value) is dict else value:
            _json_tree(item, depth + 1, active)
        active.remove(id(value))
    else:
        _need(value is None or type(value) in (str, bool), "Non-JSON PDE resource value")


def _manifest(result):
    _need(type(result) is dict and type(result.get("provenance")) is dict, "PDE result provenance required")
    backend = result["provenance"].get("adapter")
    version = result["provenance"].get("adapter_version")
    _need(backend in SUPPORTED_BACKENDS and (version == "1" or
          backend == "pde.fenicsx.coupled" and version == "1.1"),
          "Unsupported PDE field producer")
    _need(_sha(result.get("proposal_revision")) and _sha(result.get("model_revision")), "PDE result revisions required")
    _need(type(result.get("artifacts")) is list, "PDE artifact manifest required")
    manifest, folded = {}, set()
    for entry in result["artifacts"]:
        _need(type(entry) is dict and _path(entry.get("path")) and _sha(entry.get("sha256")) and
              _integer(entry.get("size_bytes"), positive=False) and entry.get("revision") == result["proposal_revision"],
              "PDE artifact identity/size/proposal revision differs")
        path = entry["path"]
        _need(path.casefold() not in folded, "Duplicate PDE artifact path")
        folded.add(path.casefold())
        manifest[path] = entry
    return backend.rsplit(".", 1)[1], manifest


def _resource(resources, role, manifest, path):
    item = resources.get(role)
    _need(type(item) is tuple and len(item) == 2, "PDE resources require (JSON, manifest entry) tuples")
    raw, entry = item
    _need(path in manifest and _same(entry, manifest[path]) and type(raw) is dict and
          0 < entry["size_bytes"] <= JSON_LIMIT, "PDE resource differs from bounded manifest entry")
    _json_tree(raw)
    return raw, entry


def _headers(result, proposal, resources):
    kind, manifest = _manifest(result)
    _need(type(proposal) is dict and result.get("experiment_id") == proposal.get("id") and
          type(result.get("experiment_id")) is str and bool(result["experiment_id"]) and
          result.get("study", {}).get("id") == proposal.get("study_id") and
          result["model_revision"] == proposal.get("model_revision") and
          proposal.get("physics", {}).get("backend") == result["provenance"]["adapter"] and
          result.get("cad_revision") is None and proposal.get("cad_revision") is None and
          result["provenance"].get("proposal_sha256") == result["proposal_revision"],
          "PDE proposal/result/model identity differs")
    _need(result.get("status") in ("COMPLETED_REVIEW_REQUIRED", "REJECTED") and
          result.get("solver_status") == "COMPLETED" and result.get("decision") == "NOT_RELEASED",
          "PDE native execution has no complete retained field")
    _need(type(resources) is dict and set(_HEADERS) <= set(resources) and len(resources) <= 8,
          "PDE resource set must contain three bounded headers")
    input_, spec_entry = _resource(resources, "input", manifest, _HEADERS["input"])
    source, source_entry = _resource(resources, "source", manifest, _HEADERS["source"])
    worker, _ = _resource(resources, "worker", manifest, _HEADERS["worker"])
    provenance = result["provenance"]
    version = provenance["adapter_version"]
    detail = provenance.get("adapter_details")
    _need(_same(input_, proposal.get("execution")) and _same(input_, provenance.get("execution_settings")),
          "PDE input differs from the immutable proposal/settings")
    _need(type(detail) is dict and detail.get("adapter") == provenance["adapter"] and
          detail.get("adapter_version") == version and detail.get("domain_plugin_version") == version and
          detail.get("units") == "dimensionless" and detail.get("source_manifest") == _HEADERS["source"] and
          detail.get("spec_sha256") == spec_entry["sha256"] == worker.get("spec_sha256") and
          detail.get("source_manifest_sha256") == source_entry["sha256"] == worker.get("source_manifest_sha256"),
          "PDE native spec/source/adapter identity differs")
    _need(_keys(source, {"schema_version", "domain_plugin_version", "files"}) and source["schema_version"] == "1" and
          source["domain_plugin_version"] == detail["domain_plugin_version"] and
          _keys(source["files"], _sources(kind)) and _keys(detail.get("source_sha256"), source["files"]),
          "PDE copied source manifest membership/version differs")
    used_sources = set()
    for key, (repository_path, copied_path) in _sources(kind).items():
        row = source["files"][key]
        _need(_keys(row, {"repository_path", "copied_path", "sha256"}) and
              row["repository_path"] == repository_path and row["copied_path"] == copied_path and
              _sha(row["sha256"]) and row["sha256"] == detail["source_sha256"][key],
              "PDE preserved source path/hash differs")
        path = "pde/" + copied_path
        _need(path in manifest and manifest[path]["sha256"] == row["sha256"] and path not in used_sources,
              "PDE copied source is not uniquely manifested")
        used_sources.add(path)
    versions = worker.get("versions")
    required_versions = _VERSIONS | ({"gmsh"} if kind == "imported" else set())
    _need(worker.get("schema_version") == "1" and worker.get("status") == "COMPLETED" and
          type(worker.get("mpi_size")) is int and worker["mpi_size"] == 1 and worker.get("scalar_type") == "float64" and
          type(versions) is dict and required_versions <= set(versions) and
          all(type(versions[key]) is str and versions[key].strip() for key in required_versions) and
          _same(detail.get("versions"), versions) and type(detail.get("mpi_size")) is int and
          detail["mpi_size"] == 1 and detail.get("scalar_type") == "float64",
          "Unsupported PDE native worker/library identity/layout")
    _need(type(input_.get("mesh")) is dict and type(input_["mesh"].get("degree")) is int and input_["mesh"]["degree"] == 1,
          "Only retained native P1 fields are supported")
    selected = input_.get("mode") == "selected_mesh"
    coupled_domain = None
    if kind == "coupled" and version == "1.1":
        from plugins.pde_coupled import reference as coupled_domain
        # Version 1.1 opts into this exact declaration contract. The original
        # producer is joined by its preserved source capsule above, never by
        # hashes of today's files or a new verdict for historical producer 1.
        _need(_same(coupled_domain.validate_settings(input_), input_),
              "Coupled 1.1 input differs from the declared contract")
        _need(detail.get("error_quadrature_degree") == (None if selected else 8),
              "Coupled reference quadrature scope differs")
    if selected:
        if kind == "coupled":
            _need(coupled_domain is not None and worker.get("mode") == detail.get("mode") == "selected_mesh" and
                  worker.get("scope") == detail.get("scope") == coupled_domain.SELECTED_SCOPE and
                  _same(worker.get("input_provenance"), input_["input_provenance"]) and
                  _same(detail.get("input_provenance"), input_["input_provenance"]),
                  "Selected coupled native scope/source differs")
        else:
            _need(kind == "rectangle" and set(input_) == {"mode", "problem", "mesh", "validation"} and
                  input_["problem"].get("reference") is None and len(input_["mesh"].get("cell_counts", [])) == 1 and
                  worker.get("mode") == detail.get("mode") == "selected_mesh" and
                  worker.get("scope") == detail.get("scope") == "SELECTED_DIMENSIONLESS_SCALAR_RECTANGLE",
                  "Selected rectangle native scope differs")
    else:
        _need("mode" not in input_ and "mode" not in worker and "mode" not in detail,
              "Unsupported PDE input/worker mode")
    return {"kind": kind, "manifest": manifest, "input": input_, "worker": worker, "detail": detail,
            "result": result, "proposal": proposal, "selected": selected, "coupled_domain": coupled_domain}


def _files(ctx, row, used):
    kind = ctx["kind"]
    names = {"field", "field_data", "form_source", "dofs"}
    if kind == "transient":
        names.add("time_binding")
    if kind in ("vector", "coupled", "imported"):
        names.add("binding")
    if kind == "imported":
        names.update(("original", "dense", "mapping"))
    _need(_keys(row.get("files"), names) and _keys(row.get("artifact_sha256"), names), "PDE study file/hash keys differ")
    result = {}
    for name in names:
        relative = row["files"][name]
        _need(_path(relative) and not relative.casefold().startswith("pde/"), "Unsafe/output-relative PDE field path")
        path = "pde/" + relative
        entry = ctx["manifest"].get(path)
        _need(entry is not None and _sha(row["artifact_sha256"][name]) and
              entry["sha256"] == row["artifact_sha256"][name] and path not in used,
              "PDE study file/manifest identity differs or is reused")
        used.add(path)
        result[name] = path
    return result


def _counts(row, vector):
    _need(_integer(row.get("global_cells")) and _integer(row.get("global_dofs")) and
          _integer(row.get("dirichlet_dofs"), positive=False), "PDE native counts malformed")
    if vector:
        _need(_integer(row.get("global_nodes")) and row["global_dofs"] == 2 * row["global_nodes"] and
              type(row.get("block_size")) is int and row["block_size"] == 2, "PDE vector block/scalar count differs")
    elif "global_nodes" in row:
        _need(type(row["global_nodes"]) is int and row["global_nodes"] == row["global_dofs"], "PDE scalar node/DOF count differs")


def _entries(ctx):
    kind, input_, worker = ctx["kind"], ctx["input"], ctx["worker"]
    entries, used = [], set()

    def append(row, study_index, step_index, study):
        _need(type(row) is dict and len(entries) < ENTRY_LIMIT, "PDE catalog exceeds 2048 entries or has an invalid row")
        _counts(row, kind in ("vector", "coupled"))
        files = _files(ctx, row, used)
        prefix = (f"study_{study_index}_n{study['cells_per_axis']}_N{study['step_count']}/step_{step_index}"
                  if kind == "transient" else f"level_{study_index}" if kind == "imported" else f"level_n{row['cells_per_axis']}")
        filenames = {"field": "field.xdmf", "field_data": "field.h5", "form_source": "forms.ufl.txt",
                     "dofs": "dofs.json", "binding": "binding.json", "time_binding": "time_binding.json",
                     "original": "original.msh", "dense": "dense-import.msh", "mapping": "import_mapping.json"}
        _need(_same(row["files"], {name: prefix + "/" + filenames[name] for name in files}),
              "PDE field paths differ from the declared producer study/step")
        entries.append({"row": row, "study": study, "study_index": study_index,
                        "step_index": step_index, "files": files})

    if kind == "transient":
        time = input_.get("time", {})
        meshes, steps = input_["mesh"].get("cell_counts"), time.get("step_counts")
        _need(input_.get("refinement_axis") in ("mesh", "time") and type(meshes) is list and type(steps) is list and
              meshes and steps and all(_integer(n) for n in [*meshes, *steps]) and
              _finite(time.get("start")) and time["start"] == 0 and _finite(time.get("end")) and time["end"] > 0 and
              time.get("unit") == "1" and time.get("scheme") == "backward_euler" and
              (len(steps) == 1 if input_["refinement_axis"] == "mesh" else len(meshes) == 1),
              "PDE transient input/refinement/time binding differs")
        pairs = [(n, steps[0]) for n in meshes] if input_["refinement_axis"] == "mesh" else [(meshes[0], n) for n in steps]
        _need(sum(count + 1 for _, count in pairs) <= ENTRY_LIMIT and
              type(worker.get("studies")) is list and len(worker["studies"]) == len(pairs), "PDE transient retained study count differs")
        for i, (n, count) in enumerate(pairs):
            study = worker["studies"][i]
            dt = time["end"] / count
            _need(type(study) is dict and type(study.get("study_index")) is int and study["study_index"] == i and
                  type(study.get("cells_per_axis")) is int and study["cells_per_axis"] == n and
                  type(study.get("step_count")) is int and study["step_count"] == count and
                  study.get("refinement_axis") == input_["refinement_axis"] and _same(study.get("dt"), dt) and
                  type(study.get("steps")) is list and len(study["steps"]) == count + 1, "PDE transient native study/grid differs")
            previous = None
            for j, row in enumerate(study["steps"]):
                instant = j * time["end"] / count
                _need(type(row) is dict and type(row.get("index")) is int and row["index"] == j and
                      _same(row.get("time"), instant) and _same(row.get("native_time_value"), instant) and
                      _same(row.get("dt"), dt if j else 0) and row.get("solver_status") == ("COMPLETED" if j else "NOT_RUN") and
                      row.get("previous_values_sha256") == previous and _sha(row.get("current_values_sha256")) and
                      row.get("distinct_state") is True, "PDE transient actual step/time/value chain differs")
                if j == 0:
                    _need(all(row.get(key) is None for key in ("linear_residual", "ksp_convergence_reason", "ksp_iterations")),
                          "PDE initial condition must remain NOT_RUN")
                append(row, i, j, study)
                previous = row["current_values_sha256"]
    else:
        levels = input_["mesh"].get("levels" if kind == "imported" else "cell_counts")
        _need(type(levels) is list and 0 < len(levels) <= ENTRY_LIMIT and type(worker.get("mesh_studies")) is list and
              len(worker["mesh_studies"]) == len(levels), "PDE mesh history differs from frozen input")
        for i, (level, row) in enumerate(zip(levels, worker["mesh_studies"])):
            _need(type(row) is dict and type(row.get("degree")) is int and row["degree"] == 1 and row.get("cell_type") == "triangle" and
                  (type(row.get("level")) is int and row["level"] == i if kind == "imported" else
                   _integer(level) and type(row.get("cells_per_axis")) is int and row["cells_per_axis"] == level),
                  "PDE native refinement/P1 triangle identity differs")
            if ctx["coupled_domain"] is not None:
                _need(row.get("global_nodes") == (level + 1)**2 and row.get("global_cells") == 2 * level**2 and
                      type(row.get("interface_facets")) is int and row["interface_facets"] == level,
                      "Coupled native full grid/interface count differs")
                if ctx["selected"]:
                    reference_names = ctx["coupled_domain"]._REFERENCE_METRICS
                    components = row.get("components")
                    _need(all(name in row and row[name] is None for name in reference_names) and
                          type(components) is list and len(components) == 2 and all(
                              type(component) is dict and type(component.get("index")) is int and
                              component["index"] == j and component.get("field") == f"u{j}" and
                              all(name in component and component[name] is None for name in reference_names)
                              for j, component in enumerate(components)),
                          "Selected coupled reference diagnostics must remain null")
            append(row, i, None, row)
            if kind == "imported":
                _need(type(level) is dict and type(level.get("data")) is str and _sha(level.get("sha256")) and
                      row.get("source_sha256") == level["sha256"] == ctx["manifest"][entries[-1]["files"]["original"]]["sha256"] and
                      _sha(row.get("dense_sha256")) and row["dense_sha256"] == ctx["manifest"][entries[-1]["files"]["dense"]]["sha256"],
                      "PDE original/dense imported mesh identity differs")
                parse_msh(level["data"], level["sha256"])
    return entries


def _selection(ctx, entries, selection):
    _need(_keys(selection, _SELECTION) and selection["kind"] == "pde_nodal" and
          _sha(selection["sha256"]) and selection["model_revision"] == ctx["result"]["model_revision"] and
          _integer(selection["study_index"], positive=False) and _integer(selection["node_id"], positive=False) and
          (selection["step_index"] is None or _integer(selection["step_index"], positive=False)),
          "Exact PDE nodal selector/revision/index required")
    components = ("u0", "u1") if ctx["kind"] in ("vector", "coupled") else ("u",)
    _need(selection["component"] in components, "PDE selector component differs from the native layout")
    matched = [entry for entry in entries if entry["study_index"] == selection["study_index"] and entry["step_index"] == selection["step_index"]]
    _need(len(matched) == 1, "PDE selected study/step is not retained")
    entry = matched[0]
    _need(selection["artifact"] == entry["files"]["dofs"] and
          selection["sha256"] == ctx["manifest"][entry["files"]["dofs"]]["sha256"],
          "PDE selector artifact/hash/level differs")
    return entry


def _policy(entry, entries):
    paths = {"dofs": entry["files"]["dofs"]}
    for role in ("binding", "mapping", "time_binding"):
        if role in entry["files"]:
            paths[role] = entry["files"][role]
    if entry["step_index"] is not None and entry["step_index"] > 0:
        previous = next(row for row in entries if row["study_index"] == entry["study_index"] and row["step_index"] == entry["step_index"] - 1)
        paths.update(previous_dofs=previous["files"]["dofs"], previous_time_binding=previous["files"]["time_binding"])
    return {role: {"path": path, "maximum_bytes": JSON_LIMIT} for role, path in paths.items()}


def _ids(value, label, count=None, positive=False):
    _need(type(value) is list and (count is None or len(value) == count) and
          all(_integer(item, positive=positive) for item in value) and len(set(value)) == len(value),
          label + ": exact unique native identifiers required")
    return set(value)


def _values(value, count, vector, label):
    _need(type(value) is list and len(value) == count and all(
        type(row) is list and len(row) == 2 and all(_finite(v) for v in row) if vector else _finite(row)
        for row in value), label + ": finite scalar/directed native layout differs")


def _geometry(ctx, row, field):
    vector = ctx["kind"] in ("vector", "coupled")
    explicit = ctx["kind"] in ("coupled", "imported")
    keys = {"schema_version", "coordinates_unit", "field_unit", "node_ids", "coordinates", "values",
            "cell_node_ids", "dirichlet_node_ids", "boundaries"}
    if vector:
        keys.update(("field_type", "components", "block_size"))
    if explicit:
        keys.add("cell_ids")
    if ctx["kind"] == "coupled":
        keys.update(("cell_regions", "interface"))
    if ctx["kind"] == "imported":
        keys.update(("source_node_ids", "source_cell_ids"))
    _need(_keys(field, keys) and field["schema_version"] == "1" and
          field["coordinates_unit"] == field["field_unit"] == "1", "PDE native field schema/units differ")
    if vector:
        _need(field["field_type"] == "vector" and type(field["block_size"]) is int and field["block_size"] == 2 and
              field["components"] == ["u0", "u1"], "PDE native component/block order differs")
    count = row["global_dofs"] // (2 if vector else 1)
    _need(count <= NODE_LIMIT and row["global_cells"] <= CELL_LIMIT, "PDE field exceeds bounded node/triangle reader limits")
    nodes = _ids(field["node_ids"], "PDE nodes", count)
    _need(field["node_ids"] == sorted(nodes), "PDE nodes must retain sorted native order")
    _need(type(field["coordinates"]) is list and len(field["coordinates"]) == count and all(
        type(point) is list and len(point) == 2 and all(_finite(v) for v in point) for point in field["coordinates"]),
        "Finite native Nx2 coordinates required")
    _need(len({tuple(point) for point in field["coordinates"]}) == count, "Duplicate PDE native coordinates")
    _values(field["values"], count, vector, "PDE native values")
    _need(type(field["cell_node_ids"]) is list and len(field["cell_node_ids"]) == row["global_cells"], "PDE triangle count differs")
    if explicit:
        _ids(field["cell_ids"], "PDE native cells", row["global_cells"])
    points = dict(zip(field["node_ids"], field["coordinates"]))
    edges, triangles, used = {}, set(), set()
    for i, cell in enumerate(field["cell_node_ids"]):
        members = _ids(cell, "PDE triangle", 3)
        _need(members <= nodes and tuple(sorted(members)) not in triangles, "PDE triangle references a foreign node or duplicate cell")
        triangles.add(tuple(sorted(members)))
        a, b, c = [points[node] for node in cell]
        area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        _need(_finite(area) and area != 0, "Degenerate/nonfinite PDE triangle")
        used.update(members)
        for pair in ((cell[0], cell[1]), (cell[1], cell[2]), (cell[2], cell[0])):
            adjacent = edges.setdefault(tuple(sorted(pair)), [])
            adjacent.append(i)
            _need(len(adjacent) <= 2, "Nonmanifold PDE native edge")
    _need(used == nodes, "Incomplete native P1 node coverage")
    shape = {"vector": vector, "nodes": nodes, "edges": edges, "exterior": set(), "facets": set(), "dirichlet": set()}
    declared = ctx["input"].get("problem", {}).get("boundaries")
    _need(type(declared) is dict and _keys(field["boundaries"], declared), "PDE named boundary membership differs")
    if ctx["kind"] != "imported":
        _need(set(declared) == _SIDES, "PDE named rectangle sides differ")
    for name, declaration in declared.items():
        _need(type(declaration) is dict and declaration.get("type") in ("dirichlet", "neumann"), "Unsupported PDE boundary type")
        if ctx["kind"] == "coupled":
            _need(type(declaration.get("value")) is dict and _keys(field["boundaries"][name], declaration["value"]), "PDE split-side regions differ")
            for boundary in field["boundaries"][name].values():
                _boundary(shape, boundary, declaration["type"])
        else:
            _boundary(shape, field["boundaries"][name], declaration["type"])
    _need(shape["exterior"] == {edge for edge, adjacent in edges.items() if len(adjacent) == 1}, "Incomplete PDE native exterior coverage")
    constrained = _ids(field["dirichlet_node_ids"], "PDE Dirichlet nodes")
    _need(field["dirichlet_node_ids"] == sorted(constrained) and constrained == shape["dirichlet"] and
          row["dirichlet_dofs"] == len(constrained) * (2 if vector else 1) and
          ("dirichlet_nodes" not in row or type(row["dirichlet_nodes"]) is int and row["dirichlet_nodes"] == len(constrained)),
          "PDE native prescribed node/scalar count differs")
    return shape


def _boundary(shape, row, type_):
    _need(type(row) is dict, "Missing PDE native boundary")
    facets = _ids(row.get("facet_ids"), "PDE native facets")
    dofs = _ids(row.get("dof_ids"), "PDE boundary DOFs")
    endpoints = row.get("facet_node_ids")
    _need(row["dof_ids"] == sorted(dofs) and type(endpoints) is list and len(endpoints) == len(facets), "PDE facet/endpoint count or order differs")
    union = set()
    for pair in endpoints:
        members = _ids(pair, "PDE boundary endpoints", 2)
        edge = tuple(sorted(pair))
        _need(members <= shape["nodes"] and len(shape["edges"].get(edge, [])) == 1 and edge not in shape["exterior"],
              "PDE boundary does not uniquely partition native exterior")
        shape["exterior"].add(edge)
        union.update(members)
    _need(dofs == union and not facets & shape["facets"], "PDE boundary endpoint/DOF/facet identities differ")
    shape["facets"].update(facets)
    _need(_finite(row.get("measure")) and row["measure"] > 0 and type(row.get("normal_integral")) is list and
          len(row["normal_integral"]) == 2 and all(_finite(v) for v in row["normal_integral"]), "PDE boundary measure/normal malformed")
    _values(row.get("prescribed_values"), len(dofs), shape["vector"], "PDE prescribed values")
    integral = row.get("prescribed_integral")
    _need(type(integral) is list and len(integral) == 2 and all(_finite(v) for v in integral) if shape["vector"] else _finite(integral),
          "PDE prescribed integral component shape differs")
    if type_ == "dirichlet":
        shape["dirichlet"].update(dofs)


def _binding(binding, field, vector):
    _need(binding.get("schema_version") == "1" and _same(binding.get("node_ids"), field["node_ids"]), "PDE binding native node order differs")
    if vector:
        _need(binding.get("components") == ["u0", "u1"], "PDE binding directed components differ")
    _values(binding.get("rhs_values"), len(field["node_ids"]), vector, "PDE RHS binding")
    _values(binding.get("reference_values"), len(field["node_ids"]), vector, "PDE reference binding")


def _coupled(ctx, row, field, binding, shape):
    _need(type(field["cell_regions"]) is list and len(field["cell_regions"]) == row["global_cells"] and
          all(region in ("left", "right") for region in field["cell_regions"]), "PDE native region labels differ")
    regions = {}
    for region in ("left", "right"):
        indices = [i for i, name in enumerate(field["cell_regions"]) if name == region]
        cells = {field["cell_ids"][i] for i in indices}
        nodes = {n for i in indices for n in field["cell_node_ids"][i]}
        _need(indices and type(row.get("region_cell_counts", {}).get(region)) is int and row["region_cell_counts"][region] == len(indices),
              "PDE native region cell count differs")
        regions[region] = (cells, nodes)
    interface = field["interface"]
    _need(type(interface) is dict, "PDE material interface missing")
    facets = _ids(interface.get("facet_ids"), "PDE interface facets")
    endpoints, neighbours = interface.get("facet_node_ids"), interface.get("adjacent_cell_ids")
    _need(type(endpoints) is list and type(neighbours) is list and len(endpoints) == len(neighbours) == len(facets) and
          _finite(interface.get("measure")) and interface["measure"] > 0 and _same(interface.get("plus_x_normal"), [1, 0]),
          "PDE interface shape/normal differs")
    seen, nodes, cell_rows = set(), set(), dict(zip(field["cell_ids"], range(row["global_cells"])))
    for pair, adjacent_cells in zip(endpoints, neighbours):
        members = _ids(pair, "PDE interface endpoints", 2)
        _ids(adjacent_cells, "PDE interface neighbour cells", 2)
        edge = tuple(sorted(pair))
        adjacent = shape["edges"].get(edge, [])
        _need(members <= shape["nodes"] and len(adjacent) == 2 and edge not in seen and
              adjacent_cells[0] in regions["left"][0] and adjacent_cells[1] in regions["right"][0] and
              set(adjacent) == {cell_rows[cell] for cell in adjacent_cells}, "PDE interface left/right adjacency differs")
        seen.add(edge)
        nodes.update(members)
    expected = {edge for edge, adjacent in shape["edges"].items() if len(adjacent) == 2 and
                field["cell_regions"][adjacent[0]] != field["cell_regions"][adjacent[1]]}
    _need(seen == expected and _ids(interface.get("node_ids"), "PDE interface nodes") == nodes and not facets & shape["facets"],
          "Incomplete or overlapping PDE material interface")
    _need(binding.get("schema_version") == "1" and binding.get("components") == ["u0", "u1"] and
          _keys(binding.get("regions"), {"left", "right"}), "PDE regional binding components differ")
    weak = ctx["input"]["problem"]["weak_form"]
    for region, (cells, nodes) in regions.items():
        b = binding["regions"][region]
        _need(type(b) is dict and _ids(b.get("cell_ids"), "PDE regional cells") == cells and
              _ids(b.get("node_ids"), "PDE regional nodes") == nodes and b["node_ids"] == sorted(nodes), "PDE regional identity differs")
        _values(b.get("rhs_values"), len(nodes), True, "PDE regional RHS traces")
        if ctx["selected"]:
            _need("reference_values" in b and b["reference_values"] is None,
                  "Selected coupled reference traces must remain explicitly null")
        else:
            _values(b.get("reference_values"), len(nodes), True, "PDE regional reference traces")
        _values(b.get("diffusion"), 2, True, "PDE diffusion matrix")
        _values(b.get("reaction"), 2, True, "PDE reaction matrix")
        _need(_same(b["diffusion"], weak["diffusion"][region]) and _same(b["reaction"], weak["reaction"]) and
              _same(b["diffusion"], row.get("region_coefficients", {}).get(region)) and _same(b["reaction"], row.get("reaction_matrix")),
              "PDE native regional coefficient binding differs")
    if ctx["coupled_domain"] is not None:
        domain = ctx["coupled_domain"]
        trees = domain._trees(ctx["input"]["problem"])
        # Reuse full native grid/tag/side/interface and declared AST trace checks,
        # without assessing reference errors, convergence or engineering release.
        domain._retained_field(ctx["input"], row, field, trees)
        domain._coefficient_observations(ctx["input"], row)
        _need(_keys(binding, {"schema_version", "components", "regions"}), "Coupled binding schema differs")
        points = dict(zip(field["node_ids"], field["coordinates"]))
        for region in ("left", "right"):
            b = binding["regions"][region]
            _need(_keys(b, {"cell_ids", "node_ids", "diffusion", "reaction", "rhs_values", "reference_values"}),
                  "Coupled regional binding schema differs")
            pairs = [("rhs_values", trees["rhs"][region])]
            if not ctx["selected"]:
                pairs.append(("reference_values", trees["reference"][region]))
            for name, parsed in pairs:
                for node, values in zip(b["node_ids"], b[name]):
                    for component in range(2):
                        domain._same(values[component], domain._value(parsed[component], points[node]),
                                     "Native coupled regional/interface input trace")


def _imported(ctx, entry, field, binding, mapping):
    row = entry["row"]
    n, m = len(field["node_ids"]), len(field["cell_ids"])
    sources = _ids(field["source_node_ids"], "PDE original nodes", n, positive=True)
    source_cells = _ids(field["source_cell_ids"], "PDE original cells", m, positive=True)
    _need(mapping.get("schema_version") == "1" and mapping.get("original_sha256") == row["source_sha256"] and
          mapping.get("dense_sha256") == row["dense_sha256"] and binding.get("source_sha256") == row["source_sha256"] and
          binding.get("dense_sha256") == row["dense_sha256"] and _same(binding.get("source_node_ids"), field["source_node_ids"]),
          "PDE imported raw/dense/binding identity differs")
    original = mapping.get("original_node_ids")
    _need(_ids(original, "PDE original sorted nodes", n, positive=True) == sources and original == sorted(sources) and
          _same(mapping.get("dense_node_ids"), list(range(1, n + 1))), "PDE original/dense/native node bijection differs")

    def permutation(value, size, label):
        _need(_ids(value, label, size) == set(range(size)), label + ": exact permutation required")

    permutation(mapping.get("geometry_input_indices"), n, "PDE geometry input indices")
    _need(_same(mapping.get("geometry_source_node_ids"), [original[i] for i in mapping["geometry_input_indices"]]), "PDE geometry/source node map differs")
    _ids(mapping.get("vertex_ids"), "PDE native vertices", n)
    permutation(mapping.get("vertex_geometry_indices"), n, "PDE vertex geometry indices")
    _need(_ids(mapping.get("vertex_dof_ids"), "PDE vertex/DOF map", n) == set(field["node_ids"]), "PDE native vertex/DOF bijection differs")
    by_node = dict(zip(field["node_ids"], field["source_node_ids"]))
    _need(all(by_node[node] == mapping["geometry_source_node_ids"][i] for node, i in
              zip(mapping["vertex_dof_ids"], mapping["vertex_geometry_indices"])), "PDE original/geometry/vertex/DOF composition differs")
    permutation(mapping.get("original_cell_index"), m, "PDE original cell indices")
    _ids(mapping.get("importer_cell_source_ids"), "PDE importer source cells", m, positive=True)
    _need(_same(mapping.get("cell_ids"), field["cell_ids"]) and _same(mapping.get("source_cell_ids"), field["source_cell_ids"]) and
          _same(mapping["source_cell_ids"], [mapping["importer_cell_source_ids"][i] for i in mapping["original_cell_index"]]),
          "PDE original/importer/native cell bijection differs")
    level = ctx["input"]["mesh"]["levels"][entry["study_index"]]
    original_mesh = parse_msh(level["data"], level["sha256"])
    dense, _ = dense_import(original_mesh)
    _need(hashlib.sha256(dense.encode("ascii")).hexdigest() == mapping["dense_sha256"], "PDE dense copy differs from original source transport")
    points = {row["id"]: row["coordinates"] for row in original_mesh["nodes"]}
    original_cells = {row["id"]: set(row["node_ids"]) for row in original_mesh["cells"]}
    _need(sources == set(points) and source_cells == set(original_cells) and
          all(_same(point, points[source]) for point, source in zip(field["coordinates"], field["source_node_ids"])) and
          all({by_node[node] for node in cell} == original_cells[source] for cell, source in zip(field["cell_node_ids"], field["source_cell_ids"])),
          "PDE native geometry/connectivity differs from the exact original MSH")
    names, body = set(ctx["input"]["problem"]["boundaries"]), ctx["input"]["problem"]["domain"]["body"]
    groups = {original_mesh["body"]["name"]: {"dim": 2, "tag": original_mesh["body"]["tag"]},
              **{name: {"dim": 1, "tag": b["tag"]} for name, b in original_mesh["boundaries"].items()}}
    _need(set(groups) == names | {body} and _same(mapping.get("physical_groups"), groups) and _same(row.get("physical_groups"), groups) and
          _keys(mapping.get("boundary_source_elements"), names), "PDE original physical-group identity differs")
    for name in names:
        boundary = field["boundaries"][name]
        source_ids = boundary.get("source_element_ids")
        elements = {e["id"]: set(e["node_ids"]) for e in original_mesh["boundaries"][name]["elements"]}
        _need(_ids(source_ids, "PDE original boundary elements", len(boundary["facet_ids"]), positive=True) == set(elements) and
              _same(mapping["boundary_source_elements"][name], source_ids) and
              all({by_node[node] for node in pair} == elements[source] for pair, source in zip(boundary["facet_node_ids"], source_ids)),
              "PDE original/native boundary element mapping differs")
    weak = ctx["input"]["problem"]["weak_form"]
    _need(_same(mapping.get("gmsh_initialization"), {"argv": [], "read_config_files": False, "finalized": True}) and
          _finite(binding.get("diffusion")) and _finite(binding.get("reaction")) and
          _same(binding["diffusion"], weak["diffusion"]) and _same(binding["reaction"], weak["reaction"]) and
          _same(row.get("coefficients"), {"diffusion": binding["diffusion"], "reaction": binding["reaction"]}),
          "PDE imported native initialization/coefficient binding differs")


def _value_hash(field):
    return hashlib.sha256(json.dumps({"node_ids": field["node_ids"], "values": field["values"]},
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _mesh_identity(field):
    return {**{key: field[key] for key in ("node_ids", "coordinates", "cell_node_ids", "dirichlet_node_ids")},
            "boundaries": {name: {key: row[key] for key in ("facet_ids", "facet_node_ids", "dof_ids", "measure", "normal_integral")}
                           for name, row in field["boundaries"].items()}}


class PDEResponseFieldsAdapter:
    """Read-only registry entry, independent of native execution admission."""

    def __init__(self, backend):
        _need(backend in SUPPORTED_BACKENDS, "Unsupported PDE response reader backend")
        self.backend = backend

    @staticmethod
    def field_response_resources(result):
        _, manifest = _manifest(result)
        for path in _HEADERS.values():
            _need(path in manifest and 0 < manifest[path]["size_bytes"] <= JSON_LIMIT, "PDE native headers unavailable or oversized")
        return {role: {"path": path, "maximum_bytes": JSON_LIMIT} for role, path in _HEADERS.items()}

    @staticmethod
    def field_selection_resources(result, selection, resources):
        # Selection policy has only result+verified headers; proposal checks run
        # again in select_response_fields with the immutable Core proposal.
        proposal = {"id": result.get("experiment_id"), "study_id": result.get("study", {}).get("id"),
                    "model_revision": result.get("model_revision"), "physics": {"backend": result.get("provenance", {}).get("adapter")},
                    "execution": result.get("provenance", {}).get("execution_settings"), "cad_revision": None}
        try:
            _need(set(resources) == set(_HEADERS), "PDE selection hook requires exactly three verified headers")
            ctx = _headers(result, proposal, resources)
            entries = _entries(ctx)
            entry = _selection(ctx, entries, selection)
            return _policy(entry, entries)
        except (KeyError, TypeError, IndexError, AttributeError, OverflowError, RecursionError) as exc:
            raise ValueError("Malformed or incomplete PDE selection resource contract") from exc

    @staticmethod
    def display_response_fields(result, proposal, resources):
        try:
            _need(type(resources) is dict and set(resources) == set(_HEADERS), "PDE display needs only its three native headers")
            ctx = _headers(result, proposal, resources)
            entries = _entries(ctx)
            catalog = []
            for entry in entries:
                path = entry["files"]["dofs"]
                catalog.append({"artifact": path, "sha256": ctx["manifest"][path]["sha256"],
                                "study_index": entry["study_index"], "step_index": entry["step_index"],
                                "cells_per_axis": entry["study"].get("cells_per_axis"), "level": entry["study"].get("level"),
                                "components": ["u0", "u1"] if ctx["kind"] in ("vector", "coupled") else ["u"],
                                "unit": "1", "time": entry["row"].get("time") if ctx["kind"] == "transient" else None,
                                "solver_status": entry["row"].get("solver_status", "COMPLETED")})
            return {"kind": "pde", "model_revision": result["model_revision"], "entries": catalog,
                    "limitations": deepcopy(_LIMITATIONS), "coordinate_frame": FRAME,
                    "recorded_status": result["status"], "decision": result["decision"]}
        except (KeyError, TypeError, IndexError, AttributeError, OverflowError, RecursionError) as exc:
            raise ValueError("Malformed or incomplete PDE display contract") from exc

    @staticmethod
    def select_response_fields(result, proposal, resources, selection):
        try:
            ctx = _headers(result, proposal, resources)
            entries = _entries(ctx)
            entry = _selection(ctx, entries, selection)
            policy = _policy(entry, entries)
            _need(set(resources) == set(_HEADERS) | set(policy), "PDE selected resources differ from the bounded exact policy")
            parsed = {role: _resource(resources, role, ctx["manifest"], spec["path"])[0] for role, spec in policy.items()}
            field = parsed["dofs"]
            shape = _geometry(ctx, entry["row"], field)
            if "binding" in parsed:
                if ctx["kind"] == "coupled":
                    _coupled(ctx, entry["row"], field, parsed["binding"], shape)
                else:
                    _binding(parsed["binding"], field, shape["vector"])
            if ctx["kind"] == "imported":
                _imported(ctx, entry, field, parsed["binding"], parsed["mapping"])
            if ctx["kind"] == "transient":
                binding = parsed["time_binding"]
                _binding(binding, field, False)
                _need(_same(binding.get("time"), entry["row"]["time"]) and _value_hash(field) == entry["row"]["current_values_sha256"],
                      "PDE transient actual time/current value hash differs")
                if entry["step_index"] > 0:
                    previous_entry = next(e for e in entries if e["study_index"] == entry["study_index"] and e["step_index"] == entry["step_index"] - 1)
                    previous, previous_binding = parsed["previous_dofs"], parsed["previous_time_binding"]
                    _geometry(ctx, previous_entry["row"], previous)
                    _binding(previous_binding, previous, False)
                    _need(_same(previous_binding.get("time"), previous_entry["row"]["time"]) and
                          _value_hash(previous) == entry["row"]["previous_values_sha256"] == previous_entry["row"]["current_values_sha256"] and
                          _same(_mesh_identity(previous), _mesh_identity(field)), "PDE transient previous value/time/mesh identity differs")
            _need(selection["node_id"] in shape["nodes"], "Selected PDE native node is absent from this exact field")
            index = field["node_ids"].index(selection["node_id"])
            value = field["values"][index]
            if shape["vector"]:
                value = value[("u0", "u1").index(selection["component"])]
            source_field = {**deepcopy(selection), "coordinates": deepcopy(field["coordinates"][index]), "coordinates_unit": "1",
                            "quantity": "PDE_VECTOR_FIELD" if shape["vector"] else "PDE_SCALAR_FIELD", "coordinate_frame": FRAME,
                            "value_origin": "NATIVE_COMPONENT", "coverage": "ALL_RECORDED_P1_NATIVE_NODES",
                            "solver_status": entry["row"].get("solver_status", "COMPLETED"),
                            "cells_per_axis": entry["study"].get("cells_per_axis"), "level": entry["study"].get("level")}
            response = {"value": value, "unit": "1", "source_field": source_field,
                        "qualification": {"numeric": "RECORDED_NATIVE_VALUE", "reference": "RECORDED_DOMAIN_VERDICT_UNCHANGED",
                                          "physical": "UNKNOWN", "decision": "NOT_RELEASED"}, "alignment": "USER_DECLARED_UNVERIFIED"}
            if ctx["kind"] == "transient":
                response["response_axis"] = {"quantity": "time", "unit": "1", "value": entry["row"]["time"]}
                source_field["axis_semantics"] = "DIMENSIONLESS_MODEL_TIME"
                source_field["dt"] = entry["row"]["dt"]
                if entry["step_index"] == 0:
                    source_field["initial_state"] = {"kind": "UNINTEGRATED_INITIAL_CONDITION", "index": 0, "solver_status": "NOT_RUN"}
            else:
                source_field["axis_semantics"] = "STATIONARY_PDE; NO_TIME_AXIS"
            if ctx["kind"] == "imported":
                source_field.update(source_node_id=field["source_node_ids"][index],
                                    original_mesh_sha256=entry["row"]["source_sha256"], dense_mesh_sha256=entry["row"]["dense_sha256"],
                                    mapping_artifact=entry["files"]["mapping"], mapping_sha256=ctx["manifest"][entry["files"]["mapping"]]["sha256"])
            return response
        except (KeyError, TypeError, IndexError, AttributeError, OverflowError, RecursionError) as exc:
            raise ValueError("Malformed or incomplete retained PDE field selection contract") from exc
