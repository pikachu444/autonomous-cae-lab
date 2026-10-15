"""Isolated, captured scikit-fem/SciPy spatial worker; no alternate FE solver.

The existing owner/JobManager supervises this process through the existing
execution_control runner. It writes partial fields/metrics before returning.
"""
from pathlib import Path
import hashlib
import json
import math
import platform
import sys


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def _solve_condensed(matrix, rhs, dofs, prescribed):
    import warnings
    import numpy as np
    from skfem import condense
    from scipy.sparse.linalg import spsolve, MatrixRankWarning
    if not np.isfinite(matrix.data).all() or not np.isfinite(rhs).all() or not np.isfinite(prescribed).all():
        raise ValueError('Nonfinite assembled matrix, load or Dirichlet data')
    a, b, solution, free = condense(matrix, rhs, x=prescribed, D=np.asarray(sorted(set(dofs)), dtype=np.int32))
    if len(free):
        with warnings.catch_warnings():
            warnings.simplefilter('error', MatrixRankWarning)
            solution[free] = spsolve(a, b, permc_spec='COLAMD', use_umfpack=False)
    if not np.isfinite(solution).all():
        raise ValueError('The sparse solve did not produce finite values')
    residual = a @ solution[free] - b
    absolute, denominator = float(np.linalg.norm(residual)), float(np.linalg.norm(b))
    relative = absolute / denominator if denominator > 0. else absolute
    receipt = {'dofs': int(matrix.shape[0]), 'free_dofs': int(len(free)), 'dirichlet_dofs': int(len(dofs)),
               'matrix_nonzeros': int(matrix.nnz), 'condensed_nonzeros': int(a.nnz),
               'residual_absolute': absolute, 'rhs_norm': denominator, 'relative_residual': relative,
               'residual_definition': 'L2(A_II*u_I-b_condensed)/L2(b_condensed); absolute L2 when denominator=0',
               'linear_solve_calls': int(bool(len(free))), 'assembly_calls': 2,
               'solver': 'scipy.sparse.linalg.spsolve', 'factorization': 'SuperLU', 'permc_spec': 'COLAMD',
               'use_umfpack': False, 'dirichlet_max_error': float(np.max(np.abs(solution[dofs] - prescribed[dofs]))) if len(dofs) else 0.}
    return solution, receipt


def _mesh(settings):
    import numpy as np
    from skfem import MeshTri
    from caelab.p1_temperature_transfer import rectangle_geometry
    geometry = rectangle_geometry(settings)
    mesh = MeshTri(np.asarray(geometry['coordinates'], dtype=float).T,
                   np.asarray(geometry['cell_node_ids'], dtype=np.int32).T, sort_t=False)
    if (not np.array_equal(mesh.p.T, np.asarray(geometry['coordinates']))
            or not np.array_equal(mesh.t.T, np.asarray(geometry['cell_node_ids']))):
        raise RuntimeError('Library mesh reordered the declared identities; no implicit remapping is allowed')
    return mesh, geometry


def _scalar(value, unit, component, reduction='native_integral'):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Nonfinite scalar response')
    return {'kind': 'scalar', 'value': value, 'unit': unit, 'component': component,
            'location': 'domain', 'reduction': reduction}


def thermal(settings, output):
    import numpy as np
    from skfem import Basis, ElementTriP1, BilinearForm, LinearForm
    from skfem.helpers import dot, grad
    from plugins.thermoelastic import reference as original
    from caelab import p1_temperature_transfer as transfer
    mesh, geometry = _mesh(settings)
    basis = Basis(mesh, ElementTriP1(), intorder=8)
    material = settings['conductivity']
    lag = settings['linearization_temperature']
    temperatures = (np.asarray(transfer._absolute_values(lag)) if lag is not None
                    else np.full(basis.N, material['reference_temperature']))
    conductivity = material['value'] * (1. + material['beta'] * (temperatures - material['reference_temperature']))
    if np.any(conductivity <= 0.) or not np.isfinite(conductivity).all():
        raise ValueError('Lagged temperature-dependent conductivity must remain strictly positive at every node')
    coefficient = basis.interpolate(conductivity)

    @BilinearForm
    def stiffness(u, v, w):
        return w.conductivity * dot(grad(u), grad(v))

    @LinearForm
    def source(v, w):
        return settings['heat_source']['value'] * v

    matrix = stiffness.assemble(basis, conductivity=coefficient)
    rhs = source.assemble(basis)
    xy = np.asarray(geometry['coordinates'])
    boundary = settings['boundary_temperature']
    temperature = boundary['value'] + transfer.ABS_UNITS[boundary['unit']]
    gx, gy = settings['boundary_gradient']['values']
    dofs = mesh.boundary_nodes()
    prescribed = np.zeros(basis.N)
    prescribed[dofs] = temperature + gx * xy[dofs, 0] + gy * xy[dofs, 1]
    solution, receipt = _solve_condensed(matrix, rhs, dofs, prescribed)
    save(output/'thermal_solution.json', {'status':'UNVALIDATED', 'unit':'K',
        'quantity':'absolute_temperature', 'values':solution.tolist(), 'coordinates':geometry['coordinates']})
    save(output/'assembly.json', receipt)
    save(output/'progress.json', {'phase':'THERMAL_SOLVED_UNVALIDATED', 'assembly':receipt,
        'field_artifact':'thermal_solution.json', 'field_status':'NOT_YET_VALIDATED'})
    field = transfer.temperature_field(settings, solution.tolist())
    # A physical-range/coverage rejection must not erase the actual solved
    # field. This unvalidated artifact is evidence, never an admissible response.
    save(output/'thermal_field.json', field)
    save(output/'assembly.json', receipt)
    save(output/'progress.json', {'phase':'THERMAL_SOLVED_UNVALIDATED', 'assembly':receipt,
                                'field_artifact':'thermal_field.json', 'field_status':'NOT_YET_VALIDATED'})
    transfer.validate_capture(field)
    response = basis.interpolate(solution)
    area = float(np.sum(basis.dx))
    mean = float(np.sum(response * basis.dx) / area)
    checks = [{'name': 'relative_algebraic_residual', 'status': 'PASS' if receipt['relative_residual'] <= settings['validation']['max_residual_relative'] else 'FAIL',
               'observed': receipt['relative_residual'], 'limit': settings['validation']['max_residual_relative']}]
    reference = None
    if settings['heat_source']['value'] == 0. and (material['beta'] == 0. or lag is None
            or np.ptp(conductivity) <= np.finfo(float).eps * max(1., float(conductivity.max()))):
        # Independent affine reference applies only to constant-conductivity,
        # zero-source conduction; no hardcoded response replaces the solve.
        exact_nodes = temperature + gx * xy[:, 0] + gy * xy[:, 1]
        qcoords = basis.global_coordinates()
        exact_q = temperature + gx*qcoords[0] + gy*qcoords[1]
        gradient_error = response.grad - np.asarray([gx, gy])[:, None, None]
        reference = {'kind': 'AFFINE_HARMONIC', 'nodal_max_error_K': float(np.max(np.abs(solution - exact_nodes))),
                     'l2_error_K_m': float(np.sqrt(np.sum((response-exact_q)**2 * basis.dx))),
                     'h1_seminorm_error_K': float(np.sqrt(np.sum(np.sum(gradient_error**2, axis=0) * basis.dx))),
                     'quadrature_degree': 8}
    responses = {'temperature': field, 'mean_temperature': _scalar(mean, 'K', 'mean_temperature'),
                 'relative_residual': _scalar(receipt['relative_residual'], '1', 'relative_residual', 'algebraic_norm')}
    if material['beta'] == 0. and lag is None:
        # Original matrix and quadrature reduction, sealed with the primal.
        # A later adjoint worker consumes these bytes without another primal.
        @LinearForm
        def unit_load(v, w):
            return v
        weights_load = unit_load.assemble(basis)
        matrix = matrix.tocsr()
        free = np.setdiff1d(np.arange(basis.N, dtype=np.int32), dofs)
        np.savez_compressed(output/'primal-system.npz', data=matrix.data, indices=matrix.indices,
            indptr=matrix.indptr, shape=np.asarray(matrix.shape), rhs=rhs, solution=solution,
            free=free, dirichlet=dofs, weights=weights_load/area, unit_load=weights_load)
        receipt['assembly_calls'] += 1
        receipt['retained_primal_system'] = 'primal-system.npz'
        receipt['response_weight_assembly_calls'] = 1
    save(output/'thermal_field.json', field)
    save(output/'assembly.json', receipt)
    save(output/'forms.txt.json', {'bilinear': 'k_lag*inner(grad(T),grad(v))', 'linear': 'q*v',
                                  'boundary': 'T0_K + gradient_x*x + gradient_y*y',
                                  'picard': 'k_lag=k0*(1+beta*(T_previous-Tkref)); previous field is immutable'})
    return {'execution_status': 'SUCCEEDED' if all(c['status'] == 'PASS' for c in checks) else 'REJECTED',
            'responses': responses, 'checks': checks,
            'diagnostics': {'assembly': receipt, 'reference': reference, 'snapshot_physics': 'STEADY_CONDUCTION',
                            'nonlinear_iteration': 'EXPLICIT_LAGGED_PICARD_ONLY'}}


def structural(settings, output):
    import numpy as np
    from skfem import Basis, ElementTriP1, ElementVector, LinearForm
    from skfem.helpers import div, sym_grad
    from skfem.models.elasticity import linear_elasticity
    from plugins.thermoelastic import reference as original
    from caelab import p1_temperature_transfer as transfer
    quantity = transfer.ABSOLUTE if settings['temperature_mode'] == 'absolute' else transfer.DIFFERENCE
    temperature = transfer.validate_bound(settings['temperature'], settings, quantity=quantity)
    mesh, geometry = _mesh(settings)
    scalar_basis = Basis(mesh, ElementTriP1(), intorder=8)
    basis = Basis(mesh, ElementVector(ElementTriP1(), dim=2), intorder=8)
    material = settings['material']
    young, nu, alpha, tref = (material[k] for k in ('young_modulus', 'poisson_ratio', 'thermal_expansion', 'reference_temperature'))
    mu = young / (2. * (1. + nu))
    lam = young * nu / ((1. + nu) * (1. - nu))  # Reduced 2D plane-stress Lamé coefficient.
    absolute = np.asarray(transfer._absolute_values(temperature), dtype=float)
    delta = absolute - tref if quantity == transfer.ABSOLUTE else np.asarray(temperature['value'], dtype=float)
    delta_q = scalar_basis.interpolate(delta)
    matrix = linear_elasticity(Lambda=lam, Mu=mu).assemble(basis)

    @LinearForm
    def thermal_load(v, w):
        return 2. * (mu + lam) * alpha * w.delta * div(v)

    rhs = thermal_load.assemble(basis, delta=delta_q)
    xy = np.asarray(geometry['coordinates'])
    nx, _ = settings['mesh']['cells']
    # Three exact original physical anchors: origin ux/uy and lower-right uy.
    dofs = np.asarray([basis.nodal_dofs[0, 0], basis.nodal_dofs[1, 0], basis.nodal_dofs[1, nx]], dtype=np.int32)
    prescribed = np.zeros(basis.N)
    solution, receipt = _solve_condensed(matrix, rhs, dofs, prescribed)
    nodal = solution[basis.nodal_dofs].T
    displacement = {k: v for k, v in temperature.items() if k not in ('capture_sha256', 'temperature_reference')}
    displacement.update(value=nodal.tolist(), unit='m', quantity='displacement', component='vector',
                        components=['x', 'y'], measure='small_strain_displacement')
    displacement = original.seal_field(displacement)
    strain = sym_grad(basis.interpolate(solution))
    trace = strain[0, 0] + strain[1, 1]
    isotropic = lam * trace - 2. * (mu + lam) * alpha * delta_q
    sigma = np.stack([2.*mu*strain[0, 0] + isotropic,
                      2.*mu*strain[1, 1] + isotropic, 2.*mu*strain[0, 1]], axis=0)
    cell_area = np.sum(basis.dx, axis=1)
    average = (np.sum(sigma * basis.dx[None, :, :], axis=2) / cell_area[None, :]).T
    if not np.isfinite(average).all():
        raise ValueError('Nonfinite cell-average Cauchy stress')
    cells = np.asarray(geometry['cell_node_ids'], dtype=int)
    stress = dict(geometry, kind='field', value=average.tolist(), unit='Pa', quantity='stress',
                  component='tensor_components', components=['xx', 'yy', 'xy'], location='cell', reduction='cell_average',
                  association='CELLS', measure='infinitesimal_Cauchy', frame='global_cartesian',
                  coordinate_units='m', coordinate_frame='global_cartesian', mesh_coordinates=geometry['coordinates'],
                  coordinates=xy[cells].mean(axis=1).tolist(), cell_ids=list(range(len(cells))),
                  time=temperature['time'], time_units=temperature['time_units'], time_origin=temperature['time_origin'],
                  basis='DG0', valid_mask=[True] * len(cells), snapshot_kind=temperature['snapshot_kind'])
    stress = original.seal_field(stress)
    threshold = settings['validation']['max_residual_relative']
    checks = [{'name': 'relative_algebraic_residual', 'status': 'PASS' if receipt['relative_residual'] <= threshold else 'FAIL',
               'observed': receipt['relative_residual'], 'limit': threshold}]
    error_limit = settings['validation']['free_expansion_max_error']
    uniformity_limit = settings['validation']['temperature_uniformity_tolerance']
    spread = float(np.ptp(absolute))
    benchmark = {'status': 'NOT_APPLIED_EXPLICITLY', 'temperature_spread_K': spread,
                 'uniformity_limit_K': uniformity_limit, 'displacement_error_m': None}
    if error_limit is not None:
        expected = alpha * delta[0] * xy
        error = float(np.max(np.linalg.norm(nodal-expected, axis=1)))
        applicable = spread <= uniformity_limit
        benchmark.update(status='PASS' if applicable and error <= error_limit else 'FAIL', displacement_error_m=error,
                         expected_delta_temperature_K=float(delta[0]), reason=None if applicable else 'NONUNIFORM_TEMPERATURE_NOT_A_FREE_EXPANSION_BENCHMARK')
        checks.extend([{'name': 'uniform_temperature_for_free_expansion', 'status': 'PASS' if applicable else 'FAIL',
                        'observed': spread, 'limit': uniformity_limit},
                       {'name': 'free_expansion_displacement', 'status': 'PASS' if applicable and error <= error_limit else 'FAIL',
                        'observed': error, 'limit': error_limit}])
    save(output/'assembly.json', receipt)
    save(output/'forms.txt.json', {'assumption': 'small_strain_plane_stress', 'lambda_plane_stress_Pa': lam, 'mu_Pa': mu,
        'strain_thermal': 'alpha*deltaT*I', 'stress': '2*mu*(epsilon-alpha*deltaT*I)+lambda_ps*tr(epsilon-alpha*deltaT*I)*I',
        'delta_temperature': 'T_absolute_K-Tref' if quantity == transfer.ABSOLUTE else 'supplied_deltaT; do not subtract Tref again',
        'Tref_owner': transfer.receiver_reference(settings), 'reference_subtractions_in_structural_solver': int(quantity == transfer.ABSOLUTE),
        'thickness': 'Uniform through-thickness temperature and constant thickness cancel from both 2D weak forms'})
    return {'execution_status': 'SUCCEEDED' if all(c['status'] == 'PASS' for c in checks) else 'REJECTED',
            'responses': {'displacement': displacement, 'stress': stress, 'temperature': temperature,
                          'max_displacement': _scalar(np.linalg.norm(nodal, axis=1).max(), 'm', 'max_displacement', 'nodal_max'),
                          'relative_residual': _scalar(receipt['relative_residual'], '1', 'relative_residual', 'algebraic_norm')},
            'checks': checks, 'diagnostics': {'assembly': receipt, 'free_expansion': benchmark,
                                             'reference_temperature': transfer.receiver_reference(settings),
                                             'reference_subtractions_in_structural_solver': int(quantity == transfer.ABSOLUTE),
                                             'snapshot_physics': 'QUASISTATIC_PLANE_STRESS'}}


def weak(settings, output):
    import numpy as np
    from skfem import Basis, ElementTriP1, BilinearForm, LinearForm
    from caelab import scikit_fem_models as domain
    from caelab import p1_temperature_transfer as transfer
    from caelab.dimensioned_expression import parse, Meaning, UNITS, unit_dimension
    from caelab.dimensioned_models import parameters
    from caelab.adapters.scikit_fem_forms import value, gradient
    from plugins.thermoelastic import reference as original
    symbols, parameters_ = parameters(settings)
    symbols.update(pi=Meaning(), x=Meaning(UNITS['m']), y=Meaning(UNITS['m']))
    base_symbols = dict(symbols)
    dim = unit_dimension(settings['field']['unit'])
    symbols.update(u=Meaning(dim, 0, (1, 0)), v=Meaning(dim, 0, (0, 1)))
    a_tree = parse(settings['forms']['bilinear'], symbols, weak=True)[0]
    b_tree = parse(settings['forms']['linear'], symbols, weak=True)[0]
    reference_tree = parse(settings['reference'], base_symbols)[0] if settings['reference'] else None
    studies, fields, responses = [], [], {}
    for level in settings['mesh']['levels']:
        physical = domain.geometry_settings(domain.WEAK, settings, level)
        mesh, geometry = _mesh(physical)
        basis = Basis(mesh, ElementTriP1(), intorder=8)
        def environment(coordinates, u=None, v=None):
            shape = coordinates[0].shape
            gradients = {'x': np.stack([np.ones(shape), np.zeros(shape)]),
                         'y': np.stack([np.zeros(shape), np.ones(shape)])}
            values = dict(parameters_, pi=math.pi, x=coordinates[0], y=coordinates[1])
            for key, field in (('u', u), ('v', v)):
                if field is not None:
                    values[key] = np.asarray(field); gradients[key] = field.grad
            return values, gradients
        @BilinearForm
        def bilinear(u, v, w):
            return value(a_tree, *environment(w.x, u, v))
        @LinearForm
        def linear(v, w):
            return value(b_tree, *environment(w.x, v=v))
        with np.errstate(all='raise'):
            matrix, rhs = bilinear.assemble(basis), linear.assemble(basis)
            xy = np.asarray(geometry['coordinates']).T
            lx, ly = physical['domain']['lengths']
            sides = {'left': (0, 0.), 'right': (0, lx), 'bottom': (1, 0.), 'top': (1, ly)}
            prescribed = np.zeros(basis.N); assigned = {}
            for row in settings['boundaries']:
                axis, location = sides[row['side']]
                nodes = np.flatnonzero(np.isclose(xy[axis], location, rtol=1e-12, atol=1e-14))
                tree = parse(row['expression'], base_symbols)[0]
                evaluated = np.broadcast_to(np.asarray(value(tree, *environment(xy)), dtype=float), (basis.N,))
                for node in nodes:
                    scalar = float(evaluated[node])
                    if node in assigned and not math.isclose(assigned[node], scalar, rel_tol=1e-12, abs_tol=1e-12):
                        raise ValueError('Conflicting Dirichlet values at a shared corner')
                    assigned[node] = scalar; prescribed[node] = scalar
            dofs = np.asarray(sorted(assigned), dtype=np.int32)
            solution, receipt = _solve_condensed(matrix, rhs, dofs, prescribed)
        field = transfer.temperature_field(physical, solution.tolist())
        if settings['physical']['quantity'] == transfer.ABSOLUTE:
            transfer.validate_capture(field)
        else:
            field.update(unit=settings['field']['unit'], quantity='declared_scalar', measure='user_declared_scalar')
            field = original.seal_field(field)
        study = dict(receipt, cells_per_axis=level, l2_error=None, h1_seminorm_error=None,
                     reference_status='NOT_DECLARED', quadrature_degree=8,
                     norm_definition='L2=sqrt(integral((uh-uref)^2 dA)); H1=sqrt(integral(|grad(uh-uref)|^2 dA))',
                     l2_unit=settings['field']['unit']+'*m', h1_unit=settings['field']['unit'])
        if reference_tree is not None:
            with np.errstate(all='raise'):
                env = environment(basis.global_coordinates())
                reference = value(reference_tree, *env); reference_gradient = gradient(reference_tree, *env)
                uh = basis.interpolate(solution)
                study.update(l2_error=float(np.sqrt(np.sum((uh-reference)**2*basis.dx))),
                             h1_seminorm_error=float(np.sqrt(np.sum(np.sum((uh.grad-reference_gradient)**2, axis=0)*basis.dx))),
                             reference_status='AVAILABLE')
        studies.append(study); fields.append(field)
        save(output/('level_'+str(level))/'field.json', field)
        save(output/'progress.json', {'completed_levels': studies, 'physical_fields': fields})
        responses[settings['field']['name']] = field
    finest = studies[-1]
    for name, unit in [('l2_error', finest['l2_unit']), ('h1_seminorm_error', finest['h1_unit']), ('relative_residual', '1')]:
        if finest[name] is not None:
            responses[name] = _scalar(finest[name], unit, name, 'algebraic_norm' if name == 'relative_residual' else 'native_integral')
    threshold = settings['solver']['residual_relative']
    checks = [{'name': 'relative_algebraic_residual', 'status': 'PASS' if row['relative_residual'] <= threshold else 'FAIL',
               'observed': row['relative_residual'], 'limit': threshold, 'cells_per_axis': row['cells_per_axis']} for row in studies]
    save(output/'forms.txt.json', settings['forms'])
    return {'execution_status': 'SUCCEEDED' if all(row['status'] == 'PASS' for row in checks) else 'REJECTED',
            'responses': responses, 'checks': checks,
            'diagnostics': {'mesh_studies': studies, 'physical_fields': fields,
                            'reference_kind': 'USER_DECLARED_NOT_QUALIFICATION', 'snapshot_physics': 'STEADY_LINEAR_WEAK_FORM'}}


def main(input_path):
    input_path = Path(input_path).resolve()
    output = input_path.parent
    # This file is copied under native/sources/caelab/adapters. The isolated
    # interpreter imports ONLY the captured product package plus installed OSS.
    sources_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(sources_root)); sys.dont_write_bytecode = True
    # `plugins` is a namespace in the product. An installed regular package of
    # the same name must not win over the captured namespace/package contents.
    from importlib.machinery import ModuleSpec
    from importlib.util import module_from_spec
    plugin_spec = ModuleSpec('plugins', loader=None, is_package=True)
    plugin_spec.submodule_search_locations = [str(sources_root / 'plugins')]
    sys.modules['plugins'] = module_from_spec(plugin_spec)
    manifest = json.loads((output/'source_manifest.json').read_text(encoding='utf-8'))
    for relative, row in manifest['files'].items():
        path = sources_root/relative
        if not path.resolve().is_relative_to(sources_root) or path.is_symlink() or sha(path) != row['sha256']:
            raise ValueError('Frozen spatial worker source identity changed')
    spec = json.loads(input_path.read_text(encoding='utf-8'))
    from caelab import scikit_fem_models as domain
    settings = domain.validate_settings(spec['backend'], spec['settings'])
    origins = {}
    for relative in manifest['files']:
        if not relative.endswith('.py'):
            continue
        module_name = relative[:-3].replace('/', '.')
        if module_name.endswith('.__init__'):
            module_name = module_name[:-9]
        loaded = sys.modules.get(module_name)
        if loaded is not None:
            path = Path(loaded.__file__).resolve()
            if path != (sources_root / relative).resolve() or sha(path) != manifest['files'][relative]['sha256']:
                raise ValueError('Imported product module is not the captured original: ' + module_name)
            origins[module_name] = {'file': str(path), 'sha256': sha(path)}
    save(output / 'import_identity.json', origins)
    from importlib.metadata import version
    versions = {name: version(name) for name in domain.VERSIONS}
    if versions != domain.VERSIONS:
        raise RuntimeError('Pinned spatial dependency versions differ: ' + repr(versions))
    versions.update(python=sys.version, platform=platform.platform(), implementation=platform.python_implementation())
    import numpy as np
    import skfem
    import scipy
    if (skfem.__version__ != versions['scikit-fem'] or scipy.__version__ != versions['scipy']
            or np.__version__ != versions['numpy']):
        raise RuntimeError('Imported library and distribution versions disagree')
    dispatch = {domain.THERMAL: thermal, domain.STRUCTURAL: structural, domain.WEAK: weak}
    if spec.get('task') == 'adjoint':
        from caelab.adapters.scikit_fem_adjoint_worker import adjoint
        raw = adjoint(settings, output, spec)
    elif 'task' in spec:
        raise ValueError('Unknown spatial worker task')
    else:
        raw = dispatch[spec['backend']](settings, output)
    save(output/'fields.json', raw['responses'])
    raw['diagnostics'].update(versions=versions, decision='NOT_RELEASED', physical_qualification='UNKNOWN',
                              backend_identity=spec['backend'], implementation_version='1',
                              solver_policy={'assembly': 'scikit-fem', 'linear_solver': 'SciPy SuperLU', 'scalar_type': 'float64', 'mpi_size': 1},
                              limitations=domain.LIMITATIONS)
    raw.update(input_sha256=sha(input_path), sources_sha256=sha(output/'source_manifest.json'), backend=spec['backend'])
    raw['worker_artifacts'] = {p.relative_to(output).as_posix(): sha(p) for p in sorted(output.rglob('*'))
                               if p.is_file() and not p.relative_to(output).as_posix().startswith('sources/')
                               and p.name not in ('stdout.log', 'stderr.log', 'execution.json', 'command.json')}
    save(output/'worker_result.json', raw)


if __name__ == '__main__':
    main(sys.argv[1])
