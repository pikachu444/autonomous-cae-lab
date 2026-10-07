"""A real external SciPy calculation producing ASCII, for adapter integration.

Run in a candidate directory containing candidate.json. This is a linear
mass/spring/damper model, not a replacement for structural or impact FE.
"""
import json
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp


def main():
    request=json.loads(Path('candidate.json').read_text(encoding='utf-8'))
    stiffness=request['values']['stiffness']
    damping=request['values']['damping']
    conditions=request.get('conditions',{})
    if set(conditions)-{'mass_kg','initial_displacement_m','initial_velocity_m_s','duration_s','samples'}:
        raise ValueError('Unknown oscillator condition')
    mass=float(conditions.get('mass_kg',1.0))
    displacement=float(conditions.get('initial_displacement_m',.01))
    initial_velocity=float(conditions.get('initial_velocity_m_s',0.))
    duration=float(conditions.get('duration_s',1.0))
    if mass<=0 or stiffness<=0 or damping<0 or duration<=0:
        raise ValueError('Mass, stiffness, duration must be positive and damping nonnegative')
    samples=conditions.get('samples',201)
    if type(samples) is not int or not 2 <= samples <= 1_000_000:
        raise ValueError('samples must be an integer between 2 and 1000000')
    time=np.linspace(0,duration,samples)
    solution=solve_ivp(lambda t,y:[y[1],(-stiffness*y[0]-damping*y[1])/mass],
        (0,duration),[displacement,initial_velocity],t_eval=time,method='DOP853',rtol=1e-10,atol=1e-12)
    if not solution.success or solution.y.shape!=(2,len(time)):
        raise RuntimeError(solution.message)
    position,velocity=solution.y
    np.savetxt('response.csv',np.column_stack((time,position,velocity,stiffness*position+damping*velocity)),
        delimiter=',',header='time_s,displacement_m,velocity_m_s,restoring_force_N',comments='',fmt='%.17g')
    Path('solver.json').write_text(json.dumps({'solver':'scipy.integrate.solve_ivp',
        'method':'DOP853','evaluations':solution.nfev,'conditions':conditions,
        'values':request['values'],'physical_qualification':'NOT_ASSESSED'}),encoding='utf-8')


if __name__=='__main__':
    main()
