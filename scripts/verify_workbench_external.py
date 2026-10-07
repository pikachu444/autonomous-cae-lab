"""Actual external calculation -> ASCII -> fit/DOE, with analytical comparison.

Use a new --output directory. No provider and no expected-output copy is used.
The retained observations are explicitly SYNTHETIC, from the same external law.
"""
import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np

from caelab.adapters.external_files import ExternalFilesAdapter, FileEvaluationFactory
from caelab.evaluation import run, read_result, save_evaluation, file_hash
from caelab.numerical import fit_model, run_doe, analyze_candidates, optimize


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=args.output.resolve(); root.mkdir(parents=True,exist_ok=False)
    program=Path(__file__).resolve().parents[1]/'examples/external_oscillator.py'
    axis={'column':'time_s','name':'time','unit':'s'}
    config={'label':'External SciPy damped oscillator','threads':1,'timeout':60,
        'variables':{'stiffness':{'lower':20.,'upper':200.,'unit':'N/m'},
                     'damping':{'lower':.2,'upper':8.,'unit':'N s/m'}},
        'command':[sys.executable,str(program)],'result':{'path':'response.csv','columns':{
            'displacement':{'column':'displacement_m','unit':'m','component':'x','location':'mass',
                            'coordinate_system':'global Cartesian','axis':axis},
            'force':{'column':'restoring_force_N','unit':'N','component':'x','location':'mass',
                     'coordinate_system':'global Cartesian','axis':axis}}}}
    conditions=[{'mass_kg':1.,'initial_displacement_m':.01,'duration_s':1.},
                {'mass_kg':1.7,'initial_displacement_m':.025,'duration_s':1.4},
                {'mass_kg':.8,'initial_displacement_m':-.012,'duration_s':.7}]
    experiments=[]; references=[]
    truth={'stiffness':90.,'damping':2.4}
    for index,condition in enumerate(conditions):
        source=run(ExternalFilesAdapter('external.oscillator',config),
            {'values':truth,'case_id':f'history-{index}','conditions':condition},output=root/f'observation-{index}')
        response=source['responses']['displacement']
        t=np.asarray(response['axes'][0]['values']); alpha=truth['damping']/(2*condition['mass_kg'])
        omega=np.sqrt(truth['stiffness']/condition['mass_kg']-alpha**2)
        reference=condition['initial_displacement_m']*np.exp(-alpha*t)*(np.cos(omega*t)+alpha/omega*np.sin(omega*t))
        error=float(np.max(np.abs(response['value']-reference)))
        assert error<2e-11, error
        references.append({'history':index,'analytical_max_abs_error_m':error,'limit_m':2e-11})
        experiments.append({'id':f'history-{index}','role':'holdout' if index==2 else 'fit',
            'settings':{'case_id':f'history-{index}','conditions':condition},'response':'displacement',
            'observations':response,'scale':.01,'weight':1.})
    variables=[{'id':'stiffness','unit':'N/m','lower':20.,'upper':200.,'value':60.},
               {'id':'damping','unit':'N s/m','lower':.2,'upper':8.,'value':4.}]
    factory=FileEvaluationFactory('external.oscillator',config,root/'candidates')
    start=time.perf_counter()
    fit=fit_model(factory,variables,experiments,options={'max_nfev':30},
        execution={'mode':'process','workers':2,'threads':1,'max_evaluations':160})
    save_evaluation(fit,root/'fit')
    assert fit['execution_status']=='SUCCEEDED',fit['failure_reason']
    assert abs(fit['parameters']['stiffness']-truth['stiffness'])<1e-4
    assert abs(fit['parameters']['damping']-truth['damping'])<1e-5
    assert max(curve['rmse'] for curve in fit['curves'])<1e-8
    doe=run_doe(factory,variables,settings={'conditions':conditions[0]},count=8,seed=27,
        execution={'mode':'process','workers':2,'threads':1})
    definition={'response':'force','unit':'N','reduction':'abs_max'}
    influence=analyze_candidates(doe,[definition])
    save_evaluation(doe,root/'doe'); save_evaluation(influence,root/'influence')
    optimization=optimize(factory,variables,definition,settings={'conditions':conditions[0]},seed=27,
        options={'max_generations':2,'population_size':6},execution={'mode':'process','workers':2,'threads':1})
    save_evaluation(optimization,root/'optimization')
    selected=read_result(root/'observation-0',selection={'responses':['displacement'],'rows':[7,14]})
    assert selected['responses']['displacement']['value']==experiments[0]['observations']['value'][7:14].tolist()
    receipt={'source_commit':'record separately from dirty source hashes','program_sha256':file_hash(program),
        'kind':'ACTUAL_LOCAL_EXTERNAL_CALCULATION','observations':'SYNTHETIC_SAME_LAW',
        'analytical_comparisons':references,'fit_parameters':fit['parameters'],
        'fit_rmse_m':[curve['rmse'] for curve in fit['curves']], 'fit_timing':fit['timing'],
        'doe_candidates':len(doe['candidates']),'optimization_candidates':len(optimization['candidates']),
        'optimization_termination':optimization['termination_reason'],'elapsed_seconds':time.perf_counter()-start,
        'raw_files':sum(1 for path in root.rglob('*') if path.is_file()),'physical_qualification':'UNKNOWN'}
    (root/'acceptance.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':
    main()
