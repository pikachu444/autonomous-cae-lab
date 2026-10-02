"""Isolated conforming component-axis coupled diffusion worker and observations."""

import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys

PETSC_INIT_ARGUMENTS = ["caelab_coupled_worker", "-skip_petscrc"]
SOURCE_PATHS = {"adapter": ("caelab/adapters/fenicsx_coupled.py", "sources/fenicsx_coupled.py"),
    "worker": ("caelab/adapters/fenicsx_coupled_worker.py", "worker.py"),
    "domain_reference": ("plugins/pde_coupled/reference.py", "coupled_reference.py"),
    "rectangle_domain_reference": ("plugins/pde_elliptic/reference.py", "domain_reference.py"),
    "expression_parser": ("caelab/adapters/fenicsx_worker.py", "fenicsx_expression.py"),
    "rectangle_adapter": ("caelab/adapters/fenicsx_rectangle.py", "sources/fenicsx_rectangle.py"),
    "rectangle_worker": ("caelab/adapters/fenicsx_rectangle_worker.py", "rectangle_worker.py"),
    "execution_control": ("caelab/execution_control.py", "sources/execution_control.py"),
    "vector_worker_helper": ("caelab/adapters/fenicsx_vector_worker.py", "vector_worker.py")}
SEGMENT_TAGS = {"xmin": {"left": 11}, "xmax": {"right": 21}, "ymin": {"left": 31, "right": 32}, "ymax": {"left": 41, "right": 42}}


def _verified_helpers(output):
    manifest_path = output / "source_manifest.json"
    if any(part.is_symlink() for part in (manifest_path, *manifest_path.parents)): raise RuntimeError("Coupled manifest path is a symbolic link")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if (not isinstance(manifest, dict) or set(manifest) != {"schema_version", "domain_plugin_version", "files"} or manifest["schema_version"] != "1" or
            manifest["domain_plugin_version"] != "1" or not isinstance(manifest["files"], dict) or set(manifest["files"]) != set(SOURCE_PATHS)):
        raise RuntimeError("Coupled saved source manifest contract mismatch")
    for key, (repository_path, relative) in SOURCE_PATHS.items():
        row, path = manifest["files"][key], output / relative
        if (not isinstance(row, dict) or set(row) != {"repository_path", "copied_path", "sha256"} or row["repository_path"] != repository_path or row["copied_path"] != relative or
                not path.resolve().is_relative_to(output.resolve()) or not path.is_file() or any(part.is_symlink() for part in (path, *path.parents)) or
                hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]): raise RuntimeError("Coupled copied source identity mismatch")
    if __package__:
        from . import fenicsx_rectangle_worker as helpers
        from . import fenicsx_vector_worker as vector
    else:
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(output))
        import rectangle_worker as helpers
        import vector_worker as vector
    if helpers._read_json(helpers._regular_file(output, "source_manifest.json")) != manifest: raise RuntimeError("Coupled source manifest changed during bootstrap")
    return helpers, vector, hashlib.sha256(manifest_bytes).hexdigest()


def _tagged_mesh(rectangle, space, ids, n, lx, ly, mesh, fem, np):
    """Actual entities/adjacency only. No solution, reference or material verdict."""
    rectangle.topology.create_connectivity(1, 2)
    cells = np.arange(rectangle.topology.index_map(2).size_local, dtype=np.int32)
    global_cells = rectangle.topology.index_map(2).local_to_global(cells)
    centers = mesh.compute_midpoints(rectangle, 2, cells)
    region_indices = {region: cells[centers[:, 0] < lx/2] if region == "left" else cells[centers[:, 0] > lx/2] for region in ("left", "right")}
    if any(len(indices) != n*n for indices in region_indices.values()) or sum(map(len, region_indices.values())) != len(cells): raise RuntimeError("Native midpoint region partition incomplete")
    cell_values = np.where(centers[:, 0] < lx/2, 1, 2).astype(np.int32)
    cell_tags = mesh.meshtags(rectangle, 2, cells, cell_values)
    cell_nodes = [[int(ids[node]) for node in space.dofmap.cell_dofs(cell)] for cell in cells]
    node_indices = {region: np.array(sorted({int(node) for cell in indices for node in space.dofmap.cell_dofs(cell)}, key=lambda node: ids[node]), dtype=np.int32) for region, indices in region_indices.items()}
    facet_map = rectangle.topology.index_map(1)
    facets, dofs, all_facets, all_tags = {}, {}, [], []
    for side, axis, bound in (("xmin", 0, 0.), ("xmax", 0, lx), ("ymin", 1, 0.), ("ymax", 1, ly)):
        whole = np.sort(mesh.locate_entities_boundary(rectangle, 1, lambda x, axis=axis, bound=bound: np.isclose(x[axis], bound, rtol=1e-12, atol=1e-12)))
        midpoints = mesh.compute_midpoints(rectangle, 1, whole)
        facets[side], dofs[side] = {}, {}
        for region, tag in SEGMENT_TAGS[side].items():
            segment = whole if axis == 0 else whole[midpoints[:, 0] < lx/2] if region == "left" else whole[midpoints[:, 0] > lx/2]
            segment = np.asarray(sorted(segment, key=lambda facet: facet_map.local_to_global(np.array([facet], dtype=np.int32))[0]), dtype=np.int32)
            if len(segment) != (n if axis == 0 else n//2): raise RuntimeError("Native exterior segment coverage incomplete")
            facets[side][region] = segment
            dofs[side][region] = np.asarray(sorted(fem.locate_dofs_topological(space, 1, segment), key=lambda node: ids[node]), dtype=np.int32)
            all_facets.extend(int(facet) for facet in segment)
            all_tags.extend([tag]*len(segment))
    if len(all_facets) != len(set(all_facets)) or not np.array_equal(np.sort(all_facets), np.sort(mesh.exterior_facet_indices(rectangle.topology))): raise RuntimeError("Native split exterior tags overlap/omit facets")
    order = np.argsort(all_facets)
    facet_tags = mesh.meshtags(rectangle, 1, np.asarray(all_facets, dtype=np.int32)[order], np.asarray(all_tags, dtype=np.int32)[order])
    interface_facets = mesh.locate_entities(rectangle, 1, lambda x: np.isclose(x[0], lx/2, rtol=1e-12, atol=1e-12))
    interface_facets = np.asarray(sorted(interface_facets, key=lambda facet: facet_map.local_to_global(np.array([facet], dtype=np.int32))[0]), dtype=np.int32)
    if len(interface_facets) != n or set(map(int, interface_facets)) & set(all_facets): raise RuntimeError("Native interface facets missing or exterior")
    connectivity = rectangle.topology.connectivity(1, 2)
    endpoints, neighbours, interface_nodes, measure = [], [], set(), 0.
    coordinates = space.tabulate_dof_coordinates()
    for facet in interface_facets:
        pair = fem.locate_dofs_topological(space, 1, np.array([facet], dtype=np.int32))
        connected = connectivity.links(facet)
        if len(pair) != 2 or len(connected) != 2: raise RuntimeError("Native interface adjacency is not an internal edge")
        by_region = {"left" if cell_values[cell] == 1 else "right": int(global_cells[cell]) for cell in connected}
        if set(by_region) != {"left", "right"}: raise RuntimeError("Native interface does not join opposite material regions")
        endpoints.append([int(ids[node]) for node in pair])
        neighbours.append([by_region["left"], by_region["right"]])
        interface_nodes.update(int(ids[node]) for node in pair)
        measure += float(np.linalg.norm(coordinates[pair[1], :2]-coordinates[pair[0], :2]))
    if len(interface_nodes) != n+1 or not math.isclose(measure, ly, rel_tol=1e-12, abs_tol=1e-12): raise RuntimeError("Native interface node/measure coverage incomplete")
    interface = {"facet_ids": [int(value) for value in facet_map.local_to_global(interface_facets)], "facet_node_ids": endpoints,
                 "node_ids": sorted(interface_nodes), "adjacent_cell_ids": neighbours, "measure": measure, "plus_x_normal": [1., 0.]}
    return {"cell_tags": cell_tags, "facet_tags": facet_tags, "cell_indices": region_indices, "node_indices": node_indices,
            "cell_ids": [int(value) for value in global_cells], "cell_regions": ["left" if value == 1 else "right" for value in cell_values],
            "cell_node_ids": cell_nodes, "facets": facets, "dofs": dofs, "interface": interface}


def _native_forms(rectangle, space, tags, settings, trees, expression, helpers, vector, fem, PETSc, np, ufl):
    weak = settings["problem"]["weak_form"]
    diffusion = {region: fem.Constant(rectangle, np.asarray(weak["diffusion"][region], dtype=PETSc.ScalarType)) for region in ("left", "right")}
    reaction = fem.Constant(rectangle, np.asarray(weak["reaction"], dtype=PETSc.ScalarType))
    x, u, v = ufl.SpatialCoordinate(rectangle), ufl.TrialFunction(space), ufl.TestFunction(space)
    functions = {name: getattr(ufl, name) for name in expression.FUNCTION_NAMES}
    dx = ufl.Measure("dx", domain=rectangle, subdomain_data=tags["cell_tags"], metadata={"quadrature_degree": 8})
    ds = ufl.Measure("ds", domain=rectangle, subdomain_data=tags["facet_tags"], metadata={"quadrature_degree": 8})
    a, L, references, side_expressions = None, None, {}, {}
    for region, tag in (("left", 1), ("right", 2)):
        rhs = vector._native_vector([expression.interpret_expression(tree, x, functions) for tree in trees["rhs"][region]], rectangle, fem, PETSc.ScalarType, ufl, helpers)
        references[region] = ufl.as_vector([expression.interpret_expression(tree, x, functions) for tree in trees["reference"][region]])
        contribution = (ufl.inner(ufl.dot(diffusion[region], ufl.grad(u)), ufl.grad(v))+ufl.inner(ufl.dot(reaction, u), v))*dx(tag)
        load = ufl.inner(rhs, v)*dx(tag)
        a, L = (contribution, load) if a is None else (a+contribution, L+load)
    for side, segments in SEGMENT_TAGS.items():
        side_expressions[side] = {}
        for region, tag in segments.items():
            value = vector._native_vector([expression.interpret_expression(tree, x, functions) for tree in trees["boundaries"][side][region]], rectangle, fem, PETSc.ScalarType, ufl, helpers)
            side_expressions[side][region] = value
            if settings["problem"]["boundaries"][side]["type"] == "neumann": L += ufl.inner(value, v)*ds(tag)
    return {"a": a, "L": L, "references": references, "side_expressions": side_expressions, "diffusion": diffusion, "reaction": reaction, "dx": dx, "ds": ds}


def _interpolate_boundary(function, parsed, side, region, lengths, numeric, np):
    """Only declared segment coordinates may evaluate its expression strings."""
    lx, ly = lengths
    axis, bound = (0, 0.) if side == "xmin" else (0, lx) if side == "xmax" else (1, 0.) if side == "ymin" else (1, ly)
    def values(coordinates):
        selected = np.isclose(coordinates[axis], bound, rtol=1e-12, atol=1e-12)
        if axis == 1:
            tolerance = max(1e-12, abs(lx/2)*1e-12)
            selected &= coordinates[0] <= lx/2+tolerance if region == "left" else coordinates[0] >= lx/2-tolerance
        result = np.zeros((2, coordinates.shape[1]), dtype=function.x.array.dtype)
        if np.any(selected): result[:, selected] = numeric(parsed, coordinates[:, selected])
        return result
    function.interpolate(values)


def run_worker(input_path):
    output = Path(input_path).resolve().parent
    helpers, vector, manifest_sha = _verified_helpers(output)
    input_path = helpers._regular_file(output, "input.json")
    spec_sha = helpers._sha(input_path)
    if __package__:
        from plugins.pde_coupled import reference as domain
        from . import fenicsx_worker as expression
        from .fenicsx_coupled import level_files
    else:
        import coupled_reference as domain
        import fenicsx_expression as expression
        def level_files(count):
            return {key: f"level_n{count}/{name}" for key, name in {"field": "field.xdmf", "field_data": "field.h5", "form_source": "forms.ufl.txt", "dofs": "dofs.json", "binding": "binding.json"}.items()}
    settings = domain.validate_settings(helpers._read_json(input_path))
    for name in ("PETSC_OPTIONS", "PETSC_OPTIONS_YAML"): os.environ.pop(name, None)
    import petsc4py
    petsc4py.init(PETSC_INIT_ARGUMENTS)
    from petsc4py import PETSc
    options = PETSc.Options().getAll()
    if options != {"skip_petscrc": None} or PETSc.Options().getBool("skip_petscrc") is not True: raise RuntimeError("Coupled PETSc admits ambient options")
    initialization = {"argv": PETSC_INIT_ARGUMENTS, "options": options, "petsc_rc_disabled": True, "ambient_options_removed": ["PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]}
    helpers._save_json(output / "petsc_initialization.json", initialization)
    import basix
    import dolfinx
    from dolfinx import fem, io, mesh
    from dolfinx.fem.petsc import LinearProblem
    import ffcx
    import mpi4py
    from mpi4py import MPI
    import numpy as np
    import ufl
    comm = MPI.COMM_WORLD
    if comm.size != 1 or np.dtype(PETSc.ScalarType) != np.dtype("float64") or np.dtype(PETSc.RealType) != np.dtype("float64"): raise RuntimeError("Coupled PDE supports serial real64 only")
    versions = {"python": platform.python_version(), "dolfinx": dolfinx.__version__, "ufl": ufl.__version__, "basix": basix.__version__, "ffcx": ffcx.__version__,
                "petsc4py": petsc4py.__version__, "petsc": ".".join(map(str, PETSc.Sys.getVersion())), "mpi4py": mpi4py.__version__, "numpy": np.__version__}
    problem, trees = settings["problem"], domain._trees(settings["problem"])
    lx, ly = problem["domain"]["lengths"]
    numpy_functions = {name: getattr(np, name) for name in expression.FUNCTION_NAMES}
    studies, completed = [], []
    helpers._save_json(output / "progress.json", {"schema_version": "1", "status": "RUNNING", "completed": completed})
    def checked(value, label, nonnegative=False):
        value = float(value)
        if not expression.finite_number(value, nonnegative=nonnegative): raise RuntimeError(f"Invalid native coupled observation: {label}")
        return value
    def numeric(parsed, coordinates):
        with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
            return np.vstack([np.broadcast_to(np.asarray(expression.interpret_expression(tree, coordinates, numpy_functions), dtype=PETSc.ScalarType), coordinates.shape[1]) for tree in parsed])
    for n in settings["mesh"]["cell_counts"]:
        rectangle = mesh.create_rectangle(comm, [np.array([0., 0.]), np.array([lx, ly])], [n, n], cell_type=mesh.CellType.triangle)
        space = fem.functionspace(rectangle, ("Lagrange", 1, (2,)))
        coordinates, boundary_function = space.tabulate_dof_coordinates(), fem.Function(space)
        owned = vector._require_layout(space, coordinates, boundary_function.x.array)
        ids = space.dofmap.index_map.local_to_global(np.arange(owned, dtype=np.int32))
        order = np.argsort(ids)
        tags = _tagged_mesh(rectangle, space, ids, n, lx, ly, mesh, fem, np)
        union = np.unique(np.concatenate([nodes for side in domain.SIDES if problem["boundaries"][side]["type"] == "dirichlet" for nodes in tags["dofs"][side].values()]))
        boundary_values, assigned = boundary_function.x.array.reshape((-1, 2)), set()
        for side in domain.SIDES:
            if problem["boundaries"][side]["type"] != "dirichlet": continue
            for region, nodes in tags["dofs"][side].items():
                interpolated = fem.Function(space)
                _interpolate_boundary(interpolated, trees["boundaries"][side][region], side, region, (lx, ly), numeric, np)
                values = interpolated.x.array.reshape((-1, 2))
                for node in nodes:
                    for component in range(2):
                        value = checked(values[node, component], "native Dirichlet value")
                        if node in assigned and not math.isclose(value, boundary_values[node, component], rel_tol=1e-12, abs_tol=1e-12): raise RuntimeError("Native corner/interface Dirichlet conflict")
                        boundary_values[node, component] = value
                    assigned.add(int(node))
        boundary_function.x.scatter_forward()
        bc = fem.dirichletbc(boundary_function, union)
        forms = _native_forms(rectangle, space, tags, settings, trees, expression, helpers, vector, fem, PETSc, np, ufl)
        linear = LinearProblem(forms["a"], forms["L"], bcs=[bc], petsc_options_prefix=f"caelab_coupled_n{n}_", petsc_options=helpers.NATIVE_OPTIONS)
        uh = linear.solve()
        uh.x.scatter_forward()
        uh.name = "u"
        vector._require_layout(space, coordinates, uh.x.array)
        synchronization, synchronized = vector._solution_synchronization(linear.x.getArray(readonly=True), uh.x.array, np)
        native_values = uh.x.array.reshape((owned, 2))
        values = [[checked(value, "directed DOF") for value in native_values[node]] for node in order]
        policy = {"ksp_type": linear.solver.getType(), "pc_type": linear.solver.getPC().getType()}
        if policy != {"ksp_type": "preonly", "pc_type": "lu"}: raise RuntimeError("Actual coupled solver policy differs")
        residual = linear.b.duplicate()
        try:
            linear.A.mult(linear.x, residual)
            residual.axpy(-1., linear.b)
            absolute, rhs_norm = checked(residual.norm(), "constrained residual", True), checked(linear.b.norm(), "actual RHS norm", True)
        finally: residual.destroy()
        residual_record = {"absolute": absolute, "rhs_norm": rhs_norm, "relative": checked(absolute/rhs_norm if rhs_norm else absolute, "relative residual", True), "normalization": "rhs_l2_norm" if rhs_norm else "absolute_for_zero_rhs"}
        component_rows = []
        for component in range(2):
            l2_form, h1_form = None, None
            for region, tag in (("left", 1), ("right", 2)):
                error = uh[component]-forms["references"][region][component]
                l2_part, h1_part = error*error*forms["dx"](tag), ufl.inner(ufl.grad(error), ufl.grad(error))*forms["dx"](tag)
                l2_form, h1_form = (l2_part, h1_part) if l2_form is None else (l2_form+l2_part, h1_form+h1_part)
            l2 = math.sqrt(checked(comm.allreduce(fem.assemble_scalar(fem.form(l2_form)), op=MPI.SUM), "component L2 square", True))
            h1 = math.sqrt(checked(comm.allreduce(fem.assemble_scalar(fem.form(h1_form)), op=MPI.SUM), "component gradient square", True))
            previous = studies[-1]["components"][component] if studies else None
            component_rows.append({"index": component, "field": domain.COMPONENTS[component], "l2_error": l2, "h1_seminorm_error": h1,
                "l2_convergence_rate": expression.error_rate(previous["l2_error"], l2) if previous else None,
                "h1_seminorm_convergence_rate": expression.error_rate(previous["h1_seminorm_error"], h1) if previous else None,
                "boundary_value_error": checked(np.max(np.abs(native_values[union, component]-boundary_values[union, component])), "component boundary error", True)})
        vector_l2, vector_h1 = None, None
        for region, tag in (("left", 1), ("right", 2)):
            error = uh-forms["references"][region]
            lp, hp = ufl.inner(error, error)*forms["dx"](tag), ufl.inner(ufl.grad(error), ufl.grad(error))*forms["dx"](tag)
            vector_l2, vector_h1 = (lp, hp) if vector_l2 is None else (vector_l2+lp, vector_h1+hp)
        l2 = math.sqrt(checked(comm.allreduce(fem.assemble_scalar(fem.form(vector_l2)), op=MPI.SUM), "vector L2 square", True))
        h1 = math.sqrt(checked(comm.allreduce(fem.assemble_scalar(fem.form(vector_h1)), op=MPI.SUM), "vector Frobenius-gradient square", True))
        normal, boundaries = ufl.FacetNormal(rectangle), {}
        for side in domain.SIDES:
            boundaries[side] = {}
            for region, facets in tags["facets"][side].items():
                nodes, tag = tags["dofs"][side][region], SEGMENT_TAGS[side][region]
                endpoints = []
                for facet in facets:
                    pair = fem.locate_dofs_topological(space, 1, np.array([facet], dtype=np.int32))
                    if len(pair) != 2: raise RuntimeError("Native split-side facet does not have two blocked endpoints")
                    endpoints.append([int(ids[node]) for node in pair])
                boundaries[side][region] = {"facet_ids": [int(value) for value in rectangle.topology.index_map(1).local_to_global(facets)], "facet_node_ids": endpoints,
                    "dof_ids": [int(ids[node]) for node in nodes], "measure": checked(fem.assemble_scalar(fem.form(1.*forms["ds"](tag))), "segment measure"),
                    "normal_integral": [checked(fem.assemble_scalar(fem.form(normal[axis]*forms["ds"](tag))), "actual side normal") for axis in range(2)],
                    "prescribed_values": [[checked(value, "directed segment input") for value in row] for row in numeric(trees["boundaries"][side][region], coordinates[nodes].T).T],
                    "prescribed_integral": [checked(fem.assemble_scalar(fem.form(forms["side_expressions"][side][region][component]*forms["ds"](tag))), "directed segment integral") for component in range(2)]}
        diffusion_values = {region: [[checked(value, "native diffusion Constant") for value in row] for row in forms["diffusion"][region].value.tolist()] for region in domain.REGIONS}
        reaction_values = [[checked(value, "native reaction Constant") for value in row] for row in forms["reaction"].value.tolist()]
        field = {"schema_version": "1", "coordinates_unit": "1", "field_unit": "1", "field_type": "vector", "components": list(domain.COMPONENTS), "block_size": 2,
                 "node_ids": [int(ids[node]) for node in order], "coordinates": [[checked(value, "coordinate") for value in coordinates[node, :2]] for node in order], "values": values,
                 "cell_ids": tags["cell_ids"], "cell_node_ids": tags["cell_node_ids"], "cell_regions": tags["cell_regions"], "interface": tags["interface"],
                 "dirichlet_node_ids": sorted(int(ids[node]) for node in union), "boundaries": boundaries}
        binding = {"schema_version": "1", "components": list(domain.COMPONENTS), "regions": {}}
        for region in domain.REGIONS:
            nodes, cells = tags["node_indices"][region], tags["cell_indices"][region]
            binding["regions"][region] = {"cell_ids": sorted(tags["cell_ids"][cell] for cell in cells), "node_ids": [int(ids[node]) for node in nodes],
                "diffusion": diffusion_values[region], "reaction": reaction_values,
                "rhs_values": [[checked(value, "regional RHS/interface trace") for value in row] for row in numeric(trees["rhs"][region], coordinates[nodes].T).T],
                "reference_values": [[checked(value, "regional reference/interface trace") for value in row] for row in numeric(trees["reference"][region], coordinates[nodes].T).T]}
        files = level_files(n)
        level = (output / files["dofs"]).parent
        level.mkdir()
        helpers._save_json(output / files["dofs"], field)
        helpers._save_json(output / files["binding"], binding)
        with io.XDMFFile(comm, str(output / files["field"]), "w") as writer:
            writer.write_mesh(rectangle)
            writer.write_function(uh)
        (output / files["form_source"]).write_text(f"a = {forms['a']}\nL = {forms['L']}\nreference = {forms['references']}\nD axis = component rows of grad(u)\nerror_quadrature_degree = 8\n", encoding="utf-8")
        study = {"cells_per_axis": n, "nominal_h": math.hypot(lx, ly)/n, "degree": 1, "cell_type": "triangle", "global_cells": rectangle.topology.index_map(2).size_global,
            "global_nodes": space.dofmap.index_map.size_global, "global_dofs": 2*space.dofmap.index_map.size_global, "dirichlet_nodes": len(union), "dirichlet_dofs": 2*len(union), "block_size": 2,
            "solution_sync_error": synchronization, "boundary_value_error": max(row["boundary_value_error"] for row in component_rows), "l2_error": l2, "h1_seminorm_error": h1,
            "l2_convergence_rate": expression.error_rate(studies[-1]["l2_error"], l2) if studies else None,
            "h1_seminorm_convergence_rate": expression.error_rate(studies[-1]["h1_seminorm_error"], h1) if studies else None, "components": component_rows,
            "region_coefficients": diffusion_values, "reaction_matrix": reaction_values, "region_cell_counts": {region: len(tags["cell_indices"][region]) for region in domain.REGIONS},
            "interface_facets": len(tags["interface"]["facet_ids"]), "linear_residual": residual_record, "ksp_convergence_reason": int(linear.solver.getConvergedReason()),
            "ksp_iterations": int(linear.solver.getIterationNumber()), "solver_policy": policy, "files": files, "artifact_sha256": {key: helpers._sha(output / relative) for key, relative in files.items()}}
        helpers._save_json(level / "observation.json", study)
        if not synchronized: raise RuntimeError("Coupled actual x/saved Function scalar-DOF mismatch; partial observation retained")
        studies.append(study)
        completed.append({"cells_per_axis": n})
        helpers._save_json(output / "progress.json", {"schema_version": "1", "status": "RUNNING", "completed": completed})
    if helpers._sha(input_path) != spec_sha or _verified_helpers(output)[2] != manifest_sha: raise RuntimeError("Coupled input/source changed during native work")
    helpers._save_json(output / "progress.json", {"schema_version": "1", "status": "COMPLETED", "completed": completed})
    result = {"schema_version": "1", "status": "COMPLETED", "spec_sha256": spec_sha, "source_manifest_sha256": manifest_sha, "mpi_size": comm.size, "scalar_type": "float64", "versions": versions,
              "petsc_initialization": initialization, "petsc_initialization_sha256": helpers._sha(output / "petsc_initialization.json"), "mesh_studies": studies}
    helpers._save_json(output / "worker_result.json", result)
    print(json.dumps({"status": "COMPLETED", "mesh_levels": len(studies), "versions": versions}, allow_nan=False))
    return result


if __name__ == "__main__":
    if len(sys.argv) != 2: raise SystemExit("Usage: coupled worker input.json")
    run_worker(sys.argv[1])
