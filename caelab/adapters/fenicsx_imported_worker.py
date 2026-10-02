"""Isolated imported scalar PDE worker with original/native ID bijections."""

import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys

PETSC_INIT_ARGUMENTS = ["caelab_imported_worker", "-skip_petscrc"]
SOURCE_PATHS = {
    "adapter": ("caelab/adapters/fenicsx_imported.py", "sources/fenicsx_imported.py"),
    "worker": ("caelab/adapters/fenicsx_imported_worker.py", "worker.py"),
    "mesh_syntax": ("caelab/adapters/fenicsx_gmsh.py", "mesh_syntax.py"),
    "domain_reference": ("plugins/pde_imported/reference.py", "imported_reference.py"),
    "rectangle_domain_reference": ("plugins/pde_elliptic/reference.py", "domain_reference.py"),
    "expression_parser": ("caelab/adapters/fenicsx_worker.py", "fenicsx_expression.py"),
    "rectangle_adapter": ("caelab/adapters/fenicsx_rectangle.py", "sources/fenicsx_rectangle.py"),
    "rectangle_worker": ("caelab/adapters/fenicsx_rectangle_worker.py", "rectangle_worker.py"),
    "vector_worker_helper": ("caelab/adapters/fenicsx_vector_worker.py", "vector_worker.py"),
    "execution_control": ("caelab/execution_control.py", "sources/execution_control.py"),
}


def _verified_helpers(output):
    manifest_path = output / "source_manifest.json"
    if not manifest_path.is_file() or any(path.is_symlink() for path in (manifest_path, *manifest_path.parents)):
        raise RuntimeError("Imported source manifest path is not a regular contained file")
    raw = manifest_path.read_bytes()
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise RuntimeError("Duplicate imported source manifest member")
            result[key] = value
        return result
    manifest = json.loads(raw, object_pairs_hook=unique)
    if (not isinstance(manifest, dict) or set(manifest) != {"schema_version", "domain_plugin_version", "files"} or manifest["schema_version"] != "1" or
            manifest["domain_plugin_version"] != "1" or not isinstance(manifest["files"], dict) or set(manifest["files"]) != set(SOURCE_PATHS)):
        raise RuntimeError("Imported source manifest contract mismatch")
    for key, (repository_path, relative) in SOURCE_PATHS.items():
        row, path = manifest["files"][key], output / relative
        if (not isinstance(row, dict) or set(row) != {"repository_path", "copied_path", "sha256"} or row["repository_path"] != repository_path or row["copied_path"] != relative or
                not isinstance(row["sha256"], str) or len(row["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in row["sha256"]) or
                not path.resolve().is_relative_to(output.resolve()) or not path.is_file() or any(part.is_symlink() for part in (path, *path.parents)) or
                hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]):
            raise RuntimeError("Imported copied source identity mismatch")
    if __package__:
        from . import fenicsx_rectangle_worker as helpers, fenicsx_vector_worker as vector, fenicsx_gmsh as syntax, fenicsx_worker as expression
        from plugins.pde_imported import reference as domain
    else:
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(output))
        import rectangle_worker as helpers
        import vector_worker as vector
        import mesh_syntax as syntax
        import fenicsx_expression as expression
        import imported_reference as domain
    if helpers._read_json(helpers._regular_file(output, "source_manifest.json")) != manifest:
        raise RuntimeError("Imported source manifest changed during bootstrap")
    return helpers, vector, syntax, expression, domain, hashlib.sha256(raw).hexdigest()


def _import_native(level, table, helpers, gmsh, importer, comm):
    """Only a contained verified derived file is merged; owned API always closes."""
    if gmsh.isInitialized(): raise RuntimeError("Imported worker cannot adopt a preinitialized Gmsh instance")
    initialization = {"argv": [], "read_config_files": False, "finalized": False}
    partial = {"schema_version": "1", **table, "gmsh_initialization": initialization}
    helpers._save_json(level / "import_mapping.json", partial)
    try:
        gmsh.initialize([], readConfigFiles=False)
        if not gmsh.isInitialized(): raise RuntimeError("Owned Gmsh initialization did not succeed")
        gmsh.merge(str(helpers._regular_file(level, "dense-import.msh")))
        topologies, physical_groups = importer.extract_topology_and_markers(gmsh.model)
        if set(topologies) != {1, 2}: raise RuntimeError("Actual imported element types differ from linear lines/triangles")
        captured = {kind: {key: value.copy() for key, value in row.items()} for kind, row in topologies.items()}
        version = gmsh.option.getString("General.Version")
        if not isinstance(version, str) or not version.strip(): raise RuntimeError("Actual Gmsh version unavailable")
        data = importer.model_to_mesh(gmsh.model, comm, 0, gdim=2)
        if data.physical_groups != physical_groups: raise RuntimeError("Gmsh physical name map changed during import")
        return data, captured, version, initialization
    finally:
        if gmsh.isInitialized(): gmsh.finalize()
        initialization["finalized"] = gmsh.isInitialized() == 0
        helpers._save_json(level / "import_mapping.json", partial)
        if not initialization["finalized"]: raise RuntimeError("Owned Gmsh finalization unconfirmed")


def _native_mapping(data, captured, source, table, space, fem, mesh, importer, np):
    """Observe actual maps; no equality between unrelated native index spaces."""
    native = data.mesh
    for a, b in ((0, 2), (2, 0), (1, 2), (1, 0), (2, 1)):
        native.topology.create_connectivity(a, b)
    size, count = len(source["nodes"]), len(source["cells"])
    vertex_map, cell_map = native.topology.index_map(0), native.topology.index_map(2)
    geometry_map, dof_map = native.geometry.index_map(), space.dofmap.index_map
    if any(index.size_local != expected or index.size_global != expected or index.num_ghosts != 0 for index, expected in ((vertex_map, size), (cell_map, count), (geometry_map, size), (dof_map, size))):
        raise RuntimeError("Actual serial imported geometry/vertex/cell/DOF counts or ghosts differ")
    coordinates = space.tabulate_dof_coordinates()
    if space.dofmap.bs != 1 or space.dofmap.index_map_bs != 1 or coordinates.shape != (size, 3) or not np.all(np.isfinite(coordinates)) or not np.all(coordinates[:, 2] == 0):
        raise RuntimeError("Actual imported scalar P1 layout or planar coordinates differ")
    ids = dof_map.local_to_global(np.arange(size, dtype=np.int32))
    cells = cell_map.local_to_global(np.arange(count, dtype=np.int32))
    vertices = vertex_map.local_to_global(np.arange(size, dtype=np.int32))
    input_indices = native.geometry.input_global_indices
    if any(set(map(int, values)) != set(range(expected)) or len(values) != expected for values, expected in ((ids, size), (cells, count), (vertices, size), (input_indices, size))):
        raise RuntimeError("Actual native serial IDs/input geometry are not full bijections")
    original = table["original_node_ids"]
    geometry_source = [original[int(index)] for index in input_indices]
    expected_xyz = {row["id"]: row["coordinates"] for row in source["nodes"]}
    for index, identifier in enumerate(geometry_source):
        if not np.allclose(native.geometry.x[index, :2], expected_xyz[identifier], rtol=1e-12, atol=1e-12) or native.geometry.x[index, 2] != 0:
            raise RuntimeError("Actual imported geometry differs from original source coordinates")
    vertex_geometry = mesh.entities_to_geometry(native, 0, np.arange(size, dtype=np.int32))
    if vertex_geometry.shape != (size, 1) or set(map(int, vertex_geometry[:, 0])) != set(range(size)):
        raise RuntimeError("Actual native vertex/geometry map is not bijective")
    vertex_dofs, dof_source = [], [None]*size
    for vertex, geometry_index in enumerate(vertex_geometry[:, 0]):
        located = fem.locate_dofs_topological(space, 0, np.array([vertex], dtype=np.int32), remote=False)
        if len(located) != 1: raise RuntimeError("Actual P1 vertex does not own exactly one scalar DOF")
        dof = int(located[0])
        if not 0 <= dof < size or dof_source[dof] is not None or not np.allclose(coordinates[dof, :2], native.geometry.x[geometry_index, :2], rtol=1e-12, atol=1e-12):
            raise RuntimeError("Actual vertex/DOF geometry map is inconsistent or duplicate")
        dof_source[dof] = geometry_source[int(geometry_index)]
        vertex_dofs.append(int(ids[dof]))
    if set(dof_source) != set(original): raise RuntimeError("Actual source/DOF mapping incomplete")
    rows = native.topology.original_cell_index
    importer_ids = captured[2]["entity_tags"]
    if len(rows) != count or set(map(int, rows)) != set(range(count)) or len(importer_ids) != count or set(map(int, importer_ids)) != {row["id"] for row in source["cells"]}:
        raise RuntimeError("Actual importer/native cell row mapping incomplete")
    source_cells = {row["id"]: row for row in source["cells"]}
    permutation = importer.cell_perm_array(mesh.CellType.triangle, 3)
    cell_source, cell_nodes, largest = [], [], 0.
    for cell in range(count):
        row = int(rows[cell])
        identifier = int(importer_ids[row])
        expected = [original[int(index)] for index in captured[2]["topology"][row][permutation]]
        geometry_indices = native.geometry.dofmap[cell]
        actual = [geometry_source[int(index)] for index in geometry_indices]
        dofs = space.dofmap.cell_dofs(cell)
        if len(actual) != 3 or actual != expected or set(actual) != set(source_cells[identifier]["node_ids"]) or [dof_source[int(dof)] for dof in dofs] != actual:
            raise RuntimeError("Actual native cell/geometry/DOF order differs from captured importer and original source")
        cell_source.append(identifier)
        cell_nodes.append([int(ids[int(dof)]) for dof in dofs])
        largest = max(largest, *(float(np.linalg.norm(native.geometry.x[a, :2]-native.geometry.x[b, :2])) for a, b in zip(geometry_indices, list(geometry_indices[1:])+[geometry_indices[0]])))
    expected_groups = {source["body"]["name"]: {"dim": 2, "tag": source["body"]["tag"]}, **{name: {"dim": 1, "tag": row["tag"]} for name, row in source["boundaries"].items()}}
    groups = {name: {"dim": int(row.dim), "tag": int(row.tag)} for name, row in data.physical_groups.items()}
    if groups != expected_groups or data.cell_tags is None or data.facet_tags is None or data.ridge_tags is not None or data.peak_tags is not None:
        raise RuntimeError("Actual native physical names/dimensions/tags differ")
    if set(map(int, data.cell_tags.indices)) != set(range(count)) or len(data.cell_tags.indices) != count or not np.all(data.cell_tags.values == source["body"]["tag"]):
        raise RuntimeError("Actual native body cell tag coverage differs")
    facet_map = native.topology.index_map(1)
    if facet_map.num_ghosts or facet_map.size_local != facet_map.size_global: raise RuntimeError("Actual native facets are not serial and ghost-free")
    exterior = set(map(int, mesh.exterior_facet_indices(native.topology)))
    if set(map(int, data.facet_tags.indices)) != exterior or len(data.facet_tags.indices) != len(exterior):
        raise RuntimeError("Actual imported facet tags do not partition the complete exterior")
    facets, dofs, endpoints, boundary_sources, seen = {}, {}, {}, {}, set()
    for name, group in sorted(source["boundaries"].items()):
        local = data.facet_tags.indices[data.facet_tags.values == group["tag"]]
        local = np.asarray(sorted(local, key=lambda i: int(facet_map.local_to_global(np.array([i], dtype=np.int32))[0])), dtype=np.int32)
        by_edge = {tuple(sorted(row["node_ids"])): row["id"] for row in group["elements"]}
        boundary_sources[name], endpoints[name] = [], []
        for facet in local:
            geometry_pair = mesh.entities_to_geometry(native, 1, np.array([facet], dtype=np.int32))[0]
            pair = fem.locate_dofs_topological(space, 1, np.array([facet], dtype=np.int32), remote=False)
            key = tuple(sorted(geometry_source[int(index)] for index in geometry_pair))
            if len(geometry_pair) != 2 or len(pair) != 2 or key not in by_edge or {dof_source[int(node)] for node in pair} != set(key) or by_edge[key] in seen:
                raise RuntimeError("Actual physical facet endpoints do not biject to original source line elements")
            seen.add(by_edge[key])
            boundary_sources[name].append(by_edge[key])
            endpoints[name].append([int(ids[int(node)]) for node in pair])
        if set(boundary_sources[name]) != set(by_edge.values()): raise RuntimeError("Actual named physical boundary coverage incomplete")
        facets[name] = local
        dofs[name] = np.asarray(sorted(fem.locate_dofs_topological(space, 1, local, remote=False), key=lambda i: ids[i]), dtype=np.int32)
    mapping = {"schema_version": "1", **table, "geometry_input_indices": [int(i) for i in input_indices], "geometry_source_node_ids": geometry_source,
               "vertex_ids": [int(i) for i in vertices], "vertex_geometry_indices": [int(i) for i in vertex_geometry[:, 0]], "vertex_dof_ids": vertex_dofs,
               "cell_ids": [int(i) for i in cells], "original_cell_index": [int(i) for i in rows], "importer_cell_source_ids": [int(i) for i in importer_ids],
               "source_cell_ids": cell_source, "physical_groups": groups, "boundary_source_elements": boundary_sources}
    return {"mapping": mapping, "ids": ids, "coordinates": coordinates, "dof_source_ids": dof_source, "cell_node_ids": cell_nodes,
            "facets": facets, "dofs": dofs, "endpoints": endpoints, "max_edge_h": largest}


def _native_forms(native, space, data, settings, expression, helpers, fem, PETSc, ufl):
    problem, weak = settings["problem"], settings["problem"]["weak_form"]
    x, u, v = ufl.SpatialCoordinate(native), ufl.TrialFunction(space), ufl.TestFunction(space)
    functions = {name: getattr(ufl, name) for name in expression.FUNCTION_NAMES}
    def scalar(source):
        return helpers._native_scalar(expression.interpret_expression(expression.parse_expression(source), x, functions), native, fem, PETSc.ScalarType, ufl)
    k, c = fem.Constant(native, PETSc.ScalarType(weak["diffusion"])), fem.Constant(native, PETSc.ScalarType(weak["reaction"]))
    dx = ufl.Measure("dx", domain=native, subdomain_data=data.cell_tags, metadata={"quadrature_degree": 8})
    ds = ufl.Measure("ds", domain=native, subdomain_data=data.facet_tags, metadata={"quadrature_degree": 8})
    body_tag = data.physical_groups[problem["domain"]["body"]].tag
    a = (k*ufl.inner(ufl.grad(u), ufl.grad(v))+c*u*v)*dx(body_tag)
    rhs, reference = scalar(weak["rhs"]), scalar(problem["reference"]["solution"])
    L, sides = rhs*v*dx(body_tag), {}
    for name, boundary in problem["boundaries"].items():
        sides[name] = scalar(boundary["value"])
        if boundary["type"] == "neumann": L += sides[name]*v*ds(data.physical_groups[name].tag)
    return {"a": a, "L": L, "reference": reference, "side_expressions": sides, "diffusion": k, "reaction": c, "dx": dx, "ds": ds, "body_tag": body_tag}


def _dirichlet_function(space, tags, problem, coordinates, ids, numeric, fem, np):
    """Assign only each declared physical group's actual scalar DOFs."""
    function, assigned = fem.Function(space), set()
    union = np.asarray(sorted({int(node) for name, nodes in tags["dofs"].items() if problem["boundaries"][name]["type"] == "dirichlet" for node in nodes}, key=lambda node: ids[node]), dtype=np.int32)
    for name, nodes in tags["dofs"].items():
        if problem["boundaries"][name]["type"] != "dirichlet": continue
        prescribed = numeric(problem["boundaries"][name]["value"], coordinates[nodes].T)
        for node, value in zip(nodes, prescribed):
            if int(node) in assigned and not math.isclose(float(function.x.array[node]), float(value), rel_tol=1e-12, abs_tol=1e-12):
                raise RuntimeError("Actual shared Dirichlet scalar assignments conflict")
            function.x.array[node] = value
            assigned.add(int(node))
    function.x.scatter_forward()
    return function, union


def run_worker(input_path):
    input_path = Path(input_path).resolve()
    output = input_path.parent
    helpers, vector, syntax, expression, domain, manifest_sha = _verified_helpers(output)
    spec_sha = helpers._sha(helpers._regular_file(output, "input.json"))
    settings = helpers._read_json(input_path)
    sources = syntax.prepare(settings)
    settings = domain.validate_settings(settings, sources)
    for name in ("PETSC_OPTIONS", "PETSC_OPTIONS_YAML"): os.environ.pop(name, None)
    import petsc4py
    petsc4py.init(PETSC_INIT_ARGUMENTS)
    from petsc4py import PETSc
    options = PETSc.Options().getAll()
    if options != {"skip_petscrc": None} or PETSc.Options().getBool("skip_petscrc") is not True: raise RuntimeError("Imported PETSc bootstrap admits ambient options")
    initialization = {"argv": PETSC_INIT_ARGUMENTS, "options": options, "petsc_rc_disabled": True, "ambient_options_removed": ["PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]}
    helpers._save_json(output / "petsc_initialization.json", initialization)
    import basix
    import dolfinx
    from dolfinx import fem, io, mesh
    from dolfinx.io import gmsh as importer
    from dolfinx.fem.petsc import LinearProblem
    import ffcx
    import gmsh
    import mpi4py
    from mpi4py import MPI
    import numpy as np
    import ufl
    comm = MPI.COMM_WORLD
    if comm.size != 1 or np.dtype(PETSc.ScalarType) != np.dtype("float64") or np.dtype(PETSc.RealType) != np.dtype("float64"):
        raise RuntimeError("Imported PDE supports serial real64 native execution only")
    versions = {"python": platform.python_version(), "dolfinx": dolfinx.__version__, "ufl": ufl.__version__, "basix": basix.__version__, "ffcx": ffcx.__version__,
                "petsc4py": petsc4py.__version__, "petsc": ".".join(map(str, PETSc.Sys.getVersion())), "mpi4py": mpi4py.__version__, "numpy": np.__version__}
    weak, problem = settings["problem"]["weak_form"], settings["problem"]
    numpy_functions = {name: getattr(np, name) for name in expression.FUNCTION_NAMES}
    def checked(value, label, nonnegative=False):
        result = float(value)
        if not expression.finite_number(result, nonnegative=nonnegative): raise RuntimeError("Nonfinite/invalid native imported observation: "+label)
        return result
    def numeric(source, coordinates):
        with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
            result = expression.interpret_expression(expression.parse_expression(source), coordinates, numpy_functions)
        values = np.broadcast_to(np.asarray(result, dtype=PETSc.ScalarType), coordinates.shape[1]).copy()
        if not np.all(np.isfinite(values)): raise RuntimeError("Nonfinite actual scalar expression values")
        return values
    def files(i):
        return {key: f"level_{i}/{name}" for key, name in {"original": "original.msh", "dense": "dense-import.msh", "mapping": "import_mapping.json", "field": "field.xdmf", "field_data": "field.h5", "form_source": "forms.ufl.txt", "dofs": "dofs.json", "binding": "binding.json"}.items()}
    def verify():
        if helpers._sha(input_path) != spec_sha or _verified_helpers(output)[-1] != manifest_sha: raise RuntimeError("Imported frozen input/source drift during native work")
    studies, completed = [], []
    helpers._save_json(output / "progress.json", {"schema_version": "1", "status": "RUNNING", "completed": completed})
    for i, (source, level_spec) in enumerate(zip(sources, settings["mesh"]["levels"])):
        verify()
        paths, level = files(i), output / f"level_{i}"
        dense, table = syntax.dense_import(source)
        if helpers._regular_file(level, "original.msh").read_bytes() != level_spec["data"].encode("ascii") or helpers._regular_file(level, "dense-import.msh").read_bytes() != dense.encode("ascii"):
            raise RuntimeError("Original or derived mesh input bytes changed before native import")
        data, captured, gmsh_version, gmsh_initialization = _import_native(level, table, helpers, gmsh, importer, comm)
        if "gmsh" in versions and versions["gmsh"] != gmsh_version: raise RuntimeError("Actual Gmsh version changed between levels")
        versions["gmsh"] = gmsh_version
        native = data.mesh
        space = fem.functionspace(native, ("Lagrange", 1))
        tags = _native_mapping(data, captured, source, table, space, fem, mesh, importer, np)
        mapping = {**tags["mapping"], "gmsh_initialization": gmsh_initialization}
        helpers._save_json(level / "import_mapping.json", mapping)
        ids, coordinates = tags["ids"], tags["coordinates"]
        size, order = len(ids), np.argsort(ids)
        boundary_function, union = _dirichlet_function(space, tags, problem, coordinates, ids, numeric, fem, np)
        bc = fem.dirichletbc(boundary_function, union)
        forms = _native_forms(native, space, data, settings, expression, helpers, fem, PETSc, ufl)
        linear = LinearProblem(forms["a"], forms["L"], bcs=[bc], petsc_options_prefix=f"caelab_imported_{i}_", petsc_options=helpers.NATIVE_OPTIONS)
        uh = linear.solve()
        uh.x.scatter_forward()
        uh.name = "u"
        if len(uh.x.array) != size: raise RuntimeError("Actual scalar solution layout differs")
        synchronization, synchronized = vector._solution_synchronization(linear.x.getArray(readonly=True), uh.x.array, np)
        values = [checked(uh.x.array[node], "scalar DOF") for node in order]
        policy = {"ksp_type": linear.solver.getType(), "pc_type": linear.solver.getPC().getType()}
        if policy != {"ksp_type": "preonly", "pc_type": "lu"}: raise RuntimeError("Actual imported solver policy differs")
        residual = linear.b.duplicate()
        try:
            linear.A.mult(linear.x, residual)
            residual.axpy(-1., linear.b)
            absolute, rhs_norm = checked(residual.norm(), "constrained residual", True), checked(linear.b.norm(), "actual RHS norm", True)
        finally: residual.destroy()
        residual_record = {"absolute": absolute, "rhs_norm": rhs_norm, "relative": checked(absolute/rhs_norm if rhs_norm else absolute, "relative residual", True), "normalization": "rhs_l2_norm" if rhs_norm else "absolute_for_zero_rhs"}
        error = uh-forms["reference"]
        l2 = math.sqrt(checked(fem.assemble_scalar(fem.form(error*error*forms["dx"](forms["body_tag"]))), "symbolic L2 square", True))
        h1 = math.sqrt(checked(fem.assemble_scalar(fem.form(ufl.inner(ufl.grad(error), ufl.grad(error))*forms["dx"](forms["body_tag"]))), "full-gradient error square", True))
        normal, boundaries = ufl.FacetNormal(native), {}
        facet_map = native.topology.index_map(1)
        for name, facets in tags["facets"].items():
            nodes, tag = tags["dofs"][name], data.physical_groups[name].tag
            boundaries[name] = {"facet_ids": [int(value) for value in facet_map.local_to_global(facets)], "facet_node_ids": tags["endpoints"][name], "dof_ids": [int(ids[node]) for node in nodes],
                "measure": checked(fem.assemble_scalar(fem.form(1.*forms["ds"](tag))), "actual group measure", True),
                "normal_integral": [checked(fem.assemble_scalar(fem.form(normal[axis]*forms["ds"](tag))), "actual group outward normal") for axis in (0, 1)],
                "prescribed_values": [checked(value, "actual boundary input") for value in numeric(problem["boundaries"][name]["value"], coordinates[nodes].T)],
                "prescribed_integral": checked(fem.assemble_scalar(fem.form(forms["side_expressions"][name]*forms["ds"](tag))), "actual boundary input integral"),
                "source_element_ids": mapping["boundary_source_elements"][name]}
        node_ids, source_ids = [int(ids[node]) for node in order], [tags["dof_source_ids"][node] for node in order]
        field = {"schema_version": "1", "coordinates_unit": "1", "field_unit": "1", "node_ids": node_ids, "coordinates": [[checked(value, "actual coordinate") for value in coordinates[node, :2]] for node in order],
                 "values": values, "source_node_ids": source_ids, "cell_ids": mapping["cell_ids"], "source_cell_ids": mapping["source_cell_ids"], "cell_node_ids": tags["cell_node_ids"],
                 "dirichlet_node_ids": sorted(int(ids[node]) for node in union), "boundaries": boundaries}
        coefficients = {"diffusion": checked(forms["diffusion"].value, "actual diffusion Constant"), "reaction": checked(forms["reaction"].value, "actual reaction Constant")}
        binding = {"schema_version": "1", "source_sha256": source["source_sha256"], "dense_sha256": table["dense_sha256"], "node_ids": node_ids, "source_node_ids": source_ids, **coefficients,
                   "rhs_values": [checked(value, "actual RHS input") for value in numeric(weak["rhs"], coordinates[order].T)],
                   "reference_values": [checked(value, "actual reference input") for value in numeric(problem["reference"]["solution"], coordinates[order].T)]}
        helpers._save_json(level / "dofs.json", field)
        helpers._save_json(level / "binding.json", binding)
        with io.XDMFFile(comm, str(level / "field.xdmf"), "w") as writer:
            writer.write_mesh(native)
            writer.write_function(uh)
        (level / "forms.ufl.txt").write_text(f"a = {forms['a']}\nL = {forms['L']}\nreference = {forms['reference']}\nerror_quadrature_degree = 8\n", encoding="utf-8")
        largest = checked(tags["max_edge_h"], "actual maximum triangle edge", True)
        boundary_error = checked(np.max(np.abs(uh.x.array[union]-boundary_function.x.array[union])), "actual Dirichlet field error", True)
        study = {"level": i, "degree": 1, "cell_type": "triangle", "max_edge_h": largest, "global_cells": native.topology.index_map(2).size_global,
            "global_nodes": native.topology.index_map(0).size_global, "global_dofs": space.dofmap.index_map.size_global, "dirichlet_nodes": len(union), "dirichlet_dofs": len(union),
            "boundary_value_error": boundary_error, "l2_error": l2, "h1_seminorm_error": h1,
            "l2_convergence_rate": domain.convergence_rate(studies[-1]["l2_error"], l2, studies[-1]["max_edge_h"], largest) if studies else None,
            "h1_seminorm_convergence_rate": domain.convergence_rate(studies[-1]["h1_seminorm_error"], h1, studies[-1]["max_edge_h"], largest) if studies else None,
            "linear_residual": residual_record, "ksp_convergence_reason": int(linear.solver.getConvergedReason()), "ksp_iterations": int(linear.solver.getIterationNumber()), "solver_policy": policy,
            "solution_synchronization": {"max_abs_difference": synchronization, "passed": synchronized}, "physical_groups": mapping["physical_groups"], "coefficients": coefficients,
            "source_sha256": source["source_sha256"], "dense_sha256": table["dense_sha256"], "files": paths, "artifact_sha256": {key: helpers._sha(output / relative) for key, relative in paths.items()}}
        helpers._save_json(level / "observation.json", study)
        if not synchronized: raise RuntimeError("Actual constrained x/saved scalar Function differ; partial fields and observation retained")
        studies.append(study)
        completed.append({"level": i})
        helpers._save_json(output / "progress.json", {"schema_version": "1", "status": "RUNNING", "completed": completed})
    verify()
    helpers._save_json(output / "progress.json", {"schema_version": "1", "status": "COMPLETED", "completed": completed})
    result = {"schema_version": "1", "status": "COMPLETED", "spec_sha256": spec_sha, "source_manifest_sha256": manifest_sha, "mpi_size": comm.size, "scalar_type": "float64",
              "versions": versions, "petsc_initialization": initialization, "petsc_initialization_sha256": helpers._sha(output / "petsc_initialization.json"), "mesh_studies": studies}
    helpers._save_json(output / "worker_result.json", result)
    print(json.dumps({"status": "COMPLETED", "mesh_levels": len(studies), "versions": versions}, allow_nan=False))
    return result


if __name__ == "__main__":
    if len(sys.argv) != 2: raise SystemExit("Usage: imported worker input.json")
    run_worker(sys.argv[1])
