"""Real external program recovery, with missing/duplicate/stale exchange checks."""
import argparse
from pathlib import Path
import sys

from caelab.adapters.external_files import ExternalFilesAdapter
from caelab.evaluation import run, save_evaluation
from caelab.numerical import export_batch, import_batch, analyze_candidates
from caelab.storage import save_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    root=Path(parser.parse_args().output).resolve()
    root.mkdir(parents=True,exist_ok=False)
    variables=[{'id':'stiffness','unit':'N/m','lower':40.,'upper':140.},
               {'id':'damping','unit':'N s/m','lower':.8,'upper':5.}]
    values=[{'stiffness':50.,'damping':1.},{'stiffness':90.,'damping':2.4},
            {'stiffness':120.,'damping':4.}]
    settings={'conditions':{'mass_kg':1.,'initial_displacement_m':.01,'duration_s':1.}}
    manifest=export_batch(variables,values,root/'export',case_id='synthetic-exchange',settings=settings)
    config={'variables':{v['id']:{k:v[k] for k in ('lower','upper','unit')} for v in variables},
        'command':[sys.executable,str(Path(__file__).resolve().parents[1]/'examples/external_oscillator.py')],
        'result':{'path':'response.csv','columns':{'force':{'column':'restoring_force_N','unit':'N',
            'component':'x','location':'mass','axis':{'column':'time_s','name':'time','unit':'s'}}}}}
    returned=[]
    for row in manifest['candidates'][:2]:
        result=run(ExternalFilesAdapter('external.oscillator',config),
            {**settings,'values':row['values'],'case_id':row['case_id']},output=root/row['candidate_id'])
        result.update({key:row[key] for key in ('candidate_id','case_id','exchange_id','values')})
        returned.append(result)
    recovered=import_batch(manifest,returned)
    assert recovered['imported_count']==2 and recovered['missing_count']==1
    assert recovered['candidates'][2]['execution_status']=='NOT_EVALUATED'
    save_evaluation(recovered,root/'recovered')
    rejected=[]
    stale=export_batch(variables,values,root/'new-export',case_id=manifest['case_id'],settings=settings)
    for label,plan,rows in [('duplicate',manifest,returned+returned[:1]),('stale',stale,returned),
                           ('wrong-values',manifest,[{**returned[0],'values':values[1]}])]:
        try:
            import_batch(plan,rows)
        except ValueError as error:
            rejected.append({'case':label,'reason':str(error)})
        else:
            raise AssertionError(label)
    analysis=analyze_candidates(recovered,[{'response':'force','unit':'N','reduction':'abs_max'}])
    save_json(root/'receipt.json',{'status':'PASS','imported':2,'unknown':1,
        'rejections':rejected,'analysis':analysis,'qualification':'SYNTHETIC_INTEGRATION_ONLY'})
    print('Actual external exchange passed:',root,flush=True)


if __name__=='__main__':
    main()
