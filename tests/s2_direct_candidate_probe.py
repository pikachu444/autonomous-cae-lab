"""One independent direct Evaluation of an actual saved DE candidate (real FE)."""
from pathlib import Path
import json
import sys
import uuid
from caelab.workbench import Workbench
from caelab.evaluation_definition import execute
from caelab.research_execution import run_domain
from caelab.storage import canonical_hash


def main(record_path, destination):
    record=json.loads(Path(record_path).read_text(encoding='utf-8'))
    wb=Workbench(Path(record['workspace']))
    try:
        doc=wb.document_open(kind='numerical',document_id=record['document_id'])
        numerical=wb.document_result(doc['id'],record['job_id'])
        assert canonical_hash(numerical)==record['result_hash']
        run=next(row for row in doc['runs'] if row['job_id']==record['job_id'])
        settings=run['draft']['request']['inputs']['settings']
        compiled=wb.evaluation_documents.from_reference(settings['definition_ref'])
        best=numerical['best']
        saved=wb.numerical_evaluation_result(doc['id'],record['job_id'],best['candidate_id'],evaluation_index=0)
        assert saved['definition_sha256']==compiled['definition_sha256']
        output=Path(destination).resolve()/('independent-'+uuid.uuid4().hex)
        actual=execute(compiled,output,lambda model,folder:run_domain(wb,model,folder),values=best['values'])
        assert actual['execution_status']=='SUCCEEDED',actual['diagnostics']
        assert actual['initial_state_sha256']==saved['initial_state_sha256']
        assert canonical_hash(actual['responses'])==canonical_hash(saved['responses'])
        assert len(actual['iterations'])==len(saved['iterations'])
        receipt={'status':'PASS','controlled_evaluator':False,'new_evaluation_directory':str(output),
                 'saved_plan_result_sha256':record['result_hash'],'definition_sha256':compiled['definition_sha256'],
                 'candidate_id':best['candidate_id'],'values':best['values'],
                 'response_sha256':canonical_hash(actual['responses']),'responses':actual['responses'],
                 'initial_state_sha256':actual['initial_state_sha256'],
                 'stage_execution_count':actual['stage_execution_count'],'iteration_count':len(actual['iterations'])}
        (Path(destination)/'independent-direct-comparison.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(receipt,ensure_ascii=False,indent=2))
    finally:
        assert wb.shutdown()['joined']


if __name__=='__main__':main(sys.argv[1],sys.argv[2])
