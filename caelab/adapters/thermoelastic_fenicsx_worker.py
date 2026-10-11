"""Isolated serial real64 FEniCSx conduction / SI thermoelastic worker.

The structural eigenstrain uses the captured solved temperature Function. No
temperature or displacement output is substituted with an analytical solution.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import sys

SOURCE_PATHS = {'adapter': ('caelab/adapters/thermoelastic_fenicsx.py', 'sources/thermoelastic_fenicsx.py'),
                'worker': ('caelab/adapters/thermoelastic_fenicsx_worker.py', 'worker.py'),
                'domain': ('plugins/thermoelastic/reference.py', 'thermoelastic_reference.py'),
                'helpers': ('caelab/adapters/fenicsx_rectangle_worker.py', 'rectangle_worker.py'),
                'runner': ('caelab/adapters/fenicsx_rectangle.py', 'sources/fenicsx_rectangle.py'),
                'execution_control': ('caelab/execution_control.py', 'sources/execution_control.py')}
PETSC_INIT_ARGUMENTS = ['caelab_thermoelastic_worker', '-skip_petscrc']


def _bootstrap(output):
    path = output / 'source_manifest.json'
    raw = path.read_bytes()
    manifest = json.loads(raw)
    if (set(manifest) != {'schema_version', 'domain_plugin_version', 'files'} or
            manifest['schema_version'] != '1' or manifest['domain_plugin_version'] != '1'
            or set(manifest['files']) != set(SOURCE_PATHS)):
        raise RuntimeError('Thermoelastic source manifest mismatch')
    for key, (repository, relative) in SOURCE_PATHS.items():
        row, copied = manifest['files'][key], output / relative
        if (row.get('repository_path') != repository or row.get('copied_path') != relative
                or not copied.resolve().is_relative_to(output.resolve())
                or any(part.is_symlink() for part in (copied, *copied.parents))
                or hashlib.sha256(copied.read_bytes()).hexdigest() != row.get('sha256')):
            raise RuntimeError('Thermoelastic captured source bytes changed')
    if __package__:
        from . import fenicsx_rectangle_worker as helpers
        from plugins.thermoelastic import reference as domain
    else:
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(output))
        import rectangle_worker as helpers
        import thermoelastic_reference as domain
    if helpers._read_json(path) != manifest:
        raise RuntimeError('Thermoelastic manifest changed during bootstrap')
    return helpers, domain, hashlib.sha256(raw).hexdigest()


def run_worker(input_path):
    input_path = Path(input_path).resolve()
    output = input_path.parent
    helpers, domain, manifest_sha = _bootstrap(output)
    spec_sha = helpers._sha(helpers._regular_file(output, 'input.json'))
    specification = helpers._read_json(input_path)
    if set(specification) != {'stage', 'settings'}: raise ValueError('Invalid stage worker specification')
    stage = specification['stage']
    settings = domain.validate_settings(specification['settings'], stage)
    if stage == 'structural' and settings['temperature'] is None:
        raise ValueError('Required temperature port is unbound')
    for name in ('PETSC_OPTIONS', 'PETSC_OPTIONS_YAML'): os.environ.pop(name, None)
    import petsc4py
    petsc4py.init(PETSC_INIT_ARGUMENTS)
    from petsc4py import PETSc
    options = PETSc.Options().getAll()
    if options != {'skip_petscrc': None} or PETSc.Options().getBool('skip_petscrc') is not True:
        raise RuntimeError('Thermoelastic PETSc bootstrap admits ambient options')
    initialization = {'argv': PETSC_INIT_ARGUMENTS, 'options': options, 'petsc_rc_disabled': True,
                      'ambient_options_removed': ['PETSC_OPTIONS', 'PETSC_OPTIONS_YAML']}
    helpers._save_json(output / 'petsc_initialization.json', initialization)
    import basix
    import dolfinx
    from dolfinx import fem, io, mesh
    from dolfinx.fem.petsc import LinearProblem
    import ffcx
    import mpi4py
    from mpi4py import MPI
    import numpy as np
    import ufl
    api_version = tuple(int(part) for part in dolfinx.__version__.split('.')[:2])
    if api_version < (0, 10):
        raise RuntimeError('Thermoelastic worker requires DOLFINx 0.10 or newer prefix/property API')
    comm = MPI.COMM_WORLD
    if comm.size != 1 or np.dtype(PETSc.ScalarType) != np.dtype('float64') or np.dtype(PETSc.RealType) != np.dtype('float64'):
        raise RuntimeError('Thermoelastic stages support serial real64 execution only')
    versions = {'python': platform.python_version(), 'dolfinx': dolfinx.__version__, 'ufl': ufl.__version__,
                'basix': basix.__version__, 'ffcx': ffcx.__version__, 'petsc4py': petsc4py.__version__,
                'petsc': '.'.join(map(str, PETSc.Sys.getVersion())), 'mpi4py': mpi4py.__version__, 'numpy': np.__version__}
    lx, ly = settings['domain']['lengths']
    nx, ny = settings['mesh']['cells']
    rectangle = mesh.create_rectangle(comm, [np.array([0., 0.]), np.array([lx, ly])], [nx, ny], cell_type=mesh.CellType.triangle)
    rectangle.topology.create_connectivity(1, 2)
    W = fem.functionspace(rectangle, ('Lagrange', 1))
    coordinates = W.tabulate_dof_coordinates()
    owned = W.dofmap.index_map.size_local
    if W.dofmap.index_map.num_ghosts or owned != (nx + 1) * (ny + 1) or W.dofmap.bs != 1:
        raise RuntimeError('Thermal scalar space requires complete serial P1 nodal layout')
    ids = W.dofmap.index_map.local_to_global(np.arange(owned, dtype=np.int32))
    order = np.argsort(ids)
    node_ids = [int(ids[node]) for node in order]
    xyz = coordinates[order, :2].tolist()
    cells = [[int(ids[node]) for node in W.dofmap.cell_dofs(cell)] for cell in range(rectangle.topology.index_map(2).size_local)]
    mesh_sha = domain.mesh_digest(xyz, cells)
    def import_temperature(field):
        domain.validate_temperature(field, settings)
        if field['node_ids'] != node_ids or field['coordinates'] != xyz or field['cell_node_ids'] != cells or field['mesh_sha256'] != mesh_sha:
            raise ValueError('Captured thermal grid differs from actual native mesh/DOF coordinates/connectivity; no mapping is inferred')
        function = fem.Function(W)
        function.x.array[order] = np.asarray(field['value'], dtype=PETSc.ScalarType)
        function.x.scatter_forward()
        return function
    dx = ufl.Measure('dx', domain=rectangle, metadata={'quadrature_degree': 4})
    checks, responses = [], {}
    helpers._save_json(output / 'progress.json', {'status': 'SOLVING', 'stage': stage, 'mesh_sha256': mesh_sha})
    if stage == 'thermal':
        old = settings['linearization_temperature']
        if old is None:
            k = fem.Constant(rectangle, PETSc.ScalarType(settings['conductivity']['value']))
        else:
            old_temperature = import_temperature(old)
            k = fem.Function(W)
            data = settings['conductivity']
            k.x.array[:] = data['value'] * (1. + data['beta'] * (old_temperature.x.array - data['reference_temperature']))
            if not np.all(np.isfinite(k.x.array)) or np.any(k.x.array <= 0.): raise ValueError('Native lagged conductivity is nonpositive')
            k.x.scatter_forward()
        boundary_facets = mesh.locate_entities_boundary(rectangle, 1, lambda x: np.ones(x.shape[1], dtype=bool))
        dofs = fem.locate_dofs_topological(W, 1, boundary_facets)
        bc = fem.dirichletbc(PETSc.ScalarType(settings['boundary_temperature']['value']), dofs, W)
        trial, test = ufl.TrialFunction(W), ufl.TestFunction(W)
        a = k * ufl.inner(ufl.grad(trial), ufl.grad(test)) * dx
        L = fem.Constant(rectangle, PETSc.ScalarType(settings['heat_source']['value'])) * test * dx
        bcs, space = [bc], W
    else:
        temperature = import_temperature(settings['temperature'])
        material = settings['material']
        E, nu, alpha, reference_temperature = (material[key] for key in ('young_modulus', 'poisson_ratio', 'thermal_expansion', 'reference_temperature'))
        mu, lame = E / (2. * (1. + nu)), E * nu / (1. - nu * nu)
        space = fem.functionspace(rectangle, ('Lagrange', 1, (2,)))
        if (space.dofmap.bs != 2 or space.dofmap.index_map_bs != 2 or space.dofmap.index_map.num_ghosts
                or not np.array_equal(space.tabulate_dof_coordinates(), coordinates)):
            raise RuntimeError('Structural vector nodes differ from validated scalar temperature nodes')
        origin = mesh.locate_entities_boundary(rectangle, 0, lambda x: np.isclose(x[0], 0., rtol=1e-12, atol=1e-14) & np.isclose(x[1], 0., rtol=1e-12, atol=1e-14))
        lower_right = mesh.locate_entities_boundary(rectangle, 0, lambda x: np.isclose(x[0], lx, rtol=1e-12, atol=1e-14) & np.isclose(x[1], 0., rtol=1e-12, atol=1e-14))
        if len(origin) != 1 or len(lower_right) != 1: raise RuntimeError('Mechanical rigid-mode anchors are incomplete')
        bcs = [fem.dirichletbc(PETSc.ScalarType(0.), fem.locate_dofs_topological(space.sub(c), 0, vertices), space.sub(c))
               for c, vertices in ((0, origin), (1, origin), (1, lower_right))]
        trial, test = ufl.TrialFunction(space), ufl.TestFunction(space)
        eps = lambda function: ufl.sym(ufl.grad(function))
        a = (2. * mu * ufl.inner(eps(trial), eps(test)) + lame * ufl.div(trial) * ufl.div(test)) * dx
        eigenstress = (2. * mu + 2. * lame) * alpha * (temperature - reference_temperature) * ufl.Identity(2)
        L = ufl.inner(eigenstress, eps(test)) * dx
    (output / 'forms.ufl.txt').write_text('a = ' + str(a) + '\nL = ' + str(L) + '\n', encoding='utf-8')
    linear = LinearProblem(a, L, bcs=bcs, petsc_options_prefix='caelab_thermoelastic_' + stage + '_', petsc_options=helpers.NATIVE_OPTIONS)
    solution = linear.solve()
    solution.x.scatter_forward()
    if not np.all(np.isfinite(solution.x.array)): raise RuntimeError('Native stage returned a nonfinite field')
    if not np.allclose(linear.x.getArray(readonly=True), solution.x.array, rtol=1e-12, atol=1e-14):
        raise RuntimeError('Algebraic and saved Function layouts differ')
    policy = {'ksp_type': linear.solver.getType(), 'pc_type': linear.solver.getPC().getType()}
    if policy != {'ksp_type': 'preonly', 'pc_type': 'lu'}: raise RuntimeError('Native stage solver policy changed')
    residual = linear.b.duplicate()
    try:
        linear.A.mult(linear.x, residual)
        residual.axpy(-1., linear.b)
        rhs_norm = float(linear.b.norm())
        relative = float(residual.norm()) / rhs_norm if rhs_norm else float(residual.norm())
    finally:
        residual.destroy()
    if not np.isfinite(relative): raise RuntimeError('Nonfinite native residual')
    passed = relative <= settings['validation']['max_residual_relative'] and linear.solver.getConvergedReason() > 0
    checks.append({'code': 'native_linear_residual', 'status': 'PASS' if passed else 'FAIL', 'observed': relative,
                   'limit': settings['validation']['max_residual_relative']})
    common = {'kind': 'field', 'location': 'node', 'reduction': 'none', 'association': 'POINTS',
              'frame': 'global_cartesian', 'coordinate_units': 'm', 'coordinate_frame': 'global_cartesian',
              'coordinates': xyz, 'node_ids': node_ids, 'cell_node_ids': cells,
              'mesh_declaration': domain.mesh_declaration(settings), 'mesh_sha256': mesh_sha,
              'time': settings['time']['value'], 'time_units': 's', 'time_origin': settings['time']['origin']}
    def scalar(value, unit, quantity):
        return {'kind': 'scalar', 'value': float(value), 'unit': unit, 'quantity': quantity, 'component': 'scalar', 'location': 'rectangle', 'reduction': 'backend_defined'}
    if stage == 'thermal':
        solution.name = 'temperature'
        field = domain.seal_field({**common, 'value': solution.x.array[order].tolist(), 'unit': 'K',
            'quantity': 'absolute_temperature', 'component': 'scalar', 'measure': 'thermodynamic_temperature'})
        helpers._save_json(output / 'thermal_field.json', field)
        domain.validate_temperature(field, settings)
        responses['temperature'] = field
        volume = fem.assemble_scalar(fem.form(fem.Constant(rectangle, PETSc.ScalarType(1.)) * dx))
        responses['mean_temperature'] = scalar(fem.assemble_scalar(fem.form(solution * dx)) / volume, 'K', 'absolute_temperature')
        responses['minimum_conductivity'] = scalar(min(domain.conductivity_values(settings)), 'W/(m*K)', 'conductivity')
    else:
        solution.name = 'displacement'
        values = solution.x.array.reshape((owned, 2))[order]
        responses['displacement'] = domain.seal_field({**common, 'value': values.tolist(), 'unit': 'm', 'quantity': 'displacement',
                                     'component': 'vector', 'components': ['x', 'y'], 'measure': 'infinitesimal_displacement'})
        responses['displacement_linf'] = scalar(np.max(np.linalg.norm(values, axis=1)), 'm', 'displacement_magnitude')
        total_stress = 2. * mu * ufl.sym(ufl.grad(solution)) + lame * ufl.div(solution) * ufl.Identity(2) - eigenstress
        stress_space = fem.functionspace(rectangle, ('DG', 0, (3,)))
        stress = fem.Function(stress_space)
        stress.interpolate(fem.Expression(ufl.as_vector([total_stress[0, 0], total_stress[1, 1], total_stress[0, 1]]), stress_space.element.interpolation_points))
        stress.x.scatter_forward()
        stress.name = 'stress_xx_yy_xy'
        stress_values = stress.x.array.reshape((-1, 3))
        stress_coordinates = stress_space.tabulate_dof_coordinates()
        cell_dofs = [int(stress_space.dofmap.cell_dofs(cell)[0]) for cell in range(len(cells))]
        cell_values = stress_values[cell_dofs]
        if not np.all(np.isfinite(cell_values)): raise RuntimeError('Nonfinite actual thermoelastic stress')
        responses['stress'] = domain.seal_field({'kind': 'field', 'value': cell_values.tolist(), 'unit': 'Pa', 'quantity': 'stress',
            'component': 'tensor_components', 'components': ['xx', 'yy', 'xy'], 'location': 'cell', 'reduction': 'cell_average',
            'association': 'CELLS', 'measure': 'infinitesimal_Cauchy', 'frame': 'global_cartesian',
            'coordinate_units': 'm', 'coordinate_frame': 'global_cartesian', 'coordinates': stress_coordinates[cell_dofs, :2].tolist(),
            'node_ids': node_ids, 'mesh_coordinates': xyz,
            'cell_ids': list(range(len(cells))), 'cell_node_ids': cells,
            'mesh_sha256': mesh_sha, 'time': settings['time']['value'], 'time_units': 's', 'time_origin': settings['time']['origin']})
        responses['stress_linf'] = scalar(np.max(np.abs(cell_values)), 'Pa', 'stress_component_magnitude')
        threshold = settings['validation']['free_expansion_max_error']
        if threshold is not None:
            actual_temperature = np.asarray(settings['temperature']['value'])
            uniform = float(np.ptp(actual_temperature)) <= settings['validation']['temperature_uniformity_tolerance']
            delta = float(np.mean(actual_temperature)) - reference_temperature
            error = float(np.max(np.linalg.norm(values - alpha * delta * np.asarray(xyz), axis=1)))
            checks.append({'code': 'free_expansion_uniform_temperature', 'status': 'PASS' if uniform else 'FAIL',
                'observed': float(np.ptp(actual_temperature)), 'limit': settings['validation']['temperature_uniformity_tolerance']})
            checks.append({'code': 'free_expansion_displacement_error', 'status': 'PASS' if uniform and error <= threshold else 'FAIL', 'observed': error, 'limit': threshold})
            responses['free_expansion_error'] = scalar(error, 'm', 'benchmark_displacement_error')
    helpers._save_json(output / 'fields.json', responses)
    with io.XDMFFile(comm, str(output / 'field.xdmf'), 'w') as writer:
        writer.write_mesh(rectangle)
        writer.write_function(solution, settings['time']['value'])
        if stage == 'structural': writer.write_function(stress, settings['time']['value'])
    artifacts = {relative: helpers._sha(helpers._regular_file(output, relative)) for relative in
                 ('fields.json', 'field.xdmf', 'field.h5', 'forms.ufl.txt', 'petsc_initialization.json')}
    if stage == 'thermal': artifacts['thermal_field.json'] = helpers._sha(output / 'thermal_field.json')
    if helpers._sha(input_path) != spec_sha or _bootstrap(output)[2] != manifest_sha:
        raise RuntimeError('Stage frozen input/source changed during native solve')
    status = 'SUCCEEDED' if all(check['status'] == 'PASS' for check in checks) else 'REJECTED'
    helpers._save_json(output / 'progress.json', {'status': 'COMPLETED', 'stage': stage, 'execution_status': status})
    result = {'schema_version': '1', 'stage': stage, 'execution_status': status, 'responses': responses, 'checks': checks,
        'spec_sha256': spec_sha, 'source_manifest_sha256': manifest_sha, 'mpi_size': comm.size, 'scalar_type': 'float64',
        'versions': versions, 'solver_policy': policy, 'petsc_initialization': initialization,
        'ksp_convergence_reason': int(linear.solver.getConvergedReason()), 'artifacts': artifacts}
    helpers._save_json(output / 'worker_result.json', result)
    print(json.dumps({'stage': stage, 'execution_status': status, 'versions': versions}, allow_nan=False))
    return result


if __name__ == '__main__':
    if len(sys.argv) != 2: raise SystemExit('Usage: thermoelastic worker input.json')
    run_worker(sys.argv[1])
