"""Retained fit/candidate reads through the actual HTTP owners and Qt windows."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_numerical_evaluation_workflow import wait


def main(store,folder,document_id,job_id,candidate_id):
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication
    from scipy.interpolate import RBFInterpolator
    from unittest.mock import patch
    from contextlib import ExitStack
    from examples.s1_windows_transfer import local_service
    from apps.research.numerical_window import NumericalWindow
    from apps.research.request_plan_window import RequestPlanWindow
    from caelab.numerical_candidate_detail import table_rows
    from caelab.storage import canonical_hash
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=False)
    app=QApplication.instance() or QApplication([]);calls=[];window=None;child=None
    def forbidden(*args,**kwargs):calls.append('calculation');raise AssertionError('Retained inspection attempted calculation')
    with local_service(Path(store).resolve()) as (wb,client),ExitStack() as stack:
        jobs_before={row['id'] for row in wb.manager.list()}
        stack.enter_context(patch.object(wb.manager,'submit',forbidden))
        stack.enter_context(patch.object(RBFInterpolator,'__init__',forbidden))
        stack.enter_context(patch.object(RBFInterpolator,'__call__',forbidden))
        original=client.document_read(document_id);owner_hash=canonical_hash(original)
        result=client.document_result(document_id,job_id);result_hash=canonical_hash(result)
        klass=RequestPlanWindow if original['draft'].get('mode')=='request' else NumericalWindow
        window=klass(client,document_id=document_id,poll_interval=0);window.show()
        def settled(predicate=lambda:True):
            wait(app,lambda:not window._busy and not window._callbacks and predicate(),lambda:window.message.text())
        try:
            settled(lambda:window.document is not None)
            row=next(i for i,r in enumerate(window.document['runs']) if r['job_id']==job_id)
            window.runs.selectRow(row);window.retry_result();settled(lambda:job_id in window._result_cache)
            assert canonical_hash(window._result_cache[job_id])==result_hash
            row=next(i for i,r in enumerate(result['candidates']) if r['candidate_id']==candidate_id)
            window.candidates.selectRow(row);app.processEvents()
            assert window.selected_candidate()==candidate_id
            if isinstance(window,RequestPlanWindow):
                window.candidate_results_button.click();child=window._candidate_result_windows[-1]
            else:
                window.candidate_detail_button.click();child=window._candidate_detail_windows[-1]
            wait(app,lambda:child.view is not None and child._read_worker is None,lambda:child.status.text())
            child.timer.stop();view=child.view
            assert view['candidate']['candidate_id']==candidate_id
            frozen=deepcopy(view['fit_input']['inputs'])
            trials=[]
            for i,trial in enumerate(view['trials']):
                child.trials.setCurrentItem(child.trials.topLevelItem(i));app.processEvents()
                rows=table_rows(view,trial['experiment_id']);assert child.model.rows==rows
                trials.append({'experiment_id':trial['experiment_id'],'role':trial['role'],
                    'execution_status':trial['execution_status'],'retention':trial['retention'],'rows':rows})
            child.trials.setCurrentItem(child.trials.topLevelItem(0));app.processEvents()
            for width,height in ((1440,900),(1100,780)):
                window.resize(width,height);app.processEvents();window.canvas.draw()
                assert window.grab().save(str(folder/f'fit-plan-{width}.png'))
                child.resize(width,height);app.processEvents();child.canvas.draw()
                assert child.grab().save(str(folder/f'candidate-detail-{width}.png'))
            child.curve_mode.setCurrentIndex(2)
            for width,height in ((1440,900),(1100,780)):
                child.resize(width,height);app.processEvents();child.canvas.draw()
                assert child.grab().save(str(folder/f'candidate-weighted-residual-{width}.png'))
            child.tabs.setCurrentIndex(1);child.table.scrollTo(child.model.index(0,6));app.processEvents()
            assert child.grab().save(str(folder/'candidate-raw-weighted-table.png'))
            holdout=next((i for i,t in enumerate(view['trials']) if t['role']=='holdout'),None)
            if holdout is not None:
                child.tabs.setCurrentIndex(0);child.trials.setCurrentItem(child.trials.topLevelItem(holdout));app.processEvents()
                child.canvas.draw();assert child.grab().save(str(folder/'candidate-independent-holdout.png'))
                assert '목적함수에서 제외' in child.residual_summary.text()
            assert canonical_hash(client.document_read(document_id))==owner_hash
            assert canonical_hash(client.document_result(document_id,job_id))==result_hash
            assert {row['id'] for row in wb.manager.list()}==jobs_before and not calls
            record={'document_id':document_id,'job_id':job_id,'candidate_id':candidate_id,
                'source':view['source'],'candidate':view['candidate'],'fit_input':frozen,'trials':trials,
                'result_sha256':result_hash,'owner_sha256':owner_hash,'new_jobs':0,
                'solve_fit_predict_submissions':0,'qt_platform':app.platformName(),
                'residual_summary':child.residual_summary.text(),
                'source_hashes':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (
                    'apps/research/numerical_window.py','apps/research/request_plan_window.py',
                    'apps/research/numerical_candidate_detail_window.py','caelab/numerical.py',
                    'caelab/numerical_candidate_detail.py','caelab/numerical_candidate_evidence.py')}}
            (folder/'first-read.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({key:record[key] for key in ('document_id','job_id','candidate_id',
                'result_sha256','new_jobs','solve_fit_predict_submissions')},ensure_ascii=False),flush=True)
        finally:
            if child:child.close()
            if window:window._allow_close=True;window.close()
            app.processEvents();assert QThreadPool.globalInstance().waitForDone(5000)


if __name__=='__main__':main(*sys.argv[1:])
