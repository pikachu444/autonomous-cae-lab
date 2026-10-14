"""Create public Data→actual FELUPE comparison→Study→editable Report.

Run explicitly: python -m examples.experiment_report --store runs/d9-example --run
No providers, external solver, WSL, or hardware. Printed IDs are launch arguments,
not titles. Use the SAME --store when starting the desktop service.
"""
from copy import deepcopy
from pathlib import Path
import argparse
import json
import time

from caelab.workbench import Workbench
from caelab.experiment_calibration import default_calibration,default_acquisition
from caelab.material_document import default_draft as material_draft
from caelab.study_document import default_draft as study_draft
from caelab.report_document import default_draft as report_draft


def command(wb,doc,operation,arguments=None):
    return wb.document_command(doc['id'],operation,arguments or {},session_id=doc['session_id'],
        expected_generation=doc['generation'])


def finish(wb,job):
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        status=wb.manager.status(job['id'])
        if status['state'] in {'SUCCEEDED','FAILED','CANCELLED'}:
            if status['state']!='SUCCEEDED':raise RuntimeError(status)
            return wb.result(job['id'])
        time.sleep(.02)
    raise RuntimeError(wb.manager.status(job['id']))


def build(store):
    wb=Workbench(store)
    try:
        directory=Path(__file__).parent/'experiment-report'
        raw=wb.upload('전압.csv',(directory/'voltage.csv').read_bytes())
        certificate=wb.upload('합성 교정.txt',(directory/'calibration.txt').read_bytes())
        recipe={**default_calibration('N'),'input_unit':'V','coefficient_input_unit':'mV',
            'a':2.,'x0':0.,'x0_unit':'mV','b':0.,
            'input_range':{'minimum':0.,'maximum':18.,'unit':'mV'},
            'sensor_range':{'minimum':-1.,'maximum':24.,'unit':'mV'},
            'source':{'data_id':certificate['id'],'sha256':certificate['sha256'],'name':certificate['name']},
            'sensor':'공개 합성 센서','gauge':'합성 표점 A','displacement_role':'not_displacement'}
        common={'column':1,'component':'z','location':'gauge_A','measure':'force','frame':'lab',
            'axis':{'column':0,'name':'time','unit':'s'},'unit':'N','calibration':recipe}
        stress={**deepcopy(common),'unit':'MPa','component':'xx','location':'material_point',
            'measure':'infinitesimal_Cauchy','frame':'material_cartesian',
            'calibration':{**deepcopy(recipe),'a':.2,'output_unit':'MPa'}}
        acquisition={**default_acquisition(),'name':'공개 파일 시험','sample_rate_hz':1.,'duration_s':4.,
            'clock':'파일 time_s (명시)','device':'장비 없음',
            'channels':[{'name':'힘','role':'measurement','unit':'N','calibration':recipe}]}
        data=wb.document_open(kind='data',title='공개 센서 시험',draft={'data_id':raw['id'],
            'mapping':{'delimiter':',','skip_header':1,'columns':{'힘':common,'응력':stress}},'acquisition':acquisition})
        imported=command(wb,data,'data.import');finish(wb,imported['job'])
        data=command(wb,wb.document_read(data['id']),'document.save')['document']
        material=material_draft();material['settings']['time']=[0,1,2,3,4]
        material['settings']['deformation_gradient']=[[[1+e,0,0],[0,1,0],[0,0,1]] for e in [0,.001,.002,.003,.004]]
        model=wb.document_open(kind='material',title='공개 탄성 계산',draft=material)
        evaluated=command(wb,model,'material.evaluate');finish(wb,evaluated['job'])
        model=command(wb,wb.document_read(model['id']),'document.save')['document']
        def source(doc,job,response):
            run=next(r for r in doc['runs'] if r['job_id']==job)
            return {'document_id':doc['id'],'job_id':job,'input_revision':run['input_revision'],
                    'input_sha256':run['input_sha256'],'response':response}
        compared=wb.document_compare(source(data,imported['job']['id'],'응력'),
            source(model,evaluated['job']['id'],'stress_xx'))
        data=command(wb,wb.document_read(data['id']),'document.save')['document']
        record=next(r for r in data['comparisons'] if r['id']==compared['id'])
        comparison_ref={'kind':'comparison','document_id':data['id'],'document_kind':'data',
            'saved_revision':record['retained_revision'],'comparison_id':record['id'],
            'result_sha256':record['result_sha256'],'start':0,'count':256}
        force_ref={'kind':'result',**wb.document_result_reference(data['id'],imported['job']['id']),
            'selection':{'responses':['힘'],'source_rows':[1,2,3,4,5]}}
        study=study_draft();study['question']='교정 구간 내에서 탄성 계산과 합성 관측이 일치하는가?'
        study['evidence']=[{'id':'Eforce','label':'원값과 교정값','kind':'result','reference':force_ref,'note':'마지막 원행은 포화'},
            {'id':'Ecompare','label':'계산과 관측','kind':'comparison','reference':comparison_ref,'note':'원 단위 MPa 비교'}]
        study['next_observations']=[{'id':'Onext','question':'포화되지 않는 범위에서 독립 시험을 추가할 것인가?',
            'hypothesis_ids':[],'evidence_ids':['Eforce','Ecompare'],'status':'PLANNED','note':'사용자 판단 예제; 자동 승인 아님'}]
        study=wb.document_open(kind='study',title='공개 시험 판단',draft=study)
        study=command(wb,study,'document.save')['document']
        report=wb.document_open(kind='report')
        draft=report_draft();draft['title']='공개 시험 비교 보고서'
        for i,(title,reference) in enumerate([('센서 교정',force_ref),('관측과 계산',comparison_ref)]):
            draft['sections'].append({'id':'E'+str(i),'title':title,'text':'공개 합성 예제. 공학적 수용을 주장하지 않는다.',
                'include':True,'table':True,'curve':True,'asset':wb.report_capture(report['id'],reference)})
        report=command(wb,report,'report.update',{'draft':draft})['document']
        report=command(wb,report,'document.save')['document']
        return {'store':str(Path(store).resolve()),'data':data['id'],'material':model['id'],
            'study':study['id'],'report':report['id'],'comparison_rmse':compared['comparison']['rmse'],
            'engineering_release':'NOT_RELEASED'}
    finally:wb.shutdown()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store',required=True);parser.add_argument('--run',action='store_true')
    args=parser.parse_args(argv)
    if not args.run:parser.error('Use --run to explicitly import and evaluate the public example.')
    print(json.dumps(build(args.store),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
