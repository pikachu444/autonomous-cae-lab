"""Explicit public SYNTHETIC example, never automatic material defaults.

Only an explicit example action or the runnable imports these values. The
production editor and engine start with missing calibration coefficients.
"""
from __future__ import annotations
from copy import deepcopy
import csv
import io

from .fatigue_tensor import COMPONENTS
from .fatigue_life import calibration_draft
from .fatigue_strain import default_settings


def synthetic_calibration():
    c = calibration_draft()
    c.update(E=200000., sigma_f=1000., epsilon_f=.5, b=-.1, c=-.5,
        cycles_min=1., cycles_max=1e9, strain_amplitude_min=1e-6, strain_amplitude_max=1.,
        max_stress_min=1e-6, max_stress_max=20000., temperature_min_k=293., temperature_max_k=294.,
        reference='PUBLIC SYNTHETIC EXAMPLE, not a measured material',
        conditions='Fully reversed axial coefficients; supplied nonproportional tensor history',
        failure_definition='Demonstration Nf cycles / Miner D=1, no material release', cyclic_state='STABILIZED')
    return c


def csv_bytes():
    n = 1000.  # Independently forward-generated synthetic reference, in cycles.
    amplitude = .005 * (2*n)**(-.1) + .5 * (2*n)**(-.5)
    stress = 1000. * (2*n)**(-.1)
    q, r = [1,0,-1,0,1,0,-1,0,1], [0,1,0,-1,0,1,0,-1,0]
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(['time_s', *('e_'+c for c in COMPONENTS), *('s_'+c for c in COMPONENTS)])
    for i, (x, y) in enumerate(zip(q, r)):
        writer.writerow([format(v,'.17g') for v in [i*.25,
            amplitude*x, -.3*amplitude*x, -.3*amplitude*x, .1*amplitude*y, 0., 0.,
            stress*x, 0., 0., .1*stress*y, 0., 0.]])
    return stream.getvalue().encode('utf-8')


def data_draft(data_id):
    from .data_document import default_draft
    d=default_draft();d['data_id']=data_id;d['mapping'].update(skip_header=1,columns={})
    for role, prefix, offset, unit, measure in (
        ('strain','e',1,'1','infinitesimal_total_strain_tensor'),
        ('stress','s',7,'MPa','infinitesimal_Cauchy')):
        for index, component in enumerate(COMPONENTS):
            d['mapping']['columns'][prefix+'_'+component] = dict(column=offset+index, unit=unit,
                component=component, location='public synthetic material point', frame='specimen_fixed_model_basis',
                measure=measure, axis=dict(column=0,name='time',unit='s'))
    d['test_metadata']={'test_id':'public-synthetic-nonproportional-tensor',
                        'specimen':'NOT_A_REAL_MATERIAL', 'protocol':'Two supplied synthetic cycles',
                        'temperature':'293.15 K assumed, not measured'}
    return d


def settings(reference, *, method='CP_SWT', mean_stress='SWT'):
    s=default_settings(method,mean_stress)
    components=COMPONENTS if method=='CP_SWT' else COMPONENTS[:1]
    s.update(source={'result':deepcopy(reference), 'title':'공개 합성 tensor (실재 재료 아님)',
                     'channels': {'strain':{c:'e_'+c for c in components},
                        **({'stress':{c:'s_'+c for c in components}} if mean_stress=='SWT' else {})}},
             calibration=synthetic_calibration(),temperature_k=293.15,repeat_block=True)
    s['interpretation'].update(strain_shear='TENSOR', history_state='STABILIZED_CYCLIC',
                              constitutive_source='Explicitly supplied SYNTHETIC stress/total strain; no constitutive solve')
    s['search'].update(polar_steps=3,refinement_levels=1)
    return s
