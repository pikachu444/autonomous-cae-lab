"""Read only the actual public S2 owner record provided on the command line."""
from pathlib import Path
import builtins
import json
import sys
from caelab.storage import canonical_hash
from caelab.workbench import Workbench
from caelab import evaluation,p1_temperature_transfer
from caelab.adapters.scikit_fem_spatial import _Spatial


def main(path):
    record=json.loads(Path(path).read_text(encoding='utf-8'));calls=[]
    def forbidden(*a,**kw):calls.append('FORBIDDEN');raise AssertionError('Reader attempted calculation/mapping')
    _Spatial.run=forbidden;_Spatial.run_adjoint=forbidden;evaluation.run=forbidden;p1_temperature_transfer.map_temperature=forbidden
    original=builtins.__import__
    def guard(name,*a,**kw):
        if name.split('.')[0] in {'skfem','scipy','dolfinx','petsc4py'}:raise AssertionError('Read imported solver')
        return original(name,*a,**kw)
    builtins.__import__=guard
    wb=Workbench(Path(record['workspace']))
    try:
        doc=wb.document_open(kind='numerical',document_id=record['document_id'])
        result=wb.document_result(doc['id'],record['job_id'])
        assert canonical_hash(result)==record['result_hash']
        candidate=result['best']['candidate_id']
        def view(query):
            return wb.numerical_evaluation_result(doc['id'],record['job_id'],candidate,evaluation_index=0,selection={'transfer':query})
        catalog=view({});assert catalog['transfers']
        iteration=max(r['iteration'] for r in catalog['transfers'] if r['id']=='TtoU')
        values=view({'id':'TtoU','iteration':iteration,'start':2,'count':5})
        assert values['exact_values_match'] is True
        assert values['original_source_and_receiver_are_different_meshes'] is True
        assert len(values['rows'])==5 and all(r['received']==r['mapped'] for r in values['rows'])
        assert all(r['valid_mask'] and r['available'] for r in values['rows'])
        assert values['metadata']['unit']=='K'
        loop=view({'id':'Picard','iteration':iteration,'start':1,'count':3})
        assert loop['exact_values_match'] is True and len(loop['rows'])==3
        bad=[]
        for query in ({'id':'unknown','iteration':0},{'id':'TtoU','iteration':iteration,'count':1025},
                      {'id':'TtoU','iteration':-1},{'path':'anything'}):
            try:view(query)
            except (ValueError,KeyError):bad.append(True)
            else:raise AssertionError('Invalid retained selection admitted')
        receipt={'read':'PASS','new_process':True,'solver_calls':len(calls),'mapping_calls':len(calls),
            'document_id':doc['id'],'job_id':record['job_id'],'candidate_id':candidate,
            'catalog_hash':canonical_hash(catalog),'mapping':values,'picard':loop,'rejected_queries':len(bad)}
        assert not calls
        print(json.dumps(receipt,ensure_ascii=False,indent=2))
    finally:
        builtins.__import__=original
        assert wb.shutdown()['joined']


if __name__=='__main__':main(sys.argv[1])
