"""Explicit public synthetic Data→fatigue example; no engineering fatigue curve."""
import argparse,time
from pathlib import Path
from caelab.workbench_client import Client
from caelab.data_document import default_draft
from caelab.fatigue import default_settings,BACKEND

def main():
    p=argparse.ArgumentParser();p.add_argument('--service',required=True);p.add_argument('--run',action='store_true')
    args=p.parse_args();client=Client(args.service)
    # Existing upload API is reused; no library, solver or provider setup.
    source=Path(__file__).with_name('cyclic-stress.csv')
    receipt=client.upload(source.name,source.read_bytes())
    draft=default_draft();draft['data_id']=receipt['id'];draft['mapping']['skip_header']=1
    spec=draft['mapping']['columns']['response']
    spec.update(unit='MPa',component='xx',location='synthetic_gauge',measure='infinitesimal_Cauchy',frame='specimen_fixed')
    spec['axis'].update(name='time',unit='s')
    data=client.document_open(kind='data',title='공개 합성 반복 응력',draft=draft)
    def change(doc,op,args=None):
        return client.document_command(doc['id'],op,args or {},session_id=doc['session_id'],expected_generation=doc['generation'])
    def wait(job):
        while client.status(job['id'])['state'] not in {'SUCCEEDED','FAILED','CANCELLED','REJECTED','INTERRUPTED'}:time.sleep(.1)
    imported=change(data,'data.import');wait(imported['job'])
    data=change(client.document_read(data['id']),'document.save')['document']
    value=default_settings();value.update(
        source={'result':client.document_result_reference(data['id'],imported['job']['id']),'response':'response','title':data['title']},
        sn_curve=[{'amplitude_mpa':50.,'cycles':1e7},{'amplitude_mpa':100.,'cycles':1e6},{'amplitude_mpa':200.,'cycles':1e5}],
        calibration={'reference':'공개 합성 예제, 실제 피로 시험 자료 아님','conditions':'단축 합성 응력 전용',
            'mean_min_mpa':0.,'mean_max_mpa':0.,'temperature_min_k':293.,'temperature_max_k':294.},
        temperature_k=293.15,repeat_block=True)
    doc=client.document_open(kind='simulation',title='합성 반복하중 평가',draft={'backend':BACKEND,'settings':value})
    doc=change(doc,'document.save')['document'];print(doc['id'])
    if args.run:
        receipt=change(doc,'simulation.evaluate');wait(receipt['job'])
        print(client.document_result(doc['id'],receipt['job']['id'])['diagnostics']['assessment'])
if __name__=='__main__':main()
