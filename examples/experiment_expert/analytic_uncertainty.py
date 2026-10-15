"""Public explicit analytic example; no service, CAD, model/provider or device.

Run from the repository root:
  python examples/experiment_expert/analytic_uncertainty.py --output NEW_FOLDER
This explicitly imports the supplied public CSV, computes once, and writes the
existing evaluation artifact format. It is an API example, not a document owner.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from caelab.adapters.file_table import read_table
from caelab.experiment_calibration import default_calibration
from caelab.experiment_uncertainty import calibration_problem,propagate
from caelab.evaluation import save_evaluation,file_hash,read_result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    here=Path(__file__).resolve().parent
    certificate=here/'PUBLIC_CALIBRATION.txt'
    recipe={**default_calibration('N'),'input_unit':'V','coefficient_input_unit':'mV',
        'a':2.,'x0':1.,'x0_unit':'mV','b':.5,
        'source':{'data_id':'Dpublic','name':certificate.name,'sha256':file_hash(certificate)},
        'input_range':{'minimum':1.,'maximum':4.,'unit':'mV'},
        'sensor_range':{'minimum':0.,'maximum':5.,'unit':'mV'},
        'uncertainty':{'kind':'expanded','value':.1,'unit':'N','k':None,'correlation':'UNKNOWN','note':'공개 합성 교정 예제'}}
    mapping={'delimiter':',','skip_header':1,'columns':{'force':{'column':1,'unit':'N','component':'z',
        'location':'public_gauge','measure':'force','frame':'lab','calibration':recipe,
        'axis':{'column':0,'name':'time','unit':'s'}}}}
    # This is the explicit import, not a hidden recalibration when reading.
    imported=read_table(here/'PUBLIC_VOLTAGE.csv',mapping)
    problem=calibration_problem(imported['responses']['force'])
    provided={v['id']:{'kind':'standard','value':.0001 if v['id'].startswith('raw:') else .1,'unit':v['unit']}
        for v in problem['variables']}
    result=propagate(problem,{'uncertainties':provided,
        'dependence':{'kind':'independent_declared','note':'이 합성 계산 예제에만 명시적으로 설정한 조건'},
        'axis_uncertainty':'UNKNOWN'})
    save_evaluation(result,args.output) # refuses an existing result directory
    saved=read_result(args.output,verify='all') # no call to propagate/calibrate
    for row in saved['experiment_analysis']['rows']:
        print(row['original_value'],row['standard_uncertainty'],row['unit'],row['status'])
    print('모델 호출 0회. k/축 불확실성/전체 측정 불확실성/공학 승인은 미확인입니다.')
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError) as error:raise SystemExit(str(error))
