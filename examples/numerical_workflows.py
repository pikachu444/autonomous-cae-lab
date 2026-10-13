"""Small public FELUPE study using the shipped evaluator and actual document owners.

Default prepares saved editable documents. --run explicitly evaluates.
No native FE process, provider or engineering qualification.
"""
from copy import deepcopy
from pathlib import Path
import argparse
import time
from caelab.material_document import default_draft
from caelab.numerical_document import request_draft
from caelab.storage import canonical_hash
from caelab.workbench import Workbench


def save(wb,doc):
    return wb.document_command(doc['id'],'document.save',{},session_id=doc['session_id'],
        expected_generation=doc['generation'])['document']


def run(wb,doc):
    job=wb.document_command(doc['id'],'numerical.run',{},session_id=doc['session_id'],
        expected_generation=doc['generation'])['job']['id']
    while wb.manager.status(job)['state'] not in {'SUCCEEDED','FAILED','CANCELLED','PARTIAL_FAILURE','REJECTED'}:
        time.sleep(.05)
    state=wb.manager.status(job)
    doc=save(wb,wb.document_read(doc['id']))
    if state['state']!='SUCCEEDED':
        raise RuntimeError(str(state))
    return doc,job,wb.document_result_reference(doc['id'],job)


def main():
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--store',type=Path,required=True)
    parser.add_argument('--run',action='store_true',help='Explicitly execute the small existing FELUPE evaluations')
    args=parser.parse_args()
    wb=Workbench(args.store)
    try:
        model=save(wb,wb.document_open(kind='material',title='공개 탄성 재료',draft=default_draft()))
        source={'document_id':model['id'],'kind':'material','saved_revision':model['saved_revision'],
                'input_revision':model['input_revision'],'input_sha256':canonical_hash(model['draft'])}
        variables=[dict(id='E',value=1000.,lower=500.,upper=1500.,
                        unit=model['draft']['settings']['stress_unit'],transform='linear')]
        def plan(title,operation,inputs,budget):
            draft=request_draft({'purpose':title,'operation':operation,'inputs':inputs,
                                 'budget':{'evaluations':budget}},source=source)
            return save(wb,wb.document_open(kind='numerical',title=title,draft=draft))
        def doe(title,points):
            return plan(title,'doe',{'backend':'material.felupe','settings':deepcopy(model['draft']['settings']),
                'variables':variables,'candidates':[{'values':{'E':point}} for point in points]},len(points))
        training=doe('탄성계수 학습 자료',[600.,1000.,1400.])
        holdout=doe('별도 검증 자료',[800.,1200.])
        print('Material:',model['id'])
        print('Training Plan:',training['id'])
        print('Holdout Plan:',holdout['id'])
        if not args.run:
            print('PREPARED_ONLY: open the Plans in Numerical; no evaluations submitted.')
            return
        training,_,train_ref=run(wb,training)
        holdout,_,hold_ref=run(wb,holdout)
        response=dict(response='stress_xx',unit=variables[0]['unit'],reduction='final',
                      component='xx',location='material_point')
        rbf=plan('탄성 응답 대리모델','surrogate',{'result_refs':{'training':train_ref,'holdout':hold_ref},
            'response':response,'points':[]},1)
        rbf,_,model_ref=run(wb,rbf)
        query=plan('저장 모델의 새 점 예측','surrogate',
            {'result_refs':{'model':model_ref},'points':[{'E':1100.}]},1)
        query,qjob,_=run(wb,query)
        confirmation=doe('1100 계수의 실제 확인',[1100.])
        confirmation,cjob,_=run(wb,confirmation)
        predicted=wb.document_result(query['id'],qjob)['predictions'][0]
        actual=wb.document_result(confirmation['id'],cjob)['candidates'][0]
        print('Stored model:',rbf['id'])
        print('Prediction:',query['id'],predicted['execution_status'],predicted['values'])
        print('Actual confirmation:',confirmation['id'],actual['execution_status'],actual['values'])
        print('The two records remain separate; no automatic coefficient adoption.')
    finally:
        wb.shutdown()


if __name__=='__main__':
    main()
