"""Public, synthetic Data/Material/Plan workflow. No private files or solver calls.

python -m examples.portable_connection_public --output <NEW FOLDER>
The example's own original store is deleted before a separate-process reopen.
No supplied/user store is ever removed. Physics qualification is NOT_RELEASED.
"""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from caelab.connection_graph import build_graph
from caelab.jobs import TERMINAL
from caelab.numerical_document import from_material_document
from caelab.portable_project import create_copy, inspect_copy, open_project, verify_project
from caelab.storage import canonical_hash, save_json
from caelab.workbench import Workbench


def command(wb, doc, op, args=None):
    return wb.document_command(doc['id'], op, args or {}, session_id=wb.session_id,
                               expected_generation=doc['generation'])['document']


def save(wb, doc):
    return command(wb, doc, 'document.save')


def wait(wb, job_id):
    end = time.monotonic() + 20
    while time.monotonic() < end:
        job = wb.manager.status(job_id)
        if job['state'] in TERMINAL:
            return job
        time.sleep(.01)
    raise TimeoutError('Public file import did not finish')


def create_public_store(folder):
    """Create real owner documents and real successful/failed table imports."""
    folder = Path(folder)
    if folder.exists():
        raise FileExistsError(folder)
    wb = Workbench(folder)
    try:
        receipt = wb.upload('공개 인장 시험.csv', b'time,stress\n0,0\n1,1.2\n2,2.4\n')
        draft = {'data_id': receipt['id'], 'mapping': {'delimiter': ',', 'skip_header': 1,
            'columns': {'stress': {'column': 1, 'unit': 'MPa', 'component': 'xx',
                'location': 'material_point', 'measure': 'infinitesimal_Cauchy', 'frame': 'material_cartesian',
                'coordinate_system': 'UNSPECIFIED', 'axis': {'column': 0, 'name': 'time', 'unit': 's'}}}},
            'test_metadata': {'test_id': 'PUBLIC_SYNTHETIC', 'specimen': '공개 예제', 'protocol': '예제 데이터', 'temperature': 'UNKNOWN'}}
        data = wb.document_open(kind='data', title='공개 인장 시험', draft=draft)
        response = wb.document_command(data['id'], 'data.import', {}, session_id=wb.session_id, expected_generation=data['generation'])
        success = wait(wb, response['job']['id'])
        if success['state'] != 'SUCCEEDED':
            raise RuntimeError(success)
        data = wb.document_read(data['id'])
        # A real out-of-range table column passes structural draft validation
        # but fails the file import. This is not a simulated solver failure.
        invalid = deepcopy(draft)
        invalid['mapping']['columns']['stress']['column'] = 9
        data = command(wb, data, 'data.update', {'draft': invalid})
        response = wb.document_command(data['id'], 'data.import', {}, session_id=wb.session_id, expected_generation=data['generation'])
        failure = wait(wb, response['job']['id'])
        if failure['state'] != 'FAILED':
            raise RuntimeError('Expected actual table import failure: ' + str(failure))
        data = command(wb, wb.document_read(data['id']), 'data.update', {'draft': draft})
        data = save(wb, data)
        material = save(wb, wb.document_open(kind='material', title='공개 탄성 재료'))
        plan_draft = from_material_document(material)
        source_run = next(r for r in data['runs'] if r['job_id'] == success['id'])
        plan_draft['experiments'] = [{'id': 'Epublic', 'role': 'fit', 'source': {
            'document_id': data['id'], 'job_id': source_run['job_id'], 'response': 'stress',
            'input_revision': source_run['input_revision'], 'input_sha256': source_run['input_sha256']},
            'response': 'stress_xx', 'settings': deepcopy(material['draft']['settings']), 'weight': 1., 'scale': 1.}]
        plan = save(wb, wb.document_open(kind='numerical', title='공개 재료 피팅 계획', draft=plan_draft))
        # Two actual Numerical owner IDs, not two catalog keys.
        second_draft = from_material_document(material)
        second_draft.update(mode='doe', count=4)
        second = save(wb, wb.document_open(kind='numerical', title='공개 계수 탐색 계획', draft=second_draft))
        return wb, {'data': data, 'material': material, 'plan': plan, 'second_plan': second,
                    'success_job': success, 'failure_job': failure}
    except BaseException:
        wb.shutdown()
        raise


def cold_check(folder):
    wb = open_project(folder)
    try:
        documents = wb.documents()['documents']
        data = next(d for d in documents if d['kind'] == 'data')
        material = next(d for d in documents if d['kind'] == 'material')
        plans = [d for d in documents if d['kind'] == 'numerical']
        assert len(plans) == 2 and len({p['id'] for p in plans}) == 2
        assert not wb.manager.list(), 'Opening must not recreate controller jobs'
        preview = wb.document_source_preview(data['id'])
        assert '2.4' in preview['text'] and preview['retained'] is True
        states = {}
        for run in data['runs']:
            job = wb.desktop.job_record(run['job_id'])
            states[job['state']] = job
            if run.get('retained_result'):
                result = wb.document_result(data['id'], run['job_id'])
                assert result['responses']['stress']['unit'] == 'MPa'
                assert result['responses']['stress']['frame'] == 'material_cartesian'
        assert {'SUCCEEDED', 'FAILED'} <= states.keys()
        assert states['FAILED']['error']['message']
        for plan in plans:
            assert plan['draft']['material']['document_id'] == material['id']
        # Edit and save through the existing owner commands; no copy-only editor.
        draft = deepcopy(material['draft'])
        draft['settings']['parameters']['E'] += 10
        updated = command(wb, material, 'material.update', {'draft': draft})
        updated = save(wb, updated)
        original_hash = canonical_hash(wb.document_result(data['id'], data['runs'][0]['job_id']))
        # Data remains editable even without its original input registration.
        new_data_draft = deepcopy(data['draft'])
        new_data_draft['test_metadata']['protocol'] = '사본 편집 후 저장'
        data = save(wb, command(wb, data, 'data.update', {'draft': new_data_draft}))
        assert canonical_hash(wb.document_result(data['id'], data['runs'][0]['job_id'])) == original_hash
        graph = build_graph(wb)
        assert any(n['status'] == 'INPUT_CHANGED' for n in graph['nodes'])
        return {'status': 'PASSED', 'documents': len(documents), 'states': sorted(states),
                'raw_source_retained': True, 'edited_and_saved': True, 'executed_on_reopen': False,
                'engineering_release': 'NOT_RELEASED'}
    finally:
        wb.shutdown()


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output')
    parser.add_argument('--cold-check')
    args = parser.parse_args(argv)
    if args.cold_check:
        print(json.dumps(cold_check(args.cold_check), ensure_ascii=False))
        return 0
    if not args.output:
        parser.error('--output is required')
    root = Path(args.output).absolute()
    root.mkdir(parents=False, exist_ok=False)
    original = root / '공개 원본 보관소'
    wb, fixture = create_public_store(original)
    try:
        chosen = [fixture[k]['id'] for k in ('data', 'material', 'plan', 'second_plan')]
        inspection = inspect_copy(wb, chosen)
        if inspection['status'] != 'READY':
            raise RuntimeError(inspection)
        receipt = create_copy(wb, inspection, root / '작업 사본', approved=True,
                              command_id='Cpublic_copy', session_id=wb.session_id)
    finally:
        wb.shutdown()
    shutil.rmtree(original)  # Only the synthetic store created above, never a caller store.
    moved = root / '한글 공백 경로 옮긴 사본'
    (root / '작업 사본').rename(moved)
    completed = subprocess.run([sys.executable, '-m', 'examples.portable_connection_public', '--cold-check', str(moved)],
                               capture_output=True, text=True, check=True, timeout=60)
    result = json.loads(completed.stdout)
    result.update(original_store_deleted=not original.exists(), moved_workspace=str(moved),
                  verification_after_edit=verify_project(moved)['status'])
    save_json(root / 'public-check.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
