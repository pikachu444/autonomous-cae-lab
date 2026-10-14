"""Create a real CSV/Data snapshot and manufactured native field, no solver.

Run with the project's ordinary research Python:
    python -m examples.post_curves <new-directory>
Then use tests/check_post_curves_native.py with installed pvpython.
"""
import json
from pathlib import Path
import time
from caelab.workbench import Workbench
from caelab.data_document import default_draft
from examples.post_comparison import write_grid


def create(directory):
    root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=False)
    fields=root/'native';fields.mkdir()
    points=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]
    frames=[]
    for i,stamp in enumerate([0.,.5,1.]):
        name='frame'+str(i)+'.vtu'
        write_grid(fields/name,points,[4*stamp,0.,0.],2.)
        frames.append((stamp,name))
    (fields/'load.pvd').write_text('<?xml version="1.0"?><VTKFile type="Collection" version="0.1" byte_order="LittleEndian"><Collection>'+
        ''.join('<DataSet timestep="'+str(t)+'" group="" part="0" file="'+name+'"/>' for t,name in frames)+
        '</Collection></VTKFile>',encoding='utf-8')
    payload=b'elapsed_ms,force_kN\n100,0\n1100,0.004\n'
    (root/'load-cell.csv').write_bytes(payload)
    wb=Workbench(root/'store')
    try:
        receipt=wb.upload('load-cell.csv',payload)
        draft=default_draft();draft['data_id']=receipt['id'];draft['mapping']['skip_header']=1
        field=draft['mapping']['columns']['response']
        field.update(unit='kN',component='x',location='load cell',measure='force',frame='global')
        field['axis'].update(name='elapsed',unit='ms')
        doc=wb.document_open(kind='data',title='하중 시험',draft=draft)
        reply=wb.document_command(doc['id'],'data.import',{},session_id=doc['session_id'],expected_generation=doc['generation'])
        job=reply['job']['id'];end=time.monotonic()+15
        while wb.manager.status(job)['state'] not in ('SUCCEEDED','FAILED') and time.monotonic()<end:
            time.sleep(.01)
        if wb.manager.status(job)['state']!='SUCCEEDED':
            raise RuntimeError(str(wb.manager.status(job)))
        doc=wb.document_read(doc['id'])
        wb.document_command(doc['id'],'document.save',{},session_id=doc['session_id'],expected_generation=doc['generation'])
        reference=wb.document_result_reference(doc['id'],job)
        curve=wb.post_curve_snapshot(reference,'response')
        native=wb.native_input(curve['id'])
        result={'native_field':str(fields/'load.pvd'),'curve_input':native,
            'store':str(root/'store'),'data_document':doc['id'],'reference':reference,
            'solver_execution':'NOT_PERFORMED','provider_execution':'NOT_PERFORMED'}
        (root/'input.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
        return result
    finally:
        wb.shutdown()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path)
    args=parser.parse_args();create(args.directory);print(args.directory/'input.json')
