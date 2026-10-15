"""DP-LINEAR-KAPPA-DEV/1, backward-Euler nonassociated small-strain update.

p=-tr(sigma)/3, q=sqrt(3/2*s:s), f=q-alpha*p-k0-H*kappa,
g=q-beta*p. kappa is accumulated equivalent DEVIATORIC plastic strain.
At the cone apex kappa is NOT the plastic multiplier. See EQUATIONS_KO.md.
Pure trial function: no passed initial state is ever mutated.
"""
from copy import deepcopy
import math
import numpy as np
from .law_native_tensors import I6, DEV, finite, stiffness, moduli

MODEL = 'drucker_prager_linear'
VARIANT = 'DP-LINEAR-KAPPA-DEV/1'
KEYS = ('E', 'nu', 'alpha', 'beta', 'k0', 'H')
# New DP numerical limits, fixed before the first execution. Existing limits untouched.
LIMITS = {'yield_relative': 2e-11, 'yield_absolute_over_E': 2e-14,
          'tangent_relative': 2e-6, 'tangent_absolute_over_E': 2e-10,
          'finite_difference_steps': [1e-6, 1e-7, 1e-8], 'strain_abs_max': .05}


class LocalFailure(ValueError):
    def __init__(self, message, evidence):
        super().__init__(message)
        self.evidence = deepcopy(evidence)


def validate_parameters(parameters):
    if not isinstance(parameters, dict) or set(parameters) != set(KEYS):
        raise ValueError('DP requires exactly E, nu, alpha, beta, k0, H (direct coefficients)')
    p = dict(zip(KEYS, finite([parameters[k] for k in KEYS], (6,), 'DP coefficients')))
    if not (p['E'] > 0 and -.99 <= p['nu'] < .495 and
            0 <= p['beta'] <= p['alpha'] <= 1 and p['k0'] > 0 and p['H'] >= 0):
        raise ValueError('DP: E,k0>0; -.99<=nu<.495; 0<=beta<=alpha<=1; H>=0')
    if not np.isfinite(list(moduli(p['E'], p['nu']))).all():
        raise ValueError('Elastic moduli overflow')
    return {key: float(value) for key, value in p.items()}


def state(*, time=0., strain_kelvin=None, plastic_strain_kelvin=None, kappa=0.):
    return {'time': float(time), 'strain_kelvin': list(strain_kelvin if strain_kelvin is not None else [0.]*6),
            'plastic_strain_kelvin': list(plastic_strain_kelvin if plastic_strain_kelvin is not None else [0.]*6),
            'kappa': float(kappa)}


def validate_state(initial):
    if not isinstance(initial, dict) or set(initial) != {'time','strain_kelvin','plastic_strain_kelvin','kappa'}:
        raise ValueError('DP initial state requires time, strain_kelvin, plastic_strain_kelvin, kappa')
    scalars = finite([initial['time'], initial['kappa']], (2,), 'DP state')
    e = finite(initial['strain_kelvin'], (6,), 'DP initial strain')
    ep = finite(initial['plastic_strain_kelvin'], (6,), 'DP plastic strain')
    if scalars[0] < 0 or scalars[1] < 0 or max(abs(e)) > LIMITS['strain_abs_max']:
        raise ValueError('DP initial time/kappa nonnegative and bounded small strain required')
    if np.sqrt(2/3)*np.linalg.norm(DEV@ep) > scalars[1] + 1e-12:
        raise ValueError('kappa cannot be below the norm of accumulated deviatoric plastic strain')
    return deepcopy(initial)


def invariants(stress):
    s = DEV@np.asarray(stress)
    return -float(I6@stress)/3, float(np.sqrt(1.5)*np.linalg.norm(s))


def integrate(parameters, initial, strain_kelvin, time):
    """Return stress, true discrete tangent (possibly unavailable), state and diagnostics."""
    p = validate_parameters(parameters)
    initial = validate_state(initial)
    e = finite(strain_kelvin, (6,), 'DP strain')
    t = float(finite([time], (1,), 'DP time')[0])
    if t < initial['time'] or max(abs(e)) > LIMITS['strain_abs_max']:
        raise ValueError('DP time must not decrease; |Kelvin strain|<=.05')
    K, G = moduli(p['E'], p['nu'])
    Ce = stiffness(K, G)
    ep0 = np.asarray(initial['plastic_strain_kelvin'])
    trial = Ce@(e-ep0)
    ptr, qtr = invariants(trial)
    s = DEV@trial
    k = p['k0'] + p['H']*initial['kappa']
    ftr = qtr - p['alpha']*ptr - k
    scale = max(p['k0'], qtr, abs(p['alpha']*ptr), 1e-30)
    tol = LIMITS['yield_absolute_over_E']*p['E'] + LIMITS['yield_relative']*scale
    d = {'variant': VARIANT, 'trial_stress_kelvin': trial.tolist(), 'trial_p': ptr,
         'trial_q': qtr, 'trial_yield': ftr, 'local_tolerance': tol,
         'initial_state': deepcopy(initial), 'differentiable': True,
         'tangent_kind': 'consistent_discrete', 'iterations': 0, 'substeps': 1}
    ep, kap, gamma, C = ep0.copy(), float(initial['kappa']), 0., Ce.copy()
    stress = trial.copy()
    if ftr <= tol:
        active = 'elastic'
        if abs(ftr) <= tol:
            d.update(differentiable=False, transition='yield_surface', tangent_side='elastic')
    else:
        D = 3*G + p['alpha']*K*p['beta'] + p['H']
        gamma = ftr/D
        qcone = qtr-3*G*gamma
        if qcone > tol and qtr > 0:
            active = 'cone'
            n = 1.5*s/qtr
            ep += gamma*(n+p['beta']*I6/3)
            kap += gamma
            q, pressure = qcone, ptr+K*p['beta']*gamma
            stress = s*(q/qtr)-pressure*I6
            C = (K*np.outer(I6,I6) + 2*G*(q/qtr)*DEV
                 + 4*G*G*gamma/qtr*np.outer(n,n)
                 - np.outer(2*G*n+K*p['beta']*I6, 2*G*n+K*p['alpha']*I6)/D)
        else:
            active = 'apex'
            if p['alpha'] == 0 or p['beta'] == 0:
                d.update(active_set=active, partial_stress_kelvin=trial.tolist(),
                         failure='No admissible apex return with alpha*beta=0', committed=False)
                raise LocalFailure(d['failure'], d)
            # Generalized flow at q=0: dev plastic norm = qtr/(3G), NOT gamma.
            dev_increment = qtr/(3*G)
            kap += dev_increment
            pressure = -(p['k0']+p['H']*kap)/p['alpha']
            gamma = (pressure-ptr)/(K*p['beta'])
            if gamma < dev_increment - tol/(3*G):
                raise LocalFailure('Apex subgradient is outside the admissible ball', d)
            ep += s/(2*G) + p['beta']*gamma*I6/3
            stress = -pressure*I6
            if qtr > tol:
                n = 1.5*s/qtr
                C = (2*p['H']/(3*p['alpha']))*np.outer(I6,n)
            elif p['H'] == 0:
                C = np.zeros((6,6))
            else:
                C = None
                d.update(differentiable=False, transition='apex_trial_axis_norm',
                         tangent_side='directional_only; no unique 6x6 derivative')
            if abs(qcone) <= tol:
                d.update(differentiable=False, transition='cone_apex_boundary')
            d.update(apex_deviatoric_kappa_increment=dev_increment,
                     apex_subgradient_norm=(dev_increment/gamma if gamma else None))
    pressure, q = invariants(stress)
    residual = q-p['alpha']*pressure-p['k0']-p['H']*kap
    # Check the actual update, including stress/strain consistency; never average failures.
    elastic_residual = float(np.linalg.norm(stress-Ce@(e-ep), ord=np.inf))
    if (not np.isfinite(stress).all() or not np.isfinite(ep).all() or not math.isfinite(kap)
            or elastic_residual > 20*tol or (active != 'elastic' and abs(residual) > 20*tol)):
        d.update(active_set=active, local_residual=residual, elastic_residual=elastic_residual,
                 partial_stress_kelvin=stress.tolist(), committed=False)
        raise LocalFailure('DP return mapping residual/finite check failed', d)
    accepted = state(time=t, strain_kelvin=e.tolist(), plastic_strain_kelvin=ep.tolist(), kappa=kap)
    d.update(active_set=active, local_residual=residual, elastic_residual=elastic_residual,
             p=pressure, q=q, plastic_multiplier=gamma, kappa_increment=kap-initial['kappa'],
             partial_stress_kelvin=stress.tolist(), committed=False)
    return {'stress': stress, 'tangent': C, 'state': accepted, 'diagnostics': d,
            'stored_energy': float(.5*(e-ep)@Ce@(e-ep) + .5*p['H']*kap*kap),
            'dissipated_energy': None}
