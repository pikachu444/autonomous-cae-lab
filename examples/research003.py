"""Public D7 inputs. Creating/saving is separate from --run."""
import argparse
import json
import time
from caelab.workbench_client import Client
from caelab.pde_document import default_draft
from caelab import user_material
from caelab.jobs import TERMINAL


def main(argv=None):
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--service',required=True)
    parser.add_argument('--case',choices=('ode','weak','user-build','user-evaluate'),default='ode')
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args(argv);client=Client(args.service)
    if args.case in ('ode','weak'):
        kind='pde';draft=default_draft('pde.scipy.ode' if args.case=='ode' else 'pde.fenicsx.dimensioned')
    else:
        kind='material';settings=user_material.default_settings()
        settings['action']='evaluate' if args.case=='user-evaluate' else 'build'
        draft={'backend':user_material.BACKEND,'settings':settings}
        print('Source SHA256:',user_material.source_hash(settings['source']))
    document=client.document_open(kind=kind,title={'ode':'온도 초기값','weak':'차원 약형식','user-build':'사용자 법칙 빌드','user-evaluate':'사용자 법칙 적분'}[args.case],draft=draft)
    def command(operation):
        nonlocal document
        result=client.document_command(document['id'],operation,{},session_id=document['session_id'],expected_generation=document['generation'])
        document=result['document'];return result
    command('document.save');job=None
    if args.run:
        job=command(kind+'.evaluate')['job']['id'];deadline=time.monotonic()+420
        while time.monotonic()<deadline:
            status=client.status(job)
            if status['state'] in TERMINAL:break
            time.sleep(.2)
        else:raise RuntimeError('작업은 계속 보존됩니다. Runner에서 상태를 확인하세요: '+job)
        document=client.document_read(document['id']);command('document.save')
        print(json.dumps({'job_id':job,'status':status['state']},ensure_ascii=False))
    print(json.dumps({'document_id':document['id'],'kind':kind,'service':args.service,'submitted':bool(job)},ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
