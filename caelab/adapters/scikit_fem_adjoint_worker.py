"""Transpose solve of a retained S1 primal system, not a new FE assembly/solver."""
from pathlib import Path
import json
import warnings


def adjoint(settings, output, spec):
    import numpy as np
    from scipy.sparse import csr_matrix
    from scipy.sparse.linalg import spsolve, MatrixRankWarning
    from caelab.linear_adjoint_contract import admit_settings, RESIDUAL_LIMIT
    from caelab.adapters.scikit_fem_worker import sha, save, _scalar
    request = admit_settings(spec['backend'], settings, spec['adjoint']['request'])
    source = output / 'primal'
    for name, expected in spec['adjoint']['files'].items():
        if Path(name).name != name or sha(source / name) != expected:
            raise ValueError('Retained primal bytes differ from the admitted source')
    original = json.loads((source/'input.json').read_text(encoding='utf-8'))
    raw = json.loads((source/'worker_result.json').read_text(encoding='utf-8'))
    if (original != {'backend': spec['backend'], 'settings': settings}
            or raw['execution_status'] != 'SUCCEEDED' or raw['backend'] != spec['backend']
            or raw['input_sha256'] != sha(source/'input.json')
            or raw['worker_artifacts'].get('primal-system.npz') != sha(source/'primal-system.npz')):
        raise ValueError('Adjoint requires the exact successful primal input/operator')
    with np.load(source/'primal-system.npz', allow_pickle=False) as archive:
        expected = {'data','indices','indptr','shape','rhs','solution','free','dirichlet','weights','unit_load'}
        if set(archive.files) != expected:
            raise ValueError('Retained primal system schema differs')
        a = {name: archive[name].copy() for name in archive.files}
    matrix = csr_matrix((a['data'], a['indices'], a['indptr']), shape=tuple(a['shape']))
    u, w, rhs, free, fixed = (a[k] for k in ('solution','weights','rhs','free','dirichlet'))
    n = len(u)
    if (matrix.shape != (n,n) or not len(free)
            or sorted(np.concatenate((free,fixed)).tolist()) != list(range(n))
            or any(v.shape != (n,) for v in (w,rhs,a['unit_load']))
            or any(not np.isfinite(v).all() for v in (matrix.data,u,w,rhs,a['unit_load']))):
        raise ValueError('Primal free/constrained DOF partition or numeric system is invalid')
    aff = matrix[free][:,free].tocsc()
    condensed_rhs = rhs[free] - matrix[free][:,fixed] @ u[fixed]
    primal_residual = aff @ u[free] - condensed_rhs
    bnorm = float(np.linalg.norm(condensed_rhs))
    pres = float(np.linalg.norm(primal_residual)) / (bnorm or 1.)
    mean = float(w @ u)
    if pres > RESIDUAL_LIMIT or abs(mean-raw['responses']['mean_temperature']['value']) > 1e-10:
        raise ValueError('Primal residual/reduction is not the exact accepted mean-temperature solve')
    save(output/'progress.json', {'phase':'ADJOINT_TRANSPOSE_STARTED','primal_solve_calls':0,
                                'adjoint_solve_calls':0,'free_dofs':len(free)})
    with warnings.catch_warnings():
        warnings.simplefilter('error', MatrixRankWarning)
        lam = spsolve(aff.T.tocsc(), w[free], permc_spec='COLAMD', use_umfpack=False)
    if not np.isfinite(lam).all():
        raise ValueError('Adjoint transpose solve is nonfinite')
    adj_residual = aff.T @ lam - w[free]
    adj_rhs = float(np.linalg.norm(w[free]))
    ares = float(np.linalg.norm(adj_residual)) / (adj_rhs or 1.)
    k = settings['conductivity']['value']
    terms = {
        'conductivity': (0., float(-lam @ ((matrix[free] @ u)/k)), 'K/(W/(m*K))'),
        'heat_source': (0., float(lam @ a['unit_load'][free]), 'K/(W/m^3)'),
        'boundary_temperature': (float(w[fixed].sum()), float(-lam @ (matrix[free][:,fixed] @ np.ones(len(fixed)))),
                                 'K/'+settings['boundary_temperature']['unit']),
        'conductivity_reference_temperature': (0., 0., 'K/K')}
    derivatives = {name: {'value': direct+implicit, 'direct': direct, 'residual_term': implicit,
                         'unit': unit, 'input_id':name,'response':'mean_temperature',
                         'state':'steady_linear_fixed_mesh', 'algorithm':'discrete_linear_adjoint'}
                   for name in request['inputs'] for direct,implicit,unit in [terms[name]]}
    np.savez_compressed(output/'adjoint-system.npz', free=free, dirichlet=fixed, adjoint=lam,
                        response_derivative=w, primal_solution=u, adjoint_rhs=w[free],
                        adjoint_residual=adj_residual)
    receipt = {'algorithm':'discrete_linear_adjoint', 'equation':'A_FF.T lambda = J_u[F]',
        'solver':'scipy.sparse.linalg.spsolve', 'factorization':'SuperLU', 'permc_spec':'COLAMD',
        'use_umfpack':False, 'primal_solve_calls':0, 'adjoint_solve_calls':1, 'assembly_calls':0,
        'free_dofs':int(len(free)), 'constrained_dofs':int(len(fixed)),
        'primal_relative_residual':pres, 'adjoint_relative_residual':ares,
        'adjoint_rhs_norm':adj_rhs, 'mean_contraction_K':mean,
        'response_reduction':'integral(P1 T)/area using original quadrature weights',
        'primal_reference':spec['adjoint']['reference'],
        'primal_system_sha256':sha(source/'primal-system.npz'), 'finite_difference_calls':0}
    save(output/'adjoint.json', {'receipt':receipt, 'derivatives':derivatives})
    save(output/'progress.json', {'phase':'ADJOINT_TRANSPOSE_FINISHED',**receipt})
    passed = ares <= RESIDUAL_LIMIT
    return {'execution_status':'SUCCEEDED' if passed else 'REJECTED',
            'responses': {name:_scalar(row['value'],row['unit'],name,'discrete_adjoint') for name,row in derivatives.items()},
            'derivatives':derivatives,
            'checks':[{'name':'adjoint_relative_residual','status':'PASS' if passed else 'FAIL',
                       'observed':ares,'limit':RESIDUAL_LIMIT}], 'diagnostics':{'adjoint':receipt}}
