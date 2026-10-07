"""Actual prepared MGIS two-property fit, distinct histories and holdout via jobs."""
import argparse
from copy import deepcopy
from pathlib import Path
import time

from caelab.storage import save_json
from caelab.workbench import Workbench


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--store',required=True)
    args=parser.parse_args()
    root=Path(args.store).resolve()
    root.mkdir(parents=True,exist_ok=False)
    bench=Workbench(root,configuration={'workers':2,'cpu_budget':4,'workspace_id':'mfront-fit'})
    truth={'youngs_modulus_mpa':275.,'poisson_ratio':.28}
    histories=[
        [(0.,[0.]*6),(.3,[.001,0.,0.,0.,0.,0.]),(.8,[-.0004,0.,0.,0.,0.,0.]),(1.2,[.0015,0.,0.,0.,0.,0.])],
        [(0.,[0.]*6),(.2,[0.,0.,0.,.0004,0.,0.]),(.7,[0.,0.,0.,-.0008,0.,0.]),(1.1,[0.,0.,0.,.0012,0.,0.])],
        [(0.,[0.]*6),(.15,[.0007,-.0002,.0001,.0003,0.,0.]),(.6,[-.0004,.0005,0.,-.0002,0.,0.])],
    ]
    def wait(job):
        end=time.monotonic()+600
        while time.monotonic()<end:
            state=bench.manager.status(job['id'])
            if state['state'] in {'SUCCEEDED','FAILED','CANCELLED','PARTIAL_FAILURE','INTERRUPTED'}:
                assert state['state']=='SUCCEEDED',state
                return bench.result(job['id'])
            time.sleep(.1)
        raise TimeoutError(job['id'])
    evidence=[]
    try:
        experiments=[]
        for index,history in enumerate(histories):
            settings={'material':truth,'temperature_k':293.15,
                      'history':[{'time_s':t,'strain':strain} for t,strain in history]}
            job=bench.submit('evaluate',{'backend':'material.mfront.prepared','settings':settings})
            observed=wait(job)
            # Independent Hooke reference for every stress component and time.
            lam=truth['youngs_modulus_mpa']*truth['poisson_ratio']/((1+truth['poisson_ratio'])*(1-2*truth['poisson_ratio']))
            mu=truth['youngs_modulus_mpa']/(2*(1+truth['poisson_ratio']))
            errors=[]
            for component,name in enumerate(('xx','yy','zz','xy','xz','yz')):
                for row,(_,strain) in enumerate(history):
                    expected=2*mu*strain[component]+(lam*sum(strain[:3]) if component<3 else 0.)
                    errors.append(abs(expected-observed['responses']['stress_'+name]['value'][row]))
            assert max(errors)<1e-10
            evidence.append({'job_id':job['id'],'reference_max_error_mpa':max(errors)})
            initial=deepcopy(settings)
            initial['material']={'youngs_modulus_mpa':180.,'poisson_ratio':.2}
            experiments.append({'id':f'history-{index}','role':'holdout' if index==2 else 'fit',
                'settings':initial,'response':'stress_xy' if index==1 else 'stress_xx',
                'observation_job':job['id'],'weight':1.,'scale':.1})
        started=time.perf_counter()
        job=bench.submit('fit',{'backend':'material.mfront.prepared',
            'variables':[{'id':'youngs_modulus_mpa','unit':'MPa','lower':100.,'upper':500.,'value':180.},
                         {'id':'poisson_ratio','unit':'1','lower':.05,'upper':.45,'value':.2}],
            'experiments':experiments,'options':{'max_nfev':25},
            'execution':{'mode':'serial','max_evaluations':160}})
        fitted=wait(job)
        assert abs(fitted['parameters']['youngs_modulus_mpa']-truth['youngs_modulus_mpa'])<1e-4
        assert abs(fitted['parameters']['poisson_ratio']-truth['poisson_ratio'])<1e-6
        assert max(curve['rmse'] for curve in fitted['curves'])<1e-8
        receipt={'kind':'ACTUAL_MGIS_FIT','observations':'SYNTHETIC_SAME_LAW','observation_checks':evidence,
                 'fit_job':job['id'],'parameters':fitted['parameters'],
                 'rmse_mpa':[curve['rmse'] for curve in fitted['curves']],
                 'timing':fitted['timing'],'elapsed_seconds':time.perf_counter()-started,
                 'physical_qualification':'UNKNOWN','limits':'Infinitesimal isotropic Elasticity; zero initial state'}
        save_json(root/'mfront_fit_receipt.json',receipt)
        print(receipt,flush=True)
    finally:
        bench.shutdown()


if __name__=='__main__':
    main()
