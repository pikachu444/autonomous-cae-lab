"""Exact exponential-ramp bulk+shear SLS; distinct from backward-Euler/Prony.

This production implementation does not call the existing independent reference.
All five parameters and the complete viscous-strain state are explicit.
"""
from copy import deepcopy
import math
import numpy as np
from .law_native_tensors import finite, stiffness, compliance, tensor

KEYS = ('K0','G0','K1','G1','tau')


def validate_parameters(p):
    if not isinstance(p, dict) or set(p) != set(KEYS):
        raise ValueError('Single branch requires K0,G0,K1,G1,tau')
    values = finite([p[k] for k in KEYS], (5,), 'SLS coefficients')
    if min(values) <= 0:
        raise ValueError('All four bulk/shear moduli and tau must be positive')
    return dict(zip(KEYS, map(float,values)))


def state(*, time=0., strain_kelvin=None, viscous_strain_kelvin=None,
          dissipated_energy=0., work=0.):
    return {'time': float(time), 'strain_kelvin': list(strain_kelvin if strain_kelvin is not None else [0.]*6),
            'viscous_strain_kelvin': list(viscous_strain_kelvin if viscous_strain_kelvin is not None else [0.]*6),
            'dissipated_energy': float(dissipated_energy), 'work': float(work)}


def validate_state(s):
    if not isinstance(s,dict) or set(s) != set(state()):
        raise ValueError('SLS requires complete time, strain, viscous strain, cumulative dissipation/work')
    z = finite([s['time'],s['dissipated_energy'],s['work']], (3,), 'SLS state')
    if z[0] < 0 or z[1] < 0:
        raise ValueError('Initial time and cumulative dissipation must be nonnegative')
    for key in ('strain_kelvin','viscous_strain_kelvin'):
        if np.max(abs(tensor(finite(s[key],(6,),key)))) > .01+8*np.finfo(float).eps:
            raise ValueError('SLS admits physical strain/state components in [-.01,.01]')
    return deepcopy(s)


def integrate(parameters, initial, strain_kelvin, time):
    p, initial = validate_parameters(parameters), validate_state(initial)
    e = finite(strain_kelvin, (6,), 'SLS strain')
    time = float(finite([time], (1,), 'SLS time')[0])
    dt = time-initial['time']
    if dt <= 0 or np.max(abs(tensor(e))) > .01+8*np.finfo(float).eps:
        raise ValueError('SLS needs positive dt and physical strain components in [-.01,.01]')
    x = dt/p['tau']
    if not math.isfinite(x) or x <= 0:
        raise ValueError('SLS dt/tau must be positive finite (underflow is not replaced by zero)')
    C0, C1 = stiffness(p['K0'],p['G0']), stiffness(p['K1'],p['G1'])
    e0, ev0 = np.asarray(initial['strain_kelvin']), np.asarray(initial['viscous_strain_kelvin'])
    q0 = C1@(e0-ev0)
    de = e-e0
    z = C1@de
    a, one_minus_a = math.exp(-x), -math.expm1(-x)
    ramp = one_minus_a/x
    q = a*q0+ramp*z
    ev = e-compliance(q,p['K1'],p['G1'])
    # Stable exact positive quadratic form for integral(q:C1^-1:q/tau dt).
    A = -math.expm1(-2*x)/2
    b = math.tanh(x/2)/x
    if x < .125:
        xx = x*x
        delta = x*(1/12 + xx*(-1/120 + xx*(17/20160 + xx*(-31/362880
                + xx*(691/79833600 + xx*(-5461/6227020800 + xx*929569/10461394944000))))))
    else:
        delta = (x-2*math.tanh(x/2))/(x*x)
    v = q0+b*z
    dD = float(A*v@compliance(v,p['K1'],p['G1']) + delta*z@compliance(z,p['K1'],p['G1']))
    if x < .125:
        # g=(1-(1-exp(-x))/x)/x; direct subtraction loses small x.
        g = sum((-x)**n/math.factorial(n+2) for n in range(18))
    else:
        g = (1-ramp)/x
    dW = float(.5*(C0@(e+e0))@de + ramp*q0@de + g*z@de)
    psi = float(.5*e@C0@e + .5*q@compliance(q,p['K1'],p['G1']))
    result = state(time=time,strain_kelvin=e.tolist(),viscous_strain_kelvin=ev.tolist(),
                   dissipated_energy=initial['dissipated_energy']+dD,work=initial['work']+dW)
    sigma = C0@e+q
    if not np.isfinite(sigma).all() or not all(math.isfinite(v) for v in (psi,dD,dW)) or dD < -1e-12:
        raise ValueError('SLS nonfinite response or negative exact dissipation')
    return {'stress':sigma,'tangent':C0+ramp*C1,'state':result,'stored_energy':psi,
            'dissipated_energy':result['dissipated_energy'],
            'diagnostics':{'active_set':'single_branch','differentiable':True,
                'tangent_kind':'consistent_discrete','initial_state':deepcopy(initial),
                'dt':dt,'dt_over_tau':x,'decay':a,'ramp_factor':ramp,
                'branch_stress_kelvin':q.tolist(),'work_increment':dW,'dissipation_increment':dD,
                'local_residual':float(np.max(abs(q-a*q0-ramp*z))), 'committed':False}}
