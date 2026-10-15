"""Root integration scenario derived from Pro C2, with C01 recovery excluded.

P=mu*t is the explicit test backend. This verifies transport, managed execution
and saved readers; it does not establish FELUPE or engineering qualification.
"""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys

from caelab.numerical_candidate_detail import read_candidate_detail, table_rows
from caelab.numerical_candidate_evidence import CAPTURE, SUCCESS
from caelab.storage import canonical_hash, load_json, save_json
from .c2_fixtures import SyntheticPoint, fit_and_detail, make_processed_plan, make_workbench
from .helpers import command


def test_canonical_owner_fit_detail_holdout_saved_reader_without_recovery(tmp_path):
    original = tmp_path / '원자료 보존'
    w = make_workbench(original)
    SyntheticPoint.calls = []; SyntheticPoint.outcome = 'SUCCEEDED'
    try:
        bundle = fit_and_detail(w, make_processed_plan(w))
        plan = w.document_read(bundle['plan']['id'])
        view, packet = bundle['view'], bundle['args']['frozen_inclusion']
        digest = canonical_hash(bundle['fit_result'])
        assert view['fit_input']['inputs']['frozen_inclusion'] == packet
        assert view['fit_input']['data_inclusion']['status'] == 'CANONICAL_CHECK_PASSED'
        assert [trial['role'] for trial in view['trials']] == ['fit', 'holdout']
        assert all(trial['execution_status'] == 'SUCCEEDED' for trial in view['trials'])
        rows = table_rows(view, view['trials'][0]['experiment_id'])
        assert len(rows) == 14 and all(row['source_row'] is None for row in rows)
        assert all(row['sample_id'] and row['coordinate_sample_id'] and row['value_lineage']['terms'] for row in rows)
        assert any(row['sample_weight'] == 2. for row in rows if row['included'])
        summary = read_candidate_detail(w.numerical_documents, plan['id'], bundle['fit_job']['id'], bundle['candidate_id'])
        assert len(summary['missing_experiments']) == 2 and summary['attempt_job_id'] is None
        policy = load_json(w.numerical_documents._folder(plan['id']) / 'commands' / 'Cactual_sample_policy.json')
        assert policy['response']['command_id'] == 'Cactual_sample_policy'
        captured = command(w.numerical_documents, plan, CAPTURE,
            {'source': bundle['source'], 'candidate_id': bundle['candidate_id'],
             'attempt_job_id': bundle['attempt']['id'], 'purpose': SUCCESS})
        reference = captured['reference']
        evidence = w.research_reference(reference)['candidate_evidence']
        assert evidence['readiness']['lineage']['status'] == 'CANONICAL_DATA_CONSUMER_VERIFIED'
        assert evidence['readiness']['preservation'] == 'IMMUTABLE_REVISION_VERIFIED'
        snapshot = deepcopy(evidence['snapshot'])
        assert snapshot['fit_input']['inputs']['frozen_inclusion'] == packet
        assert snapshot['original_candidate'] == view['candidate']
        for old, new in zip(view['fit_input']['inputs']['experiments'], snapshot['fit_input']['inputs']['experiments']):
            for key in ('processing_channel', 'sample_ids', 'coordinate_sample_ids', 'target_grid'):
                assert old['observations'][key] == new['observations'][key]
        data = command(w.data_documents, w.document_read(bundle['data']['id']), 'document.save')['document']
        command(w.material_documents, w.document_read(bundle['material']['id']), 'document.save')
    finally:
        assert w.shutdown()['joined']
    moved = tmp_path / '새 경로 한글 공백'
    shutil.move(str(original), moved)
    # Only this test's own temporary artifacts are removed. Saved revisions
    # must supply all subsequent reads; the child has no synthetic registration.
    for path in (moved / 'inputs', moved / 'results', moved / 'documents' / data['id'] / 'processing',
                 moved / 'documents' / plan['id'] / 'candidate_evidence'):
        assert path.resolve().is_relative_to(tmp_path.resolve())
        if path.exists(): shutil.rmtree(path)
    request = tmp_path / 'cold-request.json'
    save_json(request, {'workspace': str(moved), 'reference': reference,
        'plan_id': plan['id'], 'fit_job_id': bundle['fit_job']['id'],
        'candidate_id': bundle['candidate_id'], 'attempt_job_id': bundle['attempt']['id']})
    child = r"""
import json,sys
from pathlib import Path
from caelab.workbench import Workbench
from caelab.storage import load_json,canonical_hash
from caelab.numerical_candidate_detail import read_candidate_detail,table_rows
q=load_json(Path(sys.argv[1]));w=Workbench(q['workspace'])
def no_submit(*a,**k):raise AssertionError('Cold reader submitted a job')
w.submit=no_submit;w.manager.submit=no_submit
try:
    report=w.research_reference(q['reference'])
    selected=read_candidate_detail(w.numerical_documents,q['plan_id'],q['fit_job_id'],
        q['candidate_id'],attempt_job_id=q['attempt_job_id'])
    print(json.dumps({'snapshot':canonical_hash(report['candidate_evidence']['snapshot']),
        'rows':canonical_hash(table_rows(selected,selected['trials'][0]['experiment_id'])),
        'original':canonical_hash(w.numerical_documents.result(q['plan_id'],q['fit_job_id']))}))
finally:assert w.shutdown()['joined']
"""
    process = subprocess.run([sys.executable, '-X', 'utf8', '-c', child, str(request)],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, encoding='utf-8', timeout=50)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout) == {'snapshot': canonical_hash(snapshot),
        'rows': canonical_hash(rows), 'original': digest}
