"""Independent checker of retained actual FD/Taylor observations; never solves."""
import json
import sys
from pathlib import Path
from caelab.workbench import Workbench
from caelab.numerical_adjoint import assess_direction
from caelab.linear_adjoint_contract import CENTRAL_H,TAYLOR_H


def main(path):
    source=json.loads(Path(path).read_text(encoding='utf-8'));wb=Workbench(Path(source['workspace']))
    try:
        doc=wb.document_open(kind='numerical',document_id=source['document_id'])
        result=wb.document_result(doc['id'],source['job_id'])
        verify=result['gradient_verification'];assert verify['status']=='PASS'
        checked=[]
        for d in verify['directions']:
            samples={r['h']:r['value'] for r in d['samples']};g=d['adjoint_directional']
            args=(samples[CENTRAL_H],samples[-CENTRAL_H],[samples[h] for h in TAYLOR_H])
            correct=assess_direction(verify['base_value'],g,*args)
            bad_sign=assess_direction(verify['base_value'],-g,*args)
            bad_scale=assess_direction(verify['base_value'],g*1.1,*args)
            assert correct['status']=='PASS' and bad_sign['status']==bad_scale['status']=='FAIL'
            assert abs(g)>1e-6
            assert sum(r['R1']>correct['roundoff_floor'] for r in correct['taylor'])>=2
            checked.append({'direction':d['direction'],'correct':correct,'sign_corruption':bad_sign,'scale_corruption':bad_scale})
        counts=result['callback_counts'];assert counts['jacobian']>0 and counts['constraint_jacobian']>0
        assert result['algorithm']['finite_difference_jac'] is False
        print(json.dumps({'status':'PASS','directions':checked,'callbacks':counts,'solver_result':result['solver_result']},ensure_ascii=False,indent=2))
    finally:assert wb.shutdown()['joined']


if __name__=='__main__':main(sys.argv[1])
